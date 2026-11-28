"""Migratie naar Exchange Online: IMAP, Google Workspace, Exchange on-premises (hybride) en cutover.

Precies dezelfde cmdlets als in PowerShell (via de Exchange-REST-API van de app):
Get/New/Remove-MigrationEndpoint, Test-MigrationServerAvailability, Get/New/Start/Stop/Complete/Remove/Set-MigrationBatch,
Get-MigrationUser en Get-MigrationUserStatistics.

Wachtwoorden (IMAP-gebruikers, beheeraccount on-premises) en het Google-sleutelbestand gaan alleen door het geheugen
naar Microsoft en worden nergens bewaard of gelogd. Vereist bij de klant de rol Exchange Administrator.
"""
from __future__ import annotations

import base64
import csv
import io
import logging

from .clients import ApiFout, parallel
from .context import Ctx, api

log = logging.getLogger('m365beheer')

SOORTEN = {
    'imap': 'IMAP',
    'gmail': 'Google Workspace',
    'remote': 'Exchange on-premises (hybride)',
    'cutover': 'Exchange on-premises (cutover)',
}
TYPE_NAAR_SOORT = {'IMAP': 'imap', 'Gmail': 'gmail', 'ExchangeRemoteMove': 'remote', 'ExchangeOutlookAnywhere': 'cutover'}


def _s(v) -> str:
    if v is None:
        return ''
    if isinstance(v, dict):   # Exchange geeft soms objecten met een tekstweergave
        return str(v.get('Name') or v.get('Value') or v.get('DisplayName') or '')
    return str(v)


def _int(v) -> int:
    try:
        return int(str(v).split(' ')[0].replace(',', '').replace('.', ''))
    except (TypeError, ValueError):
        return 0


def _datum(v) -> str:
    s = _s(v)
    return '' if s.startswith('0001') else s


def _bytes_varianten(data: bytes) -> list:
    """Bytes (CSV, sleutelbestand) zoals PowerShell ze verstuurt (een reeks getallen); anders als base64-tekst."""
    return [list(data), base64.b64encode(data).decode()]


def _cred_varianten(gebruiker: str, wachtwoord: str) -> list:
    return [{'@odata.type': '#Exchange.PSCredential', 'UserName': gebruiker, 'Password': wachtwoord},
            {'UserName': gebruiker, 'Password': wachtwoord}]


def _run_met(c: Ctx, cmdlet: str, varianten: dict[str, list], **vast):
    """Cmdlet uitvoeren; bij een parameter die Exchange niet kan omzetten de volgende schrijfwijze proberen."""
    namen = list(varianten)
    keuze = [0] * len(namen)
    laatste: Exception | None = None
    for _ in range(4):
        p = dict(vast)
        for i, n in enumerate(namen):
            p[n] = varianten[n][keuze[i]]
        try:
            return c.x.run(cmdlet, **p)
        except ApiFout as e:
            laatste = e
            t = str(e).lower()
            if not any(w in t for w in ('cannot convert', 'cannot bind', 'deserializ', 'invalid cast', 'converteren', 'binden')):
                raise
            # volgende schrijfwijze voor de eerste parameter die nog een alternatief heeft
            for i, n in enumerate(namen):
                if keuze[i] + 1 < len(varianten[n]):
                    keuze[i] += 1
                    break
            else:
                raise
    raise laatste or ApiFout(f'{cmdlet} is niet gelukt.')


# ---------------- Verbindingen (migration endpoints) ----------------
def _endpoint(e: dict) -> dict:
    t = _s(e.get('EndpointType'))
    return {'id': _s(e.get('Identity')), 'type': TYPE_NAAR_SOORT.get(t, t), 'typeText': SOORTEN.get(TYPE_NAAR_SOORT.get(t, ''), t),
            'server': _s(e.get('RemoteServer') or e.get('ExchangeServer') or e.get('RpcProxyServer')),
            'port': _s(e.get('Port')), 'security': _s(e.get('Security')), 'max': _s(e.get('MaxConcurrentMigrations')),
            'account': _s(e.get('Username') or e.get('EmailAddress'))}


@api('mig.endpoints')
def mig_endpoints(c: Ctx, b: dict) -> dict:
    return {'endpoints': [_endpoint(e) for e in c.x.run('Get-MigrationEndpoint')]}


