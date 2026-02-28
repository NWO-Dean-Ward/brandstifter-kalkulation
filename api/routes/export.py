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


async def _get_kalkulation(projekt_id: str) -> dict:
    """Holt Kalkulationsergebnis aus Cache oder rekonstruiert aus DB."""
    if projekt_id in _kalkulations_cache:
        return _kalkulations_cache[projekt_id]

    # Cache leer (z.B. nach Server-Neustart) -> aus DB rekonstruieren
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        projekt = await cursor.fetchone()
        if not projekt:
            raise HTTPException(
                status_code=404,
                detail=f"Projekt {projekt_id} nicht gefunden.",
            )

        p = dict(projekt)
        if p.get("angebotspreis", 0) == 0 and p.get("status") == "entwurf":
            raise HTTPException(
                status_code=404,
                detail=f"Keine Kalkulation fuer {projekt_id}. "
                       f"Bitte zuerst Kalkulation starten.",
            )

        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        positionen = [dict(r) for r in await cursor.fetchall()]

    # Summen aus Positionsdaten rekonstruieren
    mat_summe = sum(pos.get("materialkosten", 0) for pos in positionen)
    mas_summe = sum(pos.get("maschinenkosten", 0) for pos in positionen)
    loh_summe = sum(pos.get("lohnkosten", 0) for pos in positionen)
    fl_summe = sum(pos.get("fremdleistungskosten", 0) for pos in positionen)
    angebotspreis = p.get("angebotspreis", 0)
    herstellkosten = p.get("herstellkosten", 0)

    kalkulation = {
        "positionen": positionen,
        "projekt_typ": p.get("projekt_typ", "standard"),
        "zuschlaege": {
            "angebotspreis_gesamt": angebotspreis,
            "herstellkosten": herstellkosten,
            "materialkosten": mat_summe,
            "maschinenkosten": mas_summe,
            "lohnkosten": loh_summe,
            "selbstkosten": herstellkosten,  # Approximation
            "gemeinkosten": {"betrag": herstellkosten - mat_summe - mas_summe - loh_summe, "satz": 0},
            "gewinn": {"betrag": 0, "satz": 0},
            "wagnis": {"betrag": 0, "satz": 0},
            "montage_zuschlag": {"betrag": 0},
            "fremdleistungen": {"kosten": fl_summe, "zuschlag": 0},
            "marge": {"prozent": p.get("marge_prozent", 0), "absolut": angebotspreis - herstellkosten},
        },
        "materialkosten": {"materialkosten_gesamt": mat_summe},
        "maschinenkosten": {"maschinenkosten_gesamt": mas_summe},
        "lohnkosten": {"lohnkosten_gesamt": loh_summe},
        "warnungen": ["Hinweis: Detaildaten aus DB rekonstruiert (Server-Neustart). "
                      "Fuer volle Details bitte Kalkulation erneut starten."],
    }

    # In Cache legen fuer naechste Anfrage
    _kalkulations_cache[projekt_id] = kalkulation
    return kalkulation


@router.post("/{projekt_id}/angebot-pdf")
async def export_angebot_pdf(projekt_id: str):
    """Generiert Angebots-PDF."""
    kalk = await _get_kalkulation(projekt_id)
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
    kalk = await _get_kalkulation(projekt_id)
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
    kalk = await _get_kalkulation(projekt_id)
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
    kalk = await _get_kalkulation(projekt_id)
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
    kalk = await _get_kalkulation(projekt_id)
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
