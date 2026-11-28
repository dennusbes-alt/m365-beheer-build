// Migratie naar Exchange Online: IMAP, Google Workspace, Exchange on-premises (hybride) en cutover.
// Zelfde cmdlets als PowerShell (New-MigrationEndpoint, New-MigrationBatch, Start/Stop/Complete-MigrationBatch, ...).
import { Fragment, useEffect, useRef, useState } from 'react';
import { startTab } from '../store.jsx';
import { CheckCircle2, Download, FileUp, Pause, Play, Plug, Plus, RefreshCw, Save, Send, Trash2, Truck, XCircle } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, askType, toast } from '../overlays.jsx';
import { useApp } from '../store.jsx';
import { Btn, Card, Check, Chip, Field, Loading, Tabs, csv, dt } from '../ui.jsx';

const SOORTEN = {
  imap: { naam: 'IMAP', uitleg: 'Van elke mailserver met IMAP (bijv. hosting, Gmail privé, Zimbra). Alleen e-mail, geen agenda of contacten. Je hebt per gebruiker het wachtwoord van het oude postvak nodig.' },
  gmail: { naam: 'Google Workspace', uitleg: 'Mail, agenda en contacten uit Google Workspace. Vraagt een Google-serviceaccount met domeinbrede delegatie (JSON-sleutelbestand) en een beheerdersadres.' },
  remote: { naam: 'Exchange on-premises (hybride)', uitleg: 'Postvakken verhuizen vanaf een eigen Exchange-server in een hybride omgeving (MRS-proxy). De gebruikers bestaan al als e-mailgebruiker via Entra Connect.' },
  cutover: { naam: 'Exchange on-premises (cutover)', uitleg: 'Alle postvakken in één keer vanaf Exchange 2010 of nieuwer zonder hybride koppeling. Alleen voor kleine omgevingen (tot 2000 postvakken). Gebruikers worden in Microsoft 365 aangemaakt.' },
};
const STATUS = {
  Created: ['Aangemaakt', 'mu'], Syncing: ['Bezig met synchroniseren', 'o'], Synced: ['Gesynchroniseerd', 'g'], SyncedWithErrors: ['Gesynchroniseerd met fouten', 'o'],
  Completing: ['Wordt voltooid', 'o'], Completed: ['Voltooid', 'g'], CompletedWithErrors: ['Voltooid met fouten', 'o'], Stopped: ['Gestopt', 'mu'],
  Stopping: ['Wordt gestopt', 'mu'], Failed: ['Mislukt', 'r'], Removing: ['Wordt verwijderd', 'mu'], Starting: ['Wordt gestart', 'o'], Queued: ['In de wachtrij', 'mu'],
  Validating: ['Controleren', 'mu'], IncrementalSyncing: ['Bijwerken', 'o'], Provisioning: ['Voorbereiden', 'o'],
};
const statusChip = (s) => { const x = STATUS[s] || [s || '-', 'mu']; return <Chip k={x[1]}>{x[0]}</Chip>; };
const BEZIG = ['Syncing', 'Completing', 'Starting', 'Stopping', 'Removing', 'Provisioning', 'Validating', 'IncrementalSyncing', 'Queued'];

export default function Migratie() {
  const { info } = useApp();
  const [tab, setTab] = useState(() => startTab('migratie', 'batches'));
  const [nieuw, setNieuw] = useState(0);
  if (info.exo === false) return <><h2>Migratie</h2><Msg kind="err">Exchange Online is niet verbonden bij deze klant. Migreren vraagt de rol Exchange Administrator.</Msg></>;
  return (
    <>
      <h2>Migratie</h2>
      <p className="sub">Postvakken naar Microsoft 365 verhuizen vanaf IMAP, Google Workspace of Exchange on-premises. Zelfde mogelijkheden als de migratiebatches in PowerShell en het Exchange-beheercentrum.</p>
      <Tabs value={tab} onChange={setTab} tabs={[['batches', 'Migraties', Truck], ['nieuw', 'Nieuwe migratie', Plus], ['verbindingen', 'Verbindingen', Plug]]} />
      {tab === 'batches' && <Batches key={nieuw} onNieuw={() => setTab('nieuw')} />}
      {tab === 'nieuw' && <Nieuw onKlaar={() => { setNieuw((n) => n + 1); setTab('batches'); }} />}
      {tab === 'verbindingen' && <Verbindingen />}
    </>
  );
}

