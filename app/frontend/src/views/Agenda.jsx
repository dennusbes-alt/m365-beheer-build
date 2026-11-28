import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Eye, Share2, Trash2 } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, toast } from '../overlays.jsx';
import { getShared, getUsers, useApp } from '../store.jsx';
import { AllesVink, Btn, Card, Check, Chip, Loading, SearchBox, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';

export default function Agenda() {
  const { info } = useApp();
  const [items, setItems] = useState(null);
  const [q, setQ] = useState('');
  const [vink, setVink] = useState([]);
  const [huidig, setHuidig] = useState(null);
  const [rechten, setRechten] = useState(null);
  const [wieSoort, setWieSoort] = useState('u');
  const [wie, setWie] = useState('');
  const [rol, setRol] = useState('Reviewer');
  const [del, setDel] = useState(false);
  const [priv, setPriv] = useState(false);
  const [mut, setMut] = useState(false);
  const [melding, setMelding] = useState(false);
  const [wijzig, setWijzig] = useState({});   // aangepaste rechten in de lijst (nog niet opgeslagen)

  useEffect(() => {
    if (info.exo === false) return;
    Promise.all([getUsers(), getShared()]).then(([u, s]) => setItems([
      ...u.filter((x) => !x.guest).map((x) => ({ v: x.upn, l: x.name, s: x.upn, k: 'u' })),
      ...s.map((x) => ({ v: x.mail, l: x.name, s: x.mail, k: 's' })),
    ])).catch(() => setItems([]));
  }, [info.exo]);
  const shown = useFilter(items || [], q, (i) => [i.l, i.s]);
  const mensen = useMemo(() => (items || []).map((i) => [`${i.l} (${i.v})`, i.v]), [items]);

  if (info.exo === false) return <><h2>Agendarechten</h2><Msg kind="err">Exchange Online is niet verbonden bij deze klant. Agendarechten zijn niet beschikbaar.</Msg></>;
  if (!items) return <Loading text="Agenda's ophalen..." />;

  const laad = async (m) => {
    setHuidig(m); setRechten(null); setWijzig({});
    const d = await act('cal.get', { mailbox: m }, { msg: 'Rechten ophalen...' });
    setRechten(d ? d.rights : []);
  };
  const rolLabel = (info.roles.find((r) => r.key === rol) || {}).label || rol;
  const toewijzen = async () => {
    if (!vink.length) return toast("Vink eerst een of meer agenda's aan.", 'e');
    if (mut && vink.length < 2) return toast("Vink minimaal twee agenda's aan voor onderlinge rechten.", 'e');
    let w = wieSoort;
    if (!mut && wieSoort === 'u') {
      const x = mensen.find((p) => p[0] === wie);
      w = x ? x[1] : wie.trim();
      if (!w) return toast('Kies of typ een gebruiker.', 'e');
    }
    const t = mut ? `Onderling tussen ${vink.length} agenda's` : `${w === 'Default' ? 'Standaard (iedereen)' : w === 'Anonymous' ? 'Anoniem' : w} op ${vink.length} agenda('s)`;
    if (!await ask(`Recht '${rolLabel}' toewijzen?\n\n${t}`, 'Toewijzen')) return;
    await act('cal.set', { targets: vink, who: w, role: rol, delegate: del, priv, mutual: mut, notify: melding }, { msg: 'Rechten instellen...' });
    if (huidig) laad(huidig);
  };
  const isEditor = rol === 'Editor';

  return (
    <>
      <h2>Agendarechten</h2>
      <p className="sub">Klik op een agenda om de huidige rechten te zien. Vink agenda's aan om rechten toe te wijzen.</p>
      <div className="cols">
        <Card title="Agenda's" icon={CalendarDays} right={vink.length ? <Btn s onClick={() => setVink([])}>{vink.length} aangevinkt · wissen</Btn> : null}>
          <SearchBox value={q} onChange={setQ} placeholder="Zoek persoon of gedeeld postvak..." />
          <AllesVink ids={shown.slice(0, MAX_RIJEN).map((i) => i.v)} value={vink} onChange={setVink} label={q ? 'Alle gevonden selecteren' : 'Alles selecteren'} />
          <div className="list" style={{ maxHeight: 'calc(100vh - 360px)' }}>
            {shown.slice(0, MAX_RIJEN).map((i) => (
              <div key={i.v} className={'li' + (huidig === i.v ? ' on' : '')}>
                <input type="checkbox" checked={vink.includes(i.v)} onChange={(e) => setVink((x) => (e.target.checked ? [...x, i.v] : x.filter((y) => y !== i.v)))} />
                <span className="m" onClick={() => laad(i.v)}><b>{i.l} {i.k === 's' && <Chip k="mu">gedeeld</Chip>}</b><small>{i.s}</small></span>
                <Btn s icon={Eye} onClick={() => laad(i.v)} title="Rechten bekijken" />
              </div>
            ))}
            <Meer totaal={shown.length} />
          </div>
        </Card>
        <div>
          <Card title={huidig ? `Huidige rechten op ${huidig}` : 'Huidige rechten'} icon={Eye}>
            {!huidig ? <div className="hint">Kies links een agenda.</div> : !rechten ? <Loading /> : (
              <table>
                <thead><tr><th>Wie</th><th>Recht</th><th title="SharingPermissionFlags Delegate (alleen bij Bewerker)">Gemachtigde</th>
                  <th title="SharingPermissionFlags CanViewPrivateItems">Privé-items</th><th title="SendNotificationToUser">Melding</th><th /></tr></thead>
                <tbody>
                  {rechten.map((r) => {
                    const id = r.key + r.name;
                    const w = wijzig[id];
                    const v = w || { role: r.role, delegate: r.delegate, priv: r.priv, notify: false };
                    const zet = (k, val) => setWijzig((o) => {
                      const n = { ...v, [k]: val };
                      if (n.role !== 'Editor') { n.delegate = false; n.priv = false; }
                      if (!n.delegate) n.priv = false;
                      return { ...o, [id]: n };
                    });
                    const anders = w && (w.role !== r.role || w.delegate !== r.delegate || w.priv !== r.priv);
                    const bewaar = async () => {
                      if (await act('cal.set', { targets: [huidig], who: r.special ? r.name : r.key, role: v.role, delegate: v.delegate, priv: v.priv, notify: v.notify },
                        { msg: `Rechten van ${r.name} opslaan...` })) laad(huidig);
                    };
                    const kanMelding = !r.special && ['AvailabilityOnly', 'LimitedDetails', 'Reviewer', 'Author', 'Editor'].includes(v.role);
                    return (
                      <tr key={id}>
                        <td>{r.name}{r.key !== r.name && <div className="hint" style={{ margin: 0 }}>{r.key}</div>}</td>
                        <td><select value={v.role} onChange={(e) => zet('role', e.target.value)}>
                          {!info.roles.some((x) => x.key === v.role) && <option value={v.role}>{v.role}</option>}
                          {info.roles.map((x) => <option key={x.key} value={x.key}>{x.label.split(' - ')[0]}</option>)}</select></td>
                        <td><input type="checkbox" checked={v.delegate} disabled={v.role !== 'Editor' || r.special} onChange={(e) => zet('delegate', e.target.checked)} /></td>
                        <td><input type="checkbox" checked={v.priv} disabled={!v.delegate} onChange={(e) => zet('priv', e.target.checked)} /></td>
                        <td><input type="checkbox" checked={v.notify} disabled={!anders || !kanMelding} onChange={(e) => zet('notify', e.target.checked)} title="Bij opslaan een e-mail naar de gebruiker sturen" /></td>
                        <td className="r" style={{ whiteSpace: 'nowrap' }}>
                          {anders ? <><Btn s v="p" onClick={bewaar}>Opslaan</Btn> <Btn s onClick={() => setWijzig((o) => { const n = { ...o }; delete n[id]; return n; })}>Annuleren</Btn></>
                            : !r.special && <Btn s v="dl" icon={Trash2} onClick={async () => {
                              if (await ask(`Rechten van ${r.name} op ${huidig} verwijderen?`, 'Verwijderen', true) && await act('cal.remove', { mailbox: huidig, users: [r.key] })) laad(huidig);
                            }} title="Verwijderen" />}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Card>
          <Card title={`Rechten toewijzen aan aangevinkte agenda's (${vink.length})`} icon={Share2}>
            <Check checked={mut} onChange={setMut}>Onderling: alle aangevinkte agenda's krijgen dit recht op elkaars agenda</Check>
            {!mut && (
              <>
                <div className="row" style={{ marginBottom: 6 }}>
                  {[['u', 'Een gebruiker'], ['Default', 'Standaard (iedereen)'], ['Anonymous', 'Anoniem']].map(([k, l]) => (
                    <label key={k} className="chk n"><input type="radio" checked={wieSoort === k} onChange={() => setWieSoort(k)} />{l}</label>
                  ))}
                </div>
                {wieSoort === 'u' && (
                  <>
                    <input type="text" list="ag_dl" value={wie} onChange={(e) => setWie(e.target.value)} placeholder="Typ een naam..." />
                    <datalist id="ag_dl">{mensen.map((p) => <option key={p[1]} value={p[0]} />)}</datalist>
                  </>
                )}
              </>
            )}
            <label className="f">Recht</label>
            <select value={rol} onChange={(e) => { setRol(e.target.value); if (e.target.value !== 'Editor') { setDel(false); setPriv(false); } }}>
              {info.roles.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
            </select>
            <Check checked={del} disabled={!isEditor} onChange={(v) => { setDel(v); if (!v) setPriv(false); }}>Gemachtigde (Delegate), alleen bij Bewerker: ontvangt ook vergaderverzoeken</Check>
            <Check checked={priv} disabled={!isEditor || !del} onChange={setPriv} className="ind">Privé-afspraken kunnen zien (CanViewPrivateItems)</Check>
            <Check checked={melding} disabled={mut ? false : wieSoort !== 'u'} onChange={setMelding}>Melding naar de gebruiker sturen (SendNotificationToUser)
              <div className="hint" style={{ margin: 0 }}>De gebruiker krijgt een e-mail dat de agenda met hem of haar gedeeld is.</div></Check>
            <Btn v="p" icon={Share2} onClick={toewijzen} disabled={!vink.length}>Rechten toewijzen</Btn>
          </Card>
        </div>
      </div>
    </>
  );
}
