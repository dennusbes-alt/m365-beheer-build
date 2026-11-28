import { useEffect, useMemo, useState } from 'react';
import { startTab } from '../store.jsx';
import { Copy, HardDrive, Info, KeyRound, Laptop, Power, RefreshCw, RotateCcw, Search, Rocket, Save, Trash2, UsersRound } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, askType, openModal, toast } from '../overlays.jsx';
import { AllesVink, Btn, Card, Check, Chip, Loading, Picker, SearchBox, Tabs, dt, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';
import { doorgeven } from '../store.jsx';

const COMP = { compliant: ['Conform', 'g'], noncompliant: ['Niet conform', 'r'], ingraceperiod: ['Respijttermijn', 'o'], unknown: ['Onbekend', 'mu'], error: ['Fout', 'r'], configmanager: ['ConfigMgr', 'mu'] };
const compChip = (c) => { const x = COMP[String(c || '').toLowerCase()] || [c || 'Onbekend', 'mu']; return <Chip k={x[1]}>{x[0]}</Chip>; };
const eigenaar = (o) => ({ company: 'Zakelijk', personal: 'Persoonlijk' }[String(o).toLowerCase()] || o || '-');
const gb = (n) => (n > 0 ? (n / 1073741824).toFixed(1) + ' GB' : '-');
const apProf = (p) => ({ assignedinsync: 'Profiel toegewezen', assignedoutofsync: 'Profiel toegewezen (niet gesynchroniseerd)', assignedunkownsyncstate: 'Profiel toegewezen', notassigned: 'Geen profiel', pending: 'In behandeling', failed: 'Mislukt' }[String(p).toLowerCase()] || p || '-');
const schijf = (v) => ({ operatingsystemvolume: 'Besturingssysteemschijf (C:)', fixeddatadrive: 'Vaste gegevensschijf', removabledatadrive: 'Verwisselbare schijf (USB)' }[String(v).toLowerCase()] || v || 'Onbekend');

export default function Apparaten() {
  const [devs, setDevs] = useState(null);
  const [start] = useState(() => { const z = doorgeven.zoek; if (z && z.soort === 'device') { delete doorgeven.zoek; return z; } return null; });
  const [q, setQ] = useState(start ? start.q : '');
  const [os, setOs] = useState('');
  const [comp, setComp] = useState('');
  const [vink, setVink] = useState([]);
  const [sel, setSel] = useState(start ? start.id : null);
  const laad = async (fresh) => { const d = await act('dev.list', { fresh: !!fresh }, { msg: 'Apparaten ophalen...' }); setDevs(d ? d.devices : []); setVink([]); };
  useEffect(() => { laad(false); }, []);
  const oss = useMemo(() => [...new Set((devs || []).map((x) => x.os).filter(Boolean))].sort(), [devs]);
  const shown = useFilter(devs || [], q, (x) => [x.name, x.upn, x.user, x.serial, x.model]).filter((x) => (!os || x.os === os)
    && (!comp || (comp === 'other' ? !['compliant', 'noncompliant'].includes(x.comp.toLowerCase()) : x.comp.toLowerCase() === comp)));
  if (!devs) return <Loading text="Apparaten ophalen..." />;
  return (
    <>
      <h2>Apparaten</h2>
      <p className="sub">Intune-apparaten beheren: gegevens, groepen, BitLocker-sleutel, synchroniseren, verwijderen en Autopilot.</p>
      <BitlockerZoeken onOpen={(id) => setSel(id)} />
      <div className="cols">
        <div className="sticky">
          <SearchBox value={q} onChange={setQ} placeholder="Zoek op naam, gebruiker of serienummer..." />
          <div className="row" style={{ marginTop: 8 }}>
            <select value={os} onChange={(e) => setOs(e.target.value)}><option value="">Alle besturingssystemen</option>{oss.map((o) => <option key={o}>{o}</option>)}</select>
            <select value={comp} onChange={(e) => setComp(e.target.value)}><option value="">Alle statussen</option><option value="compliant">Conform</option><option value="noncompliant">Niet conform</option><option value="other">Overig</option></select>
          </div>
          <AllesVink ids={shown.slice(0, MAX_RIJEN).map((x) => x.id)} value={vink} onChange={setVink} label={q || os || comp ? 'Alle gevonden apparaten selecteren' : 'Alle apparaten selecteren'} />
          <div className="list" style={{ maxHeight: 'calc(100vh - 400px)' }}>
            {shown.slice(0, MAX_RIJEN).map((x) => (
              <div key={x.id} className={'li' + (x.id === sel ? ' on' : '')} onClick={() => setSel(x.id)}>
                <input type="checkbox" checked={vink.includes(x.id)} onClick={(e) => e.stopPropagation()} onChange={(e) => setVink((v) => (e.target.checked ? [...v, x.id] : v.filter((y) => y !== x.id)))} />
                <span className="m"><b>{x.name}</b><small>{x.user || x.upn || 'Geen gebruiker'} · {x.os} {x.osv}</small></span>{compChip(x.comp)}
              </div>
            ))}
            {!shown.length && <div className="li empty">Geen apparaten gevonden</div>}
            <Meer totaal={shown.length} />
          </div>
          <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
            <div className="count" style={{ flex: 1, margin: 0 }}>{shown.length} apparaten</div>
            <div className="n btns">
              <Btn s v="p" icon={RefreshCw} disabled={!vink.length} onClick={async () => { if (await ask(`${vink.length} apparaten laten synchroniseren met Intune?`, 'Synchroniseren')) act('dev.sync', { ids: vink }, { msg: 'Synchronisatie starten...' }); }}>
                Synchroniseer{vink.length ? ` (${vink.length})` : ''}</Btn>
              {vink.length > 0 && <Btn s icon={Power} onClick={async () => { if (await ask(`${vink.length} apparaten nu laten herstarten? Gebruikers krijgen een melding en het apparaat start binnen enkele minuten opnieuw op.`, 'Herstarten')) act('dev.restartmany', { ids: vink }, { msg: 'Herstart sturen...' }); }}>Herstart ({vink.length})</Btn>}
              {vink.length > 0 && <Btn s v="d" icon={Trash2} onClick={async () => {
                const k = await openModal((close) => <WisMeer n={vink.length} namen={(devs || []).filter((x) => vink.includes(x.id)).map((x) => x.name)} close={close} />);
                if (k && await act('dev.deletemany', { ids: vink, ...k }, { msg: `${vink.length} apparaten verwijderen...` })) { setVink([]); setSel(null); laad(true); }
              }}>Verwijderen ({vink.length})</Btn>}
              <Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn>
            </div>
          </div>
        </div>
        <div>{sel ? <Detail key={sel} id={sel} item={devs.find((x) => x.id === sel)} onDeleted={() => { setSel(null); laad(true); }} /> : <div className="card muted"><Laptop size={18} />Kies links een apparaat.</div>}</div>
      </div>
    </>
  );
}

function Detail({ id, item, onDeleted }) {
  const [d, setD] = useState(null);
  const [tab, setTab] = useState(() => startTab('dev-detail', 'info'));
  const open = async () => { const x = await act('dev.get', { id, serial: item ? item.serial : null, aad: item ? item.aad : null }); if (x) setD(x); };
  useEffect(() => { open(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <Loading />;
  const T = { info: DInfo, groepen: DGroepen, bit: DBit, ap: DAp }[tab];
  return (
    <>
      <div className="card">
        <div className="headrow">
          <div className="m">
            <h3>{d.name}</h3>
            <div className="hint" style={{ margin: '2px 0 6px' }}>{d.man} {d.model}</div>
            {compChip(d.comp)} <Chip>{eigenaar(d.owner)}</Chip> <Chip k="mu">{d.mgmt || 'Intune'}</Chip>
          </div>
          <div className="btns">
            <Btn v="p" icon={RefreshCw} onClick={() => act('dev.sync', { ids: [d.id] }, { msg: 'Synchronisatie starten...' })}>Synchroniseren</Btn>
            {/windows/i.test(d.os) && <Btn v="dl" icon={RotateCcw} onClick={() => apReset(d)}>Autopilot Reset</Btn>}
            <Btn v="dl" icon={Trash2} onClick={() => wis(d, onDeleted)}>Verwijderen</Btn>
          </div>
        </div>
        <div className="hint">Laatste check-in: {dt(d.last)}</div>
      </div>
      <div className="card">
        <Tabs value={tab} onChange={setTab} tabs={[['info', 'Basisinformatie', Info], ['groepen', 'Groepen', UsersRound], ['bit', 'BitLocker', KeyRound], ['ap', 'Autopilot', Rocket]]} />
        <T d={d} herlaad={open} />
      </div>
    </>
  );
}

const KV = ({ l, v }) => <div><label>{l}</label><div>{v === '' || v == null ? '-' : v}</div></div>;

function DInfo({ d }) {
  return (
    <>
      <div className="kv">
        <KV l="Apparaatnaam" v={d.name} /><KV l="Serienummer" v={d.serial} />
        <KV l="Model" v={`${d.man} ${d.model}`} /><KV l="Eigendom" v={eigenaar(d.owner)} />
        <KV l="Besturingssysteem" v={`${d.os} ${d.osv}`} /><KV l="Compliance" v={compChip(d.comp)} />
        <KV l="Primaire gebruiker" v={d.user} /><KV l="E-mailadres gebruiker" v={d.upn} />
        <KV l="Ingeschreven op" v={dt(d.enrolled)} /><KV l="Laatste check-in" v={dt(d.last)} />
        <KV l="Versleuteld" v={d.enc === true ? 'Ja' : d.enc === false ? 'Nee' : '-'} /><KV l="Opslag (vrij / totaal)" v={d.total ? `${gb(d.free)} / ${gb(d.total)}` : '-'} />
        <KV l="Wifi MAC-adres" v={d.mac} /><KV l="IMEI" v={d.imei} />
        <KV l="Telefoonnummer" v={d.phone} /><KV l="Categorie" v={d.category} />
        <KV l="Soort inschrijving" v={d.enrollType} /><KV l="Entra-apparaat" v={d.entra ? d.entra.name + (d.entra.enabled ? '' : ' (uitgeschakeld)') : 'Niet gevonden'} />
        {d.patch && <><KV l="Android-beveiligingsupdate" v={d.patch} /><KV l="Jailbreak/root" v={d.jail} /></>}
      </div>
      <div className="hint" style={{ marginTop: 16 }}>Intune-ID: {d.id}<br />Entra-apparaat-ID: {d.aad}</div>
    </>
  );
}

function DGroepen({ d }) {
  const [r, setR] = useState(null);
  const [vink, setVink] = useState([]);
  const laad = async () => { const x = await act('dev.groups', { entraId: d.entra.id }, { msg: 'Groepen ophalen...' }); setR(x || { groups: [], all: [] }); };
  useEffect(() => { if (d.entra) laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d.entra) return <Msg kind="warn">Voor dit apparaat is geen Entra-object gevonden, dus groepen zijn niet beschikbaar.</Msg>;
  if (!r) return <Loading />;
  const mijn = new Set(r.groups.map((g) => g.id));
  const run = async (action, groupIds) => { await act('dev.group', { entraId: d.entra.id, groupIds, action }, { msg: 'Bezig...' }); setVink([]); laad(); };
  const wijzigbaar = r.groups.filter((g) => !g.dynamic);
  const weg = async (ids) => {
    const namen = r.groups.filter((g) => ids.includes(g.id)).map((g) => g.name);
    if (await ask(`${d.name} verwijderen uit:\n\n${namen.join('\n')}`, 'Verwijderen', true)) run('remove', ids);
  };
  return (
    <div className="cols2">
      <div>
        <table>
          <thead><tr>
            <th style={{ width: 30 }}><input type="checkbox" disabled={!wijzigbaar.length} checked={wijzigbaar.length > 0 && wijzigbaar.every((g) => vink.includes(g.id))}
              onChange={(e) => setVink(e.target.checked ? wijzigbaar.map((g) => g.id) : [])} /></th>
            <th>Groep</th><th>Type</th><th /></tr></thead>
          <tbody>
            {r.groups.map((g) => (
              <tr key={g.id}>
                <td><input type="checkbox" disabled={g.dynamic} checked={vink.includes(g.id)} onChange={(e) => setVink((v) => (e.target.checked ? [...v, g.id] : v.filter((x) => x !== g.id)))} /></td>
                <td>{g.name}</td><td>{g.dynamic ? <Chip k="o">dynamisch</Chip> : g.sec ? <Chip>Beveiliging</Chip> : <Chip k="mu">Overig</Chip>}</td>
                <td className="r">{!g.dynamic && <Btn s v="dl" icon={Trash2} onClick={() => weg([g.id])}>Uit groep</Btn>}</td></tr>
            ))}
            {!r.groups.length && <tr><td colSpan={4} className="hint">Dit apparaat zit in geen enkele groep.</td></tr>}
          </tbody>
        </table>
        {vink.length > 0 && <div style={{ marginTop: 10 }}><Btn v="d" s icon={Trash2} onClick={() => weg(vink)}>Uit {vink.length} groep(en) verwijderen</Btn></div>}
        <div className="hint">Dynamische groepen vullen zichzelf op basis van een regel; daaruit verwijder je een apparaat door de regel aan te passen.</div>
      </div>
      <div>
        <label className="f" style={{ marginTop: 0 }}>Toevoegen aan beveiligingsgroep (klik om toe te voegen)</label>
        <Picker items={r.all.filter((g) => !mijn.has(g.id)).map((g) => ({ v: g.id, l: g.name }))} placeholder="Zoek groep..."
          onPick={async (i) => { if (await ask(`${d.name} toevoegen aan ${i.l}?`, 'Toevoegen')) run('add', [i.v]); }} />
      </div>
    </div>
  );
}

function DBit({ d }) {
  const [r, setR] = useState(null);
  const [sleutels, setSleutels] = useState({});
  const win = /windows/i.test(d.os);
  useEffect(() => { if (win) act('dev.bitlocker', { aad: d.aad }, { msg: 'BitLocker-sleutels ophalen...' }).then((x) => setR(x || { keys: [] })); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!win) return <div className="hint">BitLocker-sleutels zijn alleen beschikbaar voor Windows-apparaten.</div>;
  if (!r) return <Loading />;
  const toon = async (k) => { const x = await act('dev.bitlockerkey', { id: k }, { msg: 'Sleutel ophalen...' }); if (x) setSleutels((s) => ({ ...s, [k]: x.key })); };
  return (
    <>
      <p style={{ marginTop: 0 }}>Herstelsleutels die in Entra ID voor dit apparaat zijn opgeslagen. Vergelijk het <b>sleutel-ID</b> met wat op het herstelscherm van de laptop staat.</p>
      <table>
        <thead><tr><th>Sleutel-ID</th><th>Schijf</th><th>Aangemaakt</th><th /></tr></thead>
        <tbody>
          {r.keys.map((k) => (
            <tr key={k.id}>
              <td colSpan={sleutels[k.id] ? 4 : 1}>
                <b>{k.id.slice(0, 8).toUpperCase()}</b><div className="hint" style={{ margin: 0 }}>{k.id}</div>
                {sleutels[k.id] && (
                  <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
                    <div className="pw" style={{ fontSize: 17, letterSpacing: 1 }}>{sleutels[k.id]}</div>
                    <div className="n"><Btn s v="p" icon={Copy} onClick={() => navigator.clipboard.writeText(sleutels[k.id]).then(() => toast('Gekopieerd.', 'g'), () => toast('Kopiëren is niet gelukt, selecteer de sleutel handmatig.', 'e'))}>Kopieer</Btn></div>
                  </div>
                )}
              </td>
              {!sleutels[k.id] && <><td>{schijf(k.vol)}</td><td>{dt(k.created)}</td><td className="r"><Btn s icon={HardDrive} onClick={() => toon(k.id)}>Sleutel tonen</Btn></td></>}
            </tr>
          ))}
          {!r.keys.length && <tr><td colSpan={4} className="hint">Geen BitLocker-herstelsleutels gevonden voor dit apparaat.</td></tr>}
        </tbody>
      </table>
      <div className="hint">Het opvragen van een sleutel wordt vastgelegd in de auditlog. Je hebt hiervoor een rol als Cloud Device Administrator, Helpdesk Administrator of Intune Administrator nodig.</div>
    </>
  );
}

function DAp({ d, herlaad }) {
  const a = d.autopilot;
  const [tag, setTag] = useState(a ? a.tag : '');
  if (!a) return <><p style={{ marginTop: 0 }}>Dit apparaat is <b>niet geregistreerd in Autopilot</b>.</p><div className="hint">Registratie van nieuwe apparaten gebeurt buiten dit scherm.</div></>;
  return (
    <>
      <div className="kv">
        <KV l="Group tag" v={a.tag} /><KV l="Profielstatus" v={apProf(a.profile)} />
        <KV l="Inschrijvingsstatus" v={a.state} /><KV l="Laatst contact" v={dt(a.contact)} />
      </div>
      <label className="f" style={{ marginTop: 18 }}>Group tag wijzigen</label>
      <div className="row"><input type="text" value={tag} onChange={(e) => setTag(e.target.value)} />
        <div className="n"><Btn v="p" icon={Save} onClick={async () => { if (await act('ap.tag', { ids: [a.id], tag: tag.trim() })) herlaad(); }}>Opslaan</Btn></div></div>
      <div style={{ marginTop: 16 }}>
        <Btn v="dl" icon={Trash2} onClick={async () => {
          if (await ask(`Autopilot-registratie van ${d.name} verwijderen?\n\nHet apparaat wordt dan niet meer automatisch ingericht bij een nieuwe start.`, 'Verwijderen', true) && await act('ap.delete', { ids: [a.id] })) herlaad();
        }}>Autopilot-registratie verwijderen</Btn>
      </div>
    </>
  );
}

function Wis({ d, close }) {
  const [e, setE] = useState(!!d.entra);
  const [a, setA] = useState(!!d.autopilot);
  return (
    <>
      <h3>{d.name} verwijderen</h3>
      <p>Het apparaat wordt uit Intune verwijderd. Het toestel zelf wordt niet gewist, maar het wordt niet meer beheerd.</p>
      <Check checked={e} disabled={!d.entra} onChange={setE}>Ook uit Entra ID verwijderen{d.entra ? '' : ' (niet gevonden)'}</Check>
      <Check checked={a} disabled={!d.autopilot} onChange={setA}>Ook de Autopilot-registratie verwijderen{d.autopilot ? '' : ' (niet geregistreerd)'}
        <div className="hint" style={{ margin: 0 }}>Laat je die staan, dan schrijft het apparaat zichzelf bij de volgende start weer in.</div></Check>
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="d" icon={Trash2} onClick={() => close({ entra: e, autopilot: a })}>Verwijderen</Btn></div>
    </>
  );
}

function WisMeer({ n, namen, close }) {
  const [e, setE] = useState(false);
  const [a, setA] = useState(false);
  const [bevestig, setBevestig] = useState('');
  return (
    <>
      <h3>{n} apparaten verwijderen</h3>
      <p>Deze apparaten worden uit Intune verwijderd. De toestellen zelf worden niet gewist, maar worden niet meer beheerd.</p>
      <div className="hint" style={{ maxHeight: 120, overflow: 'auto', margin: '0 0 8px' }}>{namen.join(', ')}</div>
      <Check checked={e} onChange={setE}>Ook uit Entra ID verwijderen</Check>
      <Check checked={a} onChange={setA}>Ook de Autopilot-registraties verwijderen
        <div className="hint" style={{ margin: 0 }}>Laat je die staan, dan schrijven de apparaten zich bij de volgende start weer in.</div></Check>
      <label className="f">Typ VERWIJDER om te bevestigen</label>
      <input value={bevestig} onChange={(x) => setBevestig(x.target.value)} />
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn>
        <Btn v="d" icon={Trash2} disabled={bevestig.trim().toUpperCase() !== 'VERWIJDER'} onClick={() => close({ entra: e, autopilot: a })}>Verwijderen</Btn></div>
    </>);
}

// Autopilot Reset: Windows opnieuw inrichten, het apparaat blijft ingeschreven in Intune en Entra
async function apReset(d) {
  const tekst = `Autopilot Reset voor ${d.name}${d.user ? ` (${d.user})` : ''}\n\n`
    + 'Bij de volgende check-in worden alle persoonlijke bestanden, apps en instellingen van het apparaat verwijderd. '
    + 'Windows wordt daarna opnieuw ingericht met de instellingen van de organisatie; het apparaat blijft ingeschreven in Intune en Entra ID.\n\n'
    + 'Let op: werkt alleen bij Windows 10/11 dat aan Entra ID is gekoppeld (niet hybride). De gebruiker moet daarna opnieuw inloggen. '
    + 'Zorg dat belangrijke bestanden in OneDrive staan.';
  if (!await askType(tekst, 'RESET', 'Reset starten')) return;
  await act('dev.apreset', { id: d.id }, { msg: 'Autopilot Reset starten...' });
}

async function wis(d, onDeleted) {
  const k = await openModal((close) => <Wis d={d} close={close} />);
  if (!k) return;
  if (await act('dev.delete', { id: d.id, ...k }, { msg: 'Verwijderen...' })) onDeleted();
}

// Zoeken op het herstelsleutel-ID dat op het BitLocker-herstelscherm van de laptop staat
function BitlockerZoeken({ onOpen }) {
  const [q, setQ] = useState('');
  const [r, setR] = useState(null);
  const [bezig, setBezig] = useState(false);
  const [sleutels, setSleutels] = useState({});
  const zoek = async () => {
    setBezig(true); setR(null);
    const x = await act('dev.bitlocker.zoek', { q });
    setBezig(false);
    if (x) setR(x);
  };
  const toon = async (id) => { const x = await act('dev.bitlockerkey', { id }, { msg: 'Sleutel ophalen...' }); if (x) setSleutels((s) => ({ ...s, [id]: x.key })); };
  return (
    <Card title="BitLocker-herstelsleutel zoeken" icon={KeyRound}>
      <div className="row">
        <input type="text" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && q.trim().length >= 4 && zoek()}
          placeholder="Sleutel-ID van het herstelscherm, bijv. 6F1C2A9B" style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace' }} />
        <div className="n"><Btn v="p" icon={Search} disabled={q.trim().length < 4 || bezig} onClick={zoek}>Zoeken</Btn></div>
      </div>
      {bezig && <Loading text="Alle herstelsleutels doorzoeken..." />}
      {r && (
        <>
          <div className="hint">{r.keys.length ? `${r.keys.length} sleutel(s) gevonden` : 'Geen sleutel gevonden met dit ID'} (doorzocht: {r.searched} sleutels).</div>
          {r.keys.length > 0 && (
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Sleutel-ID</th><th>Apparaat</th><th>Schijf</th><th>Aangemaakt</th><th /></tr></thead>
              <tbody>{r.keys.map((k) => (
                <tr key={k.id}>
                  <td colSpan={sleutels[k.id] ? 5 : 1}>
                    <b>{k.id.slice(0, 8).toUpperCase()}</b><div className="hint" style={{ margin: 0 }}>{k.id}</div>
                    {sleutels[k.id] && (
                      <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
                        <div className="pw" style={{ fontSize: 17, letterSpacing: 1 }}>{sleutels[k.id]}</div>
                        <div className="n"><Btn s v="p" icon={Copy} onClick={() => navigator.clipboard.writeText(sleutels[k.id]).then(() => toast('Gekopieerd.', 'g'))}>Kopieer</Btn></div>
                      </div>
                    )}
                  </td>
                  {!sleutels[k.id] && <>
                    <td>{k.device || '-'}{k.user && <div className="hint" style={{ margin: 0 }}>{k.user}</div>}</td>
                    <td>{schijf(k.vol)}</td><td>{dt(k.created)}</td>
                    <td className="r"><div className="btns" style={{ justifyContent: 'flex-end' }}>
                      <Btn s icon={HardDrive} onClick={() => toon(k.id)}>Sleutel tonen</Btn>
                      {k.intuneId && <Btn s onClick={() => onOpen(k.intuneId)}>Apparaat openen</Btn>}
                    </div></td>
                  </>}
                </tr>))}</tbody>
            </table>
          )}
        </>
      )}
      <div className="hint">Het opvragen van een sleutel wordt vastgelegd in de auditlog van Entra.</div>
    </Card>
  );
}
