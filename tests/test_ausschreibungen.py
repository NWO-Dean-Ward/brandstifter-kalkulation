"""
Tests fuer den Ausschreibungs-Agent.

Das HAD-Fixture (tests/fixtures/had_suchergebnis.html) ist ein echter
Ausschnitt einer Suchantwort von www.had.de, nicht nachgebaut - damit
Aenderungen am Seitenaufbau hier auffallen und nicht erst im Betrieb.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from agents.ausschreibungs_agent import AusschreibungsAgent, _entdoppele, normalisiere
from agents.base_agent import AgentMessage

FIXTURE = Path(__file__).parent / "fixtures" / "had_suchergebnis.html"
CONFIG = Path(__file__).parent.parent / "config" / "ausschreibungen.yaml"


@pytest.fixture
def agent(tmp_path):
    """Agent mit echter Config, aber eigener Wegwerf-Datenbank."""
    db = tmp_path / "test.db"
    _schema(db)
    a = AusschreibungsAgent()
    a.configure(db_pfad=str(db), config_pfad=CONFIG)
    return a


def _schema(db_pfad: Path) -> None:
    """Legt nur die fuer diese Tests noetige Tabelle an."""
    import re
    schema = (Path(__file__).parent.parent / "api" / "database.py").read_text(encoding="utf-8")
    block = re.search(
        r"(CREATE TABLE IF NOT EXISTS ausschreibungen.*?;.*?idx_ausschreibungen_ablauf[^;]*;)",
        schema, re.S,
    )
    assert block, "Schema fuer 'ausschreibungen' nicht in database.py gefunden"
    con = sqlite3.connect(db_pfad)
    con.executescript(block.group(1))
    con.commit()
    con.close()


# ----------------------------------------------------------------------
# Normalisierung
# ----------------------------------------------------------------------

def test_normalisiere_loest_umlaute_auf():
    assert normalisiere("Möbel") == "moebel"
    assert normalisiere("Küchenzeile") == "kuechenzeile"
    assert normalisiere("MASSGEFERTIGT") == "massgefertigt"
    assert normalisiere("Straße") == "strasse"


def test_normalisiere_vertraegt_leere_eingabe():
    assert normalisiere("") == ""
    assert normalisiere(None) == ""


# ----------------------------------------------------------------------
# HAD-Parser (gegen echtes Fixture)
# ----------------------------------------------------------------------

def test_parser_liest_alle_zeilen():
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    assert len(eintraege) == 2


def test_parser_extrahiert_pflichtfelder():
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    for e in eintraege:
        assert e["quelle"] == "had"
        assert "/" in e["externe_id"]          # CLI_ID/REC_ID
        assert e["titel"]
        assert e["vergabestelle"]


def test_parser_trennt_vergabestelle_von_plz():
    """Vergabestelle und PLZ stehen im HTML ohne Trennzeichen zusammen."""
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    erster = eintraege[0]
    assert erster["vergabestelle"] == "BäderBetriebe Frankfurt GmbH"
    assert "60329" not in erster["vergabestelle"]


def test_parser_liefert_iso_daten():
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    erster = eintraege[0]
    assert erster["veroeffentlicht"] == "2026-09-21"
    assert erster["ablauftermin"] == "2026-10-12"


def test_parser_behaelt_umlaute():
    """cp1252-Dekodierung: falsche Kodierung faellt hier sofort auf."""
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    volltext = " ".join(e["beschreibung"] for e in eintraege)
    assert "Schwimmbäder" in volltext
    assert "�" not in volltext


def test_parser_entpackt_plattform_link():
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    links = [e["link"] for e in eintraege if e["link"]]
    assert links, "mindestens ein Eintrag muss einen Link tragen"
    assert links[0].startswith("https://")
    assert "onlinesuche_fremdplattform" not in links[0]


def test_parser_vertraegt_leere_seite():
    leer = b"<html><body><p>Keine Treffer</p></body></html>"
    assert AusschreibungsAgent.parse_had_html(leer) == []



# ----------------------------------------------------------------------
# Textaufbereitung fuers Briefing
# ----------------------------------------------------------------------

def test_entdoppele_entfernt_wiederholte_haelfte():
    """HAD gibt den Leistungsort fuer Bildschirm und Druck doppelt aus."""
    assert _entdoppele("Schulstraße 100 Hattersheim Schulstraße 100 Hattersheim") == \
        "Schulstraße 100 Hattersheim"


def test_entdoppele_entfernt_wiederholte_nuts_codes():
    """TED liefert place-of-performance je Los erneut."""
    assert _entdoppele("DE722, DEU, DE722, DEU") == "DE722, DEU"


def test_entdoppele_laesst_echte_werte_unveraendert():
    assert _entdoppele("Bad Nauheim") == "Bad Nauheim"
    assert _entdoppele("") == ""
    assert _entdoppele("Frankfurt, Offenbach") == "Frankfurt, Offenbach"


def test_parser_setzt_wortgrenze_an_zeilenumbruch():
    """Ohne Leerzeichen an <br> entstuenden Woerter wie 'EinbaumoebelDer'."""
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    volltext = " ".join(e["beschreibung"] for e in eintraege)
    assert "Stadtgebiet Frankfurt" in volltext, "Zeilenumbruch muss Wortgrenze bleiben"


def test_parser_ort_ist_nicht_gedoppelt():
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    for e in eintraege:
        woerter = e["ort"].split()
        haelfte = len(woerter) // 2
        if haelfte:
            assert woerter[:haelfte] != woerter[haelfte:], f"Ort gedoppelt: {e['ort']}"

# ----------------------------------------------------------------------
# Bewertung
# ----------------------------------------------------------------------

def test_bewertung_kernleistung_schlaegt_briefing_schwelle(agent):
    eintrag = {
        "titel": "Lieferung und Montage von Einbaumöbeln",
        "verfahren": "Öffentliche Ausschreibung VOB/A",
        "beschreibung": "Tischlerarbeiten, Einbaumöbel und Möblierung für den Innenausbau.",
        "cpv": "",
    }
    score, begruendung = agent.bewerte(eintrag)
    schwelle = agent._cfg("schwellen", "briefing_min_score", default=12)
    assert score >= schwelle
    assert "einbaumoebel" in begruendung


def test_bewertung_titel_treffer_zaehlt_doppelt(agent):
    im_titel = {"titel": "Tischlerarbeiten Rathaus", "verfahren": "", "beschreibung": "", "cpv": ""}
    im_text = {"titel": "Rathaus Sanierung", "verfahren": "",
               "beschreibung": "Tischlerarbeiten", "cpv": ""}
    assert agent.bewerte(im_titel)[0] > agent.bewerte(im_text)[0]


def test_bewertung_fremdgewerk_wird_aussortiert(agent):
    """Reale Zeile aus dem HAD-Scan: IT-Leistung, darf nie im Briefing landen."""
    eintrag = {
        "titel": "IT-Service-Integrator für IT-Dienstleister der Landwirtschaftsförderung",
        "verfahren": "Vergabebekanntmachung Dienstleistungen",
        "beschreibung": "Betrieb Rechenzentrum, Netzwerk, DDoS Absicherung, Lizenzen.",
        "cpv": "",
    }
    score, _ = agent.bewerte(eintrag)
    assert score == 0


def test_bewertung_strassenbau_wird_aussortiert(agent):
    eintrag = {
        "titel": "Grundhafte Erneuerung Merschroder Straße",
        "verfahren": "Öffentliche Ausschreibung VOB/A",
        "beschreibung": "Straßenbau, Brückenbauwerk, Kanalbau und Entwässerung.",
        "cpv": "",
    }
    assert agent.bewerte(eintrag)[0] == 0


def test_bewertung_nachunternehmer_fall_bleibt_sichtbar(agent):
    """Innenausbau mit Elektro-Anteil: Kernleistung vorhanden, also nicht wegwerfen."""
    eintrag = {
        "titel": "Innenausbau Mensa mit Einbaumöbeln",
        "verfahren": "Öffentliche Ausschreibung VOB/A",
        "beschreibung": ("Innenausbau, Einbaumöbel und Theke. Elektroinstallation "
                         "wird bauseits gestellt."),
        "cpv": "",
    }
    score, _ = agent.bewerte(eintrag)
    assert score > 0, "Kernleistung darf nicht durch einen Ausschlussbegriff verschwinden"


def test_bewertung_ohne_treffer_ist_null(agent):
    eintrag = {"titel": "Versicherungsleistungen", "verfahren": "",
               "beschreibung": "Haftpflicht für den Fuhrpark.", "cpv": ""}
    assert agent.bewerte(eintrag)[0] == 0


def test_bewertung_liefert_nachvollziehbare_begruendung(agent):
    _, begruendung = agent.bewerte(
        {"titel": "Küche", "verfahren": "", "beschreibung": "Einbauküche", "cpv": ""}
    )
    assert begruendung and begruendung != "keine Treffer im Leistungsprofil"


# ----------------------------------------------------------------------
# Harte Filter
# ----------------------------------------------------------------------

def test_filter_verwirft_abgelaufene_frist(agent):
    gestern = (date.today() - timedelta(days=1)).isoformat()
    assert agent._passiert_filter({"ablauftermin": gestern}) is False


def test_filter_verwirft_zu_kurze_restfrist(agent):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    assert agent._passiert_filter({"ablauftermin": morgen}) is False


def test_filter_laesst_ausreichende_frist_durch(agent):
    spaeter = (date.today() + timedelta(days=30)).isoformat()
    assert agent._passiert_filter({"ablauftermin": spaeter}) is True


def test_filter_behaelt_eintrag_ohne_termin(agent):
    """Ohne Frist lieber vorlegen als verwerfen."""
    assert agent._passiert_filter({"ablauftermin": ""}) is True


# ----------------------------------------------------------------------
# TED-Feldnormalisierung
# ----------------------------------------------------------------------

def test_ted_text_bevorzugt_deutsch():
    assert AusschreibungsAgent._ted_text({"deu": ["Möbel"], "eng": ["Furniture"]}) == "Möbel"


def test_ted_text_vertraegt_alle_formen():
    assert AusschreibungsAgent._ted_text(None) == ""
    assert AusschreibungsAgent._ted_text("Text") == "Text"
    assert AusschreibungsAgent._ted_text(["a", "b"]) == "a, b"


def test_ted_datum_extrahiert_iso():
    assert AusschreibungsAgent._ted_datum("2026-10-12+02:00") == "2026-10-12"
    assert AusschreibungsAgent._ted_datum(None) == ""


# ----------------------------------------------------------------------
# Persistenz
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_speichern_und_listen(agent):
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    for e in eintraege:
        e["score"], e["score_begruendung"] = agent.bewerte(e)

    neu, aktualisiert = await agent._speichern(eintraege)
    assert neu == 2 and aktualisiert == 0

    ergebnis = await agent._liste({"min_score": 0})
    assert ergebnis["anzahl"] == 2


@pytest.mark.asyncio
async def test_erneuter_scan_legt_keine_duplikate_an(agent):
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    for e in eintraege:
        e["score"] = 0
    await agent._speichern(eintraege)
    neu, aktualisiert = await agent._speichern(eintraege)
    assert neu == 0 and aktualisiert == 2


@pytest.mark.asyncio
async def test_erneuter_scan_ueberschreibt_entscheidung_nicht(agent):
    """Kernregel: ein gesetzter Status ueberlebt jeden weiteren Scan."""
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    for e in eintraege:
        e["score"] = 0
    await agent._speichern(eintraege)

    liste = await agent._liste({"min_score": 0})
    eintrag_id = liste["ausschreibungen"][0]["id"]
    await agent._status_setzen({"id": eintrag_id, "status": "beworben", "notiz": "Angebot raus"})

    await agent._speichern(eintraege)

    danach = await agent._liste({"min_score": 0, "status": "beworben"})
    assert danach["anzahl"] == 1


@pytest.mark.asyncio
async def test_verwerfen_erfordert_begruendung(agent):
    eintraege = AusschreibungsAgent.parse_had_html(FIXTURE.read_bytes())
    for e in eintraege:
        e["score"] = 0
    await agent._speichern(eintraege)
    liste = await agent._liste({"min_score": 0})
    eintrag_id = liste["ausschreibungen"][0]["id"]

    ohne = await agent._status_setzen({"id": eintrag_id, "status": "verworfen", "notiz": ""})
    assert ohne["status"] == "fehler"

    mit = await agent._status_setzen({
        "id": eintrag_id, "status": "verworfen", "notiz": "Kapazitaet belegt",
    })
    assert mit["status"] == "ok"


@pytest.mark.asyncio
async def test_unzulaessiger_status_wird_abgelehnt(agent):
    ergebnis = await agent._status_setzen({"id": 1, "status": "vielleicht", "notiz": "x"})
    assert ergebnis["status"] == "fehler"


@pytest.mark.asyncio
async def test_dedupliziert_ueberlappende_plz_bereiche():
    doppelt = [
        {"quelle": "had", "externe_id": "5/1"},
        {"quelle": "had", "externe_id": "5/1"},
        {"quelle": "had", "externe_id": "5/2"},
    ]
    assert len(AusschreibungsAgent._dedupliziere(doppelt)) == 2


# ----------------------------------------------------------------------
# Briefing
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_briefing_bei_leerer_lage(agent):
    ergebnis = await agent._briefing({})
    assert ergebnis["anzahl"] == 0
    assert "Keine neuen Bekanntmachungen" in ergebnis["briefing"]


@pytest.mark.asyncio
async def test_briefing_listet_relevante_mit_frist(agent):
    eintrag = {
        "quelle": "had", "externe_id": "99/1",
        "titel": "Einbaumöbel Verwaltungsgebäude",
        "verfahren": "Öffentliche Ausschreibung VOB/A",
        "beschreibung": "Tischlerarbeiten und Möblierung, Innenausbau.",
        "vergabestelle": "Stadt Bad Nauheim", "ort": "61231 Bad Nauheim", "plz": "61231",
        "veroeffentlicht": date.today().isoformat(),
        "ablauftermin": (date.today() + timedelta(days=30)).isoformat(),
        "cpv": "", "link": "https://example.invalid/vergabe",
    }
    eintrag["score"], eintrag["score_begruendung"] = agent.bewerte(eintrag)
    await agent._speichern([eintrag])

    ergebnis = await agent._briefing({})
    assert ergebnis["anzahl"] == 1
    text = ergebnis["briefing"]
    assert "Stadt Bad Nauheim" in text
    assert "30 Tage" in text
    assert "bewirbt sich auf nichts" in text


@pytest.mark.asyncio
async def test_briefing_ueberspringt_bearbeitete(agent):
    """Was Dean schon entschieden hat, taucht nicht erneut auf."""
    eintrag = {
        "quelle": "had", "externe_id": "99/2", "titel": "Einbaumöbel Schule",
        "verfahren": "", "beschreibung": "Tischlerarbeiten Einbaumöbel Möblierung",
        "vergabestelle": "Kreis", "ort": "Friedberg", "plz": "61169",
        "veroeffentlicht": date.today().isoformat(),
        "ablauftermin": (date.today() + timedelta(days=40)).isoformat(),
        "cpv": "", "link": "",
    }
    eintrag["score"], eintrag["score_begruendung"] = agent.bewerte(eintrag)
    await agent._speichern([eintrag])

    liste = await agent._liste({"min_score": 0})
    await agent._status_setzen({
        "id": liste["ausschreibungen"][0]["id"], "status": "verworfen", "notiz": "zu weit weg",
    })

    assert (await agent._briefing({}))["anzahl"] == 0


# ----------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unbekannter_nachrichtentyp_meldet_fehler(agent):
    msg = AgentMessage(sender="test", receiver="ausschreibungs_agent",
                       msg_type="fliegen", payload={})
    antwort = await agent.execute(msg)
    assert antwort.msg_type == "error"
