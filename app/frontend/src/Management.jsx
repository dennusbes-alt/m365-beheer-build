// Management (alleen directie): organisatiebrede inzichten en per klant een kwartaalrapportage in gewone taal.
// Eigen uitstraling (hero + grafieken uit Grafiek.jsx); export naar PDF (organisatie of klant) en CSV.
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, BarChart3, Building2, CheckCircle2, Clock, DatabaseBackup, Download, FileText, Gauge, Info, KeyRound, MailCheck,
  RefreshCw, Search, Ticket, Users } from 'lucide-react';
import { act, api } from './api.js';
import { toast } from './overlays.jsx';
import { Btn, Loading, csv } from './ui.jsx';
import { Donut, Kolommen, Lijn, Meter, PALET, Spark, Staven, nl } from './Grafiek.jsx';

const pc = (v) => (v == null ? '-' : `${String(v).replace('.', ',')}%`);
const ST = { ok: ['In orde', 'gr'], warn: ['Aandacht', 'or'], err: ['Actie nodig', 'rd'], unknown: ['Onbekend', 'mu'], paused: ['Gepauzeerd', 'mu'] };
const NIVEAU = { err: ['rd', 'Kritiek'], warn: ['or', 'Aandacht'], info: ['hd', 'Info'] };
const uurNl = (h) => nl(h, h && h % 1 ? 1 : 0);
const duur = (h) => {
  if (h == null) return '-';
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 24) return `${nl(h, h < 10 && h % 1 ? 1 : 0)} uur`;
  const d = h / 24;
  return `${nl(d, d < 10 && d % 1 ? 1 : 0)} ${Math.round(d * 10) === 10 ? 'dag' : 'dagen'}`;
};
const lees = (k, s) => { try { return localStorage.getItem(k) || s; } catch { return s; } };
const zet = (k, v) => { try { localStorage.setItem(k, String(v)); } catch { /* geen opslag */ } };

const Kaart = ({ icon: I, titel, uitleg, extra, children, style }) => (
  <div className="mg-kaart" style={style}>
    {titel && <h3><span>{I && <I size={17} />}{titel}</span>{extra}</h3>}
    {uitleg && <p className="mg-uitleg">{uitleg}</p>}
    {!uitleg && titel && <div style={{ height: 10 }} />}
    {children}
  </div>);
const Sectie = ({ children, sub }) => <div className="mg-sectie">{children}{sub && <small>{sub}</small>}</div>;
const Niet = ({ children }) => <div className="hint" style={{ background: 'var(--bg)', padding: '12px 14px', borderRadius: 10, margin: 0 }}>{children}</div>;
const Kpi = ({ l, n, s, delta, spark }) => (
  <div className="mg-kpi">
    <div className="l">{l}</div>
    <div className="n">{n}</div>
    <div className="s"><span>{s}{delta && <> <em className={delta[1]}>{delta[0]}</em></>}</span>{spark && <Spark waarden={spark} />}</div>
  </div>);
function Tabel({ koppen, rijen, max }) {
  const [alles, setAlles] = useState(false);
  const zicht = max && !alles ? rijen.slice(0, max) : rijen;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%' }}>
        <thead><tr>{koppen.map(([k, r]) => <th key={k} style={r ? { textAlign: 'right' } : undefined}>{k}</th>)}</tr></thead>
        <tbody>{zicht.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={koppen[j][1] ? { textAlign: 'right' } : undefined}>{c}</td>)}</tr>)}</tbody>
      </table>
      {max && rijen.length > max && <button type="button" className="linkknop" style={{ marginTop: 8 }} onClick={() => setAlles(!alles)}>
        {alles ? 'Minder tonen' : `Alle ${rijen.length} tonen`}</button>}
    </div>);
}
const Status = ({ s }) => { const [t, k] = ST[s] || ST.unknown; return <b style={{ color: `var(--${k})` }}>{t}</b>; };
const Tabs = ({ tab, setTab }) => (
  <div className="mg-tabs">
    <button type="button" className={tab === 'org' ? 'aan' : ''} onClick={() => setTab('org')}><BarChart3 size={15} />Organisatie</button>
    <button type="button" className={tab === 'klant' ? 'aan' : ''} onClick={() => setTab('klant')}><Building2 size={15} />Klantrapportage</button>
  </div>);

export default function Management({ klanten }) {
  const [tab, setTabState] = useState(() => lees('mg.tab', 'org'));
  const setTab = (t) => { setTabState(t); zet('mg.tab', t); };
  return (
    <div className="mg">
      {tab === 'klant' ? <KlantRapport tabs={<Tabs tab={tab} setTab={setTab} />} /> : <Organisatie klanten={klanten} tabs={<Tabs tab={tab} setTab={setTab} />} />}
    </div>);
}

