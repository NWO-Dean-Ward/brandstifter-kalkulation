"""
SchreinersBueroAgent -- Anbindung an Schreiner's Buero (SB) ERP.

Branchensoftware von Informationssysteme Dinklage (Koeln).
PHP/MySQL-basiert, laeuft im lokalen Werkstatt-LAN.

Funktionen:
1. Auftrag anlegen/aktualisieren (Projekt -> SB-Auftrag)
2. Stueckliste senden (Positionen -> SB-Stueckliste)
3. Kunden synchronisieren
4. Materialpreise aus SB importieren
5. Auftragsstatus abfragen
6. CSV-Import/Export (Fallback fuer Offline)
"""

from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

from agents.base_agent import AgentMessage, BaseAgent


class SchreinersBueroAgent(BaseAgent):
    """Bidirektionale Schnittstelle zu Schreiner's Buero ERP."""

    def __init__(self) -> None:
        super().__init__(name="schreiners_buero")
        self._config: dict[str, Any] = {}
        self._api_url = ""
        self._api_user = ""
        self._api_pw = ""
        self._timeout = 30
        self._csv_import_dir = Path("data/sb_import")
        self._csv_export_dir = Path("data/sb_export")
        self._csv_trennzeichen = ";"
        self._csv_encoding = "iso-8859-1"
        self._defaults: dict[str, Any] = {}

    def configure(self, config: dict[str, Any]) -> None:
        """Konfiguration aus schreiners_buero.yaml laden."""
        self._config = config
        self._api_url = config.get("api_url", "")
        self._api_user = config.get("api_user", "")
        self._api_pw = config.get("api_pw", "")
        self._timeout = config.get("timeout_sekunden", 30)
        self._csv_import_dir = Path(config.get("csv_import_verzeichnis", "data/sb_import"))
        self._csv_export_dir = Path(config.get("csv_export_verzeichnis", "data/sb_export"))
        self._csv_trennzeichen = config.get("csv_trennzeichen", ";")
        self._csv_encoding = config.get("csv_encoding", "iso-8859-1")
        self._defaults = config.get("defaults", {})

        # Verzeichnisse erstellen
        self._csv_import_dir.mkdir(parents=True, exist_ok=True)
        self._csv_export_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "SB konfiguriert: API=%s, CSV-Export=%s",
            self._api_url or "(nicht gesetzt)",
            self._csv_export_dir,
        )

    async def process(self, message: AgentMessage) -> AgentMessage:
        handler_map = {
            "sb_auftrag_anlegen": self._auftrag_anlegen,
            "sb_auftrag_status": self._auftrag_status,
            "sb_stueckliste_senden": self._stueckliste_senden,
            "sb_kunde_sync": self._kunde_sync,
            "sb_materialpreise_import": self._materialpreise_import,
            "sb_csv_export": self._csv_export_stueckliste,
            "sb_csv_import": self._csv_import_stueckliste,
            "sb_verbindungstest": self._verbindungstest,
        }

        handler = handler_map.get(message.msg_type)
        if handler is None:
            return message.create_error(
                sender=self.name,
                error_msg=f"Unbekannter Nachrichtentyp: {message.msg_type}",
            )

        result = await handler(message.payload, message.projekt_id)
        return message.create_response(sender=self.name, payload=result)

    # ------------------------------------------------------------------
    # HTTP-Kommunikation mit SB
    # ------------------------------------------------------------------

    async def _sb_request(
        self, aktion: str, daten: dict[str, Any]
    ) -> dict[str, Any]:
        """Sendet eine Anfrage an den SB PHP-Endpunkt.

        SB-API-Konvention: POST mit JSON-Body, Feld 'aktion' bestimmt die Operation.
        """
        if not self._api_url:
            return {
                "status": "offline",
                "message": "SB API-URL nicht konfiguriert. CSV-Fallback verwenden.",
            }

        import httpx

        payload = {"aktion": aktion, **daten}
        auth = (self._api_user, self._api_pw) if self._api_user else None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    self._api_url,
                    json=payload,
                    auth=auth,
                    headers={"Accept": "application/json"},
                )

                if r.status_code >= 400:
                    return {
                        "status": "error",
                        "status_code": r.status_code,
                        "message": f"SB-Server Fehler: HTTP {r.status_code}",
                        "response": r.text[:500],
                    }

                # SB antwortet JSON oder Plaintext
                try:
                    return {"status": "ok", "data": r.json()}
                except Exception:
                    return {"status": "ok", "data": r.text[:1000]}

        except httpx.ConnectError:
            return {
                "status": "offline",
                "message": f"SB-Server nicht erreichbar: {self._api_url}",
            }
        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "message": f"SB-Server Timeout nach {self._timeout}s",
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ------------------------------------------------------------------
    # 1. Auftrag anlegen / aktualisieren
    # ------------------------------------------------------------------

    async def _auftrag_anlegen(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Legt einen Auftrag in SB an oder aktualisiert ihn.

        Erwartet payload mit:
        - projekt: Dict mit name, kunde, projekt_typ, angebotspreis, ...
        - positionen: Liste der kalkulierten Positionen
        """
        projekt = payload.get("projekt", {})
        positionen = payload.get("positionen", [])

        sb_auftrag = {
            "auftragsnummer": projekt_id,
            "bezeichnung": projekt.get("name", ""),
            "kunde_name": projekt.get("kunde", ""),
            "auftragsart": self._defaults.get("auftragsart", "A"),
            "kostenstelle": self._defaults.get("kostenstelle", "100"),
            "waehrung": self._defaults.get("waehrung", "EUR"),
            "mwst_satz": self._defaults.get("mwst_satz", 19.0),
            "angebotssumme": projekt.get("angebotspreis", 0),
            "herstellkosten": projekt.get("herstellkosten", 0),
            "datum": datetime.now().strftime("%Y-%m-%d"),
            "positionen": [
                {
                    "pos_nr": p.get("pos_nr", ""),
                    "bezeichnung": p.get("kurztext", ""),
                    "menge": float(p.get("menge", 0)),
                    "einheit": p.get("einheit", "STK"),
                    "material": p.get("material", ""),
                    "ep": float(p.get("einheitspreis", 0)),
                    "gp": float(p.get("gesamtpreis", 0)),
                    "materialkosten": float(p.get("materialkosten", 0)),
                    "lohnkosten": float(p.get("lohnkosten", 0)),
                    "maschinenkosten": float(p.get("maschinenkosten", 0)),
                }
                for p in positionen
            ],
        }

        # Versuche API
        result = await self._sb_request("auftrag_anlegen", sb_auftrag)

        if result["status"] == "offline":
            # Fallback: CSV-Export
            csv_result = await self._csv_export_stueckliste(
                {"positionen": positionen, "projekt": projekt},
                projekt_id,
            )
            return {
                "status": "csv_fallback",
                "message": "SB offline. Auftrag als CSV exportiert.",
                "csv": csv_result,
            }

        return {
            "status": result["status"],
            "message": "Auftrag an SB gesendet" if result["status"] == "ok" else result.get("message", ""),
            "sb_response": result.get("data", ""),
        }

    # ------------------------------------------------------------------
    # 2. Auftragsstatus abfragen
    # ------------------------------------------------------------------

    async def _auftrag_status(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Fragt den Auftragsstatus in SB ab."""
        result = await self._sb_request("auftrag_status", {
            "auftragsnummer": projekt_id,
        })

        if result["status"] == "offline":
            return {
                "status": "offline",
                "message": "SB nicht erreichbar. Status unbekannt.",
                "sb_status": "unbekannt",
            }

        if result["status"] == "ok":
            data = result.get("data", {})
            if isinstance(data, dict):
                return {
                    "status": "ok",
                    "sb_status": data.get("status", "unbekannt"),
                    "sb_auftragsnummer": data.get("auftragsnummer", projekt_id),
                    "sb_angebotssumme": data.get("angebotssumme", 0),
                    "sb_rechnungssumme": data.get("rechnungssumme", 0),
                    "sb_bezahlt": data.get("bezahlt", False),
                }
            return {"status": "ok", "sb_status": str(data), "raw": data}

        return result

    # ------------------------------------------------------------------
    # 3. Stueckliste senden
    # ------------------------------------------------------------------

    async def _stueckliste_senden(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Sendet eine Stueckliste an SB (fuer Material-/Zuschnittsplanung)."""
        positionen = payload.get("positionen", [])

        sb_stueckliste = {
            "auftragsnummer": projekt_id,
            "stueckliste": [
                {
                    "pos_nr": p.get("pos_nr", ""),
                    "bezeichnung": p.get("kurztext", ""),
                    "menge": float(p.get("menge", 0)),
                    "material": p.get("material", ""),
                    "laenge_mm": float(p.get("laenge_mm", 0)),
                    "breite_mm": float(p.get("breite_mm", 0)),
                    "staerke_mm": float(p.get("staerke_mm", 0)),
                    "kantenlaenge_lfm": float(p.get("kantenlaenge_lfm", 0)),
                    "platten_anzahl": int(p.get("platten_anzahl", 0)),
                }
                for p in positionen
            ],
        }

        result = await self._sb_request("stueckliste_import", sb_stueckliste)

        if result["status"] == "offline":
            csv_result = await self._csv_export_stueckliste(payload, projekt_id)
            return {
                "status": "csv_fallback",
                "message": "SB offline. Stueckliste als CSV exportiert.",
                "csv": csv_result,
            }

        return {
            "status": result["status"],
            "positionen_gesendet": len(positionen),
            "message": "Stueckliste an SB gesendet" if result["status"] == "ok" else result.get("message", ""),
        }

    # ------------------------------------------------------------------
    # 4. Kunden synchronisieren
    # ------------------------------------------------------------------

    async def _kunde_sync(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Synchronisiert Kundendaten mit SB."""
        kunde_name = payload.get("kunde_name", "")
        if not kunde_name:
            return {"status": "error", "message": "Kein Kundenname angegeben"}

        # Kunde in SB suchen
        result = await self._sb_request("kunde_suchen", {
            "name": kunde_name,
        })

        if result["status"] == "offline":
            return {
                "status": "offline",
                "message": "SB nicht erreichbar. Kunde manuell anlegen.",
            }

        if result["status"] == "ok":
            data = result.get("data", {})
            if isinstance(data, dict) and data.get("gefunden"):
                return {
                    "status": "ok",
                    "aktion": "gefunden",
                    "kunde": data,
                }

            # Kunde nicht gefunden -> anlegen
            neuer_kunde = {
                "name": kunde_name,
                "adresse": payload.get("adresse", ""),
                "telefon": payload.get("telefon", ""),
                "email": payload.get("email", ""),
            }
            anlegen_result = await self._sb_request("kunde_anlegen", neuer_kunde)
            return {
                "status": anlegen_result["status"],
                "aktion": "angelegt",
                "kunde": neuer_kunde,
            }

        return result

    # ------------------------------------------------------------------
    # 5. Materialpreise aus SB importieren
    # ------------------------------------------------------------------

    async def _materialpreise_import(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Importiert aktuelle Materialpreise aus SB.

        Kann entweder ueber API oder CSV-Datei erfolgen.
        """
        quelle = payload.get("quelle", "api")  # "api" oder "csv"

        if quelle == "csv":
            return await self._csv_import_materialpreise(payload)

        # API-Abfrage
        result = await self._sb_request("materialpreise_export", {
            "kategorie": payload.get("kategorie", ""),  # leer = alle
        })

        if result["status"] == "offline":
            # Versuche CSV-Fallback
            return await self._csv_import_materialpreise(payload)

        if result["status"] == "ok":
            preise = result.get("data", [])
            if isinstance(preise, list):
                return {
                    "status": "ok",
                    "quelle": "api",
                    "anzahl": len(preise),
                    "preise": preise,
                }

        return result

    async def _csv_import_materialpreise(
        self, payload: dict
    ) -> dict[str, Any]:
        """Importiert Materialpreise aus CSV-Datei im SB-Format."""
        datei_pfad = payload.get("datei_pfad", "")

        if not datei_pfad:
            # Standard-CSV im Import-Verzeichnis suchen
            csv_files = list(self._csv_import_dir.glob("materialpreise*.csv"))
            if not csv_files:
                csv_files = list(self._csv_import_dir.glob("*.csv"))
            if not csv_files:
                return {
                    "status": "error",
                    "message": f"Keine CSV-Dateien in {self._csv_import_dir}",
                }
            datei_pfad = str(sorted(csv_files)[-1])  # Neueste zuerst

        pfad = Path(datei_pfad)
        if not pfad.exists():
            return {"status": "error", "message": f"Datei nicht gefunden: {datei_pfad}"}

        preise: list[dict] = []
        try:
            with open(pfad, encoding=self._csv_encoding, errors="replace") as f:
                reader = csv.DictReader(f, delimiter=self._csv_trennzeichen)
                for row in reader:
                    preis_entry = {
                        "material_name": (
                            row.get("Bezeichnung", "")
                            or row.get("Material", "")
                            or row.get("Artikel", "")
                        ),
                        "kategorie": row.get("Kategorie", row.get("Warengruppe", "")),
                        "lieferant": row.get("Lieferant", ""),
                        "artikel_nr": row.get("Artikelnr", row.get("ArtNr", "")),
                        "einheit": row.get("Einheit", row.get("ME", "STK")),
                        "preis": _parse_sb_preis(
                            row.get("Preis", row.get("VK-Preis", row.get("EK-Preis", "0")))
                        ),
                    }
                    if preis_entry["material_name"] and preis_entry["preis"] > 0:
                        preise.append(preis_entry)

        except Exception as exc:
            return {"status": "error", "message": f"CSV-Lesefehler: {exc}"}

        return {
            "status": "ok",
            "quelle": "csv",
            "datei": pfad.name,
            "anzahl": len(preise),
            "preise": preise,
        }

    # ------------------------------------------------------------------
    # 6. CSV-Export: Stueckliste im SB-Format
    # ------------------------------------------------------------------

    async def _csv_export_stueckliste(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Exportiert Positionen als CSV im Schreiner's Buero Stuecklisten-Format.

        SB CSV-Importformat (dokumentiert):
        Pos-Nr;Bezeichnung;Menge;Einheit;Material;Laenge;Breite;Staerke;EP;GP
        Trennzeichen: Semikolon, Encoding: ISO-8859-1
        """
        positionen = payload.get("positionen", [])
        projekt = payload.get("projekt", {})

        if not positionen:
            return {"status": "error", "message": "Keine Positionen fuer Export"}

        dateiname = f"SB_Stueckliste_{projekt_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        pfad = self._csv_export_dir / dateiname

        try:
            with open(str(pfad), "w", newline="", encoding=self._csv_encoding, errors="replace") as f:
                writer = csv.writer(f, delimiter=self._csv_trennzeichen)

                # SB Stuecklisten-Header
                writer.writerow([
                    "Pos-Nr", "Bezeichnung", "Menge", "Einheit",
                    "Material", "Laenge", "Breite", "Staerke",
                    "EP", "GP", "Materialkosten", "Lohnkosten",
                    "Kostenstelle", "Bemerkung",
                ])

                for pos in positionen:
                    menge = float(pos.get("menge", 0))
                    ep = float(pos.get("einheitspreis", 0))
                    gp = float(pos.get("gesamtpreis", ep * menge))

                    writer.writerow([
                        pos.get("pos_nr", ""),
                        pos.get("kurztext", ""),
                        _format_sb_zahl(menge),
                        pos.get("einheit", "STK"),
                        pos.get("material", ""),
                        _format_sb_zahl(pos.get("laenge_mm", 0)),
                        _format_sb_zahl(pos.get("breite_mm", 0)),
                        _format_sb_zahl(pos.get("staerke_mm", 0)),
                        _format_sb_preis(ep),
                        _format_sb_preis(gp),
                        _format_sb_preis(pos.get("materialkosten", 0)),
                        _format_sb_preis(pos.get("lohnkosten", 0)),
                        self._defaults.get("kostenstelle", "100"),
                        f"Projekt: {projekt.get('name', projekt_id)}",
                    ])

        except Exception as exc:
            return {"status": "error", "message": f"CSV-Schreibfehler: {exc}"}

        self.logger.info("SB CSV exportiert: %s (%d Positionen)", pfad, len(positionen))

        return {
            "status": "ok",
            "datei": dateiname,
            "pfad": str(pfad),
            "positionen": len(positionen),
            "format": "sb_stueckliste_csv",
            "encoding": self._csv_encoding,
        }

    # ------------------------------------------------------------------
    # 7. CSV-Import: Stueckliste aus SB lesen
    # ------------------------------------------------------------------

    async def _csv_import_stueckliste(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Importiert eine Stueckliste aus einer SB-CSV-Datei.

        Liest CSV im SB-Format und gibt normalisierte Positionen zurueck.
        """
        datei_pfad = payload.get("datei_pfad", "")

        if not datei_pfad:
            # Neueste CSV im Import-Verzeichnis
            csv_files = list(self._csv_import_dir.glob("*.csv"))
            if not csv_files:
                return {
                    "status": "error",
                    "message": f"Keine CSV-Dateien in {self._csv_import_dir}",
                }
            datei_pfad = str(sorted(csv_files, key=lambda p: p.stat().st_mtime)[-1])

        pfad = Path(datei_pfad)
        if not pfad.exists():
            return {"status": "error", "message": f"Datei nicht gefunden: {datei_pfad}"}

        positionen: list[dict] = []
        try:
            with open(pfad, encoding=self._csv_encoding, errors="replace") as f:
                reader = csv.DictReader(f, delimiter=self._csv_trennzeichen)
                for row in reader:
                    pos = {
                        "pos_nr": row.get("Pos-Nr", row.get("PosNr", "")),
                        "kurztext": row.get("Bezeichnung", row.get("Beschreibung", "")),
                        "menge": _parse_sb_preis(row.get("Menge", "0")),
                        "einheit": row.get("Einheit", row.get("ME", "STK")),
                        "material": row.get("Material", ""),
                        "laenge_mm": _parse_sb_preis(row.get("Laenge", "0")),
                        "breite_mm": _parse_sb_preis(row.get("Breite", "0")),
                        "staerke_mm": _parse_sb_preis(row.get("Staerke", "0")),
                        "einheitspreis": _parse_sb_preis(row.get("EP", "0")),
                        "gesamtpreis": _parse_sb_preis(row.get("GP", "0")),
                    }
                    if pos["pos_nr"] or pos["kurztext"]:
                        positionen.append(pos)

        except Exception as exc:
            return {"status": "error", "message": f"CSV-Lesefehler: {exc}"}

        return {
            "status": "ok",
            "datei": pfad.name,
            "positionen": positionen,
            "anzahl": len(positionen),
        }

    # ------------------------------------------------------------------
    # 8. Verbindungstest
    # ------------------------------------------------------------------

    async def _verbindungstest(
        self, payload: dict, projekt_id: str
    ) -> dict[str, Any]:
        """Testet die Verbindung zum SB-Server."""
        if not self._api_url:
            return {
                "status": "nicht_konfiguriert",
                "message": "SB API-URL nicht gesetzt. Nur CSV-Modus verfuegbar.",
                "api_url": "",
                "csv_import": str(self._csv_import_dir),
                "csv_export": str(self._csv_export_dir),
            }

        result = await self._sb_request("ping", {})

        return {
            "status": result["status"],
            "api_url": self._api_url,
            "message": result.get("message", "Verbindung OK" if result["status"] == "ok" else ""),
            "csv_import": str(self._csv_import_dir),
            "csv_export": str(self._csv_export_dir),
            "csv_dateien_import": len(list(self._csv_import_dir.glob("*.csv"))),
            "csv_dateien_export": len(list(self._csv_export_dir.glob("*.csv"))),
        }


# ------------------------------------------------------------------
# Hilfsfunktionen: SB-Zahlenformate
# ------------------------------------------------------------------

def _parse_sb_preis(wert: str) -> float:
    """Parst einen Preis/Zahl im deutschen Format (Komma als Dezimaltrenner)."""
    if not wert:
        return 0.0
    try:
        # SB nutzt deutsches Format: 1.234,56
        cleaned = str(wert).strip().replace(".", "").replace(",", ".")
        return float(cleaned)
    except (ValueError, AttributeError):
        return 0.0


def _format_sb_preis(wert: float | int) -> str:
    """Formatiert einen Preis im deutschen Format fuer SB."""
    try:
        return f"{float(wert):.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return "0,00"


def _format_sb_zahl(wert: float | int) -> str:
    """Formatiert eine Zahl im deutschen Format fuer SB (ohne Nachkommastellen bei ganzen Zahlen)."""
    try:
        f = float(wert)
        if f == int(f):
            return str(int(f))
        return f"{f:.1f}".replace(".", ",")
    except (ValueError, TypeError):
        return "0"
