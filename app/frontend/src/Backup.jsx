// Back-up (servicedesk): status van Datto BCDR, Datto Endpoint Backup, Datto SaaS Protection en Unitrends per klant,
// met een gedeelde afvinklijst (SharePoint Justdata). Vervangt de Excel-lijst.
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Play, Square, Timer, CheckCircle2, ChevronDown, ChevronRight, ClipboardCheck, KeyRound, RefreshCw, Settings, ShieldCheck, UserCheck, Undo2 } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox, csv, dt } from './ui.jsx';

const ST = { ok: ['Goed', 'g'], warn: ['Waarschuwing', 'o'], err: ['Fout', 'r'], unknown: ['Onbekend', 'mu'], paused: ['Pauze', 'mu'] };
const UITKOMST = { OK: 'g', 'Actie nodig': 'o', Opgelost: 'g' };
const KLEUR = { ...UITKOMST, 'Ticket aangemaakt': 'o' };   // oudere afvinkingen
const vandaagStr = () => new Date().toDateString();
const sleutel = (n) => String(n || '').trim().toLowerCase();
const Tegel = ({ label, n, kleur, sub, on, onClick }) => (
  <div className="card tegelklik" onClick={onClick} style={on ? { borderColor: 'var(--cy)', boxShadow: '0 0 0 2px rgba(0,174,239,.25)' } : undefined}>
    <div className="hint" style={{ margin: 0 }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 900, color: kleur ? `var(--${kleur})` : 'var(--navy)' }}>{n}</div>
    {sub && <div className="hint" style={{ margin: 0 }}>{sub}</div>}
  </div>
);
const tijd = (s) => (s ? (/^\d{4}-\d{2}-\d{2}$/.test(s) ? s.split('-').reverse().join('-') : dt(s)) : '-');

// Datto SaaS Protection per gebruiker, gedeeld postvak, SharePoint-site en team; wat misgaat staat bovenaan
function SaasSeats({ id }) {
  const [r, setR] = useState(null);
  const [fout, setFout] = useState('');
  const [soort, setSoort] = useState('');
  const [q, setQ] = useState('');
  const [alles, setAlles] = useState(false);
  const laad = (fresh) => { setFout(''); api('bk.saas.seats', { id, fresh: !!fresh }, { quiet: true, nobusy: true }).then(setR).catch((e) => { setFout(e.message); setR({ seats: [], counts: {}, perType: {}, errors: [] }); }); };
  useEffect(() => { laad(false); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!r) return <div className="hint" style={{ marginTop: 10 }}>SaaS Protection per gebruiker, site en team ophalen...</div>;
  const zoek = q.trim().toLowerCase();
  const lijst = r.seats.filter((s) => (!soort || s.typeLabel === soort) && (!zoek || (s.name + ' ' + s.address).toLowerCase().includes(zoek)));
  const problemen = lijst.filter((s) => s.status !== 'ok' && s.status !== 'unknown');
  const toon = alles || lijst.length <= 30 ? lijst : [...problemen, ...lijst.filter((s) => !problemen.includes(s))].slice(0, Math.max(30, problemen.length));
  const n = r.counts || {};
  return (
    <div style={{ marginTop: 12 }}>
      <div className="btns" style={{ alignItems: 'center', margin: '0 0 6px' }}>
        <b>SaaS Protection per onderdeel</b>
        {(n.err || 0) > 0 && <Chip k="r">{n.err} fout</Chip>}
        {(n.warn || 0) > 0 && <Chip k="o">{n.warn} waarschuwing</Chip>}
        {(n.paused || 0) > 0 && <Chip k="mu">{n.paused} op pauze</Chip>}
        {(n.ok || 0) > 0 && <Chip k="g">{n.ok} goed</Chip>}
        <span className="spacer" />
        <select value={soort} onChange={(e) => setSoort(e.target.value)} style={{ width: 'auto' }}>
          <option value="">Alle soorten ({r.seats.length})</option>
          {Object.entries(r.perType || {}).map(([k, v]) => <option key={k} value={k}>{k} ({v})</option>)}
        </select>
        <input type="text" placeholder="Zoek naam of adres..." value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 200 }} />
        <Btn s icon={RefreshCw} onClick={() => { setR(null); laad(true); }}>Vernieuwen</Btn>
      </div>
      {fout && <Msg k="e">{fout}</Msg>}
      {(r.errors || []).map((e) => <Msg key={e} k="w">{e}</Msg>)}
      {!r.statusKnown && r.seats.length > 0 && <div className="hint">Datto geeft voor deze klant geen back-upstatus per onderdeel door; je ziet wel welke onderdelen beschermd, gepauzeerd of niet beschermd zijn. Het totaal hierboven (x van y volledig) komt van Datto zelf.</div>}
      {r.seats.length === 0 && !fout ? <div className="hint">Geen gebruikers, sites of teams gevonden in SaaS Protection.</div> : (
        <table>
          <thead><tr><th>Soort</th><th>Naam</th><th>Status</th><th>Laatste back-up</th><th>Melding</th></tr></thead>
          <tbody>{toon.map((s, i) => (
            <tr key={i} style={s.status === 'err' ? { background: 'rgba(220,53,69,.06)' } : undefined}>
              <td><small>{s.typeLabel}</small></td>
              <td><b>{s.name}</b>{s.address && <><br /><small className="hint">{s.address}</small></>}</td>
              <td><Chip k={ST[s.status]?.[1]}>{s.status === 'unknown' ? (s.state || 'Beschermd') : ST[s.status]?.[0] || s.status}</Chip></td>
              <td><small>{tijd(s.last)}</small></td>
              <td><small>{s.message}</small></td>
            </tr>))}</tbody>
        </table>)}
      {toon.length < lijst.length && <Btn s onClick={() => setAlles(true)}>Alle {lijst.length} tonen</Btn>}
    </div>
  );
}

