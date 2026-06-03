# CLAUDE.md

Global rules for working in LifeOS. These apply everywhere. Workstation and client `CLAUDE.md` files layer on top — they add context, they don't replace these rules.

## How We Work Together

- **Tone:** Conversational and clear. Matter of fact, not a novel.
- **Length:** 300 words max unless I tell you otherwise. Lists get bullet points. Everything else gets written as normal paragraphs.
- **Recommendations:** Give me your best single recommendation. Only offer alternatives if I ask for them.
- **Uncertainty:** Flag what you don't know. Guessing isn't helpful.
- **Voice:** Any time you're producing content that goes out under my name, read `voice-profile.md` in the nearest `brand_context/` first.
- **Plan before building:** On complex tasks, ask your questions upfront before you start building. If unclear on the full picture, plan first, then execute.
- **Directory awareness:** Always know which directory you're working in. Your current location determines which `brand_context/` you read, which `MEMORY.md` you update, and which `projects/` folder you save output to. Inside a client folder, you're in that client's world. At the root, you're in mine. Get this wrong and context bleeds between clients, or output lands in the wrong place. When in doubt, check your working directory before you start.

## Memory System

Memory is stored in a **SQLite database** (`memory/lifeos.db`) with both keyword (FTS5) and **semantic (vector)** search, accessed only through the helper `memory/mem` (a wrapper that runs under the venv — plain `python3 memory/mem.py` silently loses the vector engine). `MEMORY.md` is the cheat-sheet with exact commands. The point: load only the few memories a task needs — including ones that share no keywords with the wording — instead of reading a whole growing file.

Mostly this is **automatic** via hooks (see `.claude/settings.json`): the session-start hook loads the working set and warms the embedder; the per-prompt hook runs hybrid recall and injects confident matches. The commands below are for writing memory and for manual lookups.

- **Session start:** the hook runs `memory/mem load`. Let it shape your responses, but don't mention you've read it. Pull more on demand with `recall`/`semantic`/`search`/`get`.
- When I tell you to **"remember this,"** classify it and `add` it straight away (it auto-embeds), then tell me it's done and give the new id.
- When I say **"add this to active projects,"** `add` it with `--type project`.
- When I say **"archive this,"** run `memory/mem archive <id>` and record the outcome via `update`.
- **Never hand-edit `lifeos.db`.** All writes go through `memory/mem` (parameterized — quotes/apostrophes safe). Run `memory/mem export` after significant changes to refresh the human-readable backup.
- **Agentic recall — reformulate before retrieving.** For a non-trivial request that may lean on past memory, don't rely only on the auto-injected hook (one phrasing, fired blind). Reformulate the intent into 2–3 alternative phrasings — expand concepts, add likely domain terms/synonyms, and include a declarative restatement of the *likely answer* (HyDE-style) — then run `memory/mem recall "<p1>" "<p2>" "<p3>"` and synthesize from the union. This rescues loose paraphrases, tight noise clusters, and multi-facet questions a single phrasing misses.
- **Scope every call.** Default scope `root` (me); use `--scope ws:content|ws:finance|ws:ops` for workstations. Client memory lives in the client's **own** DB (`memory/mem --db clients/<name>/memory/lifeos.db ...`) — never store client facts in the root DB.
- If the venv/embedder is unavailable, search degrades to keyword-only; if `python3` is gone entirely, read `memory/exports/memory.md`.

### Which store does new information belong in?

Not everything goes in the same place. Quick test:

- If it tells you **how to behave** (words like "always," "never," "do X before Y") → add it here to `CLAUDE.md` under the relevant section.
- If it's a **fact about my world that might change** (people, project updates, decisions, things I've asked you to track) → add it to the **memory DB** via `mem.py add`.
- Could it go either way? Tell me where you'd put it and I'll confirm.

## Brand Context

Brand context is how LifeOS knows my business — my voice, my audience, my visual identity. These files live in the `brand_context/` folder at the root of the setup. Pull them in only when relevant.

