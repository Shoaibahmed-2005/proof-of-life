import { useEffect } from 'react';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider, I18nProvider, ToastProvider } from './app/providers';
import Layout from './components/Shell';
import RequireOfficer from './components/RequireOfficer';
import Home from './pages/Home';
import SubmitCertificate from './pages/SubmitCertificate';
import PracticeScan from './pages/PracticeScan';
import CheckStatus from './pages/CheckStatus';
import OfficerLogin from './pages/OfficerLogin';
import OfficerHome from './pages/OfficerHome';
import RegisterPensioner from './pages/RegisterPensioner';
import ReviewQueue from './pages/ReviewQueue';
import { RecordDetail, Records } from './pages/Records';
import Treasury from './pages/Treasury';
import Ledger from './pages/Ledger';
import { Contact, Help, HowItWorks, NotFound, Search } from './pages/Info';

/** On navigation: scroll to top and move focus to the main content (keyboard / screen readers). */
function RouteFocus() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    document.getElementById('main')?.focus({ preventScroll: true });
  }, [pathname]);
  return null;
}

const officer = (el) => <RequireOfficer>{el}</RequireOfficer>;

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>
            <RouteFocus />
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<Home />} />
                <Route path="submit" element={<SubmitCertificate />} />
                <Route path="practice" element={<PracticeScan />} />
                <Route path="status" element={<CheckStatus />} />
                <Route path="how-it-works" element={<HowItWorks />} />
                <Route path="help" element={<Help />} />
                <Route path="contact" element={<Contact />} />
                <Route path="search" element={<Search />} />
                <Route path="ledger" element={<Ledger />} />
                <Route path="officer/login" element={<OfficerLogin />} />
                <Route path="officer" element={officer(<OfficerHome />)} />
                <Route path="officer/register" element={officer(<RegisterPensioner />)} />
                <Route path="officer/reviews" element={officer(<ReviewQueue />)} />
                <Route path="officer/records" element={officer(<Records />)} />
                <Route path="officer/records/:id" element={officer(<RecordDetail />)} />
                <Route path="officer/treasury" element={officer(<Treasury />)} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </I18nProvider>
  );
}
