"""Grafieken voor de PDF-rapporten (fpdf2, zonder extra bibliotheken): donut, meter, kolommen, lijn en staven.

Alle functies tekenen op een bestaande FPDF-pagina op (x, y) in mm en laten de cursor ongemoeid, tenzij anders vermeld.
Kleuren zijn RGB-tuples (huisstijl uit h_rapport).
"""
from __future__ import annotations

import math

from .h_rapport import BLAUW, GRIJS, GROEN, LEI, NAVY, ORANJE, ROOD

LICHT = (238, 243, 247)
RAND = (220, 228, 235)
WIT = (255, 255, 255)
PALET = [BLAUW, (0, 174, 239), NAVY, (91, 192, 222), (120, 144, 168), (0, 120, 150), (170, 200, 220), (60, 90, 120)]


def nl(n, dec: int = 0) -> str:
    if n is None:
        return '-'
    s = f'{n:,.{dec}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def _boog(cx, cy, r, a0, a1, stappen=None):
    """Punten op een cirkelboog; hoeken in graden, 0 = boven, met de klok mee."""
    n = stappen or max(2, int(abs(a1 - a0) / 3) + 1)
    return [(cx + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)), cy - r * math.cos(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def ring(p, cx, cy, r_buiten, r_binnen, a0, a1, kleur) -> None:
    if a1 - a0 <= 0.05:
        return
    p.set_fill_color(*kleur)
    p.polygon(_boog(cx, cy, r_buiten, a0, a1) + _boog(cx, cy, r_binnen, a1, a0), style='F')


def donut(p, cx, cy, r, delen: list[tuple], midden: str = '', sub: str = '', dikte: float = 0.34) -> None:
    """delen = (label, waarde, kleur). Middelpunt (cx, cy), straal r (mm)."""
    tot = sum(max(v or 0, 0) for _, v, _ in delen)
    binnen = r * (1 - dikte)
    if not tot:
        ring(p, cx, cy, r, binnen, 0, 359.99, LICHT)
    else:
        a = 0.0
        for _, v, kl in delen:
            b = a + 360 * max(v or 0, 0) / tot
            ring(p, cx, cy, r, binnen, a, b - (0.8 if len([d for d in delen if d[1]]) > 1 else 0), kl)
            a = b
    if midden:
        p.set_font('LatoBlack', '', max(9, r * 0.62))
        p.set_text_color(*NAVY)
        p.set_xy(cx - binnen, cy - (r * 0.22 if sub else r * 0.14) - 1)
        p.cell(binnen * 2, r * 0.3, midden, align='C')
    if sub:
        p.set_font('Lato', '', max(6.5, r * 0.2))
        p.set_text_color(*GRIJS)
        p.set_xy(cx - binnen, cy + r * 0.12)
        p.cell(binnen * 2, r * 0.2, sub, align='C')


def legenda(p, x, y, delen: list[tuple], w: float = 60, regel: float = 6, pct: bool = True) -> float:
    """Verticale legenda naast een donut; geeft de y onder de legenda terug."""
    tot = sum(v or 0 for _, v, _ in delen) or 1
    for label, v, kl in delen:
        p.set_fill_color(*kl)
        p.rect(x, y + regel / 2 - 1.5, 3, 3, style='F', round_corners=True, corner_radius=0.7)
        p.set_xy(x + 5, y)
        p.set_font('Lato', '', 8.5)
        p.set_text_color(*LEI)
        t = str(label)
        while p.get_string_width(t) > w - 24 and len(t) > 4:
            t = t[:-2]
        p.cell(w - 23, regel, t if t == str(label) else t[:-1] + '…')
        p.set_font('Lato', 'B', 8.5)
        p.cell(18, regel, f"{nl(v)}{'  (' + str(round((v or 0) * 100 / tot)) + '%)' if pct else ''}", align='R')
        y += regel
    return y


def meter(p, cx, cy, r, pct, label: str = '', drempels=(95, 85)) -> None:
    """Halve-cirkelmeter (0-100%). Kleur volgens drempels (groen >= eerste, oranje >= tweede, anders rood)."""
    ring(p, cx, cy, r, r * 0.7, -90, 90, LICHT)
    if pct is not None:
        kl = GROEN if pct >= drempels[0] else ORANJE if pct >= drempels[1] else ROOD
        ring(p, cx, cy, r, r * 0.7, -90, -90 + 180 * max(0, min(100, pct)) / 100, kl)
        p.set_font('LatoBlack', '', max(10, r * 0.5))
        p.set_text_color(*kl)
        p.set_xy(cx - r, cy - r * 0.42)
        p.cell(2 * r, r * 0.36, f"{nl(pct, 1 if pct % 1 and pct < 99.95 else 0)}%", align='C')
    else:
        p.set_font('LatoBlack', '', max(10, r * 0.5))
        p.set_text_color(*GRIJS)
        p.set_xy(cx - r, cy - r * 0.42)
        p.cell(2 * r, r * 0.36, '-', align='C')
    if label:
        p.set_font('Lato', '', 8)
        p.set_text_color(*GRIJS)
        p.set_xy(cx - r - 6, cy + 1.5)
        p.cell(2 * r + 12, 4, label, align='C')


def _schaal(mx: float) -> tuple[float, float]:
    """Mooie bovengrens en stapgrootte voor een as."""
    if mx <= 0:
        return 4, 1
    ruw = mx / 4
    e = 10 ** math.floor(math.log10(ruw))
    stap = next(s * e for s in (1, 2, 2.5, 5, 10) if s * e >= ruw)
    return stap * math.ceil(mx / stap - 1e-9), stap


def _as(p, x, y, w, h, mx, eenheid='') -> float:
    top, stap = _schaal(mx)
    p.set_draw_color(*RAND)
    p.set_line_width(0.15)
    p.set_font('Lato', '', 6.8)
    p.set_text_color(*GRIJS)
    v = 0.0
    while v <= top + 1e-9:
        yy = y + h - h * v / top
        p.line(x, yy, x + w, yy)
        p.set_xy(x - 11, yy - 2)
        p.cell(10, 4, f'{nl(v, 1 if stap % 1 else 0)}{eenheid}', align='R')
        v += stap
    return top


def kolommen(p, x, y, w, h, labels: list[str], reeksen: list[tuple], eenheid: str = '', waarden: bool = True) -> None:
    """Gegroepeerde kolommen met as en rasterlijnen. reeksen = (naam, [waarden], kleur). x is de linkerrand van het plotvlak."""
    mx = max((v for _, vs, _ in reeksen for v in vs), default=0)
    top = _as(p, x, y, w, h, mx, eenheid)
    n = len(labels) or 1
    groep = w / n
    kw = min(groep * 0.7 / max(1, len(reeksen)), 16)
    for i, lab in enumerate(labels):
        x0 = x + i * groep + (groep - kw * len(reeksen)) / 2
        for j, (_, vs, kl) in enumerate(reeksen):
            v = vs[i] if i < len(vs) else 0
            hh = h * v / top if top else 0
            if hh > 0:
                p.set_fill_color(*kl)
                p.rect(x0 + j * kw + 0.4, y + h - hh, kw - 0.8, hh, style='F', round_corners=hh > 2, corner_radius=0.8)
            if waarden:
                p.set_font('Lato', 'B', 7)
                p.set_text_color(*LEI)
                p.set_xy(x0 + j * kw - 2, y + h - hh - 4.2)
                p.cell(kw + 4, 4, nl(v, 1 if isinstance(v, float) and v % 1 else 0), align='C')
        p.set_font('Lato', '', 7.5)
        p.set_text_color(*GRIJS)
        p.set_xy(x + i * groep, y + h + 1.2)
        p.cell(groep, 4, str(lab), align='C')
    p.set_draw_color(*GRIJS)
    p.set_line_width(0.25)
    p.line(x, y + h, x + w, y + h)
    p.set_line_width(0.2)
    if len(reeksen) > 1:
        lx = x
        for naam, _, kl in reeksen:
            p.set_fill_color(*kl)
            p.rect(lx, y + h + 7.2, 3, 3, style='F', round_corners=True, corner_radius=0.7)
            p.set_xy(lx + 4.5, y + h + 6.5)
            p.set_font('Lato', '', 8)
            p.set_text_color(*LEI)
            p.cell(p.get_string_width(naam) + 2, 4.5, naam)
            lx += p.get_string_width(naam) + 12


def lijn(p, x, y, w, h, labels: list[str], reeksen: list[tuple], eenheid: str = '', vlak: bool = True, elke: int = 1) -> None:
    """Lijngrafiek met (lichte) vlakvulling onder de eerste reeks. reeksen = (naam, [waarden], kleur)."""
    mx = max((v for _, vs, _ in reeksen for v in vs), default=0)
    top = _as(p, x, y, w, h, mx, eenheid)
    n = max(len(labels), 2)
    px = lambda i: x + w * i / (n - 1)  # noqa: E731
    py = lambda v: y + h - (h * v / top if top else 0)  # noqa: E731
    for j, (_, vs, kl) in enumerate(reeksen):
        pts = [(px(i), py(v)) for i, v in enumerate(vs)]
        if vlak and j == 0 and len(pts) > 1:
            licht = tuple(int(c + (255 - c) * 0.82) for c in kl)
            p.set_fill_color(*licht)
            p.polygon(pts + [(pts[-1][0], y + h), (pts[0][0], y + h)], style='F')
        p.set_draw_color(*kl)
        p.set_line_width(0.7)
        if len(pts) > 1:
            p.polyline(pts)
        p.set_fill_color(*WIT)
        for (a, b) in pts:
            p.set_line_width(0.5)
            p.circle(a, b, 0.9, style='DF')
    p.set_line_width(0.2)
    p.set_font('Lato', '', 7)
    p.set_text_color(*GRIJS)
    for i, lab in enumerate(labels):
        if i % elke == 0 or i == len(labels) - 1:
            p.set_xy(px(i) - 9, y + h + 1.2)
            p.cell(18, 4, str(lab), align='C')
    if len(reeksen) > 1:
        lx = x
        for naam, _, kl in reeksen:
            p.set_draw_color(*kl)
            p.set_line_width(0.8)
            p.line(lx, y + h + 8.5, lx + 5, y + h + 8.5)
            p.set_xy(lx + 6.5, y + h + 6.3)
            p.set_font('Lato', '', 8)
            p.set_text_color(*LEI)
            p.cell(p.get_string_width(naam) + 2, 4.5, naam)
            lx += p.get_string_width(naam) + 14
        p.set_line_width(0.2)


def staven(p, x, y, w, rijen: list[tuple], eenheid: str = '', kl=BLAUW, label_w: float = 52, regel: float = 7.2, dec: int | None = None) -> float:
    """Horizontale staven met afgeronde balken; rijen = (label, waarde). Geeft de y onder de staven terug."""
    mx = max((v for _, v in rijen), default=0) or 1
    bw = w - label_w - 20
    for i, (label, v) in enumerate(rijen):
        yy = y + i * regel
        p.set_font('Lato', '', 8.5)
        p.set_text_color(*LEI)
        t = str(label)
        while p.get_string_width(t) > label_w - 3 and len(t) > 4:
            t = t[:-2]
        p.set_xy(x, yy)
        p.cell(label_w, regel - 1.5, t if t == str(label) else t[:-1] + '…')
        p.set_fill_color(*LICHT)
        p.rect(x + label_w, yy + 1.2, bw, regel - 4, style='F', round_corners=True, corner_radius=1.2)
        if v:
            p.set_fill_color(*(kl[i % len(kl)] if isinstance(kl, list) else kl))
            p.rect(x + label_w, yy + 1.2, max(bw * v / mx, 2.6), regel - 4, style='F', round_corners=True, corner_radius=1.2)
        p.set_xy(x + label_w + bw, yy)
        p.set_font('Lato', 'B', 8.5)
        d = dec if dec is not None else (1 if isinstance(v, float) and v % 1 else 0)
        p.cell(20, regel - 1.5, f'{nl(v, d)}{eenheid}', align='R')
    return y + len(rijen) * regel
