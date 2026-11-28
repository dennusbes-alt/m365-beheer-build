"""SharePoint-mapmachtigingen ('geavanceerde machtigingen') eenvoudig beheren: site -> bibliotheek -> map, wie heeft
toegang, toegang geven (Lezen/Bewerken/Volledig beheer), weghalen, overname herstellen en 'zelfde toegang als collega'.

SharePoint REST op de site zelf (https://<tenant>.sharepoint.com/...), met een token voor de SharePoint-host van de klant.
Microsoft laat GDAP-accounts niet in de inhoud van sites. Weigert SharePoint, dan logt de beheerder één keer per sessie in
met een beheeraccount uit de tenant van de klant (`spm.klantlogin`, alleen in het geheugen); daarna gaat alles via dat account.
Geen opslag: alles live.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit

from .auth import KoppelingNodig
from .clients import ApiFout, _sessie, _verstuur, achtergrond_fn
from .context import Ctx, api

log = logging.getLogger('m365beheer')

# RoleTypeKind -> (sleutel, Nederlandse naam, uitleg)
NIVEAUS = {'read': (2, 'Lezen', 'Bestanden openen en downloaden, niets wijzigen.'),
           'edit': (6, 'Bewerken', 'Bestanden en mappen toevoegen, wijzigen en verwijderen.'),
           'contribute': (3, 'Bijdragen', 'Bestanden toevoegen en wijzigen, geen lijsten/mappen beheren.'),
           'full': (5, 'Volledig beheer', 'Alles, ook machtigingen van anderen wijzigen.')}
VERBORGEN = ('Limited Access', 'Beperkte toegang', 'Web-Only Limited Access', 'Alleen weergeven van beperkte toegang')
SOORT = {1: 'Gebruiker', 2: 'Distributielijst', 4: 'Beveiligingsgroep', 8: 'SharePoint-groep'}


def _host(site: str) -> str:
    u = urlsplit(site)
    if not u.scheme or not u.netloc.endswith('.sharepoint.com'):
        raise ApiFout('Ongeldig SharePoint-adres.')
    return f'{u.scheme}://{u.netloc}'


class KlantLoginNodig(ApiFout):
    """SharePoint weigert het GDAP-account: de interface biedt 'inloggen met een beheeraccount van de klant' aan."""
    klant_login = True


def _token(c: Ctx, host: str) -> str:
    eigen = c.staat.auth.token_klant(c.t.id, host)
    if eigen:
        return eigen
    soort = 'sp:' + host
    try:
        return c.staat.auth.token(c.t.id, soort, interactief=False)
    except KoppelingNodig:
        from .koppeling import koppelen
        koppelen(c.staat.auth, c.t.id)
        return c.staat.auth.token(c.t.id, soort, interactief=False)


def _req(c: Ctx, site: str, methode: str, pad: str, json=None, params=None):
    site = site.rstrip('/')
    h = {'Authorization': 'Bearer ' + _token(c, _host(site)), 'Accept': 'application/json;odata=nometadata'}
    if json is not None:
        h['Content-Type'] = 'application/json;odata=nometadata'
    elif methode == 'POST':
        h['Content-Length'] = '0'
    r = _verstuur(_sessie(), methode, site + pad, json=json, params=params, headers=h, timeout=120)
    if r.status_code in (401, 403):
        try:
            ms = (r.json().get('odata.error') or {}).get('message', {}).get('value') or ''
        except ValueError:
            ms = r.headers.get('x-ms-diagnostics') or ''
        log.info('SharePoint-mappen %s op %s: %s', r.status_code, site, ms[:200])
        klant = c.staat.auth.klant_account(c.t.id)
        if klant:
            raise ApiFout(f'Het account {klant} heeft geen toegang tot deze site. Maak dit account sitebeheerder (SharePoint-beheercentrum > '
                          'Actieve sites > site > Machtigingen > Sitebeheerders) of log in met een ander beheeraccount van de klant.'
                          + (f' (Microsoft: {ms[:150]})' if ms else ''), r.status_code)
        raise KlantLoginNodig('Microsoft laat je Justdata-account (GDAP) niet in de inhoud van SharePoint-sites, ook niet als sitebeheerder. '
                              'Log één keer in met een beheeraccount van de klant zelf (bijv. beheer@klant.onmicrosoft.com); '
                              'daarna werkt Mapmachtigingen voor deze klant de rest van de sessie.', r.status_code)
    if r.status_code >= 400:
        try:
            ms = (r.json().get('odata.error') or {}).get('message', {}).get('value') or r.text
        except ValueError:
            ms = r.text
        raise ApiFout(f'SharePoint: {str(ms)[:300]}', r.status_code)
    return r.json() if r.content else {}


def _rollen(c: Ctx, site: str) -> dict:
    """RoleTypeKind -> roldefinitie-ID van deze site (cache per klant en site)."""
    def ophalen():
        defs = _req(c, site, 'GET', '/_api/web/roledefinitions?$select=Id,Name,RoleTypeKind,Hidden').get('value') or []
        return {d['RoleTypeKind']: d['Id'] for d in defs if d.get('RoleTypeKind')}
    return c.t.cache(f'sprollen:{site}', ophalen, 3600)


def _object(lijst: str, item) -> str:
    return f"/_api/web/lists(guid'{lijst}')" + (f'/items({int(item)})' if item not in (None, '', 0) else '')


@api('spm.klantlogin')
def spm_klantlogin(c: Ctx, b: dict) -> dict:
    """Inloggen met een beheeraccount uit de tenant van de klant (browser), alleen voor SharePoint-site-inhoud."""
    host = _host(b['site'])
    wie = c.staat.auth.login_klant(c.t.id, host)
    c.L(f'Voor SharePoint ingelogd met het klantaccount {wie} (alleen deze sessie).')
    return {'account': wie}


@api('spm.klantlogout')
def spm_klantlogout(c: Ctx, b: dict) -> dict:
    c.staat.auth.afmelden_klant(c.t.id)
    c.L('Klantaccount voor SharePoint afgemeld.')
    return {}


@api('spm.klantstatus')
def spm_klantstatus(c: Ctx, b: dict) -> dict:
    return {'account': c.staat.auth.klant_account(c.t.id)}


@api('spm.sites')
def spm_sites(c: Ctx, b: dict) -> dict:
    """Sites om uit te kiezen: via de SharePoint-beheer-API, anders via Graph-zoeken."""
    try:
        from .h_sharepoint import sp_sites
        s = sp_sites(c, {})['sites']
        return {'sites': sorted([{'url': x['url'], 'title': x['title']} for x in s], key=lambda x: x['title'].lower())}
    except ApiFout as e:
        log.info('spm.sites via beheer-API niet gelukt (%s), Graph', e)
    r = c.g.all('/sites?search=*&$select=webUrl,displayName&$top=200')
    return {'sites': sorted([{'url': x['webUrl'], 'title': x.get('displayName') or x['webUrl']} for x in r if '/personal/' not in x.get('webUrl', '')],
                            key=lambda x: x['title'].lower())}


@api('spm.libs')
def spm_libs(c: Ctx, b: dict) -> dict:
    site = b['site']
    j = _req(c, site, 'GET', '/_api/web/lists', params={
        '$filter': 'BaseTemplate eq 101 and Hidden eq false', '$select': 'Id,Title,ItemCount,HasUniqueRoleAssignments,RootFolder/ServerRelativeUrl',
        '$expand': 'RootFolder'})
    return {'libs': [{'id': x['Id'], 'title': x['Title'], 'count': x.get('ItemCount') or 0, 'unique': bool(x.get('HasUniqueRoleAssignments')),
                      'path': (x.get('RootFolder') or {}).get('ServerRelativeUrl') or ''} for x in j.get('value') or []
                     if x.get('Title') not in ('Form Templates', 'Formuliersjablonen', 'Site Assets', 'Siteactiva', 'Style Library', 'Stijlbibliotheek')]}


@api('spm.folders')
def spm_folders(c: Ctx, b: dict) -> dict:
    site, pad = b['site'], b['path']
    j = _req(c, site, 'GET', "/_api/web/GetFolderByServerRelativePath(decodedurl=@p)/Folders",
             params={'@p': "'" + pad.replace("'", "''") + "'", '$select': 'Name,ServerRelativeUrl,ItemCount,ListItemAllFields/Id,ListItemAllFields/HasUniqueRoleAssignments',
                     '$expand': 'ListItemAllFields', '$top': '5000'})
    uit = []
    for f in j.get('value') or []:
        li = f.get('ListItemAllFields') or {}
        if f.get('Name') == 'Forms' or not li.get('Id'):
            continue
        uit.append({'name': f['Name'], 'path': f['ServerRelativeUrl'], 'count': f.get('ItemCount') or 0, 'itemId': li['Id'],
                    'unique': bool(li.get('HasUniqueRoleAssignments'))})
    uit.sort(key=lambda x: x['name'].lower())
    return {'folders': uit}


@api('spm.perms')
def spm_perms(c: Ctx, b: dict) -> dict:
    """Wie heeft toegang tot deze map (of bibliotheek): personen en groepen met hun niveau."""
    site, obj = b['site'], _object(b['listId'], b.get('itemId'))
    r = {}

    def eigen():
        r['u'] = _req(c, site, 'GET', obj, params={'$select': 'HasUniqueRoleAssignments'}).get('HasUniqueRoleAssignments')
    def toewijzingen():
        r['ra'] = _req(c, site, 'GET', obj + '/RoleAssignments', params={'$expand': 'Member,RoleDefinitionBindings'}).get('value') or []
    with ThreadPoolExecutor(max_workers=2) as ex:
        for f in [ex.submit(eigen), ex.submit(toewijzingen)]:
            f.result()
    uit = []
    for ra in r['ra']:
        m = ra.get('Member') or {}
        rollen = [d['Name'] for d in ra.get('RoleDefinitionBindings') or [] if d.get('Name') not in VERBORGEN and not d.get('Hidden')]
        if not rollen:
            continue
        login = m.get('LoginName') or ''
        uit.append({'id': ra.get('PrincipalId') or m.get('Id'), 'name': m.get('Title') or login, 'kind': SOORT.get(m.get('PrincipalType'), 'Overig'),
                    'email': m.get('Email') or (login.split('|')[-1] if '@' in login else ''), 'roles': rollen,
                    'spGroup': m.get('PrincipalType') == 8})
    uit.sort(key=lambda x: (x['kind'] != 'SharePoint-groep', x['name'].lower()))
    return {'unique': bool(r.get('u')), 'perms': uit, 'levels': [{'key': k, 'name': v[1], 'help': v[2]} for k, v in NIVEAUS.items()]}


@api('spm.groupusers')
def spm_groupusers(c: Ctx, b: dict) -> dict:
    j = _req(c, b['site'], 'GET', f"/_api/web/sitegroups/getbyid({int(b['groupId'])})/users", params={'$select': 'Title,Email,LoginName,PrincipalType'})
    return {'users': [{'name': u.get('Title') or '', 'email': u.get('Email') or ''} for u in j.get('value') or []]}


def _principal(c: Ctx, site: str, p: dict) -> int:
    """SharePoint-principal voor een Entra-gebruiker (upn) of -groep (id + soort)."""
    if p.get('upn'):
        login = f"i:0#.f|membership|{p['upn']}"
    elif p.get('groupId'):
        login = (f"c:0o.c|federateddirectoryclaimprovider|{p['groupId']}" if p.get('m365') else f"c:0t.c|tenant|{p['groupId']}")
    elif p.get('spId'):
        return int(p['spId'])
    else:
        raise ApiFout('Onbekende persoon of groep.')
    return int(_req(c, site, 'POST', '/_api/web/ensureuser', json={'logonName': login})['Id'])


def _eigen_maken(c: Ctx, site: str, obj: str) -> bool:
    if not _req(c, site, 'GET', obj, params={'$select': 'HasUniqueRoleAssignments'}).get('HasUniqueRoleAssignments'):
        # Overname verbreken en de huidige machtigingen meenemen (niemand verliest toegang)
        _req(c, site, 'POST', obj + '/breakroleinheritance(copyRoleAssignments=true,clearSubscopes=false)')
        return True
    return False


@api('spm.grant')
def spm_grant(c: Ctx, b: dict) -> dict:
    site, obj = b['site'], _object(b['listId'], b.get('itemId'))
    niveau = NIVEAUS.get(b.get('level'))
    if not niveau:
        raise ApiFout('Kies een niveau.')
    rol = _rollen(c, site).get(niveau[0])
    if not rol:
        raise ApiFout(f'Het niveau {niveau[1]} bestaat niet op deze site.')
    nieuw = _eigen_maken(c, site, obj)
    namen = []
    for p in b.get('principals') or []:
        pid = _principal(c, site, p)
        _req(c, site, 'POST', obj + f'/roleassignments/addroleassignment(principalid={pid},roledefid={rol})')
        namen.append(p.get('name') or p.get('upn') or str(pid))
    wat = b.get('label') or 'map'
    c.L(f"Toegang '{niveau[1]}' gegeven op {wat} aan {', '.join(namen)}" + (' (eigen machtigingen gemaakt, bestaande toegang behouden)' if nieuw else '') + '.')
    return {}


@api('spm.revoke')
def spm_revoke(c: Ctx, b: dict) -> dict:
    site, obj = b['site'], _object(b['listId'], b.get('itemId'))
    nieuw = _eigen_maken(c, site, obj)
    _req(c, site, 'POST', obj + f"/roleassignments/getbyprincipalid({int(b['principalId'])})/deleteobject()")
    c.L(f"Toegang van {b.get('name', b['principalId'])} weggehaald op {b.get('label') or 'map'}" + (' (eigen machtigingen gemaakt)' if nieuw else '') + '.')
    return {}


@api('spm.inherit')
def spm_inherit(c: Ctx, b: dict) -> dict:
    site, obj = b['site'], _object(b['listId'], b.get('itemId'))
    _req(c, site, 'POST', obj + '/resetroleinheritance')
    c.L(f"Machtigingen van {b.get('label') or 'map'} weer overgenomen van de bovenliggende map.")
    return {}


def _mappen_met_eigen(c: Ctx, site: str, lijst: str) -> list[dict]:
    """Alle mappen in een bibliotheek met eigen machtigingen (plus de bibliotheek zelf)."""
    uit, url = [], f"/_api/web/lists(guid'{lijst}')/items"
    params = {'$filter': 'FSObjType eq 1', '$select': 'Id,HasUniqueRoleAssignments,FileRef', '$top': '5000'}
    for _ in range(40):
        j = _req(c, site, 'GET', url, params=params)
        uit += [{'id': x['Id'], 'path': x.get('FileRef') or ''} for x in j.get('value') or [] if x.get('HasUniqueRoleAssignments')]
        volgende = j.get('odata.nextLink')
        if not volgende:
            break
        url, params = volgende.split(site.rstrip('/'), 1)[-1], None
    return uit


@api('spm.zoals')
def spm_zoals(c: Ctx, b: dict) -> dict:
    """Nieuwe medewerker dezelfde maptoegang geven als een collega: alle mappen in de bibliotheek waar de collega
    direct toegang heeft, met hetzelfde niveau. (Toegang via SharePoint-groepen gaat via 'groep' in het scherm.)"""
    site, lijst = b['site'], b['listId']
    van = _principal(c, site, {'upn': b['fromUpn']})
    naar = _principal(c, site, {'upn': b['toUpn']})
    mappen = _mappen_met_eigen(c, site, lijst)
    begin = time.time()

    def rollen_van(m):
        try:
            j = _req(c, site, 'GET', _object(lijst, m['id']) + f'/roleassignments/getbyprincipalid({van})/RoleDefinitionBindings')
            return m, [d['Id'] for d in j.get('value') or [] if d.get('Name') not in VERBORGEN]
        except ApiFout as e:
            if e.status == 404 or 'kan niet worden gevonden' in str(e).lower() or 'can not be found' in str(e).lower() or 'cannot be found' in str(e).lower():
                return m, []
            raise
    with ThreadPoolExecutor(max_workers=8) as ex:
        treffers = [x for x in ex.map(achtergrond_fn(rollen_van), mappen) if x[1]]
    for m, rollen in treffers:
        for rol in rollen:
            _req(c, site, 'POST', _object(lijst, m['id']) + f'/roleassignments/addroleassignment(principalid={naar},roledefid={rol})')
    c.L(f"{b['toUpn']} heeft dezelfde maptoegang gekregen als {b['fromUpn']}: {len(treffers)} map(pen)"
        + (': ' + ', '.join(m['path'].rsplit('/', 1)[-1] for m, _ in treffers[:15]) if treffers else '') + '.')
    log.info('spm.zoals: %d mappen met eigen machtigingen bekeken in %.1f s', len(mappen), time.time() - begin)
    return {'folders': [m['path'] for m, _ in treffers], 'checked': len(mappen)}


# ---------------------------------------------------------------- Onboarding: toegang per map via groepen (v2.25)
# Veel klanten (bijv. één site 'Data' met per map eigen machtigingen) geven maptoegang via SharePoint-groepen
# ('320 Sales' -> map Sales). Hier: overzicht van alle mappen met eigen machtigingen en welke groepen er toegang
# geven; de beheerder vinkt mappen aan en de app zet de nieuwe medewerker in de juiste groepen.
def _rol_kort(namen: list[str]) -> str:
    n = ' '.join(namen).lower()
    return 'Volledig beheer' if 'volledig' in n or 'full' in n else 'Bewerken' if any(w in n for w in ('bewerk', 'edit', 'bijdrag', 'contribute')) else 'Lezen'


@api('spm.toegangskaart')
def spm_toegangskaart(c: Ctx, b: dict) -> dict:
    site = b['site']
    libs = spm_libs(c, {'site': site})['libs']
    if b.get('listId'):
        libs = [x for x in libs if x['id'] == b['listId']]
    web = _req(c, site, 'GET', '/_api/web', params={'$select': 'AssociatedOwnerGroup/Id,AssociatedMemberGroup/Id,AssociatedVisitorGroup/Id',
                                                      '$expand': 'AssociatedOwnerGroup,AssociatedMemberGroup,AssociatedVisitorGroup'})
    standaard = {(web.get(k) or {}).get('Id') for k in ('AssociatedOwnerGroup', 'AssociatedMemberGroup', 'AssociatedVisitorGroup')} - {None}
    doelen = []
    for lib in libs:
        root = lib['path'].rstrip('/')
        doelen.append({'lib': lib['title'], 'listId': lib['id'], 'itemId': None, 'path': root, 'name': lib['title'], 'rel': '', 'depth': 0,
                       'unique': lib['unique']})
        for m in sorted(_mappen_met_eigen(c, site, lib['id']), key=lambda x: x['path'].lower()):
            rel = m['path'][len(root):].strip('/') if m['path'].startswith(root) else m['path']
            doelen.append({'lib': lib['title'], 'listId': lib['id'], 'itemId': m['id'], 'path': m['path'], 'name': rel.rsplit('/', 1)[-1] or rel,
                           'rel': rel, 'depth': rel.count('/') + 1, 'unique': True})

    def wie(d):
        ra = _req(c, site, 'GET', _object(d['listId'], d['itemId']) + '/RoleAssignments', params={'$expand': 'Member,RoleDefinitionBindings'}).get('value') or []
        uit = []
        for x in ra:
            m = x.get('Member') or {}
            rollen = [r['Name'] for r in x.get('RoleDefinitionBindings') or [] if r.get('Name') not in VERBORGEN and not r.get('Hidden')]
            if not rollen:
                continue
            login = m.get('LoginName') or ''
            soort = m.get('PrincipalType')
            entra = login.split('|')[-1] if soort == 4 and '|' in login else ''
            uit.append({'id': m.get('Id'), 'name': m.get('Title') or login, 'kind': SOORT.get(soort, 'Overig'), 'role': _rol_kort(rollen),
                        'spGroup': soort == 8, 'entraId': entra if len(entra) == 36 else '', 'm365': 'federateddirectoryclaimprovider' in login,
                        'default': m.get('Id') in standaard, 'email': m.get('Email') or (login.split('|')[-1] if '@' in login else '')})
        return {**d, 'access': sorted(uit, key=lambda g: (not (g['spGroup'] or g['entraId']), g['default'], g['name'].lower()))}
    begin = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        kaart = list(ex.map(achtergrond_fn(wie), doelen[:400]))
    # Leden van de SharePoint-groepen die toegang geven (voor 'zoals collega' en 'al lid')
    groepen = {g['id']: g['name'] for d in kaart for g in d['access'] if g['spGroup']}

    def leden(gid):
        try:
            j = _req(c, site, 'GET', f'/_api/web/sitegroups/getbyid({int(gid)})/users', params={'$select': 'Email,LoginName'})
            return gid, sorted({(u.get('Email') or u.get('LoginName', '').split('|')[-1]).lower() for u in j.get('value') or []} - {''})
        except ApiFout:
            return gid, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        lid = dict(ex.map(achtergrond_fn(leden), list(groepen)))
    log.info('spm.toegangskaart: %d mappen, %d groepen in %.1f s', len(kaart), len(groepen), time.time() - begin)
    return {'folders': kaart, 'groups': [{'id': k, 'name': v, 'members': lid.get(k, []), 'default': k in standaard} for k, v in groepen.items()],
            'truncated': len(doelen) > 400}


@api('spm.onboard')
def spm_onboard(c: Ctx, b: dict) -> dict:
    """Nieuwe medewerker toegang geven: in SharePoint-groepen, in Entra-groepen en/of directe toegang op mappen."""
    site, upn = b['site'], str(b.get('upn') or '').strip()
    if not upn:
        raise ApiFout('Kies eerst de medewerker.')
    gedaan, fouten = [], []
    for g in b.get('spGroups') or []:
        try:
            _req(c, site, 'POST', f"/_api/web/sitegroups/getbyid({int(g['id'])})/users", json={'LoginName': f'i:0#.f|membership|{upn}'})
            gedaan.append(g.get('name') or str(g['id']))
        except ApiFout as e:
            fouten.append(f"{g.get('name')}: {e}")
    if b.get('entraGroups'):
        try:
            uid = c.g.get(f"/users/{quote(upn)}?$select=id")['id']
        except ApiFout as e:
            uid = None
            fouten.append(f'Gebruiker niet gevonden in Entra: {e}')
        for g in (b.get('entraGroups') or []) if uid else []:
            try:
                try:
                    c.g.post(f"/groups/{g['id']}/members/$ref", {'@odata.id': f'https://graph.microsoft.com/v1.0/directoryObjects/{uid}'})
                except ApiFout as e:
                    if 'already exist' not in str(e).lower():
                        raise
                gedaan.append(g.get('name') or g['id'])
            except ApiFout as e:
                fouten.append(f"{g.get('name')}: {e}")
    for d in b.get('direct') or []:
        try:
            spm_grant(c, {'site': site, 'listId': d['listId'], 'itemId': d.get('itemId'), 'level': d.get('level') or 'edit',
                          'principals': [{'upn': upn, 'name': upn}], 'label': d.get('label')})
            gedaan.append(f"map {d.get('label')}")
        except ApiFout as e:
            fouten.append(f"{d.get('label')}: {e}")
    if gedaan:
        c.L(f"{upn} heeft maptoegang gekregen via: {', '.join(gedaan)}.")
    for f in fouten:
        c.L(f'Niet gelukt: {f}')
    return {'done': gedaan, 'errors': fouten}
