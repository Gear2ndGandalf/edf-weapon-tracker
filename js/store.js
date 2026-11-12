// ============================================================================
// store.js – everything that touches localStorage.
//
// Keys (one set per game: edf41, edf5, edf6):
//   edfTracker.<game>          { owned: [id, ...], stars: { id: [n, n, ...] } }
//   edfTracker.summary.<game>  { owned, maxed, total }   (read by the HQ page)
//   Profile 2 keeps its own copies of those two under edfTracker.p2.<...>
//   edfTracker.profile         '1' | '2' (the active profile)
//   edfTracker.profileNames    { 1: name, 2: name }
//   edfTracker.ui.<game>       { cls, cat, filter, detailOpen, scroll }
//   edfTracker.lastExport / edfTracker.lastChange   ISO dates, for the backup line on HQ
//   edfTracker.prefs           { text: 'auto' | '0.6' ... '1.5' (a scale, set with the HQ slider), fx: 'on' | 'off' }
//
// Export file format: { app: "edf-unlock-tracker", version: 1, appVersion, exportedAt,
//   games: { <game>: {...} },  profile2: { games: {...} },  profileNames: { 1, 2 } }   (games = profile 1)
// ("version" is the file format; "appVersion" is the app release that wrote it.)
// The old EDF 4.1 checklist (EDF-4.1-PWA) stored rangerSave / wingdiverSave /
// airraiderSave / fencerSave; those are converted with data/edf41-legacy.json.
// ============================================================================

export const GAMES = ['edf41', 'edf5', 'edf6'];
export const GAME_NAMES = { edf41: 'EDF 4.1', edf5: 'EDF 5', edf6: 'EDF 6' };
// Fallback totals for the HQ page before a game page has been opened.
// tools/build_data.py prints the real totals; update these if the data changes.
export const TOTALS = { edf41: 827, edf5: 1187, edf6: 1564 };

const P = 'edfTracker.';
const LEGACY_KEYS = ['rangerSave', 'wingdiverSave', 'airraiderSave', 'fencerSave'];
const MAX_IDS = 5000;   // sanity limits for imported files
const MAX_STATS = 16;
const MAX_STARS = 10;

// ---------- Profiles: two separate sets of progress (for example PC and console) ----------
export const PROFILE_KEY = P + 'profile';
const prefix = (profile) => (profile === '2' ? P + 'p2.' : P);
export function activeProfile() { return getRaw(PROFILE_KEY) === '2' ? '2' : '1'; }
export function setActiveProfile(id) {
  setRaw(PROFILE_KEY, id === '2' ? '2' : '1');
  if (id === '2') setRaw(P + 'p2used', '1');
}
// True once profile 2 has been used; until then the app looks exactly as it did with one profile.
export function profilesInUse() { return getRaw(P + 'p2used') === '1'; }
const cleanName = (v) => (typeof v === 'string' ? v.replace(/\s+/g, ' ').trim().slice(0, 16) : '');
export function profileNames() {
  const n = readJSON(P + 'profileNames', {});
  return { 1: cleanName(isObject(n) ? n[1] : '') || 'Profile 1', 2: cleanName(isObject(n) ? n[2] : '') || 'Profile 2' };
}
export function renameProfile(id, name) {
  const names = profileNames();
  names[id === '2' ? 2 : 1] = cleanName(name) || 'Profile ' + (id === '2' ? 2 : 1);
  return writeJSON(P + 'profileNames', names);
}
export const progressKey = (game, profile) => prefix(profile || activeProfile()) + game;

// localStorage can throw (private mode, blocked cookies, full disk), so every
// access goes through these three helpers.
function getRaw(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function setRaw(key, value) {
  try { localStorage.setItem(key, value); return true; } catch (e) { return false; }
}
function readJSON(key, fallback) {
  const raw = getRaw(key);
  if (!raw) return fallback;
  try { return JSON.parse(raw); } catch (e) { return fallback; }
}
const writeJSON = (key, value) => setRaw(key, JSON.stringify(value));
const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

// Keep only well-formed data: ids are short strings, stars are small whole numbers.
function cleanOwned(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const id of list) {
    if (typeof id === 'string' && id.length > 0 && id.length <= 64) out.push(id);
    if (out.length >= MAX_IDS) break;
  }
  return out;
}
function cleanStars(obj) {
  const out = {};
  if (!isObject(obj)) return out;
  let n = 0;
  for (const id of Object.keys(obj)) {
    const arr = obj[id];
    if (id === '__proto__' || id.length > 64 || !Array.isArray(arr)) continue;
    out[id] = arr.slice(0, MAX_STATS).map((v) => Math.min(MAX_STARS, Math.max(0, Math.floor(Number(v)) || 0)));
    if (++n >= MAX_IDS) break;
  }
  return out;
}

