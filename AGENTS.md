# RAGFlow Project Instructions for AI Coding Agents

This file provides build instructions, architecture context, and coding standards for the RAGFlow project. Expect the reader of this file to know nothing about the project.

## 1. Project Overview

RAGFlow is an open-source RAG (Retrieval-Augmented Generation) engine based on deep document understanding. It is a full-stack application with a Python legacy backend, a new Go backend, and a React/TypeScript frontend.

- **Version**: 0.25.6
- **License**: Apache 2.0
- **Project Language**: English (all comments, documentation, and commit messages must be in English)

### High-Level Architecture

The project currently runs a **dual-backend** architecture during migration:

1. **Python Backend** (legacy, port `9380`)
   - `api/ragflow_server.py`: Main API server (Quart/Flask-based).
   - `rag/svr/task_executor.py`: Background task executors for document parsing and indexing.
2. **Go Backend** (new, port `9384`)
   - `cmd/server_main.go`: Main API server (Gin-based).
   - `cmd/admin_server.go`: Admin server (port `9383`).
3. **Frontend** (port `9222` dev, served via Nginx in production)
   - React 18 + TypeScript + Vite.
   - Proxies API calls to either Python, Go, or both (`hybrid` mode).

### External Dependencies

RAGFlow requires the following services to run:

- **MySQL** 8.0+ (metadata and relational data)
- **Redis / Valkey** (caching, distributed locks, sessions)
- **MinIO** (object storage for files and documents)
- **Elasticsearch** or **OpenSearch** or **Infinity** (vector search and full-text search; choose one)
- Optional: **OceanBase** / **SeekDB** (alternative doc stores), **TEI** (text embedding inference)

## 2. Directory Structure

### Python Code

- `api/` — Backend API server (Quart/Flask).
  - `apps/` — API blueprints: RESTful APIs, auth, LLM app, services.
  - `db/` — Database models (`db_models.py`), init data, and service layer under `services/`.
  - `utils/` — API-specific utilities.
- `rag/` — Core RAG logic.
  - `app/` — Application-level RAG logic.
  - `llm/` — LLM, embedding, rerank, OCR, TTS, ASR model abstractions.
  - `svr/` — Background servers (task executor, document parsing).
  - `utils/` — RAG utilities (Redis, ES/Infinity connections).
  - `graphrag/` — GraphRAG implementation.
  - `advanced_rag/` — Advanced retrieval strategies.
  - `prompts/` — Prompt templates.
- `deepdoc/` — Document parsing and OCR modules.
  - `parser/` — Parsers for PDF, DOCX, PPTX, XLSX, HTML, Markdown, etc.
  - `vision/` — Vision models for layout detection and OCR.
- `agent/` — Agentic reasoning components with a visual canvas.
  - `component/` — Reusable agent components (LLM, browser, message, iteration, etc.).
  - `canvas.py` — Visual workflow canvas engine.
  - `tools/` — Built-in agent tools (search, data source connectors, etc.).
  - `sandbox/` — Code execution sandbox.
- `common/` — Shared Python utilities (settings, config utils, crypto, HTTP client, metadata filters, file utils, decorators, etc.).
  - `data_source/` — Connectors to external data sources.
  - `doc_store/` — Document store abstractions.
- `memory/` — Memory services for agent conversations.
- `mcp/` — Model Context Protocol (MCP) client and server.
- `sdk/python/` — Python SDK for RAGFlow.

### Go Code

- `cmd/` — Entry points.
  - `server_main.go` — RAGFlow Go API server.
  - `admin_server.go` — Admin server.
  - `ingestion_server.go` — Document ingestion server.
  - `ragflow_cli.go` — Interactive CLI.
- `internal/` — Core Go implementation.
  - `handler/` — HTTP handlers (Gin handlers).
  - `service/` — Business logic layer.
  - `dao/` — Data access layer (GORM-based).
  - `entity/` — Data models / structs.
  - `engine/` — Document search engine abstraction (ES / OpenSearch / Infinity).
  - `router/` — Route definitions.
  - `server/` — Configuration and server initialization.
  - `common/` — Shared utilities (logging, errors, constants).
  - `cache/` — Redis cache layer.
  - `storage/` — Object storage abstraction.
  - `tokenizer/` — C++ tokenizer bindings (rag_analyzer).
  - `cpp/` — C++ dependencies and build files for tokenizer.
  - `cli/` — CLI implementation.
  - `binding/` — Language bindings.
  - `ingestion/` — Ingestion pipeline logic.
- `internal/development.md` — Detailed Go backend startup guide.

### Frontend

- `web/` — React + TypeScript frontend.
  - `src/pages/` — Page components.
  - `src/components/` — Reusable UI components.
  - `src/hooks/` — Custom React hooks.
  - `src/services/` — API request wrappers.
  - `src/locales/` — i18n translations.
  - `src/routes.tsx` — Route definitions.
  - `vite.config.ts` — Vite configuration (includes proxy schemes for dev).

### Infrastructure

