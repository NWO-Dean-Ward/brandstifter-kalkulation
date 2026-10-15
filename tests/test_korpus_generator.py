"""
Tests fuer den Korpus-Generator: Geometrie, Beschlaege, Validierung,
monotone Preise, Preis-Katalog, Zuschnitt-Schaetzung und API.
"""

import copy
import itertools
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.korpus_generator import (
    KonfigurationsFehler, KorpusParameter, PreisKatalog, Teil,
    berechne_korpus, generiere_korpus, lade_regeln, schaetze_platten,
)

ROOT = Path(__file__).parent.parent
REGELN = lade_regeln(ROOT / "config" / "korpus.yaml")
MASCHINEN = yaml.safe_load(open(ROOT / "config" / "maschinen.yaml", encoding="utf-8"))
KATALOG = PreisKatalog([
    {"material_name": "Egger W1000 ST9 19mm", "kategorie": "platte", "preis": 14.5, "einheit": "m2"},
    {"material_name": "Egger H1345 ST32", "kategorie": "platte", "preis": 32.0, "einheit": "m2"},
    {"material_name": "HDF weiss", "kategorie": "platte", "preis": 4.2, "einheit": "m2"},
])


def _param(**kw):
    basis = dict(
        typ="unterschrank", breite_mm=600, hoehe_mm=720, tiefe_mm=560, einlegeboeden=1, tueren=1,
        sockel_hoehe_mm=150, korpus_material="Egger W1000 ST9", front_material="Egger H1345 ST32",
        rueckwand_material="HDF weiss",
    )
    basis.update(kw)
    return KorpusParameter(**basis)


def _rechne(**kw):
    return berechne_korpus(_param(**kw), regeln=REGELN, maschinen_cfg=MASCHINEN, katalog=KATALOG)


def _teile(ergebnis):
    return {t["bezeichnung"]: t for t in ergebnis["teile"]}


# === Geometrie ===

def test_unterschrank_geometrie():
    t = _teile(_rechne())
    assert (t["Seite"]["anzahl"], t["Seite"]["laenge_mm"], t["Seite"]["breite_mm"]) == (2, 720, 560)
    assert (t["Boden"]["laenge_mm"], t["Boden"]["breite_mm"]) == (562, 560)
    assert "Traverse vorne" in t and "Traverse hinten" in t and "Deckel" not in t
    # Rueckwand eingenutet: lichte Masse + 2 x (Nuttiefe 8 - 1)
    assert (t["Rueckwand"]["breite_mm"], t["Rueckwand"]["laenge_mm"]) == (576, 696)
    # Einlegeboden: 2 mm Luft, Innentiefe 560 - (16 + 8), 20 mm Rueckversatz
    assert (t["Einlegeboden"]["laenge_mm"], t["Einlegeboden"]["breite_mm"]) == (560, 516)
    # Tuer aufliegend mit 1.5 mm Randfuge
    assert (t["Tuer"]["breite_mm"], t["Tuer"]["laenge_mm"]) == (597, 717)


def test_haengeschrank_hat_deckel_aufhaenger_und_keinen_sockel():
    r = _rechne(typ="haengeschrank", tiefe_mm=350, sockel_hoehe_mm=150)
    t = _teile(r)
    assert "Deckel" in t and "Traverse vorne" not in t and "Sockelblende" not in t
    beschlaege = {b["bezeichnung"]: b["anzahl"] for b in r["beschlaege"]}
    assert beschlaege["Schrankaufhaenger (Paar)"] == 1
    assert "Sockelfuss verstellbar" not in beschlaege
    assert any("Sockel wird ignoriert" in w for w in r["warnungen"])


def test_rueckwand_aufgesetzt_verkuerzt_seiten():
    t = _teile(_rechne(rueckwand_art="aufgesetzt"))
    assert t["Seite"]["breite_mm"] == 552          # 560 - 8 mm Rueckwand
    assert (t["Rueckwand"]["breite_mm"], t["Rueckwand"]["laenge_mm"]) == (600, 720)


