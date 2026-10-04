import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, fmt } from '../api/client';
import { challengeText, useScanFlow } from '../app/useScanFlow';
import { useToast } from '../app/providers';
import { PageBanner } from '../components/Shell';
import { ConsentNotice } from '../components/Consent';
import ScanPanel from '../components/ScanPanel';
import { Alert, DataTable, Field, HashText, StatusBadge } from '../components/ui';

const EMPTY = { name: '', ppo_number: '', service_number: '', bank_last4: '', monthly_pension_amount: '' };

function validate(f) {
  const e = {};
  if (f.name.trim().length < 2) e.name = 'Enter the full name as on the ID.';
  if (f.ppo_number.trim().length < 4) e.ppo_number = 'Enter the PPO number (at least 4 characters).';
  if (f.service_number.trim().length < 2) e.service_number = 'Enter the service number.';
  if (!/^\d{4}$/.test(f.bank_last4)) e.bank_last4 = 'Exactly the last 4 digits.';
  if (f.monthly_pension_amount !== '' && !(Number(f.monthly_pension_amount) >= 0)) e.monthly_pension_amount = 'Enter an amount in rupees.';
  return e;
}

export default function RegisterPensioner() {
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [idChecked, setIdChecked] = useState(false);
  const [consent, setConsent] = useState(false);
  const [pensioner, setPensioner] = useState(null);
  const [session, setSession] = useState(null);
  const [approved, setApproved] = useState(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState([]);
  const flow = useScanFlow(session);

  const loadPending = useCallback(() => api('/pensioners?status=PENDING_ENROLLMENT').then(setPending).catch(() => {}), []);
  useEffect(() => { loadPending(); }, [loadPending]);

  // Resume a registration: /officer/register?pensioner=12
  useEffect(() => {
    const id = params.get('pensioner');
    if (id && !pensioner) api(`/pensioners/${id}`).then(setPensioner).catch((e) => setError(e.message));
  }, [params, pensioner]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const createPensioner = async (e) => {
    e.preventDefault();
    const errs = validate(form);
    if (!idChecked) errs.idChecked = 'Confirm you have checked the physical ID in person.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      const created = await api('/pensioners', { method: 'POST', body: {
        ...form, monthly_pension_amount: Number(form.monthly_pension_amount || 0) } });
      const p = await api(`/pensioners/${created.id}`);
      setPensioner(p); setParams({ pensioner: String(p.id) }); loadPending();
    } catch (err) { setError(err.message); }
  };

  const startScan = async () => {
    if (!consent) { setError('The pensioner must read the privacy notice and agree first.'); return; }
    setError('');
    try {
      setSession(await api('/sessions', { method: 'POST', body: { purpose: 'ENROLLMENT', pensioner_id: pensioner.id } }));
    } catch (err) { setError(err.message); }
  };

  const approve = async () => {
    try {
      const res = await api('/enroll/complete', { method: 'POST', body: { pensioner_id: pensioner.id } });
      setApproved(res); toast('Registration approved', 'success', `${res.pensioner.name} is now Active`);
      flow.onEvent({ event: 'ENROLLMENT_APPROVED', ledger_hash: res.ledger_hash });
      loadPending();
    } catch (err) { setError(err.message); }
  };

  const restart = () => {
    setForm(EMPTY); setPensioner(null); setSession(null); setApproved(null); setConsent(false);
    setIdChecked(false); setError(''); setParams({});
  };

  const captured = flow.result && ['captured', 'approved'].includes(flow.result.kind);
  return (
    <>
      <PageBanner title="Register Pensioner" crumbs={[['Officer', '/officer'], ['Register Pensioner']]} />
      <div className="container section stack">
        {error && <Alert kind="danger" title="Something went wrong">{error}</Alert>}

        {!pensioner && (
          <form className="card form" onSubmit={createPensioner} noValidate style={{ maxWidth: 760 }}>
            <h2 style={{ fontSize: '1.4rem' }}>1. Pensioner details</h2>
            <p className="demo-note">Use dummy data for the demo. Never enter Aadhaar numbers.</p>
            <div className="grid grid-2">
              <Field id="name" label="Full name" value={form.name} onChange={set('name')} error={errors.name} />
              <Field id="ppo" label="PPO number (pension ID)" value={form.ppo_number} onChange={set('ppo_number')} error={errors.ppo_number} />
              <Field id="service" label="Service number" value={form.service_number} onChange={set('service_number')} error={errors.service_number} />
              <Field id="last4" label="Bank account: last 4 digits" inputMode="numeric" maxLength={4} value={form.bank_last4}
                onChange={set('bank_last4')} error={errors.bank_last4} />
              <Field id="amount" label="Monthly pension (₹)" inputMode="numeric" value={form.monthly_pension_amount}
                onChange={set('monthly_pension_amount')} error={errors.monthly_pension_amount} />
            </div>
            <label className="check" htmlFor="idcheck">
              <input id="idcheck" type="checkbox" checked={idChecked} onChange={(e) => setIdChecked(e.target.checked)} />
              <span>I have checked the pensioner's physical ID in person.</span>
            </label>
            {errors.idChecked && <div className="field"><div className="error" role="alert">{errors.idChecked}</div></div>}
            <div><button type="submit" className="btn btn-primary">Save and continue</button></div>
          </form>
        )}

        {pensioner && !session && !approved && (
          <div className="card stack" style={{ maxWidth: 760 }}>
            <h2 style={{ fontSize: '1.4rem' }}>2. Face scan for {pensioner.name}</h2>
            <p>PPO <strong>{pensioner.ppo_number}</strong> · <StatusBadge status={pensioner.status} /></p>
            <p>The pensioner scans the QR code with <strong>their own phone</strong>. That phone becomes the only device that can submit their life certificates.</p>
            {pensioner.has_template && pensioner.device && !pensioner.device.active && (
              <Alert kind="info" title="A face scan was already captured for this pensioner">
                Approve it if the pensioner is present and was verified, or take a new scan below.
                <div style={{ marginTop: 10 }}><button type="button" className="btn btn-success btn-small" onClick={approve}>Approve captured scan</button></div>
              </Alert>
            )}
            <ConsentNotice checked={consent} onChange={setConsent} id="reg-consent" who="pensioner" />
            <div className="row">
              <button type="button" className="btn btn-primary" onClick={startScan}>Show QR code</button>
              <button type="button" className="btn btn-secondary" onClick={restart}>Cancel</button>
            </div>
          </div>
        )}

        {session && !approved && (
          <div className="stack">
            <ScanPanel session={session} flow={flow} onRefresh={startScan} instructions={[
              'Pensioner opens the Proof of Life app on their own phone.',
              'Tap “Scan QR code” and point the back camera at this code.',
              'Hold the phone at eye level, follow the prompts and keep still.',
            ]} />
            {captured && (
              <section className="card stack" aria-labelledby="capture-title">
                <h2 id="capture-title" style={{ fontSize: '1.3rem' }}>3. Check and approve</h2>
                <dl className="kv">
                  <dt>Pulse</dt><dd>{fmt.num1(flow.result.bpm)} BPM · signal {fmt.num1(flow.result.snr)} dB</dd>
                  <dt>Face frames used</dt><dd>{flow.result.frames_used ?? '—'}</dd>
                  <dt>Phone key</dt><dd><StatusBadge status={flow.result.key_type} /></dd>
                  {flow.result.challenge_type && <><dt>Challenge</dt><dd>{challengeText(flow.result.challenge_type)}: passed</dd></>}
                </dl>
                <p>Approve only if the person in front of you is the pensioner whose ID you checked.</p>
                <div><button type="button" className="btn btn-success" onClick={approve}>Approve registration</button></div>
              </section>
            )}
            {flow.result?.kind === 'rejected' && (
              <Alert kind="danger" title={`Scan not accepted: ${flow.result.reason}`}>Ask the pensioner to try again in good light.
                <div style={{ marginTop: 10 }}><button type="button" className="btn btn-secondary btn-small" onClick={startScan}>New QR code</button></div>
              </Alert>
            )}
          </div>
        )}

        {approved && (
          <>
            <Alert kind="success" title={`${approved.pensioner.name} is registered and Active`}>
              Their phone key is bound to this pension and recorded on the ledger.
            </Alert>
            <div className="card">
              <dl className="kv">
                <dt>Status</dt><dd><StatusBadge status={approved.pensioner.status} /></dd>
                <dt>Digital ID (DID)</dt><dd className="mono" style={{ fontSize: '0.8rem' }}>{approved.pensioner.did}</dd>
                <dt>Ledger entry</dt><dd><HashText value={approved.ledger_hash} /></dd>
              </dl>
              <div className="row" style={{ marginTop: 16 }}>
                <Link className="btn btn-secondary" to={`/officer/records/${approved.pensioner.id}`}>View record</Link>
                <button type="button" className="btn btn-primary" onClick={restart}>Register another</button>
              </div>
            </div>
          </>
        )}

        {!session && pending.length > 0 && (
          <section aria-labelledby="pending-title">
            <h2 id="pending-title" style={{ fontSize: '1.3rem' }}>Registrations waiting for a face scan</h2>
            <DataTable caption="Pending registrations" rows={pending} columns={[
              { key: 'name', header: 'Name' },
              { key: 'ppo_number', header: 'PPO' },
              { key: 'created_at', header: 'Added', render: (p) => fmt.date(p.created_at) },
              { key: 'actions', header: '', render: (p) => (
                <button type="button" className="btn btn-secondary btn-small"
                  onClick={() => api(`/pensioners/${p.id}`).then((d) => { setPensioner(d); setParams({ pensioner: String(p.id) }); })
                    .catch((e) => setError(e.message))}>Continue</button>) },
            ]} />
          </section>
        )}
      </div>
    </>
  );
}
