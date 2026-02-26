"""
MaschinenKalkulator – Subagent 3 (KRITISCH FÜR PRÄZISION).

Berechnet Maschinenkosten und -zeiten:
- Holzher Nextec 7707 (Nesting-CNC) mit NCHops-Integration
- Kantenanleimmaschine
- Formatkreissäge
- Bohrautomat

Kapazitäten und Stundensätze kommen aus config/maschinen.yaml.
"""

from __future__ import annotations

import math
from typing import Any

from agents.base_agent import AgentMessage, BaseAgent


class MaschinenKalkulator(BaseAgent):
    """Berechnet Maschinenzeiten und -kosten für alle Positionen."""

    def __init__(self) -> None:
        super().__init__(name="maschinen_kalkulator")
        self._config: dict[str, Any] = {}

    def load_config(self, config: dict[str, Any]) -> None:
        """Lädt Maschinenkonfiguration aus maschinen.yaml."""
        self._config = config
        self.logger.info("Maschinenkonfiguration geladen: %d Maschinen", len(config))

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Verarbeitet kalkuliere_maschinen-Anfragen.

        Erwartet im Payload:
        - "positionen": Liste der LV-Positionen

        Gibt zurück:
        - "maschineneinsaetze": Detail pro Maschine und Position
        - "maschinenkosten_gesamt": Summe
        - "cnc_schichten": Benötigte CNC-Schichten
        - "zeitplan": Übersicht aller Maschinenzeiten
        - "warnungen": Kapazitätsengpässe etc.
        """
        positionen = message.payload.get("positionen", [])
        projekt_typ = message.payload.get("projekt_typ", "standard")

        einsaetze: list[dict[str, Any]] = []
        warnungen: list[str] = []
        gesamt = 0.0
        cnc_stunden_total = 0.0

        for pos in positionen:
            pos_ergebnis = await self._kalkuliere_position(pos, projekt_typ)
            einsaetze.append(pos_ergebnis)
            gesamt += pos_ergebnis["kosten_gesamt"]
            cnc_stunden_total += pos_ergebnis.get("cnc_stunden", 0)
            warnungen.extend(pos_ergebnis.get("warnungen", []))

        # CNC-Schichten berechnen
        cnc_config = self._config.get("holzher_nextec_7707", {})
        schichtdauer = cnc_config.get("kapazitaet_standard", {}).get(
            "schichtdauer_stunden", 8
        )
        cnc_schichten = math.ceil(cnc_stunden_total / schichtdauer) if schichtdauer else 0

        # CNC-Kapazitaetswarnung: >5 Schichten = Engpass
        if cnc_schichten > 5:
            warnungen.append(
                f"CNC-KAPAZITAET: {cnc_schichten} Schichten benoetigt "
                f"({cnc_stunden_total:.1f}h). Pruefen ob Liefertermin machbar."
            )

        return message.create_response(
            sender=self.name,
            payload={
                "maschineneinsaetze": einsaetze,
                "maschinenkosten_gesamt": round(gesamt, 2),
                "cnc_stunden_total": round(cnc_stunden_total, 2),
                "cnc_schichten": cnc_schichten,
                "zeitplan": self._erstelle_zeitplan(einsaetze),
                "warnungen": warnungen,
            },
        )

    async def _kalkuliere_position(
        self, position: dict, projekt_typ: str
    ) -> dict[str, Any]:
        """Kalkuliert Maschineneinsatz für eine Position.

        Bestimmt pro Position:
        - CNC-Zeit (basierend auf Plattenanzahl + Qualitätsstufe)
        - Kantenzeit (basierend auf Kantenlänge)
        - Sägezeit, Bohrzeit
        """
        pos_nr = position.get("pos_nr", "?")
        menge = position.get("menge", 0)

        cnc = self._berechne_cnc(position, projekt_typ)
        kanten = self._berechne_kanten(position)
        saege = self._berechne_saege(position)
        bohr = self._berechne_bohr(position)

        kosten_gesamt = (
            cnc["kosten"] + kanten["kosten"] + saege["kosten"] + bohr["kosten"]
        )

        warnungen: list[str] = []
        warnungen.extend(cnc.get("warnungen", []))

        return {
            "pos_nr": pos_nr,
            "menge": menge,
            "cnc": cnc,
            "kanten": kanten,
            "saege": saege,
            "bohr": bohr,
            "kosten_gesamt": round(kosten_gesamt, 2),
            "cnc_stunden": cnc.get("stunden", 0),
            "warnungen": warnungen,
        }

    def _berechne_cnc(self, position: dict, projekt_typ: str) -> dict[str, Any]:
        """Berechnet CNC-Zeit und -Kosten für Holzher Nextec 7707.

        Logik:
        - Hochwertige Möbel: 13 Halbformat-Platten / 8h Schicht
        - Standard: 20 Halbformat-Platten / 8h Schicht
        - Rüstzeit pro Auftrag: 30 min (konfigurierbar)

        TODO Phase 2: NCHops-Parser für präzise Programmlaufzeiten.
        """
        cnc_config = self._config.get("holzher_nextec_7707", {})
        stundensatz = cnc_config.get("stundensatz_eur", 85.0)
        ruestzeit_min = cnc_config.get("ruestzeit_min", 30)

        # Qualitätsstufe bestimmt Kapazität
        ist_hochwertig = projekt_typ != "standard"
        if ist_hochwertig:
            kap = cnc_config.get("kapazitaet_hochwertig", {})
        else:
            kap = cnc_config.get("kapazitaet_standard", {})

        platten_pro_schicht = kap.get("halbformat_platten_pro_schicht", 15)
        schichtdauer = kap.get("schichtdauer_stunden", 8)

        # Plattenanzahl aus Position ableiten (vereinfacht)
        platten = position.get("platten_anzahl", position.get("menge", 0))

        if platten_pro_schicht > 0:
            cnc_stunden = (platten / platten_pro_schicht) * schichtdauer
        else:
            cnc_stunden = 0

        # Rüstzeit addieren (einmalig pro Position)
        cnc_stunden += ruestzeit_min / 60

        kosten = cnc_stunden * stundensatz
        warnungen: list[str] = []

        return {
            "stunden": round(cnc_stunden, 2),
            "kosten": round(kosten, 2),
            "platten": platten,
            "stundensatz": stundensatz,
            "qualitaetsstufe": "hochwertig" if ist_hochwertig else "standard",
            "warnungen": warnungen,
        }

    def _berechne_kanten(self, position: dict) -> dict[str, Any]:
        """Berechnet Kantenanleimmaschine-Zeit.

        TODO Phase 2: Kantenlänge aus Bauteil-Geometrie ableiten.
        """
        config = self._config.get("kantenanleimmaschine", {})
        stundensatz = config.get("stundensatz_eur", 45.0)
        kantenlaenge_lfm = position.get("kantenlaenge_lfm", 0)

        # Geschätzt: 10 lfm/Stunde (konfigurierbar)
        geschwindigkeit = config.get("lfm_pro_stunde", 10)
        stunden = kantenlaenge_lfm / geschwindigkeit if geschwindigkeit else 0

        return {
            "stunden": round(stunden, 2),
            "kosten": round(stunden * stundensatz, 2),
            "kantenlaenge_lfm": kantenlaenge_lfm,
        }

    def _berechne_saege(self, position: dict) -> dict[str, Any]:
        """Berechnet Formatkreissäge-Zeit."""
        config = self._config.get("formatkreissaege", {})
        stundensatz = config.get("stundensatz_eur", 35.0)
        schnitte = position.get("schnittanzahl", 0)

        # Geschätzt: 30 Schnitte/Stunde
        geschwindigkeit = config.get("schnitte_pro_stunde", 30)
        stunden = schnitte / geschwindigkeit if geschwindigkeit else 0

        return {
            "stunden": round(stunden, 2),
            "kosten": round(stunden * stundensatz, 2),
            "schnitte": schnitte,
        }

    def _berechne_bohr(self, position: dict) -> dict[str, Any]:
        """Berechnet Bohrautomat-Zeit."""
        config = self._config.get("bohrautomat", {})
        stundensatz = config.get("stundensatz_eur", 30.0)
        bohrungen = position.get("bohrungen_anzahl", 0)

        # Geschätzt: 60 Bohrungen/Stunde
        geschwindigkeit = config.get("bohrungen_pro_stunde", 60)
        stunden = bohrungen / geschwindigkeit if geschwindigkeit else 0

        return {
            "stunden": round(stunden, 2),
            "kosten": round(stunden * stundensatz, 2),
            "bohrungen": bohrungen,
        }

    def _erstelle_zeitplan(self, einsaetze: list[dict]) -> dict[str, float]:
        """Summiert Maschinenzeiten pro Maschinentyp."""
        zeitplan: dict[str, float] = {
            "cnc_stunden": 0,
            "kanten_stunden": 0,
            "saege_stunden": 0,
            "bohr_stunden": 0,
        }
        for e in einsaetze:
            zeitplan["cnc_stunden"] += e.get("cnc", {}).get("stunden", 0)
            zeitplan["kanten_stunden"] += e.get("kanten", {}).get("stunden", 0)
            zeitplan["saege_stunden"] += e.get("saege", {}).get("stunden", 0)
            zeitplan["bohr_stunden"] += e.get("bohr", {}).get("stunden", 0)

        return {k: round(v, 2) for k, v in zeitplan.items()}

    async def parse_nchops(self, nc_datei_pfad: str) -> dict[str, Any]:
        """Parst NCHops-Output von Smartwoop fuer praezise CNC-Zeiten.

        Delegiert an CNCIntegration Agent.
        """
        from agents.cnc_integration import CNCIntegration
        from agents.base_agent import AgentMessage

        cnc = CNCIntegration()

        msg = AgentMessage(
            sender=self.name,
            receiver="cnc_integration",
            msg_type="parse_hop",
            payload={"datei_pfad": nc_datei_pfad},
            projekt_id="DIRECT",
        )
        result = await cnc.execute(msg)
        return result.payload
