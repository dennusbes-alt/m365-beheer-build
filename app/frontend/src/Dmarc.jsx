// E-mailbeveiliging (DMARC via EasyDMARC): alle klanten en domeinen in één overzicht, problemen in gewone taal,
// falende afzenders per domein en een PDF-rapportage per klant.
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, FileText, KeyRound, MailCheck, RefreshCw, Settings, Users } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, toast } from './overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox, csv } from './ui.jsx';

const ST = { ok: ['In orde', 'g'], warn: ['Aandacht', 'o'], err: ['Actie nodig', 'r'] };
const REC = { valid: ['In orde', 'g'], warning: ['Waarschuwing', 'o'], 'no-record': ['Ontbreekt', 'r'], unknown: ['Onbekend', 'mu'] };
const POL = { reject: 'g', quarantine: 'g', none: 'o', missing: 'r' };
const Tegel = ({ label, n, kleur, sub, on, onClick }) => (
  <div className="card tegelklik" onClick={onClick} style={on ? { borderColor: 'var(--cy)', boxShadow: '0 0 0 2px rgba(0,174,239,.25)' } : undefined}>
    <div className="hint" style={{ margin: 0 }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 900, color: kleur ? `var(--${kleur})` : 'var(--navy)' }}>{n}</div>
    {sub && <div className="hint" style={{ margin: 0 }}>{sub}</div>}
  </div>
);
const nl = (n) => (n || 0).toLocaleString('nl-NL');
const pc = (v) => `${String(v).replace('.', ',')}%`;
// Geslaagd/gefaald als één gesplitste balk met percentages en aantallen.
function Verdeling({ passed, failed, pct, breed }) {
  const tot = (passed || 0) + (failed || 0);
  if (!tot || pct == null) {
    return (
      <span className="hint" style={{ margin: 0 }} title="EasyDMARC heeft in deze periode geen DMARC-rapporten ontvangen voor deze domeinen. Meestal staat in het DMARC-record (rua=mailto:...) nog niet het rapportadres van EasyDMARC, of er wordt (bijna) niet gemaild vanaf het domein.">
        geen rapporten ontvangen <small>(controleer rua in het DMARC-record)</small></span>);
  }
  const fout = Math.round((100 - pct) * 10) / 10;
  return (
    <div style={{ minWidth: breed ? 320 : 220 }}>
      <div style={{ display: 'flex', height: breed ? 14 : 10, borderRadius: 7, overflow: 'hidden', background: 'var(--bg)' }}>
        <i style={{ width: `${pct}%`, background: 'var(--gr)' }} title={`${nl(passed)} geslaagd`} />
        <i style={{ width: `${fout}%`, background: 'var(--rd)' }} title={`${nl(failed)} gefaald`} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12.5, marginTop: 3 }}>
        <span style={{ color: 'var(--gr)' }}><b>{pc(pct)}</b> geslaagd <span className="hint">({nl(passed)})</span></span>
        <span style={{ color: fout ? 'var(--rd)' : 'var(--mu)' }}><b>{pc(fout)}</b> gefaald <span className="hint">({nl(failed)})</span></span>
      </div>
    </div>);
}
const balk = (v) => (v == null ? <span className="hint">-</span> : (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
    <span className="bar" style={{ width: 70, minWidth: 70 }}><i style={{ width: `${v}%`, background: v >= 95 ? 'var(--gr)' : v >= 80 ? 'var(--or)' : 'var(--rd)' }} /></span>
    <b style={{ fontSize: 12.5 }}>{v}%</b></span>));

