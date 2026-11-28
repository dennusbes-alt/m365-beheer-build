// Servicedesk in twee niveaus: L1 (servicedesk, triage) en L2 (escalaties), change approvals en monitoring.
// Sneller dan Autotask: alles in één lijst, bulkacties, en de belangrijkste stap (oppakken, toewijzen, escaleren) met één klik.
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, BarChart3, Check, CheckCircle2, Clock, CalendarPlus, ExternalLink, Gauge, Hand, Hourglass, MonitorPlay, PackagePlus, RefreshCw,
  ShieldCheck, Target, ThumbsDown, ThumbsUp, UserCheck, Users, X } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, openModal, toast } from './overlays.jsx';
import { AllesVink, Btn, Chip, Loading, SearchBox, csv } from './ui.jsx';
import { Donut, Kolommen, Lijn, Meter, Staven, nl } from './Grafiek.jsx';
import { productenOpTicket } from './Voorraad.jsx';
import { serviceCall } from './Planning.jsx';
import { meekijkenTicket } from './Rmm.jsx';

const pc = (v) => (v == null ? '-' : `${String(v).replace('.', ',')}%`);
const duur = (h) => {
  if (h == null) return '-';
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 24) return `${nl(h, h < 10 && h % 1 ? 1 : 0)} uur`;
  const d = h / 24;
  return `${nl(d, d < 10 && d % 1 ? 1 : 0)} ${Math.round(d * 10) === 10 ? 'dag' : 'dagen'}`;
};
const openUrl = (u) => u && act('open.url', { url: u }, { nobusy: true, quiet: true });
const hoog = (p) => /crit|high|hoog|urgent|p1|p2/i.test(p || '');

