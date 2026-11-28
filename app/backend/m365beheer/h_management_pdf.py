"""Managementrapportage als PDF (huisstijl Justdata, zelfde basis als de NEN 7510- en DMARC-rapporten).

Opbouw: titelpagina, managementsamenvatting (kerncijfers + aandachtspunten), servicedesk, back-up, e-mailbeveiliging,
Microsoft 365, en een bijlage met alle tabellen. Grafieken worden met rechthoeken getekend (geen extra bibliotheken).
"""
from __future__ import annotations

from datetime import datetime

from . import h_grafiek_pdf as G
from .h_rapport import BLAUW, CYAAN, GRIJS, GROEN, LEI, MAP, NAVY, ORANJE, ROOD, _nl_datum

LICHT = (244, 247, 250)
RAND = (220, 228, 235)
WIT = (255, 255, 255)
KLEUR = {'ok': GROEN, 'warn': ORANJE, 'err': ROOD, 'info': BLAUW, 'unknown': GRIJS, 'paused': GRIJS}
STATUS_NL = {'ok': 'In orde', 'warn': 'Aandacht', 'err': 'Actie nodig', 'unknown': 'Onbekend', 'paused': 'Gepauzeerd'}


def _nl(n, dec: int = 0) -> str:
    if n is None:
        return '-'
    s = f'{n:,.{dec}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def _kl(pct):
    return GROEN if (pct or 0) >= 95 else ORANJE if (pct or 0) >= 85 else ROOD


def _pct(v) -> str:
    return '-' if v is None else f'{_nl(v, 1 if isinstance(v, float) and v % 1 else 0)}%'


