// Grafieken (SVG, geen extra bibliotheken) voor Management: lijn, kolommen, donut, meter, staven en sparkline.
// Kleuren als CSS-variabelenaam ('hd', 'gr', 'or', 'rd', 'navy', 'cy', 'mu2'); hover toont de waarden.
import { useEffect, useRef, useState } from 'react';

export const nl = (n, d = 0) => (n == null ? '-' : Number(n).toLocaleString('nl-NL', { minimumFractionDigits: d, maximumFractionDigits: d }));
const kv = (k) => (k && k.startsWith('#') ? k : `var(--${k || 'hd'})`);
export const PALET = ['hd', 'cy', 'navy', 'mg5', 'mg6', 'mg7', 'mg8', 'mu2'];

function useBreedte(standaard = 600) {
  const ref = useRef(null);
  const [w, setW] = useState(standaard);
  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(200, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function schaal(mx) {
  if (mx <= 0) return [4, 1];
  const ruw = mx / 4;
  const e = 10 ** Math.floor(Math.log10(ruw));
  const stap = [1, 2, 2.5, 5, 10].map((s) => s * e).find((s) => s >= ruw);
  return [stap * Math.ceil(mx / stap - 1e-9), stap];
}

function Legenda({ reeksen }) {
  if (reeksen.length < 2) return null;
  return (
    <div className="mg-legenda">
      {reeksen.map((r) => <span key={r.naam}><i style={{ background: kv(r.kleur) }} />{r.naam}</span>)}
    </div>);
}

function Tip({ x, y, w, titel, regels }) {
  const links = x > w * 0.62;
  return (
    <div className="mg-tip" style={{ left: links ? undefined : x + 12, right: links ? w - x + 12 : undefined, top: Math.max(0, y - 10) }}>
      <b>{titel}</b>
      {regels.map(([k, n, v]) => <div key={n}><i style={{ background: kv(k) }} />{n}<span>{v}</span></div>)}
    </div>);
}

// Lijngrafiek met vlakvulling (verloop) onder elke reeks. reeksen = [{naam, kleur, waarden}]
export function Lijn({ labels, reeksen, eenheid = '', hoogte = 230, dec = 0 }) {
  const [ref, w] = useBreedte();
  const [hov, setHov] = useState(null);
  const L = 40; const R = 12; const T = 14; const Bm = 26;
  const pw = w - L - R; const ph = hoogte - T - Bm;
  const [top, stap] = schaal(Math.max(0, ...reeksen.flatMap((r) => r.waarden)));
  const n = Math.max(labels.length, 2);
  const px = (i) => L + (pw * i) / (n - 1);
  const py = (v) => T + ph - (ph * v) / top;
  const ticks = []; for (let v = 0; v <= top + 1e-9; v += stap) ticks.push(v);
  const elke = Math.ceil(labels.length / Math.max(2, Math.floor(pw / 56)));
  const id = useRef(`l${Math.random().toString(36).slice(2, 8)}`).current;
  const pad = (vs) => vs.map((v, i) => `${i ? 'L' : 'M'}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(' ');
  return (
    <div ref={ref} className="mg-graf" onMouseLeave={() => setHov(null)}>
      <svg width={w} height={hoogte} onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const i = Math.round(((e.clientX - r.left - L) / pw) * (n - 1));
        setHov(i >= 0 && i < labels.length ? i : null);
      }}>
        <defs>{reeksen.map((r, j) => (
          <linearGradient key={j} id={`${id}${j}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={kv(r.kleur)} stopOpacity={j ? 0.12 : 0.28} /><stop offset="100%" stopColor={kv(r.kleur)} stopOpacity="0" />
          </linearGradient>))}</defs>
        {ticks.map((v) => <g key={v}><line x1={L} x2={w - R} y1={py(v)} y2={py(v)} className="mg-raster" />
          <text x={L - 8} y={py(v) + 4} textAnchor="end" className="mg-as">{nl(v, stap % 1 ? 1 : 0)}{eenheid}</text></g>)}
        {reeksen.map((r, j) => <path key={`v${j}`} d={`${pad(r.waarden)} L${px(r.waarden.length - 1)},${T + ph} L${L},${T + ph} Z`} fill={`url(#${id}${j})`} />)}
        {reeksen.map((r, j) => <path key={`l${j}`} d={pad(r.waarden)} fill="none" stroke={kv(r.kleur)} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />)}
        {hov != null && <line x1={px(hov)} x2={px(hov)} y1={T} y2={T + ph} className="mg-kruis" />}
        {reeksen.map((r, j) => r.waarden.map((v, i) => (
          <circle key={`${j}-${i}`} cx={px(i)} cy={py(v)} r={hov === i ? 5 : 3} fill="#fff" stroke={kv(r.kleur)} strokeWidth="2" />)))}
        {labels.map((l, i) => (i % elke === 0 || i === labels.length - 1) && <text key={l + i} x={px(i)} y={hoogte - 7} textAnchor="middle" className="mg-as">{l}</text>)}
      </svg>
      {hov != null && <Tip x={px(hov)} y={Math.min(...reeksen.map((r) => py(r.waarden[hov] || 0)))} w={w} titel={labels[hov]}
        regels={reeksen.map((r) => [r.kleur, r.naam, `${nl(r.waarden[hov], dec)}${eenheid}`])} />}
      <Legenda reeksen={reeksen} />
    </div>);
}

