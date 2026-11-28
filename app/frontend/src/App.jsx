import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import {
  ArrowLeftRight, Building2, CalendarDays, Download, History, KeyRound, LayoutGrid, LogOut, MonitorSmartphone,
  ShieldCheck, Sparkles, BarChart3, Bell, Receipt, CalendarClock, BriefcaseBusiness, TrendingUp, UserMinus, UserPlus, Users, UsersRound, X, Fingerprint, Globe, Mail, ShieldAlert, Rocket, AtSign, Wrench, Truck, HeartPulse, Palette, Workflow, MailX, ShieldHalf, Laptop, UserCheck, Bot, Stethoscope, Archive, DatabaseBackup, Ticket, MailCheck, SlidersHorizontal, AppWindow, LogIn, FolderLock, Package,
} from 'lucide-react';
import logo from './assets/logo.png';
import { act, api, bye, ping, setTenant } from './api.js';
import { Msg, Overlays, ask, busyText, openModal, toast } from './overlays.jsx';
import { AppCtx, doorgeven, resetCache, zetTab } from './store.jsx';
import Zoeken from './Zoeken.jsx';
import { FUNCTIES } from './functies.js';
import { Btn, Loading, Tabs } from './ui.jsx';
import Klanten from './Klanten.jsx';
import Backup from './Backup.jsx';
import Dmarc from './Dmarc.jsx';
import Management from './Management.jsx';
import Servicedesk, { ServicedeskIcon } from './Servicedesk.jsx';
import Facturatie from './Facturatie.jsx';
import Timesheet from './Timesheet.jsx';
import Projecten from './Projecten.jsx';
import Sales from './Sales.jsx';
import Voorraad from './Voorraad.jsx';
import { MeekijkBalk } from './Rmm.jsx';
import { useMeldingen } from './ServicedeskL.jsx';
import AutotaskInstellingen, { TicketBalk } from './Autotask.jsx';

// Schermen worden apart geladen (snellere start) en direct na het kiezen van een klant op de achtergrond voorgeladen
const VIEW_IMPORTS = [
  () => import('./views/Gebruikers.jsx'), () => import('./views/NieuweGebruiker.jsx'), () => import('./views/UitDienst.jsx'),
  () => import('./views/Licenties.jsx'), () => import('./views/Agenda.jsx'), () => import('./views/Groepen.jsx'),
  () => import('./views/Opruimen.jsx'), () => import('./views/Apparaten.jsx'), () => import('./views/Authenticatie.jsx'),
  () => import('./views/Exchange.jsx'), () => import('./views/Bedreiging.jsx'), () => import('./views/SharePoint.jsx'),
  () => import('./views/Autopilot.jsx'), () => import('./views/Domeinen.jsx'),
  () => import('./views/Migratie.jsx'), () => import('./views/Health.jsx'), () => import('./views/Huisstijl.jsx'),
  () => import('./views/Automatisering.jsx'), () => import('./views/Afwezig.jsx'), () => import('./views/SecureScore.jsx'),
  () => import('./views/ComplianceApparaten.jsx'), () => import('./views/ComplianceGebruikers.jsx'),
  () => import('./views/Copilot.jsx'), () => import('./views/Nen7510.jsx'), () => import('./views/Archief.jsx'),
];
const [Gebruikers, NieuweGebruiker, UitDienst, Licenties, Agenda, Groepen, Opruimen, Apparaten, Authenticatie, ExchangeView, Bedreiging, SharePoint, Autopilot, Domeinen, MigratieView, Health, Huisstijl, Automatisering, Afwezig, SecureScore, ComplianceApparaten, ComplianceGebruikers, CopilotView, Nen7510, ArchiefView] =
  VIEW_IMPORTS.map((f) => lazy(f));
const intune = () => import('./views/Intune.jsx');
VIEW_IMPORTS.push(intune);
const Profielen = lazy(() => intune().then((m) => ({ default: m.Profielen })));
const IntuneApps = lazy(() => intune().then((m) => ({ default: m.Apps })));
const mappenImport = () => import('./views/Mappen.jsx');
VIEW_IMPORTS.push(mappenImport);
const Mappen = lazy(mappenImport);
const Inschrijving = lazy(() => intune().then((m) => ({ default: m.Inschrijving })));
const caImport = () => import('./views/Voorwaardelijk.jsx');
VIEW_IMPORTS.push(caImport);
const Voorwaardelijk = lazy(caImport);

