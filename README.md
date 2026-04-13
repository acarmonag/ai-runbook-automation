# AI Runbook Automation

An LLM-powered autonomous SRE agent that monitors alerts from Prometheus/Alertmanager, reasons about root causes, selects and executes runbook actions, and reports back with what it did and why.

**This is NOT a chatbot.** It is an autonomous remediation agent with a human-approval gate for destructive actions. The LLM (Ollama or Claude) is used purely as a reasoning engine inside a tool-use loop.

---

## Architecture

```
Prometheus Alert
      │
      ▼
Alertmanager ──────────► POST /alerts/webhook
                                │
                         ┌──────▼──────────────┐
                         │  Alert Correlation  │ ← groups same (service+alertname)
                         │  Engine (Redis)     │   within 5-min window → 1 incident
                         └──────┬──────────────┘
                                │
                         ┌──────▼──────┐
                         │  ARQ Queue  │ (Redis — durable, retried on crash)
                         └──────┬──────┘
                                │
                    ┌───────────▼────────────┐
                    │    agent-worker        │ (separate Docker service)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │       SRE Agent        │
                    │  OBSERVE → REASON      │
                    │  → ACT → VERIFY        │
                    │  → REPORT              │
                    └───────────┬────────────┘
                                │
              ┌─────────────────▼────────────────────┐
              │           LLM Backend                │
              │                                      │
              │  Ollama (default, free, local)       │
              │    qwen3:14b @ host.docker.internal  │
              │                                      │
              │  Claude (Anthropic API)              │
              │    claude-sonnet-4-6 (tool_use)      │
              │                                      │
              │  Tools:                              │
              │   • get_metrics(query)               │
              │   • get_recent_logs(service, lines)  │
              │   • get_service_status(service)      │
              │   • scale_service(service, replicas) │
              │   • restart_service(service)         │
              │   • run_diagnostic(check)            │
              │   • escalate(reason, severity)       │
              └──────────────┬───────────────────────┘
                             │
              ┌──────────────▼──────────────────────┐
              │         Approval Gate               │
              │  AUTO:    destructive → human input │
              │  DRY_RUN: log only, never execute   │
              │  MANUAL:  always prompt human       │
              └──────────────┬──────────────────────┘
                             │
         ┌───────────────────┼──────────────────────┐
         ▼                   ▼                      ▼
  Prometheus           Docker Actions         Escalation
  (PromQL)             (restart/scale)        (Slack / PagerDuty)
                                                     │
                    ┌────────▼──────────┐            │
                    │ PostgreSQL        │            │
                    │  • incidents      │◄───────────┘
                    │  • PIR reports    │
                    │  • transcripts    │
                    └────────┬──────────┘
                             │
              ┌──────────────▼────────────────────┐
              │  WebSocket push → React Dashboard │
              │  (worker → Redis pub/sub → API)   │
              └───────────────────────────────────┘
```

---

## LLM Backends

The agent supports two interchangeable LLM backends. Switch between them with the `LLM_BACKEND` environment variable. All business logic — approval gates, runbooks, state machine, actions — is backend-agnostic.

### Ollama (default — free, local, no API key)

Ollama runs models on your own machine. The default model is **qwen3:14b**, which has strong reasoning and tool-use capabilities suitable for SRE tasks.

**1. Install Ollama**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

**2. Pull the model**

```bash
ollama pull qwen3:14b
```

> This downloads ~9 GB. You can substitute a smaller model (e.g. `qwen3:8b`, `llama3.1:8b`) by setting `OLLAMA_MODEL`.

**3. Start Ollama** (macOS: it starts automatically as a background service after install)

```bash
ollama serve   # if not already running
```

**4. Configure `.env`**

```env
LLM_BACKEND=ollama
OLLAMA_URL=http://host.docker.internal:11434   # reaches your host from inside Docker
OLLAMA_MODEL=qwen3:14b
```

