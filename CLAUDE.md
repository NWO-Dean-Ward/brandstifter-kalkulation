# Brandstifter Kalkulationstool

## Projekt
Ausschreibungs- & Kalkulationssoftware für AMP & Brandstifter GmbH (Schreinerei, Ober-Mörlen).

## Stack
- Backend: Python 3.12 / FastAPI / uvicorn
- Frontend: React + Tailwind CSS + React Router (Vite)
- Datenbank: SQLite (aiosqlite async + sqlite3 sync)
- GAEB: lxml (XML-Parser mit Namespace-Handling)
- PDF: ReportLab
- Excel: openpyxl
- Browser-Automation: Playwright (Einkaufs-Agent)
- Verschluesselung: cryptography/Fernet (Partner-Logins)
- LLM: Ollama lokal (gpt-oss:20b, deepseek-coder, qwen2.5-coder:14b)
- Sprache: Deutsch (UI komplett)

## Architektur
Agenten-basiert: LeadAgent orchestriert 12 Subagenten. Kommunikation über AgentMessage-Protokoll.

### Subagenten
1. DokumentParser – GAEB/PDF/Excel Parsing
2. MaterialKalkulator – Materialpreise aus DB
3. MaschinenKalkulator – CNC-Zeiten + Kosten
4. LohnKalkulator – Lohnkosten + Montage
5. ZuschlagKalkulator – GKZ/Gewinn/Wagnis/FL-Zuschlaege
6. ExportAgent – PDF/Excel/GAEB/SB-Export
7. LernAgent – Memory Layer aus Altprojekten
8. CNCIntegration – SmartWOP/NCHops HOP/MPR
9. SchreinersBueroAgent – ERP-Anbindung (CSV/API)
10. AnalyseAgent – Altprojekt-Analyse (Excel/GAEB/Smartwop-CSV, Egger-Dekore, Inflation)
11. EinkaufsAgent – Playwright-Preisrecherche (Haefele/Blum/Egger/Amazon/Google Shopping)
12. HolzTuscheAgent – B2B-Preissync bei Holz-Tusche (Playwright-Login, Shopware)

## Wichtige Regeln
- Lackierung = immer Fremdleistung mit konfigurierbarem Aufschlag
- CNC: Holzher Nextec 7707, 13 Platten/Schicht (hochwertig), 20/Schicht (standard)
- 7 Monteure verfügbar, Warnung bei Überschreitung
- Alle Daten bleiben lokal, kein Cloud-Zwang
- Offline-Kernfunktionen müssen ohne Internet funktionieren
- Config in YAML-Dateien (config/)
- Partner-Logins: Fernet-verschluesselt in config/partner-logins.yaml, Key in config/.secret_key
- EinkaufsAgent kauft NIEMALS automatisch ein – nur Recherche
- Manuelle Ueberschreibungen: Pflicht-Begruendung, Audit-Trail
- Smartwop-CSV Material-Codes = Egger-Dekornummern (W1000=Premium Weiss, H1345=Eiche Sherman natur)

## DB-Tabellen
projekte, positionen, materialpreise, maschineneinsaetze, lernhistorie, konfiguration_log, werkstuecke, zukaufteile, manuelle_ueberschreibungen, altprojekt_analysen

## API-Routes
- /api/projekte/ – CRUD Projekte
- /api/projekte/{id}/positionen/ – CRUD + PATCH Positionen
- /api/projekte/{id}/werkstuecke/ – CRUD Werkstuecke (Einzelbauteile)
- /api/projekte/{id}/zukaufteile/ – CRUD Zukaufteile (auto VK-Berechnung)
- /api/projekte/{id}/ueberschreibungen/ – Manuelle Wert-Aenderungen mit Audit
- /api/kalkulation/ – Upload + Kalkulation starten
- /api/export/ – PDF/Excel/GAEB/Alle
- /api/config/ – Maschinen/Zuschlaege/Stundensaetze
- /api/materialpreise/ – CRUD + Import
- /api/lernen/ – Lern-Agent Statistik/Vorschlaege
- /api/cnc/ – HOP/MPR Parse, HOP-Export, Stueckliste, Nesting
- /api/schreiners-buero/ – ERP CSV/API
- /api/analyse/ – Altprojekt-Scan/Excel/GAEB/Smartwop/Komplett/Inflation/Historie
- /api/einkauf/ – Preisrecherche (Einzel/Batch/Haefele/Amazon/Google/Speichern/Holz-Tusche/Sync)