def test_schubkaesten_fronten_und_innenteile():
    r = _rechne(tueren=0, schubkaesten=3, einlegeboeden=0)
    t = _teile(r)
    # (720 - 3 Randfuge - 2 x 3 Fuge) / 3
    assert t["Schubkastenfront"]["anzahl"] == 3
    assert t["Schubkastenfront"]["laenge_mm"] == pytest.approx(237)
    # Boden: lichte Breite 562 - 35; Nennlaenge (536 - 10) -> 500, minus 10
    assert (t["Schubkasten-Boden"]["laenge_mm"], t["Schubkasten-Boden"]["breite_mm"]) == (527, 490)
    beschlaege = {b["bezeichnung"]: b["anzahl"] for b in r["beschlaege"]}
    assert beschlaege["Schubkasten-Set Vollauszug mit Daempfung"] == 3
    assert beschlaege["Griff Standard"] == 3


def test_scharniere_nach_tuerhoehe():
    def scharniere(hoehe):
        r = _rechne(typ="hochschrank", hoehe_mm=hoehe, tueren=2, einlegeboeden=0)
        return {b["bezeichnung"]: b["anzahl"] for b in r["beschlaege"]}["Topfscharnier mit Daempfung inkl. Montageplatte"]

    assert scharniere(800) == 2 * 2
    assert scharniere(1500) == 2 * 3
    assert scharniere(2000) == 2 * 4


def test_leere_materialien_bekommen_getrennte_platzhalter():
    r = _rechne(korpus_material="", front_material="", rueckwand_material="")
    namen = {p["material"] for p in r["platten"]}
    assert {"Korpusmaterial (offen)", "Frontmaterial (offen)", "Rueckwand (offen)"} <= namen


def test_anzahl_skaliert_material_linear():
    einzeln = _rechne(anzahl=1)
    vierzig = _rechne(anzahl=40)
    assert vierzig["kennzahlen"]["materialkosten_netto"] == pytest.approx(
        40 * einzeln["kennzahlen"]["materialkosten_netto"], rel=1e-3)
    # Arbeitsvorbereitung einmal je Variante, nicht je Stueck
    assert vierzig["stunden"]["Arbeitsvorbereitung"] == einzeln["stunden"]["Arbeitsvorbereitung"]


def test_hinweise_tuerbreite_und_spannweite():
    r = _rechne(breite_mm=900, tueren=1)
    assert any("zweite Tuer empfohlen" in w for w in r["warnungen"])
    r = _rechne(breite_mm=1000, tueren=2)
    assert any("Durchbiegung pruefen" in w for w in r["warnungen"])


# === Validierung ===

@pytest.mark.parametrize("kw, text", [
    ({"typ": "regal"}, "Unbekannter Korpus-Typ"),
    ({"breite_mm": 100}, "Breite muss zwischen"),
    ({"tueren": 3}, "Tueren muss zwischen"),
    ({"tueren": 1, "schubkaesten": 5}, "lassen keinen Platz fuer Tueren"),
    ({"tiefe_mm": 280, "schubkaesten": 1, "tueren": 0}, "zu flach fuer Schubkaesten"),
    ({"rueckwand_art": "geklebt"}, "Unbekannte Rueckwand-Art"),
])
def test_ungueltige_parameter(kw, text):
    with pytest.raises(ValueError, match=text):
        generiere_korpus(_param(**kw), REGELN)


def test_fehlender_konfigurationswert():
    regeln = copy.deepcopy(REGELN)
    del regeln["konstruktion"]["fuge_mm"]
    with pytest.raises(KonfigurationsFehler, match="konstruktion.fuge_mm"):
        generiere_korpus(_param(), regeln)


# === Monotonie: groesser oder mehr wird nie billiger ===

def _kosten_und_stunden(**kw):
    k = _rechne(**kw)["kennzahlen"]
    return k["materialkosten_netto"], k["stunden_gesamt"]


