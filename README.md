# Vereinsseite DC Phönix Durmersheim

Eine einfache Webseite mit nächstem Spiel, Spielplan, Tabelle und Vereinsinfos.
Tabelle und Spielplan holt sich die Seite alle 6 Stunden und freitags abends alle 30 Minuten von der Badischen Dart Liga (BDL). Kosten: 0 €.

## Was in welcher Datei steht

| Datei | Wofür |
|---|---|
| `index.html` | Die Seite selbst |
| `config.json` | Deine Angaben: Teams, Training, Spiellokal, Kontakt, Instagram, Facebook, Logo |
| `data.json` | Tabelle und Spielplan (wird automatisch erneuert) |
| `update.py` | Holt die Daten von der BDL |
| `.github/workflows/seite.yml` | Der Zeitplan, der das Holen und Veröffentlichen anstößt |
| `logo.png` | Das Vereinslogo (legst du selbst dazu) |

## Einrichten (einmalig, am PC)

1. Konto auf github.com anlegen (kostenlos).
2. Neues Repository erstellen, Sichtbarkeit **Public**, Name zum Beispiel `dartclub-phoenix`.
3. Alle Dateien dieses Ordners hochladen, auch den Ordner `.github` (am PC per "Add file → Upload files" per Drag-and-drop, nicht am Handy).
4. Im Repository **Settings → Pages → Source: "GitHub Actions"** auswählen.
5. Reiter **Actions → "Daten aktualisieren und Seite veröffentlichen" → Run workflow**. Nach ein bis zwei Minuten ist die Seite online unter `https://DEIN-NAME.github.io/dartclub-phoenix/`.
6. Danach läuft alles von allein.

## Angaben eintragen

In `config.json` (Stift-Symbol auf GitHub):

- `spiellokal`, `kontakt`, `instagram`, `facebook` ausfüllen. Leere Felder zeigen auf der Seite "folgt".
- `logo`: Datei `logo.png` (oder `logo.svg`) ins Repository hochladen. Fehlt sie, zeigt die Seite nur den Vereinsnamen.
- **Zweites Team** hinzufügen, den Namen genau so schreiben wie in der BDL-Tabelle:

```json
{ "name": "Teamname wie bei der BDL", "liga": "kbz2", "liga_name": "Kreisbezirksliga 2" }
```

Die Liga-Kürzel stehen in den BDL-Adressen: `ol`, `bzo1`, `bzo2`, `bz1`, `bz2`, `kbz1` bis `kbz4`, `kl1` bis `kl7`, `sbl`.

- `"entwurf": false` setzen, sobald der Verein zugestimmt hat. Dann verschwindet der gelbe Hinweis oben.

## Bevor die Seite öffentlich wird

- Der Verein muss zustimmen, auch zur Nutzung von Namen und Logo.
- Ein **Impressum** und eine **Datenschutzerklärung** sind Pflicht. Die Adressen kommen in `config.json` bei `impressum` und `datenschutz`.
- Namen und Fotos von Mitgliedern nur mit deren Einverständnis.
- Die Seite nutzt absichtlich keine Google-Schriften, damit keine Daten an Google gehen.

## Wenn etwas nicht klappt

- **Actions zeigt ein rotes Kreuz:** Das Auslesen der BDL-Seite ist fehlgeschlagen. Die Seite bleibt online und zeigt die letzten Daten. Meist hat die BDL ihre Seite umgebaut, dann muss `update.py` angepasst werden.
- **Nach langer Pause hört die Aktualisierung auf:** GitHub schaltet Zeitpläne in Repositories ab, in denen 60 Tage nichts passiert. Im Reiter Actions den Workflow wieder aktivieren.
