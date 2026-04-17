'use client';

import { useState } from 'react';
import { workerPortalApi } from '@/lib/adminApi';
import { useAuth } from '@/context/AuthContext';
import { useSectionAccess } from '@/hooks/useAuth';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import styles from './page.module.css';

export default function SchedulePage() {
  const { user, isAdmin } = useAuth();
  const hasSchedule = useSectionAccess('schedule');
  const workerId = user?.worker_id ?? null;

  const [fromAt, setFromAt] = useState('');
  const [toAt, setToAt] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

  const doFreeNow = async () => {
    if (!workerId) return;
    setLoading('freeNow');
    const res = await workerPortalApi.freeNow(workerId);
    setResult(res.message);
    setLoading(null);
  };

  if (!hasSchedule && !isAdmin) {
    return (
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>Schedule</h1>
        </header>
        <EmptyState
          icon="🔒"
          title="Schedule section disabled"
          description="Your admin has not enabled the schedule section for your account."
        />
      </div>
    );
  }

  if (!workerId) {
    return (
      <div className={styles.page}>
        <EmptyState
          icon="⚠️"
          title="Worker account not linked"
          description="Your user account is not linked to a worker record."
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Schedule</h1>
          <p className={styles.pageSub}>Manage your availability</p>
        </div>
      </header>

      <div className={styles.cards}>
        {/* Free Now card */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>🟢 Free Now</h2>
          <p className={styles.cardDesc}>
            Signal that you are immediately available to take new bookings.
            This sends a &quot;free now&quot; availability command to the backend.
          </p>
          <Button
            id="schedule-free-now-btn"
            variant="primary"
            loading={loading === 'freeNow'}
            onClick={doFreeNow}
          >
            Mark as Free Now
          </Button>
          {result && <p className={styles.resultMsg}>{result}</p>}
        </div>
      </div>
    </div>
  );
}
