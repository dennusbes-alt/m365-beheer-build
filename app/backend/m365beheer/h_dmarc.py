"""E-mailbeveiliging (DMARC) via EasyDMARC: overzicht van alle klanten en domeinen, problemen in gewone taal,
falende afzenders per domein en een PDF-rapportage per klant.

EasyDMARC Public API (developers.easydmarc.com): token via POST https://api2.easydmarc.com/auth/token met client_id en
client_secret (Account Console > API Client management), geldig ~5 min. Organisaties: GET /v1/organizations,
domeinen met statistiek: POST /v1/domains/overview, ruwe rapportregels: POST /v1/dmarc/rua/reports.
Sleutels gedeeld (verborgen SharePoint-lijst, zie h_backup.GEDEELD), alleen de app-beheerder kan ze zetten.
Niet alle schema's zijn openbaar beschreven: bij de eerste opvraging worden veldnamen (geen waarden) gelogd.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import requests

from .clients import ApiFout, achtergrond_fn
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth, _velden_loggen
from .rechten import eis_beheerder, is_beheerder

log = logging.getLogger('m365beheer')
BASIS = 'https://api2.easydmarc.com'
_TOKEN: dict = {}
_lock = threading.Lock()
# Eén gedeelde sessie: verbindingen met EasyDMARC worden hergebruikt (geen nieuwe TLS-verbinding per aanvraag)
_S = requests.Session()
_S.mount('https://', requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=12))


# ---------------------------------------------------------------- Client
def _sleutels() -> tuple[str, str] | None:
    return GEDEELD.lees('easydmarc')


def _token(sl=None, vers: bool = False) -> str:
    sl = sl or _sleutels()
    if not sl:
        raise ApiFout('EasyDMARC is nog niet gekoppeld.')
    with _lock:
        if not vers and _TOKEN.get('sl') == sl and _TOKEN.get('tot', 0) > time.time() + 30:
            return _TOKEN['token']
        r = None
        for soort in ('json', 'form'):   # de documentatie noemt beide vormen
            try:
                r = _S.post(BASIS + '/auth/token', timeout=30, headers={'Accept': 'application/json'},
                                  **({'json': {'client_id': sl[0], 'client_secret': sl[1]}} if soort == 'json'
                                     else {'data': {'client_id': sl[0], 'client_secret': sl[1], 'grant_type': 'client_credentials'}}))
            except requests.exceptions.RequestException as e:
                raise ApiFout(f'EasyDMARC niet bereikbaar: {type(e).__name__}') from None
            if r.status_code < 400:
                break
        if r is None or r.status_code >= 400:
            raise ApiFout(f'EasyDMARC-aanmelding mislukt ({r.status_code if r is not None else "?"}). Controleer Client-ID en secret.')
        j = r.json()
        _TOKEN.update(sl=sl, token=j['access_token'], tot=time.time() + int(j.get('expires_in') or 300))
        return _TOKEN['token']


def _req(methode: str, pad: str, body=None, params=None, sl=None):
    r = None
    for poging in range(4):
        try:
            vers = r is not None and r.status_code == 401
            r = _S.request(methode, BASIS + pad, json=body, params=params, timeout=60,
                                 headers={'Authorization': 'Bearer ' + _token(sl, vers=vers), 'Accept': 'application/json'})
        except requests.exceptions.RequestException as e:
            if poging == 3:
                raise ApiFout(f'EasyDMARC niet bereikbaar: {type(e).__name__}') from None
            time.sleep(0.5 * (poging + 1))
            continue
        if r.status_code == 429 and poging < 3:
            time.sleep(2 * (poging + 1))
            continue
        if r.status_code == 401 and poging == 0:
            continue
        break
    if r.status_code >= 400:
        try:
            j = r.json()
            m = j.get('message') or j.get('error') or r.text
            det = j.get('details') if isinstance(j, dict) else None
            for x in (det if isinstance(det, list) else [det] if det else []):
                if isinstance(x, dict):
                    m = f"{m} ({x.get('property') or ''}: {x.get('message') or x})"
                else:
                    m = f'{m} ({x})'
            if isinstance(m, list):
                m = '; '.join(map(str, m))
        except ValueError:
            m = r.text
        raise ApiFout(f'EasyDMARC {r.status_code}: {str(m)[:250]}', r.status_code)
    return r.json() if r.content else {}


def _claims(token: str) -> dict:
    """Inhoud van het aanmeldtoken (JWT) lezen, zonder controle: alleen om de organisatie te vinden."""
    import base64
    try:
        deel = token.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(deel + '=' * (-len(deel) % 4)))
    except Exception:  # noqa: BLE001
        return {}


def _orgs_uit_token(sl=None) -> list[dict]:
    c = _claims(_token(sl))
    log.info('EasyDMARC-token: claims %s, scope %s', sorted(c.keys())[:40], str(c.get('scope', ''))[:120])
    gevonden = []
    for k, v in c.items():
        kl = k.lower()
        if kl in ('organization_id', 'organizationid', 'organisation_id', 'org_id', 'orgid', 'organizations', 'organization'):
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, dict) and x.get('id'):
                    gevonden.append({'id': x['id'], 'name': x.get('name') or str(x['id'])})
                elif isinstance(x, (str, int)) and str(x).strip():
                    gevonden.append({'id': x, 'name': ''})
    return gevonden


def _werkruimtes(org_id, sl=None) -> list[dict]:
    """GET /v1/workspaces?organizationId=: werkruimtes van één organisatie (409 = organisatie zonder werkruimtes)."""
    if not org_id:
        return []
    uit, pagina = [], 1
    while pagina <= 50:
        try:
            j = _req('GET', '/v1/workspaces', params={'organizationId': org_id, 'page': pagina, 'pageSize': 100}, sl=sl)
        except ApiFout as e:
            if e.status in (404, 409):
                return []
            raise
        items = (j.get('items') if isinstance(j, dict) else j) or []
        uit += [{'id': w['id'], 'name': w.get('name') or str(w['id']), 'org': org_id, 'ws': w['id']} for w in items if w.get('id')]
        if not items or len(uit) >= int((j or {}).get('totalCount') or 0):
            break
        pagina += 1
    return uit


def _ids(o: dict) -> dict:
    """organizationId/workspaceId voor een klant uit het overzicht."""
    d = {}
    org = o.get('org', o.get('id'))
    if org is not None:
        d['organizationId'] = org
    if o.get('ws'):
        d['workspaceId'] = o['ws']
    return d


def _alle_orgs(sl=None) -> list[dict]:
    """Organisaties (klanten). Partner-accounts: /v1/organizations. Mag de API-client dat niet (403), dan de
    organisatie(s) uit het token, of een 'losse' organisatie waarbij de domeinen zonder organisatie-ID worden opgehaald."""
    uit, pagina = [], 1
    try:
        while pagina <= 50:
            j = _req('GET', '/v1/organizations', params={'page': pagina, 'limit': 100}, sl=sl)
            data = j.get('data') if isinstance(j, dict) else j
            uit += data or []
            meta = j.get('meta') if isinstance(j, dict) else None
            if not meta or not meta.get('hasNextPage'):
                break
            pagina += 1
        return uit
    except ApiFout as e:
        if e.status not in (401, 403, 404):
            raise
        log.info('EasyDMARC: organisaties ophalen geweigerd (%s), terugval', e.status)
    orgs = _orgs_uit_token(sl)
    ws = [w for o in orgs for w in _werkruimtes(o['id'], sl)]
    if ws:
        log.info('EasyDMARC: %d werkruimte(s) gevonden', len(ws))
        return ws
    if orgs:
        for o in orgs:
            if not o['name']:
                try:
                    o['name'] = (_req('GET', f"/v1/organizations/{o['id']}", sl=sl) or {}).get('name') or 'EasyDMARC'
                except ApiFout:
                    o['name'] = 'EasyDMARC'
        return orgs
    return [{'id': None, 'name': 'EasyDMARC'}]


def _diagnose(sl) -> list[tuple[str, int | str]]:
    """Welke onderdelen mag deze API-client wel/niet (voor een duidelijke melding bij het koppelen)."""
    org = next((o['id'] for o in _orgs_uit_token(sl)), None)
    uit = []
    try:
        ws = _werkruimtes(org, sl)
        uit.append(('werkruimtes', f'ok ({len(ws)})'))
    except ApiFout as e:
        ws = []
        uit.append(('werkruimtes', e.status or 'fout'))
        log.info('EasyDMARC-diagnose werkruimtes: %s', e)
    ids = _ids(ws[0]) if ws else ({'organizationId': org} if org else {})
    proeven = [('organisaties', 'GET', '/v1/organizations', None, {'page': 1, 'limit': 1}),
               ('domeinen', 'GET', '/v1/domains', None, {**ids, 'page': 1, 'pageSize': 1})]
    for naam, m, pad, body, params in proeven:
        try:
            _req(m, pad, body, params, sl=sl)
            uit.append((naam, 'ok'))
        except ApiFout as e:
            uit.append((naam, e.status or 'fout'))
            if e.status in (400, 422):
                log.info('EasyDMARC-diagnose %s: %s', naam, e)
    try:
        _overzicht_pagina(ids, 7, 1, 1, sl=sl)
        uit.append(('domeinoverzicht', 'ok'))
    except ApiFout as e:
        uit.append(('domeinoverzicht', e.status or 'fout'))
        log.info('EasyDMARC-diagnose domeinoverzicht: %s', e)
    return uit


# ---------------------------------------------------------------- Beoordeling
POLICY_NL = {'reject': 'Weigeren (reject)', 'quarantine': 'Quarantaine', 'none': 'Alleen monitoren (none)', 'missing': 'Geen DMARC'}


def _pct(v) -> float | None:
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _slang(x):
    """Sleutels naar snake_case (EasyDMARC levert camelCase: dmarcCompliance, spfPassRate, domainName, nonCompliant)."""
    if isinstance(x, dict):
        return {re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', str(k)).lower(): _slang(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_slang(v) for v in x]
    return x


_VORM_GELOGD: set = set()


def _vorm(x, diepte: int = 0):
    """Opbouw (sleutels en soorten) voor het logboek, zonder waarden."""
    if isinstance(x, dict) and diepte < 3:
        return {k: _vorm(v, diepte + 1) for k, v in x.items()}
    return type(x).__name__


def _domein(d: dict) -> dict:
    """Eén domein uit /v1/domains/overview, met beoordeling en problemen in gewone taal."""
    ruw = d
    d = _slang(d)
    if 'compliance' not in _VORM_GELOGD and d.get('dmarc_compliance') is not None:
        _VORM_GELOGD.add('compliance')
        log.info('EasyDMARC dmarcCompliance-opbouw: %s', _vorm(ruw.get('dmarcCompliance', ruw.get('dmarc_compliance'))))
    d.setdefault('domain', d.get('domain_name') or '')
    policy = str(d.get('policy') or 'missing').lower()
    comp = d.get('dmarc_compliance') or {}
    if not isinstance(comp, dict):   # soms alleen een percentage
        comp = {'overall_compliance': comp}
    overall = _pct(comp.get('overall_compliance') if comp.get('overall_compliance') is not None else comp.get('overall'))
    if overall is None:
        overall = _pct((comp.get('compliant') or {}).get('percentage'))
    volume = int(float(d.get('volume') or 0))

    def _n(x):
        try:
            return int(float(x.get('value', x.get('count')) if isinstance(x, dict) else x))
        except (TypeError, ValueError):
            return None
    nc = next((comp[k] for k in ('none_compliant', 'non_compliant', 'not_compliant', 'noncompliant') if comp.get(k) is not None), None)
    geslaagd, gefaald = _n(comp.get('compliant')), _n(nc)
    if geslaagd is None and overall is not None and volume:
        geslaagd = round(volume * overall / 100)
    if gefaald is None and geslaagd is not None and volume:
        gefaald = max(volume - geslaagd, 0)
    if overall is None and geslaagd is not None and (geslaagd + (gefaald or 0)):
        overall = round(geslaagd * 100 / (geslaagd + (gefaald or 0)), 1)
    spf, dkim, dmarc = (str(d.get(k) or 'no-record').lower() for k in ('spf', 'dkim', 'dmarc'))
    soort = str(d.get('type') or 'sending').lower()
    problemen: list[tuple[str, str]] = []   # (ernst, tekst)
    if dmarc == 'no-record' or policy == 'missing':
        problemen.append(('err', 'Geen DMARC-record: iedereen kan mail versturen uit naam van dit domein zonder dat ontvangers dat tegenhouden.'))
    elif policy == 'none':
        problemen.append(('warn', 'DMARC staat op alleen monitoren (p=none): nepmail uit naam van dit domein wordt nog niet tegengehouden.'))
    if spf == 'unknown':
        pass
    elif spf == 'no-record':
        problemen.append(('err', 'Geen SPF-record: ontvangers weten niet welke servers mogen mailen namens dit domein.'))
    elif spf == 'warning':
        problemen.append(('warn', 'Het SPF-record heeft een waarschuwing (bijv. te veel DNS-lookups of een zwakke instelling).'))
    if soort != 'parked':
        if dkim == 'unknown':
            pass
        elif dkim == 'no-record':
            problemen.append(('warn', 'Geen DKIM gevonden: uitgaande mail wordt niet digitaal ondertekend.'))
        elif dkim == 'warning':
            problemen.append(('warn', 'DKIM heeft een waarschuwing.'))
        if volume and overall is not None and overall < 90:
            problemen.append(('err' if overall < 75 else 'warn',
                              f'Slechts {str(overall).replace(".", ",")}% van de mail voldoet aan DMARC: er mailt een dienst namens dit domein die niet goed is ingesteld (zie afzenders).'))
        if d.get('_basis'):
            problemen.append(('info', 'Alleen basisgegevens: de statistiek (volume, SPF/DKIM) kon niet bij EasyDMARC worden opgehaald.'))
        elif not volume and dmarc != 'no-record':
            problemen.append(('info', 'Geen DMARC-rapporten ontvangen in deze periode (er wordt weinig of niet gemaild, of de rapportage-instelling klopt niet).'))
    if not d.get('domain_verified', True):
        problemen.append(('info', 'Domein is in EasyDMARC nog niet geverifieerd.'))
    status = 'err' if any(e == 'err' for e, _ in problemen) else 'warn' if any(e == 'warn' for e, _ in problemen) else 'ok'
    groep = d.get('domain_group')
    groep = (groep.get('name') if isinstance(groep, dict) else groep if isinstance(groep, str) else '') or ''
    return {'domain': d.get('domain', ''), 'group': groep, 'policy': policy, 'policyText': POLICY_NL.get(policy, policy), 'spf': spf, 'dkim': dkim, 'dmarc': dmarc,
            'bimi': str(d.get('bimi') or ''), 'volume': volume, 'compliance': overall, 'spfPass': _pct(d.get('spf_pass_rate')),
            'dkimPass': _pct(d.get('dkim_pass_rate')), 'type': soort, 'status': status,
            'passed': geslaagd or 0, 'failed': gefaald or 0, 'failPct': round(100 - overall, 1) if overall is not None and volume else None,
            'problems': [{'level': e, 'text': t} for e, t in problemen]}


def _periode(dagen: int, iso: bool = True) -> tuple[str, str]:
    eind = datetime.now(timezone.utc).date()   # EasyDMARC rekent in UTC (anders rond middernacht 422)
    van = eind - timedelta(days=dagen)
    if iso:
        return van.isoformat() + 'T00:00:00.000Z', eind.isoformat() + 'T23:59:59.999Z'
    return van.isoformat(), eind.isoformat()


_DATUMVORM: dict = {}   # welke datumvorm EasyDMARC accepteert (onthouden na de eerste keer)


def _datum(dagen: int, vorm: str) -> tuple[str, str]:
    eind = datetime.now(timezone.utc).date()   # EasyDMARC rekent in UTC (anders rond middernacht 422)
    van = eind - timedelta(days=dagen)
    if vorm == 'iso':
        return van.isoformat() + 'T00:00:00.000Z', eind.isoformat() + 'T23:59:59.999Z'
    if vorm == 'us':
        return van.strftime('%m/%d/%Y'), eind.strftime('%m/%d/%Y')
    if vorm == 'isokort':
        return van.isoformat() + 'T00:00:00Z', eind.isoformat() + 'T23:59:59Z'
    return van.isoformat(), eind.isoformat()


# (datumvorm, ids in de body?, ids als query-parameters?)
_OV_VARIANTEN = [('us', True, False), ('iso', True, False), ('dag', True, False), ('iso', False, True), ('dag', False, True), ('isokort', True, True), ('iso', True, True)]


def _overzicht_pagina(ids: dict, dagen: int, pagina: int, grootte: int = 100, sl=None) -> dict:
    """POST /v1/domains/overview. organizationId (+ workspaceId) verplicht; datumvorm en plek van de ids zijn niet
    eenduidig beschreven: varianten proberen en de werkende onthouden. Lukt niets, dan ApiFout met status 422."""
    varianten = [_DATUMVORM['ov']] if 'ov' in _DATUMVORM else _OV_VARIANTEN
    fout = None
    for var in varianten:
        vorm, in_body, in_query = var
        van, tot = _datum(dagen, vorm)
        body = {'startDate': van, 'endDate': tot, 'page': pagina, 'pageSize': grootte, **(ids if in_body else {})}
        try:
            j = _req('POST', '/v1/domains/overview', body, params=ids if in_query and ids else None, sl=sl)
            if 'ov' not in _DATUMVORM:
                log.info('EasyDMARC: domeinoverzicht werkt met variant %s', var)
            _DATUMVORM['ov'] = var
            return j
        except ApiFout as e:
            fout = e
            if e.status not in (400, 422):
                raise
            if 'ov' not in _DATUMVORM:
                log.info('EasyDMARC: domeinoverzicht variant %s: %s', var, e)
    raise fout


def _domeinlijst(ids: dict, sl=None) -> list[dict]:
    """Terugval: GET /v1/domains (werkt wel) geeft domein, beleid en type, zonder statistiek."""
    uit, pagina = [], 1
    while pagina <= 50:
        j = _req('GET', '/v1/domains', params={**ids, 'page': pagina, 'pageSize': 100}, sl=sl)
        data = j.get('data') or []
        if data and pagina == 1:
            _velden_loggen('DMARC-domeinlijst', data[0])
        for d in data:
            uit.append({'domain': d.get('domain') or d.get('domainName') or '', 'policy': d.get('policy') or 'missing',
                        'type': d.get('type') or 'sending', 'domain_verified': d.get('domainVerified', True),
                        'spf': 'unknown', 'dkim': 'unknown', 'dmarc': 'unknown' if d.get('policy') else 'no-record', '_basis': True})
        if not (j.get('meta') or {}).get('hasNextPage'):
            break
        pagina += 1
    return uit


def _org_domeinen(org: dict, dagen: int) -> dict:
    uit, pagina, basis = [], 1, False
    while pagina <= 20:
        try:
            j = _overzicht_pagina(_ids(org), dagen, pagina)
        except ApiFout as e:
            if e.status not in (400, 422) or pagina > 1:
                raise
            log.info('EasyDMARC: domeinoverzicht niet beschikbaar voor %s, terugval op domeinlijst: %s', org.get('name'), e)
            uit, basis = _domeinlijst(_ids(org)), True
            break
        data = j.get('data') or []
        if data:
            _velden_loggen('DMARC-domein', data[0])
        uit += data
        meta = j.get('meta') or {}
        if not meta.get('hasNextPage'):
            break
        pagina += 1
    domeinen = sorted([_domein(d) for d in uit], key=lambda x: ({'err': 0, 'warn': 1, 'ok': 2}[x['status']], x['domain']))
    return {'id': org['id'], 'org': org.get('org'), 'ws': org.get('ws'), 'name': org.get('name') or '', 'basic': basis, **_samen(domeinen)}


def _samen(domeinen: list[dict]) -> dict:
    """Totalen van een klant uit zijn domeinen."""
    volume = sum(d['volume'] for d in domeinen)
    geslaagd, gefaald = sum(d['passed'] for d in domeinen), sum(d['failed'] for d in domeinen)
    gewogen = sum((d['compliance'] or 0) * d['volume'] for d in domeinen if d['compliance'] is not None)
    return {'domains': domeinen, 'volume': volume,
            'compliance': (round(geslaagd * 100 / (geslaagd + gefaald), 1) if geslaagd + gefaald else round(gewogen / volume, 1) if volume else None),
            'passed': geslaagd, 'failed': gefaald,
            'status': 'err' if any(d['status'] == 'err' for d in domeinen) else 'warn' if any(d['status'] == 'warn' for d in domeinen) else 'ok',
            'counts': {k: len([d for d in domeinen if d['status'] == k]) for k in ('ok', 'warn', 'err')}}


VERZAMEL = re.compile(r'klanten|customers|clients', re.I)   # werkruimte met domeinen van meerdere klanten (bijv. 'Justdata Klanten')
GEEN_GROEP = re.compile(r'^(default|standaard|ungrouped|no group|none|overig|other|all domains|alle domeinen|domains|domeinen)?$', re.I)
_GELOGD: set = set()
_TWEEDELIG = ('co.uk', 'org.uk', 'com.au', 'co.nz', 'com.br', 'co.za')


def _plat(s) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(s or '').lower())


def _hoofddomein(dom: str) -> str:
    """mail.korenaar.nl -> korenaar.nl (subdomeinen horen bij dezelfde klant)."""
    delen = dom.split('.')
    n = 3 if len(delen) >= 3 and '.'.join(delen[-2:]) in _TWEEDELIG else 2
    return '.'.join(delen[-n:]) if len(delen) >= n else dom


def _klantnaam_bij_domein(staat) -> dict:
    """domein -> klantnaam uit het GDAP-klantenoverzicht en de geopende klanten (alle geverifieerde domeinen)."""
    m: dict = {}
    for k in (getattr(staat, 'klanten', None) or []):
        if k.get('domain') and not k.get('own'):
            m[str(k['domain']).lower()] = k['name']
    for t in list((getattr(staat, 'tenants', None) or {}).values()):
        for d in getattr(t, 'domeinen', None) or []:
            m.setdefault(str(d['id']).lower(), t.naam)
    return m


def weergave(orgs: list[dict], staat=None) -> list[dict]:
    """Zoals de beheerder het wil zien: lege werkruimtes weg, en een verzamelwerkruimte ('Justdata Klanten') per klant
    opgesplitst (op domeingroep in EasyDMARC, anders op de GDAP-klant met dat domein, anders op de domeinnaam)."""
    uit = []
    namen = _klantnaam_bij_domein(staat) if staat is not None else {}
    for o in orgs:
        if not o.get('domains') and not o.get('error'):
            continue   # lege werkruimte (bijv. 'Default Workspace')
        if not VERZAMEL.search(o.get('name') or '') or o.get('error'):
            uit.append(o)
            continue
        per: dict = {}
        ws = _plat(o.get('name'))
        for d in o['domains']:
            dom = d['domain'].lower().strip('.')
            hoofd = _hoofddomein(dom)
            # Domeingroep alleen gebruiken als die echt een klant aanduidt: niet de werkruimte zelf ('Justdata Klanten'),
            # geen verzamel- of standaardgroep (bij Justdata hebben alle domeinen dezelfde groep: dan zou alles weer samenvallen)
            groep = d.get('group') or ''
            if not groep or VERZAMEL.search(groep) or _plat(groep) == ws or GEEN_GROEP.match(groep.strip()):
                groep = ''
            naam = (groep or namen.get(dom) or namen.get(hoofd)
                    or next((n for k, n in namen.items() if dom.endswith('.' + k)), '')
                    or hoofd.split('.')[0].replace('-', ' ').title())
            per.setdefault(naam, []).append(d)
        if ('split', o.get('id'), len(per)) not in _GELOGD:
            _GELOGD.add(('split', o.get('id'), len(per)))
            log.info('EasyDMARC: verzamelwerkruimte opgesplitst in %d klanten (%d domeinen, %d met bruikbare domeingroep)',
                     len(per), len(o['domains']), sum(1 for d in o['domains'] if d.get('group') and _plat(d['group']) != ws and not VERZAMEL.search(d['group'])))
        for naam, doms in per.items():
            sleutel = re.sub(r'[^a-z0-9]+', '-', naam.lower()).strip('-')
            uit.append({'id': f"{o['id']}~{sleutel}", 'org': o.get('org'), 'ws': o.get('ws'), 'name': naam, 'basic': o.get('basic'),
                        'from': o.get('name'), **_samen(doms)})
    return uit


# ---------------------------------------------------------------- Overzicht (achtergrondklus, net als Back-up)
_JOB: dict = {'bezig': False, 'eind': 0.0, 'dagen': 30, 'orgs': [], 'fout': '', 'klaar': 0, 'totaal': 0}
_jl = threading.Lock()


def _start(dagen: int) -> None:
    with _jl:
        if _JOB['bezig']:
            return
        vervang = bool(_JOB['orgs']) and _JOB['dagen'] == dagen   # oude stand tonen tot de nieuwe compleet is
        if not vervang:
            _JOB['orgs'] = []
        _JOB.update(bezig=True, dagen=dagen, fout='', klaar=0, totaal=0)
    nieuw: list = []

    def alles() -> None:
        try:
            orgs = _alle_orgs()
            if orgs:
                _velden_loggen('DMARC-organisatie', orgs[0])
            with _jl:
                _JOB['totaal'] = len(orgs)

            def een(o):
                try:
                    r = _org_domeinen(o, dagen)
                except ApiFout as e:
                    r = {'id': o.get('id'), 'org': o.get('org'), 'ws': o.get('ws'), 'name': o.get('name') or '', 'domains': [], 'volume': 0, 'compliance': None,
                     'passed': 0, 'failed': 0, 'status': 'warn',
                         'counts': {'ok': 0, 'warn': 0, 'err': 0}, 'error': str(e)[:200]}
                with _jl:
                    (nieuw if vervang else _JOB['orgs']).append(r)
                    _JOB['klaar'] += 1
            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(achtergrond_fn(een), orgs))
            if vervang:
                with _jl:
                    _JOB['orgs'] = nieuw
        except Exception as e:  # noqa: BLE001
            with _jl:
                _JOB['fout'] = str(e)[:300]
            log.info('DMARC-overzicht niet gelukt: %s', e)
        finally:
            with _jl:
                _JOB.update(bezig=False, eind=time.time())
    threading.Thread(target=achtergrond_fn(alles), daemon=True, name='dmarc').start()


@api('dm.overzicht')
def dm_overzicht(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    if not _sleutels():
        return {'configured': False, 'admin': is_beheerder(c.staat)}
    dagen = int(b.get('days') or 30)
    with _jl:
        bezig, eind, oud = _JOB['bezig'], _JOB['eind'], _JOB['dagen']
    if not bezig and (b.get('fresh') or not eind or time.time() - eind > 900 or dagen != oud):
        _start(dagen)
    with _jl:
        orgs = sorted(weergave(list(_JOB['orgs']), c.staat), key=lambda o: ({'err': 0, 'warn': 1, 'ok': 2}.get(o['status'], 3), o['name'].lower()))
        return {'configured': True, 'admin': is_beheerder(c.staat), 'busy': _JOB['bezig'], 'done': _JOB['klaar'], 'total': _JOB['totaal'],
                'days': _JOB['dagen'], 'error': _JOB['fout'], 'orgs': orgs, 'at': datetime.fromtimestamp(_JOB['eind']).strftime('%H:%M') if _JOB['eind'] else ''}


# ---------------------------------------------------------------- Afzenders per domein (wie faalt en waarom)
def _datumvormen(dagen: int) -> list[dict]:
    return [dict(zip(('from', 'to'), _datum(dagen, v))) for v in ('iso', 'us', 'dag')]


@api('dm.afzenders')
def dm_afzenders(c: Ctx, b: dict) -> dict:
    """Falende (en alle) afzenders van één domein, samengevat per dienst/organisatie met de reden."""
    _zet_auth(c)
    dom = str(b['domain'])
    with _jl:
        eigen = next((o for o in _JOB['orgs'] if any(d['domain'] == dom for d in o.get('domains') or [])), None)
    ids = _ids(eigen) if eigen else {}
    rijen, fout = None, ''
    vormen = _datumvormen(int(b.get('days') or 30))
    varianten = [(i, plek) for plek in ('body', 'query') for i in range(len(vormen))]
    if 'rua' in _DATUMVORM:
        varianten = [_DATUMVORM['rua']]
    for i, plek in varianten:
        dr = vormen[i]   # schema niet eenduidig: varianten proberen, de werkende onthouden
        body = {'domainNames': [dom], 'reportType': 'non-compliant', 'dateRange': dr, 'filters': {}, 'page': 1, 'pageSize': 2000}
        if plek == 'body':
            body.update(ids)
        try:
            j = _req('POST', '/v1/dmarc/rua/reports', body, params=ids if plek == 'query' and ids else None)
            rijen = j.get('data') or []
            if 'rua' not in _DATUMVORM:
                log.info('EasyDMARC: rapportregels werken met %s, ids in %s', dr, plek)
                _DATUMVORM['rua'] = (i, plek)
            break
        except ApiFout as e:
            fout = str(e)
            log.info('EasyDMARC: rapportregels %s/%s: %s', dr, plek, e)
            if e.status not in (400, 422):
                break
    if rijen is None:
        raise ApiFout(f'Afzenders konden niet worden opgehaald: {fout}')
    if rijen:
        _velden_loggen('DMARC-rapportregel', rijen[0])
    groepen: dict[str, dict] = {}
    for r in rijen:
        naam = r.get('ptrGroup') or r.get('orgName') or r.get('ptr') or r.get('sourceIpStr') or r.get('sourceIp') or 'onbekend'
        g = groepen.setdefault(str(naam), {'name': str(naam), 'count': 0, 'spfFail': 0, 'dkimFail': 0, 'ips': set(), 'from': set(), 'countries': set()})
        n = int(float(r.get('count') or 1))
        g['count'] += n
        if str(r.get('spf') or r.get('spfResult') or '').lower() not in ('pass', 'true'):
            g['spfFail'] += n
        if str(r.get('dkim') or '').lower() not in ('pass', 'true'):
            g['dkimFail'] += n
        for veld, set_ in (('sourceIpStr', g['ips']), ('envelopeFrom', g['from']), ('countryCode', g['countries'])):
            if r.get(veld):
                set_.add(str(r[veld]))
    uit = []
    for g in sorted(groepen.values(), key=lambda x: -x['count'])[:40]:
        reden = []
        if g['spfFail']:
            reden.append('SPF faalt (deze server staat niet in het SPF-record)')
        if g['dkimFail']:
            reden.append('DKIM ontbreekt of klopt niet (de dienst ondertekent niet met jullie domein)')
        uit.append({'name': g['name'], 'count': g['count'], 'reason': '; '.join(reden) or 'Voldoet niet aan DMARC',
                    'ips': sorted(g['ips'])[:5], 'from': sorted(g['from'])[:3], 'countries': sorted(g['countries'])[:5],
                    'advice': 'Is dit een eigen dienst (bijv. nieuwsbrief, CRM, scanner, website)? Voeg hem toe aan SPF en zet DKIM aan bij die dienst. '
                              'Herken je hem niet, dan is het waarschijnlijk spoofing en wordt het tegengehouden zodra DMARC op quarantine/reject staat.'})
    return {'domain': dom, 'senders': uit, 'total': sum(g['count'] for g in groepen.values())}


# ---------------------------------------------------------------- Koppeling (alleen app-beheerder)
@api('dm.keys.set')
def dm_keys_set(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    cid, geheim = str(b.get('a') or '').strip(), str(b.get('b') or '').strip()
    if not cid or not geheim:
        raise ApiFout('Vul Client-ID en secret in.')
    try:
        _token((cid, geheim), vers=True)
    except ApiFout as e:
        _TOKEN.clear()
        raise ApiFout(f'De sleutels werken niet: {e}')
    try:
        diag = _diagnose((cid, geheim))
        log.info('EasyDMARC-diagnose: %s', diag)
        if not any(n != 'werkruimtes' and v == 'ok' for n, v in diag):
            _orgs_uit_token((cid, geheim))   # claims in het logboek voor verder onderzoek
            geweigerd = ', '.join(f'{n} ({v})' for n, v in diag)
            raise ApiFout('Aanmelden bij EasyDMARC lukt, maar het ophalen van gegevens niet: ' + geweigerd + '. '
                          'Kies bij de API-sleutel in EasyDMARC de rol Organization Admin of Organization Viewer. '
                          'Blijft dit, stuur dan het logboek (regels met EasyDMARC-diagnose).')
    finally:
        _TOKEN.clear()
    GEDEELD.schrijf('easydmarc', cid, geheim)
    with _jl:
        _JOB.update(eind=0.0, orgs=[])
    c.L("EasyDMARC gekoppeld (gedeeld met alle Justdata-collega's).")
    return {}


@api('dm.keys.delete')
def dm_keys_delete(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    GEDEELD.schrijf('easydmarc', '', None)
    _TOKEN.clear()
    c.L('EasyDMARC-koppeling verwijderd (voor iedereen).')
    return {}


# ---------------------------------------------------------------- Rapportage (PDF per klant)
@api('dm.rapport')
def dm_rapport(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    from .h_rapport import _bestandsnaam, _openen
    from .h_dmarc_pdf import maak_pdf
    org = next((o for o in weergave(list(_JOB['orgs']), c.staat) if str(o['id']) == str(b.get('orgId'))), None)
    if not org:
        raise ApiFout('Klant niet gevonden in het overzicht; vernieuw eerst.')
    afz = {}
    for d in org['domains'][:15]:
        if d['volume'] and (d['compliance'] or 100) < 98:
            try:
                afz[d['domain']] = dm_afzenders(c, {'domain': d['domain'], 'days': _JOB['dagen']})['senders'][:6]
            except ApiFout:
                pass
    pad = _bestandsnaam(org['name']).with_name(re.sub(r'^NEN7510-rapport', 'DMARC-rapport', _bestandsnaam(org['name']).name))
    pad.write_bytes(maak_pdf(org, afz, _JOB['dagen']))
    c.L(f'DMARC-rapport opgeslagen: {pad}')
    _openen(pad)
    return {'path': str(pad)}


@api('dm.status')
def dm_status(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    return {'configured': _sleutels() is not None, 'admin': is_beheerder(c.staat)}



def vergeet() -> None:
    """Afmelden: token en overzicht wissen (zie h_backup.vergeet_koppelingen)."""
    _TOKEN.clear()
    _JOB.update(bezig=False, eind=0.0, orgs=[], fout='', klaar=0, totaal=0)
