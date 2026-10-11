"""Tiny Robot Framework library that serves an orders JSON file over HTTP.

Keywords:
    Start Orders Server    <path to orders.json>    -> returns the base URL (http://127.0.0.1:<port>)
    Stop Orders Server

Endpoints:
    GET /orders          -> the full JSON list from the file
    GET /orders/<id>     -> a single order (404 if unknown)
    GET /health          -> {"status": "ok"}

The server binds an ephemeral port on 127.0.0.1 and runs in a daemon thread.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Handler(BaseHTTPRequestHandler):
    orders: list = []

    def _send(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/orders":
            self._send(200, self.orders)
        elif path.startswith("/orders/"):
            oid = path.rsplit("/", 1)[-1]
            match = [o for o in self.orders if str(o.get("id")) == oid]
            if match:
                self._send(200, match[0])
            else:
                self._send(404, {"error": f"order {oid} not found"})
        elif path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, format, *args):  # keep robot console quiet
        pass


class OrdersServer:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self):
        self._server = None
        self._thread = None

    def start_orders_server(self, json_path):
        """Load ``json_path`` and serve it on an ephemeral localhost port. Returns the base URL."""
        if self._server is not None:
            self.stop_orders_server()
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        handler = type("OrdersHandler", (_Handler,), {"orders": data})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop_orders_server(self):
        """Stop the server started by `Start Orders Server` (no-op if not running)."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
