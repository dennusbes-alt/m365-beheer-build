"""Contract samenstellen op basis van de offertepagina van Justdata (https://justdata.vibeweb.nl/offerte).

- Prijsmodel: gelezen uit de openbare code van de offertepagina (het object met setupCosts, base, perUser, perServer, extraVeilig,
  extraVeiligPlus, dmarcProtection, m365Licenses). Geen sleutels of database van de site: alleen wat de pagina zelf publiceert.
  1 uur in het geheugen; laatst gelezen versie gedeeld bewaard ('prijslijst') als terugval, daarna de ingebouwde standaard.
- Berekening is dezelfde als op de pagina: staffel klein (1-10) / middel (11-50) / groot (51-150) met minimum aantal gebruikers
  per staffel; 1-2 gebruikers = organisatieprijs naar rato; Extra Veilig(++) tot 4 gebruikers met het xsmall-organisatietarief;
  EasyDMARC alleen bij het basispakket; setup = setupkosten per gebruiker (per niveau) + DMARC-setup; licenties per maand.
- Contract (`sa.contract.samenstellen`): Recurring Service 'Full Service - Klantnaam' als standaardcontract, setupFee = setup,
  per onderdeel een Autotask-dienst (Service; ontbreekt die, dan maakt de app hem aan met een vaste naam) met aantal en prijs,
  after hours / emergency uitgesloten. NIET getest met een echte Autotask (Services aanmaken, aantallen via
  ContractServiceAdjustments).
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import is_sales

log = logging.getLogger('m365beheer')
SITE = 'https://justdata.vibeweb.nl'
_S = requests.Session()
_CACHE: dict = {}
_lock = threading.Lock()

# Stand van de offertepagina op 28-11-2026 (terugval als de pagina niet te lezen is)
STANDAARD = {
    'setupCosts': {'none': 100, 'extra': 150, 'extraPlus': 175},
    'dmarcProtection': {'monthly': 29, 'setup': 385, 'extraDomain': 19.5},
    'tiers': {'small': {'min': 1, 'max': 10, 'minUsers': 3}, 'medium': {'min': 11, 'max': 50, 'minUsers': 11}, 'large': {'min': 51, 'max': 150, 'minUsers': 51}},
    'base': {'small': 90, 'medium': 179, 'large': 299}, 'perUser': {'small': 37.5, 'medium': 36, 'large': 35}, 'perServer': {'base': 69},
    'extraVeilig': {'perOrg': {'xsmall': 65, 'small': 159, 'medium': 199, 'large': 259}, 'perUser': 19, 'perServer': 49},
    'extraVeiligPlus': {'perOrg': {'xsmall': 149, 'small': 369, 'medium': 445, 'large': 799}, 'perUser': 39, 'perServer': 65},
    'm365Licenses': {
        'businessPremium': {'name': 'Microsoft Business Premium', 'yearly': {'perYear': 247.21, 'perMonth': 21.65}, 'flexible': {'perMonth': 24.75}},
        'businessStandard': {'name': 'Microsoft Business Standard', 'yearly': {'perYear': 140.4, 'perMonth': 12.5}, 'flexible': {'perMonth': 14.25}},
        'businessBasic': {'name': 'Microsoft Business Basic', 'yearly': {'perYear': 67.2, 'perMonth': 5.9}, 'flexible': {'perMonth': 6.75}},
        'exchangeP1': {'name': 'Microsoft Exchange Online P1', 'yearly': {'perYear': 44.4, 'perMonth': 3.9}, 'flexible': {'perMonth': 4.5}},
        'exchangeP2': {'name': 'Microsoft Exchange Online P2', 'yearly': {'perYear': 90, 'perMonth': 7.88}, 'flexible': {'perMonth': 9}},
        'copilot': {'name': 'Microsoft 365 Copilot', 'yearly': {'perYear': 337.2, 'perMonth': 28.1}, 'flexible': {'perMonth': 29.51}}},
}
NIVEAUS = {'none': 'Basis pakket', 'extra': 'Extra Veilig', 'extraPlus': 'Extra Veilig++'}
INBEGREPEN = {
    'none': {'org': ['Beheer & monitoring netwerkcomponenten', 'Documentatiesysteem', 'Jaarlijks basis alignement (Security)', 'Audit: Secure7',
                     'Back-up controle/strategie', 'Rapportage', 'Opvolging alerts'],
             'user': ['Monitoring desktop/notebook', 'Installatie (Microsoft) updates', 'Software t.b.v. remote ondersteuning', 'Antivirus & anti-malware',
                      'Endpoint Detection & Response (EDR)', 'Ransomware detection', 'All-in support']},
    'extra': {'org': ['Beheer Microsoft 365 Intune/Teams/SharePoint', 'SPF, DKIM en DMARC monitoring', 'Jaarlijks alignement t.b.v. NIS2, ISO, AVG'],
              'user': ['SaaS Alerts', 'Security Awareness training', 'BitLocker audit', 'Windows policy audit'],
              'server': ['Endpoint Detection and Response', 'Vulnerability scanner']},
    'extraPlus': {'org': ['Beheer Microsoft 365 Intune/Teams/SharePoint', 'SPF, DKIM en DMARC monitoring', 'Jaarlijks alignement t.b.v. NIS2, ISO, AVG',
                          'Managed UniFi Ultimate Firewall', 'Managed SOC', 'Jaarlijkse netwerk-pentest'],
                  'user': ['SaaS Alerts', 'Security Awareness training', 'BitLocker audit', 'Windows policy audit', 'Managed SOC (user focus)', 'Password manager'],
                  'server': ['Endpoint Detection and Response', 'Vulnerability scanner', 'Managed SOC']},
}


# ---------------------------------------------------------------- prijsmodel van de offertepagina
def _js_object(tekst: str, start: int) -> dict:
    """Object-literal uit geminificeerde JavaScript ({setupCosts:{none:100,...},...}) naar een dict."""
    diepte, i = 0, start
    in_str = None
    while i < len(tekst):
        ch = tekst[i]
        if in_str:
            if ch == '\\':
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in '"\'':
            in_str = ch
        elif ch == '{':
            diepte += 1
        elif ch == '}':
            diepte -= 1
            if diepte == 0:
                break
        i += 1
    js = tekst[start:i + 1]
    js = re.sub(r'([{,])\s*([A-Za-z_$][\w$]*)\s*:', r'\1"\2":', js)       # sleutels tussen aanhalingstekens
    js = re.sub(r'(?<=[:\[,])\s*\.(\d)', r'0.\1', js)                       # .5 -> 0.5
    js = js.replace('!0', 'true').replace('!1', 'false')
    return json.loads(js)


def _van_site() -> dict:
    r = _S.get(f'{SITE}/offerte', timeout=15)
    r.raise_for_status()
    idx = re.search(r'/assets/index-[\w-]+\.js', r.text)
    if not idx:
        raise ValueError('index-script niet gevonden')
    j = _S.get(SITE + idx.group(0), timeout=20).text
    off = re.search(r'assets/Offerte-[\w-]+\.js', j)
    if not off:
        raise ValueError('offerte-script niet gevonden')
    code = _S.get(f'{SITE}/{off.group(0)}', timeout=20).text
    pos = code.find('{setupCosts:')
    if pos < 0:
        raise ValueError('prijsobject niet gevonden')
    m = _js_object(code, pos)
    for k in ('base', 'perUser', 'perServer', 'extraVeilig', 'extraVeiligPlus', 'm365Licenses', 'setupCosts', 'dmarcProtection', 'tiers'):
        if k not in m:
            raise ValueError(f'onderdeel {k} ontbreekt')
    return m


def model(vers: bool = False) -> tuple[dict, str]:
    """(prijsmodel, bron): 'site' (net gelezen), 'bewaard' (laatst gelezen) of 'standaard'."""
    with _lock:
        item = _CACHE.get('m')
        if item and not vers and time.time() - item[0] < 3600:
            return item[1], item[2]
        try:
            m, bron = _van_site(), 'site'
            try:
                if GEDEELD.lees_raw('prijslijst', 3600) != json.dumps(m, sort_keys=True):
                    GEDEELD.schrijf_raw('prijslijst', json.dumps(m, sort_keys=True))
            except Exception:  # noqa: BLE001 - bewaren is een extraatje
                pass
        except Exception as e:  # noqa: BLE001
            log.info('Prijzen offertepagina niet gelezen (%s); terugval', e)
            try:
                w = GEDEELD.lees_raw('prijslijst', 86400)
                m, bron = (json.loads(w), 'bewaard') if w else (STANDAARD, 'standaard')
            except Exception:  # noqa: BLE001
                m, bron = STANDAARD, 'standaard'
        _CACHE['m'] = (time.time(), m, bron)
        return m, bron


# ---------------------------------------------------------------- berekening (zoals de offertepagina)
def _staffel(n: int) -> str:
    return 'small' if n <= 10 else 'medium' if n <= 50 else 'large'


def bereken(m: dict, cfg: dict) -> dict:
    n = max(1, int(cfg.get('users') or 1))
    servers = max(0, int(cfg.get('servers') or 0)) if cfg.get('hasServers') else 0
    niveau = cfg.get('level') if cfg.get('level') in NIVEAUS else 'none'
    st = _staffel(n)
    klein = n <= 2
    teller = n if klein else max(n, int(m['tiers'][st]['minUsers']))   # minimum aantal gebruikers per staffel
    regels = []

    def regel(sleutel, naam, aantal, prijs, eenheid):
        if aantal and prijs:
            regels.append({'key': sleutel, 'name': naam, 'qty': aantal, 'price': round(float(prijs), 2), 'unit': eenheid,
                           'amount': round(float(prijs) * aantal, 2)})
    org = m['base']['small'] / 3 * n if klein else m['base'][st]
    regel('base.org', 'Basis pakket - per organisatie', 1, org, 'organisatie')
    regel('base.user', 'Basis pakket - per gebruiker', teller, m['perUser'][st], 'gebruiker')
    regel('base.server', 'Basis pakket - per server', servers, m['perServer']['base'], 'server')
    if niveau in ('extra', 'extraPlus'):
        p = m['extraVeilig'] if niveau == 'extra' else m['extraVeiligPlus']
        naam = NIVEAUS[niveau]
        po = p['perOrg']['xsmall'] if n <= 4 and p['perOrg'].get('xsmall') is not None else p['perOrg'][st]
        regel(f'{niveau}.org', f'{naam} - per organisatie', 1, po, 'organisatie')
        regel(f'{niveau}.user', f'{naam} - per gebruiker', teller, p['perUser'], 'gebruiker')
        regel(f'{niveau}.server', f'{naam} - per server', servers, p['perServer'], 'server')
    dmarc_setup = 0
    if niveau == 'none' and cfg.get('dmarc'):
        dom = max(1, int(cfg.get('domains') or 1))
        regel('dmarc.first', 'EasyDMARC - eerste domein', 1, m['dmarcProtection']['monthly'], 'domein')
        regel('dmarc.extra', 'EasyDMARC - extra domein', dom - 1, m['dmarcProtection']['extraDomain'], 'domein')
        dmarc_setup = float(m['dmarcProtection']['setup'])
    for k, lic in (m.get('m365Licenses') or {}).items():
        sel = (cfg.get('licenses') or {}).get(k) or {}
        regel(f'lic.{k}.year', f"{lic['name']} (jaarcommitment)", int(sel.get('yearly') or 0), lic['yearly']['perMonth'], 'licentie')
        regel(f'lic.{k}.flex', f"{lic['name']} (maandelijks opzegbaar)", int(sel.get('flexible') or 0), lic['flexible']['perMonth'], 'licentie')
    setup = round(float(m['setupCosts'][niveau]) * n + dmarc_setup, 2)
    return {'lines': regels, 'monthly': round(sum(r['amount'] for r in regels), 2), 'setup': setup, 'setupPerUser': m['setupCosts'][niveau],
            'dmarcSetup': dmarc_setup, 'tier': st, 'countedUsers': teller, 'level': niveau, 'levelName': NIVEAUS[niveau]}


@api('sa.prijzen')
def sa_prijzen(c: Ctx, b: dict) -> dict:
    """Prijsmodel + berekening voor een samenstelling (voor de samensteller)."""
    _zet_auth(c)
    m, bron = model(bool(b.get('fresh')))
    return {'source': bron, 'site': f'{SITE}/offerte', 'levels': NIVEAUS, 'included': INBEGREPEN,
            'licenses': {k: {'name': v['name'], 'year': v['yearly']['perMonth'], 'flex': v['flexible']['perMonth']} for k, v in m['m365Licenses'].items()},
            'calc': bereken(m, b.get('cfg') or {})}


# ---------------------------------------------------------------- contract in Autotask
def _dienst(at, regel: dict, cache: dict) -> int:
    """Autotask-dienst (Service) met de vaste naam van dit onderdeel; ontbreekt hij, dan aanmaken."""
    naam = regel['name'][:150]
    if naam in cache:
        return cache[naam]
    r = at.query('Services', [{'op': 'eq', 'field': 'name', 'value': naam}], ['id', 'isActive'], 5)
    if r:
        cache[naam] = r[0]['id']
        return r[0]['id']
    from .h_contracten import _label
    from .h_sales import getal
    periode = _label(at, 'Services', 'periodType', r'month|maand')
    code = None
    soort = next((getal(p['value']) for p in at.picklists('BillingCodes').get('useType', []) if re.search(r'recurring|service|dienst', str(p.get('label') or ''), re.I)), None)
    if soort is not None:
        try:
            cr = at.query('BillingCodes', [{'op': 'eq', 'field': 'useType', 'value': soort}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id'], 1)
            code = cr[0]['id'] if cr else None
        except ApiFout:
            pass
    body = {'name': naam, 'description': f"Aangemaakt door Microsoft 365 beheer (offertemodel), per {regel['unit']}", 'unitPrice': regel['price'], 'unitCost': 0,
            'periodType': periode, 'isActive': True, 'billingCodeID': code}
    res = at.req('POST', 'Services', {k: v for k, v in body.items() if v is not None})
    sid = (res or {}).get('itemId')
    if not sid:
        raise ApiFout(f'Dienst {naam} niet aangemaakt.')
    log.info('Autotask-dienst aangemaakt: %s', naam)
    cache[naam] = sid
    return sid


@api('sa.contract.samenstellen')
def sa_contract_samenstellen(c: Ctx, b: dict) -> dict:
    """{companyId, companyName?, cfg, start, months}: Full Service-contract (standaardcontract) volgens het offertemodel."""
    from . import h_autotask as A
    from .h_contracten import _actief, _iso, _label, _post_kind, buiten_uren_codes, soort
    _zet_auth(c)
    if not is_sales(c.staat):
        raise ApiFout('Contracten maken doen sales en de app-beheerder.')
    if b.get('companyId') in (None, ''):
        raise ApiFout('Kies de klant.')
    company = int(b['companyId'])
    m, bron = model()
    calc = bereken(m, b.get('cfg') or {})
    if not calc['lines']:
        raise ApiFout('Er staat niets in het contract.')
    at = A._at()
    klant = (at.req('GET', f'Companies/{company}').get('item') or {}).get('companyName') or str(b.get('companyName') or '').strip()
    start = datetime.fromisoformat(str(b.get('start') or datetime.now().strftime('%Y-%m-01'))[:10]).replace(tzinfo=timezone.utc)
    maanden = max(1, int(b.get('months') or 12))
    body = {'companyID': company, 'contractName': f'Full Service - {klant}'.strip(' -')[:100], 'contractType': soort(at, 'full'), 'status': _actief(at),
            'startDate': _iso(start), 'endDate': _iso(start + timedelta(days=round(30.44 * maanden)) - timedelta(days=1)), 'isDefaultContract': True,
            'timeReportingRequiresStartAndStopTimes': 0, 'setupFee': calc['setup'], 'contractPeriodType': _label(at, 'Contracts', 'contractPeriodType', r'month|maand'),
            'description': (f"{calc['levelName']}, {int((b.get('cfg') or {}).get('users') or 1)} gebruiker(s). Samengesteld volgens {SITE}/offerte "
                            f"(prijzen: {bron}). Maandbedrag € {calc['monthly']:.2f}, setup € {calc['setup']:.2f}.")[:2000]}
    r = at.req('POST', 'Contracts', {k: v for k, v in body.items() if v is not None})
    cid = (r or {}).get('itemId')
    if not cid:
        raise ApiFout('Autotask gaf geen contractnummer terug.')
    fouten, diensten, gelukt = [], {}, 0
    for regel in calc['lines']:
        try:
            sid = _dienst(at, regel, diensten)
            _post_kind(at, 'Contracts', cid, 'Services', 'ContractServices', {'contractID': cid, 'serviceID': sid, 'adjustedPrice': regel['price'],
                                                                              'invoiceDescription': f"{regel['qty']} x {regel['name']}"[:1000]})
            if regel['qty'] != 1:   # aantal (eenheden) via een aanpassing per ingangsdatum
                try:
                    at.req('POST', 'ContractServiceAdjustments', {'contractID': cid, 'serviceID': sid, 'effectiveDate': _iso(start), 'unitChange': regel['qty'],
                                                                  'adjustedUnitPrice': regel['price']})
                except ApiFout as e:
                    fouten.append(f"{regel['name']}: aantal {regel['qty']} niet gezet ({str(e)[:100]}); controleer in Autotask")
            gelukt += 1
        except ApiFout as e:
            fouten.append(f"{regel['name']}: {str(e)[:140]}")
    uitgesloten = []
    for code in buiten_uren_codes(at):
        try:
            _post_kind(at, 'Contracts', cid, 'ExclusionBillingCodes', 'ContractExclusionBillingCodes', {'contractID': cid, 'billingCodeID': code['id']})
            uitgesloten.append(code['name'])
        except ApiFout as e:
            fouten.append(f"uitsluiten {code['name']}: {str(e)[:100]}")
    w = GEDEELD.lees_raw('contract-samenstelling', 60)
    try:
        d = json.loads(w) if w else {}
    except ValueError:
        d = {}
    d[str(cid)] = {'company': company, 'cfg': b.get('cfg') or {}, 'monthly': calc['monthly'], 'setup': calc['setup'], 'source': bron, 'at': datetime.now().isoformat(timespec='minutes')}
    GEDEELD.schrijf_raw('contract-samenstelling', json.dumps(d, separators=(',', ':')))
    c.L(f"Full Service-contract voor {klant}: {calc['levelName']}, € {calc['monthly']:.2f} per maand, setup € {calc['setup']:.2f} ({gelukt} onderdelen).")
    return {'contract': {'id': cid, 'name': body['contractName']}, 'calc': calc, 'excluded': uitgesloten, 'errors': fouten}


def vergeet() -> None:
    _CACHE.clear()
