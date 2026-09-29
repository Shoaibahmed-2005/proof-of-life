import { useEffect } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { PageBanner, HELPLINE_EMAIL, HELPLINE_PHONE } from '../components/Shell';
import { ElderAtHome, HelpChat, LedgerChain, OfficerDesk, PhonePulse, ShieldCheck } from '../components/Art';
import { Faq, FeatureCards, IconCarousel, SideInfo, UsefulLinks } from '../components/sections';
import { SECURITY_LAYERS } from './Home';

/* ── How it works ───────────────────────────────────────────────────── */

export function HowItWorks() {
  return (
    <div className="page-pensioner">
      <PageBanner title="How It Works" crumbs={[['How It Works']]} />
      <section className="section">
        <div className="container stack">
          <SideInfo links={[['Registration (once)', '#registration'], ['Yearly certificate', '#yearly'], ['Why a photo cannot pass', '#security'],
            ['Privacy', '/help#privacy'], ['Practice scan', '/practice']]}
            title="Three proofs in one scan" art={<ShieldCheck width={170} />} moreTo="/help">
            <p><strong>Alive:</strong> the phone camera sees the tiny colour changes in your skin with every heartbeat (remote photoplethysmography).</p>
            <p><strong>The right person:</strong> your face is compared one-to-one with the face registered by the officer. Nobody else's record is searched.</p>
            <p><strong>A genuine phone:</strong> the result is signed inside the phone's security chip (Titan M2), with a key that never leaves it.</p>
          </SideInfo>
        </div>
      </section>
      <section className="section section--peach" id="registration">
        <div className="container">
          <h2 className="section-title">The steps</h2>
          <FeatureCards items={[
            { title: '1. Register once', text: 'An officer checks your ID in person and you do one face scan with your own phone.', to: '/officer/login', art: <OfficerDesk width={150} /> },
            { title: '2. Every year, from home', text: 'Enter your pension ID on the portal and scan the QR code with the same phone.', to: '/submit', art: <ElderAtHome width={160} /> },
            { title: '3. Pulse, action, face', text: 'Keep still for about 10 seconds, then do the action shown ("Blink twice").', to: '/practice', art: <PhonePulse width={150} /> },
            { title: '4. Certificate recorded', text: 'Your certificate is issued instantly and recorded on the audit ledger.', to: '/ledger', art: <LedgerChain width={160} /> },
          ]} />
        </div>
      </section>
      <section className="section" id="yearly">
        <div className="container stack">
          <h2 className="section-title">What happens to the result</h2>
          <div className="grid grid-3">
            <div className="card"><h3 className="card-title">Strong match</h3><p>The certificate is issued immediately and your pension continues.</p></div>
            <div className="card"><h3 className="card-title">Borderline</h3><p>An officer looks at it (ageing, lighting or pose can lower the score). You don't need to do anything.</p></div>
            <div className="card"><h3 className="card-title">Clear mismatch or no pulse</h3><p>The attempt is rejected. After repeated failures the pension is <strong>frozen, never cancelled</strong>, until an officer resolves it with you.</p></div>
          </div>
        </div>
      </section>
      <section className="section section--peach" id="security">
        <div className="container">
          <h2 className="section-title">Why a photo or video cannot pass</h2>
          <p className="section-lead">A photo has no heartbeat. A video of you on another screen cannot answer a random request made at that moment ("turn your head left"). And a different phone does not have your registered key.</p>
          <IconCarousel items={SECURITY_LAYERS} />
        </div>
      </section>
    </div>
  );
}

/* ── Help & FAQs ────────────────────────────────────────────────────── */

export const FAQ_ITEMS = [
  ['Who needs to submit a life certificate?', 'Every pensioner, once a year, so that the pension continues. The deadline for 2026 is 30 November.'],
  ['What do I need?', 'The phone you used at registration, with the Jeevan Suraksha app, your pension ID (PPO number), and about one minute in good light.'],
  ['The scan takes long or says "No pulse detected"', 'Sit facing a window or lamp (light on your face, not behind you), hold the phone at eye level about an arm\'s length away and keep still. Try the practice scan to check your phone.'],
  ['My phone says "Can\'t reach the laptop"', <span key="wifi">Your phone and the computer showing the QR code must be on the same Wi-Fi. At a help desk, ask the staff; they may use a phone hotspot. The message lists what was tried and why it failed.</span>],
  ['Can someone else submit my certificate?', 'No. Your face must match the one registered by the officer, it must come from your registered phone, and a live pulse and a random action are required.'],
  ['What if my face has changed with age?', 'The system slowly updates your template after each strong match, and borderline cases go to an officer instead of being rejected.'],
  ['What is stored about me?', <span key="stored">Your name, pension ID, service number, the last 4 digits of your bank account, an <strong>encrypted face template</strong> (numbers, not a picture) and your phone's public key. No photos, no videos, no Aadhaar number.</span>],
  ['My pension is shown as Frozen', 'Frozen means paused, never cancelled. Contact your pension office; an officer can restore it after checking with you.'],
];

export function Help() {
  const location = useLocation();
  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' });
  }, [location.hash]);
  return (
    <div className="page-pensioner">
      <PageBanner title="Help & FAQs" crumbs={[['Help & FAQs']]} />
      <section className="section">
        <div className="container stack">
          <h2 className="section-title">Frequently asked questions</h2>
          <Faq items={FAQ_ITEMS} />
        </div>
      </section>
      <section className="section section--peach">
        <div className="container grid grid-2">
          <div className="card" id="privacy">
            <h2 className="card-title" style={{ fontSize: '1.3rem' }}>Privacy and data use</h2>
            <p>No face images are stored or sent. The phone turns your face into an encrypted template (a list of numbers) and signs the result in its security chip. The audit ledger holds only hashes. Demo data is fictional.</p>
          </div>
          <div className="card" id="consent">
            <h2 className="card-title" style={{ fontSize: '1.3rem' }}>Consent</h2>
            <p>Before every scan you are shown what will be measured and must agree. Your consent is recorded with the signed result.</p>
          </div>
          <div className="card" id="accessibility">
            <h2 className="card-title" style={{ fontSize: '1.3rem' }}>Accessibility</h2>
            <p>Use <strong>A−, A, A+</strong> at the top of every page to change the text size. Every page works with a keyboard (Tab / Shift+Tab / Enter), status changes are announced to screen readers, and colours meet WCAG AA contrast.</p>
          </div>
          <div className="card" id="limitations">
            <h2 className="card-title" style={{ fontSize: '1.3rem' }}>Known limitations</h2>
            <p>Pulse measurement from a camera varies with lighting, skin tone and age; borderline cases go to an officer. Registration relies on an officer checking ID (DigiLocker or the Aadhaar Secure QR would be the production path). The ledger is a local hash chain that can be anchored on a public blockchain.</p>
          </div>
          <div className="card" id="wifi">
            <h2 className="card-title" style={{ fontSize: '1.3rem' }}>Phone can't connect (for help-desk staff)</h2>
            <p>The phone and laptop must be on the same Wi-Fi, the backend must be started with <span className="mono">python run.py</span>, and Windows Firewall must allow ports 8000 and 5173. If the Wi-Fi blocks devices from reaching each other, use a phone hotspot. Full steps: <span className="mono">ANDROID_BUILD.md</span>, "Wi-Fi setup".</p>
          </div>
        </div>
      </section>
      <section className="section">
        <div className="container">
          <h2 className="section-title">Useful links</h2>
          <UsefulLinks art={<HelpChat width={220} />} links={[['Practice scan', '/practice'], ['Submit Life Certificate', '/submit'],
            ['Check Status', '/status'], ['How it works', '/how-it-works'], ['Audit ledger', '/ledger'], ['Contact us', '/contact']]} />
        </div>
      </section>
    </div>
  );
}

