#!/usr/bin/env python3
"""
Embedding client — talks to the warm daemon, auto-starting it if needed.

Import and call embed(texts). If the daemon isn't running, this launches it
(detached) and waits for it to come up, then sends the request. Everything is
best-effort: if embedding can't be produced, embed() returns None and callers
fall back to keyword search rather than failing.
"""

import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = os.path.join(HERE, "embd.sock")
DAEMON = os.path.join(HERE, "daemon.py")
LOG = os.path.join(HERE, "daemon.log")


def _send(obj, timeout=30.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    return json.loads(buf.decode("utf-8"))


def _alive():
    try:
        return _send({"ping": True}, timeout=2.0).get("pong") is True
    except Exception:
        return False


def ensure_running(wait=40.0):
    """Return True if the daemon is answering, starting it if necessary."""
    if _alive():
        return True
    if os.path.exists(SOCK):
        try:
            os.unlink(SOCK)  # stale socket from a dead daemon
        except OSError:
            pass
    with open(LOG, "ab") as log:
        subprocess.Popen(
            [sys.executable, DAEMON],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach: outlives this process
        )
    deadline = time.time() + wait
    while time.time() < deadline:
        if _alive():
            return True
        time.sleep(0.3)
    return False


def embed(texts, input_type="passage"):
    """Embed a list of strings. input_type is 'passage' (stored memories) or
    'query' (search prompts). Returns list[list[float]] or None on failure."""
    if not texts:
        return []
    if not ensure_running():
        return None
    try:
        return _send({"texts": list(texts), "input_type": input_type}).get("embeddings")
    except Exception:
        return None


if __name__ == "__main__":
    # CLI: `client.py warm`  -> ensure daemon is up (used by the SessionStart hook)
    ok = ensure_running()
    print("embedder daemon ready" if ok else "embedder daemon unavailable")
    sys.exit(0 if ok else 1)
