import { useEffect, useState } from 'react';
import { Download, Search, Trash2, UserX } from 'lucide-react';
import { act } from '../api.js';
import { Msg, askType, toast } from '../overlays.jsx';
import { clearCache, getSkus, skuName } from '../store.jsx';
import { Btn, Card, Chip, Loading, csv } from '../ui.jsx';

export default function Opruimen() {
  const [dagen, setDagen] = useState(90);
  const [d, setD] = useState(null);
  const [skus, setSkus] = useState([]);
  const [bezig, setBezig] = useState(false);
  const laad = async (n = dagen) => {
    if (n < 30) return toast('Kies minimaal 30 dagen.', 'e');
    setBezig(true);
    const r = await act('inactive', { days: n }, { msg: 'Inloggegevens van alle gebruikers ophalen...' });
    setBezig(false);
    if (r) setD(r);
  };
  useEffect(() => { getSkus().then(setSkus).catch(() => {}); laad(90); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const sk = (x) => x.lic.map((i) => skuName(skus, i)).join(', ');
  return (
    <>
      <h2>Inactieve gebruikers</h2>
      <p className="sub">Wie heeft al lange tijd niet meer ingelogd? Bekijk gelicentieerde gebruikers en ruim ongebruikte accounts en gasten op.</p>
      <Card>
        <div className="row">
          <div className="n" style={{ minWidth: 230 }}>
            <label className="f" style={{ marginTop: 0 }}>Niet ingelogd gedurende (dagen)</label>
            <input type="number" min={30} value={dagen} onChange={(e) => setDagen(parseInt(e.target.value, 10) || 0)} style={{ width: 120 }} onKeyDown={(e) => e.key === 'Enter' && laad()} />
          </div>
          <div className="n"><Btn v="p" icon={Search} onClick={() => laad()} disabled={bezig}>Overzicht ophalen</Btn></div>
        </div>
        <div className="hint">Het ophalen van inloggegevens kan een minuut duren. Microsoft kan enkele dagen achterlopen met inlogdatums.</div>
      </Card>
      {!d ? (bezig ? <Loading text="Inloggegevens ophalen..." /> : null) : <Resultaat d={d} sk={sk} herlaad={() => laad(d.days)} />}
    </>
  );
}

function Resultaat({ d, sk, herlaad }) {
  const dg = d.days;
  const lastTxt = (x) => (x.never
    ? <><Chip k="o">Nooit ingelogd</Chip> <span className="hint">aangemaakt {x.created}</span></>
    : <>{x.last} <span className="hint">({x.days} dagen geleden)</span></>);
  const reden = (x) => x.reason && <Chip k="o">{x.reason}</Chip>;
  return (
    <>
      {!d.mbCheck && <Msg kind="warn">Exchange Online is niet verbonden: gebruikers zonder licentie kunnen daarom niet verwijderd worden (gedeelde postvakken kunnen dan niet worden uitgesloten).</Msg>}
      {!d.roleCheck && <Msg kind="warn">De beheerdersrollen konden niet worden gecontroleerd. Controleer beheerders zelf voordat je iets verwijdert.</Msg>}
      <Card title={`Gebruikers met licentie die al ${dg} dagen niet hebben ingelogd (${d.licensed.length})`} icon={UserX}
        right={<Btn s icon={Download} onClick={() => csv('inactieve-gebruikers-met-licentie.csv', [['Naam', 'E-mailadres', 'Laatst ingelogd', 'Dagen geleden', 'Licenties', 'Actief'], ...d.licensed.map((x) => [x.name, x.upn, x.never ? 'Nooit' : x.last, x.days, sk(x), x.on ? 'ja' : 'nee'])])}>Exporteren (CSV)</Btn>}>
        <p className="hint" style={{ marginTop: 0 }}>Deze licenties kosten geld terwijl ze niet gebruikt worden. Controleer eerst of de persoon nog bij het bedrijf werkt (bijvoorbeeld via "Medewerker uit dienst").</p>
        <table>
          <thead><tr><th>Naam</th><th>Laatst ingelogd</th><th>Licenties</th><th>Status</th></tr></thead>
          <tbody>
            {d.licensed.map((x) => (
              <tr key={x.id}><td><b>{x.name}</b><div className="hint" style={{ margin: 0 }}>{x.upn}</div></td><td>{lastTxt(x)}</td><td>{sk(x)}</td>
                <td>{x.on ? <Chip k="g">actief</Chip> : <Chip k="r">geblokkeerd</Chip>} {reden(x)}</td></tr>
            ))}
            {!d.licensed.length && <tr><td colSpan={4} className="hint">Geen gebruikers gevonden.</td></tr>}
          </tbody>
        </table>
      </Card>
      <Verwijderlijst titel={`Gebruikers zonder licentie die al ${dg} dagen niet hebben ingelogd`} soort="members" naam="gebruikers zonder licentie"
        uitleg="Gedeelde postvakken, ruimtes, beheerders en jouw eigen account worden nooit meegenomen. Verwijderde gebruikers staan 30 dagen in de prullenbak van Entra en zijn daar terug te zetten."
        lijst={d.members} dg={dg} lastTxt={lastTxt} reden={reden} herlaad={herlaad} />
      <Verwijderlijst titel={`Gastgebruikers die al ${dg} dagen inactief zijn`} soort="guests" naam="gastgebruikers"
        uitleg="Gasten die hun uitnodiging nooit hebben geaccepteerd worden beoordeeld op de datum van aanmaken."
        lijst={d.guests} dg={dg} lastTxt={lastTxt} reden={reden} herlaad={herlaad} />
    </>
  );
}

function Verwijderlijst({ titel, soort, naam, uitleg, lijst, dg, lastTxt, reden, herlaad }) {
  const kand = lijst.filter((x) => !x.reason);
  const [sel, setSel] = useState(() => new Set(kand.map((x) => x.id)));
  const alles = kand.length > 0 && kand.every((x) => sel.has(x.id));
  const wis = async () => {
    const ids = [...sel];
    if (!ids.length) return toast('Niets geselecteerd.', 'e');
    if (!await askType(`${ids.length} ${naam} worden verwijderd.\n\nZe komen 30 dagen in de prullenbak van Entra en kunnen daarna niet meer teruggezet worden.`, 'VERWIJDEREN')) return;
    if (await act('inactive.delete', { kind: soort, ids, days: dg }, { msg: 'Verwijderen...' })) { clearCache('users'); herlaad(); }
  };
  return (
    <Card title={`${titel} (${lijst.length})`} icon={Trash2}>
      <p className="hint" style={{ marginTop: 0 }}>{uitleg}</p>
      <table>
        <thead><tr>
          <th style={{ width: 34 }}><input type="checkbox" checked={alles} disabled={!kand.length} onChange={(e) => setSel(e.target.checked ? new Set(kand.map((x) => x.id)) : new Set())} /></th>
          <th>Naam</th><th>Laatst ingelogd</th><th>Status</th>
        </tr></thead>
        <tbody>
          {lijst.map((x) => (
            <tr key={x.id}>
              <td><input type="checkbox" disabled={!!x.reason} checked={sel.has(x.id)} onChange={(e) => setSel((s) => { const n = new Set(s); e.target.checked ? n.add(x.id) : n.delete(x.id); return n; })} /></td>
              <td><b>{x.name}</b><div className="hint" style={{ margin: 0 }}>{x.upn}</div></td>
              <td>{lastTxt(x)}</td>
              <td>{!x.on && <Chip k="r">geblokkeerd</Chip>} {x.pending && <Chip k="o">uitnodiging niet geaccepteerd</Chip>} {reden(x)}</td>
            </tr>
          ))}
          {!lijst.length && <tr><td colSpan={4} className="hint">Geen gebruikers gevonden.</td></tr>}
        </tbody>
      </table>
      <div style={{ marginTop: 12 }}><Btn v="d" icon={Trash2} disabled={!sel.size} onClick={wis}>{sel.size} {naam} verwijderen</Btn></div>
    </Card>
  );
}
