"""
KorpusGenerator - parametrische Korpus-Kalkulation.

Aus Typ, Massen und Ausstattung (Einlegeboeden, Tueren, Schubkaesten) entsteht:
- Stueckliste (Einzelteile mit Fertigmassen, Material, Kanten)
- Plattenbedarf je Material/Staerke (netto m2, brutto m2 mit Verschnitt,
  Plattenanzahl laut Zuschnitt-Schaetzung)
- Kanten in lfm, Beschlaege in Stueck
- Stunden je Lohnkategorie des Kalkulators (Arbeitsvorbereitung, CNC, Bankraum, Montage)

Die Stuecklisten-Auswertung (werte_stueckliste_aus) haengt nicht am Korpus-Typ
und wird auch fuer den OpenCutList-Import genutzt: eine Rechenlogik, mehrere Eingaenge.

Preise kommen nur vom Server (Materialpreis-DB, Fallback config/korpus.yaml).
Alle Mengen wachsen monoton mit Massen und Stueckzahlen; die Plattenanzahl laut
Zuschnitt ist reine Information und fliesst nicht in den Preis ein.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agents.material_kalkulator import HALBFORMAT

TYPEN = ("unterschrank", "haengeschrank", "hochschrank")
RUECKWAND_ARTEN = ("eingenutet", "aufgesetzt", "keine")
QUALITAETEN = ("standard", "hochwertig")

# Preis-Einheiten, die einen Preis pro ganzer Platte statt pro m2 bedeuten
_EINHEITEN_PRO_PLATTE = {"platte", "platten", "stk", "st", "stueck", "stück"}


# ----------------------------------------------------------------------
# Datenstrukturen
# ----------------------------------------------------------------------


@dataclass
class Teil:
    """Ein Plattenteil der Stueckliste. Masse sind Fertigmasse in mm."""

    bezeichnung: str
    anzahl: int                 # Gesamtanzahl ueber alle Korpusse
    laenge_mm: float            # bei Maserung: Laenge = Faserrichtung
    breite_mm: float
    staerke_mm: float
    material: str
    gruppe: str = "korpus"      # korpus | front | rueckwand | schubkasten | import
    kanten_mm: list[float] = field(default_factory=list)  # Kantenlaengen pro Stueck
    kante_material: str = ""
    maserung: bool = False

    @property
    def flaeche_m2(self) -> float:
        return self.laenge_mm * self.breite_mm / 1_000_000 * self.anzahl


@dataclass
class Beschlag:
    schluessel: str
    bezeichnung: str
    anzahl: float
    preis_fallback: float = 0.0


@dataclass
class KorpusParameter:
    typ: str = "unterschrank"
    bezeichnung: str = ""
    anzahl: int = 1
    breite_mm: float = 600
    hoehe_mm: float = 720
    tiefe_mm: float = 560
    einlegeboeden: int = 0
    tueren: int = 1
    schubkaesten: int = 0
    sockel_hoehe_mm: float = 0
    sockelblende: bool = True
    griffe: bool = True
    montage: bool = True
    korpus_material: str = ""
    korpus_staerke_mm: float | None = None      # None -> config/korpus.yaml
    korpus_maserung: bool = False
    front_material: str = ""
    front_staerke_mm: float | None = None
    front_maserung: bool = False
    rueckwand_material: str = ""
    rueckwand_staerke_mm: float | None = None
    rueckwand_art: str | None = None
    qualitaet: str = "standard"                  # standard | hochwertig (CNC-Kapazitaet)


# ----------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------


def lade_regeln(pfad: str | Path = "config/korpus.yaml") -> dict[str, Any]:
    """Laedt die Konstruktionsregeln aus config/korpus.yaml."""
    with open(pfad, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class KonfigurationsFehler(Exception):
    """config/korpus.yaml fehlt oder ist unvollstaendig (Serverfehler, kein Eingabefehler)."""


def konfig_wert(regeln: dict[str, Any], schluessel: str) -> Any:
    """Liest einen Wert wie 'konstruktion.fuge_mm' mit klarer Fehlermeldung."""
    knoten: Any = regeln
    for teil in schluessel.split("."):
        if not isinstance(knoten, dict) or teil not in knoten:
            raise KonfigurationsFehler(f"Konfigurationswert fehlt in config/korpus.yaml: {schluessel}")
        knoten = knoten[teil]
    return knoten


# ----------------------------------------------------------------------
# Preis-Katalog
# ----------------------------------------------------------------------


class PreisKatalog:
    """Preis-Lookup in der Materialpreis-DB.

    Anders als MaterialKalkulator._lookup_preis wird die Kategorie beachtet
    (eine Kante 'W1000' liefert keinen Plattenpreis) und ein leerer Name trifft nie.
    Bei mehreren Teiltreffern gewinnt der laengste (spezifischste) Eintrag.
    """

    def __init__(self, eintraege: list[dict[str, Any]] | None = None) -> None:
        self._eintraege = eintraege or []

    @classmethod
    def aus_db(cls, db_pfad: str | Path) -> "PreisKatalog":
        if not Path(db_pfad).exists():
            return cls()
        conn = sqlite3.connect(str(db_pfad))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT material_name, kategorie, preis, einheit "
                "FROM materialpreise WHERE gueltig_bis = ''"
            ).fetchall()
        except sqlite3.Error:
            rows = []
        finally:
            conn.close()
        return cls([dict(r) for r in rows])

    def suche(self, name: str, kategorie: str) -> dict[str, Any] | None:
        gesucht = (name or "").strip().lower()
        if not gesucht:
            return None
        kandidaten = [
            e for e in self._eintraege
            if (e.get("kategorie") or "") in ("", kategorie) and (e.get("material_name") or "").strip()
        ]
        for e in kandidaten:
            if e["material_name"].strip().lower() == gesucht:
                return self._treffer(e)
        teiltreffer = [
            e for e in kandidaten
            if e["material_name"].strip().lower() in gesucht or gesucht in e["material_name"].strip().lower()
        ]
        if not teiltreffer:
            return None
        return self._treffer(max(teiltreffer, key=lambda e: len(e["material_name"])))

    @staticmethod
    def _treffer(e: dict[str, Any]) -> dict[str, Any]:
        return {
            "preis": float(e["preis"]),
            "einheit": (e.get("einheit") or "").strip(),
            "quelle": f"Materialpreise: {e['material_name']}",
        }


# ----------------------------------------------------------------------
# Korpus -> Stueckliste
# ----------------------------------------------------------------------


def _mit_defaults(p: KorpusParameter, regeln: dict[str, Any]) -> KorpusParameter:
    """Fuellt offene Staerken/Rueckwandart aus der Konfiguration."""
    if p.korpus_staerke_mm is None:
        p.korpus_staerke_mm = float(konfig_wert(regeln, "konstruktion.korpus_staerke_mm"))
    if p.front_staerke_mm is None:
        p.front_staerke_mm = float(konfig_wert(regeln, "konstruktion.front_staerke_mm"))
    if p.rueckwand_staerke_mm is None:
        p.rueckwand_staerke_mm = float(konfig_wert(regeln, "konstruktion.rueckwand_staerke_mm"))
    if not p.rueckwand_art:
        p.rueckwand_art = str(konfig_wert(regeln, "konstruktion.rueckwand_art"))
    # Ohne Materialangabe getrennte Platzhalter, sonst landen Korpus und Front in einer Gruppe
    p.korpus_material = p.korpus_material.strip() or "Korpusmaterial (offen)"
    p.front_material = p.front_material.strip() or "Frontmaterial (offen)"
    p.rueckwand_material = p.rueckwand_material.strip() or "Rueckwand (offen)"
    p.typ = (p.typ or "").strip().lower()
    p.qualitaet = (p.qualitaet or "standard").strip().lower()
    return p


def _innenmasse(p: KorpusParameter, regeln: dict[str, Any]) -> tuple[float, float, float]:
    """Gibt (lichte Breite, Tiefe Seiten/Boden, nutzbare Innentiefe) zurueck."""
    s = p.korpus_staerke_mm
    rw = p.rueckwand_staerke_mm
    lichte_b = p.breite_mm - 2 * s
    korpus_tiefe = p.tiefe_mm - rw if p.rueckwand_art == "aufgesetzt" else p.tiefe_mm
    if p.rueckwand_art == "eingenutet":
        innen_tiefe = korpus_tiefe - (float(konfig_wert(regeln, "konstruktion.nut_abstand_hinten_mm")) + rw)
    else:
        innen_tiefe = korpus_tiefe
    return lichte_b, korpus_tiefe, innen_tiefe


def _fronten(p: KorpusParameter, regeln: dict[str, Any]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Berechnet Frontmasse: (Tueren [(breite, hoehe)], Schubkastenfronten [(breite, hoehe)])."""
    fuge = float(konfig_wert(regeln, "konstruktion.fuge_mm"))
    randfuge = float(konfig_wert(regeln, "konstruktion.randfuge_mm"))
    breite_gesamt = p.breite_mm - 2 * randfuge
    hoehe_gesamt = p.hoehe_mm - 2 * randfuge
    t, d = p.tueren, p.schubkaesten

    schubkasten: list[tuple[float, float]] = []
    tueren: list[tuple[float, float]] = []

    if d > 0 and t == 0:
        h = (hoehe_gesamt - fuge * (d - 1)) / d
        schubkasten = [(breite_gesamt, h)] * d
    elif d > 0:
        h = float(konfig_wert(regeln, "konstruktion.schubkasten_front_hoehe_mm"))
        schubkasten = [(breite_gesamt, h)] * d
        hoehe_gesamt -= d * (h + fuge)

    if t > 0:
        b = (breite_gesamt - fuge * (t - 1)) / t
        tueren = [(b, hoehe_gesamt)] * t

    return tueren, schubkasten


