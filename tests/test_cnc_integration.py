"""
Tests fuer die CNC-Integration (SmartWOP/NCHops).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation, export as export_routes, lernen, cnc
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

client = TestClient(app, raise_server_exceptions=True)

FIXTURES = Path(__file__).parent / "fixtures"


def test_01_parse_hop():
    """HOP-Datei parsen und CNC-Parameter extrahieren."""
    print("\n=== 1. HOP-Parse ===\n")

    hop_path = FIXTURES / "test_bauteil.hop"
    assert hop_path.exists(), f"Fixture nicht gefunden: {hop_path}"

    with open(hop_path, "rb") as f:
        r = client.post(
            "/api/cnc/parse/hop",
            files={"datei": ("test_bauteil.hop", f, "application/octet-stream")},
            data={"projekt_id": "TEST-CNC"},
        )

    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()

    print(f"  Datei: {data['datei']}")
    ws = data["werkstueck"]
    print(f"  Werkstueck: {ws['laenge_mm']}x{ws['breite_mm']}x{ws['staerke_mm']}mm")
    print(f"  Flaeche: {ws['flaeche_m2']} m2")

    bearb = data["bearbeitungen"]
    print(f"  Bohrungen vertikal: {bearb['bohrungen_vertikal']}")
    print(f"  Bohrungen horizontal: {bearb['bohrungen_horizontal']}")
    print(f"  Bohrungen gesamt: {bearb['bohrungen_gesamt']}")
    print(f"  Fraes-Laenge: {bearb['fraes_laenge_mm']}mm")

    zeit = data["zeitschaetzung"]
    print(f"  Bearbeitungszeit: {zeit['bearbeitungszeit_min']} min")

    assert ws["laenge_mm"] == 800
    assert ws["breite_mm"] == 400
    assert ws["staerke_mm"] == 19
    assert bearb["bohrungen_gesamt"] == 12

    print("\n>>> HOP-Parse BESTANDEN <<<")


def test_02_parse_mpr():
    """MPR-Datei (WoodWOP) parsen."""
    print("\n=== 2. MPR-Parse ===\n")

    mpr_path = FIXTURES / "test_bauteil.mpr"
    assert mpr_path.exists(), f"Fixture nicht gefunden: {mpr_path}"

    with open(mpr_path, "rb") as f:
        r = client.post(
            "/api/cnc/parse/mpr",
            files={"datei": ("test_bauteil.mpr", f, "application/octet-stream")},
            data={"projekt_id": "TEST-CNC"},
        )

    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()

    print(f"  Format: {data['format']}")
    ws = data["werkstueck"]
    print(f"  Werkstueck: {ws['laenge_mm']}x{ws['breite_mm']}x{ws['staerke_mm']}mm")

    bearb = data["bearbeitungen"]
    print(f"  Bohrungen: {bearb['bohrungen']}")
    print(f"  Konturen/Fraesen: {bearb['konturen_fraesen']}")
    print(f"  Saege-Ops: {bearb['saege_operationen']}")
    print(f"  Nuten: {bearb['nuten']}")
    print(f"  Operationen gesamt: {bearb['operationen_gesamt']}")

    zeit = data["zeitschaetzung"]
    print(f"  Bearbeitungszeit: {zeit['bearbeitungszeit_min']} min")

    assert ws["laenge_mm"] == 800
    assert ws["breite_mm"] == 400
    assert ws["staerke_mm"] == 19
    assert bearb["bohrungen"] == 6
    assert bearb["saege_operationen"] == 1
    assert bearb["konturen_fraesen"] == 1

    print("\n>>> MPR-Parse BESTANDEN <<<")


def test_03_hop_export():
    """HOP-Dateien fuer ein Projekt generieren."""
    print("\n=== 3. HOP-Export ===\n")

    # Projekt + Positionen anlegen
    r = client.post("/api/projekte/", json={
        "name": "CNC-Test Kueche",
        "projekt_typ": "privat",
        "kunde": "Test CNC",
    })
    projekt_id = r.json()["id"]
    print(f"  Projekt: {projekt_id}")

    positionen = [
        {
            "pos_nr": "01.01",
            "kurztext": "Seitenwand links",
            "menge": 1,
            "einheit": "STK",
            "material": "Eiche furniert",
            "platten_anzahl": 1,
            "kantenlaenge_lfm": 3,
            "bohrungen_anzahl": 12,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Seitenwand rechts",
            "menge": 1,
            "einheit": "STK",
            "material": "Eiche furniert",
            "platten_anzahl": 1,
            "kantenlaenge_lfm": 3,
            "bohrungen_anzahl": 12,
        },
        {
            "pos_nr": "01.03",
            "kurztext": "Einlegeboden",
            "menge": 3,
            "einheit": "STK",
            "material": "Eiche furniert",
            "platten_anzahl": 3,
            "kantenlaenge_lfm": 6,
            "bohrungen_anzahl": 0,
        },
    ]

    for pos in positionen:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201, f"Position {pos['pos_nr']}: {r.text}"

    # HOP-Export
    r = client.post(f"/api/cnc/{projekt_id}/export/hop")
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()

    print(f"  Exportiert: {data['anzahl']} Dateien")
    print(f"  Verzeichnis: {data['verzeichnis']}")
    for d in data["dateien"]:
        print(f"    {d['datei']}: {d['kurztext']} ({d['dimensionen']})")

    assert data["anzahl"] == 3
    # Pruefen ob Dateien existieren
    for d in data["dateien"]:
        assert Path(d["pfad"]).exists(), f"Datei nicht gefunden: {d['pfad']}"

    print("\n>>> HOP-Export BESTANDEN <<<")
    return projekt_id


def test_04_stueckliste():
    """Stueckliste als CSV fuer Smartwoop exportieren."""
    print("\n=== 4. Stuecklisten-Export ===\n")

    # Projekt aus Test 3 verwenden (neues anlegen fuer Isolation)
    r = client.post("/api/projekte/", json={
        "name": "CNC Stueckliste Test",
        "projekt_typ": "standard",
    })
    projekt_id = r.json()["id"]

    positionen = [
        {
            "pos_nr": "01.01",
            "kurztext": "Korpus Seitenteil",
            "menge": 2,
            "einheit": "STK",
            "material": "MDF 19mm",
            "platten_anzahl": 2,
            "kantenlaenge_lfm": 4,
            "bohrungen_anzahl": 8,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Einlegeboden",
            "menge": 4,
            "einheit": "STK",
            "material": "MDF 19mm",
            "platten_anzahl": 4,
            "kantenlaenge_lfm": 8,
            "bohrungen_anzahl": 0,
        },
    ]

    for pos in positionen:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201

    r = client.post(f"/api/cnc/{projekt_id}/export/stueckliste")
    assert r.status_code == 200

    # Bei FileResponse kommt der Inhalt direkt
    content = r.text
    # BOM entfernen falls vorhanden (UTF-8-BOM fuer Excel-Kompatibilitaet)
    content = content.lstrip("\ufeff")
    lines = content.strip().split("\n")
    print(f"  CSV-Zeilen: {len(lines)}")
    print(f"  Header: {lines[0][:80]}...")
    print(f"  Erste Zeile: {lines[1][:80]}...")

    # Header + 2+4=6 Datenzeilen
    assert len(lines) >= 7, f"Erwartet >= 7 Zeilen, bekommen {len(lines)}"

    print("\n>>> Stuecklisten-Export BESTANDEN <<<")


def test_05_nesting():
    """Nesting-Analyse: Plattenverbrauch und Verschnitt."""
    print("\n=== 5. Nesting-Analyse ===\n")

    r = client.post("/api/projekte/", json={
        "name": "Nesting Test",
        "projekt_typ": "standard",
    })
    projekt_id = r.json()["id"]

    positionen = [
        {
            "pos_nr": "01.01",
            "kurztext": "Grosse Seitenwand",
            "menge": 4,
            "einheit": "STK",
            "material": "Spanplatte 19mm",
            "platten_anzahl": 4,
            "kantenlaenge_lfm": 0,
            "bohrungen_anzahl": 0,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Rueckwand",
            "menge": 2,
            "einheit": "STK",
            "material": "HDF 3mm",
            "platten_anzahl": 2,
            "kantenlaenge_lfm": 0,
            "bohrungen_anzahl": 0,
        },
    ]

    for pos in positionen:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201

    r = client.post(f"/api/cnc/{projekt_id}/nesting?platte_laenge_mm=2800&platte_breite_mm=2070")
    assert r.status_code == 200
    data = r.json()

    print(f"  Teile: {data['teile_anzahl']}")
    print(f"  Platten benoetig: {data['platten_benötigt']}")
    print(f"  Platten-Format: {data['platten_format']}")
    print(f"  Flaeche Teile: {data['flaeche_teile_m2']} m2")
    print(f"  Flaeche Platten: {data['flaeche_platten_m2']} m2")
    print(f"  Verschnitt: {data['verschnitt_m2']} m2 ({data['verschnitt_prozent']}%)")
    print(f"  Hinweis: {data['hinweis']}")

    assert data["teile_anzahl"] == 6
    assert data["platten_benötigt"] >= 1
    assert data["verschnitt_prozent"] >= 0

    print("\n>>> Nesting-Analyse BESTANDEN <<<")


def test_06_cnc_agent_direkt():
    """CNC-Agent direkt testen (ohne HTTP)."""
    print("\n=== 6. CNC-Agent direkt ===\n")

    from agents.cnc_integration import CNCIntegration
    from agents.base_agent import AgentMessage
    import asyncio

    agent = CNCIntegration()
    agent.configure(export_verzeichnis="exports")

    # Parse HOP direkt
    msg = AgentMessage(
        sender="test", receiver="cnc_integration",
        msg_type="parse_hop",
        payload={"datei_pfad": str(FIXTURES / "test_bauteil.hop")},
        projekt_id="TEST",
    )
    result = asyncio.get_event_loop().run_until_complete(agent.execute(msg))

    assert result.msg_type == "response"
    assert "error" not in result.payload
    bearb = result.payload["bearbeitungen"]
    print(f"  HOP direkt: {bearb['bohrungen_gesamt']} Bohrungen")
    assert bearb["bohrungen_gesamt"] == 12

    # Zeitschaetzung pruefen
    zeit = result.payload["zeitschaetzung"]
    print(f"  Bearbeitungszeit: {zeit['bearbeitungszeit_min']} min")
    assert zeit["bearbeitungszeit_min"] > 0

    # Parse MPR direkt
    msg2 = AgentMessage(
        sender="test", receiver="cnc_integration",
        msg_type="parse_mpr",
        payload={"datei_pfad": str(FIXTURES / "test_bauteil.mpr")},
        projekt_id="TEST",
    )
    result2 = asyncio.get_event_loop().run_until_complete(agent.execute(msg2))
    assert result2.msg_type == "response"
    assert "error" not in result2.payload
    print(f"  MPR direkt: {result2.payload['bearbeitungen']['operationen_gesamt']} Operationen")

    print("\n>>> CNC-Agent direkt BESTANDEN <<<")


def test_07_maschinen_kalkulator_nchops():
    """MaschinenKalkulator.parse_nchops delegiert an CNCIntegration."""
    print("\n=== 7. MaschinenKalkulator NCHops ===\n")

    from agents.maschinen_kalkulator import MaschinenKalkulator
    import asyncio

    mk = MaschinenKalkulator()
    hop_path = str(FIXTURES / "test_bauteil.hop")

    result = asyncio.get_event_loop().run_until_complete(mk.parse_nchops(hop_path))

    assert "error" not in result
    print(f"  Werkstueck: {result['werkstueck']['laenge_mm']}x{result['werkstueck']['breite_mm']}mm")
    print(f"  Bohrungen: {result['bearbeitungen']['bohrungen_gesamt']}")
    print(f"  Zeit: {result['zeitschaetzung']['bearbeitungszeit_min']} min")

    assert result["werkstueck"]["laenge_mm"] == 800
    assert result["bearbeitungen"]["bohrungen_gesamt"] == 12

    print("\n>>> MaschinenKalkulator NCHops BESTANDEN <<<")


def test_08_invalid_file():
    """Fehlerbehandlung bei ungueltigen Dateien."""
    print("\n=== 8. Fehlerbehandlung ===\n")

    # HOP mit falscher Endung
    r = client.post(
        "/api/cnc/parse/hop",
        files={"datei": ("test.txt", b"invalid data", "text/plain")},
    )
    assert r.status_code == 400
    print(f"  Falsche Endung: {r.status_code} - {r.json()['detail']}")

    # MPR mit falscher Endung
    r = client.post(
        "/api/cnc/parse/mpr",
        files={"datei": ("test.txt", b"invalid data", "text/plain")},
    )
    assert r.status_code == 400
    print(f"  Falsche Endung: {r.status_code} - {r.json()['detail']}")

    print("\n>>> Fehlerbehandlung BESTANDEN <<<")


if __name__ == "__main__":
    test_01_parse_hop()
    test_02_parse_mpr()
    test_03_hop_export()
    test_04_stueckliste()
    test_05_nesting()
    test_06_cnc_agent_direkt()
    test_07_maschinen_kalkulator_nchops()
    test_08_invalid_file()
    print("\n\n========================================")
    print("  ALLE CNC-INTEGRATION-TESTS BESTANDEN")
    print("========================================")
