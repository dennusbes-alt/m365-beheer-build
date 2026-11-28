// Servicestatus van Microsoft 365 en het Berichtencentrum, in begrijpelijke taal.
import { useEffect, useRef, useState } from 'react';
import { startTab } from '../store.jsx';
import { Activity, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock, Megaphone, RefreshCw } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, openModal } from '../overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox, Tabs, dt, useFilter } from '../ui.jsx';

const ELKE = 5 * 60 * 1000;   // automatisch verversen
const Status = ({ s }) => <Chip k={s.kind}>{s.text}</Chip>;
const Tegel = ({ label, n, kleur, sub }) => (
  <Card><div className="hint" style={{ margin: 0 }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 900, color: kleur ? `var(--${kleur})` : 'var(--navy)' }}>{n}</div>
    {sub && <div className="hint" style={{ margin: 0 }}>{sub}</div>}</Card>
);
const Onderdelen = ({ parts }) => (
  <div className="kv" style={{ gridTemplateColumns: '1fr', gap: 8 }}>
    {parts.filter((p) => p.label !== 'Titel').map((p, i) => <div key={i}><label>{p.label}</label><div style={{ whiteSpace: 'pre-line' }}>{p.text}</div></div>)}
  </div>
);

export default function Health() {
  const [tab, setTab] = useState(() => startTab('health', 'nu'));
  return (
    <>
      <h2>Servicestatus</h2>
      <p className="sub">Actuele storingen en meldingen van Microsoft 365 bij deze klant, en aangekondigde wijzigingen uit het Berichtencentrum. Status, diensten en kopjes staan in het Nederlands; de toelichting van Microsoft is Engels.</p>
      <Tabs value={tab} onChange={setTab} tabs={[['nu', 'Actueel', Activity], ['berichten', 'Berichtencentrum', Megaphone]]} />
      {tab === 'nu' ? <Actueel /> : <Berichten />}
    </>
  );
}

function Actueel() {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [alleDiensten, setAlleDiensten] = useState(false);
  const timer = useRef(null);
  const ververs = async (stil) => {
    try {
      const x = await api('health.overview', {}, { quiet: true });
      setD(x); setFout('');
    } catch (e) { if (!stil || !d) setFout(e.message || String(e)); }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => ververs(true), ELKE);
  };
  useEffect(() => { ververs(false); return () => clearTimeout(timer.current); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (fout && !d) return <Msg kind="warn">{fout}</Msg>;
  if (!d) return <Loading text="Servicestatus ophalen..." />;
  const problemen = d.services.filter((s) => s.status.code !== 'serviceOperational');
  const storingen = d.active.filter((i) => i.kind === 'incident');
  const meldingen = d.active.filter((i) => i.kind !== 'incident');
  const diensten = alleDiensten ? d.services : (problemen.length ? problemen : []);
  return (
    <>
      <div className="tegels">
        <Tegel label="Diensten met problemen" n={problemen.length} kleur={problemen.length ? 'or' : 'gr'} sub={`van ${d.services.length} diensten`} />
        <Tegel label="Lopende storingen" n={storingen.length} kleur={storingen.length ? 'rd' : 'gr'} sub="gebruikers merken het direct" />
        <Tegel label="Lopende meldingen" n={meldingen.length} kleur={meldingen.length ? 'or' : 'gr'} sub="beperkt of voor een deel merkbaar" />
        <Tegel label="Opgelost (7 dagen)" n={d.recent.length} sub={`bijgewerkt om ${d.at}, ververst elke 5 min`} />
      </div>
      {!d.active.length && <Msg kind="ok">Er zijn op dit moment geen storingen of meldingen bij Microsoft 365 voor deze klant.</Msg>}
      {d.issuesError && <Msg kind="warn">{d.issuesError}</Msg>}

      <Card title="Diensten" icon={Activity} right={<div className="btns">
        <label className="hint" style={{ margin: 0 }}><input type="checkbox" checked={alleDiensten} onChange={(e) => setAlleDiensten(e.target.checked)} /> Alle diensten tonen</label>
        <Btn s icon={RefreshCw} onClick={() => ververs(false)}>Vernieuwen</Btn></div>}>
        {diensten.length ? (
          <table>
            <thead><tr><th>Dienst</th><th>Status</th><th className="r">Storingen</th><th className="r">Meldingen</th></tr></thead>
            <tbody>{diensten.map((s) => (
              <tr key={s.name}><td><b>{s.name}</b></td><td><Status s={s.status} /></td>
                <td className="r">{s.incidents || '-'}</td><td className="r">{s.advisories || '-'}</td></tr>))}</tbody>
          </table>
        ) : <div className="hint" style={{ margin: 0 }}><CheckCircle2 size={14} style={{ verticalAlign: -2, color: 'var(--gr)' }} /> Alle {d.services.length} diensten werken normaal.</div>}
      </Card>

      {d.active.length > 0 && <Card title={`Lopend (${d.active.length})`} icon={AlertTriangle}>{d.active.map((i) => <Issue key={i.id} i={i} />)}</Card>}
      {d.recent.length > 0 && <Card title={`Opgelost in de afgelopen 7 dagen (${d.recent.length})`} icon={CheckCircle2}>{d.recent.map((i) => <Issue key={i.id} i={i} />)}</Card>}
    </>
  );
}

function Issue({ i }) {
  const [open, setOpen] = useState(false);
  const detail = () => openModal((close) => <IssueDetail id={i.id} close={close} />, { wide: true });
  return (
    <div style={{ borderTop: '1px solid var(--bd)', padding: '10px 0' }}>
      <div className="click" style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }} onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={16} style={{ marginTop: 3 }} /> : <ChevronRight size={16} style={{ marginTop: 3 }} />}
        <div style={{ flex: 1 }}>
          <div><Chip k={i.kind === 'incident' ? 'r' : 'o'} title={i.kindHint}>{i.kindText}</Chip> <b>{i.service}</b>{i.feature && <span className="hint"> · {i.feature}</span>} <Status s={i.status} /></div>
          <div style={{ marginTop: 4 }}>{i.title}</div>
          <div className="hint" style={{ margin: '2px 0 0' }}><Clock size={12} style={{ verticalAlign: -2 }} /> Sinds {dt(i.start)}{i.end ? ` · opgelost ${dt(i.end)}` : ''} · laatste update {dt(i.updated)} · {i.id}</div>
        </div>
      </div>
      {open && (
        <div style={{ margin: '10px 0 0 26px' }}>
          {i.impact && <div style={{ marginBottom: 8 }}><label className="f" style={{ margin: 0 }}>Samenvatting van Microsoft</label><div>{i.impact}</div></div>}
          {i.latest.length ? <Onderdelen parts={i.latest} /> : <div style={{ whiteSpace: 'pre-line' }}>{i.latestRaw}</div>}
          <div style={{ marginTop: 8 }}><Btn s onClick={detail}>Alle updates</Btn></div>
        </div>
      )}
    </div>
  );
}

