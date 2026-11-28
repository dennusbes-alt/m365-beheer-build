"""Domeinen: overzicht, DNS-controle, toevoegen en verifiëren, standaarddomein, Exchange-domeintype en verwijderen.

Graph /domains (zoals Get-MgDomain / New-MgDomain / Confirm-MgDomain) en Exchange Get/Set-AcceptedDomain.
Wijzigen vereist bij de klant de rol Domain Name Administrator; het Exchange-domeintype de rol Exchange Administrator.
De DNS-controle vraagt de records live op via DNS-over-HTTPS (Cloudflare), dus altijd de actuele stand.
"""
from __future__ import annotations

import re

from .clients import ApiFout, _sessie, parallel
from .context import Ctx, api

DNS_TYPE = {'MX': 15, 'TXT': 16, 'CNAME': 5, 'NS': 2, 'A': 1, 'AAAA': 28, 'SRV': 33, 'CAA': 257}
MS_NS = ('.bdm.microsoftonline.com',)   # nameservers van Microsoft 365 (DNS-hosting door Microsoft)

# Namen die bij DNS bij Microsoft worden opgevraagd (een volledige zone opvragen kan niet via DNS).
ZONE = [('', 'A'), ('', 'AAAA'), ('', 'MX'), ('', 'TXT'), ('', 'CAA'),
        ('www', 'CNAME'), ('www', 'A'), ('www', 'AAAA'), ('mail', 'CNAME'), ('mail', 'A'), ('webmail', 'CNAME'), ('webmail', 'A'),
        ('autodiscover', 'CNAME'), ('enterpriseregistration', 'CNAME'), ('enterpriseenrollment', 'CNAME'), ('lyncdiscover', 'CNAME'), ('sip', 'CNAME'),
        ('selector1._domainkey', 'CNAME'), ('selector2._domainkey', 'CNAME'), ('_dmarc', 'TXT'), ('_mta-sts', 'TXT'), ('mta-sts', 'CNAME'),
        ('_sip._tls', 'SRV'), ('_sipfederationtls._tcp', 'SRV'), ('_autodiscover._tcp', 'SRV'),
        ('ftp', 'A'), ('ftp', 'CNAME'), ('remote', 'A'), ('vpn', 'A'), ('smtp', 'A'), ('smtp', 'CNAME'), ('portal', 'CNAME'), ('portal', 'A'),
        ('shop', 'CNAME'), ('shop', 'A'), ('crm', 'CNAME'), ('_domainconnect', 'CNAME')]


def _dns_ruw(naam: str, soort: str) -> list[dict]:
    """DNS-opvraging met type, TTL en de volledige waarde (MX met prioriteit, SRV/CAA zoals ze zijn)."""
    try:
        r = _sessie().get('https://cloudflare-dns.com/dns-query', params={'name': naam, 'type': soort},
                          headers={'Accept': 'application/dns-json'}, timeout=8)
        uit = []
        for a in r.json().get('Answer') or []:
            if a.get('type') != DNS_TYPE[soort] or str(a.get('name', '')).rstrip('.').lower() != naam.lower():
                continue
            d = str(a.get('data', ''))
            if soort == 'TXT':
                d = ''.join(re.findall(r'"([^"]*)"', d)) or d.strip('"')
            uit.append({'type': soort, 'name': naam, 'value': d.rstrip('.'), 'ttl': a.get('TTL')})
        return uit
    except Exception:  # noqa: BLE001
        return []


def _zone(domein: str) -> list[dict]:
    """Records die van dit domein te vinden zijn. Heeft een naam een CNAME, dan worden A/AAAA daarvan niet apart getoond."""
    taken = {f'{i}': (lambda n=(f'{sub}.{domein}' if sub else domein), t=t: _dns_ruw(n, t)) for i, (sub, t) in enumerate(ZONE)}
    r = parallel(taken)
    alles = [x for i in range(len(ZONE)) for x in (r[str(i)] if isinstance(r[str(i)], list) else [])]
    cnames = {x['name'].lower() for x in alles if x['type'] == 'CNAME'}
    gezien, uit = set(), []
    for x in alles:
        k = (x['type'], x['name'].lower(), x['value'].lower())
        if k in gezien or (x['type'] in ('A', 'AAAA') and x['name'].lower() in cnames):
            continue
        gezien.add(k)
        uit.append(x)
    return uit
