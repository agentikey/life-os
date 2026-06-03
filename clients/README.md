# Clients

Each client you manage work for gets its own subfolder here, mirroring the top-level LifeOS structure. The key difference: a client has their own `brand_context/` that **overrides** yours — their workstations read from their brand, not yours.

A client folder looks like:

```
clients/<name>/
├── CLAUDE.md          ← Client-level rules (layer on top of root rules)
├── MEMORY.md          ← Pointer to this client's memory DB
├── memory/lifeos.db   ← Client's OWN memory store (isolated from yours)
├── brand_context/     ← Client's brand (voice-profile.md, positioning-icp.md, visual-identity.md)
├── workstations/      ← Client's workstations
└── projects/          ← Client's output
```

Each client gets a **separate** `memory/lifeos.db`, driven by the shared `memory/mem.py` via `--db`. Because it's a different file, one client's memory can never leak into another's or into your personal root DB.

To add one, ask LifeOS to "set up a new client" — it follows the **Setting up a new client** procedure in the root [`CLAUDE.md`](../CLAUDE.md).

Global rules from the root `CLAUDE.md` always apply. The client layer adds context; it doesn't change how LifeOS behaves. Never reference your personal brand files or another client's files within a client session.
