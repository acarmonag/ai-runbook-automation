.PHONY: up down dev reset logs logs-worker logs-ui test test-unit test-cov \
        simulate sim-memory sim-down sim-cpu sim-latency sim-live \
        fire-alert incidents health runbooks \
        clean install install-dev ui-install ui-dev ui-build help

AGENT_URL ?= http://localhost:8000
PYTHON    := python3

# ── Help ───────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  AI Runbook Automation — Commands"
	@echo "  ================================="
	@echo ""
	@echo "  Stack"
	@echo "    make up          Build and start all services (Dashboard at :3000)"
	@echo "    make down        Stop all services (keeps volumes)"
	@echo "    make clean       Stop all services and delete data volumes"
	@echo "    make reset       Clear Redis correlation keys + reset Prometheus scenario"
	@echo ""
	@echo "  Development"
	@echo "    make dev         Start backend via Docker + UI via Vite dev server (:3000)"
	@echo "    make ui-dev      Vite dev server only (backend must already be up)"
	@echo "    make ui-build    Build the React dashboard for production"
	@echo "    make ui-install  Install UI npm dependencies"
	@echo ""
	@echo "  Logs"
	@echo "    make logs        Follow agent-api logs"
	@echo "    make logs-worker Follow agent-worker logs"
	@echo "    make logs-ui     Follow nginx UI logs"
	@echo ""
	@echo "  Testing"
	@echo "    make test        Run full test suite with pytest"
	@echo "    make test-unit   Run unit tests only (no Docker required)"
	@echo "    make test-cov    Run tests with coverage report"
	@echo "    make fire-alert  POST a HighErrorRate alert to the webhook"
	@echo "    make simulate    Run high_error_rate scenario (dry-run, local)"
	@echo "    make incidents   List all incidents"
	@echo "    make health      Check API health"
	@echo ""

# ── Stack ──────────────────────────────────────────────────────────────────────

up:
	@echo "Starting AI Runbook Automation..."
	@test -f .env || cp .env.example .env
	@# Free port 3000 — stop any local Vite dev server if running
	@-pkill -f "vite" 2>/dev/null; sleep 0.5; true
	docker compose up -d --build
	@echo ""
	@echo "  Dashboard       http://localhost:3000"
	@echo "  Agent API       http://localhost:8000"
	@echo "  Mock Prometheus http://localhost:9091"
	@echo "  Alertmanager    http://localhost:9093"
	@echo "  Ollama          http://localhost:11434"
	@echo ""
	@echo "  Fire a test alert:  make fire-alert"
	@echo "  Watch the worker:   make logs-worker"
	@echo ""

down:
	docker compose down --remove-orphans
	@echo "Services stopped (data volumes preserved — use 'make clean' to delete them)"

clean:
	docker compose down -v --remove-orphans
	rm -f incidents.jsonl escalations.jsonl
	@echo "Cleaned up."

reset:
	@echo "Resetting Redis correlation keys and Prometheus scenario state..."
	docker compose exec redis redis-cli DEL \
		corr:api:higherrorrate \
		corr:api:highlatency \
		corr:api:servicedown \
		corr:api:highcpu \
		corr:worker:memoryleakdetected || true
	curl -s -X POST http://localhost:9091/api/v1/reset | python3 -m json.tool
	@echo "Ready for the next test run."

# ── Development ────────────────────────────────────────────────────────────────

dev:
	@echo "Starting backend services via Docker (no UI container)..."
	@test -f .env || cp .env.example .env
	docker compose up -d --build agent-api agent-worker postgres redis mock-prometheus alertmanager
	@echo ""
	@echo "  Backend ready — starting Vite dev server at http://localhost:3000"
	@echo ""
	cd ui && npm run dev

ui-install:
	cd ui && npm install

ui-dev:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

# ── Logs ───────────────────────────────────────────────────────────────────────

logs:
	docker compose logs -f agent-api

logs-worker:
	docker compose logs -f agent-worker

logs-ui:
	docker compose logs -f ui

# ── Tests ──────────────────────────────────────────────────────────────────────

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

test-unit:
	$(PYTHON) -m pytest tests/ -v --tb=short \
		-k "not TestHealthEndpoint and not TestWebhookEndpoint and not TestIncidentsEndpoint and not TestApprovalEndpoints and not TestRunbooksEndpoint and not TestSimulateEndpoint"

test-cov:
	$(PYTHON) -m pytest tests/ -v --tb=short --cov=agent --cov=api --cov=worker --cov=db --cov-report=term-missing

# ── Simulation ────────────────────────────────────────────────────────────────

simulate:
	$(PYTHON) simulator/scenario_runner.py --scenario high_error_rate --mode dry_run

sim-memory:
	$(PYTHON) simulator/scenario_runner.py --scenario memory_leak --mode dry_run

sim-down:
	$(PYTHON) simulator/scenario_runner.py --scenario service_down --mode dry_run

sim-cpu:
	$(PYTHON) simulator/scenario_runner.py --scenario cpu_spike --mode dry_run

sim-latency:
	$(PYTHON) simulator/scenario_runner.py --scenario high_latency --mode dry_run

sim-live:
	$(PYTHON) simulator/scenario_runner.py --scenario high_error_rate --mode auto --url $(AGENT_URL)

# ── Alerting ──────────────────────────────────────────────────────────────────

fire-alert:
	@echo "Firing HighErrorRate alert..."
	@curl -s -X POST $(AGENT_URL)/alerts/webhook \
		-H "Content-Type: application/json" \
		-d '{ \
			"version": "4", \
			"status": "firing", \
			"receiver": "agent-webhook", \
			"groupKey": "{}:{alertname=\"HighErrorRate\"}", \
			"truncatedAlerts": 0, \
			"groupLabels": {"alertname": "HighErrorRate"}, \
			"commonLabels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api"}, \
			"commonAnnotations": {"summary": "HTTP error rate above 15% for api"}, \
			"alerts": [{ \
				"status": "firing", \
				"labels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api"}, \
				"annotations": {"summary": "HTTP error rate is 15.3%", "description": "Above the 10% threshold"}, \
				"startsAt": "$(shell date -u +%Y-%m-%dT%H:%M:%SZ)", \
				"fingerprint": "$(shell head -c4 /dev/urandom | xxd -p)" \
			}] \
		}' | python3 -m json.tool

incidents:
	curl -s $(AGENT_URL)/incidents | python3 -m json.tool

health:
	curl -s $(AGENT_URL)/health | python3 -m json.tool

runbooks:
	curl -s $(AGENT_URL)/runbooks | python3 -m json.tool

# ── Install ───────────────────────────────────────────────────────────────────

install:
	pip3 install -r requirements.txt

install-dev:
	pip3 install -r requirements.txt
	pip3 install pytest pytest-asyncio pytest-cov httpx
