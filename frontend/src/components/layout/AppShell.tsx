import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import styles from './AppShell.module.css';

interface Props {
  children: ReactNode;
  pageTitle?: string;
}

export function AppShell({ children, pageTitle }: Props) {
  return (
    <div className={styles.shell}>
      <Sidebar />
      <div className={styles.content}>
        <TopBar title={pageTitle} />
        <main className={styles.main} id="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
