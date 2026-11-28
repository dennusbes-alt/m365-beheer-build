// Microsoft Secure Score: score, verloop en acties gesorteerd op wat ze opleveren, met de negatieve impact per actie.
// Een deel van de acties kan de app direct toepassen (Exchange-/Entra-instellingen).
import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, ExternalLink, RefreshCw, ShieldCheck, Wand, Zap } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask } from '../overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox, Tabs, csv, datum, useFilter } from '../ui.jsx';

const IMPACT = { Low: ['Laag', 'g'], Moderate: ['Gemiddeld', 'o'], High: ['Hoog', 'r'] };
const STATUS = { Ignored: 'Genegeerd', ThirdParty: 'Opgelost via derde partij', Reviewed: 'Beoordeeld', Default: '' };
const Tegel = ({ label, n, kleur, sub }) => (
  <div className="card"><div className="hint" style={{ margin: 0 }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 900, color: kleur ? `var(--${kleur})` : 'var(--navy)' }}>{n}</div>
    {sub && <div className="hint" style={{ margin: 0 }}>{sub}</div>}</div>
);

function Verloop({ punten }) {
  if (punten.length < 2) return null;
  const w = 260, h = 54, min = Math.min(...punten.map((p) => p.pct)) - 2, max = Math.max(...punten.map((p) => p.pct)) + 2;
  const xy = punten.map((p, i) => [i / (punten.length - 1) * w, h - (p.pct - min) / (max - min || 1) * h]);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h + 4}`} preserveAspectRatio="none" style={{ display: 'block', height: 58 }} aria-label="Verloop Secure Score">
      <polyline points={xy.map((p) => p.join(',')).join(' ')} fill="none" stroke="var(--hd)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <circle cx={xy[xy.length - 1][0]} cy={xy[xy.length - 1][1]} r="3" fill="var(--cy)" />
    </svg>
  );
}

export default function SecureScore() {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [filter, setFilter] = useState('open');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState({});
  const [kies, setKies] = useState([]);
  const laad = async (fresh) => {
    setFout('');
    try { setD(await api('ss.list', { fresh }, { quiet: true })); } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { laad(false); }, []);

  const lijst = useMemo(() => {
    if (!d) return [];
    return d.actions.filter((a) => (filter === 'open' ? !a.done && a.state === 'Default' : filter === 'fix' ? !a.done && a.fix && a.fix.possible
      : filter === 'done' ? a.done : filter === 'ignored' ? !a.done && a.state !== 'Default' : true));
  }, [d, filter]);
  const shown = useFilter(lijst, q, (a) => [a.title, a.category, a.service, a.id]);

  if (fout && !d) return <><h2>Secure Score</h2><Msg kind="warn">{fout}</Msg></>;
  if (!d) return <><h2>Secure Score</h2><Loading text="Secure Score ophalen..." /></>;

  const openActies = d.actions.filter((a) => !a.done);
  const winstFix = openActies.filter((a) => a.fix && a.fix.possible && a.fix.applied !== true).reduce((s, a) => s + a.gainPct, 0);
  const vgl = d.compare.find((c) => c.type === 'TotalSeats') || d.compare[0];

  const toepassen = async (acties) => {
    const tekst = acties.map((a) => `• ${a.title} (+${a.gainPct.toFixed(1)}%)\n  Wat verandert: ${a.fix.what}\n  Negatieve impact: ${a.fix.impact}`).join('\n\n');
    if (!await ask(`${acties.length === 1 ? 'Deze aanpassing' : `Deze ${acties.length} aanpassingen`} direct doorvoeren bij de klant?\n\n${tekst}\n\nMicrosoft werkt de Secure Score binnen 24-48 uur bij.`,
      'Toepassen', true, 'Secure Score verhogen')) return;
    for (const a of acties) await act('ss.apply', { id: a.id }, { msg: `${a.title} toepassen...` });
    setKies([]);
    laad(true);
  };
  const portaal = (url) => act('open.url', { url }, { nobusy: true });
  const export_ = () => csv('secure-score-acties.csv', [['Actie', 'Categorie', 'Punten', 'Max', 'Winst %', 'Impact gebruikers', 'Werk', 'Direct toe te passen', 'Negatieve impact'],
    ...d.actions.map((a) => [a.title, a.category, a.score, a.max, a.gainPct, IMPACT[a.userImpact]?.[0] || a.userImpact, a.cost, a.fix ? 'Ja' : 'Nee',
      a.fix ? a.fix.impact : (a.impactNl + (a.remediationImpact ? ' ' + a.remediationImpact : ''))])]);

  return (
    <>
      <h2>Secure Score</h2>
      <p className="sub">De beveiligingsscore van Microsoft voor deze klant. Acties staan gesorteerd op wat ze opleveren (hoogste percentage bovenaan). Bij elke actie staat wat er verandert en wat de negatieve impact voor gebruikers is.</p>
      <div className="tegels" style={{ marginTop: 0 }}>
        <Tegel label="Secure Score" n={`${d.pct}%`} kleur={d.pct >= 70 ? 'gr' : d.pct >= 45 ? 'or' : 'rd'} sub={`${d.current} van ${d.max} punten · ${datum(d.date)}`} />
        <Tegel label="Te winnen met open acties" n={`+${openActies.reduce((s, a) => s + a.gainPct, 0).toFixed(1)}%`} sub={`${openActies.length} acties`} />
        <Tegel label="Direct toe te passen door de app" n={`+${winstFix.toFixed(1)}%`} kleur="hd" sub={`${openActies.filter((a) => a.fix && a.fix.possible && a.fix.applied !== true).length} acties`} />
        <div className="card"><div className="hint" style={{ margin: 0 }}>Verloop (30 dagen){vgl ? ` · vergelijkbare organisaties ${vgl.pct}%` : ''}</div><Verloop punten={d.history} /></div>
      </div>
      {!d.exo && <Msg kind="warn">Exchange Online is niet verbonden: acties voor e-mail kunnen niet direct worden toegepast.</Msg>}

      <Card title="Acties" icon={ShieldCheck} right={<div className="btns">
        {kies.length > 0 && <Btn s v="p" icon={Zap} onClick={() => toepassen(d.actions.filter((a) => kies.includes(a.id)))}>{kies.length} geselecteerd toepassen</Btn>}
        <Btn s onClick={export_}>CSV</Btn>
        <Btn s icon={ExternalLink} onClick={() => portaal(d.portal)}>Microsoft Defender</Btn>
        <Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn></div>}>
        <Tabs value={filter} onChange={setFilter} tabs={[['open', `Open (${d.actions.filter((a) => !a.done && a.state === 'Default').length})`, AlertTriangle],
          ['fix', `Direct toe te passen (${openActies.filter((a) => a.fix && a.fix.possible).length})`, Wand],
          ['done', `Voltooid (${d.actions.filter((a) => a.done).length})`, CheckCircle2],
          ['ignored', `Genegeerd/derde partij (${openActies.filter((a) => a.state !== 'Default').length})`], ['alle', 'Alle']]} />
        <SearchBox value={q} onChange={setQ} placeholder="Zoek actie..." />
        <table className="vastkop" style={{ marginTop: 10 }}>
          <thead><tr><th style={{ width: 28 }} /><th>Actie</th><th className="r">Winst</th><th>Impact gebruikers</th><th>Werk</th><th>Toepassen</th></tr></thead>
          <tbody>{shown.map((a) => {
            const isOpen = open[a.id];
            const kan = a.fix && a.fix.possible && !a.done;
            return [
              <tr key={a.id} className="tegelklik" onClick={() => setOpen((o) => ({ ...o, [a.id]: !o[a.id] }))}>
                <td onClick={(e) => e.stopPropagation()}>{kan && a.fix.applied !== true
                  ? <input type="checkbox" checked={kies.includes(a.id)} onChange={(e) => setKies((k) => (e.target.checked ? [...k, a.id] : k.filter((x) => x !== a.id)))} />
                  : (isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />)}</td>
                <td><b>{a.title}</b><br /><small className="hint">{a.category}{a.service ? ` · ${a.service}` : ''}{STATUS[a.state] ? ` · ${STATUS[a.state]}` : ''}</small></td>
                <td className="r" style={{ whiteSpace: 'nowrap' }}>{a.done ? <Chip k="g">Voltooid</Chip> : <><b>+{a.gainPct.toFixed(2)}%</b><br /><small className="hint">{a.score} / {a.max} pt</small></>}</td>
                <td>{IMPACT[a.userImpact] ? <Chip k={IMPACT[a.userImpact][1]}>{IMPACT[a.userImpact][0]}</Chip> : '-'}</td>
                <td><small>{a.cost || '-'}</small></td>
                <td>{a.done ? '' : a.fix ? (a.fix.applied ? <Chip k="g" title="De instelling staat al goed; Microsoft werkt de score binnen 24-48 uur bij.">Al aangepast</Chip>
                  : a.fix.possible ? <Chip k="o">Direct mogelijk</Chip> : <Chip k="mu">Exchange nodig</Chip>) : <Chip k="mu">Handmatig</Chip>}</td>
              </tr>,
              isOpen && (
                <tr key={a.id + '-d'}><td /><td colSpan={5} style={{ background: 'var(--bg, #f6f8fa)' }}>
                  <div className="kv" style={{ gridTemplateColumns: '1fr', gap: 10, padding: '6px 0' }}>
                    {a.fix && <div><label>Wat de app aanpast</label><div style={{ fontWeight: 400 }}>{a.fix.what}</div></div>}
                    <div><label style={{ color: 'var(--rd)' }}>Negatieve impact</label><div style={{ fontWeight: 400, whiteSpace: 'pre-line' }}>
                      {a.fix ? a.fix.impact : a.impactNl || 'Onbekend.'}
                      {!a.fix && a.remediationImpact && <><br /><small className="hint">Microsoft: {a.remediationImpact}</small></>}</div></div>
                    {a.remediation && <div><label>Uitleg van Microsoft (Engels)</label><div style={{ fontWeight: 400, whiteSpace: 'pre-line', maxHeight: 220, overflow: 'auto' }}><small>{a.remediation}</small></div></div>}
                  </div>
                  <div className="btns" style={{ marginBottom: 6 }}>
                    {kan && a.fix.applied !== true && <Btn s v="p" icon={Zap} onClick={() => toepassen([a])}>Direct toepassen</Btn>}
                    {a.actionUrl && <Btn s icon={ExternalLink} onClick={() => portaal(a.actionUrl)}>Openen in beheercentrum</Btn>}
                  </div>
                </td></tr>
              ),
            ];
          })}</tbody>
        </table>
        {!shown.length && <div className="hint">Geen acties in deze selectie.</div>}
      </Card>
    </>
  );
}
