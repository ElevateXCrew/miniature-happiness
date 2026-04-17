import type { Metadata } from 'next';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Notifications' };

export default function NotificationsPage() {
  return (
    <SectionPlaceholder
      icon="🔔"
      title="Notifications"
      description="Queued, sent, retry_pending, and dead_letter notifications with manual dispatch controls."
      comingIn="Track 2"
    />
  );
}
