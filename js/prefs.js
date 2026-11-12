// ============================================================================
// prefs.js – applies the two display settings before the page is drawn, so
// there is no flash: text size (--ts and class "big-text" on <html>) and
// background effects (class "no-fx" on <html>). Settings are changed on the HQ page.
// Plain script (not a module) so it runs immediately in <head>.
// ============================================================================
(function () {
  const KEY = 'edfTracker.prefs';

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
    let ts = p.text && p.text !== 'auto' ? parseFloat(p.text) : systemScale();
    if (!(ts > 0)) ts = 1;
    ts = Math.min(1.6, Math.max(0.85, Math.round(ts * 100) / 100));
    root.style.setProperty('--ts', String(ts));
    if (p.fx === 'off') root.classList.add('no-fx'); else root.classList.remove('no-fx');
    // Large text needs more room than one phone screen: the game pages switch to a scrolling layout.
    if (ts >= 1.3) root.classList.add('big-text'); else root.classList.remove('big-text');
  }

  window.EDFPrefs = { apply: apply };
  apply();
  // Settings may have changed on HQ while this page sat in the back/forward cache.
  window.addEventListener('pageshow', apply);
})();
