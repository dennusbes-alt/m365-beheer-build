// Servicedesk: snel een ticket maken (met een kwartier tijd), je eigen open tickets met oplossingen uit IT Glue,
// en voor de eerste lijn tickets van de tweede lijn die met bestaande kennis zelf op te pakken zijn. Plus de IT Glue-koppeling
// en de tweede lijn instellen (alleen de app-beheerder).
import { useEffect, useRef, useState } from 'react';
import { ArrowUpFromLine, BarChart3, BookOpen, CalendarPlus, Hourglass, MonitorPlay, MonitorSmartphone, PackagePlus, CheckCircle2, Clock, ExternalLink, Headset, KeyRound, Lightbulb, ListChecks, Plus, RefreshCw, Save, Search, Settings, ShieldCheck, Sparkles, StickyNote, Ticket, UserPlus, Users } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { AllesVink, Btn, Card, CheckList, Chip, Loading, Tabs } from './ui.jsx';
import { EIND, EindKeuze } from './Autotask.jsx';
import { startTab } from './store.jsx';
import { Changes, Inrichting, Monitoring, Queue, RmmKoppeling, langlopendZetten } from './ServicedeskL.jsx';
import { productenOpTicket } from './Voorraad.jsx';
import { AgendaKoppeling, serviceCall } from './Planning.jsx';
import { Apparaten, meekijkenTicket } from './Rmm.jsx';

const open = (url) => url && act('open.url', { url }, { nobusy: true });
const lees = (k, s) => { try { return localStorage.getItem(k) || s; } catch { return s; } };

export default function Servicedesk() {
  const [o, setO] = useState(null);
  const [tab, setTabState] = useState(() => startTab('servicedesk', lees('sd.tab', '')));
  const setTab = (t) => { setTabState(t); try { localStorage.setItem('sd.tab', t); } catch { /* geen opslag */ } };
  const laad = () => api('sd.opties', {}, { quiet: true }).then(setO).catch((e) => setO({ error: e.message, configured: false }));
  useEffect(() => { laad(); }, []);
  if (!o) return <div className="klanten breed"><Loading text="Servicedesk openen..." /></div>;
  const rol = o.rol || { niveau: '', monitor: false, changes: false, ingericht: false };
  // Tabbladen per rol: L1 werkt vanuit de servicedeskqueue, L2 vanuit de escalaties; changes en monitoring alleen voor wie dat doet
  const tabs = [['nieuw', 'Nieuw ticket', Plus], ['l1', 'Servicedesk (L1)', Headset],
    ...(rol.niveau === 'l2' || rol.monitor ? [['l2', 'Escalaties (L2)', ArrowUpFromLine]] : []),
    ['mijn', 'Mijn tickets', ListChecks], ['eerste', 'Overnemen van L2', Lightbulb], ['apparaten', 'Apparaten', MonitorSmartphone],
    ...(rol.changes ? [['changes', 'Changes', ShieldCheck]] : []),
    ...(rol.monitor ? [['monitor', 'Monitoring', BarChart3]] : []),
    ...(o.admin ? [['instellingen', 'Instellingen', Settings]] : [])];
  const standaard = rol.niveau === 'l2' ? 'l2' : rol.ingericht ? 'l1' : 'nieuw';
  const actief = tabs.some(([k]) => k === tab) ? tab : standaard;
  return (
    <div className="klanten breed">
      <div className="headrow" style={{ marginBottom: 4 }}>
        <div className="m"><h2 style={{ margin: 0 }}>Servicedesk</h2>
          <div className="hint" style={{ margin: 0 }}>{o.me ? `Ingelogd in Autotask als ${o.me.name}` : 'Autotask'} · IT Glue {o.itglue ? 'gekoppeld' : 'niet gekoppeld'}</div></div>
      </div>
      {!o.configured ? <Msg kind="info">Autotask is nog niet gekoppeld. De app-beheerder koppelt dit onder het tabblad Autotask.</Msg> : (
        <>
          {o.error && <Msg kind="warn">{o.error}</Msg>}
          <Tabs value={actief} onChange={setTab} tabs={tabs} />
          <div style={{ marginTop: 14 }}>
            {actief === 'l1' ? <Queue key="l1" level="l1" rol={rol} me={o.me} onAfronden={afrondenTickets} />
              : actief === 'l2' ? <Queue key="l2" level="l2" rol={rol} me={o.me} onAfronden={afrondenTickets} />
                : actief === 'mijn' ? <MijnTickets itglue={o.itglue} ai={o.ai} />
                  : actief === 'eerste' ? <EersteLijn admin={o.admin} itglue={o.itglue} ai={o.ai} naarInstellingen={() => setTab('instellingen')} />
                    : actief === 'apparaten' ? <Apparaten />
                    : actief === 'changes' ? <Changes />
                      : actief === 'monitor' ? <Monitoring />
                        : actief === 'instellingen' && o.admin ? <><Inrichting /><RmmKoppeling /><div style={{ height: 14 }} /><AgendaKoppeling /><div style={{ height: 14 }} /><Instellingen o={o} onKlaar={laad} /></>
                          : <NieuwTicket o={o} itglue={o.itglue} />}
          </div>
        </>)}
    </div>);
}

