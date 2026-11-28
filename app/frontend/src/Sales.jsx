// Sales: verkoopkansen invoeren en definitief maken (sales), inzien en er een klantproject van maken (app-beheerder).
// Zo komt elk project met een volledige aanlevering vanuit sales binnen.
import { useEffect, useRef, useState } from 'react';
import { Building2, BriefcaseBusiness, CheckCircle2, ChevronLeft, FileText, FolderPlus, Paperclip, Pencil, Plus, Receipt, RefreshCw, Search, ShoppingCart, StickyNote, ThumbsDown, Trash2, TrendingUp, Upload } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { AllesVink, Btn, Chip, Loading, SearchBox } from './ui.jsx';
import { nl } from './Grafiek.jsx';
import { ContractKaart, STANDAARD_CFG, Samensteller, vastePrijsTicket } from './Contracten.jsx';

const eur = (v) => `€ ${nl(v, 0)}`;
const datum = (s) => (s ? String(s).slice(0, 10).split('-').reverse().join('-') : '-');

export default function Sales({ beheerder, onProject, onVoorraad }) {
  const [d, setD] = useState(null);
  const [opt, setOpt] = useState(null);
  const [toon, setToon] = useState('open');
  const [q, setQ] = useState('');
  const [sel, setSel] = useState([]);
  const [open, setOpen] = useState(null);   // id van de opengeklikte kans
  const [bestel, setBestel] = useState(null);   // aantal te bestellen producten (bestellijst Voorraad)
  const laad = (fresh) => api('sa.overzicht', { fresh: !!fresh }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, opportunities: [], totals: {} }));
  useEffect(() => { api('vr.overzicht', {}, { quiet: true }).then((r) => setBestel(r.totals?.toOrder || 0)).catch(() => {}); }, []);
  useEffect(() => { laad(false); api('sa.opties', {}, { quiet: true }).then(setOpt).catch(() => setOpt({ stages: [], ratings: [], sources: [], canEdit: false })); }, []);
  if (!d) return <div className="mg klanten breed"><Loading text="Saleskansen ophalen uit Autotask..." /></div>;
  const bulk = async (actie, ids) => {
    const tekst = { final: 'definitief maken (gewonnen)', lost: 'op verloren zetten', delete: 'verwijderen (in Autotask op Inactief; ze verdwijnen uit de lijst)' }[actie];
    if (!await ask(`${ids.length} kans(en) ${tekst}?`, 'Doorgaan')) return false;
    const x = await act('sa.status', { action: actie, ids }, { msg: 'Bijwerken in Autotask...' });
    if (x) { toast(`${x.ok} kans(en) bijgewerkt.`, 'g'); setSel([]); laad(true); return true; }
    return false;
  };
  const t = d.totals || {};
  const lijst = (d.opportunities || []).filter((o) => (toon === 'open' ? !o.final : toon === 'final' ? o.final && !o.project : toon === 'project' ? !!o.project : true))
    .filter((o) => !q || `${o.title} ${o.company} ${o.contact}`.toLowerCase().includes(q.toLowerCase()));

  const bewerk = async (o) => {
    const r = await openModal((close) => <KansVenster o={o} opt={opt} close={close} />, { wide: true });
    if (r && await act('sa.opslaan', r, { msg: o ? 'Kans opslaan...' : 'Kans invoeren in Autotask...' })) { toast(o ? 'Kans bijgewerkt.' : 'Kans ingevoerd.', 'g'); laad(true); }
  };
  const definitief = async (o) => {
    if (!await ask(`"${o.title}" (${o.company}, ${eur(o.amount)}) definitief maken?\n\nDe kans gaat in Autotask op gewonnen (Closed) en daarna kan er een klantproject van worden gemaakt.`, 'Definitief maken')) return;
    if (await act('sa.definitief', { id: o.id }, { msg: 'Definitief maken...' })) { toast('Kans is definitief. Het project kan nu worden aangemaakt.', 'g'); laad(true); }
  };
  const verloren = async (o) => {
    if (!await ask(`"${o.title}" op verloren zetten?`, 'Verloren')) return;
    if (await act('sa.verloren', { id: o.id }, { msg: 'Bijwerken...' })) { toast('Kans op verloren gezet.', 'g'); laad(true); }
  };
  const details = (o) => openModal((close) => <KansDetail o={o} mag={d.canStatus} close={close} />, { wide: true });
  const project = async (o) => {
    if (!o.final && !await ask(`"${o.title}" is nog niet definitief. Eerst definitief maken (gewonnen) en dan het project aanmaken?`, 'Definitief + project')) return;
    const r = await openModal((close) => <ProjectVenster o={o} close={close} />, { wide: true });
    if (!r) return;
    const x = await act('pr.vankans', { opportunityId: o.id, ...r }, { msg: r.templateId ? 'Project aanmaken en fasen/taken uit het template kopiëren...' : 'Project aanmaken...' });
    if (x) {
      toast(`Project aangemaakt${r.templateId ? ` met ${x.phases} fase(n) en ${x.tasks} taak/taken` : ''}.${x.errors && x.errors.length ? ` ${x.errors.length} onderdeel/onderdelen niet gekopieerd.` : ''}`, x.errors && x.errors.length ? 'e' : 'g');
      laad(true);
      if (onProject) onProject(x.id);
    }
  };

  const geopend = open && (d.opportunities || []).find((o) => o.id === open);
  if (geopend) {
    return <KansPagina o={geopend} opt={opt} d={d} beheerder={beheerder} onTerug={() => setOpen(null)} onOpslaan={() => laad(true)}
      onBulk={async (a) => { if (await bulk(a, [geopend.id]) && a === 'delete') setOpen(null); }} onProjectMaken={() => project(geopend)} onProject={onProject} />;
  }

  return (
    <div className="mg klanten breed">
      <div className="mg-hero" style={{ marginTop: 0 }}>
        <div className="mg-top">
          <div><h2>Sales</h2><div className="mg-sub">Verkoopkansen uit Autotask · {d.canEdit ? 'invoeren en definitief maken' : 'inzien en er een project van maken'} · stand {d.at}</div></div>
          <div className="mg-acties">
            {d.canEdit && <Btn v="p" icon={Plus} onClick={() => bewerk(null)}>Nieuwe kans</Btn>}
            {d.canEdit && <Btn icon={Building2} onClick={losseKlant} title="Nieuwe klant in Autotask, met Datto RMM-site en Full Service-contract">Nieuwe klant</Btn>}
            {d.canEdit && <Btn icon={Receipt} onClick={() => vastePrijsTicket()} title="Bijv. Nieuwe computer: product uit de voorraad + vaste prijs installatie">Vaste prijs-ticket</Btn>}
            <Btn icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
          </div>
        </div>
        <div className="mg-kpis">
          <div className="mg-kpi"><div className="l">Open pipeline</div><div className="n">{eur(t.pipeline || 0)}</div><div className="s"><span>{t.open || 0} kans(en)</span></div></div>
          <div className="mg-kpi"><div className="l">Gewogen (x kans)</div><div className="n">{eur(t.weighted || 0)}</div><div className="s"><span>bedrag x slagingskans</span></div></div>
          <div className="mg-kpi"><div className="l">Definitief (12 mnd)</div><div className="n">{eur(t.wonAmount || 0)}</div><div className="s"><span>{t.won || 0} kans(en)</span></div></div>
          <div className="mg-kpi"><div className="l">Nog geen project</div><div className="n" style={t.noProject ? { color: 'var(--or)' } : undefined}>{t.noProject || 0}</div><div className="s"><span>definitief, wacht op project</span></div></div>
        </div>
      </div>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      {bestel > 0 && <div className="msg warn" style={{ display: 'flex', gap: 10, alignItems: 'center' }}><ShoppingCart size={16} /><span style={{ flex: 1 }}><b>{bestel} product(en) te bestellen</b> op de bestellijst (niet op voorraad, aangevraagd door collega's).</span>
        {onVoorraad && <Btn s v="p" onClick={onVoorraad}>Naar de bestellijst</Btn>}</div>}
      <div className="mg-kaart">
        <div className="headrow" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <div className="btns">
            {[['open', 'Open'], ['final', `Definitief, nog geen project (${t.noProject || 0})`], ['project', 'Project gemaakt'], ['alle', 'Alle']].map(([k, l]) => (
              <Btn key={k} s v={toon === k ? 'p' : ''} onClick={() => setToon(k)}>{l}</Btn>))}
          </div>
          <div style={{ width: 260 }}><SearchBox value={q} onChange={setQ} placeholder="Zoek kans of klant..." /></div>
        </div>
        {d.canStatus && (
          <div className="sdq-bulk">
            <AllesVink ids={lijst.map((o) => o.id)} value={sel} onChange={setSel} label={`Alles selecteren (${lijst.length})`} />
            {sel.length > 0 && <>
              <b>{sel.length} gekozen</b>
              <Btn s v="p" icon={CheckCircle2} onClick={() => bulk('final', sel)}>Definitief</Btn>
              <Btn s icon={ThumbsDown} onClick={() => bulk('lost', sel)}>Verloren</Btn>
              <Btn s icon={Trash2} onClick={() => bulk('delete', sel)}>Verwijderen</Btn>
            </>}
          </div>)}
        <table style={{ width: '100%' }}>
          <thead><tr>{d.canStatus && <th style={{ width: 28 }} />}<th>Kans</th><th>Klant</th><th>Fase</th><th style={{ textAlign: 'right' }}>Bedrag</th><th style={{ textAlign: 'right' }}>Kans</th><th>Verwacht</th><th>Status</th><th style={{ textAlign: 'right' }}>Acties</th></tr></thead>
          <tbody>{lijst.map((o) => (
            <tr key={o.id} className="klikrij" onClick={() => setOpen(o.id)} title="Openklikken: alles zien en bewerken">
              {d.canStatus && <td onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={sel.includes(o.id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, o.id] : s.filter((x) => x !== o.id)))} /></td>}
              <td><b>{o.title}</b>{o.description && <div className="hint" style={{ margin: 0, maxWidth: 360, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{o.description}</div>}</td>
              <td>{o.company}{o.contact && <div className="hint" style={{ margin: 0 }}>{o.contact}</div>}</td>
              <td>{o.stageLabel || '-'}</td>
              <td style={{ textAlign: 'right' }}><b>{eur(o.amount)}</b>{o.monthly ? <div className="hint" style={{ margin: 0 }}>{eur(o.monthly)} p/m</div> : null}</td>
              <td style={{ textAlign: 'right' }}>{o.probability}%</td>
              <td>{o.final ? datum(o.closed) : datum(o.close)}</td>
              <td>{o.project ? <Chip k="g" title={o.project.name}>project {o.project.number}</Chip> : o.final ? <Chip k="o">definitief</Chip> : <Chip>{o.status || 'open'}</Chip>}</td>
              <td style={{ textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                <div className="btns" style={{ justifyContent: 'flex-end', margin: 0 }}>
                  <Btn s icon={Pencil} onClick={() => setOpen(o.id)}>Openen</Btn>
                  {d.canStatus && !o.final && <Btn s icon={CheckCircle2} onClick={() => definitief(o)}>Definitief</Btn>}
                  {!o.project && (d.canProject ?? beheerder) && <Btn s v="p" icon={FolderPlus} onClick={() => project(o)}
                    title={o.final ? 'Klantproject maken' : 'Definitief maken en er meteen een klantproject van maken'}>Project maken</Btn>}
                  {o.project && onProject && <Btn s icon={BriefcaseBusiness} onClick={() => onProject(o.project.id)}>Project</Btn>}
                </div>
              </td>
            </tr>))}</tbody>
        </table>
        {!lijst.length && <div className="hint" style={{ padding: 10 }}>Geen kansen in deze selectie.</div>}
      </div>
    </div>);
}

function KansVenster({ o, opt, close }) {
  const [v, setV] = useState(o ? { title: o.title, companyId: o.companyId, company: o.company, contactId: o.contactId || '', amount: o.amount, monthly: o.monthly || '', months: '',
    onetime: '', cost: o.cost || '', probability: o.probability, close: o.close, stage: o.stage || '', description: o.description }
    : { title: '', companyId: null, company: '', contactId: '', amount: '', onetime: '', monthly: '', months: 12, cost: '', probability: 50, close: '', stage: '', description: '' });
  const [zoek, setZoek] = useState('');
  const [nieuwK, setNieuwK] = useState(false);
  const [klaarK, setKlaarK] = useState(null);   // na een nieuwe klant: wat er allemaal is geregeld (Autotask, Datto RMM, Full Service)
  const [bedr, setBedr] = useState([]);
  const [contacten, setContacten] = useState([]);
  const t = useRef(null);
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  useEffect(() => {
    clearTimeout(t.current);
    if (zoek.trim().length < 2) { setBedr([]); return undefined; }
    t.current = setTimeout(() => api('sd.bedrijven', { q: zoek.trim() }, { quiet: true }).then((r) => setBedr(r.companies)).catch(() => {}), 300);
    return () => clearTimeout(t.current);
  }, [zoek]);
  // Contactpersonen van de klant; een net aangemaakte contactpersoon blijft erin, ook als Autotask hem nog niet teruggeeft
  useEffect(() => {
    if (!v.companyId) return;
    api('at.contacten', { companyId: v.companyId, fresh: true }, { quiet: true })
      .then((r) => setContacten((oud) => [...(r.contacts || []), ...oud.filter((c) => c.id && !(r.contacts || []).some((x) => x.id === c.id))]))
      .catch(() => {});
  }, [v.companyId]);
  const totaal = o ? Number(v.amount || 0) : Number(v.onetime || 0) + Number(v.monthly || 0) * Number(v.months || 0);
  const ok = v.title.trim().length >= 3 && v.companyId && totaal >= 0;
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><TrendingUp size={18} />{o ? 'Kans wijzigen' : 'Nieuwe saleskans'}</h3>
      <label className="f">Klant</label>
      {v.companyId ? <div className="btns" style={{ alignItems: 'center' }}><b>{v.company}</b>{!o && <button className="linkknop" onClick={() => { setContacten([]); setV({ ...v, companyId: null, company: '', contactId: '' }); }}>andere klant</button>}</div> : (
        <>
          <div className="btns" style={{ alignItems: 'center', margin: 0 }}>
            <div className="ts-zoek" style={{ flex: 1 }}><Search size={14} /><input autoFocus value={zoek} onChange={(e) => setZoek(e.target.value)} placeholder="Zoek klant in Autotask..." /></div>
            <Btn s icon={Building2} onClick={() => setNieuwK(true)}>Nieuwe klant</Btn>
          </div>
          {nieuwK && <div className="card" style={{ padding: 12, marginTop: 8 }}><NieuweKlant naam={zoek} close={async (r) => {
            if (!r) { setNieuwK(false); return; }
            const x = await nieuweKlantMaken(r, v.title);
            if (x) {
              setNieuwK(false); setContacten([{ id: x.contact.id, name: x.contact.name }]); setV({ ...v, companyId: x.company.id, company: x.company.name, contactId: x.contact.id || '' });
              setKlaarK(x.done);
            }
          }} /></div>}
          <div style={{ display: 'grid', gap: 4, marginTop: 6 }}>{bedr.map((b) => <button key={b.id} type="button" className="ts-proj" onClick={() => setV({ ...v, companyId: b.id, company: b.name })}><b>{b.name}</b></button>)}</div>
        </>)}
      {klaarK && <KlantKlaar done={klaarK} />}
      {v.companyId && <>
        <label className="f">Contactpersoon</label>
        <select value={v.contactId || ''} onChange={z('contactId')} style={{ width: 'auto', minWidth: 260 }}>
          <option value="">Geen</option>{contacten.map((c) => <option key={c.id} value={c.id}>{c.name}{c.email ? ` (${c.email})` : ''}</option>)}
        </select></>}
      <label className="f">Titel (wat wordt er verkocht?)</label>
      <input value={v.title} onChange={z('title')} placeholder="Bijv. Nieuwe inrichting Microsoft 365 + IMAP-migratie" style={{ width: '100%' }} />
      {o ? (
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Bedrag (totaal, excl. btw)</label><input type="number" value={v.amount} onChange={z('amount')} style={{ width: 160 }} /></div>
          <div><label className="f">Kosten</label><input type="number" value={v.cost} onChange={z('cost')} style={{ width: 140 }} /></div>
        </div>) : (
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Eenmalig (excl. btw)</label><input type="number" value={v.onetime} onChange={z('onetime')} style={{ width: 150 }} placeholder="bijv. projectwerk" /></div>
          <div><label className="f">Per maand</label><input type="number" value={v.monthly} onChange={z('monthly')} style={{ width: 130 }} placeholder="bijv. licenties" /></div>
          <div><label className="f">Looptijd (maanden)</label><input type="number" value={v.months} onChange={z('months')} style={{ width: 120 }} /></div>
          <div><label className="f">Kosten (optioneel)</label><input type="number" value={v.cost} onChange={z('cost')} style={{ width: 130 }} /></div>
          <div style={{ alignSelf: 'flex-end', paddingBottom: 8 }}><b>Totaal {eur(totaal)}</b></div>
        </div>)}
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Slagingskans (%)</label><input type="number" min={0} max={100} value={v.probability} onChange={z('probability')} style={{ width: 110 }} /></div>
        <div><label className="f">Verwachte afsluitdatum</label><input type="date" value={v.close} onChange={z('close')} style={{ width: 170 }} /></div>
        <div><label className="f">Fase</label><select value={v.stage || ''} onChange={z('stage')} style={{ width: 'auto', minWidth: 180 }}>
          <option value="">Standaard</option>{(opt?.stages || []).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></div>
      </div>
      <label className="f">Aanlevering voor het project (wat is er afgesproken, scope, wensen, contactmomenten)</label>
      <textarea rows={5} value={v.description} onChange={z('description')} placeholder="Dit wordt de projectomschrijving als er een project van wordt gemaakt." />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!ok} onClick={() => close({ ...(o ? { id: o.id, amount: Number(v.amount || 0) } : { onetime: Number(v.onetime || 0), monthly: Number(v.monthly || 0), months: Number(v.months || 0) }),
          title: v.title.trim(), companyId: v.companyId, contactId: v.contactId ? +v.contactId : null, cost: Number(v.cost || 0), probability: Number(v.probability || 0),
          close: v.close || null, stage: v.stage ? +v.stage : null, description: v.description })}>{o ? 'Opslaan' : 'Invoeren'}</button></div>
    </>);
}

function ProjectVenster({ o, close }) {
  const [t, setT] = useState(null);
  const vandaag = new Date().toISOString().slice(0, 10);
  const [v, setV] = useState({ name: o.title, templateId: '', start: vandaag, end: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10), leadId: '', description: o.description || '',
    vast: false, amount: '', hours: '' });
  useEffect(() => { api('pr.templates', { opportunityId: o.id }, { quiet: true }).then(setT).catch((e) => setT({ templates: [], people: [], error: e.message })); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><FolderPlus size={18} />Klantproject maken</h3>
      <div className="hint" style={{ marginTop: 0 }}>Van de definitieve kans <b>{o.title}</b> voor <b>{o.company}</b> ({eur(o.amount)}). Het project wordt aan de kans gekoppeld.</div>
      {!t ? <Loading text="Templates ophalen..." /> : <>
        {t.error && <Msg kind="warn">{t.error}</Msg>}
        <label className="f">Projectnaam</label><input value={v.name} onChange={z('name')} style={{ width: '100%' }} />
        <label className="f">Template (fasen en taken worden gekopieerd)</label>
        <select value={v.templateId} onChange={z('templateId')} style={{ width: 'auto', minWidth: 320 }}>
          <option value="">Geen template (leeg project)</option>{t.templates.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        {!t.templates.length && <div className="hint">Geen templateprojecten gevonden in Autotask (projecttype Template).</div>}
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Start</label><input type="date" value={v.start} onChange={z('start')} style={{ width: 170 }} /></div>
          <div><label className="f">Gepland klaar</label><input type="date" value={v.end} onChange={z('end')} style={{ width: 170 }} /></div>
          <div><label className="f">Projectleider</label><select value={v.leadId} onChange={z('leadId')} style={{ width: 'auto', minWidth: 220 }}>
            <option value="">Later kiezen</option>{t.people.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></div>
        </div>
        <label className="f">Projectomschrijving (aanlevering van sales)</label>
        <textarea rows={5} value={v.description} onChange={z('description')} />
        <label className="f"><b>Contract voor dit project</b></label>
        {t.fixedContract ? <Msg kind="ok">Sales heeft al een vaste prijs vastgelegd; het project krijgt dat contract.</Msg> : <>
          <div className="btns">
            <Btn s v={!v.vast ? 'p' : ''} onClick={() => setV({ ...v, vast: false })}>Geen (uren volgens nacalculatie)</Btn>
            <Btn s v={v.vast ? 'p' : ''} onClick={() => setV({ ...v, vast: true })}>Vaste prijs (fixed price-contract)</Btn>
          </div>
          {v.vast && <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <div><label className="f">Vaste prijs (excl. btw)</label><input type="number" step="0.01" autoFocus value={v.amount} onChange={z('amount')} style={{ width: 160 }} placeholder="bijv. migratieprijs" /></div>
            <div><label className="f">Geschatte uren</label><input type="number" step="0.5" value={v.hours} onChange={z('hours')} style={{ width: 120 }} /></div>
            <div className="hint" style={{ alignSelf: 'flex-end' }}>Fixed Price-contract, nooit het standaardcontract, gekoppeld aan het project.</div>
          </div>}
        </>}
      </>}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!t || !v.name.trim() || !v.start || !v.end || v.end < v.start || (v.vast && !(Number(v.amount) > 0))}
          onClick={() => close({ name: v.name.trim(), templateId: v.templateId ? +v.templateId : null, start: v.start, end: v.end, leadId: v.leadId ? +v.leadId : null, description: v.description,
            fixedAmount: v.vast ? Number(v.amount) : null, fixedHours: v.vast ? Number(v.hours || 0) : null })}>Project maken</button></div>
    </>);
}

// Notities en bijlagen bij een kans (offerte, afspraken). Notities = Autotask-notities bij de kans; bijlagen tot ~6 MB.
function KansDetail({ o, mag, close, inline }) {
  const [d, setD] = useState(null);
  const [bewerk, setBewerk] = useState(null);   // {noteId?, title, text}
  const bestand = useRef(null);
  const laad = () => api('sa.notities', { id: o.id }, { quiet: true }).then(setD).catch((e) => setD({ notes: [], files: [], error: e.message }));
  useEffect(() => { laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const bewaar = async () => {
    if (await act('sa.notitie', { id: o.id, noteId: bewerk.noteId, title: bewerk.title, text: bewerk.text }, { msg: 'Notitie opslaan...' })) { setBewerk(null); laad(); }
  };
  const weg = async (n) => {
    if (!await ask(`Notitie "${n.title}" verwijderen?`, 'Verwijderen')) return;
    if (await act('sa.notitie', { id: o.id, noteId: n.id, title: n.title, remove: true }, { msg: 'Verwijderen...' })) laad();
  };
  const upload = async (f) => {
    if (!f) return;
    if (f.size > 6 * 1024 * 1024) { toast('Dit bestand is groter dan 6 MB; Autotask accepteert via de API ongeveer 6 MB per bestand.', 'e'); return; }
    const data = await new Promise((ok, mis) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1] || ''); r.onerror = mis; r.readAsDataURL(f); });
    if (await act('sa.bijlage', { id: o.id, name: f.name, data }, { msg: `${f.name} toevoegen...` })) { toast(`${f.name} toegevoegd.`, 'g'); laad(); }
  };
  const bestandWeg = async (b) => {
    if (!await ask(`Bijlage "${b.name}" verwijderen uit Autotask?`, 'Verwijderen')) return;
    if (await act('sa.bijlage', { id: o.id, fileId: b.id, remove: true }, { msg: 'Verwijderen...' })) laad();
  };
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Paperclip size={18} />{o.title}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{o.company}{o.contact ? ` · ${o.contact}` : ''} · {eur(o.amount)}</div>
      {o.description && <div className="pr-omschrijving" style={{ marginBottom: 10 }}>{o.description}</div>}
      {!d ? <Loading text="Notities en bijlagen ophalen..." /> : <>
        {d.error && <Msg kind="warn">{d.error}</Msg>}
        <div className="headrow" style={{ margin: '6px 0' }}><b><FileText size={15} /> Bijlagen</b>
          {mag && <><input ref={bestand} type="file" hidden onChange={(e) => { upload(e.target.files[0]); e.target.value = ''; }} />
            <Btn s icon={Upload} onClick={() => bestand.current.click()}>Bestand toevoegen</Btn></>}</div>
        {d.files.length ? d.files.map((b) => (
          <div key={b.id} className="sdq-rij" style={{ alignItems: 'center' }}>
            <FileText size={16} /><div className="sdq-hoofd" onClick={() => act('sa.bijlage', { id: o.id, fileId: b.id, open: true }, { msg: 'Bijlage openen...' })}>
              <div className="sdq-titel">{b.name}</div><div className="sdq-meta"><span>{b.at}</span><span>klik om te openen</span></div></div>
            {mag && <Btn s icon={Trash2} onClick={() => bestandWeg(b)} title="Verwijderen" />}
          </div>)) : <div className="hint">Nog geen bijlagen (bijvoorbeeld de offerte).</div>}
        <div className="headrow" style={{ margin: '14px 0 6px' }}><b><StickyNote size={15} /> Notities</b>
          {mag && !bewerk && <Btn s icon={Plus} onClick={() => setBewerk({ title: 'Notitie', text: '' })}>Notitie</Btn>}</div>
        {bewerk && (
          <div className="card" style={{ padding: 10, marginBottom: 8 }}>
            <input value={bewerk.title} onChange={(e) => setBewerk({ ...bewerk, title: e.target.value })} style={{ width: '100%' }} placeholder="Titel" />
            <textarea rows={5} autoFocus value={bewerk.text} onChange={(e) => setBewerk({ ...bewerk, text: e.target.value })} style={{ marginTop: 6 }} placeholder="Wat is er besproken of afgesproken?" />
            <div className="btns" style={{ marginTop: 6 }}><Btn s onClick={() => setBewerk(null)}>Annuleren</Btn><Btn s v="p" disabled={!bewerk.text.trim()} onClick={bewaar}>Opslaan</Btn></div>
          </div>)}
        {d.notes.length ? d.notes.map((n) => (
          <div key={n.id} style={{ borderTop: '1px solid var(--bd)', padding: '8px 0' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><b>{n.title}</b><span className="hint" style={{ margin: 0 }}>{n.at}{n.by ? ` · ${n.by}` : ''}</span>
              {mag && <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}><Btn s icon={Pencil} onClick={() => setBewerk({ noteId: n.id, title: n.title, text: n.text })} title="Bewerken" />
                <Btn s icon={Trash2} onClick={() => weg(n)} title="Verwijderen" /></span>}</div>
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{n.text}</div>
          </div>)) : !bewerk && <div className="hint">Nog geen notities.</div>}
      </>}
      {!inline && <div className="foot"><button className="btn p" onClick={() => close()}>Sluiten</button></div>}
    </>);
}

// Nieuwe klant (altijd type Customer) met primaire contactpersoon, vanuit een saleskans
function NieuweKlant({ naam, close }) {
  const [v, setV] = useState({ name: naam || '', phone: '', address: '', postalCode: '', city: '', web: '', firstName: '', lastName: '', email: '', contactPhone: '', title: '' });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  // Direct mee regelen: site in Datto RMM en (optioneel) Full Service-contract als standaardcontract voor tickets
  const [rmm, setRmm] = useState(null);       // {configured}
  const eerste = new Date(); eerste.setDate(1);
  const [x, setX] = useState({ rmm: true, full: false });
  const [cfg, setCfg] = useState(STANDAARD_CFG);
  const [per, setPer] = useState({ start: eerste.toISOString().slice(0, 10), months: 12 });
  useEffect(() => { api('rmm.status', {}, { quiet: true }).then((s) => setRmm({ configured: !!s.configured })).catch(() => setRmm({ configured: false })); }, []);
  const ok = v.name.trim().length >= 2 && v.phone.trim() && v.firstName.trim() && v.lastName.trim();
  const veld = (k, l, w = 220, type = 'text') => <div><label className="f">{l}</label><input type={type} value={v[k]} onChange={z(k)} style={{ width: w }} /></div>;
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Building2 size={18} />Nieuwe klant</h3>
      <div className="hint" style={{ marginTop: 0 }}>Wordt in Autotask aangemaakt als <b>Customer</b>, met de contactpersoon als <b>primaire contactpersoon</b>. Het project komt daarna meteen op deze klant.</div>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>{veld('name', 'Bedrijfsnaam', 320)}{veld('phone', 'Telefoon (verplicht)', 180)}{veld('web', 'Website', 220)}</div>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>{veld('address', 'Adres', 260)}{veld('postalCode', 'Postcode', 120)}{veld('city', 'Plaats', 200)}</div>
      <label className="f" style={{ marginTop: 12 }}><b>Primaire contactpersoon</b></label>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>{veld('firstName', 'Voornaam', 180)}{veld('lastName', 'Achternaam', 200)}{veld('title', 'Functie', 180)}</div>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>{veld('email', 'E-mail', 260, 'email')}{veld('contactPhone', 'Telefoon', 180)}</div>
      <label className="f" style={{ marginTop: 12 }}><b>Direct mee regelen</b></label>
      <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer' }}><input type="checkbox" checked={x.rmm && !!rmm?.configured} disabled={!rmm?.configured} onChange={(e) => setX({ ...x, rmm: e.target.checked })} />
        <span><b>Site aanmaken in Datto RMM</b>{rmm && !rmm.configured && <span className="hint" style={{ margin: 0 }}> (Datto RMM is nog niet gekoppeld: Servicedesk &gt; Instellingen)</span>}</span></label>
      <div style={{ marginTop: 8 }}><b>Dienstverlening</b></div>
      <div className="btns" style={{ marginTop: 4 }}>
        <Btn s v={x.full ? 'p' : ''} onClick={() => setX({ ...x, full: true })}>Full Service-contractklant</Btn>
        <Btn s v={!x.full ? 'p' : ''} onClick={() => setX({ ...x, full: false })}>Geen Full Service</Btn>
      </div>
      {x.full && (
        <div className="card" style={{ padding: 10, marginTop: 6 }}>
          <div className="hint" style={{ marginTop: 0 }}>Recurring Service-contract <b>Full Service - {v.name.trim() || 'klantnaam'}</b> wordt het <b>standaardcontract</b> van de klant: alle servicedesktickets vallen eronder, behalve after hours / emergency.</div>
          <Samensteller cfg={cfg} onChange={setCfg} periode={per} onPeriode={setPer} />
        </div>)}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!ok} onClick={() => close({ ...Object.fromEntries(Object.entries(v).map(([k, w]) => [k, w.trim()])), rmm: x.rmm && !!rmm?.configured,
          full: x.full ? { cfg, ...per } : null })}>Klant aanmaken</button></div>
    </>);
}

