// Compliance > Gebruikers: MFA per gebruiker, beheerders, afdwingen (Security Defaults / Conditional Access), doorsturen en gasten.
import { useEffect, useMemo, useState } from 'react';
import { startTab } from '../store.jsx';
import { AlertTriangle, CheckCircle2, ExternalLink, Forward, CircleHelp, KeyRound, ListChecks, RefreshCw, ShieldCheck, UserCog, UserRound, XCircle } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask } from '../overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox, Tabs, csv, datum, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';

const MFA = { strong: ['MFA ingesteld', 'g'], weak: ['Alleen sms/bellen', 'o'], none: ['Geen MFA', 'r'], unknown: ['Onbekend', 'mu'], disabled: ['Account uit', 'mu'], shared: ['Gedeeld postvak', 'mu'] };
const ICOON = { ok: [CheckCircle2, 'gr'], warn: [AlertTriangle, 'or'], err: [XCircle, 'rd'], unknown: [CircleHelp, 'mu'] };
const Tegel = ({ label, n, kleur, sub, on, onClick }) => (
  <div className="card tegelklik" onClick={onClick} style={on ? { borderColor: 'var(--cy)', boxShadow: '0 0 0 2px rgba(0,174,239,.25)' } : undefined}>
    <div className="hint" style={{ margin: 0 }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 900, color: kleur ? `var(--${kleur})` : 'var(--navy)' }}>{n}</div>
    {sub && <div className="hint" style={{ margin: 0 }}>{sub}</div>}
  </div>
);

