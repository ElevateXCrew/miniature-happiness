import styles from './EmptyState.module.css';

interface Props {
  icon?: string;
  title: string;
  description?: string;
}

export function EmptyState({ icon = '📭', title, description }: Props) {
  return (
    <div className={styles.wrapper}>
      <span className={styles.icon} aria-hidden>{icon}</span>
      <p className={styles.title}>{title}</p>
      {description && <p className={styles.desc}>{description}</p>}
    </div>
  );
}
