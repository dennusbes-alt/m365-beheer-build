"""Automatisering: processen opbouwen uit bouwstenen en uitvoeren bij een of meer klanten.

Een proces (definitie) bestaat uit:
- invoer: startgegevens die je bij het uitvoeren invult (bijv. voornaam, achternaam);
- stappen: bouwstenen met instellingen. Instellingen mogen variabelen bevatten: {{voornaam}}, {{klantdomein}},
  {{stap1.upn}} (uitkomst van een eerdere stap) en filters zoals {{voornaam|klein}}.
Per stap: een voorwaarde (alleen uitvoeren als ...) en wat er bij een fout gebeurt (stoppen of doorgaan).

Processen worden gedeeld bewaard in een SharePoint-lijst in de Justdata-tenant (alleen de opzet, nooit wachtwoorden
of tokens). Lukt dat (nog) niet, dan op deze computer. Uitvoeren gebeurt in de app zelf, met de rechten van de
ingelogde beheerder, zoals elke andere actie in de app.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import string
import threading
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from . import common as C
from . import lokaal
from .clients import NULL, ApiFout, Graph, hashtabel, achtergrond_fn
from .context import API, Ctx, Tenant, api

log = logging.getLogger('m365beheer')
LIJST = 'M365BeheerAutomatiseringen'
LOKAAL = 'automatiseringen.json'

# ======================================================================================================
# Variabelen en voorwaarden
# ======================================================================================================
FILTERS: dict[str, Callable[[str], str]] = {
    'klein': str.lower, 'groot': str.upper, 'zonderspaties': lambda s: re.sub(r'\s+', '', s),
    'eerste': lambda s: s[:1], 'zonderaccenten': lambda s: ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch)),
    'alias': lambda s: re.sub(r'[^a-z0-9.\-]', '', ''.join(ch for ch in unicodedata.normalize('NFKD', s.lower()) if not unicodedata.combining(ch)).replace(' ', '')),
}


def _waarde(vars_: dict, pad: str) -> Any:
    deel = pad.strip().split('|')
    sleutel, filters = deel[0].strip().lower(), [f.strip().lower() for f in deel[1:]]
    w: Any = vars_
    for stuk in sleutel.split('.'):
        w = w.get(stuk, '') if isinstance(w, dict) else ''
    if isinstance(w, list):
        w = ', '.join(str(x) for x in w)
    w = '' if w is None else str(w)
    for f in filters:
        if f in FILTERS:
            w = FILTERS[f](w)
    return w


def invullen(tekst: Any, vars_: dict) -> Any:
    """{{naam}} in een tekst vervangen door de waarde (ook in lijsten en vinkjes)."""
    if isinstance(tekst, str):
        return re.sub(r'\{\{([^}]+)\}\}', lambda m: _waarde(vars_, m.group(1)), tekst)
    if isinstance(tekst, list):
        return [invullen(x, vars_) for x in tekst]
    return tekst


def voorwaarde_ok(v: dict | None, vars_: dict) -> bool:
    if not v or not v.get('veld'):
        return True
    links = str(invullen('{{' + v['veld'] + '}}', vars_)).strip().lower()
    rechts = str(invullen(v.get('waarde') or '', vars_)).strip().lower()
    op = v.get('op') or 'gelijk'
    return {'gelijk': links == rechts, 'niet': links != rechts, 'bevat': rechts in links, 'leeg': not links,
            'gevuld': bool(links), 'ja': links in ('ja', 'true', '1', 'waar'), 'nee': links not in ('ja', 'true', '1', 'waar')}.get(op, True)


def _lijst(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r'[,;\n]', str(v or '')) if x.strip()]


def _ja(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ('ja', 'true', '1', 'waar', 'aan')


def wachtwoord_maken(n: int = 14) -> str:
    tekens = string.ascii_letters + string.digits
    while True:
        w = ''.join(secrets.choice(tekens) for _ in range(n - 2)) + secrets.choice('!#$%&*+-?') + secrets.choice(string.digits)
        if any(c.islower() for c in w) and any(c.isupper() for c in w):
            return w


# ======================================================================================================
# Hulpfuncties voor bouwstenen
# ======================================================================================================
def _gebruiker(c: Ctx, wie: str) -> dict:
    wie = str(wie or '').strip()
    if not wie:
        raise ApiFout('Geen gebruiker opgegeven.')
    sel = '$select=id,displayName,userPrincipalName,mail,department,jobTitle,accountEnabled,assignedLicenses,usageLocation'
    if '@' in wie:
        try:
            return c.g.get(f"/users/{wie}?{sel}")
        except ApiFout as e:
            if e.status != 404:
                raise
            r = c.g.get(f"/users?$filter=mail eq '{wie.replace(chr(39), chr(39) * 2)}'&{sel}").get('value') or []
            if r:
                return r[0]
            raise ApiFout(f'Gebruiker {wie} niet gevonden.')
    r = c.g.get(f"/users?$filter=displayName eq '{wie.replace(chr(39), chr(39) * 2)}'&{sel}").get('value') or []
    if len(r) != 1:
        raise ApiFout(f"Gebruiker '{wie}' {'niet gevonden' if not r else 'is niet uniek (gebruik het e-mailadres)'}.")
    return r[0]


def _groep(c: Ctx, naam: str) -> dict:
    n = naam.strip().lower()
    for g in C.groepen(c):
        if n in (str(g.get('name') or '').lower(), str(g.get('mail') or '').lower()):
            return g
    raise ApiFout(f"Groep '{naam}' niet gevonden.")


def _skus(c: Ctx, namen: list[str]) -> list[dict]:
    alle = C.licenties(c, vers=True)
    uit = []
    for n in namen:
        n2 = n.strip().lower()
        s = next((x for x in alle if n2 in (x['part'].lower(), x['name'].lower(), x['id'].lower())), None) \
            or next((x for x in alle if n2 in x['name'].lower()), None)
        if not s:
            raise ApiFout(f"Licentie '{n}' niet gevonden bij deze klant.")
        uit.append(s)
    return uit


def _api(c: Ctx, naam: str, body: dict) -> dict:
    """Een bestaande actie van de app aanroepen (zodat een proces precies doet wat de knop in de app doet)."""
    return API[naam](c, body) or {}


# ======================================================================================================
# Bouwstenen
# ======================================================================================================
BLOKKEN: dict[str, dict] = {}


def blok(sleutel: str, groep: str, naam: str, uitleg: str, velden: list[dict], uitvoer: list[str] | None = None, takken: list[str] | None = None):
    """takken: logica-bouwstenen met eigen stappen erin, bijv. ['ja', 'nee'] (als/anders) of ['stappen'] (voor elk)."""
    def deco(fn):
        BLOKKEN[sleutel] = {'key': sleutel, 'group': groep, 'name': naam, 'help': uitleg, 'fields': velden, 'outputs': uitvoer or [], 'fn': fn,
                            'branches': takken or []}
        return fn
    return deco


class Stoppen(Exception):
    """Bouwsteen 'Stoppen': het proces netjes beëindigen (geen fout)."""


def V(key: str, label: str, soort: str = 'tekst', **kw) -> dict:
    return {'key': key, 'label': label, 'type': soort, **kw}


GEBRUIKER = V('gebruiker', 'Gebruiker (e-mailadres)', placeholder='{{upn}}', required=True)
G1, G2, G3, G4 = 'Gebruikers en licenties', 'Exchange en postvakken', 'Apparaten en Intune', 'Controles en rapportage'
G0, G5, G6, G7 = 'Logica', 'Groepen, Teams en gasten', 'Autotask', 'Documentatie (IT Glue)'


# ---------- Gebruikers en licenties ----------
@blok('gebruiker.aanmaken', G1, 'Gebruiker aanmaken', 'Maakt een nieuw account aan. Een leeg wachtwoord wordt automatisch gemaakt.', [
    V('voornaam', 'Voornaam', required=True, placeholder='{{voornaam}}'), V('achternaam', 'Achternaam', required=True, placeholder='{{achternaam}}'),
    V('weergavenaam', 'Weergavenaam', placeholder='{{voornaam}} {{achternaam}}'),
    V('alias', 'Alias (voor de @)', required=True, placeholder='{{voornaam|alias}}.{{achternaam|alias}}'),
    V('domein', 'Domein', placeholder='{{klantdomein}}'), V('wachtwoord', 'Wachtwoord (leeg = automatisch)', 'wachtwoord'),
    V('wijzigen', 'Wachtwoord wijzigen bij eerste aanmelding', 'vink', default=True),
    V('functie', 'Functie'), V('afdeling', 'Afdeling'), V('mobiel', 'Mobiel nummer')], ['upn', 'id', 'wachtwoord', 'naam'])
def b_gebruiker_aanmaken(c: Ctx, p: dict) -> dict:
    domein = p.get('domein') or c.t.standaard_domein
    alias = FILTERS['alias'](str(p['alias']))
    upn = f'{alias}@{domein}'.lower()
    naam = p.get('weergavenaam') or f"{p['voornaam']} {p['achternaam']}".strip()
    ww = p.get('wachtwoord') or wachtwoord_maken()
    body = {'accountEnabled': True, 'displayName': naam, 'givenName': p['voornaam'], 'surname': p['achternaam'], 'userPrincipalName': upn,
            'mailNickname': alias, 'usageLocation': 'NL', 'passwordProfile': {'password': ww, 'forceChangePasswordNextSignIn': _ja(p.get('wijzigen', True))}}
    for k, veld in (('functie', 'jobTitle'), ('afdeling', 'department'), ('mobiel', 'mobilePhone')):
        if p.get(k):
            body[veld] = p[k]
    if c.g.get(f"/users?$filter=userPrincipalName eq '{upn}'&$select=id").get('value'):
        raise ApiFout(f'Er bestaat al een gebruiker met adres {upn}.')
    u = c.g.post('/users', body)
    c.L(f'Gebruiker {upn} aangemaakt.')
    c.t.weg('users')
    return {'upn': upn, 'id': u['id'], 'wachtwoord': ww, 'naam': naam}


@blok('gebruiker.zoeken', G1, 'Gebruiker opzoeken', 'Zoekt een gebruiker op e-mailadres of naam; de gegevens zijn daarna als variabele te gebruiken.',
      [GEBRUIKER], ['upn', 'id', 'naam', 'afdeling', 'functie', 'ingeschakeld'])
def b_gebruiker_zoeken(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    c.L(f"Gevonden: {u.get('displayName')} ({u['userPrincipalName']}).")
    return {'upn': u['userPrincipalName'], 'id': u['id'], 'naam': u.get('displayName') or '', 'afdeling': u.get('department') or '',
            'functie': u.get('jobTitle') or '', 'ingeschakeld': 'ja' if u.get('accountEnabled') else 'nee'}


@blok('gebruiker.wijzigen', G1, 'Gebruikersgegevens wijzigen', 'Alleen ingevulde velden worden aangepast.', [
    GEBRUIKER, V('weergavenaam', 'Weergavenaam'), V('functie', 'Functie'), V('afdeling', 'Afdeling'), V('kantoor', 'Kantoor'), V('mobiel', 'Mobiel nummer'),
    V('manager', 'Manager (e-mailadres)')])
def b_gebruiker_wijzigen(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    body = {veld: p[k] for k, veld in (('weergavenaam', 'displayName'), ('functie', 'jobTitle'), ('afdeling', 'department'),
                                         ('kantoor', 'officeLocation'), ('mobiel', 'mobilePhone')) if p.get(k)}
    if body:
        c.g.patch(f"/users/{u['id']}", body)
    if p.get('manager'):
        m = _gebruiker(c, p['manager'])
        c.g.req('PUT', f"/users/{u['id']}/manager/$ref", {'@odata.id': f"https://graph.microsoft.com/v1.0/users/{m['id']}"})
    c.L(f"Gegevens van {u['userPrincipalName']} bijgewerkt.")
    return {}


@blok('gebruiker.blokkeren', G1, 'Aanmelden blokkeren of toestaan', 'Bij blokkeren worden ook alle sessies afgemeld.', [
    GEBRUIKER, V('actie', 'Actie', 'keuze', opties=['blokkeren', 'toestaan'], default='blokkeren')])
def b_gebruiker_blokkeren(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    blok_ = (p.get('actie') or 'blokkeren') == 'blokkeren'
    c.g.patch(f"/users/{u['id']}", {'accountEnabled': not blok_})
    if blok_:
        C.intrekken(c, u['id'])
    c.L(f"Aanmelden {'geblokkeerd en sessies afgemeld' if blok_ else 'weer toegestaan'} voor {u['userPrincipalName']}.")
    c.t.weg('users')
    return {}


@blok('gebruiker.sessies', G1, 'Alle sessies afmelden', 'De gebruiker moet op alle apparaten opnieuw inloggen.', [GEBRUIKER])
def b_gebruiker_sessies(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    C.intrekken(c, u['id'])
    c.L(f"Alle sessies van {u['userPrincipalName']} afgemeld.")
    return {}


@blok('gebruiker.wachtwoord', G1, 'Wachtwoord opnieuw instellen', 'Een leeg wachtwoord wordt automatisch gemaakt en komt in het rapport.', [
    GEBRUIKER, V('wachtwoord', 'Nieuw wachtwoord (leeg = automatisch)', 'wachtwoord'),
    V('wijzigen', 'Wijzigen bij volgende aanmelding', 'vink', default=True)], ['wachtwoord'])
def b_gebruiker_wachtwoord(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    ww = p.get('wachtwoord') or wachtwoord_maken()
    c.g.patch(f"/users/{u['id']}", {'passwordProfile': {'password': ww, 'forceChangePasswordNextSignIn': _ja(p.get('wijzigen', True))}})
    c.L(f"Wachtwoord van {u['userPrincipalName']} opnieuw ingesteld.")
    return {'wachtwoord': ww}


@blok('licentie.toewijzen', G1, 'Licentie toewijzen', 'Licenties op naam of productcode, gescheiden door komma\'s (bijv. Business Premium).', [
    GEBRUIKER, V('licenties', 'Licenties', placeholder='Microsoft 365 Business Premium', required=True)])
def b_licentie_toewijzen(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    skus = _skus(c, _lijst(p['licenties']))
    if not u.get('usageLocation'):
        c.g.patch(f"/users/{u['id']}", {'usageLocation': 'NL'})
    vol = [s['name'] for s in skus if s['free'] <= 0]
    if vol:
        c.L(f"Let op: geen vrije licenties meer voor {', '.join(vol)}.")
    c.g.post(f"/users/{u['id']}/assignLicense", {'addLicenses': [{'skuId': s['id'], 'disabledPlans': []} for s in skus], 'removeLicenses': []})
    c.L(f"Licentie(s) toegewezen aan {u['userPrincipalName']}: {', '.join(s['name'] for s in skus)}.")
    c.t.weg('users', 'skus')
    return {}


@blok('licentie.weghalen', G1, 'Licentie weghalen', 'Vul "alle" in om alle direct toegewezen licenties weg te halen.', [
    GEBRUIKER, V('licenties', 'Licenties', placeholder='alle', required=True)])
def b_licentie_weghalen(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    if str(p['licenties']).strip().lower() == 'alle':
        ids = [x['skuId'] for x in u.get('assignedLicenses') or []]
    else:
        ids = [s['id'] for s in _skus(c, _lijst(p['licenties']))]
    if ids:
        c.g.post(f"/users/{u['id']}/assignLicense", {'addLicenses': [], 'removeLicenses': ids})
    c.L(f"{len(ids)} licentie(s) weggehaald bij {u['userPrincipalName']}.")
    c.t.weg('users', 'skus')
    return {}


@blok('groep.toevoegen', G1, 'Toevoegen aan groepen', 'Groepen op naam of e-mailadres, gescheiden door komma\'s. Werkt ook voor distributielijsten.', [
    GEBRUIKER, V('groepen', 'Groepen', required=True)])
def b_groep_toevoegen(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    for n in _lijst(p['groepen']):
        g = _groep(c, n)
        C.lid_toevoegen(c, g['type'], g['id'], g.get('mail') or '', u)
        c.L(f"{u['userPrincipalName']} toegevoegd aan {g['name']}.")
    return {}


@blok('groep.verwijderen', G1, 'Uit groepen verwijderen', 'Vul "alle" in om de gebruiker uit alle (niet-dynamische) groepen te halen.', [
    GEBRUIKER, V('groepen', 'Groepen', placeholder='alle', required=True)])
def b_groep_verwijderen(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    if str(p['groepen']).strip().lower() == 'alle':
        lid = {g['id'] for g in c.g.all(f"/users/{u['id']}/memberOf/microsoft.graph.group?$select=id")}
        doel = [g for g in C.groepen(c, vers=True) if g['id'] in lid and g['type'] not in ('Dynamisch',)]
    else:
        doel = [_groep(c, n) for n in _lijst(p['groepen'])]
    for g in doel:
        try:
            C.lid_verwijderen(c, g['type'], g['id'], g.get('mail') or '', u)
            c.L(f"Verwijderd uit {g['name']}.")
        except ApiFout as e:
            c.L(f"FOUT {g['name']}: {e}")
    return {}


@blok('mfa.verwijderen', G1, 'MFA-methoden verwijderen', 'Verwijdert alle aanmeldmethoden behalve het wachtwoord, zodat de gebruiker MFA opnieuw instelt.', [GEBRUIKER])
def b_mfa_verwijderen(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    m = _api(c, 'user.mfa', {'id': u['id']})
    ids = [x['id'] for x in m.get('methods') or [] if x.get('supported')]
    if ids:
        _api(c, 'user.mfareset', {'id': u['id'], 'ids': ids})
    c.L(f"{len(ids)} MFA-methode(n) verwijderd bij {u['userPrincipalName']}.")
    return {}


# ---------- Exchange en postvakken ----------
@blok('postvak.wachten', G2, 'Wachten tot het postvak bestaat', 'Na het toewijzen van een licentie duurt het enkele minuten voordat het postvak bestaat.', [
    GEBRUIKER, V('minuten', 'Maximaal wachten (minuten)', 'getal', default='10')])
def b_postvak_wachten(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    if not C.wacht_op_mailbox(c, upn, int(float(p.get('minuten') or 10) * 60)):
        raise ApiFout(f'Het postvak van {upn} bestaat na {p.get("minuten") or 10} minuten nog niet.')
    c.L(f'Postvak van {upn} is klaar.')
    return {}


@blok('postvak.gedeeld', G2, 'Postvak omzetten naar gedeeld postvak', 'Het postvak blijft bestaan zonder licentie (tot 50 GB).', [GEBRUIKER])
def b_postvak_gedeeld(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    c.x.run('Set-Mailbox', Identity=upn, Type='Shared')
    c.L(f'Postvak van {upn} is nu een gedeeld postvak.')
    return {}


@blok('gedeeld.aanmaken', G2, 'Gedeeld postvak aanmaken', '', [
    V('naam', 'Weergavenaam', required=True), V('alias', 'Adres (voor de @)', required=True), V('domein', 'Domein', placeholder='{{klantdomein}}')], ['mail'])
def b_gedeeld_aanmaken(c: Ctx, p: dict) -> dict:
    domein = p.get('domein') or c.t.standaard_domein
    alias = FILTERS['alias'](str(p['alias']))
    _api(c, 'group.create', {'kind': 'Gedeeld', 'name': p['naam'], 'alias': alias, 'domain': domein})
    return {'mail': f'{alias}@{domein}'}


@blok('postvak.rechten', G2, 'Rechten op postvakken geven', 'Postvakken gescheiden door komma\'s.', [
    V('postvakken', 'Postvakken (e-mailadres)', required=True), GEBRUIKER,
    V('volledig', 'Volledige toegang', 'vink', default=True), V('verzenden', 'Verzenden als', 'vink', default=True),
    V('namens', 'Verzenden namens', 'vink', default=False), V('automapping', 'Automapping', 'vink', default=True)])
def b_postvak_rechten(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    for mb in _lijst(p['postvakken']):
        C.gedeeld_rechten(c, mb, upn, _ja(p.get('volledig')), _ja(p.get('verzenden')), _ja(p.get('automapping')))
        if _ja(p.get('namens')):
            c.x.run('Set-Mailbox', Identity=mb, GrantSendOnBehalfTo=hashtabel(Add=upn))
        C.rechten_bijwerken(c, mb, upn, _ja(p.get('volledig')), _ja(p.get('verzenden')), erbij=True)
        c.L(f'{upn} heeft nu rechten op {mb}.')
    return {}


@blok('postvak.rechten_weg', G2, 'Rechten op postvakken weghalen', 'Haalt volledige toegang, verzenden als en verzenden namens weg.', [
    V('postvakken', 'Postvakken (e-mailadres)', required=True), GEBRUIKER])
def b_postvak_rechten_weg(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    x = c.x
    for mb in _lijst(p['postvakken']):
        for cmd, kw in (('Remove-MailboxPermission', {'User': upn, 'AccessRights': ['FullAccess'], 'InheritanceType': 'All'}),
                        ('Remove-RecipientPermission', {'Trustee': upn, 'AccessRights': ['SendAs']})):
            try:
                x.run(cmd, Identity=mb, Confirm=False, **kw)
            except ApiFout:
                pass
        try:
            x.run('Set-Mailbox', Identity=mb, GrantSendOnBehalfTo=hashtabel(Remove=upn))
        except ApiFout:
            pass
        C.rechten_bijwerken(c, mb, upn, True, True, erbij=False)
        c.L(f'Rechten van {upn} op {mb} weggehaald.')
    return {}


@blok('agenda.recht', G2, 'Agendarecht geven', '', [
    V('agenda', 'Agenda van (e-mailadres)', required=True), GEBRUIKER,
    V('recht', 'Recht', 'keuze', opties=['Reviewer', 'Editor', 'Author', 'LimitedDetails', 'AvailabilityOnly', 'Owner'], default='Reviewer'),
    V('gemachtigde', 'Gemachtigde (Delegate, alleen bij Editor)', 'vink'), V('prive', 'Privé-items zien', 'vink'),
    V('melding', 'Melding naar de gebruiker sturen', 'vink')])
def b_agenda_recht(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    C.agenda_recht(c, p['agenda'], upn, p.get('recht') or 'Reviewer', _ja(p.get('gemachtigde')), _ja(p.get('prive')), _ja(p.get('melding')))
    c.L(f"{upn} heeft nu {p.get('recht') or 'Reviewer'} op de agenda van {p['agenda']}.")
    return {}


@blok('postvak.alias', G2, 'E-mailalias toevoegen', '', [GEBRUIKER, V('adres', 'Extra e-mailadres', required=True)])
def b_postvak_alias(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    c.x.run('Set-Mailbox', Identity=upn, EmailAddresses=hashtabel(Add=f"smtp:{p['adres']}"))
    c.L(f"Alias {p['adres']} toegevoegd aan {upn}.")
    return {}


@blok('postvak.doorsturen', G2, 'Doorsturen instellen', 'Laat het adres leeg om doorsturen uit te zetten.', [
    GEBRUIKER, V('naar', 'Doorsturen naar (e-mailadres)'), V('bewaren', 'Ook een kopie in het postvak bewaren', 'vink', default=True)])
def b_postvak_doorsturen(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    if p.get('naar'):
        c.x.run('Set-Mailbox', Identity=upn, ForwardingSmtpAddress=f"smtp:{p['naar']}", DeliverToMailboxAndForward=_ja(p.get('bewaren', True)))
        c.L(f"Mail van {upn} wordt doorgestuurd naar {p['naar']}.")
    else:
        c.x.run('Set-Mailbox', Identity=upn, ForwardingSmtpAddress=NULL, ForwardingAddress=NULL, DeliverToMailboxAndForward=False)
        c.L(f'Doorsturen voor {upn} uitgezet.')
    return {}


@blok('postvak.afwezig', G2, 'Automatisch antwoord (afwezig)', '', [
    GEBRUIKER, V('aan', 'Automatisch antwoord aan', 'vink', default=True), V('intern', 'Bericht voor collega\'s', 'tekstvak'),
    V('extern', 'Bericht voor externen (leeg = zelfde)', 'tekstvak')])
def b_postvak_afwezig(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    if _ja(p.get('aan', True)):
        intern = p.get('intern') or ''
        c.x.run('Set-MailboxAutoReplyConfiguration', Identity=upn, AutoReplyState='Enabled', InternalMessage=intern,
                ExternalMessage=p.get('extern') or intern, ExternalAudience='All')
        c.L(f'Automatisch antwoord aangezet voor {upn}.')
    else:
        c.x.run('Set-MailboxAutoReplyConfiguration', Identity=upn, AutoReplyState='Disabled')
        c.L(f'Automatisch antwoord uitgezet voor {upn}.')
    return {}


# ---------- Apparaten en Intune ----------
def _apparaten_van(c: Ctx, upn: str) -> list[dict]:
    return c.g.all(f"/deviceManagement/managedDevices?$filter=userPrincipalName eq '{upn}'&$select=id,deviceName,operatingSystem,lastSyncDateTime,complianceState")


@blok('apparaten.lijst', G3, 'Apparaten van gebruiker in rapport', 'Zet de Intune-apparaten van de gebruiker in het rapport.', [GEBRUIKER], ['aantal'])
def b_apparaten_lijst(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    l = _apparaten_van(c, upn)
    for d in l:
        c.rapport.append({'Gebruiker': upn, 'Apparaat': d.get('deviceName'), 'Systeem': d.get('operatingSystem'),
                          'Compliance': d.get('complianceState'), 'Laatste synchronisatie': (d.get('lastSyncDateTime') or '')[:16].replace('T', ' ')})
    c.L(f'{len(l)} apparaat/apparaten gevonden voor {upn}.')
    return {'aantal': len(l)}


@blok('apparaten.sync', G3, 'Apparaten synchroniseren', 'Laat de gebruiker leeg om alle apparaten van de klant te synchroniseren.', [
    V('gebruiker', 'Gebruiker (leeg = alle apparaten)')])
def b_apparaten_sync(c: Ctx, p: dict) -> dict:
    if p.get('gebruiker'):
        l = _apparaten_van(c, _gebruiker(c, p['gebruiker'])['userPrincipalName'])
    else:
        l = c.g.all('/deviceManagement/managedDevices?$select=id,deviceName')
    for d in l:
        try:
            c.g.post(f"/deviceManagement/managedDevices/{d['id']}/syncDevice")
        except ApiFout as e:
            c.L(f"FOUT {d.get('deviceName')}: {e}")
    c.L(f'Synchronisatie gestart voor {len(l)} apparaat/apparaten.')
    return {}


@blok('autopilot.sync', G3, 'Autopilot synchroniseren', 'Haalt door de leverancier geregistreerde apparaten op (max. eens per 10 minuten).', [])
def b_autopilot_sync(c: Ctx, p: dict) -> dict:
    _api(c, 'ap.sync', {})
    return {}


@blok('apparaten.oud', G3, 'Oude apparaten in rapport', 'Apparaten die langer dan het aantal dagen niet hebben gesynchroniseerd. Er wordt niets verwijderd.', [
    V('dagen', 'Niet gezien in (dagen)', 'getal', default='90')], ['aantal'])
def b_apparaten_oud(c: Ctx, p: dict) -> dict:
    dagen = int(float(p.get('dagen') or 90))
    grens = (datetime.now(timezone.utc) - timedelta(days=dagen)).strftime('%Y-%m-%dT%H:%M:%S')
    l = [d for d in c.g.all('/deviceManagement/managedDevices?$select=id,deviceName,operatingSystem,userPrincipalName,lastSyncDateTime')
         if (d.get('lastSyncDateTime') or '') < grens]
    for d in l:
        c.rapport.append({'Apparaat': d.get('deviceName'), 'Systeem': d.get('operatingSystem'), 'Gebruiker': d.get('userPrincipalName') or '',
                          'Laatste synchronisatie': (d.get('lastSyncDateTime') or '')[:10]})
    c.L(f'{len(l)} apparaat/apparaten niet gezien in {dagen} dagen.')
    return {'aantal': len(l)}


# ---------- Controles en rapportage ----------
@blok('controle.licenties', G4, 'Licentiecontrole', 'Per licentie: ingekocht, toegewezen, niet toegewezen en mogelijk minder af te nemen.', [], ['mogelijkminder'])
def b_controle_licenties(c: Ctx, p: dict) -> dict:
    from .h_administratie import klant_overzicht
    k = klant_overzicht(c.staat.auth, c.tid, c.t.naam)
    for s in k['skus']:
        if s['paid']:
            c.rapport.append({'Licentie': s['name'], 'Ingekocht': s['bought'], 'Toegewezen': s['assigned'], 'Niet toegewezen': s['free'],
                              'Uitgeschakeld': s['uit'], '> 90 dagen': s['ongebruikt'], 'Mogelijk minder': s['saving'],
                              'Verlenging': (s['renew'] or '')[:10]})
    c.L(f"Licentiecontrole: {k['saving']} licentie(s) mogelijk minder af te nemen.")
    return {'mogelijkminder': k['saving']}


@blok('controle.inactief', G4, 'Inactieve gebruikers', 'Gebruikers en gasten die het aantal dagen niet hebben aangemeld (vraagt Entra ID P1).', [
    V('dagen', 'Niet aangemeld in (dagen)', 'getal', default='90')], ['aantal'])
def b_controle_inactief(c: Ctx, p: dict) -> dict:
    r = _api(c, 'inactive', {'days': int(float(p.get('dagen') or 90))})
    n = 0
    for soort, sleutel in (('Met licentie', 'licensed'), ('Zonder licentie', 'members'), ('Gast', 'guests')):
        for u in r.get(sleutel) or []:
            n += 1
            c.rapport.append({'Soort': soort, 'Naam': u.get('name'), 'E-mailadres': u.get('upn'), 'Laatst aangemeld': u.get('last') or 'nooit',
                              'Dagen': u.get('days'), 'Opmerking': u.get('reason') or ''})
    c.L(f'{n} inactieve gebruiker(s) gevonden.')
    return {'aantal': n}


@blok('controle.mfa', G4, 'MFA-controle', 'Gebruikers met een licentie die nog geen MFA hebben ingesteld (vraagt Entra ID P1).', [], ['aantal'])
def b_controle_mfa(c: Ctx, p: dict) -> dict:
    try:
        r = c.g.all("/reports/authenticationMethods/userRegistrationDetails?$filter=isMfaRegistered eq false and userType eq 'member'")
    except ApiFout as e:
        raise ApiFout(f'MFA-status opvragen lukte niet ({e}). Dit vraagt Entra ID P1 en een rol als Reports Reader of Global Reader.')
    gelic = {u['upn'].lower() for u in C.gebruikers(c, vers=True) if u.get('lic')}
    l = [u for u in r if str(u.get('userPrincipalName') or '').lower() in gelic]
    for u in l:
        c.rapport.append({'Naam': u.get('userDisplayName'), 'E-mailadres': u.get('userPrincipalName'), 'MFA ingesteld': 'nee',
                          'Methoden': ', '.join(u.get('methodsRegistered') or []) or '-'})
    c.L(f'{len(l)} gebruiker(s) met licentie zonder MFA.')
    return {'aantal': len(l)}


@blok('controle.domeinen', G4, 'Domeincontrole (DNS)', 'Controleert MX, SPF, autodiscover, DMARC en DKIM van alle domeinen; afwijkingen komen in het rapport.', [], ['aantal'])
def b_controle_domeinen(c: Ctx, p: dict) -> dict:
    n = 0
    for d in _api(c, 'dom.list', {}).get('domains') or []:
        if d['initial'] or not d['verified']:
            continue
        for r in _api(c, 'dom.get', {'id': d['id']}).get('dns') or []:
            if r['status'] != 'ok':
                n += 1
                c.rapport.append({'Domein': d['id'], 'Dienst': r['service'], 'Type': r['type'], 'Naam': r['name'], 'Status': r['status'],
                                  'Gevonden': ', '.join(r.get('found') or []) or '-'})
    c.L(f'Domeincontrole: {n} record(s) vragen aandacht.')
    return {'aantal': n}


@blok('rapport.regel', G4, 'Regel in het rapport', 'Zet een eigen regel in het rapport, bijvoorbeeld de inloggegevens van een nieuwe medewerker.', [
    V('tekst', 'Tekst', 'tekstvak', required=True, placeholder='Nieuwe medewerker: {{stap1.upn}} / {{stap1.wachtwoord}}')])
def b_rapport_regel(c: Ctx, p: dict) -> dict:
    c.rapport.append({'Melding': p['tekst']})
    c.L(p['tekst'])
    return {}


@blok('wachten', G4, 'Wachten', 'Even wachten, bijvoorbeeld tot Microsoft een wijziging heeft verwerkt.', [V('seconden', 'Seconden', 'getal', default='30')])
def b_wachten(c: Ctx, p: dict) -> dict:
    time.sleep(min(max(float(p.get('seconden') or 0), 0), 900))
    return {}


# ======================================================================================================
# Sjablonen (kant-en-klaar; kopiëren en aanpassen)
# ======================================================================================================
def _stap(n: int, blok_: str, **params) -> dict:
    return {'id': f's{n}', 'block': blok_, 'params': params, 'onError': 'stop'}


SJABLONEN = [
    {'id': 'sjabloon-onboarding', 'template': True, 'name': 'Nieuwe medewerker', 'description': 'Account, licentie, groepen, gedeelde postvakken en een rapport met de inloggegevens.',
     'inputs': [{'key': 'voornaam', 'label': 'Voornaam', 'required': True}, {'key': 'achternaam', 'label': 'Achternaam', 'required': True},
                {'key': 'functie', 'label': 'Functie'}, {'key': 'afdeling', 'label': 'Afdeling'},
                {'key': 'licentie', 'label': 'Licentie', 'default': 'Microsoft 365 Business Premium'},
                {'key': 'groepen', 'label': 'Groepen (komma)'}, {'key': 'postvakken', 'label': 'Gedeelde postvakken (komma)'}],
     'steps': [_stap(1, 'gebruiker.aanmaken', voornaam='{{voornaam}}', achternaam='{{achternaam}}', alias='{{voornaam|alias}}.{{achternaam|alias}}',
                     domein='{{klantdomein}}', functie='{{functie}}', afdeling='{{afdeling}}', wijzigen=True),
               _stap(2, 'licentie.toewijzen', gebruiker='{{stap1.upn}}', licenties='{{licentie}}'),
               {**_stap(3, 'groep.toevoegen', gebruiker='{{stap1.upn}}', groepen='{{groepen}}'), 'when': {'veld': 'groepen', 'op': 'gevuld'}},
               {**_stap(4, 'postvak.wachten', gebruiker='{{stap1.upn}}', minuten='10'), 'when': {'veld': 'postvakken', 'op': 'gevuld'}},
               {**_stap(5, 'postvak.rechten', postvakken='{{postvakken}}', gebruiker='{{stap1.upn}}', volledig=True, verzenden=True, automapping=True),
                'when': {'veld': 'postvakken', 'op': 'gevuld'}},
               _stap(6, 'rapport.regel', tekst='{{stap1.naam}}: {{stap1.upn}} / wachtwoord {{stap1.wachtwoord}}')]},
    {'id': 'sjabloon-offboarding', 'template': True, 'name': 'Medewerker uit dienst', 'description': 'Blokkeren, sessies en MFA weg, postvak gedeeld maken en overdragen, licenties en groepen weg.',
     'inputs': [{'key': 'medewerker', 'label': 'Medewerker (e-mailadres)', 'required': True},
                {'key': 'overdragen', 'label': 'Postvak overdragen aan (e-mailadres)'}, {'key': 'afwezigtekst', 'label': 'Automatisch antwoord'}],
     'steps': [_stap(1, 'gebruiker.blokkeren', gebruiker='{{medewerker}}', actie='blokkeren'),
               {**_stap(2, 'mfa.verwijderen', gebruiker='{{medewerker}}'), 'onError': 'continue'},
               _stap(3, 'postvak.gedeeld', gebruiker='{{medewerker}}'),
               {**_stap(4, 'postvak.rechten', postvakken='{{medewerker}}', gebruiker='{{overdragen}}', volledig=True, verzenden=False, automapping=True),
                'when': {'veld': 'overdragen', 'op': 'gevuld'}},
               {**_stap(5, 'postvak.afwezig', gebruiker='{{medewerker}}', aan=True, intern='{{afwezigtekst}}'), 'when': {'veld': 'afwezigtekst', 'op': 'gevuld'}},
               {**_stap(6, 'groep.verwijderen', gebruiker='{{medewerker}}', groepen='alle'), 'onError': 'continue'},
               _stap(7, 'licentie.weghalen', gebruiker='{{medewerker}}', licenties='alle'),
               _stap(8, 'rapport.regel', tekst='{{medewerker}} is uit dienst gemeld.')]},
    {'id': 'sjabloon-onboarding-plus', 'template': True, 'name': 'Nieuwe medewerker met Autotask en IT Glue',
     'description': 'Account met licentie; per afdeling andere groepen (als/anders); elke gedeelde postvak apart (voor elk); ticket met tijd en documentatie in IT Glue.',
     'inputs': [{'key': 'voornaam', 'label': 'Voornaam', 'required': True}, {'key': 'achternaam', 'label': 'Achternaam', 'required': True},
                {'key': 'afdeling', 'label': 'Afdeling', 'default': 'Kantoor'}, {'key': 'postvakken', 'label': 'Gedeelde postvakken (komma)'},
                {'key': 'licentie', 'label': 'Licentie', 'default': 'Microsoft 365 Business Premium'}],
     'steps': [_stap(1, 'gebruiker.aanmaken', voornaam='{{voornaam}}', achternaam='{{achternaam}}', alias='{{voornaam|alias}}.{{achternaam|alias}}',
                     domein='{{klantdomein}}', afdeling='{{afdeling}}', wijzigen=True),
               _stap(2, 'licentie.toewijzen', gebruiker='{{stap1.upn}}', licenties='{{licentie}}'),
               {**_stap(3, 'logica.als', waarde='{{afdeling}}', op='is gelijk aan', vergelijk='Verkoop'),
                'children': {'ja': [{**_stap(31, 'groep.toevoegen', gebruiker='{{stap1.upn}}', groepen='Verkoop'), 'onError': 'continue'}],
                             'nee': [{**_stap(32, 'groep.toevoegen', gebruiker='{{stap1.upn}}', groepen='Kantoor'), 'onError': 'continue'}]}},
               {**_stap(4, 'postvak.wachten', gebruiker='{{stap1.upn}}', minuten='10'), 'when': {'veld': 'postvakken', 'op': 'gevuld'}},
               {**_stap(5, 'logica.voorelk', lijst='{{postvakken}}'), 'when': {'veld': 'postvakken', 'op': 'gevuld'},
                'children': {'stappen': [{**_stap(51, 'postvak.rechten', postvakken='{{item}}', gebruiker='{{stap1.upn}}', volledig=True, verzenden=True, automapping=True),
                                          'onError': 'continue'}]}},
               {**_stap(6, 'at.ticket', titel='Nieuwe medewerker {{stap1.naam}}', omschrijving='Account {{stap1.upn}} aangemaakt via Microsoft 365 beheer.', minuten='15'),
                'onError': 'continue'},
               {**_stap(7, 'itglue.document', titel='Nieuwe medewerker {{stap1.naam}} ({{datum}})',
                        oplossing='Account {{stap1.upn}}, licentie {{licentie}}, afdeling {{afdeling}}, postvakken: {{postvakken}}.'), 'onError': 'continue'},
               _stap(8, 'rapport.regel', tekst='{{stap1.naam}}: {{stap1.upn}} / wachtwoord {{stap1.wachtwoord}}')]},
    {'id': 'sjabloon-maandcontrole', 'template': True, 'name': 'Maandcontrole', 'description': 'Licenties, inactieve gebruikers, MFA, domeinen en oude apparaten in één rapport. Wijzigt niets.',
     'inputs': [],
     'steps': [{**_stap(1, 'controle.licenties'), 'onError': 'continue'}, {**_stap(2, 'controle.inactief', dagen='90'), 'onError': 'continue'},
               {**_stap(3, 'controle.mfa'), 'onError': 'continue'}, {**_stap(4, 'controle.domeinen'), 'onError': 'continue'},
               {**_stap(5, 'apparaten.oud', dagen='90'), 'onError': 'continue'}]},
]


# ======================================================================================================
# Opslag: SharePoint-lijst in de Justdata-tenant, anders lokaal
# ======================================================================================================
class Opslag:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.site = ''
        self.lijst_id = ''

    def _g(self, c: Ctx) -> Graph:
        a = c.staat.auth
        return Graph(lambda: a.token(a.home_tenant, 'partner'))

    def _lijst(self, c: Ctx) -> tuple[Graph, str, str]:
        g = self._g(c)
        with self.lock:
            if not self.lijst_id:
                site = g.get('/sites/root?$select=id')['id']
                l = g.get(f"/sites/{site}/lists?$filter=displayName eq '{LIJST}'&$select=id").get('value') or []
                if l:
                    lid = l[0]['id']
                else:
                    lid = g.post(f'/sites/{site}/lists', {'displayName': LIJST, 'description': 'Processen van de app Microsoft 365 beheer (Justdata)',
                                                          'columns': [{'name': 'Definitie', 'text': {'allowMultipleLines': True, 'textType': 'plain'}}],
                                                          'list': {'template': 'genericList', 'hidden': False}})['id']
                    log.info('SharePoint-lijst %s aangemaakt', LIJST)
                self.site, self.lijst_id = site, lid
            return g, self.site, self.lijst_id

    def _ik(self, g: Graph) -> dict:
        """Wie ben ik in de Justdata-tenant (om eigen processen te herkennen)."""
        if not getattr(self, '_mij', None):
            m = g.get('/me?$select=id,displayName')
            self._mij = {'id': m.get('id') or '', 'name': m.get('displayName') or ''}
        return self._mij

    @staticmethod
    def _maker(it: dict) -> dict:
        u = (it.get('createdBy') or {}).get('user') or {}
        return {'id': u.get('id') or '', 'name': u.get('displayName') or ''}

    def lijst(self, c: Ctx) -> tuple[list[dict], str]:
        """Teamprocessen (iedereen) en mijn eigen processen. Eigen processen van collega's worden niet getoond."""
        try:
            g, site, lid = self._lijst(c)
            ik = self._ik(g)
            items = g.all(f'/sites/{site}/lists/{lid}/items?$expand=fields($select=Title,Definitie)&$top=200')
            uit = []
            for it in items:
                try:
                    d = json.loads((it.get('fields') or {}).get('Definitie') or '{}')
                except ValueError:
                    continue
                maker = self._maker(it)
                d['scope'] = 'eigen' if d.get('scope') == 'eigen' else 'team'
                mijn = bool(maker['id']) and maker['id'] == ik['id']
                if d['scope'] == 'eigen' and not mijn:
                    continue
                d.update(id=it['id'], modified=it.get('lastModifiedDateTime') or '', owner=maker['name'], mine=mijn,
                         by=((it.get('lastModifiedBy') or {}).get('user') or {}).get('displayName') or '')
                uit.append(d)
            return uit, 'sharepoint'
        except Exception as e:  # noqa: BLE001 - geen rechten (nog niet opgezet): lokaal
            log.info('Automatisering: gedeelde opslag niet beschikbaar (%s), lokaal gebruikt', str(e)[:200])
            return [{**d, 'scope': 'eigen', 'mine': True} for d in (lokaal.lees(LOKAAL, {}) or {}).values()], 'lokaal'

    def _bestaand(self, g: Graph, site: str, lid: str, did: str) -> tuple[dict, dict]:
        it = g.get(f'/sites/{site}/lists/{lid}/items/{did}?$expand=fields($select=Definitie)')
        try:
            d = json.loads((it.get('fields') or {}).get('Definitie') or '{}')
        except ValueError:
            d = {}
        return d, self._maker(it)

    def opslaan(self, c: Ctx, d: dict) -> tuple[dict, str]:
        schoon = {k: d.get(k) for k in ('name', 'description', 'inputs', 'steps')}
        schoon['scope'] = 'eigen' if d.get('scope') == 'eigen' else 'team'
        try:
            g, site, lid = self._lijst(c)
            ik = self._ik(g)
            velden = {'Title': schoon['name'], 'Definitie': json.dumps(schoon, ensure_ascii=False)}
            if d.get('id') and not str(d['id']).startswith(('lokaal-', 'sjabloon-')):
                oud, maker = self._bestaand(g, site, lid, str(d['id']))
                van_mij = maker['id'] == ik['id']
                if oud.get('scope') == 'eigen' and not van_mij:
                    raise ApiFout('Dit is een eigen proces van een collega; dat kun je niet wijzigen. Maak een kopie.')
                if schoon['scope'] == 'eigen' and oud.get('scope') != 'eigen' and not van_mij:
                    raise ApiFout(f"Alleen {maker['name'] or 'de maker'} kan dit teamproces naar eigen processen verplaatsen. Maak een kopie voor jezelf.")
                g.patch(f"/sites/{site}/lists/{lid}/items/{d['id']}/fields", velden)
                return {**schoon, 'id': d['id'], 'mine': van_mij, 'owner': maker['name']}, 'sharepoint'
            it = g.post(f'/sites/{site}/lists/{lid}/items', {'fields': velden})
            return {**schoon, 'id': it['id'], 'mine': True, 'owner': ik['name']}, 'sharepoint'
        except ApiFout:
            raise
        except Exception as e:  # noqa: BLE001
            log.info('Automatisering: opslaan in SharePoint niet gelukt (%s), lokaal', str(e)[:200])
            alle = lokaal.lees(LOKAAL, {}) or {}
            did = d.get('id') if str(d.get('id') or '').startswith('lokaal-') else f'lokaal-{uuid.uuid4().hex[:10]}'
            alle[did] = {**schoon, 'scope': 'eigen', 'id': did, 'modified': datetime.now().strftime('%Y-%m-%dT%H:%M')}
            lokaal.schrijf(LOKAAL, alle)
            return {**alle[did], 'mine': True}, 'lokaal'

    def verwijderen(self, c: Ctx, did: str) -> None:
        if did.startswith('lokaal-'):
            alle = lokaal.lees(LOKAAL, {}) or {}
            alle.pop(did, None)
            lokaal.schrijf(LOKAAL, alle)
            return
        g, site, lid = self._lijst(c)
        oud, maker = self._bestaand(g, site, lid, did)
        if oud.get('scope') == 'eigen' and maker['id'] != self._ik(g)['id']:
            raise ApiFout('Dit is een eigen proces van een collega; dat kun je niet verwijderen.')
        g.delete(f'/sites/{site}/lists/{lid}/items/{did}')


