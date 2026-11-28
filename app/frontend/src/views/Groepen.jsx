import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, RefreshCw, Trash2, UserPlus, UsersRound } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, askType, openModal, toast } from '../overlays.jsx';
import { toonKlus } from '../Klus.jsx';
import { clearCache, doorgeven, getUsers, useApp } from '../store.jsx';
import { AllesVink, Btn, Card, Check, Chip, Field, Loading, Picker, SearchBox, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';
import { typeChip } from './Gebruikers.jsx';


export default function Groepen() {
  const [gr, setGr] = useState(null);
  const [start] = useState(() => { const z = doorgeven.zoek; if (z && z.soort === 'group') { delete doorgeven.zoek; return z; } return null; });
  const [q, setQ] = useState(start ? start.q : '');
  const [type, setType] = useState('');
  const [sel, setSel] = useState(start ? start.id : null);
  const [vink, setVink] = useState([]);
  // Net verwijderd: direct uit de lijst, ook als Microsoft ze nog even teruggeeft
  const weg = useRef(new Map());
  const filter = (l) => { const nu = Date.now(); return l.filter((g) => !(weg.current.get(g.id) > nu)); };
  const laad = async (fresh) => {
    const d = await act('groups.list', { fresh: !!fresh }, { msg: 'Groepen en postvakken ophalen...' });
    setGr(d ? filter(d.groups) : []);
  };
  const verwijderd = (ids) => {
    ids.forEach((i) => weg.current.set(i, Date.now() + 180000));
    setGr((l) => (l ? filter(l) : l));
    laad(true);
  };
  // Nieuw aangemaakt: direct live ophalen, en nog eens zodra Microsoft het overal heeft verwerkt
  const aangemaakt = () => { laad(true); setTimeout(() => laad(true), 8000); };
  useEffect(() => { laad(false); }, []);
  const types = useMemo(() => [...new Set((gr || []).map((g) => g.type))].sort(), [gr]);
  const shown = useFilter(gr || [], q, (g) => [g.name, g.mail, g.type]).filter((g) => !type || g.type === type);
  if (!gr) return <Loading text="Groepen en postvakken ophalen..." />;
  const g = gr.find((x) => x.id === sel);
  const gekozen = gr.filter((x) => vink.includes(x.id));
  const bulkWeg = async () => {
    const postvakken = gekozen.filter((x) => x.type === 'Gedeeld postvak').length;
    if (!await askType(`${gekozen.length} item(s) definitief verwijderen:\n\n${gekozen.slice(0, 15).map((x) => `${x.name} (${x.type})`).join('\n')}${gekozen.length > 15 ? `\n... en ${gekozen.length - 15} meer` : ''}`
      + (postvakken ? `\n\nLET OP: ${postvakken} gedeeld(e) postvak(ken), inclusief alle e-mail daarin.` : '') + '\n\nMicrosoft 365-groepen staan daarna 30 dagen in de prullenbak.', 'VERWIJDEREN')) return;
    await toonKlus(await act('group.deletemany', { groups: gekozen.map((x) => ({ type: x.type, id: x.id, mail: x.mail, name: x.name })) }, { msg: 'Starten...' }));
    const ids = gekozen.map((x) => x.id);
    setVink([]); setSel(null); clearCache('shared'); verwijderd(ids);
  };
  return (
    <>
      <h2>Groepen en postvakken</h2>
      <p className="sub">Microsoft 365-groepen, beveiligingsgroepen, distributielijsten en gedeelde postvakken beheren, aanmaken en verwijderen. Vink items aan om er meerdere tegelijk te verwijderen.</p>
      {vink.length > 0 && (
        <div className="updbalk">
          <UsersRound size={18} style={{ flex: 'none' }} />
          <div style={{ flex: 1 }}><b>{vink.length} geselecteerd</b></div>
          <Btn s v="dl" icon={Trash2} onClick={bulkWeg}>Verwijderen</Btn>
          <Btn s onClick={() => setVink([])}>Selectie wissen</Btn>
        </div>
      )}
      <div className="cols">
        <div className="sticky">
          <div className="row">
            <SearchBox value={q} onChange={setQ} />
            <select className="n" style={{ width: 'auto' }} value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">Alle typen</option>{types.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
          <AllesVink ids={shown.slice(0, MAX_RIJEN).filter((x) => !x.sync).map((x) => x.id)} value={vink} onChange={setVink} />
          <div className="list" style={{ maxHeight: 'calc(100vh - 340px)' }}>
            {shown.slice(0, MAX_RIJEN).map((x) => (
              <div key={x.id} className={'li' + (x.id === sel ? ' on' : '') + (x.edit ? '' : ' grey')} onClick={() => setSel(x.id)}>
                <input type="checkbox" disabled={x.sync} checked={vink.includes(x.id)} onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setVink((v) => (e.target.checked ? [...v, x.id] : v.filter((y) => y !== x.id)))} title={x.sync ? 'Komt van on-premises: daar verwijderen' : ''} />
                <span className="m"><b>{x.name}</b><small>{x.mail || '—'}</small></span>{typeChip(x.type)}
              </div>
            ))}
            {!shown.length && <div className="li empty">Niets gevonden</div>}
            <Meer totaal={shown.length} />
          </div>
          <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
            <div className="count" style={{ flex: 1, margin: 0 }}>{shown.length} items. Grijs = niet te wijzigen (dynamisch of on-premises).</div>
            <div className="n btns"><Btn v="p" s icon={Plus} onClick={() => nieuw(aangemaakt)}>Nieuw</Btn><Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn></div>
          </div>
        </div>
        <div>{g ? <Detail key={g.id} g={g} onDeleted={() => { setSel(null); verwijderd([g.id]); }} />
          : <div className="card muted"><UsersRound size={18} />Kies links een groep of postvak.</div>}</div>
      </div>
    </>
  );
}

