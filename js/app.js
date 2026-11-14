// ============================================================================
// app.js – one script drives all three game pages (EDF 4.1, 5 and 6).
// The page says which game it is with <body data-game="edf5">, and the theme
// file decides how it looks. Data comes from data/<game>.json:
//   { game, key, hasStars, stats: [statName...],
//     classes: [{ name, short, cats: [{ name, items: [[id, name, level, source, upgrades?, lines?]] }] }] }
//   source: 0 base, 1 starter, 2 DLC, 3 Mission Pack 1, 4 Mission Pack 2
//   upgrades: [[statIndex, maxStars, steps?], ...]   (EDF 5 and 6 only; steps only when fewer than 5)
//   lines: [[statIndex, [upgrade, ...]], ...]   the lines of the game's equipment screen that carry a star
//   difficulties: [name...], drops: [{ name, pack, missions, diffs: [[lowLevels], [highLevels]] }]
//
// Flow: a click finds the nearest [data-act] element -> act() changes the
// state -> render() redraws -> saveSoon() writes to localStorage.
// Version: js/version.js. Display settings: js/prefs.js (set on the HQ page).
// ============================================================================
import * as store from './store.js';

const GAME = document.body.dataset.game;
// This game's profile in use (one of its eight save slots, chosen on HQ). Fixed for
// the life of this page; a switch reloads it. (store.js from v1.4 has no per-game
// profiles; a phone can briefly pair it with this script during an update.)
const currentSlot = () => (store.activeSlot ? store.activeSlot(GAME) : store.activeProfile());
const SLOT = currentSlot();
const $ = (sel) => document.querySelector(sel);
const BADGES = { 2: 'DLC', 3: 'MP1', 4: 'MP2' };
const SEARCH_LIMIT = 150;
const STAR = '<i class="ico ico--star" aria-hidden="true"></i>';
const CHECK = '<i class="ico ico--check" aria-hidden="true"></i>';
const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESCAPES[c]);
const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, Number.isInteger(n) ? n : lo));

let D = null;              // game data
const all = [];            // every weapon, flat, in menu order
const byId = new Map();
let upgradable = 0;        // how many items have at least one upgrade (what "fully upgraded" counts out of)
const prog = store.loadProgress(GAME, SLOT);
const savedUI = store.loadUI(GAME);
const ui = Object.assign({ cls: 0, cat: 0, filter: 0, detailOpen: true, view: 'stars' }, savedUI);
let query = '';
let pickerOpen = false;
let cursorId = null;
let toastAction = null;     // { label, run } for the button on the toast
let toastTimer = 0;
let saveTimer = 0;
let saveWarned = false;
const scrollMem = new Map(); // list scroll position per category, e.g. "0:3" -> 240

// ---------- Progress helpers ----------
const isOwned = (w) => prog.owned.has(w.id);
function starsOf(w) {
  const saved = prog.stars[w.id] || [];
  return w.up.map((u, i) => clamp(saved[i] | 0, 0, u.max));
}
// The saved list as it is, at full length, with one stat set. The other stats are written back
// untouched, so a maximum that is wrong for a while (old data during an update) cannot lower them,
// and stars saved for upgrades this copy of the data does not list yet are kept.
function withStar(w, i, n) {
  const saved = prog.stars[w.id] || [];
  const list = Array.from({ length: Math.max(saved.length, w.up.length) }, (_, k) => Math.max(0, saved[k] | 0));
  list[i] = n;
  return list;
}
const capOf = (w) => w.up.reduce((a, u) => a + u.max, 0);
// The stars an upgrade can show, lowest first. With fewer than 5 steps the game prints a level as
// level * 5 // steps, so only some stars are possible (3 steps: 0, 1, 3, 5); null means every star from 0 up.
function reachable(u) {
  if (!u.steps) return null;
  const out = [];
  for (let level = 0; level <= u.steps; level++) out.push(Math.floor(level * 5 / u.steps));
  return out;
}
// The next star an upgrade can show above (up) or below (down) `n`. A value it cannot show (one entered by
// hand before v1.10.0) is left as it is until it is changed; then it moves to the next one it can show.
function stepStar(u, n, up) {
  const can = reachable(u);
  if (!can) return clamp(n + (up ? 1 : -1), 0, u.max);
  const next = up ? can.filter((v) => v > n)[0] : can.filter((v) => v < n).pop();
  return next === undefined ? clamp(n, 0, u.max) : next;
}
// Tapping star k: the lowest star the upgrade can show from k up. Tapping it again (it is already
// what is shown) steps down to the one below, as tapping the last lit star always did.
function tapStar(u, n, k) {
  const can = reachable(u);
  const want = can ? can.filter((v) => v >= k)[0] : k;
  if (want === undefined) return clamp(n, 0, u.max);
  return want === n ? stepStar(u, n, false) : clamp(want, 0, u.max);
}
// Text as it is compared in a search: lower case, full-width letters as plain ones, runs of spaces as one.
const plain = (s) => { const t = String(s); return (t.normalize ? t.normalize('NFKC') : t).replace(/\s+/g, ' ').trim().toLowerCase(); };
// The star the game prints in front of a line of its equipment screen: the average of the line's upgrades,
// cut to tenths. Half a star is printed as "+", and the star is filled only when the line is finished.
function gameStar(w, line, stars) {
  const n = line.ups.length;
  const now = Math.floor(10 * line.ups.reduce((a, i) => a + stars[i], 0) / n);
  const top = Math.floor(10 * line.ups.reduce((a, i) => a + w.up[i].max, 0) / n);
  return (now === top ? '★' : '☆') + Math.floor(now / 10) + (now % 10 ? '+' : '');
}
// One element per star. Tapping star k sets the stat to k; tapping the last lit star turns it off.
// An upgrade with fewer than 5 steps goes to the stars the game can show instead (see tapStar).
// (The − and + buttons do the same job for keyboards and screen readers.)
function starHtml(statIndex, lit, max) {
  let html = '';
  for (let k = 1; k <= max; k++) {
    html += '<i' + (k > lit ? ' class="off"' : '') + ' data-act="star" data-i="' + statIndex + '" data-n="' + k + '"></i>';
  }
  return html;
}
const haveOf = (w) => starsOf(w).reduce((a, n) => a + n, 0);
// Stars only count while the weapon is owned. Unchecking a weapon keeps its stars
// in storage, so checking it again (or Undo) brings them back.
const isMaxed = (w) => D.hasStars && isOwned(w) && w.up.length > 0 && haveOf(w) === capOf(w);
const needsStars = (w) => isOwned(w) && w.up.length > 0 && haveOf(w) < capOf(w);

