import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../app/providers';
import { Loading } from './ui';

/** Officer-only pages: send visitors to the login page, then back. */
export default function RequireOfficer({ children }) {
  const { officer, checking } = useAuth();
  const location = useLocation();
  if (checking) return <div className="container section"><Loading label="Checking your login…" /></div>;
  if (!officer) return <Navigate to="/officer/login" replace state={{ from: location.pathname + location.search }} />;
  return children;
}
