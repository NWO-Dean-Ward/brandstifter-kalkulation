"""
Phase 0 Validierung – Prüft dass die Agenten-Architektur korrekt aufgebaut ist.
"""

import asyncio
import sys
from pathlib import Path

# Projektroot zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import AgentMessage, AgentStatus, BaseAgent
from agents.lead_agent import LeadAgent
from agents.dokument_parser import DokumentParser
from agents.material_kalkulator import MaterialKalkulator
from agents.maschinen_kalkulator import MaschinenKalkulator
from agents.lohn_kalkulator import LohnKalkulator
from agents.zuschlag_kalkulator import ZuschlagKalkulator
from agents.export_agent import ExportAgent
from agents.lern_agent import LernAgent


def test_alle_agenten_instanziierbar():
    """Alle Agenten müssen ohne Fehler instanziiert werden können."""
    lead = LeadAgent()
    assert lead.name == "lead_agent"
    assert lead.status == AgentStatus.IDLE

    parser = DokumentParser()
    assert parser.name == "dokument_parser"

    material = MaterialKalkulator()
    assert material.name == "material_kalkulator"

    maschinen = MaschinenKalkulator()
    assert maschinen.name == "maschinen_kalkulator"

    lohn = LohnKalkulator()
    assert lohn.name == "lohn_kalkulator"

    zuschlag = ZuschlagKalkulator()
    assert zuschlag.name == "zuschlag_kalkulator"

    export = ExportAgent()
    assert export.name == "export_agent"

    lern = LernAgent()
    assert lern.name == "lern_agent"


def test_agent_message_erstellen():
    """AgentMessage muss korrekt erstellt und verknüpft werden können."""
    msg = AgentMessage(
        sender="test",
        receiver="lead_agent",
        msg_type="neue_ausschreibung",
        payload={"datei_pfad": "/test/datei.x83"},
        projekt_id="PRJ-001",
    )
    assert msg.sender == "test"
    assert msg.receiver == "lead_agent"
    assert msg.message_id  # nicht leer
    assert msg.timestamp  # nicht leer

    # Response erstellen
    response = msg.create_response(
        sender="lead_agent",
        payload={"status": "ok"},
    )
    assert response.receiver == "test"
    assert response.correlation_id == msg.message_id

    # Error erstellen
    error = msg.create_error(
        sender="lead_agent",
        error_msg="Datei nicht gefunden",
    )
    assert error.msg_type == "error"
    assert error.payload["error"] == "Datei nicht gefunden"


def test_lead_agent_subagenten_registrierung():
    """LeadAgent muss Subagenten registrieren können."""
    lead = LeadAgent()
    parser = DokumentParser()
    material = MaterialKalkulator()

    lead.register_subagent(parser)
    lead.register_subagent(material)

    assert "dokument_parser" in lead.subagenten
    assert "material_kalkulator" in lead.subagenten
    assert lead.subagenten["dokument_parser"] is parser


def test_agent_reset():
    """Agent-Reset muss Status und Log zurücksetzen."""
    agent = DokumentParser()
    agent.status = AgentStatus.ERROR
    agent._message_log.append(
        AgentMessage(sender="x", receiver="y", msg_type="t", payload={})
    )
    assert len(agent.get_message_log()) == 1

    agent.reset()
    assert agent.status == AgentStatus.IDLE
    assert len(agent.get_message_log()) == 0


def test_config_dateien_vorhanden():
    """Alle Config-Dateien müssen existieren."""
    config_dir = Path(__file__).parent.parent / "config"
    assert (config_dir / "maschinen.yaml").exists()
    assert (config_dir / "zuschlaege.yaml").exists()
    assert (config_dir / "stundensaetze.yaml").exists()


def test_verzeichnisstruktur():
    """Projektstruktur muss vollständig sein."""
    root = Path(__file__).parent.parent
    dirs = ["agents", "api", "api/routes", "api/models", "frontend",
            "config", "data", "data/preislisten", "data/projekte", "exports", "tests"]
    for d in dirs:
        assert (root / d).is_dir(), f"Verzeichnis fehlt: {d}"


if __name__ == "__main__":
    test_alle_agenten_instanziierbar()
    test_agent_message_erstellen()
    test_lead_agent_subagenten_registrierung()
    test_agent_reset()
    test_config_dateien_vorhanden()
    test_verzeichnisstruktur()
    print(">>> Alle Phase-0-Tests bestanden <<<")
