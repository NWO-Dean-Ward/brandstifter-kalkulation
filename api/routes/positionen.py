"""
API-Routes für Positionen (LV-Positionen pro Projekt).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.database import get_db
from api.models.schemas import PositionCreate, PositionResponse

router = APIRouter(prefix="/api/projekte/{projekt_id}/positionen", tags=["Positionen"])


@router.get("/", response_model=list[PositionResponse])
async def liste_positionen(projekt_id: str):
    """Alle Positionen eines Projekts abrufen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_response(row) for row in rows]


@router.post("/", response_model=PositionResponse, status_code=201)
async def erstelle_position(projekt_id: str, data: PositionCreate):
    """Neue Position zu einem Projekt hinzufügen."""
    # Lackierungs-Erkennung
    ist_lackierung = _check_lackierung(data.kurztext, data.langtext)

    async with get_db() as db:
        # Projekt prüfen
        cursor = await db.execute(
            "SELECT id FROM projekte WHERE id = ?", (projekt_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        cursor = await db.execute(
            """INSERT INTO positionen
               (projekt_id, pos_nr, kurztext, langtext, menge, einheit, material,
                platten_anzahl, kantenlaenge_lfm, schnittanzahl, bohrungen_anzahl,
                ist_lackierung, ist_fremdleistung)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                projekt_id, data.pos_nr, data.kurztext, data.langtext,
                data.menge, data.einheit, data.material,
                data.platten_anzahl, data.kantenlaenge_lfm,
                data.schnittanzahl, data.bohrungen_anzahl,
                int(ist_lackierung), int(ist_lackierung),  # Lackierung = Fremdleistung
            ),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM positionen WHERE id = ?", (cursor.lastrowid,)
        )
        return _row_to_response(await cursor.fetchone())


@router.delete("/{position_id}", status_code=204)
async def loesche_position(projekt_id: str, position_id: int):
    """Position löschen."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM positionen WHERE id = ? AND projekt_id = ?",
            (position_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Position nicht gefunden")

        await db.execute("DELETE FROM positionen WHERE id = ?", (position_id,))
        await db.commit()


def _check_lackierung(kurztext: str, langtext: str) -> bool:
    """Prüft ob eine Position Lackierung enthält."""
    lack_keywords = [
        "lackier", "ral ", "ral-", "ncs ", "ncs-",
        "farbbeschicht", "spritzlackier", "pulverbeschicht",
        "hochglanz", "mattlack", "seidenmatt",
    ]
    text = f"{kurztext} {langtext}".lower()
    return any(kw in text for kw in lack_keywords)


def _row_to_response(row) -> dict:
    """Konvertiert eine DB-Row in ein Response-Dict."""
    d = dict(row)
    d["ist_lackierung"] = bool(d.get("ist_lackierung", 0))
    d["ist_fremdleistung"] = bool(d.get("ist_fremdleistung", 0))
    return d