export default function ComplianceGebruikers() {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [tab, setTab] = useState(() => startTab('cgebruikers', 'mfa'));
  const [f, setF] = useState('probleem');
  const [q, setQ] = useState('');
  const laad = async (fresh) => {
    setFout('');
    try { setD(await api('cu.users', { fresh }, { quiet: true })); } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { laad(false); }, []);
  const lijst = useMemo(() => {
    if (!d) return [];
    const actief = (u) => !['disabled', 'shared'].includes(u.mfa);
    return d.users.filter((u) => (f === 'probleem' ? actief(u) && u.mfa !== 'strong' : f === 'none' ? u.mfa === 'none' : f === 'weak' ? u.mfa === 'weak'
      : f === 'strong' ? u.mfa === 'strong' : f === 'admins' ? u.roles.length > 0 : f === 'actief' ? actief(u) : true));
  }, [d, f]);
  const shown = useFilter(lijst, q, (u) => [u.name, u.upn, ...u.roles]);

  if (fout && !d) return <><h2>Gebruikers (compliance)</h2><Msg kind="warn">{fout}</Msg></>;
  if (!d) return <><h2>Gebruikers (compliance)</h2><Loading text="MFA, beheerders en beleid controleren..." /></>;
  const c = d.counts;
  const kies = (k) => { setTab('mfa'); setF(f === k ? 'actief' : k); };
  const portaal = (url) => act('open.url', { url }, { nobusy: true });
  const uitzetten = async (r) => {
    if (!await ask(`Doorsturen uitzetten voor ${r.name}?\n\nNu doorgestuurd naar: ${r.to}\n\nNegatieve impact: de ontvanger krijgt deze mail niet meer automatisch. Als dit bewust is ingesteld (bijv. voor een externe boekhouder), spreek dan eerst iets anders af.`, 'Uitzetten', true)) return;
    if (await act('cu.forward.off', { mailbox: r.mailbox }, { msg: 'Doorsturen uitzetten...' })) laad(true);
  };
  const export_ = () => csv('gebruikers-mfa.csv', [['Naam', 'UPN', 'MFA', 'Methoden', 'Afgedwongen', 'Rollen', 'Licentie', 'Laatst aangemeld'],
    ...d.users.map((u) => [u.name, u.upn, MFA[u.mfa][0], u.methods.join(', '), u.enforced == null ? 'Onbekend' : u.enforced ? 'Ja' : (u.excluded ? 'Nee (uitgezonderd)' : 'Nee'),
      u.roles.join(', '), u.licensed ? 'Ja' : 'Nee', u.last ? datum(u.last) : ''])]);

  return (
    <>
      <h2>Gebruikers (compliance)</h2>
      <p className="sub">Controleert of iedereen MFA heeft ingesteld en of MFA ook wordt afgedwongen, plus beheerders, doorsturen naar externe adressen en gasten. Klik op een tegel om te filteren.</p>
      <div className="tegels" style={{ marginTop: 0 }}>
        <Tegel label="Actieve gebruikers" n={c.active} sub="zonder uitgeschakelde accounts en gedeelde postvakken" on={f === 'actief'} onClick={() => kies('actief')} />
        <Tegel label="Geen MFA" n={c.none} kleur={c.none ? 'rd' : 'gr'} sub="kunnen inloggen met alleen een wachtwoord" on={f === 'none'} onClick={() => kies('none')} />
        <Tegel label="Beheerders zonder MFA" n={c.adminsNone} kleur={c.adminsNone ? 'rd' : 'gr'} sub="hoogste risico" on={f === 'admins'} onClick={() => kies('admins')} />
        <Tegel label="Alleen sms/bellen" n={c.weak} kleur={c.weak ? 'or' : 'gr'} sub="zwakkere methode; advies: Authenticator" on={f === 'weak'} onClick={() => kies('weak')} />
        <Tegel label="MFA ingesteld" n={c.strong} kleur="gr" sub={c.active ? `${Math.round(c.strong / c.active * 100)}% van de actieve gebruikers` : ''} on={f === 'strong'} onClick={() => kies('strong')} />
        <Tegel label="Global Administrators" n={c.ga} kleur={c.ga >= 2 && c.ga <= 4 ? 'gr' : 'or'} sub="advies: 2 tot 4" onClick={() => setTab('admins')} />
      </div>

      <Card title="Controlelijst" icon={ListChecks} right={<div className="btns"><Btn s icon={ExternalLink} onClick={() => portaal(d.portal)}>Conditional Access</Btn><Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn></div>}>
        <table>
          <tbody>{d.checks.map((k) => {
            const [I, kl] = ICOON[k.status] || ICOON.unknown;
            return <tr key={k.key}><td style={{ width: 26 }}><I size={18} style={{ color: `var(--${kl})`, verticalAlign: -4 }} /></td><td><b>{k.title}</b><br /><small>{k.text}</small></td></tr>;
          })}</tbody>
        </table>
        {d.source === 'methoden' && <div className="hint">Het MFA-registratierapport vraagt Entra ID P1; de methoden zijn daarom per gebruiker opgevraagd (maximaal 600).</div>}
      </Card>

      <Tabs value={tab} onChange={setTab} tabs={[['mfa', 'MFA per gebruiker', KeyRound], ['admins', `Beheerders (${d.admins.length})`, UserCog],
        ['ca', `Beleid (${d.ca.policies.length})`, ShieldCheck], ['fwd', `Doorsturen (${d.forwarding ? d.forwarding.list.length : '-'})`, Forward], ['guests', `Gasten (${d.guests.length})`, UserRound]]} />

      {tab === 'mfa' && (
        <Card title={`Gebruikers (${lijst.length})`} icon={KeyRound} right={<div className="btns">
          <select value={f} onChange={(e) => setF(e.target.value)} style={{ width: 'auto' }}>
            <option value="probleem">Zonder (sterke) MFA</option><option value="none">Geen MFA</option><option value="weak">Alleen sms/bellen</option>
            <option value="strong">MFA ingesteld</option><option value="admins">Beheerders</option><option value="actief">Alle actieve</option><option value="alle">Alle accounts</option>
          </select><Btn s onClick={export_}>CSV</Btn></div>}>
          <SearchBox value={q} onChange={setQ} placeholder="Zoek gebruiker of rol..." />
          {f === 'probleem' && !lijst.length && <Msg kind="ok">Alle actieve gebruikers hebben een sterke MFA-methode ingesteld.</Msg>}
          <div style={{ maxHeight: 'calc(100vh - 300px)', overflow: 'auto', marginTop: 10 }}>
            <table className="vastkop">
              <thead><tr><th>Gebruiker</th><th>MFA</th><th>Methoden</th><th>Afgedwongen</th><th>Rollen</th><th>Laatst aangemeld</th></tr></thead>
              <tbody>{shown.slice(0, MAX_RIJEN).map((u) => (
                <tr key={u.id}>
                  <td><b>{u.name}</b>{!u.licensed && u.mfa !== 'shared' && <> <Chip k="mu">geen licentie</Chip></>}<br /><small className="hint">{u.upn}</small></td>
                  <td><Chip k={MFA[u.mfa][1]}>{MFA[u.mfa][0]}</Chip></td>
                  <td><small>{u.methods.length ? u.methods.join(', ') : '-'}</small></td>
                  <td>{u.enforced == null ? <Chip k="mu">Onbekend</Chip> : u.enforced ? <Chip k="g">Ja</Chip> : <Chip k="r">{u.excluded ? 'Uitgezonderd' : 'Nee'}</Chip>}</td>
                  <td>{u.roles.length ? u.roles.map((r) => <Chip key={r} k={u.ga && r === 'Global Administrator' ? 'r' : 'o'}>{r}</Chip>) : '-'}</td>
                  <td><small>{u.last ? `${datum(u.last)} (${u.days} d)` : (d.signIns ? 'Nooit' : '-')}</small></td>
                </tr>))}</tbody>
            </table>
            <Meer totaal={shown.length} />
          </div>
        </Card>
      )}

      {tab === 'admins' && (
        <Card title="Accounts met een beheerdersrol" icon={UserCog}>
          {!d.admins.length ? <div className="hint">Geen beheerders gevonden (of de rollen konden niet worden gelezen).</div> : (
            <table className="vastkop">
              <thead><tr><th>Naam</th><th>Rollen</th><th>MFA</th></tr></thead>
              <tbody>{d.admins.map((a) => (
                <tr key={a.id}><td><b>{a.name}</b><br /><small className="hint">{a.upn}</small></td>
                  <td>{a.roles.map((r) => <Chip key={r} k={r === 'Global Administrator' ? 'r' : 'o'}>{r}</Chip>)}</td>
                  <td><Chip k={MFA[a.mfa][1]}>{MFA[a.mfa][0]}</Chip></td></tr>))}</tbody>
            </table>)}
          <div className="hint">Beheerders via GDAP (jouw partneraccount) staan hier niet in: die vallen onder het beleid van de partner-tenant.</div>
        </Card>
      )}

      {tab === 'ca' && (
        <Card title="Security Defaults en Conditional Access" icon={ShieldCheck}>
          <p><b>Security Defaults:</b> {d.securityDefaults ? <Chip k="g">Aan</Chip> : <Chip k="mu">Uit</Chip>}
            {' '}<small className="hint">{d.securityDefaults ? 'MFA voor iedereen en oude protocollen geblokkeerd.' : d.ca.policies.length ? 'Uit (normaal als Conditional Access wordt gebruikt).' : 'Uit, en er zijn geen Conditional Access-beleidsregels: MFA wordt niet afgedwongen.'}</small></p>
          {d.caError && <Msg kind="warn">Conditional Access kon niet worden gelezen (vraagt Entra ID P1 en de rol Security Reader of Conditional Access Administrator): {d.caError}</Msg>}
          {d.ca.policies.length > 0 && (
            <table>
              <thead><tr><th>Beleid</th><th>Stand</th><th>Voor wie</th><th>Vraagt</th><th className="r">Uitzonderingen</th></tr></thead>
              <tbody>{d.ca.policies.map((p) => (
                <tr key={p.name}><td><b>{p.name}</b></td><td><Chip k={p.state === 'Aan' ? 'g' : p.state === 'Uit' ? 'mu' : 'o'}>{p.state}</Chip></td><td><small>{p.scope}</small></td>
                  <td>{p.mfa && <Chip k="g">MFA</Chip>}{p.block && <Chip k="r">{p.legacy ? 'Blokkeren (oude protocollen)' : 'Blokkeren'}</Chip>}{!p.mfa && !p.block && <small className="hint">anders</small>}</td>
                  <td className="r">{p.excluded || '-'}</td></tr>))}</tbody>
            </table>)}
        </Card>
      )}

      {tab === 'fwd' && (
        <Card title="Postvakken die doorsturen" icon={Forward}>
          {!d.forwarding ? <Msg kind="warn">Exchange Online is niet verbonden; doorsturen kan niet worden gecontroleerd.</Msg>
            : !d.forwarding.list.length ? <Msg kind="ok">Geen enkel postvak stuurt automatisch door.</Msg> : (
              <table>
                <thead><tr><th>Postvak</th><th>Doorsturen naar</th><th>Kopie houden</th><th /></tr></thead>
                <tbody>{d.forwarding.list.map((r) => (
                  <tr key={r.mailbox}><td><b>{r.name}</b><br /><small className="hint">{r.mailbox}</small></td>
                    <td>{r.to} {r.external ? <Chip k="r">extern</Chip> : <Chip k="mu">intern</Chip>}</td><td>{r.keep ? 'Ja' : 'Nee'}</td>
                    <td><Btn s v="dl" onClick={() => uitzetten(r)}>Uitzetten</Btn></td></tr>))}</tbody>
              </table>)}
          <div className="hint">Alleen doorsturen dat op het postvak zelf is ingesteld. Doorstuurregels in Outlook (Postvak IN-regels) worden tegengehouden als automatisch doorsturen in het uitgaande spambeleid is geblokkeerd (zie Secure Score).</div>
        </Card>
      )}

      {tab === 'guests' && (
        <Card title="Gastaccounts" icon={UserRound} right={<Btn s onClick={() => csv('gasten.csv', [['Naam', 'Account', 'Status', 'Aangemaakt', 'Laatst aangemeld'],
          ...d.guests.map((g) => [g.name, g.upn, g.state, datum(g.created), g.last ? datum(g.last) : ''])])}>CSV</Btn>}>
          {!d.guests.length ? <div className="hint">Geen gastaccounts.</div> : (
            <div style={{ maxHeight: 'calc(100vh - 300px)', overflow: 'auto' }}>
              <table className="vastkop">
                <thead><tr><th>Gast</th><th>Status</th><th>Aangemaakt</th><th>Laatst aangemeld</th></tr></thead>
                <tbody>{d.guests.slice(0, MAX_RIJEN).map((g) => (
                  <tr key={g.id}><td><b>{g.name}</b><br /><small className="hint">{g.upn}</small></td>
                    <td>{g.state === 'PendingAcceptance' ? <Chip k="o">Uitnodiging niet geaccepteerd</Chip> : g.enabled ? <Chip k="g">Actief</Chip> : <Chip k="mu">Uit</Chip>}</td>
                    <td><small>{datum(g.created)}</small></td>
                    <td><small style={g.days > 90 ? { color: 'var(--or)', fontWeight: 700 } : undefined}>{g.last ? `${datum(g.last)} (${g.days} d)` : (d.signIns ? 'Nooit' : '-')}</small></td></tr>))}</tbody>
              </table>
              <Meer totaal={d.guests.length} />
            </div>)}
          <div className="hint">Verwijderen van oude gasten kan via Tenant &gt; Inactieve gebruikers.</div>
        </Card>
      )}
    </>
  );
}
