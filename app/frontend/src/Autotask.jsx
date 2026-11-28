// Autotask: ticketbalk (per klant), werklog en de instellingen (tabblad op het startscherm).
import { useEffect, useRef, useState } from 'react';
import { FolderKanban, Users, Building2, Check as CheckIcon, ChevronLeft, ChevronRight, Clock, Link2, ListChecks, RefreshCw, Search, Settings, SkipForward, Ticket, Trash2, User, UserPlus, UserX, Wand, X } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox } from './ui.jsx';

const kwartier = (m) => (m > 0 ? Math.max(1, Math.ceil(m / 15)) * 15 : 0);
const uren = (m) => (m >= 60 ? `${Math.floor(m / 60)}u${m % 60 ? ` ${m % 60}m` : ''}` : `${m} min`);

// Afrondkeuze: incidenten -> Complete, licentiewijzigingen -> Ready to Invoice (de administratie valideert en factureert)
export const EIND = [['complete', 'Afgerond (Complete)', 'Incident of vraag is opgelost'],
  ['invoice', 'Klaar voor facturatie (Ready to Invoice)', 'Licentie erbij of eraf: de administratie valideert en factureert']];
export function EindKeuze({ value, onChange }) {
  return (
    <div className="btns" style={{ margin: 0 }}>
      {EIND.map(([k, l, d]) => (
        <button key={k} type="button" className={'btn s' + (value === k ? ' p' : '')} onClick={() => onChange(k)} title={d}>{l}</button>))}
    </div>
  );
}

