'use client';

import { useCallback, useEffect, useState } from 'react';
import { notificationsApi } from '@/lib/adminApi';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import type { NotificationItem } from '@/types';
import styles from './page.module.css';

function notifColor(status: string): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'sent')          return 'success';
  if (status === 'retry_pending') return 'warning';
  if (status === 'dead_letter')   return 'danger';
  return 'default';
}

const fmt = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setNotifications(await notificationsApi.list()); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const runDispatch = async () => {
    setActionLoading('dispatch');
    await notificationsApi.runDispatch();
    setActionLoading(null);
    showToast('Dispatch run triggered.');
    load();
  };

  const runReminders = async () => {
    setActionLoading('reminders');
    await notificationsApi.runReminders();
    setActionLoading(null);
    showToast('Reminder run triggered.');
    load();
  };

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Notifications</h1>
          <p className={styles.pageSub}>Dispatch queue, retries and dead letters</p>
        </div>
        <div className={styles.controls}>
          <Button id="run-dispatch-btn" variant="secondary" size="sm"
            loading={actionLoading === 'dispatch'} onClick={runDispatch}>
            Run Dispatch
          </Button>
          <Button id="run-reminders-btn" variant="secondary" size="sm"
            loading={actionLoading === 'reminders'} onClick={runReminders}>
            Run Reminders
          </Button>
          <Button id="refresh-notifs-btn" variant="ghost" size="sm" onClick={load}>
            Refresh
          </Button>
        </div>
      </header>

      {toast && <div className={styles.toast} role="status">{toast}</div>}

      <div className={styles.tableCard}>
        {loading ? (
          <div className={styles.loadingRow}><Spinner /></div>
        ) : notifications.length === 0 ? (
          <EmptyState icon="🔔" title="Queue is empty" description="No due notifications at this time." />
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Template</th>
                  <th>Target</th>
                  <th>Ref</th>
                  <th>Send At</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {notifications.map((n) => (
                  <tr key={n.id}>
                    <td className={styles.mono}>{n.template_key}</td>
                    <td>{n.target_type}</td>
                    <td className={styles.mono}>{n.target_ref.slice(0, 12)}…</td>
                    <td className={styles.date}>{fmt(n.send_at)}</td>
                    <td>
                      <Badge color={notifColor(n.status)} dot>
                        {n.status.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
