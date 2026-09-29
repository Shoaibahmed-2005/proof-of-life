import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth, useI18n } from '../app/providers';
import { PageBanner } from '../components/Shell';
import { OfficerDesk } from '../components/Art';
import { Alert, Field } from '../components/ui';

export default function OfficerLogin() {
  const { t } = useI18n();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!username || !password) { setError('Enter your username and password.'); return; }
    setBusy(true); setError('');
    try {
      await login(username.trim(), password);
      navigate(location.state?.from || '/officer', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally { setBusy(false); }
  };

  return (
    <>
      <PageBanner title={t('navOfficer')} crumbs={[[t('navOfficer')]]} />
      <div className="container section">
        <div className="grid grid-2" style={{ alignItems: 'center' }}>
          <form className="card form" onSubmit={submit} noValidate>
            <h2 style={{ fontSize: '1.5rem' }}>Pension office staff</h2>
            {error && <Alert kind="danger" title="Could not sign in">{error}</Alert>}
            <Field id="username" label="Username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            <Field id="password" label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            <div><button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></div>
            <p className="demo-note">Demo login: <strong>officer</strong> / <strong>officer123</strong> (set in <span className="mono">backend/.env</span>).</p>
          </form>
          <div className="center"><OfficerDesk width={320} /></div>
        </div>
      </div>
    </>
  );
}
