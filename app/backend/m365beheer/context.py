"""Toestand van de app: ingelogde beheerder, gekozen klant (tenant) en caches per klant."""
from __future__ import annotations

import logging
import threading
import time

from datetime import datetime
from typing import Any, Callable

from .auth import Auth, KoppelingNodig
from .clients import ACHTER_POOL, POOL, ApiFout, Exchange, Graph, achtergrond, achtergrond_fn, parallel


# Gegevens zijn net als bij PowerShell altijd actueel: een lijst wordt hooguit zo lang hergebruikt (in seconden).
# Dat is genoeg om dubbele aanvragen te voorkomen en het eerste scherm na het openen van een klant direct te vullen.
VERS = 30
VERS_ACHTER = 300   # zolang na het verlopen mag het bekende antwoord nog direct getoond worden (en wordt er op de achtergrond ververst)


class Tenant:
    def __init__(self, auth: Auth, tid: str, naam: str = '', stil: bool = False):
        self.id = tid
        self.naam = naam
        self.stil = stil   # True = op de achtergrond openen: nooit een browserlogin starten
        self.graph = Graph(lambda: auth.token(tid, 'graph', interactief=not self.stil))
        self._auth = auth
        self.exo: Exchange | None = None
        self.exo_fout = ''
        self.exo_klaar = threading.Event()   # Exchange wordt op de achtergrond gecontroleerd
        self.gekoppeld = False               # True = de app is zojuist automatisch aan deze klant gekoppeld
        self.rechten_status: str | None = None   # None = nog niet gecontroleerd, 'bezig', 'compleet', 'aangevuld'
        self.rechten_klaar = threading.Event()
        self.na_exo: Callable[[], None] | None = None
        self.domeinen: list[dict] = []
        self.standaard_domein = ''
        self.lock = threading.RLock()
        self.agenda_cache: dict[str, str] = {}
        self._cache: dict[str, tuple[float, Any]] = {}
        self._sloten: dict[str, threading.Lock] = {}
        self._gen: dict[str, int] = {}   # per lijst: verhoogd bij elke wijziging (zie markeer)
        self.voortgang: Callable[[str], None] = lambda tekst: None   # stap tijdens het openen (zichtbaar in de interface)

    # ---------- cache in het geheugen (per klant, met verlooptijd) ----------
    def cache(self, sleutel: str, fn: Callable[[], Any], ttl: float = 300, vers: bool = False) -> Any:
        """Geeft de gecachte waarde terug, of haalt hem op. Gelijktijdige verzoeken wachten op één ophaalactie."""
        with self.lock:
            slot = self._sloten.setdefault(sleutel, threading.Lock())
        if not vers:
            item = self._cache.get(sleutel)
            if item and time.time() - item[0] < ttl:
                return item[1]
            # Net verlopen (tot 5 minuten): direct het bekende antwoord geven en op de achtergrond verversen.
            # Een wijziging wist de cache (weg), en 'Vernieuwen' haalt altijd live op: de beheerder wacht nooit onnodig.
            if item and time.time() - item[0] < ttl + VERS_ACHTER:
                if slot.acquire(blocking=False):
                    gen = self._gen.get(sleutel, 0)

                    def ververs() -> None:
                        try:
                            waarde = fn()
                            if self._gen.get(sleutel, 0) == gen:   # tussendoor gewijzigd? dan niet het oude beeld terugzetten
                                self._cache[sleutel] = (time.time(), waarde)
                        except Exception:  # noqa: BLE001 - de volgende vraag probeert het gewoon opnieuw
                            pass
                        finally:
                            slot.release()
                    try:
                        ACHTER_POOL.submit(achtergrond_fn(ververs))
                    except RuntimeError:   # pool gesloten (afsluiten)
                        slot.release()
                return item[1]
        begin = time.time()
        with slot:
            item = self._cache.get(sleutel)
            # Heeft een ander verzoek hem net opgehaald terwijl wij wachtten? Dan die gebruiken.
            if item and (item[0] >= begin or (not vers and time.time() - item[0] < ttl)):
                return item[1]
            waarde = fn()
            self._cache[sleutel] = (time.time(), waarde)
            return waarde

    def weg(self, *sleutels: str) -> None:
        """Cache ongeldig maken na een wijziging."""
        for s in sleutels:
            self._cache.pop(s, None)
            self.markeer(s)

    def markeer(self, sleutel: str) -> None:
        """Er is iets gewijzigd aan deze lijst: een lopende achtergrondverversing mag haar (oudere) resultaat niet opslaan."""
        self._gen[sleutel] = self._gen.get(sleutel, 0) + 1

    @property
    def exo_status(self) -> bool | None:
        """True = verbonden, False = niet beschikbaar, None = wordt nog gecontroleerd."""
        if not self.exo_klaar.is_set():
            return None
        return self.exo is not None

    def openen(self) -> None:
        """Klant openen. Alleen de Graph-basis (naam en domeinen, tegelijk opgehaald) wacht; Exchange wordt
        op de achtergrond gecontroleerd. Een actie die Exchange nodig heeft wacht daar vanzelf op."""
        self._token_vooraf('graph')
        r = parallel({
            'org': lambda: self.graph.get('/organization?$select=id,displayName'),
            'dom': lambda: self.graph.all('/domains?$select=id,isDefault,isInitial,isVerified'),
        })
        if isinstance(r['org'], Exception):
            raise r['org']   # geen Graph-toegang: deze klant kan niet geopend worden
        org = (r['org'].get('value') or [{}])[0]
        self.naam = org.get('displayName') or self.naam or self.id
        doms = r['dom'] if isinstance(r['dom'], list) else []
        self.domeinen = sorted(
            [{'id': d['id'], 'def': bool(d.get('isDefault')), 'initial': bool(d.get('isInitial'))} for d in doms if d.get('isVerified')],
            key=lambda d: (not d['def'], d['id']))
        self.standaard_domein = next((d['id'] for d in self.domeinen if d['def']), self.domeinen[0]['id'] if self.domeinen else '')
        threading.Thread(target=self._exo_controleren, daemon=True, name=f'exo-{self.id[:8]}').start()
        if not self.stil:
            self.rechten_starten()

    def rechten_starten(self) -> None:
        """Eenmalig (op de achtergrond) controleren of de koppeling alle rechten van deze app-versie heeft.
        Wordt ook gestart als een stil voorgeopende klant echt gekozen wordt (anders werd dit nooit gedaan)."""
        if self.id == self._auth.home_tenant:
            self.rechten_status = 'compleet'
            self.rechten_klaar.set()
            return
        with self.lock:
            if self.rechten_status is not None:
                return
            self.rechten_status = 'bezig'
        threading.Thread(target=achtergrond_fn(self._rechten_controleren), daemon=True, name=f'rechten-{self.id[:8]}').start()

    def rechten_nu(self, max_sec: float = 90) -> str | None:
        """Rechtencontrole (opnieuw) doen en erop wachten. Geeft 'compleet', 'aangevuld' of None (niet gelukt)."""
        with self.lock:
            if self.rechten_status != 'bezig':
                self.rechten_status = None
                self.rechten_klaar.clear()
        self.rechten_starten()
        self.rechten_klaar.wait(max_sec)
        return self.rechten_status if self.rechten_status in ('compleet', 'aangevuld') else None

    def _rechten_controleren(self) -> None:
        """Nieuwe app-versies kunnen rechten toevoegen (bijv. Secure Score): bestaande koppelingen automatisch aanvullen."""
        from .koppeling import koppelen, rechten_compleet
        log = logging.getLogger('m365beheer')
        try:
            if rechten_compleet(self.graph):
                self.rechten_status = 'compleet'
            else:
                # Partner Center vervangt de koppeling (verwijderen + opnieuw): wachten tot Graph én Exchange weer werken
                koppelen(self._auth, self.id)
                self.gekoppeld = True
                self.rechten_status = 'aangevuld'
                log.info('Koppeling aangevuld met nieuwe rechten voor %s', self.naam)
                # Exchange-controle liep mogelijk tijdens het vervangen en mislukte: nu opnieuw (schermen wachten daarop)
                self.exo_herstellen(wacht=True)
        except Exception as e:  # noqa: BLE001 - niet fataal; de functie die het recht nodig heeft meldt het dan
            self.rechten_status = None   # later opnieuw proberen
            log.info('Rechten controleren bij %s niet gelukt: %s', self.naam, e)
        finally:
            self.rechten_klaar.set()

    def sp_admin(self) -> str:
        """Adres van de SharePoint-beheer-API van deze klant, bijv. https://contoso-admin.sharepoint.com."""
        if not getattr(self, '_sp_admin', ''):
            try:
                root = self.graph.get('/sites/root?$select=webUrl').get('webUrl', '')
                naam = root.split('//', 1)[1].split('.', 1)[0]
            except Exception:  # zonder Sites-recht: afleiden uit het onmicrosoft.com-domein
                naam = next((d['id'] for d in self.domeinen if d['initial']), '').split('.', 1)[0]
            if not naam:
                raise ApiFout('Het SharePoint-adres van deze klant is niet gevonden.')
            self._sp_admin = f'https://{naam}-admin.sharepoint.com'
        return self._sp_admin

    def sp_token(self) -> str:
        """Token voor de SharePoint-beheer-API; ontbreekt de toestemming, dan wordt de koppeling eerst aangevuld."""
        soort = 'sp:' + self.sp_admin()
        try:
            return self._auth.token(self.id, soort, interactief=False)
        except KoppelingNodig:
            from .koppeling import koppelen
            koppelen(self._auth, self.id)
            return self._auth.token(self.id, soort, interactief=False)

    def _token_vooraf(self, soort: str) -> None:
        """Token ophalen. Is de app bij deze klant nog niet toegestaan, dan automatisch koppelen (nooit in de
        stille achtergrondmodus: koppelen is een wijziging in de klant-tenant en gebeurt alleen als jij de klant kiest)."""
        try:
            self._auth.token(self.id, soort, interactief=not self.stil)
        except KoppelingNodig:
            if self.stil:
                raise
            from .gdap import GdapInfo, toegang_regelen
            from .koppeling import koppelen
            a = self._auth
            meld = self.voortgang
            info = GdapInfo(Graph(lambda: a.token(a.home_tenant, 'partner')))
            nieuw = toegang_regelen(info, self.id, meld)   # eerst GDAP-toewijzing (AdminAgents) indien nodig
            # Na een nieuwe toewijzing kan Partner Center even achterlopen: opnieuw proberen, maar met een harde grens
            eind = time.time() + (240 if nieuw else 120)
            poging = 0
            while True:
                poging += 1
                meld('App koppelen via Partner Center' + (f' (poging {poging})' if poging > 1 else '') + '...')
                try:
                    koppelen(a, self.id, meld=meld)
                    break
                except ApiFout as e:
                    if not nieuw or time.time() + 15 > eind or e.status not in (400, 403):
                        raise
                    meld(f'Partner Center kent de nieuwe GDAP-rechten nog niet; over 15 seconden opnieuw (poging {poging})...')
                    time.sleep(15)
            self.gekoppeld = True
            meld('Gegevens van de klant ophalen...')
            self._auth.token(self.id, soort, interactief=False)

    def _exo_controleren(self) -> None:
        stil = self.stil   # vastleggen: een achtergrondcontrole mag nooit een browserlogin openen
        try:
            anker = next((d['id'] for d in self.domeinen if d['initial']), self.standaard_domein)
            exo = Exchange(self.id, lambda: self._auth.token(self.id, 'exo', interactief=not stil), anker)
            # Al eens zelf gekoppeld in deze sessie: kort opnieuw proberen, anders ruim (koppelen + verwerken)
            eind = time.time() + (30 if getattr(self, '_exo_gekoppeld', False) else 150)
            zelf_gekoppeld = False
            for poging in range(30):
                try:
                    # Deze controle haalt meteen de geaccepteerde domeinen op; die worden hergebruikt (scherm Domeinen)
                    self._cache['accepted'] = (time.time(), exo.run('Get-AcceptedDomain'))
                    break
                except KoppelingNodig:
                    # Geen toestemming voor Exchange (AADSTS65001): koppeling wordt net vervangen (rechten aanvullen),
                    # loopt bij Microsoft achter, of mist Exchange. Nooit opgeven zonder herstelpoging.
                    if stil or time.time() > eind:
                        raise
                    if self.rechten_status == 'bezig':
                        self.rechten_klaar.wait(120)
                    elif (not zelf_gekoppeld and not getattr(self, '_exo_gekoppeld', False)
                          and self.rechten_status != 'aangevuld'):   # net aangevuld = alleen nog wachten op Microsoft
                        # Eén keer per klant per sessie zelf koppelen (Partner Center vervangt de koppeling)
                        from .koppeling import koppelen
                        zelf_gekoppeld = self._exo_gekoppeld = True
                        koppelen(self._auth, self.id, meld=self.voortgang)
                        self.gekoppeld = True
                    else:
                        time.sleep(5)
                    self._auth.vergeet(self.id)
                except ApiFout as e:
                    # Vlak na een nieuwe koppeling/toewijzing kent Exchange de rechten soms nog niet: verse tokens en opnieuw
                    if not self.gekoppeld or time.time() > eind or e.status not in (401, 403):
                        raise
                    time.sleep(10)
                    self._auth.vergeet(self.id)
            # Daarna mag Exchange (bij gebruik) wel om inloggen vragen als het token verloopt
            exo._token = lambda: self._auth.token(self.id, 'exo', interactief=not self.stil)
            self.exo, self.exo_fout = exo, ''
        except Exception as e:  # Exchange is optioneel: de rest werkt dan nog wel
            self.exo, self.exo_fout = None, str(e)
        finally:
            self.exo_klaar.set()
        if self.exo and self.na_exo:
            try:
                self.na_exo()
            except Exception:
                pass

    def wacht_op_exo(self, max_sec: float = 60) -> None:
        self.exo_klaar.wait(max_sec)

    def exo_herstellen(self, wacht: bool = False) -> None:
        """Mislukte Exchange-controle opnieuw doen (bijv. na stil voorgeopend, of terwijl de koppeling werd vervangen).
        Alleen als de vorige controle klaar en mislukt is; steeds minder vaak (20 s, 1, 2, 5 min, daarna elke 10 min),
        zodat een klant zonder Exchange geen belasting geeft."""
        with self.lock:
            n = getattr(self, '_exo_herstel_n', 0)
            pauze = (20, 60, 120, 300)[n] if n < 4 else 600
            if (self.stil or self.exo is not None or not self.exo_klaar.is_set()
                    or time.time() - getattr(self, '_exo_herstel_t', 0) < pauze):
                return
            self._exo_herstel_t = time.time()
            self._exo_herstel_n = n + 1
            self.exo_klaar.clear()
            self.exo_fout = ''
        if wacht:
            self._exo_controleren()
        else:
            threading.Thread(target=achtergrond_fn(self._exo_controleren), daemon=True, name=f'exo-{self.id[:8]}').start()

    def voorladen(self, taken: dict[str, Callable[[], Any]]) -> None:
        """Veelgebruikte lijsten alvast op de achtergrond ophalen, zodat het eerste scherm direct vol staat."""
        def run(k: str, fn: Callable[[], Any]) -> None:
            try:
                with achtergrond():
                    self.cache(k, fn)
            except Exception:
                pass
        for k, fn in taken.items():
            ACHTER_POOL.submit(run, k, fn)


