import { useEffect, useMemo, useRef, useState } from 'react';
import { Building2, ExternalLink, LayoutGrid, MonitorSmartphone, Search, Ticket, User, UsersRound } from 'lucide-react';
import { act } from './api.js';
import { getUsers } from './store.jsx';

// Zoekbalk bovenin: alles direct vinden. Schermen en klanten zoeken in het geheugen (meteen), gegevens van de open klant
// komen uit de bestaande caches (gebruikers, groepen, apparaten), Autotask-tickets en -bedrijven via sd.zoek (na even wachten).
const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const past = (q, ...velden) => { const w = norm(q).split(/\s+/).filter(Boolean); const t = norm(velden.join(' ')); return w.every((x) => t.includes(x)); };
const MAX = 6;
// Bedrijfsnaam zonder rechtsvorm en leestekens: 'Bakkerij De Korenaar B.V.' = 'Bakkerij De Korenaar'
const bedrijf = (s) => norm(s).replace(/\b(b\.?\s?v\.?|n\.?\s?v\.?|v\.?o\.?f\.?|holding)(?=\s|$)/g, '').replace(/[^a-z0-9]+/g, ' ').trim();

// Soortwoorden mogen in de zoekvraag staan ('apparaat LT-01', 'medewerker Bram'): die horen bij elk item van die soort
const SOORT = {
  user: 'medewerker gebruiker account persoon collega user',
  group: 'groep team postvak gedeeld distributielijst mailbox group',
  device: 'apparaat laptop pc computer telefoon device intune',
};

