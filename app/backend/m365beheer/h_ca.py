"""Voorwaardelijke toegang (Conditional Access): beleid bekijken, bewerken, aanmaken, aan/uit/alleen rapporteren,
verwijderen, en benoemde locaties (IP-bereiken en landen).

Graph v1.0: /identity/conditionalAccess/policies en /identity/conditionalAccess/namedLocations,
authenticatiesterktes via /policies/authenticationStrengthPolicies, rollen via /directoryRoleTemplates.
Rechten: Policy.Read.All + Policy.ReadWrite.ConditionalAccess. GDAP-rol bij de klant: Conditional Access Administrator
(of Security Administrator). Vereist Entra ID P1 bij de klant.

Bewerken werkt op een vereenvoudigd model (`_model` <-> `_naar_graph`). Bij een bestaand beleid wordt het model in
het ORIGINELE beleid gezet, zodat instellingen die het scherm niet kent (apparaatfilters, authenticatiestromen e.d.)
behouden blijven.
"""
from __future__ import annotations

import copy
import ipaddress
import logging

from .clients import ApiFout, parallel
from .context import Ctx, api

log = logging.getLogger('m365beheer')
CA = '/identity/conditionalAccess'

GEEN_CA = ('Voorwaardelijke toegang is bij deze klant niet beschikbaar of de rechten ontbreken. Nodig: Entra ID P1 (bijv. in '
           'Microsoft 365 Business Premium) en de GDAP-rol Conditional Access Administrator of Security Administrator.')
STATUS = {'enabled': 'Aan', 'disabled': 'Uit', 'enabledForReportingButNotEnforced': 'Alleen rapporteren'}
CONTROLES = {'mfa': 'MFA vereisen', 'compliantDevice': 'Apparaat moet compliant zijn', 'domainJoinedDevice': 'Hybride Entra-apparaat',
             'approvedApplication': 'Goedgekeurde client-app', 'compliantApplication': 'App-beveiligingsbeleid', 'passwordChange': 'Wachtwoord wijzigen'}
# Gasten en externe gebruikers (alle soorten), voor 'gasten opnemen'
ALLE_EXTERN = 'internalGuest,b2bCollaborationGuest,b2bCollaborationMember,b2bDirectConnectUser,otherExternalUser,serviceProvider'
ALLE_TENANTS = {'@odata.type': '#microsoft.graph.conditionalAccessAllExternalTenants', 'membershipKind': 'all'}


def _fout(e: ApiFout) -> ApiFout:
    t = str(e)
    if e.status in (401, 403) or 'premium' in t.lower() or 'license' in t.lower():
        if 'scope' in t.lower() or 'not authorized' in t.lower():
            return ApiFout('De app mist nog het recht Policy.ReadWrite.ConditionalAccess. Bij Justdata zelf: opzetten_app.py opnieuw draaien '
                           'en opnieuw aanmelden; bij een klant vult de app de rechten zelf aan (probeer het over een paar minuten opnieuw).', e.status)
        return ApiFout(GEEN_CA + f' (Microsoft: {t[:160]})', e.status)
    return e


def _ca(c: Ctx, fn):
    """Bij een weigering (401/403) bij een klant: koppelingsrechten aanvullen, verse tokens en één keer opnieuw."""
    try:
        return fn()
    except ApiFout as e:
        if e.status not in (401, 403) or c.t.id == c.staat.auth.home_tenant:
            raise _fout(e) from None
        st = c.t.rechten_nu()
        c.staat.auth.vergeet(c.t.id)
        log.info('Voorwaardelijke toegang geweigerd bij %s, rechten: %s; opnieuw', c.t.naam, st)
        try:
            return fn()
        except ApiFout as e2:
            raise _fout(e2) from None


# ---------------------------------------------------------------- Lezen
def _namen(c: Ctx, ids: set) -> dict:
    ids = [i for i in ids if i and len(i) == 36]
    uit: dict = {}
    for i in range(0, len(ids), 900):
        try:
            for o in c.g.post('/directoryObjects/getByIds', {'ids': ids[i:i + 900], 'types': ['user', 'group', 'servicePrincipal']}).get('value') or []:
                uit[o['id']] = o.get('displayName') or o.get('userPrincipalName') or o['id']
                if o.get('appId'):
                    uit[o['appId']] = o.get('displayName') or o['appId']
        except ApiFout as e:
            log.info('CA-namen: %s', e)
    return uit


