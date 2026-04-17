import styles from './SectionPlaceholder.module.css';

interface Props {
  title: string;
  description: string;
  icon: string;
  comingIn?: string;
}

export function SectionPlaceholder({ title, description, icon, comingIn }: Props) {
  return (
    <div className={styles.wrapper}>
      <div className={styles.blob} aria-hidden />
      <div className={styles.content}>
        <span className={styles.icon} aria-hidden>{icon}</span>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.description}>{description}</p>
        {comingIn && (
          <span className={styles.badge}>Full UI in {comingIn}</span>
        )}
      </div>
    </div>
  );
}
