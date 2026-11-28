"""Gedeelde hulpfuncties (groepen, gedeelde postvakken, agenda's)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .clients import GB, ApiFout, achtergrond, parallel
from .context import Ctx, VERS
from .skus import sku_info


def heeft(waarde: Any, recht: str) -> bool:
    if isinstance(waarde, list):
        return any(recht.lower() in str(x).lower() for x in waarde)
    return recht.lower() in str(waarde or '').lower()


def groep_type(g: dict) -> str:
    gt = g.get('groupTypes') or []
    if 'DynamicMembership' in gt:
        return 'Dynamisch'
    if 'Unified' in gt:
        return 'M365'
    if g.get('mailEnabled') and g.get('securityEnabled'):
        return 'Mail-beveiliging'
    if g.get('mailEnabled'):
        return 'Distributielijst'
    if g.get('securityEnabled'):
        return 'Beveiliging'
    return 'Overig'


# Verlooptijden van de cache (seconden). Na een wijziging via de app wordt de cache direct geleegd.
TTL_LIJST = VERS
TTL_GROEPEN = VERS
TTL_RECHTEN = 600   # rechtenkaart van alle postvakken is duur; wordt na elke wijziging zelf bijgewerkt


def _groepen_ophalen(g) -> list[dict]:
    l = []
    for x in g.all('/groups?$select=id,displayName,mail,groupTypes,mailEnabled,securityEnabled,onPremisesSyncEnabled&$top=999'):
        ty = groep_type(x)
        sy = bool(x.get('onPremisesSyncEnabled'))
        l.append({'id': x['id'], 'name': x.get('displayName') or '', 'mail': x.get('mail') or '', 'type': ty,
                  'sync': sy, 'edit': ty not in ('Dynamisch', 'Overig') and not sy})
    return sorted(l, key=lambda x: x['name'].lower())


def groepen(c: Ctx, vers: bool = False) -> list[dict]:
    g = c.g
    return c.t.cache('groepen', lambda: _groepen_ophalen(g), TTL_GROEPEN, vers)


def _gedeeld_ophalen(x) -> list[dict]:
    l = [{'name': m.get('DisplayName') or '', 'mail': m.get('PrimarySmtpAddress') or ''}
         for m in x.run('Get-Mailbox', RecipientTypeDetails='SharedMailbox', ResultSize='Unlimited')]
    return sorted(l, key=lambda m: m['name'].lower())


def gedeeld_lijst(c: Ctx, vers: bool = False) -> list[dict]:
    if not c.exo_ok:
        return []
    x = c.x
    return c.t.cache('gedeeld', lambda: _gedeeld_ophalen(x), TTL_GROEPEN, vers)


def _rechten_van(x, mail: str) -> dict:
    """Volledige toegang en Verzenden als op één postvak (beide lijsten tegelijk opgehaald)."""
    r = parallel({'f': lambda: x.run('Get-MailboxPermission', Identity=mail), 's': lambda: x.run('Get-RecipientPermission', Identity=mail)})
    for v in r.values():
        if isinstance(v, Exception):
            raise v
    full = {str(p.get('User')).lower() for p in r['f']
            if p.get('User') and p.get('User') != 'NT AUTHORITY\\SELF' and not p.get('IsInherited') and not p.get('Deny')
            and heeft(p.get('AccessRights'), 'FullAccess')}
    send = {str(p.get('Trustee')).lower() for p in r['s']
            if p.get('Trustee') and p.get('Trustee') != 'NT AUTHORITY\\SELF' and heeft(p.get('AccessRights'), 'SendAs')}
    return {'full': full, 'send': send}


def rechten_van_postvak(c: Ctx, mail: str) -> dict:
    """Vers ophalen voor één postvak en de rechtenkaart meteen bijwerken."""
    r = _rechten_van(c.x, mail)
    c.t.markeer('gedeeldrechten')
    item = c.t._cache.get('gedeeldrechten')
    if item:
        item[1][mail.lower()] = r
    return r


def rechtenkaart(c: Ctx, vers: bool = False) -> dict[str, dict]:
    """Rechten op alle gedeelde postvakken, in één keer (10 postvakken tegelijk) en 10 minuten bewaard.
    Daarna is 'welke postvakken mag deze gebruiker openen' voor elke gebruiker direct bekend."""
    lijst = gedeeld_lijst(c)
    x = c.x

    def ophalen() -> dict[str, dict]:
        def een(m: dict) -> tuple[str, dict]:
            try:
                with achtergrond():
                    return m['mail'].lower(), _rechten_van(x, m['mail'])
            except ApiFout:
                return m['mail'].lower(), {'full': set(), 'send': set(), 'fout': True}
        with ThreadPoolExecutor(max_workers=4) as ex:
            return dict(ex.map(een, lijst))
    return c.t.cache('gedeeldrechten', ophalen, TTL_RECHTEN, vers)


def rechten_bijwerken(c: Ctx, mail: str, wie: str, full: bool, send: bool, erbij: bool) -> None:
    """Na een wijziging de bewaarde rechten bijwerken (in plaats van alles opnieuw ophalen)."""
    c.t.markeer('gedeeldrechten')
    item = c.t._cache.get('gedeeldrechten')
    if not item:
        return
    r = item[1].setdefault(mail.lower(), {'full': set(), 'send': set()})
    for soort, aan in (('full', full), ('send', send)):
        if aan:
            (r[soort].add if erbij else r[soort].discard)(wie.lower())


def _gebruikers_ophalen(g) -> list[dict]:
    l = []
    for u in g.all('/users?$select=id,displayName,userPrincipalName,accountEnabled,assignedLicenses,jobTitle,department,userType&$top=999'):
        if not u.get('userPrincipalName'):
            continue
        l.append({'id': u['id'], 'name': u.get('displayName') or '', 'upn': u['userPrincipalName'], 'on': u.get('accountEnabled') is not False,
                  'lic': [x['skuId'] for x in u.get('assignedLicenses') or []], 'title': u.get('jobTitle') or '',
                  'dept': u.get('department') or '', 'guest': u.get('userType') == 'Guest'})
    return sorted(l, key=lambda x: x['name'].lower())


def gebruikers(c: Ctx, vers: bool = False) -> list[dict]:
    g = c.g
    return c.t.cache('users', lambda: _gebruikers_ophalen(g), TTL_LIJST, vers)


def _licenties_ophalen(g) -> list[dict]:
    l = []
    for s in g.all('/subscribedSkus'):
        tot = int((s.get('prepaidUnits') or {}).get('enabled') or 0)
        geb = int(s.get('consumedUnits') or 0)
        l.append({'id': s['skuId'], 'part': s.get('skuPartNumber') or '', **sku_info(s.get('skuPartNumber') or '', tot),
                  'total': tot, 'used': geb, 'free': tot - geb, 'status': s.get('capabilityStatus') or ''})
    return sorted(l, key=lambda x: x['name'].lower())


def licenties(c: Ctx, vers: bool = False) -> list[dict]:
    g = c.g
    return c.t.cache('skus', lambda: _licenties_ophalen(g), TTL_LIJST, vers)


def voorladen(c: Ctx) -> None:
    """Na het openen van een klant: gebruikers, licenties en groepen alvast ophalen."""
    t, g = c.t, c.g
    from .h_apparaten import _apparaten   # Intune-apparaten worden vaak direct na het wisselen geopend (synchroniseren e.d.)
    t.voorladen({'users': lambda: _gebruikers_ophalen(g), 'skus': lambda: _licenties_ophalen(g), 'groepen': lambda: _groepen_ophalen(g),
                 'apparaten': lambda: _apparaten(g)})

    def exo_lijsten() -> None:   # zodra Exchange klaar is: gedeelde postvakken (en hun rechten) ophalen
        x = t.exo
        if x:
            t.voorladen({'gedeeld': lambda: _gedeeld_ophalen(x)})
    t.na_exo = exo_lijsten
    if t.exo_klaar.is_set():
        exo_lijsten()


def gebruiker(c: Ctx, uid: str) -> dict:
    return c.g.get(f'/users/{uid}?$select=id,userPrincipalName,displayName')


def lid_toevoegen(c: Ctx, ty: str, gid: str, mail: str, u: dict) -> None:
    if ty in ('M365', 'Beveiliging'):
        c.g.post(f'/groups/{gid}/members/$ref', {'@odata.id': f'{GB}/directoryObjects/{u["id"]}'})
    elif ty in ('Distributielijst', 'Mail-beveiliging'):
        c.x.run('Add-DistributionGroupMember', Identity=mail, Member=u['userPrincipalName'], BypassSecurityGroupManagerCheck=True)
    else:
        raise ApiFout(f"Groepen van het type '{ty}' kunnen hier niet gewijzigd worden.")


def lid_verwijderen(c: Ctx, ty: str, gid: str, mail: str, u: dict) -> None:
    if ty in ('M365', 'Beveiliging'):
        c.g.delete(f'/groups/{gid}/members/{u["id"]}/$ref')
    elif ty in ('Distributielijst', 'Mail-beveiliging'):
        c.x.run('Remove-DistributionGroupMember', Identity=mail, Member=u['userPrincipalName'], BypassSecurityGroupManagerCheck=True)
    else:
        raise ApiFout(f"Groepen van het type '{ty}' kunnen hier niet gewijzigd worden.")


def gedeeld_rechten(c: Ctx, postvak: str, upn: str, volledig: bool, send_as: bool, automapping: bool) -> None:
    if volledig:
        c.x.run('Add-MailboxPermission', Identity=postvak, User=upn, AccessRights=['FullAccess'], InheritanceType='All', AutoMapping=bool(automapping))
    if send_as:
        c.x.run('Add-RecipientPermission', Identity=postvak, Trustee=upn, AccessRights=['SendAs'])


def agenda_id(c: Ctx, postvak: str) -> str:
    t = c.t
    if postvak not in t.agenda_cache:
        mappen = c.x.run('Get-MailboxFolderStatistics', Identity=postvak, FolderScope='Calendar')
        f = next((m for m in mappen if str(m.get('FolderType')) == 'Calendar'), None)
        if not f:
            raise ApiFout(f'Geen agenda gevonden voor {postvak}')
        t.agenda_cache[postvak] = postvak + ':' + str(f.get('FolderPath', '/Calendar')).replace('/', '\\')
    return t.agenda_cache[postvak]


MELDING_ROLLEN = {'AvailabilityOnly', 'LimitedDetails', 'Reviewer', 'Author', 'Editor'}   # waarvoor Exchange een melding kan sturen


def agenda_recht(c: Ctx, postvak: str, wie: str, recht: str, delegate: bool, prive: bool, melding: bool = False) -> None:
    """Zoals Add/Set-MailboxFolderPermission -AccessRights -SharingPermissionFlags -SendNotificationToUser."""
    fid = agenda_id(c, postvak)
    p: dict[str, Any] = {'Identity': fid, 'User': wie, 'AccessRights': [recht]}
    if recht == 'Editor':   # Delegate kan alleen bij Bewerker; zonder vinkje expliciet uit (anders blijft het staan)
        p['SharingPermissionFlags'] = ('Delegate,CanViewPrivateItems' if prive else 'Delegate') if delegate else 'None'
    if melding and recht in MELDING_ROLLEN and wie not in ('Default', 'Anonymous'):
        p['SendNotificationToUser'] = True
    try:
        bestaat = bool(c.x.run('Get-MailboxFolderPermission', Identity=fid, User=wie))
    except ApiFout:
        bestaat = False
    c.x.run('Set-MailboxFolderPermission' if bestaat else 'Add-MailboxFolderPermission', **p)


def gebruikslocatie(c: Ctx, uid: str) -> None:
    u = c.g.get(f'/users/{uid}?$select=id,usageLocation')
    if not u.get('usageLocation'):
        c.g.patch(f'/users/{uid}', {'usageLocation': 'NL'})
        c.L('Gebruikslocatie ingesteld op NL (verplicht voor licenties).')


def wacht_op_mailbox(c: Ctx, upn: str, max_sec: int = 600) -> bool:
    start = time.time()
    while time.time() - start < max_sec:
        try:
            if c.x.run('Get-Mailbox', Identity=upn):
                return True
        except ApiFout:
            pass
        time.sleep(15)
    return False


def intrekken(c: Ctx, uid: str) -> None:
    c.g.post(f'/users/{uid}/revokeSignInSessions')
