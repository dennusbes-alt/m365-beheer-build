// Projecten: actieve projecten met voortgang; per project de fasen en taken. Taken oppakken, toewijzen, status wijzigen,
// tijd boeken (Autotask-tijdregel op de taak), taken toevoegen, notities en de projectstatus. Sneller dan door Autotask klikken.
import { useEffect, useState } from 'react';
import { ArrowLeft, BriefcaseBusiness, CheckCircle2, Clock, ExternalLink, Hand, Plus, RefreshCw, StickyNote, UserCheck } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, openModal, toast } from './overlays.jsx';
import { Btn, Chip, Loading, SearchBox } from './ui.jsx';
import { nl } from './Grafiek.jsx';
import { doorgeven } from './store.jsx';

const datum = (s) => (s ? String(s).slice(0, 10).split('-').reverse().join('-') : '-');
const pct = (a, b) => (b ? Math.round((a * 100) / b) : 0);

export default function Projecten() {
  const [open, setOpen] = useState(() => { const z = doorgeven.project; delete doorgeven.project; return z || null; });
  return open ? <Project id={open} terug={() => setOpen(null)} /> : <Lijst onOpen={setOpen} />;
}

function Lijst({ onOpen }) {
  const [d, setD] = useState(null);
  const [toon, setToon] = useState(() => { try { return localStorage.getItem('pr.toon') || 'mijn'; } catch { return 'mijn'; } });
  const [q, setQ] = useState('');
  const laad = (fresh) => api('pr.overzicht', { fresh: !!fresh }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, projects: [], mine: [] }));
  useEffect(() => { laad(false); }, []);
  const kies = (k) => { setToon(k); try { localStorage.setItem('pr.toon', k); } catch { /* geen opslag */ } };
  if (!d) return <div className="klanten breed"><Loading text="Projecten ophalen uit Autotask..." /></div>;
  const lijst = d.projects.filter((p) => (toon === 'mijn' ? d.mine.includes(p.id) : toon === 'laat' ? p.late : true))
    .filter((p) => !q || `${p.name} ${p.number} ${p.company} ${p.lead}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="klanten breed">
      <div className="headrow" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
        <div className="m"><h2 style={{ margin: 0 }}>Projecten</h2><div className="hint" style={{ margin: 0 }}>Actieve projecten en projecttaken: oppakken, toewijzen, status wijzigen en tijd boeken. Stand {d.at}.</div></div>
        <Btn s icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
      </div>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      <div className="headrow" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
        <div className="btns">
          {[['mijn', `Mijn projecten (${d.mine.length})`], ['alle', `Alle actieve (${d.projects.length})`], ['laat', `Over de einddatum (${d.projects.filter((p) => p.late).length})`]].map(([k, l]) => (
            <Btn key={k} s v={toon === k ? 'p' : ''} onClick={() => kies(k)}>{l}</Btn>))}
        </div>
        <div style={{ width: 280 }}><SearchBox value={q} onChange={setQ} placeholder="Zoek project, klant, projectleider..." /></div>
      </div>
      <div className="pr-raster">
        {lijst.map((p) => (
          <div key={p.id} className={'pr-kaart' + (p.late ? ' laat' : '')} onClick={() => onOpen(p.id)}>
            <div className="pr-kop"><BriefcaseBusiness size={16} /><b>{p.name}</b></div>
            <div className="hint" style={{ margin: 0 }}>{p.number} · {p.company}</div>
            <div className="pr-balk"><i style={{ width: `${pct(p.done, p.tasks)}%` }} /></div>
            <div className="sdq-meta">
              <span>{p.done}/{p.tasks} taken af ({pct(p.done, p.tasks)}%)</span>
              {p.estimated > 0 && <span><Clock size={12} /> {nl(p.estimated, 1)} uur gepland</span>}
              <span>tot {datum(p.end)}</span>
              {p.late && <Chip k="r">over de einddatum</Chip>}
            </div>
            <div className="sdq-meta">{p.status && <Chip>{p.status}</Chip>}{p.lead && <span><UserCheck size={12} /> {p.lead}</span>}</div>
          </div>))}
      </div>
      {!lijst.length && <div className="hint" style={{ padding: 10 }}>{toon === 'mijn' ? 'Je hebt geen open taken in actieve projecten. Kijk bij Alle actieve.' : 'Geen projecten in deze selectie.'}</div>}
    </div>);
}

function Project({ id, terug }) {
  const [d, setD] = useState(null);
  const [toon, setToon] = useState('open');
  const [me, setMe] = useState(null);
  const laad = () => api('pr.project', { id }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message }));
  useEffect(() => { laad(); api('pr.overzicht', {}, { quiet: true }).then((x) => setMe(x.me)).catch(() => {}); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <div className="klanten breed"><Loading text="Project ophalen..." /></div>;
  if (d.error) return <div className="klanten breed"><Btn s icon={ArrowLeft} onClick={terug}>Terug</Btn><Msg kind="warn">{d.error}</Msg></div>;
  const p = d.project;
  const klaar = d.tasks.filter((t) => t.done).length;
  const statusKlaar = (d.taskStatuses.find((s) => s.value === 5) || {}).value ?? 5;
  const bezig = (d.taskStatuses.find((s) => /in progress|bezig|in behandeling/i.test(s.label)) || {}).value;
  const wijzig = async (t, body, wat) => { if (await act('pr.taak', { projectId: p.id, id: t.id, ...body }, { msg: `${wat}...` })) { toast(`${wat}: ${t.title}`, 'g'); laad(); } };
  const tijd = async (t) => {
    const r = await openModal((close) => <TijdTaak t={t} close={close} />);
    if (!r) return;
    const eind = new Date();
    eind.setMinutes(Math.ceil(eind.getMinutes() / 15) * 15, 0, 0);
    const start = new Date(eind.getTime() - r.minutes * 60000);
    if (await act('ts.nieuw', { kind: 'taak', refId: t.id, start: start.toISOString(), end: eind.toISOString(), notes: r.text }, { msg: 'Tijd boeken...' })) {
      if (r.klaar) await act('pr.taak', { projectId: p.id, id: t.id, status: statusKlaar }, { quiet: true });
      toast(`${r.minutes} min geboekt op ${t.title}${r.klaar ? ' en afgerond' : ''}.`, 'g'); laad();
    }
  };
  const nieuweTaak = async (fase) => {
    const r = await openModal((close) => <TaakVenster fase={fase} fasen={d.phases} people={d.people} close={close} />, { wide: true });
    if (r && await act('pr.taak.nieuw', { projectId: p.id, ...r }, { msg: 'Taak toevoegen...' })) { toast('Taak toegevoegd.', 'g'); laad(); }
  };
  const notitie = async () => {
    const r = await openModal((close) => <NotitieVenster close={close} />);
    if (r && await act('pr.notitie', { projectId: p.id, ...r }, { msg: 'Notitie toevoegen...' })) { toast('Notitie toegevoegd.', 'g'); laad(); }
  };
  const projectWijzig = async (body) => { if (await act('pr.status', { id: p.id, ...body }, { msg: 'Project bijwerken...' })) { toast('Project bijgewerkt.', 'g'); laad(); } };
  const groepen = [...d.phases.map((f) => [f, d.tasks.filter((t) => t.phaseId === f.id)]), [null, d.tasks.filter((t) => !t.phaseId || !d.phases.some((f) => f.id === t.phaseId))]]
    .map(([f, l]) => [f, l.filter((t) => (toon === 'open' ? !t.done : toon === 'mijn' ? t.assignedId === me && !t.done : true))]).filter(([f, l]) => l.length || (f && toon === 'alle'));
  const uren = d.tasks.reduce((s, t) => s + t.worked, 0), gepland = d.tasks.reduce((s, t) => s + t.estimated, 0);

  return (
    <div className="klanten breed">
      <Btn s icon={ArrowLeft} onClick={terug}>Alle projecten</Btn>
      <div className="pr-hero">
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{ margin: 0 }}>{p.name}</h2>
          <div className="hint" style={{ margin: 0 }}>{p.number} · <b>{p.company}</b> · {datum(p.start)} t/m {datum(p.end)}</div>
          <div className="pr-balk" style={{ maxWidth: 460, marginTop: 8 }}><i style={{ width: `${pct(klaar, d.tasks.length)}%` }} /></div>
          <div className="sdq-meta"><span>{klaar}/{d.tasks.length} taken af</span><span><Clock size={12} /> {nl(uren, 1)} van {nl(gepland, 1)} uur geboekt</span></div>
        </div>
        <div className="btns" style={{ alignItems: 'center' }}>
          <select value={p.statusId ?? ''} onChange={(e) => projectWijzig({ status: +e.target.value })} title="Projectstatus" style={{ width: 'auto' }}>
            {d.projectStatuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <select value={p.leadId || ''} onChange={(e) => e.target.value && projectWijzig({ leadId: +e.target.value })} title="Projectleider" style={{ width: 'auto' }}>
            <option value="">Projectleider...</option>{d.people.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <Btn s icon={StickyNote} onClick={notitie}>Notitie</Btn>
          <Btn s v="p" icon={Plus} onClick={() => nieuweTaak(null)}>Taak</Btn>
          {p.url && <Btn s icon={ExternalLink} onClick={() => act('open.url', { url: p.url }, { nobusy: true, quiet: true })} title="Openen in Autotask" />}
        </div>
      </div>
      {p.description && <div className="pr-omschrijving">{p.description}</div>}
      <div className="btns" style={{ margin: '10px 0' }}>
        {[['open', 'Open taken'], ['mijn', 'Mijn taken'], ['alle', 'Alle taken']].map(([k, l]) => <Btn key={k} s v={toon === k ? 'p' : ''} onClick={() => setToon(k)}>{l}</Btn>)}
      </div>
      {groepen.map(([f, l]) => (
        <div key={f ? f.id : 'los'} className="pr-fase">
          <div className="pr-fase-kop"><b>{f ? f.title : 'Zonder fase'}</b>{f && f.end && <span className="hint" style={{ margin: 0 }}>klaar op {datum(f.end)}</span>}
            <button type="button" className="linkknop" onClick={() => nieuweTaak(f)}><Plus size={13} /> taak</button></div>
          {l.map((t) => (
            <div key={t.id} className={'sdq-rij' + (t.late ? ' laat' : '') + (t.done ? ' grijs' : '')}>
              <input type="checkbox" checked={t.done} title={t.done ? 'Afgerond' : 'Afronden'} onChange={(e) => wijzig(t, { status: e.target.checked ? statusKlaar : (bezig || 1) }, e.target.checked ? 'Afgerond' : 'Heropend')} />
              <div className="sdq-hoofd">
                <div className="sdq-titel">{t.title}</div>
                <div className="sdq-meta">
                  {t.status && <Chip k={t.done ? 'g' : ''}>{t.status}</Chip>}
                  {t.assigned ? <span><UserCheck size={12} /> {t.assigned}</span> : <Chip k="o">niemand</Chip>}
                  <span><Clock size={12} /> {nl(t.worked, 1)}{t.estimated ? ` / ${nl(t.estimated, 1)}` : ''} uur</span>
                  {t.end && <span>tot {datum(t.end)}</span>}{t.late && <Chip k="r">te laat</Chip>}
                </div>
                {t.description && <div className="sdq-tekst">{t.description.slice(0, 300)}</div>}
              </div>
              <div className="btns sdq-acties">
                {me && t.assignedId !== me && !t.done && <Btn s icon={Hand} onClick={() => wijzig(t, { assignedId: me, status: bezig }, 'Opgepakt')}>Oppakken</Btn>}
                <select value={t.statusId ?? ''} onChange={(e) => wijzig(t, { status: +e.target.value }, 'Status gewijzigd')} style={{ width: 130 }} title="Status">
                  {d.taskStatuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
                <select value={t.assignedId || ''} onChange={(e) => wijzig(t, { assignedId: e.target.value ? +e.target.value : null }, 'Toegewezen')} style={{ width: 140 }} title="Toewijzen">
                  <option value="">Niemand</option>{d.people.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
                <Btn s icon={Clock} onClick={() => tijd(t)}>Tijd</Btn>
              </div>
            </div>))}
        </div>))}
      {d.notes.length > 0 && (
        <div className="mg-kaart" style={{ marginTop: 14 }}>
          <h3><span><StickyNote size={17} />Notities</span></h3>
          {d.notes.map((n) => <div key={n.id} style={{ borderTop: '1px solid var(--bd)', padding: '8px 0' }}><b>{n.title}</b> <span className="hint">{n.at}</span><div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{n.text}</div></div>)}
        </div>)}
    </div>);
}

function TijdTaak({ t, close }) {
  const [min, setMin] = useState(30);
  const [tekst, setTekst] = useState('');
  const [af, setAf] = useState(false);
  return (
    <>
      <h3>Tijd boeken · {t.title}</h3>
      <div className="hint" style={{ marginTop: 0 }}>De tijd wordt geboekt tot nu (afgerond op het kwartier). Andere tijden? Gebruik de Timesheet.</div>
      <div className="btns" style={{ alignItems: 'center' }}>{[15, 30, 45, 60, 90, 120, 240].map((m) => <Btn key={m} s v={min === m ? 'p' : ''} onClick={() => setMin(m)}>{m < 60 ? `${m} min` : `${m / 60} uur`}</Btn>)}
        <input type="number" min={15} step={15} value={min} onChange={(e) => setMin(+e.target.value)} style={{ width: 90 }} /> min</div>
      <label className="f">Wat heb je gedaan?</label>
      <textarea rows={4} autoFocus value={tekst} onChange={(e) => setTekst(e.target.value)} />
      <label className="chk" style={{ marginTop: 8 }}><input type="checkbox" checked={af} onChange={(e) => setAf(e.target.checked)} /><span>Taak daarna afronden</span></label>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={min < 1 || tekst.trim().length < 3} onClick={() => close({ minutes: min, text: tekst.trim(), klaar: af })}><CheckCircle2 size={15} /> Boeken</button></div>
    </>);
}

function TaakVenster({ fase, fasen, people, close }) {
  const [v, setV] = useState({ title: '', description: '', estimated: '', assignedId: '', end: '', phaseId: fase ? fase.id : '' });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  return (
    <>
      <h3>Nieuwe projecttaak</h3>
      <label className="f">Titel</label><input autoFocus value={v.title} onChange={z('title')} style={{ width: '100%' }} />
      <label className="f">Omschrijving</label><textarea rows={3} value={v.description} onChange={z('description')} />
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Fase</label><select value={v.phaseId} onChange={z('phaseId')} style={{ width: 'auto', minWidth: 180 }}><option value="">Geen fase</option>{fasen.map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}</select></div>
        <div><label className="f">Toewijzen aan</label><select value={v.assignedId} onChange={z('assignedId')} style={{ width: 'auto', minWidth: 180 }}><option value="">Niemand</option>{people.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></div>
        <div><label className="f">Geschatte uren</label><input type="number" min={0} step={0.25} value={v.estimated} onChange={z('estimated')} style={{ width: 110 }} /></div>
        <div><label className="f">Klaar op</label><input type="date" value={v.end} onChange={z('end')} style={{ width: 170 }} /></div>
      </div>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={v.title.trim().length < 3} onClick={() => close({ ...v, title: v.title.trim(), phaseId: v.phaseId || null, assignedId: v.assignedId || null, estimated: v.estimated || null, end: v.end || null })}>Toevoegen</button></div>
    </>);
}

function NotitieVenster({ close }) {
  const [t, setT] = useState('Notitie');
  const [x, setX] = useState('');
  return (
    <>
      <h3>Projectnotitie</h3>
      <label className="f">Titel</label><input value={t} onChange={(e) => setT(e.target.value)} />
      <label className="f">Notitie</label><textarea rows={6} autoFocus value={x} onChange={(e) => setX(e.target.value)} />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!x.trim()} onClick={() => close({ title: t.trim() || 'Notitie', text: x.trim() })}>Toevoegen</button></div>
    </>);
}
