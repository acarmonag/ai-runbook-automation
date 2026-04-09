# AI Runbook Automation

An LLM-powered autonomous SRE agent that monitors alerts from Prometheus/Alertmanager, reasons about root causes, selects and executes runbook actions, and reports back with what it did and why.

**This is NOT a chatbot.** It is an autonomous remediation agent with a human-approval gate for destructive actions. Claude API is used purely as a reasoning engine inside a tool-use loop.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ALERT FLOW                                  │
└─────────────────────────────────────────────────────────────────┘

Prometheus Alert
      │
      ▼
Alertmanager ──────────► POST /alerts/webhook
                                │
                         ┌──────▼──────┐
                         │ Alert Queue │ (AsyncIO, deduplication)
                         └──────┬──────┘
                                │
                    ┌───────────▼────────────┐
                    │    Worker Pool (N=2)   │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │       SRE Agent        │
                    │  ┌──────────────────┐  │
                    │  │   State Machine  │  │
                    │  │ DETECTED         │  │
                    │  │  → OBSERVING     │  │
                    │  │  → REASONING     │  │
                    │  │  → ACTING        │  │
                    │  │  → VERIFYING     │  │
                    │  │  → RESOLVED      │  │
                    │  └──────────────────┘  │
                    └───────────┬────────────┘
                                │
              ┌─────────────────▼────────────────────┐
              │           Claude API                 │
              │   claude-sonnet-4-5 (tool_use)       │
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
              │                                     │
              │  AUTO:    non-destructive → auto    │
              │           destructive → human input │
              │  DRY_RUN: log only, never execute   │
              │  MANUAL:  always prompt human       │
              └──────────────┬──────────────────────┘
                             │
         ┌───────────────────┼──────────────────────┐
         │                   │                      │
         ▼                   ▼                      ▼
  Prometheus           Docker Actions         Escalation
  (PromQL queries)     (restart/scale)        (webhook + log)
         │                   │                      │
         └───────────────────┼──────────────────────┘
                             │
                    ┌────────▼──────────┐
                    │ Incident Report   │
                    │  • root_cause     │
                    │  • actions_taken  │
                    │  • transcript     │
                    │  → incidents.jsonl│
                    └───────────────────┘
```

---

## Agent Reasoning Loop

The agent runs a strict **OBSERVE → REASON → ACT → VERIFY → REPORT** loop:

1. **OBSERVE** — Collect current system state. The agent calls `get_metrics`, `get_service_status`, and `get_recent_logs` to understand what's happening *right now*.

2. **REASON** — Claude receives the alert details, runbook context, and observation results. It reasons about the most likely root cause and selects the appropriate remediation action. It must explain its reasoning before acting.

3. **ACT** — The agent executes the chosen action via the actions registry. Destructive actions (restarts, scale-down) go through the approval gate first.

4. **VERIFY** — After acting, the agent re-collects metrics to confirm the alert condition has resolved. If not, it loops back to REASON.

5. **REPORT** — The agent produces a structured incident report with root cause analysis, all actions taken, and recommendations for the team.

---

## Quickstart

```bash
# 1. Clone the repo
git clone <repo-url> && cd ai-runbook-automation

# 2. Copy and configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY (or leave default for Ollama)

# 3. Start all services
make up

# 4. Run a dry-run simulation (no real actions)
make simulate

# 5. View the incident report
make incidents

