"""
WebSocket connection manager — tracks active connections and broadcasts messages.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.debug(f"WebSocket connected ({len(self._connections)} total)")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections = [c for c in self._connections if c is not ws]
        logger.debug(f"WebSocket disconnected ({len(self._connections)} remaining)")

    async def broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
