"""Compliance: Secure Score (met acties en directe aanpassingen), apparaten (updates en BitLocker) en gebruikers (MFA e.d.).

Alles wordt live opgehaald en alleen in het geheugen gehouden. Rechten: SecurityEvents.Read.All (Secure Score),
DeviceManagementManagedDevices, BitlockerKey, UserAuthenticationMethod, AuditLog, Policy.Read.All en Exchange.
"""
from __future__ import annotations

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from .clients import NULL, ApiFout, parallel
from .context import Ctx, api, VERS

NU = lambda: datetime.now(timezone.utc)   # noqa: E731


def _dt(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')) if s else None
    except ValueError:
        return None


def _tekst(h: str) -> str:
    t = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</div>', '\n', h or '')
    t = re.sub(r'(?i)<li[^>]*>', '• ', t)
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+', ' ', t)).strip()


# =====================================================================================================
# Secure Score
# =====================================================================================================

CATEGORIE = {'Identity': 'Identiteit', 'Data': 'Gegevens', 'Device': 'Apparaten', 'Apps': 'Apps', 'Infrastructure': 'Infrastructuur'}
IMPACT_NL = {
    'Low': 'Laag: gebruikers merken er weinig of niets van.',
    'Moderate': 'Gemiddeld: sommige gebruikers merken een verandering in hoe ze werken of inloggen.',
    'High': 'Hoog: gebruikers merken dit direct; communiceer vooraf en test eerst met een kleine groep.',
}
KOSTEN_NL = {'Low': 'Weinig werk', 'Moderate': 'Gemiddeld werk', 'High': 'Veel werk'}


def _exo(cmdlet: str, **p: Any) -> Callable[[Ctx], None]:
    return lambda c: c.x.run(cmdlet, **p) and None


def _waarde(cmdlet: str, identity: str, veld: str) -> Callable[[Ctx, dict], Any]:
    """Huidige instelling lezen (met een gedeelde cache binnen één opvraging)."""
    def lees(c: Ctx, cache: dict) -> Any:
        k = (cmdlet, identity)
        if k not in cache:
            r = c.x.run(cmdlet, **({'Identity': identity} if identity else {}))
            cache[k] = r[0] if r else {}
        return cache[k].get(veld)
    return lees


def _is(lees, verwacht) -> Callable[[Ctx, dict], bool]:
    return lambda c, cache: str(lees(c, cache)).lower() == str(verwacht).lower()


def _wachtwoord_verloopt_nooit(c: Ctx) -> None:
    doms = c.g.all('/domains?$select=id,isVerified,authenticationType')
    for d in doms:
        if d.get('isVerified') and d.get('authenticationType') == 'Managed':
            c.g.patch(f"/domains/{d['id']}", {'passwordValidityPeriodInDays': 2147483647})


def _wachtwoord_check(c: Ctx, cache: dict) -> bool:
    doms = c.g.all('/domains?$select=id,isVerified,authenticationType,passwordValidityPeriodInDays')
    return all(int(d.get('passwordValidityPeriodInDays') or 0) >= 2147483647
               for d in doms if d.get('isVerified') and d.get('authenticationType') == 'Managed')


def _toestemming_uit(c: Ctx) -> None:
    p = c.g.get('/policies/authorizationPolicy')
    huidig = ((p.get('defaultUserRolePermissions') or {}).get('permissionGrantPoliciesAssigned')) or []
    nieuw = [x for x in huidig if not str(x).startswith('ManagePermissionGrantsForSelf.')]
    c.g.patch('/policies/authorizationPolicy', {'defaultUserRolePermissions': {'permissionGrantPoliciesAssigned': nieuw}})


def _toestemming_check(c: Ctx, cache: dict) -> bool:
    p = c.g.get('/policies/authorizationPolicy')
    huidig = ((p.get('defaultUserRolePermissions') or {}).get('permissionGrantPoliciesAssigned')) or []
    return not any(str(x).startswith('ManagePermissionGrantsForSelf.') for x in huidig)


_SPAM = 'Get-HostedContentFilterPolicy'
_PHISH = 'Office365 AntiPhish Default'

# Aanpassingen die de app direct kan doen. Sleutel = controlName van Microsoft (kleine letters).
# 'wat' = wat er verandert, 'nadeel' = negatieve impact voor gebruikers/beheer. 'exo' = vraagt Exchange.
OPLOSSINGEN: dict[str, dict] = {
    'mdo_autoforwardingmode': {
        'exo': True, 'wat': 'Automatisch doorsturen van e-mail naar externe adressen wordt geblokkeerd (uitgaand spambeleid "Default": AutoForwardingMode Off).',
        'nadeel': 'Bestaande doorstuurregels en postvak-doorsturingen naar externe adressen (bijv. naar een privé-Gmail of een externe boekhouder) werken niet meer; '
                  'het doorsturen wordt geweigerd en de gebruiker die doorstuurt krijgt een onbestelbaarheidsbericht (5.7.520). De mail zelf komt wel in het eigen postvak aan. Controleer eerst Compliance > Gebruikers en MFA > Doorsturen.',
        'fn': _exo('Set-HostedOutboundSpamFilterPolicy', Identity='Default', AutoForwardingMode='Off'),
        'check': _is(_waarde('Get-HostedOutboundSpamFilterPolicy', 'Default', 'AutoForwardingMode'), 'Off')},
    'exo_storageproviderrestricted': {
        'exo': True, 'wat': 'In Outlook op het web kunnen gebruikers geen externe opslag (Dropbox, Google Drive e.d.) meer koppelen.',
        'nadeel': 'Gebruikers die bijlagen vanuit Dropbox/Google Drive in Outlook op het web gebruiken, moeten bestanden eerst downloaden of OneDrive gebruiken.',
        'fn': _exo('Set-OwaMailboxPolicy', Identity='OwaMailboxPolicy-Default', AdditionalStorageProvidersAvailable=False),
        'check': _is(_waarde('Get-OwaMailboxPolicy', 'OwaMailboxPolicy-Default', 'AdditionalStorageProvidersAvailable'), False)},
    'exo_mailtipsenabled': {
        'exo': True, 'wat': 'E-mailtips gaan aan: waarschuwingen bij externe ontvangers, grote groepen en afwezige collega\'s.',
        'nadeel': 'Vrijwel geen: gebruikers zien extra meldingen boven een bericht (bijv. "deze ontvanger is extern").',
        'fn': _exo('Set-OrganizationConfig', MailTipsAllTipsEnabled=True, MailTipsExternalRecipientsTipsEnabled=True,
                   MailTipsGroupMetricsEnabled=True, MailTipsLargeAudienceThreshold=25),
        'check': _is(_waarde('Get-OrganizationConfig', '', 'MailTipsExternalRecipientsTipsEnabled'), True)},
    'exo_oauth2clientprofileenabled': {
        'exo': True, 'wat': 'Moderne verificatie (OAuth 2.0) voor Exchange Online gaat aan.',
        'nadeel': 'Zeer oude Outlook-versies (2010 en ouder) en apps die alleen basisverificatie kennen, kunnen niet meer verbinden.',
        'fn': _exo('Set-OrganizationConfig', OAuth2ClientProfileEnabled=True),
        'check': _is(_waarde('Get-OrganizationConfig', '', 'OAuth2ClientProfileEnabled'), True)},
    'exo_mailboxaudit': {
        'exo': True, 'wat': 'Postvak-auditing gaat aan voor de hele organisatie (wie opent, verplaatst of verwijdert berichten).',
        'nadeel': 'Geen merkbaar effect voor gebruikers; de auditgegevens worden 90 dagen bewaard in Microsoft Purview.',
        'fn': _exo('Set-OrganizationConfig', AuditDisabled=False),
        'check': _is(_waarde('Get-OrganizationConfig', '', 'AuditDisabled'), False)},
    'mdo_commonattachmentsfilter': {
        'exo': True, 'wat': 'Het filter voor gevaarlijke bijlagen (o.a. .exe, .js, .iso, .vbs) gaat aan in het standaard antimalwarebeleid.',
        'nadeel': 'Mails met zulke bijlagen komen in quarantaine. Leveranciers die bijvoorbeeld scripts of installatiebestanden mailen, komen niet meer aan.',
        'fn': _exo('Set-MalwareFilterPolicy', Identity='Default', EnableFileFilter=True),
        'check': _is(_waarde('Get-MalwareFilterPolicy', 'Default', 'EnableFileFilter'), True)},
    'mdo_zapspam': {
        'exo': True, 'wat': 'Zero-hour auto purge (ZAP) voor spam: al afgeleverde spam wordt achteraf alsnog verplaatst.',
        'nadeel': 'Een bericht kan na aflevering uit het Postvak IN verdwijnen (naar Ongewenste e-mail) als het later als spam wordt herkend.',
        'fn': _exo('Set-HostedContentFilterPolicy', Identity='Default', SpamZapEnabled=True),
        'check': _is(_waarde(_SPAM, 'Default', 'SpamZapEnabled'), True)},
    'mdo_zapphish': {
        'exo': True, 'wat': 'Zero-hour auto purge (ZAP) voor phishing: al afgeleverde phishing wordt achteraf in quarantaine gezet.',
        'nadeel': 'Een bericht kan na aflevering verdwijnen als Microsoft het later als phishing herkent (zelden een vals alarm).',
        'fn': _exo('Set-HostedContentFilterPolicy', Identity='Default', PhishZapEnabled=True),
        'check': _is(_waarde(_SPAM, 'Default', 'PhishZapEnabled'), True)},
    'mdo_highconfidencespamaction': {
        'exo': True, 'wat': 'Spam met hoge zekerheid gaat naar quarantaine in plaats van de map Ongewenste e-mail.',
        'nadeel': 'Gebruikers zien deze berichten niet meer in Ongewenste e-mail; een vals alarm moet uit quarantaine worden vrijgegeven.',
        'fn': _exo('Set-HostedContentFilterPolicy', Identity='Default', HighConfidenceSpamAction='Quarantine'),
        'check': _is(_waarde(_SPAM, 'Default', 'HighConfidenceSpamAction'), 'Quarantine')},
    'mdo_highconfidencephishaction': {
        'exo': True, 'wat': 'Phishing met hoge zekerheid gaat altijd naar quarantaine.',
        'nadeel': 'Nauwelijks: zulke berichten zijn bijna altijd echt kwaadaardig.',
        'fn': _exo('Set-HostedContentFilterPolicy', Identity='Default', HighConfidencePhishAction='Quarantine'),
        'check': _is(_waarde(_SPAM, 'Default', 'HighConfidencePhishAction'), 'Quarantine')},
    'mdo_phishspamaction': {
        'exo': True, 'wat': 'Berichten die als phishing zijn herkend gaan naar quarantaine.',
        'nadeel': 'Een vals alarm komt in quarantaine in plaats van Ongewenste e-mail en moet worden vrijgegeven.',
        'fn': _exo('Set-HostedContentFilterPolicy', Identity='Default', PhishSpamAction='Quarantine'),
        'check': _is(_waarde(_SPAM, 'Default', 'PhishSpamAction'), 'Quarantine')},
    'mdo_bulkthreshold': {
        'exo': True, 'wat': 'De drempel voor bulkmail (nieuwsbrieven, marketing) gaat naar 6: meer bulkmail gaat naar Ongewenste e-mail.',
        'nadeel': 'Sommige gewenste nieuwsbrieven komen in Ongewenste e-mail terecht; gebruikers moeten afzenders eventueel als veilig markeren.',
        'fn': _exo('Set-HostedContentFilterPolicy', Identity='Default', BulkThreshold=6),
        'check': lambda c, cache: int(_waarde(_SPAM, 'Default', 'BulkThreshold')(c, cache) or 9) <= 6},
    'mdo_phisthresholdlevel': {
        'exo': True, 'wat': 'Antiphishing wordt strenger (drempel 2 "Agressief") in het standaard antiphishingbeleid.',
        'nadeel': 'Iets meer kans dat een echte mail als phishing wordt gezien en in quarantaine of Ongewenste e-mail komt.',
        'fn': _exo('Set-AntiPhishPolicy', Identity=_PHISH, PhishThresholdLevel=2),
        'check': lambda c, cache: int(_waarde('Get-AntiPhishPolicy', _PHISH, 'PhishThresholdLevel')(c, cache) or 1) >= 2},
    'mdo_mailboxintelligence': {
        'exo': True, 'wat': 'Postvakintelligentie gaat aan: Microsoft leert met wie iedereen normaal mailt en herkent nagemaakte afzenders beter.',
        'nadeel': 'Vrijwel geen merkbaar effect voor gebruikers.',
        'fn': _exo('Set-AntiPhishPolicy', Identity=_PHISH, EnableMailboxIntelligence=True),
        'check': _is(_waarde('Get-AntiPhishPolicy', _PHISH, 'EnableMailboxIntelligence'), True)},
    'mdo_spoofintelligence': {
        'exo': True, 'wat': 'Spoofintelligentie gaat aan: vervalste afzenders (spoofing) worden herkend en tegengehouden.',
        'nadeel': 'Diensten die namens jullie domein mailen zonder juiste SPF/DKIM (bijv. een printer of webshop) kunnen worden tegengehouden.',
        'fn': _exo('Set-AntiPhishPolicy', Identity=_PHISH, EnableSpoofIntelligence=True),
        'check': _is(_waarde('Get-AntiPhishPolicy', _PHISH, 'EnableSpoofIntelligence'), True)},
    'pwagepolicynew': {
        'exo': False, 'wat': 'Wachtwoorden verlopen niet meer (advies van Microsoft en NIST zolang MFA aanstaat).',
        'nadeel': 'Gebruikers hoeven hun wachtwoord niet meer periodiek te wijzigen. Alleen veilig in combinatie met MFA voor iedereen.',
        'fn': _wachtwoord_verloopt_nooit, 'check': _wachtwoord_check},
    'integratedapps': {
        'exo': False, 'wat': 'Gebruikers mogen niet langer zelf toestemming geven aan apps van derden (bijv. "Aanmelden met Microsoft" bij een online tool).',
        'nadeel': 'Als een gebruiker een nieuwe app wil koppelen, moet een beheerder toestemming geven. Bestaande toestemmingen blijven werken. '
                  'Zet eventueel een beheerdersgoedkeuringsaanvraag aan in Entra zodat gebruikers erom kunnen vragen.',
        'fn': _toestemming_uit, 'check': _toestemming_check},
}
OPLOSSINGEN['mdo_phishthresholdlevel'] = OPLOSSINGEN['mdo_phisthresholdlevel']   # beide schrijfwijzen komen voor


def _secure(c: Ctx) -> dict:
    g = c.g
    def ophalen():
        return parallel({'score': lambda: g.get('/security/secureScores?$top=30'),
                         'prof': lambda: g.all('/security/secureScoreControlProfiles?$top=500')})

    def geweigerd(x) -> ApiFout | None:
        e = next((x[k] for k in ('score', 'prof') if isinstance(x[k], Exception)), None)
        if e is not None and not (isinstance(e, ApiFout) and e.status in (401, 403)):
            raise e
        return e

    r = ophalen()
    e = geweigerd(r)
    if e is not None:
        # Recht ontbreekt mogelijk nog in de koppeling: nu controleren/aanvullen en opnieuw proberen
        stand = c.t.rechten_nu()
        if stand == 'aangevuld':
            for wacht in (5, 10, 20):
                time.sleep(wacht)
                r = ophalen()
                e = geweigerd(r)
                if e is None:
                    break
        if e is not None:
            ms = str(e)[:250]
            if stand == 'aangevuld':
                raise ApiFout('De koppeling met deze klant is zojuist aangevuld met het recht voor Secure Score. Microsoft heeft soms een paar minuten nodig '
                              f'om dat door te voeren; probeer het zo opnieuw. (Melding van Microsoft: {ms})')
            if stand == 'compleet':
                raise ApiFout('De app heeft het recht voor Secure Score, maar je GDAP-rol bij deze klant geeft geen toegang. Secure Score vraagt een van de rollen '
                              'Security Reader, Global Reader of Security Administrator in de GDAP-relatie (en toegewezen aan jouw groep). '
                              f'(Melding van Microsoft: {ms})')
            raise ApiFout(f'Secure Score kan niet worden gelezen en de koppeling kon niet worden gecontroleerd. (Melding van Microsoft: {ms})')
    reeks = r['score'].get('value') or []
    if not reeks:
        raise ApiFout('Microsoft heeft voor deze klant (nog) geen Secure Score berekend. Dit gebeurt binnen 24 uur na het aanzetten van een dienst.')
    nu = reeks[0]
    totaal = float(nu.get('maxScore') or 0) or 1.0
    huidig = float(nu.get('currentScore') or 0)
    profielen = {str(p.get('id') or '').lower(): p for p in r['prof'] if not p.get('deprecated')}
    stand = {str(s.get('controlName') or '').lower(): s for s in nu.get('controlScores') or []}
    exo_ok = c.exo_ok

    acties = []
    for key, p in profielen.items():
        s = stand.get(key)
        mx = float(p.get('maxScore') or 0)
        if mx <= 0:
            continue
        sc = float((s or {}).get('score') or 0)
        laatste = (p.get('controlStateUpdates') or [{}])[-1] if p.get('controlStateUpdates') else {}
        status = str(laatste.get('state') or 'Default')   # Default, Ignored, ThirdParty, Reviewed
        winst = max(0.0, mx - sc)
        opl = OPLOSSINGEN.get(key)
        acties.append({
            'id': p.get('id'), 'title': p.get('title') or p.get('id'), 'category': CATEGORIE.get(p.get('controlCategory'), p.get('controlCategory') or ''),
            'service': p.get('service') or '', 'score': round(sc, 2), 'max': mx, 'gain': round(winst, 2), 'gainPct': round(winst / totaal * 100, 2),
            'done': winst <= 0.001, 'state': status, 'rank': p.get('rank') or 999, 'tier': p.get('tier') or '',
            'userImpact': p.get('userImpact') or '', 'impactNl': IMPACT_NL.get(p.get('userImpact') or '', ''),
            'cost': KOSTEN_NL.get(p.get('implementationCost') or '', p.get('implementationCost') or ''),
            'remediation': _tekst(p.get('remediation') or ''), 'remediationImpact': _tekst(p.get('remediationImpact') or ''),
            'actionUrl': p.get('actionUrl') or '', 'threats': p.get('threats') or [],
            'implementation': (s or {}).get('implementationStatus') or '',
            'fix': None if not opl else {'what': opl['wat'], 'impact': opl['nadeel'], 'needsExo': opl['exo'], 'possible': exo_ok or not opl['exo'], 'applied': None},
        })

    # Zijn de directe aanpassingen misschien al gedaan (Microsoft werkt de score pas na 24-48 uur bij)?
    cache: dict = {}
    te_check = [a for a in acties if a['fix'] and not a['done'] and a['fix']['possible']]

    def check(a: dict):
        try:
            return bool(OPLOSSINGEN[a['id'].lower()]['check'](c, cache))
        except Exception:  # noqa: BLE001
            return None
    with ThreadPoolExecutor(max_workers=6) as ex:
        for a, v in zip(te_check, ex.map(check, te_check)):
            a['fix']['applied'] = v

    acties.sort(key=lambda a: (a['done'], a['state'] in ('Ignored', 'ThirdParty'), -a['gain'], a['rank']))
    geschiedenis = [{'date': str(x.get('createdDateTime') or '')[:10],
                     'pct': round(float(x.get('currentScore') or 0) / (float(x.get('maxScore') or 0) or 1) * 100, 1)} for x in reversed(reeks)]
    vergelijk = [{'type': v.get('basis'), 'pct': round(float(v.get('averageScore') or 0) / totaal * 100, 1)}
                 for v in nu.get('averageComparativeScores') or [] if v.get('basis') in ('AllTenants', 'TotalSeats')]
    return {'current': round(huidig, 2), 'max': totaal, 'pct': round(huidig / totaal * 100, 1), 'date': str(nu.get('createdDateTime') or ''),
            'actions': acties, 'history': geschiedenis, 'compare': vergelijk, 'exo': exo_ok,
            'portal': 'https://security.microsoft.com/securescore?viewid=actions'}


@api('ss.list')
def ss_list(c: Ctx, b: dict) -> dict:
    return c.t.cache('securescore', lambda: _secure(c), VERS, bool(b.get('fresh')))


@api('ss.apply')
def ss_apply(c: Ctx, b: dict) -> dict:
    sleutel = str(b.get('id') or '').lower()
    opl = OPLOSSINGEN.get(sleutel)
    if not opl:
        raise ApiFout('Deze actie kan de app niet direct toepassen; gebruik de link naar het beheercentrum.')
    opl['fn'](c)
    c.t.weg('securescore')
    c.L(f"Secure Score-actie toegepast ({b.get('id')}): {opl['wat']} Microsoft werkt de score binnen 24-48 uur bij.")
    return {}


# =====================================================================================================
# Apparaten: updates en BitLocker
# =====================================================================================================

# build: (naam, einde ondersteuning Home/Pro, einde Enterprise/Education)
WINDOWS = {
    26200: ('Windows 11 25H2', '2027-10-12', '2028-10-10'),
    26100: ('Windows 11 24H2', '2026-10-13', '2027-10-12'),
    22631: ('Windows 11 23H2', '2025-11-11', '2026-11-10'),
    22621: ('Windows 11 22H2', '2024-10-08', '2025-10-14'),
    22000: ('Windows 11 21H2', '2023-10-10', '2024-10-08'),
    19045: ('Windows 10 22H2', '2025-10-14', '2025-10-14'),
    19044: ('Windows 10 21H2', '2023-06-13', '2024-06-11'),
    19043: ('Windows 10 21H1', '2022-12-13', '2022-12-13'),
    19042: ('Windows 10 20H2', '2022-05-10', '2023-05-09'),
}


def _nl(iso: str) -> str:
    j, m, d = iso.split('-')
    return f'{int(d)}-{int(m)}-{j}'


def _versie(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r'\d+', str(s or ''))[:4])


