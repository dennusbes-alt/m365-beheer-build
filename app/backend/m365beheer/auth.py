"""Inloggen bij Microsoft (partner-account via GDAP) met de eigen app-registratie "Justdata M365 Beheer".

- Er wordt NIETS op schijf bewaard: de tokencache leeft alleen in het geheugen van dit proces.
- Inloggen gebeurt in de gewone browser (geen WAM, geen device code), één keer: Graph, Exchange en
  Partner Center gebruiken dezelfde app, dus de tokens voor de andere diensten komen stil binnen.
- Klant-tenants: tokens stil via GDAP. Is de app in een klant-tenant nog niet toegestaan (AADSTS90099 e.d.),
  dan geeft token() KoppelingNodig; de app regelt de toestemming dan zelf via Partner Center (koppeling.py).
  Er wordt in dat geval nooit een browserlogin geopend, dus de Microsoft-foutpagina verschijnt niet.
"""
from __future__ import annotations

import threading
import time

import msal

from .clients import _sessie

try:
    from .appid import CLIENT_ID, PARTNER_TENANT   # aangemaakt door opzetten_app.py
except ImportError:  # pragma: no cover - zonder app-registratie kan de app niet werken
    CLIENT_ID, PARTNER_TENANT = '', ''

AUTHORITY = 'https://login.microsoftonline.com/'

# Gedelegeerde Graph-rechten van de app (ook gebruikt door opzetten_app.py en de Partner Center-koppeling)
GRAPH_RECHTEN = [
    'User.ReadWrite.All', 'Organization.Read.All', 'Domain.Read.All', 'Group.ReadWrite.All', 'GroupMember.ReadWrite.All',
    'Directory.Read.All', 'Directory.AccessAsUser.All', 'UserAuthenticationMethod.ReadWrite.All', 'AuditLog.Read.All',
    'DeviceManagementManagedDevices.ReadWrite.All', 'DeviceManagementManagedDevices.PrivilegedOperations.All',
    'DeviceManagementServiceConfig.ReadWrite.All', 'BitlockerKey.Read.All',
    # v2.4: OneDrive (opslag en provisionen), SharePoint-sites, authenticatiebeleid
    'Files.Read.All', 'Sites.Read.All', 'Policy.Read.All', 'Policy.ReadWrite.AuthenticationMethod', 'Policy.ReadWrite.Authorization',
    # v2.9: servicestatus en berichtencentrum
    'ServiceHealth.Read.All', 'ServiceMessage.Read.All',
    # v2.10: huisstijl van de aanmeldpagina
    'OrganizationalBranding.ReadWrite.All',
    # v2.12: Secure Score (compliance)
    'SecurityEvents.Read.All',
    # v2.13: gevoeligheidslabels (Copilot-readiness en NEN 7510)
    'InformationProtectionPolicy.Read',
    # v2.18: Intune-beheer (configuratieprofielen, apps, inschrijving, automatische MDM-inschrijving)
    'DeviceManagementConfiguration.ReadWrite.All', 'DeviceManagementApps.ReadWrite.All', 'Policy.ReadWrite.MobilityManagement',
    # v2.21: voorwaardelijke toegang (beleid en benoemde locaties)
    'Policy.ReadWrite.ConditionalAccess',
]
GRAPH_SCOPES = ['https://graph.microsoft.com/' + r for r in GRAPH_RECHTEN]   # voor opzetten_app.py
SHAREPOINT_RECHTEN = ['AllSites.FullControl']   # SharePoint-beheer (sites, delen) via de SharePoint-beheer-API

# Met .default krijg je precies de rechten waarvoor toestemming is gegeven (in Justdata of via de koppeling)
SCOPES = {
    'graph': ['https://graph.microsoft.com/.default'],
    'partner': ['https://graph.microsoft.com/.default'],
    'exo': ['https://outlook.office365.com/.default'],
    'pc': ['https://api.partnercenter.microsoft.com/.default'],
}

# Foutcodes die betekenen: de app is in deze klant-tenant nog niet toegestaan -> automatisch koppelen
KOPPELING_CODES = ('AADSTS90099', 'AADSTS650052', 'AADSTS700016', 'AADSTS65001', 'AADSTS90094', 'AADSTS500011')

