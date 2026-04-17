'use client';

import { useCallback, useEffect, useState } from 'react';
import { sessionsApi } from '@/lib/adminApi';
import { useAdminRealtimeRefresh } from '@/hooks/useAdminRealtimeRefresh';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import type { ActiveSession } from '@/types';
import type { StreamEnvelope } from '@/lib/realtime';
import styles from './page.module.css';

const SESSION_STATE_COLOR: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
  collecting_info: 'info',
  awaiting_review: 'warning',
  confirmed:       'success',
  idle:            'default',
  paused:          'default',
};

export default function SessionsPage() {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [agentPaused, setAgentPaused] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await sessionsApi.listActive();
      setSessions(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useAdminRealtimeRefresh(
    (event: StreamEnvelope) =>
      event.type === 'booking.status_changed'
      || event.type === 'booking.submitted_for_review'
      || event.type.startsWith('worker.'),
    () => {
      void load();
    },
  );

  const pause = async () => {
    setActionLoading('pause');
    await sessionsApi.pause();
    setAgentPaused(true);
    setActionLoading(null);
  };

  const resume = async () => {
    setActionLoading('resume');
    await sessionsApi.resume();
    setAgentPaused(false);
    setActionLoading(null);
    load();
  };

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Live Chat</h1>
          <p className={styles.pageSub}>Active conversation sessions</p>
        </div>
        <div className={styles.controls}>
          {agentPaused ? (
            <Button id="resume-btn" variant="primary" size="sm"
              loading={actionLoading === 'resume'} onClick={resume}>
              ▶ Resume Agent
            </Button>
          ) : (
            <Button id="pause-btn" variant="danger" size="sm"
              loading={actionLoading === 'pause'} onClick={pause}>
              ⏸ Pause Agent
            </Button>
          )}
          <Button id="refresh-sessions-btn" variant="secondary" size="sm" onClick={load}>
            Refresh
          </Button>
        </div>
      </header>

      {agentPaused && (
        <div className={styles.pauseBanner} role="status">
          ⏸ Agent is paused — no new messages will be sent until resumed.
        </div>
      )}

      <div className={styles.tableCard}>
        {loading ? (
          <div className={styles.loadingRow}><Spinner /></div>
        ) : sessions.length === 0 ? (
          <EmptyState
            icon="💬"
            title="No active sessions"
            description="All conversations are currently idle."
          />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Session ID</th>
                <th>Client</th>
                <th>State</th>
                <th>Channel</th>
                <th>Active Booking</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td className={styles.mono}>{s.id.slice(0, 8)}…</td>
                  <td className={styles.mono}>{s.client_id.slice(0, 8)}…</td>
                  <td>
                    <Badge color={SESSION_STATE_COLOR[s.state] ?? 'default'}>
                      {s.state.replace(/_/g, ' ')}
                    </Badge>
                  </td>
                  <td>{s.last_channel ?? '—'}</td>
                  <td className={styles.mono}>
                    {s.active_booking_id
                      ? <a href={`/bookings/${s.active_booking_id}`} className={styles.link}>
                          {s.active_booking_id.slice(0, 8)}…
                        </a>
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
