import asyncio

JOB_QUEUES: dict[int, asyncio.Queue] = {}

_ws_broadcast_loop: asyncio.AbstractEventLoop | None = None


def set_ws_broadcast_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Register the asyncio loop used for thread-safe WS queue pushes (uvicorn or worker)."""
    global _ws_broadcast_loop
    _ws_broadcast_loop = loop


def get_ws_broadcast_loop() -> asyncio.AbstractEventLoop | None:
    return _ws_broadcast_loop