// ================================================================ Organisatie
function Organisatie({ klanten, tabs }) {
  const [d, setD] = useState(null);
  const [dagen, setDagen] = useState(() => +lees('mg.dagen', 30) || 30);
  const timer = useRef(null);
  const lijst = () => (klanten || []).map((k) => ({ id: k.id, name: k.name, own: !!k.own, access: !!k.access, days: k.days ?? null, end: k.end || '' }));
  const laad = async (fresh, dg = dagen) => {
    clearTimeout(timer.current);
    try {
      const x = await api('mg.overzicht', { days: dg, fresh: !!fresh, customers: lijst() }, { quiet: true });
      setD(x);
      if (x.busy) timer.current = setTimeout(() => laad(false, dg), 2000);
    } catch (e) { toast(e.message, 'e'); }
  };
  useEffect(() => { laad(false); return () => clearTimeout(timer.current); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const periode = (v) => { setDagen(v); zet('mg.dagen', v); laad(false, v); };
  const pdf = () => act('mg.pdf', { days: dagen, customers: lijst() }, { msg: 'Managementrapportage opstellen...' });
  const licenties = async () => { await act('mg.licenties', { customers: lijst() }, { quiet: true }); laad(false); };

  const hero = (inhoud, bezig) => (
    <div className="mg-hero">
      <div className="mg-top">
        <div><h2>Management</h2>
          <div className="mg-sub">{bezig && bezig.length ? <>Bezig met ophalen: {bezig.join(', ')}...</> : d ? <>Stand {d.at} · servicedesk, back-up, e-mailbeveiliging en Microsoft 365</> : 'Gegevens verzamelen...'}</div></div>
        {d && (
          <div className="mg-acties">
            <select value={dagen} onChange={(e) => periode(+e.target.value)} style={{ width: 'auto' }}>
              {[7, 30, 90, 180, 365].map((v) => <option key={v} value={v}>Laatste {v} dagen</option>)}
            </select>
            <Btn icon={Download} onClick={() => exporteer(d)}>CSV</Btn>
            <Btn v="p" icon={FileText} onClick={pdf}>PDF-rapport</Btn>
            <Btn icon={RefreshCw} onClick={() => laad(true)} disabled={!!(bezig && bezig.length)}>{bezig && bezig.length ? 'Bezig...' : 'Vernieuwen'}</Btn>
          </div>)}
      </div>
      {tabs}
      {inhoud}
    </div>);

  if (!d) return <>{hero(null)}<Loading text="Managementgegevens verzamelen..." /></>;
  const { backup: bk, email: em, autotask: ats, m365 } = d;
  const at = ats.data;
  const { gdap: gd, licenses: lic } = m365;
  const bezig = [ats.busy && 'servicedesk', bk.busy && 'back-up', em.busy && 'e-mailbeveiliging', lic.busy && 'licenties'].filter(Boolean);
  const wk = at ? at.weeks : [];

  return (
    <>
      {hero(
        <div className="mg-kpis">
          {at && <Kpi l="Tickets afgerond" n={nl(at.kpi.completed)} s={`${nl(at.kpi.created)} binnengekomen`} spark={wk.map((w) => w.completed)} />}
          {at && <Kpi l="Open tickets" n={nl(at.kpi.open)} s={`${nl(at.kpi.openOld)} ouder dan 30 dagen`} />}
          {at && <Kpi l="Uren geregistreerd" n={nl(at.kpi.hours, 1)} s={`${pc(at.kpi.billablePct)} facturabel`} spark={wk.map((w) => w.hours)} />}
          {bk.kpi && <Kpi l="Back-ups geslaagd" n={pc(bk.kpi.pct)} s={`${nl(bk.kpi.custErr)} klant(en) met fouten`} />}
          {em.kpi && <Kpi l="DMARC-naleving" n={pc(em.kpi.pct)} s={`${nl(em.kpi.protected)}/${nl(em.kpi.domains)} domeinen beschermd`} />}
          {lic.loaded ? <Kpi l="Licentiebenutting" n={pc(lic.usePct)} s={`${nl(lic.saving)} mogelijk overbodig`} />
            : <Kpi l="GDAP-toegang" n={`${nl(gd.access)}/${nl(gd.customers)}`} s={`${gd.expiring.length} verloopt binnen 30 dagen`} />}
        </div>, bezig)}

      <Kaart icon={AlertTriangle} titel="Aandachtspunten" uitleg="Wat nu aandacht van management vraagt, het belangrijkste eerst.">
        {d.points.length ? <div className="mg-punten">{d.points.map((p, i) => (
          <div key={i} className="mg-punt"><i style={{ background: `var(--${NIVEAU[p.level][0]})` }} /><b>{p.area}</b><span>{p.text}</span></div>))}</div>
          : <div style={{ color: 'var(--gr)', fontWeight: 700, display: 'flex', gap: 8, alignItems: 'center' }}><CheckCircle2 size={18} />Geen kritieke punten of aandachtspunten.</div>}
      </Kaart>

      <Sectie sub={at ? `laatste ${at.days} dagen` : ''}>Servicedesk</Sectie>
      {!at ? <Kaart>{ats.busy ? <Loading text="Servicedeskcijfers ophalen uit Autotask..." /> : <Niet>{ats.error || (ats.configured ? 'Nog geen cijfers.' : 'Autotask is niet gekoppeld.')}</Niet>}</Kaart> : (
        <>
          <Kaart icon={Ticket} titel="Binnengekomen en afgerond per week" uitleg="Groeit de werkvoorraad, of houden we het bij? Beweeg over de grafiek voor de aantallen."
            extra={<span className="hint" style={{ margin: 0 }}>doorlooptijd (mediaan) {at.kpi.leadMedian != null ? `${nl(at.kpi.leadMedian, 1)} dagen` : '-'} · {pc(at.kpi.within1)} binnen 1 dag</span>}>
            <Lijn labels={wk.map((w) => w.label)} reeksen={[{ naam: 'Binnengekomen', kleur: 'hd', waarden: wk.map((w) => w.created) }, { naam: 'Afgerond', kleur: 'gr', waarden: wk.map((w) => w.completed) }]} />
          </Kaart>
          <div className="mg-raster-2">
            <Kaart icon={Clock} titel="Uren per week" uitleg="Alle geregistreerde uren (tickets en projecten).">
              <Kolommen labels={wk.map((w) => w.label)} reeksen={[{ naam: 'Uren', kleur: 'navy', waarden: wk.map((w) => w.hours) }]} eenheid="" dec={1} hoogte={210} waarden={wk.length <= 8} />
            </Kaart>
            <Kaart icon={Gauge} titel="Leeftijd van de open tickets" uitleg={`${nl(at.kpi.open)} tickets staan open.`}>
              <Donut delen={Object.entries(at.openAge).map(([l, n], i) => [l, n, ['gr', 'hd', 'or', 'rd'][i]])} midden={nl(at.kpi.open)} sub="open" />
            </Kaart>
          </div>
          <div className="mg-raster-2">
            <Kaart icon={Building2} titel="Meeste uren per klant"><Staven rijen={at.customers.filter((c) => c.hours).slice(0, 10).map((c) => [c.name, c.hours])} eenheid=" u" dec={1} /></Kaart>
            <Kaart icon={Ticket} titel="Meeste tickets per klant"><Staven rijen={[...at.customers].filter((c) => c.created).sort((a, b) => b.created - a.created).slice(0, 10).map((c) => [c.name, c.created])} kleur="cy" /></Kaart>
          </div>
          <div className="mg-raster-2">
            <Kaart icon={Users} titel="Uren per medewerker" uitleg="Geregistreerde en facturabele uren, en afgeronde tickets.">
              <Kolommen labels={at.employees.map((m) => m.name.split(' ')[0])} reeksen={[{ naam: 'Uren', kleur: 'navy', waarden: at.employees.map((m) => m.hours) },
                { naam: 'Facturabel', kleur: 'cy', waarden: at.employees.map((m) => m.billable) }]} dec={1} hoogte={210} waarden={at.employees.length <= 6} />
              <Tabel koppen={[['Medewerker'], ['Uren', 1], ['Facturabel', 1], ['% facturabel', 1], ['Afgerond', 1]]}
                rijen={at.employees.map((m) => [m.name, nl(m.hours, 1), nl(m.billable, 1), pc(m.billablePct), nl(m.completed)])} />
            </Kaart>
            <Kaart icon={BarChart3} titel="Verdeling" uitleg="Open tickets per prioriteit en nieuwe tickets per wachtrij.">
              <Donut delen={at.priorities.slice(0, 6).map((p, i) => [p.label, p.count, ['mu2', 'hd', 'or', 'rd', 'navy', 'cy'][i % 6]])} midden={nl(at.kpi.open)} sub="open" maat={150} />
              <div style={{ height: 14 }} />
              <Staven rijen={at.queues.slice(0, 6).map((q) => [q.label, q.count])} kleur="hd" />
            </Kaart>
          </div>
        </>)}

      <Sectie sub={bk.at ? `stand ${bk.at}` : ''}>Back-up en e-mailbeveiliging</Sectie>
      <div className="mg-raster-2">
        <Kaart icon={DatabaseBackup} titel="Back-up" uitleg="Geslaagd = een geslaagde back-up in de laatste 26 uur.">
          {!bk.kpi ? <Niet>{bk.configured === false ? 'Er is geen back-upkoppeling (Datto/Unitrends) ingesteld.' : 'Back-upgegevens ophalen...'}</Niet> : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <Meter pct={bk.kpi.pct} label="slagingspercentage" />
                <div style={{ flex: 1, minWidth: 220 }}>
                  <Donut delen={[['Geslaagd', bk.kpi.ok, 'gr'], ['Waarschuwing', bk.kpi.warn, 'or'], ['Mislukt', bk.kpi.err, 'rd'], ['Onbekend', bk.kpi.unknown, 'mu2'], ['Gepauzeerd', bk.kpi.paused, 'bd2']]}
                    midden={nl(bk.kpi.items)} sub="systemen" maat={130} />
                </div>
              </div>
              <div style={{ marginTop: 12 }}>
                {bk.customers.filter((c) => c.status === 'err' || c.status === 'warn').slice(0, 8).map((c) => (
                  <div key={c.name} style={{ padding: '6px 0', borderTop: '1px solid var(--bd)', fontSize: 13 }}>
                    <b>{c.name}</b> · <Status s={c.status} />
                    {c.issues.slice(0, 3).map((i, j) => <div key={j} style={{ fontSize: 12.5, color: `var(--${i.status === 'err' ? 'rd' : 'or'})` }}>{i.name} ({i.source}): {i.message || ST[i.status]?.[0]}</div>)}
                  </div>))}
                {!bk.customers.some((c) => c.status === 'err' || c.status === 'warn') && <div style={{ color: 'var(--gr)', fontWeight: 700 }}>Alle klanten zijn in orde.</div>}
              </div>
            </>)}
        </Kaart>
        <Kaart icon={MailCheck} titel="E-mailbeveiliging" uitleg={em.days ? `DMARC over de laatste ${em.days} dagen.` : ''}>
          {!em.kpi ? <Niet>{em.configured === false ? 'Er is geen EasyDMARC-koppeling ingesteld.' : 'Gegevens ophalen...'}</Niet> : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <Meter pct={em.kpi.pct} label="DMARC-naleving" />
                <div style={{ flex: 1, minWidth: 220 }}>
                  <Donut delen={[['Weigeren', em.policies.reject, 'gr'], ['Quarantaine', em.policies.quarantine, 'hd'], ['Monitoren', em.policies.none, 'or'], ['Geen DMARC', em.policies.missing, 'rd']]}
                    midden={nl(em.kpi.domains)} sub="domeinen" maat={130} />
                </div>
              </div>
              <Tabel koppen={[['Klant'], ['Status'], ['Berichten', 1], ['Geslaagd', 1]]} max={8}
                rijen={em.customers.map((c) => [c.name, <Status key="s" s={c.status} />, nl(c.volume), pc(c.pct)])} />
            </>)}
        </Kaart>
      </div>

      <Sectie>Microsoft 365</Sectie>
      <div className="mg-raster-2">
        <Kaart icon={KeyRound} titel="Licenties" uitleg="Ingekochte licenties van alle klanten en hoe ze gebruikt worden.">
          {!lic.loaded ? (lic.busy ? <Loading text="Licenties van alle klanten ophalen..." /> : (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <Niet>Het licentieoverzicht van alle klanten is nog niet opgehaald (duurt even, alleen lezen).</Niet>
              <Btn v="p" icon={KeyRound} onClick={licenties}>Licenties ophalen</Btn>
            </div>)) : (
            <>
              <Donut delen={[['In gebruik', Math.max(lic.assigned - lic.disabled - lic.unused, 0), 'gr'], ['Uitgeschakeld', lic.disabled, 'or'], ['Niet gebruikt (>90 d)', lic.unused, 'rd'], ['Vrij', lic.free, 'mu2']]}
                midden={nl(lic.bought)} sub="betaald" />
              <div style={{ height: 14 }} />
              <Staven rijen={lic.perCustomer.filter((c) => c.saving).slice(0, 8).map((c) => [c.name, c.saving])} kleur="or" leeg="Geen overbodige licenties gevonden." />
            </>)}
        </Kaart>
        <Kaart icon={Building2} titel="GDAP en verlengingen">
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <Meter pct={gd.customers ? Math.round((gd.access * 1000) / gd.customers) / 10 : null} label={`${nl(gd.access)} van ${nl(gd.customers)} klanten met toegang`} drempels={[95, 80]} />
            <div style={{ flex: 1, minWidth: 200, fontSize: 13 }}>
              <b style={{ color: 'var(--navy)' }}>Verloopt binnen 30 dagen</b>
              {gd.expiring.length ? gd.expiring.slice(0, 6).map((x) => <div key={x.name}>{x.name} <span className="hint" style={{ margin: 0 }}>· {x.days} d</span></div>)
                : <div className="hint" style={{ margin: 0 }}>Geen.</div>}
            </div>
          </div>
          {lic.loaded && (lic.renewals.length ? <Tabel koppen={[['Klant'], ['Licentie'], ['Verlenging', 1]]} max={6} rijen={lic.renewals.map((x) => [x.customer, x.name, x.date])} />
            : <div className="hint">Geen verlengingen binnen 45 dagen.</div>)}
        </Kaart>
      </div>
      <div className="hint" style={{ display: 'flex', gap: 6, alignItems: 'center' }}><Info size={14} />Alles wordt alleen gelezen en alleen in het geheugen bewaard. Het PDF-rapport wordt opgeslagen in Downloads en direct geopend.</div>
    </>);
}

