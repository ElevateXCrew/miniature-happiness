import React from 'react';
import styles from './KpiCard.module.css';

interface Props {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  accent?: 'default' | 'warning' | 'danger' | 'success';
  description?: string;
}

export function KpiCard({ label, value, icon, accent = 'default', description }: Props) {
  return (
    <div className={[styles.card, styles[accent]].join(' ')}>
      <div className={styles.top}>
        <span className={styles.icon} aria-hidden>{icon}</span>
        <span className={styles.value}>{value}</span>
      </div>
      <p className={styles.label}>{label}</p>
      {description && <p className={styles.desc}>{description}</p>}
    </div>
  );
}
