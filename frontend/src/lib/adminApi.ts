// ============================================================
// Typed API helper functions — all backend calls go through here.
// Import `api` for raw fetch; use these wrappers in page/components.
// ============================================================

import { api } from './api';
import type {
  ActiveSession,
  BookingDetail,
  BookingStatus,
  BookingSummary,
  MediaItem,
  Metrics,
  NotificationItem,
  SectionKey,
  SectionMap,
  SessionMessage,
  TimelineResponse,
  WorkerCommandResult,
  WorkerSectionPermissions,
  WorkerUpcomingBooking,
  WorkerUser,
} from '@/types';

// ----------------------------------------------------------
// Metrics
// ----------------------------------------------------------

export const metricsApi = {
  get: () => api.get<Metrics>('/metrics'),
};

// ----------------------------------------------------------
// Admin — Bookings
// ----------------------------------------------------------

export const bookingsApi = {
  list: (params?: { status?: BookingStatus; offset?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return api.get<BookingSummary[]>(`/admin/bookings${query ? `?${query}` : ''}`);
  },

  get: (id: string) => api.get<BookingDetail>(`/admin/bookings/${id}`),

  timeline: (id: string) => api.get<TimelineResponse>(`/admin/bookings/${id}/timeline`),

  media: (id: string) => api.get<MediaItem[]>(`/admin/bookings/${id}/media`),

  approve: (id: string, note?: string) =>
    api.post<{ booking_id: string; status: string }>(
      `/admin/bookings/${id}/approve`,
      { note: note ?? null },
    ),

  reject: (id: string, note?: string) =>
    api.post<{ booking_id: string; status: string }>(
      `/admin/bookings/${id}/reject`,
      { note: note ?? null },
    ),

  cancel: (id: string, note?: string) =>
    api.post<{ booking_id: string; status: string }>(
      `/admin/bookings/${id}/cancel`,
      { note: note ?? null },
    ),

  markIncallAddressSent: (id: string) =>
    api.post(`/admin/bookings/${id}/incall-address-sent`),

  patch: (id: string, updates: Record<string, unknown>) =>
    api.patch(`/admin/bookings/${id}`, updates),
};

// ----------------------------------------------------------
// Admin — Media
// ----------------------------------------------------------

export const mediaApi = {
  markReceipt: (mediaId: string) =>
    api.post(`/admin/media/${mediaId}/mark-receipt`),
};

// ----------------------------------------------------------
// Admin — Sessions
// ----------------------------------------------------------

export const sessionsApi = {
  listActive: () => api.get<ActiveSession[]>('/admin/sessions/active'),

  getMessages: (sessionId: string) =>
    api.get<SessionMessage[]>(`/admin/sessions/${sessionId}/messages`),

  pause: () => api.post<{ paused: boolean }>('/admin/agent/pause'),

  resume: () => api.post<{ resumed: boolean }>('/admin/agent/resume'),
};

// ----------------------------------------------------------
// Admin — Notifications
// ----------------------------------------------------------

export const notificationsApi = {
  list: () => api.get<NotificationItem[]>('/admin/notifications'),

  runDispatch: () => api.post('/notifications/dispatch/run'),

  runReminders: () => api.post('/notifications/reminders/run'),
};

// ----------------------------------------------------------
// Admin — Workers / Sections
// ----------------------------------------------------------

export const workersApi = {
  list: () => api.get<WorkerUser[]>('/admin/users/workers'),

  getPermissions: (userId: string) =>
    api.get<WorkerSectionPermissions>(`/admin/users/${userId}/section-permissions`),

  updatePermissions: (userId: string, sections: Partial<Record<SectionKey, boolean>>) =>
    api.put<WorkerSectionPermissions>(`/admin/users/${userId}/section-permissions`, {
      sections,
    }),
};

// ----------------------------------------------------------
// Worker Portal  (worker_id is always the caller's own id)
// ----------------------------------------------------------

export const workerPortalApi = {
  upcomingBookings: (workerId: string) =>
    api.get<WorkerUpcomingBooking[]>(`/worker/bookings/upcoming?worker_id=${workerId}`),

  approve: (bookingId: string, workerId: string) =>
    api.post<{ booking_id: string; status: string }>(
      `/worker/bookings/${bookingId}/approve?worker_id=${workerId}`,
    ),

  reject: (bookingId: string, workerId: string) =>
    api.post<{ booking_id: string; status: string }>(
      `/worker/bookings/${bookingId}/reject?worker_id=${workerId}`,
    ),

  completeEarly: (bookingId: string, workerId: string) =>
    api.post<{ booking_id: string; status: string }>(
      `/worker/bookings/${bookingId}/complete-early?worker_id=${workerId}`,
    ),

  freeNow: (workerId: string) =>
    api.post<WorkerCommandResult>('/worker/availability/free-now', {
      worker_id: workerId,
      message_text: 'free now',
    }),

  sendMessage: (workerId: string, messageText: string) =>
    api.post<WorkerCommandResult>('/worker/messages', {
      worker_id: workerId,
      message_text: messageText,
    }),
};

