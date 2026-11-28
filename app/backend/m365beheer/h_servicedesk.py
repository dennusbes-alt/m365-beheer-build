"""Servicedesk (startscherm > Servicedesk): snel een ticket maken, je eigen open tickets met oplossingen uit IT Glue,
en voor de eerste lijn: tickets van de tweede lijn die met bestaande kennis zelf op te pakken zijn.

- Snel ticket: klant, contactpersoon (kiezen, aanmaken of geen), onderwerp, beschrijving. Het ticket staat op jouw naam
  en er wordt direct een kwartier geboekt (ticket aanmaken = altijd 15 minuten).
- Mijn tickets: open tickets op jouw naam, met per ticket de best passende kennisdocumenten uit IT Glue.
- Eerste lijn: open tickets van de tweede lijn (instelbaar, alleen de app-beheerder) en tickets zonder behandelaar
  waarvoor IT Glue een passende oplossing heeft.
Alleen lezen uit Autotask, behalve het ticket en de tijdregel die je zelf aanmaakt. Niets opslaan.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .clients import ApiFout, achtergrond_fn
from .context import Ctx, api
from .h_backup import _zet_auth
from .rechten import eis_beheerder, is_beheerder

log = logging.getLogger('m365beheer')

_TV = ['id', 'ticketNumber', 'title', 'description', 'status', 'priority', 'companyID', 'contactID', 'assignedResourceID',
       'createDate', 'lastActivityDate', 'dueDateTime', 'queueID']
_CACHE: dict = {}
VERS = 60


def _tijd(v):
    try:
        d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _link(at, tid) -> str:
    web = getattr(at, 'web', '')
    return f'{web}/Mvc/ServiceDesk/TicketDetail.mvc?ticketId={tid}' if web else ''


def _tickets(at, filters: list, max_: int = 500) -> list[dict]:
    """Open tickets (status niet afgerond) met namen erbij."""
    from . import h_autotask as A
    inst = A._instellingen()
    klaar = A._klaar(at, 'Tickets') | ({inst['statusKlaar']} if inst.get('statusKlaar') else set())
    # Statussen voor de administratie (bijv. 'Ready to Invoice', 'Te factureren'): daar heeft de servicedesk niets meer mee te maken
    klaar |= {p['value'] for p in at.picklists('Tickets').get('status', []) if re.search(r'invoic|factur|billing|bill\b', str(p.get('label') or ''), re.I)}
    r = at.query('Tickets', filters + [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar], _TV, max_, max_)
    from .h_management import _in
    bedrijven = {b['id']: b.get('companyName') or '' for b in _in(at, 'Companies', {t.get('companyID') for t in r}, ['id', 'companyName'])}
    mensen = {m['id']: f"{m.get('firstName') or ''} {m.get('lastName') or ''}".strip()
              for m in _in(at, 'Resources', {t.get('assignedResourceID') for t in r}, ['id', 'firstName', 'lastName'])}
    pl = at.picklists('Tickets')
    lab = lambda veld: {str(p['value']): p['label'] for p in pl.get(veld, [])}  # noqa: E731
    st, pr, qu = lab('status'), lab('priority'), lab('queueID')
    nu = datetime.now(timezone.utc)
    from .h_sdniveau import langlopend
    lang = langlopend()
    uit = []
    for t in r:
        c = _tijd(t.get('createDate'))
        uit.append({'longRunning': str(t['id']) in lang, 'queueId': t.get('queueID'), 'queue': qu.get(str(t.get('queueID')), ''), 'statusId': t.get('status'), 'priorityId': t.get('priority'),
                    'isNew': bool(re.fullmatch(r'\s*(new|nieuw)\s*', st.get(str(t.get('status')), ''), re.I)), 'unassigned': not t.get('assignedResourceID'),
                    'hours': round((nu - c).total_seconds() / 3600, 1) if c else None,
                    'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'description': re.sub(r'\n\s*\n+', '\n', (t.get('description') or '').strip())[:1500],   # lege regels (mailhandtekeningen) eruit
                    'company': bedrijven.get(t.get('companyID'), ''), 'companyId': t.get('companyID'), 'status': st.get(str(t.get('status')), ''),
                    'priority': pr.get(str(t.get('priority')), ''), 'assigned': mensen.get(t.get('assignedResourceID'), ''),
                    'assignedId': t.get('assignedResourceID'), 'age': (nu - c).days if c else None,
                    'created': c.astimezone().strftime('%d-%m-%Y') if c else '', 'due': (_tijd(t.get('dueDateTime')) or nu).astimezone().strftime('%d-%m-%Y')
                    if t.get('dueDateTime') else '', 'overdue': bool(t.get('dueDateTime') and _tijd(t['dueDateTime']) < nu) and str(t['id']) not in lang,
                    'url': _link(at, t['id'])})
    uit.sort(key=lambda x: (not x['overdue'], -(x['age'] or 0)))
    return uit


def _met_kennis(tickets: list[dict], n: int = 3) -> list[dict]:
    from .h_itglue import _sleutel, index_achtergrond, zoeken
    if _sleutel() is None:
        return tickets
    if not index_achtergrond():   # IT Glue-kennis wordt nog geladen: tickets nu al tonen, suggesties bij de volgende keer
        for t in tickets:
            t['knowledgeLoading'] = True
        return tickets
    for t in tickets:
        t['knowledge'] = zoeken(f"{t['title']} {t['title']} {t['description']}", t['company'], n, onderwerp=t['title'])
    return tickets


def _opties(c: Ctx) -> dict:
    from . import h_autotask as A
    from .h_itglue import _sleutel
    gekoppeld = A._sleutel() is not None
    from .h_advies import beschikbaar
    uit = {'configured': gekoppeld, 'admin': is_beheerder(c.staat), 'itglue': _sleutel() is not None, 'ai': beschikbaar(), 'me': None, 'error': ''}
    if not gekoppeld:
        return uit
    from .h_sdniveau import rol_info
    uit['rol'] = rol_info(c)
    try:
        ik = A._ik(A._at())
        uit['me'] = {'id': ik['id'], 'name': ik['name']}
    except ApiFout as e:
        uit['error'] = str(e)
    inst = A._instellingen()
    uit['secondLine'] = inst.get('tweedeLijn') or []
    gezien: dict = {}
    for v in A._klanten().values():
        if v.get('companyId') is not None:
            gezien.setdefault(int(v['companyId']), {'id': int(v['companyId']), 'name': v.get('name') or v.get('tenant') or f"Bedrijf {v['companyId']}"})
    uit['companies'] = sorted(gezien.values(), key=lambda x: x['name'].lower())
    return uit


@api('sd.opties')
def sd_opties(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    return _opties(c)


@api('sd.bedrijven')
def sd_bedrijven(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    q = str(b.get('q') or '').strip()
    if len(q) < 2:
        return {'companies': []}
    r = A._at().query('Companies', [{'op': 'contains', 'field': 'companyName', 'value': q}, {'op': 'eq', 'field': 'isActive', 'value': True}],
                      ['id', 'companyName'], 30)
    return {'companies': sorted([{'id': x['id'], 'name': x.get('companyName') or ''} for x in r], key=lambda x: x['name'].lower())}


@api('sd.zoek')
def sd_zoek(c: Ctx, b: dict) -> dict:
    """Zoekbalk bovenin: tickets op nummer of onderwerp (ook afgeronde) en Autotask-bedrijven, max. 8 per soort."""
    from . import h_autotask as A
    _zet_auth(c)
    q = str(b.get('q') or '').strip()
    if len(q) < 3 or A._sleutel() is None:
        return {'tickets': [], 'companies': []}
    at = A._at()
    nummer = re.fullmatch(r'[tT]?\d{8}\.\d{1,4}', q)
    flt = ([{'op': 'eq', 'field': 'ticketNumber', 'value': q.upper() if q[0] in 'tT' else 'T' + q}] if nummer
           else [{'op': 'contains', 'field': 'title', 'value': q}])

    def tickets():
        r = at.query('Tickets', flt, ['id', 'ticketNumber', 'title', 'status', 'companyID', 'createDate'], 8, 8)
        from .h_management import _in
        bedrijven = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {t.get('companyID') for t in r}, ['id', 'companyName'])}
        st = {str(p['value']): p['label'] for p in at.picklists('Tickets').get('status', [])}
        r.sort(key=lambda t: str(t.get('createDate') or ''), reverse=True)
        return [{'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'status': st.get(str(t.get('status')), ''),
                 'company': bedrijven.get(t.get('companyID'), ''), 'url': _link(at, t['id'])} for t in r]

    def bedrijven():
        if nummer:
            return []
        r = at.query('Companies', [{'op': 'contains', 'field': 'companyName', 'value': q}, {'op': 'eq', 'field': 'isActive', 'value': True}],
                     ['id', 'companyName'], 8)
        return [{'id': x['id'], 'name': x.get('companyName') or ''} for x in r]
    with ThreadPoolExecutor(max_workers=2) as ex:
        ft, fb = ex.submit(tickets), ex.submit(bedrijven)
        uit = {'tickets': [], 'companies': []}
        for k, f in (('tickets', ft), ('companies', fb)):
            try:
                uit[k] = f.result()
            except ApiFout as e:
                log.info('Zoeken in Autotask (%s): %s', k, e)
    return uit


@api('sd.ticket')
def sd_ticket(c: Ctx, b: dict) -> dict:
    """Snel ticket: aanmaken op jouw naam en direct een kwartier boeken."""
    from . import h_autotask as A
    _zet_auth(c)
    from .h_autotask import _heeft_bedrijf
    company = int(b['companyId']) if _heeft_bedrijf(b) else None
    titel, omschrijving = str(b.get('title') or '').strip(), str(b.get('description') or '').strip()
    if company is None:
        raise ApiFout('Kies de klant.')
    if not titel:
        raise ApiFout('Vul het onderwerp in.')
    at = A._at()
    ik, inst = A._ik(at), A._instellingen()
    t = A._nieuw_ticket(at, company, titel[:250], omschrijving or titel, ik, inst, int(b['contactId']) if b.get('contactId') else None)
    geboekt = True
    try:
        A._tijdregel(at, {'id': t['id'], 'assignedResourceroleID': t.get('assignedResourceroleID')}, ik, 15,
                     f'Ticket aangemaakt en de vraag vastgelegd: {titel}'[:500], inst)
    except ApiFout as e:
        geboekt = False
        log.info('Kwartier boeken bij nieuw ticket: %s', e)
        c.L(f'Let op: het kwartier kon niet worden geboekt ({e}).')
    _CACHE.pop(('mijn', ik['id']), None)
    c.L(f"Ticket {t['number']} aangemaakt bij {b.get('companyName') or 'de klant'}: {titel}" + (' (15 minuten geboekt).' if geboekt else '.'))
    return {'ticket': {**t, 'url': _link(at, t['id'])}, 'booked': geboekt}


@api('sd.mijn')
def sd_mijn(c: Ctx, b: dict) -> dict:
    """Open tickets op jouw naam, met oplossingen uit IT Glue."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    s = ('mijn', ik['id'])
    item = _CACHE.get(s)
    if item and not b.get('fresh') and time.time() - item[0] < VERS:
        return item[1]
    begin = time.time()
    lijst = _met_kennis(_tickets(at, [{'op': 'eq', 'field': 'assignedResourceID', 'value': ik['id']}]))
    uit = {'tickets': lijst, 'me': ik['name'], 'at': datetime.now().strftime('%H:%M')}
    _CACHE[s] = (time.time(), uit)
    log.info('Servicedesk mijn tickets: %d in %.1f s', len(lijst), time.time() - begin)
    return uit


