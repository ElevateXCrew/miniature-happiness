import type { Metadata } from 'next';
import { LoginForm } from '@/components/auth/LoginForm';
import styles from './page.module.css';

export const metadata: Metadata = {
  title: 'Sign In',
  description: 'Sign in to the Alysha Admin Panel.',
};

export default function LoginPage() {
  return (
    <div className={styles.page}>
      {/* Background glow blobs */}
      <div className={styles.blob1} aria-hidden />
      <div className={styles.blob2} aria-hidden />

      <main className={styles.card} aria-label="Login">
        <div className={styles.header}>
          <span className={styles.logo} aria-hidden>✦</span>
          <h1 className={styles.title}>Alysha</h1>
          <p className={styles.subtitle}>Admin &amp; Worker Panel</p>
        </div>

        <LoginForm />

        <p className={styles.hint}>
          Access is restricted to authorised personnel only.
        </p>
      </main>
    </div>
  );
}
