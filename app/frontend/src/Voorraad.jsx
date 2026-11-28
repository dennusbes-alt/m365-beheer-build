// Voorraad: producten (merk, product, inkoop- en verkoopprijs) uit Autotask met het aantal op voorraad, de bestellijst
// (wat er besteld moet worden, voor sales duidelijk bovenaan) en producten op een ticket zetten.
import { useEffect, useState } from 'react';
import { CheckCircle2, Minus, Package, PackageCheck, PackagePlus, Pencil, Plus, RefreshCw, ShoppingCart, Trash2, Truck, Undo2 } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { AllesVink, Btn, Chip, Loading, SearchBox } from './ui.jsx';
import { nl } from './Grafiek.jsx';

export const eur = (v) => `€ ${nl(Number(v || 0), 2)}`;
const naam = (p) => `${p.brand ? `${p.brand} ` : ''}${p.name}`;
const dt = (s) => (s ? String(s).slice(0, 16).replace('T', ' ').split(' ').map((x, i) => (i ? x : x.split('-').reverse().join('-'))).join(' ') : '');

export default function Voorraad() {
  const [d, setD] = useState(null);
  const [q, setQ] = useState('');
  const [toon, setToon] = useState('alle');
  const [sel, setSel] = useState([]);
  const laad = (fresh) => api('vr.overzicht', { fresh: !!fresh }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, products: [], orders: [], totals: {} }));
  useEffect(() => { laad(false); }, []);
  if (!d) return <div className="mg klanten breed"><Loading text="Voorraad ophalen..." /></div>;
  const t = d.totals || {};
  const open = d.orders.filter((o) => o.status !== 'binnen');
  const binnen = d.orders.filter((o) => o.status === 'binnen').slice(-8).reverse();
  const lijst = d.products.filter((p) => (toon === 'op' ? p.stock > 0 : toon === 'leeg' ? p.stock <= 0 : true))
    .filter((p) => !q || `${p.brand} ${p.name} ${p.model} ${p.sku}`.toLowerCase().includes(q.toLowerCase()));

  const bewerk = async (p) => {
    const r = await openModal((close) => <ProductVenster p={p} close={close} />, { wide: true });
    if (r && await act('vr.product.opslaan', r, { msg: p ? 'Product opslaan in Autotask...' : 'Product toevoegen in Autotask...' })) { toast(p ? 'Product bijgewerkt.' : 'Product toegevoegd.', 'g'); laad(true); }
  };
  const weg = async (p) => {
    if (!await ask(`${naam(p)} uit de voorraadlijst halen?\n\nAutotask kan producten niet verwijderen; het product wordt inactief.`, 'Weghalen')) return;
    if (await act('vr.product.weg', { id: p.id }, { msg: 'Bijwerken...' })) laad(true);
  };
  const tel = async (p, delta) => {
    setD((x) => ({ ...x, products: x.products.map((y) => (y.id === p.id ? { ...y, stock: Math.max(0, y.stock + delta) } : y)) }));
    const r = await act('vr.voorraad', { id: p.id, delta }, { nobusy: true, quiet: true });
    if (!r) laad(true);
  };
  const zetAantal = async (p) => {
    const r = await openModal((close) => <AantalVenster p={p} close={close} />);
    if (r != null && await act('vr.voorraad', { id: p.id, stock: r }, { msg: 'Bijwerken...' })) laad(true);
  };
  const bestellen = async (p) => {
    const r = await openModal((close) => <BestelVenster p={p} close={close} />);
    if (r && await act('vr.bestellen', r, { msg: 'Op de bestellijst zetten...' })) { toast('Op de bestellijst gezet.', 'g'); laad(true); }
  };
  const besteld = async (ids, undo) => {
    if (await act('vr.besteld', { ids, undo: !!undo }, { msg: 'Bijwerken...' })) { setSel([]); laad(true); }
  };
  const ontvangen = async (o) => {
    const r = await openModal((close) => <BinnenVenster o={o} producten={d.products} close={close} />, { wide: true });
    if (!r) return;
    const x = await act('vr.binnen', { id: o.id, ...r }, { msg: 'Op voorraad zetten...' });
    if (x) { toast(x.ticket ? `Binnen en op ticket ${o.ticketNumber} gezet.` : 'Binnen en op voorraad gezet.', 'g'); laad(true); }
  };
  const bestellingWeg = async (o) => {
    if (!await ask(`${naam(o)} van de bestellijst halen?`, 'Weghalen')) return;
    if (await act('vr.bestelling.weg', { id: o.id }, { msg: 'Bijwerken...' })) laad(true);
  };

  return (
    <div className="mg klanten breed">
      <div className="mg-hero" style={{ marginTop: 0 }}>
        <div className="mg-top">
          <div><h2>Voorraad</h2><div className="mg-sub">Producten uit Autotask, aantallen op voorraad en wat er besteld moet worden</div></div>
          <div className="mg-acties">
            {d.canEdit && <Btn v="p" icon={Plus} onClick={() => bewerk(null)}>Nieuw product</Btn>}
            <Btn icon={ShoppingCart} onClick={() => bestellen(null)}>Iets laten bestellen</Btn>
            <Btn icon={RefreshCw} onClick={() => { setD(null); laad(true); }}>Vernieuwen</Btn>
          </div>
        </div>
        <div className="mg-kpis">
          <div className="mg-kpi"><div className="l">Te bestellen</div><div className="n" style={t.toOrder ? { color: 'var(--or)' } : undefined}>{t.toOrder || 0}</div><div className="s"><span>{t.ordered || 0} besteld, onderweg</span></div></div>
          <div className="mg-kpi"><div className="l">Producten</div><div className="n">{t.products || 0}</div><div className="s"><span>{t.inStock || 0} op voorraad</span></div></div>
          <div className="mg-kpi"><div className="l">Stuks op voorraad</div><div className="n">{t.units || 0}</div><div className="s"><span>alle producten samen</span></div></div>
          <div className="mg-kpi"><div className="l">Waarde (inkoop)</div><div className="n">{eur(t.value)}</div><div className="s"><span>excl. btw</span></div></div>
        </div>
      </div>
      {d.error && <Msg kind="warn">{d.error}</Msg>}

      {(
        <div className="mg-kaart vr-bestel">
          <div className="headrow" style={{ marginBottom: 8 }}><b style={{ display: 'flex', gap: 6, alignItems: 'center' }}><ShoppingCart size={16} /> Bestellijst: te bestellen en onderweg ({open.length})</b>
            {d.canEdit && <AllesVink ids={open.filter((o) => o.status === 'open').map((o) => o.id)} value={sel} onChange={setSel} label="Alles selecteren" />}</div>
          {d.canEdit && sel.length > 0 && <div className="sdq-bulk"><b>{sel.length} gekozen</b><Btn s v="p" icon={Truck} onClick={() => besteld(sel)}>Besteld</Btn></div>}
          {!open.length && <div className="hint" style={{ margin: 0 }}>Niets te bestellen. Collega's zetten hier wat er besteld moet worden (bij een ticket via Product &gt; Laten bestellen, of met Iets laten bestellen hierboven); sales bestelt het en zet het op Besteld; wie het ontvangt meldt het als Binnen.</div>}
          {open.map((o) => (
            <div key={o.id} className="sdq-rij" style={{ alignItems: 'center' }}>
              {d.canEdit && o.status === 'open' ? <input type="checkbox" checked={sel.includes(o.id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, o.id] : s.filter((x) => x !== o.id)))} /> : <span style={{ width: 13 }} />}
              <div className="sdq-hoofd" style={{ cursor: 'default' }}>
                <div className="sdq-titel"><b>{o.qty}x {naam(o)}</b> {o.status === 'besteld' ? <Chip k="g">besteld{o.orderedAt ? ` ${dt(o.orderedAt)}` : ''}</Chip> : <Chip k="o">nog bestellen</Chip>}
                  {!o.productId && <Chip k="mu" title="Bestaat nog niet in de productlijst; bij binnenkomst worden de prijzen gevraagd">nieuw product</Chip>}</div>
                <div className="sdq-meta">
                  <span>gevraagd door {o.by || 'onbekend'} op {dt(o.at)}</span>
                  {o.ticketNumber && <span>voor ticket <b>{o.ticketNumber}</b>{o.company ? ` (${o.company})` : ''}</span>}
                  {o.orderedBy && <span>besteld door {o.orderedBy}</span>}
                  {o.note && <span>{o.note}</span>}
                </div>
              </div>
              <div className="btns" style={{ margin: 0 }}>
                {d.canEdit && o.status === 'open' && <Btn s v="p" icon={Truck} onClick={() => besteld([o.id])}>Besteld</Btn>}
                {d.canEdit && o.status === 'besteld' && <Btn s icon={Undo2} onClick={() => besteld([o.id], true)} title="Terug naar te bestellen" />}
                <Btn s icon={PackageCheck} onClick={() => ontvangen(o)} title="Binnengekomen (bijv. met de post): op voorraad en zo nodig op het ticket">Binnen</Btn>
                <Btn s icon={Trash2} onClick={() => bestellingWeg(o)} title="Van de bestellijst halen" />
              </div>
            </div>))}
        </div>)}

      <div className="mg-kaart">
        <div className="headrow" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <div className="btns">{[['alle', `Alle (${d.products.length})`], ['op', 'Op voorraad'], ['leeg', 'Niet op voorraad']].map(([k, l]) => <Btn key={k} s v={toon === k ? 'p' : ''} onClick={() => setToon(k)}>{l}</Btn>)}</div>
          <div style={{ width: 280 }}><SearchBox value={q} onChange={setQ} placeholder="Zoek merk, product of artikelnummer..." /></div>
        </div>
        <table style={{ width: '100%' }}>
          <thead><tr><th>Merk</th><th>Product</th><th>Type / artikelnr.</th><th style={{ textAlign: 'right' }}>Inkoop</th><th style={{ textAlign: 'right' }}>Verkoop</th>
            <th style={{ textAlign: 'right' }}>Marge</th><th style={{ textAlign: 'center' }}>Op voorraad</th><th style={{ textAlign: 'right' }}>Acties</th></tr></thead>
          <tbody>{lijst.map((p) => (
            <tr key={p.id}>
              <td>{p.brand || '-'}</td>
              <td><b>{p.name}</b>{p.description && <div className="hint" style={{ margin: 0, maxWidth: 320, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.description}</div>}</td>
              <td>{[p.model, p.sku].filter(Boolean).join(' · ') || '-'}</td>
              <td style={{ textAlign: 'right' }}>{eur(p.cost)}</td>
              <td style={{ textAlign: 'right' }}><b>{eur(p.price)}</b></td>
              <td style={{ textAlign: 'right' }}>{p.price ? `${nl(((p.price - p.cost) / p.price) * 100, 0)}%` : '-'}</td>
              <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }}>
                <span className="vr-teller">
                  <button type="button" onClick={() => tel(p, -1)} disabled={p.stock <= 0} title="Eén eraf"><Minus size={13} /></button>
                  <b className={p.stock > 0 ? '' : 'leeg'} onClick={() => zetAantal(p)} title="Aantal invullen">{p.stock}</b>
                  <button type="button" onClick={() => tel(p, 1)} title="Eén erbij"><Plus size={13} /></button>
                </span>
              </td>
              <td style={{ textAlign: 'right' }}>
                <div className="btns" style={{ justifyContent: 'flex-end', margin: 0 }}>
                  <Btn s icon={ShoppingCart} onClick={() => bestellen(p)} title="Op de bestellijst" />
                  {d.canEdit && <Btn s icon={Pencil} onClick={() => bewerk(p)} title="Bewerken" />}
                  {d.canEdit && <Btn s icon={Trash2} onClick={() => weg(p)} title="Uit de lijst (inactief)" />}
                </div>
              </td>
            </tr>))}</tbody>
        </table>
        {!lijst.length && <div className="hint" style={{ padding: 10 }}>{d.products.length ? 'Geen producten in deze selectie.' : 'Nog geen producten. Voeg ze toe met Nieuw product.'}</div>}
      </div>

      {binnen.length > 0 && (
        <div className="mg-kaart">
          <b style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}><PackageCheck size={16} /> Laatst binnengekomen</b>
          {binnen.map((o) => <div key={o.id} className="hint" style={{ margin: '2px 0' }}>{dt(o.receivedAt)} · {o.qty}x {naam(o)}{o.receivedBy ? ` · binnen gemeld door ${o.receivedBy}` : ''}{o.ticketNumber ? ` · ticket ${o.ticketNumber}` : ''}</div>)}
        </div>)}
    </div>);
}