// Klant aanmaken in Autotask, daarna (als gekozen) de site in Datto RMM en het Full Service-contract. Geeft {company, contact, done}.
export async function nieuweKlantMaken(r, omschrijving = '') {
  const { rmm, full, ...klant } = r;
  const x = await act('sa.bedrijf.nieuw', klant, { msg: 'Klant en contactpersoon aanmaken in Autotask...' });
  if (!x) return null;
  const done = [{ ok: true, t: `Klant ${x.company.name} met primaire contactpersoon ${x.contact.name} in Autotask` }];
  if (rmm) {
    const s = await act('rmm.site.nieuw', { name: x.company.name, description: omschrijving }, { msg: 'Site aanmaken in Datto RMM...' });
    done.push(s ? { ok: true, t: `Site ${s.site.name} ${s.exists ? 'bestond al' : 'aangemaakt'} in Datto RMM`, url: s.site.url } : { ok: false, t: 'Site in Datto RMM niet aangemaakt (zie melding)' });
  }
  if (full) {
    const c = await act('sa.contract.samenstellen', { companyId: x.company.id, companyName: x.company.name, ...full }, { msg: 'Full Service-contract samenstellen in Autotask...' });
    done.push(c ? { ok: !c.errors.length, t: `Full Service-contract (standaardcontract): ${c.calc.levelName}, € ${c.calc.monthly.toFixed(2)} per maand, setup € ${c.calc.setup.toFixed(2)}${c.excluded.length ? `, buiten het contract: ${c.excluded.join(', ')}` : ''}${c.errors.length ? `; let op: ${c.errors.join('; ')}` : ''}` }
      : { ok: false, t: 'Full Service-contract niet aangemaakt (zie melding)' });
  }
  toast(`Klant ${x.company.name} aangemaakt.`, 'g');
  return { ...x, done };
}