- `docker/` — Docker deployment configurations.
  - `docker-compose.yml` — Full stack deployment.
  - `docker-compose-base.yml` — Base services (MySQL, Redis, MinIO, ES/Infinity).
  - `launch_backend_service.sh` — Script to start Python backend locally.
  - `service_conf.yaml.template` — Service configuration template.
- `helm/` — Kubernetes Helm charts.
- `conf/` — JSON/YAML config files (model factories, ES/Infinity mappings, system settings).
- `test/` — Test suites.
  - `unit_test/` — Python unit tests.
  - `testcases/` — Integration and API tests (RESTful, HTTP, SDK, web).
  - `playwright/` — E2E UI tests.

## 3. Technology Stack

| Layer | Technology |
|-------|-----------|
| Python Runtime | CPython 3.13 – 3.14 |
| Python Package Manager | `uv` |
| Python Web Framework | Quart / Flask (legacy), litellm for LLM routing |
| Go Runtime | Go 1.25.0 |
| Go Web Framework | Gin |
| Go ORM | GORM |
| Go Doc Engine | go-elasticsearch/v8, infinity-go-sdk, opensearch-py equivalent via Go SDK |
| Frontend Framework | React 18 + TypeScript 5.9 |
| Frontend Build Tool | Vite 7 |
| Frontend Styling | Tailwind CSS 3 + Less |
| Frontend State | Zustand, TanStack Query (React Query) |
| Frontend Routing | React Router 7 |
| UI Components | Radix UI + custom shadcn/ui-inspired components |
| Tests (Python) | pytest, pytest-asyncio, pytest-playwright |
| Tests (Go) | Go standard testing + stretchr/testify patterns |
| Tests (Frontend) | Jest, Testing Library |
| Linting (Python) | ruff |
| Linting (Frontend) | ESLint + Prettier |
| Pre-commit | pre-commit hooks (ruff, trailing-whitespace, etc.) |

## 4. Build Instructions

### Python Backend

The project uses **uv** for dependency management.

```bash
# 1. Sync dependencies and create venv
uv sync --python 3.13 --all-extras

# 2. Download model dependencies (DeepDoc models, NLTK data, etc.)
uv run python3 download_deps.py

# 3. Start dependent services (MySQL, ES/Infinity, Redis, MinIO)
docker compose -f docker/docker-compose-base.yml up -d

# 4. Activate venv and launch
source .venv/bin/activate
export PYTHONPATH=$(pwd)
bash docker/launch_backend_service.sh
```

The `launch_backend_service.sh` script:
- Initializes DB tables via `api.db.db_models.init_database_tables()`
- Runs MySQL migrations for model providers
- Starts `WS` (default 1) task executor workers (`rag/svr/task_executor.py`)
- Starts the main `api/ragflow_server.py`

### Go Backend

```bash
# First build (includes C++ tokenizer library)
./build.sh --cpp

# Subsequent builds (Go only)
./build.sh --go

# Run binaries
./bin/admin_server          # port 9383
./bin/ragflow_server        # port 9384
./bin/ragflow_cli           # interactive CLI
```

**Note**: The Go server depends on a C++ static library (`librag_tokenizer_c_api.a`) built from `internal/cpp/`. The `build.sh` script handles cmake + make for this.

### Frontend

```bash
cd web
npm install

# Development server (port 9222 by default)
# Proxy mode can be python / go / hybrid
export API_PROXY_SCHEME=hybrid
npm run dev
```

| Proxy Scheme | Behavior |
|-------------|----------|
| `python` | All API calls → Python backend (9380) |
| `go` | All API calls → Go backend (9384) |
| `hybrid` | Selective routing: some endpoints → Go (9384), some → Python (9380), admin → Go admin (9383) |

### Full Docker Deployment

```bash
cd docker
docker compose -f docker-compose.yml up -d
```

## 5. Testing Instructions

### Python Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest test/test_api.py

