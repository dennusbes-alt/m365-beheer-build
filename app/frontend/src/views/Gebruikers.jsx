import { useEffect, useMemo, useState } from 'react';
import { startTab } from '../store.jsx';
import { AtSign, Ban, Cloud, ExternalLink, Fingerprint, IdCard, KeyRound, LockKeyhole, LogOut, Mailbox, Plus, RefreshCw, Save, Trash2, Unlock, UserPlus, Users, X } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, askType, openModal, toast } from '../overlays.jsx';
import { toonKlus } from '../Klus.jsx';
import { clearCache, doorgeven, getShared, getSkus, getUsers, useApp, useVers } from '../store.jsx';
import { AllesVink, Avatar, Btn, Card, Check, Chip, Field, Loading, Picker, SearchBox, Tabs, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';

export const freeTxt = (s) => (s.kind === 'gratis' && s.total >= 1000 ? <Chip>geen limiet</Chip>
  : s.free < 0 ? <><b style={{ color: 'var(--rd)' }}>{s.free}</b> <Chip k="r">tekort</Chip></>
    : s.free === 0 ? <><b style={{ color: 'var(--or)' }}>0</b> <Chip k="o">op</Chip></>
      : <b style={{ color: 'var(--gr)' }}>{s.free}</b>);

export const typeChip = (t) => <Chip k={t === 'Dynamisch' || t === 'Overig' ? 'o' : ''}>{t}</Chip>;

export default function Gebruikers() {
  const [users, setUsers] = useState(null);
  // Vanuit de zoekbalk bovenin: direct de gevonden gebruiker openen
  const [start] = useState(() => { const z = doorgeven.zoek; if (z && z.soort === 'user') { delete doorgeven.zoek; return z; } return null; });
  const [q, setQ] = useState(start ? start.q : '');
  const [toon, setToon] = useState('alle');
  const [sel, setSel] = useState(start ? start.id : null);
  const laad = (fresh) => getUsers(fresh).then(setUsers).catch(() => setUsers([]));
  useVers('users', setUsers);
  useEffect(() => { getSkus().catch(() => {}); laad(false); }, []);
  const [vink, setVink] = useState([]);
  const gefilterd = useFilter(users || [], q, (u) => [u.name, u.upn, u.title, u.dept]);
  const lijst = gefilterd.filter((u) => toon === 'alle' || (toon === 'gast' ? u.guest : toon === 'blok' ? !u.on : !u.lic.length && !u.guest));
  const zichtbaar = lijst.slice(0, MAX_RIJEN);
  const alles = zichtbaar.length > 0 && zichtbaar.every((u) => vink.includes(u.id));
  const naBulk = () => { setVink([]); clearCache('users', 'skus'); setUsers(null); laad(true); };

  return (
    <>
      <h2>Gebruikers beheren</h2>
      <p className="sub">Kies een gebruiker om gegevens, aliassen, groepen, licenties, OneDrive, gedeelde postvakken en MFA aan te passen. Vink gebruikers aan voor acties op meerdere tegelijk.</p>
      {vink.length > 0 && <BulkBalk ids={vink} users={users || []} onKlaar={naBulk} onLeeg={() => setVink([])} />}
      <div className="cols">
        <div className="sticky">
          <SearchBox value={q} onChange={setQ} placeholder="Zoek op naam, e-mailadres, functie..." autoFocus />
          <div className="filters" style={{ margin: '8px 0 0' }}>
            {[['alle', 'Alle'], ['blok', 'Geblokkeerd'], ['zonder', 'Zonder licentie'], ['gast', 'Gasten']].map(([k, l]) => (
              <button key={k} className={toon === k ? 'on' : ''} onClick={() => setToon(k)}>{l}</button>
            ))}
            <button style={{ marginLeft: 'auto' }} title="Lijst opnieuw ophalen bij Microsoft" onClick={() => { setUsers(null); laad(true); }}><RefreshCw size={13} />Vernieuwen</button>
          </div>
          <div className="list" style={{ maxHeight: 'calc(100vh - 360px)' }}>
            {users && zichtbaar.length > 0 && (
              <label className="li" style={{ background: 'var(--bg)', fontSize: 12.5, color: 'var(--mu)' }}>
                <input type="checkbox" checked={alles} onChange={(e) => setVink(e.target.checked ? [...new Set([...vink, ...zichtbaar.map((u) => u.id)])] : vink.filter((x) => !zichtbaar.some((u) => u.id === x)))} />
                <span className="m">Alles in deze lijst selecteren ({zichtbaar.length})</span>
              </label>
            )}
            {!users ? <Loading /> : zichtbaar.map((u) => (
              <div key={u.id} className={'li ' + (u.id === sel ? 'on ' : '') + (u.on ? '' : 'grey')} onClick={() => setSel(u.id)}>
                <input type="checkbox" checked={vink.includes(u.id)} onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setVink((v) => (e.target.checked ? [...v, u.id] : v.filter((x) => x !== u.id)))} />
                <Avatar name={u.name} size={32} />
                <span className="m"><b>{u.name}</b><small>{u.upn}</small></span>
                {!u.on && <Chip k="r">geblokkeerd</Chip>}
                {u.guest && <Chip k="mu">gast</Chip>}
              </div>
            ))}
            {users && !lijst.length && <div className="li empty">Niemand gevonden</div>}
            <Meer totaal={users ? lijst.length : 0} />
          </div>
          <div className="count">{users ? `${lijst.length} van ${users.length} gebruikers` : ''}</div>
        </div>
        <div>{sel ? <Detail key={sel} id={sel} onChanged={() => laad(true)} /> : <div className="card muted"><Users size={18} />Kies links een gebruiker.</div>}</div>
      </div>
    </>
  );
}