// Gegroepeerde kolommen. reeksen = [{naam, kleur, waarden}]
export function Kolommen({ labels, reeksen, eenheid = '', hoogte = 230, dec = 0, waarden = true }) {
  const [ref, w] = useBreedte();
  const [hov, setHov] = useState(null);
  const L = 40; const R = 8; const T = 18; const Bm = 26;
  const pw = w - L - R; const ph = hoogte - T - Bm;
  const [top, stap] = schaal(Math.max(0, ...reeksen.flatMap((r) => r.waarden)));
  const groep = pw / Math.max(1, labels.length);
  const kw = Math.min((groep * 0.66) / reeksen.length, 46);
  const ticks = []; for (let v = 0; v <= top + 1e-9; v += stap) ticks.push(v);
  return (
    <div ref={ref} className="mg-graf" onMouseLeave={() => setHov(null)}>
      <svg width={w} height={hoogte}>
        {ticks.map((v) => <g key={v}><line x1={L} x2={w - R} y1={T + ph - (ph * v) / top} y2={T + ph - (ph * v) / top} className="mg-raster" />
          <text x={L - 8} y={T + ph - (ph * v) / top + 4} textAnchor="end" className="mg-as">{nl(v, stap % 1 ? 1 : 0)}{eenheid}</text></g>)}
        {labels.map((l, i) => {
          const x0 = L + i * groep + (groep - kw * reeksen.length) / 2;
          return (
            <g key={l + i} onMouseEnter={() => setHov(i)}>
              <rect x={L + i * groep} y={T} width={groep} height={ph} fill={hov === i ? 'var(--acl)' : 'transparent'} opacity=".55" rx="6" />
              {reeksen.map((r, j) => {
                const v = r.waarden[i] || 0; const h = (ph * v) / top;
                return (
                  <g key={j}>
                    <rect x={x0 + j * kw + 1.5} y={T + ph - h} width={kw - 3} height={Math.max(h, 0)} rx={Math.min(5, (kw - 3) / 2)} fill={kv(r.kleur)} />
                    {waarden && kw > 16 && <text x={x0 + j * kw + kw / 2} y={T + ph - h - 5} textAnchor="middle" className="mg-waarde">{nl(v, dec)}</text>}
                  </g>);
              })}
              <text x={L + i * groep + groep / 2} y={hoogte - 7} textAnchor="middle" className="mg-as">{l}</text>
            </g>);
        })}
      </svg>
      {hov != null && <Tip x={L + hov * groep + groep / 2} y={T + 10} w={w} titel={labels[hov]} regels={reeksen.map((r) => [r.kleur, r.naam, `${nl(r.waarden[hov], dec)}${eenheid}`])} />}
      <Legenda reeksen={reeksen} />
    </div>);
}

// Donut met legenda; delen = [label, waarde, kleur]
export function Donut({ delen, midden, sub, maat = 170, legenda = true, pct = true }) {
  const [hov, setHov] = useState(null);
  const tot = delen.reduce((s, [, v]) => s + (v || 0), 0);
  const r = maat / 2; const dikte = maat * 0.15; const ri = r - dikte / 2;
  const omtrek = 2 * Math.PI * ri;
  let a = 0;
  const actief = hov != null ? delen[hov] : null;
  return (
    <div className="mg-donut">
      <svg width={maat} height={maat} viewBox={`0 0 ${maat} ${maat}`}>
        <circle cx={r} cy={r} r={ri} fill="none" stroke="var(--bg)" strokeWidth={dikte} />
        {tot > 0 && delen.map(([l, v, k], i) => {
          const len = (omtrek * (v || 0)) / tot;
          const el = (
            <circle key={l} cx={r} cy={r} r={ri} fill="none" stroke={kv(k)} strokeWidth={hov === i ? dikte + 6 : dikte}
              strokeDasharray={`${Math.max(len - (delen.filter((d) => d[1]).length > 1 ? 2 : 0), 0)} ${omtrek}`} strokeDashoffset={-a}
              transform={`rotate(-90 ${r} ${r})`} onMouseEnter={() => setHov(i)} onMouseLeave={() => setHov(null)} style={{ transition: 'stroke-width .15s', cursor: 'default' }} />);
          a += len;
          return el;
        })}
        <text x={r} y={r + (sub ? 2 : 8)} textAnchor="middle" className="mg-donut-n" style={{ fontSize: maat * 0.17 }}>
          {actief ? nl(actief[1]) : midden}</text>
        {(sub || actief) && <text x={r} y={r + maat * 0.13} textAnchor="middle" className="mg-as" style={{ fontSize: Math.max(11, maat * 0.07) }}>
          {actief ? (actief[0].length > 18 ? `${actief[0].slice(0, 17)}…` : actief[0]) : sub}</text>}
      </svg>
      {legenda && (
        <div className="mg-dleg">
          {delen.map(([l, v, k], i) => (
            <div key={l} className={hov === i ? 'aan' : ''} onMouseEnter={() => setHov(i)} onMouseLeave={() => setHov(null)}>
              <i style={{ background: kv(k) }} /><span>{l}</span><b>{nl(v)}</b>{pct && <em>{tot ? `${Math.round(((v || 0) * 100) / tot)}%` : ''}</em>}
            </div>))}
        </div>)}
    </div>);
}

