# Documentation (diagrams)

This folder mirrors the **product spec** at the repo root: `Claude_v1.1_fixed.txt` (single source of truth for meaning, routes, and DDL).

| File | Purpose |
|------|---------|
| [architecture.md](./architecture.md) | Stack, pipeline, request flow, worker boundaries — **Mermaid** (diff-friendly). |
| [database.md](./database.md) | ER diagram and table roles — **Mermaid** + notes aligned with §3.2 DDL. |
| [html/](./html/) | Same content as styled HTML fragments (e.g. embedded in Cursor Canvas). |

**Rule:** edit `Claude_v1.1_fixed.txt` first, then update the matching `docs/*` files so they stay in sync.
