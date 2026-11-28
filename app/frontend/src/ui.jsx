// Herbruikbare bouwstenen voor de schermen.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';

export const cx = (...a) => a.filter(Boolean).join(' ');

export function SearchBox({ value, onChange, placeholder = 'Zoeken...', autoFocus, onKeyDown }) {
  return (
    <div className="search">
      <Search size={16} />
      <input type="search" value={value} placeholder={placeholder} autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} />
    </div>
  );
}

export const norm = (s) => String(s ?? '').toLowerCase();
export const useFilter = (items, q, keys) =>
  useMemo(() => {
    const t = norm(q).trim();
    if (!t) return items;
    return items.filter((i) => keys(i).some((k) => norm(k).includes(t)));
  }, [items, q]); // eslint-disable-line react-hooks/exhaustive-deps

export const Card = ({ title, icon: I, children, className, right }) => (
  <div className={cx('card', className)}>
    {title && <h3>{I && <I size={18} />}<span style={{ flex: 1 }}>{title}</span>{right}</h3>}
    {children}
  </div>
);

export const Chip = ({ k = '', children, title }) => <span className={'chip ' + k} title={title}>{children}</span>;

export const Btn = ({ v = '', s, w, icon: I, children, ...p }) => (
  <button className={cx('btn', v, s && 's', w && 'w')} {...p}>{I && <I size={s ? 14 : 16} />}{children}</button>
);

export function Field({ label, value, onChange, type = 'text', ...p }) {
  return (
    <div>
      <label className="f">{label}</label>
      <input type={type} value={value ?? ''} onChange={(e) => onChange(e.target.value)} {...p} />
    </div>
  );
}

export const Check = ({ checked, onChange, children, disabled, className }) => (
  <label className={cx('chk', className)} style={disabled ? { opacity: .55, cursor: 'not-allowed' } : undefined}>
    <input type="checkbox" checked={!!checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
    <span>{children}</span>
  </label>
);

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([k, l, I]) => (
        <button key={k} role="tab" className={value === k ? 'on' : ''} onClick={() => onChange(k)}>{I && <I size={15} />}{l}</button>
      ))}
    </div>
  );
}

export const Loading = ({ text = 'Laden...' }) => <div className="loading"><span className="spin" />{text}</div>;

// Lange lijsten: maximaal zoveel rijen tekenen (duizenden DOM-elementen maken het scherm traag)
export const MAX_RIJEN = 250;
export const Meer = ({ totaal }) => (totaal > MAX_RIJEN
  ? <div className="meer">Toont {MAX_RIJEN} van {totaal}. Typ in het zoekveld om te verfijnen.</div> : null);

// Vinkje 'Alles selecteren' voor een lijst: ids = wat nu zichtbaar/selecteerbaar is; houdt de rest van de keuze vast.
export function AllesVink({ ids, value, onChange, label = 'Alles selecteren', style }) {
  const ref = useRef(null);
  const aan = ids.filter((i) => value.includes(i)).length;
  useEffect(() => { if (ref.current) ref.current.indeterminate = aan > 0 && aan < ids.length; }, [aan, ids.length]);
  if (ids.length < 2) return null;
  return (
    <label className="allesvink" style={style}>
      <input ref={ref} type="checkbox" checked={aan === ids.length}
        onChange={(e) => onChange(e.target.checked ? [...new Set([...value, ...ids])] : value.filter((v) => !ids.includes(v)))} />
      {label}{aan > 0 && <span className="hint" style={{ margin: 0 }}>({aan} van {ids.length})</span>}
    </label>);
}

// Lijst met vinkjes en zoekveld. items: [{v, l, s}]
export function CheckList({ items, value, onChange, height = 240, placeholder = 'Zoeken...' }) {
  const [q, setQ] = useState('');
  const shown = useFilter(items, q, (i) => [i.l, i.s]);
  const sel = new Set(value);
  const toggle = (v, on) => { const n = new Set(sel); on ? n.add(v) : n.delete(v); onChange([...n]); };
  return (
    <div>
      <SearchBox value={q} onChange={setQ} placeholder={placeholder} />
      <AllesVink ids={shown.slice(0, MAX_RIJEN).map((i) => i.v)} value={value} onChange={onChange} label={q ? 'Alle gevonden selecteren' : 'Alles selecteren'} />
      <div className="list" style={{ maxHeight: height }}>
        {shown.slice(0, MAX_RIJEN).map((i) => (
          <label key={i.v} className="li">
            <input type="checkbox" checked={sel.has(i.v)} onChange={(e) => toggle(i.v, e.target.checked)} />
            <span className="m"><b>{i.l}</b>{i.s && <small>{i.s}</small>}</span>
          </label>
        ))}
        {!shown.length && <div className="li empty">Niets gevonden</div>}
        <Meer totaal={shown.length} />
      </div>
      <div className="count">{value.length ? `${value.length} geselecteerd` : `${items.length} beschikbaar`}</div>
    </div>
  );
}

// Zoekbare keuzelijst (voor groep of gebruiker kiezen)
export function Picker({ items, onPick, placeholder = 'Zoek...', height = 220, render }) {
  const [q, setQ] = useState('');
  const shown = useFilter(items, q, (i) => [i.l, i.s]);
  return (
    <div>
      <SearchBox value={q} onChange={setQ} placeholder={placeholder} />
      <div className="list" style={{ maxHeight: height }}>
        {shown.slice(0, 300).map((i) => (
          <div key={i.v} className="li" onClick={() => onPick(i)}>
            {render ? render(i) : <span className="m"><b>{i.l}</b>{i.s && <small>{i.s}</small>}</span>}
          </div>
        ))}
        {!shown.length && <div className="li empty">Niets gevonden</div>}
      </div>
    </div>
  );
}

const KLEUREN = ['#1b7ea9', '#003f6b', '#0a86b8', '#2c7a5b', '#7b4fa3', '#a8563a', '#3b5998', '#00838f', '#5d6b7a', '#9c6b00'];
export function kleur(s) {
  let h = 0;
  for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return KLEUREN[h % KLEUREN.length];
}
export const initialen = (n) => String(n || '?').replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';
export const Avatar = ({ name, sq, size = 42 }) => (
  <span className={cx('avatar', sq && 'sq')} style={{ background: kleur(name), width: size, height: size, fontSize: size * 0.36 }}>{initialen(name)}</span>
);

export const dt = (s) => {
  if (!s || /^0001/.test(s)) return '-';
  const d = new Date(s);
  return isNaN(d) ? s : d.toLocaleString('nl-NL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};
export const datum = (s) => {
  if (!s) return '-';
  const d = new Date(s);
  return isNaN(d) ? s : d.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short', year: 'numeric' });
};

export function csv(naam, rows) {
  const b = new Blob(['﻿' + rows.map((r) => r.map((c) => '"' + String(c ?? '').replace(/"/g, '""') + '"').join(';')).join('\r\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b);
  a.download = naam;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export function genPw() {
  const sets = ['abcdefghijkmnopqrstuvwxyz', 'ABCDEFGHJKLMNPQRSTUVWXYZ', '23456789', '!@#$%&*?'];
  const all = sets.join('');
  const r = (n) => { const a = new Uint32Array(1); crypto.getRandomValues(a); return a[0] % n; };
  const p = sets.map((s) => s[r(s.length)]);
  while (p.length < 16) p.push(all[r(all.length)]);
  for (let i = p.length - 1; i > 0; i--) { const j = r(i + 1); [p[i], p[j]] = [p[j], p[i]]; }
  return p.join('');
}

export const normAlias = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, '').replace(/[^a-z0-9-]/g, '');
