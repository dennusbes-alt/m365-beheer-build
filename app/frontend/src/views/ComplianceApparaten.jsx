// Compliance > Apparaten: alle apparaten (Intune en Entra), up-to-date of niet, en BitLocker/versleuteling.
import { useEffect, useMemo, useState } from 'react';
import { Eraser, HardDrive, Lock, MonitorSmartphone, PowerOff, RefreshCw, Trash2 } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, ask, askType, openModal } from '../overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox, csv, datum, useFilter, MAX_RIJEN, Meer } from '../ui.jsx';

const STATUS = { ok: ['Up-to-date', 'g'], behind: ['Updates achter', 'o'], unsupported: ['Niet meer ondersteund', 'r'], unknown: ['Onbekend', 'mu'] };
const BL = { on: ['Versleuteld', 'g'], off: ['Niet versleuteld', 'r'], key: ['Sleutel in Entra', 'o'], unknown: ['Onbekend', 'mu'] };
const Tegel = ({ label, n, kleur, sub, on, onClick }) => (
  <div className={'card tegelklik'} onClick={onClick} style={on ? { borderColor: 'var(--cy)', boxShadow: '0 0 0 2px rgba(0,174,239,.25)' } : undefined}>
    <div className="hint" style={{ margin: 0 }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 900, color: kleur ? `var(--${kleur})` : 'var(--navy)' }}>{n}</div>
    {sub && <div className="hint" style={{ margin: 0 }}>{sub}</div>}
  </div>
);
const FILTERS = {
  alle: () => true, ok: (d) => d.status === 'ok', behind: (d) => d.status === 'behind', unsupported: (d) => d.status === 'unsupported',
  stale: (d) => d.stale, bloff: (d) => d.kind === 'Windows' && d.bitlocker !== 'on', nokey: (d) => d.kind === 'Windows' && d.key === false,
  noncomp: (d) => d.intune && d.comp && d.comp !== 'compliant', entra: (d) => !d.intune,
};

