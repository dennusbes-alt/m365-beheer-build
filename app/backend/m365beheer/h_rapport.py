"""NEN 7510-rapport voor de klant (PDF): wat er technisch is ingericht, in begrijpelijke taal, en wat de klant zelf nog regelt.

Het rapport wordt live opgebouwd uit dezelfde controles als het scherm NEN 7510 (h_readiness) en opgeslagen in de map
Downloads van de beheerder. Er wordt niets anders bewaard.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .context import Ctx, api
from .h_readiness import _rapport

MAP = Path(__file__).parent / 'rapport'
NAVY, BLAUW, CYAAN, LEI = (0, 63, 107), (27, 126, 169), (0, 174, 239), (50, 56, 65)
GROEN, ORANJE, ROOD, GRIJS = (27, 138, 85), (168, 100, 0), (192, 57, 43), (138, 151, 165)
STATUS = {'ok': ('Ingericht', GROEN), 'warn': ('Aandachtspunt', ORANJE), 'err': ('Niet ingericht', ROOD), 'unknown': ('Niet vast te stellen', GRIJS)}
MAANDEN = ['januari', 'februari', 'maart', 'april', 'mei', 'juni', 'juli', 'augustus', 'september', 'oktober', 'november', 'december']

# Per controle: wat het betekent voor de klant (begrijpelijke taal, zonder vakjargon)
UITLEG = {
    'mfa_reg': 'Iedere medewerker logt in met een wachtwoord én een tweede stap, zoals een melding op de telefoon. Een gestolen wachtwoord is daardoor alleen niet genoeg om bij uw gegevens te komen.',
    'mfa_enf': 'De tweede inlogstap is verplicht gesteld voor iedereen. Medewerkers kunnen hem niet overslaan of uitzetten.',
    'legacy': 'Oude manieren van inloggen (bijvoorbeeld oude mailprogramma\'s die alleen een wachtwoord kennen) zijn geblokkeerd, zodat aanvallers de tweede inlogstap niet kunnen omzeilen.',
    'admins_mfa': 'Accounts met beheerrechten zijn extra goed beveiligd met een sterke tweede inlogstap. Dit zijn de accounts waar aanvallers het eerst naar zoeken.',
    'ga': 'Het aantal accounts met de hoogste beheerrechten is beperkt gehouden, maar er is wel een reserve als één account niet beschikbaar is.',
    'breakglass': 'Er is een noodaccount waarmee de omgeving altijd bereikbaar blijft, ook als de normale aanmelding door een storing of fout niet werkt.',
    'admin_apart': 'Beheerwerk gebeurt met aparte beheeraccounts. Dagelijks werk (mail, internet) gebeurt met een gewoon account, zodat een besmette mail geen beheerrechten kan misbruiken.',
    'consent': 'Medewerkers kunnen apps van derden niet zelf toegang geven tot hun mail of bestanden. Daarmee wordt voorkomen dat een nep-app via een slimme vraag gegevens wegsluist.',
    'apps': 'Alleen beheerders kunnen koppelingen (apps) registreren in uw omgeving.',
    'inactief': 'Accounts van medewerkers die niet meer actief zijn, staan niet meer open. Zo blijven er geen vergeten toegangsdeuren bestaan.',
    'gasten': 'Externe gasten (bijv. leveranciers) die lang niet meer actief zijn, worden opgeruimd, zodat alleen wie het nodig heeft toegang houdt.',
    'intune': 'Alle werkplekken worden centraal beheerd. Daardoor weten we welke apparaten er zijn en kunnen we beveiligingsinstellingen op afstand afdwingen.',
    'cpol': 'Er zijn minimumeisen voor apparaten vastgelegd (zoals versleuteling en updates) en de apparaten voldoen daaraan.',
    'bitlocker': 'De harde schijven van de laptops en pc\'s zijn versleuteld. Raakt een apparaat kwijt of wordt het gestolen, dan zijn de gegevens erop niet te lezen. De herstelsleutels zijn veilig bewaard.',
    'os': 'Alle apparaten draaien een versie van Windows (of ander besturingssysteem) die nog beveiligingsupdates van de fabrikant krijgt.',
    'patch': 'De apparaten krijgen de nieuwste beveiligingsupdates, zodat bekende lekken gedicht zijn.',
    'stale': 'Het overzicht van apparaten is actueel: oude apparaten die niet meer in gebruik zijn, zijn opgeruimd.',
    'spf': 'Uw domein vertelt andere mailservers welke servers namens u mogen mailen. Dat maakt het moeilijker om mail uit uw naam te vervalsen.',
    'dkim': 'Uitgaande mail krijgt een digitale handtekening, zodat ontvangers kunnen controleren dat de mail echt van u komt en onderweg niet is aangepast.',
    'dmarc': 'Mail die zich voordoet als uw organisatie maar niet van u komt, wordt door ontvangers tegengehouden. Dit beschermt uw patiënten en relaties tegen nepmail uit uw naam.',
    'extern': 'Mail van buiten de organisatie krijgt het label "Extern". Medewerkers zien zo direct dat een bericht niet van een collega komt, wat helpt tegen phishing.',
    'forward': 'Mail kan niet automatisch naar externe adressen (zoals een privé-Gmail) worden doorgestuurd. Zo verlaten (medische) gegevens niet ongemerkt de organisatie.',
    'bijlagen': 'Gevaarlijke bijlagen, zoals programma\'s en scripts, worden tegengehouden voordat ze de medewerker bereiken.',
    'sp': 'Bestanden in SharePoint en Teams kunnen niet meer met een openbare link (voor iedereen) worden gedeeld. Externen moeten zich aanmelden om iets te openen.',
    'od': 'Ook bestanden in OneDrive kunnen niet met een openbare link worden gedeeld.',
    'linktype': 'Bij het delen van een bestand is de standaardkeuze "alleen specifieke personen" en "alleen lezen". Zo wordt niet per ongeluk te breed gedeeld.',
    'openbaar': 'Teams en groepen zijn niet openbaar binnen de organisatie: alleen leden zien de inhoud.',
    'labels': 'Er zijn labels om informatie te classificeren (bijv. Intern, Vertrouwelijk, Medisch), zodat duidelijk is hoe met een document of mail moet worden omgegaan.',
    'ual': 'Alle belangrijke activiteiten (aanmeldingen, beheeracties, mail- en bestandsactiviteit) worden vastgelegd in een auditlog. Bij een incident is te achterhalen wat er is gebeurd.',
    'mbaudit': 'Ook binnen de mailboxen wordt vastgelegd wie berichten opent, verplaatst of verwijdert.',
}

# Organisatorische onderdelen (buiten de technische scope): wat de klant zelf regelt
ZELF = {
    'Risicoanalyse': 'Breng in kaart welke patiënt- en persoonsgegevens u verwerkt, welke risico\'s daarbij horen en welke maatregelen u neemt.',
    'Informatiebeveiligingsbeleid': 'Een door de directie vastgesteld beleid dat beschrijft hoe uw organisatie met informatiebeveiliging omgaat.',
    'Rollen en verantwoordelijkheden': 'Leg vast wie binnen uw organisatie eigenaar is van informatiebeveiliging en wie waarvoor verantwoordelijk is.',
    'Acceptabel gebruik': 'Gedragsregels voor medewerkers (bijv. over wachtwoorden, privégebruik en het delen van gegevens), door iedereen ondertekend.',
    'Autorisatieprocedure': 'Beschrijf wie welke toegang krijgt, wie dat goedkeurt en hoe vaak de rechten worden gecontroleerd.',
    'In- en uitdienstprocedure': 'Afspraken over het aanmaken en tijdig intrekken van accounts en apparaten bij in- en uitdiensttreding.',
    'Incident- en datalekprocedure': 'Hoe meldt een medewerker een incident, wie beoordeelt het en wanneer meldt u een datalek bij de Autoriteit Persoonsgegevens (binnen 72 uur).',
    'Verwerkersovereenkomsten': 'Overeenkomsten met leveranciers die persoonsgegevens voor u verwerken (bijv. Microsoft, back-up, IT-dienstverlener).',
    'Bewustwording': 'Periodieke training en phishingsimulaties, zodat medewerkers risico\'s herkennen.',
    'Evaluatie': 'Een jaarlijkse evaluatie (managementreview) en periodieke controle of de maatregelen nog werken.',
}


def _nl_datum(d: datetime) -> str:
    return f'{d.day} {MAANDEN[d.month - 1]} {d.year}'


def _pdf(klant: str, r: dict, door: str) -> bytes:
    from fpdf import FPDF

    nu = datetime.now()
    controles = r['checks']
    open_ = [x for x in controles if x['status'] != 'ok']
    compleet = not open_
    h_zelf, h_verant = ('3', '4') if compleet else ('4', '5')

    class Rapport(FPDF):
        def header(self):
            if self.page_no() == 1:
                return
            self.set_font('Lato', '', 8)
            self.set_text_color(*GRIJS)
            self.cell(0, 6, f'NEN 7510 - technische maatregelen Microsoft 365 - {klant}', align='L')
            self.ln(10)

        def footer(self):
            if self.page_no() == 1:
                return
            self.set_y(-14)
            self.set_font('Lato', '', 8)
            self.set_text_color(*GRIJS)
            self.cell(0, 6, f'{_nl_datum(nu)}  |  Pagina {self.page_no()} van {{nb}}', align='R')

    p = Rapport(format='A4')
    p.set_auto_page_break(True, margin=20)
    p.set_margins(20, 18, 20)
    for stijl, bestand in (('', 'Regular'), ('B', 'Bold'), ('I', 'Regular'), ('BI', 'Bold')):
        p.add_font('Lato', stijl, str(MAP / f'Lato-{bestand}.ttf'))
    p.add_font('LatoBlack', '', str(MAP / 'Lato-Black.ttf'))
    p.alias_nb_pages()
    B = p.epw   # bruikbare breedte

    def mc(*a, **k):   # altijd terug naar de linkermarge op de volgende regel
        return p.multi_cell(*a, **{'new_x': 'LMARGIN', 'new_y': 'NEXT', **k})

    def kop(tekst: str, grootte: int = 16, kleur=NAVY, voor: int = 4):
        p.ln(voor)
        p.set_font('LatoBlack', '', grootte)
        p.set_text_color(*kleur)
        mc(B, grootte * 0.5, tekst)
        p.ln(2)

    def tekst(t: str, grootte: float = 10, kleur=LEI, stijl: str = '', h: float = 5.2):
        p.set_font('Lato', stijl, grootte)
        p.set_text_color(*kleur)
        mc(B, h, t)

    def label(t: str, kleur):
        p.set_font('Lato', 'B', 8.5)
        w = p.get_string_width(t) + 6
        p.set_fill_color(*kleur)
        p.set_text_color(255, 255, 255)
        p.cell(w, 5.5, t, fill=True, align='C')

    # ---------- Titelpagina
    p.add_page()
    p.set_fill_color(*BLAUW)
    p.rect(0, 0, 210, 92, 'F')
    p.set_fill_color(255, 255, 255)
    p.rect(20, 20, 64, 20, 'F')
    p.image(str(MAP / 'logo.png'), x=23, y=22, h=16)
    p.set_xy(20, 52)
    p.set_font('LatoBlack', '', 26)
    p.set_text_color(255, 255, 255)
    mc(B, 11, 'NEN 7510\nTechnische maatregelen Microsoft 365')
    p.set_xy(20, 104)
    p.set_font('Lato', '', 11)
    p.set_text_color(*GRIJS)
    p.cell(0, 6, 'Opgesteld voor')
    p.set_xy(20, 111)
    p.set_font('LatoBlack', '', 20)
    p.set_text_color(*NAVY)
    mc(B, 9, klant)
    p.ln(6)
    for k, v in (('Datum', _nl_datum(nu)), ('Opgesteld door', 'Justdata' + (f' ({door})' if door else '')),
                 ('Norm', 'NEN 7510-1:2024 en NEN 7510-2:2024 (beheersmaatregelen)'), ('Omgeving', 'Microsoft 365-tenant en beheerde werkplekken')):
        p.set_font('Lato', '', 10)
        p.set_text_color(*GRIJS)
        p.cell(38, 7, k)
        p.set_font('Lato', 'B', 10)
        p.set_text_color(*LEI)
        mc(B - 38, 7, v)
    p.ln(10)
    p.set_fill_color(*(GROEN if compleet else ORANJE))
    p.set_text_color(255, 255, 255)
    p.set_font('LatoBlack', '', 13)
    mc(B, 10, '  Status: alle technische maatregelen zijn ingericht' if compleet
                 else f'  Status: tussenrapportage - {len(open_)} technische punt(en) staan nog open', fill=True)

    # ---------- Samenvatting
    p.add_page()
    kop('1. Samenvatting', 18)
    if compleet:
        tekst(f'Op {_nl_datum(nu)} is de Microsoft 365-omgeving van {klant} gecontroleerd op de technische maatregelen die NEN 7510 vraagt '
              'voor informatiebeveiliging in de zorg. Alle maatregelen die binnen deze omgeving technisch kunnen worden ingericht, zijn '
              'toegepast en actief.')
        p.ln(3)
        p.set_fill_color(229, 245, 236)
        p.set_draw_color(*GROEN)
        p.set_text_color(*NAVY)
        p.set_font('Lato', 'B', 10.5)
        mc(B, 6, f'Conclusie: de Microsoft 365-omgeving van {klant} voldoet aan de technische eisen van NEN 7510 die binnen de scope van '
                     'deze opdracht vallen. Daarmee is de technische basis gelegd om NEN 7510 te behalen. Om de norm volledig te behalen, '
                     f'moet de organisatie ook de organisatorische maatregelen uit hoofdstuk {h_zelf} op orde brengen; die vallen buiten de scope '
                     'van deze opdracht.', border=1, fill=True, padding=4)
    else:
        tekst(f'Op {_nl_datum(nu)} is de Microsoft 365-omgeving van {klant} gecontroleerd op de technische maatregelen die NEN 7510 vraagt. '
              f'{len(controles) - len(open_)} van de {len(controles)} maatregelen zijn ingericht. De openstaande punten staan in hoofdstuk 3 '
              'en worden nog afgerond. Dit rapport is daarom een tussenrapportage.')
    p.ln(4)
    tekst('NEN 7510 is de Nederlandse norm voor informatiebeveiliging in de zorg. De norm vraagt om technische maatregelen (zoals '
          'beveiligd inloggen, versleuteling en logging) én organisatorische maatregelen (zoals beleid, procedures en een risicoanalyse). '
          'Dit rapport beschrijft de technische maatregelen in Microsoft 365 en op de beheerde werkplekken.')
    p.ln(4)
    kop('Overzicht per onderdeel', 12, voor=2)
    per_cat: dict[str, list] = {}
    for x in controles:
        per_cat.setdefault(x['category'], []).append(x)
    p.set_font('Lato', 'B', 9)
    p.set_fill_color(*NAVY)
    p.set_text_color(255, 255, 255)
    p.cell(B * .55, 7, '  Onderdeel', fill=True)
    p.cell(B * .25, 7, 'Maatregelen ingericht', fill=True, align='C')
    p.cell(B * .20, 7, 'Status', fill=True, align='C', new_x='LMARGIN', new_y='NEXT')
    for i, (cat, l) in enumerate(per_cat.items()):
        ok = len([x for x in l if x['status'] == 'ok'])
        p.set_fill_color(*((244, 247, 250) if i % 2 else (255, 255, 255)))
        p.set_font('Lato', '', 9.5)
        p.set_text_color(*LEI)
        p.cell(B * .55, 7, '  ' + cat, fill=True)
        p.cell(B * .25, 7, f'{ok} van {len(l)}', fill=True, align='C')
        p.set_text_color(*(GROEN if ok == len(l) else ORANJE))
        p.set_font('Lato', 'B', 9.5)
        p.cell(B * .20, 7, 'Op orde' if ok == len(l) else 'Open punten', fill=True, align='C', new_x='LMARGIN', new_y='NEXT')

    # ---------- Maatregelen per onderdeel
    p.add_page()
    kop('2. Ingerichte maatregelen', 18)
    tekst('Per onderdeel staat hieronder welke maatregel is ingericht, wat dat voor uw organisatie betekent en wat er is gemeten. '
          'Het nummer verwijst naar de beheersmaatregel in NEN 7510-2:2024.', 9.5, GRIJS)
    for cat, l in per_cat.items():
        kop(cat, 13, BLAUW, voor=5)
        for x in l:
            if p.get_y() > 245:
                p.add_page()
            p.set_draw_color(220, 228, 235)
            p.line(20, p.get_y(), 190, p.get_y())
            p.ln(2)
            y = p.get_y()
            p.set_font('Lato', 'B', 10.5)
            p.set_text_color(*NAVY)
            mc(B - 42, 5.5, x['title'] + (f"  (maatregel {x['ref']})" if x['ref'] else ''))
            y2 = p.get_y()
            p.set_xy(190 - 40, y)
            naam, kleur = STATUS.get(x['status'], STATUS['unknown'])
            label(naam, kleur)
            p.set_xy(20, max(y2, y + 6) + 1)
            tekst(UITLEG.get(x['key'], ''), 9.5)
            p.ln(1)
            tekst('Gemeten: ' + re.sub(r'\s+', ' ', x['text']), 8.5, GRIJS, h=4.5)
            p.ln(2)

    # ---------- Openstaande punten
    if open_:
        p.add_page()
        kop('3. Openstaande technische punten', 18)
        tekst('Deze punten worden nog afgerond. Zodra alles is ingericht, wordt een definitief rapport opgesteld.', 9.5, GRIJS)
        p.ln(2)
        for x in open_:
            p.set_font('Lato', 'B', 10)
            p.set_text_color(*NAVY)
            mc(B, 5.5, f"- {x['title']}" + (f" (maatregel {x['ref']})" if x['ref'] else ''))
            tekst('   ' + re.sub(r'\s+', ' ', x['text']), 9, GRIJS, h=4.6)
            p.ln(1)

    # ---------- Wat de klant zelf regelt
    p.add_page()
    kop(f'{h_zelf}. Wat u zelf nog regelt (buiten de scope)', 18)
    tekst('NEN 7510 vraagt naast technische maatregelen ook om organisatorische maatregelen. Die liggen bij uw organisatie en vallen buiten '
          'de scope van deze opdracht. Pas als ook deze onderdelen op orde en aantoonbaar zijn, kan uw organisatie NEN 7510 volledig behalen '
          '(en eventueel laten certificeren door een geaccrediteerde certificerende instelling).')
    p.ln(3)
    for kopje, uitleg in ZELF.items():
        if p.get_y() > 255:
            p.add_page()
        p.set_font('Lato', 'B', 10)
        p.set_text_color(*NAVY)
        p.cell(6, 5.5, chr(0x2022))
        mc(B - 6, 5.5, kopje)
        p.set_x(26)
        p.set_font('Lato', '', 9.5)
        p.set_text_color(*LEI)
        mc(B - 6, 5, uitleg)
        p.ln(1.5)
    if r.get('manual'):
        p.ln(2)
        tekst('Ook de volgende technische onderdelen buiten Microsoft 365 moeten aantoonbaar zijn ingericht (bijvoorbeeld door uw IT-dienstverlener): '
              + '; '.join(m['title'] for m in r['manual'] if m['category'] == 'Techniek') + '.', 9.5)

    # ---------- Verantwoording
    if p.get_y() > 220:
        p.add_page()
    kop(f'{h_verant}. Verantwoording', 14, voor=6)
    tekst(f'De controle is op {_nl_datum(nu)} rechtstreeks uitgevoerd op de Microsoft 365-omgeving (Microsoft Graph en Exchange Online) met de '
          'beheerapplicatie van Justdata. De status in dit rapport geeft de situatie op dat moment weer. Dit rapport is geen certificaat en '
          'geen formele audit: het toont aan welke technische maatregelen zijn ingericht en ondersteunt uw organisatie bij een (her)audit. '
          'Bewaar dit rapport samen met uw beleid en procedures in uw auditdossier.', 9.5)
    return bytes(p.output())


def _bestandsnaam(klant: str) -> Path:
    map_ = Path.home() / 'Downloads'
    if not map_.is_dir():
        map_ = Path.home()
    veilig = re.sub(r'[^\w\- ]+', '', klant).strip().replace(' ', '-') or 'klant'
    pad = map_ / f'NEN7510-rapport-{veilig}-{datetime.now():%Y-%m-%d}.pdf'
    n = 2
    while pad.exists():
        pad = map_ / f'NEN7510-rapport-{veilig}-{datetime.now():%Y-%m-%d}-{n}.pdf'
        n += 1
    return pad


def _openen(pad: Path) -> None:
    try:
        if sys.platform == 'win32':
            os.startfile(str(pad))  # noqa: S606 - eigen bestand openen in de standaard PDF-lezer
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(pad)])
        else:
            subprocess.Popen(['xdg-open', str(pad)])
    except Exception:  # noqa: BLE001 - niet erg: het pad staat in de melding
        pass


@api('rd.nen.pdf')
def rd_nen_pdf(c: Ctx, b: dict) -> dict:
    r = _rapport(c, 'nen')
    klant = c.t.naam or 'Klant'
    try:
        door = str((c.staat.auth.account or {}).get('username') or '')
    except Exception:  # noqa: BLE001
        door = ''
    pad = _bestandsnaam(klant)
    pad.write_bytes(_pdf(klant, r, door.split('@')[0].replace('.', ' ').title() if door else ''))
    open_ = len([x for x in r['checks'] if x['status'] != 'ok'])
    c.L(f'NEN 7510-rapport opgeslagen: {pad}' + (f' (tussenrapportage, {open_} open punten)' if open_ else ' (alle technische maatregelen ingericht)'))
    _openen(pad)
    return {'path': str(pad), 'complete': not open_, 'open': open_}
