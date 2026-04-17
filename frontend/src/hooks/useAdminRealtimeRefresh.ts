'use client';

import { useEffect } from 'react';
import { ADMIN_REALTIME_EVENT } from '@/context/AuthContext';
import { useAuth } from '@/context/AuthContext';
import type { StreamEnvelope } from '@/lib/realtime';

export function useAdminRealtimeRefresh(
  shouldRefresh: (event: StreamEnvelope) => boolean,
  onRefresh: () => void,
): void {
  const { isAdmin, isAuthenticated } = useAuth();

  useEffect(() => {
    if (!isAuthenticated || !isAdmin) return;

    const handler = (raw: Event) => {
      const event = (raw as CustomEvent<StreamEnvelope>).detail;
      if (!event) return;
      if (shouldRefresh(event)) {
        onRefresh();
      }
    };

    window.addEventListener(ADMIN_REALTIME_EVENT, handler);
    return () => {
      window.removeEventListener(ADMIN_REALTIME_EVENT, handler);
    };
  }, [isAdmin, isAuthenticated, onRefresh, shouldRefresh]);
}
