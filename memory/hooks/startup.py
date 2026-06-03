#!/usr/bin/env python3
"""
SessionStart hook — load the working set AND warm the embedder.

Runs once when a session starts:
  1. Prints the small always-relevant slice (active about + project) so it's in
     context from the first turn, deterministically.
  2. Kicks off the embedding daemon in the BACKGROUND so the first semantic
     recall is instant — without delaying session start while the model loads.
Always exits 0 so it can never block a session.

Launched under the venv python (see .claude/settings.json), so sys.executable
already has sqlite-vec + fastembed available.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MEM = os.path.join(HERE, os.pardir, "mem.py")
WARM = os.path.join(HERE, os.pardir, "embedder", "client.py")


def main():
    # 2. warm the embedder daemon in the background (fire-and-forget)
    try:
        subprocess.Popen(
            [sys.executable, WARM],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception:
        pass
    # 1. load the working set into context
    try:
        out = subprocess.run(
            [sys.executable, MEM, "load"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return
    if out and "(no active" not in out:
        print("## LifeOS working memory (auto-loaded at session start)")
        print(out)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