def _os_soort(os_: str) -> str:
    o = (os_ or '').lower()
    if o.startswith('windows'):
        return 'Windows'
    if 'mac' in o:
        return 'macOS'
    if o in ('ios', 'ipados') or 'iphone' in o or 'ipad' in o:
        return 'iOS'
    if 'android' in o:
        return 'Android'
    return os_ or 'Onbekend'


def _apparaten(c: Ctx) -> dict:
    g = c.g
    r = parallel({
        'intune': lambda: g.all('/deviceManagement/managedDevices?$select=id,deviceName,operatingSystem,osVersion,complianceState,isEncrypted,'
                                'userPrincipalName,userDisplayName,lastSyncDateTime,azureADDeviceId,model,manufacturer,managedDeviceOwnerType&$top=500'),
        'entra': lambda: g.all('/devices?$select=id,deviceId,displayName,operatingSystem,operatingSystemVersion,approximateLastSignInDateTime,'
                               'trustType,isManaged,isCompliant,accountEnabled&$top=999'),
        'keys': lambda: g.all('/informationProtection/bitlocker/recoveryKeys?$select=deviceId'),
    })
    intune = r['intune'] if not isinstance(r['intune'], Exception) else None
    entra = r['entra'] if not isinstance(r['entra'], Exception) else []
    sleutels = {str(k.get('deviceId') or '').lower() for k in r['keys']} if not isinstance(r['keys'], Exception) else None
    if intune is None and isinstance(r['entra'], Exception):
        raise r['entra']
    nu = NU()
    lijst, gezien = [], set()
    entra_per = {str(e.get('deviceId') or '').lower(): e for e in entra}
    for d in intune or []:
        aad = str(d.get('azureADDeviceId') or '').lower()
        gezien.add(aad)
        e = entra_per.get(aad) or {}
        lijst.append({'id': d['id'], 'name': d.get('deviceName') or '', 'os': d.get('operatingSystem') or '', 'osv': d.get('osVersion') or '',
                      'user': d.get('userDisplayName') or '', 'upn': d.get('userPrincipalName') or '', 'last': d.get('lastSyncDateTime') or '',
                      'comp': d.get('complianceState') or '', 'enc': d.get('isEncrypted'), 'aad': aad, 'intune': True,
                      'model': ' '.join(x for x in (d.get('manufacturer'), d.get('model')) if x), 'owner': d.get('managedDeviceOwnerType') or '',
                      'entraId': e.get('id') or '', 'enabled': e.get('accountEnabled') is not False})
    for e in entra:
        aad = str(e.get('deviceId') or '').lower()
        if aad in gezien:
            continue
        lijst.append({'id': e['id'], 'name': e.get('displayName') or '', 'os': e.get('operatingSystem') or '', 'osv': e.get('operatingSystemVersion') or '',
                      'user': '', 'upn': '', 'last': e.get('approximateLastSignInDateTime') or '', 'comp': 'compliant' if e.get('isCompliant') else '',
                      'enc': None, 'aad': aad, 'intune': False, 'model': '', 'entraId': e['id'], 'enabled': e.get('accountEnabled') is not False, 'owner': {'AzureAd': 'Entra-joined', 'ServerAd': 'Hybride',
                                                                                        'Workplace': 'Geregistreerd'}.get(e.get('trustType'), e.get('trustType') or '')})

    # Hoogste versie per OS (en per Windows-build) in deze tenant, als maatstaf voor "updates achter"
    hoogste: dict[str, tuple] = {}
    ubr: dict[int, int] = {}
    for d in lijst:
        d['kind'] = _os_soort(d['os'])
        v = _versie(d['osv'])
        d['_v'] = v
        if d['kind'] == 'Windows' and len(v) >= 4:
            ubr[v[2]] = max(ubr.get(v[2], 0), v[3])
        elif v:
            hoogste[d['kind']] = max(hoogste.get(d['kind'], ()), v)
    nieuwste_build = max([b for b in WINDOWS] + list(ubr))

    for d in lijst:
        v, last = d.pop('_v'), _dt(d['last'])
        d['days'] = (nu - last).days if last else None
        d['stale'] = d['days'] is None or d['days'] > 30
        d['release'], d['support'], d['supportEnt'] = '', '', ''
        if d['kind'] == 'Windows' and len(v) >= 3:
            build = v[2]
            info = WINDOWS.get(build)
            if info:
                d['release'], d['support'], d['supportEnt'] = info
            elif build > max(WINDOWS):
                d['release'] = f'Windows 11 (build {build}, nieuwer)'
            else:
                d['release'] = f'Windows (build {build})'
            vandaag = nu.date().isoformat()
            if (info and info[1] < vandaag) or (not info and build < min(WINDOWS)):
                d['status'] = 'unsupported'
                d['reason'] = (f'{d["release"]} krijgt geen beveiligingsupdates meer (Home/Pro sinds {_nl(info[1])}'
                               + (f'; Enterprise/Education nog tot {_nl(info[2])}' if info and info[2] >= vandaag else '') + ').') if info else 'Deze Windows-versie wordt niet meer ondersteund.'
            elif len(v) >= 4 and v[3] < ubr.get(build, 0):
                d['status'] = 'behind'
                d['reason'] = f'Patchniveau {build}.{v[3]}; het nieuwste in deze tenant is {build}.{ubr[build]}.'
            else:
                d['status'] = 'ok'
                d['reason'] = 'Nieuwste patchniveau in deze tenant.' + (' Een nieuwere Windows-versie is beschikbaar.' if build < nieuwste_build and build in WINDOWS else '')
            d['latest'] = f'{build}.{ubr.get(build, 0)}' if build in ubr else ''
        elif v:
            top = hoogste.get(d['kind'], ())
            d['status'] = 'behind' if v < top else 'ok'
            d['reason'] = (f"Nieuwste {d['kind']}-versie in deze tenant is {'.'.join(map(str, top))}." if v < top else 'Nieuwste versie in deze tenant.')
            d['latest'] = '.'.join(map(str, top))
        else:
            d['status'], d['reason'], d['latest'] = 'unknown', 'Versie onbekend.', ''
        # BitLocker / versleuteling
        if d['kind'] == 'Windows':
            d['key'] = None if sleutels is None else (d['aad'] in sleutels)
            d['bitlocker'] = 'on' if d['enc'] else ('off' if d['enc'] is False else ('key' if d['key'] else 'unknown'))
        else:
            d['key'] = None
            d['bitlocker'] = 'on' if d['enc'] else ('off' if d['enc'] is False else 'unknown')
    lijst.sort(key=lambda d: ({'unsupported': 0, 'behind': 1, 'unknown': 2, 'ok': 3}[d['status']], d['name'].lower()))
    uit_gezet = [d for d in lijst if not d['enabled'] and not d['intune']]
    lijst = [d for d in lijst if d['enabled'] or d['intune']]
    return {'devices': lijst, 'disabled': uit_gezet, 'intune': intune is not None, 'keys': sleutels is not None,
            'builds': [{'build': b, 'name': WINDOWS[b][0], 'support': WINDOWS[b][1], 'supportEnt': WINDOWS[b][2], 'latest': ubr.get(b)} for b in sorted(WINDOWS, reverse=True)],
            'intuneError': '' if intune is not None else str(r['intune'])}


