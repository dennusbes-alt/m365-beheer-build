"""Lokale webserver (alleen 127.0.0.1) die de React-interface en de API serveert."""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from concurrent.futures import Future

from .clients import achtergrond
from .context import API, Ctx, Staat, VERS
from .rechten import (DIRECTIE_MELDING, FACTURATIE_MELDING, JUSTDATA_ACTIES, JUSTDATA_MELDING, SALES_MELDING, is_directie, is_facturatie, is_justdata,
                      is_sales)

log = logging.getLogger('m365beheer')

# Acties die het venster naar voren moeten halen (na inloggen in de browser)
NAAR_VOREN = {'auth.login'}   # alleen na inloggen in de browser; wisselen van klant laat het venster met rust

# Na deze wijzigingen wordt de cache van de betreffende klant geleegd (ook als de actie deels mislukte)
ONGELDIG = {
    'in.profile.assign': ('in.profielen',), 'in.profile.delete': ('in.profielen',),
    'in.app.assign': ('in.apps',), 'in.app.delete': ('in.apps',), 'in.app.add': ('in.apps',),
    'in.whfb.set': ('in.inschrijving',), 'in.esp.set': ('in.inschrijving',), 'in.restrict.set': ('in.inschrijving',), 'in.limit.set': ('in.inschrijving',),
    'in.mdm.set': ('in.inschrijving',), 'in.android.create': ('in.inschrijving',), 'in.android.token': ('in.inschrijving',), 'in.android.delete': ('in.inschrijving',),
    'user.update': ('users',), 'user.block': ('users',), 'inactive.delete': ('users',),
    'user.license': ('users', 'skus'), 'user.create': ('users', 'skus'),
    'offboard': ('users', 'skus', 'gedeeld', 'gedeeldrechten'),
    'group.create': ('groepen', 'gedeeld'), 'group.delete': ('groepen', 'gedeeld', 'gedeeldrechten'),
    'dev.delete': ('apparaten', 'autopilot'), 'shared.member.set': ('gedeeldrechten',), 'ap.delete': ('apparaten', 'autopilot'), 'ap.tag': ('apparaten', 'autopilot'),
    'ap.sync': ('autopilot',), 'ap.import': ('autopilot',), 'dev.apreset': ('apparaten',),
}


# Leesacties waarvan het antwoord kort (VERS seconden) per klant wordt hergebruikt: een scherm dat je net met de
# muis aanwees (vooraf geladen) opent dan direct. Gelijktijdige gelijke verzoeken wachten op één antwoord.
SNEL = {'dom.list', 'health.overview', 'health.messages', 'mig.batches', 'mig.endpoints', 'mig.domains', 'brand.get', 'auth.methods',
        'auth.sspr', 'threat.list', 'dkim.list', 'rules.list', 'connectors.list', 'groups.list', 'shared.list', 'users', 'skus',
        'dev.list', 'ap.list', 'sp.sites', 'inactive', 'ss.list', 'cd.devices', 'cu.users', 'ar.overzicht', 'rd.copilot', 'rd.nen', 'ret.list',
        'group.members', 'cal.get', 'fwd.get', 'ar.get', 'ret.mailbox', 'user.get', 'user.groups', 'user.mfa', 'dev.get', 'dkim.get', 'dom.get',
        'in.profiles', 'in.apps', 'in.enroll', 'in.profile.status', 'in.app.status', 'spm.sites', 'spm.libs', 'spm.folders', 'spm.perms', 'spm.groupusers', 'ca.list', 'ca.apps'}
# Acties die niets wijzigen: die maken de antwoordcache niet ongeldig
LEES = SNEL | {'info', 'activity', 'job.status', 'tenant.progress', 'gdap.status', 'update.status', 'auth.status', 'ping', 'prefs.get',
               'customers', 'adm.status', 'tenant.prefetch', 'user.get', 'user.groups', 'user.mfa', 'user.sharedscan', 'group.members',
               'cal.get', 'dev.get', 'dev.groups', 'dev.bitlocker', 'trace.search', 'trace.detail', 'threat.get', 'dkim.get', 'dom.get',
               'mig.users', 'mig.check', 'health.issue', 'auto.status', 'auto.lijst', 'auto.blokken', 'user.template', 'user.onedrive', 'dev.bitlocker.zoek', 'mig.endpoint.test', 'ar.get', 'ret.mailbox', 'fwd.get', 'rd.nen.pdf', 'bk.keys.status', 'bk.overzicht', 'bk.controles', 'dm.overzicht', 'dm.afzenders', 'dm.status', 'app.rol', 'at.status', 'at.opties', 'at.bedrijven', 'at.tickets', 'at.taken', 'at.contacten', 'mg.overzicht', 'sd.opties', 'sd.bedrijven', 'sd.mijn', 'sd.zoek', 'bk.saas.seats', 'sd.queue', 'sd.melding', 'sd.changes', 'sd.kpi', 'sd.inrichting', 'fa.overzicht', 'fa.pdf', 'ts.periode', 'ts.bronnen', 'ts.projecten', 'sa.opties', 'sa.overzicht', 'sa.notities', 'sa.contract.opties', 'sa.prijzen', 'vr.overzicht', 'vr.ticket', 'sc.opties', 'sc.lijst', 'sc.agenda', 'rmm.apparaten', 'rmm.apparaat', 'rmm.sessie', 'rmm.status', 'pr.overzicht', 'pr.project', 'pr.templates', 'sd.zoek','sd.eerstelijn', 'sd.resources', 'ig.status', 'ig.zoek', 'adv.status', 'adv.ticket', 'sd.statussen', 'spm.klantstatus', 'spm.toegangskaart', 'mg.kwartalen', 'mg.klant', 'at.bk.status', 'spm.sites', 'spm.libs', 'spm.folders', 'spm.perms', 'spm.groupusers', 'at.medewerkers', 'in.profiles', 'in.profile.status', 'in.apps', 'in.app.status', 'in.store.search', 'in.enroll', 'in.android.qr', 'ca.list', 'ca.apps'}


