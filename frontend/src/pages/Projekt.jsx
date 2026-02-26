import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { projekte, positionen, kalkulation, exporte, downloadBlob } from '../api'

function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}

export default function Projekt() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [projekt, setProjekt] = useState(null)
  const [posList, setPosList] = useState([])
  const [kalkResult, setKalkResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)
  const [exporting, setExporting] = useState({})
  const [error, setError] = useState(null)

  useEffect(() => {
    loadData()
  }, [id])

  const loadData = async () => {
    setLoading(true)
    try {
      const [p, pos] = await Promise.all([
        projekte.get(id),
        positionen.liste(id),
      ])
      setProjekt(p)
      setPosList(pos)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleKalkulieren = async () => {
    setCalculating(true)
    setError(null)
    try {
      const res = await kalkulation.starten(id)
      setKalkResult(res)
      // Projekt neu laden (Status hat sich geaendert)
      const p = await projekte.get(id)
      setProjekt(p)
      // Positionen neu laden (Preise sind jetzt gesetzt)
      const pos = await positionen.liste(id)
      setPosList(pos)
    } catch (e) {
      setError(e.message)
    } finally {
      setCalculating(false)
    }
  }

  const handleExport = async (typ, filename) => {
    setExporting(prev => ({ ...prev, [typ]: true }))
    try {
      let blob
      switch (typ) {
        case 'angebot-pdf': blob = await exporte.angebotPdf(id); break
        case 'intern-pdf': blob = await exporte.internPdf(id); break
        case 'excel': blob = await exporte.excel(id); break
        case 'gaeb': blob = await exporte.gaeb(id); break
      }
      downloadBlob(blob, filename)
    } catch (e) {
      alert('Export-Fehler: ' + e.message)
    } finally {
      setExporting(prev => ({ ...prev, [typ]: false }))
    }
  }

  const handleDelete = async () => {
    if (!confirm('Projekt unwiderruflich loeschen?')) return
    try {
      await projekte.loeschen(id)
      navigate('/')
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  if (loading) return <div className="text-center py-12 text-slate-400">Lade Projekt...</div>
  if (!projekt) return <div className="text-center py-12 text-red-500">{error || 'Projekt nicht gefunden'}</div>

  const isKalkuliert = projekt.status === 'kalkuliert' || kalkResult

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <button
            onClick={() => navigate('/')}
            className="text-sm text-slate-500 hover:text-slate-700 mb-1"
          >
            &lt; Zurueck zum Dashboard
          </button>
          <h1 className="text-2xl font-bold text-slate-800">{projekt.name}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-sm text-slate-500">{projekt.id}</span>
            <span className="text-sm text-slate-500">|</span>
            <span className="text-sm text-slate-500">{projekt.kunde || 'Kein Kunde'}</span>
            <span className="text-sm text-slate-500">|</span>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              projekt.status === 'kalkuliert' ? 'bg-blue-100 text-blue-700' :
              projekt.status === 'entwurf' ? 'bg-slate-100 text-slate-700' :
              'bg-green-100 text-green-700'
            }`}>
              {projekt.status}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleKalkulieren}
            disabled={calculating || posList.length === 0}
            className="bg-orange-600 hover:bg-orange-700 disabled:bg-slate-300 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            {calculating ? 'Kalkuliere...' : 'Kalkulation starten'}
          </button>
          <button
            onClick={handleDelete}
            className="text-slate-400 hover:text-red-500 px-3 py-2 text-sm transition-colors"
            title="Projekt loeschen"
          >
            X Loeschen
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 mb-4 text-sm">
          {error}
        </div>
      )}

      {/* Kalkulations-Ergebnis */}
      {(kalkResult || projekt.angebotspreis > 0) && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-4">
          <h2 className="font-semibold text-slate-700 mb-4">Kalkulationsergebnis</h2>
          <KalkUebersicht kalk={kalkResult} projekt={projekt} />

          {/* Warnungen */}
          {kalkResult?.warnungen?.length > 0 && (
            <div className="mt-4 space-y-1">
              {kalkResult.warnungen.map((w, i) => (
                <div key={i} className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                  {w}
                </div>
              ))}
            </div>
          )}

          {/* Export-Buttons */}
          <div className="mt-6 pt-4 border-t border-slate-100">
            <h3 className="text-sm font-medium text-slate-600 mb-3">Exportieren</h3>
            <div className="flex gap-2 flex-wrap">
              <ExportButton
                label="Angebots-PDF"
                loading={exporting['angebot-pdf']}
                onClick={() => handleExport('angebot-pdf', `Angebot_${projekt.name}.pdf`)}
              />
              <ExportButton
                label="Interne Kalkulation"
                loading={exporting['intern-pdf']}
                onClick={() => handleExport('intern-pdf', `Kalkulation_${projekt.name}.pdf`)}
              />
              <ExportButton
                label="Excel"
                loading={exporting['excel']}
                onClick={() => handleExport('excel', `Kalkulation_${projekt.name}.xlsx`)}
              />
              <ExportButton
                label="GAEB X83"
                loading={exporting['gaeb']}
                onClick={() => handleExport('gaeb', `Angebot_${projekt.name}.x83`)}
              />
            </div>
          </div>
        </div>
      )}

      {/* Positionsliste */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-700">Positionen ({posList.length})</h2>
        </div>
        {posList.length === 0 ? (
          <div className="p-8 text-center text-slate-400">Keine Positionen vorhanden</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th className="px-5 py-3">Pos</th>
                <th className="px-5 py-3">Beschreibung</th>
                <th className="px-5 py-3 text-right">Menge</th>
                <th className="px-5 py-3">Einheit</th>
                <th className="px-5 py-3">Material</th>
                <th className="px-5 py-3 text-right">EP</th>
                <th className="px-5 py-3 text-right">GP</th>
                <th className="px-5 py-3 text-center">Lack.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {posList.map(p => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-5 py-3 text-sm font-mono text-slate-600">{p.pos_nr}</td>
                  <td className="px-5 py-3 text-sm text-slate-800">{p.kurztext}</td>
                  <td className="px-5 py-3 text-sm text-right text-slate-600">{p.menge}</td>
                  <td className="px-5 py-3 text-sm text-slate-600">{p.einheit}</td>
                  <td className="px-5 py-3 text-sm text-slate-600">{p.material || '-'}</td>
                  <td className="px-5 py-3 text-sm text-right text-slate-700">
                    {p.einheitspreis ? euro(p.einheitspreis) : '-'}
                  </td>
                  <td className="px-5 py-3 text-sm text-right font-medium text-slate-800">
                    {p.gesamtpreis ? euro(p.gesamtpreis) : '-'}
                  </td>
                  <td className="px-5 py-3 text-center">
                    {p.ist_lackierung && (
                      <span className="px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700 font-medium">
                        Lack
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function KalkUebersicht({ kalk, projekt }) {
  // Verwende kalkResult falls vorhanden, sonst Projektdaten
  const data = kalk || {
    herstellkosten: projekt.herstellkosten,
    angebotspreis: projekt.angebotspreis,
    marge_prozent: projekt.marge_prozent,
  }

  const rows = [
    ['Materialkosten', data.materialkosten],
    ['Maschinenkosten', data.maschinenkosten],
    ['Lohnkosten', data.lohnkosten],
    null, // Trennlinie
    ['Herstellkosten', data.herstellkosten, true],
    ['Gemeinkosten (GKZ)', data.gemeinkosten],
    ['Selbstkosten', data.selbstkosten, true],
    ['Gewinn', data.gewinn],
    ['Wagnis (VOB)', data.wagnis],
    ['Montage-Zuschlag', data.montage_zuschlag],
    ['Fremdleistungen', data.fremdleistungskosten],
    ['FL-Zuschlag', data.fremdleistungszuschlag],
    null,
    ['Angebotspreis (netto)', data.angebotspreis, true, true],
  ].filter(row => row === null || row[1] !== undefined)

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
      <div>
        {rows.map((row, i) => {
          if (row === null) return <div key={i} className="border-t border-slate-200 my-2" />
          const [label, value, bold, highlight] = row
          if (value === 0 && !bold) return null
          return (
            <div key={i} className={`flex justify-between py-1 ${bold ? 'font-semibold' : ''} ${highlight ? 'text-orange-700 text-lg' : 'text-slate-700 text-sm'}`}>
              <span>{label}</span>
              <span>{euro(value)}</span>
            </div>
          )
        })}
      </div>
      <div className="flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl font-bold text-orange-600">{euro(data.angebotspreis)}</div>
          <div className="text-sm text-slate-500 mt-1">Angebotspreis (netto)</div>
          {data.marge_prozent > 0 && (
            <div className="text-sm text-green-600 mt-2 font-medium">
              Marge: {data.marge_prozent.toFixed(1)}%
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ExportButton({ label, loading, onClick }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="border border-slate-300 hover:border-orange-400 hover:bg-orange-50 disabled:bg-slate-100 disabled:text-slate-400 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
    >
      {loading ? '...' : label}
    </button>
  )
}