class Activiteit:
    """Logboek van uitgevoerde acties in deze sessie (alleen in het geheugen)."""

    def __init__(self) -> None:
        self.regels: list[dict] = []
        self.lock = threading.Lock()

    def add(self, tenant: str, actie: str, tekst: str) -> None:
        with self.lock:
            self.regels.append({'t': datetime.now().strftime('%H:%M:%S'), 'tenant': tenant, 'action': actie, 'text': tekst})
            del self.regels[:-500]


class Staat:
    def __init__(self) -> None:
        self.auth = Auth()
        self.beheerder: dict = {}
        self.tenant: Tenant | None = None
        self.tenants: dict[str, Tenant] = {}
        self.klanten: list[dict] | None = None
        self.activiteit = Activiteit()
        self.lock = threading.RLock()
        self._open_sloten: dict[str, threading.Lock] = {}
        self.voortgang: dict[str, dict] = {}   # klant-ID -> {'tekst', 'begin'} terwijl die klant geopend wordt
        self.klanten_taak = None   # lopende ophaalactie van het klantenoverzicht (direct na inloggen gestart)

    def _slot(self, tid: str) -> threading.Lock:
        with self.lock:
            return self._open_sloten.setdefault(tid, threading.Lock())

    def kies(self, tid: str, naam: str = '') -> tuple[Tenant, bool]:
        """Klant openen. Een eerder (of op de achtergrond) geopende klant komt direct uit het geheugen."""
        with self._slot(tid):   # wacht eventueel op een lopende achtergrond-opening van dezelfde klant
            t = self.tenants.get(tid)
            nieuw = t is None
            if nieuw:
                t = Tenant(self.auth, tid, naam)
                v = self.voortgang[tid] = {'tekst': 'Verbinden...', 'begin': time.time()}
                t.voortgang = lambda tekst: v.update(tekst=tekst)
                try:
                    t.openen()
                finally:
                    self.voortgang.pop(tid, None)
                    t.voortgang = lambda tekst: None
                with self.lock:
                    self.tenants[tid] = t
        self.tenant = t
        t.rechten_starten()   # ook voor klanten die stil zijn voorgeopend (daar werd dit overgeslagen)
        t.exo_herstellen()    # Exchange eerder mislukt (stil voorgeopend, koppeling net vervangen): opnieuw op de achtergrond
        return t, nieuw

    def vooraf_openen(self, tids: list[str]) -> None:
        """Recente klanten alvast stil openen (alleen tokens, naam en domeinen), zodat wisselen direct gaat.
        Lukt dat niet zonder browserlogin, dan gebeurt er niets."""
        def een(tid: str) -> None:
            slot = self._slot(tid)
            if self.tenants.get(tid) or not slot.acquire(blocking=False):
                return
            try:
                if self.tenants.get(tid) or not self.auth.ingelogd:
                    return
                t = Tenant(self.auth, tid, stil=True)
                with achtergrond():
                    t.openen()
                t.stil = False   # vanaf nu mag een actie van de gebruiker wel om inloggen vragen
                with self.lock:
                    if self.auth.ingelogd:
                        self.tenants.setdefault(tid, t)
                # Ook de lijsten die je na het wisselen het eerst ziet alvast ophalen: dan staat het eerste scherm direct vol
                from .common import _gebruikers_ophalen, _groepen_ophalen, _licenties_ophalen
                g = Graph(lambda: self.auth.token(tid, 'graph', interactief=False))   # nooit een browserlogin vanaf de achtergrond
                t.voorladen({'users': lambda: _gebruikers_ophalen(g), 'skus': lambda: _licenties_ophalen(g), 'groepen': lambda: _groepen_ophalen(g)})
            except Exception:
                pass
            finally:
                slot.release()
        for tid in tids[:6]:
            ACHTER_POOL.submit(een, tid)

    def reset(self) -> None:
        with self.lock:
            self.auth.afmelden()
            self.beheerder = {}
            self.tenant = None
            self.tenants.clear()
            self.klanten = None
            self.klanten_taak = None


