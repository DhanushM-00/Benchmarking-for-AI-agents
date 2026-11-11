# Bifrost Benchmark Platform

Fair, reproducible benchmarking for AI coding agents. React dashboard + FastAPI backend + optional Maxim AI Bifrost gateway.

| Service | Port | URL |
|---------|------|-----|
| Vite frontend (dev) | **5173** | http://127.0.0.1:5173 |
| FastAPI backend | **8000** | http://127.0.0.1:8000 |
| Bifrost gateway | **8081** | http://127.0.0.1:8081 (internal) |
| Integrated (prod) | **8000** | http://127.0.0.1:8000 (SPA + API same origin) |

Prefer **127.0.0.1** over `localhost` in config so IPv4/IPv6 resolution stays consistent on Windows.

## Catalogue

- **5 benchmarks**, **100 tasks**, all with hidden test suites
- **3 built-in agents** (Atlas, Nova, Forge) + user-registered agents
- Catalogue sync is idempotent: upgrades fill missing rows without wiping runs

## Windows one-command start

```powershell
# From repo root (PowerShell)
.\scripts\start-all.ps1
```

This starts Bifrost (8081), backend (8000) and frontend (5173) in separate windows, checks ports, waits for health, and reports the failing service if any step fails.

```powershell
.\scripts\status.ps1     # independent health of all three
.\scripts\stop-all.ps1     # stop listeners on 5173 / 8000 / 8081
```

Individual scripts still work:

```powershell
.\scripts\start-bifrost.ps1
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

### First-time setup

```powershell
# Backend venv
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # set BIFROST_API_KEY if using live mode
cd ..

# Frontend deps
cd frontend
npm ci
cd ..
```

Open http://127.0.0.1:5173

### Expected health check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
# status = ok, catalogue_version present, task_count = 100
```

## Integrated single-port mode

1. Build the frontend: `cd frontend; npm run build`
2. Start only the backend: `.\scripts\start-backend.ps1`
3. Open **http://127.0.0.1:8000** — the SPA is served from `frontend/dist`, API under `/api`, WebSockets on the same host.
4. Bifrost remains internal; virtual keys are never sent to the browser.

Development mode keeps three ports (Vite proxies `/api` and WebSockets to the backend).

## Linux / macOS

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend (other terminal)
cd frontend
npm ci
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1 npm run dev -- --host 127.0.0.1 --port 5173

# Optional gateway
npx -y @maximhq/bifrost -port 8081
```

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `BIFROST_MODE` | `auto` | `auto` / `live` / `simulated` |
| `BIFROST_GATEWAY_URL` | `http://127.0.0.1:8081` | Maxim AI Bifrost base URL (authoritative) |
| `BIFROST_API_KEY` | empty | Virtual key sent as `x-bf-vk` header |
| `BIFROST_ENABLED` | `1` | Route live LLM calls via Bifrost |
| `BIFROST_REQUIRE_DOCKER` | `1` | Fail closed without Docker for live docker isolation |
| `BIFROST_ALLOW_HOST_SANDBOX` | `0` | Dev-only subprocess grading (unsafe) |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | Frontend → backend (dev) |
| `VITE_USE_MOCK` | `false` | Force fixture catalogue |

**Never commit `backend/.env`.** Use `.env.example` as the template. Secrets are never returned by health or gateway status endpoints.

## Modes

- **simulated** — deterministic local results; every run notes `[SIMULATED]`
- **live** — real model calls + hidden-test grading; refuses to start if requirements are missing (no silent fallback)
- **auto** — live when possible; otherwise simulated with explicit `mode_reasons`

## Key API routes

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/health` | Liveness + catalogue counts (no secrets) |
| GET | `/api/v1/gateway/status` | Fresh Bifrost probe (independent of backend liveness) |
| GET | `/api/v1/benchmarks` | 5 benchmarks, live `task_count` |
| GET | `/api/v1/tasks` | Full catalogue (filters optional) |
| GET | `/api/v1/tasks/{id}` | Single task (no hidden tests) |
| GET | `/api/v1/catalogue/integrity` | Version + integrity |
| POST | `/api/v1/runs` | Body may include `task_ids` |
| GET | `/api/v1/runs/{id}` | Run detail + progress |
| POST | `/api/v1/runs/{id}/cancel` | Cancel queued/running |
| WS | `/api/v1/runs/{id}/stream` | Live run events |

See [docs/API.md](docs/API.md) and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Tests

```powershell
# Backend (expect 89 passed, 1 skipped)
cd backend
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="."
python -m pytest tests/ -q

# Frontend
cd frontend
npm test
npm run typecheck
npm run build
```

## Security notes

- API keys / virtual keys never appear in health/gateway responses or logs
- Live untrusted code expects Docker isolation; subprocess is opt-in and warned
- CORS defaults to Vite dev origins only (`localhost` and `127.0.0.1` on 5173/4173)
- Hidden tests are stored server-side and never returned by the task API
- Bifrost virtual keys stay server-side; the browser never receives them
