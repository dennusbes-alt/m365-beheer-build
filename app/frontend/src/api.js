// Verbinding met de lokale Python-backend.
import { busy, toast, werk } from './overlays.jsx';

const q = new URLSearchParams(location.search);
let TOKEN = q.get('t') || '';
try {
  if (TOKEN) sessionStorage.setItem('m365t', TOKEN);
  else TOKEN = sessionStorage.getItem('m365t') || '';
} catch { /* opslag niet beschikbaar */ }
if (q.get('t')) history.replaceState(null, '', location.pathname);

let TENANT = '';
export const setTenant = (t) => { TENANT = t || ''; };
export const getTenant = () => TENANT;

function toonLog(l) {
  if (!l || !l.length) return;
  if (l.length <= 6) { l.forEach((x) => toast(x, /^FOUT/.test(x) ? 'e' : '')); return; }
  l.filter((x) => /^FOUT/.test(x)).slice(0, 3).forEach((x) => toast(x, 'e'));
  toast(l[l.length - 1], /^FOUT/.test(l[l.length - 1]) ? 'e' : 'g');
}

// Gegevens ophalen blokkeert het scherm niet (de schermen tonen zelf een laadindicator);
// alleen acties die iets wijzigen tonen het wachtvenster.
const LEZEN = new Set(['users', 'skus', 'shared.list', 'user.get', 'user.groups', 'user.mfa', 'user.sharedscan', 'groups.list',
  'group.members', 'cal.get', 'inactive', 'dev.list', 'dev.get', 'dev.groups', 'dev.bitlocker', 'customers', 'info', 'activity',
  'prefs.get', 'update.status', 'auth.status', 'tenant.prefetch', 'gdap.status', 'job.status', 'user.template', 'user.onedrive',
  'auth.methods', 'auth.sspr', 'trace.search', 'trace.detail', 'rules.list', 'connectors.list', 'threat.list', 'threat.get', 'dkim.list',
  'dkim.get', 'sp.sites', 'dev.bitlocker.zoek', 'tenant.progress', 'ap.list', 'dom.list', 'dom.get', 'adm.status', 'mig.batches', 'mig.users', 'mig.endpoints', 'mig.domains', 'health.overview', 'health.issue', 'health.messages', 'brand.get', 'auto.blokken', 'auto.lijst', 'auto.status', 'ss.list', 'cd.devices', 'cu.users', 'ar.get', 'ar.overzicht', 'rd.copilot', 'rd.nen', 'ret.list', 'ret.mailbox', 'fwd.get', 'bk.keys.status', 'bk.overzicht', 'bk.controles', 'dm.overzicht', 'dm.afzenders', 'dm.status', 'app.rol', 'at.status', 'at.opties', 'at.bedrijven', 'at.tickets', 'at.taken', 'at.bk.status', 'spm.sites', 'spm.libs', 'spm.folders', 'spm.perms', 'spm.groupusers', 'at.medewerkers', 'in.profiles', 'in.profile.status', 'in.apps', 'in.app.status', 'in.store.search', 'in.enroll', 'in.android.qr']);

// Alleen deze acties blokkeren het scherm (inloggen, klant openen); al het andere loopt direct op de achtergrond
const BLOKKEER = new Set(['auth.login', 'auth.logout', 'tenant.select', 'customers']);
const bezig = new Map();   // dezelfde wijziging twee keer snel achter elkaar: één keer uitvoeren

// opts: msg (tekst), nobusy, quiet (geen foutmelding tonen), tenant (afwijkende klant), blokkeer (wachtvenster)
// Antwoord voor een klant die niet meer open staat: nooit een melding of foutafhandeling in het (al verdwenen) scherm.
const stil = (p) => p.catch((e) => (e && e.stale ? new Promise(() => {}) : Promise.reject(e)));

export async function api(name, body, opts = {}) {
  if (!LEZEN.has(name)) {
    const k = `${opts.tenant ?? TENANT}|${name}|${JSON.stringify(body || {})}`;
    if (bezig.has(k)) return stil(bezig.get(k));
    const p = uitvoeren(name, body, opts);
    bezig.set(k, p);
    p.finally(() => bezig.delete(k)).catch(() => {});
    return stil(p);
  }
  return stil(uitvoeren(name, body, opts));
}

async function uitvoeren(name, body, opts) {
  const tenant = opts.tenant ?? TENANT;
  if (LEZEN.has(name) && !opts.busy) opts = { ...opts, nobusy: true };
  const blok = !opts.nobusy && (opts.blokkeer || BLOKKEER.has(name));
  const klaar = !opts.nobusy && !blok ? werk(opts.msg) : null;
  if (blok) busy(true, opts.msg);
  try {
    const r = await fetch('/api/' + name, {
      method: 'POST',
      headers: { 'X-Token': TOKEN, 'X-Tenant': tenant, 'Content-Type': 'application/json', ...(opts.achter ? { 'X-Achter': '1' } : {}) },
      body: JSON.stringify(body || {}),
    });
    if (r.status === 403) throw new Error('Geen toegang tot de lokale server. Start het programma opnieuw.');
    const j = await r.json();
    // Antwoord van een andere klant dan de huidige (je bent tussendoor gewisseld): stil negeren. Het scherm van die
    // klant is al weg, dus de belofte blijft gewoon openstaan (geen melding "Klant gewisseld" meer).
    // Algemene verzoeken (startscherm, zonder klant) blijven altijd geldig.
    if (tenant && tenant !== TENANT && name !== 'tenant.select') {
      if (!LEZEN.has(name)) toonLog(j.log);   // een wijziging is wel uitgevoerd: in het activiteitenlog laten zien
      throw Object.assign(new Error('Klant gewisseld'), { stale: true });
    }
    toonLog(j.log);
    if (!j.ok) throw Object.assign(new Error(j.error || 'Onbekende fout'), { link: j.link || '', gdap: j.gdap || '', klantLogin: !!j.klantLogin });
    return j.data;
  } catch (e) {
    if (!opts.quiet && !e.stale) toast(e.message === 'Failed to fetch' ? 'De verbinding met het programma is verbroken.' : e.message || String(e), 'e');
    throw e;
  } finally {
    if (blok) busy(false);
    if (klaar) klaar();
  }
}

// Zelfde als api(), maar geeft null terug bij een fout (melding is al getoond).
export const act = async (name, body, opts) => { try { return await api(name, body, opts); } catch { return null; } };

export function ping() {
  fetch('/api/ping', { method: 'POST', headers: { 'X-Token': TOKEN } }).catch(() => {});
}
export function bye() {
  fetch('/api/bye', { method: 'POST', headers: { 'X-Token': TOKEN }, keepalive: true }).catch(() => {});
}