FOUT_ROL = 'Hiervoor heb je bij deze klant de rol Domain Name Administrator nodig. Controleer de GDAP-relatie.'
DIENSTEN = {'Email': 'E-mail', 'OfficeCommunicationsOnline': 'Teams/Skype', 'Intune': 'Intune', 'SharePoint': 'SharePoint',
            'OrgIdAuthentication': 'Aanmelden', 'Yammer': 'Viva Engage'}


def _dns(naam: str, soort: str) -> list[str]:
    """Live DNS-opvraging (zelfde bron als bij DKIM). Geeft de waarden zonder punt aan het eind."""
    try:
        r = _sessie().get('https://cloudflare-dns.com/dns-query', params={'name': naam, 'type': soort},
                          headers={'Accept': 'application/dns-json'}, timeout=8)
        uit = []
        for a in r.json().get('Answer') or []:
            if a.get('type') != DNS_TYPE[soort]:
                continue
            d = str(a.get('data', ''))
            if soort == 'TXT':
                d = ''.join(re.findall(r'"([^"]*)"', d)) or d.strip('"')
            elif soort == 'MX':
                d = d.split()[-1]
            uit.append(d.rstrip('.'))
        return uit
    except Exception:  # noqa: BLE001 - DNS niet bereikbaar: als 'onbekend' tonen
        return ['?']


def _tenant_bijwerken(c: Ctx) -> None:
    """Na een wijziging de domeinen van de klant in de app bijwerken (bijv. voor 'Nieuwe gebruiker')."""
    try:
        doms = c.g.all('/domains?$select=id,isDefault,isInitial,isVerified')
        t = c.t
        t.domeinen = sorted([{'id': d['id'], 'def': bool(d.get('isDefault')), 'initial': bool(d.get('isInitial'))} for d in doms if d.get('isVerified')],
                            key=lambda d: (not d['def'], d['id']))
        t.standaard_domein = next((d['id'] for d in t.domeinen if d['def']), t.standaard_domein)
    except ApiFout:
        pass


def _rol(e: ApiFout) -> ApiFout:
    return ApiFout(FOUT_ROL, e.status) if e.status in (401, 403) else e


def _domein(d: dict, acc: dict) -> dict:
    a = acc.get(d['id'].lower()) or {}
    return {'id': d['id'], 'default': bool(d.get('isDefault')), 'initial': bool(d.get('isInitial')), 'verified': bool(d.get('isVerified')),
            'auth': d.get('authenticationType') or 'Managed', 'services': d.get('supportedServices') or [],
            'pwdays': d.get('passwordValidityPeriodInDays'), 'exoType': a.get('DomainType') or '', 'exoDefault': bool(a.get('Default')),
            'matchSub': bool(a.get('MatchSubDomains'))}


def _accepted(c: Ctx, vers: bool = False) -> dict | None:
    """Exchange-domeintypen. Nooit wachten: is Exchange nog niet klaar, dan None (de interface vult het later aan).
    Get-AcceptedDomain wordt al bij het openen van de klant opgehaald en 5 minuten hergebruikt."""
    t = c.t
    if not t.exo_klaar.is_set():
        return None
    if not t.exo:
        return {}
    try:
        l = t.cache('accepted', lambda: t.exo.run('Get-AcceptedDomain'), 300, vers)
        return {str(a.get('DomainName') or a.get('Name') or '').lower(): a for a in l}
    except ApiFout:
        return {}


@api('dom.list')
def dom_list(c: Ctx, b: dict) -> dict:
    r = parallel({'d': lambda: c.g.all('/domains'), 'a': lambda: _accepted(c, bool(b.get('fresh')))})
    if isinstance(r['d'], Exception):
        raise r['d']
    acc = r['a'] if isinstance(r['a'], dict) else {}
    l = [_domein(d, acc) for d in r['d']]
    l.sort(key=lambda d: (not d['default'], d['initial'], d['id']))
    return {'domains': l, 'exo': bool(acc), 'exoPending': r['a'] is None}


