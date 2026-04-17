'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { workerPortalApi } from '@/lib/adminApi';
import { useAuth } from '@/context/AuthContext';
import { useSectionAccess } from '@/hooks/useAuth';
import { Badge, bookingStatusColor } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import type { WorkerUpcomingBooking } from '@/types';
import styles from './page.module.css';

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const fmt = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
    : '—';

const fmtRelative = (iso: string | null): string => {
  if (!iso) return '—';
  const diff = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(diff);
  const mins = Math.floor(abs / 60000);
  const hrs = Math.floor(mins / 60);
  const days = Math.floor(hrs / 24);
  if (days > 0) return `in ${days}d ${hrs % 24}h`;
  if (hrs > 0) return `in ${hrs}h ${mins % 60}m`;
  if (mins > 0) return `in ${mins}m`;
  return 'now';
};

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function WorkerPortalPage() {
  const { user, isAdmin } = useAuth();
  const hasBookings = useSectionAccess('bookings');
  const hasSchedule = useSectionAccess('schedule');
  const hasLiveChat = useSectionAccess('live_chat');

  const workerId = user?.worker_id ?? null;

  const [bookings, setBookings] = useState<WorkerUpcomingBooking[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [freeNowResult, setFreeNowResult] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [msgResult, setMsgResult] = useState<string | null>(null);

  const loadBookings = useCallback(async () => {
    if (!workerId || !hasBookings) return;
    setLoading(true);
    try {
      setBookings(await workerPortalApi.upcomingBookings(workerId));
    } finally {
      setLoading(false);
    }
  }, [workerId, hasBookings]);

  useEffect(() => { loadBookings(); }, [loadBookings]);

  const doAction = async (
    bookingId: string,
    action: 'approve' | 'reject' | 'completeEarly',
  ) => {
    if (!workerId) return;
    setActionLoading(bookingId + action);
    try {
      if (action === 'approve') await workerPortalApi.approve(bookingId, workerId);
      else if (action === 'reject') await workerPortalApi.reject(bookingId, workerId);
      else await workerPortalApi.completeEarly(bookingId, workerId);
      await loadBookings();
    } finally {
      setActionLoading(null);
    }
  };

  const doFreeNow = async () => {
    if (!workerId) return;
    setActionLoading('freeNow');
    const res = await workerPortalApi.freeNow(workerId);
    setFreeNowResult(res.message);
    setActionLoading(null);
    setTimeout(() => setFreeNowResult(null), 4000);
  };

  const doSendMessage = async () => {
    if (!workerId || !message.trim()) return;
    setActionLoading('msg');
    const res = await workerPortalApi.sendMessage(workerId, message.trim());
    setMsgResult(res.message);
    setMessage('');
    setActionLoading(null);
    setTimeout(() => setMsgResult(null), 4000);
  };

  /* ---- Admin viewing worker portal ---- */
  if (isAdmin && !user?.worker_id) {
    return (
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>Worker Portal</h1>
          <p className={styles.pageSub}>Admin view — no worker account linked to this login.</p>
        </header>
        <EmptyState
          icon="👜"
          title="No worker record linked"
          description="This admin account has no worker_id. Log in as a worker to use the portal."
        />
      </div>
    );
  }

  /* ---- Worker but no worker_id ---- */
  if (!workerId) {
    return (
      <div className={styles.page}>
        <EmptyState
          icon="⚠️"
          title="Worker account not linked"
          description="Your user account is not linked to a worker record. Contact your admin."
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Worker Portal</h1>
          <p className={styles.pageSub}>Your upcoming bookings and operational commands</p>
        </div>
        <Button
          id="refresh-worker-btn"
          variant="secondary"
          size="sm"
          onClick={loadBookings}
        >
          Refresh
        </Button>
      </header>

      <div className={styles.layout}>
        {/* ── Upcoming Bookings ── */}
        <section className={styles.mainSection}>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>Upcoming Bookings</h2>
            {!hasBookings && !isAdmin && (
              <Badge color="default">Section disabled by admin</Badge>
            )}
          </div>

          {!hasBookings && !isAdmin ? (
            <EmptyState
              icon="🔒"
              title="Bookings section disabled"
              description="Your admin has not enabled the bookings section for your account."
            />
          ) : loading ? (
            <div className={styles.loadingRow}><Spinner /></div>
          ) : bookings.length === 0 ? (
            <EmptyState
              icon="📅"
              title="No upcoming bookings"
              description="You have no confirmed bookings scheduled ahead."
            />
          ) : (
            <div className={styles.bookingList}>
              {bookings.map((b) => (
                <div key={b.id} className={styles.bookingCard}>
                  <div className={styles.bookingTop}>
                    <div className={styles.bookingMeta}>
                      <span className={styles.bookingTime}>{fmt(b.scheduled_start_at)}</span>
                      <span className={styles.bookingRelative}>{fmtRelative(b.scheduled_start_at)}</span>
                    </div>
                    <Badge color={bookingStatusColor(b.status)}>
                      {b.status.replace(/_/g, ' ')}
                    </Badge>
                  </div>

                  <div className={styles.bookingDetails}>
                    <span className={styles.detailChip}>
                      {b.booking_type === 'incall' ? '📍 Incall' : '🚗 Outcall'}
                    </span>
                    {b.duration_minutes && (
                      <span className={styles.detailChip}>⏱ {b.duration_minutes} min</span>
                    )}
                    {b.client_name && (
                      <span className={styles.detailChip}>👤 {b.client_name}</span>
                    )}
                  </div>

                  {hasBookings && (
                    <div className={styles.bookingActions}>
                      <Button
                        id={`worker-approve-${b.id}`}
                        variant="primary"
                        size="sm"
                        loading={actionLoading === b.id + 'approve'}
                        onClick={() => doAction(b.id, 'approve')}
                      >
                        ✓ Approve
                      </Button>
                      <Button
                        id={`worker-reject-${b.id}`}
                        variant="danger"
                        size="sm"
                        loading={actionLoading === b.id + 'reject'}
                        onClick={() => doAction(b.id, 'reject')}
                      >
                        ✗ Reject
                      </Button>
                      {b.status === 'confirmed' && (
                        <Button
                          id={`worker-complete-${b.id}`}
                          variant="ghost"
                          size="sm"
                          loading={actionLoading === b.id + 'completeEarly'}
                          onClick={() => doAction(b.id, 'completeEarly')}
                        >
                          ✓ Complete early
                        </Button>
                      )}
                      <Link href={`/bookings/${b.id}`} className={styles.detailLink}>
                        View detail →
                      </Link>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ── Sidebar: Quick Commands ── */}
        <aside className={styles.commandsSidebar}>
          {/* Schedule — Free Now */}
          <div className={styles.commandCard}>
            <h3 className={styles.commandTitle}>Availability</h3>
            {hasSchedule || isAdmin ? (
              <>
                <p className={styles.commandDesc}>
                  Signal that you are free and available to accept new bookings now.
                </p>
                <Button
                  id="free-now-btn"
                  variant="primary"
                  size="sm"
                  loading={actionLoading === 'freeNow'}
                  onClick={doFreeNow}
                >
                  🟢 Free Now
                </Button>
                {freeNowResult && (
                  <p className={styles.commandResult}>{freeNowResult}</p>
                )}
              </>
            ) : (
              <p className={styles.disabled}>Schedule section disabled by admin.</p>
            )}
          </div>

          {/* Live Chat — Send Message */}
          <div className={styles.commandCard}>
            <h3 className={styles.commandTitle}>Send Message</h3>
            {hasLiveChat || isAdmin ? (
              <>
                <p className={styles.commandDesc}>
                  Send a command or message as Alysha into the active conversation.
                </p>
                <div className={styles.msgRow}>
                  <input
                    id="worker-message-input"
                    type="text"
                    className={styles.msgInput}
                    placeholder="e.g. confirmed, be there at 8"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && doSendMessage()}
                  />
                  <Button
                    id="send-message-btn"
                    variant="secondary"
                    size="sm"
                    loading={actionLoading === 'msg'}
                    disabled={!message.trim()}
                    onClick={doSendMessage}
                  >
                    Send
                  </Button>
                </div>
                {msgResult && (
                  <p className={styles.commandResult}>{msgResult}</p>
                )}
              </>
            ) : (
              <p className={styles.disabled}>Live Chat section disabled by admin.</p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
