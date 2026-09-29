import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api/client';
import { useEventsSocket } from '../api/sockets';
import { challengeText } from '../app/useScanFlow';
import { useAuth, useToast } from '../app/providers';
import { PageBanner } from '../components/Shell';
import { Alert, DataTable, Field, Loading, StatusBadge } from '../components/ui';

function Drawer({ title, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabIndex={-1} ref={ref}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 id="drawer-title" style={{ fontSize: '1.3rem', margin: 0 }}>{title}</h2>
          <button type="button" className="copy-btn" onClick={onClose}>Close</button>
        </div>
        {children}
      </div>
    </>
  );
}

export default function ReviewQueue() {
  const { token } = useAuth();
  const toast = useToast();
  const [items, setItems] = useState(null);
  const [frozen, setFrozen] = useState([]);
  const [open, setOpen] = useState(null);       // review item or { frozen: pensioner }
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, f] = await Promise.all([api('/reviews'), api('/reviews/frozen')]);
      setItems(r); setFrozen(f);
    } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEventsSocket(token, useCallback((ev) => {
    if (['UNDER_REVIEW', 'STATUS_CHANGED', 'CERTIFICATE_ISSUED', 'REJECTED'].includes(ev.event)) load();
  }, [load]));

  const close = useCallback(() => { setOpen(null); setReason(''); setError(''); }, []);

  const decide = async (decision) => {
    if (reason.trim().length < 3) { setError('Please give a short reason (at least 3 characters).'); return; }
    setBusy(true);
    try {
      await api(`/reviews/${open.id}/decision`, { method: 'POST', body: { decision, reason: reason.trim() } });
      toast(decision === 'APPROVE' ? 'Certificate issued' : 'Certificate rejected', decision === 'APPROVE' ? 'success' : 'danger', open.pensioner_name);
      close(); load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const restore = async () => {
    if (reason.trim().length < 3) { setError('Please record how the case was resolved.'); return; }
    setBusy(true);
    try {
      await api(`/reviews/frozen/${open.frozen.id}/restore`, { method: 'POST', body: { reason: reason.trim() } });
      toast('Pension restored', 'success', open.frozen.name);
      close(); load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageBanner title="Review Queue" crumbs={[['Officer', '/officer'], ['Review Queue']]} />
      <div className="container section stack">
        {error && !open && <Alert kind="danger" title="Could not load">{error}</Alert>}
        <section aria-labelledby="borderline-title">
          <h2 id="borderline-title" style={{ fontSize: '1.4rem' }}>Borderline life certificates</h2>
          <p className="muted">Scans that were live but whose face match was not clearly strong enough (for example because of ageing, lighting or pose), or that came from a frozen pension.</p>
          {!items ? <Loading /> : (
            <DataTable caption="Certificates under review" rows={items} empty="Nothing to review. 🎉" columns={[
              { key: 'pensioner_name', header: 'Pensioner', render: (r) => <><strong>{r.pensioner_name}</strong><br /><span className="muted">{r.ppo_number}</span></> },
              { key: 'created_at', header: 'Submitted', render: (r) => fmt.dateTime(r.created_at) },
              { key: 'match_score', header: 'Match score', align: 'right', render: (r) => fmt.score(r.match_score) },
              { key: 'bpm', header: 'Pulse', align: 'right', render: (r) => `${fmt.num1(r.bpm)} BPM` },
              { key: 'reason', header: 'Why', render: (r) => r.reason },
              { key: 'actions', header: '', render: (r) => <button type="button" className="btn btn-primary btn-small" onClick={() => setOpen(r)}>Review</button> },
            ]} />
          )}
        </section>

        <section aria-labelledby="frozen-title">
          <h2 id="frozen-title" style={{ fontSize: '1.4rem' }}>Frozen pensions</h2>
          <p className="muted">Frozen after repeated failed attempts or a missed deadline. Frozen means paused, never cancelled: restore once you have resolved the case with the pensioner.</p>
          <DataTable caption="Frozen pensions" rows={frozen.map((f) => f.pensioner)} empty="No frozen pensions." columns={[
            { key: 'name', header: 'Pensioner', render: (p) => <Link to={`/officer/records/${p.id}`}>{p.name}</Link> },
            { key: 'ppo_number', header: 'PPO' },
            { key: 'status_reason', header: 'Reason' },
            { key: 'failed_attempts', header: 'Failed attempts', align: 'right' },
            { key: 'actions', header: '', render: (p) => <button type="button" className="btn btn-secondary btn-small" onClick={() => setOpen({ frozen: p, recent: frozen.find((f) => f.pensioner.id === p.id)?.recent_certificates || [] })}>Restore…</button> },
          ]} />
        </section>
      </div>

      {open && !open.frozen && (
        <Drawer title={`Review: ${open.pensioner_name}`} onClose={close}>
          <dl style={{ marginTop: 16 }}>
            <dt>PPO</dt><dd>{open.ppo_number}</dd>
            <dt>Pension status</dt><dd><StatusBadge status={open.pensioner_status} /></dd>
            <dt>Match score</dt><dd>{fmt.score(open.match_score)} (vs original registration {fmt.score(open.anchor_score)})</dd>
            <dt>Pulse</dt><dd>{fmt.num1(open.bpm)} BPM</dd>
            <dt>Signal (SNR)</dt><dd>{fmt.num1(open.snr)} dB</dd>
            <dt>Challenge</dt><dd>{open.challenge_type ? `${challengeText(open.challenge_type)}: ${open.challenge_passed ? 'passed' : 'failed'}` : '—'}</dd>
            <dt>Phone key</dt><dd><StatusBadge status={open.key_type || 'UNKNOWN'} /></dd>
            <dt>Why review</dt><dd>{open.reason}</dd>
          </dl>
          <div className="form" style={{ marginTop: 20 }}>
            <Field id="review-reason" label="Reason for your decision" value={reason} onChange={(e) => setReason(e.target.value)}
              hint="For example: “Verified by video call; poor lighting in the scan.”" error={error} />
            <div className="row">
              <button type="button" className="btn btn-success" disabled={busy} onClick={() => decide('APPROVE')}>Approve</button>
              <button type="button" className="btn btn-danger" disabled={busy} onClick={() => decide('REJECT')}>Reject</button>
            </div>
          </div>
        </Drawer>
      )}

      {open?.frozen && (
        <Drawer title={`Restore: ${open.frozen.name}`} onClose={close}>
          <p style={{ marginTop: 16 }}>{open.frozen.status_reason}</p>
          <h3 style={{ fontSize: '1.05rem' }}>Recent attempts</h3>
          <ul>
            {open.recent.map((c) => <li key={c.id}>{fmt.dateTime(c.created_at)}: <StatusBadge status={c.status} /> {c.reason_code || ''}</li>)}
          </ul>
          <div className="form" style={{ marginTop: 20 }}>
            <Field id="restore-reason" label="How was this resolved?" value={reason} onChange={(e) => setReason(e.target.value)}
              hint="For example: “Met the pensioner in person; the failed attempts were a demo.”" error={error} />
            <div><button type="button" className="btn btn-success" disabled={busy} onClick={restore}>Restore pension</button></div>
          </div>
        </Drawer>
      )}
    </>
  );
}
