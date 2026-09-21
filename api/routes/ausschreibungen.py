"""
API-Routes fuer das Ausschreibungs-Monitoring.

Durchsucht HAD (Hessische Ausschreibungsdatenbank) und TED (EU) nach
Bekanntmachungen, die zum Leistungsprofil passen, und legt sie bewertet ab.

Der Agent bewirbt sich NIEMALS automatisch auf eine Ausschreibung -
er recherchiert, bewertet und legt vor. Die Auswahl trifft Dean.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/ausschreibungen", tags=["Ausschreibungen"])

_pipeline: Any = None


def set_pipeline(pipeline: Any) -> None:
    global _pipeline
    _pipeline = pipeline


def _get_agent():
    if not _pipeline:
        raise HTTPException(status_code=503, detail="Pipeline nicht initialisiert")
    agent = _pipeline.subagenten.get("ausschreibungs_agent")
    if not agent:
        raise HTTPException(status_code=503, detail="Ausschreibungs-Agent nicht verfuegbar")
    return agent


async def _sende(msg_type: str, payload: dict) -> dict:
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="ausschreibungs_agent",
        msg_type=msg_type, payload=payload,
    )
    result = await agent.execute(msg)
    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Agent-Fehler"))
    return result.payload


@router.post("/scan")
async def scan(quellen: str = "had,ted", zeitraum_tage: int = 0):
    """Durchsucht HAD und TED nach passenden Bekanntmachungen.

    Laeuft je nach Trefferzahl einige Sekunden. Bereits bekannte Eintraege
    werden aktualisiert, ein gesetzter Bearbeitungsstatus bleibt erhalten.
    """
    payload: dict[str, Any] = {
        "quellen": [q.strip() for q in quellen.split(",") if q.strip()],
    }
    if zeitraum_tage > 0:
        payload["zeitraum_tage"] = zeitraum_tage
    return await _sende("scan", payload)


@router.get("/")
async def liste(min_score: int = 0, status: str = "", limit: int = 100):
    """Listet gespeicherte Ausschreibungen, absteigend nach Relevanz."""
    return await _sende("liste", {"min_score": min_score, "status": status, "limit": limit})


@router.patch("/{ausschreibung_id}/status")
async def status_setzen(ausschreibung_id: int, status: str, notiz: str = ""):
    """Setzt den Bearbeitungsstatus.

    Erlaubt: neu, relevant, verworfen, beworben, gewonnen, verloren.
    Verwerfen erfordert eine Begruendung - sonst laesst sich spaeter nicht
    mehr nachvollziehen, warum ein Auftrag nicht verfolgt wurde.
    """
    ergebnis = await _sende("status_setzen", {
        "id": ausschreibung_id, "status": status, "notiz": notiz,
    })
    if ergebnis.get("status") == "fehler":
        raise HTTPException(status_code=400, detail=ergebnis.get("fehler", "Ungueltige Anfrage"))
    return ergebnis


@router.get("/briefing")
async def briefing(min_score: int = 0, limit: int = 15):
    """Erzeugt den Briefing-Text fuer den Versand an Dean.

    Liefert nur Eintraege mit Status 'neu' - was einmal bewertet wurde,
    taucht nicht erneut auf.
    """
    payload: dict[str, Any] = {"limit": limit}
    if min_score > 0:
        payload["min_score"] = min_score
    return await _sende("briefing", payload)
