import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { AppScreen, HeroWave, Skyline } from './Art';

/* ── Hero carousel ──────────────────────────────────────────────────── */

export function HeroCarousel({ slides }) {
  const [i, setI] = useState(0);
  const s = slides[i];
  const go = (d) => setI((i + d + slides.length) % slides.length);
  return (
    <section className="hero" aria-roledescription="carousel" aria-label="Highlights">
      <Skyline />
      <HeroWave />
      <div className="container hero-inner" aria-live="polite">
        <div>
          <div className="hero-kicker">{s.kicker}</div>
          <h1>{s.title}</h1>
          <p>{s.text}</p>
          <Link to={s.to} className="btn btn-white">{s.cta}</Link>
        </div>
        <div className="hero-card">{s.art}</div>
      </div>
      <div className="hero-controls">
        <button type="button" className="btn-icon" onClick={() => go(-1)} aria-label="Previous slide"><ChevronLeft aria-hidden="true" /></button>
        <div className="hero-dots">
          {slides.map((sl, k) => (
            <button key={sl.title} type="button" aria-label={`Slide ${k + 1}: ${sl.title}`} aria-current={k === i} onClick={() => setI(k)} />
          ))}
        </div>
        <button type="button" className="btn-icon" onClick={() => go(1)} aria-label="Next slide"><ChevronRight aria-hidden="true" /></button>
      </div>
    </section>
  );
}

/* ── Highlight strip ────────────────────────────────────────────────── */

export function HighlightStrip({ art, title, text, stats }) {
  return (
    <div className="highlight-strip">
      {art}
      <div>
        <h2>{title}</h2>
        {text && <p className="muted" style={{ marginBottom: 0 }}>{text}</p>}
        <div className="stat-row">
          {stats.map(([value, label]) => (
            <div className="stat" key={label}><strong>{value}</strong><span>{label}</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Sidebar + info card ────────────────────────────────────────────── */

export function SideInfo({ heading = 'General Information', links, title, children, art, moreTo }) {
  return (
    <div className="side-layout">
      <aside className="side-links" aria-label={heading}>
        <h3>{heading}</h3>
        <ul>{links.map(([label, to]) => <li key={label}><Link to={to}>{label}</Link></li>)}</ul>
      </aside>
      <div className="card info-card">
        <div>
          <h3 className="card-title">{title}</h3>
          {children}
          {moreTo && <Link className="link-more" to={moreTo}>Know More ›</Link>}
        </div>
        <div aria-hidden="true">{art}</div>
      </div>
    </div>
  );
}

/* ── Feature cards (4-up) ───────────────────────────────────────────── */

export function FeatureCards({ items }) {
  return (
    <div className="grid grid-4">
      {items.map((f) => (
        <Link key={f.title} to={f.to} className="card feature-card">
          <div className="art" aria-hidden="true">{f.art}</div>
          <h3>{f.title}</h3>
          <p>{f.text}</p>
          <span className="link-more">Know More ›</span>
        </Link>
      ))}
    </div>
  );
}

/* ── Gradient showcase with thumbnails ──────────────────────────────── */

export function Showcase({ title, text }) {
  const shots = [
    ['scan', 'Step 1: scan the QR code on the portal'],
    ['measure', 'Step 2: hold still while your pulse is measured'],
    ['result', 'Step 3: certificate issued, the portal updates instantly'],
  ];
  const [i, setI] = useState(0);
  return (
    <div className="showcase">
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
        <p className="muted" style={{ fontSize: '0.9rem' }}>Illustrations of the app screens. The team will replace them with real screenshots.</p>
      </div>
      <div>
        <figure className="showcase-main" style={{ margin: 0 }}>
          <AppScreen variant={shots[i][0]} />
          <figcaption className="center" style={{ marginTop: 8, fontWeight: 600 }}>{shots[i][1]}</figcaption>
        </figure>
        <div className="showcase-thumbs">
          {shots.map(([v, label], k) => (
            <button key={v} type="button" aria-label={label} aria-current={k === i} onClick={() => setI(k)}>
              <svg viewBox="0 0 120 190" height="50" aria-hidden="true"><rect x="4" y="4" width="112" height="182" rx="16" fill="#26282B" /></svg>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Feed columns ───────────────────────────────────────────────────── */

export function FeedColumns({ columns }) {
  return (
    <div className="grid grid-3">
      {columns.map((col) => (
        <section className="feed" key={col.title} aria-labelledby={`feed-${col.title}`}>
          <h3 id={`feed-${col.title}`}>{col.title}</h3>
          <ul className="feed-list" tabIndex={0} aria-label={col.title}>
            {col.items.length === 0 ? <li className="muted">{col.empty || 'Nothing yet.'}</li> : col.items.map((it) => (
              <li key={it.key}>
                {it.text}
                {it.when && <time dateTime={it.when}>{new Date(it.when).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</time>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/* ── Circular icon carousel ─────────────────────────────────────────── */

export function IconCarousel({ items }) {
  const track = useRef(null);
  const scroll = (d) => track.current?.scrollBy({ left: d * 340, behavior: 'smooth' });
  return (
    <div className="icon-carousel">
      <button type="button" className="btn-icon" onClick={() => scroll(-1)} aria-label="Scroll left"><ChevronLeft aria-hidden="true" /></button>
      <ul className="icon-track" ref={track} style={{ listStyle: 'none', margin: 0 }}>
        {items.map(({ icon: Icon, title, text }) => (
          <li className="icon-badge" key={title}>
            <div className="circle"><Icon size={44} aria-hidden="true" /></div>
            <strong>{title}</strong>
            <span>{text}</span>
          </li>
        ))}
      </ul>
      <button type="button" className="btn-icon" onClick={() => scroll(1)} aria-label="Scroll right"><ChevronRight aria-hidden="true" /></button>
    </div>
  );
}

/* ── Useful links ───────────────────────────────────────────────────── */

export function UsefulLinks({ links, art }) {
  return (
    <div className="useful-links">
      <ul>{links.map(([label, to]) => <li key={label}><Link to={to}>{label}</Link></li>)}</ul>
      <div aria-hidden="true">{art}</div>
    </div>
  );
}

/* ── FAQ accordion ──────────────────────────────────────────────────── */

export function Faq({ items }) {
  return (
    <div className="accordion">
      {items.map(([q, a]) => (
        <details key={q}>
          <summary>{q}</summary>
          <div className="answer">{a}</div>
        </details>
      ))}
    </div>
  );
}
