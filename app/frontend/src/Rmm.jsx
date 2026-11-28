// Datto RMM: apparaten zoeken (ook op de ingelogde gebruiker), basisinformatie, en meekijken via web remote.
// Meekijken gaat altijd op een ticket (bestaand of nieuw); de tijd van de sessie wordt geboekt (per kwartier naar boven) met een
// omschrijving van de medewerker, daarna afronden of open laten.
import { useEffect, useRef, useState } from 'react';
import { Building2, CheckCircle2, ChevronDown, ChevronRight, Clock, ExternalLink, Laptop, MonitorPlay, RotateCcw, MonitorSmartphone, RefreshCw, Search, Server, Ticket, UserPlus, Wifi, WifiOff } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, openModal, toast } from './overlays.jsx';
import { Btn, Chip, Loading, SearchBox } from './ui.jsx';

// ---------------------------------------------------------------- lopende sessies (balk onderin, ook als je verder werkt)
const sessies = new Map();
const luisteraars = new Set();
const meld = () => luisteraars.forEach((f) => f([...sessies.values()]));

function sessieGestart(s) { sessies.set(s.id, { ...s, min: 0 }); meld(); }

export function MeekijkBalk() {
  const [lijst, setLijst] = useState([...sessies.values()]);
  const bezig = useRef(new Set());
  useEffect(() => { luisteraars.add(setLijst); return () => luisteraars.delete(setLijst); }, []);
  useEffect(() => {
    if (!lijst.length) return undefined;
    const t = setInterval(async () => {
      for (const s of [...sessies.values()]) {
        try {
          const r = await api('rmm.sessie', { id: s.id }, { quiet: true, achter: true });
          sessies.set(s.id, { ...s, min: r.minutes });
          if (r.ended && !bezig.current.has(s.id)) { bezig.current.add(s.id); afronden(s.id); }
        } catch { sessies.delete(s.id); }
      }
      meld();
    }, 3000);
    return () => clearInterval(t);
  }, [lijst.length]);
  const afronden = async (id) => {
    const r = await act('rmm.sessie.stop', { id }, { nobusy: true, quiet: true });
    if (!r) { bezig.current.delete(id); return; }
    const klaar = await openModal((close) => <SessieBoeken r={r} close={close} />, { wide: true });
    if (klaar) { sessies.delete(id); meld(); } else bezig.current.delete(id);
  };
  if (!lijst.length) return null;
  return (
    <div className="mk-balk">
      {lijst.map((s) => (
        <div key={s.id} className="mk-sessie">
          <MonitorPlay size={16} /><span><b>Meekijken</b> {s.device} · ticket {s.ticketNumber} · {Math.floor(s.min || 0)} min</span>
          {s.window && <Btn s icon={ExternalLink} onClick={async () => { const r = await act('rmm.sessie.browser', { id: s.id }, { nobusy: true, quiet: true }); if (r) { sessies.set(s.id, { ...sessies.get(s.id), window: false }); meld(); toast('Verder in je browser. Klik hier op Klaar als je klaar bent.', 'g'); } }}
            title="Web remote in Edge/Chrome openen: veel vloeiender; de tijd loopt door">In browser openen</Btn>}
          <Btn s icon={RotateCcw} onClick={() => act('rmm.sessie.opnieuw', { id: s.id }, { nobusy: true, quiet: true })} title="Web remote van deze pc opnieuw openen (bijv. na inloggen bij Datto)">Web remote opnieuw</Btn>
          <Btn s v="p" icon={CheckCircle2} onClick={() => { bezig.current.add(s.id); afronden(s.id); }}>Klaar</Btn>
        </div>))}
    </div>);
}

