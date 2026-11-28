"""IT Glue (EU): kennis raadplegen en oplossingen vastleggen voor de servicedesk.

- Koppeling: één API-sleutel (IT Glue > Account > Settings > API Keys), gedeeld via de verborgen SharePoint-lijst van
  Justdata. Instellen, wijzigen en verwijderen mag alleen de app-beheerder.
- Kennis: alle flexibele assets van 'kennistypes' (naam bevat bijv. werkinstructie, procedure, kennis, oplossing, how-to,
  knowledge, handleiding) plus ons eigen type 'Werkinstructie (M365 beheer)'. Index 20 minuten in het geheugen;
  zoeken = woorden uit het ticket vergelijken met titel en inhoud (zeldzame woorden tellen zwaarder).
- Vastleggen: een werkinstructie (titel, vraag/probleem, oplossing, ticket, trefwoorden) bij de juiste IT Glue-organisatie
  (op naam gekoppeld aan het Autotask-bedrijf). Het eigen type wordt bij het eerste gebruik aangemaakt.
"""
from __future__ import annotations

import html
import logging
import math
import re
import threading
import time

import requests

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import eis_beheerder, is_beheerder

log = logging.getLogger('m365beheer')

BASIS = 'https://api.eu.itglue.com'
EIGEN_TYPE = 'Werkinstructie (M365 beheer)'
KENNIS = re.compile(r'werkinstructie|procedure|kennis|oplossing|how.?to|knowledge|handleiding|instructie|kb\b|runbook|faq', re.I)
STOP = set('de het een en of van voor met bij aan op in uit naar is zijn wordt werd niet geen wel ook dat die dit deze er om te tot als dan maar '
           'kan kunnen moet moeten graag hoe wat wie waar ons onze mijn jouw uw je jij we wij hij zij ze the a an and or of for with to in on is are '
           'not no can how what please hallo hoi beste groet groeten vriendelijke bedankt alvast via per nieuw nieuwe ticket melding vraag probleem '
           'werkt werken werkte doet doen gaat gaan meer heel even graag sinds vandaag gisteren morgen klant collega iemand iets alles '
           'does work working not anymore issue error fout lukt '
           # te algemeen om iets over de oplossing te zeggen (gaven valse treffers zoals 'Offboard user' bij elk gebruikersticket)
           'user users gebruiker gebruikers event account accounts new re fw fwd mail email e-mail inhoud document documenten overzicht '
           'algemeen info informatie test data update aanvraag verzoek justdata omgeving technisch ontwerp handleiding versie concept '
           'location locatie medium high low urgent spoed dringend'.split())
_S = requests.Session()
_lock = threading.Lock()
_INDEX: dict = {'t': 0.0, 'docs': [], 'df': {}, 'orgs': [], 'bezig': False}
INDEX_VERS = 1200


# ---------------------------------------------------------------- koppeling
def _sleutel() -> str | None:
    w = GEDEELD.lees('itglue')
    return w[1] if w and w[1] else None


def _req(methode: str, pad: str, params=None, body=None, sleutel: str | None = None):
    k = sleutel or _sleutel()
    if not k:
        raise ApiFout('IT Glue is nog niet gekoppeld (startscherm > Servicedesk > IT Glue, alleen de app-beheerder).')
    h = {'x-api-key': k, 'Content-Type': 'application/vnd.api+json', 'Accept': 'application/vnd.api+json'}
    url = pad if pad.startswith('http') else BASIS + pad
    for poging in range(4):
        try:
            r = _S.request(methode, url, params=params, json=body, headers=h, timeout=60)
        except requests.exceptions.RequestException as e:
            if poging == 3:
                raise ApiFout(f'IT Glue niet bereikbaar: {type(e).__name__}') from None
            time.sleep(1 + poging)
            continue
        if r.status_code == 429 and poging < 3:
            time.sleep(3 * (poging + 1))
            continue
        break
    if r.status_code in (401, 403):
        raise ApiFout('IT Glue weigert de API-sleutel (401/403). Controleer de sleutel en of die bij de EU-omgeving hoort.', r.status_code)
    if r.status_code >= 400:
        try:
            fout = '; '.join(str(x.get('detail') or x.get('title')) for x in r.json().get('errors') or [])
        except ValueError:
            fout = r.text[:200]
        raise ApiFout(f'IT Glue: {fout or r.status_code}', r.status_code)
    return r.json() if r.content else {}


