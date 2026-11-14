// ============================================================================
// store.js – everything that touches localStorage.
//
// Keys (one set per game: edf41, edf5, edf6):
//   edfTracker.<game>          { owned: [id, ...], stars: { id: [n, n, ...] } }
//   edfTracker.summary.<game>  { owned, maxed, total }   (read by the HQ page)
//   Those two belong to the profile "PC 1". Each game has eight profiles, one per
//   save slot: pc1-pc4 and con1-con4. The others keep their own copies under
//   edfTracker.<slot>.<...>, except Console 1, which uses edfTracker.p2.<...>
//   (PC 1 and Console 1 were "profile 1" and "profile 2" in v1.3-v1.4).
//   edfTracker.slot.<game>     the game's active profile, e.g. 'con2'
//   edfTracker.slotNames       { <game>: { <slot>: name } }   (only renamed profiles)
//   edfTracker.slotsUsed.<game> '1' once the game has used a profile other than PC 1
//   edfTracker.profile / .profileNames / .p2used   from v1.3-v1.4; still read as defaults
//   edfTracker.ui.<game>       { cls, cat, filter, detailOpen, scroll }   (ui.hq: { game })
//   edfTracker.lastExport / edfTracker.lastChange   ISO dates, for the backup line on HQ
//   edfTracker.prefs           { text: 'auto' | '0.6' ... '1.5' (a scale, set with the HQ slider), fx: 'on' | 'off',
//                                layout: 'fit' | 'scroll' (game pages: fit one screen, or taller lists on a scrolling page),
//                                type: { <game>: { font: id from js/prefs.js, size: 'same' | '0.6' ... '1.5', bold, italic, caps } } }
//
// Export file format: { app: "edf-unlock-tracker", version: 1, appVersion, exportedAt,
//   games: { <game>: {...} },                 PC 1 of each game
//   profile2: { games: { <game>: {...} } },   Console 1 of each game
//   slots: { <game>: { <slot>: {...} } },     the other six profiles of each game
//   slotNames: { <game>: { <slot>: name } } }
// Files from v1.3-v1.4 have only games, profile2 and profileNames: { 1, 2 }; they still import.
// ("version" is the file format; "appVersion" is the app release that wrote it.)
// The old EDF 4.1 checklist (EDF-4.1-PWA) stored rangerSave / wingdiverSave /
// airraiderSave / fencerSave, each { categoryId: [position, ...] } with the old
// site's own category ids ('assault-rifles', 'mid-range-electro', ...). Those are
// converted with data/edf41-legacy.json, which must use exactly the same ids.
//   edfTracker.legacyDone      '2' once that checklist was imported or declined
//                              ('1' is from before v1.4.1, when the import missed most weapons)
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