function SessieBoeken({ r, close }) {
  const s = r.session;
  const [tekst, setTekst] = useState('');
  const [sluit, setSluit] = useState('');
  const [oplossing, setOplossing] = useState('');
  const boek = async () => {
    const x = await act('rmm.sessie.boek', { id: s.id, description: tekst.trim(), close: sluit, resolution: oplossing.trim() }, { msg: 'Tijd boeken in Autotask...' });
    if (x) { toast(`${x.minutes} minuten geboekt op ticket ${s.ticketNumber}${x.closed ? ' en het ticket is afgerond' : '; het ticket blijft open'}.`, 'g'); close(true); }
  };
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Clock size={18} />Meekijken klaar: wat heb je gedaan?</h3>
      <div className="hint" style={{ marginTop: 0 }}>{s.device} · ticket <b>{s.ticketNumber}</b> {s.title}{s.company ? ` · ${s.company}` : ''}<br />
        Duur {Math.round(r.minutes)} min, geboekt als <b>{r.rounded} minuten</b> (per kwartier naar boven).</div>
      <label className="f">Wat is er gedaan? (komt bij de tijd)</label>
      <textarea rows={5} autoFocus value={tekst} onChange={(e) => setTekst(e.target.value)} placeholder="Bijv. Outlook-profiel opnieuw aangemaakt en gecontroleerd met de gebruiker." />
      <label className="f">Mag het ticket worden afgesloten?</label>
      <div className="btns">
        <Btn s v={sluit === 'complete' ? 'p' : ''} onClick={() => setSluit('complete')}>Ja, afronden (Complete)</Btn>
        <Btn s v={sluit === 'invoice' ? 'p' : ''} onClick={() => setSluit('invoice')}>Ja, klaar voor facturatie</Btn>
        <Btn s v={sluit === '' ? 'p' : ''} onClick={() => setSluit('')}>Nee, open laten (opvolgen)</Btn>
      </div>
      {sluit && <><label className="f">Oplossing (voor de klant)</label>
        <textarea rows={3} value={oplossing} onChange={(e) => setOplossing(e.target.value)} placeholder="Leeg = de omschrijving hierboven" /></>}
      <div className="foot"><button className="btn" onClick={() => close(false)}>Later</button>
        <button className="btn p" disabled={!tekst.trim()} onClick={boek}>Tijd boeken</button></div>
    </>);
}

// Voorkeur per computer: web remote in de eigen browser (sneller) of in een venster van de app
export const inBrowser = () => { try { return localStorage.getItem('mk.browser') === '1'; } catch { return false; } };
const zetInBrowser = (aan) => { try { localStorage.setItem('mk.browser', aan ? '1' : '0'); } catch { /* geen opslag */ } };

export function BrowserKeuze() {
  const [aan, setAan] = useState(inBrowser());
  return (
    <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }} title="Web remote opent dan in Edge/Chrome: veel vloeiender. De tijd boek je met Klaar in de balk onderin.">
      <input type="checkbox" checked={aan} onChange={(e) => { setAan(e.target.checked); zetInBrowser(e.target.checked); }} /> Altijd in mijn browser openen (sneller)</label>);
}

async function start(device, ticket) {
  const x = await act('rmm.sessie.start', { uid: device.uid, name: device.name, ticketId: ticket.id, ticketNumber: ticket.number, title: ticket.title, company: ticket.company || '',
    browser: false }, { msg: 'Web remote openen...' });
  if (x) {
    sessieGestart(x.session);
    toast(x.session.window ? 'Meekijken gestart. Sluit het venster als je klaar bent; dan boek je de tijd.' : 'Web remote geopend in de browser. Klik onderin op Klaar als je klaar bent.', 'g');
  }
}

// ---------------------------------------------------------------- meekijken vanaf een apparaat: eerst het ticket
export async function meekijkenApparaat(device) {
  const d = await api('rmm.apparaat', { uid: device.uid }, { quiet: true }).catch(() => ({ device, company: null }));
  const ticket = await openModal((close) => <TicketKiezen d={d} close={close} />, { wide: true });
  if (ticket) await start(d.device || device, ticket);
}

