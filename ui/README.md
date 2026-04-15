# UI — sre-dashboard

Real-time SRE operations dashboard for the ai-runbook-automation system. Built with React 18, TypeScript, TailwindCSS (dark theme), and TanStack Query. All incident state changes arrive over a persistent WebSocket connection — no manual refresh needed.

---

## Tech Stack

| Library | Version | Purpose |
|---------|---------|---------|
| React | 18.3 | UI framework |
| TypeScript | 5.6 | Type safety |
| Vite | 6 | Dev server + build |
| TailwindCSS | 3 | Dark-theme styling |
| TanStack Query | 5 | Server state: queries, mutations, cache |
| React Router | 7 | Client-side routing |
| date-fns | 4 | Date/time formatting |
| clsx | 2 | Conditional classNames |
| Lucide React | 0.468 | Icon set |

---

## Quick Start

```bash
# From the ui/ directory

# Install dependencies (one-time)
npm install

# Start dev server with hot reload
npm run dev
# → http://localhost:3000

# Production build
npm run build   # output → ui/dist/

# Preview production build locally
npm run preview
```

> **Backend must be running.** The dev server proxies `/api/*` and `/ws` to `http://localhost:8000`. Start it with `docker compose up -d` from the project root.

---

## Dev Server Proxy

`vite.config.ts` configures two proxy rules so you never deal with CORS in development:

| Browser request | Forwarded to |
|-----------------|-------------|
| `GET /api/incidents` | `GET http://localhost:8000/incidents` |
| `POST /api/alerts/webhook` | `POST http://localhost:8000/alerts/webhook` |
| `ws://localhost:3000/ws` | `ws://localhost:8000/ws` |

The `/api` prefix is stripped before forwarding — the backend never sees it.

---

## Environment Variables

Create `ui/.env.local` to override defaults (this file is gitignored):

```env
# Required when API_KEY is set on the backend
VITE_API_KEY=your-secret-key

# Override WebSocket host (default: window.location.host)
VITE_WS_HOST=localhost:8000
```

> In production (Docker), these are injected at build time via `docker build --build-arg`.

---

## Pages

### `/` — Dashboard

The main live view. Three panels on a two-column layout.

**Incident Feed (left)**
- Lists all incidents ordered by most recent
- Each row: alert name, color-coded status badge, service label, duration, start time
- Updates in real-time via WebSocket without reloading
- Click any row to navigate to `/incidents/:id`

**Alert Simulator (right, top)**
- Dropdown with 15 built-in alert scenarios
- "Fire Alert" sends a POST to `/api/simulate` and shows the returned incident ID
- Scenarios span four categories: restart (memory/service), scale (traffic/CPU), escalate (dependencies), investigate (disk/network)

**Service Health (right, bottom)**
- Polls `GET /api/health` every 30 seconds
- Shows reachability for LLM backend, Prometheus, and Redis
- Green dot = healthy · red dot = unreachable

---

### `/incidents/:id` — Incident Detail

Full incident deep-dive. All sections are rendered in collapsible cards.

| Section | Content |
|---------|---------|
| Header | Alert name, status badge, incident ID, start/resolved time, duration |
| Approval Banner | Amber bar when agent is paused — Approve / Reject buttons |
| Alert Labels | All Prometheus labels from the original alert |
| Analysis | Agent's plain-text summary + identified root cause |
| Actions Timeline | Numbered list of every tool call with inputs, outputs, and result codes |
| Recommendations | Agent's follow-up suggestions |
| Reasoning Transcript | Full LLM conversation as chat bubbles |
| Post-Incident Review | Structured PIR after resolution (severity, timeline, action items) |

**Approval flow**

When the agent hits a destructive action needing approval:

1. A pulsing amber bar appears at the **top of every page** (the `ApprovalNotificationBar`) with a direct link to the incident
2. On the incident detail page, an `ApprovalBanner` shows the pending action name with Approve and Reject buttons
3. **Approve** → `POST /api/incidents/{id}/approve` — agent resumes and executes
4. **Reject** → `POST /api/incidents/{id}/reject` — agent skips and continues reasoning

