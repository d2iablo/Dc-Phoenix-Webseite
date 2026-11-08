#!/usr/bin/env python3
"""Schickt Spielern vor ihrem nächsten Spiel eine Erinnerungs-Mail (Datum, Uhrzeit, Ort, Navigation).

Läuft täglich als GitHub Action. Nur Standardbibliothek.
Geheime Werte kommen aus GitHub-Secrets (Umgebungsvariablen), nie in den Code:
  SUPABASE_URL, SUPABASE_SERVICE_KEY, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM, SITE_URL
Im Protokoll (öffentlich sichtbar!) stehen nur Zählwerte, nie Namen oder Adressen.
"""
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def clean(s):
    """Keine Zeilenumbrüche in Kopfzeilen (Schutz vor Header-Injection)."""
    return re.sub(r"[\r\n]+", " ", str(s or "")).strip()


def http_json(url, headers=None, data=None, method=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {}, method=method,
                                 data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return json.loads(body) if body else None


def sb_headers(key, extra=None):
    h = {"apikey": key, "Authorization": "Bearer " + key, "Accept": "application/json",
         "Content-Type": "application/json", "User-Agent": "dc-phoenix-erinnerung"}
    h.update(extra or {})
    return h


def venue(cfg, f):
    k = norm(f.get("heim"))
    for n, a in (cfg.get("spielorte") or {}).items():
        if norm(n) == k:
            return a
    if any(norm(t["name"]) == k for t in cfg["teams"]):
        return cfg["verein"].get("spiellokal", "")
    return ""


def ics(f, ort, titel, beschr):
    y, m, d = map(int, f["datum"].split("-"))
    hh, mm = map(int, (f.get("zeit") or "20:00").split(":"))
    start = datetime(y, m, d, hh, mm, tzinfo=TZ)
    ende = start + timedelta(hours=3)
    z = lambda x: x.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    esc = lambda s: str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DC Phoenix Durmersheim//Erinnerung//DE", "METHOD:PUBLISH",
             "BEGIN:VEVENT", "UID:%s-%s@dc-phoenix" % (f["datum"], re.sub(r"\W+", "", norm(f.get("heim")))),
             "DTSTAMP:" + z(datetime.now(TZ)), "DTSTART:" + z(start), "DTEND:" + z(ende), "SUMMARY:" + esc(titel)]
    if ort:
        lines.append("LOCATION:" + esc(ort))
    lines += ["DESCRIPTION:" + esc(beschr), "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def baue_mail(cfg, site, absender, an, team, f, tage):
    verein = cfg["verein"]["name"]
    ort = venue(cfg, f)
    heim = norm(f["heim"]) == norm(team["name"])
    gegner = f["gast"] if heim else f["heim"]
    y, m, d = map(int, f["datum"].split("-"))
    dt = date(y, m, d)
    zeit = f.get("zeit") or "20:00"
    wann = "%s, %02d.%02d.%d um %s Uhr" % (WOCHENTAGE[dt.weekday()], d, m, y, zeit)
    kurz = re.sub(r"^DC Phönix\s*", "", team["name"]) or team["name"]
    vorlauf = "morgen" if tage == 1 else "in %d Tagen" % tage
    betreff = "Dart %s: %s gegen %s (%02d.%02d.)" % (vorlauf, kurz, gegner, d, m)
    q = urllib.parse.quote(ort) if ort else ""
    gmaps = "https://www.google.com/maps/dir/?api=1&destination=" + q if ort else ""
    amaps = "https://maps.apple.com/?daddr=%s&dirflg=d" % q if ort else ""
    team_url = site.rstrip("/") + "/#" + re.sub(r"[^a-z0-9]+", "-", norm(kurz)).strip("-")
    profil_url = site.rstrip("/") + "/profil.html"

    text = [
        "Hallo,", "",
        "dein nächstes Spiel mit %s:" % team["name"], "",
        "Wann:   " + wann,
        "Gegner: %s (%s)" % (gegner, "Heimspiel" if heim else "Auswärtsspiel"),
    ]
    if ort:
        text += ["Wo:     " + ort, "", "Navigation:", "Google Maps: " + gmaps, "Apple Karten: " + amaps]
    text += ["", "Spielplan und Tabelle: " + team_url, "",
             "Du bekommst diese Mail, weil du bei %s ein Spielerkonto hast." % verein,
             "Einstellen oder abbestellen kannst du sie in deinem Profil: " + profil_url]

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    knoepfe = ""
    if ort:
        knoepfe = ('<p style="margin:18px 0"><a href="%s" style="background:#111;color:#fff;padding:12px 18px;border-radius:999px;text-decoration:none;font-weight:700">Google Maps</a>&nbsp; '
                   '<a href="%s" style="background:#111;color:#fff;padding:12px 18px;border-radius:999px;text-decoration:none;font-weight:700">Apple Karten</a></p>') % (esc(gmaps), esc(amaps))
    html = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;color:#111;max-width:520px">'
            '<p>Hallo,</p><p>dein nächstes Spiel mit <b>%s</b>:</p>'
            '<table style="border-collapse:collapse"><tr><td style="padding:4px 14px 4px 0;color:#666">Wann</td><td><b>%s</b></td></tr>'
            '<tr><td style="padding:4px 14px 4px 0;color:#666">Gegner</td><td><b>%s</b> (%s)</td></tr>%s</table>%s'
            '<p><a href="%s">Spielplan und Tabelle</a></p>'
            '<p style="color:#666;font-size:13px">Du bekommst diese Mail, weil du bei %s ein Spielerkonto hast. '
            '<a href="%s">Erinnerungen einstellen oder abbestellen</a></p></div>') % (
        esc(team["name"]), esc(wann), esc(gegner), "Heimspiel" if heim else "Auswärtsspiel",
        ('<tr><td style="padding:4px 14px 4px 0;color:#666">Wo</td><td><b>%s</b></td></tr>' % esc(ort)) if ort else "",
        knoepfe, esc(team_url), esc(verein), esc(profil_url))

    msg = EmailMessage()
    msg["Subject"] = clean(betreff)
    msg["From"] = absender
    msg["To"] = clean(an)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=absender.split("@")[-1].strip("> "))
    msg["List-Unsubscribe"] = "<%s>" % profil_url
    msg.set_content("\n".join(text))
    msg.add_alternative(html, subtype="html")
    titel = "Dart: %s – %s" % (f["heim"], f["gast"])
    msg.add_attachment(ics(f, ort, titel, team["name"]).encode("utf-8"), maintype="text", subtype="calendar",
                       filename="spiel-%s.ics" % f["datum"], params={"charset": "utf-8", "method": "PUBLISH"})
    return msg


