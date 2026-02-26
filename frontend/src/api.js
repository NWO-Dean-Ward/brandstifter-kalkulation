/**
 * API-Client fuer das Brandstifter Kalkulationstool.
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
  loeschen: (id) => request(`/projekte/${id}`, { method: 'DELETE' }),
};

// --- Positionen ---
export const positionen = {
  liste: (projektId) => json(`/projekte/${projektId}/positionen/`),
  erstellen: (projektId, data) =>
    json(`/projekte/${projektId}/positionen/`, { method: 'POST', body: JSON.stringify(data) }),
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
