"""Timesheet (startscherm > Timesheet): je eigen Autotask-tijdregels per dag of week als blokken in een schema.

- Tickets, projecttaken en algemene tijd (interne codes, BillingCodes useType 3) naar het schema slepen = tijdregel aanmaken.
- Blokken verschuiven of langer/korter maken = PATCH startDateTime/endDateTime/hoursWorked; omschrijving wijzigen.
- Verwijderen alleen als Autotask het toestaat (via de API aangemaakt en timesheet nog niet ingediend); anders een melding.
Autotask-regels: algemene tijd zonder ticket/taak moet niet-factureerbaar zijn en heeft internalBillingCodeID; wijzigen kan niet
meer als de timesheet is ingediend/goedgekeurd of de regel gefactureerd is. Tijden in UTC naar Autotask, in de interface lokaal.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import _zet_auth

log = logging.getLogger('m365beheer')
_CACHE: dict = {}
VELDEN = ['id', 'ticketID', 'taskID', 'startDateTime', 'endDateTime', 'dateWorked', 'hoursWorked', 'summaryNotes', 'internalBillingCodeID',
          'isNonBillable', 'roleID', 'billingApprovalDateTime', 'resourceID']


def _utc(s: str) -> datetime:
    d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    return (d if d.tzinfo else d.astimezone()).astimezone(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _codes(at) -> list[dict]:
    """Interne codes voor algemene tijd (Regular (Internal) Time), 30 min onthouden."""
    item = _CACHE.get('codes')
    if item and time.time() - item[0] < 1800:
        return item[1]
    r = at.query('BillingCodes', [{'op': 'eq', 'field': 'useType', 'value': 3}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'name'], 300)
    uit = sorted([{'id': x['id'], 'name': x.get('name') or ''} for x in r], key=lambda x: x['name'].lower())
    _CACHE['codes'] = (time.time(), uit)
    return uit


def ophalen(at, ik: dict, van: datetime, tot: datetime) -> list[dict]:
    """Mijn tijdregels in [van, tot) met titels erbij (los te vervangen in de testmodus)."""
    from .h_management import _in
    from .h_servicedesk import _link
    r = at.query('TimeEntries', [{'op': 'eq', 'field': 'resourceID', 'value': ik['id']}, {'op': 'gte', 'field': 'dateWorked', 'value': _iso(van - timedelta(days=1))},
                                 {'op': 'lt', 'field': 'dateWorked', 'value': _iso(tot + timedelta(days=1))}], VELDEN, 2000, 2000)
    tickets = {x['id']: x for x in _in(at, 'Tickets', {x.get('ticketID') for x in r}, ['id', 'ticketNumber', 'title', 'companyID'])}
    taken = {x['id']: x for x in _in(at, 'Tasks', {x.get('taskID') for x in r}, ['id', 'title', 'projectID'])}
    proj = {x['id']: x for x in _in(at, 'Projects', {t.get('projectID') for t in taken.values()}, ['id', 'projectName', 'companyID'])}
    bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {t.get('companyID') for t in tickets.values()} | {p.get('companyID') for p in proj.values()},
                                                              ['id', 'companyName'])}
    codes = {c['id']: c['name'] for c in _codes(at)}
    uit = []
    for x in r:
        if not x.get('startDateTime'):
            # Zonder begintijd (bijv. alleen uren op een dag): om 08:00 lokale tijd neerzetten zodat het zichtbaar is
            d = _utc(x['dateWorked']).astimezone()
            start = d.replace(hour=8, minute=0)
            eind = start + timedelta(hours=float(x.get('hoursWorked') or 0.25))
        else:
            start = _utc(x['startDateTime'])
            eind = _utc(x['endDateTime']) if x.get('endDateTime') else start + timedelta(hours=float(x.get('hoursWorked') or 0.25))
        if not (van <= start.astimezone(timezone.utc) < tot):
            continue
        t, tk = tickets.get(x.get('ticketID')), taken.get(x.get('taskID'))
        p = proj.get((tk or {}).get('projectID'))
        soort = 'ticket' if t else 'taak' if tk else 'algemeen'
        uit.append({'id': x['id'], 'kind': soort, 'start': _iso(start), 'end': _iso(eind), 'hours': float(x.get('hoursWorked') or 0),
                    'notes': x.get('summaryNotes') or '', 'locked': bool(x.get('billingApprovalDateTime')),
                    'refId': x.get('ticketID') or x.get('taskID') or x.get('internalBillingCodeID'),
                    'title': (t or {}).get('title') or (tk or {}).get('title') or codes.get(x.get('internalBillingCodeID'), 'Algemene tijd'),
                    'ref': (t or {}).get('ticketNumber') or ((p or {}).get('projectName') or ''),
                    'company': bedr.get((t or {}).get('companyID') or (p or {}).get('companyID'), ''),
                    'url': _link(at, t['id']) if t else ''})
    return sorted(uit, key=lambda e: e['start'])


@api('ts.periode')
def ts_periode(c: Ctx, b: dict) -> dict:
    """Tijdregels van mij tussen from en to (ISO, lokale dag-grenzen worden door de interface meegegeven)."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    van, tot = _utc(b['from']), _utc(b['to'])
    if (tot - van).days > 8:
        raise ApiFout('Maximaal een week tegelijk.')
    return {'entries': ophalen(at, ik, van, tot), 'me': ik['name']}


