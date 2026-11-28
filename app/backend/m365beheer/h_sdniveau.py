"""Servicedesk in twee niveaus (L1 servicedesk, L2 escalatie), sneller dan Autotask zelf.

- Inrichting (alleen app-beheerder): L1- en L2-queue uit Autotask, wie L1 is (met triageverantwoordelijken), wie L2 is,
  wie changes goedkeurt, tarieven per niveau en de doelen. Gedeeld via de verborgen SharePoint-lijst ('servicedesk-inrichting').
  Geen namen in de code: alles zijn Autotask-resource-id's.
- L1-queue: nieuwe en open tickets in de servicedeskqueue met snelle triage (toewijzen, prioriteit, in bulk) en escaleren naar L2
  (queue + notitie met de reden). Meldingen: `sd.melding` is een lichte opvraging die het scherm elke minuut doet.
- Changes: open change requests met de stemmen; goedkeuren/afkeuren in bulk via TicketChangeRequestApprovals (alleen 'create':
  Autotask laat een stem niet wijzigen via de API).
- Monitoring (app-beheerder en directie): KPI's van het L1/L2-model uit tickets en tijdregels.
Niets opslaan behalve de inrichting.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import eis_beheerder, is_beheerder, is_directie, is_facturatie

log = logging.getLogger('m365beheer')

STANDAARD = {
    'l1Queue': None, 'l2Queue': None,
    'l1': [], 'l1Leads': [], 'l2': [], 'approvers': [],
    'tariefL1': None, 'tariefL2': None,     # leeg = uurtarief van de rol in Autotask
    'doelL1': 85,                           # % tickets afgehandeld door L1 (doel 80-90%)
    'triageMin': 15,                        # nieuw ticket moet binnen zoveel minuten opgepakt zijn
    'escalatieMax': 15,                     # % escalaties naar L2
}
_CACHE: dict = {}
_HERKEN: dict = {}   # apart van _CACHE: blijft staan als lijsten na een wijziging worden geleegd


# Ook Romeinse cijfers ('Level I Support' / 'Level II Support', zo heten ze bij Justdata) en Tier 1/2
L1_NAAM = re.compile(r'(level|tier|niveau)\s*(1|i|one|een)\b|\bl1\b|eerste\s*lijn|1e\s*lijn|first\s*line', re.I)
L2_NAAM = re.compile(r'(level|tier|niveau)\s*(2|ii|two|twee)\b|\bl2\b|tweede\s*lijn|2e\s*lijn|second\s*line|escalat', re.I)


def _herken() -> dict:
    """Wat Autotask zelf al weet (10 min onthouden): de queues 'Level 1 Support' / 'Level 2 Support' (op naam) en wie daarin
    zit (ResourceRoleQueues). Wordt gebruikt zolang de beheerder in de inrichting niets anders heeft gekozen."""
    item = _HERKEN.get('h')
    if item and time.time() - item[0] < 600:
        return item[1]
    uit: dict = {}
    try:
        from . import h_autotask as A
        if A._sleutel() is None:
            return {}
        at = A._at()
        qs = at.picklists('Tickets').get('queueID', [])
        l1 = next((q for q in qs if L1_NAAM.search(str(q.get('label') or ''))), None)
        l2 = next((q for q in qs if L2_NAAM.search(str(q.get('label') or ''))), None)
        for sleutel, q in (('1', l1), ('2', l2)):
            if q:
                uit[f'l{sleutel}Queue'] = q['value']
                uit[f'l{sleutel}QueueName'] = q.get('label') or ''
                try:
                    leden = at.query('ResourceRoleQueues', [{'op': 'eq', 'field': 'queueID', 'value': q['value']}], ['resourceID', 'queueID'], 200)
                    uit[f'l{sleutel}Members'] = sorted({x['resourceID'] for x in leden if x.get('resourceID')})
                except ApiFout as e:
                    log.info('Leden van queue %s niet opgehaald: %s', q.get('label'), e)
    except ApiFout as e:
        log.info('Servicedesk-queues herkennen: %s', e)
    _HERKEN['h'] = (time.time(), uit)
    return uit


def inrichting() -> dict:
    w = GEDEELD.lees_raw('servicedesk-inrichting', 120)
    try:
        d = json.loads(w) if w else {}
    except ValueError:
        d = {}
    uit = {**STANDAARD, **d}
    for k in ('l1', 'l1Leads', 'l2', 'approvers'):
        uit[k] = [int(x) for x in uit.get(k) or [] if str(x).lstrip('-').isdigit()]
    # Niet ingesteld: overnemen uit Autotask (queues op naam, leden uit de queue)
    h = _herken() if not (uit['l1Queue'] and uit['l2Queue'] and (uit['l1'] or uit['l1Leads']) and uit['l2']) else {}
    uit['auto'] = []
    for n in ('1', '2'):
        if not uit[f'l{n}Queue'] and h.get(f'l{n}Queue'):
            uit[f'l{n}Queue'] = h[f'l{n}Queue']
            uit['auto'].append(f"queue L{n}: {h.get(f'l{n}QueueName')}")
    # Wie in beide queues zit, is een specialist die ook bij L1 meekijkt: die telt als L2
    if not uit['l2'] and h.get('l2Members'):
        uit['l2'] = [x for x in h['l2Members'] if x not in uit['l1Leads'] and x not in uit['l1']]
        uit['auto'].append('medewerkers L2 uit de queue')
    if not uit['l1'] and not uit['l1Leads'] and h.get('l1Members'):
        uit['l1'] = [x for x in h['l1Members'] if x not in uit['l2']]
        uit['auto'].append('medewerkers L1 uit de queue')
    return uit


def niveau(rid) -> str:
    """'l1lead', 'l1', 'l2' of '' voor een Autotask-resource."""
    i = inrichting()
    if rid in i['l1Leads']:
        return 'l1lead'
    if rid in i['l1']:
        return 'l1'
    if rid in i['l2']:
        return 'l2'
    return ''


def rol_info(c: Ctx) -> dict:
    """Wat deze medewerker in de servicedesk mag en ziet."""
    from . import h_autotask as A
    i = inrichting()
    uit = {'niveau': '', 'monitor': is_beheerder(c.staat) or is_directie(c.staat), 'billing': is_facturatie(c.staat),
           'changes': is_beheerder(c.staat), 'ingericht': bool(i['l1Queue'] and i['l2Queue'])}
    try:
        ik = A._ik(A._at())
        uit['niveau'] = niveau(ik['id'])
        uit['changes'] = uit['changes'] or ik['id'] in i['approvers']
    except ApiFout:
        pass
    return uit


# ---------------------------------------------------------------- langlopende tickets (buiten SLA)
def langlopend(vers: bool = False) -> dict:
    """Ticket-id's (als tekst) die langlopend zijn (bijv. een reparatie die weken duurt): nooit een incident, buiten de SLA,
    en ze tellen niet mee in de SLA-cijfers, doorlooptijd en 'over de deadline'. Gedeeld via de verborgen SharePoint-lijst."""
    w = GEDEELD.lees_raw('servicedesk-langlopend', 0 if vers else 60)
    try:
        return json.loads(w) if w else {}
    except ValueError:
        return {}


@api('sd.langlopend')
def sd_langlopend(c: Ctx, b: dict) -> dict:
    """Tickets als langlopend markeren (of terugzetten). In Autotask: tickettype Service Request (nooit Incident) en de SLA eraf,
    plus een notitie met de reden. Iedereen mag dit (triage)."""
    from . import h_autotask as A
    _zet_auth(c)
    ids = [int(x) for x in b.get('ids') or []]
    if not ids:
        raise ApiFout('Kies minstens één ticket.')
    aan = bool(b.get('on', True))
    reden = str(b.get('reason') or '').strip()
    at = A._at()
    ik = A._ik(at)
    inst = A._instellingen()
    sr = _ticketsoort(at, r'service\s*request|serviceverzoek|verzoek')
    st = langlopend(True)
    fouten = []
    for tid in ids:
        try:
            if aan:
                body = {'id': tid}
                if sr is not None:
                    body['ticketType'] = sr
                at.req('PATCH', 'Tickets', body)
                try:   # SLA eraf; weigert Autotask dat (bijv. SLA vanuit het contract), dan blijft alleen de uitsluiting in de app
                    at.req('PATCH', 'Tickets', {'id': tid, 'serviceLevelAgreementID': None})
                except ApiFout as e:
                    log.info('SLA van ticket %s niet verwijderd: %s', tid, e)
                A._notitie(at, tid, f"Langlopend ticket (buiten SLA) - {ik['name']}",
                           'Gemarkeerd als langlopend: geen incident, valt buiten de SLA.' + (f'\nReden: {reden}' if reden else ''), inst)
                st[str(tid)] = {'by': ik['name'], 'at': datetime.now().isoformat(timespec='minutes'), 'reason': reden[:300]}
            else:
                st.pop(str(tid), None)
                A._notitie(at, tid, f"Niet meer langlopend - {ik['name']}", 'Ticket telt weer mee in de servicedeskcijfers. Controleer zo nodig de SLA in Autotask.', inst)
        except ApiFout as e:
            fouten.append(f'{tid}: {str(e)[:150]}')
    GEDEELD.schrijf_raw('servicedesk-langlopend', json.dumps(st))
    GEDEELD.cache.pop('raw:servicedesk-langlopend', None)
    _CACHE.clear()
    from .h_servicedesk import _CACHE as SDC
    SDC.clear()
    c.L(f"{len(ids) - len(fouten)} ticket(s) {'als langlopend gemarkeerd (buiten SLA)' if aan else 'weer normaal'}.")
    if fouten:
        raise ApiFout('Niet gelukt bij: ' + '; '.join(fouten[:3]))
    return {'ok': len(ids)}


# ---------------------------------------------------------------- inrichting
@api('sd.inrichting')
def sd_inrichting(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    eis_beheerder(c)
    at = A._at()
    pl = at.picklists('Tickets')
    res = at.query('Resources', [{'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'firstName', 'lastName', 'email'], 500)
    return {'settings': inrichting(), 'queues': pl.get('queueID', []),
            'resources': sorted([{'id': r['id'], 'name': f"{r.get('firstName') or ''} {r.get('lastName') or ''}".strip(), 'email': r.get('email') or ''}
                                 for r in res], key=lambda r: r['name'].lower())}


@api('sd.inrichting.set')
def sd_inrichting_set(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    eis_beheerder(c)
    s = b.get('settings') or {}
    nieuw = {k: s.get(k, STANDAARD[k]) for k in STANDAARD}
    for k in ('tariefL1', 'tariefL2'):
        nieuw[k] = float(nieuw[k]) if nieuw[k] not in (None, '') else None
    for k in ('doelL1', 'triageMin', 'escalatieMax'):
        nieuw[k] = int(nieuw[k] or STANDAARD[k])
    if nieuw['l1Queue'] and nieuw['l1Queue'] == nieuw['l2Queue']:
        raise ApiFout('Kies voor L1 en L2 een verschillende queue.')
    GEDEELD.schrijf_raw('servicedesk-inrichting', json.dumps(nieuw))
    GEDEELD.cache.pop('raw:servicedesk-inrichting', None)
    _CACHE.clear()
    c.L('Inrichting servicedesk (L1/L2) opgeslagen voor iedereen.')
    return {'settings': inrichting()}


# ---------------------------------------------------------------- queues en triage
def _queue_tickets(queue, max_: int = 300) -> list[dict]:
    from . import h_autotask as A
    from .h_servicedesk import _tickets
    if not queue:
        return []
    return _tickets(A._at(), [{'op': 'eq', 'field': 'queueID', 'value': int(queue)}], max_)


def _sorteer_triage(lijst: list[dict]) -> list[dict]:
    """Eerst nieuw en niet toegewezen, dan over de deadline, dan hoogste prioriteit, dan oudste."""
    hoog = lambda t: bool(re.search(r'crit|high|hoog|urgent|p1|p2', str(t.get('priority')), re.I))  # noqa: E731
    # Langlopende tickets (reparaties e.d.) achteraan: die vragen geen triage
    return sorted(lijst, key=lambda t: (bool(t.get('longRunning')), not (t.get('isNew') or t.get('unassigned')), not t.get('overdue'), not hoog(t), -(t.get('hours') or 0)))


@api('sd.queue')
def sd_queue(c: Ctx, b: dict) -> dict:
    """De L1- of L2-queue. Voor triage: tellers en de tickets in de juiste volgorde."""
    _zet_auth(c)
    i = inrichting()
    welke = 'l2' if b.get('level') == 'l2' else 'l1'
    q = i['l2Queue'] if welke == 'l2' else i['l1Queue']
    if not q:
        return {'needSetup': True, 'tickets': []}
    sleutel = ('q', welke)
    item = _CACHE.get(sleutel)
    if item and not b.get('fresh') and time.time() - item[0] < 30:
        lijst = item[1]
    else:
        lijst = _sorteer_triage(_queue_tickets(q))
        _CACHE[sleutel] = (time.time(), lijst)
    grens = i['triageMin'] / 60
    tel = {'open': len(lijst), 'new': sum(1 for t in lijst if t.get('isNew')), 'unassigned': sum(1 for t in lijst if t.get('unassigned')),
           'overdue': sum(1 for t in lijst if t.get('overdue')),
           'triageLate': sum(1 for t in lijst if (t.get('isNew') or t.get('unassigned')) and (t.get('hours') or 0) > grens)}
    return {'tickets': lijst, 'counts': tel, 'level': welke, 'triageMin': i['triageMin'], 'at': datetime.now().strftime('%H:%M'),
            'members': _leden(welke)}


def _leden(welke: str) -> list[dict]:
    """Medewerkers van een niveau (voor 'toewijzen aan'), met namen uit Autotask (10 min onthouden)."""
    from . import h_autotask as A
    from .h_management import _in
    i = inrichting()
    ids = (i['l1Leads'] + i['l1']) if welke == 'l1' else i['l2']
    if not ids:
        return []
    sleutel = ('leden', tuple(ids))
    item = _CACHE.get(sleutel)
    if item and time.time() - item[0] < 600:
        return item[1]
    r = _in(A._at(), 'Resources', ids, ['id', 'firstName', 'lastName'])
    uit = [{'id': x['id'], 'name': f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip(), 'lead': x['id'] in i['l1Leads']} for x in r]
    _CACHE[sleutel] = (time.time(), uit)
    return uit


def _rol(at, rid: int):
    r = at.query('ResourceServiceDeskRoles', [{'op': 'eq', 'field': 'resourceID', 'value': rid}, {'op': 'eq', 'field': 'isActive', 'value': True}], None, 50)
    return next((x['roleID'] for x in r if x.get('isDefault')), r[0]['roleID'] if r else None)


def _parallel(fn, items, n: int = 4) -> list:
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(fn, items))


@api('sd.triage')
def sd_triage(c: Ctx, b: dict) -> dict:
    """Eén of meer tickets in één keer: toewijzen, prioriteit, status (bijv. In Progress)."""
    from . import h_autotask as A
    _zet_auth(c)
    ids = [int(x) for x in b.get('ids') or []]
    if not ids:
        raise ApiFout('Kies minstens één ticket.')
    at = A._at()
    patch: dict = {}
    if b.get('resourceId'):
        rid = int(b['resourceId'])
        patch.update(assignedResourceID=rid, assignedResourceRoleID=_rol(at, rid))
    for k, veld in (('priority', 'priority'), ('status', 'status')):
        if b.get(k) not in (None, ''):
            patch[veld] = int(b[k])
    if not patch:
        raise ApiFout('Kies wat je wilt wijzigen.')

    def een(tid):
        try:
            at.req('PATCH', 'Tickets', {'id': tid, **patch})
            return {'id': tid, 'ok': True}
        except ApiFout as e:
            return {'id': tid, 'ok': False, 'error': str(e)[:200]}
    res = _parallel(een, ids)
    _CACHE.clear()
    from .h_servicedesk import _CACHE as SDC
    SDC.clear()
    ok = sum(1 for r in res if r['ok'])
    c.L(f'Triage: {ok} ticket(s) bijgewerkt' + (f', {len(res) - ok} niet gelukt' if ok < len(res) else '') + '.')
    return {'results': res, 'ok': ok, 'failed': len(res) - ok}


@api('sd.escaleren')
def sd_escaleren(c: Ctx, b: dict) -> dict:
    """Naar L2: queue wijzigen, notitie met de reden (wat L1 al geprobeerd heeft) en optioneel direct aan een L2-collega."""
    from . import h_autotask as A
    _zet_auth(c)
    i = inrichting()
    if not i['l2Queue']:
        raise ApiFout('De L2-queue is nog niet ingericht (Servicedesk > Inrichting).')
    reden = str(b.get('reason') or '').strip()
    if len(reden) < 10:
        raise ApiFout('Schrijf kort waarom het naar L2 moet en wat je al hebt geprobeerd.')
    ids = [int(x) for x in b.get('ids') or []]
    at = A._at()
    ik = A._ik(at)
    inst = A._instellingen()
    patch = {'queueID': int(i['l2Queue'])}
    if b.get('resourceId'):
        rid = int(b['resourceId'])
        patch.update(assignedResourceID=rid, assignedResourceRoleID=_rol(at, rid))

    def een(tid):
        try:
            at.req('PATCH', 'Tickets', {'id': tid, **patch})
            A._notitie(at, tid, f"Escalatie naar L2 door {ik['name']}", reden, inst)
            return {'id': tid, 'ok': True}
        except ApiFout as e:
            return {'id': tid, 'ok': False, 'error': str(e)[:200]}
    res = _parallel(een, ids)
    _CACHE.clear()
    ok = sum(1 for r in res if r['ok'])
    c.L(f'{ok} ticket(s) geëscaleerd naar L2.')
    return {'results': res, 'ok': ok, 'failed': len(res) - ok}


@api('sd.terugnaarl1')
def sd_terug(c: Ctx, b: dict) -> dict:
    """L2 zet een ticket terug naar de servicedesk (bijv. met instructie), met notitie."""
    from . import h_autotask as A
    _zet_auth(c)
    i = inrichting()
    tekst = str(b.get('text') or '').strip()
    if len(tekst) < 5:
        raise ApiFout('Schrijf de instructie voor de servicedesk.')
    at = A._at()
    ik = A._ik(at)
    tid = int(b['id'])
    at.req('PATCH', 'Tickets', {'id': tid, 'queueID': int(i['l1Queue'])})
    A._notitie(at, tid, f"Terug naar de servicedesk ({ik['name']})", tekst, A._instellingen())
    _CACHE.clear()
    c.L('Ticket teruggezet naar de servicedesk (L1).')
    return {}


@api('sd.melding')
def sd_melding(c: Ctx, b: dict) -> dict:
    """Lichte opvraging voor meldingen (elke minuut): nieuwe/niet toegewezen tickets in de L1-queue en tickets die net aan jou
    zijn toegewezen. Alleen id/nummer/onderwerp/klant/tijd."""
    from . import h_autotask as A
    _zet_auth(c)
    i = inrichting()
    if A._sleutel() is None:
        return {'tickets': [], 'mine': []}
    if not i['l1Queue']:
        return {'tickets': [], 'mine': [], **_bestellingen(c)}
    item = _CACHE.get('melding')
    if item and time.time() - item[0] < 25:
        return {**item[1], **_bestellingen(c)}
    at = A._at()
    klaar = A._klaar(at, 'Tickets')
    velden = ['id', 'ticketNumber', 'title', 'companyID', 'createDate', 'status', 'assignedResourceID', 'priority']
    sinds = (datetime.now(timezone.utc) - timedelta(days=14)).strftime('%Y-%m-%dT%H:%M:%SZ')
    nieuw = at.query('Tickets', [{'op': 'eq', 'field': 'queueID', 'value': int(i['l1Queue'])}, {'op': 'notExist', 'field': 'assignedResourceID'},
                                 {'op': 'gte', 'field': 'createDate', 'value': sinds}] + [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar], velden, 100)
    mijn = []
    try:
        ik = A._ik(at)
        recent = (datetime.now(timezone.utc) - timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M:%SZ')
        mijn = at.query('Tickets', [{'op': 'eq', 'field': 'assignedResourceID', 'value': ik['id']}, {'op': 'gte', 'field': 'lastActivityDate', 'value': recent}]
                        + [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar], velden, 50)
    except ApiFout:
        pass
    from .h_management import _in
    bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {t.get('companyID') for t in nieuw + mijn}, ['id', 'companyName'])}
    vorm = lambda t: {'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'company': bedr.get(t.get('companyID'), ''),  # noqa: E731
                      'created': t.get('createDate') or ''}
    uit = {'tickets': [vorm(t) for t in sorted(nieuw, key=lambda t: str(t.get('createDate')), reverse=True)], 'mine': [vorm(t) for t in mijn],
           'lead': False}
    try:
        uit['lead'] = niveau(A._ik(at)['id']) in ('l1lead', 'l1')
    except ApiFout:
        pass
    _CACHE['melding'] = (time.time(), uit)
    return {**uit, **_bestellingen(c)}


def _bestellingen(c: Ctx) -> dict:
    """Sales ziet in de bel hoeveel er besteld moet worden (bestellijst Voorraad)."""
    from .rechten import is_sales
    if not is_sales(c.staat):
        return {}
    from .h_voorraad import te_bestellen
    return {'orders': te_bestellen()}


# ---------------------------------------------------------------- changes
def _ticketsoort(at, label_re: str):
    return next((p['value'] for p in at.picklists('Tickets').get('ticketType', []) if re.search(label_re, str(p.get('label') or ''), re.I)), None)


@api('sd.changes')
def sd_changes(c: Ctx, b: dict) -> dict:
    """Open change requests die op een besluit wachten, met de stemmen die er al zijn."""
    from . import h_autotask as A
    from .h_management import _in
    from .h_servicedesk import _link, _tijd
    _zet_auth(c)
    at = A._at()
    soort = _ticketsoort(at, r'change')
    if soort is None:
        return {'tickets': [], 'error': 'Autotask kent geen tickettype Change Request.'}
    pl = at.picklists('Tickets')
    lab = lambda veld: {str(p['value']): p['label'] for p in pl.get(veld, [])}  # noqa: E731
    cas = lab('changeApprovalStatus')
    klaar = A._klaar(at, 'Tickets')
    open_ = at.query('Tickets', [{'op': 'eq', 'field': 'ticketType', 'value': soort}] + [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar],
                     ['id', 'ticketNumber', 'title', 'description', 'companyID', 'createDate', 'status', 'priority', 'changeApprovalStatus',
                      'changeApprovalBoard', 'changeApprovalType', 'assignedResourceID', 'changeInfoField1', 'changeInfoField2', 'changeInfoField3',
                      'changeInfoField4', 'changeInfoField5'], 300)
    wacht = [t for t in open_ if not re.search(r'^approved$|^rejected$|goedgekeurd|afgekeurd', cas.get(str(t.get('changeApprovalStatus')), ''), re.I)]
    stemmen: dict = {}
    for i in range(0, len(wacht), 200):
        for s in at.query('TicketChangeRequestApprovals', [{'op': 'in', 'field': 'ticketID', 'value': [t['id'] for t in wacht[i:i + 200]]}], None, 500):
            stemmen.setdefault(s.get('ticketID'), []).append(s)
    bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {t.get('companyID') for t in wacht}, ['id', 'companyName'])}
    mensen = {x['id']: f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip()
              for x in _in(at, 'Resources', {s.get('resourceID') for l in stemmen.values() for s in l} | {t.get('assignedResourceID') for t in wacht},
                           ['id', 'firstName', 'lastName'])}
    try:
        ik = A._ik(at)['id']
    except ApiFout:
        ik = None
    st, pr = lab('status'), lab('priority')
    uit = []
    for t in wacht:
        c_ = _tijd(t.get('createDate'))
        s = stemmen.get(t['id'], [])
        mijn = next((x for x in s if x.get('resourceID') == ik), None)
        info = [t.get(f'changeInfoField{n}') for n in range(1, 6) if t.get(f'changeInfoField{n}')]
        uit.append({'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'company': bedr.get(t.get('companyID'), ''),
                    'description': re.sub(r'\n\s*\n+', '\n', (t.get('description') or '').strip())[:1500], 'info': info,
                    'status': st.get(str(t.get('status')), ''), 'priority': pr.get(str(t.get('priority')), ''),
                    'approval': cas.get(str(t.get('changeApprovalStatus')), ''), 'created': c_.astimezone().strftime('%d-%m-%Y') if c_ else '',
                    'assigned': mensen.get(t.get('assignedResourceID'), ''), 'url': _link(at, t['id']),
                    'votes': [{'name': mensen.get(x.get('resourceID'), 'contactpersoon' if x.get('contactID') else ''),
                               'vote': None if x.get('isApproved') is None else bool(x.get('isApproved')), 'note': x.get('approveRejectNote') or ''} for x in s],
                    'myVote': None if not mijn else mijn.get('isApproved'), 'iAmApprover': bool(mijn)})
    uit.sort(key=lambda t: (t['myVote'] is not None, t['created']))
    return {'tickets': uit}


@api('sd.changes.stem')
def sd_changes_stem(c: Ctx, b: dict) -> dict:
    """Goedkeuren of afkeuren in bulk. Autotask laat een stem alleen toevoegen (create), niet wijzigen: staat er al een lege
    stem van jou (lid van het change board), dan wordt die vervangen (verwijderen + toevoegen); lukt dat niet, dan een duidelijke
    melding met de link naar het ticket. NIET getest met een echte Autotask (child-URL en board-regels)."""
    from . import h_autotask as A
    from .h_servicedesk import _link
    _zet_auth(c)
    rol = rol_info(c)
    if not rol['changes']:
        raise ApiFout('Alleen de change-goedkeurders mogen changes goedkeuren of afkeuren.')
    ja = b.get('decision') == 'approve'
    noot = str(b.get('note') or '').strip()[:2000]
    if not ja and len(noot) < 5:
        raise ApiFout('Schrijf bij afkeuren kort waarom.')
    at = A._at()
    ik = A._ik(at)

    def een(tid):
        tid = int(tid)
        body = {'ticketID': tid, 'resourceID': ik['id'], 'isApproved': ja, 'approveRejectNote': noot or ('Goedgekeurd' if ja else '')}
        try:
            try:
                at.req('POST', f'Tickets/{tid}/ChangeRequestApprovals', body)
            except ApiFout as e:
                if e.status not in (404, 405):
                    raise
                at.req('POST', 'TicketChangeRequestApprovals', body)
            return {'id': tid, 'ok': True}
        except ApiFout as e:
            # Al goedkeurder zonder stem: lege stem vervangen
            bestaand = at.query('TicketChangeRequestApprovals', [{'op': 'eq', 'field': 'ticketID', 'value': tid},
                                                                  {'op': 'eq', 'field': 'resourceID', 'value': ik['id']}], None, 5)
            if bestaand and bestaand[0].get('isApproved') is None:
                try:
                    at.req('DELETE', f"Tickets/{tid}/ChangeRequestApprovals/{bestaand[0]['id']}")
                    at.req('POST', f'Tickets/{tid}/ChangeRequestApprovals', body)
                    return {'id': tid, 'ok': True}
                except ApiFout as e2:
                    e = e2
            log.info('Change-stem op %s niet gelukt: %s', tid, e)
            return {'id': tid, 'ok': False, 'url': _link(at, tid),
                    'error': f'Autotask accepteert de stem niet via de API ({str(e)[:160]}). Stem in Autotask via de link.'}
    res = _parallel(een, b.get('ids') or [])
    ok = sum(1 for r in res if r['ok'])
    c.L(f"{ok} change(s) {'goedgekeurd' if ja else 'afgekeurd'}" + (f', {len(res) - ok} niet gelukt' if ok < len(res) else '') + '.')
    return {'results': res, 'ok': ok, 'failed': len(res) - ok}


# ---------------------------------------------------------------- monitoring (KPI's)
def _uren(a, b_):
    return (b_ - a).total_seconds() / 3600 if a and b_ else None


def _med(l):
    l = [x for x in l if x is not None]
    return round(statistics.median(l), 1) if l else None


def _gem(l):
    l = [x for x in l if x is not None]
    return round(sum(l) / len(l), 1) if l else None


@api('sd.kpi')
def sd_kpi(c: Ctx, b: dict) -> dict:
    """KPI's van het L1/L2-model over een periode. 5 min onthouden."""
    from . import h_autotask as A
    from .h_management import _in
    from .h_servicedesk import _link, _tijd
    _zet_auth(c)
    if not (is_beheerder(c.staat) or is_directie(c.staat)):
        raise ApiFout('Monitoring is alleen voor de app-beheerder en de directie.')
    dagen = max(7, min(365, int(b.get('days') or 30)))
    sleutel = ('kpi', dagen)
    item = _CACHE.get(sleutel)
    if item and not b.get('fresh') and time.time() - item[0] < 300:
        return item[1]
    begin_t = time.time()
    i = inrichting()
    at = A._at()
    nu = datetime.now(timezone.utc)
    begin = nu - timedelta(days=dagen)
    bs = begin.strftime('%Y-%m-%dT%H:%M:%SZ')
    klaar = A._klaar(at, 'Tickets')
    tv = ['id', 'ticketNumber', 'title', 'companyID', 'createDate', 'completedDate', 'status', 'queueID', 'assignedResourceID',
          'completedByResourceID', 'firstResponseDateTime', 'serviceLevelAgreementHasBeenMet', 'dueDateTime', 'priority', 'ticketType']
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_nieuw = ex.submit(at.query, 'Tickets', [{'op': 'gte', 'field': 'createDate', 'value': bs}], tv, 5000, 5000)
        f_open = ex.submit(at.query, 'Tickets', [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar], tv, 3000, 3000)
        f_tijd = ex.submit(at.query, 'TimeEntries', [{'op': 'gte', 'field': 'dateWorked', 'value': bs}],
                           ['id', 'resourceID', 'hoursWorked', 'hoursToBill', 'isNonBillable', 'ticketID', 'taskID', 'roleID', 'contractID'], 10000, 10000)
        nieuw, open_, tijd = f_nieuw.result(), f_open.result(), f_tijd.result()
    L1 = set(i['l1']) | set(i['l1Leads'])
    L2 = set(i['l2'])
    lvl = lambda rid: 'l1' if rid in L1 else 'l2' if rid in L2 else 'overig'  # noqa: E731

    # Afgehandeld: wie het ticket afrondde (completedByResourceID), anders wie het had, anders de queue
    def afgehandeld_door(t):
        rid = t.get('completedByResourceID') or t.get('assignedResourceID')
        if rid in L1 or rid in L2:
            return lvl(rid)
        if t.get('queueID') == i['l2Queue']:
            return 'l2'
        if t.get('queueID') == i['l1Queue']:
            return 'l1'
        return 'overig'
    opgelost = [t for t in nieuw if t.get('status') in klaar or t.get('completedDate')]
    per_niveau = {k: [t for t in opgelost if afgehandeld_door(t) == k] for k in ('l1', 'l2', 'overig')}
    opgelost_ids = {t['id'] for t in opgelost}
    geescaleerd = [t for t in nieuw if t.get('queueID') == i['l2Queue'] or (t['id'] in opgelost_ids and afgehandeld_door(t) == 'l2')]
    # Langlopende tickets (bijv. reparaties) tellen niet mee voor SLA, doorlooptijd, eerste reactie en 'over de deadline'
    lang = set(langlopend())
    telt = lambda t: str(t['id']) not in lang  # noqa: E731
    doorloop = {k: [_uren(_tijd(t.get('createDate')), _tijd(t.get('completedDate'))) for t in v if telt(t)] for k, v in per_niveau.items()}
    reactie = [_uren(_tijd(t.get('createDate')), _tijd(t.get('firstResponseDateTime'))) for t in nieuw if t.get('firstResponseDateTime') and telt(t)]
    sla = [t.get('serviceLevelAgreementHasBeenMet') for t in opgelost if t.get('serviceLevelAgreementHasBeenMet') is not None and telt(t)]
    open_l1 = [t for t in open_ if t.get('queueID') == i['l1Queue']]
    open_l2 = [t for t in open_ if t.get('queueID') == i['l2Queue']]
    niet_toegewezen = [t for t in open_ if not t.get('assignedResourceID')]
    te_laat = [t for t in open_ if t.get('dueDateTime') and (_tijd(t['dueDateTime']) or nu) < nu and telt(t)]
    open_lang = sum(1 for t in open_ if not telt(t))
    afgerond_totaal = len(opgelost)
    pct = lambda a, b_: round(a * 100 / b_, 1) if b_ else None  # noqa: E731

    # Uren en omzet per niveau
    rollen = {}
    try:
        rollen = {r['id']: float(r.get('hourlyRate') or 0) for r in _in(at, 'Roles', {x.get('roleID') for x in tijd}, ['id', 'hourlyRate'])}
    except ApiFout as e:
        log.info('Rollen/tarieven niet opgehaald: %s', e)
    uren = {'l1': 0.0, 'l2': 0.0, 'overig': 0.0}
    factureerbaar = {'l1': 0.0, 'l2': 0.0, 'overig': 0.0}
    omzet = {'l1': 0.0, 'l2': 0.0, 'overig': 0.0}
    for x in tijd:
        n = lvl(x.get('resourceID'))
        uren[n] += float(x.get('hoursWorked') or 0)
        if not x.get('isNonBillable'):
            h = float(x.get('hoursToBill') if x.get('hoursToBill') is not None else x.get('hoursWorked') or 0)
            factureerbaar[n] += h
            tarief = (i['tariefL1'] if n == 'l1' else i['tariefL2'] if n == 'l2' else None) or rollen.get(x.get('roleID')) or 0
            omzet[n] += h * tarief

    # Per medewerker
    ids = {t.get('completedByResourceID') or t.get('assignedResourceID') for t in opgelost} | {t.get('assignedResourceID') for t in open_} | {x.get('resourceID') for x in tijd}
    namen = {x['id']: f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip() for x in _in(at, 'Resources', ids, ['id', 'firstName', 'lastName'])}
    mw: dict = {}
    for t in opgelost:
        rid = t.get('completedByResourceID') or t.get('assignedResourceID')
        if rid:
            m = mw.setdefault(rid, {'id': rid, 'name': namen.get(rid, f'#{rid}'), 'level': lvl(rid), 'resolved': 0, 'open': 0, 'hours': 0.0, 'dl': []})
            m['resolved'] += 1
            m['dl'].append(_uren(_tijd(t.get('createDate')), _tijd(t.get('completedDate'))))
    for t in open_:
        rid = t.get('assignedResourceID')
        if rid:
            mw.setdefault(rid, {'id': rid, 'name': namen.get(rid, f'#{rid}'), 'level': lvl(rid), 'resolved': 0, 'open': 0, 'hours': 0.0, 'dl': []})['open'] += 1
    for x in tijd:
        rid = x.get('resourceID')
        if rid:
            mw.setdefault(rid, {'id': rid, 'name': namen.get(rid, f'#{rid}'), 'level': lvl(rid), 'resolved': 0, 'open': 0, 'hours': 0.0, 'dl': []})['hours'] += float(x.get('hoursWorked') or 0)
    # Per medewerker: van welke klant de meeste tickets komen (afgehandeld + open), bijv. iemand die veel voor één klant werkt
    per_klant: dict = {}
    for t in opgelost:
        rid = t.get('completedByResourceID') or t.get('assignedResourceID')
        if rid and t.get('companyID'):
            per_klant.setdefault(rid, {}).setdefault(t['companyID'], 0)
            per_klant[rid][t['companyID']] += 1
    for t in open_:
        rid = t.get('assignedResourceID')
        if rid and t.get('companyID'):
            per_klant.setdefault(rid, {}).setdefault(t['companyID'], 0)
            per_klant[rid][t['companyID']] += 1
    knamen = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {c for d in per_klant.values() for c in d} | {t.get('companyID') for t in open_},
                                                               ['id', 'companyName'])}

    def top(rid):
        d = per_klant.get(rid) or {}
        tot = sum(d.values())
        if not tot:
            return None
        cid, n = max(d.items(), key=lambda kv: kv[1])
        return {'name': knamen.get(cid, ''), 'count': n, 'pct': round(n * 100 / tot)}
    medewerkers = sorted([{**{k: v for k, v in m.items() if k != 'dl'}, 'hours': round(m['hours'], 1), 'medianHours': _med(m['dl']), 'topCompany': top(m['id'])}
                          for m in mw.values()], key=lambda m: ({'l1': 0, 'l2': 1, 'overig': 2}[m['level']], -m['resolved']))

    # Per week: binnengekomen, opgelost, % L1
    weken: dict = {}
    for t in nieuw:
        d = _tijd(t.get('createDate'))
        if d:
            w = weken.setdefault(_wk(d), {'week': _wk(d), 'created': 0, 'resolved': 0, 'l1': 0})
            w['created'] += 1
    for t in opgelost:
        d = _tijd(t.get('completedDate')) or _tijd(t.get('createDate'))
        if d:
            w = weken.setdefault(_wk(d), {'week': _wk(d), 'created': 0, 'resolved': 0, 'l1': 0})
            w['resolved'] += 1
            w['l1'] += afgehandeld_door(t) == 'l1'
    trend = [{**w, 'l1Pct': pct(w['l1'], w['resolved'])} for w in sorted(weken.values(), key=lambda w: w['week'])]

    bedr = knamen
    oud = sorted(open_, key=lambda t: str(t.get('createDate')))[:12]
    l1_pct = pct(len(per_niveau['l1']), len(per_niveau['l1']) + len(per_niveau['l2']))
    esc_pct = pct(len(geescaleerd), len(nieuw))
    uit = {
        'days': dagen, 'at': datetime.now().strftime('%H:%M'), 'ingericht': bool(i['l1Queue'] and i['l2Queue'] and (L1 or L2)),
        'goals': {'l1': i['doelL1'], 'escalation': i['escalatieMax'], 'triageMin': i['triageMin']},
        'kpi': {'created': len(nieuw), 'resolved': afgerond_totaal, 'open': len(open_), 'openL1': len(open_l1), 'openL2': len(open_l2),
                'unassigned': len(niet_toegewezen), 'overdue': len(te_laat),
                'l1Pct': l1_pct, 'l1Resolved': len(per_niveau['l1']), 'l2Resolved': len(per_niveau['l2']), 'otherResolved': len(per_niveau['overig']),
                'escalated': len(geescaleerd), 'escalationPct': esc_pct,
                'medianHoursL1': _med(doorloop['l1']), 'medianHoursL2': _med(doorloop['l2']), 'medianHours': _med([x for v in doorloop.values() for x in v]),
                'firstResponseMedianH': _med(reactie), 'firstResponseAvgH': _gem(reactie), 'slaPct': pct(sum(1 for s in sla if s), len(sla)),
                'longRunning': open_lang},
        'hours': {k: round(v, 1) for k, v in uren.items()}, 'billable': {k: round(v, 1) for k, v in factureerbaar.items()},
        'revenue': {k: round(v, 2) for k, v in omzet.items()},
        'employees': medewerkers, 'trend': trend,
        'oldest': [{'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'company': bedr.get(t.get('companyID'), ''),
                    'days': (nu - (_tijd(t.get('createDate')) or nu)).days, 'level': 'l2' if t.get('queueID') == i['l2Queue'] else 'l1' if t.get('queueID') == i['l1Queue'] else '',
                    'assigned': namen.get(t.get('assignedResourceID'), ''), 'url': _link(at, t['id'])} for t in oud],
    }
    # Signalen in gewone taal
    sig = []
    if l1_pct is not None and l1_pct < i['doelL1']:
        sig.append(('warn', f"L1 handelt {str(l1_pct).replace('.', ',')}% af; doel is {i['doelL1']}%."))
    if esc_pct is not None and esc_pct > i['escalatieMax']:
        sig.append(('warn', f"{str(esc_pct).replace('.', ',')}% van de tickets gaat naar L2 (maximaal {i['escalatieMax']}%)."))
    if niet_toegewezen:
        sig.append(('err' if len(niet_toegewezen) > 5 else 'warn', f'{len(niet_toegewezen)} open ticket(s) zonder behandelaar.'))
    if te_laat:
        sig.append(('err', f'{len(te_laat)} open ticket(s) over de deadline.'))
    if not uit['ingericht']:
        sig.append(('info', 'De L1/L2-inrichting is nog niet compleet (Servicedesk > Inrichting): niveaus en queues ontbreken.'))
    uit['signals'] = [{'level': a, 'text': t} for a, t in sig]
    _CACHE[sleutel] = (time.time(), uit)
    log.info('Servicedesk-KPI over %d dagen: %d tickets, %d tijdregels in %.1f s', dagen, len(nieuw), len(tijd), time.time() - begin_t)
    return uit


def _wk(d: datetime) -> str:
    j, w, _ = d.astimezone().isocalendar()
    return f'{j}-W{w:02d}'
