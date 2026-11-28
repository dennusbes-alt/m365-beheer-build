import { useEffect, useState } from 'react';
import { Download, KeyRound, Users } from 'lucide-react';
import { getSkus, getUsers } from '../store.jsx';
import { Btn, Card, Chip, Loading, csv } from '../ui.jsx';
import { freeTxt } from './Gebruikers.jsx';

export default function Licenties() {
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(null);
  useEffect(() => {
    Promise.all([getSkus(), getUsers()]).then(([skus, users]) => setD({ skus, users })).catch(() => setD({ skus: [], users: [] }));
  }, []);
  if (!d) return <Loading text="Licenties ophalen..." />;
  const betaald = d.skus.filter((s) => s.kind !== 'gratis');
  const gratis = d.skus.filter((s) => s.kind === 'gratis');
  const tekort = betaald.filter((s) => s.free < 0);
  const ongebruikt = betaald.reduce((n, s) => n + Math.max(0, s.free), 0);
  const s = d.skus.find((x) => x.id === sel);
  const wie = s ? d.users.filter((u) => u.lic.includes(s.id)) : [];
  const rij = (x) => {
    const pct = x.total && x.total < 1000 ? Math.min(100, (x.used / x.total) * 100) : 0;
    return (
      <tr key={x.id} className={'click' + (sel === x.id ? ' on' : '')} onClick={() => setSel(x.id)}>
        <td className="sk"><b>{x.name}</b><small>{x.desc}</small></td>
        <td>{x.kind === 'gratis' && x.total >= 1000 ? 'onbeperkt' : x.total}</td>
        <td>{x.used}</td>
        <td>{freeTxt(x)}</td>
        <td style={{ width: '16%' }}><div className={'bar' + (x.free < 0 ? ' over' : x.free === 0 && x.total < 1000 ? ' full' : '')}><i style={{ width: pct + '%' }} /></div></td>
      </tr>
    );
  };
  return (
    <>
      <h2>Licenties</h2>
      <p className="sub">Wat is ingekocht, wat is toegewezen en wat is nog vrij. Klik op een licentie om te zien wie hem heeft.</p>
      <div className="row" style={{ marginBottom: 16 }}>
        <Card className="" ><div className="hint" style={{ margin: 0 }}>Betaalde licentiesoorten</div><div style={{ fontSize: 26, fontWeight: 900, color: 'var(--navy)' }}>{betaald.length}</div></Card>
        <Card><div className="hint" style={{ margin: 0 }}>Ongebruikte betaalde licenties</div><div style={{ fontSize: 26, fontWeight: 900, color: ongebruikt ? 'var(--or)' : 'var(--gr)' }}>{ongebruikt}</div></Card>
        <Card><div className="hint" style={{ margin: 0 }}>Licenties met tekort</div><div style={{ fontSize: 26, fontWeight: 900, color: tekort.length ? 'var(--rd)' : 'var(--gr)' }}>{tekort.length}</div></Card>
      </div>
      <div className="cols2" style={{ gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)' }}>
        <Card title="Overzicht" icon={KeyRound}>
          <table>
            <thead><tr><th>Licentie</th><th>Ingekocht</th><th>Toegewezen</th><th>Nog vrij</th><th /></tr></thead>
            <tbody>
              <tr className="sec"><td colSpan={5}>Betaalde licenties</td></tr>
              {betaald.map(rij)}
              {gratis.length > 0 && <tr className="sec"><td colSpan={5}>Gratis, proefversies en technische licenties</td></tr>}
              {gratis.map(rij)}
            </tbody>
          </table>
        </Card>
        <div className="sticky">
          {s ? (
            <Card title={`${s.name}: ${wie.length} gebruiker(s)`} icon={Users}
              right={<Btn s icon={Download} onClick={() => csv(`licentie-${s.part}.csv`, [['Naam', 'E-mailadres', 'Actief'], ...wie.map((u) => [u.name, u.upn, u.on ? 'ja' : 'nee'])])}>CSV</Btn>}>
              <table><tbody>
                {wie.map((u) => <tr key={u.id}><td>{u.name}<div className="hint" style={{ margin: 0 }}>{u.upn}</div></td><td className="r">{!u.on && <Chip k="r">geblokkeerd</Chip>}</td></tr>)}
                {!wie.length && <tr><td className="hint">Geen gebruikers.</td></tr>}
              </tbody></table>
              <div className="hint">Technische naam: <code>{s.part}</code></div>
            </Card>
          ) : <div className="card muted"><Users size={18} />Klik op een licentie om te zien wie hem heeft.</div>}
        </div>
      </div>
    </>
  );
}