SUCCES_HTML = ('<html><head><meta charset="utf-8"><title>Ingelogd</title></head>'
               '<body style="font-family:Segoe UI,Helvetica,sans-serif;background:#f2f6f9;color:#003f6b;text-align:center;padding-top:80px">'
               '<h2>Je bent ingelogd</h2><p>Je kunt dit tabblad sluiten en terug gaan naar Microsoft 365 beheer.</p></body></html>')
FOUT_HTML = ('<html><head><meta charset="utf-8"><title>Inloggen mislukt</title></head>'
             '<body style="font-family:Segoe UI,Helvetica,sans-serif;background:#fcebe9;color:#c0392b;text-align:center;padding-top:80px">'
             '<h2>Inloggen is niet gelukt</h2><p>$error: $error_description</p><p>Ga terug naar Microsoft 365 beheer en probeer het opnieuw.</p></body></html>')


class LoginFout(Exception):
    pass


class KoppelingNodig(LoginFout):
    """De app is in deze klant-tenant nog niet toegestaan; koppeling.py lost dit automatisch op."""


def _fout(res: dict) -> str:
    code = res.get('error', '')
    tekst = (res.get('error_description') or code or 'Onbekende fout').split('\r\n')[0]
    if 'AADSTS50020' in tekst or 'AADSTS50177' in tekst or 'AADSTS50076' in tekst and 'tenant' in tekst.lower():
        return 'Je account heeft geen toegang tot deze klant. Controleer of er een actieve GDAP-relatie is met de juiste rollen.'
    if code == 'access_denied' or 'AADSTS65004' in tekst:
        return 'Inloggen is geannuleerd.'
    return tekst


def _koppeling_nodig(res: dict | None) -> bool:
    tekst = ' '.join(str((res or {}).get(k) or '') for k in ('error_description', 'error_codes', 'suberror'))
    return any(c in tekst or c[7:] in tekst for c in KOPPELING_CODES)


