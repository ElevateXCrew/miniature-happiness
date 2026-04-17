import type { Metadata } from 'next';
import { ImageIcon } from 'lucide-react';
import { SectionPlaceholder } from '@/components/ui/SectionPlaceholder';

export const metadata: Metadata = { title: 'Media' };

export default function MediaPage() {
  return (
    <SectionPlaceholder
      icon={<ImageIcon size={40} />}
      title="Media & Receipts"
      description="Media gallery per booking with receipt badge and manual mark-receipt action."
      comingIn="Track 2"
    />
  );
}
