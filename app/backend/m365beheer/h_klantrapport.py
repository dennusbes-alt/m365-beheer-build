"""Kwartaalrapportage per klant (Management > Klantrapportage): wat heeft Justdata het afgelopen kwartaal voor deze klant gedaan.

Bedoeld om aan de klant te geven, dus in gewone taal (Jip-en-Janneketaal). Bronnen:
- Autotask: tickets (binnengekomen, opgelost, nog open), doorlooptijd, eerste reactie, uren (tickets en projecten),
  per medewerker, per contactpersoon, per soort vraag, per maand en per weekdag; vergeleken met het kwartaal ervoor.
- Back-up (Datto/Unitrends) en e-mailbeveiliging (EasyDMARC): de bestaande overzichten, gekoppeld op klantnaam.
- Microsoft 365: licenties uit het licentieoverzicht (als dat is opgehaald), via de koppeling klant -> Autotask-bedrijf.
Alleen lezen, alleen in het geheugen (10 minuten hergebruik). Alleen voor de directie (poortwachter 'mg.').
"""
from __future__ import annotations

import logging
import re
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone

from .clients import ApiFout
from .context import API, Ctx, api

log = logging.getLogger('m365beheer')

MAANDEN = ['januari', 'februari', 'maart', 'april', 'mei', 'juni', 'juli', 'augustus', 'september', 'oktober', 'november', 'december']
DAGEN = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']
_CACHE: dict = {}
_lock = threading.Lock()
VERS = 600


# ---------------------------------------------------------------- kwartalen
def _kwartaal(j: int, k: int) -> dict:
    van = datetime(j, 3 * k - 2, 1)
    tot = datetime(j + (k == 4), 1 if k == 4 else 3 * k + 1, 1)
    return {'key': f'{j}-K{k}', 'year': j, 'q': k, 'label': f'{k}e kwartaal {j}', 'short': f'K{k} {j}',
            'months': [MAANDEN[3 * k - 3 + i] for i in range(3)], 'range': f'{MAANDEN[3 * k - 3]} t/m {MAANDEN[3 * k - 1]} {j}',
            'van': van, 'tot': tot}


def _vorig(kw: dict) -> dict:
    return _kwartaal(kw['year'] - (kw['q'] == 1), 4 if kw['q'] == 1 else kw['q'] - 1)