def _endpoint_params(b: dict) -> tuple[dict, dict]:
    """Parameters voor New-MigrationEndpoint / Test-MigrationServerAvailability per soort: (vast, varianten)."""
    soort = b.get('type')
    if soort == 'imap':
        return {'IMAP': True, 'RemoteServer': str(b['server']).strip(), 'Port': int(b.get('port') or 993),
                'Security': b.get('security') or 'Ssl'}, {}
    if soort == 'gmail':
        sleutel = str(b.get('keyFile') or '')
        if not sleutel.strip().startswith('{'):
            raise ApiFout('Kies het JSON-sleutelbestand van het Google-serviceaccount.')
        return {'Gmail': True, 'EmailAddress': str(b['admin']).strip()}, {'ServiceAccountKeyFileData': _bytes_varianten(sleutel.encode('utf-8'))}
    if soort == 'remote':
        return ({'ExchangeRemoteMove': True, 'RemoteServer': str(b['server']).strip()},
                {'Credentials': _cred_varianten(str(b['user']).strip(), str(b['password']))})
    if soort == 'cutover':
        vast = {'ExchangeOutlookAnywhere': True, 'EmailAddress': str(b['admin']).strip()}
        if b.get('server'):
            vast.update(ExchangeServer=str(b['server']).strip(), RpcProxyServer=str(b.get('proxy') or b['server']).strip())
        else:
            vast['Autodiscover'] = True
        return vast, {'Credentials': _cred_varianten(str(b['user']).strip(), str(b['password']))}
    raise ApiFout('Onbekende soort migratie.')


@api('mig.endpoint.test')
def mig_endpoint_test(c: Ctx, b: dict) -> dict:
    """Verbinding testen (Test-MigrationServerAvailability), zonder iets aan te maken."""
    vast, var = _endpoint_params(b)
    r = _run_met(c, 'Test-MigrationServerAvailability', var, **vast) if var else c.x.run('Test-MigrationServerAvailability', **vast)
    res = (r or [{}])[0]
    gelukt = _s(res.get('Result')).lower() == 'success'
    melding = _s(res.get('Message') or res.get('ErrorDetail'))
    c.L(('Verbinding gelukt.' if gelukt else f'FOUT Verbinding niet gelukt: {melding or "onbekende fout"}'))
    return {'ok': gelukt, 'message': melding, 'server': _s(res.get('ConnectionSettings'))}


@api('mig.endpoint.new')
def mig_endpoint_new(c: Ctx, b: dict) -> dict:
    naam = str(b.get('name') or '').strip()
    if not naam:
        raise ApiFout('Geef de verbinding een naam.')
    vast, var = _endpoint_params(b)
    vast['Name'] = naam
    if b.get('max'):
        vast['MaxConcurrentMigrations'] = int(b['max'])
    r = _run_met(c, 'New-MigrationEndpoint', var, **vast) if var else c.x.run('New-MigrationEndpoint', **vast)
    c.L(f'Verbinding {naam} aangemaakt.')
    return {'endpoint': _endpoint((r or [{}])[0]) if r else {'id': naam}}


@api('mig.endpoint.remove')
def mig_endpoint_remove(c: Ctx, b: dict) -> dict:
    c.x.run('Remove-MigrationEndpoint', Identity=str(b['id']), Confirm=False)
    c.L(f"Verbinding {b['id']} verwijderd.")
    return {}


# ---------------- Batches ----------------
def _batch(m: dict) -> dict:
    t = _s(m.get('MigrationType'))
    return {'id': _s(m.get('Identity')), 'status': _s(m.get('Status')), 'type': TYPE_NAAR_SOORT.get(t, t.lower()),
            'typeText': SOORTEN.get(TYPE_NAAR_SOORT.get(t, ''), t), 'total': _int(m.get('TotalCount')), 'active': _int(m.get('ActiveCount')),
            'synced': _int(m.get('SyncedCount')), 'finalized': _int(m.get('FinalizedCount')), 'failed': _int(m.get('FailedCount')),
            'stopped': _int(m.get('StoppedCount')), 'pending': _int(m.get('PendingCount')),
            'created': _datum(m.get('CreationDateTime')), 'started': _datum(m.get('StartDateTime')),
            'lastSync': _datum(m.get('LastSyncedDateTime')), 'completeAfter': _datum(m.get('CompleteAfter')),
            'endpoint': _s(m.get('SourceEndpoint')), 'domain': _s(m.get('TargetDeliveryDomain')),
            'notify': _s(m.get('NotificationEmails')), 'message': _s(m.get('Message'))}


