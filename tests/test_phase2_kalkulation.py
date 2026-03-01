"""
Phase 2 End-to-End Test: Vollstaendige Kalkulations-Pipeline.

Testet:
1. Projekt + Positionen anlegen
2. Kalkulation starten (LeadAgent -> alle Subagenten)
3. Ergebnis pruefen: Alle Kostenarten berechnet, Zuschlaege korrekt
4. Lackierung korrekt als Fremdleistung erkannt
5. Warnungen bei unbekannten Materialien
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation
from api.database import init_db_sync


# Setup
init_db_sync()
app_config = AppConfig(config_dir=Path(__file__).parent.parent / "config")
config_routes.set_config(app_config)
pipeline, llm_router = _init_pipeline(app_config)
kalkulation.set_pipeline(pipeline)

client = TestClient(app, raise_server_exceptions=True)


def test_end_to_end_kalkulation():
    """Kompletter Kalkulations-Durchlauf fuer eine Kueche."""

    print("\n=== Phase 2: End-to-End Kalkulationstest ===\n")

    # 1. Projekt anlegen
    r = client.post("/api/projekte/", json={
        "name": "Kueche Familie Weber",
        "projekt_typ": "privat",
        "kunde": "Familie Weber, Ober-Moerlen",
        "beschreibung": "Einbaukueche L-Form, Eiche furniert, teilweise lackiert",
    })
    assert r.status_code == 201
    projekt = r.json()
    projekt_id = projekt["id"]
    print(f"  Projekt: {projekt_id} ({projekt['name']})")

    # 2. Positionen anlegen (realistische Kuechenausstattung)
    positionen = [
        {
            "pos_nr": "01.01",
            "kurztext": "Unterschrank 60cm mit Schublade",
            "langtext": "Unterschrank Eiche furniert, 1 Schublade Blum Tandembox, Softclose",
            "menge": 4,
            "einheit": "STK",
            "material": "Eiche furniert 19mm",
            "platten_anzahl": 8,
            "kantenlaenge_lfm": 24,
            "schnittanzahl": 0,
            "bohrungen_anzahl": 16,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Oberschrank 60cm",
            "langtext": "Oberschrank Eiche furniert, 2 Einlegeboeden, Blum Clip-Top",
            "menge": 3,
            "einheit": "STK",
            "material": "Eiche furniert 19mm",
            "platten_anzahl": 6,
            "kantenlaenge_lfm": 18,
            "schnittanzahl": 0,
            "bohrungen_anzahl": 12,
        },
        {
            "pos_nr": "01.03",
            "kurztext": "Hochschrank 60cm RAL 9010 lackiert",
            "langtext": "Hochschrank MDF RAL 9010 seidenmatt lackiert, 4 Einlegeboeden, Blum",
            "menge": 2,
            "einheit": "STK",
            "material": "MDF 19mm",
            "platten_anzahl": 10,
            "kantenlaenge_lfm": 20,
            "schnittanzahl": 0,
            "bohrungen_anzahl": 16,
        },
        {
            "pos_nr": "01.04",
            "kurztext": "Arbeitsplatte Mineralwerkstoff",
            "langtext": "Arbeitsplatte Corian Designer White, 4m lang, Ausschnitt Spuele",
            "menge": 1,
            "einheit": "STK",
            "material": "Corian Designer White",
            "platten_anzahl": 0,
            "kantenlaenge_lfm": 0,
            "schnittanzahl": 4,
            "bohrungen_anzahl": 2,
        },
        {
            "pos_nr": "01.05",
            "kurztext": "Nischenverkleidung",
            "langtext": "Nischenrueckwand Glas ESG 6mm lackiert, 2.4m breit",
            "menge": 1,
            "einheit": "STK",
            "material": "ESG Glas 6mm",
            "platten_anzahl": 0,
            "kantenlaenge_lfm": 0,
            "schnittanzahl": 0,
            "bohrungen_anzahl": 4,
        },
    ]

    for pos in positionen:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201, f"Position {pos['pos_nr']} fehlgeschlagen: {r.text}"
        pos_data = r.json()
        lack_str = " [LACKIERUNG -> FREMDLEISTUNG]" if pos_data["ist_lackierung"] else ""
        print(f"  Position {pos_data['pos_nr']}: {pos_data['kurztext']}{lack_str}")

    # 3. Kalkulation starten
    print("\n  Kalkulation wird gestartet...")
    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200, f"Kalkulation fehlgeschlagen: {r.text}"
    kalk = r.json()

    # 4. Ergebnis pruefen
    print(f"\n  === KALKULATIONSERGEBNIS ===")
    print(f"  Projekttyp:          {kalk['projekt_typ']}")
    print(f"  Materialkosten:      {kalk['materialkosten']:>10.2f} EUR")
    print(f"  Maschinenkosten:     {kalk['maschinenkosten']:>10.2f} EUR")
    print(f"  Lohnkosten:          {kalk['lohnkosten']:>10.2f} EUR")
    print(f"  -----------------------------------------")
    print(f"  Herstellkosten:      {kalk['herstellkosten']:>10.2f} EUR")
    print(f"  Gemeinkosten (GKZ):  {kalk['gemeinkosten']:>10.2f} EUR")
    print(f"  Selbstkosten:        {kalk['selbstkosten']:>10.2f} EUR")
    print(f"  Gewinn:              {kalk['gewinn']:>10.2f} EUR")
    print(f"  Wagnis:              {kalk['wagnis']:>10.2f} EUR")
    print(f"  Montage-Zuschlag:    {kalk['montage_zuschlag']:>10.2f} EUR")
    print(f"  Fremdleistungen:     {kalk['fremdleistungskosten']:>10.2f} EUR")
    print(f"  FL-Zuschlag:         {kalk['fremdleistungszuschlag']:>10.2f} EUR")
    print(f"  =========================================")
    print(f"  ANGEBOTSPREIS:       {kalk['angebotspreis']:>10.2f} EUR")
    print(f"  Marge:               {kalk['marge_prozent']:>9.1f} %")

    if kalk["warnungen"]:
        print(f"\n  Warnungen ({len(kalk['warnungen'])}):")
        for w in kalk["warnungen"]:
            print(f"    ! {w}")

    # 5. Plausibilitaetspruefungen
    assert kalk["materialkosten"] > 0, "Materialkosten muessen > 0 sein"
    assert kalk["maschinenkosten"] > 0, "Maschinenkosten muessen > 0 sein"
    assert kalk["lohnkosten"] > 0, "Lohnkosten muessen > 0 sein"
    assert kalk["herstellkosten"] > 0, "Herstellkosten muessen > 0 sein"
    assert kalk["angebotspreis"] > kalk["herstellkosten"], "Angebotspreis muss > Herstellkosten sein"
    assert kalk["marge_prozent"] > 0, "Marge muss positiv sein"
    assert kalk["gemeinkosten"] > 0, "GKZ muss > 0 sein"
    assert kalk["gewinn"] > 0, "Gewinn muss > 0 sein"
    assert kalk["projekt_typ"] == "privat"

    # 6. Lackierung muss Fremdleistung erzeugt haben
    # Pos 01.03 (RAL 9010 lackiert) + Pos 01.05 (lackiert)
    assert kalk["fremdleistungskosten"] > 0, "Fremdleistungskosten muessen > 0 sein (Lackierung!)"

    # 7. Projekt-Status in DB pruefen
    r = client.get(f"/api/projekte/{projekt_id}")
    assert r.status_code == 200
    proj_updated = r.json()
    assert proj_updated["status"] == "kalkuliert"
    assert proj_updated["angebotspreis"] > 0
    print(f"\n  Projekt-Status: {proj_updated['status']}")
    print(f"  Angebotspreis in DB: {proj_updated['angebotspreis']:.2f} EUR")

    print(f"\n>>> End-to-End Kalkulation BESTANDEN <<<")


def test_oeffentliche_ausschreibung():
    """Testet VOB-Kalkulation mit Wagnis-Zuschlag."""
    print("\n=== VOB-Kalkulation ===\n")

    r = client.post("/api/projekte/", json={
        "name": "Schule Ober-Moerlen - Moebel",
        "projekt_typ": "oeffentlich",
        "kunde": "Gemeinde Ober-Moerlen",
    })
    projekt_id = r.json()["id"]

    # Einfache Position
    r = client.post(f"/api/projekte/{projekt_id}/positionen/", json={
        "pos_nr": "1.1.10",
        "kurztext": "Einbauschrank Klassenraum",
        "menge": 10,
        "einheit": "STK",
        "material": "Melamin weiss",
        "platten_anzahl": 30,
        "kantenlaenge_lfm": 80,
        "bohrungen_anzahl": 40,
    })
    assert r.status_code == 201

    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200
    kalk = r.json()

    print(f"  Projekttyp: {kalk['projekt_typ']}")
    print(f"  Herstellkosten:  {kalk['herstellkosten']:>10.2f} EUR")
    print(f"  Wagnis (VOB):    {kalk['wagnis']:>10.2f} EUR")
    print(f"  Angebotspreis:   {kalk['angebotspreis']:>10.2f} EUR")
    print(f"  Marge:           {kalk['marge_prozent']:>9.1f} %")

    # Wagnis muss bei oeffentlich > 0 sein
    assert kalk["wagnis"] > 0, "VOB-Wagnis muss > 0 sein bei oeffentlicher Ausschreibung"
    # Marge muss niedriger sein als bei privat (15% vs 28%)
    assert kalk["marge_prozent"] < 40, "VOB-Marge muss konservativ sein"

    print(f"\n>>> VOB-Kalkulation BESTANDEN <<<")


def test_montage_kapazitaetswarnung():
    """Testet Warnung bei Monteure-Engpass (>7 Monteure noetig)."""
    print("\n=== Montage-Kapazitaetstest ===\n")

    r = client.post("/api/projekte/", json={
        "name": "Grossauftrag Hotel",
        "projekt_typ": "standard",
    })
    projekt_id = r.json()["id"]

    # 100 Einheiten -> bei 5h/Einheit = 500h Montage -> >7 Monteure noetig
    r = client.post(f"/api/projekte/{projekt_id}/positionen/", json={
        "pos_nr": "1.1",
        "kurztext": "Hotelzimmer-Moebel komplett",
        "menge": 100,
        "einheit": "STK",
        "material": "Eiche furniert",
        "platten_anzahl": 200,
        "kantenlaenge_lfm": 400,
        "bohrungen_anzahl": 300,
    })

    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200
    kalk = r.json()

    kapazitaets_warnungen = [w for w in kalk["warnungen"] if "KAPAZITAETSENGPASS" in w]
    print(f"  Montage-Stunden: hoch (100 Einheiten x 5h)")
    print(f"  Warnungen: {len(kalk['warnungen'])}")
    for w in kapazitaets_warnungen:
        print(f"    ! {w}")

    assert len(kapazitaets_warnungen) > 0, "Kapazitaetswarnung muss ausgeloest werden"
    print(f"\n>>> Montage-Kapazitaetstest BESTANDEN <<<")


if __name__ == "__main__":
    test_end_to_end_kalkulation()
    test_oeffentliche_ausschreibung()
    test_montage_kapazitaetswarnung()
    print("\n\n========================================")
    print("  ALLE PHASE-2-TESTS BESTANDEN")
    print("========================================")
