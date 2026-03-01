import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projekte, health } from '../api'
import StatusBadge from '@/components/StatusBadge'
import { STATUS_LABELS } from '@/components/StatusBadge'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'

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
            <Badge variant="outline" className={
              serverOk
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-red-500/10 text-red-400 border-red-500/30'
            }>
              <span className={`w-2 h-2 rounded-full ${serverOk ? 'bg-emerald-500' : 'bg-red-500'}`} />
              {serverOk ? 'Online' : 'Offline'}
            </Badge>
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
          <Button
            key={f.key}
            onClick={() => setFilter(f.key)}
            variant={filter === f.key ? 'default' : 'secondary'}
            size="sm"
          >
            {f.label}
            {f.key !== 'alle' && (
              <span className="ml-1.5 opacity-60">({liste.filter(p => p.status === f.key).length})</span>
            )}
          </Button>
        ))}
      </div>

      {/* Projektliste */}
      <div className="glass-card overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700/50 flex items-center justify-between gap-4">
          <h2 className="font-semibold text-slate-200">Projekte</h2>
          <div className="flex-1 max-w-xs">
            <Input
              value={suche}
              onChange={e => setSuche(e.target.value)}
              placeholder="Suche (Name, Kunde, ID)..."
            />
          </div>
          <Button onClick={() => navigate('/ausschreibung')}>
            + Neues Projekt
          </Button>
        </div>

        {loading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-10 flex-1" />
                <Skeleton className="h-10 w-24" />
                <Skeleton className="h-10 w-20" />
                <Skeleton className="h-10 w-28" />
                <Skeleton className="h-10 w-24" />
                <Skeleton className="h-10 w-16" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="p-12 text-center text-red-400">{error}</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            {liste.length === 0 ? 'Noch keine Projekte vorhanden.' : 'Keine Projekte mit diesem Filter.'}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="text-left">
                <TableHead className="px-6 py-3">Projekt</TableHead>
                <TableHead className="px-6 py-3">Kunde</TableHead>
                <TableHead className="px-6 py-3">Typ</TableHead>
                <TableHead className="px-6 py-3">Status</TableHead>
                <TableHead className="px-6 py-3 text-right">Angebotspreis</TableHead>
                <TableHead className="px-6 py-3 text-right">Marge</TableHead>
                <TableHead className="px-6 py-3"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(p => (
                <TableRow
                  key={p.id}
                  onClick={() => navigate(`/projekt/${p.id}`)}
                  className="cursor-pointer group"
                >
                  <TableCell className="px-6 py-3.5">
                    <div className="font-medium text-slate-200 group-hover:text-amber-400 transition-colors">{p.name}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{p.id}</div>
                  </TableCell>
                  <TableCell className="px-6 py-3.5 text-slate-400">{p.kunde || '-'}</TableCell>
                  <TableCell className="px-6 py-3.5 text-sm">
                    {p.projekt_typ === 'oeffentlich' ? (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-500/15 text-blue-400">VOB</span>
                    ) : p.projekt_typ === 'privat' ? (
                      <span className="text-xs text-slate-400">Privat</span>
                    ) : (
                      <span className="text-xs text-slate-500">Std.</span>
                    )}
                  </TableCell>
                  <TableCell className="px-6 py-3.5"><StatusBadge status={p.status} /></TableCell>
                  <TableCell className="px-6 py-3.5 text-right font-medium text-slate-200">
                    {p.angebotspreis ? euro(p.angebotspreis) : '-'}
                  </TableCell>
                  <TableCell className="px-6 py-3.5 text-right text-sm text-slate-400">
                    {p.marge_prozent ? `${p.marge_prozent.toFixed(1)}%` : '-'}
                  </TableCell>
                  <TableCell className="px-6 py-3.5 text-right whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleCopy(e, p.id)}
                      className="text-slate-500 hover:text-amber-400 transition-colors text-sm mr-1 opacity-0 group-hover:opacity-100"
                      title="Kopieren"
                    >
                      Kop.
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleDelete(e, p.id)}
                      className="text-slate-500 hover:text-red-400 transition-colors text-sm opacity-0 group-hover:opacity-100"
                      title="Loeschen"
                    >
                      X
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