// ---------------------------------------------------------------- Nieuw ticket
function NieuwTicket({ o, itglue }) {
  const [bedrijf, setBedrijf] = useState(null);
  const [zoek, setZoek] = useState('');
  const [gevonden, setGevonden] = useState(null);
  const [contacten, setContacten] = useState(null);
  const [contact, setContact] = useState(undefined);   // undefined = nog niet gekozen, null = geen contactpersoon
  const [titel, setTitel] = useState('');
  const [tekst, setTekst] = useState('');
  const [kennis, setKennis] = useState([]);
  const [klaar, setKlaar] = useState(null);
  const tZoek = useRef(null); const tKennis = useRef(null);

  const zoeken = (q) => {
    setZoek(q); clearTimeout(tZoek.current);
    if (q.trim().length < 2) { setGevonden(null); return; }
    tZoek.current = setTimeout(() => api('sd.bedrijven', { q }, { quiet: true }).then((r) => setGevonden(r.companies)).catch(() => {}), 300);
  };
  const kiesBedrijf = (b) => {
    setBedrijf(b); setGevonden(null); setZoek(''); setContact(undefined); setContacten(null);
    api('at.contacten', { companyId: b.id, companyName: b.name }, { quiet: true }).then((r) => setContacten(r.contacts)).catch(() => setContacten([]));
  };
  useEffect(() => {   // Al bekend in IT Glue? Terwijl je typt zoeken op onderwerp + beschrijving
    clearTimeout(tKennis.current);
    if (!itglue || titel.trim().length < 4) { setKennis([]); return undefined; }
    tKennis.current = setTimeout(() => api('ig.zoek', { q: `${titel} ${titel} ${tekst}`, org: bedrijf?.name || '', n: 3, subject: titel }, { quiet: true })
      .then((r) => setKennis(r.results || [])).catch(() => {}), 500);
    return () => clearTimeout(tKennis.current);
  }, [titel, tekst, bedrijf, itglue]);
  const nieuwContact = async () => {
    const r = await openModal((close) => <ContactNieuw close={close} />);
    if (!r) return;
    const x = await act('at.contact.nieuw', { ...r, companyId: bedrijf.id, companyName: bedrijf.name }, { msg: 'Contactpersoon aanmaken...' });
    if (x) { setContact(x.contact); setContacten((l) => [x.contact, ...(l || []).filter((c) => c.id !== x.contact.id)]); }
  };
  const maak = async () => {
    const r = await act('sd.ticket', { companyId: bedrijf.id, companyName: bedrijf.name, contactId: contact?.id || null, title: titel.trim(), description: tekst.trim() },
      { msg: 'Ticket aanmaken en een kwartier boeken...' });
    if (r) { setKlaar(r.ticket); setTitel(''); setTekst(''); setContact(undefined); setKennis([]); }
  };
  const lijst = gevonden || o.companies || [];
  const kan = bedrijf && contact !== undefined && titel.trim();

  return (
    <div className="sd-twee">
      <div>
        {klaar && <Msg kind="ok"><b>Ticket {klaar.number}</b> is aangemaakt op jouw naam en er is een kwartier geboekt.
          {klaar.url && <> <button className="linkknop" onClick={() => open(klaar.url)}>Openen in Autotask</button></>}
          {' '}<button className="linkknop" onClick={() => productenOpTicket(klaar)}>Product toevoegen</button></Msg>}
        <Card title="Nieuw ticket" icon={Ticket}>
          <label className="f">Klant</label>
          {bedrijf ? (
            <div className="li on" style={{ cursor: 'default' }}><span className="m"><b>{bedrijf.name}</b></span><Btn s onClick={() => { setBedrijf(null); setContacten(null); setContact(undefined); }}>Wijzigen</Btn></div>
          ) : (
            <>
              <div style={{ position: 'relative' }}>
                <Search size={15} style={{ position: 'absolute', left: 10, top: 11, color: 'var(--mu)' }} />
                <input value={zoek} onChange={(e) => zoeken(e.target.value)} placeholder="Zoek klant in Autotask..." style={{ paddingLeft: 32, width: '100%' }} autoFocus />
              </div>
              <div className="list" style={{ maxHeight: 200 }}>
                {lijst.map((b) => <div key={b.id} className="li" onClick={() => kiesBedrijf(b)}><span className="m"><b>{b.name}</b></span></div>)}
                {!lijst.length && <div className="li empty">{gevonden ? 'Niets gevonden.' : 'Typ minstens twee letters.'}</div>}
              </div>
            </>)}
          {bedrijf && (
            <>
              <label className="f">Contactpersoon</label>
              {!contacten ? <Loading text="Contactpersonen ophalen..." /> : (
                <div className="btns" style={{ alignItems: 'center' }}>
                  <select value={contact === undefined ? '' : contact === null ? 'geen' : String(contact.id)} style={{ width: 'auto', minWidth: 260 }}
                    onChange={(e) => setContact(e.target.value === 'geen' ? null : contacten.find((c) => String(c.id) === e.target.value))}>
                    <option value="" disabled>Kies de contactpersoon</option>
                    <option value="geen">Geen contactpersoon</option>
                    {contacten.map((c) => <option key={c.id} value={String(c.id)}>{c.name}{c.email ? ` (${c.email})` : ''}</option>)}
                  </select>
                  <Btn s icon={UserPlus} onClick={nieuwContact}>Nieuwe contactpersoon</Btn>
                </div>)}
              <label className="f">Onderwerp</label>
              <input value={titel} onChange={(e) => setTitel(e.target.value)} placeholder="Bijv. Outlook start niet op bij de receptie" maxLength={250} style={{ width: '100%' }} />
              <label className="f">Beschrijving</label>
              <textarea rows={6} style={{ width: '100%' }} value={tekst} onChange={(e) => setTekst(e.target.value)} placeholder="Wat is de vraag of het probleem? Wie, wat, sinds wanneer?" />
              <div className="foot" style={{ justifyContent: 'space-between' }}>
                <span className="hint" style={{ margin: 0, display: 'flex', gap: 6, alignItems: 'center' }}><Clock size={14} />Op jouw naam, met direct 15 minuten geboekt.</span>
                <Btn v="p" icon={Ticket} disabled={!kan} onClick={maak}>Ticket aanmaken</Btn>
              </div>
            </>)}
        </Card>
      </div>
      <div>
        <Card title="Al bekend in IT Glue?" icon={BookOpen}>
          {!itglue ? <div className="hint">IT Glue is nog niet gekoppeld (de app-beheerder doet dit onder IT Glue en instellingen).</div>
            : !kennis.length ? <div className="hint">Typ het onderwerp; passende oplossingen uit IT Glue verschijnen hier.</div>
              : <Kennis lijst={kennis} />}
        </Card>
      </div>
    </div>);
}

