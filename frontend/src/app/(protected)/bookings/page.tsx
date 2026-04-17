import type { Metadata } from 'next';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Bookings' };

export default function BookingsPage() {
  return (
    <SectionPlaceholder
      icon="📋"
      title="Bookings"
      description="Booking queue with filters, quick actions (approve / reject / cancel), and pagination."
      comingIn="Track 2"
    />
  );
}
