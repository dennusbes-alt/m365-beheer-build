// Timesheet: je Autotask-tijd als blokken in een dag- of weekschema. Sleep tickets, projecttaken of algemene tijd uit de
// zijbalk naar het schema, schuif blokken naar een andere tijd (of dag) en maak ze langer/korter aan de onderrand.
// Alles per kwartier. Wijzigingen gaan direct naar Autotask.
import { useEffect, useMemo, useRef, useState } from 'react';
import { BriefcaseBusiness, CalendarDays, ChevronLeft, ChevronRight, Clock, ExternalLink, FolderKanban, GripVertical, Lock, Plus, RefreshCw,
  Search, Ticket, Trash2 } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { Btn, Loading } from './ui.jsx';
import { EindKeuze } from './Autotask.jsx';

const PX = 56;            // pixels per uur
const KW = PX / 4;        // pixels per kwartier
const DAGNAAM = ['zo', 'ma', 'di', 'wo', 'do', 'vr', 'za'];
const KLEUR = { ticket: 'var(--hd)', taak: 'var(--navy)', algemeen: '#7a8796' };
const lees = (k, s) => { try { return localStorage.getItem(k) || s; } catch { return s; } };
const zet = (k, v) => { try { localStorage.setItem(k, String(v)); } catch { /* geen opslag */ } };

const dagStart = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
const plusDagen = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const maandag = (d) => { const x = dagStart(d); const w = (x.getDay() + 6) % 7; return plusDagen(x, -w); };
const zelfdeDag = (a, b) => dagStart(a).getTime() === dagStart(b).getTime();
const hhmm = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
const uren = (h) => `${Math.floor(h)}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`;
const naarKwartier = (min) => Math.round(min / 15) * 15;
const datumNl = (d) => d.toLocaleDateString('nl-NL', { weekday: 'long', day: 'numeric', month: 'long' });

