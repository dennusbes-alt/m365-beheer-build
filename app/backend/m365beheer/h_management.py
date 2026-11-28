"""Management: inzichten en rapportage op managementniveau (startscherm > Management).

Bundelt wat de app al weet, plus servicedeskcijfers uit Autotask:
- Servicedesk (Autotask): nieuwe/afgeronde/open tickets, doorlooptijd, uren (facturabel), per klant, per medewerker, per week.
- Back-up (Datto/Unitrends): slagingspercentage, klanten met fouten.
- E-mailbeveiliging (EasyDMARC): DMARC-naleving, beleid, domeinen met actie.
- Microsoft 365: licenties (ingekocht/toegewezen/vrij/mogelijke besparing, verlengingen) en GDAP-toegang.
Alles alleen in het geheugen; PDF via h_management_pdf. Alleen met een Justdata-login (poortwachter 'mg.').
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone

from .clients import ApiFout, achtergrond_fn
from .context import API, Ctx, api

log = logging.getLogger('m365beheer')

_AT_JOB: dict = {'bezig': False, 'dagen': 0, 'eind': 0.0, 'data': None, 'fout': ''}
_at_lock = threading.Lock()
AT_VERS = 600   # servicedeskcijfers 10 minuten hergebruiken (Vernieuwen haalt altijd opnieuw op)


# ---------------------------------------------------------------- Autotask
def _tijd(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _in(at, entiteit: str, ids, velden: list) -> list[dict]:
    """Opvragen op id in blokken (Autotask-filter 'in')."""
    ids = [i for i in dict.fromkeys(ids) if i is not None]
    uit = []
    for i in range(0, len(ids), 200):
        uit += at.query(entiteit, [{'op': 'in', 'field': 'id', 'value': ids[i:i + 200]}], velden, 500)
    return uit


def _week(d: datetime) -> str:
    j, w, _ = d.astimezone().isocalendar()
    return f'{j}-W{w:02d}'


def at_statistiek(dagen: int) -> dict:
    """Servicedeskcijfers over de laatste `dagen` dagen (alleen lezen)."""
    from . import h_autotask as A
    at = A._at()
    inst = A._instellingen()
    nu = datetime.now(timezone.utc)
    van = nu - timedelta(days=dagen)
    iso = van.strftime('%Y-%m-%dT%H:%M:%SZ')
    klaar = A._klaar(at, 'Tickets') | ({inst['statusKlaar']} if inst.get('statusKlaar') else set())
    tv = ['id', 'companyID', 'status', 'priority', 'queueID', 'createDate', 'completedDate', 'assignedResourceID', 'source']
    nieuw = at.query('Tickets', [{'op': 'gte', 'field': 'createDate', 'value': iso}], tv, 10000, 10000)
    afgerond = at.query('Tickets', [{'op': 'gte', 'field': 'completedDate', 'value': iso}], tv, 10000, 10000)
    open_ = at.query('Tickets', [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar], tv, 10000, 10000)
    tijd = at.query('TimeEntries', [{'op': 'gte', 'field': 'dateWorked', 'value': iso}],
                    ['id', 'ticketID', 'taskID', 'resourceID', 'hoursWorked', 'isNonBillable', 'dateWorked'], 20000, 20000)
    # Bedrijf bij elke tijdregel: via het ticket, of via taak -> project
    tick_bedrijf = {t['id']: t.get('companyID') for t in nieuw + afgerond + open_}
    tick_bedrijf.update({t['id']: t.get('companyID') for t in _in(at, 'Tickets', [x.get('ticketID') for x in tijd if x.get('ticketID') and x.get('ticketID') not in tick_bedrijf], ['id', 'companyID'])})
    taken = {t['id']: t.get('projectID') for t in _in(at, 'Tasks', [x.get('taskID') for x in tijd if x.get('taskID')], ['id', 'projectID'])}
    proj = {p['id']: p.get('companyID') for p in _in(at, 'Projects', list(taken.values()), ['id', 'companyID'])}

    def bedrijf_van(x):
        if x.get('ticketID'):
            return tick_bedrijf.get(x['ticketID'])
        return proj.get(taken.get(x.get('taskID')))
    bedrijven = {b['id']: b.get('companyName') or f"Bedrijf {b['id']}" for b in
                 _in(at, 'Companies', set(tick_bedrijf.values()) | set(proj.values()), ['id', 'companyName'])}
    intern = int(inst.get('internCompanyID') or 0)
    bedrijven.setdefault(intern, 'Intern (Justdata)')
    mensen = {r['id']: f"{r.get('firstName') or ''} {r.get('lastName') or ''}".strip() or f"Medewerker {r['id']}" for r in
              _in(at, 'Resources', {x.get('resourceID') for x in tijd} | {t.get('assignedResourceID') for t in afgerond}, ['id', 'firstName', 'lastName'])}
    pl = at.picklists('Tickets')
    lab = lambda veld: {str(p['value']): p['label'] for p in pl.get(veld, [])}  # noqa: E731
    prio, queue = lab('priority'), lab('queueID')

    # Doorlooptijd (aanmaken -> afgerond) van de in de periode afgeronde tickets, in dagen
    door = [(_tijd(t.get('completedDate')) - _tijd(t.get('createDate'))).total_seconds() / 86400 for t in afgerond
            if _tijd(t.get('completedDate')) and _tijd(t.get('createDate'))]
    door = [d for d in door if d >= 0]
    leeftijd = {'0-7 dagen': 0, '8-30 dagen': 0, '31-90 dagen': 0, 'Ouder dan 90 dagen': 0}
    for t in open_:
        c = _tijd(t.get('createDate'))
        d = (nu - c).days if c else 0
        leeftijd['0-7 dagen' if d <= 7 else '8-30 dagen' if d <= 30 else '31-90 dagen' if d <= 90 else 'Ouder dan 90 dagen'] += 1
    uren = sum(float(x.get('hoursWorked') or 0) for x in tijd)
    fact = sum(float(x.get('hoursWorked') or 0) for x in tijd if not x.get('isNonBillable'))

    # Per klant
    per: dict = {}
    def k(cid):
        return per.setdefault(cid, {'id': cid, 'name': bedrijven.get(cid, f'Bedrijf {cid}'), 'created': 0, 'completed': 0, 'open': 0, 'hours': 0.0, 'billable': 0.0})
    for t in nieuw:
        k(t.get('companyID'))['created'] += 1
    for t in afgerond:
        k(t.get('companyID'))['completed'] += 1
    for t in open_:
        k(t.get('companyID'))['open'] += 1
    for x in tijd:
        r = k(bedrijf_van(x))
        h = float(x.get('hoursWorked') or 0)
        r['hours'] += h
        if not x.get('isNonBillable'):
            r['billable'] += h
    klanten = sorted(per.values(), key=lambda r: (-r['hours'], -r['created'], r['name'].lower()))
    for r in klanten:
        r['hours'], r['billable'] = round(r['hours'], 1), round(r['billable'], 1)
        r['internal'] = r['id'] == intern

    # Per medewerker
    pm: dict = {}
    for x in tijd:
        r = pm.setdefault(x.get('resourceID'), {'name': mensen.get(x.get('resourceID'), 'Onbekend'), 'hours': 0.0, 'billable': 0.0, 'completed': 0})
        h = float(x.get('hoursWorked') or 0)
        r['hours'] += h
        r['billable'] += 0 if x.get('isNonBillable') else h
    for t in afgerond:
        if t.get('assignedResourceID') in mensen:
            pm.setdefault(t['assignedResourceID'], {'name': mensen[t['assignedResourceID']], 'hours': 0.0, 'billable': 0.0, 'completed': 0})['completed'] += 1
    medewerkers = sorted(({**r, 'hours': round(r['hours'], 1), 'billable': round(r['billable'], 1),
                           'billablePct': round(r['billable'] * 100 / r['hours']) if r['hours'] else None} for r in pm.values()),
                         key=lambda r: -r['hours'])

    # Per week (trend)
    weken: dict = {}
    for i in range(0, dagen + 7, 7):
        weken.setdefault(_week(van + timedelta(days=i)), {'created': 0, 'completed': 0, 'hours': 0.0})
    weken.setdefault(_week(nu), {'created': 0, 'completed': 0, 'hours': 0.0})
    for t in nieuw:
        if (d := _tijd(t.get('createDate'))):
            weken.setdefault(_week(d), {'created': 0, 'completed': 0, 'hours': 0.0})['created'] += 1
    for t in afgerond:
        if (d := _tijd(t.get('completedDate'))):
            weken.setdefault(_week(d), {'created': 0, 'completed': 0, 'hours': 0.0})['completed'] += 1
    for x in tijd:
        if (d := _tijd(x.get('dateWorked'))):
            weken.setdefault(_week(d), {'created': 0, 'completed': 0, 'hours': 0.0})['hours'] += float(x.get('hoursWorked') or 0)
    weken_l = [{'week': w, 'label': 'wk ' + w[-2:].lstrip('0'), **v, 'hours': round(v['hours'], 1)} for w, v in sorted(weken.items())]

    tel = lambda lijst, veld, labels: sorted(  # noqa: E731
        [{'label': labels.get(str(w), str(w) if w is not None else 'Geen'), 'count': n} for w, n in
         {w: sum(1 for t in lijst if t.get(veld) == w) for w in {t.get(veld) for t in lijst}}.items()], key=lambda r: -r['count'])
    return {
        'days': dagen, 'at': datetime.now().strftime('%d-%m-%Y %H:%M'),
        'kpi': {'created': len(nieuw), 'completed': len(afgerond), 'open': len(open_),
                'openOld': leeftijd['31-90 dagen'] + leeftijd['Ouder dan 90 dagen'], 'openVeryOld': leeftijd['Ouder dan 90 dagen'],
                'leadMedian': round(statistics.median(door), 1) if door else None, 'leadAvg': round(sum(door) / len(door), 1) if door else None,
                'within1': round(sum(1 for d in door if d <= 1) * 100 / len(door)) if door else None,
                'hours': round(uren, 1), 'billable': round(fact, 1), 'billablePct': round(fact * 100 / uren) if uren else None,
                'customers': len([r for r in klanten if not r['internal'] and (r['created'] or r['hours'])])},
        'weeks': weken_l[-14:], 'customers': klanten, 'employees': medewerkers, 'openAge': leeftijd,
        'priorities': tel(open_, 'priority', prio), 'queues': tel(nieuw, 'queueID', queue),
    }


def _at_start(dagen: int) -> None:
    with _at_lock:
        if _AT_JOB['bezig']:
            return
        _AT_JOB.update(bezig=True, fout='')

    def run():
        begin = time.time()
        try:
            data = at_statistiek(dagen)
            with _at_lock:
                _AT_JOB.update(data=data, dagen=dagen)
        except Exception as e:  # noqa: BLE001
            log.info('Management Autotask: %s', str(e)[:300])
            with _at_lock:
                _AT_JOB['fout'] = str(e)[:300]
        finally:
            with _at_lock:
                _AT_JOB.update(bezig=False, eind=time.time())
            log.info('Management Autotask: %.0f s', time.time() - begin)
    threading.Thread(target=achtergrond_fn(run), daemon=True, name='management-at').start()


def _autotask(c: Ctx, dagen: int, vers: bool) -> dict:
    from . import h_autotask as A
    try:
        if not A._sleutel():
            return {'configured': False}
    except Exception:  # noqa: BLE001
        return {'configured': False}
    with _at_lock:
        bezig, eind, oud = _AT_JOB['bezig'], _AT_JOB['eind'], _AT_JOB['dagen']
    if not bezig and (vers or not eind or time.time() - eind > AT_VERS or oud != dagen):
        _at_start(dagen)
    with _at_lock:
        d = _AT_JOB['data'] if _AT_JOB['data'] and _AT_JOB['dagen'] == dagen else None
        return {'configured': True, 'busy': _AT_JOB['bezig'], 'error': _AT_JOB['fout'], 'data': d}


# ---------------------------------------------------------------- Back-up, e-mail en Microsoft 365 (bestaande overzichten)
def _backup(c: Ctx, vers: bool) -> dict:
    try:
        r = API['bk.overzicht'](c, {'fresh': vers})
    except ApiFout as e:
        return {'configured': False, 'error': str(e)}
    if not r.get('configured'):
        return {'configured': False}
    kl = r.get('customers') or []
    items = [it for k in kl for it in k['items']]
    tel = {s: sum(1 for it in items if it['status'] == s) for s in ('ok', 'warn', 'err', 'unknown', 'paused')}
    beoordeeld = tel['ok'] + tel['warn'] + tel['err']
    bronnen = []
    for b in r.get('sources') or []:
        bi = [it for it in items if it['source'] == b]
        bb = sum(1 for it in bi if it['status'] in ('ok', 'warn', 'err'))
        bronnen.append({'name': b, 'items': len(bi), 'ok': sum(1 for it in bi if it['status'] == 'ok'),
                        'pct': round(sum(1 for it in bi if it['status'] == 'ok') * 100 / bb, 1) if bb else None,
                        'error': (r.get('errors') or {}).get(b, '')})
    return {'configured': True, 'busy': r.get('busy'), 'at': r.get('at'), 'errors': r.get('errors') or {},
            'kpi': {'customers': len(kl), 'items': len(items), **tel, 'pct': round(tel['ok'] * 100 / beoordeeld, 1) if beoordeeld else None,
                    'custOk': sum(1 for k in kl if k['status'] == 'ok'), 'custWarn': sum(1 for k in kl if k['status'] == 'warn'),
                    'custErr': sum(1 for k in kl if k['status'] == 'err')},
            'sources': bronnen,
            'customers': [{'name': k['name'], 'status': k['status'], 'sources': k['sources'], **k['counts'],
                           'issues': [{'name': it['name'], 'source': it['source'], 'status': it['status'], 'message': it.get('message') or ''}
                                      for it in k['items'] if it['status'] in ('err', 'warn')][:8]} for k in kl]}


def _email(c: Ctx, dagen: int, vers: bool) -> dict:
    try:
        r = API['dm.overzicht'](c, {'days': min(dagen, 90), 'fresh': vers})
    except ApiFout as e:
        return {'configured': False, 'error': str(e)}
    if not r.get('configured'):
        return {'configured': False}
    orgs = r.get('orgs') or []
    doms = [d for o in orgs for d in o['domains']]
    passed, failed = sum(o.get('passed') or 0 for o in orgs), sum(o.get('failed') or 0 for o in orgs)
    pol = {p: sum(1 for d in doms if d['policy'] == p) for p in ('reject', 'quarantine', 'none', 'missing')}
    return {'configured': True, 'busy': r.get('busy'), 'at': r.get('at'), 'days': r.get('days'), 'error': r.get('error') or '',
            'kpi': {'customers': len(orgs), 'domains': len(doms), 'volume': sum(o.get('volume') or 0 for o in orgs), 'passed': passed, 'failed': failed,
                    'pct': round(passed * 100 / (passed + failed), 1) if passed + failed else None,
                    'domOk': sum(1 for d in doms if d['status'] == 'ok'), 'domWarn': sum(1 for d in doms if d['status'] == 'warn'),
                    'domErr': sum(1 for d in doms if d['status'] == 'err'), 'protected': pol['reject'] + pol['quarantine']},
            'policies': pol,
            'customers': [{'name': o['name'], 'status': o['status'], 'domains': len(o['domains']), 'volume': o.get('volume') or 0,
                           'passed': o.get('passed') or 0, 'failed': o.get('failed') or 0, 'pct': o.get('compliance'),
                           'issues': [{'domain': d['domain'], 'status': d['status'], 'text': (d['problems'][0]['text'] if d['problems'] else '')}
                                      for d in o['domains'] if d['status'] != 'ok'][:6]} for o in orgs]}


def _m365(c: Ctx, reserve: list | None = None) -> dict:
    s = c.staat
    # Klantenoverzicht van de app; de lijst van het scherm alleen als reserve (bijv. net na het opstarten)
    kl = [k for k in (s.klanten if s.klanten is not None else [x for x in (reserve or []) if isinstance(x, dict)]) if not k.get('own')]
    gdap = {'customers': len(kl), 'access': sum(1 for k in kl if k.get('access')), 'noAccess': sum(1 for k in kl if not k.get('access')),
            'expiring': sorted([{'name': k['name'], 'days': k['days'], 'end': k.get('end') or ''} for k in kl
                                if k.get('days') is not None and k['days'] <= 30], key=lambda x: x['days'])}
    try:
        adm = API['adm.status'](c, {})
    except Exception:  # noqa: BLE001
        adm = {}
    ok = [k for k in (adm.get('klanten') or []) if k.get('ok')]
    nu = datetime.now(timezone.utc)
    verleng = []
    for k in ok:
        for x in k.get('skus') or []:
            d = _tijd(x.get('renew'))
            if x.get('paid') and d and 0 <= (d - nu).days <= 45:
                verleng.append({'customer': k['name'], 'name': x['name'], 'date': d.strftime('%d-%m-%Y'), 'days': (d - nu).days, 'bought': x['bought'], 'assigned': x['assigned']})
    som = lambda veld: sum(k.get(veld) or 0 for k in ok)  # noqa: E731
    lic = {'loaded': bool(ok), 'busy': bool(adm.get('bezig')), 'at': adm.get('eind') or '', 'customers': len(ok),
           'failed': sum(1 for k in (adm.get('klanten') or []) if k.get('ok') is False),
           'bought': som('bought'), 'assigned': som('assigned'), 'free': som('free'), 'short': som('short'), 'unused': som('unused'),
           'disabled': som('disabled'), 'inactive': som('inactive'), 'saving': som('saving'), 'trials': som('trials'),
           'usePct': round(som('assigned') * 100 / som('bought'), 1) if som('bought') else None,
           'renewals': sorted(verleng, key=lambda x: x['days']),
           'perCustomer': sorted(({'name': k['name'], 'bought': k.get('bought') or 0, 'assigned': k.get('assigned') or 0, 'free': k.get('free') or 0,
                                   'unused': k.get('unused') or 0, 'disabled': k.get('disabled') or 0, 'saving': k.get('saving') or 0} for k in ok),
                                 key=lambda r: (-r['saving'], r['name'].lower()))}
    return {'gdap': gdap, 'licenses': lic}


# ---------------------------------------------------------------- Aandachtspunten (managementsamenvatting)
def _punten(d: dict) -> list[dict]:
    p = []
    bk, em, at, m = d.get('backup') or {}, d.get('email') or {}, (d.get('autotask') or {}).get('data'), d.get('m365') or {}
    if bk.get('configured') and bk.get('kpi'):
        fout = [k['name'] for k in bk['customers'] if k['status'] == 'err']
        if fout:
            p.append({'level': 'err', 'area': 'Back-up', 'text': f"{len(fout)} klant(en) met mislukte back-ups: {', '.join(fout[:6])}{' e.a.' if len(fout) > 6 else ''}."})
        if bk['kpi'].get('pct') is not None and bk['kpi']['pct'] < 95:
            p.append({'level': 'err' if bk['kpi']['pct'] < 85 else 'warn', 'area': 'Back-up',
                      'text': f"Slagingspercentage back-ups is {str(bk['kpi']['pct']).replace('.', ',')}% (norm: 95% of hoger)."})
    if em.get('configured') and em.get('kpi'):
        geen = sum(1 for c in em['customers'] for i in c['issues'] if i['status'] == 'err')
        if geen:
            p.append({'level': 'err', 'area': 'E-mail', 'text': f'{geen} domein(en) met een kritiek e-mailbeveiligingsprobleem (bijv. geen DMARC/SPF of veel falende mail).'})
        if em['policies'].get('none'):
            p.append({'level': 'warn', 'area': 'E-mail', 'text': f"{em['policies']['none']} domein(en) staan nog op DMARC 'monitoren': nepmail wordt niet tegengehouden."})
    if at:
        k = at['kpi']
        if k['openVeryOld']:
            p.append({'level': 'warn', 'area': 'Servicedesk', 'text': f"{k['openVeryOld']} open ticket(s) ouder dan 90 dagen."})
        if k['created'] > k['completed'] * 1.2 and k['created'] >= 10:
            p.append({'level': 'warn', 'area': 'Servicedesk', 'text': f"Meer tickets binnengekomen ({k['created']}) dan afgerond ({k['completed']}): de werkvoorraad groeit."})
        if k['billablePct'] is not None and k['billablePct'] < 60:
            p.append({'level': 'info', 'area': 'Servicedesk', 'text': f"{k['billablePct']}% van de geregistreerde uren is facturabel."})
    g, lic = m.get('gdap') or {}, m.get('licenses') or {}
    if g.get('expiring'):
        p.append({'level': 'warn', 'area': 'Microsoft 365', 'text': f"GDAP-relatie van {len(g['expiring'])} klant(en) verloopt binnen 30 dagen: {', '.join(x['name'] for x in g['expiring'][:5])}."})
    if g.get('noAccess'):
        p.append({'level': 'info', 'area': 'Microsoft 365', 'text': f"{g['noAccess']} klant(en) zonder (volledige) GDAP-toegang."})
    if lic.get('loaded') and lic.get('saving'):
        p.append({'level': 'info', 'area': 'Microsoft 365', 'text': f"{lic['saving']} betaalde licentie(s) mogelijk overbodig (vrij, uitgeschakeld of >90 dagen niet gebruikt)."})
    if lic.get('renewals'):
        p.append({'level': 'info', 'area': 'Microsoft 365', 'text': f"{len(lic['renewals'])} licentieabonnement(en) worden binnen 45 dagen verlengd."})
    return sorted(p, key=lambda x: {'err': 0, 'warn': 1, 'info': 2}[x['level']])


def verzamel(c: Ctx, dagen: int, vers: bool = False, klanten: list | None = None) -> dict:
    d = {'days': dagen, 'at': datetime.now().strftime('%d-%m-%Y %H:%M'),
         'backup': _backup(c, vers), 'email': _email(c, dagen, vers), 'autotask': _autotask(c, dagen, vers), 'm365': _m365(c, klanten)}
    d['points'] = _punten(d)
    d['busy'] = bool(d['backup'].get('busy') or d['email'].get('busy') or d['autotask'].get('busy') or d['m365']['licenses'].get('busy'))
    return d


@api('mg.overzicht')
def mg_overzicht(c: Ctx, b: dict) -> dict:
    dagen = max(7, min(365, int(b.get('days') or 30)))
    return verzamel(c, dagen, bool(b.get('fresh')), b.get('customers'))


@api('mg.licenties')
def mg_licenties(c: Ctx, b: dict) -> dict:
    """Licentieoverzicht van alle klanten (op de achtergrond) starten; zelfde klus als Administratie."""
    return API['adm.start'](c, {'customers': b.get('customers') or []})


@api('mg.pdf')
def mg_pdf(c: Ctx, b: dict) -> dict:
    from .h_management_pdf import maak_pdf
    from .h_rapport import _openen
    from pathlib import Path
    dagen = max(7, min(365, int(b.get('days') or 30)))
    d = verzamel(c, dagen, klanten=b.get('customers'))
    map_ = Path.home() / 'Downloads'
    if not map_.is_dir():
        map_ = Path.home()
    pad = map_ / f'Managementrapportage-Justdata-{datetime.now():%Y-%m-%d}.pdf'
    n = 2
    while pad.exists():
        pad = pad.with_name(f'Managementrapportage-Justdata-{datetime.now():%Y-%m-%d}-{n}.pdf')
        n += 1
    door = (c.staat.beheerder or {}).get('name') or ''
    pad.write_bytes(maak_pdf(d, door))
    c.L(f'Managementrapportage opgeslagen: {pad}')
    _openen(pad)
    return {'path': str(pad)}