def smtp_senden(msgs):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 465)
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASS", "")
    modus = (os.environ.get("SMTP_MODE") or ("ssl" if port == 465 else "starttls")).lower()
    ctx = ssl.create_default_context()  # prüft Zertifikat und Hostnamen
    if modus == "ssl":
        s = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        s = smtplib.SMTP(host, port, timeout=30)
        s.ehlo()
        if modus == "starttls":
            s.starttls(context=ctx)
            s.ehlo()
        elif host not in ("localhost", "127.0.0.1"):
            raise RuntimeError("Unverschlüsselter Versand ist nur für localhost erlaubt")
    return s, user, pw


def main():
    tage_liste = (1, 3)
    cfg = json.load(open("config.json", encoding="utf-8"))
    site = os.environ.get("SITE_URL", "").strip()
    sb = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    absender = os.environ.get("MAIL_FROM", "").strip()
    if not (site and sb and key and absender and os.environ.get("SMTP_HOST")):
        print("Es fehlen Einstellungen (SITE_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY, MAIL_FROM, SMTP_HOST). Abbruch.")
        return 1
    if not sb.startswith("https://") and "127.0.0.1" not in sb and "localhost" not in sb:
        print("SUPABASE_URL muss mit https:// beginnen")
        return 1

    heute = datetime.now(TZ).date()
    if os.environ.get("TEST_HEUTE"):
        heute = date.fromisoformat(os.environ["TEST_HEUTE"])
    data = http_json(site.rstrip("/") + "/data.json", {"User-Agent": "dc-phoenix-erinnerung", "Cache-Control": "no-cache"})

    # Spiele der nächsten 1 und 3 Tage je Team
    anstehend = []  # (tage, team_cfg, fixture, spieler_normiert_liste)
    for t in data["teams"]:
        namen = {norm(p["name"]) for p in t.get("players", [])}
        for f in t.get("fixtures", []):
            if f.get("ergebnis") or not f.get("heim") or "spielfrei" in (f["heim"] + f["gast"]).lower():
                continue
            try:
                d = date.fromisoformat(f["datum"])
            except Exception:
                continue
            tage = (d - heute).days
            if tage in tage_liste:
                anstehend.append((tage, t, f, namen))
    print("Spiele in 1 oder 3 Tagen: %d" % len(anstehend))
    if not anstehend:
        return 0

    profile = http_json(sb + "/rest/v1/profiles?select=id,email,spielername,erinnerung&muss_passwort_aendern=eq.false&erinnerung=neq.keine",
                        sb_headers(key)) or []
    print("Konten mit Erinnerung: %d" % len(profile))

    offen = []
    for tage, t, f, namen in anstehend:
        for p in profile:
            if not p.get("email") or norm(p["spielername"]) not in namen:
                continue
            wahl = p["erinnerung"]
            if (wahl == "1" and tage == 1) or (wahl == "3" and tage == 3) or wahl == "beide":
                offen.append((p, t, f, tage))
    print("Zu verschicken: %d" % len(offen))
    if not offen:
        return 0

    s, user, pw = smtp_senden(None)
    gesendet = fehler = 0
    try:
        if user:
            s.login(user, pw)
        for p, t, f, tage in offen:
            spiel = "%s|%s" % (f["datum"], norm(f["heim"]))
            art = "t%d" % tage
            try:   # zuerst im Protokoll reservieren; Doppeltes wird abgelehnt (409)
                http_json(sb + "/rest/v1/mail_log", sb_headers(key, {"Prefer": "return=minimal"}), method="POST",
                          data={"user_id": p["id"], "spiel": spiel, "art": art})
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    continue
                raise
            try:
                s.send_message(baue_mail(cfg, site, absender, p["email"], t, f, tage))
                gesendet += 1
            except Exception as e:  # noqa: BLE001
                fehler += 1
                print("Versand fehlgeschlagen (%s)" % type(e).__name__)
                try:
                    http_json(sb + "/rest/v1/mail_log?user_id=eq.%s&spiel=eq.%s&art=eq.%s" % (
                        p["id"], urllib.parse.quote(spiel, safe=""), art), sb_headers(key), method="DELETE")
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(float(os.environ.get("MAIL_PAUSE", "1")))
    finally:
        try:
            s.quit()
        except Exception:  # noqa: BLE001
            pass
    print("Gesendet: %d, Fehler: %d" % (gesendet, fehler))
    return 1 if fehler and not gesendet else 0


if __name__ == "__main__":
    sys.exit(main())
