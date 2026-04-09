#!/usr/bin/env python3
"""
Scenario runner — run a full end-to-end simulation of an SRE incident.

Usage:
    python simulator/scenario_runner.py --scenario memory_leak --mode dry_run
    python simulator/scenario_runner.py --scenario service_down --mode auto
    python simulator/scenario_runner.py --list
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_scenario(scenario: str, mode: str, target_url: str = "") -> None:
    """Run a full incident scenario."""
    from simulator.alert_generator import generate_alert, SCENARIOS

    if scenario not in SCENARIOS:
        print(f"Unknown scenario: '{scenario}'")
        print(f"Available: {list(SCENARIOS)}")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  AI RUNBOOK AUTOMATION — Scenario Runner")
    print(f"{'='*70}")
    print(f"  Scenario : {scenario}")
    print(f"  Mode     : {mode.upper()}")
    print(f"  Time     : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    scenario_info = SCENARIOS[scenario]
    print(f"Scenario: {scenario_info['description']}\n")

    # Generate alert payload
    payload = generate_alert(scenario)
    alert = payload["alerts"][0]

    print(f"Alert Generated:")
    print(f"  Name     : {alert['labels']['alertname']}")
    print(f"  Severity : {alert['labels']['severity']}")
    print(f"  Service  : {alert['labels']['service']}")
    print(f"  Summary  : {alert['annotations']['summary']}")
    print(f"  Description: {alert['annotations']['description'][:80]}...")
    print()

    if target_url:
        _send_to_api(payload, target_url)
        return

    # Run locally
    _run_agent_locally(alert, mode)


def _send_to_api(payload: dict, url: str) -> None:
    """POST alert to the running API."""
    import httpx

    endpoint = f"{url.rstrip('/')}/alerts/webhook"
    print(f"Sending alert to: {endpoint}")

    try:
        resp = httpx.post(endpoint, json=payload, timeout=10.0)
        resp.raise_for_status()
        result = resp.json()
        print(f"\nQueued! Response:")
        print(json.dumps(result, indent=2))

        if result.get("incident_ids"):
            incident_id = result["incident_ids"][0]
            print(f"\nMonitor progress:")
            print(f"  curl {url}/incidents/{incident_id} | jq .")
    except httpx.ConnectError:
        print(f"\nCannot connect to {url}")
        print("Is the agent API running? Try: make up")
    except Exception as e:
        print(f"\nError: {e}")


def _run_agent_locally(alert: dict, mode: str) -> None:
    """Run the agent loop directly in this process."""
    # Set environment for local run
    os.environ.setdefault("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    os.environ.setdefault("PROMETHEUS_URL", "http://localhost:9091")

    llm_backend = os.environ.get("LLM_BACKEND", "ollama").lower()
    if llm_backend == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: LLM_BACKEND=claude requires ANTHROPIC_API_KEY to be set")
        print("Set it with: export ANTHROPIC_API_KEY=your-key")
        sys.exit(1)

    # Set approval mode
    os.environ["APPROVAL_MODE"] = mode.upper()

    from agent.actions.registry import build_default_registry
    from agent.agent import SREAgent
    from agent.approval_gate import ApprovalGate
    from agent.runbook_registry import RunbookRegistry

    print(f"Initializing agent in {mode.upper()} mode...\n")

    registry = build_default_registry()
    runbook_registry = RunbookRegistry()
    approval_gate = ApprovalGate()
    agent = SREAgent(
        action_registry=registry,
        runbook_registry=runbook_registry,
        approval_gate=approval_gate,
    )

    alert_name = alert["labels"]["alertname"]
    runbook = runbook_registry.get_runbook(alert_name)
    if runbook:
        print(f"Runbook matched: {runbook.name}")
        print(f"Triggers: {runbook.triggers}")
        print()
    else:
        print(f"No runbook found for alert: {alert_name}")
        print("Agent will proceed without runbook guidance.\n")

    print("Starting agent reasoning loop...")
    print("-" * 70)

    start = time.time()
    report = agent.run(alert)
    elapsed = time.time() - start

    print("\n" + "=" * 70)
    print("  INCIDENT REPORT")
    print("=" * 70)
    print(f"  Incident ID  : {report['incident_id']}")
    print(f"  Alert        : {report['alert_name']}")
    print(f"  Status       : {report['status']}")
    print(f"  Duration     : {elapsed:.1f}s")
    print()

    if report.get("summary"):
        print(f"Summary:")
        print(f"  {report['summary']}")
        print()

    if report.get("root_cause"):
        print(f"Root Cause:")
        print(f"  {report['root_cause']}")
        print()

    if report.get("actions_taken"):
        print(f"Actions Taken ({len(report['actions_taken'])}):")
        for i, action in enumerate(report["actions_taken"], 1):
            status = action.get("result", "UNKNOWN")
            symbol = "✓" if status == "SUCCESS" else "✗" if status == "FAILED" else "○"
            print(f"  {i}. [{symbol}] {action['action']}")
            if action.get("params"):
                params_str = json.dumps(action["params"])[:60]
                print(f"       params: {params_str}")
        print()

    if report.get("recommendations"):
        print("Recommendations:")
        for rec in report["recommendations"]:
            print(f"  • {rec}")
        print()

    transcript = report.get("reasoning_transcript", [])
    print(f"Reasoning transcript: {len(transcript)} exchanges with Claude")

    print("\nFull report saved to: incidents.jsonl")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Run AI Runbook Automation scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simulator/scenario_runner.py --scenario memory_leak --mode dry_run
  python simulator/scenario_runner.py --scenario service_down --mode auto
  python simulator/scenario_runner.py --scenario high_error_rate --url http://localhost:8000
  python simulator/scenario_runner.py --list
        """,
    )
    parser.add_argument("--scenario", "-s", help="Scenario name to run")
    parser.add_argument(
        "--mode",
        "-m",
        default="dry_run",
        choices=["dry_run", "auto", "manual"],
        help="Approval mode (default: dry_run)",
    )
    parser.add_argument(
        "--url",
        "-u",
        default="",
        help="POST alert to this URL instead of running locally (e.g. http://localhost:8000)",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available scenarios",
    )

    args = parser.parse_args()

    if args.list:
        from simulator.alert_generator import SCENARIOS
        print("Available scenarios:")
        for name, data in SCENARIOS.items():
            print(f"  {name:<20} — {data['description']}")
        return

    if not args.scenario:
        parser.print_help()
        sys.exit(1)

    run_scenario(scenario=args.scenario, mode=args.mode, target_url=args.url)


if __name__ == "__main__":
    main()
