/* DC Phönix – Service Worker: Seite und Spielplan auch ohne Netz */
var V = "dcp-v2";
var SHELL = ["./", "index.html", "config.json", "data.json", "manifest.webmanifest", "logo-offiziell.png", "logo-favicon.png", "logo-apple.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(V).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return fetch(new Request(u, { cache: "reload" })).then(function (r) { if (r.ok) return c.put(u, r); }).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== V; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

var OFFLINE = '<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#070707;color:#f4f4f2;font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px"><div><h1 style="font-size:1.4rem">DC Phönix</h1><p>Du bist offline und die Seite war noch nicht gespeichert.<br>Öffne sie einmal mit Internet, danach geht sie auch ohne.</p></div>';
function fromCache(req) {
  return caches.match(req, { ignoreSearch: true }).then(function (m) {
    return m || caches.match("./") || caches.match("index.html");
  }).then(function (m) { return m || caches.match("index.html"); });
}
function netFirst(req) {
  return fetch(req).then(function (r) {
    if (r && r.ok) { var cp = r.clone(); caches.open(V).then(function (c) { c.put(req, cp); }); }
    return r;
  }).catch(function () {
    return fromCache(req).then(function (m) {
      if (m) return m;
      if (req.mode === "navigate") return new Response(OFFLINE, { headers: { "Content-Type": "text/html; charset=utf-8" } });
      return Response.error();
    });
  });
}
function staleWhileRevalidate(req) {
  return caches.match(req, { ignoreSearch: true }).then(function (m) {
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
