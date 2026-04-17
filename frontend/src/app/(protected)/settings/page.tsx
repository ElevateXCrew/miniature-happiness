import type { Metadata } from 'next';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Settings' };

export default function SettingsPage() {
  return (
    <SectionPlaceholder
      icon="⚙️"
      title="Settings"
      description="Worker access management — toggle section visibility per worker. Admin only."
      comingIn="Track 2"
    />
  );
}