function TicketKiezen({ d, close }) {
  const [bedrijf, setBedrijf] = useState(d.company);
  const [zoek, setZoek] = useState('');
  const [bedrijven, setBedrijven] = useState([]);
  const [tickets, setTickets] = useState(null);
  const [nieuw, setNieuw] = useState(false);
  const [contacten, setContacten] = useState([]);
  const [v, setV] = useState({ contactId: '', title: '', description: '' });
  useEffect(() => {
    if (!bedrijf) return;
    api('at.tickets', { companyId: bedrijf.id, fresh: true }, { quiet: true }).then((r) => setTickets(r.tickets || [])).catch(() => setTickets([]));
    api('at.contacten', { companyId: bedrijf.id }, { quiet: true }).then((r) => setContacten(r.contacts || [])).catch(() => setContacten([]));
  }, [bedrijf]);
  useEffect(() => {
    if (bedrijf || zoek.trim().length < 2) { setBedrijven([]); return undefined; }
    const t = setTimeout(() => api('sd.bedrijven', { q: zoek.trim() }, { quiet: true }).then((r) => setBedrijven(r.companies)).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [zoek, bedrijf]);
  const maak = async () => {
    const x = await act('rmm.ticket', { companyId: bedrijf.id, contactId: v.contactId ? +v.contactId : null, title: v.title.trim(), description: v.description.trim() }, { msg: 'Ticket aanmaken...' });
    if (x) close({ ...x.ticket, company: bedrijf.name });
  };
  const dev = d.device || {};
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><MonitorPlay size={18} />Meekijken op {dev.name}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{dev.user ? `Ingelogd: ${dev.user} · ` : ''}{dev.site}. Kies het ticket waarop de tijd komt.</div>
      <label className="f">Bedrijf</label>
      {bedrijf ? <div className="btns" style={{ alignItems: 'center' }}><b>{bedrijf.name}</b>{d.company && <Chip k="g">uit Datto RMM</Chip>}
        <button className="linkknop" onClick={() => { setBedrijf(null); setTickets(null); }}>ander bedrijf</button></div> : <>
        <div className="ts-zoek"><Search size={14} /><input autoFocus value={zoek} onChange={(e) => setZoek(e.target.value)} placeholder="Zoek het bedrijf in Autotask..." /></div>
        <div style={{ display: 'grid', gap: 4, marginTop: 6 }}>{bedrijven.map((b) => <button key={b.id} type="button" className="ts-proj" onClick={() => setBedrijf(b)}><b>{b.name}</b></button>)}</div>
        {!d.company && <div className="hint">De Datto-site <b>{dev.site}</b> is niet aan een Autotask-bedrijf gekoppeld; kies het bedrijf.</div>}</>}
      {bedrijf && (nieuw ? (
        <div className="card" style={{ padding: 12, marginTop: 10 }}>
          <b>Nieuw ticket</b>
          <label className="f">Contactpersoon</label>
          <select value={v.contactId} onChange={(e) => setV({ ...v, contactId: e.target.value })} style={{ width: 'auto', minWidth: 260 }}>
            <option value="">Geen</option>{contacten.map((c) => <option key={c.id} value={c.id}>{c.name}{c.email ? ` (${c.email})` : ''}</option>)}</select>
          <label className="f">Onderwerp</label><input autoFocus value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} style={{ width: '100%' }} placeholder="Bijv. Printer installeren via meekijken" />
          <label className="f">Korte beschrijving</label><textarea rows={3} value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />
          <div className="btns" style={{ marginTop: 8 }}><Btn s onClick={() => setNieuw(false)}>Terug</Btn><Btn s v="p" icon={Ticket} disabled={!v.title.trim()} onClick={maak}>Ticket aanmaken en meekijken</Btn></div>
        </div>) : <>
        <div className="headrow" style={{ margin: '12px 0 6px' }}><b>Bestaand ticket</b><Btn s v="p" icon={UserPlus} onClick={() => setNieuw(true)}>Nieuw ticket</Btn></div>
        {!tickets ? <Loading text="Open tickets ophalen..." /> : tickets.length ? (
          <div className="list" style={{ maxHeight: 260 }}>{tickets.map((t) => (
            <div key={t.id} className="li" onClick={() => close({ ...t, company: bedrijf.name })}><span className="m"><b>{t.number}</b> {t.title}</span>{t.status && <Chip>{t.status}</Chip>}</div>))}</div>
        ) : <div className="hint">Geen open tickets bij dit bedrijf. Maak een nieuw ticket.</div>}
      </>)}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button></div>
    </>);
}