@api('cd.devices')
def cd_devices(c: Ctx, b: dict) -> dict:
    return c.t.cache('compliance-apparaten', lambda: _apparaten(c), VERS, bool(b.get('fresh')))


# =====================================================================================================
# Gebruikers: MFA, beheerders, beleid, doorsturen en gasten
# =====================================================================================================

METHODE = {
    'microsoftAuthenticatorPush': ('Authenticator-app (melding)', True), 'microsoftAuthenticatorPasswordless': ('Authenticator (zonder wachtwoord)', True),
    'softwareOneTimePasscode': ('Authenticator-app (code)', True), 'hardwareOneTimePasscode': ('Hardwaretoken (code)', True),
    'fido2': ('Beveiligingssleutel (FIDO2)', True), 'passKeyDeviceBound': ('Passkey', True), 'passKeyDeviceBoundAuthenticator': ('Passkey (Authenticator)', True),
    'passKeyDeviceBoundWindowsHello': ('Passkey (Windows Hello)', True), 'windowsHelloForBusiness': ('Windows Hello for Business', True),
    'mobilePhone': ('Sms/bellen (mobiel)', False), 'alternateMobilePhone': ('Sms/bellen (2e mobiel)', False), 'officePhone': ('Bellen (kantoor)', False),
    'email': ('E-mail (alleen wachtwoordherstel)', None), 'securityQuestion': ('Beveiligingsvragen', None), 'temporaryAccessPass': ('Tijdelijke toegangspas', None),
    # namen uit /users/{id}/authentication/methods
    'microsoftAuthenticatorAuthenticationMethod': ('Authenticator-app', True), 'softwareOathAuthenticationMethod': ('Authenticator-app (code)', True),
    'fido2AuthenticationMethod': ('Beveiligingssleutel (FIDO2)', True), 'windowsHelloForBusinessAuthenticationMethod': ('Windows Hello for Business', True),
    'platformCredentialAuthenticationMethod': ('Platform-referentie (Mac)', True), 'phoneAuthenticationMethod': ('Sms/bellen', False),
    'emailAuthenticationMethod': ('E-mail (alleen wachtwoordherstel)', None), 'temporaryAccessPassAuthenticationMethod': ('Tijdelijke toegangspas', None),
}
GLOBAL_ADMIN = '62e90394-69f5-4237-9190-012177145e10'


