"""Service calls vanuit een ticket, met de afspraak in de Outlook-agenda van de juiste collega ('sc.', Justdata-login).

- Autotask: POST ServiceCalls (companyID, startDateTime, endDateTime, description; verplicht volgens de docs), daarna het ticket
  eraan (ServiceCalls/{id}/Tickets, terugval ServiceCallTickets) en de medewerker (ServiceCallTickets/{id}/Resources, terugval
  ServiceCallTicketResources). Ligt de afspraak in de toekomst, dan gaat het ticket op 'Planned'/'Gepland' (label uit de keuzelijst).
- Agenda: Graph met een app-token (client credentials) van de eigen app-registratie in de Justdata-tenant: POST /users/{mail}/events.
  Recht Calendars.ReadWrite (toepassing) en het clientgeheim maakt opzetten_app.py (alleen met akkoord); het geheim staat gedeeld
  in de verborgen lijst ('agenda-app'), nooit lokaal of in het logboek.
- Wie in welke agenda: standaard het e-mailadres van de Autotask-resource; per resource + rol in te stellen (app-beheerder,
  'agenda-koppeling'), bijv. een gedeelde servicedesk-resource met een rol per collega. Geen namen of adressen in de code.
- Afsluiten: gaat een ticket via de app op een eindstatus (Complete of Ready to Invoice), dan worden de open service calls van dat
  ticket ook afgerond (isComplete = 1) via de haak in h_autotask (NA_STATUS).
NIET getest met een echte Autotask/Exchange (child-URL's, isComplete als 1, status Planned, client-credentials met deze app).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import eis_beheerder, is_beheerder

log = logging.getLogger('m365beheer')
_CACHE: dict = {}
_TOKEN: dict = {}
_lock = threading.Lock()
_S = requests.Session()
GEPLAND = re.compile(r'planned|gepland|ingepland|scheduled', re.I)


# ---------------------------------------------------------------- tijd
def _utc(lokaal: str) -> datetime:
    """'2026-12-01T09:00' (tijd op deze computer, Nederland) -> UTC."""
    d = datetime.fromisoformat(str(lokaal)[:16])
    return (d.astimezone() if d.tzinfo is None else d).astimezone(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _lokaal(s) -> str:
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%dT%H:%M')
    except ValueError:
        return ''


# ---------------------------------------------------------------- agenda (Graph, app-token)
def _geheim() -> dict | None:
    w = GEDEELD.lees_raw('agenda-app', 600)
    try:
        d = json.loads(w) if w else None
    except ValueError:
        return None
    return d if d and d.get('secret') else None


def _app_token() -> str:
    from . import appid
    g = _geheim()
    if not g:
        raise ApiFout('De agendakoppeling is nog niet ingericht (opzetten_app.py met het recht Calendars.ReadWrite).')
    with _lock:
        if _TOKEN.get('tot', 0) > time.time() + 120 and _TOKEN.get('s') == g['secret'][-6:]:
            return _TOKEN['t']
        r = _S.post(f'https://login.microsoftonline.com/{appid.PARTNER_TENANT}/oauth2/v2.0/token',
                    data={'grant_type': 'client_credentials', 'client_id': appid.CLIENT_ID, 'client_secret': g['secret'],
                          'scope': 'https://graph.microsoft.com/.default'}, timeout=30)
        if r.status_code >= 400:
            fout = (r.json() if r.content else {}).get('error_description', '')[:160]
            log.info('Agenda: app-token geweigerd (%s)', r.status_code)
            raise ApiFout(f'Agendakoppeling geweigerd door Microsoft ({r.status_code}). Draai opzetten_app.py opnieuw (geheim verlopen of recht ontbreekt). {fout}')
        j = r.json()
        _TOKEN.update(t=j['access_token'], tot=time.time() + int(j.get('expires_in') or 3600), s=g['secret'][-6:])
        return _TOKEN['t']


def _graph(methode: str, pad: str, body=None) -> dict:
    r = _S.request(methode, 'https://graph.microsoft.com/v1.0' + pad, json=body, timeout=30,
                   headers={'Authorization': 'Bearer ' + _app_token(), 'Content-Type': 'application/json'})
    if r.status_code >= 400:
        raise ApiFout(f'Outlook-agenda: {r.status_code} {(r.json().get("error") or {}).get("message", "") if r.content else ""}'[:240], r.status_code)
    return r.json() if r.content else {}


def _afspraak(mail: str, t: dict, start: datetime, eind: datetime, tekst: str, wie: str, event_id: str | None = None) -> str:
    body = {'subject': f"{t.get('number')} {t.get('company') or ''}: {t.get('title') or ''}".strip()[:250],
            'body': {'contentType': 'text', 'content': f"{tekst}\n\nTicket {t.get('number')} - {t.get('title')}\nKlant: {t.get('company') or '-'}\n"
                                                         f"Ingepland door {wie} via Microsoft 365 beheer." + (f"\n{t['url']}" if t.get('url') else '')},
            'start': {'dateTime': start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': 'UTC'},
            'end': {'dateTime': eind.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': 'UTC'},
            'location': {'displayName': t.get('company') or ''}, 'showAs': 'busy', 'isReminderOn': True, 'reminderMinutesBeforeStart': 15,
            'categories': ['Service call']}
    if event_id:
        _graph('PATCH', f'/users/{mail}/events/{event_id}', body)
        return event_id
    return _graph('POST', f'/users/{mail}/events', body).get('id', '')


# ---------------------------------------------------------------- gedeelde stand
def _koppeling() -> dict:
    w = GEDEELD.lees_raw('agenda-koppeling', 300)
    try:
        return json.loads(w) if w else {}
    except ValueError:
        return {}


def _calls() -> dict:
    w = GEDEELD.lees_raw('servicecalls', 60)
    try:
        return json.loads(w) if w else {}
    except ValueError:
        return {}


def _calls_bewaar(d: dict) -> None:
    grens = (datetime.now() - timedelta(days=120)).isoformat()
    d = {k: v for k, v in d.items() if v.get('at', '') >= grens}
    GEDEELD.schrijf_raw('servicecalls', json.dumps(d, separators=(',', ':')))
    GEDEELD.cache.pop('raw:servicecalls', None)


# ---------------------------------------------------------------- medewerkers (resource + rol)
def mensen(at) -> list[dict]:
    """Planbare medewerkers: per Autotask-resource de servicedeskrollen (een gedeelde resource kan per collega een rol hebben)."""
    item = _CACHE.get('mensen')
    if item and time.time() - item[0] < 600:
        return item[1]
    from .h_management import _in
    res = at.query('Resources', [{'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'firstName', 'lastName', 'email'], 500)
    try:
        rr = at.query('ResourceServiceDeskRoles', [{'op': 'eq', 'field': 'isActive', 'value': True}], ['resourceID', 'roleID', 'isDefault'], 2000)
    except ApiFout:
        rr = []
    rollen = {x['id']: x.get('name') or '' for x in _in(at, 'Roles', {x.get('roleID') for x in rr}, ['id', 'name'])}
    kop = _koppeling()
    uit = []
    for r in sorted(res, key=lambda x: f"{x.get('firstName') or ''} {x.get('lastName') or ''}".lower()):
        naam = f"{r.get('firstName') or ''} {r.get('lastName') or ''}".strip()
        eigen = [x for x in rr if x.get('resourceID') == r['id']]
        if len(eigen) > 1:   # meerdere rollen: per rol een keuze (bijv. gedeelde servicedesk-resource)
            for x in sorted(eigen, key=lambda x: rollen.get(x.get('roleID'), '')):
                k = f"{r['id']}:{x['roleID']}"
                uit.append({'key': k, 'resourceId': r['id'], 'roleId': x['roleID'], 'name': f"{naam} ({rollen.get(x['roleID'], 'rol')})",
                            'mail': kop.get(k) or kop.get(str(r['id'])) or r.get('email') or '', 'mapped': k in kop})
        else:
            k = str(r['id'])
            uit.append({'key': k, 'resourceId': r['id'], 'roleId': eigen[0]['roleID'] if eigen else None, 'name': naam,
                        'mail': kop.get(k) or r.get('email') or '', 'mapped': k in kop})
    _CACHE['mensen'] = (time.time(), uit)
    return uit


# ---------------------------------------------------------------- API
@api('sc.opties')
def sc_opties(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    lijst = mensen(at)
    return {'people': lijst, 'me': next((m['key'] for m in lijst if m['resourceId'] == ik['id']), None), 'calendar': bool(_geheim()), 'admin': is_beheerder(c.staat)}


def _ticket(at, tid: int) -> dict:
    from .h_servicedesk import _link
    t = at.req('GET', f'Tickets/{int(tid)}').get('item') or {}
    if not t:
        raise ApiFout('Ticket niet gevonden.')
    naam = (at.req('GET', f"Companies/{t['companyID']}").get('item') or {}).get('companyName') or '' if t.get('companyID') is not None else ''
    return {'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'companyId': t.get('companyID'), 'company': naam,
            'status': t.get('status'), 'url': _link(at, t['id'])}


def _post_kind(at, pad: str, los: str, body: dict) -> int | None:
    try:
        r = at.req('POST', pad, body)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        r = at.req('POST', los, body)
    return (r or {}).get('itemId')


@api('sc.lijst')
def sc_lijst(c: Ctx, b: dict) -> dict:
    """Service calls van een ticket (met wie en wanneer)."""
    from . import h_autotask as A
    from .h_management import _in
    _zet_auth(c)
    at = A._at()
    tid = int(b['ticketId'])
    sct = at.query('ServiceCallTickets', [{'op': 'eq', 'field': 'ticketID', 'value': tid}], ['id', 'serviceCallID'], 100)
    if not sct:
        return {'calls': []}
    calls = _in(at, 'ServiceCalls', {x['serviceCallID'] for x in sct}, ['id', 'startDateTime', 'endDateTime', 'description', 'isComplete', 'status'])
    res = at.query('ServiceCallTicketResources', [{'op': 'in', 'field': 'serviceCallTicketID', 'value': [x['id'] for x in sct]}], ['serviceCallTicketID', 'resourceID'], 200)
    namen = {m['resourceId']: m['name'].split(' (')[0] for m in mensen(at)}
    per_sct = {x['id']: x['serviceCallID'] for x in sct}
    wie: dict = {}
    for r in res:
        wie.setdefault(per_sct.get(r['serviceCallTicketID']), []).append(namen.get(r.get('resourceID'), ''))
    eigen = _calls()
    uit = [{'id': x['id'], 'start': _lokaal(x.get('startDateTime')), 'end': _lokaal(x.get('endDateTime')), 'description': x.get('description') or '',
            'done': bool(x.get('isComplete')), 'who': (eigen.get(str(x['id'])) or {}).get('name') or ', '.join(w for w in wie.get(x['id'], []) if w),
            'calendar': bool((eigen.get(str(x['id'])) or {}).get('eventId'))} for x in calls]
    return {'calls': sorted(uit, key=lambda x: x['start'])}


@api('sc.nieuw')
def sc_nieuw(c: Ctx, b: dict) -> dict:
    """{ticketId, who (key uit sc.opties), start, end ('YYYY-MM-DDTHH:MM' lokale tijd), description}."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    t = _ticket(at, int(b['ticketId']))
    m = next((x for x in mensen(at) if x['key'] == str(b.get('who'))), None)
    if not m:
        raise ApiFout('Kies wie de service call doet.')
    start, eind = _utc(b['start']), _utc(b['end'])
    if eind <= start:
        raise ApiFout('De eindtijd moet na de begintijd liggen.')
    tekst = str(b.get('description') or '').strip()
    if not tekst:
        raise ApiFout('Beschrijf wat er gedaan gaat worden.')
    if t['companyId'] is None:
        raise ApiFout('Het ticket heeft geen klant.')
    ik = A._ik(at)
    r = at.req('POST', 'ServiceCalls', {'companyID': t['companyId'], 'startDateTime': _iso(start), 'endDateTime': _iso(eind), 'description': tekst[:2000]})
    sid = (r or {}).get('itemId')
    if not sid:
        raise ApiFout('Autotask gaf geen nummer voor de service call terug.')
    sct = _post_kind(at, f'ServiceCalls/{sid}/Tickets', 'ServiceCallTickets', {'serviceCallID': sid, 'ticketID': t['id']})
    if sct:
        _post_kind(at, f'ServiceCallTickets/{sct}/Resources', 'ServiceCallTicketResources', {'serviceCallTicketID': sct, 'resourceID': m['resourceId']})
    gepland = False
    if start > datetime.now(timezone.utc):   # afspraak in de toekomst: ticket op Gepland
        w = next((p['value'] for p in at.picklists('Tickets').get('status', []) if GEPLAND.search(str(p.get('label') or ''))), None)
        if w is not None:
            try:
                at.req('PATCH', 'Tickets', {'id': t['id'], 'status': w})
                gepland = True
            except ApiFout as e:
                log.info('Ticket op Gepland zetten: %s', e)
    event_id, agenda_fout = '', None
    if m['mail']:
        try:
            event_id = _afspraak(m['mail'], t, start, eind, tekst, ik['name'])
        except ApiFout as e:
            agenda_fout = str(e)
    else:
        agenda_fout = f"Geen e-mailadres bekend voor {m['name']} (Servicedesk > Instellingen > Agenda)."
    d = _calls()
    d[str(sid)] = {'ticketId': t['id'], 'mail': m['mail'], 'eventId': event_id, 'name': m['name'], 'by': ik['name'], 'at': datetime.now().isoformat(timespec='minutes')}
    _calls_bewaar(d)
    A.lijst_wissen(t['companyId'], ('t',))
    c.L(f"Service call voor ticket {t['number']} ingepland: {m['name']}, {start.astimezone():%d-%m %H:%M}-{eind.astimezone():%H:%M}"
        + (' (in de agenda)' if event_id else '') + (', ticket op Gepland' if gepland else '') + '.')
    return {'id': sid, 'calendar': bool(event_id), 'calendarError': agenda_fout, 'planned': gepland}