function setStars(w, arr) {
  if (arr.some((n) => n > 0)) {
    prog.stars[w.id] = arr;
    prog.owned.add(w.id); // a weapon with stars must be owned
  } else {
    delete prog.stars[w.id];
  }
}
function toggleOwned(id) {
  if (prog.owned.has(id)) prog.owned.delete(id); else prog.owned.add(id);
}
function snapshot() {
  return { owned: new Set(prog.owned), stars: JSON.parse(JSON.stringify(prog.stars)) };
}
// Forget saved ids that are not in this game's data (e.g. a hand-edited import).
function pruneUnknown() {
  Array.from(prog.owned).forEach((id) => { if (!byId.has(id)) prog.owned.delete(id); });
  Object.keys(prog.stars).forEach((id) => { if (!byId.has(id)) delete prog.stars[id]; });
}

// ---------- Where a weapon drops ----------
// Same rule as edf-calc's drop table: in each mode and difficulty a weapon of
// level L can drop from the first mission whose highest drop level reaches L
// to the last mission whose lowest drop level is still at or below L.
// Mission-pack weapons only drop in their own pack.
function dropInfo(w) {
  if (w.src === 1) return { note: 'You start with this weapon.' };
  if (w.src === 2) return { note: 'DLC or bonus item. It does not drop in missions.' };
  const pack = w.src === 3 ? 1 : w.src === 4 ? 2 : 0;
  const modes = [];
  (D.drops || []).forEach((m) => {
    if (pack && m.pack !== pack) return;
    const diffs = [];
    m.diffs.forEach((d, di) => {
      const low = d[0], high = d[1];
      let from = -1, to = -1;
      for (let k = 0; k < high.length; k++) { if (high[k] >= w.level) { from = k; break; } }
      for (let k = low.length - 1; k >= 0; k--) { if (low[k] <= w.level) { to = k; break; } }
      if (from > -1 && to > -1) diffs.push({ name: D.difficulties[di], from: from + 1, to: to < from ? m.missions : to + 1 });
    });
    if (diffs.length) modes.push({ name: m.name, diffs });
  });
  return { modes };
}
function dropsHtml(w) {
  const info = dropInfo(w);
  if (info.note) return '<div class="empty">' + info.note + '</div>';
  if (!info.modes.length) return '<div class="empty">No drop data for this weapon.</div>';
  return '<div class="drops">' + info.modes.map((m) =>
    '<div class="drops__mode"><span class="drops__name">' + esc(m.name) + '</span><span class="drops__list">' +
    m.diffs.map((d) => '<span class="drop"><b>' + esc(d.name) + '</b> ' + (d.from === d.to ? d.from : d.from + '–' + d.to) + '</span>').join('') +
    '</span></div>').join('') +
    '<p class="drops__note">Mission numbers where it can drop, by difficulty.</p></div>';
}

