"""Portable stdin feeder (no FIFO): tail an append-only inbox file into stdout (the REPL's stdin).
Clients append cells to the inbox under a lock. Exits (-> REPL sees EOF -> graceful exit) when the
inbox file is deleted or the downstream pipe closes."""
import os, sys, time
path = sys.argv[1]
open(path, "ab").close()
out = sys.stdout.buffer
with open(path, "rb") as fh:
    fh.seek(0, os.SEEK_END)
    while True:
        chunk = fh.read()
        if chunk:
            try:
                out.write(chunk); out.flush()
            except BrokenPipeError:
                break
        else:
            if not os.path.exists(path):
                break
            time.sleep(0.003)