@api('sc.wijzig')
def sc_wijzig(c: Ctx, b: dict) -> dict:
    """Andere tijd of omschrijving: Autotask en de agenda-afspraak bijwerken."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    sid = int(b['id'])
    start, eind = _utc(b['start']), _utc(b['end'])
    tekst = str(b.get('description') or '').strip()
    at.req('PATCH', 'ServiceCalls', {'id': sid, 'startDateTime': _iso(start), 'endDateTime': _iso(eind), 'description': tekst[:2000]})
    e = _calls().get(str(sid)) or {}
    if e.get('eventId') and e.get('mail'):
        try:
            _afspraak(e['mail'], _ticket(at, int(e['ticketId'])), start, eind, tekst, A._ik(at)['name'], e['eventId'])
        except ApiFout as x:
            return {'calendarError': str(x)}
    c.L('Service call verplaatst.')
    return {}


@api('sc.verwijder')
def sc_verwijder(c: Ctx, b: dict) -> dict:
    """Service call annuleren: weg uit Autotask en uit de agenda."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    sid = int(b['id'])
    try:
        at.req('DELETE', f'ServiceCalls/{sid}')
    except ApiFout as e:
        if e.status not in (404,):
            raise
    d = _calls()
    e = d.pop(str(sid), None) or {}
    if e.get('eventId') and e.get('mail'):
        try:
            _graph('DELETE', f"/users/{e['mail']}/events/{e['eventId']}")
        except ApiFout as x:
            log.info('Agenda-afspraak verwijderen: %s', x)
    _calls_bewaar(d)
    c.L('Service call geannuleerd (ook uit de agenda).')
    return {}


