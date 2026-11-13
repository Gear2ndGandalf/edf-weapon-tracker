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
  if (!window.confirm('Importing replaces your saved progress for each game and profile in the file. Continue?')) return;
  try {
    notice(await store.importFile(file));
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
if (seen.updated) notice('Updated to v' + seen.to + '. New: ' + (self.APP_NEWS || []).join(', ') + '.');
offerLegacy(); // replaces the update note when there is an old checklist to import