def _lijst(ip_of_land: dict) -> dict:
    o = ip_of_land
    soort = 'ip' if 'ipNamedLocation' in (o.get('@odata.type') or '') else 'country'
    return {'id': o['id'], 'name': o.get('displayName', ''), 'type': soort, 'trusted': bool(o.get('isTrusted')),
            'ranges': [r.get('cidrAddress') for r in o.get('ipRanges') or [] if r.get('cidrAddress')],
            'countries': o.get('countriesAndRegions') or [], 'unknown': bool(o.get('includeUnknownCountriesAndRegions')),
            'method': o.get('countryLookupMethod') or 'clientIpAddress', 'modified': o.get('modifiedDateTime') or o.get('createdDateTime') or ''}


@api('ca.list')
def ca_list(c: Ctx, b: dict) -> dict:
    def ophalen():
        g = c.g
        r = parallel({
            'pol': lambda: g.all(f'{CA}/policies?$top=200'),
            'loc': lambda: g.all(f'{CA}/namedLocations?$top=200'),
            'rollen': lambda: g.all('/directoryRoleTemplates?$select=id,displayName'),
            'sterkte': lambda: g.all("/policies/authenticationStrengthPolicies?$select=id,displayName,policyType"),
        })
        if isinstance(r['pol'], Exception):
            raise r['pol']
        return r
    r = _ca(c, ophalen)
    rollen = {x['id']: x['displayName'] for x in (r['rollen'] if isinstance(r['rollen'], list) else [])}
    locs = [_lijst(x) for x in (r['loc'] if isinstance(r['loc'], list) else [])]
    lnaam = {x['id']: x['name'] for x in locs}
    sterktes = [{'id': x['id'], 'name': x.get('displayName', ''), 'builtIn': x.get('policyType') == 'builtIn'} for x in (r['sterkte'] if isinstance(r['sterkte'], list) else [])]
    ids = set()
    for p in r['pol']:
        u = (p.get('conditions') or {}).get('users') or {}
        a = (p.get('conditions') or {}).get('applications') or {}
        for k in ('includeUsers', 'excludeUsers', 'includeGroups', 'excludeGroups'):
            ids.update(u.get(k) or [])
        for k in ('includeApplications', 'excludeApplications'):
            ids.update(a.get(k) or [])
    namen = _namen(c, ids)
    namen.update(rollen)
    namen.update(lnaam)
    namen.update({'All': 'Alle', 'None': 'Geen', 'GuestsOrExternalUsers': 'Gasten en externe gebruikers', 'Office365': 'Office 365',
                  'MicrosoftAdminPortals': 'Microsoft-beheerportals', 'AllTrusted': 'Alle vertrouwde locaties'})
    pols = [dict(_model(p), modified=p.get('modifiedDateTime') or p.get('createdDateTime') or '', summary=_samenvatting(p, namen)) for p in r['pol']]
    pols.sort(key=lambda x: x['name'].lower())
    return {'policies': pols, 'locations': sorted(locs, key=lambda x: x['name'].lower()), 'roles': sorted([{'id': k, 'name': v} for k, v in rollen.items()], key=lambda x: x['name']),
            'strengths': sterktes, 'names': namen, 'portal': f'https://entra.microsoft.com/{c.t.id}/#view/Microsoft_AAD_ConditionalAccess/ConditionalAccessBlade/~/Policies'}


@api('ca.apps')
def ca_apps(c: Ctx, b: dict) -> dict:
    """Bedrijfsapps / Microsoft-apps (service principals) om een beleid op te richten."""
    lijst = c.t.cache('ca.apps', lambda: _ca(c, lambda: c.g.all('/servicePrincipals?$select=appId,displayName,servicePrincipalType&$top=999')), 600)
    return {'apps': sorted([{'id': x['appId'], 'name': x.get('displayName') or x['appId']} for x in lijst if x.get('appId') and x.get('servicePrincipalType') == 'Application'],
                           key=lambda x: x['name'].lower())}


# ---------------------------------------------------------------- Model <-> Graph
def _isspecial(lst, *w):
    return any(x in w for x in (lst or []))