# Run with coverage
uv run pytest --cov
```

Test markers defined in `pyproject.toml`:
- `p0` – critical priority
- `p1` – high priority
- `p2` – medium priority
- `p3` – low priority
- `smoke` – smoke tests
- `auth` – authentication UI tests

### Go Tests

Go tests are colocated with source files (`*_test.go`). Run with:

```bash
go test ./internal/...
```

### Frontend Tests

```bash
cd web
npm run test        # Jest + coverage
npm run type-check  # TypeScript check
```

### E2E Tests

Playwright tests live in `test/playwright/`.

```bash
uv run pytest test/playwright/  # or use playwright directly
```

## 6. Code Style & Guidelines

### Python

- **Formatter/Linter**: `ruff` (configured in `pyproject.toml`).
  ```bash
  ruff check .
  ruff format .
  ```
- **Line length**: 200 characters.
- **Async linting**: ruff enables `ASYNC` and `ASYNC1` rules by default.
- **Import order**: ruff handles import sorting.
- **License header**: Every Python file must begin with the Apache 2.0 header:
  ```python
  #
  #  Copyright 202X The InfiniFlow Authors. All Rights Reserved.
  #
  #  Licensed under the Apache License, Version 2.0 (the "License");
  #  ...
  #
  ```
- **Project language**: All code comments and docstrings must be in English.

### Go

- Follow standard Go formatting (`gofmt` / `goimports`).
- See `.agents/skills/go-naming/SKILL.md` for naming conventions.
- Tests are colocated: `foo.go` → `foo_test.go`.
- License header required (same Apache 2.0 style).

### Frontend (TypeScript / React)

- **Linter**: ESLint with TypeScript, React, and React Hooks plugins.
  ```bash
  cd web
  npm run lint
  ```
- **Formatter**: Prettier with `prettier-plugin-organize-imports`.
- **Styling**: Tailwind CSS + Less for legacy overrides.
- **Path aliases**: `@/` maps to `web/src/`. `@parent/` maps to project root.
- **React patterns**: Functional components with hooks. State via Zustand or TanStack Query.

### Pre-commit

Install and run pre-commit hooks:

```bash
pre-commit install
pre-commit run --all-files
```

Hooks include:
- `check-yaml`, `check-json`, `end-of-file-fixer`, `trailing-whitespace`
- `ruff` (lint + fix)
- `ruff-format`

## 7. Configuration

### Service Configuration

Runtime service config is loaded from `conf/service_conf.yaml` (generated from `docker/service_conf.yaml.template`).

Key sections:
- `ragflow` / `admin` — Server bind host and ports.
- `mysql` — Metadata DB connection.
- `es` / `os` / `infinity` — Vector search engine connection.
- `minio` / `s3` / `oss` / `azure` / `opendal` — Object storage.
- `redis` — Cache and session store.
- `oauth` — OAuth2 / OIDC / GitHub login config.
- `smtp` — Email server config.
- `user_default_llm` — Default LLM/embedding model settings.

### Environment Variables

- `PYTHONPATH` — Must include project root when running Python code.
- `RAGFLOW_HOST` — Override bind host.
- `RAGFLOW_DEBUGPY_LISTEN` — Enable debugpy remote debugging.
- `API_PROXY_SCHEME` — Frontend dev proxy mode (`python` / `go` / `hybrid`).
- `WS` — Number of task executor workers (default 1).

## 8. Key Module Details

### Document Processing Pipeline

1. Documents are uploaded via API and stored in MinIO / S3.
2. `DocumentService` creates DB records.
3. `task_executor.py` picks up tasks from Redis queue.
4. `deepdoc/parser/` extracts text, tables, and images.
5. `rag/svr/` chunks content, generates embeddings, and writes to ES/OpenSearch/Infinity.

### LLM Routing

The `rag/llm/` module abstracts all model interactions:
- `chat_model.py` — Chat completions via litellm and direct provider SDKs.
- `embedding_model.py` — Text embedding generation.
- `rerank_model.py` — Reranking.
- `cv_model.py` — Vision / multi-modal models.
- `ocr_model.py` — OCR.
- `tts_model.py` / `sequence2txt_model.py` — Speech synthesis / ASR.

### Agent Canvas

`agent/canvas.py` implements a visual workflow engine where nodes (`agent/component/`) are connected into a DAG and executed asynchronously. Components include LLM, browser, message, iteration, switch, variable assigner, etc.

## 9. Deployment & Operations

### Docker Images

- `Dockerfile` — Multi-stage build for the full application.
- `Dockerfile.deps` — Pre-builds heavy dependencies (models, NLTK, Tika).
- `Dockerfile.scratch.oc9` — OceanBase-specific variant.

### Helm / Kubernetes

Helm charts are in `helm/`:
- `Chart.yaml` and `values.yaml` for K8s deployment.

### CI/CD

GitHub Actions workflows (`.github/workflows/`):
- `tests.yml` — Runs on push/PR to `main` and version branches. Includes ruff checks, Go build, and test execution on self-hosted runners.
- `release.yml` — Nightly and version-tagged releases. Builds Docker images and publishes to Docker Hub. Publishes Python SDK to PyPI on version tags.

**CI requirements for PRs**: PRs must have the `ci` label to trigger the test workflow.

## 10. Security Considerations

- `common/ssrf_guard.py` — SSRF protection for outgoing HTTP requests.
- `pycryptodomex` — Used for encryption of sensitive config values.
- OAuth/OIDC support for external authentication.
- API token management via `api_token.go` / `api_token.go` (Go) and corresponding Python APIs.
- MinIO/Redis/DB passwords are configurable via environment variables; do not commit real credentials.

## 11. Troubleshooting

- **Frontend dev proxy issues**: Check `API_PROXY_SCHEME` in `web/.env` or environment. Update `web/vite.config.ts` `proxySchemes` when adding new API routes.
- **Go build failures**: Ensure `libpcre2-dev`, `cmake`, `g++` are installed. Run `./build.sh --cpp` first.
- **Python import errors**: Ensure `PYTHONPATH=$(pwd)` is exported.
- **Database not initialized**: `launch_backend_service.sh` runs `init_database_tables()` automatically. For manual init: `python -c "from api.db.db_models import init_database_tables; init_database_tables()"`.
- **Task executor crashes**: Check `WS` env var and Redis connectivity. The script retries up to 5 times per worker.