export default function Dmarc() {
  const [d, setD] = useState(null);
  const [dagen, setDagen] = useState(30);
  const [filter, setFilter] = useState('alle');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState({});
  const [instellen, setInstellen] = useState(false);
  const timer = useRef(null);
  const laad = async (fresh, dg = dagen) => {
    clearTimeout(timer.current);
    try {
      const x = await api('dm.overzicht', { fresh: !!fresh, days: dg }, { quiet: true });
      setD(x);
      if (x.busy) timer.current = setTimeout(() => laad(false, dg), 2000);
    } catch (e) { toast(e.message, 'e'); setD((o) => o || { configured: false }); }
  };
  useEffect(() => { laad(false); return () => clearTimeout(timer.current); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const orgs = useMemo(() => (d && d.orgs ? d.orgs.filter((o) => (filter === 'err' ? o.status === 'err' : filter === 'warn' ? o.status !== 'ok' : filter === 'ok' ? o.status === 'ok' : true))
    .filter((o) => !q || `${o.name} ${o.domains.map((x) => x.domain).join(' ')}`.toLowerCase().includes(q.toLowerCase())) : []), [d, filter, q]);

  if (!d) return <div className="klanten"><Loading text="E-mailbeveiliging openen..." /></div>;
  if (!d.configured || instellen) {
    if (!d.admin) return <div className="klanten"><Msg kind="info">E-mailbeveiliging is nog niet gekoppeld aan EasyDMARC. De app-beheerder stelt dit één keer in voor iedereen.</Msg></div>;
    return <div className="klanten"><Koppeling ingesteld={d.configured} onKlaar={() => { setInstellen(false); laad(true); }} onTerug={d.configured ? () => setInstellen(false) : null} /></div>;
  }
  const alle = d.orgs || [];
  const doms = alle.flatMap((o) => o.domains);
  const tel = (k) => alle.filter((o) => o.status === k).length;
  const totVol = alle.reduce((a, o) => a + (o.volume || 0), 0);
  const totOk = alle.reduce((a, o) => a + (o.passed || 0), 0);
  const totFout = alle.reduce((a, o) => a + (o.failed || 0), 0);
  const gemComp = totOk + totFout ? Math.round(totOk / (totOk + totFout) * 1000) / 10 : null;
  const gemFout = gemComp == null ? null : Math.round((100 - gemComp) * 10) / 10;
  const rapport = async (o) => { await act('dm.rapport', { orgId: o.id }, { msg: `Rapport voor ${o.name} opstellen...` }); };
  const export_ = () => csv(`dmarc-overzicht-${new Date().toISOString().slice(0, 10)}.csv`, [
    ['Klant', 'Domein', 'Status', 'Beleid', 'Geslaagd %', 'Gefaald %', 'Geslaagd (berichten)', 'Gefaald (berichten)', 'Berichten', 'SPF', 'DKIM', 'DMARC', 'SPF geslaagd %', 'DKIM geslaagd %', 'Problemen'],
    ...alle.flatMap((o) => o.domains.map((x) => [o.name, x.domain, ST[x.status][0], x.policyText, x.compliance ?? '', x.failPct ?? '', x.passed || 0, x.failed || 0, x.volume, x.spf, x.dkim, x.dmarc, x.spfPass ?? '', x.dkimPass ?? '',
      x.problems.map((p) => p.text).join(' | ')]))]);

  return (
    <div className="klanten breed">
      <div className="headrow" style={{ marginBottom: 6 }}>
        <div className="m"><h2 style={{ margin: 0 }}>E-mailbeveiliging (DMARC)</h2>
          <div className="hint" style={{ margin: 0 }}>{d.busy ? `Bezig met ophalen... ${d.done} van ${d.total || '?'} klanten` : `Bijgewerkt om ${d.at}`} · bron: EasyDMARC · laatste {d.days} dagen</div></div>
        <div className="btns">
          <select value={dagen} onChange={(e) => { setDagen(+e.target.value); laad(true, +e.target.value); }} style={{ width: 'auto' }}>
            {[7, 30, 90].map((n) => <option key={n} value={n}>Laatste {n} dagen</option>)}</select>
          <Btn s onClick={export_}>CSV</Btn>
          {d.admin && <Btn s icon={Settings} onClick={() => setInstellen(true)}>Koppeling</Btn>}
          <Btn s icon={RefreshCw} disabled={d.busy} onClick={() => laad(true)}>{d.busy ? 'Bezig...' : 'Vernieuwen'}</Btn>
        </div>
      </div>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      <div className="tegels" style={{ marginTop: 8 }}>
        <Tegel label="Klanten" n={alle.length} sub={`${doms.length} domeinen`} on={filter === 'alle'} onClick={() => setFilter('alle')} />
        <Tegel label="Actie nodig" n={tel('err')} kleur={tel('err') ? 'rd' : 'gr'} sub="geen DMARC/SPF of veel falende mail" on={filter === 'err'} onClick={() => setFilter(filter === 'err' ? 'alle' : 'err')} />
        <Tegel label="Aandacht" n={tel('warn')} kleur={tel('warn') ? 'or' : 'gr'} sub="bijv. DMARC nog op monitoren" on={filter === 'warn'} onClick={() => setFilter(filter === 'warn' ? 'alle' : 'warn')} />
        <Tegel label="In orde" n={tel('ok')} kleur="gr" on={filter === 'ok'} onClick={() => setFilter(filter === 'ok' ? 'alle' : 'ok')} />
        <Tegel label="Geslaagd (alle mail)" n={gemComp == null ? '-' : pc(gemComp)} kleur="gr" sub={`${nl(totOk)} van ${nl(totVol)} berichten`} />
        <Tegel label="Gefaald (alle mail)" n={gemFout == null ? '-' : pc(gemFout)} kleur={gemFout == null ? null : gemFout <= 5 ? 'gr' : gemFout <= 20 ? 'or' : 'rd'} sub={`${nl(totFout)} berichten haalden DMARC niet`} />
      </div>

      <Card title={`Klanten (${orgs.length})`} icon={MailCheck} right={<SearchBox value={q} onChange={setQ} placeholder="Zoek klant of domein..." />}>
        {d.busy && !alle.length && <Loading text="Klanten en domeinen ophalen bij EasyDMARC..." />}
        <table className="vastkop">
          <thead><tr><th>Klant</th><th>Status</th><th>Domeinen</th><th>Geslaagd / gefaald (DMARC)</th><th className="r">Berichten</th><th /></tr></thead>
          <tbody>{orgs.map((o) => {
            const isOpen = open[o.id];
            return (
              <Fragment key={o.id}>
                <tr>
                  <td className="tegelklik" onClick={() => setOpen((x) => ({ ...x, [o.id]: !x[o.id] }))}>{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} <b>{o.name}</b>
                    {o.error && <><br /><small style={{ color: 'var(--rd)' }}>{o.error}</small></>}</td>
                  <td><Chip k={ST[o.status][1]}>{ST[o.status][0]}</Chip></td>
                  <td><small>{o.counts.ok > 0 && <Chip k="g">{o.counts.ok} in orde</Chip>}{o.counts.warn > 0 && <Chip k="o">{o.counts.warn} aandacht</Chip>}{o.counts.err > 0 && <Chip k="r">{o.counts.err} actie</Chip>}</small></td>
                  <td><Verdeling passed={o.passed} failed={o.failed} pct={o.compliance} /></td>
                  <td className="r"><small>{(o.volume || 0).toLocaleString('nl-NL')}</small></td>
                  <td><Btn s icon={FileText} onClick={() => rapport(o)}>Rapport (PDF)</Btn></td>
                </tr>
                {isOpen && (
                  <tr><td colSpan={6} style={{ background: 'var(--bg)' }}>
                    {o.domains.map((x) => <Domein key={x.domain} x={x} dagen={d.days} />)}
                    {!o.domains.length && <div className="hint">Geen domeinen bij deze klant in EasyDMARC.</div>}
                  </td></tr>)}
              </Fragment>);
          })}</tbody>
        </table>
        <div className="hint"><b>Geslaagd</b> = mail die de DMARC-controle haalt (SPF of DKIM klopt en hoort bij het afzenderdomein). <b>Gefaald</b> = mail uit naam van het domein die de controle niet haalt: een eigen dienst die niet goed is ingesteld, of iemand die het domein misbruikt (spoofing). Klik een klant open en kies "Wie faalt er?" om te zien welke afzender het is. Bron: DMARC-rapporten van ontvangende mailservers via EasyDMARC.</div>
      </Card>
    </div>
  );
}

function Domein({ x, dagen }) {
  const [afz, setAfz] = useState(null);
  const [laden, setLaden] = useState(false);
  const toon = async () => {
    setLaden(true);
    try { setAfz(await api('dm.afzenders', { domain: x.domain, days: dagen }, { quiet: true })); } catch (e) { setAfz({ error: e.message, senders: [] }); }
    setLaden(false);
  };
  return (
    <div className="card" style={{ margin: '8px 0', boxShadow: 'none' }}>
      <div className="headrow">
        <div className="m"><h3 style={{ margin: 0 }}>{x.domain} <Chip k={ST[x.status][1]}>{ST[x.status][0]}</Chip>{x.type === 'parked' && <Chip k="mu">geparkeerd</Chip>}</h3>
          <div className="btns" style={{ marginTop: 6 }}>
            <Chip k={POL[x.policy] || 'mu'}>DMARC: {x.policyText}</Chip>
            {['spf', 'dkim'].map((k) => <Chip key={k} k={(REC[x[k]] || ['', 'mu'])[1]}>{k.toUpperCase()}: {(REC[x[k]] || [x[k]])[0]}</Chip>)}
          </div>
          {x.volume > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'flex-start', marginTop: 10 }}>
              <div><div className="hint" style={{ margin: '0 0 3px' }}>DMARC ({nl(x.volume)} berichten)</div><Verdeling passed={x.passed} failed={x.failed} pct={x.compliance} breed /></div>
              <div><div className="hint" style={{ margin: '0 0 3px' }}>SPF geslaagd</div>{balk(x.spfPass)}</div>
              <div><div className="hint" style={{ margin: '0 0 3px' }}>DKIM geslaagd</div>{balk(x.dkimPass)}</div>
            </div>)}
        </div>
        {x.volume > 0 && (x.compliance ?? 100) < 100 && !afz && <Btn s icon={Users} onClick={toon} disabled={laden}>{laden ? 'Ophalen...' : 'Wie faalt er?'}</Btn>}
      </div>
      {x.problems.map((p, i) => (
        <div key={i} style={{ display: 'flex', gap: 6, fontSize: 13, marginTop: 6, color: p.level === 'err' ? 'var(--rd)' : p.level === 'warn' ? 'var(--or)' : 'var(--mu)' }}>
          <AlertTriangle size={14} style={{ flex: 'none', marginTop: 2 }} /><span>{p.text}</span></div>))}
      {!x.problems.length && <div className="hint" style={{ marginBottom: 0 }}>Alles in orde.</div>}
      {afz && (
        <div style={{ marginTop: 10 }}>
          {afz.error && <Msg kind="warn">{afz.error}</Msg>}
          {!afz.error && !afz.senders.length && <Msg kind="ok">Geen falende afzenders gevonden in deze periode.</Msg>}
          {afz.senders.length > 0 && (
            <table>
              <thead><tr><th>Afzender (dienst/server)</th><th className="r">Berichten</th><th>Waarom faalt het</th><th>Details</th></tr></thead>
              <tbody>{afz.senders.map((s) => (
                <tr key={s.name}><td><b>{s.name}</b></td><td className="r">{s.count.toLocaleString('nl-NL')}</td><td><small>{s.reason}</small></td>
                  <td><small className="hint">{[...s.ips, ...s.countries].join(', ')}{s.from.length ? ` · ${s.from.join(', ')}` : ''}</small></td></tr>))}</tbody>
            </table>)}
          {afz.senders.length > 0 && <div className="hint">{afz.senders[0].advice}</div>}
        </div>)}
    </div>
  );
}

