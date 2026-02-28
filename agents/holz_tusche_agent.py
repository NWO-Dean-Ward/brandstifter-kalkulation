"""
HolzTuscheAgent -- Preisabfrage bei Holz-Tusche (holztusche.de).

Holz-Tusche ist ein Shopware-basierter B2B-Holzhandel-Onlineshop.
Preise sind nur fuer eingeloggte Geschaeftskunden sichtbar -> Playwright-Login noetig.

Funktionen:
- Einzelsuche: Produkt per Suchbegriff finden (z.B. Dekor-Nr "H1345")
- Komplett-Sync: Alle Plattenwerkstoffe scrapen -> materialpreise DB

Sicherheit:
- Login-Credentials Fernet-verschluesselt (config/partner-logins.yaml)
- Kauft NIEMALS automatisch ein
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from agents.base_agent import BaseAgent, AgentMessage

logger = logging.getLogger(__name__)


def _parse_german_price(text: str) -> float:
    """Parst deutschen Preis-String (z.B. '12,99 EUR' oder '1.234,56')."""
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.,]", "", text)
    if not cleaned:
        return 0.0
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


class HolzTuscheAgent(BaseAgent):
    """Preisrecherche bei Holz-Tusche (holztusche.de) per Playwright."""

    def __init__(self):
        super().__init__("holz_tusche")
        self._browser = None
        self._context = None
        self._playwright_instance = None
        self._db_pfad = "data/kalkulation.db"
        self._username = ""
        self._password = ""
        self._logged_in = False

    def configure(self, db_pfad: str = "data/kalkulation.db",
                  logins: dict | None = None) -> None:
        """Konfiguriert DB-Pfad und Login-Credentials."""
        self._db_pfad = db_pfad
        if logins:
            self._username = logins.get("username", "")
            self._password = logins.get("password", "")

    async def _ensure_browser(self):
        """Startet Playwright-Browser falls noetig."""
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright_instance = await async_playwright().start()
            self._browser = await self._playwright_instance.chromium.launch(headless=True)
            self._context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                locale="de-DE",
            )
            self._logged_in = False
            logger.info("Playwright-Browser gestartet (HolzTusche)")
        except ImportError:
            logger.warning("Playwright nicht installiert")
            raise RuntimeError("Playwright nicht installiert. Bitte: pip install playwright && playwright install chromium")

    async def _close_browser(self):
        """Schliesst den Browser und setzt Login-Status zurueck."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright_instance:
            await self._playwright_instance.stop()
            self._playwright_instance = None
        self._logged_in = False

    async def _dismiss_cookie_banner(self, page):
        """Versucht Cookie-Banner wegzuklicken (Shopware-typisch)."""
        selectors = [
            "button.js-cookie-configuration-button[data-action='allowAll']",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Alle Cookies akzeptieren')",
            "button:has-text('Akzeptieren')",
            ".cookie-permission-container button.btn-primary",
            "[data-testid='cookie-accept']",
        ]
        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    async def _login(self, page):
        """Loggt sich bei holztusche.de ein (Session-Cookie bleibt im Context)."""
        if self._logged_in:
            return

        if not self._username or not self._password:
            raise RuntimeError("Holz-Tusche Login-Credentials nicht konfiguriert. "
                               "Bitte: AppConfig().save_partner_login('holz_tusche', 'email', 'passwort')")

        logger.info("Holz-Tusche Login starten...")
        await page.goto("https://www.holztusche.de/account/login", timeout=20000)
        await page.wait_for_load_state("domcontentloaded")
        await self._dismiss_cookie_banner(page)
        await page.wait_for_timeout(500)

        # E-Mail und Passwort ausfuellen (Shopware 6 Login-Formular)
        email_selectors = [
            "#loginMail",
            "input[name='email']",
            "input[type='email']",
            "input[autocomplete='email']",
        ]
        for sel in email_selectors:
            email_field = await page.query_selector(sel)
            if email_field:
                await email_field.fill(self._username)
                break
        else:
            raise RuntimeError("Login-Formular: E-Mail-Feld nicht gefunden")

        pw_selectors = [
            "#loginPassword",
            "input[name='password']",
            "input[type='password']",
        ]
        for sel in pw_selectors:
            pw_field = await page.query_selector(sel)
            if pw_field:
                await pw_field.fill(self._password)
                break
        else:
            raise RuntimeError("Login-Formular: Passwort-Feld nicht gefunden")

        # Login-Button klicken
        login_selectors = [
            "button[type='submit']:has-text('Anmelden')",
            "button:has-text('Anmelden')",
            "button.login-submit",
            "#loginForm button[type='submit']",
            "form button[type='submit']",
        ]
        for sel in login_selectors:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                break
        else:
            raise RuntimeError("Login-Formular: Anmelden-Button nicht gefunden")

        # Warte auf Redirect (erfolgreicher Login -> Dashboard oder Startseite)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1000)

        # Pruefen ob Login erfolgreich (kein /login mehr in URL)
        current_url = page.url
        if "/account/login" in current_url:
            # Fehler-Meldung auf der Seite pruefen
            error_msg = "Unbekannter Login-Fehler"
            error_els = await page.query_selector_all(".alert-danger")
            for el in error_els:
                text = (await el.inner_text()).strip()
                if text:
                    error_msg = text
                    break
            raise RuntimeError(f"Holz-Tusche Login fehlgeschlagen: {error_msg}")

        self._logged_in = True
        logger.info("Holz-Tusche Login erfolgreich")

    async def _suche_produkt(self, suchbegriff: str) -> list[dict]:
        """Sucht ein Produkt bei holztusche.de und gibt Treffer zurueck."""
        await self._ensure_browser()
        page = await self._context.new_page()
        treffer = []

        try:
            await self._login(page)

            url = f"https://www.holztusche.de/search?search={quote_plus(suchbegriff)}"
            await page.goto(url, timeout=20000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1500)

            # Shopware 6 Produkt-Karten (mehrere Selektor-Varianten)
            item_selectors = [
                ".product-box",
                ".cms-listing-col",
                ".card.product-box",
                "[data-product-id]",
                ".product-info",
            ]

            items = []
            for sel in item_selectors:
                items = await page.query_selector_all(sel)
                if items:
                    break

            if not items:
                logger.info("Holz-Tusche: Keine Ergebnisse fuer '%s'", suchbegriff)
                return []

            for item in items[:20]:
                try:
                    eintrag = await self._parse_produkt_card(item)
                    if eintrag and eintrag.get("titel"):
                        treffer.append(eintrag)
                except Exception as e:
                    logger.debug("Holz-Tusche Parse-Fehler: %s", e)
                    continue

            logger.info("Holz-Tusche Suche '%s': %d Treffer", suchbegriff, len(treffer))

        except Exception as e:
            logger.warning("Holz-Tusche Suche-Fehler: %s", e)
            raise
        finally:
            await page.close()

        return treffer

    async def _parse_produkt_card(self, item) -> dict:
        """Extrahiert Daten aus einer Holz-Tusche Produkt-Karte (Shopware 6)."""
        import json as _json

        # Card-Container (.card.product-box) ggf. innerhalb von .cms-listing-col
        card = await item.query_selector(".card.product-box")
        if not card:
            card = item

        # Titel aus data-data-layer-items JSON oder aus dem Link-Title
        titel = ""
        artikel_nr = ""
        hersteller = ""
        data_layer = await card.get_attribute("data-data-layer-items")
        if data_layer:
            try:
                dl = _json.loads(data_layer)
                titel = dl.get("item_name", "")
                artikel_nr = dl.get("item_id", "")
                hersteller = dl.get("item_brand", "")
            except (ValueError, TypeError):
                pass

        # Fallback: Titel aus Link
        if not titel:
            for sel in [".product-name a", ".product-image-link", "a[title]"]:
                el = await card.query_selector(sel)
                if el:
                    titel = (await el.get_attribute("title") or "").strip()
                    if not titel:
                        titel = (await el.inner_text()).strip()
                    if titel:
                        break

        # Preis (B2B, dynamisch geladen - aus .product-price Element)
        preis = 0.0
        for sel in [".product-price", ".product-price-wrapper .product-price",
                    "[class*='price-loader'] .product-price"]:
            el = await card.query_selector(sel)
            if el:
                preis_text = (await el.inner_text()).strip()
                preis = _parse_german_price(preis_text)
                if preis > 0:
                    break

        # Einheit aus der Preis-Info (z.B. "12,50 € / qm")
        einheit = ""
        price_info = await card.query_selector(".product-price-info, .hotu-price-loader-pri")
        if price_info:
            info_text = (await price_info.inner_text()).strip()
            if "/ qm" in info_text:
                einheit = "qm"
            elif "/ lfm" in info_text:
                einheit = "lfm"
            elif "/ Stk" in info_text.lower() or "/ stk" in info_text:
                einheit = "Stk"
            elif "/ Platte" in info_text:
                einheit = "Platte"

        # Link
        link = ""
        link_el = await card.query_selector(".product-image-link, .product-name a, a[href*='/']")
        if link_el:
            link = await link_el.get_attribute("href") or ""
            if link and not link.startswith("http"):
                link = f"https://www.holztusche.de{link}"

        # Dekor-Nr aus dem Titel extrahieren (z.B. "H1345", "W1000", "U999")
        dekor_nr = ""
        dekor_match = re.search(r"\b([HWUFS]\d{3,5})\b", titel, re.IGNORECASE)
        if dekor_match:
            dekor_nr = dekor_match.group(1).upper()

        # Abmessungen aus Card-Text extrahieren
        abmessungen = ""
        card_text = await card.inner_text()
        laenge_m = re.search(r"L.nge\s*\(mm\)\s*([\d.]+)", card_text)
        breite_m = re.search(r"Breite\s*\(mm\)\s*([\d.]+)", card_text)
        staerke_m = re.search(r"St.rke\s*\(mm\)\s*([\d.,]+)", card_text)
        if laenge_m and breite_m:
            abmessungen = f"{laenge_m.group(1)}x{breite_m.group(1)}"
            if staerke_m:
                abmessungen += f"x{staerke_m.group(1)}"
            abmessungen += "mm"

        return {
            "quelle": "holz_tusche",
            "titel": titel,
            "preis": preis,
            "artikel_nr": artikel_nr,
            "hersteller": hersteller,
            "dekor_nr": dekor_nr,
            "abmessungen": abmessungen,
            "einheit": einheit or "qm",
            "link": link,
            "waehrung": "EUR",
        }

    async def _sync_alle_platten(self) -> dict:
        """Scrapt alle Plattenwerkstoffe und speichert in materialpreise DB."""
        import aiosqlite

        await self._ensure_browser()
        page = await self._context.new_page()
        alle_produkte = []

        try:
            await self._login(page)

            # Hauptkategorien fuer Plattenwerkstoffe (von holztusche.de)
            kategorie_urls = [
                "/plattenwerkstoffe/spanplatten/dekorbeschichtet/",
                "/plattenwerkstoffe/spanplatten/roh/",
                "/plattenwerkstoffe/spanplatten/leicht/",
                "/plattenwerkstoffe/mdf-platten/roh/",
                "/plattenwerkstoffe/mdf-platten/dekorbeschichtet/",
                "/plattenwerkstoffe/mdf-platten/grundierfolienbeschichtet/",
                "/plattenwerkstoffe/multiplexplatten/",
                "/plattenwerkstoffe/sperrholz/roh/",
                "/plattenwerkstoffe/hdf-platten/",
                "/plattenwerkstoffe/kompaktplatten/interieur/",
                "/plattenwerkstoffe/arbeitsplatten/",
                "/plattenwerkstoffe/schichtstoffplatten/dekorbeschichtet/",
                "/plattenwerkstoffe/leimholzplatten/3-schicht/",
                "/plattenwerkstoffe/tischlerplatten/",
            ]

            for kat_url in kategorie_urls:
                try:
                    produkte = await self._scrape_kategorie(page, kat_url)
                    alle_produkte.extend(produkte)
                except Exception as e:
                    logger.warning("Holz-Tusche Kategorie %s Fehler: %s", kat_url, e)
                    continue

            # Duplikate entfernen (nach Titel + Preis)
            gesehen = set()
            unique_produkte = []
            for p in alle_produkte:
                key = f"{p['titel']}_{p['preis']}"
                if key not in gesehen:
                    gesehen.add(key)
                    unique_produkte.append(p)

            # In DB speichern (versioniert)
            now = datetime.now().isoformat()
            stats = {"gesamt": len(unique_produkte), "neu": 0, "aktualisiert": 0, "unveraendert": 0}

            async with aiosqlite.connect(self._db_pfad) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("PRAGMA foreign_keys = ON")

                for p in unique_produkte:
                    if p["preis"] <= 0:
                        continue

                    # Existierenden aktiven Eintrag suchen
                    cursor = await db.execute(
                        """SELECT id, preis FROM materialpreise
                           WHERE material_name = ? AND lieferant = 'holz_tusche'
                           AND gueltig_bis = ''
                           ORDER BY gueltig_ab DESC LIMIT 1""",
                        (p["titel"],),
                    )
                    row = await cursor.fetchone()

                    if row:
                        alter_preis = row["preis"]
                        if abs(alter_preis - p["preis"]) < 0.01:
                            stats["unveraendert"] += 1
                            continue
                        # Alten Eintrag archivieren
                        await db.execute(
                            "UPDATE materialpreise SET gueltig_bis = ? WHERE id = ?",
                            (now, row["id"]),
                        )
                        stats["aktualisiert"] += 1
                    else:
                        stats["neu"] += 1

                    # Kategorie bestimmen
                    kategorie = self._bestimme_kategorie(p["titel"])

                    # Neuen Eintrag
                    await db.execute(
                        """INSERT INTO materialpreise
                           (material_name, kategorie, lieferant, artikel_nr, einheit,
                            preis, gueltig_ab, gueltig_bis, notizen)
                           VALUES (?, ?, 'holz_tusche', ?, ?, ?, ?, '', ?)""",
                        (
                            p["titel"],
                            kategorie,
                            p.get("artikel_nr", ""),
                            p.get("einheit", "") or "Platte",
                            p["preis"],
                            now,
                            f"Dekor: {p.get('dekor_nr', '')} | Abm: {p.get('abmessungen', '')}",
                        ),
                    )

                await db.commit()

            logger.info("Holz-Tusche Sync abgeschlossen: %s", stats)

        except Exception as e:
            logger.error("Holz-Tusche Sync Fehler: %s", e)
            raise
        finally:
            await page.close()

        return stats

    async def _scrape_kategorie(self, page, kat_url: str) -> list[dict]:
        """Scrapt eine Kategorie inkl. Pagination."""
        produkte = []
        seite = 1
        max_seiten = 20  # Sicherheitslimit

        base_url = f"https://www.holztusche.de{kat_url}"

        while seite <= max_seiten:
            url = f"{base_url}?p={seite}" if seite > 1 else base_url
            logger.info("Holz-Tusche Kategorie: %s (Seite %d)", kat_url, seite)

            try:
                await page.goto(url, timeout=20000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1000)
            except Exception as e:
                logger.warning("Seite %d nicht ladbar: %s", seite, e)
                break

            # Produkte auf dieser Seite
            item_selectors = [
                ".product-box",
                ".cms-listing-col",
                ".card.product-box",
                "[data-product-id]",
            ]

            items = []
            for sel in item_selectors:
                items = await page.query_selector_all(sel)
                if items:
                    break

            if not items:
                break

            for item in items:
                try:
                    eintrag = await self._parse_produkt_card(item)
                    if eintrag and eintrag.get("titel"):
                        produkte.append(eintrag)
                except Exception:
                    continue

            # Naechste Seite vorhanden?
            next_selectors = [
                "a.page-next",
                ".pagination-nav .page-next",
                "a[rel='next']",
                ".pagination .next a",
            ]
            hat_naechste = False
            for sel in next_selectors:
                next_btn = await page.query_selector(sel)
                if next_btn:
                    hat_naechste = True
                    break

            if not hat_naechste:
                break

            seite += 1

        return produkte

    def _bestimme_kategorie(self, titel: str) -> str:
        """Bestimmt die Materialkategorie anhand des Titels."""
        titel_lower = titel.lower()
        if any(k in titel_lower for k in ["spanplatte", "span", "melamin", "dekorspan"]):
            return "platte"
        if any(k in titel_lower for k in ["mdf", "mitteldicht"]):
            return "platte"
        if any(k in titel_lower for k in ["multiplex", "birke multiplex", "buche multiplex"]):
            return "platte"
        if any(k in titel_lower for k in ["sperrholz", "sperr"]):
            return "platte"
        if any(k in titel_lower for k in ["hdf", "hartfaser"]):
            return "platte"
        if any(k in titel_lower for k in ["arbeitsplatte", "küchenplatte"]):
            return "platte"
        if any(k in titel_lower for k in ["kompaktplatte", "kompakt", "hpl"]):
            return "platte"
        if any(k in titel_lower for k in ["kante", "abs", "umleimer"]):
            return "kante"
        if any(k in titel_lower for k in ["beschlag", "scharnier", "schublade"]):
            return "beschlag"
        return "platte"

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Verarbeitet eingehende Nachrichten."""
        handlers = {
            "holz_tusche_suche": self._handle_suche,
            "holz_tusche_sync": self._handle_sync,
        }

        handler = handlers.get(message.msg_type)
        if not handler:
            return message.create_error(
                self.name,
                f"Unbekannter msg_type: {message.msg_type}",
                {"verfuegbare_typen": list(handlers.keys())},
            )

        result = await handler(message.payload)
        return message.create_response(self.name, result)

    async def _handle_suche(self, payload: dict) -> dict:
        """Handler fuer Einzelsuche."""
        suchbegriff = payload.get("suchbegriff", "").strip()
        if not suchbegriff:
            return {"status": "error", "message": "Suchbegriff erforderlich"}

        try:
            treffer = await self._suche_produkt(suchbegriff)
            return {
                "status": "ok",
                "suchbegriff": suchbegriff,
                "treffer": treffer,
                "anzahl": len(treffer),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            await self._close_browser()

    async def _handle_sync(self, payload: dict) -> dict:
        """Handler fuer Komplett-Sync aller Plattenwerkstoffe."""
        try:
            stats = await self._sync_alle_platten()
            return {"status": "ok", **stats}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            await self._close_browser()
