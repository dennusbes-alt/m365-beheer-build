"""Intune-beheer: configuratieprofielen (incl. settings catalog, beheersjablonen en nalevingsbeleid), apps en
inschrijving (Windows: platformbeperkingen, apparaatlimiet, Windows Hello for Business, inschrijvingsstatuspagina,
automatische MDM-inschrijving; Android: Managed Google Play en inschrijvingsprofielen met QR-code).

Graph: deviceManagement/* en deviceAppManagement/* (deels beta). Rechten: DeviceManagementConfiguration.ReadWrite.All,
DeviceManagementApps.ReadWrite.All, DeviceManagementServiceConfig.ReadWrite.All, Policy.ReadWrite.MobilityManagement.
GDAP-rol bij de klant: Intune Administrator.
"""
from __future__ import annotations

import logging

import requests

from .clients import ApiFout, parallel
from .context import Ctx, VERS, api

log = logging.getLogger('m365beheer')
BETA = 'https://graph.microsoft.com/beta'
INTUNE_APP = '0000000a-0000-0000-c000-000000000000'

GEEN_INTUNE = ('Intune is bij deze klant niet beschikbaar of de rechten ontbreken: controleer de Intune-licentie en de GDAP-rol '
               'Intune Administrator. Nieuwe rechten van de app worden bij het openen van de klant aangevuld; probeer het zo nodig over een paar minuten opnieuw.')


def _fout(e: ApiFout) -> ApiFout:
    if e.status not in (401, 403) or str(e).startswith(('Intune is', 'De app')):
        return e
    if 'scope' in str(e).lower():
        return ApiFout('De app mist nog de nieuwe Intune-rechten (Microsoft: "Application is not authorized ... scopes"). '
                       'Bij Justdata zelf: opzetten_app.py één keer opnieuw laten draaien en daarna opnieuw aanmelden. '
                       'Bij een klant vult de app de rechten zelf aan; probeer het over een paar minuten opnieuw.', e.status)
    return ApiFout(GEEN_INTUNE + f' (Microsoft: {str(e)[:160]})', e.status)


def _probeer(c: Ctx, fn):
    """Bij een weigering door ontbrekende rechten: bij een klant de koppeling aanvullen, verse tokens en één keer opnieuw."""
    try:
        return fn()
    except ApiFout as e:
        if e.status not in (401, 403):
            raise
        fout = e
        if c.t.id != c.staat.auth.home_tenant:
            st = c.t.rechten_nu()
            c.staat.auth.vergeet(c.t.id)
            log.info('Intune geweigerd bij %s, rechten: %s; opnieuw', c.t.naam, st)
            try:
                return fn()
            except ApiFout as e2:
                fout = e2
        raise _fout(fout) from None


# ---------------------------------------------------------------- Toewijzingen (gedeeld)
DOEL = {'#microsoft.graph.allDevicesAssignmentTarget': 'Alle apparaten', '#microsoft.graph.allLicensedUsersAssignmentTarget': 'Alle gebruikers'}


