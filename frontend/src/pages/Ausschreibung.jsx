import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { projekte, positionen, kalkulation } from '../api'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'

const LEERE_POSITION = {
  pos_nr: '', kurztext: '', menge: 1, einheit: 'STK',
  material: '', platten_anzahl: 0, kantenlaenge_lfm: 0,
  schnittanzahl: 0, bohrungen_anzahl: 0,
}

export default function Ausschreibung() {
  const navigate = useNavigate()
  const fileRef = useRef()
  const [step, setStep] = useState(1) // 1: Projekt, 2: Positionen, 3: Ergebnis
  const [projekt, setProjekt] = useState({
    name: '', projekt_typ: 'standard', kunde: '', beschreibung: '', deadline: '',
  })
  const [projektId, setProjektId] = useState(null)
  const [posList, setPosList] = useState([])
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  // Step 1: Projekt anlegen
  const handleProjektErstellen = async (e) => {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      const res = await projekte.erstellen(projekt)
      setProjektId(res.id)
      setStep(2)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  // Datei-Upload (GAEB/PDF/Excel)
  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const res = await kalkulation.upload(file, projektId)
      if (res.positionen && res.positionen.length > 0) {
        // Geparste Positionen uebernehmen
        const mapped = res.positionen.map((p, i) => ({
          pos_nr: p.pos_nr || `${i + 1}`,
          kurztext: p.kurztext || '',
          langtext: p.langtext || '',
          menge: p.menge || 1,
          einheit: p.einheit || 'STK',
          material: p.material || '',
          platten_anzahl: p.platten_anzahl || 0,
          kantenlaenge_lfm: p.kantenlaenge_lfm || 0,
          schnittanzahl: p.schnittanzahl || 0,
          bohrungen_anzahl: p.bohrungen_anzahl || 0,
        }))
        setPosList(prev => [...prev, ...mapped])
      }
    } catch (e) {
      setError('Upload-Fehler: ' + e.message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  // Position hinzufuegen
  const addPosition = () => {
    const nr = String(posList.length + 1).padStart(2, '0')
    setPosList(prev => [...prev, { ...LEERE_POSITION, pos_nr: `01.${nr}` }])
  }

  const updatePos = (idx, field, value) => {
    setPosList(prev => prev.map((p, i) =>
      i === idx ? { ...p, [field]: value } : p
    ))
  }

  const removePos = (idx) => {
    setPosList(prev => prev.filter((_, i) => i !== idx))
  }

  // Positionen speichern und kalkulieren
  const handleKalkulieren = async () => {
    if (posList.length === 0) {
      setError('Mindestens eine Position erforderlich')
      return
    }
    setSaving(true)
    setError(null)
    try {
      // Positionen in DB speichern
      for (const pos of posList) {
        await positionen.erstellen(projektId, {
          ...pos,
          menge: Number(pos.menge) || 1,
          platten_anzahl: Number(pos.platten_anzahl) || 0,
          kantenlaenge_lfm: Number(pos.kantenlaenge_lfm) || 0,
          schnittanzahl: Number(pos.schnittanzahl) || 0,
          bohrungen_anzahl: Number(pos.bohrungen_anzahl) || 0,
        })
      }
      // Zur Projektseite navigieren und Kalkulation dort starten
      navigate(`/projekt/${projektId}`)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Neue Ausschreibung</h1>

      {/* Stepper – bleibt custom */}
      <div className="flex gap-4 mb-8">
        {['Projektdaten', 'Positionen'].map((label, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              step > i + 1 ? 'bg-green-500 text-white' :
              step === i + 1 ? 'bg-amber-600 text-white' :
              'bg-slate-700 text-slate-400'
            }`}>
              {step > i + 1 ? '>' : i + 1}
            </div>
            <span className={`text-sm ${step === i + 1 ? 'font-medium text-white' : 'text-slate-400'}`}>
              {label}
            </span>
            {i < 1 && <div className="w-12 h-px bg-slate-600 ml-2" />}
          </div>
        ))}
      </div>

      {/* Fehleranzeige */}
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Step 1: Projektdaten */}
      {step === 1 && (
        <form onSubmit={handleProjektErstellen} className="glass-card overflow-hidden p-6">
          <h2 className="font-semibold text-slate-200 mb-4">Projektdaten</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="projektname">Projektname *</Label>
              <Input
                id="projektname"
                required
                value={projekt.name}
                onChange={e => setProjekt(p => ({ ...p, name: e.target.value }))}
                placeholder="z.B. Schule Ober-Moerlen"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="kunde">Kunde</Label>
              <Input
                id="kunde"
                value={projekt.kunde}
                onChange={e => setProjekt(p => ({ ...p, kunde: e.target.value }))}
                placeholder="z.B. Gemeinde Ober-Moerlen"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="projekt_typ">Projekttyp</Label>
              <select
                id="projekt_typ"
                value={projekt.projekt_typ}
                onChange={e => setProjekt(p => ({ ...p, projekt_typ: e.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30 md:text-sm"
              >
                <option value="standard">Standard</option>
                <option value="oeffentlich">Oeffentlich (VOB)</option>
                <option value="privat">Privat</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="beschreibung">Beschreibung</Label>
              <Input
                id="beschreibung"
                value={projekt.beschreibung}
                onChange={e => setProjekt(p => ({ ...p, beschreibung: e.target.value }))}
                placeholder="Optionale Beschreibung"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="deadline">Abgabefrist</Label>
              <Input
                id="deadline"
                type="date"
                value={projekt.deadline}
                onChange={e => setProjekt(p => ({ ...p, deadline: e.target.value }))}
              />
            </div>
          </div>
          <div className="mt-6 flex justify-end">
            <Button type="submit" disabled={saving}>
              {saving ? 'Speichern...' : 'Weiter'}
            </Button>
          </div>
        </form>
      )}

      {/* Step 2: Positionen */}
      {step === 2 && (
        <div>
          {/* Upload-Box */}
          <div className="glass-card overflow-hidden p-6 mb-4">
            <h2 className="font-semibold text-slate-200 mb-3">Dokument importieren</h2>
            <p className="text-sm text-slate-400 mb-3">
              GAEB (.d83, .x83, .x84), PDF oder Excel (.xlsx) hochladen.
              Positionen werden automatisch erkannt.
            </p>
            <div className="flex gap-3 items-center">
              <Input
                ref={fileRef}
                type="file"
                accept=".d83,.x83,.x84,.pdf,.xlsx,.xls"
                onChange={handleUpload}
                className="file:mr-3 file:py-1 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-amber-500/20 file:text-amber-400 hover:file:bg-amber-500/30"
              />
              {uploading && <span className="text-sm text-slate-400">Wird geparst...</span>}
            </div>
          </div>

          {/* Positionsliste */}
          <div className="glass-card overflow-hidden p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-200">
                Positionen ({posList.length})
              </h2>
              <Button variant="ghost" size="sm" onClick={addPosition}>
                + Manuell hinzufuegen
              </Button>
            </div>

            {posList.length === 0 ? (
              <p className="text-sm text-slate-400 py-4">
                Noch keine Positionen. Importiere ein Dokument oder fuege manuell hinzu.
              </p>
            ) : (
              <div className="space-y-3">
                {posList.map((pos, idx) => (
                  <PositionRow
                    key={idx}
                    pos={pos}
                    onChange={(field, val) => updatePos(idx, field, val)}
                    onRemove={() => removePos(idx)}
                  />
                ))}
              </div>
            )}

            <div className="mt-6 flex justify-between">
              <Button
                variant="ghost"
                onClick={() => { setStep(1); setProjektId(null) }}
              >
                Zurueck
              </Button>
              <Button
                onClick={handleKalkulieren}
                disabled={saving || posList.length === 0}
              >
                {saving ? 'Speichern...' : 'Positionen speichern & Projekt oeffnen'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function PositionRow({ pos, onChange, onRemove }) {
  return (
    <Card className="gap-0 py-0 border-slate-700/50">
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          {/* Pos-Nr + Kurztext */}
          <div className="grid grid-cols-12 gap-3 flex-1">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-slate-400">Pos-Nr</Label>
              <Input
                value={pos.pos_nr}
                onChange={e => onChange('pos_nr', e.target.value)}
                className="h-8 px-2 text-sm"
              />
            </div>
            <div className="col-span-4 space-y-1">
              <Label className="text-xs text-slate-400">Kurztext</Label>
              <Input
                value={pos.kurztext}
                onChange={e => onChange('kurztext', e.target.value)}
                className="h-8 px-2 text-sm"
                placeholder="Beschreibung der Position"
              />
            </div>
            <div className="col-span-1 space-y-1">
              <Label className="text-xs text-slate-400">Menge</Label>
              <Input
                type="number" min="0" step="1"
                value={pos.menge}
                onChange={e => onChange('menge', e.target.value)}
                className="h-8 px-2 text-sm"
              />
            </div>
            <div className="col-span-1 space-y-1">
              <Label className="text-xs text-slate-400">Einheit</Label>
              <select
                value={pos.einheit}
                onChange={e => onChange('einheit', e.target.value)}
                className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30"
              >
                <option>STK</option>
                <option>m2</option>
                <option>LFM</option>
                <option>PAU</option>
              </select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-slate-400">Material</Label>
              <Input
                value={pos.material}
                onChange={e => onChange('material', e.target.value)}
                className="h-8 px-2 text-sm"
                placeholder="z.B. Melamin weiss"
              />
            </div>
            <div className="col-span-1 space-y-1">
              <Label className="text-xs text-slate-400">Platten</Label>
              <Input
                type="number" min="0"
                value={pos.platten_anzahl}
                onChange={e => onChange('platten_anzahl', e.target.value)}
                className="h-8 px-2 text-sm"
              />
            </div>
            <div className="col-span-1 space-y-1">
              <Label className="text-xs text-slate-400">Kanten</Label>
              <Input
                type="number" min="0" step="0.1"
                value={pos.kantenlaenge_lfm}
                onChange={e => onChange('kantenlaenge_lfm', e.target.value)}
                className="h-8 px-2 text-sm"
              />
            </div>
            <div className="col-span-2 hidden">
              {/* Reserviert fuer zukuenftige Felder */}
            </div>
            <div className="col-span-1 space-y-1">
              <Label className="text-xs text-slate-400">Bohr.</Label>
              <Input
                type="number" min="0"
                value={pos.bohrungen_anzahl}
                onChange={e => onChange('bohrungen_anzahl', e.target.value)}
                className="h-8 px-2 text-sm"
              />
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onRemove}
            className="mt-5 text-slate-400 hover:text-red-400"
            title="Position entfernen"
          >
            X
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