function IssueDetail({ id, close }) {
  const [d, setD] = useState(null);
  useEffect(() => { act('health.issue', { id }).then((x) => setD(x || {})); }, [id]);
  return (
    <>
      {!d ? <Loading /> : (
        <>
          <h3>{d.title}</h3>
          <div style={{ marginBottom: 10 }}><Chip k={d.kind === 'incident' ? 'r' : 'o'}>{d.kindText}</Chip> <b>{d.service}</b> {d.status && <Status s={d.status} />} <span className="hint">{d.id}</span></div>
          {(d.posts || []).map((p, n) => (
            <div key={n} style={{ borderTop: '1px solid var(--bd)', padding: '10px 0' }}>
              <div className="hint" style={{ margin: '0 0 6px' }}><Clock size={12} style={{ verticalAlign: -2 }} /> {dt(p.at)}</div>
              {p.parts.length ? <Onderdelen parts={p.parts} /> : <div style={{ whiteSpace: 'pre-line' }}>{p.raw}</div>}
            </div>
          ))}
        </>
      )}
      <div className="foot"><Btn v="p" onClick={() => close()}>Sluiten</Btn></div>
    </>
  );
}

function Berichten() {
  const [l, setL] = useState(null);
  const [fout, setFout] = useState('');
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('');
  useEffect(() => {
    api('health.messages', {}, { quiet: true }).then((x) => setL(x.messages)).catch((e) => { setFout(e.message || String(e)); setL([]); });
  }, []);
  const shown = useFilter(l || [], q, (m) => [m.title, m.id, ...m.services]).filter((m) => !cat || (cat === 'major' ? m.major : m.category === cat));
  if (!l) return <Loading text="Berichtencentrum ophalen..." />;
  if (fout) return <Msg kind="warn">{fout}</Msg>;
  const open = (m) => openModal((close) => (
    <>
      <h3>{m.title}</h3>
      <div style={{ marginBottom: 10 }}><Chip k={m.categoryKind}>{m.categoryText}</Chip>{m.major && <> <Chip k="r">Grote wijziging</Chip></>} <span className="hint">{m.id} · {m.services.join(', ')}</span></div>
      {m.actionBy && <Msg kind="warn">Actie nodig vóór {dt(m.actionBy)}</Msg>}
      <div style={{ whiteSpace: 'pre-line', maxHeight: '55vh', overflow: 'auto' }}>{m.text}</div>
      <div className="foot"><Btn v="p" onClick={() => close()}>Sluiten</Btn></div>
    </>
  ), { wide: true });
  return (
    <Card title={`${shown.length} bericht(en) (laatste 60 dagen)`} icon={Megaphone}>
      <div className="row" style={{ marginBottom: 10 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Zoek op titel, dienst of MC-nummer..." />
        <div className="n"><select value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">Alle berichten</option><option value="preventOrFixIssue">Actie nodig</option><option value="planForChange">Wijziging gepland</option>
          <option value="stayInformed">Ter info</option><option value="major">Grote wijzigingen</option></select></div>
      </div>
      <table>
        <thead><tr><th>Bericht</th><th>Soort</th><th>Diensten</th><th>Actie vóór</th><th>Bijgewerkt</th></tr></thead>
        <tbody>{shown.slice(0, 300).map((m) => (
          <tr key={m.id} className="click" onClick={() => open(m)}>
            <td><b>{m.title}</b><div className="hint" style={{ margin: 0 }}>{m.id}{m.major ? ' · grote wijziging' : ''}</div></td>
            <td><Chip k={m.categoryKind}>{m.categoryText}</Chip></td><td>{m.services.join(', ')}</td>
            <td>{m.actionBy ? dt(m.actionBy) : '-'}</td><td>{dt(m.updated)}</td></tr>))}
          {!shown.length && <tr><td colSpan={5} className="hint">Geen berichten gevonden.</td></tr>}
        </tbody>
      </table>
    </Card>
  );
}
