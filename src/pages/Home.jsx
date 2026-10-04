import { useEffect, useState } from 'react';
import { Activity, Blocks, Cpu, EyeOff, ScanFace, UserCheck } from 'lucide-react';
import { api, fmt } from '../api/client';
import { ElderAtHome, HelpChat, LedgerChain, OfficerDesk, PhonePulse, ShieldCheck } from '../components/Art';
import {
  FeatureCards, FeedColumns, HeroCarousel, HighlightStrip, IconCarousel, SideInfo, Showcase, UsefulLinks,
} from '../components/sections';

const EVENT_TEXT = {
  REGISTRATION_CAPTURED: 'Registration scan captured',
  REGISTRATION_APPROVED: 'Pensioner registration approved',
  CERTIFICATE_ISSUED: 'Life certificate issued',
  CERTIFICATE_UNDER_REVIEW: 'Certificate sent for review',
  CERTIFICATE_REJECTED: 'Certificate attempt rejected',
  REVIEW_DECISION: 'Officer review decision',
  STATUS_CHANGED: 'Pension status changed',
};

export const SECURITY_LAYERS = [
  { icon: Activity, title: 'Pulse Check', text: 'Heartbeat from the camera' },
  { icon: ScanFace, title: 'Face Match', text: '1:1 with the registered face' },
  { icon: Cpu, title: 'Hardware Signature', text: 'Signed inside Titan M2' },
  { icon: Blocks, title: 'Tamper-proof Ledger', text: 'Hash-chained records' },
  { icon: UserCheck, title: 'Officer Review', text: 'Humans decide borderline cases' },
  { icon: EyeOff, title: 'Privacy', text: 'No photos or Aadhaar stored' },
];

