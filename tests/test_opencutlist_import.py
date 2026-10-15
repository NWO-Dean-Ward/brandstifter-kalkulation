"""
Tests fuer den OpenCutList-Import (SketchUp): Spaltenerkennung DE/EN,
SketchUp-Laengen, Encodings/Trennzeichen, Kanten ohne Doppelzaehlung, API.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.opencutlist_import import parse_laenge, parse_opencutlist_csv

FIXTURES = Path(__file__).parent / "fixtures"
DE_CSV = FIXTURES / "opencutlist_unterschrank_de.csv"
EN_CSV = FIXTURES / "opencutlist_moebel_en_zoll.csv"


@pytest.mark.parametrize("text, mm, einheit", [
    ("600mm", 600, True),
    ("600 mm", 600, True),
    ("600,5mm", 600.5, True),
    ("60cm", 600, True),
    ("0,6m", 600, True),
    ("~ 600mm", 600, True),
    ('23 5/8"', 600.075, True),
    ("1' 11 5/8\"", 600.075, True),
    ('3/4"', 19.05, True),
    ("2'", 609.6, True),
    ("600", 600, False),
])
def test_parse_laenge(text, mm, einheit):
    wert, mit_einheit = parse_laenge(text)
    assert wert == pytest.approx(mm, abs=0.01)
    assert mit_einheit is einheit


@pytest.mark.parametrize("text", ["", "abc", "12 Stk"])
def test_parse_laenge_ungueltig(text):
    assert parse_laenge(text)[0] is None


def test_deutscher_standardexport():
    r = parse_opencutlist_csv(DE_CSV.read_bytes(), DE_CSV.name)
    teile = {t.bezeichnung: t for t in r.teile}
    assert set(teile) == {"Seite", "Boden", "Einlegeboden", "Rückwand", "Tür"}
    seite = teile["Seite"]
    # Rohmasse fuer die Flaeche, Fertigmass fuer die Kante
    assert (seite.anzahl, seite.laenge_mm, seite.breite_mm, seite.staerke_mm) == (2, 722, 562, 19)
    assert seite.kanten_mm == [720] and seite.kante_material == "ABS W1000 (1mm x 23mm)"
    assert teile["Tür"].kanten_mm == [717, 717, 597, 597]
    assert {b.bezeichnung: b.anzahl for b in r.beschlaege} == {"Topfscharnier Blum CLIP top": 2, "Sockelfuss": 4}
    assert r.massivholz == [{"bezeichnung": "Eiche massiv", "staerke_mm": 22, "m3": pytest.approx(0.00047740)}]
    assert r.hinweise == []


def test_englischer_export_zoll_komma_und_kantenband_ohne_doppelzaehlung():
    r = parse_opencutlist_csv(EN_CSV.read_bytes(), EN_CSV.name)
    teile = {t.bezeichnung: t for t in r.teile}
    assert teile["Side"].laenge_mm == pytest.approx(720.7, abs=0.1)
    assert teile["Top"].laenge_mm == pytest.approx(596.9, abs=0.1)
    # Kanten kommen aus der Kantenband-Zeile, nicht zusaetzlich aus den Teilen
    assert r.kanten == [{"material": "Birch edge (1mm x 22mm)", "lfm": pytest.approx(2.5)}]
    assert all(not t.kanten_mm for t in r.teile)
    assert any("Kantenband-Zeilen" in h for h in r.hinweise)
    assert [b.bezeichnung for b in r.beschlaege] == ["Drawer slide 500"]


def test_utf16_tab_ohne_einheit_und_ohne_material():
    text = (
        "Nr.\tBezeichnung\tAnzahl\tLänge\tBreite\tDicke\tMaterialtyp\tMaterialname\n"
        "A\tRegalboden\t3\t800\t300\t19\tUnbestimmt\tOhne Material\n"
    )
    r = parse_opencutlist_csv(b"\xff\xfe" + text.encode("utf-16-le"), "regal.csv")
    assert len(r.teile) == 1
    t = r.teile[0]
    assert (t.anzahl, t.laenge_mm, t.breite_mm, t.staerke_mm, t.material) == (3, 800, 300, 19, "")
    hinweise = " | ".join(r.hinweise)
    assert "ohne Material" in hinweise
    assert "als mm gelesen" in hinweise
    assert "Unbestimmt" in hinweise


def test_keine_zuschnittliste():
    with pytest.raises(ValueError, match="Keine OpenCutList-Zuschnittliste"):
        parse_opencutlist_csv(b"a;b;c\n1;2;3\n", "falsch.csv")
    with pytest.raises(ValueError, match="leer"):
        parse_opencutlist_csv(b"", "leer.csv")


# === API ===

from fastapi.testclient import TestClient  # noqa: E402
from api.database import init_db_sync  # noqa: E402
from api.main import app  # noqa: E402
from api.routes import analyse  # noqa: E402

init_db_sync()
client = TestClient(app, raise_server_exceptions=False)


def _upload(*pfade):
    return client.post("/api/analyse/opencutlist-upload", files=[
        ("dateien", (p.name, p.read_bytes(), "text/csv")) for p in pfade
    ])


def test_api_upload_mehrere_dateien():
    r = _upload(DE_CSV, EN_CSV)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert [x["datei"] for x in d["dateien"]] == [DE_CSV.name, EN_CSV.name]
    assert d["kennzahlen"]["teile_anzahl"] == 6 + 3
    imp = d["kalkulator_import"]
    assert {p["bezeichnung"] for p in imp["platten"]} >= {"Egger W1000 ST9 Premiumweiss", "Plywood Birch"}
    assert imp["massivholz"][0]["bezeichnung"] == "Eiche massiv"
    assert imp["lohn"]["CNC"] > 0
    assert "Bankraum" not in imp["lohn"]       # nur aus Parametern ableitbar, nicht aus einer Stueckliste
    assert any(h.startswith(EN_CSV.name) for h in d["hinweise"])


def test_api_upload_falsche_datei():
    r = client.post("/api/analyse/opencutlist-upload",
                    files=[("dateien", ("x.csv", b"a;b\n1;2\n", "text/csv"))])
    assert r.status_code == 422
    assert r.json()["detail"].startswith("x.csv:")


def test_api_upload_zu_gross(monkeypatch):
    monkeypatch.setattr(analyse, "MAX_UPLOAD_SIZE", 10)
    r = _upload(DE_CSV)
    assert r.status_code == 413