def _model(p: dict) -> dict:
    """Graph-beleid -> eenvoudig model voor het scherm."""
    cnd = p.get('conditions') or {}
    u = cnd.get('users') or {}
    a = cnd.get('applications') or {}
    inc = u.get('includeUsers') or []
    ig = u.get('includeGuestsOrExternalUsers') or {}
    eg = u.get('excludeGuestsOrExternalUsers') or {}
    if 'All' in inc:
        wie = 'all'
    elif 'GuestsOrExternalUsers' in inc or (ig and not (set(inc) - {'None'}) and not u.get('includeGroups') and not u.get('includeRoles')):
        wie = 'guests'
    elif 'None' in inc and not u.get('includeGroups') and not u.get('includeRoles') and not ig:
        wie = 'none'
    else:
        wie = 'select'
    ia = a.get('includeApplications') or []
    if a.get('includeUserActions'):
        wat = 'action'
    elif 'All' in ia:
        wat = 'all'
    elif ia == ['Office365']:
        wat = 'office'
    elif ia == ['MicrosoftAdminPortals']:
        wat = 'admin'
    elif not ia or ia == ['None']:
        wat = 'none'
    else:
        wat = 'select'
    pl = cnd.get('platforms') or {}
    lo = cnd.get('locations') or {}
    gc = p.get('grantControls') or {}
    sc = p.get('sessionControls') or {}
    sif = sc.get('signInFrequency') or {}
    pb = sc.get('persistentBrowser') or {}
    ctrl = gc.get('builtInControls') or []
    return {
        'id': p.get('id'), 'name': p.get('displayName', ''), 'state': p.get('state', 'disabled'),
        'users': {'include': wie, 'includeUsers': [x for x in inc if x not in ('All', 'None', 'GuestsOrExternalUsers')],
                  'includeGroups': u.get('includeGroups') or [], 'includeRoles': u.get('includeRoles') or [],
                  'excludeUsers': [x for x in u.get('excludeUsers') or [] if x != 'GuestsOrExternalUsers'],
                  'excludeGroups': u.get('excludeGroups') or [], 'excludeRoles': u.get('excludeRoles') or [],
                  'excludeGuests': 'GuestsOrExternalUsers' in (u.get('excludeUsers') or []) or (bool(eg) and 'b2bCollaborationGuest' in str(eg.get('guestOrExternalUserTypes'))),
                  'excludeServiceProvider': bool(eg) and 'serviceProvider' in str(eg.get('guestOrExternalUserTypes'))},
        'apps': {'include': wat, 'includeApps': [x for x in ia if x not in ('All', 'None', 'Office365', 'MicrosoftAdminPortals')],
                 'excludeApps': a.get('excludeApplications') or [], 'action': (a.get('includeUserActions') or [''])[0]},
        'clientAppTypes': [x for x in cnd.get('clientAppTypes') or [] if x != 'all'],
        'platforms': {'include': pl.get('includePlatforms') or [], 'exclude': pl.get('excludePlatforms') or []},
        'locations': {'include': lo.get('includeLocations') or [], 'exclude': lo.get('excludeLocations') or []},
        'signInRisk': cnd.get('signInRiskLevels') or [], 'userRisk': cnd.get('userRiskLevels') or [],
        'grant': {'block': 'block' in ctrl, 'controls': [x for x in ctrl if x != 'block'], 'operator': gc.get('operator') or 'OR',
                  'strength': ((gc.get('authenticationStrength') or {}).get('id')) or ''},
        'session': {'frequency': (sif.get('value') if sif.get('isEnabled') and sif.get('frequencyInterval') != 'everyTime' else None),
                    'frequencyType': sif.get('type') or 'hours', 'everyTime': bool(sif.get('isEnabled')) and sif.get('frequencyInterval') == 'everyTime',
                    'persistentBrowser': pb.get('mode') if pb.get('isEnabled') else '',
                    'appEnforced': bool((sc.get('applicationEnforcedRestrictions') or {}).get('isEnabled'))},
    }


def _ids(lst) -> list[str]:
    return [str(x) for x in (lst or []) if x]