export default function ComplianceApparaten() {
  const [d, setD] = useState(null);
  const [fout, setFout] = useState('');
  const [f, setF] = useState('alle');
  const [os, setOs] = useState('');
  const [q, setQ] = useState('');
  const laad = async (fresh) => {
    setFout('');
    try { setD(await api('cd.devices', { fresh }, { quiet: true })); } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { laad(false); }, []);
  const lijst = useMemo(() => (d ? d.devices.filter((x) => FILTERS[f](x) && (!os || x.kind === os)) : []), [d, f, os]);
  const shown = useFilter(lijst, q, (x) => [x.name, x.user, x.upn, x.osv, x.release, x.model]);

  if (fout && !d) return <><h2>Apparaten (compliance)</h2><Msg kind="warn">{fout}</Msg></>;
  if (!d) return <><h2>Apparaten (compliance)</h2><Loading text="Apparaten, versies en BitLocker ophalen..." /></>;
  const n = (k) => d.devices.filter(FILTERS[k]).length;
  const win = d.devices.filter((x) => x.kind === 'Windows');
  const soorten = [...new Set(d.devices.map((x) => x.kind))].sort();
  const tegel = (k, label, kleur, sub) => <Tegel label={label} n={n(k)} kleur={n(k) ? kleur : 'gr'} sub={sub} on={f === k} onClick={() => setF(f === k ? 'alle' : k)} />;
  const export_ = () => csv('apparaten-compliance.csv', [['Apparaat', 'Gebruiker', 'Besturingssysteem', 'Versie', 'Release', 'Status', 'Toelichting', 'Ondersteund tot (Pro)', 'Ondersteund tot (Enterprise)',
    'Versleuteld', 'Herstelsleutel in Entra', 'Laatst gezien', 'Intune', 'Compliant'],
  ...d.devices.map((x) => [x.name, x.upn || x.user, x.os, x.osv, x.release, STATUS[x.status][0], x.reason, x.support, x.supportEnt, BL[x.bitlocker][0],
    x.key == null ? '' : x.key ? 'Ja' : 'Nee', x.last ? datum(x.last) : '', x.intune ? 'Ja' : 'Nee (alleen Entra)', x.comp])]);

  return (
    <>
      <h2>Apparaten (compliance)</h2>
      <p className="sub">Alle apparaten van deze klant uit Intune en Entra ID. Per apparaat zie je of het up-to-date is (vergeleken met de levenscyclus van Microsoft en het nieuwste patchniveau binnen deze klant) en of BitLocker/versleuteling aan staat. Klik op een tegel om te filteren.</p>
      {!d.intune && <Msg kind="warn">Intune is niet beschikbaar bij deze klant (geen licentie of rol). Alleen apparaten uit Entra ID worden getoond; versleuteling is dan niet bekend. {d.intuneError}</Msg>}
      {!d.keys && <Msg kind="info">BitLocker-herstelsleutels konden niet worden gelezen; de kolom "Sleutel in Entra" is daarom leeg.</Msg>}
      <div className="tegels" style={{ marginTop: 0 }}>
        <Tegel label="Alle apparaten" n={d.devices.length} sub={`${win.length} Windows`} on={f === 'alle'} onClick={() => setF('alle')} />
        {tegel('ok', 'Up-to-date', 'gr', 'nieuwste patchniveau')}
        {tegel('behind', 'Updates achter', 'or', 'lager patchniveau dan collega-apparaten')}
        {tegel('unsupported', 'Niet meer ondersteund', 'rd', 'geen beveiligingsupdates meer')}
        {tegel('bloff', 'Windows zonder BitLocker', 'rd', `niet versleuteld of onbekend, van ${win.length}`)}
        {tegel('nokey', 'Geen herstelsleutel in Entra', 'or', 'sleutel niet geback-upt')}
        {tegel('stale', 'Niet gezien > 30 dagen', 'or', 'status mogelijk verouderd')}
        {d.intune && tegel('noncomp', 'Niet compliant (Intune)', 'rd', 'volgens het nalevingsbeleid')}
      </div>

      <Card title="Windows-versies" icon={HardDrive}>
        <table>
          <thead><tr><th>Versie</th><th>Build</th><th className="r">Apparaten</th><th>Nieuwste in tenant</th><th>Ondersteund tot (Home/Pro)</th><th>Ondersteund tot (Enterprise/Education)</th></tr></thead>
          <tbody>{d.builds.map((b, i) => {
            const aantal = win.filter((x) => x.osv.split('.')[2] === String(b.build)).length;
            if (!aantal && i > 2) return null;   // oude versies alleen tonen als er nog apparaten op draaien
            const verlopen = b.support < new Date().toISOString().slice(0, 10);
            return (
              <tr key={b.build} style={!aantal ? { opacity: .55 } : undefined}>
                <td><b>{b.name}</b></td><td>{b.build}</td><td className="r">{aantal || '-'}</td><td>{b.latest ? `${b.build}.${b.latest}` : '-'}</td>
                <td>{verlopen ? <Chip k="r">verlopen {datum(b.support)}</Chip> : datum(b.support)}</td><td>{datum(b.supportEnt)}</td>
              </tr>);
          })}</tbody>
        </table>
        <div className="hint">Windows 11 Business/Pro krijgt 24 maanden updates per versie, Enterprise/Education 36 maanden. "Updates achter" vergelijkt het patchniveau met het nieuwste apparaat op dezelfde versie bij deze klant.</div>
      </Card>

      <Card title={`Apparaten (${lijst.length})`} icon={MonitorSmartphone} right={<div className="btns">
        <select value={os} onChange={(e) => setOs(e.target.value)} style={{ width: 'auto' }}><option value="">Alle systemen</option>{soorten.map((s) => <option key={s}>{s}</option>)}</select>
        <Btn s onClick={export_}>CSV</Btn><Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn></div>}>
        <SearchBox value={q} onChange={setQ} placeholder="Zoek apparaat, gebruiker of versie..." />
        <div style={{ maxHeight: 'calc(100vh - 300px)', overflow: 'auto', marginTop: 10 }}>
          <table className="vastkop">
            <thead><tr><th>Apparaat</th><th>Gebruiker</th><th>Versie</th><th>Updates</th><th><Lock size={13} style={{ verticalAlign: -2 }} /> Versleuteling</th><th>Laatst gezien</th></tr></thead>
            <tbody>{shown.slice(0, MAX_RIJEN).map((x) => (
              <tr key={x.id}>
                <td><b>{x.name}</b>{!x.intune && <> <Chip k="mu" title="Staat wel in Entra ID maar niet in Intune">alleen Entra</Chip></>}<br /><small className="hint">{x.model || x.owner}</small></td>
                <td><small>{x.user || x.upn || '-'}</small></td>
                <td><small><b>{x.release || x.os}</b><br />{x.osv}</small></td>
                <td><Chip k={STATUS[x.status][1]}>{STATUS[x.status][0]}</Chip><br /><small className="hint">{x.reason}</small></td>
                <td><Chip k={BL[x.bitlocker][1]}>{BL[x.bitlocker][0]}</Chip>{x.kind === 'Windows' && x.key != null && <><br /><small className="hint">{x.key ? 'Herstelsleutel in Entra' : 'Geen herstelsleutel in Entra'}</small></>}</td>
                <td><small style={x.stale ? { color: 'var(--or)', fontWeight: 700 } : undefined}>{x.last ? datum(x.last) : 'Nooit'}{x.days != null ? ` (${x.days} d)` : ''}</small></td>
              </tr>))}</tbody>
          </table>
          <Meer totaal={shown.length} />
          {!shown.length && <div className="hint">Geen apparaten in deze selectie.</div>}
        </div>
      </Card>

      <Opschonen d={d} herlaad={() => laad(true)} />
    </>
  );
}


