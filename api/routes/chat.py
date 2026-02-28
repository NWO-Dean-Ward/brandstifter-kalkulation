"""
Chat-Route -- Persistenter KI-Chat fuer Kalkulationsbesprechung.

Endpoints:
- POST /api/chat/message  -- Chat-Nachricht verarbeiten (Ollama default, Claude bei Keywords)
- POST /api/chat/auto-vorschlag -- Automatischer Preisvorschlag nach SmartWOP-Import
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("chat")

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Dependencies (gesetzt via set_chat_dependencies)
_llm_router = None
_lern_agent = None
_db_pfad = "data/kalkulation.db"

# Keywords die Claude-Escalation ausloesen
CLAUDE_KEYWORDS = {"analyse", "vergleich", "vergleiche", "erklaer", "erklaere",
                   "warum", "optimier", "optimiere", "strategie", "komplex"}

SYSTEM_PROMPT = """Du bist ein erfahrener Schreinerei-Kalkulationsexperte fuer die Firma Brandstifter GmbH (Ober-Moerlen, Hessen).
Du hilfst bei der Kalkulation von Sonderbauten (Einbauschraenke, Kuechen, Tresen, Wandverkleidungen etc.).

Dein Wissen:
- Egger-Plattenpreise: Spanplatte melaminbeschichtet 16mm ~8-12 EUR/qm, 19mm ~10-15 EUR/qm, MDF ~12-18 EUR/qm
- Multiplexplatten: Birke 18mm ~25-35 EUR/qm, Buche ~30-40 EUR/qm
- Beschlaege: Blum Topfband ~3-5 EUR/Stk, Vollauszug 400mm ~15-25 EUR/Paar, Topfscharniere ~2-4 EUR
- Kanten ABS: 0.5-2 EUR/lfm je nach Staerke
- Lohnsaetze: Werkstatt 75 EUR/h, CNC 160 EUR/h, Montage 65 EUR/h
- Zuschlaege: Kleinteile 10%, Materialmarge 100%, Zukaufmarge 50%

Antworte immer auf Deutsch. Sei praezise und praxisnah.
Wenn du Preise vorschlaegst, formatiere sie als Action-Block:

```actions
[{"type": "set_price", "kategorie": "platten", "bezeichnung": "Materialname", "field": "preisQm", "value": 12.50, "grund": "Egger Spanplatte 19mm Standardpreis"}]
```

Action-Typen:
- set_price: Preis setzen (kategorie: platten/beschlaege/zukaufteile/halbzeuge, field: preisQm/preis, value: Zahl)
- set_hours: Stunden setzen (kategorie: lohn, bezeichnung: Kategoriename, field: stunden, value: Zahl)
- set_zuschlag: Zuschlag setzen (field: kleinteile/margeMaterial/margeZukauf/wug/rabatt, value: Zahl)