def _naar_graph(m: dict, basis: dict | None = None) -> dict:
    """Model -> Graph-body. Met `basis` (het huidige beleid) blijven onbekende instellingen behouden."""
    p = copy.deepcopy(basis or {})
    naam = str(m.get('name') or '').strip()
    if not naam:
        raise ApiFout('Geef het beleid een naam.')
    state = m.get('state') if m.get('state') in STATUS else 'enabledForReportingButNotEnforced'
    cnd = p.get('conditions') or {}
    # Gebruikers
    mu = m.get('users') or {}
    u = dict(cnd.get('users') or {})
    wie = mu.get('include') or 'select'
    u['includeUsers'] = ['All'] if wie == 'all' else ['None'] if wie == 'none' else _ids(mu.get('includeUsers'))
    u['includeGroups'] = [] if wie in ('all', 'none', 'guests') else _ids(mu.get('includeGroups'))
    u['includeRoles'] = [] if wie in ('all', 'none', 'guests') else _ids(mu.get('includeRoles'))
    u['includeGuestsOrExternalUsers'] = {'guestOrExternalUserTypes': ALLE_EXTERN, 'externalTenants': ALLE_TENANTS} if wie == 'guests' else None
    if wie == 'guests':
        u['includeUsers'] = []
    if wie == 'select' and not (u['includeUsers'] or u['includeGroups'] or u['includeRoles']):
        raise ApiFout('Kies minstens één gebruiker, groep of rol (of kies "Alle gebruikers").')
    u['excludeUsers'] = _ids(mu.get('excludeUsers'))
    u['excludeGroups'] = _ids(mu.get('excludeGroups'))
    u['excludeRoles'] = _ids(mu.get('excludeRoles'))
    soorten = []
    if mu.get('excludeGuests'):
        soorten += ['internalGuest', 'b2bCollaborationGuest', 'b2bCollaborationMember', 'b2bDirectConnectUser', 'otherExternalUser']
    if mu.get('excludeServiceProvider'):
        soorten.append('serviceProvider')
    u['excludeGuestsOrExternalUsers'] = {'guestOrExternalUserTypes': ','.join(soorten), 'externalTenants': ALLE_TENANTS} if soorten else None
    cnd['users'] = u
    # Apps
    ma = m.get('apps') or {}
    a = dict(cnd.get('applications') or {})
    wat = ma.get('include') or 'all'
    if wat == 'action':
        act = ma.get('action') or 'urn:user:registersecurityinfo'
        a.update(includeApplications=[], excludeApplications=[], includeUserActions=[act])
    else:
        a['includeUserActions'] = []
        a['includeApplications'] = {'all': ['All'], 'office': ['Office365'], 'admin': ['MicrosoftAdminPortals'], 'none': ['None']}.get(wat) or _ids(ma.get('includeApps'))
        if not a['includeApplications']:
            raise ApiFout('Kies minstens één app (of "Alle cloud-apps").')
        a['excludeApplications'] = _ids(ma.get('excludeApps'))
    cnd['applications'] = a
    # Overige voorwaarden
    cat = [x for x in m.get('clientAppTypes') or [] if x in ('browser', 'mobileAppsAndDesktopClients', 'exchangeActiveSync', 'other')]
    cnd['clientAppTypes'] = cat or ['all']
    pl = m.get('platforms') or {}
    if pl.get('include'):
        cnd['platforms'] = {'includePlatforms': pl['include'], 'excludePlatforms': pl.get('exclude') or []}
    else:
        cnd['platforms'] = None
    lo = m.get('locations') or {}
    if lo.get('include'):
        cnd['locations'] = {'includeLocations': lo['include'], 'excludeLocations': lo.get('exclude') or []}
    else:
        cnd['locations'] = None
    cnd['signInRiskLevels'] = [x for x in m.get('signInRisk') or [] if x in ('low', 'medium', 'high')]
    cnd['userRiskLevels'] = [x for x in m.get('userRisk') or [] if x in ('low', 'medium', 'high')]
    p['conditions'] = cnd
    # Toegang verlenen / blokkeren
    mg = m.get('grant') or {}
    if mg.get('block'):
        gc = {'operator': 'OR', 'builtInControls': ['block']}
    else:
        ctrl = [x for x in mg.get('controls') or [] if x in CONTROLES]
        gc = {'operator': 'AND' if mg.get('operator') == 'AND' else 'OR', 'builtInControls': ctrl}
        if mg.get('strength'):
            gc['authenticationStrength'] = {'id': str(mg['strength'])}
            gc['builtInControls'] = [x for x in ctrl if x != 'mfa']   # MFA en een sterkte gaan niet samen
        if not gc['builtInControls'] and not gc.get('authenticationStrength'):
            gc = None
    p['grantControls'] = gc
    # Sessie
    ms = m.get('session') or {}
    sc = dict(p.get('sessionControls') or {})
    if ms.get('everyTime'):
        sc['signInFrequency'] = {'isEnabled': True, 'frequencyInterval': 'everyTime', 'authenticationType': 'primaryAndSecondaryAuthentication'}
    elif ms.get('frequency'):
        n = int(ms['frequency'])
        typ = 'days' if ms.get('frequencyType') == 'days' else 'hours'
        if n < 1 or (typ == 'days' and n > 365) or (typ == 'hours' and n > 23):
            raise ApiFout('Aanmeldfrequentie: 1-23 uur of 1-365 dagen.')
        sc['signInFrequency'] = {'isEnabled': True, 'value': n, 'type': typ, 'frequencyInterval': 'timeBased', 'authenticationType': 'primaryAndSecondaryAuthentication'}
    else:
        sc.pop('signInFrequency', None)
    if ms.get('persistentBrowser') in ('always', 'never'):
        sc['persistentBrowser'] = {'isEnabled': True, 'mode': ms['persistentBrowser']}
    else:
        sc.pop('persistentBrowser', None)
    if ms.get('appEnforced'):
        sc['applicationEnforcedRestrictions'] = {'isEnabled': True}
    else:
        sc.pop('applicationEnforcedRestrictions', None)
    sc = {k: v for k, v in sc.items() if v and not k.startswith('@')}
    p['sessionControls'] = sc or None
    if not gc and not sc:
        raise ApiFout('Kies wat er moet gebeuren: blokkeren, een vereiste (bijv. MFA) of een sessie-instelling.')
    p['displayName'] = naam[:256]
    p['state'] = state
    for k in ('id', 'createdDateTime', 'modifiedDateTime', 'templateId', '@odata.context', 'partialEnablementStrategy', 'deletedDateTime'):
        p.pop(k, None)
    return p