@api('sd.eerstelijn')
def sd_eerstelijn(c: Ctx, b: dict) -> dict:
    """Tickets van de tweede lijn (en zonder behandelaar) waarvoor IT Glue een oplossing heeft: de eerste lijn kan ze oppakken."""
    from . import h_autotask as A
    from .h_itglue import _sleutel
    _zet_auth(c)
    tweede = [int(x) for x in A._instellingen().get('tweedeLijn') or []]
    if not tweede:
        return {'needSetup': True, 'tickets': [], 'itglue': _sleutel() is not None}
    s = ('eerste', tuple(tweede))
    item = _CACHE.get(s)
    if item and not b.get('fresh') and time.time() - item[0] < VERS * 3:
        return _met_triage(item[1])
    at = A._at()
    with ThreadPoolExecutor(max_workers=2) as ex:
        a = ex.submit(achtergrond_fn(_tickets), at, [{'op': 'in', 'field': 'assignedResourceID', 'value': tweede}])
        z = ex.submit(achtergrond_fn(_tickets), at, [{'op': 'notExist', 'field': 'assignedResourceID'}], 200)
        lijst = a.result()
        try:
            lijst += [dict(t, unassigned=True) for t in z.result()]
        except ApiFout as e:
            log.info('Tickets zonder behandelaar: %s', e)
    lijst = _met_kennis(lijst)
    uit = {'tickets': lijst, 'checked': len(lijst), 'itglue': _sleutel() is not None, 'at': datetime.now().strftime('%H:%M')}
    _CACHE[s] = (time.time(), uit)
    return _met_triage(uit)


