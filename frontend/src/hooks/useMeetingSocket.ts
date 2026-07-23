import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { TOKEN_STORAGE_KEY } from "@/api/client";

const RECONNECT_DELAY_MS = 3000;

/** Mirrors client.ts's baseURL derivation (VITE_API_URL, falling back to the Vite dev proxy) but as a ws://.../wss://... URL instead of http(s). */
function resolveSocketUrl(token: string): string {
  const apiUrl = import.meta.env.VITE_API_URL as string | undefined;

  if (apiUrl) {
    const wsBase = apiUrl.replace(/^http/, "ws").replace(/\/$/, "");
    return `${wsBase}/ws?token=${encodeURIComponent(token)}`;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws?token=${encodeURIComponent(token)}`;
}

/**
 * Opens a single WebSocket connection for the lifetime of an
 * authenticated session (mounted once in AppLayout) and invalidates
 * the relevant React Query caches on any meeting_* event pushed by
 * the backend (see connection_manager.broadcast_to_user_sync in
 * MeetingService) - the same cache-invalidation mechanism the
 * Analytics page's manual refresh button already uses, just
 * triggered by the server instead of a click. Auto-reconnects with a
 * fixed delay on an unexpected close; never reconnects after logout
 * (isAuthenticated goes false, which unmounts the effect's socket).
 */
export function useMeetingSocket(isAuthenticated: boolean) {
  const queryClient = useQueryClient();

  React.useEffect(() => {
    if (!isAuthenticated) return;

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      const token = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (!token) return;

      socket = new WebSocket(resolveSocketUrl(token));

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (typeof data?.type === "string" && data.type.startsWith("meeting_")) {
            queryClient.invalidateQueries({ queryKey: ["meetings"] });
            queryClient.invalidateQueries({ queryKey: ["analytics"] });
            queryClient.invalidateQueries({ queryKey: ["kpis"] });
          }
        } catch {
          // Non-JSON or unrecognized payload - ignore rather than throw,
          // this connection is a cache-invalidation hint, not a data source.
        }
      };

      socket.onclose = () => {
        if (!stopped) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [isAuthenticated, queryClient]);
}
