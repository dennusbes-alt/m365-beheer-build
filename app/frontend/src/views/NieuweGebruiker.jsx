import { useEffect, useState } from 'react';
import { startTab } from '../store.jsx';
import { FolderLock, ClipboardPaste, Copy, KeyRound, Mailbox, Plus, RefreshCw, Trash2, UserPlus, Users, UsersRound, X } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, openModal, toast } from '../overlays.jsx';
import { toonKlus } from '../Klus.jsx';
import { clearCache, doorgeven, getShared, getSkus, getUsers, useApp } from '../store.jsx';
import { Btn, Card, Check, CheckList, Field, Loading, Picker, Tabs, genPw, normAlias } from '../ui.jsx';

const LEEG = { given: '', sur: '', name: '', alias: '', title: '', dept: '', office: '', mobile: '', loc: 'NL', force: true };
const aliasVan = (g, s) => [normAlias(g || ''), normAlias(s || '')].filter(Boolean).join('.');

// Gemeenschappelijke instellingen: licenties, groepen, gedeelde postvakken (ook gebruikt bij bulk)
function Instellingen({ data, info, skus, setSkus, groepen, setGroepen, shared, setShared, r, setR }) {
  const skuItems = data.skus.map((s) => ({ v: s.id, l: s.name, s: s.kind === 'gratis' && s.total >= 1000 ? 'geen limiet' : `${s.free} vrij` }));
  return (
    <>
      <Card title="Licenties" icon={KeyRound}>
        <CheckList items={skuItems} value={skus} onChange={setSkus} height={170} placeholder="Zoek licentie..." />
        <div className="hint">Zonder licentie is er geen mailbox, dus ook geen distributielijsten en gedeelde postvakken.</div>
      </Card>
      <Card title="Groepen" icon={Users}>
        <CheckList items={data.groepen.map((g) => ({ v: g.id, l: g.name, s: g.type + (g.mail ? ' · ' + g.mail : '') }))} value={groepen} onChange={setGroepen} />
      </Card>
      <Card title="Gedeelde postvakken" icon={Mailbox}>
        {info.exo === false ? <Msg kind="warn">Exchange Online is niet verbonden.</Msg> : (
          <>
            <CheckList items={data.shared.map((s) => ({ v: s.mail, l: s.name, s: s.mail + (r.per && r.per[s.mail] ? ` · ${[r.per[s.mail].full && 'volledig', r.per[s.mail].send && 'verzenden als'].filter(Boolean).join(', ')}` : '') }))}
              value={shared} onChange={setShared} height={150} />
            <div className="row" style={{ marginTop: 4 }}>
              <Check checked={r.full} onChange={(v) => setR({ ...r, full: v })}>Volledige toegang</Check>
              <Check checked={r.send} onChange={(v) => setR({ ...r, send: v })}>Verzenden als</Check>
              <Check checked={r.auto} onChange={(v) => setR({ ...r, auto: v })}>Automapping</Check>
            </div>
            {r.per && Object.keys(r.per).length > 0 && <div className="hint">Voor postvakken van de voorbeeldmedewerker worden dezelfde rechten gebruikt als bij die medewerker.</div>}
          </>
        )}
        {!skus.length && shared.length > 0 && <Msg kind="warn">Zonder licentie worden de gedeelde postvakken overgeslagen.</Msg>}
      </Card>
    </>
  );
}

// Kies een bestaande medewerker als voorbeeld
function VoorbeeldKiezen({ close }) {
  const [users, setUsers] = useState(null);
  useEffect(() => { getUsers().then(setUsers).catch(() => setUsers([])); }, []);
  return (
    <>
      <h3>Nieuwe gebruiker op basis van een bestaande medewerker</h3>
      <p className="hint" style={{ marginTop: 0 }}>Licenties, groepen, gedeelde postvakken (met dezelfde rechten), functie, afdeling, kantoor en land worden overgenomen.</p>
      {!users ? <Loading /> : <Picker height={340} placeholder="Zoek medewerker, bijv. Henkie..."
        items={users.filter((u) => !u.guest).map((u) => ({ v: u.id, l: u.name, s: u.upn }))} onPick={(i) => close(i)} />}
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn></div>
    </>
  );
}

