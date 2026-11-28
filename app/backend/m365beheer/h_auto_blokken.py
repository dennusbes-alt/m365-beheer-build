"""Extra bouwstenen voor Automatisering (v2.29): logica (als/anders, voor elk, variabele, stoppen), groepen/Teams/gasten,
meer gebruikers-, Exchange- en Intune-acties, Autotask en IT Glue. Registreert zich in h_automatisering.BLOKKEN."""
from __future__ import annotations

from .clients import ApiFout
from .context import Ctx
from .h_automatisering import (G0, G1, G2, G3, G5, G6, G7, GEBRUIKER, FILTERS, Stoppen, V, _api, _gebruiker, _groep, _ja, _lijst,
                               blok, voorwaarde_ok, _apparaten_van)

OPS = ['is ingevuld', 'is leeg', 'is gelijk aan', 'is niet gelijk aan', 'bevat', 'is ja', 'is nee']
_OP = {'is ingevuld': 'gevuld', 'is leeg': 'leeg', 'is gelijk aan': 'gelijk', 'is niet gelijk aan': 'niet', 'bevat': 'bevat', 'is ja': 'ja', 'is nee': 'nee'}


# ---------------------------------------------------------------- Logica
@blok('logica.als', G0, 'Als … dan / anders', 'Kiest een tak: stappen bij "ja" of bij "nee". Bijvoorbeeld: als afdeling is gelijk aan Verkoop.', [
    V('waarde', 'Als', placeholder='{{afdeling}}', required=True), V('op', 'Voorwaarde', 'keuze', opties=OPS, default='is gelijk aan'),
    V('vergelijk', 'Waarde', placeholder='Verkoop')], ['waar'], takken=['ja', 'nee'])
def b_als(c: Ctx, p: dict) -> dict:
    waar = voorwaarde_ok({'veld': 'x', 'op': _OP.get(p.get('op') or '', 'gelijk'), 'waarde': p.get('vergelijk') or ''}, {'x': p.get('waarde') or ''})
    c.L(f"Voorwaarde: '{p.get('waarde')}' {p.get('op')} '{p.get('vergelijk') or ''}' → {'ja' if waar else 'nee'}.")
    return {'waar': 'ja' if waar else ''}


@blok('logica.voorelk', G0, 'Voor elk …', 'Herhaalt de stappen erin voor elk item uit een lijst (komma of nieuwe regel). Gebruik {{item}} en {{index}}.', [
    V('lijst', 'Lijst', 'tekstvak', placeholder='{{groepen}}', required=True)], ['aantal'], takken=['stappen'])
def b_voorelk(c: Ctx, p: dict) -> dict:
    items = _lijst(p['lijst'])
    c.L(f'{len(items)} item(s) in de lijst.')
    return {'items': items, 'aantal': len(items)}


@blok('logica.variabele', G0, 'Variabele instellen', 'Bewaart een waarde onder een eigen naam (bijv. {{mijn.waarde}} met de stapnaam "mijn").', [
    V('waarde', 'Waarde', 'tekstvak', required=True)], ['waarde'])
def b_variabele(c: Ctx, p: dict) -> dict:
    return {'waarde': p['waarde']}


@blok('logica.stop', G0, 'Stoppen', 'Beëindigt het proces netjes met een melding (geen fout). Handig binnen een "als"-tak.', [
    V('melding', 'Melding', placeholder='Niets te doen: gebruiker bestaat al.')])
def b_stop(c: Ctx, p: dict) -> dict:
    raise Stoppen(p.get('melding') or 'Proces gestopt.')


