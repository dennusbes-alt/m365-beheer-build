// Huisstijl van de aanmeldpagina (Microsoft Entra bedrijfshuisstijl): logo's, achtergrond, kleur en teksten.
// Afbeeldingen worden in de app automatisch op het formaat gebracht dat Microsoft vraagt.
import { useEffect, useRef, useState } from 'react';
import { ImageUp, Palette, RotateCcw, Save, Trash2 } from 'lucide-react';
import { act, api } from '../api.js';
import { Msg, askType, toast } from '../overlays.jsx';
import { Btn, Card, Check, Field, Loading } from '../ui.jsx';

// Eisen van Microsoft (breedte x hoogte, maximale grootte)
const BEELDEN = [
  ['bannerLogo', 'Bannerlogo', 'Boven het aanmeldvak', 280, 60, 20, 'contain'],
  ['squareLogo', 'Vierkant logo', 'Bijv. bij Windows-installatie (Autopilot)', 240, 240, 50, 'contain'],
  ['squareLogoDark', 'Vierkant logo (donker)', 'Voor een donkere achtergrond', 240, 240, 50, 'contain'],
  ['backgroundImage', 'Achtergrondafbeelding', 'Achter het aanmeldvak', 1920, 1080, 300, 'cover'],
  ['favicon', 'Favicon', 'Icoontje in het browsertabblad', 32, 32, 5, 'contain'],
];
const ZICHT = [
  ['hideForgotMyPassword', 'Link "Wachtwoord vergeten"'], ['hideKeepMeSignedIn', 'Vraag "Aangemeld blijven?"'],
  ['hideCannotAccessYourAccount', 'Link "Kunt u niet bij uw account?"'], ['hideAccountResetCredentials', 'Selfservice wachtwoord opnieuw instellen'],
  ['hideTermsOfUse', 'Gebruiksvoorwaarden in de voettekst'], ['hidePrivacyAndCookies', 'Privacy en cookies in de voettekst'],
];

// Afbeelding met een canvas op maat maken; te groot bestand: kleiner (JPEG) tot het past
async function opMaat(bestand, b, h, maxKb, modus) {
  const bron = await new Promise((ok, fout) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = fout; r.readAsDataURL(bestand); });
  const img = await new Promise((ok, fout) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fout; i.src = bron; });
  const cv = document.createElement('canvas'); cv.width = b; cv.height = h;
  const x = cv.getContext('2d');
  const s = modus === 'cover' ? Math.max(b / img.width, h / img.height) : Math.min(b / img.width, h / img.height);
  const w = img.width * s; const hh = img.height * s;
  x.imageSmoothingQuality = 'high';
  x.drawImage(img, (b - w) / 2, (h - hh) / 2, w, hh);
  let url = cv.toDataURL('image/png');
  const kb = (u) => Math.round((u.length - u.indexOf(',') - 1) * 0.75 / 1024);
  for (let q = 0.9; kb(url) > maxKb && q >= 0.3; q -= 0.1) {
    if (modus === 'contain') { const y = document.createElement('canvas'); y.width = b; y.height = h; const z = y.getContext('2d'); z.fillStyle = '#ffffff'; z.fillRect(0, 0, b, h); z.drawImage(cv, 0, 0); url = y.toDataURL('image/jpeg', q); } else url = cv.toDataURL('image/jpeg', q);
  }
  if (kb(url) > maxKb) throw new Error(`De afbeelding blijft groter dan ${maxKb} kB. Kies een eenvoudigere afbeelding.`);
  return { url, kb: kb(url) };
}

