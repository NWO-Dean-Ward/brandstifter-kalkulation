"""
Konfigurationsloader -- Laedt und verwaltet YAML-Konfigurationsdateien.

Dateien:
- config/maschinen.yaml
- config/zuschlaege.yaml
- config/stundensaetze.yaml
- config/schreiners_buero.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path("config")


def _load_yaml(datei: str) -> dict[str, Any]:
    """Lädt eine YAML-Datei aus dem Config-Verzeichnis."""
    pfad = CONFIG_DIR / datei
    if not pfad.exists():
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {pfad}")
    with open(pfad, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(datei: str, data: dict[str, Any]) -> None:
    """Speichert Daten in eine YAML-Datei."""
    pfad = CONFIG_DIR / datei
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


class AppConfig:
    """Zentrale Konfiguration – lädt alle YAML-Dateien und bietet Zugriff."""

    def __init__(self, config_dir: Path | None = None) -> None:
        global CONFIG_DIR
        if config_dir:
            CONFIG_DIR = config_dir

        self.maschinen: dict[str, Any] = {}
        self.zuschlaege: dict[str, Any] = {}
        self.stundensaetze: dict[str, Any] = {}
        self.schreiners_buero: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        """Laedt alle Konfigurationsdateien neu."""
        self.maschinen = _load_yaml("maschinen.yaml")
        self.zuschlaege = _load_yaml("zuschlaege.yaml")
        self.stundensaetze = _load_yaml("stundensaetze.yaml")
        try:
            self.schreiners_buero = _load_yaml("schreiners_buero.yaml")
        except FileNotFoundError:
            self.schreiners_buero = {}

    def get_maschine(self, name: str) -> dict[str, Any]:
        """Gibt Konfiguration einer Maschine zurück."""
        return self.maschinen.get(name, {})

    def get_stundensatz(self) -> float:
        """Gibt den einheitlichen Stundensatz zurück."""
        return float(self.stundensaetze.get("einheitlicher_stundensatz", 58.0))

    def get_zuschlag(self, name: str) -> float:
        """Gibt einen Zuschlagssatz zurück."""
        return float(self.zuschlaege.get(name, 0.0))

    def update_maschinen(self, data: dict[str, Any]) -> None:
        """Aktualisiert und speichert Maschinenkonfiguration."""
        self.maschinen.update(data)
        _save_yaml("maschinen.yaml", self.maschinen)

    def update_zuschlaege(self, data: dict[str, Any]) -> None:
        """Aktualisiert und speichert Zuschlagskonfiguration."""
        self.zuschlaege.update(data)
        _save_yaml("zuschlaege.yaml", self.zuschlaege)

    def update_stundensaetze(self, data: dict[str, Any]) -> None:
        """Aktualisiert und speichert Stundensätze."""
        self.stundensaetze.update(data)
        _save_yaml("stundensaetze.yaml", self.stundensaetze)
