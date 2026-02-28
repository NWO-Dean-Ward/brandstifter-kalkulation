"""
SQLite Datenbank-Schema und Verbindungsmanagement.

Tabellen:
- projekte: Alle Projekte/Ausschreibungen
- positionen: LV-Positionen pro Projekt
- materialpreise: Materialpreisliste mit Versionierung
- maschineneinsaetze: Maschinenbelegung pro Position
- lernhistorie: Abgeschlossene Projekte für den Lern-Agent
- konfiguration: Laufzeit-Konfigurationsänderungen
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

DB_PATH = Path("data/kalkulation.db")

SCHEMA_SQL = """
-- Projekte / Ausschreibungen
CREATE TABLE IF NOT EXISTS projekte (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    projekt_typ     TEXT NOT NULL DEFAULT 'standard',  -- standard | oeffentlich | privat
    status          TEXT NOT NULL DEFAULT 'entwurf',   -- entwurf | kalkuliert | angeboten | beauftragt | abgeschlossen | verloren
    kunde           TEXT DEFAULT '',
    beschreibung    TEXT DEFAULT '',
    datei_pfad      TEXT DEFAULT '',                    -- Original-Upload
    erstellt_am     TEXT NOT NULL,
    aktualisiert_am TEXT NOT NULL,
    deadline        TEXT DEFAULT '',
    angebotspreis   REAL DEFAULT 0,
    herstellkosten  REAL DEFAULT 0,
    marge_prozent   REAL DEFAULT 0
);

