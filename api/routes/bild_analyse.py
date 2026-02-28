"""
API-Routes fuer Bild- und 3D-Analyse.

Ermoeglicht die Preisschaetzung aus Bildern (Claude Vision)
und 3D-Dateien (trimesh Geometrie-Analyse).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

router = APIRouter(prefix="/api/bild-analyse", tags=["BildAnalyse"])

# Referenz auf Pipeline (wird beim Startup gesetzt)
_pipeline: Any = None


def set_pipeline(pipeline: Any) -> None:
    global _pipeline
    _pipeline = pipeline


def _get_agent():
    if not _pipeline:
        raise HTTPException(status_code=503, detail="Pipeline nicht initialisiert")
    agent = _pipeline.subagenten.get("bild_analyse_agent")
    if not agent:
        raise HTTPException(status_code=503, detail="BildAnalyse-Agent nicht verfuegbar")
    return agent


@router.post("/analyse")
async def analyse_datei(
    datei: UploadFile = File(...),
    zusatz_info: str = Form(""),
):
    """Analysiert eine Bild- oder 3D-Datei und erstellt eine Preisschaetzung.

    Unterstuetzte Formate:
    - Bilder: JPG, PNG, WEBP, GIF -> Claude Vision API
    - 3D: STL, OBJ, 3MF, PLY, GLTF/GLB -> trimesh Geometrie
    """
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    file_data = await datei.read()

    if len(file_data) > 50 * 1024 * 1024:  # 50 MB Limit
        raise HTTPException(status_code=413, detail="Datei zu gross (max. 50 MB)")

    msg = AgentMessage(
        sender="api",
        receiver="bild_analyse_agent",
        msg_type="analyse_datei",
        payload={
            "file_data": file_data,
            "dateiname": datei.filename or "upload",
            "zusatz_info": zusatz_info,
        },
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/analyse-3d")
async def analyse_3d(datei: UploadFile = File(...)):
    """Analysiert eine 3D-Datei und gibt Geometriedaten + Kalkulationsvorschlag zurueck."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    file_data = await datei.read()

    msg = AgentMessage(
        sender="api",
        receiver="bild_analyse_agent",
        msg_type="analyse_3d",
        payload={
            "file_data": file_data,
            "dateiname": datei.filename or "model.stl",
        },
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/analyse-bild")
async def analyse_bild(
    datei: UploadFile = File(...),
    zusatz_info: str = Form(""),
):
    """Analysiert ein Bild via Claude Vision API und erstellt Preisschaetzung."""
    from agents.base_agent import AgentMessage

    import os
    ext = os.path.splitext(datei.filename or "")[1].lower()
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    }
    media_type = media_types.get(ext, "image/jpeg")

    agent = _get_agent()
    file_data = await datei.read()

    msg = AgentMessage(
        sender="api",
        receiver="bild_analyse_agent",
        msg_type="analyse_bild",
        payload={
            "image_data": file_data,
            "media_type": media_type,
            "zusatz_info": zusatz_info,
        },
    )
    result = await agent.execute(msg)
    return result.payload
