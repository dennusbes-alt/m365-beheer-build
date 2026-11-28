// Automatisering: processen opbouwen uit bouwstenen en uitvoeren bij een of meer klanten.
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown, ArrowLeft, ArrowUp, BookOpen, Braces, Lock, UsersRound, CheckCircle2, ChevronDown, ChevronRight, CircleDashed, ClipboardCheck, Copy, Download, Flag,
  GitBranch, GripVertical, Library, Loader2, Mail, MonitorSmartphone, Play, Plus, Save, SkipForward, Ticket, Trash2, Users, Workflow, XCircle, Zap,
} from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, toast } from '../overlays.jsx';
import { useApp } from '../store.jsx';
import { Btn, Card, Check, Chip, Loading, SearchBox, Tabs, csv } from '../ui.jsx';

const GROEPEN = {
  Logica: { kleur: '#6b4fd8', icoon: GitBranch },
  'Gebruikers en licenties': { kleur: '#1b7ea9', icoon: Users },
  'Groepen, Teams en gasten': { kleur: '#4f7cf0', icoon: UsersRound },
  'Exchange en postvakken': { kleur: '#00aeef', icoon: Mail },
  'Apparaten en Intune': { kleur: '#003f6b', icoon: MonitorSmartphone },
  Autotask: { kleur: '#d9531e', icoon: Ticket },
  'Documentatie (IT Glue)': { kleur: '#1f9d6b', icoon: BookOpen },
  'Controles en rapportage': { kleur: '#c77700', icoon: ClipboardCheck },
};
const TAKNAAM = { ja: 'Ja', nee: 'Nee', stappen: 'Voor elk item' };
// Lijst met stappen op een pad: [] = hoofdlijn, [i, 'ja'] = tak 'ja' van stap i, [i, 'ja', j, 'stappen'] = dieper
const lijstOp = (o, pad) => {
  let l = o.steps;
  for (let k = 0; k < pad.length; k += 2) {
    const s = l[pad[k]];
    s.children = s.children || {};
    s.children[pad[k + 1]] = s.children[pad[k + 1]] || [];
    l = s.children[pad[k + 1]];
  }
  return l;
};
const telStappen = (l) => (l || []).reduce((n, s) => n + 1 + Object.values(s.children || {}).reduce((m, t) => m + telStappen(t), 0), 0);
const OPS = [['gevuld', 'is ingevuld'], ['leeg', 'is leeg'], ['gelijk', 'is gelijk aan'], ['niet', 'is niet gelijk aan'], ['bevat', 'bevat'], ['ja', 'is ja'], ['nee', 'is nee']];
const nieuwId = () => 's' + Math.random().toString(36).slice(2, 8);
const leegProces = () => ({ name: '', description: '', inputs: [], steps: [], scope: 'team' });
const kopie = (x) => JSON.parse(JSON.stringify(x));

export default function Automatisering() {
  const [meta, setMeta] = useState(null);
  const [lijst, setLijst] = useState(null);
  const [opslag, setOpslag] = useState('');
  const [scherm, setScherm] = useState('bibliotheek');
  const [proces, setProces] = useState(null);
  const laad = async () => {
    const x = await act('auto.lijst', {}, { quiet: true });
    if (x) { setLijst(x.processes); setOpslag(x.storage); } else setLijst([]);
  };
  useEffect(() => { act('auto.blokken', {}).then((x) => setMeta(x || { blocks: [], templates: [] })); laad(); }, []);
  if (!meta || !lijst) return <Loading text="Automatiseringen ophalen..." />;
  const open = (p, waar) => { setProces(kopie(p)); setScherm(waar); };
  return (
    <>
      {scherm === 'bibliotheek' && <Bibliotheek meta={meta} lijst={lijst} opslag={opslag} onOpen={open} onVernieuw={laad} />}
      {scherm === 'bouwer' && <Bouwer meta={meta} start={proces} onTerug={() => { setScherm('bibliotheek'); laad(); }}
        onUitvoeren={(p) => open(p, 'uitvoeren')} onOpgeslagen={(p) => { setProces(p); laad(); }} />}
      {scherm === 'uitvoeren' && <Uitvoeren meta={meta} proces={proces} onTerug={() => setScherm('bibliotheek')} onBewerken={() => setScherm('bouwer')} />}
    </>
  );
}