export default function NieuweGebruiker() {
  const { info } = useApp();
  const [modus, setModus] = useState(() => startTab('nieuw', 'een'));
  const [data, setData] = useState(null);
  const [skus, setSkus] = useState([]);
  const [groepen, setGroepen] = useState([]);
  const [shared, setShared] = useState([]);
  const [r, setR] = useState({ full: true, send: true, auto: true, per: {} });
  const [voorbeeld, setVoorbeeld] = useState(null);

  useEffect(() => {
    Promise.all([getSkus(), api('groups.list', { fresh: false }), info.exo !== false ? getShared() : []])
      .then(([s, g, sh]) => setData({ skus: s, groepen: g.groups.filter((x) => x.type !== 'Gedeeld postvak' && x.edit), shared: sh }))
      .catch(() => setData({ skus: [], groepen: [], shared: [] }));
  }, [info.exo]);

  const kopieer = async (setF) => {
    const i = await openModal((close) => <VoorbeeldKiezen close={close} />, { wide: true });
    if (!i) return;
    const t = await act('user.template', { id: i.v }, { busy: true, msg: `Gegevens van ${i.l} ophalen...` });
    if (!t) return;
    setVoorbeeld(t);
    setSkus(t.skus);
    setGroepen(t.groups.map((g) => g.id));
    setShared(t.shared.map((s) => s.mail));
    setR({ ...r, per: Object.fromEntries(t.shared.map((s) => [s.mail, { full: s.full, send: s.send }])) });
    if (setF) setF((f) => ({ ...f, title: t.title, dept: t.dept, office: t.office, loc: t.loc || f.loc }));
    toast(`Overgenomen van ${t.name}: ${t.skus.length} licentie(s), ${t.groups.length} groep(en), ${t.shared.length} gedeeld(e) postvak(ken).`, 'g');
  };
  const reset = () => { setSkus([]); setGroepen([]); setShared([]); setR({ full: true, send: true, auto: true, per: {} }); setVoorbeeld(null); };

  if (!data) return <Loading text="Licenties en groepen ophalen..." />;
  const gemeen = { skus, groups: groepen, shared, full: r.full, send: r.send, auto: r.auto, sharedRights: r.per };
  const props = { data, info, skus, setSkus, groepen, setGroepen, shared, setShared, r, setR };

  return (
    <>
      <h2>Nieuwe gebruiker</h2>
      <p className="sub">Account aanmaken met licenties, groepen en gedeelde postvakken. Gebruik een bestaande medewerker als voorbeeld, of maak meerdere gebruikers tegelijk aan.</p>
      <Tabs value={modus} onChange={setModus} tabs={[['een', 'Eén gebruiker', UserPlus], ['bulk', 'Meerdere gebruikers (bulk)', UsersRound]]} />
      {voorbeeld && (
        <div className="updbalk">
          <Copy size={18} style={{ flex: 'none' }} />
          <div style={{ flex: 1 }}>Instellingen overgenomen van <b>{voorbeeld.name}</b>: {voorbeeld.skus.length} licentie(s), {voorbeeld.groups.length} groep(en), {voorbeeld.shared.length} gedeeld(e) postvak(ken). Je kunt ze hieronder nog aanpassen.</div>
          <Btn s icon={X} onClick={reset}>Wissen</Btn>
        </div>
      )}
      {modus === 'een' ? <Een info={info} props={props} gemeen={gemeen} kopieer={kopieer} reset={reset} />
        : <Bulk info={info} props={props} gemeen={gemeen} kopieer={kopieer} />}
    </>
  );
}

