"""
API-Routes fuer CNC-Integration (SmartWOP/NCHops).

Endpoints fuer HOP/MPR Import, HOP-Export, Stuecklisten und Nesting.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from api.database import get_db

router = APIRouter(prefix="/api/cnc", tags=["CNC"])

# Referenz auf die CNC-Integration (wird von main.py gesetzt)
_cnc_agent: Any = None


def set_cnc_agent(agent: Any) -> None:
    global _cnc_agent
    _cnc_agent = agent


def _check_agent():
    if _cnc_agent is None:
        raise HTTPException(
            status_code=503,
            detail="CNC-Integration nicht initialisiert",
        )


# ------------------------------------------------------------------
# 1. HOP-Datei hochladen und parsen
# ------------------------------------------------------------------

@router.post("/parse/hop")
async def parse_hop(
    datei: UploadFile = File(...),
    projekt_id: str = Form(""),
):
    """Parst eine NC-HOPS .hop Datei und gibt CNC-Parameter zurueck."""
    _check_agent()

    if not datei.filename or not datei.filename.lower().endswith(".hop"):
        raise HTTPException(status_code=400, detail="Nur .hop Dateien erlaubt")

    content = await datei.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Datei zu gross (max. 50 MB)")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".hop") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from agents.base_agent import AgentMessage

        msg = AgentMessage(
            sender="api", receiver="cnc_integration",
            msg_type="parse_hop",
            payload={"datei_pfad": tmp_path},
            projekt_id=projekt_id or "TEMP",
        )
        result = await _cnc_agent.execute(msg)

        if result.payload.get("error"):
            raise HTTPException(status_code=400, detail=result.payload["error"])

        return result.payload
    finally:
        os.unlink(tmp_path)


# ------------------------------------------------------------------
# 2. MPR-Datei hochladen und parsen
# ------------------------------------------------------------------

@router.post("/parse/mpr")
async def parse_mpr(
    datei: UploadFile = File(...),
    projekt_id: str = Form(""),
):
    """Parst eine WoodWOP .mpr Datei und gibt CNC-Parameter zurueck."""
    _check_agent()

    if not datei.filename or not datei.filename.lower().endswith(".mpr"):
        raise HTTPException(status_code=400, detail="Nur .mpr Dateien erlaubt")

    content = await datei.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Datei zu gross (max. 50 MB)")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mpr") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from agents.base_agent import AgentMessage

        msg = AgentMessage(
            sender="api", receiver="cnc_integration",
            msg_type="parse_mpr",
            payload={"datei_pfad": tmp_path},
            projekt_id=projekt_id or "TEMP",
        )
        result = await _cnc_agent.execute(msg)

        if result.payload.get("error"):
            raise HTTPException(status_code=400, detail=result.payload["error"])

        return result.payload
    finally:
        os.unlink(tmp_path)


# ------------------------------------------------------------------
# 3. HOP-Export fuer Projekt
# ------------------------------------------------------------------

@router.post("/{projekt_id}/export/hop")
async def export_hop(projekt_id: str):
    """Generiert .hop Dateien fuer alle Positionen eines Projekts."""
    _check_agent()

    # Positionen aus DB laden
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    if not rows:
        raise HTTPException(status_code=404, detail="Keine Positionen gefunden")

    from agents.base_agent import AgentMessage

    msg = AgentMessage(
        sender="api", receiver="cnc_integration",
        msg_type="export_hop",
        payload={"positionen": rows},
        projekt_id=projekt_id,
    )
    result = await _cnc_agent.execute(msg)

    if result.payload.get("error"):
        raise HTTPException(status_code=500, detail=result.payload["error"])

    return result.payload


# ------------------------------------------------------------------
# 4. Stuecklisten-Export (CSV fuer Smartwoop)
# ------------------------------------------------------------------

@router.post("/{projekt_id}/export/stueckliste")
async def export_stueckliste(projekt_id: str):
    """Exportiert eine Stueckliste als CSV fuer Smartwoop-Import."""
    _check_agent()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    if not rows:
        raise HTTPException(status_code=404, detail="Keine Positionen gefunden")

    from agents.base_agent import AgentMessage

    msg = AgentMessage(
        sender="api", receiver="cnc_integration",
        msg_type="export_stueckliste",
        payload={"positionen": rows},
        projekt_id=projekt_id,
    )
    result = await _cnc_agent.execute(msg)

    if result.payload.get("error"):
        raise HTTPException(status_code=500, detail=result.payload["error"])

    # CSV-Datei als Download zurueckgeben
    csv_pfad = result.payload.get("pfad")
    if csv_pfad and Path(csv_pfad).exists():
        return FileResponse(
            csv_pfad,
            media_type="text/csv",
            filename=result.payload.get("datei", "stueckliste.csv"),
        )

    return result.payload


# ------------------------------------------------------------------
# 5. Nesting-Analyse
# ------------------------------------------------------------------

@router.post("/{projekt_id}/nesting")
async def nesting_analyse(
    projekt_id: str,
    platte_laenge_mm: float | None = None,
    platte_breite_mm: float | None = None,
):
    """Berechnet eine Nesting-Schaetzung (Plattenverbrauch + Verschnitt).

    Plattengroesse wird aus config/maschinen.yaml geladen falls nicht explizit angegeben.
    """
    _check_agent()

    # Defaults aus Config laden falls nicht uebergeben
    from api.config_loader import AppConfig
    try:
        cfg = AppConfig()
        platte_cfg = cfg.maschinen.get("platte_standard", {})
    except Exception:
        platte_cfg = {}

    if platte_laenge_mm is None:
        platte_laenge_mm = platte_cfg.get("laenge_mm", 2800)
    if platte_breite_mm is None:
        platte_breite_mm = platte_cfg.get("breite_mm", 2070)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    if not rows:
        raise HTTPException(status_code=404, detail="Keine Positionen gefunden")

    from agents.base_agent import AgentMessage

    msg = AgentMessage(
        sender="api", receiver="cnc_integration",
        msg_type="nesting_analyse",
        payload={
            "positionen": rows,
            "platte_laenge_mm": platte_laenge_mm,
            "platte_breite_mm": platte_breite_mm,
        },
        projekt_id=projekt_id,
    )
    result = await _cnc_agent.execute(msg)
    return result.payload


# ------------------------------------------------------------------
# 6. CNC-Zeitberechnung aus HOP-Dateien
# ------------------------------------------------------------------

@router.post("/{projekt_id}/zeitberechnung")
async def cnc_zeitberechnung(
    projekt_id: str,
    stundensatz: float = 85.0,
):
    """Berechnet praezise CNC-Zeiten aus vorhandenen HOP-Dateien."""
    _check_agent()

    # HOP-Dateien im CNC-Verzeichnis suchen
    cnc_dir = Path("exports/cnc")
    hop_dateien = []

    if cnc_dir.exists():
        for hop_file in cnc_dir.glob(f"{projekt_id}_*.hop"):
            hop_dateien.append({
                "datei_pfad": str(hop_file),
                "menge": 1,
            })

    if not hop_dateien:
        raise HTTPException(
            status_code=404,
            detail="Keine HOP-Dateien gefunden. Bitte zuerst HOP-Export ausfuehren.",
        )

    from agents.base_agent import AgentMessage

    msg = AgentMessage(
        sender="api", receiver="cnc_integration",
        msg_type="cnc_zeitberechnung",
        payload={
            "hop_dateien": hop_dateien,
            "stundensatz": stundensatz,
        },
        projekt_id=projekt_id,
    )
    result = await _cnc_agent.execute(msg)
    return result.payload