> `host.docker.internal` is Docker Desktop's magic hostname that resolves to your Mac/Windows host. On Linux, use your host's IP instead (e.g. `172.17.0.1`).

**Supported models** (any model with tool-use / function-calling support):

| Model | Size | Notes |
|-------|------|-------|
| `qwen3:14b` | ~9 GB | **Default.** Best reasoning + tool use. |
| `qwen3:8b` | ~5 GB | Faster, slightly less accurate. |
| `llama3.1:8b` | ~5 GB | Good alternative if Qwen is unavailable. |
| `mistral-nemo` | ~7 GB | Strong instruction following. |

Pull any model with `ollama pull <model-name>` and set `OLLAMA_MODEL=<model-name>`.

---

### Claude (Anthropic API)

Uses the Claude API — requires an Anthropic API key. Offers the strongest reasoning quality and is recommended for production use.

**Configure `.env`**

```env
LLM_BACKEND=claude
ANTHROPIC_API_KEY=sk-ant-...
```

The agent uses `claude-sonnet-4-6` by default (configurable in `agent/llm/claude_backend.py`).

---

## Quickstart

```bash
# 1. Clone the repo
git clone <repo-url> && cd ai-runbook-automation

# 2. Pull the Ollama model (one-time, ~9 GB)
ollama pull qwen3:14b

# 3. Copy and configure environment
cp .env.example .env
# For Ollama (default): no changes needed
# For Claude: set LLM_BACKEND=claude and ANTHROPIC_API_KEY=sk-ant-...

# 4. Start all services
docker compose up -d

# 5. Verify everything is healthy
curl http://localhost:8000/health

# 6. Fire a test alert
curl -X POST http://localhost:8000/alerts/webhook \
  -H "Content-Type: application/json" \
  -d @tests/payload.json

# 7. Watch the agent work
docker compose logs -f agent-worker

# 8. Open the dashboard
# http://localhost:3000 (after running the UI dev server — see below)
```

---

## React Dashboard

A real-time SRE dashboard built with **React 18**, **TypeScript**, **TailwindCSS** (dark theme), and **TanStack Query**. All incident updates arrive over a WebSocket — no manual refresh needed.

### Starting the UI

```bash
# One-time setup
cd ui && npm install

# Development server with hot reload
npm run dev
# → http://localhost:3000

# Production build
npm run build   # output → ui/dist/
```

The dev server proxies `/api/*` and `/ws` to `http://localhost:8000` automatically — no CORS config needed in development.

> **Optional env vars** (create `ui/.env.local`):
> ```env
> VITE_API_KEY=your-key-here      # if API_KEY is set on the backend
> VITE_WS_HOST=localhost:8000     # defaults to window.location.host
> ```

---

### Pages

#### `/` — Dashboard

The main live view. Two-column layout:

**Left — Incident Feed**
- Lists all incidents ordered by most recent, updated in real-time via WebSocket
- Each row: alert name, color-coded status badge, service label, duration, start time
- Click any row to open the full incident detail
- Status colors: `PENDING` → zinc · `PROCESSING` → blue · `RESOLVED` → green · `ESCALATED` → amber · `FAILED` → red

**Right — Alert Simulator**
- Dropdown with 5 built-in scenarios; "Fire Alert" sends the alert to the API and shows the returned incident ID
- Use this to trigger the full agent pipeline without Alertmanager
- Scenarios: High Error Rate (critical), High Latency (warning), Memory Leak (warning), Service Down (critical), CPU Spike (warning)

**Right — Service Health**
- Polls `/health` every 30 seconds
- Shows reachability for: LLM backend (Ollama or Claude), Prometheus, Redis
- Green dot = healthy · red dot = unreachable

---

#### `/incidents/:id` — Incident Detail

Full deep-dive for a single incident. Sections (each in its own card):

