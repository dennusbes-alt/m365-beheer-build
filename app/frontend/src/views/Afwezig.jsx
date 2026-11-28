// Automatisch antwoord (afwezigheid) per gebruiker of gedeeld postvak, plus een overzicht van wie het nu aan heeft.
import { useEffect, useState } from 'react';
import { startTab } from '../store.jsx';
import { CalendarClock, Forward, ListChecks, MailX, RefreshCw, Save } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, toast } from '../overlays.jsx';
import { getShared, getUsers, useApp } from '../store.jsx';
import { Btn, Card, Check, Chip, Loading, Picker, Tabs, csv, dt } from '../ui.jsx';

const STAND = { Enabled: ['Aan', 'g'], Scheduled: ['Gepland', 'o'], Disabled: ['Uit', 'mu'] };
const DOEL = { All: 'Iedereen buiten de organisatie', Known: 'Alleen bekende afzenders (contactpersonen)', None: 'Niet naar externen' };
// datetime-local verwacht 'jjjj-mm-ddTuu:mm' in lokale tijd
const lokaal = (s) => {
  const d = s ? new Date(s) : null;
  if (!d || isNaN(d) || d.getFullYear() < 2000) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

export default function Afwezig() {
  const { info } = useApp();
  const [tab, setTab] = useState(() => startTab('afwezig', 'instellen'));
  if (info.exo === false) return <><h2>Automatisch antwoord</h2><Msg kind="err">Exchange Online is niet verbonden bij deze klant. Automatisch antwoord is niet beschikbaar.</Msg></>;
  return (
    <>
      <h2>Afwezigheid en doorsturen</h2>
      <p className="sub">Stel per gebruiker of gedeeld postvak een automatisch antwoord in (direct, gepland of uit) of stuur de e-mail door naar een ander adres.</p>
      <Tabs value={tab} onChange={setTab} tabs={[['instellen', 'Automatisch antwoord', CalendarClock], ['overzicht', 'Wie heeft het aan?', ListChecks], ['doorsturen', 'Doorsturen', Forward]]} />
      {tab === 'instellen' ? <Instellen /> : tab === 'doorsturen' ? <Doorsturen /> : <Overzicht kies={() => setTab('instellen')} />}
    </>
  );
}

let gekozen = '';   // onthouden bij wisselen van tabblad (overzicht > bewerken)

function Instellen() {
  const [items, setItems] = useState(null);
  const [mb, setMb] = useState(gekozen);
  const [cfg, setCfg] = useState(null);
  const [fout, setFout] = useState('');

  useEffect(() => {
    Promise.all([getUsers(), getShared()]).then(([u, s]) => setItems([
      ...u.filter((x) => !x.guest && x.on !== false).map((x) => ({ v: x.upn, l: x.name, s: x.upn, k: 'u' })),
      ...s.map((x) => ({ v: x.mail, l: x.name, s: x.mail, k: 's' })),
    ])).catch(() => setItems([]));
  }, []);
  const laad = async (m) => {
    gekozen = m; setMb(m); setCfg(null); setFout('');
    try {
      const d = await api('ar.get', { mailbox: m }, { quiet: true });
      const morgen = new Date(); morgen.setDate(morgen.getDate() + 1); morgen.setHours(9, 0, 0, 0);
      const week = new Date(morgen); week.setDate(week.getDate() + 7); week.setHours(17, 0, 0, 0);
      setCfg({ ...d, start: lokaal(d.start) || lokaal(morgen), end: lokaal(d.end) || lokaal(week), zelfde: !d.external || d.external === d.internal });
    } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { if (gekozen) laad(gekozen); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!items) return <Loading text="Postvakken ophalen..." />;
  const zet = (k, v) => setCfg((c) => ({ ...c, [k]: v }));
  const naam = (items.find((i) => i.v === mb) || {}).l || mb;
  const opslaan = async () => {
    if (cfg.state !== 'Disabled' && !cfg.internal.trim()) return toast('Vul een bericht in.', 'e');
    if (cfg.state === 'Scheduled' && !(cfg.start && cfg.end && cfg.end > cfg.start)) return toast('Kies een begin en een einde na het begin.', 'e');
    const r = await act('ar.set', { mailbox: mb, state: cfg.state, internal: cfg.internal, external: cfg.zelfde ? cfg.internal : cfg.external,
      audience: cfg.audience, start: cfg.start, end: cfg.end }, { msg: 'Automatisch antwoord opslaan...' });
    if (r) laad(mb);
  };

  return (
    <div className="cols">
      <Card title="Gebruiker of postvak" icon={MailX}>
        <Picker items={items} onPick={(i) => laad(i.v)} placeholder="Zoek gebruiker of gedeeld postvak..." height={460}
          render={(i) => <span className="m" style={i.v === mb ? { color: 'var(--hd)' } : undefined}><b>{i.l} {i.k === 's' && <Chip k="mu">gedeeld</Chip>}</b><small>{i.s}</small></span>} />
      </Card>
      <Card title={mb ? naam : 'Instellingen'} icon={CalendarClock} right={cfg && <Chip k={STAND[cfg.state]?.[1]}>Nu: {STAND[cfg.state]?.[0] || cfg.state}</Chip>}>
        {!mb && <div className="hint" style={{ margin: 0 }}>Kies links een gebruiker of gedeeld postvak.</div>}
        {fout && <Msg kind="warn">{fout}</Msg>}
        {mb && !cfg && !fout && <Loading text="Huidige instelling ophalen..." />}
        {cfg && (
          <>
            <div className="btns" style={{ marginBottom: 14 }}>
              {[['Disabled', 'Uit'], ['Enabled', 'Aan (direct)'], ['Scheduled', 'Gepland (van-tot)']].map(([k, l]) => (
                <Btn key={k} v={cfg.state === k ? 'p' : ''} onClick={() => zet('state', k)}>{l}</Btn>))}
            </div>
            {cfg.state === 'Scheduled' && (
              <div className="row" style={{ marginBottom: 12 }}>
                <div><label className="f">Van</label><input type="datetime-local" value={cfg.start} onChange={(e) => zet('start', e.target.value)} /></div>
                <div><label className="f">Tot en met</label><input type="datetime-local" value={cfg.end} onChange={(e) => zet('end', e.target.value)} /></div>
              </div>
            )}
            {cfg.state !== 'Disabled' ? (
              <>
                <label className="f">Bericht voor collega's (binnen de organisatie)</label>
                <textarea rows={6} value={cfg.internal} onChange={(e) => zet('internal', e.target.value)}
                  placeholder={'Bijvoorbeeld:\nIk ben afwezig tot en met maandag 7 december. Voor dringende zaken kun je terecht bij ...'} />
                <label className="f" style={{ marginTop: 12 }}>Antwoorden naar externen</label>
                <select value={cfg.audience} onChange={(e) => zet('audience', e.target.value)}>
                  {Object.entries(DOEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
                {cfg.audience !== 'None' && (
                  <>
                    <label className="chk" style={{ marginTop: 10 }}><input type="checkbox" checked={cfg.zelfde} onChange={(e) => zet('zelfde', e.target.checked)} /><span>Zelfde bericht voor externen</span></label>
                    {!cfg.zelfde && <><label className="f" style={{ marginTop: 8 }}>Bericht voor externen</label>
                      <textarea rows={6} value={cfg.external} onChange={(e) => zet('external', e.target.value)} /></>}
                  </>
                )}
              </>
            ) : <div className="hint">Er wordt geen automatisch antwoord verstuurd. De opgeslagen tekst blijft bewaard voor een volgende keer.</div>}
            <div className="btns" style={{ marginTop: 16 }}><Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn></div>
          </>
        )}
      </Card>
    </div>
  );
}

function Overzicht({ kies }) {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const laad = async (fresh) => {
    setFout(''); if (fresh) setD(null);
    try { setD(await api('ar.overzicht', { fresh }, { quiet: true })); } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { laad(false); }, []);
  if (fout) return <Msg kind="warn">{fout}</Msg>;
  if (!d) return <Loading text="Alle postvakken nalopen (dit kan bij grote klanten even duren)..." />;
  const uitzetten = async (m) => { if (await act('ar.set', { mailbox: m, state: 'Disabled' }, { msg: 'Uitzetten...' })) laad(true); };
  return (
    <Card title={`Automatisch antwoord aan of gepland (${d.active.length} van ${d.checked} postvakken)`} icon={ListChecks}
      right={<div className="btns"><Btn s onClick={() => csv('automatisch-antwoord.csv', [['Naam', 'Postvak', 'Stand', 'Van', 'Tot', 'Extern', 'Bericht'],
        ...d.active.map((r) => [r.name, r.mailbox, STAND[r.state]?.[0], r.state === 'Scheduled' ? dt(r.start) : '', r.state === 'Scheduled' ? dt(r.end) : '', DOEL[r.audience], r.internal])])}>CSV</Btn>
        <Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn></div>}>
      {!d.active.length ? <Msg kind="ok">Niemand heeft op dit moment een automatisch antwoord aan of gepland.</Msg> : (
        <table className="vastkop">
          <thead><tr><th>Naam</th><th>Stand</th><th>Periode</th><th>Extern</th><th>Bericht</th><th /></tr></thead>
          <tbody>{d.active.map((r) => (
            <tr key={r.mailbox}>
              <td><b>{r.name}</b> {r.shared && <Chip k="mu">gedeeld</Chip>}<br /><small className="hint">{r.mailbox}</small></td>
              <td><Chip k={STAND[r.state]?.[1]}>{STAND[r.state]?.[0]}</Chip></td>
              <td>{r.state === 'Scheduled' ? <>{dt(r.start)}<br />t/m {dt(r.end)}</> : 'Tot het wordt uitgezet'}</td>
              <td>{DOEL[r.audience]}</td>
              <td style={{ maxWidth: 320, whiteSpace: 'pre-line' }}><small>{r.internal.length > 160 ? r.internal.slice(0, 160) + '...' : r.internal}</small></td>
              <td><div className="btns"><Btn s onClick={() => { gekozen = r.mailbox; kies(); }}>Bewerken</Btn><Btn s v="dl" onClick={() => uitzetten(r.mailbox)}>Uitzetten</Btn></div></td>
            </tr>))}</tbody>
        </table>
      )}
    </Card>
  );
}


function Doorsturen() {
  const [items, setItems] = useState(null);
  const [mb, setMb] = useState('');
  const [cfg, setCfg] = useState(null);
  const [fout, setFout] = useState('');
  useEffect(() => {
    Promise.all([getUsers(), getShared()]).then(([u, s]) => setItems([
      ...u.filter((x) => !x.guest && x.on !== false).map((x) => ({ v: x.upn, l: x.name, s: x.upn, k: 'u' })),
      ...s.map((x) => ({ v: x.mail, l: x.name, s: x.mail, k: 's' })),
    ])).catch(() => setItems([]));
  }, []);
  const laad = async (m) => {
    setMb(m); setCfg(null); setFout('');
    try { const d = await api('fwd.get', { mailbox: m }, { quiet: true }); setCfg({ ...d, nieuw: d.to, aan: d.on }); } catch (e) { setFout(e.message || String(e)); }
  };
  if (!items) return <Loading text="Postvakken ophalen..." />;
  const naam = (items.find((i) => i.v === mb) || {}).l || mb;
  const extern = cfg && cfg.nieuw && cfg.domains && !cfg.domains.includes(cfg.nieuw.split('@')[1]?.toLowerCase());
  const opslaan = async () => {
    if (cfg.aan && !/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(cfg.nieuw.trim())) return toast('Vul een geldig e-mailadres in.', 'e');
    if (await act('fwd.set', { mailbox: mb, on: cfg.aan, to: cfg.nieuw.trim(), keep: cfg.keep }, { msg: 'Doorsturen opslaan...' })) laad(mb);
  };
  return (
    <div className="cols">
      <Card title="Gebruiker of postvak" icon={Forward}>
        <Picker items={items} onPick={(i) => laad(i.v)} placeholder="Zoek gebruiker of gedeeld postvak..." height={460}
          render={(i) => <span className="m" style={i.v === mb ? { color: 'var(--hd)' } : undefined}><b>{i.l} {i.k === 's' && <Chip k="mu">gedeeld</Chip>}</b><small>{i.s}</small></span>} />
      </Card>
      <Card title={mb ? naam : 'Doorsturen'} icon={Forward} right={cfg && (cfg.on ? <Chip k="o">Nu: door naar {cfg.to}</Chip> : <Chip k="mu">Nu: uit</Chip>)}>
        {!mb && <div className="hint" style={{ margin: 0 }}>Kies links een gebruiker of gedeeld postvak.</div>}
        {fout && <Msg kind="warn">{fout}</Msg>}
        {mb && !cfg && !fout && <Loading text="Huidige instelling ophalen..." />}
        {cfg && (
          <>
            <div className="btns" style={{ marginBottom: 14 }}>
              <Btn v={!cfg.aan ? 'p' : ''} onClick={() => setCfg((c) => ({ ...c, aan: false }))}>Uit</Btn>
              <Btn v={cfg.aan ? 'p' : ''} onClick={() => setCfg((c) => ({ ...c, aan: true }))}>Doorsturen aan</Btn>
            </div>
            {cfg.aan && (
              <>
                <label className="f">Doorsturen naar (e-mailadres)</label>
                <input type="email" value={cfg.nieuw} onChange={(e) => setCfg((c) => ({ ...c, nieuw: e.target.value }))} placeholder="naam@voorbeeld.nl" autoFocus />
                <div style={{ marginTop: 10 }}><Check checked={cfg.keep} onChange={(v) => setCfg((c) => ({ ...c, keep: v }))}>Kopie bewaren in dit postvak</Check></div>
                {extern && cfg.mode !== 'On' && <Msg kind="warn">Dit is een extern adres. Het uitgaande spambeleid van deze klant staat op "{cfg.mode || 'onbekend'}":
                  Microsoft blokkeert extern doorsturen dan (de gebruiker krijgt een onbestelbaarheidsbericht 5.7.520). Sta extern doorsturen alleen toe als het echt nodig is
                  (Bedreigingsbeheer / uitgaand beleid); vanuit beveiliging (NEN 7510, Secure Score) is het advies het uit te laten.</Msg>}
                {extern && cfg.mode === 'On' && <Msg kind="info">Extern adres: doorsturen naar buiten is bij deze klant toegestaan. Let op: zo verlaat e-mail de organisatie.</Msg>}
              </>
            )}
            <div className="btns" style={{ marginTop: 16 }}><Btn v="p" icon={Save} onClick={opslaan}>Opslaan</Btn></div>
          </>
        )}
      </Card>
    </div>
  );
}