function ProductVenster({ p, close }) {
  const [v, setV] = useState(p ? { brand: p.brand, name: p.name, model: p.model, sku: p.sku, cost: p.cost, price: p.price, description: p.description, stock: p.stock }
    : { brand: '', name: '', model: '', sku: '', cost: '', price: '', description: '', stock: 0 });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  const marge = Number(v.price) ? ((Number(v.price) - Number(v.cost || 0)) / Number(v.price)) * 100 : null;
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Package size={18} />{p ? 'Product wijzigen' : 'Nieuw product'}</h3>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Merk</label><input autoFocus value={v.brand} onChange={z('brand')} placeholder="Bijv. HP" style={{ width: 180 }} /></div>
        <div style={{ flex: 1, minWidth: 240 }}><label className="f">Productnaam</label><input value={v.name} onChange={z('name')} placeholder="Bijv. EliteBook 840 G11, 16 GB, 512 GB" style={{ width: '100%' }} /></div>
      </div>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Type (fabrikant)</label><input value={v.model} onChange={z('model')} style={{ width: 200 }} /></div>
        <div><label className="f">Artikelnummer (SKU)</label><input value={v.sku} onChange={z('sku')} style={{ width: 180 }} /></div>
      </div>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Inkoopprijs (excl. btw)</label><input type="number" step="0.01" value={v.cost} onChange={z('cost')} style={{ width: 150 }} /></div>
        <div><label className="f">Verkoopprijs (excl. btw)</label><input type="number" step="0.01" value={v.price} onChange={z('price')} style={{ width: 150 }} /></div>
        <div><label className="f">Op voorraad</label><input type="number" min={0} value={v.stock} onChange={z('stock')} style={{ width: 110 }} /></div>
        {marge != null && <div style={{ alignSelf: 'flex-end', paddingBottom: 8 }}>Marge <b>{nl(marge, 0)}%</b> ({eur(Number(v.price) - Number(v.cost || 0))})</div>}
      </div>
      <label className="f">Omschrijving (optioneel)</label>
      <textarea rows={3} value={v.description} onChange={z('description')} />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!v.name.trim()} onClick={() => close({ ...(p ? { id: p.id } : {}), brand: v.brand.trim(), name: v.name.trim(), model: v.model.trim(), sku: v.sku.trim(),
          cost: Number(v.cost || 0), price: Number(v.price || 0), description: v.description, stock: Math.max(0, parseInt(v.stock, 10) || 0) })}>{p ? 'Opslaan' : 'Toevoegen'}</button></div>
    </>);
}

