"""Tiny local JSON API for verification: GET /api/health, GET /api/items, GET /api/items/<id>, POST /api/items.
  python api_server.py PORT"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ITEMS = [{"id": 1, "name": "Apple", "price": 1.5}, {"id": 2, "name": "Banana", "price": 0.5}]


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(200, {"status": "ok"})
        if self.path == "/api/items":
            return self._send(200, ITEMS)
        if self.path.startswith("/api/items/"):
            i = self.path.rsplit("/", 1)[1]
            it = next((x for x in ITEMS if str(x["id"]) == i), None)
            return self._send(200, it) if it else self._send(404, {"error": "not found"})
        self._send(404, {"error": "no route"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "invalid json"})
        if self.path == "/api/items" and isinstance(body, dict) and body.get("name"):
            it = {"id": len(ITEMS) + 1, "name": body["name"], "price": body.get("price", 0)}
            ITEMS.append(it)
            return self._send(201, it)
        self._send(400, {"error": "name required"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1] if len(sys.argv) > 1 else 8765)), H).serve_forever()
