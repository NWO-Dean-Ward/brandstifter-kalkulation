/**
 * AngebotTab - Kunden-Angebots-Editor (inspiriert von Lexoffice).
 *
 * Features:
 * - Positionstypen: Normal, Freitext, Alternative, Optional, Zwischensumme
 * - Positionsgruppen mit Drag (Reihenfolge aendern)
 * - Gesamtrabatt (EUR oder %)
 * - Standard-Texte (Einleitung + Schluss)
 * - Druckvorschau / PDF
 * - Dokumenten-Kette (Angebot -> AB -> Rechnung)
 */
import { useState, useMemo, useRef } from 'react'

// --- Helpers ---
function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}
function num(val) { return parseFloat(val) || 0 }

// Position types (statische Klassen fuer Tailwind JIT)
const POS_TYPES = {
  normal: { label: 'Position', badge: '', badgeCls: '', btnCls: 'bg-slate-100 text-slate-600 hover:bg-slate-200' },
  freitext: { label: 'Freitext', badge: 'Text', badgeCls: 'bg-blue-100 text-blue-600', btnCls: 'bg-blue-100 text-blue-600 hover:bg-blue-200' },
  alternative: { label: 'Alternative', badge: 'Alternative', badgeCls: 'bg-amber-100 text-amber-600', btnCls: 'bg-amber-100 text-amber-600 hover:bg-amber-200' },
  optional: { label: 'Optional', badge: 'Optional', badgeCls: 'bg-purple-100 text-purple-600', btnCls: 'bg-purple-100 text-purple-600 hover:bg-purple-200' },
  zwischensumme: { label: 'Zwischensumme', badge: 'Summe', badgeCls: 'bg-slate-100 text-slate-600', btnCls: 'bg-slate-100 text-slate-600 hover:bg-slate-200' },
}

// Einheiten
const EINHEITEN = ['Stk', 'lfm', 'qm', 'm', 'kg', 'Liter', 'Pauschal', 'h', 'Set', 'VPE']

// Standard-Texte Vorlagen
const EINLEITUNGSTEXTE = [
  { label: 'Standard', text: 'Vielen Dank fuer Ihre Anfrage. Gerne unterbreiten wir Ihnen folgendes Angebot:' },
  { label: 'Kueche', text: 'Vielen Dank fuer die Beauftragung der Kuechenplanung. Nachfolgend unser detailliertes Angebot fuer die Herstellung und Montage:' },
  { label: 'Einbauschrank', text: 'Bezugnehmend auf unser Aufmass vor Ort bieten wir Ihnen die Anfertigung und Montage wie folgt an:' },
  { label: 'Messestand', text: 'Gerne unterbreiten wir Ihnen unser Angebot fuer Planung, Herstellung und Aufbau des Messestands:' },
  { label: 'Leer', text: '' },
]

const SCHLUSSTEXTE = [
  { label: 'Standard', text: 'Dieses Angebot ist 4 Wochen gueltig. Wir freuen uns auf Ihren Auftrag und stehen fuer Rueckfragen gerne zur Verfuegung.' },
  { label: 'Mit Anzahlung', text: 'Bei Auftragserteilung bitten wir um eine Anzahlung von 40% der Netto-Auftragssumme. Restbetrag nach Abnahme. Angebot 4 Wochen gueltig.' },
  { label: 'Express', text: 'Ausfuehrungszeitraum: ca. 4-6 Wochen nach Auftragserteilung. Angebot 2 Wochen gueltig. Preise verstehen sich zzgl. gesetzl. MwSt.' },
  { label: 'Leer', text: '' },
]

// Document states (statische Klassen)
const DOK_STATUS = {
  entwurf: { label: 'Entwurf', badgeCls: 'bg-slate-100 text-slate-700', activeCls: 'bg-slate-600 text-white' },
  angebot: { label: 'Angebot', badgeCls: 'bg-blue-100 text-blue-700', activeCls: 'bg-blue-600 text-white' },
  auftragsbestaetigung: { label: 'Auftragsbestaetigung', badgeCls: 'bg-green-100 text-green-700', activeCls: 'bg-green-600 text-white' },
  rechnung: { label: 'Rechnung', badgeCls: 'bg-orange-100 text-orange-700', activeCls: 'bg-orange-600 text-white' },
}

let _nextId = 5000
function nid() { return _nextId++ }

