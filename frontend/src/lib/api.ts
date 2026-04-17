// ============================================================
// API client — fetch wrapper with auth token injection,
// automatic 401 → refresh → retry, and error normalisation.
// ============================================================

import type { TokenPair } from '@/types';

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ----------------------------------------------------------
// Token storage helpers (localStorage — client-side only)
// ----------------------------------------------------------

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('access_token');
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('refresh_token');
}

export function storeTokens(tokens: { access_token: string; refresh_token: string }): void {
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

// ----------------------------------------------------------
// Low-level refresh (no interceptor — used inside interceptor)
// ----------------------------------------------------------

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) {
      clearTokens();
      return null;
    }

    const data: TokenPair = await res.json();
    storeTokens(data);
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

export async function tryRefreshSession(): Promise<boolean> {
  const accessToken = await refreshAccessToken();
  if (accessToken) return true;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('auth:expired'));
  }
  return false;
}

// ----------------------------------------------------------
// Core fetch wrapper
// ----------------------------------------------------------

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  skipAuth?: boolean;
  _retry?: boolean; // internal flag for refresh retry
}

export class ApiResponseError extends Error {
  status: number;
  detail: string | string[];

  constructor(status: number, detail: string | string[]) {
    super(typeof detail === 'string' ? detail : detail.join(', '));
    this.status = status;
    this.detail = detail;
  }
}

function decodeJwtRole(token: string | null): string {
  if (!token) return 'anonymous';
  try {
    const payload = token.split('.')[1];
    if (!payload) return 'unknown';
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
    const decoded = atob(padded);
    const parsed = JSON.parse(decoded) as { role?: string };
    return parsed.role ?? 'unknown';
  } catch {
    return 'unknown';
  }
}

function shouldLogFailure(path: string, status: number): boolean {
  // Expected during session bootstrap with stale/rotated refresh tokens.
  if (path === '/auth/refresh' && status === 401) {
    return false;
  }
  return true;
}

function logApiFailure(path: string, status: number, detail: string | string[]): void {
  if (!shouldLogFailure(path, status)) {
    return;
  }

  const role = decodeJwtRole(getAccessToken());
  console.warn('[api] request failed', {
    endpoint: path,
    status,
    role,
    detail,
  });
}

async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth = false, _retry = false, ...init } = options;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  };

  if (!skipAuth) {
    const token = getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    logApiFailure(path, 0, 'Network error');
    throw new ApiResponseError(
      0,
      `Network error while contacting server (${BASE_URL}).`,
    );
  }

  // Auto-refresh on 401
  if (res.status === 401 && !_retry && !skipAuth) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return apiFetch<T>(path, { ...options, _retry: true });
    }
    // Refresh failed — dispatch redirect event for AuthContext to catch
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:expired'));
    }
    throw new ApiResponseError(401, 'Session expired. Please log in again.');
  }

  if (!res.ok) {
    let detail: string | string[] = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      detail = json.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    logApiFailure(path, res.status, detail);
    throw new ApiResponseError(res.status, detail);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

// ----------------------------------------------------------
// Exported API methods
// ----------------------------------------------------------

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'POST', body }),

  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'PATCH', body }),

  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'PUT', body }),

  delete: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'DELETE' }),
};
