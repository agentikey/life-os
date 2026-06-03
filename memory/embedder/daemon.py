#!/usr/bin/env python3
"""
Embedding daemon — keeps the fastembed model warm so per-prompt recall is fast.

A fresh Python process loading an embedding model costs ~1s+. The UserPromptSubmit
hook runs in a fresh process every prompt, so instead of loading the model each
time, we load it ONCE here and answer embedding requests over a local Unix socket.

It is local-only (a filesystem socket, no TCP port, no network), single-purpose,
and auto-started on demand by client.py — you never start it by hand.

Protocol (newline-delimited JSON over AF_UNIX stream):
  ->  {"texts": ["...", "..."], "input_type": "query"|"passage"}   or  {"ping": true}
  <-  {"embeddings": [[...], [...]]}                               or  {"pong": true}

input_type matters for asymmetric retrieval models: queries get an instruction
prefix, stored memories ("passage") do not. Stored memories embed as passages;
search prompts embed as queries.

Run:  <venv>/bin/python daemon.py   (client.py does this for you)
"""

import json
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = os.path.join(HERE, "embd.sock")

# --- Active model -------------------------------------------------------------
MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384-dim, ONNX, no torch
QUERY_INSTRUCTION = ""                  # bge-small: no query prefix
#
# --- PENDING UPGRADE (paused mid-download) ------------------------------------
# To finish the move to the stronger 1024-dim model, when the connection allows:
#   1. Set MODEL_NAME   = "mixedbread-ai/mxbai-embed-large-v1"
#      Set QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
#      Set EMB_DIM = 1024 in ../mem.py
#   2. Pre-download (resumes from the ~26% already cached):
#        .venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('mixedbread-ai/mxbai-embed-large-v1')"
#   3. Rebuild the vector index at the new dimension, then re-embed:
#        kill the daemon, then:  memory/mem ... (drop memories_vec) ; memory/mem backfill --all
# The asymmetric query/passage plumbing below already supports it — only these
# constants and the one-time re-embed are needed.


def main():
    from fastembed import TextEmbedding

    model = TextEmbedding(MODEL_NAME)

    def embed(texts, input_type="passage"):
        texts = list(texts)
        if input_type == "query":
            texts = [QUERY_INSTRUCTION + t for t in texts]
        return [v.tolist() for v in model.embed(texts)]

    # warm the model so the first real request is instant
    embed(["warmup"])

    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK)
    srv.listen(16)
    sys.stderr.write(f"[embedder] ready on {SOCK} ({MODEL_NAME})\n")
    sys.stderr.flush()

    while True:
        conn, _ = srv.accept()
        try:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
            if not buf:
                continue
            req = json.loads(buf.decode("utf-8"))
            if req.get("ping"):
                resp = {"pong": True, "model": MODEL_NAME}
            else:
                resp = {"embeddings": embed(req.get("texts", []),
                                            req.get("input_type", "passage"))}
            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception as e:  # never let one bad request kill the daemon
            try:
                conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
            except Exception:
                pass
        finally:
            conn.close()


if __name__ == "__main__":
    main()
