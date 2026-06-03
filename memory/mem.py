#!/usr/bin/env python3
"""
LifeOS memory store — a thin, safe CLI over a SQLite database.

Why this exists: a flat MEMORY.md grows until it no longer fits in context.
This stores each memory as a row and lets Claude pull back ONLY the rows that
matter for the task at hand, instead of loading whole files.

All writes go through parameterized queries here (never raw sqlite3 string
interpolation) so apostrophes and quotes in memory text can't corrupt the DB.

Usage (run from anywhere; --db defaults to the lifeos.db next to this script):

  python3 mem.py init
  python3 mem.py load                          # session-start working set (scope=root)
  python3 mem.py search "invoice forecast"     # keyword (FTS5) recall
  python3 mem.py add --type decision --title "Stripe over GoCardless" \\
                     --body "Simpler API, better docs." --tags billing
  python3 mem.py list --type project
  python3 mem.py get 7
  python3 mem.py update 7 --status archived
  python3 mem.py archive 7
  python3 mem.py export                         # human-readable markdown dump
  python3 mem.py stats

Scopes keep contexts separate: 'root' (you), 'ws:content' / 'ws:finance' /
'ws:ops' (workstations). Clients use their OWN database file (--db), so client
memory can never bleed into yours.
"""

import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "lifeos.db")

# Optional vector search. If sqlite-vec or the embedder aren't available, the
# store still works fully on keyword (FTS5) search — vector is purely additive.
sys.path.insert(0, os.path.join(HERE, "embedder"))
try:
    import sqlite_vec
    import client as embedder
    VEC = True
    EMB_DIM = 384  # BAAI/bge-small-en-v1.5 (see daemon.py for the pending mxbai upgrade)
except Exception:
    VEC = False
    EMB_DIM = 0

TYPES = ("about", "project", "contact", "decision", "note")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id      INTEGER PRIMARY KEY,
  scope   TEXT NOT NULL,                       -- 'root' | 'ws:content' | ...
  type    TEXT NOT NULL,                        -- about | project | contact | decision | note
  title   TEXT NOT NULL,
  body    TEXT NOT NULL,
  status  TEXT NOT NULL DEFAULT 'active',       -- active | archived
  tags    TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT (datetime('now')),
  updated TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(scope, status, type);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
  USING fts5(title, body, content='memories', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, body)
    VALUES('delete', old.id, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, body)
    VALUES('delete', old.id, old.title, old.body);
  INSERT INTO memories_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
"""


def connect(db_path):
    db_path = os.path.abspath(os.path.expanduser(db_path))
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if VEC:
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec "
                f"USING vec0(embedding float[{EMB_DIM}])"
            )
        except Exception:
            pass  # fall back to keyword-only
    return conn


def store_vec(conn, mem_id, title, body):
    """Embed a memory's text and upsert its vector. Best-effort."""
    if not VEC:
        return False
    vecs = embedder.embed([f"{title}\n{body}"])
    if not vecs:
        return False
    blob = sqlite_vec.serialize_float32(vecs[0])
    conn.execute("DELETE FROM memories_vec WHERE rowid=?", (mem_id,))
    conn.execute("INSERT INTO memories_vec(rowid, embedding) VALUES(?,?)", (mem_id, blob))
    conn.commit()
    return True


def fmt(row, full=False):
    date = (row["updated"] or "")[:10]
    tags = f"  #{row['tags'].replace(',', ' #')}" if row["tags"] else ""
    flag = "" if row["status"] == "active" else f" [{row['status']}]"
    head = f"[{row['id']}] ({row['type']}{flag}) {row['title']}  ·{date}{tags}"
    if not full:
        return head
    return head + "\n    " + (row["body"] or "").replace("\n", "\n    ")


def cmd_init(conn, args):
    conn.executescript(SCHEMA)
    conn.commit()
    print(f"Initialized memory DB at {args.db}")


def cmd_add(conn, args):
    if args.type not in TYPES:
        sys.exit(f"--type must be one of {TYPES}")
    cur = conn.execute(
        "INSERT INTO memories(scope,type,title,body,tags) VALUES(?,?,?,?,?)",
        (args.scope, args.type, args.title, args.body, args.tags or ""),
    )
    conn.commit()
    vec = store_vec(conn, cur.lastrowid, args.title, args.body)
    note = "" if vec else "  (no vector — keyword-only)"
    print(f"Added memory #{cur.lastrowid} to scope '{args.scope}'.{note}")


