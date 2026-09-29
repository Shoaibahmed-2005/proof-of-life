import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { useSessionSocket } from '../api/sockets';
import { useToast } from './providers';

/**
 * Drives a QR page from the backend's live events.
 *
 * Step layouts per purpose (indexes used below):
 *   LIFE_CERTIFICATE: Waiting for scan · Measuring pulse · Challenge · Face match · Result
 *   ENROLLMENT:       Waiting for scan · Measuring pulse · Challenge · Face captured · Officer approval
 *   AUTH (practice):  Waiting for scan · Measuring pulse · Result
 */
export const STEP_LABELS = {
  LIFE_CERTIFICATE: ['Waiting for scan', 'Measuring pulse', 'Challenge', 'Face match', 'Result'],
  ENROLLMENT: ['Waiting for scan', 'Measuring pulse', 'Challenge', 'Face captured', 'Officer approval'],
  AUTH: ['Waiting for scan', 'Measuring pulse', 'Result'],
};

const CHALLENGE_TEXT = {
  BLINK_TWICE: 'Blink twice', TURN_LEFT: 'Turn your head left', TURN_RIGHT: 'Turn your head right',
};
export const challengeText = (c) => CHALLENGE_TEXT[c] || c;

// Which step a rejection belongs to.
const FAIL_STEP = {
  NO_PULSE: 1,
  CHALLENGE_FAILED: 2, CHALLENGE_MISMATCH: 2,
  FACE_MISMATCH: 3, DEVICE_MISMATCH: 3, DEVICE_NOT_REGISTERED: 3, MODEL_MISMATCH: 3,
  INVALID_EMBEDDING: 3, INVALID_TEMPLATE: 3, TEMPLATE_MISSING: 3,
};

function initialStates(n) { return Array.from({ length: n }, (_, i) => (i === 0 ? 'active' : 'pending')); }

/** Marks steps [0, upTo) done, `upTo` with `state`, later ones pending. */
function progress(n, upTo, state = 'active') {
  return Array.from({ length: n }, (_, i) => (i < upTo ? 'done' : i === upTo ? state : 'pending'));
}