def sluit_van_ticket(at, ticket_id: int) -> int:
    """Open service calls van een afgerond ticket ook afronden."""
    sct = at.query('ServiceCallTickets', [{'op': 'eq', 'field': 'ticketID', 'value': int(ticket_id)}], ['serviceCallID'], 50)
    n = 0
    for x in sct:
        try:
            sc = at.req('GET', f"ServiceCalls/{x['serviceCallID']}").get('item') or {}
            if sc and not sc.get('isComplete'):
                at.req('PATCH', 'ServiceCalls', {'id': sc['id'], 'isComplete': 1})
                n += 1
        except ApiFout as e:
            log.info('Service call %s afronden: %s', x.get('serviceCallID'), e)
    if n:
        log.info('Ticket %s afgerond: %s service call(s) ook afgerond', ticket_id, n)
    return n


def _na_status(at, ticket_id, status) -> None:
    """Haak uit Autotask.req (PATCH Tickets met status): bij een eindstatus de service calls afronden (op de achtergrond)."""
    from . import h_autotask as A
    try:
        eind = {str(v) for v in A.eindstatussen(at).values() if v is not None} | {str(v) for v in A._klaar(at, 'Tickets')}
    except ApiFout:
        return
    if str(status) in eind:
        from .clients import achtergrond_fn
        threading.Thread(target=achtergrond_fn(lambda: sluit_van_ticket(at, ticket_id)), daemon=True).start()


