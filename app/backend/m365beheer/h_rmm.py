"""Datto RMM (API v2): na een nieuwe klant uit Sales direct de site in Datto RMM aanmaken.

- Koppeling (alleen app-beheerder): platform-URL (bij Justdata: https://pinotage-api.centrastage.net), API key en API secret van een RMM-gebruiker
  (Setup > Users > Generate API Keys). Gedeeld via de verborgen SharePoint-lijst ('datto-rmm'), nooit in logboek of code.
- Token: POST {url}/auth/oauth/token, Basic public-client:public, grant_type=password, username=key, password=secret (100 uur geldig).
- Site: PUT {url}/api/v2/site {name, description, notes, onDemand, splashtopAutoInstall}; eerst controleren of de naam al bestaat
  (GET /api/v2/account/sites?siteName=..., terugval: alle sites per pagina van 250).
Rate limit: 600 opvragingen en 100 wijzigingen per minuut per account. NIET getest met een echte Datto RMM.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time

import requests

from .clients import ApiFout
from .context import API, Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import eis_beheerder, is_beheerder, is_sales

log = logging.getLogger('m365beheer')
PLATFORMS = ['pinotage', 'merlot', 'concord', 'vidal', 'zinfandel', 'syrah']
_TOKEN: dict = {}
_lock = threading.Lock()
_S = requests.Session()


def _sleutels() -> dict | None:
    w = GEDEELD.lees_raw('datto-rmm', 300)
    try:
        d = json.loads(w) if w else None
    except ValueError:
        return None
    return d if d and d.get('url') and d.get('key') and d.get('secret') else None


def _url(u: str) -> str:
    u = str(u or '').strip().rstrip('/')
    if u.lower() in PLATFORMS:
        u = f'https://{u.lower()}-api.centrastage.net'
    if not re.fullmatch(r'https://[a-z]+-api\.centrastage\.net', u):
        raise ApiFout('Vul de API URL van Datto RMM in, bijvoorbeeld https://pinotage-api.centrastage.net (staat bij Setup > Users > API Keys).')
    return u


def _token(sl: dict, vers: bool = False) -> str:
    with _lock:
        if not vers and _TOKEN.get('key') == sl['key'] and _TOKEN.get('tot', 0) > time.time() + 300:
            return _TOKEN['token']
        r = _S.post(sl['url'] + '/auth/oauth/token', auth=('public-client', 'public'),
                    data={'grant_type': 'password', 'username': sl['key'], 'password': sl['secret']}, timeout=30)
        if r.status_code in (400, 401):
            raise ApiFout('Datto RMM weigert de API key/secret (controleer of API-toegang aan staat en of de sleutels kloppen).', r.status_code)
        if r.status_code >= 400:
            raise ApiFout(f'Datto RMM-aanmelding mislukt ({r.status_code}).', r.status_code)
        j = r.json()
        _TOKEN.update(key=sl['key'], token=j['access_token'], tot=time.time() + int(j.get('expires_in') or 360000))
        return _TOKEN['token']


def _req(methode: str, pad: str, sl: dict | None = None, **kw):
    sl = sl or _sleutels()
    if not sl:
        raise ApiFout('Datto RMM is nog niet gekoppeld (Servicedesk > Instellingen).')
    for poging in range(2):
        r = _S.request(methode, sl['url'] + pad, headers={'Authorization': 'Bearer ' + _token(sl, vers=poging > 0), 'Accept': 'application/json'}, timeout=60, **kw)
        if r.status_code == 401 and poging == 0:
            continue
        break
    if r.status_code == 429:
        raise ApiFout('Datto RMM: te veel aanvragen; probeer het over een minuut opnieuw.', 429)
    if r.status_code >= 400:
        raise ApiFout(f'Datto RMM {r.status_code}: {r.text[:200]}', r.status_code)
    return r.json() if r.content else {}


def _bestaat(naam: str, sl=None) -> dict | None:
    """Site met (vrijwel) dezelfde naam, om dubbele sites te voorkomen."""
    plat = re.sub(r'[^a-z0-9]', '', naam.lower())
    try:
        j = _req('GET', '/api/v2/account/sites', sl, params={'siteName': naam, 'max': 250})
        kandidaten = j.get('sites') or []
    except ApiFout:
        kandidaten, pagina = [], 0
        while pagina < 40:
            j = _req('GET', '/api/v2/account/sites', sl, params={'max': 250, 'page': pagina})
            kandidaten += j.get('sites') or []
            if not (j.get('pageDetails') or {}).get('nextPageUrl'):
                break
            pagina += 1
    return next((s for s in kandidaten if re.sub(r'[^a-z0-9]', '', str(s.get('name') or '').lower()) == plat), None)


@api('rmm.status')
def rmm_status(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    sl = _sleutels()
    return {'configured': bool(sl), 'url': sl['url'] if sl and is_beheerder(c.staat) else '', 'admin': is_beheerder(c.staat)}


@api('rmm.keys.set')
def rmm_keys_set(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    eis_beheerder(c)
    sl = {'url': _url(b.get('url')), 'key': str(b.get('key') or '').strip(), 'secret': str(b.get('secret') or '').strip()}
    if not sl['key'] or not sl['secret']:
        raise ApiFout('Vul de API key en het API secret in.')
    _token(sl, vers=True)                      # controleren voordat het wordt opgeslagen
    _req('GET', '/api/v2/account', sl)
    GEDEELD.schrijf_raw('datto-rmm', json.dumps(sl))
    GEDEELD.cache.pop('raw:datto-rmm', None)
    c.L('Datto RMM gekoppeld (gedeeld).')
    return {'configured': True}


@api('rmm.keys.delete')
def rmm_keys_delete(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    eis_beheerder(c)
    GEDEELD.schrijf_raw('datto-rmm', None)
    GEDEELD.cache.pop('raw:datto-rmm', None)
    _TOKEN.clear()
    return {'configured': False}


@api('rmm.site.nieuw')
def rmm_site_nieuw(c: Ctx, b: dict) -> dict:
    """Site in Datto RMM voor een (nieuwe) klant. Sales en app-beheerder."""
    _zet_auth(c)
    if not (is_sales(c.staat) or is_beheerder(c.staat)):
        raise ApiFout('Alleen sales en de app-beheerder maken sites in Datto RMM.')
    naam = str(b.get('name') or '').strip()
    if len(naam) < 2:
        raise ApiFout('Geen klantnaam.')
    bestaand = _bestaat(naam)
    if bestaand:
        return {'exists': True, 'site': {'uid': bestaand.get('uid'), 'name': bestaand.get('name'), 'url': bestaand.get('portalUrl') or ''}}
    body = {'name': naam[:100], 'description': str(b.get('description') or '')[:500], 'notes': str(b.get('notes') or 'Aangemaakt vanuit Microsoft 365 beheer (Sales)')[:500],
            'onDemand': False, 'splashtopAutoInstall': bool(b.get('splashtop', False))}
    s = _req('PUT', '/api/v2/site', json=body)
    c.L(f'Site {naam} aangemaakt in Datto RMM.')
    return {'exists': False, 'site': {'uid': s.get('uid'), 'name': s.get('name') or naam, 'url': s.get('portalUrl') or ''}}


def vergeet() -> None:
    _TOKEN.clear()


# ================================================================ apparaten en meekijken (v2.39)
# Apparaten: GET /api/v2/account/devices (pagina's van 250, pageDetails.nextPageUrl), detail GET /api/v2/device/{uid}.
# Veldnamen van het Device-object zijn NIET bevestigd (Swagger vraagt een login): _v probeert meerdere namen en de eerste
# opvraging logt de veldnamen ("Datto RMM-apparaat: velden"). Bedrijf = Autotask-koppeling van de site (autotaskCompanyId/Name
# als die bestaat), anders Autotask-bedrijf met dezelfde naam als de site.
# Meekijken: web remote van Datto in een eigen venster van de app (VENSTER, gezet door main.py). Sluit de medewerker dat venster,
# dan is de sessie klaar: tijd = duur van de sessie, per kwartier naar boven (zoals alle tijd), omschrijving door de medewerker,
# daarna afronden (Complete / Ready to Invoice) of open laten. Zonder eigen venster (browser): handmatig 'Klaar met meekijken'.
VENSTER = None          # main.py: fn(url, titel, bij_sluiten) -> opent een venster
_SESSIES: dict = {}
_VENSTERS: dict = {}   # sessie-id -> meekijkvenster (om web remote opnieuw te openen)
_VELDEN_GELOGD: set = set()
_APP_CACHE: dict = {}


def _v(d: dict, *namen, standaard=None):
    for n in namen:
        w = d.get(n)
        if w not in (None, ''):
            return w
    return standaard


def _log_velden(soort: str, d: dict) -> None:
    if soort not in _VELDEN_GELOGD and d:
        _VELDEN_GELOGD.add(soort)
        log.info('Datto RMM-%s: velden %s', soort, sorted(d.keys()))


def _alles(pad: str, sleutel: str, max_pag: int = 60) -> list[dict]:
    uit, pagina = [], 0
    while pagina < max_pag:
        j = _req('GET', pad, params={'max': 250, 'page': pagina})
        uit += j.get(sleutel) or []
        if not (j.get('pageDetails') or {}).get('nextPageUrl'):
            break
        pagina += 1
    return uit


def _apparaten(vers: bool = False) -> list[dict]:
    item = _APP_CACHE.get('dev')
    if item and not vers and time.time() - item[0] < 300:
        return item[1]
    ruw = _alles('/api/v2/account/devices', 'devices')
    if ruw:
        _log_velden('apparaat', ruw[0])
    uit = [_vorm(d) for d in ruw]
    _APP_CACHE['dev'] = (time.time(), uit)
    return uit


def _vorm(d: dict) -> dict:
    av = d.get('antivirus') if isinstance(d.get('antivirus'), dict) else {}
    pm = d.get('patchManagement') if isinstance(d.get('patchManagement'), dict) else {}
    soort = d.get('deviceType') if isinstance(d.get('deviceType'), dict) else {}
    return {'uid': _v(d, 'uid', 'deviceUid'), 'id': _v(d, 'id'), 'name': _v(d, 'hostname', 'deviceName', 'name', standaard=''),
            'description': _v(d, 'description', standaard=''), 'user': _v(d, 'lastLoggedInUser', 'lastUser', standaard=''),
            'site': _v(d, 'siteName', standaard=''), 'siteUid': _v(d, 'siteUid', standaard=''), 'online': bool(_v(d, 'online', standaard=False)),
            'lastSeen': _v(d, 'lastSeen', 'lastSeenDate', standaard=''), 'os': _v(d, 'operatingSystem', 'os', standaard=''),
            'type': soort.get('category') or soort.get('type') or _v(d, 'deviceClass', standaard=''), 'ip': _v(d, 'intIpAddress', 'internalIp', standaard=''),
            'extIp': _v(d, 'extIpAddress', 'externalIp', standaard=''), 'av': av.get('antivirusProduct') or av.get('antivirusStatus') or '',
            'avStatus': av.get('antivirusStatus') or '', 'patch': pm.get('patchStatus') or '', 'reboot': bool(_v(d, 'rebootRequired', standaard=False)),
            'portal': _v(d, 'portalUrl', standaard=''), 'remote': _v(d, 'webRemoteUrl', 'remoteUrl', standaard='')}


def _laatst(w) -> str:
    """lastSeen kan een epoch in milliseconden of een datum zijn."""
    try:
        if isinstance(w, (int, float)) or str(w).isdigit():
            from datetime import datetime
            return datetime.fromtimestamp(int(w) / 1000).strftime('%d-%m-%Y %H:%M')
    except (ValueError, OSError):
        pass
    return str(w or '')[:16].replace('T', ' ')


def _sites() -> dict:
    item = _APP_CACHE.get('sites')
    if item and time.time() - item[0] < 900:
        return item[1]
    ruw = _alles('/api/v2/account/sites', 'sites', 20)
    if ruw:
        _log_velden('site', ruw[0])
    uit = {s.get('uid'): s for s in ruw}
    _APP_CACHE['sites'] = (time.time(), uit)
    return uit


def _bedrijf(site_uid: str, site_naam: str) -> dict | None:
    """Autotask-bedrijf bij een Datto-site (bedrijfstoewijzing in Datto RMM), anders op naam."""
    from . import h_autotask as A
    s = _sites().get(site_uid) or {}
    cid = s.get('autotaskCompanyId', s.get('psaCompanyId'))
    naam = _v(s, 'autotaskCompanyName', standaard='') or site_naam
    if cid not in (None, ''):   # 0 = intern bedrijf (bijv. Justdata)
        return {'id': int(cid), 'name': naam}
    sleutel = ('bedrijf', naam.lower())
    if sleutel in _APP_CACHE:
        return _APP_CACHE[sleutel]
    at = A._at()
    r = at.query('Companies', [{'op': 'eq', 'field': 'companyName', 'value': naam}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'companyName'], 2) \
        or at.query('Companies', [{'op': 'beginsWith', 'field': 'companyName', 'value': naam[:30]}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'companyName'], 2)
    b = {'id': r[0]['id'], 'name': r[0].get('companyName') or naam} if len(r) == 1 else None
    _APP_CACHE[sleutel] = b
    return b


@api('rmm.apparaten')
def rmm_apparaten(c: Ctx, b: dict) -> dict:
    """Zoeken op apparaatnaam, ingelogde gebruiker, omschrijving, site of IP; optioneel alleen één site."""
    _zet_auth(c)
    if not _sleutels():
        return {'configured': False, 'devices': []}
    q = str(b.get('q') or '').strip().lower()
    lijst = _apparaten(bool(b.get('fresh')))
    if b.get('siteUid'):
        lijst = [d for d in lijst if d['siteUid'] == b['siteUid']]
    if b.get('company'):   # vanuit een ticket: eerst de apparaten van die klant (site met dezelfde naam)
        plat = re.sub(r'[^a-z0-9]', '', str(b['company']).lower())[:12]
        van_klant = [d for d in lijst if plat and plat in re.sub(r'[^a-z0-9]', '', d['site'].lower())]
        lijst = van_klant or lijst
    if q:
        woorden = q.split()
        lijst = [d for d in lijst if all(w in f"{d['name']} {d['user']} {d['description']} {d['site']} {d['ip']}".lower() for w in woorden)]
    lijst = sorted(lijst, key=lambda d: (not d['online'], d['name'].lower()))
    max_ = 5000 if b.get('all') else 200   # tabblad Apparaten: alles (gegroepeerd per klant); kiezen vanuit een ticket: de eerste 200
    return {'configured': True, 'total': len(lijst), 'devices': [{**d, 'lastSeen': _laatst(d['lastSeen'])} for d in lijst[:max_]]}


@api('rmm.apparaat')
def rmm_apparaat(c: Ctx, b: dict) -> dict:
    """Basisinformatie van één apparaat, met het Autotask-bedrijf (voor het ticket)."""
    _zet_auth(c)
    uid = str(b['uid'])
    try:
        ruw = _req('GET', f'/api/v2/device/{uid}')
        _log_velden('apparaat-detail', ruw)
        d = _vorm(ruw)
    except ApiFout:
        d = next((x for x in _apparaten() if x['uid'] == uid), None)
        if not d:
            raise
    try:
        bedr = _bedrijf(d['siteUid'], d['site'])
    except ApiFout:
        bedr = None
    return {'device': {**d, 'lastSeen': _laatst(d['lastSeen'])}, 'company': bedr, 'window': VENSTER is not None}


def _remote_url(d: dict) -> str:
    if d.get('remote'):
        return d['remote']
    if d.get('portal'):
        return d['portal']
    sl = _sleutels() or {}
    return sl.get('url', '').replace('-api.', '.')   # portal van het platform, bijv. pinotage.centrastage.net


@api('rmm.ticket')
def rmm_ticket(c: Ctx, b: dict) -> dict:
    """Ticket voor het meekijken (bedrijf uit Datto RMM, contactpersoon, onderwerp, korte beschrijving). Geen kwartier vooraf:
    de tijd komt uit de sessie."""
    from . import h_autotask as A
    _zet_auth(c)
    from .h_autotask import _heeft_bedrijf
    titel = str(b.get('title') or '').strip()
    if not _heeft_bedrijf(b) or not titel:
        raise ApiFout('Kies het bedrijf en vul het onderwerp in.')
    at = A._at()
    t = A._nieuw_ticket(at, int(b['companyId']), titel[:250], str(b.get('description') or '').strip() or titel, A._ik(at), A._instellingen(),
                        int(b['contactId']) if b.get('contactId') else None)
    c.L(f"Ticket {t['number']} aangemaakt voor meekijken: {titel}.")
    return {'ticket': t}


@api('rmm.sessie.start')
def rmm_sessie_start(c: Ctx, b: dict) -> dict:
    """{uid, ticketId, ticketNumber, title, company}: web remote openen en de sessie starten."""
    import uuid
    from datetime import datetime
    _zet_auth(c)
    if not b.get('ticketId'):
        raise ApiFout('Kies eerst het ticket (bestaand of nieuw).')
    d = next((x for x in _apparaten() if x['uid'] == str(b['uid'])), None) or {'uid': str(b['uid']), 'name': str(b.get('name') or 'apparaat')}
    sid = uuid.uuid4().hex[:10]
    s = {'id': sid, 'uid': d['uid'], 'device': d.get('name'), 'ticketId': int(b['ticketId']), 'ticketNumber': str(b.get('ticketNumber') or ''),
         'title': str(b.get('title') or ''), 'company': str(b.get('company') or ''), 'start': datetime.now().isoformat(timespec='seconds'), 'end': None,
         'window': VENSTER is not None}
    _SESSIES[sid] = s
    try:   # altijd de actuele web remote-link van dit apparaat (webRemoteUrl), niet de algemene portal
        vers = _vorm(_req('GET', f"/api/v2/device/{d['uid']}"))
        d = {**d, 'remote': vers.get('remote') or d.get('remote'), 'portal': vers.get('portal') or d.get('portal')}
    except ApiFout as e:
        log.info('Meekijken: apparaat opnieuw ophalen mislukt (%s)', e)
    url = _remote_url(d)
    log.info('Meekijken: %s', 'web remote van het apparaat' if d.get('remote') else 'GEEN webRemoteUrl, apparaatpagina/portal gebruikt')
    s['url'] = url
    if b.get('browser'):   # keuze van de medewerker: in de eigen browser (sneller, Datto-login van de browser)
        s['window'] = False
    if VENSTER is not None and not b.get('browser'):
        def klaar() -> None:
            _VENSTERS.pop(sid, None)
            if s.get('naarBrowser'):   # venster dicht omdat de sessie naar de browser ging: sessie loopt door
                return
            if not s['end']:
                s['end'] = datetime.now().isoformat(timespec='seconds')
        _VENSTERS[sid] = VENSTER(url, f"Meekijken: {d.get('name')} ({s['company'] or 'Datto RMM'})", klaar)
    else:
        API['open.url'](c, {'url': url})
    c.L(f"Meekijken gestart op {d.get('name')} voor ticket {s['ticketNumber']}.")
    return {'session': s, 'url': url}


@api('rmm.sessie')
def rmm_sessie(c: Ctx, b: dict) -> dict:
    from datetime import datetime
    _zet_auth(c)
    s = _SESSIES.get(str(b.get('id')))
    if not s:
        raise ApiFout('Deze meekijksessie is niet (meer) bekend.')
    eind = datetime.fromisoformat(s['end']) if s['end'] else datetime.now()
    minuten = (eind - datetime.fromisoformat(s['start'])).total_seconds() / 60
    from .h_autotask import _afgerond
    return {'session': s, 'minutes': round(minuten, 1), 'rounded': _afgerond(minuten), 'ended': bool(s['end'])}


@api('rmm.sessie.opnieuw')
def rmm_sessie_opnieuw(c: Ctx, b: dict) -> dict:
    """Web remote van het apparaat opnieuw laden (bijv. na inloggen bij Datto op de startpagina beland)."""
    _zet_auth(c)
    s = _SESSIES.get(str(b.get('id')))
    if not s or not s.get('url'):
        raise ApiFout('Deze meekijksessie is niet (meer) bekend.')
    w = _VENSTERS.get(s['id'])
    if w is not None:
        try:
            w.load_url(s['url'])
            w.show()
            return {}
        except Exception as e:  # noqa: BLE001 - venster al dicht
            log.info('Meekijkvenster opnieuw laden: %s', e)
    API['open.url'](c, {'url': s['url']})
    return {}


@api('rmm.sessie.browser')
def rmm_sessie_browser(c: Ctx, b: dict) -> dict:
    """Lopende sessie verder in de eigen browser (Edge/Chrome): sneller dan het venster van de app. De tijd loopt door;
    afronden met 'Klaar' in de app."""
    _zet_auth(c)
    s = _SESSIES.get(str(b.get('id')))
    if not s or not s.get('url'):
        raise ApiFout('Deze meekijksessie is niet (meer) bekend.')
    s['naarBrowser'] = True
    s['window'] = False
    API['open.url'](c, {'url': s['url']})
    w = _VENSTERS.pop(s['id'], None)
    if w is not None:
        try:
            w.destroy()
        except Exception as e:  # noqa: BLE001 - al dicht
            log.info('Meekijkvenster sluiten: %s', e)
    return {'session': s}


@api('rmm.sessie.stop')
def rmm_sessie_stop(c: Ctx, b: dict) -> dict:
    """Handmatig klaar (geen eigen venster, of venster bleef open)."""
    from datetime import datetime
    _zet_auth(c)
    s = _SESSIES.get(str(b.get('id')))
    if s and not s['end']:
        s['end'] = datetime.now().isoformat(timespec='seconds')
    return rmm_sessie(c, b)


@api('rmm.sessie.boek')
def rmm_sessie_boek(c: Ctx, b: dict) -> dict:
    """{id, description, close: 'complete'|'invoice'|'' , resolution}: tijd van de sessie op het ticket (per kwartier naar boven),
    daarna afronden of open laten voor opvolging."""
    from datetime import datetime
    from . import h_autotask as A
    _zet_auth(c)
    s = _SESSIES.get(str(b.get('id')))
    if not s:
        raise ApiFout('Deze meekijksessie is niet (meer) bekend.')
    if not s['end']:
        s['end'] = datetime.now().isoformat(timespec='seconds')
    tekst = str(b.get('description') or '').strip()
    if not tekst:
        raise ApiFout('Beschrijf wat er is gedaan.')
    start = datetime.fromisoformat(s['start']).astimezone()
    minuten = (datetime.fromisoformat(s['end']) - datetime.fromisoformat(s['start'])).total_seconds() / 60
    at = A._at()
    ik, inst = A._ik(at), A._instellingen()
    t = at.req('GET', f"Tickets/{s['ticketId']}").get('item') or {'id': s['ticketId']}
    A._tijdregel(at, {'id': s['ticketId'], 'assignedResourceroleID': t.get('assignedResourceroleID')}, ik, A._afgerond(minuten), tekst[:7900], inst, start=start)
    sluit = str(b.get('close') or '')
    if sluit in ('complete', 'invoice'):
        w = A.eindstatussen(at, inst)[sluit]
        if w is None:
            raise ApiFout('Tijd is geboekt, maar Autotask kent die eindstatus niet; rond het ticket af in Autotask.')
        body = {'id': s['ticketId'], 'status': w}
        if str(b.get('resolution') or '').strip():
            body['resolution'] = str(b['resolution']).strip()[:7900]
        at.req('PATCH', 'Tickets', body)
    _SESSIES.pop(s['id'], None)
    if t.get('companyID'):
        A.lijst_wissen(t['companyID'], ('t',))
    c.L(f"Meekijken op {s['device']}: {A._afgerond(minuten)} minuten geboekt op ticket {s['ticketNumber']}" +
        (', ticket afgerond.' if sluit in ('complete', 'invoice') else ', ticket blijft open.'))
    return {'minutes': A._afgerond(minuten), 'closed': sluit in ('complete', 'invoice')}
