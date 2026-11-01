"""
KorpusKalkulator - Subagent 13.

Rechnet Korpus-Positionen einer Ausschreibung (kalkulationsquelle = "korpus") mit dem
Korpus-Generator statt mit der Standard-Schaetzung von Material-, Maschinen- und
Lohn-Kalkulator. Das Ergebnis hat deren Struktur, damit Zuschlaege, Kapazitaeten,
Positionspreise und Exporte unveraendert funktionieren.

Kostenzuordnung (Saetze aus maschinen.yaml und stundensaetze.yaml, wie in der Pipeline):
- Material:  Platten (brutto m2 x Preis) + Kantenmaterial + Beschlaege
- Maschinen: CNC-Stunden x CNC-Stundensatz + Kanten-Bearbeitung (EUR/lfm, korpus.yaml)
- Lohn:      Arbeitsvorbereitung + CNC-Bedienung (= CNC-Stunden) + Bankraum + Montage

Ungueltige Korpus-Parameter fuehren nicht zum Abbruch: die Position wird als
"fehlgeschlagen" gemeldet und von der Standard-Schaetzung gerechnet (mit Warnung).
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any

from agents.base_agent import AgentMessage, BaseAgent
from agents.korpus_generator import KorpusParameter, PreisKatalog, berechne_korpus

_PARAMETER_FELDER = {f.name for f in dataclasses.fields(KorpusParameter)}


def parameter_aus_position(position: dict[str, Any]) -> KorpusParameter:
    """Baut die Korpus-Parameter einer Position: anzahl = Menge x Korpusse je Einheit.

    Wirft ValueError, wenn die Parameter fehlen oder die Menge 0 ist.
    """
    roh = position.get("korpus_parameter") or ""
    if not roh:
        raise ValueError("Keine Korpus-Parameter gespeichert")
    daten = json.loads(roh) if isinstance(roh, str) else dict(roh)
    menge = float(position.get("menge", 0) or 0)
    if menge <= 0:
        raise ValueError("Menge der Position ist 0")
    je_einheit = max(int(daten.get("anzahl", 1) or 1), 1)

    p = KorpusParameter(**{k: v for k, v in daten.items() if k in _PARAMETER_FELDER})
    p.anzahl = math.ceil(round(menge * je_einheit, 6))
    if not p.bezeichnung:
        p.bezeichnung = position.get("kurztext", "")
    return p


class KorpusKalkulator(BaseAgent):
    """Kalkuliert Korpus-Positionen mit dem Korpus-Generator."""

    def __init__(self) -> None:
        super().__init__(name="korpus_kalkulator")
        self._regeln: dict[str, Any] = {}
        self._maschinen: dict[str, Any] = {}
        self._stundensaetze: dict[str, Any] = {}
        self._db_pfad: str = ""

    def configure(
        self, regeln: dict[str, Any], maschinen: dict[str, Any],
        stundensaetze: dict[str, Any], db_pfad: str = "data/kalkulation.db",
    ) -> None:
        self._regeln = regeln
        self._maschinen = maschinen
        self._stundensaetze = stundensaetze
        self._db_pfad = db_pfad

    async def process(self, message: AgentMessage) -> AgentMessage:
        positionen = message.payload.get("positionen", [])
        stundensatz = float(self._stundensaetze.get("einheitlicher_stundensatz", 58.0))
        cnc_satz = float(self._maschinen.get("holzher_nextec_7707", {}).get("stundensatz_eur", 85.0))
        katalog = PreisKatalog.aus_db(self._db_pfad)

        materialliste: list[dict[str, Any]] = []
        einsaetze: list[dict[str, Any]] = []
        lohn_positionen: list[dict[str, Any]] = []
        montage: list[dict[str, Any]] = []
        stuecklisten: list[dict[str, Any]] = []
        fehlgeschlagen: list[str] = []
        warnungen: list[str] = []
        gewerke = {k: {"stunden": 0.0, "kosten": 0.0} for k in ("konstruktion", "cnc_bedienung", "bankraum", "montage")}

        for pos in positionen:
            nr = str(pos.get("pos_nr", "?"))
            try:
                parameter = parameter_aus_position(pos)
                ergebnis = berechne_korpus(
                    parameter, regeln=self._regeln, maschinen_cfg=self._maschinen, katalog=katalog,
                )
            except ValueError as exc:
                fehlgeschlagen.append(nr)
                warnungen.append(f"Pos {nr}: Korpus-Parameter ungueltig ({exc}) - Standard-Schaetzung verwendet")
                continue

            st = ergebnis["stunden"]
            cnc_h = st.get("CNC", 0.0)
            platten = sum(pl["kosten"] for pl in ergebnis["platten"])
            kanten_material = sum(ka["lfm"] * ka["preis_lfm"] for ka in ergebnis["kanten"])
            kanten_bearbeitung = sum(ka["lfm"] * ka["bearbeitung_lfm"] for ka in ergebnis["kanten"])
            beschlaege = sum(be["kosten"] for be in ergebnis["beschlaege"])
            lohn_stunden = {
                "konstruktion": st.get("Arbeitsvorbereitung", 0.0),
                "cnc_bedienung": cnc_h,
                "bankraum": st.get("Bankraum", 0.0),
                "montage": st.get("Montage", 0.0),
            }
            material = platten + kanten_material + beschlaege
            maschinen = cnc_h * cnc_satz + kanten_bearbeitung
            lohn = sum(lohn_stunden.values()) * stundensatz

            materialliste.append({
                "pos_nr": nr,
                "material": ", ".join(pl["material"] for pl in ergebnis["platten"]),
                "menge": float(pos.get("menge", 0)),
                "teilkosten": (
                    [{"typ": "platte", "beschreibung": f"{pl['material']} {pl['staerke_mm']:g} mm",
                      "menge": pl["brutto_m2"], "einheit": "m2", "einheitspreis": pl["preis_m2"],
                      "kosten": pl["kosten"], "quelle": pl["preis_quelle"]} for pl in ergebnis["platten"]]
                    + [{"typ": "kante", "beschreibung": ka["material"], "menge": ka["lfm"], "einheit": "lfm",
                        "einheitspreis": ka["preis_lfm"], "kosten": round(ka["lfm"] * ka["preis_lfm"], 2),
                        "quelle": ka["preis_quelle"]} for ka in ergebnis["kanten"]]
                    + [{"typ": "beschlag", "beschreibung": be["bezeichnung"], "menge": be["anzahl"], "einheit": "STK",
                        "einheitspreis": be["preis"], "kosten": be["kosten"], "quelle": be["preis_quelle"]}
                       for be in ergebnis["beschlaege"]]
                ),
                "gesamtkosten": round(material, 2),
                "quelle": "korpus",
            })
            einsaetze.append({
                "pos_nr": nr,
                "menge": float(pos.get("menge", 0)),
                "cnc": {"stunden": cnc_h, "kosten": round(cnc_h * cnc_satz, 2),
                        "platten": ergebnis["kennzahlen"]["halbformat_aequivalent"],
                        "stundensatz": cnc_satz, "qualitaetsstufe": parameter.qualitaet, "warnungen": []},
                "kanten": {"stunden": 0.0, "kosten": round(kanten_bearbeitung, 2),
                           "kantenlaenge_lfm": ergebnis["kennzahlen"]["kanten_lfm"]},
                "saege": {"stunden": 0.0, "kosten": 0.0, "schnitte": 0},
                "bohr": {"stunden": 0.0, "kosten": 0.0, "bohrungen": 0},
                "kosten_gesamt": round(maschinen, 2),
                "cnc_stunden": cnc_h,
                "warnungen": [],
                "quelle": "korpus",
            })
            lohn_positionen.append({
                "pos_nr": nr,
                "stunden": round(sum(lohn_stunden.values()), 2),
                "montage_stunden": lohn_stunden["montage"],
                "kosten": lohn,
            })
            for gewerk, h in lohn_stunden.items():
                gewerke[gewerk]["stunden"] += h
                gewerke[gewerk]["kosten"] += h * stundensatz
            if lohn_stunden["montage"] > 0:
                montage.append({"pos_nr": nr, "stunden": lohn_stunden["montage"], "einheiten": parameter.anzahl})
            stuecklisten.append({
                "pos_nr": nr,
                "gegenstand": ergebnis["gegenstand"],
                "teile": ergebnis["teile"],
                "kennzahlen": ergebnis["kennzahlen"],
            })
            warnungen.extend(f"Pos {nr}: {w}" for w in ergebnis["warnungen"])

        return message.create_response(
            sender=self.name,
            payload={
                "materialliste": materialliste,
                "materialkosten_gesamt": round(sum(m["gesamtkosten"] for m in materialliste), 2),
                "maschineneinsaetze": einsaetze,
                "maschinenkosten_gesamt": round(sum(e["kosten_gesamt"] for e in einsaetze), 2),
                "cnc_stunden_total": round(sum(e["cnc_stunden"] for e in einsaetze), 2),
                "lohn_positionen": lohn_positionen,
                "lohnkosten_gesamt": sum(lp["kosten"] for lp in lohn_positionen),
                "gewerke": {k: {"stunden": round(v["stunden"], 2), "kosten": round(v["kosten"], 2)}
                            for k, v in gewerke.items()},
                "montage": montage,
                "stuecklisten": stuecklisten,
                "fehlgeschlagen": fehlgeschlagen,
                "warnungen": warnungen,
            },
        )