export default function Timesheet() {
  const [modus, setModusS] = useState(() => lees('ts.modus', 'dag'));
  const setModus = (m) => { setModusS(m); zet('ts.modus', m); };
  const [datum, setDatum] = useState(() => dagStart(new Date()));
  const [entries, setEntries] = useState(null);
  const [fout, setFout] = useState('');
  const [bronnen, setBronnen] = useState(null);
  // Week: altijd ma-zo ophalen; het weekend alleen tonen als je een weekenddag kiest of er weekendtijd staat
  const week = useMemo(() => (modus === 'week' ? [0, 1, 2, 3, 4, 5, 6].map((i) => plusDagen(maandag(datum), i)) : [dagStart(datum)]), [modus, datum]);
  const dagen = useMemo(() => {
    if (modus !== 'week') return week;
    const weekend = [0, 6].includes(datum.getDay()) || (entries || []).some((e) => [0, 6].includes(new Date(e.start).getDay()));
    return weekend ? week : week.slice(0, 5);
  }, [week, modus, datum, entries]);

  const laad = async () => {
    const van = week[0];
    const tot = plusDagen(week[week.length - 1], 1);
    try {
      const r = await api('ts.periode', { from: van.toISOString(), to: tot.toISOString() }, { quiet: true });
      setEntries(r.entries); setFout('');
    } catch (e) { setFout(e.message); setEntries([]); }
  };
  useEffect(() => { setEntries(null); laad(); }, [week]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api('ts.bronnen', {}, { quiet: true }).then(setBronnen).catch((e) => setBronnen({ tickets: [], tasks: [], codes: [], error: e.message })); }, []);

  // Hele dag in het schema (00-24); bij openen scrollt het naar de werkdag (07:00) of, vandaag, naar een uur voor nu
  const vanUur = 0, totUur = 24;
  const scroll = useRef(null);
  useEffect(() => {
    if (!entries || !scroll.current) return;
    const vroegst = Math.min(7, ...entries.map((e) => new Date(e.start).getHours()));
    const nu = new Date().getHours();
    const doel = dagen.some((d) => zelfdeDag(d, new Date())) && nu > 9 ? Math.min(vroegst, nu - 2) : vroegst;
    scroll.current.scrollTop = Math.max(0, doel) * PX;
  }, [entries === null, modus, datum]); // eslint-disable-line react-hooks/exhaustive-deps

  const totaal = (d) => (entries || []).filter((e) => zelfdeDag(new Date(e.start), d)).reduce((s, e) => s + e.hours, 0);
  const verschuif = (n) => setDatum((d) => plusDagen(d, modus === 'week' ? 7 * n : n));

  // ---------------------------------------------------------------- acties
  const nieuw = async (bron, start, minuten = 30) => {
    const r = await openModal((close) => <Blok bron={bron} start={start} minuten={minuten} close={close} />);
    if (!r) return;
    const x = await act('ts.nieuw', { kind: bron.kind, refId: bron.id, start: r.start.toISOString(), end: r.end.toISOString(), notes: r.notes }, { msg: 'Tijd boeken in Autotask...' });
    if (x) { toast(`Geboekt: ${hhmm(r.start)}-${hhmm(r.end)} ${bron.title}`, 'g'); laad(); }
  };
  const wijzig = async (e, start, end) => {
    const oud = entries;
    setEntries((l) => l.map((x) => (x.id === e.id ? { ...x, start: start.toISOString(), end: end.toISOString(), hours: (end - start) / 3600000 } : x)));
    const x = await act('ts.wijzig', { id: e.id, start: start.toISOString(), end: end.toISOString() }, { quiet: true, nobusy: true });
    if (!x) { setEntries(oud); toast('Verschuiven niet gelukt; het blok staat weer op de oude plek.', 'e'); }
  };
  // Vergeten ticket achteraf: aanmaken, tijd boeken op de gekozen dag en eventueel meteen afronden
  const snelTicket = async (start) => {
    const dag = dagen.find((d) => zelfdeDag(d, new Date())) || dagen[0];
    let s = start;
    if (!s) {
      s = new Date(dag);
      if (zelfdeDag(dag, new Date())) { const n = new Date(); s.setHours(n.getHours(), naarKwartier(n.getMinutes()) - 30); } else s.setHours(9, 0);
    }
    const r = await openModal((close) => <SnelTicket start={s} close={close} />, { wide: true });
    if (!r) return;
    const x = await act('ts.ticket', r, { msg: r.done ? 'Ticket aanmaken, tijd boeken en afronden...' : 'Ticket aanmaken en tijd boeken...' });
    if (x) {
      toast(`Ticket ${x.ticket.number} aangemaakt en geboekt${x.closed === 'invoice' ? ', op Ready to Invoice' : x.closed ? ' en afgerond' : ''}.`, 'g');
      laad();
      api('ts.bronnen', { fresh: true }, { quiet: true }).then(setBronnen).catch(() => {});
    }
  };
  const bewerk = async (e) => {
    const r = await openModal((close) => <Blok bestaand={e} close={close} />);
    if (!r) return;
    if (r.verwijder) {
      if (!await ask(`Tijdregel ${hhmm(new Date(e.start))}-${hhmm(new Date(e.end))} (${e.title}) verwijderen uit Autotask?`, 'Verwijderen')) return;
      if (await act('ts.verwijder', { id: e.id }, { msg: 'Verwijderen...' })) { toast('Verwijderd.', 'g'); laad(); }
      return;
    }
    if (await act('ts.wijzig', { id: e.id, start: r.start.toISOString(), end: r.end.toISOString(), notes: r.notes }, { msg: 'Opslaan in Autotask...' })) { toast('Opgeslagen.', 'g'); laad(); }
  };

  return (
    <div className="klanten breed ts">
      <div className="headrow" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 10 }}>
        <div className="m"><h2 style={{ margin: 0 }}>Timesheet</h2>
          <div className="hint" style={{ margin: 0 }}>Sleep tickets, projecttaken of algemene tijd naar je dag. Schuif blokken, of trek de onderrand om de duur te wijzigen. Alles per kwartier, direct in Autotask.</div></div>
        <div className="btns" style={{ alignItems: 'center' }}>
          <Btn s icon={ChevronLeft} onClick={() => verschuif(-1)} title={modus === 'week' ? 'Vorige week' : 'Vorige dag'} />
          <Btn s onClick={() => setDatum(dagStart(new Date()))}>Vandaag</Btn>
          <Btn s icon={ChevronRight} onClick={() => verschuif(1)} title={modus === 'week' ? 'Volgende week' : 'Volgende dag'} />
          <input type="date" value={`${datum.getFullYear()}-${String(datum.getMonth() + 1).padStart(2, '0')}-${String(datum.getDate()).padStart(2, '0')}`}
            onChange={(e) => e.target.value && setDatum(dagStart(new Date(e.target.value + 'T00:00')))} style={{ width: 'auto' }} />
          <div className="ts-schakel">
            <button type="button" className={modus === 'dag' ? 'on' : ''} onClick={() => setModus('dag')}>Dag</button>
            <button type="button" className={modus === 'week' ? 'on' : ''} onClick={() => setModus('week')}>Week</button>
          </div>
          <Btn s icon={RefreshCw} onClick={() => { setEntries(null); laad(); }}>Vernieuwen</Btn>
          <Btn s v="p" icon={Plus} onClick={() => snelTicket()} title="Ticket vergeten aan te maken? Maak het hier achteraf, met tijd en eventueel meteen afgerond">Snel ticket</Btn>
        </div>
      </div>
      {fout && <Msg kind="warn">{fout}</Msg>}
      <div className="ts-raam">
        <Zijbalk bronnen={bronnen} onKlik={(b) => { const n = new Date(); const s = dagStart(dagen[0]); s.setHours(n.getHours(), naarKwartier(n.getMinutes())); nieuw(b, s); }} />
        <div className="ts-schema">
          <div className="ts-koppen" style={{ gridTemplateColumns: `52px repeat(${dagen.length}, 1fr)` }}>
            <div />
            {dagen.map((d) => {
              const t = totaal(d);
              return (
                <div key={d.toISOString()} className={'ts-kop' + (zelfdeDag(d, new Date()) ? ' vandaag' : '')}>
                  <b>{modus === 'week' ? `${DAGNAAM[d.getDay()]} ${d.getDate()}-${d.getMonth() + 1}` : datumNl(d)}</b>
                  <span className={t >= 8 ? 'vol' : ''}>{uren(t)} uur{t < 8 ? ` · nog ${uren(8 - t)}` : ''}</span>
                </div>);
            })}
          </div>
          {!entries ? <Loading text="Je tijd ophalen uit Autotask..." /> : (
            <div className="ts-scroll" ref={scroll}>
              <Raster dagen={dagen} vanUur={vanUur} totUur={totUur} entries={entries} onDrop={nieuw} onWijzig={wijzig} onBewerk={bewerk} />
            </div>)}
        </div>
      </div>
    </div>);
}

