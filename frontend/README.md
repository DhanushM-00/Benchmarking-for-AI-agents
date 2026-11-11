# Bifrost Dashboard — Frontend

React 18 + TypeScript + Vite + Recharts dashboard for the Bifrost AI agent benchmarking platform.

See [`../README.md`](../README.md) for the full project overview and
[`../docs/API.md`](../docs/API.md) for the backend contract.

## Quick start

```bash
npm install
cp .env.example .env
npm run dev          # http://localhost:5173
```

## Scripts

| Command | Does |
|---|---|
| `npm run dev` | Vite dev server with `/api` → `localhost:8000` proxy |
| `npm run build` | `tsc --noEmit` then production build to `dist/` |
| `npm run preview` | Serve the production build on `:4173` |
| `npm run typecheck` | Types only |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | FastAPI base URL |
| `VITE_USE_MOCK` | `true` | `false` to require the live backend |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | Dev-server proxy target |

With the backend unreachable the client serves the bundled fixture catalogue and the topbar shows a
**Demo data** badge.

## Structure

```
src/
├── types/index.ts        domain model (mirrors backend pydantic schemas)
├── lib/api.ts            API client + fixture fallback
├── lib/mockData.ts       deterministic fixture catalogue
├── lib/format.ts         formatters
├── hooks/useAsync.ts     useAsync · usePolling · useLocalStorage
├── components/           layout · ui primitives · themed chart wrappers
└── pages/                Dashboard · NewRun · Runs · RunDetail · Leaderboard
                          Tasks · Agents · Fairness · Settings
```
