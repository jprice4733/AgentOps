// In DSS, the SPA runs inside an iframe at a non-root path such as
// /web-apps-backends/PROJECT/WEBAPP_ID/. A bare fetch('/api/...') would
// resolve against the DSS server origin, never reaching FastAPI.
//
// Capture the pathname at module load time — before Vue Router changes it —
// and prepend it to every API path so requests always hit the right backend.

const _isEmbedded = window.self !== window.top
const _base = _isEmbedded ? window.location.pathname.replace(/\/$/, '') : ''

export function apiUrl(path: string): string {
  return _base + path
}
