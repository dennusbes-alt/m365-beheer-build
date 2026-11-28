"""Authenticatiemethoden: beleid per methode (aan/uit, groepen) en selfservice-wachtwoordherstel (SSPR)."""
from __future__ import annotations

from .clients import ApiFout, parallel
from .context import Ctx, api

POL = '/policies/authenticationMethodsPolicy'
NAMEN = {
    'MicrosoftAuthenticator': ('Microsoft Authenticator', 'Pushmelding of code in de Authenticator-app.'),
    'Fido2': ('Passkey / FIDO2-beveiligingssleutel', 'Phishingbestendig inloggen met een sleutel of passkey.'),
    'Sms': ('Sms', 'Code per sms (minder veilig).'),
    'Voice': ('Spraakoproep', 'Code via een telefoontje (minder veilig).'),
    'Email': ('Eenmalige code per e-mail', 'Alleen voor gasten en wachtwoordherstel.'),
    'TemporaryAccessPass': ('Tijdelijke toegangspas (TAP)', 'Tijdelijke code om een nieuwe telefoon of passkey te registreren.'),
    'SoftwareOath': ('Authenticator-app met code (OATH)', 'Codes uit apps van derden, zoals Google Authenticator.'),
    'HardwareOath': ('Hardwaretoken (OATH)', 'Fysieke tokens met codes.'),
    'X509Certificate': ('Certificaat', 'Inloggen met een certificaat (smartcard).'),
    'QRCodePin': ('QR-code met pincode', 'Voor frontline-medewerkers op gedeelde apparaten.'),
}
FOUT_ROL = ('Hiervoor heb je bij deze klant de rol Authentication Policy Administrator (of Global Administrator) nodig. '
            'Controleer de GDAP-relatie.')


def _groepnamen(c: Ctx, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i and i not in ('all_users',)}
    r = parallel({i: (lambda g=i: c.g.get(f'/groups/{g}?$select=displayName')) for i in ids})
    return {i: (v.get('displayName') if isinstance(v, dict) else i) for i, v in r.items()}


@api('auth.methods')
def methoden(c: Ctx, b: dict) -> dict:
    try:
        p = c.g.get(POL)
    except ApiFout as e:
        if e.status in (401, 403):
            raise ApiFout(FOUT_ROL)
        raise
    confs = p.get('authenticationMethodConfigurations') or []
    ids = {t.get('id') for x in confs for t in (x.get('includeTargets') or []) + (x.get('excludeTargets') or [])}
    namen = _groepnamen(c, ids)
    namen['all_users'] = 'Alle gebruikers'

    def doelen(lijst: list[dict]) -> list[dict]:
        return [{'id': t.get('id'), 'name': namen.get(t.get('id'), t.get('id')), 'required': bool(t.get('isRegistrationRequired'))} for t in lijst or []]
    uit = []
    for x in confs:
        n = NAMEN.get(x['id'], (x['id'], ''))
        uit.append({'id': x['id'], 'name': n[0], 'desc': n[1], 'type': x.get('@odata.type', ''), 'state': x.get('state', 'disabled'),
                    'include': doelen(x.get('includeTargets')), 'exclude': doelen(x.get('excludeTargets'))})
    uit.sort(key=lambda m: (m['state'] != 'enabled', m['name']))
    return {'methods': uit, 'migration': p.get('policyMigrationState', ''), 'updated': p.get('lastModifiedDateTime', '')}


@api('auth.method.set')
def methode_zetten(c: Ctx, b: dict) -> dict:
    """Methode aan/uit zetten en bepalen voor welke groepen (include) en uitzonderingen (exclude)."""
    mid = b['id']
    huidig = c.g.get(f'{POL}/authenticationMethodConfigurations/{mid}')
    body: dict = {'@odata.type': huidig.get('@odata.type'), 'state': 'enabled' if b.get('enabled') else 'disabled'}

    def doelen(nieuw: list[dict] | None, oud: list[dict]) -> list[dict] | None:
        if nieuw is None:
            return None
        bestaand = {t.get('id'): t for t in oud or []}
        uit = []
        for t in nieuw:
            basis = {k: v for k, v in (bestaand.get(t['id']) or {}).items() if not k.startswith('@')}
            basis.update({'id': t['id'], 'targetType': 'group'})
            basis.setdefault('isRegistrationRequired', False)
            if huidig.get('@odata.type', '').endswith('microsoftAuthenticatorAuthenticationMethodConfiguration'):
                basis.setdefault('authenticationMode', 'any')
            uit.append(basis)
        return uit
    inc = doelen(b.get('include'), huidig.get('includeTargets'))
    exc = doelen(b.get('exclude'), huidig.get('excludeTargets'))
    if inc is not None and 'includeTargets' in huidig:
        body['includeTargets'] = inc
    if exc is not None and 'excludeTargets' in huidig:
        body['excludeTargets'] = [{'id': t['id'], 'targetType': 'group'} for t in exc]
    try:
        c.g.patch(f'{POL}/authenticationMethodConfigurations/{mid}', body)
    except ApiFout as e:
        if e.status in (401, 403):
            raise ApiFout(FOUT_ROL)
        raise
    c.L(f"{NAMEN.get(mid, (mid,))[0]}: {'ingeschakeld' if b.get('enabled') else 'uitgeschakeld'}.")
    return {}


@api('auth.sspr')
def sspr(c: Ctx, b: dict) -> dict:
    """SSPR. Microsoft biedt (nog) geen API voor de tenantbrede instelling Geen/Geselecteerd/Iedereen; die openen we in het portal.
    Wel via Graph: of beheerders SSPR mogen gebruiken (authorizationPolicy.allowedToUseSSPR)."""
    if 'admins' in b:
        c.g.patch('/policies/authorizationPolicy', {'allowedToUseSSPR': bool(b['admins'])})
        c.L(f"Selfservice-wachtwoordherstel voor beheerders {'aan' if b['admins'] else 'uit'}gezet.")
    p = c.g.get('/policies/authorizationPolicy?$select=allowedToUseSSPR,allowEmailVerifiedUsersToJoinOrganization')
    tid = c.t.id
    return {'admins': bool(p.get('allowedToUseSSPR')),
            'portal': f'https://portal.azure.com/#@{tid}/view/Microsoft_AAD_IAM/PasswordResetMenuBlade/~/Properties',
            'registratie': f'https://portal.azure.com/#@{tid}/view/Microsoft_AAD_IAM/PasswordResetMenuBlade/~/AuthenticationMethods'}


@api('open.url')
def open_url(c: Ctx, b: dict) -> dict:
    """Een Microsoft-beheerpagina openen in de standaardbrowser (alleen Microsoft-domeinen)."""
    import webbrowser
    from urllib.parse import urlparse
    url = str(b.get('url') or '')
    u = urlparse(url)
    host = (u.hostname or '').lower()
    toegestaan = {'portal.azure.com', 'entra.microsoft.com', 'admin.microsoft.com', 'security.microsoft.com', 'admin.exchange.microsoft.com',
                  'partner.microsoft.com', 'intune.microsoft.com', 'endpoint.microsoft.com', 'purview.microsoft.com',
                  'compliance.microsoft.com', 'learn.microsoft.com'}
    # Servicedesk: tickets in Autotask en kennisdocumenten in IT Glue
    if u.scheme != 'https' or not (host in toegestaan or host.endswith(('.sharepoint.com', '.autotask.net', '.itglue.com', '.centrastage.net', '.datto.com'))):
        raise ApiFout('Deze link mag de app niet openen.')
    webbrowser.open(url)
    return {}
