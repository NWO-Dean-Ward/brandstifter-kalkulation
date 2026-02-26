"""
API-Routes fuer Schreiner's Buero ERP-Anbindung.

Bidirektionale Synchronisation: Auftraege, Stuecklisten, Kunden, Preise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from api.database import get_db

router = APIRouter(prefix="/api/sb", tags=["Schreiner's Buero"])

_sb_agent: Any = None


def set_sb_agent(agent: Any) -> None:
    global _sb_agent
    _sb_agent = agent


def _check_agent():
    if _sb_agent is None:
        raise HTTPException(
            status_code=503,
            detail="Schreiner's Buero Agent nicht initialisiert",
        )


# ------------------------------------------------------------------
# 1. Verbindungstest
# ------------------------------------------------------------------

@router.get("/status")
async def sb_status():
    """Testet die Verbindung zum SB-Server und zeigt Konfiguration."""
    _check_agent()

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="schreiners_buero",
        msg_type="sb_verbindungstest",
        payload={},
        projekt_id="SYSTEM",
    )
    result = await _sb_agent.execute(msg)
    return result.payload


# ------------------------------------------------------------------
# 2. Auftrag an SB senden
# ------------------------------------------------------------------

@router.post("/{projekt_id}/auftrag")
async def sb_auftrag_senden(projekt_id: str):
    """Sendet ein kalkuliertes Projekt als Auftrag an SB.

    Laedt Projekt und Positionen aus der DB und uebertraegt sie.
    Falls SB offline: automatischer CSV-Fallback.
    """
    _check_agent()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        projekt = await cursor.fetchone()
        if not projekt:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        positionen = [dict(r) for r in await cursor.fetchall()]

    if not positionen:
        raise HTTPException(status_code=400, detail="Keine Positionen vorhanden")

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="schreiners_buero",
        msg_type="sb_auftrag_anlegen",
        payload={
            "projekt": dict(projekt),
            "positionen": positionen,
        },
        projekt_id=projekt_id,
    )
    result = await _sb_agent.execute(msg)
    return result.payload


# ------------------------------------------------------------------
# 3. Auftragsstatus aus SB abfragen
# ------------------------------------------------------------------

@router.get("/{projekt_id}/status")
async def sb_auftrag_status(projekt_id: str):
    """Fragt den Auftragsstatus in SB ab."""
    _check_agent()

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="schreiners_buero",
        msg_type="sb_auftrag_status",
        payload={},
        projekt_id=projekt_id,
    )
    result = await _sb_agent.execute(msg)
    return result.payload


# ------------------------------------------------------------------
# 4. Stueckliste an SB senden
# ------------------------------------------------------------------

@router.post("/{projekt_id}/stueckliste")
async def sb_stueckliste_senden(projekt_id: str):
    """Sendet die Stueckliste eines Projekts an SB."""
    _check_agent()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        positionen = [dict(r) for r in await cursor.fetchall()]

    if not positionen:
        raise HTTPException(status_code=400, detail="Keine Positionen vorhanden")

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="schreiners_buero",
        msg_type="sb_stueckliste_senden",
        payload={"positionen": positionen},
        projekt_id=projekt_id,
    )
    result = await _sb_agent.execute(msg)
    return result.payload


# ------------------------------------------------------------------
# 5. Kunde synchronisieren
# ------------------------------------------------------------------

@router.post("/{projekt_id}/kunde")
async def sb_kunde_sync(projekt_id: str):
    """Synchronisiert den Kunden eines Projekts mit SB."""
    _check_agent()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT kunde FROM projekte WHERE id = ?", (projekt_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    kunde_name = dict(row).get("kunde", "")
    if not kunde_name:
        raise HTTPException(status_code=400, detail="Kein Kunde im Projekt hinterlegt")

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="schreiners_buero",
        msg_type="sb_kunde_sync",
        payload={"kunde_name": kunde_name},
        projekt_id=projekt_id,
    )
    result = await _sb_agent.execute(msg)
    return result.payload


# ------------------------------------------------------------------
# 6. Materialpreise aus SB importieren
# ------------------------------------------------------------------

@router.post("/materialpreise/import")
async def sb_materialpreise_import(kategorie: str = ""):
    """Importiert Materialpreise aus SB (API oder CSV)."""
    _check_agent()

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="schreiners_buero",
        msg_type="sb_materialpreise_import",
        payload={"quelle": "api", "kategorie": kategorie},
        projekt_id="SYSTEM",
    )
    result = await _sb_agent.execute(msg)

    # Bei Erfolg: Preise in lokale DB uebernehmen
    preise = result.payload.get("preise", [])
    if preise and result.payload.get("status") == "ok":
        from datetime import datetime
        async with get_db() as db:
            importiert = 0
            for p in preise:
                name = p.get("material_name", "")
                preis = p.get("preis", 0)
                if name and preis > 0:
                    await db.execute(
                        """INSERT INTO materialpreise
                           (material_name, kategorie, lieferant, artikel_nr, einheit, preis, gueltig_ab, notizen)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            name,
                            p.get("kategorie", ""),
                            p.get("lieferant", "SB-Import"),
                            p.get("artikel_nr", ""),
                            p.get("einheit", "STK"),
                            preis,
                            datetime.now().isoformat(),
                            "Importiert aus Schreiner's Buero",
                        ),
                    )
                    importiert += 1
            await db.commit()
            result.payload["in_db_gespeichert"] = importiert

    return result.payload


