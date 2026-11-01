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

        # Fremdleistungen separat behandeln (Kosten + eigener Aufschlag, ohne GKZ/Gewinn)
        fremdleistungen = material.get("fremdleistungen", [])
        fremdleistungskosten = sum(
            fl.get("geschaetzte_kosten", 0) for fl in fremdleistungen
        )

        # Einzelkosten summieren. materialkosten_gesamt des MaterialKalkulators enthaelt
        # die Fremdleistungen bereits - hier nur das eigene Material, sonst zaehlt eine
        # Lackierung doppelt (einmal mit GKZ/Gewinn, einmal als Fremdleistung).
        if "materialliste" in material:
            materialkosten = sum(m.get("gesamtkosten", 0) for m in material["materialliste"])
        else:
            materialkosten = material.get("materialkosten_gesamt", 0) - fremdleistungskosten
        maschinenkosten = maschinen.get("maschinenkosten_gesamt", 0)
        lohnkosten = lohn.get("lohnkosten_gesamt", 0)

        herstellkosten = materialkosten + maschinenkosten + lohnkosten

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
        fremdmontage_kosten = 0.0
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
                "positionen_preise": self._positionspreise(
                    material, maschinen, lohn,
                    gkz_satz=gkz_satz, gewinn_satz=gewinn_satz, wagnis_satz=wagnis_satz,
                    montage_satz=montage_satz if montage_basis > 0 else 0.0,
                    fl_saetze={"lackierung": fl_lack_satz, "montage": fl_montage_satz},
                    fremdmontage_kosten=fremdmontage_kosten,
                ),
            },
        )

    @staticmethod
    def _positionspreise(
        material: dict, maschinen: dict, lohn: dict, *,
        gkz_satz: float, gewinn_satz: float, wagnis_satz: float, montage_satz: float,
        fl_saetze: dict[str, float], fremdmontage_kosten: float,
    ) -> list[dict[str, Any]]:
        """Angebotspreis je Position nach denselben Regeln wie der Gesamtpreis.

        Jede Position traegt ihre eigenen Herstellkosten mit GKZ, Gewinn, Wagnis und
        Montagezuschlag; Fremdleistungen nur ihren eigenen Aufschlag. Fremdmontage
        (projektweit) wird nach Montagestunden verteilt. Die Summe aller Positionen
        entspricht damit dem Angebotspreis gesamt (bis auf Rundung).
        """
        pos: dict[str, dict[str, float]] = {}

        def eintrag(nr: Any) -> dict[str, float]:
            return pos.setdefault(str(nr), {
                "material": 0.0, "maschinen": 0.0, "lohn": 0.0,
                "fremdleistung": 0.0, "fl_zuschlag": 0.0, "montage_stunden": 0.0,
            })

        for m in material.get("materialliste", []):
            eintrag(m.get("pos_nr", "?"))["material"] += m.get("gesamtkosten", 0)
        for fl in material.get("fremdleistungen", []):
            e = eintrag(fl.get("pos_nr", "?"))
            kosten = fl.get("geschaetzte_kosten", 0)
            e["fremdleistung"] += kosten
            e["fl_zuschlag"] += kosten * fl_saetze.get(fl.get("typ", ""), 0.0)
        for m in maschinen.get("maschineneinsaetze", []):
            eintrag(m.get("pos_nr", "?"))["maschinen"] += m.get("kosten_gesamt", 0)
        for lp in lohn.get("positionen", []):
            e = eintrag(lp.get("pos_nr", "?"))
            e["lohn"] += lp.get("kosten", 0)
            e["montage_stunden"] += lp.get("montage_stunden", 0)

        montage_summe = sum(e["montage_stunden"] for e in pos.values())
        hk_summe = sum(e["material"] + e["maschinen"] + e["lohn"] for e in pos.values())
        fl_montage_satz = fl_saetze.get("montage", 0.0)

        ergebnis: list[dict[str, Any]] = []
        for nr, e in pos.items():
            hk = e["material"] + e["maschinen"] + e["lohn"]
            selbstkosten = hk * (1 + gkz_satz)
            if fremdmontage_kosten:
                anteil = (e["montage_stunden"] / montage_summe if montage_summe
                          else hk / hk_summe if hk_summe else 0.0)
            else:
                anteil = 0.0
            fremdmontage = fremdmontage_kosten * anteil
            angebot = (
                selbstkosten * (1 + gewinn_satz + wagnis_satz)
                + e["lohn"] * montage_satz
                + e["fremdleistung"] + e["fl_zuschlag"]
                + fremdmontage * (1 + fl_montage_satz)
            )
            ergebnis.append({
                "pos_nr": nr,
                "materialkosten": round(e["material"], 2),
                "maschinenkosten": round(e["maschinen"], 2),
                "lohnkosten": round(e["lohn"], 2),
                "fremdleistungskosten": round(e["fremdleistung"] + fremdmontage, 2),
                "herstellkosten": round(hk, 2),
                "angebotspreis": angebot,
            })
        return ergebnis

    def _get_gewinn_satz(self, projekt_typ: str) -> float:
        """Gibt den passenden Gewinnaufschlag für den Projekttyp zurück."""
        mapping = {
            "oeffentlich": "gewinnaufschlag_oeffentlich",
            "privat": "gewinnaufschlag_privat",
            "standard": "gewinnaufschlag_standard",
        }
        key = mapping.get(projekt_typ, "gewinnaufschlag_standard")
        return self._config.get(key, 0.20)
