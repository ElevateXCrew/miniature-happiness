'use client';

import { useAuth } from '@/context/AuthContext';
import type { SectionKey } from '@/types';

// Re-export for convenience
export { useAuth };

/**
 * Returns whether the current user has access to a given section key.
 * Admins always return true.
 */
export function useSectionAccess(key: SectionKey): boolean {
  const { hasSection } = useAuth();
  return hasSection(key);
}