def _nennlaenge(innen_tiefe: float, regeln: dict[str, Any]) -> float:
    abzug = float(konfig_wert(regeln, "konstruktion.schubkasten_tiefe_abzug_mm"))
    return math.floor((innen_tiefe - abzug) / 50) * 50


def pruefe_parameter(p: KorpusParameter, regeln: dict[str, Any]) -> list[str]:
    """Prueft Wertebereiche und Konstruktionsgrenzen. Gibt Fehlermeldungen zurueck."""
    fehler: list[str] = []

    def bereich(wert: float, von: float, bis: float, name: str, einheit: str = "mm") -> None:
        if wert < von or wert > bis:
            fehler.append(f"{name} muss zwischen {von:g} und {bis:g} {einheit} liegen (ist {wert:g})")

    if p.typ not in TYPEN:
        fehler.append(f"Unbekannter Korpus-Typ '{p.typ}' (erlaubt: {', '.join(TYPEN)})")
    if p.rueckwand_art not in RUECKWAND_ARTEN:
        fehler.append(f"Unbekannte Rueckwand-Art '{p.rueckwand_art}' (erlaubt: {', '.join(RUECKWAND_ARTEN)})")
    if p.qualitaet not in QUALITAETEN:
        fehler.append(f"Unbekannte Qualitaet '{p.qualitaet}' (erlaubt: {', '.join(QUALITAETEN)})")

    bereich(p.anzahl, 1, 200, "Anzahl", "Stk")
    bereich(p.breite_mm, 150, 3000, "Breite")
    bereich(p.hoehe_mm, 150, 3000, "Hoehe")
    bereich(p.tiefe_mm, 100, 1200, "Tiefe")
    bereich(p.einlegeboeden, 0, 15, "Einlegeboeden", "Stk")
    bereich(p.tueren, 0, 2, "Tueren", "Stk")
    bereich(p.schubkaesten, 0, 8, "Schubkaesten", "Stk")
    bereich(p.sockel_hoehe_mm, 0, 300, "Sockelhoehe")
    bereich(p.korpus_staerke_mm, 3, 60, "Korpusstaerke")
    bereich(p.front_staerke_mm, 3, 60, "Frontstaerke")
    bereich(p.rueckwand_staerke_mm, 2, 40, "Rueckwandstaerke")
    if fehler:
        return fehler

    lichte_b, _, innen_tiefe = _innenmasse(p, regeln)
    if lichte_b < 50:
        fehler.append(f"Lichte Breite {lichte_b:g} mm ist zu klein (Breite minus 2x Korpusstaerke)")
    if innen_tiefe < 50:
        fehler.append(f"Nutzbare Innentiefe {innen_tiefe:g} mm ist zu klein")

    tueren, schubkasten = _fronten(p, regeln)
    min_tuer = float(konfig_wert(regeln, "konstruktion.min_tuer_hoehe_mm"))
    if tueren and tueren[0][1] < min_tuer:
        if schubkasten:
            fehler.append(
                f"{len(schubkasten)} Schubkaesten je {schubkasten[0][1]:g} mm lassen keinen Platz fuer Tueren "
                f"(min. {min_tuer:g} mm) - weniger Schubkaesten, Tueren auf 0 oder hoeherer Korpus"
            )
        else:
            fehler.append(f"Tuerhoehe {tueren[0][1]:.0f} mm unter Minimum {min_tuer:g} mm")
    if schubkasten and schubkasten[0][1] < 80:
        fehler.append(f"Schubkastenfront {schubkasten[0][1]:.0f} mm zu niedrig (min. 80 mm)")
    if p.schubkaesten > 0 and _nennlaenge(innen_tiefe, regeln) < 250:
        fehler.append("Korpus zu flach fuer Schubkaesten (Nennlaenge unter 250 mm)")
    return fehler


