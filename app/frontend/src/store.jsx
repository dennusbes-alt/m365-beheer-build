// Gegevens per klant (alleen in het geheugen). Net als PowerShell altijd actueel: wat al bekend is staat direct op
// het scherm, en is het ouder dan een paar seconden, dan wordt tegelijk live opgehaald en het scherm bijgewerkt.
import { createContext, useContext, useEffect } from 'react';
import { api, getTenant } from './api.js';

export const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);
// Gegevens doorgeven tussen schermen (bijv. nieuwe medewerker -> mapmachtigingen)
export const doorgeven = {};
// Zoekbalk: een scherm openen op een bepaald tabblad. Eén keer gebruikt en maximaal 2 minuten geldig.
export const zetTab = (scherm, tab) => { doorgeven.tab = { scherm, tab, tot: Date.now() + 120000 }; };
export const startTab = (scherm, standaard) => {
  const z = doorgeven.tab;
  if (z && z.scherm === scherm) { delete doorgeven.tab; if (z.tot > Date.now()) return z.tab; }
  return standaard;
};

const caches = new Map();   // tenant-ID -> { sleutel: Promise }
const huidig = () => {
  const t = getTenant();
  if (!caches.has(t)) caches.set(t, {});
  return caches.get(t);
};
export const resetCache = () => caches.clear();
export const clearCache = (...keys) => { const c = huidig(); keys.forEach((k) => delete c[k]); };

const LIVE_MS = 10000;
const luisteraars = new Set();
// Een geopend scherm krijgt de live opgehaalde gegevens vanzelf binnen
export function useVers(key, zet) {
  useEffect(() => {
    const f = (k, v, t) => { if (k === key && t === getTenant()) zet(v); };
    luisteraars.add(f);
    return () => luisteraars.delete(f);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
}

async function cached(key, fn, fresh) {
  const c = huidig();
  const t = getTenant();
  const e = c[key];
  if (fresh || !e) c[key] = { p: fn(!!fresh, false), at: Date.now() };
  else if (Date.now() - e.at > LIVE_MS && !e.bezig) {
    e.bezig = true;
    fn(true, true).then((v) => {
      if (huidig() !== c || c[key] !== e) return;   // ondertussen gewisseld of al vervangen
      c[key] = { p: Promise.resolve(v), at: Date.now() };
      luisteraars.forEach((f) => f(key, v, t));
    }).catch(() => { e.bezig = false; });
  }
  try { return await c[key].p; } catch (err) { delete c[key]; throw err; }
}

export const getUsers = (fresh) => cached('users', (f, q) => api('users', { fresh: f }, { msg: 'Gebruikers ophalen...', quiet: q, achter: q }).then((d) => d.users), fresh);
export const getSkus = (fresh) => cached('skus', (f, q) => api('skus', { fresh: f }, { msg: 'Licenties ophalen...', quiet: q, achter: q }).then((d) => d.skus), fresh);
export const getShared = (fresh) => cached('shared', (f, q) => api('shared.list', { fresh: f }, { msg: 'Gedeelde postvakken ophalen...', quiet: q, achter: q }).then((d) => d.shared), fresh);
export const skuName = (skus, id) => (skus.find((s) => s.id === id) || { name: id }).name;
