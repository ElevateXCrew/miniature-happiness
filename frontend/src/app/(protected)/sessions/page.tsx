import type { Metadata } from 'next';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Live Chat' };

export default function SessionsPage() {
  return (
    <SectionPlaceholder
      icon="💬"
      title="Live Chat"
      description="Active sessions list, live conversation monitor, and pause / resume automation controls."
      comingIn="Track 2"
    />
  );
}