def _groepnamen(c: Ctx, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    uit = {}
    lijst = list(ids)
    for i in range(0, len(lijst), 1000):
        try:
            r = c.g.post('/directoryObjects/getByIds', {'ids': lijst[i:i + 1000], 'types': ['group']})
            uit.update({x['id']: x.get('displayName') or x['id'] for x in r.get('value') or []})
        except ApiFout:
            pass
    return uit


def _toewijzingen(lijst: list, namen: dict, app: bool = False) -> list[dict]:
    uit = []
    for a in lijst or []:
        t = a.get('target') or {}
        soort = t.get('@odata.type', '')
        gid = t.get('groupId')
        uit.append({'kind': 'exclude' if 'exclusion' in soort else 'all_devices' if 'allDevices' in soort else 'all_users' if 'allLicensedUsers' in soort else 'group',
                    'groupId': gid, 'name': DOEL.get(soort) or namen.get(gid) or gid or soort.replace('#microsoft.graph.', ''),
                    'intent': a.get('intent') if app else None})
    return uit


def _doel(t: dict) -> dict:
    k = t.get('kind')
    if k == 'all_devices':
        return {'@odata.type': '#microsoft.graph.allDevicesAssignmentTarget'}
    if k == 'all_users':
        return {'@odata.type': '#microsoft.graph.allLicensedUsersAssignmentTarget'}
    if not t.get('groupId'):
        raise ApiFout('Kies een groep.')
    return {'@odata.type': '#microsoft.graph.exclusionGroupAssignmentTarget' if k == 'exclude' else '#microsoft.graph.groupAssignmentTarget',
            'groupId': t['groupId']}


# ---------------------------------------------------------------- Configuratieprofielen
PLATFORM = {'windows10': 'Windows', 'windows81': 'Windows 8.1', 'android': 'Android', 'androidWorkProfile': 'Android (werkprofiel)',
            'androidDeviceOwner': 'Android Enterprise', 'ios': 'iOS/iPadOS', 'macOS': 'macOS', 'aosp': 'Android (AOSP)', 'linux': 'Linux'}
SOORT = {'dc': 'Sjabloon', 'sc': 'Settings catalog', 'gp': 'Beheersjabloon (ADMX)', 'cp': 'Nalevingsbeleid', 'es': 'Endpoint security'}
PAD = {'dc': '/deviceManagement/deviceConfigurations', 'sc': BETA + '/deviceManagement/configurationPolicies',
       'gp': BETA + '/deviceManagement/groupPolicyConfigurations', 'cp': '/deviceManagement/deviceCompliancePolicies'}


def _platform_van(odata: str) -> str:
    o = odata.replace('#microsoft.graph.', '').lower()
    for k, v in (('windows10', 'Windows'), ('windows81', 'Windows'), ('windows', 'Windows'), ('androiddeviceowner', 'Android Enterprise'),
                 ('androidworkprofile', 'Android (werkprofiel)'), ('aosp', 'Android (AOSP)'), ('android', 'Android'), ('ios', 'iOS/iPadOS'),
                 ('macos', 'macOS'), ('edition', 'Windows'), ('sharedpc', 'Windows')):
        if o.startswith(k):
            return v
    return ''


def _sjabloon(odata: str) -> str:
    o = odata.replace('#microsoft.graph.', '')
    for k, v in (('GeneralConfiguration', 'Apparaatbeperkingen'), ('EndpointProtection', 'Endpoint Protection'), ('CustomConfiguration', 'Aangepast (OMA-URI)'),
                 ('UpdateForBusiness', 'Windows Update-ring'), ('WiFi', 'Wifi'), ('Vpn', 'VPN'), ('HealthMonitoring', 'Statuscontrole'),
                 ('DeliveryOptimization', 'Delivery Optimization'), ('IdentityProtection', 'Identiteitsbescherming'), ('Kiosk', 'Kiosk'),
                 ('EditionUpgrade', 'Editie-upgrade'), ('TrustedRootCertificate', 'Vertrouwd certificaat'), ('ScepCertificate', 'SCEP-certificaat'),
                 ('PkcsCertificate', 'PKCS-certificaat'), ('EmailProfile', 'E-mail'), ('DomainJoin', 'Domeindeelname'), ('Compliance', 'Naleving')):
        if k.lower() in o.lower():
            return v
    return o


def _profielen(c: Ctx) -> dict:
    g = c.g
    r = parallel({
        'dc': lambda: g.all(BETA + '/deviceManagement/deviceConfigurations?$select=id,displayName,description,lastModifiedDateTime&$expand=assignments&$top=200'),
        'sc': lambda: g.all(BETA + '/deviceManagement/configurationPolicies?$select=id,name,description,platforms,technologies,lastModifiedDateTime,settingCount,templateReference'
                                   '&$expand=assignments&$top=100'),
        'gp': lambda: g.all(BETA + '/deviceManagement/groupPolicyConfigurations?$select=id,displayName,description,lastModifiedDateTime&$expand=assignments&$top=200'),
        'cp': lambda: g.all(BETA + '/deviceManagement/deviceCompliancePolicies?$select=id,displayName,description,lastModifiedDateTime&$expand=assignments&$top=200'),
    })
    if all(isinstance(v, Exception) for v in r.values()):
        raise r['dc']
    gids = {(a.get('target') or {}).get('groupId') for v in r.values() if isinstance(v, list) for p in v for a in p.get('assignments') or []}
    namen = _groepnamen(c, gids)
    uit = []
    for soort, lijst in r.items():
        if isinstance(lijst, Exception):
            log.info('Intune-profielen %s: %s', soort, lijst)
            continue
        for p in lijst:
            odata = p.get('@odata.type', '')
            if soort == 'sc':
                tf = str((p.get('templateReference') or {}).get('templateFamily') or '')
                plat = ', '.join(PLATFORM.get(x, x) for x in str(p.get('platforms') or '').split(',') if x)
                srt = 'es' if tf.startswith('endpointSecurity') else 'sc'
                naam, sjab = p.get('name') or '', ('Endpoint security: ' + tf.replace('endpointSecurity', '')) if srt == 'es' else f"{p.get('settingCount') or 0} instellingen"
            else:
                srt, naam = soort, p.get('displayName') or ''
                plat = 'Windows' if soort == 'gp' else _platform_van(odata)
                sjab = 'Beheersjabloon' if soort == 'gp' else _sjabloon(odata)
            uit.append({'id': p['id'], 'kind': soort, 'type': SOORT[srt], 'template': sjab, 'odata': odata, 'name': naam, 'desc': p.get('description') or '',
                        'platform': plat or '-', 'modified': p.get('lastModifiedDateTime') or '',
                        'assignments': _toewijzingen(p.get('assignments'), namen)})
    uit.sort(key=lambda x: (x['platform'], x['name'].lower()))
    return {'profiles': uit, 'partial': [k for k, v in r.items() if isinstance(v, Exception)]}


@api('in.profiles')
def in_profiles(c: Ctx, b: dict) -> dict:
    return _probeer(c, lambda: c.t.cache('in.profielen', lambda: _profielen(c), VERS, bool(b.get('fresh'))))


@api('in.profile.status')
def in_profile_status(c: Ctx, b: dict) -> dict:
    """Stand per apparaat (geslaagd/fout/conflict/in behandeling) voor sjablonen en nalevingsbeleid."""
    soort, pid = b['kind'], b['id']
    if soort not in ('dc', 'cp'):
        return {'overview': None}
    try:
        o = c.g.get(f"{PAD[soort]}/{pid}/deviceStatusOverview")
    except ApiFout as e:
        return {'overview': None, 'error': str(e)[:200]}
    return {'overview': {'success': o.get('successCount') or o.get('compliantDeviceCount') or 0,
                         'error': (o.get('errorCount') or 0) + (o.get('failedCount') or 0) + (o.get('nonCompliantDeviceCount') or 0),
                         'conflict': o.get('conflictCount') or 0, 'pending': o.get('pendingCount') or 0, 'na': o.get('notApplicableCount') or 0}}


@api('in.profile.assign')
def in_profile_assign(c: Ctx, b: dict) -> dict:
    """Toewijzingen van een profiel vervangen door de opgegeven lijst (groep, uitsluiten, alle apparaten/gebruikers)."""
    soort, pid = b['kind'], b['id']
    doelen = [_doel(t) for t in b.get('assignments') or []]
    pad = PAD[soort if soort in PAD else 'sc']
    body = {'assignments': [{'target': d} for d in doelen]}
    try:
        c.g.post(f'{pad}/{pid}/assign', body)
    except ApiFout as e:
        raise _fout(e)
    c.L(f"Toewijzingen van profiel '{b.get('name', pid)}' bijgewerkt ({len(doelen)} doel(en)).")
    return {}


@api('in.profile.delete')
def in_profile_delete(c: Ctx, b: dict) -> dict:
    soort = b['kind'] if b['kind'] in PAD else 'sc'
    try:
        c.g.delete(f"{PAD[soort]}/{b['id']}")
    except ApiFout as e:
        raise _fout(e)
    c.L(f"Profiel '{b.get('name', b['id'])}' verwijderd.")
    return {}


# ---------------------------------------------------------------- Apps
APPSOORT = {'winGetApp': 'Microsoft Store-app', 'win32LobApp': 'Windows-app (Win32)', 'officeSuiteApp': 'Microsoft 365 Apps', 'windowsMicrosoftEdgeApp': 'Microsoft Edge',
            'windowsMobileMSI': 'Windows MSI (LOB)', 'windowsUniversalAppX': 'Windows AppX/MSIX', 'microsoftStoreForBusinessApp': 'Store voor Bedrijven',
            'windowsStoreApp': 'Microsoft Store (oud)', 'windowsWebApp': 'Webkoppeling (Windows)', 'webApp': 'Webkoppeling', 'androidManagedStoreApp': 'Managed Google Play',
            'androidManagedStoreWebApp': 'Managed Google Play (web)', 'androidStoreApp': 'Android Store-app', 'androidLobApp': 'Android LOB', 'iosVppApp': 'iOS (VPP)',
            'iosStoreApp': 'iOS Store-app', 'iosLobApp': 'iOS LOB', 'macOSMicrosoftEdgeApp': 'Edge (macOS)', 'macOSOfficeSuiteApp': 'Microsoft 365 (macOS)',
            'macOSLobApp': 'macOS LOB', 'macOSDmgApp': 'macOS DMG', 'macOSPkgApp': 'macOS PKG', 'managedAndroidStoreApp': 'Android (beheerd)',
            'managedIOSStoreApp': 'iOS (beheerd)', 'win32CatalogApp': 'Enterprise App Catalog'}
INTENT = {'required': 'Verplicht', 'available': 'Beschikbaar', 'uninstall': 'Verwijderen', 'availableWithoutEnrollment': 'Beschikbaar zonder inschrijving'}


def _apps(c: Ctx) -> dict:
    alle = c.g.all(BETA + '/deviceAppManagement/mobileApps?$expand=assignments&$top=500')
    gids = {(a.get('target') or {}).get('groupId') for p in alle for a in p.get('assignments') or []}
    namen = _groepnamen(c, gids)
    uit = []
    for a in alle:
        o = a.get('@odata.type', '').replace('#microsoft.graph.', '')
        # Ingebouwde Microsoft-apps (app-beveiligingsbeleid) alleen tonen als ze zijn toegewezen
        if a.get('appAvailability') == 'global' and o.startswith('managed') and not a.get('assignments'):
            continue
        plat = ('Windows' if o.startswith(('win', 'microsoftStore', 'officeSuite')) else 'Android' if 'ndroid' in o else 'iOS/iPadOS' if 'ios' in o.lower()
                else 'macOS' if o.startswith('macOS') else 'Web' if o == 'webApp' else '')
        uit.append({'id': a['id'], 'name': a.get('displayName') or '', 'publisher': a.get('publisher') or '', 'type': APPSOORT.get(o, o), 'odata': o, 'platform': plat or '-',
                    'created': a.get('createdDateTime') or '', 'state': a.get('publishingState') or '',
                    'assignments': _toewijzingen(a.get('assignments'), namen, app=True)})
    uit.sort(key=lambda x: (x['platform'], x['name'].lower()))
    return {'apps': uit}


@api('in.apps')
def in_apps(c: Ctx, b: dict) -> dict:
    return _probeer(c, lambda: c.t.cache('in.apps', lambda: _apps(c), VERS, bool(b.get('fresh'))))


@api('in.app.status')
def in_app_status(c: Ctx, b: dict) -> dict:
    try:
        s = c.g.get(f"{BETA}/deviceAppManagement/mobileApps/{b['id']}/installSummary")
    except ApiFout as e:
        return {'summary': None, 'error': str(e)[:200]}
    return {'summary': {'installed': s.get('installedDeviceCount') or 0, 'failed': s.get('failedDeviceCount') or 0,
                        'pending': s.get('pendingInstallDeviceCount') or 0, 'notInstalled': s.get('notInstalledDeviceCount') or 0,
                        'na': s.get('notApplicableDeviceCount') or 0}}


@api('in.app.assign')
def in_app_assign(c: Ctx, b: dict) -> dict:
    """Toewijzingen van een app vervangen (per doel een bedoeling: verplicht, beschikbaar of verwijderen)."""
    lijst = []
    for t in b.get('assignments') or []:
        intent = t.get('intent') or 'required'
        if intent not in INTENT:
            raise ApiFout('Onbekende bedoeling.')
        lijst.append({'@odata.type': '#microsoft.graph.mobileAppAssignment', 'intent': intent, 'target': _doel(t)})
    try:
        c.g.post(f"/deviceAppManagement/mobileApps/{b['id']}/assign", {'mobileAppAssignments': lijst})
    except ApiFout as e:
        raise _fout(e)
    c.L(f"Toewijzingen van app '{b.get('name', b['id'])}' bijgewerkt ({len(lijst)} doel(en)).")
    return {}


@api('in.app.delete')
def in_app_delete(c: Ctx, b: dict) -> dict:
    try:
        c.g.delete(f"/deviceAppManagement/mobileApps/{b['id']}")
    except ApiFout as e:
        raise _fout(e)
    c.L(f"App '{b.get('name', b['id'])}' verwijderd uit Intune.")
    return {}


@api('in.store.search')
def in_store_search(c: Ctx, b: dict) -> dict:
    """Microsoft Store doorzoeken (dezelfde openbare catalogus als winget/Intune). Er wordt alleen de zoekterm verstuurd."""
    q = str(b.get('q') or '').strip()
    if len(q) < 2:
        return {'results': []}
    try:
        r = requests.post('https://storeedgefd.dsx.mp.microsoft.com/v9.0/manifestSearch', timeout=20,
                          json={'Query': {'KeyWord': q, 'MatchType': 'Substring'}})
        data = (r.json() or {}).get('Data') or []
    except (requests.exceptions.RequestException, ValueError) as e:
        raise ApiFout(f'Microsoft Store niet bereikbaar: {type(e).__name__}') from None
    return {'results': [{'id': d.get('PackageIdentifier'), 'name': d.get('PackageName'), 'publisher': d.get('Publisher')} for d in data[:30] if d.get('PackageIdentifier')]}


@api('in.app.add')
def in_app_add(c: Ctx, b: dict) -> dict:
    """App toevoegen: Microsoft Store-app (winget), Microsoft 365 Apps of Microsoft Edge; optioneel direct verplicht toewijzen."""
    soort = b.get('kind')
    if soort == 'store':
        if not b.get('packageId'):
            raise ApiFout('Kies een app uit de Microsoft Store.')
        body = {'@odata.type': '#microsoft.graph.winGetApp', 'displayName': b.get('name') or b['packageId'], 'publisher': b.get('publisher') or '-',
                'description': b.get('description') or b.get('name') or b['packageId'], 'packageIdentifier': b['packageId'],
                'installExperience': {'@odata.type': 'microsoft.graph.winGetAppInstallExperience', 'runAsAccount': 'user' if b.get('asUser') else 'system'}}
    elif soort == 'm365':
        body = {'@odata.type': '#microsoft.graph.officeSuiteApp', 'displayName': 'Microsoft 365 Apps voor Windows', 'publisher': 'Microsoft',
                'description': 'Microsoft 365 Apps (Word, Excel, PowerPoint, Outlook, OneNote, Teams)', 'isFeatured': False,
                'productIds': ['o365ProPlusRetail'], 'officePlatformArchitecture': 'x64', 'updateChannel': 'current', 'autoAcceptEula': True,
                'useSharedComputerActivation': bool(b.get('shared')), 'localesToInstall': ['nl-nl'] + (['en-us'] if b.get('english') else []),
                'excludedApps': {'groove': True, 'infoPath': True, 'sharePointDesigner': True, 'lync': True, 'access': not b.get('access'),
                                 'publisher': not b.get('publisherApp'), 'bing': True, 'teams': False, 'oneDrive': False, 'outlook': False,
                                 'word': False, 'excel': False, 'powerPoint': False, 'oneNote': False}}
    elif soort == 'edge':
        body = {'@odata.type': '#microsoft.graph.windowsMicrosoftEdgeApp', 'displayName': 'Microsoft Edge voor Windows', 'publisher': 'Microsoft',
                'description': 'Microsoft Edge (stabiel kanaal)', 'channel': 'stable', 'displayLanguageLocale': 'nl-NL'}
    else:
        raise ApiFout('Onbekende soort app.')
    try:
        app = c.g.post('/deviceAppManagement/mobileApps', body)
    except ApiFout as e:
        raise _fout(e)
    c.L(f"App '{body['displayName']}' toegevoegd aan Intune.")
    if b.get('assign'):
        try:
            in_app_assign(c, {'id': app['id'], 'name': body['displayName'], 'assignments': b['assign']})
        except ApiFout as e:
            c.L(f'FOUT toewijzen: {e}')
    return {'id': app.get('id')}


# ---------------------------------------------------------------- Inschrijving
def _inschrijving(c: Ctx) -> dict:
    g = c.g
    r = parallel({
        'conf': lambda: g.all(BETA + '/deviceManagement/deviceEnrollmentConfigurations?$expand=assignments&$top=100'),
        'mdm': lambda: g.get(BETA + '/policies/mobileDeviceManagementPolicies?$expand=includedGroups'),
        'gplay': lambda: g.get(BETA + '/deviceManagement/androidManagedStoreAccountEnterpriseSettings'),
        'aprof': lambda: g.all(BETA + '/deviceManagement/androidDeviceOwnerEnrollmentProfiles?$top=100'),
    })
    if isinstance(r['conf'], Exception):
        raise r['conf']
    gids = {(a.get('target') or {}).get('groupId') for x in r['conf'] for a in x.get('assignments') or []}
    namen = _groepnamen(c, gids)
    uit: dict = {'restrictions': [], 'limits': [], 'whfb': None, 'esp': [], 'mdm': None, 'gplay': None, 'androidProfiles': [], 'errors': {}}
    for x in r['conf']:
        o = x.get('@odata.type', '').replace('#microsoft.graph.', '')
        basis = {'id': x['id'], 'odata': x.get('@odata.type'), 'name': x.get('displayName') or '', 'priority': x.get('priority', 0),
                 'default': x.get('priority', 0) == 0, 'assignments': _toewijzingen(x.get('assignments'), namen)}
        if o == 'deviceEnrollmentPlatformRestrictionsConfiguration':   # oude vorm: alle platforms in één
            for plat, veld in (('windows', 'windowsRestriction'), ('android', 'androidRestriction'), ('androidForWork', 'androidForWorkRestriction'),
                               ('ios', 'iosRestriction'), ('mac', 'macOSRestriction')):
                v = x.get(veld) or {}
                uit['restrictions'].append({**basis, 'platform': plat, 'field': veld, 'blocked': bool(v.get('platformBlocked')),
                                            'personalBlocked': bool(v.get('personalDeviceEnrollmentBlocked')), 'min': v.get('osMinimumVersion') or '',
                                            'max': v.get('osMaximumVersion') or ''})
        elif o == 'deviceEnrollmentPlatformRestrictionConfiguration':   # nieuwe vorm: per platform
            v = x.get('platformRestriction') or {}
            uit['restrictions'].append({**basis, 'platform': x.get('platformType') or '', 'field': 'platformRestriction', 'blocked': bool(v.get('platformBlocked')),
                                        'personalBlocked': bool(v.get('personalDeviceEnrollmentBlocked')), 'min': v.get('osMinimumVersion') or '',
                                        'max': v.get('osMaximumVersion') or ''})
        elif o == 'deviceEnrollmentLimitConfiguration':
            uit['limits'].append({**basis, 'limit': x.get('limit')})
        elif o == 'deviceEnrollmentWindowsHelloForBusinessConfiguration':
            uit['whfb'] = {**basis, **{k: x.get(k) for k in ('state', 'pinMinimumLength', 'pinMaximumLength', 'pinUppercaseCharactersUsage', 'pinLowercaseCharactersUsage',
                                                            'pinSpecialCharactersUsage', 'securityDeviceRequired', 'unlockWithBiometricsEnabled',
                                                            'enhancedBiometricsState', 'pinExpirationInDays', 'pinPreviousBlockCount', 'remotePassportEnabled',
                                                            'securityKeyForSignIn', 'enhancedSignInSecurity')}}
        elif o == 'windows10EnrollmentCompletionPageConfiguration':
            uit['esp'].append({**basis, **{k: x.get(k) for k in ('showInstallationProgress', 'blockDeviceSetupRetryByUser', 'allowDeviceResetOnInstallFailure',
                                                                 'allowLogCollectionOnInstallFailure', 'customErrorMessage', 'installProgressTimeoutInMinutes',
                                                                 'allowDeviceUseOnInstallFailure', 'trackInstallProgressForAutopilotOnly',
                                                                 'disableUserStatusTrackingAfterFirstUser', 'installQualityUpdates')}})
    uit['restrictions'].sort(key=lambda x: (x['platform'], x['priority']))
    uit['limits'].sort(key=lambda x: x['priority'])
    uit['esp'].sort(key=lambda x: x['priority'])
    if isinstance(r['mdm'], dict):
        p = next((x for x in r['mdm'].get('value') or [] if x.get('id') == INTUNE_APP), None) or (r['mdm'].get('value') or [None])[0]
        if p:
            uit['mdm'] = {'id': p['id'], 'appliesTo': p.get('appliesTo') or 'none', 'groups': [{'id': x['id'], 'name': x.get('displayName') or x['id']}
                                                                                             for x in p.get('includedGroups') or []]}
    else:
        uit['errors']['mdm'] = str(r['mdm'])[:200]
    if isinstance(r['gplay'], dict):
        gp = r['gplay']
        uit['gplay'] = {'bound': gp.get('bindStatus') == 'boundAndValidated', 'status': gp.get('bindStatus') or '', 'owner': gp.get('ownerUserPrincipalName') or '',
                        'sync': gp.get('lastAppSyncDateTime') or '', 'fullyManaged': bool(gp.get('androidDeviceOwnerFullyManagedEnrollmentEnabled'))}
    else:
        uit['errors']['gplay'] = str(r['gplay'])[:200]
    if isinstance(r['aprof'], list):
        uit['androidProfiles'] = [{'id': p['id'], 'name': p.get('displayName') or '', 'mode': p.get('enrollmentMode') or '', 'devices': p.get('enrolledDeviceCount') or 0,
                                   'token': bool(p.get('tokenValue')), 'expires': p.get('tokenExpirationDateTime') or '', 'created': p.get('createdDateTime') or ''}
                                  for p in r['aprof']]
    else:
        uit['errors']['android'] = str(r['aprof'])[:200]
    return uit


@api('in.enroll')
def in_enroll(c: Ctx, b: dict) -> dict:
    return _probeer(c, lambda: c.t.cache('in.inschrijving', lambda: _inschrijving(c), VERS, bool(b.get('fresh'))))


def _patch_conf(c: Ctx, cid: str, odata: str, velden: dict) -> None:
    try:
        c.g.patch(f'{BETA}/deviceManagement/deviceEnrollmentConfigurations/{cid}', {'@odata.type': odata, **velden})
    except ApiFout as e:
        raise _fout(e)


WHFB_VELDEN = {'state', 'pinMinimumLength', 'pinMaximumLength', 'pinUppercaseCharactersUsage', 'pinLowercaseCharactersUsage', 'pinSpecialCharactersUsage',
               'securityDeviceRequired', 'unlockWithBiometricsEnabled', 'enhancedBiometricsState', 'pinExpirationInDays', 'pinPreviousBlockCount',
               'remotePassportEnabled', 'securityKeyForSignIn'}
ESP_VELDEN = {'showInstallationProgress', 'blockDeviceSetupRetryByUser', 'allowDeviceResetOnInstallFailure', 'allowLogCollectionOnInstallFailure',
              'customErrorMessage', 'installProgressTimeoutInMinutes', 'allowDeviceUseOnInstallFailure', 'trackInstallProgressForAutopilotOnly',
              'disableUserStatusTrackingAfterFirstUser'}


@api('in.whfb.set')
def in_whfb_set(c: Ctx, b: dict) -> dict:
    v = {k: b['values'][k] for k in WHFB_VELDEN if k in (b.get('values') or {})}
    if v.get('pinMinimumLength') and int(v['pinMinimumLength']) < 4:
        raise ApiFout('De pincode moet minimaal 4 tekens zijn.')
    _patch_conf(c, b['id'], '#microsoft.graph.deviceEnrollmentWindowsHelloForBusinessConfiguration', v)
    c.L('Windows Hello for Business bijgewerkt: ' + {'enabled': 'ingeschakeld', 'disabled': 'uitgeschakeld', 'notConfigured': 'niet geconfigureerd'}.get(v.get('state'), 'instellingen gewijzigd') + '.')
    return {}


@api('in.esp.set')
def in_esp_set(c: Ctx, b: dict) -> dict:
    v = {k: b['values'][k] for k in ESP_VELDEN if k in (b.get('values') or {})}
    _patch_conf(c, b['id'], '#microsoft.graph.windows10EnrollmentCompletionPageConfiguration', v)
    c.L(f"Inschrijvingsstatuspagina '{b.get('name', '')}' bijgewerkt.")
    return {}


@api('in.restrict.set')
def in_restrict_set(c: Ctx, b: dict) -> dict:
    """Platformbeperking: platform toestaan/blokkeren, persoonlijke apparaten blokkeren, min./max. versie."""
    r = {'platformBlocked': bool(b.get('blocked')), 'personalDeviceEnrollmentBlocked': bool(b.get('personalBlocked')),
         'osMinimumVersion': b.get('min') or None, 'osMaximumVersion': b.get('max') or None}
    veld = b['field']
    if veld not in ('windowsRestriction', 'androidRestriction', 'androidForWorkRestriction', 'iosRestriction', 'macOSRestriction', 'platformRestriction'):
        raise ApiFout('Onbekend platform.')
    _patch_conf(c, b['id'], b['odata'], {veld: r})
    naam = {'windows': 'Windows', 'android': 'Android-apparaatbeheerder', 'androidForWork': 'Android Enterprise (werkprofiel)', 'ios': 'iOS', 'mac': 'macOS'}.get(b.get('platform'), b.get('platform'))
    c.L(f"Inschrijvingsbeperking {naam}: {'geblokkeerd' if r['platformBlocked'] else 'toegestaan'}"
        + (', persoonlijke apparaten geblokkeerd' if r['personalDeviceEnrollmentBlocked'] else '') + '.')
    return {}


@api('in.limit.set')
def in_limit_set(c: Ctx, b: dict) -> dict:
    n = int(b.get('limit') or 0)
    if not 1 <= n <= 15:
        raise ApiFout('Kies een limiet van 1 tot 15 apparaten.')
    _patch_conf(c, b['id'], '#microsoft.graph.deviceEnrollmentLimitConfiguration', {'limit': n})
    c.L(f'Apparaatlimiet per gebruiker: {n}.')
    return {}


@api('in.mdm.set')
def in_mdm_set(c: Ctx, b: dict) -> dict:
    """Automatische Windows-inschrijving (MDM-gebruikersbereik): niemand, iedereen of geselecteerde groepen."""
    scope = b.get('appliesTo')
    if scope not in ('none', 'all', 'selected'):
        raise ApiFout('Kies niemand, iedereen of groepen.')
    pad = f"{BETA}/policies/mobileDeviceManagementPolicies/{b.get('id') or INTUNE_APP}"
    try:
        c.g.patch(pad, {'appliesTo': scope})
        if scope == 'selected':
            huidig = {x['id'] for x in (c.g.get(pad + '/includedGroups').get('value') or [])}
            nieuw = set(b.get('groups') or [])
            for gid in nieuw - huidig:
                c.g.post(pad + '/includedGroups/$ref', {'@odata.id': f'https://graph.microsoft.com/beta/groups/{gid}'})
            for gid in huidig - nieuw:
                c.g.delete(pad + f'/includedGroups/{gid}/$ref')
    except ApiFout as e:
        raise _fout(e)
    c.L('Automatische Windows-inschrijving (MDM): ' + {'none': 'niemand', 'all': 'alle gebruikers', 'selected': 'geselecteerde groepen'}[scope] + '.')
    return {}


ANDROID_MODUS = {'corporateOwnedFullyManaged': 'Volledig beheerd (zakelijk)', 'corporateOwnedDedicatedDevice': 'Toegewezen apparaat (kiosk)',
                 'corporateOwnedWorkProfile': 'Zakelijk met werkprofiel'}


@api('in.android.create')
def in_android_create(c: Ctx, b: dict) -> dict:
    modus = b.get('mode')
    if modus not in ANDROID_MODUS:
        raise ApiFout('Kies een soort inschrijving.')
    try:
        p = c.g.post(BETA + '/deviceManagement/androidDeviceOwnerEnrollmentProfiles',
                     {'displayName': b.get('name') or ANDROID_MODUS[modus], 'description': b.get('description') or '', 'enrollmentMode': modus,
                      'enrollmentTokenType': 'default'})
        c.g.post(f"{BETA}/deviceManagement/androidDeviceOwnerEnrollmentProfiles/{p['id']}/createToken", {'tokenValidityInSeconds': int(b.get('days') or 90) * 86400})
    except ApiFout as e:
        raise _fout(e)
    c.L(f"Android-inschrijvingsprofiel '{b.get('name') or ANDROID_MODUS[modus]}' aangemaakt.")
    return {'id': p['id']}


@api('in.android.qr')
def in_android_qr(c: Ctx, b: dict) -> dict:
    """QR-code en token van een Android-inschrijvingsprofiel (alleen getoond, niet bewaard)."""
    try:
        p = c.g.get(f"{BETA}/deviceManagement/androidDeviceOwnerEnrollmentProfiles/{b['id']}?$select=id,displayName,tokenValue,tokenExpirationDateTime,qrCodeImage,enrollmentMode")
    except ApiFout as e:
        raise _fout(e)
    qr = p.get('qrCodeImage') or {}
    return {'name': p.get('displayName') or '', 'token': p.get('tokenValue') or '', 'expires': p.get('tokenExpirationDateTime') or '',
            'qr': f"data:{qr.get('type') or 'image/png'};base64,{qr.get('value')}" if qr.get('value') else ''}


@api('in.android.token')
def in_android_token(c: Ctx, b: dict) -> dict:
    pad = f"{BETA}/deviceManagement/androidDeviceOwnerEnrollmentProfiles/{b['id']}"
    try:
        if b.get('revoke'):
            c.g.post(pad + '/revokeToken', {})
        else:
            c.g.post(pad + '/createToken', {'tokenValidityInSeconds': int(b.get('days') or 90) * 86400})
    except ApiFout as e:
        raise _fout(e)
    c.L(f"Android-inschrijvingstoken {'ingetrokken' if b.get('revoke') else 'vernieuwd'} ({b.get('name', '')}).")
    return {}


@api('in.android.delete')
def in_android_delete(c: Ctx, b: dict) -> dict:
    try:
        c.g.delete(f"{BETA}/deviceManagement/androidDeviceOwnerEnrollmentProfiles/{b['id']}")
    except ApiFout as e:
        raise _fout(e)
    c.L(f"Android-inschrijvingsprofiel '{b.get('name', '')}' verwijderd.")
    return {}
