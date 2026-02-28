"""
API-Routes fuer Altprojekt-Analyse.

Ermoeglicht das Scannen, Analysieren und Importieren
von historischen Projekten zur Preisreferenz.
"""

from __future__ import annotations

from typing import Any

from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File

from api.database import get_db

router = APIRouter(prefix="/api/analyse", tags=["Analyse"])

# Referenz auf Pipeline (wird beim Startup gesetzt)
_pipeline: Any = None


def set_pipeline(pipeline: Any) -> None:
    global _pipeline
    _pipeline = pipeline


def _get_agent():
    if not _pipeline:
        raise HTTPException(status_code=503, detail="Pipeline nicht initialisiert")
    agent = _pipeline.subagenten.get("analyse_agent")
    if not agent:
        raise HTTPException(status_code=503, detail="Analyse-Agent nicht verfuegbar")
    return agent


@router.post("/scan")
async def scan_altprojekt(pfad: str):
    """Scannt ein Altprojekt-Verzeichnis und listet alle relevanten Dateien."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="analyse_agent",
        msg_type="scan_altprojekt",
        payload={"pfad": pfad},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/excel")
async def analyse_excel(pfad: str):
    """Analysiert eine Excel-LV-Datei und extrahiert Positionen."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="analyse_agent",
        msg_type="analyse_excel_lv",
        payload={"pfad": pfad},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/gaeb")
async def analyse_gaeb(pfad: str):
    """Analysiert eine GAEB-Datei und extrahiert Positionen."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="analyse_agent",
        msg_type="analyse_gaeb",
        payload={"pfad": pfad},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/smartwop-csvs")
async def analyse_smartwop_csvs(pfad: str):
    """Analysiert Smartwop-CSV-Dateien (Zuschnitts-/Stuecklisten)."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="analyse_agent",
        msg_type="analyse_smartwop_csvs",
        payload={"pfad": pfad},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/smartwop-upload")
async def smartwop_csv_upload(dateien: List[UploadFile] = File(...)):
    """Nimmt eine oder mehrere SmartWOP-CSV-Dateien entgegen und parst sie."""
    import tempfile, os, shutil
    from agents.base_agent import AgentMessage

    agent = _get_agent()

    # Alle Dateien in einen temp-Ordner schreiben
    tmpdir = tempfile.mkdtemp(prefix="smartwop_")
    gespeichert = []
    for datei in dateien:
        fname = datei.filename or f"upload_{len(gespeichert)}.csv"
        tmppath = os.path.join(tmpdir, fname)
        content = await datei.read()
        with open(tmppath, "wb") as f:
            f.write(content)
        gespeichert.append(tmppath)

    msg = AgentMessage(
        sender="api", receiver="analyse_agent",
        msg_type="analyse_smartwop_csvs",
        payload={"pfad": tmpdir},
    )
    result = await agent.execute(msg)

    # Cleanup
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except OSError:
        pass

    return result.payload


@router.post("/komplett")
async def analyse_komplett(pfad: str):
    """Fuehrt eine komplette Analyse eines Altprojekt-Ordners durch."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="analyse_agent",
        msg_type="analyse_komplett",
        payload={"pfad": pfad},
    )
    result = await agent.execute(msg)

    # Bei Erfolg in DB speichern
    if result.payload.get("status") == "ok":
        await _speichere_analyse(result.payload)

    return result.payload


@router.post("/inflation")
async def inflationsanpassung(betrag: float, projekt_datum: str, rate: float = 0.04):
    """Berechnet inflationsbereinigten Preis."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="analyse_agent",
        msg_type="inflationsanpassung",
        payload={
            "betrag": betrag,
            "projekt_datum": projekt_datum,
            "inflationsrate": rate,
        },
    )
    result = await agent.execute(msg)
    return result.payload


@router.get("/historie")
async def liste_analysen():
    """Liste aller gespeicherten Altprojekt-Analysen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM altprojekt_analysen ORDER BY analyse_datum DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.get("/historie/{analyse_id}")
async def get_analyse(analyse_id: int):
    """Einzelne Analyse abrufen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM altprojekt_analysen WHERE id = ?", (analyse_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Analyse nicht gefunden")
        return dict(row)


@router.delete("/historie/{analyse_id}", status_code=204)
async def loesche_analyse(analyse_id: int):
    """Analyse loeschen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM altprojekt_analysen WHERE id = ?", (analyse_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Analyse nicht gefunden")
        await db.execute("DELETE FROM altprojekt_analysen WHERE id = ?", (analyse_id,))
        await db.commit()


async def _speichere_analyse(ergebnis: dict) -> None:
    """Speichert ein Analyse-Ergebnis in der DB."""
    import json
    from datetime import datetime

    async with get_db() as db:
        await db.execute(
            """INSERT INTO altprojekt_analysen
               (projekt_name, quell_pfad, analyse_datum,
                positionen_json, materialien_json, maschinen_json,
                stundensaetze_json, inflationsfaktor, projekt_datum, notizen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ergebnis.get("projekt_name", "Unbekannt"),
                ergebnis.get("quell_pfad", ""),
                datetime.now().isoformat(),
                json.dumps(ergebnis.get("positionen", []), ensure_ascii=False),
                json.dumps(ergebnis.get("materialien", []), ensure_ascii=False),
                json.dumps(ergebnis.get("maschinen", []), ensure_ascii=False),
                json.dumps(ergebnis.get("stundensaetze", {}), ensure_ascii=False),
                ergebnis.get("inflationsfaktor", 1.0),
                ergebnis.get("projekt_datum", ""),
                ergebnis.get("notizen", ""),
            ),
        )
        await db.commit()
