# Progressive Harmonization ETL — Web App

A web app for turning heterogeneous health/behavioural data into canonical events, FHIR R4 Bundles, and OMOP CDM v5.4 tables via LLM-generated YAML adapter configs.

## Flow

1. **Upload or paste** a JSON/CSV data sample in the browser.
2. **Describe** what the data is (subject field, record shape, quirks).
3. **Generate** — the backend calls an LLM to draft a YAML adapter config.
4. **Edit** the YAML in the in-browser Monaco editor if needed.
5. **Run** the config through the pipeline; inspect the resulting canonical events, FHIR Bundle, and OMOP CDM tables.
6. **Map concepts** — review auto-suggested terminology codes (LOINC, SNOMED, UCUM) and bind them to event slots.

No data is persisted server-side. Each request is stateless.

## Layout

```
impl/
  backend/          FastAPI single-service ETL (Python ≥ 3.11)
    api/            HTTP handlers, Pydantic models, LLM client, terminology proxy, config CRUD
    pipeline/       seven in-process stages (connector → adapter → cleaner → validator → qualifier → mapper → fhir + omop)
    domain/         canonical event model, quality rules, value-level utils
    configs/        adapter YAML configs (also the LLM few-shot corpus)
    pyproject.toml
  frontend/         Next.js (client-only, output: export) + Monaco editor
  sample_data/      test fixtures (mHealth, Fitabase CSVs, clinical pilots, serious games, VR, questionnaires)
```

## Backend

Requirements: Python 3.11+.

```bash
cd backend
pip install -e .
cp .env.example .env
# edit .env — see "Environment variables" below
uvicorn api.main:app --reload --port 8000
```

Or via Docker: `docker compose up -d` (single service `api` on :8000).

Endpoints (see `backend/api/routes.py`):

- `POST /api/generate-config` — `{ data, description, hints?, source? }` → `{ id, yaml }`
- `POST /api/transform` — `{ data, yaml, source?, device?, format?, concept_mappings? }` → `{ events, stats, bundle?, omop_cdm?, concept_slots, adapter_diagnostics }`
- `POST /api/suggest-config-fix` — `{ yaml, diagnostics, sample_record, description? }` → `{ yaml }` (LLM-patched config)
- `POST /api/suggest-concepts` — `{ slots }` → `{ suggestions, no_matches, errors }` (LLM + OMOPHub terminology mapping)
- `GET /api/terminology/search` — `?system=loinc&q=heart+rate&max=20` → terminology code search (OMOPHub proxy)
- `GET /api/configs` / `GET /api/configs/{id}` / `PUT /api/configs/{id}` — config CRUD
- `POST /api/configs/match` — `{ data, format, source? }` → ranked config matches
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
- `OMOPHUB_API_KEY` — bearer token for OMOPHub terminology search (get one at https://dashboard.omophub.com). Required for `/api/terminology/search` and `/api/suggest-concepts`.
- `ALLOWED_ORIGIN` — CORS allow-list, defaults to `http://localhost:3000`. Comma-separate for multiple.

Frontend (`frontend/.env.local`):

- `NEXT_PUBLIC_API_BASE_URL` — defaults to `http://localhost:8000`.
