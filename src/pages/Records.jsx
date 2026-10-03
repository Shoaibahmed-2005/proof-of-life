import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, fmt } from '../api/client';
import { useToast } from '../app/providers';
import { PageBanner } from '../components/Shell';
import { Alert, DataTable, Field, HashText, Loading, StatusBadge } from '../components/ui';

export function Records() {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async (query, st) => {
    const params = new URLSearchParams();
    if (query) params.set('q', query);
    if (st) params.set('status', st);
    try { setRows(await api(`/pensioners?${params}`)); setError(''); } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { const id = setTimeout(() => load(q, status), 250); return () => clearTimeout(id); }, [q, status, load]);

  return (
    <>
      <PageBanner title="Pensioner Records" crumbs={[['Officer', '/officer'], ['Pensioner Records']]} />
      <div className="container section">
        <div className="table-toolbar" role="search">
          <div style={{ flex: '1 1 280px' }}>
            <Field id="records-q" label="Search name, PPO or service number" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="field" style={{ flex: '0 1 240px' }}>
            <label htmlFor="records-status">Status</label>
            <select id="records-status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="ACTIVE">Active</option>
              <option value="FROZEN">Frozen</option>
              <option value="PENDING_ENROLLMENT">Pending registration</option>
              <option value="REMOVED">Removed</option>
            </select>
          </div>
          <Link className="btn btn-primary" to="/officer/register">Register pensioner</Link>
        </div>
        {error && <Alert kind="danger" title="Could not load">{error}</Alert>}
        {!rows ? <Loading /> : (
          <DataTable caption="Pensioners" rows={rows} empty="No pensioners match." columns={[
            { key: 'name', header: 'Name', render: (p) => <Link to={`/officer/records/${p.id}`}><strong>{p.name}</strong></Link> },
            { key: 'ppo_number', header: 'PPO' },
            { key: 'service_number', header: 'Service no.' },
            { key: 'status', header: 'Status', render: (p) => <StatusBadge status={p.status} /> },
            { key: 'monthly_pension_amount', header: 'Monthly', align: 'right', render: (p) => fmt.rupees(p.monthly_pension_amount) },
            { key: 'actions', header: '', render: (p) => <Link className="btn btn-secondary btn-small" to={`/officer/records/${p.id}`}>Open</Link> },
          ]} />
        )}
      </div>
    </>
  );
}

