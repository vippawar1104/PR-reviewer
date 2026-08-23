import logging

from fastapi import WebSocket

logger = logging.getLogger("ai_pr_reviewer")

_clients: set[WebSocket] = set()


def register(ws: WebSocket) -> None:
    _clients.add(ws)


def unregister(ws: WebSocket) -> None:
    _clients.discard(ws)


async def broadcast(event: dict) -> None:
    dead = set()
    for ws in _clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _clients.discard(ws)
