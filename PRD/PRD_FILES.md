# FILE MAP — Repository

backend/
├── main.py → B1 FastAPI + JOB_QUEUES
├── database.py → B2 SQLite init + DDL
├── schemas.py → Pydantic models
├── models.py → Row → dict converters
├── routers/
│   ├── jobs.py → M1
│   ├── settings.py → M6
│   └── artifacts.py → M7
├── worker/
│   ├── runner.py → B3 Worker Loop
│   ├── module_scraper.py → M2
│   ├── module_dom_mutator.py → M3
│   ├── module_ai_rewriter.py → M4
│   ├── module_media.py → M5
│   └── module_packer.py → M7
└── ws/
    └── log_broadcaster.py → WS

frontend/
app/
components/
tailwind.config.ts

migrations/
001_init.sql

Dockerfile
docker-compose.yml
entrypoint.sh
.env.example