def generiere_korpus(
    p: KorpusParameter, regeln: dict[str, Any],
) -> tuple[list[Teil], list[Beschlag], dict[str, float], list[str]]:
    """Erzeugt Stueckliste, Beschlaege und Stunden (ohne CNC) fuer einen Korpus-Typ.

    Konstruktion: Seiten durchgehend, Boden/Deckel eingestellt; Unterschrank mit
    zwei Traversen statt Deckel; Fronten aufliegend.
    Wirft ValueError mit allen Fehlermeldungen, wenn die Parameter ungueltig sind.
    """
    p = _mit_defaults(p, regeln)
    fehler = pruefe_parameter(p, regeln)
    if fehler:
        raise ValueError("; ".join(fehler))

    n = p.anzahl
    s = p.korpus_staerke_mm
    lichte_b, korpus_tiefe, innen_tiefe = _innenmasse(p, regeln)
    kante_korpus = str(konfig_wert(regeln, "kanten.korpus"))
    kante_front = str(konfig_wert(regeln, "kanten.front"))
    warnungen: list[str] = []

    def korpusteil(bez: str, anzahl: int, laenge: float, breite: float, kanten: list[float]) -> Teil:
        return Teil(bez, anzahl * n, laenge, breite, s, p.korpus_material, "korpus",
                    kanten, kante_korpus, p.korpus_maserung)

    teile = [
        korpusteil("Seite", 2, p.hoehe_mm, korpus_tiefe, [p.hoehe_mm]),
        korpusteil("Boden", 1, lichte_b, korpus_tiefe, [lichte_b]),
    ]
    if p.typ == "unterschrank":
        traverse = float(konfig_wert(regeln, "konstruktion.traverse_breite_mm"))
        teile.append(korpusteil("Traverse vorne", 1, lichte_b, traverse, [lichte_b]))
        teile.append(korpusteil("Traverse hinten", 1, lichte_b, traverse, []))
    else:
        teile.append(korpusteil("Deckel", 1, lichte_b, korpus_tiefe, [lichte_b]))

    if p.einlegeboeden > 0:
        eb_laenge = lichte_b - float(konfig_wert(regeln, "konstruktion.einlegeboden_luft_mm"))
        eb_tiefe = innen_tiefe - float(konfig_wert(regeln, "konstruktion.einlegeboden_rueckversatz_mm"))
        teile.append(korpusteil("Einlegeboden", p.einlegeboeden, eb_laenge, eb_tiefe, [eb_laenge]))
        max_spannweite = float(konfig_wert(regeln, "grenzwerte.max_spannweite_einlegeboden_mm"))
        if eb_laenge > max_spannweite:
            warnungen.append(
                f"Einlegeboden {eb_laenge:.0f} mm breit (> {max_spannweite:g} mm) - "
                f"Durchbiegung pruefen, Mittelwand oder staerkerer Boden"
            )

    if p.rueckwand_art != "keine":
        if p.rueckwand_art == "eingenutet":
            zugabe = 2 * (float(konfig_wert(regeln, "konstruktion.nut_tiefe_mm")) - 1)
            rw_b, rw_h = lichte_b + zugabe, p.hoehe_mm - 2 * s + zugabe
        else:
            rw_b, rw_h = p.breite_mm, p.hoehe_mm
        teile.append(Teil("Rueckwand", n, rw_h, rw_b, p.rueckwand_staerke_mm,
                          p.rueckwand_material, "rueckwand"))

    tueren, schubkasten = _fronten(p, regeln)
    if tueren:
        b, h = tueren[0]
        teile.append(Teil("Tuer", len(tueren) * n, h, b, p.front_staerke_mm, p.front_material,
                          "front", [h, h, b, b], kante_front, p.front_maserung))
        max_tuerbreite = float(konfig_wert(regeln, "grenzwerte.max_tuerbreite_mm"))
        if b > max_tuerbreite:
            warnungen.append(f"Tuerbreite {b:.0f} mm (> {max_tuerbreite:g} mm) - zweite Tuer empfohlen")
    if schubkasten:
        b, h = schubkasten[0]
        teile.append(Teil("Schubkastenfront", len(schubkasten) * n, h, b, p.front_staerke_mm,
                          p.front_material, "front", [h, h, b, b], kante_front, p.front_maserung))
        # Boden und Rueckwand je Schubkasten (Richtwerte, systemabhaengig)
        sk_staerke = float(konfig_wert(regeln, "konstruktion.schubkasten_staerke_mm"))
        sk_breite = lichte_b - float(konfig_wert(regeln, "konstruktion.schubkasten_seitenluft_mm"))
        sk_tiefe = _nennlaenge(innen_tiefe, regeln) - 10
        sk_rw_hoehe = min(max(h - 70, 70), 220)
        teile.append(Teil("Schubkasten-Boden", len(schubkasten) * n, sk_breite, sk_tiefe,
                          sk_staerke, p.korpus_material, "schubkasten"))
        teile.append(Teil("Schubkasten-Rueckwand", len(schubkasten) * n, sk_breite, sk_rw_hoehe,
                          sk_staerke, p.korpus_material, "schubkasten"))

    mit_sockel = p.typ != "haengeschrank" and p.sockel_hoehe_mm > 0
    if mit_sockel and p.sockelblende:
        teile.append(Teil("Sockelblende", n, p.breite_mm, p.sockel_hoehe_mm, p.front_staerke_mm,
                          p.front_material, "front", [], "", p.front_maserung))
    if p.typ == "haengeschrank" and p.sockel_hoehe_mm > 0:
        warnungen.append("Haengeschrank: Sockel wird ignoriert")

    # Beschlaege
    def beschlag(schluessel: str, anzahl: float) -> Beschlag:
        cfg = konfig_wert(regeln, f"beschlaege.{schluessel}")
        return Beschlag(schluessel, cfg["bezeichnung"], anzahl, float(cfg["preis"]))

    beschlaege: list[Beschlag] = []
    if tueren:
        beschlaege.append(beschlag("scharnier", _scharniere(tueren[0][1], regeln) * len(tueren) * n))
    if p.einlegeboeden:
        beschlaege.append(beschlag("bodentraeger", 4 * p.einlegeboeden * n))
    if schubkasten:
        beschlaege.append(beschlag("schubkasten_set", len(schubkasten) * n))
    if p.griffe and (tueren or schubkasten):
        beschlaege.append(beschlag("griff", (len(tueren) + len(schubkasten)) * n))
    if mit_sockel:
        beschlaege.append(beschlag("sockelfuss", (4 if p.breite_mm <= 1000 else 6) * n))
    if p.typ == "haengeschrank":
        beschlaege.append(beschlag("aufhaenger", n))

    # Stunden (CNC kommt aus der Stuecklisten-Auswertung)
    def zeit(schluessel: str) -> float:
        return float(konfig_wert(regeln, f"zeiten.{schluessel}"))

    fronten = len(tueren) + len(schubkasten)
    bankraum = n * (
        zeit("bankraum_pro_korpus_h")
        + fronten * zeit("bankraum_pro_front_h")
        + len(schubkasten) * zeit("bankraum_pro_schubkasten_h")
    )
    stunden = {
        "Arbeitsvorbereitung": zeit("arbeitsvorbereitung_pro_variante_h"),
        "Bankraum": bankraum,
        "Montage": n * zeit("montage_pro_korpus_h") if p.montage else 0.0,
    }
    return teile, beschlaege, stunden, warnungen