// ============================================================================
export default function AngebotTab({ calc, allgemein, zuschlaege, kalkDaten }) {
  // --- Angebots-State ---
  const [dokStatus, setDokStatus] = useState('entwurf')
  const [angebotNr, setAngebotNr] = useState(`ANG-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 9000 + 1000))}`)
  const [gueltigBis, setGueltigBis] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 28); return d.toISOString().slice(0, 10)
  })
  const [einleitung, setEinleitung] = useState(EINLEITUNGSTEXTE[0].text)
  const [schluss, setSchluss] = useState(SCHLUSSTEXTE[0].text)

  // Positionen
  const [positionen, setPositionen] = useState([])
  const [gesamtRabatt, setGesamtRabatt] = useState({ wert: 0, modus: 'prozent' }) // prozent | euro

  // UI state
  const [showPreview, setShowPreview] = useState(false)
  const [addMenuOpen, setAddMenuOpen] = useState(null) // index where to insert
  const printRef = useRef(null)

  // --- Auto-generate positions from Kalkulation ---
  const generateFromKalk = () => {
    if (positionen.length > 0 && !confirm('Bestehende Positionen werden ueberschrieben. Fortfahren?')) return

    const pos = []
    let posNr = 1

    // Gegenstand als Freitext-Header
    if (allgemein.gegenstand) {
      pos.push({
        id: nid(), typ: 'freitext', posNr: null,
        bezeichnung: allgemein.gegenstand,
        beschreibung: allgemein.kunde ? `Fuer: ${allgemein.kunde}` : '',
        menge: 0, einheit: '', einzelpreis: 0,
      })
    }

    // Materialien zusammengefasst als Position
    if (calc.summeVerarbeiteteMat > 0) {
      const matDetails = []
      if (kalkDaten?.platten) {
        kalkDaten.platten.filter(r => num(r.menge) > 0).forEach(r => {
          matDetails.push(`${r.bezeichnung || 'Platte'} ${r.staerke || ''}`.trim())
        })
      }
      if (kalkDaten?.massivholz) {
        kalkDaten.massivholz.filter(r => num(r.menge) > 0).forEach(r => {
          matDetails.push(`${r.bezeichnung || 'Massivholz'} ${r.staerke || ''}`.trim())
        })
      }
      pos.push({
        id: nid(), typ: 'normal', posNr: posNr++,
        bezeichnung: 'Material und Verarbeitung',
        beschreibung: matDetails.length > 0 ? matDetails.join(', ') : 'Platten, Massivholz, Kanten, Halbzeuge inkl. Verarbeitung',
        menge: 1, einheit: 'Pauschal', einzelpreis: Math.round(calc.summeVerarbeiteteMat * 100) / 100,
      })
    }

    // Beschlaege / Lacke als Position
    const beschlaegeSum = (kalkDaten?.beschlaege || []).reduce((s, r) => s + num(r.anzahl) * num(r.preis), 0)
    const lackeSum = (kalkDaten?.lacke || []).reduce((s, r) => s + num(r.liter) * num(r.preis), 0)
    if (beschlaegeSum + lackeSum > 0) {
      pos.push({
        id: nid(), typ: 'normal', posNr: posNr++,
        bezeichnung: 'Beschlaege und Oberflaeche',
        beschreibung: 'Scharniere, Griffe, Auszuege, Lackierung/Oelen',
        menge: 1, einheit: 'Pauschal', einzelpreis: Math.round((beschlaegeSum + lackeSum) * 100) / 100,
      })
    }

    // Zukaufteile einzeln
    if (kalkDaten?.zukaufteile) {
      kalkDaten.zukaufteile.filter(r => num(r.anzahl) > 0 && num(r.preis) > 0).forEach(r => {
        const aufschlag = num(zuschlaege.margeZukauf) / 100
        const vkPreis = Math.round(num(r.preis) * (1 + aufschlag) * 100) / 100
        pos.push({
          id: nid(), typ: 'normal', posNr: posNr++,
          bezeichnung: r.bezeichnung || 'Zukaufteil',
          beschreibung: r.marke ? `Marke: ${r.marke}` : '',
          menge: num(r.anzahl), einheit: r.einheit || 'Stk', einzelpreis: vkPreis,
        })
      })
    }

    // Zwischensumme Material
    pos.push({ id: nid(), typ: 'zwischensumme', posNr: null, bezeichnung: 'Zwischensumme Material', beschreibung: '', menge: 0, einheit: '', einzelpreis: 0 })

    // Fremdmaterial
    if (calc.sumFremd > 0) {
      pos.push({
        id: nid(), typ: 'normal', posNr: posNr++,
        bezeichnung: 'Fremdmaterial (vom AG)',
        beschreibung: 'Beistellung inkl. Handling',
        menge: 1, einheit: 'Pauschal', einzelpreis: Math.round(calc.sumFremd * 100) / 100,
      })
    }

    // Arbeitsstunden als Positionen
    if (kalkDaten?.lohn) {
      const stunden = kalkDaten.lohn.filter(r => num(r.stunden) > 0)
      if (stunden.length > 0) {
        pos.push({ id: nid(), typ: 'freitext', posNr: null, bezeichnung: 'Arbeitsleistung', beschreibung: '', menge: 0, einheit: '', einzelpreis: 0 })
        // Werkstatt-Stunden zusammenfassen
        const werkstatt = stunden.filter(r => r.lohnart === 1)
        const cnc = stunden.filter(r => r.lohnart === 2)
        const montage = stunden.filter(r => r.lohnart === 3)

        if (werkstatt.length > 0) {
          const h = werkstatt.reduce((s, r) => s + num(r.stunden), 0)
          const taetigkeiten = werkstatt.map(r => r.bezeichnung).filter(Boolean).join(', ')
          // Verrechnungssatz mit WUG-Aufschlag
          const stundensatz = num(kalkDaten.variablen?.lohn1 || 75) * (1 + num(zuschlaege.wug) / 100)
          pos.push({
            id: nid(), typ: 'normal', posNr: posNr++,
            bezeichnung: 'Werkstatt / Fertigung',
            beschreibung: taetigkeiten || 'Zuschnitt, Bearbeitung, Schleifen, Verpackung',
            menge: Math.round(h * 10) / 10, einheit: 'h', einzelpreis: Math.round(stundensatz * 100) / 100,
          })
        }
        if (cnc.length > 0) {
          const h = cnc.reduce((s, r) => s + num(r.stunden), 0)
          const stundensatz = num(kalkDaten.variablen?.lohn2 || 160) * (1 + num(zuschlaege.wug) / 100)
          pos.push({
            id: nid(), typ: 'normal', posNr: posNr++,
            bezeichnung: 'CNC-Bearbeitung',
            beschreibung: 'CNC-Fraesen inkl. Programmierung und Maschinenkosten',
            menge: Math.round(h * 10) / 10, einheit: 'h', einzelpreis: Math.round(stundensatz * 100) / 100,
          })
        }
        if (montage.length > 0) {
          const h = montage.reduce((s, r) => s + num(r.stunden), 0)
          const stundensatz = num(kalkDaten.variablen?.lohn3 || 65) * (1 + num(zuschlaege.wug) / 100)
          pos.push({
            id: nid(), typ: 'normal', posNr: posNr++,
            bezeichnung: 'Montage vor Ort',
            beschreibung: 'Anlieferung, Aufbau und Einpassung vor Ort',
            menge: Math.round(h * 10) / 10, einheit: 'h', einzelpreis: Math.round(stundensatz * 100) / 100,
          })
        }
      }
    }

    // KFZ
    if (calc.sumKfz > 0) {
      pos.push({
        id: nid(), typ: 'normal', posNr: posNr++,
        bezeichnung: 'Anfahrt / Transport',
        beschreibung: `${kalkDaten?.kfz ? num(kalkDaten.kfz.kmEinfach) * num(kalkDaten.kfz.anzahlWege) + ' km' : ''}`,
        menge: 1, einheit: 'Pauschal', einzelpreis: Math.round(calc.sumKfz * 100) / 100,
      })
    }

    // Zwischensumme Gesamt
    pos.push({ id: nid(), typ: 'zwischensumme', posNr: null, bezeichnung: 'Gesamtsumme', beschreibung: '', menge: 0, einheit: '', einzelpreis: 0 })

    setPositionen(pos)
    setGesamtRabatt({ wert: num(zuschlaege.rabatt), modus: 'prozent' })
  }

  // --- Position CRUD ---
  const addPosition = (typ, afterIndex = null) => {
    const newPos = {
      id: nid(), typ,
      posNr: typ === 'freitext' || typ === 'zwischensumme' ? null : null, // auto-numbered
      bezeichnung: '', beschreibung: '',
      menge: typ === 'normal' || typ === 'alternative' || typ === 'optional' ? 1 : 0,
      einheit: typ === 'normal' || typ === 'alternative' || typ === 'optional' ? 'Stk' : '',
      einzelpreis: 0,
    }
    setPositionen(prev => {
      if (afterIndex !== null && afterIndex < prev.length) {
        const copy = [...prev]
        copy.splice(afterIndex + 1, 0, newPos)
        return copy
      }
      return [...prev, newPos]
    })
    setAddMenuOpen(null)
  }

  const updatePos = (id, field, value) => {
    setPositionen(prev => prev.map(p => p.id === id ? { ...p, [field]: value } : p))
  }

  const removePos = (id) => {
    setPositionen(prev => prev.filter(p => p.id !== id))
  }

  const movePos = (index, direction) => {
    setPositionen(prev => {
      const copy = [...prev]
      const target = index + direction
      if (target < 0 || target >= copy.length) return prev
      ;[copy[index], copy[target]] = [copy[target], copy[index]]
      return copy
    })
  }

  // --- Berechnungen ---
  const angCalc = useMemo(() => {
    let posNr = 1
    const numbered = positionen.map(p => {
      if (p.typ === 'freitext' || p.typ === 'zwischensumme') return { ...p, posNr: null }
      return { ...p, posNr: posNr++ }
    })

    // Subtotals: calculate running sum for each Zwischensumme
    let runningSum = 0
    let lastZsIndex = -1
    const withSums = numbered.map((p, i) => {
      if (p.typ === 'zwischensumme') {
        const zsSum = runningSum
        runningSum = 0
        return { ...p, _zsSum: zsSum }
      }
      if (p.typ === 'normal') {
        const lineSum = num(p.menge) * num(p.einzelpreis)
        runningSum += lineSum
        return { ...p, _lineSum: lineSum }
      }
      if (p.typ === 'alternative' || p.typ === 'optional') {
        const lineSum = num(p.menge) * num(p.einzelpreis)
        return { ...p, _lineSum: lineSum } // NOT added to running sum
      }
      return p
    })

    // Total (nur normale Positionen)
    const netto = withSums.reduce((s, p) => {
      if (p.typ === 'normal') return s + (p._lineSum || 0)
      return s
    }, 0)

    // Rabatt
    let rabattBetrag = 0
    if (gesamtRabatt.modus === 'prozent') {
      rabattBetrag = netto * num(gesamtRabatt.wert) / 100
    } else {
      rabattBetrag = num(gesamtRabatt.wert)
    }

    const nettoNachRabatt = netto - rabattBetrag
    const mwstSatz = num(zuschlaege.mwst)
    const mwst = nettoNachRabatt * mwstSatz / 100
    const brutto = nettoNachRabatt + mwst

    return { positionen: withSums, netto, rabattBetrag, nettoNachRabatt, mwst, mwstSatz, brutto }
  }, [positionen, gesamtRabatt, zuschlaege.mwst])

  // --- Dokumenten-Kette ---
  const advanceStatus = () => {
    const chain = ['entwurf', 'angebot', 'auftragsbestaetigung', 'rechnung']
    const idx = chain.indexOf(dokStatus)
    if (idx < chain.length - 1) {
      const next = chain[idx + 1]
      if (confirm(`Dokument zu "${DOK_STATUS[next].label}" weiterfuehren?`)) {
        setDokStatus(next)
        // Neue Nummer vergeben
        const prefix = { angebot: 'ANG', auftragsbestaetigung: 'AB', rechnung: 'RE' }[next] || 'DOK'
        setAngebotNr(`${prefix}-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 9000 + 1000))}`)
      }
    }
  }

  // --- Print ---
  const handlePrint = () => {
    setShowPreview(true)
    setTimeout(() => window.print(), 300)
  }

  // ===========================================================================
  // RENDER
  // ===========================================================================
  const inputCls = 'border border-slate-300 rounded px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500'

  // --- Preview Mode ---
  if (showPreview) {
    return (
      <div>
        <div data-print-hide className="mb-4 flex gap-2">
          <button onClick={() => setShowPreview(false)} className="text-sm text-slate-600 hover:text-slate-800 border border-slate-300 px-3 py-1.5 rounded">
            Zurueck zum Editor
          </button>
          <button onClick={() => window.print()} className="text-sm text-white bg-orange-600 hover:bg-orange-700 px-4 py-1.5 rounded font-medium">
            Drucken / PDF
          </button>
        </div>
        <PrintPreview
          allgemein={allgemein}
          angebotNr={angebotNr}
          gueltigBis={gueltigBis}
          einleitung={einleitung}
          schluss={schluss}
          dokStatus={dokStatus}
          angCalc={angCalc}
          gesamtRabatt={gesamtRabatt}
          zuschlaege={zuschlaege}
        />
      </div>
    )
  }

  // --- Editor Mode ---
  return (
    <div className="space-y-4">
      {/* Dokument-Header */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <h2 className="font-bold text-slate-800">{DOK_STATUS[dokStatus].label}</h2>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${DOK_STATUS[dokStatus].badgeCls}`}>
              {DOK_STATUS[dokStatus].label}
            </span>
          </div>
          <div className="flex gap-2">
            {dokStatus !== 'rechnung' && (
              <button onClick={advanceStatus} className="text-xs font-medium px-3 py-1.5 rounded-md bg-green-600 text-white hover:bg-green-700">
                Weiterfuehren &rarr;
              </button>
            )}
            <button onClick={handlePrint} className="text-xs font-medium px-3 py-1.5 rounded-md border border-slate-300 hover:bg-slate-50">
              Vorschau / Drucken
            </button>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-slate-500 block mb-1">Nummer</label>
            <input value={angebotNr} onChange={e => setAngebotNr(e.target.value)} className={inputCls + ' w-full'} />
          </div>
          <div>
            <label className="text-xs text-slate-500 block mb-1">Kunde</label>
            <div className="text-sm font-medium text-slate-700 py-1.5">{allgemein.kunde || '(kein Kunde)'}</div>
          </div>
          <div>
            <label className="text-xs text-slate-500 block mb-1">Datum</label>
            <div className="text-sm text-slate-700 py-1.5">{allgemein.datum}</div>
          </div>
          <div>
            <label className="text-xs text-slate-500 block mb-1">Gueltig bis</label>
            <input type="date" value={gueltigBis} onChange={e => setGueltigBis(e.target.value)} className={inputCls + ' w-full'} />
          </div>
        </div>
      </div>

      {/* Einleitungstext */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-semibold text-slate-500 uppercase">Einleitungstext</label>
          <select onChange={e => setEinleitung(EINLEITUNGSTEXTE[e.target.value]?.text || '')}
            className="text-xs border border-slate-200 rounded px-2 py-1">
            {EINLEITUNGSTEXTE.map((t, i) => <option key={i} value={i}>{t.label}</option>)}
          </select>
        </div>
        <textarea value={einleitung} onChange={e => setEinleitung(e.target.value)}
          rows={2} className={inputCls + ' w-full resize-none'} placeholder="Einleitungstext..." />
      </div>

      {/* Auto-Generate Button */}
      {positionen.length === 0 && calc.brutto > 0 && (
        <button onClick={generateFromKalk}
          className="w-full py-4 border-2 border-dashed border-orange-300 rounded-xl text-orange-600 hover:bg-orange-50 hover:border-orange-400 font-medium transition-colors">
          Positionen aus Kalkulation generieren
        </button>
      )}

      {/* Positionen */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <span className="font-semibold text-sm text-slate-700">Positionen ({angCalc.positionen.filter(p => p.posNr).length})</span>
          <div className="flex gap-1">
            {positionen.length > 0 && (
              <button onClick={generateFromKalk} className="text-xs text-orange-600 hover:text-orange-700 font-medium px-2 py-1">
                Neu generieren
              </button>
            )}
          </div>
        </div>

        {/* Position-Tabelle */}
        <table className="w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="w-6 px-1"></th>
              <th className="w-10 px-2 py-2 text-left text-xs text-slate-500">Pos.</th>
              <th className="px-3 py-2 text-left text-xs text-slate-500">Bezeichnung / Beschreibung</th>
              <th className="w-16 px-2 py-2 text-right text-xs text-slate-500">Menge</th>
              <th className="w-16 px-2 py-2 text-xs text-slate-500">Einh.</th>
              <th className="w-24 px-2 py-2 text-right text-xs text-slate-500">EP (netto)</th>
              <th className="w-28 px-2 py-2 text-right text-xs text-slate-500">GP (netto)</th>
              <th className="w-6 px-1"></th>
            </tr>
          </thead>
          <tbody>
            {angCalc.positionen.map((p, idx) => (
              <PositionRow key={p.id} pos={p} index={idx} total={angCalc.positionen.length}
                onUpdate={updatePos} onRemove={removePos} onMove={movePos}
                onAddAfter={(typ) => addPosition(typ, idx)}
                addMenuOpen={addMenuOpen} setAddMenuOpen={setAddMenuOpen}
              />
            ))}
          </tbody>
        </table>

        {/* Add Position Menu */}
        <div className="px-4 py-2 border-t border-slate-100 flex gap-2 flex-wrap">
          <button onClick={() => addPosition('normal')} className="text-xs font-medium text-orange-600 hover:text-orange-700 px-2 py-1 rounded hover:bg-orange-50">
            + Position
          </button>
          <button onClick={() => addPosition('freitext')} className="text-xs font-medium text-blue-600 hover:text-blue-700 px-2 py-1 rounded hover:bg-blue-50">
            + Freitext
          </button>
          <button onClick={() => addPosition('alternative')} className="text-xs font-medium text-amber-600 hover:text-amber-700 px-2 py-1 rounded hover:bg-amber-50">
            + Alternative
          </button>
          <button onClick={() => addPosition('optional')} className="text-xs font-medium text-purple-600 hover:text-purple-700 px-2 py-1 rounded hover:bg-purple-50">
            + Optional
          </button>
          <button onClick={() => addPosition('zwischensumme')} className="text-xs font-medium text-slate-500 hover:text-slate-700 px-2 py-1 rounded hover:bg-slate-50">
            + Zwischensumme
          </button>
        </div>
      </div>

      {/* Gesamtrabatt + Summen */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <div className="max-w-md ml-auto space-y-2">
          {/* Netto */}
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">Zwischensumme (netto)</span>
            <span className="font-medium">{euro(angCalc.netto)}</span>
          </div>

          {/* Gesamtrabatt */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-600 flex-1">Gesamtrabatt</span>
            <input type="number" step="0.01" value={gesamtRabatt.wert || ''}
              onChange={e => setGesamtRabatt(prev => ({ ...prev, wert: e.target.value }))}
              className={inputCls + ' w-20 text-right text-sm'} />
            <select value={gesamtRabatt.modus} onChange={e => setGesamtRabatt(prev => ({ ...prev, modus: e.target.value }))}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm">
              <option value="prozent">%</option>
              <option value="euro">EUR</option>
            </select>
            {angCalc.rabattBetrag > 0 && (
              <span className="text-sm font-medium text-red-600">-{euro(angCalc.rabattBetrag)}</span>
            )}
          </div>

          {angCalc.rabattBetrag > 0 && (
            <div className="flex justify-between text-sm">
              <span className="text-slate-600">Netto nach Rabatt</span>
              <span className="font-medium">{euro(angCalc.nettoNachRabatt)}</span>
            </div>
          )}

          {/* MwSt */}
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">MwSt ({angCalc.mwstSatz}%)</span>
            <span>{euro(angCalc.mwst)}</span>
          </div>

          <div className="border-t border-slate-200 pt-2 flex justify-between items-center">
            <span className="font-bold text-slate-800">Gesamtbetrag (brutto)</span>
            <span className="text-xl font-bold text-orange-600">{euro(angCalc.brutto)}</span>
          </div>
        </div>
      </div>

      {/* Schlusstext */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-semibold text-slate-500 uppercase">Schlusstext / Zahlungsbedingungen</label>
          <select onChange={e => setSchluss(SCHLUSSTEXTE[e.target.value]?.text || '')}
            className="text-xs border border-slate-200 rounded px-2 py-1">
            {SCHLUSSTEXTE.map((t, i) => <option key={i} value={i}>{t.label}</option>)}
          </select>
        </div>
        <textarea value={schluss} onChange={e => setSchluss(e.target.value)}
          rows={2} className={inputCls + ' w-full resize-none'} placeholder="Schlussbemerkung..." />
      </div>

      {/* Dokumenten-Kette Visualisierung */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <label className="text-xs font-semibold text-slate-500 uppercase block mb-3">Dokumenten-Kette</label>
        <div className="flex items-center gap-1">
          {Object.entries(DOK_STATUS).map(([key, val], i) => {
            const active = key === dokStatus
            const past = Object.keys(DOK_STATUS).indexOf(key) < Object.keys(DOK_STATUS).indexOf(dokStatus)
            return (
              <div key={key} className="flex items-center gap-1">
                {i > 0 && <span className={`text-xs ${past || active ? 'text-green-500' : 'text-slate-300'}`}>&rarr;</span>}
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                  active ? val.activeCls :
                  past ? 'bg-green-100 text-green-700' :
                  'bg-slate-100 text-slate-400'
                }`}>
                  {val.label}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// PositionRow Component
// =============================================================================
function PositionRow({ pos, index, total, onUpdate, onRemove, onMove, onAddAfter, addMenuOpen, setAddMenuOpen }) {
  const isMenuOpen = addMenuOpen === index

  // Zwischensumme
  if (pos.typ === 'zwischensumme') {
    return (
      <tr className="bg-slate-100 border-t border-b border-slate-300">
        <td className="px-1">
          <div className="flex flex-col">
            {index > 0 && <button onClick={() => onMove(index, -1)} className="text-[10px] text-slate-400 hover:text-slate-600 leading-none">&uarr;</button>}
            {index < total - 1 && <button onClick={() => onMove(index, 1)} className="text-[10px] text-slate-400 hover:text-slate-600 leading-none">&darr;</button>}
          </div>
        </td>
        <td className="px-2 py-2"></td>
        <td className="px-3 py-2 text-sm font-semibold text-slate-700" colSpan={4}>
          <input value={pos.bezeichnung} onChange={e => onUpdate(pos.id, 'bezeichnung', e.target.value)}
            className="bg-transparent border-0 outline-none font-semibold text-sm text-slate-700 w-full" placeholder="Zwischensumme" />
        </td>
        <td className="px-2 py-2 text-right text-sm font-bold text-slate-800">{euro(pos._zsSum || 0)}</td>
        <td className="px-1"><button onClick={() => onRemove(pos.id)} className="text-slate-300 hover:text-red-500 text-xs">X</button></td>
      </tr>
    )
  }

  // Freitext
  if (pos.typ === 'freitext') {
    return (
      <tr className="bg-blue-50/30 border-t border-slate-100">
        <td className="px-1">
          <div className="flex flex-col">
            {index > 0 && <button onClick={() => onMove(index, -1)} className="text-[10px] text-slate-400 hover:text-slate-600 leading-none">&uarr;</button>}
            {index < total - 1 && <button onClick={() => onMove(index, 1)} className="text-[10px] text-slate-400 hover:text-slate-600 leading-none">&darr;</button>}
          </div>
        </td>
        <td className="px-2 py-2">
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-600 font-medium">Text</span>
        </td>
        <td className="px-3 py-2" colSpan={4}>
          <input value={pos.bezeichnung} onChange={e => onUpdate(pos.id, 'bezeichnung', e.target.value)}
            className="w-full bg-transparent border-0 outline-none text-sm font-semibold text-slate-700 focus:bg-blue-50 rounded px-1" placeholder="Ueberschrift / Freitext..." />
          <input value={pos.beschreibung} onChange={e => onUpdate(pos.id, 'beschreibung', e.target.value)}
            className="w-full bg-transparent border-0 outline-none text-xs text-slate-500 mt-0.5 focus:bg-blue-50 rounded px-1" placeholder="Beschreibung (optional)..." />
        </td>
        <td></td>
        <td className="px-1"><button onClick={() => onRemove(pos.id)} className="text-slate-300 hover:text-red-500 text-xs">X</button></td>
      </tr>
    )
  }

  // Normal / Alternative / Optional
  const typeInfo = POS_TYPES[pos.typ] || POS_TYPES.normal
  const isExcluded = pos.typ === 'alternative' || pos.typ === 'optional'
  const lineSum = pos._lineSum || 0

  return (
    <>
      <tr className={`border-t border-slate-100 hover:bg-slate-50 group ${isExcluded ? 'opacity-70' : ''}`}>
        <td className="px-1">
          <div className="flex flex-col opacity-0 group-hover:opacity-100 transition-opacity">
            {index > 0 && <button onClick={() => onMove(index, -1)} className="text-[10px] text-slate-400 hover:text-slate-600 leading-none">&uarr;</button>}
            {index < total - 1 && <button onClick={() => onMove(index, 1)} className="text-[10px] text-slate-400 hover:text-slate-600 leading-none">&darr;</button>}
          </div>
        </td>
        <td className="px-2 py-2 text-sm text-slate-500 align-top">
          {pos.posNr && <span className="font-medium">{pos.posNr}.</span>}
          {typeInfo.badge && (
            <div className={`text-[9px] px-1.5 py-0.5 rounded mt-0.5 font-medium inline-block ${typeInfo.badgeCls}`}>
              {typeInfo.badge}
            </div>
          )}
        </td>
        <td className="px-3 py-2 align-top">
          <input value={pos.bezeichnung} onChange={e => onUpdate(pos.id, 'bezeichnung', e.target.value)}
            className="w-full bg-transparent border-0 outline-none text-sm text-slate-800 focus:bg-orange-50 rounded px-1 font-medium" placeholder="Bezeichnung..." />
          <input value={pos.beschreibung} onChange={e => onUpdate(pos.id, 'beschreibung', e.target.value)}
            className="w-full bg-transparent border-0 outline-none text-xs text-slate-500 mt-0.5 focus:bg-orange-50 rounded px-1" placeholder="Beschreibung..." />
        </td>
        <td className="px-2 py-2 align-top">
          <input type="number" step="0.1" value={pos.menge || ''} onChange={e => onUpdate(pos.id, 'menge', e.target.value)}
            className="w-full bg-transparent border-0 outline-none text-sm text-right focus:bg-orange-50 rounded px-1" />
        </td>
        <td className="px-2 py-2 align-top">
          <select value={pos.einheit} onChange={e => onUpdate(pos.id, 'einheit', e.target.value)}
            className="bg-transparent border-0 outline-none text-xs text-slate-600 focus:bg-orange-50 rounded">
            {EINHEITEN.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        </td>
        <td className="px-2 py-2 align-top">
          <input type="number" step="0.01" value={pos.einzelpreis || ''} onChange={e => onUpdate(pos.id, 'einzelpreis', e.target.value)}
            className="w-full bg-transparent border-0 outline-none text-sm text-right focus:bg-orange-50 rounded px-1" />
        </td>
        <td className="px-2 py-2 text-right text-sm font-medium align-top">
          <span className={isExcluded ? 'text-slate-400 line-through' : 'text-slate-800'}>
            {lineSum > 0 ? euro(lineSum) : '-'}
          </span>
        </td>
        <td className="px-1 align-top pt-2">
          <button onClick={() => onRemove(pos.id)} className="text-slate-300 hover:text-red-500 text-xs opacity-0 group-hover:opacity-100 transition-opacity">X</button>
        </td>
      </tr>
      {/* Insert after line (minimal) */}
      {isMenuOpen && (
        <tr>
          <td colSpan={8} className="px-4 py-1 bg-orange-50 border-b border-orange-200">
            <div className="flex gap-2">
              {Object.entries(POS_TYPES).map(([key, val]) => (
                <button key={key} onClick={() => onAddAfter(key)}
                  className={`text-[10px] font-medium px-2 py-0.5 rounded ${val.btnCls}`}>
                  + {val.label}
                </button>
              ))}
              <button onClick={() => setAddMenuOpen(null)} className="text-[10px] text-slate-400 ml-auto">Abbrechen</button>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// =============================================================================
// Print Preview Component
// =============================================================================
function PrintPreview({ allgemein, angebotNr, gueltigBis, einleitung, schluss, dokStatus, angCalc, gesamtRabatt, zuschlaege }) {
  const dokLabel = DOK_STATUS[dokStatus]?.label || 'Angebot'

  return (
    <div className="bg-white max-w-[210mm] mx-auto p-8 shadow-lg text-sm" style={{ fontFamily: 'system-ui, sans-serif' }}>
      {/* Briefkopf */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="text-xl font-bold text-slate-800">Meister Eder Schreinerei</div>
          <div className="text-xs text-slate-500 mt-1">
            Schreinerei &amp; Innenausbau<br />
            Ober-Moerlen
          </div>
        </div>
        <div className="text-right text-xs text-slate-500">
          <div className="font-semibold text-slate-700 text-base mb-1">{dokLabel}</div>
          <div>Nr.: {angebotNr}</div>
          <div>Datum: {new Date(allgemein.datum).toLocaleDateString('de-DE')}</div>
          <div>Gueltig bis: {new Date(gueltigBis).toLocaleDateString('de-DE')}</div>
        </div>
      </div>

      {/* Kundenadresse */}
      <div className="mb-6 text-xs text-slate-400">
        <div className="text-[9px] border-b border-slate-300 pb-0.5 mb-1">Meister Eder Schreinerei - Ober-Moerlen</div>
        <div className="text-sm text-slate-800 font-medium">{allgemein.kunde || 'Kunde'}</div>
      </div>

      {/* Betreff */}
      <div className="mb-4">
        <div className="font-bold text-slate-800">{dokLabel}: {allgemein.gegenstand || 'Sonderbau'}</div>
        {allgemein.bearbeiter && <div className="text-xs text-slate-500 mt-0.5">Sachbearbeiter: {allgemein.bearbeiter}</div>}
      </div>

      {/* Einleitung */}
      {einleitung && <p className="text-xs text-slate-600 mb-4 leading-relaxed">{einleitung}</p>}

      {/* Positionstabelle */}
      <table className="w-full mb-4 text-xs">
        <thead>
          <tr className="border-b-2 border-slate-300">
            <th className="text-left py-1.5 w-10">Pos.</th>
            <th className="text-left py-1.5">Bezeichnung</th>
            <th className="text-right py-1.5 w-14">Menge</th>
            <th className="text-left py-1.5 w-12 pl-2">Einh.</th>
            <th className="text-right py-1.5 w-20">EP (EUR)</th>
            <th className="text-right py-1.5 w-24">GP (EUR)</th>
          </tr>
        </thead>
        <tbody>
          {angCalc.positionen.map((p) => {
            if (p.typ === 'zwischensumme') {
              return (
                <tr key={p.id} className="border-t border-slate-300 bg-slate-50">
                  <td colSpan={5} className="py-1.5 font-semibold">{p.bezeichnung}</td>
                  <td className="py-1.5 text-right font-bold">{euro(p._zsSum || 0)}</td>
                </tr>
              )
            }
            if (p.typ === 'freitext') {
              return (
                <tr key={p.id}>
                  <td></td>
                  <td colSpan={5} className="py-2">
                    <div className="font-semibold text-slate-700">{p.bezeichnung}</div>
                    {p.beschreibung && <div className="text-slate-500">{p.beschreibung}</div>}
                  </td>
                </tr>
              )
            }
            const isExcl = p.typ === 'alternative' || p.typ === 'optional'
            return (
              <tr key={p.id} className={`border-t border-slate-100 ${isExcl ? 'text-slate-400' : ''}`}>
                <td className="py-1.5 align-top">
                  {p.posNr}.
                  {isExcl && <div className="text-[8px] italic">{POS_TYPES[p.typ].badge}</div>}
                </td>
                <td className="py-1.5 align-top">
                  <div className={isExcl ? '' : 'font-medium'}>{p.bezeichnung}</div>
                  {p.beschreibung && <div className="text-slate-500 text-[10px]">{p.beschreibung}</div>}
                </td>
                <td className="py-1.5 text-right align-top">{num(p.menge) > 0 ? num(p.menge) : ''}</td>
                <td className="py-1.5 pl-2 align-top">{p.einheit}</td>
                <td className="py-1.5 text-right align-top">{num(p.einzelpreis) > 0 ? euro(p.einzelpreis) : ''}</td>
                <td className={`py-1.5 text-right align-top ${isExcl ? 'line-through' : 'font-medium'}`}>
                  {(p._lineSum || 0) > 0 ? euro(p._lineSum) : ''}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* Summenblock */}
      <div className="border-t-2 border-slate-300 pt-3 ml-auto max-w-xs">
        <div className="flex justify-between py-0.5">
          <span>Summe netto</span>
          <span className="font-medium">{euro(angCalc.netto)}</span>
        </div>
        {angCalc.rabattBetrag > 0 && (
          <>
            <div className="flex justify-between py-0.5 text-red-600">
              <span>Rabatt {gesamtRabatt.modus === 'prozent' ? `(${num(gesamtRabatt.wert)}%)` : ''}</span>
              <span>-{euro(angCalc.rabattBetrag)}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span>Netto nach Rabatt</span>
              <span className="font-medium">{euro(angCalc.nettoNachRabatt)}</span>
            </div>
          </>
        )}
        <div className="flex justify-between py-0.5">
          <span>MwSt. {angCalc.mwstSatz}%</span>
          <span>{euro(angCalc.mwst)}</span>
        </div>
        <div className="flex justify-between py-1.5 border-t-2 border-slate-800 mt-1 font-bold text-base">
          <span>Gesamtbetrag</span>
          <span>{euro(angCalc.brutto)}</span>
        </div>
      </div>

      {/* Schlusstext */}
      {schluss && <p className="text-xs text-slate-600 mt-6 leading-relaxed">{schluss}</p>}

      {/* Unterschrift */}
      <div className="mt-12 flex justify-between text-xs text-slate-400">
        <div>
          <div className="border-t border-slate-300 pt-1 w-48">Ort, Datum</div>
        </div>
        <div>
          <div className="border-t border-slate-300 pt-1 w-48 text-right">Unterschrift Auftraggeber</div>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-8 pt-3 border-t border-slate-200 text-[9px] text-slate-400 flex justify-between">
        <span>Meister Eder Schreinerei | Ober-Moerlen</span>
        <span>{allgemein.bearbeiter || 'Sachbearbeiter'}</span>
        <span>{angebotNr}</span>
      </div>
    </div>
  )
}