export default function Backup() {
  const [keys, setKeys] = useState(null);
  const [d, setD] = useState(null);
  const [checks, setChecks] = useState(null);
  const [opslag, setOpslag] = useState('');
  const [fout, setFout] = useState('');
  const [filter, setFilter] = useState('alle');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState({});
  const [kies, setKies] = useState([]);
  const [kiesItem, setKiesItem] = useState([]);   // onderdelen (sleutels) om aan een klant toe te wijzen
  const [instellen, setInstellen] = useState(false);
  const [sessieTik, setSessieTik] = useState(0);

  const [admin, setAdmin] = useState(false);
  const laadKeys = async () => { try { const x = await api('bk.keys.status', {}, { quiet: true }); setKeys(x.sources); setAdmin(!!x.admin); } catch (e) { setFout(e.message); } };
  const timer = useRef(null);
  // Het ophalen loopt op de achtergrond; het scherm vraagt elke 2 s de stand op en vult zich per bron
  const laad = async (fresh) => {
    clearTimeout(timer.current);
    setFout('');
    try {
      const x = await api('bk.overzicht', { fresh: !!fresh }, { quiet: true });
      setD(x);
      if (x.busy) timer.current = setTimeout(() => laad(false), 2000);
    } catch (e) { setFout(e.message || String(e)); setD((o) => o || { customers: [], errors: {}, sources: [], progress: {} }); }
  };
  const laadChecks = async () => { try { const x = await api('bk.controles', {}, { quiet: true }); setChecks(x.checks); setOpslag(x.storage); } catch { setChecks([]); } };
  useEffect(() => { laadKeys(); laad(false); laadChecks(); return () => clearTimeout(timer.current); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Laatste controle per klant
  const laatste = useMemo(() => {
    const m = {};
    (checks || []).forEach((c) => { const k = sleutel(c.customer); if (!m[k] || c.at > m[k].at) m[k] = c; });
    return m;
  }, [checks]);

  if (!keys || !d) return <div className="klanten"><Loading text="Back-up openen..." /></div>;
  const geenSleutels = !keys.some((k) => k.set);
  if (geenSleutels && !admin) return <div className="klanten"><Msg kind="info">Het back-upoverzicht is nog niet gekoppeld aan Datto of Unitrends. De app-beheerder stelt dit één keer in voor iedereen.</Msg></div>;
  if (geenSleutels || (instellen && admin)) return <div className="klanten"><Instellen keys={keys} onKlaar={() => { setInstellen(false); laadKeys(); laad(true); }} onTerug={geenSleutels ? null : () => setInstellen(false)} /></div>;

  const klanten = d.customers;
  const vandaagGedaan = (k) => laatste[sleutel(k.name)] && new Date(laatste[sleutel(k.name)].at).toDateString() === vandaagStr();
  const tel = { err: klanten.filter((k) => k.status === 'err').length, warn: klanten.filter((k) => k.status === 'warn').length,
    ok: klanten.filter((k) => k.status === 'ok').length, open: klanten.filter((k) => !vandaagGedaan(k)).length };
  const lijst = klanten.filter((k) => (filter === 'probleem' ? k.status === 'err' || k.status === 'warn' : filter === 'open' ? !vandaagGedaan(k)
    : filter === 'err' ? k.status === 'err' : filter === 'ok' ? k.status === 'ok' : true))
    .filter((k) => !q || `${k.name} ${k.items.map((i) => i.name).join(' ')}`.toLowerCase().includes(q.toLowerCase()));

  // Eén klik = OK. Alleen bij een afwijking (actie nodig, opgelost, opmerking) een venster.
  // De Autotask-registratie (intern ticket per medewerker per dag) gebeurt automatisch op de achtergrond.
  const afvinken = async (namen, afwijking = false) => {
    const r = afwijking ? await openModal((close) => <Afvinken namen={namen} close={close} />) : { result: 'OK', note: '' };
    if (!r) return;
    const nu = new Date().toISOString();
    setChecks((o) => [...namen.map((n) => ({ id: `nieuw-${n}`, customer: n, result: r.result, note: r.note, at: nu, by: 'jij' })), ...(o || [])]);
    setKies([]);
    await act('bk.afvinken', { customers: namen, ...r }, { msg: 'Afvinken...' });
    laadChecks();
    setSessieTik((n) => n + 1);
  };
  // Onderdelen (bijv. alle apparaten in de Datto-organisatie van Justdata) toewijzen aan de echte klant
  const toewijzen = async (sleutels, naam) => {
    const klant = naam != null ? naam : await openModal((close) => <Toewijzen aantal={sleutels.length} namen={klanten.map((k) => k.name)} close={close} />);
    if (klant == null) return;
    await act('bk.toewijzen', { keys: sleutels, customer: klant }, { msg: klant ? 'Toewijzen...' : 'Toewijzing opheffen...' });
    setKiesItem([]);
    laad(false);
  };
  const export_ = () => csv(`backup-overzicht-${new Date().toISOString().slice(0, 10)}.csv`, [
    ['Klant', 'Bron', 'Onderdeel', 'Soort', 'Status', 'Laatste geslaagde back-up', 'Laatste poging', 'Melding', 'Laatste controle', 'Door', 'Uitkomst'],
    ...klanten.flatMap((k) => k.items.map((i) => {
      const c = laatste[sleutel(k.name)] || {};
      return [k.name, i.source, i.name, i.kind, ST[i.status]?.[0] || i.status, tijd(i.lastOk), tijd(i.last), i.message, c.at ? dt(c.at) : '', c.by || '', c.result || ''];
    }))]);

  return (
    <div className="klanten breed">
      <div className="headrow" style={{ marginBottom: 6 }}>
        <div className="m"><h2 style={{ margin: 0 }}>Back-up</h2>
          <div className="hint" style={{ margin: 0 }}>{d.busy ? 'Bezig met ophalen...' : `Bijgewerkt om ${d.at}`} · afvinklijst {opslag === 'sharepoint' ? 'gedeeld in SharePoint' : 'op deze computer'}</div>
          <div className="btns" style={{ marginTop: 6 }}>{Object.entries(d.progress || {}).map(([k, v]) => (
            <Chip key={k} k={v.status === 'klaar' ? 'g' : v.status === 'fout' ? 'r' : 'o'}>
              {v.status === 'bezig' ? <span className="spin" style={{ width: 10, height: 10, borderWidth: 2, display: 'inline-block', verticalAlign: -1, marginRight: 5 }} /> : null}
              {k.replace('Datto ', '')}{v.status === 'klaar' ? ` · ${v.count} · ${v.sec}s` : v.status === 'fout' ? ' · fout' : ''}</Chip>))}
            {admin && !keys.find((x) => x.key === 'unitrends')?.set && <Chip k="mu" title="Koppel UniView via Koppelingen">Unitrends: niet gekoppeld</Chip>}</div></div>
        <div className="btns">
          {kies.length > 0 && <><Btn v="p" icon={ClipboardCheck} onClick={() => afvinken(kies)}>{kies.length} afvinken (OK)</Btn>
            <Btn s onClick={() => afvinken(kies, true)}>Met afwijking...</Btn></>}
          <Btn s onClick={export_}>CSV</Btn>
          {admin && <Btn s icon={Settings} onClick={() => setInstellen(true)}>Koppelingen</Btn>}
          <Btn s icon={RefreshCw} disabled={d.busy} onClick={() => { laad(true); laadChecks(); }}>{d.busy ? 'Bezig...' : 'Vernieuwen'}</Btn>
        </div>
      </div>
      <ControleBalk tik={sessieTik} />
      {fout && <Msg kind="warn">{fout}</Msg>}
      {Object.entries(d.errors || {}).map(([k, v]) => <Msg key={k} kind="warn"><b>{k}:</b> {v}</Msg>)}
      <div className="tegels" style={{ marginTop: 8 }}>
        <Tegel label="Klanten" n={klanten.length} sub={`${klanten.reduce((s, k) => s + k.items.length, 0)} onderdelen`} on={filter === 'alle'} onClick={() => setFilter('alle')} />
        <Tegel label="Met fouten" n={tel.err} kleur={tel.err ? 'rd' : 'gr'} sub="mislukt of te oud" on={filter === 'err'} onClick={() => setFilter(filter === 'err' ? 'alle' : 'err')} />
        <Tegel label="Met waarschuwing" n={tel.warn} kleur={tel.warn ? 'or' : 'gr'} sub="1-3 dagen oud of gedeeltelijk" on={filter === 'probleem'} onClick={() => setFilter(filter === 'probleem' ? 'alle' : 'probleem')} />
        <Tegel label="Alles goed" n={tel.ok} kleur="gr" on={filter === 'ok'} onClick={() => setFilter(filter === 'ok' ? 'alle' : 'ok')} />
        <Tegel label="Vandaag nog niet gecontroleerd" n={tel.open} kleur={tel.open ? 'or' : 'gr'} sub={`${klanten.length - tel.open} van ${klanten.length} afgevinkt`} on={filter === 'open'} onClick={() => setFilter(filter === 'open' ? 'alle' : 'open')} />
      </div>

      <Card title={`Klanten (${lijst.length})`} icon={ShieldCheck} right={<SearchBox value={q} onChange={setQ} placeholder="Zoek klant of apparaat..." />}>
        <table className="vastkop">
          <thead><tr><th style={{ width: 28 }}><input type="checkbox" checked={lijst.length > 0 && lijst.every((k) => kies.includes(k.name))}
            onChange={(e) => setKies(e.target.checked ? lijst.map((k) => k.name) : [])} /></th>
            <th>Klant</th><th>Status</th><th>Onderdelen</th><th>Bronnen</th><th>Laatste controle</th><th /></tr></thead>
          <tbody>{lijst.map((k) => {
            const c = laatste[sleutel(k.name)];
            const isOpen = open[k.name];
            return (
              <Fragment key={k.name}>
                <tr>
                  <td><input type="checkbox" checked={kies.includes(k.name)} onChange={(e) => setKies((x) => (e.target.checked ? [...x, k.name] : x.filter((y) => y !== k.name)))} /></td>
                  <td className="tegelklik" onClick={() => setOpen((o) => ({ ...o, [k.name]: !o[k.name] }))}>
                    {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} <b>{k.name}</b></td>
                  <td><Chip k={ST[k.status]?.[1]}>{ST[k.status]?.[0]}</Chip></td>
                  <td><small>{k.counts.ok > 0 && <Chip k="g">{k.counts.ok} goed</Chip>}{k.counts.warn > 0 && <Chip k="o">{k.counts.warn} waarsch.</Chip>}
                    {k.counts.err > 0 && <Chip k="r">{k.counts.err} fout</Chip>}{(k.counts.unknown + k.counts.paused) > 0 && <Chip k="mu">{k.counts.unknown + k.counts.paused} overig</Chip>}</small></td>
                  <td><small className="hint">{k.sources.map((s) => s.replace('Datto ', '')).join(', ')}</small></td>
                  <td>{c ? <><Chip k={KLEUR[c.result] || 'mu'}>{c.result}</Chip><br /><small className="hint">{dt(c.at)} · {c.by}{c.ticket ? ` · ticket ${c.ticket}` : ''}</small></> : <small className="hint">nog nooit</small>}</td>
                  <td>{vandaagGedaan(k) ? <CheckCircle2 size={18} style={{ color: 'var(--gr)' }} title="Vandaag gecontroleerd" /> : <span style={{ display: 'inline-flex', gap: 4 }}><Btn s v="p" onClick={() => afvinken([k.name])}>Afvinken</Btn>
                    <Btn s onClick={() => afvinken([k.name], true)} title="Afvinken met afwijking of opmerking">...</Btn></span>}</td>
                </tr>
                {isOpen && (
                  <tr><td /><td colSpan={6} style={{ background: 'var(--bg)' }}>
                    {(() => {
                      const eigen = k.items.map((i) => i.key).filter(Boolean);
                      const gekozen = eigen.filter((x) => kiesItem.includes(x));
                      const terug = k.items.filter((i) => i.origin && kiesItem.includes(i.key)).map((i) => i.key);
                      return (
                        <div className="btns" style={{ margin: '4px 0 8px', alignItems: 'center', minHeight: 32 }}>
                          <small className="hint" style={{ margin: 0 }}>Staan hier apparaten van meerdere klanten? Selecteer ze en wijs ze toe aan de juiste klant; dat geldt daarna voor iedereen.</small>
                          {gekozen.length > 0 && <Btn s v="p" icon={UserCheck} onClick={() => toewijzen(gekozen)}>{gekozen.length} toewijzen aan klant...</Btn>}
                          {terug.length > 0 && <Btn s icon={Undo2} onClick={() => toewijzen(terug, '')}>{terug.length} terugzetten</Btn>}
                        </div>);
                    })()}
                    <table>
                      <thead><tr><th style={{ width: 28 }}><input type="checkbox" title="Alles selecteren" checked={k.items.length > 0 && k.items.every((i) => kiesItem.includes(i.key))}
                        onChange={(e) => setKiesItem((x) => (e.target.checked ? [...new Set([...x, ...k.items.map((i) => i.key)])] : x.filter((y) => !k.items.some((i) => i.key === y))))} /></th>
                        <th>Bron</th><th>Onderdeel</th><th>Status</th><th>Laatste geslaagd</th><th>Laatste poging</th><th>Melding</th></tr></thead>
                      <tbody>{k.items.map((i, n) => (
                        <tr key={n}><td><input type="checkbox" checked={kiesItem.includes(i.key)} onChange={(e) => setKiesItem((x) => (e.target.checked ? [...x, i.key] : x.filter((y) => y !== i.key)))} /></td>
                          <td><small>{i.source}</small></td><td><b>{i.name}</b>{i.device && <><br /><small className="hint">{i.device}</small></>}
                          {i.origin && <><br /><small className="hint">toegewezen (in Datto: {i.origin})</small></>}</td>
                          <td><Chip k={ST[i.status]?.[1]}>{ST[i.status]?.[0] || i.status}</Chip></td><td><small>{tijd(i.lastOk)}</small></td><td><small>{tijd(i.last)}</small></td>
                          <td><small>{i.message}</small></td></tr>))}</tbody>
                    </table>
                    {[...new Set(k.items.filter((i) => i.saasId).map((i) => String(i.saasId)))].map((sid) => <SaasSeats key={sid} id={sid} />)}
                    {c && c.note && <div className="hint">Laatste opmerking ({c.by}): {c.note}</div>}
                  </td></tr>
                )}
              </Fragment>
            );
          })}</tbody>
        </table>
        {!lijst.length && <div className="hint">{d.busy && !klanten.length ? 'Back-ups worden opgehaald; klanten verschijnen hier zodra de eerste bron klaar is.' : 'Geen klanten in deze selectie.'}</div>}
        <div className="hint">Goed = geslaagde back-up in de laatste 26 uur. Waarschuwing = 26-72 uur of gedeeltelijk geslaagd. Fout = mislukt of ouder dan 3 dagen, of appliance offline.</div>
      </Card>
    </div>
  );
}

function Toewijzen({ aantal, namen, close }) {
  const [naam, setNaam] = useState('');
  return (
    <>
      <h3>{aantal === 1 ? 'Onderdeel' : `${aantal} onderdelen`} toewijzen aan klant</h3>
      <div className="hint" style={{ marginTop: 0 }}>Kies een bestaande klant of typ de naam. De toewijzing geldt voor alle collega's; daarna vink je deze klant los af.</div>
      <label className="f">Klant</label>
      <input list="bk-klanten" style={{ width: "100%" }} value={naam} onChange={(e) => setNaam(e.target.value)} placeholder="Naam van de klant" autoFocus
        onKeyDown={(e) => { if (e.key === 'Enter' && naam.trim()) close(naam.trim()); }} />
      <datalist id="bk-klanten">{[...new Set(namen)].sort().map((n) => <option key={n} value={n} />)}</datalist>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!naam.trim()} onClick={() => close(naam.trim())}>Toewijzen</button></div>
    </>);
}

function Afvinken({ namen, close }) {
  const [uitkomst, setUitkomst] = useState('Actie nodig');
  const [note, setNote] = useState('');
  return (
    <>
      <h3>Back-upcontrole afvinken</h3>
      <div className="hint" style={{ marginTop: 0 }}>{namen.length === 1 ? namen[0] : `${namen.length} klanten: ${namen.slice(0, 6).join(', ')}${namen.length > 6 ? ' ...' : ''}`}</div>
      <label className="f">Uitkomst</label>
      <div className="btns">{Object.keys(UITKOMST).map((u) => <Btn key={u} v={uitkomst === u ? 'p' : ''} onClick={() => setUitkomst(u)}>{u}</Btn>)}</div>
      <label className="f">Opmerking (optioneel)</label>
      <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Bijv. agent herstart, back-up loopt weer" />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" onClick={() => close({ result: uitkomst, note })}>Afvinken</button></div>
    </>
  );
}

function Instellen({ keys, onKlaar, onTerug }) {
  const [waarden, setWaarden] = useState({});
  const zet = (bron, veld, v) => setWaarden((o) => ({ ...o, [bron]: { ...(o[bron] || {}), [veld]: v } }));
  const opslaan = async (bron) => {
    const w = waarden[bron] || {};
    if (!w.a || !w.b) return toast('Vul beide velden in.', 'e');
    if (await act('bk.keys.set', { source: bron, a: w.a, b: w.b }, { msg: 'Verbinding testen en opslaan...' })) { setWaarden((o) => ({ ...o, [bron]: {} })); onKlaar(); }
  };
  const weg = async (bron) => { if (await ask('Sleutels voor deze koppeling verwijderen uit de kluis van deze computer?', 'Verwijderen', true)) { await act('bk.keys.delete', { source: bron }); onKlaar(); } };
  return (
    <>
      <div className="headrow"><h2 style={{ margin: 0 }}>Back-up: koppelingen</h2>{onTerug && <Btn s onClick={onTerug}>Terug naar overzicht</Btn>}</div>
      <p className="sub">Eén keer koppelen is genoeg: de sleutels worden eerst getest en daarna gedeeld met alle Justdata-collega's via een verborgen lijst op de Justdata-SharePoint. Collega's zien het back-upoverzicht dan direct, zonder zelf iets in te vullen. De sleutels komen nooit in het logboek. Vervangen of verwijderen geldt voor iedereen.</p>
      {keys.map((k) => (
        <Card key={k.key} title={k.name} icon={KeyRound} right={k.set ? <Chip k="g">ingesteld</Chip> : <Chip k="mu">niet ingesteld</Chip>}>
          <div className="hint" style={{ marginTop: 0 }}>{k.help}</div>
          <div className="row">{k.fields.map((f) => (
            <div key={f.key}><label className="f">{f.label}</label>
              <input type="password" autoComplete="off" value={(waarden[k.key] || {})[f.key] || ''} onChange={(e) => zet(k.key, f.key, e.target.value)} placeholder={k.set ? '(ongewijzigd)' : ''} /></div>))}
          </div>
          <div className="btns" style={{ marginTop: 10 }}><Btn v="p" onClick={() => opslaan(k.key)}>{k.set ? 'Vervangen' : 'Testen en opslaan'}</Btn>
            {k.set && <Btn v="dl" onClick={() => weg(k.key)}>Verwijderen</Btn>}</div>
        </Card>
      ))}
    </>
  );
}

// Back-upcontrole als werksessie: starten maakt één intern Autotask-ticket; afvinken verzamelt alleen; afronden zet
// alle afgevinkte klanten in één notitie, boekt de totale tijd (start tot afronden, per kwartier naar boven) en sluit het ticket.
function ControleBalk({ tik }) {
  const [s, setS] = useState(undefined);
  const [nu, setNu] = useState(Date.now());
  const laad = async () => { try { const r = await api('at.bk.status', {}, { quiet: true }); setS(r.configured ? (r.session ? { ...r.session, t: Date.now() } : null) : null); } catch { setS(null); } };
  useEffect(() => { laad(); }, [tik]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setInterval(() => setNu(Date.now()), 30000); return () => clearInterval(t); }, []);
  if (s === undefined) return null;
  const start = async () => { const r = await act('at.bk.start', {}, { msg: 'Back-upcontrole starten (ticket aanmaken)...' }); if (r) setS({ ...r.session, t: Date.now() }); };
  const stop = async (cancel) => {
    if (cancel ? !(await ask('Back-upcontrole stoppen zonder tijd te boeken? Het ticket wordt afgesloten.', 'Stoppen', true))
      : !(await ask(`Back-upcontrole afronden? ${s.items.length} klant(en) en ${s.afgerond} min worden geboekt op ticket ${s.ticket}, daarna wordt het ticket afgesloten.`, 'Afronden en boeken'))) return;
    if (await act('at.bk.stop', { cancel: !!cancel }, { msg: cancel ? 'Stoppen...' : 'Boeken in Autotask...' })) laad();
  };
  if (!s) {
    return (
      <div className="ticketbalk" style={{ marginBottom: 10 }}>
        <Timer size={16} /><span className="tb-t" style={{ flex: 1 }}>Geen back-upcontrole gestart. <small className="hint">Start eerst, dan wordt de tijd van alles wat je afvinkt in één intern ticket geboekt.</small></span>
        <Btn s v="p" icon={Play} onClick={start}>Back-upcontrole starten</Btn>
      </div>);
  }
  const min = s.minuten + Math.max(0, Math.floor((nu - s.t) / 60000));
  return (
    <div className="ticketbalk" style={{ marginBottom: 10, borderColor: 'var(--gr)' }}>
      <Timer size={16} style={{ color: 'var(--gr)' }} />
      <span className="tb-t" style={{ flex: 1 }}><b>Back-upcontrole loopt</b> sinds {s.sinds} · ticket {s.ticket} · {s.items.length} klant(en) afgevinkt · {min} min</span>
      <Btn s v="p" icon={Square} onClick={() => stop(false)} disabled={!s.items.length}>Afronden en boeken</Btn>
      <Btn s onClick={() => stop(true)}>Stoppen</Btn>
    </div>);
}