// ---------------- Overzicht van migraties ----------------
function Batches({ onNieuw }) {
  const [l, setL] = useState(null);
  const [sel, setSel] = useState(null);
  const timer = useRef(null);
  const laad = async () => {
    const d = await act('mig.batches', {}, { quiet: l !== null });
    setL(d ? d.batches : (l || []));
    return d ? d.batches : [];
  };
  // Zolang er iets loopt: elke 30 seconden live bijwerken
  useEffect(() => {
    let weg = false;
    const tik = async () => { const b = await laad(); if (!weg && b.some((x) => BEZIG.includes(x.status))) timer.current = setTimeout(tik, 30000); };
    tik();
    return () => { weg = true; clearTimeout(timer.current); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!l) return <Loading text="Migraties ophalen..." />;
  const b = l.find((x) => x.id === sel);
  return (
    <>
      <Card title={`${l.length} migratie(s)`} icon={Truck} right={<div className="btns"><Btn s v="p" icon={Plus} onClick={onNieuw}>Nieuwe migratie</Btn><Btn s icon={RefreshCw} onClick={laad}>Vernieuwen</Btn></div>}>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead><tr><th>Naam</th><th>Soort</th><th>Status</th><th className="r">Gebruikers</th><th className="r">Gesynchroniseerd</th><th className="r">Voltooid</th><th className="r">Mislukt</th><th>Laatste synchronisatie</th></tr></thead>
            <tbody>
              {l.map((x) => (
                <tr key={x.id} className={'click' + (sel === x.id ? ' on' : '')} onClick={() => setSel(sel === x.id ? null : x.id)}>
                  <td><b>{x.id}</b>{x.endpoint && <div className="hint" style={{ margin: 0 }}>{x.endpoint}</div>}</td>
                  <td>{x.typeText}</td><td>{statusChip(x.status)}</td>
                  <td className="r">{x.total}</td><td className="r">{x.synced}</td><td className="r">{x.finalized}</td>
                  <td className="r">{x.failed ? <b style={{ color: 'var(--rd)' }}>{x.failed}</b> : 0}</td>
                  <td>{x.lastSync ? dt(x.lastSync) : '-'}</td>
                </tr>
              ))}
              {!l.length && <tr><td colSpan={8} className="hint">Er zijn bij deze klant nog geen migraties. Start er een via <b>Nieuwe migratie</b>.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
      {b && <BatchDetail key={b.id} b={b} onChanged={async (weg) => { if (weg) setSel(null); await laad(); }} />}
    </>
  );
}

function BatchDetail({ b, onChanged }) {
  const { info } = useApp();
  const [u, setU] = useState(null);
  const [voltooi, setVoltooi] = useState(b.completeAfter ? b.completeAfter.slice(0, 16) : '');
  const [melding, setMelding] = useState(b.notify || '');
  const laad = async () => { const d = await act('mig.users', { id: b.id }, { quiet: u !== null }); setU(d ? d.users : (u || [])); };
  useEffect(() => { laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const actie = async (a, vraag, typ) => {
    if (typ ? !await askType(vraag, typ) : !await ask(vraag, 'Doorgaan')) return;
    if (await act('mig.batch.action', { id: b.id, action: a }, { msg: 'Bezig...' })) onChanged(a === 'remove');
  };
  const bewaar = async () => {
    const iso = voltooi ? new Date(voltooi).toISOString() : '';
    if (await act('mig.batch.set', { id: b.id, completeAfter: iso, notify: melding }, { msg: 'Opslaan...' })) onChanged();
  };
  const kanStart = ['Created', 'Stopped', 'Failed', 'SyncedWithErrors', 'CompletedWithErrors'].includes(b.status);
  const kanStop = ['Syncing', 'Synced', 'Starting', 'IncrementalSyncing', 'Queued'].includes(b.status);
  const kanVoltooi = ['Synced', 'SyncedWithErrors'].includes(b.status) && b.type !== 'imap';
  return (
    <Card title={b.id} icon={Truck} right={<Btn s icon={RefreshCw} onClick={() => { laad(); onChanged(); }}>Vernieuwen</Btn>}>
      <div className="kv">
        <div><label>Soort</label><div>{b.typeText}</div></div><div><label>Status</label><div>{statusChip(b.status)}</div></div>
        <div><label>Aangemaakt</label><div>{dt(b.created)}</div></div><div><label>Gestart</label><div>{b.started ? dt(b.started) : '-'}</div></div>
        <div><label>Bronverbinding</label><div>{b.endpoint || '-'}</div></div><div><label>Doeldomein</label><div>{b.domain || '-'}</div></div>
      </div>
      {b.message && <Msg kind="warn">{b.message}</Msg>}
      <div className="btns" style={{ marginTop: 14 }}>
        <Btn v="p" icon={Play} disabled={!kanStart} onClick={() => actie('start', `Migratie ${b.id} ${b.status === 'Created' ? 'starten' : 'hervatten'}?`)}>{b.status === 'Created' ? 'Starten' : 'Hervatten'}</Btn>
        <Btn icon={Pause} disabled={!kanStop} onClick={() => actie('stop', `Migratie ${b.id} stoppen? Je kunt hem later hervatten.`)}>Stoppen</Btn>
        <Btn icon={CheckCircle2} disabled={!kanVoltooi} onClick={() => actie('complete', `Migratie ${b.id} voltooien?\n\nEr volgt een laatste synchronisatie; daarna worden de postvakken definitief omgezet naar Microsoft 365. Zet de MX-records om zodra dit klaar is.`)}>Voltooien</Btn>
        <Btn v="dl" icon={Trash2} onClick={() => actie('remove', `Migratie ${b.id} verwijderen?\n\nAl gemigreerde e-mail blijft staan in de postvakken; alleen de migratie zelf verdwijnt.`, 'VERWIJDEREN')}>Verwijderen</Btn>
      </div>
      {b.type === 'imap' && <div className="hint">Een IMAP-migratie synchroniseert elke 24 uur opnieuw tot je hem verwijdert. Verwijder hem pas als de MX-records naar Microsoft 365 wijzen.</div>}
      <div className="row" style={{ marginTop: 14 }}>
        {b.type !== 'imap' && <div><label className="f">Automatisch voltooien op</label><input type="datetime-local" value={voltooi} onChange={(e) => setVoltooi(e.target.value)} /></div>}
        <Field label="Meldingen naar (komma)" value={melding} onChange={setMelding} placeholder={info.account} />
        <div className="n"><Btn icon={Save} onClick={bewaar}>Opslaan</Btn></div>
      </div>
      <div className="row" style={{ marginTop: 16, alignItems: 'center' }}>
        <b style={{ flex: 1 }}>Gebruikers {u ? `(${u.length})` : ''}</b>
        <div className="n"><Btn s icon={Download} disabled={!u || !u.length} onClick={() => csv(`migratie-${b.id}.csv`, [['E-mailadres', 'Status', 'Detail', 'Items gesynchroniseerd', 'Items overgeslagen', 'Items in bron', 'Overgedragen', 'Voortgang %', 'Laatste synchronisatie', 'Fout'],
          ...u.map((x) => [x.mail, x.status, x.detail, x.synced, x.skipped, x.total, x.size, x.percent, x.lastSync, x.error])])}>CSV</Btn></div>
      </div>
      {!u ? <Loading text="Voortgang per gebruiker ophalen..." /> : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ marginTop: 6 }}>
            <thead><tr><th>E-mailadres</th><th>Status</th><th style={{ width: '18%' }}>Voortgang</th><th className="r">Items</th><th className="r">Overgeslagen</th><th>Overgedragen</th><th>Laatste sync</th></tr></thead>
            <tbody>{u.map((x) => (
              <Fragment key={x.mail}>
                <tr><td>{x.mail}</td><td>{statusChip(x.status)}{x.detail && <div className="hint" style={{ margin: 0 }}>{x.detail}</div>}</td>
                  <td><div className="bar"><i style={{ width: `${Math.min(100, x.percent || 0)}%` }} /></div><small className="hint">{x.percent || 0}%</small></td>
                  <td className="r">{x.synced}{x.total ? ` / ${x.total}` : ''}</td><td className="r">{x.skipped || 0}</td><td>{x.size || '-'}</td><td>{x.lastSync ? dt(x.lastSync) : '-'}</td></tr>
                {x.error && <tr><td colSpan={7} style={{ color: 'var(--rd)', fontSize: 13 }}><XCircle size={13} style={{ verticalAlign: -2 }} /> {x.error}</td></tr>}
              </Fragment>))}
              {!u.length && <tr><td colSpan={7} className="hint">Geen gebruikers in deze migratie.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------- Nieuwe migratie ----------------
const leeg = () => ({ mail: '', user: '', password: '' });

// CSV lezen (komma of puntkomma, kolommen EmailAddress / UserName / Password, of gewoon e-mailadressen)
function leesCsv(tekst) {
  const regels = tekst.replace(/^﻿/, '').split(/\r?\n/).filter((r) => r.trim());
  if (!regels.length) return [];
  const sep = (regels[0].match(/;/g) || []).length > (regels[0].match(/,/g) || []).length ? ';' : ',';
  const splits = (r) => { const uit = []; let cur = ''; let q = false; for (const ch of r) { if (ch === '"') q = !q; else if (ch === sep && !q) { uit.push(cur); cur = ''; } else cur += ch; } uit.push(cur); return uit.map((x) => x.trim()); };
  const kop = splits(regels[0]).map((k) => k.toLowerCase());
  const heeftKop = kop.some((k) => /email|mail|user|password/.test(k));
  const i = (n) => kop.findIndex((k) => n.test(k));
  const im = heeftKop ? Math.max(0, i(/email|^mail/)) : 0;
  const iu = heeftKop ? i(/user|gebruiker/) : 1;
  const ip = heeftKop ? i(/pass|wachtw/) : 2;
  return (heeftKop ? regels.slice(1) : regels).map(splits).map((c) => ({ mail: c[im] || '', user: iu >= 0 ? c[iu] || '' : '', password: ip >= 0 ? c[ip] || '' : '' })).filter((r) => r.mail);
}

function Nieuw({ onKlaar }) {
  const { info } = useApp();
  const [soort, setSoort] = useState('');
  const [eps, setEps] = useState(null);
  const [ep, setEp] = useState('');
  const [nep, setNep] = useState({ name: '', server: '', port: '993', security: 'Ssl', admin: '', user: '', password: '', keyFile: '', keyName: '', proxy: '', max: '' });
  const [getest, setGetest] = useState(null);
  const [rijen, setRijen] = useState([leeg(), leeg(), leeg()]);
  const [check, setCheck] = useState(null);
  const [doms, setDoms] = useState([]);
  const [opt, setOpt] = useState({ name: '', domain: '', exclude: '', notify: info.account || '', autoStart: true, autoComplete: false, badItems: '' });
  const bestand = useRef(null);
  const sleutel = useRef(null);
  useEffect(() => {
    act('mig.endpoints', {}, { quiet: true }).then((d) => setEps(d ? d.endpoints : []));
    act('mig.domains', {}, { quiet: true }).then((d) => { if (d) { setDoms(d.domains); setOpt((o) => ({ ...o, domain: o.domain || d.domains[0] || '' })); } });
  }, []);
  const z = (k) => (v) => { setNep((n) => ({ ...n, [k]: v })); setGetest(null); };
  const zo = (k) => (v) => setOpt((o) => ({ ...o, [k]: v }));
  const passend = (eps || []).filter((e) => e.type === soort);
  const kies = (s) => { setSoort(s); setGetest(null); setCheck(null); setEp(''); setNep((n) => ({ ...n, port: s === 'imap' ? '993' : n.port })); };

  const epData = () => ({ type: soort, ...nep });
  const test = async () => { const r = await act('mig.endpoint.test', epData(), { msg: 'Verbinding testen...' }); if (r) setGetest(r.ok); };
  const importeer = (e) => {
    const f = e.target.files[0]; e.target.value = '';
    if (!f) return;
    f.text().then((t) => { const r = leesCsv(t); if (!r.length) return toast('Geen e-mailadressen gevonden in dit bestand.', 'e'); setRijen(r); setCheck(null); toast(`${r.length} gebruiker(s) ingelezen.`, 'g'); });
  };
  const leesSleutel = (e) => {
    const f = e.target.files[0]; e.target.value = '';
    if (f) f.text().then((t) => { setNep((n) => ({ ...n, keyFile: t, keyName: f.name })); setGetest(null); });
  };
  const gevuld = rijen.filter((r) => r.mail.trim());
  const controleer = async () => { const r = await act('mig.check', { type: soort, rows: gevuld }, { msg: 'Postvakken controleren...' }); if (r) setCheck(r.rows); };
  const maak = async () => {
    if (!opt.name.trim()) return toast('Geef de migratie een naam.', 'e');
    if (soort !== 'cutover' && !gevuld.length) return toast('Voeg minimaal één gebruiker toe.', 'e');
    let endpoint = ep;
    if (!endpoint) {
      if (!nep.name.trim()) return toast('Kies een bestaande verbinding of geef de nieuwe verbinding een naam.', 'e');
      const r = await act('mig.endpoint.new', epData(), { msg: 'Verbinding aanmaken...' });
      if (!r) return;
      endpoint = (r.endpoint && r.endpoint.id) || nep.name.trim();
    }
    const fout = check ? check.filter((x) => !x.ok).length : 0;
    if (!await ask(`Migratie "${opt.name.trim()}" aanmaken${opt.autoStart ? ' en starten' : ''}?\n\nSoort: ${SOORTEN[soort].naam}\nGebruikers: ${soort === 'cutover' ? 'alle postvakken' : gevuld.length}`
      + (fout ? `\n\nLET OP: bij ${fout} gebruiker(s) gaf de controle een probleem.` : '') + (opt.autoComplete ? '\n\nDe migratie wordt na de eerste synchronisatie automatisch voltooid.' : ''), 'Aanmaken')) return;
    const r = await act('mig.batch.new', { type: soort, endpoint, rows: gevuld, ...opt }, { msg: 'Migratie aanmaken...' });
    if (r) onKlaar();
  };

  return (
    <>
      <Card title="1. Soort migratie" icon={Truck}>
        <div className="tegels" style={{ marginTop: 0 }}>
          {Object.entries(SOORTEN).map(([k, s]) => (
            <div key={k} className={'card click' + (soort === k ? ' on' : '')} style={{ cursor: 'pointer', borderColor: soort === k ? 'var(--cy)' : undefined, borderWidth: soort === k ? 2 : undefined }} onClick={() => kies(k)}>
              <b style={{ color: 'var(--navy)' }}>{s.naam}</b><div className="hint" style={{ margin: '4px 0 0' }}>{s.uitleg}</div>
            </div>
          ))}
        </div>
      </Card>

      {soort && (
        <Card title="2. Verbinding met de bron" icon={Plug}>
          {eps === null ? <Loading /> : (
            <>
              <label className="f" style={{ marginTop: 0 }}>Verbinding</label>
              <select value={ep} onChange={(e) => setEp(e.target.value)}>
                <option value="">Nieuwe verbinding maken</option>
                {passend.map((e) => <option key={e.id} value={e.id}>{e.id}{e.server ? ` (${e.server})` : ''}</option>)}
              </select>
              {!ep && (
                <>
                  <div className="row">
                    <Field label="Naam van de verbinding" value={nep.name} onChange={z('name')} placeholder={soort === 'imap' ? 'IMAP-oudehoster' : soort === 'gmail' ? 'Google' : 'Exchange-onprem'} />
                    {soort === 'imap' && <>
                      <Field label="IMAP-server" value={nep.server} onChange={z('server')} placeholder="imap.voorbeeld.nl" />
                      <Field label="Poort" value={nep.port} onChange={z('port')} />
                      <div><label className="f">Beveiliging</label><select value={nep.security} onChange={(e) => z('security')(e.target.value)}><option value="Ssl">SSL (poort 993)</option><option value="Tls">TLS (poort 143)</option><option value="None">Geen (niet aanbevolen)</option></select></div>
                    </>}
                    {soort === 'gmail' && <Field label="Beheerdersadres Google Workspace" value={nep.admin} onChange={z('admin')} placeholder="beheerder@bedrijf.nl" />}
                    {(soort === 'remote' || soort === 'cutover') && <>
                      <Field label={soort === 'remote' ? 'MRS-proxyserver (FQDN)' : 'Exchange-server (leeg = autodiscover)'} value={nep.server} onChange={z('server')} placeholder="mail.bedrijf.nl" />
                      {soort === 'cutover' && <Field label="Beheerdersadres" value={nep.admin} onChange={z('admin')} placeholder="beheerder@bedrijf.nl" />}
                    </>}
                  </div>
                  {soort === 'gmail' && (
                    <div className="row" style={{ alignItems: 'center' }}>
                      <input ref={sleutel} type="file" accept=".json,application/json" hidden onChange={leesSleutel} />
                      <Btn icon={FileUp} onClick={() => sleutel.current.click()}>JSON-sleutelbestand kiezen</Btn>
                      <span className="hint" style={{ margin: 0 }}>{nep.keyName ? `Gekozen: ${nep.keyName}` : 'Sleutel van het Google-serviceaccount (domeinbrede delegatie ingesteld).'}</span>
                    </div>
                  )}
                  {(soort === 'remote' || soort === 'cutover') && (
                    <div className="row">
                      <Field label="Beheeraccount on-premises" value={nep.user} onChange={z('user')} placeholder="DOMEIN\beheerder" />
                      <Field label="Wachtwoord" type="password" value={nep.password} onChange={z('password')} autoComplete="new-password" />
                    </div>
                  )}
                  <div className="btns" style={{ marginTop: 10 }}>
                    <Btn icon={Plug} onClick={test}>Verbinding testen</Btn>
                    {getest === true && <Chip k="g">Verbinding gelukt</Chip>}{getest === false && <Chip k="r">Niet gelukt</Chip>}
                  </div>
                  <div className="hint">De verbinding wordt pas aangemaakt bij stap 4. Wachtwoorden en sleutels worden niet bewaard.</div>
                </>
              )}
            </>
          )}
        </Card>
      )}

      {soort && soort !== 'cutover' && (
        <Card title={`3. Gebruikers (${gevuld.length})`} icon={Send} right={<div className="btns">
          <input ref={bestand} type="file" accept=".csv,text/csv,text/plain" hidden onChange={importeer} />
          <Btn s icon={FileUp} onClick={() => bestand.current.click()}>CSV importeren</Btn>
          <Btn s icon={Plus} onClick={() => setRijen((r) => [...r, leeg()])}>Rij toevoegen</Btn></div>}>
          <table>
            <thead><tr><th>E-mailadres in Microsoft 365</th>{soort === 'imap' && <><th>Gebruikersnaam oude postvak</th><th>Wachtwoord oude postvak</th></>}<th>Controle</th><th /></tr></thead>
            <tbody>{rijen.map((r, i) => {
              const c = check && check.find((x) => x.mail === r.mail.trim().toLowerCase());
              const zet = (k, v) => { setRijen((l) => l.map((x, j) => (j === i ? { ...x, [k]: v } : x))); setCheck(null); };
              return (
                <tr key={i}>
                  <td><input type="text" value={r.mail} onChange={(e) => zet('mail', e.target.value)} placeholder="naam@bedrijf.nl" /></td>
                  {soort === 'imap' && <>
                    <td><input type="text" value={r.user} onChange={(e) => zet('user', e.target.value)} placeholder="meestal het e-mailadres" /></td>
                    <td><input type="password" value={r.password} onChange={(e) => zet('password', e.target.value)} autoComplete="new-password" /></td>
                  </>}
                  <td>{c ? (c.ok ? <Chip k="g">in orde</Chip> : <Chip k="r" title={c.reason}>{c.reason}</Chip>) : <span className="hint">-</span>}</td>
                  <td className="r"><Btn s v="dl" icon={Trash2} onClick={() => setRijen((l) => (l.length > 1 ? l.filter((_, j) => j !== i) : [leeg()]))} /></td>
                </tr>
              );
            })}</tbody>
          </table>
          <div className="row" style={{ marginTop: 10, alignItems: 'center' }}>
            <div className="hint" style={{ flex: 1, margin: 0 }}>
              CSV met kolommen <b>EmailAddress</b>{soort === 'imap' ? <>, <b>UserName</b>, <b>Password</b></> : ''} (zoals Microsoft hem verwacht), of één e-mailadres per regel.
              {soort === 'imap' || soort === 'gmail' ? ' De postvakken moeten al bestaan in Microsoft 365 en een licentie hebben.' : ' De gebruikers moeten als e-mailgebruiker bestaan (via Entra Connect).'}
            </div>
            <div className="n"><Btn icon={CheckCircle2} disabled={!gevuld.length} onClick={controleer}>Controleren</Btn></div>
          </div>
        </Card>
      )}

      {soort && (
        <Card title={`${soort === 'cutover' ? '3' : '4'}. Opties en aanmaken`} icon={Save}>
          <div className="row">
            <Field label="Naam van de migratie" value={opt.name} onChange={zo('name')} placeholder="Bijv. Verkoop-week-48" />
            {(soort === 'gmail' || soort === 'remote') && (
              <div><label className="f">Doeldomein</label><select value={opt.domain} onChange={(e) => zo('domain')(e.target.value)}>{doms.map((d) => <option key={d}>{d}</option>)}</select></div>
            )}
            <Field label="Meldingen naar (komma)" value={opt.notify} onChange={zo('notify')} />
          </div>
          {soort === 'imap' && <Field label="Mappen overslaan (komma, optioneel)" value={opt.exclude} onChange={zo('exclude')} placeholder="Bijv. Spam, Prullenbak" />}
          {soort === 'remote' && <Field label="Maximaal aantal beschadigde items (optioneel)" value={opt.badItems} onChange={zo('badItems')} placeholder="Bijv. 10" />}
          <div style={{ marginTop: 12 }}>
            <Check checked={opt.autoStart} onChange={zo('autoStart')}>Direct starten</Check>
            {soort !== 'imap' && <Check checked={opt.autoComplete} onChange={zo('autoComplete')}>Automatisch voltooien na de eerste synchronisatie
              <div className="hint" style={{ margin: 0 }}>Laat dit meestal uit: dan voltooi je zelf op het moment dat je de MX-records omzet.</div></Check>}
          </div>
          <div className="btns" style={{ marginTop: 14 }}><Btn v="p" icon={Truck} onClick={maak}>Migratie aanmaken</Btn></div>
        </Card>
      )}
    </>
  );
}

// ---------------- Verbindingen ----------------
function Verbindingen() {
  const [l, setL] = useState(null);
  const laad = async () => { const d = await act('mig.endpoints', {}, { msg: 'Verbindingen ophalen...' }); setL(d ? d.endpoints : []); };
  useEffect(() => { laad(); }, []);
  if (!l) return <Loading text="Verbindingen ophalen..." />;
  const weg = async (e) => {
    if (await ask(`Verbinding ${e.id} verwijderen?\n\nDat kan alleen als geen enkele migratie hem nog gebruikt.`, 'Verwijderen', true)
      && await act('mig.endpoint.remove', { id: e.id }, { msg: 'Verwijderen...' })) laad();
  };
  return (
    <Card title={`${l.length} verbinding(en)`} icon={Plug} right={<Btn s icon={RefreshCw} onClick={laad}>Vernieuwen</Btn>}>
      <table>
        <thead><tr><th>Naam</th><th>Soort</th><th>Server</th><th>Poort / beveiliging</th><th>Gelijktijdig</th><th /></tr></thead>
        <tbody>{l.map((e) => (
          <tr key={e.id}><td><b>{e.id}</b>{e.account && <div className="hint" style={{ margin: 0 }}>{e.account}</div>}</td><td>{e.typeText}</td><td>{e.server || '-'}</td>
            <td>{e.port ? `${e.port} / ${e.security}` : '-'}</td><td>{e.max || '-'}</td>
            <td className="r"><Btn s v="dl" icon={Trash2} onClick={() => weg(e)}>Verwijderen</Btn></td></tr>))}
          {!l.length && <tr><td colSpan={6} className="hint">Nog geen verbindingen. Die maak je aan bij Nieuwe migratie.</td></tr>}
        </tbody>
      </table>
    </Card>
  );
}