function ContactNieuw({ close }) {
  const [v, setV] = useState({ firstName: '', lastName: '', email: '', phone: '' });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  return (
    <>
      <h3>Nieuwe contactpersoon</h3>
      <div className="row"><div><label className="f">Voornaam</label><input value={v.firstName} onChange={z('firstName')} autoFocus /></div>
        <div><label className="f">Achternaam</label><input value={v.lastName} onChange={z('lastName')} /></div></div>
      <label className="f">E-mailadres</label><input type="text" inputMode="email" value={v.email} onChange={z('email')} />
      <label className="f">Telefoonnummer (optioneel)</label><input type="text" inputMode="tel" value={v.phone} onChange={z('phone')} />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!v.firstName.trim() || !v.lastName.trim() || !v.email.includes('@')} onClick={() => close(v)}>Aanmaken</button></div>
    </>);
}

// ---------------------------------------------------------------- Kennis (IT Glue)
function Kennis({ lijst, compact }) {
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {lijst.map((k) => (
        <div key={k.id} style={{ background: 'var(--bg)', borderRadius: 8, padding: compact ? '7px 10px' : '9px 12px', borderLeft: '3px solid var(--cy)' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
            <b style={{ fontSize: 13.5 }}>{k.title}</b>
            {k.url && <button className="linkknop" style={{ whiteSpace: 'nowrap' }} onClick={() => open(k.url)}><ExternalLink size={12} /> Openen</button>}
          </div>
          <div className="hint" style={{ margin: 0 }}>{[k.org, k.type, k.updated && `bijgewerkt ${k.updated.split('-').reverse().join('-')}`].filter(Boolean).join(' · ')}</div>
          {!compact && k.snippet && <div style={{ fontSize: 12.5, marginTop: 4, color: 'var(--sl)' }}>…{k.snippet}…</div>}
        </div>))}
    </div>);
}

// ---------------------------------------------------------------- Mijn tickets
function TicketKaart({ t, itglue, ai, eersteLijn, onGewijzigd, gekozen, onKies }) {
  const [uit, setUit] = useState(false);
  const afronden = async () => { if (await afrondenTickets([t])) onGewijzigd && onGewijzigd(); };
  const [advies, setAdvies] = useState(null);   // null = dicht, 'laden', of het advies
  const vastleggen = async () => {
    const r = await openModal((close) => <Vastleggen t={t} advies={advies && advies !== 'laden' ? advies : null} close={close} />, { wide: true });
    if (!r) return;
    const x = await act('ig.vastleggen', { ...r, company: t.company, ticket: `${t.number} ${t.title}` }, { msg: 'Vastleggen in IT Glue...' });
    if (x) toast(`Vastgelegd in IT Glue bij ${x.org}.`, 'g');
  };
  const tijd = async () => {
    const r = await openModal((close) => <TijdBoeken t={t} ai={ai} close={close} />, { wide: true });
    if (!r) return;
    const x = await act('sd.tijd', { id: t.id, ...r }, { msg: 'Tijd boeken in Autotask...' });
    if (x) { toast(`${t.number}: ${x.done.join(', ')}.`, 'g'); if (r.status && onGewijzigd) onGewijzigd(); }
  };
  const notitie = async () => {
    const r = await openModal((close) => <Notitie t={t} close={close} />);
    if (r && await act('sd.notitie', { id: t.id, ...r }, { msg: 'Notitie toevoegen...' })) toast('Notitie toegevoegd.', 'g');
  };
  const hoe = async (fresh) => {
    if (advies && !fresh) { setAdvies(null); return; }
    setAdvies('laden');
    try { setAdvies(await api('adv.ticket', { id: t.id, title: t.title, description: t.description, company: t.company, fresh: !!fresh }, { quiet: true })); } catch (e) { toast(e.message, 'e'); setAdvies(null); }
  };
  const tr = t.triage;
  return (
    <div className="card" style={{ padding: '12px 14px', borderLeft: `4px solid var(--${t.overdue ? 'rd' : (t.knowledge || []).length || tr?.eersteLijn ? 'gr' : 'bd2'})` }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        {onKies && <input type="checkbox" checked={!!gekozen} onChange={(e) => onKies(e.target.checked)} title="Selecteren om meerdere tickets tegelijk af te ronden" style={{ marginTop: 4 }} />}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontWeight: 900, color: 'var(--navy)' }}>{t.title}</div>
          <div className="hint" style={{ margin: 0 }}>{t.number} · <b>{t.company}</b> · {t.created}{t.age != null ? ` (${t.age} d)` : ''}
            {eersteLijn && <> · {t.unassigned ? <Chip k="o">nog niemand</Chip> : <>bij <b>{t.assigned}</b></>}</>}</div>
          <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {t.status && <Chip>{t.status}</Chip>}{t.priority && <Chip k={/high|hoog|crit/i.test(t.priority) ? 'r' : 'mu'}>{t.priority}</Chip>}
            {t.overdue && <Chip k="r">over de deadline</Chip>}
            {t.longRunning && <Chip k="mu" title="Langlopend: buiten de SLA, telt niet mee in de cijfers"><Hourglass size={11} /> langlopend</Chip>}
            {tr && (tr.eersteLijn ? <Chip k="g" title={tr.reden}>eerste lijn kan dit · ±{tr.minuten} min</Chip> : <Chip k="mu" title={tr.reden}>tweede lijn</Chip>)}
          </div>
          {tr?.reden && <div className="hint" style={{ margin: '3px 0 0' }}>{tr.reden}</div>}
        </div>
        <div className="btns">
          {(ai || advies || (t.knowledge || []).length > 0) && <Btn s v="p" icon={Lightbulb} onClick={() => hoe(false)}>{advies ? 'Advies sluiten' : 'Hoe los ik dit op?'}</Btn>}
          <Btn s icon={Clock} onClick={tijd}>Tijd boeken</Btn>
          <Btn s icon={StickyNote} onClick={notitie}>Notitie</Btn>
          <Btn s icon={PackagePlus} onClick={async () => { if (await productenOpTicket(t) && onGewijzigd) onGewijzigd(); }} title="Product uit de voorraad op dit ticket (of laten bestellen)">Product</Btn>
          <Btn s icon={CalendarPlus} onClick={async () => { if (await serviceCall(t) && onGewijzigd) onGewijzigd(); }} title="Service call inplannen (ook in de Outlook-agenda)">Service call</Btn>
          <Btn s icon={MonitorPlay} onClick={() => meekijkenTicket(t)} title="Meekijken op de computer (Datto RMM web remote); de tijd wordt geboekt">Meekijken</Btn>
          <Btn s icon={Hourglass} v={t.longRunning ? 'p' : ''} onClick={async () => { if (await langlopendZetten([t], !t.longRunning) && onGewijzigd) onGewijzigd(); }}
            title={t.longRunning ? 'Niet meer langlopend' : 'Langlopend (bijv. reparatie): geen incident, buiten de SLA'}>{t.longRunning ? 'Langlopend' : null}</Btn>
          {!eersteLijn && <Btn s icon={CheckCircle2} onClick={afronden} title="Oplossing, tijd en afronden: Afgerond (Complete) of Klaar voor facturatie (Ready to Invoice)">Afronden</Btn>}
          {t.url && <Btn s icon={ExternalLink} onClick={() => open(t.url)} title="Openen in Autotask" />}
          {itglue && <Btn s icon={BookOpen} onClick={vastleggen} title="Oplossing vastleggen in IT Glue">IT Glue</Btn>}
        </div>
      </div>
      {advies && <Advies a={advies} opnieuw={() => hoe(true)} />}
      {t.description && <div style={{ fontSize: 12.5, marginTop: 6, color: 'var(--sl)', whiteSpace: 'pre-wrap' }}>{uit ? t.description : t.description.split('\n').slice(0, 3).join('\n').slice(0, 220)}
        {(t.description.length > 220 || t.description.split('\n').length > 3) && <button className="linkknop" onClick={() => setUit(!uit)}>{uit ? ' minder' : ' … meer'}</button>}</div>}
      {(t.knowledge || []).length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--gr)', display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
            <Lightbulb size={14} />{eersteLijn ? 'Hiermee kan de eerste lijn dit oppakken:' : 'Zo is dit eerder opgelost (IT Glue):'}</div>
          <Kennis lijst={t.knowledge} compact={eersteLijn} />
        </div>)}
    </div>);
}

