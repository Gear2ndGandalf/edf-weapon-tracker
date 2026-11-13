// ============================================================================
// sw.js – offline support.
//
// The cache is named after the app version (js/version.js), so publishing a
// new version makes every phone drop the old files and fetch the new ones.
//
// To keep the first visit small, only HQ and the shared files are downloaded
// up front (CORE). Each game's files are saved the first time that game is
// opened (GAMES). After that, everything is answered from the cache first and
// refreshed in the background.
// ============================================================================
importScripts('js/version.js');
const CACHE = 'edf-tracker-v' + self.APP_VERSION;

const CORE = [
  './', 'index.html', 'manifest.webmanifest',
  'css/base.css', 'css/hq.css',
  'js/version.js', 'js/prefs.js', 'js/store.js', 'js/hq.js', 'js/savefile.js', 'js/sw-register.js',
  'data/edf41-legacy.json',
  'img/rh-base.svg', 'img/rh-light.svg',
  'fonts/oxanium-latin-600-normal.woff2', 'fonts/oxanium-latin-700-normal.woff2',
  'fonts/rajdhani-latin-500-normal.woff2', 'fonts/rajdhani-latin-600-normal.woff2',
  'fonts/saira-condensed-latin-500-normal.woff2', 'fonts/saira-condensed-latin-700-normal.woff2', 'fonts/share-tech-mono-latin-400-normal.woff2',
  'icons/icon-180.png', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png',
];
const SHARED_GAME = ['css/app.css', 'js/app.js'];
const GAMES = {
  edf41: ['edf41.html', 'css/theme-41.css', 'data/edf41.json',
    'fonts/saira-condensed-latin-500-normal.woff2', 'fonts/saira-condensed-latin-600-normal.woff2'],
  edf5: ['edf5.html', 'css/theme-5.css', 'data/edf5.json'],
  edf6: ['edf6.html', 'css/theme-6.css', 'data/edf6.json', 'img/rh-dark.svg'],
};

const OFFLINE_PAGE = '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Offline · EDF Unlock Tracker</title>' +
  '<style>body{margin:0;padding:24px;background:#0c0d10;color:#e9e6df;font-family:system-ui,sans-serif;line-height:1.4}' +
  'a{color:#e9e6df}</style></head><body><h1>Not saved for offline use yet</h1>' +
  '<p>This game has not been opened on this device while online. Connect to the internet and open it once; ' +
  'after that it works offline.</p><p><a href="index.html">Back to HQ</a></p></body></html>';

// Files are fetched past the browser's own HTTP cache, so a new version never
// starts out with a stale copy of a file.
const fresh = (url) => new Request(url, { cache: 'reload' });

// Save files, skipping anything already cached.
function keep(urls) {
  return caches.open(CACHE).then((cache) =>
    Promise.all(urls.map((url) =>
      cache.match(url).then((hit) => hit || cache.add(fresh(url)).catch(() => { /* retried on the next visit */ }))
    ))
  );
}
// The files of a font the player picked for a game. Only plain names in fonts/ are accepted.
const fontFiles = (fonts) => (Array.isArray(fonts) ? fonts : []).filter((f) => typeof f === 'string' && /^fonts\/[a-z0-9-]+\.woff2$/.test(f)).slice(0, 6);
// Save one game's files, with the font picked for it, if any.
function keepOffline(game, fonts) {
  const files = GAMES[game];
  if (!files) return Promise.resolve();
  return keep(SHARED_GAME.concat(files, fontFiles(fonts)));
}
function gameOf(url) {
  const m = /\/(edf41|edf5|edf6)\.html$/.exec(new URL(url).pathname);
  return m ? m[1] : null;
}

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE.map(fresh))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
      // Pages that were already open when this worker took over (first visit).
      .then(() => self.clients.matchAll({ type: 'window' }))
      .then((clients) => Promise.all(clients.map((c) => keepOffline(gameOf(c.url)))))
  );
});

self.addEventListener('message', (event) => {
  const msg = event.data;
  if (msg && msg.type === 'keep-offline') event.waitUntil(keepOffline(msg.game, msg.fonts));
  if (msg && msg.type === 'keep-fonts') event.waitUntil(keep(fontFiles(msg.fonts))); // HQ: a font was just picked for a game
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  const game = req.mode === 'navigate' ? gameOf(req.url) : null;
  if (game) event.waitUntil(keepOffline(game));
  event.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(req, { ignoreSearch: true }).then((hit) => {
        const network = fetch(req)
          .then((res) => {
            // Redirected responses cannot be replayed for page loads, so they are not cached.
            if (res && res.ok && !res.redirected) cache.put(req, res.clone());
            return res;
          })
          .catch(() => {
            if (hit) return hit;
            if (req.mode === 'navigate') return new Response(OFFLINE_PAGE, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
            return new Response('Offline and not cached yet.', { status: 503, headers: { 'Content-Type': 'text/plain' } });
          });
        if (hit) event.waitUntil(network); // keep the worker alive for the background refresh
        return hit || network;
      })
    )
  );
});
