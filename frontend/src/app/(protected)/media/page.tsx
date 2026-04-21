'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ImageIcon, RefreshCw } from 'lucide-react';
import { mediaApi } from '@/lib/adminApi';
import { BASE_URL, getAccessToken } from '@/lib/api';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import type { MediaItem } from '@/types';
import styles from './page.module.css';

const REFRESH_MS = 15000;

const fmt = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });

export default function MediaPage() {
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const resolveApiUrl = useCallback((url: string) => {
    if (/^https?:\/\//i.test(url)) return url;
    return `${BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`;
  }, []);

  const buildPreviewUrls = useCallback(async (items: MediaItem[]) => {
    const token = getAccessToken();
    const next: Record<string, string> = {};

    await Promise.all(items.map(async (item) => {
      if (!item.source_url) return;

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

    setPreviewUrls((prev) => {
      Object.entries(prev).forEach(([id, url]) => {
        if (!(id in next) && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      return next;
    });
  }, [resolveApiUrl]);

  const loadMedia = useCallback(async (isRefresh: boolean) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await mediaApi.listAll({ limit: 500, offset: 0 });
      setMedia(data);
      await buildPreviewUrls(data);
    } finally {
      if (isRefresh) setRefreshing(false);
      else setLoading(false);
    }
  }, [buildPreviewUrls]);

  useEffect(() => {
    void loadMedia(false);
  }, [loadMedia]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadMedia(true);
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadMedia]);

  useEffect(() => {
    return () => {
      Object.values(previewUrls).forEach((url) => {
        if (url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
    };
  }, [previewUrls]);

  const grouped = useMemo(() => {
    const map = new Map<string, MediaItem[]>();
    for (const item of media) {
      const key = item.client_phone_e164 ?? item.client_id;
      const list = map.get(key) ?? [];
      list.push(item);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [media]);

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Media</h1>
          <p className={styles.pageSub}>All backend-saved client media grouped by phone number.</p>
        </div>
        <Button
          id="refresh-media-btn"
          variant="secondary"
          size="sm"
          loading={refreshing}
          onClick={() => void loadMedia(true)}
        >
          <RefreshCw size={14} /> Refresh
        </Button>
      </header>

      {loading ? (
        <div className={styles.loadingRow}><Spinner /></div>
      ) : grouped.length === 0 ? (
        <EmptyState
          icon={<ImageIcon size={40} />}
          title="No media yet"
          description="Incoming client images and receipts will appear here."
        />
      ) : (
        <div className={styles.groups}>
          {grouped.map(([phone, items]) => (
            <section key={phone} className={styles.groupCard}>
              <div className={styles.groupHeader}>
                <h2 className={styles.phone}>{phone}</h2>
                <Badge color="info">{items.length} media</Badge>
              </div>

              <div className={styles.mediaGrid}>
                {items.map((item) => (
                  <article key={item.id} className={styles.mediaCard}>
                    <div className={styles.mediaThumb}>
                      {item.source_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={previewUrls[item.id] ?? resolveApiUrl(item.source_url)}
                          alt={item.media_type ?? 'media'}
                          className={styles.mediaImg}
                        />
                      ) : (
                        <span className={styles.mediaPlaceholder}><ImageIcon size={24} /></span>
                      )}
                    </div>

                    <div className={styles.mediaMeta}>
                      <div className={styles.mediaLine}>{item.media_type ?? 'unknown'}</div>
                      <div className={styles.mediaLine}>{fmt(item.created_at)}</div>
                      <div className={styles.badges}>
                        {item.is_receipt && <Badge color="success">receipt</Badge>}
                        {item.channel && <Badge color="default">{item.channel}</Badge>}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
