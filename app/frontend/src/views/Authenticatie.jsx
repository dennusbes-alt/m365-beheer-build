import { useEffect, useState } from 'react';
import { startTab } from '../store.jsx';
import { ExternalLink, KeyRound, Pencil, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, openModal, toast } from '../overlays.jsx';
import { Btn, Card, Check, Chip, Loading, Picker, Tabs } from '../ui.jsx';

export default function Authenticatie() {
  const [tab, setTab] = useState(() => startTab('auth', 'beleid'));
  return (
    <>
      <h2>Authenticatiemethoden</h2>
      <p className="sub">Welke manieren van inloggen en MFA zijn toegestaan, voor wie, en selfservice-wachtwoordherstel.</p>
      <Tabs value={tab} onChange={setTab} tabs={[['beleid', 'Beleid (methoden)', ShieldCheck], ['sspr', 'Wachtwoord herstellen', KeyRound]]} />
      {tab === 'beleid' ? <Beleid /> : <Sspr />}
    </>
  );
}

function Beleid() {
  const [d, setD] = useState(null);
  const laad = async () => { setD(null); const x = await act('auth.methods', {}); setD(x || { methods: [], fout: true }); };
  useEffect(() => { laad(); }, []);
  if (!d) return <Loading text="Beleid ophalen..." />;
  const bewerk = async (m) => {
    const r = await openModal((close) => <Bewerk m={m} close={close} />, { wide: true });
    if (r && await act('auth.method.set', { id: m.id, ...r }, { msg: 'Opslaan...' })) laad();
  };
  return (
    <Card title="Methoden" icon={ShieldCheck} right={<Btn s icon={RefreshCw} onClick={laad}>Vernieuwen</Btn>}>
      {d.migration && d.migration !== 'migrationComplete' && (
        <Msg kind="info">Deze klant gebruikt nog (deels) de oude MFA- en SSPR-instellingen (migratiestatus: {d.migration}). Het beleid hieronder geldt naast die oude instellingen.</Msg>
      )}
      <table>
        <thead><tr><th>Methode</th><th>Status</th><th>Geldt voor</th><th>Uitgezonderd</th><th /></tr></thead>
        <tbody>{d.methods.map((m) => (
          <tr key={m.id}>
            <td className="sk"><b>{m.name}</b><small>{m.desc}</small></td>
            <td>{m.state === 'enabled' ? <Chip k="g">Ingeschakeld</Chip> : <Chip k="mu">Uitgeschakeld</Chip>}</td>
            <td>{m.state === 'enabled' ? (m.include.map((g) => <div key={g.id}>{g.name}{g.required ? <Chip k="o">registratie verplicht</Chip> : null}</div>)) : <span className="hint">-</span>}</td>
            <td>{m.exclude.length ? m.exclude.map((g) => <div key={g.id}>{g.name}</div>) : <span className="hint">-</span>}</td>
            <td className="r"><Btn s icon={Pencil} onClick={() => bewerk(m)}>Bewerken</Btn></td>
          </tr>))}
          {!d.methods.length && <tr><td colSpan={5} className="hint">Geen methoden gevonden.</td></tr>}
        </tbody>
      </table>
      <div className="hint">Wijzigen vraagt bij de klant de rol Authentication Policy Administrator (via GDAP).</div>
    </Card>
  );
}

function GroepKiezer({ waarde, setWaarde, groepen, allen }) {
  return (
    <>
      <div className="btns" style={{ margin: '6px 0' }}>
        {waarde.map((g) => <Chip key={g.id}>{g.name} <X size={11} style={{ cursor: 'pointer' }} onClick={() => setWaarde(waarde.filter((x) => x.id !== g.id))} /></Chip>)}
        {!waarde.length && <span className="hint">Niemand</span>}
      </div>
      <Picker height={140} placeholder="Groep toevoegen..." items={[...(allen ? [{ v: 'all_users', l: 'Alle gebruikers' }] : []),
        ...groepen.filter((g) => g.type === 'Beveiliging' || g.type === 'M365' || g.type === 'Mail-beveiliging' || g.type === 'Dynamisch').map((g) => ({ v: g.id, l: g.name, s: g.type }))]
        .filter((i) => !waarde.some((w) => w.id === i.v))} onPick={(i) => setWaarde([...waarde, { id: i.v, name: i.l }])} />
    </>
  );
}

function Bewerk({ m, close }) {
  const [aan, setAan] = useState(m.state === 'enabled');
  const [inc, setInc] = useState(m.include);
  const [exc, setExc] = useState(m.exclude);
  const [groepen, setGroepen] = useState(null);
  useEffect(() => { api('groups.list', {}).then((d) => setGroepen(d.groups)).catch(() => setGroepen([])); }, []);
  return (
    <>
      <h3>{m.name}</h3>
      <p className="hint" style={{ marginTop: 0 }}>{m.desc}</p>
      <Check checked={aan} onChange={setAan}><b>Ingeschakeld</b></Check>
      {!groepen ? <Loading /> : aan && (
        <div className="cols2">
          <div><label className="f">Geldt voor</label><GroepKiezer waarde={inc} setWaarde={setInc} groepen={groepen} allen /></div>
          <div><label className="f">Uitzonderen</label><GroepKiezer waarde={exc} setWaarde={setExc} groepen={groepen} /></div>
        </div>
      )}
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn>
        <Btn v="p" disabled={aan && !inc.length} onClick={() => close({ enabled: aan, include: inc.map((g) => ({ id: g.id })), exclude: exc.map((g) => ({ id: g.id })) })}>Opslaan</Btn></div>
    </>
  );
}

function Sspr() {
  const [d, setD] = useState(null);
  useEffect(() => { act('auth.sspr', {}).then((x) => setD(x || {})); }, []);
  if (!d) return <Loading />;
  const zet = async (v) => { const x = await act('auth.sspr', { admins: v }, { busy: true, msg: 'Opslaan...' }); if (x) { setD(x); toast('Opgeslagen.', 'g'); } };
  return (
    <>
      <Card title="Selfservice-wachtwoordherstel voor gebruikers" icon={KeyRound}>
        <p style={{ marginTop: 0 }}>Hiermee kunnen gebruikers zelf hun wachtwoord herstellen via <b>aka.ms/sspr</b> (voor iedereen of voor een geselecteerde groep).</p>
        <Msg kind="info">Microsoft heeft voor deze tenantbrede instelling (Geen / Geselecteerd / Iedereen) geen beheer-API. De knop hieronder opent
          het juiste scherm van deze klant in het Azure-portal, waar je via je partneraccount direct bent aangemeld.</Msg>
        <div className="btns">
          {d.portal && <Btn v="p" icon={ExternalLink} onClick={() => act('open.url', { url: d.portal })}>SSPR instellen (Eigenschappen)</Btn>}
          {d.registratie && <Btn icon={ExternalLink} onClick={() => act('open.url', { url: d.registratie })}>Methoden voor herstel</Btn>}
        </div>
        <div className="hint">Tip: zet in het tabblad Beleid ook de methoden aan die gebruikers voor herstel mogen gebruiken (bijv. Microsoft Authenticator en sms).</div>
      </Card>
      <Card title="Selfservice-wachtwoordherstel voor beheerders" icon={ShieldCheck}>
        <Check checked={!!d.admins} onChange={zet}>Beheerders mogen hun wachtwoord zelf herstellen</Check>
        <div className="hint">Dit staat bij Microsoft standaard aan. Uitzetten betekent dat beheerders altijd via een andere beheerder een nieuw wachtwoord krijgen.</div>
      </Card>
    </>
  );
}
