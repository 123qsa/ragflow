# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAGFlow is an open-source RAG (Retrieval-Augmented Generation) engine based on deep document understanding. It's a full-stack application undergoing a **dual-backend migration**:

- **Python backend** (legacy, port 9380): Quart-based async API server + background task executors
- **Go backend** (new, ports 9383 admin / 9384 API): Gin-based server handling an increasing share of endpoints
- **React/TypeScript frontend** (port 9222 dev, served via Nginx in production)
- Peewee ORM for Python database models, GORM for Go
- Multiple data stores (MySQL/PostgreSQL, Elasticsearch/Infinity/OpenSearch/OceanBase, Redis, MinIO)

## Architecture

### Runtime Architecture

RAGFlow runs as **separate process types**, orchestrated by `docker/launch_backend_service.sh`:

- **API Server** (`api/ragflow_server.py`): Quart-based async HTTP server on port 9380
- **Task Executors** (`rag/svr/task_executor.py`): Background workers processing documents from Redis streams. Multiple instances run in parallel (controlled by `WS` env var). Each consumes from priority-ordered Redis streams (`te.1.common`, `te.0.common`), using consumer groups for load distribution.
- **Go API Server** (`cmd/server_main.go`): Gin-based on port 9384, handling user/auth/chat/search/agent endpoints
- **Go Admin Server** (`cmd/admin_server.go`): Gin-based on port 9383, handling admin/tenant management

Key consequence: task executors import a different code surface than the API server, so always check which process a module is meant for.

### Dual-Backend Routing (Frontend Dev)

During frontend development, `API_PROXY_SCHEME` in `web/.env` controls which backend handles API calls:

| Scheme | Behavior |
|--------|----------|
| `python` | All API calls → Python backend (9380) |
| `go` | All API calls → Go backend (9384) |
| `hybrid` | Selective routing: user/auth/chat/search/agent endpoints → Go (9384), knowledge base/document/LLM → Python (9380), admin → Go admin (9383) |

Proxy rules are defined in `web/vite.config.ts` under `proxySchemes`. When adding new API routes, check whether they need proxy config updates.

### Backend API (`/api/`)

- **App factory**: `api/apps/__init__.py` — creates the Quart app, configures auth (`login_required` decorator, JWT + API token + session fallback), and dynamically discovers/registers blueprints
- **Two API coexisting patterns**:
  - **RESTful APIs** in `api/apps/restful_apis/` — newer pattern with Pydantic request validation, service layer in `api/apps/services/`, routes registered under `/api/v1`
  - **Legacy APIs** in `api/apps/*_app.py` — older pattern using `@validate_request()`, routes registered under `/v1/<page_name>`
  - **SDK APIs** in `api/apps/sdk/` — registered under `/v1/`
- **Services**: `api/db/services/` — business logic wrapping Peewee model operations. `api/apps/services/` — service layer for the RESTful APIs
- **Models**: `api/db/db_models.py` — Peewee ORM models with pooled MySQL/PostgreSQL connections, custom `JSONField`/`ListField` types, retry logic on connection loss

### Go Backend (`/cmd/`, `/internal/`)

- `cmd/server_main.go` — main API server entry point
- `cmd/admin_server.go` — admin server entry point
- `internal/handler/` — Gin HTTP handlers
- `internal/service/` — business logic layer
- `internal/dao/` — data access layer (GORM-based)
- `internal/engine/` — document search engine abstraction (ES/OpenSearch/Infinity)
- `internal/cpp/` — C++ tokenizer library (`librag_tokenizer_c_api.a`) that the Go server links against
- The Go server depends on a built C++ static library; `build.sh --cpp` handles the cmake+make step

### Core Processing (`/rag/`)

