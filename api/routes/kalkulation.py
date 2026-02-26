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

    # Ergebnis im Export-Cache speichern
    p = result.payload
    from api.routes.export import cache_kalkulation
    cache_kalkulation(projekt_id, p)

    zuschlaege = p.get("zuschlaege", {})

    # Positionskosten zurueckschreiben
    mat_liste = p.get("materialkosten", {}).get("materialliste", [])
    mas_liste = p.get("maschinenkosten", {}).get("maschineneinsaetze", [])
    fl_liste = p.get("materialkosten", {}).get("fremdleistungen", [])
    lohnkosten_gesamt = p.get("lohnkosten", {}).get("lohnkosten_gesamt", 0)

    # Kosten pro pos_nr zusammenbauen
    pos_kosten: dict[str, dict] = {}
    positionen_raw = p.get("positionen", [])

    for m in mat_liste:
        nr = m.get("pos_nr", "")
        if nr:
            pos_kosten.setdefault(nr, {})["materialkosten"] = m.get("gesamtkosten", 0)
    for m in mas_liste:
        nr = m.get("pos_nr", "")
        if nr:
            pos_kosten.setdefault(nr, {})["maschinenkosten"] = m.get("kosten_gesamt", 0)
    for fl in fl_liste:
        nr = fl.get("pos_nr", "")
        if nr:
            pos_kosten.setdefault(nr, {})["fremdleistungskosten"] = fl.get("geschaetzte_kosten", 0)

    # Lohnkosten proportional aufteilen (Gewerke sind positionsuebergreifend)
    n_pos = len(positionen_raw) or 1
    lohn_pro_pos = lohnkosten_gesamt / n_pos
    for pos in positionen_raw:
        nr = pos.get("pos_nr", "")
        if nr:
            pos_kosten.setdefault(nr, {})["lohnkosten"] = round(lohn_pro_pos, 2)

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

        # Einzelne Positionen mit Kosten aktualisieren
        for pos_nr, kosten in pos_kosten.items():
            mat_k = kosten.get("materialkosten", 0)
            mas_k = kosten.get("maschinenkosten", 0)
            loh_k = kosten.get("lohnkosten", 0)
            fl_k = kosten.get("fremdleistungskosten", 0)
            gesamt = mat_k + mas_k + loh_k + fl_k

            # Menge aus DB fuer EP-Berechnung
            cursor = await db.execute(
                "SELECT menge FROM positionen WHERE projekt_id = ? AND pos_nr = ?",
                (projekt_id, pos_nr),
            )
            row = await cursor.fetchone()
            menge = dict(row)["menge"] if row else 1
            ep = gesamt / menge if menge > 0 else gesamt

            await db.execute(
                """UPDATE positionen SET
                    materialkosten = ?, maschinenkosten = ?, lohnkosten = ?,
                    fremdleistungskosten = ?, einheitspreis = ?, gesamtpreis = ?
                   WHERE projekt_id = ? AND pos_nr = ?""",
                (mat_k, mas_k, loh_k, fl_k, round(ep, 2), round(gesamt, 2),
                 projekt_id, pos_nr),
            )

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
    import tempfile
    from pathlib import Path

    suffix = Path(datei.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await datei.read()
        tmp.write(content)
        tmp_path = tmp.name

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

    return UploadResponse(
        datei_name=datei.filename,
        datei_typ=suffix.lstrip("."),
        positionen_anzahl=result.payload.get("anzahl_positionen", 0),
        positionen=result.payload.get("positionen", []),
        warnungen=[],
    )
