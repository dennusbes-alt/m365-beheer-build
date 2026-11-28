"""Automatisch koppelen van de app aan een klant-tenant (GDAP) via de Partner Center API.

Bij GDAP mag een partner in een klant-tenant alleen apps gebruiken die daar zijn toegestaan; anders geeft
Microsoft AADSTS90099. Microsoft biedt daarvoor de Partner Center API "applicationconsents": de partner geeft
namens de klant toestemming voor de eigen (multi-tenant) app. Vereist in de GDAP-relatie van die klant de rol
Application Administrator of Cloud Application Administrator, en dat je account in de bijbehorende
beveiligingsgroep zit.
"""
from __future__ import annotations

import logging
import time
import uuid

from .auth import CLIENT_ID, GRAPH_RECHTEN, SHAREPOINT_RECHTEN, KoppelingNodig, LoginFout
from .clients import ApiFout, _sessie, _verstuur

log = logging.getLogger('m365beheer')

PC = 'https://api.partnercenter.microsoft.com/v1/customers/{tid}/applicationconsents'
GRAPH_ID = '00000003-0000-0000-c000-000000000000'
EXO_ID = '00000002-0000-0ff1-ce00-000000000000'
SP_ID = '00000003-0000-0ff1-ce00-000000000000'
GRANTS = [
    {'enterpriseApplicationId': GRAPH_ID, 'scope': ','.join(GRAPH_RECHTEN)},
    {'enterpriseApplicationId': EXO_ID, 'scope': 'Exchange.Manage'},
    {'enterpriseApplicationId': SP_ID, 'scope': ','.join(SHAREPOINT_RECHTEN)},
]


def rechten_compleet(graph) -> bool:
    """Heeft de koppeling in deze klant-tenant alle rechten van deze app-versie? (Nieuwe versies kunnen rechten toevoegen.)"""
    sp = (graph.get(f"/servicePrincipals?$filter=appId eq '{CLIENT_ID}'&$select=id").get('value') or [None])[0]
    if not sp:
        return False
    nodig = {GRAPH_ID: set(GRAPH_RECHTEN), EXO_ID: {'Exchange.Manage'}, SP_ID: set(SHAREPOINT_RECHTEN)}
    heeft: dict[str, set] = {}
    for gr in graph.all(f"/oauth2PermissionGrants?$filter=clientId eq '{sp['id']}'"):
        res = graph.get(f"/servicePrincipals/{gr['resourceId']}?$select=appId").get('appId')
        heeft.setdefault(res, set()).update(s.lower() for s in (gr.get('scope') or '').split())
    return all({s.lower() for s in v} <= heeft.get(k, set()) for k, v in nodig.items())
UITLEG = ('Controleer in de GDAP-relatie met deze klant dat de rol Application Administrator of Cloud Application '
          'Administrator is toegewezen, en dat jouw account in de beveiligingsgroep van die toewijzing zit.')


def _pc(auth, methode: str, tid: str, body: dict | None = None, pad: str = ''):
    h = {'Authorization': 'Bearer ' + auth.token(auth.home_tenant, 'pc'), 'Accept': 'application/json',
         'ms-correlationid': str(uuid.uuid4()), 'ms-requestid': str(uuid.uuid4())}
    return _verstuur(_sessie(), methode, PC.format(tid=tid) + pad, json=body, headers=h, timeout=60)


def _melding(r) -> str:
    try:
        j = r.json()
        return str(j.get('description') or j.get('message') or j.get('error', {}).get('message') or r.text)[:300]
    except ValueError:
        return (r.text or r.reason or '')[:300]


def toestemming_geven(auth, tid: str) -> None:
    """Toestemming voor de app in de klant-tenant via Partner Center. Bestaat die al, dan wordt hij vernieuwd."""
    body = {'applicationId': CLIENT_ID, 'applicationGrants': GRANTS, 'displayName': 'Justdata M365 Beheer'}
    r = _pc(auth, 'POST', tid, body)
    if r.status_code == 409:   # bestaat al (mogelijk met te weinig rechten): opnieuw aanmaken
        _pc(auth, 'DELETE', tid, pad='/' + CLIENT_ID)
        time.sleep(2)
        r = _pc(auth, 'POST', tid, body)
    if r.status_code == 400:   # sommige tenants willen één resource per aanvraag
        for g in GRANTS:
            r = _pc(auth, 'POST', tid, {**body, 'applicationGrants': [g]})
            if r.status_code not in (200, 201, 409):
                break
    if r.status_code not in (200, 201, 409):
        if r.status_code in (401, 403):
            raise ApiFout(f'Automatisch koppelen bij deze klant is niet toegestaan. {UITLEG} (Partner Center: {_melding(r)})', r.status_code)
        raise ApiFout(f'Automatisch koppelen bij deze klant is niet gelukt ({r.status_code}): {_melding(r)}. {UITLEG}', r.status_code)
    log.info('Koppeling gemaakt via Partner Center voor tenant %s', tid)


def koppelen(auth, tid: str, max_sec: int = 120, meld=None, soorten: tuple = ('graph', 'exo')) -> None:
    """Toestemming geven en wachten tot Microsoft die heeft verwerkt (meestal 5 tot 60 seconden).
    Wacht op Graph én Exchange: Exchange loopt soms achter (anders AADSTS65001 bij de Exchange-controle)."""
    toestemming_geven(auth, tid)
    begin, wacht = time.time(), 3.0
    laatste = ''
    while time.time() - begin < max_sec:
        time.sleep(wacht)
        auth.vergeet(tid)
        try:
            for s in soorten:
                auth.token(tid, s, interactief=False)
            log.info('Koppeling actief na %.0f s voor tenant %s', time.time() - begin, tid)
            return
        except KoppelingNodig as e:
            laatste = str(e)
        except LoginFout as e:
            laatste = str(e)
        if meld:
            meld(f'Wachten tot Microsoft de koppeling heeft verwerkt ({int(time.time() - begin)} s)...')
        wacht = min(wacht * 1.5, 10)
    raise ApiFout('De koppeling is gemaakt, maar Microsoft heeft hem nog niet verwerkt. Probeer het over een minuut opnieuw.'
                  + (f' ({laatste})' if laatste else ''))