// Apparaten die lang niet gezien zijn: eerst uitschakelen in Entra (omkeerbaar), later verwijderen.
function Opschonen({ d, herlaad }) {
  const [dagen, setDagen] = useState(90);
  const [kies, setKies] = useState([]);
  const kandidaten = useMemo(() => [
    ...d.devices.filter((x) => x.days == null || x.days > dagen),
    ...(d.disabled || []).map((x) => ({ ...x, uit: true })),
  ].sort((a, b) => (b.days ?? 99999) - (a.days ?? 99999)), [d, dagen]);
  const gekozen = kandidaten.filter((x) => kies.includes(x.id));
  const alle = kies.length === kandidaten.length && kandidaten.length > 0;
  const doe = async (actie) => {
    if (!gekozen.length) return;
    const namen = gekozen.slice(0, 12).map((x) => '• ' + x.name).join('\n') + (gekozen.length > 12 ? `\n... en ${gekozen.length - 12} meer` : '');
    if (actie === 'disable') {
      if (!await ask(`${gekozen.length} apparaat/apparaten uitschakelen in Entra ID?

${namen}

Gevolg: met deze apparaten kan niet meer worden aangemeld met een werkaccount en ze krijgen geen toegang meer via Conditional Access. `
        + 'Dit is omkeerbaar (weer inschakelen). BitLocker-sleutels blijven bewaard.', 'Uitschakelen', true)) return;
    } else {
      const metSleutel = gekozen.filter((x) => x.key).length;
      if (!await askType(`${gekozen.length} apparaat/apparaten definitief verwijderen uit Intune en Entra ID?

${namen}

`
        + (metSleutel ? `LET OP: van ${metSleutel} apparaat/apparaten staat een BitLocker-herstelsleutel in Entra. Die wordt mee verwijderd; een versleutelde schijf is daarna niet meer te openen zonder eigen kopie van de sleutel.

` : '')
        + 'Apparaten die nog in Autopilot staan, worden overgeslagen. Dit kan niet ongedaan worden gemaakt.', 'VERWIJDEREN', 'Verwijderen')) return;
    }
    const r = await act('cd.cleanup', { action: actie, items: gekozen.map((x) => ({ id: x.id, name: x.name, intune: x.intune, entraId: x.entraId, key: x.key })) },
      { msg: actie === 'disable' ? 'Uitschakelen...' : 'Verwijderen...' });
    if (r) {
      setKies([]);
      openModal((close) => <><h3>Resultaat</h3><div className="pre">{r.results.join('\n')}</div><div className="foot"><button className="btn p" onClick={() => close()}>Sluiten</button></div></>);
      herlaad();
    }
  };
  return (
    <Card title={`Opschonen: niet gezien in ${dagen} dagen (${kandidaten.length})`} icon={Eraser} right={<div className="btns">
      <select value={dagen} onChange={(e) => { setDagen(+e.target.value); setKies([]); }} style={{ width: 'auto' }}>
        {[30, 60, 90, 180, 365].map((n) => <option key={n} value={n}>Langer dan {n} dagen</option>)}
      </select>
      <Btn s icon={PowerOff} disabled={!gekozen.length} onClick={() => doe('disable')}>Uitschakelen ({gekozen.length})</Btn>
      <Btn s v="dl" icon={Trash2} disabled={!gekozen.length} onClick={() => doe('delete')}>Verwijderen ({gekozen.length})</Btn></div>}>
      <div className="hint" style={{ marginTop: 0 }}>Advies: schakel oude apparaten eerst uit in Entra ID en verwijder ze pas als na een paar weken niemand ze mist.
        Uitgeschakelde apparaten (alleen Entra) staan onderaan. Verwijderen haalt het apparaat uit Intune en Entra ID; Autopilot-registraties blijven staan.</div>
      {!kandidaten.length ? <Msg kind="ok">Geen apparaten die langer dan {dagen} dagen niet gezien zijn.</Msg> : (
        <div style={{ maxHeight: 420, overflow: 'auto' }}>
          <table className="vastkop">
            <thead><tr><th style={{ width: 28 }}><input type="checkbox" checked={alle} onChange={(e) => setKies(e.target.checked ? kandidaten.map((x) => x.id) : [])} /></th>
              <th>Apparaat</th><th>Gebruiker</th><th>Systeem</th><th>Laatst gezien</th><th>Waar</th><th>BitLocker-sleutel</th></tr></thead>
            <tbody>{kandidaten.map((x) => (
              <tr key={x.id}>
                <td><input type="checkbox" checked={kies.includes(x.id)} onChange={(e) => setKies((k) => (e.target.checked ? [...k, x.id] : k.filter((y) => y !== x.id)))} /></td>
                <td><b>{x.name}</b>{x.uit && <> <Chip k="mu">uitgeschakeld</Chip></>}</td>
                <td><small>{x.user || x.upn || '-'}</small></td>
                <td><small>{x.release || x.os}</small></td>
                <td><small style={{ color: 'var(--or)', fontWeight: 700 }}>{x.last ? `${datum(x.last)} (${x.days} d)` : 'Nooit'}</small></td>
                <td><small>{x.intune ? 'Intune + Entra' : 'Entra'}</small></td>
                <td>{x.key ? <Chip k="o">aanwezig</Chip> : <small className="hint">-</small>}</td>
              </tr>))}</tbody>
          </table>
        </div>)}
    </Card>
  );
}
