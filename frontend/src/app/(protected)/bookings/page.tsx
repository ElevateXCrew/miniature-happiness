'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ClipboardList } from 'lucide-react';
import { bookingsApi } from '@/lib/adminApi';
import { useAdminRealtimeRefresh } from '@/hooks/useAdminRealtimeRefresh';
import { Badge, bookingStatusColor } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import type { BookingStatus, BookingSummary } from '@/types';
import type { StreamEnvelope } from '@/lib/realtime';
import styles from './page.module.css';

const LIMIT = 20;

const ALL_STATUSES: BookingStatus[] = [
  'pending_review',
  'confirmed',
  'draft',
  'rejected',
  'cancelled',
  'completed',
];

export default function BookingsPage() {
  const router = useRouter();
  const [bookings, setBookings] = useState<BookingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<BookingStatus | ''>('');
  const [offset, setOffset] = useState(0);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchBookings = useCallback(async () => {
    setLoading(true);
    try {
      const data = await bookingsApi.list({
        status: filter || undefined,
        offset,
        limit: LIMIT,
      });
      setBookings(data);
    } finally {
      setLoading(false);
    }
  }, [filter, offset]);

  useEffect(() => { fetchBookings(); }, [fetchBookings]);

  useAdminRealtimeRefresh(
    (event: StreamEnvelope) =>
      event.type.startsWith('booking.') || event.type.startsWith('worker.'),
    () => {
      void fetchBookings();
    },
  );

  const doAction = async (
    id: string,
    action: 'approve' | 'reject' | 'cancel',
  ) => {
    setActionLoading(id + action);
    try {
      if (action === 'approve') await bookingsApi.approve(id);
      else if (action === 'reject') await bookingsApi.reject(id);
      else await bookingsApi.cancel(id);
      await fetchBookings();
    } finally {
      setActionLoading(null);
    }
  };

  const fmt = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })
      : '—';

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Bookings</h1>
          <p className={styles.pageSub}>Manage all booking requests</p>
        </div>
      </header>

      {/* Filters */}
      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel} htmlFor="status-filter">Status</label>
          <select
            id="status-filter"
            className={styles.select}
            value={filter}
            onChange={(e) => { setFilter(e.target.value as BookingStatus | ''); setOffset(0); }}
          >
            <option value="">All statuses</option>
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className={styles.tableCard}>
        {loading ? (
          <div className={styles.loadingRow}><Spinner /></div>
        ) : bookings.length === 0 ? (
          <EmptyState icon={<ClipboardList size={40} />} title="No bookings found" description="Try changing your filter." />
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Type</th>
                  <th>Start</th>
                  <th>Status</th>
                  <th>Review</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {bookings.map((b) => (
                  <tr
                    key={b.id}
                    className={styles.row}
                    onClick={() => router.push(`/bookings/${b.id}`)}
                  >
                    <td className={styles.phone}>
                      {b.client_phone_e164 ?? b.client_id.slice(0, 8)}
                    </td>
                    <td>{b.booking_type ?? '—'}</td>
                    <td className={styles.date}>{fmt(b.scheduled_start_at)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <Badge color={bookingStatusColor(b.status)}>
                        {b.status.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td className={styles.muted}>{b.awaiting_review_from}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {b.status === 'pending_review' && (
                        <div className={styles.actions}>
                          <Button
                            id={`approve-${b.id}`}
                            variant="secondary"
                            size="sm"
                            loading={actionLoading === b.id + 'approve'}
                            onClick={() => doAction(b.id, 'approve')}
                          >
                            Approve
                          </Button>
                          <Button
                            id={`reject-${b.id}`}
                            variant="danger"
                            size="sm"
                            loading={actionLoading === b.id + 'reject'}
                            onClick={() => doAction(b.id, 'reject')}
                          >
                            Reject
                          </Button>
                          <Button
                            id={`cancel-${b.id}`}
                            variant="ghost"
                            size="sm"
                            loading={actionLoading === b.id + 'cancel'}
                            onClick={() => doAction(b.id, 'cancel')}
                          >
                            Cancel
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      <div className={styles.pagination}>
        <Button
          id="prev-page"
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - LIMIT))}
        >
          ← Prev
        </Button>
        <span className={styles.pageInfo}>
          {offset + 1}–{offset + bookings.length}
        </span>
        <Button
          id="next-page"
          variant="secondary"
          size="sm"
          disabled={bookings.length < LIMIT}
          onClick={() => setOffset(offset + LIMIT)}
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