function AantalVenster({ p, close }) {
  const [n, setN] = useState(p.stock);
  return (
    <>
      <h3>Aantal op voorraad</h3>
      <div className="hint" style={{ marginTop: 0 }}>{naam(p)}</div>
      <input type="number" min={0} autoFocus value={n} onChange={(e) => setN(e.target.value)} style={{ width: 120 }}
        onKeyDown={(e) => { if (e.key === 'Enter') close(Math.max(0, parseInt(n, 10) || 0)); }} />
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button><button className="btn p" onClick={() => close(Math.max(0, parseInt(n, 10) || 0))}>Opslaan</button></div>
    </>);
}

// Op de bestellijst: een bestaand product (p) of iets nieuws; optioneel voor een ticket
export function BestelVenster({ p, ticket, close, standaard }) {
  const [v, setV] = useState({ brand: p?.brand || '', name: p?.name || standaard || '', qty: 1, note: '' });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><ShoppingCart size={18} />Laten bestellen</h3>
      <div className="hint" style={{ marginTop: 0 }}>Komt op de bestellijst bij Voorraad; sales ziet het direct en bestelt het.{ticket ? <> Als het binnen is, komt het vanzelf op ticket <b>{ticket.number}</b>.</> : null}</div>
      {p ? <div style={{ margin: '8px 0' }}><b>{naam(p)}</b>{p.stock > 0 ? ` · nog ${p.stock} op voorraad` : ' · niet op voorraad'}</div> : (
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Merk</label><input value={v.brand} onChange={z('brand')} style={{ width: 160 }} /></div>
          <div style={{ flex: 1, minWidth: 240 }}><label className="f">Wat moet er besteld worden?</label><input autoFocus value={v.name} onChange={z('name')} placeholder="Bijv. USB-C dockingstation" style={{ width: '100%' }} /></div>
        </div>)}
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div><label className="f">Aantal</label><input type="number" min={1} value={v.qty} onChange={z('qty')} style={{ width: 90 }} /></div>
        <div style={{ flex: 1, minWidth: 240 }}><label className="f">Opmerking (optioneel)</label><input value={v.note} onChange={z('note')} placeholder="Bijv. liefst voor vrijdag, of een link naar de leverancier" style={{ width: '100%' }} /></div>
      </div>
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={!p && !v.name.trim()} onClick={() => close({ productId: p?.id || null, brand: v.brand.trim(), name: v.name.trim(), qty: Math.max(1, parseInt(v.qty, 10) || 1),
          note: v.note.trim(), ticketId: ticket?.id || null, ticketNumber: ticket?.number || null, company: ticket?.company || null })}>Op de bestellijst</button></div>
    </>);
}