// ================================================================ Queue (L1 of L2)
export function Queue({ level, rol, me, onAfronden }) {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [f, setF] = useState(level === 'l1' ? 'triage' : 'alle');
  const [q, setQ] = useState('');
  const [sel, setSel] = useState([]);
  const [open, setOpen] = useState(null);
  const [pl, setPl] = useState({ priorities: [], statuses: [] });
  const timer = useRef(null);
  const laad = (fresh) => {
    clearTimeout(timer.current);
    api('sd.queue', { level, fresh: !!fresh }, { quiet: true, achter: !fresh })
      .then((x) => { setD(x); setFout(''); }).catch((e) => { setFout(e.message); setD((o) => o || { tickets: [] }); })
      .finally(() => { timer.current = setTimeout(() => { if (!document.hidden) laad(false); }, 30000); });   // live: elke 30 s
  };
  useEffect(() => {
    laad(false);
    api('sd.statussen', {}, { quiet: true }).then(setPl).catch(() => {});
    return () => clearTimeout(timer.current);
  }, [level]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <Loading text={level === 'l1' ? 'Servicedeskqueue ophalen...' : 'Escalaties ophalen...'} />;
  if (d.needSetup) return <Msg kind="info">De app vond in Autotask geen queue voor {level === 'l1' ? 'Level 1' : 'Level 2'} (gezocht op 'Level 1/2 Support', 'L1/L2', 'eerste/tweede lijn'). {rol.monitor ? 'Kies de queue onder Servicedesk > Instellingen > Inrichting servicedesk (bovenaan).' : 'Vraag de app-beheerder dit in te richten.'}</Msg>;
  const mijnId = me && me.id;
  const lijst = d.tickets.filter((t) => (f === 'alle' ? true : f === 'triage' ? (t.isNew || t.unassigned) : f === 'mij' ? t.assignedId === mijnId : f === 'laat' ? t.overdue : true))
    .filter((t) => !q || `${t.number} ${t.title} ${t.company} ${t.assigned}`.toLowerCase().includes(q.toLowerCase()));
  const gekozen = d.tickets.filter((t) => sel.includes(t.id));
  const klaar = () => { setSel([]); laad(true); };

  const triage = async (ids, body, wat) => {
    const r = await act('sd.triage', { ids, ...body }, { msg: `${wat}...` });
    if (r) { toast(r.failed ? `${r.ok} gelukt, ${r.failed} niet: ${r.results.filter((x) => !x.ok).map((x) => x.error).join('; ')}` : `${wat}: ${r.ok} ticket(s).`, r.failed ? 'e' : 'g'); klaar(); }
  };
  const oppakken = (ids) => mijnId && triage(ids, { resourceId: mijnId, status: inProgress(pl) }, 'Opgepakt');
  const toewijzen = (ids, rid) => rid && triage(ids, { resourceId: +rid }, 'Toegewezen');
  const prioriteit = (ids, p) => p && triage(ids, { priority: +p }, 'Prioriteit aangepast');
  const escaleren = async (tickets) => {
    const r = await openModal((close) => <Escaleren tickets={tickets} close={close} />, { wide: true });
    if (!r) return;
    const x = await act('sd.escaleren', { ids: tickets.map((t) => t.id), ...r }, { msg: 'Escaleren naar L2...' });
    if (x) { toast(`${x.ok} ticket(s) naar L2.`, 'g'); klaar(); }
  };
  const terug = async (t) => {
    const r = await openModal((close) => <Tekstvenster titel={`Terug naar de servicedesk · ${t.number}`} label="Instructie voor L1 (wat moeten ze doen?)" knop="Terug naar L1" close={close} />);
    if (r && await act('sd.terugnaarl1', { id: t.id, text: r }, { msg: 'Terugzetten naar L1...' })) { toast('Ticket staat weer bij de servicedesk.', 'g'); klaar(); }
  };
  const afronden = async (tickets) => { if (await onAfronden(tickets)) klaar(); };
  const c = d.counts;

  return (
    <>
      {fout && <Msg kind="warn">{fout}</Msg>}
      <div className="sdq-tegels">
        <Tegel l="Open" n={c.open} />
        <Tegel l={level === 'l1' ? 'Nieuw / niet opgepakt' : 'Niet toegewezen'} n={c.unassigned + (level === 'l1' ? c.new - Math.min(c.new, c.unassigned) : 0)} k={c.unassigned ? 'or' : 'gr'}
          on={f === 'triage'} onClick={() => setF('triage')} />
        {level === 'l1' && <Tegel l={`Triage > ${d.triageMin} min`} n={c.triageLate} k={c.triageLate ? 'rd' : 'gr'} sub="nog niet opgepakt" />}
        <Tegel l="Over de deadline" n={c.overdue} k={c.overdue ? 'rd' : 'gr'} on={f === 'laat'} onClick={() => setF('laat')} />
        <Tegel l="Van mij" n={d.tickets.filter((t) => t.assignedId === mijnId).length} on={f === 'mij'} onClick={() => setF('mij')} />
      </div>
      <div className="headrow" style={{ margin: '12px 0 8px', flexWrap: 'wrap', gap: 8 }}>
        <div className="btns">
          {[['triage', level === 'l1' ? 'Triage' : 'Niet toegewezen'], ['alle', 'Alle'], ['mij', 'Van mij'], ['laat', 'Over de deadline']].map(([k, l]) => (
            <Btn key={k} s v={f === k ? 'p' : ''} onClick={() => setF(k)}>{l}</Btn>))}
        </div>
        <div className="btns" style={{ alignItems: 'center' }}>
          <div style={{ width: 240 }}><SearchBox value={q} onChange={setQ} placeholder="Zoek ticket, klant, behandelaar..." /></div>
          <span className="hint" style={{ margin: 0 }}>live · {d.at}</span>
          <Btn s icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
        </div>
      </div>

      {/* Bulkbalk */}
      <div className="sdq-bulk">
        <AllesVink ids={lijst.map((t) => t.id)} value={sel} onChange={setSel} label={`Alles selecteren (${lijst.length})`} />
        {sel.length > 0 && <>
          <b>{sel.length} gekozen</b>
          {mijnId && <Btn s v="p" icon={Hand} onClick={() => oppakken(sel)}>Oppakken</Btn>}
          <select defaultValue="" onChange={(e) => { toewijzen(sel, e.target.value); e.target.value = ''; }} style={{ width: 'auto' }}>
            <option value="">Toewijzen aan...</option>
            {(d.members || []).map((m) => <option key={m.id} value={m.id}>{m.name}{m.lead ? ' (triage)' : ''}</option>)}
          </select>
          <select defaultValue="" onChange={(e) => { prioriteit(sel, e.target.value); e.target.value = ''; }} style={{ width: 'auto' }}>
            <option value="">Prioriteit...</option>
            {pl.priorities.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
          {level === 'l1' && <Btn s icon={ArrowUpFromLine} onClick={() => escaleren(gekozen)}>Escaleren naar L2</Btn>}
          <Btn s icon={Hourglass} onClick={async () => { if (await langlopendZetten(gekozen, true)) klaar(); }} title="Langlopend: geen incident, buiten de SLA">Langlopend</Btn>
          <Btn s icon={CheckCircle2} onClick={() => afronden(gekozen)}>Afronden</Btn>
        </>}
      </div>

      <div className="sdq-lijst">
        {lijst.map((t) => (
          <div key={t.id} className={'sdq-rij' + (t.overdue ? ' laat' : '') + (sel.includes(t.id) ? ' gekozen' : '')}>
            <input type="checkbox" checked={sel.includes(t.id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, t.id] : s.filter((x) => x !== t.id)))} />
            <div className="sdq-hoofd" onClick={() => setOpen(open === t.id ? null : t.id)}>
              <div className="sdq-titel">{hoog(t.priority) && <AlertTriangle size={14} style={{ color: 'var(--rd)', flex: 'none' }} />}{t.title}</div>
              <div className="sdq-meta">
                <span>{t.number}</span><b>{t.company}</b>
                <span className={(t.isNew || t.unassigned) && t.hours > (d.triageMin || 15) / 60 ? 'rood' : ''}><Clock size={12} /> {duur(t.hours)}</span>
                {t.isNew && <Chip k="o">nieuw</Chip>}
                {t.priority && <Chip k={hoog(t.priority) ? 'r' : 'mu'}>{t.priority}</Chip>}
                {t.status && !t.isNew && <Chip>{t.status}</Chip>}
                {t.overdue && <Chip k="r">over de deadline</Chip>}
                {t.longRunning && <Chip k="mu" title="Langlopend: buiten de SLA, telt niet mee in de cijfers"><Hourglass size={11} /> langlopend</Chip>}
                {t.unassigned ? <Chip k="o">niemand</Chip> : <span><UserCheck size={12} /> {t.assigned}</span>}
              </div>
              {open === t.id && t.description && <div className="sdq-tekst">{t.description}</div>}
            </div>
            <div className="btns sdq-acties">
              {mijnId && t.assignedId !== mijnId && <Btn s v="p" icon={Hand} onClick={() => oppakken([t.id])} title="Aan mij toewijzen en op In Progress">Oppakken</Btn>}
              <select defaultValue="" onChange={(e) => { toewijzen([t.id], e.target.value); e.target.value = ''; }} title="Toewijzen" style={{ width: 120 }}>
                <option value="">Toewijzen...</option>
                {(d.members || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
              {level === 'l1' ? <Btn s icon={ArrowUpFromLine} onClick={() => escaleren([t])} title="Naar L2 met reden">L2</Btn>
                : <Btn s icon={ArrowDownToLine} onClick={() => terug(t)} title="Terug naar de servicedesk met instructie">L1</Btn>}
              <Btn s icon={Hourglass} onClick={async () => { if (await langlopendZetten([t], !t.longRunning)) klaar(); }} title={t.longRunning ? 'Niet meer langlopend' : 'Langlopend: geen incident, buiten de SLA'} v={t.longRunning ? 'p' : ''} />
              <Btn s icon={PackagePlus} onClick={() => productenOpTicket(t)} title="Product uit de voorraad op dit ticket (of laten bestellen)" />
              <Btn s icon={CalendarPlus} onClick={async () => { if (await serviceCall(t)) klaar(); }} title="Service call inplannen (ook in de Outlook-agenda)" />
              <Btn s icon={MonitorPlay} onClick={() => meekijkenTicket(t)} title="Meekijken (Datto RMM web remote)" />
              <Btn s icon={CheckCircle2} onClick={() => afronden([t])} title="Oplossing, tijd en Complete / Ready to Invoice" />
              {t.url && <Btn s icon={ExternalLink} onClick={() => openUrl(t.url)} title="Openen in Autotask" />}
            </div>
          </div>))}
        {!lijst.length && <div className="hint" style={{ padding: 14 }}>{d.tickets.length ? 'Geen tickets in deze selectie.' : 'De queue is leeg. Mooi werk!'}</div>}
      </div>
    </>);
}

// Langlopend (bijv. reparatie van weken): nooit een incident, buiten de SLA, telt niet mee in de cijfers. Iedereen mag dit.
export async function langlopendZetten(tickets, aan) {
  const reden = aan ? await openModal((close) => <Tekstvenster titel={tickets.length === 1 ? `Langlopend ticket · ${tickets[0].number}` : `Langlopend: ${tickets.length} tickets`}
    label="Waarom langlopend? (optioneel, bijv. 'Chromebook op reparatie bij leverancier')" knop="Markeren als langlopend" verplicht={false} close={close} />) : '';
  if (reden === null) return false;
  const x = await act('sd.langlopend', { ids: tickets.map((t) => t.id), on: aan, reason: reden }, { msg: aan ? 'Markeren als langlopend (buiten SLA)...' : 'Terugzetten...' });
  if (x) toast(aan ? `Gemarkeerd als langlopend: geen incident, buiten de SLA.` : 'Ticket telt weer mee in de cijfers.', 'g');
  return !!x;
}

const inProgress = (pl) => (pl.statuses.find((s) => /in progress|in behandeling|bezig/i.test(s.label)) || {}).value;

const Tegel = ({ l, n, k, sub, on, onClick }) => (
  <div className={'sdq-tegel' + (on ? ' on' : '') + (onClick ? ' klik' : '')} onClick={onClick}>
    <div className="l">{l}</div>
    <div className="n" style={k ? { color: `var(--${k})` } : undefined}>{nl(n)}</div>
    {sub && <div className="s">{sub}</div>}
  </div>);

function Escaleren({ tickets, close }) {
  const [reden, setReden] = useState('');
  const [wie, setWie] = useState('');
  const [leden, setLeden] = useState([]);
  useEffect(() => { api('sd.queue', { level: 'l2' }, { quiet: true }).then((x) => setLeden(x.members || [])).catch(() => {}); }, []);
  return (
    <>
      <h3>{tickets.length === 1 ? `Escaleren naar L2 · ${tickets[0].number}` : `${tickets.length} tickets escaleren naar L2`}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{tickets.slice(0, 4).map((t) => t.title).join(' · ')}{tickets.length > 4 ? ' ...' : ''}</div>
      <label className="f">Waarom L2? Wat heb je al geprobeerd? (komt als notitie op het ticket)</label>
      <textarea rows={5} autoFocus value={reden} onChange={(e) => setReden(e.target.value)} placeholder="Bijv.: Intune-inschrijving faalt met fout 0x80180014, apparaat al uit Entra verwijderd en opnieuw geprobeerd." />
      <label className="f">Direct toewijzen aan (optioneel)</label>
      <select value={wie} onChange={(e) => setWie(e.target.value)} style={{ width: 'auto', minWidth: 240 }}>
        <option value="">Nog niemand (L2 pakt het op)</option>
        {leden.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={reden.trim().length < 10} onClick={() => close({ reason: reden.trim(), resourceId: wie ? +wie : null })}>Escaleren</button></div>
    </>);
}

function Tekstvenster({ titel, label, knop, close, min = 5, verplicht = true, start = '' }) {
  const [t, setT] = useState(start);
  return (
    <>
      <h3>{titel}</h3>
      <label className="f">{label}</label>
      <textarea rows={5} autoFocus value={t} onChange={(e) => setT(e.target.value)} />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={verplicht && t.trim().length < min} onClick={() => close(t.trim())}>{knop}</button></div>
    </>);
}

// ================================================================ Changes
export function Changes() {
  const [d, setD] = useState(null);
  const [sel, setSel] = useState([]);
  const [open, setOpen] = useState(null);
  const laad = () => api('sd.changes', {}, { quiet: true }).then(setD).catch((e) => setD({ tickets: [], error: e.message }));
  useEffect(() => { laad(); }, []);
  if (!d) return <Loading text="Change requests ophalen..." />;
  const wacht = d.tickets.filter((t) => t.myVote == null);
  const stem = async (ids, ja) => {
    const note = await openModal((close) => <Tekstvenster titel={`${ids.length} change(s) ${ja ? 'goedkeuren' : 'afkeuren'}`} knop={ja ? 'Goedkeuren' : 'Afkeuren'}
      label={ja ? 'Opmerking (optioneel)' : 'Waarom afgekeurd? (verplicht, de engineer ziet dit)'} verplicht={!ja} start={ja ? 'Akkoord' : ''} close={close} />);
    if (note == null) return;
    const r = await act('sd.changes.stem', { ids, decision: ja ? 'approve' : 'reject', note }, { msg: ja ? 'Goedkeuren...' : 'Afkeuren...' });
    if (!r) return;
    const mis = r.results.filter((x) => !x.ok);
    if (mis.length) {
      openModal((close) => (<>
        <h3>{r.ok} gelukt, {mis.length} niet</h3>
        <Msg kind="warn">Autotask accepteerde deze stemmen niet via de API. Stem voor deze changes in Autotask zelf:</Msg>
        {mis.map((x) => <div key={x.id} style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '6px 0' }}>
          <b>{(d.tickets.find((t) => t.id === x.id) || {}).number || x.id}</b>{x.url && <Btn s icon={ExternalLink} onClick={() => openUrl(x.url)}>Openen</Btn>}</div>)}
        <div className="foot"><button className="btn p" onClick={() => close()}>Sluiten</button></div></>));
    } else toast(`${r.ok} change(s) ${ja ? 'goedgekeurd' : 'afgekeurd'}.`, 'g');
    setSel([]); laad();
  };
  return (
    <>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      <div className="headrow" style={{ marginBottom: 8 }}>
        <div className="hint" style={{ margin: 0 }}><b>{wacht.length}</b> change(s) wachten op jouw besluit · {d.tickets.length - wacht.length} al beoordeeld</div>
        <Btn s icon={RefreshCw} onClick={() => { setD(null); laad(); }}>Vernieuwen</Btn>
      </div>
      <div className="sdq-bulk">
        <AllesVink ids={wacht.map((t) => t.id)} value={sel} onChange={setSel} label={`Alle openstaande selecteren (${wacht.length})`} />
        {sel.length > 0 && <>
          <b>{sel.length} gekozen</b>
          <Btn s v="p" icon={ThumbsUp} onClick={() => stem(sel, true)}>Goedkeuren</Btn>
          <Btn s icon={ThumbsDown} onClick={() => stem(sel, false)}>Afkeuren</Btn>
        </>}
      </div>
      <div className="sdq-lijst">
        {d.tickets.map((t) => (
          <div key={t.id} className={'sdq-rij' + (sel.includes(t.id) ? ' gekozen' : '') + (t.myVote != null ? ' grijs' : '')}>
            <input type="checkbox" disabled={t.myVote != null} checked={sel.includes(t.id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, t.id] : s.filter((x) => x !== t.id)))} />
            <div className="sdq-hoofd" onClick={() => setOpen(open === t.id ? null : t.id)}>
              <div className="sdq-titel">{t.title}</div>
              <div className="sdq-meta">
                <span>{t.number}</span><b>{t.company}</b><span>{t.created}</span>
                <Chip k={/partial|gedeelt/i.test(t.approval) ? 'o' : 'mu'}>{t.approval || 'wacht op besluit'}</Chip>
                {t.priority && <Chip k={hoog(t.priority) ? 'r' : 'mu'}>{t.priority}</Chip>}
                {t.assigned && <span><UserCheck size={12} /> {t.assigned}</span>}
                {t.myVote === true && <Chip k="g">door jou goedgekeurd</Chip>}{t.myVote === false && <Chip k="r">door jou afgekeurd</Chip>}
              </div>
              {(t.votes || []).length > 0 && <div className="sdq-meta">{t.votes.map((v, i) => (
                <span key={i}>{v.vote == null ? <Clock size={12} /> : v.vote ? <Check size={12} style={{ color: 'var(--gr)' }} /> : <X size={12} style={{ color: 'var(--rd)' }} />} {v.name}{v.note ? `: ${v.note}` : ''}</span>))}</div>}
              {open === t.id && <div className="sdq-tekst">{[t.description, ...(t.info || [])].filter(Boolean).join('\n') || 'Geen omschrijving.'}</div>}
            </div>
            <div className="btns sdq-acties">
              {t.myVote == null && <><Btn s v="p" icon={ThumbsUp} onClick={() => stem([t.id], true)}>Goed</Btn><Btn s icon={ThumbsDown} onClick={() => stem([t.id], false)}>Af</Btn></>}
              {t.url && <Btn s icon={ExternalLink} onClick={() => openUrl(t.url)} title="Openen in Autotask" />}
            </div>
          </div>))}
        {!d.tickets.length && <div className="hint" style={{ padding: 14 }}>Er wachten geen change requests op een besluit.</div>}
      </div>
    </>);
}

