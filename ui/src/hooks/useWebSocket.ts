/**
 * Shared WebSocket connection for real-time incident updates.
 *
 * Connects once per app session (singleton via module-level state) and lets
 * callers register message handlers. Auto-reconnects with exponential backoff
 * on unexpected closes.
 */

type MessageHandler = (data: unknown) => void;

const handlers = new Set<MessageHandler>();
let socket: WebSocket | null = null;
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
let backoffMs = 1_000;

function getWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // In dev, Vite proxies /ws → ws://localhost:8000/ws (ws: true in vite.config.ts).
  // In production, VITE_WS_HOST can override (e.g. "api.example.com").
  const host = import.meta.env.VITE_WS_HOST ?? window.location.host;
  return `${proto}//${host}/ws`;
}

function connect(): void {
  if (socket && socket.readyState <= WebSocket.OPEN) return;

  const url = getWsUrl();
  socket = new WebSocket(url);

  socket.onopen = () => {
    backoffMs = 1_000; // reset backoff on successful connect
  };

  socket.onmessage = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data as string);
      handlers.forEach((h) => h(data));
    } catch {
      // ignore unparseable frames
    }
  };

  socket.onclose = (event) => {
    if (event.wasClean) return; // intentional close — don't reconnect
    scheduleReconnect();
  };

  socket.onerror = () => {
    socket?.close();
  };
}

function scheduleReconnect(): void {
  if (reconnectTimeout) return;
  reconnectTimeout = setTimeout(() => {
    reconnectTimeout = null;
    backoffMs = Math.min(backoffMs * 2, 30_000);
    connect();
  }, backoffMs);
}

/** Subscribe to incoming WebSocket messages. Returns an unsubscribe function. */
export function subscribe(handler: MessageHandler): () => void {
  handlers.add(handler);
  connect(); // ensure connection is live
  return () => {
    handlers.delete(handler);
    // If nobody is listening, close gracefully.
    if (handlers.size === 0) {
      socket?.close(1000, "no subscribers");
      socket = null;
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }
    }
  };
}
