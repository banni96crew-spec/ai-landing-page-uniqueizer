```markdown
# PRD MAP — Document Map "PRD.md"

Source of Truth: PRD.md
Section Priority in Conflict: §3 > §4 > §2

# 0 MAIN RULE

Pipeline ≠ API layer ≠ Infrastructure.

Pipeline = M2–M7.  
M1 (Jobs), M6 (Settings), WebSocket are infrastructure services, not pipeline steps.

---

# 1 GLOBAL DEPENDENCY GRAPH

 ┌────────────────────┐
 │ Infrastructure     │
 │ Docker / Env / DB  │
 └─────────┬──────────┘
           │
 ┌─────────▼──────────┐
 │ Core Backend       │
 │ FastAPI + Worker   │
 └──────┬─────────────┘
        │
 ┌──────┼─────────────────────┐
 │      │                     │
 ▼      ▼                     ▼
M1 Jobs API   M6 Settings API   WebSocket Logs
 │      │                     │
 └──────┬────────┴──────────┬──┘
        │                   │
        ▼                   ▼
    SQLite DB         JOB_QUEUES dict
        │
        ▼
    Worker Loop
        │
        ▼
 ┌─────────────────────────────────────────────┐
 │                 PIPELINE                    │
 │                                             │
 │         M2 → M3 → M4 → M5 → M7             │
 │                                             │
 └─────────────────────────────────────────────┘

---

# 2 PIPELINE — SHORT CHAIN + I/O

M2 Scraper  
 INPUT: target_url (from jobs)  
 OUTPUT: /jobs/{id}/raw/  
         /jobs/{id}/cleaned/  

M3 DOM Mutator  
 INPUT: /jobs/{id}/cleaned/  
 OUTPUT: /jobs/{id}/mutated/  

M4 AI Rewriter  
 INPUT: /jobs/{id}/mutated/  
 OUTPUT: /jobs/{id}/rewritten/  
         (copy of mutated + AI text)  

M5 Media Uniqueizer  
 INPUT: /jobs/{id}/rewritten/assets/  
 OUTPUT: overwritten files (in-place)  

M7 Packer  
 INPUT: /jobs/{id}/rewritten/  
 OUTPUT: /volumes/artifacts/{id}.zip  
         INSERT artifacts  
         UPDATE jobs.status='done'  

Cleanup:  
 delete /jobs/{id}/ (all intermediate folders)  

---

# 3 IMPORTANT SEPARATION

## Infrastructure Layer (not a pipeline step):

- M1 Jobs API  
- M6 Settings API  
- WebSocket Log Broadcaster  
- Worker Loop  
- JOB_QUEUES  
- SQLite  
- Docker  

These modules do NOT belong to pipeline steps 1–5.  
They serve the pipeline.

---

# 4 GAP REGISTRY (WITH ID)

| GAP ID | Name | PRD Section | Status |
|---------|------|------------|--------|
| GAP-A | migrations/001_init.sql in Docker | §3.2 | Resolved |
| GAP-B | rewrite_asset_urls algorithm | §3.3 | Resolved |
| GAP-C | Per-job JOB_QUEUES | §3.1 WS | Resolved |
| GAP-D | Circular import fix (runner/main) | §7.6 | Resolved |
| GAP-E | rewrite_css_urls algorithm | §3.3 | Resolved |
| GAP-F | rewritten/ as final source | §2 | Resolved |
| GAP-G | Multi-page limitation | §8 | Known |
| GAP-H | JS_REPLACE_PATTERNS (6 items) | §3.3 | Resolved |
| GAP-I | Duplicate URL allowed | §3.1 | Resolved |
| GAP-J | Filename date from jobs.created_at | §4 | Resolved |
| GAP-K | Error state JobInputPanel | §5 | Resolved |
| GAP-L | VPS deploy via .env | §7 | Resolved |
| GAP-M | No resume after crash | §8 | Known |

---

# 5 MODULE MAP (LOGICAL)

M1 — Jobs API  
M2 — Scraper  
M3 — DOM Mutator  
M4 — AI Rewriter  
M5 — Media Uniqueizer  
M6 — Settings  
M7 — Artifact & Download  
WS — WebSocket Logs  
B1 — FastAPI App  
B2 — Database  
B3 — Worker Loop  
I1–I7 — Infrastructure  

---

# 6 WHERE TO LOOK FOR A TASK

Modify API → §3.1 + §4  
Modify DB → §3.2  
Modify pipeline → §3.3 + §4 M*  
Modify status logic → §2 + §3.2  
Modify WS → §3.1 WS + GAP-C  
Modify Docker → §7  

