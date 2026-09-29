import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Shield,
  Smartphone,
  ArrowRight,
  RefreshCw,
  CheckCircle2,
  Lock,
  UserCheck,
  LogOut,
  Activity,
  CreditCard,
  Send,
  History,
  Bell,
  AlertCircle,
  Wifi,
  WifiOff,
  ChevronRight,
  ShieldCheck,
  Cpu
} from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';

// Backend address: set VITE_API_BASE in .env.local to override (e.g. http://192.168.1.20:8000/api/v1).
const API_BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws') + '/ws';

// Number of WebSocket reconnect attempts before giving up.
const WS_MAX_RETRIES = 3;
// Heartbeat interval in ms — keeps the connection alive through proxies / NAT.
const WS_HEARTBEAT_INTERVAL_MS = 30_000;

export default function App() {
  const [appStep, setAppStep] = useState(1);
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [wsStatus, setWsStatus] = useState('disconnected'); // 'disconnected' | 'connecting' | 'connected' | 'error'
  const [wsError, setWsError] = useState('');
  const [authData, setAuthData] = useState(null);
  const [countdown, setCountdown] = useState(300);
  const [qrPayload, setQrPayload] = useState(null);   // what the phone scans (backend qr_payload)
  const [liveScan, setLiveScan] = useState(null);     // MEASURING / SCAN_STARTED events from the phone
  const [rejection, setRejection] = useState(null);   // REJECTED event: { reason, reasonCode }
  const [sessionError, setSessionError] = useState('');
  const [sessionExpired, setSessionExpired] = useState(false);

  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const heartbeatRef = useRef(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef(null);
  // Use a ref so ws.onclose always reads the current step, not a stale closure.
  const appStepRef = useRef(appStep);
  useEffect(() => { appStepRef.current = appStep; }, [appStep]);

  // ── Teardown helper ──────────────────────────────────────────────
  const closeAll = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null; // prevent reconnect loop on manual close
      wsRef.current.close();
      wsRef.current = null;
    }
    clearInterval(timerRef.current);
    clearInterval(heartbeatRef.current);
    clearTimeout(retryTimeoutRef.current);
  }, []);

  // Clean up on unmount
  useEffect(() => () => closeAll(), [closeAll]);

  // ── Countdown timer for active QR screen ────────────────────────
  useEffect(() => {
    if (appStep === 2 && sessionId) {
      setCountdown(300);
      setSessionExpired(false);
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timerRef.current);
            setSessionExpired(true);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [appStep, sessionId]);

  // ── WebSocket heartbeat ping ─────────────────────────────────────
  const startHeartbeat = useCallback((ws) => {
    clearInterval(heartbeatRef.current);
    heartbeatRef.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, WS_HEARTBEAT_INTERVAL_MS);
  }, []);

  // ── WebSocket connection with exponential-backoff retry ─────────
  const connectWebSocket = useCallback((id, retryAttempt = 0) => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    setWsStatus('connecting');
    setWsError('');

    try {
      const wsUrl = `${WS_BASE_URL}/${id}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocket] Connection opened for session:', id);
        retryCountRef.current = 0;
        setWsStatus('connected');
        startHeartbeat(ws);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[WebSocket] Received event:', data);

          if (data.event === 'CONNECTED') {
            setWsStatus('connected');
          } else if (data.event === 'SCAN_STARTED') {
            setLiveScan({ started: true });
          } else if (data.event === 'MEASURING' || data.event === 'STABLE_READING') {
            setLiveScan({ started: true, bpm: data.bpm, snr: data.snr, progress: data.progress,
                          stable: data.stable || data.event === 'STABLE_READING' });
          } else if (data.event === 'FACE_LOST') {
            setLiveScan((prev) => ({ ...(prev || {}), faceLost: true }));
          } else if (data.event === 'REJECTED') {
            setRejection({ reason: data.reason || 'Verification failed', reasonCode: data.reason_code });
          } else if (data.event === 'ACCESS_GRANTED') {
            console.log('[WebSocket] Access granted!', data);
            setAuthData({
              bpm: data.bpm || 74,
              deviceId: data.device_id || 'Pixel 7 (Titan M2)',
              grantedAt: data.granted_at || new Date().toISOString()
            });
            setAppStep(3);
          }
        } catch (err) {
          console.error('[WebSocket] Error parsing message:', err);
        }
      };

      ws.onerror = (err) => {
        console.warn('[WebSocket] Error (backend might be offline):', err);
        // onclose will fire next and handle reconnect logic
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Connection closed:', event.code, event.reason);
        clearInterval(heartbeatRef.current);

        // Only attempt reconnect while still on the QR screen
        if (appStepRef.current !== 2) return;

        const attempt = retryCountRef.current;
        if (attempt < WS_MAX_RETRIES) {
          const backoffMs = Math.min(1000 * 2 ** attempt, 8000); // 1s, 2s, 4s, 8s cap
          retryCountRef.current += 1;
          console.log(
            `[WebSocket] Reconnect attempt ${attempt + 1}/${WS_MAX_RETRIES} in ${backoffMs}ms`
          );
          setWsStatus('connecting');
          retryTimeoutRef.current = setTimeout(() => connectWebSocket(id, attempt + 1), backoffMs);
        } else {
          console.warn('[WebSocket] Max retries reached');
          setWsStatus('error');
          setWsError('Lost the live connection to the backend. Refresh the QR code to try again.');
        }
      };
    } catch (err) {
      console.error('[WebSocket] Instantiation failed:', err);
      setWsStatus('error');
    }
  }, [startHeartbeat]);

  // ── Create session + connect WebSocket ───────────────────────────
  const startLoginFlow = useCallback(async () => {
    closeAll();
    retryCountRef.current = 0;
    setLoading(true);
    setWsError('');
    setSessionError('');
    setSessionExpired(false);
    setLiveScan(null);
    setRejection(null);

    try {
      const response = await fetch(`${API_BASE_URL}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        const data = await response.json();
        const activeSessionId = data.session_id;
        setSessionId(activeSessionId);
        setQrPayload(data.qr_payload || { session_id: activeSessionId });
        setAppStep(2);
        setLoading(false);
        connectWebSocket(activeSessionId);
      } else {
        throw new Error(`Server returned HTTP ${response.status}`);
      }
    } catch (error) {
      console.error('[Session API] Could not create a session:', error.message);
      setSessionError(`Cannot reach the backend at ${API_BASE_URL}. Start it with: uvicorn app.main:app --host 0.0.0.0 --port 8000`);
      setLoading(false);
    }
  }, [closeAll, connectWebSocket]);

  const handleRefreshQR = useCallback(() => {
    startLoginFlow();
  }, [startLoginFlow]);

  const handleLogout = useCallback(() => {
    closeAll();
    setAppStep(1);
    setSessionId('');
    setAuthData(null);
    setWsStatus('disconnected');
    setQrPayload(null);
    setLiveScan(null);
    setRejection(null);
    setSessionExpired(false);
  }, [closeAll]);

  const formatCountdown = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div style={{ minHeight: '100vh', width: '100vw', margin: 0, backgroundColor: '#0A0E17', color: '#F8FAFC', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>

      {/* Navigation Header */}
      <header style={{ width: '100%', background: '#1E293B', borderBottom: '1px solid #334155', padding: '16px 36px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxSizing: 'border-box', position: 'sticky', top: 0, zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ background: '#0F172A', padding: '10px', borderRadius: '10px', border: '1px solid #38BDF8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Shield style={{ width: '26px', height: '26px', color: '#38BDF8' }} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ margin: 0, fontSize: '20px', fontWeight: '700', letterSpacing: '0.5px', color: '#FFFFFF' }}>Sentinel-Hard Bank India</h1>
              <span style={{ background: 'rgba(56, 189, 248, 0.15)', border: '1px solid #38BDF8', color: '#38BDF8', fontSize: '11px', padding: '2px 8px', borderRadius: '12px', fontWeight: '600' }}>
                ZERO-TRUST PORTAL
              </span>
            </div>
            <p style={{ margin: 0, fontSize: '12px', color: '#94A3B8' }}>Biometric Hardware Authentication Platform</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
          {appStep === 2 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: '#0F172A', padding: '6px 12px', borderRadius: '20px', border: '1px solid #334155', fontSize: '13px' }}>
              {wsStatus === 'connected' ? (
                <>
                  <Wifi style={{ width: '14px', height: '14px', color: '#10B981' }} />
                  <span style={{ color: '#10B981', fontWeight: '500' }}>WebSocket Live</span>
                </>
              ) : wsStatus === 'connecting' ? (
                <>
                  <RefreshCw className="animate-spin-fast" style={{ width: '14px', height: '14px', color: '#F59E0B' }} />
                  <span style={{ color: '#F59E0B', fontWeight: '500' }}>Connecting...</span>
                </>
              ) : (
                <>
                  <WifiOff style={{ width: '14px', height: '14px', color: '#94A3B8' }} />
                  <span style={{ color: '#94A3B8', fontWeight: '500' }}>Offline Mode</span>
                </>
              )}
            </div>
          )}

          {appStep === 3 && (
            <button
              onClick={handleLogout}
              aria-label="End secure banking session and return to login"
              style={{ background: '#DC2626', border: 'none', borderRadius: '8px', padding: '10px 18px', color: '#F8FAFC', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px', transition: 'all 0.2s', boxShadow: '0 4px 12px rgba(220, 38, 38, 0.3)' }}
            >
              <LogOut style={{ width: '16px', height: '16px' }} /> End Session
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '36px 20px', boxSizing: 'border-box' }}>

        {/* STAGE 1: LOGIN LANDING */}
        {appStep === 1 && (
          <div className="animate-fade-in" style={{ maxWidth: '800px', width: '100%', background: '#1E293B', borderRadius: '20px', border: '1px solid #334155', padding: '52px', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)', boxSizing: 'border-box', textAlign: 'center' }}>
            <div style={{ display: 'inline-flex', padding: '22px', background: 'rgba(56, 189, 248, 0.1)', borderRadius: '50%', marginBottom: '28px', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
              <Lock style={{ width: '48px', height: '48px', color: '#38BDF8' }} />
            </div>

            <h2 style={{ fontSize: '28px', fontWeight: '700', marginBottom: '14px', color: '#F8FAFC', letterSpacing: '-0.5px' }}>
              Cryptographic Netbanking Authentication
            </h2>
            <p style={{ color: '#94A3B8', fontSize: '15px', lineHeight: '1.6', maxWidth: '580px', margin: '0 auto 36px auto' }}>
              Welcome to India's next-generation passwordless netbanking portal. Authenticate seamlessly using your Android device's Titan M2 hardware enclave and live cardiac biometric verification.
            </p>

            {/* Feature Highlights Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '40px', textAlign: 'left' }}>
              <div style={{ background: '#0F172A', padding: '16px 20px', borderRadius: '12px', border: '1px solid #334155' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#38BDF8', fontWeight: '600', marginBottom: '6px' }}>
                  <Cpu style={{ width: '18px', height: '18px' }} /> Titan M2 Enclave
                </div>
                <div style={{ fontSize: '13px', color: '#94A3B8' }}>Hardware-rooted ECDSA cryptographic signatures</div>
              </div>

              <div style={{ background: '#0F172A', padding: '16px 20px', borderRadius: '12px', border: '1px solid #334155' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#10B981', fontWeight: '600', marginBottom: '6px' }}>
                  <Activity style={{ width: '18px', height: '18px' }} /> Cardiac Biometrics
                </div>
                <div style={{ fontSize: '13px', color: '#94A3B8' }}>Real-time PPG heart rate signal validation</div>
              </div>

              <div style={{ background: '#0F172A', padding: '16px 20px', borderRadius: '12px', border: '1px solid #334155' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#A855F7', fontWeight: '600', marginBottom: '6px' }}>
                  <ShieldCheck style={{ width: '18px', height: '18px' }} /> Zero Passwords
                </div>
                <div style={{ fontSize: '13px', color: '#94A3B8' }}>Immune to phishing, replay &amp; credential theft</div>
              </div>
            </div>

            <button
              onClick={startLoginFlow}
              disabled={loading}
              className="animate-pulse-glow"
              aria-label="Initialize a new cryptographic authentication session"
              style={{ background: '#0284C7', color: '#FFF', border: 'none', borderRadius: '10px', padding: '18px 40px', fontSize: '17px', fontWeight: '700', cursor: loading ? 'wait' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: '12px', boxShadow: '0 6px 20px rgba(2, 132, 199, 0.4)', transition: 'all 0.2s' }}
            >
              {loading ? (
                <>
                  <RefreshCw className="animate-spin-fast" style={{ width: '20px', height: '20px' }} /> Creating Session...
                </>
              ) : (
                <>
                  Initialize Cryptographic Session <ArrowRight style={{ width: '20px', height: '20px' }} />
                </>
              )}
            </button>
            {sessionError && (
              <p role="alert" style={{ marginTop: '20px', color: '#FCA5A5', fontSize: '14px' }}>{sessionError}</p>
            )}
          </div>
        )}

        {/* STAGE 2: QR CODE VERIFICATION & WEBSOCKET LISTENER */}
        {appStep === 2 && (
          <div className="animate-fade-in" style={{ maxWidth: '680px', width: '100%', background: '#1E293B', borderRadius: '20px', border: '1px solid #334155', padding: '40px', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)', boxSizing: 'border-box', position: 'relative' }}>

            {/* Session Expired Overlay */}
            {sessionExpired && (
              <div style={{
                position: 'absolute', inset: 0, borderRadius: '20px', zIndex: 20,
                background: 'rgba(10, 14, 23, 0.92)', backdropFilter: 'blur(6px)',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '18px'
              }}>
                <AlertCircle style={{ width: '48px', height: '48px', color: '#EF4444' }} />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '18px', fontWeight: '700', color: '#F8FAFC', marginBottom: '8px' }}>Session Expired</div>
                  <div style={{ fontSize: '14px', color: '#94A3B8' }}>The QR code has expired. Generate a fresh session to continue.</div>
                </div>
                <button
                  onClick={handleRefreshQR}
                  aria-label="Generate a new session and refresh the QR code"
                  style={{ background: '#0284C7', border: 'none', borderRadius: '10px', padding: '14px 28px', color: '#FFF', fontSize: '15px', fontWeight: '700', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '10px', boxShadow: '0 4px 14px rgba(2, 132, 199, 0.4)', transition: 'all 0.2s' }}
                >
                  <RefreshCw style={{ width: '18px', height: '18px' }} /> Refresh Session
                </button>
              </div>
            )}

            <div style={{ background: '#0F172A', padding: '32px', borderRadius: '16px', border: '1px solid #1E293B', textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div style={{ fontSize: '13px', color: '#94A3B8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  Session Expiry: <strong style={{ color: countdown < 60 ? '#EF4444' : '#F59E0B' }}>{formatCountdown(countdown)}</strong>
                </div>
                <button
                  onClick={handleRefreshQR}
                  aria-label="Refresh the QR code and generate a new session"
                  style={{ background: 'rgba(51, 65, 85, 0.5)', border: '1px solid #334155', borderRadius: '8px', padding: '8px 12px', cursor: 'pointer', color: '#94A3B8', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', transition: 'all 0.2s' }}
                  title="Refresh Session &amp; QR Code"
                >
                  <RefreshCw style={{ width: '14px', height: '14px' }} /> Refresh QR
                </button>
              </div>

              <h2 style={{ fontSize: '22px', fontWeight: '700', marginBottom: '8px', color: '#F8FAFC' }}>Device Verification Handshake</h2>
              <p style={{ color: '#94A3B8', fontSize: '14px', marginBottom: '28px', maxWidth: '440px', margin: '0 auto 28px auto' }}>
                Open your verified mobile banking app and scan the QR code to sign the active session payload.
              </p>

              {/* QR Code */}
              <div style={{ background: '#FFFFFF', padding: '24px', display: 'inline-block', borderRadius: '16px', marginBottom: '28px', boxShadow: '0 10px 25px rgba(0, 0, 0, 0.5)', border: '4px solid #38BDF8' }}>
                <QRCodeSVG value={qrPayload ? JSON.stringify(qrPayload) : sessionId} size={260} level="M" includeMargin={false} />
              </div>

              {/* WebSocket Status */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '28px', fontSize: '13px' }}>
                {wsStatus === 'connected' ? (
                  <span style={{ color: '#10B981', display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(16, 185, 129, 0.1)', padding: '6px 14px', borderRadius: '20px', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10B981', display: 'inline-block' }}></span>
                    Listening for mobile verification signal over WebSocket...
                  </span>
                ) : (
                  <span style={{ color: '#F59E0B', display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(245, 158, 11, 0.1)', padding: '6px 14px', borderRadius: '20px', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
                    <AlertCircle style={{ width: '14px', height: '14px' }} />
                    {wsStatus === 'connecting'
                      ? 'Connecting to backend...'
                      : wsError || 'WebSocket disconnected'}
                  </span>
                )}
              </div>

              {/* Live status from the phone (relayed by the backend) */}
              <div role="status" aria-live="polite" style={{ marginBottom: '24px', minHeight: '48px' }}>
                {rejection ? (
                  <div style={{ background: 'rgba(239, 68, 68, 0.12)', border: '1px solid #EF4444', borderRadius: '12px', padding: '14px 18px', color: '#FCA5A5' }}>
                    <div style={{ fontWeight: 700, fontSize: '16px', color: '#EF4444', marginBottom: '6px' }}>Rejected</div>
                    <div style={{ fontSize: '14px' }}>{rejection.reason}</div>
                    <button onClick={handleRefreshQR} style={{ marginTop: '12px', background: '#0284C7', border: 'none', borderRadius: '8px', padding: '10px 18px', color: '#FFF', fontWeight: 700, cursor: 'pointer' }}>
                      Try again
                    </button>
                  </div>
                ) : liveScan ? (
                  <div style={{ fontSize: '15px', color: liveScan.stable ? '#10B981' : '#F8FAFC' }}>
                    {liveScan.faceLost
                      ? 'Face lost: please face the camera'
                      : liveScan.bpm
                      ? `${liveScan.stable ? 'Pulse steady' : 'Measuring pulse…'} ${Math.round(liveScan.bpm)} BPM · signal ${Number(liveScan.snr).toFixed(1)} dB · ${Math.round((liveScan.progress || 0) * 100)}%`
                      : 'Phone connected: measuring pulse…'}
                  </div>
                ) : (
                  <div style={{ fontSize: '14px', color: '#94A3B8' }}>Waiting for the phone to scan…</div>
                )}
              </div>

              <div style={{ fontSize: '12px', color: '#64748B', wordBreak: 'break-all', borderTop: '1px solid #1E293B', paddingTop: '16px' }}>
                Active Session Token: <span style={{ color: '#38BDF8', fontFamily: 'monospace', fontWeight: '600' }}>{sessionId}</span>
              </div>
            </div>
          </div>
        )}

        {/* STAGE 3: ACCOUNT DASHBOARD */}
        {appStep === 3 && (
          <div className="animate-scale-up" style={{ maxWidth: '1000px', width: '100%', boxSizing: 'border-box' }}>

            {/* Live Unlock Telemetry Banner */}
            <div style={{ background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 78, 59, 0.3) 100%)', border: '1px solid rgba(16, 185, 129, 0.4)', padding: '24px 32px', borderRadius: '16px', marginBottom: '28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ background: '#10B981', padding: '12px', borderRadius: '50%', color: '#0F172A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CheckCircle2 style={{ width: '32px', height: '32px' }} />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: '700', color: '#10B981' }}>ACCESS GRANTED — Biometric Session Authenticated</h3>
                  <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#A7F3D0' }}>
                    Titan M2 Signature Verified &amp; Live Cardiac Telemetry Validated
                  </p>
                </div>
              </div>

              {authData && (
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                  <div style={{ background: 'rgba(15, 23, 42, 0.7)', padding: '8px 16px', borderRadius: '10px', border: '1px solid rgba(16, 185, 129, 0.3)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {/* Heartbeat animation on the BPM icon */}
                    <Activity className="animate-heartbeat" style={{ width: '18px', height: '18px' }} />
                    <div>
                      <div style={{ fontSize: '11px', color: '#94A3B8' }}>Live BPM</div>
                      <div style={{ fontSize: '15px', fontWeight: '700', color: '#F8FAFC' }}>{authData.bpm} BPM</div>
                    </div>
                  </div>

                  <div style={{ background: 'rgba(15, 23, 42, 0.7)', padding: '8px 16px', borderRadius: '10px', border: '1px solid rgba(16, 185, 129, 0.3)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Smartphone style={{ width: '18px', height: '18px', color: '#38BDF8' }} />
                    <div>
                      <div style={{ fontSize: '11px', color: '#94A3B8' }}>Verified Device</div>
                      <div style={{ fontSize: '13px', fontWeight: '600', color: '#F8FAFC' }}>{authData.deviceId}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Account Dashboard Content Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px', marginBottom: '28px' }}>

              {/* Account Overview Card */}
              <div style={{ background: '#1E293B', padding: '28px', borderRadius: '16px', border: '1px solid #334155', boxShadow: '0 10px 25px rgba(0,0,0,0.4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <span style={{ fontSize: '14px', color: '#94A3B8', fontWeight: '500' }}>Primary Netbanking Account</span>
                  <span style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10B981', fontSize: '12px', padding: '4px 10px', borderRadius: '12px', fontWeight: '600' }}>ACTIVE</span>
                </div>

                <div style={{ fontSize: '13px', color: '#64748B', marginBottom: '6px' }}>Account No: •••• •••• 8842 (Savings)</div>
                <div style={{ fontSize: '32px', fontWeight: '800', color: '#F8FAFC', marginBottom: '24px', letterSpacing: '-0.5px' }}>
                  ₹ 14,85,250<span style={{ fontSize: '20px', color: '#94A3B8' }}>.00</span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <button
                    aria-label="Make a quick fund transfer"
                    style={{ background: '#0284C7', border: 'none', borderRadius: '8px', padding: '12px', color: '#FFF', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', transition: 'all 0.2s' }}
                  >
                    <Send style={{ width: '14px', height: '14px' }} /> Quick Transfer
                  </button>
                  <button
                    aria-label="Manage cards and UPI settings"
                    style={{ background: '#334155', border: 'none', borderRadius: '8px', padding: '12px', color: '#FFF', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', transition: 'all 0.2s' }}
                  >
                    <CreditCard style={{ width: '14px', height: '14px' }} /> Cards &amp; UPI
                  </button>
                </div>
              </div>

              {/* Security Telemetry & Audit Card */}
              <div style={{ background: '#1E293B', padding: '28px', borderRadius: '16px', border: '1px solid #334155', boxShadow: '0 10px 25px rgba(0,0,0,0.4)' }}>
                <h4 style={{ margin: '0 0 18px 0', fontSize: '16px', fontWeight: '700', color: '#F8FAFC', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShieldCheck style={{ width: '18px', height: '18px', color: '#38BDF8' }} /> Session Security Audit
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '13px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #334155', paddingBottom: '8px' }}>
                    <span style={{ color: '#94A3B8' }}>Cryptographic Scheme</span>
                    <span style={{ color: '#F8FAFC', fontWeight: '600', fontFamily: 'monospace' }}>ECDSA (secp256r1)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #334155', paddingBottom: '8px' }}>
                    <span style={{ color: '#94A3B8' }}>Hardware Root of Trust</span>
                    <span style={{ color: '#10B981', fontWeight: '600' }}>Google Titan M2</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #334155', paddingBottom: '8px' }}>
                    <span style={{ color: '#94A3B8' }}>Biometric Verification</span>
                    <span style={{ color: '#10B981', fontWeight: '600' }}>Cardiac PPG Waveform</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#94A3B8' }}>Session Token</span>
                    <span style={{ color: '#38BDF8', fontWeight: '600', fontFamily: 'monospace' }}>{sessionId || 'ACTIVE-SESSION-GRANTED'}</span>
                  </div>
                </div>
              </div>

            </div>

            {/* Recent Transactions Section */}
            <div style={{ background: '#1E293B', padding: '28px', borderRadius: '16px', border: '1px solid #334155', boxShadow: '0 10px 25px rgba(0,0,0,0.4)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h4 style={{ margin: 0, fontSize: '16px', fontWeight: '700', color: '#F8FAFC', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <History style={{ width: '18px', height: '18px', color: '#38BDF8' }} /> Recent Netbanking Transactions
                </h4>
                <span
                  role="button"
                  tabIndex={0}
                  aria-label="View all transactions"
                  style={{ fontSize: '13px', color: '#38BDF8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                >
                  View All <ChevronRight style={{ width: '14px', height: '14px' }} />
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ background: '#0F172A', padding: '16px 20px', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: '600', fontSize: '14px', color: '#F8FAFC' }}>NEFT Transfer — HDFC Corp</div>
                    <div style={{ fontSize: '12px', color: '#64748B' }}>Today, 14:15 IST • Ref: TXN9812401</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: '700', fontSize: '15px', color: '#EF4444' }}>- ₹ 45,000.00</div>
                    <div style={{ fontSize: '11px', color: '#10B981' }}>COMPLETED</div>
                  </div>
                </div>

                <div style={{ background: '#0F172A', padding: '16px 20px', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: '600', fontSize: '14px', color: '#F8FAFC' }}>Interest Credit — Savings Account</div>
                    <div style={{ fontSize: '12px', color: '#64748B' }}>24 Jul 2026 • Quarterly Interest</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: '700', fontSize: '15px', color: '#10B981' }}>+ ₹ 12,450.00</div>
                    <div style={{ fontSize: '11px', color: '#10B981' }}>CREDITED</div>
                  </div>
                </div>
              </div>
            </div>

          </div>
        )}

      </main>
    </div>
  );
}