// ---------- Profiles: eight per game, one for each save slot (4 on PC, 4 on console) ----------
// Every game has its own active profile. PC 1 and Console 1 keep the storage keys
// that "profile 1" and "profile 2" had in v1.3-v1.4, so progress saved by those
// versions is simply there, and nothing has to be moved.
export const SLOTS = ['pc1', 'pc2', 'pc3', 'pc4', 'con1', 'con2', 'con3', 'con4'];
export const PLATFORMS = [
  { id: 'pc', name: 'PC', slots: ['pc1', 'pc2', 'pc3', 'pc4'] },
  { id: 'con', name: 'Console', slots: ['con1', 'con2', 'con3', 'con4'] },
];
const OLD_PROFILE_KEY = P + 'profile'; // '1' | '2': one setting for all three games (v1.3-v1.4)
const isSlot = (s) => SLOTS.indexOf(s) !== -1;
const isGame = (g) => GAMES.indexOf(g) !== -1;
// Accepts a slot id or nothing (the game's active profile). The ids '1' and '2' come from a page
// still running v1.3-v1.4 scripts: they mean PC 1 and Console 1 until the game has a profile
// chosen in this version, and after that they follow the chosen profile, so such a page
// never saves into a different profile from the one HQ shows as in use.
const slotOf = (game, slot) => {
  if (isSlot(slot)) return slot;
  if ((slot === '1' || slot === '2') && !isSlot(getRaw(slotKey(game)))) return slot === '2' ? 'con1' : 'pc1';
  return activeSlot(game);
};
const prefix = (slot) => (slot === 'pc1' ? P : slot === 'con1' ? P + 'p2.' : P + slot + '.');
export const defaultSlotName = (slot) => (slot.indexOf('pc') === 0 ? 'PC ' : 'Console ') + slot.slice(-1);
export const slotKey = (game) => P + 'slot.' + game;
export function activeSlot(game) {
  const s = getRaw(slotKey(game));
  if (isSlot(s)) return s;
  return getRaw(OLD_PROFILE_KEY) === '2' ? 'con1' : 'pc1'; // not chosen yet: follow the old two-profile setting
}
export function setActiveSlot(game, slot) {
  const s = isSlot(slot) ? slot : 'pc1';
  const ok = setRaw(slotKey(game), s);
  if (s !== 'pc1') setRaw(P + 'slotsUsed.' + game, '1');
  return ok;
}
// Called when a profile is given weapons without being switched to (Import from game save).
export function noteSlotUsed(game, slot) {
  if (isGame(game) && isSlot(slot) && slot !== 'pc1') setRaw(P + 'slotsUsed.' + game, '1');
}
// True once the game has used a profile other than PC 1; until then its pages look as they did with one profile.
export function slotsInUse(game) {
  return activeSlot(game) !== 'pc1' || getRaw(P + 'slotsUsed.' + game) === '1' || getRaw(P + 'p2used') === '1';
}
const cleanName = (v) => (typeof v === 'string' ? v.replace(/\s+/g, ' ').trim().slice(0, 16) : '');
// A name given to one of the two profiles of v1.3-v1.4 ('' if it was left at its default).
const oldName = (names, id) => {
  const v = cleanName(isObject(names) ? names[id] : '');
  return v && v !== 'Profile ' + id ? v : '';
};
// { pc1: name, ..., con4: name } for one game.
export function slotNames(game) {
  const all = readJSON(P + 'slotNames', {});
  const mine = isObject(all) && isObject(all[game]) ? all[game] : {};
  const old = readJSON(P + 'profileNames', {});
  const out = {};
  for (const s of SLOTS) {
    out[s] = cleanName(mine[s]) || (s === 'pc1' ? oldName(old, 1) : s === 'con1' ? oldName(old, 2) : '') || defaultSlotName(s);
  }
  return out;
}
// An empty name puts the default back.
export function renameSlot(game, slot, name) {
  if (!isGame(game) || !isSlot(slot)) return false;
  const all = readJSON(P + 'slotNames', {});
  const names = isObject(all) ? all : {};
  const mine = isObject(names[game]) ? names[game] : {};
  mine[slot] = cleanName(name) || defaultSlotName(slot);
  names[game] = mine;
  return writeJSON(P + 'slotNames', names);
}
export const progressKey = (game, slot) => prefix(slotOf(game, slot)) + game;
const summaryKey = (game, slot) => prefix(slotOf(game, slot)) + 'summary.' + game;

