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
- LLM: Ollama lokal (gpt-oss:20b, deepseek-coder, qwen2.5-coder:14b)
- Sprache: Deutsch (UI komplett)

## Architektur
Agenten-basiert: LeadAgent orchestriert 9 Subagenten (DokumentParser, MaterialKalkulator, MaschinenKalkulator, LohnKalkulator, ZuschlagKalkulator, ExportAgent, LernAgent, CNCIntegration, SchreinersBueroAgent). Kommunikation über AgentMessage-Protokoll.

## Wichtige Regeln
- Lackierung = immer Fremdleistung mit konfigurierbarem Aufschlag
- CNC: Holzher Nextec 7707, 13 Platten/Schicht (hochwertig), 20/Schicht (standard)
- 7 Monteure verfügbar, Warnung bei Überschreitung
- Alle Daten bleiben lokal, kein Cloud-Zwang
- Offline-Kernfunktionen müssen ohne Internet funktionieren
- Config in YAML-Dateien (config/)

## Verzeichnisstruktur
- agents/ – Business-Agenten (Python)
- api/ – FastAPI Backend
- frontend/ – React App
- config/ – YAML-Konfiguration
- data/ – Preislisten, Projekte, SQLite DB, SB-Austausch (sb_import/, sb_export/)
- exports/ – Generierte Dateien (exports/cnc/ fuer HOP/Stuecklisten)
- tests/ – Tests

## Entwicklungshinweise
- venv aktivieren: `.venv/Scripts/python.exe` direkt nutzen (source activate funktioniert nicht in dieser Shell)
- Tests: `.venv/Scripts/python.exe -m pytest tests/ -v`
- Server: `.venv/Scripts/python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8080`
- Export-Cache: Kalkulation muss vor Export laufen (cache_kalkulation() in kalkulation.py)
- Positions-Kosten: Kalkulations-Route schreibt EP/GP/Material/Maschinen/Lohn pro Position in DB zurueck
- GAEB-Parser: Namespace-aware, collect_spans() für verschachtelte <span> Elemente
- LLM-Router: qwen2.5-coder:14b primaer, gpt-oss:20b fuer Rechenlogik, Claude API fuer Lead/Lern
- Frontend Dev: `cd frontend && npx vite` (Port 5173, Proxy auf 8080)
- Windows: Keine Unicode-Sonderzeichen in Print-Ausgaben (cp1252)
- CNC: nc-hops Paket (ReadHop.ExtractHopProcessing, WriteHop.WriteHop) - Import: `import WriteHop as WriteHopModule`
- CNC WriteHop.drilling.vertical(x, y, diameter, depth, cycle) - Reihenfolge beachten
- Stuecklisten-CSV: UTF-8-BOM (utf-8-sig) fuer Excel, Semikolon-getrennt
- SB-CSV: ISO-8859-1 Encoding, Semikolon-getrennt, deutsches Zahlenformat (Komma als Dezimaltrenner)
- SB API: http://192.168.51.85/sb/proc/sb.php (PHP/MySQL, LAN), auto CSV-Fallback bei Offline
- FastAPI Form-Parameter bei Multipart-Upload: `Form()` verwenden, nicht bare `str`

## Phasen
0. Agenten-Architektur ✓
1. Tech-Stack Setup + DB-Schema + API-Routes ✓
2. Kalkulationslogik (Material/Maschinen/Lohn/Zuschlag) ✓
3. GAEB-Parser + Export-Agent (PDF/Excel/GAEB) ✓
4. Frontend (React+Tailwind) ✓, Lern-Agent (Memory Layer) ✓, LLM-Router (qwen2.5-coder:14b) ✓
5. SmartWOP/NCHops CNC-Integration ✓ (HOP/MPR Parse, HOP-Export, Stueckliste, Nesting, Zeitberechnung)
6. Schreiner's Buero ERP-Anbindung ✓ (Auftraege, Stuecklisten, Kunden, Materialpreise, CSV Import/Export)
