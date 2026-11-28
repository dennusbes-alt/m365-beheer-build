// Contracten vanuit Sales (snelle invoer): vaste prijs-ticket (product + vaste prijs installatie), vaste prijs bij een project
// (bijv. migratie) en Full Service (Recurring Service-contract waar alles onder valt behalve after hours / emergency).
import { useEffect, useRef, useState } from 'react';
import { FileSignature, PackagePlus, Plus, Receipt, Search, ShieldCheck, Ticket, Trash2 } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, openModal, toast } from './overlays.jsx';
import { Btn, Chip, Loading } from './ui.jsx';
import { eur } from './Voorraad.jsx';

const naam = (p) => `${p.brand ? `${p.brand} ` : ''}${p.name}`;

function KlantZoeken({ waarde, onKies }) {
  const [zoek, setZoek] = useState('');
  const [bedr, setBedr] = useState([]);
  const t = useRef(null);
  useEffect(() => {
    clearTimeout(t.current);
    if (zoek.trim().length < 2) { setBedr([]); return undefined; }
    t.current = setTimeout(() => api('sd.bedrijven', { q: zoek.trim() }, { quiet: true }).then((r) => setBedr(r.companies)).catch(() => {}), 300);
    return () => clearTimeout(t.current);
  }, [zoek]);
  if (waarde) return <div className="btns" style={{ alignItems: 'center' }}><b>{waarde.name}</b><button className="linkknop" onClick={() => onKies(null)}>andere klant</button></div>;
  return (
    <>
      <div className="ts-zoek"><Search size={14} /><input autoFocus value={zoek} onChange={(e) => setZoek(e.target.value)} placeholder="Zoek klant in Autotask..." /></div>
      <div style={{ display: 'grid', gap: 4, marginTop: 6 }}>{bedr.map((b) => <button key={b.id} type="button" className="ts-proj" onClick={() => onKies(b)}><b>{b.name}</b></button>)}</div>
    </>);
}

// ================================================================ vaste prijs-ticket (bijv. Nieuwe computer = product + 2 uur installatie)
export async function vastePrijsTicket() {
  const r = await openModal((close) => <VastePrijs close={close} />, { wide: true });
  if (!r) return null;
  const x = await act('sa.vasteprijs', r, { msg: 'Contract, ticket en producten aanmaken in Autotask...' });
  if (x) {
    toast(`Ticket ${x.ticket.number} aangemaakt${x.contract ? ' met vaste prijs-contract' : ''}.${x.ordered?.length ? ` Op de bestellijst: ${x.ordered.join(', ')}.` : ''}${x.errors?.length ? ` Niet gelukt: ${x.errors.join('; ')}` : ''}`,
      x.errors?.length ? 'e' : 'g');
    if (x.contract?.milestoneError) toast(`De vaste prijs (mijlpaal) kon niet aan het contract worden toegevoegd: ${x.contract.milestoneError}`, 'e');
  }
  return x;
}

