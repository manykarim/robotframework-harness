#!/usr/bin/env bash
# Helper-owned isolated display: start Xvfb, mint rf-mcp's isolation marker + X-server PID, exec the daemon.
set -e
for n in $(seq 140 199); do [ -e /tmp/.X11-unix/X$n ] || { N=$n; break; }; done
Xvfb :$N -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
XPID=$!
for i in $(seq 50); do [ -e /tmp/.X11-unix/X$N ] && break; sleep 0.05; done
export DISPLAY=:$N ROBOTMCP_PLATYNUI_ISOLATED_DISPLAY=:$N ROBOTMCP_PLATYNUI_ISOLATED_XPID=$XPID XDG_SESSION_TYPE=x11
unset WAYLAND_DISPLAY
exec "$@"
