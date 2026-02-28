/**
 * Chat Context Builder -- Komprimiert Kalkulations-State fuer den KI-Chat.
 * Ziel: ~200 Tokens statt ~2000 (nur aggregierte Summen + nicht-leere Items).
 */

function num(val) {
  return parseFloat(val) || 0
}

/**
 * Baut kompakten Kontext aus dem Kalkulations-State.
 * Nur nicht-leere Zeilen, max 15 Items, aggregierte Summen.
 */
export function buildChatContext({ allgemein, platten, beschlaege, zukaufteile, halbzeuge, lohn, calc, zuschlaege }) {
  const items = []

  // Platten mit Inhalt
  for (const r of (platten || [])) {
    if (!r.bezeichnung && num(r.menge) === 0) continue
    items.push({
      kat: 'platte',
      bez: r.bezeichnung || '?',
      menge: num(r.menge),
      preis: num(r.preisQm),
      einheit: 'qm',
      staerke: r.staerke || '',
    })
  }

  // Beschlaege mit Inhalt
  for (const r of (beschlaege || [])) {
    if (!r.bezeichnung && num(r.anzahl) === 0) continue
    items.push({
      kat: 'beschlag',
      bez: r.bezeichnung || '?',
      menge: num(r.anzahl),
      preis: num(r.preis),
      einheit: 'Stk',
    })
  }

  // Zukaufteile mit Inhalt
  for (const r of (zukaufteile || [])) {
    if (!r.bezeichnung && num(r.anzahl) === 0) continue
    items.push({
      kat: 'zukauf',
      bez: r.bezeichnung || '?',
      menge: num(r.anzahl),
      preis: num(r.preis),
      einheit: r.einheit || 'Stk',
    })
  }

  // Halbzeuge mit Inhalt
  for (const r of (halbzeuge || [])) {
    if (!r.bezeichnung && num(r.anzahl) === 0) continue
    items.push({
      kat: 'halbzeug',
      bez: r.bezeichnung || '?',
      menge: num(r.anzahl),
      preis: num(r.preis),
      einheit: r.einheit || 'Stk',
    })
  }

  // Lohn mit Stunden > 0
  for (const r of (lohn || [])) {
    if (num(r.stunden) === 0) continue
    items.push({
      kat: 'lohn',
      bez: r.bezeichnung || '?',
      menge: num(r.stunden),
      preis: 0,
      einheit: 'h',
    })
  }

  return {
    gegenstand: allgemein?.gegenstand || '',
    kunde: allgemein?.kunde || '',
    items: items.slice(0, 15),
    sums: calc ? {
      materialRoh: calc.materialRoh || 0,
      sumLohn: calc.sumLohn || 0,
      selbstkosten: calc.selbstkosten || 0,
      gesamt: calc.gesamt || 0,
      brutto: calc.brutto || 0,
    } : {},
    zuschlaege: zuschlaege ? {
      kleinteile: zuschlaege.kleinteile,
      margeMaterial: zuschlaege.margeMaterial,
      margeZukauf: zuschlaege.margeZukauf,
      mwst: zuschlaege.mwst,
    } : {},
  }
}

/**
 * Baut den Request fuer den Auto-Vorschlag nach SmartWOP-Import.
 */
export function buildAutoVorschlagRequest({ allgemein, platten, beschlaege, calc }) {
  return {
    gegenstand: allgemein?.gegenstand || '',
    platten: (platten || [])
      .filter(r => r.bezeichnung)
      .map(r => ({
        bezeichnung: r.bezeichnung,
        staerke: r.staerke || '',
        menge: num(r.menge),
        preisQm: num(r.preisQm),
      })),
    beschlaege: (beschlaege || [])
      .filter(r => r.bezeichnung)
      .map(r => ({
        bezeichnung: r.bezeichnung,
        anzahl: num(r.anzahl),
        preis: num(r.preis),
      })),
    calc_sums: calc ? {
      materialRoh: calc.materialRoh || 0,
      gesamt: calc.gesamt || 0,
      brutto: calc.brutto || 0,
    } : {},
  }
}
