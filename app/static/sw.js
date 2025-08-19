// static/sw.js
const VERSION = 'v3';
const STATIC_CACHE = `static-${VERSION}`;
const HTML_CACHE   = `html-${VERSION}`;
const OFFLINE_URL  = '/static/offline.html';

const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  // Ajoute ici tes CSS/JS statiques, ex:
  // '/static/css/bootstrap.min.css',
  // '/static/js/app.js',
  OFFLINE_URL
];

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

// Pré-cache des assets statiques
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(c => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

// Claim immédiat + nettoyage des vieux caches
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(k => ![STATIC_CACHE, HTML_CACHE].includes(k))
      .map(k => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

// Network-first pour les pages (HTML), SWR pour CSS/JS/icônes/images.
// Fallback offline sur OFFLINE_URL si réseau indisponible.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') {
    event.respondWith(fetch(req)); return;
  }

  const dest = req.destination;

  // HTML : network-first + fallback cache + offline.html
  if (dest === 'document' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req, { credentials: 'include' });
        const cache = await caches.open(HTML_CACHE);
        cache.put(req, fresh.clone());
        return fresh;
      } catch (e) {
        const cache = await caches.open(HTML_CACHE);
        const cached = await cache.match(req);
        return cached || caches.match(OFFLINE_URL);
      }
    })());
    return;
  }

  // Stale-While-Revalidate pour le reste (scripts, styles, images, fonts…)
  if (['script','style','image','font'].includes(dest) || dest === '') {
    event.respondWith((async () => {
      const cache = await caches.open(STATIC_CACHE);
      const cached = await cache.match(req);
      const fetchPromise = fetch(req).then(resp => {
        // Évite de mettre en cache les réponses opaques d’origines “privées” si tu veux
        if (resp && resp.status === 200) cache.put(req, resp.clone());
        return resp;
      }).catch(() => null);
      return cached || (await fetchPromise) || caches.match(OFFLINE_URL);
    })());
    return;
  }

  // Par défaut : passe-plat réseau
  event.respondWith(fetch(req).catch(() => caches.match(OFFLINE_URL)));
});
