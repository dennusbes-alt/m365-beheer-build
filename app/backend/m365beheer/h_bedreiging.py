"""Bedreigingsbeheer: anti-spambeleid, anti-phishingbeleid en DKIM (Exchange Online Protection / Defender)."""
from __future__ import annotations

from .clients import ApiFout, _sessie, parallel
from .context import Ctx, api

# Per soort: cmdlets, de koppeling regel -> beleid, en welke eigenschappen de interface mag lezen/bewerken
SOORTEN = {
    'spam': {
        'beleid': 'HostedContentFilterPolicy', 'regel': 'HostedContentFilterRule', 'koppel': 'HostedContentFilterPolicy',
        'velden': [
            # drempelwaarden en eigenschappen
            'BulkThreshold', 'MarkAsSpamBulkMail', 'QuarantineRetentionPeriod', 'InlineSafetyTipsEnabled', 'SpamZapEnabled', 'PhishZapEnabled',
            'IncreaseScoreWithImageLinks', 'IncreaseScoreWithNumericIps', 'IncreaseScoreWithRedirectToOtherPort', 'IncreaseScoreWithBizOrInfoUrls',
            'MarkAsSpamEmptyMessages', 'MarkAsSpamJavaScriptInHtml', 'MarkAsSpamFramesInHtml', 'MarkAsSpamObjectTagsInHtml',
            'MarkAsSpamEmbedTagsInHtml', 'MarkAsSpamFormTagsInHtml', 'MarkAsSpamWebBugsInHtml', 'MarkAsSpamSensitiveWordList',
            'MarkAsSpamSpfRecordHardFail', 'MarkAsSpamFromAddressAuthFail', 'MarkAsSpamNdrBackscatter',
            'EnableLanguageBlockList', 'LanguageBlockList', 'EnableRegionBlockList', 'RegionBlockList',
            # acties
            'SpamAction', 'HighConfidenceSpamAction', 'PhishSpamAction', 'HighConfidencePhishAction', 'BulkSpamAction',
            'AddXHeaderValue', 'ModifySubjectValue',
            # toegestaan en geblokkeerd
            'AllowedSenders', 'AllowedSenderDomains', 'BlockedSenders', 'BlockedSenderDomains',
        ],
    },
    'phish': {
        'beleid': 'AntiPhishPolicy', 'regel': 'AntiPhishRule', 'koppel': 'AntiPhishPolicy',
        'velden': [
            # beveiligingsinstellingen
            'Enabled', 'PhishThresholdLevel', 'EnableSpoofIntelligence', 'HonorDmarcPolicy', 'EnableUnauthenticatedSender', 'EnableViaTag',
            'EnableFirstContactSafetyTips', 'EnableMailboxIntelligence', 'EnableMailboxIntelligenceProtection',
            'EnableTargetedUserProtection', 'TargetedUsersToProtect', 'EnableOrganizationDomainsProtection',
            'EnableTargetedDomainsProtection', 'TargetedDomainsToProtect', 'ExcludedDomains', 'ExcludedSenders',
            'EnableSimilarUsersSafetyTips', 'EnableSimilarDomainsSafetyTips', 'EnableUnusualCharactersSafetyTips',
            # acties
            'AuthenticationFailAction', 'DmarcQuarantineAction', 'DmarcRejectAction', 'MailboxIntelligenceProtectionAction',
            'TargetedUserProtectionAction', 'TargetedDomainProtectionAction',
        ],
    },
}
LIJSTVELDEN = {'AllowedSenders', 'AllowedSenderDomains', 'BlockedSenders', 'BlockedSenderDomains', 'LanguageBlockList', 'RegionBlockList',
               'TargetedUsersToProtect', 'TargetedDomainsToProtect', 'ExcludedDomains', 'ExcludedSenders'}


def _soort(b: dict) -> dict:
    s = SOORTEN.get(b.get('kind'))
    if not s:
        raise ApiFout('Onbekende soort beleid.')
    return s


def _waarde(v):
    if isinstance(v, list):
        return [str(x.get('Sender') if isinstance(x, dict) and 'Sender' in x else x) for x in v]
    return v


def _lijst(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v or '').replace(';', ',').replace('\n', ',').split(',') if x.strip()]


