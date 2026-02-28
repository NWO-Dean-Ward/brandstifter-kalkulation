import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projekte, health } from '../api'

const STATUS_LABELS = {
  entwurf: { label: 'Entwurf', bg: 'bg-slate-500/20', text: 'text-slate-300', dot: 'bg-slate-400' },
  kalkuliert: { label: 'Kalkuliert', bg: 'bg-blue-500/20', text: 'text-blue-300', dot: 'bg-blue-400' },
  angeboten: { label: 'Angeboten', bg: 'bg-amber-500/20', text: 'text-amber-300', dot: 'bg-amber-400' },
  beauftragt: { label: 'Beauftragt', bg: 'bg-emerald-500/20', text: 'text-emerald-300', dot: 'bg-emerald-400' },
  abgeschlossen: { label: 'Abgeschlossen', bg: 'bg-green-500/20', text: 'text-green-300', dot: 'bg-green-400' },
  verloren: { label: 'Verloren', bg: 'bg-red-500/20', text: 'text-red-300', dot: 'bg-red-400' },
}

function StatusBadge({ status }) {
  const s = STATUS_LABELS[status] || { label: status, bg: 'bg-gray-500/20', text: 'text-gray-300', dot: 'bg-gray-400' }
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
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
  const [filter, setFilter] = useState('alle')
  const [suche, setSuche] = useState('')
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

  const handleCopy = async (e, id) => {
    e.stopPropagation()
    try {
      const kopie = await projekte.kopieren(id)
      setListe(prev => [kopie, ...prev])
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  // Filter & Stats
  const suchFilter = suche.trim().toLowerCase()
  const filtered = liste
    .filter(p => filter === 'alle' || p.status === filter)
    .filter(p => !suchFilter || p.name.toLowerCase().includes(suchFilter) || (p.kunde || '').toLowerCase().includes(suchFilter) || p.id.toLowerCase().includes(suchFilter))
  const offen = liste.filter(p => ['entwurf', 'kalkuliert', 'angeboten'].includes(p.status)).length
  const gesamtwert = liste.reduce((s, p) => s + (p.angebotspreis || 0), 0)
  const beauftragt = liste.filter(p => p.status === 'beauftragt').length

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">Uebersicht aller Projekte und Kalkulationen</p>
        </div>
        <div className="flex items-center gap-3">
          {serverOk !== null && (
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
              serverOk ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
            }`}>
              <span className={`w-2 h-2 rounded-full ${serverOk ? 'bg-emerald-500' : 'bg-red-500'}`} />
              {serverOk ? 'Online' : 'Offline'}
            </div>
          )}
        </div>
      </div>

      {/* Statistik-Karten */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Projekte gesamt" value={liste.length} icon="folder" />
        <StatCard label="Offen" value={offen} icon="clock" accent />
        <StatCard label="Beauftragt" value={beauftragt} icon="check" />
        <StatCard label="Gesamtwert" value={euro(gesamtwert)} icon="euro" />
      </div>

      {/* Status-Filter */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {[
          { key: 'alle', label: 'Alle' },
          ...Object.entries(STATUS_LABELS).map(([key, { label }]) => ({ key, label })),
        ].map(f => (
          <button key={f.key} onClick={() => setFilter(f.key)}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
              filter === f.key
                ? 'bg-amber-600/90 text-white shadow-lg shadow-amber-900/20'
                : 'bg-slate-800/60 text-slate-400 hover:bg-slate-700/60 hover:text-slate-300'
            }`}>
            {f.label}
            {f.key !== 'alle' && (
              <span className="ml-1.5 opacity-60">({liste.filter(p => p.status === f.key).length})</span>
            )}
          </button>
        ))}
      </div>

      {/* Projektliste */}
      <div className="glass-card overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700/50 flex items-center justify-between gap-4">
          <h2 className="font-semibold text-slate-200">Projekte</h2>
          <div className="flex-1 max-w-xs">
            <input
              value={suche}
              onChange={e => setSuche(e.target.value)}
              placeholder="Suche (Name, Kunde, ID)..."
              className="me-input w-full"
            />
          </div>
          <button
            onClick={() => navigate('/ausschreibung')}
            className="btn-primary"
          >
            + Neues Projekt
          </button>
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-500">
            <div className="inline-block w-6 h-6 border-2 border-slate-600 border-t-amber-500 rounded-full animate-spin mb-3" />
            <div>Lade Projekte...</div>
          </div>
        ) : error ? (
          <div className="p-12 text-center text-red-400">{error}</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            {liste.length === 0 ? 'Noch keine Projekte vorhanden.' : 'Keine Projekte mit diesem Filter.'}
          </div>
        ) : (
          <table className="me-table">
            <thead>
              <tr className="text-left">
                <th className="px-6 py-3">Projekt</th>
                <th className="px-6 py-3">Kunde</th>
                <th className="px-6 py-3">Typ</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3 text-right">Angebotspreis</th>
                <th className="px-6 py-3 text-right">Marge</th>
                <th className="px-6 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => (
                <tr
                  key={p.id}
                  onClick={() => navigate(`/projekt/${p.id}`)}
                  className="cursor-pointer group"
                >
                  <td className="px-6 py-3.5">
                    <div className="font-medium text-slate-200 group-hover:text-amber-400 transition-colors">{p.name}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{p.id}</div>
                  </td>
                  <td className="px-6 py-3.5 text-slate-400">{p.kunde || '-'}</td>
                  <td className="px-6 py-3.5 text-sm">
                    {p.projekt_typ === 'oeffentlich' ? (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-500/15 text-blue-400">VOB</span>
                    ) : p.projekt_typ === 'privat' ? (
                      <span className="text-xs text-slate-400">Privat</span>
                    ) : (
                      <span className="text-xs text-slate-500">Std.</span>
                    )}
                  </td>
                  <td className="px-6 py-3.5"><StatusBadge status={p.status} /></td>
                  <td className="px-6 py-3.5 text-right font-medium text-slate-200">
                    {p.angebotspreis ? euro(p.angebotspreis) : '-'}
                  </td>
                  <td className="px-6 py-3.5 text-right text-sm text-slate-400">
                    {p.marge_prozent ? `${p.marge_prozent.toFixed(1)}%` : '-'}
                  </td>
                  <td className="px-6 py-3.5 text-right whitespace-nowrap">
                    <button
                      onClick={(e) => handleCopy(e, p.id)}
                      className="text-slate-500 hover:text-amber-400 transition-colors text-sm mr-3 opacity-0 group-hover:opacity-100"
                      title="Kopieren"
                    >
                      Kop.
                    </button>
                    <button
                      onClick={(e) => handleDelete(e, p.id)}
                      className="text-slate-500 hover:text-red-400 transition-colors text-sm opacity-0 group-hover:opacity-100"
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

function StatCard({ label, value, icon, accent }) {
  return (
    <div className="stat-card p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-slate-400 font-medium uppercase tracking-wide">{label}</span>
        <span className={`text-lg ${accent ? 'text-amber-500' : 'text-slate-500'}`}>
          {icon === 'folder' && '\u{1F4C1}'}
          {icon === 'clock' && '\u{23F3}'}
          {icon === 'check' && '\u2705'}
          {icon === 'euro' && '\u{1F4B6}'}
        </span>
      </div>
      <div className={`text-2xl font-bold ${accent ? 'text-amber-400' : 'text-white'}`}>{value}</div>
    </div>
  )
}
