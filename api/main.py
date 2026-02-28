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
from api.routes import (
    projekte, kalkulation, config as config_routes, positionen,
    materialpreise, export, lernen, cnc, schreiners_buero,
    werkstuecke, zukaufteile, ueberschreibungen, analyse, einkauf,
    bild_analyse, chat,
)
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
from agents.analyse_agent import AnalyseAgent
from agents.einkaufs_agent import EinkaufsAgent
from agents.bild_analyse_agent import BildAnalyseAgent
from agents.holz_tusche_agent import HolzTuscheAgent


def _init_pipeline(app_config: AppConfig) -> tuple[LeadAgent, "LLMRouter"]:
    """Initialisiert die Agenten-Pipeline mit allen Subagenten. Gibt (LeadAgent, LLMRouter) zurueck."""
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

    analyse = AnalyseAgent()
    analyse.configure()

    # LLM-Router fuer Vision + KI-Preisschaetzung (API-Key aus .env oder Umgebungsvariable)
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")

    from agents.llm_router import LLMRouter
    llm_router = LLMRouter(claude_api_key=claude_key)

    einkauf_agent = EinkaufsAgent(llm_router=llm_router)
    einkauf_agent.configure(db_pfad="data/kalkulation.db")

    bild_agent = BildAnalyseAgent(llm_router=llm_router)

    # Holz-Tusche Agent (B2B-Plattenpreise)
    holz_tusche_agent = HolzTuscheAgent()
    logins = app_config.get_partner_logins()
    holz_tusche_agent.configure(
        db_pfad="data/kalkulation.db",
        logins=logins.get("holz_tusche", {}),
    )

    # Beim Lead-Agent registrieren
    for agent in [parser, material, maschinen, lohn, zuschlag, export, lern, cnc_agent, sb_agent, analyse, einkauf_agent, bild_agent, holz_tusche_agent]:
        lead.register_subagent(agent)

    return lead, llm_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown: DB und Pipeline initialisieren."""
    # Startup
    await init_db()

    app_config = AppConfig()
    pipeline, llm_router = _init_pipeline(app_config)

    # Chat-Dependencies setzen
    lern_agent = pipeline.subagenten.get("lern_agent")
    chat.set_chat_dependencies(llm_router, lern_agent, db_pfad="data/kalkulation.db")

    # Config und Pipeline an Routes übergeben
    kalkulation.set_pipeline(pipeline)
    projekte.set_pipeline(pipeline)
    export.set_pipeline(pipeline)
    lernen.set_pipeline(pipeline)
    cnc.set_cnc_agent(pipeline.subagenten.get("cnc_integration"))
    schreiners_buero.set_sb_agent(pipeline.subagenten.get("schreiners_buero"))
    analyse.set_pipeline(pipeline)
    einkauf.set_pipeline(pipeline)
    bild_analyse.set_pipeline(pipeline)
    config_routes.set_config(app_config)

    yield

    # Shutdown (cleanup falls nötig)


app = FastAPI(
    title="Brandstifter Kalkulationstool",
    description="Ausschreibungs- & Kalkulationssoftware für AMP & Brandstifter GmbH",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS fuer LAN-Zugriff (192.168.51.x Subnetz + localhost fuer Entwicklung)
_CORS_ORIGINS = [
    "http://localhost:5173",        # Vite Dev Server
    "http://localhost:3000",        # React Prod lokal
    "http://localhost:8080",        # API direkt
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
]
# LAN-Rechner im 192.168.51.x Subnetz dynamisch erlauben
for _i in range(1, 255):
    _CORS_ORIGINS.append(f"http://192.168.51.{_i}")
    _CORS_ORIGINS.append(f"http://192.168.51.{_i}:5173")
    _CORS_ORIGINS.append(f"http://192.168.51.{_i}:8080")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
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
app.include_router(werkstuecke.router)
app.include_router(zukaufteile.router)
app.include_router(ueberschreibungen.router)
app.include_router(analyse.router)
app.include_router(einkauf.router)
app.include_router(bild_analyse.router)
app.include_router(chat.router)


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