| Resource | Read when... |
|----------|--------------|
| `voice-profile.md` | Writing any content on my behalf — emails, posts, scripts, anything with my name on it |
| `positioning-icp.md` | Creating content, messaging, or offers aimed at my audience |
| `visual-identity.md` | Building anything visual — slides, documents, landing pages, or any asset that needs to look on-brand |

```
root/
├── CLAUDE.md
├── MEMORY.md
│
└── brand_context/
    ├── voice-profile.md       ← How you sound
    ├── positioning-icp.md     ← Who you're talking to, what you stand for
    └── visual-identity.md     ← How things look (colours, fonts, visual style)
```

Everything downstream reads from this folder. When LifeOS writes content, it checks `voice-profile.md`. When it builds a slide deck, it checks `visual-identity.md`. One source of truth for your brand, used everywhere.

## Workstations

A workstation is a permanent area of the business that has its own rules, its own contacts, and its own way of working. Content. Finance. Ops. Each gets its own folder because LifeOS needs specific context and memory to perform well in each. Each workstation inherits the overall `brand_context/`.

A workstation is **not** a project. "Launch the new website" is a project. "Content" is the workstation that project lives inside.

```
root/
├── CLAUDE.md                  ← Global rules. Apply everywhere.
├── MEMORY.md
├── brand_context/             ← Your brand. Shared across all workstations.
│
└── workstations/
    ├── content/
    │   ├── CLAUDE.md          ← Inherits global rules + your brand_context
    │   ├── MEMORY.md          ← Content-specific contacts and decisions
    │   └── resources/         ← Reference files for this workstation
    ├── finance/
    │   ├── CLAUDE.md
    │   ├── MEMORY.md
    │   └── resources/
    └── ops/
        ├── CLAUDE.md
        ├── MEMORY.md
        └── resources/
```

Each workstation's `CLAUDE.md` layers on top of the global rules — it doesn't replace them. Tone, preferences, and the memory system still apply. The workstation just adds its own workflow, editorial rules, and resource triggers.

### Routing Map

LifeOS uses this table to decide which workstation to load. Every time a new workstation is set up, add it here.

| Workstation | Route here when I... |
|-------------|----------------------|
| Content | ...am writing, repurposing, or planning any content (scripts, posts, newsletters) |
| Finance | ...am working on budgets, invoices, spending, or forecasting |
| Ops | ...am dealing with internal processes, SOPs, hiring, or team workflows |

Client delivery is handled separately — see **Clients** below. Client work routes into `clients/<name>/`, not a standalone workstation here.

### Setting up a new workstation

When I ask for a new workstation, create a subfolder under `workstations/` using the workstation name. Inside it, add three things:

**1. `CLAUDE.md`** — four sections, in this order:
- **Identity** — Short paragraph. What this workstation handles, what belongs here, what doesn't.
- **Resources** — "Resource" / "Load when..." table. Leave it empty to start.
- **Workflow** — Numbered steps for the core task. Keep it basic. We'll tighten it up over time.
- **Editorial Rules** — First line is always: "Follow the voice profile in the nearest parent brand_context folder (voice-profile.md)." Workstations at the root read from `root/brand_context/`. Workstations inside a client read from `clients/{client}/brand_context/`.

**2. `MEMORY.md`** — a short pointer (not a content store). It states that this workstation's memory lives in the LifeOS DB under scope `ws:<name>`, and shows the `mem.py list/search/add --scope ws:<name>` commands. Memory itself goes in the DB, not this file.

**3. `resources/`** — Empty folder. Reference files for this domain go here.

Once it's built, add a row to the Routing Map above so LifeOS picks it up automatically.

## Projects (Output)

Projects are where all output goes. Nothing gets saved inside a workstation folder — workstations hold rules and context, projects hold the actual work.

For my own business, output is organised by workstation name, then by date and slug. For client work, projects live inside the client's own folder (see Clients below).