| Section | Content |
|---------|---------|
| **Header** | Alert name, status badge, incident ID, start time, resolved time, total duration |
| **Approval Banner** | Amber bar when agent is paused waiting for human approval — Approve / Reject buttons |
| **Alert Labels** | All Prometheus labels from the original alert (e.g. `service=checkout`, `severity=critical`) |
| **Analysis** | Agent's summary paragraph + identified root cause |
| **Actions** | Numbered timeline of every tool call — action name, input parameters, output/result |
| **Recommendations** | Bulleted follow-up suggestions from the agent |
| **Reasoning Transcript** | Full LLM conversation as chat bubbles: system prompt, user turns, assistant reasoning, tool call/result blocks |
| **Post-Incident Review** | Auto-generated structured PIR after resolution |

**Approval flow**

When the agent needs to run a destructive action (e.g. `restart_service`), it pauses and the amber banner appears:

- **Approve** → `POST /incidents/{id}/approve` — agent resumes and executes the action
- **Reject** → `POST /incidents/{id}/reject` — agent skips the action and continues reasoning

**Post-Incident Review (PIR)**

Auto-generated by the LLM after every RESOLVED incident:

- Severity (P1–P4) with color coding (P1=red, P2=orange, P3=yellow, P4=zinc)
- Root cause, impact, and resolution narrative
- Contributing factors list
- Event timeline with timestamps
- Action items with priority badges and owner tags
- Prevention checklist

If the PIR is still generating, a placeholder is shown — refresh in a moment.

---

#### `/runbooks` — Runbook Browser

Lists all loaded YAML runbooks. Each card shows:

- Name (monospace) + severity and team metadata badges
- Description — when the runbook applies
- **Triggers** — alert names that activate this runbook (amber badges)
- **Actions** — numbered investigation/remediation steps
- **Escalation threshold** — condition under which the agent escalates to humans

**Inline YAML editor**

1. Click **Edit YAML ›** — fetches the raw YAML and opens a resizable textarea
2. Edit directly in the browser (monospace font)
3. Click **Save** → `PUT /runbooks/{name}` — YAML is validated on the server before writing
4. On success the editor closes; changes take effect on the next agent run — no restart needed
5. Click **Cancel** to discard changes

---

#### `/stats` — MTTR / SLO Dashboard

| Element | Description |
|---------|-------------|
| **Total** tile | All incidents ever processed |
| **Auto-Resolved %** tile | Incidents resolved by the agent without escalation (green) |
| **MTTR** tile | Mean time to resolve, formatted as s / m / h (blue) |
| **Escalated** tile | Escalated count with failed count subtitle (amber if > 0) |
| **Outcome breakdown bar** | Proportional split: Resolved (green) · Escalated (amber) · Failed (red) · Processing (gray) |
| **Top alert types chart** | Horizontal bars for the 5 most frequent alert names |

---

### WebSocket Real-Time Updates

The dashboard keeps a single persistent WebSocket connection to `/ws`. All state changes (PENDING → PROCESSING → RESOLVED / ESCALATED / FAILED) are pushed instantly from the worker to the UI.

- A **pulsing green dot** in the top bar indicates an active connection
- On disconnect, the client reconnects automatically with exponential backoff (1s → 2s → 4s … up to 30s)
- Queries also refresh every 30 seconds as a fallback

---