// Advies: stappenplan in gewone taal (AI, met IT Glue en Microsoft-documentatie als bron) + passende IT Glue-documenten
function Advies({ a, opnieuw }) {
  if (a === 'laden') return <div style={{ marginTop: 10 }}><Loading text="Advies opstellen..." /></div>;
  const ai = a.ai;
  return (
    <div style={{ marginTop: 10, background: 'var(--acl)', borderRadius: 10, padding: '12px 14px', display: 'grid', gap: 10 }}>
      {ai ? (
        <div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 4 }}>
            <b style={{ color: 'var(--navy)' }}>Zo pak je het aan</b>
            {ai.eersteLijn ? <Chip k="g">eerste lijn kan dit</Chip> : <Chip k="o">liever tweede lijn</Chip>}
            {ai.tijdInschatting ? <Chip k="mu">±{ai.tijdInschatting} min</Chip> : null}
            <button className="linkknop" style={{ marginLeft: 'auto' }} onClick={opnieuw}>opnieuw</button>
          </div>
          <div style={{ fontSize: 13.5 }}>{ai.samenvatting}</div>
          {ai.uitleg && <div style={{ fontSize: 13, marginTop: 6, background: 'var(--card)', borderRadius: 8, padding: '8px 10px' }}><b>Waarom dit gebeurt:</b> {ai.uitleg}</div>}
          {ai.vragenAanKlant?.length > 0 && <><div style={{ fontWeight: 700, fontSize: 13, marginTop: 8 }}>Vraag eerst aan de klant</div>
            <ul style={{ margin: '2px 0 0 18px', fontSize: 13 }}>{ai.vragenAanKlant.map((v) => <li key={v}>{v}</li>)}</ul></>}
          <div style={{ fontWeight: 700, fontSize: 13, marginTop: 8 }}>Stappen</div>
          <ol style={{ margin: '2px 0 0 20px', fontSize: 13.5, lineHeight: 1.5 }}>{ai.stappen.map((s, i) => <li key={i}>{s}</li>)}</ol>
          <div style={{ fontSize: 13, marginTop: 8 }}><b>Klaar als:</b> {ai.controle}</div>
          <div style={{ fontSize: 13 }}><b>Doorzetten naar de tweede lijn als:</b> {ai.escalerenAls}</div>
          {!ai.eersteLijn && ai.waarom && <div className="hint" style={{ margin: '4px 0 0' }}>{ai.waarom}</div>}
        </div>
      ) : null}
      {(a.itglue || []).length > 0 && <div><div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>Zo is dit eerder opgelost (IT Glue)</div><Kennis lijst={a.itglue} compact /></div>}
      {!ai && !(a.itglue || []).length && <div className="hint" style={{ margin: 0 }}>Hier is nog geen bekende oplossing voor.</div>}
    </div>);
}

