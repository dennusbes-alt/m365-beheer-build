"""Agendarechten, groepen en gedeelde postvakken."""
from __future__ import annotations

from . import common as C
from .clients import ApiFout, parallel, hashtabel
from .context import Ctx, api

SPECIAAL = {'Default', 'Standaard', 'Anonymous', 'Anoniem'}


def _gebruiker_van_recht(p: dict) -> tuple[str, str]:
    """Naam en sleutel (mailadres indien bekend) uit een MailboxFolderPermission."""
    u = p.get('User')
    naam = str(p.get('UserDisplayName') or '')
    sleutel = ''
    if isinstance(u, dict):
        naam = naam or str(u.get('DisplayName') or '')
        r = u.get('ADRecipient') or {}
        if isinstance(r, dict):
            sleutel = str(r.get('PrimarySmtpAddress') or '')
        rp = u.get('RecipientPrincipal')
        if not sleutel and isinstance(rp, str):
            sleutel = rp
    elif u:
        naam = naam or str(u)
    naam = naam or 'Onbekend'
    return naam, sleutel or naam


@api('cal.get')
def cal_get(c: Ctx, b: dict) -> dict:
    fid = C.agenda_id(c, b['mailbox'])
    l = []
    for p in c.x.run('Get-MailboxFolderPermission', Identity=fid):
        naam, sleutel = _gebruiker_van_recht(p)
        ar = p.get('AccessRights')
        rechten = ', '.join(ar) if isinstance(ar, list) else str(ar or '')
        vl = p.get('SharingPermissionFlags')
        vl = [str(x).strip() for x in (vl if isinstance(vl, list) else str(vl or '').split(',')) if x and str(x).strip() != 'None']
        rol = (ar[0] if isinstance(ar, list) and ar else str(ar or '')).strip()
        l.append({'name': naam, 'key': sleutel, 'rights': rechten, 'role': rol, 'delegate': 'Delegate' in vl,
                  'priv': 'CanViewPrivateItems' in vl, 'flags': vl, 'special': naam in SPECIAAL})
    return {'rights': l}


@api('cal.set')
def cal_set(c: Ctx, b: dict) -> dict:
    doel = list(b.get('targets') or [])
    if b.get('mutual'):
        paren = [(o, g) for o in doel for g in doel if o != g]
    else:
        paren = [(o, str(b['who'])) for o in doel if o != b.get('who')]
    for postvak, wie in paren:
        try:
            C.agenda_recht(c, postvak, wie, b['role'], bool(b.get('delegate')), bool(b.get('priv')), bool(b.get('notify')))
            extra = ' als gemachtigde' if b['role'] == 'Editor' and b.get('delegate') else ''
            extra += ' (ook privé-afspraken)' if extra and b.get('priv') else ''
            c.L(f"{wie} heeft nu {b['role']}{extra} op de agenda van {postvak}" + (', met melding.' if b.get('notify') else '.'))
        except ApiFout as e:
            c.L(f'FOUT {wie} op {postvak}: {e}')
    return {}


@api('cal.remove')
def cal_remove(c: Ctx, b: dict) -> dict:
    fid = C.agenda_id(c, b['mailbox'])
    for k in b.get('users') or []:
        try:
            c.x.run('Remove-MailboxFolderPermission', Identity=fid, User=k)
            c.L(f'Rechten van {k} verwijderd.')
        except ApiFout as e:
            c.L(f'FOUT {k}: {e}')
    return {}


@api('groups.list')
def groups_list(c: Ctx, b: dict) -> dict:
    l = list(C.groepen(c, vers=bool(b.get('fresh'))))
    s = [{'id': m['mail'], 'name': m['name'], 'mail': m['mail'], 'type': 'Gedeeld postvak', 'sync': False, 'edit': True}
         for m in C.gedeeld_lijst(c)]
    return {'groups': l + s}


@api('group.members')
def group_members(c: Ctx, b: dict) -> dict:
    rows = []
    ty = b.get('type')
    if ty in ('M365', 'Beveiliging', 'Dynamisch'):
        for m in c.g.all(f"/groups/{b['id']}/members?$select=id,displayName,userPrincipalName,mail&$top=999"):
            soort = {'user': 'Gebruiker', 'group': 'Groep', 'device': 'Apparaat'}.get(
                str(m.get('@odata.type', '')).replace('#microsoft.graph.', ''), 'Overig')
            rows.append({'id': m['id'], 'key': m.get('userPrincipalName') or m.get('mail') or '', 'name': m.get('displayName') or '', 'info': soort})
    elif ty == 'Gedeeld postvak':
        r = parallel({'rechten': lambda: C.rechten_van_postvak(c, b['mail']), 'namens': lambda: _namens(c, b['mail'])})
        if isinstance(r['rechten'], Exception):
            raise r['rechten']
        rechten = r['rechten']
        namens = r['namens'] if isinstance(r['namens'], set) else set()
        for u in sorted(rechten['full'] | rechten['send'] | namens):
            full, send, behalf = u in rechten['full'], u in rechten['send'], u in namens
            info = ', '.join(x for x, ok in (('Volledige toegang', full), ('Verzenden als', send), ('Verzenden namens', behalf)) if ok)
            rows.append({'id': u, 'key': u, 'name': u, 'info': info, 'full': full, 'send': send, 'behalf': behalf})
    else:
        for m in c.x.run('Get-DistributionGroupMember', Identity=b['mail'], ResultSize='Unlimited'):
            adres = str(m.get('PrimarySmtpAddress') or '')
            rows.append({'id': adres, 'key': adres, 'name': m.get('DisplayName') or adres, 'info': str(m.get('RecipientType') or '')})
    return {'members': rows}


