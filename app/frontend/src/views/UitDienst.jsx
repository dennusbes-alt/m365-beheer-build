import { useEffect, useState } from 'react';
import { ClipboardCheck, LogOut, Mailbox, UserMinus, UserRound } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, toast } from '../overlays.jsx';
import { clearCache, getUsers, useApp } from '../store.jsx';
import { Avatar, Btn, Card, Check, CheckList, Loading, Picker } from '../ui.jsx';

const START = { debtt: false, ren: false, pre: '_Archief_ ', shared: true, block: true, revoke: true, groups: true, licenses: true };

export default function UitDienst() {
  const { info } = useApp();
  const [users, setUsers] = useState(null);
  const [sel, setSel] = useState(null);
  const [o, setO] = useState(START);
  const [acc, setAcc] = useState([]);
  const [r, setR] = useState({ full: true, send: true, auto: true });
  const [klaar, setKlaar] = useState('');
  useEffect(() => { getUsers().then(setUsers).catch(() => setUsers([])); }, []);
  if (!users) return <Loading text="Gebruikers ophalen..." />;
  const z = (k) => (v) => setO((x) => {
    const n = { ...x, [k]: v };
    if (k === 'debtt' && v) Object.assign(n, { ren: true, pre: '_Archief_ ', shared: true, licenses: true, revoke: true });
    return n;
  });

  const go = async () => {
    if (!sel) return toast('Kies eerst een medewerker.', 'e');
    const rename = o.ren ? o.pre : '';
    if (o.ren && !rename.trim()) return toast('Vul de tekst in die voor de naam moet komen.', 'e');
    if (o.shared && info.exo === false) return toast('Exchange Online is niet verbonden: omzetten naar gedeeld postvak kan niet.', 'e');
    const b = { id: sel.id, rename, revoke: o.revoke, shared: o.shared, block: o.block, groups: o.groups, licenses: o.licenses, access: o.shared ? acc : [], ...r };
    const t = [`${sel.name} uit dienst melden bij ${info.tenant}?`, ''];
    if (b.shared) t.push('- postvak wordt gedeeld postvak');
    if (b.rename) t.push(`- hernoemd naar: ${b.rename}${sel.name}`);
    if (b.block) t.push('- aanmelden geblokkeerd');
    if (b.revoke) t.push('- alle sessies afgemeld');
    if (b.groups) t.push('- uit groepen verwijderd');
    if (b.licenses) t.push('- licenties verwijderd');
    if (b.shared && b.access.length) t.push(`- toegang voor ${b.access.length} collega('s)`);
    if (!b.shared && b.licenses) t.push('', 'Let op: zonder gedeeld postvak wordt de mailbox na 30 dagen verwijderd.');
    if (!await ask(t.join('\n'), 'Uit dienst melden', true)) return;
    let d = await act('offboard', b, { msg: 'Bezig met afhandelen...' });
    if (d && d.confirm) {
      if (!await ask(d.confirm, 'Toch doorgaan', true)) return;
      d = await act('offboard', { ...b, force: true }, { msg: 'Bezig met afhandelen...' });
    }
    if (d) {
      clearCache('users', 'skus');
      setKlaar(sel.name);
      document.querySelector('main.main')?.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <>
      <h2>Medewerker uit dienst</h2>
      <p className="sub">Kies de medewerker en wat er moet gebeuren. Alles gebeurt in de juiste volgorde: eerst het postvak omzetten, dan pas de licentie eraf.</p>
      {klaar && <Msg kind="ok"><b>{klaar}</b> is uit dienst gemeld. Bekijk de details in "Activiteit" rechtsboven.</Msg>}
      <div className="cols">
        <div>
          <Card title="1. Medewerker" icon={UserRound}>
            {sel ? (
              <div className="headrow" style={{ marginBottom: 10 }}>
                <Avatar name={sel.name} size={40} />
                <div className="m"><b>{sel.name}</b><div className="hint" style={{ margin: 0 }}>{sel.upn}</div></div>
                <Btn s onClick={() => { setSel(null); setKlaar(''); }}>Andere kiezen</Btn>
              </div>
            ) : (
              <Picker items={users.filter((u) => !u.guest).map((u) => ({ v: u.id, l: u.name, s: u.upn }))} height={380}
                placeholder="Zoek medewerker..." onPick={(i) => { setSel(users.find((u) => u.id === i.v)); setKlaar(''); }} />
            )}
          </Card>
        </div>
        <div>
          <Card title="2. Wat moet er gebeuren?" icon={ClipboardCheck}>
            <Check checked={o.debtt} onChange={z('debtt')}><b>Is dit een medewerker van Debtt?</b><div className="hint" style={{ margin: 0 }}>Zet _Archief_ voor de naam, maakt er een gedeeld postvak van, haalt de licentie eraf en meldt alle sessies af.</div></Check>
            <Check checked={o.ren} onChange={z('ren')}>Gebruiker hernoemen (tekst voor de weergavenaam zetten)</Check>
            {o.ren && <input type="text" value={o.pre} onChange={(e) => z('pre')(e.target.value)} style={{ margin: '0 0 8px 26px', width: 'calc(100% - 26px)' }} />}
            <Check checked={o.shared} onChange={z('shared')} disabled={info.exo === false}><b>Postvak omzetten naar gedeeld postvak</b><div className="hint" style={{ margin: 0 }}>Gebeurt voor het verwijderen van de licentie. Zonder omzetten verdwijnt het postvak na 30 dagen.</div></Check>
            <Check checked={o.block} onChange={z('block')}>Aanmelden blokkeren</Check>
            <Check checked={o.revoke} onChange={z('revoke')}>Alle sessies afmelden (de gebruiker wordt overal uitgelogd)</Check>
            <Check checked={o.groups} onChange={z('groups')}>Verwijderen uit groepen en distributielijsten</Check>
            <Check checked={o.licenses} onChange={z('licenses')}>Licenties verwijderen</Check>
          </Card>
          {o.shared && info.exo !== false && (
            <Card title="3. Wie krijgt toegang tot het gedeelde postvak?" icon={Mailbox}>
              <CheckList items={users.filter((u) => u.on && !u.guest && (!sel || u.id !== sel.id)).map((u) => ({ v: u.upn, l: u.name, s: u.upn }))} value={acc} onChange={setAcc} height={190} />
              <div className="row" style={{ marginTop: 4 }}>
                <Check checked={r.full} onChange={(v) => setR({ ...r, full: v })}>Volledige toegang</Check>
                <Check checked={r.send} onChange={(v) => setR({ ...r, send: v })}>Verzenden als</Check>
                <Check checked={r.auto} onChange={(v) => setR({ ...r, auto: v })}>Automapping</Check>
              </div>
            </Card>
          )}
          <Btn v="d lg" w icon={UserMinus} disabled={!sel} onClick={go}>Uit dienst melden</Btn>
          <div style={{ marginTop: 8 }}>
            <Btn w icon={LogOut} disabled={!sel} onClick={async () => { if (await ask(`Alle sessies van ${sel.name} afmelden?`, 'Afmelden', true)) act('user.revoke', { id: sel.id }); }}>Alleen alle sessies afmelden</Btn>
          </div>
        </div>
      </div>
    </>
  );
}