function VastePrijs({ close }) {
  const [klant, setKlant] = useState(null);
  const [contacten, setContacten] = useState([]);
  const [opt, setOpt] = useState(null);
  const [prods, setProds] = useState(null);
  const [v, setV] = useState({ contactId: '', title: '', description: '', hours: 2, amount: '', assign: 'queue' });
  const [regels, setRegels] = useState([]);   // [{p, qty}]
  const [q, setQ] = useState('');
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  useEffect(() => {
    api('vr.overzicht', {}, { quiet: true }).then((r) => setProds(r.products)).catch(() => setProds([]));
    api('sa.contract.opties', {}, { quiet: true }).then(setOpt).catch(() => setOpt({}));
  }, []);
  useEffect(() => { if (klant) api('at.contacten', { companyId: klant.id }, { quiet: true }).then((r) => setContacten(r.contacts || [])).catch(() => setContacten([])); }, [klant]);
  // Standaard vaste prijs = uren x tarief (als het tarief bekend is), daarna vrij aan te passen
  const tarief = opt?.rate;
  const voorstel = tarief ? Math.round(Number(v.hours || 0) * tarief * 100) / 100 : '';
  const bedrag = v.amount === '' ? voorstel : v.amount;
  const producten = regels.reduce((s, r) => s + r.p.price * (parseInt(r.qty, 10) || 1), 0);
  const gevonden = (prods || []).filter((p) => q && `${p.brand} ${p.name} ${p.model} ${p.sku}`.toLowerCase().includes(q.toLowerCase())).slice(0, 8);
  const ok = klant && v.title.trim();
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Receipt size={18} />Vaste prijs-ticket</h3>
      <div className="hint" style={{ marginTop: 0 }}>Bijvoorbeeld <b>Nieuwe computer</b> = de computer uit de voorraad + installatie voor een vaste prijs. De app maakt een vaste prijs-contract (nooit het standaardcontract), het ticket op dat contract en zet de producten erop. Uren op dit ticket worden niet apart gefactureerd.</div>
      <label className="f">Klant</label>
      <KlantZoeken waarde={klant} onKies={(b) => { setKlant(b); setContacten([]); setV({ ...v, contactId: '' }); }} />
      {klant && <>
        <label className="f">Contactpersoon</label>
        <select value={v.contactId} onChange={z('contactId')} style={{ width: 'auto', minWidth: 260 }}>
          <option value="">Geen</option>{contacten.map((c) => <option key={c.id} value={c.id}>{c.name}{c.email ? ` (${c.email})` : ''}</option>)}
        </select></>}
      <label className="f">Onderwerp</label>
      <input value={v.title} onChange={z('title')} placeholder="Bijv. Nieuwe computer receptie" style={{ width: '100%' }} />
      <label className="f">Producten uit de voorraad</label>
      {regels.map((r, i) => (
        <div key={r.p.id} style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '4px 0' }}>
          <input type="number" min={1} value={r.qty} onChange={(e) => setRegels(regels.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))} style={{ width: 70 }} />
          <span style={{ flex: 1 }}>{naam(r.p)} · {eur(r.p.price)} p/st {r.p.stock < (parseInt(r.qty, 10) || 1) && <Chip k="o">niet genoeg op voorraad: komt op de bestellijst</Chip>}</span>
          <Btn s icon={Trash2} onClick={() => setRegels(regels.filter((_, j) => j !== i))} />
        </div>))}
      {prods === null ? <Loading text="Voorraad ophalen..." /> : (
        <div style={{ position: 'relative' }}>
          <div className="ts-zoek"><PackagePlus size={14} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Product zoeken en toevoegen..." /></div>
          {gevonden.length > 0 && <div style={{ display: 'grid', gap: 4, marginTop: 4 }}>{gevonden.map((p) => (
            <button key={p.id} type="button" className="ts-proj" onClick={() => { setRegels((l) => (l.some((x) => x.p.id === p.id) ? l : [...l, { p, qty: 1 }])); setQ(''); }}>
              <b>{naam(p)}</b> · {eur(p.price)} · {p.stock > 0 ? `${p.stock} op voorraad` : 'niet op voorraad'}</button>))}</div>}
        </div>)}
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Installatie (uren)</label><input type="number" step="0.25" min={0} value={v.hours} onChange={z('hours')} style={{ width: 110 }} /></div>
        <div><label className="f">Vaste prijs installatie (excl. btw)</label><input type="number" step="0.01" value={bedrag} onChange={z('amount')} style={{ width: 170 }} placeholder="0 = geen vaste prijs" /></div>
        <div style={{ alignSelf: 'flex-end', paddingBottom: 8 }}>{tarief ? <span className="hint" style={{ margin: 0 }}>voorstel {v.hours || 0} x {eur(tarief)} · </span> : null}
          Totaal <b>{eur(Number(bedrag || 0) + producten)}</b> excl. btw</div>
      </div>
      <label className="f">Omschrijving / afspraken (optioneel)</label>
      <textarea rows={3} value={v.description} onChange={z('description')} placeholder="Wat is er afgesproken, wanneer, waar?" />
      <label className="f">Ticket</label>
      <div className="btns">
        <Btn s v={v.assign === 'queue' ? 'p' : ''} onClick={() => setV({ ...v, assign: 'queue' })}>In de servicedeskqueue</Btn>
        <Btn s v={v.assign === 'me' ? 'p' : ''} onClick={() => setV({ ...v, assign: 'me' })}>Op mijn naam</Btn>
      </div>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!ok} onClick={() => close({ companyId: klant.id, contactId: v.contactId ? +v.contactId : null, title: v.title.trim(), description: v.description,
          hours: Number(v.hours || 0), amount: Number(bedrag || 0), assign: v.assign, products: regels.map((r) => ({ productId: r.p.id, qty: Math.max(1, parseInt(r.qty, 10) || 1) })) })}>
          <Ticket size={14} /> Aanmaken</button></div>
    </>);
}