// ---------- Saving ----------
function summary() {
  let maxed = 0;
  if (D.hasStars) for (const w of all) if (isMaxed(w)) maxed++;
  return { owned: prog.owned.size, maxed, total: all.length };
}
function saveNow() {
  clearTimeout(saveTimer);
  saveTimer = 0;
  if (!D) return;
  const ok = store.saveProgress(GAME, prog, summary(), SLOT);
  if (!ok && !saveWarned) {
    saveWarned = true;
    showToast('Progress cannot be saved on this device. Storage is full or blocked.');
  }
  rememberScroll();
  store.saveUI(GAME, { cls: ui.cls, cat: ui.cat, filter: ui.filter, detailOpen: ui.detailOpen, view: ui.view, scroll: scrollMem.get(catKey()) || 0 });
}
// ---------- Scroll memory: each category reopens where you left it ----------
const catKey = () => ui.cls + ':' + ui.cat;
const showingCategory = () => !query && !pickerOpen;
function rememberScroll() {
  if (D && showingCategory()) scrollMem.set(catKey(), $('#list').scrollTop);
}
function restoreScroll() {
  $('#list').scrollTop = showingCategory() ? (scrollMem.get(catKey()) || 0) : 0;
}

function saveSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 250);
}
// Progress changed outside this page (another tab, an import on HQ, or this
// page coming back from the browser's back/forward cache): reload it so a
// later save cannot overwrite the newer data.
function reloadFromStorage() {
  if (!D) return;
  clearTimeout(saveTimer);
  saveTimer = 0;
  const fresh = store.loadProgress(GAME, SLOT);
  prog.owned = fresh.owned;
  prog.stars = fresh.stars;
  pruneUnknown();
  hideToast();
  render();
}
window.addEventListener('pagehide', saveNow);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') saveNow(); });
// The profile was switched on HQ or in another tab: start over on the new profile.
const profileChanged = () => currentSlot() !== SLOT;
window.addEventListener('pageshow', (e) => {
  if (!e.persisted) return;
  if (profileChanged()) window.location.reload(); else reloadFromStorage();
});
window.addEventListener('storage', (e) => {
  // Newer progress for this page's profile comes first, so nothing below can write an older copy over it.
  const mine = e.key === null || e.key === store.progressKey(GAME, SLOT);
  if (mine) reloadFromStorage();
  if (profileChanged()) {
    if (saveTimer) saveNow(); // a change made here in the last moment, not yet written
    window.location.reload();
    return;
  }
  if (!mine && D) renderTitle(); // for example the profile was renamed on HQ
});

// ---------- Which weapons are on screen ----------
function filterOk(w) {
  if (ui.filter === 1) return !isOwned(w);
  if (ui.filter === 2) return D.hasStars ? needsStars(w) : isOwned(w);
  return true;
}
function visibleRows() {
  if (query) {
    const q = plain(query);
    return all.filter((w) => w.lname.indexOf(q) !== -1 && filterOk(w));
  }
  return D.classes[ui.cls].cats[ui.cat].items.filter(filterOk);
}

// ---------- Rendering ----------
let shownPlace = ''; // the class, category, filter and search the list was last drawn for
function render() {
  const focus = rememberFocus();
  const rows = visibleRows();
  const inRows = rows.some((w) => w.id === cursorId);
  // The panel follows the list when the list changes (another class, category, filter or search). It does
  // not jump to another weapon when an edit takes the current one out of the list (marked owned under
  // Missing, fully upgraded under To upgrade): the next tap would change the wrong weapon.
  const place = ui.cls + ':' + ui.cat + ':' + ui.filter + ':' + query;
  const moved = place !== shownPlace;
  shownPlace = place;
  if (!byId.has(cursorId) || (!query && rows.length && !inRows && moved)) {
    const first = rows.length ? rows[0] : D.classes[ui.cls].cats[ui.cat].items[0];
    cursorId = first ? first.id : null;
  }
  renderTitle();
  renderTabs();
  renderCategory();
  renderFilters();
  renderList(rows);
  renderDetail();
  restoreFocus(focus);
  checkFit();
}

// ---------- Fit check ----------
// On phones the page normally fits one screen. When the header of the details panel no longer
// fits (a very narrow screen, or a wide font or capitals picked on HQ), the page switches to the
// scrolling layout (class "no-fit", same rules as large text) instead of clipping it. So does a
// screen too short to show the panel's list. Checked
// after every redraw and once the fonts have loaded. It is only reconsidered when the screen
// width changes: mobile browsers change the height while a page scrolls.
let fitWidth = window.innerWidth;
function checkFit() {
  const root = document.documentElement;
  if (root.classList.contains('no-fit') || window.innerWidth >= 860) return;
  const detail = $('#detail');
  const head = detail.querySelector('.detail__head');
  if (head && detail.clientHeight + 1 < head.offsetHeight) root.classList.add('no-fit');
  // The same when the open panel has room for only about one row of a longer list (short phone
  // screens with the browser's bars showing): a list that can barely be seen is no use.
  const stats = detail.querySelector('.stats');
  if (stats && stats.clientHeight > 0 && stats.clientHeight < 92 && stats.scrollHeight > stats.clientHeight + 1) root.classList.add('no-fit');
}
window.addEventListener('resize', () => {
  if (window.innerWidth === fitWidth) return;
  fitWidth = window.innerWidth;
  document.documentElement.classList.remove('no-fit');
  if (D) checkFit();
});