function KlantKlaar({ done }) {
  return (
    <div className="card" style={{ padding: 10, marginTop: 8, background: 'var(--acl)' }}>
      {done.map((d, i) => <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>{d.ok ? <CheckCircle2 size={14} color="var(--gr)" /> : <ThumbsDown size={14} color="var(--or)" />}<span>{d.t}</span>
        {d.url && <button className="linkknop" onClick={() => act('open.url', { url: d.url }, { nobusy: true, quiet: true })}>Openen</button>}</div>)}
    </div>);
}

async function losseKlant() {
  const r = await openModal((close) => <NieuweKlant naam="" close={close} />, { wide: true });
  if (!r) return;
  const x = await nieuweKlantMaken(r);
  if (x) openModal((close) => <><h3>Klant aangemaakt</h3><KlantKlaar done={x.done} /><div className="foot"><button className="btn p" onClick={() => close()}>Sluiten</button></div></>);
}

// Een opengeklikte kans: alles zien en bewerken (gegevens, status, notities, bijlagen) en het project maken
function KansPagina({ o, opt, d, beheerder, onTerug, onOpslaan, onBulk, onProjectMaken, onProject }) {
  const [sleutel, setSleutel] = useState(0);   // formulier opnieuw opbouwen na opslaan
  const opslaan = async (r) => {
    if (!r) { onTerug(); return; }
    if (await act('sa.opslaan', r, { msg: 'Kans opslaan in Autotask...' })) { toast('Kans bijgewerkt.', 'g'); onOpslaan(); setSleutel((x) => x + 1); }
  };
  return (
    <div className="mg klanten breed">
      <div className="btns" style={{ alignItems: 'center', marginBottom: 10 }}>
        <Btn s icon={ChevronLeft} onClick={onTerug}>Alle kansen</Btn>
        <h2 style={{ margin: '0 0 0 6px', flex: 1, minWidth: 0 }}>{o.title}</h2>
        {o.project ? <Chip k="g">project {o.project.number}</Chip> : o.final ? <Chip k="o">definitief</Chip> : <Chip>{o.status || 'open'}</Chip>}
        {d.canStatus && !o.final && <><Btn s icon={ThumbsDown} onClick={() => onBulk('lost')}>Verloren</Btn><Btn s icon={CheckCircle2} onClick={() => onBulk('final')}>Definitief</Btn></>}
        {d.canStatus && <Btn s icon={Trash2} onClick={() => onBulk('delete')}>Verwijderen</Btn>}
        {!o.project && (d.canProject ?? beheerder) && <Btn s v="p" icon={FolderPlus} onClick={onProjectMaken}>Project maken</Btn>}
        {o.project && onProject && <Btn s icon={BriefcaseBusiness} onClick={() => onProject(o.project.id)}>Naar project</Btn>}
      </div>
      <div className="sa-pagina">
        <div className="mg-kaart">
          <div className="hint" style={{ marginTop: 0 }}>{o.company}{o.contact ? ` · ${o.contact}` : ''} · {eur(o.amount)} · {o.probability}% · verwacht {datum(o.close)}{o.owner ? ` · eigenaar ${o.owner}` : ''}</div>
          {d.canEdit ? <KansVenster key={sleutel} o={o} opt={opt} close={opslaan} inline /> : <div className="pr-omschrijving">{o.description || 'Geen omschrijving.'}</div>}
        </div>
        <div><div className="mg-kaart" style={{ marginBottom: 12 }}><ContractKaart o={o} mag={d.canEdit} /></div><div className="mg-kaart"><KansDetail o={o} mag={d.canStatus} inline close={() => {}} /></div></div>
      </div>
    </div>);
}