function TijdBoeken({ t, ai: aiAan, close }) {
  const [min, setMin] = useState(15);
  const [tekst, setTekst] = useState('');
  const [notitie, setNotitie] = useState(false);
  const [status, setStatus] = useState('');
  const [statussen, setStatussen] = useState([]);
  const [ai, setAi] = useState(false);
  useEffect(() => { api('sd.statussen', {}, { quiet: true }).then((r) => setStatussen(r.statuses)).catch(() => {}); }, []);
  const schrijf = async () => {
    setAi(true);
    try { setTekst((await api('adv.tijdtekst', { title: t.title, notes: tekst }, { quiet: true })).text); } catch (e) { toast(e.message, 'e'); }
    setAi(false);
  };
  return (
    <>
      <h3>Tijd boeken · {t.number}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{t.title} · {t.company}</div>
      <label className="f">Tijd</label>
      <div className="btns" style={{ alignItems: 'center' }}>
        {[15, 30, 45, 60, 90, 120].map((m) => <Btn key={m} s v={min === m ? 'p' : ''} onClick={() => setMin(m)}>{m < 60 ? `${m} min` : `${m / 60} uur`}</Btn>)}
        <input type="number" min={1} max={600} value={min} onChange={(e) => setMin(+e.target.value)} style={{ width: 90 }} /> <span className="hint" style={{ margin: 0 }}>minuten</span>
      </div>
      <label className="f">Wat heb je gedaan?</label>
      <textarea rows={5} style={{ width: '100%' }} value={tekst} onChange={(e) => setTekst(e.target.value)}
        placeholder="Steekwoorden zijn genoeg, bijv.: outlook profiel opnieuw, ost weg, werkt weer" autoFocus />
      <div className="btns" style={{ marginTop: 6 }}>
        {aiAan && <Btn s icon={Lightbulb} disabled={ai || tekst.trim().length < 3} onClick={schrijf}>{ai ? 'Bezig...' : 'Netjes laten schrijven (AI)'}</Btn>}
      </div>
      <label className="chk" style={{ marginTop: 10 }}><input type="checkbox" checked={notitie} onChange={(e) => setNotitie(e.target.checked)} /><span>Ook als notitie op het ticket zetten</span></label>
      <label className="f">Status daarna (optioneel)</label>
      <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: 'auto', minWidth: 240 }}>
        <option value="">Niet wijzigen ({t.status || 'huidig'})</option>
        {statussen.map((s) => <option key={s.value} value={s.value}>{s.label}{s.done ? ' (afgerond)' : ''}</option>)}
      </select>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!min || tekst.trim().length < 5} onClick={() => close({ minutes: min, text: tekst.trim(), note: notitie, status: status ? +status : null })}>Boeken</button></div>
    </>);
}

function Notitie({ t, close }) {
  const [titel, setTitel] = useState('Notitie');
  const [tekst, setTekst] = useState('');
  return (
    <>
      <h3>Notitie toevoegen · {t.number}</h3>
      <label className="f">Titel</label><input value={titel} onChange={(e) => setTitel(e.target.value)} style={{ width: '100%' }} />
      <label className="f">Notitie</label><textarea rows={6} style={{ width: '100%' }} value={tekst} onChange={(e) => setTekst(e.target.value)} autoFocus />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!tekst.trim()} onClick={() => close({ title: titel.trim() || 'Notitie', text: tekst.trim() })}>Toevoegen</button></div>
    </>);
}

function Vastleggen({ t, advies, close }) {
  const [v, setV] = useState({ title: t.title, problem: t.description || '', solution: advies?.ai ? advies.ai.stappen.map((s, i) => `${i + 1}. ${s}`).join('\n') : '', keywords: '' });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  return (
    <>
      <h3>Oplossing vastleggen in IT Glue</h3>
      <div className="hint" style={{ marginTop: 0 }}>Wordt een werkinstructie bij <b>{t.company}</b>. Schrijf het zo dat een collega het de volgende keer zelf kan.</div>
      <label className="f">Titel</label><input value={v.title} onChange={z('title')} />
      <label className="f">Vraag of probleem</label><textarea rows={3} value={v.problem} onChange={z('problem')} />
      <label className="f">Oplossing (stappen)</label>
      <textarea rows={8} value={v.solution} onChange={z('solution')} placeholder={'1. ...\n2. ...\n3. Controleren: ...'} autoFocus />
      <label className="f">Trefwoorden (optioneel)</label><input value={v.keywords} onChange={z('keywords')} placeholder="Bijv. outlook, profiel, ost" />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!v.title.trim() || !v.solution.trim()} onClick={() => close(v)}>Vastleggen</button></div>
    </>);
}

// Eén of meer tickets afronden: per ticket oplossing, tijd en Afgerond (Complete) of Klaar voor facturatie (Ready to Invoice).
// Licentietickets staan standaard op facturatie. Geeft true als er iets is afgerond.
async function afrondenTickets(tickets) {
  const r = await openModal((close) => <Afronden tickets={tickets} close={close} />, { wide: true });
  if (!r) return false;
  const x = await act('sd.afsluiten', { items: r }, { msg: `${r.length} ticket(s) afronden in Autotask...` });
  if (!x) return false;
  if (x.failed) toast(`${x.ok} afgerond, ${x.failed} niet gelukt: ${x.results.filter((y) => !y.ok).map((y) => y.error).join('; ').slice(0, 300)}`, 'e');
  else toast(`${x.ok} ticket(s) afgerond, met oplossing en tijd.`, 'g');
  return x.ok > 0;
}

