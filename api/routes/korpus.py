"""
API-Routes fuer den Korpus-Generator (parametrische Korpus-Kalkulation).

Liefert Stueckliste, Plattenbedarf, Kanten, Beschlaege und Stunden;
der Kalkulator uebernimmt diese Mengen ueber den Block "kalkulator_import".
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agents.korpus_generator import (
    QUALITAETEN, RUECKWAND_ARTEN, TYPEN,
    KonfigurationsFehler, KorpusParameter, PreisKatalog, berechne_korpus, konfig_wert,
)
from api.config_loader import AppConfig
from api.database import DB_PATH
from api.models.schemas import KorpusRequest

router = APIRouter(prefix="/api/korpus", tags=["Korpus-Generator"])


def lade_kalkulationsbasis() -> tuple[dict[str, Any], dict[str, Any], PreisKatalog]:
    """Konstruktionsregeln, Maschinen-Config und Preis-Katalog (bei jedem Aufruf frisch)."""
    cfg = AppConfig()
    if not cfg.korpus:
        raise HTTPException(status_code=500, detail="config/korpus.yaml fehlt")
    return cfg.korpus, cfg.maschinen, PreisKatalog.aus_db(DB_PATH)


@router.get("/vorlagen")
async def vorlagen():
    """Vorlagen und Standardwerte fuer das Korpus-Formular."""
    regeln, _, _ = lade_kalkulationsbasis()
    try:
        standard = {
            "korpus_staerke_mm": konfig_wert(regeln, "konstruktion.korpus_staerke_mm"),
            "front_staerke_mm": konfig_wert(regeln, "konstruktion.front_staerke_mm"),
            "rueckwand_staerke_mm": konfig_wert(regeln, "konstruktion.rueckwand_staerke_mm"),
            "rueckwand_art": konfig_wert(regeln, "konstruktion.rueckwand_art"),
        }
    except KonfigurationsFehler as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "vorlagen": regeln.get("vorlagen", []),
        "standard": standard,
        "typen": list(TYPEN),
        "rueckwand_arten": list(RUECKWAND_ARTEN),
        "qualitaeten": list(QUALITAETEN),
    }


@router.post("/berechnen")
async def berechnen(data: KorpusRequest):
    """Berechnet Stueckliste, Mengen und Stunden fuer einen Korpus-Typ."""
    regeln, maschinen, katalog = lade_kalkulationsbasis()
    try:
        return berechne_korpus(
            KorpusParameter(**data.model_dump()),
            regeln=regeln, maschinen_cfg=maschinen, katalog=katalog,
        )
    except KonfigurationsFehler as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