const MENU = [
  ['Gebruikers', [
    ['users', 'Gebruikers beheren', Users, Gebruikers],
    ['nieuw', 'Nieuwe gebruiker', UserPlus, NieuweGebruiker],
    ['uit', 'Medewerker uit dienst', UserMinus, UitDienst],
  ]],
  ['Tenant', [
    ['lic', 'Licenties', KeyRound, Licenties],
    ['opruim', 'Inactieve gebruikers', Sparkles, Opruimen],
    ['auth', 'Authenticatiemethoden', Fingerprint, Authenticatie],
    ['ca', 'Voorwaardelijke toegang', ShieldCheck, Voorwaardelijk],
    ['domeinen', 'Domeinen', AtSign, Domeinen],
    ['huisstijl', 'Huisstijl aanmeldpagina', Palette, Huisstijl],
  ]],
  ['Samenwerken', [
    ['agenda', 'Agendarechten', CalendarDays, Agenda],
    ['groepen', 'Groepen en postvakken', UsersRound, Groepen],
    ['sharepoint', 'SharePoint', Globe, SharePoint],
    ['spmappen', 'Mapmachtigingen', FolderLock, Mappen],
  ]],
  ['E-mail', [
    ['exchange', 'Exchange', Mail, ExchangeView],
    ['afwezig', 'Afwezigheid en doorsturen', MailX, Afwezig],
    ['archief', 'Archief en retentie', Archive, ArchiefView],
    ['bedreiging', 'Bedreigingsbeheer', ShieldAlert, Bedreiging],
  ]],
  ['Apparaten', [
    ['apparaten', 'Apparaten (Intune)', MonitorSmartphone, Apparaten],
    ['autopilot', 'Autopilot', Rocket, Autopilot],
    ['iprofielen', 'Configuratieprofielen', SlidersHorizontal, Profielen],
    ['iapps', 'Apps', AppWindow, IntuneApps],
    ['iinschrijving', 'Inschrijving en Windows Hello', LogIn, Inschrijving],
  ]],
  ['Compliance', [
    ['securescore', 'Secure Score', ShieldHalf, SecureScore],
    ['capparaten', 'Apparaten', Laptop, ComplianceApparaten],
    ['cgebruikers', 'Gebruikers en MFA', UserCheck, ComplianceGebruikers],
    ['copilot', 'Copilot-readiness', Bot, CopilotView],
    ['nen7510', 'NEN 7510', Stethoscope, Nen7510],
  ]],
  ['Migratie', [
    ['migratie', 'Migratie', Truck, MigratieView],
  ]],
  ['Automatisering', [
    ['automatisering', 'Automatisering', Workflow, Automatisering],
  ]],
  ['Health', [
    ['health', 'Servicestatus', HeartPulse, Health],
  ]],
];
// Welke gegevens een scherm direct nodig heeft: die worden opgehaald zodra je het menu-item aanwijst
const VOORAF = {
  users: [['users'], ['skus']], nieuw: [['users'], ['skus'], ['groups.list', { fresh: false }], ['shared.list']], uit: [['users']],
  lic: [['skus'], ['users']], auth: [['auth.methods']], ca: [['ca.list']], domeinen: [['dom.list']], agenda: [['users'], ['shared.list']],
  groepen: [['groups.list', { fresh: false }]], sharepoint: [['sp.sites', { fresh: false }]], bedreiging: [['threat.list', { kind: 'spam' }]], opruim: [['skus'], ['inactive', { days: 90 }]],
  apparaten: [['dev.list', { fresh: false }]], autopilot: [['ap.list', { fresh: false }]], iprofielen: [['in.profiles', { fresh: false }]], iapps: [['in.apps', { fresh: false }]], iinschrijving: [['in.enroll', { fresh: false }]], migratie: [['mig.batches']],
  health: [['health.overview']], huisstijl: [['brand.get']], automatisering: [['auto.blokken'], ['auto.lijst']],
  afwezig: [['users'], ['shared.list']], securescore: [['ss.list']], capparaten: [['cd.devices']], cgebruikers: [['cu.users']], copilot: [['rd.copilot']], archief: [['ret.list']], nen7510: [['rd.nen']],
};
const vooraf = (k) => (VOORAF[k] || []).forEach(([n, b]) => act(n, b || {}, { nobusy: true, quiet: true }));
const VIEWS = Object.fromEntries(MENU.flatMap(([, items]) => items.map(([k, , , C]) => [k, C])));

