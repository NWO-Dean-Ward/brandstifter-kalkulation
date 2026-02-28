"""
API-Routes fuer manuelle Ueberschreibungen (Audit-Trail pro Position).

Erlaubt das manuelle Ueberschreiben von Kalkulationswerten
mit Pflicht-Begruendung und vollstaendigem Audit-Trail.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.database import get_db
from api.models.schemas import UeberschreibungCreate, UeberschreibungResponse

router = APIRouter(prefix="/api/projekte/{projekt_id}/ueberschreibungen", tags=["Ueberschreibungen"])

# Erlaubte Felder fuer Ueberschreibungen
ERLAUBTE_FELDER = {"einheitspreis", "materialkosten", "maschinenkosten", "lohnkosten", "gesamtpreis"}


@router.get("/", response_model=list[UeberschreibungResponse])
async def liste_ueberschreibungen(projekt_id: str, position_id: int | None = None):
    """Alle Ueberschreibungen eines Projekts (optional nach Position gefiltert)."""
    async with get_db() as db:
        if position_id is not None:
            cursor = await db.execute(
                """SELECT * FROM manuelle_ueberschreibungen
                   WHERE projekt_id = ? AND position_id = ?
                   ORDER BY geaendert_am DESC""",
                (projekt_id, position_id),
            )
        else:
            cursor = await db.execute(
                """SELECT * FROM manuelle_ueberschreibungen
                   WHERE projekt_id = ?
                   ORDER BY geaendert_am DESC""",
                (projekt_id,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.post("/", response_model=UeberschreibungResponse, status_code=201)
async def erstelle_ueberschreibung(projekt_id: str, data: UeberschreibungCreate):
    """Erstellt eine manuelle Ueberschreibung mit Audit-Trail.

    - Aktualisiert den Wert in der Positionen-Tabelle
    - Speichert den alten Wert im Audit-Trail
    - Begruendung ist Pflicht
    """
    if data.feld not in ERLAUBTE_FELDER:
        raise HTTPException(
            status_code=400,
            detail=f"Feld '{data.feld}' nicht erlaubt. Erlaubt: {', '.join(sorted(ERLAUBTE_FELDER))}",
        )

    if not data.begruendung.strip():
        raise HTTPException(
            status_code=400,
            detail="Begruendung ist Pflicht bei manueller Ueberschreibung",
        )

    now = datetime.now().isoformat()

    async with get_db() as db:
        # Position pruefen und alten Wert holen
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE id = ? AND projekt_id = ?",
            (data.position_id, projekt_id),
        )
        position = await cursor.fetchone()
        if not position:
            raise HTTPException(status_code=404, detail="Position nicht gefunden")

        pos_dict = dict(position)
        alter_wert = pos_dict.get(data.feld, 0)

        # Ueberschreibung im Audit-Trail speichern
        cursor = await db.execute(
            """INSERT INTO manuelle_ueberschreibungen
               (projekt_id, position_id, feld, alter_wert, neuer_wert,
                begruendung, geaendert_am, geaendert_von)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                projekt_id, data.position_id, data.feld,
                alter_wert, data.neuer_wert,
                data.begruendung.strip(), now, "dean",
            ),
        )
        ueberschreibung_id = cursor.lastrowid

        # Wert in Positionen-Tabelle aktualisieren
        await db.execute(
            f"UPDATE positionen SET {data.feld} = ? WHERE id = ? AND projekt_id = ?",
            (data.neuer_wert, data.position_id, projekt_id),
        )

        # Bei EP-Aenderung: GP automatisch neu berechnen
        if data.feld == "einheitspreis":
            menge = pos_dict.get("menge", 0)
            neuer_gp = round(data.neuer_wert * menge, 2)
            await db.execute(
                "UPDATE positionen SET gesamtpreis = ? WHERE id = ? AND projekt_id = ?",
                (neuer_gp, data.position_id, projekt_id),
            )

        # Bei GP-Aenderung: EP automatisch neu berechnen
        if data.feld == "gesamtpreis":
            menge = pos_dict.get("menge", 0)
            if menge > 0:
                neuer_ep = round(data.neuer_wert / menge, 2)
                await db.execute(
                    "UPDATE positionen SET einheitspreis = ? WHERE id = ? AND projekt_id = ?",
                    (neuer_ep, data.position_id, projekt_id),
                )

        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM manuelle_ueberschreibungen WHERE id = ?",
            (ueberschreibung_id,),
        )
        return dict(await cursor.fetchone())


@router.delete("/{ueberschreibung_id}", status_code=204)
async def loesche_ueberschreibung(projekt_id: str, ueberschreibung_id: int):
    """Ueberschreibung loeschen (setzt NICHT den alten Wert zurueck)."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM manuelle_ueberschreibungen WHERE id = ? AND projekt_id = ?",
            (ueberschreibung_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Ueberschreibung nicht gefunden")

        await db.execute(
            "DELETE FROM manuelle_ueberschreibungen WHERE id = ?",
            (ueberschreibung_id,),
        )
        await db.commit()
