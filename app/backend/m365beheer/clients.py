"""HTTP-clients voor Microsoft Graph en Exchange Online (REST, zonder PowerShell)."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

GB = 'https://graph.microsoft.com/v1.0'
log = logging.getLogger('m365beheer')


def _tls_snel() -> None:
    """Snelle TLS voor ALLE requests-verkeer in de app (Graph, Exchange, MSAL, SharePoint, Autotask, Datto, Unitrends, EasyDMARC).
    requests laat urllib3 bij elke nieuwe verbinding het CA-bestand (certifi) opnieuw inlezen met load_verify_locations;
    op Windows kost dat 1,3-2,8 s per verbinding (gemeten), waardoor tokens en eerste aanvragen 5-6 s duurden.
    Nu: één SSLContext, één keer gevuld via cadata (~20 ms), gedeeld door alle verbindingen. Controle blijft gelijk
    (dezelfde certifi-certificaten, CERT_REQUIRED, hostnaamcontrole)."""
    import ssl
    try:
        import certifi
        with open(certifi.where(), encoding='ascii') as f:
            ctx = ssl.create_default_context(cadata=f.read())
    except Exception as e:   # geen certifi: gewoon het standaardgedrag van requests houden
        log.info('Snelle TLS niet actief: %s', e)
        return
    oud_init, oud_verify = HTTPAdapter.init_poolmanager, HTTPAdapter.cert_verify

    def init_poolmanager(self, *a, **kw):
        kw.setdefault('ssl_context', ctx)
        return oud_init(self, *a, **kw)

    def cert_verify(self, conn, url, verify, cert):
        oud_verify(self, conn, url, verify, cert)
        if verify is True and url.lower().startswith('https'):
            conn.ca_certs = None       # niet opnieuw inlezen: de gedeelde context bevat de certificaten al
            conn.ca_cert_dir = None

    HTTPAdapter.init_poolmanager, HTTPAdapter.cert_verify = init_poolmanager, cert_verify


_tls_snel()
TRAAG_MS = 1500   # aanvragen die langer duren komen in het logboek (om knelpunten te vinden)

# Twee werkpools: POOL voor wat de beheerder nu doet (klikken, schermen), ACHTER_POOL voor alles op de achtergrond
# (voorladen, vooraf openen, live verversen, klantenoverzicht). Zo hoeft een klik nooit te wachten op achtergrondwerk.
# Ruim bemeten: het meeste werk is wachten op Microsoft (I/O), threads zijn goedkoop.
POOL = ThreadPoolExecutor(max_workers=64, thread_name_prefix='ms')
ACHTER_POOL = ThreadPoolExecutor(max_workers=48, thread_name_prefix='achter')


class ApiFout(Exception):
    def __init__(self, tekst: str, status: int = 0):
        super().__init__(tekst)
        self.status = status


_SESSIES: dict[bool, requests.Session] = {}
_sessie_lock = threading.Lock()
_LOKAAL = threading.local()


@contextmanager
def achtergrond():
    """Aanvragen binnen dit blok (voorladen, rechtenkaart e.d.) gebruiken eigen verbindingen. Zo hoeft een klik van de
    beheerder nooit te wachten tot het voorladen op de achtergrond een verbinding vrijgeeft."""
    oud = getattr(_LOKAAL, 'achter', False)
    _LOKAAL.achter = True
    try:
        yield
    finally:
        _LOKAAL.achter = oud


def achtergrond_fn(fn):
    """Functie die altijd met de achtergrondverbindingen draait (voor threads en werkpools van lange klussen)."""
    def f(*a, **k):
        with achtergrond():
            return fn(*a, **k)
    return f


def is_achtergrond() -> bool:
    return bool(getattr(_LOKAAL, 'achter', False))


def _sessie(achter: bool | None = None) -> requests.Session:
    """Gedeelde HTTP-sessies voor alle klanten: verbindingen (TLS) worden hergebruikt.
    Een nieuwe TLS-verbinding naar Microsoft kost al snel 150-400 ms; nu gebeurt dat één keer.
    Twee aparte sets verbindingen: voorgrond (wat de beheerder doet, 10 per dienst) en achtergrond (voorladen, klussen, 6 per dienst)."""
    achter = is_achtergrond() if achter is None else achter
    with _sessie_lock:
        if achter not in _SESSIES:
            s = requests.Session()
            s.headers['User-Agent'] = 'M365Beheer/2.2'
            s.headers['Accept-Encoding'] = 'gzip, deflate'
            # Maximaal 10 verbindingen per Microsoft-dienst, die steeds hergebruikt worden (pool_block: extra aanvragen
            # wachten op een vrije verbinding in plaats van een nieuwe te openen). Beveiligingssoftware (bijv. Datto AV)
            # vertraagt of blokkeert een programma dat veel verbindingen tegelijk opent (WinError 10013).
            # Bij een (tijdelijk) geweigerde verbinding: tot 4 keer opnieuw, met oplopende pauze.
            n = 6 if achter else 10
            ad = HTTPAdapter(pool_connections=10, pool_maxsize=n, pool_block=True,
                             max_retries=Retry(total=4, connect=4, read=0, backoff_factor=1.0, allowed_methods=False, status_forcelist=()))
            s.mount('https://', ad)
            _SESSIES[achter] = s
        return _SESSIES[achter]


VERBINDING_FOUT = ('Er kon geen verbinding met Microsoft gemaakt worden. Waarschijnlijk blokkeert beveiligingssoftware op deze '
                   'computer (bijv. Datto AV) het programma. Voeg "Microsoft 365 beheer.exe" toe als uitzondering in de virusscanner, '
                   'of probeer het over een minuut opnieuw.')


def _verstuur(s: requests.Session, methode: str, url: str, **kw) -> requests.Response:
    """Aanvraag versturen; een geweigerde verbinding (bijv. WinError 10013 door een virusscanner) wordt een duidelijke melding."""
    for poging in range(3):
        try:
            # Bewust per aanvraag de juiste sessie kiezen (voorgrond of achtergrond)
            if s in _SESSIES.values():
                s = _sessie()
            return s.request(methode, url, **kw)
        except (requests.exceptions.ContentDecodingError, requests.exceptions.ChunkedEncodingError) as e:
            # Af en toe stuurt Microsoft een afgebroken/kapot antwoord: gewoon opnieuw vragen in plaats van een foutmelding
            log.info('Kapot antwoord van Microsoft (%s), poging %d: %s', url.split('?')[0][:100], poging + 1, str(e)[:120])
            veilig = methode == 'GET' or str((kw.get('headers') or {}).get('X-CmdletName', '')).startswith('Get-')
            if not veilig:   # een wijziging niet dubbel uitvoeren
                raise ApiFout('Microsoft gaf een onvolledig antwoord op deze wijziging. Controleer of hij is doorgevoerd (vernieuwen) en probeer het zo nodig opnieuw.') from None
            if poging == 2:
                raise ApiFout('Microsoft gaf een onvolledig antwoord. Probeer het opnieuw.') from None
            time.sleep(0.5 * (poging + 1))
        except requests.exceptions.ConnectionError as e:
            log.warning('Verbinding mislukt (%s): %s', url.split('?')[0][:100], str(e)[-160:])
            if '10013' in str(e) or 'Permission' in str(e):
                raise ApiFout(VERBINDING_FOUT) from None
            raise ApiFout('Geen verbinding met Microsoft. Controleer de internetverbinding en probeer het opnieuw.') from None
    raise ApiFout('Microsoft gaf geen antwoord. Probeer het opnieuw.')


def _meet(soort: str, wat: str, begin: float) -> None:
    ms = (time.perf_counter() - begin) * 1000
    if ms > TRAAG_MS:
        log.info('Traag: %s %s %.0f ms', soort, wat[:140], ms)


def parallel(taken: dict[str, Callable[[], Any]]) -> dict[str, Any]:
    """Meerdere aanvragen tegelijk uitvoeren. Fouten komen terug als ApiFout-object (niet opgegooid)."""
    achter = is_achtergrond()

    def met_stand(fn):   # achtergrondstand meegeven aan de werkthreads
        if not achter:
            return fn

        def f():
            with achtergrond():
                return fn()
        return f
    pool = ACHTER_POOL if achter else POOL
    fut = {k: pool.submit(met_stand(fn)) for k, fn in taken.items()}
    uit: dict[str, Any] = {}
    for k, f in fut.items():
        try:
            uit[k] = f.result()
        except Exception as e:  # noqa: BLE001
            uit[k] = e if isinstance(e, ApiFout) else ApiFout(str(e))
    return uit


def _wacht(r: requests.Response, poging: int) -> bool:
    if r.status_code in (429, 503, 504) and poging < 5:
        try:
            sec = float(r.headers.get('Retry-After', '0'))
        except ValueError:
            sec = 0
        time.sleep(min(max(sec, 2 ** poging), 30))
        return True
    return False


class Graph:
    def __init__(self, token: Callable[[], str]):
        self._token = token
        self.s = _sessie()

    def req(self, method: str, path: str, body: Any = None, headers: dict | None = None) -> Any:
        url = path if path.startswith('http') else GB + path
        begin = time.perf_counter()
        for poging in range(6):
            tb = time.perf_counter()
            tok = self._token()
            if (time.perf_counter() - tb) * 1000 > TRAAG_MS:
                log.info('Traag: token voor Graph %.0f ms', (time.perf_counter() - tb) * 1000)
            h = {'Authorization': 'Bearer ' + tok, 'ConsistencyLevel': 'eventual'}
            if headers:
                h.update(headers)
            r = _verstuur(self.s, method, url, json=body, headers=h, timeout=120)
            if _wacht(r, poging):
                continue
            break
        _meet('Graph', f'{method} {url.replace(GB, "")}', begin)
        if r.status_code >= 400:
            try:
                e = r.json().get('error', {})
                tekst = e.get('message') or e.get('code') or r.text
            except ValueError:
                tekst = r.text or r.reason
            raise ApiFout(tekst, r.status_code)
        if r.status_code == 204 or not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return {}

    def get(self, path: str) -> Any:
        return self.req('GET', path)

    def post(self, path: str, body: Any = None) -> Any:
        return self.req('POST', path, body if body is not None else {})

    def patch(self, path: str, body: Any) -> Any:
        return self.req('PATCH', path, body)

    def delete(self, path: str) -> Any:
        return self.req('DELETE', path)

    def all(self, path: str) -> list:
        uit: list = []
        url: str | None = path
        while url:
            r = self.get(url)
            uit.extend(r.get('value', []))
            url = r.get('@odata.nextLink')
        return uit

    def all_of(self, *paden: str) -> list:
        """Probeert het eerste pad; geeft Graph een 400 (bijv. filter niet ondersteund), dan het volgende."""
        for i, p in enumerate(paden):
            try:
                return self.all(p)
            except ApiFout as e:
                if e.status != 400 or i == len(paden) - 1:
                    raise
        return []


def _exo_fout(r: requests.Response) -> str:
    try:
        j = r.json()
        e = j.get('error', {})
        tekst = ''
        for d in e.get('details') or []:
            tekst = d.get('message') or tekst
        tekst = tekst or e.get('message') or r.text
    except ValueError:
        tekst = r.text or r.reason
    # Exchange plakt er vaak technische delen voor: "|Microsoft.Exchange...|Echte melding"
    if '|' in tekst:
        tekst = tekst.split('|')[-1]
    return tekst.strip() or f'Exchange-fout ({r.status_code})'


class _Null:
    """Expliciet $null meegeven aan een cmdlet (None-parameters worden namelijk weggelaten)."""


NULL = _Null()


class Exchange:
    """Exchange Online-cmdlets via de REST-API die ook de ExchangeOnlineManagement-module gebruikt."""

    def __init__(self, tenant_id: str, token: Callable[[], str], anker_domein: str = ''):
        self.url = f'https://outlook.office365.com/adminapi/beta/{tenant_id}/InvokeCommand'
        self.tenant_id = tenant_id
        self._token = token
        self.anker_domein = anker_domein
        self.s = _sessie()

    def run(self, cmdlet: str, **params: Any) -> list[dict]:
        body = {'CmdletInput': {'CmdletName': cmdlet, 'Parameters': {k: (None if v is NULL else v) for k, v in params.items() if v is not None}}}
        uit: list[dict] = []
        url: str | None = self.url
        while url:
            for poging in range(6):
                h = {'Authorization': 'Bearer ' + self._token(), 'Content-Type': 'application/json',
                     'X-CmdletName': cmdlet, 'X-ClientApplication': 'ExoManagementModule',
                     'Prefer': 'odata.maxpagesize=1000'}
                if self.anker_domein:
                    h['X-AnchorMailbox'] = f'UPN:SystemMailbox{{bb558c35-97f1-4cb9-8ff7-d53741dc928c}}@{self.anker_domein}'
                begin = time.perf_counter()
                r = _verstuur(self.s, "POST", url, json=body, headers=h, timeout=180)
                _meet('Exchange', cmdlet, begin)
                if _wacht(r, poging):
                    continue
                break
            if r.status_code >= 400:
                raise ApiFout(_exo_fout(r), r.status_code)
            if not r.content:
                break
            j = r.json()
            v = j.get('value')
            if isinstance(v, list):
                uit.extend(v)
            elif j:
                uit.append(j)
            url = j.get('@odata.nextLink')
        return uit

    def een(self, cmdlet: str, **params: Any) -> dict | None:
        r = self.run(cmdlet, **params)
        return r[0] if r else None


def hashtabel(**kw: Any) -> dict:
    """Parameter van PowerShell-type hashtable (bijv. EmailAddresses @{Add=...})."""
    return {'@odata.type': '#Exchange.GenericHashTable', **kw}
