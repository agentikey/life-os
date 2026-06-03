# LifeOS

A context-and-memory operating system for running a business through [Claude Code](https://claude.com/claude-code).

LifeOS gives an AI assistant three things it normally lacks: a durable, searchable
**memory**; isolated **contexts** so different parts of the business don't bleed into
each other; and a consistent **brand voice** to work from. It's a folder structure plus
a local memory engine wired into Claude Code's hooks.

## What's inside

| Piece | What it does |
|-------|--------------|
| `CLAUDE.md` | Global operating rules, loaded every session |
| `memory/` | Local hybrid-recall memory engine (SQLite + FTS5 + semantic vectors) |
| `brand_context/` | Voice, positioning, and visual identity — the brand's source of truth |
| `workstations/` | Isolated working contexts (content, finance, ops), each with its own rules and memory scope |
| `projects/` | Where all output is saved, organized by workstation and date |
| `clients/` | Per-client mirror of the structure, each with its own isolated memory |

## The memory engine

The core of LifeOS is a local memory store that keeps the always-loaded context small
while still surfacing exactly what a task needs — including memories that share *no
keywords* with the prompt.

- **Storage:** SQLite (`memory/lifeos.db`), one row per memory.
- **Recall:** hybrid — keyword (FTS5) **and** semantic (vector) search via a warm,
  local embedding daemon (`fastembed`, `bge-small`, 384-dim). No network, no API keys.
- **Automatic:** Claude Code hooks load the working set at session start and inject
  relevant memories on every prompt — degrading gracefully to keyword-only if the
  embedder is unavailable.
- **Isolated:** scopes (`root`, `ws:*`) and per-client database files keep contexts
  from bleeding into each other.

All access goes through the `memory/mem` helper (parameterized, quote-safe). See
[`MEMORY.md`](MEMORY.md) for the full command reference.

## Setup

Requires Python 3 and Claude Code.

```bash
# 1. Create the memory engine's virtualenv and install dependencies
python3 -m venv memory/.venv
memory/.venv/bin/python -m pip install --upgrade pip
memory/.venv/bin/python -m pip install sqlite-vec fastembed

# 2. Initialize the memory store
memory/mem init

# 3. (Optional) seed it, then warm the embedder
memory/.venv/bin/python memory/embedder/client.py
```

The Claude Code hooks are configured in [`.claude/settings.json`](.claude/settings.json).
After cloning into a new location, point the hook commands at this project's paths.

## Using it

Once set up, just talk to Claude Code normally. A few phrases trigger the key behaviors:

- *"Remember this…"* → stores a memory (auto-classified and embedded)
- *"Add this to active projects"* → stores it as a project
- *"Archive this"* → marks a memory inactive

Relevant memory surfaces automatically — you don't have to ask for it.

## Conventions

- **Brand context** is the single source of truth for voice and identity; everything
  that writes on the business's behalf reads from it first.
- **Workstations** hold rules and context; **projects** hold output. Output is never
  saved inside a workstation folder.
- **Client work** lives entirely under `clients/<name>/`, with its own brand context and
  its own memory database — never mixed with personal or other-client context.

See [`CLAUDE.md`](CLAUDE.md) for the complete operating rules.
