/* DC Phönix – Service Worker: Seite und Spielplan auch ohne Netz */
var V = "dcp-v1";
var SHELL = ["./", "index.html", "config.json", "data.json", "manifest.webmanifest", "logo-offiziell.png", "logo-favicon.png", "logo-apple.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(V).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== V; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function netFirst(req) {
  return fetch(req).then(function (r) {
    if (r && r.ok) { var cp = r.clone(); caches.open(V).then(function (c) { c.put(req, cp); }); }
    return r;
  }).catch(function () { return caches.match(req).then(function (m) { return m || caches.match("index.html"); }); });
}
function staleWhileRevalidate(req) {
  return caches.match(req).then(function (m) {
    var net = fetch(req).then(function (r) {
      if (r && r.ok) { var cp = r.clone(); caches.open(V).then(function (c) { c.put(req, cp); }); }
      return r;
    }).catch(function () { return m; });
    return m || net;
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var u = new URL(req.url);
  if (u.origin !== location.origin) return;                    /* Supabase & Co. nie anfassen */
  if (/\/profil(\.html|\.js)?$/.test(u.pathname)) return;      /* Login-Seite immer frisch */
  if (req.mode === "navigate" || /\.(json|html|webmanifest)$/.test(u.pathname) || u.pathname.slice(-1) === "/") {
    e.respondWith(netFirst(req));
  } else {
    e.respondWith(staleWhileRevalidate(req));
  }
});