@pytest.mark.parametrize("typ", ["unterschrank", "haengeschrank", "hochschrank"])
@pytest.mark.parametrize("feld, werte", [
    ("breite_mm", [300, 450, 600, 601, 800, 1000, 1001, 1200]),
    ("hoehe_mm", [600, 720, 900, 901, 1600, 1601, 2000, 2400]),
    ("tiefe_mm", [350, 400, 500, 560, 580, 590, 600, 650]),
    ("einlegeboeden", [0, 1, 2, 3, 4, 5]),
    ("tueren", [0, 1, 2]),
    ("anzahl", [1, 2, 5, 10, 40]),
])
def test_preis_monoton(typ, feld, werte):
    vorher = (0.0, 0.0)
    for w in werte:
        aktuell = _kosten_und_stunden(typ=typ, **{feld: w})
        assert aktuell[0] >= vorher[0] - 1e-9, f"{typ} {feld}={w}: Material {aktuell[0]} < {vorher[0]}"
        assert aktuell[1] >= vorher[1] - 1e-9, f"{typ} {feld}={w}: Stunden {aktuell[1]} < {vorher[1]}"
        vorher = aktuell


def test_preis_monoton_schubkaesten():
    vorher = 0.0
    for d in range(0, 4):
        kosten, _ = _kosten_und_stunden(typ="unterschrank", tueren=0, einlegeboeden=0, schubkaesten=d)
        assert kosten >= vorher
        vorher = kosten


def test_preis_monoton_im_raster():
    """Stichprobe ueber Kombinationen: jede Vergroesserung einer Dimension kostet mehr oder gleich."""
    for b, h, t in itertools.product([400, 600, 900], [700, 1200, 2000], [350, 560]):
        basis, _ = _kosten_und_stunden(typ="hochschrank", breite_mm=b, hoehe_mm=h, tiefe_mm=t)
        for groesser in ({"breite_mm": b + 50}, {"hoehe_mm": h + 50}, {"tiefe_mm": t + 20}):
            parameter = {"breite_mm": b, "hoehe_mm": h, "tiefe_mm": t, **groesser}
            assert _kosten_und_stunden(typ="hochschrank", **parameter)[0] >= basis


# === Preis-Katalog ===

def test_katalog_beachtet_kategorie_und_laengsten_treffer():
    katalog = PreisKatalog([
        {"material_name": "W1000", "kategorie": "kante", "preis": 0.9, "einheit": "lfm"},
        {"material_name": "Egger W1000", "kategorie": "platte", "preis": 12.0, "einheit": "m2"},
        {"material_name": "Egger W1000 ST9", "kategorie": "platte", "preis": 14.0, "einheit": "m2"},
    ])
    assert katalog.suche("Egger W1000 ST9 Premiumweiss", "platte")["preis"] == 14.0
    assert katalog.suche("W1000", "kante")["preis"] == 0.9
    assert katalog.suche("Kante W1000 ABS", "kante")["preis"] == 0.9
    assert katalog.suche("", "platte") is None
    assert katalog.suche("   ", "platte") is None


def test_plattenpreis_mit_staerke_und_richtwert():
    r = _rechne()
    preise = {p["material"]: p for p in r["platten"]}
    assert preise["Egger W1000 ST9"]["preis_m2"] == 14.5            # Treffer "... 19mm"
    assert preise["HDF weiss"]["preis_m2"] == 4.2
    r = _rechne(front_material="Fenix NTM")
    fenix = {p["material"]: p for p in r["platten"]}["Fenix NTM"]
    assert fenix["preis_quelle"] == "Richtwert korpus.yaml"
    assert any("Kein Preis fuer 'Fenix NTM'" in w for w in r["warnungen"])


def test_preis_pro_platte_wird_umgerechnet():
    katalog = PreisKatalog([{"material_name": "Multiplex Birke", "kategorie": "platte", "preis": 115.92, "einheit": "Platte"}])
    r = berechne_korpus(_param(korpus_material="Multiplex Birke"), regeln=REGELN, maschinen_cfg=MASCHINEN, katalog=katalog)
    birke = {p["material"]: p for p in r["platten"]}["Multiplex Birke"]
    assert birke["preis_m2"] == pytest.approx(115.92 / (2.8 * 2.07), abs=0.01)
    assert any("pro Platte hinterlegt" in w for w in r["warnungen"])