def _controle(verwacht: list[dict], domein: str) -> list[dict]:
    """Verwachte records (van Microsoft) naast de werkelijke DNS leggen. Alle opvragingen tegelijk."""
    taken = {}
    for i, v in enumerate(verwacht):
        taken[str(i)] = (lambda v=v: _dns(v['name'], v['type']))
    gevonden = parallel(taken)
    uit = []
    for i, v in enumerate(verwacht):
        w = gevonden.get(str(i))
        w = w if isinstance(w, list) else ['?']
        if w == ['?']:
            status = 'onbekend'
        elif v['type'] == 'MX':
            # Microsoft gebruikt naast <domein>.mail.protection.outlook.com ook het nieuwere <domein>.<x>.mx.microsoft
            m365 = [x for x in w if x.lower() == v['value'].lower() or x.lower().endswith(('.mail.protection.outlook.com', '.mx.microsoft'))]
            status = ('ok' if len(m365) == len(w) else 'controleren') if m365 else ('afwijkend' if w else 'ontbreekt')
        elif v['type'] == 'TXT' and v['value'].lower().startswith('v=spf1'):
            spf = [x for x in w if x.lower().startswith('v=spf1')]
            w = spf
            if len(spf) > 1:
                status = 'afwijkend'   # meer dan één SPF-record is ongeldig
            elif any('include:spf.protection.outlook.com' in x.lower() for x in spf):
                status = 'ok'
            else:   # bijv. een SPF-dienst (EasyDMARC, dmarcian) die Microsoft via een eigen include regelt
                status = 'controleren' if spf else 'ontbreekt'
        elif v['type'] == 'TXT' and v['name'].startswith('_dmarc.'):
            w = [x for x in w if x.lower().startswith('v=dmarc1')]
            status = 'ok' if w else 'ontbreekt'
        elif v['type'] == 'TXT':
            status = 'ok' if any(x == v['value'] for x in w) else ('afwijkend' if w else 'ontbreekt')
        else:   # CNAME
            if v.get('vrij'):   # DKIM: Microsoft bepaalt de exacte waarde; aanwezig = goed
                status = 'ok' if w else 'ontbreekt'
            else:
                status = 'ok' if any(x.lower() == v['value'].lower() for x in w) else ('afwijkend' if w else 'ontbreekt')
        uit.append({**v, 'found': w, 'status': status})
    return uit


@api('dom.get')
def dom_get(c: Ctx, b: dict) -> dict:
    """Details van één domein met de DNS-controle (verwachte records van Microsoft tegen de live DNS)."""
    did = str(b['id'])
    r = parallel({'svc': lambda: c.g.all(f'/domains/{did}/serviceConfigurationRecords'),
                  'ns': lambda: _dns_ruw(did, 'NS'),
                  'ver': lambda: c.g.all(f'/domains/{did}/verificationDnsRecords'),
                  'ref': lambda: c.g.get(f'/domains/{did}/domainNameReferences?$select=id&$top=999').get('value', [])})
    gegevens = {'id': did}
    if not did.lower().endswith('.onmicrosoft.com'):
        verwacht = []
        svc = r['svc'] if isinstance(r['svc'], list) else []
        for s in svc:
            if s.get('supportedService') not in ('Email', 'Intune'):
                continue   # oude Skype-records (SRV, sip) zijn niet meer nodig
            t = str(s.get('recordType') or '').upper().replace('CNAME', 'CNAME')
            naam = s.get('label') or did
            if t == 'MX':
                verwacht.append({'type': 'MX', 'name': naam, 'value': s.get('mailExchange', ''), 'service': 'E-mail',
                                 'extra': f"Prioriteit {s.get('preference', 0)}"})
            elif t == 'TXT':
                verwacht.append({'type': 'TXT', 'name': naam, 'value': s.get('text', ''), 'service': 'E-mail (SPF)'})
            elif t == 'CNAME':
                verwacht.append({'type': 'CNAME', 'name': naam, 'value': s.get('canonicalName', ''),
                                 'service': DIENSTEN.get(s.get('supportedService'), s.get('supportedService'))})
        # Aanbevolen beveiliging, die Microsoft niet zelf opgeeft
        verwacht.append({'type': 'TXT', 'name': f'_dmarc.{did}', 'value': f'v=DMARC1; p=quarantine; rua=mailto:dmarc@{did}',
                         'service': 'DMARC (aanbevolen)'})
        for sel in ('selector1', 'selector2'):
            verwacht.append({'type': 'CNAME', 'name': f'{sel}._domainkey.{did}', 'value': 'zie Bedreigingsbeheer > DKIM',
                             'service': 'DKIM', 'vrij': True})
        gegevens['dns'] = _controle(verwacht, did)
    ver = r['ver'] if isinstance(r['ver'], list) else []
    gegevens['verification'] = [{'type': str(v.get('recordType') or '').upper(), 'name': v.get('label') or did,
                                 'value': v.get('text') or v.get('mailExchange') or '', 'ttl': v.get('ttl') or 3600}
                                for v in ver if str(v.get('recordType') or '').lower() == 'txt']
    gegevens['references'] = len(r['ref']) if isinstance(r['ref'], list) else None
    ns = [x['value'] for x in r['ns']] if isinstance(r['ns'], list) else []
    gegevens['nameservers'] = ns
    gegevens['msDns'] = bool(ns) and all(x.lower().endswith(MS_NS) for x in ns)
    if gegevens['msDns']:
        gegevens['zone'] = _zone(did)
        initieel = next((d['id'] for d in c.t.domeinen if d.get('initial')), '')
        gegevens['links'] = {
            # Beheercentrum van de klant openen via de partnersessie (werkt met GDAP)
            'klant': f'https://admin.microsoft.com/Partner/BeginClientSession.aspx?CTID={c.t.id}&CSDEST=o365admincenter',
            # Direct naar de DNS-records van dit domein in het beheercentrum van de klant
            'dns': f'https://admin.microsoft.com/?delegatedOrg={initieel}#/Domains/Details/{did}' if initieel else '',
        }
    return gegevens


