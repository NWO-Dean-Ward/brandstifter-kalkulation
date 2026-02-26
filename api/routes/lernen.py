"""
API-Routes fuer den Lern-Agent (Memory Layer).

Ermoeglicht Zugriff auf historische Daten, Vorschlaege und Abweichungsanalyse.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agents.base_agent import AgentMessage

router = APIRouter(prefix="/api/lernen", tags=["Lernen"])

# Referenz auf Pipeline
_pipeline: Any = None


def set_pipeline(pipeline: Any) -> None:
    global _pipeline
    _pipeline = pipeline


def _get_lern_agent():
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline nicht initialisiert")
    agent = _pipeline.subagenten.get("lern_agent")
    if agent is None:
        raise HTTPException(status_code=503, detail="Lern-Agent nicht verfuegbar")
    return agent


@router.post("/{projekt_id}/speichern")
async def projekt_speichern(projekt_id: str, data: dict[str, Any]):
    """Speichert ein abgeschlossenes Projekt in der Lernhistorie.

    Body: {"positionen": [...], "zuschlaege": {...}, "ergebnis": "gewonnen|verloren|beauftragt"}
    """
    agent = _get_lern_agent()
    msg = AgentMessage(
        sender="api", receiver="lern_agent",
        msg_type="projekt_speichern",
        payload=data,
        projekt_id=projekt_id,
    )
    result = await agent.execute(msg)
    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Fehler"))
    return result.payload


@router.post("/{projekt_id}/plausibilitaet")
async def plausibilitaets_check(projekt_id: str, data: dict[str, Any]):
    """Prueft eine Kalkulation gegen historische Daten.

    Body: {"positionen": [...], "kalkulation": {...}}
    """
    agent = _get_lern_agent()
    msg = AgentMessage(
        sender="api", receiver="lern_agent",
        msg_type="plausibilitaets_check",
        payload=data,
        projekt_id=projekt_id,
    )
    result = await agent.execute(msg)
    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Fehler"))
    return result.payload


@router.post("/vorschlag")
async def preisvorschlag(data: dict[str, Any]):
    """Gibt Preisvorschlaege basierend auf aehnlichen Altprojekten.

    Body: {"kurztext": "...", "material": "...", "menge": 1}
    """
    agent = _get_lern_agent()
    msg = AgentMessage(
        sender="api", receiver="lern_agent",
        msg_type="vorschlag",
        payload=data,
        projekt_id="",
    )
    result = await agent.execute(msg)
    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Fehler"))
    return result.payload


@router.get("/statistik")
async def lernstatistik():
    """Gibt eine Zusammenfassung der gesamten Lernhistorie."""
    agent = _get_lern_agent()
    msg = AgentMessage(
        sender="api", receiver="lern_agent",
        msg_type="statistik",
        payload={},
        projekt_id="",
    )
    result = await agent.execute(msg)
    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Fehler"))
    return result.payload


@router.get("/abweichungen")
async def abweichungsanalyse(limit: int = 10):
    """Zeigt Top-Abweichungen zwischen Kalkulation und Ist-Werten."""
    agent = _get_lern_agent()
    msg = AgentMessage(
        sender="api", receiver="lern_agent",
        msg_type="abweichungsanalyse",
        payload={"limit": limit},
        projekt_id="",
    )
    result = await agent.execute(msg)
    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Fehler"))
    return result.payload


@router.post("/{projekt_id}/ist-werte")
async def ist_werte_eintragen(projekt_id: str, data: dict[str, Any]):
    """Traegt tatsaechliche Werte nach Projektabschluss ein.

    Body: {"ist_werte": [{"id": 1, "tatsaechlicher_preis": 500.0}], "ergebnis": "gewonnen"}
    """
    agent = _get_lern_agent()
    msg = AgentMessage(
        sender="api", receiver="lern_agent",
        msg_type="ist_werte_eintragen",
        payload=data,
        projekt_id=projekt_id,
    )
    result = await agent.execute(msg)
    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Fehler"))
    return result.payload