function BinnenVenster({ o, producten, close }) {
  const bestaand = o.productId ? producten.find((p) => p.id === o.productId) : null;
  const [koppel, setKoppel] = useState(bestaand ? String(bestaand.id) : '');
  const [v, setV] = useState({ qty: o.qty, brand: o.brand || '', name: o.name || '', model: '', sku: '', cost: '', price: '' });
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  const nieuw = !koppel;
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><PackageCheck size={18} />Binnengekomen</h3>
      <div className="hint" style={{ marginTop: 0 }}>{o.qty}x {naam(o)}{o.ticketNumber ? <> · gaat direct op ticket <b>{o.ticketNumber}</b>{o.company ? ` (${o.company})` : ''}</> : ' · gaat op voorraad'}</div>
      <label className="f">Aantal binnen</label><input type="number" min={1} value={v.qty} onChange={z('qty')} style={{ width: 90 }} />
      {!bestaand && <>
        <label className="f">Product</label>
        <select value={koppel} onChange={(e) => setKoppel(e.target.value)} style={{ width: 'auto', minWidth: 320 }}>
          <option value="">Nieuw product aanmaken</option>{producten.map((p) => <option key={p.id} value={p.id}>{naam(p)}</option>)}
        </select>
        {nieuw && <>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <div><label className="f">Merk</label><input value={v.brand} onChange={z('brand')} style={{ width: 160 }} /></div>
            <div style={{ flex: 1, minWidth: 220 }}><label className="f">Productnaam</label><input value={v.name} onChange={z('name')} style={{ width: '100%' }} /></div>
          </div>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <div><label className="f">Inkoopprijs (excl. btw)</label><input type="number" step="0.01" value={v.cost} onChange={z('cost')} style={{ width: 150 }} /></div>
            <div><label className="f">Verkoopprijs (excl. btw)</label><input type="number" step="0.01" value={v.price} onChange={z('price')} style={{ width: 150 }} /></div>
            <div><label className="f">Artikelnummer</label><input value={v.sku} onChange={z('sku')} style={{ width: 160 }} /></div>
          </div>
          <div className="hint">Het product komt in Autotask (zodat het op tickets en de factuur kan).</div>
        </>}
      </>}
      <div className="foot"><button className="btn" onClick={() => close(null)}>Annuleren</button>
        <button className="btn p" disabled={nieuw && !bestaand && (!v.name.trim() || v.price === '')}
          onClick={() => close({ qty: Math.max(1, parseInt(v.qty, 10) || 1), ...(bestaand ? {} : koppel ? { productId: +koppel } : { brand: v.brand.trim(), name: v.name.trim(), sku: v.sku.trim(), cost: Number(v.cost || 0), price: Number(v.price || 0) }) })}>
          <CheckCircle2 size={14} /> Binnen melden</button></div>
    </>);
}

