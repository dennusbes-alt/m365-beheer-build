// E-mail > Archief en retentie: online archief en retentiebeleid per postvak, retentiebeleid en retentietags beheren.
import { useEffect, useMemo, useState } from 'react';
import { startTab } from '../store.jsx';
import { Archive, ChevronDown, ChevronRight, Pencil, Plus, RefreshCw, Tags, Trash2, Users } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, openModal, toast } from '../overlays.jsx';
import { useApp } from '../store.jsx';
import { Btn, Card, Check, Chip, Loading, SearchBox, Tabs, csv, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';

const gb = (b) => (b == null ? '-' : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);
const termijn = (d) => (d == null ? 'onbeperkt' : d % 365 === 0 ? `${d / 365} jaar` : d % 30 === 0 && d >= 60 ? `${d / 30} maanden` : `${d} dagen`);

export default function Archief() {
  const { info } = useApp();
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [tab, setTab] = useState(() => startTab('archief', 'postvakken'));
  const laad = async (fresh) => {
    setFout('');
    try { setD(await api('ret.list', { fresh }, { quiet: true })); } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { if (info.exo !== false) laad(false); }, [info.exo]); // eslint-disable-line react-hooks/exhaustive-deps
  if (info.exo === false) return <><h2>Archief en retentie</h2><Msg kind="err">Exchange Online is niet verbonden bij deze klant.</Msg></>;
  if (fout && !d) return <><h2>Archief en retentie</h2><Msg kind="warn">{fout}</Msg></>;
  if (!d) return <><h2>Archief en retentie</h2><Loading text="Postvakken en retentiebeleid ophalen..." /></>;
  return (
    <>
      <h2>Archief en retentie</h2>
      <p className="sub">Online archief en retentiebeleid per postvak, en het beheer van retentiebeleid en retentietags (zoals in Exchange: bijv. "na 2 jaar naar het archief").</p>
      <Tabs value={tab} onChange={setTab} tabs={[['postvakken', `Postvakken (${d.mailboxes.length})`, Users], ['beleid', `Retentiebeleid (${d.policies.length})`, Archive],
        ['tags', `Retentietags (${d.tags.length})`, Tags]]} />
      {tab === 'postvakken' && <Postvakken d={d} herlaad={() => laad(true)} />}
      {tab === 'beleid' && <Beleid d={d} herlaad={() => laad(true)} />}
      {tab === 'tags' && <TagsLijst d={d} herlaad={() => laad(true)} />}
    </>
  );
}

// ---------------------------------------------------------------- Postvakken
function Postvakken({ d, herlaad }) {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('');
  const [kies, setKies] = useState([]);
  const [beleid, setBeleid] = useState('');
  const [open, setOpen] = useState(null);
  const [detail, setDetail] = useState({});
  const lijst = useMemo(() => d.mailboxes.filter((m) => (filter === 'archief' ? m.archive : filter === 'geen' ? !m.archive : filter ? m.policy === filter : true)), [d, filter]);
  const shown = useFilter(lijst, q, (m) => [m.name, m.mail, m.policy]);
  const alle = shown.length > 0 && shown.every((m) => kies.includes(m.mail));
  const toon = async (m) => {
    setOpen(open === m.mail ? null : m.mail);
    if (!detail[m.mail]) {
      try { const x = await api('ret.mailbox', { mailbox: m.mail }, { quiet: true }); setDetail((o) => ({ ...o, [m.mail]: x })); } catch (e) { setDetail((o) => ({ ...o, [m.mail]: { fout: e.message } })); }
    }
  };
  const doe = async (body, tekst, gevaar) => {
    const doelen = kies.length ? kies : [];
    if (!doelen.length) return toast('Vink eerst een of meer postvakken aan.', 'e');
    if (!await ask(`${tekst}\n\n${doelen.length} postvak(ken): ${doelen.slice(0, 8).join(', ')}${doelen.length > 8 ? ' ...' : ''}`, 'Uitvoeren', !!gevaar)) return;
    const r = await act('ret.mailbox.set', { ...body, mailboxes: doelen }, { msg: 'Bezig...' });
    if (r) {
      if (r.failed) openModal((close) => <><h3>Resultaat</h3><div className="pre">{r.results.join('\n')}</div><div className="foot"><button className="btn p" onClick={() => close()}>Sluiten</button></div></>);
      setKies([]); setDetail({}); herlaad();
    }
  };
  return (
    <Card title="Postvakken" icon={Users} right={<div className="btns">
      <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 'auto' }}>
        <option value="">Alle postvakken</option><option value="archief">Met archief</option><option value="geen">Zonder archief</option>
        {d.policies.map((p) => <option key={p.name} value={p.name}>Beleid: {p.name}</option>)}
      </select>
      <Btn s onClick={() => csv('archief-retentie.csv', [['Naam', 'Postvak', 'Soort', 'Retentiebeleid', 'Archief', 'Automatisch uitbreiden', 'Retentie gepauzeerd'],
        ...d.mailboxes.map((m) => [m.name, m.mail, m.type, m.policy, m.archive ? 'Ja' : 'Nee', m.autoExpand ? 'Ja' : 'Nee', m.hold ? 'Ja' : 'Nee'])])}>CSV</Btn>
      <Btn s icon={RefreshCw} onClick={herlaad}>Vernieuwen</Btn></div>}>
      <div className="bulkbalk" style={{ background: "var(--bg)", borderRadius: 8, padding: "8px 10px", display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
        <b style={{ fontSize: 13 }}>{kies.length} geselecteerd:</b>
        <select value={beleid} onChange={(e) => setBeleid(e.target.value)} style={{ width: 'auto' }}>
          <option value="">Retentiebeleid kiezen...</option>{d.policies.map((p) => <option key={p.name}>{p.name}</option>)}
        </select>
        <Btn s disabled={!beleid || !kies.length} onClick={() => doe({ policy: beleid, process: true }, `Retentiebeleid '${beleid}' toewijzen? De verwerking wordt direct gestart (het verplaatsen of verwijderen kan enkele uren tot dagen duren).`)}>Beleid toewijzen</Btn>
        <Btn s disabled={!kies.length} onClick={() => doe({ archive: 'enable' }, 'Online archief aanzetten? Vraagt een licentie met archief (Exchange Online Plan 1 of hoger, of Exchange Online Archiving).')}>Archief aan</Btn>
        <Btn s disabled={!kies.length} onClick={() => doe({ autoExpand: true }, 'Automatisch uitbreidend archief aanzetten (tot 1,5 TB)?\n\nLet op: dit kan niet meer worden uitgezet. Vraagt Exchange Online Plan 2, Business Premium, E3/E5 of Exchange Online Archiving.', true)}>Automatisch uitbreiden</Btn>
        <Btn s disabled={!kies.length} onClick={() => doe({ hold: true }, 'Retentie pauzeren (Retention Hold)? Er wordt dan niets meer verplaatst of verwijderd, bijv. tijdens lang verlof.')}>Pauzeren</Btn>
        <Btn s disabled={!kies.length} onClick={() => doe({ hold: false }, 'Retentie hervatten?')}>Hervatten</Btn>
        <Btn s disabled={!kies.length} onClick={() => doe({ process: true }, 'Verwerking van retentie nu starten (Start-ManagedFolderAssistant)?')}>Nu verwerken</Btn>
        <Btn s v="dl" disabled={!kies.length} onClick={() => doe({ archive: 'disable' }, 'Online archief UITZETTEN?\n\nGevolg: het archief is niet meer zichtbaar voor de gebruiker. De inhoud blijft 30 dagen herstelbaar door het archief weer aan te zetten; daarna is het weg.', true)}>Archief uit</Btn>
      </div>
      <SearchBox value={q} onChange={setQ} placeholder="Zoek postvak of beleid..." />
      <div style={{ maxHeight: 'calc(100vh - 360px)', overflow: 'auto', marginTop: 10 }}>
        <table className="vastkop">
          <thead><tr><th style={{ width: 28 }}><input type="checkbox" checked={alle} onChange={(e) => setKies(e.target.checked ? shown.map((m) => m.mail) : [])} /></th>
            <th>Postvak</th><th>Retentiebeleid</th><th>Archief</th><th /></tr></thead>
          <tbody>{shown.slice(0, MAX_RIJEN).map((m) => {
            const x = detail[m.mail];
            return [
              <tr key={m.mail}>
                <td><input type="checkbox" checked={kies.includes(m.mail)} onChange={(e) => setKies((k) => (e.target.checked ? [...k, m.mail] : k.filter((y) => y !== m.mail)))} /></td>
                <td className="tegelklik" onClick={() => toon(m)}><b>{m.name}</b> {m.type !== 'Gebruiker' && <Chip k="mu">{m.type.toLowerCase()}</Chip>}<br /><small className="hint">{m.mail}</small></td>
                <td>{m.policy || <span className="hint">geen</span>} {m.hold && <Chip k="o">gepauzeerd</Chip>}</td>
                <td>{m.archive ? <Chip k="g">Aan{m.autoExpand ? ' · uitbreidend' : ''}</Chip> : <Chip k="mu">Uit</Chip>}</td>
                <td><Btn s onClick={() => toon(m)}>{open === m.mail ? <ChevronDown size={14} /> : <ChevronRight size={14} />}Details</Btn></td>
              </tr>,
              open === m.mail && (
                <tr key={m.mail + '-d'}><td /><td colSpan={4} style={{ background: 'var(--bg)' }}>
                  {!x ? <Loading text="Grootte ophalen..." /> : x.fout ? <Msg kind="warn">{x.fout}</Msg> : (
                    <div className="kv">
                      <div><label>Postvak</label><div>{gb(x.size)} <small className="hint">({x.items ?? '-'} items, limiet {String(x.quota).split(' (')[0] || '-'})</small></div></div>
                      <div><label>Archief</label><div>{x.archive ? <>{gb(x.archiveSize)} <small className="hint">({x.archiveItems ?? '-'} items{x.autoExpand ? ', automatisch uitbreidend' : `, limiet ${String(x.archiveQuota).split(' (')[0] || '-'}`})</small></> : 'Niet aan'}</div></div>
                      <div><label>Retentiebeleid</label><div>{x.policy || 'geen'}{x.hold ? ' (gepauzeerd)' : ''}</div></div>
                      <div><label>Bewaren voor juridische procedure</label><div>{x.litigation ? 'Aan (Litigation Hold)' : 'Uit'}</div></div>
                    </div>)}
                </td></tr>),
            ];
          })}</tbody>
        </table>
        <Meer totaal={shown.length} />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- Retentiebeleid
function BeleidForm({ d, p, close }) {
  const [naam, setNaam] = useState(p ? p.name : '');
  const [tags, setTags] = useState(p ? p.tags : []);
  const [std, setStd] = useState(p ? p.default : false);
  const opslaan = async () => {
    if (!naam.trim()) return toast('Geef het beleid een naam.', 'e');
    if (await act('ret.policy.save', { original: p ? p.name : undefined, name: naam.trim(), tags, default: std && !(p && p.default) }, { msg: 'Opslaan...' })) close(true);
  };
  const standaardTags = tags.map((t) => d.tags.find((x) => x.name === t)).filter((t) => t && t.type === 'All');
  return (
    <>
      <h3>{p ? `Retentiebeleid '${p.name}' bewerken` : 'Nieuw retentiebeleid'}</h3>
      <label className="f">Naam</label>
      <input type="text" value={naam} onChange={(e) => setNaam(e.target.value)} placeholder="Bijv. Zorg 7 jaar bewaren" autoFocus />
      <label className="f" style={{ marginTop: 12 }}>Retentietags in dit beleid</label>
      <div className="list" style={{ maxHeight: 300 }}>
        {d.tags.map((t) => (
          <label key={t.name} className="li" style={{ cursor: 'pointer' }}>
            <input type="checkbox" checked={tags.includes(t.name)} onChange={(e) => setTags((x) => (e.target.checked ? [...x, t.name] : x.filter((y) => y !== t.name)))} />
            <span className="m"><b>{t.name}</b><small>{t.typeText} · {t.actionText} na {termijn(t.days)}{t.enabled ? '' : ' · uitgeschakeld'}</small></span>
          </label>))}
      </div>
      {standaardTags.length > 1 && <Msg kind="warn">Er zitten {standaardTags.length} standaardtags (hele postvak) in; Exchange staat er per actie maar één toe (één om te verplaatsen en één om te verwijderen).</Msg>}
      {!(p && p.default) && <div style={{ marginTop: 10 }}><Check checked={std} onChange={setStd}>Standaardbeleid voor nieuwe postvakken</Check></div>}
      <div className="foot"><button className="btn" onClick={() => close(false)}>Annuleren</button><button className="btn p" onClick={opslaan}>Opslaan</button></div>
    </>
  );
}

function Beleid({ d, herlaad }) {
  const bewerk = async (p) => { if (await openModal((close) => <BeleidForm d={d} p={p} close={close} />)) herlaad(); };
  const weg = async (p) => {
    if (!await ask(`Retentiebeleid '${p.name}' verwijderen?${p.used ? `\n\nLET OP: ${p.used} postvak(ken) gebruiken dit beleid. Die hebben daarna geen retentiebeleid meer (er wordt niets meer automatisch gearchiveerd).` : ''}`, 'Verwijderen', true)) return;
    if (await act('ret.policy.delete', { name: p.name }, { msg: 'Verwijderen...' })) herlaad();
  };
  return (
    <Card title="Retentiebeleid" icon={Archive} right={<Btn s v="p" icon={Plus} onClick={() => bewerk(null)}>Nieuw beleid</Btn>}>
      <div className="hint" style={{ marginTop: 0 }}>Een retentiebeleid is een set retentietags die je aan postvakken toewijst. Wijzigingen gelden voor alle postvakken met dit beleid.</div>
      {d.policies.map((p) => (
        <div key={p.name} className="card" style={{ margin: '10px 0', boxShadow: 'none' }}>
          <div className="headrow">
            <div className="m"><h3 style={{ margin: 0 }}>{p.name} {p.default && <Chip k="g">standaard</Chip>}</h3>
              <div className="hint" style={{ margin: '2px 0 0' }}>{p.used} postvak(ken) · {p.tags.length} tag(s)</div></div>
            <div className="btns"><Btn s icon={Pencil} onClick={() => bewerk(p)}>Bewerken</Btn>{!p.default && <Btn s v="dl" icon={Trash2} onClick={() => weg(p)} title="Verwijderen" />}</div>
          </div>
          <div className="btns" style={{ marginTop: 8 }}>{p.tags.map((n) => {
            const t = d.tags.find((x) => x.name === n);
            return <Chip key={n} k={t && t.action === 'MoveToArchive' ? 'g' : t && t.action === 'PermanentlyDelete' ? 'r' : 'mu'}
              title={t ? `${t.typeText} · ${t.actionText} na ${termijn(t.days)}` : ''}>{n}</Chip>;
          })}{!p.tags.length && <span className="hint">Geen tags</span>}</div>
        </div>))}
    </Card>
  );
}

// ---------------------------------------------------------------- Retentietags
function TagForm({ d, t, close }) {
  const [v, setV] = useState(t ? { ...t, days: t.days ?? 730 } : { name: '', type: 'All', days: 730, action: 'MoveToArchive', enabled: true, comment: '' });
  const zet = (k, x) => setV((o) => ({ ...o, [k]: x }));
  const archiefKan = ['All', 'Personal', 'RecoverableItems'].includes(v.type);
  const opslaan = async () => {
    if (!v.name.trim()) return toast('Geef de tag een naam.', 'e');
    if (await act('ret.tag.save', { original: t ? t.name : undefined, name: v.name.trim(), type: v.type, days: +v.days, action: v.action, enabled: v.enabled, comment: v.comment },
      { msg: 'Opslaan...' })) close(true);
  };
  return (
    <>
      <h3>{t ? `Retentietag '${t.name}' bewerken` : 'Nieuwe retentietag'}</h3>
      <label className="f">Naam</label>
      <input type="text" value={v.name} onChange={(e) => zet('name', e.target.value)} placeholder="Bijv. 7 jaar bewaren, daarna verwijderen" autoFocus />
      <div className="row" style={{ marginTop: 10 }}>
        <div><label className="f">Geldt voor</label>
          <select value={v.type} disabled={!!t} onChange={(e) => { zet('type', e.target.value); if (!['All', 'Personal', 'RecoverableItems'].includes(e.target.value) && v.action === 'MoveToArchive') zet('action', 'DeleteAndAllowRecovery'); }}>
            {Object.entries(d.types).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></div>
        <div><label className="f">Actie</label>
          <select value={v.action} onChange={(e) => zet('action', e.target.value)}>
            {Object.entries(d.actions).filter(([k]) => k !== 'MoveToArchive' || archiefKan).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></div>
        <div><label className="f">Na (dagen)</label>
          <input type="number" min={1} max={24855} value={v.days} onChange={(e) => zet('days', e.target.value)} />
          <div className="hint" style={{ margin: '2px 0 0' }}>= {termijn(+v.days)}</div></div>
      </div>
      <label className="f" style={{ marginTop: 10 }}>Omschrijving (optioneel)</label>
      <input type="text" value={v.comment} onChange={(e) => zet('comment', e.target.value)} />
      <div style={{ marginTop: 10 }}><Check checked={v.enabled} onChange={(x) => zet('enabled', x)}>Tag actief</Check></div>
      {v.action === 'PermanentlyDelete' && <Msg kind="warn">Definitief verwijderen: items zijn daarna niet meer te herstellen door de gebruiker of beheerder (tenzij er een bewaarbeleid of Litigation Hold actief is).</Msg>}
      {t && <div className="hint">Het type kan na het aanmaken niet meer worden gewijzigd. Wijzigingen gelden voor alle postvakken met een beleid dat deze tag bevat.</div>}
      <div className="foot"><button className="btn" onClick={() => close(false)}>Annuleren</button><button className="btn p" onClick={opslaan}>Opslaan</button></div>
    </>
  );
}

function TagsLijst({ d, herlaad }) {
  const bewerk = async (t) => { if (await openModal((close) => <TagForm d={d} t={t} close={close} />)) herlaad(); };
  const weg = async (t) => {
    const in_ = d.policies.filter((p) => p.tags.includes(t.name)).map((p) => p.name);
    if (!await ask(`Retentietag '${t.name}' verwijderen?${in_.length ? `\n\nDeze tag zit in: ${in_.join(', ')}. Hij verdwijnt daar ook uit.` : ''}`, 'Verwijderen', true)) return;
    if (await act('ret.tag.delete', { name: t.name }, { msg: 'Verwijderen...' })) herlaad();
  };
  return (
    <Card title="Retentietags" icon={Tags} right={<Btn s v="p" icon={Plus} onClick={() => bewerk(null)}>Nieuwe tag</Btn>}>
      <table className="vastkop">
        <thead><tr><th>Naam</th><th>Geldt voor</th><th>Actie</th><th>Na</th><th>In beleid</th><th /></tr></thead>
        <tbody>{d.tags.map((t) => (
          <tr key={t.name}>
            <td><b>{t.name}</b>{!t.enabled && <> <Chip k="mu">uit</Chip></>}{t.comment && <><br /><small className="hint">{t.comment}</small></>}</td>
            <td><small>{t.typeText}</small></td>
            <td><Chip k={t.action === 'MoveToArchive' ? 'g' : t.action === 'PermanentlyDelete' ? 'r' : 'o'}>{t.actionText}</Chip></td>
            <td>{termijn(t.days)}</td>
            <td><small>{d.policies.filter((p) => p.tags.includes(t.name)).map((p) => p.name).join(', ') || '-'}</small></td>
            <td><div className="btns">{!t.system && <><Btn s icon={Pencil} onClick={() => bewerk(t)} title="Bewerken" /><Btn s v="dl" icon={Trash2} onClick={() => weg(t)} title="Verwijderen" /></>}</div></td>
          </tr>))}</tbody>
      </table>
    </Card>
  );
}