_TRIAGE: dict = {}


def _met_triage(uit: dict) -> dict:
    """AI-beoordeling 'kan de eerste lijn dit?' op de achtergrond; het scherm vraagt na een paar seconden opnieuw."""
    from .h_advies import beschikbaar, triage
    lijst = uit['tickets']
    if not lijst or not beschikbaar():
        return {**uit, 'ai': False, 'tickets': _sorteer([t for t in lijst if t.get('knowledge')])}
    s = tuple(sorted(t['id'] for t in lijst))
    job = _TRIAGE.get(s)
    if job is None or (job.done() and job.exception() is not None and time.time() - getattr(job, 't', 0) > 120):
        from .clients import ACHTER_POOL
        job = _TRIAGE[s] = ACHTER_POOL.submit(achtergrond_fn(triage), lijst)
        job.t = time.time()
    if not job.done():
        return {**uit, 'ai': True, 'triageBusy': True, 'tickets': _sorteer([t for t in lijst if t.get('knowledge')])}
    try:
        oordeel = job.result()
    except Exception as e:  # noqa: BLE001
        return {**uit, 'ai': True, 'triageError': str(e)[:200], 'tickets': _sorteer([t for t in lijst if t.get('knowledge')])}
    met = [{**t, 'triage': oordeel.get(t['id'])} for t in lijst]
    return {**uit, 'ai': True, 'tickets': _sorteer([t for t in met if t.get('knowledge') or (t.get('triage') or {}).get('eersteLijn')])}