// ---------------------------------------------------------------- Bibliotheek
function Bibliotheek({ meta, lijst, opslag, onOpen, onVernieuw }) {
  const [q, setQ] = useState('');
  const gedeeld = opslag === 'sharepoint';
  const [soort, setSoort] = useState(() => { try { return localStorage.getItem('autoSoort') || 'team'; } catch { return 'team'; } });
  const kies = (k) => { setSoort(k); try { localStorage.setItem('autoSoort', k); } catch { /* niet erg */ } };
  const zoek = (p) => !q || `${p.name} ${p.description} ${p.owner || ''}`.toLowerCase().includes(q.toLowerCase());
  const team = lijst.filter((p) => p.scope !== 'eigen');
  const mijn = lijst.filter((p) => p.scope === 'eigen');
  const toon = (gedeeld ? (soort === 'team' ? team : mijn) : lijst).filter(zoek);
  const weg = async (p) => {
    const extra = gedeeld && p.scope !== 'eigen' ? `\n\nDit is een teamproces: het verdwijnt ook bij je collega's.${p.mine ? '' : `\nGemaakt door ${p.owner || 'een collega'}.`}` : '';
    if (!await ask(`Proces '${p.name}' verwijderen?${extra}`, 'Verwijderen', true)) return;
    if (await act('auto.verwijderen', { id: p.id }, { msg: 'Verwijderen...' })) onVernieuw();
  };
  const verplaats = async (p) => {
    const naar = p.scope === 'eigen' ? 'team' : 'eigen';
    const vraag = naar === 'team' ? `'${p.name}' delen met het team?\n\nAlle collega's kunnen het dan vinden, uitvoeren en aanpassen.`
      : `'${p.name}' terugzetten naar je eigen processen?\n\nCollega's zien het dan niet meer in de app.`;
    if (!await ask(vraag, naar === 'team' ? 'Delen met team' : 'Naar mijn processen')) return;
    if (await act('auto.opslaan', { process: { ...p, scope: naar } }, { msg: 'Verplaatsen...' })) { kies(naar); onVernieuw(); }
  };
  const tegel = (p, sjabloon) => (
    <div key={p.id} className="card autotegel">
      <div className="headrow" style={{ alignItems: 'flex-start' }}>
        <div className="m"><h3 style={{ margin: 0 }}><Workflow size={17} />{p.name}</h3>
          <div className="hint" style={{ margin: '4px 0 0' }}>{p.description || 'Geen omschrijving'}</div></div>
      </div>
      <div className="stappenstrip">{(p.steps || []).map((s, i) => {
        const b = meta.blocks.find((x) => x.key === s.block);
        const g = GROEPEN[b?.group] || {};
        return <span key={i} title={b?.name} style={{ background: g.kleur || '#999' }} />;
      })}</div>
      <div className="hint" style={{ margin: '6px 0 10px' }}>{(p.steps || []).length} stappen
        {!sjabloon && gedeeld && p.owner ? ` · gemaakt door ${p.mine ? 'jou' : p.owner}` : ''}{p.by && p.by !== p.owner ? ` · gewijzigd door ${p.by}` : ''}</div>
      <div className="btns">
        <Btn s v="p" icon={Play} onClick={() => onOpen(sjabloon ? { ...kopie(p), id: undefined } : p, 'uitvoeren')}>Uitvoeren</Btn>
        <Btn s icon={sjabloon ? Copy : Workflow} onClick={() => onOpen(sjabloon ? { ...kopie(p), id: undefined, template: undefined, scope: gedeeld ? soort : 'team', name: `${p.name} (aangepast)` } : p, 'bouwer')}>{sjabloon ? 'Kopiëren en aanpassen' : 'Bewerken'}</Btn>
        {!sjabloon && <Btn s icon={Copy} onClick={() => onOpen({ ...kopie(p), id: undefined, mine: true, owner: undefined, name: `${p.name} (kopie)` }, 'bouwer')} title="Dupliceren" />}
        {!sjabloon && gedeeld && p.mine && <Btn s icon={p.scope === 'eigen' ? UsersRound : Lock} onClick={() => verplaats(p)}
          title={p.scope === 'eigen' ? 'Delen met het team' : 'Terugzetten naar mijn processen'}>{p.scope === 'eigen' ? 'Delen met team' : null}</Btn>}
        {!sjabloon && <Btn s v="dl" icon={Trash2} onClick={() => weg(p)} title="Verwijderen" />}
      </div>
    </div>
  );
  return (
    <>
      <h2>Automatisering</h2>
      <p className="sub">Bouw processen uit bouwstenen en voer ze in één keer uit bij een of meer klanten: van een nieuwe medewerker tot een maandelijkse controle.</p>
      {opslag === 'lokaal' && <Msg kind="warn">Processen worden nu op deze computer bewaard. Voor gedeelde opslag in SharePoint (voor alle collega's) moet de app-registratie in de Justdata-tenant nog eenmalig worden bijgewerkt.</Msg>}
      <div className="row" style={{ marginBottom: 14, alignItems: 'center' }}>
        <SearchBox value={q} onChange={setQ} placeholder="Zoek proces..." />
        <div className="n"><Btn v="p" icon={Plus} onClick={() => onOpen({ ...leegProces(), scope: gedeeld ? soort : 'team' }, 'bouwer')}>Nieuw proces</Btn></div>
      </div>
      {gedeeld ? (
        <Tabs value={soort} onChange={kies} tabs={[['team', `Teamprocessen (${team.length})`, UsersRound], ['eigen', `Mijn processen (${mijn.length})`, Lock]]} />
      ) : <h3 className="kopje"><Library size={17} />Processen op deze computer</h3>}
      {gedeeld && <div className="hint" style={{ margin: '0 0 10px' }}>{soort === 'team'
        ? "Teamprocessen zien alle collega's in de app; iedereen kan ze uitvoeren en aanpassen. Nieuwe processen van collega's verschijnen hier vanzelf."
        : "Mijn processen zie alleen jij in de app (handig om eerst te testen). Met 'Delen met team' zet je een proces bij de teamprocessen."}</div>}
      <div className="autogrid">
        {toon.map((p) => tegel(p, false))}
        {!toon.length && <div className="card muted" onClick={() => onOpen({ ...leegProces(), scope: gedeeld ? soort : 'team' }, 'bouwer')} style={{ cursor: 'pointer' }}><Plus size={18} />
          {q ? 'Geen processen gevonden.' : 'Nog geen processen.'} Begin met een nieuw proces of kopieer een sjabloon.</div>}
      </div>
      <h3 className="kopje" style={{ marginTop: 22 }}><Zap size={17} />Sjablonen</h3>
      <div className="autogrid">{meta.templates.map((p) => tegel(p, true))}</div>
    </>
  );
}

// ---------------------------------------------------------------- Bouwer
function Bouwer({ meta, start, onTerug, onUitvoeren, onOpgeslagen }) {
  const [p, setP] = useState(() => ({ ...leegProces(), ...start, steps: (start.steps || []).map((s) => ({ ...s, id: s.id || nieuwId() })) }));
  const [open, setOpen] = useState(() => new Set());
  const [invoegen, setInvoegen] = useState({ pad: [], index: null });   // waar de volgende bouwsteen komt (index null = achteraan in die lijst)
  const [sleep, setSleep] = useState(null);
  const [gewijzigd, setGewijzigd] = useState(!start.id);
  const zet = (fn) => { setP((o) => fn(kopie(o))); setGewijzigd(true); };
  const blokVan = (k) => meta.blocks.find((b) => b.key === k);
  const zelfdePad = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  // Beschikbare variabelen op een plek: startgegevens, klantgegevens, uitkomsten van eerdere stappen op de hoofdlijn,
  // stappen met een eigen naam, en {{item}}/{{index}} binnen 'voor elk'
  const variabelen = (pad, i) => {
    const tot = pad.length ? pad[0] : i;
    const namen = [];
    const loop = (l) => l.forEach((s) => { if (s.alias) (blokVan(s.block)?.outputs || []).forEach((o) => namen.push({ v: `${s.alias}.${o}`, l: `${o} (${s.alias}: ${blokVan(s.block)?.name})`, g: 'Uitkomsten' })); Object.values(s.children || {}).forEach(loop); });
    loop(p.steps);
    return [
      ...p.inputs.map((x) => ({ v: x.key, l: x.label || x.key, g: 'Startgegevens' })),
      { v: 'klant', l: 'Naam van de klant', g: 'Klant' }, { v: 'klantdomein', l: 'Standaarddomein van de klant', g: 'Klant' }, { v: 'datum', l: 'Datum van vandaag', g: 'Klant' },
      ...(pad.includes('stappen') ? [{ v: 'item', l: 'Het huidige item (voor elk)', g: 'Klant' }, { v: 'index', l: 'Nummer van het item (1, 2, 3...)', g: 'Klant' }] : []),
      ...p.steps.slice(0, tot).flatMap((s, k) => (blokVan(s.block)?.outputs || []).map((o) => ({ v: `stap${k + 1}.${o}`, l: `${o} (stap ${k + 1}: ${blokVan(s.block)?.name})`, g: 'Uitkomsten' }))),
      ...namen,
    ];
  };
  const toevoegen = (b) => {
    const params = {};
    b.fields.forEach((f) => { if (f.default !== undefined) params[f.key] = f.default; else if (f.placeholder && f.placeholder.includes('{{')) params[f.key] = f.placeholder; });
    const stap = { id: nieuwId(), block: b.key, params, onError: 'stop', ...(b.branches?.length ? { children: Object.fromEntries(b.branches.map((t) => [t, []])) } : {}) };
    zet((o) => { const l = lijstOp(o, invoegen.pad); l.splice(invoegen.index ?? l.length, 0, stap); return o; });
    setOpen((s) => new Set([...s, stap.id]));
    setInvoegen({ pad: invoegen.pad, index: null });
  };
  const verplaats = (pad, van, naar) => zet((o) => { const l = lijstOp(o, pad); const [x] = l.splice(van, 1); l.splice(naar, 0, x); return o; });
  const plekTekst = invoegen.pad.length
    ? `in tak '${TAKNAAM[invoegen.pad[invoegen.pad.length - 1]]}' van stap ${invoegen.pad[0] + 1}${invoegen.index != null ? `, vóór stap ${invoegen.index + 1}` : ', achteraan'}`
    : (invoegen.index == null ? 'achteraan' : `vóór stap ${invoegen.index + 1}`);

  // Eén baan (hoofdlijn of tak) met stappen, verbindingen en een '+' tussen elke stap
  const Baan = ({ pad, stappen }) => (
    <>
      {stappen.map((s, i) => {
        const b = blokVan(s.block);
        const g = GROEPEN[b?.group] || { kleur: '#999', icoon: Workflow };
        const I = g.icoon;
        const isOpen = open.has(s.id);
        const sleutel = JSON.stringify([...pad, i]);
        return (
          <Fragment key={s.id}>
            <Verbinding actief={zelfdePad(invoegen.pad, pad) && invoegen.index === i} onPlus={() => setInvoegen(zelfdePad(invoegen.pad, pad) && invoegen.index === i ? { pad: [], index: null } : { pad, index: i })} />
            <div className={'blok' + (sleep === sleutel ? ' sleep' : '') + (b?.branches?.length ? ' container' : '')} style={{ '--k': g.kleur }} draggable
              onDragStart={(e) => { e.stopPropagation(); setSleep(sleutel); e.dataTransfer.effectAllowed = 'move'; }} onDragEnd={() => setSleep(null)}
              onDragOver={(e) => e.preventDefault()} onDrop={(e) => {
                e.preventDefault(); e.stopPropagation();
                const van = sleep ? JSON.parse(sleep) : null;
                if (van && zelfdePad(van.slice(0, -1), pad) && van[van.length - 1] !== i) verplaats(pad, van[van.length - 1], i);
                setSleep(null);
              }}>
              <div className="blokkop" onClick={() => setOpen((x) => { const n = new Set(x); if (n.has(s.id)) n.delete(s.id); else n.add(s.id); return n; })}>
                <GripVertical size={15} className="greep" />
                <span className="nr">{pad.length ? `${pad.filter((x) => typeof x === 'number').map((x) => x + 1).join('.')}.${i + 1}` : i + 1}</span>
                <span className="ic"><I size={16} /></span>
                <span className="m"><b>{b?.name || s.block}{s.alias ? <code className="varchip" style={{ marginLeft: 6 }}>{s.alias}</code> : null}</b><small>{samenvatting(b, s)}</small></span>
                {s.when && s.when.veld && <Chip k="mu" title="Voorwaarde">alleen als {s.when.veld} {(OPS.find((o) => o[0] === s.when.op) || [])[1]} {s.when.waarde || ''}</Chip>}
                {s.onError === 'continue' && <Chip k="o">doorgaan bij fout</Chip>}
                <span className="btns" onClick={(e) => e.stopPropagation()}>
                  <button className="btn s" disabled={i === 0} onClick={() => verplaats(pad, i, i - 1)} title="Omhoog"><ArrowUp size={13} /></button>
                  <button className="btn s" disabled={i === stappen.length - 1} onClick={() => verplaats(pad, i, i + 1)} title="Omlaag"><ArrowDown size={13} /></button>
                  <button className="btn s" onClick={() => zet((o) => { const l = lijstOp(o, pad); const nieuw = kopie(s); const ids = (x) => { x.id = nieuwId(); Object.values(x.children || {}).forEach((t) => t.forEach(ids)); }; ids(nieuw); l.splice(i + 1, 0, nieuw); return o; })} title="Dupliceren"><Copy size={13} /></button>
                  <button className="btn s dl" onClick={() => zet((o) => { lijstOp(o, pad).splice(i, 1); return o; })} title="Verwijderen"><Trash2 size={13} /></button>
                </span>
                {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </div>
              {isOpen && b && <StapInstellingen b={b} s={s} vars={variabelen(pad, i)} nr={pad.length ? null : i + 1}
                zetStap={(fn) => zet((o) => { const l = lijstOp(o, pad); l[i] = fn(l[i]); return o; })} />}
              {b?.branches?.length > 0 && (
                <div className={'takken' + (b.branches.length > 1 ? ' twee' : '')}>
                  {b.branches.map((t) => (
                    <div key={t} className={'tak tak-' + t}>
                      <div className="takkop">{TAKNAAM[t] || t}</div>
                      {Baan({ pad: [...pad, i, t], stappen: (s.children || {})[t] || [] })}
                    </div>))}
                </div>)}
            </div>
          </Fragment>
        );
      })}
      <Verbinding actief={zelfdePad(invoegen.pad, pad) && invoegen.index === null && (pad.length > 0 || true)} onPlus={() => setInvoegen({ pad, index: null })} laatste />
      {pad.length > 0 && !stappen.length && <div className="hint" style={{ margin: '0 0 6px', textAlign: 'center' }}>Klik op + en kies rechts een bouwsteen</div>}
    </>
  );
  const opslaan = async () => {
    const x = await act('auto.opslaan', { process: p }, { msg: 'Proces opslaan...' });
    if (x) {
      const extra = { id: x.process.id, scope: x.process.scope, mine: x.process.mine, owner: x.process.owner };
      setP((o) => ({ ...o, ...extra })); setGewijzigd(false); onOpgeslagen({ ...p, ...extra });
    }
  };
  const terug = async () => { if (!gewijzigd || await ask('Je wijzigingen zijn nog niet opgeslagen. Toch terug?', 'Terug zonder opslaan', true)) onTerug(); };

  return (
    <>
      <div className="headrow" style={{ marginBottom: 12 }}>
        <div className="m" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Btn s icon={ArrowLeft} onClick={terug}>Bibliotheek</Btn>
          <h2 style={{ margin: 0 }}>{p.name || 'Nieuw proces'}</h2>{gewijzigd && <Chip k="o">niet opgeslagen</Chip>}
        </div>
        <div className="btns">
          <Btn icon={Play} disabled={!p.steps.length} onClick={() => onUitvoeren(p)}>Uitvoeren</Btn>
          <Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn>
        </div>
      </div>
      <div className="bouwer">
        <div>
          <Card>
            <div className="row">
              <div style={{ flex: 1 }}><label className="f" style={{ marginTop: 0 }}>Naam van het proces</label>
                <input type="text" value={p.name} onChange={(e) => zet((o) => ({ ...o, name: e.target.value }))} placeholder="Bijv. Nieuwe medewerker verkoop" /></div>
              <div style={{ flex: 2 }}><label className="f" style={{ marginTop: 0 }}>Omschrijving</label>
                <input type="text" value={p.description} onChange={(e) => zet((o) => ({ ...o, description: e.target.value }))} placeholder="Wat doet dit proces?" /></div>
              <div className="n"><label className="f" style={{ marginTop: 0 }}>Zichtbaar voor</label>
                <select value={p.scope === 'eigen' ? 'eigen' : 'team'} disabled={!!p.id && p.mine === false} onChange={(e) => zet((o) => ({ ...o, scope: e.target.value }))}
                  title={p.id && p.mine === false ? `Gemaakt door ${p.owner || 'een collega'}; alleen de maker kan dit wijzigen` : ''}>
                  <option value="team">Het hele team</option><option value="eigen">Alleen mij</option>
                </select></div>
            </div>
          </Card>

          <div className="flow">
            <Startgegevens p={p} zet={zet} />
            {Baan({ pad: [], stappen: p.steps })}
            <div className="eindknoop"><Flag size={15} />{p.steps.length ? `Klaar · ${telStappen(p.steps)} stappen` : 'Kies rechts een bouwsteen om te beginnen'}</div>
          </div>
        </div>
        <Palet meta={meta} onKies={toevoegen} plek={plekTekst} />
      </div>
    </>
  );
}

function samenvatting(b, s) {
  if (!b) return '';
  const delen = b.fields.filter((f) => f.type !== 'vink' && s.params?.[f.key]).slice(0, 3).map((f) => `${f.label.split(' (')[0]}: ${s.params[f.key]}`);
  return delen.join(' · ') || b.help;
}

function Verbinding({ actief, onPlus, laatste }) {
  return (
    <div className={'verbinding' + (actief ? ' actief' : '')}>
      <span className="lijn" />
      <button className="plus" onClick={onPlus} title={laatste ? 'Bouwsteen achteraan toevoegen' : 'Bouwsteen hier invoegen'}><Plus size={13} /></button>
      {actief && <span className="hint" style={{ margin: 0 }}>{laatste ? 'Nieuwe bouwsteen komt hier' : 'Nieuwe bouwsteen wordt hier ingevoegd'}</span>}
    </div>
  );
}

function Startgegevens({ p, zet }) {
  const [open, setOpen] = useState(!p.inputs.length);
  return (
    <div className="blok start" style={{ '--k': '#323841' }}>
      <div className="blokkop" onClick={() => setOpen(!open)}>
        <span className="ic"><Play size={15} /></span>
        <span className="m"><b>Start: gegevens die je bij het uitvoeren invult</b>
          <small>{p.inputs.length ? p.inputs.map((x) => `{{${x.key}}}`).join('  ') : 'Geen startgegevens (bijv. voor een controle)'}</small></span>
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </div>
      {open && (
        <div className="blokinhoud">
          {p.inputs.map((x, i) => (
            <div key={i} className="row" style={{ alignItems: 'center', marginBottom: 6 }}>
              <input type="text" value={x.label} placeholder="Omschrijving, bijv. Voornaam" onChange={(e) => zet((o) => {
                const oud = o.inputs[i]; const lab = e.target.value;
                const auto = !oud.key || oud.key === sleutelVan(oud.label || '');
                o.inputs[i] = { ...oud, label: lab, key: auto ? sleutelVan(lab) : oud.key }; return o;
              })} />
              <input type="text" value={x.key} placeholder="variabele" style={{ maxWidth: 160, fontFamily: 'ui-monospace, Consolas, monospace' }}
                onChange={(e) => zet((o) => { o.inputs[i].key = sleutelVan(e.target.value); return o; })} />
              <input type="text" value={x.default || ''} placeholder="standaardwaarde" style={{ maxWidth: 200 }} onChange={(e) => zet((o) => { o.inputs[i].default = e.target.value; return o; })} />
              <label className="chk n"><input type="checkbox" checked={!!x.required} onChange={(e) => zet((o) => { o.inputs[i].required = e.target.checked; return o; })} />verplicht</label>
              <button className="btn s dl" onClick={() => zet((o) => { o.inputs.splice(i, 1); return o; })}><Trash2 size={13} /></button>
            </div>
          ))}
          <Btn s icon={Plus} onClick={() => zet((o) => { o.inputs.push({ key: '', label: '', required: false }); return o; })}>Startgegeven toevoegen</Btn>
          <div className="hint">Gebruik een startgegeven in een stap als <code>{'{{variabele}}'}</code>, bijvoorbeeld <code>{'{{voornaam|alias}}'}</code> (filters: klein, groot, alias, zonderspaties, zonderaccenten, eerste).</div>
        </div>
      )}
    </div>
  );
}
const sleutelVan = (t) => String(t || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '').slice(0, 30);

function StapInstellingen({ b, s, vars, nr, zetStap }) {
  const zetP = (k, v) => zetStap((o) => ({ ...o, params: { ...(o.params || {}), [k]: v } }));
  const w = s.when || {};
  return (
    <div className="blokinhoud">
      {b.help && <div className="hint" style={{ marginTop: 0 }}>{b.help}</div>}
      <div className="velden">
        {b.fields.map((f) => (
          <div key={f.key} className={f.type === 'tekstvak' ? 'breed' : ''}>
            {f.type === 'vink' ? <Check checked={s.params?.[f.key] === true || s.params?.[f.key] === 'ja'} onChange={(v) => zetP(f.key, v)}>{f.label}</Check> : (
              <>
                <label className="f">{f.label}{f.required && ' *'}</label>
                <div className="metvar">
                  {f.type === 'keuze' ? (
                    <select value={s.params?.[f.key] ?? f.default ?? ''} onChange={(e) => zetP(f.key, e.target.value)}>{f.opties.map((o) => <option key={o}>{o}</option>)}</select>
                  ) : f.type === 'tekstvak' ? (
                    <textarea rows={2} value={s.params?.[f.key] ?? ''} placeholder={f.placeholder || ''} onChange={(e) => zetP(f.key, e.target.value)} />
                  ) : (
                    <input type={f.type === 'wachtwoord' ? 'password' : 'text'} value={s.params?.[f.key] ?? ''} placeholder={f.placeholder || ''} autoComplete="off"
                      onChange={(e) => zetP(f.key, e.target.value)} />
                  )}
                  {f.type !== 'keuze' && <VarKnop vars={vars} onKies={(v) => zetP(f.key, `${s.params?.[f.key] || ''}{{${v}}}`)} />}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
      <div className="row stapopties">
        <div><label className="f">Alleen uitvoeren als</label>
          <div className="row" style={{ gap: 6 }}>
            <select value={w.veld || ''} onChange={(e) => zetStap((o) => ({ ...o, when: e.target.value ? { op: 'gevuld', ...(o.when || {}), veld: e.target.value } : null }))}>
              <option value="">altijd uitvoeren</option>{vars.map((v) => <option key={v.v} value={v.v}>{v.v}</option>)}</select>
            {w.veld && <select value={w.op || 'gevuld'} onChange={(e) => zetStap((o) => ({ ...o, when: { ...o.when, op: e.target.value } }))}>{OPS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}
            {w.veld && ['gelijk', 'niet', 'bevat'].includes(w.op) && <input type="text" value={w.waarde || ''} placeholder="waarde" onChange={(e) => zetStap((o) => ({ ...o, when: { ...o.when, waarde: e.target.value } }))} />}
          </div></div>
        <div><label className="f">Bij een fout</label>
          <select value={s.onError || 'stop'} onChange={(e) => zetStap((o) => ({ ...o, onError: e.target.value }))}>
            <option value="stop">proces stoppen</option><option value="continue">doorgaan met de volgende stap</option></select></div>
        {b.outputs.length > 0 && (
          <div><label className="f">Naam voor de uitkomst (optioneel)</label>
            <input type="text" value={s.alias || ''} placeholder={nr ? `stap${nr}` : 'bijv. ticket'} style={{ maxWidth: 180 }}
              onChange={(e) => zetStap((o) => ({ ...o, alias: e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '') || undefined }))} /></div>)}
      </div>
      {b.outputs.length > 0 && (
        <div className="hint">Uitkomsten voor latere stappen: {b.outputs.map((o) => {
          const v = `{{${s.alias || (nr ? `stap${nr}` : '?')}.${o}}}`;
          return <code key={o} className="varchip" onClick={() => navigator.clipboard?.writeText(v).then(() => toast('Gekopieerd.', 'g'), () => {})}>{v}</code>;
        })}{!nr && !s.alias && <span> · geef deze stap een naam om de uitkomst later te gebruiken</span>}</div>
      )}
    </div>
  );
}

function VarKnop({ vars, onKies }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const k = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', k);
    return () => document.removeEventListener('mousedown', k);
  }, [open]);
  return (
    <span className="varknop" ref={ref}>
      <button className="btn s" type="button" title="Variabele invoegen" onClick={() => setOpen(!open)}><Braces size={14} /></button>
      {open && (
        <div className="varmenu">
          {['Startgegevens', 'Klant', 'Uitkomsten'].map((g) => {
            const l = vars.filter((v) => v.g === g);
            return l.length ? <div key={g}><div className="grp">{g}</div>{l.map((v) => (
              <button key={v.v} onClick={() => { onKies(v.v); setOpen(false); }}><code>{`{{${v.v}}}`}</code><small>{v.l}</small></button>))}</div> : null;
          })}
        </div>
      )}
    </span>
  );
}

function Palet({ meta, onKies, plek }) {
  const [q, setQ] = useState('');
  const groepen = useMemo(() => Object.keys(GROEPEN).map((g) => [g, meta.blocks.filter((b) => b.group === g && (!q || `${b.name} ${b.help}`.toLowerCase().includes(q.toLowerCase())))]), [meta, q]);
  return (
    <div className="palet sticky">
      <Card title="Bouwstenen" icon={Workflow}>
        <SearchBox value={q} onChange={setQ} placeholder="Zoek bouwsteen..." />
        <div className="hint" style={{ margin: '6px 0' }}>Klik om toe te voegen ({plek}).</div>
        <div className="paletlijst">
          {groepen.map(([g, l]) => l.length > 0 && (
            <div key={g}>
              <div className="grp" style={{ color: GROEPEN[g].kleur }}>{g}</div>
              {l.map((b) => { const I = GROEPEN[g].icoon; return (
                <button key={b.key} className="paletblok" style={{ '--k': GROEPEN[g].kleur }} onClick={() => onKies(b)} title={b.help}>
                  <span className="ic"><I size={14} /></span><span className="m"><b>{b.name}</b><small>{b.help}</small></span><Plus size={14} />
                </button>
              ); })}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- Uitvoeren
function Uitvoeren({ meta, proces, onTerug, onBewerken }) {
  const { info } = useApp();
  const [klanten, setKlanten] = useState(null);
  const [gekozen, setGekozen] = useState(() => new Set(info ? [info.tenantId] : []));
  const [q, setQ] = useState('');
  const [rijen, setRijen] = useState([{}]);
  const [run, setRun] = useState(null);
  const timer = useRef(null);
  useEffect(() => { act('customers', {}, { quiet: true }).then((x) => setKlanten(x ? x.customers.filter((k) => k.access !== false) : [])); return () => clearTimeout(timer.current); }, []);
  const volg = async (id) => {
    const x = await act('auto.status', { id }, { quiet: true });
    if (x) setRun(x);
    if (!x || x.bezig) timer.current = setTimeout(() => volg(id), 1200);
  };
  const inputs = proces.inputs || [];
  const startNu = async () => {
    const lijst = (klanten || []).filter((k) => gekozen.has(k.id)).map((k) => ({ id: k.id, name: k.name }));
    if (!lijst.length) return toast('Kies minimaal één klant.', 'e');
    const r = rijen.filter((x) => inputs.length === 0 || Object.values(x).some((v) => String(v || '').trim()));
    const aantal = lijst.length * Math.max(1, r.length);
    if (!await ask(`Proces '${proces.name || 'Nieuw proces'}' uitvoeren?\n\n${lijst.length} klant(en)${inputs.length ? ` x ${r.length} regel(s)` : ''} = ${aantal} uitvoering(en), elk ${proces.steps.length} stappen.`
      + '\n\nDe stappen worden echt uitgevoerd bij de klant.', 'Uitvoeren')) return;
    const x = await act('auto.start', { process: proces, customers: lijst, rows: r.length ? r : [{}] }, { msg: 'Proces starten...' });
    if (x) { setRun(x); timer.current = setTimeout(() => volg(x.id), 800); }
  };
  const plakken = (tekst) => {
    const regels = tekst.split(/\r?\n/).filter((r) => r.trim());
    if (!regels.length) return;
    const sep = (regels[0].match(/;/g) || []).length > (regels[0].match(/,/g) || []).length ? ';' : (regels[0].includes('\t') ? '\t' : ',');
    const kop = regels[0].split(sep).map((x) => x.trim().toLowerCase());
    const heeftKop = inputs.some((i) => kop.includes(i.key) || kop.includes((i.label || '').toLowerCase()));
    const sleutels = heeftKop ? kop.map((k) => (inputs.find((i) => i.key === k || (i.label || '').toLowerCase() === k) || {}).key || k) : inputs.map((i) => i.key);
    const data = (heeftKop ? regels.slice(1) : regels).map((r) => Object.fromEntries(r.split(sep).map((v, i) => [sleutels[i], v.trim()]).filter(([k]) => k)));
    setRijen(data);
    toast(`${data.length} regel(s) ingelezen.`, 'g');
  };
  if (!klanten) return <Loading text="Klanten ophalen..." />;
  const zichtbaar = klanten.filter((k) => !q || k.name.toLowerCase().includes(q.toLowerCase()));
  const rapport = run ? run.items.flatMap((it) => (it.rapport || []).map((r) => ({ Klant: it.klantnaam, ...(run.items.some((x) => x.regel > 1) ? { Regel: it.regel } : {}), ...r }))) : [];
  const kolommen = [...new Set(rapport.flatMap((r) => Object.keys(r)))];
  return (
    <>
      <div className="headrow" style={{ marginBottom: 12 }}>
        <div className="m" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Btn s icon={ArrowLeft} onClick={onTerug}>Bibliotheek</Btn><h2 style={{ margin: 0 }}>Uitvoeren: {proces.name || 'Nieuw proces'}</h2>
        </div>
        {!proces.template && <Btn icon={Workflow} onClick={onBewerken}>Proces bewerken</Btn>}
      </div>
      {!run ? (
        <div className="cols2" style={{ gridTemplateColumns: 'minmax(280px, 1fr) minmax(0, 2fr)' }}>
          <Card title={`Klanten (${gekozen.size})`} icon={Users} right={<div className="btns">
            <Btn s onClick={() => setGekozen(new Set(zichtbaar.map((k) => k.id)))}>Alle</Btn><Btn s onClick={() => setGekozen(new Set())}>Geen</Btn></div>}>
            <SearchBox value={q} onChange={setQ} placeholder="Zoek klant..." />
            <div className="list" style={{ maxHeight: 420, marginTop: 8 }}>
              {zichtbaar.map((k) => (
                <label key={k.id} className="li" style={{ cursor: 'pointer' }}>
                  <input type="checkbox" checked={gekozen.has(k.id)} onChange={(e) => setGekozen((s) => { const n = new Set(s); if (e.target.checked) n.add(k.id); else n.delete(k.id); return n; })} />
                  <span className="m"><b>{k.name}</b><small>{k.domain || k.id}</small></span>
                </label>
              ))}
            </div>
          </Card>
          <div>
            <Card title={inputs.length ? `Startgegevens (${rijen.length} ${rijen.length === 1 ? 'regel' : 'regels'})` : 'Startgegevens'} icon={Play}
              right={inputs.length ? <div className="btns"><Btn s icon={Plus} onClick={() => setRijen((r) => [...r, {}])}>Regel</Btn></div> : null}>
              {!inputs.length ? <div className="hint" style={{ margin: 0 }}>Dit proces heeft geen startgegevens.</div> : (
                <>
                  <div style={{ overflowX: 'auto' }}><table>
                    <thead><tr>{inputs.map((i) => <th key={i.key}>{i.label || i.key}{i.required && ' *'}</th>)}<th /></tr></thead>
                    <tbody>{rijen.map((r, n) => (
                      <tr key={n}>{inputs.map((i) => <td key={i.key}><input type={/wachtwoord/i.test(i.key) ? 'password' : 'text'} value={r[i.key] ?? ''}
                        placeholder={i.default || ''} onChange={(e) => setRijen((l) => l.map((x, j) => (j === n ? { ...x, [i.key]: e.target.value } : x)))} /></td>)}
                        <td className="r"><button className="btn s dl" disabled={rijen.length === 1} onClick={() => setRijen((l) => l.filter((_, j) => j !== n))}><Trash2 size={13} /></button></td></tr>
                    ))}</tbody>
                  </table></div>
                  <details style={{ marginTop: 10 }}><summary className="hint" style={{ cursor: 'pointer' }}>Veel regels tegelijk? Plak ze hier (uit Excel of CSV)</summary>
                    <textarea rows={4} placeholder={inputs.map((i) => i.key).join(';')} onBlur={(e) => { if (e.target.value.trim()) { plakken(e.target.value); e.target.value = ''; } }} />
                    <div className="hint">Eerste regel mag de kolomnamen bevatten ({inputs.map((i) => i.key).join(', ')}). Scheidingsteken: puntkomma, komma of tab.</div></details>
                </>
              )}
            </Card>
            <Card title={`Stappen (${proces.steps.length})`} icon={Workflow}>
              <ol className="stappenlijst">{proces.steps.map((s, i) => { const b = meta.blocks.find((x) => x.key === s.block); return (
                <li key={i} style={{ '--k': (GROEPEN[b?.group] || {}).kleur }}><b>{b?.name || s.block}</b> <span className="hint" style={{ margin: 0 }}>{samenvatting(b, s)}</span></li>); })}</ol>
              <div className="btns" style={{ marginTop: 12 }}><Btn v="p" icon={Play} onClick={startNu}>Uitvoeren bij {gekozen.size} klant(en)</Btn></div>
            </Card>
          </div>
        </div>
      ) : (
        <>
          <Voortgang run={run} />
          {!run.bezig && (
            <Card title={`Rapport (${rapport.length} regels)`} icon={ClipboardCheck}
              right={<div className="btns"><Btn s icon={Download} disabled={!rapport.length} onClick={() => csv(`${(proces.name || 'proces').replace(/[^\w-]+/g, '-')}-${new Date().toISOString().slice(0, 10)}.csv`, [kolommen, ...rapport.map((r) => kolommen.map((k) => r[k] ?? ''))])}>Exporteren (CSV)</Btn>
                <Btn s icon={Play} onClick={() => setRun(null)}>Opnieuw uitvoeren</Btn></div>}>
              {!rapport.length ? <div className="hint" style={{ margin: 0 }}>Dit proces heeft geen rapportregels opgeleverd.</div> : (
                <div style={{ maxHeight: 420, overflow: 'auto' }}><table className="vastkop">
                  <thead><tr>{kolommen.map((k) => <th key={k}>{k}</th>)}</tr></thead>
                  <tbody>{rapport.slice(0, 500).map((r, i) => <tr key={i}>{kolommen.map((k) => <td key={k}>{String(r[k] ?? '')}</td>)}</tr>)}</tbody>
                </table></div>
              )}
            </Card>
          )}
        </>
      )}
    </>
  );
}

const STATUS_ICOON = { ok: [CheckCircle2, 'var(--gr)'], fout: [XCircle, 'var(--rd)'], bezig: [Loader2, 'var(--cy)'], wachten: [CircleDashed, 'var(--mu)'], overgeslagen: [SkipForward, 'var(--mu)'] };
function Voortgang({ run }) {
  const klaar = run.items.filter((x) => x.status === 'ok' || x.status === 'fout').length;
  const fout = run.items.filter((x) => x.status === 'fout').length;
  return (
    <>
      <div className={run.bezig ? 'updbalk' : `msg ${fout ? 'warn' : 'ok'}`} style={{ marginBottom: 14 }}>
        {run.bezig ? <span className="spin" /> : fout ? <XCircle size={17} /> : <CheckCircle2 size={17} />}
        <div style={{ flex: 1 }}><b>{run.bezig ? `Bezig: ${klaar} van ${run.items.length} uitvoering(en) klaar` : `Klaar: ${run.items.length - fout} gelukt${fout ? `, ${fout} met fouten` : ''}`}</b>
          {run.bezig && <div className="bar" style={{ marginTop: 6 }}><i style={{ width: `${(klaar / run.items.length) * 100}%` }} /></div>}</div>
      </div>
      <div className="autogrid">
        {run.items.map((it, n) => (
          <div key={n} className="card" style={{ marginBottom: 0 }}>
            <div className="headrow"><div className="m"><b>{it.klantnaam}</b>{run.items.some((x) => x.regel > 1) && <span className="hint" style={{ margin: 0 }}> · regel {it.regel}</span>}</div>
              <Chip k={it.status === 'ok' ? 'g' : it.status === 'fout' ? 'r' : 'mu'}>{{ ok: 'gelukt', fout: 'fout', bezig: 'bezig', wachten: 'wacht' }[it.status] || it.status}</Chip></div>
            {it.fout && <div className="hint" style={{ color: 'var(--rd)' }}>{it.fout}</div>}
            <div className="stapstatus">{it.stappen.map((s, i) => { const [I, k] = STATUS_ICOON[s.status] || STATUS_ICOON.wachten; return (
              <div key={i} title={s.melding}><I size={15} style={{ color: k, flex: 'none' }} className={s.status === 'bezig' ? 'draai' : ''} />
                <span><b>{i + 1}. {s.naam}</b>{s.melding && <small style={{ color: s.status === 'fout' ? 'var(--rd)' : undefined }}>{s.melding}</small>}</span></div>); })}</div>
          </div>
        ))}
      </div>
    </>
  );
}
