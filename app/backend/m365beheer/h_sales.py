"""Sales (startscherm > Sales): verkoopkansen (Autotask Opportunities) invoeren en definitief maken, en daarna een klantproject.

- Invoeren en definitief maken: alleen rechten.SALES_INVOEREN. Inzien: ook de app-beheerder, die van een definitieve kans
  een project maakt (h_projecten.pr_vankans). Zo is de aanlevering van sales aan projecten altijd volledig.
- Definitief = status 'Closed'/'Implemented'/'Won' (op label uit de Autotask-picklist) + closedDate vandaag.
- Verplicht bij aanmaken (Autotask): title, companyID, ownerResourceID, amount, cost, probability, projectedCloseDate, stage,
  status, useQuoteTotals. Omschrijving in 'description'; weigert Autotask dat, dan als CompanyNote met opportunityID.
NIET getest met een echte Autotask (statuswaarden, description-veld).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import _zet_auth
from .rechten import is_beheerder, is_sales, mag_sales_invoeren

log = logging.getLogger('m365beheer')
_CACHE: dict = {}
GEWONNEN = re.compile(r'closed|implemented|won|gewonnen|gesloten|definitief', re.I)
VERLOREN = re.compile(r'lost|verloren', re.I)
ACTIEF = re.compile(r'^\s*(active|actief|open)\s*$', re.I)


def _pl(at, veld: str) -> list[dict]:
    return at.picklists('Opportunities').get(veld, [])


def _waarde(lijst: list[dict], patroon, standaard=None):
    for p in lijst:
        if patroon.search(str(p.get('label') or '')):
            return p['value']
    return standaard


def getal(w):
    """Autotask geeft keuzelijstwaarden als tekst ('2'), maar de status van een kans als getal (2): altijd als getal vergelijken.
    (Hierdoor zag de app een gesloten kans nooit als definitief.)"""
    try:
        return int(w)
    except (TypeError, ValueError):
        return w


def statussen(at) -> dict:
    st = [{**p, 'value': getal(p.get('value'))} for p in _pl(at, 'status')]
    gewonnen = [p for p in st if GEWONNEN.search(str(p.get('label') or '')) and not VERLOREN.search(str(p.get('label') or ''))]
    # Voorkeur: 'Closed' (gewonnen) boven 'Implemented'
    won = next((p['value'] for p in gewonnen if re.search(r'closed|won|gewonnen', str(p.get('label')), re.I)), gewonnen[0]['value'] if gewonnen else None)
    return {'active': _waarde(st, ACTIEF, next((p['value'] for p in st if p.get('default')), st[0]['value'] if st else 1)), 'won': won,
            'wonAll': {p['value'] for p in gewonnen}, 'lost': {p['value'] for p in st if VERLOREN.search(str(p.get('label') or ''))}}


def _eis_invoeren(c: Ctx) -> None:
    """Kansen aanmaken en wijzigen: sales en de app-beheerder (allebei SALES_INZIEN)."""
    if not is_sales(c.staat):
        raise ApiFout('Je mag geen saleskansen aanmaken of wijzigen.')


def _eis_status(c: Ctx) -> None:
    """Definitief maken of op verloren zetten: sales en de app-beheerder (die er daarna een project van maakt)."""
    if not is_sales(c.staat):
        raise ApiFout('Je mag de status van saleskansen niet wijzigen.')


def maak_definitief(at, kid: int) -> None:
    st = statussen(at)
    if st['won'] is None:
        raise ApiFout("Autotask kent geen status voor een gewonnen kans (zoals 'Closed' of 'Implemented').")
    at.req('PATCH', 'Opportunities', {'id': int(kid), 'status': st['won'], 'closedDate': datetime.now().strftime('%Y-%m-%dT00:00:00Z'), 'probability': 100})
    _CACHE.clear()


@api('sa.opties')
def sa_opties(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    return {'stages': _pl(at, 'stage'), 'ratings': _pl(at, 'rating'), 'sources': _pl(at, 'leadSource'), 'categories': _pl(at, 'opportunityCategoryID'),
            'canEdit': is_sales(c.staat), 'canSalesEdit': mag_sales_invoeren(c.staat)}


@api('sa.overzicht')
def sa_overzicht(c: Ctx, b: dict) -> dict:
    """Open kansen en de definitieve kansen van het laatste jaar, met het project dat er al van gemaakt is."""
    from . import h_autotask as A
    from .h_management import _in
    _zet_auth(c)
    item = _CACHE.get('ov')
    if item and not b.get('fresh') and time.time() - item[0] < 60:
        return item[1]
    at = A._at()
    st = statussen(at)
    velden = ['id', 'title', 'companyID', 'contactID', 'ownerResourceID', 'amount', 'cost', 'probability', 'projectedCloseDate', 'stage', 'status',
              'rating', 'leadSource', 'closedDate', 'createDate', 'description', 'monthlyRevenue', 'onetimeRevenue']
    jaar = (datetime.now(timezone.utc) - timedelta(days=365)).strftime('%Y-%m-%dT00:00:00Z')
    open_ = at.query('Opportunities', [{'op': 'eq', 'field': 'status', 'value': st['active']}], velden, 1000) if st['active'] is not None else []
    won = at.query('Opportunities', [{'op': 'in', 'field': 'status', 'value': sorted(st['wonAll'])}, {'op': 'gte', 'field': 'closedDate', 'value': jaar}], velden, 1000) \
        if st['wonAll'] else []
    alle = open_ + won
    projecten = at.query('Projects', [{'op': 'in', 'field': 'opportunityID', 'value': [o['id'] for o in alle]}], ['id', 'projectName', 'opportunityID', 'projectNumber'], 1000) \
        if alle else []
    per_kans = {p['opportunityID']: p for p in projecten}
    bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {o.get('companyID') for o in alle}, ['id', 'companyName'])}
    mensen = {x['id']: f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip() for x in _in(at, 'Resources', {o.get('ownerResourceID') for o in alle}, ['id', 'firstName', 'lastName'])}
    contacten = {x['id']: f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip() for x in _in(at, 'Contacts', {o.get('contactID') for o in alle}, ['id', 'firstName', 'lastName'])}
    lab = lambda veld: {str(p['value']): p['label'] for p in _pl(at, veld)}  # noqa: E731
    stg, sts = lab('stage'), lab('status')
    uit = []
    for o in alle:
        p = per_kans.get(o['id'])
        uit.append({'id': o['id'], 'title': o.get('title') or '', 'company': bedr.get(o.get('companyID'), ''), 'companyId': o.get('companyID'),
                    'contact': contacten.get(o.get('contactID'), ''), 'contactId': o.get('contactID'), 'owner': mensen.get(o.get('ownerResourceID'), ''),
                    'amount': float(o.get('amount') or 0), 'cost': float(o.get('cost') or 0), 'monthly': float(o.get('monthlyRevenue') or 0),
                    'probability': int(o.get('probability') or 0), 'close': str(o.get('projectedCloseDate') or '')[:10], 'closed': str(o.get('closedDate') or '')[:10],
                    'stage': o.get('stage'), 'stageLabel': stg.get(str(o.get('stage')), ''), 'status': sts.get(str(o.get('status')), ''),
                    'final': getal(o.get('status')) in st['wonAll'], 'description': o.get('description') or '', 'created': str(o.get('createDate') or '')[:10],
                    'project': {'id': p['id'], 'name': p.get('projectName') or '', 'number': p.get('projectNumber') or ''} if p else None})
    uit.sort(key=lambda o: (o['final'], o['close'] or '9999'))
    open_l = [o for o in uit if not o['final']]
    res = {'opportunities': uit, 'totals': {'open': len(open_l), 'pipeline': round(sum(o['amount'] for o in open_l), 2),
                                            'weighted': round(sum(o['amount'] * o['probability'] / 100 for o in open_l), 2),
                                            'won': sum(1 for o in uit if o['final']), 'wonAmount': round(sum(o['amount'] for o in uit if o['final']), 2),
                                            'noProject': sum(1 for o in uit if o['final'] and not o['project'])},
           'canEdit': is_sales(c.staat), 'canStatus': is_sales(c.staat), 'canProject': is_beheerder(c.staat), 'at': datetime.now().strftime('%H:%M')}
    _CACHE['ov'] = (time.time(), res)
    return res


@api('sa.opslaan')
def sa_opslaan(c: Ctx, b: dict) -> dict:
    """Nieuwe kans of wijzigen. Bedrag = totaal (eenmalig + maandbedrag x looptijd); kosten optioneel."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis_invoeren(c)
    titel = str(b.get('title') or '').strip()
    if len(titel) < 3 or not b.get('companyId'):
        raise ApiFout('Vul de klant en een korte titel in.')
    at = A._at()
    ik = A._ik(at)
    st = statussen(at)
    stages = _pl(at, 'stage')
    eenmalig, maand, maanden = float(b.get('onetime') or 0), float(b.get('monthly') or 0), int(b.get('months') or 0)
    body = {'title': titel[:128], 'companyID': int(b['companyId']), 'contactID': int(b['contactId']) if b.get('contactId') else None,
            'amount': round(float(b.get('amount') or (eenmalig + maand * max(maanden, 1 if maand else 0))), 2), 'cost': round(float(b.get('cost') or 0), 2),
            'probability': max(0, min(100, int(b.get('probability') or 50))),
            'projectedCloseDate': (str(b.get('close') or '') or (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')) + 'T00:00:00Z',
            'stage': int(b['stage']) if b.get('stage') else next((p['value'] for p in stages if p.get('default')), stages[0]['value'] if stages else 1),
            'rating': int(b['rating']) if b.get('rating') else None, 'leadSource': int(b['source']) if b.get('source') else None,
            'onetimeRevenue': eenmalig or None, 'monthlyRevenue': maand or None, 'totalAmountMonths': maanden or None,
            'description': str(b.get('description') or '').strip()[:7900] or None}
    body = {k: v for k, v in body.items() if v is not None}
    if b.get('id'):
        body['id'] = int(b['id'])
        methode = 'PATCH'
    else:
        body.update(ownerResourceID=ik['id'], status=st['active'], useQuoteTotals=False)
        methode = 'POST'
    try:
        r = at.req(methode, 'Opportunities', body)
    except ApiFout as e:
        if 'description' not in body or 'description' not in str(e).lower():
            raise
        tekst = body.pop('description')
        r = at.req(methode, 'Opportunities', body)
        kid = body.get('id') or (r or {}).get('itemId')
        try:
            at.req('POST', 'CompanyNotes', {'companyID': body.get('companyID'), 'opportunityID': kid, 'title': 'Omschrijving kans', 'description': tekst,
                                            'actionType': 1})
        except ApiFout as e2:
            log.info('Omschrijving kans als notitie niet gelukt: %s', e2)
    _CACHE.clear()
    c.L(f"Saleskans {'gewijzigd' if b.get('id') else 'ingevoerd'}: {titel} (€ {body.get('amount', 0):.2f}).")
    return {'id': body.get('id') or (r or {}).get('itemId')}


@api('sa.definitief')
def sa_definitief(c: Ctx, b: dict) -> dict:
    """Kans gewonnen = definitief: status op Closed/Won en closedDate vandaag. Daarna kan er een project van gemaakt worden."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis_status(c)
    maak_definitief(A._at(), int(b['id']))
    c.L('Saleskans definitief gemaakt (gewonnen).')
    return {}


@api('sa.verloren')
def sa_verloren(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    _eis_status(c)
    at = A._at()
    st = statussen(at)
    if not st['lost']:
        raise ApiFout("Autotask kent geen status 'Lost'.")
    for kid in b.get('ids') or [b['id']]:
        at.req('PATCH', 'Opportunities', {'id': int(kid), 'status': min(st['lost'])})
    _CACHE.clear()
    c.L('Saleskans(en) op verloren gezet.')
    return {}


@api('sa.status')
def sa_status(c: Ctx, b: dict) -> dict:
    """Meerdere kansen tegelijk: definitief, verloren of verwijderen. Autotask kan kansen niet verwijderen via de API:
    'verwijderen' zet de status op Inactive (de kans verdwijnt uit het overzicht)."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis_status(c)
    at = A._at()
    st = statussen(at)
    wat = b.get('action')
    ids = [int(x) for x in b.get('ids') or []]
    if not ids:
        raise ApiFout('Kies minstens één kans.')
    if wat == 'final':
        for kid in ids:
            maak_definitief(at, kid)
    else:
        if wat == 'delete':
            waarde = _waarde(_pl(at, 'status'), re.compile(r'inactive|inactief|niet actief', re.I))
            if waarde is None:
                raise ApiFout("Autotask kent geen status 'Inactive' om de kans te verwijderen.")
        elif wat == 'lost':
            if not st['lost']:
                raise ApiFout("Autotask kent geen status 'Lost'.")
            waarde = min(st['lost'])
        else:
            raise ApiFout('Onbekende actie.')
        fouten = []
        for kid in ids:
            try:
                at.req('PATCH', 'Opportunities', {'id': kid, 'status': waarde})
            except ApiFout as e:
                fouten.append(str(e)[:150])
        if fouten:
            _CACHE.clear()
            raise ApiFout('; '.join(fouten[:3]))
    _CACHE.clear()
    c.L(f"{len(ids)} saleskans(en): {'definitief' if wat == 'final' else 'verloren' if wat == 'lost' else 'verwijderd (inactief)'}.")
    return {'ok': len(ids)}


# ---------------------------------------------------------------- notities bij een kans (CompanyNotes met opportunityID)
VERWIJDERD = '(verwijderd) '


def _kans(at, kid: int) -> dict:
    k = at.req('GET', f'Opportunities/{int(kid)}').get('item') or {}
    if not k:
        raise ApiFout('Saleskans niet gevonden.')
    return k


@api('sa.notities')
def sa_notities(c: Ctx, b: dict) -> dict:
    """Notities en bijlagen van een kans."""
    from . import h_autotask as A
    from .h_management import _in
    _zet_auth(c)
    at = A._at()
    kid = int(b['id'])
    n = at.query('CompanyNotes', [{'op': 'eq', 'field': 'opportunityID', 'value': kid}], ['id', 'name', 'note', 'createDateTime', 'lastModifiedDate', 'assignedResourceID'], 300)
    try:
        bij = at.query('OpportunityAttachments', [{'op': 'eq', 'field': 'opportunityID', 'value': kid}], ['id', 'title', 'fullPath', 'attachDate', 'contentType'], 200)
    except ApiFout as e:
        log.info('Bijlagen kans niet opgehaald: %s', e)
        bij = []
    namen = {x['id']: f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip() for x in _in(at, 'Resources', {x.get('assignedResourceID') for x in n}, ['id', 'firstName', 'lastName'])}
    return {'notes': sorted([{'id': x['id'], 'title': x.get('name') or '', 'text': x.get('note') or '', 'by': namen.get(x.get('assignedResourceID'), ''),
                              'at': str(x.get('lastModifiedDate') or x.get('createDateTime') or '')[:16].replace('T', ' ')}
                             for x in n if not str(x.get('name') or '').startswith(VERWIJDERD)], key=lambda x: x['at'], reverse=True),
            'files': sorted([{'id': x['id'], 'name': x.get('fullPath') or x.get('title') or 'bestand', 'title': x.get('title') or '', 'at': str(x.get('attachDate') or '')[:16].replace('T', ' ')}
                             for x in bij], key=lambda x: x['at'], reverse=True)}


@api('sa.notitie')
def sa_notitie(c: Ctx, b: dict) -> dict:
    """Notitie toevoegen, bewerken of verwijderen. Autotask kan CompanyNotes niet verwijderen via de API: 'verwijderen'
    maakt de notitie leeg met '(verwijderd)' in de titel, en de app laat hem niet meer zien."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis_status(c)
    at = A._at()
    if b.get('remove'):
        at.req('PATCH', 'CompanyNotes', {'id': int(b['noteId']), 'name': (VERWIJDERD + str(b.get('title') or ''))[:128], 'note': ''})
        c.L('Notitie bij saleskans verwijderd.')
        return {}
    titel, tekst = str(b.get('title') or 'Notitie').strip()[:128], str(b.get('text') or '').strip()[:32000]
    if not tekst:
        raise ApiFout('Schrijf de notitie.')
    if b.get('noteId'):
        at.req('PATCH', 'CompanyNotes', {'id': int(b['noteId']), 'name': titel, 'note': tekst})
        c.L('Notitie bij saleskans bewerkt.')
        return {}
    kans = _kans(at, int(b['id']))
    ik = A._ik(at)
    soorten = at.picklists('CompanyNotes').get('actionType', [])
    soort = next((p['value'] for p in soorten if re.search(r'general|algemeen|note|notitie', str(p.get('label') or ''), re.I)), soorten[0]['value'] if soorten else 1)
    nu = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    at.req('POST', 'CompanyNotes', {'companyID': kans['companyID'], 'opportunityID': kans['id'], 'actionType': soort, 'assignedResourceID': ik['id'],
                                    'startDateTime': nu, 'endDateTime': nu, 'name': titel, 'note': tekst})
    c.L('Notitie bij saleskans toegevoegd.')
    return {}


# ---------------------------------------------------------------- bijlagen (offerte e.d.): OpportunityAttachments
MAX_BIJLAGE = 6 * 1024 * 1024   # Autotask-API: 6 à 7 MB per bestand


@api('sa.bijlage')
def sa_bijlage(c: Ctx, b: dict) -> dict:
    """Bijlage toevoegen (base64 uit de interface), openen (downloaden naar Downloads) of verwijderen."""
    import base64
    from pathlib import Path
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    kid = int(b['id'])
    if b.get('open'):
        x = at.req('GET', f"Opportunities/{kid}/Attachments/{int(b['fileId'])}")
        item = (x.get('items') or [x.get('item') or {}])[0] if isinstance(x, dict) else {}
        data = item.get('data')
        if not data:
            raise ApiFout('Autotask gaf de inhoud van de bijlage niet terug.')
        naam = re.sub(r'[\\/:*?"<>|]+', '_', str(item.get('fullPath') or item.get('title') or 'bijlage'))[:120]
        map_ = Path.home() / 'Downloads'
        if not map_.is_dir():
            map_ = Path.home()
        pad = map_ / naam
        n = 2
        while pad.exists():
            pad = pad.with_name(f'{pad.stem}-{n}{pad.suffix}')
            n += 1
        pad.write_bytes(base64.b64decode(data))
        from .h_rapport import _openen
        _openen(pad)
        return {'path': str(pad)}
    _eis_status(c)
    if b.get('remove'):
        at.req('DELETE', f"Opportunities/{kid}/Attachments/{int(b['fileId'])}")
        c.L('Bijlage bij saleskans verwijderd.')
        return {}
    naam = re.sub(r'[\\/:*?"<>|]+', '_', str(b.get('name') or 'bijlage'))[:240]
    data = str(b.get('data') or '')
    if not data:
        raise ApiFout('Geen bestand ontvangen.')
    if len(data) * 3 // 4 > MAX_BIJLAGE:
        raise ApiFout('Het bestand is te groot: Autotask accepteert via de API bestanden tot ongeveer 6 MB.')
    body = {'attachmentType': 'FILE_ATTACHMENT', 'title': (str(b.get('title') or '') or naam)[:255], 'fullPath': naam, 'data': data, 'publish': 1}
    try:
        at.req('POST', f'Opportunities/{kid}/Attachments', body)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        at.req('POST', 'OpportunityAttachments', {**body, 'parentID': kid})
    c.L(f'Bijlage {naam} toegevoegd aan saleskans.')
    return {}


# ---------------------------------------------------------------- nieuwe klant vanuit een kans
@api('sa.bedrijf.nieuw')
def sa_bedrijf_nieuw(c: Ctx, b: dict) -> dict:
    """Nieuw bedrijf (altijd type Customer, geen lead/prospect) met primaire contactpersoon, direct te kiezen bij de kans.
    Het project komt daardoor meteen op de nieuwe klant met de juiste contactpersoon."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis_invoeren(c)
    naam = str(b.get('name') or '').strip()
    if len(naam) < 2:
        raise ApiFout('Vul de bedrijfsnaam in.')
    if not str(b.get('phone') or '').strip():
        raise ApiFout('Vul het telefoonnummer van het bedrijf in (verplicht in Autotask).')
    vn, an = str(b.get('firstName') or '').strip(), str(b.get('lastName') or '').strip()
    if not vn or not an:
        raise ApiFout('Vul voor- en achternaam van de contactpersoon in.')
    at = A._at()
    ik = A._ik(at)
    bestaand = at.query('Companies', [{'op': 'eq', 'field': 'companyName', 'value': naam}], ['id', 'companyName'], 5)
    if bestaand:
        raise ApiFout(f"Er bestaat al een bedrijf '{bestaand[0].get('companyName')}' in Autotask. Zoek het op bij Klant.")
    soorten = at.picklists('Companies').get('companyType', [])
    klant = next((p['value'] for p in soorten if re.fullmatch(r'\s*(customer|klant)\s*', str(p.get('label') or ''), re.I)), None)
    if klant is None:
        raise ApiFout("Autotask kent geen bedrijfstype 'Customer'.")
    body = {'companyName': naam[:100], 'companyType': klant, 'ownerResourceID': ik['id'], 'phone': str(b['phone']).strip()[:25],
            'address1': str(b.get('address') or '').strip()[:150] or None, 'postalCode': str(b.get('postalCode') or '').strip()[:30] or None,
            'city': str(b.get('city') or '').strip()[:50] or None, 'webAddress': str(b.get('web') or '').strip()[:255] or None}
    land = next((p['value'] for p in at.picklists('Companies').get('countryID', []) if re.search(r'netherlands|nederland', str(p.get('label') or ''), re.I)), None)
    if land is not None:
        body['countryID'] = land
    r = at.req('POST', 'Companies', {k: v for k, v in body.items() if v is not None})
    cid = (r or {}).get('itemId')
    if not cid:
        raise ApiFout('Autotask gaf geen bedrijfsnummer terug.')
    contact = {'companyID': cid, 'firstName': vn[:20], 'lastName': an[:20], 'isActive': 1, 'primaryContact': True,
               'emailAddress': str(b.get('email') or '').strip()[:254] or None, 'phone': str(b.get('contactPhone') or '').strip()[:25] or None,
               'title': str(b.get('title') or '').strip()[:50] or None}
    contact = {k: v for k, v in contact.items() if v is not None}
    try:
        rc = at.req('POST', f'Companies/{cid}/Contacts', contact)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        rc = at.req('POST', 'Contacts', contact)
    A.lijst_wissen(cid)
    c.L(f'Nieuwe klant {naam} aangemaakt in Autotask met primaire contactpersoon {vn} {an}.')
    return {'company': {'id': cid, 'name': naam}, 'contact': {'id': (rc or {}).get('itemId'), 'name': f'{vn} {an}'}}


def vergeet() -> None:
    _CACHE.clear()
