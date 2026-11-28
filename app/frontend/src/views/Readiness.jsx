// Gedeeld scherm voor readiness-controles met score (Copilot-readiness en NEN 7510).
import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, ClipboardList, FileText, Lightbulb, RefreshCw, XCircle, Zap } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, toast } from '../overlays.jsx';
import { useApp } from '../store.jsx';
import { Btn, Card, Chip, Loading, csv } from '../ui.jsx';

const ST = { ok: ['In orde', 'g', CheckCircle2, 'gr'], warn: ['Aandacht', 'o', AlertTriangle, 'or'], err: ['Actie nodig', 'r', XCircle, 'rd'], unknown: ['Onbekend', 'mu', CircleHelp, 'mu'] };
const kleur = (s) => (s >= 80 ? 'gr' : s >= 55 ? 'or' : 'rd');

function Meter({ score, label }) {
  const r = 52, omtrek = 2 * Math.PI * r;
  return (
    <svg width="140" height="140" viewBox="0 0 140 140" role="img" aria-label={`${label}: ${score}%`}>
      <circle cx="70" cy="70" r={r} fill="none" stroke="var(--bd)" strokeWidth="12" />
      <circle cx="70" cy="70" r={r} fill="none" stroke={`var(--${kleur(score)})`} strokeWidth="12" strokeLinecap="round"
        strokeDasharray={`${omtrek * score / 100} ${omtrek}`} transform="rotate(-90 70 70)" />
      <text x="70" y="74" textAnchor="middle" style={{ font: '900 30px Lato, sans-serif', fill: 'var(--navy)' }}>{score}%</text>
      <text x="70" y="96" textAnchor="middle" style={{ font: '700 11px Lato, sans-serif', fill: 'var(--mu)' }}>{label}</text>
    </svg>
  );
}