Gib Actions NUR wenn der User explizit nach Preisvorschlaegen fragt oder ein Auto-Vorschlag gefordert ist.
WICHTIG: Schreibe IMMER zuerst eine kurze Erklaerung in normalem Text, DANN optional den Actions-Block. Antworte NIEMALS nur mit einem Actions-Block ohne Erklaerung davor.
"""


def set_chat_dependencies(llm_router: Any, lern_agent: Any, db_pfad: str = "data/kalkulation.db") -> None:
    """Setzt die Abhaengigkeiten fuer den Chat (aufgerufen in main.py lifespan)."""
    global _llm_router, _lern_agent, _db_pfad
    _llm_router = llm_router
    _lern_agent = lern_agent
    _db_pfad = db_pfad


class ChatMessage(BaseModel):
    message: str
    context: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)
    force_claude: bool = False


class AutoVorschlagRequest(BaseModel):
    gegenstand: str = ""
    platten: list[dict] = Field(default_factory=list)
    beschlaege: list[dict] = Field(default_factory=list)
    calc_sums: dict = Field(default_factory=dict)


def _extract_actions(text: str) -> tuple[str, list[dict]]:
    """Extrahiert Actions aus ```actions [...] ``` Bloecken in der LLM-Antwort."""
    actions = []
    clean_text = text

    pattern = r"```actions\s*\n?(.*?)\n?```"
    matches = re.findall(pattern, text, re.DOTALL)

    for match in matches:
        try:
            parsed = json.loads(match.strip())
            if isinstance(parsed, list):
                actions.extend(parsed)
            elif isinstance(parsed, dict):
                actions.append(parsed)
        except json.JSONDecodeError:
            logger.warning("Konnte Actions nicht parsen: %s", match[:100])

    # Actions-Block aus dem Text entfernen
    clean_text = re.sub(pattern, "", text, flags=re.DOTALL).strip()

    return clean_text, actions


def _should_use_claude(message: str, force: bool) -> bool:
    """Pruefen ob Claude statt Ollama verwendet werden soll."""
    if force:
        return True
    words = set(message.lower().split())
    return bool(words & CLAUDE_KEYWORDS)


def _build_prompt(message: str, context: dict, history: list[dict]) -> str:
    """Baut den vollstaendigen Prompt aus History + Kontext + Nachricht."""
    parts = []

    # Kompakter Kontext
    if context:
        ctx_lines = []
        if context.get("gegenstand"):
            ctx_lines.append(f"Projekt: {context['gegenstand']}")
        if context.get("kunde"):
            ctx_lines.append(f"Kunde: {context['kunde']}")
        if context.get("items"):
            for item in context["items"][:15]:
                ctx_lines.append(f"- {item.get('kat', '?')}: {item.get('bez', '?')} | Menge: {item.get('menge', 0)} | Preis: {item.get('preis', 0)}")
        if context.get("sums"):
            s = context["sums"]
            ctx_lines.append(f"Summen: Material={s.get('materialRoh', 0):.2f}, Lohn={s.get('sumLohn', 0):.2f}, Selbstkosten={s.get('selbstkosten', 0):.2f}, Gesamt={s.get('gesamt', 0):.2f}, Brutto={s.get('brutto', 0):.2f}")
        if ctx_lines:
            parts.append("=== Aktuelle Kalkulation ===\n" + "\n".join(ctx_lines))

    # Rolling History (max 5)
    for msg in history[-5:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            parts.append(f"User: {content}")
        else:
            parts.append(f"Assistent: {content}")

    parts.append(f"User: {message}")

    return "\n\n".join(parts)


@router.post("/message")
async def chat_message(req: ChatMessage):
    """Chat-Nachricht verarbeiten und Antwort generieren."""
    if not _llm_router:
        return {"text": "Chat-Backend nicht initialisiert. Bitte Server neu starten.", "actions": [], "model_used": "none", "tokens": 0}

    prompt = _build_prompt(req.message, req.context, req.history)
    use_claude = _should_use_claude(req.message, req.force_claude)

    try:
        if use_claude and _llm_router._claude_api_key:
            result = await _llm_router._generate_claude(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.4,
                max_tokens=1500,
            )
        else:
            result = await _llm_router._generate_ollama(
                modell_name="qwen2.5-coder:14b",
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.4,
                max_tokens=1500,
            )

        raw_text = result.get("response", "") or result.get("text", "")
        model_used = result.get("modell", "ollama")
        tokens = result.get("tokens", 0)

        clean_text, actions = _extract_actions(raw_text)

        return {
            "text": clean_text,
            "actions": actions,
            "model_used": model_used,
            "tokens": tokens,
        }

    except Exception as exc:
        logger.error("Chat-Fehler: %s", exc)
        return {
            "text": f"Fehler bei der Verarbeitung: {exc}",
            "actions": [],
            "model_used": "error",
            "tokens": 0,
        }


@router.post("/auto-vorschlag")
async def auto_vorschlag(req: AutoVorschlagRequest):
    """Automatischer Preisvorschlag nach SmartWOP-Import."""
    if not _llm_router:
        return {"text": "Chat-Backend nicht initialisiert.", "actions": [], "model_used": "none", "tokens": 0}

    # Sammle Items ohne Preis
    items_ohne_preis = []
    for p in req.platten:
        bez = p.get("bezeichnung", "").strip()
        preis = float(p.get("preisQm", 0) or 0)
        if bez and preis == 0:
            items_ohne_preis.append(f"Platte: {bez} (Staerke: {p.get('staerke', '?')}, Menge: {p.get('menge', 0)} qm)")

    for b in req.beschlaege:
        bez = b.get("bezeichnung", "").strip()
        preis = float(b.get("preis", 0) or 0)
        if bez and preis == 0:
            items_ohne_preis.append(f"Beschlag: {bez} (Anzahl: {b.get('anzahl', 0)})")

    if not items_ohne_preis:
        return {"text": "Alle importierten Positionen haben bereits Preise.", "actions": [], "model_used": "none", "tokens": 0}

    # DB-Lookup: Echte Holz-Tusche Preise aus materialpreise
    db_actions = []
    items_noch_ohne_preis = []
    try:
        import aiosqlite
        async with aiosqlite.connect(_db_pfad) as db:
            db.row_factory = aiosqlite.Row
            for p in req.platten:
                bez = p.get("bezeichnung", "").strip()
                preis = float(p.get("preisQm", 0) or 0)
                if not bez or preis > 0:
                    continue
                # Suche nach Dekor-Nr oder Bezeichnung in materialpreise
                dekor_match = re.search(r"\b([HWUFS]\d{3,5})\b", bez, re.IGNORECASE)
                suche = dekor_match.group(1).upper() if dekor_match else bez

                cursor = await db.execute(
                    """SELECT material_name, preis, einheit, notizen FROM materialpreise
                       WHERE lieferant = 'holz_tusche' AND gueltig_bis = ''
                       AND (material_name LIKE ? OR artikel_nr LIKE ? OR notizen LIKE ?)
                       ORDER BY gueltig_ab DESC LIMIT 1""",
                    (f"%{suche}%", f"%{suche}%", f"%{suche}%"),
                )
                row = await cursor.fetchone()
                if row:
                    db_actions.append({
                        "type": "set_price",
                        "kategorie": "platten",
                        "bezeichnung": bez,
                        "field": "preisQm",
                        "value": row["preis"],
                        "grund": f"Holz-Tusche B2B-Preis ({row['material_name']})",
                    })
                else:
                    items_noch_ohne_preis.append(f"Platte: {bez} (Staerke: {p.get('staerke', '?')}, Menge: {p.get('menge', 0)} qm)")
    except Exception as exc:
        logger.warning("DB-Preislookup fehlgeschlagen: %s", exc)
        items_noch_ohne_preis = items_ohne_preis

    # Beschlaege ohne Preis (kein DB-Lookup fuer Beschlaege)
    for b in req.beschlaege:
        bez = b.get("bezeichnung", "").strip()
        preis = float(b.get("preis", 0) or 0)
        if bez and preis == 0:
            items_noch_ohne_preis.append(f"Beschlag: {bez} (Anzahl: {b.get('anzahl', 0)})")

    # Wenn alle Preise aus DB gefunden, direkt zurueckgeben
    if db_actions and not items_noch_ohne_preis:
        return {
            "text": f"{len(db_actions)} Preise aus Holz-Tusche Preisliste gefunden und eingesetzt.",
            "actions": db_actions,
            "model_used": "holz_tusche_db",
            "tokens": 0,
        }

    # Fuer Items ohne DB-Preis: LLM als Fallback
    items_ohne_preis = items_noch_ohne_preis if items_noch_ohne_preis else items_ohne_preis

    # Historische Referenz vom LernAgent holen
    referenz_text = ""
    if _lern_agent and req.gegenstand:
        try:
            from agents.base_agent import AgentMessage
            msg = AgentMessage(
                sender="chat", receiver="lern_agent",
                msg_type="vorschlag",
                payload={"kurztext": req.gegenstand, "material": "diverse", "menge": 1},
            )
            result = await _lern_agent.execute(msg)
            if result and result.payload.get("status") == "ok":
                referenz_text = f"\nHistorischer Referenzpreis fuer '{req.gegenstand}': {result.payload.get('vorschlag_preis', 'N/A')} EUR (Konfidenz: {result.payload.get('konfidenz', 'N/A')})"
        except Exception as exc:
            logger.warning("LernAgent-Abfrage fehlgeschlagen: %s", exc)

    prompt = f"""Fuer das Projekt '{req.gegenstand or 'Sonderbau'}' wurden folgende Materialien per SmartWOP-CSV importiert, haben aber noch keine Preise:

