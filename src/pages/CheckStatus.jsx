import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api/client';
import { useI18n } from '../app/providers';
import { PageBanner } from '../components/Shell';
import { Alert, DataTable, Field, HashText, StatusBadge } from '../components/ui';

export default function CheckStatus() {
  const { t } = useI18n();
  const [ppo, setPpo] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const lookup = async (e) => {
    e.preventDefault();
    if (ppo.trim().length < 4) { setError('Enter your pension ID (PPO number).'); return; }
    setBusy(true); setError('');
    try {
      setData(await api(`/pensioners/lookup?ppo_number=${encodeURIComponent(ppo.trim())}`, { auth: false }));
    } catch (err) {
      setData(null); setError(err.message);
    } finally { setBusy(false); }
  };

  const year = new Date().getFullYear();
  return (
    <div className="page-pensioner">
      <PageBanner title={t('navStatus')} crumbs={[[t('navStatus')]]} />
      <div className="container section stack">
        <form className="card form" onSubmit={lookup} noValidate style={{ maxWidth: 620 }}>
          <Field id="status-ppo" label={t('pensionId')} value={ppo} onChange={(e) => setPpo(e.target.value)} error={error} autoComplete="off" />
          <div><button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Looking up…' : t('checkCta')}</button></div>
        </form>

        {data && (
          <>
            <section className="card" aria-labelledby="summary-title">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <h2 id="summary-title" style={{ margin: 0 }}>{data.name}</h2>
                <StatusBadge status={data.status} />
              </div>
              <dl className="kv" style={{ marginTop: 16 }}>
                <dt>Pension ID</dt><dd>{data.ppo_number}</dd>
                <dt>Certificate {year}</dt><dd>{data.certificate_this_year ? <StatusBadge status={data.certificate_this_year} /> : 'Not submitted yet'}</dd>
                <dt>Pension payment</dt><dd><StatusBadge status={data.entitlement} /></dd>
                {data.status_reason && <><dt>Note</dt><dd>{data.status_reason}</dd></>}
                {data.did && <><dt>Digital ID (DID)</dt><dd className="mono" style={{ fontSize: '0.8rem' }}>{data.did}</dd></>}
              </dl>
              {data.certificate_this_year !== 'ISSUED' && data.status !== 'PENDING_ENROLLMENT' && (
                <p style={{ marginTop: 16, marginBottom: 0 }}><Link className="btn btn-primary" to="/submit">{t('submitCta')}</Link></p>
              )}
              {data.status === 'FROZEN' && (
                <div style={{ marginTop: 16 }}><Alert kind="danger" title="Your pension is frozen, not cancelled">Please contact your pension office. An officer can restore it after checking with you.</Alert></div>
              )}
            </section>
            <section aria-labelledby="history-title">
              <h2 id="history-title" style={{ fontSize: '1.4rem' }}>Certificate history</h2>
              <DataTable caption="Certificate history" rows={data.certificates} empty="No certificates yet." columns={[
                { key: 'year', header: 'Year' },
                { key: 'created_at', header: 'Date', render: (c) => fmt.dateTime(c.created_at) },
                { key: 'status', header: 'Result', render: (c) => <StatusBadge status={c.status} /> },
                { key: 'reason', header: 'Details', render: (c) => c.reason || (c.status === 'ISSUED' ? 'Verified' : '—') },
                { key: 'ledger_hash', header: 'Ledger record', render: (c) => <HashText value={c.ledger_hash} /> },
              ]} />
            </section>
          </>
        )}
      </div>
    </div>
  );
}