function renderTitle() {
  const s = summary();
  let html = '<span class="pill" title="Owned">' + CHECK + '<span class="sr-only">Owned </span>' + s.owned + '/' + s.total + '</span>';
  // Out of the items that have upgrades: about 120 per game have none, so the owned total can never be reached.
  if (D.hasStars) {
    html += '<span class="pill" title="Fully upgraded, out of the ' + upgradable + ' items that have upgrades">' + STAR +
      '<span class="sr-only">Fully upgraded ' + s.maxed + ' of ' + upgradable + '</span><span aria-hidden="true">' + s.maxed + '/' + upgradable + '</span></span>';
  }
  // Shown only once this game uses more than one profile, so it is clear whose progress this is.
  if (store.slotsInUse && store.slotsInUse(GAME)) html = '<span class="pill pill--profile" title="Profile (change it on HQ)">' + esc(store.slotNames(GAME)[SLOT]) + '</span>' + html;
  $('#pills').innerHTML = html;
}

function renderTabs() {
  $('#tabs').innerHTML = D.classes.map((c, i) => {
    let own = 0, total = 0;
    for (const k of c.cats) for (const w of k.items) { total++; if (isOwned(w)) own++; }
    const pct = total ? Math.round((own / total) * 100) : 0;
    return '<button type="button" class="tab" data-act="tab" data-i="' + i + '" aria-pressed="' + (i === ui.cls && !query) + '"' +
      ' aria-label="' + esc(c.name) + ', ' + own + ' of ' + total + ' owned">' +
      '<span class="tab__name">' + esc(c.short) + '</span>' +
      '<span class="tab__count">' + own + '/' + total + '</span>' +
      '<span class="tab__bar"><span style="width:' + pct + '%"></span></span></button>';
  }).join('');
}

function renderCategory() {
  const k = D.classes[ui.cls].cats[ui.cat];
  const own = k.items.filter(isOwned).length;
  $('#catname').textContent = k.name;
  $('#catcount').textContent = own + '/' + k.items.length;
  $('#catbtn').setAttribute('aria-expanded', String(pickerOpen));
}

function renderFilters() {
  // [label, tooltip, screen-reader name (only where the label is an icon)]
  const chips = [['All', 'Show everything'], ['Missing', 'Weapons you do not have yet']];
  chips.push(D.hasStars
    ? ['To upgrade', 'Owned weapons with stars left to earn']
    : ['Owned', 'Weapons you own']);
  $('#filters').innerHTML = chips.map((c, i) =>
    '<button type="button" class="chip" data-act="filter" data-i="' + i + '" title="' + c[1] + '"' +
    (c[2] ? ' aria-label="' + c[2] + '"' : '') + ' aria-pressed="' + (i === ui.filter) + '">' + c[0] + '</button>'
  ).join('');
  $('#qclear').hidden = !query;
}

function emptyMessage() {
  if (query) return 'No weapons match “' + esc(query) + '”. Check the spelling' + (ui.filter ? ' or set the filter to All.' : '.');
  if (ui.filter === 1) return 'You own everything in this category.';
  if (ui.filter === 2 && D.hasStars) return 'No owned weapons here have stars left to earn.';
  if (ui.filter === 2) return 'You have not marked any weapons in this category yet.';
  return 'This category has no weapons.';
}

function renderList(rows) {
  const head = $('#listhead');
  const list = $('#list');
  if (pickerOpen) {
    head.hidden = true;
    list.innerHTML = '<div class="picker">' + D.classes[ui.cls].cats.map((k, i) => {
      const own = k.items.filter(isOwned).length;
      return '<button type="button" class="picker__item" data-act="cat" data-i="' + i + '"' + (i === ui.cat ? ' aria-current="true"' : '') + '>' +
        '<span>' + esc(k.name) + '</span><span class="picker__count">' + own + '/' + k.items.length + '</span></button>';
    }).join('') + '</div>';
    return;
  }
  head.hidden = false;
  const shown = rows.slice(0, SEARCH_LIMIT);
  const allOwned = shown.length > 0 && shown.every(isOwned);
  const allLabel = allOwned ? 'Unmark all shown weapons' : 'Mark all shown weapons owned';
  head.innerHTML =
    '<button type="button" class="allbox" data-act="all" aria-pressed="' + allOwned + '" aria-label="' + allLabel + '" title="' + allLabel + '"' + (shown.length ? '' : ' disabled') + '></button>' +
    '<div class="listhead__name">' + (query ? rows.length + (rows.length === 1 ? ' match' : ' matches') : 'Name') + '</div>' +
    '<div class="listhead__lv">Lv</div>' +
    (D.hasStars ? '<div class="listhead__star">' + STAR + '<span class="sr-only">Stars</span></div>' : '');

  if (!rows.length) {
    list.innerHTML = '<div class="empty">' + emptyMessage() + '</div>';
    return;
  }
  let html = '<div class="rows" role="list">';
  for (const w of shown) {
    const owned = isOwned(w);
    const cur = w.id === cursorId;
    const maxed = isMaxed(w);
    const badge = BADGES[w.src] ? '<span class="badge">' + BADGES[w.src] + '</span>' : '';
    const sub = query ? '<span class="row__sub">' + esc(D.classes[w.ci].short + ' · ' + D.classes[w.ci].cats[w.ki].name) + '</span>' : '';
    let meter = '';
    if (D.hasStars) {
      if (w.up.length) {
        const h = haveOf(w), c = capOf(w);
        meter = '<span class="meter"><span class="meter__text">' + h + '/' + c + '</span>' +
          '<span class="meter__track"><span class="' + (maxed ? 'is-max' : '') + '" style="width:' + Math.round((h / c) * 100) + '%"></span></span></span>';
      } else {
        meter = '<span class="meter"><span class="meter__text">—</span></span>';
      }
    }
    html += '<div class="row cols' + (owned ? ' is-owned' : '') + (cur ? ' is-cur' : '') + '" role="listitem">' +
      '<span class="row__edge" aria-hidden="true"></span>' +
      '<button type="button" class="box" data-act="own" data-id="' + esc(w.id) + '" aria-pressed="' + owned + '" aria-label="Owned: ' + esc(w.name) + '"></button>' +
      '<button type="button" class="row__name" data-act="sel" data-id="' + esc(w.id) + '"' + (cur ? ' aria-current="true"' : '') + '>' +
        '<span class="row__title">' + (maxed ? STAR + '<span class="sr-only">Fully upgraded: </span>' : '') +
        '<span class="row__label">' + esc(w.name) + '</span>' + badge + '</span>' + sub + '</button>' +
      '<span class="row__lv">' + w.level + '</span>' + meter + '</div>';
  }
  html += '</div>';
  if (rows.length > shown.length) html += '<div class="more">Showing the first ' + SEARCH_LIMIT + ' of ' + rows.length + '. Type more to narrow it down.</div>';
  list.innerHTML = html;
}