```
projects/
├── content/
│   ├── 2026-05-18_weekly-newsletter/
│   └── 2026-05-20_youtube-script/
├── finance/
│   └── 2026-05-15_q2-forecast/
└── ops/
    └── 2026-05-12_onboarding-sop/
```

**Naming convention:** `YYYY-MM-DD_slug` inside the workstation folder. The slug should be short and descriptive. Create the folder when you start a new piece of work.

## Clients

If I manage work for multiple clients, each client gets their own space inside a `clients/` folder. The key difference: a client has their own `brand_context/` that **overrides** mine. Their workstations read from their brand, not mine.

A client folder mirrors the top-level structure — its own `brand_context/`, its own memory, its own workstations. Global rules from this root `CLAUDE.md` still apply; the client layer adds context, it doesn't override how LifeOS behaves.

```
root/
├── CLAUDE.md                          ← Global rules. Apply everywhere.
├── MEMORY.md
├── brand_context/                     ← YOUR brand (default)
├── workstations/                      ← Your own business workstations
├── projects/                          ← Your own output
│
└── clients/
    └── acme/
        ├── CLAUDE.md                  ← Client-level rules (layers on top of global)
        ├── MEMORY.md                  ← ACME-specific contacts and decisions
        ├── brand_context/             ← ACME's brand (overrides yours)
        │   ├── voice-profile.md
        │   ├── positioning-icp.md
        │   └── visual-identity.md
        ├── workstations/
        │   ├── content/
        │   │   ├── CLAUDE.md          ← Inherits global rules + ACME's brand_context
        │   │   ├── MEMORY.md
        │   │   └── resources/
        │   └── reporting/
        │       ├── CLAUDE.md
        │       ├── MEMORY.md
        │       └── resources/
        └── projects/                  ← ACME's output lives here
            ├── content/
            │   └── 2026-05-18_blog-post/
            └── reporting/
                └── 2026-05-16_monthly-report/
```

### Context loading convention

When LifeOS is operating inside a client workstation, it loads context in this order:

1. Read `clients/{client}/MEMORY.md` — client-level contacts, decisions, and project history.
2. Read the active workstation's `MEMORY.md` — workstation-specific context.
3. Apply the active workstation's `CLAUDE.md` rules — layered on top of both global and client rules.

Brand context always comes from the client's own `brand_context/` folder, not the top-level one.

### The inheritance rule

- Workstations inside `workstations/` load the top-level `brand_context/`. That's your brand. Output goes to `projects/`.
- Workstations inside `clients/acme/workstations/` load `clients/acme/brand_context/` instead. That's their brand. Output goes to `clients/acme/projects/`.
- Global rules from this root `CLAUDE.md` apply everywhere. Workstation `CLAUDE.md` files layer on top, they don't replace.

### Setting up a new client

When I ask for a new client, create a subfolder inside `clients/` using the client name. Inside it, add:

- **`brand_context/`** — Same three files as the top-level (`voice-profile.md`, `positioning-icp.md`, `visual-identity.md`). Leave them blank to fill in.
- **`memory/`** — The client's **own** memory store. Initialise a fresh DB with `memory/mem --db clients/<name>/memory/lifeos.db init` (the shared root venv/embedder drives it — clients don't need their own). All of this client's memory uses this file, never the root DB, so contexts stay isolated.
- **`MEMORY.md`** — A short pointer: client memory lives in `clients/<name>/memory/lifeos.db`; show the `memory/mem --db clients/<name>/memory/lifeos.db ...` commands.
- **`CLAUDE.md`** — Client-level rules. Starts with: "Inherits all rules from the root CLAUDE.md. Add client-specific rules below." Use this for anything that applies across all of this client's workstations.
- **`workstations/`** — Empty folder. Add workstations inside it using the same setup process above.
- **`projects/`** — Empty folder. Output for this client's work goes here, organised by workstation and date.
