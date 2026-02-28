import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { analyse, bildAnalyse, einkauf, chat as chatApi } from '../api'
import AngebotTab from '../components/AngebotTab'
import { buildChatContext, buildAutoVorschlagRequest } from '../chatContext'

function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}
function num(val) {
  return parseFloat(val) || 0
}

// --- Default rows per section ---
const mkRow = (id, extra = {}) => ({ id, bezeichnung: '', ...extra })

const DEFAULT_VARIABLEN = {
  lohn1: 75, lohn2: 160, lohn3: 65, kfzKm: 0.40,
}
const DEFAULT_ZUSCHLAEGE = {
  kleinteile: 10, margeMaterial: 100, margeZukauf: 50, handlingfee: 0,
  wug: 0, rabatt: 0, mwst: 19,
}

const LOHN_KATEGORIEN = [
  { bezeichnung: 'Projektmanagement', lohnart: 1 },
  { bezeichnung: 'Arbeitsvorbereitung', lohnart: 1 },
  { bezeichnung: 'Maschinenraum', lohnart: 1 },
  { bezeichnung: 'Bankraum', lohnart: 1 },
  { bezeichnung: 'Oberflaeche', lohnart: 1 },
  { bezeichnung: 'CNC', lohnart: 2 },
  { bezeichnung: 'Elektro', lohnart: 1 },
  { bezeichnung: 'Verpackung', lohnart: 1 },
  { bezeichnung: 'Handling', lohnart: 1 },
  { bezeichnung: 'Montage', lohnart: 3 },
]

// --- Reusable table row components ---
function InputCell({ value, onChange, type = 'text', placeholder = '', className = '', step, min }) {
  return (
    <input
      type={type} step={step} min={min}
      value={value || (type === 'number' ? '' : '')}
      onChange={e => onChange(type === 'number' ? e.target.value : e.target.value)}
      placeholder={placeholder}
      className={`w-full border-0 bg-transparent text-sm outline-none text-slate-200 placeholder-slate-500 focus:bg-slate-700/50 focus:ring-1 focus:ring-amber-500/50 rounded px-2 py-1 ${className}`}
    />
  )
}

function SectionHeader({ title, summe, open, onToggle, nr }) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/60 hover:bg-slate-700/60 transition-colors border-b border-slate-700/50"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-400 w-6">{open ? '\u25BC' : '\u25B6'}</span>
        <span className="text-xs font-bold text-amber-500/70 uppercase">{nr}</span>
        <span className="font-semibold text-slate-200 text-sm">{title}</span>
      </div>
      {summe !== null && <span className="text-sm font-bold text-amber-400">{euro(summe)}</span>}
    </button>
  )
}

function AddRowBtn({ onClick, label = '+ Zeile' }) {
  return (
    <button onClick={onClick} className="text-xs text-amber-500 hover:text-amber-400 font-medium px-4 py-1.5">
      {label}
    </button>
  )
}

function RemoveBtn({ onClick }) {
  return (
    <button onClick={onClick} className="text-slate-600 hover:text-red-400 text-xs opacity-0 group-hover:opacity-100 transition-opacity" title="Entfernen">
      X
    </button>
  )
}

