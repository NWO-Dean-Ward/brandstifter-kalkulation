"""
BildAnalyseAgent -- Analysiert Bilder und 3D-Dateien fuer Preisschaetzung.

Kombiniert:
- Claude Vision API fuer Bild-/Renderinganalyse
- trimesh/numpy-stl fuer 3D-Datei-Parsing (STL, OBJ, 3MF)
- Geometriedaten (Abmessungen, Volumen, Oberflaeche) fuer Kalkulationsvorschlaege

Unterstuetzte Formate:
- Bilder: JPG, PNG, WEBP, GIF
- 3D-Dateien: STL, OBJ, 3MF, PLY, GLTF/GLB
"""

from __future__ import annotations

import io
import json
import logging
import os
from typing import Any

from agents.base_agent import BaseAgent, AgentMessage

logger = logging.getLogger("bild_analyse_agent")

# Unterstuetzte Dateiformate
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MESH_EXTENSIONS = {".stl", ".obj", ".3mf", ".ply", ".gltf", ".glb", ".off"}

# Media-Type Mapping
MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class BildAnalyseAgent(BaseAgent):
    """Agent fuer Bild-/3D-basierte Moebel-Preisschaetzung."""

    def __init__(self, llm_router=None):
        super().__init__(name="bild_analyse_agent")
        self._llm = llm_router
        self._handlers = {
            "analyse_bild": self._analyse_bild,
            "analyse_3d": self._analyse_3d,
            "analyse_datei": self._analyse_datei,
        }

    async def process(self, message: AgentMessage) -> AgentMessage:
        handler = self._handlers.get(message.msg_type)
        if not handler:
            return message.create_error(
                self.name,
                f"Unbekannter Nachrichtentyp: {message.msg_type}. "
                f"Verfuegbar: {', '.join(self._handlers.keys())}",
            )
        result = await handler(message.payload, message.projekt_id)
        return message.create_response(self.name, result)

    async def _analyse_bild(self, payload: dict, projekt_id: str) -> dict:
        """Analysiert ein Bild via Claude Vision API."""
        image_data = payload.get("image_data")  # bytes
        media_type = payload.get("media_type", "image/jpeg")
        zusatz_info = payload.get("zusatz_info", "")

        if not image_data:
            return {"status": "error", "fehler": "Keine Bilddaten uebergeben"}

        if not self._llm:
            return {"status": "error", "fehler": "LLM-Router nicht konfiguriert"}

        result = await self._llm.analyse_bild(
            image_data=image_data,
            media_type=media_type,
            prompt=zusatz_info,
        )

        if result.get("error"):
            return {
                "status": "error",
                "fehler": result["error"],
                "hinweis": "ANTHROPIC_API_KEY in .env Datei setzen",
            }

        analyse = result.get("response", {})
        return {
            "status": "ok",
            "analyse": analyse,
            "modell": result.get("modell", "claude-vision"),
            "tokens": result.get("tokens", 0),
            "input_tokens": result.get("input_tokens", 0),
        }

    async def _analyse_3d(self, payload: dict, projekt_id: str) -> dict:
        """Analysiert eine 3D-Datei und extrahiert Geometriedaten."""
        file_data = payload.get("file_data")  # bytes
        dateiname = payload.get("dateiname", "model.stl")

        if not file_data:
            return {"status": "error", "fehler": "Keine 3D-Daten uebergeben"}

        ext = os.path.splitext(dateiname)[1].lower()
        if ext not in MESH_EXTENSIONS:
            return {
                "status": "error",
                "fehler": f"Nicht unterstuetztes Format: {ext}. Unterstuetzt: {', '.join(MESH_EXTENSIONS)}",
            }

        geometrie = self._parse_3d_datei(file_data, dateiname)
        if geometrie.get("fehler"):
            return {"status": "error", "fehler": geometrie["fehler"]}

        # Kalkulationsvorschlag aus Geometrie ableiten
        vorschlag = self._geometrie_zu_kalkulation(geometrie)

        return {
            "status": "ok",
            "geometrie": geometrie,
            "kalkulations_vorschlag": vorschlag,
        }

    async def _analyse_datei(self, payload: dict, projekt_id: str) -> dict:
        """Erkennt den Dateityp und leitet an die richtige Analyse weiter."""
        file_data = payload.get("file_data")  # bytes
        dateiname = payload.get("dateiname", "")
        zusatz_info = payload.get("zusatz_info", "")

        if not file_data or not dateiname:
            return {"status": "error", "fehler": "Keine Datei uebergeben"}

        ext = os.path.splitext(dateiname)[1].lower()

        # Bild -> Claude Vision
        if ext in IMAGE_EXTENSIONS:
            media_type = MEDIA_TYPES.get(ext, "image/jpeg")
            result = await self._analyse_bild({
                "image_data": file_data,
                "media_type": media_type,
                "zusatz_info": zusatz_info,
            }, projekt_id)

            # Bei Bildern: Geometrie aus der KI-Analyse extrahieren
            if result.get("status") == "ok" and result.get("analyse"):
                analyse = result["analyse"]
                abm = analyse.get("abmessungen", {})
                if abm:
                    result["geometrie"] = {
                        "laenge_mm": abm.get("laenge_mm", 0),
                        "breite_mm": abm.get("breite_mm", 0),
                        "hoehe_mm": abm.get("hoehe_mm", 0),
                        "quelle": "ki_schaetzung",
                    }
            return result

        # 3D-Datei -> trimesh
        if ext in MESH_EXTENSIONS:
            result_3d = await self._analyse_3d({
                "file_data": file_data,
                "dateiname": dateiname,
            }, projekt_id)

            # Optional: 3D-Vorschau als Bild rendern und an Claude senden
            # (Nicht implementiert - benoetigt pyrender/pyglet)
            return result_3d

        return {
            "status": "error",
            "fehler": f"Nicht unterstuetztes Format: {ext}",
            "unterstuetzt": {
                "bilder": list(IMAGE_EXTENSIONS),
                "3d": list(MESH_EXTENSIONS),
            },
        }

    def _parse_3d_datei(self, file_data: bytes, dateiname: str) -> dict:
        """Parst eine 3D-Datei mit trimesh und extrahiert Geometriedaten."""
        try:
            import trimesh

            # trimesh aus bytes laden
            file_obj = io.BytesIO(file_data)
            ext = os.path.splitext(dateiname)[1].lower()

            mesh = trimesh.load(
                file_obj,
                file_type=ext.lstrip("."),
                force="mesh",
            )

            if isinstance(mesh, trimesh.Scene):
                # Scene -> alle Meshes zusammenfuegen
                meshes = list(mesh.geometry.values())
                if not meshes:
                    return {"fehler": "3D-Datei enthaelt keine Geometrie"}
                mesh = trimesh.util.concatenate(meshes)

            # Bounding Box
            bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
            extents = mesh.bounding_box.extents  # [width, height, depth]

            # Sortiere: Laenge >= Breite >= Hoehe
            dims = sorted(extents, reverse=True)

            return {
                "laenge_mm": round(dims[0], 1),
                "breite_mm": round(dims[1], 1),
                "hoehe_mm": round(dims[2], 1),
                "volumen_cm3": round(mesh.volume / 1000, 2) if mesh.is_watertight else None,
                "oberflaeche_qm": round(mesh.area / 1000000, 4),
                "ist_wasserdicht": mesh.is_watertight,
                "anzahl_faces": len(mesh.faces),
                "anzahl_vertices": len(mesh.vertices),
                "anzahl_bodies": 1,
                "quelle": "trimesh",
            }

        except Exception as exc:
            logger.error("3D-Parse Fehler (%s): %s", dateiname, exc)
            return {"fehler": f"3D-Datei konnte nicht gelesen werden: {exc}"}

    def _geometrie_zu_kalkulation(self, geo: dict) -> dict:
        """Leitet aus Geometriedaten einen Kalkulationsvorschlag ab."""
        laenge = geo.get("laenge_mm", 0) or 0
        breite = geo.get("breite_mm", 0) or 0
        hoehe = geo.get("hoehe_mm", 0) or 0
        oberflaeche = geo.get("oberflaeche_qm", 0) or 0

        # Abmessungen in m
        l_m = laenge / 1000
        b_m = breite / 1000
        h_m = hoehe / 1000

        # Plattenflaeche schaetzen (grob: 2x Seitenflaechen + Boden + Deckel + Rueckwand)
        platten_qm = 2 * (l_m * h_m) + 2 * (b_m * h_m) + (l_m * b_m) + (l_m * b_m)

        # Kantenlaenge schaetzen (alle sichtbaren Kanten)
        kanten_lfm = 4 * l_m + 4 * b_m + 4 * h_m

        # Komplexitaet schaetzen
        if oberflaeche > 5:
            komplexitaet = "komplex"
        elif oberflaeche > 2:
            komplexitaet = "mittel"
        else:
            komplexitaet = "einfach"

        # Arbeitsstunden-Schaetzung
        stunden_basis = {
            "einfach": {"werkstatt": 8, "cnc": 2, "oberflaeche": 2, "montage": 4},
            "mittel": {"werkstatt": 16, "cnc": 4, "oberflaeche": 4, "montage": 8},
            "komplex": {"werkstatt": 32, "cnc": 8, "oberflaeche": 8, "montage": 12},
        }
        stunden = stunden_basis.get(komplexitaet, stunden_basis["mittel"])

        return {
            "platten_qm_schaetzung": round(platten_qm, 2),
            "kanten_lfm_schaetzung": round(kanten_lfm, 1),
            "komplexitaet": komplexitaet,
            "arbeitsstunden_schaetzung": stunden,
            "hinweis": "Grobe Schaetzung aus Geometriedaten. Preise manuell anpassen!",
        }
