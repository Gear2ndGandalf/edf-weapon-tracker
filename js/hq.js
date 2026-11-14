// ============================================================================
// hq.js – HQ page: shows progress for each game, export/import, and offers
// to bring over progress from the old EDF 4.1 checklist on this device.
// ============================================================================
import * as store from './store.js';

const $ = (sel) => document.querySelector(sel);
const STAR = '<i class="ico ico--star" aria-hidden="true"></i>';
const CHECK = '<i class="ico ico--check" aria-hidden="true"></i>';

function showProgress() {
  for (const g of store.GAMES) {
    const s = store.loadSummary(g);
    const pct = s.total ? Math.round((s.owned / s.total) * 100) : 0;
    const count = document.querySelector('[data-count="' + g + '"]');
    const bar = document.querySelector('[data-bar="' + g + '"]');
    if (count) {
      count.innerHTML = CHECK + '<span class="sr-only">Owned </span>' + s.owned + '/' + s.total +
        (g === 'edf41' ? '' : ' · ' + STAR + '<span class="sr-only">Fully upgraded </span>' + s.maxed);
    }
    if (bar) bar.style.width = pct + '%';
  }
}

// ---------- Backup reminder ----------
function showBackup() {
  const el = $('#backup');
  const b = store.backupStatus();
  const hasProgress = store.GAMES.some((g) => (store.SLOTS || [undefined]).some((slot) => store.loadSummary(g, slot).owned > 0)); // any profile
  let text = '';
  if (b.lastExport) {
    const when = new Date(b.lastExport).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    const changed = b.lastChange && Date.parse(b.lastChange) > Date.parse(b.lastExport);
    text = 'Last export: ' + when + '.' + (changed ? ' Progress has changed since.' : '');
  } else if (hasProgress) {
    text = 'Not exported yet. Export to keep a backup.';
  }
  el.textContent = text;
  el.hidden = !text;
}

// Messages are plain text; buttons are added as real elements.
function notice(text, buttons) {
  const n = $('#notice');
  n.textContent = '';
  if (!text) { n.hidden = true; return; }
  const p = document.createElement('p');
  p.textContent = text;
  n.appendChild(p);
  (buttons || []).forEach((b) => {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'hq-btn' + (b.primary ? ' hq-btn--red' : '');
    el.textContent = b.label;
    el.addEventListener('click', b.run);
    n.appendChild(el);
  });
  n.hidden = false;
}

function offerLegacy() {
  if (store.legacyDismissed()) return;
  const found = store.findLegacyOnDevice();
  if (!found) return;
  // Asked again after v1.4.1 fixed the import (see legacyAskedBefore in store.js). Importing only adds weapons.
  const again = store.legacyAskedBefore && store.legacyAskedBefore();
  notice('Your old EDF 4.1 checklist on this device has ' + found.count + ' weapons checked. ' +
    (again ? 'Earlier versions missed most of them when importing. Import them all into EDF 4.1 now?' : 'Import them into EDF 4.1?'), [
    {
      label: 'Import', primary: true,
      run: async () => {
        try {
          const n = await store.importLegacy(found.data);
          notice('Imported ' + n + ' EDF 4.1 weapons from the old checklist.');
          showProfiles();
          showProgress();
          showBackup();
        } catch (err) {
          notice(err && err.message ? err.message : 'The old checklist could not be imported.');
        }
      },
    },
    { label: 'Not now', run: () => { store.markLegacyDone(); notice(''); } },
  ]);
}

$('#export').addEventListener('click', async () => {
  const how = await store.exportProgress();
  if (how === 'downloaded') notice('Progress exported. Keep the file somewhere safe, then use Import progress on any device.');
  if (how === 'shared') notice('Progress exported. Use Import progress on any device to load it.');
  showBackup();
});
$('#import').addEventListener('click', () => $('#importfile').click());
$('#importfile').addEventListener('change', async (e) => {
  const file = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!file) return;
  if (!window.confirm('Importing replaces the saved progress here with the file\u2019s, for every game and profile the file holds. A profile that is empty in the file becomes empty here. Continue?')) return;
  try {
    notice(await store.importFile(file));
    ['edf5', 'edf6'].forEach((g) => (store.SLOTS || []).forEach((slot) => { const s = store.loadSummary(g, slot); if (s.owned > 0 || s.maxed > 0) recountMaxed(g, slot); }));
    showProfiles();
    showProgress();
    showBackup();
  } catch (err) {
    notice(err && err.message ? err.message : 'Import failed.');
    showProfiles(); // some profiles may already have been replaced before it failed
    showProgress();
    showBackup();
  }
});