function Afronden({ tickets, close }) {
  const [rijen, setRijen] = useState(() => tickets.map((t) => ({ id: t.id, minutes: 15, text: '', end: /licen/i.test(`${t.title} ${t.description || ''}`) ? 'invoice' : 'complete' })));
  const zet = (i, k, v) => setRijen((l) => l.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const alle = (k, v) => setRijen((l) => l.map((x) => ({ ...x, [k]: v })));
  const ok = rijen.every((x) => x.text.trim().length >= 5 && x.minutes > 0 && x.minutes <= 600);
  return (
    <>
      <h3>{tickets.length === 1 ? `Ticket afronden · ${tickets[0].number}` : `${tickets.length} tickets afronden`}</h3>
      <div className="hint" style={{ marginTop: 0 }}>Per ticket: wat is de oplossing, hoeveel tijd, en hoe rond je af. Licentie erbij of eraf = <b>Klaar voor facturatie</b> (de administratie valideert en factureert); een incident of vraag = <b>Afgerond</b>.</div>
      {tickets.length > 1 && (
        <div className="btns" style={{ alignItems: 'center', margin: '8px 0' }}>
          <span className="hint" style={{ margin: 0 }}>Voor alle tickets:</span>
          {[15, 30, 60].map((m) => <Btn key={m} s onClick={() => alle('minutes', m)}>{m} min</Btn>)}
          {EIND.map(([k, l]) => <Btn key={k} s onClick={() => alle('end', k)}>{l}</Btn>)}
        </div>)}
      <div style={{ display: 'grid', gap: 10, maxHeight: '60vh', overflow: 'auto' }}>
        {tickets.map((t, i) => (
          <div key={t.id} className="card" style={{ padding: '10px 12px' }}>
            <div style={{ fontWeight: 700, color: 'var(--navy)' }}>{t.number} · {t.title}</div>
            <div className="hint" style={{ margin: '0 0 6px' }}>{t.company}</div>
            <textarea rows={2} style={{ width: '100%' }} value={rijen[i].text} onChange={(e) => zet(i, 'text', e.target.value)} autoFocus={i === 0}
              placeholder="Oplossing, bijv.: licentie Business Premium toegevoegd voor nieuwe medewerker" />
            <div className="btns" style={{ alignItems: 'center', marginTop: 6 }}>
              {[15, 30, 45, 60].map((m) => <Btn key={m} s v={rijen[i].minutes === m ? 'p' : ''} onClick={() => zet(i, 'minutes', m)}>{m} min</Btn>)}
              <input type="number" min={1} max={600} value={rijen[i].minutes} onChange={(e) => zet(i, 'minutes', +e.target.value)} style={{ width: 80 }} />
              <span style={{ width: 12 }} />
              <EindKeuze value={rijen[i].end} onChange={(v) => zet(i, 'end', v)} />
            </div>
          </div>))}
      </div>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!ok} onClick={() => close(rijen.map((x) => ({ ...x, text: x.text.trim() })))}>
          {tickets.length === 1 ? 'Afronden' : `${tickets.length} tickets afronden`}</button></div>
    </>);
}

