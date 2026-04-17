'use client';

// ============================================================
// AuthGuard — blocks unauthenticated access.
// Redirects to /login if not authenticated.
// Shows full-screen spinner during bootstrap.
// ============================================================

import { useEffect, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { Spinner } from '@/components/ui/Spinner';
import type { SectionKey } from '@/types';
import styles from './AuthGuard.module.css';

interface Props {
  children: ReactNode;
  /** If provided, user must have this section enabled (or be admin). */
  requiredSection?: SectionKey;
}

export function AuthGuard({ children, requiredSection }: Props) {
  const { isLoading, isAuthenticated, hasSection } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated) {
      router.replace('/login');
      return;
    }

    if (requiredSection && !hasSection(requiredSection)) {
      router.replace('/dashboard');
    }
  }, [isLoading, isAuthenticated, requiredSection, hasSection, router]);

  if (isLoading) {
    return (
      <div className={styles.screen}>
        <Spinner size="lg" label="Loading session…" />
      </div>
    );
  }

  if (!isAuthenticated) return null;
  if (requiredSection && !hasSection(requiredSection)) return null;

  return <>{children}</>;
}
