// NF-Sawava Suite Service Worker (PWA Shell Caching)
const CACHE_NAME = 'nf-sawava-v2';
const STATIC_URLS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/manifest.json',
  '/favicon.ico',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_URLS).catch(err => console.debug('Precache skipped for some URLs:', err));
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Stale-while-revalidate for static assets, network-only for /api/ and /admin
  if (url.pathname.startsWith('/static/') || url.pathname === '/favicon.ico') {
    event.respondWith(
      caches.match(event.request).then(cached => {
        const fetchPromise = fetch(event.request).then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return networkResponse;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
  }
});
