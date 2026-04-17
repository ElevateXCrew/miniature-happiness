'use client';

import { useCallback, useEffect, useState } from 'react';
import { workersApi } from '@/lib/adminApi';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import type { SectionKey, SectionMap, WorkerSectionPermissions, WorkerUser } from '@/types';
import styles from './page.module.css';

const SECTION_KEYS: SectionKey[] = [
  'dashboard', 'bookings', 'live_chat', 'media',
  'notifications', 'schedule', 'timeline', 'settings',
];

const SECTION_LABELS: Record<SectionKey, string> = {
  dashboard: 'Dashboard', bookings: 'Bookings', live_chat: 'Live Chat',
  media: 'Media', notifications: 'Notifications', schedule: 'Schedule',
  timeline: 'Timeline', settings: 'Settings',
};

export default function SettingsPage() {
  const [workers, setWorkers] = useState<WorkerUser[]>([]);
  const [perms, setPerms] = useState<Record<string, SectionMap>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  const loadWorkers = useCallback(async () => {
    setLoading(true);
    try {
      const list = await workersApi.list();
      setWorkers(list);
      const permMap: Record<string, SectionMap> = {};
      await Promise.all(
        list.map(async (w) => {
          const p: WorkerSectionPermissions = await workersApi.getPermissions(w.id);
          permMap[w.id] = p.sections;
        }),
      );
      setPerms(permMap);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadWorkers(); }, [loadWorkers]);

  const toggle = async (workerId: string, key: SectionKey, current: boolean) => {
    setSaving(workerId + key);
    const updated = { ...perms[workerId], [key]: !current };
    try {
      const res = await workersApi.updatePermissions(workerId, { [key]: !current });
      setPerms((prev) => ({ ...prev, [workerId]: res.sections }));
    } catch {
      // revert on failure
      setPerms((prev) => ({ ...prev, [workerId]: { ...updated, [key]: current } }));
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Settings</h1>
          <p className={styles.pageSub}>Worker section access controls</p>
        </div>
      </header>

      <div className={styles.tableCard}>
        {loading ? (
          <div className={styles.loadingRow}><Spinner /></div>
        ) : workers.length === 0 ? (
          <EmptyState icon="👤" title="No worker accounts found"
            description="Create a worker user to manage their section access." />
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Worker</th>
                  {SECTION_KEYS.map((k) => (
                    <th key={k} className={styles.sectionHead}>{SECTION_LABELS[k]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {workers.map((w) => {
                  const workerPerms = perms[w.id];
                  return (
                    <tr key={w.id}>
                      <td>
                        <div className={styles.workerCell}>
                          <span className={styles.workerEmail}>{w.email}</span>
                          <Badge color={w.is_active ? 'success' : 'default'}>
                            {w.is_active ? 'active' : 'inactive'}
                          </Badge>
                        </div>
                      </td>
                      {SECTION_KEYS.map((k) => {
                        const enabled = workerPerms?.[k] ?? false;
                        const isSaving = saving === w.id + k;
                        return (
                          <td key={k} className={styles.toggleCell}>
                            <button
                              id={`toggle-${w.id}-${k}`}
                              className={[styles.toggle, enabled ? styles.on : styles.off].join(' ')}
                              onClick={() => toggle(w.id, k, enabled)}
                              disabled={isSaving}
                              aria-label={`${enabled ? 'Disable' : 'Enable'} ${SECTION_LABELS[k]} for ${w.email}`}
                              aria-pressed={enabled}
                            >
                              {isSaving ? '…' : enabled ? '●' : '○'}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
