"""
API-Routes fuer den Einkaufs-Agent (Preisrecherche).

Stellt Endpunkte fuer Browser-basierte Preisrecherche bereit.
KAUFT NIEMALS AUTOMATISCH EIN - nur Recherche und Vorschlaege.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/einkauf", tags=["Einkauf"])

_pipeline: Any = None


def set_pipeline(pipeline: Any) -> None:
    global _pipeline
    _pipeline = pipeline


def _get_agent():
    if not _pipeline:
        raise HTTPException(status_code=503, detail="Pipeline nicht initialisiert")
    agent = _pipeline.subagenten.get("einkaufs_agent")
    if not agent:
        raise HTTPException(status_code=503, detail="Einkaufs-Agent nicht verfuegbar")
    return agent


@router.post("/recherche")
async def preis_recherche(
    bezeichnung: str = "",
    hersteller: str = "",
    artikel_nr: str = "",
    quellen: str = "google_shopping,amazon",
):
    """Recherchiert Preise fuer ein Produkt bei verschiedenen Quellen."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="einkaufs_agent",
        msg_type="preis_recherche",
        payload={
            "bezeichnung": bezeichnung,
            "hersteller": hersteller,
            "artikel_nr": artikel_nr,
            "quellen": [q.strip() for q in quellen.split(",") if q.strip()],
        },
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/recherche/batch")
async def preis_recherche_batch(
    produkte: list[dict],
    quellen: str = "google_shopping,amazon",
):
    """Recherchiert Preise fuer mehrere Produkte auf einmal."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="einkaufs_agent",
        msg_type="preis_recherche_batch",
        payload={
            "produkte": produkte,
            "quellen": [q.strip() for q in quellen.split(",") if q.strip()],
        },
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/recherche/haefele")
async def suche_haefele(suchbegriff: str = "", artikel_nr: str = ""):
    """Sucht gezielt bei Haefele."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="einkaufs_agent",
        msg_type="haefele_suche",
        payload={"suchbegriff": suchbegriff, "artikel_nr": artikel_nr},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/recherche/amazon")
async def suche_amazon(suchbegriff: str):
    """Sucht gezielt bei Amazon.de."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="einkaufs_agent",
        msg_type="amazon_suche",
        payload={"suchbegriff": suchbegriff},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/recherche/google")
async def suche_google_shopping(suchbegriff: str):
    """Sucht bei Google Shopping."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="einkaufs_agent",
        msg_type="google_shopping",
        payload={"suchbegriff": suchbegriff},
    )
    result = await agent.execute(msg)
    return result.payload


def _get_holz_tusche_agent():
    if not _pipeline:
        raise HTTPException(status_code=503, detail="Pipeline nicht initialisiert")
    agent = _pipeline.subagenten.get("holz_tusche")
    if not agent:
        raise HTTPException(status_code=503, detail="Holz-Tusche Agent nicht verfuegbar")
    return agent


@router.post("/recherche/holz-tusche")
async def suche_holz_tusche(suchbegriff: str = ""):
    """Sucht bei Holz-Tusche (B2B-Holzhandel) nach Plattenwerkstoffen."""
    from agents.base_agent import AgentMessage

    if not suchbegriff:
        raise HTTPException(status_code=400, detail="Suchbegriff erforderlich")

    agent = _get_holz_tusche_agent()
    msg = AgentMessage(
        sender="api", receiver="holz_tusche",
        msg_type="holz_tusche_suche",
        payload={"suchbegriff": suchbegriff},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/sync/holz-tusche")
async def sync_holz_tusche():
    """Komplett-Sync aller Plattenwerkstoffe von Holz-Tusche (~2-5 Min)."""
    from agents.base_agent import AgentMessage

    agent = _get_holz_tusche_agent()
    msg = AgentMessage(
        sender="api", receiver="holz_tusche",
        msg_type="holz_tusche_sync",
        payload={},
    )
    result = await agent.execute(msg)
    return result.payload


@router.post("/speichern/{projekt_id}")
async def ergebnis_speichern(
    projekt_id: str,
    treffer: dict,
    position_id: int | None = None,
    aufschlag_prozent: float = 15.0,
    menge: float = 1,
):
    """Speichert ein Recherche-Ergebnis als Zukaufteil in der DB."""
    from agents.base_agent import AgentMessage

    agent = _get_agent()
    msg = AgentMessage(
        sender="api", receiver="einkaufs_agent",
        msg_type="ergebnis_speichern",
        payload={
            "treffer": treffer,
            "position_id": position_id,
            "aufschlag_prozent": aufschlag_prozent,
            "menge": menge,
        },
        projekt_id=projekt_id,
    )
    result = await agent.execute(msg)
    return result.payload
