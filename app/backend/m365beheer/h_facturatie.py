"""Facturatie (startscherm > Facturatie): uurtje-factuurtje buiten de full-service-contracten, per klant goedkeuren en afvinken
zodra de factuur in Exact staat. Alleen voor wie facturen goedkeurt (rechten.FACTURATIE).

Wat te factureren is
- Factureerbare tijdregels (isNonBillable = false) in de periode, zonder contract of op een Time & Materials-contract.
  Tijd op full-service-contracten (recurring service, vaste prijs, strippenkaart, retainer, per ticket) valt erbuiten.
- Tickets met status 'Ready to Invoice' (bijv. licentiewijzigingen) staan erbij, ook als er geen uren op staan.
- Tarief: ingestelde L1/L2-tarieven (Servicedesk > Inrichting), anders het uurtarief van de rol in Autotask (Roles.hourlyRate).

Proces: goedkeuren (wie/wanneer) -> in Exact verwerken -> 'Verwerkt in Exact' afvinken: de regels verdwijnen uit de lijst
en de Ready-to-Invoice-tickets van die klant gaan (optioneel) op Complete. Autotask heeft geen API voor 'Approve and Post';
de stand staat daarom gedeeld in de verborgen SharePoint-lijst ('facturatie'). Terugdraaien kan via de historie.
NIET getest met een echte Autotask (contractType-waarden, hoursToBill, Roles.hourlyRate).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth

log = logging.getLogger('m365beheer')
BTW = 0.21
_lock = threading.Lock()
_CACHE: dict = {}


def _stand(vers: bool = False) -> dict:
    w = GEDEELD.lees_raw('facturatie', 0 if vers else 60)
    try:
        d = json.loads(w) if w else {}
    except ValueError:
        d = {}
    return {'verwerkt': d.get('verwerkt') or [], 'goedgekeurd': d.get('goedgekeurd') or {}}


def _bewaar(d: dict) -> None:
    grens = (datetime.now() - timedelta(days=400)).isoformat()
    d['verwerkt'] = [v for v in d['verwerkt'] if v.get('at', '') >= grens]   # ouder dan ruim een jaar valt buiten elke periode
    GEDEELD.schrijf_raw('facturatie', json.dumps(d, separators=(',', ':')))
    GEDEELD.cache.pop('raw:facturatie', None)
    _CACHE.clear()


def _wie(c: Ctx) -> str:
    try:
        from . import h_autotask as A
        return A._ik(A._at())['name']
    except ApiFout:
        return str((c.staat.auth.account or {}).get('name') or (c.staat.auth.account or {}).get('username') or '')


def ophalen(dagen: int) -> dict:
    """Ruwe gegevens uit Autotask (los te vervangen in de testmodus)."""
    from . import h_autotask as A
    from .h_management import _in
    from concurrent.futures import ThreadPoolExecutor
    at = A._at()
    begin = (datetime.now(timezone.utc) - timedelta(days=dagen)).strftime('%Y-%m-%dT00:00:00Z')
    eind = A.eindstatussen(at)

    def geboekt():
        """Al goedgekeurd en geboekt in Autotask (Approve and Post) = er is een BillingItem; met invoiceID = gefactureerd.
        Die uren staan niet meer open en horen niet in deze lijst."""
        try:
            r = at.query('BillingItems', [{'op': 'gte', 'field': 'itemDate', 'value': begin}, {'op': 'exist', 'field': 'timeEntryID'}],
                         ['timeEntryID', 'invoiceID'], 20000, 20000)
            return {x['timeEntryID'] for x in r if x.get('timeEntryID')}
        except ApiFout as e:
            log.info('Facturatie: BillingItems niet opgehaald (%s); geboekte uren kunnen in de lijst staan', e)
            return None
    def kosten():
        """Producten op tickets (TicketCharges): factureerbaar en nog niet gefactureerd. Ook bij een contract (alleen de uren
        vallen onder een contract, producten niet)."""
        try:
            return at.query('TicketCharges', [{'op': 'gte', 'field': 'datePurchased', 'value': begin}, {'op': 'eq', 'field': 'isBillableToCompany', 'value': True},
                                              {'op': 'eq', 'field': 'isBilled', 'value': False}],
                            ['id', 'ticketID', 'name', 'productID', 'unitQuantity', 'unitPrice', 'datePurchased'], 5000, 5000)
        except ApiFout as e:
            log.info('Facturatie: TicketCharges niet opgehaald (%s)', e)
            return []

    def mijlpalen():
        """Vaste prijs-contracten: mijlpalen die nog niet gefactureerd zijn (status niet 'billed')."""
        try:
            r = at.query('ContractMilestones', [{'op': 'gte', 'field': 'dateDue', 'value': begin}], ['id', 'contractID', 'title', 'amount', 'dateDue', 'status'], 2000)
            klaar = {str(p['value']) for p in at.picklists('ContractMilestones').get('status', []) if re.search(r'billed|gefactureerd|invoiced', str(p.get('label') or ''), re.I)}
            return [m for m in r if str(m.get('status')) not in klaar and float(m.get('amount') or 0) > 0]
        except ApiFout as e:
            log.info('Facturatie: ContractMilestones niet opgehaald (%s)', e)
            return []
    with ThreadPoolExecutor(max_workers=5) as ex:
        f_kosten, f_mijl = ex.submit(kosten), ex.submit(mijlpalen)
        f_tijd = ex.submit(at.query, 'TimeEntries', [{'op': 'gte', 'field': 'dateWorked', 'value': begin}, {'op': 'eq', 'field': 'isNonBillable', 'value': False}],
                           ['id', 'ticketID', 'taskID', 'resourceID', 'roleID', 'dateWorked', 'hoursWorked', 'hoursToBill', 'summaryNotes', 'contractID'], 10000, 10000)
        f_rti = ex.submit(lambda: at.query('Tickets', [{'op': 'eq', 'field': 'status', 'value': eind['invoice']}], ['id', 'ticketNumber', 'title', 'companyID', 'status'], 1000)
                          if eind['invoice'] is not None else [])
        f_geboekt = ex.submit(geboekt)
        alle_tijd, rti, gb = f_tijd.result(), f_rti.result(), f_geboekt.result()
        charges, mijl = f_kosten.result(), f_mijl.result()
    tijd = [x for x in alle_tijd if not gb or x['id'] not in gb]
    al_geboekt = round(sum(float(x.get('hoursToBill') if x.get('hoursToBill') is not None else x.get('hoursWorked') or 0) for x in alle_tijd if gb and x['id'] in gb), 1)
    cpl = at.picklists('Contracts').get('contractType', [])
    tm = {p['value'] for p in cpl if re.search(r'time.*material|tijd.*materia|nacalculatie', str(p.get('label') or ''), re.I)} or {1}
    with ThreadPoolExecutor(max_workers=5) as ex:
        f_c = ex.submit(_in, at, 'Contracts', {x.get('contractID') for x in tijd}, ['id', 'contractType', 'contractName'])
        f_t = ex.submit(_in, at, 'Tickets', {x.get('ticketID') for x in tijd} | {x.get('ticketID') for x in charges}, ['id', 'ticketNumber', 'title', 'companyID', 'status'])
        f_mc = ex.submit(_in, at, 'Contracts', {m.get('contractID') for m in mijl}, ['id', 'contractName', 'companyID'])
        f_k = ex.submit(_in, at, 'Tasks', {x.get('taskID') for x in tijd}, ['id', 'title', 'projectID'])
        f_m = ex.submit(_in, at, 'Resources', {x.get('resourceID') for x in tijd}, ['id', 'firstName', 'lastName'])
        f_r = ex.submit(_in, at, 'Roles', {x.get('roleID') for x in tijd}, ['id', 'name', 'hourlyRate'])
        contracten = {x['id']: x for x in f_c.result()}
        tickets = {x['id']: x for x in f_t.result()}
        taken = {x['id']: x for x in f_k.result()}
        mensen = {x['id']: f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip() for x in f_m.result()}
        rollen = {x['id']: x for x in f_r.result()}
        vaste = {x['id']: x for x in f_mc.result()}
    tickets.update({t['id']: t for t in rti})
    projecten = {x['id']: x for x in _in(at, 'Projects', {t.get('projectID') for t in taken.values()}, ['id', 'projectName', 'companyID'])}
    bedrijven = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {t.get('companyID') for t in tickets.values()} | {p.get('companyID') for p in projecten.values()}
                                                                   | {v.get('companyID') for v in vaste.values()},
                                                                   ['id', 'companyName'])}
    from .h_servicedesk import _link
    return {'tijd': tijd, 'rti': [t['id'] for t in rti], 'contracten': contracten, 'tm': tm, 'tickets': tickets, 'taken': taken, 'projecten': projecten,
            'bedrijven': bedrijven, 'mensen': mensen, 'rollen': rollen, 'link': lambda tid: _link(at, tid), 'eind': eind,
            'alGeboekt': al_geboekt, 'geboektBekend': gb is not None, 'charges': charges,
            'mijlpalen': [{**m, 'contract': vaste.get(m.get('contractID')) or {}} for m in mijl],
            'klaarT': A._klaar(at, 'Tickets') | ({A._instellingen()['statusKlaar']} if A._instellingen().get('statusKlaar') else set())}


def overzicht(dagen: int, vers: bool = False, onderhanden: bool = False) -> dict:
    sleutel = ('ov', dagen, onderhanden)
    item = _CACHE.get(sleutel)
    if item and not vers and time.time() - item[0] < 120:
        return item[1]
    from .h_sdniveau import inrichting, niveau
    ruw = _CACHE.get(('ruw', dagen))   # Autotask-gegevens apart onthouden: wisselen tussen met/zonder onderhanden is dan direct
    if ruw and not vers and time.time() - ruw[0] < 120:
        r = ruw[1]
    else:
        r = ophalen(dagen)
        _CACHE[('ruw', dagen)] = (time.time(), r)
    st = _stand(vers)
    gedaan = {i for v in st['verwerkt'] for i in v.get('ids') or []}
    gedaan_t = {i for v in st['verwerkt'] for i in v.get('tickets') or []}
    inr = inrichting()
    klanten: dict = {}

    def klant(cid):
        return klanten.setdefault(cid, {'id': cid, 'name': r['bedrijven'].get(cid, f'Bedrijf {cid}'), 'lines': [], 'tickets': {}})
    klaar_t = r.get('klaarT')   # statussen 'afgerond' van tickets (None in de testmodus = niet filteren)
    open_uren = open_bedrag = 0.0
    open_tickets: set = set()
    for x in r['tijd']:
        if x['id'] in gedaan:
            continue
        con = r['contracten'].get(x.get('contractID'))
        if x.get('contractID') and (not con or con.get('contractType') not in r['tm']):
            continue   # tijd op een full-service-contract (of onbekend contract): niet apart factureren
        t = r['tickets'].get(x.get('ticketID'))
        # Zoals Autotask Approve & Post: ticketuren pas als het ticket is afgerond. Daarvoor zijn ze 'onderhanden'.
        if t and klaar_t is not None and t.get('status') not in klaar_t and not onderhanden:
            h_ = float(x.get('hoursToBill') if x.get('hoursToBill') is not None else x.get('hoursWorked') or 0)
            rol_ = r['rollen'].get(x.get('roleID')) or {}
            n_ = niveau(x.get('resourceID'))
            open_uren += h_
            open_bedrag += h_ * ((inr['tariefL1'] if n_ in ('l1', 'l1lead') else inr['tariefL2'] if n_ == 'l2' else None) or float(rol_.get('hourlyRate') or 0))
            open_tickets.add(t['id'])
            continue
        taak = r['taken'].get(x.get('taskID'))
        proj = r['projecten'].get((taak or {}).get('projectID'))
        cid = (t or {}).get('companyID') or (proj or {}).get('companyID')
        if not cid:
            continue
        uren = float(x.get('hoursToBill') if x.get('hoursToBill') is not None else x.get('hoursWorked') or 0)
        n = niveau(x.get('resourceID'))
        rol = r['rollen'].get(x.get('roleID')) or {}
        tarief = (inr['tariefL1'] if n in ('l1', 'l1lead') else inr['tariefL2'] if n == 'l2' else None) or float(rol.get('hourlyRate') or 0)
        k = klant(cid)
        k['lines'].append({'id': x['id'], 'date': str(x.get('dateWorked') or '')[:10], 'ticketId': x.get('ticketID'),
                           'ref': (t or {}).get('ticketNumber') or ((proj or {}).get('projectName') or ''), 'title': (t or {}).get('title') or (taak or {}).get('title') or '',
                           'employee': r['mensen'].get(x.get('resourceID'), ''), 'level': 'L1' if n in ('l1', 'l1lead') else 'L2' if n == 'l2' else '',
                           'role': rol.get('name') or '', 'notes': re.sub(r'\s+', ' ', str(x.get('summaryNotes') or '')).strip()[:500],
                           'hours': round(uren, 2), 'rate': round(tarief, 2), 'amount': round(uren * tarief, 2),
                           'contract': (con or {}).get('contractName') or ''})
        if t:
            k['tickets'][t['id']] = {'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'rti': t['id'] in r['rti'],
                                     'url': r['link'](t['id'])}
    for x in r.get('charges') or []:   # producten op tickets: verkoopprijs x aantal, ook op een contract
        lid = f"p{x['id']}"
        t = r['tickets'].get(x.get('ticketID'))
        if lid in gedaan or not t or not t.get('companyID'):
            continue
        bedrag = round(float(x.get('unitQuantity') or 0) * float(x.get('unitPrice') or 0), 2)
        if t and klaar_t is not None and t.get('status') not in klaar_t and not onderhanden:
            open_bedrag += bedrag   # ticket nog niet afgerond: onderhanden
            open_tickets.add(t['id'])
            continue
        k = klant(t['companyID'])
        k['lines'].append({'id': lid, 'kind': 'product', 'date': str(x.get('datePurchased') or '')[:10], 'ticketId': t['id'], 'ref': t.get('ticketNumber') or '',
                           'title': t.get('title') or '', 'employee': '', 'level': '', 'role': '', 'notes': f"Product: {x.get('name') or ''}",
                           'hours': 0, 'qty': float(x.get('unitQuantity') or 0), 'rate': round(float(x.get('unitPrice') or 0), 2), 'amount': bedrag, 'contract': ''})
        k['tickets'][t['id']] = k['tickets'].get(t['id']) or {'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '',
                                                              'rti': t['id'] in r['rti'], 'url': r['link'](t['id'])}
    for m in r.get('mijlpalen') or []:   # vaste prijs (contractmijlpaal): het afgesproken bedrag, uren vallen eronder
        lid = f"m{m['id']}"
        cid = (m.get('contract') or {}).get('companyID')
        if lid in gedaan or not cid:
            continue
        k = klant(cid)
        k['lines'].append({'id': lid, 'kind': 'fixed', 'date': str(m.get('dateDue') or '')[:10], 'ticketId': None, 'ref': 'Vaste prijs',
                           'title': (m.get('contract') or {}).get('contractName') or m.get('title') or '', 'employee': '', 'level': '', 'role': '',
                           'notes': str(m.get('title') or ''), 'hours': 0, 'qty': 1, 'rate': round(float(m.get('amount') or 0), 2),
                           'amount': round(float(m.get('amount') or 0), 2), 'contract': (m.get('contract') or {}).get('contractName') or ''})
    for tid in r['rti']:   # Ready to Invoice zonder (nieuwe) uren, bijv. een licentiewijziging
        t = r['tickets'].get(tid)
        if not t or tid in gedaan_t or not t.get('companyID'):
            continue
        k = klant(t['companyID'])
        k['tickets'].setdefault(tid, {'id': tid, 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'rti': True, 'url': r['link'](tid)})
    uit = []
    for k in klanten.values():
        k['lines'].sort(key=lambda l: (l['date'], l['ref']))
        sub = round(sum(l['amount'] for l in k['lines']), 2)
        ids = sorted((l['id'] for l in k['lines']), key=str)   # uren (getal), producten 'p..', vaste prijs 'm..'
        g = st['goedgekeurd'].get(str(k['id']))
        tickets = sorted(k['tickets'].values(), key=lambda t: t['number'])
        uit.append({**k, 'tickets': tickets, 'hours': round(sum(l['hours'] for l in k['lines']), 2), 'subtotal': sub, 'vat': round(sub * BTW, 2),
                    'total': round(sub * (1 + BTW), 2), 'ids': ids, 'rtiCount': sum(1 for t in tickets if t['rti']),
                    'noRate': sum(1 for l in k['lines'] if not l['rate']),
                    'approved': ({'by': g.get('by'), 'at': g.get('at'), 'changed': sorted(g.get('ids') or [], key=str) != ids} if g else None)})
    uit.sort(key=lambda k: (-k['total'], k['name'].lower()))
    res = {'customers': uit, 'days': dagen, 'at': datetime.now().strftime('%H:%M'),
           'totals': {'customers': len(uit), 'subtotal': round(sum(k['subtotal'] for k in uit), 2), 'total': round(sum(k['total'] for k in uit), 2),
                      'hours': round(sum(k['hours'] for k in uit), 1), 'approved': sum(1 for k in uit if k['approved'] and not k['approved']['changed'])},
           'history': [{k: v for k, v in b.items() if k not in ('ids',)} for b in sorted(st['verwerkt'], key=lambda b: b.get('at', ''), reverse=True)[:30]],
           'invoiceStatus': r['eind']['invoice'] is not None, 'postedHours': r.get('alGeboekt', 0), 'postedKnown': r.get('geboektBekend', True),
           'wip': {'hours': round(open_uren, 1), 'amount': round(open_bedrag, 2), 'tickets': len(open_tickets)}, 'inclWip': onderhanden,
           'rtiTotal': sum(1 for k in uit for t in k['tickets'] if t['rti'])}
    _CACHE[sleutel] = (time.time(), res)
    return res


@api('fa.overzicht')
def fa_overzicht(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    return overzicht(max(14, min(366, int(b.get('days') or 365))), bool(b.get('fresh')), bool(b.get('wip')))


def _klant(c: Ctx, b: dict) -> tuple[dict, dict]:
    d = overzicht(max(14, min(366, int(b.get('days') or 365))), False, bool(b.get('wip')))
    k = next((x for x in d['customers'] if str(x['id']) == str(b.get('companyId'))), None)
    if not k:
        raise ApiFout('Deze klant staat niet (meer) in de lijst. Ververs het overzicht.')
    return d, k


@api('fa.goedkeuren')
def fa_goedkeuren(c: Ctx, b: dict) -> dict:
    """Goedkeuren (of goedkeuring intrekken) van wat er nu voor een klant klaarstaat."""
    _zet_auth(c)
    _, k = _klant(c, b)
    with _lock:
        st = _stand(True)
        if b.get('undo'):
            st['goedgekeurd'].pop(str(k['id']), None)
        else:
            st['goedgekeurd'][str(k['id'])] = {'ids': k['ids'], 'by': _wie(c), 'at': datetime.now().isoformat(timespec='minutes'), 'total': k['total']}
        _bewaar(st)
    c.L(f"Facturatie {k['name']}: " + ('goedkeuring ingetrokken.' if b.get('undo') else f"goedgekeurd (€ {k['total']:.2f} incl. btw)."))
    return {}


@api('fa.verwerkt')
def fa_verwerkt(c: Ctx, b: dict) -> dict:
    """Verwerkt in Exact: regels uit de lijst en (optioneel) de Ready-to-Invoice-tickets van deze klant op Complete."""
    from . import h_autotask as A
    _zet_auth(c)
    _, k = _klant(c, b)
    if not k['approved'] or k['approved']['changed']:
        raise ApiFout('Keur de factuur eerst goed (er is iets gewijzigd sinds de goedkeuring, of nog niet goedgekeurd).')
    rti = [t['id'] for t in k['tickets'] if t['rti']]
    gesloten, fout = 0, []
    if b.get('closeTickets', True) and rti:
        at = A._at()
        compleet = A.eindstatussen(at)['complete']
        for tid in rti:
            try:
                at.req('PATCH', 'Tickets', {'id': tid, 'status': compleet})
                gesloten += 1
            except ApiFout as e:
                fout.append(f'{tid}: {str(e)[:120]}')
    with _lock:
        st = _stand(True)
        st['verwerkt'].append({'id': uuid.uuid4().hex[:10], 'company': k['id'], 'name': k['name'], 'ids': k['ids'], 'tickets': [t['id'] for t in k['tickets']],
                               'hours': k['hours'], 'total': k['total'], 'subtotal': k['subtotal'], 'ref': str(b.get('ref') or '')[:60],
                               'by': _wie(c), 'at': datetime.now().isoformat(timespec='minutes')})
        st['goedgekeurd'].pop(str(k['id']), None)
        _bewaar(st)
    c.L(f"Facturatie {k['name']}: verwerkt in Exact (€ {k['total']:.2f})" + (f', {gesloten} ticket(s) op Complete' if gesloten else '') + '.')
    return {'closed': gesloten, 'errors': fout}


@api('fa.terug')
def fa_terug(c: Ctx, b: dict) -> dict:
    """Een verwerkte factuur terugzetten (bijv. per ongeluk afgevinkt): de regels komen terug in de lijst."""
    _zet_auth(c)
    with _lock:
        st = _stand(True)
        weg = [v for v in st['verwerkt'] if v.get('id') == b.get('id')]
        if not weg:
            raise ApiFout('Niet gevonden in de historie.')
        st['verwerkt'] = [v for v in st['verwerkt'] if v.get('id') != b.get('id')]
        _bewaar(st)
    c.L(f"Facturatie {weg[0].get('name')}: teruggezet in de lijst.")
    return {}


@api('fa.pdf')
def fa_pdf(c: Ctx, b: dict) -> dict:
    from .h_facturatie_pdf import maak_pdf
    from .h_rapport import _openen
    _zet_auth(c)
    d, k = _klant(c, b)
    map_ = Path.home() / 'Downloads'
    if not map_.is_dir():
        map_ = Path.home()
    naam = re.sub(r'[^A-Za-z0-9 _.-]+', '', k['name']).strip().replace(' ', '-')[:60] or 'klant'
    pad = map_ / f'Factuurspecificatie-{naam}-{datetime.now():%Y-%m-%d}.pdf'
    n = 2
    while pad.exists():
        pad = pad.with_name(f'Factuurspecificatie-{naam}-{datetime.now():%Y-%m-%d}-{n}.pdf')
        n += 1
    pad.write_bytes(maak_pdf(k, d['days'], _wie(c)))
    c.L(f'Factuurspecificatie opgeslagen: {pad}')
    _openen(pad)
    return {'path': str(pad)}
