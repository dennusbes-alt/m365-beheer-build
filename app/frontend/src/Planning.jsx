// Service calls vanuit een ticket: inplannen voor een collega (Autotask + Outlook-agenda van die collega), verplaatsen, annuleren.
// Afronden gaat vanzelf: wordt het ticket via de app afgerond, dan ook de service call.
import { useEffect, useState } from 'react';
import { CalendarCheck2, CalendarClock, CalendarPlus, CalendarX2, Save } from 'lucide-react';
import { act, api } from './api.js';
import { Msg, ask, openModal, toast } from './overlays.jsx';
import { Btn, Card, Chip, Loading } from './ui.jsx';

const pad = (n) => String(n).padStart(2, '0');
const lokaal = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const toon = (s) => (s ? `${s.slice(8, 10)}-${s.slice(5, 7)} ${s.slice(11, 16)}` : '');

export function serviceCall(t) {
  return openModal((close) => <ServiceCall t={t} close={close} />, { wide: true });
}

function ServiceCall({ t, close }) {
  const [o, setO] = useState(null);
  const [lijst, setLijst] = useState(null);
  const morgen = new Date(); morgen.setDate(morgen.getDate() + 1); morgen.setHours(9, 0, 0, 0);
  const [v, setV] = useState({ who: '', datum: lokaal(morgen).slice(0, 10), van: '09:00', tot: '10:00', description: '' });
  const [bewerk, setBewerk] = useState(null);   // id van een bestaande service call
  const [gewijzigd, setGewijzigd] = useState(false);
  const laad = () => api('sc.lijst', { ticketId: t.id }, { quiet: true }).then((r) => setLijst(r.calls)).catch(() => setLijst([]));
  useEffect(() => {
    api('sc.opties', {}, { quiet: true }).then((r) => { setO(r); setV((x) => ({ ...x, who: x.who || r.me || '' })); }).catch((e) => setO({ error: e.message, people: [] }));
    laad();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const z = (k) => (e) => setV({ ...v, [k]: e.target.value });
  const duur = (u) => { const [h, m] = v.van.split(':').map(Number); const e = h * 60 + m + u * 60; setV({ ...v, tot: `${pad(Math.floor(e / 60) % 24)}:${pad(e % 60)}` }); };
  const ok = v.who && v.datum && v.van && v.tot && v.tot > v.van && v.description.trim();
  const opslaan = async () => {
    const body = { start: `${v.datum}T${v.van}`, end: `${v.datum}T${v.tot}`, description: v.description.trim() };
    if (bewerk) {
      const x = await act('sc.wijzig', { id: bewerk, ...body }, { msg: 'Service call verplaatsen...' });
      if (x) { toast(x.calendarError ? `Verplaatst in Autotask; agenda niet bijgewerkt: ${x.calendarError}` : 'Service call verplaatst (ook in de agenda).', x.calendarError ? 'e' : 'g'); setBewerk(null); setGewijzigd(true); laad(); }
      return;
    }
    const x = await act('sc.nieuw', { ticketId: t.id, who: v.who, ...body }, { msg: 'Service call inplannen...' });
    if (x) {
      toast(`Service call ingepland${x.calendar ? ' en in de agenda gezet' : ''}${x.planned ? '; ticket staat op Gepland' : ''}.`, 'g');
      if (x.calendarError) toast(`Niet in de agenda: ${x.calendarError}`, 'e');
      setV({ ...v, description: '' }); setGewijzigd(true); laad();
    }
  };
  const annuleer = async (s) => {
    if (!await ask(`Service call van ${toon(s.start)} annuleren? Hij verdwijnt ook uit de agenda.`, 'Annuleren')) return;
    if (await act('sc.verwijder', { id: s.id }, { msg: 'Annuleren...' })) { setGewijzigd(true); laad(); }
  };
  const verplaats = (s) => { setBewerk(s.id); setV({ ...v, datum: s.start.slice(0, 10), van: s.start.slice(11, 16), tot: s.end.slice(11, 16), description: s.description }); };
  const gekozen = o?.people.find((p) => p.key === v.who);
  return (
    <>
      <h3 style={{ display: 'flex', gap: 8, alignItems: 'center' }}><CalendarPlus size={18} />Service call voor ticket {t.number}</h3>
      <div className="hint" style={{ marginTop: 0 }}>{t.title}{t.company ? ` · ${t.company}` : ''}. Komt in Autotask en in de Outlook-agenda van de collega. Ligt hij in de toekomst, dan gaat het ticket op Gepland. Wordt het ticket afgerond, dan ook de service call.</div>
      {!o ? <Loading text="Collega's ophalen..." /> : <>
        {o.error && <Msg kind="warn">{o.error}</Msg>}
        {!o.calendar && <Msg kind="warn">De agendakoppeling is nog niet ingericht: de service call komt wel in Autotask, maar nog niet in Outlook (app-beheerder: opzetten_app.py).</Msg>}
        {lijst && lijst.length > 0 && (
          <div className="card" style={{ padding: 10, marginBottom: 10 }}>
            <b>Ingepland</b>
            {lijst.map((s) => (
              <div key={s.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '5px 0', borderTop: '1px solid var(--bd)' }}>
                <CalendarClock size={15} />
                <span style={{ flex: 1 }}><b>{toon(s.start)}-{s.end.slice(11, 16)}</b> · {s.who || 'onbekend'} · {s.description}</span>
                {s.done ? <Chip k="g">afgerond</Chip> : <>{s.calendar && <Chip k="g" title="Staat in de Outlook-agenda"><CalendarCheck2 size={11} /> agenda</Chip>}
                  <Btn s onClick={() => verplaats(s)}>Verplaatsen</Btn><Btn s icon={CalendarX2} onClick={() => annuleer(s)} title="Annuleren" /></>}
              </div>))}
          </div>)}
        <b>{bewerk ? 'Service call verplaatsen' : 'Nieuwe service call'}</b>
        {!bewerk && <>
          <label className="f">Wie</label>
          <select value={v.who} onChange={z('who')} style={{ width: 'auto', minWidth: 320 }}>
            <option value="" disabled>Kies de collega</option>
            {o.people.map((p) => <option key={p.key} value={p.key}>{p.name}{p.mail ? '' : ' (geen agenda)'}</option>)}
          </select>
          {gekozen && <div className="hint">Agenda: {gekozen.mail || 'onbekend, stel het in bij Servicedesk > Instellingen > Agenda'}</div>}
        </>}
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div><label className="f">Datum</label><input type="date" value={v.datum} onChange={z('datum')} style={{ width: 160 }} /></div>
          <div><label className="f">Van</label><input type="time" step={900} value={v.van} onChange={z('van')} style={{ width: 110 }} /></div>
          <div><label className="f">Tot</label><input type="time" step={900} value={v.tot} onChange={z('tot')} style={{ width: 110 }} /></div>
          <div style={{ alignSelf: 'flex-end', paddingBottom: 6 }} className="btns">{[0.5, 1, 2, 4].map((u) => <Btn key={u} s onClick={() => duur(u)}>{u < 1 ? '30 min' : `${u} uur`}</Btn>)}</div>
        </div>
        <label className="f">Wat gaat er gebeuren?</label>
        <textarea rows={3} value={v.description} onChange={z('description')} placeholder="Bijv. Laptop ophalen voor reparatie scherm, of: nieuwe pc installeren op locatie" />
      </>}
      <div className="foot">
        {bewerk ? <button className="btn" onClick={() => setBewerk(null)}>Terug</button> : <button className="btn" onClick={() => close(gewijzigd)}>Sluiten</button>}
        <button className="btn p" disabled={!o || !ok} onClick={opslaan}><Save size={14} /> {bewerk ? 'Verplaatsen' : 'Inplannen'}</button></div>
    </>);
}

// Servicedesk > Instellingen (app-beheerder): in welke agenda komt wie (gedeelde resource met een rol per collega)
export function AgendaKoppeling() {
  const [d, setD] = useState(null);
  const [mail, setMail] = useState({});
  const laad = () => api('sc.agenda', {}, { quiet: true }).then((r) => { setD(r); setMail(Object.fromEntries(r.people.map((p) => [p.key, p.mail]))); }).catch((e) => setD({ error: e.message, people: [] }));
  useEffect(() => { laad(); }, []);
  if (!d) return null;
  const bewaar = async (p) => { if (await act('sc.agenda.koppel', { key: p.key, mail: mail[p.key] }, { msg: 'Opslaan...' })) { toast('Opgeslagen.', 'g'); laad(); } };
  return (
    <Card title="Agenda (service calls)" icon={CalendarClock}>
      {d.error && <Msg kind="warn">{d.error}</Msg>}
      {d.configured ? <div className="hint" style={{ marginTop: 0 }}>Agendakoppeling actief{d.until ? ` (geheim geldig tot ${d.until.slice(0, 10).split('-').reverse().join('-')})` : ''}.</div>
        : <Msg kind="warn">Nog niet ingericht. Draai eenmalig <b>opzetten_app.py</b> als Global Administrator: dat geeft de app het recht Calendars.ReadWrite (toepassing) en zet het geheim in de verborgen lijst.</Msg>}
      <div className="hint">Standaard komt een service call in de agenda van het e-mailadres van de Autotask-resource. Heeft een (gedeelde) resource meerdere rollen, dan staat elke rol apart: vul daar het adres van de collega in.</div>
      <table style={{ width: '100%' }}><thead><tr><th>Medewerker (rol)</th><th>Agenda</th><th /></tr></thead>
        <tbody>{d.people.map((p) => (
          <tr key={p.key}><td>{p.name}{p.mapped && <Chip k="g">ingesteld</Chip>}</td>
            <td><input value={mail[p.key] || ''} onChange={(e) => setMail({ ...mail, [p.key]: e.target.value })} placeholder="naam@bedrijf.nl" style={{ width: 280 }} /></td>
            <td><Btn s onClick={() => bewaar(p)} disabled={(mail[p.key] || '') === (p.mail || '')}>Opslaan</Btn></td></tr>))}</tbody></table>
    </Card>);
}