// ---------- Progress ----------
// "profile" is optional everywhere below; the active profile is used when it is left out.
export function loadProgress(game, profile) {
  const o = readJSON(progressKey(game, profile), {});
  return { owned: new Set(cleanOwned(o && o.owned)), stars: cleanStars(o && o.stars) };
}
export function saveProgress(game, progress, summary, profile) {
  const key = progressKey(game, profile);
  const text = JSON.stringify({ owned: Array.from(progress.owned), stars: progress.stars });
  let ok = true;
  if (getRaw(key) !== text) { // only real changes count as "changed since the last export"
    ok = setRaw(key, text);
    if (ok) setRaw(P + 'lastChange', new Date().toISOString());
  }
  if (summary) writeJSON(prefix(profile || activeProfile()) + 'summary.' + game, summary);
  return ok;
}
export function loadSummary(game, profile) {
  const s = readJSON(prefix(profile || activeProfile()) + 'summary.' + game, null);
  const owned = loadProgress(game, profile).owned.size; // the real list is the source of truth
  return {
    owned,
    maxed: s && Number.isFinite(s.maxed) ? s.maxed : 0,
    total: s && Number.isFinite(s.total) && s.total > 0 ? s.total : TOTALS[game],
  };
}

// ---------- Display settings (applied by js/prefs.js on every page) ----------
// Text size is 'auto' (follow the device) or a scale from TEXT_MIN to TEXT_MAX, stored as a string such as '0.85'.
export const TEXT_MIN = 0.6;
export const TEXT_MAX = 1.5;
function cleanText(v) {
  const n = typeof v === 'string' || typeof v === 'number' ? parseFloat(v) : NaN;
  if (!(n > 0)) return 'auto';
  return String(Math.round(Math.min(TEXT_MAX, Math.max(TEXT_MIN, n)) * 100) / 100);
}
export function loadPrefs() {
  const p = readJSON(P + 'prefs', {});
  return {
    text: isObject(p) ? cleanText(p.text) : 'auto',
    fx: isObject(p) && p.fx === 'off' ? 'off' : 'on',
  };
}
export function savePrefs(prefs) { return writeJSON(P + 'prefs', prefs); }

// ---------- App version seen on this device ----------
// Returns { updated, from, to }. "updated" is true the first time a page runs
// after the app version changed (never on the very first visit).
export function checkVersion() {
  const to = self.APP_VERSION || '';
  const from = getRaw(P + 'seenVersion');
  if (to && from !== to) setRaw(P + 'seenVersion', to);
  return { updated: !!from && !!to && from !== to, from, to };
}

// ---------- UI state ----------
export function loadUI(game) {
  const ui = readJSON(P + 'ui.' + game, {});
  return isObject(ui) ? ui : {};
}
export function saveUI(game, ui) { writeJSON(P + 'ui.' + game, ui); }

// ---------- Export ----------
export function buildExport() {
  const gamesOf = (profile) => {
    const games = {};
    for (const g of GAMES) {
      const p = loadProgress(g, profile);
      games[g] = { owned: Array.from(p.owned), stars: p.stars, summary: readJSON(prefix(profile) + 'summary.' + g, null) };
    }
    return games;
  };
  return {
    app: 'edf-unlock-tracker', version: 1, appVersion: self.APP_VERSION || '', exportedAt: new Date().toISOString(),
    games: gamesOf('1'), profile2: { games: gamesOf('2') }, profileNames: profileNames(),
  };
}
// Phones get the share sheet (Save to Files, AirDrop, ...) when the browser allows
// sharing this file type; everything else gets a normal download.
// Returns 'shared', 'downloaded' or 'cancelled'.
export async function exportProgress() {
  const text = JSON.stringify(buildExport(), null, 1);
  const now = new Date(); // local date, so the file name matches the day you exported
  const two = (n) => (n < 10 ? '0' : '') + n;
  const name = 'edf-unlocks-' + now.getFullYear() + '-' + two(now.getMonth() + 1) + '-' + two(now.getDate()) + '.json';
  try {
    const touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
    if (touch && typeof File === 'function' && navigator.canShare) {
      const file = new File([text], name, { type: 'application/json' });
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: 'EDF Unlock Tracker progress' });
        setRaw(P + 'lastExport', now.toISOString());
        return 'shared';
      }
    }
  } catch (e) {
    if (e && e.name === 'AbortError') return 'cancelled';
    // any other share failure falls through to a download
  }
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  setRaw(P + 'lastExport', now.toISOString());
  return 'downloaded';
}

// When progress was last exported and last changed (ISO strings, or null).
export function backupStatus() {
  const valid = (s) => (s && !Number.isNaN(Date.parse(s)) ? s : null);
  return { lastExport: valid(getRaw(P + 'lastExport')), lastChange: valid(getRaw(P + 'lastChange')) };
}

