/**
 * API-Client fuer das Meister Eder Kalkulationstool.
 */

const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res;
}

async function json(path, options) {
  const res = await request(path, options);
  return res.json();
}

// --- Projekte ---
export const projekte = {
  liste: () => json('/projekte/'),
  get: (id) => json(`/projekte/${id}`),
  erstellen: (data) => json('/projekte/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => json(`/projekte/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  kopieren: (id) => json(`/projekte/${id}/kopieren`, { method: 'POST' }),
  loeschen: (id) => request(`/projekte/${id}`, { method: 'DELETE' }),
};

// --- Positionen ---
export const positionen = {
  liste: (projektId) => json(`/projekte/${projektId}/positionen/`),
  erstellen: (projektId, data) =>
    json(`/projekte/${projektId}/positionen/`, { method: 'POST', body: JSON.stringify(data) }),
  update: (projektId, posId, data) =>
    json(`/projekte/${projektId}/positionen/${posId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  loeschen: (projektId, posId) =>
    request(`/projekte/${projektId}/positionen/${posId}`, { method: 'DELETE' }),
};

// --- Kalkulation ---
export const kalkulation = {
  starten: (projektId) => json(`/kalkulation/starten/${projektId}`, { method: 'POST' }),
  upload: async (datei, projektId = '') => {
    const form = new FormData();
    form.append('datei', datei);
    if (projektId) form.append('projekt_id', projektId);
    const res = await fetch(`${BASE}/kalkulation/upload`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
};

// --- Export ---
export const exporte = {
  angebotPdf: (projektId) =>
    request(`/export/${projektId}/angebot-pdf`, { method: 'POST' }).then(r => r.blob()),
  internPdf: (projektId) =>
    request(`/export/${projektId}/intern-pdf`, { method: 'POST' }).then(r => r.blob()),
  excel: (projektId) =>
    request(`/export/${projektId}/excel`, { method: 'POST' }).then(r => r.blob()),
  gaeb: (projektId) =>
    request(`/export/${projektId}/gaeb`, { method: 'POST' }).then(r => r.blob()),
  alle: (projektId) =>
    json(`/export/${projektId}/alle`, { method: 'POST' }),
};

// --- Konfiguration ---
export const config = {
  maschinen: {
    get: () => json('/config/maschinen'),
    save: (data) => json('/config/maschinen', { method: 'PUT', body: JSON.stringify(data) }),
  },
  zuschlaege: {
    get: () => json('/config/zuschlaege'),
    save: (data) => json('/config/zuschlaege', { method: 'PUT', body: JSON.stringify(data) }),
  },
  stundensaetze: {
    get: () => json('/config/stundensaetze'),
    save: (data) => json('/config/stundensaetze', { method: 'PUT', body: JSON.stringify(data) }),
  },
};

// --- Materialpreise ---
export const materialpreise = {
  liste: (kategorie = '', suche = '') => {
    const params = new URLSearchParams();
    if (kategorie) params.set('kategorie', kategorie);
    if (suche) params.set('suche', suche);
    const qs = params.toString();
    return json(`/materialpreise/${qs ? '?' + qs : ''}`);
  },
  erstellen: (data) =>
    json('/materialpreise/', { method: 'POST', body: JSON.stringify(data) }),
  importieren: async (datei) => {
    const form = new FormData();
    form.append('datei', datei);
    const res = await fetch(`${BASE}/materialpreise/import`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
};

// --- Werkstuecke ---
export const werkstuecke = {
  liste: (projektId, positionId = null) => {
    const qs = positionId ? `?position_id=${positionId}` : '';
    return json(`/projekte/${projektId}/werkstuecke/${qs}`);
  },
  get: (projektId, id) => json(`/projekte/${projektId}/werkstuecke/${id}`),
  erstellen: (projektId, data) =>
    json(`/projekte/${projektId}/werkstuecke/`, { method: 'POST', body: JSON.stringify(data) }),
  update: (projektId, id, data) =>
    json(`/projekte/${projektId}/werkstuecke/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  loeschen: (projektId, id) =>
    request(`/projekte/${projektId}/werkstuecke/${id}`, { method: 'DELETE' }),
};

// --- Zukaufteile ---
export const zukaufteile = {
  liste: (projektId, positionId = null) => {
    const qs = positionId ? `?position_id=${positionId}` : '';
    return json(`/projekte/${projektId}/zukaufteile/${qs}`);
  },
  get: (projektId, id) => json(`/projekte/${projektId}/zukaufteile/${id}`),
  erstellen: (projektId, data) =>
    json(`/projekte/${projektId}/zukaufteile/`, { method: 'POST', body: JSON.stringify(data) }),
  update: (projektId, id, data) =>
    json(`/projekte/${projektId}/zukaufteile/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  loeschen: (projektId, id) =>
    request(`/projekte/${projektId}/zukaufteile/${id}`, { method: 'DELETE' }),
};

// --- Ueberschreibungen ---
export const ueberschreibungen = {
  liste: (projektId, positionId = null) => {
    const qs = positionId ? `?position_id=${positionId}` : '';
    return json(`/projekte/${projektId}/ueberschreibungen/${qs}`);
  },
  erstellen: (projektId, data) =>
    json(`/projekte/${projektId}/ueberschreibungen/`, { method: 'POST', body: JSON.stringify(data) }),
  loeschen: (projektId, id) =>
    request(`/projekte/${projektId}/ueberschreibungen/${id}`, { method: 'DELETE' }),
};

// --- Einkauf (Preisrecherche) ---
export const einkauf = {
  recherche: (bezeichnung, hersteller = '', artikelNr = '', quellen = 'google_shopping,amazon') =>
    json(`/einkauf/recherche?bezeichnung=${encodeURIComponent(bezeichnung)}&hersteller=${encodeURIComponent(hersteller)}&artikel_nr=${encodeURIComponent(artikelNr)}&quellen=${quellen}`, { method: 'POST' }),
  haefele: (suchbegriff, artikelNr = '') =>
    json(`/einkauf/recherche/haefele?suchbegriff=${encodeURIComponent(suchbegriff)}&artikel_nr=${encodeURIComponent(artikelNr)}`, { method: 'POST' }),
  amazon: (suchbegriff) =>
    json(`/einkauf/recherche/amazon?suchbegriff=${encodeURIComponent(suchbegriff)}`, { method: 'POST' }),
  speichern: (projektId, treffer, positionId = null, aufschlag = 15.0) =>
    json(`/einkauf/speichern/${projektId}?aufschlag_prozent=${aufschlag}${positionId ? '&position_id=' + positionId : ''}`, { method: 'POST', body: JSON.stringify(treffer) }),
  holzTusche: (suchbegriff) =>
    json(`/einkauf/recherche/holz-tusche?suchbegriff=${encodeURIComponent(suchbegriff)}`, { method: 'POST' }),
  holzTuscheSync: () =>
    json('/einkauf/sync/holz-tusche', { method: 'POST' }),
};

// --- Analyse (Altprojekte) ---
export const analyse = {
  scan: (pfad) => json(`/analyse/scan?pfad=${encodeURIComponent(pfad)}`, { method: 'POST' }),
  komplett: (pfad) => json(`/analyse/komplett?pfad=${encodeURIComponent(pfad)}`, { method: 'POST' }),
  inflation: (betrag, datum, rate = 0.04) =>
    json(`/analyse/inflation?betrag=${betrag}&projekt_datum=${datum}&rate=${rate}`, { method: 'POST' }),
  historie: () => json('/analyse/historie'),
  getAnalyse: (id) => json(`/analyse/historie/${id}`),
  smartwopUpload: async (dateien) => {
    const form = new FormData();
    const files = dateien instanceof FileList ? Array.from(dateien) : Array.isArray(dateien) ? dateien : [dateien];
    for (const f of files) {
      form.append('dateien', f);
    }
    const res = await fetch(`${BASE}/analyse/smartwop-upload`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
};

// --- Lernen ---
export const lernen = {
  statistik: () => json('/lernen/statistik'),
  abweichungen: (limit = 10) => json(`/lernen/abweichungen?limit=${limit}`),
  vorschlag: (data) => json('/lernen/vorschlag', { method: 'POST', body: JSON.stringify(data) }),
  plausibilitaet: (projektId, data) =>
    json(`/lernen/${projektId}/plausibilitaet`, { method: 'POST', body: JSON.stringify(data) }),
  istWerte: (projektId, data) =>
    json(`/lernen/${projektId}/ist-werte`, { method: 'POST', body: JSON.stringify(data) }),
};

// --- CNC ---
export const cnc = {
  parseHop: async (datei) => {
    const form = new FormData();
    form.append('datei', datei);
    const res = await fetch(`${BASE}/cnc/parse/hop`, { method: 'POST', body: form });
    if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || `HTTP ${res.status}`); }
    return res.json();
  },
  parseMpr: async (datei) => {
    const form = new FormData();
    form.append('datei', datei);
    const res = await fetch(`${BASE}/cnc/parse/mpr`, { method: 'POST', body: form });
    if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || `HTTP ${res.status}`); }
    return res.json();
  },
  exportHop: (projektId) => json(`/cnc/${projektId}/export/hop`, { method: 'POST' }),
  stueckliste: (projektId) => json(`/cnc/${projektId}/export/stueckliste`, { method: 'POST' }),
  nesting: (projektId, laenge = null, breite = null) => {
    const params = [];
    if (laenge) params.push(`platte_laenge_mm=${laenge}`);
    if (breite) params.push(`platte_breite_mm=${breite}`);
    const qs = params.length ? '?' + params.join('&') : '';
    return json(`/cnc/${projektId}/nesting${qs}`, { method: 'POST' });
  },
  zeitberechnung: (projektId) => json(`/cnc/${projektId}/zeitberechnung`, { method: 'POST' }),
};

// --- Schreiners Buero ---
export const sb = {
  status: () => json('/sb/status'),
  auftragSenden: (projektId) => json(`/sb/${projektId}/auftrag`, { method: 'POST' }),
  auftragStatus: (projektId) => json(`/sb/${projektId}/status`),
  csvUpload: async (datei) => {
    const form = new FormData();
    form.append('datei', datei);
    const res = await fetch(`${BASE}/sb/csv/upload`, { method: 'POST', body: form });
    if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || `HTTP ${res.status}`); }
    return res.json();
  },
};

// --- BildAnalyse ---
export const bildAnalyse = {
  analyse: async (datei, zusatzInfo = '') => {
    const form = new FormData();
    form.append('datei', datei);
    if (zusatzInfo) form.append('zusatz_info', zusatzInfo);
    const res = await fetch(`${BASE}/bild-analyse/analyse`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  analyse3d: async (datei) => {
    const form = new FormData();
    form.append('datei', datei);
    const res = await fetch(`${BASE}/bild-analyse/analyse-3d`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
};

// --- Chat ---
export const chat = {
  message: (data) => json('/chat/message', { method: 'POST', body: JSON.stringify(data) }),
  autoVorschlag: (data) => json('/chat/auto-vorschlag', { method: 'POST', body: JSON.stringify(data) }),
};

// --- Health ---
export const health = () => json('/health');

// Download helper
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