function Detail({ id, onChanged }) {
  const { info } = useApp();
  const [u, setU] = useState(null);
  const [tab, setTab] = useState(() => startTab('users-detail', 'gegevens'));
  const open = async () => {
    const d = await act('user.get', { id }, { msg: 'Gebruiker ophalen...' });
    if (d) {
      setU(d);
      // Postvakrechten alvast op de achtergrond ophalen: het tabblad staat dan direct klaar
      if (info.exo !== false) setTimeout(() => api('group.members', { type: 'Gedeeld postvak', mail: d.mail || d.upn }, { quiet: true }).catch(() => {}), 400);
    }
  };
  useEffect(() => { open(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!u) return <Loading />;
  const herlaad = async (lijstOok) => { await open(); if (lijstOok) { clearCache('users'); onChanged(); } };

  const revoke = async () => { if (await ask(`Alle sessies van ${u.name} afmelden? De gebruiker moet overal opnieuw inloggen.`, 'Afmelden', true)) act('user.revoke', { id }); };
  const blok = async () => {
    if (u.on && !await ask(`Aanmelden blokkeren voor ${u.name} en alle sessies intrekken?`, 'Blokkeren', true)) return;
    if (await act('user.block', { id, blocked: u.on })) herlaad(true);
  };
  const T = { gegevens: Gegevens, alias: Aliassen, groepen: Groepen, lic: Lic, onedrive: OneDrive, shared: Gedeeld, rechten: PostvakRechten, mfa: Mfa }[tab];
  return (
    <>
      <div className="card">
        <div className="headrow">
          <Avatar name={u.name} size={48} />
          <div className="m">
            <h3>{u.name}</h3>
            <div className="hint" style={{ margin: 0 }}>{u.upn} {u.on ? <Chip k="g">actief</Chip> : <Chip k="r">geblokkeerd</Chip>}{u.title && <> · {u.title}</>}</div>
          </div>
          <div className="btns">
            <Btn icon={LogOut} onClick={revoke}>Sessies afmelden</Btn>
            <Btn v={u.on ? 'dl' : 'p'} icon={u.on ? Ban : Unlock} onClick={blok}>{u.on ? 'Aanmelden blokkeren' : 'Aanmelden toestaan'}</Btn>
          </div>
        </div>
      </div>
      <div className="card">
        <Tabs value={tab} onChange={setTab} tabs={[['gegevens', 'Gegevens', IdCard], ['alias', 'Aliassen', AtSign], ['groepen', 'Groepen', Users],
          ['lic', 'Licenties', KeyRound], ['onedrive', 'OneDrive', Cloud], ['shared', 'Gedeelde postvakken', Mailbox], ['rechten', 'Postvakrechten', LockKeyhole], ['mfa', 'Beveiliging (MFA)', Fingerprint]]} />
        <T u={u} info={info} herlaad={herlaad} />
      </div>
    </>
  );
}

function Gegevens({ u, info, herlaad }) {
  const [lp0, dom0] = u.upn.split('@');
  const [f, setF] = useState({ name: u.name, given: u.given, sur: u.sur, title: u.title, dept: u.dept, office: u.office, mobile: u.mobile, lp: lp0, dom: dom0 });
  const s = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  const doms = info.domains.some((d) => d.id === dom0) ? info.domains : [...info.domains, { id: dom0 }];
  const opslaan = async () => {
    if (!f.name.trim()) return toast('Weergavenaam mag niet leeg zijn.', 'e');
    const b = { id: u.id, name: f.name, given: f.given, sur: f.sur, title: f.title, dept: f.dept, office: f.office, mobile: f.mobile };
    const nu = f.lp.trim() + '@' + f.dom;
    if (nu.toLowerCase() !== u.upn.toLowerCase()) {
      if (!await ask(`Inlognaam wijzigen van ${u.upn} naar ${nu}?\n\nDe gebruiker moet daarna met het nieuwe adres inloggen.`)) return;
      b.upn = nu;
    }
    if (await act('user.update', b, { msg: 'Opslaan...' })) herlaad(true);
  };
  return (
    <>
      <div className="row"><Field label="Weergavenaam" value={f.name} onChange={s('name')} /><Field label="Voornaam" value={f.given} onChange={s('given')} /><Field label="Achternaam" value={f.sur} onChange={s('sur')} /></div>
      <label className="f">Inlognaam (e-mailadres)</label>
      <div className="row"><input type="text" value={f.lp} onChange={(e) => s('lp')(e.target.value)} />
        <select value={f.dom} onChange={(e) => s('dom')(e.target.value)}>{doms.map((d) => <option key={d.id}>{d.id}</option>)}</select></div>
      <div className="row"><Field label="Functie" value={f.title} onChange={s('title')} /><Field label="Afdeling" value={f.dept} onChange={s('dept')} /></div>
      <div className="row"><Field label="Kantoorlocatie" value={f.office} onChange={s('office')} /><Field label="Mobiel" value={f.mobile} onChange={s('mobile')} /></div>
      <div className="hint">Verandert de inlognaam, dan moet de gebruiker met het nieuwe adres inloggen. Het oude adres wordt in Exchange vaak als alias bewaard.</div>
      <div style={{ marginTop: 14 }}><Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn></div>
    </>
  );
}

function Aliassen({ u, info, herlaad }) {
  const [lp, setLp] = useState('');
  const [dom, setDom] = useState(info.defaultDomain);
  const run = async (action, alias) => { if (await act('user.alias', { upn: u.upn, action, alias })) herlaad(); };
  return (
    <>
      {info.exo === false && <Msg kind="warn">Exchange Online is niet verbonden: aliassen aanpassen werkt niet.</Msg>}
      <table>
        <thead><tr><th>E-mailadres</th><th /></tr></thead>
        <tbody>
          {u.aliases.map((a) => (
            <tr key={a.addr}>
              <td>{a.addr} {a.primary && <Chip k="g">primair</Chip>}</td>
              <td className="r">{!a.primary && <div className="btns" style={{ justifyContent: 'flex-end' }}>
                <Btn s onClick={() => run('primary', a.addr)}>Primair maken</Btn>
                <Btn s v="dl" icon={Trash2} onClick={async () => { if (await ask(`Alias ${a.addr} verwijderen?`, 'Verwijderen', true)) run('remove', a.addr); }}>Verwijderen</Btn>
              </div>}</td>
            </tr>
          ))}
          {!u.aliases.length && <tr><td colSpan={2} className="hint">Geen adressen (geen mailbox?)</td></tr>}
        </tbody>
      </table>
      <label className="f">Alias toevoegen</label>
      <div className="row">
        <input type="text" value={lp} placeholder="naam" onChange={(e) => setLp(e.target.value)} />
        <select value={dom} onChange={(e) => setDom(e.target.value)}>{info.domains.map((d) => <option key={d.id}>{d.id}</option>)}</select>
        <div className="n"><Btn v="p" icon={Plus} disabled={!lp.trim()} onClick={() => run('add', lp.trim() + '@' + dom)}>Toevoegen</Btn></div>
      </div>
    </>
  );
}

function Groepen({ u }) {
  const [d, setD] = useState(null);
  const laad = async () => { const r = await act('user.groups', { id: u.id }, { msg: 'Groepen ophalen...' }); setD(r || { groups: [], all: [] }); };
  useEffect(() => { laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <Loading />;
  const mijn = new Set(d.groups.map((g) => g.id));
  const rest = d.all.filter((g) => g.edit && !mijn.has(g.id));
  const run = async (action, groupId) => { if (await act('user.group', { userId: u.id, groupId, action }, { msg: 'Bezig...' })) laad(); };
  return (
    <div className="cols2">
      <div>
        <table>
          <thead><tr><th>Lid van</th><th>Type</th><th /></tr></thead>
          <tbody>
            {d.groups.map((g) => (
              <tr key={g.id}>
                <td>{g.name}<div className="hint" style={{ margin: 0 }}>{g.mail}</div></td>
                <td>{typeChip(g.type)}{g.sync && <> <Chip k="o">on-premises</Chip></>}</td>
                <td className="r">{g.edit && <Btn s v="dl" icon={Trash2} onClick={async () => { if (await ask(`${u.name} uit ${g.name} verwijderen?`, 'Verwijderen', true)) run('remove', g.id); }}>Verwijderen</Btn>}</td>
              </tr>
            ))}
            {!d.groups.length && <tr><td colSpan={3} className="hint">Lid van geen enkele groep.</td></tr>}
          </tbody>
        </table>
      </div>
      <div>
        <label className="f" style={{ marginTop: 0 }}>Toevoegen aan groep (klik om toe te voegen)</label>
        <Picker items={rest.map((g) => ({ v: g.id, l: g.name, s: `${g.type}${g.mail ? ' · ' + g.mail : ''}` }))} placeholder="Zoek groep..."
          onPick={async (i) => { if (await ask(`${u.name} toevoegen aan ${i.l}?`, 'Toevoegen')) run('add', i.v); }} />
      </div>
    </div>
  );
}

function Lic({ u, herlaad }) {
  const [skus, setSkus] = useState(null);
  const heeft = useMemo(() => new Map(u.licenses.map((l) => [l.sku, l])), [u]);
  const [aan, setAan] = useState(() => new Set(u.licenses.map((l) => l.sku)));
  useEffect(() => { getSkus().then(setSkus).catch(() => setSkus([])); }, []);
  if (!skus) return <Loading />;
  const rij = (s) => {
    const h = heeft.get(s.id);
    const via = h && !h.direct;
    return (
      <tr key={s.id}>
        <td style={{ width: 34 }}><input type="checkbox" checked={aan.has(s.id)} disabled={via || (!h && s.free <= 0 && !aan.has(s.id))}
          onChange={(e) => setAan((x) => { const n = new Set(x); e.target.checked ? n.add(s.id) : n.delete(s.id); return n; })} /></td>
        <td className="sk"><b>{s.name}</b> {via && <Chip k="o">via groep</Chip>}<small>{s.desc}</small></td>
        <td>{freeTxt(s)}</td>
      </tr>
    );
  };
  const betaald = skus.filter((s) => s.kind !== 'gratis');
  const gratis = skus.filter((s) => s.kind === 'gratis');
  const opslaan = async () => {
    const add = [...aan].filter((x) => !heeft.has(x));
    const rem = [...heeft.keys()].filter((x) => !aan.has(x) && heeft.get(x).direct);
    if (!add.length && !rem.length) return toast('Geen wijzigingen.');
    if (await act('user.license', { id: u.id, add, remove: rem }, { msg: 'Licenties bijwerken...' })) { clearCache('skus'); herlaad(true); }
  };
  return (
    <>
      <table>
        <thead><tr><th /><th>Licentie</th><th>Nog beschikbaar</th></tr></thead>
        <tbody>
          <tr className="sec"><td colSpan={3}>Betaalde licenties</td></tr>
          {betaald.length ? betaald.map(rij) : <tr><td colSpan={3} className="hint">Geen</td></tr>}
          {gratis.length > 0 && <tr className="sec"><td colSpan={3}>Gratis, proefversies en technische licenties</td></tr>}
          {gratis.map(rij)}
        </tbody>
      </table>
      <div className="hint">Een licentie die "via groep" is toegewezen, wijzig je alleen via die groep.{u.loc ? '' : ' De gebruikslocatie ontbreekt en wordt automatisch op NL gezet.'}</div>
      <div style={{ marginTop: 14 }}><Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn></div>
    </>
  );
}

function Gedeeld({ u, info }) {
  const [all, setAll] = useState(null);
  const [res, setRes] = useState({});
  const [klaar, setKlaar] = useState(0);
  const [keuze, setKeuze] = useState('');
  const [r, setR] = useState({ full: true, send: true, auto: true });
  useEffect(() => {
    if (info.exo === false) return undefined;
    let stop = false;
    (async () => {
      let lijst;
      try { lijst = await getShared(); } catch { lijst = []; }
      if (stop) return;
      setAll(lijst);
      // Eén aanvraag: de backend houdt de rechten van alle gedeelde postvakken van deze klant bij,
      // dus na de eerste keer is dit voor elke gebruiker direct klaar.
      const d = await act('user.sharedscan', { upn: u.upn }, { nobusy: true });
      if (stop) return;
      if (d) setRes(Object.fromEntries(d.results.map((y) => [y.mail, y])));
      setKlaar(lijst.length);
    })();
    return () => { stop = true; };
  }, [u.upn, info.exo]);
  if (info.exo === false) return <Msg kind="warn">Exchange Online is niet verbonden.</Msg>;
  if (!all) return <Loading text="Gedeelde postvakken ophalen..." />;
  const scan = async (mail) => {
    const d = await act('user.sharedscan', { upn: u.upn, mailboxes: [mail] }, { nobusy: true });
    if (d) setRes((x) => ({ ...x, [mail]: d.results[0] }));
  };
  const rows = all.filter((s) => res[s.mail] && (res[s.mail].full || res[s.mail].send));
  return (
    <>
      {klaar < all.length
        ? <><div className="hint">Rechten van alle {all.length} gedeelde postvakken ophalen (eenmalig per klant, daarna direct)...</div>
          <div className="bar indet" style={{ margin: '6px 0 12px' }}><i /></div></>
        : <div className="hint" style={{ marginBottom: 10 }}>{all.length} gedeelde postvakken gecontroleerd.</div>}
      <table>
        <thead><tr><th>Postvak</th><th>Rechten</th><th /></tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.mail}>
              <td>{s.name}<div className="hint" style={{ margin: 0 }}>{s.mail}</div></td>
              <td>{res[s.mail].full && <Chip>Volledige toegang</Chip>} {res[s.mail].send && <Chip>Verzenden als</Chip>}</td>
              <td className="r"><Btn s v="dl" icon={Trash2} onClick={async () => {
                if (!await ask(`Rechten van ${u.name} op ${s.mail} verwijderen?`, 'Verwijderen', true)) return;
                if (await act('user.sharedset', { action: 'remove', upn: u.upn, mailbox: s.mail, full: res[s.mail].full, send: res[s.mail].send })) scan(s.mail);
              }}>Verwijderen</Btn></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={3} className="hint">{klaar >= all.length ? 'Geen toegang tot gedeelde postvakken.' : 'Nog niets gevonden...'}</td></tr>}
        </tbody>
      </table>
      <label className="f">Toegang geven tot</label>
      <select value={keuze} onChange={(e) => setKeuze(e.target.value)}>
        <option value="">Kies een gedeeld postvak...</option>
        {all.map((s) => <option key={s.mail} value={s.mail}>{s.name} ({s.mail})</option>)}
      </select>
      <div className="row" style={{ marginTop: 6 }}>
        <Check checked={r.full} onChange={(v) => setR({ ...r, full: v })}>Volledige toegang</Check>
        <Check checked={r.send} onChange={(v) => setR({ ...r, send: v })}>Verzenden als</Check>
        <Check checked={r.auto} onChange={(v) => setR({ ...r, auto: v })}>Automapping in Outlook</Check>
      </div>
      <Btn v="p" icon={Plus} disabled={!keuze || !(r.full || r.send)} onClick={async () => {
        if (await act('user.sharedset', { action: 'add', upn: u.upn, mailbox: keuze, ...r }, { msg: 'Rechten instellen...' })) scan(keuze);
      }}>Toevoegen</Btn>
    </>
  );
}

function Mfa({ u }) {
  const [d, setD] = useState(null);
  const [rev, setRev] = useState(true);
  const laad = async () => { const r = await act('user.mfa', { id: u.id }, { msg: 'MFA-methoden ophalen...' }); setD(r || { methods: [] }); };
  useEffect(() => { laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <Loading />;
  const run = async (ids, t) => {
    if (!await ask(t, 'Resetten', true)) return;
    if (await act('user.mfareset', { id: u.id, ids, revoke: rev }, { msg: 'MFA resetten...' })) laad();
  };
  return (
    <>
      <p style={{ marginTop: 0 }}>Zo beveiligt {u.name} zich nu extra (MFA). Na een reset moet de gebruiker bij de volgende keer inloggen opnieuw MFA instellen, bijvoorbeeld bij een nieuwe telefoon of een verloren toestel.</p>
      <table>
        <thead><tr><th>Geregistreerde methode</th><th /></tr></thead>
        <tbody>
          {d.methods.map((m) => (
            <tr key={m.id}><td>{m.name}</td><td className="r">{m.supported && <Btn s v="dl" icon={Trash2} onClick={() => run([m.id], `Deze methode verwijderen?\n\n${m.name}`)}>Verwijderen</Btn>}</td></tr>
          ))}
          {!d.methods.length && <tr><td colSpan={2} className="hint">Geen MFA-methoden geregistreerd.</td></tr>}
        </tbody>
      </table>
      <Check checked={rev} onChange={setRev} className="" >Ook alle aanmeldsessies intrekken (aanbevolen: de gebruiker moet dan opnieuw inloggen)</Check>
      <Btn v="d" icon={Fingerprint} disabled={!d.methods.length} onClick={() => run(null, `Alle MFA-methoden van ${u.name} verwijderen?\n\nDe gebruiker moet bij de volgende aanmelding MFA opnieuw instellen.`)}>MFA volledig resetten</Btn>
      <div className="hint">Hiervoor heb je minimaal de rol Authentication Administrator nodig (voor beheerders: Privileged Authentication Administrator).</div>
    </>
  );
}

// ---------------- Acties op meerdere gebruikers ----------------
function LicentieKeuze({ close, n }) {
  const [skus, setSkus] = useState(null);
  const [add, setAdd] = useState([]);
  const [rem, setRem] = useState([]);
  useEffect(() => { getSkus().then(setSkus).catch(() => setSkus([])); }, []);
  const zet = (lijst, set, id, aan) => set(aan ? [...lijst, id] : lijst.filter((x) => x !== id));
  return (
    <>
      <h3>Licenties voor {n} gebruiker(s)</h3>
      {!skus ? <Loading /> : (
        <table>
          <thead><tr><th>Licentie</th><th>Nog vrij</th><th className="r">Toevoegen</th><th className="r">Verwijderen</th></tr></thead>
          <tbody>{skus.map((s) => (
            <tr key={s.id}>
              <td className="sk"><b>{s.name}</b><small>{s.desc}</small></td><td>{freeTxt(s)}</td>
              <td className="r"><input type="checkbox" checked={add.includes(s.id)} onChange={(e) => { zet(add, setAdd, s.id, e.target.checked); if (e.target.checked) setRem(rem.filter((x) => x !== s.id)); }} /></td>
              <td className="r"><input type="checkbox" checked={rem.includes(s.id)} onChange={(e) => { zet(rem, setRem, s.id, e.target.checked); if (e.target.checked) setAdd(add.filter((x) => x !== s.id)); }} /></td>
            </tr>))}</tbody>
        </table>
      )}
      <div className="hint">Gebruikers zonder gebruikslocatie krijgen automatisch NL. Licenties via een groep worden niet aangepast.</div>
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" disabled={!add.length && !rem.length} onClick={() => close({ add, remove: rem })}>Toepassen</Btn></div>
    </>
  );
}

function WachtwoordKeuze({ close, n }) {
  const [vast, setVast] = useState('');
  const [eigen, setEigen] = useState(false);
  const [force, setForce] = useState(true);
  const [revoke, setRevoke] = useState(true);
  return (
    <>
      <h3>Nieuw wachtwoord voor {n} gebruiker(s)</h3>
      <Check checked={!eigen} onChange={(v) => setEigen(!v)}>Voor iedereen een eigen willekeurig wachtwoord (aanbevolen)</Check>
      <Check checked={eigen} onChange={setEigen}>Hetzelfde wachtwoord voor iedereen</Check>
      {eigen && <input type="text" value={vast} onChange={(e) => setVast(e.target.value)} placeholder="Minimaal 8 tekens" style={{ marginLeft: 26, width: 'calc(100% - 26px)' }} />}
      <Check checked={force} onChange={setForce}>Wachtwoord moet bij de volgende aanmelding gewijzigd worden</Check>
      <Check checked={revoke} onChange={setRevoke}>Alle sessies afmelden</Check>
      <div className="hint">Na afloop kun je de nieuwe wachtwoorden als CSV exporteren.</div>
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn>
        <Btn v="p" disabled={eigen && vast.length < 8} onClick={() => close({ password: eigen ? vast : '', force, revoke })}>Wachtwoorden instellen</Btn></div>
    </>
  );
}

function BulkBalk({ ids, users, onKlaar, onLeeg }) {
  const n = ids.length;
  const namen = users.filter((u) => ids.includes(u.id)).map((u) => u.name);
  const klaar = (k) => { if (k) onKlaar(); };
  const verwijder = async () => {
    if (!await askType(`${n} gebruiker(s) verwijderen:\n\n${namen.slice(0, 15).join('\n')}${n > 15 ? `\n... en ${n - 15} meer` : ''}\n\nZe staan daarna 30 dagen in de prullenbak van Entra (Verwijderde gebruikers) en zijn daar terug te zetten.`, 'VERWIJDEREN')) return;
    klaar(await toonKlus(await act('users.bulkdelete', { ids }, { msg: 'Starten...' })));
  };
  const licenties = async () => {
    const k = await openModal((close) => <LicentieKeuze close={close} n={n} />, { wide: true });
    if (k) klaar(await toonKlus(await act('users.bulklicense', { ids, ...k }, { msg: 'Starten...' }), { kolommen: [['added', 'Toegevoegd'], ['removed', 'Verwijderd']] }));
  };
  const wachtwoorden = async () => {
    const k = await openModal((close) => <WachtwoordKeuze close={close} n={n} />);
    if (k) klaar(await toonKlus(await act('users.bulkpassword', { ids, ...k }, { msg: 'Starten...' }), { kolommen: [['upn', 'Account'], ['password', 'Wachtwoord']], csv: 'nieuwe-wachtwoorden.csv' }));
  };
  const onedrive = async () => {
    if (!await ask(`OneDrive aanmaken voor ${n} gebruiker(s)? Bij gebruikers die al een OneDrive hebben gebeurt er niets.`, 'OneDrive aanmaken')) return;
    await toonKlus(await act('users.bulkonedrive', { ids }, { msg: 'Starten...' }), { kolommen: [['status', 'Status'], ['url', 'OneDrive'], ['gebruikt', 'Gebruikt']], csv: 'onedrive.csv' });
  };
  return (
    <div className="updbalk">
      <Users size={18} style={{ flex: 'none' }} />
      <div style={{ flex: 1 }}><b>{n} geselecteerd</b></div>
      <Btn s icon={KeyRound} onClick={licenties}>Licenties</Btn>
      <Btn s icon={Fingerprint} onClick={wachtwoorden}>Wachtwoorden</Btn>
      <Btn s icon={Cloud} onClick={onedrive}>OneDrive aanmaken</Btn>
      <Btn s v="dl" icon={Trash2} onClick={verwijder}>Verwijderen</Btn>
      <Btn s icon={X} onClick={onLeeg}>Selectie wissen</Btn>
    </div>
  );
}

// ---------------- OneDrive ----------------
function OneDrive({ u }) {
  const [d, setD] = useState(null);
  const [bezig, setBezig] = useState(false);
  const haal = async (provision) => {
    setBezig(true);
    const r = await act('user.onedrive', { id: u.id, provision });
    setBezig(false);
    if (r) setD(r);
  };
  const pct = d && d.totalGb ? Math.min(100, (d.usedGb / d.totalGb) * 100) : 0;
  return (
    <>
      <p style={{ marginTop: 0 }}>OneDrive wordt normaal pas aangemaakt als de gebruiker zich voor het eerst aanmeldt. Hier kun je dat vooraf doen,
        bijvoorbeeld na het aanmaken van nieuwe gebruikers, en zie je de opslag zoals in het beheercentrum.</p>
      {!d && <Btn v="p" icon={Cloud} disabled={bezig} onClick={() => haal(true)}>{bezig ? 'Bezig...' : 'OneDrive ophalen en zo nodig aanmaken'}</Btn>}
      {bezig && <Loading text="OneDrive ophalen of aanmaken (de eerste keer kan dit even duren)..." />}
      {d && !d.exists && (d.queued
        ? <Msg kind="ok">OneDrive wordt aangemaakt. Dat is meestal binnen enkele minuten klaar; klik daarna op Vernieuwen.</Msg>
        : <Msg kind="warn">Deze gebruiker heeft nog geen OneDrive.</Msg>)}
      {d && !d.exists && <div style={{ marginTop: 8 }}><Btn s icon={RefreshCw} onClick={() => haal(false)}>Vernieuwen</Btn></div>}
      {d && d.exists && (
        <>
          <div className="kv" style={{ marginBottom: 14 }}>
            <div><label>OneDrive-adres</label><div style={{ fontWeight: 400 }}><a href="#" onClick={(e) => { e.preventDefault(); act('open.url', { url: d.url }); }}>{d.url} <ExternalLink size={12} /></a></div></div>
            <div><label>Gebruikte opslag</label><div>{d.usedGb >= 1 ? `${d.usedGb} GB` : `${d.usedMb ?? 0} MB`} van {d.totalGb} GB</div></div>
            <div><label>Prullenbak</label><div>{d.deletedGb} GB</div></div>
            <div><label>Status</label><div>{{ normal: 'Normaal', nearing: 'Bijna vol', critical: 'Kritiek', exceeded: 'Vol' }[d.state] || d.state || '-'}</div></div>
          </div>
          <div className={'bar' + (pct > 90 ? ' over' : pct > 75 ? ' full' : '')}><i style={{ width: pct + '%' }} /></div>
          <div style={{ marginTop: 12 }}><Btn s icon={RefreshCw} onClick={() => haal(false)}>Vernieuwen</Btn></div>
        </>
      )}
    </>
  );
}


// Wie heeft rechten op het postvak van deze gebruiker (volledige toegang, verzenden als, verzenden namens, automapping)
function PostvakRechten({ u, info }) {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [users, setUsers] = useState([]);
  const [wijzig, setWijzig] = useState({});
  const [vink, setVink] = useState([]);
  const [r, setR] = useState({ full: true, send: false, behalf: false, auto: true });
  const mb = u.mail || u.upn;
  const laad = async (fresh) => {
    setWijzig({}); setVink([]); setFout('');
    try {
      const x = await api('group.members', { type: 'Gedeeld postvak', mail: mb, ...(fresh === true ? { fresh: true } : {}) }, { quiet: true });
      setD(x ? x.members.filter((m) => m.key.toLowerCase() !== mb.toLowerCase()) : []);
    } catch (e) { setFout(e.message || String(e)); setD([]); }
  };
  useEffect(() => { if (info.exo !== false) { laad(); getUsers().then(setUsers).catch(() => {}); } }, [mb]); // eslint-disable-line react-hooks/exhaustive-deps
  if (info.exo === false) return <Msg kind="err">Exchange Online is niet verbonden bij deze klant.</Msg>;
  if (!d) return <Loading text="Rechten op het postvak ophalen..." />;
  const al = new Set([mb.toLowerCase(), ...d.map((m) => m.key.toLowerCase())]);
  const toevoegen = async (i) => {
    if (!(r.full || r.send || r.behalf)) return toast('Vink minimaal een recht aan.', 'e');
    const rechten = [r.full && `volledige toegang${r.auto ? ' (met automapping)' : ' (zonder automapping)'}`, r.send && 'verzenden als', r.behalf && 'verzenden namens'].filter(Boolean).join(', ');
    if (!await ask(`${i.l} krijgt ${rechten} op het postvak van ${u.name}.\n\nMet volledige toegang kan ${i.l} alle mail, agenda en contactpersonen van ${u.name} lezen en wijzigen.`, 'Rechten geven')) return;
    if (await act('shared.member.set', { mail: mb, key: i.s, full: r.full, send: r.send, behalf: r.behalf, auto: r.full ? r.auto : null, was: {} }, { msg: 'Rechten geven...' })) laad();
  };
  const weg = async () => {
    const m = d.filter((x) => vink.includes(x.id));
    if (!await ask(`Alle rechten op het postvak van ${u.name} intrekken voor:\n\n${m.map((x) => x.name).join('\n')}`, 'Intrekken', true)) return;
    if (await act('group.remove', { type: 'Gedeeld postvak', mail: mb, members: m }, { msg: 'Intrekken...' })) laad();
  };
  return (
    <>
      <div className="hint" style={{ marginTop: 0 }}>Wie mag het postvak van {u.name} ({mb}) openen of namens {u.name} mailen. Handig bij afwezigheid, een assistent of overdracht bij uitdiensttreding.
        Agendarechten stel je in onder Samenwerken &gt; Agendarechten.</div>
      {fout && <Msg kind="warn">{/mailbox|couldn't be found|niet gevonden/i.test(fout) ? `${u.name} heeft geen postvak (geen licentie met Exchange).` : fout}</Msg>}
      {!fout && (
        <>
          <div className="headrow" style={{ margin: '6px 0' }}>
            <b>Wie heeft toegang ({d.length})</b>
            <span className="btns">{vink.length > 0 && <Btn s v="d" icon={Trash2} onClick={weg}>{vink.length} intrekken</Btn>}<Btn s icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn></span>
          </div>
          {!d.length ? <div className="hint">Niemand anders heeft rechten op dit postvak.</div> : (
            <table>
              <thead><tr><th style={{ width: 30 }}><AllesVink ids={d.map((m) => m.id)} value={vink} onChange={setVink} label="" style={{ margin: 0 }} /></th><th>Wie</th><th>Volledige toegang</th><th>Verzenden als</th><th>Verzenden namens</th><th>Automapping</th><th /></tr></thead>
              <tbody>{d.map((m) => {
                const w = wijzig[m.id];
                const v = w || { full: !!m.full, send: !!m.send, behalf: !!m.behalf, auto: '' };
                const zet = (k, val) => setWijzig((o) => ({ ...o, [m.id]: { ...v, [k]: val } }));
                const anders = w && (w.full !== !!m.full || w.send !== !!m.send || w.behalf !== !!m.behalf || (w.auto !== '' && w.full));
                const naam = (users.find((x) => x.upn.toLowerCase() === m.key.toLowerCase()) || {}).name;
                const bewaar = async () => {
                  if (!v.full && !v.send && !v.behalf) return toast('Laat minimaal een recht aan, of trek alles in met het vinkje links.', 'e');
                  if (await act('shared.member.set', { mail: mb, key: m.key, full: v.full, send: v.send, behalf: v.behalf, auto: v.auto === '' ? null : v.auto === 'aan',
                    was: { full: !!m.full, send: !!m.send, behalf: !!m.behalf } }, { msg: `Rechten van ${m.key} opslaan...` })) laad();
                };
                return (
                  <tr key={m.id}>
                    <td><input type="checkbox" checked={vink.includes(m.id)} onChange={(e) => setVink((x) => (e.target.checked ? [...x, m.id] : x.filter((y) => y !== m.id)))} /></td>
                    <td>{naam || m.name}{naam && <div className="hint" style={{ margin: 0 }}>{m.key}</div>}</td>
                    <td><input type="checkbox" checked={v.full} onChange={(e) => zet('full', e.target.checked)} /></td>
                    <td><input type="checkbox" checked={v.send} onChange={(e) => zet('send', e.target.checked)} /></td>
                    <td><input type="checkbox" checked={v.behalf} onChange={(e) => zet('behalf', e.target.checked)} /></td>
                    <td><select value={v.auto} disabled={!v.full} onChange={(e) => zet('auto', e.target.value)} title="Automapping is bij Microsoft niet uit te lezen. Kies aan of uit om het opnieuw in te stellen.">
                      <option value="">{m.full ? 'Ongewijzigd' : 'Aan (standaard)'}</option><option value="aan">Aan</option><option value="uit">Uit</option></select></td>
                    <td className="r">{anders && <><Btn s v="p" onClick={bewaar}>Opslaan</Btn> <Btn s onClick={() => setWijzig((o) => { const n = { ...o }; delete n[m.id]; return n; })}>Annuleren</Btn></>}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          )}
          <h4 style={{ margin: '18px 0 6px', display: 'flex', alignItems: 'center', gap: 6 }}><UserPlus size={16} />Toegang geven aan iemand anders</h4>
          <div className="row" style={{ marginBottom: 6 }}>
            <Check checked={r.full} onChange={(v) => setR({ ...r, full: v })}>Volledige toegang</Check>
            <Check checked={r.send} onChange={(v) => setR({ ...r, send: v })}>Verzenden als</Check>
            <Check checked={r.behalf} onChange={(v) => setR({ ...r, behalf: v })}>Verzenden namens</Check>
            <Check checked={r.auto} disabled={!r.full} onChange={(v) => setR({ ...r, auto: v })}>Automapping (postvak verschijnt vanzelf in Outlook)</Check>
          </div>
          <Picker placeholder="Zoek collega en klik om rechten te geven..." height={200}
            items={users.filter((x) => !x.guest && !al.has(x.upn.toLowerCase())).map((x) => ({ v: x.id, l: x.name, s: x.upn }))} onPick={toevoegen} />
        </>
      )}
    </>
  );
}
