import { useEffect, useState } from 'react';
import { startTab } from '../store.jsx';
import { ArrowDownToLine, ArrowUpFromLine, Cable, Download, Plus, RefreshCw, Route, Search, Trash2, Workflow } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, openModal, toast } from '../overlays.jsx';
import { useApp } from '../store.jsx';
import { Btn, Card, Check, Chip, Field, Loading, Tabs, csv, dt } from '../ui.jsx';

export default function Exchange() {
  const { info } = useApp();
  const [tab, setTab] = useState(() => startTab('exchange', 'trace'));
  if (info.exo === false) return <><h2>Exchange</h2><Msg kind="err">Exchange Online is niet verbonden bij deze klant.</Msg></>;
  return (
    <>
      <h2>Exchange</h2>
      <p className="sub">Berichten traceren, e-mailstroomregels en connectors beheren.</p>
      <Tabs value={tab} onChange={setTab} tabs={[['trace', 'Message trace', Route], ['regels', 'Regels', Workflow], ['connectors', 'Connectors', Cable]]} />
      {tab === 'trace' ? <Trace /> : tab === 'regels' ? <Regels /> : <Connectors />}
    </>
  );
}

// ---------------- Message trace ----------------
const STATUS = { Delivered: ['Afgeleverd', 'g'], Failed: ['Mislukt', 'r'], FilteredAsSpam: ['Spam', 'o'], Quarantined: ['Quarantaine', 'o'],
  Pending: ['In behandeling', 'mu'], Expanded: ['Uitgebreid (groep)', 'mu'], GettingStatus: ['Status ophalen', 'mu'], Resolved: ['Omgeleid', 'mu'] };
const statusChip = (s) => { const x = STATUS[s] || [s, 'mu']; return <Chip k={x[1]}>{x[0]}</Chip>; };
const vandaag = (d = 0) => new Date(Date.now() - d * 86400000).toISOString().slice(0, 10);