// ---------------------------------------------------------------- raster met blokken
function Raster({ dagen, vanUur, totUur, entries, onDrop, onWijzig, onBewerk }) {
  const ref = useRef(null);
  const [sleep, setSleep] = useState(null);   // {id, dag, startMin, duur} tijdens slepen/rekken
  const [doel, setDoel] = useState(null);     // markering bij slepen uit de zijbalk
  const hoogte = (totUur - vanUur) * PX;
  const kolomVan = (clientX) => {
    const r = ref.current.getBoundingClientRect();
    const w = (r.width - 52) / dagen.length;
    return Math.max(0, Math.min(dagen.length - 1, Math.floor((clientX - r.left - 52) / w)));
  };
  const minVan = (clientY) => {
    const r = ref.current.getBoundingClientRect();
    return Math.max(0, Math.min((totUur - vanUur) * 60 - 15, naarKwartier(((clientY - r.top) / PX) * 60)));
  };
  const tijd = (dagIdx, min) => { const d = new Date(dagen[dagIdx]); d.setHours(vanUur, 0, 0, 0); return new Date(d.getTime() + min * 60000); };

  // Blok verschuiven of rekken met de muis
  const begin = (ev, e, wat) => {
    if (e.locked) { toast('Deze tijdregel is al goedgekeurd of gefactureerd en kan niet meer worden verschoven.', 'e'); return; }
    ev.preventDefault();
    ev.stopPropagation();
    const s = new Date(e.start), t = new Date(e.end);
    const dagIdx = dagen.findIndex((d) => zelfdeDag(d, s));
    const startMin = (s.getHours() - vanUur) * 60 + s.getMinutes();
    const duur = Math.max(15, (t - s) / 60000);
    const y0 = ev.clientY, x0 = ev.clientX;
    let laatste = { id: e.id, dag: dagIdx, startMin, duur };
    let bewogen = false;
    const beweeg = (m) => {
      const dy = naarKwartier(((m.clientY - y0) / PX) * 60);
      if (Math.abs(m.clientY - y0) > 4 || Math.abs(m.clientX - x0) > 4) bewogen = true;
      laatste = wat === 'rek'
        ? { ...laatste, duur: Math.max(15, duur + dy) }
        : { ...laatste, dag: dagen.length > 1 ? kolomVan(m.clientX) : dagIdx, startMin: Math.max(0, Math.min((totUur - vanUur) * 60 - duur, startMin + dy)) };
      setSleep(laatste);
    };
    const los = () => {
      window.removeEventListener('pointermove', beweeg);
      window.removeEventListener('pointerup', los);
      setSleep(null);
      if (!bewogen) { if (wat !== 'rek') onBewerk(e); return; }
      if (laatste.dag === dagIdx && laatste.startMin === startMin && laatste.duur === duur) return;
      const ns = tijd(laatste.dag, laatste.startMin);
      onWijzig(e, ns, new Date(ns.getTime() + laatste.duur * 60000));
    };
    window.addEventListener('pointermove', beweeg);
    window.addEventListener('pointerup', los);
  };

  return (
    <div className="ts-raster" ref={ref} style={{ gridTemplateColumns: `52px repeat(${dagen.length}, 1fr)`, height: hoogte }}>
      <div className="ts-uren">
        {Array.from({ length: totUur - vanUur }, (_, i) => <div key={i} style={{ height: PX }}>{String(vanUur + i).padStart(2, '0')}:00</div>)}
      </div>
      {dagen.map((d, i) => (
        <div key={d.toISOString()} className={'ts-kolom' + (zelfdeDag(d, new Date()) ? ' vandaag' : '')}
          onDragOver={(ev) => { ev.preventDefault(); setDoel({ dag: i, min: minVan(ev.clientY) }); }}
          onDragLeave={() => setDoel(null)}
          onDrop={(ev) => {
            ev.preventDefault();
            setDoel(null);
            let bron = null;
            try { bron = JSON.parse(ev.dataTransfer.getData('application/json')); } catch { /* geen bron */ }
            if (bron) onDrop(bron, tijd(i, minVan(ev.clientY)));
          }}>
          {Array.from({ length: (totUur - vanUur) * 4 }, (_, k) => <div key={k} className={'ts-kwartier' + (k % 4 === 3 ? ' uur' : '')} style={{ height: KW }} />)}
          {zelfdeDag(d, new Date()) && <NuLijn vanUur={vanUur} totUur={totUur} />}
          {doel && doel.dag === i && <div className="ts-doel" style={{ top: (doel.min / 60) * PX, height: KW * 2 }}>{hhmm(tijd(i, doel.min))}</div>}
          {entries.filter((e) => {
            const pos = sleep && sleep.id === e.id ? sleep.dag : dagen.findIndex((x) => zelfdeDag(x, new Date(e.start)));
            return pos === i;
          }).map((e) => {
            const s = new Date(e.start), t = new Date(e.end);
            const p = sleep && sleep.id === e.id ? sleep : { startMin: (s.getHours() - vanUur) * 60 + s.getMinutes(), duur: Math.max(15, (t - s) / 60000) };
            const top = (p.startMin / 60) * PX, h = Math.max(KW, (p.duur / 60) * PX - 2);
            const vs = tijd(i, p.startMin), ve = new Date(vs.getTime() + p.duur * 60000);
            return (
              <div key={e.id} className={'ts-blok' + (sleep && sleep.id === e.id ? ' sleept' : '') + (e.locked ? ' slot' : '')}
                style={{ top, height: h, background: KLEUR[e.kind] }} onPointerDown={(ev) => begin(ev, e, 'schuif')}
                title={`${hhmm(vs)}-${hhmm(ve)} · ${e.title}${e.company ? ' · ' + e.company : ''}${e.notes ? '\n' + e.notes : ''}`}>
                <div className="ts-blok-t">{e.locked && <Lock size={11} />}<b>{hhmm(vs)}-{hhmm(ve)}</b> {e.ref && <span>{e.ref}</span>}</div>
                {h > 26 && <div className="ts-blok-n">{e.title}{e.company ? ` · ${e.company}` : ''}</div>}
                {h > 44 && e.notes && <div className="ts-blok-o">{e.notes}</div>}
                {!e.locked && <div className="ts-rek" onPointerDown={(ev) => begin(ev, e, 'rek')} title="Sleep om langer of korter te maken" />}
              </div>);
          })}
        </div>))}
    </div>);
}

