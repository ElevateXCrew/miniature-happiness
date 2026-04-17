'use client';

// ============================================================
// Sidebar — role-aware navigation with section guards.
// ============================================================

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  BookOpen,
  MessageCircle,
  ImageIcon,
  Bell,
  CalendarDays,
  Settings,
  BriefcaseBusiness,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import type { SectionKey } from '@/types';
import styles from './Sidebar.module.css';

// ----------------------------------------------------------
// Nav item definitions
// ----------------------------------------------------------

interface NavItem {
  label: string;
  href: string;
  sectionKey?: SectionKey;
  adminOnly?: boolean;
  workerOnly?: boolean;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard',     href: '/dashboard',     sectionKey: 'dashboard',     icon: <LayoutDashboard size={18} /> },
  { label: 'Bookings',      href: '/bookings',       sectionKey: 'bookings',      icon: <BookOpen size={18} /> },
  { label: 'Live Chat',     href: '/sessions',       sectionKey: 'live_chat',     icon: <MessageCircle size={18} /> },
  { label: 'Media',         href: '/media',          sectionKey: 'media',         icon: <ImageIcon size={18} /> },
  { label: 'Notifications', href: '/notifications',  sectionKey: 'notifications', icon: <Bell size={18} /> },
  { label: 'Schedule',      href: '/schedule',       sectionKey: 'schedule',      icon: <CalendarDays size={18} /> },
  { label: 'Settings',      href: '/settings',       adminOnly: true,             icon: <Settings size={18} /> },
  { label: 'Worker Portal', href: '/worker',         workerOnly: true,            icon: <BriefcaseBusiness size={18} /> },
];

// ----------------------------------------------------------
// Component
// ----------------------------------------------------------

export function Sidebar() {
  const { isAdmin, hasSection, user } = useAuth();
  const pathname = usePathname();

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (item.adminOnly) return isAdmin;
    if (item.workerOnly) return !isAdmin; // only visible to workers
    if (item.sectionKey) return hasSection(item.sectionKey);
    return true;
  });

  return (
    <aside className={styles.sidebar} aria-label="Main navigation">
      {/* Logo / brand */}
      <div className={styles.brand}>
        <span className={styles.brandLogo}>✦</span>
        <span className={styles.brandName}>Alysha</span>
        <span className={styles.brandRole}>
          {isAdmin ? 'Admin' : 'Worker'}
        </span>
      </div>

      {/* Nav */}
      <nav className={styles.nav}>
        {visibleItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <Link
              key={item.href}
              href={item.href}
              id={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
              className={[styles.navItem, isActive ? styles.active : ''].join(' ')}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className={styles.navIcon} aria-hidden>
                {item.icon}
              </span>
              <span className={styles.navLabel}>{item.label}</span>
              {isActive && <span className={styles.activeIndicator} />}
            </Link>
          );
        })}
      </nav>

      {/* Footer: user info */}
      <div className={styles.sidebarFooter}>
        <div className={styles.userInfo}>
          <span className={styles.userAvatar}>
            {user?.email?.[0]?.toUpperCase() ?? '?'}
          </span>
          <div className={styles.userDetails}>
            <span className={styles.userEmail} title={user?.email}>
              {user?.email}
            </span>
            <span className={styles.userRoleBadge}>
              {user?.role ?? '—'}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}
