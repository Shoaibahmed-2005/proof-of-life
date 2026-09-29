import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import { fmt } from '../api/client';
import { PhonePulse } from './Art';

/* ── Status badge: always text + colour (never colour alone) ────────── */

const BADGES = {
  ACTIVE: ['success', 'Active'],
  ISSUED: ['success', 'Certificate issued'],
  RELEASED: ['success', 'Released'],
  VALID: ['success', 'Valid'],
  UNDER_REVIEW: ['warning', 'Under review'],
  AWAITING_CERTIFICATE: ['warning', 'Awaiting certificate'],
  REJECTED: ['danger', 'Rejected'],
  FROZEN: ['danger', 'Frozen'],
  INVALID: ['danger', 'Tampered'],
  PENDING_ENROLLMENT: ['neutral', 'Pending registration'],
  NOT_REGISTERED: ['neutral', 'Not registered'],
  PENDING: ['neutral', 'Pending'],
  STRONGBOX: ['success', 'Titan M2 StrongBox'],
  TEE: ['info', 'TEE hardware key'],
  SOFTWARE: ['neutral', 'Software key (simulator)'],
  UNKNOWN: ['neutral', 'Unknown key'],
};

export function StatusBadge({ status, label }) {
  const [kind, text] = BADGES[status] || ['neutral', status || '—'];
  return <span className={`badge badge-${kind}`}>{label || text}</span>;
}

/* ── Status stepper ─────────────────────────────────────────────────── */

const STATE_TEXT = { pending: 'Pending', active: 'In progress', done: 'Done', failed: 'Failed', review: 'Needs review' };