export function useScanFlow(session) {
  const purpose = session?.purpose || 'AUTH';
  const labels = STEP_LABELS[purpose];
  const n = labels.length;
  const resultIdx = n - 1;
  const [states, setStates] = useState(initialStates(n));
  const [notes, setNotes] = useState({});
  const [live, setLive] = useState(null);       // { bpm, snr, progress, stable }
  const [result, setResult] = useState(null);   // final event payload + kind
  const toast = useToast();
  const sessionId = session?.session_id;
  const doneRef = useRef(false);

  useEffect(() => {
    setStates(initialStates(n)); setNotes({}); setLive(null); setResult(null); doneRef.current = false;
  }, [sessionId, n]);

  const finish = useCallback((kind, ev) => { doneRef.current = true; setResult({ kind, ...ev }); }, []);

  const onEvent = useCallback((ev) => {
    switch (ev.event) {
      case 'CONNECTED':
        if (ev.outcome || (ev.status && !['PENDING', 'PROCESSING'].includes(ev.status))) {
          // Decided before we connected (page reloaded): fetch the result.
          api(`/sessions/${sessionId}`).then((s) => {
            if (s.outcome === 'REJECTED' || s.status === 'REJECTED') {
              setStates(progress(n, FAIL_STEP[s.reason_code] ?? resultIdx, 'failed'));
              finish('rejected', { reason: s.reason, reason_code: s.reason_code });
            }
          }).catch(() => {});
        }
        break;
      case 'SCAN_STARTED':
        setStates(progress(n, 1)); toast('Phone connected', 'info', 'Measuring pulse…');
        break;
      case 'MEASURING':
        setStates((s) => (s[1] === 'done' ? s : progress(n, 1)));
        setLive({ bpm: ev.bpm, snr: ev.snr, progress: ev.progress, stable: ev.stable });
        break;
      case 'STABLE_READING':
        setLive((l) => ({ ...(l || {}), bpm: ev.bpm, snr: ev.snr, stable: true }));
        setStates(progress(n, purpose === 'AUTH' ? 2 : 2));
        toast('Pulse detected', 'success', ev.bpm ? `${Math.round(ev.bpm)} BPM` : '');
        break;
      case 'CHALLENGE_ISSUED':
        setStates(progress(n, 2)); setNotes((x) => ({ ...x, 2: challengeText(ev.challenge_type) }));
        toast('Challenge', 'info', challengeText(ev.challenge_type));
        break;
      case 'CHALLENGE_PASSED':
        setStates(progress(n, 3)); toast('Challenge passed', 'success');
        break;
      case 'CHALLENGE_FAILED':
        setStates(progress(n, 2, 'failed'));
        break;
      case 'FACE_LOST':
        setNotes((x) => ({ ...x, 1: 'Face lost – restarting' }));
        break;
      case 'MULTIPLE_FACES':
        setNotes((x) => ({ ...x, 1: 'More than one face' }));
        break;
      case 'ACCESS_GRANTED':
        setStates(progress(n, n)); finish('granted', ev); toast('Scan verified', 'success', `${Math.round(ev.bpm || 0)} BPM`);
        break;
      case 'CERTIFICATE_ISSUED':
        setStates(progress(n, n)); finish('issued', ev);
        toast(`Life certificate issued for ${ev.year || new Date().getFullYear()}`, 'success');
        break;
      case 'UNDER_REVIEW':
        setStates(progress(n, resultIdx, 'review')); finish('review', ev);
        toast('Sent for officer review', 'warning', ev.reason);
        break;
      case 'ENROLLMENT_CAPTURED':
        setStates(progress(n, 4)); setNotes((x) => ({ ...x, 3: `${ev.frames_used || '—'} frames` }));
        finish('captured', ev); toast('Face captured', 'success', 'Waiting for officer approval');
        break;
      case 'ENROLLMENT_APPROVED':
        setStates(progress(n, n)); finish('approved', ev); toast('Registration approved', 'success');
        break;
      case 'REJECTED': {
        const idx = FAIL_STEP[ev.reason_code] ?? resultIdx;
        setStates(progress(n, purpose === 'AUTH' ? Math.min(idx, resultIdx) : idx, 'failed'));
        finish('rejected', ev);
        toast('Rejected', 'danger', ev.reason);
        break;
      }
      case 'STATUS_CHANGED':
        if (ev.pension_status === 'FROZEN') toast('Pension frozen', 'danger', ev.reason || 'Repeated failed attempts');
        break;
      default:
        break;
    }
  }, [n, purpose, resultIdx, sessionId, toast, finish]);

  const socket = useSessionSocket(sessionId, onEvent);

  // Fallback: if the socket can't stay open, poll the session for its result.
  useEffect(() => {
    if (!sessionId || socket !== 'closed') return undefined;
    const id = setInterval(async () => {
      if (doneRef.current) return;
      try {
        const s = await api(`/sessions/${sessionId}`);
        if (s.status === 'GRANTED') onEvent({ event: 'ACCESS_GRANTED' });
        else if (s.status === 'REJECTED') onEvent({ event: 'REJECTED', reason: s.reason, reason_code: s.reason_code });
        else if (s.outcome === 'ISSUED') onEvent({ event: 'CERTIFICATE_ISSUED', certificate_id: s.certificate_id });
        else if (s.outcome === 'UNDER_REVIEW') onEvent({ event: 'UNDER_REVIEW', reason: s.reason });
        else if (s.outcome === 'CAPTURED') onEvent({ event: 'ENROLLMENT_CAPTURED' });
      } catch { /* keep polling */ }
    }, 4000);
    return () => clearInterval(id);
  }, [sessionId, socket, onEvent]);

  const steps = labels.map((label, i) => ({ label, state: states[i], note: notes[i] }));
  return { steps, live, result, socket, onEvent };
}