def _scharniere(tuer_hoehe: float, regeln: dict[str, Any]) -> int:
    tabelle = sorted(konfig_wert(regeln, "scharniere_nach_tuerhoehe"), key=lambda e: e[0])
    for bis_mm, anzahl in tabelle:
        if tuer_hoehe <= bis_mm:
            return int(anzahl)
    return int(tabelle[-1][1]) + 1


# ----------------------------------------------------------------------
# Zuschnitt-Schaetzung (Information, nicht preisrelevant)
# ----------------------------------------------------------------------


def schaetze_platten(
    teile: list[Teil], platte_laenge: float, platte_breite: float,
    schnitt_mm: float = 4, rand_mm: float = 10,
) -> dict[str, Any]:
    """Zuschnitt-Schaetzung (MaxRects, Best Short Side Fit) fuer die Plattenanzahl.

    Teile mit Maserung bleiben in Faserrichtung (Laenge entlang Plattenlaenge),
    alle anderen duerfen gedreht werden. Schnittbreite wird je Teil zugeschlagen.
    Keine Guillotine-Pruefung - praeziser rechnet BetterNest/CAMPUS.
    """
    nutz_l = platte_laenge - 2 * rand_mm + schnitt_mm   # letzter Schnitt faellt in den Rand
    nutz_b = platte_breite - 2 * rand_mm + schnitt_mm
    stuecke: list[tuple[float, float, bool]] = []       # (laenge, breite, drehbar) inkl. Schnitt
    zu_gross: list[str] = []

    for t in teile:
        l, b = t.laenge_mm + schnitt_mm, t.breite_mm + schnitt_mm
        if not (l <= nutz_l and b <= nutz_b) and (t.maserung or not (b <= nutz_l and l <= nutz_b)):
            zu_gross.append(f"{t.bezeichnung} {t.laenge_mm:.0f} x {t.breite_mm:.0f} mm")
            continue
        stuecke.extend([(l, b, not t.maserung)] * t.anzahl)

    # Grosse Teile zuerst
    stuecke.sort(key=lambda s: (max(s[0], s[1]), min(s[0], s[1])), reverse=True)
    platten: list[list[tuple[float, float, float, float]]] = []   # freie Rechtecke (x, y, l, b) je Platte

    for l, b, drehbar in stuecke:
        platziert = False
        for frei in platten:
            wahl = _bester_platz(frei, l, b, drehbar)
            if wahl:
                _belege(frei, *wahl)
                platziert = True
                break
        if not platziert:
            frei = [(0.0, 0.0, nutz_l, nutz_b)]
            wahl = _bester_platz(frei, l, b, drehbar)
            _belege(frei, *wahl)
            platten.append(frei)

    teile_m2 = sum((l - schnitt_mm) * (b - schnitt_mm) for l, b, _ in stuecke) / 1_000_000
    platten_m2 = len(platten) * platte_laenge * platte_breite / 1_000_000
    return {
        "platten_anzahl": len(platten),
        "format": f"{platte_laenge:.0f} x {platte_breite:.0f} mm",
        "ausnutzung_prozent": round(teile_m2 / platten_m2 * 100, 1) if platten_m2 else 0.0,
        "zu_gross": zu_gross,
    }


