import type { Metadata } from 'next';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Dashboard' };

export default function DashboardPage() {
  return (
    <SectionPlaceholder
      icon="⬛"
      title="Dashboard"
      description="KPI cards, pending reviews, and reliability highlights will live here."
      comingIn="Track 2"
    />
  );
}
