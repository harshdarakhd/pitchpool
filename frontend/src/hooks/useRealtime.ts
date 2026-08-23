import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

const PING_INTERVAL_MS = 30_000;
const MAX_BACKOFF_MS = 30_000;

export function useRealtime() {
  const qc = useQueryClient();

  useEffect(() => {
    let socket: WebSocket | null = null;
    let pingTimer: number | undefined;
    let retryTimer: number | undefined;
    let attempts = 0;
    // Set during cleanup so a socket we closed ourselves never reconnects.
    let disposed = false;

    const connect = () => {
      if (disposed) return;

      // The browser includes the secure same-origin access cookie during the
      // WebSocket handshake. Keeping JWTs out of query strings avoids leaking
      // them through proxy and server logs.
      const ws = new WebSocket(WS_URL);
      socket = ws;

      ws.onopen = () => {
        attempts = 0;
        pingTimer = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (
            data.type === 'pool_updated' ||
            data.type === 'match_settled' ||
            data.type === 'match_locked'
          ) {
            qc.invalidateQueries({ queryKey: ['matches'] });
            if (data.match_id) qc.invalidateQueries({ queryKey: ['match', data.match_id] });
          }
          if (data.type === 'leaderboard_updated') {
            qc.invalidateQueries({ queryKey: ['leaderboard'] });
          }
        } catch {
          /* ping/pong */
        }
      };

      ws.onerror = () => ws.close();

      ws.onclose = () => {
        window.clearInterval(pingTimer);
        if (disposed) return;
        // Reconnect the socket only. Reloading the page here would throw away
        // whatever the user was looking at, and loops forever if /ws is down.
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempts);
        attempts += 1;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      window.clearInterval(pingTimer);
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [qc]);
}
