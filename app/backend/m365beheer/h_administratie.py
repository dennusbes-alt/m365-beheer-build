"""Administratie: per klant welke licenties er zijn ingekocht en wat daarvan echt wordt gebruikt.

Bedoeld voor de maandelijkse controle (bijv. tegen de Pax8-factuur): wat kan er af of worden opgezegd?
Per klant (alleen lezen, via GDAP):
- /subscribedSkus             ingekocht (prepaidUnits) en toegewezen (consumedUnits)
- /directory/subscriptions    abonnementen met volgende verlengdatum, proefversie en status
- /users (met licentie)       laatste aanmelding (signInActivity, vraagt Entra ID P1) en of het account aan staat

Alles wordt alleen in het geheugen bewaard (zoals de rest van de app) en verdwijnt bij afsluiten.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import lokaal
from .auth import KoppelingNodig, LoginFout
from .clients import ApiFout, Graph, parallel, achtergrond_fn
from .context import Ctx, api
from .skus import sku_info

log = logging.getLogger('m365beheer')
ACTIEF_DAGEN = 30
INACTIEF_DAGEN = 90
GELIJKTIJDIG = 4

_KLUS: dict = {'bezig': False, 'totaal': 0, 'klaar': 0, 'begin': '', 'eind': '', 'klanten': {}}
_lock = threading.Lock()


def _datum(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None


def _gebruikers(g: Graph) -> tuple[list[dict], bool]:
    """Gebruikers met een licentie, met laatste aanmelding als dat kan (Entra ID P1). Geeft (lijst, aanmelddata_beschikbaar)."""
    basis = ('/users?$filter=assignedLicenses/$count ne 0&$count=true&$top=999'
             '&$select=id,displayName,userPrincipalName,accountEnabled,assignedLicenses,userType,createdDateTime')
    try:
        return g.all(basis + ',signInActivity'), True
    except ApiFout as e:
        if e.status not in (400, 403):
            raise
        return g.all(basis), False   # geen P1 of geen rechten op aanmeldgegevens: dan zonder


def klant_overzicht(auth, tid: str, naam: str) -> dict:
    g = Graph(lambda: auth.token(tid, 'graph', interactief=False))
    auth.token(tid, 'graph', interactief=False)   # eerst het token: zo komt 'koppeling nodig' als die fout door (niet ingepakt)
    r = parallel({'skus': lambda: g.all('/subscribedSkus'),
                  'subs': lambda: g.all('/directory/subscriptions'),
                  'users': lambda: _gebruikers(g)})
    if isinstance(r['skus'], Exception):
        raise r['skus']
    nu = datetime.now(timezone.utc)
    subs = r['subs'] if isinstance(r['subs'], list) else []
    users, aanmeld = r['users'] if not isinstance(r['users'], Exception) else ([], False)
    # Per gebruiker het gebruik bepalen
    per_sku: dict[str, list[dict]] = {}
    for u in users:
        sa = u.get('signInActivity') or {}
        data = [d for d in (_datum(sa.get(k)) for k in ('lastSignInDateTime', 'lastNonInteractiveSignInDateTime', 'lastSuccessfulSignInDateTime')) if d]
        laatst = max(data) if data else None
        dagen = (nu - laatst).days if laatst else None
        aangemaakt = _datum(u.get('createdDateTime'))
        nieuw = bool(aangemaakt and (nu - aangemaakt).days < ACTIEF_DAGEN)
        if u.get('accountEnabled') is False:
            gebruik = 'uit'
        elif not aanmeld:
            gebruik = 'onbekend'
        elif dagen is not None and dagen <= ACTIEF_DAGEN:
            gebruik = 'actief'
        elif nieuw:
            gebruik = 'nieuw'          # net aangemaakt: nog niet als ongebruikt tellen
        elif dagen is not None and dagen <= INACTIEF_DAGEN:
            gebruik = 'inactief'       # 30 tot 90 dagen niet aangemeld
        else:
            gebruik = 'ongebruikt'     # meer dan 90 dagen niet (of nooit) aangemeld
        item = {'name': u.get('displayName') or '', 'upn': u.get('userPrincipalName') or '', 'use': gebruik,
                'last': laatst.isoformat() if laatst else '', 'days': dagen, 'guest': u.get('userType') == 'Guest'}
        for lic in u.get('assignedLicenses') or []:
            per_sku.setdefault(lic.get('skuId'), []).append(item)
    lijst = []
    for s in r['skus']:
        part = s.get('skuPartNumber') or ''
        pre = s.get('prepaidUnits') or {}
        ingekocht = int(pre.get('enabled') or 0)
        info = sku_info(part, ingekocht)
        mijn_subs = [x for x in subs if x.get('skuId') == s.get('skuId')]
        verleng = sorted(d for d in (_datum(x.get('nextLifecycleDateTime')) for x in mijn_subs if x.get('status') in ('Enabled', 'Warning')) if d)
        wie = per_sku.get(s.get('skuId'), [])
        tel = {k: sum(1 for w in wie if w['use'] == k) for k in ('actief', 'nieuw', 'inactief', 'ongebruikt', 'uit', 'onbekend')}
        toegewezen = int(s.get('consumedUnits') or 0)
        vrij = max(0, ingekocht - toegewezen)
        lijst.append({
            'sku': s.get('skuId'), 'part': part, 'name': info['name'], 'paid': info['kind'] == 'betaald',
            'bought': ingekocht, 'assigned': toegewezen, 'free': vrij, 'short': max(0, toegewezen - ingekocht),
            'suspended': int(pre.get('suspended') or 0), 'warning': int(pre.get('warning') or 0),
            'status': s.get('capabilityStatus') or '', **tel,
            'saving': vrij + tel['uit'] + tel['ongebruikt'],
            'renew': verleng[0].isoformat() if verleng else '',
            'trial': any(x.get('isTrial') for x in mijn_subs), 'subs': len(mijn_subs),
            'users': sorted(wie, key=lambda w: (['uit', 'ongebruikt', 'inactief', 'onbekend', 'nieuw', 'actief'].index(w['use']), w['name'].lower())),
        })
    lijst.sort(key=lambda x: (not x['paid'], -x['bought'], x['name'].lower()))
    betaald = [x for x in lijst if x['paid']]
    som = lambda k: sum(x[k] for x in betaald)  # noqa: E731
    verlengingen = sorted(x['renew'] for x in betaald if x['renew'])
    return {'id': tid, 'name': naam, 'ok': True, 'signins': aanmeld, 'skus': lijst,
            'bought': som('bought'), 'assigned': som('assigned'), 'free': som('free'), 'short': som('short'),
            'disabled': som('uit'), 'unused': som('ongebruikt'), 'inactive': som('inactief'), 'saving': som('saving'),
            'warnings': sum(1 for x in betaald if x['status'] in ('Warning', 'Suspended', 'LockedOut') or x['warning'] or x['suspended']),
            'trials': sum(1 for x in lijst if x['trial']), 'renew': verlengingen[0] if verlengingen else '',
            'at': datetime.now().strftime('%Y-%m-%d %H:%M')}


def _fout(e: Exception) -> tuple[str, str]:
    """(soort, uitleg). Soort 'koppeling' kan de app zelf oplossen (GDAP-toewijzing en koppeling regelen)."""
    t = str(e)
    if isinstance(e, KoppelingNodig) or any(c in t for c in ('AADSTS65001', 'AADSTS90099', 'AADSTS650052', 'AADSTS700016', 'AADSTS90094', 'AADSTS500011')):
        return 'koppeling', 'De app is bij deze klant nog niet gekoppeld. Klik op Koppeling regelen; de app doet het zelf.'
    if 'AADSTS50079' in t or 'AADSTS50076' in t:
        return 'mfa', 'Deze klant vraagt om extra verificatie (MFA) voor je account. Open de klant om je aan te melden.'
    if 'geen toegang tot deze klant' in t.lower() or (isinstance(e, ApiFout) and e.status in (401, 403)):
        return 'gdap', ('Geen rechten om licenties te lezen. Klik op Koppeling regelen of open de klant: de app regelt dan de GDAP-toewijzing '
                        '(nodig: bijv. License Administrator of Global Reader).')
    if isinstance(e, LoginFout):
        return 'overig', 'Geen toegang (opnieuw inloggen nodig).'
    return 'overig', t[:300]


def _koppelen(s, tid: str) -> None:
    """Zelfde als bij het openen van een klant: GDAP-toewijzing (AdminAgents) en app-koppeling regelen. Nooit een browserlogin."""
    from .gdap import GdapInfo, toegang_regelen
    from .koppeling import koppelen
    a = s.auth
    try:
        a.token(tid, 'graph', interactief=False)
        return
    except KoppelingNodig:
        pass
    info = GdapInfo(Graph(lambda: a.token(a.home_tenant, 'partner')))
    nieuw = toegang_regelen(info, tid)
    eind = time.time() + (240 if nieuw else 120)
    while True:
        try:
            koppelen(a, tid)
            return
        except ApiFout as e:
            if not nieuw or time.time() + 15 > eind or e.status not in (400, 403):
                raise
            time.sleep(15)


@api('adm.start')
def adm_start(c: Ctx, b: dict) -> dict:
    """Licentieoverzicht ophalen voor alle klanten met toegang (of de opgegeven klanten), op de achtergrond."""
    s = c.staat
    # Klantenlijst: die van de app, of (net na het starten, als de actuele lijst nog wordt opgehaald) die van het scherm
    bron = s.klanten or [k for k in (b.get('customers') or []) if isinstance(k, dict) and k.get('id')]
    if not bron and s.klanten_taak is not None:
        try:
            s.klanten_taak.result(timeout=90)
        except Exception:  # noqa: BLE001
            pass
        bron = s.klanten or []
    # Alle klanten, ook zonder (volledige) GDAP-toegang: dan staat de reden in het overzicht
    alle = [{'id': k['id'], 'name': k.get('name') or k['id'], 'own': bool(k.get('own'))} for k in bron]
    ids = set(b.get('ids') or [])
    koppel = bool(b.get('koppel'))   # eerst de koppeling regelen (voor klanten met 'koppeling nodig' of 'geen rechten')
    doel = [k for k in alle if not ids or k['id'] in ids]
    with _lock:
        if _KLUS['bezig']:
            return _status()
        _KLUS.update(bezig=True, totaal=len(doel), klaar=0, begin=datetime.now().strftime('%Y-%m-%d %H:%M'), eind='')
        if not ids:
            _KLUS['klanten'] = {}
        for k in doel:   # direct zichtbaar als regel; wordt per klant gevuld zodra de gegevens binnen zijn
            _KLUS['klanten'][k['id']] = {'id': k['id'], 'name': k['name'], 'own': k['own'], 'ok': None, 'loading': True}
    # Eigen tenant en de klanten waar je het laatst werkte eerst, dan de rest
    recent = (lokaal.lees('voorkeuren.json', {}) or {}).get('recent', [])
    doel.sort(key=lambda k: (not k['own'], recent.index(k['id']) if k['id'] in recent else 999, k['name'].lower()))

    def een(k: dict) -> None:
        try:
            if koppel:
                with _lock:
                    _KLUS['klanten'][k['id']]['step'] = 'Koppeling regelen (GDAP-toewijzing en app, kan 1 tot 3 minuten duren)...'
                _koppelen(s, k['id'])
            uit = klant_overzicht(s.auth, k['id'], k['name'])
        except Exception as e:  # noqa: BLE001 - per klant melden, de rest gaat door
            log.info('Administratie %s: %s', k['name'], e)
            soort, tekst = _fout(e)
            uit = {'id': k['id'], 'name': k['name'], 'ok': False, 'error': tekst, 'errorKind': soort, 'at': datetime.now().strftime('%Y-%m-%d %H:%M')}
        uit['own'] = bool(k.get('own'))
        with _lock:
            _KLUS['klanten'][k['id']] = uit
            _KLUS['klaar'] += 1

    def alles() -> None:
        begin = time.time()
        try:
            with ThreadPoolExecutor(max_workers=3 if koppel else GELIJKTIJDIG, thread_name_prefix='adm') as ex:
                list(ex.map(achtergrond_fn(een), doel))
        finally:
            with _lock:
                _KLUS['bezig'] = False
                _KLUS['eind'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            log.info('Administratie: %d klanten in %.0f s', len(doel), time.time() - begin)
    threading.Thread(target=alles, daemon=True, name='administratie').start()
    return _status()


def _status() -> dict:
    with _lock:
        return {'bezig': _KLUS['bezig'], 'totaal': _KLUS['totaal'], 'klaar': _KLUS['klaar'], 'begin': _KLUS['begin'],
                'eind': _KLUS['eind'], 'klanten': sorted(_KLUS['klanten'].values(), key=lambda k: (not k.get('own'), k['name'].lower()))}


@api('adm.status')
def adm_status(c: Ctx, b: dict) -> dict:
    return _status()
