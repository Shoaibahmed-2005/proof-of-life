import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api, getToken, setToken } from '../api/client';
import { STRINGS } from './strings';

/* ── Officer authentication ─────────────────────────────────────────── */

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setTok] = useState(getToken());
  const [officer, setOfficer] = useState(null);
  const [checking, setChecking] = useState(Boolean(getToken()));

  useEffect(() => {
    if (!token) { setOfficer(null); setChecking(false); return; }
    let cancelled = false;
    api('/officers/me')
      .then((o) => { if (!cancelled) setOfficer(o); })
      .catch(() => { if (!cancelled) { setToken(null); setTok(null); } })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
  }, [token]);

  const login = useCallback(async (username, password) => {
    const res = await api('/officers/login', { method: 'POST', body: { username, password }, auth: false });
    setToken(res.access_token);
    setTok(res.access_token);
    setOfficer(res.officer);
    return res.officer;
  }, []);

  const logout = useCallback(() => { setToken(null); setTok(null); setOfficer(null); }, []);

  const value = useMemo(() => ({ token, officer, checking, login, logout }), [token, officer, checking, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

/* ── Toasts + ARIA live announcements ───────────────────────────────── */

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [announcement, setAnnouncement] = useState('');
  const nextId = useRef(1);

  const push = useCallback((title, kind = 'info', detail = '') => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-3), { id, title, kind, detail }]);
    setAnnouncement(`${title}${detail ? `. ${detail}` : ''}`);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-hidden="true">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.title}
            {t.detail && <small>{t.detail}</small>}
          </div>
        ))}
      </div>
      {/* Screen readers hear every status change (DESIGN.md §6). */}
      <div className="visually-hidden" role="status" aria-live="polite">{announcement}</div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/* ── Language (English first, Hindi labels) ─────────────────────────── */

const I18nContext = createContext(null);

function stored(key, fallback) {
  try { return window.localStorage.getItem(key) || fallback; } catch { return fallback; }
}
function store(key, value) {
  try { window.localStorage.setItem(key, value); } catch { /* per-viewer convenience only */ }
}

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(stored('js_lang', 'en'));
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((l) => { setLangState(l); store('js_lang', l); }, []);
  const t = useCallback((key) => (lang === 'hi' && STRINGS.hi[key]) || STRINGS.en[key] || key, [lang]);
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);

/* ── Text size (A− / A / A+) ────────────────────────────────────────── */

export function useTextSize() {
  const [size, setSizeState] = useState(stored('js_text_size', 'normal'));
  useEffect(() => { document.documentElement.dataset.textSize = size; }, [size]);
  const setSize = useCallback((s) => { setSizeState(s); store('js_text_size', s); }, []);
  return [size, setSize];
}
