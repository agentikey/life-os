#!/usr/bin/env python3
"""
UserPromptSubmit hook — auto-recall relevant LifeOS memory.

Claude Code runs this before every user prompt and pipes a JSON event on stdin.
We pull the prompt text, search the memory DB for relevant past entries, and
print them to stdout. Claude Code injects whatever we print into the model's
context for that turn — so relevant memory surfaces automatically, without the
model having to remember to search.

Design choices that keep this from bloating context:
  - Only the top few keyword matches are returned (mem.py recall --limit).
  - If the prompt has too few meaningful terms, or nothing matches, we print
    nothing at all.
  - We always exit 0; a memory hook must never block the user's prompt.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MEM = os.path.join(HERE, os.pardir, "mem.py")


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return  # no/invalid event — do nothing, let the prompt through
    prompt = (event.get("prompt") or "").strip()
    if not prompt:
        return
    try:
        out = subprocess.run(
            [sys.executable, MEM, "recall", prompt, "--limit", "3"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return
    if out:
        print("## Relevant LifeOS memory (auto-recalled by keyword)")
        print(out)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)  # never block the prompt, whatever happened