// The names v1.3-v1.4 pages call. Kept so a page that is still running those
// scripts while an update installs keeps working; nothing in this version uses them.
export const PROFILE_KEY = OLD_PROFILE_KEY;
export function activeProfile() { return getRaw(OLD_PROFILE_KEY) === '2' ? '2' : '1'; }
export function setActiveProfile(id) {
  setRaw(OLD_PROFILE_KEY, id === '2' ? '2' : '1');
  if (id === '2') setRaw(P + 'p2used', '1');
}
export function profilesInUse() { return getRaw(P + 'p2used') === '1'; }
export function profileNames() {
  const n = readJSON(P + 'profileNames', {});
  return { 1: cleanName(isObject(n) ? n[1] : '') || 'Profile 1', 2: cleanName(isObject(n) ? n[2] : '') || 'Profile 2' };
}
export function renameProfile(id, name) {
  const names = profileNames();
  names[id === '2' ? 2 : 1] = cleanName(name) || 'Profile ' + (id === '2' ? 2 : 1);
  return writeJSON(P + 'profileNames', names);
}

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
// "slot" is optional everywhere below; the game's active profile is used when it is left out.
export function loadProgress(game, slot) {
  const o = readJSON(progressKey(game, slot), {});
  return { owned: new Set(cleanOwned(o && o.owned)), stars: cleanStars(o && o.stars) };
}
export function saveProgress(game, progress, summary, slot) {
  const key = progressKey(game, slot);
  const text = JSON.stringify({ owned: Array.from(progress.owned), stars: progress.stars });
  let ok = true;
  const had = getRaw(key);
  const nothing = had === null && !Array.from(progress.owned).length && !Object.keys(progress.stars).length; // nothing saved, nothing to save
  if (had !== text && !nothing) { // only real changes count as "changed since the last export"
    ok = setRaw(key, text);
    if (ok) setRaw(P + 'lastChange', new Date().toISOString());
  }
  if (summary) writeJSON(summaryKey(game, slot), summary);
  return ok;
}
export function loadSummary(game, slot) {
  const s = readJSON(summaryKey(game, slot), null);
  const owned = loadProgress(game, slot).owned.size; // the real list is the source of truth
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
// Each game's own text settings; anything missing or malformed falls back to "same as everywhere else".
function cleanType(v) {
  const out = {};
  for (const g of GAMES) {
    const t = isObject(v) && isObject(v[g]) ? v[g] : {};
    const size = cleanText(t.size);
    out[g] = {
      font: typeof t.font === 'string' && /^[a-z0-9]{1,16}$/.test(t.font) ? t.font : 'default',
      size: size === 'auto' ? 'same' : size,
      bold: t.bold === true, italic: t.italic === true, caps: t.caps === true,
    };
  }
  return out;
}
export function loadPrefs() {
  const p = readJSON(P + 'prefs', {});
  return {
    text: isObject(p) ? cleanText(p.text) : 'auto',
    fx: isObject(p) && p.fx === 'off' ? 'off' : 'on',
    layout: isObject(p) && p.layout === 'scroll' ? 'scroll' : 'fit',
    type: cleanType(isObject(p) ? p.type : null),
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
// HQ lists what is new once per version. `seen` is what checkVersion just returned there. The list is
// also due when the update was first met on a game page, which only says "Updated".
export function newsDue(seen) {
  const to = self.APP_VERSION || '';
  const had = getRaw(P + 'newsVersion');
  if (to && had !== to) setRaw(P + 'newsVersion', to);
  return !!to && !!seen && !!seen.from && (seen.updated || had !== to);
}

// ---------- UI state ----------
export function loadUI(game) {
  const ui = readJSON(P + 'ui.' + game, {});
  return isObject(ui) ? ui : {};
}
export function saveUI(game, ui) { writeJSON(P + 'ui.' + game, ui); }

// ---------- Export ----------
// All 24 profiles go into the file, empty ones included, so importing it puts
// every profile back exactly as it was. PC 1 and Console 1 sit where v1.3-v1.4
// files had "profile 1" and "profile 2", so those versions can still read them.
export function buildExport() {
  const one = (g, slot) => {
    const p = loadProgress(g, slot);
    return { owned: Array.from(p.owned), stars: p.stars, summary: readJSON(summaryKey(g, slot), null) };
  };
  const gamesOf = (slot) => {
    const games = {};
    for (const g of GAMES) games[g] = one(g, slot);
    return games;
  };
  const slots = {};
  const names = {};
  for (const g of GAMES) {
    slots[g] = {};
    for (const s of SLOTS) if (s !== 'pc1' && s !== 'con1') slots[g][s] = one(g, s);
    names[g] = slotNames(g);
  }
  return {
    app: 'edf-unlock-tracker', version: 1, appVersion: self.APP_VERSION || '', exportedAt: new Date().toISOString(),
    games: gamesOf('pc1'), profile2: { games: gamesOf('con1') }, slots, slotNames: names,
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
// Before v1.4.1 the import only matched 6 of the 31 categories, so anyone who
// answered the offer back then ('1') is asked once more; '2' is the answer that counts.
export function legacyDismissed() { return getRaw(P + 'legacyDone') === '2'; }
export function legacyAskedBefore() { return getRaw(P + 'legacyDone') === '1'; }
export function markLegacyDone() { setRaw(P + 'legacyDone', '2'); }

// Merge legacy ids into one EDF 4.1 profile (never removes anything already marked).
// "slot" is the profile to add to; EDF 4.1's profile in use when it is left out.
export async function importLegacy(legacyData, slot) {
  const target = slotOf('edf41', slot); // settled before the lookup file is fetched
  const ids = await convertLegacy(legacyData);
  const p = loadProgress('edf41', target);
  ids.forEach((id) => p.owned.add(id));
  saveProgress('edf41', p, { owned: p.owned.size, maxed: 0, total: TOTALS.edf41 }, target);
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
    // Every profile in the file replaces the same profile here; profiles the file
    // does not mention are left alone. "games" is PC 1 (the only profile in the
    // oldest files), "profile2" is Console 1, "slots" holds the other six per game.
    const p2 = isObject(obj.profile2) && isObject(obj.profile2.games) ? obj.profile2.games : {};
    const more = isObject(obj.slots) ? obj.slots : {};
    const done = [];
    let filled = 0; // profiles in the file that have at least one weapon
    for (const g of GAMES) {
      const perSlot = isObject(more[g]) ? more[g] : {};
      let any = false;
      for (const slot of SLOTS) {
        const src = slot === 'pc1' ? obj.games[g] : slot === 'con1' ? p2[g] : perSlot[slot];
        if (!isObject(src)) continue;
        const owned = cleanOwned(src.owned);
        const stars = cleanStars(src.stars);
        const s = isObject(src.summary) ? src.summary : {};
        const summary = { owned: owned.length, maxed: Number.isFinite(s.maxed) ? s.maxed : 0, total: TOTALS[g] };
        if (!saveProgress(g, { owned: new Set(owned), stars }, summary, slot)) {
          throw new Error('Progress could not be saved on this device. Storage is full or blocked.');
        }
        any = true;
        if (owned.length) {
          filled++;
          if (slot !== 'pc1') setRaw(P + 'slotsUsed.' + g, '1');
        }
      }
      if (any) done.push(GAME_NAMES[g]);
    }
    if (!done.length) throw new Error('The file has no EDF 4.1, 5 or 6 progress in it.');
    if (isObject(obj.slotNames)) {
      for (const g of GAMES) {
        const names = obj.slotNames[g];
        if (!isObject(names)) continue;
        for (const slot of SLOTS) if (typeof names[slot] === 'string') renameSlot(g, slot, names[slot]);
      }
    } else if (isObject(obj.profileNames)) { // a v1.3-v1.4 file: one pair of names for all three games
      for (const g of GAMES) {
        if (oldName(obj.profileNames, 1)) renameSlot(g, 'pc1', obj.profileNames[1]);
        if (oldName(obj.profileNames, 2)) renameSlot(g, 'con1', obj.profileNames[2]);
      }
    }
    return 'Imported progress for ' + done.join(', ') + (filled > 1 ? ' (' + filled + ' profiles).' : '.');
  }
  if (isObject(obj) && obj.version === 1 && isObject(obj.data) && LEGACY_KEYS.some((k) => obj.data[k])) {
    const n = await importLegacy(obj.data);
    return 'Imported ' + n + ' EDF 4.1 weapons from the old checklist.';
  }
  throw new Error('This file was not made by the EDF Unlock Tracker or the EDF 4.1 checklist.');
}
