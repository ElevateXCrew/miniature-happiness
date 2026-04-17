'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ClipboardList, Bell, AlertTriangle, Wrench } from 'lucide-react';
import { metricsApi, bookingsApi, notificationsApi } from '@/lib/adminApi';
import { useAdminRealtimeRefresh } from '@/hooks/useAdminRealtimeRefresh';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { Badge, bookingStatusColor } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import type { Metrics, BookingSummary, NotificationItem } from '@/types';
import type { StreamEnvelope } from '@/lib/realtime';
import styles from './page.module.css';

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [bookings, setBookings] = useState<BookingSummary[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [m, b, n] = await Promise.all([
      metricsApi.get(),
      bookingsApi.list({ limit: 5 }),
      notificationsApi.list(),
    ]);
    setMetrics(m);
    setBookings(b);
    setNotifications(n.slice(0, 5));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const runInitialLoad = async () => {
      try {
        const [m, b, n] = await Promise.all([
          metricsApi.get(),
          bookingsApi.list({ limit: 5 }),
          notificationsApi.list(),
        ]);
        if (cancelled) return;
        setMetrics(m);
        setBookings(b);
        setNotifications(n.slice(0, 5));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    runInitialLoad();
    return () => { cancelled = true; };
  }, []);

  useAdminRealtimeRefresh(
    (event: StreamEnvelope) =>
      event.type.startsWith('booking.')
      || event.type.startsWith('notification.')
      || event.type.startsWith('worker.'),
    () => {
      void load();
    },
  );

  if (loading) {
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
        </section>
      </div>
    </div>
  );
}