### UI Component Map

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
│   │   ├── IncidentRow.tsx         — single row: status badge + duration
│   │   ├── StatusBadge.tsx         — color-coded status pill
│   │   ├── SeverityBadge.tsx       — P1–P4 severity pill
│   │   ├── ActionsTimeline.tsx     — numbered list of agent tool calls + outputs
│   │   ├── ApprovalBanner.tsx      — amber bar with Approve/Reject buttons
│   │   ├── ReasoningTranscript.tsx — LLM chat bubble renderer
│   │   └── PirPanel.tsx            — Post-Incident Review sections
│   ├── simulator/
│   │   └── AlertSimulator.tsx      — scenario dropdown + Fire Alert button
│   ├── health/
│   │   └── HealthPanel.tsx         — service reachability status dots
│   ├── runbooks/
│   │   └── RunbookCard.tsx         — runbook card + inline YAML editor
│   ├── stats/
│   │   └── MttrDashboard.tsx       — KPI tiles + breakdown bar + top alerts chart
│   ├── transcript/
│   │   ├── MessageBubble.tsx       — chat bubble (user / assistant / system)
│   │   └── ToolCallBlock.tsx       — collapsible tool call + result block
│   ├── layout/
│   │   ├── Sidebar.tsx             — nav: Dashboard | Runbooks | MTTR/SLO
│   │   ├── TopBar.tsx              — page title + live WS indicator
│   │   └── LiveIndicator.tsx       — pulsing green dot when WS connected
│   └── ui/
│       ├── Badge.tsx               — generic pill badge
│       ├── Button.tsx              — primary / danger / success variants
│       ├── Card.tsx                — dark card container with optional title
│       ├── EmptyState.tsx          — centered empty message
│       └── Spinner.tsx             — loading spinner
│
├── hooks/
│   ├── useWebSocket.ts         — singleton WS with exponential reconnect
│   ├── useIncidents.ts         — list query + WS-driven cache invalidation
│   ├── useIncident.ts          — single incident + WS-driven invalidation
│   ├── useFireAlert.ts         — POST /simulate mutation
│   ├── useApproveIncident.ts   — POST /incidents/{id}/approve mutation
│   ├── useRejectIncident.ts    — POST /incidents/{id}/reject mutation
│   ├── useRunbooks.ts          — GET /runbooks query
│   ├── useRunbookYaml.ts       — lazy GET /runbooks/{name}/yaml (on editor open)
│   ├── useUpdateRunbook.ts     — PUT /runbooks/{name} mutation
│   ├── useHealth.ts            — GET /health (30s interval)
│   └── useStats.ts             — GET /stats (30s interval)
│
└── lib/
    ├── api.ts          — typed fetch wrapper with auth headers
    ├── format.ts       — formatDuration, formatTimestamp helpers
    └── queryClient.ts  — TanStack Query client configuration
```

### UI Tech Stack

| Library | Purpose |
|---------|---------|
| React 18 | UI framework |
| TypeScript 5 | Type safety |
| TailwindCSS 3 | Dark-theme styling |
| TanStack Query v5 | Server state: fetching, caching, mutations |
| React Router v6 | Client-side routing |
| Vite 5 | Dev server + build tool |
| Lucide React | Icons |

---

## Running Test Scenarios

Fire alerts against the stack using the included test payload or the Alert Simulator in the UI.

```bash
# Single alert via curl (from project root)
curl -X POST http://localhost:8000/alerts/webhook \
  -H "Content-Type: application/json" \
  -d @tests/payload.json

# Watch the worker process it
docker compose logs -f agent-worker

# Check the result
curl http://localhost:8000/incidents | python3 -m json.tool
```

Available alert scenarios (edit `tests/payload.json` or use the UI simulator):

| `alertname` | Runbook triggered | What the agent does |
|-------------|-------------------|---------------------|
| `HighErrorRate` | high_error_rate | Queries error rate → checks logs → restarts if needed |
| `HighLatency` | high_latency | Checks p99 latency → CPU usage → scales if needed |
| `MemoryLeakDetected` | memory_leak | Checks memory growth → OOM logs → restarts |
| `ServiceDown` | service_down | Checks container status → restarts → escalates if fails |
| `HighCPU` | cpu_spike | CPU metrics → run_diagnostic → scale up |

---

## Runbooks

Each runbook is a YAML file in `runbooks/` mapping alert names to investigation and remediation sequences.

### Adding a New Runbook

Create `runbooks/my_runbook.yml`:

```yaml
name: my_runbook
description: |
  Handles MySpecificAlert — what this runbook does and when to use it.

