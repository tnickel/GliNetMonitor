# GL.iNet Gateway Network Monitor 🌐

![GL.iNet Gateway Network Monitor Banner](assets/hero.jpg)

Ein moderner Echtzeit-Monitor für das GL.iNet Sicherheits-Gateway (GL-MT2500 / Brume 2), der für **jeden Rechner und jedes Mobilgerät im Netzwerk die aufgerufenen Webadressen (Domains) und deren exakte Häufigkeit** anzeigt.

---

## 🚀 Features

- **Rechner- & Geräte-Erkennung:** Automatische Auflösung aller IP-Adressen, rDNS-Hostnamen (z. B. `Ryzen7950X`, `Redmi-Note-14`, `homey`, `HUAWEI-P30-lite`) und Gerätetypen.
- **Detaillierte Webadressen-Statistik pro Rechner:**
  - Jede aufgerufene Domain mit exakter Aufruf-Anzahl
  - Prozentualer Anteil am Datenverkehr des jeweiligen Rechners
  - Zuletzt aufgerufen (mit Relativ- und Absolutzeit)
  - Status (Erlaubt / Durch Filterliste blockiert)
  - Schnellsuchfeld und Sortierung (nach Häufigkeit, Aktualität, Alphabet)
- **Netzwerkweite Top-Domains:** Meistbesuchte Adressen über alle Geräte hinweg mit Angabe, wie viele und welche Rechner darauf zugreifen.
- **Live-Stream (Echtzeit-Ticker):** Live-Feed jeder einzelnen DNS-Anfrage im Sekundentakt mit Latenz, Query-Typ (A, AAAA, HTTPS) und Client.
- **24-Stunden-Aktivitätsverlauf:** Interaktives Diagramm mit Anfragenvolumen und aktiven Rechnern über den Tagesverlauf.
- **Permanenter SQLite-Speicher:** Alle Daten werden lokal in `glinet_monitor.db` persistiert – keine Daten gehen verloren, wenn der Router-Buffer überläuft.
- **Automatischer Background-Collector:** Pollt das Gateway alle 5 Sekunden und füllt beim Start bestehende Verläufe automatisch auf.

---

## 🛠️ Architektur & Gateway-Anbindung

Das Tool verbindet sich direkt mit dem **GL.iNet Gateway (`192.168.178.93`)**:
1. **Challenge-Response Authentifizierung:** Führt den herstellerspezifischen GL-Session RPC-Handshake (`challenge` -> Salted SHA256 Hash -> `login`) durch und bezieht ein valides Admin-Sitzungstoken (`Admin-Token`).
2. **AdGuard Home Core API:** Liest über den internen Nginx-Reverse-Proxy des Gateways die Schnittstellen `/control/clients`, `/control/stats` und `/control/querylog` aus.
3. **Persistierung:** Der `DataCollector` dedupliziert die Anfragen und pflegt in SQLite aggregierte Tabellen für blitzschnelle Auswertungen.

---

## 📦 Starten

Doppelklick auf `start.bat` oder im Terminal:

```powershell
python main.py
```

Das Dashboard öffnet sich unter:
👉 **http://localhost:8080**