def _bester_platz(
    frei: list[tuple[float, float, float, float]], l: float, b: float, drehbar: bool,
) -> tuple[float, float, float, float] | None:
    """Freies Rechteck mit kleinstem Rest an der kuerzeren Seite -> (x, y, l, b) oder None."""
    beste: tuple[float, float, float, float] | None = None
    bester_rest = math.inf
    for x, y, fl, fb in frei:
        for pl, pb in ((l, b), (b, l)) if drehbar else ((l, b),):
            if pl <= fl and pb <= fb:
                rest = min(fl - pl, fb - pb)
                if rest < bester_rest:
                    beste, bester_rest = (x, y, pl, pb), rest
    return beste


def _belege(frei: list[tuple[float, float, float, float]], x: float, y: float, l: float, b: float) -> None:
    """Teilt alle freien Rechtecke, die das platzierte Teil schneiden, und entfernt enthaltene."""
    neu: list[tuple[float, float, float, float]] = []
    for fx, fy, fl, fb in frei:
        if x >= fx + fl or x + l <= fx or y >= fy + fb or y + b <= fy:
            neu.append((fx, fy, fl, fb))
            continue
        if x > fx:
            neu.append((fx, fy, x - fx, fb))
        if x + l < fx + fl:
            neu.append((x + l, fy, fx + fl - (x + l), fb))
        if y > fy:
            neu.append((fx, fy, fl, y - fy))
        if y + b < fy + fb:
            neu.append((fx, y + b, fl, fy + fb - (y + b)))
    frei[:] = [
        r for i, r in enumerate(neu)
        if not any(
            j != i and o[0] <= r[0] and o[1] <= r[1]
            and o[0] + o[2] >= r[0] + r[2] and o[1] + o[3] >= r[1] + r[3]
            and (o != r or j < i)
            for j, o in enumerate(neu)
        )
    ]