triggers:
  - MySpecificAlert
  - RelatedAlert

actions:
  - "get_metrics: Query the relevant metric — rate(my_metric[5m])"
  - "get_recent_logs: Check service logs for error patterns"
  - "run_diagnostic: Run memory_pressure or disk_usage check"
  - "scale_service: Scale up if resource constrained"
  - "restart_service: Restart if logs show known crash pattern (requires approval)"
  - "get_metrics: Re-query metric to verify resolution"

escalation_threshold: |
  Escalate if metric remains above threshold after remediation.
  Also escalate if root cause is unknown.

metadata:
  severity: P2
  team: platform
  runbook_version: "1.0"
```

No code changes needed — the registry picks up new YAML files on restart. You can also edit existing runbooks from the browser via the **Runbook Browser → Edit YAML** button.

---

## Approval Modes

Set via `APPROVAL_MODE` environment variable:

| Mode | Behavior |
|------|----------|
| `AUTO` | Auto-approves safe actions (metrics, logs, diagnostics). Prompts for destructive actions. **Default.** |
| `DRY_RUN` | Logs all actions but never executes any. Safe for testing. |
| `MANUAL` | Prompts for human approval on every single action. |

Destructive actions (require approval in AUTO/MANUAL):
- `restart_service` — always destructive
- `scale_service` — only when scaling **down** (replicas < current)

Approvals can be granted via the dashboard banner or the API:

```bash
curl -X POST http://localhost:8000/incidents/<id>/approve \
  -H "Content-Type: application/json" \
  -d '{"action": "restart_service", "operator": "oncall-engineer"}'
```

---

## Alert Correlation

The correlation engine prevents alert storms from spawning redundant agent runs. Two alerts are considered correlated if they share the same `(service, alertname)` pair and arrive within the configured window (default: 5 minutes).

```bash
# Check active correlation groups
curl http://localhost:8000/correlations

# Tune the window
CORRELATION_WINDOW_SECONDS=600  # 10 minutes
```

---

## Escalation (Slack + PagerDuty)

When the agent calls `escalate`, it notifies your on-call channels:

```env
# Slack — incoming webhook URL
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...

# PagerDuty — Events API v2 routing key
PAGERDUTY_ROUTING_KEY=abc123...
```

If neither is set, escalations are logged locally to `/tmp/escalations.jsonl` inside the worker container.

---

## API Reference

### Alerts

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/alerts/webhook` | Receive Alertmanager webhook payload |
| `POST` | `/simulate` | Same as webhook but forces DRY_RUN mode |

### Incidents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/incidents` | List all incidents |
| `GET` | `/incidents/{id}` | Full incident detail + transcript |
| `GET` | `/incidents/{id}/pir` | Auto-generated Post-Incident Review |
| `POST` | `/incidents/{id}/approve` | Approve a pending destructive action |
| `POST` | `/incidents/{id}/reject` | Reject a pending action |

