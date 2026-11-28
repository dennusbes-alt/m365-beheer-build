"""Factuurspecificatie als PDF (huisstijl Justdata): per klant de factureerbare uren buiten de full-service-contracten,
tickets op 'Ready to Invoice', subtotaal, btw en totaal. De officiële factuur maakt Exact; dit is de onderbouwing erbij."""
from __future__ import annotations

from datetime import datetime

from .h_rapport import BLAUW, CYAAN, GRIJS, LEI, MAP, NAVY, _nl_datum

LICHT = (244, 247, 250)
RAND = (220, 228, 235)


def _eur(v: float) -> str:
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'EUR {s}'


def _uur(v: float) -> str:
    return f'{v:.2f}'.replace('.', ',')


def _datum(s: str) -> str:
    try:
        return datetime.fromisoformat(s[:10]).strftime('%d-%m-%Y')
    except ValueError:
        return s


def maak_pdf(k: dict, dagen: int, door: str = '') -> bytes:
    from fpdf import FPDF
    nu = datetime.now()

    class Pdf(FPDF):
        def footer(self):
            self.set_y(-13)
            self.set_draw_color(*RAND)
            self.line(20, self.get_y() - 1, 190, self.get_y() - 1)
            self.set_font('Lato', '', 8)
            self.set_text_color(*GRIJS)
            self.cell(85, 6, f"Justdata  |  Factuurspecificatie {k['name'][:40]}")
            self.cell(85, 6, f'{_nl_datum(nu)}  |  Pagina {self.page_no()} van {{nb}}', align='R')

    p = Pdf(format='A4')
    p.set_auto_page_break(True, margin=18)
    p.set_margins(20, 18, 20)
    for stijl, bestand in (('', 'Regular'), ('B', 'Bold'), ('I', 'Regular'), ('BI', 'Bold')):
        p.add_font('Lato', stijl, str(MAP / f'Lato-{bestand}.ttf'))
    p.add_font('LatoBlack', '', str(MAP / 'Lato-Black.ttf'))
    p.alias_nb_pages()
    p.add_page()
    B = p.epw

    # Kop: logo + titel
    p.image(str(MAP / 'logo.png'), x=20, y=16, h=13)
    p.set_xy(110, 16)
    p.set_font('LatoBlack', '', 18)
    p.set_text_color(*NAVY)
    p.cell(80, 8, 'Factuurspecificatie', align='R', new_x='LMARGIN', new_y='NEXT')
    p.set_x(110)
    p.set_font('Lato', '', 9)
    p.set_text_color(*GRIJS)
    p.cell(80, 5, f'Datum: {nu:%d-%m-%Y}', align='R', new_x='LMARGIN', new_y='NEXT')
    p.ln(10)

    # Klant en samenvatting
    p.set_font('Lato', '', 9)
    p.set_text_color(*GRIJS)
    p.cell(B, 5, 'Klant', new_x='LMARGIN', new_y='NEXT')
    p.set_font('LatoBlack', '', 14)
    p.set_text_color(*NAVY)
    p.cell(B, 7, k['name'], new_x='LMARGIN', new_y='NEXT')
    p.set_font('Lato', '', 9.5)
    p.set_text_color(*LEI)
    datums = [l['date'] for l in k['lines'] if l['date']]
    periode = f"{_datum(min(datums))} t/m {_datum(max(datums))}" if datums else '-'
    p.cell(B, 5.5, f"Periode werkzaamheden: {periode}   |   {_uur(k['hours'])} uur   |   {len(k['tickets'])} ticket(s)", new_x='LMARGIN', new_y='NEXT')
    if k.get('approved'):
        a = k['approved']
        p.cell(B, 5.5, f"Goedgekeurd door {a.get('by') or '-'} op {str(a.get('at') or '').replace('T', ' ')}", new_x='LMARGIN', new_y='NEXT')
    p.ln(4)

    # Tabel met regels
    kol = [('Datum', 19), ('Ticket', 26), ('Werkzaamheden', 52), ('Medewerker', 24), ('Uren', 11), ('Tarief', 17)]
    rest = B - sum(w for _, w in kol)
    kol.append(('Bedrag', rest))

    def kop():
        p.set_fill_color(*NAVY)
        p.set_text_color(255, 255, 255)
        p.set_font('Lato', 'B', 8.5)
        for t, w in kol:
            p.cell(w, 7, ' ' + t, fill=True, align='R' if t in ('Uren', 'Tarief', 'Bedrag') else 'L')
        p.ln(7)
    kop()
    p.set_font('Lato', '', 8.3)
    for n, l in enumerate(k['lines']):
        omschrijving = (l['title'] + (': ' + l['notes'] if l['notes'] else ''))[:240]
        p.set_font('Lato', '', 8.3)
        regels = p.multi_cell(kol[2][1] - 2, 4.2, omschrijving, dry_run=True, output='LINES', align='L')
        h = max(6.5, 4.2 * len(regels) + 2.2)
        if p.get_y() + h > p.h - 22:
            p.add_page()
            kop()
            p.set_font('Lato', '', 8.3)
        y = p.get_y()
        if n % 2:
            p.set_fill_color(*LICHT)
            p.rect(20, y, B, h, 'F')
        p.set_text_color(*LEI)
        p.set_xy(20, y + 1)
        p.cell(kol[0][1], 4.2, ' ' + _datum(l['date']))
        p.cell(kol[1][1], 4.2, ' ' + str(l['ref'])[:15])
        x = p.get_x()
        p.set_xy(x + 1, y + 1)
        p.multi_cell(kol[2][1] - 2, 4.2, omschrijving, align='L')
        p.set_xy(x + kol[2][1], y + 1)
        p.cell(kol[3][1], 4.2, ' ' + str(l['employee'])[:18])
        p.cell(kol[4][1], 4.2, (f"{l.get('qty') or 1:g} st" if l.get('kind') == 'product' else 'vast' if l.get('kind') == 'fixed' else _uur(l['hours'])), align='R')
        p.cell(kol[5][1], 4.2, _eur(l['rate']) if l['rate'] else '-', align='R')
        p.cell(kol[6][1], 4.2, _eur(l['amount']), align='R')
        p.set_xy(20, y + h)
    p.set_draw_color(*RAND)
    p.line(20, p.get_y(), 190, p.get_y())
    p.ln(3)

    # Tickets op Ready to Invoice (bijv. licenties)
    rti = [t for t in k['tickets'] if t['rti']]
    if rti:
        if p.get_y() > p.h - 50:
            p.add_page()
        p.set_font('Lato', 'B', 9.5)
        p.set_text_color(*NAVY)
        p.cell(B, 6, 'Te factureren via Exact (bijv. licentiewijzigingen)', new_x='LMARGIN', new_y='NEXT')
        p.set_font('Lato', '', 8.8)
        p.set_text_color(*LEI)
        for t in rti:
            p.cell(B, 5, f"  {t['number']}  {t['title'][:110]}", new_x='LMARGIN', new_y='NEXT')
        p.ln(3)

    # Totalen
    if p.get_y() > p.h - 45:
        p.add_page()
    x = 20 + B - 80
    for label, waarde, vet in (('Subtotaal', k['subtotal'], False), ('Btw 21%', k['vat'], False), ('Totaal', k['total'], True)):
        p.set_x(x)
        p.set_font('LatoBlack' if vet else 'Lato', '', 11 if vet else 9.5)
        p.set_text_color(*(NAVY if vet else LEI))
        if vet:
            p.set_draw_color(*CYAAN)
            p.set_line_width(0.6)
            p.line(x, p.get_y(), 190, p.get_y())
            p.set_line_width(0.2)
            p.ln(1)
            p.set_x(x)
        p.cell(45, 7, label)
        p.cell(35, 7, _eur(waarde), align='R', new_x='LMARGIN', new_y='NEXT')
    p.ln(6)
    p.set_font('Lato', '', 8.5)
    p.set_text_color(*GRIJS)
    p.multi_cell(B, 4.5, 'Deze specificatie hoort bij de factuur uit Exact en bevat de werkzaamheden buiten het full-service-contract. '
                         f'Bedragen exclusief en inclusief 21% btw. Opgesteld met Microsoft 365 beheer van Justdata{(" door " + door) if door else ""}.',
                 new_x='LMARGIN', new_y='NEXT')
    p.ln(2)
    p.set_text_color(*BLAUW)
    return bytes(p.output())
