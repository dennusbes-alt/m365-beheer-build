// Domeinen: overzicht, live DNS-controle, toevoegen en verifiëren, standaarddomein, Exchange-domeintype en verwijderen.
import { useEffect, useState } from 'react';
import { CheckCircle2, Copy, ExternalLink, Globe, List, Plus, RefreshCw, Server, Settings, ShieldCheck, Star, Trash2 } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, askType, openModal, toast } from '../overlays.jsx';
import { useApp } from '../store.jsx';
import { Btn, Chip, Field, Loading, SearchBox, Tabs, useFilter } from '../ui.jsx';

const STATUS = { ok: ['In orde', 'g'], controleren: ['Controleren', 'o'], afwijkend: ['Afwijkend', 'r'], ontbreekt: ['Ontbreekt', 'r'], onbekend: ['Onbekend', 'mu'] };
const statusChip = (s) => { const x = STATUS[s] || [s, 'mu']; return <Chip k={x[1]}>{x[0]}</Chip>; };
const UITLEG = {
  controleren: 'Er staat een record, maar niet precies wat Microsoft voorstelt. Bij MX kan dat het nieuwere mx.microsoft-adres zijn; bij SPF een SPF-dienst die Microsoft via een eigen include regelt. Controleer of e-mail goed werkt.',
  afwijkend: 'Er staat een ander record dan Microsoft verwacht.',
  ontbreekt: 'Dit record staat niet in de DNS.',
};
const kopieer = (t) => navigator.clipboard.writeText(t).then(() => toast('Gekopieerd.', 'g'), () => toast('Kopiëren is niet gelukt.', 'e'));

export default function Domeinen() {
  const { herlaadInfo } = useApp();
  const [d, setD] = useState(null);
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(null);
  const laad = async (fresh, poging = 0) => {
    const x = await act('dom.list', fresh ? { fresh: true } : {}, { msg: 'Domeinen ophalen...', quiet: poging > 0 });
    if (x || !poging) setD(x || { domains: [] });
    // Exchange-gegevens (domeintype) nog niet klaar: de lijst staat er al, het type wordt even later aangevuld
    if (x && x.exoPending && poging < 12) setTimeout(() => laad(false, poging + 1), 1500);
    return x;
  };
  useEffect(() => { laad().then((x) => x && x.domains.length && setSel((s) => s || x.domains[0].id)); }, []);
  const shown = useFilter(d ? d.domains : [], q, (x) => [x.id]);
  if (!d) return <Loading text="Domeinen ophalen..." />;
  const gewijzigd = async (nieuwSel) => { await laad(true); if (nieuwSel !== undefined) setSel(nieuwSel); if (herlaadInfo) herlaadInfo(); };
  const toevoegen = async () => {
    const naam = await openModal((close) => <Toevoegen close={close} />);
    if (!naam) return;
    if (await act('dom.add', { id: naam }, { msg: 'Domein toevoegen...' })) gewijzigd(naam);
  };
  const dom = d.domains.find((x) => x.id === sel);
  return (
    <>
      <h2>Domeinen</h2>
      <p className="sub">Domeinen van deze klant: live DNS-controle, toevoegen en verifiëren, standaarddomein en Exchange-instellingen.</p>
      <div className="cols">
        <div className="sticky">
          <SearchBox value={q} onChange={setQ} placeholder="Zoek domein..." />
          <div className="list" style={{ maxHeight: 'calc(100vh - 320px)' }}>
            {shown.map((x) => (
              <div key={x.id} className={'li' + (x.id === sel ? ' on' : '')} onClick={() => setSel(x.id)}>
                <span className="m"><b>{x.id}</b><small>{x.initial ? 'Standaard Microsoft-domein' : (x.services || []).length ? x.services.join(', ') : 'Geen diensten'}</small></span>
                {x.default && <Chip k="g">standaard</Chip>}
                {!x.verified && <Chip k="o">niet geverifieerd</Chip>}
              </div>
            ))}
            {!shown.length && <div className="li empty">Geen domeinen gevonden</div>}
          </div>
          <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
            <div className="count" style={{ flex: 1, margin: 0 }}>{d.domains.length} domeinen</div>
            <div className="n btns"><Btn v="p" s icon={Plus} onClick={toevoegen}>Toevoegen</Btn><Btn s icon={RefreshCw} onClick={() => laad()}>Vernieuwen</Btn></div>
          </div>
        </div>
        <div>{dom ? <Detail key={dom.id} dom={dom} exo={d.exo} onChanged={gewijzigd} />
          : <div className="card muted"><Globe size={18} />Kies links een domein.</div>}</div>
      </div>
    </>
  );
}