- **Document ingestion pipeline**: `rag/flow/pipeline.py` — `Pipeline` (extends `agent.canvas.Graph`) orchestrates the ingestion DAG. Components: File (fetches binary from storage), Parser (dispatches to `deepdoc.parser` based on file type), TokenChunker/TitleChunker (splits into chunks), Tokenizer (computes full-text tokens + embedding vectors), Extractor (LLM-based extraction). Data flows via Pydantic `*FromUpstream` schemas.
- **Document parsing**: `deepdoc/` — PDF parsing (vision-based OCR, layout analysis, table structure recognition) and format-specific parsers (DOCX, XLSX, PPT, Markdown, HTML, images). All parsers normalize to a common structure (list of bbox dicts for PDFs, `{text, doc_type_kwd}` for others).
- **LLM Integration**: `rag/llm/` — factory pattern with runtime class discovery. `chat_model.py` (30+ providers via OpenAI SDK and LiteLLM wrappers), `embedding_model.py`, `rerank_model.py`, `cv_model.py` (image-to-text), `sequence2txt_model.py` (ASR), `tts_model.py`. Use `LLMBundle` (from `api.db.services.llm_service`) as the unified interface.
- **Graph RAG**: `rag/graphrag/` — multi-phase pipeline: per-document subgraph extraction (LLM or spaCy NER), Leiden community detection, entity resolution, community summarization. Entities/relations/reports are indexed as chunks alongside regular text chunks, differentiated by `knowledge_graph_kwd`.
- **Search**: `rag/nlp/search.py` — `Dealer` class combines vector similarity + BM25 + re-ranking. `KGSearch` extends it for graph-aware retrieval (entity resolution, n-hop enrichment).

### Agent System (`/agent/`)

- **Execution engine**: `agent/canvas.py` — `Canvas` (extends `Graph`) executes the DAG. Components are run in topological order via `_run_batch`, each receiving upstream outputs as kwargs. Control-flow components (`Categorize`, `Switch`, `Iteration`, `Loop`) dynamically modify the execution path.
- **Component base**: `agent/component/base.py` — `ComponentBase` with `invoke(**kwargs)` / `invoke_async(**kwargs)` lifecycle. Variable references (`{component_id@output_var}` or `{sys.query}`) are resolved from the canvas graph at runtime.
- **Components**: Modular workflow components in `agent/component/` — Begin, LLM, Agent (tool-calling LLM), Categorize, Switch, Iteration, Loop, Message, Invoke (HTTP), and data manipulation nodes. Auto-discovered by `__init__.py`.
- **Templates**: Pre-built agent workflows as JSON DSL files in `agent/templates/`. Each contains a complete `components` DAG, `path`, and `globals`.
- **Tools**: `agent/tools/` — Retrieval, web search (DuckDuckGo, Google, Tavily, SearXNG), academic search (ArXiv, PubMed, Google Scholar, Wikipedia), code execution, SQL execution, email, GitHub, finance data, translation, weather. Tools implement `ToolBase` (extends `ComponentBase`) and produce OpenAI-compatible function descriptors.
- **Plugins**: `agent/plugin/` — plugin system using `pluginlib` for loading external LLM tool plugins from `embedded_plugins/`.

### MCP Server (`/mcp/`)

RAGFlow can run as an MCP (Model Context Protocol) server, configured via CLI flags in the Docker entrypoint. Enable with `--enable-mcpserver` and related flags in `docker/docker-compose.yml`.

### Frontend (`/web/`)

- React/TypeScript with vitejs framework
- shadcn/ui components (Radix UI primitives + Tailwind CSS)
- `@tanstack/react-query` for server state (cache keys, mutations, invalidation)
- Zustand for local state (primarily agent canvas graph store)
- `react-router` v7 with lazy-loaded pages
- `react-i18next` for i18n (17 languages)
- Axios for HTTP with a layered pattern: endpoint definitions (`utils/api.ts`) → HTTP client (`utils/next-request.ts`) → service layer (`services/`) → query hooks (`hooks/use-*-request.ts`) → components
- `@xyflow/react` for the agent workflow canvas
- `react-hook-form` + `zod` for form validation
- Two API proxy prefixes: `webAPI = '/v1'` (legacy) and `restAPIv1 = '/api/v1'` (RESTful)
- Path alias: `@/` maps to `web/src/`, `@parent/` maps to project root

## Common Development Commands

### Python Backend