## Verzeichnisstruktur
- agents/ – 11 Business-Agenten (Python)
- api/ – FastAPI Backend (routes/, models/)
- frontend/ – React App (pages: Dashboard, Ausschreibung, Projekt, Einstellungen, Werkzeuge)
- config/ – YAML-Konfiguration + .secret_key + partner-logins.yaml
- data/ – Preislisten, Projekte, SQLite DB, SB-Austausch (sb_import/, sb_export/)
- exports/ – Generierte Dateien (exports/cnc/ fuer HOP/Stuecklisten)
- tests/ – 74 Tests (test_erweiterung.py = 24 Tests fuer Erweiterung)

## Entwicklungshinweise
- venv aktivieren: `.venv/Scripts/python.exe` direkt nutzen (source activate funktioniert nicht in dieser Shell)
- Tests: `.venv/Scripts/python.exe -m pytest tests/ -v`
- Server: `.venv/Scripts/python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8080`
- Export-Cache: Rekonstruiert aus DB bei Cache-Miss (nach Server-Neustart)
- Positions-Kosten: Kalkulations-Route schreibt EP/GP/Material/Maschinen/Lohn pro Position in DB zurueck
- GAEB-Parser: Namespace-aware, collect_spans() für verschachtelte <span> Elemente
- LLM-Router: qwen2.5-coder:14b primaer, gpt-oss:20b fuer Rechenlogik, Claude API fuer Lead/Lern
- Frontend Dev: `cd frontend && npx vite` (Port 5173, Proxy auf 8080)
- Frontend Projekt.jsx: 4 Tabs (Positionen, Werkstuecke, Zukaufteile, Nachkalkulation), Status-Dropdown, Inline-Edit per Doppelklick, Projekt-Kopieren
- Frontend Dashboard: Status-Filter-Buttons, Kopieren-Button pro Projekt, Status "verloren"
- Projekt-Kopieren: POST /api/projekte/{id}/kopieren - dupliziert Projekt inkl. Positionen
- Windows: Keine Unicode-Sonderzeichen in Print-Ausgaben (cp1252)
- CNC: nc-hops Paket (ReadHop.ExtractHopProcessing, WriteHop.WriteHop) - Import: `import WriteHop as WriteHopModule`
- CNC WriteHop.drilling.vertical(x, y, diameter, depth, cycle) - Reihenfolge beachten
- Stuecklisten-CSV: UTF-8-BOM (utf-8-sig) fuer Excel, Semikolon-getrennt
- SB-CSV: ISO-8859-1 Encoding, Semikolon-getrennt, deutsches Zahlenformat (Komma als Dezimaltrenner)
- SB API: http://192.168.51.85/sb/proc/sb.php (PHP/MySQL, LAN), auto CSV-Fallback bei Offline
- FastAPI Form-Parameter bei Multipart-Upload: `Form()` verwenden, nicht bare `str`
- Upload-Limit: 50MB auf allen Upload-Endpoints
- FK-Enforcement: PRAGMA foreign_keys = ON in get_db() und init_db_sync()
- Playwright: `pip install playwright && playwright install chromium` (einmalig)
- Egger-Dekore: 100+ Dekore in agents/analyse_agent.py EGGER_DEKORE dict

## Phasen
0. Agenten-Architektur ✓
1. Tech-Stack Setup + DB-Schema + API-Routes ✓
2. Kalkulationslogik (Material/Maschinen/Lohn/Zuschlag) ✓
3. GAEB-Parser + Export-Agent (PDF/Excel/GAEB) ✓
4. Frontend (React+Tailwind) ✓, Lern-Agent (Memory Layer) ✓, LLM-Router (qwen2.5-coder:14b) ✓
5. SmartWOP/NCHops CNC-Integration ✓ (HOP/MPR Parse, HOP-Export, Stueckliste, Nesting, Zeitberechnung)
6. Schreiner's Buero ERP-Anbindung ✓ (Auftraege, Stuecklisten, Kunden, Materialpreise, CSV Import/Export)
7. Erweiterung ✓ (Werkstuecke, Zukaufteile, Ueberschreibungen, AnalyseAgent, EinkaufsAgent, Egger-Mapping, Fernet, Tab-Frontend)