# ----------------------------------------------------------------------
# Stuecklisten-Auswertung (Korpus-Generator und OpenCutList-Import)
# ----------------------------------------------------------------------


def werte_stueckliste_aus(
    teile: list[Teil],
    beschlaege: list[Beschlag],
    *,
    regeln: dict[str, Any],
    maschinen_cfg: dict[str, Any],
    katalog: PreisKatalog,
    qualitaet: str = "standard",
    stunden: dict[str, float] | None = None,
    extra_kanten: list[dict[str, Any]] | None = None,
    massivholz: list[dict[str, Any]] | None = None,
    gegenstand: str = "",
    warnungen: list[str] | None = None,
) -> dict[str, Any]:
    """Fasst eine Stueckliste zu Platten, Kanten, Beschlaegen und Stunden zusammen.

    extra_kanten: [{material, lfm}] fuer Kantenband-Zeilen aus Importen.
    massivholz:   [{bezeichnung, staerke_mm, m3}] fuer Massivholz/Stangenware.
    """
    warnungen = list(warnungen or [])
    verschnitt = float(konfig_wert(regeln, "kalkulation.verschnitt_prozent"))
    zugabe_mm = float(konfig_wert(regeln, "kalkulation.kanten_zugabe_mm"))
    bearbeitung = float(konfig_wert(regeln, "kalkulation.kanten_bearbeitung_eur_lfm"))
    platte_cfg = maschinen_cfg.get("platte_standard", {})
    platte_l = float(platte_cfg.get("laenge_mm", 2800))
    platte_b = float(platte_cfg.get("breite_mm", 2070))
    schnitt = float(platte_cfg.get("schnittbreite_mm", 4))
    platte_m2 = platte_l * platte_b / 1_000_000

    # --- Platten je Material + Staerke ---
    gruppen: dict[tuple[str, float], list[Teil]] = {}
    for t in teile:
        gruppen.setdefault((t.material.strip(), t.staerke_mm), []).append(t)

    platten: list[dict[str, Any]] = []
    for (material, staerke), gruppe in gruppen.items():
        netto = sum(t.flaeche_m2 for t in gruppe)
        brutto = netto * (1 + verschnitt / 100)
        nur_rueckwand = all(t.gruppe == "rueckwand" for t in gruppe)
        preis, quelle = _plattenpreis(material, staerke, katalog, regeln, platte_m2, warnungen, nur_rueckwand)
        zuschnitt = schaetze_platten(gruppe, platte_l, platte_b, schnitt)
        for z in zuschnitt["zu_gross"]:
            warnungen.append(f"Teil groesser als Plattenformat {zuschnitt['format']}: {z} - Sonderformat oder Stoss")
        # Verschnitt laut Zuschnitt, gleiche Definition wie im Kalkulator (Aufschlag auf Netto)
        verschnitt_zuschnitt = (zuschnitt["platten_anzahl"] * platte_m2 / netto - 1) * 100 if netto else 0.0
        zuschnitt["verschnitt_prozent"] = round(verschnitt_zuschnitt, 1)
        # Bei 1-2 Platten bleibt der Rest im Lager - erst ab 3 Platten aussagekraeftig
        if zuschnitt["platten_anzahl"] >= 3 and verschnitt_zuschnitt > verschnitt + 10:
            warnungen.append(
                f"{material or 'Ohne Material'} {staerke:g} mm: Zuschnitt-Schaetzung ergibt "
                f"{verschnitt_zuschnitt:.0f} % Verschnitt (kalkuliert {verschnitt:g} %) - "
                f"Verschnitt im Kalkulator pruefen"
            )
        platten.append({
            "material": material or "Ohne Material",
            "staerke_mm": staerke,
            "netto_m2": round(netto, 3),
            "verschnitt_prozent": verschnitt,
            "brutto_m2": round(brutto, 3),
            "preis_m2": round(preis, 2),
            "preis_quelle": quelle,
            "kosten": round(brutto * preis, 2),
            "zuschnitt": {k: v for k, v in zuschnitt.items() if k != "zu_gross"},
        })

    # --- Kanten je Kantenmaterial ---
    kanten_lfm: dict[str, float] = {}
    for t in teile:
        if t.kanten_mm:
            name = t.kante_material or "Kante"
            lfm = (sum(t.kanten_mm) + zugabe_mm * len(t.kanten_mm)) / 1000 * t.anzahl
            kanten_lfm[name] = kanten_lfm.get(name, 0.0) + lfm
    for ek in extra_kanten or []:
        name = ek.get("material") or "Kante"
        kanten_lfm[name] = kanten_lfm.get(name, 0.0) + float(ek.get("lfm", 0))

    kanten: list[dict[str, Any]] = []
    for name, lfm in kanten_lfm.items():
        treffer = katalog.suche(name, "kante")
        if treffer:
            preis, quelle = treffer["preis"], treffer["quelle"]
        else:
            preis, quelle = float(konfig_wert(regeln, "fallback_preise.kante_eur_lfm")), "Richtwert korpus.yaml"
        kanten.append({
            "material": name,
            "lfm": round(lfm, 2),
            "preis_lfm": round(preis, 2),
            "bearbeitung_lfm": bearbeitung,
            "preis_quelle": quelle,
            "kosten": round(lfm * (preis + bearbeitung), 2),
        })

    # --- Beschlaege (gleiche Bezeichnung zusammenfassen) ---
    beschlag_summen: dict[str, Beschlag] = {}
    for b in beschlaege:
        if b.bezeichnung in beschlag_summen:
            beschlag_summen[b.bezeichnung].anzahl += b.anzahl
        else:
            beschlag_summen[b.bezeichnung] = Beschlag(b.schluessel, b.bezeichnung, b.anzahl, b.preis_fallback)
    beschlag_liste: list[dict[str, Any]] = []
    for b in beschlag_summen.values():
        treffer = katalog.suche(b.bezeichnung, "beschlag")
        if treffer:
            preis, quelle = treffer["preis"], treffer["quelle"]
        elif b.preis_fallback > 0:
            preis, quelle = b.preis_fallback, "Richtwert korpus.yaml"
        else:
            preis, quelle = 0.0, "offen"
        beschlag_liste.append({
            "bezeichnung": b.bezeichnung,
            "anzahl": b.anzahl,
            "preis": round(preis, 2),
            "preis_quelle": quelle,
            "kosten": round(b.anzahl * preis, 2),
        })

    # --- Massivholz (nur aus Importen) ---
    massivholz_liste = [
        {"bezeichnung": m["bezeichnung"], "staerke_mm": m.get("staerke_mm", 0), "m3": round(float(m["m3"]), 4)}
        for m in massivholz or []
    ]

    # --- Stunden: CNC aus Brutto-Flaeche (Halbformat-Aequivalente) ---
    brutto_gesamt = sum(pl["brutto_m2"] for pl in platten)
    halbformat_m2 = HALBFORMAT["breite"] * HALBFORMAT["hoehe"] / 1_000_000
    cnc_cfg = maschinen_cfg.get("holzher_nextec_7707", {})
    kap = cnc_cfg.get("kapazitaet_hochwertig" if qualitaet == "hochwertig" else "kapazitaet_standard", {})
    platten_pro_schicht = float(kap.get("halbformat_platten_pro_schicht", 15))
    schicht_h = float(kap.get("schichtdauer_stunden", 8))
    aequivalent = brutto_gesamt / halbformat_m2
    cnc_h = 0.0
    if brutto_gesamt > 0 and platten_pro_schicht > 0:
        cnc_h = aequivalent / platten_pro_schicht * schicht_h + float(cnc_cfg.get("ruestzeit_min", 30)) / 60

    stunden_gesamt = {"Arbeitsvorbereitung": 0.0, "CNC": cnc_h, "Bankraum": 0.0, "Montage": 0.0}
    for kat, h in (stunden or {}).items():
        stunden_gesamt[kat] = stunden_gesamt.get(kat, 0.0) + h
    stunden_gesamt = {kat: round(h, 2) for kat, h in stunden_gesamt.items()}

    materialkosten = (
        sum(pl["kosten"] for pl in platten)
        + sum(ka["kosten"] for ka in kanten)
        + sum(be["kosten"] for be in beschlag_liste)
    )

    return {
        "status": "ok",
        "gegenstand": gegenstand,
        "teile": [
            {
                "bezeichnung": t.bezeichnung,
                "gruppe": t.gruppe,
                "anzahl": t.anzahl,
                "laenge_mm": round(t.laenge_mm, 1),
                "breite_mm": round(t.breite_mm, 1),
                "staerke_mm": t.staerke_mm,
                "material": t.material or "Ohne Material",
                "kanten_lfm": round(sum(t.kanten_mm) / 1000 * t.anzahl, 2),
                "flaeche_m2": round(t.flaeche_m2, 3),
            }
            for t in teile
        ],
        "platten": platten,
        "kanten": kanten,
        "beschlaege": beschlag_liste,
        "massivholz": massivholz_liste,
        "stunden": stunden_gesamt,
        "kennzahlen": {
            "teile_anzahl": sum(t.anzahl for t in teile),
            "flaeche_netto_m2": round(sum(pl["netto_m2"] for pl in platten), 3),
            "flaeche_brutto_m2": round(brutto_gesamt, 3),
            "platten_zuschnitt": sum(pl["zuschnitt"]["platten_anzahl"] for pl in platten),
            "halbformat_aequivalent": round(aequivalent, 2),
            "kanten_lfm": round(sum(ka["lfm"] for ka in kanten), 2),
            "beschlaege_stueck": sum(be["anzahl"] for be in beschlag_liste),
            "stunden_gesamt": round(sum(stunden_gesamt.values()), 2),
            "materialkosten_netto": round(materialkosten, 2),
        },
        "kalkulator_import": {
            "gegenstand": gegenstand,
            "platten": [
                {
                    "bezeichnung": pl["material"],
                    "staerke": f"{pl['staerke_mm']:g}mm",
                    "verschnitt": pl["verschnitt_prozent"],
                    "preisQm": pl["preis_m2"],
                    "menge": pl["netto_m2"],
                }
                for pl in platten
            ],
            "massivholz": [
                {
                    "bezeichnung": m["bezeichnung"],
                    "staerke": f"{m['staerke_mm']:g}mm" if m["staerke_mm"] else "",
                    "verschnitt": verschnitt,
                    "preisCbm": 0,
                    "menge": m["m3"],
                }
                for m in massivholz_liste
            ],
            "kanten": [
                {
                    "bezeichnung": ka["material"],
                    "laenge": ka["lfm"],
                    "bearbeitung": ka["bearbeitung_lfm"],
                    "kantePreis": ka["preis_lfm"],
                }
                for ka in kanten
            ],
            "beschlaege": [
                {"bezeichnung": be["bezeichnung"], "anzahl": be["anzahl"], "einheit": "Stk", "preis": be["preis"]}
                for be in beschlag_liste
            ],
            "lohn": {kat: h for kat, h in stunden_gesamt.items() if h > 0},
        },
        "warnungen": warnungen,
    }