# 6. (Optional) Start the React dashboard
make ui-install   # first time only
make ui-dev       # opens http://localhost:3000
```

---

## React Dashboard

A real-time SRE dashboard built with React, TypeScript, and TailwindCSS. Connects to the FastAPI backend via proxy — no separate auth or config needed.

```
┌─────────────────────────────────────────────────────────┐
│  SRE Dashboard  (http://localhost:3000)                 │
│                                                         │
│  ┌─────────────────────────┐  ┌───────────────────────┐ │
│  │  Incident Feed          │  │  Alert Simulator      │ │
│  │  • live 2s polling      │  │  • 5 scenarios        │ │
│  │  • status badges        │  │  • fire & watch       │ │
│  │  • click for detail     │  ├───────────────────────┤ │
│  │                         │  │  Service Health       │ │
│  │  Incident Detail        │  │  • LLM reachability   │ │
│  │  • root cause           │  │  • Prometheus status  │ │
│  │  • actions timeline     │  │  • queue / workers    │ │
│  │  • AI transcript        │  └───────────────────────┘ │
│  │  • approve/reject gate  │                            │
│  └─────────────────────────┘                            │
│                                                         │
│  Runbooks page: browse all loaded runbooks with         │
│  triggers, action sequences, escalation thresholds      │
└─────────────────────────────────────────────────────────┘
```

### Dashboard Features

| Feature | Description |
|---------|-------------|
| **Incident Feed** | Live list of all incidents, sorted newest-first. Status badges, action count, duration. Click to drill in. |
| **Incident Detail** | Alert labels, root cause analysis, full actions timeline with output, recommendations, and the complete Claude reasoning transcript rendered as chat bubbles. |
| **Alert Simulator** | Drop-down to choose scenario (high_error_rate, high_latency, memory_leak, service_down, cpu_spike) and fire it directly from the browser. |
| **Approval Gate** | When `APPROVAL_MODE=MANUAL`, an amber banner appears on pending incidents with Approve / Reject buttons. |
| **Health Panel** | Live LLM backend status, Prometheus reachability, queue depth, active workers — refreshes every 5s. |
| **Runbook Browser** | Searchable cards showing each runbook's triggers, action steps, and escalation thresholds. |
| **Live Indicator** | Green pulse in the top bar on every successful poll. Red when the backend is unreachable. |

### Dashboard Quickstart

```bash
# Install Node.js dependencies (one-time)
make ui-install

# Start dev server with hot reload
make ui-dev
# → http://localhost:3000

# Production build
make ui-build
# → ui/dist/ (serve with any static server or behind nginx)
```

The dev server proxies `/api/*` to `http://localhost:8000`, so CORS is never an issue in development.

### Dashboard Project Structure

```
ui/
├── src/
│   ├── lib/          # API client, React Query setup, format helpers
│   ├── types/        # TypeScript types (Incident, Runbook, Health)
│   ├── hooks/        # React Query hooks (useIncidents, useHealth, useFireAlert, ...)
│   ├── components/
│   │   ├── incidents/  # Feed, detail, status badges, actions timeline, transcript
│   │   ├── simulator/  # AlertSimulator form
│   │   ├── health/     # HealthPanel
│   │   ├── runbooks/   # RunbookCard
│   │   └── layout/     # Sidebar, TopBar, LiveIndicator
│   └── pages/        # DashboardPage, IncidentDetailPage, RunbooksPage
└── vite.config.ts    # Proxy: /api → http://localhost:8000
```

---

## Running Scenarios

All scenarios run the full Claude reasoning loop against mock Prometheus and Docker services.

```bash
# Dry-run simulations (safe — no real actions executed)
make simulate       # High error rate: 15% HTTP 500s
make sim-memory     # Memory leak: growing to 1.8GB
make sim-down       # Service down: health checks failing
make sim-cpu        # CPU spike: 94% utilization
make sim-latency    # High latency: p99 at 4.2s

# Direct scenario runner with full output
python simulator/scenario_runner.py --scenario memory_leak --mode dry_run
python simulator/scenario_runner.py --list

# Send to a running API instance
python simulator/scenario_runner.py --scenario service_down --url http://localhost:8000
```

---

## Runbooks

Each runbook is a YAML file in `runbooks/` that maps alert names to investigation and remediation sequences.

| Runbook | Triggers | Key Actions |
|---------|----------|-------------|
| `high_error_rate` | HighErrorRate, ServiceDegraded | get_metrics → get_recent_logs → restart_service (if known bug) → verify |
| `high_latency` | HighLatency, SlowEndpoint | get_metrics → get_service_status → scale_service (if CPU>80%) → verify |
| `memory_leak` | MemoryLeakDetected, HighMemoryUsage | get_metrics → get_recent_logs (OOM) → run_diagnostic → restart_service → verify |
| `service_down` | ServiceDown, HealthCheckFailing | get_service_status → get_recent_logs → restart_service → escalate (if still down) |
| `cpu_spike` | HighCPU, CPUSaturation | get_metrics → run_diagnostic → scale_service → verify |

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
  Escalate if metric remains above threshold X after remediation action.
  Also escalate if root cause is unknown.

metadata:
  severity: P2
  team: platform
  runbook_version: "1.0"
```

No code changes needed — the registry picks up new YAML files automatically on restart.

---

## Approval Modes

Set via `APPROVAL_MODE` environment variable:

| Mode | Behavior |
|------|----------|
| `AUTO` | Auto-approves non-destructive actions (metrics, logs, diagnostics). Prompts for destructive actions (restart, scale-down). **Default.** |
| `DRY_RUN` | Logs all actions but never executes any. Safe for testing and CI. |
| `MANUAL` | Prompts for human approval on every action. |

Destructive actions that require approval in AUTO/MANUAL mode:
- `restart_service` — always destructive
- `scale_service` — only when scaling DOWN (replicas < current)

---

## Adding a New Action

1. Add the handler function to an appropriate file in `agent/actions/`:

```python
# agent/actions/my_actions.py
def my_new_action(param1: str, param2: int = 10) -> dict:
    """Does something useful."""
    result = do_something(param1, param2)
    return {"success": True, "output": result}
```

2. Register it in `agent/actions/registry.py`:

```python
from agent.actions.my_actions import my_new_action
registry.register("my_new_action", my_new_action)
```

3. Add the tool definition in `agent/agent.py` `TOOL_DEFINITIONS`:

```python
{
    "name": "my_new_action",
    "description": "Does something useful when X condition is met.",
    "input_schema": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {"type": "integer", "description": "...", "default": 10},
        },
        "required": ["param1"]
    }
}
```

---

## API Reference

### POST /alerts/webhook
Receive Alertmanager webhook payload. Matches Alertmanager v4 format exactly.

```bash
curl -X POST http://localhost:8000/alerts/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "version": "4",
    "status": "firing",
    "receiver": "agent-webhook",
    "groupLabels": {"alertname": "HighErrorRate"},
    "commonLabels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api-service"},
    "commonAnnotations": {"summary": "Error rate above 10%"},
    "groupKey": "test",
    "truncatedAlerts": 0,
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api-service"},
      "annotations": {"summary": "Error rate is 15.3%"},
      "startsAt": "2024-01-15T10:00:00Z",
      "fingerprint": "abc123"
    }]
  }'
```

### GET /incidents
List all incidents with status, alert name, actions taken, and duration.

```bash
curl http://localhost:8000/incidents | jq .
```

### GET /incidents/{id}
Full incident details including the Claude reasoning transcript.

```bash
curl http://localhost:8000/incidents/abc12345 | jq .
```

### POST /incidents/{id}/approve
Approve a pending destructive action (for MANUAL mode).

```bash
curl -X POST http://localhost:8000/incidents/abc12345/approve \
  -H "Content-Type: application/json" \
  -d '{"action": "restart_service", "operator": "oncall-engineer"}'
```

### POST /incidents/{id}/reject
Reject a pending action with reason.

```bash
curl -X POST http://localhost:8000/incidents/abc12345/reject \
  -H "Content-Type: application/json" \
  -d '{"action": "restart_service", "reason": "Service is in maintenance window"}'
```

### GET /runbooks
List all loaded runbooks.

```bash
curl http://localhost:8000/runbooks | jq .
```

### POST /simulate
Simulate alert processing in DRY_RUN mode — safe to call at any time.

```bash
curl -X POST http://localhost:8000/simulate -d @payload.json
```

### GET /health
Service health including Claude API and Prometheus reachability.

```bash
curl http://localhost:8000/health | jq .
```

---

## Example Incident Report

```json
{
  "incident_id": "a1b2c3d4",
  "alert_name": "MemoryLeakDetected",
  "status": "RESOLVED",
  "summary": "Worker service restarted to recover from memory leak — memory reclaimed from 1.8GB to 256MB",
  "root_cause": "CacheManager objects were not being evicted, causing linear memory growth at ~25MB/min. Restart clears the cache and reclaims memory.",
  "actions_taken": [
    {
      "action": "get_metrics",
      "params": {"query": "container_memory_usage_bytes{container_name='worker-service'}"},
      "result": "SUCCESS",
      "output": {"value": 1932735283.2, "labels": {"container_name": "worker-service"}},
      "duration_ms": 45
    },
    {
      "action": "get_recent_logs",
      "params": {"service": "worker-service", "lines": 200},
      "result": "SUCCESS",
      "output": {"has_errors": true, "error_summary": {"total_error_lines": 4, "pattern_counts": {"OOM": 1, "ERROR": 3}}},
      "duration_ms": 120
    },
    {
      "action": "restart_service",
      "params": {"service": "worker-service"},
      "result": "SUCCESS",
      "output": {"success": true, "new_status": "running"},
      "duration_ms": 3200
    }
  ],
  "recommendations": [
    "Fix the CacheManager eviction policy — LRU with a max size of 10,000 entries",
    "Add a Prometheus alert for memory growth rate (>10MB/min)",
    "Consider adding a periodic cache clear as a short-term mitigation"
  ]
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | **required** | Your Anthropic API key |
| `PROMETHEUS_URL` | `http://localhost:9091` | Prometheus base URL |
| `APPROVAL_MODE` | `AUTO` | Approval gate mode: AUTO \| DRY_RUN \| MANUAL |
| `NUM_WORKERS` | `2` | Number of concurrent alert processing workers |
| `LOG_LEVEL` | `INFO` | Logging level: DEBUG \| INFO \| WARNING \| ERROR |
| `DRY_RUN` | `false` | Force DRY_RUN for all actions regardless of APPROVAL_MODE |
| `MOCK_SCENARIO` | `high_error_rate` | Scenario for mock-prometheus metrics |
| `ESCALATION_WEBHOOK_URL` | *(unset)* | Optional webhook for escalation notifications |
| `INCIDENTS_FILE` | `incidents.jsonl` | Path to persist incident records |

---

## Project Structure

```
ai-runbook-automation/
├── agent/                      # Core agent logic
│   ├── agent.py                # Main reasoning engine + Claude tool_use loop
│   ├── approval_gate.py        # Human approval gate (AUTO/DRY_RUN/MANUAL)
│   ├── runbook_registry.py     # Loads YAML runbooks, maps alerts → runbooks
│   ├── state_machine.py        # Incident state machine with event history
│   └── actions/                # Action handlers
│       ├── registry.py         # ActionRegistry + ActionResult
│       ├── prometheus.py       # PromQL queries
│       ├── docker_actions.py   # Container restart/scale/status
│       ├── log_actions.py      # Container log collection + error parsing
│       ├── diagnostic.py       # System health diagnostics
│       └── escalation.py       # Escalation record + webhook
├── api/                        # FastAPI web layer
│   ├── main.py                 # All API endpoints
│   ├── models.py               # Pydantic models (AlertmanagerWebhook, Incident, etc.)
│   └── alert_queue.py          # Async queue + worker pool
├── runbooks/                   # YAML runbook definitions
│   ├── high_error_rate.yml
│   ├── high_latency.yml
│   ├── memory_leak.yml
│   ├── service_down.yml
│   └── cpu_spike.yml
├── simulator/                  # Test environment
│   ├── alert_generator.py      # Generates realistic Alertmanager payloads
│   ├── mock_prometheus.py      # FastAPI mock Prometheus server
│   ├── mock_services.py        # Mock Docker service state
│   └── scenario_runner.py      # CLI scenario runner
├── tests/                      # Test suite
│   ├── conftest.py             # Fixtures (mock Claude, sample alerts, etc.)
│   ├── test_agent.py           # Agent + state machine + runbook + approval tests
│   ├── test_actions.py         # Action handler tests
│   └── test_api.py             # API endpoint tests
├── alertmanager/
│   └── alertmanager.yml        # Alertmanager config → routes to agent webhook
├── docker-compose.yml          # All services
├── Dockerfile                  # Agent API image
├── Dockerfile.prometheus       # Mock Prometheus image
├── requirements.txt
├── Makefile
└── .env.example
```

---

## Security Notes

- `ANTHROPIC_API_KEY` is **never** hardcoded — always injected via environment
- The Docker image runs as a non-root user (`agent`)
- Destructive actions require human approval in AUTO mode
- DRY_RUN mode is always safe — zero side effects
- Escalation webhooks use HTTPS by default
