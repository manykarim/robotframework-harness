"""Dummy remote HTTP MCP server for the agent-compat test.

Run: uv run --directory ~/workspace/rf-mcp-robotcode python <this file>
Serves streamable HTTP at http://127.0.0.1:6850/mcp with one tool `echo`.
Requires `Authorization: Bearer probe-token-123` (401 otherwise) and logs every request's
method/path/auth/user-agent to echo_requests.log next to this file.
"""
import os
import time

import uvicorn
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

TOKEN = "probe-token-123"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "echo_requests.log")

mcp = FastMCP("echo-probe")


@mcp.tool
def echo(text: str) -> str:
    """Echo the given text back, prefixed with ECHO:."""
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} TOOLCALL echo text={text!r}\n")
    return f"ECHO:{text}"


class AuthLog(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("authorization", "")
        ua = request.headers.get("user-agent", "")
        ok = auth == f"Bearer {TOKEN}"
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {request.method} {request.url.path} "
                    f"auth={'OK' if ok else repr(auth[:30])} ua={ua[:60]!r}\n")
        if not ok:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


app = mcp.http_app(path="/mcp")
app.add_middleware(AuthLog)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=6850, log_level="warning")
