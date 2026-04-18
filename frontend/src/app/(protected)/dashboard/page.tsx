'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ClipboardList, Bell, AlertTriangle, Wrench } from 'lucide-react';
import { metricsApi, bookingsApi, notificationsApi } from '@/lib/adminApi';
import { useAdminRealtimeRefresh } from '@/hooks/useAdminRealtimeRefresh';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { Badge, bookingStatusColor } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { useAuth } from '@/context/AuthContext';
import type { Metrics, BookingSummary, NotificationItem } from '@/types';
import type { StreamEnvelope } from '@/lib/realtime';
import styles from './page.module.css';

interface DashboardErrors {
  metrics?: string;
  bookings?: string;
  notifications?: string;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Request failed';
}

export default function DashboardPage() {
  const { isAdmin, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [bookings, setBookings] = useState<BookingSummary[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [errors, setErrors] = useState<DashboardErrors>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [m, b, n] = await Promise.allSettled([
      metricsApi.get(),
      bookingsApi.list({ limit: 5 }),
      notificationsApi.list(),
    ]);

    const nextErrors: DashboardErrors = {};

    if (m.status === 'fulfilled') {
      setMetrics(m.value);
    } else {
      nextErrors.metrics = getErrorMessage(m.reason);
    }

    if (b.status === 'fulfilled') {
      setBookings(b.value);
    } else {
      nextErrors.bookings = getErrorMessage(b.reason);
    }

    if (n.status === 'fulfilled') {
      setNotifications(n.value.slice(0, 5));
    } else {
      nextErrors.notifications = getErrorMessage(n.reason);
    }

    setErrors(nextErrors);
  }, []);

  const hasAnyError = Boolean(errors.metrics || errors.bookings || errors.notifications);

  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.replace('/worker');
    }
  }, [authLoading, isAdmin, router]);

  useEffect(() => {
    if (authLoading || !isAdmin) {
      return;
    }

    let cancelled = false;
    const runInitialLoad = async () => {
      try {
        const [m, b, n] = await Promise.allSettled([
          metricsApi.get(),
          bookingsApi.list({ limit: 5 }),
          notificationsApi.list(),
        ]);
        if (cancelled) return;

        const nextErrors: DashboardErrors = {};

        if (m.status === 'fulfilled') {
          setMetrics(m.value);
        } else {
          nextErrors.metrics = getErrorMessage(m.reason);
        }

        if (b.status === 'fulfilled') {
          setBookings(b.value);
        } else {
          nextErrors.bookings = getErrorMessage(b.reason);
        }

        if (n.status === 'fulfilled') {
          setNotifications(n.value.slice(0, 5));
        } else {
          nextErrors.notifications = getErrorMessage(n.reason);
        }

        setErrors(nextErrors);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    runInitialLoad();
    return () => { cancelled = true; };
  }, [authLoading, isAdmin]);

  useAdminRealtimeRefresh(
    (event: StreamEnvelope) =>
      isAdmin
      && (
        event.type.startsWith('booking.')
      || event.type.startsWith('notification.')
      || event.type.startsWith('worker.')
      ),
    () => {
      if (isAdmin) {
        void load();
      }
    },
  );

  if (authLoading || loading || !isAdmin) {
    return (
      <div className={styles.loadingCenter}>
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Dashboard</h1>
        <p className={styles.pageSub}>Live operational overview</p>
      </header>

      {hasAnyError && (
        <div className={styles.alertBanner} role="alert">
          <span>Some dashboard data could not be loaded.</span>
          <button type="button" className={styles.retryButton} onClick={() => void load()}>
            Retry all
          </button>
        </div>
      )}

      {/* KPI Row */}
      <section className={styles.kpiGrid} aria-label="Key metrics">
        <KpiCard
          icon={<ClipboardList size={20} />}
          label="Pending Reviews"
          value={metrics?.pending_reviews ?? '—'}
          accent={metrics && metrics.pending_reviews > 0 ? 'warning' : 'default'}
          description="Bookings awaiting admin decision"
        />
        <KpiCard
          icon={<Bell size={20} />}
          label="Queued Notifications"
          value={metrics?.queued_due_notifications ?? '—'}
          accent="default"
          description="Due notifications in dispatch queue"
        />
        <KpiCard
          icon={<AlertTriangle size={20} />}
          label="Reminder Failures"
          value={metrics?.reminder_failures ?? '—'}
          accent={metrics && metrics.reminder_failures > 0 ? 'danger' : 'default'}
          description="Failed reminder send attempts"
        />
        <KpiCard
          icon={<Wrench size={20} />}
          label="Failed Tool Calls"
          value={metrics?.failed_tool_calls ?? '—'}
          accent={metrics && metrics.failed_tool_calls > 0 ? 'danger' : 'default'}
          description="Agent tool errors in last cycle"
        />
      </section>
      {errors.metrics && (
        <p className={styles.sectionError}>
          Metrics load failed: {errors.metrics}
        </p>
      )}

      {/* Recent activity */}
      <div className={styles.recentGrid}>
        {/* Recent bookings */}
        <section className={styles.recentSection}>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>Recent Bookings</h2>
            <Link href="/bookings" className={styles.viewAll}>View all →</Link>
          </div>
          <div className={styles.tableWrapper}>
            {bookings.length === 0 ? (
              <p className={styles.empty}>No bookings yet.</p>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Phone</th>
                    <th>Type</th>
                    <th>Start</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {bookings.map((b) => (
                    <tr key={b.id}>
                      <td>
                        <Link href={`/bookings/${b.id}`} className={styles.link}>
                          {b.client_phone_e164 ?? b.client_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td>{b.booking_type ?? '—'}</td>
                      <td>
                        {b.scheduled_start_at
                          ? new Date(b.scheduled_start_at).toLocaleString('en-GB', {
                              dateStyle: 'short',
                              timeStyle: 'short',
                            })
                          : '—'}
                      </td>
                      <td>
                        <Badge color={bookingStatusColor(b.status)}>
                          {b.status.replace('_', ' ')}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {errors.bookings && (
            <div className={styles.widgetErrorRow}>
              <p className={styles.sectionError}>Bookings load failed: {errors.bookings}</p>
              <button
                type="button"
                className={styles.retryButton}
                onClick={() => void load()}
              >
                Retry
              </button>
            </div>
          )}
        </section>

        {/* Recent notifications */}
        <section className={styles.recentSection}>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>Recent Notifications</h2>
            <Link href="/notifications" className={styles.viewAll}>View all →</Link>
          </div>
          <div className={styles.tableWrapper}>
            {notifications.length === 0 ? (
              <p className={styles.empty}>No notifications in queue.</p>
            ) : (
              <ul className={styles.notifList}>
                {notifications.map((n) => (
                  <li key={n.id} className={styles.notifItem}>
                    <span className={styles.notifKey}>{n.template_key}</span>
                    <Badge
                      color={
                        n.status === 'dead_letter'
                          ? 'danger'
                          : n.status === 'retry_pending'
                          ? 'warning'
                          : n.status === 'sent'
                          ? 'success'
                          : 'default'
                      }
                    >
                      {n.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {errors.notifications && (
            <div className={styles.widgetErrorRow}>
              <p className={styles.sectionError}>
                Notifications load failed: {errors.notifications}
              </p>
              <button
                type="button"
                className={styles.retryButton}
                onClick={() => void load()}
              >
                Retry
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