// ================================================================ contracten bij een kans (klant): vaste prijs voor het project, Full Service
export function ContractKaart({ o, mag }) {
  const [d, setD] = useState(null);
  const [vorm, setVorm] = useState(null);   // 'fixed' | 'full'
  const laad = () => (o.companyId ? api('sa.contract.opties', { companyId: o.companyId, opportunityId: o.id }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, contracts: [] })) : null);
  useEffect(() => { laad(); }, [o.companyId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!o.companyId) return null;
  return (
    <>
      <div className="headrow" style={{ margin: '0 0 6px' }}><b style={{ display: 'flex', gap: 6, alignItems: 'center' }}><FileSignature size={15} /> Contracten van {o.company}</b></div>
      {!d ? <Loading text="Contracten ophalen..." /> : <>
        {d.error && <Msg kind="warn">{d.error}</Msg>}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
          {d.fullService ? <Chip k="g"><ShieldCheck size={11} /> Full Service-klant</Chip> : <Chip k="mu">geen Full Service-contract</Chip>}
          {d.projectContract && <Chip k="g" title="Het project van deze kans krijgt dit contract">vaste prijs voor het project vastgelegd</Chip>}
        </div>
        {(d.contracts || []).map((c) => (
          <div key={c.id} className="hint" style={{ margin: '2px 0' }}><b>{c.name}</b> · {c.type}{c.default ? ' · standaardcontract' : ''} · {c.start} t/m {c.end}{c.amount ? ` · ${eur(c.amount)}` : ''}</div>))}
        {mag && !vorm && (
          <div className="btns" style={{ marginTop: 8 }}>
            {!d.projectContract && <Btn s icon={Plus} onClick={() => setVorm('fixed')}>Vaste prijs-contract voor het project</Btn>}
            {!d.fullService && <Btn s icon={ShieldCheck} onClick={() => setVorm('full')}>Full Service-contract</Btn>}
          </div>)}
        {vorm === 'fixed' && <VastProject o={o} close={(ok) => { setVorm(null); if (ok) laad(); }} />}
        {vorm === 'full' && <FullService o={o} uitgesloten={d.excluded || []} close={(ok) => { setVorm(null); if (ok) laad(); }} />}
      </>}
    </>);
}

function VastProject({ o, close }) {
  const [v, setV] = useState({ name: `Vaste prijs - ${o.title}`.slice(0, 100), amount: '', hours: '', months: 3 });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  const maak = async () => {
    const x = await act('sa.contract.vast', { companyId: o.companyId, opportunityId: o.id, name: v.name.trim(), amount: Number(v.amount), hours: Number(v.hours || 0), months: Number(v.months || 3),
      description: o.description || '' }, { msg: 'Vaste prijs-contract aanmaken...' });
    if (x) { toast(x.project ? `Contract aangemaakt en gekoppeld aan project ${x.project}.` : 'Contract aangemaakt; het project van deze kans krijgt dit contract.', 'g'); close(true); }
  };
  return (
    <div className="card" style={{ padding: 12, marginTop: 8 }}>
      <b>Vaste prijs voor het project</b>
      <div className="hint" style={{ marginTop: 2 }}>Bijv. een afgesproken migratieprijs. Fixed Price-contract met de vaste prijs als mijlpaal, gekoppeld aan het project. Nooit het standaardcontract.</div>
      <label className="f">Naam</label><input value={v.name} onChange={z('name')} style={{ width: '100%' }} />
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Vaste prijs (excl. btw)</label><input type="number" step="0.01" autoFocus value={v.amount} onChange={z('amount')} style={{ width: 150 }} /></div>
        <div><label className="f">Geschatte uren</label><input type="number" step="0.5" value={v.hours} onChange={z('hours')} style={{ width: 110 }} /></div>
        <div><label className="f">Looptijd (maanden)</label><input type="number" min={1} value={v.months} onChange={z('months')} style={{ width: 110 }} /></div>
      </div>
      <div className="btns" style={{ marginTop: 8 }}><Btn s onClick={() => close(false)}>Annuleren</Btn><Btn s v="p" disabled={!(Number(v.amount) > 0) || !v.name.trim()} onClick={maak}>Contract maken</Btn></div>
    </div>);
}