export function StatusStepper({ steps }) {
  return (
    <ol className="stepper" style={{ '--steps': steps.length }} aria-label="Progress">
      {steps.map((s, i) => (
        <li key={s.label} className={s.state} aria-current={s.state === 'active' ? 'step' : undefined}>
          <span className="dot" aria-hidden="true">{s.state === 'done' ? '✓' : s.state === 'failed' ? '✕' : s.state === 'review' ? '!' : i + 1}</span>
          <span>
            {s.label}
            <span className="state">{STATE_TEXT[s.state]}{s.note ? ` · ${s.note}` : ''}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/* ── Countdown ──────────────────────────────────────────────────────── */

export function useCountdown(expiresAt) {
  const [left, setLeft] = useState(null);
  useEffect(() => {
    if (!expiresAt) { setLeft(null); return undefined; }
    const end = new Date(expiresAt).getTime();
    const tick = () => setLeft(Math.max(0, Math.round((end - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt]);
  return left;
}

/* ── QR panel ───────────────────────────────────────────────────────── */

export function QrPanel({ qrPayload, expiresAt, steps, onRefresh, done }) {
  const left = useCountdown(expiresAt);
  const [showData, setShowData] = useState(false);
  const expired = left === 0 && !done;
  const value = JSON.stringify(qrPayload);
  return (
    <div className="card qr-panel">
      <div className="qr-box">
        {expired ? (
          <div style={{ width: 260, height: 260, display: 'grid', placeItems: 'center' }}>
            <div>
              <p><strong>This QR code has expired.</strong></p>
              {onRefresh && <button type="button" className="btn btn-primary btn-small" onClick={onRefresh}>Get a new code</button>}
            </div>
          </div>
        ) : (
          <QRCodeSVG value={value} size={260} level="M" marginSize={2} title="Scan this code with the Jeevan Suraksha app" />
        )}
        {!done && left !== null && (
          <div className={`countdown ${expired ? 'expired' : ''}`} aria-live="off">
            {expired ? 'Expired' : `Expires in ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`}
          </div>
        )}
      </div>
      <div>
        <h2 style={{ fontSize: '1.4rem' }}>Scan with your phone</h2>
        <ol className="qr-steps">
          {steps.map((s) => <li key={s}>{s}</li>)}
        </ol>
        <p className="muted" style={{ fontSize: '0.92rem' }}>
          The phone will connect to <strong className="mono">{qrPayload?.base_url || 'this laptop'}</strong>.
          Phone and laptop must be on the same Wi-Fi. <a href="/help#wifi">Trouble connecting?</a>
        </p>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end' }}>
          <PhonePulse width={150} />
          <button type="button" className="copy-btn" onClick={() => setShowData((v) => !v)} aria-expanded={showData}>
            {showData ? 'Hide' : 'Show'} QR data (testing)
          </button>
        </div>
        {showData && (
          <div className="qr-data">
            <label htmlFor="qr-json" className="muted">QR contents, for the phone simulator (backend/scripts/simulate_phone.py --qr '…')</label>
            <textarea id="qr-json" readOnly value={value} onFocus={(e) => e.target.select()} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Copyable hash ──────────────────────────────────────────────────── */

export function HashText({ value, short = true }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="muted">—</span>;
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  return (
    <span className="row" style={{ gap: 8, display: 'inline-flex' }}>
      <span className="mono" title={value}>{short ? fmt.shortHash(value) : value}</span>
      <button type="button" className="copy-btn" onClick={copy} aria-label="Copy full hash">{copied ? 'Copied' : 'Copy'}</button>
    </span>
  );
}

/* ── Certificate card ───────────────────────────────────────────────── */

export function CertificateCard({ name, ppo, year, issuedAt, matchScore, ledgerHash, credentialHash, did, certificateId, reviewed }) {
  return (
    <article className="certificate" aria-labelledby="cert-title">
      <div className="seal" aria-hidden="true">✓<br />VERIFIED</div>
      <div className="cert-head">Life Certificate {year}</div>
      <h2 id="cert-title">{name || 'Pensioner'}</h2>
      <dl>
        {ppo && <><dt>Pension ID</dt><dd>{ppo}</dd></>}
        <dt>Year</dt><dd>{year}</dd>
        <dt>Issued on</dt><dd>{fmt.dateTime(issuedAt)}{reviewed ? ' (approved by an officer)' : ''}</dd>
        <dt>Face match score</dt><dd>{fmt.score(matchScore)}</dd>
        <dt>Ledger entry</dt><dd><HashText value={ledgerHash} /></dd>
        {credentialHash && <><dt>Credential hash</dt><dd><HashText value={credentialHash} /></dd></>}
        {did && <><dt>Pensioner DID</dt><dd className="mono" style={{ fontSize: '0.8rem' }}>{did}</dd></>}
      </dl>
      {certificateId && (
        <p style={{ marginTop: 18, marginBottom: 0 }}>
          <Link className="link-more" to={`/ledger?verify=${certificateId}`}>Verify this certificate on the ledger ›</Link>
        </p>
      )}
    </article>
  );
}

/* ── Data table ─────────────────────────────────────────────────────── */

export function DataTable({ columns, rows, rowKey = 'id', empty = 'Nothing to show yet.', caption }) {
  return (
    <div className="table-wrap">
      <table className="data">
        {caption && <caption className="visually-hidden">{caption}</caption>}
        <thead>
          <tr>{columns.map((c) => <th key={c.key} scope="col" style={{ textAlign: c.align || 'left' }}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td className="empty" colSpan={columns.length}>{empty}</td></tr>
          ) : rows.map((r) => (
            <tr key={r[rowKey]}>
              {columns.map((c) => (
                <td key={c.key} className={c.key === 'actions' ? 'actions' : undefined} style={{ textAlign: c.align || undefined }}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Form field ─────────────────────────────────────────────────────── */

export function Field({ id, label, hint, error, children, ...inputProps }) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <div className={`field ${error ? 'invalid' : ''}`}>
      <label htmlFor={id}>{label}</label>
      {children || <input id={id} aria-invalid={Boolean(error)} aria-describedby={describedBy} {...inputProps} />}
      {hint && <div id={`${id}-hint`} className="hint">{hint}</div>}
      {error && <div id={`${id}-error`} className="error" role="alert">{error}</div>}
    </div>
  );
}

export function Alert({ kind = 'info', title, children }) {
  return (
    <div className={`alert alert-${kind}`} role={kind === 'danger' ? 'alert' : 'status'}>
      <div>
        {title && <h3>{title}</h3>}
        {children && <div>{children}</div>}
      </div>
    </div>
  );
}

export function Loading({ label = 'Loading…' }) {
  return <p className="muted"><span className="spinner" aria-hidden="true" /> {label}</p>;
}