# ---------------------------------------------------------------- Gebruikers (extra)
@blok('gebruiker.verwijderen', G1, 'Gebruiker verwijderen', 'Zet het account in de prullenbak van Entra ID (30 dagen terug te halen).', [GEBRUIKER])
def b_gebruiker_verwijderen(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    c.g.delete(f"/users/{u['id']}")
    c.t.weg('users', 'skus')
    c.L(f"{u['userPrincipalName']} verwijderd (30 dagen terug te halen).")
    return {}


@blok('gebruiker.onedrive', G1, 'OneDrive klaarzetten', 'Maakt de OneDrive van de gebruiker alvast aan, zodat bestanden direct gedeeld kunnen worden.', [GEBRUIKER])
def b_onedrive(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    _api(c, 'user.onedrive', {'id': u['id'], 'upn': u['userPrincipalName'], 'provision': True})
    return {}


@blok('gast.uitnodigen', G5, 'Gast uitnodigen', 'Nodigt een externe gebruiker uit als gast (bijv. leverancier of accountant).', [
    V('mail', 'E-mailadres van de gast', required=True), V('naam', 'Naam'), V('bericht', 'Uitnodigingsbericht versturen', 'vink', default=True)], ['id', 'upn'])
def b_gast(c: Ctx, p: dict) -> dict:
    r = c.g.post('/invitations', {'invitedUserEmailAddress': p['mail'], 'invitedUserDisplayName': p.get('naam') or p['mail'],
                                  'inviteRedirectUrl': 'https://myapps.microsoft.com', 'sendInvitationMessage': _ja(p.get('bericht', True))})
    u = r.get('invitedUser') or {}
    c.L(f"Gast {p['mail']} uitgenodigd.")
    c.t.weg('users')
    return {'id': u.get('id') or '', 'upn': p['mail']}


# ---------------------------------------------------------------- Groepen, Teams
@blok('groep.aanmaken', G5, 'Groep aanmaken', 'Microsoft 365-groep (met mailbox en SharePoint), beveiligingsgroep of distributielijst.', [
    V('soort', 'Soort', 'keuze', opties=['Microsoft 365-groep', 'Beveiligingsgroep', 'Distributielijst'], default='Microsoft 365-groep'),
    V('naam', 'Naam', required=True), V('alias', 'Adres (voor de @)'), V('domein', 'Domein', placeholder='{{klantdomein}}')], ['mail'])
def b_groep_aanmaken(c: Ctx, p: dict) -> dict:
    soort = {'Microsoft 365-groep': 'M365', 'Beveiligingsgroep': 'Beveiliging', 'Distributielijst': 'Distributielijst'}.get(p.get('soort') or '', 'M365')
    alias = FILTERS['alias'](str(p.get('alias') or p['naam']))
    domein = p.get('domein') or c.t.standaard_domein
    _api(c, 'group.create', {'kind': soort, 'name': p['naam'], 'alias': alias, 'domain': domein})
    c.t.weg('groepen')
    return {'mail': f'{alias}@{domein}'}


@blok('team.lid', G5, 'Toevoegen aan een team', 'Voegt de gebruiker toe aan een Microsoft Teams-team (lid of eigenaar).', [
    GEBRUIKER, V('team', 'Team (naam)', required=True), V('rol', 'Rol', 'keuze', opties=['lid', 'eigenaar'], default='lid')])
def b_team_lid(c: Ctx, p: dict) -> dict:
    u = _gebruiker(c, p['gebruiker'])
    g = _groep(c, p['team'])
    c.g.post(f"/groups/{g['id']}/members/$ref", {'@odata.id': f"https://graph.microsoft.com/v1.0/directoryObjects/{u['id']}"}) \
        if (p.get('rol') or 'lid') == 'lid' else c.g.post(f"/groups/{g['id']}/owners/$ref", {'@odata.id': f"https://graph.microsoft.com/v1.0/directoryObjects/{u['id']}"})
    c.L(f"{u['userPrincipalName']} is {p.get('rol') or 'lid'} van {g['name']}.")
    return {}


# ---------------------------------------------------------------- Exchange (extra)
@blok('postvak.archief', G2, 'Online archief aanzetten', 'Zet het online archief (In-Place Archive) aan voor het postvak.', [GEBRUIKER])
def b_archief(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    c.x.run('Enable-Mailbox', Identity=upn, Archive=True)
    c.L(f'Online archief aangezet voor {upn}.')
    return {}


@blok('postvak.verbergen', G2, 'Verbergen in het adresboek', 'Het postvak verschijnt niet meer in de adreslijst (bijv. na uitdiensttreding).', [
    GEBRUIKER, V('verbergen', 'Verbergen', 'vink', default=True)])
def b_verbergen(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    c.x.run('Set-Mailbox', Identity=upn, HiddenFromAddressListsEnabled=_ja(p.get('verbergen', True)))
    c.L(f"{upn} {'verborgen in' if _ja(p.get('verbergen', True)) else 'weer zichtbaar in'} het adresboek.")
    return {}


# ---------------------------------------------------------------- Intune (extra)
@blok('apparaten.actie', G3, 'Actie op apparaten van gebruiker', 'Herstarten, buiten gebruik stellen (bedrijfsgegevens weg) of verwijderen uit Intune.', [
    GEBRUIKER, V('actie', 'Actie', 'keuze', opties=['herstarten', 'buiten gebruik stellen', 'verwijderen uit Intune'], default='herstarten')], ['aantal'])
def b_apparaten_actie(c: Ctx, p: dict) -> dict:
    upn = _gebruiker(c, p['gebruiker'])['userPrincipalName']
    l = _apparaten_van(c, upn)
    actie = p.get('actie') or 'herstarten'
    for d in l:
        try:
            if actie == 'herstarten':
                c.g.post(f"/deviceManagement/managedDevices/{d['id']}/rebootNow")
            elif actie == 'buiten gebruik stellen':
                c.g.post(f"/deviceManagement/managedDevices/{d['id']}/retire")
            else:
                c.g.delete(f"/deviceManagement/managedDevices/{d['id']}")
        except ApiFout as e:
            c.L(f"FOUT {d.get('deviceName')}: {e}")
    c.t.weg('apparaten')
    c.L(f"{actie.capitalize()}: {len(l)} apparaat/apparaten van {upn}.")
    return {'aantal': len(l)}


# ---------------------------------------------------------------- Autotask
def _bedrijf(c: Ctx) -> int:
    from . import h_autotask as A
    kl = A._klanten().get(c.t.id)
    if not kl:
        raise ApiFout('Deze klant is nog niet gekoppeld aan een Autotask-bedrijf (ticketbalk > klant koppelen).')
    return int(kl['companyId'])


@blok('at.ticket', G6, 'Autotask: ticket aanmaken', 'Maakt een ticket bij deze klant op jouw naam. De uitkomst (nummer, id) is te gebruiken in volgende stappen.', [
    V('titel', 'Onderwerp', required=True, placeholder='Nieuwe medewerker {{voornaam}} {{achternaam}}'), V('omschrijving', 'Beschrijving', 'tekstvak'),
    V('minuten', 'Direct tijd boeken (minuten, 0 = niet)', 'getal', default='0')], ['id', 'nummer'])
def b_at_ticket(c: Ctx, p: dict) -> dict:
    from . import h_autotask as A
    at = A._at()
    ik, inst = A._ik(at), A._instellingen()
    t = A._nieuw_ticket(at, _bedrijf(c), p['titel'][:250], p.get('omschrijving') or p['titel'], ik, inst)
    m = int(float(p.get('minuten') or 0))
    if m > 0:
        A._tijdregel(at, {'id': t['id'], 'assignedResourceroleID': t.get('assignedResourceroleID')}, ik, m, p.get('omschrijving') or p['titel'], inst)
    c.L(f"Autotask-ticket {t['number']} aangemaakt" + (f' ({m} minuten geboekt).' if m > 0 else '.'))
    return {'id': t['id'], 'nummer': t['number']}


@blok('at.notitie', G6, 'Autotask: notitie op ticket', 'Zet een notitie op een ticket, bijvoorbeeld een samenvatting van wat het proces heeft gedaan.', [
    V('ticket', 'Ticket-id', required=True, placeholder='{{stap1.id}}'), V('titel', 'Titel', default='Automatisering'), V('tekst', 'Tekst', 'tekstvak', required=True)])
def b_at_notitie(c: Ctx, p: dict) -> dict:
    from . import h_autotask as A
    A._notitie(A._at(), int(p['ticket']), p.get('titel') or 'Automatisering', p['tekst'], A._instellingen())
    c.L(f"Notitie gezet op ticket {p['ticket']}.")
    return {}


@blok('at.tijd', G6, 'Autotask: tijd boeken', 'Boekt tijd op een ticket op jouw naam.', [
    V('ticket', 'Ticket-id', required=True, placeholder='{{stap1.id}}'), V('minuten', 'Minuten', 'getal', default='15', required=True),
    V('tekst', 'Omschrijving', 'tekstvak', required=True)])
def b_at_tijd(c: Ctx, p: dict) -> dict:
    from . import h_autotask as A
    at = A._at()
    t = at.req('GET', f"Tickets/{int(p['ticket'])}").get('item') or {}
    A._tijdregel(at, {'id': int(p['ticket']), 'assignedResourceroleID': t.get('assignedResourceRoleID') or t.get('assignedResourceroleID')},
                 A._ik(at), int(float(p['minuten'])), p['tekst'], A._instellingen())
    c.L(f"{p['minuten']} minuten geboekt op ticket {t.get('ticketNumber') or p['ticket']}.")
    return {}


@blok('at.status', G6, 'Autotask: ticketstatus wijzigen', 'Zet een ticket op een andere status, bijvoorbeeld afgerond.', [
    V('ticket', 'Ticket-id', required=True, placeholder='{{stap1.id}}'), V('status', 'Status (naam)', required=True, placeholder='Complete')])
def b_at_status(c: Ctx, p: dict) -> dict:
    from . import h_autotask as A
    at = A._at()
    st = next((x['value'] for x in at.picklists('Tickets').get('status', []) if str(x['label']).lower() == p['status'].strip().lower()), None)
    if st is None:
        raise ApiFout(f"Status '{p['status']}' bestaat niet in Autotask.")
    at.req('PATCH', 'Tickets', {'id': int(p['ticket']), 'status': st})
    c.L(f"Ticket {p['ticket']} op status {p['status']} gezet.")
    return {}


@blok('at.contact', G6, 'Autotask: contactpersoon aanmaken', 'Maakt de nieuwe medewerker aan als contactpersoon bij het Autotask-bedrijf (bestaat het e-mailadres al, dan die).', [
    V('voornaam', 'Voornaam', required=True, placeholder='{{voornaam}}'), V('achternaam', 'Achternaam', required=True, placeholder='{{achternaam}}'),
    V('mail', 'E-mailadres', required=True, placeholder='{{stap1.upn}}'), V('telefoon', 'Telefoon')], ['id'])
def b_at_contact(c: Ctx, p: dict) -> dict:
    r = _api(c, 'at.contact.nieuw', {'companyId': _bedrijf(c), 'firstName': p['voornaam'], 'lastName': p['achternaam'], 'email': p['mail'], 'phone': p.get('telefoon') or ''})
    return {'id': (r.get('contact') or {}).get('id')}


@blok('at.contact.uit', G6, 'Autotask: contactpersoon deactiveren', 'Zet de contactpersoon met dit e-mailadres op inactief (bijv. bij uitdiensttreding).', [
    V('mail', 'E-mailadres', required=True, placeholder='{{medewerker}}')])
def b_at_contact_uit(c: Ctx, p: dict) -> dict:
    from . import h_autotask as A
    at = A._at()
    r = at.query('Contacts', [{'op': 'eq', 'field': 'companyID', 'value': _bedrijf(c)}, {'op': 'eq', 'field': 'emailAddress', 'value': p['mail']}], ['id'], 5)
    if not r:
        c.L(f"Geen contactpersoon met {p['mail']} gevonden.")
        return {}
    for x in r:
        at.req('PATCH', f"Companies/{_bedrijf(c)}/Contacts", {'id': x['id'], 'isActive': 0})
    A.lijst_wissen(_bedrijf(c), ('c',))
    c.L(f"Contactpersoon {p['mail']} gedeactiveerd in Autotask.")
    return {}


# ---------------------------------------------------------------- IT Glue
@blok('itglue.document', G7, 'IT Glue: documentatie vastleggen', 'Legt een werkinstructie of opleverdocument vast bij deze klant in IT Glue.', [
    V('titel', 'Titel', required=True, placeholder='Inrichting {{klant}} {{datum}}'), V('probleem', 'Aanleiding / vraag', 'tekstvak'),
    V('oplossing', 'Wat is er gedaan / hoe is het ingesteld', 'tekstvak', required=True), V('trefwoorden', 'Trefwoorden')], ['url'])
def b_itglue(c: Ctx, p: dict) -> dict:
    from .h_itglue import vastleggen
    r = vastleggen(c.t.naam, p['titel'], p.get('probleem') or '', p['oplossing'], '', p.get('trefwoorden') or '')
    c.L(f"Vastgelegd in IT Glue bij {r['org']}.")
    return {'url': r.get('url') or ''}