// ---------------------------------------------------------------- meekijken vanuit een ticket: eerst het apparaat
export async function meekijkenTicket(t) {
  const dev = await openModal((close) => <ApparaatKiezen t={t} close={close} />, { wide: true });
  if (dev) await start(dev, t);
}

function ApparaatKiezen({ t, close }) {
  const [q, setQ] = useState('');
  const [d, setD] = useState(null);
  useEffect(() => {
    const x = setTimeout(() => api('rmm.apparaten', { q, company: t.company }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, devices: [] })), q ? 300 : 0);
    return () => clearTimeout(x);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><MonitorPlay size={18} />Meekijken voor ticket {t.number}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{t.title}{t.company ? ` · ${t.company}` : ''}. Zoek de computer op naam of op de ingelogde gebruiker.</div>
      <SearchBox value={q} onChange={setQ} placeholder="Computernaam of gebruiker..." autoFocus />
      {!d ? <Loading text="Apparaten ophalen uit Datto RMM..." /> : d.configured === false ? <Msg kind="warn">Datto RMM is nog niet gekoppeld (app-beheerder: Servicedesk &gt; Instellingen).</Msg> : <>
        {d.error && <Msg kind="warn">{d.error}</Msg>}
        <ApparaatLijst lijst={d.devices} onKies={close} />
      </>}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button></div>
    </>);
}

function ApparaatLijst({ lijst, onKies, gekozen, kaal }) {
  if (!lijst.length) return <div className="hint" style={{ padding: 10 }}>Geen apparaten gevonden.</div>;
  return (
    <div className="list" style={kaal ? { border: 0, borderRadius: 0, margin: 0 } : { maxHeight: 420, marginTop: 6 }}>{lijst.map((x) => (
      <div key={x.uid} className={`li${gekozen === x.uid ? ' on' : ''}`} onClick={() => onKies(x)}>
        {x.type && /server/i.test(x.type) ? <Server size={15} /> : <Laptop size={15} />}
        <span className="m"><b>{x.name}</b><div className="hint" style={{ margin: 0 }}>{[x.user, kaal ? '' : x.site, x.os].filter(Boolean).join(' · ')}</div></span>
        {x.online ? <Chip k="g"><Wifi size={11} /> online</Chip> : <Chip k="mu" title={x.lastSeen ? `Laatst gezien ${x.lastSeen}` : ''}><WifiOff size={11} /> offline</Chip>}
      </div>))}</div>);
}

// Per klant (Datto-site) uitklapbaar; bij zoeken klappen de klanten met treffers vanzelf open
function ApparaatGroepen({ lijst, zoekt, onKies, gekozen }) {
  const [open, setOpen] = useState(() => new Set());
  const groepen = {};
  lijst.forEach((x) => { (groepen[x.site || 'Zonder klant'] = groepen[x.site || 'Zonder klant'] || []).push(x); });
  const namen = Object.keys(groepen).sort((a, b) => a.localeCompare(b, 'nl'));
  const allesOpen = zoekt && lijst.length <= 60;
  const wissel = (n) => setOpen((s) => { const t = new Set(s); if (t.has(n)) t.delete(n); else t.add(n); return t; });
  if (!lijst.length) return <div className="hint" style={{ padding: 10 }}>Geen apparaten gevonden.</div>;
  return (
    <>
      <div className="hint">{namen.length} klant(en) · {lijst.length} apparaat/apparaten{zoekt ? ' gevonden' : ''}
        {!allesOpen && <> · <button className="linkknop" onClick={() => setOpen(open.size ? new Set() : new Set(namen))}>{open.size ? 'alles inklappen' : 'alles uitklappen'}</button></>}</div>
      <div className="mk-groepen">
        {namen.map((n) => {
          const g = groepen[n];
          const isOpen = allesOpen || open.has(n);
          const aan = g.filter((x) => x.online).length;
          return (
            <div key={n} className="mk-groep">
              <button type="button" className="mk-kop" onClick={() => wissel(n)}>
                {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}<Building2 size={15} /><b>{n}</b>
                <span className="hint" style={{ margin: '0 0 0 auto' }}>{g.length} apparaat/apparaten</span>
                <Chip k={aan ? 'g' : 'mu'}>{aan} online</Chip>
              </button>
              {isOpen && <ApparaatLijst lijst={g} onKies={onKies} gekozen={gekozen} kaal />}
            </div>);
        })}
      </div>
    </>);
}

