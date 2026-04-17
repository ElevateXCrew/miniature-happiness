import styles from './Card.module.css';
import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
  glow?: boolean;
  padding?: 'sm' | 'md' | 'lg';
}

export function Card({ children, className = '', glow = false, padding = 'md' }: Props) {
  return (
    <div
      className={[
        styles.card,
        styles[`pad-${padding}`],
        glow ? styles.glow : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </div>
  );
}