def _mfa_stand(methoden: list[str]) -> str:
    sterk = [m for m in methoden if METHODE.get(m, ('', None))[1] is True]
    zwak = [m for m in methoden if METHODE.get(m, ('', None))[1] is False]
    return 'strong' if sterk else ('weak' if zwak else 'none')


def _ca(beleid: list[dict]) -> dict:
    regels, alle, admins, legacy = [], False, False, False
    mfa_rollen: set[str] = set()
    for p in beleid:
        cond = p.get('conditions') or {}
        u = cond.get('users') or {}
        apps = cond.get('applications') or {}
        grant = p.get('grantControls') or {}
        ctrl = [str(x).lower() for x in grant.get('builtInControls') or []]
        mfa = 'mfa' in ctrl or bool(grant.get('authenticationStrength'))
        blok = 'block' in ctrl
        aan = p.get('state') == 'enabled'
        iedereen = 'All' in (u.get('includeUsers') or [])
        alle_apps = 'All' in (apps.get('includeApplications') or [])
        rollen = bool(u.get('includeRoles'))
        oud = bool({'exchangeActiveSync', 'other'} & set(cond.get('clientAppTypes') or []))
        if aan and mfa and iedereen and alle_apps:
            alle = True
        if aan and mfa and (rollen or iedereen):
            admins = True
        if aan and mfa and rollen:
            mfa_rollen.update(u.get('includeRoles') or [])
        if aan and blok and oud:
            legacy = True
        uitz = len(u.get('excludeUsers') or []) + len(u.get('excludeGroups') or []) + len(u.get('excludeRoles') or [])
        regels.append({'name': p.get('displayName') or '', 'state': {'enabled': 'Aan', 'disabled': 'Uit',
                                                                       'enabledForReportingButNotEnforced': 'Alleen rapporteren'}.get(p.get('state'), p.get('state') or ''),
                       'mfa': mfa, 'block': blok, 'legacy': oud and blok,
                       'scope': 'Alle gebruikers' if iedereen else ('Beheerdersrollen' if rollen else 'Selectie van gebruikers/groepen'),
                       'excluded': uitz, 'excludeUsers': (u.get('excludeUsers') or []) if aan else []})
    return {'policies': regels, 'mfaAll': alle, 'mfaAdmins': admins, 'legacyBlock': legacy, 'mfaRoles': sorted(mfa_rollen)}


