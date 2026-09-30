'use client';
// Thin fetch wrapper around the FastAPI backend (/api/v1). The bearer token
// lives in localStorage; 401 sends the user back to sign-in, 503 means the
// backend is still warming up (training models on first start).

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const TOKEN_KEY = 'wp_token';
const USER_KEY = 'wp_user';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function safeGet(key) {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
function safeSet(key, val) {
  try { val == null ? window.localStorage.removeItem(key) : window.localStorage.setItem(key, val); } catch { /* private mode */ }
}

export function getToken() { return typeof window === 'undefined' ? null : safeGet(TOKEN_KEY); }
export function getStoredUser() {
  const raw = typeof window === 'undefined' ? null : safeGet(USER_KEY);
  try { return raw ? JSON.parse(raw) : null; } catch { return null; }
}
export function setSession(token, user) { safeSet(TOKEN_KEY, token); safeSet(USER_KEY, user ? JSON.stringify(user) : null); }
export function clearSession() { safeSet(TOKEN_KEY, null); safeSet(USER_KEY, null); }

export async function api(path, { method = 'GET', body, raw = false, signal } = {}) {
  const headers = { Accept: 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined, signal });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(0, `Cannot reach the WeatherPulse server at ${API_BASE}. Is the backend running?`);
  }
  if (res.status === 401 && typeof window !== 'undefined' && !path.startsWith('/auth/')) {
    clearSession();
    window.location.href = '/?expired=1';
    throw new ApiError(401, 'Session expired');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not json */ }
    throw new ApiError(res.status, detail);
  }
  if (raw) return res;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export async function download(path, filename) {
  const res = await api(path, { raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export async function login(username, password) {
  const res = await api('/auth/login', { method: 'POST', body: { username, password } });
  setSession(res.token, res.user);
  return res.user;
}

export async function register(body) {
  const res = await api('/auth/register', { method: 'POST', body });
  setSession(res.token, res.user);
  return res.user;
}

export const HOME_BY_ROLE = {
  official: '/gov',
  institution: '/institution',
  rescue: '/rescue',
  citizen: '/citizen',
  traveller: '/traveller',
};