/* ── Contact ────────────────────────────────────────────────────────── */

export function Contact() {
  return (
    <div className="page-pensioner">
      <PageBanner title="Contact" crumbs={[['Contact']]} />
      <div className="container section grid grid-2" style={{ alignItems: 'center' }}>
        <div className="card stack">
          <h2 className="card-title" style={{ fontSize: '1.4rem' }}>Pension help desk</h2>
          <dl className="kv">
            <dt>Email</dt><dd><a href={`mailto:${HELPLINE_EMAIL}`}>{HELPLINE_EMAIL}</a></dd>
            <dt>Phone</dt><dd>{HELPLINE_PHONE}</dd>
            <dt>Office hours</dt><dd>Monday–Friday, 9:30 am – 5:30 pm</dd>
          </dl>
          <p className="demo-note">This is a demonstration portal (SIH 2026). The contact details are placeholders.</p>
        </div>
        <div className="center"><HelpChat width={280} /></div>
      </div>
    </div>
  );
}

/* ── Search ─────────────────────────────────────────────────────────── */

const SEARCH_INDEX = [
  ['Submit Life Certificate', '/submit', 'submit life certificate yearly annual proof of life qr scan'],
  ['Check Status', '/status', 'status check certificate issued frozen payment'],
  ['Practice scan', '/practice', 'practice test phone device check pulse wifi'],
  ['How It Works', '/how-it-works', 'how works pulse face match hardware signature ledger security video photo'],
  ['Help & FAQs', '/help', 'help faq questions problem no pulse slow'],
  ['Privacy and data use', '/help#privacy', 'privacy data aadhaar photo stored template'],
  ['Accessibility', '/help#accessibility', 'accessibility text size keyboard screen reader'],
  ['Phone cannot connect', '/help#wifi', 'wifi network connect firewall hotspot laptop reach'],
  ['Audit Ledger', '/ledger', 'ledger blockchain hash chain verify integrity credential'],
  ['Verify a credential', '/ledger#verify', 'verify credential did bank certificate'],
  ['Officer login', '/officer/login', 'officer login staff register review'],
  ['Contact', '/contact', 'contact email phone help desk office hours'],
];

export function Search() {
  const [params] = useSearchParams();
  const q = (params.get('q') || '').toLowerCase().trim();
  const words = q.split(/\s+/).filter(Boolean);
  const results = words.length ? SEARCH_INDEX.filter(([title, , keys]) => words.some((w) => `${title} ${keys}`.toLowerCase().includes(w))) : [];
  const faqs = words.length ? FAQ_ITEMS.filter(([question]) => words.some((w) => question.toLowerCase().includes(w))) : [];
  return (
    <>
      <PageBanner title="Search" crumbs={[['Search']]} />
      <div className="container section stack">
        <p>{words.length ? <>Results for <strong>“{q}”</strong></> : 'Type in the search box at the top of the page.'}</p>
        {results.length === 0 && faqs.length === 0 && words.length > 0 && <p>No pages found. Try “certificate”, “status” or “help”.</p>}
        <ul>{results.map(([title, to]) => <li key={to}><Link to={to}>{title}</Link></li>)}</ul>
        {faqs.length > 0 && <><h2 style={{ fontSize: '1.2rem' }}>From the FAQs</h2><Faq items={faqs} /></>}
      </div>
    </>
  );
}

export function NotFound() {
  return (
    <>
      <PageBanner title="Page not found" crumbs={[['Not found']]} />
      <div className="container section center">
        <p>We couldn't find that page.</p>
        <Link className="btn btn-primary" to="/">Go to the home page</Link>
      </div>
    </>
  );
}