function renderDetail() {
  const box = $('#detail');
  const w = byId.get(cursorId);
  if (!w) { box.innerHTML = ''; box.dataset.shown = ''; return; }
  // Every change redraws the panel. While it still shows the same weapon and view, its list stays where it
  // was scrolled to, so adding a star far down does not jump back to the top.
  const shown = w.id + ' ' + (D.hasStars && ui.view === 'drops' ? 'drops' : 'stars');
  const before = box.querySelector('.stats');
  const keepTop = before && box.dataset.shown === shown ? before.scrollTop : 0;
  const where = D.classes[w.ci].short + ' · ' + D.classes[w.ci].cats[w.ki].name;
  const has = D.hasStars && w.up.length > 0;
  const showStars = D.hasStars && ui.view !== 'drops';
  const collapse = '<button type="button" class="btn btn--ghost collapse" data-act="collapse" aria-expanded="' + ui.detailOpen + '" aria-label="Show or hide details">' +
    '<span class="caret' + (ui.detailOpen ? '' : ' caret--up') + '" aria-hidden="true"></span></button>';

  let html = '<div class="detail__head"><div class="detail__info">' +
    '<span class="detail__name">' + esc(w.name) + '</span>' +
    '<span class="detail__meta">Lv ' + w.level + (has ? ' · ' + haveOf(w) + '/' + capOf(w) + ' stars' : '') + ' · ' + esc(where) + '</span></div>';
  if (!D.hasStars) {
    const owned = isOwned(w);
    html += '<button type="button" class="btn btn--own" data-act="ownsel" aria-pressed="' + owned + '">' + (owned ? CHECK + 'Owned' : 'Mark owned') + '</button>';
  } else if (has && showStars) {
    html += '<button type="button" class="btn btn--accent" data-act="max" aria-label="Max all stars">' + STAR + 'Max</button>' +
      '<button type="button" class="btn btn--ghost" data-act="clear" aria-label="Clear all stars">Clear</button>';
  }
  html += collapse + '</div><div class="stats' + (ui.detailOpen ? '' : ' is-closed') + '">';

  if (D.hasStars) { // EDF 5 and 6: switch between star upgrades and drop locations
    html += '<div class="views" role="group" aria-label="Details shown">' +
      '<button type="button" class="chip" data-act="view" data-i="0" aria-pressed="' + showStars + '">Upgrades</button>' +
      '<button type="button" class="chip" data-act="view" data-i="1" aria-pressed="' + !showStars + '">Drops</button></div>';
  }
  if (showStars) {
    const stars = starsOf(w);
    if (!has) html += '<div class="empty">This item has no star upgrades.</div>';
    // One row per upgrade, where the game first shows it. "i" is the upgrade's place in the saved list.
    const row = (i, label, part) => {
      const u = w.up[i];
      const n = stars[i];
      const said = esc(u.stat.replace(': ', ', '));
      // Under the label, the value as the game's equipment screen writes it: ☆n, and ★n once it is at the top.
      // (Screen readers already hear "n of m stars" from the stars.)
      return '<div class="stat' + (part ? ' stat--part' : '') + '"><div class="stat__main"><span class="stat__head"><span class="stat__label">' + esc(label) + '</span>' +
        '<span class="stat__game" aria-hidden="true">' + (n === u.max ? '★' : '☆') + n + '</span></span>' +
        '<span class="stat__stars" role="img" aria-label="' + said + ': ' + n + ' of ' + u.max + ' stars">' +
          starHtml(i, n, u.max) + '</span></div>' +
        '<button type="button" class="btn btn--ghost stat__btn" data-act="dec" data-i="' + i + '" aria-label="Remove a star: ' + said + '"' + (n === 0 ? ' disabled' : '') + '>−</button>' +
        '<button type="button" class="btn btn--ghost stat__btn" data-act="inc" data-i="' + i + '" aria-label="Add a star: ' + said + '"' + (n === u.max ? ' disabled' : '') + '>+</button></div>';
    };
    const note = (label, text, part, tip) => '<div class="statline' + (part ? ' statline--part' : '') + '"><span class="stat__label">' + esc(label) + '</span>' +
      '<span class="statline__note"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + esc(text) + '</span></div>';
    // What a value is called on a line it shares with another: "Damage" and "Count" on a Damage line.
    const partName = (line, i) => {
      const k = line.ups.indexOf(i);
      if (line.parts && line.parts[k]) return line.parts[k];
      const s = w.up[i].stat;
      return s.indexOf(line.label + ': ') === 0 ? s.slice(line.label.length + 2) : s;
    };
    const IN_GAME = 'The star the game prints for this line: the average of its values. + is half a star.';
    const drawn = new Set(); // upgrades that have their row already
    w.lines.forEach((line) => {
      const fresh = line.ups.filter((i) => !drawn.has(i));
      if (line.ups.length === 1 && fresh.length) {
        html += row(line.ups[0], line.label, false);
      } else if (line.ups.length === 1) { // the game shows this value on a second line (Shot Speed and Range)
        html += note(line.label, gameStar(w, line, stars) + ' · same as ' + w.up[line.ups[0]].stat, false);
      } else { // several values on one line: the game shows one star for them, their average
        html += note(line.label, 'In game: ' + gameStar(w, line, stars) + (fresh.length ? '' : ' · set above'), false, IN_GAME);
        line.ups.forEach((i) => {
          if (!drawn.has(i)) html += row(i, partName(line, i), true);
          else if (fresh.length) html += note(partName(line, i), '☆★'[+(stars[i] === w.up[i].max)] + stars[i] + ' · same as ' + w.up[i].stat, true);
        });
      }
      fresh.forEach((i) => drawn.add(i));
    });
  } else {
    html += dropsHtml(w);
  }
  box.innerHTML = html + '</div>';
  box.dataset.shown = shown;
  if (keepTop) box.querySelector('.stats').scrollTop = keepTop;
}

