.PHONY: up down logs test simulate sim-memory sim-down sim-cpu sim-latency sim-live fire-alert incidents health runbooks clean install install-dev ui-install ui-dev ui-build help

AGENT_URL ?= http://localhost:8000
PYTHON    := python3

help:
	@echo ""
	@echo "  AI Runbook Automation — Available Commands"
	@echo "  ==========================================="
	@echo "  make up          Start all services via Docker Compose"
	@echo "  make down        Stop all services"
	@echo "  make logs        Follow agent-api logs"
	@echo "  make test        Run test suite with pytest"
	@echo "  make simulate    Run high_error_rate scenario (dry_run, local)"
	@echo "  make sim-memory  Run memory_leak scenario (dry_run, local)"
	@echo "  make sim-down    Run service_down scenario (dry_run, local)"
	@echo "  make sim-cpu     Run cpu_spike scenario (dry_run, local)"
	@echo "  make sim-latency Run high_latency scenario (dry_run, local)"
	@echo "  make fire-alert  POST a sample alert to the webhook endpoint"
	@echo "  make incidents   List all incidents (pretty-printed)"
	@echo "  make health      Check API health status"
	@echo "  make clean       Stop all services and remove volumes"
	@echo "  make ui-install  Install UI dependencies (npm install in ui/)"
	@echo "  make ui-dev      Start the React dashboard on http://localhost:3000"
	@echo "  make ui-build    Build the React dashboard for production"
	@echo ""

ui-install:
	cd ui && npm install

ui-dev:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

up:
	@echo "Starting AI Runbook Automation..."
	@test -f .env || cp .env.example .env
	docker compose up -d --build
	@echo ""
	@echo "Services started:"
	@echo "  Agent API      : http://localhost:8000"
	@echo "  Ollama         : http://localhost:11434  (model: $$(grep OLLAMA_MODEL .env | cut -d= -f2))"
	@echo "  Mock Prometheus: http://localhost:9091"
	@echo "  Alertmanager   : http://localhost:9093"
	@echo ""
	@echo "Try: make simulate  (runs a local dry-run scenario)"

down:
	docker compose down --rmi all --volumes --remove-orphans

logs:
	docker compose logs -f agent-api

test:
	@echo "Running test suite..."
	$(PYTHON) -m pytest tests/ -v --tb=short

test-cov:
	@echo "Running test suite with coverage..."
	$(PYTHON) -m pytest tests/ -v --tb=short --cov=agent --cov=api --cov-report=term-missing

simulate:
	@echo "Running high_error_rate scenario (DRY_RUN)..."
	$(PYTHON) simulator/scenario_runner.py --scenario high_error_rate --mode dry_run

sim-memory:
	@echo "Running memory_leak scenario (DRY_RUN)..."
	$(PYTHON) simulator/scenario_runner.py --scenario memory_leak --mode dry_run

sim-down:
	@echo "Running service_down scenario (DRY_RUN)..."
	$(PYTHON) simulator/scenario_runner.py --scenario service_down --mode dry_run

sim-cpu:
	@echo "Running cpu_spike scenario (DRY_RUN)..."
	$(PYTHON) simulator/scenario_runner.py --scenario cpu_spike --mode dry_run

sim-latency:
	@echo "Running high_latency scenario (DRY_RUN)..."
	$(PYTHON) simulator/scenario_runner.py --scenario high_latency --mode dry_run

sim-live:
	@echo "Sending high_error_rate alert to running API..."
	$(PYTHON) simulator/scenario_runner.py --scenario high_error_rate --mode auto --url $(AGENT_URL)

fire-alert:
	@echo "Firing a sample HighErrorRate alert..."
	curl -s -X POST $(AGENT_URL)/alerts/webhook \
		-H "Content-Type: application/json" \
		-d '{ \
			"version": "4", \
			"status": "firing", \
			"receiver": "agent-webhook", \
			"groupKey": "{}:{alertname=\"HighErrorRate\"}", \
			"truncatedAlerts": 0, \
			"groupLabels": {"alertname": "HighErrorRate"}, \
			"commonLabels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api-service"}, \
			"commonAnnotations": {"summary": "HTTP error rate above 15% for api-service"}, \
			"alerts": [{ \
				"status": "firing", \
				"labels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api-service"}, \
				"annotations": {"summary": "HTTP error rate is 15.3%", "description": "Above the 10% threshold"}, \
				"startsAt": "2024-01-15T10:00:00Z", \
				"fingerprint": "fire-alert-001" \
			}] \
		}' | python3 -m json.tool

incidents:
	@echo "Fetching all incidents..."
	curl -s $(AGENT_URL)/incidents | python3 -m json.tool

health:
	@echo "Checking API health..."
	curl -s $(AGENT_URL)/health | python3 -m json.tool

runbooks:
	@echo "Listing all runbooks..."
	curl -s $(AGENT_URL)/runbooks | python3 -m json.tool

clean:
	docker compose down -v
	rm -f incidents.jsonl escalations.jsonl
	@echo "Cleaned up."

install:
	pip3 install -r requirements.txt

install-dev:
	pip3 install -r requirements.txt
	pip3 install pytest pytest-asyncio pytest-cov httpx