---

### `/runbooks` — Runbook Browser

Lists all loaded YAML runbooks. Each `RunbookCard` shows:
- Name (monospace), severity badge, team badge
- Description and trigger alert names (amber badges)
- Numbered action steps
- Escalation threshold

**Inline YAML editor**

1. Click **Edit YAML ›** on any card — lazy-fetches raw YAML from `GET /api/runbooks/{name}/yaml`
2. Edit in the resizable textarea (monospace font)
3. **Save** → `PUT /api/runbooks/{name}` — server validates before writing to disk
4. Changes take effect for the next incident — no service restart needed
5. **Cancel** discards changes

---

### `/stats` — MTTR / SLO Dashboard

| Element | Description |
|---------|-------------|
| Total tile | All incidents processed |
| Auto-Resolved % tile | Incidents resolved without escalation |
| MTTR tile | Mean time to resolve (formatted as s / m / h) |
| Escalated tile | Escalated + failed counts |
| Outcome breakdown bar | Proportional split: Resolved · Escalated · Failed · Processing |
| Top alert types | Horizontal bar chart of the 5 most frequent alert names |

---

## Project Structure

```
ui/src/
├── pages/
│   ├── DashboardPage.tsx       — / (incident feed + simulator + health)
│   ├── IncidentDetailPage.tsx  — /incidents/:id
│   ├── RunbooksPage.tsx        — /runbooks
│   └── StatsPage.tsx           — /stats
│
├── components/
│   ├── incidents/
│   │   ├── IncidentFeed.tsx        — real-time incident list
│   │   ├── IncidentRow.tsx         — single row with status badge + duration
│   │   ├── StatusBadge.tsx         — color-coded status pill
│   │   ├── SeverityBadge.tsx       — P1–P4 severity pill
│   │   ├── ActionsTimeline.tsx     — numbered agent tool call log
│   │   ├── ApprovalBanner.tsx      — per-incident Approve / Reject UI
│   │   ├── ReasoningTranscript.tsx — LLM conversation renderer
│   │   └── PirPanel.tsx            — Post-Incident Review sections
│   ├── simulator/
│   │   └── AlertSimulator.tsx      — scenario dropdown + fire button
│   ├── health/
│   │   └── HealthPanel.tsx         — service reachability dots
│   ├── runbooks/
│   │   ├── RunbookCard.tsx         — runbook card + inline YAML editor
│   │   └── NewRunbookModal.tsx     — create runbook form
│   ├── stats/
│   │   └── MttrDashboard.tsx       — KPI tiles + breakdown bar + top alerts
│   ├── transcript/
│   │   ├── MessageBubble.tsx       — chat bubble (user / assistant / system roles)
│   │   └── ToolCallBlock.tsx       — collapsible tool call + result
│   ├── layout/
│   │   ├── Sidebar.tsx                 — nav links: Dashboard | Runbooks | MTTR/SLO
│   │   ├── TopBar.tsx                  — page title + WS indicator + mode toggle
│   │   ├── ApprovalNotificationBar.tsx — global amber bar when any incident awaits approval
│   │   └── LiveIndicator.tsx           — pulsing green dot when WebSocket is connected
│   └── ui/
│       ├── Badge.tsx       — generic pill badge (variant prop)
│       ├── Button.tsx      — primary / danger / success / ghost variants
│       ├── Card.tsx        — dark card container with optional title + footer
│       ├── EmptyState.tsx  — centered icon + message for empty lists
│       └── Spinner.tsx     — loading spinner
│
├── hooks/
│   ├── useWebSocket.ts         — singleton WS subscription
│   ├── useIncidents.ts         — incident list query + WS invalidation
│   ├── useIncident.ts          — single incident query + WS invalidation
│   ├── useFireAlert.ts         — POST /simulate mutation
│   ├── useAgentMode.ts         — GET + POST agent mode
│   ├── useApproveIncident.ts   — POST /incidents/{id}/approve
│   ├── useRejectIncident.ts    — POST /incidents/{id}/reject
│   ├── useRunbooks.ts          — GET /runbooks list
│   ├── useRunbookYaml.ts       — lazy GET /runbooks/{name}/yaml
│   ├── useUpdateRunbook.ts     — PUT /runbooks/{name}
│   ├── useHealth.ts            — GET /health (30s interval)
│   └── useStats.ts             — GET /stats (30s interval)
│
└── lib/
    ├── api.ts          — typed fetch wrapper with auth headers
    ├── format.ts       — formatDuration, formatTimestamp
    └── queryClient.ts  — TanStack Query client config
```