function Koppeling({ ingesteld, onKlaar, onTerug }) {
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const opslaan = async () => {
    if (!a || !b) return toast('Vul beide velden in.', 'e');
    if (await act('dm.keys.set', { a, b }, { msg: 'Verbinding met EasyDMARC testen...' })) onKlaar();
  };
  return (
    <>
      <div className="headrow"><h2 style={{ margin: 0 }}>E-mailbeveiliging: koppeling</h2>{onTerug && <Btn s onClick={onTerug}>Terug naar overzicht</Btn>}</div>
      <Card title="EasyDMARC" icon={KeyRound} right={ingesteld ? <Chip k="g">gekoppeld</Chip> : <Chip k="mu">niet gekoppeld</Chip>}>
        <div className="hint" style={{ marginTop: 0 }}>Maak in EasyDMARC (Account Console &gt; API Client management) een API-client aan en vul Client-ID en secret in. Ze worden eerst getest en daarna gedeeld met alle Justdata-collega's (alleen jij kunt ze wijzigen).</div>
        <div className="row">
          <div><label className="f">Client-ID</label><input type="password" autoComplete="off" value={a} onChange={(e) => setA(e.target.value)} placeholder={ingesteld ? '(ongewijzigd)' : ''} /></div>
          <div><label className="f">Client secret</label><input type="password" autoComplete="off" value={b} onChange={(e) => setB(e.target.value)} /></div>
        </div>
        <div className="btns" style={{ marginTop: 10 }}><Btn v="p" onClick={opslaan}>{ingesteld ? 'Vervangen' : 'Testen en koppelen'}</Btn>
          {ingesteld && <Btn v="dl" onClick={async () => { if (await ask('EasyDMARC-koppeling verwijderen voor iedereen?', 'Verwijderen', true)) { await act('dm.keys.delete', {}); onKlaar(); } }}>Verwijderen</Btn>}</div>
      </Card>
    </>
  );
}

