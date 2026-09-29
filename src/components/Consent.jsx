/**
 * Consent notice shown before any scan starts (build-prompt §6, §7).
 * The backend also requires `consent: true` to create a life-certificate
 * session, and the phone records consent in the signed payload.
 */
export function ConsentNotice({ checked, onChange, id = 'consent', who = 'I' }) {
  return (
    <div className="consent">
      <h3>Before you scan: your privacy</h3>
      <ul>
        <li>Your phone measures your pulse from the camera and compares your face with the one registered by the officer.</li>
        <li><strong>No photo or video of you is saved or sent.</strong> Only a signed result and an encrypted face template (numbers, not a picture) leave the phone.</li>
        <li>We never ask for or store Aadhaar numbers.</li>
        <li>Each scan is recorded as a hash on the audit ledger (no personal details on the ledger).</li>
      </ul>
      <label className="check" htmlFor={id}>
        <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span>{who === 'I' ? 'I have read this and I agree to the scan.' : 'The pensioner has read this notice and agrees to the scan.'}</span>
      </label>
    </div>
  );
}