function NuLijn({ vanUur, totUur }) {
  const [, tik] = useState(0);
  useEffect(() => { const t = setInterval(() => tik((x) => x + 1), 60000); return () => clearInterval(t); }, []);
  const n = new Date();
  const min = (n.getHours() - vanUur) * 60 + n.getMinutes();
  if (min < 0 || min > (totUur - vanUur) * 60) return null;
  return <div className="ts-nu" style={{ top: (min / 60) * PX }} />;
}

// ---------------------------------------------------------------- zijbalk met wat je kunt slepen
function Zijbalk({ bronnen, onKlik }) {
  const [q, setQ] = useState('');
  const [tab, setTab] = useState('tickets');
  const [proj, setProj] = useState(null);        // gekozen project met zijn taken
  const [gevonden, setGevonden] = useState([]);
  useEffect(() => {
    if (tab !== 'project' || q.trim().length < 2) { setGevonden([]); return undefined; }
    const t = setTimeout(() => api('ts.projecten', { q: q.trim() }, { quiet: true }).then((r) => setGevonden(r.projects)).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [q, tab]);
  if (!bronnen) return <div className="ts-zij"><Loading text="Tickets en taken ophalen..." /></div>;
  const filter = (l) => l.filter((x) => !q || `${x.ref} ${x.title} ${x.company}`.toLowerCase().includes(q.toLowerCase()));
  const kiesProject = async (p) => {
    try {
      const r = await api('ts.projecten', { projectId: p.id, projectName: p.name, company: p.company }, { quiet: true });
      setProj({ ...p, tasks: r.tasks });
    } catch (e) { toast(e.message, 'e'); }
  };
  const lijst = tab === 'tickets' ? filter(bronnen.tickets) : tab === 'taken' ? filter(bronnen.tasks) : tab === 'algemeen' ? filter(bronnen.codes) : proj ? proj.tasks : [];
  return (
    <div className="ts-zij">
      <div className="ts-tabs">
        {[['tickets', 'Tickets', Ticket], ['taken', 'Mijn taken', FolderKanban], ['project', 'Project', BriefcaseBusiness], ['algemeen', 'Algemeen', Clock]].map(([k, l, I]) => (
          <button key={k} type="button" className={tab === k ? 'on' : ''} onClick={() => { setTab(k); setProj(null); setQ(''); }}><I size={13} />{l}</button>))}
      </div>
      <div className="ts-zoek"><Search size={14} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tab === 'project' ? 'Zoek project...' : 'Filter...'} /></div>
      {bronnen.error && <div className="hint" style={{ color: 'var(--rd)' }}>{bronnen.error}</div>}
      {tab === 'project' && !proj && (
        <div className="ts-items">
          {gevonden.map((p) => <button key={p.id} type="button" className="ts-proj" onClick={() => kiesProject(p)}><b>{p.name}</b><small>{p.number} · {p.company}</small></button>)}
          {q.trim().length < 2 && <div className="hint">Typ minstens 2 letters van de projectnaam; kies het project en sleep een taak naar het schema.</div>}
        </div>)}
      {tab === 'project' && proj && <button type="button" className="linkknop" onClick={() => setProj(null)}><ChevronLeft size={13} /> {proj.name}</button>}
      {(tab !== 'project' || proj) && (
        <div className="ts-items">
          {lijst.map((x) => (
            <div key={`${x.kind}${x.id}`} className={'ts-item ' + x.kind} draggable
              onDragStart={(ev) => { ev.dataTransfer.setData('application/json', JSON.stringify(x)); ev.dataTransfer.effectAllowed = 'copy'; }}
              title="Sleep naar het schema (of klik om nu te boeken)">
              <GripVertical size={14} className="grip" />
              <div className="ts-item-t"><b>{x.title}</b><small>{[x.ref, x.company].filter(Boolean).join(' · ')}{x.kind === 'ticket' && x.mine === false ? ' · recent gewerkt' : ''}</small></div>
              <button type="button" className="ts-plus" onClick={() => onKlik(x)} title="Nu boeken (begint op dit moment)"><Plus size={14} /></button>
            </div>))}
          {!lijst.length && <div className="hint">{tab === 'algemeen' ? 'Geen interne codes gevonden in Autotask.' : 'Niets gevonden.'}</div>}
        </div>)}
    </div>);
}

// ---------------------------------------------------------------- venster: nieuw blok of bestaand blok aanpassen
function Blok({ bron, start, minuten, bestaand, close }) {
  const s0 = bestaand ? new Date(bestaand.start) : start;
  const e0 = bestaand ? new Date(bestaand.end) : new Date(start.getTime() + minuten * 60000);
  const [van, setVan] = useState(hhmm(s0));
  const [tot, setTot] = useState(hhmm(e0));
  const [tekst, setTekst] = useState(bestaand ? bestaand.notes : '');
  const soort = bestaand ? bestaand.kind : bron.kind;
  const titel = bestaand ? bestaand.title : bron.title;
  const zetTijd = (basis, t) => { const [h, m] = t.split(':').map(Number); const d = new Date(basis); d.setHours(h, m, 0, 0); return d; };
  const vs = zetTijd(s0, van), ve = zetTijd(s0, tot);
  const duur = (ve - vs) / 60000;
  const ok = duur > 0 && (soort === 'algemeen' || tekst.trim().length >= 3);
  const snel = (m) => setTot(hhmm(new Date(vs.getTime() + m * 60000)));
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><CalendarDays size={18} />{bestaand ? 'Tijd aanpassen' : 'Tijd boeken'}</h3>
      <div className="hint" style={{ marginTop: 0 }}><b>{titel}</b>{(bestaand || bron).company ? ` · ${(bestaand || bron).company}` : ''} · {datumNl(s0)}</div>
      {bestaand && bestaand.locked && <Msg kind="info">Deze tijdregel is al goedgekeurd of gefactureerd; Autotask staat wijzigen niet meer toe.</Msg>}
      <div className="btns" style={{ alignItems: 'center', marginTop: 8 }}>
        <label className="f" style={{ margin: 0 }}>Van</label><input type="time" step={900} value={van} onChange={(e) => setVan(e.target.value)} style={{ width: 120 }} />
        <label className="f" style={{ margin: 0 }}>tot</label><input type="time" step={900} value={tot} onChange={(e) => setTot(e.target.value)} style={{ width: 120 }} />
        <span className="hint" style={{ margin: 0 }}>{duur > 0 ? `${Math.floor(duur / 60)}:${String(duur % 60).padStart(2, '0')} uur` : 'eindtijd na begintijd'}</span>
      </div>
      <div className="btns" style={{ marginTop: 6 }}>{[15, 30, 45, 60, 90, 120].map((m) => <Btn key={m} s v={duur === m ? 'p' : ''} onClick={() => snel(m)}>{m < 60 ? `${m} min` : `${m / 60} uur`}</Btn>)}</div>
      <label className="f">Wat heb je gedaan?{soort === 'algemeen' ? ' (optioneel)' : ''}</label>
      <textarea rows={4} autoFocus value={tekst} onChange={(e) => setTekst(e.target.value)} placeholder={soort === 'algemeen' ? 'Bijv. teamoverleg' : 'Bijv. Outlook-profiel opnieuw aangemaakt, werkt weer'} />
      <div className="foot">
        {bestaand && !bestaand.locked && <button className="btn" style={{ marginRight: 'auto', color: 'var(--rd)' }} onClick={() => close({ verwijder: true })}><Trash2 size={15} /> Verwijderen</button>}
        {bestaand && bestaand.url && <button className="btn" onClick={() => act('open.url', { url: bestaand.url }, { nobusy: true, quiet: true })}><ExternalLink size={15} /> Ticket</button>}
        <button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!ok || (bestaand && bestaand.locked)} onClick={() => close({ start: vs, end: ve, notes: tekst.trim() })}>{bestaand ? 'Opslaan' : 'Boeken'}</button>
      </div>
    </>);
}

