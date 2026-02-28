"""
EinkaufsAgent (#11) – Preisrecherche per Playwright-Browser-Automation.

Recherchiert Preise bei:
- Haefele (haefele.de)
- Blum (blum.com)
- Egger (egger.com)
- Amazon (amazon.de)
- Google Shopping

Sicherheit:
- Fernet-verschluesselte Partner-Logins
- Kauft NIEMALS automatisch ein
- Alle Ergebnisse als Vorschlaege, kein Auto-Checkout
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from agents.base_agent import BaseAgent, AgentMessage

logger = logging.getLogger(__name__)


class EinkaufsAgent(BaseAgent):
    """Preisrecherche-Agent mit Playwright-Browser-Automation."""

    def __init__(self, llm_router=None):
        super().__init__("einkaufs_agent")
        self._browser = None
        self._context = None
        self._logins: dict[str, dict] = {}
        self._db_pfad = "data/kalkulation.db"
        self._llm = llm_router

    def configure(self, db_pfad: str = "data/kalkulation.db", logins: dict | None = None) -> None:
        self._db_pfad = db_pfad
        if logins:
            self._logins = logins

    async def _ensure_browser(self):
        """Startet Playwright-Browser falls noetig."""
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                locale="de-DE",
            )
            logger.info("Playwright-Browser gestartet")
        except ImportError:
            logger.warning("Playwright nicht installiert. Bitte: pip install playwright && playwright install chromium")
            raise RuntimeError("Playwright nicht installiert")

    async def _dismiss_cookie_banner(self, page):
        """Versucht Cookie-Banner wegzuklicken (Google/Amazon/Haefele)."""
        selectors = [
            # Google
            "button#L2AGLb",
            "[aria-label='Alle akzeptieren']",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Alle annehmen')",
            # Amazon
            "#sp-cc-accept",
            "input[name='accept']",
            # Generic
            "[data-testid='cookie-accept']",
            "button:has-text('Akzeptieren')",
            "button:has-text('Accept')",
            "button:has-text('Zustimmen')",
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

    async def _close_browser(self):
        """Schliesst den Browser."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def process(self, message: AgentMessage) -> AgentMessage:
        handlers = {
            "preis_recherche": self._recherche_einzeln,
            "preis_recherche_batch": self._recherche_batch,
            "haefele_suche": self._suche_haefele,
            "amazon_suche": self._suche_amazon,
            "google_shopping": self._suche_google_shopping,
            "ergebnis_speichern": self._ergebnis_speichern,
        }

        handler = handlers.get(message.msg_type)
        if not handler:
            return message.create_error(
                self.name,
                f"Unbekannter msg_type: {message.msg_type}",
                {"verfuegbare_typen": list(handlers.keys())},
            )

        result = await handler(message.payload, message.projekt_id)
        return message.create_response(self.name, result)

    # --- Einzelrecherche ---

    async def _recherche_einzeln(self, payload: dict, projekt_id: str) -> dict:
        """Recherchiert Preis fuer ein einzelnes Produkt."""
        bezeichnung = payload.get("bezeichnung", "")
        hersteller = payload.get("hersteller", "")
        artikel_nr = payload.get("artikel_nr", "")
        quellen = payload.get("quellen", ["google_shopping", "amazon"])

        if not bezeichnung and not artikel_nr:
            return {"status": "error", "message": "Bezeichnung oder Artikel-Nr erforderlich"}

        suchbegriff = f"{hersteller} {artikel_nr} {bezeichnung}".strip()
        ergebnisse = []

        for quelle in quellen:
            try:
                if quelle == "haefele":
                    treffer = await self._scrape_haefele(suchbegriff, artikel_nr)
                elif quelle == "amazon":
                    treffer = await self._scrape_amazon(suchbegriff)
                elif quelle == "google_shopping":
                    treffer = await self._scrape_google_shopping(suchbegriff)
                elif quelle == "blum":
                    treffer = await self._scrape_blum(suchbegriff, artikel_nr)
                elif quelle == "egger":
                    treffer = await self._scrape_egger(suchbegriff)
                else:
                    continue
                ergebnisse.extend(treffer)
            except Exception as e:
                logger.warning("Fehler bei %s-Suche: %s", quelle, e)
                ergebnisse.append({
                    "quelle": quelle,
                    "status": "fehler",
                    "fehler": str(e),
                })

        # Nach Preis sortieren (guenstigster zuerst)
        preis_ergebnisse = [e for e in ergebnisse if e.get("preis", 0) > 0]
        preis_ergebnisse.sort(key=lambda x: x.get("preis", float("inf")))
        fehler_ergebnisse = [e for e in ergebnisse if e.get("status") == "fehler"]

        # KI-Fallback: Wenn kein Scraping-Treffer, Claude nach Preis fragen
        if not preis_ergebnisse and self._llm:
            ki_treffer = await self._ki_preisschaetzung(suchbegriff, bezeichnung, hersteller)
            if ki_treffer:
                preis_ergebnisse.extend(ki_treffer)

        return {
            "status": "ok",
            "suchbegriff": suchbegriff,
            "treffer": preis_ergebnisse,
            "fehler": fehler_ergebnisse,
            "anzahl_treffer": len(preis_ergebnisse),
            "guenstigster": preis_ergebnisse[0] if preis_ergebnisse else None,
        }

    # --- Batch-Recherche ---

    async def _recherche_batch(self, payload: dict, projekt_id: str) -> dict:
        """Recherchiert Preise fuer mehrere Produkte."""
        produkte = payload.get("produkte", [])
        quellen = payload.get("quellen", ["google_shopping", "amazon"])

        ergebnisse = []
        for produkt in produkte:
            produkt["quellen"] = quellen
            result = await self._recherche_einzeln(produkt, projekt_id)
            ergebnisse.append({
                "bezeichnung": produkt.get("bezeichnung", ""),
                "artikel_nr": produkt.get("artikel_nr", ""),
                **result,
            })

        return {
            "status": "ok",
            "anzahl": len(ergebnisse),
            "ergebnisse": ergebnisse,
        }

    # --- Haefele ---

    async def _suche_haefele(self, payload: dict, projekt_id: str) -> dict:
        suchbegriff = payload.get("suchbegriff", "")
        artikel_nr = payload.get("artikel_nr", "")
        treffer = await self._scrape_haefele(suchbegriff, artikel_nr)
        return {"status": "ok", "quelle": "haefele", "treffer": treffer}

    async def _scrape_haefele(self, suchbegriff: str, artikel_nr: str = "") -> list[dict]:
        """Scrapet Haefele-Webshop."""
        await self._ensure_browser()
        page = await self._context.new_page()
        treffer = []

        try:
            suche = artikel_nr or suchbegriff
            url = f"https://www.haefele.de/search?q={quote_plus(suche)}"
            await page.goto(url, timeout=15000)
            await page.wait_for_load_state("domcontentloaded")
            await self._dismiss_cookie_banner(page)
            await page.wait_for_timeout(1000)

            # Warte auf Produkt-Karten
            try:
                await page.wait_for_selector("[data-testid='product-card'], .product-card, .search-result-item", timeout=8000)
            except Exception:
                logger.info("Haefele: Keine Ergebnisse fuer '%s'", suche)
                return []

            # Produkte extrahieren
            items = await page.query_selector_all("[data-testid='product-card'], .product-card, .search-result-item")
            for item in items[:10]:
                try:
                    titel_el = await item.query_selector("h3, .product-title, .product-name, a[title]")
                    titel = await titel_el.inner_text() if titel_el else ""

                    preis_el = await item.query_selector(".price, .product-price, [data-testid='price']")
                    preis_text = await preis_el.inner_text() if preis_el else "0"

                    link_el = await item.query_selector("a[href]")
                    link = await link_el.get_attribute("href") if link_el else ""
                    if link and not link.startswith("http"):
                        link = f"https://www.haefele.de{link}"

                    artnr_el = await item.query_selector(".article-number, .sku, [data-testid='article-number']")
                    artnr = await artnr_el.inner_text() if artnr_el else ""

                    preis = _parse_german_price(preis_text)

                    if titel:
                        treffer.append({
                            "quelle": "haefele",
                            "titel": titel.strip(),
                            "preis": preis,
                            "artikel_nr": artnr.strip(),
                            "link": link,
                            "waehrung": "EUR",
                        })
                except Exception as e:
                    logger.debug("Haefele: Element-Parse-Fehler: %s", e)
                    continue

        except Exception as e:
            logger.warning("Haefele-Scraping-Fehler: %s", e)
        finally:
            await page.close()

        return treffer

    # --- Amazon ---

    async def _suche_amazon(self, payload: dict, projekt_id: str) -> dict:
        suchbegriff = payload.get("suchbegriff", "")
        treffer = await self._scrape_amazon(suchbegriff)
        return {"status": "ok", "quelle": "amazon", "treffer": treffer}

    async def _scrape_amazon(self, suchbegriff: str) -> list[dict]:
        """Scrapet Amazon.de Suchergebnisse."""
        await self._ensure_browser()
        page = await self._context.new_page()
        treffer = []

        try:
            url = f"https://www.amazon.de/s?k={quote_plus(suchbegriff)}"
            await page.goto(url, timeout=15000)
            await page.wait_for_load_state("domcontentloaded")
            await self._dismiss_cookie_banner(page)
            await page.wait_for_timeout(1000)

            try:
                await page.wait_for_selector("[data-component-type='s-search-result']", timeout=8000)
            except Exception:
                logger.info("Amazon: Keine Ergebnisse fuer '%s'", suchbegriff)
                return []

            items = await page.query_selector_all("[data-component-type='s-search-result']")
            for item in items[:10]:
                try:
                    titel_el = await item.query_selector("h2 a span, h2 span")
                    titel = await titel_el.inner_text() if titel_el else ""

                    preis_whole = await item.query_selector(".a-price-whole")
                    preis_frac = await item.query_selector(".a-price-fraction")
                    preis = 0
                    if preis_whole:
                        whole = await preis_whole.inner_text()
                        frac = await preis_frac.inner_text() if preis_frac else "00"
                        preis = _parse_german_price(f"{whole},{frac}")

                    link_el = await item.query_selector("h2 a")
                    link = await link_el.get_attribute("href") if link_el else ""
                    if link and not link.startswith("http"):
                        link = f"https://www.amazon.de{link}"

                    if titel and preis > 0:
                        treffer.append({
                            "quelle": "amazon",
                            "titel": titel.strip()[:200],
                            "preis": preis,
                            "link": link,
                            "waehrung": "EUR",
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning("Amazon-Scraping-Fehler: %s", e)
        finally:
            await page.close()

        return treffer

    # --- Google Shopping ---

    async def _suche_google_shopping(self, payload: dict, projekt_id: str) -> dict:
        suchbegriff = payload.get("suchbegriff", "")
        treffer = await self._scrape_google_shopping(suchbegriff)
        return {"status": "ok", "quelle": "google_shopping", "treffer": treffer}

    async def _scrape_google_shopping(self, suchbegriff: str) -> list[dict]:
        """Scrapet Google Shopping Ergebnisse."""
        await self._ensure_browser()
        page = await self._context.new_page()
        treffer = []

        try:
            url = f"https://www.google.de/search?q={quote_plus(suchbegriff)}&tbm=shop&hl=de"
            await page.goto(url, timeout=15000)
            await page.wait_for_load_state("domcontentloaded")
            await self._dismiss_cookie_banner(page)
            await page.wait_for_timeout(1000)

            # Mehrere Selektor-Varianten (Google aendert regelmaessig)
            item_selectors = [
                ".sh-dgr__grid-result",
                ".sh-dlr__list-result",
                "[data-docid]",
                ".sh-pr__product-results .sh-pr__product-result",
                ".xcR77",
            ]
            found = False
            for sel in item_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=4000)
                    found = True
                    break
                except Exception:
                    continue

            if not found:
                logger.info("Google Shopping: Keine Ergebnisse fuer '%s'", suchbegriff)
                return []

            items = []
            for sel in item_selectors:
                items = await page.query_selector_all(sel)
                if items:
                    break

            for item in items[:10]:
                try:
                    # Titel (mehrere Varianten)
                    titel = ""
                    for ts in ["h3", ".tAxDx", "a[aria-label]", ".Xjkr3b"]:
                        titel_el = await item.query_selector(ts)
                        if titel_el:
                            titel = await titel_el.inner_text()
                            if titel.strip():
                                break

                    # Preis (mehrere Varianten)
                    preis = 0
                    for ps in [".a8Pemb", ".HRLxBb", "span[aria-label*='EUR']", ".kHxwFf", "b"]:
                        preis_el = await item.query_selector(ps)
                        if preis_el:
                            preis_text = await preis_el.inner_text()
                            preis = _parse_german_price(preis_text)
                            if preis > 0:
                                break

                    # Shop-Name
                    shop = ""
                    for ss in [".aULzUe", ".IuHnof", ".E5ocAb", ".zPEcBd"]:
                        shop_el = await item.query_selector(ss)
                        if shop_el:
                            shop = await shop_el.inner_text()
                            if shop.strip():
                                break

                    # Link
                    link_el = await item.query_selector("a[href*='url?']") or await item.query_selector("a[href]")
                    link = await link_el.get_attribute("href") if link_el else ""
                    if link and link.startswith("/"):
                        link = f"https://www.google.de{link}"

                    if titel and preis > 0:
                        treffer.append({
                            "quelle": "google_shopping",
                            "titel": titel.strip()[:200],
                            "preis": preis,
                            "shop": shop.strip(),
                            "link": link,
                            "waehrung": "EUR",
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning("Google-Shopping-Fehler: %s", e)
        finally:
            await page.close()

        return treffer

    # --- Blum ---

    async def _scrape_blum(self, suchbegriff: str, artikel_nr: str = "") -> list[dict]:
        """Scrapet Blum-Produktkatalog."""
        await self._ensure_browser()
        page = await self._context.new_page()
        treffer = []

        try:
            suche = artikel_nr or suchbegriff
            url = f"https://www.blum.com/de-de/search?q={suche}"
            await page.goto(url, timeout=15000)
            await page.wait_for_load_state("domcontentloaded")

            try:
                await page.wait_for_selector(".search-result, .product-tile", timeout=8000)
            except Exception:
                return []

            items = await page.query_selector_all(".search-result, .product-tile")
            for item in items[:10]:
                try:
                    titel_el = await item.query_selector("h3, .product-name, .title")
                    titel = await titel_el.inner_text() if titel_el else ""

                    link_el = await item.query_selector("a[href]")
                    link = await link_el.get_attribute("href") if link_el else ""
                    if link and not link.startswith("http"):
                        link = f"https://www.blum.com{link}"

                    if titel:
                        treffer.append({
                            "quelle": "blum",
                            "titel": titel.strip(),
                            "preis": 0,  # Blum zeigt selten Preise direkt
                            "link": link,
                            "hinweis": "Preis auf Anfrage / Haendler",
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning("Blum-Scraping-Fehler: %s", e)
        finally:
            await page.close()

        return treffer

    # --- Egger ---

    async def _scrape_egger(self, suchbegriff: str) -> list[dict]:
        """Scrapet Egger-Dekore/Produkte."""
        await self._ensure_browser()
        page = await self._context.new_page()
        treffer = []

        try:
            url = f"https://www.egger.com/de_DE/search?q={suchbegriff}"
            await page.goto(url, timeout=15000)
            await page.wait_for_load_state("domcontentloaded")

            try:
                await page.wait_for_selector(".product-item, .search-result", timeout=8000)
            except Exception:
                return []

            items = await page.query_selector_all(".product-item, .search-result")
            for item in items[:10]:
                try:
                    titel_el = await item.query_selector("h3, .product-title, .title")
                    titel = await titel_el.inner_text() if titel_el else ""

                    link_el = await item.query_selector("a[href]")
                    link = await link_el.get_attribute("href") if link_el else ""
                    if link and not link.startswith("http"):
                        link = f"https://www.egger.com{link}"

                    dekor_el = await item.query_selector(".decor-number, .article-number")
                    dekor = await dekor_el.inner_text() if dekor_el else ""

                    if titel:
                        treffer.append({
                            "quelle": "egger",
                            "titel": titel.strip(),
                            "preis": 0,  # Egger = Haendlerpreise
                            "dekor_nr": dekor.strip(),
                            "link": link,
                            "hinweis": "Haendlerpreis - Anfrage bei Holzhandel",
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning("Egger-Scraping-Fehler: %s", e)
        finally:
            await page.close()

        return treffer

    # --- Ergebnis in DB speichern ---

    async def _ergebnis_speichern(self, payload: dict, projekt_id: str) -> dict:
        """Speichert ein Recherche-Ergebnis als Zukaufteil in der DB."""
        import aiosqlite

        treffer = payload.get("treffer", {})
        position_id = payload.get("position_id")
        aufschlag = payload.get("aufschlag_prozent", 15.0)

        einkaufspreis = treffer.get("preis", 0)
        verkaufspreis = round(einkaufspreis * (1 + aufschlag / 100), 2)
        now = datetime.now().isoformat()

        alternativ = payload.get("alternativen", [])

        async with aiosqlite.connect(self._db_pfad) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cursor = await db.execute(
                """INSERT INTO zukaufteile
                   (projekt_id, position_id, bezeichnung, hersteller, produkt,
                    artikel_nr, produkt_link, einkaufspreis, menge,
                    aufschlag_prozent, verkaufspreis, status, quelle,
                    alternativ_json, erstellt_am, aktualisiert_am)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    projekt_id,
                    position_id,
                    treffer.get("titel", ""),
                    treffer.get("hersteller", ""),
                    treffer.get("produkt", ""),
                    treffer.get("artikel_nr", ""),
                    treffer.get("link", ""),
                    einkaufspreis,
                    payload.get("menge", 1),
                    aufschlag,
                    verkaufspreis,
                    "recherchiert",
                    treffer.get("quelle", ""),
                    json.dumps(alternativ, ensure_ascii=False),
                    now, now,
                ),
            )
            await db.commit()
            zukaufteil_id = cursor.lastrowid

        return {
            "status": "ok",
            "zukaufteil_id": zukaufteil_id,
            "einkaufspreis": einkaufspreis,
            "verkaufspreis": verkaufspreis,
            "aufschlag_prozent": aufschlag,
        }

    # --- KI-Preisschaetzung (Fallback) ---

    async def _ki_preisschaetzung(self, suchbegriff: str, bezeichnung: str, hersteller: str) -> list[dict]:
        """Fragt Claude nach einer Preisschaetzung wenn Scraping fehlschlaegt."""
        try:
            import os
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                if self._llm and hasattr(self._llm, "_claude_key"):
                    api_key = self._llm._claude_key
            if not api_key:
                return []

            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            prompt = f"""Du bist ein Experte fuer Schreinerei-/Tischlerei-Zubehoer und Beschlaege.
Gib mir fuer folgendes Produkt eine realistische Preisschaetzung (Marktpreis in EUR, netto, B2B-Preis Deutschland).

Produkt: {bezeichnung}
Hersteller: {hersteller or 'unbekannt'}
Suchbegriff: {suchbegriff}

Antworte NUR im JSON-Format (keine Erklaerung):
{{
  "produkte": [
    {{
      "titel": "Genaue Produktbezeichnung",
      "preis_min": 0.00,
      "preis_max": 0.00,
      "preis_typisch": 0.00,
      "hersteller": "Marke",
      "hinweis": "Kurze Info (z.B. Preis pro Stueck, VPE etc.)"
    }}
  ]
}}

Gib 1-3 Varianten/Alternativen zurueck. Wenn du unsicher bist, schaetze trotzdem - markiere es im Hinweis."""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # JSON aus der Antwort extrahieren
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)

            treffer = []
            for p in data.get("produkte", []):
                preis = p.get("preis_typisch", 0) or ((p.get("preis_min", 0) + p.get("preis_max", 0)) / 2)
                if preis > 0:
                    treffer.append({
                        "quelle": "ki_schaetzung",
                        "titel": p.get("titel", bezeichnung),
                        "preis": round(preis, 2),
                        "shop": p.get("hersteller", hersteller or ""),
                        "link": "",
                        "waehrung": "EUR",
                        "hinweis": p.get("hinweis", "KI-Preisschaetzung - Preis verifizieren!"),
                        "preis_min": p.get("preis_min"),
                        "preis_max": p.get("preis_max"),
                    })

            logger.info("KI-Preisschaetzung fuer '%s': %d Vorschlaege", suchbegriff, len(treffer))
            return treffer

        except Exception as e:
            logger.warning("KI-Preisschaetzung Fehler: %s", e)
            return []


def _parse_german_price(text: str) -> float:
    """Parst deutschen Preis-String (z.B. '12,99 EUR' oder '1.234,56')."""
    if not text:
        return 0.0
    import re
    # Entferne alles ausser Ziffern, Punkt, Komma
    cleaned = re.sub(r"[^\d.,]", "", text)
    if not cleaned:
        return 0.0
    # Deutsches Format: 1.234,56 -> 1234.56
    if "," in cleaned:
        # Tausenderpunkte entfernen, Komma zu Punkt
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0
