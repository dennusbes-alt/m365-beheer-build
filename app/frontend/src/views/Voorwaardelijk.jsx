// Voorwaardelijke toegang: beleid bekijken, bewerken, aanmaken, aan/uit en verwijderen, plus benoemde locaties (IP en landen).
import { useEffect, useMemo, useState } from 'react';
import { startTab } from '../store.jsx';
import { ExternalLink, Globe, MapPin, Pencil, Plus, RefreshCw, ShieldCheck, Trash2, X } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, askType, openModal } from '../overlays.jsx';
import { Btn, Card, Check, Chip, Loading, Picker, SearchBox, Tabs, dt, useFilter } from '../ui.jsx';

const STATUS = { enabled: ['Aan', 'g'], disabled: ['Uit', ''], enabledForReportingButNotEnforced: ['Alleen rapporteren', 'o'] };
const CONTROLES = [['mfa', 'MFA vereisen'], ['compliantDevice', 'Apparaat moet compliant zijn (Intune)'], ['domainJoinedDevice', 'Hybride Entra-apparaat'],
  ['approvedApplication', 'Goedgekeurde client-app'], ['compliantApplication', 'App-beveiligingsbeleid (MAM)'], ['passwordChange', 'Wachtwoord wijzigen']];
const PLATFORMS = [['windows', 'Windows'], ['macOS', 'macOS'], ['iOS', 'iOS/iPadOS'], ['android', 'Android'], ['linux', 'Linux'], ['windowsPhone', 'Windows Phone']];
const CLIENTS = [['browser', 'Browser'], ['mobileAppsAndDesktopClients', 'Mobiele apps en desktop-apps'], ['exchangeActiveSync', 'Exchange ActiveSync (oud)'], ['other', 'Andere clients (oud: POP, IMAP, SMTP)']];
const RISICO = [['low', 'Laag'], ['medium', 'Gemiddeld'], ['high', 'Hoog']];
const LANDEN = ('AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW').split(' ');
let landNaam = (c) => c;
try { const dn = new Intl.DisplayNames(['nl'], { type: 'region' }); landNaam = (c) => dn.of(c) || c; } catch { /* oude browser */ }

const LEEG = {
  name: '', state: 'enabledForReportingButNotEnforced',
  users: { include: 'all', includeUsers: [], includeGroups: [], includeRoles: [], excludeUsers: [], excludeGroups: [], excludeRoles: [], excludeGuests: false, excludeServiceProvider: true },
  apps: { include: 'all', includeApps: [], excludeApps: [], action: '' },
  clientAppTypes: [], platforms: { include: [], exclude: [] }, locations: { include: [], exclude: [] }, signInRisk: [], userRisk: [],
  grant: { block: false, controls: ['mfa'], operator: 'OR', strength: '' },
  session: { frequency: null, frequencyType: 'hours', everyTime: false, persistentBrowser: '', appEnforced: false },
};
const kopie = (o) => JSON.parse(JSON.stringify(o));
const met = (basis, extra) => { const m = kopie(LEEG); Object.entries(extra).forEach(([k, v]) => { m[k] = typeof v === 'object' && !Array.isArray(v) ? { ...m[k], ...v } : v; }); return { ...m, ...basis }; };

// Veelgebruikte sjablonen (Microsoft-aanbevelingen); starten altijd als 'Alleen rapporteren'
const SJABLONEN = [
  ['MFA voor alle gebruikers', 'Iedereen moet MFA gebruiken bij elke cloud-app.', () => met({ name: 'MFA voor alle gebruikers' }, {})],
  ['MFA voor beheerders', 'Beheerdersrollen altijd met MFA.', (rollen) => met({ name: 'MFA voor beheerders' }, {
    users: { include: 'select', includeRoles: rollen.filter((r) => /administrator$/i.test(r.name) && /^(Global|Security|Exchange|SharePoint|User|Billing|Conditional Access|Intune|Helpdesk|Privileged|Application|Cloud Application|Authentication)/i.test(r.name)).map((r) => r.id) } })],
  ['Oude authenticatie blokkeren', 'Blokkeert POP, IMAP, SMTP-auth en ActiveSync zonder moderne aanmelding.', () => met({ name: 'Oude authenticatie blokkeren', clientAppTypes: ['exchangeActiveSync', 'other'] }, { grant: { block: true, controls: [] } })],
  ['Alleen toegang vanuit toegestane landen', 'Blokkeert aanmelden buiten de gekozen landen (maak eerst een benoemde locatie met landen).', () => met({ name: 'Blokkeren buiten toegestane landen', locations: { include: ['All'], exclude: [] } }, { grant: { block: true, controls: [] } })],
  ['Beheerportals alleen met MFA', 'Azure-, Entra-, Microsoft 365- en Exchange-beheercentra met MFA.', () => met({ name: 'MFA voor Microsoft-beheerportals' }, { apps: { include: 'admin' } })],
  ['Beveiligingsgegevens registreren', 'MFA-methoden registreren alleen vanaf vertrouwde locaties of met MFA.', () => met({ name: 'Registreren beveiligingsgegevens beveiligen', locations: { include: ['All'], exclude: ['AllTrusted'] } }, { apps: { include: 'action', action: 'urn:user:registersecurityinfo' } })],
  ['Leeg beleid', 'Zelf alles instellen.', () => met({ name: '' }, {})],
];

