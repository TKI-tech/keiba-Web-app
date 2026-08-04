// 競馬予想Webアプリ用 Service Worker
//
// Streamlitはページ内容をWebSocket経由で動的に描画するSPAのため、アプリ本体
// (HTML/JS/WSレスポンス)は積極キャッシュしない。キャッシュするのはPWAの
// インストール性に関わる静的アセット(アイコン・manifest)と、オフライン時の
// フォールバック画面のみ。

const CACHE_NAME = "keiba-yosou-pwa-v1";
const PRECACHE_URLS = [
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/offline.html",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  const isPrecachedAsset = PRECACHE_URLS.includes(url.pathname);
  if (isPrecachedAsset) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/offline.html"))
    );
    return;
  }

  // Streamlit本体のアセット・WebSocket通信はそのままネットワークへ通す。
});
