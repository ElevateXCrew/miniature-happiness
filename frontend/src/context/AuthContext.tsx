'use client';

// ============================================================
// AuthContext — global auth state, token management,
// section permissions, and session bootstrap.
// ============================================================

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import {
  api,
  clearTokens,
  getRefreshToken,
  storeTokens,
} from '@/lib/api';
import { openAuthenticatedSseStream, type StreamEnvelope } from '@/lib/realtime';
import type { SectionKey, SectionMap, User } from '@/types';

// ----------------------------------------------------------
// Types
// ----------------------------------------------------------

interface AuthState {
  user: User | null;
  sections: SectionMap | null;
  isLoading: boolean;        // true during initial bootstrap
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  isAdmin: boolean;
  hasSection: (key: SectionKey) => boolean;
}

export const ADMIN_REALTIME_EVENT = 'admin:realtime';

// ----------------------------------------------------------
// Default section map — all visible (admin) / empty
// ----------------------------------------------------------

const ALL_SECTIONS: SectionMap = {
  dashboard: true,
  live_chat: true,
  bookings: true,
  timeline: true,
  media: true,
  notifications: true,
  schedule: true,
  settings: true,
};

// ----------------------------------------------------------
// Context
// ----------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

// ----------------------------------------------------------
// Provider
// ----------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    sections: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const bootstrapped = useRef(false);

  // ---- helpers ----

  const fetchMeAndSections = useCallback(async (): Promise<{
    user: User;
    sections: SectionMap;
  }> => {
    const [meRes, sectionsRes] = await Promise.all([
      api.get<User>('/auth/me'),
      api.get<{ sections: SectionMap }>('/ui/sections'),
    ]);
    return { user: meRes, sections: sectionsRes.sections };
  }, []);

  const setAuthenticated = useCallback((user: User, sections: SectionMap) => {
    setState({
      user,
      sections,
      isLoading: false,
      isAuthenticated: true,
    });
  }, []);

  const refreshSections = useCallback(async () => {
    const sectionsRes = await api.get<{ sections: SectionMap }>('/ui/sections');
    setState((prev) =>
      prev.isAuthenticated
        ? {
            ...prev,
            sections: sectionsRes.sections,
          }
        : prev,
    );
  }, []);

  const setUnauthenticated = useCallback(() => {
    setState({
      user: null,
      sections: null,
      isLoading: false,
      isAuthenticated: false,
    });
  }, []);

  // ---- bootstrap on mount ----

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    const bootstrap = async () => {
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        setUnauthenticated();
        return;
      }

      try {
        // Refresh tokens first so access token is fresh
        const refreshed = await api.post<{
          access_token: string;
          refresh_token: string;
          token_type: string;
        }>('/auth/refresh', { refresh_token: refreshToken }, { skipAuth: true });

        storeTokens(refreshed);
        const { user, sections } = await fetchMeAndSections();
        setAuthenticated(user, sections);
      } catch {
        clearTokens();
        setUnauthenticated();
      }
    };

    bootstrap();
  }, [fetchMeAndSections, setAuthenticated, setUnauthenticated]);

  // ---- session expiry event from api.ts ----

  useEffect(() => {
    const handler = () => {
      clearTokens();
      setUnauthenticated();
    };
    window.addEventListener('auth:expired', handler);
    return () => window.removeEventListener('auth:expired', handler);
  }, [setUnauthenticated]);

  // ---- realtime stream (admin sync + worker permission updates) ----

  useEffect(() => {
    if (!state.isAuthenticated || !state.user) {
      return;
    }

    const path = state.user.role === 'admin' ? '/events/admin/stream' : '/events/worker/stream';

    const stop = openAuthenticatedSseStream({
      path,
      onEvent: (event: StreamEnvelope) => {
        if (state.user?.role === 'worker' && event.type === 'worker.permissions.updated') {
          void refreshSections();
        }

        if (typeof window !== 'undefined' && state.user?.role === 'admin') {
          window.dispatchEvent(new CustomEvent(ADMIN_REALTIME_EVENT, { detail: event }));
        }
      },
    });

    return () => {
      stop();
    };
  }, [refreshSections, state.isAuthenticated, state.user]);

  // ---- public actions ----

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.post<{
        access_token: string;
        refresh_token: string;
        token_type: string;
      }>('/auth/login', { email, password }, { skipAuth: true });

      storeTokens(res);
      const { user, sections } = await fetchMeAndSections();
      setAuthenticated(user, sections);
    },
    [fetchMeAndSections, setAuthenticated],
  );

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    try {
      if (refreshToken) {
        await api.post('/auth/logout', { refresh_token: refreshToken });
      }
    } catch {
      // best-effort
    }
    clearTokens();
    setUnauthenticated();
  }, [setUnauthenticated]);

  // ---- derived values ----

  const isAdmin = state.user?.role === 'admin';

  const hasSection = useCallback(
    (key: SectionKey): boolean => {
      if (!state.isAuthenticated) return false;
      if (isAdmin) return true; // admin always has all sections
      if (key === 'dashboard') return false;
      return state.sections?.[key] ?? false;
    },
    [state.isAuthenticated, state.sections, isAdmin],
  );

  const value: AuthContextValue = {
    ...state,
    login,
    logout,
    isAdmin,
    hasSection,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ----------------------------------------------------------
// Hook
// ----------------------------------------------------------

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