{chr(10).join(items_ohne_preis)}
{referenz_text}

Schlage bitte realistische Marktpreise 2026 fuer alle Positionen ohne Preis vor.
Gib die Preise als Actions zurueck."""

    try:
        result = await _llm_router._generate_ollama(
            modell_name="qwen2.5-coder:14b",
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=2000,
        )

        raw_text = result.get("response", "") or result.get("text", "")
        model_used = result.get("modell", "ollama")
        tokens = result.get("tokens", 0)

        clean_text, actions = _extract_actions(raw_text)

        # DB-Preise + LLM-Schaetzungen zusammenfuegen
        alle_actions = db_actions + actions
        if db_actions:
            db_info = f"\n\n{len(db_actions)} Preise aus Holz-Tusche Preisliste, Rest per KI-Schaetzung."
            clean_text = clean_text + db_info

        return {
            "text": clean_text,
            "actions": alle_actions,
            "model_used": model_used,
            "tokens": tokens,
        }

    except Exception as exc:
        logger.error("Auto-Vorschlag Fehler: %s", exc)
        # Bei LLM-Fehler trotzdem DB-Preise zurueckgeben
        if db_actions:
            return {
                "text": f"{len(db_actions)} Preise aus Holz-Tusche Preisliste. LLM-Fallback fehlgeschlagen: {exc}",
                "actions": db_actions,
                "model_used": "holz_tusche_db",
                "tokens": 0,
            }
        return {
            "text": f"Fehler beim Erstellen des Vorschlags: {exc}",
            "actions": [],
            "model_used": "error",
            "tokens": 0,
        }
