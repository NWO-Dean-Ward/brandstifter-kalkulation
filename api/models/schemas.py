"""
Pydantic-Modelle für die API.

Definiert Request/Response-Schemas für alle Endpunkte.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Projekt ---

class ProjektCreate(BaseModel):
    name: str
    projekt_typ: str = "standard"  # standard | oeffentlich | privat
    kunde: str = ""
    beschreibung: str = ""
    deadline: str = ""


class ProjektUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    kunde: str | None = None
    beschreibung: str | None = None
    deadline: str | None = None


class ProjektResponse(BaseModel):
    id: str
    name: str
    projekt_typ: str
    status: str
    kunde: str
    beschreibung: str
    erstellt_am: str
    aktualisiert_am: str
    deadline: str
    angebotspreis: float
    herstellkosten: float
    marge_prozent: float


# --- Position ---

class PositionCreate(BaseModel):
    pos_nr: str
    kurztext: str = ""
    langtext: str = ""
    menge: float = 0
    einheit: str = "STK"
    material: str = ""
    platten_anzahl: float = 0
    kantenlaenge_lfm: float = 0
    schnittanzahl: int = 0
    bohrungen_anzahl: int = 0


class PositionResponse(BaseModel):
    id: int
    projekt_id: str
    pos_nr: str
    kurztext: str
    langtext: str
    menge: float
    einheit: str
    material: str
    einheitspreis: float
    gesamtpreis: float
    materialkosten: float
    maschinenkosten: float
    lohnkosten: float
    ist_lackierung: bool
    ist_fremdleistung: bool
    fremdleistungskosten: float
    platten_anzahl: float
    kantenlaenge_lfm: float
    schnittanzahl: int
    bohrungen_anzahl: int


# --- Kalkulation ---

class KalkulationRequest(BaseModel):
    projekt_id: str


class KalkulationErgebnis(BaseModel):
    projekt_id: str
    projekt_typ: str
    herstellkosten: float
    materialkosten: float
    maschinenkosten: float
    lohnkosten: float
    gemeinkosten: float
    selbstkosten: float
    gewinn: float
    wagnis: float
    montage_zuschlag: float
    fremdleistungskosten: float
    fremdleistungszuschlag: float
    angebotspreis: float
    marge_prozent: float
    warnungen: list[str] = []


# --- Konfiguration ---

class MaschinenConfig(BaseModel):
    holzher_nextec_7707: dict = {}
    kantenanleimmaschine: dict = {}
    formatkreissaege: dict = {}
    bohrautomat: dict = {}


class ZuschlaegeConfig(BaseModel):
    gemeinkosten_gkz: float = 0.25
    gewinnaufschlag_standard: float = 0.20
    gewinnaufschlag_oeffentlich: float = 0.15
    gewinnaufschlag_privat: float = 0.28
    wagnis_vob: float = 0.03
    montage_baustellenzuschlag: float = 0.12
    fremdleistung_lackierung: float = 0.15
    fremdleistung_montage: float = 0.12


class StundensaetzeConfig(BaseModel):
    einheitlicher_stundensatz: float = 58.0
    monteure_anzahl: int = 7
    montage_stunden_pro_einheit: dict = Field(
        default_factory=lambda: {"min": 4, "max": 6, "standard": 5}
    )


# --- Materialpreisliste ---

class MaterialpreisCreate(BaseModel):
    material_name: str
    kategorie: str = ""
    lieferant: str = ""
    artikel_nr: str = ""
    einheit: str = "STK"
    preis: float
    notizen: str = ""


class MaterialpreisResponse(BaseModel):
    id: int
    material_name: str
    kategorie: str
    lieferant: str
    artikel_nr: str
    einheit: str
    preis: float
    gueltig_ab: str
    gueltig_bis: str
    notizen: str


# --- Upload ---

class UploadResponse(BaseModel):
    datei_name: str
    datei_typ: str
    positionen_anzahl: int
    positionen: list[dict] = []
    warnungen: list[str] = []