OPSLAG = Opslag()


@api('auto.blokken')
def auto_blokken(c: Ctx, b: dict) -> dict:
    return {'blocks': [{k: v for k, v in x.items() if k != 'fn'} for x in BLOKKEN.values()], 'templates': SJABLONEN,
            'filters': list(FILTERS)}


@api('auto.lijst')
def auto_lijst(c: Ctx, b: dict) -> dict:
    l, waar = OPSLAG.lijst(c)
    l.sort(key=lambda d: str(d.get('name') or '').lower())
    return {'processes': l, 'storage': waar}


@api('auto.opslaan')
def auto_opslaan(c: Ctx, b: dict) -> dict:
    d = b.get('process') or {}
    if not str(d.get('name') or '').strip():
        raise ApiFout('Geef het proces een naam.')
    onbekend = [s.get('block') for s in _alle_stappen(d.get('steps') or []) if s.get('block') not in BLOKKEN]
    if onbekend:
        raise ApiFout(f"Onbekende bouwsteen: {', '.join(map(str, onbekend))}")
    uit, waar = OPSLAG.opslaan(c, d)
    c.L(f"Proces '{d['name']}' opgeslagen" + ((" als teamproces (zichtbaar voor alle collega's)." if uit.get('scope') == 'team' else ' bij je eigen processen.')
                                             if waar == 'sharepoint' else ' op deze computer (gedeelde opslag nog niet beschikbaar).'))
    return {'process': uit, 'storage': waar}


