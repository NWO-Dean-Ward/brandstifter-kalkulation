"""
FastAPI Hauptserver – Brandstifter Kalkulationstool.

Startet den Server auf Port 8080, initialisiert DB und Agenten-Pipeline.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Projektroot zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import init_db
from api.config_loader import AppConfig
from api.routes import projekte, kalkulation, config as config_routes, positionen, materialpreise, export, lernen, cnc, schreiners_buero
from agents.lead_agent import LeadAgent
from agents.dokument_parser import DokumentParser
from agents.material_kalkulator import MaterialKalkulator
from agents.maschinen_kalkulator import MaschinenKalkulator
from agents.lohn_kalkulator import LohnKalkulator
from agents.zuschlag_kalkulator import ZuschlagKalkulator
from agents.export_agent import ExportAgent
from agents.lern_agent import LernAgent
from agents.cnc_integration import CNCIntegration
from agents.schreiners_buero import SchreinersBueroAgent


def _init_pipeline(app_config: AppConfig) -> LeadAgent:
    """Initialisiert die Agenten-Pipeline mit allen Subagenten."""
    lead = LeadAgent()

    # Subagenten erstellen und konfigurieren
    parser = DokumentParser()

    material = MaterialKalkulator()
    material.configure(db_pfad="data/kalkulation.db")

    maschinen = MaschinenKalkulator()
    maschinen.load_config(app_config.maschinen)

    lohn = LohnKalkulator()
    lohn.load_config(app_config.stundensaetze)

    zuschlag = ZuschlagKalkulator()
    zuschlag.load_config(app_config.zuschlaege)

    sb_config = app_config.schreiners_buero

    export = ExportAgent()
    export.configure(
        export_verzeichnis="exports",
        sb_api_url=sb_config.get("api_url", "http://192.168.51.85/sb/proc/sb.php"),
        sb_api_user=sb_config.get("api_user", ""),
        sb_api_pw=sb_config.get("api_pw", ""),
    )

    lern = LernAgent()
    lern.configure(db_pfad="data/kalkulation.db")

    cnc_agent = CNCIntegration()
    cnc_agent.configure(export_verzeichnis="exports")

    sb_agent = SchreinersBueroAgent()
    sb_agent.configure(sb_config)

    # Beim Lead-Agent registrieren
    for agent in [parser, material, maschinen, lohn, zuschlag, export, lern, cnc_agent, sb_agent]:
        lead.register_subagent(agent)

    return lead


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown: DB und Pipeline initialisieren."""
    # Startup
    await init_db()

    app_config = AppConfig()
    pipeline = _init_pipeline(app_config)

    # Config und Pipeline an Routes übergeben
    kalkulation.set_pipeline(pipeline)
    export.set_pipeline(pipeline)
    lernen.set_pipeline(pipeline)
    cnc.set_cnc_agent(pipeline.subagenten.get("cnc_integration"))
    schreiners_buero.set_sb_agent(pipeline.subagenten.get("schreiners_buero"))
    config_routes.set_config(app_config)

    yield

    # Shutdown (cleanup falls nötig)


app = FastAPI(
    title="Brandstifter Kalkulationstool",
    description="Ausschreibungs- & Kalkulationssoftware für AMP & Brandstifter GmbH",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS für Frontend-Zugriff aus dem lokalen Netzwerk
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Im Produktivbetrieb einschränken auf 192.168.51.x
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-Routes registrieren
app.include_router(projekte.router)
app.include_router(positionen.router)
app.include_router(kalkulation.router)
app.include_router(config_routes.router)
app.include_router(materialpreise.router)
app.include_router(export.router)
app.include_router(lernen.router)
app.include_router(cnc.router)
app.include_router(schreiners_buero.router)


@app.get("/api/health")
async def health_check():
    """Healthcheck-Endpunkt."""
    return {"status": "ok", "service": "brandstifter-kalkulation"}


# Frontend static files (wenn gebaut)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