class App:
    def __init__(self, web_dir: Path, token: str | None = None):
        self.web_dir = web_dir
        self.token = token or secrets.token_urlsafe(24)
        self.staat = Staat()
        self._snel: dict = {}
        self._snel_lock = threading.Lock()
        self.laatste_ping = time.time()
        self.bye_op: float | None = None
        self.stop = threading.Event()
        self.naar_voren: Callable[[], None] | None = None
        self.httpd: ThreadingHTTPServer | None = None
        self.port = 0

    def start(self, port: int = 0) -> str:
        app = self

        class H(Handler):
            pass
        H.app = app
        self.httpd = ThreadingHTTPServer(('127.0.0.1', port), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name='http').start()
        return f'http://127.0.0.1:{self.port}/?t={self.token}'

    def afsluiten(self) -> None:
        try:
            self.staat.reset()      # tokens wissen = afgemeld
        finally:
            if self.httpd:
                threading.Thread(target=self.httpd.shutdown, daemon=True).start()
            self.stop.set()

    def uitvoeren(self, naam: str, body: dict, tid: str) -> dict:
        if naam in SNEL:
            return self._snel_uitvoeren(naam, body, tid)
        if naam not in LEES:   # wijziging: antwoorden van deze klant niet meer hergebruiken
            with self._snel_lock:
                for k in [k for k in self._snel if k[0] == tid]:
                    self._snel.pop(k, None)
        return self._uitvoeren(naam, body, tid)

    def _snel_uitvoeren(self, naam: str, body: dict, tid: str) -> dict:
        vers = bool(body.get('fresh'))
        sleutel = (tid, naam, json.dumps({k: v for k, v in body.items() if k != 'fresh'}, sort_keys=True))
        with self._snel_lock:
            item = self._snel.get(sleutel)
            eigen = vers or not item or time.time() - item[0] > VERS
            if eigen:
                fut: Future = Future()
                self._snel[sleutel] = (time.time(), fut)
            else:
                fut = item[1]
        if not eigen:
            return fut.result()
        try:
            res = self._uitvoeren(naam, body, tid)
        except BaseException as e:  # noqa: BLE001
            res = {'ok': False, 'error': str(e), 'log': []}
        if not res.get('ok'):
            with self._snel_lock:
                if self._snel.get(sleutel, (0, None))[1] is fut:
                    self._snel.pop(sleutel, None)
        fut.set_result(res)
        return res

    def _uitvoeren(self, naam: str, body: dict, tid: str) -> dict:
        c = Ctx(self.staat, naam, tid)
        if naam.startswith(JUSTDATA_ACTIES) and not is_justdata(self.staat):
            # Alleen-Justdata-koppelingen: zonder Justdata-login niets doen (geen sleutels lezen, geen verkeer)
            if naam.endswith('.status'):
                return {'ok': True, 'data': {'configured': False, 'justdata': False, 'session': None, 'admin': False}, 'log': []}
            return {'ok': False, 'error': JUSTDATA_MELDING, 'log': []}
        if naam.startswith('mg.') and not is_directie(self.staat):
            return {'ok': False, 'error': DIRECTIE_MELDING, 'log': []}
        if naam.startswith('fa.') and not is_facturatie(self.staat):
            return {'ok': False, 'error': FACTURATIE_MELDING, 'log': []}
        if naam.startswith('sa.') and not is_sales(self.staat):
            return {'ok': False, 'error': SALES_MELDING, 'log': []}
        begin = time.perf_counter()
        try:
            fn = API.get(naam)
            if not fn:
                raise ValueError(f'Onbekende actie: {naam}')
            data = fn(c, body) or {}
            res = {'ok': True, 'data': data, 'log': c.log}
            ms = (time.perf_counter() - begin) * 1000
            if ms > 800 and naam not in ('auth.login', 'update.status'):
                log.info('Actie %s duurde %.0f ms', naam, ms)
        except Exception as e:  # noqa: BLE001 - alles netjes terug naar de interface
            log.error('FOUT (%s): %s\n%s', naam, e, traceback.format_exc())
            res = {'ok': False, 'error': str(e) or e.__class__.__name__, 'log': c.log}
            if getattr(e, 'klant_login', False):   # SharePoint: inloggen met een klantaccount aanbieden
                res['klantLogin'] = True
            if getattr(e, 'gdap_status', ''):   # GDAP-uitleg: link (bijv. goedkeuringslink voor de klant) meesturen
                res.update(link=getattr(e, 'link', ''), gdap=e.gdap_status)
        if res.get('ok') and naam not in LEES and tid and is_justdata(self.staat):
            try:
                from .h_autotask import registreer
                registreer(self.staat, tid, naam, c.log)
            except Exception:  # noqa: BLE001 - werkregistratie mag een actie nooit hinderen
                pass
        t = self.staat.tenants.get(tid) if naam in ONGELDIG else None
        if t is not None and hasattr(t, 'weg'):
            t.weg(*ONGELDIG[naam])
        for regel in c.log:
            log.info('[%s] %s', naam, regel)
        if naam in NAAR_VOREN and self.naar_voren:
            try:
                self.naar_voren()
            except Exception:
                pass
        return res


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = 'M365Beheer'
    sys_version = ''

    def log_message(self, fmt, *args):  # geen verzoeken in de log
        pass

    def _host_ok(self) -> bool:
        h = self.headers.get('Host', '')
        return h in (f'127.0.0.1:{self.app.port}', f'localhost:{self.app.port}')

    def _stuur(self, status: int, type_: str, data: bytes, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header('Content-Type', type_)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _weiger(self) -> None:
        self._stuur(403, 'text/plain; charset=utf-8', 'Niet toegestaan'.encode())

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            return self._weiger()
        u = urlparse(self.path)
        pad = u.path
        cookie_zetten = False
        if pad in ('/', '/index.html'):
            via_url = parse_qs(u.query).get('t', [''])[0] == self.app.token
            via_cookie = f'm365t={self.app.token}' in [c.strip() for c in self.headers.get('Cookie', '').split(';')]
            if not (via_url or via_cookie):
                return self._weiger()
            cookie_zetten = via_url
            self.app.laatste_ping = time.time()
            self.app.bye_op = None
            pad = '/index.html'
        bestand = (self.app.web_dir / pad.lstrip('/')).resolve()
        if not str(bestand).startswith(str(self.app.web_dir.resolve())) or not bestand.is_file():
            return self._stuur(404, 'text/plain; charset=utf-8', b'Niet gevonden')
        type_ = mimetypes.guess_type(bestand.name)[0] or 'application/octet-stream'
        if type_.startswith('text/') or type_ in ('application/javascript', 'image/svg+xml'):
            type_ += '; charset=utf-8'
        extra = {'Content-Security-Policy': "default-src 'self'; img-src 'self' data: https://aadcdn.msftauthimages.net https://aadcdn.msauthimages.net https://secure.aadcdn.microsoftonline-p.com; style-src 'self' 'unsafe-inline'; "
                                            "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"} if pad == '/index.html' else None
        if cookie_zetten:  # zodat verversen (F5) blijft werken; alleen geldig voor deze lokale sessie
            extra['Set-Cookie'] = f'm365t={self.app.token}; HttpOnly; SameSite=Strict; Path=/'
        self._stuur(200, type_, bestand.read_bytes(), extra)

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok() or self.headers.get('X-Token') != self.app.token:
            return self._weiger()
        pad = urlparse(self.path).path
        if not pad.startswith('/api/'):
            return self._weiger()
        naam = pad[5:]
        self.app.laatste_ping = time.time()
        if naam == 'ping':
            self.app.bye_op = None
            return self._json({'ok': True})
        if naam == 'bye':
            self.app.bye_op = time.time()
            return self._json({'ok': True})
        if naam == 'quit':
            self._json({'ok': True})
            self.app.afsluiten()
            return
        self.app.bye_op = None
        lengte = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(lengte) or b'{}') if lengte else {}
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if self.headers.get('X-Achter') == '1':   # live verversen van een scherm: achtergrondverbindingen en -pool, nooit ten koste van een klik
            with achtergrond():
                return self._json(self.app.uitvoeren(naam, body, self.headers.get('X-Tenant', '')))
        self._json(self.app.uitvoeren(naam, body, self.headers.get('X-Tenant', '')))

    def _json(self, obj: dict) -> None:
        data = json.dumps(obj, ensure_ascii=False, default=_json_extra, separators=(',', ':')).encode('utf-8')
        self._stuur(200, 'application/json; charset=utf-8', data)


def _json_extra(o):
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


def bewaak_browser(app: App) -> None:
    """Alleen in browsermodus: stoppen als het tabblad dicht is of lang niets doet."""
    while not app.stop.wait(1):
        if app.bye_op and time.time() - app.bye_op > 8:
            break
        if time.time() - app.laatste_ping > 20 * 60:
            break
    app.afsluiten()


def omgeving_pad() -> Path:
    return Path(os.path.expanduser('~'))
