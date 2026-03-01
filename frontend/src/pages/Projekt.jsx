import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { projekte, positionen, kalkulation, exporte, downloadBlob, werkstuecke, zukaufteile, ueberschreibungen } from '../api'
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Separator } from "@/components/ui/separator"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table"
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select"

function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}

const STATUS_OPTIONS = [
  { value: 'entwurf', label: 'Entwurf', color: 'bg-slate-500/20 text-slate-300' },
  { value: 'kalkuliert', label: 'Kalkuliert', color: 'bg-blue-500/20 text-blue-300' },
  { value: 'angeboten', label: 'Angeboten', color: 'bg-amber-500/20 text-amber-300' },
  { value: 'beauftragt', label: 'Beauftragt', color: 'bg-green-500/20 text-green-300' },
  { value: 'abgeschlossen', label: 'Abgeschlossen', color: 'bg-emerald-500/20 text-emerald-300' },
  { value: 'verloren', label: 'Verloren', color: 'bg-red-500/20 text-red-300' },
]

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
  const [activeTab, setActiveTab] = useState('positionen')
  const [editingMeta, setEditingMeta] = useState(false)
  const [meta, setMeta] = useState({})

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
      const p = await projekte.get(id)
      setProjekt(p)
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

  const handleStatusChange = async (newStatus) => {
    try {
      await projekte.update(id, { status: newStatus })
      setProjekt(prev => ({ ...prev, status: newStatus }))
    } catch (e) {
      alert('Status-Fehler: ' + e.message)
    }
  }

  const handleMetaSave = async () => {
    try {
      await projekte.update(id, meta)
      setProjekt(prev => ({ ...prev, ...meta }))
      setEditingMeta(false)
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  const startEditMeta = () => {
    setMeta({ name: projekt.name, kunde: projekt.kunde || '', beschreibung: projekt.beschreibung || '' })
    setEditingMeta(true)
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
  if (!projekt) return <div className="text-center py-12 text-red-400">{error || 'Projekt nicht gefunden'}</div>

  const isKalkuliert = projekt.status === 'kalkuliert' || kalkResult
  const currentStatusOption = STATUS_OPTIONS.find(s => s.value === projekt.status) || STATUS_OPTIONS[0]

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/')}
            className="text-sm text-slate-400 hover:text-slate-200 mb-1 px-0"
          >
            &lt; Zurueck zum Dashboard
          </Button>
          {editingMeta ? (
            <div className="space-y-2">
              <Input value={meta.name} onChange={e => setMeta({...meta, name: e.target.value})}
                className="text-2xl font-bold text-white bg-slate-800/60 border-slate-600 w-96" />
              <div className="flex gap-2">
                <Input value={meta.kunde} onChange={e => setMeta({...meta, kunde: e.target.value})}
                  placeholder="Kunde" className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm w-48" />
                <Input value={meta.beschreibung} onChange={e => setMeta({...meta, beschreibung: e.target.value})}
                  placeholder="Beschreibung" className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm w-64" />
                <Button onClick={handleMetaSave} size="sm">Speichern</Button>
                <Button variant="ghost" size="sm" onClick={() => setEditingMeta(false)}
                  className="text-slate-400 hover:text-slate-200">Abbrechen</Button>
              </div>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-bold text-white cursor-pointer hover:text-amber-400 transition-colors"
                onClick={startEditMeta} title="Klicken zum Bearbeiten">
                {projekt.name}
              </h1>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-sm text-slate-400">{projekt.id}</span>
                <span className="text-sm text-slate-400">|</span>
                <span className="text-sm text-slate-400 cursor-pointer hover:text-slate-200" onClick={startEditMeta}>
                  {projekt.kunde || 'Kein Kunde'}
                </span>
                <span className="text-sm text-slate-400">|</span>
                {projekt.projekt_typ !== 'standard' && (
                  <>
                    <Badge variant="outline" className={`text-xs font-medium ${
                      projekt.projekt_typ === 'oeffentlich' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' : 'bg-slate-500/20 text-slate-300 border-slate-500/30'
                    }`}>
                      {projekt.projekt_typ === 'oeffentlich' ? 'VOB' : 'Privat'}
                    </Badge>
                    <span className="text-sm text-slate-400">|</span>
                  </>
                )}
                {projekt.deadline && (
                  <>
                    <span className={`text-xs font-medium ${
                      new Date(projekt.deadline) < new Date() ? 'text-red-400' :
                      new Date(projekt.deadline) < new Date(Date.now() + 7 * 86400000) ? 'text-amber-500' :
                      'text-slate-400'
                    }`}>
                      Frist: {new Date(projekt.deadline).toLocaleDateString('de-DE')}
                    </span>
                    <span className="text-sm text-slate-400">|</span>
                  </>
                )}
                <Select value={projekt.status} onValueChange={handleStatusChange}>
                  <SelectTrigger className={`h-auto px-2 py-0.5 rounded-full text-xs font-medium border-0 w-auto gap-1 ${currentStatusOption.color}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {STATUS_OPTIONS.map(s => (
                      <SelectItem key={s.value} value={s.value} className="text-sm text-slate-200 focus:bg-slate-700 focus:text-white">
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            onClick={handleKalkulieren}
            disabled={calculating || posList.length === 0}
            className="bg-amber-600 hover:bg-amber-700 disabled:bg-slate-700 disabled:text-slate-500 text-white px-5"
          >
            {calculating ? 'Kalkuliere...' : 'Kalkulation starten'}
          </Button>
          <Button
            variant="outline"
            onClick={async () => {
              try {
                const kopie = await projekte.kopieren(id)
                navigate(`/projekt/${kopie.id}`)
              } catch (e) { alert('Fehler: ' + e.message) }
            }}
            className="border-slate-600 hover:border-amber-400 text-slate-300"
            title="Projekt duplizieren"
          >
            Kopieren
          </Button>
          <Button
            variant="ghost"
            onClick={handleDelete}
            className="text-slate-400 hover:text-red-400"
            title="Projekt loeschen"
          >
            X Loeschen
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4 bg-red-500/10 border-red-500/30 text-red-400">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Kalkulations-Ergebnis */}
      {(kalkResult || projekt.angebotspreis > 0) && (
        <div className="glass-card p-6 mb-4">
          <h2 className="font-semibold text-slate-200 mb-4">Kalkulationsergebnis</h2>
          <KalkUebersicht kalk={kalkResult} projekt={projekt} />

          {kalkResult?.warnungen?.length > 0 && (
            <div className="mt-4 space-y-1">
              {kalkResult.warnungen.map((w, i) => (
                <Alert key={i} className="bg-amber-500/10 border-amber-500/30 text-amber-300 py-2">
                  <AlertDescription className="text-sm">{w}</AlertDescription>
                </Alert>
              ))}
            </div>
          )}

          <div className="mt-6 pt-4 border-t border-slate-700/30">
            <h3 className="text-sm font-medium text-slate-300 mb-3">Exportieren</h3>
            <div className="flex gap-2 flex-wrap">
              <ExportButton label="Angebots-PDF" loading={exporting['angebot-pdf']}
                onClick={() => handleExport('angebot-pdf', `Angebot_${projekt.name}.pdf`)} />
              <ExportButton label="Interne Kalkulation" loading={exporting['intern-pdf']}
                onClick={() => handleExport('intern-pdf', `Kalkulation_${projekt.name}.pdf`)} />
              <ExportButton label="Excel" loading={exporting['excel']}
                onClick={() => handleExport('excel', `Kalkulation_${projekt.name}.xlsx`)} />
              <ExportButton label="GAEB X83" loading={exporting['gaeb']}
                onClick={() => handleExport('gaeb', `Angebot_${projekt.name}.x83`)} />
            </div>
          </div>
        </div>
      )}

      {/* Tab-Navigation */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="border-b border-slate-700/50 bg-transparent rounded-none h-auto p-0 w-full justify-start">
          <TabsTrigger
            value="positionen"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3 text-sm font-medium"
          >
            Positionen
            <span className="ml-1.5 text-xs bg-slate-800/60 text-slate-300 rounded-full px-2 py-0.5">
              {posList.length}
            </span>
          </TabsTrigger>
          <TabsTrigger
            value="werkstuecke"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3 text-sm font-medium"
          >
            Werkstuecke
          </TabsTrigger>
          <TabsTrigger
            value="zukaufteile"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3 text-sm font-medium"
          >
            Zukaufteile
          </TabsTrigger>
          <TabsTrigger
            value="nachkalkulation"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3 text-sm font-medium"
          >
            Nachkalkulation
          </TabsTrigger>
        </TabsList>

        {/* Tab-Inhalt */}
        <TabsContent value="positionen" className="mt-4">
          <PositionenTab posList={posList} projektId={id} onReload={loadData} />
        </TabsContent>
        <TabsContent value="werkstuecke" className="mt-4">
          <WerkstueckeTab projektId={id} posList={posList} />
        </TabsContent>
        <TabsContent value="zukaufteile" className="mt-4">
          <ZukaufteileTab projektId={id} posList={posList} />
        </TabsContent>
        <TabsContent value="nachkalkulation" className="mt-4">
          <NachkalkulationTab projektId={id} posList={posList} onReload={loadData} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// === POSITIONEN TAB ===
function PositionenTab({ posList, projektId, onReload }) {
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [editData, setEditData] = useState({})
  const [expandedId, setExpandedId] = useState(null)
  const [form, setForm] = useState({
    pos_nr: '', kurztext: '', menge: 1, einheit: 'STK', material: '',
  })

  const handleAdd = async (e) => {
    e.preventDefault()
    try {
      await positionen.erstellen(projektId, form)
      setShowForm(false)
      setForm({ pos_nr: '', kurztext: '', menge: 1, einheit: 'STK', material: '' })
      onReload()
    } catch (err) {
      alert('Fehler: ' + err.message)
    }
  }

  const handleDelete = async (posId) => {
    if (!confirm('Position loeschen?')) return
    try {
      await positionen.loeschen(projektId, posId)
      onReload()
    } catch (err) {
      alert('Fehler: ' + err.message)
    }
  }

  const startEdit = (p) => {
    setEditId(p.id)
    setEditData({ kurztext: p.kurztext || '', menge: p.menge, einheit: p.einheit, material: p.material || '' })
  }

  const cancelEdit = () => { setEditId(null); setEditData({}) }

  const saveEdit = async (posId) => {
    try {
      await positionen.update(projektId, posId, editData)
      setEditId(null)
      onReload()
    } catch (err) {
      alert('Fehler: ' + err.message)
    }
  }

  const handleKeyDown = (e, posId) => {
    if (e.key === 'Enter') saveEdit(posId)
    if (e.key === 'Escape') cancelEdit()
  }

  // Summen
  const summeGP = posList.reduce((s, p) => s + (p.gesamtpreis || 0), 0)

  return (
    <div className="glass-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/30 flex justify-between items-center">
        <h2 className="font-semibold text-slate-200">Positionen ({posList.length})</h2>
        <Button onClick={() => setShowForm(!showForm)} size="sm"
          className="bg-amber-600 hover:bg-amber-700 text-white">
          {showForm ? 'Abbrechen' : '+ Position'}
        </Button>
      </div>

      {showForm && (
        <form onSubmit={handleAdd} className="p-5 bg-slate-800/40 border-b border-slate-700/50">
          <div className="grid grid-cols-5 gap-3">
            <div>
              <Label className="text-xs text-slate-400">Pos-Nr. *</Label>
              <Input type="text" required value={form.pos_nr}
                onChange={e => setForm({...form, pos_nr: e.target.value})}
                placeholder="01.01"
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-slate-400">Kurztext</Label>
              <Input type="text" value={form.kurztext}
                onChange={e => setForm({...form, kurztext: e.target.value})}
                placeholder="Beschreibung..."
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Menge</Label>
              <Input type="number" step="0.01" min="0" value={form.menge}
                onChange={e => setForm({...form, menge: parseFloat(e.target.value) || 0})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Einheit</Label>
              <select value={form.einheit} onChange={e => setForm({...form, einheit: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                <option>STK</option><option>m</option><option>m2</option>
                <option>lfm</option><option>psch</option><option>kg</option>
              </select>
            </div>
          </div>
          <div className="mt-2">
            <Label className="text-xs text-slate-400">Material</Label>
            <Input type="text" value={form.material}
              onChange={e => setForm({...form, material: e.target.value})}
              placeholder="Spanplatte, MDF..."
              className="w-64 bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
          </div>
          <Button type="submit"
            className="mt-3 bg-amber-600 hover:bg-amber-700 text-white">
            Speichern
          </Button>
        </form>
      )}

      {posList.length === 0 && !showForm ? (
        <div className="p-8 text-center text-slate-400">Keine Positionen vorhanden</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="text-left text-xs text-slate-400 uppercase tracking-wider border-slate-700/30 hover:bg-transparent">
              <TableHead className="px-5 py-3 text-slate-400">Pos</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Beschreibung</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">Menge</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Einheit</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Material</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">EP</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">GP</TableHead>
              <TableHead className="px-5 py-3 text-center text-slate-400">Lack.</TableHead>
              <TableHead className="px-5 py-3"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {posList.map(p => (
              editId === p.id ? (
                <TableRow key={p.id} className="bg-amber-500/10 border-slate-700/30">
                  <TableCell className="px-5 py-2 text-sm font-mono text-slate-300">{p.pos_nr}</TableCell>
                  <TableCell className="px-5 py-2">
                    <Input value={editData.kurztext} onChange={e => setEditData({...editData, kurztext: e.target.value})}
                      onKeyDown={e => handleKeyDown(e, p.id)}
                      className="bg-slate-800/60 text-slate-200 border-amber-500/50 text-sm" autoFocus />
                  </TableCell>
                  <TableCell className="px-5 py-2">
                    <Input type="number" step="0.01" value={editData.menge}
                      onChange={e => setEditData({...editData, menge: parseFloat(e.target.value) || 0})}
                      onKeyDown={e => handleKeyDown(e, p.id)}
                      className="w-20 bg-slate-800/60 text-slate-200 border-amber-500/50 text-sm text-right" />
                  </TableCell>
                  <TableCell className="px-5 py-2">
                    <select value={editData.einheit} onChange={e => setEditData({...editData, einheit: e.target.value})}
                      className="bg-slate-800/60 text-slate-200 border border-amber-500/50 rounded px-2 py-1 text-sm outline-none">
                      <option>STK</option><option>m</option><option>m2</option>
                      <option>lfm</option><option>psch</option><option>kg</option>
                    </select>
                  </TableCell>
                  <TableCell className="px-5 py-2">
                    <Input value={editData.material} onChange={e => setEditData({...editData, material: e.target.value})}
                      onKeyDown={e => handleKeyDown(e, p.id)}
                      className="bg-slate-800/60 text-slate-200 border-amber-500/50 text-sm" />
                  </TableCell>
                  <TableCell className="px-5 py-2 text-sm text-right text-slate-400">{p.einheitspreis ? euro(p.einheitspreis) : '-'}</TableCell>
                  <TableCell className="px-5 py-2 text-sm text-right text-slate-400">{p.gesamtpreis ? euro(p.gesamtpreis) : '-'}</TableCell>
                  <TableCell className="px-5 py-2"></TableCell>
                  <TableCell className="px-5 py-2 text-right">
                    <Button variant="ghost" size="sm" onClick={() => saveEdit(p.id)} className="text-xs text-green-400 hover:text-green-300 mr-1 px-2 h-auto py-1">OK</Button>
                    <Button variant="ghost" size="sm" onClick={cancelEdit} className="text-xs text-slate-400 hover:text-slate-300 px-2 h-auto py-1">Abb.</Button>
                  </TableCell>
                </TableRow>
              ) : (
                <React.Fragment key={p.id}>
                <TableRow className="hover:bg-slate-700/30 cursor-pointer border-slate-700/30" onDoubleClick={() => startEdit(p)}>
                  <TableCell className="px-5 py-3 text-sm font-mono text-slate-300">{p.pos_nr}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-white">{p.kurztext}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-right text-slate-300">{p.menge}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-300">{p.einheit}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-300">{p.material || '-'}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-right text-slate-200">
                    {p.einheitspreis ? euro(p.einheitspreis) : '-'}
                  </TableCell>
                  <TableCell className="px-5 py-3 text-sm text-right font-medium text-white cursor-pointer hover:text-amber-400"
                    onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                    title="Klicken fuer Kostendetails">
                    {p.gesamtpreis ? euro(p.gesamtpreis) : '-'}
                  </TableCell>
                  <TableCell className="px-5 py-3 text-center">
                    {p.ist_lackierung && (
                      <Badge variant="outline" className="bg-purple-500/20 text-purple-300 border-purple-500/30 text-xs">
                        Lack
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="px-5 py-3 text-right">
                    <Button variant="ghost" size="sm" onClick={() => startEdit(p)} className="text-xs text-slate-400 hover:text-amber-400 mr-1 px-2 h-auto py-1" title="Bearbeiten">Ed</Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(p.id)}
                      className="text-xs text-slate-400 hover:text-red-400 px-2 h-auto py-1" title="Loeschen">X</Button>
                  </TableCell>
                </TableRow>
                {expandedId === p.id && p.gesamtpreis > 0 && (
                  <TableRow className="bg-slate-800/40 border-slate-700/30">
                    <TableCell></TableCell>
                    <TableCell colSpan={8} className="px-5 py-2">
                      <div className="flex gap-6 text-xs text-slate-300">
                        <span>Material: <b className="text-slate-200">{euro(p.materialkosten || 0)}</b></span>
                        <span>Maschinen: <b className="text-slate-200">{euro(p.maschinenkosten || 0)}</b></span>
                        <span>Lohn: <b className="text-slate-200">{euro(p.lohnkosten || 0)}</b></span>
                        {(p.fremdleistungskosten || 0) > 0 && (
                          <span>Fremdleistung: <b className="text-purple-300">{euro(p.fremdleistungskosten)}</b></span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )}
                </React.Fragment>
              )
            ))}
          </TableBody>
        </Table>
      )}

      {posList.length > 0 && (
        <div className="px-5 py-3 bg-slate-800/40 border-t border-slate-700/50 flex justify-between text-sm">
          <span className="text-slate-400 text-xs">Doppelklick auf eine Zeile zum Bearbeiten</span>
          <span className="font-medium text-slate-200">Summe GP: {euro(summeGP)}</span>
        </div>
      )}
    </div>
  )
}

// === WERKSTUECKE TAB ===
function WerkstueckeTab({ projektId, posList = [] }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    bezeichnung: '', anzahl: 1, position_id: '',
    laenge_mm: 0, breite_mm: 0, tiefe_mm: 0, staerke_mm: 0,
    material: '', oberflaeche: '', fertigung: 'cnc-nesting',
    hop_datei: '', notizen: '',
  })

  useEffect(() => { loadItems() }, [projektId])

  const loadItems = async () => {
    setLoading(true)
    try {
      const data = await werkstuecke.liste(projektId)
      setItems(data)
    } catch (e) {
      console.error('Werkstuecke laden:', e)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const payload = { ...form }
      if (payload.position_id) payload.position_id = parseInt(payload.position_id)
      else delete payload.position_id
      await werkstuecke.erstellen(projektId, payload)
      setShowForm(false)
      setForm({ bezeichnung: '', anzahl: 1, position_id: '', laenge_mm: 0, breite_mm: 0, tiefe_mm: 0, staerke_mm: 0, material: '', oberflaeche: '', fertigung: 'cnc-nesting', hop_datei: '', notizen: '' })
      loadItems()
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  const handleDelete = async (wsId) => {
    if (!confirm('Werkstueck loeschen?')) return
    try {
      await werkstuecke.loeschen(projektId, wsId)
      loadItems()
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  const materialOptions = ['Spanplatte', 'MDF', 'Multiplex', 'Massivholz', 'Mineralwerkstoff', 'Sonstige']
  const oberflaecheOptions = ['Melamin', 'Folie', 'Echtholzfurnier', 'Mineralwerkstoff', 'Lackiert-extern']
  const fertigungOptions = [
    { value: 'cnc-nesting', label: 'CNC-Nesting' },
    { value: 'handfertigung', label: 'Handfertigung' },
    { value: 'zukauf', label: 'Zukauf' },
  ]

  if (loading) return <div className="text-center py-8 text-slate-400">Lade...</div>

  return (
    <div className="glass-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/30 flex justify-between items-center">
        <h2 className="font-semibold text-slate-200">Werkstuecke ({items.length})</h2>
        <Button onClick={() => setShowForm(!showForm)} size="sm"
          className="bg-amber-600 hover:bg-amber-700 text-white">
          {showForm ? 'Abbrechen' : '+ Neu'}
        </Button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="p-5 bg-slate-800/40 border-b border-slate-700/50">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="col-span-2">
              <Label className="text-xs text-slate-400">Bezeichnung *</Label>
              <Input type="text" required value={form.bezeichnung}
                onChange={e => setForm({...form, bezeichnung: e.target.value})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Position</Label>
              <select value={form.position_id} onChange={e => setForm({...form, position_id: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                <option value="">-- Alle --</option>
                {posList.map(p => <option key={p.id} value={p.id}>Pos {p.pos_nr}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs text-slate-400">Anzahl</Label>
              <Input type="number" min="1" value={form.anzahl}
                onChange={e => setForm({...form, anzahl: parseInt(e.target.value) || 1})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Staerke (mm)</Label>
              <Input type="number" step="0.1" value={form.staerke_mm}
                onChange={e => setForm({...form, staerke_mm: parseFloat(e.target.value) || 0})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Laenge (mm)</Label>
              <Input type="number" step="0.1" value={form.laenge_mm}
                onChange={e => setForm({...form, laenge_mm: parseFloat(e.target.value) || 0})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Breite (mm)</Label>
              <Input type="number" step="0.1" value={form.breite_mm}
                onChange={e => setForm({...form, breite_mm: parseFloat(e.target.value) || 0})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Tiefe (mm)</Label>
              <Input type="number" step="0.1" value={form.tiefe_mm}
                onChange={e => setForm({...form, tiefe_mm: parseFloat(e.target.value) || 0})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Material</Label>
              <select value={form.material} onChange={e => setForm({...form, material: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                <option value="">-- Waehlen --</option>
                {materialOptions.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs text-slate-400">Oberflaeche</Label>
              <select value={form.oberflaeche} onChange={e => setForm({...form, oberflaeche: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                <option value="">-- Waehlen --</option>
                {oberflaecheOptions.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs text-slate-400">Fertigung</Label>
              <select value={form.fertigung} onChange={e => setForm({...form, fertigung: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                {fertigungOptions.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-slate-400">Notizen</Label>
              <Input type="text" value={form.notizen}
                onChange={e => setForm({...form, notizen: e.target.value})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
          </div>
          {form.oberflaeche === 'Lackiert-extern' && (
            <Alert className="mt-2 bg-purple-500/10 border-purple-500/30 text-purple-300 py-1.5">
              <AlertDescription className="text-xs">
                Automatisch als Fremdleistung markiert (externe Lackierung)
              </AlertDescription>
            </Alert>
          )}
          <Button type="submit"
            className="mt-3 bg-amber-600 hover:bg-amber-700 text-white">
            Speichern
          </Button>
        </form>
      )}

      {items.length === 0 && !showForm ? (
        <div className="p-8 text-center text-slate-400">Keine Werkstuecke vorhanden</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="text-left text-xs text-slate-400 uppercase tracking-wider border-slate-700/30 hover:bg-transparent">
              <TableHead className="px-5 py-3 text-slate-400">Bezeichnung</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">Anz.</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">L x B x T</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Material</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Oberfl.</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Fertigung</TableHead>
              <TableHead className="px-5 py-3 text-center text-slate-400">FL</TableHead>
              <TableHead className="px-5 py-3"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map(ws => (
              <TableRow key={ws.id} className="hover:bg-slate-700/30 border-slate-700/30">
                <TableCell className="px-5 py-3 text-sm text-white">{ws.bezeichnung}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-right text-slate-300">{ws.anzahl}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-right text-slate-300 font-mono">
                  {ws.laenge_mm} x {ws.breite_mm} x {ws.tiefe_mm}
                </TableCell>
                <TableCell className="px-5 py-3 text-sm text-slate-300">{ws.material || '-'}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-slate-300">{ws.oberflaeche || '-'}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-slate-300">{ws.fertigung}</TableCell>
                <TableCell className="px-5 py-3 text-center">
                  {ws.ist_fremdleistung && (
                    <Badge variant="outline" className="bg-purple-500/20 text-purple-300 border-purple-500/30 text-xs">FL</Badge>
                  )}
                </TableCell>
                <TableCell className="px-5 py-3 text-right">
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(ws.id)}
                    className="text-xs text-slate-400 hover:text-red-400 px-2 h-auto py-1">X</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

// === ZUKAUFTEILE TAB ===
function ZukaufteileTab({ projektId, posList = [] }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    bezeichnung: '', hersteller: '', produkt: '', artikel_nr: '',
    produkt_link: '', einkaufspreis: 0, menge: 1, aufschlag_prozent: 15.0,
    status: 'ausstehend', quelle: 'manuell', position_id: '',
  })

  useEffect(() => { loadItems() }, [projektId])

  const loadItems = async () => {
    setLoading(true)
    try {
      const data = await zukaufteile.liste(projektId)
      setItems(data)
    } catch (e) {
      console.error('Zukaufteile laden:', e)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const payload = { ...form }
      if (payload.position_id) payload.position_id = parseInt(payload.position_id)
      else delete payload.position_id
      await zukaufteile.erstellen(projektId, payload)
      setShowForm(false)
      setForm({ bezeichnung: '', hersteller: '', produkt: '', artikel_nr: '', produkt_link: '', einkaufspreis: 0, menge: 1, aufschlag_prozent: 15.0, status: 'ausstehend', quelle: 'manuell', position_id: '' })
      loadItems()
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  const handleDelete = async (ztId) => {
    if (!confirm('Zukaufteil loeschen?')) return
    try {
      await zukaufteile.loeschen(projektId, ztId)
      loadItems()
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  const statusColors = {
    ausstehend: 'bg-slate-500/20 text-slate-300',
    angefragt: 'bg-yellow-500/20 text-yellow-300',
    bestellt: 'bg-blue-500/20 text-blue-300',
    geliefert: 'bg-green-500/20 text-green-300',
    recherchiert: 'bg-purple-500/20 text-purple-300',
  }

  const verkaufspreis = form.einkaufspreis * form.menge * (1 + form.aufschlag_prozent / 100)

  if (loading) return <div className="text-center py-8 text-slate-400">Lade...</div>

  return (
    <div className="glass-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/30 flex justify-between items-center">
        <h2 className="font-semibold text-slate-200">Zukaufteile ({items.length})</h2>
        <Button onClick={() => setShowForm(!showForm)} size="sm"
          className="bg-amber-600 hover:bg-amber-700 text-white">
          {showForm ? 'Abbrechen' : '+ Neu'}
        </Button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="p-5 bg-slate-800/40 border-b border-slate-700/50">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <Label className="text-xs text-slate-400">Position</Label>
              <select value={form.position_id} onChange={e => setForm({...form, position_id: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                <option value="">-- Alle --</option>
                {posList.map(p => <option key={p.id} value={p.id}>Pos {p.pos_nr}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs text-slate-400">Bezeichnung *</Label>
              <Input type="text" required value={form.bezeichnung}
                onChange={e => setForm({...form, bezeichnung: e.target.value})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Hersteller</Label>
              <Input type="text" value={form.hersteller}
                onChange={e => setForm({...form, hersteller: e.target.value})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Artikel-Nr.</Label>
              <Input type="text" value={form.artikel_nr}
                onChange={e => setForm({...form, artikel_nr: e.target.value})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-slate-400">Produkt</Label>
              <Input type="text" value={form.produkt}
                onChange={e => setForm({...form, produkt: e.target.value})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-slate-400">Produkt-Link</Label>
              <Input type="url" value={form.produkt_link}
                onChange={e => setForm({...form, produkt_link: e.target.value})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Einkaufspreis (netto)</Label>
              <Input type="number" step="0.01" min="0" value={form.einkaufspreis}
                onChange={e => setForm({...form, einkaufspreis: parseFloat(e.target.value) || 0})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Menge</Label>
              <Input type="number" step="0.01" min="0.01" value={form.menge}
                onChange={e => setForm({...form, menge: parseFloat(e.target.value) || 1})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">Aufschlag %</Label>
              <Input type="number" step="0.1" value={form.aufschlag_prozent}
                onChange={e => setForm({...form, aufschlag_prozent: parseFloat(e.target.value) || 0})}
                className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-400">= Verkaufspreis</Label>
              <div className="border border-slate-700/50 bg-slate-800/60 rounded px-3 py-1.5 text-sm font-medium text-green-400">
                {euro(verkaufspreis)}
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-400">Status</Label>
              <select value={form.status} onChange={e => setForm({...form, status: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                <option value="ausstehend">Ausstehend</option>
                <option value="angefragt">Angefragt</option>
                <option value="bestellt">Bestellt</option>
                <option value="geliefert">Geliefert</option>
              </select>
            </div>
            <div>
              <Label className="text-xs text-slate-400">Quelle</Label>
              <select value={form.quelle} onChange={e => setForm({...form, quelle: e.target.value})}
                className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                <option value="manuell">Manuell</option>
                <option value="haefele">Haefele</option>
                <option value="blum">Blum</option>
                <option value="egger">Egger</option>
                <option value="amazon">Amazon</option>
              </select>
            </div>
          </div>
          <Button type="submit"
            className="mt-3 bg-amber-600 hover:bg-amber-700 text-white">
            Speichern
          </Button>
        </form>
      )}

      {items.length === 0 && !showForm ? (
        <div className="p-8 text-center text-slate-400">Keine Zukaufteile vorhanden</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="text-left text-xs text-slate-400 uppercase tracking-wider border-slate-700/30 hover:bg-transparent">
              <TableHead className="px-5 py-3 text-slate-400">Bezeichnung</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Hersteller</TableHead>
              <TableHead className="px-5 py-3 text-slate-400">Art.-Nr.</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">EK</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">Menge</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">Aufschl.</TableHead>
              <TableHead className="px-5 py-3 text-right text-slate-400">VK</TableHead>
              <TableHead className="px-5 py-3 text-center text-slate-400">Status</TableHead>
              <TableHead className="px-5 py-3"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map(zt => (
              <TableRow key={zt.id} className="hover:bg-slate-700/30 border-slate-700/30">
                <TableCell className="px-5 py-3 text-sm text-white">
                  {zt.produkt_link ? (
                    <a href={zt.produkt_link} target="_blank" rel="noopener" className="text-blue-400 hover:underline">{zt.bezeichnung}</a>
                  ) : zt.bezeichnung}
                </TableCell>
                <TableCell className="px-5 py-3 text-sm text-slate-300">{zt.hersteller || '-'}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-slate-300 font-mono">{zt.artikel_nr || '-'}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-right text-slate-300">{euro(zt.einkaufspreis)}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-right text-slate-300">{zt.menge}</TableCell>
                <TableCell className="px-5 py-3 text-sm text-right text-slate-300">{zt.aufschlag_prozent}%</TableCell>
                <TableCell className="px-5 py-3 text-sm text-right font-medium text-green-400">{euro(zt.verkaufspreis)}</TableCell>
                <TableCell className="px-5 py-3 text-center">
                  <Badge variant="outline" className={`text-xs font-medium ${statusColors[zt.status] || 'bg-slate-500/20 text-slate-300'} border-transparent`}>
                    {zt.status}
                  </Badge>
                </TableCell>
                <TableCell className="px-5 py-3 text-right">
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(zt.id)}
                    className="text-xs text-slate-400 hover:text-red-400 px-2 h-auto py-1">X</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {items.length > 0 && (
        <div className="px-5 py-3 bg-slate-800/40 border-t border-slate-700/50 flex justify-between text-sm">
          <span className="text-slate-400">Summe EK: {euro(items.reduce((s, z) => s + z.einkaufspreis * z.menge, 0))}</span>
          <span className="font-medium text-green-400">Summe VK: {euro(items.reduce((s, z) => s + z.verkaufspreis, 0))}</span>
        </div>
      )}
    </div>
  )
}

// === NACHKALKULATION TAB (Manuelle Ueberschreibungen) ===
function NachkalkulationTab({ projektId, posList, onReload }) {
  const [overrides, setOverrides] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    position_id: '', feld: 'einheitspreis', neuer_wert: 0, begruendung: '',
  })

  useEffect(() => { loadOverrides() }, [projektId])

  const loadOverrides = async () => {
    setLoading(true)
    try {
      const data = await ueberschreibungen.liste(projektId)
      setOverrides(data)
    } catch (e) {
      console.error('Ueberschreibungen laden:', e)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.begruendung.trim()) {
      alert('Begruendung ist Pflicht!')
      return
    }
    try {
      await ueberschreibungen.erstellen(projektId, {
        ...form,
        position_id: parseInt(form.position_id),
        neuer_wert: parseFloat(form.neuer_wert),
      })
      setShowForm(false)
      setForm({ position_id: '', feld: 'einheitspreis', neuer_wert: 0, begruendung: '' })
      loadOverrides()
      if (onReload) onReload()
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  const feldLabels = {
    einheitspreis: 'Einheitspreis',
    materialkosten: 'Materialkosten',
    maschinenkosten: 'Maschinenkosten',
    lohnkosten: 'Lohnkosten',
    gesamtpreis: 'Gesamtpreis',
  }

  if (loading) return <div className="text-center py-8 text-slate-400">Lade...</div>

  return (
    <div className="space-y-4">
      {/* Info-Box */}
      <Alert className="bg-amber-500/10 border-amber-500/30 text-amber-300">
        <AlertDescription className="text-sm">
          Manuelle Ueberschreibungen aendern Kalkulationswerte einzelner Positionen.
          Jede Aenderung wird mit Begruendung protokolliert (Audit-Trail).
        </AlertDescription>
      </Alert>

      <div className="glass-card overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700/30 flex justify-between items-center">
          <h2 className="font-semibold text-slate-200">Ueberschreibungen ({overrides.length})</h2>
          <Button onClick={() => setShowForm(!showForm)} size="sm"
            className="bg-amber-600 hover:bg-amber-700 text-white">
            {showForm ? 'Abbrechen' : '+ Wert aendern'}
          </Button>
        </div>

        {showForm && (
          <form onSubmit={handleSubmit} className="p-5 bg-slate-800/40 border-b border-slate-700/50">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <Label className="text-xs text-slate-400">Position *</Label>
                <select required value={form.position_id}
                  onChange={e => setForm({...form, position_id: e.target.value})}
                  className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                  <option value="">-- Waehlen --</option>
                  {posList.map(p => (
                    <option key={p.id} value={p.id}>
                      Pos {p.pos_nr}: {p.kurztext?.substring(0, 30)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs text-slate-400">Feld *</Label>
                <select value={form.feld} onChange={e => setForm({...form, feld: e.target.value})}
                  className="w-full bg-slate-800/60 text-slate-200 border border-slate-600 rounded px-3 py-1.5 text-sm">
                  {Object.entries(feldLabels).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs text-slate-400">Neuer Wert *</Label>
                <Input type="number" step="0.01" required value={form.neuer_wert}
                  onChange={e => setForm({...form, neuer_wert: e.target.value})}
                  className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
              </div>
              <div>
                <Label className="text-xs text-slate-400">Begruendung * (Pflicht!)</Label>
                <Input type="text" required value={form.begruendung}
                  placeholder="z.B. Kundenrabatt, Erfahrungswert..."
                  onChange={e => setForm({...form, begruendung: e.target.value})}
                  className="bg-slate-800/60 text-slate-200 border-slate-600 text-sm" />
              </div>
            </div>
            <Button type="submit"
              className="mt-3 bg-amber-600 hover:bg-amber-700 text-white">
              Ueberschreiben
            </Button>
          </form>
        )}

        {overrides.length === 0 && !showForm ? (
          <div className="p-8 text-center text-slate-400">Keine manuellen Ueberschreibungen</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="text-left text-xs text-slate-400 uppercase tracking-wider border-slate-700/30 hover:bg-transparent">
                <TableHead className="px-5 py-3 text-slate-400">Position</TableHead>
                <TableHead className="px-5 py-3 text-slate-400">Feld</TableHead>
                <TableHead className="px-5 py-3 text-right text-slate-400">Alt</TableHead>
                <TableHead className="px-5 py-3 text-right text-slate-400">Neu</TableHead>
                <TableHead className="px-5 py-3 text-slate-400">Begruendung</TableHead>
                <TableHead className="px-5 py-3 text-slate-400">Datum</TableHead>
                <TableHead className="px-5 py-3 text-slate-400">Von</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {overrides.map(ov => (
                <TableRow key={ov.id} className="hover:bg-slate-700/30 border-slate-700/30">
                  <TableCell className="px-5 py-3 text-sm font-mono text-slate-300">Pos #{ov.position_id}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-200">{feldLabels[ov.feld] || ov.feld}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-right text-red-400 line-through">{euro(ov.alter_wert)}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-right font-medium text-green-400">{euro(ov.neuer_wert)}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-300 italic">{ov.begruendung}</TableCell>
                  <TableCell className="px-5 py-3 text-xs text-slate-400">{ov.geaendert_am?.substring(0, 16)}</TableCell>
                  <TableCell className="px-5 py-3 text-xs text-slate-400">{ov.geaendert_von}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}

function KalkUebersicht({ kalk, projekt }) {
  const data = kalk || {
    herstellkosten: projekt.herstellkosten,
    angebotspreis: projekt.angebotspreis,
    marge_prozent: projekt.marge_prozent,
  }

  const rows = [
    ['Materialkosten', data.materialkosten],
    ['Maschinenkosten', data.maschinenkosten],
    ['Lohnkosten', data.lohnkosten],
    null,
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
          if (row === null) return <Separator key={i} className="my-2 bg-slate-700/50" />
          const [label, value, bold, highlight] = row
          if (value === 0 && !bold) return null
          return (
            <div key={i} className={`flex justify-between py-1 ${bold ? 'font-semibold' : ''} ${highlight ? 'text-amber-400 text-lg' : 'text-slate-200 text-sm'}`}>
              <span>{label}</span>
              <span>{euro(value)}</span>
            </div>
          )
        })}
      </div>
      <div className="flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl font-bold text-amber-500">{euro(data.angebotspreis)}</div>
          <div className="text-sm text-slate-400 mt-1">Angebotspreis (netto)</div>
          {data.marge_prozent > 0 && (
            <div className="text-sm text-green-400 mt-2 font-medium">
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
    <Button
      variant="outline"
      size="sm"
      onClick={onClick}
      disabled={loading}
      className="border-slate-600 hover:border-amber-400 hover:bg-amber-500/10 disabled:bg-slate-700 disabled:text-slate-500 text-slate-200"
    >
      {loading ? '...' : label}
    </Button>
  )
}