function Afronden({ licentie, close }) {
  const [sluit, setSluit] = useState(licentie ? 'invoice' : 'complete');
  const [res, setRes] = useState('');
  const ok = res.trim().length >= 5;
  return (
    <>
      <h3>Boeken en ticket afronden</h3>
      {licentie && <Msg kind="info">Er zijn licenties gewijzigd: het ticket gaat standaard naar Klaar voor facturatie (Ready to Invoice), zodat de administratie het kan valideren en factureren.</Msg>}
      <label className="f">Hoe rond je het ticket af?</label>
      <EindKeuze value={sluit} onChange={setSluit} />
      <label className="f" style={{ marginTop: 12 }}>Oplossing (komt in het ticket)</label>
      <textarea rows={4} autoFocus value={res} onChange={(e) => setRes(e.target.value)} placeholder="Wat is er opgelost of gewijzigd?" />
      <div className="foot">
        <button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!ok} onClick={() => close({ sluit, resolution: res.trim() })}>{sluit === 'invoice' ? 'Boeken en klaar voor facturatie' : 'Boeken en afronden'}</button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- Ticketbalk (boven elk scherm bij een klant)
export function TicketBalk({ info }) {
  const [st, setSt] = useState(null);
  const timer = useRef(null);
  const laad = async () => {
    try { setSt(await api('at.status', {}, { quiet: true })); } catch { setSt(null); }
    clearTimeout(timer.current);
    timer.current = setTimeout(laad, 8000);
  };
  useEffect(() => { laad(); return () => clearTimeout(timer.current); }, [info.tenantId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!st || !st.configured || !st.session) return null;
  const s = st.session;
  const open = s.items.filter((i) => !i.skip);
  const kiezen = async () => { if (await openModal((close) => <TicketKiezen info={info} st={st} close={close} />, { wide: true })) laad(); };
  const werklog = async () => { if ((await openModal((close) => <Werklog close={close} />, { wide: true })) === 'boeken') return boeken(); laad(); };
  // Contactpersoon kiezen/wijzigen; geeft false bij annuleren
  const contactKiezen = async () => {
    const k = await kiesContact(info);
    if (!k) return false;
    await act('at.sessie.contact', { contact: k.contact }, { quiet: true });
    laad();
    return true;
  };
  const autoTicket = async () => {
    const k = await kiesContact(info);
    if (!k) return;
    await act('at.sessie.set', { mode: 'auto', contact: k.contact }, { quiet: true });
    laad();
  };
  const boeken = async () => {
    // Automatisch ticket dat nog gemaakt moet worden: eerst vragen van wie de aanvraag komt
    if (s.mode === 'auto' && !s.ticket && !s.contactGekozen && !(await contactKiezen())) return;
    await act('at.boek', {}, { msg: 'Boeken in Autotask...' });
    laad();
  };
  // Boeken en het ticket meteen afronden: Complete (incident) of Ready to Invoice (licentiewijziging, voor de factuur)
  const afronden = async () => {
    if (s.mode === 'auto' && !s.ticket && !s.contactGekozen && !(await contactKiezen())) return;
    const k = await openModal((close) => <Afronden licentie={s.licentie} close={close} />);
    if (!k) return;
    const r = await act('at.boek', { sluit: k.sluit, resolution: k.resolution }, { msg: 'Boeken en afsluiten in Autotask...' });
    if (r && r.closed) toast(r.closed === 'invoice' ? 'Ticket staat op klaar voor facturatie (Ready to Invoice).' : 'Ticket afgerond (Complete).', 'g');
    laad();
  };
  const contactChip = s.mode === 'auto' && (
    <button className={'tb-chip' + (s.contactGekozen ? '' : ' let')} onClick={contactKiezen} title="Contactpersoon van het ticket kiezen of wijzigen">
      {s.contact ? <User size={13} /> : <UserX size={13} />}
      {s.contactGekozen ? (s.contact ? s.contact.name : 'Geen contactpersoon') : 'Contactpersoon kiezen'}</button>);
  const skip = async () => { await act('at.sessie.set', { mode: 'skip' }, { quiet: true }); laad(); };

  let inhoud;
  if (s.mode === 'ticket' && s.ticket) {
    inhoud = s.ticket.soort === 'taak'
      ? <><FolderKanban size={16} /><span className="tb-t"><b>{s.ticket.project || 'Project'}</b> · taak: {s.ticket.title}</span></>
      : <><Ticket size={16} /><span className="tb-t"><b>{s.ticket.number}</b> {s.ticket.title}</span></>;
  } else if (s.mode === 'auto') {
    inhoud = <><Wand size={16} /><span className="tb-t"><b>Automatisch ticket</b>{s.ticket ? ` · ${s.ticket.number}` : ' · wordt aangemaakt bij het boeken'}</span></>;
  } else if (s.mode === 'skip') {
    inhoud = <><SkipForward size={16} /><span className="tb-t">Niet registreren in Autotask</span></>;
  } else {
    inhoud = <><Ticket size={16} /><span className="tb-t">{open.length ? <b>{open.length} actie(s) wachten op een ticket</b> : 'Geen ticket gekozen'}</span></>;
  }
  const aandacht = !s.mode && open.length > 0;
  return (
    <div className={'ticketbalk' + (aandacht ? ' let' : '') + (s.mode === 'skip' ? ' uit' : '')}>
      {inhoud}
      {contactChip}
      {s.mode !== 'skip' && open.length > 0 && (
        <button className="tb-chip" onClick={werklog} title="Werklog bekijken en aanpassen">
          <Clock size={13} />{open.length} actie(s) · {uren(s.afgerond)}</button>)}
      {s.fout && <span className="tb-fout" title={s.fout}>Boeken mislukt: {s.fout.slice(0, 80)}</span>}
      <span className="tb-knoppen">
        {!s.mode && open.length > 0 && <Btn s v="p" icon={Wand} onClick={autoTicket}>Automatisch ticket</Btn>}
        {(s.mode === 'ticket' || s.mode === 'auto') && open.length > 0 && <Btn s v="p" icon={CheckIcon} onClick={boeken}>Nu boeken</Btn>}
        {((s.mode === 'ticket' && s.ticket && s.ticket.soort !== 'taak') || (s.mode === 'auto' && (s.ticket || open.length > 0))) && (
          <Btn s v={open.length > 0 ? 'p' : undefined} icon={CheckIcon} onClick={afronden}
            title="Boeken en het ticket afronden: Afgerond (Complete) of Klaar voor facturatie (Ready to Invoice)">
            {s.licentie ? 'Afronden: klaar voor facturatie' : 'Ticket afronden'}</Btn>)}
        <Btn s icon={Link2} onClick={kiezen}>{s.mode ? 'Wijzigen' : 'Ticket kiezen'}</Btn>
        {!s.mode && <Btn s icon={SkipForward} onClick={skip} title="Regulier beheer zonder ticket">Overslaan</Btn>}
      </span>
    </div>
  );
}

function TicketKiezen({ info, st, close }) {
  const [bedrijf, setBedrijf] = useState(st.company || null);
  const [q, setQ] = useState('');
  const [tickets, setTickets] = useState(null);
  const [nummer, setNummer] = useState('');
  const [tab, setTab] = useState('tickets');
  const [taken, setTaken] = useState(null);
  // Bekende lijst direct tonen; was die al wat ouder ('stale'), dan meteen de verse lijst erachteraan
  const laadLijst = async (naam, veld, zet, zoek) => {
    const body = zoek ? { q: zoek } : {};
    const pak = (r) => (veld ? r[veld] : { tasks: r.tasks || [], projects: r.projects || [] });
    try {
      const r = await api(naam, body, { quiet: true });
      zet(pak(r));
      if (r.stale) zet(pak(await api(naam, { ...body, fresh: true }, { quiet: true })));
    } catch (e) { toast(e.message, 'e'); zet((x) => x || (veld ? [] : { tasks: [], projects: [] })); }
  };
  const laadTickets = (zoek) => { setTickets(null); return laadLijst('at.tickets', 'tickets', setTickets, zoek); };
  // Projecttaken: alles in één keer ophalen; zoeken en project kiezen gebeurt direct in de interface
  const laadTaken = () => { setTaken(null); return laadLijst('at.taken', null, setTaken); };
  const [project, setProject] = useState(null);
  // Tickets en projecttaken tegelijk ophalen, zodat wisselen tussen de tabbladen direct is
  useEffect(() => { if (bedrijf) { laadTickets(); laadTaken(); } }, [bedrijf]); // eslint-disable-line react-hooks/exhaustive-deps
  const zoek = () => (tab === 'taken' ? null : laadTickets(q));
  // Projecten en taken filteren op de zoektekst (projectnaam/-nummer of taaknaam)
  const zq = q.trim().toLowerCase();
  const takenVan = (pid) => (taken ? taken.tasks.filter((t) => t.projectId === pid) : []);
  const pTreft = (p) => !zq || `${p.name} ${p.number}`.toLowerCase().includes(zq);
  const tTreft = (t) => !zq || `${t.title} ${t.number}`.toLowerCase().includes(zq);
  const projecten = taken ? taken.projects.filter((p) => pTreft(p) || takenVan(p.id).some(tTreft)) : null;
  const projTaken = project ? takenVan(project.id).filter((t) => pTreft(project) || tTreft(t)) : [];
  const kies = async (t) => { if (await act('at.sessie.set', { mode: 'ticket', ticket: t }, { msg: t.soort === 'taak' ? 'Projecttaak koppelen...' : 'Ticket koppelen...' })) close(true); };
  const modus = async (m, extra = {}) => { if (await act('at.sessie.set', { mode: m, ...extra }, { quiet: true })) close(true); };
  const [stap, setStap] = useState('');
  if (bedrijf && stap === 'contact') {
    return (
      <>
        <h3>Contactpersoon voor het automatische ticket</h3>
        <ContactStap info={info} onKies={(c) => modus('auto', { contact: c })} onTerug={() => setStap('')} />
      </>
    );
  }
  const zoekNummer = async () => {
    if (!/^T\d{8}\.\d+$/i.test(nummer.trim())) return toast('Gebruik een ticketnummer zoals T20261126.0042', 'e');
    const r = await api('at.tickets', { q: nummer.trim() }, { quiet: true }).catch((e) => { toast(e.message, 'e'); return null; });
    if (r && r.tickets.length) kies(r.tickets[0]); else if (r) toast('Ticket niet gevonden.', 'e');
  };
  return (
    <>
      <h3>Werk registreren voor {info.tenant}</h3>
      {!bedrijf ? <BedrijfKoppelen info={info} onGekoppeld={setBedrijf} /> : (
        <>
          <div className="hint" style={{ marginTop: 0 }}><Building2 size={13} style={{ verticalAlign: -2 }} /> Autotask-bedrijf: <b>{bedrijf.name}</b>{' '}
            <button className="linkknop" onClick={() => setBedrijf(null)}>wijzigen</button></div>
          <div className="keuzes">
            <button className="keuze" onClick={() => setStap('contact')}><Wand size={20} /><b>Automatisch nieuw ticket</b><small>Bij het boeken maakt de app een ticket met een passend onderwerp, op jouw naam. Je kiest eerst de contactpersoon.</small></button>
            <button className="keuze" onClick={() => modus('skip')}><SkipForward size={20} /><b>Niet registreren</b><small>Regulier beheer zonder ticket; er wordt niets gelogd.</small></button>
          </div>
          <div className="tabs" style={{ marginTop: 14 }}>
            <button className={`tab ${tab === 'tickets' ? 'on' : ''}`} onClick={() => setTab('tickets')}><Ticket size={14} /> Bestaand ticket{tickets ? ` (${tickets.length})` : ''}</button>
            <button className={`tab ${tab === 'taken' ? 'on' : ''}`} onClick={() => setTab('taken')}><FolderKanban size={14} /> Projecttaak{taken ? ` (${taken.projects.length} project${taken.projects.length === 1 ? '' : 'en'})` : ''}</button>
          </div>
          <div className="row" style={{ alignItems: 'center', marginTop: 8 }}>
            <SearchBox value={q} onChange={setQ} placeholder={tab === 'taken' ? (project ? 'Zoek een taak in dit project...' : 'Zoek op project of taak...') : 'Zoek in open tickets van deze klant (Enter)...'} onKeyDown={(e) => e.key === 'Enter' && zoek()} />
            {tab === 'tickets' && <div className="n" style={{ display: 'flex', gap: 6 }}>
              <input type="text" value={nummer} onChange={(e) => setNummer(e.target.value)} placeholder="T20261126.0042" style={{ width: 160 }} onKeyDown={(e) => e.key === 'Enter' && zoekNummer()} />
              <Btn s icon={Search} onClick={zoekNummer}>Nummer</Btn></div>}
          </div>
          {tab === 'tickets' ? (
            <div className="list" style={{ maxHeight: 320, marginTop: 8 }}>
              {!tickets ? <Loading text="Open tickets ophalen..." /> : tickets.length ? tickets.map((t) => (
                <div key={t.id} className="li" onClick={() => kies(t)} style={{ cursor: 'pointer' }}>
                  <Ticket size={15} style={{ color: 'var(--hd)', flex: 'none' }} />
                  <span className="m"><b>{t.number}</b> {t.title}<small>{t.status}{t.created ? ` · ${t.created.split('-').reverse().join('-')}` : ''}{t.mine ? ' · op jouw naam' : ''}</small></span>
                </div>)) : <div className="li empty">Geen open tickets gevonden.</div>}
            </div>
          ) : !project ? (
            // Stap 1: project kiezen
            <div className="list" style={{ maxHeight: 320, marginTop: 8 }}>
              {!projecten ? <Loading text="Open projecten ophalen..." /> : projecten.length ? projecten.map((p) => (
                <div key={p.id} className="li" onClick={() => { setProject(p); setQ(''); }} style={{ cursor: 'pointer' }}>
                  <FolderKanban size={15} style={{ color: 'var(--hd)', flex: 'none' }} />
                  <span className="m"><b>{p.name}</b><small>{[p.number, p.status].filter(Boolean).join(' · ')}</small></span>
                  <span className="n" style={{ color: p.open ? 'var(--hd)' : 'var(--mu2)', whiteSpace: 'nowrap', fontSize: 13 }}>
                    {p.open ? `${p.open} open ${p.open === 1 ? 'taak' : 'taken'}` : 'geen open taken'} <ChevronRight size={14} style={{ verticalAlign: -2 }} /></span>
                </div>)) : <div className="li empty">{zq ? 'Geen project of taak gevonden.' : 'Geen open projecten bij deze klant.'}</div>}
            </div>
          ) : (
            // Stap 2: taak binnen het gekozen project; terug naar de projecten blijft altijd mogelijk
            <>
              <div style={{ display: 'flex', alignItems: 'center', marginTop: 8, gap: 10 }}>
                <Btn s icon={ChevronLeft} onClick={() => { setProject(null); setQ(''); }}>Ander project</Btn>
                <span style={{ minWidth: 0 }}><b>{project.name}</b>{project.number ? <small style={{ color: 'var(--mu)' }}> ({project.number})</small> : null}</span>
              </div>
              <div className="list" style={{ maxHeight: 280, marginTop: 8 }}>
                {projTaken.length ? projTaken.map((t) => (
                  <div key={t.id} className="li" onClick={() => kies(t)} style={{ cursor: 'pointer' }}>
                    <ListChecks size={15} style={{ color: 'var(--hd)', flex: 'none' }} />
                    <span className="m"><b>{t.title}</b><small>{[t.number !== project.number && t.number, t.status, t.mine && 'op jouw naam'].filter(Boolean).join(' · ')}</small></span>
                  </div>)) : <div className="li empty">{zq ? 'Geen taak gevonden in dit project.' : 'Dit project heeft geen open taken.'}</div>}
              </div>
            </>
          )}
          <div className="hint">Acties en tijd worden geboekt op het gekozen ticket of de projecttaak, op jouw naam (per kwartier naar boven).</div>
        </>
      )}
      <div className="foot"><button className="btn" onClick={() => close(false)}>Sluiten</button></div>
    </>
  );
}

// Contactpersoon voor een automatisch ticket: kiezen uit Autotask, nieuw aanmaken of bewust geen.
// onKies(contact | null); onTerug optioneel (terug naar de vorige stap).
function ContactStap({ info, onKies, onTerug, terugTekst = 'Terug' }) {
  const [lijst, setLijst] = useState(null);
  const [q, setQ] = useState('');
  const [nieuw, setNieuw] = useState(null);
  const [bezig, setBezig] = useState(false);
  useEffect(() => {
    (async () => {
      try {
        const r = await api('at.contacten', {}, { quiet: true });
        setLijst(r.contacts);
        if (r.stale) setLijst((await api('at.contacten', { fresh: true }, { quiet: true })).contacts);
      } catch (e) { toast(e.message, 'e'); setLijst((x) => x || []); }
    })();
  }, []);
  const z = q.trim().toLowerCase();
  const zichtbaar = (lijst || []).filter((c) => !z || `${c.name} ${c.email} ${c.phone}`.toLowerCase().includes(z));
  const begin = () => {
    // Zoektekst als startpunt: e-mailadres of naam
    const d = { firstName: '', lastName: '', email: '', phone: '' };
    if (q.includes('@')) d.email = q.trim();
    else if (q.trim()) { const w = q.trim().split(/\s+/); d.firstName = w[0]; d.lastName = w.slice(1).join(' '); }
    setNieuw(d);
  };
  const mailOk = nieuw && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(nieuw.email.trim());
  const maak = async () => {
    setBezig(true);
    const r = await act('at.contact.nieuw', nieuw, { msg: 'Contactpersoon aanmaken in Autotask...' });
    setBezig(false);
    if (r) onKies(r.contact);   // melding komt al uit het activiteitenlog van de backend
  };
  if (nieuw) {
    // type="text" + inputMode: dezelfde opmaak als de andere velden
    const veld = (k, label, mode = 'text', extra = {}) => (
      <div><label className="f">{label}</label><input type="text" inputMode={mode} autoComplete="off" value={nieuw[k]} onChange={(e) => setNieuw({ ...nieuw, [k]: e.target.value })} {...extra} /></div>);
    return (
      <>
        <div className="hint" style={{ marginTop: 0 }}>Nieuwe contactpersoon bij het Autotask-bedrijf van {info.tenant}.</div>
        <div className="grid2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {veld('firstName', 'Voornaam', 'text', { autoFocus: true })}
          {veld('lastName', 'Achternaam')}
          {veld('email', 'E-mailadres', 'email')}
          {veld('phone', 'Telefoonnummer (optioneel)', 'tel')}
        </div>
        <div className="foot">
          <button className="btn" onClick={() => setNieuw(null)}>Terug</button>
          <button className="btn p" disabled={bezig || !nieuw.firstName.trim() || !nieuw.lastName.trim() || !mailOk} onClick={maak}>Aanmaken en kiezen</button>
        </div>
      </>
    );
  }
  return (
    <>
      <div className="hint" style={{ marginTop: 0 }}>Van wie komt de aanvraag? De app kan dat niet zelf achterhalen.</div>
      <div className="row" style={{ alignItems: 'center' }}>
        <SearchBox value={q} onChange={setQ} placeholder="Zoek op naam, e-mail of telefoon..." autoFocus />
        <Btn s v="p" icon={UserPlus} onClick={begin}>Nieuwe contactpersoon</Btn>
      </div>
      <div className="list" style={{ maxHeight: 300, marginTop: 8 }}>
        <div className="li" onClick={() => onKies(null)} style={{ cursor: 'pointer' }}>
          <UserX size={15} style={{ flex: 'none', color: 'var(--mu)' }} /><span className="m"><b>Geen contactpersoon</b><small>Ticket zonder contactpersoon aanmaken</small></span></div>
        {!lijst ? <Loading text="Contactpersonen ophalen..." /> : zichtbaar.length ? zichtbaar.slice(0, 250).map((c) => (
          <div key={c.id} className="li" onClick={() => onKies(c)} style={{ cursor: 'pointer' }}>
            <User size={15} style={{ flex: 'none', color: 'var(--hd)' }} />
            <span className="m"><b>{c.name}</b><small>{[c.email, c.phone, c.title].filter(Boolean).join(' · ') || 'geen gegevens'}</small></span></div>))
          : <div className="li empty">{z ? 'Niet gevonden. ' : 'Geen contactpersonen bij dit bedrijf. '}
            <button className="linkknop" onClick={begin}>Nieuwe contactpersoon aanmaken</button></div>}
      </div>
      {onTerug && <div className="foot"><button className="btn" onClick={onTerug}>{terugTekst}</button></div>}
    </>
  );
}

// Los venster (ticketbalk): geeft { contact } terug, of undefined bij annuleren
export const kiesContact = (info) => openModal((close) => (
  <>
    <h3>Contactpersoon voor het automatische ticket</h3>
    <ContactStap info={info} onKies={(c) => close({ contact: c })} onTerug={() => close(undefined)} terugTekst="Annuleren" />
  </>
), { wide: true });

function BedrijfKoppelen({ info, onGekoppeld, tid, tenantName, domain }) {
  const [q, setQ] = useState('');
  const [lijst, setLijst] = useState(null);
  const zoek = async (tekst) => {
    setLijst(null);
    try { setLijst((await api('at.bedrijven', tekst ? { q: tekst } : { tid: tid || info.tenantId, name: tenantName || info.tenant, domain }, { quiet: true })).companies); } catch (e) { toast(e.message, 'e'); setLijst([]); }
  };
  useEffect(() => { zoek(''); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const kies = async (b) => {
    if (await act('at.klant.set', { tid: tid || info.tenantId, companyId: b.id, name: b.name, tenantName: tenantName || info.tenant }, { msg: 'Koppelen...' })) onGekoppeld({ companyId: b.id, name: b.name });
  };
  return (
    <>
      <Msg kind="info">Koppel {tenantName || info.tenant} eenmalig aan het juiste Autotask-bedrijf. Dit geldt daarna voor alle collega's.</Msg>
      <SearchBox value={q} onChange={setQ} placeholder="Zoek bedrijf in Autotask (Enter)..." onKeyDown={(e) => e.key === 'Enter' && zoek(q)} />
      <div className="list" style={{ maxHeight: 300, marginTop: 8 }}>
        {!lijst ? <Loading text="Bedrijven zoeken..." /> : lijst.length ? lijst.map((b) => (
          <div key={b.id} className="li" onClick={() => kies(b)} style={{ cursor: 'pointer' }}>
            <Building2 size={15} style={{ flex: 'none' }} /><span className="m"><b>{b.name}</b><small>{b.web || ''}</small></span></div>))
          : <div className="li empty">Geen voorstel gevonden; zoek op naam.</div>}
      </div>
    </>
  );
}

function Werklog({ close }) {
  const [s, setS] = useState(null);
  const laad = async () => { try { setS((await api('at.status', {}, { quiet: true })).session); } catch { setS(null); } };
  useEffect(() => { laad(); }, []);
  if (!s) return <Loading />;
  const zet = async (id, w) => setS(await act('at.sessie.item', { id, ...w }, { quiet: true }) || s);
  const boek = async () => {
    // Contactpersoon nog niet gekozen: venster sluiten, de ticketbalk vraagt het en boekt daarna
    if (s.mode === 'auto' && !s.ticket && !s.contactGekozen) return close('boeken');
    const r = await act('at.boek', {}, { msg: 'Boeken in Autotask...' });
    if (r) close(true);
  };
  const telt = s.items.filter((i) => !i.skip);
  return (
    <>
      <h3>Werklog {s.klant}</h3>
      <div className="hint" style={{ marginTop: 0 }}>Alleen uitgevoerde wijzigingen; opvragen en rondklikken worden niet gelogd. Tijd per actie is een realistische schatting die je kunt aanpassen. Het totaal gaat altijd per 15 minuten naar boven.</div>
      {!s.items.length ? <Msg kind="info">Er staan geen acties klaar.</Msg> : (
        <table>
          <thead><tr><th>Tijd</th><th>Actie</th><th className="r">Minuten</th><th>Meetellen</th><th /></tr></thead>
          <tbody>{s.items.map((i) => (
            <tr key={i.id} style={i.skip ? { opacity: .5 } : undefined}>
              <td><small>{new Date(i.ts).toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' })}</small></td>
              <td><b>{i.label}</b><br /><small className="hint">{i.tekst}</small></td>
              <td className="r"><input type="number" min={0} max={480} value={i.minuten} style={{ width: 70, textAlign: 'right' }}
                onChange={(e) => setS({ ...s, items: s.items.map((x) => (x.id === i.id ? { ...x, minuten: e.target.value } : x)) })}
                onBlur={(e) => zet(i.id, { minuten: +e.target.value })} /></td>
              <td><input type="checkbox" checked={!i.skip} onChange={(e) => zet(i.id, { skip: !e.target.checked })} /></td>
              <td><button className="btn s dl" onClick={() => zet(i.id, { remove: true })} title="Verwijderen"><Trash2 size={13} /></button></td>
            </tr>))}</tbody>
        </table>)}
      <div className="headrow" style={{ marginTop: 12 }}>
        <div className="m">{s.eerder ? <><b>Komt bij de registratie van {s.eerder.om}</b> ({s.eerder.acties} eerdere actie(s), {s.eerder.minuten} min, nu {uren(s.eerder.geboekt)} geboekt):<br />
          totaal {s.eerder.minuten + telt.reduce((a, i) => a + (+i.minuten || 0), 0)} min → <b style={{ color: 'var(--hd)' }}>{uren(kwartier(s.eerder.minuten + telt.reduce((a, i) => a + (+i.minuten || 0), 0)))}</b> in Autotask (dezelfde tijdregel wordt bijgewerkt)</>
          : <><b>Totaal: {telt.reduce((a, i) => a + (+i.minuten || 0), 0)} min</b> → <b style={{ color: 'var(--hd)' }}>{uren(kwartier(telt.reduce((a, i) => a + (+i.minuten || 0), 0)))}</b> in Autotask</>}
          <div className="hint" style={{ margin: 0 }}>{s.mode === 'ticket' && s.ticket ? (s.ticket.soort === 'taak' ? `Projecttaak ${s.ticket.title} (${s.ticket.project})` : `Ticket ${s.ticket.number}`) : s.mode === 'auto' ? 'Nieuw ticket wordt aangemaakt' : 'Kies eerst een ticket in de ticketbalk'}</div></div>
      </div>
      <div className="foot"><button className="btn" onClick={() => close(false)}>Sluiten</button>
        <button className="btn p" disabled={!telt.length || !(s.mode === 'ticket' || s.mode === 'auto')} onClick={boek}>Nu boeken</button></div>
    </>
  );
}

// ---------------------------------------------------------------- Tabblad Autotask (startscherm)
export default function AutotaskInstellingen({ klanten }) {
  const [st, setSt] = useState(null);
  const [opties, setOpties] = useState(null);
  const [inst, setInst] = useState(null);
  const [k, setK] = useState({ user: '', secret: '', code: '' });
  const [q, setQ] = useState('');
  const laad = async () => {
    try {
      const x = await api('at.status', { me: true }, { quiet: true });
      setSt(x); setInst(x.settings);
      if (x.configured) setOpties(await api('at.opties', {}, { quiet: true }).catch(() => null));
    } catch (e) { toast(e.message, 'e'); }
  };
  useEffect(() => { laad(); }, []);
  if (!st) return <div className="klanten"><Loading text="Autotask openen..." /></div>;
  const koppel = async () => {
    if (!k.user || !k.secret || !k.code) return toast('Vul alle drie de velden in.', 'e');
    if (await act('at.keys.set', k, { msg: 'Verbinding met Autotask testen...' })) { setK({ user: '', secret: '', code: '' }); laad(); }
  };
  const opslaan = async () => { if (await act('at.settings.save', { settings: inst }, { msg: 'Opslaan...' })) toast('Instellingen opgeslagen voor iedereen.', 'g'); };
  const sel = (veld, lijst, label, leeg = 'Standaard van Autotask') => (
    <div><label className="f">{label}</label>
      <select value={inst[veld] ?? ''} onChange={(e) => setInst({ ...inst, [veld]: e.target.value === '' ? null : +e.target.value })}>
        <option value="">{leeg}</option>{(lijst || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></div>);
  const gekoppeld = st.customers || {};
  const lijst = (klanten || []).filter((x) => !q || x.name.toLowerCase().includes(q.toLowerCase()));
  const koppelKlant = async (x) => {
    await openModal((close) => (<><h3>{x.name} koppelen</h3>
      <BedrijfKoppelen info={{ tenantId: x.id, tenant: x.name }} tid={x.id} tenantName={x.name} domain={x.domain} onGekoppeld={() => close(true)} />
      <div className="foot"><button className="btn" onClick={() => close(false)}>Sluiten</button></div></>), { wide: true });
    laad();
  };
  return (
    <div className="klanten breed">
      <h2 style={{ marginTop: 0 }}>Autotask</h2>
      <p className="sub">Automatische werkregistratie: acties in de app komen als notitie en tijd (per 15 minuten) op het juiste ticket, bij de juiste klant en op naam van de medewerker. Back-upcontroles worden per dag op een intern ticket geregistreerd. Eén keer instellen geldt voor alle collega's.</p>
      {st.error && <Msg kind="warn">{st.error}</Msg>}
      <Card title="Koppeling" icon={Link2} right={st.configured ? <Chip k="g">gekoppeld{st.me ? ` · jij bent ${st.me.name}` : ''}</Chip> : <Chip k="mu">niet gekoppeld</Chip>}>
        <div className="hint" style={{ marginTop: 0 }}>Gebruik een Autotask API-gebruiker (beveiligingsniveau "API User (API-only)") met een Tracking Identifier (integratiecode). Collega's worden herkend aan hun e-mailadres in Autotask.</div>
        <div className="row">
          <div><label className="f">API-gebruikersnaam</label><input type="text" autoComplete="off" value={k.user} onChange={(e) => setK({ ...k, user: e.target.value })} placeholder={st.configured ? '(ongewijzigd)' : 'api@justdata...'} /></div>
          <div><label className="f">Secret</label><input type="password" autoComplete="off" value={k.secret} onChange={(e) => setK({ ...k, secret: e.target.value })} /></div>
          <div><label className="f">Integratiecode (Tracking Identifier)</label><input type="password" autoComplete="off" value={k.code} onChange={(e) => setK({ ...k, code: e.target.value })} /></div>
        </div>
        <div className="btns" style={{ marginTop: 10 }}><Btn v="p" onClick={koppel}>{st.configured ? 'Vervangen' : 'Testen en koppelen'}</Btn>
          {st.configured && <Btn v="dl" onClick={async () => { if (await ask('Autotask-koppeling verwijderen voor iedereen?', 'Verwijderen', true)) { await act('at.keys.delete', {}); laad(); } }}>Verwijderen</Btn>}</div>
      </Card>

      {st.configured && inst && (
        <Card title="Hoe tickets en tijd worden vastgelegd" icon={Settings} right={<Btn s v="p" onClick={opslaan}>Opslaan</Btn>}>
          {!opties ? <Loading text="Keuzelijsten uit Autotask ophalen..." /> : (
            <>
              <div className="row">
                <div><label className="f">Bij de eerste actie bij een klant</label>
                  <select value={inst.modus} onChange={(e) => setInst({ ...inst, modus: e.target.value })}>
                    <option value="vragen">Vragen in de ticketbalk (aanbevolen)</option><option value="auto">Automatisch nieuw ticket</option><option value="skip">Niet registreren</option></select></div>
                <div><label className="f">Automatisch boeken</label>
                  <select value={inst.autoBoeken ? 'ja' : 'nee'} onChange={(e) => setInst({ ...inst, autoBoeken: e.target.value === 'ja' })}>
                    <option value="ja">Ja, bij wisselen van klant en na inactiviteit</option><option value="nee">Nee, alleen met "Nu boeken"</option></select></div>
                <div><label className="f">Inactief na (minuten)</label>
                  <input type="number" min={5} max={240} value={inst.inactiefMin} onChange={(e) => setInst({ ...inst, inactiefMin: +e.target.value })} /></div>
              </div>
              <div className="hint">Tijd wordt altijd per 15 minuten naar boven afgerond (minimaal 15 minuten).</div>
              <h4 className="kopje">Nieuwe tickets</h4>
              <div className="row">
                {sel('queueID', opties.queueID, 'Wachtrij (queue)')}{sel('status', opties.status, 'Status bij aanmaken')}{sel('priority', opties.priority, 'Prioriteit')}
              </div>
              <div className="row">
                {sel('issueType', opties.issueType, 'Probleemtype (issue type)', 'Geen')}
                {sel('subIssueType', (opties.subIssueType || []).filter((o) => !inst.issueType || String(o.parent) === String(inst.issueType)), 'Subtype', 'Geen')}
                {sel('source', opties.source, 'Bron')}{sel('ticketCategory', opties.ticketCategory, 'Ticketcategorie')}
              </div>
              <div className="row">
                {sel('statusKlaar', opties.status, 'Status "afgehandeld"', 'Niet automatisch sluiten')}
                <div><label className="f">Automatische tickets na boeken sluiten</label>
                  <select value={inst.sluitAuto ? 'ja' : 'nee'} onChange={(e) => setInst({ ...inst, sluitAuto: e.target.value === 'ja' })}>
                    <option value="ja">Ja</option><option value="nee">Nee, open laten</option></select></div>
                {sel('billingCodeID', opties.billingCodes, 'Werktype (work type)')}
              </div>
              <h4 className="kopje">Notities</h4>
              <div className="row">{sel('noteType', opties.noteType, 'Notitietype')}{sel('publish', opties.publish, 'Zichtbaar voor')}</div>
              <h4 className="kopje">Back-upcontrole</h4>
              <div className="row">
                <div><label className="f">Intern bedrijf (ID, 0 = eigen organisatie)</label><input type="number" min={0} value={inst.internCompanyID ?? 0} onChange={(e) => setInst({ ...inst, internCompanyID: +e.target.value })} /></div>
                <div><label className="f">Minuten per klant</label><input type="number" min={1} max={60} value={inst.backupMinPerKlant} onChange={(e) => setInst({ ...inst, backupMinPerKlant: +e.target.value })} /></div>
                {sel('backupBillingCodeID', opties.billingCodes, 'Werktype back-upcontrole', 'Zelfde als hierboven')}
              </div>
            </>)}
        </Card>
      )}

      {st.configured && <Medewerkers />}

      {st.configured && (
        <Card title={`Klanten koppelen (${Object.keys(gekoppeld).length} van ${(klanten || []).length})`} icon={Building2}
          right={<SearchBox value={q} onChange={setQ} placeholder="Zoek klant..." />}>
          <div className="hint" style={{ marginTop: 0 }}>Welke Microsoft 365-klant hoort bij welk Autotask-bedrijf. Koppelen kan ook direct vanuit de ticketbalk; de app stelt een bedrijf voor op basis van domein en naam.</div>
          <table className="vastkop"><thead><tr><th>Klant (Microsoft 365)</th><th>Autotask-bedrijf</th><th /></tr></thead>
            <tbody>{lijst.map((x) => (
              <tr key={x.id}><td><b>{x.name}</b><br /><small className="hint">{x.domain}</small></td>
                <td>{gekoppeld[x.id] ? <Chip k="g">{gekoppeld[x.id].name}</Chip> : <Chip k="mu">niet gekoppeld</Chip>}</td>
                <td><div className="btns"><Btn s onClick={() => koppelKlant(x)}>{gekoppeld[x.id] ? 'Wijzigen' : 'Koppelen'}</Btn>
                  {gekoppeld[x.id] && <Btn s v="dl" icon={X} onClick={async () => { await act('at.klant.set', { tid: x.id, companyId: null }); laad(); }} title="Ontkoppelen" />}</div></td></tr>))}</tbody></table>
        </Card>
      )}

      {st.configured && (
        <Card title="Recent geboekt (deze sessie)" icon={ListChecks} right={<Btn s icon={RefreshCw} onClick={laad}>Vernieuwen</Btn>}>
          {!st.booked.length ? <div className="hint">Nog niets geboekt.</div> : (
            <table><thead><tr><th>Wanneer</th><th>Klant</th><th>Ticket</th><th className="r">Tijd</th><th>Hoe</th></tr></thead>
              <tbody>{st.booked.map((r, i) => <tr key={i}><td><small>{r.at}</small></td><td>{r.klant}</td><td><b>{r.ticket}</b> <small className="hint">{r.titel}</small></td>
                <td className="r">{uren(r.minuten)}</td><td><small className="hint">{r.acties} actie(s), {r.wie}</small></td></tr>)}</tbody></table>)}
          {st.open.length > 0 && <Msg kind="warn">Nog niet geboekt: {st.open.map((o) => `${o.klant} (${o.aantal})`).join(', ')}. Open de klant en kies een ticket of "Nu boeken".</Msg>}
        </Card>
      )}
    </div>
  );
}


// Welke Microsoft-login boekt als welke Autotask-medewerker (bijv. meerdere logins op één gedeelde servicedesk-medewerker)
function Medewerkers() {
  const [d, setD] = useState(null);
  const [mail, setMail] = useState('');
  const [res, setRes] = useState('');
  const laad = async () => { try { setD(await api('at.medewerkers', {}, { quiet: true })); } catch (e) { toast(e.message, 'e'); setD({ resources: [], mapping: {} }); } };
  useEffect(() => { laad(); }, []);
  if (!d) return <Card title="Medewerkers" icon={Users}><Loading text="Medewerkers uit Autotask ophalen..." /></Card>;
  // Voorstel op voornaam (of exact e-mailadres) zodra een login is ingevuld
  const voorstel = (m) => {
    const lok = m.split('@')[0].toLowerCase();
    const x = d.resources.find((r) => r.email === m.toLowerCase()) || d.resources.find((r) => r.name.toLowerCase().split(' ')[0] === lok);
    return x ? String(x.id) : '';
  };
  const opslaan = async (m, id) => {
    const r = d.resources.find((x) => String(x.id) === String(id));
    const x = await act('at.medewerker.set', { email: m, resourceId: id === '' ? null : +id, name: r ? r.name : '' }, { msg: 'Opslaan...' });
    if (x) { setD({ ...d, mapping: x.mapping }); setMail(''); setRes(''); }
  };
  const rijen = Object.entries(d.mapping).sort();
  return (
    <Card title={`Medewerkers (${rijen.length})`} icon={Users}>
      <div className="hint" style={{ marginTop: 0 }}>Welke Microsoft-login boekt als welke Autotask-medewerker. Meerdere logins mogen op dezelfde medewerker boeken (bijv. een gedeelde servicedesk-medewerker). Logins zonder koppeling worden op e-mailadres gezocht.</div>
      <table><thead><tr><th>Microsoft-login</th><th>Boekt als (Autotask)</th><th /></tr></thead>
        <tbody>
          {rijen.map(([m, v]) => (
            <tr key={m}><td><b>{m}</b></td>
              <td><select value={v.id} onChange={(e) => opslaan(m, e.target.value)}>{d.resources.map((r) => <option key={r.id} value={r.id}>{r.name}{r.email ? ` (${r.email})` : ''}</option>)}</select></td>
              <td><Btn s v="dl" icon={X} onClick={() => opslaan(m, '')} title="Koppeling verwijderen" /></td></tr>))}
          <tr><td><input type="email" value={mail} placeholder="naam@justdata.nl" onChange={(e) => { setMail(e.target.value); if (!res || res === voorstel(mail)) setRes(voorstel(e.target.value)); }} /></td>
            <td><select value={res} onChange={(e) => setRes(e.target.value)}><option value="">Kies Autotask-medewerker...</option>
              {d.resources.map((r) => <option key={r.id} value={r.id}>{r.name}{r.email ? ` (${r.email})` : ''}</option>)}</select></td>
            <td><Btn s v="p" onClick={() => (mail && res ? opslaan(mail.trim(), res) : toast('Vul een login in en kies een medewerker.', 'e'))}>Toevoegen</Btn></td></tr>
        </tbody></table>
    </Card>
  );
}
