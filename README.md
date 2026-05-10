# Progressive Harmonization ETL — Web App

A small web app for turning heterogeneous health/behavioural data into canonical events via an LLM-generated YAML adapter config.

## Flow

1. **Upload or paste** a JSON data sample in the browser.
2. **Describe** what the data is (subject field, record shape, quirks).
3. **Generate** — the backend calls an LLM to draft a YAML adapter config.
4. **Edit** the YAML in the in-browser Monaco editor if needed.
5. **Run** the config through the engine; inspect and download the resulting canonical events.

No data is persisted server-side. Each request is stateless.

## Layout

```
impl/
  backend/          FastAPI single-service ETL
    api/            HTTP handlers, Pydantic models, LLM client, config CRUD
    pipeline/       five in-process stages (connector → adapter → cleaner → validator → qualifier)
    domain/         canonical event model, quality rules, value-level utils
    configs/        adapter YAML configs (also the LLM few-shot corpus)
    pyproject.toml
  frontend/         Next.js (client-only, output: export) + Monaco editor
  sample_data/      test fixtures
```

## Backend

Requirements: Python 3.11+.

```bash
cd backend
pip install -e .
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
uvicorn api.main:app --reload --port 8000
```

Endpoints (see `backend/api/routes.py`):

- `POST /api/generate-config` — `{ data, description, hints?, source? }` → `{ yaml }`
- `POST /api/transform` — `{ data, yaml, source?, device? }` → `{ events, stats }`
- `GET /api/healthz`

## Frontend

Requirements: Node 18+.

```bash
cd frontend
npm install
cp .env.local.example .env.local   # optional; default API base is http://localhost:8000
npm run dev
```

Open http://localhost:3000.

## Environment variables

Backend (`backend/.env`):

- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` — whichever matches `LLM_PROVIDER`.
- `LLM_PROVIDER` — passed to LangChain's `init_chat_model` (`anthropic`, `openai`, `google_genai`, …). Defaults to `anthropic`. Install the matching integration: `pip install -e .[openai]` or `.[google]`.
- `LLM_MODEL` — model id, defaults to `claude-opus-4-7`.
- `ALLOWED_ORIGIN` — CORS allow-list, defaults to `http://localhost:3000`. Comma-separate for multiple.

Frontend (`frontend/.env.local`):

- `NEXT_PUBLIC_API_BASE_URL` — defaults to `http://localhost:8000`.
