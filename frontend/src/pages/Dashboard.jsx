import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projekte, health } from '../api'

const STATUS_LABELS = {
  entwurf: { label: 'Entwurf', color: 'bg-slate-100 text-slate-700' },
  kalkuliert: { label: 'Kalkuliert', color: 'bg-blue-100 text-blue-700' },
  angeboten: { label: 'Angeboten', color: 'bg-orange-100 text-orange-700' },
  beauftragt: { label: 'Beauftragt', color: 'bg-green-100 text-green-700' },
  abgeschlossen: { label: 'Abgeschlossen', color: 'bg-emerald-100 text-emerald-700' },
}

function StatusBadge({ status }) {
  const s = STATUS_LABELS[status] || { label: status, color: 'bg-gray-100 text-gray-700' }
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${s.color}`}>
      {s.label}
    </span>
  )
}

function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}

export default function Dashboard() {
  const [liste, setListe] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [serverOk, setServerOk] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    health()
      .then(() => setServerOk(true))
      .catch(() => setServerOk(false))

    projekte.liste()
      .then(setListe)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = async (e, id) => {
    e.stopPropagation()
    if (!confirm('Projekt wirklich loeschen?')) return
    try {
      await projekte.loeschen(id)
      setListe(prev => prev.filter(p => p.id !== id))
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  // Stats
  const kalkuliert = liste.filter(p => p.status === 'kalkuliert').length
  const gesamtwert = liste.reduce((s, p) => s + (p.angebotspreis || 0), 0)

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-800">Dashboard</h1>
        <div className="flex items-center gap-2">
          {serverOk !== null && (
            <span className={`w-2 h-2 rounded-full ${serverOk ? 'bg-green-500' : 'bg-red-500'}`} />
          )}
          <span className="text-xs text-slate-500">
            {serverOk === true ? 'Server online' : serverOk === false ? 'Server offline' : '...'}
          </span>
        </div>
      </div>

      {/* Statistik-Karten */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Projekte gesamt" value={liste.length} />
        <StatCard label="Kalkuliert" value={kalkuliert} />
        <StatCard label="Gesamtwert" value={euro(gesamtwert)} />
        <StatCard label="Durchschnitt" value={euro(liste.length ? gesamtwert / liste.length : 0)} />
      </div>

      {/* Projektliste */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-semibold text-slate-700">Projekte</h2>
          <button
            onClick={() => navigate('/ausschreibung')}
            className="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            + Neues Projekt
          </button>
        </div>

        {loading ? (
          <div className="p-8 text-center text-slate-400">Lade Projekte...</div>
        ) : error ? (
          <div className="p-8 text-center text-red-500">{error}</div>
        ) : liste.length === 0 ? (
          <div className="p-8 text-center text-slate-400">
            Noch keine Projekte vorhanden. Erstelle ein neues Projekt!
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th className="px-5 py-3">Projekt</th>
                <th className="px-5 py-3">Kunde</th>
                <th className="px-5 py-3">Typ</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Angebotspreis</th>
                <th className="px-5 py-3 text-right">Marge</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {liste.map(p => (
                <tr
                  key={p.id}
                  onClick={() => navigate(`/projekt/${p.id}`)}
                  className="hover:bg-slate-50 cursor-pointer transition-colors"
                >
                  <td className="px-5 py-3">
                    <div className="font-medium text-slate-800">{p.name}</div>
                    <div className="text-xs text-slate-400">{p.id}</div>
                  </td>
                  <td className="px-5 py-3 text-slate-600">{p.kunde || '-'}</td>
                  <td className="px-5 py-3 text-sm text-slate-600">{p.projekt_typ}</td>
                  <td className="px-5 py-3"><StatusBadge status={p.status} /></td>
                  <td className="px-5 py-3 text-right font-medium text-slate-800">
                    {p.angebotspreis ? euro(p.angebotspreis) : '-'}
                  </td>
                  <td className="px-5 py-3 text-right text-sm text-slate-600">
                    {p.marge_prozent ? `${(p.marge_prozent * 100).toFixed(1)}%` : '-'}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={(e) => handleDelete(e, p.id)}
                      className="text-slate-400 hover:text-red-500 transition-colors text-sm"
                      title="Loeschen"
                    >
                      X
                    </button>
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

function StatCard({ label, value }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className="text-xl font-bold text-slate-800">{value}</div>
    </div>
  )
}