// ============================================================================
export default function Kalkulator({ updateChatContext, addChatMessages, registerActionHandler }) {
  // --- State ---
  const [allgemein, setAllgemein] = useState({ kunde: '', gegenstand: '', bearbeiter: '', datum: new Date().toISOString().slice(0, 10) })
  const [variablen, setVariablen] = useState({ ...DEFAULT_VARIABLEN })
  const [zuschlaege, setZuschlaege] = useState({ ...DEFAULT_ZUSCHLAEGE })

  const [platten, setPlatten] = useState([mkRow(1, { staerke: '', verschnitt: 10, preisQm: 0, menge: 0 })])
  const [massivholz, setMassivholz] = useState([mkRow(1, { staerke: '', verschnitt: 10, preisCbm: 0, menge: 0 })])
  const [kanten, setKanten] = useState([mkRow(1, { laenge: 0, bearbeitung: 1, kantePreis: 1 })])
  const [halbzeuge, setHalbzeuge] = useState([mkRow(1, { anzahl: 0, einheit: 'Stk', preis: 0 })])
  const [beschlaege, setBeschlaege] = useState([mkRow(1, { anzahl: 0, einheit: 'Stk', preis: 0 })])
  const [lacke, setLacke] = useState([mkRow(1, { liter: 0, preis: 0 })])

  const [zukaufteile, setZukaufteile] = useState([mkRow(1, { marke: '', link: '', anzahl: 0, einheit: 'Stk', preis: 0 })])
  const [fremdmaterial, setFremdmaterial] = useState([mkRow(1, { anzahl: 0, preis: 0, handlingPct: 10 })])

  const [lohn, setLohn] = useState(LOHN_KATEGORIEN.map((k, i) => ({ id: i + 1, bezeichnung: k.bezeichnung, stunden: 0, lohnart: k.lohnart })))
  const [kfz, setKfz] = useState({ kmEinfach: 0, anzahlWege: 0 })

  const [openSections, setOpenSections] = useState({
    allgemein: true, variablen: false, platten: true, massivholz: false, kanten: false,
    halbzeuge: false, beschlaege: false, lacke: false, zukaufteile: true, fremdmaterial: false,
    lohn: true, kfz: false,
  })

  // SmartWOP Import
  const [importStatus, setImportStatus] = useState(null)
  const fileInputRef = useRef(null)

  // 3D/Bild Analyse
  const [bildInputRef] = useState(() => ({ current: null }))
  const bildRef = useRef(null)
  const [bildStatus, setBildStatus] = useState(null)
  const [bildResult, setBildResult] = useState(null)

  // Tab (Kalkulation / Angebot)
  const [activeTab, setActiveTab] = useState('kalkulation')

  // Zukaufteile KI-Suche
  const [zkSearch, setZkSearch] = useState({}) // { [rowId]: { loading, treffer, error } }

  const [nextId, setNextId] = useState(100)
  const nid = () => { const n = nextId; setNextId(p => p + 1); return n }

  const toggle = (key) => setOpenSections(prev => ({ ...prev, [key]: !prev[key] }))

  // --- Generic list helpers ---
  const updateList = (setter) => (id, field, value) =>
    setter(prev => prev.map(r => r.id === id ? { ...r, [field]: value } : r))
  const removeFromList = (setter) => (id) =>
    setter(prev => prev.filter(r => r.id !== id))

  // --- Zukaufteile: KI-Produktsuche ---
  const searchZukaufteil = async (rowId) => {
    const row = zukaufteile.find(r => r.id === rowId)
    if (!row) return
    const suchbegriff = (row.bezeichnung || '').trim()
    if (!suchbegriff) return

    setZkSearch(prev => ({ ...prev, [rowId]: { loading: true, treffer: null, error: null } }))
    try {
      const result = await einkauf.recherche(suchbegriff, row.marke || '', '', 'google_shopping,amazon,haefele')
      if (result.status === 'ok' && result.treffer?.length > 0) {
        setZkSearch(prev => ({ ...prev, [rowId]: { loading: false, treffer: result.treffer, error: null } }))
        // Wenn nur 1 Treffer oder guenstigster vorhanden: direkt uebernehmen
        if (result.guenstigster && result.treffer.length <= 3) {
          applyZkTreffer(rowId, result.guenstigster)
        }
      } else {
        setZkSearch(prev => ({ ...prev, [rowId]: { loading: false, treffer: [], error: 'Keine Treffer gefunden' } }))
      }
    } catch (err) {
      setZkSearch(prev => ({ ...prev, [rowId]: { loading: false, treffer: null, error: err.message } }))
    }
  }

  const applyZkTreffer = (rowId, treffer) => {
    setZukaufteile(prev => prev.map(r => {
      if (r.id !== rowId) return r
      return {
        ...r,
        bezeichnung: treffer.titel || r.bezeichnung,
        marke: treffer.quelle === 'haefele' ? 'Haefele' : (treffer.shop || treffer.quelle || r.marke),
        preis: treffer.preis > 0 ? treffer.preis : r.preis,
        link: treffer.link || r.link,
        anzahl: num(r.anzahl) > 0 ? r.anzahl : 1,
      }
    }))
    // Dropdown schliessen
    setZkSearch(prev => { const n = { ...prev }; delete n[rowId]; return n })
  }

  const searchAllZukaufteile = async () => {
    const rows = zukaufteile.filter(r => (r.bezeichnung || '').trim() && num(r.preis) === 0)
    for (const row of rows) {
      await searchZukaufteil(row.id)
    }
  }

  // --- Berechnungen ---
  const calc = useMemo(() => {
    const sumPlatten = platten.reduce((s, r) => {
      const menge = num(r.menge)
      const rohMenge = menge + (menge * num(r.verschnitt) / 100)
      return s + rohMenge * num(r.preisQm)
    }, 0)

    const sumMassivholz = massivholz.reduce((s, r) => {
      const menge = num(r.menge)
      const rohMenge = menge + (menge * num(r.verschnitt) / 100)
      return s + rohMenge * num(r.preisCbm)
    }, 0)

    const sumKanten = kanten.reduce((s, r) =>
      s + num(r.laenge) * (num(r.bearbeitung) + num(r.kantePreis)), 0)

    const sumHalbzeuge = halbzeuge.reduce((s, r) =>
      s + num(r.anzahl) * num(r.preis), 0)

    const sumBeschlaege = beschlaege.reduce((s, r) =>
      s + num(r.anzahl) * num(r.preis), 0)

    const sumLacke = lacke.reduce((s, r) =>
      s + num(r.liter) * num(r.preis), 0)

    const materialRoh = sumPlatten + sumMassivholz + sumKanten + sumHalbzeuge + sumBeschlaege + sumLacke
    const kleinteilZuschlag = materialRoh * num(zuschlaege.kleinteile) / 100
    const materialMitKleinteile = materialRoh + kleinteilZuschlag
    const margeMaterial = materialMitKleinteile * num(zuschlaege.margeMaterial) / 100
    const summeVerarbeiteteMat = materialMitKleinteile + margeMaterial

    const sumZukauf = zukaufteile.reduce((s, r) =>
      s + num(r.anzahl) * num(r.preis), 0)
    const margeZukauf = sumZukauf * num(zuschlaege.margeZukauf) / 100
    const summeHalbfabrikate = sumZukauf + margeZukauf

    const sumFremd = fremdmaterial.reduce((s, r) =>
      s + num(r.anzahl) * num(r.preis) * num(r.handlingPct) / 100, 0)

    const summeMaterialGesamt = summeVerarbeiteteMat + summeHalbfabrikate + sumFremd

    const lohnSaetze = { 1: num(variablen.lohn1), 2: num(variablen.lohn2), 3: num(variablen.lohn3) }
    const sumLohn = lohn.reduce((s, r) => {
      const satz = lohnSaetze[r.lohnart] || lohnSaetze[1]
      return s + num(r.stunden) * satz
    }, 0)
    const sumStunden = lohn.reduce((s, r) => s + num(r.stunden), 0)

    const sumKfz = num(kfz.kmEinfach) * num(kfz.anzahlWege) * num(variablen.kfzKm)

    const selbstkosten = summeMaterialGesamt + sumLohn + sumKfz

    const wug = selbstkosten * num(zuschlaege.wug) / 100
    const gesamt = selbstkosten + wug

    const db1 = gesamt - sumKfz - sumZukauf - kleinteilZuschlag - materialRoh

    const rabattPct = num(zuschlaege.rabatt)
    const rabattBetrag = rabattPct > 0 ? gesamt / (1 - rabattPct / 100) - gesamt : 0
    const gesamtMitRabatt = gesamt + rabattBetrag

    const mwst = gesamtMitRabatt * num(zuschlaege.mwst) / 100
    const brutto = gesamtMitRabatt + mwst

    return {
      sumPlatten, sumMassivholz, sumKanten, sumHalbzeuge, sumBeschlaege, sumLacke,
      materialRoh, kleinteilZuschlag, margeMaterial, summeVerarbeiteteMat,
      sumZukauf, margeZukauf, summeHalbfabrikate,
      sumFremd, summeMaterialGesamt,
      sumLohn, sumStunden, sumKfz,
      selbstkosten, wug, gesamt, db1,
      rabattBetrag, gesamtMitRabatt, mwst, brutto,
    }
  }, [platten, massivholz, kanten, halbzeuge, beschlaege, lacke, zukaufteile, fremdmaterial, lohn, kfz, variablen, zuschlaege])

  // --- Chat-Integration: Kontext-Updates ---
  useEffect(() => {
    if (updateChatContext) {
      updateChatContext(buildChatContext({ allgemein, platten, beschlaege, zukaufteile, halbzeuge, lohn, calc, zuschlaege }))
    }
  }, [allgemein, platten, beschlaege, zukaufteile, halbzeuge, lohn, calc, zuschlaege, updateChatContext])

  // --- Chat-Integration: Action-Handler registrieren ---
  const handleChatAction = useCallback((action) => {
    if (!action) return
    switch (action.type) {
      case 'set_price': {
        const bez = (action.bezeichnung || '').toLowerCase()
        const kat = action.kategorie || 'platten'
        const field = action.field || 'preis'
        const value = parseFloat(action.value) || 0
        if (kat === 'platten') {
          setPlatten(prev => prev.map(r =>
            (r.bezeichnung || '').toLowerCase().includes(bez) ? { ...r, [field]: value } : r
          ))
        } else if (kat === 'beschlaege') {
          setBeschlaege(prev => prev.map(r =>
            (r.bezeichnung || '').toLowerCase().includes(bez) ? { ...r, preis: value } : r
          ))
        } else if (kat === 'zukaufteile') {
          setZukaufteile(prev => prev.map(r =>
            (r.bezeichnung || '').toLowerCase().includes(bez) ? { ...r, preis: value } : r
          ))
        } else if (kat === 'halbzeuge') {
          setHalbzeuge(prev => prev.map(r =>
            (r.bezeichnung || '').toLowerCase().includes(bez) ? { ...r, preis: value } : r
          ))
        }
        break
      }
      case 'set_hours': {
        const bez = (action.bezeichnung || '').toLowerCase()
        const value = parseFloat(action.value) || 0
        setLohn(prev => prev.map(r =>
          (r.bezeichnung || '').toLowerCase().includes(bez) ? { ...r, stunden: value } : r
        ))
        break
      }
      case 'set_zuschlag': {
        const field = action.field
        const value = parseFloat(action.value) || 0
        if (field && field in zuschlaege) {
          setZuschlaege(prev => ({ ...prev, [field]: value }))
        }
        break
      }
      default:
        break
    }
  }, [zuschlaege])

  useEffect(() => {
    if (registerActionHandler) {
      registerActionHandler(handleChatAction)
    }
  }, [registerActionHandler, handleChatAction])

  // --- SmartWOP CSV Import ---
  const handleSmartWopImport = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    setImportStatus({ type: 'loading', msg: `${files.length} SmartWOP CSV${files.length > 1 ? 's' : ''} werden gelesen...` })

    try {
      const result = await analyse.smartwopUpload(files)

      if (result.status !== 'ok') {
        setImportStatus({ type: 'error', msg: result.fehler || 'Import fehlgeschlagen' })
        return
      }

      // Stuecklisten aus allen Moebeln zusammenfuehren
      const moebel = result.moebel_stuecklisten || []

      // Alle Bauteile und Beschlaege aus allen Moebeln sammeln
      const alleBauteile = moebel.flatMap(m => m.bauteile || [])
      const alleBeschlaege = moebel.flatMap(m => m.beschlaege || [])

      // Material-Gruppen: gleiches Material zusammenfassen zu qm
      const matMap = {}
      for (const b of alleBauteile) {
        const key = b.material_code || b.egger_dekor || 'unbekannt'
        if (!matMap[key]) {
          matMap[key] = {
            bezeichnung: `${b.egger_name || b.material_code || 'Material'} (${b.egger_dekor || key})`,
            staerke: b.staerke_mm ? `${b.staerke_mm}mm` : '',
            qm: 0, count: 0,
          }
        }
        const qm = (num(b.laenge_mm) * num(b.breite_mm) * num(b.anzahl)) / 1000000
        matMap[key].qm += qm
        matMap[key].count += num(b.anzahl)
      }

      // Platten befuellen
      const neuePlatten = Object.entries(matMap).map(([key, v]) => mkRow(nid(), {
        bezeichnung: v.bezeichnung,
        staerke: v.staerke,
        verschnitt: 10,
        preisQm: 0,
        menge: Math.round(v.qm * 1000) / 1000,
      }))
      if (neuePlatten.length > 0) {
        setPlatten(prev => [...prev.filter(r => r.bezeichnung || num(r.menge) > 0), ...neuePlatten])
        setOpenSections(prev => ({ ...prev, platten: true }))
      }

      // Beschlaege befuellen (aus allen Moebeln gesammelt)
      if (alleBeschlaege.length > 0) {
        const neueBeschlaege = alleBeschlaege.map(b => mkRow(nid(), {
          bezeichnung: `${b.bezeichnung || b.artikel_nr || 'Beschlag'}`,
          anzahl: num(b.anzahl),
          einheit: 'Stk',
          preis: 0,
        }))
        setBeschlaege(prev => [...prev.filter(r => r.bezeichnung || num(r.anzahl) > 0), ...neueBeschlaege])
        setOpenSections(prev => ({ ...prev, beschlaege: true }))
      }

      // Moebel-Info als Gegenstand setzen
      if (moebel.length > 0 && !allgemein.gegenstand) {
        const namen = moebel.map(m => m.moebel_name).filter(Boolean).join(', ')
        if (namen) setAllgemein(prev => ({ ...prev, gegenstand: namen }))
      }

      const anzahl = Object.keys(matMap).length
      setImportStatus({
        type: 'success',
        msg: `${anzahl} Materialien + ${alleBeschlaege.length} Beschlaege importiert aus ${result.csv_dateien || 1} CSV(s)`
      })

      // Auto-Vorschlag via KI-Chat nach Import
      if (addChatMessages) {
        try {
          const vorschlagReq = buildAutoVorschlagRequest({
            allgemein: { ...allgemein, gegenstand: allgemein.gegenstand || moebel.map(m => m.moebel_name).filter(Boolean).join(', ') },
            platten: [...platten.filter(r => r.bezeichnung || num(r.menge) > 0), ...neuePlatten],
            beschlaege: [...beschlaege.filter(r => r.bezeichnung || num(r.anzahl) > 0), ...(alleBeschlaege.length > 0 ? alleBeschlaege.map(b => ({
              bezeichnung: b.bezeichnung || b.artikel_nr || 'Beschlag',
              anzahl: num(b.anzahl),
              preis: 0,
            })) : [])],
            calc,
          })
          const vorschlag = await chatApi.autoVorschlag(vorschlagReq)
          if (vorschlag.text) {
            addChatMessages([{
              role: 'assistant',
              content: vorschlag.text,
              actions: vorschlag.actions || [],
              model_used: vorschlag.model_used || 'ollama',
              tokens: vorschlag.tokens || 0,
              ts: Date.now(),
              appliedActions: {},
            }])
          }
        } catch (chatErr) {
          // Chat-Fehler nicht kritisch - Import war trotzdem erfolgreich
          console.warn('Auto-Vorschlag fehlgeschlagen:', chatErr)
        }
      }
    } catch (err) {
      setImportStatus({ type: 'error', msg: `Import-Fehler: ${err.message}` })
    }

    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // --- 3D/Bild Analyse ---
  const handleBildUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBildStatus({ type: 'loading', msg: 'Bild/3D-Datei wird analysiert...' })
    setBildResult(null)

    try {
      const result = await bildAnalyse.analyse(file, allgemein.gegenstand || '')

      if (result.status !== 'ok') {
        setBildStatus({ type: 'error', msg: result.fehler || 'Analyse fehlgeschlagen' })
        return
      }

      setBildResult(result)

      // Analyse-Ergebnisse in Kalkulation uebernehmen
      const a = result.analyse || {}
      const vorschlag = result.kalkulations_vorschlag || {}

      // Materialien einfuegen
      if (a.materialien?.length > 0) {
        const neuePlatten = a.materialien
          .filter(m => m.typ === 'platte' || m.typ === 'massivholz')
          .map(m => mkRow(nid(), {
            bezeichnung: m.bezeichnung || 'Material (KI)',
            staerke: '',
            verschnitt: 10,
            preisQm: num(m.preis_qm_schaetzung),
            menge: num(m.menge_qm),
          }))
        if (neuePlatten.length > 0) {
          setPlatten(prev => [...prev.filter(r => r.bezeichnung || num(r.menge) > 0), ...neuePlatten])
          setOpenSections(prev => ({ ...prev, platten: true }))
        }

        const neueHalbzeuge = a.materialien
          .filter(m => m.typ === 'glas' || m.typ === 'metall')
          .map(m => mkRow(nid(), {
            bezeichnung: m.bezeichnung || 'Halbzeug (KI)',
            anzahl: 1,
            einheit: 'qm',
            preis: num(m.menge_qm) * num(m.preis_qm_schaetzung),
          }))
        if (neueHalbzeuge.length > 0) {
          setHalbzeuge(prev => [...prev.filter(r => r.bezeichnung || num(r.anzahl) > 0), ...neueHalbzeuge])
          setOpenSections(prev => ({ ...prev, halbzeuge: true }))
        }
      }

      // Beschlaege einfuegen
      if (a.beschlaege?.length > 0) {
        const neueBeschl = a.beschlaege.map(b => mkRow(nid(), {
          bezeichnung: b.bezeichnung || 'Beschlag (KI)',
          anzahl: num(b.anzahl),
          einheit: 'Stk',
          preis: num(b.preis_schaetzung),
        }))
        setBeschlaege(prev => [...prev.filter(r => r.bezeichnung || num(r.anzahl) > 0), ...neueBeschl])
        setOpenSections(prev => ({ ...prev, beschlaege: true }))
      }

      // Kanten
      if (num(a.kanten_lfm) > 0 || num(vorschlag?.kanten_lfm_schaetzung) > 0) {
        const lfm = num(a.kanten_lfm) || num(vorschlag?.kanten_lfm_schaetzung)
        setKanten(prev => [...prev.filter(r => r.bezeichnung || num(r.laenge) > 0),
          mkRow(nid(), { bezeichnung: 'ABS (KI-Schaetzung)', laenge: Math.round(lfm * 10) / 10, bearbeitung: 1, kantePreis: 1 })
        ])
        setOpenSections(prev => ({ ...prev, kanten: true }))
      }

      // Arbeitsstunden
      const stunden = a.arbeitsstunden || vorschlag?.arbeitsstunden_schaetzung || {}
      if (stunden.werkstatt || stunden.cnc || stunden.montage || stunden.oberflaeche) {
        setLohn(prev => prev.map(r => {
          if (r.bezeichnung === 'Maschinenraum' || r.bezeichnung === 'Bankraum') return { ...r, stunden: num(stunden.werkstatt) / 2 }
          if (r.bezeichnung === 'CNC') return { ...r, stunden: num(stunden.cnc) }
          if (r.bezeichnung === 'Oberflaeche') return { ...r, stunden: num(stunden.oberflaeche) }
          if (r.bezeichnung === 'Montage') return { ...r, stunden: num(stunden.montage) }
          return r
        }))
        setOpenSections(prev => ({ ...prev, lohn: true }))
      }

      // Gegenstand
      if (a.moebeltyp && !allgemein.gegenstand) {
        setAllgemein(prev => ({ ...prev, gegenstand: a.moebeltyp }))
      }

      setBildStatus({
        type: 'success',
        msg: `${a.moebeltyp || '3D-Objekt'} analysiert - ${a.komplexitaet || vorschlag?.komplexitaet || ''} - KI-Schaetzung: ${
          a.preis_schaetzung ? euro(a.preis_schaetzung.gesamt_netto) : 'siehe Sektionen'
        }`
      })
    } catch (err) {
      setBildStatus({ type: 'error', msg: `Analyse-Fehler: ${err.message}` })
    }

    if (bildRef.current) bildRef.current.value = ''
  }

  // --- CSV Export ---
  const exportCSV = () => {
    const lines = ['\uFEFF']
    const sep = ';'
    const de = (v) => v.toFixed(2).replace('.', ',')

    lines.push(`Sonderbau-Kalkulation${sep}${allgemein.gegenstand}`)
    lines.push(`Kunde${sep}${allgemein.kunde}`)
    lines.push(`Bearbeiter${sep}${allgemein.bearbeiter}`)
    lines.push(`Datum${sep}${allgemein.datum}`)
    lines.push('')

    // Detaillierte Positionen
    lines.push(`Pos${sep}Bezeichnung${sep}Marke${sep}Menge${sep}Einheit${sep}EK-Preis${sep}Summe`)

    // Platten
    platten.filter(r => num(r.menge) > 0).forEach(r => {
      const m = num(r.menge); const roh = m + m * num(r.verschnitt) / 100
      lines.push(`Material${sep}${r.bezeichnung}${sep}${r.staerke}${sep}${roh.toFixed(3)}${sep}qm${sep}${de(num(r.preisQm))}${sep}${de(roh * num(r.preisQm))}`)
    })
    // Zukaufteile
    zukaufteile.filter(r => num(r.anzahl) > 0).forEach(r => {
      lines.push(`Zukauf${sep}${r.bezeichnung}${sep}${r.marke || ''}${sep}${r.anzahl}${sep}${r.einheit}${sep}${de(num(r.preis))}${sep}${de(num(r.anzahl) * num(r.preis))}`)
    })

    lines.push('')
    lines.push(`Kostenart${sep}Betrag`)
    lines.push(`Material (Rohkosten)${sep}${de(calc.materialRoh)}`)
    lines.push(`Kleinteile-Zuschlag (${zuschlaege.kleinteile}%)${sep}${de(calc.kleinteilZuschlag)}`)
    lines.push(`Marge Material (${zuschlaege.margeMaterial}%)${sep}${de(calc.margeMaterial)}`)
    lines.push(`Verarbeitete Materialien${sep}${de(calc.summeVerarbeiteteMat)}`)
    lines.push(`Zukaufteile${sep}${de(calc.sumZukauf)}`)
    lines.push(`Marge Zukauf (${zuschlaege.margeZukauf}%)${sep}${de(calc.margeZukauf)}`)
    lines.push(`Halbfabrikate${sep}${de(calc.summeHalbfabrikate)}`)
    lines.push(`Fremdmaterial (Handlingfee)${sep}${de(calc.sumFremd)}`)
    lines.push(`SUMME MATERIAL GESAMT${sep}${de(calc.summeMaterialGesamt)}`)
    lines.push(`Lohn (${calc.sumStunden.toFixed(1)} h)${sep}${de(calc.sumLohn)}`)
    lines.push(`KFZ${sep}${de(calc.sumKfz)}`)
    lines.push(`SELBSTKOSTEN${sep}${de(calc.selbstkosten)}`)
    lines.push(`WUG (${zuschlaege.wug}%)${sep}${de(calc.wug)}`)
    lines.push(`GESAMT${sep}${de(calc.gesamt)}`)
    if (zuschlaege.rabatt > 0) lines.push(`Rabatt (${zuschlaege.rabatt}%)${sep}${de(calc.rabattBetrag)}`)
    lines.push(`Gesamt mit Rabatt${sep}${de(calc.gesamtMitRabatt)}`)
    lines.push(`MWSt (${zuschlaege.mwst}%)${sep}${de(calc.mwst)}`)
    lines.push(`BRUTTOPREIS${sep}${de(calc.brutto)}`)

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Kalkulation_${allgemein.gegenstand || 'Sonderbau'}_${allgemein.datum}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // --- Clear all ---
  const clearAll = () => {
    if (!confirm('Alle Eingaben loeschen?')) return
    setAllgemein({ kunde: '', gegenstand: '', bearbeiter: '', datum: new Date().toISOString().slice(0, 10) })
    setVariablen({ ...DEFAULT_VARIABLEN })
    setZuschlaege({ ...DEFAULT_ZUSCHLAEGE })
    setPlatten([mkRow(nid(), { staerke: '', verschnitt: 10, preisQm: 0, menge: 0 })])
    setMassivholz([mkRow(nid(), { staerke: '', verschnitt: 10, preisCbm: 0, menge: 0 })])
    setKanten([mkRow(nid(), { laenge: 0, bearbeitung: 1, kantePreis: 1 })])
    setHalbzeuge([mkRow(nid(), { anzahl: 0, einheit: 'Stk', preis: 0 })])
    setBeschlaege([mkRow(nid(), { anzahl: 0, einheit: 'Stk', preis: 0 })])
    setLacke([mkRow(nid(), { liter: 0, preis: 0 })])
    setZukaufteile([mkRow(nid(), { marke: '', link: '', anzahl: 0, einheit: 'Stk', preis: 0 })])
    setFremdmaterial([mkRow(nid(), { anzahl: 0, preis: 0, handlingPct: 10 })])
    setLohn(LOHN_KATEGORIEN.map((k, i) => ({ id: nid() + i, bezeichnung: k.bezeichnung, stunden: 0, lohnart: k.lohnart })))
    setKfz({ kmEinfach: 0, anzahlWege: 0 })
    setImportStatus(null)
  }

  // --- Render ---
  const inputCls = 'bg-slate-800/60 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50 placeholder-slate-500'
  const thCls = 'px-3 py-2 text-left text-xs text-slate-400 uppercase tracking-wider'

  // Kalk-Daten Paket fuer AngebotTab
  const kalkDaten = { platten, massivholz, kanten, halbzeuge, beschlaege, lacke, zukaufteile, fremdmaterial, lohn, kfz, variablen }

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header + Tabs */}
      <div className="flex items-center justify-between mb-6 animate-fade-in">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-white">Sonderbau-Kalkulation</h1>
          {/* Tab Switcher */}
          <div className="flex bg-slate-800/80 rounded-lg p-0.5 border border-slate-700/50">
            <button onClick={() => setActiveTab('kalkulation')}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${activeTab === 'kalkulation' ? 'bg-amber-600/90 text-white shadow-lg shadow-amber-900/20' : 'text-slate-400 hover:text-slate-200'}`}>
              Kalkulation
            </button>
            <button onClick={() => setActiveTab('angebot')}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${activeTab === 'angebot' ? 'bg-amber-600/90 text-white shadow-lg shadow-amber-900/20' : 'text-slate-400 hover:text-slate-200'}`}>
              Angebot
            </button>
          </div>
        </div>
        <div className="flex gap-2 items-center">
          {/* SmartWOP Import */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            multiple
            onChange={handleSmartWopImport}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="border border-blue-500/30 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
            title="SmartWOP CSV importieren"
          >
            SmartWOP Import
          </button>
          {/* 3D/Bild Analyse */}
          <input
            ref={bildRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.gif,.stl,.obj,.3mf,.ply,.gltf,.glb"
            onChange={handleBildUpload}
            className="hidden"
          />
          <button
            onClick={() => bildRef.current?.click()}
            className="border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
            title="3D-Datei oder Bild fuer KI-Preisschaetzung hochladen"
          >
            3D/Bild Analyse
          </button>
          <button onClick={clearAll} className="text-sm text-slate-500 hover:text-red-400 transition-colors">
            Leeren
          </button>
          <button
            onClick={exportCSV}
            disabled={calc.brutto === 0}
            className="border border-slate-600 hover:border-amber-500/50 hover:bg-amber-500/10 disabled:opacity-30 text-slate-300 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            CSV Export
          </button>
        </div>
      </div>

      {/* Import Status */}
      {importStatus && (
        <div className={`mb-4 px-4 py-2 rounded-lg text-sm ${
          importStatus.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/30' :
          importStatus.type === 'error' ? 'bg-red-500/10 text-red-400 border border-red-500/30' :
          'bg-blue-500/10 text-blue-400 border border-blue-500/30'
        }`}>
          {importStatus.msg}
          <button onClick={() => setImportStatus(null)} className="ml-2 text-xs opacity-60 hover:opacity-100">X</button>
        </div>
      )}

      {bildStatus && (
        <div className={`mb-4 px-4 py-2 rounded-lg text-sm ${
          bildStatus.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' :
          bildStatus.type === 'error' ? 'bg-red-500/10 text-red-400 border border-red-500/30' :
          'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 animate-pulse'
        }`}>
          {bildStatus.msg}
          {bildStatus.type !== 'loading' && (
            <button onClick={() => { setBildStatus(null); setBildResult(null) }} className="ml-2 text-xs opacity-60 hover:opacity-100">X</button>
          )}
        </div>
      )}

      {/* Bild-Analyse Detail-Ergebnis */}
      {bildResult?.analyse?.preis_schaetzung && (
        <div className="mb-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-bold text-emerald-400 text-sm mb-2">KI-Preisschaetzung: {bildResult.analyse.moebeltyp}</h3>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <div className="text-emerald-500/70 text-xs">Material</div>
                  <div className="font-bold text-emerald-300">{euro(bildResult.analyse.preis_schaetzung.material_netto)}</div>
                </div>
                <div>
                  <div className="text-emerald-500/70 text-xs">Lohn</div>
                  <div className="font-bold text-emerald-300">{euro(bildResult.analyse.preis_schaetzung.lohn_netto)}</div>
                </div>
                <div>
                  <div className="text-emerald-500/70 text-xs">Gesamt (netto)</div>
                  <div className="font-bold text-lg text-emerald-200">{euro(bildResult.analyse.preis_schaetzung.gesamt_netto)}</div>
                </div>
              </div>
              {bildResult.analyse.hinweise?.length > 0 && (
                <div className="mt-2 text-xs text-emerald-500/80">
                  {bildResult.analyse.hinweise.map((h, i) => <div key={i}>- {h}</div>)}
                </div>
              )}
            </div>
            <div className="text-right text-xs text-emerald-500/60">
              <div>Konfidenz: {bildResult.analyse.preis_schaetzung.konfidenz}</div>
              <div>{bildResult.tokens} Tokens</div>
              <button onClick={() => setBildResult(null)} className="mt-1 text-emerald-500/60 hover:text-emerald-300">Schliessen</button>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Angebot */}
      {activeTab === 'angebot' && (
        <AngebotTab calc={calc} allgemein={allgemein} zuschlaege={zuschlaege} kalkDaten={kalkDaten} />
      )}

      {/* Tab: Kalkulation */}
      {activeTab === 'kalkulation' && <>
      <div className="flex gap-4">
        {/* Left: Sections */}
        <div className="flex-1 space-y-2 min-w-0">

          {/* 1. Allgemeine Angaben */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Allgemeine Angaben" summe={null} open={openSections.allgemein} onToggle={() => toggle('allgemein')} nr="1" />
            {openSections.allgemein && (
              <div className="p-4 grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-400">Kunde</label>
                  <input value={allgemein.kunde} onChange={e => setAllgemein(p => ({ ...p, kunde: e.target.value }))}
                    className={`w-full ${inputCls}`} placeholder="Firmenname..." />
                </div>
                <div>
                  <label className="text-xs text-slate-400">Gegenstand</label>
                  <input value={allgemein.gegenstand} onChange={e => setAllgemein(p => ({ ...p, gegenstand: e.target.value }))}
                    className={`w-full ${inputCls}`} placeholder="z.B. KlappBar, Empfangstresen..." />
                </div>
                <div>
                  <label className="text-xs text-slate-400">Bearbeiter</label>
                  <input value={allgemein.bearbeiter} onChange={e => setAllgemein(p => ({ ...p, bearbeiter: e.target.value }))}
                    className={`w-full ${inputCls}`} />
                </div>
                <div>
                  <label className="text-xs text-slate-400">Datum</label>
                  <input type="date" value={allgemein.datum} onChange={e => setAllgemein(p => ({ ...p, datum: e.target.value }))}
                    className={`w-full ${inputCls}`} />
                </div>
              </div>
            )}
          </div>

          {/* 3. Variablen */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Variablen & Zuschlaege" summe={null} open={openSections.variablen} onToggle={() => toggle('variablen')} nr="3" />
            {openSections.variablen && (
              <div className="p-4">
                <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                  <div className="col-span-2 text-xs font-bold text-slate-500 uppercase">Lohnsaetze</div>
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-slate-300 w-48">Lohn 1 - Werkstatt</label>
                    <input type="number" step="1" value={variablen.lohn1} onChange={e => setVariablen(p => ({ ...p, lohn1: e.target.value }))}
                      className={`w-24 text-right ${inputCls}`} /><span className="text-xs text-slate-400">EUR/h</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-slate-300 w-48">Lohn 2 - CNC inkl. Mann</label>
                    <input type="number" step="1" value={variablen.lohn2} onChange={e => setVariablen(p => ({ ...p, lohn2: e.target.value }))}
                      className={`w-24 text-right ${inputCls}`} /><span className="text-xs text-slate-400">EUR/h</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-slate-300 w-48">Lohn 3 - Montage vor Ort</label>
                    <input type="number" step="1" value={variablen.lohn3} onChange={e => setVariablen(p => ({ ...p, lohn3: e.target.value }))}
                      className={`w-24 text-right ${inputCls}`} /><span className="text-xs text-slate-400">EUR/h</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-slate-300 w-48">KFZ-Kosten</label>
                    <input type="number" step="0.01" value={variablen.kfzKm} onChange={e => setVariablen(p => ({ ...p, kfzKm: e.target.value }))}
                      className={`w-24 text-right ${inputCls}`} /><span className="text-xs text-slate-400">EUR/km</span>
                  </div>
                  <div className="col-span-2 text-xs font-bold text-slate-500 uppercase mt-3">Zuschlaege</div>
                  {[
                    ['Kleinteile-Zuschlag', 'kleinteile'],
                    ['Marge auf Material', 'margeMaterial'],
                    ['Marge auf Zukaufteile', 'margeZukauf'],
                    ['WUG (Wagnis & Gewinn)', 'wug'],
                    ['Rabatt', 'rabatt'],
                    ['MWSt', 'mwst'],
                  ].map(([label, key]) => (
                    <div key={key} className="flex items-center gap-2">
                      <label className="text-sm text-slate-300 w-48">{label}</label>
                      <input type="number" step="1" value={zuschlaege[key]} onChange={e => setZuschlaege(p => ({ ...p, [key]: e.target.value }))}
                        className={`w-20 text-right ${inputCls}`} /><span className="text-xs text-slate-400">%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 4. Material (Platten) */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Material (Platten)" summe={calc.sumPlatten} open={openSections.platten} onToggle={() => toggle('platten')} nr="4" />
            {openSections.platten && (
              <div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-800/40">
                      <th className={thCls}>Bezeichnung</th>
                      <th className={`${thCls} w-20`}>Staerke</th>
                      <th className={`${thCls} w-16 text-right`}>Verschn.%</th>
                      <th className={`${thCls} w-24 text-right`}>EUR/qm</th>
                      <th className={`${thCls} w-20 text-right`}>Menge qm</th>
                      <th className={`${thCls} w-28 text-right`}>Summe</th>
                      <th className={`${thCls} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {platten.map(r => {
                      const menge = num(r.menge)
                      const rohMenge = menge + (menge * num(r.verschnitt) / 100)
                      const summe = rohMenge * num(r.preisQm)
                      return (
                        <tr key={r.id} className="hover:bg-slate-800/40 group">
                          <td className="px-3 py-1.5"><InputCell value={r.bezeichnung} onChange={v => updateList(setPlatten)(r.id, 'bezeichnung', v)} placeholder="z.B. H1345 ST22" /></td>
                          <td className="px-3 py-1.5"><InputCell value={r.staerke} onChange={v => updateList(setPlatten)(r.id, 'staerke', v)} placeholder="19mm" className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="1" value={r.verschnitt} onChange={v => updateList(setPlatten)(r.id, 'verschnitt', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.preisQm} onChange={v => updateList(setPlatten)(r.id, 'preisQm', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.menge} onChange={v => updateList(setPlatten)(r.id, 'menge', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{summe > 0 ? euro(summe) : '-'}</td>
                          <td className="px-2 py-1.5"><RemoveBtn onClick={() => removeFromList(setPlatten)(r.id)} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <AddRowBtn onClick={() => setPlatten(p => [...p, mkRow(nid(), { staerke: '', verschnitt: 10, preisQm: 0, menge: 0 })])} />
              </div>
            )}
          </div>

          {/* 4b. Massivholz */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Massivholz" summe={calc.sumMassivholz} open={openSections.massivholz} onToggle={() => toggle('massivholz')} nr="4b" />
            {openSections.massivholz && (
              <div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-800/40">
                      <th className={thCls}>Bezeichnung</th>
                      <th className={`${thCls} w-20`}>Staerke</th>
                      <th className={`${thCls} w-16 text-right`}>Verschn.%</th>
                      <th className={`${thCls} w-24 text-right`}>EUR/cbm</th>
                      <th className={`${thCls} w-20 text-right`}>Menge cbm</th>
                      <th className={`${thCls} w-28 text-right`}>Summe</th>
                      <th className={`${thCls} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {massivholz.map(r => {
                      const menge = num(r.menge)
                      const rohMenge = menge + (menge * num(r.verschnitt) / 100)
                      const summe = rohMenge * num(r.preisCbm)
                      return (
                        <tr key={r.id} className="hover:bg-slate-800/40 group">
                          <td className="px-3 py-1.5"><InputCell value={r.bezeichnung} onChange={v => updateList(setMassivholz)(r.id, 'bezeichnung', v)} placeholder="z.B. Eiche" /></td>
                          <td className="px-3 py-1.5"><InputCell value={r.staerke} onChange={v => updateList(setMassivholz)(r.id, 'staerke', v)} placeholder="40mm" className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="1" value={r.verschnitt} onChange={v => updateList(setMassivholz)(r.id, 'verschnitt', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.preisCbm} onChange={v => updateList(setMassivholz)(r.id, 'preisCbm', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.001" value={r.menge} onChange={v => updateList(setMassivholz)(r.id, 'menge', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{summe > 0 ? euro(summe) : '-'}</td>
                          <td className="px-2 py-1.5"><RemoveBtn onClick={() => removeFromList(setMassivholz)(r.id)} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <AddRowBtn onClick={() => setMassivholz(p => [...p, mkRow(nid(), { staerke: '', verschnitt: 10, preisCbm: 0, menge: 0 })])} />
              </div>
            )}
          </div>

          {/* 5. Kanten */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Kanten" summe={calc.sumKanten} open={openSections.kanten} onToggle={() => toggle('kanten')} nr="5" />
            {openSections.kanten && (
              <div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-800/40">
                      <th className={thCls}>Bezeichnung</th>
                      <th className={`${thCls} w-24 text-right`}>Laenge m</th>
                      <th className={`${thCls} w-28 text-right`}>Bearbeitung EUR/m</th>
                      <th className={`${thCls} w-24 text-right`}>Kante EUR/m</th>
                      <th className={`${thCls} w-28 text-right`}>Summe</th>
                      <th className={`${thCls} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {kanten.map(r => {
                      const s = num(r.laenge) * (num(r.bearbeitung) + num(r.kantePreis))
                      return (
                        <tr key={r.id} className="hover:bg-slate-800/40 group">
                          <td className="px-3 py-1.5"><InputCell value={r.bezeichnung} onChange={v => updateList(setKanten)(r.id, 'bezeichnung', v)} placeholder="ABS..." /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.1" value={r.laenge} onChange={v => updateList(setKanten)(r.id, 'laenge', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.bearbeitung} onChange={v => updateList(setKanten)(r.id, 'bearbeitung', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.kantePreis} onChange={v => updateList(setKanten)(r.id, 'kantePreis', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{s > 0 ? euro(s) : '-'}</td>
                          <td className="px-2 py-1.5"><RemoveBtn onClick={() => removeFromList(setKanten)(r.id)} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <AddRowBtn onClick={() => setKanten(p => [...p, mkRow(nid(), { laenge: 0, bearbeitung: 1, kantePreis: 1 })])} />
              </div>
            )}
          </div>

          {/* 6. Halbzeuge (Glas etc.) */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Halbzeuge (Glas etc.)" summe={calc.sumHalbzeuge} open={openSections.halbzeuge} onToggle={() => toggle('halbzeuge')} nr="6" />
            {openSections.halbzeuge && (
              <SimpleItemTable rows={halbzeuge} setter={setHalbzeuge} update={updateList(setHalbzeuge)} remove={removeFromList(setHalbzeuge)} nid={nid} />
            )}
          </div>

          {/* 7. Beschlaege */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Beschlaege" summe={calc.sumBeschlaege} open={openSections.beschlaege} onToggle={() => toggle('beschlaege')} nr="7" />
            {openSections.beschlaege && (
              <SimpleItemTable rows={beschlaege} setter={setBeschlaege} update={updateList(setBeschlaege)} remove={removeFromList(setBeschlaege)} nid={nid} />
            )}
          </div>

          {/* 8. Lacke, Beizen, Oele */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Lacke, Beizen, Oele" summe={calc.sumLacke} open={openSections.lacke} onToggle={() => toggle('lacke')} nr="8" />
            {openSections.lacke && (
              <div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-800/40">
                      <th className={thCls}>Bezeichnung</th>
                      <th className={`${thCls} w-24 text-right`}>Liter</th>
                      <th className={`${thCls} w-24 text-right`}>EUR/Liter</th>
                      <th className={`${thCls} w-28 text-right`}>Summe</th>
                      <th className={`${thCls} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {lacke.map(r => {
                      const s = num(r.liter) * num(r.preis)
                      return (
                        <tr key={r.id} className="hover:bg-slate-800/40 group">
                          <td className="px-3 py-1.5"><InputCell value={r.bezeichnung} onChange={v => updateList(setLacke)(r.id, 'bezeichnung', v)} placeholder="Lack..." /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.1" value={r.liter} onChange={v => updateList(setLacke)(r.id, 'liter', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.preis} onChange={v => updateList(setLacke)(r.id, 'preis', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{s > 0 ? euro(s) : '-'}</td>
                          <td className="px-2 py-1.5"><RemoveBtn onClick={() => removeFromList(setLacke)(r.id)} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <AddRowBtn onClick={() => setLacke(p => [...p, mkRow(nid(), { liter: 0, preis: 0 })])} />
              </div>
            )}
          </div>

          {/* 9. Zukaufteile (mit KI-Preissuche) */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Zukaufteile" summe={calc.sumZukauf} open={openSections.zukaufteile} onToggle={() => toggle('zukaufteile')} nr="9" />
            {openSections.zukaufteile && (
              <div>
                {/* Batch-Suche Button */}
                <div className="px-4 py-2 border-b border-slate-700/50 flex items-center justify-between" style={{ background: 'linear-gradient(90deg, rgba(147,51,234,0.08), rgba(59,130,246,0.08))' }}>
                  <span className="text-xs text-slate-400">Bezeichnung eingeben, dann KI-Suche starten - Preis, Name & Link werden automatisch gefuellt</span>
                  <button
                    onClick={searchAllZukaufteile}
                    disabled={!zukaufteile.some(r => (r.bezeichnung || '').trim() && num(r.preis) === 0)}
                    className="text-xs font-medium px-3 py-1 rounded-md bg-purple-600 text-white hover:bg-purple-700 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed transition-colors"
                  >
                    Alle ohne Preis suchen
                  </button>
                </div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-800/40">
                      <th className={thCls}>Bezeichnung</th>
                      <th className={`${thCls} w-28`}>Marke</th>
                      <th className={`${thCls} w-8`}></th>
                      <th className={`${thCls} w-8`}></th>
                      <th className={`${thCls} w-16 text-right`}>Anz.</th>
                      <th className={`${thCls} w-16`}>Einh.</th>
                      <th className={`${thCls} w-24 text-right`}>EUR/Einh.</th>
                      <th className={`${thCls} w-28 text-right`}>Summe</th>
                      <th className={`${thCls} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {zukaufteile.map(r => {
                      const s = num(r.anzahl) * num(r.preis)
                      const search = zkSearch[r.id]
                      return (
                        <tr key={r.id} className="hover:bg-slate-800/40 group relative">
                          <td className="px-3 py-1.5 relative">
                            <div className="flex items-center gap-1">
                              <InputCell value={r.bezeichnung} onChange={v => updateList(setZukaufteile)(r.id, 'bezeichnung', v)} placeholder="z.B. Scharnier Blum CLIP top" />
                              <button
                                onClick={() => searchZukaufteil(r.id)}
                                disabled={!(r.bezeichnung || '').trim() || search?.loading}
                                className="shrink-0 w-7 h-7 flex items-center justify-center rounded-md bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 disabled:bg-slate-700/50 disabled:text-slate-600 disabled:cursor-not-allowed transition-colors"
                                title="KI-Preissuche starten"
                              >
                                {search?.loading ? (
                                  <span className="animate-spin text-xs">&#9696;</span>
                                ) : (
                                  <span className="text-sm">&#x1F50D;</span>
                                )}
                              </button>
                            </div>
                            {/* Suchergebnis-Dropdown */}
                            {search?.treffer && search.treffer.length > 0 && (
                              <div className="absolute left-0 top-full z-50 w-[500px] bg-slate-800 border border-slate-600 rounded-lg shadow-2xl mt-1 max-h-64 overflow-y-auto">
                                <div className="px-3 py-1.5 bg-slate-700/50 border-b border-slate-600 flex items-center justify-between">
                                  <span className="text-xs font-semibold text-slate-300">{search.treffer.length} Treffer</span>
                                  <button onClick={() => setZkSearch(prev => { const n = { ...prev }; delete n[r.id]; return n })}
                                    className="text-xs text-slate-400 hover:text-red-400">X</button>
                                </div>
                                {search.treffer.map((t, i) => (
                                  <button key={i} onClick={() => applyZkTreffer(r.id, t)}
                                    className="w-full text-left px-3 py-2 hover:bg-purple-500/10 border-b border-slate-700/50 last:border-0 transition-colors">
                                    <div className="flex items-center justify-between gap-2">
                                      <span className="text-sm text-slate-200 truncate flex-1">{t.titel}</span>
                                      <span className="text-sm font-bold text-green-400 shrink-0">{t.preis > 0 ? euro(t.preis) : 'k.A.'}</span>
                                    </div>
                                    <div className="flex items-center gap-2 mt-0.5">
                                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">{t.quelle}</span>
                                      {t.shop && <span className="text-[10px] text-slate-500">{t.shop}</span>}
                                      {t.artikel_nr && <span className="text-[10px] text-slate-500">Art. {t.artikel_nr}</span>}
                                    </div>
                                  </button>
                                ))}
                              </div>
                            )}
                            {search?.error && (
                              <div className="absolute left-0 top-full z-50 bg-red-500/10 border border-red-500/30 rounded-lg shadow-lg mt-1 px-3 py-2">
                                <span className="text-xs text-red-400">{search.error}</span>
                                <button onClick={() => setZkSearch(prev => { const n = { ...prev }; delete n[r.id]; return n })}
                                  className="ml-2 text-xs text-red-500/60 hover:text-red-400">X</button>
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-1.5"><InputCell value={r.marke} onChange={v => updateList(setZukaufteile)(r.id, 'marke', v)} placeholder="Blum, Haefele..." /></td>
                          <td className="px-1 py-1.5 text-center">
                            {r.link ? (
                              <a href={r.link} target="_blank" rel="noopener noreferrer"
                                className="text-blue-500 hover:text-blue-700 text-sm" title={r.link}>
                                &#x2197;
                              </a>
                            ) : (
                              <button
                                onClick={() => {
                                  const url = prompt('Produkt-Link (URL) eingeben:')
                                  if (url) updateList(setZukaufteile)(r.id, 'link', url)
                                }}
                                className="text-slate-300 hover:text-blue-500 text-sm" title="Link hinzufuegen"
                              >
                                +
                              </button>
                            )}
                          </td>
                          <td className="px-1 py-1.5 text-center">
                            {search?.loading && <span className="text-xs text-purple-500 animate-pulse">...</span>}
                          </td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="1" value={r.anzahl} onChange={v => updateList(setZukaufteile)(r.id, 'anzahl', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell value={r.einheit} onChange={v => updateList(setZukaufteile)(r.id, 'einheit', v)} className="w-14" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.preis} onChange={v => updateList(setZukaufteile)(r.id, 'preis', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{s > 0 ? euro(s) : '-'}</td>
                          <td className="px-2 py-1.5"><RemoveBtn onClick={() => removeFromList(setZukaufteile)(r.id)} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <AddRowBtn onClick={() => setZukaufteile(p => [...p, mkRow(nid(), { marke: '', link: '', anzahl: 0, einheit: 'Stk', preis: 0 })])} />
              </div>
            )}
          </div>

          {/* 10. Fremdmaterial vom AG */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="Fremdmaterial (vom AG)" summe={calc.sumFremd} open={openSections.fremdmaterial} onToggle={() => toggle('fremdmaterial')} nr="10" />
            {openSections.fremdmaterial && (
              <div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-800/40">
                      <th className={thCls}>Bezeichnung</th>
                      <th className={`${thCls} w-20 text-right`}>Anzahl</th>
                      <th className={`${thCls} w-24 text-right`}>EUR/Einh.</th>
                      <th className={`${thCls} w-20 text-right`}>Handling %</th>
                      <th className={`${thCls} w-28 text-right`}>Handlingfee</th>
                      <th className={`${thCls} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {fremdmaterial.map(r => {
                      const s = num(r.anzahl) * num(r.preis) * num(r.handlingPct) / 100
                      return (
                        <tr key={r.id} className="hover:bg-slate-800/40 group">
                          <td className="px-3 py-1.5"><InputCell value={r.bezeichnung} onChange={v => updateList(setFremdmaterial)(r.id, 'bezeichnung', v)} placeholder="Material..." /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="1" value={r.anzahl} onChange={v => updateList(setFremdmaterial)(r.id, 'anzahl', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.preis} onChange={v => updateList(setFremdmaterial)(r.id, 'preis', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="1" value={r.handlingPct} onChange={v => updateList(setFremdmaterial)(r.id, 'handlingPct', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{s > 0 ? euro(s) : '-'}</td>
                          <td className="px-2 py-1.5"><RemoveBtn onClick={() => removeFromList(setFremdmaterial)(r.id)} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <AddRowBtn onClick={() => setFremdmaterial(p => [...p, mkRow(nid(), { anzahl: 0, preis: 0, handlingPct: 10 })])} />
              </div>
            )}
          </div>

          {/* 11. Arbeitsstunden */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title={`Arbeitsstunden (${calc.sumStunden.toFixed(1)} h)`} summe={calc.sumLohn} open={openSections.lohn} onToggle={() => toggle('lohn')} nr="11" />
            {openSections.lohn && (
              <div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-800/40">
                      <th className={thCls}>Taetigkeit</th>
                      <th className={`${thCls} w-20 text-right`}>Stunden</th>
                      <th className={`${thCls} w-40`}>Lohnart</th>
                      <th className={`${thCls} w-20 text-right`}>EUR/h</th>
                      <th className={`${thCls} w-28 text-right`}>Summe</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {lohn.map(r => {
                      const lohnSaetze = { 1: num(variablen.lohn1), 2: num(variablen.lohn2), 3: num(variablen.lohn3) }
                      const satz = lohnSaetze[r.lohnart] || lohnSaetze[1]
                      const s = num(r.stunden) * satz
                      return (
                        <tr key={r.id} className="hover:bg-slate-800/40">
                          <td className="px-3 py-1.5"><InputCell value={r.bezeichnung} onChange={v => updateList(setLohn)(r.id, 'bezeichnung', v)} /></td>
                          <td className="px-3 py-1.5"><InputCell type="number" step="0.5" value={r.stunden} onChange={v => updateList(setLohn)(r.id, 'stunden', v)} className="text-right" /></td>
                          <td className="px-3 py-1.5">
                            <select value={r.lohnart} onChange={e => updateList(setLohn)(r.id, 'lohnart', parseInt(e.target.value))}
                              className="border-0 bg-transparent text-sm text-slate-300 outline-none focus:ring-1 focus:ring-amber-500/50 rounded px-1 py-1">
                              <option value={1}>1 - Werkstatt ({euro(num(variablen.lohn1))})</option>
                              <option value={2}>2 - CNC ({euro(num(variablen.lohn2))})</option>
                              <option value={3}>3 - Montage ({euro(num(variablen.lohn3))})</option>
                            </select>
                          </td>
                          <td className="px-3 py-1.5 text-sm text-right text-slate-500">{euro(satz)}</td>
                          <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{s > 0 ? euro(s) : '-'}</td>
                        </tr>
                      )
                    })}
                    <tr className="bg-slate-700/30 font-semibold">
                      <td className="px-3 py-2 text-sm text-slate-200">Summe</td>
                      <td className="px-3 py-2 text-sm text-right text-slate-400">{calc.sumStunden.toFixed(1)} h</td>
                      <td colSpan={2}></td>
                      <td className="px-3 py-2 text-sm text-right text-amber-400">{euro(calc.sumLohn)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* 12. KFZ */}
          <div className="glass-card overflow-hidden">
            <SectionHeader title="KFZ" summe={calc.sumKfz} open={openSections.kfz} onToggle={() => toggle('kfz')} nr="12" />
            {openSections.kfz && (
              <div className="p-4 flex items-center gap-4 flex-wrap">
                <div>
                  <label className="text-xs text-slate-400">km (einfach)</label>
                  <input type="number" step="1" value={kfz.kmEinfach || ''} onChange={e => setKfz(p => ({ ...p, kmEinfach: e.target.value }))}
                    className={`w-24 text-right ${inputCls}`} />
                </div>
                <div>
                  <label className="text-xs text-slate-400">Anzahl Wege</label>
                  <input type="number" step="1" value={kfz.anzahlWege || ''} onChange={e => setKfz(p => ({ ...p, anzahlWege: e.target.value }))}
                    className={`w-20 text-right ${inputCls}`} />
                </div>
                <div>
                  <label className="text-xs text-slate-400">EUR/km</label>
                  <div className="text-sm font-medium text-slate-300 px-2 py-1.5">{num(variablen.kfzKm).toFixed(2)}</div>
                </div>
                <div>
                  <label className="text-xs text-slate-400">Gesamt km</label>
                  <div className="text-sm font-medium text-slate-300 px-2 py-1.5">{(num(kfz.kmEinfach) * num(kfz.anzahlWege)).toFixed(0)}</div>
                </div>
                <div>
                  <label className="text-xs text-slate-400">Summe</label>
                  <div className="text-sm font-bold text-amber-400 px-2 py-1.5">{euro(calc.sumKfz)}</div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right sidebar: Summary + KI */}
        <div className="w-80 flex-shrink-0 space-y-3">
          {/* Summary */}
          <div className="sticky top-4 space-y-3">
            <div className="glass-card overflow-hidden">
              <div className="px-4 py-3 border-b border-amber-500/30" style={{ background: 'linear-gradient(135deg, rgba(180,83,9,0.15), rgba(245,158,11,0.1))' }}>
                <h2 className="font-bold text-amber-400 text-sm">Zusammenfassung</h2>
              </div>
              <div className="p-4 space-y-1 text-sm">
                <SummaryLine label="Material (Roh)" value={calc.materialRoh} />
                <SummaryLine label={`+ Kleinteile (${zuschlaege.kleinteile}%)`} value={calc.kleinteilZuschlag} indent />
                <SummaryLine label={`+ Marge Material (${zuschlaege.margeMaterial}%)`} value={calc.margeMaterial} indent />
                <SummaryLine label="= Verarbeitete Materialien" value={calc.summeVerarbeiteteMat} bold />
                <div className="border-t border-slate-700/30 my-2" />

                <SummaryLine label="Zukaufteile" value={calc.sumZukauf} />
                <SummaryLine label={`+ Marge Zukauf (${zuschlaege.margeZukauf}%)`} value={calc.margeZukauf} indent />
                <SummaryLine label="= Halbfabrikate" value={calc.summeHalbfabrikate} bold />
                <div className="border-t border-slate-700/30 my-2" />

                <SummaryLine label="Fremdmaterial (Handlingfee)" value={calc.sumFremd} />
                <div className="border-t border-slate-700/30 my-2" />

                <SummaryLine label="SUMME MATERIAL GESAMT" value={calc.summeMaterialGesamt} bold highlight />
                <div className="border-t border-slate-600/40 my-2" />

                <SummaryLine label={`Lohn (${calc.sumStunden.toFixed(1)} h)`} value={calc.sumLohn} />
                <SummaryLine label="KFZ" value={calc.sumKfz} />
                <div className="border-t border-slate-600/40 my-2" />

                <SummaryLine label="SELBSTKOSTEN" value={calc.selbstkosten} bold highlight />
                <SummaryLine label={`WUG (${zuschlaege.wug}%)`} value={calc.wug} indent />
                <div className="border-t border-slate-600/40 my-2" />

                <SummaryLine label="GESAMT (netto)" value={calc.gesamt} bold />
                {calc.db1 > 0 && (
                  <div className="flex justify-between text-xs text-green-400">
                    <span className="pl-2">DB I</span>
                    <span>{euro(calc.db1)}</span>
                  </div>
                )}

                {num(zuschlaege.rabatt) > 0 && <SummaryLine label={`Rabatt (${zuschlaege.rabatt}%)`} value={calc.rabattBetrag} indent />}
                {num(zuschlaege.rabatt) > 0 && <SummaryLine label="Gesamt mit Rabatt" value={calc.gesamtMitRabatt} bold />}
                <SummaryLine label={`MWSt (${zuschlaege.mwst}%)`} value={calc.mwst} indent />
                <div className="border-t border-slate-600/40 my-3" />

                <div className="flex justify-between items-center">
                  <span className="font-bold text-white">BRUTTOPREIS</span>
                  <span className="text-xl font-bold text-amber-400">{euro(calc.brutto)}</span>
                </div>
                {calc.gesamt > 0 && (
                  <div className="text-xs text-slate-400 text-right">Netto: {euro(calc.gesamtMitRabatt)}</div>
                )}
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* Formelhinweise */}
      <div className="mt-6 text-xs text-slate-400">
        Material + Kleinteile + Marge = Verarb. Mat. | Zukauf + Marge = Halbfabr. | Mat. Gesamt + Lohn + KFZ = Selbstkosten | + WUG - Rabatt + MWSt = Brutto
      </div>
      </>}
    </div>
  )
}

// --- Shared components ---

function SimpleItemTable({ rows, setter, update, remove, nid }) {
  const thCls = 'px-3 py-2 text-left text-xs text-slate-400 uppercase tracking-wider'
  return (
    <div>
      <table className="w-full">
        <thead>
          <tr className="bg-slate-800/40">
            <th className={thCls}>Bezeichnung</th>
            <th className={`${thCls} w-20 text-right`}>Anzahl</th>
            <th className={`${thCls} w-20`}>Einheit</th>
            <th className={`${thCls} w-24 text-right`}>EUR/Einh.</th>
            <th className={`${thCls} w-28 text-right`}>Summe</th>
            <th className={`${thCls} w-8`}></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/30">
          {rows.map(r => {
            const s = num(r.anzahl) * num(r.preis)
            return (
              <tr key={r.id} className="hover:bg-slate-800/40 group">
                <td className="px-3 py-1.5"><InputCell value={r.bezeichnung} onChange={v => update(r.id, 'bezeichnung', v)} placeholder="Beschreibung..." /></td>
                <td className="px-3 py-1.5"><InputCell type="number" step="1" value={r.anzahl} onChange={v => update(r.id, 'anzahl', v)} className="text-right" /></td>
                <td className="px-3 py-1.5"><InputCell value={r.einheit} onChange={v => update(r.id, 'einheit', v)} className="w-16" /></td>
                <td className="px-3 py-1.5"><InputCell type="number" step="0.01" value={r.preis} onChange={v => update(r.id, 'preis', v)} className="text-right" /></td>
                <td className="px-3 py-1.5 text-sm text-right font-medium text-slate-300">{s > 0 ? euro(s) : '-'}</td>
                <td className="px-2 py-1.5"><RemoveBtn onClick={() => remove(r.id)} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <AddRowBtn onClick={() => setter(p => [...p, mkRow(nid(), { anzahl: 0, einheit: 'Stk', preis: 0 })])} />
    </div>
  )
}

function SummaryLine({ label, value, bold, indent, highlight }) {
  return (
    <div className={`flex justify-between ${indent ? 'pl-2 text-slate-500' : ''} ${bold ? 'font-semibold text-slate-200' : 'text-slate-400'} ${highlight ? 'bg-amber-500/10 -mx-4 px-4 py-1 rounded' : ''}`}>
      <span className="text-xs">{label}</span>
      <span className={`${bold ? 'font-bold text-amber-400' : ''}`}>{euro(value)}</span>
    </div>
  )
}