// ---------------------------------------------------------------- tabblad Servicedesk > Apparaten
export function Apparaten() {
  const [q, setQ] = useState('');
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(null);
  const [det, setDet] = useState(null);
  const laad = (fresh) => api('rmm.apparaten', { q, fresh: !!fresh, all: true }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, devices: [] }));
  useEffect(() => { const t = setTimeout(() => laad(false), q ? 300 : 0); return () => clearTimeout(t); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (sel) { setDet(null); api('rmm.apparaat', { uid: sel.uid }, { quiet: true }).then(setDet).catch(() => setDet({ device: sel, company: null })); } }, [sel]);
  if (d && d.configured === false) return <Msg kind="info">Datto RMM is nog niet gekoppeld. De app-beheerder doet dit onder Servicedesk &gt; Instellingen.</Msg>;
  const x = det?.device || sel;
  const rij = (l, w) => (w ? <div className="mk-rij"><span>{l}</span><b>{w}</b></div> : null);
  return (
    <div className="sd-twee">
      <div>
        <div className="btns" style={{ alignItems: 'center' }}>
          <div style={{ flex: 1 }}><SearchBox value={q} onChange={setQ} placeholder="Zoek op computernaam, ingelogde gebruiker, klant of IP..." autoFocus /></div>
          <Btn icon={RefreshCw} onClick={() => { setD(null); laad(true); }} title="Vernieuwen" />
        </div>
        {!d ? <Loading text="Apparaten ophalen uit Datto RMM..." /> : <>
          {d.error && <Msg kind="warn">{d.error}</Msg>}
          <ApparaatGroepen lijst={d.devices} zoekt={!!q.trim()} onKies={setSel} gekozen={sel?.uid} />
        </>}
      </div>
      <div>
        {!x ? <div className="hint" style={{ padding: 20 }}><MonitorSmartphone size={16} /> Kies een apparaat voor de details.</div> : (
          <div className="card" style={{ padding: 14 }}>
            <div className="headrow"><h3 style={{ margin: 0, display: 'flex', gap: 8, alignItems: 'center' }}>{x.type && /server/i.test(x.type) ? <Server size={18} /> : <Laptop size={18} />}{x.name}</h3>
              {x.online ? <Chip k="g">online</Chip> : <Chip k="mu">offline</Chip>}</div>
            {x.description && <div className="hint">{x.description}</div>}
            <div style={{ marginTop: 8 }}>
              {rij('Ingelogde gebruiker', x.user)}{rij('Klant (Datto-site)', x.site)}{rij('Autotask-bedrijf', det?.company?.name || (det ? 'niet gekoppeld' : '...'))}
              {rij('Besturingssysteem', x.os)}{rij('Soort', x.type)}{rij('Intern IP', x.ip)}{rij('Extern IP', x.extIp)}{rij('Laatst gezien', x.lastSeen)}
              {rij('Antivirus', [x.av, x.avStatus && x.avStatus !== x.av ? x.avStatus : ''].filter(Boolean).join(' · '))}{rij('Patches', x.patch)}{rij('Herstart nodig', x.reboot ? 'ja' : '')}
            </div>
            <div className="btns" style={{ marginTop: 12 }}>
              <Btn v="p" icon={MonitorPlay} disabled={!det} onClick={() => meekijkenApparaat(x)} title={x.online ? 'Web remote: meekijken op deze computer' : 'Het apparaat is offline'}>Meekijken (web remote)</Btn>
              {x.portal && <Btn onClick={() => act('open.url', { url: x.portal }, { nobusy: true, quiet: true })}>Openen in Datto RMM</Btn>}
            </div>
            {det && !det.window && <div className="hint">Web remote opent in de browser; klik onderin op Klaar als je klaar bent.</div>}
          </div>)}
      </div>
    </div>);
}
