"""
API-Routes für Kalkulationen.

Triggert die Agenten-Pipeline und gibt Ergebnisse zurück.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from api.database import get_db
from api.models.schemas import KalkulationErgebnis, UploadResponse

router = APIRouter(prefix="/api/kalkulation", tags=["Kalkulation"])

# Referenz auf die Agenten-Pipeline (wird von main.py gesetzt)
_pipeline: Any = None


def set_pipeline(pipeline: Any) -> None:
    """Setzt die Referenz auf die initialisierte Agenten-Pipeline."""
    global _pipeline
    _pipeline = pipeline


@router.post("/starten/{projekt_id}", response_model=KalkulationErgebnis)
async def starte_kalkulation(projekt_id: str):
    """Startet die Kalkulations-Pipeline für ein Projekt.

    Workflow:
    1. Projekt + Positionen aus DB laden
    2. LeadAgent mit allen Subagenten ausführen
    3. Ergebnis in DB speichern
    4. KalkulationErgebnis zurückgeben
    """
    if _pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Kalkulations-Pipeline nicht initialisiert",
        )

    async with get_db() as db:
        # Projekt laden
        cursor = await db.execute(
            "SELECT * FROM projekte WHERE id = ?", (projekt_id,)
        )
        projekt = await cursor.fetchone()
        if not projekt:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        # Positionen laden
        cursor = await db.execute(
            "SELECT * FROM positionen WHERE projekt_id = ? ORDER BY pos_nr",
            (projekt_id,),
        )
        positionen = [dict(row) for row in await cursor.fetchall()]

        if not positionen:
            raise HTTPException(
                status_code=400,
                detail="Keine Positionen vorhanden. Bitte zuerst Positionen anlegen.",
            )

    # Agenten-Pipeline ausfuehren
    from agents.base_agent import AgentMessage

    message = AgentMessage(
        sender="api",
        receiver="lead_agent",
        msg_type="kalkuliere_positionen",
        payload={
            "positionen": positionen,
            "projekt_typ": dict(projekt)["projekt_typ"],
        },
        projekt_id=projekt_id,
    )

    result = await _pipeline.execute(message)

    if result.msg_type == "error":
        raise HTTPException(status_code=500, detail=result.payload.get("error", "Unbekannter Fehler"))

    p = result.payload
    zuschlaege = p.get("zuschlaege", {})

    # Angebotspreise je Position (inkl. GKZ/Gewinn/Wagnis/Zuschlaege, Lohn nach eigenen Stunden).
    # EP auf Cent gerundet, GP = EP x Menge - so rechnet auch der Auftraggeber aus der GAEB-Datei.
    menge_je_nr = {str(pos.get("pos_nr", "")): float(pos.get("menge", 0)) for pos in positionen}
    pos_preise: dict[str, dict] = {}
    for pp in zuschlaege.get("positionen_preise", []):
        nr = pp["pos_nr"]
        menge = menge_je_nr.get(nr, 1) or 1
        ep = round(pp["angebotspreis"] / menge, 2)
        pos_preise[nr] = {**pp, "einheitspreis": ep, "gesamtpreis": round(ep * menge, 2)}

    # Angebotssumme = Summe der Positionen (Rundung je Position kann wenige Cent abweichen)
    if pos_preise:
        summe_gp = round(sum(pp["gesamtpreis"] for pp in pos_preise.values()), 2)
        differenz = summe_gp - zuschlaege.get("angebotspreis_gesamt", 0)
        zuschlaege["angebotspreis_gesamt"] = summe_gp
        marge = zuschlaege.setdefault("marge", {"absolut": 0, "prozent": 0})
        marge["absolut"] = round(marge.get("absolut", 0) + differenz, 2)
        marge["prozent"] = round(marge["absolut"] / summe_gp * 100, 1) if summe_gp else 0
        p["gesamtpreis"] = summe_gp

    # Export-Cache mit den Positionspreisen fuellen (PDF/GAEB lesen EP/GP aus dem Cache)
    for pos in p.get("positionen", []):
        preis = pos_preise.get(str(pos.get("pos_nr", "")))
        if preis:
            pos.update({k: preis[k] for k in (
                "einheitspreis", "gesamtpreis", "materialkosten", "maschinenkosten",
                "lohnkosten", "fremdleistungskosten",
            )})
    from api.routes.export import cache_kalkulation
    cache_kalkulation(projekt_id, p)

    async with get_db() as db:
        # Projekt aktualisieren
        await db.execute(
            """UPDATE projekte SET
                angebotspreis = ?, herstellkosten = ?, marge_prozent = ?,
                status = 'kalkuliert', aktualisiert_am = ?
               WHERE id = ?""",
            (
                zuschlaege.get("angebotspreis_gesamt", 0),
                zuschlaege.get("herstellkosten", 0),
                zuschlaege.get("marge", {}).get("prozent", 0),
                datetime.now().isoformat(),
                projekt_id,
            ),
        )

        # Einzelne Positionen: Kosten (Herstellkosten-Anteile) + Angebotspreise EP/GP
        for pos_nr, preis in pos_preise.items():
            await db.execute(
                """UPDATE positionen SET
                    materialkosten = ?, maschinenkosten = ?, lohnkosten = ?,
                    fremdleistungskosten = ?, einheitspreis = ?, gesamtpreis = ?
                   WHERE projekt_id = ? AND pos_nr = ?""",
                (preis["materialkosten"], preis["maschinenkosten"], round(preis["lohnkosten"], 2),
                 preis["fremdleistungskosten"], preis["einheitspreis"], preis["gesamtpreis"],
                 projekt_id, pos_nr),
            )

        # Korpus-Positionen: Stueckliste als Werkstuecke ins Projekt (ersetzt die vorherige)
        from api.routes.positionen import schreibe_korpus_werkstuecke
        position_id_je_nr = {str(pos["pos_nr"]): pos["id"] for pos in positionen}
        for stueckliste in p.get("korpus_stuecklisten", []):
            position_id = position_id_je_nr.get(str(stueckliste["pos_nr"]))
            if position_id is not None:
                await schreibe_korpus_werkstuecke(db, projekt_id, position_id, stueckliste)

        await db.commit()

    return KalkulationErgebnis(
        projekt_id=projekt_id,
        projekt_typ=p.get("projekt_typ", "standard"),
        herstellkosten=zuschlaege.get("herstellkosten", 0),
        materialkosten=zuschlaege.get("materialkosten", 0),
        maschinenkosten=zuschlaege.get("maschinenkosten", 0),
        lohnkosten=zuschlaege.get("lohnkosten", 0),
        gemeinkosten=zuschlaege.get("gemeinkosten", {}).get("betrag", 0),
        selbstkosten=zuschlaege.get("selbstkosten", 0),
        gewinn=zuschlaege.get("gewinn", {}).get("betrag", 0),
        wagnis=zuschlaege.get("wagnis", {}).get("betrag", 0),
        montage_zuschlag=zuschlaege.get("montage_zuschlag", {}).get("betrag", 0),
        fremdleistungskosten=zuschlaege.get("fremdleistungen", {}).get("kosten", 0),
        fremdleistungszuschlag=zuschlaege.get("fremdleistungen", {}).get("zuschlag", 0),
        angebotspreis=zuschlaege.get("angebotspreis_gesamt", 0),
        marge_prozent=zuschlaege.get("marge", {}).get("prozent", 0),
        warnungen=p.get("warnungen", []),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_dokument(
    datei: UploadFile = File(...),
    projekt_id: str = Form(""),
):
    """Lädt ein Ausschreibungsdokument hoch und parst es.

    Unterstützte Formate: GAEB (.d83, .x83, .x84), PDF, Excel (.xlsx)
    """
    if not datei.filename:
        raise HTTPException(status_code=400, detail="Kein Dateiname")

    # Datei temporär speichern
    import os
    import tempfile
    from pathlib import Path

    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

    suffix = Path(datei.filename).suffix
    content = await datei.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Datei zu gross (max. 50 MB)")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Parser ausführen
        if _pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="Kalkulations-Pipeline nicht initialisiert",
            )

        from agents.base_agent import AgentMessage

        if not projekt_id:
            projekt_id = f"PRJ-{uuid.uuid4().hex[:8].upper()}"

        message = AgentMessage(
            sender="api",
            receiver="dokument_parser",
            msg_type="parse_dokument",
            payload={"datei_pfad": tmp_path},
            projekt_id=projekt_id,
        )

        parser = _pipeline.subagenten.get("dokument_parser")
        if parser is None:
            raise HTTPException(status_code=503, detail="Dokument-Parser nicht verfügbar")

        result = await parser.execute(message)

        if result.msg_type == "error":
            raise HTTPException(status_code=500, detail=result.payload.get("error", "Parse-Fehler"))
    finally:
        os.unlink(tmp_path)

    return UploadResponse(
        datei_name=datei.filename,
        datei_typ=suffix.lstrip("."),
        positionen_anzahl=result.payload.get("anzahl_positionen", 0),
        positionen=result.payload.get("positionen", []),
        warnungen=[],
    )
