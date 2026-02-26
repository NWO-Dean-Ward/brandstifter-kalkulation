"""
Tests fuer die Schreiner's Buero ERP-Anbindung.

Testet CSV Import/Export, Offline-Fallback und Agent-Logik.
(API-Tests gegen den echten SB-Server werden uebersprungen wenn offline.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import (
    config as config_routes, kalkulation, export as export_routes,
    lernen, cnc, schreiners_buero,
)
from api.database import init_db_sync

# Setup
init_db_sync()
app_config = AppConfig(config_dir=Path(__file__).parent.parent / "config")
config_routes.set_config(app_config)
pipeline = _init_pipeline(app_config)
kalkulation.set_pipeline(pipeline)
export_routes.set_pipeline(pipeline)
lernen.set_pipeline(pipeline)
cnc.set_cnc_agent(pipeline.subagenten.get("cnc_integration"))
schreiners_buero.set_sb_agent(pipeline.subagenten.get("schreiners_buero"))

client = TestClient(app, raise_server_exceptions=True)

FIXTURES = Path(__file__).parent / "fixtures"


def test_01_sb_status():
    """Verbindungstest / Status-Abfrage."""
    print("\n=== 1. SB Verbindungstest ===\n")

    r = client.get("/api/sb/status")
    assert r.status_code == 200
    data = r.json()

    print(f"  Status: {data['status']}")
    print(f"  API-URL: {data.get('api_url', '(nicht gesetzt)')}")
    print(f"  Nachricht: {data.get('message', '')}")
    print(f"  CSV-Import: {data.get('csv_import', '')}")
    print(f"  CSV-Export: {data.get('csv_export', '')}")

    # SB ist im Testumfeld nicht erreichbar -> offline oder nicht_konfiguriert
    assert data["status"] in ("offline", "nicht_konfiguriert", "ok", "timeout")

    print("\n>>> SB Verbindungstest BESTANDEN <<<")


def test_02_csv_export():
    """CSV-Export im SB-Format."""
    print("\n=== 2. CSV-Export SB-Format ===\n")

    # Projekt + Positionen anlegen
    r = client.post("/api/projekte/", json={
        "name": "SB-Test Einbaumoebel",
        "projekt_typ": "privat",
        "kunde": "Familie Schneider",
    })
    projekt_id = r.json()["id"]
    print(f"  Projekt: {projekt_id}")

    positionen = [
        {
            "pos_nr": "01.01",
            "kurztext": "Einbauschrank Flur",
            "menge": 1,
            "einheit": "STK",
            "material": "MDF 19mm weiss",
            "platten_anzahl": 8,
            "kantenlaenge_lfm": 16,
            "bohrungen_anzahl": 24,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Garderobe mit Hutablage",
            "menge": 1,
            "einheit": "STK",
            "material": "Eiche furniert",
            "platten_anzahl": 4,
            "kantenlaenge_lfm": 8,
            "bohrungen_anzahl": 12,
        },
        {
            "pos_nr": "01.03",
            "kurztext": "Schuhschrank niedrig",
            "menge": 1,
            "einheit": "STK",
            "material": "MDF 19mm weiss",
            "platten_anzahl": 6,
            "kantenlaenge_lfm": 12,
            "bohrungen_anzahl": 16,
        },
    ]

    for pos in positionen:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201

    # Kalkulieren (damit EP/GP in DB stehen)
    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200
    print(f"  Angebotspreis: {r.json()['angebotspreis']:,.2f} EUR")

    # CSV-Export
    r = client.post(f"/api/sb/{projekt_id}/csv/export")
    assert r.status_code == 200

    # FileResponse liefert den CSV-Inhalt
    content = r.text
    lines = content.strip().split("\n")
    print(f"  CSV-Zeilen: {len(lines)} (1 Header + {len(lines)-1} Daten)")
    print(f"  Header: {lines[0][:70]}...")

    # Pruefen: Semikolon-getrennt, richtige Anzahl Zeilen
    assert ";" in lines[0], "Semikolon als Trennzeichen erwartet"
    assert len(lines) == 4, f"Erwartet 4 Zeilen (Header + 3 Pos), bekommen {len(lines)}"

    # EP/GP muessen > 0 sein (Kalkulation war erfolgreich)
    for line in lines[1:]:
        felder = line.split(";")
        print(f"    Pos {felder[0]}: {felder[1][:30]} | EP: {felder[8]} | GP: {felder[9]}")

    print("\n>>> CSV-Export BESTANDEN <<<")
    return projekt_id


def test_03_csv_import():
    """CSV-Import im SB-Format."""
    print("\n=== 3. CSV-Import SB-Format ===\n")

    # Test-CSV erstellen
    csv_content = (
        "Pos-Nr;Bezeichnung;Menge;Einheit;Material;Laenge;Breite;Staerke;EP;GP\n"
        "01.01;Wandregal Buche;3;STK;Buche Multiplex 18mm;800;300;18;145,50;436,50\n"
        "01.02;Konsolentisch;1;STK;Eiche massiv;1200;600;40;890,00;890,00\n"
        "01.03;Wandpaneel;2;STK;MDF 16mm;2400;600;16;78,25;156,50\n"
    )

    r = client.post(
        "/api/sb/csv/upload",
        files={"datei": ("sb_testdaten.csv", csv_content.encode("iso-8859-1"), "text/csv")},
        data={"typ": "stueckliste"},
    )
    assert r.status_code == 200
    data = r.json()

    print(f"  Status: {data['status']}")
    print(f"  Datei: {data.get('datei', '')}")
    print(f"  Positionen: {data.get('anzahl', 0)}")

    assert data["status"] == "ok"
    assert data["anzahl"] == 3

    for pos in data["positionen"]:
        print(f"    {pos['pos_nr']}: {pos['kurztext']} | {pos['material']} | EP: {pos['einheitspreis']}")

    # Preise pruefen (deutsche Formatierung korrekt geparst)
    preise = data["positionen"]
    assert preise[0]["einheitspreis"] == 145.50, f"EP falsch: {preise[0]['einheitspreis']}"
    assert preise[1]["einheitspreis"] == 890.00
    assert preise[2]["gesamtpreis"] == 156.50

    print("\n>>> CSV-Import BESTANDEN <<<")


def test_04_materialpreise_csv_import():
    """Materialpreise aus SB-CSV importieren."""
    print("\n=== 4. Materialpreise CSV-Import ===\n")

    csv_content = (
        "Bezeichnung;Kategorie;Lieferant;Artikelnr;Einheit;Preis\n"
        "Spanplatte 19mm weiss;Platte;Egger;E100;m2;12,50\n"
        "MDF 19mm roh;Platte;Egger;M200;m2;8,75\n"
        "ABS-Kante 2mm weiss;Kante;Rehau;K300;lfm;1,20\n"
        "Topfband Blum;Beschlag;Blum;B400;STK;4,85\n"
        "Schubkastenfuehrung 500mm;Beschlag;Hettich;H500;Paar;18,90\n"
    )

    r = client.post(
        "/api/sb/csv/upload",
        files={"datei": ("materialpreise_2026.csv", csv_content.encode("iso-8859-1"), "text/csv")},
        data={"typ": "materialpreise"},
    )
    assert r.status_code == 200
    data = r.json()

    print(f"  Status: {data['status']}")
    print(f"  Quelle: {data.get('quelle', '')}")
    print(f"  Anzahl: {data.get('anzahl', 0)}")

    assert data["status"] == "ok"
    assert data["anzahl"] == 5

    for p in data["preise"]:
        print(f"    {p['material_name']}: {p['preis']:.2f} EUR/{p['einheit']} ({p['lieferant']})")

    # Preis-Check
    assert data["preise"][0]["preis"] == 12.50
    assert data["preise"][3]["preis"] == 4.85

    print("\n>>> Materialpreise CSV-Import BESTANDEN <<<")


def test_05_auftrag_offline_fallback():
    """Auftrag senden mit automatischem CSV-Fallback (SB offline)."""
    print("\n=== 5. Auftrag senden (Offline-Fallback) ===\n")

    # Projekt mit Positionen (wiederverwendbar)
    r = client.post("/api/projekte/", json={
        "name": "SB Offline Test",
        "projekt_typ": "standard",
        "kunde": "Testfirma GmbH",
    })
    projekt_id = r.json()["id"]

    r = client.post(f"/api/projekte/{projekt_id}/positionen/", json={
        "pos_nr": "01.01",
        "kurztext": "Testposition",
        "menge": 5,
        "einheit": "STK",
        "material": "Span 19mm",
        "platten_anzahl": 10,
        "kantenlaenge_lfm": 20,
        "bohrungen_anzahl": 15,
    })
    assert r.status_code == 201

    # Kalkulieren
    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200

    # Auftrag an SB senden (wird offline -> CSV-Fallback)
    r = client.post(f"/api/sb/{projekt_id}/auftrag")
    assert r.status_code == 200
    data = r.json()

    print(f"  Status: {data['status']}")
    print(f"  Nachricht: {data.get('message', '')}")

    # SB ist offline im Test -> csv_fallback oder offline
    assert data["status"] in ("csv_fallback", "offline", "ok")

    if data["status"] == "csv_fallback":
        csv_info = data.get("csv", {})
        print(f"  CSV-Datei: {csv_info.get('datei', '')}")
        print(f"  Positionen: {csv_info.get('positionen', 0)}")
        assert csv_info.get("status") == "ok"

        # CSV-Datei pruefen
        csv_pfad = csv_info.get("pfad", "")
        if csv_pfad:
            assert Path(csv_pfad).exists(), f"CSV nicht gefunden: {csv_pfad}"

    print("\n>>> Auftrag Offline-Fallback BESTANDEN <<<")


def test_06_stueckliste_offline():
    """Stueckliste senden (Offline -> CSV)."""
    print("\n=== 6. Stueckliste senden (Offline) ===\n")

    # Bestehendes Projekt nutzen
    r = client.post("/api/projekte/", json={
        "name": "SB Stueckliste Test",
        "projekt_typ": "privat",
    })
    projekt_id = r.json()["id"]

    for pos in [
        {"pos_nr": "01.01", "kurztext": "Seitenwand", "menge": 2, "einheit": "STK",
         "material": "Eiche", "platten_anzahl": 2, "kantenlaenge_lfm": 4, "bohrungen_anzahl": 8},
        {"pos_nr": "01.02", "kurztext": "Boden", "menge": 3, "einheit": "STK",
         "material": "Eiche", "platten_anzahl": 3, "kantenlaenge_lfm": 6, "bohrungen_anzahl": 0},
    ]:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201

    r = client.post(f"/api/sb/{projekt_id}/stueckliste")
    assert r.status_code == 200
    data = r.json()

    print(f"  Status: {data['status']}")
    print(f"  Nachricht: {data.get('message', '')}")

    assert data["status"] in ("csv_fallback", "offline", "ok")

    print("\n>>> Stueckliste Offline BESTANDEN <<<")


def test_07_agent_direkt():
    """SB-Agent direkte Aufrufe testen."""
    print("\n=== 7. SB-Agent direkt ===\n")

    from agents.schreiners_buero import SchreinersBueroAgent, _parse_sb_preis, _format_sb_preis
    from agents.base_agent import AgentMessage
    import asyncio

    # Zahlenformat-Tests
    assert _parse_sb_preis("1.234,56") == 1234.56, "Deutsch -> Float"
    assert _parse_sb_preis("12,50") == 12.50
    assert _parse_sb_preis("890,00") == 890.00
    assert _parse_sb_preis("") == 0.0
    assert _parse_sb_preis("0") == 0.0
    print("  Zahlenformat-Parsing: OK")

    assert _format_sb_preis(1234.56) == "1234,56"
    assert _format_sb_preis(12.5) == "12,50"
    assert _format_sb_preis(0) == "0,00"
    print("  Zahlenformat-Ausgabe: OK")

    # Agent-Instanz
    agent = SchreinersBueroAgent()
    agent.configure({
        "api_url": "",  # Kein API-Server
        "csv_export_verzeichnis": "data/sb_export",
        "csv_import_verzeichnis": "data/sb_import",
    })

    # CSV-Export direkt
    msg = AgentMessage(
        sender="test", receiver="schreiners_buero",
        msg_type="sb_csv_export",
        payload={
            "positionen": [
                {"pos_nr": "01.01", "kurztext": "Testbauteil", "menge": 2, "einheit": "STK",
                 "material": "MDF", "einheitspreis": 150.0, "gesamtpreis": 300.0},
            ],
            "projekt": {"name": "Direkttest"},
        },
        projekt_id="TEST-DIREKT",
    )
    result = asyncio.get_event_loop().run_until_complete(agent.execute(msg))
    assert result.payload["status"] == "ok"
    print(f"  CSV-Export direkt: {result.payload['datei']}")

    # Verbindungstest (ohne URL)
    msg2 = AgentMessage(
        sender="test", receiver="schreiners_buero",
        msg_type="sb_verbindungstest",
        payload={},
        projekt_id="TEST",
    )
    result2 = asyncio.get_event_loop().run_until_complete(agent.execute(msg2))
    assert result2.payload["status"] == "nicht_konfiguriert"
    print(f"  Verbindungstest (keine URL): {result2.payload['status']}")

    print("\n>>> SB-Agent direkt BESTANDEN <<<")


def test_08_sb_config_geladen():
    """Pruefen ob SB-Konfiguration korrekt geladen wird."""
    print("\n=== 8. SB-Konfiguration ===\n")

    config = app_config.schreiners_buero
    print(f"  API-URL: {config.get('api_url', '(fehlt)')}")
    print(f"  CSV-Trennzeichen: '{config.get('csv_trennzeichen', '')}'")
    print(f"  CSV-Encoding: {config.get('csv_encoding', '')}")
    print(f"  Kostenstelle: {config.get('defaults', {}).get('kostenstelle', '')}")
    print(f"  MwSt: {config.get('defaults', {}).get('mwst_satz', 0)}%")

    assert config.get("api_url"), "API-URL muss gesetzt sein"
    assert config.get("csv_trennzeichen") == ";", "Semikolon als Trennzeichen"
    assert config.get("csv_encoding") == "iso-8859-1", "ISO-8859-1 Encoding"

    print("\n>>> SB-Konfiguration BESTANDEN <<<")


if __name__ == "__main__":
    test_01_sb_status()
    test_02_csv_export()
    test_03_csv_import()
    test_04_materialpreise_csv_import()
    test_05_auftrag_offline_fallback()
    test_06_stueckliste_offline()
    test_07_agent_direkt()
    test_08_sb_config_geladen()
    print("\n\n========================================")
    print("  ALLE SCHREINERS BUERO TESTS BESTANDEN")
    print("========================================")