// ---------- Legacy EDF 4.1 checklist ----------
let legacyMapPromise = null;
function legacyMap() {
  if (!legacyMapPromise) {
    legacyMapPromise = fetch('data/edf41-legacy.json').then((r) => {
      if (!r.ok) throw new Error('The old-checklist map did not load. Check your connection and try again.');
      return r.json();
    });
    legacyMapPromise.catch(() => { legacyMapPromise = null; }); // allow a retry
  }
  return legacyMapPromise;
}
// legacyData: { rangerSave: { categoryId: [index, ...] }, ... }  ->  Set of new weapon ids
export async function convertLegacy(legacyData) {
  const map = await legacyMap();
  const ids = new Set();
  for (const key of LEGACY_KEYS) {
    const saved = legacyData[key];
    if (!isObject(saved) || !map[key]) continue;
    for (const cat of Object.keys(saved)) {
      const indexes = saved[cat];
      const slots = map[key][cat];
      if (!Array.isArray(indexes) || !Array.isArray(slots)) continue;
      for (const i of indexes) (slots[i] || []).forEach((id) => ids.add(id));
    }
  }
  return ids;
}
// Progress left on this device by the old checklist (same GitHub Pages domain).
export function findLegacyOnDevice() {
  const data = {};
  let count = 0;
  for (const key of LEGACY_KEYS) {
    const saved = readJSON(key, null);
    if (!isObject(saved)) continue;
    data[key] = saved;
    for (const cat of Object.keys(saved)) if (Array.isArray(saved[cat])) count += saved[cat].length;
  }
  return count > 0 ? { data, count } : null;
}
export function legacyDismissed() { return getRaw(P + 'legacyDone') === '1'; }
export function markLegacyDone() { setRaw(P + 'legacyDone', '1'); }

// Merge legacy ids into the active profile's EDF 4.1 progress (never removes anything already marked).
export async function importLegacy(legacyData) {
  const ids = await convertLegacy(legacyData);
  const p = loadProgress('edf41');
  ids.forEach((id) => p.owned.add(id));
  saveProgress('edf41', p, { owned: p.owned.size, maxed: 0, total: TOTALS.edf41 });
  markLegacyDone();
  return ids.size;
}

// ---------- Import (new format or old checklist export) ----------
function readText(file) {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => { // older browsers
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsText(file);
  });
}
// Returns a short description of what was imported. Throws Error with a readable message.
export async function importFile(file) {
  if (file.size > 5 * 1024 * 1024) throw new Error('That file is too large to be a tracker export.');
  let obj;
  try {
    obj = JSON.parse(await readText(file));
  } catch (e) {
    throw new Error('That file is not valid JSON. Choose a file exported from this tracker.');
  }
  if (isObject(obj) && obj.app === 'edf-unlock-tracker' && isObject(obj.games)) {
    // Files from before profiles existed only have "games"; that is profile 1.
    const sets = [['1', obj.games]];
    if (isObject(obj.profile2) && isObject(obj.profile2.games)) sets.push(['2', obj.profile2.games]);
    const done = [];
    let profile2HasData = false;
    for (const [profile, games] of sets) {
      for (const g of GAMES) {
        const src = games[g];
        if (!isObject(src)) continue;
        const owned = cleanOwned(src.owned);
        const stars = cleanStars(src.stars);
        const s = isObject(src.summary) ? src.summary : {};
        const summary = { owned: owned.length, maxed: Number.isFinite(s.maxed) ? s.maxed : 0, total: TOTALS[g] };
        if (!saveProgress(g, { owned: new Set(owned), stars }, summary, profile)) {
          throw new Error('Progress could not be saved on this device. Storage is full or blocked.');
        }
        if (profile === '1') done.push(GAME_NAMES[g]);
        else if (owned.length) profile2HasData = true;
      }
    }
    if (!done.length) throw new Error('The file has no EDF 4.1, 5 or 6 progress in it.');
    if (profile2HasData) setRaw(P + 'p2used', '1');
    if (isObject(obj.profileNames)) {
      renameProfile('1', obj.profileNames[1]);
      renameProfile('2', obj.profileNames[2]);
    }
    return 'Imported progress for ' + done.join(', ') + (profile2HasData ? ' (both profiles).' : '.');
  }
  if (isObject(obj) && obj.version === 1 && isObject(obj.data) && LEGACY_KEYS.some((k) => obj.data[k])) {
    const n = await importLegacy(obj.data);
    return 'Imported ' + n + ' EDF 4.1 weapons from the old checklist.';
  }
  throw new Error('This file was not made by the EDF Unlock Tracker or the EDF 4.1 checklist.');
}