@api('ts.bronnen')
def ts_bronnen(c: Ctx, b: dict) -> dict:
    """Wat je naar het schema kunt slepen: je open tickets, tickets waar je recent aan werkte, je projecttaken en de interne codes."""
    from . import h_autotask as A
    from .h_management import _in
    from .h_servicedesk import _link
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    sleutel = ('bronnen', ik['id'])
    item = _CACHE.get(sleutel)
    if item and not b.get('fresh') and time.time() - item[0] < 120:
        return item[1]
    klaar = A._klaar(at, 'Tickets')
    sinds = _iso(datetime.now(timezone.utc) - timedelta(days=14))
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_open = ex.submit(at.query, 'Tickets', [{'op': 'eq', 'field': 'assignedResourceID', 'value': ik['id']}] + [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar],
                           ['id', 'ticketNumber', 'title', 'companyID', 'lastActivityDate'], 200)
        f_recent = ex.submit(at.query, 'TimeEntries', [{'op': 'eq', 'field': 'resourceID', 'value': ik['id']}, {'op': 'gte', 'field': 'dateWorked', 'value': sinds}],
                             ['ticketID', 'taskID'], 500)
        f_taken = ex.submit(at.query, 'Tasks', [{'op': 'eq', 'field': 'assignedResourceID', 'value': ik['id']}] + [{'op': 'noteq', 'field': 'status', 'value': w} for w in A._klaar(at, 'Tasks')],
                            ['id', 'title', 'projectID', 'status'], 200)
        f_codes = ex.submit(_codes, at)
        open_, recent, taken, codes = f_open.result(), f_recent.result(), f_taken.result(), f_codes.result()
    recent_ids = {x.get('ticketID') for x in recent} - {t['id'] for t in open_} - {None}
    recent_t = _in(at, 'Tickets', recent_ids, ['id', 'ticketNumber', 'title', 'companyID', 'lastActivityDate'])
    recent_taak_ids = {x.get('taskID') for x in recent} - {t['id'] for t in taken} - {None}
    taken += _in(at, 'Tasks', recent_taak_ids, ['id', 'title', 'projectID', 'status'])
    proj = {x['id']: x for x in _in(at, 'Projects', {t.get('projectID') for t in taken}, ['id', 'projectName', 'companyID'])}
    bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {t.get('companyID') for t in open_ + recent_t} | {p.get('companyID') for p in proj.values()},
                                                              ['id', 'companyName'])}
    vorm = lambda t, mijn: {'kind': 'ticket', 'id': t['id'], 'ref': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'company': bedr.get(t.get('companyID'), ''),  # noqa: E731
                            'mine': mijn, 'url': _link(at, t['id'])}
    uit = {'tickets': [vorm(t, True) for t in sorted(open_, key=lambda t: str(t.get('lastActivityDate')), reverse=True)]
           + [vorm(t, False) for t in sorted(recent_t, key=lambda t: str(t.get('lastActivityDate')), reverse=True)],
           'tasks': [{'kind': 'taak', 'id': t['id'], 'title': t.get('title') or '', 'ref': (proj.get(t.get('projectID')) or {}).get('projectName') or '',
                      'company': bedr.get((proj.get(t.get('projectID')) or {}).get('companyID'), '')} for t in taken],
           'codes': [{'kind': 'algemeen', 'id': x['id'], 'title': x['name'], 'ref': '', 'company': ''} for x in codes]}
    _CACHE[sleutel] = (time.time(), uit)
    return uit


