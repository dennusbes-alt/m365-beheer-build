"""Gebruikers: kopiëren van een bestaande medewerker, bulkacties en OneDrive."""
from __future__ import annotations

import re
import secrets

from . import common as C
from . import klussen
from .clients import ApiFout, parallel
from .context import Ctx, api
from .h_gebruikers import user_create


def wachtwoord(lengte: int = 16) -> str:
    sets = ['abcdefghijkmnopqrstuvwxyz', 'ABCDEFGHJKLMNPQRSTUVWXYZ', '23456789', '!@#$%&*?']
    alles = ''.join(sets)
    w = [secrets.choice(s) for s in sets] + [secrets.choice(alles) for _ in range(lengte - len(sets))]
    secrets.SystemRandom().shuffle(w)
    return ''.join(w)


# ---------------- Nieuwe gebruiker op basis van een bestaande medewerker ----------------
@api('user.template')
def user_template(c: Ctx, b: dict) -> dict:
    """Alles van een bestaande medewerker dat je voor een nieuwe collega wilt overnemen."""
    uid = b['id']
    r = parallel({
        'u': lambda: c.g.get(f'/users/{uid}?$select=id,displayName,userPrincipalName,jobTitle,department,officeLocation,companyName,'
                            'usageLocation,assignedLicenses,licenseAssignmentStates'),
        'lid': lambda: {m['id'] for m in c.g.all(f'/users/{uid}/memberOf?$select=id&$top=999')},
        'groepen': lambda: C.groepen(c),
    })
    for k in ('u', 'lid', 'groepen'):
        if isinstance(r[k], Exception):
            raise r[k]
    u = r['u']
    direct = sorted({s['skuId'] for s in u.get('licenseAssignmentStates') or [] if not s.get('assignedByGroup')}) \
        or [x['skuId'] for x in u.get('assignedLicenses') or []]
    groepen = [g for g in r['groepen'] if g['id'] in r['lid'] and g['edit']]
    gedeeld = []
    if c.exo_ok:
        upn = (u.get('userPrincipalName') or '').lower()
        try:
            kaart = C.rechtenkaart(c)
            for m in C.gedeeld_lijst(c):
                x = kaart.get(m['mail'].lower()) or {}
                if upn in x.get('full', ()) or upn in x.get('send', ()):
                    gedeeld.append({'mail': m['mail'], 'name': m['name'], 'full': upn in x.get('full', ()), 'send': upn in x.get('send', ())})
        except ApiFout as e:
            c.log.append(f'FOUT gedeelde postvakken van het voorbeeld ophalen: {e}')
    return {'name': u.get('displayName'), 'upn': u.get('userPrincipalName'), 'title': u.get('jobTitle') or '',
            'dept': u.get('department') or '', 'office': u.get('officeLocation') or '', 'company': u.get('companyName') or '',
            'loc': u.get('usageLocation') or 'NL', 'skus': direct, 'groups': [{'id': g['id'], 'name': g['name'], 'type': g['type']} for g in groepen],
            'shared': gedeeld}


# ---------------- Bulk ----------------
@api('users.bulkcreate')
def bulk_create(c: Ctx, b: dict) -> dict:
    """Meerdere gebruikers aanmaken (elke rij zoals bij 'Nieuwe gebruiker'). Loopt op de achtergrond, 3 tegelijk."""
    rijen = [r for r in b.get('rows') or [] if r.get('alias') and r.get('domain')]
    if not rijen:
        raise ApiFout('Geen geldige rijen (inlognaam en domein zijn verplicht).')

    def een(sub: Ctx, r: dict) -> dict:
        r = dict(r)
        r.setdefault('password', wachtwoord())
        r['bulk'] = True
        if not r.get('name'):
            r['name'] = f"{r.get('given', '')} {r.get('sur', '')}".strip() or r['alias']
        uit = user_create(sub, r)
        return {'upn': uit['upn'], 'password': r['password'], 'problems': uit.get('problems', [])}
    k = klussen.start(c, f'{len(rijen)} gebruikers aanmaken', rijen, een, lambda r: f"{r['alias']}@{r['domain']}", tegelijk=3)
    c.t.weg('users', 'skus')
    return k


@api('users.bulkdelete')
def bulk_delete(c: Ctx, b: dict) -> dict:
    ids = list(b.get('ids') or [])
    alle = {u['id']: u for u in C.gebruikers(c)}

    def een(sub: Ctx, uid: str) -> dict:
        sub.g.delete(f'/users/{uid}')
        sub.L(f"Verwijderd: {alle.get(uid, {}).get('upn', uid)}")
        return {}
    k = klussen.start(c, f'{len(ids)} gebruikers verwijderen', ids, een, lambda i: alle.get(i, {}).get('name', i), tegelijk=6)
    c.t.weg('users', 'skus')
    return k


@api('users.bulklicense')
def bulk_license(c: Ctx, b: dict) -> dict:
    ids = list(b.get('ids') or [])
    add = [{'skuId': s, 'disabledPlans': []} for s in b.get('add') or []]
    rem = list(b.get('remove') or [])
    if not add and not rem:
        raise ApiFout('Kies minimaal één licentie om toe te voegen of te verwijderen.')
    alle = {u['id']: u for u in C.gebruikers(c)}

    def een(sub: Ctx, uid: str) -> dict:
        C.gebruikslocatie(sub, uid)
        heeft = set(alle.get(uid, {}).get('lic', []))
        weg = [s for s in rem if s in heeft]
        erbij = [a for a in add if a['skuId'] not in heeft]
        if erbij or weg:
            sub.g.post(f'/users/{uid}/assignLicense', {'addLicenses': erbij, 'removeLicenses': weg})
        return {'added': len(erbij), 'removed': len(weg)}
    k = klussen.start(c, f'Licenties voor {len(ids)} gebruikers', ids, een, lambda i: alle.get(i, {}).get('name', i), tegelijk=6)
    c.t.weg('users', 'skus')
    return k


