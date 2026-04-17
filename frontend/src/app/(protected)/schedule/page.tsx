import type { Metadata } from 'next';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Schedule' };

export default function SchedulePage() {
  return (
    <SectionPlaceholder
      icon="📅"
      title="Schedule"
      description="Worker availability and upcoming booking schedule view."
      comingIn="Track 3"
    />
  );
}
