'use client';

import React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { MessageCircle, FileText, Bell, ImageIcon, Dot } from 'lucide-react';
import { bookingsApi, mediaApi } from '@/lib/adminApi';
import { BASE_URL, getAccessToken } from '@/lib/api';
import { Badge, bookingStatusColor } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import type { BookingDetail, MediaItem, TimelineItem } from '@/types';
import styles from './page.module.css';

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const fmt = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
    : '—';

function timelineIcon(kind: TimelineItem['kind']): React.ReactNode {
  switch (kind) {
    case 'message':      return <MessageCircle size={14} />;
    case 'audit':        return <FileText size={14} />;
    case 'notification': return <Bell size={14} />;
    case 'media':        return <ImageIcon size={14} />;
    default:             return <Dot size={14} />;
  }
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function BookingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [booking, setBooking] = useState<BookingDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [mediaPreviewUrls, setMediaPreviewUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'timeline' | 'media'>('timeline');

  const resolveApiUrl = useCallback((url: string) => {
    if (/^https?:\/\//i.test(url)) return url;
    return `${BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`;
  }, []);

  const buildMediaPreviewUrls = useCallback(async (items: MediaItem[]) => {
    const token = getAccessToken();
    const next: Record<string, string> = {};

    await Promise.all(items.map(async (item) => {
      if (!item.source_url) return;

      // Auth-protected backend media endpoint must be fetched with bearer token,
      // then rendered via object URL.
      if (item.source_url.startsWith('/admin/media/')) {
        if (!token) return;
        try {
          const res = await fetch(resolveApiUrl(item.source_url), {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) return;
          const blob = await res.blob();
          next[item.id] = URL.createObjectURL(blob);
          return;
        } catch {
          return;
        }
      }

      next[item.id] = resolveApiUrl(item.source_url);
    }));

    setMediaPreviewUrls((prev) => {
      Object.entries(prev).forEach(([id, url]) => {
        if (!(id in next) && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      return next;
    });
  }, [resolveApiUrl]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [b, t, m] = await Promise.all([
        bookingsApi.get(id),
        bookingsApi.timeline(id),
        bookingsApi.media(id),
      ]);
      setBooking(b);
      setTimeline(t.timeline);
      setMedia(m);
      await buildMediaPreviewUrls(m);
    } finally {
      setLoading(false);
    }
  }, [buildMediaPreviewUrls, id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    return () => {
      Object.values(mediaPreviewUrls).forEach((url) => {
        if (url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
    };
  }, [mediaPreviewUrls]);

  const doAction = async (action: 'approve' | 'reject' | 'cancel') => {
    if (!booking) return;
    setActionLoading(action);
    try {
      if (action === 'approve') await bookingsApi.approve(id);
      else if (action === 'reject') await bookingsApi.reject(id);
      else await bookingsApi.cancel(id);
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  const doMarkReceipt = async (mediaId: string) => {
    setActionLoading('receipt-' + mediaId);
    try {
      await mediaApi.markReceipt(mediaId);
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  const doMarkIncall = async () => {
    setActionLoading('incall');
    try {
      await bookingsApi.markIncallAddressSent(id);
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return <div className={styles.loadingCenter}><Spinner size="lg" /></div>;
  }

  if (!booking) {
    return (
      <div className={styles.error}>
        <p>Booking not found.</p>
        <Button variant="secondary" size="sm" onClick={() => router.back()}>← Back</Button>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* Header */}
      <header className={styles.header}>
        <button className={styles.back} onClick={() => router.push('/bookings')}>
          ← Bookings
        </button>
        <div className={styles.headerRight}>
          <Badge color={bookingStatusColor(booking.status)}>
            {booking.status.replace(/_/g, ' ')}
          </Badge>
          {booking.status === 'pending_review' && (
            <div className={styles.headerActions}>
              <Button id="approve-btn" variant="primary" size="sm"
                loading={actionLoading === 'approve'}
                onClick={() => doAction('approve')}>Approve</Button>
              <Button id="reject-btn" variant="danger" size="sm"
                loading={actionLoading === 'reject'}
                onClick={() => doAction('reject')}>Reject</Button>
              <Button id="cancel-btn" variant="ghost" size="sm"
                loading={actionLoading === 'cancel'}
                onClick={() => doAction('cancel')}>Cancel</Button>
            </div>
          )}
        </div>
      </header>

      <div className={styles.layout}>
        {/* ── Detail panel ── */}
        <aside className={styles.detailPanel}>
          <h2 className={styles.panelTitle}>Booking Details</h2>

          <dl className={styles.fields}>
            <Field label="Client" value={booking.client_phone_e164 ?? booking.client_id} mono />
            <Field label="Type" value={booking.booking_type ?? '—'} />
            <Field label="Start" value={fmt(booking.scheduled_start_at)} />
            <Field label="End" value={fmt(booking.scheduled_end_at)} />
            <Field label="Duration" value={booking.duration_minutes ? `${booking.duration_minutes} min` : '—'} />
            <Field label="Age" value={booking.client_age ?? '—'} />
            <Field label="Ethnicity" value={booking.client_ethnicity ?? '—'} />
            <Field label="Name" value={booking.client_name ?? '—'} />
            {booking.booking_type === 'outcall' && (
              <>
                <Field label="Address" value={booking.outcall_address ?? '—'} />
                <Field label="Advance required" value={booking.advance_required_gbp ? `£${booking.advance_required_gbp}` : '—'} />
                <Field label="Advance received"
                  value={<Badge color={booking.advance_received ? 'success' : 'warning'}>{booking.advance_received ? 'Yes' : 'No'}</Badge>} />
              </>
            )}
            {booking.booking_type === 'incall' && (
              <div className={styles.incallRow}>
                <Field label="Address sent" value={booking.incall_address_sent_at ? fmt(booking.incall_address_sent_at) : 'Not yet'} />
                {!booking.incall_address_sent_at && booking.status === 'confirmed' && (
                  <Button id="incall-sent-btn" variant="secondary" size="sm"
                    loading={actionLoading === 'incall'}
                    onClick={doMarkIncall}>
                    Mark sent
                  </Button>
                )}
              </div>
            )}
            <Field label="Price" value={booking.price_total_gbp ? `£${booking.price_total_gbp}` : '—'} />
            <Field label="Has receipt"
              value={<Badge color={booking.has_receipt ? 'success' : 'default'}>{booking.has_receipt ? 'Yes' : 'No'}</Badge>} />
            <Field label="Media" value={booking.media_count} />
            <Field label="Awaiting" value={booking.awaiting_review_from} />
            <Field label="Created" value={fmt(booking.created_at)} />
            <Field label="Updated" value={fmt(booking.updated_at)} />
          </dl>
        </aside>

        {/* ── Timeline / Media tabs ── */}
        <main className={styles.main}>
          {/* Tabs */}
          <div className={styles.tabs}>
            <button
              id="tab-timeline"
              className={[styles.tab, activeTab === 'timeline' ? styles.activeTab : ''].join(' ')}
              onClick={() => setActiveTab('timeline')}
            >
              Timeline
              <span className={styles.tabCount}>{timeline.length}</span>
            </button>
            <button
              id="tab-media"
              className={[styles.tab, activeTab === 'media' ? styles.activeTab : ''].join(' ')}
              onClick={() => setActiveTab('media')}
            >
              Media
              <span className={styles.tabCount}>{media.length}</span>
            </button>
          </div>

          {/* Timeline */}
          {activeTab === 'timeline' && (
            <div className={styles.timeline}>
              {timeline.length === 0 ? (
                <p className={styles.empty}>No timeline events yet.</p>
              ) : (
                timeline.map((item) => (
                  <div key={item.id} className={[styles.timelineItem, styles[item.kind]].join(' ')}>
                    <span className={styles.tlIcon}>{timelineIcon(item.kind)}</span>
                    <div className={styles.tlContent}>
                      <div className={styles.tlMeta}>
                        <span className={styles.tlKind}>{item.kind}</span>
                        <span className={styles.tlTime}>{fmt(item.timestamp)}</span>
                      </div>
                      {item.kind === 'message' && (
                        <p className={styles.tlBody}>{item.body as string}</p>
                      )}
                      {item.kind === 'audit' && (
                        <p className={styles.tlBody}>{item.event_type as string}</p>
                      )}
                      {item.kind === 'notification' && (
                        <p className={styles.tlBody}>
                          {item.template_key as string} — <Badge color="default">{item.status as string}</Badge>
                        </p>
                      )}
                      {item.kind === 'media' && (
                        <p className={styles.tlBody}>
                          {item.media_type as string}
                          {Boolean(item.is_receipt) && <Badge color="success">receipt</Badge>}
                        </p>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Media Gallery */}
          {activeTab === 'media' && (
            <div className={styles.mediaGrid}>
              {media.length === 0 ? (
                <p className={styles.empty}>No media attached to this booking.</p>
              ) : (
                media.map((m) => (
                  <div key={m.id} className={styles.mediaCard}>
                    <div className={styles.mediaThumb}>
                      {m.source_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={mediaPreviewUrls[m.id] ?? resolveApiUrl(m.source_url)}
                          alt={m.media_type ?? 'media'}
                          className={styles.mediaImg}
                        />
                      ) : (
                        <span className={styles.mediaPlaceholder}><ImageIcon size={32} /></span>
                      )}
                    </div>
                    <div className={styles.mediaMeta}>
                      <span className={styles.mediaType}>{m.media_type}</span>
                      {m.is_receipt ? (
                        <Badge color="success">receipt</Badge>
                      ) : (
                        <Button
                          id={`mark-receipt-${m.id}`}
                          variant="secondary"
                          size="sm"
                          loading={actionLoading === 'receipt-' + m.id}
                          onClick={() => doMarkReceipt(m.id)}
                        >
                          Mark receipt
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Field helper                                                        */
/* ------------------------------------------------------------------ */

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <>
      <dt className={styles.fieldLabel}>{label}</dt>
      <dd className={[styles.fieldValue, mono ? styles.mono : ''].filter(Boolean).join(' ')}>
        {value}
      </dd>
    </>
  );
}
