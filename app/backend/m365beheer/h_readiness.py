"""Readiness-controles met score: Copilot-readiness en NEN 7510 (informatiebeveiliging in de zorg).

Eén set metingen (feiten) wordt per klant opgehaald en gedeeld door beide profielen. Elke controle geeft een status
(ok / warn / err / unknown), een toelichting en zo mogelijk een directe actie met de negatieve impact. NEN 7510-onderdelen
die niet technisch te meten zijn (beleid, procedures) staan als handmatige punten in het overzicht en tellen niet mee in de score.

Verwijzingen bij NEN 7510 gaan naar de beheersmaatregelen van NEN 7510-2:2024 (zelfde nummering als ISO/IEC 27002:2022).
"""
from __future__ import annotations

import re
from html import escape

from . import common as C
from . import h_compliance as HC
from .clients import ApiFout, parallel
from .context import Ctx, api, VERS
from .h_domeinen import _dns

BETA = 'https://graph.microsoft.com/beta'
BASIS_SKUS = ('SPB', 'O365_BUSINESS_PREMIUM', 'O365_BUSINESS_ESSENTIALS', 'SMB_BUSINESS_PREMIUM', 'SPE_E3', 'SPE_E5', 'ENTERPRISEPACK',
              'ENTERPRISEPREMIUM', 'O365_BUSINESS', 'SPE_F1', 'M365_F1', 'Microsoft_365_E3', 'Microsoft_365_E5', 'O365_w/o_Teams_Bundle_M3',
              'O365_w/o_Teams_Bundle_M5', 'Microsoft_365_Business_Standard', 'Microsoft_365_Business_Premium', 'STANDARDPACK')
GOED = {'ok': 1.0, 'warn': 0.5, 'err': 0.0}


# =====================================================================================================
# Feiten ophalen (alles tegelijk, per onderdeel mag iets mislukken)
# =====================================================================================================

def _sp_tenant(c: Ctx) -> dict:
    from .h_sharepoint import _sp
    velden = 'SharingCapability,DefaultSharingLinkType,DefaultLinkPermission,OneDriveSharingCapability,RequireAnonymousLinksExpireInDays'
    try:
        return _sp(c, 'GET', f'/_api/SPO.Tenant?$select={velden}').json()
    except ApiFout:
        return _sp(c, 'GET', '/_api/SPO.Tenant').json()


def _exo(c: Ctx) -> dict:
    if not c.exo_ok:
        raise ApiFout('Exchange niet verbonden')
    x = c.x
    r = parallel({
        'audit': lambda: x.een('Get-AdminAuditLogConfig') or {},
        'org': lambda: x.een('Get-OrganizationConfig') or {},
        'ext': lambda: x.run('Get-ExternalInOutlook'),
        'out': lambda: x.een('Get-HostedOutboundSpamFilterPolicy', Identity='Default') or {},
        'mal': lambda: x.een('Get-MalwareFilterPolicy', Identity='Default') or {},
        'dkim': lambda: x.run('Get-DkimSigningConfig'),
        'dom': lambda: x.run('Get-AcceptedDomain'),
    })
    return {k: (None if isinstance(v, Exception) else v) for k, v in r.items()}


def _mail_dns(domeinen: list[str]) -> dict:
    taken = {}
    for d in domeinen:
        taken[d + '|spf'] = (lambda d=d: [x for x in _dns(d, 'TXT') if x.lower().startswith('v=spf1') or x == '?'])
        taken[d + '|dmarc'] = (lambda d=d: [x for x in _dns('_dmarc.' + d, 'TXT') if x.lower().startswith('v=dmarc1') or x == '?'])
    r = parallel(taken) if taken else {}
    return {d: {'spf': r.get(d + '|spf') if isinstance(r.get(d + '|spf'), list) else ['?'],
                'dmarc': r.get(d + '|dmarc') if isinstance(r.get(d + '|dmarc'), list) else ['?']} for d in domeinen}


