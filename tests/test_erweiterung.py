"""
Tests fuer die Erweiterung: Werkstuecke, Zukaufteile, Ueberschreibungen,
AnalyseAgent (Egger-Mapping), EinkaufsAgent.
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation, export, analyse, einkauf
from api.database import init_db_sync


def setup():
    init_db_sync()
    app_config = AppConfig(config_dir=Path(__file__).parent.parent / "config")
    config_routes.set_config(app_config)
    from api.main import _init_pipeline
    pipeline = _init_pipeline(app_config)
    kalkulation.set_pipeline(pipeline)
    export.set_pipeline(pipeline)
    analyse.set_pipeline(pipeline)
    einkauf.set_pipeline(pipeline)


setup()
client = TestClient(app, raise_server_exceptions=False)

# --- Hilfsfunktionen ---

_projekt_id = None


def _create_projekt():
    global _projekt_id
    if _projekt_id:
        return _projekt_id
    r = client.post("/api/projekte/", json={
        "name": "Test Erweiterung", "projekt_typ": "standard", "kunde": "TestKunde"
    })
    assert r.status_code == 201
    _projekt_id = r.json()["id"]
    return _projekt_id


def _create_position(projekt_id):
    r = client.post(f"/api/projekte/{projekt_id}/positionen/", json={
        "pos_nr": "01.01", "kurztext": "Testposition", "menge": 5, "einheit": "STK",
    })
    assert r.status_code == 201
    return r.json()["id"]


# === WERKSTUECKE ===

def test_01_werkstuecke_leer():
    pid = _create_projekt()
    r = client.get(f"/api/projekte/{pid}/werkstuecke/")
    assert r.status_code == 200
    assert r.json() == []
    print("  Werkstuecke leer: OK")


def test_02_werkstueck_erstellen():
    pid = _create_projekt()
    r = client.post(f"/api/projekte/{pid}/werkstuecke/", json={
        "bezeichnung": "Seitenwand links",
        "anzahl": 2,
        "laenge_mm": 800,
        "breite_mm": 600,
        "staerke_mm": 19,
        "material": "Spanplatte",
        "oberflaeche": "Melamin",
        "fertigung": "cnc-nesting",
    })
    assert r.status_code == 201
    ws = r.json()
    assert ws["bezeichnung"] == "Seitenwand links"
    assert ws["anzahl"] == 2
    assert ws["laenge_mm"] == 800
    assert ws["staerke_mm"] == 19
    assert ws["ist_fremdleistung"] is False
    print(f"  Werkstueck erstellt: #{ws['id']}")


def test_03_werkstueck_lackierung_fremdleistung():
    pid = _create_projekt()
    r = client.post(f"/api/projekte/{pid}/werkstuecke/", json={
        "bezeichnung": "Front lackiert",
        "anzahl": 1,
        "laenge_mm": 500,
        "breite_mm": 400,
        "staerke_mm": 19,
        "material": "MDF",
        "oberflaeche": "Lackiert-extern",
        "fertigung": "cnc-nesting",
    })
    assert r.status_code == 201
    ws = r.json()
    assert ws["ist_fremdleistung"] is True
    print(f"  Lackierung = Fremdleistung: OK")


def test_04_werkstueck_liste():
    pid = _create_projekt()
    r = client.get(f"/api/projekte/{pid}/werkstuecke/")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2
    print(f"  Werkstuecke Liste: {len(data)} Stueck")


def test_05_werkstueck_loeschen():
    pid = _create_projekt()
    # Erstellen
    r = client.post(f"/api/projekte/{pid}/werkstuecke/", json={
        "bezeichnung": "Zum Loeschen", "laenge_mm": 100, "breite_mm": 100,
    })
    ws_id = r.json()["id"]
    # Loeschen
    r = client.delete(f"/api/projekte/{pid}/werkstuecke/{ws_id}")
    assert r.status_code == 204
    print(f"  Werkstueck geloescht: #{ws_id}")


# === ZUKAUFTEILE ===

def test_06_zukaufteile_leer():
    pid = _create_projekt()
    r = client.get(f"/api/projekte/{pid}/zukaufteile/")
    assert r.status_code == 200
    print("  Zukaufteile initial: OK")


def test_07_zukaufteil_erstellen():
    pid = _create_projekt()
    r = client.post(f"/api/projekte/{pid}/zukaufteile/", json={
        "bezeichnung": "Blum Topfband",
        "hersteller": "Blum",
        "artikel_nr": "71B3550",
        "einkaufspreis": 4.50,
        "menge": 10,
        "aufschlag_prozent": 15.0,
        "status": "ausstehend",
        "quelle": "blum",
    })
    assert r.status_code == 201
    zt = r.json()
    assert zt["bezeichnung"] == "Blum Topfband"
    assert zt["einkaufspreis"] == 4.50
    assert zt["menge"] == 10
    # VK = 4.50 * 10 * 1.15 = 51.75
    assert zt["verkaufspreis"] == 51.75
    print(f"  Zukaufteil erstellt: #{zt['id']} VK={zt['verkaufspreis']}")


def test_08_zukaufteil_update():
    pid = _create_projekt()
    # Erstellen
    r = client.post(f"/api/projekte/{pid}/zukaufteile/", json={
        "bezeichnung": "Haefele Griff", "einkaufspreis": 12.0, "menge": 5,
        "aufschlag_prozent": 20.0, "quelle": "haefele",
    })
    zt_id = r.json()["id"]
    # Update
    r = client.patch(f"/api/projekte/{pid}/zukaufteile/{zt_id}", json={
        "bezeichnung": "Haefele Griff Edelstahl", "einkaufspreis": 15.0, "menge": 5,
        "aufschlag_prozent": 20.0, "quelle": "haefele",
    })
    assert r.status_code == 200
    zt = r.json()
    assert zt["bezeichnung"] == "Haefele Griff Edelstahl"
    # VK = 15.0 * 5 * 1.20 = 90.0
    assert zt["verkaufspreis"] == 90.0
    print(f"  Zukaufteil updated: VK={zt['verkaufspreis']}")


def test_09_zukaufteil_loeschen():
    pid = _create_projekt()
    r = client.post(f"/api/projekte/{pid}/zukaufteile/", json={
        "bezeichnung": "Zum Loeschen", "einkaufspreis": 1.0,
    })
    zt_id = r.json()["id"]
    r = client.delete(f"/api/projekte/{pid}/zukaufteile/{zt_id}")
    assert r.status_code == 204
    print(f"  Zukaufteil geloescht: #{zt_id}")


# === UEBERSCHREIBUNGEN ===

def test_10_ueberschreibung_erstellen():
    pid = _create_projekt()
    pos_id = _create_position(pid)

    r = client.post(f"/api/projekte/{pid}/ueberschreibungen/", json={
        "position_id": pos_id,
        "feld": "einheitspreis",
        "neuer_wert": 150.0,
        "begruendung": "Erfahrungswert aus Altprojekt",
    })
    assert r.status_code == 201
    ov = r.json()
    assert ov["feld"] == "einheitspreis"
    assert ov["neuer_wert"] == 150.0
    assert ov["begruendung"] == "Erfahrungswert aus Altprojekt"
    assert ov["geaendert_von"] == "dean"
    print(f"  Ueberschreibung erstellt: #{ov['id']}")


def test_11_ueberschreibung_aktualisiert_position():
    pid = _create_projekt()
    pos_id = _create_position(pid)

    # EP ueberschreiben
    r = client.post(f"/api/projekte/{pid}/ueberschreibungen/", json={
        "position_id": pos_id, "feld": "einheitspreis",
        "neuer_wert": 200.0, "begruendung": "Kundenrabatt",
    })
    assert r.status_code == 201

    # Position pruefen: EP sollte 200, GP = 200 * 5 = 1000
    r = client.get(f"/api/projekte/{pid}/positionen/")
    pos = [p for p in r.json() if p["id"] == pos_id][0]
    assert pos["einheitspreis"] == 200.0
    assert pos["gesamtpreis"] == 1000.0
    print(f"  Position nach Ueberschreibung: EP={pos['einheitspreis']} GP={pos['gesamtpreis']}")


def test_12_ueberschreibung_ohne_begruendung():
    pid = _create_projekt()
    pos_id = _create_position(pid)

    r = client.post(f"/api/projekte/{pid}/ueberschreibungen/", json={
        "position_id": pos_id, "feld": "einheitspreis",
        "neuer_wert": 100.0, "begruendung": "",
    })
    assert r.status_code == 400
    assert "Pflicht" in r.json()["detail"]
    print("  Leere Begruendung abgelehnt: OK")


def test_13_ueberschreibung_ungueltig_feld():
    pid = _create_projekt()
    pos_id = _create_position(pid)

    r = client.post(f"/api/projekte/{pid}/ueberschreibungen/", json={
        "position_id": pos_id, "feld": "status",
        "neuer_wert": 1.0, "begruendung": "Test",
    })
    assert r.status_code == 400
    assert "nicht erlaubt" in r.json()["detail"]
    print("  Ungueltiges Feld abgelehnt: OK")


def test_14_ueberschreibung_liste():
    pid = _create_projekt()
    r = client.get(f"/api/projekte/{pid}/ueberschreibungen/")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    print(f"  Ueberschreibungen Liste: {len(data)} Eintraege")


# === POSITIONEN PATCH ===

def test_15_position_patch():
    pid = _create_projekt()
    pos_id = _create_position(pid)

    r = client.patch(f"/api/projekte/{pid}/positionen/{pos_id}", json={
        "pos_nr": "01.01", "kurztext": "Aktualisiert", "menge": 10, "einheit": "STK",
    })
    assert r.status_code == 200
    pos = r.json()
    assert pos["kurztext"] == "Aktualisiert"
    assert pos["menge"] == 10
    print(f"  Position gepatched: menge={pos['menge']}")


# === ANALYSE AGENT (Egger-Mapping) ===

def test_16_egger_dekor_mapping():
    from agents.analyse_agent import AnalyseAgent
    agent = AnalyseAgent()

    # W1000_19 -> Premium Weiss, 19mm
    info = agent._resolve_egger_code("W1000_19")
    assert info["egger_dekor"] == "W1000"
    assert info["egger_name"] == "Premium Weiss"
    assert info["staerke_mm"] == 19
    print(f"  W1000_19 -> {info['egger_name']} {info['staerke_mm']}mm")

    # U750 ST9 -> Taupe, Feelwood
    info = agent._resolve_egger_code("U750 ST9")
    assert info["egger_dekor"] == "U750"
    assert info["egger_name"] == "Taupe"
    assert info["egger_struktur"] == "ST9"
    assert "Feelwood" in info["egger_struktur_name"]
    print(f"  U750 ST9 -> {info['egger_name']} / {info['egger_struktur_name']}")

    # H1345 -> Eiche Sherman natur
    info = agent._resolve_egger_code("H1345")
    assert info["egger_name"] == "Eiche Sherman natur"
    print(f"  H1345 -> {info['egger_name']}")

    # Unbekannter Code
    info = agent._resolve_egger_code("X9999_25")
    assert info.get("egger_unbekannt") is True
    print("  Unbekannter Code erkannt: OK")


def test_17_egger_steindekor():
    from agents.analyse_agent import AnalyseAgent
    agent = AnalyseAgent()

    info = agent._resolve_egger_code("F186")
    assert info["egger_name"] == "Beton Chicago hellgrau"
    assert info["egger_kategorie"] == "steindekor"
    print(f"  F186 -> {info['egger_name']} ({info['egger_kategorie']})")


# === ANALYSE HISTORIE ===

def test_18_analyse_historie_leer():
    r = client.get("/api/analyse/historie")
    assert r.status_code == 200
    print(f"  Analyse Historie: {len(r.json())} Eintraege")


# === EINKAUFS-AGENT ===

def test_19_einkaufs_agent_instanziierbar():
    from agents.einkaufs_agent import EinkaufsAgent, _parse_german_price
    agent = EinkaufsAgent()
    assert agent.name == "einkaufs_agent"

    # Preis-Parser testen
    assert _parse_german_price("12,99 EUR") == 12.99
    assert _parse_german_price("1.234,56") == 1234.56
    assert _parse_german_price("") == 0.0
    assert _parse_german_price("ab 45,00 EUR") == 45.0
    print("  EinkaufsAgent + Preis-Parser: OK")


# === CONFIG: PARTNER-LOGINS ===

def test_20_config_partner_logins():
    from api.config_loader import AppConfig
    cfg = AppConfig(config_dir=Path(__file__).parent.parent / "config")
    logins = cfg.get_partner_logins()
    # Sollte leer sein (noch keine partner-logins.yaml)
    assert isinstance(logins, dict)
    print(f"  Partner-Logins: {len(logins)} Eintraege")


# === PROJEKT STATUS AENDERN ===

def test_21_projekt_status_aendern():
    pid = _create_projekt()
    r = client.patch(f"/api/projekte/{pid}", json={"status": "kalkuliert"})
    assert r.status_code == 200
    assert r.json()["status"] == "kalkuliert"
    print(f"  Status geaendert: kalkuliert")


def test_22_projekt_status_verloren():
    """Status 'verloren' sollte akzeptiert werden und Auto-Learn nicht crashen."""
    # Neues Projekt damit wir sauber testen
    r = client.post("/api/projekte/", json={
        "name": "Test Verloren", "projekt_typ": "standard", "kunde": "Verloren-Kunde"
    })
    assert r.status_code == 201
    pid = r.json()["id"]

    r = client.patch(f"/api/projekte/{pid}", json={"status": "verloren"})
    assert r.status_code == 200
    assert r.json()["status"] == "verloren"
    print(f"  Status verloren + Auto-Learn: OK")


def test_23_projekt_meta_update():
    pid = _create_projekt()
    r = client.patch(f"/api/projekte/{pid}", json={
        "name": "Umbenanntes Projekt",
        "kunde": "Neuer Kunde",
        "beschreibung": "Neue Beschreibung",
    })
    assert r.status_code == 200
    p = r.json()
    assert p["name"] == "Umbenanntes Projekt"
    assert p["kunde"] == "Neuer Kunde"
    assert p["beschreibung"] == "Neue Beschreibung"
    print(f"  Projekt Meta aktualisiert: OK")


def test_24_projekt_kopieren():
    """Projekt kopieren inkl. Positionen."""
    # Projekt mit Positionen erstellen
    r = client.post("/api/projekte/", json={
        "name": "Original Projekt", "projekt_typ": "oeffentlich", "kunde": "TestKunde"
    })
    assert r.status_code == 201
    orig_id = r.json()["id"]

    # 2 Positionen anlegen
    for i in range(1, 3):
        r = client.post(f"/api/projekte/{orig_id}/positionen/", json={
            "pos_nr": f"0{i}.01", "kurztext": f"Position {i}", "menge": i * 3, "einheit": "STK",
        })
        assert r.status_code == 201

    # Kopieren
    r = client.post(f"/api/projekte/{orig_id}/kopieren")
    assert r.status_code == 201
    kopie = r.json()
    assert "(Kopie)" in kopie["name"]
    assert kopie["status"] == "entwurf"
    assert kopie["id"] != orig_id
    assert kopie["kunde"] == "TestKunde"
    assert kopie["projekt_typ"] == "oeffentlich"

    # Positionen pruefen
    r = client.get(f"/api/projekte/{kopie['id']}/positionen/")
    assert r.status_code == 200
    pos = r.json()
    assert len(pos) == 2
    assert pos[0]["kurztext"] == "Position 1"
    assert pos[1]["kurztext"] == "Position 2"
    print(f"  Projekt kopiert: {kopie['id']} mit {len(pos)} Positionen")
