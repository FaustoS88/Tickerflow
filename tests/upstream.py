"""A local aiohttp server that stands in for the provider APIs in tests — no network."""

from __future__ import annotations

import asyncio
import socket
import threading
from dataclasses import dataclass

from aiohttp import web


@dataclass
class _Reply:
    payload: object = None
    status: int = 200
    text: str | None = None
    delay: float = 0.0
    drop: bool = False


class Upstream:
    """Answers GET requests by path prefix; runs on its own loop in a thread,
    so it outlives the event loops the tests open and close."""

    def __init__(self) -> None:
        self._replies: dict[str, _Reply] = {}
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.url = ""

    def reply(
        self,
        prefix: str,
        payload: object = None,
        *,
        status: int = 200,
        text: str | None = None,
        delay: float = 0.0,
        drop: bool = False,
    ) -> None:
        """Answer requests under *prefix* with JSON *payload* (or raw *text*), after *delay*;
        *drop* closes the connection instead, so the client raises. A callable *payload*
        gets the query string as a dict and returns the JSON."""
        self._replies[prefix] = _Reply(payload, status, text, delay, drop)

    def reset(self) -> None:
        self._replies.clear()
        self.requests.clear()

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        self.requests.append((request.path, dict(request.query)))
        # Whole path segments only: /ohlc must not answer /ohlcv
        match = [p for p in self._replies if f"{request.path}/".startswith(f"{p}/")]
        if not match:
            return web.json_response({"error": "no reply set"}, status=404)
        r = self._replies[max(match, key=len)]
        if r.delay:
            await asyncio.sleep(r.delay)
        if r.drop:
            assert request.transport is not None
            request.transport.close()
            return web.Response()
        if r.text is not None:
            return web.Response(text=r.text, status=r.status)
        payload = r.payload(dict(request.query)) if callable(r.payload) else r.payload
        return web.json_response(payload, status=r.status)

    def start(self) -> None:
        app = web.Application()
        app.router.add_route("GET", "/{tail:.*}", self._handle)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self._loop = asyncio.new_event_loop()
        self._runner = web.AppRunner(app)
        self._loop.run_until_complete(self._runner.setup())
        self._loop.run_until_complete(web.SockSite(self._runner, sock).start())
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{sock.getsockname()[1]}"

    def stop(self) -> None:
        asyncio.run_coroutine_threadsafe(self._runner.cleanup(), self._loop).result(5)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._loop.close()