def _gebruikers(c: Ctx) -> dict:
    g = c.g

    def gebruikers():
        try:
            return g.all('/users?$select=id,displayName,userPrincipalName,accountEnabled,userType,assignedLicenses,createdDateTime,externalUserState,'
                         'signInActivity&$top=500'), True
        except ApiFout:   # zonder Entra ID P1 geen aanmeldgegevens
            return g.all('/users?$select=id,displayName,userPrincipalName,accountEnabled,userType,assignedLicenses,createdDateTime,externalUserState&$top=999'), False

    def rollen():
        rl = g.get('/directoryRoles?$select=id,displayName,roleTemplateId').get('value', [])
        leden = parallel({x['id']: (lambda rid=x['id']: g.all(f'/directoryRoles/{rid}/members?$select=id,displayName,userPrincipalName')) for x in rl})
        return [{'role': x.get('displayName') or '', 'tpl': x.get('roleTemplateId') or '', 'members': leden[x['id']] if not isinstance(leden[x['id']], Exception) else []}
                for x in rl]

    def postvakken():
        if not c.exo_ok:
            raise ApiFout('Exchange niet verbonden')
        r = c.x.run('Get-Mailbox', ResultSize='Unlimited', RecipientTypeDetails=['SharedMailbox', 'RoomMailbox', 'EquipmentMailbox'])
        return {str(m.get('ExternalDirectoryObjectId') or '') for m in r}

    def doorsturen():
        if not c.exo_ok:
            raise ApiFout('Exchange niet verbonden')
        x = c.x
        r = parallel({'mb': lambda: x.run('Get-Mailbox', ResultSize='Unlimited', Filter='ForwardingSmtpAddress -ne $null -or ForwardingAddress -ne $null'),
                      'pol': lambda: x.run('Get-HostedOutboundSpamFilterPolicy', Identity='Default')})
        if isinstance(r['mb'], Exception):
            raise r['mb']
        eigen = {d['id'].lower() for d in c.t.domeinen}
        uit = []
        for m in r['mb']:
            smtp = re.sub(r'(?i)^smtp:', '', str(m.get('ForwardingSmtpAddress') or ''))
            intern = str(m.get('ForwardingAddress') or '')
            dom = smtp.rsplit('@', 1)[-1].lower() if '@' in smtp else ''
            uit.append({'mailbox': str(m.get('PrimarySmtpAddress') or ''), 'name': str(m.get('DisplayName') or ''), 'to': smtp or intern,
                        'external': bool(smtp) and dom not in eigen, 'keep': bool(m.get('DeliverToMailboxAndForward'))})
        modus = '' if isinstance(r['pol'], Exception) or not r['pol'] else str(r['pol'][0].get('AutoForwardingMode') or '')
        return {'list': sorted(uit, key=lambda f: (not f['external'], f['name'].lower())), 'mode': modus}

    r = parallel({
        'users': gebruikers,
        'reg': lambda: g.all('/reports/authenticationMethods/userRegistrationDetails?$top=999'),
        'roles': rollen,
        'sd': lambda: g.get('/policies/identitySecurityDefaultsEnforcementPolicy'),
        'ca': lambda: g.all('/identity/conditionalAccess/policies'),
        'auth': lambda: g.get('/policies/authorizationPolicy'),
        'shared': postvakken,
        'fwd': doorsturen,
    })
    if isinstance(r['users'], Exception):
        raise r['users']
    users, met_aanmelding = r['users']
    gedeeld = r['shared'] if not isinstance(r['shared'], Exception) else set()
    rol_data = r['roles'] if not isinstance(r['roles'], Exception) else []
    rol_per: dict[str, list[str]] = {}
    tpl_per: dict[str, set[str]] = {}
    ga = set()
    for rl in rol_data:
        for m in rl['members']:
            if m.get('@odata.type', '#microsoft.graph.user') == '#microsoft.graph.user':
                rol_per.setdefault(m['id'], []).append(rl['role'])
                tpl_per.setdefault(m['id'], set()).add(rl['tpl'])
                if rl['tpl'] == GLOBAL_ADMIN:
                    ga.add(m['id'])

    # MFA-registratie: liefst het rapport (Entra ID P1), anders per gebruiker de methoden opvragen
    bron = 'rapport'
    reg: dict[str, list[str]] = {}
    if not isinstance(r['reg'], Exception):
        for x in r['reg']:
            reg[x['id']] = list(x.get('methodsRegistered') or [])
    else:
        bron = 'methoden'
        doel = [u for u in users if u.get('accountEnabled') and u.get('userType') != 'Guest' and u['id'] not in gedeeld][:600]

        def methoden(u):
            try:
                return u['id'], [str(m.get('@odata.type', '')).replace('#microsoft.graph.', '')
                                 for m in g.get(f"/users/{u['id']}/authentication/methods").get('value', [])]
            except ApiFout:
                return u['id'], None
        with ThreadPoolExecutor(max_workers=8) as ex:
            for uid, m in ex.map(methoden, doel):
                if m is not None:
                    reg[uid] = [x for x in m if x != 'passwordAuthenticationMethod']

    sd = not isinstance(r['sd'], Exception) and bool(r['sd'].get('isEnabled'))
    ca = _ca(r['ca']) if not isinstance(r['ca'], Exception) else {'policies': [], 'mfaAll': False, 'mfaAdmins': False, 'legacyBlock': False, 'mfaRoles': []}
    ca_fout = str(r['ca']) if isinstance(r['ca'], Exception) else ''
    uitgezonderd = {uid for p in ca['policies'] if p['mfa'] for uid in p['excludeUsers']}
    afgedwongen = sd or ca['mfaAll']

    nu = NU()
    lijst, gasten = [], []
    for u in users:
        sa = u.get('signInActivity') or {}
        laatst = max([d for d in (_dt(sa.get(k)) for k in ('lastSignInDateTime', 'lastNonInteractiveSignInDateTime', 'lastSuccessfulSignInDateTime')) if d],
                     default=None)
        if u.get('userType') == 'Guest':
            gasten.append({'id': u['id'], 'name': u.get('displayName') or '', 'upn': u.get('userPrincipalName') or '', 'state': u.get('externalUserState') or '',
                           'created': u.get('createdDateTime') or '', 'last': laatst.isoformat() if laatst else '',
                           'days': (nu - laatst).days if laatst else None, 'enabled': u.get('accountEnabled') is not False})
            continue
        m = reg.get(u['id'])
        stand = 'unknown' if m is None else _mfa_stand(m)
        rollen_u = rol_per.get(u['id'], [])
        if u['id'] in gedeeld:
            stand_lbl = 'shared'
        elif not u.get('accountEnabled'):
            stand_lbl = 'disabled'
        else:
            stand_lbl = stand
        lijst.append({'id': u['id'], 'name': u.get('displayName') or '', 'upn': u.get('userPrincipalName') or '', 'enabled': bool(u.get('accountEnabled')),
                      'licensed': bool(u.get('assignedLicenses')), 'mfa': stand_lbl, 'methods': [METHODE.get(x, (x, None))[0] for x in (m or [])],
                      'roles': rollen_u, 'ga': u['id'] in ga,
                      'enforced': ((afgedwongen and u['id'] not in uitgezonderd) or bool(tpl_per.get(u['id'], set()) & set(ca['mfaRoles'])))
                      if (sd or not ca_fout) else None,
                      'excluded': u['id'] in uitgezonderd, 'last': laatst.isoformat() if laatst else '', 'days': (nu - laatst).days if laatst else None})
    volgorde = {'none': 0, 'unknown': 1, 'weak': 2, 'strong': 3, 'disabled': 4, 'shared': 5}
    lijst.sort(key=lambda u: (not u['roles'] or u['mfa'] in ('strong', 'disabled', 'shared'), volgorde.get(u['mfa'], 9), u['name'].lower()))

    # Controlelijst met tenantinstellingen
    auth = r['auth'] if not isinstance(r['auth'], Exception) else {}
    dur = auth.get('defaultUserRolePermissions') or {}
    zelf_toestemming = any(str(x).startswith('ManagePermissionGrantsForSelf.') for x in dur.get('permissionGrantPoliciesAssigned') or [])
    actief = [u for u in lijst if u['mfa'] not in ('disabled', 'shared')]
    zonder = [u for u in actief if u['mfa'] == 'none']
    admin_zonder = [u for u in zonder if u['roles']]
    fwd = r['fwd'] if not isinstance(r['fwd'], Exception) else None
    extern = [f for f in (fwd or {}).get('list', []) if f['external']]
    def _oud(x: dict) -> bool:
        if x['days'] is not None:
            return x['days'] > 90
        gemaakt = _dt(x['created'])   # nooit aangemeld: alleen meetellen als de gast al langer dan 90 dagen bestaat
        return met_aanmelding and bool(gemaakt) and (nu - gemaakt).days > 90
    oud_gast = [x for x in gasten if _oud(x)]
    controles = [
        {'key': 'mfa', 'title': 'MFA geregistreerd voor alle actieve gebruikers',
         'status': 'ok' if not zonder else ('err' if admin_zonder else 'warn'),
         'text': 'Alle actieve gebruikers hebben MFA geregistreerd.' if not zonder else
                 f'{len(zonder)} van {len(actief)} actieve gebruikers hebben geen MFA' + (f', waarvan {len(admin_zonder)} beheerder(s)!' if admin_zonder else '.')},
        {'key': 'enforce', 'title': 'MFA wordt afgedwongen',
         'status': 'ok' if afgedwongen else ('warn' if ca['mfaAdmins'] else 'err'),
         'text': 'Security Defaults staan aan (MFA voor iedereen).' if sd else
                 ('Een Conditional Access-beleid vraagt MFA voor alle gebruikers en apps.' if ca['mfaAll'] else
                  ('MFA wordt alleen afgedwongen voor beheerders of een selectie, niet voor iedereen.' if ca['mfaAdmins'] else
                   'Er is geen Security Defaults en geen Conditional Access-beleid dat MFA vraagt: registratie alleen is niet genoeg.'))},
        {'key': 'legacy', 'title': 'Verouderde aanmeldmethoden (basisverificatie) geblokkeerd',
         'status': 'ok' if (sd or ca['legacyBlock']) else 'warn',
         'text': 'Geblokkeerd via ' + ('Security Defaults.' if sd else 'Conditional Access.') if (sd or ca['legacyBlock'])
                 else 'Geen beleid gevonden dat oude protocollen (ActiveSync, IMAP/POP met wachtwoord) blokkeert. Exchange Online heeft basisverificatie wel zelf al uitgezet.'},
        {'key': 'ga', 'title': 'Aantal Global Administrators (advies: 2 tot 4)',
         'status': 'ok' if 2 <= len(ga) <= 4 else ('warn' if len(ga) else 'unknown'),
         'text': f'{len(ga)} Global Administrator(s).' + (' Eén is te weinig (geen reserve bij uitsluiting).' if len(ga) == 1 else '')
                 + (' Meer dan 4 vergroot het risico.' if len(ga) > 4 else '') if rol_data else 'Rollen konden niet worden gelezen.'},
        {'key': 'consent', 'title': 'Gebruikers mogen zelf apps toestemming geven',
         'status': 'warn' if zelf_toestemming else 'ok',
         'text': 'Ja: gebruikers kunnen apps van derden toegang geven tot hun gegevens (risico op "consent phishing").' if zelf_toestemming
                 else 'Nee: alleen beheerders geven toestemming aan apps.'},
        {'key': 'apps', 'title': 'Gebruikers mogen app-registraties maken',
         'status': 'warn' if dur.get('allowedToCreateApps') else 'ok',
         'text': 'Ja: iedere gebruiker kan apps registreren in Entra.' if dur.get('allowedToCreateApps') else 'Nee.'},
        {'key': 'invite', 'title': 'Wie mag gasten uitnodigen',
         'status': 'warn' if auth.get('allowInvitesFrom') == 'everyone' else 'ok',
         'text': {'everyone': 'Iedereen, ook gasten zelf.', 'adminsGuestInvitersAndAllMembers': 'Alle leden (standaard).',
                  'adminsAndGuestInviters': 'Alleen beheerders en Gastuitnodigers.', 'none': 'Niemand.'}.get(auth.get('allowInvitesFrom'), auth.get('allowInvitesFrom') or 'Onbekend')},
        {'key': 'fwd', 'title': 'Postvakken die extern doorsturen',
         'status': 'unknown' if fwd is None else ('warn' if extern else 'ok'),
         'text': 'Exchange niet verbonden.' if fwd is None else
                 (f'{len(extern)} postvak(ken) sturen door naar een extern adres.' if extern else 'Geen postvakken die extern doorsturen.')
                 + (f" Automatisch doorsturen (uitgaand beleid): {({'Automatic': 'Automatisch (geblokkeerd)', 'On': 'Toegestaan', 'Off': 'Geblokkeerd'}).get(fwd['mode'], fwd['mode'])}." if fwd and fwd['mode'] else '')},
        {'key': 'guests', 'title': 'Gasten zonder recente aanmelding (>90 dagen)',
         'status': 'warn' if oud_gast else 'ok',
         'text': f'{len(gasten)} gast(en), waarvan {len(oud_gast)} langer dan 90 dagen niet aangemeld.' if met_aanmelding
                 else f'{len(gasten)} gast(en). Aanmelddata vraagt Entra ID P1.'},
    ]
    return {'users': lijst, 'guests': sorted(gasten, key=lambda x: (-(x['days'] or 99999) if met_aanmelding else 0, x['name'].lower())),
            'checks': controles, 'securityDefaults': sd, 'ca': ca, 'caError': ca_fout, 'forwarding': fwd, 'source': bron, 'signIns': met_aanmelding,
            'admins': [{'id': u['id'], 'name': u['name'], 'upn': u['upn'], 'roles': u['roles'], 'mfa': u['mfa'], 'ga': u['ga']} for u in lijst if u['roles']],
            'counts': {'active': len(actief), 'none': len(zonder), 'weak': len([u for u in actief if u['mfa'] == 'weak']),
                       'strong': len([u for u in actief if u['mfa'] == 'strong']), 'adminsNone': len(admin_zonder), 'ga': len(ga), 'guests': len(gasten)},
            'portal': f'https://entra.microsoft.com/{c.t.id}/#view/Microsoft_AAD_ConditionalAccess/ConditionalAccessBlade/~/Policies'}


