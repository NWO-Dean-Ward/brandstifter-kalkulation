"""
Phase 1 Validierung – Tech-Stack, DB-Schema, Config-Loader, API-Imports.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports_agenten():
    """Alle Agenten-Module importierbar."""
    from agents.base_agent import BaseAgent, AgentMessage, AgentStatus
    from agents.lead_agent import LeadAgent
    from agents.dokument_parser import DokumentParser
    from agents.material_kalkulator import MaterialKalkulator
    from agents.maschinen_kalkulator import MaschinenKalkulator
    from agents.lohn_kalkulator import LohnKalkulator
    from agents.zuschlag_kalkulator import ZuschlagKalkulator
    from agents.export_agent import ExportAgent
    from agents.lern_agent import LernAgent
    assert True


def test_imports_api():
    """Alle API-Module importierbar."""
    from api.database import init_db_sync, SCHEMA_SQL
    from api.config_loader import AppConfig
    from api.models.schemas import ProjektCreate, KalkulationErgebnis
    assert True


def test_config_loader():
    """Config-Loader lädt YAML-Dateien korrekt."""
    from api.config_loader import AppConfig
    config = AppConfig(config_dir=Path(__file__).parent.parent / "config")

    assert config.maschinen["holzher_nextec_7707"]["stundensatz_eur"] == 85.0
    assert config.zuschlaege["gemeinkosten_gkz"] == 0.25
    assert config.stundensaetze["einheitlicher_stundensatz"] == 58.0
    assert config.stundensaetze["monteure_anzahl"] == 7


def test_db_schema_sync():
    """Datenbank lässt sich synchron initialisieren."""
    import tempfile
    from api.database import init_db_sync

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        init_db_sync(db_path)
        assert db_path.exists()
        assert db_path.stat().st_size > 0

        # Tabellen prüfen
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tabellen = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "projekte" in tabellen
        assert "positionen" in tabellen
        assert "materialpreise" in tabellen
        assert "maschineneinsaetze" in tabellen
        assert "lernhistorie" in tabellen
        assert "konfiguration_log" in tabellen


def test_pipeline_init():
    """Agenten-Pipeline lässt sich vollständig initialisieren."""
    from api.config_loader import AppConfig
    from agents.lead_agent import LeadAgent
    from agents.dokument_parser import DokumentParser
    from agents.material_kalkulator import MaterialKalkulator
    from agents.maschinen_kalkulator import MaschinenKalkulator
    from agents.lohn_kalkulator import LohnKalkulator
    from agents.zuschlag_kalkulator import ZuschlagKalkulator
    from agents.export_agent import ExportAgent
    from agents.lern_agent import LernAgent

    config = AppConfig(config_dir=Path(__file__).parent.parent / "config")

    lead = LeadAgent()
    maschinen = MaschinenKalkulator()
    maschinen.load_config(config.maschinen)

    lohn = LohnKalkulator()
    lohn.load_config(config.stundensaetze)

    zuschlag = ZuschlagKalkulator()
    zuschlag.load_config(config.zuschlaege)

    for agent in [DokumentParser(), MaterialKalkulator(), maschinen, lohn, zuschlag, ExportAgent(), LernAgent()]:
        lead.register_subagent(agent)

    assert len(lead.subagenten) == 7
    assert "dokument_parser" in lead.subagenten
    assert "material_kalkulator" in lead.subagenten
    assert "maschinen_kalkulator" in lead.subagenten
    assert "lohn_kalkulator" in lead.subagenten
    assert "zuschlag_kalkulator" in lead.subagenten
    assert "export_agent" in lead.subagenten
    assert "lern_agent" in lead.subagenten


def test_agentmessage_protocol():
    """Nachrichten-Protokoll funktioniert end-to-end."""
    from agents.base_agent import AgentMessage

    # Request erstellen
    req = AgentMessage(
        sender="api",
        receiver="lead_agent",
        msg_type="neue_ausschreibung",
        payload={"datei_pfad": "/test.x83"},
        projekt_id="PRJ-TEST001",
    )

    # Response erstellen
    resp = req.create_response(
        sender="lead_agent",
        payload={"positionen": [], "angebotspreis": 12500.0},
    )
    assert resp.correlation_id == req.message_id
    assert resp.receiver == "api"
    assert resp.projekt_id == "PRJ-TEST001"

    # Error erstellen
    err = req.create_error(
        sender="lead_agent",
        error_msg="Datei nicht gefunden",
        details={"pfad": "/test.x83"},
    )
    assert err.msg_type == "error"
    assert "Datei nicht gefunden" in err.payload["error"]


if __name__ == "__main__":
    test_imports_agenten()
    print("OK: Agenten-Imports")
    test_imports_api()
    print("OK: API-Imports")
    test_config_loader()
    print("OK: Config-Loader")
    test_db_schema_sync()
    print("OK: DB-Schema")
    test_pipeline_init()
    print("OK: Pipeline-Init")
    test_agentmessage_protocol()
    print("OK: AgentMessage-Protokoll")
    print("\n>>> Alle Phase-1-Tests bestanden <<<")
