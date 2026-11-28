"""Exchange-functies: message trace, transportregels (e-mailstroomregels) en connectors."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .clients import ApiFout, parallel
from .context import Ctx, api


def _s(v) -> str:
    if isinstance(v, list):
        return ', '.join(str(x) for x in v)
    return '' if v is None else str(v)


def _lijst(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return [x.strip() for x in str(v or '').replace(';', ',').replace('\n', ',').split(',') if x.strip()]


def _datum(s: str, eind: bool = False) -> str:
    """'2026-11-25' of ISO -> UTC ISO-tekst voor Exchange."""
    if not s:
        return ''
    d = datetime.fromisoformat(s.replace('Z', '+00:00')) if 'T' in s else datetime.fromisoformat(s)
    if 'T' not in s and eind:
        d = d + timedelta(days=1) - timedelta(seconds=1)
    if d.tzinfo is None:
        d = d.astimezone() if 'T' in s else d.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------- Message trace ----------------
MAX_PER_BLOK = 5000          # Get-MessageTraceV2 geeft per aanvraag maximaal 5000 resultaten
BLOK = timedelta(days=10) - timedelta(seconds=1)   # Microsoft staat maximaal 10 dagen per aanvraag toe
MAX_TOTAAL = 100000


def _tijd(s: str) -> datetime:
    return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


@api('trace.search')
def trace_search(c: Ctx, b: dict) -> dict:
    """Berichten zoeken, tot 90 dagen terug. Een langere periode dan 10 dagen wordt automatisch opgedeeld in blokken van
    maximaal 10 dagen die tegelijk worden opgevraagd. Een blok met 5000 resultaten (het maximum) wordt verder opgedeeld,
    zodat er geen berichten wegvallen."""
    nu = datetime.now(timezone.utc)
    start = _tijd(_datum(b.get('start')) or _iso(nu - timedelta(days=2)))
    eind = _tijd(_datum(b.get('end'), eind=True) or _iso(nu))
    grens = nu - timedelta(days=90) + timedelta(minutes=5)
    if start < grens:
        start = grens
    if eind > nu:
        eind = nu
    if eind <= start:
        raise ApiFout('De einddatum moet na de begindatum liggen.')
    filt = {}
    if b.get('sender'):
        filt['SenderAddress'] = _lijst(b['sender'])
    if b.get('recipient'):
        filt['RecipientAddress'] = _lijst(b['recipient'])
    if b.get('status'):
        filt['Status'] = _lijst(b['status'])
    if b.get('subject'):
        filt['Subject'] = str(b['subject'])
        filt['SubjectFilterType'] = 'Contains'
    x = c.x
    oud = {'v': False}   # tenant zonder Get-MessageTraceV2: oude cmdlet (alleen laatste 10 dagen, geen onderwerpfilter)

    def blok(van: datetime, tot: datetime, diepte: int = 0) -> list[dict]:
        p = {**filt, 'StartDate': _iso(van), 'EndDate': _iso(tot), 'ResultSize': MAX_PER_BLOK}
        try:
            if oud['v']:
                raise ApiFout('not recognized')
            rijen = x.run('Get-MessageTraceV2', **p)
        except ApiFout as e:
            if 'not recognized' not in str(e).lower() and not ('is not' in str(e).lower() and 'cmdlet' in str(e).lower()):
                raise
            oud['v'] = True
            p.pop('Subject', None), p.pop('SubjectFilterType', None)
            p['PageSize'] = p.pop('ResultSize')
            rijen = x.run('Get-MessageTrace', **p)
        # Maximum bereikt: periode halveren en beide helften opvragen (tot op een half uur nauwkeurig)
        if len(rijen) >= MAX_PER_BLOK and tot - van > timedelta(minutes=30) and diepte < 8:
            midden = van + (tot - van) / 2   # na elkaar: binnen een blok geen nieuwe taken op de gedeelde werkpool
            return blok(van, midden, diepte + 1) + blok(midden, tot, diepte + 1)
        return rijen

    blokken, van = [], start
    while van < eind:
        tot = min(van + BLOK, eind)
        blokken.append((van, tot))
        van = tot
    r = parallel({str(k): (lambda a=a, z=z: blok(a, z)) for k, (a, z) in enumerate(blokken)})
    rijen, fouten = [], []
    for k in sorted(r, key=int):
        if isinstance(r[k], Exception):
            fouten.append(r[k])
        else:
            rijen.extend(r[k])
    if fouten and not rijen:
        raise fouten[0]
    for f in fouten[:3]:
        c.L(f'FOUT bij een deel van de periode: {f}')
    gezien, uit = set(), []
    for m in rijen:
        sleutel = (_s(m.get('MessageTraceId')), _s(m.get('RecipientAddress')), _s(m.get('Received')))
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        uit.append({'received': _s(m.get('Received')), 'sender': _s(m.get('SenderAddress')), 'recipient': _s(m.get('RecipientAddress')),
                    'subject': _s(m.get('Subject')), 'status': _s(m.get('Status')), 'size': m.get('Size') or 0,
                    'traceId': _s(m.get('MessageTraceId')), 'messageId': _s(m.get('MessageId')), 'fromIp': _s(m.get('FromIP')),
                    'toIp': _s(m.get('ToIP'))})
    uit.sort(key=lambda m: m['received'], reverse=True)
    afgekapt = len(uit) > MAX_TOTAAL
    if oud['v'] and (nu - start).days > 10:
        c.L('Let op: deze klant heeft nog de oude message trace; Microsoft geeft dan alleen de laatste 10 dagen.')
    return {'messages': uit[:MAX_TOTAAL], 'start': _iso(start), 'end': _iso(eind), 'blocks': len(blokken), 'truncated': afgekapt}


@api('trace.detail')
def trace_detail(c: Ctx, b: dict) -> dict:
    p = {'MessageTraceId': b['traceId'], 'RecipientAddress': b['recipient']}
    try:
        rijen = c.x.run('Get-MessageTraceDetailV2', **p)
    except ApiFout as e:
        if 'not recognized' not in str(e).lower():
            raise
        rijen = c.x.run('Get-MessageTraceDetail', **p)
    return {'events': [{'date': _s(r.get('Date')), 'event': _s(r.get('Event')), 'action': _s(r.get('Action')),
                        'detail': _s(r.get('Detail')), 'data': _s(r.get('Data'))[:2000]} for r in rijen]}


# ---------------- Transportregels ----------------
@api('rules.list')
def rules_list(c: Ctx, b: dict) -> dict:
    uit = []
    for r in c.x.run('Get-TransportRule', ResultSize='Unlimited'):
        uit.append({'id': _s(r.get('Guid') or r.get('Identity')), 'name': _s(r.get('Name')), 'state': _s(r.get('State')),
                    'priority': r.get('Priority'), 'mode': _s(r.get('Mode')), 'desc': _s(r.get('Description')),
                    'comments': _s(r.get('Comments')), 'modified': _s(r.get('WhenChanged'))})
    uit.sort(key=lambda r: (r['priority'] if isinstance(r['priority'], int) else 999))
    return {'rules': uit}


# Eenvoudige voorwaarden en acties die vaak nodig zijn (vrij uit te breiden)
VOORWAARDEN = {'from': ('From', True), 'sentTo': ('SentTo', True), 'subjectContains': ('SubjectContainsWords', True),
               'subjectOrBodyContains': ('SubjectOrBodyContainsWords', True), 'senderDomain': ('SenderDomainIs', True),
               'recipientDomain': ('RecipientDomainIs', True), 'fromScope': ('FromScope', False), 'sentToScope': ('SentToScope', False),
               'attachmentExt': ('AttachmentExtensionMatchesWords', True)}
ACTIES = {'redirectTo': ('RedirectMessageTo', True), 'bccTo': ('BlindCopyTo', True), 'addTo': ('AddToRecipients', True),
          'prependSubject': ('PrependSubject', False), 'setScl': ('SetSCL', False), 'reject': ('RejectMessageReasonText', False),
          'moderateBy': ('ModerateMessageByUser', True), 'setHeaderName': ('SetHeaderName', False), 'setHeaderValue': ('SetHeaderValue', False)}


@api('rules.create')
def rules_create(c: Ctx, b: dict) -> dict:
    if not str(b.get('name') or '').strip():
        raise ApiFout('Geef de regel een naam.')
    p: dict = {'Name': b['name'].strip(), 'Enabled': bool(b.get('enabled', True)), 'Mode': b.get('mode') or 'Enforce'}
    for sleutel, (param, lijst) in {**VOORWAARDEN, **ACTIES}.items():
        v = b.get(sleutel)
        if v in (None, '', []):
            continue
        p[param] = _lijst(v) if lijst else (int(v) if param == 'SetSCL' else str(v))
    if b.get('disclaimer'):
        p.update(ApplyHtmlDisclaimerText=str(b['disclaimer']), ApplyHtmlDisclaimerLocation=b.get('disclaimerLocation') or 'Append',
                 ApplyHtmlDisclaimerFallbackAction=b.get('disclaimerFallback') or 'Wrap')
    if b.get('delete'):
        p['DeleteMessage'] = True
    if b.get('stop'):
        p['StopRuleProcessing'] = True
    if b.get('priority') not in (None, ''):
        p['Priority'] = int(b['priority'])
    if b.get('comments'):
        p['Comments'] = str(b['comments'])
    if not any(k in p for k in (*[v[0] for v in ACTIES.values()], 'ApplyHtmlDisclaimerText', 'DeleteMessage')):
        raise ApiFout('Kies minimaal één actie.')
    c.x.run('New-TransportRule', **p)
    c.L(f"Regel '{p['Name']}' aangemaakt.")
    return {}


@api('rules.set')
def rules_set(c: Ctx, b: dict) -> dict:
    rid = b['id']
    if 'enabled' in b:
        c.x.run('Enable-TransportRule' if b['enabled'] else 'Disable-TransportRule', Identity=rid)
        c.L(f"Regel {'ingeschakeld' if b['enabled'] else 'uitgeschakeld'}.")
    if b.get('priority') not in (None, ''):
        c.x.run('Set-TransportRule', Identity=rid, Priority=int(b['priority']))
        c.L(f"Prioriteit gewijzigd naar {b['priority']}.")
    return {}


@api('rules.delete')
def rules_delete(c: Ctx, b: dict) -> dict:
    for rid in b.get('ids') or [b.get('id')]:
        try:
            c.x.run('Remove-TransportRule', Identity=rid)
            c.L(f'Regel verwijderd: {rid}')
        except ApiFout as e:
            c.L(f'FOUT {rid}: {e}')
    return {}


# ---------------- Connectors ----------------
@api('connectors.list')
def connectors_list(c: Ctx, b: dict) -> dict:
    uit = []
    for soort, cmd in (('Inkomend', 'Get-InboundConnector'), ('Uitgaand', 'Get-OutboundConnector')):
        for r in c.x.run(cmd):
            uit.append({'id': _s(r.get('Guid') or r.get('Identity')), 'name': _s(r.get('Name')), 'dir': soort,
                        'enabled': bool(r.get('Enabled')), 'type': _s(r.get('ConnectorType')), 'comment': _s(r.get('Comment')),
                        'domains': _s(r.get('SenderDomains') if soort == 'Inkomend' else r.get('RecipientDomains')),
                        'ips': _s(r.get('SenderIPAddresses')), 'smarthosts': _s(r.get('SmartHosts')),
                        'tls': _s(r.get('RequireTls') if soort == 'Inkomend' else r.get('TlsSettings')),
                        'useMx': bool(r.get('UseMXRecord'))})
    return {'connectors': uit}


@api('connectors.create')
def connectors_create(c: Ctx, b: dict) -> dict:
    naam = str(b.get('name') or '').strip()
    if not naam:
        raise ApiFout('Geef de connector een naam.')
    if b.get('dir') == 'Uitgaand':
        p = {'Name': naam, 'ConnectorType': b.get('type') or 'Partner', 'Enabled': bool(b.get('enabled', True)),
             'RecipientDomains': _lijst(b.get('domains')) or None, 'Comment': b.get('comment') or None}
        hosts = _lijst(b.get('smarthosts'))
        if hosts:
            p.update(SmartHosts=hosts, UseMXRecord=False)
        else:
            p['UseMXRecord'] = True
        if b.get('tls'):
            p['TlsSettings'] = b['tls']
        c.x.run('New-OutboundConnector', **p)
    else:
        p = {'Name': naam, 'ConnectorType': b.get('type') or 'Partner', 'Enabled': bool(b.get('enabled', True)),
             'SenderDomains': _lijst(b.get('domains')) or ['*'], 'Comment': b.get('comment') or None,
             'RequireTls': bool(b.get('requireTls'))}
        ips = _lijst(b.get('ips'))
        if ips:
            p.update(SenderIPAddresses=ips, RestrictDomainsToIPAddresses=bool(b.get('restrictIps')))
        c.x.run('New-InboundConnector', **p)
    c.L(f"Connector '{naam}' aangemaakt.")
    return {}


@api('connectors.set')
def connectors_set(c: Ctx, b: dict) -> dict:
    cmd = 'Set-OutboundConnector' if b.get('dir') == 'Uitgaand' else 'Set-InboundConnector'
    c.x.run(cmd, Identity=b['id'], Enabled=bool(b.get('enabled')))
    c.L(f"Connector {'ingeschakeld' if b.get('enabled') else 'uitgeschakeld'}.")
    return {}


@api('connectors.delete')
def connectors_delete(c: Ctx, b: dict) -> dict:
    cmd = 'Remove-OutboundConnector' if b.get('dir') == 'Uitgaand' else 'Remove-InboundConnector'
    c.x.run(cmd, Identity=b['id'])
    c.L('Connector verwijderd.')
    return {}