```bash
# Install dependencies
uv sync --python 3.13 --all-extras
uv run python3 download_deps.py
pre-commit install

# Start dependent services
docker compose -f docker/docker-compose-base.yml up -d

# Run backend (requires services to be running)
source .venv/bin/activate
export PYTHONPATH=$(pwd)
bash docker/launch_backend_service.sh

# Run all tests
uv run pytest

# Run a single test file
uv run pytest test/test_api.py

# Run tests matching a keyword
uv run pytest -k "test_login"

# Run tests with a specific marker
uv run pytest -m p0

# Run with coverage
uv run pytest --cov

# Linting
ruff check .
ruff format .
```

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

# Run tests
go test ./internal/...
```

### Frontend

```bash
cd web
npm install
npm run dev        # Development server (set API_PROXY_SCHEME in .env)
npm run build      # Production build
npm run lint       # ESLint
npm run test       # Jest tests
npm run type-check # TypeScript check
```

### Docker

```bash
cd docker
docker compose -f docker-compose.yml up -d     # Full stack
docker compose -f docker-compose-base.yml up -d # Base services only
docker logs -f ragflow-server                   # Check server status
docker build --platform linux/amd64 -f Dockerfile -t infiniflow/ragflow:nightly .
```

## Key Configuration Files

- `docker/.env` - Environment variables for Docker deployment
- `docker/service_conf.yaml.template` - Backend service configuration (LLM/embedding defaults, DB/storage connections, OAuth, SMTP)
- `pyproject.toml` - Python dependencies, ruff config, pytest config, coverage config
- `web/package.json` - Frontend dependencies and scripts
- `web/vite.config.ts` - Vite config including API proxy schemes for dual-backend routing

## Testing

- **Python**: pytest with asyncio_mode=auto. Markers: `p0`/`p1`/`p2`/`p3` (priority), `smoke`, `auth`. Test paths: `test/` (unit tests and integration/API tests), `test/playwright/` (E2E).
- **Go**: Standard `go test` with colocated `*_test.go` files under `internal/`.
- **Frontend**: Jest with React Testing Library.
- **SDK Tests**: `sdk/python/test/`

## Python Code Conventions

- **License header**: Every new Python file must begin with the Apache 2.0 license header (see existing files for the exact text).
- **Linting**: ruff with line-length=200, `extend-select = ["ASYNC", "ASYNC1"]`.
- **Import ordering**: ruff handles this automatically.
- **Comments/docstrings**: Must be in English.

## CI/CD

GitHub Actions workflows in `.github/workflows/`:
- `tests.yml` — Runs on push/PR to `main` and version branches. PRs **must have the `ci` label** to trigger the test workflow.
- `release.yml` — Nightly and version-tagged releases. Builds Docker images and publishes to Docker Hub. Publishes Python SDK to PyPI on version tags.

## Database Engines

RAGFlow supports switching between Elasticsearch (default), Infinity, OpenSearch, and OceanBase:

- Set `DOC_ENGINE=infinity` (or `opensearch`, `elasticsearch`, `oceanbase`) in `docker/.env`
- Requires container restart: `docker compose down -v && docker compose up -d`

## Troubleshooting

- **Frontend dev proxy issues**: Check `API_PROXY_SCHEME` in `web/.env`. Update `web/vite.config.ts` `proxySchemes` when adding new API routes.
- **Go build failures**: Ensure `libpcre2-dev`, `cmake`, `g++` are installed. Run `./build.sh --cpp` first.
- **Python import errors**: Ensure `PYTHONPATH=$(pwd)` is exported.
- **Database not initialized**: `launch_backend_service.sh` runs `init_database_tables()` automatically. For manual init: `python -c "from api.db.db_models import init_database_tables; init_database_tables()"`.
- **Task executor crashes**: Check `WS` env var and Redis connectivity. The launch script retries up to 5 times per worker.

1. Think before acting. Read existing files before writing code.
2. Be concise in output but thorough in reasoning.
3. Prefer editing over rewriting whole files.
4. Do not re-read files you have already read.
5. Test your code before declaring done.
6. No sycophantic openers or closing fluff.
7. Keep solutions simple and direct.
8. User instructions always override this file.
