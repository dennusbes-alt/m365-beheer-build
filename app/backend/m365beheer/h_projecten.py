"""Projecten (startscherm > Projecten): actieve klantprojecten met fasen en taken bijhouden, taken oppakken/toewijzen/afronden,
tijd boeken (via ts.nieuw), notities, projectstatus. En van een definitieve saleskans een klantproject maken.

Project from template: de Autotask-API kent geen 'maak vanuit template'. De app maakt het klantproject (projectType Client,
opportunityID = de kans) en kopieert de fasen en taken van een templateproject (projectType Template): titel, omschrijving,
geschatte uren, afdeling/werksoort en de datums verschoven naar de nieuwe startdatum. Zonder template: een leeg project.
Taakstatus 5 = Complete (Autotask). NIET getest met een echte Autotask (vooral child-URL's van Tasks/Phases en verplichte velden).
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import _zet_auth
from .rechten import is_beheerder

log = logging.getLogger('m365beheer')
_CACHE: dict = {}
KLAAR = 5   # Tasks.status Complete


def _tijd(s):
    try:
        d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _lab(at, ent: str, veld: str) -> dict:
    return {str(p['value']): p['label'] for p in at.picklists(ent).get(veld, [])}


def _projecttype(at, patroon: str):
    return next((p['value'] for p in at.picklists('Projects').get('projectType', []) if re.search(patroon, str(p.get('label') or ''), re.I)), None)


def _klaar_projecten(at) -> set:
    from . import h_autotask as A
    return A._klaar(at, 'Projects') | {p['value'] for p in at.picklists('Projects').get('status', []) if re.search(r'inactive|inactief|cancel|geannuleerd', str(p.get('label') or ''), re.I)}


def _mensen(at) -> list[dict]:
    item = _CACHE.get('mensen')
    if item and time.time() - item[0] < 900:
        return item[1]
    r = at.query('Resources', [{'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'firstName', 'lastName'], 500)
    uit = sorted([{'id': x['id'], 'name': f"{x.get('firstName') or ''} {x.get('lastName') or ''}".strip()} for x in r], key=lambda x: x['name'].lower())
    _CACHE['mensen'] = (time.time(), uit)
    return uit


# ---------------------------------------------------------------- overzicht
@api('pr.overzicht')
def pr_overzicht(c: Ctx, b: dict) -> dict:
    """Actieve klant- en interne projecten met voortgang (taken af / totaal, uren gepland / geboekt) en of jij er taken in hebt."""
    from . import h_autotask as A
    from .h_management import _in
    _zet_auth(c)
    at = A._at()
    ik = A._ik(at)
    item = _CACHE.get('ov')
    if item and not b.get('fresh') and time.time() - item[0] < 60:
        p_lijst = item[1]
    else:
        klaar = _klaar_projecten(at)
        sjabloon = _projecttype(at, r'template|sjabloon')
        filters = [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar]
        if sjabloon is not None:
            filters.append({'op': 'noteq', 'field': 'projectType', 'value': sjabloon})
        pr = at.query('Projects', filters, ['id', 'projectName', 'projectNumber', 'companyID', 'status', 'startDateTime', 'endDateTime', 'projectLeadResourceID',
                                            'projectType', 'opportunityID', 'description'], 500)
        ids = [p['id'] for p in pr]
        taken = []
        for i in range(0, len(ids), 200):
            taken += at.query('Tasks', [{'op': 'in', 'field': 'projectID', 'value': ids[i:i + 200]}], ['id', 'projectID', 'status', 'assignedResourceID', 'estimatedHours',
                                                                                                    'endDateTime'], 5000, 5000)
        bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {p.get('companyID') for p in pr}, ['id', 'companyName'])}
        namen = {m['id']: m['name'] for m in _mensen(at)}
        st, tp = _lab(at, 'Projects', 'status'), _lab(at, 'Projects', 'projectType')
        nu = datetime.now(timezone.utc)
        p_lijst = []
        for p in pr:
            t = [x for x in taken if x.get('projectID') == p['id']]
            af = sum(1 for x in t if x.get('status') == KLAAR)
            eind = _tijd(p.get('endDateTime'))
            p_lijst.append({'id': p['id'], 'name': p.get('projectName') or '', 'number': p.get('projectNumber') or '', 'company': bedr.get(p.get('companyID'), ''),
                            'status': st.get(str(p.get('status')), ''), 'statusId': p.get('status'), 'type': tp.get(str(p.get('projectType')), ''),
                            'start': str(p.get('startDateTime') or '')[:10], 'end': str(p.get('endDateTime') or '')[:10],
                            'late': bool(eind and eind < nu and af < len(t)), 'lead': namen.get(p.get('projectLeadResourceID'), ''), 'leadId': p.get('projectLeadResourceID'),
                            'tasks': len(t), 'done': af, 'estimated': round(sum(float(x.get('estimatedHours') or 0) for x in t), 1),
                            'members': sorted({x.get('assignedResourceID') for x in t if x.get('assignedResourceID') and x.get('status') != KLAAR}),
                            'opportunityId': p.get('opportunityID')})
        p_lijst.sort(key=lambda p: (p['end'] or '9999', p['name'].lower()))
        _CACHE['ov'] = (time.time(), p_lijst)
    mijn = [p['id'] for p in p_lijst if ik['id'] in p['members'] or p['leadId'] == ik['id']]
    return {'projects': p_lijst, 'mine': mijn, 'me': ik['id'], 'at': datetime.now().strftime('%H:%M')}


@api('pr.project')
def pr_project(c: Ctx, b: dict) -> dict:
    """Eén project: fasen, taken (met geboekte uren), notities, keuzelijsten."""
    from . import h_autotask as A
    from .h_management import _in
    _zet_auth(c)
    at = A._at()
    pid = int(b['id'])
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_p = ex.submit(at.req, 'GET', f'Projects/{pid}')
        f_f = ex.submit(at.query, 'Phases', [{'op': 'eq', 'field': 'projectID', 'value': pid}], ['id', 'title', 'startDate', 'dueDate', 'parentPhaseID'], 500)
        f_t = ex.submit(at.query, 'Tasks', [{'op': 'eq', 'field': 'projectID', 'value': pid}],
                        ['id', 'title', 'description', 'status', 'phaseID', 'assignedResourceID', 'estimatedHours', 'remainingHours', 'startDateTime', 'endDateTime',
                         'completedDateTime', 'priorityLabel'], 2000)
        f_n = ex.submit(lambda: _notities(at, pid))
        p, fasen, taken, notities = (f_p.result().get('item') or {}), f_f.result(), f_t.result(), f_n.result()
    uren: dict = {}
    for i in range(0, len(taken), 200):
        for x in at.query('TimeEntries', [{'op': 'in', 'field': 'taskID', 'value': [t['id'] for t in taken[i:i + 200]]}], ['taskID', 'hoursWorked'], 10000, 10000):
            uren[x['taskID']] = uren.get(x['taskID'], 0) + float(x.get('hoursWorked') or 0)
    namen = {m['id']: m['name'] for m in _mensen(at)}
    bedr = {x['id']: x.get('companyName') or '' for x in _in(at, 'Companies', {p.get('companyID')}, ['id', 'companyName'])}
    ts = _lab(at, 'Tasks', 'status')
    nu = datetime.now(timezone.utc)
    taken_uit = [{'id': t['id'], 'title': t.get('title') or '', 'description': (t.get('description') or '').strip()[:2000], 'status': ts.get(str(t.get('status')), ''),
                  'statusId': t.get('status'), 'done': t.get('status') == KLAAR, 'phaseId': t.get('phaseID'), 'assigned': namen.get(t.get('assignedResourceID'), ''),
                  'assignedId': t.get('assignedResourceID'), 'estimated': float(t.get('estimatedHours') or 0), 'worked': round(uren.get(t['id'], 0), 2),
                  'start': str(t.get('startDateTime') or '')[:10], 'end': str(t.get('endDateTime') or '')[:10],
                  'late': bool(_tijd(t.get('endDateTime')) and _tijd(t.get('endDateTime')) < nu and t.get('status') != KLAAR)} for t in taken]
    taken_uit.sort(key=lambda t: (t['end'] or '9999', t['title'].lower()))
    from .h_servicedesk import _link
    web = getattr(at, 'web', '')
    return {'project': {'id': pid, 'name': p.get('projectName') or '', 'number': p.get('projectNumber') or '', 'company': bedr.get(p.get('companyID'), ''),
                        'companyId': p.get('companyID'), 'statusId': p.get('status'), 'start': str(p.get('startDateTime') or '')[:10], 'end': str(p.get('endDateTime') or '')[:10],
                        'leadId': p.get('projectLeadResourceID'), 'description': p.get('description') or '',
                        'url': f'{web}/Mvc/Projects/ProjectDetail.mvc?projectId={pid}' if web else ''},
            'phases': sorted([{'id': f['id'], 'title': f.get('title') or '', 'end': str(f.get('dueDate') or '')[:10]} for f in fasen], key=lambda f: f['end'] or f['title']),
            'tasks': taken_uit, 'notes': notities, 'people': _mensen(at),
            'taskStatuses': [{'value': p_['value'], 'label': p_['label']} for p_ in at.picklists('Tasks').get('status', [])],
            'projectStatuses': [{'value': p_['value'], 'label': p_['label']} for p_ in at.picklists('Projects').get('status', [])], '_link': bool(_link)}


def _notities(at, pid: int) -> list[dict]:
    try:
        r = at.query('ProjectNotes', [{'op': 'eq', 'field': 'projectID', 'value': pid}], ['id', 'title', 'description', 'createDateTime', 'creatorResourceID'], 100)
    except ApiFout as e:
        log.info('Projectnotities niet opgehaald: %s', e)
        return []
    return sorted([{'id': n['id'], 'title': n.get('title') or '', 'text': n.get('description') or '', 'at': str(n.get('createDateTime') or '')[:16].replace('T', ' ')}
                   for n in r], key=lambda n: n['at'], reverse=True)


# ---------------------------------------------------------------- wijzigen
def _patch_taak(at, pid: int, body: dict) -> None:
    try:
        at.req('PATCH', f'Projects/{pid}/Tasks', body)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        at.req('PATCH', 'Tasks', body)


@api('pr.taak')
def pr_taak(c: Ctx, b: dict) -> dict:
    """Taak wijzigen (één of meer): status (bijv. afronden), toewijzen, geschatte uren, einddatum, titel."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    pid = int(b['projectId'])
    body: dict = {}
    if b.get('status') not in (None, ''):
        body['status'] = int(b['status'])
    if 'assignedId' in b:
        if b['assignedId']:
            from .h_sdniveau import _rol
            body.update(assignedResourceID=int(b['assignedId']), assignedResourceRoleID=_rol(at, int(b['assignedId'])))
        else:
            body.update(assignedResourceID=None, assignedResourceRoleID=None)
    if b.get('estimated') not in (None, ''):
        body['estimatedHours'] = float(b['estimated'])
    if b.get('end'):
        body['endDateTime'] = str(b['end'])[:10] + 'T17:00:00Z'
    if b.get('title'):
        body['title'] = str(b['title'])[:255]
    if not body:
        raise ApiFout('Niets te wijzigen.')
    fouten = []
    for tid in b.get('ids') or [b.get('id')]:
        try:
            _patch_taak(at, pid, {'id': int(tid), **body})
        except ApiFout as e:
            fouten.append(str(e)[:200])
    _CACHE.pop('ov', None)
    if fouten:
        raise ApiFout('; '.join(fouten))
    c.L('Projecttaak bijgewerkt.')
    return {}


