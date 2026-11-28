"""Inloggen, klantenoverzicht (GDAP) en wisselen van klant."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import __version__, lokaal
from .clients import ACHTER_POOL, POOL, ApiFout, Graph, parallel, achtergrond_fn
from .common import voorladen
from .gdap import KOPPEL_ROLLEN, STATUS_NL, effectieve_rollen, goedkeuringslink
from .context import Ctx, Tenant, api

AGENDA_ROLLEN = [
    ('Owner', 'Eigenaar - alles, ook rechten beheren'),
    ('PublishingEditor', 'Publicerende bewerker - maken, bewerken, verwijderen, submappen'),
    ('Editor', 'Bewerker - maken, bewerken en verwijderen van alle afspraken'),
    ('PublishingAuthor', 'Publicerende auteur - maken, eigen afspraken bewerken, submappen'),
    ('Author', 'Auteur - maken, eigen afspraken bewerken en verwijderen'),
    ('NonEditingAuthor', 'Auteur zonder bewerken - maken, eigen afspraken verwijderen'),
    ('Reviewer', 'Lezer - alle afspraken lezen'),
    ('Contributor', 'Bijdrager - alleen afspraken aanmaken'),
    ('LimitedDetails', 'Beperkte details - vrij/bezet, onderwerp en locatie'),
    ('AvailabilityOnly', 'Alleen beschikbaarheid - alleen vrij/bezet'),
    ('None', 'Geen toegang'),
]

# Entra-rolsjablonen (roleDefinitionId in GDAP) -> leesbare naam
ROLNAMEN = {
    '62e90394-69f5-4237-9190-012177145e10': 'Global Administrator',
    'fe930be7-5e62-47db-91af-98c3a49a38b1': 'User Administrator',
    '4d6ac14f-3453-41d0-bef9-a3e0c569773a': 'License Administrator',
    '29232cdf-9323-42fd-ade2-1d097af3e4de': 'Exchange Administrator',
    '3a2c62db-5318-420d-8d74-23affee5d9d5': 'Intune Administrator',
    'fdd7a751-b60b-444a-984c-02652fe8fa1c': 'Groups Administrator',
    '729827e3-9c14-49f7-bb1b-9608f156bbb8': 'Helpdesk Administrator',
    'c4e39bd9-1100-46d3-8c65-fb160da0071f': 'Authentication Administrator',
    '7be44c8a-adaf-4e2a-84d6-ab2649e08a13': 'Privileged Authentication Administrator',
    '7698a772-787b-4ac8-901f-60d6b08affd2': 'Cloud Device Administrator',
    'f2ef992c-3afb-46b9-b7cf-a126ee74c451': 'Global Reader',
    '4a5d8f65-41da-4de4-8968-e035b65339cf': 'Reports Reader',
    '88d8e3e3-8f55-4a1e-953a-9b9898b8876b': 'Directory Readers',
    '194ae4cb-b126-40b2-bd5b-6091b380977d': 'Security Administrator',
    'f28a1f50-f6e7-4571-818b-6a12f2af6b6c': 'SharePoint Administrator',
    '69091246-20e8-4a56-aa4d-066075b2a7a8': 'Teams Administrator',
    'b0f54661-2d74-4c50-afa3-1ec803f12efe': 'Billing Administrator',
    'e8611ab8-c189-46e8-94e1-60213ab1f814': 'Privileged Role Administrator',
    '158c047a-c907-4556-b7ef-446551a6b5f7': 'Cloud Application Administrator',
    '9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3': 'Application Administrator',
    'f023fd81-a637-4b56-95fd-791ac0226033': 'Service Support Administrator',
}
# Rollen die (samen) alle onderdelen van de app afdekken
NODIG = {
    'Koppelen': {'Application Administrator', 'Cloud Application Administrator'},   # automatische app-koppeling via Partner Center
    'Gebruikers': {'User Administrator'},
    'Licenties': {'License Administrator', 'User Administrator'},
    'Exchange': {'Exchange Administrator'},
    'Apparaten': {'Intune Administrator', 'Cloud Device Administrator'},
    'MFA': {'Authentication Administrator', 'Privileged Authentication Administrator'},
}


def _partner(c: Ctx) -> Graph:
    a = c.staat.auth
    return Graph(lambda: a.token(a.home_tenant, 'partner'))


@api('auth.status')
def status(c: Ctx, b: dict) -> dict:
    s = c.staat
    return {'loggedIn': s.auth.ingelogd, 'user': s.beheerder, 'tenant': s.tenant.id if s.tenant else None, 'version': __version__}


@api('auth.login')
def login(c: Ctx, b: dict) -> dict:
    s = c.staat
    from .h_backup import vergeet_koppelingen
    vergeet_koppelingen()          # niets van een vorige login meenemen
    s.beheerder = s.auth.login()
    # Klantenoverzicht al ophalen terwijl de gebruiker de Exchange-login in de browser afrondt
    fut = _start_klanten(s)

    def opwarmen(_f=None):   # daarna back-up, e-mailbeveiliging, afvinklijst en Autotask alvast ophalen
        import threading
        from .clients import achtergrond_fn
        from .h_backup import opwarmen as warm
        threading.Thread(target=achtergrond_fn(lambda: warm(s)), daemon=True, name='opwarmen').start()
    try:
        fut.add_done_callback(opwarmen)
    except AttributeError:
        opwarmen()
    exo = True
    try:
        s.auth.login_exchange()
    except Exception as e:  # zonder Exchange werkt een deel van de app nog
        exo = False
        c.log.append(f'FOUT Exchange-login: {e}')
    return {'user': s.beheerder, 'exo': exo}


@api('auth.logout')
def logout(c: Ctx, b: dict) -> dict:
    c.staat.reset()
    from .h_backup import vergeet_koppelingen
    vergeet_koppelingen()   # sleutels en gegevens van Datto, Unitrends, Autotask en EasyDMARC uit het geheugen
    return {}


def _cachebestand(s) -> str:
    return f'klanten-{s.auth.home_tenant}.json'


def _start_klanten(s, opnieuw: bool = False):
    """Start (of hergebruik) één lopende ophaalactie van het klantenoverzicht."""
    with s.lock:
        taak = s.klanten_taak
        if taak is None or (taak.done() and (opnieuw or taak.exception() is not None)):
            taak = s.klanten_taak = ACHTER_POOL.submit(achtergrond_fn(_klanten_ophalen), s)
        return taak


@api('customers')
def klanten(c: Ctx, b: dict) -> dict:
    s = c.staat
    if s.klanten is not None and not b.get('fresh'):
        return {'customers': s.klanten, 'home': s.auth.home_tenant}
    if not b.get('fresh') and not b.get('noCache'):
        # Lokale cache van een vorige sessie: direct tonen, de interface ververst daarna op de achtergrond
        d = lokaal.lees(_cachebestand(s))
        if isinstance(d, dict) and isinstance(d.get('customers'), list):
            _start_klanten(s)   # alvast verversen
            return {'customers': d['customers'], 'home': s.auth.home_tenant, 'cached': True, 'cachedAt': d.get('at', '')}
    lijst, fout = _start_klanten(s, opnieuw=bool(b.get('fresh'))).result()
    if fout:
        c.log.append('FOUT bij ophalen klanten: ' + fout + ' (Je hebt hiervoor in de Justdata-tenant een rol nodig die GDAP-relaties mag lezen, bijv. Admin Agent.)')
    return {'customers': lijst, 'home': s.auth.home_tenant}


def _klanten_ophalen(s) -> tuple[list[dict], str]:
    a = s.auth
    p = Graph(lambda: a.token(a.home_tenant, 'partner'))
    # Alles tegelijk: dit waren vier aanvragen na elkaar
    r = parallel({
        # Alle relaties: actieve geven toegang, nieuwe (wacht op goedkeuring / wordt geactiveerd) tonen we als status
        'rels': lambda: p.all_of('/tenantRelationships/delegatedAdminRelationships?$top=300',
                                 '/tenantRelationships/delegatedAdminRelationships'),
        'klanten': lambda: p.all('/tenantRelationships/delegatedAdminCustomers'),
        'contracten': lambda: p.all('/contracts?$select=customerId,defaultDomainName,displayName&$top=999'),
        'org': lambda: p.get('/organization?$select=displayName'),
        'mijn': lambda: {g['id'] for g in p.all('/me/transitiveMemberOf/microsoft.graph.group?$select=id&$top=999')},
    })
    per: dict[str, dict] = {}
    fout = ''
    rels = r['rels']
    if isinstance(rels, Exception):
        rels, fout = [], str(rels)
    onderweg = [rel for rel in rels if rel.get('status') in ('created', 'approvalPending', 'activating')]
    rels = [rel for rel in rels if str(rel.get('status', '')).lower() == 'active']
    # Werkelijke rechten: alleen rollen die via een toegangstoewijzing aan een van jouw groepen gelden
    mijn = r['mijn'] if isinstance(r['mijn'], set) else set()
    effectief = effectieve_rollen(p, rels, mijn) if mijn else {}
    nu = datetime.now(timezone.utc)
    for rel in rels:
        cu = rel.get('customer') or {}
        tid = cu.get('tenantId')
        if not tid:
            continue
        k = per.setdefault(tid, {'id': tid, 'name': cu.get('displayName') or tid, 'domain': '', 'roles': set(), 'end': '', 'rels': 0,
                                 'relrollen': set()})
        k['rels'] += 1
        k['relrollen'] |= {ur.get('roleDefinitionId', '') for ur in (rel.get('accessDetails') or {}).get('unifiedRoles') or []}
        k['roles'] = {ROLNAMEN[x] for x in effectief.get(tid, set()) if x in ROLNAMEN}
        end = rel.get('endDateTime') or ''
        if end and (not k['end'] or end > k['end']):
            k['end'] = end
    for rel in onderweg:   # nieuwe relatie die nog niet actief is
        cu = rel.get('customer') or {}
        tid = cu.get('tenantId')
        if not tid:
            continue
        k = per.setdefault(tid, {'id': tid, 'name': cu.get('displayName') or tid, 'domain': '', 'roles': set(), 'end': '', 'rels': 0,
                                 'relrollen': set()})
        st = rel.get('status')
        k['pending'] = {'status': st, 'text': STATUS_NL.get(st, st), 'name': rel.get('displayName') or '',
                        'link': goedkeuringslink(rel['id']) if st == 'approvalPending' else ''}
    if isinstance(r['klanten'], list):
        for cu in r['klanten']:
            tid = cu.get('tenantId') or cu.get('id')
            if tid and tid not in per:
                per[tid] = {'id': tid, 'name': cu.get('displayName') or tid, 'domain': '', 'roles': set(), 'end': '', 'rels': 0,
                            'relrollen': set()}
    else:
        fout = fout or str(r['klanten'])
    if isinstance(r['contracten'], list):   # oude DAP-contracten geven het standaarddomein
        for co in r['contracten']:
            tid = co.get('customerId')
            if tid in per:
                per[tid]['domain'] = co.get('defaultDomainName') or ''
    lijst = []
    for k in per.values():
        rollen = sorted(k['roles'])
        dagen = None
        if k['end']:
            try:
                dagen = (datetime.fromisoformat(k['end'].replace('Z', '+00:00')) - nu).days
            except ValueError:
                pass
        toegang = bool(effectief.get(k['id']))
        ontbreekt = [deel for deel, nodig in NODIG.items()
                     if 'Global Administrator' not in rollen and not (nodig & set(rollen))] if toegang else []
        # Kan de app het zelf regelen? Dan moet de relatie een rol bevatten om te koppelen
        regelbaar = bool(KOPPEL_ROLLEN & k['relrollen'])
        lijst.append({'id': k['id'], 'name': k['name'], 'domain': k['domain'], 'roles': rollen, 'end': k['end'][:10],
                      'days': dagen, 'missing': ontbreekt, 'own': False, 'access': toegang, 'fixable': regelbaar,
                      'pending': k.get('pending')})
    lijst.sort(key=lambda x: x['name'].lower())
    eigen_naam = 'Eigen tenant'
    if isinstance(r['org'], dict):
        eigen_naam = (r['org'].get('value') or [{}])[0].get('displayName') or eigen_naam
    eigen = {'id': a.home_tenant, 'name': eigen_naam, 'domain': (s.beheerder.get('upn') or '@').split('@')[-1],
             'roles': [], 'end': '', 'days': None, 'missing': [], 'own': True, 'access': True, 'fixable': False}
    s.klanten = [eigen] + [k for k in lijst if k['id'] != a.home_tenant]
    if fout and not lijst:
        return s.klanten, fout
    lokaal.schrijf(_cachebestand(s), {'at': datetime.now().strftime('%Y-%m-%d %H:%M'), 'customers': s.klanten})
    # Recente klanten alvast stil openen, zodat het wisselen ernaar direct gaat
    bekend = {k['id'] for k in s.klanten}
    recent = [i for i in (lokaal.lees('voorkeuren.json', {}) or {}).get('recent', []) if i in bekend]
    s.vooraf_openen(recent)
    return s.klanten, ''


def _info(c: Ctx) -> dict:
    t = c.t
    return {'tenantId': t.id, 'tenant': t.naam, 'account': c.staat.beheerder.get('upn', ''), 'exo': t.exo_status, 'linked': t.gekoppeld,
            'exoError': t.exo_fout, 'domains': t.domeinen, 'defaultDomain': t.standaard_domein,
            'roles': [{'key': k, 'label': v} for k, v in AGENDA_ROLLEN]}


@api('tenant.select')
def kies(c: Ctx, b: dict) -> dict:
    tid = str(b.get('id') or '').strip()
    if not tid:
        raise ApiFout('Geen klant gekozen.')
    naam = next((k['name'] for k in (c.staat.klanten or []) if k['id'] == tid), '')
    if b.get('fresh'):
        c.staat.tenants.pop(tid, None)
    c.staat.kies(tid, naam)
    c.tid = tid
    voorladen(c)   # gebruikers, licenties en groepen alvast ophalen (alleen als de cache verlopen is)
    from . import h_autotask
    ACHTER_POOL.submit(achtergrond_fn(lambda: h_autotask.opwarmen_klant(tid)))   # open tickets en projecttaken alvast
    return _info(c)   # ontbreekt Exchange, dan toont de interface een balk bovenaan


@api('tenant.progress')
def voortgang(c: Ctx, b: dict) -> dict:
    """Welke stap loopt er nu bij het openen van deze klant (de interface vraagt dit elke 2 seconden op)."""
    v = c.staat.voortgang.get(str(b.get('id') or ''))
    return {'text': v['tekst'], 'seconds': int(time.time() - v['begin'])} if v else {}


@api('info')
def info(c: Ctx, b: dict) -> dict:
    t = c.staat.tenants.get(c.tid) if c.tid else None
    if t is not None:
        t.exo_herstellen()   # Exchange niet verbonden: op de achtergrond opnieuw proberen (max. eens per 20 s)
    return _info(c)


@api('activity')
def activiteit(c: Ctx, b: dict) -> dict:
    return {'items': list(reversed(c.staat.activiteit.regels))}


@api('tenant.prefetch')
def vooraf(c: Ctx, b: dict) -> dict:
    """De klant die je aanwijst in het overzicht alvast stil openen (zonder browserlogin)."""
    if c.staat.auth.ingelogd:
        c.staat.vooraf_openen([str(i) for i in (b.get("ids") or []) if i][:6])
    return {}


# ---------- Toegang regelen voor alle klanten (achtergrondklus met voortgang) ----------
_KLUS: dict = {'bezig': False, 'totaal': 0, 'klaar': 0, 'ok': [], 'fouten': []}
_klus_lock = threading.Lock()


@api('gdap.alles')
def gdap_alles(c: Ctx, b: dict) -> dict:
    """Voor alle klanten zonder toegang: GDAP-toewijzing (AdminAgents) en app-koppeling regelen."""
    s = c.staat
    with _klus_lock:
        if _KLUS['bezig']:
            return dict(_KLUS)
        doel = [k for k in (s.klanten or []) if not k.get('own') and not k.get('access') and k.get('fixable')]
        _KLUS.update(bezig=True, totaal=len(doel), klaar=0, ok=[], fouten=[])

    def een(k: dict) -> None:
        try:
            with s._slot(k['id']):
                if k['id'] not in s.tenants:
                    t = Tenant(s.auth, k['id'], k['name'])
                    t.openen()   # regelt toewijzing en koppeling indien nodig
                    with s.lock:
                        s.tenants[k['id']] = t
            k['access'] = True
            _KLUS['ok'].append(k['name'])
        except Exception as e:  # noqa: BLE001
            _KLUS['fouten'].append({'name': k['name'], 'error': str(e)[:300]})
        finally:
            _KLUS['klaar'] += 1
            c.staat.activiteit.add(k['name'], 'gdap.alles', ('Toegang geregeld' if k.get('access') else 'FOUT: toegang niet geregeld'))

    def alles() -> None:
        try:
            with ThreadPoolExecutor(max_workers=3) as ex:
                list(ex.map(achtergrond_fn(een), doel))
        finally:
            _KLUS['bezig'] = False
            if s.klanten:
                lokaal.schrijf(_cachebestand(s), {'at': datetime.now().strftime('%Y-%m-%d %H:%M'), 'customers': s.klanten})
    threading.Thread(target=alles, daemon=True, name='gdap-alles').start()
    return dict(_KLUS)


@api('gdap.status')
def gdap_status(c: Ctx, b: dict) -> dict:
    return {**_KLUS, 'customers': c.staat.klanten if not _KLUS['bezig'] else None}
