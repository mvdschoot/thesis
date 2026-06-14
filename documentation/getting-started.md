# Getting started

This page gets the app running locally and walks through one transform end to end.

## Prerequisites

- **Python ≥ 3.11** (backend)
- **Node ≥ 18** (frontend)
- Optionally **Docker** (for the full four-service stack incl. a HAPI FHIR server)
- An LLM API key (Anthropic / OpenAI / Google) — only needed for the *generate-config* and
  *suggest-concepts* features, not for running a config you wrote by hand.
- An `OMOPHUB_API_KEY` — only needed for terminology search and OMOP concept resolution.

## Run the backend

```bash
cd backend
pip install -e .
# create a .env (see backend/.env.example for the template)
uvicorn api.main:app --reload --port 8000
```

Required environment variables live in `backend/.env`. Start from `backend/.env.example` and fill
in the keys you need:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | Selects the LLM backend for config generation |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | API key for the chosen provider |
| `OMOPHUB_API_KEY` | Terminology search + OMOP domain routing |

!!! warning "Never commit real keys"
    `.env` files are git-ignored. If a `.env` with live keys was ever committed, untrack it
    (`git rm --cached .env backend/.env`), rotate the leaked keys, and rely on
    `backend/.env.example` as the shared template.

## Run the frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
```

## Or run everything in Docker

```bash
docker compose up -d
```

This brings up four services: the FastAPI `api` (`:8000`), the Next.js `frontend` (`:3000`), a
persistent HAPI FHIR R4 server `hapi-fhir` (`:8080`, Postgres-backed), and its `hapi-db`. The
frontend talks to HAPI directly from the browser; the backend is not involved in FHIR-server
traffic.

## Your first transform

The single endpoint you need is `POST /api/transform`. It takes raw data plus a YAML config and
returns canonical events, stats, a FHIR bundle, and OMOP tables. Here is a minimal run against a
one-record JSON payload:

```bash
curl -s http://localhost:8000/api/transform \
  -H 'content-type: application/json' \
  -d '{
        "source": "withings",
        "format": "json",
        "data": [
          {"userId": "u1", "measurementType": {"typeDescription": "Weight"},
           "measurementValue": 72.5, "measurementDateTime": "2025-01-12T06:04:00Z"}
        ],
        "yaml": "<your YAML config as a string>"
      }'
```

The response shape is documented in [Engine → API contract](engine/api.md). The fastest way to
author the YAML is in the web UI, which previews events, diagnostics, and concept slots as you
edit. See the [DSL Overview](dsl/overview.md) for the structure of that YAML.

## What to read next

- New to the config format? → [DSL → Overview](dsl/overview.md)
- Want a working file to adapt? → [DSL → Examples](dsl/examples.md)
