import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, fmt } from '../api/client';
import { PageBanner } from '../components/Shell';
import { Alert, DataTable, HashText, Loading } from '../components/ui';

const EVENT_TEXT = {
  REGISTRATION_CAPTURED: 'Registration scan captured',
  REGISTRATION_APPROVED: 'Registration approved',
  CERTIFICATE_ISSUED: 'Certificate issued',
  CERTIFICATE_UNDER_REVIEW: 'Sent for review',
  CERTIFICATE_REJECTED: 'Attempt rejected',
  REVIEW_DECISION: 'Officer decision',
  STATUS_CHANGED: 'Pension status changed',
};
const PAGE = 25;

const CHECK_LABEL = {
  signature: 'Signature', issuer: 'Issuer', validity_period: 'Validity period',
  ledger_record: 'Recorded on the ledger', certificate_status: 'Certificate still valid', ledger_chain: 'Ledger chain intact',
};

function CredentialVerifier({ initialId }) {
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const verify = useCallback(async (credential) => {
    setError(''); setResult(null);
    try { setResult(await api('/credentials/verify', { method: 'POST', auth: false, body: { credential } })); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => {
    if (!initialId) return;
    api(`/certificates/${initialId}/credential`, { auth: false })
      .then((c) => { setText(JSON.stringify(c, null, 2)); verify(c); })
      .catch((e) => setError(e.message));
  }, [initialId, verify]);

  const onVerify = () => {
    try { verify(JSON.parse(text)); } catch { setError('That is not valid JSON. Paste the whole credential.'); }
  };

  return (
    <section className="card stack" aria-labelledby="vc-title" id="verify">
      <h2 id="vc-title" style={{ fontSize: '1.3rem' }}>Verify a life-certificate credential</h2>
      <p className="muted">Every issued certificate comes with a digital credential signed by this portal. It names the pensioner only by a pseudonymous digital ID (DID). Anyone, for example a bank, can check it here.</p>
      <div className="field">
        <label htmlFor="vc-json">Credential (JSON)</label>
        <textarea id="vc-json" value={text} onChange={(e) => setText(e.target.value)} className="mono" style={{ minHeight: 160 }} />
      </div>
      <div><button type="button" className="btn btn-primary" onClick={onVerify} disabled={!text.trim()}>Verify credential</button></div>
      {error && <Alert kind="danger" title="Could not verify">{error}</Alert>}
      {result && (
        <>
          <Alert kind={result.valid ? 'success' : 'danger'} title={result.valid ? 'Valid credential' : 'Not valid'}>
            {result.valid ? 'Genuine, issued by this portal, recorded on the ledger, and unchanged.' : 'At least one check failed (see below). Do not rely on this credential.'}
          </Alert>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {Object.entries(result.checks).map(([k, c]) => (
              <li key={k} style={{ padding: '6px 0' }}>
                <span className={`badge ${c.ok ? 'badge-success' : 'badge-danger'}`}>{c.ok ? 'Pass' : 'Fail'}</span>{' '}
                <strong>{CHECK_LABEL[k] || k}</strong>: {c.detail}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export default function Ledger() {
  const [params] = useSearchParams();
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState('');
  const [data, setData] = useState(null);
  const [chain, setChain] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const qs = new URLSearchParams({ offset: String(page * PAGE), limit: String(PAGE) });
    if (filter) qs.set('event_type', filter);
    api(`/ledger?${qs}`, { auth: false }).then(setData).catch((e) => setError(e.message));
  }, [page, filter]);

  const verifyChain = async () => {
    setChecking(true);
    try { setChain(await api('/ledger/verify', { auth: false })); } catch (e) { setError(e.message); } finally { setChecking(false); }
  };

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;
  return (
    <>
      <PageBanner title="Audit Ledger" crumbs={[['Audit Ledger']]} />
      <div className="container section stack">
        <p className="section-lead" style={{ textAlign: 'left', margin: 0 }}>
          Every registration, certificate and status change is recorded here as a <strong>hash</strong>, never personal details. Each entry includes the previous entry's hash, so changing any past record breaks the chain.
        </p>
        <div className="card row" style={{ justifyContent: 'space-between' }}>
          <div>
            <strong>Latest hash (chain head)</strong><br />
            <HashText value={data?.head} short={false} />
            <div className="muted" style={{ fontSize: '0.88rem' }}>This single value can be anchored on a public blockchain (Hyperledger Fabric or Polygon) to prove the whole history.</div>
          </div>
          <button type="button" className="btn btn-primary" onClick={verifyChain} disabled={checking}>
            {checking ? 'Checking…' : 'Verify chain integrity'}
          </button>
        </div>
        {chain && (
          <Alert kind={chain.valid ? 'success' : 'danger'} title={chain.valid ? 'Chain intact' : `Chain broken at entry #${chain.first_bad_entry}`}>
            {chain.message} (checked {fmt.dateTime(chain.checked_at)}).
          </Alert>
        )}
        {error && <Alert kind="danger" title="Could not load">{error}</Alert>}

        <div className="table-toolbar">
          <div className="field" style={{ flex: '0 1 280px' }}>
            <label htmlFor="ledger-filter">Show</label>
            <select id="ledger-filter" value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }}>
              <option value="">All events</option>
              {Object.entries(EVENT_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <span className="muted">{data ? `${data.total} entries` : ''}</span>
        </div>
        {!data ? <Loading /> : (
          <DataTable caption="Ledger entries" rowKey="seq" rows={data.entries} empty="The ledger is empty." columns={[
            { key: 'seq', header: '#', align: 'right' },
            { key: 'created_at', header: 'Time', render: (e) => fmt.dateTime(e.created_at) },
            { key: 'event_type', header: 'Event', render: (e) => EVENT_TEXT[e.event_type] || e.event_type },
            { key: 'ref', header: 'Reference', render: (e) => <span className="mono">{e.ref || '—'}</span> },
            { key: 'entry_hash', header: 'Entry hash', render: (e) => <HashText value={e.entry_hash} /> },
            { key: 'prev_hash', header: 'Previous hash', render: (e) => <span className="mono muted" title={e.prev_hash}>{fmt.shortHash(e.prev_hash)}</span> },
          ]} />
        )}
        <div className="row" style={{ justifyContent: 'center' }}>
          <button type="button" className="btn btn-secondary btn-small" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Newer</button>
          <span>Page {page + 1} of {pages}</span>
          <button type="button" className="btn btn-secondary btn-small" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>Older</button>
        </div>

        <CredentialVerifier initialId={params.get('verify')} />
      </div>
    </>
  );
}
