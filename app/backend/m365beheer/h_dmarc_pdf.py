"""PDF-rapportage e-mailbeveiliging (DMARC) per klant, in begrijpelijke taal (zelfde huisstijl als het NEN 7510-rapport)."""
from __future__ import annotations

from datetime import datetime

from .h_rapport import BLAUW, CYAAN, GRIJS, GROEN, LEI, MAP, NAVY, ORANJE, ROOD, _nl_datum   # noqa: F401

UITLEG = {
    'reject': 'Mail die zich voordoet als uw organisatie maar niet van u komt, wordt geweigerd. Dit is de sterkste bescherming.',
    'quarantine': 'Mail die zich voordoet als uw organisatie maar niet van u komt, komt bij de ontvanger in de spam of quarantaine.',
    'none': 'DMARC staat op monitoren: we zien wie er namens uw domein mailt, maar nepmail wordt nog niet tegengehouden.',
    'missing': 'Er is geen DMARC ingesteld: iedereen kan mail versturen uit naam van dit domein.',
}
STATUS = {'ok': ('In orde', GROEN), 'warn': ('Aandachtspunt', ORANJE), 'err': ('Actie nodig', ROOD)}


def maak_pdf(org: dict, afzenders: dict, dagen: int) -> bytes:
    from fpdf import FPDF
    nu = datetime.now()
    klant = org['name']

    class Rapport(FPDF):
        def footer(self):
            if self.page_no() == 1:
                return
            self.set_y(-14)
            self.set_font('Lato', '', 8)
            self.set_text_color(*GRIJS)
            self.cell(0, 6, f'E-mailbeveiliging {klant}  |  {_nl_datum(nu)}  |  Pagina {self.page_no()} van {{nb}}', align='R')

    p = Rapport(format='A4')
    p.set_auto_page_break(True, margin=20)
    p.set_margins(20, 18, 20)
    for stijl, bestand in (('', 'Regular'), ('B', 'Bold'), ('I', 'Regular'), ('BI', 'Bold')):
        p.add_font('Lato', stijl, str(MAP / f'Lato-{bestand}.ttf'))
    p.add_font('LatoBlack', '', str(MAP / 'Lato-Black.ttf'))
    p.alias_nb_pages()
    B = p.epw

    def mc(*a, **k):
        return p.multi_cell(*a, **{'new_x': 'LMARGIN', 'new_y': 'NEXT', **k})

    def kop(t, g=16, kl=NAVY, voor=4):
        p.ln(voor)
        p.set_font('LatoBlack', '', g)
        p.set_text_color(*kl)
        mc(B, g * 0.5, t)
        p.ln(2)

    def tekst(t, g=10, kl=LEI, st='', h=5.2):
        p.set_font('Lato', st, g)
        p.set_text_color(*kl)
        mc(B, h, t)

    # Titelpagina
    p.add_page()
    p.set_fill_color(*BLAUW)
    p.rect(0, 0, 210, 92, 'F')
    p.set_fill_color(255, 255, 255)
    p.rect(20, 20, 64, 20, 'F')
    p.image(str(MAP / 'logo.png'), x=23, y=22, h=16)
    p.set_xy(20, 52)
    p.set_font('LatoBlack', '', 26)
    p.set_text_color(255, 255, 255)
    mc(B, 11, 'E-mailbeveiliging\nDMARC-rapportage')
    p.set_xy(20, 104)
    p.set_font('Lato', '', 11)
    p.set_text_color(*GRIJS)
    p.cell(0, 6, 'Opgesteld voor')
    p.set_xy(20, 111)
    p.set_font('LatoBlack', '', 20)
    p.set_text_color(*NAVY)
    mc(B, 9, klant)
    p.ln(6)
    for k, v in (('Datum', _nl_datum(nu)), ('Periode', f'laatste {dagen} dagen'), ('Opgesteld door', 'Justdata'), ('Bron', 'DMARC-rapporten van ontvangende mailservers (via EasyDMARC)')):
        p.set_font('Lato', '', 10)
        p.set_text_color(*GRIJS)
        p.cell(38, 7, k)
        p.set_font('Lato', 'B', 10)
        p.set_text_color(*LEI)
        mc(B - 38, 7, v)
    p.ln(8)
    naam, kl = STATUS.get(org['status'], STATUS['warn'])
    p.set_fill_color(*kl)
    p.set_text_color(255, 255, 255)
    p.set_font('LatoBlack', '', 13)
    mc(B, 10, f"  Status: {naam}" + (f" - {org['compliance']}% van de mail voldoet aan DMARC" if org.get('compliance') is not None else ''), fill=True)

    # Samenvatting
    p.add_page()
    kop('1. Samenvatting', 18)
    tekst('DMARC, SPF en DKIM zorgen ervoor dat ontvangers kunnen controleren of mail echt van uw organisatie komt. Zo wordt voorkomen dat '
          'criminelen mail versturen uit uw naam (bijvoorbeeld nepfacturen aan uw klanten). Dit rapport laat zien hoe uw domeinen ervoor staan '
          'en wat er nog verbeterd kan worden.')
    p.ln(3)
    tekst(f"Aantal domeinen: {len(org['domains'])}   |   Verzonden berichten (gemeten): {org['volume']:,}".replace(',', '.'), 10, NAVY, 'B')
    if org.get('compliance') is not None:
        tekst(f"Geslaagd voor DMARC: {org.get('passed', 0):,} berichten ({org['compliance']}%)   |   Gefaald: {org.get('failed', 0):,} berichten ({round(100 - org['compliance'], 1)}%)".replace(',', '.'), 10, NAVY, 'B')
    p.ln(3)
    p.set_font('Lato', 'B', 9)
    p.set_fill_color(*NAVY)
    p.set_text_color(255, 255, 255)
    kol = [B * .30, B * .19, B * .15, B * .14, B * .11, B * .11]
    for w, t in zip(kol, ('  Domein', 'Beleid', 'Geslaagd', 'Gefaald', 'SPF', 'DKIM')):
        p.cell(w, 7, t, fill=True)
    p.ln(7)
    for i, d in enumerate(org['domains']):
        p.set_fill_color(*((244, 247, 250) if i % 2 else (255, 255, 255)))
        p.set_font('Lato', '', 9)
        p.set_text_color(*LEI)
        p.cell(kol[0], 7, '  ' + d['domain'][:38], fill=True)
        p.cell(kol[1], 7, d['policyText'], fill=True)
        heeft = d['compliance'] is not None and d['volume']
        p.set_text_color(*GROEN)
        p.cell(kol[2], 7, f"{d['compliance']}%" if heeft else '-', fill=True)
        p.set_text_color(*(ROOD if heeft and d.get('failPct') else LEI))
        p.cell(kol[3], 7, f"{d.get('failPct')}%" if heeft else '-', fill=True)
        p.set_text_color(*LEI)
        for w, k in ((kol[4], 'spf'), (kol[5], 'dkim')):
            v = d[k]
            p.set_text_color(*(GROEN if v == 'valid' else ORANJE if v == 'warning' else GRIJS if v == 'unknown' else ROOD))
            p.cell(w, 7, {'valid': 'In orde', 'warning': 'Waarschuwing', 'no-record': 'Ontbreekt', 'unknown': 'Onbekend'}.get(v, v), fill=True)
            p.set_text_color(*LEI)
        p.ln(7)

    # Per domein
    p.add_page()
    kop('2. Per domein', 18)
    for d in org['domains']:
        if p.get_y() > 235:
            p.add_page()
        naam, kl = STATUS.get(d['status'], STATUS['warn'])
        p.set_draw_color(220, 228, 235)
        p.line(20, p.get_y(), 190, p.get_y())
        p.ln(2)
        p.set_font('LatoBlack', '', 12)
        p.set_text_color(*NAVY)
        p.cell(B - 40, 7, d['domain'])
        p.set_font('Lato', 'B', 8.5)
        p.set_fill_color(*kl)
        p.set_text_color(255, 255, 255)
        p.cell(38, 6, naam, fill=True, align='C', new_x='LMARGIN', new_y='NEXT')
        tekst(UITLEG.get(d['policy'], ''), 9.5)
        if d['volume']:
            tekst(f"{d['volume']:,} berichten gemeten: {d.get('passed', 0):,} geslaagd ({d['compliance']}%) en {d.get('failed', 0):,} gefaald ({d.get('failPct')}%). "
                  f"SPF geslaagd {d['spfPass']}%, DKIM geslaagd {d['dkimPass']}%.".replace(',', '.'), 9, GRIJS)
        for pr in d['problems']:
            tekst(f"- {pr['text']}", 9.5, ROOD if pr['level'] == 'err' else ORANJE if pr['level'] == 'warn' else GRIJS)
        for a in (afzenders.get(d['domain']) or [])[:5]:
            tekst(f"   Afzender {a['name']}: {a['count']} bericht(en) - {a['reason']}", 8.5, LEI, h=4.6)
        p.ln(2)

    # Advies
    if p.get_y() > 200:
        p.add_page()
    kop('3. Advies', 14, voor=6)
    adv = []
    if any(d['policy'] in ('none', 'missing') for d in org['domains']):
        adv.append('Zet DMARC stapsgewijs van "none" naar "quarantine" en daarna "reject" zodra alle eigen diensten slagen.')
    if any(d['spf'] != 'valid' for d in org['domains']):
        adv.append('Herstel de SPF-records met een waarschuwing of zonder record.')
    if any(d['dkim'] != 'valid' and d['type'] != 'parked' for d in org['domains']):
        adv.append('Zet DKIM aan voor alle diensten die namens uw domein mailen (Microsoft 365, nieuwsbrief, CRM, boekhoudpakket).')
    if any(afzenders.values()):
        adv.append('Controleer de genoemde afzenders: eigen diensten toevoegen aan SPF/DKIM; onbekende afzenders zijn vaak misbruik.')
    if not adv:
        adv.append('Alles is goed ingericht. Wij blijven de rapporten maandelijks controleren.')
    for a in adv:
        tekst(f'- {a}', 10)
    return bytes(p.output())