function FullService({ o, uitgesloten, close }) {
  const eerste = new Date(); eerste.setDate(1);
  const [cfg, setCfg] = useState(STANDAARD_CFG);
  const [per, setPer] = useState({ start: eerste.toISOString().slice(0, 10), months: 12 });
  const maak = async () => {
    const x = await act('sa.contract.samenstellen', { companyId: o.companyId, companyName: o.company, cfg, ...per }, { msg: 'Full Service-contract samenstellen in Autotask...' });
    if (x) { toast(`Full Service-contract aangemaakt (${eur(x.calc.monthly)} per maand, setup ${eur(x.calc.setup)})${x.excluded.length ? `; buiten het contract: ${x.excluded.join(', ')}` : ''}.${x.errors.length ? ` Let op: ${x.errors.join('; ')}` : ''}`, x.errors.length ? 'e' : 'g'); close(true); }
  };
  return (
    <div className="card" style={{ padding: 12, marginTop: 8 }}>
      <b>Full Service-contractklant: {`Full Service - ${o.company}`}</b>
      <div className="hint" style={{ marginTop: 2 }}>Recurring Service-contract als standaardcontract: al het servicedeskwerk valt eronder, behalve after hours / emergency{uitgesloten.length ? ` (${uitgesloten.map((u) => u.name).join(', ')})` : ''}. Elk onderdeel wordt een dienst met aantal en prijs; ontbrekende diensten maakt de app aan in Autotask.</div>
      <Samensteller cfg={cfg} onChange={setCfg} periode={per} onPeriode={setPer} />
      <div className="btns" style={{ marginTop: 8 }}><Btn s onClick={() => close(false)}>Annuleren</Btn><Btn s v="p" onClick={maak}>Contract maken</Btn></div>
    </div>);
}

// ================================================================ contract samenstellen zoals de offertepagina (pakket, servers, DMARC, licenties)
export const STANDAARD_CFG = { users: 5, hasServers: false, servers: 1, level: 'none', dmarc: false, domains: 1, licenses: {} };