-- LV-Positionen pro Projekt
CREATE TABLE IF NOT EXISTS positionen (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projekt_id          TEXT NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    pos_nr              TEXT NOT NULL,
    kurztext            TEXT DEFAULT '',
    langtext            TEXT DEFAULT '',
    menge               REAL DEFAULT 0,
    einheit             TEXT DEFAULT 'STK',
    material            TEXT DEFAULT '',
    einheitspreis       REAL DEFAULT 0,
    gesamtpreis         REAL DEFAULT 0,
    materialkosten      REAL DEFAULT 0,
    maschinenkosten     REAL DEFAULT 0,
    lohnkosten          REAL DEFAULT 0,
    ist_lackierung      INTEGER DEFAULT 0,
    ist_fremdleistung   INTEGER DEFAULT 0,
    fremdleistungskosten REAL DEFAULT 0,
    sonderanforderungen TEXT DEFAULT '[]',  -- JSON Array
    platten_anzahl      REAL DEFAULT 0,
    kantenlaenge_lfm    REAL DEFAULT 0,
    schnittanzahl       INTEGER DEFAULT 0,
    bohrungen_anzahl    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_positionen_projekt ON positionen(projekt_id);

-- Materialpreisliste (versioniert)
CREATE TABLE IF NOT EXISTS materialpreise (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    material_name   TEXT NOT NULL,
    kategorie       TEXT DEFAULT '',      -- platte | kante | beschlag | mineralwerkstoff | sonstiges
    lieferant       TEXT DEFAULT '',
    artikel_nr      TEXT DEFAULT '',
    einheit         TEXT DEFAULT 'STK',
    preis           REAL NOT NULL,
    gueltig_ab      TEXT NOT NULL,
    gueltig_bis     TEXT DEFAULT '',      -- leer = aktuell gültig
    notizen         TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_materialpreise_name ON materialpreise(material_name);
CREATE INDEX IF NOT EXISTS idx_materialpreise_kategorie ON materialpreise(kategorie);

-- Maschineneinsätze pro Position
CREATE TABLE IF NOT EXISTS maschineneinsaetze (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    projekt_id      TEXT NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    position_id     INTEGER REFERENCES positionen(id) ON DELETE CASCADE,
    maschine        TEXT NOT NULL,       -- holzher_nextec_7707 | kantenanleimmaschine | ...
    stunden         REAL DEFAULT 0,
    stundensatz     REAL DEFAULT 0,
    kosten          REAL DEFAULT 0,
    details         TEXT DEFAULT '{}'    -- JSON mit Zusatzinfos
);

CREATE INDEX IF NOT EXISTS idx_maschineneinsaetze_projekt ON maschineneinsaetze(projekt_id);

-- Lernhistorie: Abgeschlossene Projekte für KI-Vorschläge
CREATE TABLE IF NOT EXISTS lernhistorie (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projekt_id          TEXT NOT NULL,
    position_typ        TEXT DEFAULT '',       -- z.B. "Küchenfront", "Einbauschrank"
    material            TEXT DEFAULT '',
    menge               REAL DEFAULT 0,
    kalkulierter_preis  REAL DEFAULT 0,
    tatsaechlicher_preis REAL DEFAULT 0,
    abweichung_prozent  REAL DEFAULT 0,
    ergebnis            TEXT DEFAULT '',       -- gewonnen | verloren | beauftragt
    erfasst_am          TEXT NOT NULL,
    notizen             TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_lernhistorie_typ ON lernhistorie(position_typ);

-- Konfigurationsänderungen (Audit-Trail)
CREATE TABLE IF NOT EXISTS konfiguration_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    schluessel      TEXT NOT NULL,
    alter_wert      TEXT DEFAULT '',
    neuer_wert      TEXT NOT NULL,
    geaendert_am    TEXT NOT NULL,
    geaendert_von   TEXT DEFAULT 'system'
);

-- Werkstuecke (Einzelbauteile pro Position)
CREATE TABLE IF NOT EXISTS werkstuecke (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    projekt_id      TEXT NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    position_id     INTEGER REFERENCES positionen(id) ON DELETE CASCADE,
    bezeichnung     TEXT NOT NULL DEFAULT '',
    anzahl          INTEGER DEFAULT 1,
    laenge_mm       REAL DEFAULT 0,
    breite_mm       REAL DEFAULT 0,
    tiefe_mm        REAL DEFAULT 0,
    staerke_mm      REAL DEFAULT 0,
    material        TEXT DEFAULT '',         -- Spanplatte | MDF | Multiplex | Massivholz | Mineralwerkstoff | Sonstige
    oberflaeche     TEXT DEFAULT '',         -- Melamin | Folie | Echtholzfurnier | Mineralwerkstoff | Lackiert-extern
    fertigung       TEXT DEFAULT 'cnc',      -- cnc-nesting | handfertigung | zukauf
    ist_fremdleistung INTEGER DEFAULT 0,     -- auto bei Lackiert-extern
    hop_datei       TEXT DEFAULT '',          -- Referenz auf HOP-Datei
    notizen         TEXT DEFAULT '',
    erstellt_am     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_werkstuecke_position ON werkstuecke(position_id);
CREATE INDEX IF NOT EXISTS idx_werkstuecke_projekt ON werkstuecke(projekt_id);

-- Zukaufteile (eingekaufte Teile pro Projekt)
CREATE TABLE IF NOT EXISTS zukaufteile (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    projekt_id      TEXT NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    position_id     INTEGER REFERENCES positionen(id) ON DELETE SET NULL,
    bezeichnung     TEXT NOT NULL DEFAULT '',
    hersteller      TEXT DEFAULT '',
    produkt         TEXT DEFAULT '',
    artikel_nr      TEXT DEFAULT '',
    produkt_link    TEXT DEFAULT '',         -- URL zur Produktseite
    einkaufspreis   REAL DEFAULT 0,          -- netto
    menge           REAL DEFAULT 1,
    aufschlag_prozent REAL DEFAULT 15.0,     -- konfigurierbarer Aufschlag
    verkaufspreis   REAL DEFAULT 0,          -- automatisch berechnet
    status          TEXT DEFAULT 'ausstehend', -- ausstehend | angefragt | bestellt | geliefert
    quelle          TEXT DEFAULT '',         -- haefele | blum | egger | amazon | manuell
    alternativ_json TEXT DEFAULT '[]',       -- JSON: Alternativanbieter
    erstellt_am     TEXT NOT NULL,
    aktualisiert_am TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_zukaufteile_projekt ON zukaufteile(projekt_id);

-- Manuelle Ueberschreibungen (Audit-Trail pro Position)
CREATE TABLE IF NOT EXISTS manuelle_ueberschreibungen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    projekt_id      TEXT NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    position_id     INTEGER NOT NULL REFERENCES positionen(id) ON DELETE CASCADE,
    feld            TEXT NOT NULL,           -- z.B. 'einheitspreis', 'materialkosten', 'lohnkosten'
    alter_wert      REAL DEFAULT 0,
    neuer_wert      REAL NOT NULL,
    begruendung     TEXT NOT NULL DEFAULT '', -- Pflichtfeld: z.B. 'Kundenrabatt', 'Altpreis'
    geaendert_am    TEXT NOT NULL,
    geaendert_von   TEXT DEFAULT 'dean'
);

CREATE INDEX IF NOT EXISTS idx_ueberschreibungen_position ON manuelle_ueberschreibungen(position_id);

-- Altprojekt-Analysen (extrahierte Daten aus historischen Projekten)
CREATE TABLE IF NOT EXISTS altprojekt_analysen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    projekt_name    TEXT NOT NULL,
    quell_pfad      TEXT NOT NULL,           -- Pfad zum Altprojekt-Ordner
    analyse_datum   TEXT NOT NULL,
    positionen_json TEXT DEFAULT '[]',       -- JSON: extrahierte Positionen mit Preisen
    materialien_json TEXT DEFAULT '[]',      -- JSON: erkannte Materialien + Preise
    maschinen_json  TEXT DEFAULT '[]',       -- JSON: Maschinenzeiten
    stundensaetze_json TEXT DEFAULT '{}',    -- JSON: extrahierte Stundensaetze
    inflationsfaktor REAL DEFAULT 1.0,       -- Berechneter Aufschlag seit Projektdatum
    projekt_datum   TEXT DEFAULT '',          -- Wann war das Altprojekt
    notizen         TEXT DEFAULT '',
    status          TEXT DEFAULT 'analysiert' -- analysiert | importiert | verworfen
);
"""


async def init_db(db_path: Path | None = None) -> None:
    """Erstellt die Datenbank und alle Tabellen."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(path)) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


@asynccontextmanager
async def get_db(db_path: Path | None = None) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async Context Manager für Datenbankverbindungen."""
    path = db_path or DB_PATH
    async with aiosqlite.connect(str(path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        yield db


def init_db_sync(db_path: Path | None = None) -> None:
    """Synchrone DB-Initialisierung (für Tests und Startup)."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
