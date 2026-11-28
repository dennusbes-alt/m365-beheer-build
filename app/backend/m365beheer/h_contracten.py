"""Contracten vanuit Sales (snelle invoer, sales en de app-beheerder; 'sa.'-poort is_sales).

- Vaste prijs-ticket (`sa.vasteprijs`): bijv. 'Nieuwe computer' = product(en) uit de voorraad (TicketCharges, gewoon
  gefactureerd) + installatie voor een vaste prijs. De app maakt een Fixed Price-contract (nooit het standaardcontract), een
  mijlpaal (ContractMilestones) met de vaste prijs en een ticket op dat contract (uren vallen dan niet apart op de factuur).
- Vaste prijs voor een project (`sa.contract.vast` met opportunityId), bijv. een afgesproken migratieprijs: Fixed Price-contract
  + mijlpaal; het project van de kans krijgt dat contract (nu als het project er al is, anders bij pr.vankans). Koppeling
  kans -> contract gedeeld als 'sales-contracten'.
- Full Service (`sa.contract.full`): Recurring Service-contract (contractType 7) als standaardcontract van de klant, met de dienst
  (ContractServices, maandprijs als adjustedPrice) en after hours / emergency uitgesloten (ContractExclusionBillingCodes voor
  de werktype-codes met die naam). Alles valt eronder behalve die codes.
Verplicht bij Contracts (docs): companyID (actieve Customer), contractName, contractType, startDate < endDate, status,
timeReportingRequiresStartAndStopTimes; niet-recurring ook estimatedCost/Hours/Revenue; recurring ook contractPeriodType, setupFee.
NIET getest met een echte Autotask (picklistwaarden contractType/status/periode, child-URL's Milestones/Services).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import is_sales

log = logging.getLogger('m365beheer')
BUITEN_UREN = re.compile(r'after.?hours|emergency|spoed|nood|buiten\s*(kantoor|werk)?\s*(uren|tijd)', re.I)


def _eis(c: Ctx) -> None:
    if not is_sales(c.staat):
        raise ApiFout('Contracten maken doen sales en de app-beheerder.')


def _iso(d: datetime) -> str:
    return d.strftime('%Y-%m-%dT00:00:00Z')


def _pl(at, ent: str, veld: str) -> list[dict]:
    return at.picklists(ent).get(veld, [])


def _label(at, ent: str, veld: str, patroon: str, standaard=None):
    from .h_sales import getal
    return getal(next((p['value'] for p in _pl(at, ent, veld) if re.search(patroon, str(p.get('label') or ''), re.I)), standaard))


def soort(at, wat: str):
    if wat == 'fixed':
        w = _label(at, 'Contracts', 'contractType', r'fixed|vaste')
    else:
        w = _label(at, 'Contracts', 'contractType', r'recurring|terugkerend', 7)
    if w is None:
        raise ApiFout("Autotask kent het contracttype 'Fixed Price' niet.")
    return w


def _actief(at):
    st = _pl(at, 'Contracts', 'status')
    from .h_sales import getal
    return getal(next((p['value'] for p in st if re.fullmatch(r'\s*(active|actief)\s*', str(p.get('label') or ''), re.I)),
                      next((p['value'] for p in st if p.get('default')), 1)))


def _post_kind(at, ouder: str, oid: int, kind: str, los: str, body: dict) -> dict:
    try:
        return at.req('POST', f'{ouder}/{oid}/{kind}', body)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        return at.req('POST', los, body)


def vast_contract(at, company: int, naam: str, bedrag: float, uren: float, start: datetime | None = None, maanden: int = 3,
                  omschrijving: str = '') -> dict:
    """Fixed Price-contract met één mijlpaal (de vaste prijs). Nooit het standaardcontract."""
    if bedrag <= 0:
        raise ApiFout('Vul de vaste prijs in.')
    start = start or datetime.now(timezone.utc)
    body = {'companyID': int(company), 'contractName': naam[:100], 'contractType': soort(at, 'fixed'), 'status': _actief(at),
            'startDate': _iso(start), 'endDate': _iso(start + timedelta(days=31 * max(1, maanden))), 'isDefaultContract': False,
            'timeReportingRequiresStartAndStopTimes': 0, 'estimatedHours': round(float(uren or 0), 2), 'estimatedRevenue': round(float(bedrag), 2),
            'estimatedCost': 0, 'description': omschrijving[:2000] or None}
    r = at.req('POST', 'Contracts', {k: v for k, v in body.items() if v is not None})
    cid = (r or {}).get('itemId')
    if not cid:
        raise ApiFout('Autotask gaf geen contractnummer terug.')
    mijl = {'contractID': cid, 'title': naam[:100], 'amount': round(float(bedrag), 2), 'dateDue': _iso(start), 'isInitialPayment': True,
            'status': _label(at, 'ContractMilestones', 'status', r'ready|bill|klaar|factur', None)}
    code = _code(at, r'milestone|mijlpaal')
    if code:
        mijl['billingCodeID'] = code
    if mijl['status'] is None:
        lijst = _pl(at, 'ContractMilestones', 'status')
        mijl['status'] = lijst[0]['value'] if lijst else 1
    fout = None
    try:
        _post_kind(at, 'Contracts', cid, 'Milestones', 'ContractMilestones', mijl)
    except ApiFout as e:
        fout = str(e)[:200]
        log.info('Mijlpaal bij vaste prijs-contract: %s', e)
    return {'id': cid, 'name': naam, 'milestoneError': fout}


def _code(at, patroon: str) -> int | None:
    """Eerste actieve BillingCode van een soort (useType-label), bijv. Milestone."""
    st = next((p['value'] for p in at.picklists('BillingCodes').get('useType', []) if re.search(patroon, str(p.get('label') or ''), re.I)), None)
    if st is None:
        return None
    try:
        r = at.query('BillingCodes', [{'op': 'eq', 'field': 'useType', 'value': st}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id'], 1)
    except ApiFout:
        return None
    return r[0]['id'] if r else None


def buiten_uren_codes(at) -> list[dict]:
    """Werktype-codes (BillingCodes) voor after hours / emergency: vallen buiten het Full Service-contract."""
    wt = next((p['value'] for p in at.picklists('BillingCodes').get('useType', []) if re.search(r'work\s*type|werksoort|werktype', str(p.get('label') or ''), re.I)), 1)
    r = at.query('BillingCodes', [{'op': 'eq', 'field': 'useType', 'value': wt}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'name'], 500)
    return [{'id': x['id'], 'name': x.get('name') or ''} for x in r if BUITEN_UREN.search(str(x.get('name') or ''))]


def _koppelingen() -> dict:
    w = GEDEELD.lees_raw('sales-contracten', 60)
    try:
        return json.loads(w) if w else {}
    except ValueError:
        return {}


def contract_van_kans(kid: int) -> int | None:
    return (_koppelingen().get(str(kid)) or {}).get('contractId')


@api('sa.contract.opties')
def sa_contract_opties(c: Ctx, b: dict) -> dict:
    """Keuzes voor de snelle invoer: diensten (voor Full Service), after hours-codes, en de contracten van de klant."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    uit: dict = {'services': [], 'excluded': [], 'contracts': []}
    try:
        uit['services'] = [{'id': s['id'], 'name': s.get('name') or '', 'price': float(s.get('unitPrice') or 0)}
                           for s in at.query('Services', [{'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'name', 'unitPrice'], 500)]
        uit['services'].sort(key=lambda s: (0 if re.search(r'full|beheer|managed', s['name'], re.I) else 1, s['name'].lower()))
    except ApiFout as e:
        log.info('Services ophalen: %s', e)
    try:
        uit['excluded'] = buiten_uren_codes(at)
    except ApiFout as e:
        log.info('After hours-codes ophalen: %s', e)
    if b.get('companyId'):
        types = {str(p['value']): p['label'] for p in _pl(at, 'Contracts', 'contractType')}
        r = at.query('Contracts', [{'op': 'eq', 'field': 'companyID', 'value': int(b['companyId'])}, {'op': 'eq', 'field': 'status', 'value': _actief(at)}],
                     ['id', 'contractName', 'contractType', 'startDate', 'endDate', 'isDefaultContract', 'estimatedRevenue'], 100)
        uit['contracts'] = [{'id': x['id'], 'name': x.get('contractName') or '', 'type': types.get(str(x.get('contractType')), ''),
                             'start': str(x.get('startDate') or '')[:10], 'end': str(x.get('endDate') or '')[:10], 'default': bool(x.get('isDefaultContract')),
                             'amount': float(x.get('estimatedRevenue') or 0)} for x in r]
        uit['fullService'] = any(re.search(r'recurring', x['type'], re.I) and x['default'] for x in uit['contracts'])
    if b.get('opportunityId'):
        uit['projectContract'] = contract_van_kans(int(b['opportunityId']))
    from .h_sdniveau import inrichting
    uit['rate'] = inrichting().get('tariefL2') or inrichting().get('tariefL1')
    return uit


@api('sa.contract.vast')
def sa_contract_vast(c: Ctx, b: dict) -> dict:
    """Vaste prijs-contract voor een klant, optioneel gekoppeld aan (het project van) een saleskans."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis(c)
    at = A._at()
    company = int(b.get('companyId') or 0)
    if not company:
        raise ApiFout('Kies de klant.')
    naam = str(b.get('name') or 'Vaste prijs').strip()
    con = vast_contract(at, company, naam, float(b.get('amount') or 0), float(b.get('hours') or 0),
                        datetime.fromisoformat(str(b['start'])[:10]).replace(tzinfo=timezone.utc) if b.get('start') else None,
                        int(b.get('months') or 3), str(b.get('description') or ''))
    project = None
    if b.get('opportunityId'):
        kid = int(b['opportunityId'])
        k = _koppelingen()
        k[str(kid)] = {'contractId': con['id'], 'at': datetime.now().isoformat(timespec='minutes')}
        GEDEELD.schrijf_raw('sales-contracten', json.dumps(k, separators=(',', ':')))
        GEDEELD.cache.pop('raw:sales-contracten', None)
        p = at.query('Projects', [{'op': 'eq', 'field': 'opportunityID', 'value': kid}], ['id', 'projectName'], 1)
        if p:
            at.req('PATCH', 'Projects', {'id': p[0]['id'], 'contractID': con['id']})
            project = p[0].get('projectName')
    c.L(f"Vaste prijs-contract '{naam}' aangemaakt (€ {float(b.get('amount') or 0):.2f})" + (f", gekoppeld aan project {project}" if project else
                                                                                                ', wordt gekoppeld aan het project van de kans' if b.get('opportunityId') else '') + '.')
    return {'contract': con, 'project': project}


@api('sa.contract.full')
def sa_contract_full(c: Ctx, b: dict) -> dict:
    """Full Service-klant: Recurring Service-contract (standaardcontract) met de dienst; after hours/emergency uitgesloten."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis(c)
    at = A._at()
    company = int(b.get('companyId') or 0)
    if not company:
        raise ApiFout('Kies de klant.')
    if not b.get('serviceId'):
        raise ApiFout('Kies de dienst (Service) voor het Full Service-contract.')
    start = datetime.fromisoformat(str(b.get('start') or datetime.now().strftime('%Y-%m-01'))[:10]).replace(tzinfo=timezone.utc)
    maanden = max(1, int(b.get('months') or 12))
    periode = _label(at, 'Contracts', 'contractPeriodType', r'month|maand')
    klantnaam = (at.req('GET', f'Companies/{company}').get('item') or {}).get('companyName') or str(b.get('companyName') or '').strip()
    body = {'companyID': company, 'contractName': f'Full Service - {klantnaam}'.strip(' -')[:100], 'contractType': soort(at, 'full'),   # vaste naamgeving Justdata
            'status': _actief(at), 'startDate': _iso(start), 'endDate': _iso(start + timedelta(days=round(30.44 * maanden)) - timedelta(days=1)),
            'isDefaultContract': True, 'timeReportingRequiresStartAndStopTimes': 0, 'setupFee': round(float(b.get('setupFee') or 0), 2),
            'contractPeriodType': periode, 'description': str(b.get('description') or '')[:2000] or None}
    r = at.req('POST', 'Contracts', {k: v for k, v in body.items() if v is not None})
    cid = (r or {}).get('itemId')
    if not cid:
        raise ApiFout('Autotask gaf geen contractnummer terug.')
    fouten = []
    dienst = {'contractID': cid, 'serviceID': int(b['serviceId'])}
    if b.get('monthly') not in (None, ''):
        dienst['adjustedPrice'] = round(float(b['monthly']), 2)
    try:
        _post_kind(at, 'Contracts', cid, 'Services', 'ContractServices', dienst)
    except ApiFout as e:
        fouten.append(f'dienst: {str(e)[:160]}')
    uitgesloten = []
    for code in buiten_uren_codes(at):
        try:
            _post_kind(at, 'Contracts', cid, 'ExclusionBillingCodes', 'ContractExclusionBillingCodes', {'contractID': cid, 'billingCodeID': code['id']})
            uitgesloten.append(code['name'])
        except ApiFout as e:
            fouten.append(f"{code['name']}: {str(e)[:120]}")
    c.L(f"Full Service-contract aangemaakt (standaardcontract)" + (f"; buiten het contract: {', '.join(uitgesloten)}" if uitgesloten else '') + '.')
    return {'contract': {'id': cid, 'name': body['contractName']}, 'excluded': uitgesloten, 'errors': fouten}


@api('sa.vasteprijs')
def sa_vasteprijs(c: Ctx, b: dict) -> dict:
    """Vaste prijs-ticket: {companyId, contactId?, title, description?, products: [{productId, qty}], hours, amount, assign: 'queue'|'me'}."""
    from . import h_autotask as A
    from . import h_voorraad as V
    _zet_auth(c)
    _eis(c)
    at = A._at()
    company = int(b.get('companyId') or 0)
    titel = str(b.get('title') or '').strip()
    if not company or not titel:
        raise ApiFout('Kies de klant en vul het onderwerp in (bijv. Nieuwe computer).')
    regels = [x for x in (b.get('products') or []) if x.get('productId')]
    prods = {p['id']: p for p in V.producten(at)}
    voorraad = V._stand(True)['stock']
    for x in regels:
        if int(x['productId']) not in prods:
            raise ApiFout('Een gekozen product bestaat niet meer (ververs de lijst).')
    bedrag = float(b.get('amount') or 0)
    con = vast_contract(at, company, f'Vaste prijs - {titel}'[:100], bedrag, float(b.get('hours') or 0), omschrijving=str(b.get('description') or '')) if bedrag > 0 else None
    ik, inst = A._ik(at), A._instellingen()
    oms = (str(b.get('description') or '').strip() or titel) + (f"\n\nVaste prijs: € {bedrag:.2f} ({float(b.get('hours') or 0):g} uur)" if con else '')
    t = A._nieuw_ticket(at, company, titel[:250], oms, ik, inst, int(b['contactId']) if b.get('contactId') else None,
                        contract=con['id'] if con else None, zelf=b.get('assign') == 'me')
    besteld, fouten = [], []
    for x in regels:
        p, n = prods[int(x['productId'])], max(1, int(x.get('qty') or 1))
        try:
            V.ticket_product(at, t['id'], p, n)
        except ApiFout as e:
            fouten.append(f"{p['name']}: {str(e)[:120]}")
            continue
        if voorraad.get(str(p['id']), 0) < n:   # niet (genoeg) op voorraad: meteen op de bestellijst voor dit ticket
            V.vr_bestellen(c, {'productId': p['id'], 'qty': n - max(0, voorraad.get(str(p['id']), 0)), 'ticketId': t['id'], 'ticketNumber': t['number'],
                               'note': 'Voor vaste prijs-ticket (product staat al op het ticket)', 'charged': True})
            besteld.append(p['name'])
    A.lijst_wissen(company)
    c.L(f"Vaste prijs-ticket {t['number']} aangemaakt: {titel}" + (f" (€ {bedrag:.2f} vast)" if con else '') + (f", {len(regels)} product(en)" if regels else '') + '.')
    from .h_servicedesk import _link
    return {'ticket': {**t, 'url': _link(at, t['id'])}, 'contract': con, 'ordered': besteld, 'errors': fouten}