@api('auto.verwijderen')
def auto_verwijderen(c: Ctx, b: dict) -> dict:
    OPSLAG.verwijderen(c, str(b['id']))
    c.L('Proces verwijderd.')
    return {}


# ======================================================================================================
# Uitvoeren
# ======================================================================================================
_RUNS: dict[str, dict] = {}
_rlock = threading.Lock()


def voeren(cx: Ctx, stappen: list[dict], vars_: dict, statussen: list[dict] | None = None, pad: str = '') -> str:
    """Stappen uitvoeren (ook binnen 'als/anders' en 'voor elk'). Geeft '' (klaar), 'fout' (gestopt door een fout) of 'stop' terug.
    Uitkomsten van stappen op het hoogste niveau heten stap1, stap2 ...; binnen een tak via de eigen naam (alias) van de stap."""
    gestopt = ''
    for n, s in enumerate(stappen, start=1):
        st = statussen[n - 1] if statussen is not None and n - 1 < len(statussen) else {'status': 'wachten', 'melding': ''}
        label = f'{pad}{n}'
        if gestopt:
            st['status'] = 'overgeslagen'
            continue
        if not voorwaarde_ok(s.get('when'), vars_):
            st['status'], st['melding'] = 'overgeslagen', 'Voorwaarde niet van toepassing'
            continue
        meta = BLOKKEN.get(s.get('block'))
        if not meta:
            st['status'], st['melding'] = 'fout', 'Onbekende bouwsteen'
            gestopt = 'fout'
            continue
        st['status'] = 'bezig'
        voor = len(cx.log)
        try:
            p = {k: invullen(v, vars_) for k, v in (s.get('params') or {}).items()}
            for f in meta['fields']:
                if f.get('required') and not str(p.get(f['key']) or '').strip():
                    raise ApiFout(f"'{f['label']}' is leeg.")
            uit = meta['fn'](cx, p) or {}
            if not pad:
                vars_[f'stap{n}'] = uit
            if s.get('alias'):
                vars_[str(s['alias']).lower()] = uit
            kinderen = s.get('children') or {}
            extra = ''
            if meta['branches'] == ['ja', 'nee']:
                tak = 'ja' if uit.get('waar') else 'nee'
                r = voeren(cx, kinderen.get(tak) or [], vars_, None, f'{label}.{tak}.')
                extra = f" → tak '{tak}' ({len(kinderen.get(tak) or [])} stap(pen))"
                if r == 'fout':
                    raise ApiFout(f"Een stap in tak '{tak}' is mislukt.")
                if r == 'stop':
                    raise Stoppen()
            elif meta['branches'] == ['stappen']:
                lijst_ = uit.get('items') or []
                for i, x in enumerate(lijst_, start=1):
                    vars_['item'], vars_['index'] = x, i
                    r = voeren(cx, kinderen.get('stappen') or [], vars_, None, f'{label}.{i}.')
                    if r == 'stop':
                        raise Stoppen()
                    if r == 'fout' and s.get('onError') != 'continue':
                        raise ApiFout(f"Mislukt bij '{x}'.")
                extra = f' → {len(lijst_)} keer uitgevoerd'
            st['status'] = 'ok'
            st['melding'] = (' '.join(cx.log[voor:])[-380:] + extra).strip()
        except Stoppen as e:
            st['status'], st['melding'] = 'ok', str(e) or 'Proces gestopt.'
            cx.L(st['melding'])
            gestopt = 'stop'
        except Exception as e:  # noqa: BLE001
            st['status'], st['melding'] = 'fout', str(e)[:400]
            cx.L(f"FOUT stap {label} ({meta['name']}): {e}")
            if s.get('onError') != 'continue':
                gestopt = 'fout'
    return gestopt