// Keep keyboard focus on the same control after a re-render.
function rememberFocus() {
  const a = document.activeElement;
  if (!a || !a.dataset || !a.dataset.act) return null;
  const same = Array.from(document.querySelectorAll('[data-act="' + a.dataset.act + '"]'));
  return { act: a.dataset.act, id: a.dataset.id, i: a.dataset.i, at: same.indexOf(a) };
}
function restoreFocus(f) {
  if (!f) return;
  const same = Array.from(document.querySelectorAll('[data-act="' + f.act + '"]'));
  let match = same.filter((el) => (f.id === undefined || el.dataset.id === f.id) && (f.i === undefined || el.dataset.i === f.i))[0];
  // The row left the list (for example it was marked owned under the Missing filter): stay at the same position.
  if (!match && f.id !== undefined && same.length) match = same[Math.min(f.at, same.length - 1)];
  // "+" at the top or "−" at zero switches off: stay on its neighbour instead of losing the place.
  if (match && match.disabled && (f.act === 'inc' || f.act === 'dec')) match = document.querySelector('[data-act="' + (f.act === 'inc' ? 'dec' : 'inc') + '"][data-i="' + f.i + '"]');
  if (match && !match.disabled) match.focus({ preventScroll: true });
}

// ---------- Toast with one optional action button ----------
function showToast(msg, action, keep) {
  toastAction = action || null;
  $('#toastmsg').textContent = msg;
  const btn = $('#toastundo');
  btn.hidden = !action;
  if (action) btn.textContent = action.label;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  if (!keep) toastTimer = setTimeout(hideToast, 6000);
}
function hideToast() {
  clearTimeout(toastTimer);
  toastAction = null;
  $('#toast').hidden = true;
}
// An Undo action that puts progress back to how it was in the snapshot.
function undoTo(snap) {
  return {
    label: 'Undo',
    run: () => {
      prog.owned = snap.owned;
      prog.stars = snap.stars;
      render();
      saveSoon();
    },
  };
}