@api('threat.list')
def threat_list(c: Ctx, b: dict) -> dict:
    s = _soort(b)
    x = c.x
    r = parallel({'p': lambda: x.run(f"Get-{s['beleid']}"), 'r': lambda: x.run(f"Get-{s['regel']}")})
    if isinstance(r['p'], Exception):
        raise r['p']
    regels = {str(g.get(s['koppel'])): g for g in (r['r'] if isinstance(r['r'], list) else [])}
    uit = []
    for p in r['p']:
        naam = str(p.get('Name'))
        g = regels.get(naam) or {}
        standaard = bool(p.get('IsDefault'))
        preset = naam.startswith(('Standard Preset', 'Strict Preset'))   # door Microsoft beheerde voorinstelling
        uit.append({'name': naam, 'default': standaard, 'preset': preset, 'rule': g.get('Name') or '',
                    'state': 'Altijd aan' if standaard else 'Voorinstelling' if preset else str(g.get('State') or 'Geen regel'),
                    'priority': 'Laagst' if standaard else g.get('Priority'),
                    'domains': _waarde(g.get('RecipientDomainIs')) or [], 'users': _waarde(g.get('SentTo')) or [],
                    'groups': _waarde(g.get('SentToMemberOf')) or [], 'enabled': p.get('Enabled', True)})
    uit.sort(key=lambda p: (p['default'], p['priority'] if isinstance(p['priority'], int) else 999))
    return {'policies': uit}


@api('threat.get')
def threat_get(c: Ctx, b: dict) -> dict:
    s = _soort(b)
    p = c.x.een(f"Get-{s['beleid']}", Identity=b['name'])
    if not p:
        raise ApiFout('Beleid niet gevonden.')
    return {'name': p.get('Name'), 'default': bool(p.get('IsDefault')),
            'props': {k: _waarde(p.get(k)) for k in s['velden'] if k in p}}


@api('threat.set')
def threat_set(c: Ctx, b: dict) -> dict:
    s = _soort(b)
    props = {k: (_lijst(v) if k in LIJSTVELDEN else v) for k, v in (b.get('props') or {}).items() if k in s['velden']}
    if not props:
        raise ApiFout('Geen wijzigingen.')
    try:
        c.x.run(f"Set-{s['beleid']}", Identity=b['name'], **props)
    except ApiFout as e:
        if 'not available' in str(e).lower() or 'license' in str(e).lower():
            raise ApiFout(f'Niet alle instellingen zijn beschikbaar bij deze klant (Defender for Office 365 nodig voor imitatiebeveiliging). {e}')
        raise
    c.L(f"Beleid '{b['name']}' opgeslagen ({len(props)} instelling(en)).")
    return {}


@api('threat.create')
def threat_create(c: Ctx, b: dict) -> dict:
    s = _soort(b)
    naam = str(b.get('name') or '').strip()
    if not naam:
        raise ApiFout('Geef het beleid een naam.')
    domeinen, users, groepen = _lijst(b.get('domains')), _lijst(b.get('users')), _lijst(b.get('groups'))
    if not (domeinen or users or groepen):
        raise ApiFout('Kies voor wie het beleid geldt (domeinen, gebruikers of groepen).')
    c.x.run(f"New-{s['beleid']}", Name=naam)
    regel = {'Name': naam, s['koppel']: naam}
    if domeinen:
        regel['RecipientDomainIs'] = domeinen
    if users:
        regel['SentTo'] = users
    if groepen:
        regel['SentToMemberOf'] = groepen
    if b.get('priority') not in (None, ''):
        regel['Priority'] = int(b['priority'])
    try:
        c.x.run(f"New-{s['regel']}", **regel)
    except ApiFout:
        c.x.run(f"Remove-{s['beleid']}", Identity=naam)   # geen half beleid achterlaten
        raise
    c.L(f"Beleid '{naam}' aangemaakt.")
    return {}


@api('threat.delete')
def threat_delete(c: Ctx, b: dict) -> dict:
    s = _soort(b)
    for naam in b.get('names') or [b.get('name')]:
        try:
            p = c.x.een(f"Get-{s['beleid']}", Identity=naam) or {}
            if p.get('IsDefault'):
                c.L(f"Overgeslagen: '{naam}' is het standaardbeleid en kan niet verwijderd worden.")
                continue
            for g in c.x.run(f"Get-{s['regel']}"):
                if str(g.get(s['koppel'])) == naam:
                    c.x.run(f"Remove-{s['regel']}", Identity=g.get('Name'))
            c.x.run(f"Remove-{s['beleid']}", Identity=naam)
            c.L(f"Beleid '{naam}' verwijderd.")
        except ApiFout as e:
            c.L(f'FOUT {naam}: {e}')
    return {}


