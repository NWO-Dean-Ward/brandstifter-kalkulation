"""
LernAgent -- Subagent 7 (Memory Layer).

Speichert abgeschlossene Projekte und lernt daraus:
- Historische Preise und Zeiten
- Muster bei Unter-/Ueberkalkulation
- Vorschlaege fuer aehnliche Positionen
- Abweichungsanalyse

Datenbank: SQLite lokal (lernhistorie-Tabelle).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from agents.base_agent import AgentMessage, BaseAgent


# Materialkategorien fuer Aehnlichkeitssuche
MATERIAL_SYNONYME: dict[str, str] = {
    "melamin": "melamin", "melaminharz": "melamin", "melaminbeschichtet": "melamin",
    "mdf": "mdf", "mitteldicht": "mdf",
    "spanplatte": "spanplatte", "span": "spanplatte",
    "multiplex": "multiplex", "schichtholz": "multiplex",
    "eiche": "eiche", "eichenfurnier": "eiche",
    "buche": "buche", "buchenfurnier": "buche",
    "birke": "birke", "birkenmultiplex": "birke",
    "nuss": "nuss", "nussbaum": "nuss", "walnuss": "nuss",
    "ahorn": "ahorn",
    "esche": "esche",
    "corian": "mineralwerkstoff", "mineralwerkstoff": "mineralwerkstoff", "hi-macs": "mineralwerkstoff",
    "granit": "naturstein", "naturstein": "naturstein", "marmor": "naturstein",
    "hpl": "hpl", "schichtstoff": "hpl",
    "glas": "glas",
    "stahl": "metall", "edelstahl": "metall", "aluminium": "metall", "alu": "metall",
}

# Positionstyp-Erkennung aus Kurztext
POSITIONSTYP_KEYWORDS: dict[str, list[str]] = {
    "einbauschrank": ["einbauschrank", "wandschrank", "nischenschrank"],
    "kuechenfront": ["kuechenfront", "kueche", "kuechenschrank"],
    "garderobenschrank": ["garderobe", "garderobenschrank"],
    "regal": ["regal", "regalwand", "buecherregal", "wandregal"],
    "arbeitsplatte": ["arbeitsplatte", "abdeckung", "platte"],
    "tisch": ["tisch", "konferenztisch", "schreibtisch", "esstisch"],
    "tresen": ["tresen", "theke", "empfang", "rezeption"],
    "tuer": ["tuer", "innentuer", "schiebetuer", "drehtuer"],
    "treppe": ["treppe", "stufe", "handlauf", "gelaender"],
    "wandverkleidung": ["wandverkleidung", "paneele", "wandpaneel", "akustik"],
    "deckenverkleidung": ["decke", "deckenverkleidung", "deckenpaneel"],
    "moebel_allgemein": ["schrank", "kommode", "sideboard", "vitrine", "anrichte"],
}


class LernAgent(BaseAgent):
    """Memory Layer -- lernt aus abgeschlossenen Projekten."""

    def __init__(self) -> None:
        super().__init__(name="lern_agent")
        self._db_pfad: str = ""

    def configure(self, db_pfad: str = "data/kalkulation.db") -> None:
        """Konfiguriert Datenbankpfad."""
        self._db_pfad = db_pfad

    def _get_db(self) -> sqlite3.Connection:
        """Erstellt eine synchrone DB-Verbindung."""
        conn = sqlite3.connect(self._db_pfad)
        conn.row_factory = sqlite3.Row
        return conn

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Verarbeitet Lern-Agent-Anfragen.

        Erwartete msg_types:
        - "projekt_speichern": Abgeschlossenes Projekt archivieren
        - "plausibilitaets_check": Kalkulation gegen Historie pruefen
        - "vorschlag": Preisvorschlag basierend auf Historie
        - "abweichungsanalyse": Top-Abweichungen anzeigen
        - "statistik": Zusammenfassung der Lernhistorie
        - "ist_werte_eintragen": Tatsaechliche Werte nachtragen
        """
        msg_type = message.msg_type

        handler_map = {
            "projekt_speichern": self._projekt_speichern,
            "plausibilitaets_check": self._plausibilitaets_check,
            "vorschlag": self._vorschlag,
            "abweichungsanalyse": self._abweichungsanalyse,
            "statistik": self._statistik,
            "ist_werte_eintragen": self._ist_werte_eintragen,
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
    # 1. Projekt speichern
    # ------------------------------------------------------------------

    async def _projekt_speichern(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Speichert ein abgeschlossenes Projekt in der Lern-Datenbank.

        Erwartet payload mit:
        - positionen: Liste der kalkulierten Positionen (optional, sonst aus DB)
        - ergebnis: "gewonnen" | "verloren" | "beauftragt"

        Wenn positionen keine Kostendaten haben, werden sie aus der DB geladen.
        """
        positionen = payload.get("positionen", [])
        ergebnis = payload.get("ergebnis", "beauftragt")
        jetzt = datetime.now().isoformat()

        gespeichert = 0
        conn = self._get_db()
        try:
            # Falls keine Positionen gegeben oder keine Kosten drin:
            # aus der DB laden (dort stehen nach Kalkulation die Preise)
            if not positionen or not any(
                pos.get("materialkosten") or pos.get("einheitspreis") or pos.get("gesamtpreis")
                for pos in positionen
            ):
                db_pos = conn.execute(
                    """SELECT pos_nr, kurztext, langtext, material, menge, einheit,
                              einheitspreis, gesamtpreis, materialkosten, maschinenkosten,
                              lohnkosten, fremdleistungskosten, ist_lackierung
                       FROM positionen WHERE projekt_id = ? ORDER BY pos_nr""",
                    (projekt_id,),
                ).fetchall()
                if db_pos:
                    positionen = [dict(row) for row in db_pos]

            for pos in positionen:
                kurztext = pos.get("kurztext", "")
                material = pos.get("material", "")
                menge = float(pos.get("menge", 0))

                # Positionstyp und Materialkategorie erkennen
                pos_typ = self._erkenne_positionstyp(kurztext)
                mat_kat = self._erkenne_materialkategorie(material)

                # Kalkulierten EP: Wenn einheitspreis vorhanden, direkt nutzen
                ep = float(pos.get("einheitspreis", 0))

                # Sonst aus Einzelkosten berechnen
                if ep == 0 and menge > 0:
                    mat_k = float(pos.get("materialkosten", 0))
                    mas_k = float(pos.get("maschinenkosten", 0))
                    loh_k = float(pos.get("lohnkosten", 0))
                    fl_k = float(pos.get("fremdleistungskosten", 0))
                    ep = (mat_k + mas_k + loh_k + fl_k) / menge

                # Fallback: Gesamtpreis / Menge
                if ep == 0 and menge > 0:
                    gp = float(pos.get("gesamtpreis", 0))
                    if gp > 0:
                        ep = gp / menge

                conn.execute(
                    """INSERT INTO lernhistorie
                       (projekt_id, position_typ, material, menge,
                        kalkulierter_preis, tatsaechlicher_preis, abweichung_prozent,
                        ergebnis, erfasst_am, notizen)
                       VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)""",
                    (
                        projekt_id, pos_typ, mat_kat, menge,
                        round(ep, 2), ergebnis, jetzt,
                        f"{kurztext} | {material}",
                    ),
                )
                gespeichert += 1

            conn.commit()
        finally:
            conn.close()

        self.logger.info(
            "Projekt %s gespeichert: %d Positionen, Ergebnis: %s",
            projekt_id, gespeichert, ergebnis,
        )

        return {
            "status": "gespeichert",
            "positionen_gespeichert": gespeichert,
            "projekt_id": projekt_id,
            "ergebnis": ergebnis,
        }

    # ------------------------------------------------------------------
    # 2. Plausibilitaets-Check
    # ------------------------------------------------------------------

    async def _plausibilitaets_check(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Prueft eine neue Kalkulation gegen historische Daten.

        Vergleicht Einheitspreise pro Positionstyp/Material.
        Warnt bei >20% Abweichung vom historischen Durchschnitt.
        """
        positionen = payload.get("positionen", [])
        kalkulation = payload.get("kalkulation", {})
        warnungen: list[str] = []
        vergleiche: list[dict] = []

        conn = self._get_db()
        try:
            for pos in positionen:
                kurztext = pos.get("kurztext", "")
                material = pos.get("material", "")
                menge = float(pos.get("menge", 0))
                pos_typ = self._erkenne_positionstyp(kurztext)
                mat_kat = self._erkenne_materialkategorie(material)

                # Aktuellen EP berechnen
                ep_aktuell = 0
                if menge > 0:
                    mat_k = float(pos.get("materialkosten", 0))
                    mas_k = float(pos.get("maschinenkosten", 0))
                    loh_k = float(pos.get("lohnkosten", 0))
                    fl_k = float(pos.get("fremdleistungskosten", 0))
                    ep_aktuell = (mat_k + mas_k + loh_k + fl_k) / menge

                if ep_aktuell == 0:
                    continue

                # Historischen Durchschnitt suchen
                hist = self._suche_historisch(conn, pos_typ, mat_kat)
                if hist is None:
                    continue

                avg_preis = hist["durchschnitt_ep"]
                anzahl_projekte = hist["anzahl"]
                abweichung = (ep_aktuell - avg_preis) / avg_preis if avg_preis > 0 else 0

                vergleich = {
                    "pos_nr": pos.get("pos_nr", "?"),
                    "kurztext": kurztext,
                    "ep_aktuell": round(ep_aktuell, 2),
                    "ep_historisch": round(avg_preis, 2),
                    "abweichung_prozent": round(abweichung * 100, 1),
                    "anzahl_referenzen": anzahl_projekte,
                }
                vergleiche.append(vergleich)

                if abs(abweichung) > 0.20:
                    richtung = "hoeher" if abweichung > 0 else "niedriger"
                    warnungen.append(
                        f"Lern-Agent: Pos {pos.get('pos_nr', '?')} ({kurztext}) ist "
                        f"{abs(abweichung * 100):.0f}% {richtung} als historischer Durchschnitt "
                        f"({euro(avg_preis)}/Einheit, {anzahl_projekte} Referenzen)"
                    )

        finally:
            conn.close()

        return {
            "warnungen": warnungen,
            "vergleichsdaten": vergleiche,
        }

    # ------------------------------------------------------------------
    # 3. Vorschlag
    # ------------------------------------------------------------------

    async def _vorschlag(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Gibt Preisvorschlaege basierend auf aehnlichen Altprojekten.

        Erwartet payload mit:
        - kurztext: Positionsbeschreibung
        - material: Materialangabe
        - menge: Geplante Menge
        """
        kurztext = payload.get("kurztext", "")
        material = payload.get("material", "")
        menge = float(payload.get("menge", 1))
        pos_typ = self._erkenne_positionstyp(kurztext)
        mat_kat = self._erkenne_materialkategorie(material)

        conn = self._get_db()
        try:
            # Suche 1: Exakte Typ+Material-Kombination
            vorschlaege = self._finde_aehnliche(conn, pos_typ, mat_kat, menge, limit=5)

            # Suche 2: Nur Typ (breitere Suche falls wenig Ergebnisse)
            if len(vorschlaege) < 3 and pos_typ:
                mehr = self._finde_aehnliche(conn, pos_typ, "", menge, limit=5)
                ids_schon_da = {v["id"] for v in vorschlaege}
                for m in mehr:
                    if m["id"] not in ids_schon_da:
                        vorschlaege.append(m)

            # Durchschnittspreis berechnen
            if vorschlaege:
                avg = sum(v["kalkulierter_preis"] for v in vorschlaege) / len(vorschlaege)
                min_p = min(v["kalkulierter_preis"] for v in vorschlaege)
                max_p = max(v["kalkulierter_preis"] for v in vorschlaege)
            else:
                avg = min_p = max_p = 0

        finally:
            conn.close()

        return {
            "vorschlaege": vorschlaege,
            "empfohlener_ep": round(avg, 2),
            "preisspanne": {"min": round(min_p, 2), "max": round(max_p, 2)},
            "basis": f"{len(vorschlaege)} historische Positionen",
            "position_typ": pos_typ,
            "material_kategorie": mat_kat,
        }

    # ------------------------------------------------------------------
    # 4. Abweichungsanalyse
    # ------------------------------------------------------------------

    async def _abweichungsanalyse(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Analysiert Abweichungen zwischen Kalkulation und Ist-Werten.

        Zeigt Top-Abweicher und Trends.
        """
        limit = int(payload.get("limit", 10))

        conn = self._get_db()
        try:
            # Top-Abweichungen (nur wo Ist-Werte vorliegen)
            cursor = conn.execute(
                """SELECT * FROM lernhistorie
                   WHERE tatsaechlicher_preis > 0
                   ORDER BY ABS(abweichung_prozent) DESC
                   LIMIT ?""",
                (limit,),
            )
            top_abweichungen = []
            for row in cursor.fetchall():
                top_abweichungen.append({
                    "projekt_id": row["projekt_id"],
                    "position_typ": row["position_typ"],
                    "material": row["material"],
                    "kalkuliert": row["kalkulierter_preis"],
                    "tatsaechlich": row["tatsaechlicher_preis"],
                    "abweichung_prozent": row["abweichung_prozent"],
                    "ergebnis": row["ergebnis"],
                    "notizen": row["notizen"],
                })

            # Durchschnittliche Abweichung pro Positionstyp
            cursor = conn.execute(
                """SELECT position_typ,
                          COUNT(*) as anzahl,
                          AVG(abweichung_prozent) as avg_abweichung,
                          AVG(kalkulierter_preis) as avg_kalk_preis
                   FROM lernhistorie
                   WHERE tatsaechlicher_preis > 0
                   GROUP BY position_typ
                   ORDER BY ABS(AVG(abweichung_prozent)) DESC"""
            )
            typ_trends = []
            for row in cursor.fetchall():
                typ_trends.append({
                    "position_typ": row["position_typ"],
                    "anzahl_projekte": row["anzahl"],
                    "avg_abweichung_prozent": round(row["avg_abweichung"], 1),
                    "avg_kalkulierter_preis": round(row["avg_kalk_preis"], 2),
                })

            # Empfehlungen generieren
            empfehlungen = []
            for trend in typ_trends:
                abw = trend["avg_abweichung_prozent"]
                typ = trend["position_typ"]
                if abw > 10:
                    empfehlungen.append(
                        f"'{typ}' wird systematisch unterkalkiert ({abw:+.1f}%). "
                        f"Materialkosten oder Arbeitszeiten erhoehen."
                    )
                elif abw < -10:
                    empfehlungen.append(
                        f"'{typ}' wird systematisch ueberkalkiert ({abw:+.1f}%). "
                        f"Preise koennen wettbewerbsfaehiger kalkuliert werden."
                    )

        finally:
            conn.close()

        return {
            "top_abweichungen": top_abweichungen,
            "typ_trends": typ_trends,
            "empfehlungen": empfehlungen,
        }

    # ------------------------------------------------------------------
    # 5. Statistik
    # ------------------------------------------------------------------

    async def _statistik(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Gibt eine Zusammenfassung der gesamten Lernhistorie."""
        conn = self._get_db()
        try:
            # Gesamtstatistik
            row = conn.execute(
                """SELECT COUNT(*) as gesamt,
                          COUNT(DISTINCT projekt_id) as projekte,
                          AVG(kalkulierter_preis) as avg_ep,
                          SUM(CASE WHEN ergebnis='gewonnen' THEN 1 ELSE 0 END) as gewonnen,
                          SUM(CASE WHEN ergebnis='verloren' THEN 1 ELSE 0 END) as verloren,
                          SUM(CASE WHEN tatsaechlicher_preis > 0 THEN 1 ELSE 0 END) as mit_ist
                   FROM lernhistorie"""
            ).fetchone()

            # Haeufigste Positionstypen
            cursor = conn.execute(
                """SELECT position_typ, COUNT(*) as anzahl,
                          AVG(kalkulierter_preis) as avg_preis
                   FROM lernhistorie
                   GROUP BY position_typ
                   ORDER BY anzahl DESC
                   LIMIT 10"""
            )
            typen = [
                {
                    "typ": r["position_typ"],
                    "anzahl": r["anzahl"],
                    "avg_ep": round(r["avg_preis"], 2),
                }
                for r in cursor.fetchall()
            ]

            # Haeufigste Materialien
            cursor = conn.execute(
                """SELECT material, COUNT(*) as anzahl,
                          AVG(kalkulierter_preis) as avg_preis
                   FROM lernhistorie
                   WHERE material != ''
                   GROUP BY material
                   ORDER BY anzahl DESC
                   LIMIT 10"""
            )
            materialien = [
                {
                    "material": r["material"],
                    "anzahl": r["anzahl"],
                    "avg_ep": round(r["avg_preis"], 2),
                }
                for r in cursor.fetchall()
            ]

            gewonnen = row["gewonnen"] or 0
            verloren = row["verloren"] or 0
            total_ergebnis = gewonnen + verloren
            quote = (gewonnen / total_ergebnis * 100) if total_ergebnis > 0 else 0

        finally:
            conn.close()

        return {
            "gesamt_positionen": row["gesamt"],
            "gesamt_projekte": row["projekte"],
            "durchschnitt_ep": round(row["avg_ep"] or 0, 2),
            "positionen_mit_ist_werten": row["mit_ist"],
            "gewinnquote": {
                "gewonnen": gewonnen,
                "verloren": verloren,
                "quote_prozent": round(quote, 1),
            },
            "haeufigste_typen": typen,
            "haeufigste_materialien": materialien,
        }

    # ------------------------------------------------------------------
    # 6. Ist-Werte eintragen
    # ------------------------------------------------------------------

    async def _ist_werte_eintragen(self, payload: dict, projekt_id: str) -> dict[str, Any]:
        """Traegt tatsaechliche Preise/Ergebnisse nach Projektabschluss ein.

        Erwartet payload mit:
        - projekt_id: ID des Projekts
        - ist_werte: Liste von {position_typ, tatsaechlicher_preis}
        - ergebnis: "gewonnen" | "verloren" (optional, aktualisiert alle)
        """
        ist_werte = payload.get("ist_werte", [])
        ergebnis = payload.get("ergebnis", "")
        aktualisiert = 0

        conn = self._get_db()
        try:
            # Ergebnis-Status aktualisieren
            if ergebnis:
                conn.execute(
                    "UPDATE lernhistorie SET ergebnis = ? WHERE projekt_id = ?",
                    (ergebnis, projekt_id),
                )

            # Ist-Preise eintragen
            for iw in ist_werte:
                tatsaechlich = float(iw.get("tatsaechlicher_preis", 0))
                hist_id = iw.get("id")

                if hist_id:
                    # Per ID aktualisieren
                    cursor = conn.execute(
                        "SELECT kalkulierter_preis FROM lernhistorie WHERE id = ?",
                        (hist_id,),
                    )
                    row = cursor.fetchone()
                    if row and tatsaechlich > 0:
                        kalk = row["kalkulierter_preis"]
                        abweichung = ((tatsaechlich - kalk) / kalk * 100) if kalk > 0 else 0
                        conn.execute(
                            """UPDATE lernhistorie
                               SET tatsaechlicher_preis = ?, abweichung_prozent = ?
                               WHERE id = ?""",
                            (tatsaechlich, round(abweichung, 1), hist_id),
                        )
                        aktualisiert += 1

            conn.commit()
        finally:
            conn.close()

        return {
            "status": "aktualisiert",
            "positionen_aktualisiert": aktualisiert,
            "projekt_id": projekt_id,
        }

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _erkenne_positionstyp(self, kurztext: str) -> str:
        """Erkennt den Positionstyp aus dem Kurztext."""
        text = kurztext.lower()
        for typ, keywords in POSITIONSTYP_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return typ
        return "moebel_allgemein"

    def _erkenne_materialkategorie(self, material: str) -> str:
        """Normalisiert Material auf eine Standardkategorie."""
        if not material:
            return ""
        text = material.lower()
        for keyword, kategorie in MATERIAL_SYNONYME.items():
            if keyword in text:
                return kategorie
        return material.lower().strip()

    def _suche_historisch(
        self, conn: sqlite3.Connection, pos_typ: str, mat_kat: str,
    ) -> dict[str, Any] | None:
        """Sucht historischen Durchschnittspreis fuer Typ+Material."""
        if pos_typ and mat_kat:
            cursor = conn.execute(
                """SELECT AVG(kalkulierter_preis) as avg_preis,
                          COUNT(*) as anzahl,
                          MIN(kalkulierter_preis) as min_preis,
                          MAX(kalkulierter_preis) as max_preis
                   FROM lernhistorie
                   WHERE position_typ = ? AND material = ?""",
                (pos_typ, mat_kat),
            )
        elif pos_typ:
            cursor = conn.execute(
                """SELECT AVG(kalkulierter_preis) as avg_preis,
                          COUNT(*) as anzahl,
                          MIN(kalkulierter_preis) as min_preis,
                          MAX(kalkulierter_preis) as max_preis
                   FROM lernhistorie
                   WHERE position_typ = ?""",
                (pos_typ,),
            )
        else:
            return None

        row = cursor.fetchone()
        if row is None or row["anzahl"] == 0:
            return None

        return {
            "durchschnitt_ep": row["avg_preis"],
            "anzahl": row["anzahl"],
            "min_ep": row["min_preis"],
            "max_ep": row["max_preis"],
        }

    def _finde_aehnliche(
        self,
        conn: sqlite3.Connection,
        pos_typ: str,
        mat_kat: str,
        menge: float,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Findet aehnliche historische Positionen."""
        if pos_typ and mat_kat:
            cursor = conn.execute(
                """SELECT id, projekt_id, position_typ, material, menge,
                          kalkulierter_preis, tatsaechlicher_preis,
                          ergebnis, notizen, erfasst_am
                   FROM lernhistorie
                   WHERE position_typ = ? AND material = ?
                   ORDER BY ABS(menge - ?) ASC
                   LIMIT ?""",
                (pos_typ, mat_kat, menge, limit),
            )
        elif pos_typ:
            cursor = conn.execute(
                """SELECT id, projekt_id, position_typ, material, menge,
                          kalkulierter_preis, tatsaechlicher_preis,
                          ergebnis, notizen, erfasst_am
                   FROM lernhistorie
                   WHERE position_typ = ?
                   ORDER BY ABS(menge - ?) ASC
                   LIMIT ?""",
                (pos_typ, menge, limit),
            )
        else:
            return []

        return [
            {
                "id": r["id"],
                "projekt_id": r["projekt_id"],
                "position_typ": r["position_typ"],
                "material": r["material"],
                "menge": r["menge"],
                "kalkulierter_preis": r["kalkulierter_preis"],
                "tatsaechlicher_preis": r["tatsaechlicher_preis"],
                "ergebnis": r["ergebnis"],
                "notizen": r["notizen"],
                "erfasst_am": r["erfasst_am"],
            }
            for r in cursor.fetchall()
        ]


def euro(val: float) -> str:
    """Formatiert einen Betrag als Euro-String."""
    return f"{val:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
