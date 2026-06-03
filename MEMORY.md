# Memory — How It Works

Memory is stored in a **SQLite database** with both keyword (FTS5) and **semantic (vector)** search. This keeps the always-loaded footprint tiny: instead of reading my whole history, the system pulls only the few rows relevant to the task — including ones that share *no keywords* with your wording.

- **Store:** `memory/lifeos.db`  ·  **Helper:** `memory/mem` (runs under the venv)  ·  **Backup:** `memory/exports/memory.md`
- **Embedder:** a warm local daemon (`memory/embedder/`, fastembed `bge-small`, 384-dim) — auto-starts on demand, no manual management, no network.
- Always use `memory/mem` (not `python3 memory/mem.py` — that misses the vector engine). All writes are parameterized, so quotes/apostrophes are safe. Never hand-edit the DB.

## Automatic (via hooks in `.claude/settings.json`)
- **Session start** → `hooks/startup.py` injects the working set *and* warms the embedder in the background.
- **Every prompt** → `hooks/recall.py` runs **hybrid recall** (semantic + keyword) on your message and injects only confident matches. Irrelevant/trivial prompts inject nothing.

## Manual commands
```
memory/mem load                          # working set (active about + project)
memory/mem recall "<text>"               # hybrid: what the hook runs
memory/mem recall "<p1>" "<p2>" "<p3>"   # agentic rewrite: union of reformulations
memory/mem semantic "<concept>"          # pure vector / concept search
memory/mem search "<keywords>"           # pure keyword (FTS5)
memory/mem list --type contact           # browse one type
memory/mem get <id>                       # one full entry
```

## Writing memory
On "remember this," classify and insert (auto-embeds for semantic recall). Types: `about`, `project`, `contact`, `decision`, `note`.
```
memory/mem add --type decision --title "..." --body "..." --tags "..."
```
- "add this to active projects" → `add --type project ...`
- "archive this" → `memory/mem archive <id>`

## Scopes (context isolation)
- `root` (default) = me. `ws:content` / `ws:finance` / `ws:ops` = workstations (pass `--scope`).
- **Clients use their own DB file** (`memory/mem --db clients/<name>/memory/lifeos.db ...`) — client memory can never bleed into mine.

## Housekeeping
```
memory/mem backfill        # embed any rows missing a vector (e.g. after import)
memory/mem export          # refresh the human-readable backup
memory/mem stats           # counts by scope/type — spot bloat to consolidate
```
Notes: semantic recall is tunable (`--max-distance`, and the `VEC_*` constants in `mem.py`); a small embedding model gives noisy distances on short text, so very loose paraphrases can still be missed. If the venv/embedder is unavailable, search degrades gracefully to keyword-only.