def _samenvatting(p: dict, namen: dict) -> dict:
    m = _model(p)
    n = lambda lst: [namen.get(x, x) for x in lst]   # noqa: E731
    mu, ma = m['users'], m['apps']
    wie = {'all': ['Alle gebruikers'], 'none': ['Niemand'], 'guests': ['Gasten en externe gebruikers']}.get(mu['include']) or \
        n(mu['includeUsers']) + n(mu['includeGroups']) + n(mu['includeRoles'])
    uit = n(mu['excludeUsers']) + n(mu['excludeGroups']) + n(mu['excludeRoles']) + (['gasten'] if mu['excludeGuests'] else []) + \
        (['beheerders via GDAP'] if mu['excludeServiceProvider'] else [])
    wat = {'all': ['Alle cloud-apps'], 'office': ['Office 365'], 'admin': ['Microsoft-beheerportals'], 'none': ['Geen'],
           'action': ['Beveiligingsgegevens registreren' if 'security' in ma['action'] else 'Apparaat registreren']}.get(ma['include']) or n(ma['includeApps'])
    g = m['grant']
    dan = ['Blokkeren'] if g['block'] else [CONTROLES.get(x, x) for x in g['controls']] + (['Authenticatiesterkte'] if g['strength'] else [])
    if m['session']['frequency']:
        dan.append(f"Opnieuw aanmelden na {m['session']['frequency']} {'dagen' if m['session']['frequencyType'] == 'days' else 'uur'}")
    if m['session']['everyTime']:
        dan.append('Elke keer opnieuw aanmelden')
    if m['session']['persistentBrowser']:
        dan.append('Browsersessie ' + ('blijft' if m['session']['persistentBrowser'] == 'always' else 'blijft niet') + ' aangemeld')
    voorw = []
    if m['locations']['include']:
        voorw.append('Locatie: ' + ', '.join(n(m['locations']['include'])) + (' behalve ' + ', '.join(n(m['locations']['exclude'])) if m['locations']['exclude'] else ''))
    if m['platforms']['include']:
        voorw.append('Platform: ' + ', '.join(m['platforms']['include']))
    if m['clientAppTypes']:
        voorw.append('Client-apps: ' + ', '.join(m['clientAppTypes']))
    if m['signInRisk']:
        voorw.append('Aanmeldrisico: ' + ', '.join(m['signInRisk']))
    if m['userRisk']:
        voorw.append('Gebruikersrisico: ' + ', '.join(m['userRisk']))
    return {'who': wie, 'except': uit, 'apps': wat, 'then': dan, 'conditions': voorw}


