(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var CFG = null, SB = "", KEY = "", S = null, PROFILE = null, RECOVERY = false, CURPW = "", VIALINK = false;
  var SKEY = "dcp_session";

  var FELDER = [
    { k: "spitzname", l: "Spitzname", t: "text", max: 40 },
    { k: "pfeile", l: "Meine Dartpfeile", t: "text", max: 80, h: "Marke und Modell, z. B. Target Phil Taylor" },
    { k: "gewicht_gramm", l: "Gewicht der Pfeile (Gramm)", t: "number", min: 10, max: 60, step: "0.1" },
    { k: "bestes_finish", l: "Bestes Finish", t: "number", min: 2, max: 170, step: "1", h: "Höchster Checkout, 2 bis 170" },
    { k: "bester_short_leg", l: "Bester Short Leg (Darts)", t: "number", min: 9, max: 60, step: "1", h: "Wenigste Darts für ein Leg, mindestens 9" },
    { k: "herkunft", l: "Woher ich komme", t: "text", max: 60 },
    { k: "geburtstag", l: "Geburtstag", t: "date", h: "Öffentlich wird nur Tag und Monat gezeigt, nie das Jahr." },
    { k: "geburtsort", l: "Geboren in", t: "text", max: 60 },
    { k: "nationalitaet", l: "Nationalität", t: "text", max: 40 }
  ];

  function show(id) {
    ["vLogin", "vPw", "vProfile", "off"].forEach(function (x) { $(x).hidden = x !== id; });
    window.scrollTo(0, 0);
  }
  function msg(id, text, ok) {
    var m = $(id); if (!text) { m.hidden = true; return; }
    m.hidden = false; m.className = "msg " + (ok ? "ok" : "bad"); m.textContent = text;
  }
  function saveS() { try { if (S) sessionStorage.setItem(SKEY, JSON.stringify(S)); else sessionStorage.removeItem(SKEY); } catch (e) {} }
  function loadS() { try { var r = sessionStorage.getItem(SKEY); return r ? JSON.parse(r) : null; } catch (e) { return null; } }
  function setSession(j) {
    S = { access_token: j.access_token, refresh_token: j.refresh_token, uid: j.user && j.user.id,
          email: j.user && j.user.email, exp: Date.now() + (j.expires_in || 3600) * 1000 - 30000 };
    saveS();
  }

  function raw(path, opt) {
    opt = opt || {};
    var h = { "apikey": KEY, "Content-Type": "application/json" };
    if (opt.token) h["Authorization"] = "Bearer " + opt.token;
    if (opt.prefer) h["Prefer"] = opt.prefer;
    return fetch(SB + path, {
      method: opt.method || "GET", headers: h, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer",
      body: opt.body ? JSON.stringify(opt.body) : undefined
    }).then(function (r) {
      return r.text().then(function (t) {
        var j = null; try { j = t ? JSON.parse(t) : null; } catch (e) {}
        if (!r.ok) { var e = new Error("http"); e.status = r.status; e.body = j; throw e; }
        return j;
      });
    });
  }
  function refresh() {
    if (!S || !S.refresh_token) return Promise.reject(new Error("nosession"));
    return raw("/auth/v1/token?grant_type=refresh_token", { method: "POST", body: { refresh_token: S.refresh_token } })
      .then(setSession);
  }
  function auth(path, opt) {
    opt = opt || {};
    var go = function () { opt.token = S.access_token; return raw(path, opt); };
    if (!S) return Promise.reject(new Error("nosession"));
    var p = Date.now() > S.exp ? refresh().then(go) : go();
    return p.catch(function (e) {
      if (e.status === 401 && !opt._retried) { opt._retried = true; return refresh().then(go); }
      throw e;
    });
  }

  function logout(m) {
    var t = S && S.access_token;
    S = null; PROFILE = null; CURPW = ""; saveS();
    if (t) raw("/auth/v1/logout", { method: "POST", token: t }).catch(function () {});
    ["liPw", "pwNew", "pwNew2"].forEach(function (i) { $(i).value = ""; });
    show("vLogin"); $("fLogin").hidden = false; $("fForgot").hidden = true;
    msg("liMsg", m || "", !!m && m.indexOf("abgemeldet") >= 0);
  }

  // ---------- Passwort-Regeln ----------
  function pwFehler(p, p2) {
    if (p.length < 12) return "Das Passwort braucht mindestens 12 Zeichen.";
    if (p !== p2) return "Die beiden Passwörter sind nicht gleich.";
    var klassen = [/[a-zäöüß]/, /[A-ZÄÖÜ]/, /\d/, /[^A-Za-z0-9äöüßÄÖÜ]/].filter(function (r) { return r.test(p); }).length;
    if (p.length < 16 && klassen < 4) return "Nutze Groß- und Kleinbuchstaben, Zahl und Sonderzeichen, oder mindestens 16 Zeichen.";
    if (/^(.)\1+$/.test(p)) return "Bitte ein Passwort ohne Wiederholungen wählen.";
    var low = p.toLowerCase();
    var schwach = ["passwort", "password", "12345678", "qwertz", "qwerty", "dartpfeil", "phoenix", "phönix", "durmersheim"];
    for (var i = 0; i < schwach.length; i++) if (low.indexOf(schwach[i]) >= 0) return "Dieses Passwort ist zu leicht zu erraten.";
    return "";
  }

  // ---------- Profil ----------
  function loadProfile() {
    return auth("/rest/v1/profiles?select=*&id=eq." + encodeURIComponent(S.uid)).then(function (rows) {
      if (!rows || !rows[0]) throw new Error("noprofile");
      PROFILE = rows[0]; return PROFILE;
    });
  }
  function route() {
    if (!PROFILE) return;
    if (PROFILE.muss_passwort_aendern || RECOVERY) { showPw(); } else { showProfile(); }
  }
  function showPw() {
    $("pwWhy").textContent = RECOVERY && !PROFILE.muss_passwort_aendern
      ? "Lege ein neues Passwort fest."
      : "Willkommen! Bitte lege jetzt ein eigenes Passwort fest. Erst danach kannst du dein Profil bearbeiten.";
    $("pwWhy").style.fontWeight = "700";
    ["pwNew", "pwNew2", "pwOld"].forEach(function (i) { $(i).value = ""; });
    $("oldBox").hidden = VIALINK || !!CURPW;
    msg("pwMsg", ""); show("vPw");
  }
  function showProfile() {
    $("whoName").textContent = PROFILE.spielername || "Spieler";
    $("whoMail").textContent = PROFILE.email || (S && S.email) || "";
    var box = $("fields"); box.textContent = "";
    FELDER.forEach(function (f) {
      var w = document.createElement("div"); w.className = "field";
      var lab = document.createElement("label"); lab.htmlFor = "f_" + f.k; lab.textContent = f.l; w.appendChild(lab);
      var inp = document.createElement("input"); inp.id = "f_" + f.k; inp.type = f.t; inp.autocomplete = "off";
      if (f.t === "text") inp.maxLength = f.max;
      if (f.t === "number") { inp.min = f.min; inp.max = f.max; inp.step = f.step; inp.inputMode = "decimal"; }
      if (f.t === "date") { inp.min = "1900-01-01"; inp.max = new Date().toISOString().slice(0, 10); }
      var v = PROFILE[f.k]; inp.value = v == null ? "" : String(v);
      w.appendChild(inp);
      if (f.h) { var h = document.createElement("div"); h.className = "hint"; h.textContent = f.h; w.appendChild(h); }
      var c = document.createElement("label"); c.className = "chk";
      var cb = document.createElement("input"); cb.type = "checkbox"; cb.id = "z_" + f.k; cb.checked = !!PROFILE["zeige_" + f.k];
      c.appendChild(cb); c.appendChild(document.createTextNode("Öffentlich auf der Webseite zeigen"));
      w.appendChild(c); box.appendChild(w);
    });
    $("erinnerung").value = PROFILE.erinnerung || "1";
    msg("prMsg", ""); show("vProfile"); loadNext();
  }

  function wert(f, el) {
    var v = el.value.trim();
    if (v === "") return null;
    if (f.t === "number") {
      var n = Number(v.replace(",", "."));
      if (!isFinite(n) || n < f.min || n > f.max) throw new Error(f.l + ": Bitte einen Wert zwischen " + f.min + " und " + f.max + " eingeben.");
      return n;
    }
    if (f.t === "date") {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || v < "1900-01-01" || v > new Date().toISOString().slice(0, 10)) throw new Error("Geburtstag: Bitte ein gültiges Datum eingeben.");
      return v;
    }
    if (v.length > f.max) throw new Error(f.l + " ist zu lang.");
    return v;
  }
  function onSave(e) {
    e.preventDefault();
    var body = {};
    try {
      FELDER.forEach(function (f) { body[f.k] = wert(f, $("f_" + f.k)); body["zeige_" + f.k] = $("z_" + f.k).checked; });
    } catch (er) { msg("prMsg", er.message); return; }
    body.erinnerung = $("erinnerung").value;
    patch(body, "Gespeichert. Auf der Webseite erscheint es nach der nächsten Aktualisierung.");
  }
  function patch(body, okText) {
    msg("prMsg", "Speichere …", true);
    auth("/rest/v1/profiles?id=eq." + encodeURIComponent(S.uid), { method: "PATCH", body: body, prefer: "return=minimal" })
      .then(function () { return loadProfile(); })
      .then(function () { showProfile(); msg("prMsg", okText, true); })
      .catch(function (e) { msg("prMsg", e.status === 401 || e.status === 403 ? "Bitte melde dich neu an." : "Speichern hat nicht geklappt. Prüfe deine Eingaben und versuche es noch einmal."); });
  }
  function onWipe() {
    var body = {};
    FELDER.forEach(function (f) { body[f.k] = null; body["zeige_" + f.k] = false; });
    $("wipeAsk").hidden = true; $("bWipe").hidden = false;
    patch(body, "Alle Angaben wurden gelöscht.");
  }

  // ---------- Nächstes Spiel ----------
  function norm(s) { return String(s || "").replace(/\s+/g, " ").trim().toLowerCase(); }
  function loadNext() {
    $("nextBox").hidden = true;
    Promise.all([fetch("config.json", { cache: "no-store" }).then(function (r) { return r.json(); }),
                 fetch("data.json", { cache: "no-store" }).then(function (r) { return r.json(); })])
      .then(function (a) {
        var cfg = a[0], data = a[1], me = norm(PROFILE.spielername), best = null, bestTeam = null;
        var today = new Date().toISOString().slice(0, 10);
        (data.teams || []).forEach(function (t) {
          if (!(t.players || []).some(function (p) { return norm(p.name) === me; })) return;
          (t.fixtures || []).forEach(function (f) {
            if (f.ergebnis || !f.heim || !f.datum || f.datum < today) return;
            if (/spielfrei/i.test(f.heim + f.gast)) return;
            if (!best || f.datum < best.datum) { best = f; bestTeam = t; }
          });
        });
        if (!best) return;
        var ort = "", k = norm(best.heim);
        Object.keys(cfg.spielorte || {}).forEach(function (n) { if (norm(n) === k) ort = cfg.spielorte[n]; });
        if (!ort && (cfg.teams || []).some(function (t) { return norm(t.name) === k; })) ort = (cfg.verein || {}).spiellokal || "";
        var heim = norm(best.heim) === norm(bestTeam.name);
        var p = best.datum.split("-"), d = new Date(+p[0], +p[1] - 1, +p[2]);
        var wt = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"][d.getDay()];
        var box = $("nextTxt"); box.textContent = "";
        var b = document.createElement("b"); b.textContent = bestTeam.name + (heim ? " gegen " : " bei ") + (heim ? best.gast : best.heim) + "";
        var s = document.createElement("div");
        s.textContent = wt + ", " + p[2] + "." + p[1] + "." + p[0] + " um " + (best.zeit || "20:00") + " Uhr" + (ort ? " · " + ort : "");
        box.appendChild(b); box.appendChild(s);
        var L = $("nextLinks"); L.textContent = "";
        if (ort) {
          var q = encodeURIComponent(ort);
          [["Google Maps", "https://www.google.com/maps/dir/?api=1&destination=" + q],
           ["Apple Karten", "https://maps.apple.com/?daddr=" + q + "&dirflg=d"]].forEach(function (x) {
            var a2 = document.createElement("a"); a2.className = "btn sm"; a2.textContent = "Navigation: " + x[0];
            a2.href = x[1]; a2.target = "_blank"; a2.rel = "noopener noreferrer"; L.appendChild(a2);
          });
        }
        $("nextBox").hidden = false;
      }).catch(function () {});
  }

  // ---------- Handlers ----------
  function onLogin(e) {
    e.preventDefault();
    var mail = $("liMail").value.trim(), pw = $("liPw").value;
    if (!mail || !pw) { msg("liMsg", "Bitte E-Mail und Passwort eingeben."); return; }
    msg("liMsg", "Melde an …", true);
    raw("/auth/v1/token?grant_type=password", { method: "POST", body: { email: mail, password: pw } })
      .then(function (j) { setSession(j); CURPW = pw; VIALINK = false; $("liPw").value = ""; RECOVERY = false; return loadProfile(); })
      .then(route)
      .catch(function (er) {
        S = null; saveS(); $("liPw").value = "";
        msg("liMsg", er.status === 429 ? "Zu viele Versuche. Bitte warte kurz und versuche es später noch einmal."
          : "Anmeldung nicht möglich. Prüfe E-Mail und Passwort.");
      });
  }
  function onForgot(e) {
    e.preventDefault();
    var mail = $("fgMail").value.trim();
    if (!mail) { msg("fgMsg", "Bitte E-Mail eingeben."); return; }
    var redirect = location.origin + location.pathname;
    raw("/auth/v1/recover?redirect_to=" + encodeURIComponent(redirect), { method: "POST", body: { email: mail } })
      .catch(function () {})
      .then(function () { msg("fgMsg", "Wenn zu dieser Adresse ein Konto existiert, ist jetzt eine E-Mail mit einem Link unterwegs.", true); });
  }
  function onPw(e) {
    e.preventDefault();
    var p = $("pwNew").value, f = pwFehler(p, $("pwNew2").value);
    if (f) { msg("pwMsg", f); return; }
    msg("pwMsg", "Speichere …", true);
    var step = 1;
    var body = { password: p }, cur = CURPW || $("pwOld").value;
    if (cur && !VIALINK) body.current_password = cur;
    if (!VIALINK && !cur) { msg("pwMsg", "Bitte gib dein aktuelles Passwort ein."); return; }
    auth("/auth/v1/user", { method: "PUT", body: body })
      .then(function () { step = 2; return auth("/rest/v1/rpc/passwort_geaendert", { method: "POST", body: {} }); })
      .then(function () { RECOVERY = false; CURPW = p; VIALINK = false; return loadProfile(); })
      .then(function () { ["pwNew", "pwNew2", "pwOld"].forEach(function (i) { $(i).value = ""; }); showProfile(); msg("prMsg", "Dein neues Passwort ist gespeichert.", true); })
      .catch(function (er) {
        var t = er.body && (er.body.error_code || er.body.msg || "");
        msg("pwMsg", /same_password/.test(t) ? "Das neue Passwort muss anders sein als das alte."
          : /current_password/.test(t) ? "Das aktuelle Passwort fehlt oder stimmt nicht."
          : /weak_password/.test(t) ? "Dieses Passwort ist zu schwach. Wähle ein längeres."
          : "Das hat nicht geklappt (Schritt " + step + ", Code " + (er.status || "?") + (t ? ", " + String(t).slice(0, 60) : "") + "). Bitte versuche es noch einmal.");
      });
  }

  function init() {
    fetch("config.json", { cache: "no-store" }).then(function (r) { return r.json(); }).catch(function () { return {}; }).then(function (c) {
      CFG = c; var k = c.konto || {};
      SB = String(k.supabase_url || "").replace(/\/+$/, ""); KEY = String(k.anon_key || "");
      if (!/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(SB) || !KEY) { show("off"); return; }

      // Link aus der Passwort-vergessen-Mail: Token steckt im Hash
      var h = location.hash.replace(/^#/, "");
      if (h.indexOf("access_token=") >= 0) {
        var q = new URLSearchParams(h);
        if (q.get("type") === "recovery" && q.get("access_token")) {
          RECOVERY = true; VIALINK = true;
          var tok = q.get("access_token");
          history.replaceState(null, "", location.pathname);
          raw("/auth/v1/user", { token: tok }).then(function (u) {
            S = { access_token: tok, refresh_token: q.get("refresh_token") || "", uid: u.id, email: u.email,
                  exp: Date.now() + (Number(q.get("expires_in")) || 3600) * 1000 - 30000 };
            saveS(); return loadProfile();
          }).then(route).catch(function () { RECOVERY = false; show("vLogin"); msg("liMsg", "Der Link ist abgelaufen oder wurde schon benutzt. Fordere einen neuen an."); });
          return;
        }
        history.replaceState(null, "", location.pathname);
      } else if (h.indexOf("error") >= 0) {
        history.replaceState(null, "", location.pathname);
        show("vLogin"); msg("liMsg", "Der Link ist abgelaufen oder wurde schon benutzt. Fordere einen neuen an."); return;
      }

      S = loadS();
      if (S) { loadProfile().then(route).catch(function () { S = null; saveS(); show("vLogin"); }); }
      else show("vLogin");
    });
  }

  $("fLogin").addEventListener("submit", onLogin);
  $("fForgot").addEventListener("submit", onForgot);
  $("fPw").addEventListener("submit", onPw);
  $("fProfile").addEventListener("submit", onSave);
  $("bForgot").addEventListener("click", function () { $("fLogin").hidden = true; $("fForgot").hidden = false; msg("fgMsg", ""); $("fgMail").value = $("liMail").value; });
  $("bBack").addEventListener("click", function () { $("fLogin").hidden = false; $("fForgot").hidden = true; });
  $("bOut").addEventListener("click", function () { logout("Du wurdest abgemeldet."); });
  $("pwOut").addEventListener("click", function () { logout("Du wurdest abgemeldet."); });
  $("bChangePw").addEventListener("click", function () { RECOVERY = true; showPw(); });
  $("bWipe").addEventListener("click", function () { $("wipeAsk").hidden = false; $("bWipe").hidden = true; });
  $("bWipeNo").addEventListener("click", function () { $("wipeAsk").hidden = true; $("bWipe").hidden = false; });
  $("bWipeYes").addEventListener("click", onWipe);
  document.querySelectorAll("[data-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var i = $(b.getAttribute("data-toggle")); var vis = i.type === "text";
      i.type = vis ? "password" : "text"; b.textContent = vis ? "Zeigen" : "Verbergen";
    });
  });
  // Inaktivität: nach 15 Minuten ohne Eingabe abmelden
  var idle; function reset() { clearTimeout(idle); idle = setTimeout(function () { if (S) logout("Aus Sicherheitsgründen wurdest du abgemeldet."); }, 15 * 60 * 1000); }
  ["click", "keydown", "touchstart"].forEach(function (ev) { document.addEventListener(ev, reset, { passive: true }); }); reset();
  init();
})();