@api('users.bulkpassword')
def bulk_password(c: Ctx, b: dict) -> dict:
    """Nieuw wachtwoord per gebruiker (willekeurig, of één opgegeven wachtwoord voor iedereen)."""
    ids = list(b.get('ids') or [])
    vast = str(b.get('password') or '')
    if vast and len(vast) < 8:
        raise ApiFout('Het wachtwoord moet minimaal 8 tekens hebben.')
    forceer = bool(b.get('force', True))
    alle = {u['id']: u for u in C.gebruikers(c)}

    def een(sub: Ctx, uid: str) -> dict:
        ww = vast or wachtwoord()
        sub.g.patch(f'/users/{uid}', {'passwordProfile': {'password': ww, 'forceChangePasswordNextSignIn': forceer}})
        if b.get('revoke'):
            C.intrekken(sub, uid)
        return {'upn': alle.get(uid, {}).get('upn', uid), 'password': ww}
    return klussen.start(c, f'Wachtwoorden van {len(ids)} gebruikers', ids, een, lambda i: alle.get(i, {}).get('name', i), tegelijk=6)


# ---------------- OneDrive ----------------
def _gb(n) -> float:
    return round(float(n or 0) / 1024 ** 3, 2)


def _od_site(c: Ctx, upn: str) -> dict | None:
    """OneDrive (persoonlijke site) van een gebruiker via de SharePoint-beheer-API (een beheerder kan via Graph
    niet in andermans OneDrive kijken). Eerst het adres uit het gebruikersprofiel, anders het standaardadres."""
    from urllib.parse import quote
    from .h_sharepoint import _sp
    url = ''
    try:
        acc = quote(f"'i:0#.f|membership|{upn}'", safe="'|:.@")
        p = _sp(c, 'GET', f"/_api/SP.UserProfiles.PeopleManager/GetPropertiesFor(accountName=@v)?@v={acc}&$select=PersonalUrl").json()
        url = str(p.get('PersonalUrl') or '').rstrip('/')
    except ApiFout:
        pass
    if '/personal/' not in url:
        my = c.t.sp_admin().replace('-admin.sharepoint.com', '-my.sharepoint.com')
        url = f"{my}/personal/{re.sub(r'[^a-z0-9]', '_', upn.lower())}"
    body = {'speFilter': {'IncludePersonalSite': 1, 'IncludeDetail': True, 'StartIndex': None, 'Template': None, 'Filter': f"Url -eq '{url}'"}}
    v = _sp(c, 'POST', '/_api/SPO.Tenant/GetSitePropertiesFromSharePointByFilters', json=body).json().get('value') or []
    return v[0] if v else None


@api('user.onedrive')
def user_onedrive(c: Ctx, b: dict) -> dict:
    """OneDrive-gegevens (adres en opslag, zoals in het beheercentrum). Met provision=True wordt OneDrive aangemaakt als die
    er nog niet is, net als Request-SPOPersonalSite (CreatePersonalSiteEnqueueBulk). Vereist de rol SharePoint Administrator."""
    from .h_sharepoint import _sp
    upn = b.get('upn') or c.g.get(f"/users/{b['id']}?$select=userPrincipalName")['userPrincipalName']
    s = _od_site(c, upn)
    if not s and b.get('provision'):
        _sp(c, 'POST', '/_api/SP.UserProfiles.ProfileLoader.GetProfileLoader/CreatePersonalSiteEnqueueBulk', json={'emailIDs': [upn]})
        c.L(f'OneDrive voor {upn} wordt aangemaakt (meestal binnen enkele minuten klaar).')
        return {'exists': False, 'queued': True}
    if not s:
        return {'exists': False}
    if b.get('provision'):
        c.L(f'{upn} heeft al een OneDrive.')
    gebruikt, max_ = float(s.get('StorageUsage') or 0), float(s.get('StorageMaximumLevel') or 0)
    return {'exists': True, 'url': s.get('Url', ''), 'usedGb': round(gebruikt / 1024, 2), 'usedMb': round(gebruikt), 'totalGb': round(max_ / 1024, 2),
            'deletedGb': 0, 'state': 'normal' if not max_ or gebruikt / max_ < 0.9 else 'nearing',
            'modified': s.get('LastContentModifiedDate', ''), 'created': ''}


@api('users.bulkonedrive')
def bulk_onedrive(c: Ctx, b: dict) -> dict:
    """OneDrive aanmaken voor meerdere gebruikers (bijv. na het in bulk aanmaken van accounts)."""
    ids = list(b.get('ids') or [])
    alle = {u['id']: u for u in C.gebruikers(c)}

    def een(sub: Ctx, uid: str) -> dict:
        d = user_onedrive(sub, {'id': uid, 'upn': alle.get(uid, {}).get('upn'), 'provision': True})
        if d.get('queued'):
            return {'status': 'Wordt aangemaakt'}
        return {'status': 'Bestond al', 'url': d.get('url', ''), 'gebruikt': f"{d.get('usedGb', 0)} GB"}
    return klussen.start(c, f'OneDrive aanmaken voor {len(ids)} gebruikers', ids, een, lambda i: alle.get(i, {}).get('name', i), tegelijk=6)