// ---------- Actions ----------
const CHANGES = ['own', 'all', 'ownsel', 'inc', 'dec', 'star', 'max', 'clear']; // actions that change progress
function leaveSearch() {
  query = '';
  $('#q').value = '';
}
function act(name, el) {
  const moves = name === 'tab' || name === 'prev' || name === 'next' || name === 'cat' || name === 'picker' || name === 'clearq';
  if (moves) rememberScroll();
  const id = el.dataset.id;
  const i = el.dataset.i !== undefined ? Number(el.dataset.i) : -1;
  const w = byId.get(cursorId);
  // An Undo that is still on offer puts everything back to how it was before its change. Once
  // something else is changed it is withdrawn, or it would take that later change back too.
  if (toastAction && toastAction.label === 'Undo' && CHANGES.indexOf(name) !== -1) hideToast();
  switch (name) {
    case 'tab':
      if (i === ui.cls && !query && !pickerOpen) return; // already here
      if (i !== ui.cls) ui.cat = 0;
      ui.cls = i; pickerOpen = false; leaveSearch();
      break;
    case 'prev':
    case 'next': {
      const n = D.classes[ui.cls].cats.length;
      ui.cat = (ui.cat + (name === 'next' ? 1 : n - 1)) % n;
      pickerOpen = false; leaveSearch();
      break;
    }
    case 'picker': pickerOpen = !pickerOpen; break;
    case 'cat': ui.cat = i; pickerOpen = false; leaveSearch(); break;
    case 'filter': ui.filter = i; pickerOpen = false; break;
    case 'clearq': leaveSearch(); $('#q').focus(); break;
    case 'own':
    case 'sel': {
      const t = byId.get(id);
      if (!t) return;
      if (name === 'own') toggleOwned(id);
      else if (D.hasStars) ui.detailOpen = true;
      cursorId = id;
      if (query) { ui.cls = t.ci; ui.cat = t.ki; } // clearing the search lands on this weapon's category
      break;
    }
    case 'all': {
      const shown = visibleRows().slice(0, SEARCH_LIMIT);
      if (!shown.length) return;
      const snap = snapshot();
      const mark = !shown.every(isOwned);
      shown.forEach((t) => { if (mark) prog.owned.add(t.id); else prog.owned.delete(t.id); });
      showToast((mark ? 'Marked ' : 'Unmarked ') + shown.length + (shown.length === 1 ? ' weapon' : ' weapons'), undoTo(snap));
      break;
    }
    case 'ownsel':
      if (!w) return;
      toggleOwned(w.id);
      break;
    case 'inc':
    case 'dec': {
      if (!w || !w.up[i]) return;
      setStars(w, withStar(w, i, stepStar(w.up[i], starsOf(w)[i], name === 'inc')));
      break;
    }
    case 'star': {
      if (!w || !w.up[i]) return;
      setStars(w, withStar(w, i, tapStar(w.up[i], starsOf(w)[i], Number(el.dataset.n))));
      break;
    }
    case 'max':
      if (!w) return;
      setStars(w, w.up.map((u) => u.max).concat((prog.stars[w.id] || []).slice(w.up.length)));
      break;
    case 'clear': {
      if (!w || !haveOf(w)) return;
      const snap = snapshot();
      setStars(w, w.up.map(() => 0));
      showToast('Cleared stars on ' + w.name, undoTo(snap));
      break;
    }
    case 'collapse': ui.detailOpen = !ui.detailOpen; break;
    case 'view': ui.view = i === 1 ? 'drops' : 'stars'; ui.detailOpen = true; break;
    case 'legacy-import': importLegacyNow(); return;
    case 'legacy-dismiss': store.markLegacyDone(); $('#banner').hidden = true; return;
    default: return;
  }
  render();
  if (moves) restoreScroll();
  if (name === 'filter') $('#list').scrollTop = 0;
  saveSoon();
}

document.addEventListener('click', (e) => {
  const el = e.target.closest ? e.target.closest('[data-act]') : null;
  if (!el || el.disabled) return;
  if (el.dataset.act === 'reload') { window.location.reload(); return; }
  if (el.dataset.act === 'toast') { // the toast's button: Undo, Reload, ...
    const action = toastAction;
    hideToast();
    if (action) action.run();
    return;
  }
  if (D) act(el.dataset.act, el);
});
// Escape closes the category picker.
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !pickerOpen) return;
  pickerOpen = false;
  render();
  restoreScroll();
  $('#catbtn').focus();
});

// Up/Down arrows move through the list; Home/End jump to the ends.
function bindListKeys() {
  $('#list').addEventListener('keydown', (e) => {
    const step = { ArrowDown: 1, ArrowUp: -1, Home: -Infinity, End: Infinity }[e.key];
    const cur = e.target;
    if (step === undefined || !cur.dataset || !cur.dataset.act) return;
    const same = Array.from($('#list').querySelectorAll('[data-act="' + cur.dataset.act + '"]'));
    const at = same.indexOf(cur);
    if (at < 0) return;
    const to = same[Math.min(same.length - 1, Math.max(0, at + step))];
    if (to) { e.preventDefault(); to.focus(); }
  });
}

// ---------- Search ----------
function bindSearch() {
  const input = $('#q');
  input.addEventListener('input', () => {
    rememberScroll(); // only records while a category (not a search) is showing
    query = input.value.trim();
    pickerOpen = false;
    render();
    restoreScroll();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && input.value) { e.stopPropagation(); leaveSearch(); render(); restoreScroll(); }
    if (e.key === 'Enter') input.blur(); // close the phone keyboard
  });
}