function exporteer(d) {
  const { backup: bk, email: em, autotask: ats, m365 } = d;
  const at = ats.data; const { gdap: gd, licenses: lic } = m365;
  const r = [['Onderdeel', 'Klant / onderwerp', 'Kenmerk', 'Waarde']];
  const k = (o, n, w) => r.push([o, '', n, w]);
  if (at) {
    Object.entries(at.kpi).forEach(([n, w]) => k('Servicedesk (totaal)', n, w));
    at.customers.forEach((c) => r.push(['Servicedesk', c.name, 'nieuw/afgerond/open/uren/facturabel', `${c.created}/${c.completed}/${c.open}/${c.hours}/${c.billable}`]));
    at.employees.forEach((m) => r.push(['Servicedesk medewerker', m.name, 'uren/facturabel/afgerond', `${m.hours}/${m.billable}/${m.completed}`]));
    at.weeks.forEach((w) => r.push(['Servicedesk week', w.label, 'binnengekomen/afgerond/uren', `${w.created}/${w.completed}/${w.hours}`]));
  }
  if (bk.kpi) {
    Object.entries(bk.kpi).forEach(([n, w]) => k('Back-up (totaal)', n, w));
    bk.customers.forEach((c) => {
      r.push(['Back-up', c.name, 'status/geslaagd/waarschuwing/mislukt', `${ST[c.status]?.[0] || c.status}/${c.ok}/${c.warn}/${c.err}`]);
      c.issues.forEach((i) => r.push(['Back-up probleem', c.name, `${i.name} (${i.source})`, i.message || ST[i.status]?.[0]]));
    });
  }
  if (em.kpi) {
    Object.entries(em.kpi).forEach(([n, w]) => k('E-mail (totaal)', n, w));
    em.customers.forEach((c) => r.push(['E-mail', c.name, 'status/domeinen/berichten/geslaagd %', `${ST[c.status]?.[0] || c.status}/${c.domains}/${c.volume}/${c.pct ?? '-'}`]));
  }
  k('Microsoft 365', 'klanten/met toegang/zonder toegang', `${gd.customers}/${gd.access}/${gd.noAccess}`);
  gd.expiring.forEach((x) => r.push(['GDAP verloopt', x.name, 'einddatum/dagen', `${x.end}/${x.days}`]));
  if (lic.loaded) {
    lic.perCustomer.forEach((c) => r.push(['Licenties', c.name, 'ingekocht/toegewezen/vrij/uitgeschakeld/>90d/overbodig', `${c.bought}/${c.assigned}/${c.free}/${c.disabled}/${c.unused}/${c.saving}`]));
    lic.renewals.forEach((x) => r.push(['Verlenging', x.customer, x.name, x.date]));
  }
  d.points.forEach((p) => r.push(['Aandachtspunt', p.area, NIVEAU[p.level][1], p.text]));
  csv(`management-${new Date().toISOString().slice(0, 10)}.csv`, r);
}