export default function Readiness({ naam, titel, intro, scoreLabel, refLabel, pdf }) {
  const { info } = useApp();
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [open, setOpen] = useState({});
  const [alleenOpen, setAlleenOpen] = useState(true);
  const laad = async (fresh) => {
    setFout(''); if (fresh) setD(null);
    try { setD(await api(naam, { fresh }, { quiet: true })); } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { laad(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (fout && !d) return <><h2>{titel}</h2><Msg kind="warn">{fout}</Msg></>;
  if (!d) return <><h2>{titel}</h2><p className="sub">{intro}</p><Loading text="Alles controleren (MFA, apparaten, e-mail, delen, logging)..." /></>;

  const toepassen = async (x) => {
    if (!await ask(`${x.title}\n\nWat de app aanpast: ${x.fix.what}\n\nNegatieve impact: ${x.fix.impact}`, 'Toepassen', true, 'Direct toepassen')) return;
    if (await act('rd.apply', { key: x.fix.key }, { msg: `${x.title}...` })) laad(true);
  };
  const rapport = async () => {
    const open_ = d.checks.filter((x) => x.status !== 'ok').length;
    if (open_ && !await ask(`Er staan nog ${open_} punt(en) open (of zijn niet vast te stellen). Het rapport wordt daarom een tussenrapportage met de openstaande punten erin.\n\nAls alles op orde is, staat in het rapport dat alle technische maatregelen zijn ingericht.`, 'Tussenrapportage maken')) return;
    const r = await act(pdf, {}, { msg: 'Rapport opstellen...' });
    if (r) toast(`Rapport opgeslagen en geopend: ${r.path}`, 'g');
  };
  const lijst = d.checks.filter((x) => !alleenOpen || x.status !== 'ok');
  const fixbaar = d.checks.filter((x) => x.fix);
  const tel = (s) => d.checks.filter((x) => x.status === s).length;
  const export_ = () => csv(`${naam.replace('rd.', '')}-${(info.tenant || 'klant').replace(/[^\w-]+/g, '-')}.csv`, [
    ['Categorie', 'Controle', refLabel || 'Verwijzing', 'Status', 'Toelichting', 'Details', 'Winst %', 'Directe actie', 'Negatieve impact'],
    ...d.checks.map((x) => [x.category, x.title, x.ref, ST[x.status][0], x.text, (x.details || []).join(', '), x.gainPct, x.fix ? x.fix.what : '', x.fix ? x.fix.impact : '']),
    ...d.manual.map((m) => [m.category, m.title, m.ref, 'Handmatig vaststellen', 'Niet technisch te meten; aantonen met documentatie.', '', '', '', '']),
  ]);

  return (
    <>
      <h2>{titel}</h2>
      <p className="sub">{intro}</p>
      <div className="readkop">
        <Card><div style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
          <Meter score={d.score} label={scoreLabel} />
          <div style={{ flex: 1, minWidth: 200 }}>
            <div className="btns" style={{ marginBottom: 10 }}>
              <Chip k="r">{tel('err')} actie nodig</Chip><Chip k="o">{tel('warn')} aandacht</Chip><Chip k="g">{tel('ok')} in orde</Chip>
              {tel('unknown') > 0 && <Chip k="mu">{tel('unknown')} onbekend</Chip>}
            </div>
            <div className="hint" style={{ margin: 0 }}>{fixbaar.length} punt(en) kan de app direct voor je aanpassen (met bevestiging). Onbekende punten tellen niet mee in de score.</div>
            <div className="btns" style={{ marginTop: 10 }}>
              <Btn s icon={RefreshCw} onClick={() => laad(true)}>Opnieuw controleren</Btn>
              <Btn s onClick={export_}>Rapport (CSV)</Btn>
              {pdf && <Btn s v="p" icon={FileText} onClick={rapport}>Rapport voor de klant (PDF)</Btn>}
            </div>
          </div>
        </div></Card>
        <Card title="Per onderdeel">
          {d.categories.map((c) => (
            <div key={c.name} style={{ marginBottom: 9 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><b>{c.name}</b><span style={{ color: `var(--${kleur(c.score)})`, fontWeight: 900 }}>{c.score}%</span></div>
              <div className="bar"><i style={{ width: `${c.score}%`, background: `var(--${kleur(c.score)})` }} /></div>
            </div>))}
        </Card>
      </div>

      <Card title="Controles" icon={ClipboardList} right={<label className="hint" style={{ margin: 0 }}>
        <input type="checkbox" checked={alleenOpen} onChange={(e) => setAlleenOpen(e.target.checked)} /> Alleen wat aandacht vraagt</label>}>
        <table className="vastkop">
          <thead><tr><th style={{ width: 24 }} /><th>Controle</th><th>Status</th><th className="r">Winst</th><th>Directe actie</th></tr></thead>
          <tbody>{lijst.map((x) => {
            const [lbl, k, I, kl] = ST[x.status] || ST.unknown;
            const isOpen = open[x.key];
            return [
              <tr key={x.key} className="tegelklik" onClick={() => setOpen((o) => ({ ...o, [x.key]: !o[x.key] }))}>
                <td>{isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                <td><I size={15} style={{ color: `var(--${kl})`, verticalAlign: -3, marginRight: 6 }} /><b>{x.title}</b>
                  <br /><small className="hint">{x.category}{x.ref ? ` · ${refLabel} ${x.ref}` : ''}</small></td>
                <td><Chip k={k}>{lbl}</Chip></td>
                <td className="r">{x.gainPct ? <b>+{x.gainPct}%</b> : '-'}</td>
                <td onClick={(e) => e.stopPropagation()}>{x.fix ? <Btn s v="p" icon={Zap} onClick={() => toepassen(x)}>Toepassen</Btn> : <small className="hint">{x.status === 'ok' ? '' : 'handmatig'}</small>}</td>
              </tr>,
              isOpen && (
                <tr key={x.key + '-d'}><td /><td colSpan={4} style={{ background: 'var(--bg)' }}>
                  <div style={{ padding: '4px 0' }}>{x.text}</div>
                  {x.details && x.details.length > 0 && <div className="hint" style={{ margin: '4px 0' }}>{x.details.join(' · ')}</div>}
                  {x.fix && <div className="kv" style={{ gridTemplateColumns: '1fr', gap: 8, marginTop: 8 }}>
                    <div><label>Wat de app aanpast</label><div style={{ fontWeight: 400 }}>{x.fix.what}</div></div>
                    <div><label style={{ color: 'var(--rd)' }}>Negatieve impact</label><div style={{ fontWeight: 400 }}>{x.fix.impact}</div></div>
                  </div>}
                </td></tr>),
            ];
          })}</tbody>
        </table>
        {!lijst.length && <Msg kind="ok">Alle controles zijn in orde.</Msg>}
      </Card>

      {d.manual.length > 0 && (
        <Card title={`Handmatig vast te stellen (${d.manual.length})`} icon={ClipboardList}>
          <div className="hint" style={{ marginTop: 0 }}>Deze onderdelen van NEN 7510 zijn niet technisch te meten. Leg ze vast in beleid en procedures en neem ze op in de auditor-map. Ze tellen niet mee in de score hierboven.</div>
          <table>
            <thead><tr><th>Onderdeel</th><th>Wat moet aantoonbaar zijn</th><th>{refLabel}</th></tr></thead>
            <tbody>{d.manual.map((m) => <tr key={m.title}><td><Chip k="mu">{m.category}</Chip></td><td>{m.title}</td><td><small>{m.ref}</small></td></tr>)}</tbody>
          </table>
        </Card>
      )}
      {d.advice.length > 0 && (
        <Card title="Aanbevelingen" icon={Lightbulb}>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{d.advice.map((a) => <li key={a} style={{ marginBottom: 4 }}>{a}</li>)}</ul>
        </Card>
      )}
    </>
  );
}