// ---------- Old EDF 4.1 checklist on this device ----------
function checkLegacy() {
  if (GAME !== 'edf41' || store.legacyDismissed()) return;
  const found = store.findLegacyOnDevice();
  if (!found) return;
  const b = $('#banner');
  // Asked again after v1.4.1 fixed the import (see legacyAskedBefore in store.js). Importing only adds weapons.
  const again = store.legacyAskedBefore && store.legacyAskedBefore();
  b.innerHTML = '<p>Your old EDF 4.1 checklist on this device has ' + found.count + ' weapons checked. ' +
    (again ? 'Earlier versions missed most of them when importing. Import them all now?' : 'Import them here?') + '</p>' +
    '<button type="button" class="btn btn--accent" data-act="legacy-import">Import</button>' +
    '<button type="button" class="btn btn--ghost" data-act="legacy-dismiss">Not now</button>';
  b.hidden = false;
}
async function importLegacyNow() {
  const found = store.findLegacyOnDevice();
  if (!found) return;
  saveNow();
  try {
    const n = await store.importLegacy(found.data, SLOT);
    $('#banner').hidden = true;
    reloadFromStorage();
    saveNow();
    showToast('Imported ' + n + ' weapons from the old checklist');
  } catch (err) {
    showToast(err && err.message ? err.message : 'The old checklist could not be imported.');
  }
}

// ---------- Start ----------
async function boot() {
  try {
    const res = await fetch('data/' + GAME + '.json');
    if (!res.ok) throw new Error(String(res.status));
    D = await res.json();
  } catch (e) {
    $('#catname').textContent = 'Not loaded';
    $('#list').innerHTML = '<div class="empty"><p>Weapon data did not load. Check your connection, then try again.</p>' +
      '<button type="button" class="btn btn--ghost" data-act="reload">Reload</button></div>';
    return;
  }
  D.classes.forEach((c, ci) => c.cats.forEach((k, ki) => {
    k.items = k.items.map((t) => {
      const w = {
        id: t[0], name: t[1], lname: plain(t[1]), level: t[2], src: t[3],
        // steps: set only for an upgrade with fewer than 5 steps (data without it, an older copy, gives every star)
        up: (t[4] || []).map((u) => ({ stat: D.stats[u[0]], max: u[1], steps: Number.isInteger(u[2]) && u[2] >= 1 && u[2] < 5 && u[1] === 5 ? u[2] : 0 })), ci, ki,
      };
      if (w.up.length) upgradable++;
      // The lines of the game's equipment screen that carry a star, in the game's order: its label and the
      // upgrades it shows. Saved stars stay in the data's own order (the "up" list); this is only for display.
      // Data without lines (an older copy during an update): every upgrade is its own line.
      const listed = new Set();
      w.lines = (t[5] || []).map((l) => {
        const at = (l[1] || []).map((i, k) => [i, k]).filter((p) => w.up[p[0]]);
        // parts: what each value is called on this line (only for lines with several values)
        return { label: D.stats[l[0]], ups: at.map((p) => p[0]), parts: l[2] ? at.map((p) => D.stats[l[2][p[1]]]) : null };
      }).filter((l) => l.label && l.ups.length);
      w.lines.forEach((l) => l.ups.forEach((i) => listed.add(i)));
      w.up.forEach((u, i) => { if (!listed.has(i)) w.lines.push({ label: u.stat, ups: [i], parts: null }); });
      all.push(w);
      byId.set(w.id, w);
      return w;
    });
  }));
  pruneUnknown();

  ui.cls = clamp(ui.cls, 0, D.classes.length - 1);
  ui.cat = clamp(ui.cat, 0, D.classes[ui.cls].cats.length - 1);
  ui.filter = clamp(ui.filter, 0, 2);
  ui.detailOpen = ui.detailOpen !== false;
  ui.view = ui.view === 'drops' ? 'drops' : 'stars';
  // Short phone screens start with the upgrade panel closed so the list has room.
  if (savedUI.detailOpen === undefined && window.innerWidth < 860 && window.innerHeight < 760) ui.detailOpen = false;
  // EDF 4.1 has no upgrades, so on phones its drop details start closed to leave the list as tall as possible.
  if (savedUI.detailOpen === undefined && !D.hasStars && window.innerWidth < 860) ui.detailOpen = false;
  document.body.classList.toggle('has-stars', !!D.hasStars);
  bindSearch();
  bindListKeys();
  if (Number.isFinite(savedUI.scroll) && savedUI.scroll > 0) scrollMem.set(catKey(), savedUI.scroll);
  render();
  restoreScroll();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(checkFit); // a font that arrives late can be wider
  checkLegacy();
  const v = store.checkVersion();
  if (v.updated) showToast('Updated to v' + v.to);
}
// A new version was installed while this page was open: offer to load it.
window.addEventListener('edf-update', () => {
  showToast('A new version is installed.', { label: 'Reload', run: () => window.location.reload() }, true);
});
boot();
