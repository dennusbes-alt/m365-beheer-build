// Voortgangsvenster voor bulkacties (achtergrondklussen in de backend).
import { useEffect, useState } from 'react';
import { CheckCircle2, Download, XCircle } from 'lucide-react';
import { act } from './api.js';
import { openModal } from './overlays.jsx';
import { Btn, csv } from './ui.jsx';

function Voortgang({ start, close, kolommen, csvNaam }) {
  const [k, setK] = useState(start);
  useEffect(() => {
    let stop = false;
    (async () => {
      let s = start;
      while (!stop && s && s.bezig) {
        await new Promise((r) => setTimeout(r, 1500));
        const n = await act('job.status', { id: s.id }, { quiet: true });
        if (n) { s = n; setK(n); }
      }
    })();
    return () => { stop = true; };
  }, [start]);
  const pct = k.totaal ? Math.round((k.klaar / k.totaal) * 100) : 100;
  const res = k.resultaten || [];
  return (
    <>
      <h3>{k.titel}</h3>
      <div className="hint" style={{ margin: 0 }}>{k.bezig ? `Bezig: ${k.klaar} van ${k.totaal}...` : `Klaar: ${k.ok} gelukt${k.fout ? `, ${k.fout} mislukt` : ''}.`}</div>
      <div className={'bar' + (k.bezig ? '' : k.fout ? ' full' : '')} style={{ margin: '8px 0 12px' }}><i style={{ width: pct + '%' }} /></div>
      <div className="list" style={{ maxHeight: '42vh' }}>
        {res.map((r, i) => (
          <div key={i} className="li" style={{ cursor: 'default', alignItems: 'flex-start' }}>
            {r.ok ? <CheckCircle2 size={16} color="var(--gr)" style={{ flex: 'none', marginTop: 3 }} /> : <XCircle size={16} color="var(--rd)" style={{ flex: 'none', marginTop: 3 }} />}
            <span className="m"><b>{r.naam}</b>
              <small style={{ whiteSpace: 'normal' }}>
                {r.ok ? (kolommen || []).map(([key, label]) => (r[key] ? `${label}: ${r[key]}` : '')).filter(Boolean).join(' · ') : r.fout}
                {r.problems && r.problems.length ? ' · Let op: ' + r.problems.join('; ') : ''}
              </small></span>
          </div>
        ))}
        {!res.length && <div className="li empty">Wordt gestart...</div>}
      </div>
      <div className="foot">
        {csvNaam && !k.bezig && res.length > 0 && (
          <Btn icon={Download} onClick={() => csv(csvNaam, [['Naam', 'Gelukt', ...(kolommen || []).map((x) => x[1]), 'Fout'],
            ...res.map((r) => [r.naam, r.ok ? 'ja' : 'nee', ...(kolommen || []).map((x) => r[x[0]] ?? ''), r.fout || ''])])}>Exporteren (CSV)</Btn>
        )}
        <Btn v="p" onClick={() => close(k)}>{k.bezig ? 'Op de achtergrond laten doorlopen' : 'Sluiten'}</Btn>
      </div>
    </>
  );
}

// Start een klus (resultaat van een api-aanroep die een klus teruggeeft) en toon de voortgang. Resolves bij sluiten.
export function toonKlus(start, opts = {}) {
  if (!start) return Promise.resolve(null);
  return openModal((close) => <Voortgang start={start} close={close} kolommen={opts.kolommen} csvNaam={opts.csv} />, { wide: true });
}
