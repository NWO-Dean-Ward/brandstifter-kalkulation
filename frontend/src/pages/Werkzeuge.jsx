import { useState, useEffect } from 'react'
import { lernen, cnc, sb, analyse, einkauf } from '../api'
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"

function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}

export default function Werkzeuge() {
  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Werkzeuge</h1>

      <Tabs defaultValue="lernen">
        <TabsList
          variant="line"
          className="border-b border-slate-700/50 bg-transparent rounded-none h-auto p-0 w-full"
        >
          <TabsTrigger
            value="lernen"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3"
          >
            Lernhistorie
          </TabsTrigger>
          <TabsTrigger
            value="cnc"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3"
          >
            CNC
          </TabsTrigger>
          <TabsTrigger
            value="analyse"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3"
          >
            Altprojekte
          </TabsTrigger>
          <TabsTrigger
            value="einkauf"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3"
          >
            Preisrecherche
          </TabsTrigger>
          <TabsTrigger
            value="sb"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-amber-400 data-[state=active]:shadow-none text-slate-400 hover:text-slate-200 px-5 py-3"
          >
            Schreiner's Buero
          </TabsTrigger>
        </TabsList>

        <TabsContent value="lernen" className="mt-4">
          <LernenTab />
        </TabsContent>
        <TabsContent value="cnc" className="mt-4">
          <CNCTab />
        </TabsContent>
        <TabsContent value="analyse" className="mt-4">
          <AnalyseTab />
        </TabsContent>
        <TabsContent value="einkauf" className="mt-4">
          <EinkaufTab />
        </TabsContent>
        <TabsContent value="sb" className="mt-4">
          <SBTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// === LERNEN TAB ===
function LernenTab() {
  const [stats, setStats] = useState(null)
  const [abweichungen, setAbweichungen] = useState(null)
  const [vorschlagInput, setVorschlagInput] = useState({ kurztext: '', material: '', menge: 1 })
  const [vorschlag, setVorschlag] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadStats() }, [])

  const loadStats = async () => {
    setLoading(true)
    try {
      const [s, a] = await Promise.all([
        lernen.statistik(),
        lernen.abweichungen(10),
      ])
      setStats(s)
      setAbweichungen(a)
    } catch (e) {
      console.error('Lernen laden:', e)
    } finally {
      setLoading(false)
    }
  }

  const handleVorschlag = async () => {
    try {
      const res = await lernen.vorschlag(vorschlagInput)
      setVorschlag(res)
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  if (loading) return <div className="text-center py-8 text-slate-400">Lade Lernhistorie...</div>

  return (
    <div className="space-y-6">
      {/* Statistik */}
      <div className="glass-card p-6">
        <h2 className="font-semibold text-slate-200 mb-4">Lernstatistik</h2>
        {stats ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MiniStat label="Projekte gesamt" value={stats.projekte_gesamt ?? 0} />
            <MiniStat label="Positionen erfasst" value={stats.positionen_gesamt ?? 0} />
            <MiniStat label="Durchschn. Abweichung" value={`${(stats.durchschn_abweichung ?? 0).toFixed(1)}%`} />
            <MiniStat label="Gewonnen" value={stats.gewonnen ?? 0} />
          </div>
        ) : (
          <div className="text-slate-400 text-sm">Noch keine Daten vorhanden. Projekte als "abgeschlossen" markieren, um den Lernprozess zu starten.</div>
        )}
      </div>

      {/* Preisvorschlag */}
      <div className="glass-card p-6">
        <h2 className="font-semibold text-slate-200 mb-4">Preisvorschlag (aus Historiedaten)</h2>
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <Label className="text-xs text-slate-400">Kurztext</Label>
            <Input type="text" value={vorschlagInput.kurztext}
              onChange={e => setVorschlagInput({...vorschlagInput, kurztext: e.target.value})}
              placeholder="z.B. Einbauschrank, Kuechenfront..."
              className="border-slate-600 bg-slate-800/60 text-slate-200" />
          </div>
          <div>
            <Label className="text-xs text-slate-400">Material</Label>
            <Input type="text" value={vorschlagInput.material}
              onChange={e => setVorschlagInput({...vorschlagInput, material: e.target.value})}
              placeholder="z.B. Spanplatte, MDF..."
              className="border-slate-600 bg-slate-800/60 text-slate-200" />
          </div>
          <div>
            <Label className="text-xs text-slate-400">Menge</Label>
            <div className="flex gap-2">
              <Input type="number" min="1" value={vorschlagInput.menge}
                onChange={e => setVorschlagInput({...vorschlagInput, menge: parseFloat(e.target.value) || 1})}
                className="border-slate-600 bg-slate-800/60 text-slate-200" />
              <Button onClick={handleVorschlag}
                className="bg-amber-600 hover:bg-amber-700 text-white whitespace-nowrap">
                Vorschlag
              </Button>
            </div>
          </div>
        </div>
        {vorschlag && (
          <div className="bg-slate-800/40 rounded-lg p-4 mt-3">
            <div className="text-sm text-slate-200">
              {vorschlag.vorschlaege?.length > 0 ? (
                vorschlag.vorschlaege.map((v, i) => (
                  <div key={i} className="flex justify-between py-1 border-b border-slate-700/50 last:border-0">
                    <span>{v.position_typ || v.kurztext || 'Position'}</span>
                    <span className="font-medium">{euro(v.vorgeschlagener_preis || v.kalkulierter_preis)}</span>
                  </div>
                ))
              ) : (
                <span className="text-slate-400">Keine aehnlichen Projekte in der Historie gefunden.</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Abweichungen */}
      {abweichungen?.abweichungen?.length > 0 && (
        <div className="glass-card p-6">
          <h2 className="font-semibold text-slate-200 mb-4">Top-Abweichungen (Kalkulation vs. Ist)</h2>
          <Table>
            <TableHeader>
              <TableRow className="border-slate-700/50">
                <TableHead className="text-xs text-slate-400 uppercase">Positionstyp</TableHead>
                <TableHead className="text-xs text-slate-400 uppercase text-right">Kalkuliert</TableHead>
                <TableHead className="text-xs text-slate-400 uppercase text-right">Tatsaechlich</TableHead>
                <TableHead className="text-xs text-slate-400 uppercase text-right">Abweichung</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {abweichungen.abweichungen.map((a, i) => (
                <TableRow key={i} className="border-slate-700/30">
                  <TableCell className="text-sm text-slate-200">{a.position_typ}</TableCell>
                  <TableCell className="text-sm text-right">{euro(a.kalkulierter_preis)}</TableCell>
                  <TableCell className="text-sm text-right">{euro(a.tatsaechlicher_preis)}</TableCell>
                  <TableCell className={`text-sm text-right font-medium ${
                    Math.abs(a.abweichung_prozent) > 15 ? 'text-red-400' : 'text-slate-300'
                  }`}>
                    {a.abweichung_prozent > 0 ? '+' : ''}{a.abweichung_prozent.toFixed(1)}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

// === CNC TAB ===
function CNCTab() {
  const [parseResult, setParseResult] = useState(null)
  const [parsing, setParsing] = useState(false)

  const handleFileUpload = async (e, type) => {
    const file = e.target.files[0]
    if (!file) return
    setParsing(true)
    try {
      const res = type === 'hop' ? await cnc.parseHop(file) : await cnc.parseMpr(file)
      setParseResult({ type, ...res })
    } catch (err) {
      alert('Parse-Fehler: ' + err.message)
    } finally {
      setParsing(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-card p-6">
        <h2 className="font-semibold text-slate-200 mb-4">CNC-Datei analysieren</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-slate-400 block mb-1">HOP-Datei (NCHops)</Label>
            <Input type="file" accept=".hop" onChange={e => handleFileUpload(e, 'hop')}
              className="border-slate-600 bg-slate-800/60 text-slate-200" />
          </div>
          <div>
            <Label className="text-xs text-slate-400 block mb-1">MPR-Datei</Label>
            <Input type="file" accept=".mpr" onChange={e => handleFileUpload(e, 'mpr')}
              className="border-slate-600 bg-slate-800/60 text-slate-200" />
          </div>
        </div>
        {parsing && <div className="mt-3 text-sm text-slate-400">Analysiere...</div>}
      </div>

      {parseResult && (
        <div className="glass-card p-6">
          <h2 className="font-semibold text-slate-200 mb-4">
            Analyse-Ergebnis ({parseResult.type?.toUpperCase()})
          </h2>
          {parseResult.bauteile && (
            <div className="mb-3">
              <div className="text-sm font-medium text-slate-300 mb-2">Bauteile: {parseResult.bauteile.length}</div>
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-700/50">
                    <TableHead className="text-xs text-slate-400 uppercase">Bezeichnung</TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase text-right">L x B (mm)</TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase">Material</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(parseResult.bauteile || []).slice(0, 20).map((b, i) => (
                    <TableRow key={i} className="border-slate-700/30">
                      <TableCell className="text-slate-200">{b.bezeichnung || b.name || '-'}</TableCell>
                      <TableCell className="text-right font-mono text-slate-300">
                        {b.laenge_mm || b.laenge || '-'} x {b.breite_mm || b.breite || '-'}
                      </TableCell>
                      <TableCell className="text-slate-300">{b.material || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {parseResult.bearbeitungen && (
            <div className="text-sm text-slate-300">
              Bearbeitungen: {parseResult.bearbeitungen.length}
              {parseResult.bearbeitungen.slice(0, 5).map((b, i) => (
                <div key={i} className="ml-2 text-xs text-slate-400">
                  {b.typ}: {b.x}/{b.y} {b.durchmesser ? `D${b.durchmesser}` : ''}
                </div>
              ))}
            </div>
          )}
          <pre className="mt-3 bg-slate-800/40 rounded p-3 text-xs text-slate-300 max-h-64 overflow-auto">
            {JSON.stringify(parseResult, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

// === ANALYSE TAB ===
function AnalyseTab() {
  const [pfad, setPfad] = useState('')
  const [result, setResult] = useState(null)
  const [historie, setHistorie] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    analyse.historie().then(setHistorie).catch(() => {})
  }, [])

  const handleScan = async () => {
    if (!pfad.trim()) return
    setLoading(true)
    try {
      const res = await analyse.komplett(pfad.trim())
      setResult(res)
      analyse.historie().then(setHistorie).catch(() => {})
    } catch (e) {
      alert('Analyse-Fehler: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-card p-6">
        <h2 className="font-semibold text-slate-200 mb-4">Altprojekt analysieren</h2>
        <div className="flex gap-3">
          <Input type="text" value={pfad} onChange={e => setPfad(e.target.value)}
            placeholder="D:\Ausschreibung-kalulation-Beispiel\Grundschule Worfelden"
            className="flex-1 border-slate-600 bg-slate-800/60 text-slate-200" />
          <Button onClick={handleScan} disabled={loading || !pfad.trim()}
            className="bg-amber-600 hover:bg-amber-700 disabled:bg-slate-700 disabled:text-slate-500 text-white">
            {loading ? 'Analysiere...' : 'Komplett-Analyse'}
          </Button>
        </div>
      </div>

      {result && (
        <div className="glass-card p-6">
          <h2 className="font-semibold text-slate-200 mb-4">Analyse-Ergebnis</h2>

          {result.scan && (
            <div className="mb-4">
              <div className="text-sm font-medium text-slate-300">
                {result.scan.dateien_gesamt} Dateien gefunden
              </div>
              <div className="flex gap-2 mt-1 flex-wrap">
                {Object.entries(result.scan.typen || {}).map(([typ, count]) => (
                  <Badge key={typ} variant="secondary" className="bg-slate-700 text-slate-400">
                    {typ}: {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {result.excel_analysen?.filter(e => e.status === 'ok').map((excel, i) => (
            <div key={i} className="mb-4 p-3 bg-blue-500/10 rounded-lg">
              <div className="text-sm font-medium text-blue-400">
                Excel: {excel.positionen_anzahl} Positionen, Summe: {euro(excel.gesamtsumme)}
              </div>
            </div>
          ))}

          {result.smartwop_analysen?.filter(s => s.status === 'ok').map((sw, i) => (
            <div key={i} className="mb-4 p-3 bg-green-500/10 rounded-lg">
              <div className="text-sm font-medium text-green-400">
                Smartwop: {sw.csv_dateien} CSVs, {sw.moebel_stuecklisten?.length || 0} Moebel
              </div>
              {sw.materialien_details?.length > 0 && (
                <div className="mt-2 grid grid-cols-3 gap-1">
                  {sw.materialien_details.slice(0, 12).map((m, j) => (
                    <div key={j} className="text-xs text-green-400">
                      {m.code}: {m.egger_name || '?'} ({m.anzahl}x)
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          <pre className="mt-3 bg-slate-800/40 rounded p-3 text-xs text-slate-300 max-h-64 overflow-auto">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}

      {historie.length > 0 && (
        <div className="glass-card p-6">
          <h2 className="font-semibold text-slate-200 mb-4">Analyse-Historie ({historie.length})</h2>
          <Table>
            <TableHeader>
              <TableRow className="border-slate-700/50">
                <TableHead className="text-xs text-slate-400 uppercase">Projekt</TableHead>
                <TableHead className="text-xs text-slate-400 uppercase">Pfad</TableHead>
                <TableHead className="text-xs text-slate-400 uppercase">Datum</TableHead>
                <TableHead className="text-xs text-slate-400 uppercase text-right">Inflation</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {historie.map(h => (
                <TableRow key={h.id} className="border-slate-700/30">
                  <TableCell className="text-slate-200">{h.projekt_name}</TableCell>
                  <TableCell className="text-slate-400 text-xs font-mono truncate max-w-[200px]">{h.quell_pfad}</TableCell>
                  <TableCell className="text-slate-400">{h.analyse_datum?.substring(0, 10)}</TableCell>
                  <TableCell className="text-right text-slate-300">{((h.inflationsfaktor - 1) * 100).toFixed(1)}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

// === EINKAUF TAB ===
function EinkaufTab() {
  const [suchbegriff, setSuchbegriff] = useState('')
  const [quellen, setQuellen] = useState('google_shopping,amazon')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSuche = async () => {
    if (!suchbegriff.trim()) return
    setLoading(true)
    try {
      const res = await einkauf.recherche(suchbegriff.trim(), '', '', quellen)
      setResult(res)
    } catch (e) {
      alert('Recherche-Fehler: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-card p-6">
        <h2 className="font-semibold text-slate-200 mb-4">Preisrecherche</h2>
        <div className="flex gap-3">
          <Input type="text" value={suchbegriff} onChange={e => setSuchbegriff(e.target.value)}
            placeholder="Blum Topfband 71B3550, Haefele Griff..."
            onKeyDown={e => e.key === 'Enter' && handleSuche()}
            className="flex-1 border-slate-600 bg-slate-800/60 text-slate-200" />
          <select value={quellen} onChange={e => setQuellen(e.target.value)}
            className="border border-slate-600 bg-slate-800/60 text-slate-200 rounded-md px-3 py-2 text-sm h-9 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/50">
            <option value="google_shopping,amazon">Google + Amazon</option>
            <option value="haefele">Haefele</option>
            <option value="amazon">Amazon</option>
            <option value="google_shopping">Google Shopping</option>
            <option value="google_shopping,amazon,haefele">Alle</option>
          </select>
          <Button onClick={handleSuche} disabled={loading || !suchbegriff.trim()}
            className="bg-amber-600 hover:bg-amber-700 disabled:bg-slate-700 disabled:text-slate-500 text-white">
            {loading ? 'Suche...' : 'Suchen'}
          </Button>
        </div>
        <div className="mt-2 text-xs text-slate-400">
          Hinweis: Erfordert Playwright (pip install playwright && playwright install chromium)
        </div>
      </div>

      {result && (
        <div className="glass-card p-6">
          <h2 className="font-semibold text-slate-200 mb-4">
            Ergebnisse: {result.anzahl_treffer || 0} Treffer
          </h2>
          {result.treffer?.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700/50">
                  <TableHead className="text-xs text-slate-400 uppercase">Produkt</TableHead>
                  <TableHead className="text-xs text-slate-400 uppercase">Quelle</TableHead>
                  <TableHead className="text-xs text-slate-400 uppercase text-right">Preis</TableHead>
                  <TableHead className="text-xs text-slate-400 uppercase"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.treffer.map((t, i) => (
                  <TableRow key={i} className={`border-slate-700/30 ${i === 0 ? 'bg-green-500/10' : ''}`}>
                    <TableCell className="text-slate-200">{t.titel?.substring(0, 80)}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="bg-slate-700 text-slate-400">
                        {t.quelle}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-medium text-green-400">{euro(t.preis)}</TableCell>
                    <TableCell className="text-right">
                      {t.link && (
                        <a href={t.link} target="_blank" rel="noopener" className="text-xs text-blue-400 hover:underline">
                          Link
                        </a>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-sm text-slate-400">Keine Treffer gefunden.</div>
          )}
          {result.fehler?.length > 0 && (
            <div className="mt-3">
              {result.fehler.map((f, i) => (
                <div key={i} className="text-xs text-red-400">{f.quelle}: {f.fehler}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// === SCHREINERS BUERO TAB ===
function SBTab() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    sb.status()
      .then(setStatus)
      .catch(e => setStatus({ status: 'offline', error: e.message }))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center py-8 text-slate-400">Pruefe Verbindung...</div>

  const isOnline = status?.status === 'ok' || status?.status === 'online'

  return (
    <div className="space-y-6">
      <div className="glass-card p-6">
        <h2 className="font-semibold text-slate-200 mb-4">Schreiner's Buero Status</h2>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className={
            isOnline
              ? 'border-green-500 text-green-400'
              : 'border-red-500 text-red-400'
          }>
            {isOnline ? 'Online' : 'Offline'}
          </Badge>
          <span className="text-sm text-slate-200">
            {isOnline
              ? "Verbunden mit Schreiner's Buero"
              : 'Offline (CSV-Fallback aktiv)'}
          </span>
        </div>
        {status?.api_url && (
          <div className="text-xs text-slate-400 mt-2">API: {status.api_url}</div>
        )}
        {status?.error && (
          <div className="text-xs text-red-400 mt-2">{status.error}</div>
        )}
      </div>

      <div className="glass-card p-6">
        <h2 className="font-semibold text-slate-200 mb-4">CSV Import/Export</h2>
        <div className="text-sm text-slate-300 space-y-2">
          <div>Import: <code className="bg-slate-700/50 px-1 rounded">data/sb_import/</code></div>
          <div>Export: <code className="bg-slate-700/50 px-1 rounded">data/sb_export/</code></div>
          <div className="text-xs text-slate-400 mt-3">
            Auftraege, Stuecklisten und Materialpreise werden automatisch synchronisiert wenn SB online ist.
            Bei Offline-Betrieb: CSV-Dateien manuell in die Import/Export-Ordner legen.
          </div>
        </div>
      </div>
    </div>
  )
}

function MiniStat({ label, value }) {
  return (
    <Card className="bg-slate-800/40 border-slate-700/50 py-0 gap-0">
      <CardContent className="p-3">
        <div className="text-xs text-slate-400">{label}</div>
        <div className="text-lg font-bold text-white">{value}</div>
      </CardContent>
    </Card>
  )
}