// ---------------------------------------------------------------- snel ticket (vergeten aan te maken)
function SnelTicket({ start, close }) {
  const [opties, setOpties] = useState(null);
  const [zoek, setZoek] = useState('');
  const [gevonden, setGevonden] = useState([]);
  const [klant, setKlant] = useState(null);
  const [contacten, setContacten] = useState([]);
  const [v, setV] = useState({ contactId: '', title: '', notes: '', datum: `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`,
    van: hhmm(start), tot: hhmm(new Date(start.getTime() + 30 * 60000)), done: true, end: 'complete', resolution: '' });
  useEffect(() => { api('sd.opties', {}, { quiet: true }).then(setOpties).catch(() => setOpties({ companies: [] })); }, []);
  useEffect(() => {
    if (zoek.trim().length < 2) { setGevonden([]); return undefined; }
    const t = setTimeout(() => api('sd.bedrijven', { q: zoek.trim() }, { quiet: true }).then((r) => setGevonden(r.companies)).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [zoek]);
  useEffect(() => { if (klant) api('at.contacten', { companyId: klant.id }, { quiet: true }).then((r) => setContacten(r.contacts || [])).catch(() => setContacten([])); }, [klant]);
  const z = (k) => (e) => setV({ ...v, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  const tijd = (t) => { const [h, m] = t.split(':').map(Number); const d = new Date(`${v.datum}T00:00`); d.setHours(h, m, 0, 0); return d; };
  const s = tijd(v.van), e = tijd(v.tot);
  const duur = (e - s) / 60000;
  const lijst = zoek.trim().length >= 2 ? gevonden : (opties?.companies || []);
  const ok = klant && v.title.trim().length >= 3 && v.notes.trim().length >= 3 && duur > 0;
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Ticket size={18} />Snel ticket (achteraf)</h3>
      <div className="hint" style={{ marginTop: 0 }}>Vergeten een ticket aan te maken? Het ticket komt op jouw naam, de tijd staat direct in je timesheet.</div>
      <label className="f">Klant</label>
      {klant ? <div className="btns" style={{ alignItems: 'center' }}><b>{klant.name}</b><button className="linkknop" onClick={() => { setKlant(null); setContacten([]); setV({ ...v, contactId: '' }); }}>andere klant</button></div> : (
        <>
          <div className="ts-zoek"><Search size={14} /><input autoFocus value={zoek} onChange={(ev) => setZoek(ev.target.value)} placeholder="Zoek klant (of kies een gekoppelde klant hieronder)..." /></div>
          <div style={{ display: 'grid', gap: 4, marginTop: 6, maxHeight: 180, overflow: 'auto' }}>
            {lijst.slice(0, 40).map((b) => <button key={b.id} type="button" className="ts-proj" onClick={() => setKlant(b)}><b>{b.name}</b></button>)}
            {!opties && <Loading text="Klanten ophalen..." />}
          </div>
        </>)}
      {klant && <>
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Contactpersoon</label>
            <select value={v.contactId} onChange={z('contactId')} style={{ width: 220 }}><option value="">Geen</option>{contacten.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div><label className="f">Datum</label><input type="date" value={v.datum} onChange={z('datum')} style={{ width: 160 }} /></div>
          <div><label className="f">Van</label><input type="time" step={900} value={v.van} onChange={z('van')} style={{ width: 110 }} /></div>
          <div><label className="f">Tot</label><input type="time" step={900} value={v.tot} onChange={z('tot')} style={{ width: 110 }} /></div>
          <div style={{ alignSelf: 'flex-end', paddingBottom: 8 }}><span className="hint" style={{ margin: 0 }}>{duur > 0 ? `${Math.floor(duur / 60)}:${String(duur % 60).padStart(2, '0')} uur` : 'eindtijd na begintijd'}</span></div>
        </div>
        <label className="f">Onderwerp</label>
        <input value={v.title} onChange={z('title')} placeholder="Bijv. Outlook start niet op bij receptie" style={{ width: '100%' }} />
        <label className="f">Wat heb je gedaan?</label>
        <textarea rows={3} value={v.notes} onChange={z('notes')} placeholder="Komt in de tijdregel" />
        <label className="chk" style={{ marginTop: 10 }}><input type="checkbox" checked={v.done} onChange={z('done')} /><span><b>Is het al afgerond?</b></span></label>
        {v.done && <>
          <div style={{ marginTop: 6 }}><EindKeuze value={v.end} onChange={(x) => setV({ ...v, end: x })} /></div>
          <label className="f">Wat is er gebeurd / opgelost?</label>
          <textarea rows={3} value={v.resolution} onChange={z('resolution')} placeholder="Leeg = zelfde als hierboven" />
        </>}
      </>}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!ok} onClick={() => close({ companyId: klant.id, contactId: v.contactId ? +v.contactId : null, title: v.title.trim(), notes: v.notes.trim(),
          start: s.toISOString(), end: e.toISOString(), done: v.done, endStatus: v.end, resolution: v.resolution.trim() })}>
          {v.done ? 'Aanmaken, boeken en afronden' : 'Aanmaken en boeken'}</button></div>
    </>);
}