function Een({ info, props, gemeen, kopieer, reset }) {
  const app = useApp();
  const [f, setF] = useState(LEEG);
  const [dom, setDom] = useState(info.defaultDomain);
  const [pw, setPw] = useState(genPw);
  const [hand, setHand] = useState({ name: false, alias: false });
  const [res, setRes] = useState(null);
  const zet = (k) => (v) => setF((x) => {
    const n = { ...x, [k]: v };
    if (k === 'given' || k === 'sur') {
      if (!hand.name) n.name = [n.given.trim(), n.sur.trim()].filter(Boolean).join(' ');
      if (!hand.alias) n.alias = aliasVan(n.given, n.sur);
    }
    return n;
  });
  const maak = async () => {
    if (!f.given.trim() || !f.sur.trim() || !f.alias.trim()) return toast('Vul voornaam, achternaam en inlognaam in.', 'e');
    if (!/^[a-z0-9._-]+$/i.test(f.alias.trim())) return toast('De inlognaam mag alleen letters, cijfers, punt, streepje en liggend streepje bevatten.', 'e');
    if (pw.length < 8) return toast('Wachtwoord is te kort.', 'e');
    const upn = f.alias.trim() + '@' + dom;
    if (!await ask(`Gebruiker ${upn} aanmaken?\n\nLicenties: ${gemeen.skus.length}\nGroepen: ${gemeen.groups.length}\nGedeelde postvakken: ${gemeen.shared.length}`, 'Aanmaken')) return;
    const d = await act('user.create', { ...f, ...gemeen, name: f.name.trim() || `${f.given} ${f.sur}`, alias: f.alias.trim(), domain: dom, password: pw },
      { msg: 'Gebruiker aanmaken... (met licentie en postvakrechten kan het enkele minuten duren)' });
    if (!d) return;
    clearCache('users', 'skus');
    setRes({ ...d, pw });
  };
  if (res) {
    return (
      <Card>
        <Msg kind="ok"><b>{res.upn}</b> is aangemaakt.</Msg>
        <label className="f">Tijdelijk wachtwoord</label>
        <div className="row"><div className="pw">{res.pw}</div>
          <div className="n"><Btn icon={Copy} onClick={() => navigator.clipboard.writeText(`${res.upn}\n${res.pw}`).then(() => toast('Gekopieerd.', 'g'), () => toast('Kopiëren is niet gelukt.', 'e'))}>Inloggegevens kopiëren</Btn></div></div>
        {res.problems.length > 0 && <Msg kind="warn"><b>Let op, dit is niet gelukt:</b><br />{res.problems.map((p) => <div key={p}>{p}</div>)}</Msg>}
        <div style={{ marginTop: 16 }} className="btns">
          <Btn v="p" icon={UserPlus} onClick={() => { setRes(null); setF(LEEG); setPw(genPw()); setHand({ name: false, alias: false }); }}>Nog een gebruiker (zelfde instellingen)</Btn>
          <Btn onClick={() => { setRes(null); setF(LEEG); setPw(genPw()); setHand({ name: false, alias: false }); reset(); }}>Nieuwe gebruiker vanaf leeg</Btn>
        </div>
        {app && (
          <div className="card" style={{ marginTop: 16, display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', borderLeft: '4px solid var(--cy)' }}>
            <FolderLock size={22} style={{ color: 'var(--hd)' }} />
            <div style={{ flex: 1, minWidth: 240 }}><b>Volgende stap: toegang tot mappen</b>
              <div className="hint" style={{ margin: 0 }}>Werkt deze klant met één SharePoint-site met mappen per afdeling (bijv. site Data)? Vink daar aan welke mappen {res.upn} nodig heeft; de app zet de medewerker in de juiste SharePoint-groepen.</div></div>
            <Btn v="p" icon={FolderLock} onClick={() => { doorgeven.mappenGebruiker = res.upn; app.setView('spmappen'); }}>Mappen kiezen</Btn>
          </div>)}
        <div>
        </div>
      </Card>
    );
  }
  return (
    <div className="cols2">
      <div>
        <Card title="Gegevens" icon={UserPlus} right={<Btn s icon={Copy} onClick={() => kopieer(setF)}>Kopiëren van medewerker</Btn>}>
          <div className="row"><Field label="Voornaam *" value={f.given} onChange={zet('given')} autoFocus /><Field label="Achternaam *" value={f.sur} onChange={zet('sur')} /></div>
          <Field label="Weergavenaam" value={f.name} onChange={(v) => { setHand((h) => ({ ...h, name: true })); zet('name')(v); }} />
          <label className="f">Inlognaam *</label>
          <div className="row">
            <input type="text" value={f.alias} onChange={(e) => { setHand((h) => ({ ...h, alias: true })); zet('alias')(e.target.value); }} />
            <select value={dom} onChange={(e) => setDom(e.target.value)}>{info.domains.map((d) => <option key={d.id}>{d.id}</option>)}</select>
          </div>
          <div className="row"><Field label="Functie" value={f.title} onChange={zet('title')} /><Field label="Afdeling" value={f.dept} onChange={zet('dept')} /></div>
          <div className="row"><Field label="Kantoorlocatie" value={f.office} onChange={zet('office')} /><Field label="Mobiel" value={f.mobile} onChange={zet('mobile')} /></div>
          <label className="f">Land (gebruikslocatie)</label>
          <select value={f.loc} onChange={(e) => zet('loc')(e.target.value)}>{['NL', 'BE', 'DE', 'FR', 'GB', 'US'].map((l) => <option key={l}>{l}</option>)}</select>
          <label className="f">Tijdelijk wachtwoord</label>
          <div className="row"><input type="text" value={pw} onChange={(e) => setPw(e.target.value)} style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace' }} />
            <div className="n"><Btn icon={RefreshCw} onClick={() => setPw(genPw())}>Nieuw</Btn></div></div>
          <Check checked={f.force} onChange={zet('force')}>Wachtwoord moet bij eerste keer inloggen gewijzigd worden</Check>
        </Card>
      </div>
      <div>
        <Instellingen {...props} />
        <Btn v="p lg" w icon={UserPlus} onClick={maak}>Gebruiker aanmaken</Btn>
      </div>
    </div>
  );
}

// ---------------- Bulk ----------------
const KOLOMMEN = [['given', 'Voornaam *'], ['sur', 'Achternaam *'], ['alias', 'Inlognaam'], ['title', 'Functie'], ['dept', 'Afdeling'], ['mobile', 'Mobiel']];
const leegRij = () => ({ given: '', sur: '', alias: '', title: '', dept: '', mobile: '', hand: false });

function Plakken({ close }) {
  const [t, setT] = useState('');
  return (
    <>
      <h3>Plakken uit Excel of CSV</h3>
      <p className="hint" style={{ marginTop: 0 }}>Eén gebruiker per regel. Kolommen (gescheiden door tab, puntkomma of komma): <b>voornaam, achternaam, functie, afdeling, mobiel, inlognaam</b>.
        Alleen voornaam en achternaam zijn verplicht. Een kopregel wordt herkend en overgeslagen.</p>
      <textarea rows={10} value={t} onChange={(e) => setT(e.target.value)} placeholder={'Jan\tJansen\tMonteur\tWerkplaats\t0612345678\nPetra\tde Vries\tAdministratie'} autoFocus />
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" disabled={!t.trim()} onClick={() => close(t)}>Toevoegen</Btn></div>
    </>
  );
}

function Bulk({ info, props, gemeen, kopieer }) {
  const [rijen, setRijen] = useState([leegRij(), leegRij(), leegRij()]);
  const [dom, setDom] = useState(info.defaultDomain);
  const [loc, setLoc] = useState('NL');
  const [force, setForce] = useState(true);
  const [algemeen, setAlgemeen] = useState({ title: '', dept: '', office: '' });
  const zet = (i, k, v) => setRijen((rs) => rs.map((r, j) => {
    if (j !== i) return r;
    const n = { ...r, [k]: v };
    if (k === 'alias') n.hand = true;
    if ((k === 'given' || k === 'sur') && !n.hand) n.alias = aliasVan(n.given, n.sur);
    return n;
  }));
  const plak = async () => {
    const t = await openModal((close) => <Plakken close={close} />, { wide: true });
    if (!t) return;
    const nieuw = t.split(/\r?\n/).map((l) => l.split(/\t|;|,/).map((x) => x.trim())).filter((c) => c[0] || c[1])
      .filter((c, i) => !(i === 0 && /voornaam|first/i.test(c[0])))
      .map((c) => ({ given: c[0] || '', sur: c[1] || '', title: c[2] || '', dept: c[3] || '', mobile: c[4] || '', alias: c[5] || aliasVan(c[0], c[1]), hand: !!c[5] }));
    setRijen((rs) => [...rs.filter((r) => r.given || r.sur), ...nieuw]);
    toast(`${nieuw.length} regel(s) toegevoegd.`, 'g');
  };
  const geldig = rijen.filter((r) => r.given.trim() && r.sur.trim() && r.alias.trim());
  const start = async () => {
    if (!geldig.length) return toast('Vul minimaal één regel met voornaam en achternaam in.', 'e');
    const fout = geldig.find((r) => !/^[a-z0-9._-]+$/i.test(r.alias.trim()));
    if (fout) return toast(`Ongeldige inlognaam: ${fout.alias}`, 'e');
    const dubbel = geldig.map((r) => r.alias.toLowerCase()).find((a, i, l) => l.indexOf(a) !== i);
    if (dubbel) return toast(`Inlognaam komt twee keer voor: ${dubbel}`, 'e');
    if (!await ask(`${geldig.length} gebruiker(s) aanmaken in ${info.tenant}?\n\nDomein: ${dom}\nLicenties: ${gemeen.skus.length}\nGroepen: ${gemeen.groups.length}\nGedeelde postvakken: ${gemeen.shared.length}\n\nIeder krijgt een eigen willekeurig wachtwoord; na afloop kun je die exporteren.`, 'Aanmaken')) return;
    const rows = geldig.map((r) => ({
      ...gemeen, given: r.given.trim(), sur: r.sur.trim(), name: `${r.given.trim()} ${r.sur.trim()}`, alias: r.alias.trim(), domain: dom,
      title: r.title || algemeen.title, dept: r.dept || algemeen.dept, office: algemeen.office, mobile: r.mobile, loc, force,
    }));
    const k = await toonKlus(await act('users.bulkcreate', { rows }, { msg: 'Starten...' }),
      { kolommen: [['upn', 'Account'], ['password', 'Wachtwoord']], csv: 'nieuwe-gebruikers.csv' });
    if (k) { clearCache('users', 'skus'); if (!k.bezig && !k.fout) setRijen([leegRij(), leegRij(), leegRij()]); }
  };
  return (
    <div className="cols2" style={{ gridTemplateColumns: 'minmax(0, 1.5fr) minmax(320px, 1fr)' }}>
      <div>
        <Card title={`Gebruikers (${geldig.length})`} icon={UsersRound}
          right={<div className="btns"><Btn s icon={ClipboardPaste} onClick={plak}>Plakken uit Excel</Btn><Btn s icon={Copy} onClick={() => kopieer(null)}>Kopiëren van medewerker</Btn></div>}>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead><tr>{KOLOMMEN.map(([, l]) => <th key={l}>{l}</th>)}<th /></tr></thead>
              <tbody>{rijen.map((r, i) => (
                <tr key={i}>
                  {KOLOMMEN.map(([k]) => (
                    <td key={k} style={{ padding: '4px 4px' }}>
                      <input type="text" value={r[k]} onChange={(e) => zet(i, k, e.target.value)} style={{ minWidth: k === 'alias' ? 140 : 100, padding: '6px 8px' }}
                        placeholder={k === 'alias' ? 'automatisch' : ''} />
                    </td>))}
                  <td><Btn s icon={Trash2} onClick={() => setRijen((rs) => rs.filter((_, j) => j !== i))} title="Regel verwijderen" /></td>
                </tr>))}</tbody>
            </table>
          </div>
          <div style={{ marginTop: 8 }}><Btn s icon={Plus} onClick={() => setRijen((rs) => [...rs, leegRij()])}>Regel toevoegen</Btn></div>
        </Card>
        <Card title="Voor alle gebruikers">
          <div className="row">
            <div><label className="f" style={{ marginTop: 0 }}>Domein</label><select value={dom} onChange={(e) => setDom(e.target.value)}>{info.domains.map((d) => <option key={d.id}>{d.id}</option>)}</select></div>
            <div><label className="f" style={{ marginTop: 0 }}>Land</label><select value={loc} onChange={(e) => setLoc(e.target.value)}>{['NL', 'BE', 'DE', 'FR', 'GB', 'US'].map((l) => <option key={l}>{l}</option>)}</select></div>
          </div>
          <div className="row"><Field label="Functie (als niet ingevuld)" value={algemeen.title} onChange={(v) => setAlgemeen({ ...algemeen, title: v })} />
            <Field label="Afdeling (als niet ingevuld)" value={algemeen.dept} onChange={(v) => setAlgemeen({ ...algemeen, dept: v })} />
            <Field label="Kantoorlocatie" value={algemeen.office} onChange={(v) => setAlgemeen({ ...algemeen, office: v })} /></div>
          <Check checked={force} onChange={setForce}>Wachtwoord moet bij eerste keer inloggen gewijzigd worden</Check>
          <div className="hint">Iedere gebruiker krijgt een eigen willekeurig wachtwoord. Na afloop kun je de lijst met wachtwoorden exporteren (CSV). Maak daarna eventueel in Gebruikers beheren de OneDrives aan.</div>
        </Card>
        <Btn v="p lg" w icon={UsersRound} disabled={!geldig.length} onClick={start}>{geldig.length} gebruiker(s) aanmaken</Btn>
      </div>
      <div><Instellingen {...props} /></div>
    </div>
  );
}