function Detail({ dom, exo, onChanged }) {
  const [g, setG] = useState(null);
  const [tab, setTab] = useState(dom.verified ? 'dns' : 'verificatie');
  const laad = async () => { setG(null); const x = await act('dom.get', { id: dom.id }, { msg: 'DNS controleren...' }); setG(x || { id: dom.id }); };
  useEffect(() => { laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const tabs = [
    ...(dom.verified ? [] : [['verificatie', 'Verificatie', ShieldCheck]]),
    ...(dom.initial ? [] : [['dns', 'DNS-controle', Globe]]),
    ...(g && g.msDns ? [['zone', 'DNS-records (Microsoft)', List]] : []),
    ['inst', 'Instellingen', Settings],
  ];
  const T = tab === 'verificatie' ? Verificatie : tab === 'dns' && !dom.initial ? Dns : tab === 'zone' ? Zone : Instellingen;
  return (
    <>
      <div className="card">
        <div className="headrow">
          <div className="m">
            <h3>{dom.id}</h3>
            <div style={{ marginTop: 4 }}>
              {dom.default && <Chip k="g">Standaarddomein</Chip>} {dom.verified ? <Chip k="g">Geverifieerd</Chip> : <Chip k="o">Niet geverifieerd</Chip>}{' '}
              {dom.initial && <Chip k="mu">Microsoft-domein</Chip>} {dom.auth === 'Federated' && <Chip k="o">Gefedereerd</Chip>}{' '}
              {dom.exoType && <Chip>{dom.exoType === 'Authoritative' ? 'Exchange: gezaghebbend' : 'Exchange: intern relais'}</Chip>}{' '}
              {g && g.msDns && <Chip k="o" title={g.nameservers.join(', ')}>DNS bij Microsoft</Chip>}
            </div>
            <div className="hint" style={{ margin: '4px 0 0' }}>
              <Server size={12} style={{ verticalAlign: -1 }} /> Nameservers: {g ? (g.nameservers && g.nameservers.length ? g.nameservers.join(', ') : 'niet gevonden') : '...'}
            </div>
          </div>
          <div className="btns"><Btn icon={RefreshCw} onClick={laad}>Opnieuw controleren</Btn></div>
        </div>
      </div>
      <div className="card">
        <Tabs value={tab} onChange={setTab} tabs={tabs} />
        {!g ? <Loading text="DNS live controleren..." /> : <T dom={dom} g={g} exo={exo} herlaad={laad} onChanged={onChanged} />}
      </div>
    </>
  );
}

const portaal = (url) => act('open.url', { url }, { nobusy: true });

function MsDnsBalk({ g }) {
  if (!g.msDns) return null;
  return (
    <Msg kind="info">
      De DNS van dit domein staat bij Microsoft 365 (nameservers {g.nameservers.join(', ')}). Microsoft heeft geen API om deze records te wijzigen;
      toevoegen, wijzigen en verwijderen gaat in het Microsoft 365-beheercentrum van de klant onder Instellingen &gt; Domeinen &gt; {g.id} &gt; DNS-records.
      <div className="btns" style={{ marginTop: 8 }}>
        {g.links?.dns && <Btn s v="p" icon={ExternalLink} onClick={() => portaal(g.links.dns)}>DNS-records openen in beheercentrum</Btn>}
        <Btn s icon={ExternalLink} onClick={() => portaal(g.links.klant)}>Beheercentrum van de klant</Btn>
        <Btn s icon={Copy} onClick={() => kopieer(g.id)}>Domeinnaam kopiëren</Btn>
      </div>
    </Msg>
  );
}

function Zone({ g }) {
  const recs = g.zone || [];
  const [q, setQ] = useState('');
  const shown = useFilter(recs, q, (r) => [r.type, r.name, r.value]);
  return (
    <>
      <MsDnsBalk g={g} />
      <SearchBox value={q} onChange={setQ} placeholder="Zoek record..." />
      <div style={{ overflowX: 'auto', marginTop: 10 }}>
        <table>
          <thead><tr><th>Type</th><th>Naam</th><th>Waarde</th><th className="r">TTL</th></tr></thead>
          <tbody>{shown.map((r, i) => (
            <tr key={i}><td><Chip k="mu">{r.type}</Chip></td><td style={{ wordBreak: 'break-all' }}>{r.name}</td>
              <td style={{ wordBreak: 'break-all' }}>{r.value} <button className="btn s" title="Kopiëren" onClick={() => kopieer(r.value)}><Copy size={12} /></button></td>
              <td className="r">{r.ttl ?? '-'}</td></tr>))}
            {!shown.length && <tr><td colSpan={4} className="hint">Geen records gevonden.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="hint">Live opgevraagd. Een volledige lijst van alle records kan via DNS niet worden opgevraagd; de app zoekt de gangbare namen
        (domein zelf, www, mail, autodiscover, DKIM, DMARC, Intune, Teams/SIP en meer). Eigen namen staan alleen in het beheercentrum.</div>
    </>
  );
}

function Dns({ g }) {
  const recs = g.dns || [];
  const fout = recs.filter((r) => r.status !== 'ok').length;
  return (
    <>
      <MsDnsBalk g={g} />
      {fout === 0 ? <Msg kind="ok">Alle DNS-records zijn in orde.</Msg>
        : <Msg kind="warn">{fout} record(s) vragen aandacht. De DNS wordt live opgevraagd; na een wijziging bij de DNS-provider kun je meteen opnieuw controleren.</Msg>}
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead><tr><th>Dienst</th><th>Type</th><th>Naam</th><th>Verwacht</th><th>Gevonden</th><th>Status</th></tr></thead>
          <tbody>{recs.map((r, i) => (
            <tr key={i} title={UITLEG[r.status] || ''}>
              <td>{r.service}{r.extra && <div className="hint" style={{ margin: 0 }}>{r.extra}</div>}</td>
              <td><Chip k="mu">{r.type}</Chip></td>
              <td style={{ wordBreak: 'break-all' }}>{r.name}</td>
              <td style={{ wordBreak: 'break-all' }}>{r.vrij ? <span className="hint">{r.value}</span> : <>{r.value} <button className="btn s" title="Kopiëren" onClick={() => kopieer(r.value)}><Copy size={12} /></button></>}</td>
              <td style={{ wordBreak: 'break-all' }}>{r.found && r.found.length ? r.found.join(', ') : <span className="hint">-</span>}</td>
              <td>{statusChip(r.status)}</td>
            </tr>))}
            {!recs.length && <tr><td colSpan={6} className="hint">Geen records om te controleren.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="hint">DKIM zet je aan bij E-mail &gt; Bedreigingsbeheer. DMARC is een aanbeveling: begin met p=none of p=quarantine.</div>
    </>
  );
}

function Verificatie({ dom, g, herlaad, onChanged }) {
  const v = (g.verification || [])[0];
  const verifieer = async () => { if (await act('dom.verify', { id: dom.id }, { msg: 'Verifiëren...' })) onChanged(dom.id); };
  return (
    <>
      <p style={{ marginTop: 0 }}>Voeg dit TXT-record toe bij de DNS-provider van <b>{dom.id}</b> en klik daarna op <b>Verifiëren</b>.</p>
      {v ? (
        <div className="kv">
          <div><label>Type</label><div>TXT</div></div>
          <div><label>Naam / host</label><div>@ <span className="hint">({v.name})</span></div></div>
          <div><label>Waarde</label><div><b>{v.value}</b> <button className="btn s" onClick={() => kopieer(v.value)}><Copy size={12} /></button></div></div>
          <div><label>TTL</label><div>{v.ttl} seconden</div></div>
        </div>
      ) : <Msg kind="warn">Het verificatierecord kon niet opgehaald worden.</Msg>}
      <div className="btns" style={{ marginTop: 16 }}>
        <Btn v="p" icon={CheckCircle2} onClick={verifieer}>Verifiëren</Btn>
        <Btn icon={RefreshCw} onClick={herlaad}>Opnieuw ophalen</Btn>
      </div>
      <div className="hint">Een nieuw DNS-record is meestal binnen enkele minuten zichtbaar, soms pas na een uur.</div>
    </>
  );
}

function Instellingen({ dom, g, exo, onChanged }) {
  const [type, setType] = useState(dom.exoType || 'Authoritative');
  const standaard = async () => {
    if (await ask(`${dom.id} instellen als standaarddomein?\n\nNieuwe gebruikers en groepen krijgen dan standaard een adres op dit domein. Bestaande adressen veranderen niet.`, 'Instellen')
      && await act('dom.default', { id: dom.id }, { msg: 'Standaarddomein instellen...' })) onChanged();
  };
  const bewaarType = async () => {
    if (await act('dom.exotype', { id: dom.id, type }, { msg: 'Exchange-domeintype opslaan...' })) onChanged();
  };
  const weg = async () => {
    if (!await askType(`Domein ${dom.id} verwijderen uit de tenant van deze klant?\n\n`
      + (g.references ? `Er zijn nog ${g.references} gebruiker(s), groep(en) of app(s) met een adres op dit domein; die moeten eerst naar een ander domein.\n\n` : '')
      + 'E-mail naar dit domein komt daarna niet meer aan in Microsoft 365.', 'VERWIJDEREN')) return;
    if (await act('dom.delete', { id: dom.id }, { msg: 'Domein verwijderen...' })) onChanged(null);
  };
  return (
    <>
      <div className="kv">
        <div><label>Status</label><div>{dom.verified ? 'Geverifieerd' : 'Niet geverifieerd'}</div></div>
        <div><label>Aanmelden</label><div>{dom.auth === 'Federated' ? 'Gefedereerd (bijv. ADFS)' : 'Beheerd (Microsoft Entra)'}</div></div>
        <div><label>Diensten</label><div>{(dom.services || []).join(', ') || '-'}</div></div>
        <div><label>In gebruik door</label><div>{g.references == null ? '-' : `${g.references} object(en)`}</div></div>
      </div>
      <label className="f" style={{ marginTop: 18 }}>Standaarddomein</label>
      {dom.default ? <div className="hint" style={{ marginTop: 0 }}>Dit is het standaarddomein.</div>
        : <Btn icon={Star} disabled={!dom.verified} onClick={standaard}>Instellen als standaarddomein</Btn>}
      {exo && dom.verified && (
        <>
          <label className="f" style={{ marginTop: 18 }}>Exchange-domeintype</label>
          <div className="row">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="Authoritative">Gezaghebbend: alle postvakken van dit domein staan in Microsoft 365</option>
              <option value="InternalRelay">Intern relais: een deel van de postvakken staat elders (bijv. tijdens een migratie)</option>
            </select>
            <div className="n"><Btn v="p" disabled={type === (dom.exoType || 'Authoritative')} onClick={bewaarType}>Opslaan</Btn></div>
          </div>
        </>
      )}
      {!dom.initial && !dom.default && (
        <div style={{ marginTop: 22 }}><Btn v="dl" icon={Trash2} onClick={weg}>Domein verwijderen</Btn></div>
      )}
      {!dom.initial && dom.default && <div className="hint" style={{ marginTop: 18 }}>Het standaarddomein kun je niet verwijderen; maak eerst een ander domein standaard.</div>}
    </>
  );
}

function Toevoegen({ close }) {
  const [n, setN] = useState('');
  const ok = () => { const v = n.trim().toLowerCase(); if (!/^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/.test(v)) return toast('Vul een geldige domeinnaam in, bijvoorbeeld bedrijf.nl.', 'e'); close(v); };
  return (
    <>
      <h3>Domein toevoegen</h3>
      <p>Na het toevoegen krijg je een TXT-record om bij de DNS-provider te zetten. Daarmee bewijs je dat het domein van de klant is.</p>
      <Field label="Domeinnaam" value={n} onChange={setN} placeholder="bedrijf.nl" autoFocus onKeyDown={(e) => e.key === 'Enter' && ok()} />
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" icon={Plus} onClick={ok}>Toevoegen</Btn></div>
    </>
  );
}