// ---------- Profiles: eight per game, one for each save slot (4 on PC, 4 on console) ----------
// The game buttons choose whose profiles are listed. Tapping a profile makes it
// that game's profile in use: its progress is what the game page and its card show.
// (During an update a phone can briefly pair this script with the previous
// index.html or store.js, which have no per-game profiles; then this panel is left alone.)
const slotButtons = document.querySelectorAll('#segProfile [data-slot]');
const hasSlots = !!(store.SLOTS && slotButtons.length && $('#segGame') && $('#slotNow'));
let shownGame = store.loadUI('hq').game;
if (store.GAMES.indexOf(shownGame) === -1) shownGame = store.GAMES[0];
function showProfiles() {
  if (!store.SLOTS) return;
  for (const g of store.GAMES) { // the profile in use, on each game card
    const tag = document.querySelector('[data-slotname="' + g + '"]');
    if (!tag) continue;
    const used = store.slotsInUse(g);
    tag.textContent = used ? store.slotNames(g)[store.activeSlot(g)] : '';
    tag.hidden = !used;
  }
  if (!hasSlots) return;
  const names = store.slotNames(shownGame);
  const active = store.activeSlot(shownGame);
  document.querySelectorAll('#segGame button[data-game]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.game === shownGame)));
  slotButtons.forEach((b) => {
    const slot = b.dataset.slot;
    const s = store.loadSummary(shownGame, slot);
    b.querySelector('.slot__name').textContent = names[slot];
    b.querySelector('.slot__count').textContent = s.owned ? s.owned + '/' + s.total : 'Empty';
    b.classList.toggle('is-empty', !s.owned);
    b.setAttribute('aria-label', names[slot] + ', ' + (s.owned ? s.owned + ' of ' + s.total + ' owned' : 'empty'));
    b.setAttribute('aria-pressed', String(slot === active));
  });
  $('#slotNow').textContent = store.GAME_NAMES[shownGame] + ' uses ' + names[active];
  if (hasSaveIn && !saveIn.hidden) showSaveTarget(); // the open "Import from game save" panel lists profiles too
}
if (!hasSlots) { // mismatched files during an update: hide a profile list that could not work
  ['#segProfile', '#segGame'].forEach((sel) => { if ($(sel)) $(sel).hidden = true; });
} else {
  $('#segGame').addEventListener('click', (e) => {
    const b = e.target.closest ? e.target.closest('button[data-game]') : null;
    if (!b || store.GAMES.indexOf(b.dataset.game) === -1) return;
    shownGame = b.dataset.game;
    store.saveUI('hq', { game: shownGame });
    showProfiles();
    showGameText();
  });
  $('#segProfile').addEventListener('click', (e) => {
    const b = e.target.closest ? e.target.closest('button') : null;
    if (!b) return;
    if (b.dataset.slot) {
      if (!store.setActiveSlot(shownGame, b.dataset.slot)) notice('Settings cannot be saved on this device. Storage is full or blocked.');
    } else if (b.id === 'renameProfile') {
      const active = store.activeSlot(shownGame);
      const name = window.prompt('Name for this ' + store.GAME_NAMES[shownGame] + ' profile (up to 16 characters)', store.slotNames(shownGame)[active]);
      if (name === null) return; // cancelled
      if (!store.renameSlot(shownGame, active, name)) notice('The name cannot be saved on this device. Storage is full or blocked.');
    }
    showProfiles();
    showProgress();
    showBackup();
  });
}

// ---------- Import from game save ----------
// Marks the weapons owned by reading the player's own PC save. The reading is done by
// js/savefile.js, which is only loaded when this panel is opened. Nothing is saved until
// the player has seen what would change and picked Add or Match; Undo takes it back.
// In EDF 5 and 6 the save also holds each weapon's star levels, which are read too unless unticked.
// (The button stays hidden when this script is paired with a previous index.html or store.js.)
const saveIn = $('#saveIn');
const saveOpen = $('#saveOpen');
const hasSaveIn = !!(store.SLOTS && saveIn && saveOpen && $('#saveGame') && $('#saveSlot') && $('#saveFile') && $('#saveResult') && $('#savePath') && $('#saveName') &&
  $('#saveClose') && $('#savePick') && $('#saveCopy'));
let saveLib = null;     // promise for js/savefile.js, once asked for
let saveLibNow = null;  // the module itself, once loaded
let saveUndo = null;    // what the last import changed: { game, slot, added: [id], removed: [id], stars: { id: { was, now } }, after: { id: stars } }
let savePreview = false; // true while the result area shows a preview with Add / Match buttons
// "Also read star levels" as it is ticked right now (a preview can outlive a change of the box).
const starsWanted = () => !!($('#saveStars') && $('#saveStars').checked);
let saveTurn = 0;       // goes up whenever the panel's question changes, so an answer that arrives late is dropped
const weapons = (n) => n + (n === 1 ? ' weapon' : ' weapons');
function saveLibrary() {
  if (!saveLib) {
    saveLib = import('./savefile.js').then((lib) => { saveLibNow = lib; return lib; });
    saveLib.catch(() => { saveLib = null; }); // allow another try
  }
  return saveLib;
}
// The result area: lines of plain text, then buttons. Keyboard focus stays in the area if it was there.
function saveMessage(lines, buttons) {
  const box = $('#saveResult');
  const hadFocus = box.contains(document.activeElement);
  box.textContent = '';
  (lines || []).forEach((text) => {
    const p = document.createElement('p');
    p.textContent = text;
    box.appendChild(p);
  });
  if (buttons && buttons.length) {
    const row = document.createElement('div');
    row.className = 'savein__row';
    buttons.forEach((b) => {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = 'hq-btn' + (b.primary ? ' hq-btn--red' : '');
      el.textContent = b.label;
      el.addEventListener('click', b.run);
      row.appendChild(el);
    });
    box.appendChild(row);
  }
  box.hidden = !(lines && lines.length);
  if (hadFocus) (box.querySelector('button') || $('#savePick')).focus();
}
const saveTargetName = (game, slot) => store.GAME_NAMES[game] + ' · ' + store.slotNames(game)[slot];
// The profile list and folder path for the game chosen in the panel. The chosen profile is kept
// while the game stays the same; `fresh` starts over on the game's profile in use.
function showSaveTarget(fresh) {
  const lib = saveLibNow;
  const game = $('#saveGame').value;
  if (!lib || !lib.SAVES[game]) return;
  const names = store.slotNames(game);
  const active = store.activeSlot(game);
  const list = $('#saveSlot');
  const keep = !fresh && list.dataset.game === game && store.SLOTS.indexOf(list.value) !== -1 ? list.value : active;
  list.textContent = '';
  store.SLOTS.forEach((slot) => {
    const o = document.createElement('option');
    o.value = slot;
    o.textContent = names[slot] + (slot === active ? ' (in use)' : '');
    list.appendChild(o);
  });
  list.value = keep;
  list.dataset.game = game;
  $('#savePath').textContent = lib.SAVES[game].where;
  $('#saveName').textContent = lib.SAVES[game].file;
  if ($('#saveStarsRow')) $('#saveStarsRow').hidden = !(lib.SAVES[game].rowSize >= 12); // EDF 4.1 has no star levels
  savePreview = false;
}
function refreshAfterSave() {
  showProfiles();
  showProgress();
  showBackup();
}
// How many owned weapons have every star, counted the way the game page counts them. The game's
// weapon list is needed for the star caps; if it cannot be fetched the old number is kept, capped.
async function recountMaxed(game, slot) {
  let data = null;
  try {
    const res = await fetch('data/' + game + '.json');
    if (res.ok) data = await res.json();
  } catch (e) { /* offline and not saved yet: keep the old number, capped; the game page corrects it when next opened */ }
  const p = store.loadProgress(game, slot); // read after the wait, so nothing done meanwhile is counted wrongly
  const s = store.loadSummary(game, slot);
  let maxed = Math.min(s.maxed, p.owned.size);
  if (data && Array.isArray(data.classes)) {
    maxed = 0;
    if (data.hasStars) {
      for (const c of data.classes) for (const k of c.cats) for (const t of k.items) {
        const up = t[4] || [];
        const have = p.stars[t[0]] || [];
        if (up.length && p.owned.has(t[0]) && up.every((u, i) => (have[i] | 0) >= u[1])) maxed++;
      }
    }
  }
  store.saveProgress(game, p, { owned: p.owned.size, maxed, total: s.total }, slot);
  refreshAfterSave();
}
// Star levels, compared as lists of the same length (a weapon without saved stars counts as all zero).
const starList = (list, length) => Array.from({ length }, (_, i) => (list && list[i]) | 0);
const sameStars = (a, b) => a.length === b.length && a.every((n, i) => n === b[i]);
// What importing `found` (from readSave) into a profile would change, worked out from the profile as it
// is right now. `match` makes the profile the same as the save; otherwise weapons are only added and
// stars only raised. `withStars` is off when the player unticked "Also read star levels".
function planSave(p, found, match, withStars) {
  const inSave = new Set(found.owned);
  const added = found.owned.filter((id) => !p.owned.has(id));
  const removed = match ? Array.from(p.owned).filter((id) => !inSave.has(id)) : [];
  const stars = {}; // id -> { was: list or null, now: list }
  let up = 0;
  let down = 0;
  if (withStars && found.stars) {
    found.owned.forEach((id) => {
      const want = found.stars[id];
      if (!want || !want.length) return;
      // What is saved here counts up to the most each upgrade can have.
      const caps = (found.most && found.most[id]) || [];
      const have = starList(p.stars[id], want.length).map((n, i) => (caps[i] >= 0 ? Math.min(n, caps[i]) : n));
      const now = match ? want.slice() : want.map((n, i) => Math.max(n, have[i]));
      if (sameStars(now, have)) return;
      stars[id] = { was: p.stars[id] ? p.stars[id].slice() : null, now };
      if (now.some((n, i) => n > have[i])) up++;
      if (now.some((n, i) => n < have[i])) down++;
    });
  }
  return { added, removed, stars, up, down };
}
// Change one profile the way planSave describes, and remember exactly what was changed for Undo.
function applySave(game, slot, found, match, withStars) {
  const p = store.loadProgress(game, slot);
  const plan = planSave(p, found, match, withStars);
  plan.added.forEach((id) => p.owned.add(id));
  plan.removed.forEach((id) => p.owned.delete(id));
  Object.keys(plan.stars).forEach((id) => {
    const now = plan.stars[id].now;
    if (now.some((n) => n > 0)) p.stars[id] = now; else delete p.stars[id];
  });
  const s = store.loadSummary(game, slot);
  if (!store.saveProgress(game, p, { owned: p.owned.size, maxed: Math.min(s.maxed, p.owned.size), total: s.total }, slot)) {
    saveMessage(['Progress could not be saved on this device. Storage is full or blocked.']);
    return;
  }
  if (p.owned.size && store.noteSlotUsed) store.noteSlotUsed(game, slot);
  const starred = Object.keys(plan.stars).length;
  const did = [];
  if (plan.added.length) did.push('marked ' + weapons(plan.added.length));
  if (plan.removed.length) did.push('unmarked ' + weapons(plan.removed.length));
  if (starred) did.push('set the stars of ' + weapons(starred));
  // "after" is how the added weapons' stars stand now, so Undo can tell if the player has upgraded one since.
  const after = {};
  plan.added.forEach((id) => { after[id] = p.stars[id] ? p.stars[id].slice() : null; });
  saveUndo = did.length ? { game, slot, added: plan.added, removed: plan.removed, stars: plan.stars, after } : null;
  savePreview = false;
  const text = did.length ? did.join(', ').replace(/^./, (c) => c.toUpperCase()) : 'Nothing needed changing';
  saveMessage([text + ' in ' + saveTargetName(game, slot) + '.'], did.length ? [{ label: 'Undo', run: undoSave }] : []);
  refreshAfterSave();
  recountMaxed(game, slot);
}
// Takes back exactly what the last import changed. Anything marked, unmarked or upgraded since then stays:
// a weapon's stars are only put back if they are still what the import left, and a weapon the import
// marked stays marked if the player has changed its stars since.
function undoSave() {
  const u = saveUndo;
  if (!u) return;
  saveUndo = null;
  savePreview = false;
  const p = store.loadProgress(u.game, u.slot);
  const text = (list) => JSON.stringify(list || []).replace(/^\[(0,)*0?\]$/, '[]'); // no stars and all zero are the same
  u.added.forEach((id) => {
    if (u.after && text(p.stars[id]) !== text(u.after[id])) return; // upgraded since the import: it stays
    p.owned.delete(id);
  });
  u.removed.forEach((id) => p.owned.add(id));
  Object.keys(u.stars || {}).forEach((id) => {
    const change = u.stars[id];
    if (!sameStars(starList(p.stars[id], change.now.length), change.now)) return; // changed again since the import
    if (change.was) p.stars[id] = change.was; else delete p.stars[id];
  });
  const s = store.loadSummary(u.game, u.slot);
  if (!store.saveProgress(u.game, p, { owned: p.owned.size, maxed: Math.min(s.maxed, p.owned.size), total: s.total }, u.slot)) {
    saveMessage(['Progress could not be saved on this device. Storage is full or blocked.']);
    return;
  }
  saveMessage(['The import into ' + saveTargetName(u.game, u.slot) + ' was taken back.']);
  refreshAfterSave();
  recountMaxed(u.game, u.slot);
}
// Read the chosen file and show what importing it would change.
async function previewSave(file) {
  let game = $('#saveGame').value;
  const slot = $('#saveSlot').value;
  if (!file || store.GAMES.indexOf(game) === -1 || store.SLOTS.indexOf(slot) === -1) return;
  const turn = ++saveTurn;
  saveUndo = null;
  savePreview = false;
  saveMessage(['Reading the save…']);
  try {
    const lib = await saveLibrary();
    if (turn !== saveTurn) return;
    // Each game's save has its own size, so a file picked with the wrong Game chosen is recognised,
    // and anything else is turned away without being read.
    const fits = store.GAMES.filter((g) => lib.SAVES[g] && lib.SAVES[g].size === file.size);
    if (!fits.length) throw lib.wrongFile(game);
    const switched = fits[0] !== game;
    if (switched) {
      game = fits[0];
      $('#saveGame').value = game;
      showSaveTarget();
      $('#saveSlot').value = slot; // the same profile number, in the right game
    }
    let data;
    try {
      data = typeof file.arrayBuffer === 'function' ? await file.arrayBuffer() : await new Response(file).arrayBuffer();
    } catch (e) { // moved, deleted or locked since it was chosen
      throw Object.assign(new Error('The file could not be opened. It may have been moved or be in use; choose it again.'), { readable: true });
    }
    const found = await lib.readSave(game, data);
    if (turn !== saveTurn) return; // the game, profile or file was changed while this one was being read
    const withStars = !!(found.stars && $('#saveStars') && $('#saveStars').checked);
    const p = store.loadProgress(game, slot);
    const add = planSave(p, found, false, withStars);
    const match = planSave(p, found, true, withStars);
    const lines = ['This save owns ' + found.owned.length + ' of ' + found.total + ' weapons. ' + saveTargetName(game, slot) + ' has ' + p.owned.size + ' marked.'];
    if (switched) lines.unshift('This is an ' + store.GAME_NAMES[game] + ' save, so Game was changed to ' + store.GAME_NAMES[game] + '.');
    const buttons = [];
    const adds = [];
    if (add.added.length) adds.push('marks the ' + weapons(add.added.length) + ' the save owns that ' + (add.added.length === 1 ? 'is' : 'are') + ' not marked yet');
    if (add.up) adds.push('raises the stars of ' + weapons(add.up));
    const more = [];
    if (match.removed.length) more.push('unmarks the ' + weapons(match.removed.length) + ' marked here that this save does not own');
    if (match.down) more.push('lowers the stars of ' + weapons(match.down) + ' to the save\'s levels');
    const noStars = !found.stars && lib.hasStarLevels && lib.hasStarLevels(game) && $('#saveStars') && $('#saveStars').checked;
    if (!adds.length && !more.length) {
      lines.push(withStars ? 'They already match, weapons and stars, so there is nothing to import.' : 'They already match, so there is nothing to import.');
    } else {
      if (adds.length) {
        lines.push((add.added.length ? 'Add: ' : 'Raise stars: ') + adds.join(' and ') + '. Nothing is unmarked' + (withStars ? ' or lowered.' : '.'));
        buttons.push({ label: add.added.length ? 'Add ' + add.added.length : 'Raise stars', primary: true, run: () => applySave(game, slot, found, false, withStars && starsWanted()) });
      }
      if (more.length) {
        lines.push('Match: ' + (adds.length ? 'does that and also ' : '') + more.join(' and ') + '.');
        buttons.push({ label: 'Match the save', primary: !adds.length, run: () => applySave(game, slot, found, true, withStars && starsWanted()) });
      }
    }
    if (noStars) lines.push('Star levels could not be read this time. Reload this page and choose the file again to bring them over.');
    buttons.push({ label: 'Cancel', run: () => { savePreview = false; saveMessage([]); } });
    saveMessage(lines, buttons);
    savePreview = true;
  } catch (err) {
    if (turn !== saveTurn) return;
    saveMessage([err && err.readable ? err.message : 'The save could not be read.']);
  }
}
if (hasSaveIn) {
  saveOpen.hidden = false;
  const hasFiles = (e) => !!(e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') !== -1);
  const closeSave = () => {
    saveTurn++;
    const hadFocus = saveIn.contains(document.activeElement);
    saveIn.hidden = true;
    saveOpen.setAttribute('aria-expanded', 'false');
    saveMessage([]);
    saveUndo = null;
    if (hadFocus) saveOpen.focus();
  };
  saveOpen.addEventListener('click', async () => {
    if (!saveIn.hidden) { closeSave(); return; }
    try {
      const lib = await saveLibrary();
      const games = store.GAMES.filter((g) => lib.SAVES[g]);
      const list = $('#saveGame');
      list.textContent = '';
      games.forEach((g) => {
        const o = document.createElement('option');
        o.value = g;
        o.textContent = store.GAME_NAMES[g];
        list.appendChild(o);
      });
      list.value = games.indexOf(shownGame) !== -1 ? shownGame : games[0];
      showSaveTarget(true);
      saveMessage([]);
      saveIn.hidden = false;
      saveOpen.setAttribute('aria-expanded', 'true');
      if (saveIn.scrollIntoView) saveIn.scrollIntoView({ block: 'nearest' });
      $('#saveTitle').focus();
    } catch (err) {
      notice('The save reader did not load. Check your connection, reload this page and try again.');
    }
  });
  $('#saveClose').addEventListener('click', closeSave);
  $('#saveGame').addEventListener('change', () => { saveTurn++; saveUndo = null; showSaveTarget(true); saveMessage([]); });
  $('#saveSlot').addEventListener('change', () => { saveTurn++; saveUndo = null; saveMessage([]); });
  if ($('#saveStars')) {
    $('#saveStars').addEventListener('change', () => { // a preview made for the other choice is dropped; a finished import keeps its Undo
      if (!savePreview) return;
      savePreview = false;
      saveMessage([]);
    });
  }
  $('#savePick').addEventListener('click', () => $('#saveFile').click());
  $('#saveFile').addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    previewSave(file);
  });
  // A file can also be dropped onto the panel. While the panel is open, a file dropped beside it
  // is ignored, so a near miss does not make the browser open the save as a page.
  saveIn.addEventListener('dragover', (e) => { if (hasFiles(e)) { e.preventDefault(); saveIn.classList.add('is-drop'); } });
  saveIn.addEventListener('dragleave', (e) => { if (!saveIn.contains(e.relatedTarget)) saveIn.classList.remove('is-drop'); });
  saveIn.addEventListener('drop', (e) => {
    saveIn.classList.remove('is-drop');
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.stopPropagation();
    previewSave(e.dataTransfer.files && e.dataTransfer.files[0]);
  });
  ['dragover', 'drop'].forEach((type) => window.addEventListener(type, (e) => { if (!saveIn.hidden && hasFiles(e)) e.preventDefault(); }));
  $('#saveCopy').addEventListener('click', () => {
    const btn = $('#saveCopy');
    const said = (text) => { btn.textContent = text; setTimeout(() => { btn.textContent = 'Copy'; }, 1800); };
    const selectIt = () => { // no clipboard access: select the path so it can be copied by hand
      const range = document.createRange();
      range.selectNodeContents($('#savePath'));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      said('Selected');
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText($('#savePath').textContent).then(() => said('Copied'), selectIt);
    else selectIt();
  });
}

// ---------- A game's own text: font, size and style ----------
// These follow the game chosen under Profiles. The font list comes from js/prefs.js,
// which also applies the settings on the game pages. (Left alone when this script is
// paired with a previous index.html, store.js or prefs.js during an update.)
const FONTS = (window.EDFPrefs && window.EDFPrefs.FONTS) || [];
const OWN_FONT = { edf41: "'Saira Condensed'", edf5: "'Rajdhani'", edf6: "'Share Tech Mono'" }; // each theme's own font, for the sample
const SAMPLE = { edf41: 'AF14-ST · Fusion Blaster · Lv 2', edf5: 'PA-11 SLS · Slugger NN1 · Lv 5', edf6: 'MR98 Fang · Blazer · Lv 12' };
const typeFont = $('#typeFont');
const typeRange = $('#typeRange');
const hasGameText = !!(FONTS.length && typeFont && typeRange && $('#typeSame') && $('#typeValue') && $('#segTypeStyle') && $('#typePreview') && store.loadPrefs().type);
function globalScale() { // the size "Same" stands for: the Text size setting, or the device's size when that is Auto
  const t = store.loadPrefs().text;
  return t === 'auto' ? (parseFloat(document.documentElement.style.getPropertyValue('--ts')) || 1) : parseFloat(t);
}
function showGameText() {
  if (!hasGameText) return;
  const t = store.loadPrefs().type[shownGame];
  const font = FONTS.filter((f) => f[0] === t.font)[0] || FONTS[0];
  const same = t.size === 'same';
  const scale = same ? globalScale() : parseFloat(t.size);
  const pct = Math.round(scale * 100);
  $('#lblGameText').textContent = store.GAME_NAMES[shownGame] + ' text';
  typeFont.value = font[0];
  $('#typeSame').setAttribute('aria-pressed', String(same));
  typeRange.classList.toggle('is-auto', same);
  if (Number(typeRange.value) !== pct) typeRange.value = String(pct);
  typeRange.setAttribute('aria-valuetext', pct + '%' + (same ? ', same as Text size' : ''));
  $('#typeValue').textContent = pct + '%';
  document.querySelectorAll('#segTypeStyle button[data-style]').forEach((b) => b.setAttribute('aria-pressed', String(t[b.dataset.style] === true)));
  const sample = $('#typePreview');
  sample.textContent = SAMPLE[shownGame];
  sample.style.fontFamily = (font[2] || OWN_FONT[shownGame]) + ', system-ui, sans-serif';
  sample.style.fontSize = 'calc(17px * ' + scale + ')';
  sample.style.fontStyle = t.italic ? 'italic' : 'normal';
  sample.style.textTransform = t.caps ? 'uppercase' : 'none';
  sample.style.webkitTextStroke = t.bold ? '0.022em currentColor' : '0';
}
function changeGameText(key, value) {
  const p = store.loadPrefs();
  p.type[shownGame][key] = value;
  if (!store.savePrefs(p)) notice('Settings cannot be saved on this device. Storage is full or blocked.');
  showGameText();
  // Keep every file of a newly picked font, so the game page has it even if it is next opened offline.
  const worker = key === 'font' && navigator.serviceWorker ? navigator.serviceWorker.controller : null;
  if (worker && window.EDFPrefs.fontFiles) worker.postMessage({ type: 'keep-fonts', fonts: window.EDFPrefs.fontFiles(shownGame) });
}
if (!hasGameText) {
  if ($('#gameText')) $('#gameText').hidden = true;
} else {
  FONTS.forEach((f, i) => { // the first option is already in the page
    const o = i === 0 ? typeFont.options[0] : document.createElement('option');
    o.value = f[0];
    o.textContent = f[1];
    if (i > 0) typeFont.appendChild(o);
  });
  typeFont.addEventListener('change', () => changeGameText('font', typeFont.value));
  $('#typeSame').addEventListener('click', () => changeGameText('size', 'same'));
  typeRange.addEventListener('input', () => changeGameText('size', String(Number(typeRange.value) / 100)));
  $('#segTypeStyle').addEventListener('click', (e) => {
    const b = e.target.closest ? e.target.closest('button[data-style]') : null;
    if (b) changeGameText(b.dataset.style, b.getAttribute('aria-pressed') !== 'true');
  });
}

// ---------- Display settings ----------
// Text size: the Auto button follows the device; moving the slider picks a fixed size.
// While Auto is on, the slider and the number show the size in use.
// (During an update a phone can briefly pair this script with its saved copy of
// the previous index.html, which has no slider. Then the text-size control is
// left alone, and the next visit loads matching files.)
const textRange = $('#textRange');
const textAuto = $('#textAuto');
const textValue = $('#textValue');
const hasTextSlider = !!(textRange && textAuto && textValue);
function showPrefs() {
  const p = store.loadPrefs();
  if (hasTextSlider) {
    const auto = p.text === 'auto';
    const inUse = parseFloat(document.documentElement.style.getPropertyValue('--ts')) || 1; // set by js/prefs.js
    const pct = Math.round((auto ? inUse : parseFloat(p.text)) * 100);
    textAuto.setAttribute('aria-pressed', String(auto));
    textRange.classList.toggle('is-auto', auto);
    if (Number(textRange.value) !== pct) textRange.value = String(pct); // the slider snaps it to its own steps
    textRange.setAttribute('aria-valuetext', pct + '%' + (auto ? ', automatic' : ''));
    textValue.textContent = pct + '%';
  }
  document.querySelectorAll('#segFx button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.fx === p.fx)));
  document.querySelectorAll('#segLayout button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.layout === (p.layout || 'fit'))));
  showGameText(); // "Same" follows the Text size above
}
function changePref(key, value) {
  const p = store.loadPrefs();
  p[key] = value;
  if (!store.savePrefs(p)) notice('Settings cannot be saved on this device. Storage is full or blocked.');
  if (window.EDFPrefs) window.EDFPrefs.apply();
  showPrefs();
}
if (hasTextSlider) {
  textAuto.addEventListener('click', () => changePref('text', 'auto'));
  textRange.addEventListener('input', () => changePref('text', String(Number(textRange.value) / 100)));
}
if ($('#segLayout')) { // not in the previous version's index.html
  $('#segLayout').addEventListener('click', (e) => {
    const b = e.target.closest ? e.target.closest('button[data-layout]') : null;
    if (b) changePref('layout', b.dataset.layout);
  });
}
$('#segFx').addEventListener('click', (e) => {
  const b = e.target.closest ? e.target.closest('button[data-fx]') : null;
  if (b) changePref('fx', b.dataset.fx);
});

$('#version').textContent = 'v' + (self.APP_VERSION || '?');

// ---------- Updates ----------
const seen = store.checkVersion();
window.addEventListener('edf-update', () => {
  notice('A new version is installed.', [{ label: 'Reload', primary: true, run: () => window.location.reload() }]);
});

// Progress may change in another tab or after returning from a game page.
window.addEventListener('pageshow', () => { showProfiles(); showProgress(); showPrefs(); showBackup(); });
window.addEventListener('storage', () => { if (window.EDFPrefs) window.EDFPrefs.apply(); showProfiles(); showProgress(); showPrefs(); showBackup(); });
showProfiles();
showProgress();
showPrefs();
showBackup();
// (an older store.js may still be in use right after an update; it has no newsDue)
const news = store.newsDue ? store.newsDue(seen) : seen.updated;
if (news) {
  notice(['Updated to v' + seen.to].concat(self.APP_NEWS || []).join('. ') + '.');
  // The count of fully upgraded weapons was made with the star maximums of the version before; make it again.
  ['edf5', 'edf6'].forEach((g) => (store.SLOTS || []).forEach((slot) => { if (store.loadSummary(g, slot).maxed > 0) recountMaxed(g, slot); }));
}
offerLegacy(); // replaces the update note when there is an old checklist to import