---

## Custom Hooks Reference

### `useWebSocket`

Module-level singleton. Call `subscribe(handler)` to receive all incoming WebSocket messages. Returns an unsubscribe function to clean up.

```ts
import { subscribe } from "@/hooks/useWebSocket";

useEffect(() => {
  const unsub = subscribe((data) => {
    console.log(data); // parsed JSON from /ws
  });
  return unsub;
}, []);
```

Reconnects automatically with exponential backoff (1 s → 2 s → 4 s … capped at 30 s). Closes gracefully when all subscribers unsubscribe.

---

### `useIncidents`

```ts
const { data, isLoading, error } = useIncidents();
// data: IncidentSummary[]
```

Fetches `GET /api/incidents`. Subscribes to the WebSocket and calls `queryClient.invalidateQueries(["incidents"])` when any incident state change arrives.

---

### `useIncident(id: string)`

```ts
const { data, isLoading } = useIncident(incidentId);
// data: Incident (full detail with transcript + PIR)
```

Fetches `GET /api/incidents/{id}`. Subscribes to WebSocket and re-fetches when a matching `incident_id` message arrives.

---

### `useFireAlert`

```ts
const { mutate, isPending } = useFireAlert();
mutate(alertPayload); // AlertmanagerWebhook shape
```

Sends `POST /api/simulate`. On success, invalidates the incidents list.

---

### `useAgentMode`

```ts
const { data } = useAgentMode();           // { mode: "AUTO" | "MANUAL" | "DRY_RUN" }
const { mutate } = useAgentMode().setMode;
mutate({ mode: "MANUAL" });
```

`GET /api/agent/mode` for reads, `POST /api/agent/mode` for writes.

---

### `useApproveIncident` / `useRejectIncident`

```ts
const { mutate: approve } = useApproveIncident();
approve({ incidentId, action, operator, reason });

const { mutate: reject } = useRejectIncident();
reject({ incidentId, action, reason });
```

Both post to `/api/incidents/{id}/approve` or `/reject` and invalidate the incident query on success.

---

### `useRunbooks`

```ts
const { data } = useRunbooks();
// data: Runbook[]
```

Fetches `GET /api/runbooks`.

---

### `useRunbookYaml(name: string, enabled: boolean)`

```ts
const { data: yaml } = useRunbookYaml(name, isEditorOpen);
```

Lazy query — only fetches when `enabled` is `true` (editor opens). Fetches `GET /api/runbooks/{name}/yaml`.

---

### `useUpdateRunbook`

```ts
const { mutate: save, isPending } = useUpdateRunbook();
save({ name, yaml });
```

Sends `PUT /api/runbooks/{name}` with the raw YAML string. Invalidates `["runbooks"]` on success.

---

### `useHealth`

```ts
const { data } = useHealth();
// data: HealthResponse { status, claude_api, prometheus, redis, ... }
```

Polls `GET /api/health` every 30 seconds via `refetchInterval`.

---

### `useStats`

```ts
const { data } = useStats();
// data: { total, resolved, escalated, failed, resolution_rate, avg_resolution_seconds, top_alert_types }
```

Polls `GET /api/stats` every 30 seconds.

---

## API Client (`lib/api.ts`)

Thin typed wrapper around `fetch`. All requests go to `/api/*` (proxied to the backend in dev, routed to the real host in production).

