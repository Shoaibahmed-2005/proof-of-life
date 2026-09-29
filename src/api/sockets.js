import { useEffect, useRef, useState } from 'react';
import { WS_BASE } from './client';

const MAX_RETRIES = 6;
const PING_MS = 25000;

/**
 * Keeps a WebSocket open to `url` while it is non-null, reconnecting with
 * back-off, and calls onEvent(data) for every JSON message.
 * Returns 'idle' | 'connecting' | 'open' | 'closed'.
 */
function useJsonSocket(url, onEvent) {
  const [state, setState] = useState('idle');
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!url) { setState('idle'); return undefined; }
    let ws = null;
    let retries = 0;
    let retryTimer = null;
    let pingTimer = null;
    let stopped = false;

    const open = () => {
      setState('connecting');
      ws = new WebSocket(url);
      ws.onopen = () => {
        retries = 0;
        setState('open');
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
        }, PING_MS);
      };
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.event !== 'pong') handler.current(data);
        } catch { /* ignore non-JSON */ }
      };
      ws.onclose = (e) => {
        clearInterval(pingTimer);
        if (stopped) return;
        // 4001 expired / 4003 forbidden / 4004 unknown: retrying won't help.
        if ([4001, 4003, 4004].includes(e.code) || retries >= MAX_RETRIES) { setState('closed'); return; }
        retries += 1;
        setState('connecting');
        retryTimer = setTimeout(open, Math.min(1000 * 2 ** (retries - 1), 10000));
      };
    };
    open();
    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      clearInterval(pingTimer);
      if (ws) ws.close();
    };
  }, [url]);

  return state;
}

/** Live events for one session (the page showing its QR code). */
export function useSessionSocket(sessionId, onEvent) {
  return useJsonSocket(sessionId ? `${WS_BASE}/ws/${sessionId}` : null, onEvent);
}

/** System-wide events for logged-in officers. */
export function useEventsSocket(token, onEvent) {
  return useJsonSocket(token ? `${WS_BASE}/ws/events?token=${encodeURIComponent(token)}` : null, onEvent);
}
