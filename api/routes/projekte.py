"""
API-Routes für Projekte.

CRUD-Operationen + Kalkulations-Trigger.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.database import get_db
from api.models.schemas import (
    ProjektCreate,
    ProjektResponse,
    ProjektUpdate,
)

router = APIRouter(prefix="/api/projekte", tags=["Projekte"])


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

        await db.execute(
            f"UPDATE projekte SET {set_clause} WHERE id = ?", values
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
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
