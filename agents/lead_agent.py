"""
LeadAgent -- Kalkulations-Orchestrator.

Koordiniert den gesamten Kalkulationsworkflow:
1. Empfaengt Ausschreibungsdokumente / Anfragen / direkte Positionen
2. Delegiert an Subagenten (Parser -> Material -> Maschinen -> Lohn -> Zuschlag)
3. Fuehrt Teilergebnisse zusammen
4. Plausibilitaetspruefung
5. Uebergabe an Export-Agent
6. Nach Projektabschluss: Feedback an Lern-Agent
"""

from __future__ import annotations

import asyncio
from typing import Any

from agents.base_agent import AgentMessage, AgentStatus, BaseAgent


class LeadAgent(BaseAgent):
    """Orchestriert die Kalkulations-Pipeline."""

    def __init__(self) -> None:
        super().__init__(name="lead_agent")
        self.subagenten: dict[str, BaseAgent] = {}
        self.aktives_projekt: dict[str, Any] | None = None

    def register_subagent(self, agent: BaseAgent) -> None:
        """Registriert einen Subagenten beim Orchestrator."""
        self.subagenten[agent.name] = agent
        self.logger.info("Subagent registriert: %s", agent.name)

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Hauptlogik: Steuert den Kalkulations-Workflow.

        Erwartete msg_types:
        - "neue_ausschreibung": Startet GAEB/VOB-Workflow (mit Dokument-Parser)
        - "neue_anfrage": Startet Schnellkalkulations-Workflow
        - "kalkuliere_positionen": Direkte Kalkulation aus DB-Positionen
        - "projekt_abschluss": Triggert Lern-Agent
        """
        msg_type = message.msg_type

        if msg_type == "neue_ausschreibung":
            return await self._workflow_ausschreibung(message)
        elif msg_type == "neue_anfrage":
            return await self._workflow_schnellkalkulation(message)
        elif msg_type == "kalkuliere_positionen":
            return await self._workflow_direkt(message)
        elif msg_type == "projekt_abschluss":
            return await self._workflow_abschluss(message)
        else:
            return message.create_error(
                sender=self.name,
                error_msg=f"Unbekannter Nachrichtentyp: {msg_type}",
            )

    # ------------------------------------------------------------------
    # Kern-Kalkulations-Pipeline (wird von allen Workflows genutzt)
    # ------------------------------------------------------------------

    async def _kalkuliere(
        self, positionen: list[dict], projekt_typ: str, projekt_id: str,
        original_message: AgentMessage,
    ) -> AgentMessage:
        """Fuehrt die Kalkulations-Pipeline aus: Material + Maschinen + Lohn -> Zuschlag."""

        kalk_payload = {
            "positionen": positionen,
            "projekt_typ": projekt_typ,
        }

        # Parallel: Material, Maschinen, Lohn
        material_req = AgentMessage(
            sender=self.name, receiver="material_kalkulator",
            msg_type="kalkuliere_material", payload=kalk_payload,
            projekt_id=projekt_id,
        )
        maschinen_req = AgentMessage(
            sender=self.name, receiver="maschinen_kalkulator",
            msg_type="kalkuliere_maschinen", payload=kalk_payload,
            projekt_id=projekt_id,
        )
        lohn_req = AgentMessage(
            sender=self.name, receiver="lohn_kalkulator",
            msg_type="kalkuliere_lohn", payload=kalk_payload,
            projekt_id=projekt_id,
        )

        material_res, maschinen_res, lohn_res = await asyncio.gather(
            self._delegate("material_kalkulator", material_req),
            self._delegate("maschinen_kalkulator", maschinen_req),
            self._delegate("lohn_kalkulator", lohn_req),
        )

        # Fehlerpruefung
        for res in [material_res, maschinen_res, lohn_res]:
            if res.msg_type == "error":
                return res

        # Zuschlaege berechnen
        zuschlag_req = AgentMessage(
            sender=self.name, receiver="zuschlag_kalkulator",
            msg_type="kalkuliere_zuschlaege",
            payload={
                "materialkosten": material_res.payload,
                "maschinenkosten": maschinen_res.payload,
                "lohnkosten": lohn_res.payload,
                "projekt_typ": projekt_typ,
            },
            projekt_id=projekt_id,
        )
        zuschlag_res = await self._delegate("zuschlag_kalkulator", zuschlag_req)
        if zuschlag_res.msg_type == "error":
            return zuschlag_res

        # Plausibilitaets-Check (Lern-Agent)
        warnungen = await self._plausibilitaets_check(
            positionen, zuschlag_res.payload, projekt_id
        )

        # Warnungen aus Subagenten sammeln
        for res in [material_res, maschinen_res, lohn_res]:
            warnungen.extend(res.payload.get("warnungen", []))

        # Gesamtergebnis
        gesamtergebnis = {
            "projekt_id": projekt_id,
            "projekt_typ": projekt_typ,
            "positionen": positionen,
            "materialkosten": material_res.payload,
            "maschinenkosten": maschinen_res.payload,
            "lohnkosten": lohn_res.payload,
            "zuschlaege": zuschlag_res.payload,
            "gesamtpreis": zuschlag_res.payload.get("angebotspreis_gesamt", 0),
            "warnungen": warnungen,
        }

        self.aktives_projekt = gesamtergebnis

        return original_message.create_response(
            sender=self.name,
            payload=gesamtergebnis,
            msg_type="kalkulation_ergebnis",
        )

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    async def _workflow_ausschreibung(self, message: AgentMessage) -> AgentMessage:
        """Vollstaendiger Ausschreibungs-Workflow (GAEB/VOB).

        1. Dokument parsen -> LV-Positionen
        2. Kalkulations-Pipeline
        """
        projekt_id = message.projekt_id

        # Schritt 1: Dokument parsen
        parse_request = AgentMessage(
            sender=self.name,
            receiver="dokument_parser",
            msg_type="parse_dokument",
            payload=message.payload,
            projekt_id=projekt_id,
        )
        parse_result = await self._delegate("dokument_parser", parse_request)
        if parse_result.msg_type == "error":
            return parse_result

        positionen = parse_result.payload.get("positionen", [])
        projekt_typ = parse_result.payload.get("projekt_typ", "standard")

        # Schritt 2: Kalkulieren
        return await self._kalkuliere(positionen, projekt_typ, projekt_id, message)

    async def _workflow_schnellkalkulation(self, message: AgentMessage) -> AgentMessage:
        """Schnellkalkulation: Positionen kommen direkt."""
        positionen = message.payload.get("positionen", [])
        projekt_typ = message.payload.get("projekt_typ", "privat")
        return await self._kalkuliere(positionen, projekt_typ, message.projekt_id, message)

    async def _workflow_direkt(self, message: AgentMessage) -> AgentMessage:
        """Direkte Kalkulation: Positionen aus der DB, kein Parsing noetig."""
        positionen = message.payload.get("positionen", [])
        projekt_typ = message.payload.get("projekt_typ", "standard")

        # DB-Positionen normalisieren (int -> bool, fehlende Felder auffuellen)
        normalisiert = []
        for pos in positionen:
            normalisiert.append({
                "pos_nr": pos.get("pos_nr", "?"),
                "kurztext": pos.get("kurztext", ""),
                "langtext": pos.get("langtext", ""),
                "menge": float(pos.get("menge", 0)),
                "einheit": pos.get("einheit", "STK"),
                "material": pos.get("material", ""),
                "ist_lackierung": bool(pos.get("ist_lackierung", False)),
                "ist_fremdleistung": bool(pos.get("ist_fremdleistung", False)),
                "platten_anzahl": float(pos.get("platten_anzahl", 0)),
                "kantenlaenge_lfm": float(pos.get("kantenlaenge_lfm", 0)),
                "schnittanzahl": int(pos.get("schnittanzahl", 0)),
                "bohrungen_anzahl": int(pos.get("bohrungen_anzahl", 0)),
            })

        return await self._kalkuliere(normalisiert, projekt_typ, message.projekt_id, message)

    async def _workflow_abschluss(self, message: AgentMessage) -> AgentMessage:
        """Projekt als abgeschlossen markieren -> Lern-Agent fuettern."""
        if "lern_agent" in self.subagenten:
            lern_req = AgentMessage(
                sender=self.name, receiver="lern_agent",
                msg_type="projekt_speichern",
                payload=message.payload,
                projekt_id=message.projekt_id,
            )
            await self._delegate("lern_agent", lern_req)

        return message.create_response(
            sender=self.name,
            payload={"status": "projekt_abgeschlossen"},
        )

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    async def _delegate(self, agent_name: str, message: AgentMessage) -> AgentMessage:
        """Delegiert eine Nachricht an einen registrierten Subagenten."""
        agent = self.subagenten.get(agent_name)
        if agent is None:
            return message.create_error(
                sender=self.name,
                error_msg=f"Subagent nicht registriert: {agent_name}",
            )
        return await agent.execute(message)

    async def _plausibilitaets_check(
        self, positionen: list, zuschlag_ergebnis: dict, projekt_id: str
    ) -> list[str]:
        """Prueft Kalkulation gegen historische Daten (via Lern-Agent)."""
        warnungen: list[str] = []

        if "lern_agent" not in self.subagenten:
            return warnungen

        check_req = AgentMessage(
            sender=self.name, receiver="lern_agent",
            msg_type="plausibilitaets_check",
            payload={
                "positionen": positionen,
                "kalkulation": zuschlag_ergebnis,
            },
            projekt_id=projekt_id,
        )
        check_res = await self._delegate("lern_agent", check_req)
        if check_res.msg_type == "response":
            warnungen = check_res.payload.get("warnungen", [])

        return warnungen