### Runbooks

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/runbooks` | List all loaded runbooks |
| `GET` | `/runbooks/{name}` | Single runbook detail |
| `GET` | `/runbooks/{name}/yaml` | Raw YAML (for the editor) |
| `PUT` | `/runbooks/{name}` | Save updated YAML (validated before write) |

### Observability

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | LLM backend + Prometheus + Redis reachability |
| `GET` | `/stats` | MTTR, resolution rate, incident breakdown |
| `GET` | `/correlations` | Active alert correlation groups |
| `GET` | `/metrics` | Prometheus scrape endpoint |
| `WS` | `/ws` | WebSocket stream of incident state changes |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BACKEND` | `ollama` | LLM backend: `ollama` or `claude` |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama server URL (reachable from Docker) |
| `OLLAMA_MODEL` | `qwen3:14b` | Model name — any Ollama model with tool-use support |
| `ANTHROPIC_API_KEY` | *(unset)* | Required when `LLM_BACKEND=claude` |
| `APPROVAL_MODE` | `AUTO` | Approval gate: `AUTO` \| `DRY_RUN` \| `MANUAL` |
| `DATABASE_URL` | `postgresql+asyncpg://sre:sre@postgres:5432/runbooks` | PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379` | Redis connection string |
| `PROMETHEUS_URL` | `http://mock-prometheus:9091` | Prometheus base URL |
| `NUM_WORKERS` | `4` | Max concurrent ARQ jobs in the worker |
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `CORRELATION_WINDOW_SECONDS` | `300` | Seconds to group related alerts into one incident |
| `SLACK_WEBHOOK_URL` | *(unset)* | Slack incoming webhook for escalations |
| `PAGERDUTY_ROUTING_KEY` | *(unset)* | PagerDuty Events v2 routing key for escalations |
| `API_KEY` | *(unset)* | When set, requires `X-API-Key: <value>` on all requests |
| `MOCK_SCENARIO` | `high_error_rate` | Scenario served by mock-prometheus |
| `COMPOSE_PROJECT_NAME` | *(directory name)* | Docker Compose project prefix for container name resolution |

---

## Project Structure

```
ai-runbook-automation/
├── agent/                      # Core agent logic
│   ├── agent.py                # Main OBSERVE→REASON→ACT→VERIFY→REPORT loop
│   ├── approval_gate.py        # Human approval gate (AUTO/DRY_RUN/MANUAL)
│   ├── runbook_registry.py     # Loads YAML runbooks, maps alerts → runbooks
│   ├── state_machine.py        # Incident state machine with event history
│   ├── metrics.py              # Prometheus metrics (MTTR, actions, tokens)
│   ├── llm/
│   │   ├── base.py             # LLMResponse + ToolCall dataclasses
│   │   ├── factory.py          # Creates backend from LLM_BACKEND env var
│   │   ├── ollama_backend.py   # Ollama (OpenAI-compatible API)
│   │   └── claude_backend.py   # Anthropic Claude API
│   └── actions/                # Tool handlers
│       ├── registry.py         # ActionRegistry + ActionResult
│       ├── prometheus.py       # PromQL queries
│       ├── docker_actions.py   # Container restart/scale/status
│       ├── log_actions.py      # Container log collection + error parsing
│       ├── diagnostic.py       # System health diagnostics
│       └── escalation.py       # Slack + PagerDuty escalation
├── api/                        # FastAPI web layer
│   ├── main.py                 # All HTTP + WebSocket endpoints
│   ├── models.py               # Pydantic models
│   ├── alert_queue.py          # ARQ enqueue wrapper
│   ├── correlation.py          # Alert correlation engine (Redis)
│   ├── auth.py                 # API key authentication dependency
│   └── ws_manager.py           # WebSocket connection manager
├── db/                         # Database layer
│   ├── database.py             # Async SQLAlchemy engine + session
│   ├── models.py               # Incident ORM model (JSONB columns)
│   └── incident_store.py       # CRUD operations + MTTR stats
├── worker/                     # ARQ worker process
│   ├── main.py                 # WorkerSettings, startup/shutdown hooks
│   ├── jobs.py                 # process_alert ARQ job
│   ├── publisher.py            # Redis pub/sub publisher
│   └── pir.py                  # Post-Incident Review generator
├── ui/                         # React dashboard
│   ├── src/
│   │   ├── lib/                # API client, format helpers
│   │   ├── types/              # TypeScript types
│   │   ├── hooks/              # React Query + WebSocket hooks
│   │   ├── components/         # UI components
│   │   └── pages/              # Dashboard, IncidentDetail, Runbooks, Stats
│   └── vite.config.ts          # Proxy: /api and /ws → :8000
├── runbooks/                   # YAML runbook definitions
│   ├── high_error_rate.yml
│   ├── high_latency.yml
│   ├── memory_leak.yml
│   ├── service_down.yml
│   └── cpu_spike.yml
├── simulator/                  # Test environment
│   ├── mock_prometheus.py      # FastAPI mock Prometheus server
│   ├── alert_generator.py      # Generates Alertmanager payloads
│   └── scenario_runner.py      # CLI scenario runner
├── tests/
│   └── payload.json            # Sample alert payload for curl testing
├── alertmanager/
│   └── alertmanager.yml        # Routes alerts → agent webhook
├── docker-compose.yml          # All services
├── Dockerfile                  # agent-api image
├── Dockerfile.worker           # agent-worker image
├── Dockerfile.prometheus       # mock-prometheus image
├── requirements.txt
└── .env.example
```

