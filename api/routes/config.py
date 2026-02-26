"""
API-Routes für Konfiguration.

Lesen und Schreiben der YAML-Konfigurationsdateien.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/config", tags=["Konfiguration"])

# Referenz auf AppConfig (wird von main.py gesetzt)
_config: Any = None


def set_config(config: Any) -> None:
    global _config
    _config = config


def _get_config():
    if _config is None:
        raise HTTPException(status_code=503, detail="Konfiguration nicht initialisiert")
    return _config


@router.get("/maschinen")
async def get_maschinen() -> dict[str, Any]:
    """Maschinenkonfiguration abrufen."""
    return _get_config().maschinen


@router.put("/maschinen")
async def update_maschinen(data: dict[str, Any]) -> dict[str, Any]:
    """Maschinenkonfiguration aktualisieren."""
    _get_config().update_maschinen(data)
    return _get_config().maschinen


@router.get("/zuschlaege")
async def get_zuschlaege() -> dict[str, Any]:
    """Zuschlagskonfiguration abrufen."""
    return _get_config().zuschlaege


@router.put("/zuschlaege")
async def update_zuschlaege(data: dict[str, Any]) -> dict[str, Any]:
    """Zuschlagskonfiguration aktualisieren."""
    _get_config().update_zuschlaege(data)
    return _get_config().zuschlaege


@router.get("/stundensaetze")
async def get_stundensaetze() -> dict[str, Any]:
    """Stundensätze abrufen."""
    return _get_config().stundensaetze


@router.put("/stundensaetze")
async def update_stundensaetze(data: dict[str, Any]) -> dict[str, Any]:
    """Stundensätze aktualisieren."""
    _get_config().update_stundensaetze(data)
    return _get_config().stundensaetze
