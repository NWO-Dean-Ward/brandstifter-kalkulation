"""
API-Integrationstest – Prüft alle Endpunkte end-to-end.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation
from api.database import init_db_sync


def setup():
    """Initialisiert DB und Config für Tests."""
    init_db_sync()
    app_config = AppConfig(config_dir=Path(__file__).parent.parent / "config")
    config_routes.set_config(app_config)

    # Pipeline initialisieren
    from api.main import _init_pipeline
    pipeline, llm_router = _init_pipeline(app_config)
    kalkulation.set_pipeline(pipeline)


setup()
client = TestClient(app, raise_server_exceptions=False)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    print(f"  Health: OK")


def test_config_maschinen():
    r = client.get("/api/config/maschinen")
    assert r.status_code == 200
    data = r.json()
    assert "holzher_nextec_7707" in data
    assert data["holzher_nextec_7707"]["stundensatz_eur"] == 85.0
    print(f"  Config Maschinen: OK ({len(data)} Maschinen)")


def test_config_zuschlaege():
    r = client.get("/api/config/zuschlaege")
    assert r.status_code == 200
    assert r.json()["gemeinkosten_gkz"] == 0.25
    print(f"  Config Zuschlaege: OK (GKZ={r.json()['gemeinkosten_gkz']})")


def test_config_stundensaetze():
    r = client.get("/api/config/stundensaetze")
    assert r.status_code == 200
    assert r.json()["einheitlicher_stundensatz"] == 58.0
    print(f"  Config Stundensaetze: OK ({r.json()['einheitlicher_stundensatz']} EUR/h)")


def test_projekt_crud():
    # Erstellen
    r = client.post("/api/projekte/", json={
        "name": "Testkueche Musterhaus",
        "projekt_typ": "privat",
        "kunde": "Familie Mustermann",
    })
    assert r.status_code == 201
    projekt = r.json()
    assert projekt["name"] == "Testkueche Musterhaus"
    assert projekt["projekt_typ"] == "privat"
    projekt_id = projekt["id"]
    print(f"  Projekt erstellt: {projekt_id}")

    # Lesen
    r = client.get(f"/api/projekte/{projekt_id}")
    assert r.status_code == 200

    # Update
    r = client.patch(f"/api/projekte/{projekt_id}", json={"status": "kalkuliert"})
    assert r.status_code == 200
    assert r.json()["status"] == "kalkuliert"

    # Liste
    r = client.get("/api/projekte/")
    assert r.status_code == 200
    assert len(r.json()) >= 1
    print(f"  Projekt CRUD: OK")
    return projekt_id


def test_positionen():
    # Eigenes Projekt anlegen
    r = client.post("/api/projekte/", json={
        "name": "Positionstest",
        "projekt_typ": "privat",
    })
    assert r.status_code == 201
    projekt_id = r.json()["id"]

    # Position mit Lackierung
    r = client.post(f"/api/projekte/{projekt_id}/positionen/", json={
        "pos_nr": "01.01.001",
        "kurztext": "Unterschrank 60cm",
        "langtext": "Eiche furniert, RAL 9010 lackiert, Softclose",
        "menge": 3,
        "einheit": "STK",
        "material": "Eiche furniert",
        "platten_anzahl": 6,
        "kantenlaenge_lfm": 12,
    })
    assert r.status_code == 201
    pos = r.json()
    assert pos["ist_lackierung"] == True, "Lackierung nicht erkannt!"
    assert pos["ist_fremdleistung"] == True
    print(f"  Position mit Lackierung: OK (erkannt={pos['ist_lackierung']})")

    # Position ohne Lackierung
    r = client.post(f"/api/projekte/{projekt_id}/positionen/", json={
        "pos_nr": "01.02.001",
        "kurztext": "Arbeitsplatte Granit",
        "menge": 1,
        "einheit": "STK",
        "material": "Granit poliert",
    })
    assert r.status_code == 201
    pos2 = r.json()
    assert pos2["ist_lackierung"] == False
    print(f"  Position ohne Lackierung: OK")

    # Liste
    r = client.get(f"/api/projekte/{projekt_id}/positionen/")
    assert r.status_code == 200
    assert len(r.json()) == 2
    print(f"  Positionen Liste: {len(r.json())} Positionen")


def test_materialpreise():
    r = client.post("/api/materialpreise/", json={
        "material_name": "Eiche furniert 19mm",
        "kategorie": "platte",
        "lieferant": "Egger",
        "preis": 45.50,
        "einheit": "m2",
    })
    assert r.status_code == 201
    print(f"  Materialpreis erstellt: {r.json()['material_name']} = {r.json()['preis']} EUR")

    # Liste
    r = client.get("/api/materialpreise/")
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # Versionierung: gleicher Name, neuer Preis
    r = client.post("/api/materialpreise/", json={
        "material_name": "Eiche furniert 19mm",
        "kategorie": "platte",
        "lieferant": "Egger",
        "preis": 48.00,
        "einheit": "m2",
    })
    assert r.status_code == 201
    print(f"  Materialpreis aktualisiert: {r.json()['preis']} EUR (alter Preis archiviert)")


if __name__ == "__main__":
    print("=== API-Integrationstest ===\n")

    test_health()
    test_config_maschinen()
    test_config_zuschlaege()
    test_config_stundensaetze()

    test_projekt_crud()
    test_positionen()
    test_materialpreise()

    print("\n>>> Alle API-Tests bestanden <<<")