def test_kalkulator_import_passt_zur_auswertung():
    r = _rechne(anzahl=3)
    imp = r["kalkulator_import"]
    platten = sum(p["menge"] * (1 + p["verschnitt"] / 100) * p["preisQm"] for p in imp["platten"])
    kanten = sum(k["laenge"] * (k["bearbeitung"] + k["kantePreis"]) for k in imp["kanten"])
    beschlaege = sum(b["anzahl"] * b["preis"] for b in imp["beschlaege"])
    assert platten + kanten + beschlaege == pytest.approx(r["kennzahlen"]["materialkosten_netto"], abs=0.1)
    assert set(imp["lohn"]) <= {"Arbeitsvorbereitung", "CNC", "Bankraum", "Montage"}
    assert imp["lohn"]["CNC"] > 0


# === Zuschnitt-Schaetzung ===

def test_zuschnitt_grosse_serie_realistische_ausnutzung():
    r = _rechne(typ="hochschrank", anzahl=40, breite_mm=1000, hoehe_mm=2000, tiefe_mm=600,
                einlegeboeden=4, tueren=2, sockel_hoehe_mm=100)
    korpus = {p["material"]: p for p in r["platten"]}["Egger W1000 ST9"]
    platte_m2 = 2.8 * 2.07
    assert korpus["zuschnitt"]["platten_anzahl"] >= korpus["netto_m2"] / platte_m2
    assert korpus["zuschnitt"]["ausnutzung_prozent"] > 75


def test_zuschnitt_maserung_dreht_nicht_und_meldet_uebergroesse():
    # 2700 x 1000 mit Maserung passt nur laengs auf 2800 x 2070
    passt = schaetze_platten([Teil("Front", 2, 2700, 1000, 19, "Eiche", maserung=True)], 2800, 2070)
    assert passt["platten_anzahl"] == 1 and not passt["zu_gross"]
    # 1000 x 2700 mit Maserung (Faser quer) passt nicht
    quer = schaetze_platten([Teil("Front", 1, 1000, 2700, 19, "Eiche", maserung=True)], 2800, 2070)
    assert quer["zu_gross"] and quer["platten_anzahl"] == 0
    # ohne Maserung wird gedreht
    gedreht = schaetze_platten([Teil("Front", 1, 1000, 2700, 19, "W1000")], 2800, 2070)
    assert gedreht["platten_anzahl"] == 1


def test_warnung_bei_hohem_verschnitt_nur_ab_drei_platten():
    einzeln = _rechne(anzahl=1)
    assert not any("Zuschnitt-Schaetzung ergibt" in w for w in einzeln["warnungen"])
    serie = _rechne(typ="hochschrank", anzahl=40, breite_mm=1000, hoehe_mm=2000, tiefe_mm=600,
                    tueren=2, front_maserung=True)
    assert any("Zuschnitt-Schaetzung ergibt" in w for w in serie["warnungen"])


# === API ===

from fastapi.testclient import TestClient  # noqa: E402
from api.database import init_db_sync  # noqa: E402
from api.main import app  # noqa: E402

init_db_sync()
client = TestClient(app, raise_server_exceptions=False)


def test_api_vorlagen():
    r = client.get("/api/korpus/vorlagen")
    assert r.status_code == 200
    d = r.json()
    assert any(v["name"].startswith("Zimmerschrank") for v in d["vorlagen"])
    assert d["standard"]["korpus_staerke_mm"] == 19
    assert "unterschrank" in d["typen"]


def test_api_berechnen():
    r = client.post("/api/korpus/berechnen", json={
        "typ": "hochschrank", "anzahl": 2, "breite_mm": 600, "hoehe_mm": 2000, "tiefe_mm": 560,
        "einlegeboeden": 4, "tueren": 1, "korpus_material": "Egger W1000 ST9",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["kennzahlen"]["teile_anzahl"] > 0
    assert set(d["kalkulator_import"]) >= {"platten", "kanten", "beschlaege", "lohn"}
    assert d["parameter"]["korpus_staerke_mm"] == 19


def test_api_berechnen_fehler_auf_deutsch():
    r = client.post("/api/korpus/berechnen", json={"typ": "unterschrank", "tueren": 1, "schubkaesten": 5})
    assert r.status_code == 422
    assert "Schubkaesten" in r.json()["detail"]