@api('mig.batches')
def mig_batches(c: Ctx, b: dict) -> dict:
    l = [_batch(m) for m in c.x.run('Get-MigrationBatch')]
    l.sort(key=lambda x: x['created'], reverse=True)
    return {'batches': l}


@api('mig.users')
def mig_users(c: Ctx, b: dict) -> dict:
    """Gebruikers van een batch met voortgang (Get-MigrationUser + Get-MigrationUserStatistics per gebruiker)."""
    gebruikers = c.x.run('Get-MigrationUser', BatchId=str(b['id']), ResultSize='Unlimited')
    x = c.x

    def stats(mail: str) -> dict:
        r = x.run('Get-MigrationUserStatistics', Identity=mail)
        return (r or [{}])[0]
    st = parallel({_s(u.get('Identity')): (lambda m=_s(u.get('Identity')): stats(m)) for u in gebruikers[:300]})
    uit = []
    for u in gebruikers:
        mail = _s(u.get('Identity'))
        s = st.get(mail)
        s = s if isinstance(s, dict) else {}
        uit.append({'mail': mail, 'status': _s(u.get('Status')), 'detail': _s(s.get('StatusDetail') or u.get('StatusDetail')),
                    'synced': _int(s.get('SyncedItemCount')), 'skipped': _int(s.get('SkippedItemCount')),
                    'total': _int(s.get('TotalItemsInSourceMailboxCount')), 'size': _s(s.get('BytesTransferred') or s.get('EstimatedTotalTransferSize')),
                    'percent': _int(s.get('PercentageComplete')), 'lastSync': _datum(u.get('LastSuccessfulSyncTime') or s.get('LastSuccessfulSyncTime')),
                    'error': _s(s.get('Error') or u.get('ErrorSummary'))[:500]})
    return {'users': uit}