@api('dom.add')
def dom_add(c: Ctx, b: dict) -> dict:
    c.t.weg('accepted')
    naam = str(b.get('id') or '').strip().lower()
    if not re.fullmatch(r'(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}', naam):
        raise ApiFout('Vul een geldige domeinnaam in, bijvoorbeeld bedrijf.nl.')
    try:
        c.g.post('/domains', {'id': naam})
    except ApiFout as e:
        raise _rol(e)
    c.L(f'Domein {naam} toegevoegd. Voeg het TXT-record toe bij de DNS-provider en klik daarna op Verifiëren.')
    return dom_get(c, {'id': naam})


@api('dom.verify')
def dom_verify(c: Ctx, b: dict) -> dict:
    c.t.weg('accepted')
    did = str(b['id'])
    try:
        c.g.post(f'/domains/{did}/verify')
    except ApiFout as e:
        if e.status in (400, 404) and 'verif' in str(e).lower():
            raise ApiFout(f'{did} kon nog niet geverifieerd worden: het TXT-record is (nog) niet gevonden. '
                          'DNS-wijzigingen kunnen enkele minuten tot een uur duren.')
        raise _rol(e)
    c.L(f'{did} is geverifieerd.')
    _tenant_bijwerken(c)
    return {}


@api('dom.default')
def dom_default(c: Ctx, b: dict) -> dict:
    c.t.weg('accepted')
    did = str(b['id'])
    try:
        c.g.patch(f'/domains/{did}', {'isDefault': True})
    except ApiFout as e:
        raise _rol(e)
    c.L(f'{did} is nu het standaarddomein (voor nieuwe gebruikers).')
    _tenant_bijwerken(c)
    return {}


@api('dom.exotype')
def dom_exotype(c: Ctx, b: dict) -> dict:
    c.t.weg('accepted')
    """Exchange: Gezaghebbend (alle postvakken in Microsoft 365) of Intern relais (deel van de postvakken elders)."""
    did, soort = str(b['id']), str(b['type'])
    if soort not in ('Authoritative', 'InternalRelay'):
        raise ApiFout('Onbekend domeintype.')
    c.x.run('Set-AcceptedDomain', Identity=did, DomainType=soort)
    c.L(f"Exchange-domeintype van {did}: {'Gezaghebbend' if soort == 'Authoritative' else 'Intern relais'}.")
    return {}


@api('dom.delete')
def dom_delete(c: Ctx, b: dict) -> dict:
    c.t.weg('accepted')
    did = str(b['id'])
    try:
        c.g.delete(f'/domains/{did}')
    except ApiFout as e:
        if e.status in (400, 409) or 'reference' in str(e).lower() or 'in use' in str(e).lower():
            raise ApiFout(f'{did} is nog in gebruik (gebruikers, groepen of apps met een adres op dit domein). '
                          'Verander die eerst naar een ander domein.')
        raise _rol(e)
    c.L(f'Domein {did} verwijderd.')
    _tenant_bijwerken(c)
    return {}
