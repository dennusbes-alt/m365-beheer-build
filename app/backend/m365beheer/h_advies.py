"""Advies voor de servicedesk: hoe los ik dit ticket op? In begrijpelijke taal, zodat de eerste lijn zelfstandig verder kan.

Bronnen per ticket:
- IT Glue: hoe het eerder bij ons is opgelost (h_itglue).
- Microsoft Learn: de best passende Microsoft-artikelen (openbare zoek-API, geen sleutel; alleen trefwoorden uit het onderwerp).
- AI (Claude, Anthropic): een stappenplan in gewone taal, plus de vraag of de eerste lijn dit kan oppakken. Gebruikt onderwerp,
  beschrijving (zonder e-mailadressen en telefoonnummers) en de titels uit IT Glue/Learn. Sleutel gedeeld via SharePoint;
  instellen alleen de app-beheerder. Antwoorden blijven alleen in het geheugen (1 uur per ticket).
Daarnaast: triage van alle open tickets van de tweede lijn in één AI-vraag, en een tekst voor de tijdregel opstellen.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time

import requests

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import eis_beheerder, is_beheerder

log = logging.getLogger('m365beheer')

MODEL = 'claude-opus-5-5'
LEARN = 'https://learn.microsoft.com/api/search'
_S = requests.Session()
_CACHE: dict = {}
_lock = threading.Lock()
_CLIENT: dict = {}

SYSTEEM = (
    'Je bent een ervaren servicedeskcollega bij Justdata, een Nederlandse IT-dienstverlener (MSP) voor het MKB. '
    'Onze omgeving: Microsoft 365 (Exchange Online, Teams, SharePoint, OneDrive, Entra ID), Intune, Windows, Autotask, IT Glue, '
    'Datto-back-ups en netwerkapparatuur bij klanten. Je helpt een eerstelijnsmedewerker die geen specialist is.\n'
    'Schrijf in eenvoudig, duidelijk Nederlands, zonder vakjargon (of leg het kort uit). Concreet: welke knop, welk scherm, welke vraag aan de klant. '
    'Geef alleen stappen die een eerstelijnsmedewerker veilig kan uitvoeren; zeg duidelijk wanneer het naar de tweede lijn moet. '
    'Verzin geen klantgegevens. Gebruik de kennis uit IT Glue als die past: daar staat hoe het bij onze klanten is ingericht.'
)


# ---------------------------------------------------------------- sleutel (alleen de app-beheerder)
def _sleutel() -> str | None:
    w = GEDEELD.lees('anthropic')
    return w[1] if w and w[1] else None


def _client():
    import anthropic
    k = _sleutel()
    if not k:
        raise ApiFout('AI-advies is nog niet ingesteld (Servicedesk > IT Glue en instellingen, alleen de app-beheerder).')
    if _CLIENT.get('k') != k:
        _CLIENT.update(k=k, c=anthropic.Anthropic(api_key=k, max_retries=2, timeout=120.0))
    return _CLIENT['c']


# Werkt de AI echt (sleutel geldig en tegoed)? Bij geen tegoed/ongeldige sleutel 30 minuten niet meer aanbieden,
# daarna één mini-controle. Zo staat er nooit een AI-knop in beeld die niets doet.
_WERKT: dict = {'ok': None, 't': 0.0, 'reden': ''}


def beschikbaar() -> bool:
    if not _sleutel():
        return False
    if _WERKT['ok'] is False and time.time() - _WERKT['t'] < 1800:
        return False
    if _WERKT['ok'] is None or (_WERKT['ok'] is False):
        try:
            import anthropic
            _client().messages.create(model=MODEL, max_tokens=256, output_config={'effort': 'low'}, messages=[{'role': 'user', 'content': 'Antwoord alleen: OK'}])
            _WERKT.update(ok=True, t=time.time(), reden='')
        except anthropic.APIStatusError as e:
            _WERKT.update(ok=False, t=time.time(), reden=_uitleg(e))
        except Exception as e:  # noqa: BLE001 - geen verbinding: nu niet aanbieden, straks opnieuw proberen
            _WERKT.update(ok=False, t=time.time() - 1500, reden=str(e)[:200])
    return bool(_WERKT['ok'])


@api('adv.status')
def adv_status(c: Ctx, b: dict) -> dict:
    _zet_auth(c)
    return {'configured': _sleutel() is not None, 'available': beschikbaar(), 'problem': '' if _WERKT['ok'] else _WERKT['reden'],
            'admin': is_beheerder(c.staat), 'model': MODEL}


@api('adv.keys.set')
def adv_keys_set(c: Ctx, b: dict) -> dict:
    import anthropic
    eis_beheerder(c)
    _zet_auth(c)
    k = str(b.get('key') or '').strip()
    if not k.startswith('sk-ant-'):
        raise ApiFout('Dit lijkt geen Anthropic API-sleutel (begint met sk-ant-).')
    try:
        # Echte mini-vraag (fractie van een cent): zo blijkt ook direct of er tegoed op het account staat
        anthropic.Anthropic(api_key=k, max_retries=1, timeout=60.0).messages.create(
            model=MODEL, max_tokens=256, output_config={'effort': 'low'}, messages=[{'role': 'user', 'content': 'Antwoord alleen: OK'}])
    except anthropic.AuthenticationError:
        raise ApiFout('Anthropic weigert deze sleutel. Controleer of je hem volledig hebt gekopieerd.') from None
    except anthropic.APIStatusError as e:
        raise ApiFout(_uitleg(e)) from None
    except anthropic.APIError as e:
        raise ApiFout(f'De sleutel controleren lukte niet: {e}') from None
    GEDEELD.schrijf('anthropic', '', k)
    _CLIENT.clear()
    _WERKT.update(ok=True, t=time.time(), reden='')
    c.L("AI-advies (Anthropic) gekoppeld (gedeeld met alle Justdata-collega's).")
    return {}


@api('adv.keys.delete')
def adv_keys_delete(c: Ctx, b: dict) -> dict:
    eis_beheerder(c)
    _zet_auth(c)
    GEDEELD.schrijf('anthropic', '', None)
    _CLIENT.clear()
    _WERKT.update(ok=None, t=0.0, reden='')
    c.L('AI-advies (Anthropic) ontkoppeld (voor iedereen).')
    return {}


# ---------------------------------------------------------------- hulpjes
_MAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_TEL = re.compile(r'(\+?\d[\d \-]{7,}\d)')


def schoon(t: str, n: int = 3000) -> str:
    """Ticketinhoud zonder e-mailadressen en telefoonnummers (die hoeven niet naar buiten)."""
    return _TEL.sub('[telefoon]', _MAIL.sub('[e-mail]', str(t or '')))[:n]


# Producten waar de servicedesk mee werkt: alleen artikelen daarover zijn bruikbaar (geen Azure Kubernetes, ontwikkelaarsdocumentatie e.d.)
PRODUCTEN = re.compile(r'microsoft 365|office|outlook|exchange|teams|sharepoint|onedrive|entra|azure active directory|intune|windows|defender|'
                       r'word|excel|powerpoint|purview|authenticator|edge|copilot|planner|forms|power automate', re.I)
PRODUCTWOORDEN = {'outlook', 'exchange', 'teams', 'sharepoint', 'onedrive', 'entra', 'intune', 'windows', 'defender', 'word', 'excel', 'powerpoint',
                  'office', 'authenticator', 'edge', 'copilot', 'planner', 'forms', 'mfa', 'vpn', 'printer', 'wifi', 'bitlocker', 'autopilot'}


def _zoekwoorden(onderwerp: str) -> list[str]:
    """Trefwoorden zonder namen: woorden met een hoofdletter midden in de zin (Sigrid, Mortier) vallen af, behalve productnamen."""
    from .h_itglue import woorden
    t = schoon(onderwerp, 300)
    namen = {w.lower() for i, w in enumerate(re.findall(r'[A-Za-zÀ-ÿ][\w\-]*', t)) if i > 0 and w[:1].isupper() and w.lower() not in PRODUCTWOORDEN}
    return [w for w in dict.fromkeys(woorden(t)) if w not in namen and not re.search(r'\d{3,}|@', w)]


def learn(onderwerp: str, n: int = 3, extra: str = '') -> list[dict]:
    """Microsoft Learn: alleen trefwoorden (geen namen, adressen of nummers), alleen Microsoft 365/Windows/Intune-artikelen,
    en alleen artikelen die echt woorden met het ticket gemeen hebben. Liever niets dan iets onzinnigs."""
    from .h_itglue import woorden
    ws = _zoekwoorden(onderwerp)
    if extra:   # zoekvraag van de AI (als die er is): die is meestal veel preciezer
        ws = list(dict.fromkeys(_zoekwoorden(extra) + ws))
    if not ws:
        return []
    q = ' '.join(ws[:8])
    if not PRODUCTWOORDEN & set(ws):
        q += ' Microsoft 365'
    try:
        r = _S.get(LEARN, params={'search': q, 'locale': 'nl-nl', '$top': 15}, timeout=15)
        r.raise_for_status()
        uit = []
        for x in r.json().get('results') or []:
            if not x.get('url'):
                continue
            prod = ' '.join(x.get('products') or [])
            tekst = f"{x.get('title') or ''} {x.get('description') or ''}"
            if prod and not PRODUCTEN.search(prod) and not PRODUCTEN.search(x.get('title') or ''):
                continue
            if not set(ws) & set(woorden(tekst)):
                continue
            uit.append({'title': x.get('title') or '', 'url': x['url'], 'description': (x.get('description') or '')[:300], 'products': x.get('products') or []})
            if len(uit) >= n:
                break
        return uit
    except (requests.exceptions.RequestException, ValueError) as e:
        log.info('Microsoft Learn: %s', e)
        return []


def _uitleg(e) -> str:
    """Foutmelding van Anthropic in gewone taal (en de echte melding in het logboek)."""
    try:
        ms = str(((e.body or {}).get('error') or {}).get('message') or e.message)
    except Exception:  # noqa: BLE001
        ms = str(e)
    log.info('AI-advies %s: %s', getattr(e, 'status_code', '?'), ms[:400])
    laag = ms.lower()
    if 'credit balance' in laag or 'billing' in laag:
        return ('Er staat geen tegoed op het Anthropic-account. Ga naar platform.claude.com > Settings > Billing, koop tegoed (minimaal $5) '
                'en zet eventueel automatisch bijkopen met een maandlimiet aan. Daarna werkt het direct.')
    if 'workspace' in laag:
        return 'Deze API-sleutel hoort niet bij een workspace. Maak in platform.claude.com een sleutel aan binnen een workspace (bijv. "Default") en stel die opnieuw in.'
    if getattr(e, 'status_code', 0) == 404 or 'model' in laag and 'not found' in laag:
        return f'Het AI-model is niet beschikbaar voor deze sleutel ({ms[:150]}).'
    return f'AI-advies mislukt ({getattr(e, "status_code", "?")}): {ms[:200]}'


def _vraag(prompt: str, schema: dict, effort: str = 'medium', max_tokens: int = 8000) -> dict:
    """Eén vraag aan Claude met een gegarandeerd JSON-antwoord (structured output)."""
    import anthropic
    client = _client()
    try:
        r = client.beta.messages.create(
            model=MODEL, max_tokens=max_tokens, system=SYSTEEM,
            betas=['server-side-fallback-2026-07-01'], fallbacks='default',
            output_config={'effort': effort, 'format': {'type': 'json_schema', 'schema': schema}},
            messages=[{'role': 'user', 'content': prompt}])
    except anthropic.RateLimitError:
        raise ApiFout('De AI is even druk (te veel vragen). Probeer het over een minuut opnieuw.') from None
    except anthropic.AuthenticationError:
        _WERKT.update(ok=False, t=time.time(), reden='De Anthropic-sleutel werkt niet meer.')
        raise ApiFout('De Anthropic-sleutel werkt niet meer. De app-beheerder moet een nieuwe instellen.') from None
    except anthropic.APIConnectionError:
        raise ApiFout('De AI is niet bereikbaar (geen verbinding).') from None
    except anthropic.APIStatusError as e:
        uitleg = _uitleg(e)
        if e.status_code in (400, 401, 402, 403):   # geen tegoed, ongeldige sleutel of workspace: niet meer aanbieden
            _WERKT.update(ok=False, t=time.time(), reden=uitleg)
        raise ApiFout(uitleg) from None
    _WERKT.update(ok=True, t=time.time(), reden='')
    if r.stop_reason == 'refusal':
        raise ApiFout('De AI wil hier geen advies over geven.')
    tekst = next((x.text for x in r.content if x.type == 'text'), '')
    try:
        return json.loads(tekst)
    except ValueError:
        raise ApiFout('Het AI-antwoord was onvolledig. Probeer het opnieuw.') from None


ADVIES_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['samenvatting', 'eersteLijn', 'waarom', 'vragenAanKlant', 'stappen', 'controle', 'escalerenAls', 'tijdInschatting', 'uitleg'],
    'properties': {
        'samenvatting': {'type': 'string', 'description': 'Wat is er aan de hand, in één of twee zinnen gewone taal.'},
        'eersteLijn': {'type': 'boolean', 'description': 'Kan een eerstelijnsmedewerker dit veilig zelf oplossen?'},
        'waarom': {'type': 'string', 'description': 'Korte reden waarom wel/niet eerste lijn.'},
        'vragenAanKlant': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Wat je eerst aan de klant vraagt (0-4 vragen).'},
        'stappen': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Genummerde, concrete stappen in gewone taal (3-10).'},
        'controle': {'type': 'string', 'description': 'Hoe weet je dat het is opgelost?'},
        'escalerenAls': {'type': 'string', 'description': 'Wanneer doorzetten naar de tweede lijn.'},
        'tijdInschatting': {'type': 'integer', 'description': 'Geschatte tijd in minuten (veelvoud van 15).'},
        'uitleg': {'type': 'string', 'description': 'Waarom dit gebeurt en waarom de oplossing werkt, in 2-4 zinnen gewone taal, toegespitst op dit ticket.'},
    }}


@api('adv.ticket')
def adv_ticket(c: Ctx, b: dict) -> dict:
    """Advies voor één ticket: IT Glue + Microsoft Learn + (als ingesteld) AI-stappenplan. 1 uur bewaard per ticket."""
    _zet_auth(c)
    tid, titel, tekst, klant = b.get('id'), str(b.get('title') or ''), str(b.get('description') or ''), str(b.get('company') or '')
    s = ('t', tid, titel)
    with _lock:
        item = _CACHE.get(s)
    if item and not b.get('fresh') and time.time() - item[0] < 3600:
        return item[1]
    from .h_itglue import zoeken
    kennis = zoeken(f'{titel} {titel} {tekst}', klant, 3, 5.0, onderwerp=titel)
    uit = {'itglue': kennis, 'ai': None, 'aiAvailable': False}
    if beschikbaar():
        uit['aiAvailable'] = True
        # Microsoft Learn alleen als bron voor de AI: de medewerker krijgt de uitleg in gewone taal, geen links om zelf te lezen
        bronnen = learn(titel, 3)
        context = '\n'.join([f'- IT Glue: {k["title"]} ({k["org"]}): {k["snippet"]}' for k in kennis]
                            + [f'- Microsoft-documentatie: {a["title"]}: {a["description"]}' for a in bronnen])
        prompt = (f'Ticket{f" bij klant {klant}" if klant else ""}.\n\nOnderwerp: {schoon(titel, 300)}\n\nBeschrijving:\n{schoon(tekst)}\n\n'
                  f'Achtergrond (onze IT Glue-documentatie en Microsoft-documentatie; gebruik alleen wat echt over dit probleem gaat):\n{context or "(geen)"}\n\n'
                  'Maak een stappenplan voor een eerstelijnsmedewerker. Leg alles zelf uit in gewone taal, concreet voor dit ticket; '
                  'verwijs NIET naar artikelen of websites. Noem IT Glue alleen als daar klantspecifieke informatie staat die nodig is. Houd het kort en praktisch.')
        try:
            uit['ai'] = _vraag(prompt, ADVIES_SCHEMA, 'medium')
        except ApiFout as e:
            log.info('AI-advies: %s', e)
            uit['aiAvailable'] = beschikbaar()
    with _lock:
        _CACHE[s] = (time.time(), uit)
    return uit


TRIAGE_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['tickets'],
    'properties': {'tickets': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False, 'required': ['id', 'eersteLijn', 'reden', 'minuten'],
        'properties': {'id': {'type': 'integer'}, 'eersteLijn': {'type': 'boolean'},
                       'reden': {'type': 'string', 'description': 'Max. 15 woorden, gewone taal.'},
                       'minuten': {'type': 'integer', 'description': 'Geschatte tijd in minuten.'}}}}}}


def triage(tickets: list[dict]) -> dict[int, dict]:
    """Welke open tickets kan de eerste lijn oppakken? Eén AI-vraag voor alle tickets (alleen nummer, onderwerp, eerste regels)."""
    if not tickets or not beschikbaar():
        return {}
    s = ('triage', tuple(sorted(t['id'] for t in tickets)))
    with _lock:
        item = _CACHE.get(s)
    if item and time.time() - item[0] < 1800:
        return item[1]
    regels = [f"{t['id']} | {schoon(t['title'], 160)} | {schoon(t.get('description') or '', 200).replace(chr(10), ' ')}" for t in tickets[:250]]
    prompt = ('Hieronder open tickets (id | onderwerp | begin van de beschrijving). Geef per ticket aan of een eerstelijnsmedewerker '
              '(basiskennis Microsoft 365, Windows, wachtwoorden, printers, Outlook, Teams) het zelfstandig en veilig kan oppakken. '
              'Projecten, netwerk/firewall, servers, migraties, offertes en beveiligingsincidenten zijn tweede lijn.\n\n' + '\n'.join(regels))
    r = _vraag(prompt, TRIAGE_SCHEMA, 'low', 16000)
    uit = {int(x['id']): x for x in r.get('tickets') or []}
    with _lock:
        _CACHE[s] = (time.time(), uit)
    return uit


TIJD_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['tekst'], 'properties': {'tekst': {'type': 'string'}}}


@api('adv.tijdtekst')
def adv_tijdtekst(c: Ctx, b: dict) -> dict:
    """Nette omschrijving voor een tijdregel, op basis van het ticket en de steekwoorden van de medewerker."""
    _zet_auth(c)
    prompt = (f"Ticket: {schoon(b.get('title') or '', 300)}\nWat de medewerker deed (steekwoorden): {schoon(b.get('notes') or '', 1500)}\n\n"
              'Schrijf een korte, nette omschrijving voor de tijdregel in Autotask (2-5 zinnen, verleden tijd, zakelijk, voor de klant leesbaar). '
              'Alleen wat er gedaan is en het resultaat; geen aannames toevoegen.')
    return {'text': _vraag(prompt, TIJD_SCHEMA, 'low', 2000)['tekst']}


def vergeet() -> None:
    with _lock:
        _CACHE.clear()
    _CLIENT.clear()
