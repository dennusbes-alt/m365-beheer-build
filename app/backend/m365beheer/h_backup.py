"""Back-upoverzicht voor de servicedesk: Datto BCDR, Datto Endpoint Backup (Direct-to-Cloud), Datto SaaS Protection
en Unitrends (UniView), met een gedeelde afvinklijst in SharePoint (Justdata).

- API-sleutels staan in de kluis van het besturingssysteem (Windows Referentiebeheer / Mac-sleutelhanger) via keyring,
  nooit in bestanden van de app en nooit in het logboek.
- Datto: https://api.datto.com/v1, basic auth met openbare + geheime sleutel (Partner Portal > Admin > Integrations).
- Unitrends: OAuth2 client credentials op https://login.backup.net/connect/token, API https://public-api.backup.net.
- Datto documenteert de veldnamen van de antwoorden niet openbaar: velden worden daarom flexibel gelezen (meerdere
  mogelijke namen) en bij de eerste opvraging worden de veldNAMEN (niet de waarden) in het logboek gezet.
"""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import requests
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from . import lokaal
from .clients import ApiFout, Graph, _sessie, _verstuur, achtergrond_fn
from .context import Ctx, api
from .rechten import eis_beheerder, eis_justdata, is_beheerder, is_justdata

log = logging.getLogger('m365beheer')
DIENST = 'Justdata M365 Beheer'
BRONNEN = {
    'datto': {'naam': 'Datto (BCDR, Endpoint Backup en SaaS Protection)', 'velden': [('a', 'Openbare API-sleutel'), ('b', 'Geheime API-sleutel')],
              'uitleg': 'Datto Partner Portal > Admin > Integrations > API Keys.'},
    'unitrends': {'naam': 'Unitrends (UniView)', 'velden': [('a', 'Client-ID'), ('b', 'Client secret')],
                  'uitleg': 'UniView-portal > instellingen > API Access > + New. Het secret is maar één keer zichtbaar.'},
}
DATTO = 'https://api.datto.com/v1'
UT_TOKEN = 'https://login.backup.net/connect/token'
UT = 'https://public-api.backup.net'
OK_UUR, WAARSCHUW_UUR = 26, 72      # laatste geslaagde back-up: tot 26 uur = goed, tot 72 uur = waarschuwing, daarna fout
LIJST = 'M365BeheerBackupControles'
LOKAAL = 'backupcontroles.json'


# ---------------------------------------------------------------- Kluis (keyring)
def _kluis():
    import keyring
    try:   # expliciet de juiste kluis (in de gebouwde app werkt automatisch zoeken niet altijd)
        if sys.platform == 'win32':
            from keyring.backends import Windows
            keyring.set_keyring(Windows.WinVaultKeyring())
        elif sys.platform == 'darwin':
            from keyring.backends import macOS
            keyring.set_keyring(macOS.Keyring())
    except Exception:  # noqa: BLE001
        pass
    return keyring


def _kluis_lees(bron: str) -> tuple[str, str] | None:
    try:
        w = _kluis().get_password(DIENST, f'backup-{bron}')
        if not w:
            return None
        d = json.loads(w)
        return d['a'], d['b']
    except Exception:  # noqa: BLE001
        return None


def _kluis_weg(bron: str) -> None:
    try:
        _kluis().delete_password(DIENST, f'backup-{bron}')
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- Gedeelde koppelingen (SharePoint Justdata)
# De sleutels staan in een verborgen lijst op de Justdata-SharePoint, zodat één beheerder koppelt en alle collega's
# (met hun eigen Justdata-login) direct verder kunnen. Alleen in het geheugen gelezen (10 min), nooit gelogd.
SLEUTELLIJST = 'M365BeheerKoppelingen'
_AUTH: dict = {}


def _zet_auth(c: Ctx) -> None:
    _AUTH['auth'] = c.staat.auth


_ROOT: dict = {}
_root_lock = threading.Lock()


def _root_site(g: Graph) -> str:
    """ID van de Justdata-rootsite, één keer per sessie opgevraagd (gedeeld door koppelingen en afvinklijst)."""
    with _root_lock:
        if not _ROOT.get('id'):
            _ROOT['id'] = g.get('/sites/root?$select=id')['id']
        return _ROOT['id']


