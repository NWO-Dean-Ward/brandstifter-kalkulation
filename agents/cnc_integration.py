"""
CNC-Integration -- Smartwoop/NCHops Anbindung fuer Holzher Nextec 7707.

Funktionen:
1. HOP-Import: Liest NC-HOPS .hop Dateien fuer praezise CNC-Zeitberechnung
2. MPR-Import: Liest WoodWOP .mpr Dateien (Branchenstandard-Austauschformat)
3. HOP-Export: Generiert .hop Dateien mit Bohr-/Fraesoperationen
4. Stuecklisten-Export: CSV fuer Smartwoop-Import
5. Nesting-Analyse: Plattenoptimierung und Verschnitt-Berechnung

nc-hops Paket: https://github.com/apers0/nc-hops (MIT Lizenz)
"""

from __future__ import annotations

import csv
import math
import re
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

from agents.base_agent import AgentMessage, BaseAgent


class CNCIntegration(BaseAgent):
    """Smartwoop/NCHops Integration fuer Holzher Nextec 7707."""

    def __init__(self) -> None:
        super().__init__(name="cnc_integration")
        self._export_verzeichnis = Path("exports")
        self._cnc_verzeichnis = Path("exports/cnc")

    def configure(self, export_verzeichnis: str = "exports") -> None:
        self._export_verzeichnis = Path(export_verzeichnis)
        self._cnc_verzeichnis = self._export_verzeichnis / "cnc"
        self._cnc_verzeichnis.mkdir(parents=True, exist_ok=True)

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.msg_type

        handler_map = {
            "parse_hop": self._parse_hop,
            "parse_mpr": self._parse_mpr,
            "export_hop": self._export_hop,
            "export_stueckliste": self._export_stueckliste,
            "nesting_analyse": self._nesting_analyse,
            "cnc_zeitberechnung": self._cnc_zeitberechnung,
        }

        handler = handler_map.get(msg_type)
        if handler is None:
            return message.create_error(
                sender=self.name,
                error_msg=f"Unbekannter Nachrichtentyp: {msg_type}",
            )

        result = await handler(message.payload, message.projekt_id)
        return message.create_response(sender=self.name, payload=result)

    # ------------------------------------------------------------------
    # 1. HOP-Import (NC-HOPS Dateien lesen)
    # ------------------------------------------------------------------

    async def _parse_hop(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Parst eine NC-HOPS .hop Datei und extrahiert CNC-Parameter.

        Erwartet payload mit:
        - datei_pfad: Pfad zur .hop Datei
        """
        from ReadHop import ReadHop

        datei_pfad = payload.get("datei_pfad", "")
        if not datei_pfad or not Path(datei_pfad).exists():
            return {"error": f"Datei nicht gefunden: {datei_pfad}"}

        try:
            hop = ReadHop.ExtractHopProcessing(datei_pfad)

            # Variablen extrahieren (Werkstueck-Dimensionen)
            hop_vars = hop.get_vars()
            dx = _parse_num(hop_vars.get("DX", "0"))
            dy = _parse_num(hop_vars.get("DY", "0"))
            dz = _parse_num(hop_vars.get("DZ", "0"))

            # Kommentare (Metadaten)
            comments = hop.get_comments()

            # Bohrungen zaehlen
            drill_counts = hop.drill_count()
            bohrungen_vertikal = drill_counts.get("vcount", 0)
            bohrungen_horizontal = drill_counts.get("hcount", 0)

            # Saege-Operationen
            try:
                saege_laenge = hop.sawing_length()
            except (IndexError, ValueError):
                saege_laenge = 0

            # Fraes-Operationen
            fraes_prozesse = hop.milling_processes()
            fraes_laenge = 0.0
            werkzeug_wechsel = len(fraes_prozesse)
            for tool in fraes_prozesse:
                for mill in tool.get("milling", []):
                    sp = mill.get("sp", [0, 0])
                    ep = mill.get("ep", [0, 0])
                    if len(sp) >= 2 and len(ep) >= 2:
                        dx_m = float(ep[0]) - float(sp[0])
                        dy_m = float(ep[1]) - float(sp[1])
                        fraes_laenge += math.sqrt(dx_m**2 + dy_m**2)

            # Alle Bearbeitungsschritte
            alle_schritte = hop.get_processing()

            # Geschaetzte Bearbeitungszeit (Erfahrungswerte)
            zeit_minuten = self._schaetze_bearbeitungszeit(
                bohrungen=bohrungen_vertikal + bohrungen_horizontal,
                fraes_laenge_mm=fraes_laenge,
                saege_laenge_mm=saege_laenge,
                werkzeug_wechsel=werkzeug_wechsel,
            )

            return {
                "datei": Path(datei_pfad).name,
                "werkstueck": {
                    "laenge_mm": dx,
                    "breite_mm": dy,
                    "staerke_mm": dz,
                    "flaeche_m2": round((dx * dy) / 1_000_000, 3),
                },
                "bearbeitungen": {
                    "bohrungen_vertikal": bohrungen_vertikal,
                    "bohrungen_horizontal": bohrungen_horizontal,
                    "bohrungen_gesamt": bohrungen_vertikal + bohrungen_horizontal,
                    "fraes_laenge_mm": round(fraes_laenge, 1),
                    "saege_laenge_mm": round(saege_laenge, 1),
                    "werkzeug_wechsel": werkzeug_wechsel,
                    "bearbeitungsschritte": len(alle_schritte),
                },
                "zeitschaetzung": {
                    "bearbeitungszeit_min": round(zeit_minuten, 1),
                    "bearbeitungszeit_h": round(zeit_minuten / 60, 2),
                },
                "variablen": hop_vars,
                "kommentare": comments,
            }

        except Exception as exc:
            self.logger.error("HOP-Parse Fehler: %s", exc)
            return {"error": f"HOP-Parse Fehler: {exc}"}

    # ------------------------------------------------------------------
    # 2. MPR-Import (WoodWOP Dateien lesen)
    # ------------------------------------------------------------------

    async def _parse_mpr(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Parst eine WoodWOP .mpr Datei und extrahiert CNC-Parameter.

        MPR-Format: Textbasiert, Sektionen mit [NNN], Operationstypen:
        \\BO_ = Bohren, \\KO_ = Kontur, \\SA_ = Saegen, \\NU_ = Nut
        """
        datei_pfad = payload.get("datei_pfad", "")
        if not datei_pfad or not Path(datei_pfad).exists():
            return {"error": f"Datei nicht gefunden: {datei_pfad}"}

        try:
            # Encoding erkennen
            with open(datei_pfad, "rb") as f:
                raw = f.read()

            for enc in ["utf-8", "iso-8859-1", "windows-1252"]:
                try:
                    content = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                content = raw.decode("utf-8", errors="replace")

            lines = content.splitlines()

            # Header parsen
            header: dict[str, str] = {}
            operationen: list[dict] = []
            aktuelle_op: dict | None = None

            for line in lines:
                line = line.strip()

                # Header-Bereich: key=value Zeilen
                if "=" in line and not line.startswith("[") and aktuelle_op is None:
                    key, _, val = line.partition("=")
                    key = key.strip().strip('"')
                    val = val.strip().strip('"')
                    header[key] = val

                # Neue Sektion [NNN]
                elif re.match(r"\[\d+\]", line):
                    if aktuelle_op is not None:
                        operationen.append(aktuelle_op)
                    aktuelle_op = {"sektion": line, "typ": "", "parameter": {}}

                # Operationstyp
                elif line.startswith("\\") and aktuelle_op is not None:
                    aktuelle_op["typ"] = line

                # Parameter innerhalb einer Operation
                elif "=" in line and aktuelle_op is not None:
                    key, _, val = line.partition("=")
                    aktuelle_op["parameter"][key.strip().strip('"')] = val.strip().strip('"')

            if aktuelle_op is not None:
                operationen.append(aktuelle_op)

            # Operationen kategorisieren
            bohrungen = [op for op in operationen if "BO" in op.get("typ", "").upper()]
            konturen = [op for op in operationen if "KO" in op.get("typ", "").upper()]
            saege_ops = [op for op in operationen if "SA" in op.get("typ", "").upper()]
            nuten = [op for op in operationen if "NU" in op.get("typ", "").upper()]

            # Dimensionen aus Header
            laenge = _parse_num(header.get("KL", header.get("L", "0")))
            breite = _parse_num(header.get("KB", header.get("B", "0")))
            staerke = _parse_num(header.get("KH", header.get("D", "0")))

            # Zeitschaetzung
            zeit_minuten = self._schaetze_bearbeitungszeit(
                bohrungen=len(bohrungen),
                fraes_laenge_mm=len(konturen) * 500,  # Grobe Schaetzung
                saege_laenge_mm=len(saege_ops) * 300,
                werkzeug_wechsel=len(set(
                    op.get("parameter", {}).get("TNO", "0") for op in operationen
                )),
            )

            return {
                "datei": Path(datei_pfad).name,
                "format": "mpr",
                "werkstueck": {
                    "laenge_mm": laenge,
                    "breite_mm": breite,
                    "staerke_mm": staerke,
                    "flaeche_m2": round((laenge * breite) / 1_000_000, 3),
                },
                "bearbeitungen": {
                    "bohrungen": len(bohrungen),
                    "konturen_fraesen": len(konturen),
                    "saege_operationen": len(saege_ops),
                    "nuten": len(nuten),
                    "operationen_gesamt": len(operationen),
                },
                "zeitschaetzung": {
                    "bearbeitungszeit_min": round(zeit_minuten, 1),
                    "bearbeitungszeit_h": round(zeit_minuten / 60, 2),
                },
                "header": header,
            }

        except Exception as exc:
            self.logger.error("MPR-Parse Fehler: %s", exc)
            return {"error": f"MPR-Parse Fehler: {exc}"}

    # ------------------------------------------------------------------
    # 3. HOP-Export (NC-HOPS Dateien generieren)
    # ------------------------------------------------------------------

    async def _export_hop(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Generiert .hop Dateien fuer jedes Bauteil eines Projekts.

        Erwartet payload mit:
        - positionen: Liste der Positionen mit Dimensionen und Bearbeitungen
        """
        import WriteHop as WriteHopModule
        WriteHopCls = WriteHopModule.WriteHop

        positionen = payload.get("positionen", [])
        if not positionen:
            return {"error": "Keine Positionen fuer HOP-Export"}

        exportierte_dateien: list[dict] = []

        for pos in positionen:
            pos_nr = pos.get("pos_nr", "?").replace(".", "_")
            kurztext = pos.get("kurztext", "Bauteil")
            menge = int(pos.get("menge", 1))

            # Dimensionen aus Position oder Defaults
            laenge = float(pos.get("laenge_mm", 600))
            breite = float(pos.get("breite_mm", 400))
            staerke = float(pos.get("staerke_mm", 19))

            hop = WriteHopCls(dx=laenge, dy=breite, dz=staerke)

            # Bohrungen hinzufuegen (System 32 Raster fuer Beschlaege)
            bohrungen = int(pos.get("bohrungen_anzahl", 0))
            if bohrungen > 0:
                self._add_system32_bohrungen(hop, laenge, breite, bohrungen)

            # HOP-Datei schreiben
            dateiname = f"{projekt_id}_{pos_nr}.hop"
            pfad = self._cnc_verzeichnis / dateiname
            hop.write_to_file(
                str(pfad),
                wzgv="HOLZHER",
                comment=f"{kurztext} | Pos {pos.get('pos_nr', '')} | Menge: {menge}",
            )

            exportierte_dateien.append({
                "datei": dateiname,
                "pfad": str(pfad),
                "pos_nr": pos.get("pos_nr", ""),
                "kurztext": kurztext,
                "menge": menge,
                "dimensionen": f"{laenge}x{breite}x{staerke}mm",
            })

        self.logger.info(
            "HOP-Export: %d Dateien fuer Projekt %s",
            len(exportierte_dateien), projekt_id,
        )

        return {
            "status": "ok",
            "dateien": exportierte_dateien,
            "anzahl": len(exportierte_dateien),
            "verzeichnis": str(self._cnc_verzeichnis),
        }

    # ------------------------------------------------------------------
    # 4. Stuecklisten-Export (CSV fuer Smartwoop)
    # ------------------------------------------------------------------

    async def _export_stueckliste(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Exportiert eine Stueckliste als CSV fuer Smartwoop-Import.

        Format: pos_nr, bezeichnung, menge, laenge, breite, staerke, material,
                kante_oben, kante_unten, kante_links, kante_rechts
        """
        positionen = payload.get("positionen", [])
        if not positionen:
            return {"error": "Keine Positionen fuer Stueckliste"}

        dateiname = f"Stueckliste_{projekt_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        pfad = self._cnc_verzeichnis / dateiname

        with open(str(pfad), "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")

            # Header
            writer.writerow([
                "Pos-Nr", "Bezeichnung", "Menge", "Laenge_mm", "Breite_mm",
                "Staerke_mm", "Material", "Kante_L1", "Kante_L2",
                "Kante_B1", "Kante_B2", "Drehung", "Bemerkung",
            ])

            for pos in positionen:
                menge = int(pos.get("menge", 1))
                platten = int(pos.get("platten_anzahl", menge))
                material = pos.get("material", "")
                kurztext = pos.get("kurztext", "")
                laenge = pos.get("laenge_mm", 600)
                breite = pos.get("breite_mm", 400)
                staerke = pos.get("staerke_mm", 19)

                # Kanteninformation (vereinfacht)
                kanten_lfm = float(pos.get("kantenlaenge_lfm", 0))
                hat_kanten = kanten_lfm > 0
                kante_mat = "ABS 2mm" if hat_kanten else ""

                for i in range(platten):
                    writer.writerow([
                        pos.get("pos_nr", ""),
                        f"{kurztext} ({i+1}/{platten})" if platten > 1 else kurztext,
                        1,  # Menge pro Zeile = 1 (jede Platte einzeln)
                        laenge,
                        breite,
                        staerke,
                        material,
                        kante_mat if hat_kanten else "",
                        kante_mat if hat_kanten else "",
                        kante_mat if hat_kanten else "",
                        "",  # Hinterkante oft ohne Kante
                        0,  # Drehung
                        f"Pos {pos.get('pos_nr', '')}",
                    ])

        self.logger.info("Stueckliste exportiert: %s", pfad)
        return {
            "status": "ok",
            "datei": dateiname,
            "pfad": str(pfad),
            "positionen": len(positionen),
        }

    # ------------------------------------------------------------------
    # 5. Nesting-Analyse
    # ------------------------------------------------------------------

    async def _nesting_analyse(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Berechnet eine Nesting-Schaetzung (Plattenverbrauch + Verschnitt).

        Vereinfachte Rechteck-Nesting-Berechnung.
        BetterNest auf dem CAMPUS-System macht das praeziser.
        """
        positionen = payload.get("positionen", [])
        platte_laenge = float(payload.get("platte_laenge_mm", 2800))
        platte_breite = float(payload.get("platte_breite_mm", 2070))
        schnittbreite = float(payload.get("schnittbreite_mm", 4))

        platten_flaeche = platte_laenge * platte_breite  # mm2
        teile: list[dict] = []
        gesamt_teile_flaeche = 0.0

        for pos in positionen:
            menge = int(pos.get("menge", 1))
            platten_anzahl = int(pos.get("platten_anzahl", menge))
            laenge = float(pos.get("laenge_mm", 600))
            breite = float(pos.get("breite_mm", 400))

            for _ in range(platten_anzahl):
                teil_flaeche = (laenge + schnittbreite) * (breite + schnittbreite)
                gesamt_teile_flaeche += teil_flaeche
                teile.append({"l": laenge, "b": breite, "flaeche": teil_flaeche})

        # Grobe Schaetzung: Flaeche + 15% Verschnitt
        verschnitt_faktor = 1.15
        benoetigte_flaeche = gesamt_teile_flaeche * verschnitt_faktor
        platten_benötigt = math.ceil(benoetigte_flaeche / platten_flaeche)

        # Verschnitt berechnen
        genutzte_flaeche = gesamt_teile_flaeche
        gesamt_platten_flaeche = platten_benötigt * platten_flaeche
        verschnitt_flaeche = gesamt_platten_flaeche - genutzte_flaeche
        verschnitt_prozent = (verschnitt_flaeche / gesamt_platten_flaeche * 100) if gesamt_platten_flaeche > 0 else 0

        return {
            "teile_anzahl": len(teile),
            "platten_benötigt": platten_benötigt,
            "platten_format": f"{platte_laenge:.0f} x {platte_breite:.0f} mm",
            "flaeche_teile_m2": round(genutzte_flaeche / 1_000_000, 2),
            "flaeche_platten_m2": round(gesamt_platten_flaeche / 1_000_000, 2),
            "verschnitt_m2": round(verschnitt_flaeche / 1_000_000, 2),
            "verschnitt_prozent": round(verschnitt_prozent, 1),
            "hinweis": "Schaetzung. Praezises Nesting ueber BetterNest (CAMPUS) empfohlen.",
        }

    # ------------------------------------------------------------------
    # 6. CNC-Zeitberechnung (praezise aus HOP/MPR-Daten)
    # ------------------------------------------------------------------

    async def _cnc_zeitberechnung(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Berechnet CNC-Zeiten aus geparsten HOP/MPR-Daten.

        Erwartet payload mit:
        - hop_dateien: Liste von {datei_pfad, menge} (HOP-Dateien pro Position)
        - ruestzeit_min: Ruestzeit pro Auftragswechsel (Default: 30)
        - stundensatz: CNC-Stundensatz (Default: 85 EUR/h)
        """
        hop_dateien = payload.get("hop_dateien", [])
        ruestzeit_min = float(payload.get("ruestzeit_min", 30))
        stundensatz = float(payload.get("stundensatz", 85))

        positionen_zeiten: list[dict] = []
        gesamt_zeit_min = ruestzeit_min  # Grundruestzeit

        for hop_entry in hop_dateien:
            datei_pfad = hop_entry.get("datei_pfad", "")
            menge = int(hop_entry.get("menge", 1))

            # HOP parsen
            hop_daten = await self._parse_hop({"datei_pfad": datei_pfad}, projekt_id)
            if "error" in hop_daten:
                continue

            zeit_pro_teil = hop_daten["zeitschaetzung"]["bearbeitungszeit_min"]
            zeit_gesamt = zeit_pro_teil * menge

            positionen_zeiten.append({
                "datei": hop_daten["datei"],
                "menge": menge,
                "zeit_pro_teil_min": zeit_pro_teil,
                "zeit_gesamt_min": round(zeit_gesamt, 1),
                "bohrungen": hop_daten["bearbeitungen"]["bohrungen_gesamt"],
                "fraes_laenge_mm": hop_daten["bearbeitungen"]["fraes_laenge_mm"],
            })
            gesamt_zeit_min += zeit_gesamt

        gesamt_zeit_h = gesamt_zeit_min / 60
        cnc_kosten = gesamt_zeit_h * stundensatz

        return {
            "positionen": positionen_zeiten,
            "ruestzeit_min": ruestzeit_min,
            "gesamt_bearbeitungszeit_min": round(gesamt_zeit_min, 1),
            "gesamt_bearbeitungszeit_h": round(gesamt_zeit_h, 2),
            "stundensatz": stundensatz,
            "cnc_kosten": round(cnc_kosten, 2),
            "quelle": "nchops_praezise",
        }

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _schaetze_bearbeitungszeit(
        self,
        bohrungen: int = 0,
        fraes_laenge_mm: float = 0,
        saege_laenge_mm: float = 0,
        werkzeug_wechsel: int = 0,
    ) -> float:
        """Schaetzt die CNC-Bearbeitungszeit in Minuten.

        Erfahrungswerte Holzher Nextec 7707:
        - Bohrung: ~2 Sekunden (inkl. Positionierung)
        - Fraesen: ~15mm/Sekunde Vorschub (bei Holz)
        - Saegen: ~20mm/Sekunde
        - Werkzeugwechsel: ~8 Sekunden
        - Grundzeit (Platte aufspannen): ~30 Sekunden
        """
        zeit_sek = 30.0  # Grundzeit

        zeit_sek += bohrungen * 2.0
        zeit_sek += fraes_laenge_mm / 15.0  # 15mm/s Vorschub
        zeit_sek += saege_laenge_mm / 20.0  # 20mm/s
        zeit_sek += werkzeug_wechsel * 8.0

        return zeit_sek / 60.0  # -> Minuten

    def _add_system32_bohrungen(
        self, hop: Any, laenge: float, breite: float, anzahl: int
    ) -> None:
        """Fuegt System-32-Lochreihen in eine HOP-Datei ein.

        System 32: Standardabstand 32mm fuer Beschlagbohrungen.
        Typische Anordnung: 37mm vom Rand, dann alle 32mm.
        """
        # Einfache vertikale Lochreihen links und rechts
        x_links = 37.0  # Abstand vom linken Rand
        x_rechts = laenge - 37.0
        y_start = 37.0
        raster = 32.0

        bohrungen_pro_reihe = min(
            anzahl // 2,
            int((breite - 2 * y_start) / raster) + 1,
        )

        for i in range(bohrungen_pro_reihe):
            y = y_start + i * raster
            if y > breite - 20:
                break
            # Bohrung links (5mm Durchmesser, 12mm Tiefe, Cycle 0)
            hop.drilling.vertical(x_links, y, 5, 12, 0)
            # Bohrung rechts
            if x_rechts > x_links + 50:
                hop.drilling.vertical(x_rechts, y, 5, 12, 0)


def _parse_num(val: str) -> float:
    """Parst einen String zu float, robust gegen verschiedene Formate."""
    if not val:
        return 0.0
    try:
        cleaned = val.replace(",", ".").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return 0.0
