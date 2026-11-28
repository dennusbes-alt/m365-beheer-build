"""SharePoint-beheer: actieve sites met opslag en de deelinstelling per site.

Gebruikt de SharePoint-beheer-API van de klant (https://<tenant>-admin.sharepoint.com), net als het
SharePoint-beheercentrum en de SharePoint Online-module (Set-SPOSite -SharingCapability).
Vereist bij de klant de rol SharePoint Administrator.
"""
from __future__ import annotations

import logging
import time

from xml.sax.saxutils import escape

from .clients import ApiFout, _sessie, _verstuur
from .context import Ctx, api, VERS

DELEN = {
    0: ('Disabled', 'Alleen personen in de organisatie'),
    3: ('ExistingExternalUserSharingOnly', 'Bestaande gasten'),
    1: ('ExternalUserSharingOnly', 'Nieuwe en bestaande gasten'),
    2: ('ExternalUserAndGuestSharing', 'Iedereen (ook anonieme links)'),
}
TENANT_TYPE = '{268004ae-ef6b-4e9b-8425-127220d84719}'   # Microsoft.Online.SharePoint.TenantAdministration.Tenant
FOUT_ROL = 'Hiervoor heb je bij deze klant de rol SharePoint Administrator nodig. Controleer de GDAP-relatie.'


def _ms_melding(r) -> str:
    """De echte reden van SharePoint (body of diagnoseheader), voor het logboek en de melding."""
    try:
        j = r.json()
        m = (j.get('error') or {}).get('message') or (j.get('odata.error') or {}).get('message', {}).get('value') or j.get('error_description')
        if isinstance(m, dict):
            m = m.get('value')
        if m:
            return str(m)[:250]
    except ValueError:
        pass
    return (r.headers.get('x-ms-diagnostics') or r.headers.get('WWW-Authenticate') or r.text or r.reason or '')[:250]


def _token_info(token: str) -> str:
    """Alleen voor het logboek bij een weigering: welke rollen (wids) en rechten (scp) zitten in het token. Nooit het token zelf."""
    import base64
    import json as _json
    try:
        deel = token.split('.')[1]
        j = _json.loads(base64.urlsafe_b64decode(deel + '=' * (-len(deel) % 4)))
        return f"aud={j.get('aud')} wids={j.get('wids', 'GEEN')} scp={str(j.get('scp', ''))[:80]} idtyp={j.get('idtyp', '')}"
    except Exception:  # noqa: BLE001
        return 'onleesbaar'


def _rollen(c: Ctx) -> list[str] | None:
    k = next((k for k in (c.staat.klanten or []) if k.get('id') == c.t.id), None)
    return list(k.get('roles') or []) if k else None


def _sp(c: Ctx, methode: str, pad: str, json=None, data=None, ctype=None, _opnieuw: bool = True):
    t = c.t
    token = t.sp_token()
    h = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json;odata=nometadata'}
    if json is not None:
        h['Content-Type'] = 'application/json;odata=nometadata'
    if ctype:
        h['Content-Type'] = ctype
    r = _verstuur(_sessie(), methode, t.sp_admin() + pad, json=json, data=data, headers=h, timeout=120)
    if r.status_code in (401, 403):
        ms = _ms_melding(r)
        logging.getLogger('m365beheer').info('SharePoint %s bij %s (%s): %s | token: %s', r.status_code, t.naam, pad.split('?')[0], ms, _token_info(token))
        # Misschien ontbreekt het SharePoint-recht nog in de koppeling: aanvullen en één keer opnieuw (met een vers token)
        if _opnieuw and t.id != c.staat.auth.home_tenant and t.rechten_nu() == 'aangevuld':
            time.sleep(5)
            return _sp(c, methode, pad, json=json, data=data, ctype=ctype, _opnieuw=False)
        rollen = _rollen(c)
        if rollen is not None and 'SharePoint Administrator' not in rollen:
            raise ApiFout('Je GDAP-rollen bij deze klant bevatten geen SharePoint Administrator'
                          + (f" (wel: {', '.join(rollen)})" if rollen else '') + '. Voeg die rol toe aan de GDAP-relatie en aan de toewijzing voor jouw groep.',
                          r.status_code)
        raise ApiFout(f'SharePoint weigert de toegang ({r.status_code}). Melding van Microsoft: {ms or "geen"}. Controleer dat de GDAP-rol '
                      'SharePoint Administrator voor jou actief is (een nieuwe toewijzing kan tot een uur duren).', r.status_code)
    if r.status_code >= 400:
        try:
            j = r.json()
            tekst = (j.get('error') or {}).get('message') or j.get('odata.error', {}).get('message', {}).get('value') or r.text
        except ValueError:
            tekst = r.text
        raise ApiFout(f'SharePoint: {str(tekst)[:300]}', r.status_code)
    return r


