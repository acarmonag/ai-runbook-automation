"""
Async alert queue with worker pool.

Receives alerts from the webhook endpoint, deduplicates them,
and dispatches them to worker coroutines that run the agent loop.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

NUM_WORKERS = int(os.environ.get("NUM_WORKERS", "2"))


class AsyncAlertQueue:
    def __init__(self, agent_runner, num_workers: int = NUM_WORKERS):
        self.agent_runner = agent_runner
        self.num_workers = num_workers
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._in_flight: set[str] = set()  # fingerprints currently being processed
        self._incidents: dict[str, dict] = {}  # incident_id → incident record
        self._workers: list[asyncio.Task] = []
        self._processed_count = 0
        self._running = False

    async def start(self) -> None:
        """Start the worker pool."""
        self._running = True
        for i in range(self.num_workers):
            task = asyncio.create_task(
                self._worker(worker_id=i), name=f"alert-worker-{i}"
            )
            self._workers.append(task)
        logger.info(f"Alert queue started with {self.num_workers} workers")

    async def stop(self) -> None:
        """Gracefully stop all workers."""
        self._running = False
        for _ in self._workers:
            await self._queue.put(None)  # Poison pill
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("Alert queue stopped")

    async def enqueue(self, alert: dict[str, Any]) -> Optional[str]:
        """
        Enqueue an alert for processing.

        Returns incident_id if queued, None if deduplicated/dropped.
        """
        fingerprint = alert.get("fingerprint", str(uuid.uuid4()))
        alert_name = alert.get("labels", {}).get("alertname", "Unknown")

        # Deduplication — skip if fingerprint already in-flight
        if fingerprint in self._in_flight:
            logger.info(
                f"Deduplicating alert {alert_name} (fingerprint {fingerprint} already processing)"
            )
            return None

        incident_id = str(uuid.uuid4())[:8]
        self._in_flight.add(fingerprint)

        # Create incident record in PENDING state
        incident_record = {
            "incident_id": incident_id,
            "alert_name": alert_name,
            "alert": alert,
            "status": "PENDING",
            "fingerprint": fingerprint,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
            "summary": None,
            "root_cause": None,
            "actions_taken": [],
            "recommendations": [],
            "reasoning_transcript": [],
            "state_history": [],
            "full_agent_response": None,
        }
        self._incidents[incident_id] = incident_record

        try:
            await asyncio.wait_for(
                self._queue.put((incident_id, alert, fingerprint)),
                timeout=5.0,
            )
            logger.info(f"Queued alert {alert_name} as incident {incident_id}")
            return incident_id
        except asyncio.TimeoutError:
            logger.error("Alert queue is full — dropping alert")
            self._in_flight.discard(fingerprint)
            del self._incidents[incident_id]
            return None

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine that processes alerts from the queue."""
        logger.info(f"Worker {worker_id} started")
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if item is None:
                break  # Poison pill

            incident_id, alert, fingerprint = item
            alert_name = alert.get("labels", {}).get("alertname", "Unknown")

            logger.info(f"[Worker {worker_id}] Processing {alert_name} ({incident_id})")
            self._incidents[incident_id]["status"] = "PROCESSING"

            try:
                # Run agent in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                report = await loop.run_in_executor(
                    None, self.agent_runner, alert
                )
                self._incidents[incident_id].update({
                    "status": report.get("status", "RESOLVED"),
                    "summary": report.get("summary"),
                    "root_cause": report.get("root_cause"),
                    "actions_taken": report.get("actions_taken", []),
                    "recommendations": report.get("recommendations", []),
                    "reasoning_transcript": report.get("reasoning_transcript", []),
                    "state_history": report.get("state_history", []),
                    "resolved_at": report.get("resolved_at"),
                    "full_agent_response": report.get("full_agent_response"),
                })
                self._processed_count += 1
                logger.info(
                    f"[Worker {worker_id}] Completed {alert_name} ({incident_id}): "
                    f"{report.get('status', 'UNKNOWN')}"
                )
            except Exception as e:
                logger.error(
                    f"[Worker {worker_id}] Agent failed for {alert_name} ({incident_id}): {e}",
                    exc_info=True,
                )
                self._incidents[incident_id].update({
                    "status": "FAILED",
                    "summary": f"Agent error: {e}",
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                })
            finally:
                self._in_flight.discard(fingerprint)
                self._queue.task_done()

        logger.info(f"Worker {worker_id} stopped")

    def get_incident(self, incident_id: str) -> Optional[dict]:
        return self._incidents.get(incident_id)

    def list_incidents(self) -> list[dict]:
        return sorted(
            self._incidents.values(),
            key=lambda x: x["started_at"],
            reverse=True,
        )

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def active_workers(self) -> int:
        return sum(1 for w in self._workers if not w.done())

    @property
    def processed_count(self) -> int:
        return self._processed_count
