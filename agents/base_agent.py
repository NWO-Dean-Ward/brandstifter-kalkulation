"""
BaseAgent – Basisklasse und Kommunikationsprotokoll für alle Agenten.

Jeder Agent:
- hat einen eindeutigen Namen und Status
- empfängt AgentMessage-Objekte als Input
- gibt AgentMessage-Objekte als Output zurück
- loggt alle Aktionen für Nachvollziehbarkeit
- kann Fehler strukturiert melden
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    """Statuswerte eines Agenten während der Verarbeitung."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"           # wartet auf Input von anderem Agenten
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentMessage:
    """Standardisierte Nachricht zwischen Agenten.

    Jede Kommunikation zwischen Agenten läuft über dieses Format.
    Das ermöglicht Logging, Replay und Debugging der gesamten Pipeline.
    """
    sender: str
    receiver: str
    msg_type: str                # z.B. "request", "response", "error", "warning"
    payload: dict[str, Any]      # die eigentlichen Daten
    projekt_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    correlation_id: str = ""     # verknüpft Request mit Response

    def create_response(self, sender: str, payload: dict[str, Any],
                        msg_type: str = "response") -> AgentMessage:
        """Erzeugt eine Antwort-Nachricht mit gleicher correlation_id."""
        return AgentMessage(
            sender=sender,
            receiver=self.sender,
            msg_type=msg_type,
            payload=payload,
            projekt_id=self.projekt_id,
            correlation_id=self.message_id,
        )

    def create_error(self, sender: str, error_msg: str,
                     details: dict[str, Any] | None = None) -> AgentMessage:
        """Erzeugt eine Fehlernachricht."""
        return AgentMessage(
            sender=sender,
            receiver=self.sender,
            msg_type="error",
            payload={
                "error": error_msg,
                "details": details or {},
            },
            projekt_id=self.projekt_id,
            correlation_id=self.message_id,
        )


class BaseAgent(ABC):
    """Abstrakte Basisklasse für alle Agenten im Kalkulationstool.

    Stellt sicher, dass jeder Agent:
    - einen Namen hat
    - seinen Status tracked
    - ein einheitliches Interface (process) implementiert
    - Logging korrekt konfiguriert ist
    """

    def __init__(self, name: str):
        self.name = name
        self.status = AgentStatus.IDLE
        self.logger = logging.getLogger(f"agent.{name}")
        self._message_log: list[AgentMessage] = []

    @abstractmethod
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Verarbeitet eine eingehende Nachricht und gibt eine Antwort zurück.

        Jeder Agent implementiert hier seine Kernlogik.
        """
        ...

    async def execute(self, message: AgentMessage) -> AgentMessage:
        """Wrapper um process() mit Status-Tracking und Fehlerbehandlung."""
        self.status = AgentStatus.RUNNING
        self._message_log.append(message)
        self.logger.info(
            "Nachricht empfangen: type=%s von=%s projekt=%s",
            message.msg_type, message.sender, message.projekt_id,
        )

        try:
            response = await self.process(message)
            self.status = AgentStatus.COMPLETED
            self._message_log.append(response)
            self.logger.info(
                "Verarbeitung abgeschlossen: type=%s → %s",
                message.msg_type, response.msg_type,
            )
            return response

        except Exception as exc:
            self.status = AgentStatus.ERROR
            self.logger.error("Fehler bei Verarbeitung: %s", exc, exc_info=True)
            error_response = message.create_error(
                sender=self.name,
                error_msg=str(exc),
                details={"exception_type": type(exc).__name__},
            )
            self._message_log.append(error_response)
            return error_response

    def get_message_log(self) -> list[AgentMessage]:
        """Gibt das vollständige Nachrichtenprotokoll zurück."""
        return list(self._message_log)

    def reset(self) -> None:
        """Setzt den Agenten auf Ausgangszustand zurück."""
        self.status = AgentStatus.IDLE
        self._message_log.clear()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} status={self.status.value}>"
