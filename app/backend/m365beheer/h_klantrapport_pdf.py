"""Kwartaalrapportage voor de klant als PDF: helder, in gewone taal en met duidelijke grafieken.

Opbouw: voorblad, 'het kwartaal in het kort', uw vragen en meldingen, hoe snel wij helpen, wie u hielp en de uren,
uw IT-omgeving (back-up, e-mail, Microsoft 365, alleen wat bekend is), bijlagen (opgeloste en openstaande tickets) en
een woordenlijst. Bij elk onderdeel een kader 'Wat betekent dit?'.
"""
from __future__ import annotations

from datetime import datetime

from . import h_grafiek_pdf as G
from .h_rapport import BLAUW, CYAAN, GRIJS, GROEN, LEI, MAP, NAVY, ORANJE, ROOD, _nl_datum

LICHT = (244, 247, 250)
ACCENT = (227, 244, 251)
RAND = (220, 228, 235)
WIT = (255, 255, 255)
nl = G.nl


def uur(h) -> str:
    return nl(h, 1 if h and h % 1 else 0)


def _duur(h) -> str:
    from .h_klantrapport import _uren_tekst
    return _uren_tekst(h)


def maak_pdf(d: dict, door: str = '') -> bytes:
    from fpdf import FPDF
    nu = datetime.now()
    klant = d['company']['name']
    kw = d['quarter']
    k, v = d['kpi'], d['prev']
    opties = d.get('options') or {}

    class Rapport(FPDF):
        def footer(self):
            if self.page_no() == 1:
                return
            self.set_y(-13)
            self.set_draw_color(*RAND)
            self.line(20, self.get_y() - 1, 190, self.get_y() - 1)
            self.set_font('Lato', '', 8)
            self.set_text_color(*GRIJS)
            self.cell(110, 6, f'Kwartaalrapportage {kw["short"]}  |  {klant}'[:90])
            self.cell(60, 6, f'Justdata  |  pagina {self.page_no()} van {{nb}}', align='R')

    p = Rapport(format='A4')
    p.set_auto_page_break(True, margin=18)
    p.set_margins(20, 18, 20)
    for stijl, bestand in (('', 'Regular'), ('B', 'Bold'), ('I', 'Regular'), ('BI', 'Bold')):
        p.add_font('Lato', stijl, str(MAP / f'Lato-{bestand}.ttf'))
    p.add_font('LatoBlack', '', str(MAP / 'Lato-Black.ttf'))
    p.alias_nb_pages()
    B = p.epw

    def mc(*a, **kw_):
        return p.multi_cell(*a, **{'new_x': 'LMARGIN', 'new_y': 'NEXT', 'align': 'L', **kw_})

    def ruimte(mm: float) -> None:
        if p.get_y() + mm > p.h - 20:
            p.add_page()

    def hoofdstuk(nr: str, titel: str, intro: str = '') -> None:
        p.add_page()
        p.set_fill_color(*BLAUW)
        p.rect(20, p.get_y(), 4, 11, 'F')
        p.set_x(27)
        p.set_font('LatoBlack', '', 19)
        p.set_text_color(*NAVY)
        p.cell(B - 7, 11, f'{nr}  {titel}', new_x='LMARGIN', new_y='NEXT')
        p.ln(2)
        if intro:
            tekst(intro, 10, GRIJS)
            p.ln(2)

    def kop(t: str, blok: float = 0) -> None:
        ruimte(max(22, blok + 16))
        p.ln(4)
        p.set_font('LatoBlack', '', 12.5)
        p.set_text_color(*NAVY)
        mc(B, 6.5, t)
        p.set_draw_color(*CYAAN)
        p.set_line_width(0.6)
        p.line(20, p.get_y() + 0.5, 34, p.get_y() + 0.5)
        p.set_line_width(0.2)
        p.ln(3.5)

    def tekst(t: str, g: float = 10, kl=LEI, st: str = '', h: float = 5.4) -> None:
        p.set_font('Lato', st, g)
        p.set_text_color(*kl)
        mc(B, h, t)

    def uitleg(t: str, titel: str = 'Wat betekent dit?') -> None:
        p.set_font('Lato', '', 9.3)
        regels = len(p.multi_cell(B - 14, 4.8, t, dry_run=True, output='LINES'))
        hoogte = 9 + regels * 4.8 + 3
        ruimte(hoogte + 3)
        y = p.get_y()
        p.set_fill_color(*ACCENT)
        p.rect(20, y, B, hoogte, style='F', round_corners=True, corner_radius=2)
        p.set_fill_color(*CYAAN)
        p.rect(20, y, 1.6, hoogte, style='F')
        p.set_xy(27, y + 3)
        p.set_font('Lato', 'B', 9.3)
        p.set_text_color(*NAVY)
        p.cell(B - 14, 5, titel, new_x='LEFT', new_y='NEXT')
        p.set_x(27)
        p.set_font('Lato', '', 9.3)
        p.set_text_color(*LEI)
        p.multi_cell(B - 14, 4.8, t, align='L', new_x='LMARGIN', new_y='NEXT')
        p.set_y(y + hoogte + 4)

    def verschil(nu_, toen, hoger_goed=None) -> tuple[str, tuple]:
        if not toen:
            return '', GRIJS
        d_ = nu_ - toen
        if abs(d_) < max(1, toen * 0.05):
            return f'gelijk aan {v["short"]}', GRIJS
        pct = round(abs(d_) * 100 / toen)
        kl = GRIJS if hoger_goed is None else (GROEN if (d_ > 0) == hoger_goed else ORANJE)
        return f"{'+' if d_ > 0 else '-'}{pct}% t.o.v. {v['short']}", kl

    def tegels(items: list[tuple], per_rij: int = 4, hoogte: float = 30) -> None:
        """items: (label, waarde, toelichting, toelichting-kleur, accentkleur)"""
        gap = 4
        w = (B - gap * (per_rij - 1)) / per_rij
        for i in range(0, len(items), per_rij):
            ruimte(hoogte + 4)
            y = p.get_y()
            for j, (label, waarde, sub, skl, kl) in enumerate(items[i:i + per_rij]):
                x = 20 + j * (w + gap)
                p.set_fill_color(*LICHT)
                p.rect(x, y, w, hoogte, style='F', round_corners=True, corner_radius=2.5)
                p.set_fill_color(*kl)
                p.rect(x, y + 4, 1.5, hoogte - 8, style='F')
                p.set_xy(x + 5, y + 3.5)
                p.set_font('Lato', '', 8.3)
                p.set_text_color(*GRIJS)
                p.cell(w - 7, 4.5, label)
                p.set_xy(x + 5, y + 9.5)
                p.set_font('LatoBlack', '', 19)
                p.set_text_color(*kl)
                p.cell(w - 7, 9, str(waarde))
                if sub:
                    p.set_xy(x + 5, y + 20.5)
                    p.set_font('Lato', 'B' if skl != GRIJS else '', 7.6)
                    p.set_text_color(*skl)
                    p.multi_cell(w - 7, 3.6, sub[:80], align='L')
            p.set_xy(20, y + hoogte + gap)

    def tabel(koppen: list[tuple], rijen: list[list]) -> None:
        ws = [B * f for _, f, _ in koppen]

        def kopregel():
            p.set_font('Lato', 'B', 8.5)
            p.set_fill_color(*NAVY)
            p.set_text_color(*WIT)
            for (t, _, al), w in zip(koppen, ws):
                p.cell(w, 7, ('  ' + t) if al == 'L' else t + '  ', fill=True, align=al)
            p.ln(7)
        ruimte(16)
        kopregel()
        for i, r in enumerate(rijen):
            if p.get_y() + 6.5 > p.h - 20:
                p.add_page()
                kopregel()
            p.set_fill_color(*(LICHT if i % 2 else WIT))
            p.set_text_color(*LEI)
            p.set_font('Lato', '', 8.3)
            for (_, _, al), w, val in zip(koppen, ws, r):
                s = str(val)
                while p.get_string_width(s) > w - 4 and len(s) > 3:
                    s = s[:-2]
                if s != str(val):
                    s = s[:-1] + '…'
                p.cell(w, 6.3, ('  ' + s) if al == 'L' else s + '  ', fill=True, align=al)
            p.ln(6.3)
        p.ln(3)

    def niets(t: str) -> None:
        p.set_fill_color(*LICHT)
        p.set_text_color(*GRIJS)
        p.set_font('Lato', '', 9.5)
        mc(B, 9, '   ' + t, fill=True)
        p.ln(2)

    # ------------------------------------------------------------ voorblad
    p.add_page()
    p.set_fill_color(*BLAUW)
    p.rect(0, 0, 210, 150, 'F')
    p.set_fill_color(*NAVY)
    p.rect(0, 150, 210, 4, 'F')
    # decoratieve ringen (huisstijlkleuren)
    G.ring(p, 182, 34, 46, 38, 0, 359.99, (40, 140, 184))
    G.ring(p, 182, 34, 30, 26, 0, 359.99, (52, 152, 196))
    p.set_fill_color(*WIT)
    p.rect(20, 20, 82, 24, style='F', round_corners=True, corner_radius=2)
    p.image(str(MAP / 'logo.png'), x=24, y=24, h=16)
    p.set_xy(20, 74)
    p.set_font('Lato', '', 13)
    p.set_text_color(*WIT)
    mc(B, 7, 'Kwartaalrapportage')
    p.set_x(20)
    p.set_font('LatoBlack', '', 30)
    mc(B, 13, klant)
    p.set_x(20)
    p.set_font('Lato', 'B', 14)
    mc(B, 8, f"{kw['label']}  ·  {kw['range']}")
    p.set_xy(20, 166)
    for a, b in (('Voor', klant), ('Periode', f"{kw['range']}{' (tot en met vandaag)' if d.get('current') else ''}"),
                 ('Datum', _nl_datum(nu)), ('Opgesteld door', f'{door}, Justdata' if door else 'Justdata')):
        p.set_font('Lato', '', 10)
        p.set_text_color(*GRIJS)
        p.cell(36, 7.5, a)
        p.set_font('Lato', 'B', 10)
        p.set_text_color(*LEI)
        mc(B - 36, 7.5, b)
    p.ln(8)
    tekst('In dit rapport leest u wat wij het afgelopen kwartaal voor u hebben gedaan: hoeveel vragen en meldingen er binnenkwamen, '
          'hoe snel wij die hebben opgelost, wie u heeft geholpen en hoeveel tijd wij eraan hebben besteed. '
          'Waar mogelijk laten we ook zien hoe het staat met uw back-ups, uw e-mailbeveiliging en uw Microsoft 365-licenties. '
          'Heeft u vragen over dit rapport? Neem gerust contact met ons op.', 10, GRIJS, h=5.6)

    # ------------------------------------------------------------ 1. in het kort
    hoofdstuk('1.', 'Het kwartaal in het kort', f"{kw['label']} ({kw['range']}), vergeleken met het kwartaal ervoor ({v['label']}).")
    t1, k1 = verschil(k['created'], v['created'])
    t2, k2 = verschil(k['completed'], v['completed'], True)
    t3, k3 = verschil(k['hours'], v['hours'])
    tegels([('Vragen binnengekomen', nl(k['created']), t1, k1, BLAUW),
            ('Opgelost', nl(k['completed']), t2, k2, GROEN),
            ('Uren gewerkt', uur(k['hours']), t3, k3, NAVY),
            ('Helft opgelost binnen', _duur(k['leadMedian']) if k['leadMedian'] is not None else '-', 'doorlooptijd (mediaan)', GRIJS, CYAAN)])
    kop('Samengevat')
    y = p.get_y()
    for zin in d['summary']:
        ruimte(12)
        y = p.get_y()
        p.set_fill_color(*GROEN)
        p.ellipse(21, y + 1.3, 3.2, 3.2, style='F')
        p.set_draw_color(*WIT)
        p.set_line_width(0.45)
        p.line(21.8, y + 2.9, 22.4, y + 3.6)
        p.line(22.4, y + 3.6, 23.5, y + 2.0)
        p.set_line_width(0.2)
        p.set_xy(27, y)
        p.set_font('Lato', '', 10)
        p.set_text_color(*LEI)
        p.multi_cell(B - 7, 5.6, zin, align='L', new_x='LMARGIN', new_y='NEXT')
        p.ln(1.2)
    # twee grafieken naast elkaar: opgelost/open en snelheid
    kop('In één oogopslag', 62)
    y0 = p.get_y()
    G.donut(p, 46, y0 + 25, 22, [('Opgelost', k['completed'], GROEN), ('Nog open', k['open'], ORANJE)], nl(k['completed']), 'opgelost')
    G.legenda(p, 76, y0 + 14, [('Opgelost', k['completed'], GROEN), ('Nog open', k['open'], ORANJE)], 50, pct=False)
    G.meter(p, 162, y0 + 34, 24, k['within1'], 'binnen een dag opgelost', (70, 50))
    p.set_y(y0 + 56)

    # ------------------------------------------------------------ 2. vragen en meldingen
    hoofdstuk('2.', 'Uw vragen en meldingen', 'Elke vraag, storing of wens die bij ons binnenkomt, leggen wij vast als een ticket. Zo raakt er niets kwijt '
              'en kunnen wij precies laten zien wat er met uw vraag is gebeurd.')
    kop('Per maand', 70)
    y0 = p.get_y()
    G.kolommen(p, 33, y0 + 4, B - 13, 50, [m.capitalize() for m in kw['months']],
               [('Binnengekomen', [m['created'] for m in d['months']], BLAUW), ('Opgelost', [m['completed'] for m in d['months']], GROEN)])
    p.set_y(y0 + 70)
    soorten = [x for x in d['types'] if x['count']][:7]
    if soorten:
        kop('Waar gingen de vragen over?', 58)
        y0 = p.get_y()
        delen = [(x['label'], x['count'], G.PALET[i % len(G.PALET)]) for i, x in enumerate(soorten)]
        G.donut(p, 46, y0 + 25, 23, delen, nl(k['created']), 'vragen')
        yl = G.legenda(p, 80, y0 + 25 - len(delen) * 3, delen, 110)
        p.set_y(max(y0 + 54, yl + 4))
    bronnen = [x for x in d['sources'] if x['count']][:6]
    if bronnen:
        kop('Hoe kwamen de vragen binnen?', 8 + len(bronnen) * 7.2)
        p.set_y(G.staven(p, 20, p.get_y(), B, [(x['label'], x['count']) for x in bronnen], kl=CYAAN) + 2)
    kop('Op welke dagen kwamen de vragen binnen?', 62)
    y0 = p.get_y()
    wd = d['weekdays'] if any(x['count'] for x in d['weekdays'][5:]) else d['weekdays'][:5]
    G.kolommen(p, 33, y0 + 4, B - 13, 44, [x['label'][:2].capitalize() if len(wd) == 7 else x['label'].capitalize() for x in wd],
               [('Vragen', [x['count'] for x in wd], NAVY)])
    p.set_y(y0 + 58)
    contacten = [x for x in d['contacts'] if x['count']][:10]
    if contacten:
        kop('Wie stelde de vragen?', 8 + len(contacten) * 7.2)
        p.set_y(G.staven(p, 20, p.get_y(), B, [(x['label'], x['count']) for x in contacten], kl=BLAUW) + 2)
    uitleg('Hoe meer vragen er binnenkomen, hoe meer wij voor u doen. Komen er veel vragen over hetzelfde onderwerp binnen? '
           'Dan kijken wij samen met u of we het probleem bij de bron kunnen oplossen, zodat u er minder last van heeft.')

    # ------------------------------------------------------------ 3. snelheid
    hoofdstuk('3.', 'Hoe snel helpen wij u?', 'Hier ziet u hoe lang het duurde voordat uw vraag helemaal was opgelost: de tijd tussen uw melding en het moment '
              'dat wij het ticket hebben afgesloten. Nachten en weekenden tellen hierin mee.')
    tegels([('Eerste reactie (meestal)', _duur(k['firstResponse']) if k['firstResponse'] is not None else '-', 'na uw melding', GRIJS, CYAAN),
            ('Helft opgelost binnen', _duur(k['leadMedian']) if k['leadMedian'] is not None else '-', 'doorlooptijd (mediaan)', GRIJS, BLAUW),
            ('Binnen 4 uur opgelost', f"{k['within4']}%" if k['within4'] is not None else '-', 'van de opgeloste vragen', GRIJS, GROEN)], 3)
    snel = d.get('speed') or []
    if any(x['count'] for x in snel):
        kop('Hoe lang duurde het oplossen?', 62)
        y0 = p.get_y()
        kl = [GROEN, (88, 170, 120), BLAUW, ORANJE, ROOD]
        delen = [(x['label'], x['count'], kl[i]) for i, x in enumerate(snel)]
        G.donut(p, 46, y0 + 25, 23, delen, f"{k['within1']}%" if k['within1'] is not None else '-', 'binnen een dag')
        G.legenda(p, 80, y0 + 10, delen, 110)
        p.set_y(y0 + 56)
    uitleg('De mediaan is het middelste getal: de ene helft van de vragen was sneller klaar, de andere helft duurde langer. '
           'Wij gebruiken dit getal omdat één grote klus die lang duurt het beeld dan niet vertekent. '
           'Grotere wensen of bestellingen duren vanzelfsprekend langer dan een wachtwoord herstellen.')

    # ------------------------------------------------------------ 4. wie en uren
    hoofdstuk('4.', 'Wie heeft u geholpen en hoeveel tijd?', 'Alle tijd die wij aan uw vragen en projecten besteden, schrijven wij per kwartier of minuut. '
              'Hieronder ziet u hoeveel tijd dat was en wie van ons team u heeft geholpen.')
    kop('Uren per maand', 64)
    y0 = p.get_y()
    G.kolommen(p, 33, y0 + 4, B - 13, 46, [m.capitalize() for m in kw['months']], [('Uren', [m['hours'] for m in d['months']], NAVY)], ' u')
    p.set_y(y0 + 60)
    if k['projectHours'] and k['ticketHours']:
        kop('Waar ging de tijd naartoe?', 56)
        y0 = p.get_y()
        delen = [('Vragen en meldingen', k['ticketHours'], BLAUW), ('Projecten', k['projectHours'], CYAAN)]
        G.donut(p, 46, y0 + 23, 21, delen, uur(k['hours']), 'uur')
        G.legenda(p, 80, y0 + 17, delen, 100)
        p.set_y(y0 + 50)
        if d['projects']:
            p.set_y(G.staven(p, 20, p.get_y(), B, [(x['label'], x['hours']) for x in d['projects'][:8]], ' u', CYAAN) + 2)
    mw = [m for m in d['employees'] if m['tickets'] or m['hours']][:10]
    if mw and opties.get('employees', True):
        kop('Uw vaste aanspreekpunten', 12 + len(mw) * 7)
        tabel([('Medewerker', 0.5, 'L'), ('Opgeloste vragen', 0.25, 'R'), ('Uren', 0.25, 'R')],
              [[m['name'], nl(m['tickets']), nl(m['hours'], 1)] for m in mw])

    # ------------------------------------------------------------ 5. IT-omgeving
    ex = d.get('extra') or {}
    if any(ex.get(x) for x in ('backup', 'email', 'm365')):
        hoofdstuk('5.', 'Uw IT-omgeving', 'Naast het oplossen van vragen houden wij uw omgeving dagelijks in de gaten. Dit is de stand op het moment van dit rapport.')
        bk = ex.get('backup')
        if bk:
            kop('Back-ups', 50)
            y0 = p.get_y()
            G.meter(p, 50, y0 + 30, 25, bk['pct'], 'back-ups gelukt')
            p.set_xy(88, y0 + 4)
            p.set_font('Lato', '', 10)
            p.set_text_color(*LEI)
            st = ('Alles is in orde.' if bk['status'] == 'ok' else 'Er vraagt iets aandacht; wij pakken dit op.' if bk['status'] == 'warn'
                  else 'Er is een back-up niet gelukt; wij pakken dit op.')
            p.multi_cell(B - 68, 5.4, f"Wij maken een reservekopie van {nl(bk['total'])} {'systeem' if bk['total'] == 1 else 'systemen'} "
                                      f"({', '.join(bk['sources'])}). {st} Gaat er iets mis met een computer of server, "
                                      'dan kunnen wij uw gegevens hiermee terugzetten.', align='L', new_x='LMARGIN', new_y='NEXT')
            p.set_y(max(p.get_y(), y0 + 40) + 4)
        em = ex.get('email')
        if em:
            kop('E-mailbeveiliging', 50)
            y0 = p.get_y()
            G.meter(p, 50, y0 + 30, 25, em['pct'], 'e-mail goed beveiligd')
            p.set_xy(88, y0 + 4)
            p.set_font('Lato', '', 10)
            p.set_text_color(*LEI)
            beschermd = sum(1 for x in em['domains'] if x['policy'] in ('reject', 'quarantine'))
            p.multi_cell(B - 68, 5.4, f"Wij controleren of e-mail die met uw naam wordt verstuurd ook echt van u komt. Dit kwartaal ging het om "
                                      f"{nl(em['volume'])} e-mails. {beschermd} van uw {len(em['domains'])} domeinnamen {'is' if beschermd == 1 else 'zijn'} volledig beschermd "
                                      'tegen nepmail uit uw naam.', align='L', new_x='LMARGIN', new_y='NEXT')
            p.set_y(max(p.get_y(), y0 + 40) + 4)
        m = ex.get('m365')
        if m:
            kop('Microsoft 365-licenties', 20 + len(m['skus']) * 6.3)
            tekst(f"U heeft {nl(m['bought'])} betaalde licenties, waarvan er {nl(m['assigned'])} aan een gebruiker zijn gekoppeld."
                  + (f" Er {'is' if m['saving'] == 1 else 'zijn'} {nl(m['saving'])} licentie(s) die u mogelijk niet nodig heeft; wij bespreken graag met u of u daarop kunt besparen."
                     if m['saving'] else ''), 10)
            p.ln(2)
            if m['skus']:
                tabel([('Licentie', 0.6, 'L'), ('Aantal', 0.2, 'R'), ('In gebruik', 0.2, 'R')], [[x['name'], nl(x['bought']), nl(x['assigned'])] for x in m['skus']])

    # ------------------------------------------------------------ bijlagen
    if opties.get('tickets', True) and (d['resolved'] or d['openList']):
        hoofdstuk('A.', 'Bijlage: alle tickets', 'Een overzicht van alle vragen en meldingen die in dit kwartaal zijn opgelost, en wat er nog openstaat.')
        if d['resolved']:
            kop(f"Opgelost in dit kwartaal ({len(d['resolved'])})")
            tabel([('Nummer', 0.18, 'L'), ('Onderwerp', 0.37, 'L'), ('Gemeld', 0.12, 'L'), ('Opgelost', 0.12, 'L'), ('Uren', 0.07, 'R'), ('Door', 0.14, 'L')],
                  [[t['number'], t['title'], t['created'], t['completed'], nl(t['hours'], 1) if t['hours'] else '-', t['by'] or ''] for t in d['resolved']])
        if d['openList']:
            kop(f"Nog open ({len(d['openList'])})")
            tabel([('Nummer', 0.18, 'L'), ('Onderwerp', 0.44, 'L'), ('Gemeld', 0.14, 'L'), ('Status', 0.24, 'L')],
                  [[t['number'], t['title'], t['created'], t['status']] for t in d['openList']])

    hoofdstuk('B.', 'Woordenlijst')
    for a, b in (('Ticket', 'Een vraag, storing of wens die bij ons is binnengekomen en die wij hebben vastgelegd.'),
                 ('Opgelost', 'Het ticket is afgerond: de vraag is beantwoord of het probleem is verholpen.'),
                 ('Eerste reactie', 'De tijd tussen uw melding en het eerste antwoord van een van onze medewerkers.'),
                 ('Doorlooptijd', 'De tijd tussen uw melding en het moment waarop het ticket helemaal is opgelost.'),
                 ('Mediaan', 'Het middelste getal: de helft is sneller, de andere helft langzamer.'),
                 ('Back-up', 'Een reservekopie van uw gegevens, zodat wij die kunnen terugzetten als er iets misgaat.'),
                 ('E-mailbeveiliging (DMARC)', 'Een controle die voorkomt dat criminelen e-mail versturen die van u lijkt te komen.'),
                 ('Licentie', 'Het recht om een programma (zoals Microsoft 365) te gebruiken; u betaalt per gebruiker per maand.')):
        ruimte(14)
        p.set_font('Lato', 'B', 10)
        p.set_text_color(*NAVY)
        p.cell(52, 6, a)
        p.set_font('Lato', '', 10)
        p.set_text_color(*LEI)
        mc(B - 52, 6, b)
        p.ln(1.5)
    return bytes(p.output())
