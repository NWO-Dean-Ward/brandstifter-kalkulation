"""
Tests fuer die Angebotspreise je Position (EP/GP).

Regressionsschutz fuer drei Fehler:
- EP/GP enthielten keine Zuschlaege (GKZ/Gewinn/Wagnis) -> GAEB-Summe unter Angebotspreis
- Lohn wurde gleichmaessig auf Positionen verteilt (1 Blende = 40 Schraenke)
- Fremdleistung (Lackierung) zaehlte doppelt (in Material mit GKZ/Gewinn und als Fremdleistung)
"""

import asyncio
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app, _init_pipeline
from api.config_loader import AppConfig
from api.routes import config as config_routes, kalkulation, export
from api.database import init_db_sync
from agents.base_agent import AgentMessage
from agents.lohn_kalkulator import LohnKalkulator
from agents.zuschlag_kalkulator import ZuschlagKalkulator

ROOT = Path(__file__).parent.parent
ZUSCHLAEGE = yaml.safe_load(open(ROOT / "config" / "zuschlaege.yaml", encoding="utf-8"))

init_db_sync()
_cfg = AppConfig(config_dir=ROOT / "config")
config_routes.set_config(_cfg)
_pipeline, _ = _init_pipeline(_cfg)
kalkulation.set_pipeline(_pipeline)
export.set_pipeline(_pipeline)
client = TestClient(app, raise_server_exceptions=False)