def _sorteer(lijst: list[dict]) -> list[dict]:
    return sorted(lijst, key=lambda t: (-(bool((t.get('triage') or {}).get('eersteLijn')) + bool(t.get('knowledge'))),
                                        -max([k['score'] for k in t.get('knowledge') or []] or [0])))


# ---------------------------------------------------------------- acties op een ticket (tijd boeken, notitie, status)
def _ticket(at, tid: int) -> dict:
    t = at.req('GET', f'Tickets/{int(tid)}').get('item') or {}
    if not t:
        raise ApiFout('Ticket niet gevonden.')
    return t


@api('sd.statussen')
def sd_statussen(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    klaar = A._klaar(at, 'Tickets')
    pl = at.picklists('Tickets')
    return {'statuses': [{'value': p['value'], 'label': p['label'], 'done': p['value'] in klaar} for p in pl.get('status', [])],
            'priorities': [{'value': p['value'], 'label': p['label']} for p in pl.get('priority', [])], 'end': A.eindstatussen(at)}


@api('sd.afsluiten')
def sd_afsluiten(c: Ctx, b: dict) -> dict:
    """Meerdere tickets in één keer afronden. Per ticket: oplossing (in het ticket), tijd op jouw naam (met de oplossing als
    omschrijving) en de eindstatus: 'complete' (incident) of 'invoice' (Ready to Invoice: licentiewijziging, voor de factuur)."""
    from . import h_autotask as A
    _zet_auth(c)
    items = [x for x in (b.get('items') or []) if isinstance(x, dict)]
    if not items:
        raise ApiFout('Kies minstens één ticket.')
    for x in items:
        if len(str(x.get('text') or '').strip()) < 5:
            raise ApiFout('Vul bij elk ticket de oplossing in.')
        if not 0 < int(x.get('minutes') or 0) <= 600:
            raise ApiFout('Vul bij elk ticket de tijd in (1 tot 600 minuten).')
        if x.get('end') not in ('complete', 'invoice'):
            raise ApiFout('Kies bij elk ticket Complete of Ready to Invoice.')
    at = A._at()
    ik, inst = A._ik(at), A._instellingen()
    eind = A.eindstatussen(at, inst)
    for soort in {x['end'] for x in items}:
        if eind.get(soort) is None:
            raise ApiFout("De status 'Ready to Invoice' bestaat niet in Autotask." if soort == 'invoice' else 'Er is geen afgeronde status gevonden in Autotask.')

    def een(x):
        try:
            t = _ticket(at, x['id'])
            tekst = str(x['text']).strip()
            A._tijdregel(at, {'id': t['id'], 'assignedResourceroleID': t.get('assignedResourceRoleID') or t.get('assignedResourceroleID')},
                         ik, int(x['minutes']), tekst, inst)
            at.req('PATCH', 'Tickets', {'id': t['id'], 'status': eind[x['end']], 'resolution': tekst[:7900]})
            return {'id': x['id'], 'number': t.get('ticketNumber') or '', 'ok': True, 'end': x['end']}
        except ApiFout as e:
            return {'id': x['id'], 'ok': False, 'error': str(e)[:300]}
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(een, items))
    _CACHE.clear()
    goed = [r for r in res if r['ok']]
    if goed:
        n_inv = sum(1 for r in goed if r['end'] == 'invoice')
        c.L(f"{len(goed)} ticket(s) afgerond ({len(goed) - n_inv} Complete, {n_inv} Ready to Invoice), met oplossing en tijd: "
            + ', '.join(r['number'] for r in goed if r['number']) + '.')
    return {'results': res, 'ok': len(goed), 'failed': len(res) - len(goed)}