def kwartalen(n: int = 8) -> list[dict]:
    nu = datetime.now()
    kw = _kwartaal(nu.year, (nu.month - 1) // 3 + 1)
    uit = []
    for i in range(n):
        uit.append({k: v for k, v in kw.items() if k not in ('van', 'tot')} | {'current': i == 0})
        kw = _vorig(kw)
    return uit


def _uit_sleutel(s: str) -> dict:
    m = re.fullmatch(r'(\d{4})-K([1-4])', str(s or ''))
    if not m:
        nu = datetime.now()
        return _vorig(_kwartaal(nu.year, (nu.month - 1) // 3 + 1))   # standaard: het vorige (volledige) kwartaal
    return _kwartaal(int(m[1]), int(m[2]))


def _utc(d: datetime) -> datetime:
    return d.astimezone(timezone.utc)


def _iso(d: datetime) -> str:
    return _utc(d).strftime('%Y-%m-%dT%H:%M:%SZ')


def _tijd(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- ophalen (Autotask)
_TV = ['id', 'ticketNumber', 'title', 'status', 'priority', 'queueID', 'issueType', 'source', 'createDate', 'completedDate',
       'firstResponseDateTime', 'assignedResourceID', 'contactID', 'lastActivityDate']


def _blokken(at, entiteit: str, veld: str, ids, extra: list, velden: list, n: int = 200) -> list[dict]:
    ids = [i for i in dict.fromkeys(ids) if i is not None]
    uit = []
    for i in range(0, len(ids), n):
        uit += at.query(entiteit, [{'op': 'in', 'field': veld, 'value': ids[i:i + n]}] + extra, velden, 20000, 20000)
    return uit


def ophalen(company: int, van: datetime, tot: datetime) -> dict:
    """Ruwe gegevens van één bedrijf vanaf `van` (begin vorig kwartaal) tot nu. Los te vervangen in de testmodus."""
    from . import h_autotask as A
    at = A._at()
    inst = A._instellingen()
    iso = _iso(van)
    bedrijf = [{'op': 'eq', 'field': 'companyID', 'value': company}]
    klaar = A._klaar(at, 'Tickets') | ({inst['statusKlaar']} if inst.get('statusKlaar') else set())
    tickets: dict = {}
    for f in ([{'op': 'gte', 'field': 'createDate', 'value': iso}], [{'op': 'gte', 'field': 'completedDate', 'value': iso}],
              [{'op': 'noteq', 'field': 'status', 'value': w} for w in klaar], [{'op': 'gte', 'field': 'lastActivityDate', 'value': iso}]):
        for t in at.query('Tickets', bedrijf + f, _TV, 10000, 10000):
            tickets[t['id']] = t
    tv = ['id', 'ticketID', 'taskID', 'resourceID', 'hoursWorked', 'isNonBillable', 'dateWorked']
    datum = [{'op': 'gte', 'field': 'dateWorked', 'value': iso}]
    tijd = _blokken(at, 'TimeEntries', 'ticketID', list(tickets), datum, tv)
    projecten = at.query('Projects', bedrijf, ['id', 'projectName', 'status'], 2000, 2000)
    taken = _blokken(at, 'Tasks', 'projectID', [p['id'] for p in projecten], [], ['id', 'projectID', 'title'])
    tijd += _blokken(at, 'TimeEntries', 'taskID', [t['id'] for t in taken], datum, tv)
    mensen = {r['id']: f"{r.get('firstName') or ''} {r.get('lastName') or ''}".strip() for r in
              _blokken(at, 'Resources', 'id', {x.get('resourceID') for x in tijd} | {t.get('assignedResourceID') for t in tickets.values()}, [],
                       ['id', 'firstName', 'lastName'])}
    contacten = {r['id']: f"{r.get('firstName') or ''} {r.get('lastName') or ''}".strip() for r in
                 _blokken(at, 'Contacts', 'id', {t.get('contactID') for t in tickets.values()}, [], ['id', 'firstName', 'lastName'])}
    naam = (at.req('GET', f'Companies/{company}').get('item') or {}).get('companyName') or ''
    pl = at.picklists('Tickets')
    lab = lambda veld: {str(p['value']): p['label'] for p in pl.get(veld, [])}  # noqa: E731
    return {'name': naam, 'tickets': list(tickets.values()), 'time': tijd, 'projects': {p['id']: p.get('projectName') or '' for p in projecten},
            'tasks': {t['id']: t.get('projectID') for t in taken}, 'resources': mensen, 'contacts': contacten, 'done': sorted(klaar),
            'labels': {'priority': lab('priority'), 'queueID': lab('queueID'), 'issueType': lab('issueType'), 'source': lab('source'), 'status': lab('status')}}


# ---------------------------------------------------------------- cijfers (los van Autotask, ook in de testmodus)
def _uren_tekst(h: float | None) -> str:
    """Duur in gewone taal: 'binnen 45 minuten', '3,5 uur', '2 dagen'."""
    if h is None:
        return '-'
    if h < 1:
        return f'{max(1, round(h * 60))} minuten'
    if h < 24:
        return f"{_nl(h, 1 if h < 10 and h % 1 else 0)} uur"
    d = h / 24
    return f"{_nl(d, 1 if d < 10 and d % 1 else 0)} {'dag' if round(d, 1) == 1 else 'dagen'}"


def _nl(n, dec: int = 0) -> str:
    if n is None:
        return '-'
    s = f'{n:,.{dec}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def _tel(rijen, sleutel, labels=None, leeg='Overig') -> list[dict]:
    t: dict = {}
    for r in rijen:
        w = sleutel(r)
        naam = (labels or {}).get(str(w), w) if w not in (None, '') else leeg
        t[naam or leeg] = t.get(naam or leeg, 0) + 1
    return sorted(({'label': k, 'count': v} for k, v in t.items()), key=lambda x: -x['count'])


def cijfers(raw: dict, kw: dict) -> dict:
    van, tot = _utc(kw['van']), _utc(kw['tot'])
    vk = _vorig(kw)
    vvan = _utc(vk['van'])
    nu = datetime.now(timezone.utc)
    lab = raw['labels']
    klaar = set(raw['done'])
    T = raw['tickets']
    inq = lambda d, a=van, b=tot: d is not None and a <= d < b  # noqa: E731
    nieuw = [t for t in T if inq(_tijd(t.get('createDate')))]
    opgelost = [t for t in T if inq(_tijd(t.get('completedDate')))]
    v_nieuw = [t for t in T if inq(_tijd(t.get('createDate')), vvan, van)]
    v_opgelost = [t for t in T if inq(_tijd(t.get('completedDate')), vvan, van)]
    # Open: aan het eind van het kwartaal (of nu, bij het lopende kwartaal) nog niet afgerond
    eind = min(tot, nu)
    open_ = [t for t in T if (c := _tijd(t.get('createDate'))) and c < eind and
             not ((d := _tijd(t.get('completedDate'))) and d < eind) and (t.get('status') not in klaar or _tijd(t.get('completedDate')))]
    duur = [(_tijd(t['completedDate']) - _tijd(t['createDate'])).total_seconds() / 3600 for t in opgelost if _tijd(t.get('createDate'))]
    duur = [d for d in duur if d >= 0]
    reactie = [(_tijd(t['firstResponseDateTime']) - _tijd(t['createDate'])).total_seconds() / 3600 for t in nieuw
               if _tijd(t.get('firstResponseDateTime')) and _tijd(t.get('createDate'))]
    reactie = [d for d in reactie if d >= 0]

    def uren_in(a, b):
        return [x for x in raw['time'] if inq(_tijd(x.get('dateWorked')), a, b)]
    tijd, v_tijd = uren_in(van, tot), uren_in(vvan, van)
    h = lambda xs: round(sum(float(x.get('hoursWorked') or 0) for x in xs), 1)  # noqa: E731
    per_ticket: dict = {}
    for x in tijd:
        if x.get('ticketID'):
            per_ticket[x['ticketID']] = per_ticket.get(x['ticketID'], 0) + float(x.get('hoursWorked') or 0)

    # Per maand
    maanden = []
    for i in range(3):
        a = _utc(datetime(kw['van'].year, kw['van'].month + i, 1))
        b = _utc(datetime(kw['van'].year + (kw['van'].month + i == 12), 1 if kw['van'].month + i == 12 else kw['van'].month + i + 1, 1))
        maanden.append({'label': kw['months'][i], 'created': sum(1 for t in nieuw if inq(_tijd(t.get('createDate')), a, b)),
                        'completed': sum(1 for t in opgelost if inq(_tijd(t.get('completedDate')), a, b)), 'hours': h(uren_in(a, b))})
    weekdag = [0] * 7
    for t in nieuw:
        weekdag[_tijd(t['createDate']).astimezone().weekday()] += 1

    # Per medewerker: opgeloste tickets (toegewezen) en uren
    pm: dict = {}
    for x in tijd:
        r = pm.setdefault(x.get('resourceID'), {'name': raw['resources'].get(x.get('resourceID')) or 'Collega', 'tickets': 0, 'hours': 0.0})
        r['hours'] += float(x.get('hoursWorked') or 0)
    for t in opgelost:
        if t.get('assignedResourceID'):
            pm.setdefault(t['assignedResourceID'], {'name': raw['resources'].get(t['assignedResourceID']) or 'Collega', 'tickets': 0, 'hours': 0.0})['tickets'] += 1
    medewerkers = sorted(({**r, 'hours': round(r['hours'], 1)} for r in pm.values()), key=lambda r: (-r['tickets'], -r['hours']))
    contacten = _tel(nieuw, lambda t: raw['contacts'].get(t.get('contactID')) if t.get('contactID') else None, leeg='Geen contactpersoon')
    soorten = _tel(nieuw, lambda t: t.get('issueType'), lab['issueType'], 'Algemeen')
    bronnen = _tel(nieuw, lambda t: t.get('source'), lab['source'], 'Onbekend')
    prio = _tel(nieuw, lambda t: t.get('priority'), lab['priority'], 'Normaal')
    projecten: dict = {}
    for x in tijd:
        if x.get('taskID'):
            p = raw['projects'].get(raw['tasks'].get(x['taskID'])) or 'Project'
            projecten[p] = projecten.get(p, 0) + float(x.get('hoursWorked') or 0)

    dag = lambda v: (_tijd(v).astimezone().strftime('%d-%m-%Y') if _tijd(v) else '')  # noqa: E731
    lijst_opgelost = [{'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'created': dag(t.get('createDate')), 'completed': dag(t.get('completedDate')),
                       'by': raw['resources'].get(t.get('assignedResourceID')) or '', 'contact': raw['contacts'].get(t.get('contactID')) or '',
                       'hours': round(per_ticket.get(t['id'], 0), 1)} for t in sorted(opgelost, key=lambda t: t.get('completedDate') or '')]
    lijst_open = [{'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'created': dag(t.get('createDate')),
                   'status': lab['status'].get(str(t.get('status')), ''), 'by': raw['resources'].get(t.get('assignedResourceID')) or '',
                   'age': (eind - _tijd(t['createDate'])).days} for t in sorted(open_, key=lambda t: t.get('createDate') or '')]
    med = lambda xs: round(statistics.median(xs), 2) if xs else None  # noqa: E731
    k = {'created': len(nieuw), 'completed': len(opgelost), 'open': len(open_), 'openOld': sum(1 for t in lijst_open if t['age'] > 30),
         'hours': h(tijd), 'ticketHours': h([x for x in tijd if x.get('ticketID')]), 'projectHours': h([x for x in tijd if x.get('taskID')]),
         'leadMedian': med(duur), 'within1': round(sum(1 for d in duur if d <= 24) * 100 / len(duur)) if duur else None,
         'within4': round(sum(1 for d in duur if d <= 4) * 100 / len(duur)) if duur else None,
         'firstResponse': med(reactie), 'contacts': len([c for c in contacten if c['label'] != 'Geen contactpersoon']),
         'employees': len([m for m in medewerkers if m['hours'] or m['tickets']])}
    vorige = {'label': vk['label'], 'short': vk['short'], 'created': len(v_nieuw), 'completed': len(v_opgelost), 'hours': h(v_tijd)}
    emmers = [('Binnen 4 uur', 4), ('Binnen een dag', 24), ('1 tot 3 dagen', 72), ('3 tot 7 dagen', 168), ('Langer dan een week', 1e12)]
    snelheid, ondergrens = [], -1.0
    for label, grens in emmers:
        snelheid.append({'label': label, 'count': sum(1 for d in duur if ondergrens < d <= grens)})
        ondergrens = grens
    return {'kpi': k, 'prev': vorige, 'months': maanden, 'speed': snelheid, 'weekdays': [{'label': DAGEN[i], 'count': weekdag[i]} for i in range(7)],
            'employees': medewerkers, 'contacts': contacten, 'types': soorten, 'sources': bronnen, 'priorities': prio,
            'projects': sorted(({'label': k_, 'hours': round(v, 1)} for k_, v in projecten.items()), key=lambda x: -x['hours']),
            'resolved': lijst_opgelost, 'openList': lijst_open}


# ---------------------------------------------------------------- overige onderdelen (bestaande overzichten, op naam gekoppeld)
_RUIS = r'\b(b\.?v\.?|n\.?v\.?|v\.?o\.?f\.?|holding|groep|group|stichting|vereniging|de|het|en|&)\b'


def _sleutel(naam: str) -> str:
    return re.sub(r'[^a-z0-9]', '', re.sub(_RUIS, ' ', str(naam or '').lower()))


def _zelfde(a: str, b: str) -> bool:
    x, y = _sleutel(a), _sleutel(b)
    return bool(x and y) and (x == y or (min(len(x), len(y)) >= 5 and (x in y or y in x)))


def _extra(c: Ctx, company: int, naam: str) -> dict:
    uit: dict = {'backup': None, 'email': None, 'm365': None}
    try:
        bk = API['bk.overzicht'](c, {})
        k = next((k for k in bk.get('customers') or [] if _zelfde(k['name'], naam)), None) if bk.get('configured') else None
        if k:
            n = k['counts']
            beoordeeld = n.get('ok', 0) + n.get('warn', 0) + n.get('err', 0)
            uit['backup'] = {'status': k['status'], 'ok': n.get('ok', 0), 'warn': n.get('warn', 0), 'err': n.get('err', 0), 'total': len(k['items']),
                             'pct': round(n.get('ok', 0) * 100 / beoordeeld, 1) if beoordeeld else None, 'sources': k['sources'],
                             'items': [{'name': it['name'], 'source': it['source'], 'status': it['status']} for it in k['items']][:30]}
    except Exception as e:  # noqa: BLE001
        log.info('Klantrapport back-up: %s', str(e)[:200])
    try:
        em = API['dm.overzicht'](c, {'days': 90})
        o = next((o for o in em.get('orgs') or [] if _zelfde(o['name'], naam)), None) if em.get('configured') else None
        if o:
            uit['email'] = {'status': o['status'], 'volume': o.get('volume') or 0, 'passed': o.get('passed') or 0, 'failed': o.get('failed') or 0,
                            'pct': o.get('compliance'), 'domains': [{'domain': d['domain'], 'policy': d['policy'], 'status': d['status']} for d in o['domains']]}
    except Exception as e:  # noqa: BLE001
        log.info('Klantrapport e-mail: %s', str(e)[:200])
    try:
        from . import h_autotask as A
        tids = {tid for tid, v in A._klanten().items() if int(v.get('companyId') or 0) == int(company)}
        adm = API['adm.status'](c, {})
        k = next((k for k in adm.get('klanten') or [] if k.get('ok') and (k['id'] in tids or _zelfde(k.get('name') or '', naam))), None)
        if k:
            uit['m365'] = {'bought': k.get('bought') or 0, 'assigned': k.get('assigned') or 0, 'free': k.get('free') or 0, 'saving': k.get('saving') or 0,
                           'skus': [{'name': x['name'], 'bought': x['bought'], 'assigned': x['assigned']} for x in k.get('skus') or [] if x.get('paid')][:12]}
    except Exception as e:  # noqa: BLE001
        log.info('Klantrapport Microsoft 365: %s', str(e)[:200])
    return uit


# ---------------------------------------------------------------- samenvatting in gewone taal
def _verschil(nu: int | float, toen: int | float, eenheid: str) -> str:
    if not toen:
        return ''
    d = nu - toen
    if abs(d) < max(1, toen * 0.05):
        return ' Dat is ongeveer evenveel als het kwartaal ervoor.'
    return f" Dat is {_nl(abs(d), 1 if isinstance(d, float) and d % 1 else 0)} {eenheid} {'meer' if d > 0 else 'minder'} dan het kwartaal ervoor."


def samenvatting(d: dict) -> list[str]:
    k, v = d['kpi'], d['prev']
    z = []
    if not k['created'] and not k['completed'] and not k['hours']:
        return ['In dit kwartaal zijn er geen vragen of meldingen binnengekomen en hebben wij geen uren voor u geregistreerd.']
    z.append(f"Dit kwartaal kregen wij {_nl(k['created'])} {'vraag of melding' if k['created'] == 1 else 'vragen en meldingen'} van u binnen."
             + _verschil(k['created'], v['created'], 'vragen'))
    z.append(f"Wij hebben er {_nl(k['completed'])} opgelost." + (f" Aan het einde van het kwartaal stonden er nog {_nl(k['open'])} open." if k['open'] else ' Er stond niets meer open.'))
    if k['leadMedian'] is not None:
        z.append(f"De helft van de vragen was binnen {_uren_tekst(k['leadMedian'])} helemaal opgelost."
                 + (f" {k['within1']} van de 100 vragen waren binnen een dag klaar." if k['within1'] is not None else ''))
    if k['firstResponse'] is not None:
        z.append(f"Na uw melding kreeg u meestal binnen {_uren_tekst(k['firstResponse'])} een eerste reactie van ons.")
    if k['hours']:
        z.append(f"Wij hebben in totaal {_nl(k['hours'], 1 if k['hours'] % 1 else 0)} uur voor u gewerkt" + (f", waarvan {_nl(k['projectHours'], 1 if k['projectHours'] % 1 else 0)} uur aan projecten." if k['projectHours'] else '.')
                 + _verschil(k['hours'], v['hours'], 'uur'))
    if d['types'] and d['types'][0]['label'] not in ('Algemeen', 'Overig'):
        z.append(f"De meeste vragen gingen over: {d['types'][0]['label'].lower()}.")
    if d['employees']:
        namen = [m['name'] for m in d['employees'][:3] if m['tickets'] or m['hours']]
        if namen:
            z.append(f"U bent vooral geholpen door {', '.join(namen[:-1]) + ' en ' + namen[-1] if len(namen) > 1 else namen[0]}.")
    bk, em = d['extra'].get('backup'), d['extra'].get('email')
    if bk and bk['pct'] is not None:
        z.append(f"Back-ups: {_nl(bk['pct'], 0)} van de 100 back-ups zijn goed gelukt." + (' Waar iets misging, hebben wij dat opgepakt.' if bk['err'] else ''))
    if em and em['pct'] is not None:
        z.append(f"E-mail: {_nl(em['pct'], 0)} van de 100 e-mails die namens u zijn verstuurd, waren echt van u en goed beveiligd.")
    return z


def klant_rapport(c: Ctx, company: int, sleutel: str, vers: bool = False) -> dict:
    kw = _uit_sleutel(sleutel)
    s = (int(company), kw['key'])
    with _lock:
        item = _CACHE.get(s)
    if item and not vers and time.time() - item[0] < VERS:
        d = item[1]
    else:
        begin = time.time()
        raw = ophalen(int(company), _vorig(kw)['van'], kw['tot'])
        d = {'company': {'id': int(company), 'name': raw['name'] or f'Bedrijf {company}'}, **cijfers(raw, kw)}
        log.info('Klantrapport Autotask: %.1f s', time.time() - begin)
        with _lock:
            _CACHE[s] = (time.time(), d)
    d = {**d, 'quarter': {x: y for x, y in kw.items() if x not in ('van', 'tot')}, 'current': kw['tot'] > datetime.now(),
         'at': datetime.now().strftime('%d-%m-%Y %H:%M'), 'extra': _extra(c, company, d['company']['name'])}
    d['summary'] = samenvatting(d)
    return d


# ---------------------------------------------------------------- API
@api('mg.kwartalen')
def mg_kwartalen(c: Ctx, b: dict) -> dict:
    """Kwartalen om uit te kiezen en de klanten die aan een Autotask-bedrijf gekoppeld zijn (of zoeken op naam)."""
    from . import h_autotask as A
    if not A._sleutel():
        return {'configured': False, 'quarters': kwartalen(), 'companies': []}
    q = str(b.get('q') or '').strip()
    if q:
        at = A._at()
        r = at.query('Companies', [{'op': 'contains', 'field': 'companyName', 'value': q}, {'op': 'eq', 'field': 'isActive', 'value': True}],
                     ['id', 'companyName'], 25)
        bedrijven = [{'id': x['id'], 'name': x.get('companyName') or ''} for x in r]
    else:
        gezien: dict = {}
        for v in A._klanten().values():
            if v.get('companyId') is not None:
                gezien.setdefault(int(v['companyId']), {'id': int(v['companyId']), 'name': v.get('name') or v.get('tenant') or f"Bedrijf {v['companyId']}"})
        bedrijven = sorted(gezien.values(), key=lambda x: x['name'].lower())
    return {'configured': True, 'quarters': kwartalen(), 'companies': bedrijven}


@api('mg.klant')
def mg_klant(c: Ctx, b: dict) -> dict:
    if not b.get('companyId'):
        raise ApiFout('Kies eerst een klant.')
    return klant_rapport(c, int(b['companyId']), str(b.get('quarter') or ''), bool(b.get('fresh')))


@api('mg.klant.pdf')
def mg_klant_pdf(c: Ctx, b: dict) -> dict:
    from pathlib import Path
    from .h_klantrapport_pdf import maak_pdf
    from .h_rapport import _openen
    if not b.get('companyId'):
        raise ApiFout('Kies eerst een klant.')
    d = klant_rapport(c, int(b['companyId']), str(b.get('quarter') or ''))
    d['options'] = {'tickets': b.get('tickets', True) is not False, 'employees': b.get('employees', True) is not False}
    map_ = Path.home() / 'Downloads'
    if not map_.is_dir():
        map_ = Path.home()
    naam = re.sub(r'[^\w\- ]+', '', d['company']['name']).strip().replace(' ', '-')[:60] or 'Klant'
    basis = f"Kwartaalrapportage-{naam}-{d['quarter']['short'].replace(' ', '-')}"
    pad, n = map_ / f'{basis}.pdf', 2
    while pad.exists():
        pad, n = map_ / f'{basis}-{n}.pdf', n + 1
    pad.write_bytes(maak_pdf(d, (c.staat.beheerder or {}).get('name') or ''))
    c.L(f'Kwartaalrapportage opgeslagen: {pad}')
    _openen(pad)
    return {'path': str(pad)}
