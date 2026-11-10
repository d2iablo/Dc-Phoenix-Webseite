#!/usr/bin/env python3
"""Holt Tabelle und Spielplan von der Badischen Dart Liga und schreibt data.json.

Aufruf:  python update.py
Test:    python update.py --offline ordner_mit_html --data /tmp/test.json
Nur die Python-Standardbibliothek, nichts zu installieren.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE = "https://www.badischedartliga.de/results/"
UA = "Mozilla/5.0 (compatible; Vereinsseite/1.0)"


def clean(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def norm(s):
    return clean(s or "").casefold()


class Row(list):
    """Tabellenzeile; .links enthält die Link-Adressen (href) der Zeile."""
    links = None


class Collector(HTMLParser):
    """Sammelt Text und Tabellen in der Reihenfolge, in der sie im HTML stehen."""

    def __init__(self, keepbr=False):
        super().__init__(convert_charrefs=True)
        self.keepbr = keepbr
        self.events = []
        self._table = None
        self._depth = 0
        self._row = None
        self._cell = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = Row()
            self._row.links = []
        elif tag == "a" and self._row is not None:
            href = dict(attrs).get("href")
            if href:
                self._row.links.append(href)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag in ("br", "div", "p", "li") and self._cell is not None:
            self._cell.append("\n" if self.keepbr else " ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            raw = "".join(self._cell)
            if self.keepbr:
                lines = [clean(x) for x in raw.split("\n")]
                self._row.append("\n".join(x for x in lines if x))
            else:
                self._row.append(clean(raw))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._table is not None and self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            self._depth = max(0, self._depth - 1)
            if self._depth == 0 and self._table is not None:
                self.events.append(("table", self._table))
                self._table = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._table is None:
            t = clean(data)
            if t:
                self.events.append(("text", t))


def collect(html, keepbr=False):
    c = Collector(keepbr)
    c.feed(html)
    return c.events


def to_int(s):
    d = re.sub(r"\D", "", s or "")
    return int(d) if d else None


def ratio(s):
    m = re.match(r"^\s*(\d+)\s*:\s*(\d+)\s*$", s or "")
    return "%s : %s" % (m.group(1), m.group(2)) if m else (s or "")


def parse_table(html):
    """Gibt die Tabelle als Liste von Zeilen zurück (leer, wenn nichts gefunden wurde)."""
    for kind, rows in collect(html):
        if kind != "table":
            continue
        head_i, low = None, None
        for i, row in enumerate(rows):
            lower = [norm(x) for x in row]
            if "team" in lower and "punkte" in lower:
                head_i, low = i, lower
                break
        if head_i is None:
            continue
        idx = {n: low.index(n) for n in ("platz", "team", "spiele", "g", "u", "v", "sets", "legs", "punkte") if n in low}
        out = []
        for row in rows[head_i + 1:]:
            if idx.get("team", 99) >= len(row) or idx.get("punkte", 99) >= len(row):
                continue
            platz = to_int(row[idx["platz"]]) if "platz" in idx and idx["platz"] < len(row) else len(out) + 1
            punkte = to_int(row[idx["punkte"]])
            if platz is None or punkte is None:
                continue

            def cell(n):
                return row[idx[n]] if n in idx and idx[n] < len(row) else ""

            out.append({
                "platz": platz,
                "team": cell("team"),
                "spiele": to_int(cell("spiele")) or 0,
                "g": to_int(cell("g")) or 0,
                "u": to_int(cell("u")) or 0,
                "v": to_int(cell("v")) or 0,
                "sets": ratio(cell("sets")),
                "legs": ratio(cell("legs")),
                "punkte": punkte,
            })
        if out:
            return out
    return []


DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
SCORE_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")


def parse_fixtures(html, base=BASE):
    """Alle Spiele der Liga mit Spieltag, Datum, Heim, Gast und Ergebnis."""
    fixtures = []
    spieltag, runde, zeit = None, None, "20:00"
    for kind, val in collect(html):
        if kind == "text":
            m = re.match(r"^(Hinrunde|Rückrunde)\b", val)
            if m:
                runde = m.group(1)
            m = re.search(r"(\d+)\.\s*Spieltag", val)
            if m:
                spieltag = int(m.group(1))
                m2 = re.search(r"Spielbeginn[^0-9]*(\d{1,2})(?::(\d{2}))?\s*Uhr", val)
                if m2:
                    zeit = "%02d:%s" % (int(m2.group(1)), m2.group(2) or "00")
            continue
        rows = val
        col = {"datum": 0, "heim": 1, "ergebnis": 2, "gast": 3}
        for row in rows:
            lower = [norm(x) for x in row]
            if "heim" in lower and "gast" in lower:
                col = {"datum": lower.index("datum") if "datum" in lower else 0,
                       "heim": lower.index("heim"),
                       "ergebnis": lower.index("ergebnis") if "ergebnis" in lower else lower.index("heim") + 1,
                       "gast": lower.index("gast")}
                continue
            if not row or max(col.values()) >= len(row):
                continue
            m = DATE_RE.search(row[col["datum"]])
            if not m:
                continue
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            sc = SCORE_RE.match(row[col["ergebnis"]])
            link = None
            for href in getattr(row, "links", None) or []:
                low = href.lower()
                if low.startswith(("#", "javascript", "webcal", "mailto")) or "ical" in low or low.endswith(".ics"):
                    continue
                link = urljoin(base, href)
                break
            fixtures.append({
                "bericht": link,
                "spieltag": spieltag,
                "runde": runde,
                "datum": "%04d-%02d-%02d" % (y, mo, d),
                "zeit": zeit,
                "heim": row[col["heim"]],
                "gast": row[col["gast"]],
                "ergebnis": [int(sc.group(1)), int(sc.group(2))] if sc else None,
            })
    return fixtures


LET_RE = re.compile(r"[A-Za-zÄÖÜäöüß]")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(s).replace("ö", "oe").replace("ä", "ae").replace("ü", "ue").replace("ß", "ss")).strip("-")


def split_names(cell):
    out = []
    for part in cell.split("\n"):
        for n in re.split(r"\s*(?:/|&|\s\+\s)\s*", part):
            if n.strip():
                out.append(n.strip())
    return out


def vals(s):
    """'125' -> [125]; '14\n16' -> [14, 16]; '' -> []"""
    return [to_int(x) for x in (s or "").split("\n")] if (s or "").strip() else []


def parse_report(html):
    """Liest einen Online-Spielberichtsbogen der BDL. Gibt None zurück, wenn nichts erkannt wird."""
    for ev in collect(html, True):
        if ev[0] != "table":
            continue
        rows = ev[1]
        head = None
        for i, r in enumerate(rows):
            low = [norm(x) for x in r]
            if any(x.startswith("heim") for x in low) and any(x.startswith("gast") for x in low):
                head = i
                break
        if head is None:
            continue
        hr = rows[head]
        low = [norm(x) for x in hr]

        def after(prefix):
            for j, x in enumerate(low):
                if x.startswith(prefix):
                    for y in hr[j + 1:]:
                        if y.strip():
                            return y.replace("\n", " ")
            return ""

        games, legs, sets = [], None, None
        prev_game = False
        for r in rows[head + 1:]:
            if any(norm(c).startswith("ergebnis") for c in r):
                prev_game = False
                nums = [m for c in r for m in re.findall(r"(\d+)\s*:\s*(\d+)", c)]
                if nums:
                    legs = [int(nums[0][0]), int(nums[0][1])]
                if len(nums) > 1:
                    sets = [int(nums[1][0]), int(nums[1][1])]
                continue
            idx = next((j for j, c in enumerate(r) if SCORE_RE.match(c)), None)
            if idx is None:
                # Doppel: Die zweite Zeile enthält die Partner (ohne Ergebnis): HF | Max | Name | Name | Max | HF
                lets = [j for j, c in enumerate(r) if LET_RE.search(c)]
                if prev_game and games and len(lets) == 2 and not games[-1].get("_done"):
                    a, b = lets
                    g = games[-1]
                    g["heim"] += split_names(r[a])
                    g["gast"] += split_names(r[b])
                    g["typ"] = "Doppel"
                    g["_done"] = True
                    if a >= 2:
                        g["h"]["hf"] += vals(r[a - 2])
                        g["h"]["max"] += vals(r[a - 1])
                    if b + 2 < len(r):
                        g["g"]["max"] += vals(r[b + 1])
                        g["g"]["hf"] += vals(r[b + 2])
                prev_game = False
                continue
            li = max((j for j in range(idx) if LET_RE.search(r[j])), default=None)
            ri = min((j for j in range(idx + 1, len(r)) if LET_RE.search(r[j])), default=None)
            if li is None or ri is None:
                continue
            left = list(r[max(0, li - 3):li])
            left = [""] * (3 - len(left)) + left
            right = list(r[ri + 1:ri + 4])
            right = right + [""] * (3 - len(right))
            hn, gn = split_names(r[li]), split_names(r[ri])
            m = SCORE_RE.match(r[idx])
            prev_game = True
            games.append({
                "typ": "Doppel" if len(hn) > 1 or len(gn) > 1 else "Einzel",
                "heim": hn, "gast": gn,
                "ergebnis": [int(m.group(1)), int(m.group(2))],
                "h": {"sl": vals(left[0]), "hf": vals(left[1]), "max": vals(left[2])},
                "g": {"max": vals(right[0]), "hf": vals(right[1]), "sl": vals(right[2])},
            })
        if len(games) == 12:
            # Aufbau einer Begegnung: 4 Einzel, 2 Doppel, 4 Einzel, 2 Doppel
            for i, g in enumerate(games):
                g["typ"] = "Doppel" if i in (4, 5, 10, 11) else "Einzel"
        for g in games:
            g.pop("_done", None)
        if games:
            return {"v": 2, "heim": after("heim"), "gast": after("gast"), "legs": legs, "sets": sets, "spiele": games}
    return None


def parse_statistics(html, team_names):
    """Spielerstatistik der BDL. Übernimmt NUR Zeilen, deren Verein-Spalte genau einem unserer Teams entspricht.
    Die Spalten werden relativ zur Team-Zelle gelesen, damit verschobene Zeilen keine Rolle spielen:
    [Spieler] [Team] [Einzel-Siege] [Doppel-Siege] [HF] [SL] [Max]"""
    wanted = {norm(n): n for n in team_names}
    out = []
    for ev in collect(html):
        if ev[0] != "table":
            continue
        for r in ev[1]:
            for j, c in enumerate(r):
                if norm(c) not in wanted or j < 1:
                    continue
                name = r[j - 1]
                if not LET_RE.search(name):
                    break
                rest = list(r[j + 1:j + 6]) + [""] * 5
                out.append({
                    "name": name, "team": wanted[norm(c)],
                    "einzel": to_int(rest[0]) or 0, "doppel": to_int(rest[1]) or 0,
                    "hf": to_int(rest[2]) or 0, "sl": to_int(rest[3]) or 0, "max": to_int(rest[4]) or 0,
                })
                break
    seen, uniq = set(), []
    for p in out:
        k = (norm(p["name"]), norm(p["team"]))
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return sorted(uniq, key=lambda p: (-(2 * p["einzel"] + p["doppel"]), p["name"]))


def fetch(url):
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3)
    raise RuntimeError("Abruf fehlgeschlagen: %s (%s)" % (url, last))


def load_url(url, offline):
    if offline:
        with open(os.path.join(offline, "report_" + slugify(url.rsplit("/", 1)[-1]) + ".html"), encoding="utf-8") as f:
            return f.read()
    return fetch(url)


def load(name, offline):
    if offline:
        with open(os.path.join(offline, name), encoding="utf-8") as f:
            return f.read()
    return fetch(BASE + name)


def write_photo_index(root="fotos"):
    """Listet alle Bilder in fotos/<Ordner>/ nach fotos/index.json auf (Ordner -> Dateinamen)."""
    exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")
    out = {}
    try:
        if os.path.isdir(root):
            for sub in sorted(os.listdir(root)):
                d = os.path.join(root, sub)
                if os.path.isdir(d):
                    out[sub] = sorted(n for n in os.listdir(d) if n.lower().endswith(exts))
            with open(os.path.join(root, "index.json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("Fotoliste:", e)


def fetch_profiles(path="profile.json"):
    """Holt die vom Spieler freigegebenen Profilangaben (Spielerkonten, optional) nach profile.json."""
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        return
    if not url.startswith("https://"):
        print("Profile: SUPABASE_URL muss mit https:// beginnen")
        return
    hdr = {"apikey": key, "Accept": "application/json", "User-Agent": "dc-phoenix-update"}
    if not key.startswith("sb_"):  # alte JWT-Schlüssel brauchen zusätzlich den Bearer-Header
        hdr["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url + "/rest/v1/oeffentliche_profile?select=*", headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = json.load(r)
        out = {}
        for row in rows:
            name = row.pop("spielername", None)
            vals = {k: v for k, v in row.items() if v not in (None, "")}
            if name and vals:
                out[name] = vals
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("Profile: %d Spielerprofile mit freigegebenen Angaben" % len(out))
    except Exception as e:  # noqa: BLE001
        print("Profile: nicht abrufbar (%s)" % type(e).__name__)


# ---------------------------------------------------------------------------
# KI-Berichtstexte (optional). Braucht ANTHROPIC_API_KEY + Supabase (Tabelle "berichte").
# Jeder Text wird nur einmal erzeugt und in Supabase gespeichert.
# ---------------------------------------------------------------------------
KI_MODELL = os.environ.get("KI_MODELL", "claude-haiku-5-5")
KI_URL = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
WT = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MO = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
KI_SYSTEM = (
    "Du schreibst kurze Zeitungsberichte über Dartspiele eines Amateurvereins (Badische Dart Liga) auf Deutsch. "
    "Schreibe eine Überschrift (eine Zeile), danach 2 bis 4 kurze Absätze, insgesamt 90 bis 160 Wörter. "
    "Ton: sachlich, lebendig, freundlich zum Verein, aber ohne Übertreibung. "
    "STRIKTE REGELN: Verwende ausschließlich Fakten aus dem gelieferten JSON. Erfinde keine Zahlen, Namen, Zitate, "
    "Tabellenplätze, Wetter, Zuschauer oder Spielverläufe. Nenne keine Spieler des Gegners. Wenn etwas im JSON fehlt, "
    "erwähne es nicht. Zahlen müssen exakt übernommen werden. Schreibe nur den Bericht, ohne Einleitung, ohne "
    "Markdown, ohne Hashtags, ohne Anführungszeichen um den Text."
)


def _sb(method, path, body=None, prefer=None):
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    hdr = {"apikey": key, "Content-Type": "application/json", "User-Agent": "dc-phoenix-update"}
    if not key.startswith("sb_"):
        hdr["Authorization"] = "Bearer " + key
    if prefer:
        hdr["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers=hdr, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def _datum_lang(ds):
    try:
        d = datetime.strptime(ds, "%Y-%m-%d")
        return "%s, %d. %s %d" % (WT[d.weekday()], d.day, MO[d.month - 1], d.year)
    except Exception:  # noqa: BLE001
        return ""


def _pv(o, i, n):
    a = (o or {}) if isinstance(o, dict) else {}
    out = {}
    for k in ("sl", "hf", "max"):
        v = a.get(k) or []
        out[k] = v[i] if len(v) == n else (v[0] if len(v) == 1 and n == 1 else None)
    return out


def _short(n):
    return re.sub(r"^DC Phönix\s*", "", n or "", flags=re.I) or n


def ki_fakten(f, team, rep, own_names):
    """Baut die Fakten für einen Bericht. Gegner-Spielernamen werden nie mitgeschickt."""
    home = norm(f["heim"]) == norm(team["name"])
    m, g = (f["ergebnis"][0], f["ergebnis"][1]) if home else (f["ergebnis"][1], f["ergebnis"][0])
    fx = {
        "team": _short(team["name"]), "gegner": f["gast"] if home else f["heim"],
        "ort": "zu Hause" if home else "auswärts", "datum": _datum_lang(f.get("datum")),
        "ergebnis_aus_sicht_des_teams": "%d:%d" % (m, g),
    }
    if rep:
        side, oth, ok = ("heim", "gast", "h") if home else ("gast", "heim", "g")
        os_, ps_ = (0, 1) if home else (1, 0)
        ew = el = dw = dl = 0
        st = {}
        for sp in rep.get("spiele", []):
            a, b = sp["ergebnis"][os_], sp["ergebnis"][ps_]
            if sp.get("typ") == "Doppel":
                dw += a > b
                dl += a < b
            else:
                ew += a > b
                el += a < b
            names = sp.get(side, [])
            for i, n in enumerate(names):
                if n == "Gegner":
                    continue
                o = st.setdefault(n, {"name": n, "spiele": 0, "siege": 0, "high_finish": [], "short_leg_darts": [], "maximums": 0})
                o["spiele"] += 1
                o["siege"] += a > b
                v = _pv(sp.get(ok), i, len(names))
                if v["hf"]:
                    o["high_finish"].append(v["hf"])
                if v["sl"]:
                    o["short_leg_darts"].append(v["sl"])
                if v["max"]:
                    o["maximums"] += v["max"]
        if rep.get("legs"):
            fx["legs"] = "%d:%d" % (rep["legs"][os_], rep["legs"][ps_])
        fx["einzel"] = "%d:%d" % (ew, el)
        fx["doppel"] = "%d:%d" % (dw, dl)
        fx["spieler_des_eigenen_teams"] = [v for v in st.values() if v["spiele"]]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    later = [x for x in team.get("fixtures", []) if x.get("ergebnis") and x["datum"] > f["datum"]]
    if not later:
        nxt = sorted([x for x in team.get("fixtures", []) if not x.get("ergebnis") and x.get("heim") and x["datum"] >= today
                      and "spielfrei" not in (x["heim"] + x["gast"]).lower()], key=lambda x: x["datum"])
        if nxt:
            n = nxt[0]
            h = norm(n["heim"]) == norm(team["name"])
            fx["naechstes_spiel"] = "%s, %s Uhr, %s %s" % (_datum_lang(n["datum"]), n.get("zeit") or "20:00",
                                                           "zu Hause gegen" if h else "auswärts bei", n["gast"] if h else n["heim"])
    return fx


def ki_pruefen(text, fx):
    """Gibt None zurück, wenn der Text in Ordnung ist, sonst den Grund der Ablehnung."""
    if not (60 <= len(text) <= 2600):
        return "Länge %d" % len(text)
    erlaubt = set(re.findall(r"\d+", json.dumps(fx, ensure_ascii=False)))
    erlaubt |= {str(i) for i in range(0, 32)}  # kleine Zahlen, Tage im Monat
    erlaubt |= {str(datetime.now(timezone.utc).year), str(datetime.now(timezone.utc).year - 1)}
    for z in re.findall(r"\d+", text):
        if z not in erlaubt:
            return "Zahl %s nicht in den Fakten" % z
    m, g = fx["ergebnis_aus_sicht_des_teams"].split(":")
    if not re.search(r"(?<!\d)%s\s*(?::|-|–|zu)\s*%s(?!\d)" % (m, g), text):
        return "Ergebnis %s:%s fehlt" % (m, g)
    return None


def ki_schreiben(fx, key):
    body = {"model": KI_MODELL, "max_tokens": 700, "system": KI_SYSTEM,
            "messages": [{"role": "user", "content": "Fakten (JSON):\n" + json.dumps(fx, ensure_ascii=False, indent=1) + (
                "" if "einzel" in fx else "\n\nHinweis: Es liegen nur wenige Fakten vor (kein Spielbericht). Schreibe deshalb nur eine "
                "Überschrift und einen kurzen Absatz mit 35 bis 60 Wörtern und füge nichts hinzu, was nicht im JSON steht.")}]}
    req = urllib.request.Request(KI_URL, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json", "User-Agent": "dc-phoenix-update"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.load(r)
    return "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text").strip()


def ki_berichte(cfg, teams, reports):
    """Gibt {spiel_id: text} zurück. Ohne Schlüssel/Supabase passiert nichts."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        return {}
    try:
        rows = _sb("GET", "/rest/v1/berichte?select=spiel_id,text") or []
    except Exception as e:  # noqa: BLE001
        print("KI-Berichte: Speicher nicht abrufbar (%s)" % type(e).__name__)
        return {}
    texte = {r["spiel_id"]: r["text"] for r in rows}
    limit = int(os.environ.get("KI_MAX_PRO_LAUF", "4"))
    neu = fehl = 0
    own_names = {norm(t["name"]) for t in cfg.get("teams", [])}
    for t in teams:
        for f in sorted(t.get("fixtures", []), key=lambda x: x["datum"], reverse=True):
            if neu >= limit:
                break
            if not f.get("ergebnis") or not f.get("id") or f["id"] in texte or not f.get("heim"):
                continue
            if "spielfrei" in (f["heim"] + f["gast"]).lower():
                continue
            fx = ki_fakten(f, t, reports.get(f["id"]), own_names)
            try:
                grund = None
                for _versuch in range(2):
                    text = ki_schreiben(fx, key)
                    grund = ki_pruefen(text, fx)
                    if not grund:
                        break
                if grund:
                    fehl += 1
                    print("KI-Bericht %s abgelehnt: %s" % (f["id"], grund))
                    continue
                _sb("POST", "/rest/v1/berichte", {"spiel_id": f["id"], "text": text, "modell": KI_MODELL},
                    prefer="resolution=ignore-duplicates,return=minimal")
                texte[f["id"]] = text
                neu += 1
                time.sleep(1)
            except Exception as e:  # noqa: BLE001
                fehl += 1
                print("KI-Bericht %s: %s %s" % (f["id"], type(e).__name__, str(e)[:200]))
    print("KI-Berichte: %d vorhanden, %d neu, %d abgelehnt oder fehlgeschlagen" % (len(texte), neu, fehl))
    return texte


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--data", default="data.json")
    ap.add_argument("--offline", help="Ordner mit Test-HTML statt Abruf von der BDL")
    args = ap.parse_args()

    write_photo_index()
    fetch_profiles()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    old = {}
    if os.path.exists(args.data):
        with open(args.data, encoding="utf-8") as f:
            old = json.load(f)
    old_teams = {norm(t["name"]): t for t in old.get("teams", [])}

    problems, notes, teams = [], [], []
    reports = dict(old.get("reports", {}))
    for t in cfg["teams"]:
        liga, name = t["liga"], t["name"]
        prev = old_teams.get(norm(name), {})
        entry = {"name": name, "liga": liga, "liga_name": t.get("liga_name", liga),
                 "table": prev.get("table", []), "fixtures": prev.get("fixtures", []),
                 "players": prev.get("players", [])}
        try:
            table = parse_table(load("leagueTable_%s.html" % liga, args.offline))
            if len(table) < 2:
                raise RuntimeError("Tabelle nicht gefunden")
            entry["table"] = table
        except Exception as e:  # noqa: BLE001
            problems.append("%s: Tabelle: %s" % (name, e))
        try:
            allfix = parse_fixtures(load("gameOverview_%s.html" % liga, args.offline), BASE + "gameOverview_%s.html" % liga)
            if not allfix:
                raise RuntimeError("Spielplan nicht gefunden")
            mine = [f for f in allfix if norm(name) in (norm(f["heim"]), norm(f["gast"]))]
            mine.sort(key=lambda f: (f["datum"], f["zeit"] or ""))
            for f in mine:
                f["id"] = "%s_%s_%s_%s" % (liga, f["datum"], slugify(f["heim"]), slugify(f["gast"]))
            entry["fixtures"] = mine
        except Exception as e:  # noqa: BLE001
            problems.append("%s: Spielplan: %s" % (name, e))
        try:
            players = parse_statistics(load("statistics_%s.html" % liga, args.offline), [name])
            if not players:
                raise RuntimeError("keine Spieler von %s gefunden" % name)
            entry["players"] = players
        except Exception as e:  # noqa: BLE001
            problems.append("%s: Spielerstatistik: %s" % (name, e))
        teams.append(entry)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        for f in entry["fixtures"]:
            url = f.get("bericht")
            if f.get("ergebnis") and not url:
                notes.append("Kein Bericht-Link: %s" % f.get("id"))
            if not url or not f.get("id") or not f.get("ergebnis"):
                continue
            recent = f["datum"] >= cutoff
            if f["id"] in reports and not recent and reports[f["id"]].get("v", 1) >= 2:
                continue
            try:
                rep_ = parse_report(load_url(url, args.offline))
                if not rep_:
                    raise RuntimeError("Bericht nicht erkannt")
                if len(rep_["spiele"]) != 12:
                    notes.append("Bericht %s hat %d statt 12 Spielen" % (f["id"], len(rep_["spiele"])))
                rep_["url"] = url
                rep_["datum"] = f["datum"]
                reports[f["id"]] = rep_
                time.sleep(1)
            except Exception as e:  # noqa: BLE001
                notes.append("Spielbericht %s: %s" % (f["id"], e))

    # Datensparsamkeit: Namen von Spielern anderer Vereine nicht veröffentlichen
    if not cfg.get("verein", {}).get("gegner_namen_zeigen", False):
        own_names = {norm(t["name"]) for t in cfg.get("teams", [])}
        for rep_ in reports.values():
            for side, key in (("heim", "heim"), ("gast", "gast")):
                if norm(rep_.get(side, "")) not in own_names:
                    for g in rep_.get("spiele", []):
                        g[key] = ["Gegner"] * max(1, len(g[key]))

    texte = ki_berichte(cfg, teams, reports)
    data = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "teams": teams, "reports": reports, "notes": notes[:30]}
    if texte:
        data["texte"] = texte
    with open(args.data, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    for p in problems:
        print("WARNUNG:", p, file=sys.stderr)
    for n in notes[:10]:
        print("HINWEIS:", n, file=sys.stderr)
    print("data.json geschrieben, %d Team(s)." % len(teams))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
