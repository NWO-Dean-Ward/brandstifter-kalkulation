"""
API-Routes fuer Exports.

Generiert PDFs, Excel, GAEB aus abgeschlossenen Kalkulationen.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.database import get_db

router = APIRouter(prefix="/api/export", tags=["Export"])

# Referenz auf Pipeline + letztes Kalkulationsergebnis
_pipeline: Any = None
_kalkulations_cache: dict[str, dict] = {}


def set_pipeline(pipeline: Any) -> None:
    global _pipeline
    _pipeline = pipeline


def cache_kalkulation(projekt_id: str, ergebnis: dict) -> None:
    """Speichert Kalkulationsergebnis fuer spaetere Exports."""
    _kalkulations_cache[projekt_id] = ergebnis


def _get_kalkulation(projekt_id: str) -> dict:
    if projekt_id not in _kalkulations_cache:
        raise HTTPException(
            status_code=404,
            detail=f"Keine Kalkulation fuer {projekt_id} im Cache. "
                   f"Bitte zuerst Kalkulation starten.",
        )
    return _kalkulations_cache[projekt_id]


@router.post("/{projekt_id}/angebot-pdf")
async def export_angebot_pdf(projekt_id: str):
    """Generiert Angebots-PDF."""
    kalk = _get_kalkulation(projekt_id)
    export = _pipeline.subagenten.get("export_agent")
    if not export:
        raise HTTPException(status_code=503, detail="Export-Agent nicht verfuegbar")

    result = await export._export_angebot_pdf(kalk, projekt_id)
    if result.get("status") == "ok":
        return FileResponse(
            result["datei"],
            media_type="application/pdf",
            filename=result["dateiname"],
        )
    raise HTTPException(status_code=500, detail=result.get("message", "Export fehlgeschlagen"))


@router.post("/{projekt_id}/intern-pdf")
async def export_intern_pdf(projekt_id: str):
    """Generiert interne Kalkulations-PDF."""
    kalk = _get_kalkulation(projekt_id)
    export = _pipeline.subagenten.get("export_agent")
    if not export:
        raise HTTPException(status_code=503, detail="Export-Agent nicht verfuegbar")

    result = await export._export_intern_pdf(kalk, projekt_id)
    if result.get("status") == "ok":
        return FileResponse(
            result["datei"],
            media_type="application/pdf",
            filename=result["dateiname"],
        )
    raise HTTPException(status_code=500, detail=result.get("message", "Export fehlgeschlagen"))


@router.post("/{projekt_id}/excel")
async def export_excel(projekt_id: str):
    """Generiert Excel-Export."""
    kalk = _get_kalkulation(projekt_id)
    export = _pipeline.subagenten.get("export_agent")
    if not export:
        raise HTTPException(status_code=503, detail="Export-Agent nicht verfuegbar")

    result = await export._export_excel(kalk, projekt_id)
    if result.get("status") == "ok":
        return FileResponse(
            result["datei"],
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=result["dateiname"],
        )
    raise HTTPException(status_code=500, detail=result.get("message", "Export fehlgeschlagen"))


@router.post("/{projekt_id}/gaeb")
async def export_gaeb(projekt_id: str):
    """Generiert GAEB-X83 Export."""
    kalk = _get_kalkulation(projekt_id)
    export = _pipeline.subagenten.get("export_agent")
    if not export:
        raise HTTPException(status_code=503, detail="Export-Agent nicht verfuegbar")

    result = await export._export_gaeb(kalk, projekt_id)
    if result.get("status") == "ok":
        return FileResponse(
            result["datei"],
            media_type="application/xml",
            filename=result["dateiname"],
        )
    raise HTTPException(status_code=500, detail=result.get("message", "Export fehlgeschlagen"))


@router.post("/{projekt_id}/alle")
async def export_alle(projekt_id: str):
    """Generiert alle Export-Formate auf einmal."""
    kalk = _get_kalkulation(projekt_id)
    export = _pipeline.subagenten.get("export_agent")
    if not export:
        raise HTTPException(status_code=503, detail="Export-Agent nicht verfuegbar")

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="export_agent",
        msg_type="export_alle",
        payload={"kalkulation": kalk},
        projekt_id=projekt_id,
    )
    result = await export.execute(msg)
    return result.payload