function MijnTickets({ itglue, ai }) {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [filter, setFilter] = useState('alle');
  const [sel, setSel] = useState([]);
  const laad = (fresh) => { setFout(''); api('sd.mijn', { fresh: !!fresh }, { quiet: true }).then(setD).catch((e) => { setFout(e.message); setD({ tickets: [] }); }); };
  useEffect(() => { laad(false); }, []);
  if (!d) return <Loading text={itglue ? 'Je open tickets ophalen en oplossingen zoeken in IT Glue...' : 'Je open tickets ophalen...'} />;
  const met = d.tickets.filter((t) => (t.knowledge || []).length).length;
  // Per klant: hoeveel van jouw open tickets van welke klant zijn (klik = filteren)
  const perKlant = Object.entries(d.tickets.reduce((m, t) => { m[t.company || '(onbekend)'] = (m[t.company || '(onbekend)'] || 0) + 1; return m; }, {}))
    .sort((a, b) => b[1] - a[1]);
  const lijst = d.tickets.filter((t) => (filter === 'kennis' ? (t.knowledge || []).length : filter === 'laat' ? t.overdue : filter === 'lang' ? t.longRunning
    : filter.startsWith('klant:') ? (t.company || '(onbekend)') === filter.slice(6) : true));
  return (
    <>
      {fout && <Msg kind="warn">{fout}</Msg>}
      <div className="headrow" style={{ marginBottom: 10 }}>
        <div className="btns">
          <Btn s v={filter === 'alle' ? 'p' : ''} onClick={() => setFilter('alle')}>Alle ({d.tickets.length})</Btn>
          {itglue && <Btn s v={filter === 'kennis' ? 'p' : ''} icon={Lightbulb} onClick={() => setFilter('kennis')}>Met oplossing ({met})</Btn>}
          <Btn s v={filter === 'laat' ? 'p' : ''} onClick={() => setFilter('laat')}>Over de deadline ({d.tickets.filter((t) => t.overdue).length})</Btn>
          {d.tickets.some((t) => t.longRunning) && <Btn s v={filter === 'lang' ? 'p' : ''} icon={Hourglass} onClick={() => setFilter('lang')}>Langlopend ({d.tickets.filter((t) => t.longRunning).length})</Btn>}
        </div>
        <Btn s icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
      </div>
      {perKlant.length > 1 && (
        <div className="sd-klanten">
          <span className="hint" style={{ margin: 0 }}>Per klant:</span>
          {perKlant.map(([k, n]) => (
            <button key={k} type="button" className={'sd-klant' + (filter === `klant:${k}` ? ' on' : '')} onClick={() => setFilter(filter === `klant:${k}` ? 'alle' : `klant:${k}`)}
              title={`${Math.round((n * 100) / d.tickets.length)}% van je open tickets`}>
              {k} <b>{n}</b><small>{Math.round((n * 100) / d.tickets.length)}%</small></button>))}
        </div>)}
      {!itglue && <Msg kind="info">Koppel IT Glue (app-beheerder) om bij elk ticket te zien hoe het eerder is opgelost.</Msg>}
      {itglue && d.tickets.some((t) => t.knowledgeLoading) && <Msg kind="info">De kennis uit IT Glue wordt op de achtergrond geladen; klik straks op Vernieuwen voor de oplossingen. "Hoe los ik dit op?" werkt al.</Msg>}
      {lijst.length > 0 && (
        <div className="btns" style={{ alignItems: 'center', margin: '0 0 8px', minHeight: 32 }}>
          <AllesVink ids={lijst.map((t) => t.id)} value={sel} onChange={setSel} label="Alle tickets selecteren" />
          {sel.length > 0 && <Btn s v="p" icon={CheckCircle2} onClick={async () => {
            if (await afrondenTickets(d.tickets.filter((t) => sel.includes(t.id)))) { setSel([]); laad(true); }
          }}>{sel.length} ticket(s) afronden</Btn>}
        </div>)}
      <div style={{ display: 'grid', gap: 10 }}>{lijst.map((t) => <TicketKaart key={t.id} t={t} itglue={itglue} ai={ai} onGewijzigd={() => { setSel([]); laad(true); }}
        gekozen={sel.includes(t.id)} onKies={(v) => setSel((s) => (v ? [...s, t.id] : s.filter((x) => x !== t.id)))} />)}</div>
      {!lijst.length && <div className="hint">{d.tickets.length ? 'Geen tickets in deze selectie.' : 'Je hebt geen open tickets. Lekker bezig!'}</div>}
    </>);
}