class Ctx:
    """Wordt aan elke API-handler meegegeven."""

    def __init__(self, staat: Staat, naam: str, tid: str = ''):
        self.staat = staat
        self.naam = naam
        self.tid = tid          # klant waarvoor de pagina deze actie startte (header X-Tenant)
        self.log: list[str] = []

    @property
    def t(self) -> Tenant:
        # Altijd de klant van het verzoek gebruiken, niet "de huidige": zo kan een actie
        # nooit bij een andere klant terechtkomen als je tussendoor wisselt.
        t = self.staat.tenants.get(self.tid) if self.tid else None
        if not t:
            raise ApiFout('Kies eerst een klant.')
        return t

    @property
    def g(self) -> Graph:
        return self.t.graph

    @property
    def x(self) -> Exchange:
        self.t.wacht_op_exo()   # controle loopt mogelijk nog op de achtergrond
        if not self.t.exo:
            self.t.exo_herstellen(wacht=True)   # nooit opgeven zonder herstelpoging
        if not self.t.exo:
            raise ApiFout('Exchange Online is niet verbonden (dit onderdeel heeft Exchange nodig).'
                          + (f' Reden: {self.t.exo_fout}' if self.t.exo_fout else ''))
        return self.t.exo

    @property
    def exo_ok(self) -> bool:
        self.t.wacht_op_exo()
        if self.t.exo is None:
            self.t.exo_herstellen(wacht=True)
        return self.t.exo is not None

    def L(self, tekst: str) -> None:
        self.log.append(tekst)
        t = self.staat.tenants.get(self.tid)
        tnaam = t.naam if t else '-'
        self.staat.activiteit.add(tnaam, self.naam, tekst)


API: dict[str, Any] = {}


def api(naam: str):
    def deco(fn):
        API[naam] = fn
        return fn
    return deco
