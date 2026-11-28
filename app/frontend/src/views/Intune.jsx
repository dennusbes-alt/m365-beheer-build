// Intune-beheer: configuratieprofielen, apps en inschrijving (Windows, Windows Hello, Android).
import { useEffect, useMemo, useState } from 'react';
import { startTab } from '../store.jsx';
import { AppWindow, Fingerprint, KeyRound, Laptop, Plus, QrCode, RefreshCw, Save, ShieldCheck, Smartphone, Trash2, Users } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, openModal, toast } from '../overlays.jsx';
import { Btn, Card, Check, Chip, Loading, Picker, SearchBox, Tabs, dt, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';

const INTENT = { required: ['Verplicht', 'g'], available: ['Beschikbaar', ''], uninstall: ['Verwijderen', 'r'], availableWithoutEnrollment: ['Beschikbaar (zonder inschrijving)', ''] };

// Toewijzingen als chips
function Doelen({ lijst, app }) {
  if (!lijst || !lijst.length) return <Chip k="o">Niet toegewezen</Chip>;
  return lijst.map((a, i) => (
    <Chip key={i} k={a.kind === 'exclude' ? 'r' : app ? (INTENT[a.intent] || ['', 'mu'])[1] : 'g'}>
      {a.kind === 'exclude' ? 'Uitgesloten: ' : app && INTENT[a.intent] ? `${INTENT[a.intent][0]}: ` : ''}{a.name}</Chip>));
}

// Venster om toewijzingen te bewerken (profiel of app)
function Toewijzen({ titel, huidig, app, close }) {
  const [lijst, setLijst] = useState(huidig.map((a) => ({ ...a })));
  const [groepen, setGroepen] = useState(null);
  const [intent, setIntent] = useState('required');
  const [soort, setSoort] = useState('group');
  useEffect(() => { api('groups.list', { fresh: false }, { quiet: true }).then((r) => setGroepen(r.groups.filter((g) => ['M365', 'Beveiliging', 'Dynamisch'].includes(g.type)))).catch(() => setGroepen([])); }, []);
  const voeg = (a) => setLijst((l) => [...l.filter((x) => !(x.kind === a.kind && x.groupId === a.groupId)), a]);
  return (
    <>
      <h3>Toewijzen: {titel}</h3>
      <label className="f">Huidige toewijzingen</label>
      <table><tbody>
        {lijst.map((a, i) => (
          <tr key={i}><td>{a.kind === 'exclude' ? <Chip k="r">Uitsluiten</Chip> : app ? <Chip k={(INTENT[a.intent] || ['', ''])[1]}>{(INTENT[a.intent] || [a.intent])[0]}</Chip> : <Chip k="g">Toegewezen</Chip>}</td>
            <td><b>{a.name}</b></td><td className="r"><Btn s v="dl" icon={Trash2} onClick={() => setLijst((l) => l.filter((_, n) => n !== i))}>Weg</Btn></td></tr>))}
        {!lijst.length && <tr><td className="hint">Nog niets: het {app ? 'app' : 'profiel'} wordt dan nergens toegepast.</td></tr>}
      </tbody></table>
      <label className="f">Toevoegen</label>
      <div className="btns">
        {app && Object.entries(INTENT).filter(([k]) => k !== 'availableWithoutEnrollment').map(([k, [l]]) => <Btn key={k} s v={intent === k ? 'p' : ''} onClick={() => setIntent(k)}>{l}</Btn>)}
        <Btn s v={soort === 'group' ? 'p' : ''} onClick={() => setSoort('group')}>Groep</Btn>
        <Btn s v={soort === 'exclude' ? 'p' : ''} onClick={() => setSoort('exclude')}>Groep uitsluiten</Btn>
        <Btn s onClick={() => voeg({ kind: 'all_users', name: 'Alle gebruikers', intent })}>+ Alle gebruikers</Btn>
        <Btn s onClick={() => voeg({ kind: 'all_devices', name: 'Alle apparaten', intent })}>+ Alle apparaten</Btn>
      </div>
      {!groepen ? <Loading text="Groepen ophalen..." /> : (
        <div style={{ marginTop: 8 }}><Picker items={groepen.map((g) => ({ v: g.id, l: g.name, s: g.type }))} placeholder={soort === 'exclude' ? 'Zoek groep om uit te sluiten...' : 'Zoek groep om toe te wijzen...'} height={200}
          onPick={(i) => voeg({ kind: soort, groupId: i.v, name: i.l, intent })} /></div>)}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button><button className="btn p" onClick={() => close(lijst)}>Opslaan</button></div>
    </>
  );
}

// ---------------------------------------------------------------- Configuratieprofielen
export function Profielen() {
  const [d, setD] = useState(null);
  const [q, setQ] = useState('');
  const [plat, setPlat] = useState('');
  const [sel, setSel] = useState(null);
  const laad = async (fresh) => { try { setD(await api('in.profiles', { fresh: !!fresh }, { quiet: true })); } catch (e) { toast(e.message, 'e'); setD({ profiles: [], error: e.message }); } };
  useEffect(() => { laad(false); }, []);
  const plats = useMemo(() => [...new Set((d?.profiles || []).map((p) => p.platform))].sort(), [d]);
  const shown = useFilter(d?.profiles || [], q, (p) => [p.name, p.type, p.template, p.platform, p.desc]).filter((p) => !plat || p.platform === plat);
  if (!d) return <Loading text="Configuratieprofielen ophalen..." />;
  const p = sel && d.profiles.find((x) => x.id === sel);
  return (
    <>
      <h2>Configuratieprofielen</h2>
      <p className="sub">Alle Intune-profielen op één plek: sjablonen, settings catalog, beheersjablonen (ADMX), endpoint security en nalevingsbeleid. Toewijzen, status bekijken en opruimen.</p>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      {d.partial?.length > 0 && <Msg kind="info">Niet alle soorten konden worden opgehaald ({d.partial.join(', ')}).</Msg>}
      <div className="cols">
        <div className="sticky">
          <SearchBox value={q} onChange={setQ} placeholder="Zoek profiel..." />
          <div className="row" style={{ marginTop: 8 }}>
            <select value={plat} onChange={(e) => setPlat(e.target.value)}><option value="">Alle platforms</option>{plats.map((x) => <option key={x}>{x}</option>)}</select>
            <Btn s icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
          </div>
          <div className="list" style={{ maxHeight: 'calc(100vh - 330px)' }}>
            {shown.slice(0, MAX_RIJEN).map((x) => (
              <div key={x.id} className={`li ${sel === x.id ? 'on' : ''}`} onClick={() => setSel(x.id)}>
                <ShieldCheck size={15} style={{ flex: 'none', color: x.assignments.length ? 'var(--gr)' : 'var(--mu)' }} />
                <span className="m"><b>{x.name}</b><small>{x.platform} · {x.type}{x.assignments.length ? '' : ' · niet toegewezen'}</small></span>
              </div>))}
            {!shown.length && <div className="li empty">Geen profielen gevonden.</div>}
          </div>
          <Meer totaal={shown.length} />
        </div>
        <div>{p ? <ProfielDetail key={p.id} p={p} opnieuw={() => laad(true)} weg={() => { setSel(null); laad(true); }} /> : <Card><div className="hint">Kies een profiel.</div></Card>}</div>
      </div>
    </>
  );
}

function ProfielDetail({ p, opnieuw, weg }) {
  const [st, setSt] = useState(undefined);
  useEffect(() => { if (['dc', 'cp'].includes(p.kind)) api('in.profile.status', { kind: p.kind, id: p.id }, { quiet: true }).then((r) => setSt(r.overview)).catch(() => setSt(null)); else setSt(null); }, [p.id, p.kind]);
  const toewijzen = async () => {
    const l = await openModal((close) => <Toewijzen titel={p.name} huidig={p.assignments} close={close} />);
    if (l && await act('in.profile.assign', { kind: p.kind, id: p.id, name: p.name, assignments: l }, { msg: 'Toewijzingen opslaan...' })) opnieuw();
  };
  const verwijder = async () => { if (await ask(`Profiel "${p.name}" verwijderen? Apparaten krijgen de instellingen dan niet meer.`, 'Verwijderen', true) && await act('in.profile.delete', { kind: p.kind, id: p.id, name: p.name }, { msg: 'Verwijderen...' })) weg(); };
  return (
    <Card title={p.name} icon={ShieldCheck} right={<Chip>{p.type}</Chip>}>
      {p.desc && <div className="hint" style={{ marginTop: 0 }}>{p.desc}</div>}
      <table><tbody>
        <tr><td className="hint">Platform</td><td>{p.platform}</td></tr>
        <tr><td className="hint">Soort</td><td>{p.template}</td></tr>
        <tr><td className="hint">Gewijzigd</td><td>{dt(p.modified)}</td></tr>
        <tr><td className="hint">Toegewezen aan</td><td><Doelen lijst={p.assignments} /></td></tr>
      </tbody></table>
      {st === undefined && ['dc', 'cp'].includes(p.kind) && <Loading text="Status per apparaat ophalen..." />}
      {st && (
        <div className="btns" style={{ marginTop: 10 }}>
          <Chip k="g">{st.success} geslaagd</Chip>{st.error > 0 && <Chip k="r">{st.error} fout</Chip>}{st.conflict > 0 && <Chip k="o">{st.conflict} conflict</Chip>}
          {st.pending > 0 && <Chip k="mu">{st.pending} in behandeling</Chip>}{st.na > 0 && <Chip k="mu">{st.na} niet van toepassing</Chip>}
        </div>)}
      <div className="btns" style={{ marginTop: 14 }}>
        <Btn v="p" icon={Users} onClick={toewijzen}>Toewijzingen wijzigen</Btn>
        <Btn v="dl" icon={Trash2} onClick={verwijder}>Verwijderen</Btn>
      </div>
      <div className="hint">De instellingen zelf wijzig je in het Intune-beheercentrum; hier beheer je wie het profiel krijgt.</div>
    </Card>
  );
}

// ---------------------------------------------------------------- Apps
export function Apps() {
  const [d, setD] = useState(null);
  const [q, setQ] = useState('');
  const [plat, setPlat] = useState('');
  const [sel, setSel] = useState(null);
  const laad = async (fresh) => { try { setD(await api('in.apps', { fresh: !!fresh }, { quiet: true })); } catch (e) { toast(e.message, 'e'); setD({ apps: [], error: e.message }); } };
  useEffect(() => { laad(false); }, []);
  const plats = useMemo(() => [...new Set((d?.apps || []).map((p) => p.platform))].sort(), [d]);
  const shown = useFilter(d?.apps || [], q, (p) => [p.name, p.publisher, p.type]).filter((p) => !plat || p.platform === plat);
  if (!d) return <Loading text="Apps ophalen..." />;
  const a = sel && d.apps.find((x) => x.id === sel);
  const toevoegen = async () => { const r = await openModal((close) => <AppToevoegen close={close} />, { wide: true }); if (r) { setD(null); laad(true); } };
  return (
    <>
      <div className="headrow"><div className="m"><h2 style={{ margin: 0 }}>Apps</h2>
        <p className="sub">Intune-apps: wie krijgt welke app (verplicht, beschikbaar of verwijderen), installatiestatus en nieuwe apps toevoegen.</p></div>
        <Btn v="p" icon={Plus} onClick={toevoegen}>App toevoegen</Btn></div>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      <div className="cols">
        <div className="sticky">
          <SearchBox value={q} onChange={setQ} placeholder="Zoek app..." />
          <div className="row" style={{ marginTop: 8 }}>
            <select value={plat} onChange={(e) => setPlat(e.target.value)}><option value="">Alle platforms</option>{plats.map((x) => <option key={x}>{x}</option>)}</select>
            <Btn s icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
          </div>
          <div className="list" style={{ maxHeight: 'calc(100vh - 330px)' }}>
            {shown.slice(0, MAX_RIJEN).map((x) => (
              <div key={x.id} className={`li ${sel === x.id ? 'on' : ''}`} onClick={() => setSel(x.id)}>
                <AppWindow size={15} style={{ flex: 'none', color: x.assignments.length ? 'var(--gr)' : 'var(--mu)' }} />
                <span className="m"><b>{x.name}</b><small>{x.platform} · {x.type}{x.assignments.length ? '' : ' · niet toegewezen'}</small></span>
              </div>))}
            {!shown.length && <div className="li empty">Geen apps gevonden.</div>}
          </div>
          <Meer totaal={shown.length} />
        </div>
        <div>{a ? <AppDetail key={a.id} a={a} opnieuw={() => laad(true)} weg={() => { setSel(null); laad(true); }} /> : <Card><div className="hint">Kies een app.</div></Card>}</div>
      </div>
    </>
  );
}

function AppDetail({ a, opnieuw, weg }) {
  const [st, setSt] = useState(undefined);
  useEffect(() => { api('in.app.status', { id: a.id }, { quiet: true }).then((r) => setSt(r.summary)).catch(() => setSt(null)); }, [a.id]);
  const toewijzen = async () => {
    const l = await openModal((close) => <Toewijzen titel={a.name} huidig={a.assignments} app close={close} />);
    if (l && await act('in.app.assign', { id: a.id, name: a.name, assignments: l }, { msg: 'Toewijzingen opslaan...' })) opnieuw();
  };
  const verwijder = async () => { if (await ask(`App "${a.name}" uit Intune verwijderen? Hij wordt dan niet meer uitgerold (al geïnstalleerde apps blijven staan).`, 'Verwijderen', true) && await act('in.app.delete', { id: a.id, name: a.name }, { msg: 'Verwijderen...' })) weg(); };
  return (
    <Card title={a.name} icon={AppWindow} right={<Chip>{a.type}</Chip>}>
      <table><tbody>
        <tr><td className="hint">Uitgever</td><td>{a.publisher || '-'}</td></tr>
        <tr><td className="hint">Platform</td><td>{a.platform}</td></tr>
        <tr><td className="hint">Toegevoegd</td><td>{dt(a.created)}</td></tr>
        <tr><td className="hint">Toegewezen aan</td><td><Doelen lijst={a.assignments} app /></td></tr>
      </tbody></table>
      {st === undefined && <Loading text="Installatiestatus ophalen..." />}
      {st && (
        <div className="btns" style={{ marginTop: 10 }}>
          <Chip k="g">{st.installed} geïnstalleerd</Chip>{st.failed > 0 && <Chip k="r">{st.failed} mislukt</Chip>}{st.pending > 0 && <Chip k="o">{st.pending} bezig</Chip>}
          {st.notInstalled > 0 && <Chip k="mu">{st.notInstalled} niet geïnstalleerd</Chip>}{st.na > 0 && <Chip k="mu">{st.na} niet van toepassing</Chip>}
        </div>)}
      <div className="btns" style={{ marginTop: 14 }}>
        <Btn v="p" icon={Users} onClick={toewijzen}>Toewijzingen wijzigen</Btn>
        <Btn v="dl" icon={Trash2} onClick={verwijder}>Verwijderen</Btn>
      </div>
    </Card>
  );
}

function AppToevoegen({ close }) {
  const [soort, setSoort] = useState('store');
  const [q, setQ] = useState('');
  const [res, setRes] = useState(null);
  const [keuze, setKeuze] = useState(null);
  const [alsGebruiker, setAlsGebruiker] = useState(false);
  const [m365, setM365] = useState({ shared: false, english: false, access: false, publisherApp: false });
  const [iedereen, setIedereen] = useState(true);
  const zoek = async () => { setRes(null); try { setRes((await api('in.store.search', { q }, { quiet: true })).results); } catch (e) { toast(e.message, 'e'); setRes([]); } };
  const opslaan = async () => {
    if (soort === 'store' && !keuze) return toast('Kies eerst een app uit de Microsoft Store.', 'e');
    const body = { kind: soort, ...(soort === 'store' ? { packageId: keuze.id, name: keuze.name, publisher: keuze.publisher, asUser: alsGebruiker } : {}), ...(soort === 'm365' ? m365 : {}),
      assign: iedereen ? [{ kind: 'all_devices', intent: 'required', name: 'Alle apparaten' }] : null };
    if (await act('in.app.add', body, { msg: 'App toevoegen...' })) close(true);
  };
  return (
    <>
      <h3>App toevoegen aan Intune</h3>
      <Tabs value={soort} onChange={setSoort} tabs={[['store', 'Microsoft Store'], ['m365', 'Microsoft 365 Apps'], ['edge', 'Microsoft Edge']]} />
      {soort === 'store' && (
        <>
          <div className="row" style={{ alignItems: 'center' }}>
            <SearchBox value={q} onChange={setQ} placeholder="Zoek in de Microsoft Store (bijv. Company Portal, 7-Zip, Adobe Reader) en druk op Enter" onKeyDown={(e) => e.key === 'Enter' && zoek()} />
            <div className="n"><Btn onClick={zoek}>Zoeken</Btn></div>
          </div>
          <div className="list" style={{ maxHeight: 260, marginTop: 8 }}>
            {res === null ? (q ? <Loading text="Zoeken..." /> : <div className="li empty">Zoek een app.</div>) : res.length ? res.map((r) => (
              <div key={r.id} className={`li ${keuze?.id === r.id ? 'on' : ''}`} onClick={() => setKeuze(r)}>
                <AppWindow size={15} style={{ flex: 'none' }} /><span className="m"><b>{r.name}</b><small>{r.publisher} · {r.id}</small></span></div>)) : <div className="li empty">Niets gevonden.</div>}
          </div>
          <Check checked={alsGebruiker} onChange={setAlsGebruiker}>Installeren in de context van de gebruiker (anders voor het hele apparaat)</Check>
        </>)}
      {soort === 'm365' && (
        <div style={{ display: 'grid', gap: 6 }}>
          <div className="hint" style={{ marginTop: 0 }}>Word, Excel, PowerPoint, Outlook, OneNote, Teams en OneDrive; 64-bits, kanaal Current, Nederlands.</div>
          <Check checked={m365.english} onChange={(v) => setM365({ ...m365, english: v })}>Ook Engels installeren</Check>
          <Check checked={m365.access} onChange={(v) => setM365({ ...m365, access: v })}>Access meenemen</Check>
          <Check checked={m365.publisherApp} onChange={(v) => setM365({ ...m365, publisherApp: v })}>Publisher meenemen</Check>
          <Check checked={m365.shared} onChange={(v) => setM365({ ...m365, shared: v })}>Gedeelde computeractivering (RDS/AVD)</Check>
        </div>)}
      {soort === 'edge' && <div className="hint">Microsoft Edge, stabiel kanaal, Nederlands.</div>}
      <div style={{ marginTop: 12 }}><Check checked={iedereen} onChange={setIedereen}>Direct verplicht toewijzen aan alle apparaten</Check></div>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button><button className="btn p" onClick={opslaan}>Toevoegen</button></div>
    </>
  );
}

// ---------------------------------------------------------------- Inschrijving
const PLAT = { windows: 'Windows', android: 'Android-apparaatbeheerder', androidForWork: 'Android Enterprise (werkprofiel)', ios: 'iOS/iPadOS', mac: 'macOS', macOS: 'macOS',
  androidAOSP: 'Android (AOSP)' };
const GEBRUIK = [['allowed', 'Toegestaan'], ['required', 'Verplicht'], ['disallowed', 'Niet toegestaan']];

export function Inschrijving() {
  const [d, setD] = useState(null);
  const [tab, setTab] = useState(() => startTab('iinschrijving', 'windows'));
  const laad = async (fresh) => { try { setD(await api('in.enroll', { fresh: !!fresh }, { quiet: true })); } catch (e) { toast(e.message, 'e'); setD({ error: e.message, restrictions: [], limits: [], esp: [], androidProfiles: [], errors: {} }); } };
  useEffect(() => { laad(false); }, []);
  if (!d) return <Loading text="Inschrijvingsinstellingen ophalen..." />;
  const ververs = () => laad(true);
  return (
    <>
      <div className="headrow"><div className="m"><h2 style={{ margin: 0 }}>Inschrijving</h2>
        <p className="sub">Hoe apparaten in Intune komen: automatische inschrijving, beperkingen, Windows Hello for Business, inschrijvingsstatuspagina en Android Enterprise.</p></div>
        <Btn s icon={RefreshCw} onClick={() => { setD(null); ververs(); }}>Vernieuwen</Btn></div>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      <Tabs value={tab} onChange={setTab} tabs={[['windows', 'Windows', Laptop], ['hello', 'Windows Hello', Fingerprint], ['android', 'Android', Smartphone], ['beperking', 'Beperkingen', ShieldCheck]]} />
      {tab === 'windows' && <><Mdm d={d} ververs={ververs} />{d.esp.map((e) => <Esp key={e.id} e={e} ververs={ververs} />)}</>}
      {tab === 'hello' && (d.whfb ? <Hello w={d.whfb} ververs={ververs} /> : <Msg kind="info">Windows Hello for Business-instelling niet gevonden bij deze klant.</Msg>)}
      {tab === 'android' && <Android d={d} ververs={ververs} />}
      {tab === 'beperking' && <Beperkingen d={d} ververs={ververs} />}
    </>
  );
}

function Mdm({ d, ververs }) {
  const m = d.mdm;
  const [scope, setScope] = useState(m?.appliesTo || 'none');
  const [groepen, setGroepen] = useState(m?.groups || []);
  const [alle, setAlle] = useState(null);
  useEffect(() => { if (scope === 'selected' && !alle) api('groups.list', { fresh: false }, { quiet: true }).then((r) => setAlle(r.groups.filter((g) => ['M365', 'Beveiliging', 'Dynamisch'].includes(g.type)))).catch(() => setAlle([])); }, [scope, alle]);
  if (!m) return <Card title="Automatische inschrijving (Windows)" icon={Laptop}><Msg kind="warn">Niet uit te lezen{d.errors?.mdm ? `: ${d.errors.mdm}` : ''}.</Msg></Card>;
  const opslaan = async () => { if (await act('in.mdm.set', { id: m.id, appliesTo: scope, groups: groepen.map((g) => g.id) }, { msg: 'Opslaan...' })) ververs(); };
  return (
    <Card title="Automatische inschrijving (Windows)" icon={Laptop}>
      <div className="hint" style={{ marginTop: 0 }}>Wie zijn Windows-apparaat bij het aanmelden met een werkaccount (of via Autopilot) automatisch in Intune krijgt (MDM-gebruikersbereik).</div>
      <div className="btns">{[['none', 'Niemand'], ['selected', 'Groepen'], ['all', 'Iedereen']].map(([k, l]) => <Btn key={k} v={scope === k ? 'p' : ''} onClick={() => setScope(k)}>{l}</Btn>)}</div>
      {scope === 'selected' && (
        <div className="row" style={{ marginTop: 10 }}>
          <div><label className="f">Gekozen groepen</label>
            <div className="btns">{groepen.map((g) => <Chip key={g.id}>{g.name} <button className="linkknop" onClick={() => setGroepen((l) => l.filter((x) => x.id !== g.id))}>x</button></Chip>)}{!groepen.length && <span className="hint">Nog geen groepen.</span>}</div></div>
          <div>{!alle ? <Loading text="Groepen..." /> : <Picker items={alle.filter((g) => !groepen.some((x) => x.id === g.id)).map((g) => ({ v: g.id, l: g.name }))} placeholder="Groep toevoegen..." height={160}
            onPick={(i) => setGroepen((l) => [...l, { id: i.v, name: i.l }])} />}</div>
        </div>)}
      <div className="btns" style={{ marginTop: 12 }}><Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn></div>
    </Card>
  );
}

function Esp({ e, ververs }) {
  const [v, setV] = useState(e);
  const z = (k, w) => setV((o) => ({ ...o, [k]: w }));
  const opslaan = async () => { if (await act('in.esp.set', { id: e.id, name: e.name, values: v }, { msg: 'Opslaan...' })) ververs(); };
  return (
    <Card title={`Inschrijvingsstatuspagina: ${e.name}${e.default ? ' (standaard)' : ''}`} icon={Laptop} right={e.default ? null : <Doelen lijst={e.assignments} />}>
      <div style={{ display: 'grid', gap: 6 }}>
        <Check checked={!!v.showInstallationProgress} onChange={(w) => z('showInstallationProgress', w)}>Voortgang van apps en profielen tonen tijdens de inschrijving</Check>
        {v.showInstallationProgress && <>
          <div className="row"><div><label className="f">Maximale wachttijd (minuten)</label><input type="number" min={15} max={1440} value={v.installProgressTimeoutInMinutes || 60} onChange={(x) => z('installProgressTimeoutInMinutes', +x.target.value)} /></div>
            <div><label className="f">Foutmelding bij overschrijding</label><input type="text" value={v.customErrorMessage || ''} onChange={(x) => z('customErrorMessage', x.target.value)} /></div></div>
          <Check checked={!v.blockDeviceSetupRetryByUser} onChange={(w) => z('blockDeviceSetupRetryByUser', !w)}>Gebruiker mag het opnieuw proberen bij een fout</Check>
          <Check checked={!!v.allowDeviceResetOnInstallFailure} onChange={(w) => z('allowDeviceResetOnInstallFailure', w)}>Apparaat resetten toestaan bij een fout</Check>
          <Check checked={!!v.allowDeviceUseOnInstallFailure} onChange={(w) => z('allowDeviceUseOnInstallFailure', w)}>Apparaat toch gebruiken bij een fout</Check>
          <Check checked={!!v.allowLogCollectionOnInstallFailure} onChange={(w) => z('allowLogCollectionOnInstallFailure', w)}>Logbestanden verzamelen bij een fout</Check>
          <Check checked={!!v.trackInstallProgressForAutopilotOnly} onChange={(w) => z('trackInstallProgressForAutopilotOnly', w)}>Alleen tonen bij Autopilot-apparaten</Check>
        </>}
      </div>
      <div className="btns" style={{ marginTop: 12 }}><Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn></div>
    </Card>
  );
}

function Hello({ w, ververs }) {
  const [v, setV] = useState(w);
  const z = (k, x) => setV((o) => ({ ...o, [k]: x }));
  const opslaan = async () => { if (await act('in.whfb.set', { id: w.id, values: v }, { msg: 'Windows Hello opslaan...' })) ververs(); };
  const keuze = (k, l) => (
    <div><label className="f">{l}</label><select value={v[k] || 'allowed'} onChange={(e) => z(k, e.target.value)}>{GEBRUIK.map(([a, b]) => <option key={a} value={a}>{b}</option>)}</select></div>);
  return (
    <Card title="Windows Hello for Business (bij inschrijving)" icon={Fingerprint}>
      <div className="hint" style={{ marginTop: 0 }}>Geldt voor alle Windows-apparaten die in Intune worden ingeschreven: aanmelden met pincode, vingerafdruk of gezichtsherkenning in plaats van een wachtwoord.</div>
      <div className="btns">{[['enabled', 'Ingeschakeld'], ['disabled', 'Uitgeschakeld'], ['notConfigured', 'Niet geconfigureerd']].map(([k, l]) => <Btn key={k} v={v.state === k ? 'p' : ''} onClick={() => z('state', k)}>{l}</Btn>)}</div>
      {v.state === 'enabled' && (
        <>
          <div className="row" style={{ marginTop: 10 }}>
            <div><label className="f">Minimale pinlengte</label><input type="number" min={4} max={127} value={v.pinMinimumLength || 6} onChange={(e) => z('pinMinimumLength', +e.target.value)} /></div>
            <div><label className="f">Maximale pinlengte</label><input type="number" min={4} max={127} value={v.pinMaximumLength || 127} onChange={(e) => z('pinMaximumLength', +e.target.value)} /></div>
            <div><label className="f">Pincode verloopt na (dagen, 0 = nooit)</label><input type="number" min={0} max={730} value={v.pinExpirationInDays || 0} onChange={(e) => z('pinExpirationInDays', +e.target.value)} /></div>
            <div><label className="f">Eerdere pincodes onthouden</label><input type="number" min={0} max={50} value={v.pinPreviousBlockCount || 0} onChange={(e) => z('pinPreviousBlockCount', +e.target.value)} /></div>
          </div>
          <div className="row">{keuze('pinUppercaseCharactersUsage', 'Hoofdletters')}{keuze('pinLowercaseCharactersUsage', 'Kleine letters')}{keuze('pinSpecialCharactersUsage', 'Speciale tekens')}</div>
          <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
            <Check checked={!!v.securityDeviceRequired} onChange={(x) => z('securityDeviceRequired', x)}>TPM verplicht (aanbevolen)</Check>
            <Check checked={!!v.unlockWithBiometricsEnabled} onChange={(x) => z('unlockWithBiometricsEnabled', x)}>Vingerafdruk en gezichtsherkenning toestaan</Check>
            <div className="row"><div><label className="f">Verbeterde anti-spoofing gezichtsherkenning</label>
              <select value={v.enhancedBiometricsState || 'notConfigured'} onChange={(e) => z('enhancedBiometricsState', e.target.value)}><option value="notConfigured">Niet geconfigureerd</option><option value="enabled">Aan</option><option value="disabled">Uit</option></select></div>
              <div><label className="f">Aanmelden met beveiligingssleutel (FIDO2)</label>
                <select value={v.securityKeyForSignIn || 'notConfigured'} onChange={(e) => z('securityKeyForSignIn', e.target.value)}><option value="notConfigured">Niet geconfigureerd</option><option value="enabled">Aan</option><option value="disabled">Uit</option></select></div></div>
            <Check checked={!!v.remotePassportEnabled} onChange={(x) => z('remotePassportEnabled', x)}>Telefoon als aanmeldmiddel (Remote Windows Hello)</Check>
          </div>
        </>)}
      <div className="btns" style={{ marginTop: 12 }}><Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn></div>
      <div className="hint">Wijzigingen gelden voor nieuwe inschrijvingen. Voor bestaande apparaten gebruik je een Windows Hello-profiel (Configuratieprofielen).</div>
    </Card>
  );
}

const MODUS = { corporateOwnedFullyManaged: 'Volledig beheerd (zakelijk)', corporateOwnedDedicatedDevice: 'Toegewezen apparaat (kiosk)', corporateOwnedWorkProfile: 'Zakelijk met werkprofiel' };

function Android({ d, ververs }) {
  const g = d.gplay;
  const nieuw = async () => {
    const r = await openModal((close) => <AndroidNieuw close={close} />);
    if (r && await act('in.android.create', r, { msg: 'Profiel aanmaken...' })) ververs();
  };
  const qr = async (p) => {
    const r = await api('in.android.qr', { id: p.id }, { quiet: true }).catch((e) => { toast(e.message, 'e'); return null; });
    if (r) openModal((close) => (<><h3>{r.name}</h3>{r.qr ? <img src={r.qr} alt="QR-code" style={{ width: 280, display: 'block', margin: '8px auto' }} /> : <Msg kind="warn">Geen QR-code (token verlopen of ingetrokken).</Msg>}
      {r.token && <div className="hint">Token: <b>{r.token}</b> · geldig tot {dt(r.expires)}</div>}<div className="hint">Scan de QR-code op het welkomstscherm van een nieuw (of teruggezet) Android-apparaat: tik 6 keer op het scherm.</div>
      <div className="foot"><button className="btn" onClick={() => close()}>Sluiten</button></div></>));
  };
  return (
    <>
      <Card title="Managed Google Play" icon={Smartphone}>
        {g ? (g.bound ? <Msg kind="ok">Gekoppeld met {g.owner || 'een Google-account'}{g.sync ? ` · laatste app-synchronisatie ${dt(g.sync)}` : ''}.</Msg>
          : <Msg kind="warn">Niet gekoppeld ({g.status || 'onbekend'}). Koppel Managed Google Play eenmalig in het Intune-beheercentrum (Apparaten &gt; Android &gt; Android-inschrijving); dat vraagt een Google-account en kan niet via de API.</Msg>)
          : <Msg kind="warn">Niet uit te lezen{d.errors?.gplay ? `: ${d.errors.gplay}` : ''}.</Msg>}
      </Card>
      <Card title="Inschrijvingsprofielen (zakelijke apparaten)" icon={QrCode} right={<Btn s v="p" icon={Plus} onClick={nieuw}>Nieuw profiel</Btn>}>
        <table>
          <thead><tr><th>Naam</th><th>Soort</th><th className="r">Apparaten</th><th>Token geldig tot</th><th /></tr></thead>
          <tbody>{d.androidProfiles.map((p) => (
            <tr key={p.id}><td><b>{p.name}</b></td><td>{MODUS[p.mode] || p.mode}</td><td className="r">{p.devices}</td>
              <td>{p.token ? dt(p.expires) : <Chip k="mu">geen token</Chip>}</td>
              <td className="r"><span className="btns" style={{ justifyContent: 'flex-end' }}>
                <Btn s icon={QrCode} onClick={() => qr(p)}>QR-code</Btn>
                <Btn s icon={KeyRound} onClick={async () => { if (await act('in.android.token', { id: p.id, name: p.name, days: 90 }, { msg: 'Token vernieuwen...' })) ververs(); }}>Nieuw token</Btn>
                {p.token && <Btn s v="dl" onClick={async () => { if (await ask(`Token van "${p.name}" intrekken? Nieuwe apparaten kunnen zich dan niet meer met deze QR-code inschrijven.`, 'Intrekken', true) && await act('in.android.token', { id: p.id, name: p.name, revoke: true }, { msg: 'Intrekken...' })) ververs(); }}>Intrekken</Btn>}
                <Btn s v="dl" icon={Trash2} onClick={async () => { if (await ask(`Profiel "${p.name}" verwijderen?`, 'Verwijderen', true) && await act('in.android.delete', { id: p.id, name: p.name }, { msg: 'Verwijderen...' })) ververs(); }} />
              </span></td></tr>))}
            {!d.androidProfiles.length && <tr><td colSpan={5} className="hint">Nog geen profielen{d.errors?.android ? ` (${d.errors.android})` : ''}.</td></tr>}
          </tbody>
        </table>
        <div className="hint">Persoonlijke Android-apparaten met werkprofiel schrijven zich in via de Bedrijfsportal-app; dat staat aan of uit bij Beperkingen.</div>
      </Card>
    </>
  );
}

function AndroidNieuw({ close }) {
  const [mode, setMode] = useState('corporateOwnedFullyManaged');
  const [name, setName] = useState('');
  const [days, setDays] = useState(90);
  return (
    <>
      <h3>Nieuw Android-inschrijvingsprofiel</h3>
      <label className="f">Soort</label>
      <div className="btns">{Object.entries(MODUS).map(([k, l]) => <Btn key={k} v={mode === k ? 'p' : ''} onClick={() => setMode(k)}>{l}</Btn>)}</div>
      <label className="f">Naam</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder={MODUS[mode]} />
      <label className="f">Token geldig (dagen, max. 90)</label><input type="number" min={1} max={90} value={days} onChange={(e) => setDays(Math.min(90, Math.max(1, +e.target.value)))} />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button><button className="btn p" onClick={() => close({ mode, name: name || MODUS[mode], days })}>Aanmaken</button></div>
    </>
  );
}

function Beperkingen({ d, ververs }) {
  const standaard = d.restrictions.filter((r) => r.default);
  const ander = d.restrictions.filter((r) => !r.default);
  const limiet = d.limits.find((l) => l.default) || d.limits[0];
  const [n, setN] = useState(limiet?.limit || 5);
  const zet = async (r, w) => { if (await act('in.restrict.set', { id: r.id, odata: r.odata, field: r.field, platform: r.platform, blocked: r.blocked, personalBlocked: r.personalBlocked, min: r.min, max: r.max, ...w }, { msg: 'Opslaan...' })) ververs(); };
  return (
    <>
      <Card title="Platformbeperkingen (standaard, voor iedereen)" icon={ShieldCheck}>
        <table>
          <thead><tr><th>Platform</th><th>Inschrijven</th><th>Persoonlijke apparaten</th><th>Versie</th></tr></thead>
          <tbody>{standaard.map((r) => (
            <tr key={r.id + r.field}><td><b>{PLAT[r.platform] || r.platform}</b></td>
              <td><Btn s v={r.blocked ? 'dl' : ''} onClick={() => zet(r, { blocked: !r.blocked })}>{r.blocked ? 'Geblokkeerd' : 'Toegestaan'}</Btn></td>
              <td>{r.blocked ? <span className="hint">-</span> : <Btn s v={r.personalBlocked ? 'dl' : ''} onClick={() => zet(r, { personalBlocked: !r.personalBlocked })}>{r.personalBlocked ? 'Geblokkeerd' : 'Toegestaan'}</Btn>}</td>
              <td><small className="hint">{r.min || r.max ? `${r.min || '...'} t/m ${r.max || '...'}` : 'alle'}</small></td></tr>))}
          </tbody>
        </table>
        {ander.length > 0 && <div className="hint">Daarnaast {ander.length} aanvullende beperking(en) voor specifieke groepen: {[...new Set(ander.map((r) => r.name))].join(', ')}.</div>}
      </Card>
      {limiet && (
        <Card title="Apparaatlimiet per gebruiker" icon={Users}>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <div><label className="f">Maximaal aantal apparaten per gebruiker (1-15)</label><input type="number" min={1} max={15} value={n} onChange={(e) => setN(+e.target.value)} /></div>
            <div className="n"><Btn v="p" icon={Save} onClick={async () => { if (await act('in.limit.set', { id: limiet.id, limit: n }, { msg: 'Opslaan...' })) ververs(); }}>Opslaan</Btn></div>
          </div>
        </Card>)}
    </>
  );
}
