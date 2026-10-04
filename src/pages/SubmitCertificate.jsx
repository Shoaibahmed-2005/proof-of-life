import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useScanFlow } from '../app/useScanFlow';
import { useI18n } from '../app/providers';
import { PageBanner } from '../components/Shell';
import { ConsentNotice } from '../components/Consent';
import ScanPanel from '../components/ScanPanel';
import { Alert, CertificateCard, Field } from '../components/ui';

const REASON_HELP = {
  NO_PULSE: 'Sit in good, even light, hold the phone steady at eye level and keep still. Then try again.',
  CHALLENGE_FAILED: 'Please do the action shown on your phone (for example "Blink twice") when it appears.',
  FACE_MISMATCH: 'The face did not match the registered pensioner. Only the registered pensioner can submit.',
  DEVICE_MISMATCH: 'Please use the phone that was registered with the officer.',
  MULTIPLE_FACES: 'Only the pensioner may be in front of the camera. Ask others to step away and try again.',
  FACE_NOT_CAPTURED: 'Your face was not captured clearly. Face the camera directly, in good even light, and try again.',
};

export default function SubmitCertificate() {
  const { t } = useI18n();
  const [ppo, setPpo] = useState('');
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState(null);
  const [pensioner, setPensioner] = useState(null);
  const flow = useScanFlow(session);
  const result = flow.result;

  const start = async (e) => {
    e?.preventDefault();
    const errs = {};
    if (ppo.trim().length < 4) errs.ppo = 'Enter your pension ID (PPO number), as printed on your pension papers.';
    if (!consent) errs.consent = 'Please read the privacy notice and tick the box to continue.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const s = await api('/sessions', { method: 'POST', auth: false,
        body: { purpose: 'LIFE_CERTIFICATE', ppo_number: ppo.trim(), consent: true } });
      setSession(s);
      api(`/pensioners/lookup?ppo_number=${encodeURIComponent(ppo.trim())}`, { auth: false })
        .then(setPensioner).catch(() => setPensioner(null));
    } catch (err) {
      setErrors({ ppo: err.message });
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setSession(null); setPensioner(null); };

  // Show the officer-issued certificate details once issued.
  const [cert, setCert] = useState(null);
  useEffect(() => {
    if (result?.kind !== 'issued') { setCert(null); return; }
    api(`/pensioners/lookup?ppo_number=${encodeURIComponent(ppo.trim())}`, { auth: false })
      .then((p) => { setPensioner(p); setCert(p.certificates.find((c) => c.id === result.certificate_id) || null); })
      .catch(() => {});
  }, [result, ppo]);

  return (
    <div className="page-pensioner">
      <PageBanner title={t('navSubmit')} crumbs={[[t('navSubmit')]]} />
      <div className="container section">
        {!session && (
          <div className="grid grid-2" style={{ alignItems: 'start' }}>
            <form className="card form" onSubmit={start} noValidate>
              <h2 style={{ fontSize: '1.5rem' }}>Start your life certificate</h2>
              <Field id="ppo" label={t('pensionId')} value={ppo} onChange={(e) => setPpo(e.target.value)}
                autoComplete="off" hint="Example: PPO-DEF-0001" error={errors.ppo} />
              <ConsentNotice checked={consent} onChange={setConsent} />
              {errors.consent && <div className="field"><div className="error" role="alert">{errors.consent}</div></div>}
              <div><button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Please wait…' : 'Show QR code'}</button></div>
            </form>
            <div className="card stack">
              <h2 style={{ fontSize: '1.3rem' }}>What you need</h2>
              <ul>
                <li>The phone you used when the officer registered you, with the Proof of Life app.</li>
                <li>Good, even light on your face (face a window or lamp, not with it behind you).</li>
                <li>About one minute, sitting still.</li>
              </ul>
              <p className="muted">Not sure your phone works? <Link to="/practice">Try a practice scan</Link> first; it doesn't submit anything.</p>
            </div>
          </div>
        )}

        {session && (
          <div className="stack">
            {pensioner && (
              <p style={{ fontSize: '1.15rem' }}>Submitting for <strong>{pensioner.name}</strong> ({pensioner.ppo_number}), year {new Date().getFullYear()}.</p>
            )}
            <ScanPanel session={session} flow={flow} onRefresh={() => start()} instructions={[
              'Open the Proof of Life app on your registered phone.',
              'Tap “Scan QR code” and point the back camera at this code.',
              'Hold the phone at eye level and follow the prompts. Keep still until it says done.',
            ]} />

            {result?.kind === 'issued' && (
              <>
                <Alert kind="success" title={`Life certificate issued for ${result.year || new Date().getFullYear()}`}>
                  Your pension continues. A copy is recorded on the audit ledger.
                </Alert>
                <CertificateCard name={pensioner?.name} ppo={pensioner?.ppo_number} year={result.year || new Date().getFullYear()}
                  issuedAt={cert?.created_at || result.at} matchScore={result.match_score ?? cert?.match_score}
                  ledgerHash={result.ledger_hash || cert?.ledger_hash} credentialHash={result.credential_hash || cert?.credential_hash}
                  did={result.did || pensioner?.did} certificateId={result.certificate_id} />
              </>
            )}
            {result?.kind === 'review' && (
              <Alert kind="warning" title="Sent to an officer for review">
                {result.reason || 'Your scan needs a quick check by an officer.'} You don't need to do anything now; check back on the <Link to="/status">status page</Link>.
              </Alert>
            )}
            {result?.kind === 'rejected' && (
              <Alert kind="danger" title={`Not accepted: ${result.reason || 'verification failed'}`}>
                {REASON_HELP[result.reason_code] || 'Please try again.'}
              </Alert>
            )}
            {result && (
              <div className="row">
                <button type="button" className="btn btn-secondary" onClick={reset}>{result.kind === 'rejected' ? t('tryAgain') : 'Done'}</button>
                <Link className="btn btn-secondary" to="/status">{t('checkCta')}</Link>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