# ------------------------------------------------------------------
# 7. CSV-Datei hochladen (Materialpreise oder Stueckliste)
# ------------------------------------------------------------------

@router.post("/csv/upload")
async def sb_csv_upload(
    datei: UploadFile = File(...),
    typ: str = Form("stueckliste"),
):
    """Laedt eine SB-CSV-Datei hoch und importiert sie.

    typ: 'stueckliste' oder 'materialpreise'
    """
    _check_agent()

    if not datei.filename or not datei.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Nur CSV-Dateien erlaubt")

    # In Import-Verzeichnis speichern
    import_dir = Path("data/sb_import")
    import_dir.mkdir(parents=True, exist_ok=True)
    ziel = import_dir / datei.filename
    content = await datei.read()
    with open(str(ziel), "wb") as f:
        f.write(content)

    from agents.base_agent import AgentMessage

    if typ == "materialpreise":
        msg = AgentMessage(
            sender="api", receiver="schreiners_buero",
            msg_type="sb_materialpreise_import",
            payload={"quelle": "csv", "datei_pfad": str(ziel)},
            projekt_id="IMPORT",
        )
    else:
        msg = AgentMessage(
            sender="api", receiver="schreiners_buero",
            msg_type="sb_csv_import",
            payload={"datei_pfad": str(ziel)},
            projekt_id="IMPORT",
        )

    result = await _sb_agent.execute(msg)
    return result.payload


# ------------------------------------------------------------------
# 8. CSV-Export herunterladen
# ------------------------------------------------------------------

@router.post("/{projekt_id}/csv/export")
async def sb_csv_export(projekt_id: str):
    """Exportiert Positionen als CSV im SB-Format."""
    _check_agent()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        projekt = await cursor.fetchone()
        if not projekt:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        positionen = [dict(r) for r in await cursor.fetchall()]

    if not positionen:
        raise HTTPException(status_code=400, detail="Keine Positionen vorhanden")

    from agents.base_agent import AgentMessage
    msg = AgentMessage(
        sender="api", receiver="schreiners_buero",
        msg_type="sb_csv_export",
        payload={
            "positionen": positionen,
            "projekt": dict(projekt),
        },
        projekt_id=projekt_id,
    )
    result = await _sb_agent.execute(msg)

    csv_pfad = result.payload.get("pfad")
    if csv_pfad and Path(csv_pfad).exists():
        return FileResponse(
            csv_pfad,
            media_type="text/csv",
            filename=result.payload.get("datei", "sb_export.csv"),
        )

    if result.payload.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("message", "Export fehlgeschlagen"))

    return result.payload
