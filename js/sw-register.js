// Registers the service worker so the tracker works offline, asks it to keep
// this page's game available offline (see the file groups in sw.js), and
// tells the page when a new version has been installed while it is open.
if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  window.addEventListener('load', function () {
    const sw = navigator.serviceWorker;
    const hadWorker = !!sw.controller; // false on the very first visit
    sw.register('sw.js', { updateViaCache: 'none' }).catch(function () { /* offline support is optional */ });
    // Ask a worker to keep this page's game, and the font the player picked for it on HQ (see js/prefs.js).
    function keep(worker) {
      const game = document.body.getAttribute('data-game');
      const fonts = game && window.EDFPrefs && window.EDFPrefs.fontFiles ? window.EDFPrefs.fontFiles(game) : [];
      if (game && worker) worker.postMessage({ type: 'keep-offline', game: game, fonts: fonts });
    }
    sw.ready.then(function (reg) { keep(reg.active); }).catch(function () { /* ignore */ });
    sw.addEventListener('controllerchange', function () {
      keep(sw.controller); // a new version starts with an empty cache: ask again, or the picked font would be missing offline
      if (hadWorker) window.dispatchEvent(new Event('edf-update'));
    });
  });
}