def _plattenpreis(
    material: str, staerke: float, katalog: PreisKatalog, regeln: dict[str, Any],
    platte_m2: float, warnungen: list[str], rueckwand: bool = False,
) -> tuple[float, str]:
    """Plattenpreis pro m2: DB (mit oder ohne Staerke im Namen), sonst Richtwert."""
    treffer = None
    if material.strip():
        treffer = katalog.suche(f"{material} {staerke:g}mm", "platte") or katalog.suche(material, "platte")
    if treffer:
        if treffer["einheit"].lower() in _EINHEITEN_PRO_PLATTE:
            warnungen.append(
                f"Preis fuer '{material}' ist pro Platte hinterlegt - umgerechnet auf "
                f"{platte_m2:.2f} m2 Plattenformat"
            )
            return treffer["preis"] / platte_m2, treffer["quelle"] + " (pro Platte, umgerechnet)"
        return treffer["preis"], treffer["quelle"]
    fallback = float(konfig_wert(regeln, "fallback_preise.rueckwand_eur_m2" if rueckwand else "fallback_preise.platte_eur_m2"))
    name = material or "Ohne Material"
    warnungen.append(f"Kein Preis fuer '{name}' in den Materialpreisen - Richtwert {fallback:g} EUR/m2 verwendet")
    return fallback, "Richtwert korpus.yaml"


def berechne_korpus(
    p: KorpusParameter,
    *,
    regeln: dict[str, Any],
    maschinen_cfg: dict[str, Any],
    katalog: PreisKatalog,
) -> dict[str, Any]:
    """Kompletter Lauf: Parameter -> Stueckliste -> Auswertung."""
    teile, beschlaege, stunden, warnungen = generiere_korpus(p, regeln)
    gegenstand = p.bezeichnung or (
        f"{p.anzahl}x {p.typ.capitalize()} {p.breite_mm:g}x{p.hoehe_mm:g}x{p.tiefe_mm:g}"
    )
    ergebnis = werte_stueckliste_aus(
        teile, beschlaege,
        regeln=regeln, maschinen_cfg=maschinen_cfg, katalog=katalog,
        qualitaet=p.qualitaet, stunden=stunden, gegenstand=gegenstand, warnungen=warnungen,
    )
    ergebnis["parameter"] = {k: v for k, v in vars(p).items()}
    return ergebnis
