// ============================================================================
// app.js – one script drives all three game pages (EDF 4.1, 5 and 6).
// The page says which game it is with <body data-game="edf5">, and the theme
// file decides how it looks. Data comes from data/<game>.json:
//   { game, key, hasStars, stats: [statName...],
//     classes: [{ name, short, cats: [{ name, items: [[id, name, level, source, upgrades?]] }] }] }
//   source: 0 base, 1 starter, 2 DLC, 3 Mission Pack 1, 4 Mission Pack 2
//   upgrades: [[statIndex, maxStars], ...]   (EDF 5 and 6 only)
//   difficulties: [name...], drops: [{ name, pack, missions, diffs: [[lowLevels], [highLevels]] }]
//
// Flow: a click finds the nearest [data-act] element -> act() changes the
// state -> render() redraws -> saveSoon() writes to localStorage.
// Version: js/version.js. Display settings: js/prefs.js (set on the HQ page).
// ============================================================================
import * as store from './store.js';

const GAME = document.body.dataset.game;
const PROFILE = store.activeProfile(); // fixed for the life of this page; a profile switch reloads it
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
const prog = store.loadProgress(GAME, PROFILE);
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
const capOf = (w) => w.up.reduce((a, u) => a + u.max, 0);
// One element per star. Tapping star k sets the stat to k; tapping the last lit star turns it off.
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
  const ok = store.saveProgress(GAME, prog, summary(), PROFILE);
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
  const fresh = store.loadProgress(GAME, PROFILE);
  prog.owned = fresh.owned;
  prog.stars = fresh.stars;
  pruneUnknown();
  hideToast();
  render();
}
window.addEventListener('pagehide', saveNow);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') saveNow(); });
// The profile was switched on HQ or in another tab: start over on the new profile.
const profileChanged = () => store.activeProfile() !== PROFILE;
window.addEventListener('pageshow', (e) => {
  if (!e.persisted) return;
  if (profileChanged()) window.location.reload(); else reloadFromStorage();
});
window.addEventListener('storage', (e) => {
  if (e.key === store.PROFILE_KEY && profileChanged()) { saveNow(); window.location.reload(); return; }
  if (e.key === null || e.key === store.progressKey(GAME, PROFILE)) reloadFromStorage();
});

// ---------- Which weapons are on screen ----------
function filterOk(w) {
  if (ui.filter === 1) return !isOwned(w);
  if (ui.filter === 2) return D.hasStars ? needsStars(w) : isOwned(w);
  return true;
}
function visibleRows() {
  if (query) {
    const q = query.toLowerCase();
    return all.filter((w) => w.lname.indexOf(q) !== -1 && filterOk(w));
  }
  return D.classes[ui.cls].cats[ui.cat].items.filter(filterOk);
}

// ---------- Rendering ----------
function render() {
  const focus = rememberFocus();
  const rows = visibleRows();
  const inRows = rows.some((w) => w.id === cursorId);
  if (!byId.has(cursorId) || (!query && rows.length && !inRows)) {
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
}

function renderTitle() {
  const s = summary();
  let html = '<span class="pill" title="Owned">' + CHECK + '<span class="sr-only">Owned </span>' + s.owned + '/' + s.total + '</span>';
  if (D.hasStars) html += '<span class="pill" title="Fully upgraded">' + STAR + '<span class="sr-only">Fully upgraded </span>' + s.maxed + '</span>';
  // Shown only once a second profile is in use, so it is clear whose progress this is.
  if (store.profilesInUse()) html = '<span class="pill pill--profile" title="Profile (change it on HQ)">' + esc(store.profileNames()[PROFILE]) + '</span>' + html;
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
  if (query) return 'No weapons match “' + esc(query) + '”. Check the spelling or set the filter to All.';
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
  if (!w) { box.innerHTML = ''; return; }
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
    w.up.forEach((u, i) => {
      const n = stars[i];
      html += '<div class="stat"><div class="stat__main"><span class="stat__label">' + esc(u.stat) + '</span>' +
        '<span class="stat__stars" role="img" aria-label="' + esc(u.stat) + ': ' + n + ' of ' + u.max + ' stars">' +
          starHtml(i, n, u.max) + '</span></div>' +
        '<button type="button" class="btn btn--ghost stat__btn" data-act="dec" data-i="' + i + '" aria-label="Remove a star: ' + esc(u.stat) + '"' + (n === 0 ? ' disabled' : '') + '>−</button>' +
        '<button type="button" class="btn btn--ghost stat__btn" data-act="inc" data-i="' + i + '" aria-label="Add a star: ' + esc(u.stat) + '"' + (n === u.max ? ' disabled' : '') + '>+</button></div>';
    });
  } else {
    html += dropsHtml(w);
  }
  box.innerHTML = html + '</div>';
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
      const s = starsOf(w);
      s[i] = clamp(s[i] + (name === 'inc' ? 1 : -1), 0, w.up[i].max);
      setStars(w, s);
      break;
    }
    case 'star': {
      if (!w || !w.up[i]) return;
      const n = Number(el.dataset.n);
      const s = starsOf(w);
      s[i] = clamp(s[i] === n ? n - 1 : n, 0, w.up[i].max);
      setStars(w, s);
      break;
    }
    case 'max':
      if (!w) return;
      setStars(w, w.up.map((u) => u.max));
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
  b.innerHTML = '<p>Your old EDF 4.1 checklist on this device has ' + found.count + ' weapons checked. Import them here?</p>' +
    '<button type="button" class="btn btn--accent" data-act="legacy-import">Import</button>' +
    '<button type="button" class="btn btn--ghost" data-act="legacy-dismiss">Not now</button>';
  b.hidden = false;
}
async function importLegacyNow() {
  const found = store.findLegacyOnDevice();
  if (!found) return;
  saveNow();
  try {
    const n = await store.importLegacy(found.data);
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
        id: t[0], name: t[1], lname: t[1].toLowerCase(), level: t[2], src: t[3],
        up: (t[4] || []).map((u) => ({ stat: D.stats[u[0]], max: u[1] })), ci, ki,
      };
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
  checkLegacy();
  const v = store.checkVersion();
  if (v.updated) showToast('Updated to v' + v.to);
}
// A new version was installed while this page was open: offer to load it.
window.addEventListener('edf-update', () => {
  showToast('A new version is installed.', { label: 'Reload', run: () => window.location.reload() }, true);
});
boot();
