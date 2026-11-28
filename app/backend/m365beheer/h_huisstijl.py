"""Huisstijl van de aanmeldpagina van een klant (Microsoft Entra 'Bedrijfshuisstijl' / company branding).

Geldt voor wat gebruikers zien bij het aanmelden (login.microsoftonline.com), niet voor de beheerportals.
Graph: /organization/{id}/branding (zoals Update-MgOrganizationBranding) en de afbeeldingen als stream
(bannerLogo, squareLogo, squareLogoDark, backgroundImage, favicon).
Vereist het recht OrganizationalBranding.ReadWrite.All en bij de klant de rol Organizational Branding Administrator.
"""
from __future__ import annotations

import base64

from .clients import ApiFout, GB, _sessie, _verstuur, parallel
from .context import Ctx, api

FOUT_ROL = ('De huisstijl is bij deze klant niet te wijzigen. Nodig: in de GDAP-relatie de rol Organizational Branding Administrator. '
            'Is de app net bijgewerkt, open de klant dan opnieuw zodat de nieuwe rechten worden toegevoegd.')
AFBEELDINGEN = {'bannerLogo', 'squareLogo', 'squareLogoDark', 'backgroundImage', 'favicon'}
VELDEN = ['backgroundColor', 'signInPageText', 'usernameHintText', 'customPrivacyAndCookiesText', 'customPrivacyAndCookiesUrl',
          'customTermsOfUseText', 'customTermsOfUseUrl', 'customCannotAccessYourAccountText', 'customCannotAccessYourAccountUrl',
          'customForgotMyPasswordText', 'customResetItNowText', 'customAccountResetCredentialsUrl']
ZICHTBAAR = ['hideCannotAccessYourAccount', 'hideForgotMyPassword', 'hideResetItNow', 'hideKeepMeSignedIn',
             'hideAccountResetCredentials', 'hideTermsOfUse', 'hidePrivacyAndCookies']
STANDAARD = {'Accept-Language': '0', 'Content-Language': '0'}   # 0 = de standaard (niet-taalgebonden) huisstijl


def _org(c: Ctx) -> str:
    oid = c.t.cache('org-id', lambda: c.g.get('/organization?$select=id')['value'][0]['id'], 3600)
    return oid


def _rol(e: Exception) -> Exception:
    return ApiFout(FOUT_ROL, e.status) if isinstance(e, ApiFout) and e.status in (401, 403) else e


def _branding(c: Ctx, oid: str) -> dict:
    try:
        return c.g.req('GET', f'/organization/{oid}/branding', headers=STANDAARD)
    except ApiFout as e:
        if e.status == 404:
            return {}   # nog geen huisstijl ingesteld
        raise _rol(e)


@api('brand.get')
def brand_get(c: Ctx, b: dict) -> dict:
    oid = _org(c)
    r = parallel({'b': lambda: _branding(c, oid), 'o': lambda: c.g.get(f'/organization/{oid}?$select=displayName')})
    if isinstance(r['b'], Exception):
        raise r['b']
    br = r['b'] or {}
    cdn = (br.get('cdnList') or [''])[0]
    url = lambda rel: f'https://{cdn}/{rel}' if cdn and rel else ''  # noqa: E731
    zicht = br.get('loginPageTextVisibilitySettings') or {}
    layout = br.get('loginPageLayoutConfiguration') or {}
    return {
        'exists': bool(br), 'org': (r['o'] if isinstance(r['o'], dict) else {}).get('displayName') or c.t.naam,
        **{k: br.get(k) or '' for k in VELDEN},
        'visibility': {k: bool(zicht.get(k)) for k in ZICHTBAAR},
        'layout': layout.get('layoutTemplateType') or 'default', 'header': bool(layout.get('isHeaderShown')),
        'footer': layout.get('isFooterShown') is not False,
        'images': {k: url(br.get(f'{k}RelativeUrl')) for k in AFBEELDINGEN},
    }


