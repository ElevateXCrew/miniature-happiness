import { BASE_URL, getAccessToken, tryRefreshSession } from './api';

export interface StreamEnvelope {
  id?: number;
  type: string;
  timestamp?: string;
  payload?: Record<string, unknown>;
}

interface StreamOptions {
  path: string;
  onEvent: (event: StreamEnvelope) => void;
  onOpen?: () => void;
  onError?: (error: unknown) => void;
}

export function openAuthenticatedSseStream(options: StreamOptions): () => void {
  const { path, onEvent, onOpen, onError } = options;

  const controller = new AbortController();
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;
  let lastEventId: number | null = null;

  const parseAndEmit = (block: string): void => {
    const lines = block.split('\n');
    let data = '';
    let eventId: number | null = null;

    for (const line of lines) {
      if (line.startsWith('id:')) {
        const value = line.slice(3).trim();
        if (/^\d+$/.test(value)) {
          eventId = Number(value);
        }
      } else if (line.startsWith('data:')) {
        data += line.slice(5).trim();
      }
    }

    if (!data) return;

    try {
      const parsed = JSON.parse(data) as StreamEnvelope;
      if (eventId !== null) {
        lastEventId = eventId;
        parsed.id = eventId;
      }
      onEvent(parsed);
    } catch (err) {
      onError?.(err);
    }
  };

  const connect = async (): Promise<void> => {
    if (closed) return;

    const token = getAccessToken();
    if (!token) {
      onError?.(new Error('Missing access token for realtime stream'));
      return;
    }

    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${token}`,
    };
    if (lastEventId !== null) {
      headers['Last-Event-ID'] = String(lastEventId);
    }

    try {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'GET',
        headers,
        signal: controller.signal,
        cache: 'no-store',
      });

      if (response.status === 401) {
        const refreshed = await tryRefreshSession();
        if (!refreshed || closed) return;
        reconnectTimer = setTimeout(() => {
          void connect();
        }, 750);
        return;
      }

      if (!response.ok || !response.body) {
        throw new Error(`Realtime stream failed with HTTP ${response.status}`);
      }

      onOpen?.();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (!closed) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        let boundaryIndex = buffer.indexOf('\n\n');
        while (boundaryIndex >= 0) {
          const block = buffer.slice(0, boundaryIndex).trim();
          buffer = buffer.slice(boundaryIndex + 2);
          if (block && !block.startsWith(':')) {
            parseAndEmit(block);
          }
          boundaryIndex = buffer.indexOf('\n\n');
        }
      }

      if (!closed) {
        reconnectTimer = setTimeout(() => {
          void connect();
        }, 1200);
      }
    } catch (err) {
      if (closed || controller.signal.aborted) return;
      onError?.(err);
      reconnectTimer = setTimeout(() => {
        void connect();
      }, 1500);
    }
  };

  void connect();

  return () => {
    closed = true;
    controller.abort();
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };
}