```ts
import { api } from "@/lib/api";

// GET
const incidents = await api.get<IncidentSummary[]>("/incidents");

// POST with body
const result = await api.post<WebhookResponse>("/simulate", payload);

// PUT with body
await api.put(`/runbooks/${name}`, { yaml });
```

Automatically injects the `X-API-Key` header when `VITE_API_KEY` is set. Throws an `Error` with the HTTP status + body on non-2xx responses.

---

## State Management

The dashboard uses **TanStack Query v5** for all server state. There is no global client-side state store (no Redux, no Zustand).

### Cache invalidation via WebSocket

`useIncidents` and `useIncident` both subscribe to the WebSocket. When a message arrives:

1. The hook checks if `data.incident_id` matches the query key
2. Calls `queryClient.invalidateQueries(...)` — TanStack Query refetches in the background
3. The UI updates atomically once the new data arrives

This means the 30-second polling interval is a fallback only. In practice, updates appear within milliseconds of the worker publishing to Redis.

### Optimistic updates

Approve and reject mutations update the incident status to `PROCESSING` immediately (optimistic) before the API call completes, so the approval banner disappears instantly on click.

---

## UI Primitives (`components/ui/`)

Generic building blocks used throughout the dashboard.

### `Badge`

```tsx
<Badge variant="success">RESOLVED</Badge>
<Badge variant="warning">PENDING_APPROVAL</Badge>
<Badge variant="danger">FAILED</Badge>
<Badge variant="info">PROCESSING</Badge>
<Badge variant="default">PENDING</Badge>
```

### `Button`

```tsx
<Button variant="primary" onClick={...}>Approve</Button>
<Button variant="danger" onClick={...}>Reject</Button>
<Button variant="ghost" size="sm" onClick={...}>Cancel</Button>
<Button loading={isPending}>Save</Button>
```

### `Card`

```tsx
<Card title="Alert Labels">
  {/* content */}
</Card>
```

### `EmptyState`

```tsx
<EmptyState icon={AlertCircle} message="No incidents yet" />
```

### `Spinner`

```tsx
<Spinner size="sm" />
<Spinner size="md" />
```

---

## WebSocket Connection

The app maintains one WebSocket connection shared across all components via the module-level singleton in `hooks/useWebSocket.ts`.

- **URL:** `ws://{host}/ws` (or `wss://` over HTTPS)
- **Auth:** `?api_key=<value>` query parameter when `VITE_API_KEY` is set
- **Reconnect:** exponential backoff, 1 s → 2 s → 4 s … max 30 s
- **Indicator:** `LiveIndicator` in the `TopBar` shows a pulsing green dot when connected

The connection closes cleanly when the page unloads (all subscribers removed).

---

## Production Build

```bash
# Build optimised static assets
npm run build
# Output: ui/dist/

# The Docker image builds this automatically
docker build -t sre-dashboard ./ui
```

The `ui/Dockerfile` is a two-stage build:
1. **Build stage** — Node 20 Alpine, `npm ci && npm run build`
2. **Serve stage** — nginx Alpine, serves `dist/` on port 80

The nginx config proxies `/api` and `/ws` to the API service hostname — set via the `API_HOST` build arg.

---

## Adding a New Page

1. Create `ui/src/pages/MyPage.tsx`
2. Add a route in `ui/src/main.tsx` (or the router config file):

   ```tsx
   <Route path="/my-page" element={<MyPage />} />
   ```

3. Add a nav link in `components/layout/Sidebar.tsx`
4. Create any needed hooks in `ui/src/hooks/`
5. Use existing `Card`, `Badge`, `Button` primitives from `components/ui/`

### Conventions

- **One query per hook.** Don't put multiple `useQuery` calls in a single hook file.
- **Invalidate on mutation.** Always call `queryClient.invalidateQueries` in `onSuccess`.
- **Tailwind only.** No inline styles, no CSS modules.
- **No `any`.** Type all API responses with the shared types from `ui/src/types/`.
