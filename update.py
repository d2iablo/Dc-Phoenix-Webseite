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
from datetime import datetime, timezone
from html.parser import HTMLParser

BASE = "https://www.badischedartliga.de/results/"
UA = "Mozilla/5.0 (compatible; Vereinsseite/1.0)"


def clean(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def norm(s):
    return clean(s or "").casefold()


class Collector(HTMLParser):
    """Sammelt Text und Tabellen in der Reihenfolge, in der sie im HTML stehen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
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
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(clean("".join(self._cell)))
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


def collect(html):
    c = Collector()
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


def parse_fixtures(html):
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
            fixtures.append({
                "spieltag": spieltag,
                "runde": runde,
                "datum": "%04d-%02d-%02d" % (y, mo, d),
                "zeit": zeit,
                "heim": row[col["heim"]],
                "gast": row[col["gast"]],
                "ergebnis": [int(sc.group(1)), int(sc.group(2))] if sc else None,
            })
    return fixtures


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


def load(name, offline):
    if offline:
        with open(os.path.join(offline, name), encoding="utf-8") as f:
            return f.read()
    return fetch(BASE + name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--data", default="data.json")
    ap.add_argument("--offline", help="Ordner mit Test-HTML statt Abruf von der BDL")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    old = {}
    if os.path.exists(args.data):
        with open(args.data, encoding="utf-8") as f:
            old = json.load(f)
    old_teams = {norm(t["name"]): t for t in old.get("teams", [])}

    problems, teams = [], []
    for t in cfg["teams"]:
        liga, name = t["liga"], t["name"]
        prev = old_teams.get(norm(name), {})
        entry = {"name": name, "liga": liga, "liga_name": t.get("liga_name", liga),
                 "table": prev.get("table", []), "fixtures": prev.get("fixtures", [])}
        try:
            table = parse_table(load("leagueTable_%s.html" % liga, args.offline))
            if len(table) < 2:
                raise RuntimeError("Tabelle nicht gefunden")
            entry["table"] = table
        except Exception as e:  # noqa: BLE001
            problems.append("%s: Tabelle: %s" % (name, e))
        try:
            allfix = parse_fixtures(load("gameOverview_%s.html" % liga, args.offline))
            if not allfix:
                raise RuntimeError("Spielplan nicht gefunden")
            mine = [f for f in allfix if norm(name) in (norm(f["heim"]), norm(f["gast"]))]
            mine.sort(key=lambda f: (f["datum"], f["zeit"] or ""))
            entry["fixtures"] = mine
        except Exception as e:  # noqa: BLE001
            problems.append("%s: Spielplan: %s" % (name, e))
        teams.append(entry)

    data = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "teams": teams}
    with open(args.data, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    for p in problems:
        print("WARNUNG:", p, file=sys.stderr)
    print("data.json geschrieben, %d Team(s)." % len(teams))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