class Gedeeld:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.site = self.lijst_id = ''
        self.cache: dict[str, tuple[float, Any]] = {}
        self.lees_lock = threading.Lock()
        self.geladen = 0.0
        self.ververst_bezig = False

    def _g(self) -> Graph:
        a = _AUTH.get('auth')
        if not a or not a.ingelogd:
            raise ApiFout('Niet aangemeld.')
        eis_justdata(SimpleNamespace(auth=a))   # gedeelde koppelingen staan alleen in de Justdata-tenant
        return Graph(lambda: a.token(a.home_tenant, 'partner'))

    def _lijst(self) -> tuple[Graph, str, str]:
        g = self._g()
        with self.lock:
            if not self.lijst_id:
                site = _root_site(g)
                l = g.get(f"/sites/{site}/lists?$filter=displayName eq '{SLEUTELLIJST}'&$select=id").get('value') or []
                if l:
                    lid = l[0]['id']
                else:
                    lid = g.post(f'/sites/{site}/lists', {'displayName': SLEUTELLIJST, 'description': 'Koppelingen van de app Microsoft 365 beheer (niet wijzigen)',
                                                          'columns': [{'name': 'Waarde', 'text': {'allowMultipleLines': True, 'textType': 'plain'}}],
                                                          'list': {'template': 'genericList', 'hidden': True}})['id']
                    log.info('SharePoint-lijst %s aangemaakt (verborgen)', SLEUTELLIJST)
                self.site, self.lijst_id = site, lid
            return g, self.site, self.lijst_id

    def _items(self) -> list[dict]:
        g, site, lid = self._lijst()
        return g.all(f'/sites/{site}/lists/{lid}/items?$expand=fields($select=Title,Waarde)&$top=50')

    def alles_lezen(self) -> bool:
        """Alle koppelingen in één opvraging lezen (was: één volledige opvraging per koppeling, na elkaar)."""
        with self.lees_lock:   # gelijktijdige verzoeken wachten op één ophaalactie
            if time.time() - self.geladen < 5:
                return True
            try:
                items = self._items()
            except Exception as e:  # noqa: BLE001 - niet aangemeld of geen rechten
                log.info('Gedeelde gegevens lezen niet gelukt (%s)', type(e).__name__)
                return False
            nu = time.time()
            gezien = set()
            for it in items:
                f = it.get('fields') or {}
                if f.get('Title') and f.get('Waarde'):
                    self.cache['raw:' + f['Title']] = (nu, f['Waarde'])
                    gezien.add('raw:' + f['Title'])
            for k in [k for k in self.cache if k.startswith('raw:') and k not in gezien]:
                self.cache[k] = (nu, None)
            for k in [k for k in self.cache if not k.startswith('raw:')]:
                self.cache.pop(k, None)   # afgeleide waarden opnieuw bepalen
            self.geladen = nu
            return True

    def lees_raw(self, titel: str, ttl: int = 600) -> str | None:
        item = self.cache.get('raw:' + titel)
        if item and time.time() - item[0] < ttl:
            return item[1]
        if item:
            # verouderd: direct de bekende waarde geven en op de achtergrond verversen
            if not self.ververst_bezig:
                self.ververst_bezig = True

                def ververs():
                    try:
                        self.alles_lezen()
                    finally:
                        self.ververst_bezig = False
                threading.Thread(target=achtergrond_fn(ververs), daemon=True).start()
            return item[1]
        if self.geladen and time.time() - self.geladen < ttl:
            return None   # bij de laatste lezing niet aanwezig
        self.alles_lezen()
        item = self.cache.get('raw:' + titel)
        return item[1] if item else None

    def schrijf_raw(self, titel: str, waarde: str | None) -> None:
        g, site, lid = self._lijst()
        bestaand = [it for it in self._items() if (it.get('fields') or {}).get('Title') == titel]
        for it in (bestaand[1:] if waarde is not None else bestaand):
            g.delete(f"/sites/{site}/lists/{lid}/items/{it['id']}")
        if waarde is not None:
            if bestaand:
                g.patch(f"/sites/{site}/lists/{lid}/items/{bestaand[0]['id']}/fields", {'Waarde': waarde})
            else:
                g.post(f'/sites/{site}/lists/{lid}/items', {'fields': {'Title': titel, 'Waarde': waarde}})
        self.cache['raw:' + titel] = (time.time(), waarde)
        if titel.startswith('backup-'):
            self.cache.pop(titel[7:], None)

    def lees(self, bron: str) -> tuple[str, str] | None:
        item = self.cache.get(bron)
        if item and time.time() - item[0] < 600:
            return item[1]
        w = self.lees_raw(f'backup-{bron}')
        try:
            d = json.loads(w) if w else None
            v = (d['a'], d['b']) if d else None
        except (ValueError, KeyError, TypeError):
            v = None
        self.cache[bron] = (time.time(), v)
        return v

    def schrijf(self, bron: str, a: str, b: str | None) -> None:
        self.schrijf_raw(f'backup-{bron}', json.dumps({'a': a, 'b': b}) if b is not None else None)
        self.cache[bron] = (time.time(), (a, b) if b is not None else None)


GEDEELD = Gedeeld()


def _sleutels(bron: str) -> tuple[str, str] | None:
    """Gedeelde koppeling (SharePoint Justdata); staat die er nog niet maar wel in de eigen kluis, dan wordt die gedeeld."""
    if not is_justdata(SimpleNamespace(auth=_AUTH.get('auth'))):
        return None   # zonder Justdata-login: geen sleutels, ook niet uit de eigen kluis
    w = GEDEELD.lees(bron)
    if w:
        return w
    eigen = _kluis_lees(bron)
    if eigen and _AUTH.get('auth') and is_beheerder(SimpleNamespace(auth=_AUTH['auth'])):
        try:
            GEDEELD.schrijf(bron, eigen[0], eigen[1])
            _kluis_weg(bron)
            log.info('Koppeling %s uit de eigen kluis gedeeld met alle collega\'s.', bron)
        except Exception as e:  # noqa: BLE001
            log.info('Koppeling %s delen niet gelukt (%s)', bron, type(e).__name__)
    return eigen


