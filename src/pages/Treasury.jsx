import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api/client';
import { useEventsSocket } from '../api/sockets';
import { useAuth } from '../app/providers';
import { PageBanner } from '../components/Shell';
import { LedgerChain } from '../components/Art';
import { HighlightStrip } from '../components/sections';
import { Alert, DataTable, Loading, StatusBadge } from '../components/ui';

const ENT_COLORS = { RELEASED: 'var(--accent-green)', AWAITING_CERTIFICATE: 'var(--warning)', FROZEN: 'var(--danger)', NOT_REGISTERED: 'var(--neutral)' };
const ENT_LABEL = { RELEASED: 'Released', AWAITING_CERTIFICATE: 'Awaiting certificate', FROZEN: 'Frozen', NOT_REGISTERED: 'Not registered' };
const REASON_LABEL = { NO_PULSE: 'No pulse (photo?)', FACE_MISMATCH: 'Face mismatch', CHALLENGE_FAILED: 'Challenge failed (video?)', DEVICE_MISMATCH: 'Wrong phone', OTHER: 'Other' };

/** Labelled horizontal bars: value is always shown as text, never colour alone. */
function Bars({ rows, format = (v) => v }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="bars">
      {rows.map((r) => (
        <div className="bar-row" key={r.label}>
          <span>{r.label}</span>
          <div className="bar-track" aria-hidden="true"><div className="bar-fill" style={{ width: `${(100 * r.value) / max}%`, background: r.color }} /></div>
          <span className="num">{format(r.value)}{r.suffix || ''}</span>
        </div>
      ))}
    </div>
  );
}

export default function Treasury() {
  const { token } = useAuth();
  const [t, setT] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(() => api('/treasury/summary').then(setT).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEventsSocket(token, useCallback(() => load(), [load]));

  const ent = t?.entitlements;
  return (
    <>
      <PageBanner title="Treasury Dashboard" crumbs={[['Officer', '/officer'], ['Treasury']]} />
      <div className="container section stack">
        {error && <Alert kind="danger" title="Could not load">{error}</Alert>}
        {!t ? <Loading /> : (
          <>
            <HighlightStrip art={<LedgerChain width={200} />} title={`Pension year ${t.year}`}
              text={`Life certificates are due by ${fmt.date(t.deadline)}. A pension is paid only while a valid certificate exists for the year.`}
              stats={[[fmt.rupees(ent.RELEASED.monthly_amount), 'released per month'], [fmt.rupees(ent.FROZEN.monthly_amount), 'frozen per month'],
                [t.certificates_this_year.issued, 'certificates this year']]} />
            <div className="grid grid-4">
              {[['Active', t.pensioners.active, 'pensions', 'var(--accent-green)'], ['Frozen', t.pensioners.frozen, 'pensions', 'var(--danger)'],
                ['Certificates', t.certificates_this_year.issued, `issued in ${t.year}`, 'var(--primary-dark)'],
                ['Rejected attempts', t.certificates_this_year.rejected_attempts, `${t.certificates_this_year.under_review} under review`, 'var(--text)']].map(([label, value, trend, color]) => (
                <div className="card stat-tile" key={label}>
                  <div className="label">{label}</div>
                  <div className="value" style={{ color }}>{value}</div>
                  <div className="trend muted">{trend}</div>
                </div>
              ))}
            </div>
            <div className="grid grid-2">
              <section className="card" aria-labelledby="released-title">
                <h2 id="released-title" style={{ fontSize: '1.2rem' }}>Monthly pension amount by status</h2>
                <Bars format={fmt.rupees} rows={['RELEASED', 'AWAITING_CERTIFICATE', 'FROZEN'].map((k) => ({
                  label: `${ENT_LABEL[k]} (${ent[k].count})`, value: ent[k].monthly_amount, color: ENT_COLORS[k] }))} />
              </section>
              <section className="card" aria-labelledby="reasons-title">
                <h2 id="reasons-title" style={{ fontSize: '1.2rem' }}>Rejected attempts by reason ({t.year})</h2>
                <Bars rows={Object.entries(t.rejections_by_reason).map(([k, v]) => ({ label: REASON_LABEL[k] || k, value: v, color: 'var(--danger)' }))} />
              </section>
            </div>
            <section aria-labelledby="rows-title">
              <h2 id="rows-title" style={{ fontSize: '1.3rem' }}>Pensions</h2>
              <DataTable caption="Pension entitlements" rowKey="pensioner_id" rows={t.rows} columns={[
                { key: 'name', header: 'Pensioner', render: (r) => <Link to={`/officer/records/${r.pensioner_id}`}>{r.name}</Link> },
                { key: 'ppo_number', header: 'PPO' },
                { key: 'status', header: 'Pension', render: (r) => <StatusBadge status={r.status} /> },
                { key: 'entitlement', header: `Payment ${t.year}`, render: (r) => <StatusBadge status={r.entitlement} /> },
                { key: 'monthly_pension_amount', header: 'Monthly', align: 'right', render: (r) => fmt.rupees(r.monthly_pension_amount) },
                { key: 'latest_certificate_status', header: 'Latest certificate', render: (r) => (r.latest_certificate_status ? <StatusBadge status={r.latest_certificate_status} /> : '—') },
              ]} />
            </section>
          </>
        )}
      </div>
    </>
  );
}
