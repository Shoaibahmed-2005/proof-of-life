import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Mail, Phone, Search } from 'lucide-react';
import { Logo } from './Art';
import { useAuth, useI18n, useTextSize } from '../app/providers';

export const HELPLINE_EMAIL = 'help@jeevansuraksha.example';
export const HELPLINE_PHONE = '1800-000-0000 (demo)';

function UtilityBar() {
  const { t } = useI18n();
  const [size, setSize] = useTextSize();
  const sizes = [['small', 'A−', 'Smaller text'], ['normal', 'A', 'Normal text'], ['large', 'A+', 'Larger text']];
  return (
    <div className="utility-bar">
      <div className="container">
        <div className="utility-contacts">
          <span><Mail size={15} aria-hidden="true" /> <a href={`mailto:${HELPLINE_EMAIL}`}>{HELPLINE_EMAIL}</a></span>
          <span><Phone size={15} aria-hidden="true" /> {t('helpline')}: {HELPLINE_PHONE}</span>
        </div>
        <div className="row" style={{ gap: 16 }}>
          <Link to="/help#accessibility">{t('accessibility')}</Link>
          <div className="text-size" role="group" aria-label={t('textSize')}>
            {sizes.map(([key, label, aria]) => (
              <button key={key} type="button" aria-label={aria} aria-pressed={size === key} onClick={() => setSize(key)}>{label}</button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Header() {
  const { t, lang, setLang } = useI18n();
  const [q, setQ] = useState('');
  const navigate = useNavigate();
  const onSearch = (e) => {
    e.preventDefault();
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  };
  return (
    <header className="site-header">
      <div className="container">
        <Link to="/" className="brand" aria-label={`${t('portalName')} – ${t('portalSub')}, home`}>
          <Logo />
          <span>
            <span className="brand-name">{t('portalName')}</span>
            <span className="brand-sub" style={{ display: 'block' }}>{t('portalSub')}</span>
          </span>
        </Link>
        <div className="header-tools">
          <div className="lang-pill" role="group" aria-label="Language">
            <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>English</button>
            <button type="button" aria-pressed={lang === 'hi'} onClick={() => setLang('hi')} lang="hi">हिन्दी</button>
          </div>
          <form className="search-box" role="search" onSubmit={onSearch}>
            <label htmlFor="site-search" className="visually-hidden">{t('search')}</label>
            <input id="site-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('searchPlaceholder')} />
            <button type="submit" aria-label={t('search')}><Search size={18} aria-hidden="true" /></button>
          </form>
        </div>
      </div>
    </header>
  );
}

function MainNav() {
  const { t } = useI18n();
  const { officer } = useAuth();
  const items = [
    ['/', 'navHome'], ['/submit', 'navSubmit'], ['/status', 'navStatus'],
    [officer ? '/officer' : '/officer/login', 'navOfficer'], ['/how-it-works', 'navHow'], ['/help', 'navHelp'], ['/contact', 'navContact'],
  ];
  return (
    <nav className="main-nav" aria-label="Main">
      <div className="container">
        <ul>
          {items.map(([to, key]) => (
            <li key={key}><NavLink to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>{t(key)}</NavLink></li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

function OfficerNav() {
  const { t } = useI18n();
  const { officer, logout } = useAuth();
  const navigate = useNavigate();
  if (!officer) return null;
  const items = [['/officer/register', 'navRegister'], ['/officer/reviews', 'navReviews'], ['/officer/records', 'navRecords'],
    ['/officer/treasury', 'navTreasury'], ['/ledger', 'navLedger']];
  return (
    <nav className="officer-nav" aria-label="Officer">
      <div className="container">
        {items.map(([to, key]) => (
          <NavLink key={key} to={to} className={({ isActive }) => (isActive ? 'active' : '')}>{t(key)}</NavLink>
        ))}
        <span className="who">
          Signed in as <strong>{officer.full_name}</strong>
          <button type="button" className="btn btn-secondary btn-small" onClick={() => { logout(); navigate('/'); }}>{t('signOut')}</button>
        </span>
      </div>
    </nav>
  );
}

function Footer() {
  const { t } = useI18n();
  return (
    <>
      <footer className="site-footer">
        <div className="container footer-grid">
          <div>
            <div className="footer-brand"><Logo size={44} /><strong style={{ fontSize: '1.15rem' }}>{t('portalName')}</strong></div>
            <p className="footer-note">Annual life certificates for defence pensioners, from home: a pulse check, a face match and a hardware-signed proof, recorded on a tamper-evident ledger.</p>
            <p className="footer-note"><strong style={{ color: '#fff' }}>Office hours:</strong> Monday–Friday, 9:30 am – 5:30 pm</p>
          </div>
          <div>
            <h2>Policies</h2>
            <ul>
              <li><Link to="/help#privacy">Privacy &amp; data use</Link></li>
              <li><Link to="/help#consent">Consent</Link></li>
              <li><Link to="/help#limitations">Known limitations</Link></li>
            </ul>
          </div>
          <div>
            <h2>Help</h2>
            <ul>
              <li><Link to="/how-it-works">How it works</Link></li>
              <li><Link to="/help">FAQs</Link></li>
              <li><Link to="/practice">Practice scan</Link></li>
              <li><Link to="/ledger">Audit ledger</Link></li>
            </ul>
          </div>
          <div>
            <h2>Accessibility &amp; Contact</h2>
            <ul>
              <li><Link to="/help#accessibility">Accessibility</Link></li>
              <li><Link to="/contact">Contact us</Link></li>
              <li><a href={`mailto:${HELPLINE_EMAIL}`}>{HELPLINE_EMAIL}</a></li>
            </ul>
          </div>
        </div>
      </footer>
      <div className="copyright-bar">
        © 2026 Jeevan Suraksha — a demonstration portal built for Smart India Hackathon 2026 (SIH26125). Not a government website.
      </div>
    </>
  );
}

export function PageBanner({ title, crumbs = [] }) {
  return (
    <div className="page-banner">
      <div className="container">
        <h1>{title}</h1>
        <nav aria-label="Breadcrumb">
          <ol className="breadcrumb">
            <li><Link to="/">Home</Link></li>
            {crumbs.map(([label, to]) => <li key={label}>{to ? <Link to={to}>{label}</Link> : <span aria-current="page">{label}</span>}</li>)}
          </ol>
        </nav>
      </div>
    </div>
  );
}

export default function Layout() {
  return (
    <>
      <a href="#main" className="skip-link">Skip to main content</a>
      <UtilityBar />
      <Header />
      <MainNav />
      <OfficerNav />
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
      <Footer />
    </>
  );
}
