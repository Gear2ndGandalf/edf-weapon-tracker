// ============================================================================
// prefs.js – applies the display settings before the page is drawn, so there
// is no flash: text size (--ts and class "big-text" on <html>), background
// effects (class "no-fx"), the game-page layout (class "page-scroll") and each
// game's own text: font (--font), size and style (classes "type-bold",
// "type-italic", "type-caps"). Settings are changed on the HQ page.
// Plain script (not a module) so it runs immediately in <head>.
// ============================================================================
(function () {
  const KEY = 'edfTracker.prefs';

  // Fonts a game page can use: [id, name shown on HQ, CSS family, files to keep for offline use].
  // 'default' is the game's own font from its theme file. The @font-face rules are in css/base.css.
  const two = (id, light) => ['fonts/' + id + '-latin-' + light + '-normal.woff2', 'fonts/' + id + '-latin-700-normal.woff2'];
  const FONTS = [
    ['default', 'Game default', '', []],
    ['orbitron', 'Orbitron', "'Orbitron'", two('orbitron', 500)],
    ['exo2', 'Exo 2', "'Exo 2'", two('exo-2', 500)],
    ['chakra', 'Chakra Petch', "'Chakra Petch'", two('chakra-petch', 500)],
    ['tektur', 'Tektur', "'Tektur'", two('tektur', 500)],
    ['quantico', 'Quantico', "'Quantico'", two('quantico', 400)],
    ['jura', 'Jura', "'Jura'", two('jura', 500)],
    ['oxanium', 'Oxanium', "'Oxanium'", ['fonts/oxanium-latin-500-normal.woff2', 'fonts/oxanium-latin-600-normal.woff2', 'fonts/oxanium-latin-700-normal.woff2']],
    ['rajdhani', 'Rajdhani', "'Rajdhani'", ['fonts/rajdhani-latin-500-normal.woff2', 'fonts/rajdhani-latin-600-normal.woff2']],
    ['saira', 'Saira Condensed', "'Saira Condensed'", ['fonts/saira-condensed-latin-500-normal.woff2', 'fonts/saira-condensed-latin-600-normal.woff2', 'fonts/saira-condensed-latin-700-normal.woff2']],
    ['mono', 'Share Tech Mono', "'Share Tech Mono'", ['fonts/share-tech-mono-latin-400-normal.woff2']],
  ];
  const fontById = (id) => FONTS.filter((f) => f[0] === id)[0] || FONTS[0];
  // Which game this page is ('' on HQ). <body> does not exist yet when this runs, so the address is used.
  const GAME = (/\/(edf41|edf5|edf6)(?:\.html)?$/.exec(window.location.pathname) || [])[1] || ''; // GitHub Pages also serves /edf5
  // One game's text settings as saved: { font, size, bold, italic, caps }, or {} when nothing is set.
  function typeOf(prefs, game) {
    const all = prefs && typeof prefs.type === 'object' && prefs.type ? prefs.type : {};
    return game && typeof all[game] === 'object' && all[game] ? all[game] : {};
  }

  function read() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }

  // "Auto" text size: follow the device. iPhones and iPads report their
  // Dynamic Type size through the -apple-system-body font (17px by default);
  // other browsers report their default font size through 1rem (16px by default).
  function systemScale() {
    const root = document.documentElement;
    const probe = document.createElement('div');
    let base = 16;
    probe.style.cssText = 'position:absolute;visibility:hidden;font-size:1rem';
    const touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
    if (touch && window.CSS && CSS.supports && CSS.supports('font', '-apple-system-body')) {
      probe.style.font = '-apple-system-body';
      base = 17;
    }
    root.appendChild(probe);
    const px = parseFloat(window.getComputedStyle(probe).fontSize);
    root.removeChild(probe);
    return px > 0 ? px / base : 1;
  }

  function apply() {
    const p = read();
    const root = document.documentElement;
    // A size picked on HQ (60% to 150%) wins; anything else means Auto: follow the device.
    const picked = p.text && p.text !== 'auto' ? parseFloat(p.text) : NaN;
    let ts;
    if (picked > 0) {
      ts = Math.min(1.5, Math.max(0.6, picked));
    } else {
      ts = systemScale();
      if (!(ts > 0)) ts = 1;
      ts = Math.min(1.6, Math.max(0.85, ts));
    }
    // A game page may have its own size, font and style (HQ: the game's "Text" settings).
    const type = typeOf(p, GAME);
    const own = parseFloat(type.size);
    if (own > 0) ts = Math.min(1.5, Math.max(0.6, own));
    ts = Math.round(ts * 100) / 100;
    root.style.setProperty('--ts', String(ts));
    const font = fontById(type.font);
    if (GAME && font[2]) root.style.setProperty('--font', font[2] + ', system-ui, sans-serif'); else root.style.removeProperty('--font');
    [['type-bold', type.bold], ['type-italic', type.italic], ['type-caps', type.caps]].forEach((c) => {
      if (GAME && c[1] === true) root.classList.add(c[0]); else root.classList.remove(c[0]);
    });
    if (p.fx === 'off') root.classList.add('no-fx'); else root.classList.remove('no-fx');
    // Large text needs more room than one phone screen: the game pages switch to a scrolling layout.
    if (ts >= 1.3) root.classList.add('big-text'); else root.classList.remove('big-text');
    // "Game pages: Taller lists": on phones the game pages scroll, with a taller weapon list and full details.
    if (p.layout === 'scroll') root.classList.add('page-scroll'); else root.classList.remove('page-scroll');
  }

  window.EDFPrefs = {
    apply: apply,
    FONTS: FONTS,
    // The font files a game's page needs with its current settings (js/sw-register.js asks the offline cache to keep them).
    fontFiles: function (game) { return fontById(typeOf(read(), game).font)[3].slice(); },
  };
  apply();
  // Settings may have changed on HQ while this page sat in the back/forward cache.
  window.addEventListener('pageshow', apply);
})();
