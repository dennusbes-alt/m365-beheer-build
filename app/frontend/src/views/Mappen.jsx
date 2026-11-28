// SharePoint-mapmachtigingen in gewone taal: site -> bibliotheek -> map, wie heeft toegang, toegang geven of weghalen,
// en een nieuwe medewerker dezelfde maptoegang geven als een collega. Voor servicedeskmedewerkers zonder SharePoint-kennis.
import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, Copy, Folder, FolderLock, Globe, Library, LogIn, LogOut, RotateCcw, Trash2, UserPlus, Users } from 'lucide-react';
import { act, api, getTenant } from '../api.js';
import { Msg, ask, openModal, toast } from '../overlays.jsx';
import { doorgeven, getUsers } from '../store.jsx';
import { Btn, Card, Chip, Loading, Picker, SearchBox, useFilter } from '../ui.jsx';
import MappenOnboarding from './MappenOnboarding.jsx';

const KLEUR = { 'Volledig beheer': 'r', 'Full Control': 'r', Bewerken: 'o', Edit: 'o', Bijdragen: 'o', Contribute: 'o', Lezen: 'g', Read: 'g' };

export default function Mappen() {
  const [sites, setSites] = useState(null);
  const [site, setSite] = useState(null);
  const [libs, setLibs] = useState(null);
  const [lib, setLib] = useState(null);
  const [pad, setPad] = useState([]);          // gekozen mappen (kruimelpad)
  const [mappen, setMappen] = useState(null);
  const [rechten, setRechten] = useState(null);
  const [fout, setFoutTekst] = useState('');
  const [klantNodig, setKlantNodig] = useState(false);   // SharePoint weigert GDAP: inloggen met klantaccount aanbieden
  const [klantAcc, setKlantAcc] = useState('');
  const [onboard, setOnboard] = useState(false);
  const setFout = (e) => { setFoutTekst(typeof e === 'string' ? e : e.message); setKlantNodig(!!(e && e.klantLogin)); };
  const [q, setQ] = useState('');
  const [nieuweMedewerker, setNieuw] = useState(doorgeven.mappenGebruiker || '');

  // Per klant onthouden welke site je voor mappen gebruikt (bijv. 'Data'): bij een nieuwe medewerker opent die direct
  const siteSleutel = `spm.site.${getTenant()}`;
  useEffect(() => {
    api('spm.sites', {}, { quiet: true }).then((r) => {
      setSites(r.sites);
      let vorige = null;
      try { vorige = r.sites.find((s) => s.url === localStorage.getItem(siteSleutel)); } catch { /* geen opslag */ }
      if (vorige && doorgeven.mappenGebruiker) kiesSite(vorige, true);
    }).catch((e) => { setFout(e); setSites([]); });
    api('spm.klantstatus', {}, { quiet: true }).then((r) => setKlantAcc(r.account || '')).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const kiesSite = async (s, metOnboarding) => {
    setSite(s); setLib(null); setPad([]); setMappen(null); setRechten(null); setLibs(null); setFout('');
    try { localStorage.setItem(siteSleutel, s.url); } catch { /* geen opslag */ }
    try {
      const l = (await api('spm.libs', { site: s.url }, { quiet: true })).libs;
      setLibs(l);
      if ((metOnboarding === true || doorgeven.mappenGebruiker) && l.length) setOnboard(true);   // nieuwe medewerker: direct de mappenlijst
    } catch (e) { setFout(e); setLibs([]); }
  };
  const map = pad.length ? pad[pad.length - 1] : null;
  const doel = lib && { site: site.url, listId: lib.id, itemId: map ? map.itemId : null, label: map ? map.name : lib.title };
  const laadMappen = async (p) => { setMappen(null); try { setMappen((await api('spm.folders', { site: site.url, path: p }, { quiet: true })).folders); } catch (e) { setFout(e); setMappen([]); } };
  const laadRechten = async () => { setRechten(null); try { setRechten(await api('spm.perms', doel, { quiet: true })); } catch (e) { setFout(e); setRechten({ perms: [], levels: [] }); } };
  useEffect(() => { if (lib) { laadMappen(map ? map.path : lib.path); laadRechten(); } }, [lib, pad]); // eslint-disable-line react-hooks/exhaustive-deps

  const klantLogin = async () => {
    const r = await act('spm.klantlogin', { site: site.url }, { msg: 'Inloggen met het beheeraccount van de klant (browser)...' });
    if (r) { setKlantAcc(r.account); kiesSite(site); }
  };
  const klantLogout = async () => { if (await act('spm.klantlogout', {}, { quiet: true }) !== null) { setKlantAcc(''); if (site) kiesSite(site); } };
  const Fout = () => (fout ? (
    <Msg kind="warn">{fout}
      {klantNodig && site && <div style={{ marginTop: 8 }}><Btn v="p" icon={LogIn} onClick={klantLogin}>Inloggen met beheeraccount van de klant</Btn></div>}
    </Msg>) : null);
  const KlantChip = () => (klantAcc ? (
    <div className="hint" style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: -4, marginBottom: 8 }}>
      SharePoint via klantaccount <b>{klantAcc}</b> (alleen deze sessie)
      <button className="linkknop" onClick={klantLogout}><LogOut size={12} /> afmelden</button></div>) : null);
  const shownSites = useFilter(sites || [], q, (s) => [s.title, s.url]);
  if (!sites) return <Loading text="Sites ophalen..." />;

  // Stap 1: site kiezen
  if (!site) {
    return (
      <>
        <h2>Mapmachtigingen (SharePoint)</h2>
        <p className="sub">Bepaal wie bij welke map mag. Kies eerst de site, dan de bibliotheek en de map.</p>
        {nieuweMedewerker && <Msg kind="info">Nieuwe medewerker: <b>{nieuweMedewerker}</b>. Kies de site en bibliotheek; daarna kun je deze persoon toegang geven of dezelfde toegang als een collega.</Msg>}
        <KlantChip /><Fout />
        <Card title="Kies een site" icon={Globe} right={<SearchBox value={q} onChange={setQ} placeholder="Zoek site..." />}>
          <div className="list" style={{ maxHeight: 'calc(100vh - 330px)' }}>
            {shownSites.map((s) => <div key={s.url} className="li" onClick={() => kiesSite(s)}><Globe size={15} style={{ flex: 'none' }} /><span className="m"><b>{s.title}</b><small>{s.url}</small></span></div>)}
            {!shownSites.length && <div className="li empty">Geen sites gevonden.</div>}
          </div>
        </Card>
      </>
    );
  }

  const kruimel = (
    <div className="btns" style={{ alignItems: 'center', gap: 4, marginBottom: 10 }}>
      <button className="linkknop" onClick={() => { setSite(null); setFout(''); }}>Sites</button><ChevronRight size={14} />
      <button className="linkknop" onClick={() => { setLib(null); setPad([]); }}>{site.title}</button>
      {lib && <><ChevronRight size={14} /><button className="linkknop" onClick={() => setPad([])}>{lib.title}</button></>}
      {pad.map((m, i) => <span key={m.path} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><ChevronRight size={14} /><button className="linkknop" onClick={() => setPad(pad.slice(0, i + 1))}>{m.name}</button></span>)}
    </div>);

  if (onboard) return <MappenOnboarding site={site} vooraf={nieuweMedewerker} onTerug={() => setOnboard(false)} />;

  // Stap 2: bibliotheek kiezen
  if (!lib) {
    return (
      <>
        <h2>Mapmachtigingen (SharePoint)</h2>
        {kruimel}
        <KlantChip /><Fout />
        {libs && libs.length > 0 && (
          <div className="card" style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', borderLeft: '4px solid var(--cy)' }}>
            <UserPlus size={22} style={{ color: 'var(--hd)' }} />
            <div style={{ flex: 1, minWidth: 240 }}><b>Nieuwe medewerker toegang geven</b>
              <div className="hint" style={{ margin: 0 }}>Alle mappen met eigen machtigingen in deze site in één lijst: vink aan wat de medewerker nodig heeft, de app zet hem in de juiste groepen.{nieuweMedewerker ? ` (${nieuweMedewerker})` : ''}</div></div>
            <Btn v="p" icon={UserPlus} onClick={() => setOnboard(true)}>Toegang per map</Btn>
          </div>)}
        <Card title="Kies een bibliotheek" icon={Library}>
          {!libs ? <Loading text="Bibliotheken ophalen..." /> : (
            <div className="list">{libs.map((l) => <div key={l.id} className="li" onClick={() => setLib(l)}><Library size={15} style={{ flex: 'none' }} />
              <span className="m"><b>{l.title}</b><small>{l.count} items{l.unique ? ' · eigen machtigingen' : ''}</small></span></div>)}
              {!libs.length && <div className="li empty">Geen bibliotheken (of geen toegang).</div>}</div>)}
        </Card>
      </>
    );
  }

  // Stap 3: mappen en machtigingen
  const geven = async (vooraf) => {
    const r = await openModal((close) => <ToegangGeven doel={doel} levels={rechten?.levels || []} vooraf={vooraf} close={close} />, { wide: true });
    if (r && await act('spm.grant', { ...doel, ...r }, { msg: 'Toegang geven...' })) laadRechten();
  };
  const weg = async (p) => {
    if (!(await ask(`Toegang van ${p.name} tot "${doel.label}" weghalen?${rechten && !rechten.unique ? ' Deze map krijgt daarvoor eigen machtigingen (de rest blijft zoals het is).' : ''}`, 'Weghalen', true))) return;
    if (await act('spm.revoke', { ...doel, principalId: p.id, name: p.name }, { msg: 'Weghalen...' })) laadRechten();
  };
  const herstel = async () => {
    if (!(await ask(`"${doel.label}" weer dezelfde machtigingen geven als de bovenliggende map? Alle aparte toegang op deze map vervalt.`, 'Herstellen', true))) return;
    if (await act('spm.inherit', doel, { msg: 'Herstellen...' })) { laadRechten(); if (map) map.unique = false; }
  };
  const zoals = async () => {
    const r = await openModal((close) => <ZoalsCollega vooraf={nieuweMedewerker} lib={lib} close={close} />);
    if (!r) return;
    const x = await act('spm.zoals', { site: site.url, listId: lib.id, fromUpn: r.from, toUpn: r.to }, { msg: `Mappen van ${r.from} nalopen en dezelfde toegang geven...` });
    if (x) { toast(`${r.to} heeft toegang gekregen tot ${x.folders.length} map(pen).`, 'g'); laadRechten(); }
  };
  return (
    <>
      <div className="headrow"><div className="m"><h2 style={{ margin: 0 }}>Mapmachtigingen (SharePoint)</h2></div>
        <Btn icon={Copy} onClick={zoals}>Zelfde toegang als collega...</Btn></div>
      {kruimel}
      <KlantChip /><Fout />
      {nieuweMedewerker && <Msg kind="info">Nieuwe medewerker: <b>{nieuweMedewerker}</b> <button className="linkknop" onClick={() => geven(nieuweMedewerker)}>toegang geven tot "{doel.label}"</button> {' · '}
        <button className="linkknop" onClick={() => { doorgeven.mappenGebruiker = ''; setNieuw(''); }}>klaar</button></Msg>}
      <div className="cols">
        <div className="sticky">
          <Card title={map ? map.name : lib.title} icon={Folder}>
            {pad.length > 0 && <div className="li" onClick={() => setPad(pad.slice(0, -1))} style={{ cursor: 'pointer' }}><Folder size={15} /><span className="m"><b>..</b><small>terug</small></span></div>}
            <div className="list" style={{ maxHeight: 'calc(100vh - 380px)' }}>
              {!mappen ? <Loading text="Mappen ophalen..." /> : mappen.map((m) => (
                <div key={m.path} className="li" onClick={() => setPad([...pad, m])}>
                  {m.unique ? <FolderLock size={15} style={{ flex: 'none', color: 'var(--or)' }} /> : <Folder size={15} style={{ flex: 'none' }} />}
                  <span className="m"><b>{m.name}</b><small>{m.count} items{m.unique ? ' · eigen machtigingen' : ''}</small></span><ChevronRight size={14} />
                </div>))}
              {mappen && !mappen.length && <div className="li empty">Geen submappen.</div>}
            </div>
          </Card>
        </div>
        <div>
          <Card title={`Wie heeft toegang tot "${doel.label}"`} icon={Users} right={<Btn v="p" icon={UserPlus} onClick={() => geven()}>Toegang geven</Btn>}>
            {!rechten ? <Loading text="Machtigingen ophalen..." /> : (
              <>
                {rechten.unique ? <Msg kind="info">Deze {map ? 'map' : 'bibliotheek'} heeft <b>eigen machtigingen</b> (afwijkend van de bovenliggende). {map && <button className="linkknop" onClick={herstel}><RotateCcw size={12} /> Weer gelijk maken aan bovenliggende map</button>}</Msg>
                  : <div className="hint" style={{ marginTop: 0 }}>Deze {map ? 'map' : 'bibliotheek'} neemt de machtigingen over van {map ? 'de bovenliggende map' : 'de site'}. Geef je hier toegang, dan krijgt alleen deze {map ? 'map' : 'bibliotheek'} (met alles erin) eigen machtigingen; bestaande toegang blijft behouden.</div>}
                <table>
                  <thead><tr><th>Naam</th><th>Soort</th><th>Niveau</th><th /></tr></thead>
                  <tbody>{rechten.perms.map((p) => <Rij key={p.id} p={p} site={site.url} weg={() => weg(p)} />)}
                    {!rechten.perms.length && <tr><td colSpan={4} className="hint">Niemand heeft (zichtbare) toegang.</td></tr>}</tbody>
                </table>
              </>)}
          </Card>
        </div>
      </div>
    </>
  );
}

