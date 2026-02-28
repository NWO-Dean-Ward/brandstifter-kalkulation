"""
Konfigurationsloader -- Laedt und verwaltet YAML-Konfigurationsdateien.

Dateien:
- config/maschinen.yaml
- config/zuschlaege.yaml
- config/stundensaetze.yaml
- config/schreiners_buero.yaml
- config/partner-logins.yaml (Fernet-verschluesselt)
- config/.secret_key (auto-generiert, in .gitignore)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

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

    def get_partner_logins(self) -> dict[str, dict[str, str]]:
        """Laedt und entschluesselt Partner-Logins fuer den Einkaufs-Agent."""
        return _load_encrypted_logins()

    def save_partner_login(self, partner: str, username: str, password: str) -> None:
        """Speichert einen verschluesselten Partner-Login."""
        _save_encrypted_login(partner, username, password)


# --- Fernet-Verschluesselung fuer Partner-Logins ---

def _get_or_create_fernet_key() -> bytes:
    """Laedt oder erstellt den Fernet-Schluessel."""
    key_path = CONFIG_DIR / ".secret_key"
    if key_path.exists():
        return key_path.read_bytes().strip()

    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        logger.info("Neuer Fernet-Schluessel generiert: %s", key_path)
        return key
    except ImportError:
        logger.warning("cryptography nicht installiert - Partner-Logins nicht verschluesselt")
        return b""


def _load_encrypted_logins() -> dict[str, dict[str, str]]:
    """Laedt Partner-Logins und entschluesselt Passwoerter."""
    login_path = CONFIG_DIR / "partner-logins.yaml"
    if not login_path.exists():
        return {}

    try:
        data = _load_yaml("partner-logins.yaml")
    except FileNotFoundError:
        return {}

    key = _get_or_create_fernet_key()
    if not key:
        return data.get("partner", {})

    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
    except ImportError:
        return data.get("partner", {})

    result: dict[str, dict[str, str]] = {}
    for partner, creds in data.get("partner", {}).items():
        pw = creds.get("password", "")
        if pw.startswith("gAAAAA"):  # Fernet-verschluesselt
            try:
                pw = f.decrypt(pw.encode()).decode()
            except Exception:
                logger.warning("Passwort fuer %s konnte nicht entschluesselt werden", partner)
                pw = ""
        result[partner] = {"username": creds.get("username", ""), "password": pw}

    return result


def _save_encrypted_login(partner: str, username: str, password: str) -> None:
    """Speichert einen Partner-Login mit verschluesseltem Passwort."""
    login_path = CONFIG_DIR / "partner-logins.yaml"

    if login_path.exists():
        data = _load_yaml("partner-logins.yaml")
    else:
        data = {"partner": {}}

    key = _get_or_create_fernet_key()
    encrypted_pw = password

    if key:
        try:
            from cryptography.fernet import Fernet
            f = Fernet(key)
            encrypted_pw = f.encrypt(password.encode()).decode()
        except ImportError:
            logger.warning("cryptography nicht installiert - Passwort wird unverschluesselt gespeichert")

    if "partner" not in data:
        data["partner"] = {}

    data["partner"][partner] = {"username": username, "password": encrypted_pw}
    _save_yaml("partner-logins.yaml", data)