# ---------------------------------------------------------------- instellingen (app-beheerder)
@api('sc.agenda')
def sc_agenda(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    eis_beheerder(c)
    g = _geheim()
    return {'configured': bool(g), 'until': (g or {}).get('end', ''), 'people': mensen(A._at())}


@api('sc.agenda.koppel')
def sc_agenda_koppel(c: Ctx, b: dict) -> dict:
    """{key ('resource' of 'resource:rol'), mail}: in welke agenda deze medewerker/rol komt. Leeg = standaard (e-mail van de resource)."""
    _zet_auth(c)
    eis_beheerder(c)
    k = _koppeling()
    mail = str(b.get('mail') or '').strip().lower()
    if mail and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[a-z]{2,}', mail):
        raise ApiFout('Vul een geldig e-mailadres in.')
    if mail:
        k[str(b['key'])] = mail
    else:
        k.pop(str(b['key']), None)
    GEDEELD.schrijf_raw('agenda-koppeling', json.dumps(k))
    GEDEELD.cache.pop('raw:agenda-koppeling', None)
    _CACHE.pop('mensen', None)
    c.L('Agendakoppeling bijgewerkt.')
    return {}


def vergeet() -> None:
    _CACHE.clear()
    _TOKEN.clear()


def _registreer() -> None:
    from . import h_autotask as A
    if _na_status not in A.NA_STATUS:
        A.NA_STATUS.append(_na_status)


_registreer()