// Halve-cirkelmeter 0-100%
export function Meter({ pct, label, drempels = [95, 85], maat = 190 }) {
  const r = maat / 2 - 10; const cx = maat / 2; const cy = maat / 2 + 4;
  const k = pct == null ? 'mu2' : pct >= drempels[0] ? 'gr' : pct >= drempels[1] ? 'or' : 'rd';
  const boog = (p) => { const a = Math.PI * (1 - p / 100); return [cx + r * Math.cos(a), cy - r * Math.sin(a)]; };
  const [ex, ey] = boog(Math.max(0.5, Math.min(100, pct || 0)));
  return (
    <div className="mg-meter">
      <svg width={maat} height={maat / 2 + 22} viewBox={`0 0 ${maat} ${maat / 2 + 22}`}>
        <path d={`M${cx - r},${cy} A${r},${r} 0 0 1 ${cx + r},${cy}`} fill="none" stroke="var(--bg)" strokeWidth="16" strokeLinecap="round" />
        {pct != null && <path d={`M${cx - r},${cy} A${r},${r} 0 0 1 ${ex},${ey}`} fill="none" stroke={kv(k)} strokeWidth="16" strokeLinecap="round" />}
        <text x={cx} y={cy - 8} textAnchor="middle" className="mg-donut-n" style={{ fontSize: maat * 0.16, fill: kv(k) }}>
          {pct == null ? '-' : `${nl(pct, pct % 1 && pct < 99.95 ? 1 : 0)}%`}</text>
        <text x={cx - r} y={cy + 18} textAnchor="middle" className="mg-as">0</text>
        <text x={cx + r} y={cy + 18} textAnchor="middle" className="mg-as">100</text>
      </svg>
      {label && <div className="mg-meter-l">{label}</div>}
    </div>);
}

// Horizontale staven met rangorde; rijen = [label, waarde]
export function Staven({ rijen, eenheid = '', kleur = 'hd', dec = 0, leeg = 'Geen gegevens in deze periode.' }) {
  const mx = Math.max(1, ...rijen.map(([, v]) => v || 0));
  if (!rijen.length) return <div className="hint">{leeg}</div>;
  return (
    <div className="mg-staven">
      {rijen.map(([l, v], i) => (
        <div key={`${l}${i}`} className="mg-staaf">
          <span className="mg-rang">{i + 1}</span>
          <span className="mg-sl" title={l}>{l}</span>
          <span className="mg-sb"><i style={{ width: `${((v || 0) * 100) / mx}%`, background: `linear-gradient(90deg, ${kv(kleur)}, color-mix(in srgb, ${kv(kleur)} 65%, #fff))` }} /></span>
          <b>{nl(v, dec)}{eenheid}</b>
        </div>))}
    </div>);
}

// Kleine trendlijn voor in een tegel
export function Spark({ waarden, kleur = '#fff', hoogte = 34, breedte = 120 }) {
  if (!waarden || waarden.length < 2) return null;
  const mx = Math.max(...waarden, 1); const mn = Math.min(...waarden, 0);
  const pts = waarden.map((v, i) => [(breedte * i) / (waarden.length - 1), hoogte - 3 - ((hoogte - 6) * (v - mn)) / (mx - mn || 1)]);
  const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  return (
    <svg width={breedte} height={hoogte} className="mg-spark">
      <path d={`${d} L${breedte},${hoogte} L0,${hoogte} Z`} fill={kleur} opacity=".16" />
      <path d={d} fill="none" stroke={kleur} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1][0] - 1} cy={pts[pts.length - 1][1]} r="3" fill={kleur} />
    </svg>);
}
