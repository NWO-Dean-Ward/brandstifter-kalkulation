"""
Tests fuer Korpus-Positionen in Projekt und Ausschreibung:
DB-Migration, Positions-Endpunkte, Pipeline (KorpusKalkulator + LeadAgent),
Werkstuecke, Kapazitaeten, Rueckfall auf die Standard-Schaetzung.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation, export
from api.database import DB_PATH, init_db_sync
from agents.base_agent import AgentMessage
from agents.korpus_generator import PreisKatalog, berechne_korpus, lade_regeln
from agents.korpus_kalkulator import parameter_aus_position
from agents.lohn_kalkulator import LohnKalkulator

ROOT = Path(__file__).parent.parent

init_db_sync()
_cfg = AppConfig(config_dir=ROOT / "config")
config_routes.set_config(_cfg)
_pipeline, _ = _init_pipeline(_cfg)
kalkulation.set_pipeline(_pipeline)
export.set_pipeline(_pipeline)
client = TestClient(app, raise_server_exceptions=False)

ZIMMERSCHRANK = {
    "typ": "hochschrank", "anzahl": 1, "breite_mm": 1000, "hoehe_mm": 2000, "tiefe_mm": 600,
    "einlegeboeden": 4, "tueren": 2, "sockel_hoehe_mm": 100,
    "korpus_material": "Egger W1000 ST9", "front_material": "Egger H1345 ST32",
    "front_maserung": True, "rueckwand_material": "HDF weiss",
}


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _projekt_mit_positionen():
    pid = client.post("/api/projekte/", json={
        "name": "Test Korpus-Ausschreibung", "projekt_typ": "oeffentlich", "kunde": "Pflegeheim",
    }).json()["id"]
    ids = {}
    for nr, text, menge, material, platten in [
        ("01.01", "Zimmerschrank 1000x2000", 40, "", 0),
        ("01.02", "Blende", 1, "Egger W1000", 0.2),
    ]:
        r = client.post(f"/api/projekte/{pid}/positionen/", json={
            "pos_nr": nr, "kurztext": text, "menge": menge, "einheit": "STK",
            "material": material, "platten_anzahl": platten, "kantenlaenge_lfm": 3,
        })
        ids[nr] = r.json()["id"]
    return pid, ids


def _positionen(pid):
    return {p["pos_nr"]: p for p in client.get(f"/api/projekte/{pid}/positionen/").json()}


def _werkstuecke(pid):
    return client.get(f"/api/projekte/{pid}/werkstuecke/").json()


# === DB-Migration ===

def test_migration_ergaenzt_spalten_in_alter_db(tmp_path):
    # Bestehende DB nachbilden: aktuelles Schema ohne die nachtraeglich ergaenzten Spalten
    db = tmp_path / "alt.db"
    init_db_sync(db)
    conn = sqlite3.connect(db)
    for tabelle, spalte in [("positionen", "kalkulationsquelle"), ("positionen", "korpus_parameter"),
                            ("werkstuecke", "quelle")]:
        conn.execute(f"ALTER TABLE {tabelle} DROP COLUMN {spalte}")
    conn.commit()
    conn.close()
    init_db_sync(db)
    init_db_sync(db)   # zweimal: Migration ist idempotent
    conn = sqlite3.connect(db)
    pos_spalten = {r[1] for r in conn.execute("PRAGMA table_info(positionen)")}
    ws_spalten = {r[1] for r in conn.execute("PRAGMA table_info(werkstuecke)")}
    conn.close()
    assert {"kalkulationsquelle", "korpus_parameter"} <= pos_spalten
    assert "quelle" in ws_spalten


# === Parameter aus Position ===

def test_parameter_menge_mal_je_einheit():
    pos = {"menge": 2.5, "kurztext": "Schrankwand", "korpus_parameter": json.dumps({**ZIMMERSCHRANK, "anzahl": 3})}
    p = parameter_aus_position(pos)
    assert p.anzahl == 8                       # ceil(2.5 x 3)
    assert p.bezeichnung == "Schrankwand"
    with pytest.raises(ValueError, match="Menge"):
        parameter_aus_position({**pos, "menge": 0})
    with pytest.raises(ValueError, match="Keine Korpus-Parameter"):
        parameter_aus_position({"menge": 1, "korpus_parameter": ""})


# === Positions-Endpunkte ===

def test_korpus_setzen_schreibt_werkstuecke():
    pid, ids = _projekt_mit_positionen()
    r = client.put(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus", json=ZIMMERSCHRANK)
    assert r.status_code == 200
    assert r.json()["position"]["kalkulationsquelle"] == "korpus"
    assert json.loads(r.json()["position"]["korpus_parameter"])["anzahl"] == 1
    ws = {w["bezeichnung"]: w for w in _werkstuecke(pid)}
    assert ws["Seite"]["anzahl"] == 80 and ws["Seite"]["quelle"] == "korpus-generator"
    assert ws["Seite"]["position_id"] == ids["01.01"]
    assert ws["Tuer"]["anzahl"] == 80


@pytest.mark.parametrize("body, status, text", [
    ({**ZIMMERSCHRANK, "typ": "regal"}, 422, "Unbekannter Korpus-Typ"),
    ({**ZIMMERSCHRANK, "hoehe_mm": 900, "tueren": 1, "schubkaesten": 8}, 422, "Schubkaesten"),
])
def test_korpus_setzen_ungueltig(body, status, text):
    pid, ids = _projekt_mit_positionen()
    r = client.put(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus", json=body)
    assert r.status_code == status
    assert text in r.json()["detail"]
    assert _positionen(pid)["01.01"]["kalkulationsquelle"] == ""


def test_korpus_unbekannte_position():
    pid, _ = _projekt_mit_positionen()
    assert client.put(f"/api/projekte/{pid}/positionen/999999/korpus", json=ZIMMERSCHRANK).status_code == 404


# === Pipeline ===

def test_kalkulation_rechnet_korpus_position_mit_generator():
    pid, ids = _projekt_mit_positionen()
    client.put(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus", json=ZIMMERSCHRANK)
    r = client.post(f"/api/kalkulation/starten/{pid}")
    assert r.status_code == 200
    kalk = r.json()
    pos = _positionen(pid)

    # Material der Korpus-Position = Platten + Kantenmaterial + Beschlaege des Generators
    erwartet = berechne_korpus(
        parameter_aus_position(pos["01.01"]), regeln=lade_regeln(ROOT / "config" / "korpus.yaml"),
        maschinen_cfg=_cfg.maschinen, katalog=PreisKatalog.aus_db(DB_PATH),
    )
    material = (sum(p["kosten"] for p in erwartet["platten"])
                + sum(k["lfm"] * k["preis_lfm"] for k in erwartet["kanten"])
                + sum(b["kosten"] for b in erwartet["beschlaege"]))
    assert pos["01.01"]["materialkosten"] == pytest.approx(material, abs=0.05)
    assert pos["01.01"]["lohnkosten"] > 0 and pos["01.01"]["maschinenkosten"] > 0

    # Positionspreise passen zum Angebotspreis
    summe = sum(p["einheitspreis"] * p["menge"] for p in pos.values())
    assert summe == pytest.approx(kalk["angebotspreis"], abs=0.01)
    assert any("Pos 01.01:" in w for w in kalk["warnungen"])


def test_cnc_kapazitaet_enthaelt_korpus_stunden():
    pid, ids = _projekt_mit_positionen()
    client.put(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus", json=ZIMMERSCHRANK)
    positionen = list(_positionen(pid).values())
    msg = AgentMessage(sender="test", receiver="lead_agent", msg_type="kalkuliere_positionen",
                       payload={"positionen": positionen, "projekt_typ": "oeffentlich"}, projekt_id=pid)
    res = _run(_pipeline.execute(msg)).payload
    korpus_einsatz = [e for e in res["maschinenkosten"]["maschineneinsaetze"] if e.get("quelle") == "korpus"]
    assert len(korpus_einsatz) == 1
    assert res["maschinenkosten"]["cnc_stunden_total"] >= korpus_einsatz[0]["cnc_stunden"]
    assert res["lohnkosten"]["montage_plan"]["gesamt_stunden"] >= 40   # 40 Schraenke x 1 h Montage
    assert res["korpus_stuecklisten"][0]["pos_nr"] == "01.01"


def test_mengenaenderung_aktualisiert_werkstuecke_manuelle_bleiben():
    pid, ids = _projekt_mit_positionen()
    client.put(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus", json=ZIMMERSCHRANK)
    client.post(f"/api/projekte/{pid}/werkstuecke/", json={
        "position_id": ids["01.01"], "bezeichnung": "Sonderblende manuell", "anzahl": 2,
    })
    client.patch(f"/api/projekte/{pid}/positionen/{ids['01.01']}", json={
        "pos_nr": "01.01", "kurztext": "Zimmerschrank 1000x2000", "menge": 60, "einheit": "STK",
    })
    assert _positionen(pid)["01.01"]["kalkulationsquelle"] == "korpus"   # PATCH laesst den Korpus stehen
    client.post(f"/api/kalkulation/starten/{pid}")
    ws = {w["bezeichnung"]: w for w in _werkstuecke(pid)}
    assert ws["Seite"]["anzahl"] == 120
    assert ws["Sonderblende manuell"]["quelle"] == ""


def test_korpus_entfernen():
    pid, ids = _projekt_mit_positionen()
    client.put(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus", json=ZIMMERSCHRANK)
    r = client.delete(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus")
    assert r.status_code == 200
    assert r.json()["kalkulationsquelle"] == "" and r.json()["korpus_parameter"] == ""
    assert _werkstuecke(pid) == []
    assert client.post(f"/api/kalkulation/starten/{pid}").status_code == 200


def test_ungueltige_parameter_fallen_auf_standard_zurueck():
    pid, ids = _projekt_mit_positionen()
    # Parameter, die inzwischen ungueltig sind (z.B. nach Aenderung der korpus.yaml)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE positionen SET kalkulationsquelle = 'korpus', korpus_parameter = ? WHERE id = ?",
                 (json.dumps({**ZIMMERSCHRANK, "typ": "regal"}), ids["01.01"]))
    conn.commit()
    conn.close()
    r = client.post(f"/api/kalkulation/starten/{pid}")
    assert r.status_code == 200
    assert any("Standard-Schaetzung verwendet" in w for w in r.json()["warnungen"])
    assert _positionen(pid)["01.01"]["einheitspreis"] > 0


def test_projekt_kopie_behaelt_korpus():
    pid, ids = _projekt_mit_positionen()
    client.put(f"/api/projekte/{pid}/positionen/{ids['01.01']}/korpus", json=ZIMMERSCHRANK)
    kopie = client.post(f"/api/projekte/{pid}/kopieren").json()["id"]
    pos = _positionen(kopie)["01.01"]
    assert pos["kalkulationsquelle"] == "korpus"
    assert json.loads(pos["korpus_parameter"])["breite_mm"] == 1000


# === Lohn: Korpus-Montage in Monteurplanung und Transport ===

def test_lohnkalkulator_zusatz_montage():
    agent = LohnKalkulator()
    agent.load_config(yaml.safe_load(open(ROOT / "config" / "stundensaetze.yaml", encoding="utf-8")))

    def rechne(zusatz):
        msg = AgentMessage(sender="test", receiver="lohn_kalkulator", msg_type="kalkuliere_lohn", payload={
            "positionen": [{"pos_nr": "1", "menge": 1, "platten_anzahl": 1}], "zusatz_montage": zusatz,
        })
        return _run(agent.execute(msg)).payload

    ohne = rechne([])
    mit = rechne([{"pos_nr": "K", "stunden": 300, "einheiten": 60}])
    assert mit["montage_plan"]["gesamt_stunden"] == ohne["montage_plan"]["gesamt_stunden"] + 300
    assert mit["montage_plan"]["monteure_benoetigt"] > ohne["montage_plan"]["monteure_benoetigt"]
    assert mit["gewerke"]["transport"]["stunden"] > ohne["gewerke"]["transport"]["stunden"]
    # Die Korpus-Position bekommt nur ihren Transport-Anteil, ihr eigener Lohn kommt vom KorpusKalkulator
    korpus = {p["pos_nr"]: p for p in mit["positionen"]}["K"]
    assert korpus["montage_stunden"] == 300
    assert 0 < korpus["kosten"] < mit["lohnkosten_gesamt"]