@api('cu.users')
def cu_users(c: Ctx, b: dict) -> dict:
    return c.t.cache('compliance-gebruikers', lambda: _gebruikers(c), VERS, bool(b.get('fresh')))


@api('cu.forward.off')
def cu_forward_off(c: Ctx, b: dict) -> dict:
    mb = str(b['mailbox'])
    c.x.run('Set-Mailbox', Identity=mb, ForwardingSmtpAddress=NULL, ForwardingAddress=NULL, DeliverToMailboxAndForward=False)
    c.t.weg('compliance-gebruikers')
    c.L(f'Doorsturen uitgezet voor {mb}.')
    return {}


@api('cd.cleanup')
def cd_cleanup(c: Ctx, b: dict) -> dict:
    """Apparaten opschonen: uitschakelen in Entra (omkeerbaar) of verwijderen (Intune en Entra)."""
    actie = b.get('action')
    if actie not in ('disable', 'enable', 'delete'):
        raise ApiFout('Onbekende actie.')
    g = c.g

    def een(d: dict):
        naam = d.get('name') or d.get('id')
        try:
            if actie in ('disable', 'enable'):
                if not d.get('entraId'):
                    return f'{naam}: staat niet in Entra ID, overgeslagen.'
                g.patch(f"/devices/{d['entraId']}", {'accountEnabled': actie == 'enable'})
                return f"{naam}: {'uitgeschakeld' if actie == 'disable' else 'weer ingeschakeld'} in Entra ID."
            if d.get('intune'):
                g.delete(f"/deviceManagement/managedDevices/{d['id']}")
            if d.get('entraId'):
                g.delete(f"/devices/{d['entraId']}")
            return f'{naam}: verwijderd' + (' uit Intune en Entra ID.' if d.get('intune') and d.get('entraId') else '.')
        except ApiFout as e:
            fout = str(e)
            if 'autopilot' in fout.lower() or 'ZtdDeviceAssigned' in fout:
                fout = 'staat in Autopilot; verwijder het eerst daar (Apparaten > Autopilot).'
            return f'FOUT {naam}: {fout[:200]}'
    with ThreadPoolExecutor(max_workers=6) as ex:
        regels = list(ex.map(een, b.get('items') or []))
    for r in regels:
        c.L(r)
    c.t.weg('compliance-apparaten', 'apparaten', 'readiness-feiten')
    return {'results': regels, 'failed': len([r for r in regels if r.startswith('FOUT')])}