function Detail({ g, onDeleted }) {
  const [d, setD] = useState(null);
  const [users, setUsers] = useState([]);
  const [vink, setVink] = useState([]);
  const [r, setR] = useState({ full: true, send: true, behalf: false, auto: true });
  const [wijzig, setWijzig] = useState({});   // lid -> aangepaste rechten (nog niet opgeslagen)
  const sh = g.type === 'Gedeeld postvak';
  const laad = async () => {
    setVink([]); setWijzig({});
    const x = await act('group.members', { type: g.type, id: g.id, mail: g.mail }, { msg: 'Leden ophalen...' });
    setD(x ? x.members : []);
  };
  useEffect(() => { laad(); getUsers().then(setUsers).catch(() => {}); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const verwijder = async () => {
    if (!await ask(`LET OP: ${g.type} '${g.name}' wordt definitief verwijderd.\n\nDit kan niet ongedaan gemaakt worden${sh ? ' (ook alle e-mail in het postvak verdwijnt)' : ''}. Doorgaan?`, 'Verwijderen', true)) return;
    if (sh && !await ask(`Laatste controle: postvak ${g.mail} en alle e-mail daarin echt verwijderen?`, 'Ja, verwijderen', true)) return;
    if (await act('group.delete', { type: g.type, id: g.id, mail: g.mail, name: g.name }, { msg: 'Verwijderen...' })) { clearCache('shared'); onDeleted(); }
  };
  const leden = new Set((d || []).map((m) => m.key.toLowerCase()));
  return (
    <>
      <div className="card">
        <div className="headrow">
          <div className="m"><h3>{g.name}</h3><div className="hint" style={{ margin: 0 }}>{g.mail} {typeChip(g.type)} {g.sync && <Chip k="o">on-premises</Chip>}</div></div>
          <Btn v="dl" icon={Trash2} disabled={g.sync} onClick={verwijder}>{g.type} verwijderen</Btn>
        </div>
      </div>
      <Card title={`${sh ? 'Wie heeft toegang' : 'Leden'}${d ? ` (${d.length})` : ''}`} icon={UsersRound}
        right={g.edit && vink.length ? <Btn s v="d" icon={Trash2} onClick={async () => {
          const m = d.filter((x) => vink.includes(x.id));
          if (!await ask(`Verwijderen uit ${g.name}:\n\n${m.map((x) => x.name).join('\n')}`, 'Verwijderen', true)) return;
          if (await act('group.remove', { type: g.type, id: g.id, mail: g.mail, members: m })) laad();
        }}>{vink.length} verwijderen</Btn> : null}>
        {!d ? <Loading /> : (
          <>{g.edit && <AllesVink ids={d.map((m) => m.id)} value={vink} onChange={setVink} />}
          <table>
            {sh && d.length > 0 && <thead><tr><th style={{ width: 30 }} /><th>Wie</th><th>Volledige toegang</th><th>Verzenden als</th><th>Verzenden namens</th><th>Automapping</th><th /></tr></thead>}
            <tbody>
            {d.map((m) => {
              const w = wijzig[m.id];
              const v = w || { full: !!m.full, send: !!m.send, behalf: !!m.behalf, auto: '' };
              const zet = (k, val) => setWijzig((o) => ({ ...o, [m.id]: { ...v, [k]: val } }));
              const anders = w && (w.full !== !!m.full || w.send !== !!m.send || w.behalf !== !!m.behalf || (w.auto !== '' && w.full));
              const bewaar = async () => {
                if (!v.full && !v.send && !v.behalf) return toast('Laat minimaal een recht aan, of verwijder de persoon met het vinkje links.', 'e');
                if (await act('shared.member.set', { mail: g.mail, key: m.key, full: v.full, send: v.send, behalf: v.behalf,
                  auto: v.auto === '' ? null : v.auto === 'aan', was: { full: !!m.full, send: !!m.send, behalf: !!m.behalf } }, { msg: `Rechten van ${m.key} opslaan...` })) laad();
              };
              return (
                <tr key={m.id}>
                  <td style={{ width: 30 }}><input type="checkbox" disabled={!g.edit} checked={vink.includes(m.id)} onChange={(e) => setVink((x) => (e.target.checked ? [...x, m.id] : x.filter((y) => y !== m.id)))} /></td>
                  <td>{m.name}{m.key !== m.name && <div className="hint" style={{ margin: 0 }}>{m.key}</div>}</td>
                  {sh ? <>
                    <td><input type="checkbox" disabled={!g.edit} checked={v.full} onChange={(e) => zet('full', e.target.checked)} /></td>
                    <td><input type="checkbox" disabled={!g.edit} checked={v.send} onChange={(e) => zet('send', e.target.checked)} /></td>
                    <td><input type="checkbox" disabled={!g.edit} checked={v.behalf} onChange={(e) => zet('behalf', e.target.checked)} /></td>
                    <td><select value={v.auto} disabled={!g.edit || !v.full} onChange={(e) => zet('auto', e.target.value)} title="Automapping is bij Microsoft niet uit te lezen. Kies aan of uit om het opnieuw in te stellen.">
                      <option value="">{m.full ? 'Ongewijzigd' : 'Aan (standaard)'}</option><option value="aan">Aan</option><option value="uit">Uit</option></select></td>
                    <td className="r">{anders && <><Btn s v="p" onClick={bewaar}>Opslaan</Btn> <Btn s onClick={() => setWijzig((o) => { const n = { ...o }; delete n[m.id]; return n; })}>Annuleren</Btn></>}</td>
                  </> : <td>{m.info}</td>}
                </tr>
              );
            })}
            {!d.length && <tr><td className="hint">Geen leden.</td></tr>}
          </tbody></table></>
        )}
      </Card>
      {g.edit ? (
        <Card title={sh ? 'Toegang geven' : 'Lid toevoegen'} icon={UserPlus}>
          {sh && (
            <div className="row" style={{ marginTop: -6 }}>
              <Check checked={r.full} onChange={(v) => setR({ ...r, full: v })}>Volledige toegang</Check>
              <Check checked={r.send} onChange={(v) => setR({ ...r, send: v })}>Verzenden als</Check>
              <Check checked={r.behalf} onChange={(v) => setR({ ...r, behalf: v })}>Verzenden namens</Check>
              <Check checked={r.auto} onChange={(v) => setR({ ...r, auto: v })}>Automapping</Check>
            </div>
          )}
          <Picker placeholder="Zoek gebruiker en klik om toe te voegen..." height={200}
            items={users.filter((u) => !leden.has(u.upn.toLowerCase())).map((u) => ({ v: u.id, l: u.name, s: u.upn }))}
            onPick={async (i) => {
              if (sh && !(r.full || r.send || r.behalf)) return toast('Vink minimaal een recht aan.', 'e');
              if (!await ask(`${i.l} toevoegen aan ${g.name}?`, 'Toevoegen')) return;
              if (await act('group.add', { type: g.type, id: g.id, mail: g.mail, userId: i.v, ...(sh ? r : {}) }, { msg: 'Toevoegen...' })) laad();
            }} />
        </Card>
      ) : <Msg kind="warn">Deze groep is dynamisch of komt van on-premises en kan hier niet worden gewijzigd.</Msg>}
    </>
  );
}

const HINT = {
  M365: 'Krijgt ook een gedeelde agenda, postvak en SharePoint-site.',
  Beveiliging: 'Zonder mailadres; de alias is alleen een interne naam.',
  Distributielijst: 'Mail naar het adres gaat naar alle leden.',
  Gedeeld: 'Postvak zonder eigen licentie (tot 50 GB). Daarna geef je gebruikers toegang.',
};

function Nieuw({ close, onDone }) {
  const { info } = useApp();
  const [k, setK] = useState('M365');
  const [n, setN] = useState('');
  const [a, setA] = useState('');
  const [dom, setDom] = useState(info.defaultDomain);
  const exoNodig = k === 'Distributielijst' || k === 'Gedeeld';
  const ok = async () => {
    const alias = a.trim().toLowerCase();
    if (!n.trim() || !/^[a-z0-9._-]+$/.test(alias)) return toast('Vul een naam en een geldig adres in (kleine letters, cijfers, punt, streepje).', 'e');
    close();
    if (await act('group.create', { kind: k, name: n.trim(), alias, domain: dom }, { msg: 'Aanmaken...' })) {
      clearCache('shared'); onDone();
    }
  };
  return (
    <>
      <h3>Nieuw aanmaken bij {info.tenant}</h3>
      <label className="f">Soort</label>
      <select value={k} onChange={(e) => setK(e.target.value)}>
        <option value="M365">Microsoft 365-groep</option><option value="Beveiliging">Beveiligingsgroep</option>
        <option value="Distributielijst">Distributielijst</option><option value="Gedeeld">Gedeeld postvak</option>
      </select>
      <Field label="Naam *" value={n} onChange={(v) => { setN(v); if (!a || a === n.toLowerCase().replace(/[^a-z0-9]+/g, '.')) setA(v.toLowerCase().replace(/[^a-z0-9]+/g, '.').replace(/^\.|\.$/g, '')); }} autoFocus />
      <label className="f">E-mailadres / alias *</label>
      <div className="row"><input type="text" value={a} onChange={(e) => setA(e.target.value)} />
        <select value={dom} disabled={k === 'Beveiliging'} onChange={(e) => setDom(e.target.value)}>{info.domains.map((d) => <option key={d.id}>{d.id}</option>)}</select></div>
      <div className="hint">{HINT[k]}</div>
      {exoNodig && info.exo === false && <Msg kind="warn">Hiervoor is Exchange Online nodig, en dat is niet verbonden.</Msg>}
      <div className="foot"><Btn onClick={() => close()}>Annuleren</Btn><Btn v="p" icon={Plus} disabled={exoNodig && info.exo === false} onClick={ok}>Aanmaken</Btn></div>
    </>
  );
}

function nieuw(onDone) {
  openModal((close) => <Nieuw close={close} onDone={onDone} />);
}
