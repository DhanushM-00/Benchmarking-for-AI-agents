"""A tiny real HTTP server that impersonates the Bifrost gateway.

Used by the Phase 5 connection tests so the probes run over an actual socket
instead of a mocked ``httpx.get``.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Behaviours the fake gateway can be switched between at runtime.
MODE_OK = "ok"            # 200 + OpenAI-shaped /v1/models
MODE_UNAUTHORIZED = "unauthorized"  # 401 on /v1/models
MODE_FORBIDDEN = "forbidden"        # 403 on /v1/models
MODE_SLOW = "slow"        # never answers (models a black-holed gateway)
MODE_VK = "vk"            # Bifrost v2: requires the virtual key in x-bf-vk


class _GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the pytest output clean
        pass

    def _send(self, code: int, payload=None):
        body = json.dumps(payload if payload is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - stdlib naming
        mode = self.server.mode  # type: ignore[attr-defined]
        self.server.requests.append({"method": "GET", "path": self.path,
                                     "headers": {k.lower(): v for k, v in self.headers.items()}})
        if mode == MODE_SLOW:
            time.sleep(30)
            return
        if mode == MODE_VK:
            # Exactly what Bifrost v2.5 does when the virtual key is missing.
            if self.headers.get("x-bf-vk") != self.server.virtual_key:  # type: ignore[attr-defined]
                self._send(401, {"error": "virtual key is required. Provide a virtual key via the x-bf-vk header."})
                return
            self._send(200, {"data": [{"id": "gemini/gemini-2.5-pro"}]})
            return
        if self.path.startswith("/v1/models"):
            if mode == MODE_UNAUTHORIZED:
                self._send(401, {"error": "invalid virtual key"})
                return
            if mode == MODE_FORBIDDEN:
                self._send(403, {"error": "forbidden"})
                return
            self._send(200, {"data": [
                {"id": "gemini/gemini-2.5-pro"},
                {"id": "openrouter/google/gemini-2.5-flash"},
            ]})
            return
        self._send(200, {"status": "ok", "version": "1.0.0"})

    def do_POST(self):  # noqa: N802 - stdlib naming
        self.server.requests.append({"method": "POST", "path": self.path,
                                     "headers": {k.lower(): v for k, v in self.headers.items()}})
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        mode = self.server.mode  # type: ignore[attr-defined]
        if mode == MODE_VK and self.headers.get("x-bf-vk") != self.server.virtual_key:  # type: ignore[attr-defined]
            self._send(401, {"error": "virtual key is required. Provide a virtual key via the x-bf-vk header."})
            return
        self._send(200, {
            "id": "chatcmpl-1",
            "choices": [{"message": {"content": "```python\npass\n```"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
        })


class FakeGateway:
    """A real HTTP server whose behaviour can be flipped at runtime."""

    def __init__(self, mode: str = MODE_OK, virtual_key: str = "sk-bf-test"):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
        self.server.mode = mode  # type: ignore[attr-defined]
        self.server.virtual_key = virtual_key  # type: ignore[attr-defined]
        self.server.requests = []  # type: ignore[attr-defined]
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def set_mode(self, mode: str) -> None:
        self.server.mode = mode  # type: ignore[attr-defined]

    @property
    def requests(self) -> list[dict]:
        """Every request the fake gateway received (path + headers)."""
        return self.server.requests  # type: ignore[attr-defined]

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def free_port() -> int:
    """A TCP port with nothing listening on it."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
