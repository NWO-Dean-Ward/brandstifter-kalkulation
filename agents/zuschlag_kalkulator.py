"""
ZuschlagKalkulator – Subagent 5.

Berechnet alle Zuschläge auf die Herstellkosten:
- Gemeinkosten-Zuschlag (GKZ)
- Gewinnaufschlag (abhängig vom Projekttyp)
- Wagnis & Gewinn (VOB-konform)
- Montage-/Baustellenzuschlag
- Fremdleistungsaufschlag (Lackierung, Fremdmontage)

Konfiguration aus config/zuschlaege.yaml.
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentMessage, BaseAgent


class ZuschlagKalkulator(BaseAgent):
    """Berechnet Zuschläge und ermittelt den Angebotspreis."""

    def __init__(self) -> None:
        super().__init__(name="zuschlag_kalkulator")
        self._config: dict[str, Any] = {}

    def load_config(self, config: dict[str, Any]) -> None:
        """Lädt Zuschlagskonfiguration aus zuschlaege.yaml."""
        self._config = config
        self.logger.info("Zuschlagskonfiguration geladen")

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Verarbeitet kalkuliere_zuschlaege-Anfragen.

        Erwartet im Payload:
        - "materialkosten": Ergebnis vom MaterialKalkulator
        - "maschinenkosten": Ergebnis vom MaschinenKalkulator
        - "lohnkosten": Ergebnis vom LohnKalkulator
        - "projekt_typ": "oeffentlich" | "privat" | "standard"

        Gibt zurück:
        - Herstellkosten
        - Zuschlagstabelle
        - Selbstkosten
        - Angebotspreis
        - Margenübersicht
        """
        material = message.payload.get("materialkosten", {})
        maschinen = message.payload.get("maschinenkosten", {})
        lohn = message.payload.get("lohnkosten", {})
        projekt_typ = message.payload.get("projekt_typ", "standard")

        # Einzelkosten summieren
        materialkosten = material.get("materialkosten_gesamt", 0)
        maschinenkosten = maschinen.get("maschinenkosten_gesamt", 0)
        lohnkosten = lohn.get("lohnkosten_gesamt", 0)

        herstellkosten = materialkosten + maschinenkosten + lohnkosten

        # Fremdleistungen separat behandeln
        fremdleistungen = material.get("fremdleistungen", [])
        fremdleistungskosten = sum(
            fl.get("geschaetzte_kosten", 0) for fl in fremdleistungen
        )

        # Zuschläge berechnen
        gkz_satz = self._config.get("gemeinkosten_gkz", 0.25)
        gkz = herstellkosten * gkz_satz

        selbstkosten = herstellkosten + gkz

        # Gewinnaufschlag nach Projekttyp
        gewinn_satz = self._get_gewinn_satz(projekt_typ)
        gewinn = selbstkosten * gewinn_satz

        # Wagnis (nur bei VOB/öffentlich)
        wagnis_satz = 0.0
        wagnis = 0.0
        if projekt_typ == "oeffentlich":
            wagnis_satz = self._config.get("wagnis_vob", 0.03)
            wagnis = selbstkosten * wagnis_satz

        # Montage-/Baustellenzuschlag
        montage_satz = self._config.get("montage_baustellenzuschlag", 0.12)
        montage_basis = lohn.get("montage_plan", {}).get("gesamt_stunden", 0)
        montage_zuschlag = lohnkosten * montage_satz if montage_basis > 0 else 0

        # Fremdleistungszuschlag
        fl_lack_satz = self._config.get("fremdleistung_lackierung", 0.15)
        fl_montage_satz = self._config.get("fremdleistung_montage", 0.12)

        fremdleistungszuschlag = 0.0
        for fl in fremdleistungen:
            if fl.get("typ") == "lackierung":
                fremdleistungszuschlag += fl.get("geschaetzte_kosten", 0) * fl_lack_satz
            elif fl.get("typ") == "montage":
                fremdleistungszuschlag += fl.get("geschaetzte_kosten", 0) * fl_montage_satz

        # Fremdmontage prüfen
        if lohn.get("montage_plan", {}).get("fremdmontage_empfohlen", False):
            fremdmonteure = lohn["montage_plan"].get("fremdmonteure_anzahl", 0)
            # Geschätzte Fremdmontagekosten (wird manuell angepasst)
            fremdmontage_kosten = fremdmonteure * 8 * 65  # 65€/h Fremdleistung
            fremdleistungskosten += fremdmontage_kosten
            fremdleistungszuschlag += fremdmontage_kosten * fl_montage_satz

        # Angebotspreis
        angebotspreis = (
            selbstkosten
            + gewinn
            + wagnis
            + montage_zuschlag
            + fremdleistungskosten
            + fremdleistungszuschlag
        )

        # Marge berechnen
        marge_absolut = angebotspreis - herstellkosten - fremdleistungskosten
        marge_prozent = (marge_absolut / angebotspreis * 100) if angebotspreis > 0 else 0

        return message.create_response(
            sender=self.name,
            payload={
                "herstellkosten": round(herstellkosten, 2),
                "materialkosten": round(materialkosten, 2),
                "maschinenkosten": round(maschinenkosten, 2),
                "lohnkosten": round(lohnkosten, 2),
                "gemeinkosten": {
                    "satz": gkz_satz,
                    "betrag": round(gkz, 2),
                },
                "selbstkosten": round(selbstkosten, 2),
                "gewinn": {
                    "satz": gewinn_satz,
                    "betrag": round(gewinn, 2),
                },
                "wagnis": {
                    "satz": wagnis_satz,
                    "betrag": round(wagnis, 2),
                },
                "montage_zuschlag": {
                    "satz": montage_satz,
                    "betrag": round(montage_zuschlag, 2),
                },
                "fremdleistungen": {
                    "kosten": round(fremdleistungskosten, 2),
                    "zuschlag": round(fremdleistungszuschlag, 2),
                },
                "angebotspreis_gesamt": round(angebotspreis, 2),
                "marge": {
                    "absolut": round(marge_absolut, 2),
                    "prozent": round(marge_prozent, 1),
                },
                "projekt_typ": projekt_typ,
            },
        )

    def _get_gewinn_satz(self, projekt_typ: str) -> float:
        """Gibt den passenden Gewinnaufschlag für den Projekttyp zurück."""
        mapping = {
            "oeffentlich": "gewinnaufschlag_oeffentlich",
            "privat": "gewinnaufschlag_privat",
            "standard": "gewinnaufschlag_standard",
        }
        key = mapping.get(projekt_typ, "gewinnaufschlag_standard")
        return self._config.get(key, 0.20)
