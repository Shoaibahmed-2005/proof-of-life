import { useState } from 'react';
import { api } from '../api/client';
import { useScanFlow } from '../app/useScanFlow';
import { PageBanner } from '../components/Shell';
import { ConsentNotice } from '../components/Consent';
import ScanPanel from '../components/ScanPanel';
import { Alert } from '../components/ui';
import { PhonePulse } from '../components/Art';

/**
 * Practice scan / device check: an AUTH session, so any phone can test the
 * pulse scan and the Wi-Fi connection without submitting a certificate.
 * (Also used for the Milestone 2 phone tests.)
 */
export default function PracticeScan() {
  const [consent, setConsent] = useState(false);
  const [session, setSession] = useState(null);
  const [error, setError] = useState('');
  const flow = useScanFlow(session);
  const result = flow.result;

  const start = async () => {
    if (!consent) { setError('Please read the privacy notice and tick the box first.'); return; }
    setError('');
    try {
      setSession(await api('/sessions', { method: 'POST', auth: false }));
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="page-pensioner">
      <PageBanner title="Practice scan" crumbs={[['Help & FAQs', '/help'], ['Practice scan']]} />
      <div className="container section">
        {!session ? (
          <div className="grid grid-2" style={{ alignItems: 'center' }}>
            <div className="card stack">
              <h2 style={{ fontSize: '1.5rem' }}>Check your phone before the real thing</h2>
              <p>This measures your pulse exactly like a real life certificate, but <strong>nothing is submitted</strong>. Use it to check that your phone connects to this computer and can read your pulse in your room's light.</p>
              <ConsentNotice checked={consent} onChange={setConsent} id="practice-consent" />
              {error && <Alert kind="danger" title="Can't start">{error}</Alert>}
              <div><button type="button" className="btn btn-primary" onClick={start}>Start practice scan</button></div>
            </div>
            <div className="center"><PhonePulse width={300} /></div>
          </div>
        ) : (
          <div className="stack">
            <ScanPanel session={session} flow={flow} onRefresh={start} instructions={[
              'Open the Proof of Life app and tap “Scan QR code”.',
              'Point the back camera at this code.',
              'Hold the phone at eye level and keep still until it says done.',
            ]} />
            {result?.kind === 'granted' && (
              <Alert kind="success" title="Your phone is ready">Pulse measured and signed by the phone's security chip. You can now submit your life certificate.</Alert>
            )}
            {result?.kind === 'rejected' && (
              <Alert kind="danger" title={result.reason || 'The scan did not complete'}>
                Try brighter, even light on your face, and keep the phone steady. Tap “Diagnostics” on the phone to see why it is slow.
              </Alert>
            )}
            {result && <div><button type="button" className="btn btn-secondary" onClick={start}>Practise again</button></div>}
          </div>
        )}
      </div>
    </div>
  );
}