export default function Voorwaardelijk() {
  const [tab, setTab] = useState(() => startTab('ca', 'beleid'));
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const laad = async (fresh) => {
    setFout('');
    try { setD(await api('ca.list', fresh ? { fresh: true } : {}, { quiet: true })); } catch (e) { setFout(e.message); setD((x) => x || null); }
  };
  useEffect(() => { laad(); }, []);
  if (fout && !d) return <Msg kind="err">{fout}</Msg>;
  if (!d) return <Loading text="Voorwaardelijke toegang ophalen..." />;
  return (
    <>
      <div className="headrow"><div className="m"><h2 style={{ margin: 0 }}>Voorwaardelijke toegang</h2>
        <p className="sub">Wie mag zich wanneer, waarvandaan en hoe aanmelden. Nieuw beleid start als 'Alleen rapporteren', zodat je veilig kunt testen.</p></div>
        <div className="btns">
          <Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn>
          <Btn s icon={ExternalLink} onClick={() => act('open.url', { url: d.portal }, { quiet: true })}>Entra-beheercentrum</Btn>
        </div></div>
      <Tabs value={tab} onChange={setTab} tabs={[['beleid', `Beleid (${d.policies.length})`, ShieldCheck], ['locaties', `Benoemde locaties (${d.locations.length})`, MapPin]]} />
      {fout && <Msg kind="err">{fout}</Msg>}
      {tab === 'beleid' ? <Beleid d={d} laad={laad} /> : <Locaties d={d} laad={laad} />}
    </>
  );
}

