import { useEffect, useState } from 'react';
import { Download, ExternalLink, Globe, RefreshCw, Share2 } from 'lucide-react';
import { act } from '../api.js';
import { ask } from '../overlays.jsx';
import { Btn, Card, Chip, Loading, SearchBox, csv, datum, useFilter } from '../ui.jsx';

const gb = (mb) => (mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`);
const DEEL_KLEUR = { 0: 'g', 3: 'mu', 1: 'o', 2: 'r' };

export default function SharePoint() {
  const [d, setD] = useState(null);
  const [q, setQ] = useState('');
  const laad = async (fresh) => { setD(null); const x = await act('sp.sites', { fresh }); setD(x || { sites: [], options: [] }); };
  useEffect(() => { laad(false); }, []);
  const shown = useFilter(d ? d.sites : [], q, (s) => [s.title, s.url, s.owner]);
  if (!d) return <><h2>SharePoint</h2><Loading text="Sites ophalen..." /></>;
  const totaal = d.sites.reduce((n, s) => n + s.usedMb, 0);
  const zet = async (s, waarde) => {
    const opt = d.options.find((o) => String(o.value) === String(waarde));
    if (!await ask(`Delen voor '${s.title}' wijzigen naar:\n${opt ? opt.label : waarde}?`, 'Wijzigen')) return;
    if (await act('sp.sharing.set', { url: s.url, value: Number(waarde) }, { msg: 'Opslaan...' })) laad(true);
  };
  return (
    <>
      <h2>SharePoint</h2>
      <p className="sub">Actieve sites met gebruikte opslag en de deelinstelling per site.</p>
      <div className="row" style={{ marginBottom: 16 }}>
        <Card><div className="hint" style={{ margin: 0 }}>Actieve sites</div><div style={{ fontSize: 26, fontWeight: 900, color: 'var(--navy)' }}>{d.sites.length}</div></Card>
        <Card><div className="hint" style={{ margin: 0 }}>Gebruikte opslag (sites)</div><div style={{ fontSize: 26, fontWeight: 900, color: 'var(--navy)' }}>{gb(totaal)}</div>
          {d.tenantQuotaMb ? <div className="hint" style={{ margin: 0 }}>van {gb(d.tenantQuotaMb)} voor de organisatie</div> : null}</Card>
        <Card><div className="hint" style={{ margin: 0 }}>Delen op organisatieniveau</div><div style={{ fontSize: 16, fontWeight: 900, color: 'var(--navy)', marginTop: 6 }}>{d.tenantSharingText || '-'}</div>
          <div className="hint" style={{ margin: 0 }}>Een site kan niet ruimer delen dan dit.</div></Card>
      </div>
      <Card title={`Sites (${shown.length})`} icon={Globe}
        right={<div className="btns"><Btn s icon={Download} onClick={() => csv('sharepoint-sites.csv', [['Site', 'Adres', 'Gebruikt (MB)', 'Delen', 'Laatst gewijzigd'], ...d.sites.map((s) => [s.title, s.url, Math.round(s.usedMb), s.sharingText, s.modified])])}>CSV</Btn>
          <Btn s icon={RefreshCw} onClick={() => laad(true)}>Vernieuwen</Btn></div>}>
        <SearchBox value={q} onChange={setQ} placeholder="Zoek site op naam, adres of eigenaar..." />
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>Site</th><th>Opslag</th><th>Laatst gewijzigd</th><th>Delen</th></tr></thead>
          <tbody>{shown.slice(0, 300).map((s) => {
            const pct = s.maxMb ? Math.min(100, (s.usedMb / s.maxMb) * 100) : 0;
            return (
              <tr key={s.url}>
                <td className="sk"><b>{s.title}</b> {s.group && <Chip k="mu">Teams/M365-groep</Chip>}
                  <small><a href="#" onClick={(e) => { e.preventDefault(); act('open.url', { url: s.url }); }}>{s.url} <ExternalLink size={11} /></a></small></td>
                <td style={{ minWidth: 140 }}>{gb(s.usedMb)}<div className={'bar' + (pct > 90 ? ' over' : pct > 75 ? ' full' : '')} style={{ marginTop: 4 }}><i style={{ width: pct + '%' }} /></div></td>
                <td>{datum(s.modified)}</td>
                <td style={{ minWidth: 220 }}>
                  <select value={s.sharing ?? ''} onChange={(e) => zet(s, e.target.value)}>
                    {d.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <Chip k={DEEL_KLEUR[s.sharing] || 'mu'}><Share2 size={11} />{s.sharingText}</Chip>
                </td>
              </tr>
            );
          })}
            {!shown.length && <tr><td colSpan={4} className="hint">Geen sites gevonden.</td></tr>}
          </tbody>
        </table>
        <div className="hint">Hiervoor heb je bij de klant de rol SharePoint Administrator nodig. OneDrives van gebruikers staan bij Gebruikers beheren (tabblad OneDrive).</div>
      </Card>
    </>
  );
}