export default function Home() {
  const [stats, setStats] = useState(null);
  const [feed, setFeed] = useState({ certs: [], activity: [] });

  useEffect(() => {
    const load = async () => {
      try {
        const [issued, regs, all, chain] = await Promise.all([
          api('/ledger?event_type=CERTIFICATE_ISSUED&limit=8', { auth: false }),
          api('/ledger?event_type=REGISTRATION_APPROVED&limit=1', { auth: false }),
          api('/ledger?limit=8', { auth: false }),
          api('/ledger/verify', { auth: false }),
        ]);
        setStats({ issued: issued.total, registered: regs.total, entries: all.total, valid: chain.valid });
        setFeed({ certs: issued.entries, activity: all.entries });
      } catch {
        setStats(null);
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  const slides = [
    { kicker: 'For defence pensioners', title: 'Submit your life certificate from home, in under a minute',
      text: 'No queues and no travel. Your phone checks your pulse and your face, and signs the proof inside its security chip.',
      cta: 'Submit Life Certificate', to: '/submit', art: <ElderAtHome width={320} /> },
    { kicker: 'Proof of life you can trust', title: 'A photo or a video cannot pass',
      text: 'A live heartbeat, a random action like "turn your head left", and a match with your registered face are all required.',
      cta: 'How it works', to: '/how-it-works', art: <PhonePulse width={300} /> },
    { kicker: 'Transparent and tamper-evident', title: 'Every certificate is recorded on an audit ledger',
      text: 'Hash-chained records mean nobody can quietly change history. Anyone can check the chain.',
      cta: 'View audit ledger', to: '/ledger', art: <LedgerChain width={320} /> },
  ];

  const features = [
    { title: 'Submit Certificate', text: 'Enter your pension ID, scan the QR code and follow the prompts on your phone.', to: '/submit', art: <PhonePulse width={150} /> },
    { title: 'Check Status', text: 'See whether your certificate for this year has been issued.', to: '/status', art: <ShieldCheck width={96} /> },
    { title: 'Officer Registration', text: 'Officers register pensioners once, after checking their ID in person.', to: '/officer/login', art: <OfficerDesk width={150} /> },
    { title: 'Help & Support', text: 'Answers to common questions, and a practice scan to test your phone.', to: '/help', art: <HelpChat width={130} /> },
  ];

  return (
    <div className="page-pensioner">
      <HeroCarousel slides={slides} />

      <section className="section">
        <div className="container">
          <HighlightStrip
            art={<ShieldCheck width={180} />}
            title="Live on the audit ledger"
            text={stats ? (stats.valid ? 'The ledger chain is intact (verified just now).' : 'Warning: the ledger chain failed verification.') : 'Connecting to the ledger…'}
            stats={[
              [stats ? stats.issued : '—', 'certificates issued'],
              [stats ? stats.registered : '—', 'pensioners registered'],
              [stats ? stats.entries : '—', 'ledger entries'],
            ]}
          />
        </div>
      </section>

      <section className="section section--peach" aria-labelledby="about-title">
        <div className="container">
          <h2 id="about-title" className="section-title">About the portal</h2>
          <p className="section-lead">Every pensioner proves once a year that they are alive, so their pension continues. Proof of Life lets them do it from home, securely.</p>
          <SideInfo
            links={[['How it works', '/how-it-works'], ['Submit a life certificate', '/submit'], ['Check your status', '/status'],
              ['Practice scan', '/practice'], ['Privacy and data use', '/help#privacy'], ['Audit ledger', '/ledger']]}
            title="Why proof of life needs more than a photo"
            art={<ElderAtHome width={200} />}
            moreTo="/how-it-works"
          >
            <p>Pensions have been paid out long after a pensioner has passed away, using old photos or videos. Proof of Life checks three things at once: that the person is <strong>alive</strong> (a heartbeat measured by the camera), that they are <strong>the registered pensioner</strong> (a face match), and that the proof comes from <strong>their genuine phone</strong> (a signature from its security chip).</p>
          </SideInfo>
        </div>
      </section>

      <section className="section" aria-labelledby="services-title">
        <div className="container">
          <h2 id="services-title" className="section-title">Services</h2>
          <p className="section-lead">Everything a pensioner or officer needs, in plain language.</p>
          <FeatureCards items={features} />
        </div>
      </section>

      <section className="section" aria-labelledby="showcase-title">
        <div className="container">
          <h2 id="showcase-title" className="visually-hidden">The app</h2>
          <Showcase title="Three steps on your phone" text="The Proof of Life app guides you with large, clear prompts. The officer portal updates the moment you finish." />
        </div>
      </section>

      <section className="section section--peach" aria-labelledby="feeds-title">
        <div className="container">
          <h2 id="feeds-title" className="section-title">What's new</h2>
          <FeedColumns columns={[
            { title: 'Announcements', items: [
              { key: 'a1', text: 'Life certificates for 2026 are due by 30 November.' },
              { key: 'a2', text: 'New: practise the scan on your phone before submitting.' },
              { key: 'a3', text: 'Officers can now review borderline cases from the Review Queue.' },
              { key: 'a4', text: 'Every certificate now comes with a verifiable digital credential.' },
            ] },
            { title: 'Recent Certificates', empty: 'No certificates yet this year.', items: feed.certs.map((e) => ({
              key: e.entry_hash, when: e.created_at, text: <>Certificate recorded · <span className="mono">{fmt.shortHash(e.entry_hash)}</span></>,
            })) },
            { title: 'Ledger Activity', empty: 'The ledger is empty.', items: feed.activity.map((e) => ({
              key: e.entry_hash, when: e.created_at, text: <>#{e.seq} {EVENT_TEXT[e.event_type] || e.event_type}</>,
            })) },
          ]} />
        </div>
      </section>

      <section className="section" aria-labelledby="security-title">
        <div className="container">
          <h2 id="security-title" className="section-title">How the security works</h2>
          <p className="section-lead">Six layers protect every certificate.</p>
          <IconCarousel items={SECURITY_LAYERS} />
        </div>
      </section>

      <section className="section section--peach" aria-labelledby="links-title">
        <div className="container">
          <h2 id="links-title" className="section-title">Useful links</h2>
          <UsefulLinks
            art={<HelpChat width={220} />}
            links={[['Submit Life Certificate', '/submit'], ['Check Status', '/status'], ['Practice scan', '/practice'],
              ['How it works', '/how-it-works'], ['Help & FAQs', '/help'], ['Accessibility', '/help#accessibility'],
              ['Privacy and data use', '/help#privacy'], ['Audit ledger', '/ledger'], ['Officer login', '/officer/login'], ['Contact us', '/contact']]}
          />
        </div>
      </section>
    </div>
  );
}
