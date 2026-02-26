"""
Tests fuer den Lern-Agent (Memory Layer).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation, export as export_routes, lernen
from api.database import init_db_sync

# Setup
init_db_sync()
app_config = AppConfig(config_dir=Path(__file__).parent.parent / "config")
config_routes.set_config(app_config)
pipeline = _init_pipeline(app_config)
kalkulation.set_pipeline(pipeline)
export_routes.set_pipeline(pipeline)
lernen.set_pipeline(pipeline)

client = TestClient(app, raise_server_exceptions=True)


def test_01_statistik_leer():
    """Statistik bei leerer Datenbank."""
    print("\n=== 1. Statistik (leere DB) ===\n")

    r = client.get("/api/lernen/statistik")
    assert r.status_code == 200
    data = r.json()
    print(f"  Gesamt-Positionen: {data['gesamt_positionen']}")
    print(f"  Gesamt-Projekte: {data['gesamt_projekte']}")
    print(f"  Durchschnitt EP: {data['durchschnitt_ep']}")

    print(">>> Statistik (leer) BESTANDEN <<<")


def test_02_projekt_speichern():
    """Projekt kalkulieren und in Lernhistorie speichern."""
    print("\n=== 2. Projekt speichern ===\n")

    # Projekt + Positionen anlegen
    r = client.post("/api/projekte/", json={
        "name": "Lerntest Kueche",
        "projekt_typ": "privat",
        "kunde": "Familie Mueller",
    })
    projekt_id = r.json()["id"]
    print(f"  Projekt: {projekt_id}")

    positionen_data = [
        {
            "pos_nr": "01.01",
            "kurztext": "Unterschrank Eiche furniert",
            "menge": 6,
            "einheit": "STK",
            "material": "Eiche furniert",
            "platten_anzahl": 18,
            "kantenlaenge_lfm": 36,
            "bohrungen_anzahl": 24,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Haengeschrank Glas",
            "menge": 4,
            "einheit": "STK",
            "material": "MDF 19mm",
            "platten_anzahl": 8,
            "kantenlaenge_lfm": 16,
            "bohrungen_anzahl": 12,
        },
        {
            "pos_nr": "01.03",
            "kurztext": "Arbeitsplatte Granit poliert",
            "menge": 1,
            "einheit": "STK",
            "material": "Granit",
            "platten_anzahl": 0,
            "kantenlaenge_lfm": 0,
            "bohrungen_anzahl": 0,
        },
    ]
    for pos in positionen_data:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201

    # Kalkulieren
    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200
    kalk = r.json()
    print(f"  Angebotspreis: {kalk['angebotspreis']:,.2f} EUR")

    # In Lernhistorie speichern (Positionen aus DB laden, dort stehen die Kosten)
    r = client.post(f"/api/lernen/{projekt_id}/speichern", json={
        "ergebnis": "gewonnen",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "gespeichert"
    assert data["positionen_gespeichert"] == 3
    print(f"  Gespeichert: {data['positionen_gespeichert']} Positionen")
    print(f"  Ergebnis: {data['ergebnis']}")

    print(">>> Projekt speichern BESTANDEN <<<")
    return projekt_id


def test_03_zweites_projekt():
    """Zweites Projekt speichern fuer Vergleichsdaten."""
    print("\n=== 3. Zweites Projekt (Vergleichsdaten) ===\n")

    r = client.post("/api/projekte/", json={
        "name": "Lerntest Buero",
        "projekt_typ": "oeffentlich",
        "kunde": "Stadtverwaltung",
    })
    projekt_id = r.json()["id"]

    positionen_data = [
        {
            "pos_nr": "01.01",
            "kurztext": "Einbauschrank Melamin weiss",
            "menge": 8,
            "einheit": "STK",
            "material": "Melamin beschichtet",
            "platten_anzahl": 24,
            "kantenlaenge_lfm": 48,
            "bohrungen_anzahl": 32,
        },
        {
            "pos_nr": "01.02",
            "kurztext": "Regalwand Buche Multiplex",
            "menge": 6,
            "einheit": "STK",
            "material": "Buche Multiplex 18mm",
            "platten_anzahl": 12,
            "kantenlaenge_lfm": 24,
            "bohrungen_anzahl": 20,
        },
    ]
    for pos in positionen_data:
        r = client.post(f"/api/projekte/{projekt_id}/positionen/", json=pos)
        assert r.status_code == 201

    r = client.post(f"/api/kalkulation/starten/{projekt_id}")
    assert r.status_code == 200

    # Speichern als verlorenes Projekt (Positionen aus DB)
    r = client.post(f"/api/lernen/{projekt_id}/speichern", json={
        "ergebnis": "verloren",
    })
    assert r.status_code == 200
    print(f"  Projekt {projekt_id}: {r.json()['positionen_gespeichert']} Positionen (verloren)")

    print(">>> Zweites Projekt BESTANDEN <<<")
    return projekt_id


def test_04_statistik_gefuellt():
    """Statistik nach dem Speichern."""
    print("\n=== 4. Statistik (gefuellt) ===\n")

    r = client.get("/api/lernen/statistik")
    assert r.status_code == 200
    data = r.json()

    print(f"  Gesamt-Positionen: {data['gesamt_positionen']}")
    print(f"  Gesamt-Projekte: {data['gesamt_projekte']}")
    print(f"  Durchschnitt EP: {data['durchschnitt_ep']:.2f} EUR")
    print(f"  Gewinnquote: {data['gewinnquote']['gewonnen']}W / {data['gewinnquote']['verloren']}V "
          f"= {data['gewinnquote']['quote_prozent']:.0f}%")

    assert data["gesamt_positionen"] >= 5
    assert data["gesamt_projekte"] >= 2
    assert data["gewinnquote"]["gewonnen"] >= 3  # Kueche: 3 Pos gewonnen
    assert data["gewinnquote"]["verloren"] >= 2  # Buero: 2 Pos verloren

    print(f"\n  Haeufigste Typen:")
    for t in data["haeufigste_typen"]:
        print(f"    {t['typ']}: {t['anzahl']}x (avg {t['avg_ep']:.2f} EUR)")

    print(f"\n  Haeufigste Materialien:")
    for m in data["haeufigste_materialien"]:
        print(f"    {m['material']}: {m['anzahl']}x (avg {m['avg_ep']:.2f} EUR)")

    print("\n>>> Statistik (gefuellt) BESTANDEN <<<")


def test_05_preisvorschlag():
    """Preisvorschlag fuer aehnliche Position."""
    print("\n=== 5. Preisvorschlag ===\n")

    # Aehnlich wie Kueche-Projekt: Einbauschrank
    r = client.post("/api/lernen/vorschlag", json={
        "kurztext": "Einbauschrank Buero",
        "material": "Melamin weiss",
        "menge": 4,
    })
    assert r.status_code == 200
    data = r.json()

    print(f"  Position: Einbauschrank Buero (Melamin weiss, 4 STK)")
    print(f"  Erkannter Typ: {data['position_typ']}")
    print(f"  Material-Kategorie: {data['material_kategorie']}")
    print(f"  Empfohlener EP: {data['empfohlener_ep']:.2f} EUR")
    print(f"  Preisspanne: {data['preisspanne']['min']:.2f} - {data['preisspanne']['max']:.2f} EUR")
    print(f"  Basis: {data['basis']}")
    print(f"  Vorschlaege: {len(data['vorschlaege'])}")
    for v in data["vorschlaege"][:3]:
        print(f"    {v['notizen'][:60]} | EP: {v['kalkulierter_preis']:.2f} EUR | {v['ergebnis']}")

    assert data["position_typ"] == "einbauschrank"
    assert len(data["vorschlaege"]) > 0

    print("\n>>> Preisvorschlag BESTANDEN <<<")


def test_06_ist_werte():
    """Ist-Werte nachtragen und Abweichungen pruefen."""
    print("\n=== 6. Ist-Werte eintragen ===\n")

    # Alle Lernhistorie-Eintraege holen (direkt aus DB)
    import sqlite3
    conn = sqlite3.connect("data/kalkulation.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, kalkulierter_preis, notizen FROM lernhistorie").fetchall()
    conn.close()

    print(f"  {len(rows)} Positionen in Lernhistorie")

    # Ist-Werte eintragen: 10% hoeher als kalkuliert (typische Praxis)
    ist_werte = []
    for row in rows[:3]:  # Nur Kueche-Projekt (erste 3)
        kalk_preis = row["kalkulierter_preis"]
        # Falls kalk_preis 0, setze einen realistischen Wert
        if kalk_preis == 0:
            kalk_preis = 500.0
        ist_preis = round(kalk_preis * 1.10, 2)  # 10% teurer als kalkuliert
        ist_werte.append({"id": row["id"], "tatsaechlicher_preis": ist_preis})
        print(f"    ID {row['id']}: Kalk {row['kalkulierter_preis']:.2f} -> Ist {ist_preis:.2f}")

    r = client.post(f"/api/lernen/dummy/ist-werte", json={
        "ist_werte": ist_werte,
        "ergebnis": "beauftragt",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["positionen_aktualisiert"] == 3
    print(f"\n  Aktualisiert: {data['positionen_aktualisiert']} Positionen")

    print(">>> Ist-Werte BESTANDEN <<<")


def test_07_abweichungsanalyse():
    """Abweichungsanalyse nach Ist-Werten."""
    print("\n=== 7. Abweichungsanalyse ===\n")

    r = client.get("/api/lernen/abweichungen?limit=10")
    assert r.status_code == 200
    data = r.json()

    print(f"  Top-Abweichungen: {len(data['top_abweichungen'])}")
    for a in data["top_abweichungen"]:
        print(f"    {a['position_typ']}/{a['material']}: "
              f"Kalk {a['kalkuliert']:.2f} / Ist {a['tatsaechlich']:.2f} "
              f"= {a['abweichung_prozent']:+.1f}%")

    print(f"\n  Typ-Trends: {len(data['typ_trends'])}")
    for t in data["typ_trends"]:
        print(f"    {t['position_typ']}: {t['avg_abweichung_prozent']:+.1f}% "
              f"({t['anzahl_projekte']} Projekte)")

    if data["empfehlungen"]:
        print(f"\n  Empfehlungen:")
        for e in data["empfehlungen"]:
            print(f"    >> {e}")

    assert len(data["top_abweichungen"]) == 3  # 3 Positionen mit Ist-Werten

    print("\n>>> Abweichungsanalyse BESTANDEN <<<")


def test_08_plausibilitaet():
    """Plausibilitaets-Check bei neuer Kalkulation."""
    print("\n=== 8. Plausibilitaets-Check ===\n")

    # Neues Projekt mit bewusst extremen Werten
    r = client.post("/api/projekte/", json={
        "name": "Plausibilitaetstest",
        "projekt_typ": "standard",
    })
    projekt_id = r.json()["id"]

    # Position mit absichtlich hohen Materialkosten
    positionen = [
        {
            "pos_nr": "01.01",
            "kurztext": "Einbauschrank Eiche massiv",
            "menge": 2,
            "einheit": "STK",
            "material": "Eiche massiv",
            "materialkosten": 5000,  # Absichtlich hoch
            "maschinenkosten": 200,
            "lohnkosten": 800,
            "platten_anzahl": 8,
        },
    ]

    r = client.post(f"/api/lernen/{projekt_id}/plausibilitaet", json={
        "positionen": positionen,
        "kalkulation": {},
    })
    assert r.status_code == 200
    data = r.json()

    print(f"  Warnungen: {len(data['warnungen'])}")
    for w in data["warnungen"]:
        print(f"    !! {w}")
    print(f"  Vergleichsdaten: {len(data['vergleichsdaten'])}")
    for v in data["vergleichsdaten"]:
        print(f"    Pos {v['pos_nr']}: EP {v['ep_aktuell']:.2f} vs historisch {v['ep_historisch']:.2f} "
              f"({v['abweichung_prozent']:+.1f}%, {v['anzahl_referenzen']} Referenzen)")

    print("\n>>> Plausibilitaets-Check BESTANDEN <<<")


if __name__ == "__main__":
    test_01_statistik_leer()
    test_02_projekt_speichern()
    test_03_zweites_projekt()
    test_04_statistik_gefuellt()
    test_05_preisvorschlag()
    test_06_ist_werte()
    test_07_abweichungsanalyse()
    test_08_plausibilitaet()
    print("\n\n========================================")
    print("  ALLE LERN-AGENT-TESTS BESTANDEN")
    print("========================================")
