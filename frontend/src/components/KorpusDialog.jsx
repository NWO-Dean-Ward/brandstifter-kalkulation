import { useEffect, useRef, useState } from 'react'
import { korpus as korpusApi, materialpreise } from '../api'

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table"

const TYP_LABEL = { unterschrank: 'Unterschrank', haengeschrank: 'Haengeschrank', hochschrank: 'Hochschrank' }
const RUECKWAND_LABEL = { eingenutet: 'Eingenutet', aufgesetzt: 'Aufgesetzt', keine: 'Keine Rueckwand' }
const QUALITAET_LABEL = { standard: 'Standard', hochwertig: 'Hochwertig' }

const ZAHL_FELDER = ['anzahl', 'breite_mm', 'hoehe_mm', 'tiefe_mm', 'einlegeboeden', 'tueren', 'schubkaesten', 'sockel_hoehe_mm']
const STAERKE_FELDER = ['korpus_staerke_mm', 'front_staerke_mm', 'rueckwand_staerke_mm']

const LEERES_FORMULAR = {
  typ: 'unterschrank', bezeichnung: '', anzahl: '1',
  breite_mm: '600', hoehe_mm: '720', tiefe_mm: '560',
  einlegeboeden: '1', tueren: '1', schubkaesten: '0', sockel_hoehe_mm: '150',
  sockelblende: true, griffe: true, montage: true,
  korpus_material: '', korpus_staerke_mm: '', korpus_maserung: false,
  front_material: '', front_staerke_mm: '', front_maserung: false,
  rueckwand_material: '', rueckwand_staerke_mm: '', rueckwand_art: 'eingenutet',
  qualitaet: 'standard',
}

function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}
function zahl(val, stellen = 2) {
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: stellen }).format(val || 0)
}

function toRequest(form) {
  const req = { ...form }
  for (const f of ZAHL_FELDER) req[f] = Number(form[f]) || 0
  for (const f of STAERKE_FELDER) req[f] = form[f] === '' ? null : Number(form[f])
  return req
}

const inputClass = "h-8 bg-slate-800/60 border-slate-600 text-slate-200 text-sm placeholder-slate-500 focus:ring-amber-500/50 focus:border-amber-500/50"
const triggerClass = "h-8 w-full bg-slate-800/60 border-slate-600 text-slate-200 text-sm"

function Feld({ label, htmlFor, children, className = '' }) {
  return (
    <div className={`space-y-1 ${className}`}>
      <Label htmlFor={htmlFor} className="text-xs text-slate-400">{label}</Label>
      {children}
    </div>
  )
}

function Haken({ id, label, checked, onChange }) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
      <input id={id} type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)}
        className="h-4 w-4 accent-amber-600" />
      {label}
    </label>
  )
}

function Kennzahl({ label, wert, sub }) {
  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-base font-bold text-amber-400">{wert}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  )
}

/**
 * Korpus-Generator: Masse und Ausstattung -> Stueckliste, Plattenbedarf, Kanten,
 * Beschlaege und Stunden (Berechnung auf dem Server, Live-Vorschau).
 */
