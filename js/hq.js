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
  const hasProgress = store.GAMES.some((g) => store.loadSummary(g).owned > 0);
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
  notice('Your old EDF 4.1 checklist on this device has ' + found.count + ' weapons checked. Import them into EDF 4.1?', [
    {
      label: 'Import', primary: true,
      run: async () => {
        try {
          const n = await store.importLegacy(found.data);
          notice('Imported ' + n + ' EDF 4.1 weapons from the old checklist.');
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
  }
});

// ---------- Profiles ----------
function showProfiles() {
  const names = store.profileNames();
  const active = store.activeProfile();
  document.querySelectorAll('#segProfile button[data-profile]').forEach((b) => {
    b.textContent = names[b.dataset.profile];
    b.setAttribute('aria-pressed', String(b.dataset.profile === active));
  });
}
$('#segProfile').addEventListener('click', (e) => {
  const b = e.target.closest ? e.target.closest('button') : null;
  if (!b) return;
  if (b.dataset.profile) {
    store.setActiveProfile(b.dataset.profile);
  } else if (b.id === 'renameProfile') {
    const active = store.activeProfile();
    const name = window.prompt('Name for this profile (up to 16 characters)', store.profileNames()[active]);
    if (name === null) return; // cancelled
    store.renameProfile(active, name);
  }
  showProfiles();
  showProgress();
  showBackup();
});

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
window.addEventListener('storage', () => { showProfiles(); showProgress(); showPrefs(); showBackup(); if (window.EDFPrefs) window.EDFPrefs.apply(); });
showProfiles();
showProgress();
showPrefs();
showBackup();
if (seen.updated) notice('Updated to v' + seen.to + '. New: ' + (self.APP_NEWS || []).join(', ') + '.');
offerLegacy(); // replaces the update note when there is an old checklist to import