def _alle(pad: str, params: dict | None = None, max_: int = 20000) -> list[dict]:
    uit, url, p = [], pad, {**(params or {}), 'page[size]': 1000}
    while url and len(uit) < max_:
        j = _req('GET', url, params=p)
        uit += j.get('data') or []
        url, p = (j.get('links') or {}).get('next'), None
    return uit


@api('ig.status')
def ig_status(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    if _sleutel() is not None:
        index_achtergrond()
    soorten: dict = {}
    for d in _INDEX['docs']:
        soorten[d['type']] = soorten.get(d['type'], 0) + 1
    return {'configured': _sleutel() is not None, 'admin': is_beheerder(c.staat), 'docs': len(_INDEX['docs']), 'loading': bool(_INDEX.get('bezig')),
            'types': sorted(({'name': k, 'count': v} for k, v in soorten.items()), key=lambda x: -x['count']),
            'at': time.strftime('%H:%M', time.localtime(_INDEX['t'])) if _INDEX['t'] else ''}


@api('ig.keys.set')
def ig_keys_set(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    k = str(b.get('key') or '').strip()
    if not k:
        raise ApiFout('Vul de API-sleutel in.')
    try:
        _req('GET', '/organizations', params={'page[size]': 1}, sleutel=k)
    except ApiFout as e:
        raise ApiFout(f'De sleutel werkt niet: {e}')
    GEDEELD.schrijf('itglue', 'eu', k)
    with _lock:
        _INDEX.update(t=0.0, docs=[], df={}, orgs=[])
    c.L("IT Glue gekoppeld (gedeeld met alle Justdata-collega's).")
    return {}


@api('ig.keys.delete')
def ig_keys_delete(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    GEDEELD.schrijf('itglue', '', None)
    with _lock:
        _INDEX.update(t=0.0, docs=[], df={}, orgs=[])
    c.L('IT Glue-koppeling verwijderd (voor iedereen).')
    return {}


# ---------------------------------------------------------------- kennisindex
def woorden(t: str) -> list[str]:
    t = html.unescape(re.sub(r'<[^>]+>', ' ', str(t or ''))).lower()
    return [w for w in re.findall(r'[a-z0-9à-ÿ][a-z0-9à-ÿ\-\.]{2,}', t) if w not in STOP and not w.isdigit()]


def _tekst(traits: dict) -> str:
    delen = []
    for v in (traits or {}).values():
        if isinstance(v, str):
            delen.append(v)
        elif isinstance(v, dict) and isinstance(v.get('values'), list):
            delen += [str(x.get('name') or '') for x in v['values'] if isinstance(x, dict)]
    return ' '.join(delen)


def ophalen_index() -> dict:
    """Alle kennisdocumenten uit IT Glue (los te vervangen in de testmodus)."""
    types = [t for t in _alle('/flexible_asset_types') if KENNIS.search(str((t.get('attributes') or {}).get('name') or ''))
             or (t.get('attributes') or {}).get('name') == EIGEN_TYPE]
    docs = []
    for t in types:
        for a in _alle('/flexible_assets', {'filter[flexible_asset_type_id]': t['id']}):
            at = a.get('attributes') or {}
            tr = at.get('traits') or {}
            titel = at.get('name') or tr.get('titel') or tr.get('name') or 'Zonder titel'
            docs.append({'id': a['id'], 'title': str(titel)[:200], 'org': at.get('organization-name') or '', 'orgId': at.get('organization-id'),
                         'type': (t.get('attributes') or {}).get('name') or '', 'url': at.get('resource-url') or '',
                         'text': html.unescape(re.sub(r'<[^>]+>', ' ', _tekst(tr)))[:6000], 'updated': (at.get('updated-at') or '')[:10]})
    orgs = [{'id': o['id'], 'name': (o.get('attributes') or {}).get('name') or ''} for o in _alle('/organizations')]

    # IT Glue Documents (de meeste kennis staat daar): per organisatie alle niet-gearchiveerde documenten, ook in mappen.
    # De lijst geeft titel en (bij oudere documenten) de inhoud; nieuwere documenten bestaan uit secties: daarvan telt de titel.
    def docs_van(o):
        try:
            return [d for d in _alle(f"/organizations/{o['id']}/relationships/documents", {'filter[document_folder_id]': 'null', 'filter[archived]': 'false'}, 5000)]
        except ApiFout as e:
            log.info('IT Glue-documenten van %s: %s', o['name'], e)
            return []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:   # IT Glue staat ongeveer 10 aanvragen per seconde toe
        for o, lijst in zip(orgs, ex.map(docs_van, orgs)):
            for d in lijst:
                at = d.get('attributes') or {}
                docs.append({'id': f"d{d['id']}", 'title': str(at.get('name') or 'Zonder titel')[:200], 'org': at.get('organization-name') or o['name'],
                             'orgId': o['id'], 'type': 'Document', 'url': at.get('resource-url') or '',
                             'text': html.unescape(re.sub(r'<[^>]+>', ' ', str(at.get('content') or '')))[:6000], 'updated': (at.get('updated-at') or '')[:10]})
    return {'docs': docs, 'orgs': orgs}


def index_achtergrond() -> bool:
    """Index op de achtergrond (op)bouwen; geeft True als er nu al een bruikbare index is. Een scherm wacht nooit op IT Glue."""
    with _lock:
        klaar = bool(_INDEX['t'])
        if (_INDEX['t'] and time.time() - _INDEX['t'] < INDEX_VERS) or _INDEX.get('bezig'):
            return klaar
        _INDEX['bezig'] = True

    def run():
        try:
            index(True)
        except Exception as e:  # noqa: BLE001
            log.info('IT Glue-index: %s', e)
        finally:
            _INDEX['bezig'] = False
    from .clients import ACHTER_POOL, achtergrond_fn
    ACHTER_POOL.submit(achtergrond_fn(run))
    return klaar


def index(vers: bool = False) -> dict:
    with _lock:
        if _INDEX['t'] and not vers and time.time() - _INDEX['t'] < INDEX_VERS:
            return _INDEX
    begin = time.time()
    r = ophalen_index()
    df: dict = {}
    for d in r['docs']:
        d['w'] = set(woorden(d['title'])) | set(woorden(d['text']))
        d['wt'] = set(woorden(d['title']))
        for w in d['w']:
            df[w] = df.get(w, 0) + 1
    with _lock:
        _INDEX.update(t=time.time(), docs=r['docs'], df=df, orgs=r['orgs'])
    log.info('IT Glue-kennisindex: %d documenten, %d organisaties in %.1f s', len(r['docs']), len(r['orgs']), time.time() - begin)
    return _INDEX


def zoeken(tekst: str, organisatie: str = '', n: int = 3, minimum: float = 6.0, onderwerp: str = '') -> list[dict]:
    """Beste kennisdocumenten bij een ticket (titel + omschrijving). Alleen documenten van de klant zelf en de interne kennis van
    Justdata: documentatie van andere klanten gaat over hun omgeving en is bij dit ticket niet bruikbaar (en hoort daar niet)."""
    if _sleutel() is None:
        return []
    if not index_achtergrond():   # nog geen index: niet wachten, de volgende keer zijn er suggesties
        return []
    ix = _INDEX
    vraag = set(woorden(tekst))
    # Het onderwerp zegt waar het ticket over gaat; een (automatische) melding bevat veel bijwoorden zoals 'backup' of
    # 'platform' die niets met het probleem te maken hebben. De titel van het document moet daarom aansluiten bij het onderwerp.
    kern = set(woorden(onderwerp)) if onderwerp else vraag
    if not vraag or not ix['docs']:
        return []
    N = len(ix['docs'])
    uit = []
    from .h_klantrapport import _zelfde
    for d in ix['docs']:
        eigen = bool(organisatie and d['org'] and _zelfde(d['org'], organisatie))
        intern = 'justdata' in str(d['org']).lower() or d['type'] == EIGEN_TYPE and not d['org']
        if not (eigen or intern):
            continue
        gedeeld = vraag & d['w']
        # Streng: minstens twee betekenisvolle woorden gemeen, waarvan minstens één in de titel van het document
        if len(gedeeld) < 2 or not gedeeld & d['wt'] & kern:
            continue
        # Een documenttitel met meerdere woorden moet voor minstens de helft in het ticket terugkomen ('Failing backup'
        # past niet bij een EDR-melding waarin toevallig 'backup' staat)
        if len(d['wt']) >= 2 and len(d['wt'] & vraag) * 2 < len(d['wt']):
            continue
        score = sum(math.log(1 + N / ix['df'].get(w, 1)) * (2.0 if w in d['wt'] else 1.0) for w in gedeeld)
        if eigen:
            score *= 1.3
        if score >= minimum:
            uit.append({'id': d['id'], 'title': d['title'], 'org': d['org'], 'type': d['type'], 'url': d['url'], 'updated': d['updated'],
                        'score': round(score, 1), 'match': sorted(gedeeld, key=lambda w: ix['df'].get(w, 1))[:6],
                        'snippet': _fragment(d['text'], gedeeld)})
    uit.sort(key=lambda x: -x['score'])
    return uit[:n]


def _fragment(t: str, ws: set) -> str:
    laag = t.lower()
    pos = min((laag.find(w) for w in ws if laag.find(w) >= 0), default=0)
    s = t[max(0, pos - 60):pos + 180].strip()
    return re.sub(r'\s+', ' ', s)[:240]


@api('ig.zoek')
def ig_zoek(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    if _sleutel() is None:
        return {'configured': False, 'results': []}
    if b.get('fresh'):
        index(True)
    return {'configured': True, 'results': zoeken(str(b.get('q') or ''), str(b.get('org') or ''), int(b.get('n') or 5), float(b.get('min') or 4.0),
                                                       str(b.get('subject') or ''))}


# ---------------------------------------------------------------- vastleggen
def _eigen_type() -> str:
    for t in _alle('/flexible_asset_types'):
        if (t.get('attributes') or {}).get('name') == EIGEN_TYPE:
            return t['id']
    velden = [('Titel', 'Text', True, True), ('Vraag of probleem', 'Textbox', False, False), ('Oplossing', 'Textbox', True, False),
              ('Ticket', 'Text', False, True), ('Trefwoorden', 'Text', False, False)]
    body = {'data': {'type': 'flexible_asset_types', 'attributes': {
        'name': EIGEN_TYPE, 'description': 'Hoe iets is ingesteld of opgelost, vastgelegd vanuit de servicedesk (Microsoft 365 beheer).',
        'icon': 'book', 'show-in-menu': True, 'enabled': True},
        'relationships': {'flexible_asset_fields': {'data': [
            {'type': 'flexible_asset_fields', 'attributes': {'order': i + 1, 'name': n, 'kind': k, 'required': req, 'show-in-list': lijst, 'use-for-title': i == 0}}
            for i, (n, k, req, lijst) in enumerate(velden)]}}}}
    r = _req('POST', '/flexible_asset_types', body=body)
    log.info('IT Glue: eigen type %s aangemaakt', EIGEN_TYPE)
    return (r.get('data') or {}).get('id')


def _organisatie(naam: str) -> dict | None:
    from .h_klantrapport import _zelfde
    orgs = _INDEX['orgs'] or [{'id': o['id'], 'name': (o.get('attributes') or {}).get('name') or ''} for o in _alle('/organizations')]
    return next((o for o in orgs if o['name'].strip().lower() == naam.strip().lower()), None) or next((o for o in orgs if _zelfde(o['name'], naam)), None)


def vastleggen(klant: str, titel: str, probleem: str, oplossing: str, ticket: str = '', trefwoorden: str = '') -> dict:
    org = _organisatie(klant) if klant else None
    if not org:
        raise ApiFout(f"Geen IT Glue-organisatie gevonden voor '{klant}'. Controleer de naam in IT Glue (moet gelijk zijn aan die in Autotask).")
    tid = _eigen_type()
    nl = lambda t: html.escape(str(t or '')).replace('\n', '<br>')  # noqa: E731
    body = {'data': {'type': 'flexible-assets', 'attributes': {'organization-id': org['id'], 'flexible-asset-type-id': tid, 'traits': {
        'titel': titel[:250], 'vraag-of-probleem': nl(probleem), 'oplossing': nl(oplossing), 'ticket': ticket[:250], 'trefwoorden': trefwoorden[:250]}}}}
    r = _req('POST', '/flexible_assets', body=body)
    d = r.get('data') or {}
    with _lock:
        if _INDEX['t']:
            _INDEX['t'] = time.time() - INDEX_VERS - 1   # verlopen maar bruikbaar: wordt op de achtergrond opnieuw opgebouwd
    return {'id': d.get('id'), 'url': (d.get('attributes') or {}).get('resource-url') or '', 'org': org['name']}


@api('ig.vastleggen')
def ig_vastleggen(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    titel, oplossing = str(b.get('title') or '').strip(), str(b.get('solution') or '').strip()
    if not titel or not oplossing:
        raise ApiFout('Vul een titel en de oplossing in.')
    r = vastleggen(str(b.get('company') or ''), titel, str(b.get('problem') or ''), oplossing, str(b.get('ticket') or ''), str(b.get('keywords') or ''))
    c.L(f"Werkinstructie '{titel}' vastgelegd in IT Glue bij {r['org']}.")
    return r


def vergeet() -> None:
    with _lock:
        _INDEX.update(t=0.0, docs=[], df={}, orgs=[])
