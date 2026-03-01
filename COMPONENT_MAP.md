# shadcn/ui Component Map – Brandstifter Kalkulation

> Referenz fuer KI-gestuetzte UI-Entwicklung.
> Nutze AUSSCHLIESSLICH Komponenten aus dieser Map. Kein generisches AI-Design.
> Brand: Amber/Dark Slate, Handwerk-Aesthetik, professionell-pragmatisch.

## Installation

Komponenten einzeln installieren: `npx shadcn@latest add <name>`

---

## Layout & Container

| Komponente | Befehl | Einsatz im Projekt |
|-----------|--------|-------------------|
| **Card** | `add card` | Projekt-Karten, Statistik-Boxen, Positions-Details, Kosten-Uebersichten |
| **Separator** | `add separator` | Visuelle Trennung zwischen Kalkulationsbereichen |
| **Resizable** | `add resizable` | Split-Panels: Kalkulator links / Chat rechts |
| **Scroll Area** | `add scroll-area` | Lange Positionslisten, Material-Tabellen, Chat-Verlauf |
| **Aspect Ratio** | `add aspect-ratio` | Bilder von Werkstuecken/Projekten |
| **Collapsible** | `add collapsible` | Aufklappbare Kalkulationsdetails pro Position |
| **Sidebar** | `add sidebar` | Hauptnavigation, kann bestehende Nav ersetzen |

## Navigation

| Komponente | Befehl | Einsatz im Projekt |
|-----------|--------|-------------------|
| **Tabs** | `add tabs` | Projekt-Tabs (Positionen/Werkstuecke/Zukaufteile/Nachkalkulation), Kalkulator-Modi |
| **Breadcrumb** | `add breadcrumb` | Projekte > Projekt XY > Position 1 |
| **Navigation Menu** | `add navigation-menu` | Hauptmenue als Alternative zur aktuellen Nav |
| **Pagination** | `add pagination` | Projektliste, Materialpreisliste |
| **Menubar** | `add menubar` | Aktionsleiste: Datei/Bearbeiten/Export/Werkzeuge |

## Formulare & Eingaben

| Komponente | Befehl | Einsatz im Projekt |
|-----------|--------|-------------------|
| **Input** | `add input` | Alle Texteingaben (Projektname, Masse, Preise) |
| **Textarea** | `add textarea` | Positionsbeschreibungen, Notizen, GAEB-Langtexte |
| **Select** | `add select` | Materialauswahl, Status-Dropdown, Maschinentyp |
| **Checkbox** | `add checkbox` | Optionen: Lackierung ja/nein, CNC-Bearbeitung |
| **Radio Group** | `add radio-group` | Qualitaetsstufe (Standard/Hochwertig), Berechnungsmodus |
| **Switch** | `add switch` | Toggle: Zuschlaege aktiv/inaktiv, Fremdleistung |
| **Slider** | `add slider` | Gewinnzuschlag %, Wagnis %, Aufschlag-Prozente |
| **Label** | `add label` | Formular-Labels, barrierefrei |
| **Form** | `add form` | Validierte Formulare (react-hook-form + zod) |
| **Input OTP** | `add input-otp` | Partner-Login Verifikation |
| **Calendar** | `add calendar` | Liefertermin, Montageplanung |
| **Date Picker** | _(Calendar + Popover)_ | Angebotsdatum, Lieferdatum |
| **Combobox** | _(Command + Popover)_ | Material-Suche mit Autocomplete, Egger-Dekor-Suche |
| **Toggle** | `add toggle` | Ansichtswechsel (Liste/Kacheln), Editor-Toolbar |
| **Toggle Group** | `add toggle-group` | Mehrfachauswahl: Export-Formate (PDF+Excel+GAEB) |

## Datenanzeige & Tabellen

| Komponente | Befehl | Einsatz im Projekt |
|-----------|--------|-------------------|
| **Table** | `add table` | Positionslisten, Materiallisten, Preistabellen, Nachkalkulation |
| **Data Table** | _(Table + tanstack)_ | Sortierbare/filterbare Projektliste, Materialpreise |
| **Badge** | `add badge` | Status-Labels (Entwurf/Kalkuliert/Angebot/Auftrag/Verloren), Prioritaet |
| **Avatar** | `add avatar` | Monteur-Zuweisung, Bearbeiter-Anzeige |
| **Progress** | `add progress` | Kalkulations-Fortschritt, Upload-Status |
| **Skeleton** | `add skeleton` | Ladezustand fuer Karten, Tabellen, Listen |
| **Chart** | `add chart` | Kosten-Aufteilung (Material/Lohn/Maschine), Projekt-Statistiken |
| **Carousel** | `add carousel` | Projektbilder-Galerie, CNC-Zeichnungen |

## Feedback & Status

| Komponente | Befehl | Einsatz im Projekt |
|-----------|--------|-------------------|
| **Toast / Sonner** | `add sonner` | Erfolg/Fehler-Meldungen (Speichern, Export, Kalkulation) |
| **Alert** | `add alert` | Warnungen (7-Monteure-Limit, fehlende Preise, Offline-Modus) |
| **Alert Dialog** | `add alert-dialog` | Bestaetigung: Projekt loeschen, Position entfernen |
| **Tooltip** | `add tooltip` | Erklaerungen fuer Zuschlagssaetze, CNC-Parameter |
| **Hover Card** | `add hover-card` | Material-Vorschau bei Hover, Dekor-Details |

