"""
Phase 3 Tests: GAEB-Parser + Export-Agent (PDF, Excel, GAEB).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation, export as export_routes
from api.database import init_db_sync


# Setup
init_db_sync()
app_config = AppConfig(config_dir=Path(__file__).parent.parent / "config")
config_routes.set_config(app_config)
pipeline = _init_pipeline(app_config)
kalkulation.set_pipeline(pipeline)
export_routes.set_pipeline(pipeline)

client = TestClient(app, raise_server_exceptions=True)

GAEB_FILE = Path(__file__).parent / "test_gaeb_beispiel.x83"


def test_gaeb_parser():
    """Testet GAEB X83 Parser direkt."""
    print("\n=== GAEB X83 Parser ===\n")

    from agents.dokument_parser import DokumentParser
    parser = DokumentParser()

    positionen = parser._parse_gaeb_xml(GAEB_FILE)

    assert len(positionen) == 3, f"Erwartet 3 Positionen, bekommen {len(positionen)}"

    # Position 1
    p1 = positionen[0]
    assert p1["pos_nr"] == "01.01.001"
    assert p1["menge"] == 8.0
    assert p1["einheit"] == "STK"
    assert "Einbauschrank" in p1["kurztext"]
    print(f"  Pos {p1['pos_nr']}: {p1['kurztext'][:50]} | {p1['menge']} {p1['einheit']}")

    # Position 2 (Lackierung!)
    p2 = positionen[1]
    assert p2["pos_nr"] == "01.01.002"
    assert p2["menge"] == 4.0
    print(f"  Pos {p2['pos_nr']}: {p2['kurztext'][:50]} | {p2['menge']} {p2['einheit']}")

    # Position 3
    p3 = positionen[2]
    assert p3["pos_nr"] == "01.02.001"
    assert p3["menge"] == 12.0
    print(f"  Pos {p3['pos_nr']}: {p3['kurztext'][:50]} | {p3['menge']} {p3['einheit']}")

    # Lackierung erkennen
    positionen = parser._erkennung_lackierung(positionen)
    assert positionen[1]["ist_lackierung"] == True, "RAL 7035 muss als Lackierung erkannt werden"
    assert positionen[0]["ist_lackierung"] == False
    assert positionen[2]["ist_lackierung"] == False
    print(f"\n  Lackierung erkannt bei Pos {positionen[1]['pos_nr']}: JA")

    print(f"\n>>> GAEB-Parser BESTANDEN ({len(positionen)} Positionen) <<<")


def test_export_pipeline():
    """Testet den kompletten Workflow: Projekt -> Kalkulation -> Export."""
    print("\n=== Export-Pipeline ===\n")

    # 1. Projekt + Positionen anlegen
    r = client.post("/api/projekte/", json={
        "name": "Schule Export-Test",
        "projekt_typ": "oeffentlich",
        "kunde": "Gemeinde Ober-Moerlen",
    })
    projekt_id = r.json()["id"]
    print(f"  Projekt: {projekt_id}")

    positionen_data = [
        {
            "pos_nr": "01.01",
            "kurztext": "Einbauschrank Klassenzimmer",
            "menge": 8,
            "einheit": "STK",
            "material": "Melamin weiss",
            "platten_anzahl": 24,
            "kantenlaenge_lfm": 48,
            "bohrungen_anzahl": 32,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Garderobenschrank RAL 7035 lackiert",
            "menge": 4,
            "einheit": "STK",
            "material": "MDF 19mm",
            "platten_anzahl": 12,
            "kantenlaenge_lfm": 24,
            "bohrungen_anzahl": 16,
        },
        {
            "pos_nr": "01.03",
            "kurztext": "Regalwand Birke Multiplex",
            "menge": 12,
            "einheit": "STK",
            "material": "Birke Multiplex 18mm",
            "platten_anzahl": 24,
            "kantenlaenge_lfm": 36,
            "bohrungen_anzahl": 48,
        },
    ]
    for pos in positionen_data:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201

    # 2. Kalkulation
    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200
    kalk = r.json()
    print(f"  Angebotspreis: {kalk['angebotspreis']:,.2f} EUR")
    print(f"  Warnungen: {len(kalk['warnungen'])}")

    # 3. Angebots-PDF
    print("\n  --- Angebots-PDF ---")
    r = client.post(f"/api/export/{projekt_id}/angebot-pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    pdf_size = len(r.content)
    print(f"  PDF generiert: {pdf_size:,} Bytes")
    assert pdf_size > 1000, "PDF zu klein"

    # 4. Interne Kalkulations-PDF
    print("  --- Interne Kalkulations-PDF ---")
    r = client.post(f"/api/export/{projekt_id}/intern-pdf")
    assert r.status_code == 200
    intern_size = len(r.content)
    print(f"  PDF generiert: {intern_size:,} Bytes")
    assert intern_size > 1000

    # 5. Excel
    print("  --- Excel-Export ---")
    r = client.post(f"/api/export/{projekt_id}/excel")
    assert r.status_code == 200
    assert "spreadsheet" in r.headers["content-type"]
    excel_size = len(r.content)
    print(f"  Excel generiert: {excel_size:,} Bytes")
    assert excel_size > 1000

    # 6. GAEB-Export
    print("  --- GAEB X83 Export ---")
    r = client.post(f"/api/export/{projekt_id}/gaeb")
    assert r.status_code == 200
    gaeb_content = r.content.decode("utf-8")
    assert "<GAEB" in gaeb_content
    assert "Brandstifter" in gaeb_content
    print(f"  GAEB generiert: {len(r.content):,} Bytes")

    # GAEB-Datei validieren: Positionen muessen drin sein
    assert "01.01" in gaeb_content or "Einbauschrank" in gaeb_content

    # 7. Alle Exports auf einmal
    print("  --- Alle Exports ---")
    r = client.post(f"/api/export/{projekt_id}/alle")
    assert r.status_code == 200
    exports = r.json().get("exports", {})
    for name, result in exports.items():
        status = result.get("status", "?")
        datei = result.get("dateiname", "?")
        print(f"  {name}: {status} -> {datei}")

    print(f"\n>>> Export-Pipeline BESTANDEN <<<")


def test_export_dateien_existieren():
    """Prueft ob die Export-Dateien tatsaechlich auf der Festplatte liegen."""
    print("\n=== Export-Dateien auf Disk ===\n")
    export_dir = Path(__file__).parent.parent / "exports"
    dateien = list(export_dir.glob("*"))
    print(f"  Export-Verzeichnis: {export_dir}")
    print(f"  Dateien: {len(dateien)}")
    for d in sorted(dateien):
        print(f"    {d.name} ({d.stat().st_size:,} Bytes)")

    pdf_count = len([d for d in dateien if d.suffix == ".pdf"])
    xlsx_count = len([d for d in dateien if d.suffix == ".xlsx"])
    gaeb_count = len([d for d in dateien if d.suffix == ".x83"])

    assert pdf_count >= 2, f"Mindestens 2 PDFs erwartet, {pdf_count} gefunden"
    assert xlsx_count >= 1, f"Mindestens 1 Excel erwartet, {xlsx_count} gefunden"
    assert gaeb_count >= 1, f"Mindestens 1 GAEB erwartet, {gaeb_count} gefunden"

    print(f"\n>>> Dateien-Check BESTANDEN (PDF:{pdf_count} XLSX:{xlsx_count} GAEB:{gaeb_count}) <<<")


if __name__ == "__main__":
    test_gaeb_parser()
    test_export_pipeline()
    test_export_dateien_existieren()
    print("\n\n========================================")
    print("  ALLE PHASE-3-TESTS BESTANDEN")
    print("========================================")
