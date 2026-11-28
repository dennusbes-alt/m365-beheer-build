"""Gebruikers, licenties, MFA, nieuwe gebruiker, uit dienst en inactieve gebruikers."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import common as C
from .clients import ApiFout, hashtabel, parallel
from .context import Ctx, api


@api('skus')
def skus(c: Ctx, b: dict) -> dict:
    return {'skus': C.licenties(c, vers=bool(b.get('fresh')))}


@api('users')
def users(c: Ctx, b: dict) -> dict:
    return {'users': C.gebruikers(c, vers=bool(b.get('fresh')))}


@api('shared.list')
def gedeeld(c: Ctx, b: dict) -> dict:
    return {'shared': C.gedeeld_lijst(c, vers=bool(b.get('fresh')))}


@api('user.get')
def user_get(c: Ctx, b: dict) -> dict:
    u = c.g.get(f"/users/{b['id']}?$select=id,displayName,givenName,surname,userPrincipalName,mail,jobTitle,department,officeLocation,"
                "mobilePhone,accountEnabled,usageLocation,assignedLicenses,licenseAssignmentStates,proxyAddresses")
    al = [{'addr': re.sub(r'(?i)^smtp:', '', p), 'primary': p.startswith('SMTP:')}
          for p in u.get('proxyAddresses') or [] if p.lower().startswith('smtp:')]
    states = u.get('licenseAssignmentStates') or []
    lic = []
    for l in u.get('assignedLicenses') or []:
        st = [s for s in states if s.get('skuId') == l['skuId']]
        lic.append({'sku': l['skuId'], 'direct': any(not s.get('assignedByGroup') for s in st) or not st})
    return {'id': u['id'], 'name': u.get('displayName') or '', 'given': u.get('givenName') or '', 'sur': u.get('surname') or '',
            'upn': u.get('userPrincipalName') or '', 'mail': u.get('mail') or '', 'title': u.get('jobTitle') or '',
            'dept': u.get('department') or '', 'office': u.get('officeLocation') or '', 'mobile': u.get('mobilePhone') or '',
            'on': u.get('accountEnabled') is not False, 'loc': u.get('usageLocation') or '', 'aliases': al, 'licenses': lic}


@api('user.update')
def user_update(c: Ctx, b: dict) -> dict:
    kaart = {'name': 'displayName', 'given': 'givenName', 'sur': 'surname', 'title': 'jobTitle', 'dept': 'department',
             'office': 'officeLocation', 'mobile': 'mobilePhone'}
    p = {v: (str(b[k]).strip() or None) for k, v in kaart.items() if k in b}
    if p.get('displayName') is None:
        p.pop('displayName', None)  # weergavenaam mag niet leeg
    if b.get('upn'):
        p['userPrincipalName'] = str(b['upn']).strip()
    c.g.patch(f"/users/{b['id']}", p)
    c.L('Gegevens opgeslagen.')
    return {}


@api('user.block')
def user_block(c: Ctx, b: dict) -> dict:
    blok = bool(b.get('blocked'))
    c.g.patch(f"/users/{b['id']}", {'accountEnabled': not blok})
    if blok:
        C.intrekken(c, b['id'])
    c.L('Aanmelden geblokkeerd en sessies ingetrokken.' if blok else 'Aanmelden weer toegestaan.')
    return {}


@api('user.revoke')
def user_revoke(c: Ctx, b: dict) -> dict:
    C.intrekken(c, b['id'])
    c.L('Alle sessies afgemeld: de gebruiker moet opnieuw inloggen.')
    return {}


@api('user.alias')
def user_alias(c: Ctx, b: dict) -> dict:
    a = str(b.get('alias') or '').strip().lower()
    upn = b['upn']
    actie = b.get('action')
    if actie == 'add':
        c.x.run('Set-Mailbox', Identity=upn, EmailAddresses=hashtabel(Add=f'smtp:{a}'))
        c.L(f'Alias {a} toegevoegd.')
    elif actie == 'remove':
        c.x.run('Set-Mailbox', Identity=upn, EmailAddresses=hashtabel(Remove=f'smtp:{a}'))
        c.L(f'Alias {a} verwijderd.')
    elif actie == 'primary':
        c.x.run('Set-Mailbox', Identity=upn, WindowsEmailAddress=a)
        c.L(f'{a} is nu het primaire e-mailadres.')
    return {}


MFA_PAD = {
    'microsoftAuthenticatorAuthenticationMethod': 'microsoftAuthenticatorMethods', 'phoneAuthenticationMethod': 'phoneMethods',
    'softwareOathAuthenticationMethod': 'softwareOathMethods', 'fido2AuthenticationMethod': 'fido2Methods',
    'windowsHelloForBusinessAuthenticationMethod': 'windowsHelloForBusinessMethods',
    'temporaryAccessPassAuthenticationMethod': 'temporaryAccessPassMethods', 'emailAuthenticationMethod': 'emailMethods',
}


def _mfa(c: Ctx, uid: str) -> list[dict]:
    uit = []
    for m in c.g.get(f'/users/{uid}/authentication/methods').get('value', []):
        t = str(m.get('@odata.type', '')).replace('#microsoft.graph.', '')
        if t == 'passwordAuthenticationMethod':
            continue
        dn = f" ({m['displayName']})" if m.get('displayName') else ''
        naam = {
            'microsoftAuthenticatorAuthenticationMethod': 'Microsoft Authenticator-app' + dn,
            'phoneAuthenticationMethod': 'Telefoon (sms/bellen): ' + str(m.get('phoneNumber') or ''),
            'softwareOathAuthenticationMethod': 'Authenticator-app met code (OATH)',
            'fido2AuthenticationMethod': 'Beveiligingssleutel (FIDO2)' + dn,
            'windowsHelloForBusinessAuthenticationMethod': 'Windows Hello for Business' + dn,
            'temporaryAccessPassAuthenticationMethod': 'Tijdelijke toegangspas',
            'emailAuthenticationMethod': 'E-mail: ' + str(m.get('emailAddress') or ''),
        }.get(t, t)
        uit.append({'id': m['id'], 'type': t, 'name': naam, 'supported': t in MFA_PAD})
    return uit


@api('user.mfa')
def user_mfa(c: Ctx, b: dict) -> dict:
    return {'methods': _mfa(c, b['id'])}


@api('user.mfareset')
def user_mfareset(c: Ctx, b: dict) -> dict:
    alle = _mfa(c, b['id'])
    ids = b.get('ids')
    doel = [m for m in alle if m['id'] in ids] if ids else alle
    fout = 0
    for m in doel:
        if not m['supported']:
            c.L(f"Overgeslagen (niet te verwijderen via dit scherm): {m['name']}")
            continue
        try:
            c.g.delete(f"/users/{b['id']}/authentication/{MFA_PAD[m['type']]}/{m['id']}")
            c.L(f"Verwijderd: {m['name']}")
        except ApiFout as e:
            fout += 1
            c.L(f"FOUT bij {m['name']}: {e}")
    if b.get('revoke'):
        try:
            C.intrekken(c, b['id'])
            c.L('Alle aanmeldsessies ingetrokken: de gebruiker moet opnieuw inloggen en MFA opnieuw instellen.')
        except ApiFout as e:
            c.L(f'FOUT bij sessies intrekken: {e}')
    if not doel:
        c.L('Er waren geen MFA-methoden geregistreerd.')
    return {'failed': fout}


def _datum(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None


def _inactief(c: Ctx, dagen: int) -> dict:
    nu = datetime.now(timezone.utc)
    grens = nu - timedelta(days=dagen)
    g = c.g

    def beheerders_ophalen() -> set[str]:
        rollen = g.get('/directoryRoles?$select=id').get('value', [])
        r = parallel({x['id']: (lambda rid=x['id']: g.all(f'/directoryRoles/{rid}/members?$select=id')) for x in rollen})
        if any(isinstance(v, Exception) for v in r.values()):
            raise ApiFout('rollen')
        return {m['id'] for leden in r.values() for m in leden}

    def postvakken() -> set[str]:
        if not c.exo_ok:
            raise ApiFout('geen exchange')
        return {str(mb.get('ExternalDirectoryObjectId') or '')
                for mb in c.x.run('Get-Mailbox', RecipientTypeDetails=['SharedMailbox', 'RoomMailbox', 'EquipmentMailbox'], ResultSize='Unlimited')}

    # Alles tegelijk ophalen (dit gebeurde eerder na elkaar)
    r = parallel({
        'alle': lambda: g.all('/users?$select=id,displayName,userPrincipalName,accountEnabled,userType,assignedLicenses,createdDateTime,'
                              'signInActivity,externalUserState,onPremisesSyncEnabled&$top=500'),
        'eigen': lambda: g.get('/me?$select=id').get('id', ''),   # via GDAP bestaat je eigen account niet in de klant-tenant
        'beheer': beheerders_ophalen,
        'postvak': postvakken,
    })
    if isinstance(r['alle'], Exception):
        raise ApiFout(f"Inlogdatums ophalen is niet gelukt: {r['alle']} - Dit vraagt Entra ID P1 (zit in Microsoft 365 Business Premium) "
                      'en een rol die inloggegevens mag lezen (bijv. Reports Reader of Global Reader).')
    alle = r['alle']
    eigen = '' if isinstance(r['eigen'], Exception) else r['eigen']
    rol_check = not isinstance(r['beheer'], Exception)
    beheerders = r['beheer'] if rol_check else set()
    mb_check = not isinstance(r['postvak'], Exception)
    postvak = r['postvak'] if mb_check else set()
    lic, leden, gasten = [], [], []
    for u in alle:
        sa = u.get('signInActivity') or {}
        data = [d for d in (_datum(sa.get(k)) for k in ('lastSignInDateTime', 'lastNonInteractiveSignInDateTime', 'lastSuccessfulSignInDateTime')) if d]
        laatst = max(data) if data else None
        aangemaakt = _datum(u.get('createdDateTime'))
        ref = laatst or aangemaakt
        if not ref or ref >= grens:
            continue
        uid = u['id']
        gast = u.get('userType') == 'Guest'
        licenties = [x['skuId'] for x in u.get('assignedLicenses') or []]
        reden = ''
        if uid == eigen:
            reden = 'Dit is je eigen account'
        elif uid in beheerders:
            reden = 'Heeft een beheerdersrol'
        elif u.get('onPremisesSyncEnabled'):
            reden = 'Komt van de on-premises AD (daar verwijderen)'
        elif not gast and not licenties and uid in postvak:
            reden = 'Gedeeld postvak of ruimte/apparaat'
        elif not gast and not licenties and not mb_check:
            reden = 'Exchange niet verbonden: kan gedeelde postvakken niet uitsluiten'
        item = {'id': uid, 'name': u.get('displayName') or '', 'upn': u.get('userPrincipalName') or '', 'on': u.get('accountEnabled') is not False,
                'last': laatst.strftime('%Y-%m-%d') if laatst else '', 'created': aangemaakt.strftime('%Y-%m-%d') if aangemaakt else '',
                'days': (nu - ref).days, 'never': laatst is None, 'lic': licenties, 'guest': gast, 'reason': reden,
                'pending': u.get('externalUserState') == 'PendingAcceptance'}
        (gasten if gast else lic if licenties else leden).append(item)
    srt = lambda l: sorted(l, key=lambda x: -x['days'])
    return {'licensed': srt(lic), 'members': srt(leden), 'guests': srt(gasten), 'mbCheck': mb_check, 'roleCheck': rol_check,
            'total': len(alle), 'days': dagen}


@api('inactive')
def inactive(c: Ctx, b: dict) -> dict:
    return _inactief(c, int(b.get('days') or 90))


@api('inactive.delete')
def inactive_delete(c: Ctx, b: dict) -> dict:
    d = int(b.get('days') or 90)
    if d < 30:
        raise ApiFout('Kies minimaal 30 dagen.')
    r = _inactief(c, d)
    soort = b.get('kind')
    if soort not in ('members', 'guests'):
        raise ApiFout('Onbekende soort.')
    toegestaan = {x['id']: x for x in r[soort] if not x['reason']}
    ok = fout = 0
    for uid in b.get('ids') or []:
        x = toegestaan.get(uid)
        if not x:
            c.L(f'Overgeslagen (geen kandidaat meer of beschermd): {uid}')
            continue
        try:
            c.g.delete(f'/users/{uid}')
            ok += 1
            c.L(f"Verwijderd: {x['name']} ({x['upn']})")
        except ApiFout as e:
            fout += 1
            c.L(f"FOUT bij {x['upn']}: {e}")
    c.L(f'{ok} verwijderd, {fout} mislukt.')
    return {'deleted': ok, 'failed': fout}


@api('user.license')
def user_license(c: Ctx, b: dict) -> dict:
    C.gebruikslocatie(c, b['id'])
    add = [{'skuId': s, 'disabledPlans': []} for s in b.get('add') or [] if s]
    rem = [s for s in b.get('remove') or [] if s]
    c.g.post(f"/users/{b['id']}/assignLicense", {'addLicenses': add, 'removeLicenses': rem})
    c.L(f'Licenties bijgewerkt (+{len(add)} / -{len(rem)}).')
    return {}


def _lid_van(c: Ctx, uid: str) -> set[str]:
    return {m['id'] for m in c.g.all(f'/users/{uid}/memberOf?$select=id&$top=999')}


@api('user.groups')
def user_groups(c: Ctx, b: dict) -> dict:
    r = parallel({'alle': lambda: C.groepen(c), 'mijn': lambda: _lid_van(c, b['id'])})
    for v in r.values():
        if isinstance(v, Exception):
            raise v
    return {'groups': [g for g in r['alle'] if g['id'] in r['mijn']], 'all': r['alle']}


@api('user.group')
def user_group(c: Ctx, b: dict) -> dict:
    g = next((x for x in C.groepen(c) if x['id'] == b.get('groupId')), None)
    if not g:
        raise ApiFout('Groep niet gevonden.')
    u = C.gebruiker(c, b['userId'])
    if b.get('action') == 'add':
        C.lid_toevoegen(c, g['type'], g['id'], g['mail'], u)
        c.L(f"Toegevoegd aan {g['name']}.")
    else:
        C.lid_verwijderen(c, g['type'], g['id'], g['mail'], u)
        c.L(f"Verwijderd uit {g['name']}.")
    return {}


@api('user.sharedscan')
def user_sharedscan(c: Ctx, b: dict) -> dict:
    """Op welke gedeelde postvakken heeft deze gebruiker rechten? Uit de rechtenkaart van de klant
    (eenmalig opgehaald voor alle postvakken), dus voor elke volgende gebruiker direct klaar."""
    upn = str(b['upn']).lower()
    kaart = C.rechtenkaart(c, vers=bool(b.get('fresh')))
    mails = b.get('mailboxes') or [m['mail'] for m in C.gedeeld_lijst(c)]
    res = []
    for mail in mails:
        r = kaart.get(str(mail).lower()) or {}
        res.append({'mail': mail, 'full': upn in r.get('full', ()), 'send': upn in r.get('send', ())})
    return {'results': res}


@api('user.sharedset')
def user_sharedset(c: Ctx, b: dict) -> dict:
    full, send = bool(b.get('full')), bool(b.get('send'))
    if b.get('action') == 'add':
        C.gedeeld_rechten(c, b['mailbox'], b['upn'], full, send, bool(b.get('auto')))
        C.rechten_bijwerken(c, b['mailbox'], b['upn'], full, send, erbij=True)
        c.L(f"Rechten ingesteld op {b['mailbox']}.")
    else:
        x = c.x
        taken = {}
        if full:
            taken['f'] = lambda: x.run('Remove-MailboxPermission', Identity=b['mailbox'], User=b['upn'], AccessRights=['FullAccess'], InheritanceType='All')
        if send:
            taken['s'] = lambda: x.run('Remove-RecipientPermission', Identity=b['mailbox'], Trustee=b['upn'], AccessRights=['SendAs'])
        fouten = [r for r in parallel(taken).values() if isinstance(r, Exception)]
        if fouten:
            raise fouten[0]
        C.rechten_bijwerken(c, b['mailbox'], b['upn'], full, send, erbij=False)
        c.L(f"Rechten verwijderd van {b['mailbox']}.")
    return {}


@api('user.create')
def user_create(c: Ctx, b: dict) -> dict:
    upn = f"{b['alias']}@{b['domain']}".lower()
    if c.g.get(f"/users?$filter=userPrincipalName eq '{upn.replace(chr(39), chr(39) * 2)}'&$select=id").get('value'):
        raise ApiFout(f'Er bestaat al een gebruiker met adres {upn}.')
    problemen: list[str] = []
    p = {'accountEnabled': True, 'displayName': b['name'], 'givenName': b['given'], 'surname': b['sur'], 'userPrincipalName': upn,
         'mailNickname': b['alias'], 'usageLocation': b.get('loc') or 'NL',
         'passwordProfile': {'password': b['password'], 'forceChangePasswordNextSignIn': bool(b.get('force'))}}
    for k, v in (('title', 'jobTitle'), ('dept', 'department'), ('office', 'officeLocation'), ('mobile', 'mobilePhone')):
        if b.get(k):
            p[v] = b[k]
    nieuw = c.g.post('/users', p)
    c.L(f'Gebruiker {upn} aangemaakt.')
    u = {'id': nieuw['id'], 'userPrincipalName': upn}
    heeft_lic = False
    skus = [s for s in (b.get('skus') or ([b['sku']] if b.get('sku') else [])) if s]
    if skus:
        try:
            c.g.post(f"/users/{nieuw['id']}/assignLicense", {'addLicenses': [{'skuId': s, 'disabledPlans': []} for s in skus], 'removeLicenses': []})
            c.L(f'{len(skus)} licentie(s) toegewezen.')
            heeft_lic = True
        except ApiFout as e:
            c.L(f'FOUT licentie: {e}')
            problemen.append(f'Licentie: {e}')
    gr = {g['id']: g for g in C.groepen(c, vers=not b.get('bulk'))}   # bij bulk: groepenlijst uit de cache
    wacht = []
    for gid in b.get('groups') or []:
        g = gr.get(gid)
        if not g:
            continue
        if g['type'] in ('M365', 'Beveiliging'):
            try:
                C.lid_toevoegen(c, g['type'], g['id'], g['mail'], u)
                c.L(f"Toegevoegd aan {g['name']}.")
            except ApiFout as e:
                c.L(f"FOUT groep {g['name']}: {e}")
                problemen.append(f"Groep {g['name']}: {e}")
        else:
            wacht.append(g)
    smb = list(b.get('shared') or [])
    if wacht or smb:
        if heeft_lic and c.exo_ok:
            c.L('Wachten tot de mailbox bestaat (kan enkele minuten duren)...')
            if C.wacht_op_mailbox(c, upn):
                for g in wacht:
                    try:
                        C.lid_toevoegen(c, g['type'], g['id'], g['mail'], u)
                        c.L(f"Toegevoegd aan {g['name']}.")
                    except ApiFout as e:
                        c.L(f"FOUT {g['name']}: {e}")
                        problemen.append(f"Groep {g['name']}: {e}")
                for sm in smb:
                    try:
                        rr = (b.get('sharedRights') or {}).get(sm) or {}   # per postvak (bij kopiëren van een medewerker)
                        C.gedeeld_rechten(c, sm, upn, bool(rr.get('full', b.get('full'))), bool(rr.get('send', b.get('send'))), bool(b.get('auto')))
                        C.rechten_bijwerken(c, sm, upn, bool(rr.get('full', b.get('full'))), bool(rr.get('send', b.get('send'))), erbij=True)
                        c.L(f'Rechten op {sm} ingesteld.')
                    except ApiFout as e:
                        c.L(f'FOUT {sm}: {e}')
                        problemen.append(f'Gedeeld postvak {sm}: {e}')
            else:
                c.L('FOUT: mailbox na 10 minuten nog niet beschikbaar.')
                problemen += [f"Nog toe te voegen: {g['name']}" for g in wacht] + [f'Gedeeld postvak nog toe te voegen: {sm}' for sm in smb]
        else:
            problemen += [f"Overgeslagen (geen mailbox/Exchange): {g['name']}" for g in wacht] + [f'Overgeslagen (geen mailbox/Exchange): {sm}' for sm in smb]
    return {'upn': upn, 'id': nieuw['id'], 'problems': problemen}


def _bytes(tekst: str) -> float:
    m = re.search(r'\(([\d,.\s]+) bytes\)', tekst)
    return float(re.sub(r'\D', '', m.group(1))) if m else 0


@api('offboard')
def offboard(c: Ctx, b: dict) -> dict:
    u = c.g.get(f"/users/{b['id']}?$select=id,displayName,userPrincipalName,assignedLicenses,licenseAssignmentStates")
    upn = u['userPrincipalName']
    naam = u.get('displayName') or upn
    if b.get('shared'):
        x = c.x
        if not b.get('force'):
            try:
                st = x.een('Get-MailboxStatistics', Identity=upn) or {}
                if _bytes(str(st.get('TotalItemSize', ''))) > 50 * 1024 ** 3:
                    return {'confirm': 'Het postvak is groter dan 50 GB. Een gedeeld postvak boven 50 GB heeft een licentie nodig. Toch doorgaan?'}
            except ApiFout:
                pass
        x.run('Set-Mailbox', Identity=upn, Type='Shared')
        c.L('Postvak is nu een gedeeld postvak.')
        for a in b.get('access') or []:
            try:
                C.gedeeld_rechten(c, upn, str(a), bool(b.get('full')), bool(b.get('send')), bool(b.get('auto')))
                c.L(f'Toegang gegeven aan {a}.')
            except ApiFout as e:
                c.L(f'FOUT toegang {a}: {e}')
    if b.get('rename'):
        voor = str(b['rename'])
        if not naam.startswith(voor.strip()):
            nieuw = (voor + naam).strip()
            c.g.patch(f"/users/{u['id']}", {'displayName': nieuw})
            c.L(f'Naam gewijzigd naar: {nieuw}')
        else:
            c.L('De naam heeft deze tekst al, niet opnieuw hernoemd.')
    if b.get('block'):
        c.g.patch(f"/users/{u['id']}", {'accountEnabled': False})
        c.L('Aanmelden geblokkeerd.')
    if b.get('block') or b.get('revoke'):
        C.intrekken(c, u['id'])
        c.L('Alle sessies afgemeld: de gebruiker moet opnieuw inloggen.')
    if b.get('groups'):
        gr = {g['id']: g for g in C.groepen(c, vers=True)}
        for gid in _lid_van(c, u['id']):
            g = gr.get(gid)
            if not g:
                continue
            if not g['edit']:
                c.L(f"Overgeslagen (niet wijzigbaar): {g['name']}")
                continue
            try:
                C.lid_verwijderen(c, g['type'], g['id'], g['mail'], u)
                c.L(f"Verwijderd uit {g['name']}.")
            except ApiFout as e:
                c.L(f"FOUT {g['name']}: {e}")
    if b.get('licenses'):
        alle = u.get('assignedLicenses') or []
        direct = sorted({s['skuId'] for s in u.get('licenseAssignmentStates') or [] if not s.get('assignedByGroup')})
        if direct:
            c.g.post(f"/users/{u['id']}/assignLicense", {'addLicenses': [], 'removeLicenses': direct})
            c.L(f'{len(direct)} licentie(s) verwijderd.')
        rest = len(alle) - len(direct)
        if rest > 0:
            c.L(f'Let op: {rest} licentie(s) komen via een groep en vervallen zodra de gebruiker uit die groep is.')
        if not alle:
            c.L('De gebruiker had geen licenties.')
    c.L(f'KLAAR: {naam} is uit dienst gemeld.')
    return {}