function Trace() {
  const [f, setF] = useState({ sender: '', recipient: '', subject: '', status: '', start: vandaag(2), end: vandaag(0) });
  const [r, setR] = useState(null);
  const [bezig, setBezig] = useState(false);
  const z = (k) => (v) => setF({ ...f, [k]: v });
  const [meta, setMeta] = useState(null);
  const zoek = async () => {
    if (f.end < f.start) return toast('De einddatum moet na de begindatum liggen.', 'e');
    setBezig(true);
    const x = await act('trace.search', f);
    setBezig(false);
    if (x) { setR(x.messages); setMeta(x); }
  };
  const exporteer = () => csv(`message-trace-${f.start}-tot-${f.end}.csv`, [
    ['Ontvangen', 'Afzender', 'Ontvanger', 'Onderwerp', 'Status', 'Grootte (bytes)', 'Van IP', 'Naar IP', 'Message-ID', 'Trace-ID'],
    ...r.map((m) => [m.received, m.sender, m.recipient, m.subject, m.status, m.size, m.fromIp, m.toIp, m.messageId, m.traceId])]);
  useEffect(() => { zoek(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const detail = (m) => openModal((close) => <TraceDetail m={m} close={close} />, { wide: true });
  return (
    <>
      <Card>
        <div className="row">
          <Field label="Afzender" value={f.sender} onChange={z('sender')} placeholder="naam@domein.nl (meerdere: komma)" />
          <Field label="Ontvanger" value={f.recipient} onChange={z('recipient')} placeholder="naam@domein.nl" />
          <Field label="Onderwerp bevat" value={f.subject} onChange={z('subject')} />
        </div>
        <div className="row">
          <div><label className="f">Van</label><input type="date" value={f.start} min={vandaag(90)} max={vandaag(0)} onChange={(e) => z('start')(e.target.value)} /></div>
          <div><label className="f">Tot en met</label><input type="date" value={f.end} min={vandaag(90)} max={vandaag(0)} onChange={(e) => z('end')(e.target.value)} /></div>
          <div><label className="f">Status</label><select value={f.status} onChange={(e) => z('status')(e.target.value)}>
            <option value="">Alle</option>{Object.entries(STATUS).slice(0, 6).map(([k, v]) => <option key={k} value={k}>{v[0]}</option>)}</select></div>
          <div className="n"><Btn v="p" icon={Search} onClick={zoek} disabled={bezig}>Zoeken</Btn></div>
        </div>
        <div className="hint">Je kunt tot 90 dagen terugzoeken. Een langere periode dan 10 dagen wordt automatisch in delen opgevraagd.</div>
      </Card>
      {bezig ? <Loading text="Berichten zoeken..." /> : r && (
        <Card title={`${r.length} bericht(en)`} icon={Route}
          right={<Btn s icon={Download} onClick={exporteer}>Exporteren (CSV)</Btn>}>
          {meta && meta.truncated && <Msg kind="warn">Er zijn meer dan {r.length} berichten gevonden; verfijn de zoekopdracht om alles te zien.</Msg>}
          <table>
            <thead><tr><th>Ontvangen</th><th>Afzender</th><th>Ontvanger</th><th>Onderwerp</th><th>Status</th></tr></thead>
            <tbody>{r.slice(0, 500).map((m, i) => (
              <tr key={i} className="click" onClick={() => detail(m)}>
                <td style={{ whiteSpace: 'nowrap' }}>{dt(m.received)}</td><td>{m.sender}</td><td>{m.recipient}</td><td>{m.subject}</td><td>{statusChip(m.status)}</td>
              </tr>))}
              {!r.length && <tr><td colSpan={5} className="hint">Geen berichten gevonden.</td></tr>}
            </tbody>
          </table>
          {r.length > 500 && <div className="hint">Toont 500 van {r.length}. De CSV-export bevat alle {r.length} berichten.</div>}
        </Card>
      )}
    </>
  );
}

function TraceDetail({ m, close }) {
  const [d, setD] = useState(null);
  useEffect(() => { act('trace.detail', { traceId: m.traceId, recipient: m.recipient }).then((x) => setD(x || { events: [] })); }, [m]);
  return (
    <>
      <h3>{m.subject || '(geen onderwerp)'}</h3>
      <div className="kv" style={{ marginBottom: 12 }}>
        <div><label>Afzender</label><div>{m.sender}</div></div><div><label>Ontvanger</label><div>{m.recipient}</div></div>
        <div><label>Ontvangen</label><div>{dt(m.received)}</div></div><div><label>Status</label><div>{statusChip(m.status)}</div></div>
        <div><label>Grootte</label><div>{Math.round((m.size || 0) / 1024)} kB</div></div><div><label>Van IP</label><div>{m.fromIp || '-'}</div></div>
      </div>
      <div className="hint" style={{ wordBreak: 'break-all' }}>Message-ID: {m.messageId}</div>
      {!d ? <Loading /> : (
        <table style={{ marginTop: 10 }}>
          <thead><tr><th>Tijd</th><th>Gebeurtenis</th><th>Details</th></tr></thead>
          <tbody>{d.events.map((e, i) => <tr key={i}><td style={{ whiteSpace: 'nowrap' }}>{dt(e.date)}</td><td><b>{e.event}</b>{e.action && <div className="hint" style={{ margin: 0 }}>{e.action}</div>}</td><td>{e.detail}</td></tr>)}
            {!d.events.length && <tr><td colSpan={3} className="hint">Geen details beschikbaar.</td></tr>}</tbody>
        </table>
      )}
      <div className="foot"><Btn v="p" onClick={() => close()}>Sluiten</Btn></div>
    </>
  );
}

// ---------------- Regels ----------------
function Regels() {
  const [d, setD] = useState(null);
  const laad = async () => { const x = await act('rules.list', {}); setD(x ? x.rules : []); };
  useEffect(() => { laad(); }, []);
  if (!d) return <Loading text="Regels ophalen..." />;
  const nieuw = async () => {
    const r = await openModal((close) => <NieuweRegel close={close} />, { wide: true });
    if (r && await act('rules.create', r, { msg: 'Regel aanmaken...' })) laad();
  };
  return (
    <Card title={`E-mailstroomregels (${d.length})`} icon={Workflow}
      right={<div className="btns"><Btn s v="p" icon={Plus} onClick={nieuw}>Nieuwe regel</Btn><Btn s icon={RefreshCw} onClick={laad}>Vernieuwen</Btn></div>}>
      <table>
        <thead><tr><th>Prio</th><th>Naam en beschrijving</th><th>Status</th><th /></tr></thead>
        <tbody>{d.map((r) => (
          <tr key={r.id}>
            <td style={{ width: 70 }}><input type="number" min={0} defaultValue={r.priority} style={{ width: 60 }}
              onBlur={(e) => { if (String(e.target.value) !== String(r.priority)) act('rules.set', { id: r.id, priority: e.target.value }).then(laad); }} /></td>
            <td className="sk"><b>{r.name}</b><small className="pre">{r.desc}</small></td>
            <td>{r.state === 'Enabled' ? <Chip k="g">Aan</Chip> : <Chip k="mu">Uit</Chip>}{r.mode && r.mode !== 'Enforce' && <> <Chip k="o">{r.mode === 'Audit' ? 'Test' : r.mode}</Chip></>}</td>
            <td className="r"><div className="btns" style={{ justifyContent: 'flex-end' }}>
              <Btn s onClick={async () => { if (await act('rules.set', { id: r.id, enabled: r.state !== 'Enabled' })) laad(); }}>{r.state === 'Enabled' ? 'Uitzetten' : 'Aanzetten'}</Btn>
              <Btn s v="dl" icon={Trash2} onClick={async () => { if (await ask(`Regel '${r.name}' verwijderen?`, 'Verwijderen', true) && await act('rules.delete', { id: r.id })) laad(); }} />
            </div></td>
          </tr>))}
          {!d.length && <tr><td colSpan={4} className="hint">Geen regels.</td></tr>}
        </tbody>
      </table>
    </Card>
  );
}

function NieuweRegel({ close }) {
  const [f, setF] = useState({ name: '', enabled: true, mode: 'Enforce', fromScope: '', sentToScope: '', from: '', sentTo: '', senderDomain: '', recipientDomain: '',
    subjectContains: '', subjectOrBodyContains: '', attachmentExt: '', redirectTo: '', bccTo: '', addTo: '', prependSubject: '', setScl: '', reject: '',
    disclaimer: '', disclaimerLocation: 'Append', delete: false, stop: false, priority: '', comments: '' });
  const z = (k) => (v) => setF({ ...f, [k]: v });
  return (
    <>
      <h3>Nieuwe e-mailstroomregel</h3>
      <Field label="Naam *" value={f.name} onChange={z('name')} autoFocus />
      <h4 style={{ margin: '14px 0 0', color: 'var(--navy)' }}>Wanneer (alle ingevulde voorwaarden moeten kloppen)</h4>
      <div className="row">
        <div><label className="f">Afzender is</label><select value={f.fromScope} onChange={(e) => z('fromScope')(e.target.value)}><option value="">Iedereen</option><option value="InOrganization">Binnen de organisatie</option><option value="NotInOrganization">Buiten de organisatie</option></select></div>
        <div><label className="f">Ontvanger is</label><select value={f.sentToScope} onChange={(e) => z('sentToScope')(e.target.value)}><option value="">Iedereen</option><option value="InOrganization">Binnen de organisatie</option><option value="NotInOrganization">Buiten de organisatie</option></select></div>
      </div>
      <div className="row"><Field label="Van (adressen)" value={f.from} onChange={z('from')} placeholder="komma-gescheiden" /><Field label="Aan (adressen)" value={f.sentTo} onChange={z('sentTo')} /></div>
      <div className="row"><Field label="Afzenderdomein" value={f.senderDomain} onChange={z('senderDomain')} /><Field label="Ontvangerdomein" value={f.recipientDomain} onChange={z('recipientDomain')} /></div>
      <div className="row"><Field label="Onderwerp bevat" value={f.subjectContains} onChange={z('subjectContains')} /><Field label="Onderwerp of tekst bevat" value={f.subjectOrBodyContains} onChange={z('subjectOrBodyContains')} /></div>
      <Field label="Bijlage-extensie" value={f.attachmentExt} onChange={z('attachmentExt')} placeholder="bijv. exe, js" />
      <h4 style={{ margin: '14px 0 0', color: 'var(--navy)' }}>Doe dan</h4>
      <div className="row"><Field label="Omleiden naar" value={f.redirectTo} onChange={z('redirectTo')} /><Field label="Bcc naar" value={f.bccTo} onChange={z('bccTo')} /><Field label="Ontvanger toevoegen" value={f.addTo} onChange={z('addTo')} /></div>
      <div className="row"><Field label="Tekst voor onderwerp" value={f.prependSubject} onChange={z('prependSubject')} placeholder="[EXTERN] " />
        <div><label className="f">Spamscore (SCL)</label><select value={f.setScl} onChange={(e) => z('setScl')(e.target.value)}><option value="">Niet wijzigen</option><option value="-1">-1 (spamfilter overslaan)</option>{[0, 1, 5, 6, 9].map((n) => <option key={n}>{n}</option>)}</select></div></div>
      <Field label="Weigeren met tekst" value={f.reject} onChange={z('reject')} />
      <label className="f">Disclaimer / handtekening (HTML mag)</label>
      <textarea rows={3} value={f.disclaimer} onChange={(e) => z('disclaimer')(e.target.value)} />
      {f.disclaimer && <select value={f.disclaimerLocation} onChange={(e) => z('disclaimerLocation')(e.target.value)} style={{ marginTop: 6 }}><option value="Append">Onderaan</option><option value="Prepend">Bovenaan</option></select>}
      <Check checked={f.delete} onChange={z('delete')}>Bericht verwijderen zonder melding</Check>
      <Check checked={f.stop} onChange={z('stop')}>Daarna geen andere regels meer verwerken</Check>
      <div className="row">
        <div><label className="f">Modus</label><select value={f.mode} onChange={(e) => z('mode')(e.target.value)}><option value="Enforce">Afdwingen</option><option value="Audit">Testen (zonder actie)</option><option value="AuditAndNotify">Testen met beleidstips</option></select></div>
        <Field label="Prioriteit (leeg = laatst)" value={f.priority} onChange={z('priority')} type="number" />
      </div>
      <Check checked={f.enabled} onChange={z('enabled')}>Regel direct inschakelen</Check>
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" disabled={!f.name.trim()} onClick={() => close(f)}>Aanmaken</Btn></div>
    </>
  );
}

// ---------------- Connectors ----------------
function Connectors() {
  const [d, setD] = useState(null);
  const laad = async () => { const x = await act('connectors.list', {}); setD(x ? x.connectors : []); };
  useEffect(() => { laad(); }, []);
  if (!d) return <Loading text="Connectors ophalen..." />;
  const nieuw = async (richting) => {
    const r = await openModal((close) => <NieuweConnector close={close} richting={richting} />, { wide: true });
    if (r && await act('connectors.create', r, { msg: 'Connector aanmaken...' })) laad();
  };
  return (
    <Card title={`Connectors (${d.length})`} icon={Cable}
      right={<div className="btns"><Btn s v="p" icon={ArrowDownToLine} onClick={() => nieuw('Inkomend')}>Inkomend</Btn><Btn s v="p" icon={ArrowUpFromLine} onClick={() => nieuw('Uitgaand')}>Uitgaand</Btn><Btn s icon={RefreshCw} onClick={laad} /></div>}>
      <table>
        <thead><tr><th>Naam</th><th>Richting</th><th>Domeinen / IP</th><th>Status</th><th /></tr></thead>
        <tbody>{d.map((x) => (
          <tr key={x.id}>
            <td className="sk"><b>{x.name}</b><small>{x.comment}</small></td>
            <td>{x.dir} <Chip k="mu">{x.type === 'OnPremises' ? 'Eigen server' : 'Partner'}</Chip></td>
            <td style={{ fontSize: 12.5 }}>{x.domains}{x.ips && <div className="hint" style={{ margin: 0 }}>IP: {x.ips}</div>}{x.smarthosts && <div className="hint" style={{ margin: 0 }}>Smarthost: {x.smarthosts}</div>}</td>
            <td>{x.enabled ? <Chip k="g">Aan</Chip> : <Chip k="mu">Uit</Chip>}</td>
            <td className="r"><div className="btns" style={{ justifyContent: 'flex-end' }}>
              <Btn s onClick={async () => { if (await act('connectors.set', { id: x.id, dir: x.dir, enabled: !x.enabled })) laad(); }}>{x.enabled ? 'Uitzetten' : 'Aanzetten'}</Btn>
              <Btn s v="dl" icon={Trash2} onClick={async () => { if (await ask(`Connector '${x.name}' verwijderen?`, 'Verwijderen', true) && await act('connectors.delete', { id: x.id, dir: x.dir })) laad(); }} />
            </div></td>
          </tr>))}
          {!d.length && <tr><td colSpan={5} className="hint">Geen connectors.</td></tr>}
        </tbody>
      </table>
    </Card>
  );
}

function NieuweConnector({ close, richting }) {
  const [f, setF] = useState({ dir: richting, name: '', type: 'Partner', domains: '', ips: '', restrictIps: false, requireTls: true, smarthosts: '', tls: '', comment: '', enabled: true });
  const z = (k) => (v) => setF({ ...f, [k]: v });
  const uit = f.dir === 'Uitgaand';
  return (
    <>
      <h3>Nieuwe {uit ? 'uitgaande' : 'inkomende'} connector</h3>
      <Field label="Naam *" value={f.name} onChange={z('name')} autoFocus />
      <label className="f">{uit ? 'Naar' : 'Van'}</label>
      <select value={f.type} onChange={(e) => z('type')(e.target.value)}><option value="Partner">Partnerorganisatie (bijv. scandienst, mailfilter)</option><option value="OnPremises">Eigen mailserver</option></select>
      <Field label={uit ? 'Ontvangerdomeinen (leeg = alle, * mag)' : 'Afzenderdomeinen (* = alle)'} value={f.domains} onChange={z('domains')} placeholder="domein.nl, *.voorbeeld.nl" />
      {uit ? (
        <>
          <Field label="Smarthosts (leeg = via MX-record)" value={f.smarthosts} onChange={z('smarthosts')} placeholder="mail.provider.nl" />
          <label className="f">TLS</label>
          <select value={f.tls} onChange={(e) => z('tls')(e.target.value)}><option value="">Standaard (opportunistisch)</option><option value="EncryptionOnly">Altijd versleutelen</option><option value="CertificateValidation">Versleutelen + certificaat controleren</option><option value="DomainValidation">Versleutelen + domein controleren</option></select>
        </>
      ) : (
        <>
          <Field label="Afzender-IP-adressen" value={f.ips} onChange={z('ips')} placeholder="1.2.3.4, 5.6.7.0/24" />
          <Check checked={f.restrictIps} onChange={z('restrictIps')}>Mail van deze domeinen alleen accepteren vanaf deze IP-adressen</Check>
          <Check checked={f.requireTls} onChange={z('requireTls')}>TLS verplicht</Check>
        </>
      )}
      <Field label="Opmerking" value={f.comment} onChange={z('comment')} />
      <Check checked={f.enabled} onChange={z('enabled')}>Direct inschakelen</Check>
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" disabled={!f.name.trim()} onClick={() => close(f)}>Aanmaken</Btn></div>
    </>
  );
}