---

## Development & Testing

### Running Tests Without Docker

All unit tests mock external dependencies (Docker, Redis, PostgreSQL) and run without any services:

```bash
# Install Python dependencies
pip install -r requirements.txt

# Unit tests only (no Docker required)
make test-unit

# Full test suite (requires running services for API integration tests)
make test

# With coverage report
make test-cov
```

**Test suite layout:**

| File | What it covers |
|------|----------------|
| `tests/test_agent.py` | SRE agent loop, approval gate, action registry |
| `tests/test_actions.py` | Docker actions, log tailing, service status |
| `tests/test_correlation.py` | Alert dedup via Redis SET NX / TTL |
| `tests/test_db.py` | Incident CRUD, MTTR stats (mocked SQLAlchemy) |
| `tests/test_worker.py` | ARQ job lifecycle, PIR generation |
| `tests/test_service_resolver.py` | Docker container name resolution |
| `tests/test_api.py` | FastAPI endpoints (requires running services) |
| `tests/test_llm_backends.py` | Ollama + Claude adapter contracts |

### Local Dev (UI hot-reload + Docker backend)

```bash
# 1. Copy env
cp .env.example .env

# 2. Start backend services only (PostgreSQL, Redis, worker, Prometheus)
make up

# 3. Start Vite dev server with hot-reload
make ui-dev        # → http://localhost:3000
```

### Python Compatibility

The codebase requires **Python 3.9+**. All files use `from __future__ import annotations`
for deferred evaluation of type hints. The exception is `db/models.py` — SQLAlchemy 2.x
evaluates `Mapped[]` annotations at import time, so `Optional[X]` is used directly there
instead of `X | None`.

---

## Troubleshooting

### Agent worker shows "LLM unreachable" in logs

1. Check Ollama is running on the host: `ollama ps`
2. Verify `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env`
3. Pull the model if missing: `ollama pull qwen3:14b`
4. Switch to Claude: set `LLM_BACKEND=claude` and provide `ANTHROPIC_API_KEY`

### Database migration errors on first start

The `api` service runs `alembic upgrade head` on startup. If it fails:

```bash
make logs          # check alembic output
make reset         # drop volumes and restart clean
```

### Alert webhook returns 422

Alertmanager payload must include a `labels.alertname` field. Test with:

```bash
make fire-alert
```

### UI shows blank incident list

- Check `VITE_API_URL` in `ui/.env` (defaults to `http://localhost:8000`)
- Confirm the `api` container is healthy: `docker ps`
- WebSocket updates require the `api` service — no polling fallback

### Docker container not found errors in agent

The agent resolves logical service names (e.g. `api`) to Docker container names
(e.g. `ai-runbook-automation-api-1`). Override with `COMPOSE_PROJECT_NAME` in `.env`
if your project directory name differs from `ai-runbook-automation`.

---

## Security Notes

- `ANTHROPIC_API_KEY` is **never** hardcoded — always injected via environment variable
- Docker images run as non-root users
- All actions in AUTO mode are pre-approved for unattended operation; use MANUAL mode for human-in-the-loop
- DRY_RUN mode is always safe — zero side effects
- API key auth available via `API_KEY` env var (`/health` and `/metrics` bypass auth for scraping)
- Escalation webhooks use HTTPS
