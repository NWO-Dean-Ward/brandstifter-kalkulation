"""
API-Routes für Projekte.

CRUD-Operationen + Kalkulations-Trigger.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

import logging

from api.database import get_db
from api.models.schemas import (
    ProjektCreate,
    ProjektResponse,
    ProjektUpdate,
)

router = APIRouter(prefix="/api/projekte", tags=["Projekte"])
logger = logging.getLogger(__name__)

# Referenz auf Pipeline (fuer Auto-Learn)
_pipeline = None

def set_pipeline(pipeline) -> None:
    global _pipeline
    _pipeline = pipeline


@router.get("/", response_model=list[ProjektResponse])
async def liste_projekte():
    """Alle Projekte abrufen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM projekte ORDER BY aktualisiert_am DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.get("/{projekt_id}", response_model=ProjektResponse)
async def get_projekt(projekt_id: str):
    """Ein Projekt anhand der ID abrufen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        return dict(row)


@router.post("/", response_model=ProjektResponse, status_code=201)
async def erstelle_projekt(data: ProjektCreate):
    """Neues Projekt anlegen."""
    projekt_id = f"PRJ-{uuid.uuid4().hex[:8].upper()}"
    jetzt = datetime.now().isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO projekte
               (id, name, projekt_typ, status, kunde, beschreibung, deadline,
                erstellt_am, aktualisiert_am)
               VALUES (?, ?, ?, 'entwurf', ?, ?, ?, ?, ?)""",
            (
                projekt_id, data.name, data.projekt_typ,
                data.kunde, data.beschreibung, data.deadline,
                jetzt, jetzt,
            ),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        return dict(await cursor.fetchone())


@router.patch("/{projekt_id}", response_model=ProjektResponse)
async def update_projekt(projekt_id: str, data: ProjektUpdate):
    """Projekt aktualisieren."""
    async with get_db() as db:
        # Prüfen ob Projekt existiert
        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        updates = data.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="Keine Änderungen angegeben")

        updates["aktualisiert_am"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [projekt_id]

        # Alten Status merken fuer Auto-Learn
        cursor2 = await db.execute("SELECT status FROM projekte WHERE id = ?", (projekt_id,))
        alter_status_row = await cursor2.fetchone()
        alter_status = dict(alter_status_row).get("status", "") if alter_status_row else ""

        await db.execute(
            f"UPDATE projekte SET {set_clause} WHERE id = ?", values
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        projekt = dict(await cursor.fetchone())

        # Auto-Learn: Bei Statuswechsel zu abgeschlossen/beauftragt/verloren
        neuer_status = updates.get("status", "")
        lern_trigger = {"abgeschlossen", "beauftragt", "verloren"}
        if neuer_status in lern_trigger and alter_status not in lern_trigger:
            await _auto_learn(projekt_id, neuer_status)

        return projekt


async def _auto_learn(projekt_id: str, ergebnis: str) -> None:
    """Speichert Projekt automatisch in der Lernhistorie bei Statuswechsel."""
    if not _pipeline:
        return
    lern_agent = _pipeline.subagenten.get("lern_agent")
    if not lern_agent:
        return

    try:
        from agents.base_agent import AgentMessage
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM positionen WHERE projekt_id = ?", (projekt_id,)
            )
            positionen = [dict(r) for r in await cursor.fetchall()]

        if not positionen:
            return

        # Ergebnis-Mapping
        ergebnis_map = {"abgeschlossen": "beauftragt", "beauftragt": "beauftragt", "verloren": "verloren"}

        msg = AgentMessage(
            sender="api", receiver="lern_agent",
            msg_type="projekt_speichern",
            payload={
                "positionen": positionen,
                "ergebnis": ergebnis_map.get(ergebnis, ergebnis),
            },
            projekt_id=projekt_id,
        )
        await lern_agent.execute(msg)
        logger.info("Auto-Learn: Projekt %s als '%s' gespeichert", projekt_id, ergebnis)
    except Exception as e:
        logger.warning("Auto-Learn fehlgeschlagen fuer %s: %s", projekt_id, e)


@router.post("/{projekt_id}/kopieren", response_model=ProjektResponse, status_code=201)
async def kopiere_projekt(projekt_id: str):
    """Projekt duplizieren inkl. Positionen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        original = await cursor.fetchone()
        if not original:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        original = dict(original)
        neues_id = f"PRJ-{uuid.uuid4().hex[:8].upper()}"
        jetzt = datetime.now().isoformat()

        await db.execute(
            """INSERT INTO projekte
               (id, name, projekt_typ, status, kunde, beschreibung, deadline,
                erstellt_am, aktualisiert_am)
               VALUES (?, ?, ?, 'entwurf', ?, ?, ?, ?, ?)""",
            (
                neues_id,
                f"{original['name']} (Kopie)",
                original["projekt_typ"],
                original["kunde"],
                original["beschreibung"],
                original.get("deadline", ""),
                jetzt, jetzt,
            ),
        )

        # Positionen kopieren
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ?", (projekt_id,)
        )
        pos_rows = [dict(r) for r in await cursor.fetchall()]
        for pos in pos_rows:
            await db.execute(
                """INSERT INTO positionen
                   (projekt_id, pos_nr, kurztext, langtext, menge, einheit, material,
                    platten_anzahl, kantenlaenge_lfm, schnittanzahl, bohrungen_anzahl,
                    ist_lackierung)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    neues_id, pos["pos_nr"], pos["kurztext"], pos.get("langtext", ""),
                    pos["menge"], pos["einheit"], pos.get("material", ""),
                    pos.get("platten_anzahl", 0), pos.get("kantenlaenge_lfm", 0),
                    pos.get("schnittanzahl", 0), pos.get("bohrungen_anzahl", 0),
                    pos.get("ist_lackierung", 0),
                ),
            )

        await db.commit()

        cursor = await db.execute("SELECT * FROM projekte WHERE id = ?", (neues_id,))
        return dict(await cursor.fetchone())


@router.delete("/{projekt_id}", status_code=204)
async def loesche_projekt(projekt_id: str):
    """Projekt und alle zugehörigen Daten löschen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM projekte WHERE id = ?", (projekt_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        await db.execute("DELETE FROM projekte WHERE id = ?", (projekt_id,))
        await db.commit()
