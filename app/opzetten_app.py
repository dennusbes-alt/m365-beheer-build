"""Eenmalig: maakt de eigen app-registratie "Microsoft 365 beheer (Justdata)" aan in de Justdata-tenant.

Waarom: bij GDAP mag een partner in een klant-tenant alleen apps gebruiken die daar zijn toegestaan
(anders AADSTS90099). Met een eigen multi-tenant app kan de beheer-app die toestemming per klant zelf
regelen via de Partner Center API (applicationconsents).

Wat dit script doet (idempotent, opnieuw draaien is veilig):
  1. Inloggen in de browser met een Global Administrator van Justdata.
  2. App-registratie aanmaken of bijwerken: multi-tenant, openbare client (geen geheim), redirect http://localhost.
  3. Gedelegeerde rechten: Microsoft Graph, Office 365 Exchange Online (Exchange.Manage), Partner Center.
  4. Beheerderstoestemming in de Justdata-tenant.
  5. Client-ID wegschrijven naar backend/m365beheer/appid.py (wordt meegebouwd in de app).
  6. Agenda (service calls): toepassingsrecht Microsoft Graph Calendars.ReadWrite met beheerderstoestemming, en een
     clientgeheim (2 jaar). Het geheim gaat rechtstreeks in de verborgen SharePoint-lijst van de app ('agenda-app') en
     wordt nooit getoond of lokaal opgeslagen. Een nieuw geheim alleen als er geen is of het binnen 60 dagen verloopt.

Gebruik:  .venv\\Scripts\\python.exe opzetten_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import msal
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent / 'backend'))
from m365beheer.auth import GRAPH_SCOPES, SHAREPOINT_RECHTEN  # noqa: E402

NAAM = 'Justdata M365 Beheer'   # 'Microsoft' mag niet in de naam van een app-registratie
GRAPH_CLI = '14d82eec-204b-4c2f-b7e8-296a70dab67e'   # alleen voor dit opzetscript, in de eigen tenant
GB = 'https://graph.microsoft.com/v1.0'

GRAPH_ID = '00000003-0000-0000-c000-000000000000'          # Microsoft Graph
EXO_ID = '00000002-0000-0ff1-ce00-000000000000'            # Office 365 Exchange Online
PC_ID = 'fa3d9a0c-3fb0-42cc-9193-47c7ecd2edbd'             # Partner Center API

# Alleen in de Justdata-tenant (niet bij klanten): GDAP, groepen en de SharePoint-lijst met automatiseringen
GRAPH_RECHTEN = ['openid', 'profile', 'offline_access', 'DelegatedAdminRelationship.ReadWrite.All', 'Group.Read.All',
                 'Sites.ReadWrite.All', 'Sites.Manage.All'] + \
    [s.rsplit('/', 1)[-1] for s in GRAPH_SCOPES]
SP_ID = '00000003-0000-0ff1-ce00-000000000000'             # SharePoint Online
APP_RECHT = 'Calendars.ReadWrite'                           # toepassingsrecht voor service calls in de agenda
GEHEIM_NAAM = 'Agenda (service calls)'
SLEUTELLIJST = 'M365BeheerKoppelingen'                       # verborgen lijst van de app op de Justdata-rootsite
RECHTEN = {GRAPH_ID: GRAPH_RECHTEN, EXO_ID: ['Exchange.Manage'], PC_ID: ['user_impersonation'], SP_ID: SHAREPOINT_RECHTEN}


def stap(t: str) -> None:
    print(f'  {t}', flush=True)


class G:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers['Authorization'] = 'Bearer ' + token

    def req(self, m: str, pad: str, body=None) -> dict:
        r = self.s.request(m, GB + pad, json=body, timeout=60)
        if r.status_code >= 400:
            raise SystemExit(f'Graph-fout {r.status_code} bij {m} {pad}: {r.text[:400]}')
        return r.json() if r.content else {}


def main() -> None:
    print(f'\n  {NAAM} opzetten in de Justdata-tenant\n  -------------------------------------------')
    app = msal.PublicClientApplication(GRAPH_CLI, authority='https://login.microsoftonline.com/organizations')
    stap('Inloggen in de browser (Global Administrator van Justdata)...')
    res = app.acquire_token_interactive(
        ['https://graph.microsoft.com/Application.ReadWrite.All', 'https://graph.microsoft.com/DelegatedPermissionGrant.ReadWrite.All',
         'https://graph.microsoft.com/Directory.Read.All', 'https://graph.microsoft.com/AppRoleAssignment.ReadWrite.All',
         'https://graph.microsoft.com/Sites.ReadWrite.All'], prompt='select_account', timeout=300)
    if 'access_token' not in res:
        raise SystemExit('Inloggen mislukt: ' + str(res.get('error_description') or res))
    tid = res['id_token_claims'].get('tid')
    stap(f"Ingelogd als {res['id_token_claims'].get('preferred_username')} (tenant {tid}).")
    g = G(res['access_token'])

    # Service principals van de doel-API's (Partner Center bestaat soms nog niet in de tenant)
    sps: dict[str, dict] = {}
    for api_id in RECHTEN:
        v = g.req('GET', f"/servicePrincipals?$filter=appId eq '{api_id}'&$select=id,appId,displayName,oauth2PermissionScopes,appRoles")['value']
        sps[api_id] = v[0] if v else g.req('POST', '/servicePrincipals', {'appId': api_id})
        stap(f"API gevonden: {sps[api_id].get('displayName')}")

    toegang = []
    for api_id, rechten in RECHTEN.items():
        scopes = {s['value'].lower(): (s['value'], s['id']) for s in sps[api_id].get('oauth2PermissionScopes') or []}
        ontbreekt = [r for r in rechten if r.lower() not in scopes]
        if ontbreekt:
            raise SystemExit(f"Rechten niet gevonden bij {sps[api_id].get('displayName')}: {ontbreekt}")
        RECHTEN[api_id] = [scopes[r.lower()][0] for r in rechten]   # exacte schrijfwijze van Microsoft
        toegang.append({'resourceAppId': api_id, 'resourceAccess': [{'id': scopes[r.lower()][1], 'type': 'Scope'} for r in rechten]})
    # Toepassingsrecht (geen gebruiker): afspraken in de agenda van collega's zetten (service calls)
    rol = next((r for r in sps[GRAPH_ID].get('appRoles') or [] if r.get('value') == APP_RECHT), None)
    if not rol:
        raise SystemExit(f'Toepassingsrecht {APP_RECHT} niet gevonden bij Microsoft Graph.')
    next(x for x in toegang if x['resourceAppId'] == GRAPH_ID)['resourceAccess'].append({'id': rol['id'], 'type': 'Role'})

    # App-registratie aanmaken of bijwerken
    bestaand = g.req('GET', f"/applications?$filter=displayName eq '{NAAM}'&$select=id,appId")['value']
    eigenschappen = {
        'displayName': NAAM,
        'signInAudience': 'AzureADMultipleOrgs',
        'isFallbackPublicClient': True,
        'publicClient': {'redirectUris': ['http://localhost']},
        'requiredResourceAccess': toegang,
        # Beheerrollen (wids) in de tokens: SharePoint gebruikt die om GDAP-beheerders (SharePoint Administrator) te herkennen
        'groupMembershipClaims': 'DirectoryRole',
        'notes': 'Gebruikt door de app Microsoft 365 beheer (Justdata) voor klantbeheer via GDAP. Eén geheim alleen voor de agenda (service calls) '
                 'in de Justdata-tenant; staat in de verborgen app-lijst.',
    }
    if bestaand:
        app_obj = bestaand[0]
        g.req('PATCH', f"/applications/{app_obj['id']}", eigenschappen)
        stap(f"Bestaande app-registratie bijgewerkt ({app_obj['appId']}).")
    else:
        app_obj = g.req('POST', '/applications', eigenschappen)
        stap(f"App-registratie aangemaakt ({app_obj['appId']}).")
    client_id = app_obj['appId']

    v = g.req('GET', f"/servicePrincipals?$filter=appId eq '{client_id}'&$select=id")['value']
    sp = v[0] if v else g.req('POST', '/servicePrincipals', {'appId': client_id, 'tags': ['WindowsAzureActiveDirectoryIntegratedApp']})

    # Beheerderstoestemming (voor alle gebruikers in Justdata)
    for api_id, rechten in RECHTEN.items():
        scope = ' '.join(rechten)
        v = g.req('GET', f"/oauth2PermissionGrants?$filter=clientId eq '{sp['id']}' and resourceId eq '{sps[api_id]['id']}'")['value']
        if v:
            g.req('PATCH', f"/oauth2PermissionGrants/{v[0]['id']}", {'scope': scope})
        else:
            g.req('POST', '/oauth2PermissionGrants', {'clientId': sp['id'], 'consentType': 'AllPrincipals',
                                                     'resourceId': sps[api_id]['id'], 'scope': scope})
        stap(f"Toestemming gegeven voor {sps[api_id].get('displayName')}.")

    agenda(g, app_obj, sp, sps[GRAPH_ID], rol)

    doel = Path(__file__).resolve().parent / 'backend' / 'm365beheer' / 'appid.py'
    doel.write_text(f'"""Eigen app-registratie in de Justdata-tenant (aangemaakt door opzetten_app.py). Geen geheim."""\n'
                    f"CLIENT_ID = '{client_id}'\nPARTNER_TENANT = '{tid}'\n", encoding='utf-8')
    print(f'\n  Klaar. Client-ID {client_id} staat in {doel.name}.\n')


def agenda(g: G, app_obj: dict, sp: dict, graph_sp: dict, rol: dict) -> None:
    """Toestemming voor het toepassingsrecht en het clientgeheim in de verborgen lijst (nooit op het scherm of op schijf)."""
    import json
    from datetime import datetime, timedelta, timezone
    al = g.req('GET', f"/servicePrincipals/{sp['id']}/appRoleAssignments")['value']
    if not any(a.get('appRoleId') == rol['id'] and a.get('resourceId') == graph_sp['id'] for a in al):
        g.req('POST', f"/servicePrincipals/{sp['id']}/appRoleAssignments", {'principalId': sp['id'], 'resourceId': graph_sp['id'], 'appRoleId': rol['id']})
    stap(f'Toestemming gegeven voor het toepassingsrecht {APP_RECHT} (agenda).')

    site = g.req('GET', '/sites/root?$select=id')['id']
    lijst = g.req('GET', f"/sites/{site}/lists?$filter=displayName eq '{SLEUTELLIJST}'&$select=id")['value']
    if lijst:
        lid = lijst[0]['id']
    else:
        lid = g.req('POST', f'/sites/{site}/lists', {'displayName': SLEUTELLIJST, 'description': 'Koppelingen van de app Microsoft 365 beheer (niet wijzigen)',
                                                     'columns': [{'name': 'Waarde', 'text': {'allowMultipleLines': True, 'textType': 'plain'}}],
                                                     'list': {'template': 'genericList', 'hidden': True}})['id']
    items = g.req('GET', f"/sites/{site}/lists/{lid}/items?$expand=fields($select=Title,Waarde)&$top=200")['value']
    bestaand = next((i for i in items if (i.get('fields') or {}).get('Title') == 'agenda-app'), None)
    grens = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    if bestaand:
        try:
            eind = json.loads(bestaand['fields'].get('Waarde') or '{}').get('end', '')
        except ValueError:
            eind = ''
        if eind > grens:
            stap(f'Agendageheim is nog geldig tot {eind[:10]}; geen nieuw geheim nodig.')
            return
    oud = g.req('GET', f"/applications/{app_obj['id']}?$select=passwordCredentials")['passwordCredentials']
    for c in oud:   # vorige agendageheimen weg (één geldig geheim)
        if c.get('displayName') == GEHEIM_NAAM:
            g.req('POST', f"/applications/{app_obj['id']}/removePassword", {'keyId': c['keyId']})
    eind = (datetime.now(timezone.utc) + timedelta(days=730)).replace(microsecond=0)
    nieuw = g.req('POST', f"/applications/{app_obj['id']}/addPassword",
                  {'passwordCredential': {'displayName': GEHEIM_NAAM, 'endDateTime': eind.isoformat().replace('+00:00', 'Z')}})
    waarde = json.dumps({'secret': nieuw['secretText'], 'end': eind.isoformat()})
    if bestaand:
        g.req('PATCH', f"/sites/{site}/lists/{lid}/items/{bestaand['id']}/fields", {'Waarde': waarde})
    else:
        g.req('POST', f'/sites/{site}/lists/{lid}/items', {'fields': {'Title': 'agenda-app', 'Waarde': waarde}})
    stap(f'Nieuw agendageheim aangemaakt (geldig tot {eind:%d-%m-%Y}) en in de verborgen app-lijst gezet.')


if __name__ == '__main__':
    main()