@api('ts.projecten')
def ts_projecten(c: Ctx, b: dict) -> dict:
    """Open projecten zoeken (naam of nummer), met hun open taken: voor projecttijd op een taak die niet aan jou hangt."""
    from . import h_autotask as A
    from .h_management import _in
    _zet_auth(c)
    q = str(b.get('q') or '').strip()
    at = A._at()
    if b.get('projectId'):
        klaar = A._klaar(at, 'Tasks')
        t = at.query('Tasks', [{'op': 'eq', 'field': 'projectID', 'value': int(b['projectId'])}] + [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar],
                     ['id', 'title', 'projectID'], 300)
        return {'tasks': [{'kind': 'taak', 'id': x['id'], 'title': x.get('title') or '', 'ref': b.get('projectName') or '', 'company': b.get('company') or ''} for x in t]}
    if len(q) < 2:
        return {'projects': []}
    klaar = A._klaar(at, 'Projects')
    p = at.query('Projects', [{'op': 'contains', 'field': 'projectName', 'value': q}] + [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar],
                 ['id', 'projectName', 'projectNumber', 'companyID'], 30)
    bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {x.get('companyID') for x in p}, ['id', 'companyName'])}
    return {'projects': [{'id': x['id'], 'name': x.get('projectName') or '', 'number': x.get('projectNumber') or '', 'company': bedr.get(x.get('companyID'), '')} for x in p]}


def _tijden(b: dict) -> tuple[datetime, datetime, float]:
    start, eind = _utc(b['start']), _utc(b['end'])
    if eind <= start:
        raise ApiFout('De eindtijd moet na de begintijd liggen.')
    uren = round((eind - start).total_seconds() / 3600, 2)
    if uren > 24:
        raise ApiFout('Een blok kan maximaal 24 uur zijn.')
    return start, eind, uren


def _wis(ik_id) -> None:
    for k in list(_CACHE):
        if k != 'codes':
            _CACHE.pop(k, None)


@api('ts.nieuw')
def ts_nieuw(c: Ctx, b: dict) -> dict:
    """Blok in het schema = tijdregel: op een ticket, een projecttaak of algemene tijd (interne code)."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    start, eind, uren = _tijden(b)
    tekst = str(b.get('notes') or '').strip()
    soort = b.get('kind')
    body = {'resourceID': ik['id'], 'roleID': ik['role'], 'startDateTime': _iso(start), 'endDateTime': _iso(eind), 'hoursWorked': uren, 'summaryNotes': tekst[:31000]}
    if soort in ('ticket', 'taak'):
        if len(tekst) < 3:
            raise ApiFout('Schrijf kort wat je hebt gedaan (Autotask vraagt een omschrijving bij ticket- en projecttijd).')
        body['ticketID' if soort == 'ticket' else 'taskID'] = int(b['refId'])
        inst = A._instellingen()
        if inst.get('billingCodeID'):
            body['billingCodeID'] = inst['billingCodeID']
    elif soort == 'algemeen':
        body.update(internalBillingCodeID=int(b['refId']), isNonBillable=True)   # rol = altijd de standaardrol van de medewerker
    else:
        raise ApiFout('Onbekende soort tijd.')
    try:
        r = at.req('POST', 'TimeEntries', body)
    except ApiFout as e:
        # Rol moet soms die van het ticket/de taak zijn
        if soort in ('ticket', 'taak') and 'role' in str(e).lower():
            obj = at.req('GET', f"{'Tickets' if soort == 'ticket' else 'Tasks'}/{int(b['refId'])}").get('item') or {}
            rol = obj.get('assignedResourceRoleID') or obj.get('assignedResourceroleID')
            if not rol:
                raise
            body['roleID'] = rol
            r = at.req('POST', 'TimeEntries', body)
        else:
            raise
    _wis(ik['id'])
    c.L(f"Tijd geboekt: {uren:.2f} uur ({soort}).".replace('.', ',', 1))
    return {'id': (r or {}).get('itemId')}


@api('ts.wijzig')
def ts_wijzig(c: Ctx, b: dict) -> dict:
    """Blok verschoven, langer/korter gemaakt of omschrijving aangepast."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    body: dict = {'id': int(b['id'])}
    if b.get('start') and b.get('end'):
        start, eind, uren = _tijden(b)
        body.update(startDateTime=_iso(start), endDateTime=_iso(eind), hoursWorked=uren)
    if 'notes' in b:
        body['summaryNotes'] = str(b.get('notes') or '').strip()[:31000]
    bestaand = at.req('GET', f"TimeEntries/{int(b['id'])}").get('item') or {}
    if bestaand.get('resourceID') != ik['id']:
        raise ApiFout('Je kunt alleen je eigen tijdregels wijzigen.')
    try:
        at.req('PATCH', 'TimeEntries', body)
    except ApiFout as e:
        raise ApiFout(f'Autotask staat deze wijziging niet toe (is je timesheet al ingediend of goedgekeurd?): {str(e)[:200]}') from None
    _wis(ik['id'])
    return {}