def _namens(c: Ctx, mail: str) -> set[str]:
    """Wie mag 'verzenden namens' (GrantSendOnBehalfTo). Exchange geeft namen terug; die worden e-mailadressen."""
    mb = c.x.een('Get-Mailbox', Identity=mail) or {}
    namen = [str(n) for n in (mb.get('GrantSendOnBehalfTo') or []) if str(n).strip()]
    if not namen:
        return set()
    x = c.x
    r = parallel({n: (lambda n=n: x.een('Get-Recipient', Identity=n)) for n in namen})
    return {str((v or {}).get('PrimarySmtpAddress') or k).lower() for k, v in r.items() if not isinstance(v, Exception)}


@api('shared.member.set')
def shared_member_set(c: Ctx, b: dict) -> dict:
    """Rechten van één persoon op een gedeeld postvak aanpassen (zoals Add/Remove-MailboxPermission, -RecipientPermission
    en Set-Mailbox -GrantSendOnBehalfTo). Automapping is niet uit te lezen; is er een keuze gemaakt, dan wordt volledige
    toegang opnieuw gezet met die automapping."""
    mail, wie = str(b['mail']), str(b['key'])
    was = b.get('was') or {}
    full, send, behalf = bool(b.get('full')), bool(b.get('send')), bool(b.get('behalf'))
    auto = b.get('auto')   # None = ongewijzigd, True/False = aan/uit
    x = c.x
    if not (full or send or behalf):
        raise ApiFout('Laat minimaal een recht aan, of verwijder de persoon uit de lijst.')
    gedaan = []
    if full and (not was.get('full') or auto is not None):
        if was.get('full'):   # automapping wijzigen: eerst weghalen, dan opnieuw met de gekozen automapping
            x.run('Remove-MailboxPermission', Identity=mail, User=wie, AccessRights=['FullAccess'], InheritanceType='All', Confirm=False)
        x.run('Add-MailboxPermission', Identity=mail, User=wie, AccessRights=['FullAccess'], InheritanceType='All',
              AutoMapping=True if auto is None else bool(auto))
        gedaan.append('volledige toegang' + ('' if auto is None else f" (automapping {'aan' if auto else 'uit'})"))
    elif not full and was.get('full'):
        x.run('Remove-MailboxPermission', Identity=mail, User=wie, AccessRights=['FullAccess'], InheritanceType='All', Confirm=False)
        gedaan.append('volledige toegang weggehaald')
    if send != bool(was.get('send')):
        if send:
            x.run('Add-RecipientPermission', Identity=mail, Trustee=wie, AccessRights=['SendAs'], Confirm=False)
        else:
            x.run('Remove-RecipientPermission', Identity=mail, Trustee=wie, AccessRights=['SendAs'], Confirm=False)
        gedaan.append('verzenden als ' + ('aan' if send else 'uit'))
    if behalf != bool(was.get('behalf')):
        x.run('Set-Mailbox', Identity=mail, GrantSendOnBehalfTo=hashtabel(**({'Add': wie} if behalf else {'Remove': wie})))
        gedaan.append('verzenden namens ' + ('aan' if behalf else 'uit'))
    # Bewaarde rechtenkaart bijwerken (voor het scherm Gebruikers)
    C.rechten_bijwerken(c, mail, wie, full and not was.get('full'), send and not was.get('send'), erbij=True)
    C.rechten_bijwerken(c, mail, wie, was.get('full') and not full, was.get('send') and not send, erbij=False)
    c.L(f"{wie}: {', '.join(gedaan) if gedaan else 'niets gewijzigd'}.")
    return {}