@api('brand.save')
def brand_save(c: Ctx, b: dict) -> dict:
    """Kleur, teksten, koppelingen en zichtbaarheid opslaan (één PATCH, direct actief)."""
    oid = _org(c)
    body = {k: (str(b[k]).strip() or None) for k in VELDEN if k in b}
    kleur = body.get('backgroundColor')
    if kleur and not (len(kleur) == 7 and kleur.startswith('#')):
        raise ApiFout('De achtergrondkleur moet een kleurcode zijn, bijv. #1B7EA9.')
    if body.get('signInPageText') and len(body['signInPageText']) > 1024:
        raise ApiFout('De tekst op de aanmeldpagina mag maximaal 1024 tekens zijn.')
    if body.get('usernameHintText') and len(body['usernameHintText']) > 64:
        raise ApiFout('De hint in het gebruikersnaamveld mag maximaal 64 tekens zijn.')
    if 'visibility' in b:
        body['loginPageTextVisibilitySettings'] = {k: bool((b['visibility'] or {}).get(k)) for k in ZICHTBAAR}
    if 'layout' in b:
        body['loginPageLayoutConfiguration'] = {'layoutTemplateType': 'verticalSplit' if b['layout'] == 'verticalSplit' else 'default',
                                                'isHeaderShown': bool(b.get('header')), 'isFooterShown': bool(b.get('footer', True))}
    try:
        c.g.req('PATCH', f'/organization/{oid}/branding', body, headers=STANDAARD)
    except ApiFout as e:
        raise _rol(e)
    c.L('Huisstijl van de aanmeldpagina opgeslagen. Gebruikers zien het binnen enkele minuten.')
    return {}


@api('brand.image')
def brand_image(c: Ctx, b: dict) -> dict:
    """Afbeelding plaatsen (data: base64 van PNG/JPG, door de app al op het juiste formaat gebracht) of verwijderen."""
    soort = str(b.get('kind') or '')
    if soort not in AFBEELDINGEN:
        raise ApiFout('Onbekende afbeelding.')
    oid = _org(c)
    url = f'{GB}/organization/{oid}/branding/localizations/0/{soort}'
    h = {'Authorization': 'Bearer ' + c.g._token()}
    if b.get('remove'):
        r = _verstuur(_sessie(), 'DELETE', url, headers=h, timeout=60)
        if r.status_code == 405:   # sommige tenants: leeg bestand plaatsen
            r = _verstuur(_sessie(), 'PUT', url, data=b'', headers={**h, 'Content-Type': 'image/png'}, timeout=60)
    else:
        data = base64.b64decode(str(b.get('data') or '').split(',')[-1])
        if not data:
            raise ApiFout('Geen afbeelding ontvangen.')
        ctype = 'image/jpeg' if data[:3] == b'\xff\xd8\xff' else 'image/png'
        if not _bestaat(c, oid):   # eerst een (lege) huisstijl aanmaken, anders weigert Microsoft de afbeelding
            c.g.req('PATCH', f'/organization/{oid}/branding', {'backgroundColor': None}, headers=STANDAARD)
        r = _verstuur(_sessie(), 'PUT', url, data=data, headers={**h, 'Content-Type': ctype}, timeout=120)
    if r.status_code in (401, 403):
        raise ApiFout(FOUT_ROL, r.status_code)
    if r.status_code >= 400 and not (b.get('remove') and r.status_code == 404):
        try:
            tekst = r.json().get('error', {}).get('message') or r.text
        except ValueError:
            tekst = r.text
        raise ApiFout(f'Microsoft weigerde de afbeelding: {str(tekst)[:300]}', r.status_code)
    namen = {'bannerLogo': 'Bannerlogo', 'squareLogo': 'Vierkant logo', 'squareLogoDark': 'Vierkant logo (donker)',
             'backgroundImage': 'Achtergrondafbeelding', 'favicon': 'Favicon'}
    c.L(f"{namen[soort]} {'verwijderd' if b.get('remove') else 'geplaatst'}.")
    return {}


def _bestaat(c: Ctx, oid: str) -> bool:
    try:
        c.g.req('GET', f'/organization/{oid}/branding?$select=id', headers=STANDAARD)
        return True
    except ApiFout as e:
        if e.status == 404:
            return False
        raise _rol(e)


@api('brand.reset')
def brand_reset(c: Ctx, b: dict) -> dict:
    """Huisstijl helemaal weghalen (terug naar de standaard van Microsoft): eerst de afbeeldingen, dan de rest."""
    oid = _org(c)
    for soort in AFBEELDINGEN:
        try:
            brand_image(c, {'kind': soort, 'remove': True})
        except ApiFout:
            pass
    c.log.clear()
    try:
        c.g.req('DELETE', f'/organization/{oid}/branding', headers=STANDAARD)
    except ApiFout as e:
        if e.status != 404:
            raise _rol(e)
    c.L('Huisstijl verwijderd; de aanmeldpagina gebruikt weer de standaard van Microsoft.')
    return {}