@api('threat.rule')
def threat_rule(c: Ctx, b: dict) -> dict:
    s = _soort(b)
    regel = b['rule']
    if 'enabled' in b:
        c.x.run(f"{'Enable' if b['enabled'] else 'Disable'}-{s['regel']}", Identity=regel)
        c.L(f"Regel {'ingeschakeld' if b['enabled'] else 'uitgeschakeld'}.")
    upd = {}
    if b.get('priority') not in (None, ''):
        upd['Priority'] = int(b['priority'])
    for k, param in (('domains', 'RecipientDomainIs'), ('users', 'SentTo'), ('groups', 'SentToMemberOf')):
        if k in b:
            upd[param] = _lijst(b[k]) or None
    if upd:
        c.x.run(f"Set-{s['regel']}", Identity=regel, **upd)
        c.L('Regel bijgewerkt.')
    return {}


# ---------------- DKIM ----------------
def _cname(naam: str) -> str:
    """DNS-controle via DNS-over-HTTPS (Cloudflare), zodat dit ook werkt zonder lokale DNS-tools."""
    try:
        r = _sessie().get('https://cloudflare-dns.com/dns-query', params={'name': naam, 'type': 'CNAME'},
                          headers={'Accept': 'application/dns-json'}, timeout=8)
        for a in r.json().get('Answer') or []:
            if a.get('type') == 5:
                return str(a.get('data', '')).rstrip('.')
    except Exception:
        pass
    return ''


@api('dkim.list')
def dkim_list(c: Ctx, b: dict) -> dict:
    x = c.x
    r = parallel({'d': lambda: x.run('Get-AcceptedDomain'), 'k': lambda: x.run('Get-DkimSigningConfig')})
    if isinstance(r['d'], Exception):
        raise r['d']
    conf = {str(k.get('Domain') or k.get('Name')).lower(): k for k in (r['k'] if isinstance(r['k'], list) else [])}
    uit = []
    for d in r['d']:
        naam = str(d.get('DomainName') or d.get('Name'))
        k = conf.get(naam.lower())
        uit.append({'domain': naam, 'configured': bool(k), 'enabled': bool(k and k.get('Enabled')),
                    'status': str((k or {}).get('Status') or ('Niet ingesteld' if not k else '')),
                    'onmicrosoft': naam.lower().endswith('.onmicrosoft.com'), 'default': bool(d.get('Default'))})
    uit.sort(key=lambda d: (d['onmicrosoft'], d['domain']))
    return {'domains': uit}


@api('dkim.get')
def dkim_get(c: Ctx, b: dict) -> dict:
    dom = b['domain']
    k = None
    try:
        k = c.x.een('Get-DkimSigningConfig', Identity=dom)
    except ApiFout:
        pass
    if not k:
        return {'domain': dom, 'configured': False}
    records = []
    for sel in ('Selector1', 'Selector2'):
        doel = str(k.get(f'{sel}CNAME') or '')
        naam = f"{sel.lower()}._domainkey.{dom}"
        huidig = _cname(naam)
        records.append({'name': naam, 'value': doel, 'current': huidig, 'ok': bool(doel) and huidig.lower() == doel.lower()})
    return {'domain': dom, 'configured': True, 'enabled': bool(k.get('Enabled')), 'status': str(k.get('Status') or ''),
            'keySize': k.get('Selector1KeySize') or k.get('KeySize'), 'created': str(k.get('KeyCreationTime') or ''),
            'rotateOn': str(k.get('RotateOnDate') or ''), 'lastChecked': str(k.get('LastChecked') or ''),
            'records': records, 'onmicrosoft': dom.lower().endswith('.onmicrosoft.com')}


@api('dkim.create')
def dkim_create(c: Ctx, b: dict) -> dict:
    c.x.run('New-DkimSigningConfig', DomainName=b['domain'], Enabled=False, KeySize=2048)
    c.L(f"DKIM ingesteld voor {b['domain']}. Zet de twee CNAME-records in de DNS en schakel DKIM daarna in.")
    return dkim_get(c, b)


@api('dkim.set')
def dkim_set(c: Ctx, b: dict) -> dict:
    try:
        c.x.run('Set-DkimSigningConfig', Identity=b['domain'], Enabled=bool(b.get('enabled')))
    except ApiFout as e:
        if 'cname' in str(e).lower():
            raise ApiFout('DKIM kan nog niet aan: de CNAME-records staan (nog) niet goed in de DNS. Zet de records zoals hieronder '
                          'getoond en probeer het opnieuw (DNS-wijzigingen kunnen even duren).')
        raise
    c.L(f"DKIM voor {b['domain']} {'ingeschakeld' if b.get('enabled') else 'uitgeschakeld'}.")
    return dkim_get(c, b)


@api('dkim.rotate')
def dkim_rotate(c: Ctx, b: dict) -> dict:
    c.x.run('Rotate-DkimSigningConfig', Identity=b['domain'], KeySize=2048)
    c.L(f"DKIM-sleutels voor {b['domain']} worden geroteerd (de nieuwe sleutel is binnen enkele dagen actief).")
    return dkim_get(c, b)