def _naam_delen(v) -> str:
    try:
        return DELEN.get(int(v), (str(v), str(v)))[1]
    except (TypeError, ValueError):
        return str(v or '')


@api('sp.sites')
def sp_sites(c: Ctx, b: dict) -> dict:
    def ophalen() -> list[dict]:
        sites, start = [], None
        for _ in range(50):   # max 50 pagina's
            body = {'speFilter': {'IncludePersonalSite': 0, 'IncludeDetail': True, 'StartIndex': start, 'Template': None, 'Filter': None}}
            j = _sp(c, 'POST', '/_api/SPO.Tenant/GetSitePropertiesFromSharePointByFilters', json=body).json()
            sites.extend(j.get('value') or [])
            start = j.get('_nextStartIndexById')
            if not start or start == '-1':
                break
        return sites
    alle = c.t.cache('spsites', ophalen, VERS, bool(b.get('fresh')))
    uit = []
    for s in alle:
        url = s.get('Url') or ''
        if '/personal/' in url or s.get('Status') not in (None, 'Active'):
            continue
        uit.append({'url': url, 'title': s.get('Title') or url, 'template': s.get('Template') or '',
                    'usedMb': float(s.get('StorageUsage') or 0), 'maxMb': float(s.get('StorageMaximumLevel') or 0),
                    'sharing': s.get('SharingCapability'), 'sharingText': _naam_delen(s.get('SharingCapability')),
                    'modified': s.get('LastContentModifiedDate') or '', 'owner': s.get('OwnerEmail') or s.get('Owner') or '',
                    'group': bool(s.get('GroupId')) and s.get('GroupId') != '00000000-0000-0000-0000-000000000000'})
    uit.sort(key=lambda s: -s['usedMb'])
    tenant = {}
    try:
        tenant = _sp(c, 'GET', '/_api/SPO.Tenant?$select=SharingCapability,StorageQuota,StorageQuotaAllocated').json()
    except ApiFout:
        pass
    return {'sites': uit, 'tenantSharing': tenant.get('SharingCapability'), 'tenantSharingText': _naam_delen(tenant.get('SharingCapability')),
            'tenantQuotaMb': tenant.get('StorageQuota'), 'options': [{'value': k, 'label': v[1]} for k, v in DELEN.items()]}


@api('sp.sharing.set')
def sp_sharing_set(c: Ctx, b: dict) -> dict:
    """Deelinstelling van één site (zoals Set-SPOSite -SharingCapability), via de CSOM-beheer-API."""
    url, waarde = str(b['url']), int(b['value'])
    if waarde not in DELEN:
        raise ApiFout('Onbekende deelinstelling.')
    xml = (f'<Request AddExpandoFieldTypeSuffix="true" SchemaVersion="15.0.0.0" LibraryVersion="16.0.0.0" ApplicationName="M365Beheer" '
           f'xmlns="http://schemas.microsoft.com/sharepoint/clientquery/2009"><Actions>'
           f'<ObjectPath Id="2" ObjectPathId="1" /><ObjectPath Id="4" ObjectPathId="3" />'
           f'<SetProperty Id="5" ObjectPathId="3" Name="SharingCapability"><Parameter Type="Enum">{waarde}</Parameter></SetProperty>'
           f'<Method Name="Update" Id="6" ObjectPathId="3" /></Actions><ObjectPaths>'
           f'<Constructor Id="1" TypeId="{TENANT_TYPE}" />'
           f'<Method Id="3" ParentId="1" Name="GetSitePropertiesByUrl"><Parameters><Parameter Type="String">{escape(url)}</Parameter>'
           f'<Parameter Type="Boolean">false</Parameter></Parameters></Method></ObjectPaths></Request>')
    r = _sp(c, 'POST', '/_vti_bin/client.svc/ProcessQuery', data=xml.encode('utf-8'), ctype='text/xml')
    try:
        j = r.json()
        fout = (j[0] or {}).get('ErrorInfo') if isinstance(j, list) and j else None
    except ValueError:
        fout = None
    if fout:
        tekst = fout.get('ErrorMessage') or str(fout)
        if 'sharing' in tekst.lower() and ('tenant' in tekst.lower() or 'organization' in tekst.lower()):
            tekst = 'Deze instelling is ruimer dan wat de organisatie toestaat. Verruim eerst de deelinstelling op organisatieniveau.'
        raise ApiFout(f'SharePoint: {tekst}')
    c.t.weg('spsites')
    c.L(f"Delen voor {url}: {DELEN[waarde][1]}.")
    return {}