export default function Huisstijl() {
  const [d, setD] = useState(null);
  const [f, setF] = useState(null);
  const [fout, setFout] = useState('');
  const ophalen = async () => {
    try {
      const x = await api('brand.get', {}, { quiet: true });
      setD(x); setF(x); setFout('');
    } catch (e) { setFout(e.message || String(e)); }
  };
  useEffect(() => { ophalen(); }, []);
  if (fout) return <><h2>Huisstijl aanmeldpagina</h2><Msg kind="warn">{fout}</Msg></>;
  if (!d || !f) return <Loading text="Huisstijl ophalen..." />;
  const z = (k) => (v) => setF((o) => ({ ...o, [k]: v }));
  const gewijzigd = JSON.stringify({ ...f, images: 0 }) !== JSON.stringify({ ...d, images: 0 });
  const opslaan = async () => {
    const body = { visibility: f.visibility, layout: f.layout, header: f.header, footer: f.footer };
    ['backgroundColor', 'signInPageText', 'usernameHintText', 'customPrivacyAndCookiesText', 'customPrivacyAndCookiesUrl', 'customTermsOfUseText',
      'customTermsOfUseUrl', 'customCannotAccessYourAccountUrl', 'customForgotMyPasswordText'].forEach((k) => { body[k] = f[k] || ''; });
    if (await act('brand.save', body, { msg: 'Huisstijl opslaan...' })) setD(f);
  };
  const beeld = async (soort, bestand) => {
    const s = BEELDEN.find((x) => x[0] === soort);
    try {
      const r = await opMaat(bestand, s[3], s[4], s[5], s[6]);
      setF((o) => ({ ...o, images: { ...o.images, [soort]: r.url } }));   // direct zichtbaar in het voorbeeld
      if (await act('brand.image', { kind: soort, data: r.url }, { msg: `${s[1]} plaatsen...` })) {
        setD((o) => ({ ...o, images: { ...o.images, [soort]: r.url } }));
      }
    } catch (e) { toast(e.message || 'Deze afbeelding kan niet gelezen worden.', 'e'); }
  };
  const beeldWeg = async (soort) => {
    setF((o) => ({ ...o, images: { ...o.images, [soort]: '' } }));
    await act('brand.image', { kind: soort, remove: true }, { msg: 'Verwijderen...' });
  };
  const reset = async () => {
    if (!await askType(`De volledige huisstijl van de aanmeldpagina van ${d.org} verwijderen? Gebruikers zien daarna weer de standaardpagina van Microsoft.`, 'VERWIJDEREN', 'Verwijderen')) return;
    if (await act('brand.reset', {}, { msg: 'Huisstijl verwijderen...' })) ophalen();
  };
  return (
    <>
      <h2>Huisstijl aanmeldpagina</h2>
      <p className="sub">Wat medewerkers van {d.org} zien bij het aanmelden bij Microsoft 365 (en bij het inrichten van een Windows-laptop). Wijzigingen zijn binnen enkele minuten zichtbaar. De beheerportals veranderen niet.</p>
      <div className="cols2" style={{ gridTemplateColumns: 'minmax(0, 1.15fr) minmax(0, 1fr)' }}>
        <div>
          <Card title="Afbeeldingen" icon={ImageUp}>
            <div className="hint" style={{ marginTop: 0 }}>Kies een willekeurige afbeelding; de app maakt hem zelf op het formaat dat Microsoft vraagt en plaatst hem direct.</div>
            <table>
              <tbody>{BEELDEN.map(([k, naam, uitleg, b, h, kb]) => (
                <Beeld key={k} k={k} naam={naam} uitleg={`${uitleg} · ${b} x ${h} px, max. ${kb} kB`} url={f.images[k]} onKies={(file) => beeld(k, file)} onWeg={() => beeldWeg(k)} />
              ))}</tbody>
            </table>
          </Card>
          <Card title="Kleur, tekst en opmaak" icon={Palette}>
            <div className="row">
              <div><label className="f">Achtergrondkleur</label>
                <div className="row" style={{ gap: 8 }}><input type="color" value={f.backgroundColor || '#f2f2f2'} onChange={(e) => z('backgroundColor')(e.target.value.toUpperCase())} style={{ width: 52, padding: 2 }} />
                  <input type="text" value={f.backgroundColor} onChange={(e) => z('backgroundColor')(e.target.value)} placeholder="#1B7EA9" style={{ width: 110 }} /></div></div>
              <div><label className="f">Indeling</label><select value={f.layout} onChange={(e) => z('layout')(e.target.value)}>
                <option value="default">Aanmeldvak in het midden</option><option value="verticalSplit">Gesplitst (afbeelding links)</option></select></div>
            </div>
            <Field label="Hint in het gebruikersnaamveld (max. 64)" value={f.usernameHintText} onChange={z('usernameHintText')} placeholder="naam@bedrijf.nl" maxLength={64} />
            <label className="f">Tekst onder het aanmeldvak (max. 1024)</label>
            <textarea rows={3} value={f.signInPageText} onChange={(e) => z('signInPageText')(e.target.value)} maxLength={1024} placeholder="Bijv. Hulp nodig? Bel Justdata: 0xx-xxxxxxx" />
            <label className="f">Tonen op de aanmeldpagina</label>
            {ZICHT.map(([k, l]) => <Check key={k} checked={!f.visibility[k]} onChange={(v) => setF((o) => ({ ...o, visibility: { ...o.visibility, [k]: !v } }))}>{l}</Check>)}
            <div className="row">
              <Field label="Privacyverklaring (URL)" value={f.customPrivacyAndCookiesUrl} onChange={z('customPrivacyAndCookiesUrl')} placeholder="https://..." />
              <Field label="Gebruiksvoorwaarden (URL)" value={f.customTermsOfUseUrl} onChange={z('customTermsOfUseUrl')} placeholder="https://..." />
            </div>
            <div className="btns" style={{ marginTop: 14 }}>
              <Btn v="p" icon={Save} disabled={!gewijzigd} onClick={opslaan}>Opslaan</Btn>
              {gewijzigd && <Btn onClick={() => setF({ ...d, images: f.images })}>Wijzigingen ongedaan maken</Btn>}
              <span style={{ flex: 1 }} />
              {d.exists && <Btn v="dl" icon={RotateCcw} onClick={reset}>Huisstijl verwijderen</Btn>}
            </div>
          </Card>
        </div>
        <div className="sticky"><Card title="Voorbeeld"><Voorbeeld f={f} /></Card></div>
      </div>
    </>
  );
}