## Overlays & Modals

| Komponente | Befehl | Einsatz im Projekt |
|-----------|--------|-------------------|
| **Dialog** | `add dialog` | Neue Position anlegen, Materialpreis bearbeiten, Einstellungen |
| **Drawer** | `add drawer` | Mobile: Positionsdetails, Chat-Panel |
| **Sheet** | `add sheet` | Seitenpanel: Positions-Editor, Filter-Panel, Export-Optionen |
| **Popover** | `add popover` | Inline-Bearbeitung, Schnellaktionen, Datepicker-Container |
| **Command** | `add command` | Cmd+K Suche: Projekte/Positionen/Materialien finden |
| **Context Menu** | `add context-menu` | Rechtsklick auf Tabellenzeilen: Bearbeiten/Kopieren/Loeschen |
| **Dropdown Menu** | `add dropdown-menu` | Aktions-Menues: Export-Optionen, Mehr-Aktionen |

## Spezial

| Komponente | Befehl | Einsatz im Projekt |
|-----------|--------|-------------------|
| **Accordion** | `add accordion` | FAQ, Kalkulationsdetails aufklappen, Zuschlagserklaerungen |
| **Empty** | `add empty` | Leerzustand: "Noch keine Positionen", "Keine Projekte" |
| **Kbd** | `add kbd` | Tastaturkuerzel anzeigen (Ctrl+S = Speichern) |
| **Spinner** | `add spinner` | Lade-Indikator bei Kalkulation, Export, LLM-Anfrage |

---

## Komponenten-Empfehlungen nach Feature

### Dashboard / Projektuebersicht
```
Card, Badge, Table, Pagination, Input (Suche),
Select (Status-Filter), Skeleton, Empty, Chart
```

### Kalkulator
```
Tabs, Table, Input, Select, Slider, Switch,
Collapsible, Card, Tooltip, Progress, Sonner,
Sheet (Positions-Editor), Command (Material-Suche)
```

### Ausschreibung / GAEB-Import
```
Card, Textarea, Table, Badge, Progress,
Alert (Parsing-Warnungen), Sonner, Skeleton
```

### Projekt-Editor (Positionen/Werkstuecke/Zukaufteile)
```
Tabs, Table, Dialog (Neu/Bearbeiten), Input, Select,
Checkbox, Context Menu, Alert Dialog (Loeschen),
Badge, Tooltip, Hover Card
```

### Export
```
Toggle Group (Format-Auswahl), Dialog, Progress,
Sonner (Erfolg/Fehler), Badge
```

### Einstellungen
```
Form, Input, Select, Switch, Slider, Separator,
Card, Tabs, Sonner, Alert
```

### Chat / KI-Assistent
```
Scroll Area, Card, Input, Skeleton, Badge,
Drawer (Mobile), Resizable (Desktop Split)
```

### Einkaufs-Agent / Preisrecherche
```
Table, Badge, Progress, Alert, Card,
Hover Card, Sonner, Skeleton
```

---

## Design-Regeln (Anti-AI-Slop)

### VERBOTEN
- Standard-Inter ohne Hierarchie
- Lila/Blau Gradient-Hintergruende
- Uebergrosse Border-Radius (> 1rem)
- Leere "Hero"-Sections ohne Inhalt
- Generische Stock-Icons ohne Kontext

### PFLICHT
- **Schriftgroessen-Hierarchie**: 3-4 klar unterscheidbare Stufen
- **8pt Spacing Grid**: Abstaende immer in 4/8/12/16/24/32px
- **States**: Jede Komponente braucht loading/empty/error/success
- **Responsive**: Mobile-first, ab md: Desktop-Layout
- **a11y**: Labels, Kontrast (WCAG AA), Keyboard-Navigation
- **Brandstifter-Palette**: amber/slate, kein generisches Grau
- **Handwerk-Aesthetik**: Robust, professionell, werkzeug-pragmatisch
- **Dichte Information**: Dashboards/Tabellen duerfen dicht sein, aber lesbar

### Farbpalette (CSS-Variablen)
```css
--primary: #b45309      /* Braun/Amber – Hauptaktion */
--primary-light: #d97706 /* Heller Amber – Hover/Focus */
--accent: #f59e0b       /* Gold – Highlights, aktive States */
--background: #0f172a   /* Dark Navy – Hintergrund */
--surface: #1e293b      /* Slate-800 – Karten/Panels */
--border: #334155       /* Slate-700 – Trennlinien */
--text: #f1f5f9         /* Fast-Weiss – Haupttext */
--text-muted: #94a3b8   /* Slate-400 – Sekundaertext */
--success: #22c55e      /* Gruen – Erfolg/Auftrag */
--danger: #ef4444       /* Rot – Fehler/Loeschen/Verloren */
```

---

## Community-Registries (optional installierbar)

Fuer erweiterte Anforderungen – in `components.json` unter `registries` eintragen:

| Registry | Fokus | Beispiel-Komponenten |
|----------|-------|---------------------|
| `@magicui` | Animationen | Animated Numbers, Sparkles |
| `@shadcnblocks` | Fertige Bloecke | Pricing Tables, Feature Grids |
| `@reui` | Enterprise UI | Advanced Data Tables, Multi-Select |
| `@bundui` | Minimale Varianten | Clean Cards, Simple Forms |

Installation: `npx shadcn@latest add <registry>/<component>`

Beispiel: `npx shadcn@latest add @magicui/animated-number`