def _feiten(c: Ctx) -> dict:
    t, g = c.t, c.g
    mail_domeinen = [d['id'] for d in t.domeinen if not d['id'].lower().endswith('.onmicrosoft.com')]
    taken = {
        'users': lambda: t.cache('compliance-gebruikers', lambda: HC._gebruikers(c), VERS),
        'devices': lambda: t.cache('compliance-apparaten', lambda: HC._apparaten(c), VERS),
        'sp': lambda: _sp_tenant(c),
        'groups': lambda: g.all("/groups?$filter=groupTypes/any(x:x eq 'Unified')&$select=id,displayName,visibility,resourceProvisioningOptions&$top=999"),
        'skus': lambda: C.licenties(c),
        'labels': lambda: g.get(BETA + '/security/informationProtection/sensitivityLabels').get('value', []),
        'cpol': lambda: g.all('/deviceManagement/deviceCompliancePolicies?$select=id,displayName'),
        'exo': lambda: _exo(c),
        'mail': lambda: _mail_dns(mail_domeinen),
        'auth': lambda: g.get('/policies/authorizationPolicy'),
    }
    # Eigen threads (niet de gedeelde POOL): de onderdelen gebruiken zelf ook parallel(), zo blijft het maximaal 2 niveaus diep
    from concurrent.futures import ThreadPoolExecutor

    def veilig(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            return e
    with ThreadPoolExecutor(max_workers=len(taken)) as ex:
        r = dict(zip(taken, ex.map(veilig, taken.values())))
    return {k: (None if isinstance(v, Exception) else v) for k, v in r.items()} | {'_fout': {k: str(v)[:200] for k, v in r.items() if isinstance(v, Exception)}}


# =====================================================================================================
# Directe acties (met wat er verandert en de negatieve impact)
# =====================================================================================================

def _sp_zet(c: Ctx, **waarden: int) -> None:
    """Tenantinstellingen van SharePoint wijzigen (zoals Set-SPOTenant), via de CSOM-beheer-API."""
    from .h_sharepoint import TENANT_TYPE, _sp
    acties = ''.join(f'<SetProperty Id="{10 + i}" ObjectPathId="1" Name="{k}"><Parameter Type="Enum">{int(v)}</Parameter></SetProperty>'
                     for i, (k, v) in enumerate(waarden.items()))
    xml = (f'<Request AddExpandoFieldTypeSuffix="true" SchemaVersion="15.0.0.0" LibraryVersion="16.0.0.0" ApplicationName="M365Beheer" '
           f'xmlns="http://schemas.microsoft.com/sharepoint/clientquery/2009"><Actions><ObjectPath Id="2" ObjectPathId="1" />{acties}'
           f'<Method Name="Update" Id="9" ObjectPathId="1" /></Actions><ObjectPaths><Constructor Id="1" TypeId="{TENANT_TYPE}" /></ObjectPaths></Request>')
    r = _sp(c, 'POST', '/_vti_bin/client.svc/ProcessQuery', data=xml.encode('utf-8'), ctype='text/xml')
    try:
        j = r.json()
        fout = (j[0] or {}).get('ErrorInfo') if isinstance(j, list) and j else None
    except ValueError:
        fout = None
    if fout:
        raise ApiFout('SharePoint: ' + escape(str(fout.get('ErrorMessage') or fout))[:300])


def _dkim_aan(c: Ctx) -> None:
    x = c.x
    bestaand = {str(k.get('Domain') or k.get('Name')).lower(): k for k in x.run('Get-DkimSigningConfig')}
    fouten = []
    for d in x.run('Get-AcceptedDomain'):
        naam = str(d.get('DomainName') or d.get('Name'))
        if naam.lower().endswith('.onmicrosoft.com'):
            continue
        k = bestaand.get(naam.lower())
        if k and k.get('Enabled'):
            continue
        try:
            if not k:
                x.run('New-DkimSigningConfig', DomainName=naam, Enabled=False, KeySize=2048)
            x.run('Set-DkimSigningConfig', Identity=naam, Enabled=True)
        except ApiFout as e:
            fouten.append(f"{naam}: {'CNAME-records ontbreken in de DNS (zie Bedreigingsbeheer > DKIM)' if 'cname' in str(e).lower() else str(e)[:120]}")
    if fouten:
        raise ApiFout('DKIM kon niet overal aan. ' + '; '.join(fouten))


def _openbaar_prive(c: Ctx) -> None:
    groepen = c.g.all("/groups?$filter=groupTypes/any(x:x eq 'Unified')&$select=id,displayName,visibility&$top=999")
    for gr in groepen:
        if str(gr.get('visibility') or '').lower() == 'public':
            c.g.patch(f"/groups/{gr['id']}", {'visibility': 'Private'})
            c.L(f"Groep/team '{gr.get('displayName')}' is nu privé.")


def _apps_maken_uit(c: Ctx) -> None:
    c.g.patch('/policies/authorizationPolicy', {'defaultUserRolePermissions': {'allowedToCreateApps': False}})


OPL = HC.OPLOSSINGEN
FIXES: dict[str, dict] = {
    'ual': {'what': 'Unified Audit Log aanzetten (Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled $true).',
            'impact': 'Geen merkbaar effect voor gebruikers. Het kan tot 60 minuten duren voordat de auditlog gevuld wordt.',
            'fn': lambda c: c.x.run('Set-AdminAuditLogConfig', UnifiedAuditLogIngestionEnabled=True)},
    'mailboxaudit': {'what': OPL['exo_mailboxaudit']['wat'], 'impact': OPL['exo_mailboxaudit']['nadeel'], 'fn': OPL['exo_mailboxaudit']['fn']},
    'autoforward': {'what': OPL['mdo_autoforwardingmode']['wat'], 'impact': OPL['mdo_autoforwardingmode']['nadeel'], 'fn': OPL['mdo_autoforwardingmode']['fn']},
    'attachments': {'what': OPL['mdo_commonattachmentsfilter']['wat'], 'impact': OPL['mdo_commonattachmentsfilter']['nadeel'], 'fn': OPL['mdo_commonattachmentsfilter']['fn']},
    'consent': {'what': OPL['integratedapps']['wat'], 'impact': OPL['integratedapps']['nadeel'], 'fn': OPL['integratedapps']['fn']},
    'externaltag': {'what': 'Externe afzenders markeren in Outlook (Set-ExternalInOutlook -Enabled $true): berichten van buiten krijgen het label "Extern".',
                    'impact': 'Gebruikers zien bij externe mail een label "Extern"; verder geen effect. Het kan tot 48 uur duren voordat het overal zichtbaar is.',
                    'fn': lambda c: c.x.run('Set-ExternalInOutlook', Enabled=True)},
    'dkim': {'what': 'DKIM-ondertekening aanzetten voor alle eigen domeinen (wordt zo nodig eerst aangemaakt).',
             'impact': 'Geen effect voor gebruikers. Lukt alleen als de twee DKIM-CNAME-records in de DNS staan; anders meldt de app welke domeinen nog records nodig hebben.',
             'fn': _dkim_aan},
    'sp_sharing': {'what': 'Delen met "Iedereen" (anonieme links) uitzetten voor SharePoint: alleen nog delen met nieuwe en bestaande gasten die zich aanmelden.',
                   'impact': 'Bestaande "Iedereen"-links werken direct niet meer. Externen die zo\'n link gebruikten, moeten opnieuw worden uitgenodigd (met aanmelden). '
                             'Delen met gasten blijft mogelijk.',
                   'fn': lambda c: _sp_zet(c, SharingCapability=1)},
    'od_sharing': {'what': 'Delen met "Iedereen" (anonieme links) uitzetten voor OneDrive.',
                   'impact': 'Bestaande anonieme OneDrive-links werken niet meer; delen met gasten (met aanmelden) blijft mogelijk.',
                   'fn': lambda c: _sp_zet(c, OneDriveSharingCapability=1)},
    'sp_linktype': {'what': 'Standaard deellink wordt "Specifieke personen" met alleen-lezen (in plaats van iedereen in de organisatie / bewerken).',
                    'impact': 'Gebruikers moeten bij delen zelf kiezen als ze een bredere link of bewerkrechten willen. Bestaande links veranderen niet.',
                    'fn': lambda c: _sp_zet(c, DefaultSharingLinkType=1, DefaultLinkPermission=1)},
    'public_groups': {'what': 'Alle openbare Microsoft 365-groepen en Teams privé maken.',
                      'impact': 'Collega\'s die geen lid zijn, kunnen deze teams niet meer vinden of zelf lid worden; de eigenaar moet ze toevoegen. '
                                'Leden merken niets. Copilot toont de inhoud daarna alleen nog aan leden.',
                      'fn': _openbaar_prive},
    'apps_create': {'what': 'Gebruikers mogen geen app-registraties meer maken in Entra ID.',
                    'impact': 'Vrijwel geen: alleen beheerders (Application Developer of hoger) kunnen nog apps registreren.',
                    'fn': _apps_maken_uit},
}


# =====================================================================================================
# Controles
# =====================================================================================================
# Elke controle: fn(f) -> (status, tekst[, details]) met status ok/warn/err/unknown.

def _u(f):
    return f['users'] or {}


def _chk(u, key):
    return next((x for x in u.get('checks', []) if x['key'] == key), None)


def c_mfa_reg(f):
    u = _u(f)
    if not u:
        return 'unknown', 'Gebruikers konden niet worden gelezen.'
    k = u['counts']
    if not k['none']:
        return 'ok', f"Alle {k['active']} actieve gebruikers hebben MFA geregistreerd."
    return ('err' if k['adminsNone'] or k['none'] / max(k['active'], 1) > .1 else 'warn'), \
        f"{k['none']} van {k['active']} actieve gebruikers zonder MFA" + (f", waarvan {k['adminsNone']} beheerder(s)." if k['adminsNone'] else '.'), \
        [x['name'] for x in u['users'] if x['mfa'] == 'none'][:30]


def c_mfa_enf(f):
    c = _chk(_u(f), 'enforce')
    return (c['status'], c['text']) if c else ('unknown', 'Onbekend.')


def c_legacy(f):
    c = _chk(_u(f), 'legacy')
    return (c['status'], c['text']) if c else ('unknown', 'Onbekend.')


def c_admins_mfa(f):
    u = _u(f)
    if not u:
        return 'unknown', 'Onbekend.'
    zonder = [a for a in u['admins'] if a['mfa'] in ('none', 'weak')]
    if not zonder:
        return 'ok', f"Alle {len(u['admins'])} beheerders hebben een sterke MFA-methode."
    return 'err', f'{len(zonder)} beheerder(s) zonder sterke MFA (geen of alleen sms).', [a['name'] for a in zonder]


def c_ga(f):
    c = _chk(_u(f), 'ga')
    return (c['status'], c['text']) if c else ('unknown', 'Onbekend.')


def c_breakglass(f):
    u = _u(f)
    if not u:
        return 'unknown', 'Onbekend.'
    nood = [a for a in u['admins'] if a['ga'] and re.search(r'break|glass|nood|emergency|bg[-_.]?admin', (a['name'] + a['upn']).lower())]
    if nood:
        return 'ok', f"Noodaccount(s) gevonden: {', '.join(a['upn'] for a in nood)}. Controleer dat ze buiten Conditional Access vallen en een sterke FIDO2-sleutel hebben."
    return 'warn', 'Geen herkenbaar noodaccount (break-glass) gevonden. Advies: twee cloud-only Global Administrator-accounts, uitgezonderd van CA, met FIDO2 en bewaakt.'


def c_admin_apart(f):
    u = _u(f)
    if not u:
        return 'unknown', 'Onbekend.'
    dagelijks = [x for x in u['users'] if x['roles'] and x['licensed'] and x['mfa'] not in ('disabled', 'shared')]
    if not dagelijks:
        return 'ok', 'Beheerdersrollen zitten op aparte accounts zonder licentie.'
    return 'warn', f'{len(dagelijks)} account(s) met een beheerdersrol worden ook dagelijks gebruikt (hebben een licentie). Advies: aparte beheeraccounts.', \
        [f"{x['name']} ({', '.join(x['roles'])})" for x in dagelijks][:20]


def c_consent(f):
    c = _chk(_u(f), 'consent')
    return (c['status'], c['text']) if c else ('unknown', 'Onbekend.')


def c_apps(f):
    c = _chk(_u(f), 'apps')
    return (c['status'], c['text']) if c else ('unknown', 'Onbekend.')


def c_gasten(f):
    c = _chk(_u(f), 'guests')
    return (c['status'], c['text']) if c else ('unknown', 'Onbekend.')


def c_inactief(f):
    u = _u(f)
    if not u:
        return 'unknown', 'Onbekend.'
    if not u.get('signIns'):
        return 'unknown', 'Aanmelddata vraagt Entra ID P1 (Business Premium).'
    oud = [x for x in u['users'] if x['enabled'] and x['mfa'] not in ('shared', 'disabled') and (x['days'] is None or x['days'] > 90)]
    if not oud:
        return 'ok', 'Geen actieve accounts die langer dan 90 dagen niet zijn gebruikt.'
    return 'warn', f'{len(oud)} account(s) staan aan maar zijn langer dan 90 dagen niet gebruikt. Opruimen via Tenant > Inactieve gebruikers.', [x['name'] for x in oud][:30]


def _dev(f):
    return f['devices'] or {}


def c_bitlocker(f):
    d = _dev(f)
    if not d:
        return 'unknown', 'Apparaten konden niet worden gelezen.'
    win = [x for x in d['devices'] if x['kind'] == 'Windows' and x['intune']]
    if not win:
        return 'unknown', 'Geen Windows-apparaten in Intune.'
    uit = [x for x in win if x['bitlocker'] != 'on']
    if not uit:
        return 'ok', f'Alle {len(win)} Windows-apparaten zijn versleuteld met BitLocker.'
    return 'err', f'{len(uit)} van {len(win)} Windows-apparaten zijn niet (aantoonbaar) versleuteld.', [x['name'] for x in uit][:30]


def c_os(f):
    d = _dev(f)
    if not d:
        return 'unknown', 'Onbekend.'
    oud = [x for x in d['devices'] if x['status'] == 'unsupported' and not x['stale']]
    if not oud:
        return 'ok', 'Alle actieve apparaten draaien een ondersteunde versie.'
    return 'err', f'{len(oud)} actief(ve) apparaat/apparaten krijgen geen beveiligingsupdates meer.', [f"{x['name']} ({x['release'] or x['osv']})" for x in oud][:30]


def c_patch(f):
    d = _dev(f)
    if not d:
        return 'unknown', 'Onbekend.'
    achter = [x for x in d['devices'] if x['status'] == 'behind' and not x['stale']]
    if not achter:
        return 'ok', 'Alle actieve apparaten hebben het nieuwste patchniveau in deze tenant.'
    return 'warn', f'{len(achter)} apparaat/apparaten lopen achter met updates.', [x['name'] for x in achter][:30]


def c_stale(f):
    d = _dev(f)
    if not d:
        return 'unknown', 'Onbekend.'
    oud = [x for x in d['devices'] if x['days'] is not None and x['days'] > 90]
    if not oud:
        return 'ok', 'Geen apparaten die langer dan 90 dagen niet zijn gezien.'
    return 'warn', f'{len(oud)} apparaat/apparaten zijn langer dan 90 dagen niet gezien. Opschonen via Compliance > Apparaten > Opschonen.', [x['name'] for x in oud][:30]


def c_intune(f):
    d = _dev(f)
    if not d:
        return 'unknown', 'Onbekend.'
    if not d.get('intune'):
        return 'err', 'Intune is niet beschikbaar: apparaten worden niet centraal beheerd (geen inventaris, geen versleutelingsbeleid).'
    totaal = len([x for x in d['devices'] if not x['stale']])
    beheerd = len([x for x in d['devices'] if x['intune'] and not x['stale']])
    if totaal and beheerd / totaal < .8:
        return 'warn', f'Slechts {beheerd} van {totaal} actieve apparaten staan in Intune.'
    return 'ok', f'{beheerd} actieve apparaten worden beheerd met Intune.'


def c_cpol(f):
    if f['cpol'] is None:
        return 'unknown', 'Nalevingsbeleid kon niet worden gelezen (Intune).'
    if not f['cpol']:
        return 'err', 'Er is geen Intune-nalevingsbeleid (compliance policy): niet vast te stellen of apparaten aan de eisen voldoen.'
    d = _dev(f)
    nc = [x for x in d.get('devices', []) if x['intune'] and x['comp'] and x['comp'] != 'compliant' and not x['stale']]
    if nc:
        return 'warn', f"{len(f['cpol'])} nalevingsbeleid(en) actief, maar {len(nc)} apparaat/apparaten voldoen niet.", [x['name'] for x in nc][:30]
    return 'ok', f"{len(f['cpol'])} nalevingsbeleid(en) actief en alle beheerde apparaten voldoen."


def _mail(f):
    return f['mail'] or {}


def c_spf(f):
    m = _mail(f)
    if not m:
        return 'unknown', 'Geen eigen domeinen of DNS niet bereikbaar.'
    fout = [d for d, v in m.items() if not v['spf'] or len(v['spf']) > 1]
    if not fout:
        return 'ok', f'SPF staat goed voor {len(m)} domein(en).'
    return 'err', f"SPF ontbreekt of is dubbel bij: {', '.join(fout)}."


def c_dmarc(f):
    m = _mail(f)
    if not m:
        return 'unknown', 'Geen eigen domeinen.'
    geen = [d for d, v in m.items() if not v['dmarc']]
    zwak = [d for d, v in m.items() if v['dmarc'] and re.search(r'p\s*=\s*none', v['dmarc'][0], re.I)]
    if geen:
        return 'err', f"Geen DMARC-record bij: {', '.join(geen)}."
    if zwak:
        return 'warn', f"DMARC staat alleen op monitoren (p=none) bij: {', '.join(zwak)}. Advies: p=quarantine of p=reject."
    return 'ok', f'DMARC staat op quarantine of reject voor alle {len(m)} domein(en).'


def _exof(f):
    return f['exo'] or {}


def c_dkim(f):
    e = _exof(f)
    if e.get('dkim') is None or e.get('dom') is None:
        return 'unknown', 'Exchange niet verbonden.'
    aan = {str(k.get('Domain') or k.get('Name')).lower() for k in e['dkim'] if k.get('Enabled')}
    eigen = [str(d.get('DomainName') or d.get('Name')) for d in e['dom'] if not str(d.get('DomainName') or d.get('Name')).lower().endswith('.onmicrosoft.com')]
    uit = [d for d in eigen if d.lower() not in aan]
    if not uit:
        return 'ok', 'DKIM staat aan voor alle eigen domeinen.'
    return 'err', f"DKIM staat uit bij: {', '.join(uit)}."


def c_extern(f):
    e = _exof(f)
    if e.get('ext') is None:
        return 'unknown', 'Exchange niet verbonden.'
    aan = any(x.get('Enabled') for x in e['ext'])
    return ('ok', 'Externe afzenders krijgen het label "Extern" in Outlook.') if aan else ('warn', 'Externe afzenders worden niet gemarkeerd in Outlook.')


def c_forward(f):
    e = _exof(f)
    if e.get('out') is None:
        return 'unknown', 'Exchange niet verbonden.'
    modus = str(e['out'].get('AutoForwardingMode') or '')
    if modus == 'Off':
        return 'ok', 'Automatisch doorsturen naar externe adressen is geblokkeerd.'
    if modus == 'Automatic':
        return 'warn', 'Automatisch doorsturen staat op "Automatisch" (Microsoft blokkeert nu, maar dit kan veranderen). Advies: expliciet uitzetten.'
    return 'err', 'Automatisch doorsturen naar externe adressen is toegestaan.'


def c_bijlagen(f):
    e = _exof(f)
    if e.get('mal') is None:
        return 'unknown', 'Exchange niet verbonden.'
    return ('ok', 'Gevaarlijke bijlagen (.exe, .js, .iso e.d.) worden tegengehouden.') if e['mal'].get('EnableFileFilter') \
        else ('err', 'Het filter voor gevaarlijke bijlagen staat uit.')


def c_ual(f):
    e = _exof(f)
    if e.get('audit') is None:
        return 'unknown', 'Exchange niet verbonden.'
    return ('ok', 'De Unified Audit Log staat aan (aanmeldingen, beheeracties, mail- en bestandsactiviteit worden vastgelegd).') \
        if e['audit'].get('UnifiedAuditLogIngestionEnabled') else ('err', 'De Unified Audit Log staat uit: activiteiten worden niet vastgelegd.')


def c_mbaudit(f):
    e = _exof(f)
    if e.get('org') is None:
        return 'unknown', 'Exchange niet verbonden.'
    return ('err', 'Postvak-auditing staat uit voor de organisatie.') if e['org'].get('AuditDisabled') else ('ok', 'Postvak-auditing staat aan.')


DELEN_NL = {0: 'alleen intern', 1: 'nieuwe en bestaande gasten', 2: 'iedereen (anonieme links)', 3: 'alleen bestaande gasten'}


def c_sp(f):
    s = f['sp']
    if s is None:
        return 'unknown', 'SharePoint-instellingen konden niet worden gelezen (rol SharePoint Administrator nodig).'
    v = int(s.get('SharingCapability') or 0)
    return ('err' if v == 2 else 'ok'), f'SharePoint: delen met {DELEN_NL.get(v, v)}.'


def c_od(f):
    s = f['sp']
    if s is None:
        return 'unknown', 'Onbekend.'
    v = s.get('OneDriveSharingCapability')
    if v is None:
        return 'unknown', 'Onbekend.'
    return ('err' if int(v) == 2 else 'ok'), f'OneDrive: delen met {DELEN_NL.get(int(v), v)}.'


def c_linktype(f):
    s = f['sp']
    if s is None or s.get('DefaultSharingLinkType') is None:
        return 'unknown', 'Onbekend.'
    t, p = int(s.get('DefaultSharingLinkType') or 0), int(s.get('DefaultLinkPermission') or 0)
    naam = {1: 'specifieke personen', 2: 'iedereen in de organisatie', 3: 'iedereen met de link'}.get(t, 'standaard')
    if t == 3:
        return 'err', f'Standaard deellink: {naam}. Een snel gedeelde link is dan openbaar.'
    if t == 2 or p == 2:
        return 'warn', f"Standaard deellink: {naam}{', met bewerkrechten' if p == 2 else ''}. Dit vergroot oversharing (ook via Copilot)."
    return 'ok', f'Standaard deellink: {naam}, alleen-lezen.'


def c_openbaar(f):
    if f['groups'] is None:
        return 'unknown', 'Groepen konden niet worden gelezen.'
    pub = [x for x in f['groups'] if str(x.get('visibility') or '').lower() == 'public']
    if not pub:
        return 'ok', 'Er zijn geen openbare Microsoft 365-groepen of Teams.'
    return 'warn', f'{len(pub)} openbare groep(en)/team(s): alle collega\'s kunnen de inhoud zien en Copilot kan die aan iedereen tonen.', \
        [x.get('displayName') or '' for x in pub][:30]


def c_labels(f):
    if f['labels'] is None:
        return 'unknown', 'Gevoeligheidslabels konden niet worden gelezen (recht InformationProtectionPolicy.Read of licentie ontbreekt).'
    if not f['labels']:
        return 'warn', 'Er zijn geen gevoeligheidslabels (bijv. Openbaar, Intern, Vertrouwelijk, Medisch).'
    return 'ok', f"{len(f['labels'])} gevoeligheidslabel(s): {', '.join(str(x.get('name') or '') for x in f['labels'][:6])}."


def _skus(f):
    return [s for s in (f['skus'] or []) if s.get('total')]


def c_copilot_lic(f):
    if f['skus'] is None:
        return 'unknown', 'Licenties konden niet worden gelezen.'
    cp = [s for s in _skus(f) if 'copilot' in s['part'].lower() and 'studio' not in s['name'].lower() and 'dragon' not in s['part'].lower()]
    if cp:
        return 'ok', ', '.join(f"{s['name']}: {s['used']} van {s['total']} toegewezen" for s in cp)
    return 'warn', 'Nog geen Microsoft 365 Copilot-licenties. Gratis Copilot Chat werkt wel (zonder toegang tot bedrijfsgegevens).'


def c_basis(f):
    if f['skus'] is None:
        return 'unknown', 'Onbekend.'
    basis = [s for s in _skus(f) if s['part'] in BASIS_SKUS or re.search(r'business_(premium|standard)|_e[35]\b', s['part'], re.I)]
    if basis:
        return 'ok', 'Geschikte basislicentie aanwezig: ' + ', '.join(s['name'] for s in basis[:4]) + '.'
    return 'err', 'Geen basislicentie gevonden die Copilot ondersteunt (Business Basic/Standard/Premium of E3/E5).'


# key, categorie, titel, functie, fix, {profiel: (gewicht, verwijzing)}
CONTROLES: list[tuple] = [
    ('copilot_lic', 'Licenties', 'Copilot-licenties', c_copilot_lic, None, {'copilot': (1, '')}),
    ('basis', 'Licenties', 'Basislicentie geschikt voor Copilot', c_basis, None, {'copilot': (2, '')}),
    ('mfa_reg', 'Identiteit en toegang', 'MFA geregistreerd voor alle gebruikers', c_mfa_reg, None, {'copilot': (2, ''), 'nen': (3, '8.5')}),
    ('mfa_enf', 'Identiteit en toegang', 'MFA wordt afgedwongen', c_mfa_enf, None, {'copilot': (2, ''), 'nen': (3, '8.5')}),
    ('legacy', 'Identiteit en toegang', 'Verouderde aanmeldmethoden geblokkeerd', c_legacy, None, {'nen': (2, '8.5')}),
    ('admins_mfa', 'Identiteit en toegang', 'Beheerders met sterke MFA', c_admins_mfa, None, {'nen': (3, '8.2')}),
    ('ga', 'Identiteit en toegang', 'Aantal Global Administrators (2 tot 4)', c_ga, None, {'nen': (1, '8.2')}),
    ('breakglass', 'Identiteit en toegang', 'Noodaccount (break-glass) aanwezig', c_breakglass, None, {'nen': (1, '5.18')}),
    ('admin_apart', 'Identiteit en toegang', 'Aparte beheeraccounts', c_admin_apart, None, {'nen': (1, '8.2')}),
    ('consent', 'Identiteit en toegang', 'Gebruikers geven geen toestemming aan apps', c_consent, 'consent', {'copilot': (1, ''), 'nen': (1, '5.23')}),
    ('apps', 'Identiteit en toegang', 'Gebruikers maken geen app-registraties', c_apps, 'apps_create', {'nen': (1, '8.2')}),
    ('inactief', 'Identiteit en toegang', 'Geen ongebruikte actieve accounts', c_inactief, None, {'copilot': (1, ''), 'nen': (2, '5.18')}),
    ('gasten', 'Identiteit en toegang', 'Gastaccounts actueel', c_gasten, None, {'copilot': (1, ''), 'nen': (1, '5.18')}),
    ('intune', 'Apparaten', 'Apparaten centraal beheerd (Intune)', c_intune, None, {'nen': (2, '8.1')}),
    ('cpol', 'Apparaten', 'Nalevingsbeleid en compliant apparaten', c_cpol, None, {'nen': (2, '8.1')}),
    ('bitlocker', 'Apparaten', 'Versleuteling (BitLocker)', c_bitlocker, None, {'nen': (3, '8.24')}),
    ('os', 'Apparaten', 'Ondersteunde besturingssystemen', c_os, None, {'nen': (3, '8.8')}),
    ('patch', 'Apparaten', 'Updates bijgewerkt', c_patch, None, {'nen': (2, '8.8')}),
    ('stale', 'Apparaten', 'Geen verouderde apparaten in de inventaris', c_stale, None, {'nen': (1, '5.9')}),
    ('spf', 'E-mail', 'SPF', c_spf, None, {'nen': (2, '5.14')}),
    ('dkim', 'E-mail', 'DKIM', c_dkim, 'dkim', {'nen': (2, '5.14')}),
    ('dmarc', 'E-mail', 'DMARC (quarantine of reject)', c_dmarc, None, {'nen': (2, '5.14')}),
    ('extern', 'E-mail', 'Externe afzenders gemarkeerd', c_extern, 'externaltag', {'nen': (1, '5.14')}),
    ('forward', 'E-mail', 'Extern doorsturen geblokkeerd', c_forward, 'autoforward', {'copilot': (1, ''), 'nen': (2, '5.14')}),
    ('bijlagen', 'E-mail', 'Gevaarlijke bijlagen tegengehouden', c_bijlagen, 'attachments', {'nen': (2, '8.7')}),
    ('sp', 'Gegevens en delen', 'SharePoint: geen anonieme links', c_sp, 'sp_sharing', {'copilot': (3, ''), 'nen': (3, '5.14')}),
    ('od', 'Gegevens en delen', 'OneDrive: geen anonieme links', c_od, 'od_sharing', {'copilot': (2, ''), 'nen': (2, '5.14')}),
    ('linktype', 'Gegevens en delen', 'Standaard deellink beperkt', c_linktype, 'sp_linktype', {'copilot': (3, ''), 'nen': (1, '5.10')}),
    ('openbaar', 'Gegevens en delen', 'Geen openbare groepen of Teams', c_openbaar, 'public_groups', {'copilot': (3, ''), 'nen': (1, '5.15')}),
    ('labels', 'Gegevens en delen', 'Gevoeligheidslabels (classificatie)', c_labels, None, {'copilot': (2, ''), 'nen': (2, '5.12')}),
    ('ual', 'Logging en monitoring', 'Unified Audit Log aan', c_ual, 'ual', {'copilot': (2, ''), 'nen': (3, '8.15')}),
    ('mbaudit', 'Logging en monitoring', 'Postvak-auditing aan', c_mbaudit, 'mailboxaudit', {'nen': (2, '8.15')}),
]

# NEN 7510: niet technisch te meten, wel nodig voor de audit (blijven buiten de score)
HANDMATIG_NEN = [
    ('Organisatie', 'Risicoanalyse informatiebeveiliging (patiënt- en persoonsgegevens geïnventariseerd)', '6.1 / 5.12'),
    ('Organisatie', 'Informatiebeveiligingsbeleid vastgesteld door de directie', '5.1'),
    ('Organisatie', 'Rollen en verantwoordelijkheden vastgelegd (wie is eigenaar van informatiebeveiliging)', '5.2'),
    ('Organisatie', 'Acceptabel-gebruikbeleid, ondertekend door medewerkers', '5.10'),
    ('Organisatie', 'Autorisatieprocedure (wie krijgt welke toegang, periodieke controle)', '5.15 / 5.18'),
    ('Organisatie', 'Procedure in en uit dienst (onboarding/offboarding)', '6.1 / 6.5'),
    ('Organisatie', 'Incident- en datalekprocedure (inclusief meldplicht AP)', '5.24 - 5.26'),
    ('Organisatie', 'Verwerkersovereenkomsten met leveranciers (Microsoft, back-up, EDR e.d.)', '5.19 - 5.21'),
    ('Mensen', 'Security awareness-training en phishingsimulatie (bijv. BullPhish ID)', '6.3'),
    ('Techniek', 'Back-up van Microsoft 365 (mail, OneDrive, SharePoint, Teams) met hersteltest', '8.13'),
    ('Techniek', 'EDR/antivirus op alle werkplekken actief en bewaakt (bijv. Datto EDR / Defender)', '8.7'),
    ('Techniek', 'Geen lokale beheerdersrechten voor gebruikers (LAPS of Intune-accountbescherming)', '8.2'),
    ('Techniek', 'Monitoring en alerts op aanmeldingen en activiteiten (bijv. SaaS Alerts)', '8.16'),
    ('Techniek', 'Bewaartermijnen en retentie vastgelegd (Purview) en audit-bewaartermijn bekend', '5.33 / 8.15'),
    ('Organisatie', 'Maandelijkse security review en jaarlijkse evaluatie (managementreview)', '5.35 / 5.36'),
]

ADVIES_COPILOT = [
    'Voer Copilot gefaseerd in: begin met een pilotgroep en evalueer na 4 weken.',
    'Controleer de sites met de meeste deellinks en gevoelige inhoud (SharePoint Advanced Management of het rapport "Oversharing" in Purview).',
    'Zet Restricted Content Discovery aan voor sites die Copilot niet mag doorzoeken (bijv. HR of directie).',
    'Zorg dat Microsoft 365 Apps op het kanaal "Huidig" of "Maandelijks Enterprise" staan; Copilot werkt niet op oude builds.',
    'Leg in een gebruiksrichtlijn vast wat medewerkers wel en niet met Copilot doen (bijv. geen patiëntgegevens in prompts zonder afspraak).',
]


def _rapport(c: Ctx, profiel: str) -> dict:
    f = c.t.cache('readiness-feiten', lambda: _feiten(c), VERS)
    uit, totaal, behaald = [], 0.0, 0.0
    per_cat: dict[str, list[float]] = {}
    for key, cat, titel, fn, fix, profielen in CONTROLES:
        if profiel not in profielen:
            continue
        gewicht, ref = profielen[profiel]
        try:
            r = fn(f)
        except Exception as e:  # noqa: BLE001 - één controle mag de rest niet stoppen
            r = ('unknown', f'Controle mislukt: {str(e)[:150]}')
        status, tekst = r[0], r[1]
        details = r[2] if len(r) > 2 else []
        if status in GOED:
            totaal += gewicht
            behaald += gewicht * GOED[status]
            per_cat.setdefault(cat, [0.0, 0.0])
            per_cat[cat][0] += gewicht
            per_cat[cat][1] += gewicht * GOED[status]
        fx = FIXES.get(fix) if fix and status in ('warn', 'err') else None
        uit.append({'key': key, 'category': cat, 'title': titel, 'status': status, 'text': tekst, 'details': details, 'weight': gewicht, 'ref': ref,
                    'gain': gewicht * (1 - GOED.get(status, 1)),
                    'fix': {'key': fix, 'what': fx['what'], 'impact': fx['impact']} if fx else None})
    for x in uit:   # winst als percentage van de totale score
        x['gainPct'] = round(x.pop('gain') / totaal * 100, 1) if totaal else 0
    volgorde = {'err': 0, 'warn': 1, 'unknown': 2, 'ok': 3}
    uit.sort(key=lambda x: (volgorde.get(x['status'], 9), -x['gainPct']))
    return {'score': round(behaald / totaal * 100) if totaal else 0, 'checks': uit,
            'categories': [{'name': k, 'score': round(v[1] / v[0] * 100) if v[0] else 0} for k, v in per_cat.items()],
            'manual': [{'category': a, 'title': b, 'ref': r} for a, b, r in HANDMATIG_NEN] if profiel == 'nen' else [],
            'advice': ADVIES_COPILOT if profiel == 'copilot' else [], 'errors': f['_fout']}


@api('rd.copilot')
def rd_copilot(c: Ctx, b: dict) -> dict:
    if b.get('fresh'):
        c.t.weg('readiness-feiten', 'compliance-gebruikers', 'compliance-apparaten')
    return _rapport(c, 'copilot')


@api('rd.nen')
def rd_nen(c: Ctx, b: dict) -> dict:
    if b.get('fresh'):
        c.t.weg('readiness-feiten', 'compliance-gebruikers', 'compliance-apparaten')
    return _rapport(c, 'nen')


@api('rd.apply')
def rd_apply(c: Ctx, b: dict) -> dict:
    fx = FIXES.get(str(b.get('key')))
    if not fx:
        raise ApiFout('Deze actie kan de app niet direct toepassen.')
    fx['fn'](c)
    c.t.weg('readiness-feiten', 'compliance-gebruikers', 'securescore')
    c.L(f"Toegepast: {fx['what']}")
    return {}
