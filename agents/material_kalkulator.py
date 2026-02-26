"""
MaterialKalkulator – Subagent 2.

Berechnet Materialkosten pro LV-Position:
- Plattenmaterial, Kanten, Beschlaege, Mineralwerkstoff
- Preise aus interner Preisliste (DB oder manuell geladen)
- Plattenoptimierung (Zuschnitt -> Plattenanzahl)
- Sonderlogik: Lackierung -> Fremdleistung mit Aufschlag
- Warnung bei unbekannten Materialien
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

from agents.base_agent import AgentMessage, BaseAgent

# Standard-Plattenformate (Halbformat in mm)
HALBFORMAT = {"breite": 2100, "hoehe": 1300}
VOLLFORMAT = {"breite": 2800, "hoehe": 2100}

# Geschaetzte Materialkosten pro Kategorie wenn nichts in DB
# Realistische Fallback-Preise fuer gaengige Schreinermaterialien
FALLBACK_PREISE: dict[str, dict[str, Any]] = {
    "platte": {"preis": 35.0, "einheit": "m2", "beschreibung": "Standard-Platte geschaetzt"},
    "kante": {"preis": 2.50, "einheit": "lfm", "beschreibung": "ABS-Kante geschaetzt"},
    "beschlag": {"preis": 8.50, "einheit": "STK", "beschreibung": "Standard-Beschlag geschaetzt"},
    "mineralwerkstoff": {"preis": 120.0, "einheit": "m2", "beschreibung": "Mineralwerkstoff geschaetzt"},
    "lack_fremdleistung": {"preis": 65.0, "einheit": "m2", "beschreibung": "Lackierung Fremdleistung geschaetzt"},
    "sonstiges": {"preis": 15.0, "einheit": "STK", "beschreibung": "Sonstiges Material geschaetzt"},
}

# Materialerkennung: Stichwort -> Kategorie
MATERIAL_KATEGORIEN: dict[str, str] = {
    "eiche": "platte", "buche": "platte", "birke": "platte", "nuss": "platte",
    "ahorn": "platte", "esche": "platte", "kirsch": "platte", "fichte": "platte",
    "mdf": "platte", "hdf": "platte", "span": "platte", "multiplex": "platte",
    "sperrholz": "platte", "laminat": "platte", "melamin": "platte",
    "furnier": "platte", "dekor": "platte", "egger": "platte",
    "kante": "kante", "abs": "kante", "umleimer": "kante",
    "scharnier": "beschlag", "schublade": "beschlag", "griff": "beschlag",
    "softclose": "beschlag", "topf": "beschlag", "blum": "beschlag",
    "haefele": "beschlag", "hettich": "beschlag", "auszug": "beschlag",
    "corian": "mineralwerkstoff", "mineralwerk": "mineralwerkstoff",
    "himacs": "mineralwerkstoff", "solid surface": "mineralwerkstoff",
    "granit": "mineralwerkstoff", "quarz": "mineralwerkstoff",
}


class MaterialKalkulator(BaseAgent):
    """Berechnet Materialkosten fuer alle Positionen eines Projekts."""

    def __init__(self) -> None:
        super().__init__(name="material_kalkulator")
        self._preisliste: dict[str, dict[str, Any]] = {}
        self._db_pfad: str = ""

    def configure(self, db_pfad: str = "data/kalkulation.db") -> None:
        """Konfiguriert DB-Pfad fuer Preislisten-Lookup."""
        self._db_pfad = db_pfad

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Verarbeitet kalkuliere_material-Anfragen."""
        positionen = message.payload.get("positionen", [])

        # Preisliste aus DB laden falls verfuegbar
        if self._db_pfad and Path(self._db_pfad).exists():
            self._load_preisliste_from_db()

        materialliste: list[dict[str, Any]] = []
        fremdleistungen: list[dict[str, Any]] = []
        warnungen: list[str] = []
        gesamt = 0.0

        for pos in positionen:
            ergebnis = self._kalkuliere_position(pos)
            materialliste.append(ergebnis["material"])
            gesamt += ergebnis["kosten"]

            if ergebnis.get("fremdleistung"):
                fremdleistungen.append(ergebnis["fremdleistung"])
                gesamt += ergebnis["fremdleistung"].get("geschaetzte_kosten", 0)

            warnungen.extend(ergebnis.get("warnungen", []))

        return message.create_response(
            sender=self.name,
            payload={
                "materialliste": materialliste,
                "materialkosten_gesamt": round(gesamt, 2),
                "fremdleistungen": fremdleistungen,
                "warnungen": warnungen,
            },
        )

    def _kalkuliere_position(self, position: dict) -> dict[str, Any]:
        """Kalkuliert Materialkosten fuer eine einzelne Position."""
        pos_nr = position.get("pos_nr", "?")
        menge = float(position.get("menge", 0))
        material = position.get("material", "")
        ist_lackierung = bool(position.get("ist_lackierung", False))
        platten_anzahl = float(position.get("platten_anzahl", 0))
        kantenlaenge = float(position.get("kantenlaenge_lfm", 0))

        warnungen: list[str] = []
        teil_kosten: list[dict[str, Any]] = []

        # 1. Plattenmaterial
        if platten_anzahl > 0 or self._erkenne_kategorie(material) == "platte":
            platten_preis = self._lookup_preis(material, "platte")
            # Plattenkosten: Anzahl Platten * Preis pro Platte (Halbformat ~2.73 m2)
            platte_m2 = (HALBFORMAT["breite"] / 1000) * (HALBFORMAT["hoehe"] / 1000)
            effektive_platten = platten_anzahl if platten_anzahl > 0 else menge
            platte_kosten = effektive_platten * platte_m2 * platten_preis["preis"]

            teil_kosten.append({
                "typ": "platte",
                "beschreibung": material or "Plattenmaterial",
                "menge": effektive_platten,
                "einheit": "Platten",
                "einheitspreis": round(platte_m2 * platten_preis["preis"], 2),
                "kosten": round(platte_kosten, 2),
                "quelle": platten_preis["quelle"],
            })

            if platten_preis["quelle"] == "fallback":
                warnungen.append(
                    f"Pos {pos_nr}: Material '{material}' nicht in Preisliste - Schaetzpreis verwendet"
                )

        # 2. Kanten
        if kantenlaenge > 0:
            kanten_preis = self._lookup_preis("ABS-Kante", "kante")
            kanten_kosten = kantenlaenge * kanten_preis["preis"]
            teil_kosten.append({
                "typ": "kante",
                "beschreibung": "Kantenband",
                "menge": kantenlaenge,
                "einheit": "lfm",
                "einheitspreis": kanten_preis["preis"],
                "kosten": round(kanten_kosten, 2),
                "quelle": kanten_preis["quelle"],
            })

        # 3. Beschlaege (geschaetzt pro Einheit)
        beschlag_anzahl = float(position.get("bohrungen_anzahl", 0))
        if beschlag_anzahl > 0:
            beschlag_preis = self._lookup_preis("Beschlag", "beschlag")
            beschlag_kosten = beschlag_anzahl * beschlag_preis["preis"]
            teil_kosten.append({
                "typ": "beschlag",
                "beschreibung": "Beschlaege",
                "menge": beschlag_anzahl,
                "einheit": "STK",
                "einheitspreis": beschlag_preis["preis"],
                "kosten": round(beschlag_kosten, 2),
                "quelle": beschlag_preis["quelle"],
            })

        # Gesamtkosten Material
        kosten_summe = sum(tk["kosten"] for tk in teil_kosten)

        # Falls gar keine Teilkosten berechnet wurden: Fallback auf menge * Schaetzpreis
        if not teil_kosten and menge > 0:
            kat = self._erkenne_kategorie(material)
            fallback = self._lookup_preis(material, kat)
            kosten_summe = menge * fallback["preis"]
            teil_kosten.append({
                "typ": kat,
                "beschreibung": material or "Unbekanntes Material",
                "menge": menge,
                "einheit": position.get("einheit", "STK"),
                "einheitspreis": fallback["preis"],
                "kosten": round(kosten_summe, 2),
                "quelle": fallback["quelle"],
            })
            if fallback["quelle"] == "fallback":
                warnungen.append(
                    f"Pos {pos_nr}: Kein Material angegeben - Fallback-Schaetzung verwendet"
                )

        ergebnis: dict[str, Any] = {
            "material": {
                "pos_nr": pos_nr,
                "material": material,
                "menge": menge,
                "teilkosten": teil_kosten,
                "gesamtkosten": round(kosten_summe, 2),
            },
            "kosten": round(kosten_summe, 2),
            "warnungen": warnungen,
        }

        # Lackierung -> Fremdleistung
        if ist_lackierung:
            # Lackierkosten schaetzen: basierend auf Flaeche oder pauschal pro Einheit
            lack_preis = FALLBACK_PREISE["lack_fremdleistung"]["preis"]
            platten_fuer_lack = platten_anzahl if platten_anzahl > 0 else menge
            platte_m2 = (HALBFORMAT["breite"] / 1000) * (HALBFORMAT["hoehe"] / 1000)
            lack_flaeche = platten_fuer_lack * platte_m2
            lack_kosten = lack_flaeche * lack_preis

            ergebnis["fremdleistung"] = {
                "pos_nr": pos_nr,
                "typ": "lackierung",
                "beschreibung": f"Lackierung {lack_flaeche:.1f} m2 fuer Pos {pos_nr}",
                "flaeche_m2": round(lack_flaeche, 2),
                "preis_pro_m2": lack_preis,
                "geschaetzte_kosten": round(lack_kosten, 2),
            }

        return ergebnis

    def _lookup_preis(self, material: str, kategorie: str = "") -> dict[str, Any]:
        """Sucht Material in der Preisliste (DB -> manuell -> Fallback)."""
        # 1. Exakter Match in manueller Preisliste
        if material in self._preisliste:
            info = self._preisliste[material]
            return {"preis": info["preis"], "quelle": "preisliste", "einheit": info.get("einheit", "")}

        # 2. Teilmatch in manueller Preisliste
        material_lower = material.lower()
        for name, info in self._preisliste.items():
            if material_lower in name.lower() or name.lower() in material_lower:
                return {"preis": info["preis"], "quelle": "preisliste_teilmatch", "einheit": info.get("einheit", "")}

        # 3. Kategorie-basierter Fallback
        if not kategorie:
            kategorie = self._erkenne_kategorie(material)

        fallback = FALLBACK_PREISE.get(kategorie, FALLBACK_PREISE["sonstiges"])
        return {"preis": fallback["preis"], "quelle": "fallback", "einheit": fallback["einheit"]}

    def _erkenne_kategorie(self, material: str) -> str:
        """Erkennt die Materialkategorie anhand von Stichworten."""
        if not material:
            return "sonstiges"
        material_lower = material.lower()
        for stichwort, kategorie in MATERIAL_KATEGORIEN.items():
            if stichwort in material_lower:
                return kategorie
        return "sonstiges"

    def _load_preisliste_from_db(self) -> None:
        """Laedt aktuelle Materialpreise aus der SQLite-Datenbank."""
        try:
            conn = sqlite3.connect(self._db_pfad)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT material_name, kategorie, preis, einheit "
                "FROM materialpreise WHERE gueltig_bis = '' ORDER BY material_name"
            )
            for row in cursor.fetchall():
                self._preisliste[row["material_name"]] = {
                    "preis": row["preis"],
                    "kategorie": row["kategorie"],
                    "einheit": row["einheit"],
                    "quelle": "datenbank",
                }
            conn.close()
            self.logger.info("Preisliste aus DB geladen: %d Eintraege", len(self._preisliste))
        except Exception as exc:
            self.logger.warning("Preisliste konnte nicht aus DB geladen werden: %s", exc)

    def load_preisliste(self, daten: dict[str, dict[str, Any]]) -> None:
        """Laedt eine Preisliste manuell (z.B. fuer Tests)."""
        self._preisliste.update(daten)
        self.logger.info("Preisliste manuell geladen: %d Eintraege", len(daten))

    def plattenoptimierung(
        self, bauteile: list[dict], rohplatte: dict | None = None
    ) -> dict[str, Any]:
        """Berechnet benoetigte Plattenanzahl mit Verschnitt-Schaetzung.

        Vereinfachter Algorithmus (kein volles 2D-Nesting):
        - Berechnet Gesamtflaeche aller Bauteile
        - Addiert Verschnittfaktor (Standard 15%)
        - Teilt durch Plattenflaeche
        """
        if rohplatte is None:
            rohplatte = HALBFORMAT

        platte_m2 = (rohplatte["breite"] / 1000) * (rohplatte["hoehe"] / 1000)
        gesamt_flaeche = 0.0

        for teil in bauteile:
            breite_m = teil.get("breite", 0) / 1000
            hoehe_m = teil.get("hoehe", 0) / 1000
            menge = teil.get("menge", 1)
            gesamt_flaeche += breite_m * hoehe_m * menge

        verschnitt_faktor = 1.15  # 15% Verschnitt
        benoetigte_flaeche = gesamt_flaeche * verschnitt_faktor
        platten_anzahl = math.ceil(benoetigte_flaeche / platte_m2) if platte_m2 > 0 else 0
        verschnitt_prozent = ((platten_anzahl * platte_m2 - gesamt_flaeche) / (platten_anzahl * platte_m2) * 100) if platten_anzahl > 0 else 0

        return {
            "bauteile_flaeche_m2": round(gesamt_flaeche, 2),
            "benoetigte_flaeche_m2": round(benoetigte_flaeche, 2),
            "platte_flaeche_m2": round(platte_m2, 2),
            "platten_anzahl": platten_anzahl,
            "verschnitt_prozent": round(verschnitt_prozent, 1),
        }
