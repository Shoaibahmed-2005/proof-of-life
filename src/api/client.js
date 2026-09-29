/**
 * Backend API client.
 *
 * The backend runs on port 8000 of the same machine that serves the portal
 * (works for localhost and for the laptop's LAN IP). Override with
 * VITE_API_BASE in .env.local, e.g. VITE_API_BASE=http://192.168.1.20:8000/api/v1
 */
export const API_BASE =
  import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
export const WS_BASE = API_BASE.replace(/^http/, 'ws');

const TOKEN_KEY = 'js_officer_token';

export function getToken() {
  try { return window.localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable: token lives only for this page load */ }
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function detailMessage(body, status) {
  const d = body && body.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) {
    return d.map((e) => `${(e.loc || []).slice(-1)[0] || 'field'}: ${e.msg}`).join('; ');
  }
  return `Request failed (${status})`;
}

/** JSON request helper. Adds the officer token when one is stored. */
export async function api(path, { method = 'GET', body, auth = true, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method, headers, signal, body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(0, `Cannot reach the server at ${API_BASE}. Is the backend running?`);
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) throw new ApiError(res.status, detailMessage(data, res.status));
  return data;
}

export const fmt = {
  date: (iso) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'),
  dateTime: (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'),
  rupees: (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`,
  score: (s) => (s === null || s === undefined ? '—' : Number(s).toFixed(2)),
  num1: (n) => (n === null || n === undefined ? '—' : Number(n).toFixed(1)),
  shortHash: (h) => (h ? `${h.slice(0, 10)}…${h.slice(-6)}` : '—'),
};
