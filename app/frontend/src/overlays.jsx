// Meldingen, wachtvenster en bevestigingsvensters (los van React-state, overal aan te roepen).
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

let st = { toasts: [], busyN: 0, busyMsg: '', modal: null, werk: [] };
const subs = new Set();
const set = (p) => { st = { ...st, ...p }; subs.forEach((f) => f()); };
const useStore = () => useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, () => st);

let tid = 0;
export function toast(text, kind = '') {
  const id = ++tid;
  set({ toasts: [...st.toasts, { id, text, kind }].slice(-6) });
  setTimeout(() => set({ toasts: st.toasts.filter((t) => t.id !== id) }), kind === 'e' ? 9000 : 4500);
}
export function busy(on, msg) {
  const n = Math.max(0, st.busyN + (on ? 1 : -1));
  set({ busyN: n, busyMsg: on && msg ? msg : n ? st.busyMsg : '' });
}
// Tekst van het lopende wachtvenster bijwerken (bijv. voortgang per stap)
export function busyText(msg) { if (st.busyN) set({ busyMsg: msg }); }
// Actie op de achtergrond: niets blokkeert, alleen een dunne balk bovenin en een klein label onderin
let wid = 0;
export function werk(msg) {
  const id = ++wid;
  set({ werk: [...st.werk, { id, msg: msg || 'Bezig...' }] });
  return () => set({ werk: st.werk.filter((w) => w.id !== id) });
}
export function openModal(render, opts = {}) {
  return new Promise((resolve) => {
    const close = (v) => { set({ modal: null }); resolve(v); };
    set({ modal: { render, close, wide: opts.wide } });
  });
}
export const closeModal = () => st.modal && st.modal.close(undefined);

export function ask(text, okText = 'Doorgaan', danger = false, title = 'Bevestigen') {
  return openModal((close) => (
    <>
      <h3>{title}</h3>
      <div className="pre">{text}</div>
      <div className="foot">
        <button className="btn" onClick={() => close(false)}>Annuleren</button>
        <button className={'btn ' + (danger ? 'd' : 'p')} onClick={() => close(true)} autoFocus>{okText}</button>
      </div>
    </>
  )).then(Boolean);
}

function TypeConfirm({ text, word, close, okText = 'Verwijderen' }) {
  const [v, setV] = useState('');
  return (
    <>
      <h3>Bevestigen</h3>
      <div className="pre">{text}</div>
      <label className="f">Typ <b>{word}</b> om door te gaan</label>
      <input type="text" value={v} onChange={(e) => setV(e.target.value)} autoFocus autoComplete="off" />
      <div className="foot">
        <button className="btn" onClick={() => close(false)}>Annuleren</button>
        <button className="btn d" disabled={v.trim().toUpperCase() !== word} onClick={() => close(true)}>{okText}</button>
      </div>
    </>
  );
}
export const askType = (text, word, okText) => openModal((close) => <TypeConfirm text={text} word={word} close={close} okText={okText} />).then(Boolean);

const icon = { e: XCircle, g: CheckCircle2, '': Info };

export function Overlays() {
  const s = useStore();
  const ref = useRef(null);
  useEffect(() => {
    if (!s.modal) return undefined;
    const k = (e) => { if (e.key === 'Escape') s.modal.close(undefined); };
    addEventListener('keydown', k);
    return () => removeEventListener('keydown', k);
  }, [s.modal]);
  return (
    <>
      <div className="toasts">
        {s.toasts.map((t) => {
          const I = icon[t.kind] || Info;
          return (
            <div key={t.id} className={'toast ' + t.kind}>
              <I size={17} style={{ flex: 'none', marginTop: 1 }} />
              <span>{t.text}</span>
              <button onClick={() => set({ toasts: st.toasts.filter((x) => x.id !== t.id) })} aria-label="Sluiten"><X size={15} /></button>
            </div>
          );
        })}
      </div>
      {s.modal && (
        <div className={'modal' + (s.modal.wide ? ' wide' : '')} onMouseDown={(e) => { if (e.target === e.currentTarget) s.modal.close(undefined); }}>
          <div ref={ref} role="dialog" aria-modal="true">{s.modal.render(s.modal.close)}</div>
        </div>
      )}
      {s.werk.length > 0 && (
        <>
          <div className="werkbalk"><i /></div>
          <div className="werklabel"><span className="spin" />{s.werk[s.werk.length - 1].msg}{s.werk.length > 1 ? ` (+${s.werk.length - 1})` : ''}</div>
        </>
      )}
      {s.busyN > 0 && (
        <div className="busy"><div><span className="spin" /><span>{s.busyMsg || 'Bezig...'}</span></div></div>
      )}
    </>
  );
}

export const Msg = ({ kind = 'info', children }) => {
  const I = { warn: AlertTriangle, err: XCircle, ok: CheckCircle2, info: Info }[kind];
  return <div className={'msg ' + kind}><I size={17} /><div>{children}</div></div>;
};
