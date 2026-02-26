"""
LohnKalkulator – Subagent 4.

Berechnet Lohnkosten pro Gewerk:
- Konstruktion / Programmierung
- CNC-Bedienung
- Kantenbeschichtung
- Montage (inkl. Monteureplanung)
- Zwischentransport

Montage-Logik:
- 7 Monteure verfuegbar
- Standard 4-6 Stunden pro Einheit
- Warnung bei >7 Monteuren noetig -> Fremdmontage-Option
"""

from __future__ import annotations

import math
from typing import Any

from agents.base_agent import AgentMessage, BaseAgent


class LohnKalkulator(BaseAgent):
    """Berechnet Lohnkosten fuer alle Gewerke eines Projekts."""

    def __init__(self) -> None:
        super().__init__(name="lohn_kalkulator")
        self._config: dict[str, Any] = {}

    def load_config(self, config: dict[str, Any]) -> None:
        """Laedt Stundensatz-Konfiguration aus stundensaetze.yaml."""
        self._config = config
        self.logger.info("Stundensaetze geladen")

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Verarbeitet kalkuliere_lohn-Anfragen."""
        positionen = message.payload.get("positionen", [])
        stundensatz = float(self._config.get("einheitlicher_stundensatz", 58.0))
        monteure_verfuegbar = int(self._config.get("monteure_anzahl", 7))
        montage_config = self._config.get("montage_stunden_pro_einheit", {})
        montage_std_pro_einheit = float(montage_config.get("standard", 5))

        gewerke = {
            "konstruktion": {"stunden": 0.0, "kosten": 0.0},
            "cnc_bedienung": {"stunden": 0.0, "kosten": 0.0},
            "kantenbeschichtung": {"stunden": 0.0, "kosten": 0.0},
            "montage": {"stunden": 0.0, "kosten": 0.0},
            "transport": {"stunden": 0.0, "kosten": 0.0},
        }
        warnungen: list[str] = []
        montage_einheiten_total = 0.0
        hat_montage = False

        for pos in positionen:
            menge = float(pos.get("menge", 0))
            platten = float(pos.get("platten_anzahl", 0))
            kanten_lfm = float(pos.get("kantenlaenge_lfm", 0))
            bohrungen = int(pos.get("bohrungen_anzahl", 0))

            # Konstruktion/Programmierung:
            # - Basis: 1.5h pro Position (Zeichnung, CAD, Smartwoop)
            # - Zusaetzlich 0.25h pro Platte (CNC-Programmierung)
            konstr_stunden = 1.5 + (platten * 0.25)
            gewerke["konstruktion"]["stunden"] += konstr_stunden

            # CNC-Bedienung:
            # - Abgeleitet von Plattenanzahl (Maschine beladen, ueberwachen)
            # - Ca. 0.3h pro Platte (beladen + entladen + pruefen)
            cnc_stunden = platten * 0.3 if platten > 0 else menge * 0.2
            gewerke["cnc_bedienung"]["stunden"] += cnc_stunden

            # Kantenbeschichtung:
            # - Abgeleitet von Kantenlaenge
            # - Ca. 6 lfm pro Stunde (einlegen, pruefen, nacharbeiten)
            kanten_stunden = kanten_lfm / 6.0 if kanten_lfm > 0 else menge * 0.15
            gewerke["kantenbeschichtung"]["stunden"] += kanten_stunden

            # Montage:
            # - Standard: konfigurierbar, 4-6 Stunden pro Einheit
            # - Nur fuer Einheiten die montiert werden (STK, PAU)
            montage_stunden = menge * montage_std_pro_einheit
            gewerke["montage"]["stunden"] += montage_stunden
            montage_einheiten_total += menge
            if montage_stunden > 0:
                hat_montage = True

        # Transport:
        # - Pauschal basierend auf Gesamtmenge
        # - Beladung Werkstatt + Entladung Baustelle + Rueckfahrt
        if hat_montage:
            transport_basis = 3.0  # Grundzeit: Laden, Fahren, Entladen
            transport_zusatz = montage_einheiten_total * 0.3  # pro Einheit: Handling
            gewerke["transport"]["stunden"] = transport_basis + transport_zusatz

        # Kosten berechnen
        lohnkosten_gesamt = 0.0
        for gewerk_data in gewerke.values():
            gewerk_data["stunden"] = round(gewerk_data["stunden"], 2)
            gewerk_data["kosten"] = round(gewerk_data["stunden"] * stundensatz, 2)
            lohnkosten_gesamt += gewerk_data["kosten"]

        # Montageplanung
        montage_gesamt_stunden = gewerke["montage"]["stunden"]
        monteure_benoetigt = self._berechne_monteure(montage_gesamt_stunden)

        montage_plan: dict[str, Any] = {
            "gesamt_stunden": montage_gesamt_stunden,
            "einheiten_total": montage_einheiten_total,
            "stunden_pro_einheit": montage_std_pro_einheit,
            "monteure_benoetigt": monteure_benoetigt,
            "monteure_verfuegbar": monteure_verfuegbar,
            "tage_geschaetzt": math.ceil(
                montage_gesamt_stunden / (min(monteure_benoetigt, monteure_verfuegbar) * 8)
            ) if monteure_benoetigt > 0 else 0,
            "fremdmontage_empfohlen": False,
        }

        # Warnung bei Kapazitaetsengpass
        if monteure_benoetigt > monteure_verfuegbar:
            fremd_anzahl = monteure_benoetigt - monteure_verfuegbar
            warnungen.append(
                f"KAPAZITAETSENGPASS MONTAGE: {monteure_benoetigt} Monteure benoetigt, "
                f"nur {monteure_verfuegbar} verfuegbar. "
                f"Fremdmontage empfohlen fuer {fremd_anzahl} zusaetzliche Monteure."
            )
            montage_plan["fremdmontage_empfohlen"] = True
            montage_plan["fremdmonteure_anzahl"] = fremd_anzahl

        return message.create_response(
            sender=self.name,
            payload={
                "gewerke": gewerke,
                "lohnkosten_gesamt": round(lohnkosten_gesamt, 2),
                "stundensatz": stundensatz,
                "montage_plan": montage_plan,
                "warnungen": warnungen,
            },
        )

    def _berechne_monteure(self, montage_stunden: float) -> int:
        """Berechnet die benoetigte Anzahl Monteure.

        Logik: Montage soll innerhalb einer Woche (5 Tage = 40h) abgeschlossen sein.
        Wenn >40h -> mehrere Monteure parallel noetig.
        """
        if montage_stunden <= 0:
            return 0
        # Pro Monteur: 40h/Woche verfuegbar
        return max(1, math.ceil(montage_stunden / 40))
