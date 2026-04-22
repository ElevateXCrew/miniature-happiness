'use client';

import React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Play, Pause, MessageCircle, X, RefreshCw, Trash2 } from 'lucide-react';
import { sessionsApi } from '@/lib/adminApi';
import { useAdminRealtimeRefresh } from '@/hooks/useAdminRealtimeRefresh';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import type { ActiveSession, SessionMessage } from '@/types';
import type { StreamEnvelope } from '@/lib/realtime';
import styles from './page.module.css';

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const fmt = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })
    : '—';

const SESSION_STATE_COLOR: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
  collecting:                'info',
  collecting_info:           'info',
  awaiting_client_confirmation: 'warning',
  awaiting_review:           'warning',
  confirmed:                 'success',
  idle:                      'default',
  paused:                    'default',
};

/* ------------------------------------------------------------------ */
/* Chat Panel                                                           */
/* ------------------------------------------------------------------ */

function ChatPanel({
  session,
  onClose,
}: {
  session: ActiveSession;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await sessionsApi.getMessages(session.id);
      setMessages(data);
    } finally {
      setLoading(false);
    }
  }, [session.id]);

  const clearHistory = useCallback(async () => {
    const confirmed = window.confirm(
      'Delete this full chat history? This will remove messages, draft bookings, and confirmed bookings for this session. This cannot be undone.',
    );
    if (!confirmed) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      await sessionsApi.clearMessages(session.id);
      setMessages([]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete chat history.';
      setDeleteError(msg);
    } finally {
      setDeleting(false);
    }
  }, [session.id]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!loading) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading]);

  const label = session.client_phone_e164 ?? session.client_id.slice(0, 8) + '…';

  return (
    <div className={styles.chatPanel}>
      <div className={styles.chatHeader}>
        <div className={styles.chatHeaderLeft}>
          <MessageCircle size={16} />
          <span className={styles.chatTitle}>{label}</span>
          <Badge color={SESSION_STATE_COLOR[session.state] ?? 'default'}>
            {session.state.replace(/_/g, ' ')}
          </Badge>
        </div>
        <div className={styles.chatHeaderRight}>
          <Button
            id="delete-chat-history-btn"
            variant="danger"
            size="sm"
            loading={deleting}
            onClick={() => void clearHistory()}
            title="Delete all messages"
            disabled={loading}
          >
            <Trash2 size={14} /> Delete History
          </Button>
          <button
            id="refresh-chat-btn"
            className={styles.iconBtn}
            onClick={() => void load()}
            title="Refresh"
          >
            <RefreshCw size={14} />
          </button>
          <button
            id="close-chat-btn"
            className={styles.iconBtn}
            onClick={onClose}
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      <div className={styles.chatBody}>
        {deleteError && (
          <p className={styles.chatError}>{deleteError}</p>
        )}
        {loading ? (
          <div className={styles.chatLoading}><Spinner /></div>
        ) : messages.length === 0 ? (
          <p className={styles.chatEmpty}>No messages in this session yet.</p>
        ) : (
          messages.map((msg) => {
            const isAgent = msg.direction === 'outbound';
            return (
              <div
                key={msg.id}
                className={[
                  styles.bubble,
                  isAgent ? styles.bubbleAgent : styles.bubbleClient,
                ].join(' ')}
              >
                <div className={styles.bubbleMeta}>
                  <span className={styles.bubbleSender}>
                    {isAgent ? 'Alysha' : label}
                  </span>
                  <span className={styles.bubbleTime}>{fmt(msg.created_at)}</span>
                </div>
                <p className={styles.bubbleBody}>{msg.body ?? '(media)'}</p>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                 */
/* ------------------------------------------------------------------ */

export default function SessionsPage() {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [agentPaused, setAgentPaused] = useState(false);
  const [selectedSession, setSelectedSession] = useState<ActiveSession | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await sessionsApi.listActive();
      setSessions(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setLoadError(msg);
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useAdminRealtimeRefresh(
    (event: StreamEnvelope) =>
      event.type === 'booking.status_changed'
      || event.type === 'booking.submitted_for_review'
      || event.type === 'session.inbound_message'
      || event.type === 'session.outbound_message'
      || event.type.startsWith('worker.'),
    () => { void load(); },
  );

  const pause = async () => {
    setActionLoading('pause');
    await sessionsApi.pause();
    setAgentPaused(true);
    setActionLoading(null);
  };

  const resume = async () => {
    setActionLoading('resume');
    await sessionsApi.resume();
    setAgentPaused(false);
    setActionLoading(null);
    void load();
  };

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Live Chat</h1>
          <p className={styles.pageSub}>
            All conversation sessions — click a row to view the chat
          </p>
        </div>
        <div className={styles.controls}>
          {agentPaused ? (
            <Button id="resume-btn" variant="primary" size="sm"
              loading={actionLoading === 'resume'} onClick={resume}>
              <Play size={14} /> Resume Agent
            </Button>
          ) : (
            <Button id="pause-btn" variant="danger" size="sm"
              loading={actionLoading === 'pause'} onClick={pause}>
              <Pause size={14} /> Pause Agent
            </Button>
          )}
          <Button id="refresh-sessions-btn" variant="secondary" size="sm" onClick={load}>
            Refresh
          </Button>
        </div>
      </header>

      {agentPaused && (
        <div className={styles.pauseBanner} role="status">
          <Pause size={14} /> Agent is paused — no new messages will be sent until resumed.
        </div>
      )}

      <div className={styles.splitLayout}>
        {/* Sessions table */}
        <div className={[styles.tableCard, selectedSession ? styles.tableCardSplit : ''].join(' ')}>
          {loading ? (
            <div className={styles.loadingRow}><Spinner /></div>
          ) : loadError ? (
            <div className={styles.errorState}>
              <MessageCircle size={32} />
              <p className={styles.errorTitle}>Cannot reach the server</p>
              <p className={styles.errorDetail}>{loadError}</p>
              <button className={styles.retryBtn} onClick={() => void load()}>Retry</button>
            </div>
          ) : sessions.length === 0 ? (
            <EmptyState
              icon={<MessageCircle size={40} />}
              title="No sessions yet"
              description="Sessions will appear here once a client sends a message."
            />
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>State</th>
                  <th>Channel</th>
                  <th>Last Active</th>
                  <th>Active Booking</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr
                    key={s.id}
                    className={[
                      styles.clickableRow,
                      selectedSession?.id === s.id ? styles.selectedRow : '',
                    ].join(' ')}
                    onClick={() => setSelectedSession(s)}
                  >
                    <td className={styles.mono}>
                      {s.client_phone_e164 ?? s.client_id.slice(0, 8) + '…'}
                    </td>
                    <td>
                      <Badge color={SESSION_STATE_COLOR[s.state] ?? 'default'}>
                        {s.state.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td>{s.last_channel ?? '—'}</td>
                    <td className={styles.date}>{fmt(s.last_inbound_at)}</td>
                    <td className={styles.mono}>
                      {s.active_booking_id
                        ? <a href={`/bookings/${s.active_booking_id}`} className={styles.link}
                            onClick={(e) => e.stopPropagation()}>
                            {s.active_booking_id.slice(0, 8)}…
                          </a>
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Chat panel */}
        {selectedSession && (
          <ChatPanel
            session={selectedSession}
            onClose={() => setSelectedSession(null)}
          />
        )}
      </div>
    </div>
  );
}
