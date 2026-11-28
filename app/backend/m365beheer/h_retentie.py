"""Archief en retentie (Exchange Online, MRM): online archief per postvak, retentiebeleid en retentietags.

Zoals in PowerShell: Get/Set-Mailbox (RetentionPolicy, archief), Enable/Disable-Mailbox -Archive, -AutoExpandingArchive,
Get-MailboxStatistics (-Archive), Start-ManagedFolderAssistant, Get/New/Set/Remove-RetentionPolicy en -RetentionPolicyTag.
Retentiebeleid van Microsoft Purview (Security & Compliance) valt hier buiten.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from .clients import ApiFout, parallel
from .context import Ctx, api, VERS

LEGE_GUID = '00000000-0000-0000-0000-000000000000'
TYPES = {   # retentietag-typen (waar de tag op werkt)
    'All': 'Hele postvak (standaardtag)', 'Personal': 'Persoonlijk (gebruiker kiest zelf)', 'Inbox': 'Postvak IN', 'SentItems': 'Verzonden items',
    'DeletedItems': 'Verwijderde items', 'JunkEmail': 'Ongewenste e-mail', 'Drafts': 'Concepten', 'Calendar': 'Agenda', 'Tasks': 'Taken',
    'Notes': 'Notities', 'Journal': 'Logboek', 'RssSubscriptions': 'RSS-feeds', 'ConversationHistory': 'Gespreksgeschiedenis',
    'SyncIssues': 'Synchronisatieproblemen', 'RecoverableItems': 'Herstelbare items', 'Archive': 'Archief',
}
ACTIES = {'MoveToArchive': 'Verplaatsen naar archief', 'DeleteAndAllowRecovery': 'Verwijderen (herstelbaar)',
          'PermanentlyDelete': 'Definitief verwijderen', 'MarkAsPastRetentionLimit': 'Markeren als verlopen'}


def _dagen(v) -> int | None:
    """'730.00:00:00' of {'Days': 730} of 730 -> 730. Onbeperkt/leeg -> None."""
    if v is None or v == '' or str(v).lower() == 'unlimited':
        return None
    if isinstance(v, dict):
        v = v.get('Days') if v.get('Days') is not None else v.get('TotalDays')
        return int(float(v)) if v is not None else None
    m = re.match(r'^(\d+)(?:\.|$)', str(v))
    return int(m.group(1)) if m else None


def _bytes(v) -> int | None:
    """'1.234 GB (1,325,000,000 bytes)' of {'Value': ...} -> 1325000000."""
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get('Value') or v.get('value') or str(v)
    m = re.search(r'\(([\d.,]+)\s*bytes\)', str(v))
    if m:
        return int(re.sub(r'[.,]', '', m.group(1)))
    return int(v) if str(v).isdigit() else None


def _namen(v) -> list[str]:
    if not v:
        return []
    l = v if isinstance(v, list) else [v]
    return [str(x.get('Name') if isinstance(x, dict) else x).split('\\')[-1] for x in l]


def _postvak(m: dict) -> dict:
    guid = str(m.get('ArchiveGuid') or LEGE_GUID)
    return {'mail': str(m.get('PrimarySmtpAddress') or ''), 'name': str(m.get('DisplayName') or ''),
            'type': {'UserMailbox': 'Gebruiker', 'SharedMailbox': 'Gedeeld', 'RoomMailbox': 'Ruimte', 'EquipmentMailbox': 'Apparatuur'}
            .get(str(m.get('RecipientTypeDetails')), str(m.get('RecipientTypeDetails') or '')),
            'policy': str(m.get('RetentionPolicy') or ''), 'archive': guid != LEGE_GUID,
            'autoExpand': bool(m.get('AutoExpandingArchiveEnabled')), 'hold': bool(m.get('RetentionHoldEnabled')),
            'litigation': bool(m.get('LitigationHoldEnabled')), 'archiveQuota': str(m.get('ArchiveQuota') or '')}


def _lijst(c: Ctx) -> dict:
    x = c.x
    r = parallel({
        'mb': lambda: x.run('Get-Mailbox', ResultSize='Unlimited', RecipientTypeDetails=['UserMailbox', 'SharedMailbox']),
        'pol': lambda: x.run('Get-RetentionPolicy'),
        'tag': lambda: x.run('Get-RetentionPolicyTag'),
        'org': lambda: x.een('Get-OrganizationConfig') or {},
    })
    for k in ('mb', 'pol', 'tag'):
        if isinstance(r[k], Exception):
            raise r[k]
    tags = sorted([{'name': str(t.get('Name') or ''), 'type': str(t.get('Type') or ''), 'typeText': TYPES.get(str(t.get('Type')), str(t.get('Type') or '')),
                    'days': _dagen(t.get('AgeLimitForRetention')), 'action': str(t.get('RetentionAction') or ''),
                    'actionText': ACTIES.get(str(t.get('RetentionAction')), str(t.get('RetentionAction') or '')),
                    'enabled': t.get('RetentionEnabled') is not False, 'comment': str(t.get('Comment') or ''),
                    'system': bool(t.get('SystemTag'))} for t in r['tag']], key=lambda t: (t['type'] != 'All', t['name'].lower()))
    postvakken = sorted([_postvak(m) for m in r['mb']], key=lambda m: m['name'].lower())
    standaard = next((str(p.get('Name')) for p in r['pol'] if p.get('IsDefault')), '')
    gebruik: dict[str, int] = {}
    for m in postvakken:
        gebruik[m['policy']] = gebruik.get(m['policy'], 0) + 1
    beleid = sorted([{'name': str(p.get('Name') or ''), 'tags': _namen(p.get('RetentionPolicyTagLinks')), 'default': bool(p.get('IsDefault')),
                      'used': gebruik.get(str(p.get('Name') or ''), 0)} for p in r['pol']], key=lambda p: (not p['default'], p['name'].lower()))
    org = r['org'] if isinstance(r['org'], dict) else {}
    return {'mailboxes': postvakken, 'policies': beleid, 'tags': tags, 'defaultPolicy': standaard,
            'autoExpandOrg': bool(org.get('AutoExpandingArchiveEnabled')), 'types': TYPES, 'actions': ACTIES}


@api('ret.list')
def ret_list(c: Ctx, b: dict) -> dict:
    return c.t.cache('retentie', lambda: _lijst(c), VERS, bool(b.get('fresh')))


@api('ret.mailbox')
def ret_mailbox(c: Ctx, b: dict) -> dict:
    """Details van één postvak: grootte van postvak en archief."""
    x, mb = c.x, str(b['mailbox'])
    r = parallel({'m': lambda: x.een('Get-Mailbox', Identity=mb) or {},
                  's': lambda: x.een('Get-MailboxStatistics', Identity=mb) or {},
                  'a': lambda: x.een('Get-MailboxStatistics', Identity=mb, Archive=True) or {}})
    if isinstance(r['m'], Exception):
        raise r['m']
    d = _postvak(r['m'])
    s = r['s'] if isinstance(r['s'], dict) else {}
    a = r['a'] if isinstance(r['a'], dict) and d['archive'] else {}
    d.update(size=_bytes(s.get('TotalItemSize')), items=s.get('ItemCount'), quota=str(r['m'].get('ProhibitSendReceiveQuota') or ''),
             archiveSize=_bytes(a.get('TotalItemSize')) if a else None, archiveItems=a.get('ItemCount') if a else None)
    return d


def _een_postvak(c: Ctx, mb: str, b: dict) -> list[str]:
    x, regels = c.x, []
    if b.get('archive') == 'enable':
        x.run('Enable-Mailbox', Identity=mb, Archive=True)
        regels.append(f'{mb}: online archief aangezet.')
    elif b.get('archive') == 'disable':
        x.run('Disable-Mailbox', Identity=mb, Archive=True, Confirm=False)
        regels.append(f'{mb}: online archief uitgezet (de inhoud blijft 30 dagen herstelbaar).')
    if b.get('autoExpand'):
        x.run('Enable-Mailbox', Identity=mb, AutoExpandingArchive=True)
        regels.append(f'{mb}: automatisch uitbreidend archief aangezet (kan niet meer uit).')
    if b.get('policy'):
        x.run('Set-Mailbox', Identity=mb, RetentionPolicy=str(b['policy']))
        regels.append(f"{mb}: retentiebeleid '{b['policy']}'.")
    if b.get('hold') is not None:
        x.run('Set-Mailbox', Identity=mb, RetentionHoldEnabled=bool(b['hold']))
        regels.append(f"{mb}: retentie {'gepauzeerd (bijv. tijdens verlof)' if b['hold'] else 'weer actief'}.")
    if b.get('process'):
        x.run('Start-ManagedFolderAssistant', Identity=mb)
        regels.append(f'{mb}: verwerking van retentie gestart (kan enkele uren duren).')
    return regels


@api('ret.mailbox.set')
def ret_mailbox_set(c: Ctx, b: dict) -> dict:
    """Eén of meer postvakken: archief aan/uit, automatisch uitbreiden, retentiebeleid, retentie pauzeren, verwerking starten."""
    doelen = [str(m) for m in (b.get('mailboxes') or ([b['mailbox']] if b.get('mailbox') else []))]
    if not doelen:
        raise ApiFout('Kies een of meer postvakken.')

    def een(mb: str) -> list[str]:
        try:
            return _een_postvak(c, mb, b)
        except ApiFout as e:
            tekst = str(e)
            if 'license' in tekst.lower() or 'licentie' in tekst.lower():
                tekst = 'de licentie ondersteunt dit niet (archief vraagt Exchange Online Plan 1 of hoger; automatisch uitbreiden vraagt Plan 2, Business Premium of E3/E5).'
            return [f'FOUT {mb}: {tekst[:220]}']
    with ThreadPoolExecutor(max_workers=6) as ex:
        regels = [r for l in ex.map(een, doelen) for r in l]
    for r in regels:
        c.L(r)
    c.t.weg('retentie')
    return {'results': regels, 'failed': len([r for r in regels if r.startswith('FOUT')])}


@api('ret.policy.save')
def ret_policy_save(c: Ctx, b: dict) -> dict:
    naam = str(b.get('name') or '').strip()
    if not naam:
        raise ApiFout('Geef het beleid een naam.')
    tags = [str(t) for t in b.get('tags') or []]
    if b.get('original'):
        c.x.run('Set-RetentionPolicy', Identity=str(b['original']), Name=naam if naam != b['original'] else None, RetentionPolicyTagLinks=tags, Confirm=False)
        c.L(f"Retentiebeleid '{naam}' bijgewerkt ({len(tags)} tags).")
    else:
        c.x.run('New-RetentionPolicy', Name=naam, RetentionPolicyTagLinks=tags)
        c.L(f"Retentiebeleid '{naam}' aangemaakt ({len(tags)} tags).")
    if b.get('default'):
        c.x.run('Set-RetentionPolicy', Identity=naam, IsDefault=True, Confirm=False)
        c.L(f"'{naam}' is nu het standaardbeleid voor nieuwe postvakken.")
    c.t.weg('retentie')
    return {}


@api('ret.policy.delete')
def ret_policy_delete(c: Ctx, b: dict) -> dict:
    naam = str(b['name'])
    c.x.run('Remove-RetentionPolicy', Identity=naam, Confirm=False)
    c.L(f"Retentiebeleid '{naam}' verwijderd.")
    c.t.weg('retentie')
    return {}


@api('ret.tag.save')
def ret_tag_save(c: Ctx, b: dict) -> dict:
    naam = str(b.get('name') or '').strip()
    if not naam:
        raise ApiFout('Geef de tag een naam.')
    actie = str(b.get('action') or '')
    if actie not in ACTIES:
        raise ApiFout('Kies een actie.')
    dagen = int(b.get('days') or 0)
    if dagen < 1 or dagen > 24855:
        raise ApiFout('Kies een bewaartermijn tussen 1 en 24855 dagen.')
    p = {'AgeLimitForRetention': f'{dagen}.00:00:00', 'RetentionAction': actie, 'RetentionEnabled': b.get('enabled', True) is not False,
         'Comment': str(b.get('comment') or '') or None}
    if b.get('original'):
        c.x.run('Set-RetentionPolicyTag', Identity=str(b['original']), Name=naam if naam != b['original'] else None, Confirm=False, **p)
        c.L(f"Retentietag '{naam}' bijgewerkt.")
    else:
        soort = str(b.get('type') or '')
        if soort not in TYPES:
            raise ApiFout('Kies waar de tag voor geldt.')
        if actie == 'MoveToArchive' and soort not in ('All', 'Personal', 'RecoverableItems'):
            raise ApiFout('Verplaatsen naar archief kan alleen met een standaardtag (hele postvak), persoonlijke tag of herstelbare items.')
        c.x.run('New-RetentionPolicyTag', Name=naam, Type=soort, **p)
        c.L(f"Retentietag '{naam}' aangemaakt.")
    c.t.weg('retentie')
    return {}


@api('ret.tag.delete')
def ret_tag_delete(c: Ctx, b: dict) -> dict:
    naam = str(b['name'])
    c.x.run('Remove-RetentionPolicyTag', Identity=naam, Confirm=False)
    c.L(f"Retentietag '{naam}' verwijderd.")
    c.t.weg('retentie')
    return {}