def _csv(soort: str, rijen: list[dict]) -> bytes:
    """CSV zoals Microsoft hem verwacht. IMAP: EmailAddress,UserName,Password; anders: EmailAddress."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\r\n')
    if soort == 'imap':
        w.writerow(['EmailAddress', 'UserName', 'Password'])
        for r in rijen:
            w.writerow([r['mail'].strip(), (r.get('user') or r['mail']).strip(), r.get('password') or ''])
    else:
        w.writerow(['EmailAddress'])
        for r in rijen:
            w.writerow([r['mail'].strip()])
    return buf.getvalue().encode('utf-8')


@api('mig.check')
def mig_check(c: Ctx, b: dict) -> dict:
    """Controle vooraf: bestaan de doelpostvakken in Microsoft 365 (IMAP/Google) of de e-mailgebruikers (hybride)?"""
    adressen = [str(r.get('mail') or '').strip().lower() for r in b.get('rows') or [] if str(r.get('mail') or '').strip()]
    soort = b.get('type')
    bekend: dict[str, str] = {}
    for r in c.x.run('Get-Recipient', ResultSize='Unlimited', RecipientTypeDetails=['UserMailbox', 'SharedMailbox', 'MailUser']):
        soort_ontv = _s(r.get('RecipientTypeDetails'))
        for a in r.get('EmailAddresses') or []:
            a = str(a)
            if a.lower().startswith('smtp:'):
                bekend[a[5:].lower()] = soort_ontv
    uit = []
    for a in adressen:
        t = bekend.get(a, '')
        if soort in ('imap', 'gmail'):
            ok = t in ('UserMailbox', 'SharedMailbox')
            uitleg = '' if ok else ('Is een e-mailgebruiker, geen postvak' if t else 'Geen postvak met dit adres in Microsoft 365 (eerst aanmaken en licentie geven)')
        elif soort == 'remote':
            ok = t == 'MailUser'
            uitleg = '' if ok else ('Heeft al een postvak in Microsoft 365' if t else 'Geen e-mailgebruiker gevonden (synchroniseer eerst met Entra Connect)')
        else:
            ok, uitleg = True, ''
        uit.append({'mail': a, 'ok': ok, 'type': t, 'reason': uitleg})
    return {'rows': uit}


@api('mig.batch.new')
def mig_batch_new(c: Ctx, b: dict) -> dict:
    naam = str(b.get('name') or '').strip()
    soort = b.get('type')
    if not naam:
        raise ApiFout('Geef de migratie een naam.')
    vast: dict = {'Name': naam, 'AutoStart': bool(b.get('autoStart')), 'AutoComplete': bool(b.get('autoComplete'))}
    if b.get('endpoint'):
        vast['SourceEndpoint'] = str(b['endpoint'])
    if b.get('notify'):
        vast['NotificationEmails'] = [x.strip() for x in str(b['notify']).replace(';', ',').split(',') if x.strip()]
    if soort in ('gmail', 'remote'):
        if not b.get('domain'):
            raise ApiFout('Kies het doeldomein (meestal <tenant>.mail.onmicrosoft.com).')
        vast['TargetDeliveryDomain'] = str(b['domain'])
    if soort == 'imap' and b.get('exclude'):
        vast['ExcludeFolders'] = [x.strip() for x in str(b['exclude']).split(',') if x.strip()]
    if soort == 'remote' and b.get('badItems'):
        vast['BadItemLimit'] = int(b['badItems'])
    var = {}
    if soort != 'cutover':
        rijen = [r for r in b.get('rows') or [] if str(r.get('mail') or '').strip()]
        if not rijen:
            raise ApiFout('Voeg minimaal één gebruiker toe.')
        if soort == 'imap' and any(not r.get('password') for r in rijen):
            raise ApiFout('Vul voor elke IMAP-gebruiker het wachtwoord van het oude postvak in.')
        var['CSVData'] = _bytes_varianten(_csv(soort, rijen))
    r = _run_met(c, 'New-MigrationBatch', var, **vast) if var else c.x.run('New-MigrationBatch', **vast)
    c.L(f"Migratie {naam} aangemaakt{' en gestart' if vast['AutoStart'] else ''}.")
    return {'batch': _batch((r or [{}])[0]) if r else {'id': naam}}


@api('mig.batch.action')
def mig_batch_action(c: Ctx, b: dict) -> dict:
    """Starten / hervatten, stoppen, voltooien (laatste synchronisatie en omzetten) of verwijderen."""
    acties = {'start': ('Start-MigrationBatch', 'gestart'), 'stop': ('Stop-MigrationBatch', 'gestopt'),
              'complete': ('Complete-MigrationBatch', 'wordt voltooid'), 'remove': ('Remove-MigrationBatch', 'verwijderd')}
    if b.get('action') not in acties:
        raise ApiFout('Onbekende actie.')
    cmd, tekst = acties[b['action']]
    p = {'Identity': str(b['id']), 'Confirm': False}
    c.x.run(cmd, **p)
    c.L(f"Migratie {b['id']} {tekst}.")
    return {}


@api('mig.batch.set')
def mig_batch_set(c: Ctx, b: dict) -> dict:
    """Instellingen wijzigen: automatisch voltooien op een tijdstip, meldingsadressen."""
    p: dict = {'Identity': str(b['id'])}
    if 'completeAfter' in b:
        p['CompleteAfter'] = b['completeAfter'] or None
    if 'notify' in b:
        p['NotificationEmails'] = [x.strip() for x in str(b['notify'] or '').replace(';', ',').split(',') if x.strip()]
    c.x.run('Set-MigrationBatch', **{k: v for k, v in p.items() if v is not None})
    c.L(f"Migratie {b['id']} bijgewerkt.")
    return {}


@api('mig.domains')
def mig_domains(c: Ctx, b: dict) -> dict:
    """Mogelijke doeldomeinen (Google/hybride): bij voorkeur <tenant>.mail.onmicrosoft.com."""
    doms = [str(d.get('DomainName') or d.get('Name')) for d in c.x.run('Get-AcceptedDomain')]
    doms.sort(key=lambda d: (not d.endswith('.mail.onmicrosoft.com'), not d.endswith('.onmicrosoft.com'), d))
    return {'domains': doms}