@api('bk.keys.status')
def bk_keys_status(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    return {'admin': is_beheerder(c.staat), 'sources': [{'key': k, 'name': v['naam'], 'fields': [{'key': f, 'label': l} for f, l in v['velden']], 'help': v['uitleg'],
                         'set': _sleutels(k) is not None} for k, v in BRONNEN.items()]}


@api('bk.keys.set')
def bk_keys_set(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    bron = str(b.get('source'))
    if bron not in BRONNEN:
        raise ApiFout('Onbekende bron.')
    a, s = str(b.get('a') or '').strip(), str(b.get('b') or '').strip()
    if not a or not s:
        raise ApiFout('Vul beide velden in.')
    # Eerst testen, dan pas bewaren
    try:
        (_datto_get('/bcdr/device', {'_page': 1, '_perPage': 1}, (a, s)) if bron == 'datto' else _ut_token((a, s), vers=True))
    except ApiFout as e:
        raise ApiFout(f"De sleutels werken niet: {e}")
    _zet_auth(c)
    try:
        GEDEELD.schrijf(bron, a, s)
        _kluis_weg(bron)
        waar = 'gedeeld met alle Justdata-collega\'s (verborgen SharePoint-lijst)'
    except Exception as e:  # noqa: BLE001 - SharePoint niet beschikbaar: alleen op deze computer
        log.info('Gedeelde koppeling opslaan niet gelukt (%s), eigen kluis gebruikt', type(e).__name__)
        _kluis().set_password(DIENST, f'backup-{bron}', json.dumps({'a': a, 'b': s}))
        waar = 'opgeslagen in de kluis van deze computer (delen via SharePoint lukte niet)'
    with _job_lock:
        _JOB['bronnen'] = {}
    c.L(f"API-sleutels voor {BRONNEN[bron]['naam']} {waar}.")
    return {}


@api('bk.keys.delete')
def bk_keys_delete(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    bron = str(b.get('source'))
    _zet_auth(c)
    _kluis_weg(bron)
    try:
        GEDEELD.schrijf(bron, '', None)
    except Exception:  # noqa: BLE001
        pass
    with _job_lock:
        _JOB['bronnen'] = {}
    c.L('Koppeling verwijderd (voor alle collega\'s).')
    return {}


# ---------------------------------------------------------------- Hulpfuncties
def _tijd(v) -> datetime | None:
    if v in (None, '', 0, '0'):
        return None
    if isinstance(v, dict):
        v = v.get('timestamp') or v.get('time') or v.get('date')
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            x = float(v)
            return datetime.fromtimestamp(x / 1000 if x > 1e12 else x, tz=timezone.utc)
        s = str(v).strip().replace(' ', 'T', 1)
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, OSError):
        return None


def _veld(d: dict, *namen, standaard=None):
    for n in namen:
        if isinstance(d, dict) and d.get(n) not in (None, ''):
            return d[n]
    return standaard


_GEZIEN: set[str] = set()


def _velden_loggen(soort: str, item: dict) -> None:
    """Eén keer per soort de veldnamen in het logboek (geen waarden), om de koppeling te kunnen verfijnen."""
    if soort not in _GEZIEN and isinstance(item, dict):
        _GEZIEN.add(soort)
        log.info('Back-up %s: velden %s', soort, sorted(item.keys())[:60])


def _klasse(status) -> str:
    if isinstance(status, bool):   # Datto Endpoint Backup: backupStatus True/False
        return 'ok' if status else 'err'
    s = str(status if status is not None else '').lower()
    if s in ('true', 'false'):
        return 'ok' if s == 'true' else 'err'
    if re.search(r'fail|error|fout|missed|critical', s):
        return 'err'
    if re.search(r'warn|partial|incomplete|skipped', s):
        return 'warn'
    if re.search(r'success|perfect|ok|complete|good', s):
        return 'ok'
    return 'unknown'


def _beoordeel(laatste_ok: datetime | None, nu: datetime, fout: str = '', gepauzeerd: bool = False) -> tuple[str, str]:
    if gepauzeerd:
        return 'paused', 'Back-up staat op pauze.'
    if not laatste_ok:
        return 'err', fout or 'Geen geslaagde back-up gevonden.'
    uur = (nu - laatste_ok).total_seconds() / 3600
    if uur <= OK_UUR:
        return ('warn', fout) if fout else ('ok', '')
    if uur <= WAARSCHUW_UUR:
        return 'warn', fout or f'Laatste geslaagde back-up {int(uur)} uur geleden.'
    return 'err', fout or f'Laatste geslaagde back-up {int(uur // 24)} dagen geleden.'


# ---------------------------------------------------------------- Datto
def _datto_sessie() -> requests.Session:
    """Eigen sessie voor Datto: geen automatische herhalingen met lange pauzes (dat doen we zelf, sneller)."""
    from requests.adapters import HTTPAdapter
    s_ = requests.Session()
    s_.headers['User-Agent'] = 'M365Beheer'
    s_.mount('https://', HTTPAdapter(pool_connections=2, pool_maxsize=4, max_retries=0))
    return s_


_DATTO_SESSIE = _datto_sessie()
_DATTO_SLOT = threading.BoundedSemaphore(3)   # maximaal 3 aanvragen tegelijk naar Datto


def _datto_get(pad: str, params: dict | None = None, sleutels=None) -> Any:
    sl = sleutels or _sleutels('datto')
    if not sl:
        raise ApiFout('Geen Datto-sleutels ingesteld.')
    # Datto breekt verbindingen af als er te veel tegelijk lopen (SSL EOF). Dan kort wachten en opnieuw (max. 5 keer), zonder lange pauzes.
    with _DATTO_SLOT:
        for poging in range(5):
            try:
                r = _DATTO_SESSIE.get(DATTO + pad, params=params or {}, auth=sl, headers={'Accept': 'application/json'}, timeout=60)
                break
            except requests.exceptions.RequestException as e:
                if poging == 4:
                    raise ApiFout(f'Datto is niet bereikbaar: {type(e).__name__}') from None
                time.sleep(0.4 * (poging + 1))
    if r.status_code in (401, 403):
        raise ApiFout(f'Datto weigert de toegang ({r.status_code}). Controleer de API-sleutels.', r.status_code)
    if r.status_code >= 400:
        raise ApiFout(f'Datto {r.status_code}: {r.text[:200]}', r.status_code)
    return r.json() if r.content else {}


def _datto_alle(pad: str, params: dict | None = None) -> list[dict]:
    uit, pagina = [], 1
    while pagina <= 50:
        j = _datto_get(pad, {**(params or {}), '_page': pagina, '_perPage': 100})
        items = j if isinstance(j, list) else (j.get('items') or j.get('data') or [])
        uit.extend(items)
        pag = j.get('pagination') if isinstance(j, dict) else None
        totaal = _veld(pag or {}, 'totalPages', 'total_pages', standaard=1)
        if isinstance(j, list) or pagina >= int(totaal or 1) or not items:
            break
        pagina += 1
    return uit


def _bcdr(nu: datetime) -> list[dict]:
    apparaten = [d for d in _datto_alle('/bcdr/device', {'showHiddenDevices': 0}) if not d.get('hidden')]
    if apparaten:
        _velden_loggen('BCDR-apparaat', apparaten[0])

    def per(d: dict) -> list[dict]:
        serie = _veld(d, 'serialNumber', 'serial', standaard='')
        klant = _veld(d, 'clientCompanyName', 'organizationName', 'clientName', 'customerName', 'resellerCompanyName', standaard='(onbekende klant)')
        naam = _veld(d, 'name', 'hostname', standaard=serie)
        gezien = _tijd(_veld(d, 'lastSeenDate', 'lastSeen', 'lastCheckin'))
        regels = []
        offline = not gezien or (nu - gezien) > timedelta(hours=2)
        regels.append({'source': 'Datto BCDR', 'customer': klant, 'name': f'{naam} (appliance)', 'kind': 'Appliance',
                       'last': gezien.isoformat() if gezien else '', 'lastOk': gezien.isoformat() if gezien else '',
                       'status': 'err' if offline and (not gezien or (nu - gezien) > timedelta(hours=24)) else ('warn' if offline else 'ok'),
                       'message': ('Appliance niet online gezien sinds ' + gezien.strftime('%d-%m %H:%M')) if offline and gezien else
                                  ('Appliance nooit online gezien.' if not gezien else ''),
                       'alerts': int(_veld(d, 'alertCount', standaard=0) or 0)})
        try:
            assets = _datto_alle(f'/bcdr/device/{serie}/asset')
        except ApiFout as e:
            regels[0].update(status='warn', message=f'Agents konden niet worden gelezen: {e}')
            return regels
        if assets:
            _velden_loggen('BCDR-agent', assets[0])
        for a in assets:
            if a.get('isArchived'):
                continue
            backups = a.get('backups') or []
            if backups:
                _velden_loggen('BCDR-backup', backups[0])
            laatste_ok, laatste, fout = None, None, ''
            for bk in sorted(backups, key=lambda x: _tijd(x.get('timestamp')) or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
                t = _tijd(bk.get('timestamp'))
                st = (bk.get('backup') or {}).get('status') if isinstance(bk.get('backup'), dict) else bk.get('status')
                laatste = laatste or t
                if _klasse(st) == 'ok' and not laatste_ok:
                    laatste_ok = t
                if not fout and _klasse(st) == 'err':
                    fout = str((bk.get('backup') or {}).get('errorMessage') or 'Laatste back-up mislukt.')[:200]
            if not laatste_ok:
                laatste_ok = _tijd(_veld(a, 'lastSnapshot', 'lastBackup', 'latestSnapshot'))
            status, melding = _beoordeel(laatste_ok, nu, fout if laatste_ok is None or (laatste and laatste > laatste_ok) else '', bool(a.get('isPaused')))
            schot = str(_veld(a, 'lastScreenshotAttemptStatus', standaard='')).lower()
            if status == 'ok' and schot in ('false', 'failed', '0'):
                status, melding = 'warn', 'Screenshotverificatie mislukt.'
            regels.append({'source': 'Datto BCDR', 'customer': klant, 'name': _veld(a, 'name', 'agentName', 'hostname', 'volume', standaard='?'),
                           'kind': 'Share' if str(a.get('type', '')).lower() == 'share' else 'Agent', 'device': naam,
                           'last': laatste.isoformat() if laatste else '', 'lastOk': laatste_ok.isoformat() if laatste_ok else '',
                           'offsite': (_tijd(_veld(a, 'latestOffsite', 'lastOffsite')) or None) and _tijd(_veld(a, 'latestOffsite', 'lastOffsite')).isoformat(),
                           'status': status, 'message': melding})
        return regels
    with ThreadPoolExecutor(max_workers=3) as ex:
        return [x for l in ex.map(per, apparaten) for x in l]


def _dtc(nu: datetime) -> list[dict]:
    assets = _datto_alle('/dtc/assets')
    if assets:
        _velden_loggen('Endpoint-asset', assets[0])
    uit = []
    for a in assets:
        if a.get('isArchived') or a.get('archived'):
            continue
        hist = [h for h in (a.get('last10Backups') or []) if isinstance(h, dict)]
        if hist:
            _velden_loggen('Endpoint-backup', hist[0])
        if isinstance(a.get('lastBackup'), dict):
            _velden_loggen('Endpoint-lastBackup', a['lastBackup'])
        laatste_ok, fout = None, ''
        for h in sorted(hist, key=lambda h: _tijd(_veld(h, 'timestamp', 'endTime', 'startTime', 'time')) or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
            t = _tijd(_veld(h, 'timestamp', 'endTime', 'startTime', 'time'))
            k = _klasse(_veld(h, 'status', 'state', 'result', 'backupStatus', standaard=''))
            if k == 'ok' and t:
                laatste_ok = t
                break
            if k == 'err' and not fout:
                fout = str(_veld(h, 'errorMessage', 'message', 'error', standaard='Een of meer recente back-ups zijn mislukt.'))[:200]
        lb = a.get('lastBackup')
        if not laatste_ok and not hist:
            lbk = _klasse(_veld(lb, 'status', 'state', standaard='')) if isinstance(lb, dict) else 'unknown'
            laatste_ok = _tijd(lb) if lbk in ('ok', 'unknown') else None
        st = str(_veld(a, 'backupState', 'backupStatus', 'lastBackupStatus', standaard=''))
        if not fout and _klasse(st) == 'err':
            fout = f'Back-upstatus: {st}'
        gepauzeerd = bool(_veld(a, 'isPaused', 'paused', standaard=False)) or 'pause' in st.lower()
        status, melding = _beoordeel(laatste_ok, nu, fout, gepauzeerd)
        if status == 'ok' and a.get('screenshotSuccess') is False:
            status, melding = 'warn', 'Screenshotverificatie mislukt.'
        uit.append({'source': 'Datto Endpoint Backup', 'customer': _veld(a, 'organizationName', 'clientName', 'customerName', 'companyName', standaard='(onbekende klant)'),
                    'name': _veld(a, 'hostname', 'name', 'agentName', standaard='?'), 'kind': 'Endpoint',
                    'last': laatste_ok.isoformat() if laatste_ok else '', 'lastOk': laatste_ok.isoformat() if laatste_ok else '', 'status': status, 'message': melding})
    return uit


def _historie(o: Any, pad: str = '') -> list[tuple[str, list]]:
    """Zoekt in een willekeurig antwoord alle 'backupHistory'-lijsten op, met de naam van het onderdeel erbij."""
    gevonden = []
    if isinstance(o, dict):
        if isinstance(o.get('backupHistory'), list):
            gevonden.append((str(_veld(o, 'appType', 'type', 'name', 'suiteType', 'application', 'serviceType', standaard=pad or 'Back-up')), o['backupHistory']))
        for k, v in o.items():
            if k != 'backupHistory':
                gevonden += _historie(v, str(_veld(o, 'appType', 'type', standaard=pad)) if isinstance(v, (list, dict)) else pad)
    elif isinstance(o, list):
        for v in o:
            gevonden += _historie(v, pad)
    return gevonden


def _saas(nu: datetime) -> list[dict]:
    domeinen = _datto_alle('/saas/domains')
    if domeinen:
        _velden_loggen('SaaS-domein', domeinen[0])

    def per(d: dict) -> list[dict]:
        sid = _veld(d, 'saasCustomerId', 'customerId', 'id')
        klant = _veld(d, 'organizationName', 'saasCustomerName', 'customerName', 'domain', standaard='(onbekende klant)')
        product = _veld(d, 'productType', 'product', standaard='SaaS')
        try:
            j = _datto_get(f'/saas/{sid}/applications', {'daysUntil': 3})
        except ApiFout as e:
            return [{'source': 'Datto SaaS Protection', 'customer': klant, 'name': str(product), 'kind': 'SaaS', 'last': '', 'lastOk': '',
                     'status': 'unknown', 'message': f'Status kon niet worden gelezen: {e}'}]
        if isinstance(j, dict) and 'SaaS-toepassing' not in _GEZIEN:
            eerste = j if 'items' not in j else ((j.get('items') or [{}])[0] or {})
            _velden_loggen('SaaS-toepassing', eerste)
            if isinstance(eerste.get('suites'), list) and eerste['suites'] and isinstance(eerste['suites'][0], dict):
                _velden_loggen('SaaS-suite', eerste['suites'][0])
            if isinstance(d.get('backupStats'), dict):
                _velden_loggen('SaaS-backupStats', d['backupStats'])
        regels = []
        for app, hist in _historie(j):
            hist = [h for h in hist if isinstance(h, dict)]
            if hist:
                _velden_loggen('SaaS-historie', hist[0])
            laatste = sorted(hist, key=lambda h: str(_veld(h, 'endTime', 'startTime', 'timeWindow', 'date', standaard='')))[-1] if hist else {}
            st = _veld(laatste, 'status', 'result', standaard='')
            k = _klasse(st)
            totaal = laatste.get('activeServiceCount') or laatste.get('totalServiceCount')
            perfect = laatste.get('activeServiceWithPerfectBackupCount')
            met = laatste.get('activeServiceWithBackupCount')
            detail = f' ({perfect} van {totaal} volledig, {met} met back-up)' if totaal is not None and perfect is not None else ''
            if k == 'ok' and totaal and perfect is not None and perfect < totaal:
                k = 'warn'
            eind = _tijd(_veld(laatste, 'endTime', 'startTime'))
            regels.append({'source': 'Datto SaaS Protection', 'customer': klant, 'name': f'{product} - {app}', 'kind': 'SaaS', 'saasId': sid,
                           'seats': {'total': totaal, 'perfect': perfect, 'withBackup': met},
                           'last': eind.isoformat() if eind else str(_veld(laatste, 'timeWindow', standaard='')),
                           'lastOk': eind.isoformat() if eind and k == 'ok' else '',
                           'status': k if k != 'unknown' else 'warn', 'message': '' if k == 'ok' else f'Laatste status: {st or "onbekend"}{detail}'})
        if not regels:
            regels.append({'source': 'Datto SaaS Protection', 'customer': klant, 'name': str(product), 'kind': 'SaaS', 'saasId': sid, 'last': '', 'lastOk': '',
                           'status': 'unknown', 'message': 'Geen back-uphistorie ontvangen.'})
        return regels
    with ThreadPoolExecutor(max_workers=3) as ex:
        return [x for l in ex.map(per, domeinen) for x in l]


SEAT_SOORTEN = [('User', 'Gebruiker'), ('SharedMailbox', 'Gedeeld postvak'), ('Site', 'SharePoint-site'), ('TeamSite', 'Teamsite'), ('Team', 'Team')]
_SEATS: dict = {}


def _seat(s: dict, soort: str, label: str, nu: datetime) -> dict:
    """Eén beschermd onderdeel (gebruiker, postvak, site, team). De back-upstatus per seat is niet openbaar gedocumenteerd:
    meerdere veldnamen proberen en de veldnamen loggen."""
    naam = _veld(s, 'name', 'displayName', 'seatName', 'mainId', 'email', 'remoteId', standaard='(zonder naam)')
    adres = _veld(s, 'mainId', 'email', 'url', 'siteUrl', standaard='')
    staat = str(_veld(s, 'seatState', 'state', 'protectionStatus', standaard='') or '')
    bst = _veld(s, 'backupStatus', 'lastBackupStatus', 'status', 'lastBackupResult')
    laatste = _tijd(_veld(s, 'lastBackupDate', 'lastSuccessfulBackup', 'lastBackup', 'lastBackupTime', 'lastBackupDateTime'))
    fout = str(_veld(s, 'errorMessage', 'lastError', 'error', standaard='') or '')
    k = _klasse(bst) if bst is not None else 'unknown'
    melding = fout
    if re.search(r'pause', staat, re.I):
        k, melding = 'paused', 'Back-up staat op pauze.'
    elif re.search(r'unprotect|inactive|archiv|unlicens', staat, re.I):
        k, melding = 'warn', f'Niet beschermd ({staat}).'
    elif laatste and k in ('ok', 'unknown'):
        k2, m2 = _beoordeel(laatste, nu, fout)
        k, melding = k2, m2 or melding
    if k in ('err', 'warn') and not melding and bst:
        melding = f'Laatste back-up: {bst}.'
    return {'name': str(naam), 'address': str(adres) if adres != naam else '', 'type': soort, 'typeLabel': label, 'state': staat,
            'status': k, 'message': melding, 'last': laatste.isoformat() if laatste else ''}


@api('bk.saas.seats')
def bk_saas_seats(c: Ctx, b: dict) -> dict:
    """SaaS Protection per gebruiker, gedeeld postvak, SharePoint-site en team; problemen bovenaan. 5 min in het geheugen."""
    _zet_auth(c)
    sid = str(b.get('id') or '').strip()
    if not sid:
        raise ApiFout('Geen SaaS-klant opgegeven.')
    oud = _SEATS.get(sid)
    if oud and not b.get('fresh') and time.time() - oud['t'] < 300:
        return oud['r']
    nu = datetime.now(timezone.utc)

    def soort(x):
        code, label = x
        try:
            lijst = _datto_alle(f'/saas/{sid}/seats', {'seatType': code})
        except ApiFout as e:
            if e.status in (400, 404):   # soort bestaat niet bij deze klant (bijv. geen Teams)
                return [], ''
            return [], f'{label}: {e}'
        if lijst:
            _velden_loggen('SaaS-seat', lijst[0])
        return [_seat(s, code, label, nu) for s in lijst if isinstance(s, dict)], ''
    with ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(soort, SEAT_SOORTEN))
    seats = [s for l, _ in res for s in l]
    volgorde = {'err': 0, 'warn': 1, 'paused': 2, 'unknown': 3, 'ok': 4}
    seats.sort(key=lambda s: (volgorde.get(s['status'], 3), s['typeLabel'], s['name'].lower()))
    tel = {k: sum(1 for s in seats if s['status'] == k) for k in volgorde}
    per = {label: sum(1 for s in seats if s['typeLabel'] == label) for _, label in SEAT_SOORTEN}
    r = {'seats': seats, 'counts': tel, 'perType': {k: v for k, v in per.items() if v}, 'errors': [f for _, f in res if f],
         'statusKnown': any(s['status'] != 'unknown' for s in seats)}
    _SEATS[sid] = {'t': time.time(), 'r': r}
    return r


# ---------------------------------------------------------------- Unitrends (UniView)
_UT_TOKEN: dict = {}


def _ut_token(sleutels=None, vers: bool = False) -> str:
    if not vers and _UT_TOKEN.get('tot', 0) > time.time() + 60:
        return _UT_TOKEN['token']
    sl = sleutels or _sleutels('unitrends')
    if not sl:
        raise ApiFout('Geen Unitrends-sleutels ingesteld.')
    r = _verstuur(_sessie(), 'POST', UT_TOKEN, data={'grant_type': 'client_credentials'}, auth=sl, timeout=30)
    if r.status_code >= 400:
        raise ApiFout(f'Unitrends-aanmelding mislukt ({r.status_code}). Controleer Client-ID en secret.', r.status_code)
    j = r.json()
    if sleutels is None:
        _UT_TOKEN.update(token=j['access_token'], tot=time.time() + int(j.get('expires_in') or 3600))
    return j['access_token']


def _ut_alle(pad: str, params: dict | None = None) -> list[dict]:
    uit, pagina = [], 1
    while pagina <= 100:
        r = _verstuur(_sessie(), 'GET', UT + pad, params={**(params or {}), 'page_number': pagina, 'page_size': 500},
                      headers={'Authorization': 'Bearer ' + _ut_token(), 'Accept': 'application/json'}, timeout=60)
        if r.status_code >= 400:
            raise ApiFout(f'Unitrends {r.status_code}: {r.text[:200]}', r.status_code)
        items = r.json() if r.content else []
        uit.extend(items if isinstance(items, list) else [])
        totaal = int(r.headers.get('Paging-Total-Pages') or 1)
        if pagina >= totaal or not items:
            break
        pagina += 1
    return uit


def _unitrends(nu: datetime) -> list[dict]:
    van = (nu - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    with ThreadPoolExecutor(max_workers=4) as ex:
        fk = ex.submit(_ut_alle, '/v1/customers')
        fa = ex.submit(_ut_alle, '/v1/appliances')
        fs = ex.submit(_ut_alle, '/v1/assets', {'include[backups]': 'last'})
        fb = ex.submit(_ut_alle, '/v1/backups', {'status': 'Successful', 'start_time_from': van})
        klanten, apps, assets, gelukt = fk.result(), fa.result(), fs.result(), fb.result()
    namen = {k.get('id'): k.get('name') or '(onbekende klant)' for k in klanten}
    laatste_ok: dict[str, datetime] = {}
    for b in gelukt:
        t = _tijd(b.get('complete_time') or b.get('start_time'))
        k = b.get('asset_key') or b.get('asset_tag')
        if t and (k not in laatste_ok or t > laatste_ok[k]):
            laatste_ok[k] = t
    uit = []
    for a in apps:
        uit.append({'source': 'Unitrends', 'customer': namen.get(a.get('customer_id'), '(onbekende klant)'), 'name': f"{a.get('name') or a.get('asset_tag')} (appliance)",
                    'kind': 'Appliance', 'last': '', 'lastOk': '', 'status': 'ok' if a.get('is_online') else 'err',
                    'message': '' if a.get('is_online') else 'Appliance offline.'})
    for s in assets:
        lb = s.get('last_backup') or {}
        ok_t = laatste_ok.get(s.get('key')) or laatste_ok.get(s.get('asset_tag'))
        fout = '' if _klasse(lb.get('status')) in ('ok', 'unknown') else f"Laatste back-up: {lb.get('status')}"
        status, melding = _beoordeel(ok_t, nu, fout)
        if not lb and not ok_t:
            status, melding = 'unknown', 'Geen back-up in de afgelopen 7 dagen gevonden (mogelijk niet beveiligd).'
        uit.append({'source': 'Unitrends', 'customer': namen.get(s.get('customer_id'), '(onbekende klant)'), 'name': s.get('name') or s.get('asset_tag') or '?',
                    'kind': s.get('type') or 'Asset', 'last': (_tijd(lb.get('start_time')) or '') and _tijd(lb.get('start_time')).isoformat(),
                    'lastOk': ok_t.isoformat() if ok_t else '', 'status': status, 'message': melding})
    return uit


# ---------------------------------------------------------------- Overzicht (achtergrondklus)
# Het ophalen kan bij veel klanten minuten duren (Datto geeft per apparaat de agents apart). Daarom draait het op de
# achtergrond (eigen verbindingen) en toont het scherm direct wat er al binnen is; elke bron vult zich zodra die klaar is.
_CACHE: dict = {}
_JOB: dict = {'bezig': False, 'start': 0.0, 'eind': 0.0, 'bronnen': {}}
_job_lock = threading.Lock()
VERS_SEC = 300   # zolang wordt een afgerond overzicht hergebruikt (Vernieuwen haalt altijd opnieuw op)


def _taken() -> dict:
    t = {}
    if _sleutels('datto'):
        t.update({'Datto BCDR': _bcdr, 'Datto Endpoint Backup': _dtc, 'Datto SaaS Protection': _saas})
    if _sleutels('unitrends'):
        t['Unitrends'] = _unitrends
    return t


def _start() -> None:
    taken = _taken()
    with _job_lock:
        if _JOB['bezig']:
            return
        oud = _JOB['bronnen']
        _JOB.update(bezig=True, start=time.time(), bronnen={k: {'status': 'bezig', 'items': (oud.get(k) or {}).get('items') or [], 'fout': '', 'sec': 0} for k in taken})
    nu = datetime.now(timezone.utc)

    def een(naam: str, fn) -> None:
        begin = time.time()
        try:
            items = fn(nu)
            with _job_lock:
                _JOB['bronnen'][naam].update(status='klaar', items=items, sec=round(time.time() - begin))
        except Exception as e:  # noqa: BLE001
            log.info('Back-up %s niet gelukt: %s', naam, str(e)[:300])
            with _job_lock:
                _JOB['bronnen'][naam].update(status='fout', fout=str(e)[:300], sec=round(time.time() - begin))
        log.info('Back-up %s: %.0f s', naam, time.time() - begin)

    def alles() -> None:
        try:
            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(achtergrond_fn(lambda kv: een(*kv)), taken.items()))
        finally:
            with _job_lock:
                _JOB.update(bezig=False, eind=time.time())
    threading.Thread(target=alles, daemon=True, name='backup').start()


# ---------------------------------------------------------------- Toewijzing van onderdelen aan een klant (gedeeld)
# Datto Endpoint Backup kent alleen de Datto-organisatie; staan de apparaten van veel klanten in één organisatie
# (bijv. die van Justdata zelf), dan wijs je ze hier per apparaat toe aan de echte klant. Gedeeld via SharePoint.
def item_sleutel(it: dict) -> str:
    return f"{it.get('source') or ''}|{it.get('device') or ''}|{it.get('name') or ''}".lower()


def toewijzingen() -> dict:
    try:
        w = GEDEELD.lees_raw('backup-toewijzing', 120)
        return json.loads(w) if w else {}
    except Exception:  # noqa: BLE001 - zonder toewijzingen gewoon de Datto-indeling
        return {}


def toewijzingen_opslaan(m: dict) -> None:
    GEDEELD.schrijf_raw('backup-toewijzing', json.dumps(m) if m else None)


def _stand() -> dict:
    with _job_lock:
        bronnen = {k: dict(v) for k, v in _JOB['bronnen'].items()}
        bezig = _JOB['bezig']
        eind = _JOB['eind']
    toew = toewijzingen()
    items = []
    for v in bronnen.values():
        if v['status'] == 'fout':
            continue
        for it in v['items']:
            sl = item_sleutel(it)
            it = {**it, 'key': sl}
            if toew.get(sl):
                it.update(origin=it['customer'], customer=toew[sl])
            items.append(it)
    klanten: dict[str, dict] = {}
    volgorde = {'err': 0, 'warn': 1, 'unknown': 2, 'paused': 3, 'ok': 4}
    for it in items:
        naam = str(it['customer'] or '(onbekende klant)').strip()
        k = klanten.setdefault(naam.lower(), {'name': naam, 'sources': set(), 'counts': {'ok': 0, 'warn': 0, 'err': 0, 'unknown': 0, 'paused': 0}, 'items': []})
        k['sources'].add(it['source'])
        k['counts'][it['status']] = k['counts'].get(it['status'], 0) + 1
        k['items'].append(it)
    lijst = []
    for k in klanten.values():
        k['items'].sort(key=lambda x: (volgorde.get(x['status'], 9), x['source'], str(x['name']).lower()))
        k['status'] = 'err' if k['counts']['err'] else 'warn' if k['counts']['warn'] else 'unknown' if k['counts']['unknown'] else 'ok'
        k['sources'] = sorted(k['sources'])
        lijst.append(k)
    lijst.sort(key=lambda k: (volgorde.get(k['status'], 9), k['name'].lower()))
    return {'customers': lijst, 'busy': bezig, 'progress': {k: {'status': v['status'], 'sec': v['sec'], 'count': len(v['items'])} for k, v in bronnen.items()},
            'errors': {k: v['fout'] for k, v in bronnen.items() if v['status'] == 'fout'}, 'sources': list(bronnen),
            'at': datetime.fromtimestamp(eind).strftime('%H:%M') if eind else '', 'configured': bool(bronnen) or bool(_taken())}


@api('bk.overzicht')
def bk_overzicht(c: Ctx, b: dict) -> dict:
    """Geeft direct de huidige stand terug en start zo nodig een nieuwe ophaalklus (de interface vraagt elke 2 s opnieuw)."""
    _zet_auth(c)
    with _job_lock:
        bezig, eind, leeg = _JOB['bezig'], _JOB['eind'], not _JOB['bronnen']
    if not bezig and (b.get('fresh') or leeg or time.time() - eind > VERS_SEC):
        _start()
    return _stand()


# ---------------------------------------------------------------- Controles afvinken (SharePoint Justdata, gedeeld)
class Controles:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.site = self.lijst_id = ''
        self._mij: dict = {}

    def _g(self, c: Ctx) -> Graph:
        a = c.staat.auth
        eis_justdata(c.staat)
        return Graph(lambda: a.token(a.home_tenant, 'partner'))

    def _lijst(self, c: Ctx) -> tuple[Graph, str, str]:
        g = self._g(c)
        with self.lock:
            if not self.lijst_id:
                site = _root_site(g)
                l = g.get(f"/sites/{site}/lists?$filter=displayName eq '{LIJST}'&$select=id").get('value') or []
                if l:
                    lid = l[0]['id']
                else:
                    lid = g.post(f'/sites/{site}/lists', {'displayName': LIJST, 'description': 'Back-upcontroles van de servicedesk (app Microsoft 365 beheer)',
                                                          'columns': [{'name': 'Klant', 'text': {}}, {'name': 'Uitkomst', 'text': {}},
                                                                      {'name': 'Opmerking', 'text': {'allowMultipleLines': True, 'textType': 'plain'}},
                                                                      {'name': 'Ticket', 'text': {}}],
                                                          'list': {'template': 'genericList', 'hidden': False}})['id']
                    log.info('SharePoint-lijst %s aangemaakt', LIJST)
                self.site, self.lijst_id = site, lid
            return g, self.site, self.lijst_id

    def lijst(self, c: Ctx, dagen: int = 45) -> tuple[list[dict], str]:
        k = self._mij.get(dagen)
        if k and time.time() - k[0] < 60:
            return k[1], k[2]
        uit = self._lijst_ophalen(c, dagen)
        self._mij[dagen] = (time.time(), *uit)
        return uit

    def _lijst_ophalen(self, c: Ctx, dagen: int = 45) -> tuple[list[dict], str]:
        grens = (datetime.now(timezone.utc) - timedelta(days=dagen)).strftime('%Y-%m-%dT%H:%M:%SZ')
        try:
            g, site, lid = self._lijst(c)
            items = [it for it in g.all(f"/sites/{site}/lists/{lid}/items?$expand=fields($select=Title,Klant,Uitkomst,Opmerking,Ticket)&$top=500")
                     if str(it.get('createdDateTime') or '') >= grens]
            items.sort(key=lambda it: str(it.get('createdDateTime') or ''), reverse=True)
            uit = [{'id': it['id'], 'customer': (it.get('fields') or {}).get('Klant') or '', 'result': (it.get('fields') or {}).get('Uitkomst') or '',
                    'note': (it.get('fields') or {}).get('Opmerking') or '', 'ticket': (it.get('fields') or {}).get('Ticket') or '',
                    'at': it.get('createdDateTime') or '', 'by': ((it.get('createdBy') or {}).get('user') or {}).get('displayName') or ''} for it in items]
            return uit, 'sharepoint'
        except Exception as e:  # noqa: BLE001
            log.info('Back-upcontroles: SharePoint niet beschikbaar (%s), lokaal', str(e)[:200])
            alle = lokaal.lees(LOKAAL, []) or []
            return [x for x in alle if x.get('at', '') >= grens], 'lokaal'

    def toevoegen(self, c: Ctx, rij: dict) -> str:
        velden = {'Title': f"{rij['customer']} {datetime.now():%Y-%m-%d}", 'Klant': rij['customer'], 'Uitkomst': rij['result'],
                  'Opmerking': rij.get('note') or '', 'Ticket': rij.get('ticket') or ''}
        try:
            g, site, lid = self._lijst(c)
            g.post(f'/sites/{site}/lists/{lid}/items', {'fields': velden})
            self._mij.clear()
            return 'sharepoint'
        except Exception as e:  # noqa: BLE001
            log.info('Back-upcontrole: opslaan in SharePoint niet gelukt (%s), lokaal', str(e)[:200])
            alle = lokaal.lees(LOKAAL, []) or []
            alle.append({**rij, 'at': datetime.now(timezone.utc).isoformat(), 'by': (c.staat.auth.account or {}).get('username', '')})
            lokaal.schrijf(LOKAAL, alle[-3000:])
            return 'lokaal'


CONTROLES = Controles()


@api('bk.toewijzen')
def bk_toewijzen(c: Ctx, b: dict) -> dict:
    """Onderdelen (sleutels uit het overzicht) toewijzen aan een klant, of de toewijzing opheffen (customer leeg)."""
    _zet_auth(c)
    sleutels = [str(k).lower() for k in (b.get('keys') or []) if str(k).strip()]
    klant = str(b.get('customer') or '').strip()[:120]
    if not sleutels:
        raise ApiFout('Kies eerst een of meer onderdelen.')
    GEDEELD.cache.pop('raw:backup-toewijzing', None)
    m = toewijzingen()
    for k in sleutels:
        if klant:
            m[k] = klant
        else:
            m.pop(k, None)
    toewijzingen_opslaan(m)
    c.L(f'{len(sleutels)} onderdeel/onderdelen toegewezen aan {klant}.' if klant else f'Toewijzing van {len(sleutels)} onderdeel/onderdelen opgeheven.')
    return {}


@api('bk.controles')
def bk_controles(c: Ctx, b: dict) -> dict:
    l, waar = CONTROLES.lijst(c, int(b.get('days') or 45))
    return {'checks': l, 'storage': waar}


@api('bk.afvinken')
def bk_afvinken(c: Ctx, b: dict) -> dict:
    klanten = [str(k) for k in (b.get('customers') or []) if str(k).strip()]
    uitkomst = str(b.get('result') or '')
    if not klanten or uitkomst not in ('OK', 'Actie nodig', 'Opgelost'):
        raise ApiFout('Kies een klant en een uitkomst.')
    notitie = str(b.get('note') or '')[:2000]
    with ThreadPoolExecutor(max_workers=6) as ex:
        waar = list(ex.map(lambda k: CONTROLES.toevoegen(c, {'customer': k, 'result': uitkomst, 'note': notitie}), klanten))[-1]
    c.L(f"Back-upcontrole afgevinkt voor {len(klanten)} klant(en): {uitkomst}" + ('' if waar == 'sharepoint' else ' (op deze computer bewaard)') + '.')
    geregistreerd = False
    try:
        from .h_autotask import bk_afgevinkt
        geregistreerd = bk_afgevinkt(klanten, uitkomst, notitie)
    except Exception as e:  # noqa: BLE001
        log.info('Back-upcontrole verzamelen: %s', e)
    return {'storage': waar, 'session': geregistreerd}


def opwarmen(staat) -> None:
    """Direct na het inloggen (op de achtergrond): koppelingen, afvinklijst, back-upoverzicht, e-mailbeveiliging en
    Autotask alvast ophalen, zodat die tabbladen meteen gevuld zijn."""
    begin = time.time()
    _AUTH['auth'] = staat.auth
    if not is_justdata(staat):
        return
    if not GEDEELD.alles_lezen():
        return
    c = SimpleNamespace(staat=staat)
    taken = [lambda: CONTROLES.lijst(c, 45)]
    if _taken():
        taken.append(_start)
    try:
        from . import h_dmarc
        if h_dmarc._sleutels():
            taken.append(lambda: h_dmarc._start(30))
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import h_autotask
        if h_autotask._sleutel():
            taken.append(lambda: (h_autotask._instellingen(), h_autotask._klanten(), h_autotask._ik(h_autotask._at())))
            for ent in ('Tickets', 'Projects', 'Tasks'):   # keuzelijsten (statussen e.d.): één keer per sessie
                taken.append(lambda ent=ent: h_autotask._at().picklists(ent))
    except Exception:  # noqa: BLE001
        pass
    with ThreadPoolExecutor(max_workers=7) as ex:
        for f in [ex.submit(achtergrond_fn(t)) for t in taken]:
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                log.info('Opwarmen: %s', str(e)[:200])
    log.info('Opwarmen na inloggen: %.1f s', time.time() - begin)


def vergeet_koppelingen() -> None:
    """Bij afmelden en vóór elke nieuwe login: alle sleutels, tokens en opgehaalde gegevens van de
    Justdata-koppelingen uit het geheugen wissen (een volgende login, bijv. van een andere organisatie, ziet niets)."""
    _AUTH.clear()
    _ROOT.clear()
    g = GEDEELD
    with g.lock:
        g.site = g.lijst_id = ''
        g.cache.clear()
        g.geladen = 0.0
    with CONTROLES.lock:
        CONTROLES.site = CONTROLES.lijst_id = ''
        CONTROLES._mij.clear()
    for d in (_UT_TOKEN, _CACHE):
        d.clear()
    with _job_lock:
        _JOB.update(bezig=False, start=0.0, eind=0.0, bronnen={})
    for naam in ('h_dmarc', 'h_autotask', 'h_itglue', 'h_advies', 'h_servicecall', 'h_rmm', 'h_voorraad', 'h_sales'):
        try:
            import importlib
            importlib.import_module(f'.{naam}', __package__).vergeet()
        except Exception as e:  # noqa: BLE001
            log.info('Wissen %s: %s', naam, e)
