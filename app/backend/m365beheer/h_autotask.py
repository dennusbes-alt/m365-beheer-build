"""Autotask PSA: automatische werkregistratie (tickets, notities en tijd) voor acties in de app.

Zo werkt het:
- Per klant kies je in de ticketbalk: een bestaand ticket koppelen, automatisch een nieuw ticket, of niet registreren.
- Alleen echte, geslaagde wijzigingen tellen (nooit opvragen/rondklikken). Elke actie krijgt een realistische tijd uit
  `MINUTEN` (niet de kloktijd), en de beschrijving komt uit de activiteitregels van de actie zelf.
- Boeken = één notitie met alle acties + één tijdregel (afgerond) op naam van de medewerker, bij de juiste klant.
  Dat gebeurt bij het wisselen van klant, na een tijd zonder activiteit, of direct met "Nu boeken".
- Back-upcontrole: per medewerker per dag één intern ticket met een notitie en tijd per afvinkronde.

Autotask REST: zone via webservices.autotask.net/atservicesrest/v1.0/zoneInformation?user=..., headers Username, Secret,
APIIntegrationcode. Koppeling en instellingen staan gedeeld (verborgen SharePoint-lijst Justdata, zie h_backup.GEDEELD).
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
from types import SimpleNamespace
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .clients import ApiFout, achtergrond_fn
from .context import Ctx, api
from .rechten import eis_beheerder, eis_justdata, is_beheerder, is_justdata
from .h_backup import GEDEELD, _zet_auth, _AUTH

log = logging.getLogger('m365beheer')
ZONE = 'https://webservices.autotask.net/atservicesrest/v1.0/zoneInformation'

# Realistische tijd per actie (minuten). Alleen wijzigingen; opvragen telt nooit. Onbekende wijzigingen: STANDAARD.
MINUTEN: dict[str, tuple[str, int]] = {
    'user.create': ('Nieuwe gebruiker aangemaakt', 10), 'users.bulkcreate': ('Gebruikers aangemaakt (bulk)', 15),
    'user.update': ('Gebruikersgegevens gewijzigd', 3), 'user.block': ('Aanmelden geblokkeerd/toegestaan', 2),
    'user.license': ('Licenties gewijzigd', 3), 'users.bulklicense': ('Licenties gewijzigd (bulk)', 5),
    'user.password': ('Wachtwoord opnieuw ingesteld', 3), 'users.bulkpassword': ('Wachtwoorden opnieuw ingesteld (bulk)', 5),
    'user.revoke': ('Sessies afgemeld', 2), 'user.mfareset': ('MFA opnieuw ingesteld', 5), 'user.alias': ('E-mailalias gewijzigd', 3),
    'user.delete': ('Gebruiker verwijderd', 3), 'users.bulkdelete': ('Gebruikers verwijderd (bulk)', 5), 'offboard': ('Medewerker uit dienst gemeld', 20),
    'inactive.delete': ('Inactieve gebruikers opgeruimd', 5), 'user.onedrive': ('OneDrive ingericht', 3), 'users.bulkonedrive': ('OneDrive ingericht (bulk)', 5),
    'group.add': ('Lid/rechten toegevoegd', 2), 'group.remove': ('Lid/rechten verwijderd', 2), 'group.create': ('Groep/postvak aangemaakt', 5),
    'group.delete': ('Groep/postvak verwijderd', 3), 'group.deletemany': ('Groepen verwijderd', 5), 'shared.member.set': ('Postvakrechten gewijzigd', 3),
    'cal.set': ('Agendarechten ingesteld', 3), 'cal.remove': ('Agendarechten verwijderd', 2),
    'ar.set': ('Automatisch antwoord ingesteld', 3), 'fwd.set': ('Doorsturen ingesteld', 3), 'cu.forward.off': ('Doorsturen uitgezet', 2),
    'ret.mailbox.set': ('Archief/retentie per postvak ingesteld', 3), 'ret.policy.save': ('Retentiebeleid aangepast', 5),
    'ret.policy.delete': ('Retentiebeleid verwijderd', 3), 'ret.tag.save': ('Retentietag aangepast', 5), 'ret.tag.delete': ('Retentietag verwijderd', 3),
    'dom.add': ('Domein toegevoegd', 10), 'dom.verify': ('Domein geverifieerd', 5), 'dom.default': ('Standaarddomein gewijzigd', 3),
    'dom.exotype': ('Exchange-domeintype gewijzigd', 3), 'dom.delete': ('Domein verwijderd', 5),
    'dkim.create': ('DKIM ingericht', 5), 'dkim.set': ('DKIM aan/uit gezet', 3), 'dkim.rotate': ('DKIM-sleutel vernieuwd', 3),
    'ss.apply': ('Beveiligingsmaatregel toegepast (Secure Score)', 5), 'rd.apply': ('Beveiligingsmaatregel toegepast (compliance)', 5),
    'rd.nen.pdf': ('NEN 7510-rapport opgesteld', 10), 'cd.cleanup': ('Apparaten opgeschoond', 5),
    'dev.sync': ('Apparaat gesynchroniseerd', 2), 'dev.restart': ('Apparaat herstart', 2), 'dev.wipe': ('Apparaat gewist', 5),
    'dev.retire': ('Apparaat buiten gebruik gesteld', 5), 'dev.delete': ('Apparaat verwijderd', 3), 'dev.deletemany': ('Apparaten verwijderd (meerdere)', 5), 'dev.restartmany': ('Apparaten herstart (meerdere)', 3), 'dev.apreset': ('Autopilot Reset gestart', 5),
    'dev.group': ('Apparaatgroep gewijzigd', 2), 'ap.sync': ('Autopilot gesynchroniseerd', 2), 'ap.delete': ('Autopilot-apparaat verwijderd', 3),
    'ap.tag': ('Autopilot group tag gewijzigd', 2),
    'ca.save': ('Beleid voor voorwaardelijke toegang ingesteld', 10), 'ca.state': ('Beleid voor voorwaardelijke toegang aan/uit gezet', 3),
    'ca.delete': ('Beleid voor voorwaardelijke toegang verwijderd', 3), 'ca.loc.save': ('Benoemde locatie ingesteld', 5), 'ca.loc.delete': ('Benoemde locatie verwijderd', 2),
    'in.profile.assign': ('Intune-configuratieprofiel toegewezen', 5), 'in.profile.delete': ('Intune-configuratieprofiel verwijderd', 3),
    'in.app.add': ('App toegevoegd aan Intune', 10), 'in.app.assign': ('Intune-app toegewezen', 5), 'in.app.delete': ('Intune-app verwijderd', 3),
    'in.whfb.set': ('Windows Hello for Business ingesteld', 10), 'in.esp.set': ('Inschrijvingsstatuspagina ingesteld', 5),
    'in.restrict.set': ('Inschrijvingsbeperking gewijzigd', 5), 'in.limit.set': ('Apparaatlimiet gewijzigd', 2), 'in.mdm.set': ('Automatische Windows-inschrijving ingesteld', 5),
    'in.android.create': ('Android-inschrijvingsprofiel aangemaakt', 10), 'in.android.token': ('Android-inschrijvingstoken vernieuwd/ingetrokken', 3),
    'in.android.delete': ('Android-inschrijvingsprofiel verwijderd', 3),
    'spm.grant': ('SharePoint-maptoegang gegeven', 3), 'spm.revoke': ('SharePoint-maptoegang weggehaald', 2),
    'spm.inherit': ('SharePoint-mapmachtigingen hersteld', 2), 'spm.zoals': ('SharePoint-maptoegang gekopieerd van collega', 10), 'spm.onboard': ('SharePoint-maptoegang nieuwe medewerker ingericht', 5), 'sp.sharing.set': ('SharePoint-deelinstelling gewijzigd', 3),
    'auth.methods.set': ('Authenticatiemethoden gewijzigd', 5), 'auth.sspr': ('Wachtwoordherstel ingesteld', 3),
    'brand.set': ('Huisstijl aanmeldpagina aangepast', 10), 'brand.image': ('Afbeelding aanmeldpagina geplaatst', 5),
    'auto.start': ('Automatiseringsproces uitgevoerd', 5),
}
STANDAARD = ('Wijziging uitgevoerd', 2)
# Nooit registreren: app-instellingen, inloggen, koppelingen, administratie, back-up en Autotask zelf
NIET = re.compile(r'^(auth\.(login|logout|status)|tenant\.|prefs\.|open\.url|customers|gdap\.|adm\.|bk\.|at\.|dm\.|mg\.|sd\.|ig\.|adv\.|fa\.|ts\.|sa\.|pr\.|rmm\.|vr\.|sc\.|spm\.klant|update\.|job\.|auto\.(opslaan|verwijderen)|ping)')

STANDAARD_INSTELLINGEN = {
    'modus': 'vragen',          # vragen | auto | skip: wat de ticketbalk standaard doet bij de eerste actie bij een klant
    'autoBoeken': True, 'inactiefMin': 20,
    'status': None, 'statusKlaar': None, 'sluitAuto': True, 'priority': None, 'queueID': None, 'issueType': None,
    'subIssueType': None, 'source': None, 'ticketCategory': None, 'billingCodeID': None, 'noteType': None, 'publish': None,
    'internCompanyID': 0, 'backupMinPerKlant': 2, 'backupBillingCodeID': None,
    'tweedeLijn': [],           # Autotask-resource-id's van de tweede lijn (Servicedesk > eerste lijn: suggesties om tickets over te nemen)
}


# ---------------------------------------------------------------- Autotask-client
class Autotask:
    def __init__(self, gebruiker: str, geheim: str, code: str) -> None:
        self.h = {'Username': gebruiker, 'Secret': geheim, 'APIIntegrationcode': code, 'Content-Type': 'application/json', 'Accept': 'application/json'}
        self.s = requests.Session()
        self.s.mount('https://', requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=12))
        r = self.s.get(ZONE, params={'user': gebruiker}, timeout=30)
        if r.status_code >= 400 or not r.content:
            raise ApiFout(f'Autotask-zone niet gevonden voor deze API-gebruiker ({r.status_code}).')
        url = (r.json() or {}).get('url') or ''
        if not url:
            raise ApiFout('Autotask kent deze API-gebruiker niet (controleer de gebruikersnaam).')
        self.base = url.rstrip('/') + '/v1.0/'
        self.web = ((r.json() or {}).get('webUrl') or '').rstrip('/')   # voor links naar tickets in de webinterface
        self.picklist_cache: dict[str, dict] = {}
        self._pl_locks: dict[str, threading.Lock] = {}

    def req(self, methode: str, pad: str, body: Any = None) -> Any:
        url = pad if pad.startswith('http') else self.base + pad.lstrip('/')
        for poging in range(4):
            try:
                r = self.s.request(methode, url, json=body, headers=self.h, timeout=60)
            except requests.exceptions.RequestException as e:
                if poging == 3:
                    raise ApiFout(f'Autotask niet bereikbaar: {type(e).__name__}') from None
                time.sleep(0.5 * (poging + 1))
                continue
            if r.status_code == 429 and poging < 3:
                time.sleep(2 * (poging + 1))
                continue
            break
        if r.status_code == 401:
            raise ApiFout('Autotask weigert de aanmelding (401). Controleer gebruikersnaam, secret en integratiecode.', 401)
        try:
            j = r.json() if r.content else {}
        except ValueError:
            j = {}
        if r.status_code >= 400:
            fouten = j.get('errors') if isinstance(j, dict) else None
            raise ApiFout('Autotask: ' + ('; '.join(map(str, fouten)) if fouten else f'{r.status_code} {r.text[:200]}'), r.status_code)
        if methode == 'PATCH' and pad == 'Tickets' and isinstance(body, dict) and body.get('status') is not None and body.get('id'):
            for haak in NA_STATUS:   # bijv. service calls afronden als het ticket is afgerond
                try:
                    haak(self, body['id'], body['status'])
                except Exception as e:  # noqa: BLE001
                    log.info('Na statuswijziging ticket %s: %s', body.get('id'), e)
        return j

    def query(self, entiteit: str, filters: list, velden: list | None = None, max_: int = 500, limiet: int = 2000) -> list[dict]:
        body: dict = {'filter': filters, 'MaxRecords': min(max_, 500)}
        if velden:
            body['IncludeFields'] = velden
        uit, url = [], f'{entiteit}/query'
        while url and len(uit) < limiet:
            j = self.req('POST', url, body)
            uit.extend(j.get('items') or [])
            url = (j.get('pageDetails') or {}).get('nextPageUrl')
            if len(uit) >= max_:
                break
        return uit

    def picklists(self, entiteit: str) -> dict:
        if entiteit in self.picklist_cache:
            return self.picklist_cache[entiteit]
        with self._pl_locks.setdefault(entiteit, threading.Lock()):   # gelijktijdige verzoeken wachten op één opvraging
            return self._picklists(entiteit)

    def _picklists(self, entiteit: str) -> dict:
        if entiteit not in self.picklist_cache:
            velden = self.req('GET', f'{entiteit}/entityInformation/fields').get('fields') or []
            self.picklist_cache[entiteit] = {f['name']: [{'value': p.get('value'), 'label': p.get('label'), 'default': bool(p.get('isDefaultValue')),
                                                           'parent': p.get('parentValue')}
                                                          for p in (f.get('picklistValues') or []) if p.get('isActive', True)]
                                             for f in velden if f.get('isPickList')}
        return self.picklist_cache[entiteit]


_AT: dict = {}
_at_lock = threading.Lock()
NA_STATUS: list = []


def _heeft_bedrijf(b: dict) -> bool:
    """companyId 0 is het interne bedrijf (bijv. Justdata zelf) en dus wel een bedrijf; alleen leeg/None is geen bedrijf."""
    return b.get('companyId') not in (None, '')   # haken na PATCH Tickets met een status (h_servicecall)


def _sleutel() -> tuple[str, str, str] | None:
    w = GEDEELD.lees('autotask')
    if not w:
        return None
    try:
        d = json.loads(w[1])
        return w[0], d['secret'], d['code']
    except (ValueError, KeyError, TypeError):
        return None


def _at() -> Autotask:
    sl = _sleutel()
    if not sl:
        raise ApiFout('Autotask is nog niet gekoppeld (startscherm > Autotask).')
    with _at_lock:
        if _AT.get('sl') != sl:
            _AT.update(sl=sl, client=Autotask(*sl), me={})
        return _AT['client']


def _instellingen() -> dict:
    w = GEDEELD.lees_raw('autotask-instellingen')
    try:
        return {**STANDAARD_INSTELLINGEN, **(json.loads(w) if w else {})}
    except ValueError:
        return dict(STANDAARD_INSTELLINGEN)


def _klanten() -> dict:
    w = GEDEELD.lees_raw('autotask-klanten')
    try:
        return json.loads(w) if w else {}
    except ValueError:
        return {}


def _l1_queue():
    """Nieuwe tickets uit de app landen in de servicedesk-queue (L1), tenzij in de instellingen een andere queue staat."""
    try:
        from .h_sdniveau import inrichting
        return inrichting().get('l1Queue')
    except (ValueError, ApiFout):
        return None


def _medewerkers() -> dict:
    w = GEDEELD.lees_raw('autotask-medewerkers', 120)
    try:
        return json.loads(w) if w else {}
    except ValueError:
        return {}


def _ik(at: Autotask) -> dict:
    """De Autotask-medewerker (resource) van wie de app gebruikt: eerst de koppeling uit het tabblad Autotask
    (bijv. meerdere logins op één gedeelde servicedesk-medewerker), anders op e-mailadres. Met zijn standaard servicedeskrol."""
    a = _AUTH.get('auth')
    mail = str(((a.account or {}) if a else {}).get('username') or '').lower()
    if _AT.get('me', {}).get('mail') == mail and _AT['me'].get('id') and time.time() - _AT['me'].get('t', 0) < 300:
        return _AT['me']
    if not mail:
        raise ApiFout('Niet aangemeld.')
    gekoppeld = _medewerkers().get(mail)
    if gekoppeld:
        r = [at.req('GET', f"Resources/{gekoppeld['id']}").get('item') or {}]
    else:
        r = at.query('Resources', [{'op': 'eq', 'field': 'email', 'value': mail}], ['id', 'firstName', 'lastName', 'email', 'isActive'], 5)
    if not r or not r[0].get('id'):
        raise ApiFout(f'Er is geen Autotask-medewerker gekoppeld aan {mail}. Koppel je login op het startscherm > Autotask > Medewerkers.')
    res = r[0]
    rollen = at.query('ResourceServiceDeskRoles', [{'op': 'eq', 'field': 'resourceID', 'value': res['id']}, {'op': 'eq', 'field': 'isActive', 'value': True}],
                      None, 50)
    rol = next((x['roleID'] for x in rollen if x.get('isDefault')), rollen[0]['roleID'] if rollen else None)
    _AT['me'] = {'mail': mail, 'id': res['id'], 'name': f"{res.get('firstName', '')} {res.get('lastName', '')}".strip(), 'role': rol, 't': time.time()}
    return _AT['me']


# ---------------------------------------------------------------- Werkregistratie (in het geheugen, per klant)
_SESSIES: dict[str, dict] = {}
_GEBOEKT: list[dict] = []
_wl = threading.RLock()


def _sessie(tid: str, naam: str = '') -> dict:
    with _wl:
        s = _SESSIES.get(tid)
        if not s:
            s = _SESSIES[tid] = {'tid': tid, 'klant': naam, 'mode': None, 'ticket': None, 'items': [], 'laatst': time.time(), 'fout': ''}
        if naam:
            s['klant'] = naam
        return s


def registreer(staat, tid: str, actie: str, regels: list[str]) -> None:
    """Na elke geslaagde wijziging (aangeroepen door de server). Opvragen komt hier nooit."""
    if not tid or NIET.match(actie):
        return
    try:
        if not _sleutel():
            return
    except Exception:  # noqa: BLE001
        return
    t = staat.tenants.get(tid)
    s = _sessie(tid, t.naam if t else '')
    if s['mode'] is None:
        s['mode'] = _instellingen().get('modus') if _instellingen().get('modus') in ('auto', 'skip') else None
    if s['mode'] == 'skip':
        return
    label, minuten = MINUTEN.get(actie, STANDAARD)
    tekst = ' '.join(r for r in regels if not r.startswith('FOUT')) or label
    with _wl:
        if LICENTIE.search(f'{actie} {label} {tekst}'):
            s['licentie'] = True   # licentiewijziging: ticket gaat naar 'Ready to Invoice' (validatie en factuur)
        s['items'].append({'id': f'{time.time():.6f}', 'ts': datetime.now(timezone.utc).isoformat(), 'actie': actie, 'label': label,
                           'tekst': tekst[:600], 'minuten': minuten, 'skip': False})
        s['laatst'] = time.time()


def _afgerond(min_: float, inst: dict | None = None) -> int:
    """Tijd gaat altijd per 15 minuten naar boven, met minimaal 15 minuten (nooit per minuut)."""
    return int(max(1, math.ceil(max(float(min_), 1) / 15)) * 15)


def _titel(items: list[dict], klant: str) -> str:
    labels = []
    for i in items:
        if i['label'] not in labels:
            labels.append(i['label'])
    if len(items) == 1:
        t = items[0]['tekst']
        return (t if len(t) <= 90 else items[0]['label'])[:250]
    return f"Microsoft 365: {', '.join(labels[:3])}{' e.a.' if len(labels) > 3 else ''}"[:250]


def _notitie_tekst(items: list[dict], medewerker: str) -> str:
    regels = [f"Uitgevoerd via Microsoft 365 beheer door {medewerker}:", '']
    for i in items:
        t = datetime.fromisoformat(i['ts']).astimezone().strftime('%H:%M')
        regels.append(f"- {t} {i['label']}: {i['tekst']}" if i['tekst'] != i['label'] else f"- {t} {i['label']}")
    return '\n'.join(regels)[:31000]


def _notitie(at: Autotask, ticket_id: int, titel: str, tekst: str, inst: dict, bestaand: int | None = None, soort: str = 'ticket') -> int | None:
    """Notitie maken (op een ticket of een projecttaak), of een eerder gemaakte notitie van deze werksessie bijwerken. Geeft het id terug."""
    ouder, veld, los = ('Tasks', 'taskID', 'TaskNotes') if soort == 'taak' else ('Tickets', 'ticketID', 'TicketNotes')
    if bestaand:
        try:
            at.req('PATCH', f'{ouder}/{ticket_id}/Notes', {'id': bestaand, 'title': titel[:250], 'description': tekst})
            return bestaand
        except ApiFout as e:
            log.info('Notitie bijwerken niet gelukt (%s), nieuwe notitie', e)
    body = {veld: ticket_id, 'title': titel[:250], 'description': tekst, 'publish': inst.get('publish') or 1,
            'noteType': (inst.get('taakNoteType') if soort == 'taak' else inst.get('noteType')) or 1}
    try:
        r = at.req('POST', f'{ouder}/{ticket_id}/Notes', body)
    except ApiFout as e:
        if e.status not in (404, 405):
            if soort == 'taak' and 'notetype' in str(e).lower():   # notitiesoorten van taken wijken soms af: zonder soort opnieuw
                body.pop('noteType', None)
                r = at.req('POST', f'{ouder}/{ticket_id}/Notes', body)
                return r.get('itemId') if isinstance(r, dict) else None
            raise
        r = at.req('POST', los, body)
    return r.get('itemId') if isinstance(r, dict) else None


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _tijdregel(at: Autotask, ticket: dict, ik: dict, minuten: int, samenvatting: str, inst: dict, billing=None,
               bestaand: dict | None = None, start: datetime | None = None) -> dict:
    """Tijdregel maken, of de tijdregel van deze werksessie bijwerken (zelfde start, nieuwe duur per kwartier). Geeft {id, start} terug."""
    if bestaand and bestaand.get('id'):
        start = datetime.fromisoformat(bestaand['start'])
        try:
            at.req('PATCH', 'TimeEntries', {'id': bestaand['id'], 'endDateTime': _iso(start + timedelta(minutes=minuten)),
                                             'hoursWorked': round(minuten / 60, 2), 'summaryNotes': samenvatting[:31000]})
            return bestaand
        except ApiFout as e:
            log.info('Tijdregel bijwerken niet gelukt (%s), nieuwe tijdregel', e)
    if start is not None:
        eind = start + timedelta(minutes=minuten)
    else:
        eind = datetime.now(timezone.utc).replace(microsecond=0)
        start = eind - timedelta(minutes=minuten)
    body = {('taskID' if ticket.get('soort') == 'taak' else 'ticketID'): ticket['id'], 'resourceID': ik['id'], 'roleID': ik['role'], 'startDateTime': _iso(start),
            'endDateTime': _iso(eind), 'hoursWorked': round(minuten / 60, 2), 'summaryNotes': samenvatting[:31000]}
    if billing or inst.get('billingCodeID'):
        body['billingCodeID'] = billing or inst.get('billingCodeID')
    try:
        r = at.req('POST', 'TimeEntries', body)
    except ApiFout as e:
        rol = ticket.get('assignedResourceRoleID') or ticket.get('assignedResourceroleID')
        if rol and rol != body['roleID'] and 'role' in str(e).lower():   # rol moet gelijk zijn aan die op het ticket
            body['roleID'] = rol
            r = at.req('POST', 'TimeEntries', body)
        else:
            raise
    return {'id': r.get('itemId') if isinstance(r, dict) else None, 'start': start.isoformat()}


def _nieuw_ticket(at: Autotask, company: int, titel: str, omschrijving: str, ik: dict, inst: dict, contact: int | None = None,
                 contract: int | None = None, zelf: bool = True) -> dict:
    """contract: ticket op dat contract (bijv. vaste prijs). zelf=False: niet op jouw naam maar in de queue (L1)."""
    lijst_wissen(company, ('t',))
    pl = at.picklists('Tickets')
    def std(veld, verplicht: bool = False, voorkeur: tuple = ()):
        """Ingestelde waarde, anders de standaardwaarde uit Autotask; is een verplicht veld daar niet ingesteld,
        dan een passende waarde uit de lijst (bijv. prioriteit 'Normal'/'Medium'), anders de eerste."""
        if inst.get(veld) is not None:
            return inst.get(veld)
        lijst = pl.get(veld, [])
        # Werkwijze Justdata: eerst de voorkeur (prioriteit Low, status In Progress), dan de standaard van Autotask, dan de eerste
        w = next((p['value'] for p in lijst if str(p.get('label') or '').strip().lower() in voorkeur), None)
        if w is None:
            w = next((p['value'] for p in lijst if p['default']), None)
        if w is None and verplicht and lijst:
            w = lijst[0]['value']
        return w
    body = {'companyID': company, 'title': titel, 'description': omschrijving[:7900],
            'status': std('status', True, ('in progress', 'in behandeling', 'bezig')) or 1,
            'priority': std('priority', True, ('low', 'laag', 'p4', 'p4 - low')),
            'queueID': inst.get('queueID') or _l1_queue(), 'issueType': inst.get('issueType'), 'subIssueType': inst.get('subIssueType'), 'source': std('source'),
            'ticketCategory': inst.get('ticketCategory'), 'dueDateTime': (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'assignedResourceID': ik['id'] if zelf else None, 'assignedResourceroleID': ik['role'] if zelf else None, 'contactID': contact,
            'contractID': contract}
    body = {k: v for k, v in body.items() if v is not None}
    r = at.req('POST', 'Tickets', body)
    tid_ = r.get('itemId') or (r.get('item') or {}).get('id')
    t = at.req('GET', f'Tickets/{tid_}').get('item') or {'id': tid_}
    return {'id': t['id'], 'number': t.get('ticketNumber', ''), 'title': t.get('title', titel), 'assignedResourceroleID': t.get('assignedResourceroleID')}


SAMEN_SEC = 3600   # vervolgacties binnen een uur op hetzelfde ticket = dezelfde tijdregel (bijgewerkt, opnieuw per kwartier afgerond)


def _vorige(s: dict, ticket: dict | None) -> dict | None:
    v = s.get('vorig')
    if v and ticket and v.get('ticket_id') == ticket.get('id') and time.time() - v.get('t', 0) < SAMEN_SEC:
        return v
    return None


LICENTIE = re.compile(r'licen', re.I)


def eindstatussen(at: Autotask, inst: dict | None = None) -> dict:
    """De twee manieren om een ticket af te ronden bij Justdata: 'complete' (incidenten) en 'invoice' ('Ready to Invoice':
    licentiewijzigingen, zodat de administratie valideert en factureert). Waarden uit de picklist; None als die er niet is."""
    inst = inst if inst is not None else _instellingen()
    pl = at.picklists('Tickets').get('status', [])
    klaar = _klaar(at, 'Tickets')
    complete = inst.get('statusKlaar') or next((p['value'] for p in pl if re.fullmatch(r'\s*(complete|completed|voltooid|afgerond|gesloten|closed)\s*', str(p.get('label') or ''), re.I)), None) \
        or (min(klaar) if klaar else None)
    invoice = next((p['value'] for p in pl if re.search(r'ready\s*to\s*invoice', str(p.get('label') or ''), re.I)), None) \
        or next((p['value'] for p in pl if re.search(r'invoic|factur', str(p.get('label') or ''), re.I)), None)
    return {'complete': complete, 'invoice': invoice}


def _afsluiten(at: Autotask, s: dict, inst: dict) -> None:
    t = s.get('ticket')
    if not t:
        return
    status = inst['statusKlaar']
    if s.get('licentie'):
        status = eindstatussen(at, inst)['invoice'] or status
    try:
        at.req('PATCH', 'Tickets', {'id': t['id'], 'status': status})
    except ApiFout as e:
        log.info('Ticket afsluiten niet gelukt: %s', e)
    with _wl:
        s['ticket'] = None   # volgende acties krijgen een nieuw ticket
        s['vorig'] = None
        s['licentie'] = False


def boek(tid: str, wie: str = 'handmatig') -> dict:
    """Openstaande acties van een klant boeken: (zo nodig) ticket, notitie en tijdregel."""
    with _wl:
        s = _SESSIES.get(tid)
        if not s or not s['items']:
            return {'booked': 0}
        items = [i for i in s['items'] if not i['skip']]
        if s['mode'] == 'skip' or not items:
            s['items'] = []
            return {'booked': 0}
        if s['mode'] not in ('ticket', 'auto'):
            raise ApiFout('Kies eerst een ticket of "automatisch nieuw ticket" in de ticketbalk.')
        s['items'] = [i for i in s['items'] if i not in items and not i['skip']]   # meteen leeg: dubbel boeken kan niet
    inst = _instellingen()
    try:
        at = _at()
        ik = _ik(at)
        ticket = s['ticket']
        vorig = _vorige(s, ticket)
        alle = (vorig['items'] if vorig else []) + items          # alle acties van deze werksessie op dit ticket
        minuten = _afgerond(sum(float(i['minuten']) for i in alle), inst)
        tekst = _notitie_tekst(alle, ik['name'])
        if not ticket:
            kl = _klanten().get(tid)
            if not kl:
                raise ApiFout(f"Koppel {s['klant'] or 'deze klant'} eerst aan een Autotask-bedrijf (ticketbalk > Ticket).")
            ticket = _nieuw_ticket(at, kl['companyId'], _titel(alle, s['klant']), tekst, ik, inst, (s.get('contact') or {}).get('id'))
            ticket['door_app'] = True
            s['ticket'] = ticket
        elif ticket.get('door_app') and vorig and ticket.get('soort') != 'taak':
            # Automatisch ticket van de app: onderwerp en beschrijving bijwerken naar alle acties samen
            nieuw = _titel(alle, s['klant'])
            try:
                at.req('PATCH', 'Tickets', {'id': ticket['id'], 'title': nieuw, 'description': tekst[:7900]})
                ticket['title'] = nieuw
            except ApiFout as e:
                log.info('Ticketonderwerp bijwerken niet gelukt: %s', e)
        noot = _notitie(at, ticket['id'], 'Microsoft 365 beheer: uitgevoerde acties', tekst, inst, vorig.get('noot') if vorig else None,
                        ticket.get('soort') or 'ticket')
        tijd = _tijdregel(at, ticket, ik, minuten, tekst, inst, bestaand=vorig.get('tijd') if vorig else None)
        with _wl:
            s['vorig'] = {'ticket_id': ticket['id'], 'items': alle, 'noot': noot, 'tijd': tijd, 't': time.time(), 'minuten': minuten}
        if s['mode'] == 'auto' and inst.get('sluitAuto') and inst.get('statusKlaar') and wie.startswith('automatisch'):
            _afsluiten(at, s, inst)
        regel = {'at': datetime.now().strftime('%d-%m %H:%M'), 'klant': s['klant'], 'ticket': ticket.get('number') or ticket['id'],
                 'titel': ticket.get('title', ''), 'minuten': minuten, 'acties': len(alle), 'wie': wie + (' (bijgewerkt)' if vorig else '')}
        with _wl:   # dezelfde registratie bijgewerkt: oude regel in het overzicht vervangen
            _GEBOEKT[:] = [g for g in _GEBOEKT if not (vorig and g.get('ticket') == regel['ticket'] and g.get('sessie') == id(s))]
        regel['sessie'] = id(s)
        with _wl:
            _GEBOEKT.insert(0, regel)
            del _GEBOEKT[50:]
            s['fout'] = ''
        log.info('Autotask: %d actie(s) geboekt op %s (%d min, %s)', len(items), regel['ticket'], minuten, wie)
        return {'booked': len(items), 'minutes': minuten, 'ticket': regel['ticket']}
    except Exception as e:
        with _wl:   # niets kwijt: terugzetten
            s['items'] = items + s['items']
            s['fout'] = str(e)[:300]
        raise


def _bewaker() -> None:
    """Boekt automatisch na een tijd zonder activiteit (als de klant een ticket of 'automatisch' heeft)."""
    while True:
        time.sleep(60)
        try:
            inst = _instellingen() if _AUTH.get('auth') else None
            if not inst or not inst.get('autoBoeken'):
                continue
            grens = time.time() - 60 * int(inst.get('inactiefMin') or 20)
            for tid, s in list(_SESSIES.items()):
                if s['items'] and s['mode'] in ('ticket', 'auto') and s['laatst'] < grens and not s['fout']:
                    try:
                        boek(tid, 'automatisch (geen activiteit)')
                    except Exception as e:  # noqa: BLE001
                        log.info('Automatisch boeken niet gelukt: %s', e)
                elif (not s['items'] and s['mode'] == 'auto' and s.get('ticket') and s['laatst'] < grens
                      and inst.get('sluitAuto') and inst.get('statusKlaar')):
                    try:
                        _afsluiten(_at(), s, inst)
                    except Exception as e:  # noqa: BLE001
                        log.info('Automatisch afsluiten niet gelukt: %s', e)
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=_bewaker, daemon=True, name='autotask').start()


# ---------------------------------------------------------------- Back-upcontrole
_BK: dict = {}          # lopende back-upcontrole van deze medewerker: {'ticket', 'start', 'items': [...]}
_bk_lock = threading.Lock()


def fout_melden(wat: str, fout: str) -> None:
    """Mislukte registratie zichtbaar maken in de werklog (tabblad Autotask)."""
    with _wl:
        _GEBOEKT.insert(0, {'at': datetime.now().strftime('%d-%m %H:%M'), 'klant': wat, 'ticket': 'MISLUKT', 'titel': fout[:200], 'minuten': 0, 'acties': 0,
                            'wie': 'fout'})
        del _GEBOEKT[50:]


def _datum_at(w) -> datetime | None:
    try:
        return datetime.fromisoformat(str(w).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


def bk_sessie() -> dict | None:
    with _bk_lock:
        return dict(_BK, items=list(_BK.get('items') or [])) if _BK else None


def bk_afgevinkt(klanten: list[str], uitkomst: str, opmerking: str = '') -> bool:
    """Afvinken tijdens een gestarte back-upcontrole: alleen verzamelen (niets naar Autotask, dat gebeurt bij afronden)."""
    with _bk_lock:
        if not _BK:
            return False
        nu = datetime.now().strftime('%H:%M')
        for k in klanten:
            _BK['items'] = [i for i in _BK['items'] if i['klant'] != k]   # opnieuw afvinken = laatste uitkomst telt
            _BK['items'].append({'klant': k, 'uitkomst': uitkomst, 'opmerking': opmerking, 'om': nu})
        return True


def _bk_uit(s: dict | None) -> dict | None:
    if not s:
        return None
    sec = time.time() - s['start']
    return {'ticket': s['ticket'].get('number') or s['ticket']['id'], 'titel': s['ticket'].get('title', ''), 'sinds': datetime.fromtimestamp(s['start']).strftime('%H:%M'),
            'minuten': int(sec // 60), 'afgerond': _afgerond(sec / 60), 'items': s['items']}


@api('at.bk.status')
def at_bk_status(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    return {'configured': _sleutel() is not None, 'session': _bk_uit(bk_sessie())}


@api('at.bk.start')
def at_bk_start(c: Ctx, b: dict) -> dict:
    """Back-upcontrole starten: intern ticket (intern bedrijf, op naam van de medewerker, In Progress)."""
    _zet_auth(c)
    with _bk_lock:
        if _BK:
            return {'session': _bk_uit(dict(_BK))}
    inst = _instellingen()
    at = _at()
    ik = _ik(at)
    titel = f"Back-upcontrole {datetime.now():%d-%m-%Y %H:%M} - {ik['name']}"
    ticket = _nieuw_ticket(at, int(inst.get('internCompanyID') or 0), titel,
                           f"Controle van de back-ups (Datto/Unitrends) door {ik['name']}. De afgevinkte klanten en de bestede tijd worden bij het afronden toegevoegd.",
                           ik, {**inst, 'issueType': inst.get('backupIssueType') or inst.get('issueType')})
    with _bk_lock:
        _BK.clear()
        _BK.update(ticket=ticket, start=time.time(), items=[], ik=ik)
    c.L(f"Back-upcontrole gestart: intern ticket {ticket.get('number') or ticket['id']}.")
    return {'session': _bk_uit(dict(_BK))}


def _bk_notitie(s: dict, ik: dict, eind: float) -> str:
    items = s['items']
    regels = [f"Back-upcontrole door {ik['name']}, {datetime.fromtimestamp(s['start']):%d-%m-%Y %H:%M} - {datetime.fromtimestamp(eind):%H:%M}.",
              f"{len(items)} klant(en) gecontroleerd: " + ', '.join(f"{n} {u.lower()}" for u in ('OK', 'Actie nodig', 'Opgelost')
                                                            if (n := len([i for i in items if i['uitkomst'] == u]))) + '.', '']
    for u in ('Actie nodig', 'Opgelost', 'OK'):
        groep = [i for i in items if i['uitkomst'] == u]
        if not groep:
            continue
        regels.append({'OK': 'In orde:', 'Actie nodig': 'Actie nodig:', 'Opgelost': 'Opgelost tijdens de controle:'}[u])
        for i in groep:
            regels.append(f"- {i['klant']} ({i['om']})" + (f": {i['opmerking']}" if i['opmerking'] else ''))
        regels.append('')
    return '\n'.join(regels).strip()[:31000]


@api('at.bk.stop')
def at_bk_stop(c: Ctx, b: dict) -> dict:
    """Back-upcontrole afronden: één notitie met alle afgevinkte klanten, één tijdregel met de totale tijd
    (start tot afronden, per kwartier naar boven) en het ticket afsluiten. Met cancel: alleen stoppen."""
    _zet_auth(c)
    with _bk_lock:
        s = dict(_BK) if _BK else None
    if not s:
        raise ApiFout('Er loopt geen back-upcontrole.')
    inst = _instellingen()
    at = _at()
    ik = s.get('ik') or _ik(at)
    ticket = s['ticket']
    eind = time.time()
    if b.get('cancel') or not s['items']:
        try:
            _notitie(at, ticket['id'], 'Back-upcontrole geannuleerd', 'Back-upcontrole gestopt zonder afgevinkte klanten.', inst)
            at.req('PATCH', 'Tickets', {'id': ticket['id'], 'status': inst.get('statusKlaar') or min(_klaar(at, 'Tickets'))})
        except ApiFout as e:
            log.info('Back-upcontrole annuleren: %s', e)
        with _bk_lock:
            _BK.clear()
        c.L('Back-upcontrole gestopt zonder registratie.')
        return {'booked': 0}
    tekst = _bk_notitie(s, ik, eind)
    minuten = _afgerond((eind - s['start']) / 60)
    _notitie(at, ticket['id'], f"Back-upcontrole: {len(s['items'])} klant(en)", tekst, inst)
    _tijdregel(at, ticket, ik, minuten, tekst, inst, inst.get('backupBillingCodeID'), start=datetime.fromtimestamp(s['start'], timezone.utc).replace(microsecond=0))
    try:
        at.req('PATCH', 'Tickets', {'id': ticket['id'], 'description': tekst[:7900], 'status': inst.get('statusKlaar') or min(_klaar(at, 'Tickets'))})
    except ApiFout as e:
        log.info('Back-upticket afsluiten niet gelukt: %s', e)
    with _bk_lock:
        _BK.clear()
    nr = ticket.get('number') or ticket['id']
    with _wl:
        _GEBOEKT.insert(0, {'at': datetime.now().strftime('%d-%m %H:%M'), 'klant': 'Intern (back-upcontrole)', 'ticket': nr, 'titel': ticket.get('title', ''),
                            'minuten': minuten, 'acties': len(s['items']), 'wie': 'back-upcontrole'})
        del _GEBOEKT[50:]
    c.L(f"Back-upcontrole afgerond: {len(s['items'])} klant(en), {minuten} min geboekt op ticket {nr} (afgesloten).")
    return {'booked': len(s['items']), 'minutes': minuten, 'ticket': nr}


# ---------------------------------------------------------------- API voor de interface
def _sessie_uit(s: dict) -> dict:
    nieuw = sum(float(i['minuten']) for i in s['items'] if not i['skip'])
    vorig = _vorige(s, s.get('ticket'))
    eerder = sum(float(i['minuten']) for i in vorig['items']) if vorig else 0
    return {'mode': s['mode'], 'ticket': s['ticket'], 'klant': s['klant'], 'fout': s['fout'], 'items': s['items'], 'minuten': nieuw,
            'contact': s.get('contact'), 'contactGekozen': 'contact' in s, 'licentie': bool(s.get('licentie')),
            'afgerond': _afgerond(nieuw + eerder) if nieuw else 0,
            'eerder': {'minuten': eerder, 'geboekt': vorig['minuten'], 'om': datetime.fromtimestamp(vorig['t']).strftime('%H:%M'), 'acties': len(vorig['items'])} if vorig else None}


@api('at.status')
def at_status(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    gekoppeld = _sleutel() is not None
    uit = {'admin': is_beheerder(c.staat), 'configured': gekoppeld, 'settings': _instellingen(), 'customers': _klanten(), 'booked': _GEBOEKT[:20], 'me': None, 'error': ''}
    if gekoppeld and b.get('me'):
        try:
            uit['me'] = _ik(_at())
        except ApiFout as e:
            uit['error'] = str(e)
    if c.tid:
        s = _sessie(c.tid)
        uit['session'] = _sessie_uit(s)
        uit['company'] = _klanten().get(c.tid)
    uit['open'] = [{'tid': t, 'klant': s['klant'], 'aantal': len([i for i in s['items'] if not i['skip']]), 'mode': s['mode']}
                   for t, s in _SESSIES.items() if s['items']]
    return uit


@api('at.keys.set')
def at_keys_set(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    g, geheim, code = (str(b.get(k) or '').strip() for k in ('user', 'secret', 'code'))
    if not (g and geheim and code):
        raise ApiFout('Vul gebruikersnaam, secret en integratiecode (Tracking Identifier) in.')
    at = Autotask(g, geheim, code)
    at.query('Resources', [{'op': 'eq', 'field': 'isActive', 'value': True}], ['id'], 1)   # test
    GEDEELD.schrijf_raw('backup-autotask', json.dumps({'a': g, 'b': json.dumps({'secret': geheim, 'code': code})}))
    GEDEELD.cache.pop('autotask', None)
    _AT.clear()
    c.L('Autotask gekoppeld (gedeeld met alle Justdata-collega\'s).')
    return {}


@api('at.keys.delete')
def at_keys_delete(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    GEDEELD.schrijf_raw('backup-autotask', None)
    GEDEELD.cache.pop('autotask', None)
    _AT.clear()
    c.L('Autotask-koppeling verwijderd (voor iedereen).')
    return {}


@api('at.opties')
def at_opties(c: Ctx, b: dict) -> dict:
    """Keuzelijsten voor de instellingen (uit Autotask zelf)."""
    eis_beheerder(c)
    _zet_auth(c)
    at = _at()
    t = at.picklists('Tickets')
    n = at.picklists('TicketNotes')
    werk = at.query('BillingCodes', [{'op': 'eq', 'field': 'useType', 'value': 1}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'name'], 500)
    return {'status': t.get('status', []), 'priority': t.get('priority', []), 'queueID': t.get('queueID', []), 'issueType': t.get('issueType', []),
            'subIssueType': t.get('subIssueType', []), 'source': t.get('source', []), 'ticketCategory': t.get('ticketCategory', []),
            'noteType': n.get('noteType', []), 'publish': n.get('publish', []), 'billingCodes': [{'value': w['id'], 'label': w['name']} for w in werk]}


@api('at.settings.save')
def at_settings_save(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    inst = {k: b['settings'].get(k) for k in STANDAARD_INSTELLINGEN if k in (b.get('settings') or {})}
    GEDEELD.schrijf_raw('autotask-instellingen', json.dumps(inst))
    c.L('Autotask-instellingen opgeslagen (voor iedereen).')
    return {}


@api('at.bedrijven')
def at_bedrijven(c: Ctx, b: dict) -> dict:
    """Autotask-bedrijven zoeken op naam; zonder zoektekst voorstellen op basis van de domeinen/naam van de klant."""
    _zet_auth(c)
    at = _at()
    q = str(b.get('q') or '').strip()
    velden = ['id', 'companyName', 'webAddress', 'isActive']
    if q:
        r = at.query('Companies', [{'op': 'contains', 'field': 'companyName', 'value': q}, {'op': 'eq', 'field': 'isActive', 'value': True}], velden, 25)
    else:
        tid = str(b.get('tid') or c.tid or '')
        t = c.staat.tenants.get(tid) if tid else None
        doms = [d['id'] for d in (t.domeinen if t else []) if not d['id'].lower().endswith('.onmicrosoft.com')][:10]
        if not doms and b.get('domain') and not str(b['domain']).lower().endswith('.onmicrosoft.com'):
            doms = [str(b['domain'])]
        r = []
        if doms:
            r = at.query('Companies', [{'op': 'or', 'items': [{'op': 'contains', 'field': 'webAddress', 'value': d} for d in doms]},
                                       {'op': 'eq', 'field': 'isActive', 'value': True}], velden, 10)
        naam = (t.naam if t else '') or str(b.get('name') or '')
        if not r and naam:
            woord = max(re.split(r'[\s,.]+', naam.strip()), key=len)
            r = at.query('Companies', [{'op': 'contains', 'field': 'companyName', 'value': woord}, {'op': 'eq', 'field': 'isActive', 'value': True}], velden, 10)
    return {'companies': [{'id': x['id'], 'name': x.get('companyName', ''), 'web': x.get('webAddress') or ''} for x in r]}


@api('at.klant.set')
def at_klant_set(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    alle = _klanten()
    tid = str(b.get('tid') or c.tid)
    if b.get('companyId') is None:
        alle.pop(tid, None)
    else:
        alle[tid] = {'companyId': int(b['companyId']), 'name': str(b.get('name') or ''), 'tenant': str(b.get('tenantName') or '')}
    GEDEELD.schrijf_raw('autotask-klanten', json.dumps(alle))
    c.L(f"Klant gekoppeld aan Autotask-bedrijf {b.get('name') or ''}." if b.get('companyId') is not None else 'Klantkoppeling verwijderd.')
    return {}



# ---------------------------------------------------------------- Lijstcache (tickets/projecttaken per bedrijf)
# Autotask is traag (1-3 s per opvraging). Bekende lijst direct tonen en op de achtergrond verversen ('stale': de
# interface vraagt dan meteen de verse lijst op). Na het aanmaken van een ticket wordt de cache van het bedrijf gewist.
_LIJST: dict = {}
_lijst_lock = threading.Lock()
LIJST_VERS = 45          # seconden: binnen deze tijd geldt de lijst als actueel
LIJST_MAX = 15 * 60      # tot deze leeftijd: direct tonen + verversen


def _lijst(sleutel: tuple, fn, vers: bool = False) -> tuple[dict, bool]:
    with _lijst_lock:
        item = _LIJST.get(sleutel)
    leeftijd = time.time() - item[0] if item else 1e9
    if item and not vers and leeftijd < LIJST_VERS:
        return item[1], False
    if item and not vers and leeftijd < LIJST_MAX:
        def ververs():
            try:
                _LIJST[sleutel] = (time.time(), fn())
            except Exception as e:  # noqa: BLE001
                log.info('Autotask-lijst verversen: %s', str(e)[:160])
        threading.Thread(target=achtergrond_fn(ververs), daemon=True).start()
        return item[1], True
    res = fn()
    with _lijst_lock:
        _LIJST[sleutel] = (time.time(), res)
    return res, False


def lijst_wissen(company=None, soorten: tuple | None = None) -> None:
    with _lijst_lock:
        for k in [k for k in _LIJST if (company is None or k[1] == company) and (soorten is None or k[0] in soorten)]:
            _LIJST.pop(k, None)


def opwarmen_klant(tid: str) -> None:
    """Bij het openen van een klant (achtergrond): open tickets en projecttaken alvast ophalen."""
    try:
        if not is_justdata(SimpleNamespace(auth=_AUTH.get('auth'))) or not _sleutel():
            return
        kl = _klanten().get(tid)
        if not kl:
            return
        at = _at()
        for soort, fn in (('t', lambda: _tickets_ophalen(at, kl['companyId'], '')), ('p', lambda: _taken_ophalen(at, kl['companyId'], '')),
                          ('c', lambda: _contacten_ophalen(at, kl['companyId']))):
            _lijst((soort, kl['companyId'], ''), fn)
    except Exception as e:  # noqa: BLE001
        log.info('Autotask vooraf laden: %s', str(e)[:160])


@api('at.tickets')
def at_tickets(c: Ctx, b: dict) -> dict:
    """Open tickets van de gekoppelde klant, of zoeken op ticketnummer."""
    _zet_auth(c)
    at = _at()
    q = str(b.get('q') or '').strip()
    if re.match(r'^T\d{8}\.\d+$', q, re.I):
        return _tickets_uit(at, at.query('Tickets', [{'op': 'eq', 'field': 'ticketNumber', 'value': q.upper()}], _TICKETVELDEN, 5))
    kl = {'companyId': int(b['companyId'])} if _heeft_bedrijf(b) else _klanten().get(c.tid)   # meekijken: elk bedrijf (ook 0 = intern)
    if not kl:
        return {'tickets': [], 'needCompany': True}
    res, oud = _lijst(('t', kl['companyId'], q), lambda: _tickets_ophalen(at, kl['companyId'], q), bool(b.get('fresh')))
    return {**res, 'stale': oud}


_TICKETVELDEN = ['id', 'ticketNumber', 'title', 'status', 'assignedResourceID', 'assignedResourceroleID', 'companyID', 'createDate', 'lastActivityDate']


def _tickets_ophalen(at: Autotask, company: int, q: str) -> dict:
    inst = _instellingen()
    f = [{'op': 'eq', 'field': 'companyID', 'value': company}]
    for w in _klaar(at, 'Tickets') | ({inst['statusKlaar']} if inst.get('statusKlaar') else set()):
        f.append({'op': 'noteq', 'field': 'status', 'value': w})
    if q:
        f.append({'op': 'contains', 'field': 'title', 'value': q})
    return _tickets_uit(at, at.query('Tickets', f, _TICKETVELDEN, 500))


def _tickets_uit(at: Autotask, r: list) -> dict:
    statussen = {str(p['value']): p['label'] for p in at.picklists('Tickets').get('status', [])}
    # Nieuwste eerst (aanmaakdatum, dan ticketnummer)
    r.sort(key=lambda x: (str(x.get('createDate') or ''), int(x.get('id') or 0)), reverse=True)
    mij = (_AT.get('me') or {}).get('id')
    return {'tickets': [{'id': x['id'], 'number': x.get('ticketNumber', ''), 'title': x.get('title', ''), 'status': statussen.get(str(x.get('status')), x.get('status')),
                         'created': str(x.get('createDate') or '')[:10], 'assignedResourceroleID': x.get('assignedResourceroleID'),
                         'mine': mij is not None and x.get('assignedResourceID') == mij}
                        for x in r[:100]]}


_KLAAR_WOORDEN = ('complete', 'completed', 'voltooid', 'afgerond', 'gesloten', 'closed', 'done')


def _klaar(at: Autotask, entiteit: str) -> set:
    """Statuswaarde(n) die 'afgerond' betekenen (Autotask: Complete = 5), uit de picklist."""
    w = {p['value'] for p in at.picklists(entiteit).get('status', []) if str(p.get('label') or '').strip().lower() in _KLAAR_WOORDEN}
    return w or {5}


@api('at.taken')
def at_taken(c: Ctx, b: dict) -> dict:
    """Open projecttaken van de gekoppelde klant (open projecten, nieuwste eerst), optioneel zoeken in taak/project."""
    _zet_auth(c)
    at = _at()
    kl = _klanten().get(c.tid)
    if not kl:
        return {'tasks': [], 'needCompany': True}
    q = str(b.get('q') or '').strip().lower()
    res, oud = _lijst(('p', kl['companyId'], q), lambda: _taken_ophalen(at, kl['companyId'], q), bool(b.get('fresh')))
    return {**res, 'stale': oud}


def _taken_ophalen(at: Autotask, company: int, q: str) -> dict:
    kl = {'companyId': company}
    pf = [{'op': 'eq', 'field': 'companyID', 'value': kl['companyId']}]
    for w in _klaar(at, 'Projects'):
        pf.append({'op': 'noteq', 'field': 'status', 'value': w})
    projecten = at.query('Projects', pf, ['id', 'projectName', 'projectNumber', 'status', 'createDateTime', 'startDateTime'], 500)
    if not projecten:
        return {'tasks': [], 'projects': []}
    pinfo = {p['id']: p for p in projecten}
    tf = [{'op': 'in', 'field': 'projectID', 'value': list(pinfo)[:500]}]
    for w in _klaar(at, 'Tasks'):
        tf.append({'op': 'noteq', 'field': 'status', 'value': w})
    taken = at.query('Tasks', tf, ['id', 'title', 'taskNumber', 'projectID', 'status', 'assignedResourceID', 'assignedResourceRoleID',
                                   'createDateTime', 'startDateTime', 'endDateTime'], 500, 2000)
    statussen = {str(p['value']): p['label'] for p in at.picklists('Tasks').get('status', [])}
    mij = (_AT.get('me') or {}).get('id')
    uit = []
    for t in taken:
        p = pinfo.get(t.get('projectID')) or {}
        naam = p.get('projectName') or ''
        if q and q not in f"{t.get('title', '')} {naam} {t.get('taskNumber', '')} {p.get('projectNumber', '')}".lower():
            continue
        uit.append({'id': t['id'], 'soort': 'taak', 'number': t.get('taskNumber') or p.get('projectNumber') or '', 'title': t.get('title', ''),
                    'projectId': t.get('projectID'), 'project': naam, 'projectNumber': p.get('projectNumber') or '', 'status': statussen.get(str(t.get('status')), t.get('status')),
                    'assignedResourceroleID': t.get('assignedResourceRoleID'), 'mine': mij is not None and t.get('assignedResourceID') == mij,
                    '_p': str(p.get('createDateTime') or p.get('startDateTime') or ''), '_t': str(t.get('createDateTime') or '')})
    # Nieuwste projecten eerst, binnen een project de nieuwste taken eerst
    uit.sort(key=lambda x: (x['_p'], x['_t'], x['id']), reverse=True)
    for x in uit:
        x.pop('_p'), x.pop('_t')
    # Alle open projecten (nieuwste eerst) met het aantal open taken: de interface toont eerst het project, dan de taken
    pstatus = {str(p['value']): p['label'] for p in at.picklists('Projects').get('status', [])}
    aantal: dict = {}
    for x in uit:
        aantal[x['projectId']] = aantal.get(x['projectId'], 0) + 1
    projecten.sort(key=lambda p: (str(p.get('createDateTime') or p.get('startDateTime') or ''), p['id']), reverse=True)
    plijst = [{'id': p['id'], 'name': p.get('projectName') or f"Project {p['id']}", 'number': p.get('projectNumber') or '',
               'status': pstatus.get(str(p.get('status')), p.get('status')), 'open': aantal.get(p['id'], 0)}
              for p in projecten if not q or aantal.get(p['id']) or q in f"{p.get('projectName', '')} {p.get('projectNumber', '')}".lower()]
    return {'tasks': uit[:1000], 'projects': plijst}


@api('at.sessie.set')
def at_sessie_set(c: Ctx, b: dict) -> dict:
    """Ticketbalk: modus (ticket/auto/skip) en eventueel het gekozen ticket voor de huidige klant."""
    if not c.tid:
        raise ApiFout('Kies eerst een klant.')
    s = _sessie(c.tid, c.t.naam if c.tid in c.staat.tenants else '')
    mode = b.get('mode')
    if mode not in ('ticket', 'auto', 'skip'):
        raise ApiFout('Onbekende keuze.')
    with _wl:
        s['mode'] = mode
        s['fout'] = ''
        if mode == 'ticket':
            t = b.get('ticket') or {}
            if not t.get('id'):
                raise ApiFout('Kies een ticket of projecttaak.')
            s['ticket'] = {'id': int(t['id']), 'number': t.get('number', ''), 'title': t.get('title', ''), 'assignedResourceroleID': t.get('assignedResourceroleID'),
                           'soort': 'taak' if t.get('soort') == 'taak' else 'ticket', 'project': t.get('project', '')}
        elif mode == 'auto':
            s['ticket'] = None
            if 'contact' in b:
                s['contact'] = _contact_schoon(b.get('contact'))
        else:
            s['ticket'] = None
            s['items'] = []
        if mode != 'auto':
            s.pop('contact', None)
    return _sessie_uit(s)


# ---------------------------------------------------------------- Contactpersonen (automatisch ticket)
# De app weet niet wie de aanvraag deed: bij een automatisch ticket kiest de medewerker de contactpersoon
# (of maakt die aan, of kiest bewust 'geen'). Niet gekozen = ticket zonder contactpersoon.
_CONTACTVELDEN = ['id', 'firstName', 'lastName', 'emailAddress', 'phone', 'mobilePhone', 'title', 'isActive']
_MAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _contact_schoon(c) -> dict | None:
    if not isinstance(c, dict) or not c.get('id'):
        return None
    return {'id': int(c['id']), 'name': str(c.get('name') or '')[:120], 'email': str(c.get('email') or '')[:200]}


def _contact_uit(x: dict) -> dict:
    return {'id': x['id'], 'name': f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip() or x.get('emailAddress') or f"Contact {x['id']}",
            'email': x.get('emailAddress') or '', 'phone': x.get('phone') or x.get('mobilePhone') or '', 'title': x.get('title') or ''}


def _contacten_ophalen(at: Autotask, company: int) -> dict:
    r = at.query('Contacts', [{'op': 'eq', 'field': 'companyID', 'value': company}, {'op': 'eq', 'field': 'isActive', 'value': 1}],
                 _CONTACTVELDEN, 500, 2000)
    uit = [_contact_uit(x) for x in r]
    uit.sort(key=lambda x: x['name'].lower())
    return {'contacts': uit}


@api('at.contacten')
def at_contacten(c: Ctx, b: dict) -> dict:
    """Actieve contactpersonen van het gekoppelde Autotask-bedrijf (lijstcache: direct tonen, op de achtergrond verversen)."""
    _zet_auth(c)
    kl = ({'companyId': int(b['companyId']), 'name': str(b.get('companyName') or '')} if _heeft_bedrijf(b) else _klanten().get(c.tid))   # Servicedesk: elk bedrijf
    if not kl:
        return {'contacts': [], 'needCompany': True}
    at = _at()
    res, oud = _lijst(('c', kl['companyId'], ''), lambda: _contacten_ophalen(at, kl['companyId']), bool(b.get('fresh')))
    return {**res, 'stale': oud}


@api('at.contact.nieuw')
def at_contact_nieuw(c: Ctx, b: dict) -> dict:
    """Nieuwe contactpersoon bij het gekoppelde Autotask-bedrijf (voornaam, achternaam, e-mail; telefoon optioneel).
    Bestaat het e-mailadres al bij dit bedrijf, dan wordt die contactpersoon gebruikt (geen dubbele)."""
    _zet_auth(c)
    kl = ({'companyId': int(b['companyId']), 'name': str(b.get('companyName') or '')} if _heeft_bedrijf(b) else _klanten().get(c.tid))   # Servicedesk: elk bedrijf
    if not kl:
        raise ApiFout('Koppel deze klant eerst aan een Autotask-bedrijf.')
    voor, achter, mail, tel = (str(b.get(k) or '').strip() for k in ('firstName', 'lastName', 'email', 'phone'))
    if not voor or not achter:
        raise ApiFout('Vul voornaam en achternaam in.')
    if not _MAIL.match(mail):
        raise ApiFout('Vul een geldig e-mailadres in.')
    at = _at()
    bestaand = at.query('Contacts', [{'op': 'eq', 'field': 'companyID', 'value': kl['companyId']}, {'op': 'eq', 'field': 'emailAddress', 'value': mail}],
                        _CONTACTVELDEN, 5)
    if bestaand:
        x = _contact_uit(bestaand[0])
        c.L(f"Contactpersoon {x['name']} bestond al bij {kl.get('name') or 'dit bedrijf'}; die wordt gebruikt.")
        return {'contact': x, 'existed': True}
    body = {'companyID': kl['companyId'], 'firstName': voor[:50], 'lastName': achter[:50], 'emailAddress': mail[:254], 'isActive': 1}
    if tel:
        body['phone'] = tel[:25]
    try:
        r = at.req('POST', f"Companies/{kl['companyId']}/Contacts", body)
    except ApiFout as e:
        if e.status in (404, 405):   # oudere zone zonder child-URL: terugval op het entiteit-eindpunt
            r = at.req('POST', 'Contacts', body)
        else:
            raise
    nid = r.get('itemId') or (r.get('item') or {}).get('id')
    lijst_wissen(kl['companyId'], ('c',))
    x = {'id': nid, 'name': f'{voor} {achter}', 'email': mail, 'phone': tel, 'title': ''}
    c.L(f"Contactpersoon {x['name']} aangemaakt bij {kl.get('name') or 'het Autotask-bedrijf'}.")
    return {'contact': x, 'existed': False}


@api('at.sessie.contact')
def at_sessie_contact(c: Ctx, b: dict) -> dict:
    """Contactpersoon voor het automatische ticket kiezen of wijzigen (None = geen contactpersoon).
    Is het ticket al door de app aangemaakt, dan wordt de contactpersoon daar ook bijgewerkt."""
    if not c.tid:
        raise ApiFout('Kies eerst een klant.')
    s = _sessie(c.tid)
    contact = _contact_schoon(b.get('contact'))
    with _wl:
        s['contact'] = contact
        t = s.get('ticket')
    if t and t.get('door_app') and t.get('soort') != 'taak':
        _zet_auth(c)
        try:
            _at().req('PATCH', 'Tickets', {'id': t['id'], 'contactID': contact['id'] if contact else None})
        except ApiFout as e:
            log.info('Contactpersoon op ticket bijwerken niet gelukt: %s', e)
            raise ApiFout(f'Contactpersoon kon niet op ticket {t.get("number") or t["id"]} gezet worden: {e}') from None
    return _sessie_uit(s)


@api('at.sessie.item')
def at_sessie_item(c: Ctx, b: dict) -> dict:
    s = _sessie(str(b.get('tid') or c.tid))
    with _wl:
        for i in s['items']:
            if i['id'] == b.get('id'):
                if b.get('remove'):
                    s['items'].remove(i)
                    break
                if 'minuten' in b:
                    i['minuten'] = max(0, min(480, float(b['minuten'] or 0)))
                if 'skip' in b:
                    i['skip'] = bool(b['skip'])
    return _sessie_uit(s)


@api('at.boek')
def at_boek(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    tid = str(b.get('tid') or c.tid)
    s = _SESSIES.get(tid)
    ticket = (s or {}).get('ticket')
    r = boek(tid, 'handmatig' if not b.get('wissel') else 'bij wisselen van klant')
    if r.get('booked'):
        c.L(f"{r['booked']} actie(s) geboekt op Autotask-ticket {r['ticket']} ({r['minutes']} min).")
    # Direct afronden: 'complete' (incident) of 'invoice' (Ready to Invoice, licentiewijziging) met oplossing
    sluit = b.get('sluit')
    if sluit in ('complete', 'invoice') and s and (s.get('ticket') or ticket) and (s.get('ticket') or ticket).get('soort') != 'taak':
        t = s.get('ticket') or ticket
        at = _at()
        inst = _instellingen()
        status = eindstatussen(at, inst)[sluit]
        if status is None:
            raise ApiFout('Deze status bestaat niet in Autotask.' if sluit == 'complete' else "De status 'Ready to Invoice' bestaat niet in Autotask.")
        body = {'id': t['id'], 'status': status}
        if str(b.get('resolution') or '').strip():
            body['resolution'] = str(b['resolution']).strip()[:7900]
        at.req('PATCH', 'Tickets', body)
        with _wl:
            s['ticket'] = None
            s['vorig'] = None
            s['licentie'] = False
            if s['mode'] == 'ticket':
                s['mode'] = None
        c.L(f"Ticket {t.get('number') or t['id']} afgesloten ({'Ready to Invoice' if sluit == 'invoice' else 'Complete'}).")
        r['closed'] = sluit
    return r


@api('at.medewerkers')
def at_medewerkers(c: Ctx, b: dict) -> dict:
    """Actieve Autotask-medewerkers (voor de keuzelijst) en de huidige koppelingen login -> medewerker."""
    eis_beheerder(c)
    _zet_auth(c)
    at = _at()
    res = at.query('Resources', [{'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'firstName', 'lastName', 'email'], 500)
    lijst = sorted([{'id': x['id'], 'name': f"{x.get('firstName', '')} {x.get('lastName', '')}".strip(), 'email': (x.get('email') or '').lower()} for x in res],
                   key=lambda x: x['name'].lower())
    return {'resources': lijst, 'mapping': _medewerkers()}


@api('at.medewerker.set')
def at_medewerker_set(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    mail = str(b.get('email') or '').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[a-z]{2,}', mail):
        raise ApiFout('Vul een geldig e-mailadres (Microsoft-login) in.')
    alle = _medewerkers()
    if b.get('resourceId') is None:
        alle.pop(mail, None)
    else:
        alle[mail] = {'id': int(b['resourceId']), 'name': str(b.get('name') or '')}
    GEDEELD.schrijf_raw('autotask-medewerkers', json.dumps(alle))
    _AT.pop('me', None)
    c.L(f"{mail} boekt voortaan als {b.get('name')} in Autotask." if b.get('resourceId') is not None else f'Koppeling van {mail} verwijderd.')
    return {'mapping': alle}


def vergeet() -> None:
    """Afmelden: Autotask-client (sleutels), medewerker, lijsten, werklog en back-upsessie uit het geheugen."""
    with _at_lock:
        _AT.clear()
    lijst_wissen()
    with _bk_lock:
        _BK.clear()
    with _wl:
        _SESSIES.clear()
        _GEBOEKT.clear()
