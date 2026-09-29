import { fmt } from '../api/client';
import { QrPanel, StatusStepper } from './ui';

const SOCKET_TEXT = { open: 'Live updates on', connecting: 'Connecting live updates…', closed: 'Live updates off (checking every few seconds)', idle: '' };

/**
 * QR code + live stepper + live pulse line, shared by the Submit, Register
 * and Practice pages. `flow` comes from useScanFlow(session).
 */
export default function ScanPanel({ session, flow, instructions, onRefresh }) {
  const done = Boolean(flow.result);
  const { live } = flow;
  return (
    <div className="stack">
      {!done && (
        <QrPanel qrPayload={session.qr_payload} expiresAt={session.expires_at} steps={instructions}
          onRefresh={onRefresh} done={done} />
      )}
      <section className="card" aria-labelledby="progress-title">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 id="progress-title" style={{ fontSize: '1.3rem', margin: 0 }}>Progress</h2>
          <span className={`socket-state ${flow.socket}`}>{SOCKET_TEXT[flow.socket]}</span>
        </div>
        <StatusStepper steps={flow.steps} />
        {!done && (
          <div className="live-line" aria-live="off">
            {live && live.bpm
              ? `${live.stable ? 'Pulse steady' : 'Measuring pulse…'} ${Math.round(live.bpm)} BPM · signal ${fmt.num1(live.snr)} dB · ${Math.round((live.progress || 0) * 100)}%`
              : 'Waiting for the phone to scan…'}
          </div>
        )}
      </section>
    </div>
  );
}
