import { useState, useEffect } from 'react'
import { config, materialpreise } from '../api'
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Table, TableHeader, TableBody, TableHead, TableRow, TableCell,
} from "@/components/ui/table"

export default function Einstellungen() {
  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Einstellungen</h1>

      {/* Tab-Navigation mit shadcn Tabs */}
      <Tabs defaultValue="maschinen">
        <TabsList className="bg-slate-800/60 w-full">
          <TabsTrigger
            value="maschinen"
            className="flex-1 data-[state=active]:bg-amber-600/90 data-[state=active]:text-white data-[state=active]:shadow-lg data-[state=active]:shadow-amber-900/20"
          >
            Maschinen
          </TabsTrigger>
          <TabsTrigger
            value="zuschlaege"
            className="flex-1 data-[state=active]:bg-amber-600/90 data-[state=active]:text-white data-[state=active]:shadow-lg data-[state=active]:shadow-amber-900/20"
          >
            Zuschlaege
          </TabsTrigger>
          <TabsTrigger
            value="stundensaetze"
            className="flex-1 data-[state=active]:bg-amber-600/90 data-[state=active]:text-white data-[state=active]:shadow-lg data-[state=active]:shadow-amber-900/20"
          >
            Stundensaetze
          </TabsTrigger>
          <TabsTrigger
            value="materialpreise"
            className="flex-1 data-[state=active]:bg-amber-600/90 data-[state=active]:text-white data-[state=active]:shadow-lg data-[state=active]:shadow-amber-900/20"
          >
            Materialpreise
          </TabsTrigger>
        </TabsList>

        <TabsContent value="maschinen">
          <MaschinenTab />
        </TabsContent>
        <TabsContent value="zuschlaege">
          <ZuschlaegeTab />
        </TabsContent>
        <TabsContent value="stundensaetze">
          <StundensaetzeTab />
        </TabsContent>
        <TabsContent value="materialpreise">
          <MaterialpreiseTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// --- Maschinen ---
function MaschinenTab() {
  const [data, setData] = useState(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => { config.maschinen.get().then(setData).catch(e => setMsg(e.message)) }, [])

  const update = (maschine, key, value) => {
    setData(prev => ({
      ...prev,
      [maschine]: { ...prev[maschine], [key]: Number(value) || value },
    }))
  }

  const save = async () => {
    setSaving(true)
    try {
      const res = await config.maschinen.save(data)
      setData(res)
      setMsg('Gespeichert!')
      setTimeout(() => setMsg(null), 2000)
    } catch (e) {
      setMsg('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!data) return <Loading />

  const maschinen = [
    { key: 'holzher_nextec_7707', label: 'Holzher Nextec 7707 (CNC)',
      fields: ['stundensatz', 'platten_pro_schicht_premium', 'platten_pro_schicht_standard', 'schichtdauer_h', 'ruestzeit_min'] },
    { key: 'kantenanleimmaschine', label: 'Kantenanleimmaschine',
      fields: ['stundensatz', 'lfm_pro_stunde'] },
    { key: 'formatkreissaege', label: 'Formatkreissaege',
      fields: ['stundensatz', 'schnitte_pro_stunde'] },
    { key: 'bohrautomat', label: 'Bohrautomat',
      fields: ['stundensatz', 'bohrungen_pro_stunde'] },
  ]

  return (
    <ConfigCard title="Maschinenkonfiguration" onSave={save} saving={saving} msg={msg}>
      {maschinen.map(m => (
        <div key={m.key} className="mb-6 last:mb-0">
          <h3 className="font-medium text-slate-200 mb-3">{m.label}</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {m.fields.map(f => (
              <ConfigField
                key={f}
                label={fieldLabel(f)}
                value={data[m.key]?.[f] ?? ''}
                onChange={v => update(m.key, f, v)}
              />
            ))}
          </div>
        </div>
      ))}
    </ConfigCard>
  )
}

// --- Zuschlaege ---
function ZuschlaegeTab() {
  const [data, setData] = useState(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => { config.zuschlaege.get().then(setData).catch(e => setMsg(e.message)) }, [])

  const update = (key, value) => {
    setData(prev => ({ ...prev, [key]: Number(value) || 0 }))
  }

  const save = async () => {
    setSaving(true)
    try {
      const res = await config.zuschlaege.save(data)
      setData(res)
      setMsg('Gespeichert!')
      setTimeout(() => setMsg(null), 2000)
    } catch (e) {
      setMsg('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!data) return <Loading />

  const fields = [
    { key: 'gemeinkosten_gkz', label: 'Gemeinkostenzuschlag (GKZ)' },
    { key: 'gewinnaufschlag_standard', label: 'Gewinn Standard' },
    { key: 'gewinnaufschlag_oeffentlich', label: 'Gewinn Oeffentlich (VOB)' },
    { key: 'gewinnaufschlag_privat', label: 'Gewinn Privat' },
    { key: 'wagnis_vob', label: 'Wagnis (VOB)' },
    { key: 'montage_baustellenzuschlag', label: 'Montage/Baustelle' },
    { key: 'fremdleistung_lackierung', label: 'FL Lackierung' },
    { key: 'fremdleistung_montage', label: 'FL Montage' },
  ]

  return (
    <ConfigCard title="Zuschlagssaetze" onSave={save} saving={saving} msg={msg}>
      <div className="grid grid-cols-2 gap-4">
        {fields.map(f => (
          <div key={f.key}>
            <Label className="text-slate-300 mb-1">{f.label}</Label>
            <div className="flex items-center gap-2">
              <Input
                type="number" step="0.01" min="0" max="1"
                value={data[f.key] ?? ''}
                onChange={e => update(f.key, e.target.value)}
                className="bg-slate-800/60 border-slate-600 text-slate-200 focus-visible:ring-amber-500/50 focus-visible:border-amber-500/50"
              />
              <span className="text-sm text-slate-400 whitespace-nowrap">
                = {((data[f.key] || 0) * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </ConfigCard>
  )
}

// --- Stundensaetze ---
function StundensaetzeTab() {
  const [data, setData] = useState(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => { config.stundensaetze.get().then(setData).catch(e => setMsg(e.message)) }, [])

  const update = (key, value) => {
    setData(prev => ({ ...prev, [key]: Number(value) || 0 }))
  }

  const updateNested = (parent, key, value) => {
    setData(prev => ({
      ...prev,
      [parent]: { ...prev[parent], [key]: Number(value) || 0 },
    }))
  }

  const save = async () => {
    setSaving(true)
    try {
      const res = await config.stundensaetze.save(data)
      setData(res)
      setMsg('Gespeichert!')
      setTimeout(() => setMsg(null), 2000)
    } catch (e) {
      setMsg('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!data) return <Loading />

  return (
    <ConfigCard title="Stundensaetze & Montage" onSave={save} saving={saving} msg={msg}>
      <div className="grid grid-cols-2 gap-4 mb-6">
        <ConfigField
          label="Einheitlicher Stundensatz (EUR/h)"
          value={data.einheitlicher_stundensatz ?? ''}
          onChange={v => update('einheitlicher_stundensatz', v)}
        />
        <ConfigField
          label="Verfuegbare Monteure"
          value={data.monteure_anzahl ?? ''}
          onChange={v => update('monteure_anzahl', v)}
        />
      </div>
      <h3 className="font-medium text-slate-200 mb-3">Montage-Stunden pro Einheit</h3>
      <div className="grid grid-cols-3 gap-4">
        <ConfigField
          label="Minimum"
          value={data.montage_stunden_pro_einheit?.min ?? ''}
          onChange={v => updateNested('montage_stunden_pro_einheit', 'min', v)}
        />
        <ConfigField
          label="Standard"
          value={data.montage_stunden_pro_einheit?.standard ?? ''}
          onChange={v => updateNested('montage_stunden_pro_einheit', 'standard', v)}
        />
        <ConfigField
          label="Maximum"
          value={data.montage_stunden_pro_einheit?.max ?? ''}
          onChange={v => updateNested('montage_stunden_pro_einheit', 'max', v)}
        />
      </div>
    </ConfigCard>
  )
}

// --- Materialpreise ---
function MaterialpreiseTab() {
  const [liste, setListe] = useState([])
  const [suche, setSuche] = useState('')
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newItem, setNewItem] = useState({
    material_name: '', kategorie: '', lieferant: '', preis: 0, einheit: 'STK',
  })

  const loadPreise = async () => {
    setLoading(true)
    try {
      const res = await materialpreise.liste('', suche)
      setListe(res)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadPreise() }, [])

  const handleSearch = (e) => {
    e.preventDefault()
    loadPreise()
  }

  const handleAdd = async (e) => {
    e.preventDefault()
    try {
      await materialpreise.erstellen({ ...newItem, preis: Number(newItem.preis) })
      setShowAdd(false)
      setNewItem({ material_name: '', kategorie: '', lieferant: '', preis: 0, einheit: 'STK' })
      loadPreise()
      setMsg('Preis hinzugefuegt!')
      setTimeout(() => setMsg(null), 2000)
    } catch (e) {
      setMsg('Fehler: ' + e.message)
    }
  }

  const handleImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    try {
      const res = await materialpreise.importieren(file)
      setMsg(`${res.importiert} Preise importiert!`)
      loadPreise()
      setTimeout(() => setMsg(null), 3000)
    } catch (e) {
      setMsg('Import-Fehler: ' + e.message)
    }
    e.target.value = ''
  }

  return (
    <Card className="glass-card border-0 py-0 gap-0">
      <CardHeader className="px-5 py-4 border-b border-slate-700/30 flex-row items-center justify-between">
        <CardTitle className="text-slate-200">Materialpreisliste</CardTitle>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild
            className="border-slate-600 hover:border-amber-500/50 text-slate-200 cursor-pointer"
          >
            <label>
              CSV/Excel importieren
              <input type="file" accept=".csv,.xlsx,.xls" onChange={handleImport} className="hidden" />
            </label>
          </Button>
          <Button size="sm" onClick={() => setShowAdd(!showAdd)}
            className="bg-amber-600 hover:bg-amber-700 text-white"
          >
            + Neuer Preis
          </Button>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {/* Erfolgs-/Fehlermeldung */}
        {msg && (
          <div className="mx-5 mt-3">
            <Alert className="bg-green-500/10 border-green-500/30 text-green-400">
              <AlertDescription>{msg}</AlertDescription>
            </Alert>
          </div>
        )}

        {/* Neuer Preis Form */}
        {showAdd && (
          <form onSubmit={handleAdd} className="px-5 py-4 border-b border-slate-700/30 bg-slate-800/40">
            <div className="grid grid-cols-5 gap-3">
              <Input
                required
                value={newItem.material_name}
                onChange={e => setNewItem(p => ({ ...p, material_name: e.target.value }))}
                placeholder="Materialname"
                className="bg-slate-800/60 border-slate-600 text-slate-200 focus-visible:ring-amber-500/50"
              />
              <Input
                value={newItem.kategorie}
                onChange={e => setNewItem(p => ({ ...p, kategorie: e.target.value }))}
                placeholder="Kategorie"
                className="bg-slate-800/60 border-slate-600 text-slate-200 focus-visible:ring-amber-500/50"
              />
              <Input
                value={newItem.lieferant}
                onChange={e => setNewItem(p => ({ ...p, lieferant: e.target.value }))}
                placeholder="Lieferant"
                className="bg-slate-800/60 border-slate-600 text-slate-200 focus-visible:ring-amber-500/50"
              />
              <Input
                type="number" step="0.01" min="0" required
                value={newItem.preis}
                onChange={e => setNewItem(p => ({ ...p, preis: e.target.value }))}
                placeholder="Preis"
                className="bg-slate-800/60 border-slate-600 text-slate-200 focus-visible:ring-amber-500/50"
              />
              <Button type="submit" className="bg-amber-600 hover:bg-amber-700 text-white">
                Speichern
              </Button>
            </div>
          </form>
        )}

        {/* Suche */}
        <form onSubmit={handleSearch} className="px-5 py-3 border-b border-slate-700/30 flex gap-2">
          <Input
            value={suche}
            onChange={e => setSuche(e.target.value)}
            placeholder="Material suchen..."
            className="flex-1 bg-slate-800/60 border-slate-600 text-slate-200 focus-visible:ring-amber-500/50"
          />
          <Button type="submit" variant="ghost" className="text-amber-500 hover:text-amber-400">
            Suchen
          </Button>
        </form>

        {/* Tabelle */}
        {loading ? (
          <div className="p-8 text-center text-slate-400">Lade...</div>
        ) : liste.length === 0 ? (
          <div className="p-8 text-center text-slate-400">Keine Materialpreise gefunden</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-slate-700/30 hover:bg-transparent">
                <TableHead className="px-5 py-3 text-xs text-slate-400 uppercase tracking-wider">Material</TableHead>
                <TableHead className="px-5 py-3 text-xs text-slate-400 uppercase tracking-wider">Kategorie</TableHead>
                <TableHead className="px-5 py-3 text-xs text-slate-400 uppercase tracking-wider">Lieferant</TableHead>
                <TableHead className="px-5 py-3 text-xs text-slate-400 uppercase tracking-wider">Einheit</TableHead>
                <TableHead className="px-5 py-3 text-xs text-slate-400 uppercase tracking-wider text-right">Preis</TableHead>
                <TableHead className="px-5 py-3 text-xs text-slate-400 uppercase tracking-wider">Gueltig ab</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {liste.map(m => (
                <TableRow key={m.id} className="border-slate-700/30 hover:bg-slate-700/30">
                  <TableCell className="px-5 py-3 text-sm font-medium text-white">{m.material_name}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-300">{m.kategorie || '-'}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-300">{m.lieferant || '-'}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-300">{m.einheit}</TableCell>
                  <TableCell className="px-5 py-3 text-sm text-right font-medium text-white">
                    {Number(m.preis).toFixed(2)} EUR
                  </TableCell>
                  <TableCell className="px-5 py-3 text-sm text-slate-400">
                    {m.gueltig_ab ? new Date(m.gueltig_ab).toLocaleDateString('de-DE') : '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// --- Shared Components ---
function ConfigCard({ title, children, onSave, saving, msg }) {
  return (
    <Card className="glass-card border-0 py-0 gap-0">
      <CardHeader className="px-6 pt-6 pb-0 flex-row items-center justify-between">
        <CardTitle className="text-slate-200">{title}</CardTitle>
        {msg && (
          <Alert className="w-auto bg-green-500/10 border-green-500/30 text-green-400 py-1.5 px-3">
            <AlertDescription>{msg}</AlertDescription>
          </Alert>
        )}
      </CardHeader>
      <CardContent className="px-6 pt-4 pb-0">
        {children}
      </CardContent>
      <CardFooter className="px-6 pt-4 pb-6 justify-end">
        <Button
          onClick={onSave}
          disabled={saving}
          className="bg-amber-600 hover:bg-amber-700 disabled:bg-slate-700 disabled:text-slate-500 disabled:opacity-100 text-white px-6"
        >
          {saving ? 'Speichern...' : 'Speichern'}
        </Button>
      </CardFooter>
    </Card>
  )
}

function ConfigField({ label, value, onChange }) {
  return (
    <div>
      <Label className="text-slate-300 mb-1">{label}</Label>
      <Input
        type="number" step="any"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="bg-slate-800/60 border-slate-600 text-slate-200 focus-visible:ring-amber-500/50 focus-visible:border-amber-500/50"
      />
    </div>
  )
}

function Loading() {
  return <div className="text-center py-8 text-slate-400">Lade Konfiguration...</div>
}

function fieldLabel(key) {
  const labels = {
    stundensatz: 'Stundensatz (EUR/h)',
    platten_pro_schicht_premium: 'Platten/Schicht (Premium)',
    platten_pro_schicht_standard: 'Platten/Schicht (Standard)',
    schichtdauer_h: 'Schichtdauer (h)',
    ruestzeit_min: 'Ruestzeit (min)',
    lfm_pro_stunde: 'Lfm pro Stunde',
    schnitte_pro_stunde: 'Schnitte pro Stunde',
    bohrungen_pro_stunde: 'Bohrungen pro Stunde',
  }
  return labels[key] || key
}
