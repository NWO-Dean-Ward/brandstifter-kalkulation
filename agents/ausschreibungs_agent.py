"""
AusschreibungsAgent - Monitoring oeffentlicher Ausschreibungen.

Durchsucht zwei Quellen nach Bekanntmachungen, die zum Leistungsprofil
von AMP & Brandstifter passen:

  HAD  Hessische Ausschreibungsdatenbank (www.had.de). Nach dem Hessischen
       Vergabe- und Tariftreuegesetz muessen alle hessischen Bekanntmachungen
       dort veroeffentlicht werden, national und EU-weit. Fuer Hessen ist das
       damit die Vollmenge, nicht nur ein Ausschnitt. Zugriff ohne Login ueber
       das POST-Formular der erweiterten Suche.

  TED  Tenders Electronic Daily (api.ted.europa.eu/v3). EU-weite Bekannt-
       machungen oberhalb der Schwellenwerte, anonym abfragbar. Ergaenzt HAD
       um Vergaben ausserhalb Hessens.

Das eigentliche Problem ist nicht die Beschaffung, sondern die Menge: allein
fuer PLZ 60000-65999 erscheinen rund 1100 Bekanntmachungen in 30 Tagen. Der
Agent bewertet deshalb jede Bekanntmachung gegen ein konfigurierbares
Leistungsprofil (config/ausschreibungen.yaml) und reicht nur die Kandidaten
oberhalb der Schwelle weiter.

Der Agent entscheidet nichts und bewirbt sich auf nichts. Er sammelt, bewertet
und legt vor. Die Auswahl trifft Dean.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from agents.base_agent import AgentMessage, BaseAgent

logger = logging.getLogger(__name__)

CONFIG_PFAD = Path("config/ausschreibungen.yaml")
DB_PFAD = "data/kalkulation.db"

# Browser-Kennung: HAD liefert ohne plausiblen User-Agent teils leere Seiten aus.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_UMLAUTE = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
}

_DATUM_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
# Kein \b verwenden: im HAD-HTML klebt die PLZ direkt am Firmennamen
# ("... GmbH60329 Frankfurt"), dort gibt es keine Wortgrenze.
_PLZ_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")


def normalisiere(text: str) -> str:
    """Kleinschreibung + Umlaut-Aufloesung, damit 'Moebel' und 'Möbel' gleich zaehlen."""
    text = (text or "").lower()
    for zeichen, ersatz in _UMLAUTE.items():
        text = text.replace(zeichen.lower(), ersatz)
    return text


def _zellentext(element) -> str:
    """Text einer Tabellenzelle mit Wortgrenzen an <br>.

    text_content() klebt durch <br> getrennte Zeilen zusammen
    ("EinbaumoebelDer Main-Taunus-Kreis"). Das Zusammenfuegen der einzelnen
    Textknoten mit Leerzeichen erhaelt die Wortgrenze.
    """
    return " ".join(" ".join(element.xpath(".//text()")).split())


def _entdoppele(text: str) -> str:
    """Entfernt wortgleiche Wiederholungen ("Hattersheim Hattersheim").

    HAD gibt den Leistungsort fuer Bildschirm- und Druckansicht doppelt aus,
    TED liefert NUTS-Codes mehrfach je Los.
    """
    text = (text or "").strip()
    if not text:
        return ""
    # Exakte Haelften-Wiederholung: "A B A B" -> "A B"
    woerter = text.split()
    haelfte = len(woerter) // 2
    if haelfte and woerter[:haelfte] == woerter[haelfte:]:
        woerter = woerter[:haelfte]
    # Kommagetrennte Wiederholungen entdoppeln, Reihenfolge erhalten
    roh = " ".join(woerter)
    if "," in roh:
        gesehen, teile = set(), []
        for teil in (t.strip() for t in roh.split(",")):
            if teil and teil not in gesehen:
                gesehen.add(teil)
                teile.append(teil)
        return ", ".join(teile)
    return roh


def _parse_datum(text: str) -> str:
    """Extrahiert das erste TT.MM.JJJJ und gibt es als ISO-Datum zurueck."""
    treffer = _DATUM_RE.search(text or "")
    if not treffer:
        return ""
    try:
        return datetime.strptime(treffer.group(1), "%d.%m.%Y").date().isoformat()
    except ValueError:
        return ""


class AusschreibungsAgent(BaseAgent):
    """Sucht, bewertet und verwaltet oeffentliche Ausschreibungen."""

    def __init__(self, llm_router=None):
        super().__init__("ausschreibungs_agent")
        self.llm_router = llm_router
        self.db_pfad = DB_PFAD
        self.config: dict[str, Any] = {}
        self._config_geladen = False

    # ------------------------------------------------------------------
    # Konfiguration
    # ------------------------------------------------------------------

    def configure(self, db_pfad: str = DB_PFAD, config_pfad: Path | str | None = None) -> None:
        self.db_pfad = db_pfad
        pfad = Path(config_pfad) if config_pfad else CONFIG_PFAD
        if pfad.exists():
            with open(pfad, encoding="utf-8") as fh:
                self.config = yaml.safe_load(fh) or {}
            self._config_geladen = True
            logger.info("Leistungsprofil geladen: %s", pfad)
        else:
            logger.warning("Leistungsprofil nicht gefunden: %s - nutze Defaults", pfad)
            self.config = {}
            self._config_geladen = False

    def _cfg(self, *pfad: str, default: Any = None) -> Any:
        knoten: Any = self.config
        for teil in pfad:
            if not isinstance(knoten, dict) or teil not in knoten:
                return default
            knoten = knoten[teil]
        return knoten

    # ------------------------------------------------------------------
    # Nachrichten-Dispatch
    # ------------------------------------------------------------------

    async def process(self, message: AgentMessage) -> AgentMessage:
        if not self._config_geladen:
            self.configure(self.db_pfad)

        typ = message.msg_type
        payload = message.payload or {}

        if typ == "scan":
            ergebnis = await self._scan(payload)
        elif typ == "liste":
            ergebnis = await self._liste(payload)
        elif typ == "status_setzen":
            ergebnis = await self._status_setzen(payload)
        elif typ == "briefing":
            ergebnis = await self._briefing(payload)
        else:
            return message.create_error(
                self.name,
                f"Unbekannter Nachrichtentyp: {typ}",
                {"unterstuetzt": ["scan", "liste", "status_setzen", "briefing"]},
            )

        return message.create_response(self.name, ergebnis)

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    async def _scan(self, payload: dict) -> dict:
        """Durchsucht die aktivierten Quellen und legt neue Treffer in der DB ab."""
        quellen = payload.get("quellen") or ["had", "ted"]
        gefunden: list[dict] = []
        fehler: list[dict] = []

        if "had" in quellen and self._cfg("quellen", "had", "aktiv", default=True):
            try:
                gefunden.extend(await self._scan_had(payload))
            except Exception as exc:
                logger.warning("HAD-Scan fehlgeschlagen: %s", exc)
                fehler.append({"quelle": "had", "fehler": str(exc)})

        if "ted" in quellen and self._cfg("quellen", "ted", "aktiv", default=True):
            try:
                gefunden.extend(await self._scan_ted(payload))
            except Exception as exc:
                logger.warning("TED-Scan fehlgeschlagen: %s", exc)
                fehler.append({"quelle": "ted", "fehler": str(exc)})

        # Bewerten
        for eintrag in gefunden:
            score, begruendung = self.bewerte(eintrag)
            eintrag["score"] = score
            eintrag["score_begruendung"] = begruendung

        # Harte Filter
        vor_filter = len(gefunden)
        gefunden = [e for e in gefunden if self._passiert_filter(e)]

        # LLM-Zweitmeinung nur fuer den engeren Kreis (Kostenbremse)
        min_llm = int(self._cfg("schwellen", "llm_pruefung_min_score", default=6))
        max_llm = int(self._cfg("schwellen", "llm_max_kandidaten", default=25))
        kandidaten = sorted(
            [e for e in gefunden if e["score"] >= min_llm],
            key=lambda e: e["score"], reverse=True,
        )[:max_llm]
        if kandidaten and self.llm_router:
            await self._llm_zweitmeinung(kandidaten)

        neu, aktualisiert = await self._speichern(gefunden)

        briefing_schwelle = int(self._cfg("schwellen", "briefing_min_score", default=12))
        return {
            "status": "ok",
            "quellen": quellen,
            "roh_gefunden": vor_filter,
            "nach_filter": len(gefunden),
            "neu": neu,
            "aktualisiert": aktualisiert,
            "kandidaten_llm": len(kandidaten),
            "ueber_briefing_schwelle": sum(1 for e in gefunden if e["score"] >= briefing_schwelle),
            "fehler": fehler,
        }

    # ------------------------------------------------------------------
    # Quelle: HAD
    # ------------------------------------------------------------------

    async def _scan_had(self, payload: dict) -> list[dict]:
        """Fragt die HAD-Suchmaske je PLZ-Bereich ab (ein Bereich pro Abfrage)."""
        import httpx

        url = self._cfg("quellen", "had", "basis_url",
                        default="https://www.had.de/onlinesuche_erweitert.html")
        tage = int(payload.get("zeitraum_tage")
                   or self._cfg("quellen", "had", "zeitraum_tage", default=14))
        max_treffer = int(self._cfg("quellen", "had", "max_treffer", default=500))
        bereiche = payload.get("plz_bereiche") or self._cfg(
            "quellen", "had", "plz_bereiche",
            default=[{"von": "60000", "bis": "65999", "name": "Rhein-Main"}],
        )

        treffer: list[dict] = []
        headers = {"User-Agent": _USER_AGENT, "Referer": url}

        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True, headers=headers) as client:
            # Session-Cookie holen; ohne ihn liefert das Formular nur sich selbst zurueck.
            await client.get(url)

            for bereich in bereiche:
                daten = {
                    "TYPE": "013",           # erweiterte Suche, aktuelle Bekanntmachungen
                    "L_CAT": "SQL0",         # Bekanntmachung/Vorinformation/vergebene Auftraege
                    "A_NAME": "",
                    "PLZ_VON_A": "",
                    "PLZ_BIS_A": "",
                    "V_LOC": "",
                    "PLZ_VON": str(bereich.get("von", "")),
                    "PLZ_BIS": str(bereich.get("bis", "")),
                    "DELIV": "",
                    "DDAYS": str(tage),
                    "CNT": str(max_treffer),
                    "CMD": "SE",             # Suche ausfuehren
                }
                antwort = await client.post(url, data=daten)
                antwort.raise_for_status()
                zeilen = self.parse_had_html(antwort.content)
                for zeile in zeilen:
                    zeile["plz_bereich"] = bereich.get("name", "")
                treffer.extend(zeilen)
                logger.info(
                    "HAD %s (%s-%s): %d Bekanntmachungen",
                    bereich.get("name", ""), bereich.get("von"), bereich.get("bis"), len(zeilen),
                )

        return self._dedupliziere(treffer)

    @staticmethod
    def parse_had_html(rohdaten: bytes) -> list[dict]:
        """Zerlegt eine HAD-Ergebnisseite in strukturierte Eintraege.

        Die Seite ist cp1252-kodiert und enthaelt verschachtelte Tabellen, daher
        lxml statt Regex. Jede Ergebniszeile traegt CLI_ID/REC_ID als stabile
        Kennung in versteckten Formularfeldern.
        """
        import lxml.html

        parser = lxml.html.HTMLParser(encoding="cp1252")
        doc = lxml.html.document_fromstring(rohdaten, parser=parser)
        zeilen = doc.xpath(
            "//tr[contains(@class,'searchlistgreyrow') or contains(@class,'searchlistwhiterow')]"
        )

        eintraege: list[dict] = []
        for tr in zeilen:
            tds = tr.xpath("./td")
            if len(tds) < 5:
                continue

            cli = tr.xpath(".//input[@name='CLI_ID']/@value")
            rec = tr.xpath(".//input[@name='REC_ID']/@value")
            if not cli or not rec:
                continue
            externe_id = f"{cli[0]}/{rec[0]}"

            # Zelle 1: Verfahren (div.small), dahinter Auftragsart und Beschreibung.
            leistung_td = tds[1]
            verfahren_el = leistung_td.xpath(".//div[@class='small']")
            verfahren = _zellentext(verfahren_el[0]) if verfahren_el else ""

            # Volltext steht im ausklappbaren span#contractdetails, sonst der Kurztext.
            volltext_el = leistung_td.xpath(".//span[@id='contractdetails']")
            if volltext_el:
                beschreibung = _zellentext(volltext_el[0])
            else:
                beschreibung = _zellentext(leistung_td)
            # Auftragsart = erste Zeile nach dem <hr>
            ganzer_text = _zellentext(leistung_td)
            art = ""
            if verfahren and ganzer_text.startswith(verfahren):
                rest = ganzer_text[len(verfahren):].strip()
                art = rest.split(" ", 1)[0] if rest else ""

            # Zelle 2: veroeffentlicht / Ablauftermin
            datumstext = _zellentext(tds[2])
            daten = _DATUM_RE.findall(datumstext)
            veroeffentlicht = _parse_datum(daten[0]) if daten else ""
            ablauftermin = _parse_datum(daten[1]) if len(daten) > 1 else ""

            # Zelle 3: Vergabestelle + PLZ Ort (durch <br> getrennt)
            stelle_text = _entdoppele(_zellentext(tds[3]))
            plz_treffer = _PLZ_RE.search(stelle_text)
            if plz_treffer:
                vergabestelle = stelle_text[:plz_treffer.start()].strip()
                stelle_ort = stelle_text[plz_treffer.end():].strip()
                stelle_plz = plz_treffer.group(1)
            else:
                vergabestelle, stelle_ort, stelle_plz = stelle_text, "", ""

            # Zelle 4: Ort der Leistung
            leistungsort = _entdoppele(_zellentext(tds[4]))
            ort_plz = _PLZ_RE.search(leistungsort)

            # Zelle 5: Link zur Vergabeplattform (URL-Parameter enthaelt das Ziel)
            link = ""
            hrefs = tds[5].xpath(".//a/@href") if len(tds) > 5 else []
            if hrefs:
                link = AusschreibungsAgent._entpacke_had_link(hrefs[0])

            titel = beschreibung[:160].strip()
            if len(beschreibung) > 160:
                titel += " ..."

            eintraege.append({
                "quelle": "had",
                "externe_id": externe_id,
                "titel": titel or verfahren or externe_id,
                "verfahren": " ".join(x for x in (verfahren, art) if x).strip(),
                "beschreibung": beschreibung,
                "vergabestelle": vergabestelle,
                "ort": leistungsort or stelle_ort,
                "plz": (ort_plz.group(1) if ort_plz else stelle_plz),
                "veroeffentlicht": veroeffentlicht,
                "ablauftermin": ablauftermin,
                "cpv": "",
                "link": link,
            })

        return eintraege

    @staticmethod
    def _entpacke_had_link(href: str) -> str:
        """HAD verlinkt ueber /onlinesuche_fremdplattform.html?URL=<kodiert>."""
        if not href:
            return ""
        if "URL=" in href:
            query = urlparse(href).query
            ziel = parse_qs(query).get("URL", [""])[0]
            if ziel:
                return unquote(ziel)
        if href.startswith("http"):
            return href
        return f"https://www.had.de{href}"

    # ------------------------------------------------------------------
    # Quelle: TED
    # ------------------------------------------------------------------

    async def _scan_ted(self, payload: dict) -> list[dict]:
        """Fragt die TED-Search-API an (anonymer Zugriff auf veroeffentlichte Notices)."""
        import httpx

        url = self._cfg("quellen", "ted", "basis_url",
                        default="https://api.ted.europa.eu/v3/notices/search")
        cpv = payload.get("cpv_codes") or self._cfg("quellen", "ted", "cpv_codes", default=[])
        nuts = payload.get("nuts_codes") or self._cfg("quellen", "ted", "nuts_codes", default=["DE7"])
        limit = int(self._cfg("quellen", "ted", "max_treffer", default=100))
        if not cpv:
            return []

        # Die TED-API kennt keinen Sortier-Parameter: ohne Datumsfenster liefert
        # sie die aeltesten Treffer zuerst (Bekanntmachungen von 2016 und frueher).
        # Das Fenster ist daher nicht optional, sondern haelt die Treffer aktuell.
        tage = int(payload.get("zeitraum_tage")
                   or self._cfg("quellen", "ted", "zeitraum_tage", default=30))
        ab_datum = (date.today() - timedelta(days=tage)).strftime("%Y%m%d")

        query = f"classification-cpv IN ({' '.join(cpv)})"
        if nuts:
            query += f" AND place-of-performance IN ({' '.join(nuts)})"
        query += f" AND publication-date >= {ab_datum}"

        body = {
            "query": query,
            "fields": [
                "publication-number", "notice-title", "buyer-name",
                "deadline-receipt-tender-date-lot", "publication-date",
                "classification-cpv", "place-of-performance",
            ],
            "limit": limit,
            "page": 1,
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            antwort = await client.post(url, json=body, headers={"User-Agent": _USER_AGENT})
            antwort.raise_for_status()
            daten = antwort.json()

        eintraege: list[dict] = []
        for notice in daten.get("notices", []):
            nummer = notice.get("publication-number", "")
            if not nummer:
                continue
            eintraege.append({
                "quelle": "ted",
                "externe_id": str(nummer),
                "titel": self._ted_text(notice.get("notice-title")),
                "verfahren": "EU-Bekanntmachung (TED)",
                "beschreibung": self._ted_text(notice.get("notice-title")),
                "vergabestelle": self._ted_text(notice.get("buyer-name")),
                "ort": _entdoppele(self._ted_text(notice.get("place-of-performance"))),
                "plz": "",
                "veroeffentlicht": self._ted_datum(notice.get("publication-date")),
                "ablauftermin": self._ted_datum(notice.get("deadline-receipt-tender-date-lot")),
                "cpv": _entdoppele(self._ted_text(notice.get("classification-cpv"))),
                "link": f"https://ted.europa.eu/de/notice/-/detail/{nummer}",
            })
        logger.info("TED: %d Bekanntmachungen ab %s (Gesamtbestand laut API: %s)",
                    len(eintraege), ab_datum, daten.get("totalNoticeCount", "?"))
        return eintraege

    @staticmethod
    def _ted_text(wert: Any) -> str:
        """TED liefert Felder je nach Typ als String, Liste oder Sprach-Dict."""
        if wert is None:
            return ""
        if isinstance(wert, str):
            return wert.strip()
        if isinstance(wert, list):
            return ", ".join(AusschreibungsAgent._ted_text(w) for w in wert if w)
        if isinstance(wert, dict):
            for sprache in ("deu", "ger", "eng", "mul", "MUL"):
                if sprache in wert:
                    return AusschreibungsAgent._ted_text(wert[sprache])
            for w in wert.values():
                text = AusschreibungsAgent._ted_text(w)
                if text:
                    return text
        return str(wert)

    @staticmethod
    def _ted_datum(wert: Any) -> str:
        text = AusschreibungsAgent._ted_text(wert)
        if not text:
            return ""
        treffer = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        return treffer.group(1) if treffer else ""

    # ------------------------------------------------------------------
    # Bewertung
    # ------------------------------------------------------------------

    def bewerte(self, eintrag: dict) -> tuple[int, str]:
        """Bewertet eine Bekanntmachung gegen das Leistungsprofil.

        Titel-Treffer zaehlen doppelt, weil die Leistung dort benannt wird und
        nicht nur beilaeufig im Fliesstext vorkommt.
        """
        titel = normalisiere(eintrag.get("titel", ""))
        volltext = normalisiere(
            " ".join([
                eintrag.get("titel", ""),
                eintrag.get("verfahren", ""),
                eintrag.get("beschreibung", ""),
                eintrag.get("cpv", ""),
            ])
        )

        gewichte = self._cfg("gewichte", default={}) or {}
        g_stark = int(gewichte.get("stark", 10))
        g_mittel = int(gewichte.get("mittel", 5))
        g_schwach = int(gewichte.get("schwach", 2))
        titel_faktor = int(gewichte.get("titel_faktor", 2))
        abzug = int(gewichte.get("ausschluss_abzug", 8))

        score = 0
        gruende: list[str] = []
        hat_starkes = False

        for stufe, gewicht in (("stark", g_stark), ("mittel", g_mittel), ("schwach", g_schwach)):
            begriffe = {normalisiere(b) for b in (self._cfg("schlagworte", stufe, default=[]) or [])}
            for begriff in sorted(begriffe):
                if not begriff or begriff not in volltext:
                    continue
                punkte = gewicht * (titel_faktor if begriff in titel else 1)
                score += punkte
                gruende.append(f"+{punkte} {begriff}")
                if stufe == "stark":
                    hat_starkes = True

        ausschluesse = {normalisiere(b) for b in (self._cfg("ausschluss", default=[]) or [])}
        getroffene_ausschluesse = [b for b in sorted(ausschluesse) if b and b in volltext]
        for begriff in getroffene_ausschluesse:
            score -= abzug
            gruende.append(f"-{abzug} {begriff}")

        # Ausschlussbegriff ohne jedes starke Schlagwort: eindeutig fremdes Gewerk.
        if getroffene_ausschluesse and not hat_starkes:
            score = min(score, 0)
            gruende.append("Fremdgewerk (Ausschluss ohne Kernleistung)")

        return max(score, 0), "; ".join(gruende) if gruende else "keine Treffer im Leistungsprofil"

    def _passiert_filter(self, eintrag: dict) -> bool:
        """Harte Filter: nur laufende Verfahren mit realistischer Restfrist."""
        if not self._cfg("filter", "nur_laufende", default=True):
            return True
        ablauf = eintrag.get("ablauftermin", "")
        if not ablauf:
            return True  # ohne Termin lieber vorlegen als verwerfen
        try:
            ablauf_datum = date.fromisoformat(ablauf)
        except ValueError:
            return True
        min_tage = int(self._cfg("filter", "min_resttage", default=7))
        return ablauf_datum >= date.today() + timedelta(days=min_tage)

    @staticmethod
    def _dedupliziere(eintraege: list[dict]) -> list[dict]:
        """Ueberlappende PLZ-Bereiche koennen dieselbe Bekanntmachung liefern."""
        gesehen: set[tuple[str, str]] = set()
        eindeutig: list[dict] = []
        for eintrag in eintraege:
            schluessel = (eintrag.get("quelle", ""), eintrag.get("externe_id", ""))
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            eindeutig.append(eintrag)
        return eindeutig

    async def _llm_zweitmeinung(self, kandidaten: list[dict]) -> None:
        """Laesst das LLM die Vorauswahl gegenlesen - Ergaenzung, kein Ersatz.

        Die Schlagwort-Bewertung bleibt massgeblich fuer den Score. Das LLM
        liefert nur eine Einschaetzung im Klartext, damit Dean im Briefing
        sieht, warum etwas vorgelegt wurde.
        """
        from agents.llm_router import LLMTask

        for eintrag in kandidaten:
            prompt = (
                "Schreinerei mit eigener Manufaktur in Ober-Moerlen (Hessen), 16 Mitarbeiter. "
                "Leistungen: Einbaumoebel, Kuechen, Ladenbau, Gastro-Ausstattung, Bueromoebel, "
                "Innenausbau. Keine Elektro-, Sanitaer-, Heizungs-, Dach- oder Tiefbauarbeiten.\n\n"
                f"Bekanntmachung:\nVerfahren: {eintrag.get('verfahren','')}\n"
                f"Vergabestelle: {eintrag.get('vergabestelle','')}\n"
                f"Ort: {eintrag.get('ort','')}\n"
                f"Text: {eintrag.get('beschreibung','')[:1500]}\n\n"
                "Antworte in genau zwei Saetzen: Erstens ob die Schreinerei hier als Haupt- oder "
                "Nachunternehmer anbieten kann. Zweitens die konkrete Leistung, um die es geht."
            )
            try:
                antwort = await self.llm_router.generate(
                    prompt=prompt,
                    task=LLMTask.FREITEXT_INTERPRETATION,
                    temperature=0.1,
                    max_tokens=300,
                )
                text = (antwort or {}).get("text", "") if isinstance(antwort, dict) else str(antwort)
                eintrag["llm_bewertung"] = " ".join((text or "").split())[:800]
            except Exception as exc:
                logger.debug("LLM-Bewertung fehlgeschlagen fuer %s: %s",
                             eintrag.get("externe_id"), exc)
                eintrag["llm_bewertung"] = ""

    # ------------------------------------------------------------------
    # Persistenz
    # ------------------------------------------------------------------

    async def _speichern(self, eintraege: list[dict]) -> tuple[int, int]:
        """Legt neue Bekanntmachungen an und aktualisiert bekannte.

        Ein von Dean gesetzter Status (relevant, verworfen, beworben) bleibt
        beim Wiederfinden erhalten - ein erneuter Scan darf eine Entscheidung
        nicht ueberschreiben.
        """
        import aiosqlite

        if not eintraege:
            return 0, 0

        jetzt = datetime.now().isoformat(timespec="seconds")
        neu = aktualisiert = 0

        async with aiosqlite.connect(self.db_pfad) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            for eintrag in eintraege:
                cursor = await db.execute(
                    "SELECT id FROM ausschreibungen WHERE quelle = ? AND externe_id = ?",
                    (eintrag.get("quelle", ""), eintrag.get("externe_id", "")),
                )
                vorhanden = await cursor.fetchone()

                if vorhanden:
                    await db.execute(
                        """UPDATE ausschreibungen
                           SET titel = ?, beschreibung = ?, ablauftermin = ?,
                               score = ?, score_begruendung = ?,
                               llm_bewertung = COALESCE(NULLIF(?, ''), llm_bewertung),
                               gescannt_am = ?
                           WHERE id = ?""",
                        (
                            eintrag.get("titel", ""), eintrag.get("beschreibung", ""),
                            eintrag.get("ablauftermin", ""), eintrag.get("score", 0),
                            eintrag.get("score_begruendung", ""), eintrag.get("llm_bewertung", ""),
                            jetzt, vorhanden["id"],
                        ),
                    )
                    aktualisiert += 1
                else:
                    await db.execute(
                        """INSERT INTO ausschreibungen
                           (quelle, externe_id, titel, verfahren, beschreibung, vergabestelle,
                            ort, plz, veroeffentlicht, ablauftermin, cpv, link, score,
                            score_begruendung, llm_bewertung, status, gescannt_am)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            eintrag.get("quelle", ""), eintrag.get("externe_id", ""),
                            eintrag.get("titel", ""), eintrag.get("verfahren", ""),
                            eintrag.get("beschreibung", ""), eintrag.get("vergabestelle", ""),
                            eintrag.get("ort", ""), eintrag.get("plz", ""),
                            eintrag.get("veroeffentlicht", ""), eintrag.get("ablauftermin", ""),
                            eintrag.get("cpv", ""), eintrag.get("link", ""),
                            eintrag.get("score", 0), eintrag.get("score_begruendung", ""),
                            eintrag.get("llm_bewertung", ""), "neu", jetzt,
                        ),
                    )
                    neu += 1
            await db.commit()

        logger.info("Ausschreibungen gespeichert: %d neu, %d aktualisiert", neu, aktualisiert)
        return neu, aktualisiert

    async def _liste(self, payload: dict) -> dict:
        import aiosqlite

        min_score = int(payload.get("min_score", 0))
        status = payload.get("status", "")
        limit = int(payload.get("limit", 100))

        sql = "SELECT * FROM ausschreibungen WHERE score >= ?"
        params: list[Any] = [min_score]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY score DESC, ablauftermin ASC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_pfad) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            zeilen = await cursor.fetchall()

        return {"status": "ok", "anzahl": len(zeilen), "ausschreibungen": [dict(z) for z in zeilen]}

    async def _status_setzen(self, payload: dict) -> dict:
        """Setzt den Bearbeitungsstatus. Begruendung ist Pflicht beim Verwerfen."""
        import aiosqlite

        eintrag_id = payload.get("id")
        neuer_status = payload.get("status", "")
        notiz = payload.get("notiz", "")

        erlaubt = {"neu", "relevant", "verworfen", "beworben", "gewonnen", "verloren"}
        if neuer_status not in erlaubt:
            return {"status": "fehler", "fehler": f"Status unzulaessig: {neuer_status}",
                    "erlaubt": sorted(erlaubt)}
        if neuer_status == "verworfen" and not notiz.strip():
            return {"status": "fehler",
                    "fehler": "Verwerfen erfordert eine Begruendung (Feld 'notiz')"}

        stempel = datetime.now().isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_pfad) as db:
            cursor = await db.execute(
                """UPDATE ausschreibungen
                   SET status = ?,
                       notizen = TRIM(COALESCE(notizen,'') || ?)
                   WHERE id = ?""",
                (neuer_status, f"\n[{stempel}] {neuer_status}: {notiz}".rstrip(), eintrag_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                return {"status": "fehler", "fehler": f"Ausschreibung {eintrag_id} nicht gefunden"}

        return {"status": "ok", "id": eintrag_id, "neuer_status": neuer_status}

    # ------------------------------------------------------------------
    # Briefing
    # ------------------------------------------------------------------

    async def _briefing(self, payload: dict) -> dict:
        """Erzeugt den Text fuer das Ausschreibungs-Briefing an Dean.

        Bewusst nuechtern: Leistung, Frist, Auftraggeber, Link. Keine Bewertung
        der Gewinnchance - die kennt nur Dean.
        """
        import aiosqlite

        min_score = int(payload.get("min_score")
                        or self._cfg("schwellen", "briefing_min_score", default=12))
        limit = int(payload.get("limit", 15))

        async with aiosqlite.connect(self.db_pfad) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM ausschreibungen
                   WHERE score >= ? AND status = 'neu'
                   ORDER BY score DESC, ablauftermin ASC LIMIT ?""",
                (min_score, limit),
            )
            zeilen = [dict(z) for z in await cursor.fetchall()]

        heute = date.today()
        if not zeilen:
            text = (
                f"Ausschreibungs-Briefing {heute.strftime('%d.%m.%Y')}\n\n"
                "Keine neuen Bekanntmachungen oberhalb der Relevanzschwelle."
            )
            return {"status": "ok", "anzahl": 0, "briefing": text, "ausschreibungen": []}

        bloecke = [
            f"Ausschreibungs-Briefing {heute.strftime('%d.%m.%Y')}",
            "",
            f"{len(zeilen)} Bekanntmachung(en) passen zum Leistungsprofil.",
            "",
        ]
        for i, z in enumerate(zeilen, 1):
            frist = z.get("ablauftermin") or ""
            resttage = ""
            if frist:
                try:
                    resttage = f" ({(date.fromisoformat(frist) - heute).days} Tage)"
                except ValueError:
                    resttage = ""
                frist = date.fromisoformat(frist).strftime("%d.%m.%Y") if resttage else frist

            bloecke.append(f"{i}. {z.get('titel','')}")
            bloecke.append(f"   Auftraggeber: {z.get('vergabestelle','')}")
            bloecke.append(f"   Ort: {z.get('ort','')}")
            bloecke.append(f"   Verfahren: {z.get('verfahren','')}")
            bloecke.append(f"   Frist: {frist or 'nicht angegeben'}{resttage}")
            if z.get("llm_bewertung"):
                bloecke.append(f"   Einschaetzung: {z['llm_bewertung']}")
            if z.get("link"):
                bloecke.append(f"   Unterlagen: {z['link']}")
            bloecke.append(f"   Quelle: {z.get('quelle','').upper()} {z.get('externe_id','')}")
            bloecke.append("")

        bloecke.append(
            "Bewertung nach Schlagwortprofil (config/ausschreibungen.yaml). "
            "Der Agent bewirbt sich auf nichts - Auswahl und Angebot bleiben bei Dean."
        )

        return {
            "status": "ok",
            "anzahl": len(zeilen),
            "briefing": "\n".join(bloecke),
            "ausschreibungen": zeilen,
        }