def cmd_load(conn, args):
    """Session-start working set: the small, always-relevant slice."""
    rows = conn.execute(
        """SELECT * FROM memories
           WHERE scope=? AND status='active' AND type IN ('about','project')
           ORDER BY type, updated DESC""",
        (args.scope,),
    ).fetchall()
    if not rows:
        print(f"(no active about/project memories in scope '{args.scope}')")
        return
    for r in rows:
        print(fmt(r, full=True))


def cmd_search(conn, args):
    q = args.query.strip()
    try:
        rows = conn.execute(
            """SELECT m.* FROM memories_fts f JOIN memories m ON m.id=f.rowid
               WHERE memories_fts MATCH ? AND m.scope=? AND m.status='active'
               ORDER BY rank LIMIT ?""",
            (q, args.scope, args.limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # FTS syntax fallback: plain substring match
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT * FROM memories
               WHERE scope=? AND status='active' AND (title LIKE ? OR body LIKE ?)
               ORDER BY updated DESC LIMIT ?""",
            (args.scope, like, like, args.limit),
        ).fetchall()
    if not rows:
        print(f"(no matches for '{q}' in scope '{args.scope}')")
        return
    for r in rows:
        print(fmt(r, full=True))


STOPWORDS = {
    "the", "and", "for", "you", "your", "are", "was", "what", "when", "where",
    "who", "how", "why", "did", "does", "can", "could", "would", "should", "this",
    "that", "with", "from", "have", "has", "had", "about", "into", "out", "our",
    "his", "her", "she", "him", "they", "them", "their", "but", "not", "all",
    "any", "get", "got", "let", "him", "she", "see", "say", "tell", "want",
}


def tokenize(text):
    """Pull meaningful search terms out of a free-text prompt."""
    words, seen = [], set()
    for raw in text.lower().replace("'", "").split():
        w = "".join(c for c in raw if c.isalnum())
        if len(w) >= 3 and w not in STOPWORDS and w not in seen:
            seen.add(w)
            words.append(w)
    return words


# Semantic-recall tuning. Small embedding models give noisy, overlapping
# distances on short text, so a flat cutoff can't separate a real paraphrase
# match from generic noise. Instead we trust a hit only when it's a CONFIDENT
# LEADER: closest within CEILING, and either very close (STRONG) or clearly
# ahead of the runner-up (GAP). Near-ties within MARGIN ride along. All tunable.
VEC_GAP = 0.05      # runner-up must be this much farther to trust a lone leader
VEC_STRONG = 0.38   # ...unless the leader is at least this close (trust regardless)
VEC_MARGIN = 0.05   # include near-ties within this distance of the leader


def vector_hits(conn, query, k, max_distance):
    """Semantic search by cosine distance. Returns an ascending list of
    (memory_id, distance) for the k nearest within max_distance. Empty if no
    vectors / embedder down."""
    if not VEC:
        return []
    vecs = embedder.embed([query], input_type="query")
    if not vecs:
        return []
    try:
        blob = sqlite_vec.serialize_float32(vecs[0])
        rows = conn.execute(
            "SELECT v.rowid AS rid, vec_distance_cosine(v.embedding, ?) AS dist "
            "FROM memories_vec v ORDER BY dist LIMIT ?",
            (blob, k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r["rid"], r["dist"]) for r in rows if r["dist"] <= max_distance]


def confident_vectors(hits):
    """Keep semantic hits only when there's a clear winner — filters out the
    flat 'everything is vaguely related' clusters that are really noise."""
    if not hits:
        return {}
    best = hits[0][1]
    if len(hits) > 1 and (hits[1][1] - best) < VEC_GAP and best > VEC_STRONG:
        return {}  # ambiguous cluster, no confidently-relevant memory
    return {mid: d for mid, d in hits if d <= best + VEC_MARGIN}


def keyword_hits(conn, query, min_terms):
    """FTS keyword match. Returns a set of memory ids. Empty if too few terms."""
    terms = tokenize(query)
    if len(terms) < min_terms:
        return set()
    try:
        rows = conn.execute(
            "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?",
            (" OR ".join(terms),),
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {r["rowid"] for r in rows}


def cmd_recall(conn, args):
    """Hybrid free-text recall for the UserPromptSubmit hook.

    Combines semantic (vector) and keyword (FTS) matches across all scopes,
    then prints only the top active hits. Vector recall catches paraphrases
    that share no words (apple-weight memory surfacing on a Newton query);
    keyword recall nails exact terms. Prints NOTHING on trivial/empty prompts
    so it never bloats context.
    """
    # Accepts ONE prompt (the hook) or SEVERAL reformulations (agentic query
    # rewriting). Each query is searched independently — vector + keyword — and a
    # memory keeps its BEST score across queries. So if one phrasing lands in a
    # noisy cluster, a better-worded reformulation can still surface the memory.
    queries = [q for q in args.query if len(tokenize(q)) >= args.min_terms]
    if not queries:
        return  # all trivial ("ok thanks") — skip entirely

    agg = {}  # memory_id -> best score across all queries
    for q in queries:
        vh = confident_vectors(vector_hits(conn, q, args.limit * 4, args.max_distance))
        kh = keyword_hits(conn, q, args.min_terms)
        for mid in set(vh) | kh:
            s = (1.0 - vh[mid] if mid in vh else 0.0) + (0.4 if mid in kh else 0.0)
            agg[mid] = max(agg.get(mid, 0.0), s)
    if not agg:
        return

    rows = conn.execute(
        f"SELECT * FROM memories WHERE id IN ({','.join('?' * len(agg))}) "
        f"AND status='active'",
        list(agg),
    ).fetchall()
    rows.sort(key=lambda r: agg.get(r["id"], 0), reverse=True)
    for r in rows[: args.limit]:
        print(fmt(r, full=True))


def cmd_semantic(conn, args):
    """Pure semantic (vector) search — for manual, precise concept lookup."""
    if not VEC:
        sys.exit("Vector search unavailable (sqlite-vec/embedder not installed).")
    vh = dict(vector_hits(conn, args.query, args.limit, args.max_distance))
    if not vh:
        print(f"(no semantic matches for '{args.query}')")
        return
    rows = conn.execute(
        f"SELECT * FROM memories WHERE id IN ({','.join('?' * len(vh))}) "
        f"AND status='active'",
        list(vh),
    ).fetchall()
    rows.sort(key=lambda r: vh.get(r["id"], 9.0))  # ascending distance
    for r in rows:
        print(fmt(r, full=True))


def cmd_backfill(conn, args):
    """Embed every memory that doesn't yet have a vector (e.g. rows added before
    vector search existed, or after a model change with --all)."""
    if not VEC:
        sys.exit("Vector search unavailable (sqlite-vec/embedder not installed).")
    if args.all:
        rows = conn.execute("SELECT id, title, body FROM memories").fetchall()
    else:
        rows = conn.execute(
            "SELECT m.id, m.title, m.body FROM memories m "
            "LEFT JOIN memories_vec v ON v.rowid=m.id WHERE v.rowid IS NULL"
        ).fetchall()
    if not rows:
        print("Nothing to backfill — all memories already have vectors.")
        return
    texts = [f"{r['title']}\n{r['body']}" for r in rows]
    vecs = embedder.embed(texts)
    if not vecs:
        sys.exit("Embedder unavailable — could not backfill.")
    for r, v in zip(rows, vecs):
        blob = sqlite_vec.serialize_float32(v)
        conn.execute("DELETE FROM memories_vec WHERE rowid=?", (r["id"],))
        conn.execute("INSERT INTO memories_vec(rowid, embedding) VALUES(?,?)", (r["id"], blob))
    conn.commit()
    print(f"Backfilled vectors for {len(rows)} memories.")


def cmd_list(conn, args):
    sql = "SELECT * FROM memories WHERE scope=?"
    params = [args.scope]
    if args.type:
        sql += " AND type=?"
        params.append(args.type)
    if not args.all:
        sql += " AND status='active'"
    sql += " ORDER BY type, updated DESC"
    rows = conn.execute(sql, params).fetchall()
    for r in rows:
        print(fmt(r, full=args.full))
    if not rows:
        print("(none)")


def cmd_get(conn, args):
    r = conn.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
    if not r:
        sys.exit(f"No memory #{args.id}")
    print(fmt(r, full=True))


def cmd_update(conn, args):
    fields, params = [], []
    for col in ("title", "body", "tags", "status", "scope", "type"):
        val = getattr(args, col)
        if val is not None:
            fields.append(f"{col}=?")
            params.append(val)
    if not fields:
        sys.exit("Nothing to update. Pass --title/--body/--tags/--status/etc.")
    fields.append("updated=datetime('now')")
    params.append(args.id)
    cur = conn.execute(f"UPDATE memories SET {', '.join(fields)} WHERE id=?", params)
    conn.commit()
    if cur.rowcount == 0:
        sys.exit(f"No memory #{args.id}")
    if args.title is not None or args.body is not None:
        r = conn.execute("SELECT title, body FROM memories WHERE id=?", (args.id,)).fetchone()
        store_vec(conn, args.id, r["title"], r["body"])
    print(f"Updated memory #{args.id}.")


def cmd_archive(conn, args):
    cur = conn.execute(
        "UPDATE memories SET status='archived', updated=datetime('now') WHERE id=?",
        (args.id,),
    )
    conn.commit()
    if cur.rowcount == 0:
        sys.exit(f"No memory #{args.id}")
    print(f"Archived memory #{args.id}.")


def cmd_export(conn, args):
    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.db)), "exports", "memory.md"
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    rows = conn.execute(
        "SELECT * FROM memories WHERE (?='' OR scope=?) ORDER BY scope, type, updated DESC",
        (args.scope or "", args.scope or ""),
    ).fetchall()
    lines = ["# LifeOS Memory — export", ""]
    cur_scope = cur_type = None
    for r in rows:
        if r["scope"] != cur_scope:
            cur_scope, cur_type = r["scope"], None
            lines += ["", f"## scope: {cur_scope}"]
        if r["type"] != cur_type:
            cur_type = r["type"]
            lines += ["", f"### {cur_type}"]
        flag = "" if r["status"] == "active" else f" _({r['status']})_"
        tag = f"  `{r['tags']}`" if r["tags"] else ""
        lines.append(f"- **{r['title']}**{flag} — {r['body']}{tag}  ·{r['updated'][:10]}")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Exported {len(rows)} memories to {out}")


def cmd_stats(conn, args):
    rows = conn.execute(
        """SELECT scope, type, status, COUNT(*) n FROM memories
           GROUP BY scope, type, status ORDER BY scope, type""").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    print(f"Total memories: {total}")
    for r in rows:
        print(f"  {r['scope']:<14} {r['type']:<9} {r['status']:<9} {r['n']}")


def build_parser():
    p = argparse.ArgumentParser(description="LifeOS SQLite memory store")
    p.add_argument("--db", default=DEFAULT_DB, help="path to the memory DB file")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    a = sub.add_parser("add")
    a.add_argument("--scope", default="root")
    a.add_argument("--type", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--body", required=True)
    a.add_argument("--tags", default="")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("load")
    l.add_argument("--scope", default="root")
    l.set_defaults(func=cmd_load)

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--scope", default="root")
    s.add_argument("--limit", type=int, default=5)
    s.set_defaults(func=cmd_search)

    rc = sub.add_parser("recall")
    rc.add_argument("query", nargs="+", help="one prompt, or several reformulations to union")
    rc.add_argument("--limit", type=int, default=3)
    rc.add_argument("--min-terms", type=int, default=2, dest="min_terms")
    rc.add_argument("--max-distance", type=float, default=0.46, dest="max_distance",
                    help="cosine-distance ceiling for semantic hits (lower = stricter)")
    rc.set_defaults(func=cmd_recall)

    se = sub.add_parser("semantic")
    se.add_argument("query")
    se.add_argument("--limit", type=int, default=5)
    se.add_argument("--max-distance", type=float, default=0.60, dest="max_distance")
    se.set_defaults(func=cmd_semantic)

    bf = sub.add_parser("backfill")
    bf.add_argument("--all", action="store_true", help="re-embed every memory")
    bf.set_defaults(func=cmd_backfill)

    li = sub.add_parser("list")
    li.add_argument("--scope", default="root")
    li.add_argument("--type", default=None)
    li.add_argument("--all", action="store_true", help="include archived")
    li.add_argument("--full", action="store_true", help="show bodies")
    li.set_defaults(func=cmd_list)

    g = sub.add_parser("get")
    g.add_argument("id", type=int)
    g.set_defaults(func=cmd_get)

    u = sub.add_parser("update")
    u.add_argument("id", type=int)
    for col in ("title", "body", "tags", "status", "scope", "type"):
        u.add_argument(f"--{col}", default=None)
    u.set_defaults(func=cmd_update)

    ar = sub.add_parser("archive")
    ar.add_argument("id", type=int)
    ar.set_defaults(func=cmd_archive)

    e = sub.add_parser("export")
    e.add_argument("--scope", default=None, help="limit to one scope")
    e.add_argument("--out", default=None)
    e.set_defaults(func=cmd_export)

    sub.add_parser("stats").set_defaults(func=cmd_stats)
    return p


def main():
    args = build_parser().parse_args()
    conn = connect(args.db)
    args.func(conn, args)
    conn.close()


if __name__ == "__main__":
    main()
