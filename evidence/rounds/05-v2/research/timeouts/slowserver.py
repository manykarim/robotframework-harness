"""Local HTTP server: /slow?ms=N delays the response N ms; everything else served from ../site."""
import http.server, os, sys, time, urllib.parse, functools
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site")
class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/slow":
            ms = int(urllib.parse.parse_qs(u.query).get("ms", ["5000"])[0])
            time.sleep(ms / 1000)
            body = f"<html><head><title>Slow {ms}</title></head><body><h1 id='slow'>slow {ms}</h1></body></html>".encode()
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()
    def log_message(self, *a): pass
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=SITE)).serve_forever()