def _alle_stappen(stappen: list[dict]):
    for s in stappen or []:
        yield s
        for tak in (s.get('children') or {}).values():
            yield from _alle_stappen(tak)


def _klant_openen(staat, tid: str, naam: str) -> Tenant:
    with staat._slot(tid):
        t = staat.tenants.get(tid)
        if t is None:
            t = Tenant(staat.auth, tid, naam)
            t.openen()
            with staat.lock:
                staat.tenants[tid] = t
        return t


@api('auto.start')
def auto_start(c: Ctx, b: dict) -> dict:
    """Proces uitvoeren voor de gekozen klanten en invoerregels (elke klant x elke regel is één uitvoering)."""
    d = b.get('process') or {}
    stappen = list(d.get('steps') or [])
    if not stappen:
        raise ApiFout('Het proces heeft nog geen stappen.')
    klanten = [k for k in b.get('customers') or [] if k.get('id')]
    if not klanten:
        raise ApiFout('Kies minimaal één klant.')
    rijen = [r for r in b.get('rows') or [{}] if isinstance(r, dict)] or [{}]
    for inv in d.get('inputs') or []:
        if inv.get('required'):
            leeg = [i + 1 for i, r in enumerate(rijen) if not str(r.get(inv['key']) or inv.get('default') or '').strip()]
            if leeg:
                raise ApiFout(f"Vul '{inv.get('label') or inv['key']}' in" + (f' (regel {", ".join(map(str, leeg))}).' if len(rijen) > 1 else '.'))
    rid = uuid.uuid4().hex[:12]
    items = []
    for k in klanten:
        for i, r in enumerate(rijen):
            items.append({'klant': k['id'], 'klantnaam': k.get('name') or k['id'], 'regel': i + 1, 'invoer': r, 'status': 'wachten',
                          'stappen': [{'id': s.get('id'), 'naam': BLOKKEN.get(s.get('block'), {}).get('name', s.get('block')), 'status': 'wachten',
                                       'melding': ''} for s in stappen], 'rapport': [], 'log': []})
    run = {'id': rid, 'naam': d.get('name') or 'Proces', 'bezig': True, 'items': items, 'start': datetime.now().strftime('%Y-%m-%d %H:%M')}
    with _rlock:
        _RUNS[rid] = run
    staat = c.staat

    def een(item: dict) -> None:
        item['status'] = 'bezig'
        try:
            t = _klant_openen(staat, item['klant'], item['klantnaam'])
        except Exception as e:  # noqa: BLE001
            item['status'], item['fout'] = 'fout', f'Klant openen lukte niet: {e}'
            for s in item['stappen']:
                s['status'] = 'overgeslagen'
            return
        vars_: dict[str, Any] = {str(k).lower(): v for k, v in (item['invoer'] or {}).items()}
        for inv in d.get('inputs') or []:
            vars_.setdefault(inv['key'].lower(), inv.get('default') or '')
            if not str(vars_.get(inv['key'].lower()) or '').strip() and inv.get('default'):
                vars_[inv['key'].lower()] = inv['default']
        vars_.update(klant=t.naam, klantdomein=t.standaard_domein, klantid=t.id, datum=datetime.now().strftime('%d-%m-%Y'))
        cx = Ctx(staat, f"auto:{d.get('name')}", t.id)
        cx.rapport = []   # type: ignore[attr-defined]
        voeren(cx, stappen, vars_, item['stappen'])
        item['rapport'] = cx.rapport
        item['log'] = cx.log
        item['status'] = 'fout' if any(x['status'] == 'fout' for x in item['stappen']) else 'ok'

    def alles() -> None:
        try:
            # Per klant na elkaar (stappen bouwen op elkaar voort); klanten tegelijk (3)
            per_klant: dict[str, list[dict]] = {}
            for it in items:
                per_klant.setdefault(it['klant'], []).append(it)
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix='auto') as ex:
                list(ex.map(achtergrond_fn(lambda l: [een(x) for x in l]), per_klant.values()))
        finally:
            run['bezig'] = False
            run['eind'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            log.info("Automatisering '%s': %d uitvoering(en) klaar", run['naam'], len(items))
    threading.Thread(target=alles, daemon=True, name=f'auto-{rid}').start()
    c.staat.activiteit.add('-', 'auto.start', f"Proces '{run['naam']}' gestart voor {len(klanten)} klant(en).")
    return _run_status(rid)


def _run_status(rid: str) -> dict:
    r = _RUNS.get(rid)
    if not r:
        return {'id': rid, 'bezig': False, 'onbekend': True}
    return {**r, 'items': [{k: v for k, v in it.items() if k != 'invoer'} | {'invoer': {k: ('••••' if 'wachtwoord' in k.lower() else v)
                                                                                        for k, v in (it.get('invoer') or {}).items()}}
                           for it in r['items']]}


@api('auto.status')
def auto_status(c: Ctx, b: dict) -> dict:
    return _run_status(str(b.get('id') or ''))