// ================================================================ Klantrapportage (kwartaal)
function KlantRapport({ tabs }) {
  const [opties, setOpties] = useState(null);
  const [zoek, setZoek] = useState('');
  const [gevonden, setGevonden] = useState(null);
  const [bedrijf, setBedrijf] = useState(() => { try { return JSON.parse(lees('mg.klant', 'null')); } catch { return null; } });
  const [kw, setKw] = useState('');
  const [d, setD] = useState(null);
  const [laden, setLaden] = useState(false);
  const [bijlage, setBijlage] = useState(true);
  const [mensen, setMensen] = useState(true);
  const zoekTimer = useRef(null);

  useEffect(() => {
    api('mg.kwartalen', {}, { quiet: true }).then((x) => { setOpties(x); setKw((o) => o || (x.quarters[1] || x.quarters[0]).key); })
      .catch((e) => toast(e.message, 'e'));
  }, []);
  const laad = async (b = bedrijf, q = kw, fresh = false) => {
    if (!b || !q) return;
    setLaden(true);
    try { setD(await api('mg.klant', { companyId: b.id, quarter: q, fresh }, { quiet: true })); } catch (e) { toast(e.message, 'e'); setD(null); }
    setLaden(false);
  };
  useEffect(() => { if (bedrijf && kw) laad(bedrijf, kw); }, [bedrijf?.id, kw]); // eslint-disable-line react-hooks/exhaustive-deps
  const kies = (b) => { setBedrijf(b); zet('mg.klant', JSON.stringify(b)); setGevonden(null); setZoek(''); };
  const zoeken = (q) => {
    setZoek(q);
    clearTimeout(zoekTimer.current);
    if (q.trim().length < 2) { setGevonden(null); return; }
    zoekTimer.current = setTimeout(() => api('mg.kwartalen', { q }, { quiet: true }).then((x) => setGevonden(x.companies)).catch(() => {}), 350);
  };
  const pdf = () => act('mg.klant.pdf', { companyId: bedrijf.id, quarter: kw, tickets: bijlage, employees: mensen }, { msg: 'Kwartaalrapportage opstellen...' });
  const exporteerKlant = () => {
    const r = [['Nummer', 'Onderwerp', 'Gemeld', 'Opgelost', 'Uren', 'Medewerker', 'Contactpersoon']];
    d.resolved.forEach((t) => r.push([t.number, t.title, t.created, t.completed, t.hours, t.by, t.contact]));
    csv(`tickets-${d.company.name}-${d.quarter.short}.csv`.replace(/\s+/g, '-'), r);
  };

  const k = d?.kpi; const v = d?.prev;
  const delta = (nu, toen, goed) => {
    if (!toen) return null;
    const x = nu - toen;
    if (Math.abs(x) < Math.max(1, toen * 0.05)) return ['gelijk', ''];
    return [`${x > 0 ? '+' : '−'}${Math.round((Math.abs(x) * 100) / toen)}%`, goed == null ? '' : (x > 0) === goed ? 'op' : 'af'];
  };
  const bedrijven = gevonden || opties?.companies || [];

  return (
    <>
      <div className="mg-hero">
        <div className="mg-top">
          <div><h2>Kwartaalrapportage</h2>
            <div className="mg-sub">Per klant: wat hebben wij het afgelopen kwartaal gedaan, in gewone taal. Als PDF klaar om naar de klant te sturen.</div></div>
          {d && (
            <div className="mg-acties">
              <Btn icon={Download} onClick={exporteerKlant}>CSV</Btn>
              <Btn v="p" icon={FileText} onClick={pdf}>PDF voor de klant</Btn>
              <Btn icon={RefreshCw} onClick={() => laad(bedrijf, kw, true)} disabled={laden}>Vernieuwen</Btn>
            </div>)}
        </div>
        {tabs}
        {opties && opties.configured === false ? <div className="mg-kies"><Niet>Autotask is niet gekoppeld.</Niet></div> : (
          <div className="mg-kies">
            <select value={bedrijf ? String(bedrijf.id) : ''} onChange={(e) => { const b = bedrijven.find((x) => String(x.id) === e.target.value); if (b) kies(b); }}>
              <option value="" disabled>{gevonden ? `${gevonden.length} gevonden, kies een klant` : 'Kies een klant'}</option>
              {bedrijf && !bedrijven.some((x) => x.id === bedrijf.id) && <option value={String(bedrijf.id)}>{bedrijf.name}</option>}
              {bedrijven.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
            </select>
            <div style={{ position: 'relative' }}>
              <Search size={15} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--mu)' }} />
              <input value={zoek} onChange={(e) => zoeken(e.target.value)} placeholder="Andere klant zoeken in Autotask" style={{ paddingLeft: 32 }} />
            </div>
            <select value={kw} onChange={(e) => setKw(e.target.value)} style={{ minWidth: 0 }}>
              {(opties?.quarters || []).map((q) => <option key={q.key} value={q.key}>{q.label}{q.current ? ' (lopend)' : ''}</option>)}
            </select>
            {d && <><label><input type="checkbox" checked={bijlage} onChange={(e) => setBijlage(e.target.checked)} />Ticketlijst in de PDF</label>
              <label><input type="checkbox" checked={mensen} onChange={(e) => setMensen(e.target.checked)} />Medewerkers in de PDF</label></>}
          </div>)}
        {d && k && (
          <div className="mg-kpis">
            <Kpi l="Vragen binnengekomen" n={nl(k.created)} s={`vorig kwartaal ${nl(v.created)}`} delta={delta(k.created, v.created)} spark={d.months.map((m) => m.created)} />
            <Kpi l="Opgelost" n={nl(k.completed)} s={`${nl(k.open)} nog open`} delta={delta(k.completed, v.completed, true)} spark={d.months.map((m) => m.completed)} />
            <Kpi l="Uren gewerkt" n={uurNl(k.hours)} s={`vorig kwartaal ${uurNl(v.hours)}`} delta={delta(k.hours, v.hours)} spark={d.months.map((m) => m.hours)} />
            <Kpi l="Helft opgelost binnen" n={duur(k.leadMedian)} s={k.firstResponse != null ? `eerste reactie ${duur(k.firstResponse)}` : ''} />
          </div>)}
      </div>

      {!bedrijf ? <div className="mg-kaart mg-leeg"><Building2 size={42} /><div>Kies hierboven een klant en een kwartaal.</div></div>
        : laden && !d ? <Loading text="Gegevens van de klant ophalen uit Autotask..." />
          : !d ? null : (
            <div style={{ opacity: laden ? 0.55 : 1, transition: 'opacity .2s' }}>
              <Kaart icon={CheckCircle2} titel={`${d.company.name} · ${d.quarter.label}`} uitleg={`Zo leest de klant het in de PDF (${d.quarter.range}${d.current ? ', tot en met vandaag' : ''}).`}>
                {d.summary.map((z) => <div key={z} className="mg-zin"><CheckCircle2 size={17} /><span>{z}</span></div>)}
              </Kaart>

              <Sectie sub="tickets">Vragen en meldingen</Sectie>
              <div className="mg-raster-2">
                <Kaart icon={Ticket} titel="Per maand" uitleg="Binnengekomen en opgeloste vragen.">
                  <Kolommen labels={d.months.map((m) => m.label)} reeksen={[{ naam: 'Binnengekomen', kleur: 'hd', waarden: d.months.map((m) => m.created) }, { naam: 'Opgelost', kleur: 'gr', waarden: d.months.map((m) => m.completed) }]} />
                </Kaart>
                <Kaart icon={BarChart3} titel="Waar gingen de vragen over?">
                  <Donut delen={d.types.slice(0, 7).map((x, i) => [x.label, x.count, PALET[i % PALET.length]])} midden={nl(k.created)} sub="vragen" />
                </Kaart>
              </div>
              <div className="mg-raster-3">
                <Kaart icon={Users} titel="Wie stelde de vragen?"><Staven rijen={d.contacts.slice(0, 8).map((x) => [x.label, x.count])} /></Kaart>
                <Kaart icon={MailCheck} titel="Hoe kwamen ze binnen?"><Staven rijen={d.sources.slice(0, 6).map((x) => [x.label, x.count])} kleur="cy" /></Kaart>
                <Kaart icon={Clock} titel="Op welke dag?">
                  <Kolommen labels={d.weekdays.slice(0, d.weekdays.slice(5).some((x) => x.count) ? 7 : 5).map((x) => x.label.slice(0, 2))}
                    reeksen={[{ naam: 'Vragen', kleur: 'navy', waarden: d.weekdays.slice(0, d.weekdays.slice(5).some((x) => x.count) ? 7 : 5).map((x) => x.count) }]} hoogte={190} />
                </Kaart>
              </div>

              <Sectie sub="doorlooptijd en eerste reactie">Snelheid</Sectie>
              <div className="mg-raster-2">
                <Kaart icon={Gauge} titel="Hoe lang duurde het oplossen?" uitleg="Van melding tot afgesloten ticket, nachten en weekenden inbegrepen.">
                  <Donut delen={d.speed.map((x, i) => [x.label, x.count, ['gr', '#58aa78', 'hd', 'or', 'rd'][i]])} midden={pc(k.within1)} sub="binnen een dag" />
                </Kaart>
                <Kaart icon={Clock} titel="Kerncijfers snelheid">
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'space-around' }}>
                    <Meter pct={k.within4} label="binnen 4 uur opgelost" drempels={[50, 30]} maat={170} />
                    <Meter pct={k.within1} label="binnen een dag opgelost" drempels={[70, 50]} maat={170} />
                  </div>
                  <div className="hint" style={{ textAlign: 'center' }}>Eerste reactie meestal binnen <b>{duur(k.firstResponse)}</b> · helft opgelost binnen <b>{duur(k.leadMedian)}</b></div>
                </Kaart>
              </div>

              <Sectie sub="uren en medewerkers">Tijd</Sectie>
              <div className="mg-raster-2">
                <Kaart icon={Clock} titel="Uren per maand" uitleg={k.projectHours ? `${uurNl(k.ticketHours)} uur aan vragen en meldingen, ${uurNl(k.projectHours)} uur aan projecten.` : ''}>
                  <Kolommen labels={d.months.map((m) => m.label)} reeksen={[{ naam: 'Uren', kleur: 'navy', waarden: d.months.map((m) => m.hours) }]} dec={1} />
                </Kaart>
                <Kaart icon={Users} titel="Wie heeft de klant geholpen?">
                  <Tabel koppen={[['Medewerker'], ['Opgelost', 1], ['Uren', 1]]} rijen={d.employees.filter((m) => m.tickets || m.hours).map((m) => [m.name, nl(m.tickets), nl(m.hours, 1)])} />
                  {!!d.projects.length && <><div style={{ height: 12 }} /><Staven rijen={d.projects.slice(0, 6).map((x) => [x.label, x.hours])} eenheid=" u" kleur="cy" dec={1} /></>}
                </Kaart>
              </div>

              {(d.extra.backup || d.extra.email || d.extra.m365) && (
                <>
                  <Sectie sub="stand van vandaag">IT-omgeving</Sectie>
                  <div className="mg-raster-3">
                    {d.extra.backup && <Kaart icon={DatabaseBackup} titel="Back-ups"><Meter pct={d.extra.backup.pct} label={`${d.extra.backup.total} systemen · ${ST[d.extra.backup.status]?.[0]}`} /></Kaart>}
                    {d.extra.email && <Kaart icon={MailCheck} titel="E-mailbeveiliging"><Meter pct={d.extra.email.pct} label={`${nl(d.extra.email.volume)} e-mails · ${d.extra.email.domains.length} domein(en)`} /></Kaart>}
                    {d.extra.m365 && <Kaart icon={KeyRound} titel="Microsoft 365-licenties">
                      <Donut delen={[['In gebruik', d.extra.m365.assigned, 'gr'], ['Vrij', d.extra.m365.free, 'mu2']]} midden={nl(d.extra.m365.bought)} sub="licenties" maat={130} pct={false} /></Kaart>}
                  </div>
                  {!d.extra.backup && !d.extra.email && <div className="hint">Back-up en e-mail: geen gegevens gevonden onder deze klantnaam.</div>}
                </>)}

              <Sectie sub={`${d.resolved.length} opgelost · ${d.openList.length} open`}>Tickets</Sectie>
              <Kaart>
                <Tabel koppen={[['Nummer'], ['Onderwerp'], ['Gemeld'], ['Opgelost'], ['Uren', 1], ['Medewerker'], ['Contactpersoon']]} max={12}
                  rijen={d.resolved.map((t) => [t.number, t.title, t.created, t.completed, t.hours ? nl(t.hours, 1) : '-', t.by, t.contact])} />
                {!!d.openList.length && <><div className="mg-sectie" style={{ fontSize: 14, margin: '18px 0 8px' }}>Nog open</div>
                  <Tabel koppen={[['Nummer'], ['Onderwerp'], ['Gemeld'], ['Status'], ['Medewerker'], ['Dagen open', 1]]}
                    rijen={d.openList.map((t) => [t.number, t.title, t.created, t.status, t.by, nl(t.age)])} /></>}
              </Kaart>
              <div className="hint" style={{ display: 'flex', gap: 6, alignItems: 'center' }}><Info size={14} />Alleen lezen uit Autotask; niets wordt opgeslagen. De PDF komt in Downloads en opent direct.</div>
            </div>)}
    </>);
}