function Login({ onDone, versie }) {
  const [stap, setStap] = useState(0);
  const [fout, setFout] = useState('');
  const start = async () => {
    setFout(''); setStap(1);
    try {
      const r = await api('auth.login', {}, { nobusy: true, quiet: true });
      setStap(3);
      onDone(r.user);
    } catch (e) { setFout(e.message); setStap(0); }
  };
  const S = ({ n, t, d }) => (
    <div className={'step ' + (stap > n ? 'done' : stap >= n && stap ? 'on' : '')}>
      <span className="nr">{stap > n ? '✓' : n}</span>
      <div><b>{t}</b><div style={{ fontSize: 12.5 }}>{d}</div></div>
      {stap === n && <span className="spin" style={{ marginLeft: 'auto' }} />}
    </div>
  );
  return (
    <div className="splash">
      <div className="box">
        <img src={logo} alt="Justdata" />
        <h1>Microsoft 365 beheer</h1>
        <p className="sub" style={{ margin: 0 }}>Log in met je Justdata-account. Daarna kies je de klant die je wilt beheren.</p>
        <div className="steps">
          <S n={1} t="Inloggen bij Microsoft" d="In je browser, met je Justdata-beheerdersaccount" />
          <S n={2} t="Exchange Online" d="Meestal automatisch, zonder opnieuw je wachtwoord" />
        </div>
        {stap ? <Msg kind="info">Rond het inloggen af in het browservenster dat nu opent en kom daarna hier terug.</Msg>
          : <Btn v="p lg" w onClick={start} icon={ShieldCheck}>Inloggen met je Justdata-account</Btn>}
        {fout && <Msg kind="err">{fout}</Msg>}
        <p className="hint" style={{ marginTop: 18 }}>Er wordt niets opgeslagen op deze computer. Als je het programma sluit, ben je automatisch afgemeld.</p>
        {versie && <p className="hint" style={{ margin: 0, color: 'var(--mu2)' }}>Versie {versie}</p>}
      </div>
    </div>
  );
}

