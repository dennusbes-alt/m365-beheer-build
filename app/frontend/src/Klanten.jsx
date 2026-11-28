// Klantenoverzicht: eerste scherm na inloggen, en (compact) het wisselvenster.
import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeft, ChevronRight, Clock, Home, RefreshCw, ShieldAlert, Star, X } from 'lucide-react';
import { act } from './api.js';
import { Avatar, Btn, Chip, SearchBox, cx, datum } from './ui.jsx';

const FILTERS = [
  ['alle', 'Alle klanten'],
  ['fav', 'Favorieten'],
  ['recent', 'Recent'],
  ['verloopt', 'GDAP verloopt binnenkort'],
  ['beperkt', 'Beperkte rechten'],
  ['geen', 'Geen toegang'],
];

export default function Klanten({ klanten, huidig, onPick, onRefresh, onTerug, onClose, onOverzicht, compact, user, ververst, onRegelAlles, klus }) {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('alle');
  const [fav, setFav] = useState([]);
  const [recent, setRecent] = useState([]);
  const [kb, setKb] = useState(0);
  const lijstRef = useRef(null);

  useEffect(() => {
    act('prefs.get', {}, { nobusy: true, quiet: true }).then((p) => { if (p) { setFav(p.fav); setRecent(p.recent); } });
  }, []);

  const favSet = useMemo(() => new Set(fav), [fav]);
  const regelbaar = useMemo(() => klanten.filter((k) => k.access === false && k.fixable).length, [klanten]);
  const telling = useMemo(() => ({
    alle: klanten.length,
    fav: klanten.filter((k) => favSet.has(k.id)).length,
    recent: klanten.filter((k) => recent.includes(k.id)).length,
    verloopt: klanten.filter((k) => k.days != null && k.days <= 30).length,
    beperkt: klanten.filter((k) => k.missing && k.missing.length).length,
    geen: klanten.filter((k) => k.access === false).length,
  }), [klanten, favSet, recent]);

  const lijst = useMemo(() => {
    const t = q.trim().toLowerCase();
    let l = klanten.filter((k) => !t || k.name.toLowerCase().includes(t) || (k.domain || '').toLowerCase().includes(t) || k.id.toLowerCase().startsWith(t));
    if (filter === 'fav') l = l.filter((k) => favSet.has(k.id));
    if (filter === 'recent') l = recent.map((id) => l.find((k) => k.id === id)).filter(Boolean);
    if (filter === 'verloopt') l = l.filter((k) => k.days != null && k.days <= 30);
    if (filter === 'beperkt') l = l.filter((k) => k.missing && k.missing.length);
    if (filter === 'geen') l = l.filter((k) => k.access === false);
    if (filter !== 'recent') {
      // eigen tenant bovenaan, dan favorieten, dan alfabetisch
      l = [...l].sort((a, b) => (b.own - a.own) || (favSet.has(b.id) - favSet.has(a.id)) || a.name.localeCompare(b.name, 'nl'));
    }
    return l;
  }, [klanten, q, filter, favSet, recent]);

  useEffect(() => { setKb(0); }, [q, filter]);
  // Aangewezen klant (muis of pijltjestoetsen) na een korte pauze alvast stil openen: klikken gaat dan sneller
  useEffect(() => {
    const k = lijst[kb];
    if (!k || k.id === huidig) return undefined;
    const t = setTimeout(() => act('tenant.prefetch', { ids: [k.id] }, { quiet: true }), 450);
    return () => clearTimeout(t);
  }, [kb, lijst, huidig]);
  useEffect(() => {
    const el = lijstRef.current && lijstRef.current.querySelector('.kb');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [kb]);

  const toets = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setKb((i) => Math.min(lijst.length - 1, i + 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setKb((i) => Math.max(0, i - 1)); }
    if (e.key === 'Enter' && lijst[kb]) { e.preventDefault(); onPick(lijst[kb]); }
  };
  const ster = async (e, k) => {
    e.stopPropagation();
    const on = !favSet.has(k.id);
    setFav((f) => (on ? [...f, k.id] : f.filter((x) => x !== k.id)));
    act('prefs.fav', { id: k.id, on }, { nobusy: true });
  };

  const rij = (k, i) => {
    const verloopt = k.days != null && k.days <= 30;
    return (
      <div key={k.id} className={cx('krow', i === kb && 'kb', k.id === huidig && 'cur')} onClick={() => onPick(k)} onMouseMove={() => setKb(i)}>
        <button className={cx('star', favSet.has(k.id) && 'on')} onClick={(e) => ster(e, k)} title={favSet.has(k.id) ? 'Uit favorieten' : 'Favoriet maken'}>
          <Star size={17} fill={favSet.has(k.id) ? 'currentColor' : 'none'} />
        </button>
        <Avatar name={k.name} sq size={compact ? 36 : 42} />
        <div className="m">
          <b>{k.name}{k.own && <Chip k="mu"><Home size={11} />eigen tenant</Chip>}{k.id === huidig && <Chip k="g">huidige klant</Chip>}</b>
          <small>{k.domain || k.id}</small>
        </div>
        <div className="meta">
          {k.access === false && k.pending && !k.fixable && (
            <Chip k="o" title={`Nieuwe GDAP-relatie '${k.pending.name}' ${k.pending.text}.` + (k.pending.link ? ' Open de klant voor de goedkeuringslink.' : '')}>
              <Clock size={12} />Nieuwe GDAP-relatie: {k.pending.status === 'approvalPending' ? 'wacht op goedkeuring' : k.pending.status === 'activating' ? 'wordt geactiveerd' : 'nog niet verstuurd'}</Chip>
          )}
          {k.access === false && k.fixable && (
            <Chip k="o" title="Er is nog geen GDAP-toewijzing voor jou. De app regelt de toewijzing (AdminAgents) en de koppeling automatisch bij openen; de eerste keer duurt dat 1 tot 2 minuten.">
              <ShieldAlert size={12} />Geen toegang: wordt automatisch geregeld</Chip>
          )}
          {k.access === false && !k.fixable && !k.pending && (
            <Chip k="r" title="De GDAP-relatie met deze klant bevat geen Application Administrator of Cloud Application Administrator. Maak in het partnerportaal een nieuwe relatie met die rol en laat de klant hem goedkeuren.">
              <ShieldAlert size={12} />Geen toegang: nieuwe GDAP-relatie nodig</Chip>
          )}
          {k.missing && k.missing.length > 0 && (
            <Chip k="o" title={'Ontbrekende GDAP-rollen voor: ' + k.missing.join(', ')}><ShieldAlert size={12} />Beperkt: {k.missing.join(', ')}</Chip>
          )}
          {k.end && (
            <Chip k={verloopt ? 'r' : 'mu'} title={'GDAP-relatie loopt tot ' + datum(k.end)}>
              {verloopt ? <AlertTriangle size={12} /> : <Clock size={12} />}GDAP {verloopt ? `verloopt over ${k.days} dagen` : 'tot ' + datum(k.end)}
            </Chip>
          )}
          {!compact && k.roles && k.roles.length > 0 && <Chip title={k.roles.join('\n')}>{k.roles.length} {k.roles.length === 1 ? 'rol' : 'rollen'}</Chip>}
        </div>
        <ChevronRight size={18} className="go" />
      </div>
    );
  };

  const inhoud = (
    <>
      <div className="kzoek">
        <SearchBox value={q} onChange={setQ} placeholder="Zoek klant op naam, domein of tenant-ID..." autoFocus onKeyDown={toets} />
        {onRefresh && <Btn icon={RefreshCw} onClick={onRefresh} title="Lijst opnieuw ophalen uit het partnerportaal">Vernieuwen</Btn>}
      </div>
      <div className="filters">
        {FILTERS.map(([k, l]) => (
          <button key={k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>{l}<span>{telling[k]}</span></button>
        ))}
      </div>
      <div className="klist" ref={lijstRef} style={compact ? { maxHeight: '52vh', overflow: 'auto' } : undefined}>
        {lijst.map(rij)}
        {!lijst.length && <div className="krow" style={{ cursor: 'default', color: 'var(--mu)' }}>Geen klanten gevonden.</div>}
      </div>
      <div className="kbd-hint"><span><kbd>↑</kbd> <kbd>↓</kbd> kiezen</span><span><kbd>Enter</kbd> openen</span><span><kbd>Esc</kbd> sluiten</span>
        <span style={{ marginLeft: 'auto' }}>{ververst && <span className="ververst"><span className="spin" />Lijst bijwerken... </span>}{klanten.length - 1} klanten met een GDAP-relatie</span></div>
    </>
  );

  if (compact) {
    return (
      <div>
        <div className="headrow" style={{ marginBottom: 2 }}>
          <h3 className="m" style={{ margin: 0 }}>Wissel van klant</h3>
          {onOverzicht && <Btn s onClick={onOverzicht}>Volledig overzicht</Btn>}
          <Btn s onClick={onClose} icon={X}>Sluiten</Btn>
        </div>
        {inhoud}
      </div>
    );
  }
  return (
    <div className="klanten">
      <div className="headrow">
        <div className="m">
          <h2>Kies een klant</h2>
          <p className="sub" style={{ margin: 0 }}>
            {user && user.name ? `Welkom ${user.name.split(' ')[0]}. ` : ''}Dit zijn de klanten waarmee Justdata een actieve GDAP-relatie heeft (zoals in het Microsoft 365-partnerportaal).
          </p>
        </div>
        {onTerug && <Btn icon={ArrowLeft} onClick={onTerug}>Terug naar huidige klant</Btn>}
      </div>
      {klus && klus.bezig ? (
        <div className="updbalk" style={{ marginTop: 16 }}>
          <span className="spin" />
          <div style={{ flex: 1 }}>
            <b>Toegang regelen: {klus.klaar} van {klus.totaal} klanten</b> (3 tegelijk, per klant 1 tot 2 minuten). Je kunt intussen gewoon verder werken.
            <div className="bar" style={{ marginTop: 6 }}><i style={{ width: `${klus.totaal ? (klus.klaar / klus.totaal) * 100 : 0}%` }} /></div>
          </div>
        </div>
      ) : regelbaar > 0 && onRegelAlles ? (
        <div className="updbalk" style={{ marginTop: 16 }}>
          <ShieldAlert size={18} style={{ flex: 'none' }} />
          <div style={{ flex: 1 }}><b>Bij {regelbaar} {regelbaar === 1 ? 'klant' : 'klanten'} heb je nog geen toegang.</b> De app kan de GDAP-toewijzing (AdminAgents, zonder Global Administrator) en de koppeling voor je regelen.</div>
          <Btn s v="p" icon={ShieldAlert} onClick={onRegelAlles}>Toegang regelen voor {regelbaar}</Btn>
        </div>
      ) : null}
      {klus && !klus.bezig && klus.fouten && klus.fouten.length > 0 && (
        <div className="msg warn" style={{ marginTop: 12 }}>
          <AlertTriangle size={17} />
          <div><b>Bij {klus.fouten.length} klant(en) lukte het niet:</b>{klus.fouten.slice(0, 8).map((f) => <div key={f.name}>{f.name}: {f.error}</div>)}</div>
        </div>
      )}
      {inhoud}
    </div>
  );
}