// ---------------------------------------------------------------- Beleid
function Beleid({ d, laad }) {
  const [q, setQ] = useState('');
  const lijst = useFilter(d.policies, q, (p) => [p.name, ...p.summary.who, ...p.summary.apps, ...p.summary.then]);
  const bewerk = async (p) => { if (await openModal((close) => <Editor d={d} start={p} close={close} />, { wide: true })) laad(true); };
  const nieuw = async () => {
    const keuze = await openModal((close) => (
      <>
        <h3>Nieuw beleid</h3>
        <p className="hint">Kies een startpunt. Nieuw beleid start altijd als <b>Alleen rapporteren</b>: er wordt niets geblokkeerd tot je het aanzet.</p>
        <div className="list" style={{ maxHeight: 420 }}>
          {SJABLONEN.map(([t, uitleg, fn]) => <div key={t} className="li" onClick={() => close(fn(d.roles))}><span className="m"><b>{t}</b><small>{uitleg}</small></span></div>)}
        </div>
        <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn></div>
      </>));
    if (keuze) bewerk(keuze);
  };
  const zet = async (p, state) => {
    if (state === 'enabled' && p.grant.block && p.users.include === 'all' && !(await ask(`'${p.name}' blokkeert toegang voor alle gebruikers. Weet je zeker dat je het aanzet? Controleer eerst in 'Alleen rapporteren' wie geraakt wordt.`, 'Aanzetten', true))) return;
    if (await act('ca.state', { id: p.id, state, name: p.name }, { msg: 'Status wijzigen...' })) laad(true);
  };
  const weg = async (p) => {
    if (!(await askType(`Beleid '${p.name}' definitief verwijderen? Dit kan niet ongedaan gemaakt worden.`, 'VERWIJDER'))) return;
    if (await act('ca.delete', { id: p.id, name: p.name }, { msg: 'Verwijderen...' })) laad(true);
  };
  return (
    <Card>
      <div className="btns" style={{ marginBottom: 10 }}>
        <div style={{ flex: 1 }}><SearchBox value={q} onChange={setQ} placeholder="Zoek beleid..." /></div>
        <Btn v="p" icon={Plus} onClick={nieuw}>Nieuw beleid</Btn>
      </div>
      {!d.policies.length && <Msg kind="info">Er is nog geen beleid voor voorwaardelijke toegang. Begin bijvoorbeeld met 'MFA voor alle gebruikers'.</Msg>}
      <table>
        <thead><tr><th>Beleid</th><th>Wie</th><th>Apps</th><th>Dan</th><th>Status</th><th /></tr></thead>
        <tbody>
          {lijst.map((p) => (
            <tr key={p.id}>
              <td><button className="linkknop" style={{ fontWeight: 800, textAlign: 'left' }} onClick={() => bewerk(p)}>{p.name}</button>
                <div className="hint">{[...p.summary.conditions, ...(p.modified ? [`gewijzigd ${dt(p.modified)}`] : [])].join(' · ')}</div></td>
              <td>{p.summary.who.join(', ')}{p.summary.except.length > 0 && <div className="hint">behalve {p.summary.except.join(', ')}</div>}</td>
              <td>{p.summary.apps.join(', ')}</td>
              <td>{p.summary.then.map((t) => <Chip key={t} k={t === 'Blokkeren' ? 'r' : ''}>{t}</Chip>)}</td>
              <td>
                <select value={p.state} onChange={(e) => zet(p, e.target.value)}>
                  {Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </td>
              <td className="r" style={{ whiteSpace: 'nowrap' }}>
                <Btn s icon={Pencil} onClick={() => bewerk(p)}>Bewerken</Btn>
                <Btn s v="dl" icon={Trash2} onClick={() => weg(p)} />
              </td>
            </tr>))}
        </tbody>
      </table>
    </Card>
  );
}

// Gekozen items als chips + zoeklijst om toe te voegen
function Kies({ label, items, value, onChange, names, placeholder }) {
  const [open, setOpen] = useState(false);
  const beschikbaar = useMemo(() => (items || []).filter((i) => !value.includes(i.v)), [items, value]);
  return (
    <div style={{ marginBottom: 8 }}>
      <label className="f">{label}</label>
      <div className="btns" style={{ minHeight: 28 }}>
        {value.map((v) => <Chip key={v}>{names[v] || (items || []).find((i) => i.v === v)?.l || v} <button className="linkknop" onClick={() => onChange(value.filter((x) => x !== v))}><X size={11} /></button></Chip>)}
        <Btn s icon={Plus} onClick={() => setOpen(!open)}>{open ? 'Klaar' : 'Toevoegen'}</Btn>
      </div>
      {open && (items ? <Picker items={beschikbaar} placeholder={placeholder} height={180} onPick={(i) => onChange([...value, i.v])} /> : <Loading />)}
    </div>
  );
}

const Keuze = ({ opties, value, onChange }) => (
  <div className="btns">{opties.map(([k, l]) => <Btn key={k} s v={value === k ? 'p' : ''} onClick={() => onChange(k)}>{l}</Btn>)}</div>
);

const Vinkjes = ({ opties, value, onChange }) => (
  <div className="btns">{opties.map(([k, l]) => <Check key={k} checked={value.includes(k)} onChange={(on) => onChange(on ? [...value, k] : value.filter((x) => x !== k))}>{l}</Check>)}</div>
);

function Editor({ d, start, close }) {
  const [m, setM] = useState(() => kopie(start));
  const [stap, setStap] = useState('wie');
  const [users, setUsers] = useState(null);
  const [groepen, setGroepen] = useState(null);
  const [apps, setApps] = useState(null);
  useEffect(() => {
    api('users', {}, { quiet: true }).then((r) => setUsers(r.users.map((u) => ({ v: u.id, l: u.name, s: u.upn })))).catch(() => setUsers([]));
    api('groups.list', { fresh: false }, { quiet: true }).then((r) => setGroepen(r.groups.filter((g) => ['M365', 'Beveiliging', 'Dynamisch'].includes(g.type)).map((g) => ({ v: g.id, l: g.name, s: g.type })))).catch(() => setGroepen([]));
  }, []);
  useEffect(() => { if (stap === 'apps' && !apps) api('ca.apps', {}, { quiet: true }).then((r) => setApps(r.apps.map((a) => ({ v: a.id, l: a.name, s: a.id })))).catch(() => setApps([])); }, [stap, apps]);
  const z = (deel, veld) => (v) => setM((x) => ({ ...x, [deel]: veld ? { ...x[deel], [veld]: v } : v }));
  const rollen = d.roles.map((r) => ({ v: r.id, l: r.name }));
  const locs = [{ v: 'AllTrusted', l: 'Alle vertrouwde locaties' }, ...d.locations.map((l) => ({ v: l.id, l: l.name, s: l.type === 'ip' ? `IP: ${l.ranges.slice(0, 3).join(', ')}` : `Landen: ${l.countries.slice(0, 6).map(landNaam).join(', ')}` }))];
  const n = d.names;
  const u = m.users;
  const g = m.grant;
  const s = m.session;
  const allesBlok = g.block && u.include === 'all' && m.apps.include === 'all';
  const opslaan = async () => {
    if (m.state === 'enabled' && allesBlok && !(await ask('Dit beleid blokkeert ALLE gebruikers voor ALLE apps. Daarmee kan iedereen buitengesloten worden. Toch aanzetten?', 'Ja, opslaan', true))) return;
    if (m.state === 'enabled' && u.include === 'all' && !u.excludeServiceProvider && !(await ask('Beheerders van Justdata (GDAP) zijn niet uitgesloten. Als dit beleid hen blokkeert, kan Justdata deze klant niet meer beheren. Toch opslaan?', 'Opslaan', true))) return;
    if (await act('ca.save', { policy: m }, { msg: 'Beleid opslaan...' })) close(true);
  };
  return (
    <>
      <h3>{m.id ? 'Beleid bewerken' : 'Nieuw beleid'}</h3>
      <label className="f">Naam</label>
      <input type="text" value={m.name} onChange={(e) => z('name')(e.target.value)} placeholder="Bijv. MFA voor alle gebruikers" autoFocus={!m.id} />
      <label className="f">Status</label>
      <Keuze opties={Object.entries(STATUS).map(([k, [l]]) => [k, l])} value={m.state} onChange={z('state')} />
      <div className="hint">Alleen rapporteren: Microsoft logt wat er zou gebeuren (aanmeldlogboek), zonder iemand te blokkeren. Zo test je veilig.</div>
      <div style={{ margin: '12px 0' }}>
        <Tabs value={stap} onChange={setStap} tabs={[['wie', 'Wie'], ['apps', 'Apps'], ['voorwaarden', 'Voorwaarden'], ['toegang', 'Toegang'], ['sessie', 'Sessie']]} />
      </div>

      {stap === 'wie' && <>
        <label className="f">Van toepassing op</label>
        <Keuze opties={[['all', 'Alle gebruikers'], ['select', 'Gekozen gebruikers, groepen of rollen'], ['guests', 'Gasten en externe gebruikers'], ['none', 'Niemand']]} value={u.include} onChange={z('users', 'include')} />
        {u.include === 'select' && <>
          <Kies label="Gebruikers" items={users} value={u.includeUsers} onChange={z('users', 'includeUsers')} names={n} placeholder="Zoek gebruiker..." />
          <Kies label="Groepen" items={groepen} value={u.includeGroups} onChange={z('users', 'includeGroups')} names={n} placeholder="Zoek groep..." />
          <Kies label="Beheerdersrollen" items={rollen} value={u.includeRoles} onChange={z('users', 'includeRoles')} names={n} placeholder="Zoek rol..." />
        </>}
        <label className="f" style={{ marginTop: 14 }}><b>Uitsluiten</b></label>
        <Check checked={u.excludeServiceProvider} onChange={z('users', 'excludeServiceProvider')}><b>Beheerders van Justdata (GDAP) uitsluiten</b> (aanbevolen, anders kan Justdata buitengesloten worden)</Check>
        <Check checked={u.excludeGuests} onChange={z('users', 'excludeGuests')}>Gasten en externe gebruikers uitsluiten</Check>
        <Kies label="Gebruikers uitsluiten (bijv. noodaccount)" items={users} value={u.excludeUsers} onChange={z('users', 'excludeUsers')} names={n} placeholder="Zoek gebruiker..." />
        <Kies label="Groepen uitsluiten" items={groepen} value={u.excludeGroups} onChange={z('users', 'excludeGroups')} names={n} placeholder="Zoek groep..." />
        <Kies label="Rollen uitsluiten" items={rollen} value={u.excludeRoles} onChange={z('users', 'excludeRoles')} names={n} placeholder="Zoek rol..." />
      </>}

      {stap === 'apps' && <>
        <label className="f">Doel</label>
        <Keuze opties={[['all', 'Alle cloud-apps'], ['office', 'Office 365'], ['admin', 'Microsoft-beheerportals'], ['select', 'Gekozen apps'], ['action', 'Gebruikersactie']]} value={m.apps.include} onChange={z('apps', 'include')} />
        {m.apps.include === 'select' && <Kies label="Apps" items={apps} value={m.apps.includeApps} onChange={z('apps', 'includeApps')} names={n} placeholder="Zoek app..." />}
        {m.apps.include === 'action' && <Keuze opties={[['urn:user:registersecurityinfo', 'Beveiligingsgegevens registreren'], ['urn:user:registerdevice', 'Apparaat registreren of koppelen']]}
          value={m.apps.action || 'urn:user:registersecurityinfo'} onChange={z('apps', 'action')} />}
        {m.apps.include !== 'action' && m.apps.include !== 'none' && <Kies label="Apps uitsluiten" items={apps} value={m.apps.excludeApps} onChange={z('apps', 'excludeApps')} names={n} placeholder="Zoek app..." />}
      </>}

      {stap === 'voorwaarden' && <>
        <label className="f">Locaties</label>
        <Keuze opties={[['', 'Niet gebruiken'], ['All', 'Alle locaties'], ['sel', 'Gekozen locaties']]}
          value={!m.locations.include.length ? '' : m.locations.include.includes('All') ? 'All' : 'sel'}
          onChange={(k) => z('locations')({ include: k === 'All' ? ['All'] : k === 'sel' ? ['AllTrusted'] : [], exclude: k ? m.locations.exclude : [] })} />
        {m.locations.include.length > 0 && !m.locations.include.includes('All') &&
          <Kies label="Van toepassing op locaties" items={locs} value={m.locations.include} onChange={(v) => z('locations')({ ...m.locations, include: v })} names={n} placeholder="Zoek locatie..." />}
        {m.locations.include.length > 0 && <Kies label="Locaties uitsluiten (bijv. kantoor of toegestane landen)" items={locs} value={m.locations.exclude} onChange={(v) => z('locations')({ ...m.locations, exclude: v })} names={n} placeholder="Zoek locatie..." />}
        {!d.locations.length && <div className="hint">Nog geen benoemde locaties: maak ze aan op het tabblad Benoemde locaties.</div>}
        <label className="f">Apparaatplatforms (leeg = alle)</label>
        <Vinkjes opties={PLATFORMS} value={m.platforms.include.filter((x) => x !== 'all')} onChange={(v) => z('platforms')({ include: v, exclude: [] })} />
        <label className="f">Client-apps (leeg = alle)</label>
        <Vinkjes opties={CLIENTS} value={m.clientAppTypes} onChange={z('clientAppTypes')} />
        <label className="f">Aanmeldrisico (vereist Entra ID P2)</label>
        <Vinkjes opties={RISICO} value={m.signInRisk} onChange={z('signInRisk')} />
        <label className="f">Gebruikersrisico (vereist Entra ID P2)</label>
        <Vinkjes opties={RISICO} value={m.userRisk} onChange={z('userRisk')} />
      </>}

      {stap === 'toegang' && <>
        <Keuze opties={[['blok', 'Toegang blokkeren'], ['ok', 'Toegang verlenen met vereisten']]} value={g.block ? 'blok' : 'ok'} onChange={(k) => z('grant', 'block')(k === 'blok')} />
        {!g.block && <>
          <label className="f">Vereisten</label>
          {CONTROLES.map(([k, l]) => <Check key={k} checked={g.controls.includes(k)} disabled={k === 'mfa' && !!g.strength}
            onChange={(on) => z('grant', 'controls')(on ? [...g.controls, k] : g.controls.filter((x) => x !== k))}>{l}</Check>)}
          <label className="f">Authenticatiesterkte (in plaats van gewone MFA)</label>
          <select value={g.strength} onChange={(e) => z('grant', 'strength')(e.target.value)}>
            <option value="">Niet gebruiken</option>
            {d.strengths.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
          {g.controls.length + (g.strength ? 1 : 0) > 1 && <>
            <label className="f">Bij meerdere vereisten</label>
            <Keuze opties={[['AND', 'Alle vereisten'], ['OR', 'Eén van de vereisten']]} value={g.operator} onChange={z('grant', 'operator')} />
          </>}
        </>}
        {allesBlok && <Msg kind="err">Let op: dit blokkeert alle gebruikers voor alle apps. Sluit minstens een noodaccount en Justdata (GDAP) uit.</Msg>}
      </>}

      {stap === 'sessie' && <>
        <Check checked={!!s.frequency || s.everyTime} onChange={(on) => z('session')({ ...s, frequency: on ? 8 : null, everyTime: false })}>Aanmeldfrequentie: opnieuw aanmelden na een tijd</Check>
        {(!!s.frequency || s.everyTime) && <div className="btns" style={{ marginLeft: 26 }}>
          <Check checked={s.everyTime} onChange={(on) => z('session')({ ...s, everyTime: on, frequency: on ? null : 8 })}>Elke keer</Check>
          {!s.everyTime && <>
            <input type="number" min="1" max={s.frequencyType === 'days' ? 365 : 23} value={s.frequency || ''} style={{ width: 80 }} onChange={(e) => z('session', 'frequency')(Number(e.target.value) || null)} />
            <select value={s.frequencyType} onChange={(e) => z('session', 'frequencyType')(e.target.value)}><option value="hours">uur</option><option value="days">dagen</option></select>
          </>}
        </div>}
        <label className="f">Aangemeld blijven in de browser</label>
        <Keuze opties={[['', 'Niet instellen'], ['always', 'Altijd aangemeld blijven'], ['never', 'Nooit aangemeld blijven']]} value={s.persistentBrowser} onChange={z('session', 'persistentBrowser')} />
        <div className="hint">'Aangemeld blijven' werkt alleen als het beleid geldt voor alle cloud-apps.</div>
        <Check checked={s.appEnforced} onChange={z('session', 'appEnforced')}>Door de app afgedwongen beperkingen (bijv. SharePoint/Exchange beperkt op onbeheerde apparaten)</Check>
      </>}

      <div className="foot">
        <Btn onClick={() => close(false)}>Annuleren</Btn>
        <Btn v="p" icon={ShieldCheck} onClick={opslaan}>{m.id ? 'Opslaan' : 'Aanmaken'}</Btn>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- Benoemde locaties
function Locaties({ d, laad }) {
  const bewerk = async (l) => { if (await openModal((close) => <LocatieEditor start={l} close={close} />, { wide: true })) laad(true); };
  const weg = async (l) => {
    if (!(await ask(`Benoemde locatie '${l.name}' verwijderen? Dit lukt alleen als geen enkel beleid hem gebruikt.`, 'Verwijderen', true))) return;
    if (await act('ca.loc.delete', { id: l.id, name: l.name }, { msg: 'Verwijderen...' })) laad(true);
  };
  return (
    <Card>
      <div className="btns" style={{ marginBottom: 10 }}>
        <Btn v="p" icon={Plus} onClick={() => bewerk({ type: 'ip', name: '', trusted: true, ranges: [], countries: [], unknown: false, method: 'clientIpAddress' })}>IP-adressen</Btn>
        <Btn v="p" icon={Globe} onClick={() => bewerk({ type: 'country', name: '', trusted: false, ranges: [], countries: ['NL'], unknown: false, method: 'clientIpAddress' })}>Landen</Btn>
      </div>
      {!d.locations.length && <Msg kind="info">Nog geen benoemde locaties. Voeg bijvoorbeeld het kantoor-IP toe (vertrouwd), of een lijst met toegestane landen.</Msg>}
      <table>
        <thead><tr><th>Naam</th><th>Soort</th><th>Inhoud</th><th /></tr></thead>
        <tbody>
          {d.locations.map((l) => (
            <tr key={l.id}>
              <td><button className="linkknop" style={{ fontWeight: 800 }} onClick={() => bewerk(l)}>{l.name}</button>{l.trusted && <> <Chip k="g">Vertrouwd</Chip></>}</td>
              <td>{l.type === 'ip' ? 'IP-adressen' : 'Landen'}</td>
              <td className="hint">{l.type === 'ip' ? l.ranges.join(', ') : l.countries.map(landNaam).join(', ') + (l.unknown ? ' + onbekende landen' : '')}</td>
              <td className="r" style={{ whiteSpace: 'nowrap' }}><Btn s icon={Pencil} onClick={() => bewerk(l)}>Bewerken</Btn><Btn s v="dl" icon={Trash2} onClick={() => weg(l)} /></td>
            </tr>))}
        </tbody>
      </table>
    </Card>
  );
}

function LocatieEditor({ start, close }) {
  const [l, setL] = useState(() => ({ ...start, tekst: (start.ranges || []).join('\n') }));
  const [q, setQ] = useState('');
  const z = (k) => (v) => setL((x) => ({ ...x, [k]: v }));
  const landen = useMemo(() => LANDEN.map((c) => ({ c, n: landNaam(c) })).sort((a, b) => a.n.localeCompare(b.n, 'nl')), []);
  const getoond = useFilter(landen, q, (x) => [x.n, x.c]);
  const opslaan = async () => {
    const body = { id: l.id, type: l.type, name: l.name, trusted: l.trusted, ranges: l.tekst.split(/[\s,;]+/).filter(Boolean), countries: l.countries, unknown: l.unknown, method: l.method };
    if (await act('ca.loc.save', body, { msg: 'Locatie opslaan...' })) close(true);
  };
  return (
    <>
      <h3>{l.id ? 'Locatie bewerken' : l.type === 'ip' ? 'Nieuwe locatie: IP-adressen' : 'Nieuwe locatie: landen'}</h3>
      <label className="f">Naam</label>
      <input type="text" value={l.name} onChange={(e) => z('name')(e.target.value)} placeholder={l.type === 'ip' ? 'Bijv. Kantoor Amsterdam' : 'Bijv. Toegestane landen'} autoFocus />
      {l.type === 'ip' ? <>
        <label className="f">IP-adressen of bereiken (één per regel)</label>
        <textarea rows={6} value={l.tekst} onChange={(e) => z('tekst')(e.target.value)} placeholder={'203.0.113.10\n198.51.100.0/24\n2001:db8::/48'} />
        <div className="hint">Een los adres wordt /32. IPv6 mag ook.</div>
        <Check checked={l.trusted} onChange={z('trusted')}>Markeren als vertrouwde locatie (telt mee bij 'Alle vertrouwde locaties' en verlaagt het aanmeldrisico)</Check>
      </> : <>
        <label className="f">Landen ({l.countries.length} gekozen)</label>
        <div className="btns" style={{ minHeight: 28 }}>{l.countries.map((c) => <Chip key={c}>{landNaam(c)} <button className="linkknop" onClick={() => z('countries')(l.countries.filter((x) => x !== c))}><X size={11} /></button></Chip>)}</div>
        <SearchBox value={q} onChange={setQ} placeholder="Zoek land..." />
        <div className="list" style={{ maxHeight: 220 }}>
          {getoond.map((x) => (
            <label key={x.c} className="li"><input type="checkbox" checked={l.countries.includes(x.c)} onChange={(e) => z('countries')(e.target.checked ? [...l.countries, x.c] : l.countries.filter((y) => y !== x.c))} />
              <span className="m"><b>{x.n}</b><small>{x.c}</small></span></label>))}
        </div>
        <Check checked={l.unknown} onChange={z('unknown')}>Ook onbekende landen/regio's meenemen (IP-adressen zonder land)</Check>
        <label className="f">Land bepalen via</label>
        <Keuze opties={[['clientIpAddress', 'IP-adres (standaard)'], ['authenticatorAppGps', 'GPS van de Authenticator-app']]} value={l.method} onChange={z('method')} />
      </>}
      <div className="foot">
        <Btn onClick={() => close(false)}>Annuleren</Btn>
        <Btn v="p" icon={MapPin} onClick={opslaan}>Opslaan</Btn>
      </div>
    </>
  );
}
