"""
LLM-Router -- Routet Anfragen an lokale Ollama-Modelle oder Claude API.

Modelle:
- qwen2.5-coder:14b -> Primaeres Modell: Dokument-Parser, Material-Kalkulator, Export-Agent
- gpt-oss:20b       -> Rechenlogik: Lohn-Kalkulator, Zuschlag-Kalkulator
- deepseek-coder    -> Leichtgewichtiges Backup
- claude (extern)   -> Lead-Agent, Lern-Agent (optional, braucht API-Key)

Ollama-Modellpfad: C:\\Users\\Black\\.ollama\\models
Ollama-API: http://localhost:11434
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger("llm_router")

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODELS_PATH = r"C:\Users\Black\.ollama\models"


class LLMModell(str, Enum):
    """Verfuegbare LLM-Modelle."""
    QWEN_CODER = "qwen2.5-coder:14b"       # Primaer: Parsing, Material, Export
    GPT_OSS = "gpt-oss:20b"                 # Rechenlogik: Lohn, Zuschlag
    DEEPSEEK_CODER = "deepseek-coder"       # Backup
    CLAUDE = "claude"                        # Extern: Lead-Agent, Lern-Agent


class LLMTask(str, Enum):
    """Aufgabentypen fuer automatisches Routing."""
    FREITEXT_INTERPRETATION = "freitext"      # -> qwen-coder
    MATERIAL_SCHAETZUNG = "material"           # -> qwen-coder
    POSITIONS_EXTRAKTION = "extraktion"        # -> qwen-coder
    DATEN_STRUKTURIERUNG = "strukturierung"    # -> qwen-coder
    PLAUSIBILITAET = "plausibilitaet"          # -> gpt-oss
    LOHN_BERECHNUNG = "lohn"                   # -> gpt-oss
    ZUSCHLAG_BERECHNUNG = "zuschlag"           # -> gpt-oss
    LEAD_ORCHESTRIERUNG = "lead"               # -> claude
    LERN_ANALYSE = "lernen"                    # -> claude
    CODE_GENERIERUNG = "code"                  # -> qwen-coder
    EXPORT_FORMATIERUNG = "export"             # -> qwen-coder


# Automatisches Routing: Task -> bevorzugtes Modell (mit Fallbacks)
TASK_ROUTING: dict[LLMTask, list[LLMModell]] = {
    # qwen2.5-coder:14b primaer
    LLMTask.FREITEXT_INTERPRETATION: [LLMModell.QWEN_CODER, LLMModell.GPT_OSS, LLMModell.DEEPSEEK_CODER],
    LLMTask.MATERIAL_SCHAETZUNG: [LLMModell.QWEN_CODER, LLMModell.GPT_OSS, LLMModell.DEEPSEEK_CODER],
    LLMTask.POSITIONS_EXTRAKTION: [LLMModell.QWEN_CODER, LLMModell.DEEPSEEK_CODER, LLMModell.GPT_OSS],
    LLMTask.DATEN_STRUKTURIERUNG: [LLMModell.QWEN_CODER, LLMModell.DEEPSEEK_CODER, LLMModell.GPT_OSS],
    LLMTask.CODE_GENERIERUNG: [LLMModell.QWEN_CODER, LLMModell.DEEPSEEK_CODER],
    LLMTask.EXPORT_FORMATIERUNG: [LLMModell.QWEN_CODER, LLMModell.GPT_OSS],
    # gpt-oss:20b primaer
    LLMTask.PLAUSIBILITAET: [LLMModell.GPT_OSS, LLMModell.QWEN_CODER],
    LLMTask.LOHN_BERECHNUNG: [LLMModell.GPT_OSS, LLMModell.QWEN_CODER],
    LLMTask.ZUSCHLAG_BERECHNUNG: [LLMModell.GPT_OSS, LLMModell.QWEN_CODER],
    # Claude primaer (Fallback auf lokale Modelle)
    LLMTask.LEAD_ORCHESTRIERUNG: [LLMModell.CLAUDE, LLMModell.QWEN_CODER, LLMModell.GPT_OSS],
    LLMTask.LERN_ANALYSE: [LLMModell.CLAUDE, LLMModell.QWEN_CODER, LLMModell.GPT_OSS],
}


class LLMRouter:
    """Routet LLM-Anfragen an das passende lokale oder externe Modell."""

    def __init__(
        self,
        ollama_url: str = OLLAMA_BASE_URL,
        claude_api_key: str = "",
        timeout: float = 120.0,
    ) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._claude_api_key = claude_api_key
        self._timeout = timeout
        self._verfuegbare_modelle: list[str] = []

    async def init(self) -> None:
        """Prueft Ollama-Verbindung und laedt verfuegbare Modelle."""
        self._verfuegbare_modelle = await self._list_ollama_models()
        logger.info(
            "LLM-Router initialisiert: %d Ollama-Modelle verfuegbar: %s",
            len(self._verfuegbare_modelle),
            ", ".join(self._verfuegbare_modelle),
        )

    async def is_available(self) -> bool:
        """Prueft ob Ollama erreichbar ist."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._ollama_url}/")
                return r.status_code == 200
        except Exception:
            return False

    async def _list_ollama_models(self) -> list[str]:
        """Listet alle verfuegbaren Ollama-Modelle."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self._ollama_url}/api/tags")
                if r.status_code == 200:
                    data = r.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("Ollama nicht erreichbar: %s", exc)
        return []

    async def generate(
        self,
        prompt: str,
        task: LLMTask | None = None,
        modell: LLMModell | None = None,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Sendet eine Anfrage an das passende LLM.

        Args:
            prompt: Die eigentliche Anfrage
            task: Aufgabentyp fuer automatisches Routing (optional)
            modell: Explizites Modell (ueberschreibt Routing)
            system_prompt: System-Kontext
            temperature: Kreativitaet (0.0 = deterministisch)
            max_tokens: Maximale Antwortlaenge

        Returns:
            {"response": str, "modell": str, "tokens": int, "duration_ms": float}
        """
        # Modell bestimmen
        if modell is None and task is not None:
            modell = self._route_task(task)
        elif modell is None:
            modell = LLMModell.QWEN_CODER  # Default: qwen2.5-coder:14b

        if modell == LLMModell.CLAUDE:
            return await self._generate_claude(prompt, system_prompt, temperature, max_tokens)

        return await self._generate_ollama(
            modell_name=modell.value,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _route_task(self, task: LLMTask) -> LLMModell:
        """Waehlt das beste verfuegbare Modell fuer eine Aufgabe."""
        kandidaten = TASK_ROUTING.get(task, [LLMModell.QWEN_CODER])

        for kandidat in kandidaten:
            # Claude braucht keinen Ollama-Check
            if kandidat == LLMModell.CLAUDE:
                if self._claude_api_key:
                    return kandidat
                continue  # Kein API-Key -> naechster Kandidat

            if kandidat.value in self._verfuegbare_modelle:
                return kandidat
            # Teilmatch (z.B. "deepseek-coder" matcht "deepseek-coder:latest")
            for verfuegbar in self._verfuegbare_modelle:
                if kandidat.value in verfuegbar:
                    return kandidat

        # Fallback: erstes verfuegbares lokales Modell
        if self._verfuegbare_modelle:
            return LLMModell(self._verfuegbare_modelle[0])

        logger.error("Kein LLM-Modell verfuegbar!")
        raise RuntimeError("Kein LLM-Modell verfuegbar")

    async def _generate_ollama(
        self,
        modell_name: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Sendet Anfrage an Ollama /api/generate."""
        payload: dict[str, Any] = {
            "model": modell_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    f"{self._ollama_url}/api/generate",
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()

                return {
                    "response": data.get("response", ""),
                    "modell": modell_name,
                    "tokens": data.get("eval_count", 0),
                    "duration_ms": data.get("total_duration", 0) / 1_000_000,  # ns -> ms
                    "done": data.get("done", False),
                }

        except httpx.TimeoutException:
            logger.error("Ollama Timeout fuer Modell %s", modell_name)
            return {
                "response": "",
                "modell": modell_name,
                "error": "timeout",
                "tokens": 0,
                "duration_ms": 0,
            }
        except Exception as exc:
            logger.error("Ollama Fehler: %s", exc)
            return {
                "response": "",
                "modell": modell_name,
                "error": str(exc),
                "tokens": 0,
                "duration_ms": 0,
            }

    async def _generate_claude(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Sendet Anfrage an Claude API (Lead-Agent, Lern-Agent).

        Erfordert ANTHROPIC_API_KEY.
        """
        if not self._claude_api_key:
            return {
                "response": "",
                "modell": "claude",
                "error": "Kein API-Key konfiguriert",
                "tokens": 0,
                "duration_ms": 0,
            }

        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=self._claude_api_key)
            message = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt or "Du bist ein Experte fuer Schreinerei-Kalkulation.",
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text if message.content else ""

            return {
                "response": response_text,
                "modell": "claude",
                "tokens": message.usage.output_tokens,
                "duration_ms": 0,
            }
        except Exception as exc:
            logger.error("Claude API Fehler: %s", exc)
            return {
                "response": "",
                "modell": "claude",
                "error": str(exc),
                "tokens": 0,
                "duration_ms": 0,
            }

    async def schaetze_materialpreis(self, material: str, einheit: str = "m2") -> dict[str, Any]:
        """Schaetzt einen Materialpreis via LLM wenn nicht in Preisliste.

        Spezialisierte Methode fuer den MaterialKalkulator.
        Verwendet qwen2.5-coder:14b als primaeres Modell.
        """
        prompt = (
            f"Du bist ein Experte fuer Schreinerei-Materialpreise in Deutschland (2026).\n"
            f"Schaetze den aktuellen Marktpreis fuer:\n"
            f"Material: {material}\n"
            f"Einheit: {einheit}\n\n"
            f"Antworte NUR mit einer JSON-Zeile im Format:\n"
            f'{{"preis": <zahl>, "einheit": "{einheit}", "konfidenz": "hoch|mittel|niedrig"}}\n'
            f"Keine Erklaerung, nur JSON."
        )

        result = await self.generate(
            prompt=prompt,
            task=LLMTask.MATERIAL_SCHAETZUNG,
            temperature=0.1,
            max_tokens=100,
        )

        response = result.get("response", "").strip()
        try:
            # JSON aus der Antwort extrahieren
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(response[start:end])
                return {
                    "preis": float(parsed.get("preis", 0)),
                    "einheit": parsed.get("einheit", einheit),
                    "konfidenz": parsed.get("konfidenz", "niedrig"),
                    "quelle": f"ki_schaetzung ({result['modell']})",
                }
        except (json.JSONDecodeError, ValueError):
            pass

        return {
            "preis": 0,
            "einheit": einheit,
            "konfidenz": "keine",
            "quelle": "ki_schaetzung_fehlgeschlagen",
        }

    async def interpretiere_freitext(self, beschreibung: str) -> list[dict[str, Any]]:
        """Interpretiert eine Freitext-Projektbeschreibung und generiert LV-Positionen.

        Spezialisierte Methode fuer den DokumentParser / Schnellkalkulation.
        Verwendet qwen2.5-coder:14b als primaeres Modell.
        """
        prompt = (
            "Du bist ein Experte fuer Schreinerei-Kalkulation. "
            "Interpretiere folgende Projektbeschreibung und erstelle daraus "
            "strukturierte LV-Positionen.\n\n"
            f"Beschreibung: {beschreibung}\n\n"
            "Antworte NUR mit einem JSON-Array im Format:\n"
            '[{"pos_nr": "01.01", "kurztext": "...", "menge": 1, "einheit": "STK", '
            '"material": "...", "platten_anzahl": 0, "kantenlaenge_lfm": 0}]\n'
            "Keine Erklaerung, nur JSON."
        )

        result = await self.generate(
            prompt=prompt,
            task=LLMTask.FREITEXT_INTERPRETATION,
            temperature=0.2,
            max_tokens=2048,
        )

        response = result.get("response", "").strip()
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        return []