@api('ts.verwijder')
def ts_verwijder(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    bestaand = at.req('GET', f"TimeEntries/{int(b['id'])}").get('item') or {}
    if bestaand.get('resourceID') != ik['id']:
        raise ApiFout('Je kunt alleen je eigen tijdregels verwijderen.')
    try:
        at.req('DELETE', f"TimeEntries/{int(b['id'])}")
    except ApiFout as e:
        raise ApiFout('Autotask staat verwijderen niet toe (alleen regels die via de app zijn gemaakt en nog niet zijn ingediend). '
                      f'Verwijder deze regel in Autotask zelf. ({str(e)[:160]})') from None
    _wis(ik['id'])
    c.L('Tijdregel verwijderd.')
    return {}


@api('ts.ticket')
def ts_ticket(c: Ctx, b: dict) -> dict:
    """Vergeten ticket achteraf: ticket aanmaken (op jouw naam), de tijd als blok in het schema boeken en desgewenst direct
    afronden met oplossing: Complete of Ready to Invoice."""
    from . import h_autotask as A
    _zet_auth(c)
    titel = str(b.get('title') or '').strip()
    if len(titel) < 3 or not b.get('companyId'):
        raise ApiFout('Kies de klant en vul het onderwerp in.')
    tekst = str(b.get('notes') or '').strip()
    if len(tekst) < 3:
        raise ApiFout('Schrijf kort wat je hebt gedaan.')
    start, eind, uren = _tijden(b)
    at = A._at()
    ik = A._ik(at)
    inst = A._instellingen()
    t = A._nieuw_ticket(at, int(b['companyId']), titel[:250], str(b.get('description') or tekst)[:7900], ik, inst,
                        int(b['contactId']) if b.get('contactId') else None)
    body = {'resourceID': ik['id'], 'roleID': ik['role'], 'ticketID': t['id'], 'startDateTime': _iso(start), 'endDateTime': _iso(eind), 'hoursWorked': uren,
            'summaryNotes': tekst[:31000]}
    if inst.get('billingCodeID'):
        body['billingCodeID'] = inst['billingCodeID']
    try:
        at.req('POST', 'TimeEntries', body)
    except ApiFout as e:
        if 'role' not in str(e).lower() or not t.get('assignedResourceroleID'):
            raise ApiFout(f"Ticket {t.get('number')} is aangemaakt, maar de tijd boeken lukte niet: {e}") from None
        body['roleID'] = t['assignedResourceroleID']
        at.req('POST', 'TimeEntries', body)
    afgerond = ''
    if b.get('done'):
        eindst = A.eindstatussen(at, inst)
        factuur = b.get('endStatus') == 'invoice'
        status = eindst['invoice' if factuur else 'complete']
        if status is None:
            raise ApiFout(f"Ticket {t.get('number')} en tijd staan erin, maar de eindstatus bestaat niet in Autotask.")
        oplossing = str(b.get('resolution') or tekst).strip()[:7900]
        at.req('PATCH', 'Tickets', {'id': t['id'], 'status': status, 'resolution': oplossing})
        afgerond = 'invoice' if factuur else 'complete'
    _wis(ik['id'])
    from .h_servicedesk import _CACHE as SDC
    SDC.clear()
    c.L(f"Ticket {t.get('number')} achteraf aangemaakt ({uren:.2f} uur geboekt".replace('.', ',', 1)
        + (', afgerond: Ready to Invoice' if afgerond == 'invoice' else ', afgerond' if afgerond else '') + ').')
    return {'ticket': {'id': t['id'], 'number': t.get('number') or ''}, 'closed': afgerond}


def vergeet() -> None:
    _CACHE.clear()
