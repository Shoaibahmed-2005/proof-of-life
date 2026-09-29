import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api/client';
import { useEventsSocket } from '../api/sockets';
import { useAuth } from '../app/providers';
import { PageBanner } from '../components/Shell';

const EVENT_TEXT = {
  ENROLLMENT_CAPTURED: 'Registration scan captured, waiting for approval',
  ENROLLMENT_APPROVED: 'Registration approved',
  CERTIFICATE_ISSUED: 'Life certificate issued',
  UNDER_REVIEW: 'Certificate sent for review',
  REJECTED: 'Attempt rejected',
  STATUS_CHANGED: 'Pension status changed',
  ACCESS_GRANTED: 'Practice scan verified',
};

export default function OfficerHome() {
  const { officer, token } = useAuth();
  const [counts, setCounts] = useState(null);
  const [events, setEvents] = useState([]);

  const load = useCallback(async () => {
    try {
      const [reviews, frozen, pending, treasury] = await Promise.all([
        api('/reviews'), api('/reviews/frozen'), api('/pensioners?status=PENDING_ENROLLMENT'), api('/treasury/summary'),
      ]);
      setCounts({ reviews: reviews.length, frozen: frozen.length, pending: pending.length, treasury });
    } catch { setCounts(null); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const socket = useEventsSocket(token, useCallback((ev) => {
    if (!EVENT_TEXT[ev.event]) return;
    setEvents((e) => [{ ...ev, key: `${ev.event}-${ev.at}-${Math.random()}` }, ...e].slice(0, 12));
    load();
  }, [load]));

  const tiles = [
    ['Register Pensioner', '/officer/register', counts ? `${counts.pending} waiting to finish` : ''],
    ['Review Queue', '/officer/reviews', counts ? `${counts.reviews} to review · ${counts.frozen} frozen` : ''],
    ['Pensioner Records', '/officer/records', counts ? `${counts.treasury.pensioners.total} pensioners` : ''],
    ['Treasury', '/officer/treasury', counts ? `${counts.treasury.entitlements.RELEASED.count} released` : ''],
    ['Audit Ledger', '/ledger', 'Verify chain integrity'],
    ['Practice scan', '/practice', 'Test a phone'],
  ];
  return (
    <>
      <PageBanner title="Officer dashboard" crumbs={[['Officer']]} />
      <div className="container section stack">
        <p style={{ fontSize: '1.1rem' }}>Welcome, <strong>{officer?.full_name}</strong>.</p>
        <div className="grid grid-3">
          {tiles.map(([title, to, sub]) => (
            <Link key={title} to={to} className="card feature-card">
              <h3>{title}</h3>
              <p>{sub || ' '}</p>
              <span className="link-more">Open ›</span>
            </Link>
          ))}
        </div>
        <section className="card" aria-labelledby="live-title">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 id="live-title" style={{ fontSize: '1.3rem', margin: 0 }}>Live activity</h2>
            <span className={`socket-state ${socket}`}>{socket === 'open' ? 'Live' : 'Connecting…'}</span>
          </div>
          <ul className="feed-list" style={{ marginTop: 12, boxShadow: 'none' }}>
            {events.length === 0 ? <li className="muted">Events appear here as phones scan.</li> : events.map((e) => (
              <li key={e.key}>
                <strong>{EVENT_TEXT[e.event]}</strong>{e.reason ? `: ${e.reason}` : ''}
                {e.pensioner_id ? <> · <Link to={`/officer/records/${e.pensioner_id}`}>pensioner #{e.pensioner_id}</Link></> : null}
                <time dateTime={e.at}>{fmt.dateTime(e.at)}</time>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