// ---------------------------------------------------------------- Eerste lijn
function EersteLijn({ admin, itglue, ai, naarInstellingen }) {
  const [d, setD] = useState(null);
  const timer = useRef(null);
  const laad = (fresh) => {
    clearTimeout(timer.current);
    api('sd.eerstelijn', { fresh: !!fresh }, { quiet: true }).then((x) => {
      setD(x);
      if (x.triageBusy) timer.current = setTimeout(() => laad(false), 4000);   // AI-beoordeling loopt nog: zo opnieuw kijken
    }).catch((e) => setD({ tickets: [], error: e.message }));
  };
  useEffect(() => { laad(false); return () => clearTimeout(timer.current); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <Loading text="Tickets van de tweede lijn nalopen..." />;
  if (d.needSetup) return <Msg kind="info">Stel eerst in wie bij de tweede lijn hoort. {admin ? <button className="linkknop" onClick={naarInstellingen}>Tweede lijn instellen</button> : 'Dat doet de app-beheerder.'}</Msg>;
  return (
    <>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      {d.triageError && <Msg kind="warn">AI-beoordeling niet gelukt: {d.triageError}</Msg>}
      <div className="headrow" style={{ marginBottom: 10 }}>
        <div className="hint" style={{ margin: 0 }}>{d.tickets.length} van {d.checked} open tickets bij de tweede lijn (of zonder behandelaar) kan de eerste lijn waarschijnlijk zelf oppakken
          {d.ai ? ' (beoordeeld door AI en IT Glue).' : ' (op basis van IT Glue).'} Klik op "Hoe los ik dit op?" voor een stappenplan in gewone taal.
          {d.triageBusy && <b> De AI is de tickets nog aan het beoordelen...</b>}
          {!d.ai && admin && <> <button className="linkknop" onClick={naarInstellingen}>AI-advies aanzetten</button></>}</div>
        <Btn s icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
      </div>
      <div style={{ display: 'grid', gap: 10 }}>{d.tickets.map((t) => <TicketKaart key={t.id} t={t} itglue={itglue} ai={ai} eersteLijn onGewijzigd={() => laad(true)} />)}</div>
      {!d.tickets.length && !d.triageBusy && <Msg kind="ok">Geen tickets gevonden die de eerste lijn zelf kan oppakken.</Msg>}
    </>);
}

// ---------------------------------------------------------------- Instellingen (alleen app-beheerder)
function Instellingen({ o, onKlaar }) {
  const [sleutel, setSleutel] = useState('');
  const [ig, setIg] = useState(null);
  const [res, setRes] = useState(null);
  const [tweede, setTweede] = useState((o.secondLine || []).map(String));
  useEffect(() => {
    api('ig.status', {}, { quiet: true }).then(setIg).catch(() => setIg({}));
    api('sd.resources', {}, { quiet: true }).then((r) => setRes(r.resources)).catch(() => setRes([]));
  }, []);
  const koppel = async () => { if (await act('ig.keys.set', { key: sleutel.trim() }, { msg: 'IT Glue-sleutel controleren...' })) { setSleutel(''); onKlaar(); api('ig.status', {}, { quiet: true }).then(setIg); } };
  const ontkoppel = async () => { if (await ask('IT Glue ontkoppelen? Niemand ziet dan nog oplossingen uit IT Glue.', 'Ontkoppelen', true) && await act('ig.keys.delete', {})) { onKlaar(); api('ig.status', {}, { quiet: true }).then(setIg); } };
  const bewaar = async () => { if (await act('sd.tweedelijn.set', { ids: tweede.map(Number) }, { msg: 'Opslaan...' })) onKlaar(); };
  return (
    <div className="sd-twee">
      <Card title="IT Glue-koppeling" icon={KeyRound}>
        {!ig ? <Loading /> : ig.configured ? (
          <>
            <Msg kind="ok">IT Glue is gekoppeld (EU).{ig.docs ? ` ${ig.docs} kennisdocumenten geladen${ig.at ? ` om ${ig.at}` : ''}` : ''}{ig.loading ? ' · bezig met (opnieuw) laden...' : '.'}
              {(ig.types || []).length > 0 && <div className="hint" style={{ margin: '4px 0 0' }}>{ig.types.map((x) => `${x.name}: ${x.count}`).join(' · ')}</div>}</Msg>
            <div className="btns"><Btn s v="dl" onClick={ontkoppel}>Ontkoppelen</Btn></div>
            <label className="f">Andere sleutel</label>
          </>) : <Msg kind="info">Nog niet gekoppeld. Alleen jij (app-beheerder) kunt dit instellen; collega's gebruiken de koppeling daarna automatisch.</Msg>}
        <input type="password" value={sleutel} onChange={(e) => setSleutel(e.target.value)} placeholder="IT Glue API-sleutel (ITG.…)" autoComplete="off" />
        <div className="foot"><Btn v="p" icon={KeyRound} disabled={!sleutel.trim()} onClick={koppel}>Koppelen</Btn></div>
        <div className="hint">
          <b>Zo maak je de sleutel:</b> IT Glue (eu.itglue.com) &gt; <b>Account</b> &gt; <b>Settings</b> &gt; <b>API Keys</b> &gt; <b>Custom API Keys</b> &gt; <b>+ Generate API Key</b>.
          Geef hem een naam (bijv. "M365 beheer"), laat <i>Allow Access to Passwords</i> <b>uit</b>, en kopieer de sleutel direct (je ziet hem maar één keer). Plak hem hierboven.
          De app leest alle Documents en de flexibele assets van het soort werkinstructie, procedure, kennisbank of how-to, en maakt bij het eerste vastleggen het type
          "Werkinstructie (M365 beheer)" aan.
        </div>
      </Card>
      <AiInstelling />
      <Card title="Tweede lijn" icon={Users}>
        <div className="hint" style={{ marginTop: 0 }}>Wie hoort bij de tweede lijn? Tickets op hun naam (en tickets zonder behandelaar) waarvoor IT Glue een oplossing heeft,
          verschijnen bij <b>Eerste lijn</b> als suggestie om over te nemen.</div>
        {!res ? <Loading /> : <CheckList items={res.map((r) => ({ v: String(r.id), l: r.name, s: r.email }))} value={tweede} onChange={setTweede} placeholder="Zoek medewerker..." />}
        <div className="foot"><Btn v="p" icon={Save} onClick={bewaar}>Opslaan</Btn></div>
      </Card>
    </div>);
}

function AiInstelling() {
  const [s, setS] = useState(null);
  const [sleutel, setSleutel] = useState('');
  const laad = () => api('adv.status', {}, { quiet: true }).then(setS).catch(() => setS({}));
  useEffect(() => { laad(); }, []);
  const koppel = async () => { if (await act('adv.keys.set', { key: sleutel.trim() }, { msg: 'Sleutel controleren bij Anthropic...' })) { setSleutel(''); laad(); } };
  const ontkoppel = async () => { if (await ask('AI-advies uitzetten voor iedereen?', 'Uitzetten', true) && await act('adv.keys.delete', {})) laad(); };
  return (
    <Card title="AI-advies (Claude)" icon={Sparkles}>
      {!s ? <Loading /> : s.configured ? (
        <>{s.available ? <Msg kind="ok">AI-advies werkt ({s.model}). Per ticket een stappenplan in gewone taal en de beoordeling bij Eerste lijn.</Msg>
          : <Msg kind="warn">AI-advies is ingesteld maar werkt nu niet, en is daarom voor iedereen verborgen. {s.problem}</Msg>}
          <div className="btns"><Btn s v="dl" onClick={ontkoppel}>Uitzetten</Btn></div><label className="f">Andere sleutel</label></>)
        : <Msg kind="info">Staat uit. Zonder AI-advies zien collega's alleen de oplossingen uit IT Glue; AI-knoppen zijn dan verborgen.</Msg>}
      <input type="password" value={sleutel} onChange={(e) => setSleutel(e.target.value)} placeholder="Anthropic API-sleutel (sk-ant-…)" autoComplete="off" />
      <div className="foot"><Btn v="p" icon={KeyRound} disabled={!sleutel.trim()} onClick={koppel}>Koppelen</Btn></div>
      <div className="hint">
        <b>Zo maak je de sleutel:</b> ga naar <b>platform.claude.com</b> en log in met het Justdata-account (of maak een organisatie "Justdata" aan) &gt; <b>Settings</b> &gt; <b>Billing</b>: voeg een betaalmethode toe
        en zet een maandlimiet (bijv. € 25) &gt; <b>API Keys</b> &gt; <b>Create Key</b>, naam "M365 beheer", en kopieer de sleutel direct. Plak hem hierboven.
        Wat er naar Anthropic gaat: onderwerp en beschrijving van het ticket, zonder e-mailadressen en telefoonnummers. Kosten: ongeveer 1 tot 2 cent per advies.
      </div>
    </Card>);
}

export const ServicedeskIcon = Headset;