def maak_pdf(d: dict, door: str = '') -> bytes:
    from fpdf import FPDF
    nu = datetime.now()
    dagen = d['days']

    class Rapport(FPDF):
        def footer(self):
            if self.page_no() == 1:
                return
            self.set_y(-13)
            self.set_draw_color(*RAND)
            self.line(20, self.get_y() - 1, 190, self.get_y() - 1)
            self.set_font('Lato', '', 8)
            self.set_text_color(*GRIJS)
            self.cell(85, 6, 'Justdata  |  Managementrapportage  |  vertrouwelijk')
            self.cell(85, 6, f'{_nl_datum(nu)}  |  Pagina {self.page_no()} van {{nb}}', align='R')

    p = Rapport(format='A4')
    p.set_auto_page_break(True, margin=18)
    p.set_margins(20, 18, 20)
    for stijl, bestand in (('', 'Regular'), ('B', 'Bold'), ('I', 'Regular'), ('BI', 'Bold')):
        p.add_font('Lato', stijl, str(MAP / f'Lato-{bestand}.ttf'))
    p.add_font('LatoBlack', '', str(MAP / 'Lato-Black.ttf'))
    p.alias_nb_pages()
    B = p.epw   # 170 mm

    # ------------------------------------------------------------ bouwstenen
    def mc(*a, **k):
        return p.multi_cell(*a, **{'new_x': 'LMARGIN', 'new_y': 'NEXT', 'align': 'L', **k})

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
            tekst(intro, 9.5, GRIJS)
            p.ln(2)

    def kop(t: str, voor: float = 5, blok: float = 0) -> None:
        ruimte(max(22, blok + 16))   # kop nooit los onderaan; met blok blijft de grafiek/tabel erbij
        p.ln(voor)
        p.set_font('LatoBlack', '', 12.5)
        p.set_text_color(*NAVY)
        mc(B, 6.5, t)
        p.set_draw_color(*CYAAN)
        p.set_line_width(0.6)
        p.line(20, p.get_y() + 0.5, 34, p.get_y() + 0.5)
        p.set_line_width(0.2)
        p.ln(3)

    def tekst(t: str, g: float = 10, kl=LEI, st: str = '', h: float = 5.2) -> None:
        p.set_font('Lato', st, g)
        p.set_text_color(*kl)
        mc(B, h, t)

    def niet(t: str) -> None:
        p.set_fill_color(*LICHT)
        p.set_text_color(*GRIJS)
        p.set_font('Lato', '', 9.5)
        mc(B, 8, '   ' + t, fill=True)

    def tegels(items: list[tuple], per_rij: int = 3, hoogte: float = 25) -> None:
        """items: (label, waarde, toelichting, kleur)"""
        gap = 4
        w = (B - gap * (per_rij - 1)) / per_rij
        for i in range(0, len(items), per_rij):
            ruimte(hoogte + 4)
            y = p.get_y()
            for j, (label, waarde, sub, kl) in enumerate(items[i:i + per_rij]):
                x = 20 + j * (w + gap)
                p.set_fill_color(*LICHT)
                p.rect(x, y, w, hoogte, 'F')
                p.set_fill_color(*(kl or BLAUW))
                p.rect(x, y, 1.6, hoogte, 'F')
                p.set_xy(x + 5, y + 3)
                p.set_font('Lato', '', 8.5)
                p.set_text_color(*GRIJS)
                p.cell(w - 7, 4.5, label)
                p.set_xy(x + 5, y + 8)
                p.set_font('LatoBlack', '', 17)
                p.set_text_color(*(kl or NAVY))
                p.cell(w - 7, 8, str(waarde))
                if sub:
                    p.set_xy(x + 5, y + 17)
                    p.set_font('Lato', '', 7.8)
                    p.set_text_color(*GRIJS)
                    p.multi_cell(w - 7, 3.6, sub[:110], align='L')
            p.set_xy(20, y + hoogte + gap)

    def verdeling(delen: list[tuple], hoogte: float = 7, legenda: bool = True) -> None:
        """Gestapelde balk over de volle breedte: delen = (label, aantal, kleur)."""
        tot = sum(n for _, n, _ in delen) or 1
        ruimte(hoogte + 12)
        y, x = p.get_y(), 20
        for _, n, kl in delen:
            w = B * n / tot
            if w > 0:
                p.set_fill_color(*kl)
                p.rect(x, y, w, hoogte, 'F')
                if w > 12:
                    p.set_xy(x, y)
                    p.set_font('Lato', 'B', 7.5)
                    p.set_text_color(*WIT)
                    p.cell(w, hoogte, f'{round(n * 100 / tot)}%', align='C')
            x += w
        p.set_xy(20, y + hoogte + 1.5)
        if legenda:
            for label, n, kl in delen:
                p.set_fill_color(*kl)
                p.rect(p.get_x(), p.get_y() + 1.3, 2.6, 2.6, 'F')
                p.set_x(p.get_x() + 4)
                p.set_font('Lato', '', 8)
                p.set_text_color(*LEI)
                t = f'{label}: {_nl(n)}'
                p.cell(p.get_string_width(t) + 6, 5, t)
            p.ln(7)

    def staven(rijen: list[tuple], eenheid: str = '', kl=BLAUW, label_w: float = 58) -> None:
        """Horizontale staven: rijen = (label, waarde)."""
        mx = max((v for _, v in rijen), default=0) or 1
        for label, v in rijen:
            ruimte(7)
            y = p.get_y()
            p.set_font('Lato', '', 8.5)
            p.set_text_color(*LEI)
            p.cell(label_w, 5.6, str(label)[:40])
            w = (B - label_w - 24) * v / mx
            p.set_fill_color(*LICHT)
            p.rect(20 + label_w, y + 1, B - label_w - 24, 3.6, 'F')
            p.set_fill_color(*kl)
            p.rect(20 + label_w, y + 1, max(w, 0.4), 3.6, 'F')
            p.set_xy(20 + B - 22, y)
            p.set_font('Lato', 'B', 8.5)
            p.cell(22, 5.6, f'{_nl(v, 1 if isinstance(v, float) and v % 1 else 0)}{eenheid}', align='R', new_x='LMARGIN', new_y='NEXT')
        p.ln(2)

    def kolommen(weken: list[dict]) -> None:
        """Weektrend: per week twee kolommen (binnengekomen / afgerond)."""
        if not weken:
            return
        h = 42
        ruimte(h + 16)
        y0 = p.get_y()
        mx = max(max(w['created'], w['completed']) for w in weken) or 1
        breed = B / len(weken)
        p.set_draw_color(*RAND)
        for i in range(5):
            yy = y0 + h - h * i / 4
            p.line(20, yy, 190, yy)
        for i, w in enumerate(weken):
            x = 20 + i * breed + breed * 0.18
            kw = breed * 0.3
            for j, (v, kl) in enumerate(((w['created'], BLAUW), (w['completed'], GROEN))):
                hh = h * v / mx
                p.set_fill_color(*kl)
                p.rect(x + j * kw, y0 + h - hh, kw - 0.4, hh, 'F')
            p.set_xy(20 + i * breed, y0 + h + 1)
            p.set_font('Lato', '', 7)
            p.set_text_color(*GRIJS)
            p.cell(breed, 4, w['label'], align='C')
        p.set_xy(20, y0 + h + 6)
        for label, kl in (('Binnengekomen', BLAUW), ('Afgerond', GROEN)):
            p.set_fill_color(*kl)
            p.rect(p.get_x(), p.get_y() + 1.3, 2.6, 2.6, 'F')
            p.set_x(p.get_x() + 4)
            p.set_font('Lato', '', 8)
            p.set_text_color(*LEI)
            p.cell(30, 5, label)
        p.set_font('Lato', '', 8)
        p.set_text_color(*GRIJS)
        p.cell(0, 5, f'(schaal tot {mx} tickets per week)', align='R', new_x='LMARGIN', new_y='NEXT')
        p.ln(3)

    def tabel(koppen: list[tuple], rijen: list[list], kleuren: list | None = None) -> None:
        """koppen: (titel, breedte-fractie, uitlijning). Kop wordt herhaald op een nieuwe pagina."""
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
            for j, ((_, _, al), w, v) in enumerate(zip(koppen, ws, r)):
                kl = (kleuren[i][j] if kleuren and kleuren[i] and j < len(kleuren[i]) else None) or LEI
                p.set_text_color(*kl)
                p.set_font('Lato', 'B' if kl != LEI else '', 8.5)
                s = str(v)
                while p.get_string_width(s) > w - 4 and len(s) > 3:
                    s = s[:-2]
                if s != str(v):
                    s = s[:-1] + '…' if p.get_string_width(s[:-1] + '…') <= w - 4 else s
                p.cell(w, 6.5, ('  ' + s) if al == 'L' else s + '  ', fill=True, align=al)
            p.ln(6.5)
        p.ln(3)

    bk, em, ats, m = d['backup'], d['email'], d['autotask'], d['m365']
    at = ats.get('data')
    lic, gd = m['licenses'], m['gdap']

    # ------------------------------------------------------------ titelpagina
    p.add_page()
    p.set_fill_color(*BLAUW)
    p.rect(0, 0, 210, 112, 'F')
    p.set_fill_color(*NAVY)
    p.rect(0, 112, 210, 3, 'F')
    p.set_fill_color(*WIT)
    p.rect(20, 18, 82, 24, 'F')
    p.image(str(MAP / 'logo.png'), x=24, y=22, h=16)
    p.set_xy(20, 56)
    p.set_font('LatoBlack', '', 30)
    p.set_text_color(*WIT)
    mc(B, 12, 'Managementrapportage')
    p.set_x(20)
    p.set_font('Lato', '', 13)
    mc(B, 7, 'Servicedesk, back-up, e-mailbeveiliging en Microsoft 365')
    p.set_xy(20, 128)
    for k, v in (('Periode', f'laatste {dagen} dagen (t/m {_nl_datum(nu)})'), ('Datum', _nl_datum(nu)), ('Opgesteld door', door or 'Justdata'),
                 ('Bronnen', 'Autotask, Datto, Unitrends, EasyDMARC en Microsoft 365 (GDAP)'), ('Vertrouwelijkheid', 'Intern - vertrouwelijk')):
        p.set_font('Lato', '', 10)
        p.set_text_color(*GRIJS)
        p.cell(40, 7.5, k)
        p.set_font('Lato', 'B', 10)
        p.set_text_color(*LEI)
        mc(B - 40, 7.5, v)
    p.ln(10)
    kritiek = sum(1 for x in d['points'] if x['level'] == 'err')
    aandacht = sum(1 for x in d['points'] if x['level'] == 'warn')
    kl = ROOD if kritiek else ORANJE if aandacht else GROEN
    p.set_fill_color(*kl)
    p.set_text_color(*WIT)
    p.set_font('LatoBlack', '', 13)
    mc(B, 11, '  ' + (f'{kritiek} kritiek(e) punt(en) en {aandacht} aandachtspunt(en)' if kritiek else
                      f'{aandacht} aandachtspunt(en), geen kritieke punten' if aandacht else 'Geen kritieke punten of aandachtspunten'), fill=True)
    p.ln(4)
    tekst('Dit rapport geeft een overzicht op managementniveau van de dienstverlening en de technische staat van de klantomgevingen. '
          'Hoofdstuk 1 vat de belangrijkste cijfers en aandachtspunten samen; de hoofdstukken daarna geven per onderdeel de details. '
          'In de bijlage staan alle onderliggende gegevens per klant.', 9.5, GRIJS)

    # ------------------------------------------------------------ 1. samenvatting
    hoofdstuk('1.', 'Managementsamenvatting', f'Stand per {d["at"]}. Cijfers over de laatste {dagen} dagen, tenzij anders vermeld.')
    kern = []
    if at:
        k = at['kpi']
        kern += [('Tickets afgerond', _nl(k['completed']), f"{_nl(k['created'])} binnengekomen in de periode", GROEN if k['completed'] >= k['created'] else ORANJE),
                 ('Open tickets', _nl(k['open']), f"waarvan {_nl(k['openOld'])} ouder dan 30 dagen", ORANJE if k['openVeryOld'] else NAVY),
                 ('Uren geregistreerd', _nl(k['hours'], 1), f"{_pct(k['billablePct'])} facturabel" if k['billablePct'] is not None else '', NAVY)]
    if bk.get('configured') and bk.get('kpi'):
        k = bk['kpi']
        kern.append(('Back-ups geslaagd', _pct(k['pct']), f"{_nl(k['custErr'])} klant(en) met fouten van {_nl(k['customers'])}",
                     GROEN if (k['pct'] or 0) >= 95 else ORANJE if (k['pct'] or 0) >= 85 else ROOD))
    if em.get('configured') and em.get('kpi'):
        k = em['kpi']
        kern.append(('E-mail DMARC-naleving', _pct(k['pct']), f"{_nl(k['protected'])} van {_nl(k['domains'])} domeinen beschermd (reject/quarantine)",
                     GROEN if (k['pct'] or 0) >= 95 else ORANJE if (k['pct'] or 0) >= 85 else ROOD))
    if lic.get('loaded'):
        kern.append(('Licentiebenutting', _pct(lic['usePct']), f"{_nl(lic['saving'])} mogelijk overbodig, {_nl(lic['customers'])} klanten", NAVY))
    elif gd['customers']:
        kern.append(('Klanten met GDAP-toegang', f"{_nl(gd['access'])}/{_nl(gd['customers'])}", f"{len(gd['expiring'])} relatie(s) verlopen binnen 30 dagen", NAVY))
    if kern:
        tegels(kern)
    kop('Aandachtspunten')
    if d['points']:
        for x in d['points']:
            ruimte(10)
            y = p.get_y()
            p.set_fill_color(*KLEUR[x['level']])
            p.rect(20, y + 1.2, 2.4, 3.6, 'F')
            p.set_xy(25, y)
            p.set_font('Lato', 'B', 9.5)
            p.set_text_color(*KLEUR[x['level']])
            p.cell(28, 6, x['area'])
            p.set_font('Lato', '', 9.5)
            p.set_text_color(*LEI)
            p.multi_cell(B - 33, 6, x['text'], new_x='LMARGIN', new_y='NEXT', align='L')
    else:
        tekst('Er zijn geen kritieke punten of aandachtspunten gevonden.', 10, GROEN, 'B')
    kop('Per onderdeel')
    zinnen = []
    if at:
        k = at['kpi']
        zinnen.append(('Servicedesk', f"{_nl(k['created'])} tickets binnengekomen en {_nl(k['completed'])} afgerond; mediane doorlooptijd "
                       f"{_nl(k['leadMedian'], 1) if k['leadMedian'] is not None else '-'} dag(en). {_nl(k['hours'], 1)} uur geregistreerd voor {_nl(k['customers'])} klanten."))
    else:
        zinnen.append(('Servicedesk', 'Autotask is niet gekoppeld of de cijfers konden niet worden opgehaald.'))
    zinnen.append(('Back-up', (f"{_pct(bk['kpi']['pct'])} van de {_nl(bk['kpi']['items'])} beveiligde systemen had een recente geslaagde back-up; "
                               f"{_nl(bk['kpi']['custOk'])} klanten volledig in orde.") if bk.get('configured') and bk.get('kpi') else 'Geen back-upkoppeling.'))
    zinnen.append(('E-mail', (f"{_pct(em['kpi']['pct'])} van {_nl(em['kpi']['volume'])} gemeten berichten haalde de DMARC-controle; "
                              f"{_nl(em['kpi']['domErr'])} domein(en) vragen actie.") if em.get('configured') and em.get('kpi') else 'Geen EasyDMARC-koppeling.'))
    zinnen.append(('Microsoft 365', f"{_nl(gd['access'])} van {_nl(gd['customers'])} klanten met GDAP-toegang" +
                   (f"; {_nl(lic['assigned'])} van {_nl(lic['bought'])} betaalde licenties toegewezen." if lic.get('loaded') else '.')))
    for a, t in zinnen:
        ruimte(10)
        p.set_font('Lato', 'B', 9.5)
        p.set_text_color(*NAVY)
        p.cell(30, 5.6, a)
        p.set_font('Lato', '', 9.5)
        p.set_text_color(*LEI)
        p.multi_cell(B - 30, 5.6, t, new_x='LMARGIN', new_y='NEXT', align='L')
        p.ln(1)

    # ------------------------------------------------------------ 2. servicedesk
    hoofdstuk('2.', 'Servicedesk (Autotask)', 'Tickets, doorlooptijd en geregistreerde uren. Bron: Autotask PSA.')
    if not at:
        niet(ats.get('error') or ('Autotask is niet gekoppeld.' if not ats.get('configured') else 'De cijfers worden nog opgehaald; maak het rapport over een moment opnieuw.'))
    else:
        k = at['kpi']
        tegels([('Binnengekomen', _nl(k['created']), 'nieuwe tickets in de periode', BLAUW),
                ('Afgerond', _nl(k['completed']), f"{_pct(k['within1'])} binnen 1 dag afgerond" if k['within1'] is not None else '', GROEN),
                ('Doorlooptijd (mediaan)', f"{_nl(k['leadMedian'], 1)} d" if k['leadMedian'] is not None else '-',
                 f"gemiddeld {_nl(k['leadAvg'], 1)} dagen" if k['leadAvg'] is not None else '', NAVY),
                ('Open tickets', _nl(k['open']), f"{_nl(k['openVeryOld'])} ouder dan 90 dagen", ORANJE if k['openVeryOld'] else NAVY),
                ('Uren', _nl(k['hours'], 1), f"{_nl(k['billable'], 1)} uur facturabel", NAVY),
                ('Facturabel', _pct(k['billablePct']), 'aandeel facturabele uren', GROEN if (k['billablePct'] or 0) >= 70 else ORANJE)])
        kop('Trend per week', blok=62)
        y0 = p.get_y()
        G.lijn(p, 33, y0 + 3, B - 15, 44, [w['label'] for w in at['weeks']],
               [('Binnengekomen', [w['created'] for w in at['weeks']], BLAUW), ('Afgerond', [w['completed'] for w in at['weeks']], GROEN)],
               elke=2 if len(at['weeks']) > 8 else 1)
        p.set_y(y0 + 62)
        kop('Leeftijd van de open tickets', blok=54)
        y0 = p.get_y()
        delen = [(lab, n, kl) for (lab, n), kl in zip(at['openAge'].items(), (GROEN, BLAUW, ORANJE, ROOD))]
        G.donut(p, 46, y0 + 23, 22, delen, _nl(k['open']), 'open')
        G.legenda(p, 80, y0 + 11, delen, 100)
        p.set_y(y0 + 50)
        kop('Meeste uren per klant (top 10)', blok=6 * min(10, len([r for r in at['customers'] if r['hours']])) + 4)
        top = [r for r in at['customers'] if r['hours']][:10]
        staven([(r['name'], r['hours']) for r in top], ' u') if top else niet('Geen uren geregistreerd in de periode.')
        kop('Meeste tickets per klant (top 10)', blok=6 * min(10, len([r for r in at['customers'] if r['created']])) + 4)
        topt = sorted([r for r in at['customers'] if r['created']], key=lambda r: -r['created'])[:10]
        staven([(r['name'], r['created']) for r in topt], '', CYAAN) if topt else niet('Geen nieuwe tickets in de periode.')
        if at['employees']:
            kop('Uren per medewerker', blok=min(80, 7 + 6.5 * len(at['employees'])))
            tabel([('Medewerker', .40, 'L'), ('Uren', .15, 'R'), ('Facturabel', .15, 'R'), ('% facturabel', .15, 'R'), ('Afgerond', .15, 'R')],
                  [[r['name'], _nl(r['hours'], 1), _nl(r['billable'], 1), _pct(r['billablePct']), _nl(r['completed'])] for r in at['employees']])
        if at['priorities']:
            kop('Open tickets per prioriteit', blok=6 * min(8, len(at['priorities'])) + 4)
            staven([(r['label'], r['count']) for r in at['priorities'][:8]], '', NAVY)
        if at['queues']:
            kop('Binnengekomen per wachtrij', blok=6 * min(8, len(at['queues'])) + 4)
            staven([(r['label'], r['count']) for r in at['queues'][:8]], '', BLAUW)

    # ------------------------------------------------------------ 3. back-up
    hoofdstuk('3.', 'Back-up', 'Stand van de back-ups van alle beveiligde systemen. Geslaagd = geslaagde back-up in de laatste 26 uur. Bron: Datto en Unitrends.')
    if not (bk.get('configured') and bk.get('kpi')):
        niet('Er is geen back-upkoppeling (Datto/Unitrends) ingesteld.')
    else:
        k = bk['kpi']
        tegels([('Back-ups geslaagd', _pct(k['pct']), f"{_nl(k['ok'])} van {_nl(k['ok'] + k['warn'] + k['err'])} systemen", _kl(k['pct'])),
                ('Klanten in orde', f"{_nl(k['custOk'])}/{_nl(k['customers'])}", 'alle systemen geslaagd', GROEN),
                ('Klanten met fouten', _nl(k['custErr']), f"{_nl(k['custWarn'])} met waarschuwingen", ROOD if k['custErr'] else GROEN)])
        kop('Status van alle systemen', blok=54)
        y0 = p.get_y()
        delen = [('Geslaagd', k['ok'], GROEN), ('Waarschuwing', k['warn'], ORANJE), ('Mislukt', k['err'], ROOD),
                 ('Onbekend', k['unknown'], GRIJS), ('Gepauzeerd', k['paused'], (190, 198, 206))]
        G.donut(p, 44, y0 + 23, 22, delen, _nl(k['items']), 'systemen')
        G.legenda(p, 74, y0 + 8, delen, 62)
        G.meter(p, 162, y0 + 32, 24, k['pct'], 'slagingspercentage')
        p.set_y(y0 + 50)
        kop('Per back-updienst', blok=7 + 6.5 * len(bk['sources']))
        tabel([('Dienst', .40, 'L'), ('Systemen', .20, 'R'), ('Geslaagd', .20, 'R'), ('Slagingspercentage', .20, 'R')],
              [[s['name'], _nl(s['items']), _nl(s['ok']), _pct(s['pct']) if not s['error'] else 'niet opgehaald'] for s in bk['sources']],
              [[None, None, None, GROEN if (s['pct'] or 0) >= 95 else ORANJE if s['pct'] is not None else ROOD] for s in bk['sources']])
        probleem = [c for c in bk['customers'] if c['status'] in ('err', 'warn')]
        kop('Klanten die aandacht vragen')
        if not probleem:
            tekst('Alle klanten zijn in orde.', 10, GROEN, 'B')
        for c in probleem:
            ruimte(14)
            p.set_font('Lato', 'B', 10)
            p.set_text_color(*NAVY)
            p.cell(B - 32, 6.5, c['name'])
            p.set_fill_color(*KLEUR[c['status']])
            p.set_text_color(*WIT)
            p.set_font('Lato', 'B', 8)
            p.cell(32, 5.5, STATUS_NL[c['status']], fill=True, align='C', new_x='LMARGIN', new_y='NEXT')
            for i in c['issues']:
                tekst(f"- {i['name']} ({i['source']}): {i['message'] or STATUS_NL[i['status']]}", 8.8, ROOD if i['status'] == 'err' else ORANJE, h=4.6)
            p.ln(2)

    # ------------------------------------------------------------ 4. e-mail
    hoofdstuk('4.', 'E-mailbeveiliging', 'DMARC, SPF en DKIM: voorkomen dat criminelen mail versturen uit naam van onze klanten. Bron: DMARC-rapporten via EasyDMARC.')
    if not (em.get('configured') and em.get('kpi')):
        niet('Er is geen EasyDMARC-koppeling ingesteld.')
    else:
        k = em['kpi']
        tegels([('DMARC-naleving', _pct(k['pct']), f"{_nl(k['passed'])} van {_nl(k['volume'])} berichten geslaagd", _kl(k['pct'])),
                ('Domeinen beschermd', f"{_nl(k['protected'])}/{_nl(k['domains'])}", 'beleid reject of quarantine', GROEN if k['protected'] == k['domains'] else ORANJE),
                ('Domeinen met actie', _nl(k['domErr']), f"{_nl(k['domWarn'])} met aandachtspunten", ROOD if k['domErr'] else GROEN)])
        if k['passed'] + k['failed']:
            kop('Geslaagd en gefaald (alle gemeten mail)', blok=18)
            verdeling([('Geslaagd', k['passed'], GROEN), ('Gefaald', k['failed'], ROOD)])
        kop('DMARC-beleid van alle domeinen', blok=54)
        pol = em['policies']
        y0 = p.get_y()
        delen = [('Weigeren (reject)', pol['reject'], GROEN), ('Quarantaine', pol['quarantine'], BLAUW), ('Alleen monitoren', pol['none'], ORANJE),
                 ('Geen DMARC', pol['missing'], ROOD)]
        G.donut(p, 44, y0 + 23, 22, delen, _nl(k['domains']), 'domeinen')
        G.legenda(p, 74, y0 + 11, delen, 62)
        G.meter(p, 162, y0 + 32, 24, k['pct'], 'DMARC-naleving')
        p.set_y(y0 + 50)
        kop('Per klant', blok=min(80, 7 + 6.5 * len(em['customers'])))
        tabel([('Klant', .34, 'L'), ('Status', .14, 'L'), ('Domeinen', .12, 'R'), ('Berichten', .14, 'R'), ('Geslaagd', .13, 'R'), ('Gefaald', .13, 'R')],
              [[c['name'], STATUS_NL.get(c['status'], c['status']), _nl(c['domains']), _nl(c['volume']), _pct(c['pct']),
                _pct(round(100 - c['pct'], 1)) if c['pct'] is not None else '-'] for c in em['customers']],
              [[None, KLEUR.get(c['status']), None, None, GROEN if c['pct'] is not None else None, ROOD if c['pct'] is not None and c['pct'] < 100 else None]
               for c in em['customers']])
        acties = [(c['name'], i) for c in em['customers'] for i in c['issues'] if i['status'] == 'err']
        if acties:
            kop('Domeinen die actie vragen')
            for naam, i in acties:
                tekst(f"- {i['domain']} ({naam}): {i['text']}", 8.8, ROOD, h=4.6)

    # ------------------------------------------------------------ 5. Microsoft 365
    hoofdstuk('5.', 'Microsoft 365', 'Toegang tot de klantomgevingen (GDAP) en licentiegebruik. Bron: Microsoft 365 via GDAP.')
    tegels([('Klanten', _nl(gd['customers']), 'met een GDAP-relatie', NAVY),
            ('Met toegang', _nl(gd['access']), f"{_nl(gd['noAccess'])} zonder (volledige) toegang", GROEN if not gd['noAccess'] else ORANJE),
            ('Verloopt binnen 30 dagen', _nl(len(gd['expiring'])), 'GDAP-relaties om te verlengen', ORANJE if gd['expiring'] else GROEN)])
    if gd['expiring']:
        kop('GDAP-relaties die binnenkort verlopen', blok=min(80, 7 + 6.5 * len(gd['expiring'])))
        tabel([('Klant', .60, 'L'), ('Einddatum', .20, 'R'), ('Dagen', .20, 'R')],
              [[x['name'], x['end'][8:10] + '-' + x['end'][5:7] + '-' + x['end'][:4] if x['end'] else '-', _nl(x['days'])] for x in gd['expiring']])
    kop('Licenties')
    if not lic.get('loaded'):
        niet('Het licentieoverzicht is nog niet opgehaald (tabblad Management > Licenties ophalen, of Administratie).')
    else:
        tegels([('Betaalde licenties', _nl(lic['bought']), f"bij {_nl(lic['customers'])} klanten", NAVY),
                ('Toegewezen', _nl(lic['assigned']), f"benutting {_pct(lic['usePct'])}", GROEN if (lic['usePct'] or 0) >= 90 else ORANJE),
                ('Mogelijk overbodig', _nl(lic['saving']), f"{_nl(lic['free'])} vrij, {_nl(lic['disabled'])} uitgeschakeld, {_nl(lic['unused'])} >90 d niet gebruikt",
                 ORANJE if lic['saving'] else GROEN)])
        verdeling([('In gebruik', max(lic['assigned'] - lic['disabled'] - lic['unused'], 0), GROEN), ('Uitgeschakeld', lic['disabled'], ORANJE),
                   ('Niet gebruikt (>90 d)', lic['unused'], ROOD), ('Vrij', lic['free'], GRIJS)])
        top = [r for r in lic['perCustomer'] if r['saving']][:10]
        if top:
            kop('Grootste besparingsmogelijkheden (top 10)', blok=6 * len(top) + 4)
            staven([(r['name'], r['saving']) for r in top], '', ORANJE)
        if lic['renewals']:
            kop('Verlengingen binnen 45 dagen', blok=min(80, 7 + 6.5 * len(lic['renewals'])))
            tabel([('Klant', .32, 'L'), ('Licentie', .34, 'L'), ('Datum', .14, 'R'), ('Toegewezen', .20, 'R')],
                  [[r['customer'], r['name'], r['date'], f"{_nl(r['assigned'])}/{_nl(r['bought'])}"] for r in lic['renewals']])

    # ------------------------------------------------------------ bijlage
    hoofdstuk('B.', 'Bijlage: gegevens per klant', 'Alle onderliggende cijfers per klant, als naslag bij de hoofdstukken.')
    if at and at['customers']:
        kop('Servicedesk per klant', 2)
        tabel([('Klant', .40, 'L'), ('Nieuw', .12, 'R'), ('Afgerond', .12, 'R'), ('Open', .12, 'R'), ('Uren', .12, 'R'), ('Facturabel', .12, 'R')],
              [[r['name'], _nl(r['created']), _nl(r['completed']), _nl(r['open']), _nl(r['hours'], 1), _nl(r['billable'], 1)] for r in at['customers']])
    if bk.get('configured') and bk.get('customers'):
        kop('Back-up per klant', blok=min(60, 7 + 6.5 * len(bk['customers'])))
        tabel([('Klant', .40, 'L'), ('Status', .16, 'L'), ('Geslaagd', .11, 'R'), ('Waarsch.', .11, 'R'), ('Mislukt', .11, 'R'), ('Overig', .11, 'R')],
              [[c['name'], STATUS_NL.get(c['status'], c['status']), _nl(c['ok']), _nl(c['warn']), _nl(c['err']), _nl(c['unknown'] + c['paused'])] for c in bk['customers']],
              [[None, KLEUR.get(c['status'])] for c in bk['customers']])
    if lic.get('loaded') and lic['perCustomer']:
        kop('Licenties per klant', blok=min(60, 7 + 6.5 * len(lic['perCustomer'])))
        tabel([('Klant', .34, 'L'), ('Ingekocht', .11, 'R'), ('Toegewezen', .12, 'R'), ('Vrij', .10, 'R'), ('Uitgesch.', .11, 'R'), ('>90 d', .10, 'R'), ('Overbodig', .12, 'R')],
              [[r['name'], _nl(r['bought']), _nl(r['assigned']), _nl(r['free']), _nl(r['disabled']), _nl(r['unused']), _nl(r['saving'])] for r in lic['perCustomer']])
    p.ln(4)
    tekst('Toelichting: "mogelijk overbodig" = vrije licenties plus licenties van uitgeschakelde accounts en accounts die meer dan 90 dagen niet hebben '
          'aangemeld (alleen betaalde licenties). Doorlooptijd = tijd tussen aanmaken en afronden van een ticket. Facturabel = uren die niet als '
          'niet-facturabel zijn geregistreerd.', 8.5, GRIJS, h=4.4)
    return bytes(p.output())