// ================================================================ product(en) op een ticket
export async function productenOpTicket(t) {
  return openModal((close) => <TicketProducten t={t} close={close} />, { wide: true });
}

function TicketProducten({ t, close }) {
  const [d, setD] = useState(null);
  const [q, setQ] = useState('');
  const [kies, setKies] = useState(null);   // {p, qty, price}
  const [bestel, setBestel] = useState(null);
  const [gewijzigd, setGewijzigd] = useState(false);
  const laad = () => api('vr.ticket', { ticketId: t.id }, { quiet: true }).then(setD).catch((e) => setD({ error: e.message, charges: [], products: [], orders: [] }));
  useEffect(() => { laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const lijst = (d?.products || []).filter((p) => !q || `${p.brand} ${p.name} ${p.model} ${p.sku}`.toLowerCase().includes(q.toLowerCase())).slice(0, 40);
  const toevoegen = async (force) => {
    const x = await act('vr.ticket.product', { ticketId: t.id, ticketNumber: t.number, productId: kies.p.id, qty: Math.max(1, parseInt(kies.qty, 10) || 1),
      price: kies.price === '' ? null : Number(kies.price), force: !!force }, { msg: 'Product op het ticket zetten...' });
    if (x) { toast(`${naam(kies.p)} op het ticket gezet (${eur(x.amount)}).`, 'g'); setKies(null); setQ(''); setGewijzigd(true); laad(); }
  };
  const bestellen = async (r) => {
    setBestel(null);
    if (r && await act('vr.bestellen', r, { msg: 'Op de bestellijst zetten...' })) { toast('Op de bestellijst gezet. Sales bestelt het; als het binnen is komt het op dit ticket.', 'g'); laad(); }
  };
  const weg = async (ch) => {
    if (!await ask(`${ch.name} van het ticket halen? Het gaat terug op voorraad.`, 'Weghalen')) return;
    if (await act('vr.ticket.product.weg', { ticketId: t.id, id: ch.id }, { msg: 'Bijwerken...' })) { setGewijzigd(true); laad(); }
  };
  const totaal = (d?.charges || []).reduce((s, c) => s + (c.billable ? c.amount : 0), 0);
  const tekort = kies && kies.p.stock < (parseInt(kies.qty, 10) || 1);
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><PackagePlus size={18} />Product op ticket {t.number}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{t.title}{t.company ? ` · ${t.company}` : ''}. Het product wordt gefactureerd (verkoopprijs) samen met de uren, ook als de uren onder een contract vallen.</div>
      {!d ? <Loading text="Producten ophalen..." /> : <>
        {d.error && <Msg kind="warn">{d.error}</Msg>}
        {d.charges.length > 0 && (
          <div className="card" style={{ padding: 10, marginBottom: 10 }}>
            <b>Op dit ticket</b>
            {d.charges.map((c) => (
              <div key={c.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0', borderTop: '1px solid var(--bd)' }}>
                <span style={{ flex: 1 }}>{nl(c.qty, 0)}x {c.name}{!c.billable && <Chip k="mu">niet factureerbaar</Chip>}{c.billed && <Chip k="g">gefactureerd</Chip>}</span>
                <b>{eur(c.amount)}</b>{!c.billed && <Btn s icon={Trash2} onClick={() => weg(c)} title="Van het ticket halen" />}
              </div>))}
            <div style={{ textAlign: 'right', marginTop: 4 }}>Producten samen <b>{eur(totaal)}</b> excl. btw</div>
          </div>)}
        {d.orders.length > 0 && <Msg kind="info">Besteld voor dit ticket: {d.orders.map((o) => `${o.qty}x ${naam(o)} (${o.status === 'besteld' ? 'besteld' : 'nog bestellen'})`).join(', ')}</Msg>}
        {bestel ? <div className="card" style={{ padding: 12 }}><BestelVenster p={bestel.p} standaard={bestel.q} ticket={t} close={bestellen} /></div>
          : kies ? (
            <div className="card" style={{ padding: 12 }}>
              <b>{naam(kies.p)}</b> <span className="hint">· {kies.p.stock > 0 ? `${kies.p.stock} op voorraad` : 'niet op voorraad'}</span>
              <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
                <div><label className="f">Aantal</label><input type="number" min={1} autoFocus value={kies.qty} onChange={(e) => setKies({ ...kies, qty: e.target.value })} style={{ width: 90 }} /></div>
                <div><label className="f">Verkoopprijs per stuk</label><input type="number" step="0.01" value={kies.price} onChange={(e) => setKies({ ...kies, price: e.target.value })} style={{ width: 140 }} /></div>
                <div style={{ alignSelf: 'flex-end', paddingBottom: 8 }}>Samen <b>{eur((parseInt(kies.qty, 10) || 1) * Number(kies.price || 0))}</b></div>
              </div>
              {tekort && <Msg kind="warn">Niet genoeg op voorraad. Zet het op de bestellijst (het komt dan vanzelf op dit ticket als het binnen is), of voeg het toch toe als het er wel ligt.</Msg>}
              <div className="btns" style={{ marginTop: 8 }}>
                <Btn s onClick={() => setKies(null)}>Terug</Btn>
                {tekort ? <><Btn s v="p" icon={ShoppingCart} onClick={() => { setBestel({ p: kies.p }); setKies(null); }}>Laten bestellen</Btn><Btn s onClick={() => toevoegen(true)}>Toch toevoegen</Btn></>
                  : <Btn s v="p" icon={PackagePlus} onClick={() => toevoegen(false)}>Op het ticket</Btn>}
              </div>
            </div>) : <>
            <SearchBox value={q} onChange={setQ} placeholder="Zoek product uit de voorraad..." />
            <div className="list" style={{ maxHeight: 280, marginTop: 6 }}>
              {lijst.map((p) => (
                <div key={p.id} className="li" onClick={() => setKies({ p, qty: 1, price: p.price })}>
                  <span className="m"><b>{naam(p)}</b>{p.model || p.sku ? <span className="hint" style={{ margin: 0 }}> · {[p.model, p.sku].filter(Boolean).join(' · ')}</span> : null}</span>
                  <span>{eur(p.price)}</span>{p.stock > 0 ? <Chip k="g">{p.stock} op voorraad</Chip> : <Chip k="o">niet op voorraad</Chip>}
                </div>))}
              {!lijst.length && <div className="li empty">{q ? 'Niet gevonden in de voorraad.' : 'Nog geen producten.'}</div>}
            </div>
            <div className="btns" style={{ marginTop: 8 }}><Btn s icon={ShoppingCart} onClick={() => setBestel({ p: null, q })}>Staat er niet bij: laten bestellen</Btn></div>
          </>}
      </>}
      <div className="foot"><button className="btn p" onClick={() => close(gewijzigd)}>Klaar</button></div>
    </>);
}
