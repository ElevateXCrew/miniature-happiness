import styles from './Badge.module.css';
import type { ReactNode } from 'react';

export type BadgeColor = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'accent';

interface Props {
  children: ReactNode;
  color?: BadgeColor;
  dot?: boolean;
}

export function Badge({ children, color = 'default', dot = false }: Props) {
  return (
    <span className={[styles.badge, styles[color]].join(' ')}>
      {dot && <span className={styles.dot} />}
      {children}
    </span>
  );
}

export function bookingStatusColor(status: string): BadgeColor {
  switch (status) {
    case 'confirmed':   return 'success';
    case 'pending_review': return 'warning';
    case 'rejected':
    case 'cancelled':  return 'danger';
    case 'completed':  return 'info';
    default:           return 'default';
  }
}
