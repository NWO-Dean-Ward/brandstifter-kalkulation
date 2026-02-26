"""
Test: Materialpreise aus DB werden korrekt verwendet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation
from api.database import init_db_sync

init_db_sync()
app_config = AppConfig(config_dir=Path(__file__).parent.parent / "config")
config_routes.set_config(app_config)
pipeline = _init_pipeline(app_config)
kalkulation.set_pipeline(pipeline)

client = TestClient(app, raise_server_exceptions=True)


def test_kalkulation_mit_preisliste():
    """Wenn Materialpreise in DB -> keine 'nicht in Preisliste'-Warnung."""
    print("\n=== Kalkulation mit Preisliste ===\n")

    # Preise anlegen
    preise = [
        {"material_name": "Eiche furniert 19mm", "kategorie": "platte", "lieferant": "Egger", "preis": 52.00, "einheit": "m2"},
        {"material_name": "MDF 19mm", "kategorie": "platte", "lieferant": "Egger", "preis": 12.50, "einheit": "m2"},
        {"material_name": "ABS-Kante 2mm Eiche", "kategorie": "kante", "lieferant": "Doellken", "preis": 1.80, "einheit": "lfm"},
    ]
    for p in preise:
        r = client.post("/api/materialpreise/", json=p)
        assert r.status_code == 201
        print(f"  Preis: {p['material_name']} = {p['preis']} EUR/{p['einheit']}")

    # Projekt + Position
    r = client.post("/api/projekte/", json={
        "name": "Test Preisliste",
        "projekt_typ": "privat",
    })
    projekt_id = r.json()["id"]

    r = client.post(f"/api/projekte/{projekt_id}/positionen/", json={
        "pos_nr": "1.1",
        "kurztext": "Unterschrank Eiche",
        "menge": 2,
        "einheit": "STK",
        "material": "Eiche furniert 19mm",
        "platten_anzahl": 4,
        "kantenlaenge_lfm": 12,
        "bohrungen_anzahl": 8,
    })

    # Kalkulieren
    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200
    kalk = r.json()

    # Preisliste-Warnungen checken
    preis_warnungen = [w for w in kalk["warnungen"] if "Preisliste" in w or "Schaetzpreis" in w]
    print(f"\n  Materialkosten: {kalk['materialkosten']:.2f} EUR")
    print(f"  Angebotspreis:  {kalk['angebotspreis']:.2f} EUR")
    print(f"  Preis-Warnungen: {len(preis_warnungen)}")

    # Eiche furniert 19mm ist jetzt in der DB -> keine Warnung dafuer
    eiche_warnungen = [w for w in preis_warnungen if "Eiche furniert" in w]
    assert len(eiche_warnungen) == 0, f"Keine Preiswarnung fuer Eiche erwartet, aber: {eiche_warnungen}"

    print(f"\n>>> Preislisten-Test BESTANDEN <<<")


if __name__ == "__main__":
    test_kalkulation_mit_preisliste()
