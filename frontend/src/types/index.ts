// ============================================================
// Shared TypeScript types for Alysha Admin Panel
// ============================================================

// ----------------------------------------------------------
// Auth
// ----------------------------------------------------------

export type UserRole = 'admin' | 'worker';

export interface User {
  id: string;
  email: string;
  role: UserRole;
  worker_id: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginResponse extends TokenPair {
  user: User;
}

// ----------------------------------------------------------
// Sections
// ----------------------------------------------------------

export type SectionKey =
  | 'dashboard'
  | 'live_chat'
  | 'bookings'
  | 'timeline'
  | 'media'
  | 'notifications'
  | 'schedule'
  | 'settings';

export type SectionMap = Record<SectionKey, boolean>;

// ----------------------------------------------------------
// Bookings
// ----------------------------------------------------------

export type BookingStatus =
  | 'collecting_info'
  | 'pending_review'
  | 'confirmed'
  | 'rejected'
  | 'cancelled'
  | 'completed';

export type BookingType = 'incall' | 'outcall';

export interface BookingSummary {
  id: string;
  status: BookingStatus;
  client_id: string;
  client_phone_e164: string | null;
  worker_id: string;
  scheduled_start_at: string | null;
  booking_type: BookingType | null;
  awaiting_review_from: string;
  created_at: string;
  updated_at: string;
}

export interface BookingDetail extends BookingSummary {
  session_id: string;
  scheduled_end_at: string | null;
  duration_minutes: number | null;
  client_age: number | null;
  client_ethnicity: string | null;
  client_name: string | null;
  outcall_address: string | null;
  price_total_gbp: string | null;
  advance_required_gbp: string | null;
  advance_received: boolean;
  confirmed_at: string | null;
  cancelled_at: string | null;
  completed_at: string | null;
  incall_address_sent_at: string | null;
  media_count: number;
  has_receipt: boolean;
}

// ----------------------------------------------------------
// Timeline
// ----------------------------------------------------------

export type TimelineItemKind = 'message' | 'audit' | 'notification' | 'media';

export interface TimelineItem {
  kind: TimelineItemKind;
  timestamp: string;
  id: string;
  [key: string]: unknown;
}

export interface TimelineResponse {
  booking_id: string;
  timeline: TimelineItem[];
}

// ----------------------------------------------------------
// Media
// ----------------------------------------------------------

export interface MediaItem {
  id: string;
  booking_id: string;
  channel: string;
  media_type: string;
  source_url: string | null;
  is_receipt: boolean;
  created_at: string;
}

// ----------------------------------------------------------
// Sessions
// ----------------------------------------------------------

export interface ActiveSession {
  id: string;
  client_id: string;
  worker_id: string;
  state: string;
  last_channel: string | null;
  active_booking_id: string | null;
}

// ----------------------------------------------------------
// Notifications
// ----------------------------------------------------------

export type NotificationStatus =
  | 'queued'
  | 'sent'
  | 'retry_pending'
  | 'dead_letter'
  | 'failed';

export interface NotificationItem {
  id: string;
  target_type: string;
  target_ref: string;
  template_key: string;
  status: NotificationStatus;
  send_at: string;
}

// ----------------------------------------------------------
// Metrics
// ----------------------------------------------------------

export interface Metrics {
  pending_reviews: number;
  queued_due_notifications: number;
  failed_tool_calls: number;
  reminder_failures: number;
}

// ----------------------------------------------------------
// Workers / Users
// ----------------------------------------------------------

export interface WorkerUser {
  id: string;
  email: string;
  is_active: boolean;
  role: UserRole;
  worker_id: string | null;
}

export interface WorkerSectionPermissions {
  user_id: string;
  sections: SectionMap;
}

export interface WorkerUpcomingBooking {
  id: string;
  status: BookingStatus;
  scheduled_start_at: string | null;
  duration_minutes: number | null;
  booking_type: BookingType | null;
  client_name: string | null;
}

export interface WorkerCommandResult {
  success: boolean;
  message: string;
}

// ----------------------------------------------------------
// API
// ----------------------------------------------------------

export interface ApiError {
  detail: string | string[];
}

export interface PaginationParams {
  offset?: number;
  limit?: number;
  status?: BookingStatus;
}

