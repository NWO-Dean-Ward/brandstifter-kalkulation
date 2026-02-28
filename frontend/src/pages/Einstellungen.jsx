import { useState, useEffect } from 'react'
import { config, materialpreise } from '../api'

export default function Einstellungen() {
  const [tab, setTab] = useState('maschinen')

  const tabs = [
    { id: 'maschinen', label: 'Maschinen' },
    { id: 'zuschlaege', label: 'Zuschlaege' },
    { id: 'stundensaetze', label: 'Stundensaetze' },
    { id: 'materialpreise', label: 'Materialpreise' },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Einstellungen</h1>

      {/* Tab-Navigation */}
      <div className="flex gap-1 bg-slate-800/60 rounded-lg p-1 mb-6">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === t.id
                ? 'bg-amber-600/90 text-white shadow-lg shadow-amber-900/20'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'maschinen' && <MaschinenTab />}
      {tab === 'zuschlaege' && <ZuschlaegeTab />}
      {tab === 'stundensaetze' && <StundensaetzeTab />}
      {tab === 'materialpreise' && <MaterialpreiseTab />}
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
            <label className="block text-sm font-medium text-slate-300 mb-1">{f.label}</label>
            <div className="flex items-center gap-2">
              <input
                type="number" step="0.01" min="0" max="1"
                value={data[f.key] ?? ''}
                onChange={e => update(f.key, e.target.value)}
                className="w-full border border-slate-600 rounded-lg px-3 py-2 text-sm bg-slate-800/60 text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50"
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
    <div className="glass-card">
      <div className="px-5 py-4 border-b border-slate-700/30 flex items-center justify-between">
        <h2 className="font-semibold text-slate-200">Materialpreisliste</h2>
        <div className="flex gap-2">
          <label className="border border-slate-600 hover:border-amber-500/50 text-slate-200 px-3 py-1.5 rounded-lg text-sm font-medium cursor-pointer transition-colors">
            CSV/Excel importieren
            <input type="file" accept=".csv,.xlsx,.xls" onChange={handleImport} className="hidden" />
          </label>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="bg-amber-600 hover:bg-amber-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
          >
            + Neuer Preis
          </button>
        </div>
      </div>

      {msg && (
        <div className="mx-5 mt-3 text-sm text-green-400 bg-green-500/10 border border-green-500/30 rounded px-3 py-2">
          {msg}
        </div>
      )}

      {/* Neuer Preis Form */}
      {showAdd && (
        <form onSubmit={handleAdd} className="px-5 py-4 border-b border-slate-700/30 bg-slate-800/40">
          <div className="grid grid-cols-5 gap-3">
            <input
              required
              value={newItem.material_name}
              onChange={e => setNewItem(p => ({ ...p, material_name: e.target.value }))}
              placeholder="Materialname"
              className="border border-slate-600 rounded px-2 py-1.5 text-sm bg-slate-800/60 text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50"
            />
            <input
              value={newItem.kategorie}
              onChange={e => setNewItem(p => ({ ...p, kategorie: e.target.value }))}
              placeholder="Kategorie"
              className="border border-slate-600 rounded px-2 py-1.5 text-sm bg-slate-800/60 text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50"
            />
            <input
              value={newItem.lieferant}
              onChange={e => setNewItem(p => ({ ...p, lieferant: e.target.value }))}
              placeholder="Lieferant"
              className="border border-slate-600 rounded px-2 py-1.5 text-sm bg-slate-800/60 text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50"
            />
            <input
              type="number" step="0.01" min="0" required
              value={newItem.preis}
              onChange={e => setNewItem(p => ({ ...p, preis: e.target.value }))}
              placeholder="Preis"
              className="border border-slate-600 rounded px-2 py-1.5 text-sm bg-slate-800/60 text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50"
            />
            <button
              type="submit"
              className="bg-amber-600 hover:bg-amber-700 text-white rounded text-sm font-medium transition-colors"
            >
              Speichern
            </button>
          </div>
        </form>
      )}

      {/* Suche */}
      <form onSubmit={handleSearch} className="px-5 py-3 border-b border-slate-700/30 flex gap-2">
        <input
          value={suche}
          onChange={e => setSuche(e.target.value)}
          placeholder="Material suchen..."
          className="flex-1 border border-slate-600 rounded-lg px-3 py-1.5 text-sm bg-slate-800/60 text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50"
        />
        <button
          type="submit"
          className="text-sm text-amber-500 hover:text-amber-400 font-medium"
        >
          Suchen
        </button>
      </form>

      {/* Tabelle */}
      {loading ? (
        <div className="p-8 text-center text-slate-400">Lade...</div>
      ) : liste.length === 0 ? (
        <div className="p-8 text-center text-slate-400">Keine Materialpreise gefunden</div>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs text-slate-400 uppercase tracking-wider">
              <th className="px-5 py-3">Material</th>
              <th className="px-5 py-3">Kategorie</th>
              <th className="px-5 py-3">Lieferant</th>
              <th className="px-5 py-3">Einheit</th>
              <th className="px-5 py-3 text-right">Preis</th>
              <th className="px-5 py-3">Gueltig ab</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/30">
            {liste.map(m => (
              <tr key={m.id} className="hover:bg-slate-700/30">
                <td className="px-5 py-3 text-sm font-medium text-white">{m.material_name}</td>
                <td className="px-5 py-3 text-sm text-slate-300">{m.kategorie || '-'}</td>
                <td className="px-5 py-3 text-sm text-slate-300">{m.lieferant || '-'}</td>
                <td className="px-5 py-3 text-sm text-slate-300">{m.einheit}</td>
                <td className="px-5 py-3 text-sm text-right font-medium text-white">
                  {Number(m.preis).toFixed(2)} EUR
                </td>
                <td className="px-5 py-3 text-sm text-slate-400">
                  {m.gueltig_ab ? new Date(m.gueltig_ab).toLocaleDateString('de-DE') : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// --- Shared Components ---
function ConfigCard({ title, children, onSave, saving, msg }) {
  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-slate-200">{title}</h2>
        {msg && <span className="text-sm text-green-400">{msg}</span>}
      </div>
      {children}
      <div className="mt-6 flex justify-end">
        <button
          onClick={onSave}
          disabled={saving}
          className="bg-amber-600 hover:bg-amber-700 disabled:bg-slate-700 disabled:text-slate-500 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? 'Speichern...' : 'Speichern'}
        </button>
      </div>
    </div>
  )
}

function ConfigField({ label, value, onChange }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-300 mb-1">{label}</label>
      <input
        type="number" step="any"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full border border-slate-600 rounded-lg px-3 py-2 text-sm bg-slate-800/60 text-slate-200 outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50"
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