function Rij({ p, site, weg }) {
  const [leden, setLeden] = useState(null);
  const toon = async () => { if (leden) return setLeden(null); try { setLeden((await api('spm.groupusers', { site, groupId: p.id }, { quiet: true })).users); } catch (e) { toast(e.message, 'e'); } };
  return (
    <>
      <tr>
        <td><b>{p.name}</b>{p.email && <><br /><small className="hint">{p.email}</small></>}{p.spGroup && <><br /><button className="linkknop" onClick={toon}>{leden ? 'leden verbergen' : 'leden tonen'}</button></>}</td>
        <td><small>{p.kind}</small></td>
        <td>{p.roles.map((r) => <Chip key={r} k={KLEUR[r] || ''}>{r}</Chip>)}</td>
        <td className="r"><Btn s v="dl" icon={Trash2} onClick={weg}>Weghalen</Btn></td>
      </tr>
      {leden && <tr><td colSpan={4} style={{ background: 'var(--bg)' }}><small>{leden.length ? leden.map((u) => u.name).join(', ') : 'Geen leden.'}</small></td></tr>}
    </>
  );
}

function ToegangGeven({ doel, levels, vooraf, close }) {
  const [users, setUsers] = useState(null);
  const [groepen, setGroepen] = useState(null);
  const [gekozen, setGekozen] = useState([]);
  const [niveau, setNiveau] = useState('edit');
  useEffect(() => {
    getUsers().then((u) => {
      setUsers(u);
      if (vooraf) { const x = u.find((y) => (y.upn || '').toLowerCase() === vooraf.toLowerCase()); setGekozen([x ? { upn: x.upn, name: x.name } : { upn: vooraf, name: vooraf }]); }
    }).catch(() => setUsers([]));
    api('groups.list', { fresh: false }, { quiet: true }).then((r) => setGroepen(r.groups.filter((g) => ['M365', 'Beveiliging'].includes(g.type)))).catch(() => setGroepen([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const items = useMemo(() => [...(users || []).map((u) => ({ v: 'u:' + u.upn, l: u.name, s: u.upn, p: { upn: u.upn, name: u.name } })),
    ...(groepen || []).map((g) => ({ v: 'g:' + g.id, l: g.name, s: `Groep (${g.type})`, p: { groupId: g.id, m365: g.type === 'M365', name: g.name } }))], [users, groepen]);
  return (
    <>
      <h3>Toegang geven tot "{doel.label}"</h3>
      <label className="f">Wie</label>
      <div className="btns" style={{ minHeight: 30 }}>{gekozen.map((g) => <Chip key={g.upn || g.groupId}>{g.name} <button className="linkknop" onClick={() => setGekozen((l) => l.filter((x) => x !== g))}>x</button></Chip>)}
        {!gekozen.length && <span className="hint">Kies hieronder één of meer personen of groepen.</span>}</div>
      {!users || !groepen ? <Loading text="Personen en groepen ophalen..." /> : <Picker items={items} placeholder="Zoek persoon of groep..." height={200} onPick={(i) => setGekozen((l) => (l.some((x) => (x.upn || x.groupId) === (i.p.upn || i.p.groupId)) ? l : [...l, i.p]))} />}
      <label className="f">Wat mag diegene</label>
      <div style={{ display: 'grid', gap: 6 }}>
        {levels.filter((l) => l.key !== 'contribute').map((l) => (
          <button key={l.key} className={`keuze ${niveau === l.key ? 'on' : ''}`} style={{ textAlign: 'left', borderColor: niveau === l.key ? 'var(--cy)' : undefined }} onClick={() => setNiveau(l.key)}>
            <b>{l.name}</b><small>{l.help}</small></button>))}
      </div>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!gekozen.length} onClick={() => close({ principals: gekozen, level: niveau })}>Toegang geven</button></div>
    </>
  );
}

function ZoalsCollega({ vooraf, lib, close }) {
  const [users, setUsers] = useState(null);
  const [van, setVan] = useState(null);
  const [naar, setNaar] = useState(vooraf || '');
  useEffect(() => { getUsers().then(setUsers).catch(() => setUsers([])); }, []);
  const items = (users || []).map((u) => ({ v: u.upn, l: u.name, s: u.upn }));
  return (
    <>
      <h3>Zelfde maptoegang als een collega</h3>
      <div className="hint" style={{ marginTop: 0 }}>Alle mappen in "{lib.title}" waar de collega direct toegang heeft, krijgt de nieuwe medewerker met hetzelfde niveau.</div>
      <label className="f">Nieuwe medewerker</label>
      {naar ? <Chip>{naar} <button className="linkknop" onClick={() => setNaar('')}>x</button></Chip>
        : !users ? <Loading /> : <Picker items={items} placeholder="Zoek de nieuwe medewerker..." height={150} onPick={(i) => setNaar(i.v)} />}
      <label className="f">Collega (voorbeeld)</label>
      {van ? <Chip>{van} <button className="linkknop" onClick={() => setVan(null)}>x</button></Chip>
        : !users ? <Loading /> : <Picker items={items.filter((i) => i.v !== naar)} placeholder="Zoek de collega..." height={150} onPick={(i) => setVan(i.v)} />}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!van || !naar} onClick={() => close({ from: van, to: naar })}>Toegang kopiëren</button></div>
    </>
  );
}
