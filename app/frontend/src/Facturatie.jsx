// Facturatie (alleen wie facturen goedkeurt): uren buiten de full-service-contracten per klant, hoogste bedrag bovenaan.
// Goedkeuren -> in Exact verwerken -> afvinken (verdwijnt uit de lijst). PDF-specificatie per klant.
import { Fragment, useEffect, useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, Download, ExternalLink, FileText, History, Receipt, RefreshCw, Undo2 } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { Btn, Chip, Loading, SearchBox, csv } from './ui.jsx';
import { nl } from './Grafiek.jsx';

const eur = (v) => `€ ${nl(v, 2)}`;
const datum = (s) => (s ? String(s).slice(0, 10).split('-').reverse().join('-') : '-');
const openUrl = (u) => u && act('open.url', { url: u }, { nobusy: true, quiet: true });

export default function Facturatie() {
  const [d, setD] = useState(null);
  const [dagen, setDagen] = useState(365);
  const [wip, setWip] = useState(false);   // ook uren op tickets die nog openstaan (zit nog niet in Autotask Approve & Post)
  const [open, setOpen] = useState({});
  const [q, setQ] = useState('');
  const [toon, setToon] = useState('alle');
  const [hist, setHist] = useState(false);
  const laad = (fresh, dg = dagen) => api('fa.overzicht', { days: dg, fresh: !!fresh, wip }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, customers: [] }));
  useEffect(() => { laad(false); }, [wip]); // eslint-disable-line react-hooks/exhaustive-deps

  const hero = (inhoud) => (
    <div className="mg-hero" style={{ marginTop: 0 }}>
      <div className="mg-top">
        <div><h2>Facturatie</h2><div className="mg-sub">Uurtje-factuurtje buiten de full-service-contracten en tickets op Ready to Invoice · goedkeuren, in Exact verwerken, afvinken{d && d.at ? ` · stand ${d.at}` : ''}</div></div>
        <div className="mg-acties">
          <select value={dagen} onChange={(e) => { setDagen(+e.target.value); setD(null); laad(false, +e.target.value); }} style={{ width: 'auto' }}>
            {[90, 180, 365].map((v) => <option key={v} value={v}>Werk van de laatste {v} dagen</option>)}
          </select>
          {d && d.customers && d.customers.length > 0 && <Btn icon={Download} onClick={() => exporteer(d)}>CSV</Btn>}
          <Btn icon={History} onClick={() => setHist(!hist)}>Verwerkt</Btn>
          <Btn icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
        </div>
      </div>
      {inhoud}
    </div>);
  if (!d) return <div className="mg klanten breed">{hero(null)}<Loading text="Factureerbare uren ophalen uit Autotask..." /></div>;
  const t = d.totals || { customers: 0, subtotal: 0, total: 0, hours: 0, approved: 0 };
  const goed = (k) => k.approved && !k.approved.changed;
  const lijst = (d.customers || []).filter((k) => (toon === 'alle' ? true : toon === 'goed' ? goed(k) : !goed(k)))
    .filter((k) => !q || k.name.toLowerCase().includes(q.toLowerCase()));

  const goedkeuren = async (k, undo) => {
    if (await act('fa.goedkeuren', { companyId: k.id, days: dagen, wip, undo: !!undo }, { msg: undo ? 'Goedkeuring intrekken...' : 'Goedkeuren...' })) {
      toast(undo ? `Goedkeuring van ${k.name} ingetrokken.` : `${k.name} goedgekeurd: ${eur(k.total)}.`, 'g'); laad(true);
    }
  };
  const verwerkt = async (k) => {
    const r = await openModal((close) => <Verwerkt k={k} close={close} />);
    if (!r) return;
    const x = await act('fa.verwerkt', { companyId: k.id, days: dagen, wip, ...r }, { msg: 'Afvinken...' });
    if (x) { toast(`${k.name} afgevinkt als verwerkt in Exact${x.closed ? `; ${x.closed} ticket(s) op Complete` : ''}.`, 'g'); laad(true); }
  };
  const pdf = (k) => act('fa.pdf', { companyId: k.id, days: dagen, wip }, { msg: 'Factuurspecificatie opstellen...' });
  const terug = async (b) => {
    if (!await ask(`De factuur van ${b.name} (${eur(b.total)}, ${b.at.replace('T', ' ')}) terugzetten in de lijst?`, 'Terugzetten')) return;
    if (await act('fa.terug', { id: b.id }, { msg: 'Terugzetten...' })) { toast('Teruggezet in de lijst.', 'g'); laad(true); }
  };

  return (
    <div className="mg klanten breed">
      {hero(
        <div className="mg-kpis">
          <div className="mg-kpi"><div className="l">Approve & Post (excl. btw)</div><div className="n">{eur(t.subtotal)}</div><div className="s"><span>{eur(t.total)} incl. btw</span></div></div>
          <div className="mg-kpi"><div className="l">Klanten</div><div className="n">{nl(t.customers)}</div><div className="s"><span>{nl(t.approved)} goedgekeurd</span></div></div>
          <div className="mg-kpi"><div className="l">Uren</div><div className="n">{nl(t.hours, 1)}</div><div className="s"><span>buiten contract</span></div></div>
        </div>)}
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      {d.postedKnown === false && <Msg kind="warn">Autotask gaf niet door welke uren al zijn goedgekeurd en geboekt (BillingItems); er kunnen al gefactureerde uren tussen staan.</Msg>}
      {d.postedKnown !== false && d.postedHours > 0 && <div className="hint" style={{ margin: '0 0 10px' }}>Niet getoond: {nl(d.postedHours, 1)} uur die in Autotask al is goedgekeurd en geboekt (Approve and Post) of gefactureerd.</div>}
      {d.wip && (d.wip.hours > 0 || d.inclWip) && <div className="hint" style={{ margin: '0 0 10px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        {d.inclWip ? <span>Inclusief onderhanden werk: uren op tickets die nog niet zijn afgerond.</span> : <span>Onderhanden (nog niet in Approve & Post): <b>{nl(d.wip.hours, 1)} uur</b> ({eur(d.wip.amount)}) op {d.wip.tickets} ticket(s) die nog niet zijn afgerond. Autotask zet ticketuren pas klaar als het ticket af is.</span>}
        <Btn s onClick={() => { setD(null); setWip(!wip); }}>{d.inclWip ? 'Alleen Approve & Post' : 'Onderhanden ook tonen'}</Btn></div>}
      {d.rtiTotal > 0 && <div className="hint" style={{ margin: '0 0 10px' }}>Ready to Invoice (wijzigingen): <b>{d.rtiTotal}</b> ticket(s), per klant zichtbaar bij het uitklappen.</div>}
      {d.invoiceStatus === false && <Msg kind="info">In Autotask is geen status 'Ready to Invoice' gevonden; alleen uren buiten contract worden getoond.</Msg>}

      {hist && (
        <div className="mg-kaart">
          <h3><span><History size={17} />Verwerkt in Exact (laatste 30)</span></h3>
          {(d.history || []).length ? (
            <table style={{ width: '100%' }}>
              <thead><tr><th>Klant</th><th>Verwerkt</th><th>Door</th><th>Referentie</th><th style={{ textAlign: 'right' }}>Totaal</th><th /></tr></thead>
              <tbody>{d.history.map((b) => (
                <tr key={b.id}><td><b>{b.name}</b></td><td>{b.at.replace('T', ' ')}</td><td>{b.by}</td><td>{b.ref || '-'}</td><td style={{ textAlign: 'right' }}>{eur(b.total)}</td>
                  <td style={{ textAlign: 'right' }}><Btn s icon={Undo2} onClick={() => terug(b)}>Terugzetten</Btn></td></tr>))}</tbody>
            </table>) : <div className="hint">Nog niets verwerkt.</div>}
        </div>)}

      <div className="mg-kaart">
        <div className="headrow" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <div className="btns">
            {[['alle', `Alle (${(d.customers || []).length})`], ['open', 'Nog goedkeuren'], ['goed', 'Goedgekeurd, nog naar Exact']].map(([k, l]) => (
              <Btn key={k} s v={toon === k ? 'p' : ''} onClick={() => setToon(k)}>{l}</Btn>))}
          </div>
          <div style={{ width: 260 }}><SearchBox value={q} onChange={setQ} placeholder="Zoek klant..." /></div>
        </div>
        <table style={{ width: '100%' }}>
          <thead><tr><th style={{ width: 26 }} /><th>Klant</th><th style={{ textAlign: 'right' }}>Uren</th><th style={{ textAlign: 'right' }}>Excl. btw</th>
            <th style={{ textAlign: 'right' }}>Totaal factuur</th><th>Status</th><th style={{ textAlign: 'right' }}>Acties</th></tr></thead>
          <tbody>{lijst.map((k) => (
            <Fragment key={k.id}>
              <tr className="klikrij" onClick={() => setOpen({ ...open, [k.id]: !open[k.id] })}>
                <td>{open[k.id] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</td>
                <td><b>{k.name}</b><div className="hint" style={{ margin: 0 }}>{k.lines.length} regel(s) · {k.tickets.length} ticket(s){k.rtiCount ? ` · ${k.rtiCount} op Ready to Invoice` : ''}{k.noRate ? ` · ${k.noRate} zonder tarief` : ''}</div></td>
                <td style={{ textAlign: 'right' }}>{nl(k.hours, 2)}</td>
                <td style={{ textAlign: 'right' }}>{eur(k.subtotal)}</td>
                <td style={{ textAlign: 'right' }}><b style={{ fontSize: 15 }}>{eur(k.total)}</b></td>
                <td>{goed(k) ? <Chip k="g" title={`Door ${k.approved.by} op ${k.approved.at.replace('T', ' ')}`}>goedgekeurd · {k.approved.by}</Chip>
                  : k.approved ? <Chip k="o" title="Er zijn regels bijgekomen of weggevallen">gewijzigd na goedkeuring</Chip> : <Chip k="mu">nog goedkeuren</Chip>}</td>
                <td style={{ textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                  <div className="btns" style={{ justifyContent: 'flex-end', margin: 0 }}>
                    <Btn s icon={FileText} onClick={() => pdf(k)} title="Factuurspecificatie als PDF">PDF</Btn>
                    {!goed(k) ? <Btn s v="p" icon={CheckCircle2} onClick={() => goedkeuren(k)}>Goedkeuren</Btn>
                      : <><Btn s icon={Undo2} onClick={() => goedkeuren(k, true)} title="Goedkeuring intrekken" />
                        <Btn s v="p" icon={Receipt} onClick={() => verwerkt(k)}>Verwerkt in Exact</Btn></>}
                  </div>
                </td>
              </tr>
              {open[k.id] && (
                <tr><td /><td colSpan={6} style={{ background: 'var(--bg)' }}>
                  {k.lines.length > 0 && (
                    <table style={{ width: '100%', margin: '6px 0' }}>
                      <thead><tr><th>Datum</th><th>Ticket</th><th>Werkzaamheden</th><th>Medewerker</th><th style={{ textAlign: 'right' }}>Uren</th>
                        <th style={{ textAlign: 'right' }}>Tarief</th><th style={{ textAlign: 'right' }}>Bedrag</th></tr></thead>
                      <tbody>{k.lines.map((l) => (
                        <tr key={l.id}><td>{datum(l.date)}</td><td>{l.ref}</td><td><b>{l.title}</b>{l.notes && <div className="hint" style={{ margin: 0 }}>{l.notes}</div>}</td>
                          <td>{l.employee}{l.level && <> <Chip k={l.level === 'L1' ? 'g' : ''}>{l.level}</Chip></>}</td>
                          <td style={{ textAlign: 'right' }}>{l.kind === 'product' ? `${nl(l.qty, 0)} st` : l.kind === 'fixed' ? 'vast' : nl(l.hours, 2)}</td><td style={{ textAlign: 'right' }}>{l.rate ? eur(l.rate) : <Chip k="o">geen tarief</Chip>}</td>
                          <td style={{ textAlign: 'right' }}>{eur(l.amount)}</td></tr>))}</tbody>
                    </table>)}
                  {k.tickets.filter((x) => x.rti).length > 0 && (
                    <div style={{ margin: '6px 0' }}><b>Op Ready to Invoice</b> (bijv. licentiewijzigingen; bedrag zelf in Exact):
                      {k.tickets.filter((x) => x.rti).map((x) => <div key={x.id} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span>{x.number} · {x.title}</span>{x.url && <Btn s icon={ExternalLink} onClick={() => openUrl(x.url)} title="Openen in Autotask" />}</div>)}</div>)}
                  <div className="hint" style={{ margin: '6px 0 0' }}>Subtotaal {eur(k.subtotal)} · btw 21% {eur(k.vat)} · totaal {eur(k.total)}</div>
                </td></tr>)}
            </Fragment>))}</tbody>
        </table>
        {!lijst.length && <div className="hint" style={{ padding: 10 }}>{(d.customers || []).length ? 'Geen klanten in deze selectie.' : 'Er staat niets klaar om te factureren.'}</div>}
      </div>
    </div>);
}

function Verwerkt({ k, close }) {
  const [ref, setRef] = useState('');
  const [sluit, setSluit] = useState(true);
  const rti = k.tickets.filter((t) => t.rti).length;
  return (
    <>
      <h3>Verwerkt in Exact · {k.name}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{eur(k.total)} incl. btw · {k.lines.length} regel(s). Na afvinken verdwijnt deze klant uit de lijst (terugzetten kan via Verwerkt).</div>
      <label className="f">Factuurnummer in Exact (optioneel)</label>
      <input value={ref} onChange={(e) => setRef(e.target.value)} autoFocus placeholder="Bijv. 2026-00123" />
      {rti > 0 && <label className="chk" style={{ marginTop: 10 }}><input type="checkbox" checked={sluit} onChange={(e) => setSluit(e.target.checked)} />
        <span>{rti} ticket(s) op Ready to Invoice in Autotask op Complete zetten</span></label>}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" onClick={() => close({ ref: ref.trim(), closeTickets: sluit })}>Afvinken</button></div>
    </>);
}

function exporteer(d) {
  const rijen = [['Klant', 'Datum', 'Ticket', 'Werkzaamheden', 'Medewerker', 'Niveau', 'Uren', 'Tarief', 'Bedrag excl. btw', 'Goedgekeurd door']];
  d.customers.forEach((k) => k.lines.forEach((l) => rijen.push([k.name, datum(l.date), l.ref, `${l.title}${l.notes ? ': ' + l.notes : ''}`, l.employee, l.level,
    String(l.hours).replace('.', ','), String(l.rate).replace('.', ','), String(l.amount).replace('.', ','), k.approved ? k.approved.by : ''])));
  csv('facturatie.csv', rijen);
}