export function Samensteller({ cfg, onChange, periode, onPeriode }) {
  const [p, setP] = useState(null);
  const t = useRef(null);
  useEffect(() => {
    clearTimeout(t.current);
    t.current = setTimeout(() => api('sa.prijzen', { cfg }, { quiet: true }).then(setP).catch((e) => setP((x) => ({ ...(x || {}), error: e.message }))), p ? 250 : 0);
    return () => clearTimeout(t.current);
  }, [JSON.stringify(cfg)]); // eslint-disable-line react-hooks/exhaustive-deps
  const z = (k, w) => onChange({ ...cfg, [k]: w });
  const lic = (k, soort, w) => onChange({ ...cfg, licenses: { ...cfg.licenses, [k]: { ...(cfg.licenses[k] || {}), [soort]: Math.max(0, parseInt(w, 10) || 0) } } });
  if (!p) return <Loading text="Prijzen van de offertepagina ophalen..." />;
  const c = p.calc || { lines: [] };
  const inbegrepen = p.included?.[cfg.level] || {};
  return (
    <div className="sm-raster">
      <div>
        {p.error && <Msg kind="warn">{p.error}</Msg>}
        <div className="hint" style={{ marginTop: 0 }}>Prijzen en berekening zoals op de <button className="linkknop" onClick={() => act('open.url', { url: p.site }, { nobusy: true, quiet: true })}>offertepagina</button>
          {p.source !== 'site' && <b> (offertepagina niet bereikbaar: {p.source === 'bewaard' ? 'laatst gelezen prijzen' : 'standaardprijzen'})</b>}.</div>
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Aantal gebruikers</label><input type="number" min={1} max={150} value={cfg.users} onChange={(e) => z('users', Math.max(1, parseInt(e.target.value, 10) || 1))} style={{ width: 110 }} /></div>
          <div><label className="f">Servers</label>
            <div className="btns" style={{ alignItems: 'center' }}><label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={cfg.hasServers} onChange={(e) => z('hasServers', e.target.checked)} /> Heeft servers</label>
              {cfg.hasServers && <input type="number" min={1} value={cfg.servers} onChange={(e) => z('servers', Math.max(1, parseInt(e.target.value, 10) || 1))} style={{ width: 80 }} />}</div></div>
        </div>
        <label className="f">Beveiligingsniveau</label>
        <div className="btns">{Object.entries(p.levels).map(([k, l]) => <Btn key={k} s v={cfg.level === k ? 'p' : ''} onClick={() => z('level', k)}>{l}</Btn>)}</div>
        {cfg.level === 'none' && (
          <div className="btns" style={{ alignItems: 'center', marginTop: 6 }}>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={cfg.dmarc} onChange={(e) => z('dmarc', e.target.checked)} /> EasyDMARC-bescherming</label>
            {cfg.dmarc && <>domeinen <input type="number" min={1} value={cfg.domains} onChange={(e) => z('domains', Math.max(1, parseInt(e.target.value, 10) || 1))} style={{ width: 70 }} /></>}
          </div>)}
        <label className="f">Microsoft 365-licenties (aantal)</label>
        <table className="sm-lic"><thead><tr><th>Licentie</th><th style={{ textAlign: 'right' }}>Jaar (p/m)</th><th>Aantal</th><th style={{ textAlign: 'right' }}>Maand (p/m)</th><th>Aantal</th></tr></thead>
          <tbody>{Object.entries(p.licenses).map(([k, l]) => (
            <tr key={k}><td>{l.name}</td><td style={{ textAlign: 'right' }}>{eur(l.year)}</td>
              <td><input type="number" min={0} value={cfg.licenses[k]?.yearly || 0} onChange={(e) => lic(k, 'yearly', e.target.value)} style={{ width: 70 }} /></td>
              <td style={{ textAlign: 'right' }}>{eur(l.flex)}</td>
              <td><input type="number" min={0} value={cfg.licenses[k]?.flexible || 0} onChange={(e) => lic(k, 'flexible', e.target.value)} style={{ width: 70 }} /></td></tr>))}</tbody></table>
        {periode && <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Start contract</label><input type="date" value={periode.start} onChange={(e) => onPeriode({ ...periode, start: e.target.value })} style={{ width: 160 }} /></div>
          <div><label className="f">Looptijd (maanden)</label><input type="number" min={1} value={periode.months} onChange={(e) => onPeriode({ ...periode, months: Math.max(1, parseInt(e.target.value, 10) || 12) })} style={{ width: 110 }} /></div>
        </div>}
      </div>
      <div className="sm-offerte">
        <div className="sm-kop">{c.levelName || 'Basis pakket'}</div>
        {c.lines.map((l) => <div key={l.key} className="sm-regel"><span>{l.qty > 1 || l.unit !== 'organisatie' ? `${l.qty}x ` : ''}{l.name.replace(/ - per (organisatie|gebruiker|server)$/, (x) => x)}</span><b>{eur(l.amount)}</b></div>)}
        <div className="sm-totaal"><span>Totaal per maand</span><b>{eur(c.monthly)}</b></div>
        <div className="sm-regel"><span>Eenmalige setup ({cfg.users}x {eur(c.setupPerUser)}{c.dmarcSetup ? ` + DMARC ${eur(c.dmarcSetup)}` : ''})</span><b>{eur(c.setup)}</b></div>
        <div className="hint">Excl. btw · staffel {c.tier === 'small' ? '1-10' : c.tier === 'medium' ? '11-50' : '51-150'} gebruikers{c.countedUsers > cfg.users ? ` (minimaal ${c.countedUsers} gebruikers gerekend)` : ''}</div>
        <div className="sm-kop" style={{ marginTop: 10 }}>Inbegrepen</div>
        {['org', 'user', 'server'].filter((k) => inbegrepen[k]).map((k) => (
          <div key={k} style={{ marginBottom: 6 }}><div className="hint" style={{ margin: 0 }}>{{ org: 'Per organisatie', user: 'Per gebruiker', server: 'Per server' }[k]}</div>
            {inbegrepen[k].map((x) => <div key={x} className="sm-incl">✓ {x}</div>)}</div>))}
        {cfg.level !== 'none' && <div className="hint">Plus alles uit het Basis pakket.</div>}
        <div className="hint">After hours / emergency vallen buiten het contract.</div>
      </div>
    </div>);
}