export function RecordDetail() {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api(`/pensioners/${id}`).then(setP).catch((e) => setError(e.message)); }, [id]);
  const removed = p?.status === 'REMOVED';

  return (
    <>
      <PageBanner title={p ? p.name : 'Pensioner'} crumbs={[['Officer', '/officer'], ['Pensioner Records', '/officer/records'], [p ? p.name : '…']]} />
      <div className="container section stack">
        {error && <Alert kind="danger" title="Could not load">{error}</Alert>}
        {!p && !error && <Loading />}
        {p && (
          <>
            <div className="grid grid-2" style={{ alignItems: 'start' }}>
              <section className="card" aria-labelledby="person-title">
                <h2 id="person-title" style={{ fontSize: '1.3rem' }}>Pensioner</h2>
                <dl className="kv">
                  <dt>Status</dt><dd><StatusBadge status={p.status} />{p.status_reason ? <div className="muted">{p.status_reason}</div> : null}</dd>
                  <dt>PPO</dt><dd>{p.ppo_number}</dd>
                  <dt>Service no.</dt><dd>{p.service_number}</dd>
                  <dt>Bank account</dt><dd>•••• {p.bank_last4}</dd>
                  <dt>Monthly pension</dt><dd>{fmt.rupees(p.monthly_pension_amount)}</dd>
                  <dt>Payment this year</dt><dd><StatusBadge status={p.entitlement} /></dd>
                  <dt>Failed attempts</dt><dd>{p.failed_attempts}</dd>
                  <dt>Registered</dt><dd>{fmt.date(p.created_at)}</dd>
                </dl>
                {p.status === 'PENDING_ENROLLMENT' && (
                  <p style={{ marginTop: 16, marginBottom: 0 }}><Link className="btn btn-primary" to={`/officer/register?pensioner=${p.id}`}>Continue registration</Link></p>
                )}
                {p.status === 'FROZEN' && (
                  <p style={{ marginTop: 16, marginBottom: 0 }}><Link className="btn btn-secondary" to="/officer/reviews">Resolve in Review Queue</Link></p>
                )}
                {removed && (
                  <p className="muted" style={{ marginTop: 16, marginBottom: 0 }}>This record was removed: the face template, phone key and personal details were erased. The pension ID can be registered again as a new pensioner.</p>
                )}
              </section>
              <section className="card" aria-labelledby="security-title">
                <h2 id="security-title" style={{ fontSize: '1.3rem' }}>Device and identity</h2>
                <dl className="kv">
                  <dt>Phone key</dt><dd>{p.device ? <><StatusBadge status={p.device.key_type} /> {p.device.active ? '' : '(awaiting approval)'}</> : '—'}</dd>
                  <dt>Key registered</dt><dd>{p.device ? fmt.date(p.device.registered_at) : '—'}</dd>
                  <dt>Face template</dt><dd>{p.has_template ? `Encrypted · ${p.template_model_version} · updated ${p.template_updates}×` : 'Not captured'}</dd>
                  <dt>DID</dt><dd className="mono" style={{ fontSize: '0.78rem' }}>{p.did || '—'}</dd>
                </dl>
                <p className="muted" style={{ marginTop: 12, marginBottom: 0, fontSize: '0.9rem' }}>No face image is stored: only an encrypted template (numbers) and the phone's public key.</p>
              </section>
            </div>
            <section aria-labelledby="certs-title">
              <h2 id="certs-title" style={{ fontSize: '1.3rem' }}>Certificate history</h2>
              <DataTable caption="Certificate history" rows={p.certificates} empty="No certificate attempts yet." columns={[
                { key: 'created_at', header: 'Date', render: (c) => fmt.dateTime(c.created_at) },
                { key: 'status', header: 'Result', render: (c) => <StatusBadge status={c.status} /> },
                { key: 'match_score', header: 'Match', align: 'right', render: (c) => fmt.score(c.match_score) },
                { key: 'bpm', header: 'Pulse', align: 'right', render: (c) => (c.bpm ? `${fmt.num1(c.bpm)} BPM` : '—') },
                { key: 'reason', header: 'Details', render: (c) => c.reason || '—' },
                { key: 'ledger_hash', header: 'Ledger', render: (c) => <HashText value={c.ledger_hash} /> },
                { key: 'actions', header: '', render: (c) => (c.credential_hash ? <Link to={`/ledger?verify=${c.id}`} className="link-more">Verify ›</Link> : null) },
              ]} />
            </section>
            {!removed && <RemovePensioner pensioner={p} />}
          </>
        )}
      </div>
    </>
  );
}

/**
 * Officer-only removal (e.g. a test registration or a record entered by mistake).
 * The backend erases the face template, the phone key and the personal details,
 * frees the pension ID for a fresh registration, and records the removal on the ledger.
 */
function RemovePensioner({ pensioner }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const remove = async () => {
    if (reason.trim().length < 3) { setError('Please give a reason, for example “Test registration”.'); return; }
    setBusy(true);
    try {
      await api(`/pensioners/${pensioner.id}/remove`, { method: 'POST', body: { reason: reason.trim() } });
      toast('Pensioner removed', 'success', `${pensioner.name} (${pensioner.ppo_number})`);
      navigate('/officer/records');
    } catch (e) { setError(e.message); setBusy(false); }
  };

  return (
    <section className="card" aria-labelledby="remove-title" style={{ borderColor: 'var(--danger)' }}>
      <h2 id="remove-title" style={{ fontSize: '1.2rem' }}>Remove this pensioner</h2>
      {!open ? (
        <>
          <p className="muted">For a test registration or a record entered by mistake. The person can be registered again afterwards.</p>
          <button type="button" className="btn btn-secondary" onClick={() => setOpen(true)}>Remove pensioner…</button>
        </>
      ) : (
        <div className="form">
          <p style={{ margin: 0 }}>This will <strong>permanently erase</strong> for {pensioner.name} ({pensioner.ppo_number}):</p>
          <ul style={{ margin: 0 }}>
            <li>the face template (all stored face data),</li>
            <li>the registered phone key,</li>
            <li>the name, service number and bank digits.</li>
          </ul>
          <p className="muted" style={{ margin: 0 }}>Open QR codes stop working and pending reviews are closed. The audit ledger keeps only hashes, so it stays valid and records this removal. The pension ID becomes free to register again.</p>
          <Field id="remove-reason" label="Reason for removal" value={reason} onChange={(e) => setReason(e.target.value)}
            hint="For example: “Test registration” or “Entered with the wrong PPO number”." error={error} />
          <div className="row">
            <button type="button" className="btn btn-danger" disabled={busy} onClick={remove}>{busy ? 'Removing…' : 'Remove permanently'}</button>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => { setOpen(false); setError(''); }}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}
