"""
API-Routes fuer Werkstuecke (Einzelbauteile pro Projekt/Position).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.database import get_db
from api.models.schemas import WerkstueckCreate, WerkstueckResponse

router = APIRouter(prefix="/api/projekte/{projekt_id}/werkstuecke", tags=["Werkstuecke"])


@router.get("/", response_model=list[WerkstueckResponse])
async def liste_werkstuecke(projekt_id: str, position_id: int | None = None):
    """Alle Werkstuecke eines Projekts (optional nach Position gefiltert)."""
    async with get_db() as db:
        if position_id is not None:
            cursor = await db.execute(
                "SELECT * FROM werkstuecke WHERE projekt_id = ? AND position_id = ? ORDER BY id",
                (projekt_id, position_id),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM werkstuecke WHERE projekt_id = ? ORDER BY position_id, id",
                (projekt_id,),
            )
        rows = await cursor.fetchall()
        return [_row_to_response(row) for row in rows]


@router.post("/", response_model=WerkstueckResponse, status_code=201)
async def erstelle_werkstueck(projekt_id: str, data: WerkstueckCreate):
    """Neues Werkstueck anlegen."""
    # Fremdleistung automatisch bei Lackierung
    ist_fremd = 1 if data.oberflaeche.lower() in ("lackiert-extern", "lackiert") else 0

    now = datetime.now().isoformat()

    async with get_db() as db:
        # Projekt pruefen
        cursor = await db.execute("SELECT id FROM projekte WHERE id = ?", (projekt_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        # Position pruefen falls angegeben
        if data.position_id is not None:
            cursor = await db.execute(
                "SELECT id FROM positionen WHERE id = ? AND projekt_id = ?",
                (data.position_id, projekt_id),
            )
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Position nicht gefunden")

        cursor = await db.execute(
            """INSERT INTO werkstuecke
               (projekt_id, position_id, bezeichnung, anzahl,
                laenge_mm, breite_mm, tiefe_mm, staerke_mm,
                material, oberflaeche, fertigung, ist_fremdleistung,
                hop_datei, notizen, erstellt_am)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                projekt_id, data.position_id, data.bezeichnung, data.anzahl,
                data.laenge_mm, data.breite_mm, data.tiefe_mm, data.staerke_mm,
                data.material, data.oberflaeche, data.fertigung, ist_fremd,
                data.hop_datei, data.notizen, now,
            ),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM werkstuecke WHERE id = ?", (cursor.lastrowid,))
        return _row_to_response(await cursor.fetchone())


@router.get("/{werkstueck_id}", response_model=WerkstueckResponse)
async def get_werkstueck(projekt_id: str, werkstueck_id: int):
    """Einzelnes Werkstueck abrufen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM werkstuecke WHERE id = ? AND projekt_id = ?",
            (werkstueck_id, projekt_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Werkstueck nicht gefunden")
        return _row_to_response(row)


@router.patch("/{werkstueck_id}", response_model=WerkstueckResponse)
async def update_werkstueck(projekt_id: str, werkstueck_id: int, data: WerkstueckCreate):
    """Werkstueck aktualisieren."""
    ist_fremd = 1 if data.oberflaeche.lower() in ("lackiert-extern", "lackiert") else 0

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM werkstuecke WHERE id = ? AND projekt_id = ?",
            (werkstueck_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Werkstueck nicht gefunden")

        await db.execute(
            """UPDATE werkstuecke SET
               position_id=?, bezeichnung=?, anzahl=?,
               laenge_mm=?, breite_mm=?, tiefe_mm=?, staerke_mm=?,
               material=?, oberflaeche=?, fertigung=?, ist_fremdleistung=?,
               hop_datei=?, notizen=?
               WHERE id = ? AND projekt_id = ?""",
            (
                data.position_id, data.bezeichnung, data.anzahl,
                data.laenge_mm, data.breite_mm, data.tiefe_mm, data.staerke_mm,
                data.material, data.oberflaeche, data.fertigung, ist_fremd,
                data.hop_datei, data.notizen,
                werkstueck_id, projekt_id,
            ),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM werkstuecke WHERE id = ?", (werkstueck_id,))
        return _row_to_response(await cursor.fetchone())


@router.delete("/{werkstueck_id}", status_code=204)
async def loesche_werkstueck(projekt_id: str, werkstueck_id: int):
    """Werkstueck loeschen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM werkstuecke WHERE id = ? AND projekt_id = ?",
            (werkstueck_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Werkstueck nicht gefunden")

        await db.execute("DELETE FROM werkstuecke WHERE id = ?", (werkstueck_id,))
        await db.commit()


def _row_to_response(row) -> dict:
    d = dict(row)
    d["ist_fremdleistung"] = bool(d.get("ist_fremdleistung", 0))
    return d