@api('pr.taak.nieuw')
def pr_taak_nieuw(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    pid = int(b['projectId'])
    titel = str(b.get('title') or '').strip()
    if len(titel) < 3:
        raise ApiFout('Geef de taak een titel.')
    tst = at.picklists('Tasks')
    status = next((p['value'] for p in tst.get('status', []) if re.fullmatch(r'\s*(new|nieuw)\s*', str(p.get('label') or ''), re.I)), 1)
    soort = next((p['value'] for p in tst.get('taskType', []) if re.search(r'fixed\s*work|vast\s*werk', str(p.get('label') or ''), re.I)),
                 (tst.get('taskType') or [{'value': 1}])[0]['value'])
    body = {'projectID': pid, 'title': titel[:255], 'status': status, 'taskType': soort, 'description': str(b.get('description') or '')[:7900] or None,
            'estimatedHours': float(b['estimated']) if b.get('estimated') else None, 'phaseID': int(b['phaseId']) if b.get('phaseId') else None,
            'endDateTime': str(b['end'])[:10] + 'T17:00:00Z' if b.get('end') else None}
    if b.get('assignedId'):
        from .h_sdniveau import _rol
        body.update(assignedResourceID=int(b['assignedId']), assignedResourceRoleID=_rol(at, int(b['assignedId'])))
        inst = A._instellingen()
        if inst.get('billingCodeID'):
            body['billingCodeID'] = inst['billingCodeID']
    body = {k: v for k, v in body.items() if v is not None}
    try:
        r = at.req('POST', f'Projects/{pid}/Tasks', body)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        r = at.req('POST', 'Tasks', body)
    _CACHE.pop('ov', None)
    c.L(f'Projecttaak toegevoegd: {titel}.')
    return {'id': (r or {}).get('itemId')}


@api('pr.status')
def pr_status(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    body = {'id': int(b['id'])}
    if b.get('status') not in (None, ''):
        body['status'] = int(b['status'])
    if b.get('end'):
        body['endDateTime'] = str(b['end'])[:10] + 'T17:00:00Z'
    if b.get('leadId'):
        body['projectLeadResourceID'] = int(b['leadId'])
    at.req('PATCH', 'Projects', body)
    _CACHE.pop('ov', None)
    c.L('Project bijgewerkt.')
    return {}


@api('pr.notitie')
def pr_notitie(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    tekst = str(b.get('text') or '').strip()
    if not tekst:
        raise ApiFout('Schrijf de notitie.')
    pid = int(b['projectId'])
    inst = A._instellingen()
    pl = at.picklists('ProjectNotes')
    body = {'projectID': pid, 'title': str(b.get('title') or 'Notitie')[:250], 'description': tekst[:3200], 'isAnnouncement': False,
            'noteType': (pl.get('noteType') or [{'value': inst.get('noteType') or 1}])[0]['value'], 'publish': inst.get('publish') or 1}
    try:
        at.req('POST', f'Projects/{pid}/Notes', body)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        at.req('POST', 'ProjectNotes', body)
    c.L('Projectnotitie toegevoegd.')
    return {}


# ---------------------------------------------------------------- van saleskans naar project
@api('pr.templates')
def pr_templates(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    from .h_contracten import contract_van_kans
    vast = bool(contract_van_kans(int(b['opportunityId']))) if b.get('opportunityId') else False   # sales legde al een vaste prijs vast
    tp = _projecttype(at, r'template|sjabloon')
    if tp is None:
        return {'templates': [], 'people': _mensen(at), 'fixedContract': vast}
    r = at.query('Projects', [{'op': 'eq', 'field': 'projectType', 'value': tp}], ['id', 'projectName', 'description'], 300)
    return {'templates': sorted([{'id': x['id'], 'name': x.get('projectName') or '', 'description': (x.get('description') or '')[:200]} for x in r], key=lambda x: x['name'].lower()),
            'people': _mensen(at), 'fixedContract': vast}


@api('pr.vankans')
def pr_vankans(c: Ctx, b: dict) -> dict:
    """Klantproject van een definitieve saleskans (alleen app-beheerder), optioneel met fasen en taken uit een templateproject."""
    from . import h_autotask as A
    from .h_sales import statussen
    _zet_auth(c)
    if not is_beheerder(c.staat):
        raise ApiFout('Alleen de app-beheerder maakt projecten van saleskansen.')
    at = A._at()
    kans = at.req('GET', f"Opportunities/{int(b['opportunityId'])}").get('item') or {}
    if not kans:
        raise ApiFout('Saleskans niet gevonden.')
    from .h_sales import getal
    if getal(kans.get('status')) not in statussen(at)['wonAll']:
        # Project maken van een open kans = eerst definitief maken (gewonnen)
        from .h_sales import maak_definitief
        maak_definitief(at, kans['id'])
    bestaand = at.query('Projects', [{'op': 'eq', 'field': 'opportunityID', 'value': kans['id']}], ['id', 'projectName'], 5)
    if bestaand:
        raise ApiFout(f"Van deze kans is al een project gemaakt: {bestaand[0].get('projectName')}.")
    start = datetime.fromisoformat(str(b.get('start') or datetime.now().strftime('%Y-%m-%d'))[:10]).replace(hour=8, tzinfo=timezone.utc)
    eind = datetime.fromisoformat(str(b.get('end'))[:10]).replace(hour=17, tzinfo=timezone.utc) if b.get('end') else start + timedelta(days=30)
    klant = _projecttype(at, r'client|klant')
    if klant is None:
        raise ApiFout("Autotask kent geen projecttype 'Client'.")
    pst = at.picklists('Projects').get('status', [])
    status = next((p['value'] for p in pst if re.fullmatch(r'\s*(new|nieuw|active|actief)\s*', str(p.get('label') or ''), re.I)),
                  next((p['value'] for p in pst if p.get('default')), pst[0]['value'] if pst else 1))
    naam = str(b.get('name') or kans.get('title') or 'Project').strip()[:100]
    body = {'projectName': naam, 'companyID': kans['companyID'], 'projectType': klant, 'status': status, 'startDateTime': _iso(start), 'endDateTime': _iso(eind),
            'opportunityID': kans['id'], 'description': (str(b.get('description') or '') or str(kans.get('description') or ''))[:7900] or None}
    if b.get('leadId'):
        body['projectLeadResourceID'] = int(b['leadId'])
    from .h_contracten import contract_van_kans, vast_contract
    if contract_van_kans(kans['id']):   # vaste prijs (bijv. migratie) die sales bij de kans vastlegde
        body['contractID'] = contract_van_kans(kans['id'])
    elif b.get('fixedAmount') and float(b['fixedAmount']) > 0:   # vaste prijs gekozen in 'Project maken': Fixed Price-contract voor dit project
        maanden = max(1, round((eind - start).days / 30) + 1)
        con = vast_contract(at, kans['companyID'], f'Vaste prijs - {naam}'[:100], float(b['fixedAmount']), float(b.get('fixedHours') or 0), start, maanden,
                            str(b.get('description') or kans.get('description') or ''))
        body['contractID'] = con['id']
    body = {k: v for k, v in body.items() if v is not None}
    r = at.req('POST', 'Projects', body)
    pid = (r or {}).get('itemId')
    if not pid:
        raise ApiFout('Autotask gaf geen projectnummer terug.')
    fasen_n = taken_n = 0
    fouten = []
    if b.get('templateId'):
        fasen_n, taken_n, fouten = _kopieer(at, int(b['templateId']), int(pid), start)
    _CACHE.pop('ov', None)
    from . import h_sales
    h_sales.vergeet()
    c.L(f"Project '{naam}' aangemaakt van saleskans" + (f' met {fasen_n} fase(n) en {taken_n} taak/taken uit het template' if b.get('templateId') else '') + '.')
    return {'id': pid, 'phases': fasen_n, 'tasks': taken_n, 'errors': fouten[:10]}


def _kopieer(at, tid: int, pid: int, start: datetime) -> tuple[int, int, list]:
    """Fasen en taken van templateproject tid naar project pid; datums schuiven mee met het verschil in startdatum."""
    tpl = at.req('GET', f'Projects/{tid}').get('item') or {}
    t_start = _tijd(tpl.get('startDateTime')) or start
    schuif = start - t_start
    fasen = at.query('Phases', [{'op': 'eq', 'field': 'projectID', 'value': tid}], ['id', 'title', 'description', 'startDate', 'dueDate', 'parentPhaseID'], 500)
    taken = at.query('Tasks', [{'op': 'eq', 'field': 'projectID', 'value': tid}],
                     ['id', 'title', 'description', 'phaseID', 'estimatedHours', 'startDateTime', 'endDateTime', 'taskType', 'departmentID', 'billingCodeID',
                      'priorityLabel', 'isVisibleInClientPortal'], 2000)
    tst = at.picklists('Tasks')
    nieuw_status = next((p['value'] for p in tst.get('status', []) if re.fullmatch(r'\s*(new|nieuw)\s*', str(p.get('label') or ''), re.I)), 1)
    verschuif = lambda s: _iso(_tijd(s) + schuif) if _tijd(s) else None  # noqa: E731
    kaart: dict = {}
    fouten: list = []
    # Fasen in volgorde (ouders eerst)
    rest = list(fasen)
    while rest:
        klaar = [f for f in rest if not f.get('parentPhaseID') or f['parentPhaseID'] in kaart]
        if not klaar:
            klaar = rest   # ouder onbekend: zonder ouder aanmaken
        for f in klaar:
            body = {'projectID': pid, 'title': f.get('title') or 'Fase', 'description': f.get('description') or None, 'startDate': verschuif(f.get('startDate')),
                    'dueDate': verschuif(f.get('dueDate')), 'parentPhaseID': kaart.get(f.get('parentPhaseID'))}
            body = {k: v for k, v in body.items() if v is not None}
            try:
                try:
                    r = at.req('POST', f'Projects/{pid}/Phases', body)
                except ApiFout as e:
                    if e.status not in (404, 405):
                        raise
                    r = at.req('POST', 'Phases', body)
                kaart[f['id']] = (r or {}).get('itemId')
            except ApiFout as e:
                fouten.append(f"Fase {f.get('title')}: {str(e)[:120]}")
            rest.remove(f)
    n_taken = 0
    for t in taken:
        body = {'projectID': pid, 'title': t.get('title') or 'Taak', 'description': t.get('description') or None, 'status': nieuw_status,
                'taskType': t.get('taskType'), 'estimatedHours': t.get('estimatedHours'), 'phaseID': kaart.get(t.get('phaseID')),
                'startDateTime': verschuif(t.get('startDateTime')), 'endDateTime': verschuif(t.get('endDateTime')), 'departmentID': t.get('departmentID'),
                'billingCodeID': t.get('billingCodeID'), 'isVisibleInClientPortal': t.get('isVisibleInClientPortal')}
        body = {k: v for k, v in body.items() if v is not None}
        try:
            try:
                at.req('POST', f'Projects/{pid}/Tasks', body)
            except ApiFout as e:
                if e.status not in (404, 405):
                    raise
                at.req('POST', 'Tasks', body)
            n_taken += 1
        except ApiFout as e:
            fouten.append(f"Taak {t.get('title')}: {str(e)[:120]}")
    if fouten:
        log.info('Template kopiëren: %d fout(en): %s', len(fouten), fouten[:3])
    return len([v for v in kaart.values() if v]), n_taken, fouten


def vergeet() -> None:
    _CACHE.clear()