// ================================================================ Monitoring (KPI's L1/L2)
const Kaart = ({ icon: I, titel, uitleg, children }) => (
  <div className="mg-kaart">
    {titel && <h3><span>{I && <I size={17} />}{titel}</span></h3>}
    {uitleg ? <p className="mg-uitleg">{uitleg}</p> : <div style={{ height: 10 }} />}
    {children}
  </div>);
const Kpi = ({ l, n, s, k }) => (
  <div className="mg-kpi"><div className="l">{l}</div><div className="n" style={k ? { color: `var(--${k})` } : undefined}>{n}</div><div className="s"><span>{s}</span></div></div>);

export function Monitoring() {
  const [d, setD] = useState(null);
  const [dagen, setDagen] = useState(30);
  const laad = (fresh, dg = dagen) => { setD(null); api('sd.kpi', { days: dg, fresh: !!fresh }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message })); };
  useEffect(() => { laad(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const exporteer = () => csv('servicedesk-kpi.csv', [['Medewerker', 'Niveau', 'Afgehandeld', 'Open', 'Uren', 'Mediaan doorlooptijd (uur)'],
    ...d.employees.map((m) => [m.name, m.level.toUpperCase(), m.resolved, m.open, m.hours, m.medianHours ?? ''])]);
  const hero = (inhoud) => (
    <div className="mg-hero" style={{ marginTop: 0 }}>
      <div className="mg-top">
        <div><h2>Monitoring servicedesk</h2><div className="mg-sub">{d && d.kpi ? `Stand ${d.at} · laatste ${d.days} dagen · doel: ${d.goals.l1}% door L1, max. ${d.goals.escalation}% escalaties` : 'KPI\'s van het L1/L2-model uit Autotask'}</div></div>
        <div className="mg-acties">
          <select value={dagen} onChange={(e) => { setDagen(+e.target.value); laad(false, +e.target.value); }} style={{ width: 'auto' }}>
            {[7, 30, 90, 180].map((v) => <option key={v} value={v}>Laatste {v} dagen</option>)}
          </select>
          {d && d.kpi && <Btn icon={ArrowDownToLine} onClick={exporteer}>CSV</Btn>}
          <Btn icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn>
        </div>
      </div>
      {inhoud}
    </div>);
  if (!d) return <>{hero(null)}<Loading text="KPI's berekenen uit Autotask..." /></>;
  if (d.error) return <>{hero(null)}<Msg kind="warn">{d.error}</Msg></>;
  const k = d.kpi;
  const doelKleur = (v, doel, hoger = true) => (v == null ? undefined : (hoger ? v >= doel : v <= doel) ? 'gr' : 'or');
  const tot = (o) => (o.l1 || 0) + (o.l2 || 0) + (o.overig || 0);
  return (
    <div className="mg">
      {hero(
        <div className="mg-kpis">
          <Kpi l="Afgehandeld door L1" n={pc(k.l1Pct)} s={`doel ${d.goals.l1}% · ${nl(k.l1Resolved)} van ${nl(k.l1Resolved + k.l2Resolved)}`} k={doelKleur(k.l1Pct, d.goals.l1)} />
          <Kpi l="Escalaties naar L2" n={pc(k.escalationPct)} s={`max. ${d.goals.escalation}% · ${nl(k.escalated)} tickets`} k={doelKleur(k.escalationPct, d.goals.escalation, false)} />
          <Kpi l="Open nu" n={nl(k.open)} s={`L1 ${nl(k.openL1)} · L2 ${nl(k.openL2)}${k.longRunning ? ` · ${nl(k.longRunning)} langlopend` : ''}`} />
          <Kpi l="Zonder behandelaar" n={nl(k.unassigned)} s={`${nl(k.overdue)} over de deadline`} k={k.unassigned ? 'or' : 'gr'} />
          <Kpi l="Eerste reactie" n={duur(k.firstResponseMedianH)} s="mediaan" />
          <Kpi l="SLA gehaald" n={pc(k.slaPct)} s={`${nl(k.resolved)} afgerond · ${nl(k.created)} nieuw`} />
        </div>)}

      {d.signals.length > 0 && (
        <Kaart icon={AlertTriangle} titel="Aandachtspunten">
          <div className="mg-punten">{d.signals.map((s, i) => <div key={i} className="mg-punt"><i style={{ background: `var(--${{ err: 'rd', warn: 'or', info: 'hd' }[s.level]})` }} /><b>{{ err: 'Kritiek', warn: 'Aandacht', info: 'Info' }[s.level]}</b><span>{s.text}</span></div>)}</div>
        </Kaart>)}

      <div className="mg-raster-2">
        <Kaart icon={Target} titel="Wie lost het op?" uitleg="Doel van het nieuwe model: 80-90% van de tickets wordt door de servicedesk (L1) afgehandeld.">
          <div style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
            <Meter pct={k.l1Pct || 0} label="door L1" drempels={[d.goals.l1, d.goals.l1 - 10]} />
            <Donut delen={[['L1 servicedesk', k.l1Resolved, 'gr'], ['L2 escalatie', k.l2Resolved, 'navy'], ['Overig', k.otherResolved, 'mu2']]} midden={nl(k.resolved)} sub="afgerond" maat={150} />
          </div>
        </Kaart>
        <Kaart icon={BarChart3} titel="Per week" uitleg="Binnengekomen en afgerond, en het aandeel van L1.">
          <Lijn labels={d.trend.map((w) => w.week.slice(5))} reeksen={[{ naam: 'Binnengekomen', kleur: 'hd', waarden: d.trend.map((w) => w.created) },
            { naam: 'Afgerond', kleur: 'gr', waarden: d.trend.map((w) => w.resolved) }]} hoogte={210} />
        </Kaart>
      </div>
      <div className="mg-raster-2">
        <Kaart icon={Clock} titel="Doorlooptijd (mediaan)" uitleg="Van aanmaken tot afgerond.">
          <Staven rijen={[['L1 servicedesk', k.medianHoursL1 || 0], ['L2 escalatie', k.medianHoursL2 || 0], ['Alles', k.medianHours || 0]]} eenheid=" uur" dec={1} />
        </Kaart>
        <Kaart icon={Gauge} titel="Uren en omzet per niveau" uitleg="Gewerkte uren, factureerbare uren en de omzet daarvan (tarief L1/L2 of het tarief van de rol).">
          <Kolommen labels={['L1', 'L2', 'Overig']} reeksen={[{ naam: 'Gewerkt', kleur: 'navy', waarden: [d.hours.l1, d.hours.l2, d.hours.overig] },
            { naam: 'Factureerbaar', kleur: 'cy', waarden: [d.billable.l1, d.billable.l2, d.billable.overig] }]} dec={1} hoogte={190} />
          <div className="hint" style={{ margin: '6px 0 0' }}>Omzet: L1 € {nl(d.revenue.l1)} · L2 € {nl(d.revenue.l2)} · totaal € {nl(tot(d.revenue))}</div>
        </Kaart>
      </div>
      <Kaart icon={Users} titel="Per medewerker" uitleg="Afgehandelde tickets, wat er nog openstaat en de gewerkte uren in de periode.">
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%' }}>
            <thead><tr><th>Medewerker</th><th>Niveau</th><th style={{ textAlign: 'right' }}>Afgehandeld</th><th style={{ textAlign: 'right' }}>Open</th>
              <th style={{ textAlign: 'right' }}>Uren</th><th style={{ textAlign: 'right' }}>Doorlooptijd</th><th>Meeste tickets van</th></tr></thead>
            <tbody>{d.employees.map((m) => (
              <tr key={m.id}><td><b>{m.name}</b></td><td><Chip k={m.level === 'l1' ? 'g' : m.level === 'l2' ? '' : 'mu'}>{m.level === 'overig' ? 'overig' : m.level.toUpperCase()}</Chip></td>
                <td style={{ textAlign: 'right' }}>{nl(m.resolved)}</td><td style={{ textAlign: 'right' }}>{nl(m.open)}</td>
                <td style={{ textAlign: 'right' }}>{nl(m.hours, 1)}</td><td style={{ textAlign: 'right' }}>{duur(m.medianHours)}</td>
                <td>{m.topCompany ? <>{m.topCompany.name} <span className="hint" style={{ margin: 0 }}>{m.topCompany.pct}% ({m.topCompany.count})</span></> : '-'}</td></tr>))}</tbody>
          </table>
        </div>
      </Kaart>
      <Kaart icon={Clock} titel="Oudste open tickets">
        {d.oldest.map((t) => (
          <div key={t.id} className="mg-punt" style={{ cursor: t.url ? 'pointer' : 'default' }} onClick={() => openUrl(t.url)}>
            <i style={{ background: `var(--${t.days > 14 ? 'rd' : 'or'})` }} /><b>{t.days} d</b><span>{t.number} · {t.title} · {t.company}{t.level ? ` · ${t.level.toUpperCase()}` : ''}{t.assigned ? ` · ${t.assigned}` : ' · niemand'}</span></div>))}
      </Kaart>
    </div>);
}

// ================================================================ Inrichting (alleen app-beheerder)
export function Inrichting() {
  const [d, setD] = useState(null);
  const [s, setS] = useState(null);
  useEffect(() => { api('sd.inrichting', {}, { quiet: true }).then((x) => { setD(x); setS(x.settings); }).catch((e) => setD({ error: e.message })); }, []);
  if (!d) return <Loading text="Inrichting ophalen..." />;
  if (d.error) return <Msg kind="warn">{d.error}</Msg>;
  const z = (k) => (e) => setS({ ...s, [k]: e.target.value === '' ? null : e.target.value });
  const lijst = (k) => (
    <div className="sdq-kies">{d.resources.map((r) => (
      <label key={r.id} className="chk"><input type="checkbox" checked={(s[k] || []).includes(r.id)}
        onChange={(e) => setS({ ...s, [k]: e.target.checked ? [...(s[k] || []), r.id] : (s[k] || []).filter((x) => x !== r.id) })} /><span>{r.name}</span></label>))}</div>);
  const bewaar = async () => {
    const r = await act('sd.inrichting.set', { settings: { ...s, l1Queue: s.l1Queue ? +s.l1Queue : null, l2Queue: s.l2Queue ? +s.l2Queue : null } }, { msg: 'Opslaan...' });
    if (r) { setS(r.settings); toast('Inrichting opgeslagen voor iedereen.', 'g'); }
  };
  return (
    <div className="card" style={{ padding: 18 }}>
      <h3 style={{ marginTop: 0 }}><ShieldCheck size={18} /> Inrichting servicedesk (L1 / L2)</h3>
      <div className="hint" style={{ marginTop: 0 }}>Alle nieuwe tickets uit de app landen in de L1-queue. L1 escaleert naar de L2-queue. Medewerkers en tarieven komen uit Autotask; er staan geen namen in de app zelf.</div>
      {(s.auto || []).length > 0 && <Msg kind="info">Automatisch overgenomen uit Autotask: {s.auto.join(', ')}. Pas het hieronder aan en sla op om het vast te zetten (bijv. wie de triage doet en meldingen krijgt).</Msg>}
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        <div><label className="f">Queue L1 (servicedesk)</label><select value={s.l1Queue || ''} onChange={z('l1Queue')}><option value="">Kies...</option>{d.queues.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}</select></div>
        <div><label className="f">Queue L2 (escalatie)</label><select value={s.l2Queue || ''} onChange={z('l2Queue')}><option value="">Kies...</option>{d.queues.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}</select></div>
      </div>
      <label className="f">L1: verantwoordelijk voor triage (krijgen meldingen van nieuwe tickets)</label>{lijst('l1Leads')}
      <label className="f">L1: ondersteuning servicedesk</label>{lijst('l1')}
      <label className="f">L2: specialisten (escalaties)</label>{lijst('l2')}
      <label className="f">Change-goedkeurders (naast de app-beheerder)</label>{lijst('approvers')}
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        <div><label className="f">Tarief L1 per uur (€, leeg = tarief van de rol)</label><input type="number" min={0} value={s.tariefL1 ?? ''} onChange={z('tariefL1')} style={{ width: 160 }} /></div>
        <div><label className="f">Tarief L2 per uur (€)</label><input type="number" min={0} value={s.tariefL2 ?? ''} onChange={z('tariefL2')} style={{ width: 160 }} /></div>
        <div><label className="f">Doel: % door L1</label><input type="number" min={50} max={100} value={s.doelL1} onChange={z('doelL1')} style={{ width: 110 }} /></div>
        <div><label className="f">Max. % escalaties</label><input type="number" min={0} max={100} value={s.escalatieMax} onChange={z('escalatieMax')} style={{ width: 110 }} /></div>
        <div><label className="f">Triage binnen (min)</label><input type="number" min={1} max={480} value={s.triageMin} onChange={z('triageMin')} style={{ width: 110 }} /></div>
      </div>
      <div className="btns" style={{ marginTop: 14 }}><Btn v="p" icon={Check} onClick={bewaar}>Opslaan</Btn></div>
    </div>);
}

// ================================================================ Meldingen voor de triage (L1-verantwoordelijken)
// Vraagt elke minuut op welke tickets nieuw en nog niet opgepakt zijn; nieuwe sinds de vorige keer geven een melding
// (in de app, en als Windows/Mac-melding als dat mag) en een teller.
export function useMeldingen(aan) {
  const [stand, setStand] = useState({ tickets: [], nieuw: 0, orders: 0 });
  const gezien = useRef(null);
  const bestel = useRef(null);
  useEffect(() => {
    if (!aan) return undefined;
    let t;
    const vraag = async () => {
      try {
        const r = await api('sd.melding', {}, { quiet: true, achter: true });
        if (r.orders != null) {   // sales: nieuwe aanvragen op de bestellijst
          if (bestel.current != null && r.orders > bestel.current) toast(`Er is iets op de bestellijst gezet (${r.orders} te bestellen). Zie Voorraad.`, 'g');
          bestel.current = r.orders;
          setStand((s) => ({ ...s, orders: r.orders }));
        }
        if (r.lead === false) return;
        const ids = new Set(r.tickets.map((x) => x.id));
        if (gezien.current) {
          const nieuw = r.tickets.filter((x) => !gezien.current.has(x.id));
          nieuw.slice(0, 3).forEach((x) => {
            toast(`Nieuw ticket in de servicedesk: ${x.number} ${x.title}${x.company ? ` (${x.company})` : ''}`, 'g');
            try { if (window.Notification && Notification.permission === 'granted') new Notification('Nieuw servicedeskticket', { body: `${x.title}\n${x.company}` }); } catch { /* geen meldingen */ }
          });
        } else {
          try { if (window.Notification && Notification.permission === 'default') Notification.requestPermission(); } catch { /* geen meldingen */ }
        }
        gezien.current = ids;
        setStand((s) => ({ ...s, tickets: r.tickets, nieuw: r.tickets.length }));
      } catch { /* stil */ } finally { t = setTimeout(vraag, 60000); }
    };
    vraag();
    return () => clearTimeout(t);
  }, [aan]);
  return stand;
}

export const filterTeller = (n) => (n ? <span className="sdq-teller">{n > 99 ? '99+' : n}</span> : null);

// ================================================================ Koppeling Datto RMM (alleen app-beheerder): sites aanmaken vanuit Sales
export function RmmKoppeling() {
  const [s, setS] = useState(null);
  const [v, setV] = useState({ url: 'https://pinotage-api.centrastage.net', key: '', secret: '' });
  const laad = () => api('rmm.status', {}, { quiet: true }).then(setS).catch(() => setS({ configured: false }));
  useEffect(() => { laad(); }, []);
  if (!s) return null;
  const bewaar = async () => { if (await act('rmm.keys.set', v, { msg: 'Datto RMM-koppeling controleren...' })) { toast('Datto RMM gekoppeld.', 'g'); setV({ ...v, key: '', secret: '' }); laad(); } };
  const weg = async () => { if (await act('rmm.keys.delete', {}, { msg: 'Ontkoppelen...' })) laad(); };
  return (
    <div className="card" style={{ padding: 18, marginTop: 14 }}>
      <h3 style={{ marginTop: 0 }}><ShieldCheck size={18} /> Datto RMM</h3>
      <div className="hint" style={{ marginTop: 0 }}>Na een nieuwe klant in Sales maakt de app op verzoek direct de site in Datto RMM aan. API-sleutels: Datto RMM &gt; Setup &gt; Users &gt; gebruiker &gt; Generate API Keys (API-toegang moet aan staan bij Global Settings &gt; Access Control). Daar staat ook de API URL.</div>
      {s.configured ? <div className="btns" style={{ alignItems: 'center' }}><Chip k="g">gekoppeld</Chip><span className="hint" style={{ margin: 0 }}>{s.url}</span><Btn s onClick={weg}>Ontkoppelen</Btn></div> : (
        <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div><label className="f">API URL</label><input value={v.url} onChange={(e) => setV({ ...v, url: e.target.value })} style={{ width: 280 }} /></div>
          <div><label className="f">API key</label><input value={v.key} onChange={(e) => setV({ ...v, key: e.target.value })} style={{ width: 220 }} autoComplete="off" /></div>
          <div><label className="f">API secret</label><input type="password" value={v.secret} onChange={(e) => setV({ ...v, secret: e.target.value })} style={{ width: 220 }} autoComplete="off" /></div>
          <Btn v="p" icon={Check} disabled={!v.key || !v.secret} onClick={bewaar}>Koppelen</Btn>
        </div>)}
    </div>);
}