class Auth:
    def __init__(self) -> None:
        self.cache = msal.TokenCache()          # alleen in het geheugen
        self.lock = threading.RLock()
        self.login_lock = threading.Lock()      # maar een browserlogin tegelijk
        self._apps: dict[tuple[str, str], msal.PublicClientApplication] = {}
        self.account: dict | None = None        # MSAL-account van de beheerder
        self.home_tenant: str = ''
        self._memo: dict[tuple[str, str], tuple[str, float]] = {}   # (soort, tenant) -> (token, verloopt)
        self._http_cache: dict = {}                                  # MSAL-discovery, gedeeld door alle klanten
        self._token_sloten: dict[tuple[str, str], threading.Lock] = {}
        self._app_sloten: dict[tuple[str, str], threading.Lock] = {}
        threading.Thread(target=self._voorverwarmen, daemon=True, name='auth-warm').start()

    def _voorverwarmen(self) -> None:
        """Bij het opstarten (vóór de klik op Inloggen): MSAL-discovery en de eerste TLS-verbindingen met Microsoft
        alvast opzetten. Kost anders ~3 s bij het inloggen. Er wordt niets opgeslagen."""
        try:
            if CLIENT_ID:
                self._app(CLIENT_ID, 'organizations')
            s = _sessie(False)
            for url in ('https://graph.microsoft.com/v1.0/', 'https://outlook.office365.com/'):
                try:
                    s.head(url, timeout=10)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001 - alleen een versnelling
            pass

    # ---------- intern ----------
    def _app(self, client: str, tenant: str) -> msal.PublicClientApplication:
        key = (client, tenant)
        app = self._apps.get(key)
        if app is not None:
            return app
        # Aanmaken doet netwerkverkeer (discovery). Dat gebeurt NIET onder de algemene lock: anders wacht elk
        # token van elke klant op deze ene klant (oorzaak van trage eerste aanvragen na het inloggen).
        with self.lock:
            slot = self._app_sloten.setdefault(key, threading.Lock())
        with slot:
            app = self._apps.get(key)
            if app is None:
                # http_cache: discovery-antwoorden van Microsoft één keer ophalen voor alle klanten (alleen in het geheugen).
                # http_client: dezelfde verbindingspool als Graph/Exchange (TLS-verbindingen hergebruiken).
                app = msal.PublicClientApplication(
                    client, authority=AUTHORITY + tenant, token_cache=self.cache,
                    http_cache=self._http_cache, http_client=_sessie(False))
                self._apps[key] = app
            return app

    def _interactief(self, client: str, tenant: str, scopes: list[str], prompt: str | None = None) -> dict:
        app = self._app(client, tenant)
        hint = (self.account or {}).get('username')
        with self.login_lock:
            kw = dict(scopes=scopes, prompt=prompt, login_hint=hint if not prompt else None, timeout=300)
            try:
                res = app.acquire_token_interactive(success_template=SUCCES_HTML, error_template=FOUT_HTML, **kw)
            except TypeError:
                res = app.acquire_token_interactive(**kw)
        if 'access_token' not in res:
            raise LoginFout(_fout(res))
        return res

    def _account_voor(self, app: msal.PublicClientApplication) -> dict | None:
        if not self.account:
            return None
        for a in app.get_accounts():
            if a.get('home_account_id') == self.account.get('home_account_id'):
                return a
        return None

    # ---------- publiek ----------
    @property
    def ingelogd(self) -> bool:
        return self.account is not None

    def login(self) -> dict:
        """Eén keer inloggen in de browser (Justdata-account). Exchange en Partner Center komen daarna stil binnen."""
        if not CLIENT_ID:
            raise LoginFout('De app-registratie ontbreekt in deze versie (appid.py). Neem contact op met de beheerder.')
        res = self._interactief(CLIENT_ID, 'organizations', SCOPES['graph'], prompt='select_account')
        claims = res.get('id_token_claims') or {}
        app = self._app(CLIENT_ID, 'organizations')
        accounts = [a for a in app.get_accounts() if a.get('home_account_id', '').startswith(claims.get('oid', '~'))]
        self.account = accounts[0] if accounts else (app.get_accounts() or [None])[0]
        self.home_tenant = claims.get('tid', '')
        return {'name': claims.get('name', ''), 'upn': claims.get('preferred_username', ''), 'tid': self.home_tenant}

    def login_exchange(self) -> None:
        """Exchange-token voor de eigen tenant: stil via dezelfde app (geen tweede browserlogin)."""
        self.token(self.home_tenant, 'exo', interactief=True)

    def token(self, tenant: str, soort: str = 'graph', interactief: bool = True) -> str:
        if not self.account:
            raise LoginFout('Je bent niet ingelogd.')
        # 'sp:https://contoso-admin.sharepoint.com' = token voor de SharePoint-beheer-API van die klant
        client, scopes = CLIENT_ID, (SCOPES[soort] if not soort.startswith('sp:') else [soort[3:] + '/.default'])
        eigen = tenant in (self.home_tenant, 'organizations')
        sleutel = (soort, tenant)
        m = self._memo.get(sleutel)
        if m and m[1] - time.time() > 300:   # nog minimaal 5 minuten geldig: geen MSAL nodig
            return m[0]
        with self.lock:
            slot = self._token_sloten.setdefault(sleutel, threading.Lock())
        with slot:   # parallelle aanvragen voor dezelfde klant halen samen één token op
            m = self._memo.get(sleutel)
            if m and m[1] - time.time() > 300:
                return m[0]
            app = self._app(client, tenant)
            acc = self._account_voor(app)
            res = app.acquire_token_silent_with_error(scopes, account=acc) if acc else None
            if not (res and 'access_token' in res):
                if not eigen and _koppeling_nodig(res):
                    # App nog niet toegestaan bij deze klant: NIET de browser openen (dan toont Microsoft
                    # de foutpagina AADSTS90099), maar laten koppelen via Partner Center.
                    raise KoppelingNodig(_fout(res or {}))
                if not interactief:
                    raise LoginFout(_fout(res or {'error_description': 'Geen geldig token.'}))
                res = self._interactief(client, tenant, scopes)
            self._memo[sleutel] = (res['access_token'], time.time() + int(res.get('expires_in') or 600))
            return res['access_token']

    # ---------- account van de klant zelf (alleen waar GDAP niet werkt, bijv. inhoud van SharePoint-sites) ----------
    # Microsoft laat GDAP-accounts niet in de inhoud van SharePoint-sites (ook niet als sitebeheerder). Daarvoor logt de
    # beheerder één keer per sessie in met een beheeraccount uit de tenant van de klant. Alleen in het geheugen.
    def klant_account(self, tenant: str) -> str:
        return ((getattr(self, '_klantacc', {}) or {}).get(tenant) or {}).get('username', '')

    def login_klant(self, tenant: str, host: str) -> str:
        if not CLIENT_ID:
            raise LoginFout('De app-registratie ontbreekt in deze versie.')
        scopes = [host.rstrip('/') + '/.default']
        res = self._interactief(CLIENT_ID, tenant, scopes, prompt='select_account')
        claims = res.get('id_token_claims') or {}
        if str(claims.get('tid', '')).lower() != tenant.lower():
            raise LoginFout('Dit account hoort niet bij deze klant. Log in met een beheeraccount uit de tenant van de klant zelf '
                            '(bijv. beheer@klant.onmicrosoft.com), niet met je Justdata-account.')
        app = self._app(CLIENT_ID, tenant)
        acc = next((a for a in app.get_accounts() if a.get('home_account_id', '').startswith(claims.get('oid', '~'))), None)
        with self.lock:
            if not hasattr(self, '_klantacc'):
                self._klantacc = {}
            self._klantacc[tenant] = acc or {'username': claims.get('preferred_username', ''), 'home_account_id': ''}
            self._memo[('klant:sp:' + host.rstrip('/'), tenant)] = (res['access_token'], time.time() + int(res.get('expires_in') or 600))
        return claims.get('preferred_username', '')

    def token_klant(self, tenant: str, host: str) -> str | None:
        """Token voor een SharePoint-site met het klantaccount (of None als er voor deze klant niet is ingelogd)."""
        acc = (getattr(self, '_klantacc', {}) or {}).get(tenant)
        if not acc:
            return None
        sleutel = ('klant:sp:' + host.rstrip('/'), tenant)
        m = self._memo.get(sleutel)
        if m and m[1] - time.time() > 300:
            return m[0]
        app = self._app(CLIENT_ID, tenant)
        echt = next((a for a in app.get_accounts() if a.get('home_account_id') == acc.get('home_account_id')), None)
        res = app.acquire_token_silent_with_error([host.rstrip('/') + '/.default'], account=echt) if echt else None
        if not (res and 'access_token' in res):
            return None
        self._memo[sleutel] = (res['access_token'], time.time() + int(res.get('expires_in') or 600))
        return res['access_token']

    def afmelden_klant(self, tenant: str) -> None:
        with self.lock:
            (getattr(self, '_klantacc', {}) or {}).pop(tenant, None)
            for k in [k for k in self._memo if k[1] == tenant and k[0].startswith('klant:')]:
                self._memo.pop(k, None)

    def vergeet(self, tenant: str) -> None:
        """Na het koppelen: opgeslagen (mislukte) tokenpogingen voor deze klant wissen."""
        with self.lock:
            for k in [k for k in self._memo if k[1] == tenant]:
                self._memo.pop(k, None)
            # Ook de toegangstokens in de MSAL-cache: die kunnen nog van vóór het koppelen zijn (verkeerde rechten)
            try:
                for at in list(self.cache.find(msal.TokenCache.CredentialType.ACCESS_TOKEN, query={'realm': tenant})):
                    self.cache.remove_at(at)
            except Exception:
                pass

    def afmelden(self) -> None:
        """Alles uit het geheugen wissen. Bewust zonder netwerkverkeer: afmelden moet altijd lukken."""
        with self.lock:
            self._apps.clear()
            self._memo.clear()
            self._token_sloten.clear()
            self._app_sloten.clear()
            self.cache = msal.TokenCache()
            self._klantacc = {}
            self.account = None
            self.home_tenant = ''