@api('sd.tijd')
def sd_tijd(c: Ctx, b: dict) -> dict:
    """Tijd boeken op een ticket (op jouw naam), met omschrijving; optioneel ook als notitie en/of een nieuwe status."""
    from . import h_autotask as A
    _zet_auth(c)
    minuten, tekst = int(b.get('minutes') or 0), str(b.get('text') or '').strip()
    if minuten <= 0 or minuten > 600:
        raise ApiFout('Vul de tijd in minuten in (1 tot 600).')
    if len(tekst) < 5:
        raise ApiFout('Schrijf kort wat je hebt gedaan.')
    at = A._at()
    ik, inst = A._ik(at), A._instellingen()
    t = _ticket(at, b['id'])
    A._tijdregel(at, {'id': t['id'], 'assignedResourceroleID': t.get('assignedResourceRoleID') or t.get('assignedResourceroleID')}, ik, minuten, tekst, inst)
    gedaan = [f'{minuten} minuten geboekt']
    if b.get('note'):
        A._notitie(at, t['id'], f"Werkzaamheden {ik['name']}", tekst, inst)
        gedaan.append('notitie toegevoegd')
    if b.get('status') not in (None, '', t.get('status')):
        at.req('PATCH', 'Tickets', {'id': t['id'], 'status': int(b['status'])})
        gedaan.append('status gewijzigd')
    _CACHE.clear()
    c.L(f"Ticket {t.get('ticketNumber')}: {', '.join(gedaan)}.")
    return {'done': gedaan}


@api('sd.notitie')
def sd_notitie(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    tekst = str(b.get('text') or '').strip()
    if not tekst:
        raise ApiFout('Schrijf de notitie.')
    at = A._at()
    t = _ticket(at, b['id'])
    A._notitie(at, t['id'], str(b.get('title') or 'Notitie')[:250], tekst, A._instellingen())
    c.L(f"Notitie toegevoegd aan ticket {t.get('ticketNumber')}.")
    return {}


@api('sd.status')
def sd_status(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    t = _ticket(at, b['id'])
    at.req('PATCH', 'Tickets', {'id': t['id'], 'status': int(b['status'])})
    _CACHE.clear()
    c.L(f"Status van ticket {t.get('ticketNumber')} gewijzigd.")
    return {}


@api('sd.tweedelijn.set')
def sd_tweedelijn_set(c: Ctx, b: dict) -> dict:
    """Wie hoort bij de tweede lijn (Autotask-resources). Alleen de app-beheerder."""
    import json
    from . import h_autotask as A
    from .h_backup import GEDEELD
    eis_beheerder(c)
    _zet_auth(c)
    inst = A._instellingen()
    inst['tweedeLijn'] = [int(x) for x in b.get('ids') or []]
    GEDEELD.schrijf_raw('autotask-instellingen', json.dumps({k: inst.get(k) for k in A.STANDAARD_INSTELLINGEN}))
    _CACHE.clear()
    c.L(f"Tweede lijn ingesteld ({len(inst['tweedeLijn'])} medewerker(s)).")
    return {}


@api('sd.resources')
def sd_resources(c: Ctx, b: dict) -> dict:
    """Actieve Autotask-medewerkers om de tweede lijn uit te kiezen (alleen de app-beheerder)."""
    from .context import API
    eis_beheerder(c)
    return API['at.medewerkers'](c, b)