function Activiteit({ onClose }) {
  const [items, setItems] = useState(null);
  useEffect(() => { act('activity', {}, { nobusy: true }).then((d) => setItems(d ? d.items : [])); }, []);
  return (
    <div className="drawer" role="dialog">
      <header><History size={18} /><h3>Activiteit in deze sessie</h3><Btn s onClick={onClose} icon={X}>Sluiten</Btn></header>
      <div className="items">
        {!items ? <Loading /> : !items.length ? <p className="hint">Nog geen acties uitgevoerd.</p> : items.map((a, i) => (
          <div key={i} className={'act' + (/^FOUT/.test(a.text) ? ' fout' : '')}>
            <time>{a.t}</time>
            <div><div className="tn">{a.tenant}</div><div>{a.text}</div></div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [fase, setFase] = useState('boot');   // boot | login | klanten | app
  const [user, setUser] = useState(null);
  const [klanten, setKlanten] = useState(null);
  // Eerste scherm: technisch beheer (klant kiezen), back-up, e-mailbeveiliging, management of Autotask; keuze onthouden
  const [appBeheer, setAppBeheer] = useState(false);
  const [justdata, setJustdata] = useState(false);   // Back-up, e-mailbeveiliging en Autotask alleen met een Justdata-login
  const [directie, setDirectie] = useState(false);   // Management alleen voor de directie
  const [billing, setBilling] = useState(false);     // Facturatie alleen voor wie facturen goedkeurt
  const [sales, setSales] = useState(false);         // Sales: invoeren (sales) of inzien + project maken (beheerder)
  useEffect(() => {
    if (!user) { setAppBeheer(false); setJustdata(false); setDirectie(false); setBilling(false); setSales(false); return; }
    api('app.rol', {}, { quiet: true }).then((x) => { setAppBeheer(!!(x && x.admin)); setJustdata(!!(x && x.justdata)); setDirectie(!!(x && x.directie)); setBilling(!!(x && x.billing)); setSales(!!(x && x.sales)); })
      .catch(() => { setAppBeheer(false); setJustdata(false); setDirectie(false); setBilling(false); setSales(false); });
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  const [projectGen, setProjectGen] = useState(0);   // opnieuw openen van Projecten met een gekozen project (vanuit Sales)
  // Meldingen van nieuwe servicedesktickets (alleen voor de triage-verantwoordelijken; de backend zegt of je dat bent)
  const meldingen = useMeldingen(justdata);
  const [eerste, setEersteState] = useState(() => { try { const v = localStorage.getItem('m365-eerste'); return v && v !== 'administratie' ? v : 'technisch'; } catch { return 'technisch'; } });
  const setEerste = (v) => { setEersteState(v); try { localStorage.setItem('m365-eerste', v); } catch { /* geen opslag */ } };
  const [info, setInfo] = useState(null);
  const [view, setView] = useState('users');
  const [actOpen, setActOpen] = useState(false);
  const [gen, setGen] = useState(0);           // verhoogt bij klantwissel: schermen starten opnieuw
  const [versie, setVersie] = useState('');
  const [update, setUpdate] = useState(null);
  const [ververst, setVerversen] = useState(false);

  useEffect(() => {
    const t = setInterval(ping, 5000);
    addEventListener('pagehide', bye);
    act('auth.status', {}, { nobusy: true, quiet: true }).then((s) => {
      if (s) setVersie(s.version || '');
      if (s && s.loggedIn) { setUser(s.user); setFase('klanten'); } else setFase('login');
    });
    // Updatecontrole: loopt op de achtergrond; server onbereikbaar = gewoon doorgaan
    act('update.status', {}, { nobusy: true, quiet: true }).then((u) => {
      if (u && u.available) { setUpdate(u); if (u.required) installeerUpdate(u, true); }
    });
    return () => { clearInterval(t); removeEventListener('pagehide', bye); };
  }, []);

  const laadKlanten = useCallback(async (fresh) => {
    const d = await act('customers', { fresh }, { msg: 'Klanten ophalen uit het partnerportaal...' });
    if (!d) return null;
    setKlanten(d.customers);
    if (d.cached) {
      // Lijst uit de lokale cache staat er al; nu op de achtergrond de actuele lijst ophalen
      setVerversen(true);
      act('customers', { noCache: true }, { nobusy: true, quiet: true }).then((v) => { if (v) setKlanten(v.customers); }).finally(() => setVerversen(false));
    }
    return d.customers;
  }, []);
  useEffect(() => { if (fase === 'klanten' && !klanten) laadKlanten(false); }, [fase, klanten, laadKlanten]);

  // Duidelijke uitleg als een klant (nog) niet geopend kan worden, met de goedkeuringslink voor de klant
  const gdapMelding = (k, e) => {
    const tekst = e.message === 'Failed to fetch' ? 'De verbinding met het programma is verbroken.' : e.message || String(e);
    if (!e.link) { toast(tekst, 'e'); return; }
    const klant = e.gdap === 'approvalPending';
    openModal((close) => (
      <>
        <h3>{k.name}: {klant ? 'wacht op goedkeuring' : 'GDAP-relatie nodig'}</h3>
        <div className="pre">{tekst}</div>
        {klant && <>
          <label className="f">Goedkeuringslink voor de klant (een Global Administrator van de klant opent deze)</label>
          <input type="text" readOnly value={e.link} onFocus={(ev) => ev.target.select()} />
        </>}
        <div className="foot">
          <button className="btn" onClick={() => close()}>Sluiten</button>
          {klant
            ? <button className="btn p" autoFocus onClick={() => { navigator.clipboard?.writeText(e.link).then(() => toast('Goedkeuringslink gekopieerd.', 'g'), () => {}); }}>Link kopiëren</button>
            : <button className="btn p" autoFocus onClick={() => { act('open.url', { url: e.link }, { nobusy: true }); close(); }}>Partnerportaal openen</button>}
        </div>
      </>
    ));
  };

  // Na een wijziging die de klantgegevens raakt (bijv. domeinen): gegevens bovenin en in andere schermen bijwerken
  const herlaadInfo = useCallback(async () => {
    const d = await act('info', {}, { quiet: true });
    if (d) setInfo((oud) => (oud && oud.tenantId === d.tenantId ? { ...oud, ...d } : oud));
  }, []);

  const kies = useCallback(async (k) => {
    if (info && k.id === info.tenantId) {
      setFase('app');
      if (doorgeven.naKlant) { const f = doorgeven.naKlant; delete doorgeven.naKlant; f(); }
      return true;
    }
    if (info && info.tenantId) act('at.boek', { tid: info.tenantId, wissel: true }, { quiet: true, nobusy: true, tenant: info.tenantId });
    const eerste = k.access === false;
    const kop = eerste ? `Toegang regelen bij ${k.name}` : `Verbinden met ${k.name}`;
    // Voortgang per stap tonen terwijl de backend de klant opent (GDAP-toewijzing, wachten op Microsoft, koppelen)
    const poll = setInterval(async () => {
      const v = await act('tenant.progress', { id: k.id }, { quiet: true });
      if (v && v.text) busyText(`${kop}
${v.text}
(${v.seconds} s bezig)`);
    }, 2000);
    let d = null;
    try {
      d = await api('tenant.select', { id: k.id }, {
        tenant: k.id, quiet: true,
        msg: eerste
          ? `${kop}
GDAP-toewijzing en koppeling worden automatisch gemaakt. Dit kan 1 tot 3 minuten duren...`
          : `${kop}... (de eerste keer bij een klant wordt de koppeling automatisch gemaakt)`,
      });
    } catch (e) {
      if (e.stale) return false;
      gdapMelding(k, e);
      return false;
    } finally {
      clearInterval(poll);
    }
    if (d.linked) {
      toast(`De app is automatisch gekoppeld aan ${d.tenant}. Vanaf nu gaat openen direct.`, 'g');
      setKlanten((l) => (l ? l.map((x) => (x.id === k.id ? { ...x, access: true } : x)) : l));
    }
    setTenant(d.tenantId);   // de cache per klant blijft bewaard: terugwisselen gaat direct
    setInfo(d);
    setGen((g) => g + 1);
    setFase('app');
    act('prefs.recent', { id: k.id }, { nobusy: true, quiet: true });
    toast(`Je werkt nu bij ${d.tenant}.`, 'g');
    // Gekozen via de zoekbalk ('kies eerst een klant'): nu meteen die functie openen
    if (doorgeven.naKlant) { const f = doorgeven.naKlant; delete doorgeven.naKlant; f(); }
    return true;
  }, [info]);

  // Exchange wordt na het openen op de achtergrond gecontroleerd: status ophalen zodra die bekend is
  useEffect(() => {
    // Niet verbonden: elke 20 s opnieuw (de backend probeert de verbinding dan zelf te herstellen)
    if (!info || info.exo === true) return undefined;
    const tid = info.tenantId;
    const t = setTimeout(async () => {
      const d = await act('info', {}, { quiet: true });
      if (d && d.tenantId === tid) setInfo((oud) => (oud && oud.tenantId === tid ? { ...oud, exo: d.exo, exoError: d.exoError } : oud));
    }, info.exo === null ? 700 : 20000);
    return () => clearTimeout(t);
  }, [info]);

  // Code van alle schermen alvast laden zodra je bij een klant bent: daarna opent elk menu-item direct
  useEffect(() => {
    if (fase !== 'app') return;
    const laad = () => VIEW_IMPORTS.forEach((f) => f().catch(() => {}));
    if (window.requestIdleCallback) window.requestIdleCallback(laad, { timeout: 1500 });
    else setTimeout(laad, 300);
  }, [fase]);

  // Toegang regelen voor alle klanten zonder toegang (achtergrondklus in de backend, met voortgang)
  const [klus, setKlus] = useState(null);
  const volgKlus = useCallback(async () => {
    for (;;) {
      await new Promise((r) => setTimeout(r, 2500));
      const s = await act('gdap.status', {}, { quiet: true });
      if (!s) continue;
      setKlus(s);
      if (!s.bezig) {
        if (s.customers) setKlanten(s.customers);
        toast(`Toegang geregeld bij ${s.ok.length} klant(en)${s.fouten.length ? `, bij ${s.fouten.length} niet gelukt` : ''}.`, s.fouten.length ? 'e' : 'g');
        return;
      }
    }
  }, []);
  const regelAlles = useCallback(async () => {
    const n = (klanten || []).filter((k) => k.access === false && k.fixable).length;
    if (!await ask(`Bij ${n} klanten toegang regelen?\n\nPer klant maakt de app een GDAP-toegangstoewijzing aan de groep AdminAgents (alle rollen uit de relatie behalve Global Administrator) en koppelt hij zichzelf via Partner Center.\n\nDit loopt op de achtergrond (3 klanten tegelijk, 1 tot 2 minuten per klant).`, 'Toegang regelen')) return;
    const s = await act('gdap.alles', {});
    if (s) { setKlus(s); volgKlus(); }
  }, [klanten, volgKlus]);

  const wissel = useCallback(async () => {
    const lijst = klanten || await laadKlanten(false);
    if (!lijst) return;
    openModal((close) => (
      <Klanten compact klanten={lijst} huidig={info && info.tenantId}
        onPick={async (k) => { close(); await kies(k); }} onClose={() => close()}
        onOverzicht={() => { close(); setFase('klanten'); }} />
    ), { wide: true });
  }, [klanten, info, kies, laadKlanten]);

  useEffect(() => {
    const k = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && fase === 'app') { e.preventDefault(); wissel(); }
    };
    addEventListener('keydown', k);
    return () => removeEventListener('keydown', k);
  }, [fase, wissel]);

  const afmelden = async () => {
    if (!await ask('Afmelden bij Microsoft? Alle tokens worden uit het geheugen gewist.', 'Afmelden')) return;
    await act('auth.logout', {}, { msg: 'Afmelden...' });
    setTenant(''); resetCache(); setInfo(null); setKlanten(null); setUser(null); setFase('login');
  };

  const balk = update && !update.required ? <UpdateBalk u={update} onLater={() => setUpdate(null)} /> : null;

  // Zoekbalk bovenin: schermen van de klant (alleen als er een klant open is), tabbladen van het startscherm, klanten, gegevens, tickets
  const starttabs = [['technisch', 'Klantenoverzicht (technisch beheer)', Wrench], ...(justdata ? [['servicedesk', 'Servicedesk', ServicedeskIcon], ['backup', 'Back-up', DatabaseBackup], ['dmarc', 'E-mailbeveiliging', MailCheck]] : []),
    ...(justdata ? [['timesheet', 'Timesheet', CalendarClock], ['projecten', 'Projecten', BriefcaseBusiness], ['voorraad', 'Voorraad', Package]] : []), ...(justdata && sales ? [['sales', 'Sales', TrendingUp]] : []),
    ...(justdata && directie ? [['management', 'Management', BarChart3]] : []), ...(justdata && billing ? [['facturatie', 'Facturatie', Receipt]] : []), ...(appBeheer ? [['autotask', 'Autotask', Ticket]] : [])];
  // Bel bovenin: nieuwe tickets in de servicedeskqueue die nog niemand heeft opgepakt (triage)
  const naarL1 = () => { zetTab('servicedesk', 'l1'); try { localStorage.setItem('sd.tab', 'l1'); } catch { /* geen opslag */ } setEerste('servicedesk'); setFase('klanten'); };
  // Sales: producten die besteld moeten worden (bestellijst Voorraad)
  const belBestel = justdata && meldingen.orders > 0 ? (
    <button className="topbtn bel" onClick={() => { setEerste('voorraad'); setFase('klanten'); }} title={`${meldingen.orders} product(en) te bestellen (bestellijst Voorraad)`}>
      <Package size={16} /><span className="sdq-teller">{meldingen.orders > 99 ? '99+' : meldingen.orders}</span></button>) : null;
  const belTickets = justdata && meldingen.nieuw > 0 ? (
    <button className="topbtn bel" onClick={naarL1} title={`${meldingen.nieuw} nieuw(e) ticket(s) in de servicedesk nog niet opgepakt:\n${meldingen.tickets.slice(0, 6).map((t) => `${t.number} ${t.title}`).join('\n')}`}>
      <Bell size={16} /><span className="sdq-teller">{meldingen.nieuw > 99 ? '99+' : meldingen.nieuw}</span></button>) : null;
  const bel = belTickets || belBestel ? <>{belBestel}{belTickets}</> : null;
  const schermen = [
    ...starttabs.map(([k, l, I]) => ({ key: 'start-' + k, label: l, group: 'Startscherm', icon: I, run: () => { setEerste(k); setFase('klanten'); } })),
    ...(info ? MENU.flatMap(([g, items]) => items.map(([k, l, I]) => ({ key: k, label: l, group: `${g} · ${info.tenant}`, icon: I, run: () => { setView(k); setFase('app'); } }))) : []),
  ];
  // Alle functies uit functies.js: startscherm-onderdelen alleen als je ze mag zien; functies bij een klant vragen eerst om een klant
  const startMag = { technisch: true, servicedesk: justdata, timesheet: justdata, projecten: justdata, sales: justdata && sales, backup: justdata, dmarc: justdata, management: justdata && directie, facturatie: justdata && billing };
  const menuIcoon = Object.fromEntries(MENU.flatMap(([, items]) => items.map(([k, , I]) => [k, I])));
  const menuNaam = Object.fromEntries(MENU.flatMap(([g, items]) => items.map(([k, l]) => [k, `${g} › ${l}`])));
  const functies = FUNCTIES.filter((f) => !f.v.startsWith('start:') || startMag[f.v.slice(6)]).map((f, i) => {
    const start = f.v.startsWith('start:') ? f.v.slice(6) : null;
    const open = () => {
      if (f.t) zetTab(start || f.v, f.t);
      if (f.d) zetTab(f.v === 'apparaten' ? 'dev-detail' : 'users-detail', f.d);
      if (start) { setEerste(start); setFase('klanten'); return; }
      setView(f.v); setGen((g) => g + 1); setFase('app');
    };
    return {
      key: i, label: f.l, keywords: f.k, icon: start ? LayoutGrid : menuIcoon[f.v],
      sub: [start ? 'Startscherm' : menuNaam[f.v], f.h].filter(Boolean).join(' · ') + (!start && !info ? ' · kies eerst een klant' : ''),
      run: start || info ? open : () => { doorgeven.naKlant = open; setEerste('technisch'); setFase('klanten'); toast('Kies de klant; daarna opent de app dit meteen.'); },
    };
  });
  const zoek = (
    <Zoeken schermen={schermen} functies={functies} klanten={klanten} klant={info} justdata={justdata}
      onKlant={(k) => kies(k)}
      onOpen={(v, z) => { doorgeven.zoek = z; setView(v); setGen((g) => g + 1); setFase('app'); }} />
  );

  let inhoud;
  if (fase === 'boot') inhoud = <div className="splash"><Loading text="Starten..." /></div>;
  else if (fase === 'login') inhoud = <><Login onDone={(u) => { setUser(u); setFase('klanten'); }} versie={versie} />{balk && <div className="updfloat">{balk}</div>}</>;
  else if (fase === 'klanten') {
    inhoud = (
      <div className="shell">
        <Top user={user} info={null} onLogout={afmelden} onHome={() => setEerste('technisch')} zoek={zoek} bel={bel} />
        {justdata && <MeekijkBalk />}
        <div style={{ overflow: 'auto' }}>
          {balk && <div className="klanten" style={{ paddingBottom: 0 }}>{balk}</div>}
          <div className={'klanten tabkop' + (eerste !== 'technisch' ? ' breed' : '')}>
            <Tabs value={eerste} onChange={setEerste} tabs={[['technisch', 'Technisch beheer', Wrench], ...(justdata ? [['servicedesk', 'Servicedesk', ServicedeskIcon], ['projecten', 'Projecten', BriefcaseBusiness], ['timesheet', 'Timesheet', CalendarClock], ['voorraad', 'Voorraad', Package], ['backup', 'Back-up', DatabaseBackup], ['dmarc', 'E-mailbeveiliging', MailCheck]] : []), ...(justdata && sales ? [['sales', 'Sales', TrendingUp]] : []), ...(justdata && directie ? [['management', 'Management', BarChart3]] : []), ...(justdata && billing ? [['facturatie', 'Facturatie', Receipt]] : []), ...(appBeheer ? [['autotask', 'Autotask', Ticket]] : [])]} />
          </div>
          {!klanten ? <Loading text="Klanten ophalen..." />
            : eerste === 'servicedesk' && justdata ? <Servicedesk />
            : eerste === 'backup' && justdata ? <Backup />
            : eerste === 'dmarc' && justdata ? <Dmarc />
            : eerste === 'management' && justdata && directie ? <Management klanten={klanten} />
            : eerste === 'facturatie' && justdata && billing ? <Facturatie />
            : eerste === 'timesheet' && justdata ? <Timesheet />
            : eerste === 'projecten' && justdata ? <Projecten key={projectGen} />
            : eerste === 'voorraad' && justdata ? <Voorraad />
            : eerste === 'sales' && justdata && sales ? <Sales beheerder={appBeheer} onVoorraad={() => setEerste('voorraad')} onProject={(id) => { doorgeven.project = id; setProjectGen((g) => g + 1); setEerste('projecten'); }} />
            : eerste === 'autotask' && appBeheer ? <AutotaskInstellingen klanten={klanten} />
              : <Klanten klanten={klanten} huidig={info && info.tenantId} onPick={kies} onRefresh={() => laadKlanten(true)}
                onTerug={info ? () => setFase('app') : null} user={user} ververst={ververst} onRegelAlles={regelAlles} klus={klus} />}
        </div>
      </div>
    );
  } else {
    const V = VIEWS[view];
    inhoud = (
      <div className="shell">
        <Top user={user} info={info} onSwitch={wissel} onLogout={afmelden} onAct={() => setActOpen(true)} onHome={() => setFase('klanten')} zoek={zoek} bel={bel} />
        {justdata && <MeekijkBalk />}
        <div className="body">
          <aside className="nav">
            <button onClick={() => setFase('klanten')}><LayoutGrid size={18} />Klantenoverzicht</button>
            {MENU.map(([g, items]) => (
              <div key={g}>
                <div className="grp">{g}</div>
                {items.map(([k, l, I]) => (
                  <button key={k} className={view === k ? 'on' : ''} onMouseEnter={() => vooraf(k)} onClick={() => setView(k)}><I size={18} />{l}</button>
                ))}
              </div>
            ))}
            <div className="ft"><ShieldCheck size={15} style={{ flex: 'none' }} /><span>Bij afsluiten word je automatisch afgemeld.{versie && <><br />Versie {versie}</>}</span></div>
          </aside>
          <main className="main">
            <div className="page">
              <TicketBalk info={info} />
              {balk}
              {info.exo === false && (
                <div className="tbanner"><Building2 size={17} />Exchange Online is niet verbonden bij deze klant: aliassen, gedeelde postvakken, distributielijsten en agendarechten werken niet.{info.exoError ? ` (${info.exoError})` : ''}</div>
              )}
              <Suspense fallback={<Loading />}><V key={view + gen} /></Suspense>
            </div>
          </main>
        </div>
        {actOpen && <Activiteit onClose={() => setActOpen(false)} />}
      </div>
    );
  }
  return (
    <AppCtx.Provider value={{ info, user, setView, kies, herlaadInfo }}>
      {inhoud}
      <Overlays />
    </AppCtx.Provider>
  );
}

async function installeerUpdate(u, verplicht) {
  if (!u.canInstall) {
    const ok = await ask(`Versie ${u.latest} staat klaar${verplicht ? ' en is verplicht' : ''}.\n\nDeze installatie kan zichzelf niet bijwerken. Download het installatiebestand en voer dat uit.`, 'Downloadpagina openen');
    if (ok) act('update.download', {}, { nobusy: true });
    return;
  }
  const tekst = [`${verplicht ? 'Er is een verplichte update' : 'Bijwerken naar versie ' + u.latest}?`, '',
    ...(u.notes || []).map((n) => '- ' + n), '', 'De app sluit, installeert de nieuwe versie en start daarna vanzelf opnieuw. Je moet daarna opnieuw inloggen.'].join('\n');
  if (!await ask(tekst, 'Nu bijwerken', false, verplicht ? 'Update vereist' : 'Update installeren')) return;
  const r = await act('update.install', {}, { msg: `Versie ${u.latest} downloaden en controleren...` });
  if (r) {
    document.body.innerHTML = '<div style="font:18px Lato,Segoe UI,sans-serif;color:#003f6b;text-align:center;margin-top:30vh">Bijwerken naar versie ' + u.latest + '...<br><small style="color:#5d6b7a">De app start zo vanzelf opnieuw.</small></div>';
  }
}

function UpdateBalk({ u, onLater }) {
  return (
    <div className="updbalk">
      <Download size={18} style={{ flex: 'none' }} />
      <div style={{ flex: 1 }}><b>Versie {u.latest} staat klaar</b> (je hebt {u.current}).{u.notes && u.notes.length ? ' ' + u.notes.slice(0, 2).join(' · ') : ''}</div>
      <Btn s v="p" icon={Download} onClick={() => installeerUpdate(u, false)}>Nu bijwerken</Btn>
      <Btn s onClick={onLater}>Later</Btn>
    </div>
  );
}

function Top({ user, info, onSwitch, onLogout, onAct, onHome, zoek, bel }) {
  return (
    <header className="top">
      <div className="logo" onClick={onHome} role={onHome ? 'button' : undefined} title={onHome ? 'Naar het startscherm' : undefined}
        style={onHome ? { cursor: 'pointer' } : undefined}><img src={logo} alt="Justdata" /></div>
      <div className="apptitle"><b>Microsoft 365 beheer</b><span>Full service ICT beheer</span></div>
      {zoek}
      <div className="spacer" />
      {info && (
        <button className="tswitch" onClick={onSwitch} title="Wissel van klant (Ctrl+K)">
          <Building2 size={22} style={{ flex: 'none' }} />
          <span className="tm">
            <span className="tl">Je werkt bij</span>
            <span className="tn" style={{ display: 'block' }}>{info.tenant}</span>
            <span className="td" style={{ display: 'block' }}>{info.defaultDomain}</span>
          </span>
          <span className="tb"><ArrowLeftRight size={15} />Wissel klant <kbd>Ctrl K</kbd></span>
        </button>
      )}
      <div className="spacer" />
      {bel}
      {onAct && <button className="topbtn" onClick={onAct} title="Wat heb ik gedaan in deze sessie?"><History size={16} />Activiteit</button>}
      {user && (
        <div className="acct"><b>{user.name}</b>{user.upn}</div>
      )}
      <button className="topbtn" onClick={onLogout} title="Afmelden"><LogOut size={16} />Afmelden</button>
    </header>
  );
}
