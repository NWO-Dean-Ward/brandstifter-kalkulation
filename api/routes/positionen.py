"""
API-Routes für Positionen (LV-Positionen pro Projekt).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from api.database import get_db
from api.models.schemas import KorpusRequest, PositionCreate, PositionResponse

KORPUS_QUELLE = "korpus-generator"

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


@router.patch("/{position_id}", response_model=PositionResponse)
async def update_position(projekt_id: str, position_id: int, data: PositionCreate):
    """Position aktualisieren."""
    ist_lackierung = _check_lackierung(data.kurztext, data.langtext)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM positionen WHERE id = ? AND projekt_id = ?",
            (position_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Position nicht gefunden")

        await db.execute(
            """UPDATE positionen SET
               pos_nr=?, kurztext=?, langtext=?, menge=?, einheit=?, material=?,
               platten_anzahl=?, kantenlaenge_lfm=?, schnittanzahl=?, bohrungen_anzahl=?,
               ist_lackierung=?, ist_fremdleistung=?
               WHERE id = ? AND projekt_id = ?""",
            (
                data.pos_nr, data.kurztext, data.langtext,
                data.menge, data.einheit, data.material,
                data.platten_anzahl, data.kantenlaenge_lfm,
                data.schnittanzahl, data.bohrungen_anzahl,
                int(ist_lackierung), int(ist_lackierung),
                position_id, projekt_id,
            ),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM positionen WHERE id = ?", (position_id,))
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


@router.put("/{position_id}/korpus")
async def setze_korpus(projekt_id: str, position_id: int, data: KorpusRequest):
    """Macht die Position zur Korpus-Position: Kalkulation ueber den Korpus-Generator.

    data.anzahl = Korpusse je Positionseinheit (z.B. 1 je STK, 5 je PAU).
    Speichert die Parameter und die Stueckliste als Werkstuecke; EP/GP kommen mit
    der naechsten Kalkulation.
    """
    from agents.korpus_generator import KonfigurationsFehler, berechne_korpus
    from agents.korpus_kalkulator import parameter_aus_position
    from api.routes.korpus import lade_kalkulationsbasis

    parameter = data.model_dump()
    parameter["anzahl"] = max(int(parameter.get("anzahl") or 1), 1)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE id = ? AND projekt_id = ?", (position_id, projekt_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Position nicht gefunden")

        regeln, maschinen, katalog = lade_kalkulationsbasis()
        try:
            korpus_parameter = parameter_aus_position({**dict(row), "korpus_parameter": json.dumps(parameter)})
            ergebnis = berechne_korpus(korpus_parameter, regeln=regeln, maschinen_cfg=maschinen, katalog=katalog)
        except KonfigurationsFehler as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        await db.execute(
            "UPDATE positionen SET kalkulationsquelle = 'korpus', korpus_parameter = ? WHERE id = ?",
            (json.dumps(parameter, ensure_ascii=False), position_id),
        )
        await schreibe_korpus_werkstuecke(db, projekt_id, position_id, ergebnis)
        await db.commit()

        cursor = await db.execute("SELECT * FROM positionen WHERE id = ?", (position_id,))
        position = _row_to_response(await cursor.fetchone())

    return {
        "position": position,
        "korpus": ergebnis,
        "hinweis": "Korpus gespeichert. Kalkulation neu starten, damit EP/GP aktualisiert werden.",
    }


@router.delete("/{position_id}/korpus", response_model=PositionResponse)
async def entferne_korpus(projekt_id: str, position_id: int):
    """Setzt die Position zurueck auf die Standard-Schaetzung und loescht die Korpus-Werkstuecke."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM positionen WHERE id = ? AND projekt_id = ?", (position_id, projekt_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Position nicht gefunden")

        await db.execute(
            "UPDATE positionen SET kalkulationsquelle = '', korpus_parameter = '' WHERE id = ?",
            (position_id,),
        )
        await db.execute(
            "DELETE FROM werkstuecke WHERE projekt_id = ? AND position_id = ? AND quelle = ?",
            (projekt_id, position_id, KORPUS_QUELLE),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM positionen WHERE id = ?", (position_id,))
        return _row_to_response(await cursor.fetchone())


async def schreibe_korpus_werkstuecke(
    db: Any, projekt_id: str, position_id: int, stueckliste: dict[str, Any],
) -> None:
    """Ersetzt die Korpus-Werkstuecke einer Position durch die aktuelle Stueckliste.

    Manuell angelegte Werkstuecke (quelle leer) bleiben unberuehrt. Commit macht der Aufrufer.
    """
    await db.execute(
        "DELETE FROM werkstuecke WHERE projekt_id = ? AND position_id = ? AND quelle = ?",
        (projekt_id, position_id, KORPUS_QUELLE),
    )
    jetzt = datetime.now().isoformat()
    notiz = f"Korpus-Generator: {stueckliste.get('gegenstand', '')}"
    for teil in stueckliste.get("teile", []):
        await db.execute(
            """INSERT INTO werkstuecke
               (projekt_id, position_id, bezeichnung, anzahl, laenge_mm, breite_mm, tiefe_mm,
                staerke_mm, material, oberflaeche, fertigung, ist_fremdleistung, hop_datei,
                notizen, erstellt_am, quelle)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, '', 'cnc-nesting', 0, '', ?, ?, ?)""",
            (
                projekt_id, position_id, teil["bezeichnung"], int(teil["anzahl"]),
                teil["laenge_mm"], teil["breite_mm"], teil["staerke_mm"], teil["material"],
                notiz, jetzt, KORPUS_QUELLE,
            ),
        )


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
