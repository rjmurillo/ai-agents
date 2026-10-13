"""Constants and the local order API used by the api-doc-authoring tests."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "api-doc-authoring"

WORKED_EXAMPLE = SKILL_DIR / "references" / "worked-example.md"
QTY_FIELD_V1 = "qty"
QTY_FIELD_V2 = "quantity"


def make_handler(qty_field: str) -> type[BaseHTTPRequestHandler]:
    """Build a handler whose contract requires `qty_field` on POST /orders."""
    orders: dict[str, dict[str, Any]] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return

        def _reply(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            amount = body.get(qty_field)
            if self.path != "/orders" or not isinstance(amount, int):
                self._reply(422, {"error": "missing_field", "field": qty_field})
            elif amount < 1:
                self._reply(422, {"error": "invalid_quantity"})
            else:
                order_id = f"ord_{len(orders) + 1}"
                orders[order_id] = {"id": order_id, "status": "pending", "qty": amount}
                self._reply(201, {"id": order_id, "status": "pending"})

        def do_GET(self) -> None:
            order = orders.get(self.path.removeprefix("/orders/"))
            if order is None:
                self._reply(404, {"error": "order_not_found"})
            else:
                self._reply(200, order)

    return Handler


@contextmanager
def serve(qty_field: str) -> Iterator[str]:
    """Serve the order API on a free loopback port and yield its base URL."""
    server = HTTPServer(("127.0.0.1", 0), make_handler(qty_field))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
