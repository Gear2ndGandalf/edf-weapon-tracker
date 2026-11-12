// Registers the service worker so the tracker works offline, asks it to keep
// this page's game available offline (see the file groups in sw.js), and
// tells the page when a new version has been installed while it is open.
if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  window.addEventListener('load', function () {
    const sw = navigator.serviceWorker;
    const hadWorker = !!sw.controller; // false on the very first visit
    sw.register('sw.js').catch(function () { /* offline support is optional */ });
    sw.ready.then(function (reg) {
      const game = document.body.getAttribute('data-game');
      if (game && reg.active) reg.active.postMessage({ type: 'keep-offline', game: game });
    }).catch(function () { /* ignore */ });
    sw.addEventListener('controllerchange', function () {
      if (hadWorker) window.dispatchEvent(new Event('edf-update'));
    });
  });
}