@api('group.add')
def group_add(c: Ctx, b: dict) -> dict:
    u = C.gebruiker(c, b['userId'])
    if b.get('type') == 'Gedeeld postvak':
        if not (b.get('full') or b.get('send') or b.get('behalf')):
            raise ApiFout('Vink minimaal een recht aan.')
        C.gedeeld_rechten(c, b['mail'], u['userPrincipalName'], bool(b.get('full')), bool(b.get('send')), bool(b.get('auto')))
        if b.get('behalf'):
            c.x.run('Set-Mailbox', Identity=b['mail'], GrantSendOnBehalfTo=hashtabel(Add=u['userPrincipalName']))
        C.rechten_bijwerken(c, b['mail'], u['userPrincipalName'], bool(b.get('full')), bool(b.get('send')), erbij=True)
    else:
        C.lid_toevoegen(c, b['type'], b['id'], b.get('mail') or '', u)
    c.L(f"{u.get('displayName')} toegevoegd.")
    return {}


@api('group.remove')
def group_remove(c: Ctx, b: dict) -> dict:
    gedeeld = b.get('type') == 'Gedeeld postvak'
    x = c.x if gedeeld or b.get('type') in ('Distributielijst', 'Mail-beveiliging') else None

    def een(m: dict) -> None:
        if gedeeld:
            if m.get('full'):
                x.run('Remove-MailboxPermission', Identity=b['mail'], User=m['key'], AccessRights=['FullAccess'], InheritanceType='All')
            if m.get('send'):
                x.run('Remove-RecipientPermission', Identity=b['mail'], Trustee=m['key'], AccessRights=['SendAs'])
            if m.get('behalf'):
                x.run('Set-Mailbox', Identity=b['mail'], GrantSendOnBehalfTo=hashtabel(Remove=m['key']))
            C.rechten_bijwerken(c, b['mail'], m['key'], bool(m.get('full')), bool(m.get('send')), erbij=False)
        else:
            C.lid_verwijderen(c, b['type'], b['id'], b.get('mail') or '', {'id': m['id'], 'userPrincipalName': m['key']})

    leden = list(b.get('members') or [])
    # Alle leden tegelijk verwijderen in plaats van een voor een
    uitkomst = parallel({str(i): (lambda m=m: een(m)) for i, m in enumerate(leden)})
    for i, m in enumerate(leden):
        r = uitkomst[str(i)]
        c.L(f"FOUT {m.get('name')}: {r}" if isinstance(r, Exception) else f"{m.get('name')} verwijderd.")
    return {}


@api('group.delete')
def group_delete(c: Ctx, b: dict) -> dict:
    ty = b.get('type')
    if ty in ('M365', 'Beveiliging', 'Dynamisch'):
        c.g.delete(f"/groups/{b['id']}")
    elif ty in ('Distributielijst', 'Mail-beveiliging'):
        c.x.run('Remove-DistributionGroup', Identity=b['mail'], BypassSecurityGroupManagerCheck=True)
    elif ty == 'Gedeeld postvak':
        c.x.run('Remove-Mailbox', Identity=b['mail'])
    else:
        raise ApiFout('Dit type kan hier niet verwijderd worden.')
    c.L(f"{b.get('name')} verwijderd.")
    return {}


@api('group.create')
def group_create(c: Ctx, b: dict) -> dict:
    naam, alias = b['name'], b['alias']
    adres = f"{alias}@{b.get('domain')}"
    soort = b.get('kind')
    if soort == 'M365':
        c.g.post('/groups', {'displayName': naam, 'mailNickname': alias, 'mailEnabled': True, 'securityEnabled': False, 'groupTypes': ['Unified']})
    elif soort == 'Beveiliging':
        c.g.post('/groups', {'displayName': naam, 'mailNickname': alias, 'mailEnabled': False, 'securityEnabled': True, 'groupTypes': []})
    elif soort == 'Distributielijst':
        c.x.run('New-DistributionGroup', Name=naam, DisplayName=naam, Alias=alias, PrimarySmtpAddress=adres, Type='Distribution')
    elif soort == 'Gedeeld':
        c.x.run('New-Mailbox', Shared=True, Name=naam, DisplayName=naam, Alias=alias, PrimarySmtpAddress=adres)
    else:
        raise ApiFout('Onbekend type.')
    c.L(f'{naam} aangemaakt.')
    return {}


@api('group.deletemany')
def group_deletemany(c: Ctx, b: dict) -> dict:
    """Meerdere groepen of gedeelde postvakken in één keer verwijderen (op de achtergrond, met voortgang)."""
    from . import klussen
    items = [g for g in b.get('groups') or [] if g.get('type') != 'Dynamisch' or g.get('id')]

    def een(sub: Ctx, g: dict) -> dict:
        group_delete(sub, g)
        return {}
    k = klussen.start(c, f'{len(items)} groepen/postvakken verwijderen', items, een, lambda g: g.get('name', ''), tegelijk=4)
    c.t.weg('groepen', 'gedeeld', 'gedeeldrechten')
    return k