export default function KorpusDialog({ open, onOpenChange, onUebernehmen }) {
  const [form, setForm] = useState(LEERES_FORMULAR)
  const [vorlagen, setVorlagen] = useState([])
  const [vorlage, setVorlage] = useState('')
  const [plattenNamen, setPlattenNamen] = useState([])
  const [ergebnis, setErgebnis] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [laedt, setLaedt] = useState(false)
  const anfrageNr = useRef(0)

  // Vorlagen, Standardwerte und Materialnamen beim ersten Oeffnen laden
  useEffect(() => {
    if (!open || vorlagen.length > 0) return
    korpusApi.vorlagen()
      .then(d => {
        setVorlagen(d.vorlagen || [])
        if (d.standard) {
          setForm(prev => ({
            ...prev,
            korpus_staerke_mm: prev.korpus_staerke_mm || String(d.standard.korpus_staerke_mm),
            front_staerke_mm: prev.front_staerke_mm || String(d.standard.front_staerke_mm),
            rueckwand_staerke_mm: prev.rueckwand_staerke_mm || String(d.standard.rueckwand_staerke_mm),
            rueckwand_art: d.standard.rueckwand_art || prev.rueckwand_art,
          }))
        }
      })
      .catch(e => setFehler(`Vorlagen nicht geladen: ${e.message}`))
    materialpreise.liste('platte')
      .then(liste => setPlattenNamen(liste.map(m => m.material_name)))
      .catch(() => setPlattenNamen([]))
  }, [open, vorlagen.length])

  // Live-Vorschau: jede Aenderung neu berechnen (entprellt), veraltete Antworten verwerfen
  useEffect(() => {
    if (!open) return
    const nr = ++anfrageNr.current
    setLaedt(true)
    const timer = setTimeout(async () => {
      try {
        const r = await korpusApi.berechnen(toRequest(form))
        if (nr !== anfrageNr.current) return
        setErgebnis(r)
        setFehler(null)
      } catch (e) {
        if (nr !== anfrageNr.current) return
        setErgebnis(null)
        setFehler(e.message)
      } finally {
        if (nr === anfrageNr.current) setLaedt(false)
      }
    }, 350)
    return () => clearTimeout(timer)
  }, [form, open])

  const set = (feld, wert) => setForm(prev => ({ ...prev, [feld]: wert }))

  const waehleVorlage = (name) => {
    setVorlage(name)
    const v = vorlagen.find(x => x.name === name)
    if (!v) return
    setForm(prev => {
      const neu = { ...prev, bezeichnung: v.name, typ: v.typ }
      for (const f of ZAHL_FELDER) if (v[f] !== undefined) neu[f] = String(v[f])
      return neu
    })
  }

  const uebernehmen = () => {
    if (!ergebnis) return
    onUebernehmen(ergebnis)
    onOpenChange(false)
  }

  const zahlInput = (feld, props = {}) => (
    <Input id={`korpus-${feld}`} type="number" value={form[feld]} onChange={e => set(feld, e.target.value)}
      className={`${inputClass} text-right`} {...props} />
  )

  const k = ergebnis?.kennzahlen

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-6xl max-h-[92vh] overflow-hidden p-0 gap-0 bg-slate-900 border-slate-700 text-slate-200">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-slate-700/60">
          <DialogTitle className="text-white">Korpus-Generator</DialogTitle>
          <DialogDescription className="text-slate-400 text-xs">
            Masse und Ausstattung eingeben. Stueckliste, Plattenbedarf, Kanten, Beschlaege und Stunden
            werden auf dem Server berechnet. Preise aus der Materialpreis-Datenbank, sonst Richtwerte aus config/korpus.yaml.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] min-h-0 overflow-y-auto max-h-[calc(92vh-140px)]">
          {/* Formular */}
          <div className="p-5 space-y-4 border-r border-slate-700/60">
            <Feld label="Vorlage">
              <Select value={vorlage} onValueChange={waehleVorlage}>
                <SelectTrigger className={triggerClass}><SelectValue placeholder="Vorlage waehlen..." /></SelectTrigger>
                <SelectContent>
                  {vorlagen.map(v => <SelectItem key={v.name} value={v.name}>{v.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </Feld>

            <div className="grid grid-cols-3 gap-2">
              <Feld label="Typ" className="col-span-2">
                <Select value={form.typ} onValueChange={v => set('typ', v)}>
                  <SelectTrigger className={triggerClass}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(TYP_LABEL).map(([w, l]) => <SelectItem key={w} value={w}>{l}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Feld>
              <Feld label="Anzahl" htmlFor="korpus-anzahl">{zahlInput('anzahl', { min: 1, max: 200 })}</Feld>
            </div>

            <Feld label="Bezeichnung" htmlFor="korpus-bezeichnung">
              <Input id="korpus-bezeichnung" value={form.bezeichnung} onChange={e => set('bezeichnung', e.target.value)}
                placeholder="z.B. Zimmerschrank Pflege" className={inputClass} />
            </Feld>

            <div>
              <div className="text-[11px] font-bold uppercase text-slate-500 mb-1">Aussenmasse Korpus (mm)</div>
              <div className="grid grid-cols-3 gap-2">
                <Feld label="Breite" htmlFor="korpus-breite_mm">{zahlInput('breite_mm', { step: 1 })}</Feld>
                <Feld label="Hoehe" htmlFor="korpus-hoehe_mm">{zahlInput('hoehe_mm', { step: 1 })}</Feld>
                <Feld label="Tiefe" htmlFor="korpus-tiefe_mm">{zahlInput('tiefe_mm', { step: 1 })}</Feld>
              </div>
            </div>

            <div>
              <div className="text-[11px] font-bold uppercase text-slate-500 mb-1">Ausstattung</div>
              <div className="grid grid-cols-4 gap-2">
                <Feld label="Boeden" htmlFor="korpus-einlegeboeden">{zahlInput('einlegeboeden', { min: 0, max: 15 })}</Feld>
                <Feld label="Tueren" htmlFor="korpus-tueren">{zahlInput('tueren', { min: 0, max: 2 })}</Feld>
                <Feld label="Schubk." htmlFor="korpus-schubkaesten">{zahlInput('schubkaesten', { min: 0, max: 8 })}</Feld>
                <Feld label="Sockel" htmlFor="korpus-sockel_hoehe_mm">{zahlInput('sockel_hoehe_mm', { min: 0, step: 10 })}</Feld>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                <Haken id="korpus-sockelblende" label="Sockelblende" checked={form.sockelblende} onChange={v => set('sockelblende', v)} />
                <Haken id="korpus-griffe" label="Griffe" checked={form.griffe} onChange={v => set('griffe', v)} />
                <Haken id="korpus-montage" label="Montage vor Ort" checked={form.montage} onChange={v => set('montage', v)} />
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-[11px] font-bold uppercase text-slate-500">Material</div>
              <datalist id="korpus-plattenmaterialien">
                {plattenNamen.map(n => <option key={n} value={n} />)}
              </datalist>
              {[
                ['korpus', 'Korpus', 'z.B. Egger W1000 ST9'],
                ['front', 'Front', 'z.B. Egger H1345 ST32'],
                ['rueckwand', 'Rueckwand', 'z.B. HDF weiss'],
              ].map(([key, label, ph]) => (
                <div key={key} className="grid grid-cols-[1fr_64px] gap-2">
                  <Feld label={label} htmlFor={`korpus-${key}_material`}>
                    <Input id={`korpus-${key}_material`} list="korpus-plattenmaterialien" value={form[`${key}_material`]}
                      onChange={e => set(`${key}_material`, e.target.value)} placeholder={ph} className={inputClass} />
                  </Feld>
                  <Feld label="mm" htmlFor={`korpus-${key}_staerke_mm`}>{zahlInput(`${key}_staerke_mm`, { min: 2, step: 1 })}</Feld>
                </div>
              ))}
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <Haken id="korpus-korpus_maserung" label="Korpus mit Maserung" checked={form.korpus_maserung} onChange={v => set('korpus_maserung', v)} />
                <Haken id="korpus-front_maserung" label="Front mit Maserung" checked={form.front_maserung} onChange={v => set('front_maserung', v)} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Feld label="Rueckwand-Art">
                  <Select value={form.rueckwand_art} onValueChange={v => set('rueckwand_art', v)}>
                    <SelectTrigger className={triggerClass}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(RUECKWAND_LABEL).map(([w, l]) => <SelectItem key={w} value={w}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </Feld>
                <Feld label="CNC-Kapazitaet">
                  <Select value={form.qualitaet} onValueChange={v => set('qualitaet', v)}>
                    <SelectTrigger className={triggerClass}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(QUALITAET_LABEL).map(([w, l]) => <SelectItem key={w} value={w}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </Feld>
              </div>
            </div>
          </div>

          {/* Vorschau */}
          <div className="p-5 space-y-4 min-w-0" aria-live="polite">
            {fehler && (
              <Alert variant="destructive" className="bg-red-500/10 text-red-400 border-red-500/30">
                <AlertDescription>{fehler}</AlertDescription>
              </Alert>
            )}

            {!ergebnis && !fehler && (
              <div className="text-sm text-slate-500 py-12 text-center">{laedt ? 'Berechne...' : 'Noch keine Berechnung.'}</div>
            )}

            {ergebnis && (
              <div className={`space-y-4 transition-opacity ${laedt ? 'opacity-60' : ''}`}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <Kennzahl label="Material netto" wert={euro(k.materialkosten_netto)} sub="Platten, Kanten, Beschlaege" />
                  <Kennzahl label="Platten" wert={`${zahl(k.flaeche_netto_m2)} m2`}
                    sub={`${zahl(k.flaeche_brutto_m2)} m2 brutto / ca. ${k.platten_zuschnitt} Platten`} />
                  <Kennzahl label="Kanten" wert={`${zahl(k.kanten_lfm)} lfm`} sub={`${k.beschlaege_stueck} Beschlaege`} />
                  <Kennzahl label="Stunden" wert={`${zahl(k.stunden_gesamt)} h`}
                    sub={Object.entries(ergebnis.stunden).filter(([, h]) => h > 0).map(([kat, h]) => `${kat} ${zahl(h, 1)}`).join(' / ')} />
                </div>

                {ergebnis.warnungen?.length > 0 && (
                  <Alert className="bg-amber-500/10 text-amber-300 border-amber-500/30">
                    <AlertDescription>
                      <ul className="list-disc pl-4 space-y-0.5 text-xs">
                        {ergebnis.warnungen.map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
                    </AlertDescription>
                  </Alert>
                )}

                <div>
                  <div className="text-[11px] font-bold uppercase text-slate-500 mb-1">Plattenbedarf</div>
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-800/40 border-slate-700/30">
                        <TableHead className="text-xs text-slate-400">Material</TableHead>
                        <TableHead className="text-xs text-slate-400 text-right">m2 netto</TableHead>
                        <TableHead className="text-xs text-slate-400 text-right">EUR/m2</TableHead>
                        <TableHead className="text-xs text-slate-400 text-right">Zuschnitt</TableHead>
                        <TableHead className="text-xs text-slate-400 text-right">Summe</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ergebnis.platten.map(p => (
                        <TableRow key={`${p.material}-${p.staerke_mm}`} className="border-slate-700/30">
                          <TableCell className="text-sm py-1.5">{p.material} <span className="text-slate-500">{p.staerke_mm} mm</span></TableCell>
                          <TableCell className="text-sm py-1.5 text-right">{zahl(p.netto_m2, 3)}</TableCell>
                          <TableCell className="text-sm py-1.5 text-right" title={p.preis_quelle}>
                            {zahl(p.preis_m2)}
                            {p.preis_quelle.startsWith('Richtwert') && <span className="ml-1 text-amber-500" aria-label="Richtwert">*</span>}
                          </TableCell>
                          <TableCell className="text-xs py-1.5 text-right text-slate-400">
                            {p.zuschnitt.platten_anzahl} Pl.
                            {p.zuschnitt.platten_anzahl >= 3 && ` / ${zahl(p.zuschnitt.verschnitt_prozent, 0)} %`}
                          </TableCell>
                          <TableCell className="text-sm py-1.5 text-right font-medium">{euro(p.kosten)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="text-[11px] text-slate-500 mt-1">
                    * Richtwert, kein Eintrag in den Materialpreisen. Preis = m2 netto + {ergebnis.platten[0]?.verschnitt_prozent ?? 0} % Verschnitt.
                    Zuschnitt ist eine Schaetzung und fliesst nicht in den Preis ein; Verschnitt laut Zuschnitt erst ab 3 Platten
                    (darunter bleibt der Rest im Lager).
                  </div>
                </div>

                <div>
                  <div className="text-[11px] font-bold uppercase text-slate-500 mb-1">Stueckliste ({k.teile_anzahl} Teile)</div>
                  <div className="max-h-64 overflow-y-auto rounded border border-slate-700/40">
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-slate-800/40 border-slate-700/30">
                          <TableHead className="text-xs text-slate-400">Teil</TableHead>
                          <TableHead className="text-xs text-slate-400 text-right">Anz.</TableHead>
                          <TableHead className="text-xs text-slate-400 text-right">L x B x S (mm)</TableHead>
                          <TableHead className="text-xs text-slate-400">Material</TableHead>
                          <TableHead className="text-xs text-slate-400 text-right">Kante lfm</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {ergebnis.teile.map((t, i) => (
                          <TableRow key={`${t.bezeichnung}-${i}`} className="border-slate-700/30">
                            <TableCell className="text-sm py-1">{t.bezeichnung}</TableCell>
                            <TableCell className="text-sm py-1 text-right">{t.anzahl}</TableCell>
                            <TableCell className="text-sm py-1 text-right font-mono text-slate-300">
                              {zahl(t.laenge_mm, 1)} x {zahl(t.breite_mm, 1)} x {zahl(t.staerke_mm, 1)}
                            </TableCell>
                            <TableCell className="text-xs py-1 text-slate-400">{t.material}</TableCell>
                            <TableCell className="text-sm py-1 text-right">{t.kanten_lfm > 0 ? zahl(t.kanten_lfm) : '-'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <div className="text-[11px] font-bold uppercase text-slate-500 mb-1">Beschlaege</div>
                    <ul className="text-sm space-y-0.5">
                      {ergebnis.beschlaege.map(b => (
                        <li key={b.bezeichnung} className="flex justify-between gap-2">
                          <span className="text-slate-300">{b.anzahl} x {b.bezeichnung}</span>
                          <span className="text-slate-400" title={b.preis_quelle}>{euro(b.kosten)}</span>
                        </li>
                      ))}
                      {ergebnis.beschlaege.length === 0 && <li className="text-slate-500">Keine</li>}
                    </ul>
                  </div>
                  <div>
                    <div className="text-[11px] font-bold uppercase text-slate-500 mb-1">Kanten</div>
                    <ul className="text-sm space-y-0.5">
                      {ergebnis.kanten.map(ka => (
                        <li key={ka.material} className="flex justify-between gap-2">
                          <span className="text-slate-300">{zahl(ka.lfm)} lfm {ka.material}</span>
                          <span className="text-slate-400" title={ka.preis_quelle}>{euro(ka.kosten)}</span>
                        </li>
                      ))}
                      {ergebnis.kanten.length === 0 && <li className="text-slate-500">Keine</li>}
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="px-6 py-3 border-t border-slate-700/60 items-center">
          <span className="text-xs text-slate-500 mr-auto">
            Uebernimmt Platten, Kanten, Beschlaege und Stunden in die Kalkulation. Zuschlaege und Lohnsaetze bleiben wie eingestellt.
          </span>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-slate-600 text-slate-300">
            Abbrechen
          </Button>
          <Button onClick={uebernehmen} disabled={!ergebnis || !!fehler || laedt}
            className="bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-40">
            In Kalkulation uebernehmen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