function Beeld({ naam, uitleg, url, onKies, onWeg }) {
  const inp = useRef(null);
  return (
    <tr>
      <td style={{ width: 120 }}>
        <div style={{ width: 110, height: 52, border: '1px dashed var(--bd)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'repeating-conic-gradient(#eee 0 25%, #fff 0 50%) 0 0 / 12px 12px', overflow: 'hidden' }}>
          {url ? <img src={url} alt="" style={{ maxWidth: '100%', maxHeight: '100%' }} /> : <span className="hint" style={{ margin: 0 }}>geen</span>}
        </div>
      </td>
      <td><b>{naam}</b><div className="hint" style={{ margin: 0 }}>{uitleg}</div></td>
      <td className="r" style={{ whiteSpace: 'nowrap' }}>
        <input ref={inp} type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" hidden onChange={(e) => { const x = e.target.files[0]; e.target.value = ''; if (x) onKies(x); }} />
        <Btn s icon={ImageUp} onClick={() => inp.current.click()}>Kiezen</Btn>{' '}
        {url && <Btn s v="dl" icon={Trash2} onClick={onWeg} title="Verwijderen" />}
      </td>
    </tr>
  );
}

// Benadering van de aanmeldpagina van Microsoft, zodat je het effect direct ziet
function Voorbeeld({ f }) {
  const split = f.layout === 'verticalSplit';
  const achter = { background: f.images.backgroundImage ? `url(${f.images.backgroundImage}) center/cover` : (f.backgroundColor || '#f2f2f2') };
  const vak = (
    <div style={{ background: '#fff', width: 250, padding: '22px 22px 18px', boxShadow: '0 2px 6px rgba(0,0,0,.2)', fontFamily: 'Segoe UI, sans-serif', color: '#1b1b1b' }}>
      {f.images.bannerLogo ? <img src={f.images.bannerLogo} alt="" style={{ maxHeight: 28, maxWidth: 160 }} /> : <div style={{ fontSize: 13, fontWeight: 600, color: '#737373' }}>Microsoft</div>}
      <div style={{ fontSize: 19, fontWeight: 600, margin: '12px 0 10px' }}>Aanmelden</div>
      <div style={{ borderBottom: '1px solid #666', fontSize: 12, color: '#666', padding: '4px 0' }}>{f.usernameHintText || 'E-mailadres, telefoonnummer of Skype'}</div>
      {!f.visibility.hideCannotAccessYourAccount && <div style={{ fontSize: 11, color: '#0067b8', marginTop: 10 }}>Kunt u niet bij uw account?</div>}
      <div style={{ textAlign: 'right', marginTop: 14 }}><span style={{ background: '#0067b8', color: '#fff', fontSize: 12, padding: '5px 18px' }}>Volgende</span></div>
      {f.signInPageText && <div style={{ fontSize: 11, color: '#444', marginTop: 14, whiteSpace: 'pre-line', borderTop: '1px solid #eee', paddingTop: 8 }}>{f.signInPageText}</div>}
    </div>
  );
  return (
    <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--bd)' }}>
      <div style={{ height: 360, display: 'flex', ...(split ? { background: '#fff' } : achter) }}>
        {split && <div style={{ flex: 1, ...achter }} />}
        <div style={{ flex: split ? 'none' : 1, width: split ? 290 : undefined, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{vak}</div>
      </div>
      {f.footer !== false && (
        <div style={{ background: 'rgba(0,0,0,.6)', color: '#fff', fontSize: 10, padding: '4px 10px', textAlign: 'right' }}>
          {!f.visibility.hideTermsOfUse && 'Gebruiksvoorwaarden'}{!f.visibility.hideTermsOfUse && !f.visibility.hidePrivacyAndCookies && '   '}{!f.visibility.hidePrivacyAndCookies && 'Privacy en cookies'}
        </div>
      )}
    </div>
  );
}