def _run(coro):
    """Eigener Event-Loop: asyncio.run() wuerde den Loop anderer Tests (get_event_loop) entfernen."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

POSITIONEN = [
    ("01.01", "Zimmerschrank 1000x2000", 40, "Egger W1000", 3),
    ("01.02", "Blende", 1, "Egger W1000", 0.2),
    ("01.03", "Garderobe lackiert RAL 9010", 12, "MDF", 1),
]


@pytest.fixture(scope="module")
def projekt():
    pid = client.post("/api/projekte/", json={
        "name": "Test Positionspreise", "projekt_typ": "oeffentlich", "kunde": "Test",
    }).json()["id"]
    for nr, text, menge, material, platten in POSITIONEN:
        r = client.post(f"/api/projekte/{pid}/positionen/", json={
            "pos_nr": nr, "kurztext": text, "menge": menge, "einheit": "STK",
            "material": material, "platten_anzahl": platten, "kantenlaenge_lfm": 10,
        })
        assert r.status_code == 201
    r = client.post(f"/api/kalkulation/starten/{pid}")
    assert r.status_code == 200
    positionen = {p["pos_nr"]: p for p in client.get(f"/api/projekte/{pid}/positionen/").json()}
    return pid, r.json(), positionen


def _gaeb_summe(pid):
    r = client.post(f"/api/export/{pid}/gaeb")
    assert r.status_code == 200
    xml = (ROOT / "exports" / f"Angebot_{pid}.x83").read_text(encoding="utf-8")
    preise = re.findall(r"<Item ID=\"([^\"]+)\">.*?<Qty>([^<]+)</Qty>.*?<UP>([^<]+)</UP>", xml, re.S)
    return {nr: float(up) for nr, _, up in preise}, sum(float(q) * float(up) for _, q, up in preise)


def test_summe_ep_mal_menge_ist_angebotspreis(projekt):
    _, kalk, positionen = projekt
    summe = sum(p["einheitspreis"] * p["menge"] for p in positionen.values())
    assert summe == pytest.approx(kalk["angebotspreis"], abs=0.01)
    for p in positionen.values():
        assert p["gesamtpreis"] == pytest.approx(round(p["einheitspreis"] * p["menge"], 2), abs=0.001)


def test_ep_enthaelt_zuschlaege(projekt):
    _, _, positionen = projekt
    for p in positionen.values():
        kosten = p["materialkosten"] + p["maschinenkosten"] + p["lohnkosten"] + p["fremdleistungskosten"]
        assert p["gesamtpreis"] > kosten, f"Pos {p['pos_nr']}: GP ohne Zuschlaege"


def test_lohn_nach_eigenen_stunden(projekt):
    _, kalk, positionen = projekt
    assert positionen["01.01"]["lohnkosten"] > 10 * positionen["01.02"]["lohnkosten"]
    assert sum(p["lohnkosten"] for p in positionen.values()) == pytest.approx(kalk["lohnkosten"], abs=0.05)


def test_fremdleistung_zaehlt_nur_einmal(projekt):
    _, kalk, positionen = projekt
    assert kalk["fremdleistungskosten"] > 0
    # Material im Ergebnis ist das eigene Material ohne Lackierung
    assert kalk["materialkosten"] == pytest.approx(sum(p["materialkosten"] for p in positionen.values()), abs=0.05)
    gkz, gewinn, wagnis = (ZUSCHLAEGE["gemeinkosten_gkz"], ZUSCHLAEGE["gewinnaufschlag_oeffentlich"],
                           ZUSCHLAEGE["wagnis_vob"])
    erwartet = (
        kalk["herstellkosten"] * (1 + gkz) * (1 + gewinn + wagnis)
        + kalk["lohnkosten"] * ZUSCHLAEGE["montage_baustellenzuschlag"]
        + kalk["fremdleistungskosten"] * (1 + ZUSCHLAEGE["fremdleistung_lackierung"])
    )
    # EP wird je Position auf Cent gerundet: Abweichung hoechstens 0.5 Cent je Stueck
    rundung = 0.005 * sum(p["menge"] for p in positionen.values())
    assert kalk["angebotspreis"] == pytest.approx(erwartet, abs=rundung)


def test_gaeb_export_enthaelt_positionspreise(projekt):
    pid, kalk, positionen = projekt
    preise, summe = _gaeb_summe(pid)
    assert preise == {nr: p["einheitspreis"] for nr, p in positionen.items()}
    assert summe == pytest.approx(kalk["angebotspreis"], abs=0.01)


def test_gaeb_export_nach_neustart_gleich(projekt):
    pid, kalk, positionen = projekt
    export._kalkulations_cache.pop(pid, None)       # Server-Neustart: Cache leer
    preise, summe = _gaeb_summe(pid)
    assert preise == {nr: p["einheitspreis"] for nr, p in positionen.items()}
    assert summe == pytest.approx(kalk["angebotspreis"], abs=0.01)


def test_lohnkalkulator_verteilung_summe_und_transport():
    agent = LohnKalkulator()
    agent.load_config(yaml.safe_load(open(ROOT / "config" / "stundensaetze.yaml", encoding="utf-8")))
    msg = AgentMessage(sender="test", receiver="lohn_kalkulator", msg_type="kalkuliere_lohn", payload={
        "positionen": [
            {"pos_nr": "1", "menge": 10, "platten_anzahl": 4, "kantenlaenge_lfm": 30},
            {"pos_nr": "2", "menge": 0, "platten_anzahl": 1, "kantenlaenge_lfm": 0},
        ],
    })
    res = _run(agent.execute(msg)).payload
    verteilt = {p["pos_nr"]: p for p in res["positionen"]}
    assert sum(p["kosten"] for p in verteilt.values()) == pytest.approx(res["lohnkosten_gesamt"], abs=1e-6)
    # Position 2 hat keine Montage und bekommt deshalb keinen Transport
    assert verteilt["2"]["montage_stunden"] == 0
    assert verteilt["1"]["kosten"] > verteilt["2"]["kosten"]


def test_zuschlag_fremdmontage_nach_montagestunden():
    agent = ZuschlagKalkulator()
    agent.load_config(ZUSCHLAEGE)
    payload = {
        "materialkosten": {"materialliste": [{"pos_nr": "1", "gesamtkosten": 1000}, {"pos_nr": "2", "gesamtkosten": 500}],
                           "fremdleistungen": [], "materialkosten_gesamt": 1500},
        "maschinenkosten": {"maschineneinsaetze": [{"pos_nr": "1", "kosten_gesamt": 200}, {"pos_nr": "2", "kosten_gesamt": 100}],
                            "maschinenkosten_gesamt": 300},
        "lohnkosten": {
            "lohnkosten_gesamt": 3000,
            "positionen": [{"pos_nr": "1", "kosten": 2400, "montage_stunden": 300},
                           {"pos_nr": "2", "kosten": 600, "montage_stunden": 0}],
            "montage_plan": {"gesamt_stunden": 300, "fremdmontage_empfohlen": True, "fremdmonteure_anzahl": 1},
        },
        "projekt_typ": "standard",
    }
    msg = AgentMessage(sender="test", receiver="zuschlag_kalkulator", msg_type="kalkuliere_zuschlaege", payload=payload)
    res = _run(agent.execute(msg)).payload
    preise = {p["pos_nr"]: p for p in res["positionen_preise"]}
    assert sum(p["angebotspreis"] for p in preise.values()) == pytest.approx(res["angebotspreis_gesamt"], abs=0.01)
    # Fremdmontage (8 h x 65 EUR) liegt komplett auf der Position mit Montage
    assert preise["1"]["fremdleistungskosten"] == pytest.approx(520)
    assert preise["2"]["fremdleistungskosten"] == 0
