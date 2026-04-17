'use client';

import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/Button';
import styles from './TopBar.module.css';

interface Props {
  title?: string;
}

export function TopBar({ title }: Props) {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  return (
    <header className={styles.topbar} role="banner">
      <div className={styles.left}>
        {title && <h1 className={styles.title}>{title}</h1>}
      </div>

      <div className={styles.right}>
        {user && (
          <span className={styles.userLabel} aria-label="Logged in as">
            {user.email}
          </span>
        )}
        <Button
          id="logout-btn"
          variant="ghost"
          size="sm"
          onClick={handleLogout}
          aria-label="Log out"
        >
          Log out
        </Button>
      </div>
    </header>
  );
}
