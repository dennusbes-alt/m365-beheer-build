// Windows Autopilot: geregistreerde apparaten, synchroniseren, group tag en verwijderen.
import { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw, Rocket, Tag, Trash2 } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, askType, openModal } from '../overlays.jsx';
import { Btn, Check, Chip, Loading, SearchBox, csv, dt, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';

const PROFIEL = {
  assignedinsync: ['Profiel toegewezen', 'g'], assignedunkownsyncstate: ['Profiel toegewezen', 'g'], assignedoutofsync: ['Toegewezen, niet gesynchroniseerd', 'o'],
  notassigned: ['Geen profiel', 'r'], pending: ['In behandeling', 'o'], failed: ['Mislukt', 'r'],
};
const profiel = (p) => { const x = PROFIEL[String(p).toLowerCase()] || [p || 'Onbekend', 'mu']; return <Chip k={x[1]}>{x[0]}</Chip>; };
const STAAT = { enrolled: 'Ingeschreven', notcontacted: 'Nog niet ingeschreven', pendingreset: 'Wacht op reset', failed: 'Mislukt', blocked: 'Geblokkeerd' };
const staat = (s) => STAAT[String(s).toLowerCase()] || s || '-';
const SYNC = { completed: ['Gelukt', 'g'], inprogress: ['Bezig', 'o'], failed: ['Mislukt', 'r'], unknown: ['Onbekend', 'mu'] };

export default function Autopilot() {
  const [d, setD] = useState(null);
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('');
  const [tagF, setTagF] = useState('');
  const [vink, setVink] = useState([]);
  const laad = async (fresh) => {
    const x = await act('ap.list', { fresh: !!fresh }, { msg: 'Autopilot-apparaten ophalen...' });
    setD(x || { items: [], fout: true }); setVink([]);
  };
  useEffect(() => { laad(false); }, []);
  const items = d ? d.items : [];
  const tags = useMemo(() => [...new Set(items.map((x) => x.tag).filter(Boolean))].sort(), [items]);
  const shown = useFilter(items, q, (x) => [x.serial, x.model, x.man, x.tag, x.upn, x.name, x.order]).filter((x) => (
    (!tagF || (tagF === '-' ? !x.tag : x.tag === tagF))
    && (!filter || (filter === 'intune' ? !!x.intune : filter === 'los' ? !x.intune : !['assignedinsync', 'assignedunkownsyncstate'].includes(String(x.profile).toLowerCase())))));
  if (!d) return <Loading text="Autopilot-apparaten ophalen..." />;
  const gekozen = items.filter((x) => vink.includes(x.id));
  const alles = shown.length > 0 && shown.slice(0, MAX_RIJEN).every((x) => vink.includes(x.id));
  const sync = SYNC[String(d.syncStatus).toLowerCase()];

  const synchroniseer = async () => {
    if (!await ask('Autopilot synchroniseren?\n\nApparaten die de leverancier of distributeur voor deze klant heeft geregistreerd, worden opgehaald. Microsoft staat dit maximaal eens per 10 minuten toe.', 'Synchroniseren')) return;
    if (await act('ap.sync', {}, { msg: 'Synchronisatie starten...' })) setTimeout(() => laad(true), 4000);
  };
  const verwijder = async (lijst) => {
    const k = await openModal((close) => <Weg lijst={lijst} close={close} />);
    if (!k) return;
    if (lijst.length > 5 && !await askType(`Je verwijdert ${lijst.length} Autopilot-registraties${k.intune ? ' én de bijbehorende Intune-apparaten' : ''}. Dit kan niet ongedaan gemaakt worden.`, 'VERWIJDEREN')) return;
    await act('ap.delete', { ids: lijst.map((x) => x.id), intune: k.intune }, { msg: `${lijst.length} registratie(s) verwijderen...` });
    laad(true);
  };
  const tagZetten = async (lijst) => {
    const t = await openModal((close) => <TagVenster lijst={lijst} tags={tags} close={close} />);
    if (t == null) return;
    if (await act('ap.tag', { ids: lijst.map((x) => x.id), tag: t }, { msg: 'Group tag aanpassen...' })) laad(true);
  };

  return (
    <>
      <h2>Autopilot</h2>
      <p className="sub">Windows-apparaten die bij deze klant in Autopilot zijn geregistreerd: synchroniseren, group tag aanpassen en registraties verwijderen.</p>
      <div className="card">
        <div className="headrow">
          <div className="m">
            <h3 style={{ margin: 0 }}><Rocket size={18} style={{ verticalAlign: -3 }} /> {items.length} geregistreerde apparaten</h3>
            <div className="hint" style={{ margin: '4px 0 0' }}>
              Laatste synchronisatie: {d.lastSync ? dt(d.lastSync) : 'onbekend'} {sync && <Chip k={sync[1]}>{sync[0]}</Chip>}
              {d.lastManualSync && <> · handmatig gestart: {dt(d.lastManualSync)}</>}
            </div>
          </div>
          <div className="btns">
            <Btn v="p" icon={RefreshCw} onClick={synchroniseer}>Synchroniseren</Btn>
            <Btn icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn>
          </div>
        </div>
      </div>
      {d.fout && <Msg kind="warn">De Autopilot-gegevens konden niet opgehaald worden.</Msg>}
      <div className="card">
        <div className="row">
          <SearchBox value={q} onChange={setQ} placeholder="Zoek op serienummer, model, group tag of gebruiker..." />
          <div className="n">
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">Alle apparaten</option><option value="intune">Ingeschreven in Intune</option>
              <option value="los">Niet in Intune</option><option value="profiel">Zonder (gesynchroniseerd) profiel</option>
            </select>
          </div>
          <div className="n">
            <select value={tagF} onChange={(e) => setTagF(e.target.value)}>
              <option value="">Alle group tags</option><option value="-">Zonder group tag</option>{tags.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <div className="row" style={{ margin: '10px 0', alignItems: 'center' }}>
          <div className="count" style={{ flex: 1, margin: 0 }}>{shown.length} apparaten{vink.length ? ` · ${vink.length} geselecteerd` : ''}</div>
          <div className="n btns">
            <Btn s icon={Tag} disabled={!vink.length} onClick={() => tagZetten(gekozen)}>Group tag</Btn>
            <Btn s v="dl" icon={Trash2} disabled={!vink.length} onClick={() => verwijder(gekozen)}>Verwijderen{vink.length ? ` (${vink.length})` : ''}</Btn>
            <Btn s icon={Download} disabled={!shown.length} onClick={() => csv('autopilot.csv', [['Serienummer', 'Fabrikant', 'Model', 'Group tag', 'Profiel', 'Status', 'Laatst contact', 'Gebruiker', 'In Intune', 'Inkooporder'],
              ...shown.map((x) => [x.serial, x.man, x.model, x.tag, x.profile, staat(x.state), x.contact, x.upn, x.intune ? 'Ja' : 'Nee', x.order])])}>Exporteren</Btn>
          </div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead><tr>
              <th style={{ width: 30 }}><input type="checkbox" checked={alles} onChange={(e) => setVink(e.target.checked ? shown.slice(0, MAX_RIJEN).map((x) => x.id) : [])} /></th>
              <th>Serienummer</th><th>Model</th><th>Group tag</th><th>Profiel</th><th>Status</th><th>Laatst contact</th><th /></tr></thead>
            <tbody>
              {shown.slice(0, MAX_RIJEN).map((x) => (
                <tr key={x.id}>
                  <td><input type="checkbox" checked={vink.includes(x.id)} onChange={(e) => setVink((v) => (e.target.checked ? [...v, x.id] : v.filter((y) => y !== x.id)))} /></td>
                  <td><b>{x.serial}</b>{(x.name || x.upn) && <div className="hint" style={{ margin: 0 }}>{[x.name, x.upn].filter(Boolean).join(' · ')}</div>}</td>
                  <td>{x.man} {x.model}</td>
                  <td>{x.tag ? <Chip>{x.tag}</Chip> : <span className="hint">-</span>}</td>
                  <td>{profiel(x.profile)}</td>
                  <td>{staat(x.state)}{x.intune && <div><Chip k="g">in Intune</Chip></div>}</td>
                  <td>{dt(x.contact)}</td>
                  <td className="r"><Btn s v="dl" icon={Trash2} onClick={() => verwijder([x])} title="Registratie verwijderen" /></td>
                </tr>
              ))}
              {!shown.length && <tr><td colSpan={8} className="hint">Geen Autopilot-apparaten gevonden.</td></tr>}
            </tbody>
          </table>
        </div>
        <Meer totaal={shown.length} />
      </div>
    </>
  );
}

function Weg({ lijst, close }) {
  const inIntune = lijst.filter((x) => x.intune).length;
  const [intune, setIntune] = useState(inIntune > 0);
  const naam = lijst.length === 1 ? lijst[0].serial : `${lijst.length} apparaten`;
  return (
    <>
      <h3>Autopilot-registratie verwijderen: {naam}</h3>
      <p>Het apparaat wordt daarna bij een nieuwe installatie <b>niet meer automatisch ingericht</b> voor deze klant. Doe dit bijvoorbeeld bij verkoop, retour of een defect toestel.</p>
      {inIntune > 0 ? (
        <>
          <Msg kind="warn">{inIntune === lijst.length ? (lijst.length === 1 ? 'Dit apparaat staat' : 'Deze apparaten staan') : `${inIntune} van de ${lijst.length} apparaten ${inIntune === 1 ? 'staat' : 'staan'}`} nog in Intune. Microsoft verwijdert een Autopilot-registratie pas als het apparaat eerst uit Intune is verwijderd.</Msg>
          <Check checked={intune} onChange={setIntune}>Ook uit Intune verwijderen
            <div className="hint" style={{ margin: 0 }}>Het toestel zelf wordt niet gewist, maar wordt niet meer beheerd.</div></Check>
        </>
      ) : null}
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="d" icon={Trash2} onClick={() => close({ intune })}>Verwijderen</Btn></div>
    </>
  );
}

function TagVenster({ lijst, tags, close }) {
  const [t, setT] = useState(lijst.length === 1 ? lijst[0].tag : '');
  return (
    <>
      <h3>Group tag voor {lijst.length === 1 ? lijst[0].serial : `${lijst.length} apparaten`}</h3>
      <p>Met de group tag bepaal je via dynamische groepen welk Autopilot-profiel en welke apps een apparaat krijgt. Laat leeg om de tag te verwijderen.</p>
      <input type="text" list="ap-tags" value={t} onChange={(e) => setT(e.target.value)} autoFocus placeholder="Bijv. Kantoor" />
      <datalist id="ap-tags">{tags.map((x) => <option key={x} value={x} />)}</datalist>
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" icon={Tag} onClick={() => close(t.trim())}>Opslaan</Btn></div>
    </>
  );
}
