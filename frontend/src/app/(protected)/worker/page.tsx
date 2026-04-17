import type { Metadata } from 'next';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Worker Portal' };

export default function WorkerPage() {
  return (
    <SectionPlaceholder
      icon="👜"
      title="Worker Portal"
      description="Upcoming bookings, approve / reject decisions, and operational commands for Alysha."
      comingIn="Track 3"
    />
  );
}
