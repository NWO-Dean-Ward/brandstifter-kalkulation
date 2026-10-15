"""
OpenCutList-Import - Stuecklisten aus SketchUp (Erweiterung OpenCutList).

Liest den CSV-Export der Zuschnittliste. OpenCutList-Standard: Quelle
"Zuschnittliste", Semikolon, UTF-8 mit BOM. Komma/Tab und UTF-16 werden
ebenfalls erkannt. Spaltenbeschriftung auf Deutsch, Englisch oder Franzoesisch
(Texte aus den OpenCutList-Uebersetzungen, tab.cutlist.export.*).

Masse kommen als SketchUp-Laengen in Modelleinheit: "600mm", "60 cm", "0,6m",
"23 5/8\"", "1' 11 5/8\"". Zahlen ohne Einheit werden als mm gelesen.

Ergebnis sind Teile/Beschlaege fuer korpus_generator.werte_stueckliste_aus,
damit Korpus-Generator und SketchUp-Import dieselbe Rechenlogik nutzen.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from agents.korpus_generator import Beschlag, Teil

# Spaltentitel je Sprache (OpenCutList i18n) + interne Formelnamen
SPALTEN: dict[str, tuple[str, ...]] = {
    "bezeichnung": ("bezeichnung", "designation", "désignation", "name"),
    "anzahl": ("anzahl", "quantity", "quantité", "count"),
    "laenge_roh": ("länge - roh", "length - raw", "longueur débit", "cutting_length"),
    "breite_roh": ("breite - roh", "width - raw", "largeur débit", "cutting_width"),
    "dicke_roh": ("dicke - roh", "thickness - raw", "épaisseur débit", "cutting_thickness"),
    "laenge": ("länge", "length", "longueur capable", "bbox_length"),
    "breite": ("breite", "width", "largeur capable", "bbox_width"),
    "dicke": ("dicke", "thickness", "épaisseur capable", "bbox_thickness"),
    "materialtyp": ("materialtyp", "material type", "type de matière", "material_type"),
    "material": ("materialname", "material name", "nom de la matière", "material_name"),
    "kante_l1": ("kantenband länge 1", "edge length 1", "chant longueur 1", "edge_ymin"),
    "kante_l2": ("kantenband länge 2", "edge length 2", "chant longueur 2", "edge_ymax"),
    "kante_b1": ("kantenband breite 1", "edge width 1", "chant largeur 1", "edge_xmin"),
    "kante_b2": ("kantenband breite 2", "edge width 2", "chant largeur 2", "edge_xmax"),
}

MATERIALTYPEN: dict[str, tuple[str, ...]] = {
    "platte": ("platte", "sheet goods", "panneau"),
    "massivholz": ("massivholz", "solid wood", "bois massif"),
    "stangenware": ("stangenware", "dimensional", "barre"),
    "kante": ("kantenband", "edge banding", "bande de chant"),
    "zubehoer": ("zubehör", "hardware", "accessoire"),
    "furnier": ("furnier", "veneer", "feuille de placage"),
    "unbestimmt": ("unbestimmt", "undefined", "non défini"),
}

OHNE_MATERIAL = ("ohne material", "without material", "sans matière")


@dataclass
class OpenCutListErgebnis:
    datei: str
    teile: list[Teil] = field(default_factory=list)
    beschlaege: list[Beschlag] = field(default_factory=list)
    kanten: list[dict[str, Any]] = field(default_factory=list)       # {material, lfm}
    massivholz: list[dict[str, Any]] = field(default_factory=list)   # {bezeichnung, staerke_mm, m3}
    hinweise: list[str] = field(default_factory=list)
    zeilen: int = 0


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").replace(" ", " ").strip().lower()
    return re.sub(r"\s+", " ", text)


def _zahl(text: str) -> float:
    """Deutsche und englische Zahlen: '1.200,5' / '1,200.5' / '600,5' / '600.5'."""
    s = text.strip().replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return float(s)


def parse_laenge(text: str) -> tuple[float | None, bool]:
    """SketchUp-Laenge -> (mm, Einheit war angegeben)."""
    s = _norm(text).lstrip("~").strip()
    if not s:
        return None, False
    try:
        if '"' in s or "'" in s:
            return _zoll_zu_mm(s), True
        m = re.fullmatch(r"(-?[\d.,]+)\s*(mm|cm|m)?", s)
        if not m:
            return None, False
        faktor = {"mm": 1.0, "cm": 10.0, "m": 1000.0}.get(m.group(2) or "", 1.0)
        return _zahl(m.group(1)) * faktor, m.group(2) is not None
    except ValueError:
        return None, False


def _zoll_zu_mm(s: str) -> float | None:
    zoll = 0.0
    fuss = re.match(r"\s*([\d.,]+)\s*'", s)
    if fuss:
        zoll += _zahl(fuss.group(1)) * 12
        s = s[fuss.end():]
    m = re.search(r"(?:([\d.,]+)\s+)?(?:(\d+)\s*/\s*(\d+)|([\d.,]+))\s*\"", s)
    if m:
        if m.group(4):
            zoll += _zahl(m.group(4))
        else:
            zoll += _zahl(m.group(1) or "0") + int(m.group(2)) / int(m.group(3))
    elif not fuss:
        return None
    return zoll * 25.4


def _dekodiere(inhalt: bytes) -> str:
    if inhalt.startswith(b"\xff\xfe"):
        return inhalt[2:].decode("utf-16-le")
    if inhalt.startswith(b"\xfe\xff"):
        return inhalt[2:].decode("utf-16-be")
    if inhalt.startswith(b"\xef\xbb\xbf"):
        return inhalt[3:].decode("utf-8")
    try:
        return inhalt.decode("utf-8")
    except UnicodeDecodeError:
        return inhalt.decode("cp1252")


def _trennzeichen(text: str) -> str:
    erste_zeile = next((z for z in text.splitlines() if z.strip()), "")
    return max((";", "\t", ","), key=erste_zeile.count)


def _spalten_index(header: list[str]) -> dict[str, int]:
    index: dict[str, int] = {}
    for i, titel in enumerate(header):
        t = _norm(titel)
        for schluessel, varianten in SPALTEN.items():
            if schluessel not in index and t in varianten:
                index[schluessel] = i
                break
    return index


def _materialtyp(text: str) -> str:
    t = _norm(text)
    for typ, varianten in MATERIALTYPEN.items():
        if t in varianten:
            return typ
    return ""


def parse_opencutlist_csv(inhalt: bytes, dateiname: str = "") -> OpenCutListErgebnis:
    """Parst einen OpenCutList-Zuschnittlisten-Export.

    Wirft ValueError, wenn keine Zuschnittliste erkannt wird.
    """
    text = _dekodiere(inhalt)
    zeilen = list(csv.reader(StringIO(text), delimiter=_trennzeichen(text)))
    zeilen = [z for z in zeilen if any(zelle.strip() for zelle in z)]
    if not zeilen:
        raise ValueError("Datei ist leer")

    sp = _spalten_index(zeilen[0])
    hat_laenge = any(k in sp for k in ("laenge_roh", "laenge"))
    if "bezeichnung" not in sp or "anzahl" not in sp or not hat_laenge:
        raise ValueError(
            "Keine OpenCutList-Zuschnittliste erkannt (Spalten Bezeichnung, Anzahl und Laenge "
            "erwartet). Export-Quelle 'Zuschnittliste' waehlen."
        )

    ergebnis = OpenCutListErgebnis(datei=dateiname, zeilen=len(zeilen) - 1)
    ohne_einheit = False
    unbestimmt_als_platte = False
    massivholz: dict[tuple[str, float], float] = {}

    def zelle(zeile: list[str], schluessel: str) -> str:
        i = sp.get(schluessel)
        return zeile[i].strip() if i is not None and i < len(zeile) else ""

    def mass(zeile: list[str], *schluessel: str) -> float:
        nonlocal ohne_einheit
        for s in schluessel:
            wert, mit_einheit = parse_laenge(zelle(zeile, s))
            if wert:
                ohne_einheit = ohne_einheit or not mit_einheit
                return round(wert, 1)
        return 0.0

    for nr, zeile in enumerate(zeilen[1:], start=2):
        name = zelle(zeile, "bezeichnung") or f"Teil Zeile {nr}"
        try:
            anzahl = int(round(_zahl(zelle(zeile, "anzahl") or "1")))
        except ValueError:
            ergebnis.hinweise.append(f"Zeile {nr}: Anzahl '{zelle(zeile, 'anzahl')}' nicht lesbar - uebersprungen")
            continue
        if anzahl <= 0:
            continue

        material = zelle(zeile, "material")
        if _norm(material) in OHNE_MATERIAL:
            material = ""
        typ = _materialtyp(zelle(zeile, "materialtyp"))
        laenge = mass(zeile, "laenge_roh", "laenge")
        breite = mass(zeile, "breite_roh", "breite")
        dicke = mass(zeile, "dicke_roh", "dicke")

        if not typ:
            typ = "platte" if laenge and breite and dicke else "zubehoer"
        if typ == "unbestimmt":
            if not (laenge and breite and dicke):
                typ = "zubehoer"
            else:
                typ = "platte"
                unbestimmt_als_platte = True

        if typ == "zubehoer":
            ergebnis.beschlaege.append(Beschlag("import", name, anzahl))
        elif typ == "kante":
            if laenge:
                ergebnis.kanten.append({"material": material or name, "lfm": laenge * anzahl / 1000})
        elif typ == "furnier":
            ergebnis.hinweise.append(f"Zeile {nr}: Furnier '{name}' nicht uebernommen - bitte manuell erfassen")
        elif typ in ("massivholz", "stangenware"):
            if laenge and breite and dicke:
                key = (material or name, dicke)
                massivholz[key] = massivholz.get(key, 0.0) + laenge * breite * dicke * anzahl / 1e9
            else:
                ergebnis.hinweise.append(f"Zeile {nr}: '{name}' ohne vollstaendige Masse - uebersprungen")
        else:
            if not (laenge and breite):
                ergebnis.hinweise.append(f"Zeile {nr}: '{name}' ohne Laenge/Breite - uebersprungen")
                continue
            if not material:
                ergebnis.hinweise.append(f"Zeile {nr}: '{name}' ohne Material - in SketchUp Material zuweisen")
            fertig_l = mass(zeile, "laenge", "laenge_roh")
            fertig_b = mass(zeile, "breite", "breite_roh")
            kanten_mm: list[float] = []
            kante_material = ""
            for schluessel, kantenlaenge in (("kante_l1", fertig_l), ("kante_l2", fertig_l),
                                            ("kante_b1", fertig_b), ("kante_b2", fertig_b)):
                kante = zelle(zeile, schluessel)
                if kante:
                    kanten_mm.append(kantenlaenge)
                    kante_material = kante_material or kante
            ergebnis.teile.append(Teil(
                name, anzahl, laenge, breite, dicke, material, "import",
                kanten_mm, kante_material,
            ))

    ergebnis.massivholz = [
        {"bezeichnung": mat, "staerke_mm": staerke, "m3": m3} for (mat, staerke), m3 in massivholz.items()
    ]

    # Kantenband-Gruppen enthalten die Kanten bereits -> Kanten an den Teilen nicht doppelt zaehlen
    if ergebnis.kanten and any(t.kanten_mm for t in ergebnis.teile):
        for t in ergebnis.teile:
            t.kanten_mm = []
        ergebnis.hinweise.append("Kanten aus den Kantenband-Zeilen uebernommen (nicht zusaetzlich aus den Teilen)")
    if ohne_einheit:
        ergebnis.hinweise.append("Masse ohne Einheit gefunden - als mm gelesen")
    if unbestimmt_als_platte:
        ergebnis.hinweise.append("Material mit Typ 'Unbestimmt' als Platte uebernommen - Materialtyp in OpenCutList setzen")
    if not (ergebnis.teile or ergebnis.beschlaege or ergebnis.kanten or ergebnis.massivholz):
        ergebnis.hinweise.append("Keine verwertbaren Zeilen gefunden")
    return ergebnis
