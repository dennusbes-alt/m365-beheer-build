// Nieuwe medewerker toegang geven per map (bijv. één site 'Data' met per map eigen machtigingen via SharePoint-groepen):
// alle mappen met eigen machtigingen in één lijst, aanvinken wat de medewerker nodig heeft, de app zet hem in de juiste groepen.
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, CheckCircle2, Copy, Folder, FolderLock, UserPlus, Users } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, toast } from '../overlays.jsx';
import { getUsers } from '../store.jsx';
import { AllesVink, Btn, Card, Chip, Loading, Picker, SearchBox } from '../ui.jsx';

const DIRECT = '__direct';
const RECHT = { Lezen: 'mag alleen lezen', Bewerken: 'mag bewerken', 'Volledig beheer': 'volledig beheer (ook rechten wijzigen)' };
const uitleg = (a) => `via groep '${a.name}' · ${RECHT[a.role] || a.role.toLowerCase()}`;
const sleutel = (d) => `${d.listId}|${d.itemId ?? ''}`;

export default function MappenOnboarding({ site, vooraf, onTerug }) {
  const [kaart, setKaart] = useState(null);
  const [fout, setFout] = useState('');
  const [users, setUsers] = useState(null);
  const [wie, setWie] = useState(null);
  const [collega, setCollega] = useState(null);
  const [kies, setKies] = useState([]);          // sleutels van aangevinkte mappen
  const [via, setVia] = useState({});            // sleutel -> gekozen toegang (groep-id, 'e:<entraId>' of DIRECT)
  const [q, setQ] = useState('');
  const [klaar, setKlaar] = useState(null);

  useEffect(() => {
    api('spm.toegangskaart', { site: site.url }, { quiet: true }).then(setKaart).catch((e) => { setFout(e.message); setKaart({ folders: [], groups: [] }); });
    getUsers().then((u) => {
      setUsers(u);
      if (vooraf) { const x = u.find((y) => y.upn.toLowerCase() === vooraf.toLowerCase() || y.mail?.toLowerCase() === vooraf.toLowerCase()); if (x) setWie(x); }
    }).catch(() => setUsers([]));
  }, [site.url]); // eslint-disable-line react-hooks/exhaustive-deps

  const leden = useMemo(() => Object.fromEntries((kaart?.groups || []).map((g) => [g.id, new Set(g.members)])), [kaart]);
  // Keuzes per map: eerst de groepen die specifiek voor deze map zijn, de standaardgroepen van de site alleen als er niets anders is
  const opties = (d) => {
    const groepen = d.access.filter((a) => a.spGroup || a.entraId);
    const eigen = groepen.filter((a) => !a.default);
    const voorkeur = { Bewerken: 0, Lezen: 1, 'Volledig beheer': 2 };   // standaardgroepen: liefst 'leden', nooit eerst 'eigenaars'
    return [...(eigen.length ? eigen : [...groepen].sort((x, y) => voorkeur[x.role] - voorkeur[y.role])).map((a) => ({ v: a.spGroup ? String(a.id) : `e:${a.entraId}`, l: uitleg(a), a })),
      { v: DIRECT, l: 'zonder groep, direct op de map · mag bewerken' }];
  };
  const keuze = (d) => via[sleutel(d)] || opties(d)[0].v;
  const isLid = (d, upn) => {
    if (!upn) return false;
    const k = keuze(d);
    return !k.startsWith('e:') && k !== DIRECT && !!leden[Number(k)]?.has(upn.toLowerCase());
  };
  const viaCollega = (upn) => {
    if (!kaart) return;
    const u = upn.toLowerCase();
    const treffers = kaart.folders.filter((d) => d.itemId != null && d.access.some((a) => a.spGroup && !a.default && leden[a.id]?.has(u)));
    setKies(treffers.map(sleutel));
    setVia(Object.fromEntries(treffers.map((d) => [sleutel(d), String(d.access.find((a) => a.spGroup && !a.default && leden[a.id]?.has(u)).id)])));
    toast(treffers.length ? `${treffers.length} map(pen) aangevinkt zoals ${upn}.` : `${upn} zit in geen van de mapgroepen.`, treffers.length ? 'g' : undefined);
  };

  if (!kaart || !users) return <><Kop site={site} onTerug={onTerug} /><Loading text="Alle mappen met eigen machtigingen en hun groepen ophalen..." /></>;
  const zicht = kaart.folders.filter((d) => !q || `${d.rel} ${d.name} ${d.access.map((a) => a.name).join(' ')}`.toLowerCase().includes(q.toLowerCase()));
  const gekozen = kaart.folders.filter((d) => kies.includes(sleutel(d)));
  const plan = { sp: new Map(), entra: new Map(), direct: [] };
  gekozen.forEach((d) => {
    const k = keuze(d);
    const o = opties(d).find((x) => x.v === k);
    if (k === DIRECT) plan.direct.push({ listId: d.listId, itemId: d.itemId, label: d.rel || d.name, level: 'edit' });
    else if (k.startsWith('e:')) plan.entra.set(k.slice(2), { id: k.slice(2), name: o.a.name });
    else plan.sp.set(Number(k), { id: Number(k), name: o.a.name });
  });
  const upn = wie?.upn || '';
  const nieuwSp = [...plan.sp.values()].filter((g) => !leden[g.id]?.has(upn.toLowerCase()));

  const uitvoeren = async () => {
    const regels = [...nieuwSp.map((g) => `SharePoint-groep ${g.name}`), ...[...plan.entra.values()].map((g) => `Entra-groep ${g.name}`), ...plan.direct.map((d) => `map ${d.label} (direct)`)];
    if (!regels.length) return toast(`${wie.name} heeft al toegang tot alle gekozen mappen.`);
    if (!await ask(`${wie.name} toegang geven via:\n\n${regels.join('\n')}`, 'Toegang geven')) return;
    const r = await act('spm.onboard', { site: site.url, upn, spGroups: nieuwSp, entraGroups: [...plan.entra.values()], direct: plan.direct }, { msg: 'Toegang geven...' });
    if (r) {
      setKlaar(r);
      api('spm.toegangskaart', { site: site.url }, { quiet: true }).then(setKaart).catch(() => {});   // 'al toegang' bijwerken
    }
  };

  return (
    <>
      <Kop site={site} onTerug={onTerug} />
      {fout && <Msg kind="warn">{fout}</Msg>}
      {kaart.truncated && <Msg kind="info">Er zijn meer dan 400 mappen met eigen machtigingen; alleen de eerste 400 staan hieronder.</Msg>}
      {klaar && <Msg kind={klaar.errors.length ? 'warn' : 'ok'}><b>{wie?.name}</b> heeft toegang gekregen via {klaar.done.join(', ') || '-'}.
        {klaar.errors.map((e) => <div key={e}>Niet gelukt: {e}</div>)}
        <div className="hint" style={{ margin: '4px 0 0' }}>Het kan een paar minuten duren voordat de mappen in OneDrive/Teams verschijnen.</div></Msg>}
      <div className="cols">
        <div className="sticky">
          <Card title="1. Wie" icon={UserPlus}>
            {wie ? (
              <div className="li on" style={{ cursor: 'default' }}><span className="m"><b>{wie.name}</b><small>{wie.upn}</small></span>
                <Btn s onClick={() => { setWie(null); setKlaar(null); }}>Wijzigen</Btn></div>
            ) : <Picker items={users.filter((u) => !u.guest).map((u) => ({ v: u.id, l: u.name, s: u.upn }))} placeholder="Zoek de nieuwe medewerker..."
              onPick={(i) => { setWie(users.find((u) => u.id === i.v)); setKlaar(null); }} />}
          </Card>
          <Card title="Zelfde mappen als een collega (optioneel)" icon={Copy}>
            {collega ? <div className="li" style={{ cursor: 'default' }}><span className="m"><b>{collega.name}</b><small>{collega.upn}</small></span>
              <Btn s onClick={() => setCollega(null)}>Andere</Btn></div>
              : <Picker items={users.filter((u) => !u.guest && u.id !== wie?.id).map((u) => ({ v: u.id, l: u.name, s: u.upn }))} height={160} placeholder="Zoek collega..."
                onPick={(i) => { const c = users.find((u) => u.id === i.v); setCollega(c); viaCollega(c.upn); }} />}
            <div className="hint">Vinkt de mappen aan waarvan de collega lid is van de mapgroep. Daarna kun je aanpassen.</div>
          </Card>
        </div>
        <div>
          <Card title={`2. Welke mappen (${gekozen.length} gekozen)`} icon={FolderLock} right={<SearchBox value={q} onChange={setQ} placeholder="Zoek map of groep..." />}>
            <AllesVink ids={zicht.map(sleutel)} value={kies} onChange={setKies} label={q ? 'Alle gevonden mappen' : 'Alle mappen'} />
            <table>
              <thead><tr><th style={{ width: 28 }} /><th>Map</th><th>Zo krijgt de medewerker toegang</th><th /></tr></thead>
              <tbody>{zicht.map((d) => {
                const k = sleutel(d);
                const o = opties(d);
                const aan = kies.includes(k);
                return (
                  <tr key={k} style={aan ? { background: 'var(--acl)' } : undefined}>
                    <td><input type="checkbox" checked={aan} onChange={(e) => setKies((x) => (e.target.checked ? [...x, k] : x.filter((y) => y !== k)))} /></td>
                    <td style={{ paddingLeft: 8 + d.depth * 18 }}>
                      <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>{d.depth ? <FolderLock size={14} style={{ color: 'var(--or)' }} /> : <Folder size={14} />}
                        <b>{d.depth ? d.name : `${d.lib} (hele bibliotheek)`}</b></span>
                      {d.depth > 1 && <div className="hint" style={{ margin: 0 }}>{d.rel}</div>}</td>
                    <td>{o.length > 2 || (o.length === 2 && aan) ? (
                      <select value={keuze(d)} onChange={(e) => setVia((v) => ({ ...v, [k]: e.target.value }))} style={{ width: 'auto', maxWidth: 280 }}>
                        {o.map((x) => <option key={x.v} value={x.v}>{x.l}</option>)}</select>)
                      : <small>{o[0].a ? uitleg(o[0].a) : 'direct op de map · mag bewerken'}</small>}</td>
                    <td>{isLid(d, upn) && <Chip k="g"><CheckCircle2 size={12} /> al toegang</Chip>}</td>
                  </tr>);
              })}</tbody>
            </table>
            {!zicht.length && <div className="hint">Geen mappen met eigen machtigingen gevonden.</div>}
          </Card>
          <div className="card" style={{ position: 'sticky', bottom: 0, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', boxShadow: '0 -6px 20px rgba(0,63,107,.08)' }}>
            <Users size={18} style={{ color: 'var(--hd)' }} />
            <div style={{ flex: 1, minWidth: 220, fontSize: 13 }}>
              {!wie ? 'Kies eerst de medewerker.' : !gekozen.length ? 'Vink de mappen aan die de medewerker nodig heeft.' : (
                <>{wie.name} wordt lid van: <b>{[...plan.sp.values(), ...plan.entra.values()].map((g) => g.name).join(', ') || '-'}</b>
                  {plan.direct.length > 0 && <> en krijgt direct toegang tot <b>{plan.direct.map((x) => x.label).join(', ')}</b></>}
                  {plan.sp.size > nieuwSp.length && <span className="hint" style={{ margin: 0 }}> ({plan.sp.size - nieuwSp.length} groep(en) al lid)</span>}</>)}
            </div>
            <Btn v="p" icon={UserPlus} disabled={!wie || !gekozen.length} onClick={uitvoeren}>Toegang geven</Btn>
          </div>
        </div>
      </div>
    </>);
}

const Kop = ({ site, onTerug }) => (
  <div className="headrow">
    <div className="m"><h2 style={{ margin: 0 }}>Nieuwe medewerker: toegang per map</h2>
      <div className="hint" style={{ margin: 0 }}>Site {site.title} · vink de mappen aan; de app zet de medewerker in de groepen die toegang geven.</div></div>
    <Btn icon={ArrowLeft} onClick={onTerug}>Terug</Btn>
  </div>);