# ---------------------------------------------------------------- Wijzigen
@api('ca.save')
def ca_save(c: Ctx, b: dict) -> dict:
    m = b.get('policy') or {}
    pid = str(m.get('id') or '')
    if pid:
        huidig = _ca(c, lambda: c.g.get(f'{CA}/policies/{pid}'))
        body = _naar_graph(m, huidig)
        _ca(c, lambda: c.g.patch(f'{CA}/policies/{pid}', body))
        c.L(f"Beleid voor voorwaardelijke toegang '{body['displayName']}' gewijzigd ({STATUS[body['state']]}).")
        return {'id': pid}
    body = _naar_graph(m)
    r = _ca(c, lambda: c.g.post(f'{CA}/policies', body))
    c.L(f"Beleid voor voorwaardelijke toegang '{body['displayName']}' aangemaakt ({STATUS[body['state']]}).")
    return {'id': (r or {}).get('id')}


@api('ca.state')
def ca_state(c: Ctx, b: dict) -> dict:
    pid, st = str(b.get('id') or ''), b.get('state')
    if not pid or st not in STATUS:
        raise ApiFout('Onbekend beleid of status.')
    _ca(c, lambda: c.g.patch(f'{CA}/policies/{pid}', {'state': st}))
    c.L(f"Beleid '{b.get('name') or pid}' staat nu op: {STATUS[st]}.")
    return {}


@api('ca.delete')
def ca_delete(c: Ctx, b: dict) -> dict:
    pid = str(b.get('id') or '')
    if not pid:
        raise ApiFout('Geen beleid gekozen.')
    _ca(c, lambda: c.g.delete(f'{CA}/policies/{pid}'))
    c.L(f"Beleid voor voorwaardelijke toegang '{b.get('name') or pid}' verwijderd.")
    return {}


# ---------------------------------------------------------------- Benoemde locaties
def _cidr(t: str) -> dict:
    t = t.strip()
    try:
        net = ipaddress.ip_network(t if '/' in t else t + ('/32' if ':' not in t else '/128'), strict=False)
    except ValueError:
        raise ApiFout(f'Ongeldig IP-adres of bereik: {t}') from None
    if net.version == 4 and net.prefixlen < 8:
        raise ApiFout(f'Bereik {t} is te groot (Microsoft staat minimaal /8 toe).')
    return {'@odata.type': '#microsoft.graph.iPv4CidrRange' if net.version == 4 else '#microsoft.graph.iPv6CidrRange', 'cidrAddress': str(net)}


@api('ca.loc.save')
def ca_loc_save(c: Ctx, b: dict) -> dict:
    lid = str(b.get('id') or '')
    naam = str(b.get('name') or '').strip()
    if not naam:
        raise ApiFout('Geef de locatie een naam.')
    if b.get('type') == 'ip':
        bereiken = [_cidr(x) for x in b.get('ranges') or [] if str(x).strip()]
        if not bereiken:
            raise ApiFout('Vul minstens één IP-adres of bereik in (bijv. 203.0.113.10 of 203.0.113.0/24).')
        body = {'@odata.type': '#microsoft.graph.ipNamedLocation', 'displayName': naam, 'isTrusted': bool(b.get('trusted')), 'ipRanges': bereiken}
    else:
        landen = sorted({str(x).upper() for x in b.get('countries') or [] if len(str(x)) == 2})
        if not landen and not b.get('unknown'):
            raise ApiFout('Kies minstens één land.')
        body = {'@odata.type': '#microsoft.graph.countryNamedLocation', 'displayName': naam, 'countriesAndRegions': landen,
                'includeUnknownCountriesAndRegions': bool(b.get('unknown')),
                'countryLookupMethod': 'authenticatorAppGps' if b.get('method') == 'authenticatorAppGps' else 'clientIpAddress'}
    if lid:
        _ca(c, lambda: c.g.patch(f'{CA}/namedLocations/{lid}', body))
        c.L(f"Benoemde locatie '{naam}' gewijzigd.")
        return {'id': lid}
    r = _ca(c, lambda: c.g.post(f'{CA}/namedLocations', body))
    c.L(f"Benoemde locatie '{naam}' aangemaakt.")
    return {'id': (r or {}).get('id')}


@api('ca.loc.delete')
def ca_loc_delete(c: Ctx, b: dict) -> dict:
    lid = str(b.get('id') or '')
    try:
        _ca(c, lambda: c.g.delete(f'{CA}/namedLocations/{lid}'))
    except ApiFout as e:
        if e.status == 400 or 'referenced' in str(e).lower() or 'in use' in str(e).lower():
            raise ApiFout('Deze locatie wordt nog gebruikt in een beleid. Haal hem daar eerst weg.') from None
        raise
    c.L(f"Benoemde locatie '{b.get('name') or lid}' verwijderd.")
    return {}
