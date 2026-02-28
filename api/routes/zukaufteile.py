"""
API-Routes fuer Zukaufteile (eingekaufte Teile pro Projekt).
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.database import get_db
from api.models.schemas import ZukaufteilCreate, ZukaufteilResponse

router = APIRouter(prefix="/api/projekte/{projekt_id}/zukaufteile", tags=["Zukaufteile"])


@router.get("/", response_model=list[ZukaufteilResponse])
async def liste_zukaufteile(projekt_id: str, position_id: int | None = None):
    """Alle Zukaufteile eines Projekts (optional nach Position gefiltert)."""
    async with get_db() as db:
        if position_id is not None:
            cursor = await db.execute(
                "SELECT * FROM zukaufteile WHERE projekt_id = ? AND position_id = ? ORDER BY id",
                (projekt_id, position_id),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM zukaufteile WHERE projekt_id = ? ORDER BY position_id, id",
                (projekt_id,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.post("/", response_model=ZukaufteilResponse, status_code=201)
async def erstelle_zukaufteil(projekt_id: str, data: ZukaufteilCreate):
    """Neues Zukaufteil anlegen."""
    now = datetime.now().isoformat()
    verkaufspreis = round(data.einkaufspreis * data.menge * (1 + data.aufschlag_prozent / 100), 2)

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM projekte WHERE id = ?", (projekt_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        if data.position_id is not None:
            cursor = await db.execute(
                "SELECT id FROM positionen WHERE id = ? AND projekt_id = ?",
                (data.position_id, projekt_id),
            )
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Position nicht gefunden")

        cursor = await db.execute(
            """INSERT INTO zukaufteile
               (projekt_id, position_id, bezeichnung, hersteller, produkt,
                artikel_nr, produkt_link, einkaufspreis, menge,
                aufschlag_prozent, verkaufspreis, status, quelle,
                alternativ_json, erstellt_am, aktualisiert_am)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                projekt_id, data.position_id, data.bezeichnung, data.hersteller,
                data.produkt, data.artikel_nr, data.produkt_link,
                data.einkaufspreis, data.menge, data.aufschlag_prozent,
                verkaufspreis, data.status, data.quelle,
                "[]", now, now,
            ),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM zukaufteile WHERE id = ?", (cursor.lastrowid,))
        return dict(await cursor.fetchone())


@router.get("/{zukaufteil_id}", response_model=ZukaufteilResponse)
async def get_zukaufteil(projekt_id: str, zukaufteil_id: int):
    """Einzelnes Zukaufteil abrufen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM zukaufteile WHERE id = ? AND projekt_id = ?",
            (zukaufteil_id, projekt_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Zukaufteil nicht gefunden")
        return dict(row)


@router.patch("/{zukaufteil_id}", response_model=ZukaufteilResponse)
async def update_zukaufteil(projekt_id: str, zukaufteil_id: int, data: ZukaufteilCreate):
    """Zukaufteil aktualisieren."""
    now = datetime.now().isoformat()
    verkaufspreis = round(data.einkaufspreis * data.menge * (1 + data.aufschlag_prozent / 100), 2)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM zukaufteile WHERE id = ? AND projekt_id = ?",
            (zukaufteil_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Zukaufteil nicht gefunden")

        await db.execute(
            """UPDATE zukaufteile SET
               position_id=?, bezeichnung=?, hersteller=?, produkt=?,
               artikel_nr=?, produkt_link=?, einkaufspreis=?, menge=?,
               aufschlag_prozent=?, verkaufspreis=?, status=?, quelle=?,
               aktualisiert_am=?
               WHERE id = ? AND projekt_id = ?""",
            (
                data.position_id, data.bezeichnung, data.hersteller, data.produkt,
                data.artikel_nr, data.produkt_link, data.einkaufspreis, data.menge,
                data.aufschlag_prozent, verkaufspreis, data.status, data.quelle,
                now, zukaufteil_id, projekt_id,
            ),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM zukaufteile WHERE id = ?", (zukaufteil_id,))
        return dict(await cursor.fetchone())


@router.delete("/{zukaufteil_id}", status_code=204)
async def loesche_zukaufteil(projekt_id: str, zukaufteil_id: int):
    """Zukaufteil loeschen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM zukaufteile WHERE id = ? AND projekt_id = ?",
            (zukaufteil_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Zukaufteil nicht gefunden")

        await db.execute("DELETE FROM zukaufteile WHERE id = ?", (zukaufteil_id,))
        await db.commit()