export default function Zoeken({ schermen, functies = [], klanten, klant, justdata, onKlant, onOpen }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [actief, setActief] = useState(0);
  const [data, setData] = useState({});          // gegevens van de open klant
  const [at, setAt] = useState({ q: '', tickets: [], companies: [], bezig: false });
  const veld = useRef(null);
  const tid = klant && klant.tenantId;

  // Ctrl+F of '/' (buiten een invoerveld) springt naar de zoekbalk
  useEffect(() => {
    const k = (e) => {
      const inVeld = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
      if (((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') || (e.key === '/' && !inVeld)) {
        e.preventDefault(); veld.current?.focus(); veld.current?.select();
      }
    };
    addEventListener('keydown', k);
    return () => removeEventListener('keydown', k);
  }, []);

  // Gegevens van de open klant pas ophalen zodra je gaat zoeken (meestal al in de cache)
  const geladen = useRef('');
  const laadKlant = () => {
    if (!tid || geladen.current === tid) return;
    geladen.current = tid;
    setData({});
    const o = { quiet: true, nobusy: true };
    getUsers(false).then((u) => setData((d) => ({ ...d, users: u || [] }))).catch(() => {});
    act('groups.list', { fresh: false }, o).then((r) => setData((d) => ({ ...d, groups: (r && r.groups) || [] })));
    act('dev.list', { fresh: false }, o).then((r) => setData((d) => ({ ...d, devices: (r && r.devices) || [] })));
  };
  useEffect(() => { geladen.current = ''; setData({}); }, [tid]);

  // Autotask: pas na 350 ms stilstand en vanaf 3 tekens
  useEffect(() => {
    if (!justdata || q.trim().length < 3) { setAt({ q: '', tickets: [], companies: [], bezig: false }); return undefined; }
    const z = q.trim();
    setAt((a) => ({ ...a, bezig: true }));
    const t = setTimeout(() => {
      act('sd.zoek', { q: z }, { quiet: true, nobusy: true }).then((r) => setAt((a) => (z === q.trim()
        ? { q: z, tickets: (r && r.tickets) || [], companies: (r && r.companies) || [], bezig: false } : a)));
    }, 350);
    return () => clearTimeout(t);
  }, [q, justdata]); // eslint-disable-line react-hooks/exhaustive-deps

  const groepen = useMemo(() => {
    const z = q.trim();
    if (!z) return [];
    const uit = [];
    // Functies: eerst die waarvan de naam zelf past, daarna die via een zoekwoord
    const f = functies.filter((x) => past(z, x.label, x.keywords, x.sub))
      .sort((a, b) => (past(z, b.label) - past(z, a.label))).slice(0, 8);
    if (f.length) uit.push(['Functies', f.map((x) => ({ key: 'f' + x.key, icon: x.icon || LayoutGrid, label: x.label, sub: x.sub, run: x.run }))]);
    const s = schermen.filter((x) => past(z, x.label, x.group) && !f.some((y) => y.label === x.label)).slice(0, MAX);
    if (s.length) uit.push(['Schermen', s.map((x) => ({ key: 's' + x.key, icon: x.icon || LayoutGrid, label: x.label, sub: x.group, run: x.run }))]);
    const k = (klanten || []).filter((x) => past(z, x.name, x.domain, 'klant')).slice(0, MAX);
    if (k.length) uit.push(['Klanten', k.map((x) => ({ key: 'k' + x.id, icon: Building2, label: x.name, sub: x.domain, run: () => onKlant(x) }))]);
    if (tid) {
      const naam = klant.tenant;
      const u = (data.users || []).filter((x) => past(z, x.name, x.upn, x.title, x.dept, SOORT.user)).slice(0, MAX);
      if (u.length) uit.push([`Gebruikers bij ${naam}`, u.map((x) => ({ key: 'u' + x.id, icon: User, label: x.name, sub: x.upn + (x.on === false ? ' · geblokkeerd' : ''), run: () => onOpen('users', { soort: 'user', id: x.id, q: x.name }) }))]);
      const g = (data.groups || []).filter((x) => past(z, x.name, x.mail, x.type, SOORT.group)).slice(0, MAX);
      if (g.length) uit.push([`Groepen en postvakken bij ${naam}`, g.map((x) => ({ key: 'g' + x.id, icon: UsersRound, label: x.name, sub: [x.type, x.mail].filter(Boolean).join(' · '), run: () => onOpen('groepen', { soort: 'group', id: x.id, q: x.name }) }))]);
      const d = (data.devices || []).filter((x) => past(z, x.name, x.upn, x.user, x.serial, x.model, x.os, SOORT.device)).slice(0, MAX);
      if (d.length) uit.push([`Apparaten bij ${naam}`, d.map((x) => ({ key: 'd' + x.id, icon: MonitorSmartphone, label: x.name, sub: [x.user || x.upn, x.serial].filter(Boolean).join(' · '), run: () => onOpen('apparaten', { soort: 'device', id: x.id, q: x.name }) }))]);
    }
    if (justdata && at.tickets.length) {
      uit.push(['Tickets in Autotask', at.tickets.map((x) => ({ key: 't' + x.id, icon: Ticket, label: `${x.number} ${x.title}`, sub: [x.company, x.status].filter(Boolean).join(' · '), ext: true,
        run: () => x.url && act('open.url', { url: x.url }, { nobusy: true, quiet: true }) }))]);
    }
    if (justdata && at.companies.length) {
      // Autotask-bedrijf dat ook een Microsoft-klant is: die openen; anders alleen tonen
      const extra = at.companies.filter((c) => !k.some((x) => bedrijf(x.name) === bedrijf(c.name)));
      const m = extra.map((c) => ({ c, kl: (klanten || []).find((x) => bedrijf(x.name) === bedrijf(c.name)) }));
      if (m.length) uit.push(['Bedrijven in Autotask', m.map(({ c, kl }) => ({ key: 'c' + c.id, icon: Building2, label: c.name, sub: kl ? 'Klant openen' : 'Geen Microsoft 365-koppeling', run: kl ? () => onKlant(kl) : null }))]);
    }
    return uit;
  }, [q, schermen, functies, klanten, tid, data, at, justdata]); // eslint-disable-line react-hooks/exhaustive-deps

  const plat = groepen.flatMap(([, l]) => l).filter((x) => x.run);
  useEffect(() => { setActief(0); }, [q]);
  const kies = (x) => { if (!x || !x.run) return; x.run(); setQ(''); setOpen(false); veld.current?.blur(); };
  const toets = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActief((a) => Math.min(a + 1, plat.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActief((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); kies(plat[actief]); }
    else if (e.key === 'Escape') { setQ(''); setOpen(false); veld.current?.blur(); }
  };
  const laadt = (tid && (!data.users || !data.groups || !data.devices)) || at.bezig;

  return (
    <div className="gzoek" onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }}>
      <Search size={16} className="gz-ic" />
      <input ref={veld} value={q} placeholder={tid ? `Zoek scherm, klant, gebruiker, apparaat, ticket...` : 'Zoek scherm, klant of ticket...'}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => { setOpen(true); laadKlant(); }} onKeyDown={toets} />
      <kbd>Ctrl F</kbd>
      {open && q.trim() && (
        <div className="gz-res" tabIndex={-1}>
          {groepen.map(([titel, l]) => (
            <div key={titel}>
              <div className="gz-grp">{titel}</div>
              {l.map((x) => {
                const i = plat.indexOf(x);
                const I = x.icon;
                return (
                  <button key={x.key} type="button" className={'gz-it' + (i === actief ? ' on' : '') + (x.run ? '' : ' uit')} disabled={!x.run}
                    onMouseEnter={() => i >= 0 && setActief(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => kies(x)}>
                    <I size={16} style={{ flex: 'none' }} />
                    <span className="gz-t"><b>{x.label}</b>{x.sub && <small>{x.sub}</small>}</span>
                    {x.ext && <ExternalLink size={13} style={{ flex: 'none', opacity: 0.6 }} />}
                  </button>
                );
              })}
            </div>
          ))}
          {laadt && <div className="gz-leeg"><span className="spin" style={{ width: 12, height: 12, borderWidth: 2 }} /> Nog aan het zoeken...</div>}
          {!laadt && !groepen.length && <div className="gz-leeg">Niets gevonden voor "{q.trim()}".</div>}
          {!tid && <div className="gz-leeg" style={{ fontSize: 12 }}>Medewerkers, groepen en apparaten vind je hier zodra je een klant hebt geopend.</div>}
        </div>
      )}
    </div>
  );
}
