# Run ID Consistency Investigation

**Date:** 2026-11-11  
**Symptom:** Frontend repeatedly requested `GET /api/v1/runs/run-2511` → 404. Backend created runs successfully (`POST` → 201); `run-2509` retrieved fine.

## Lifecycle (as designed)

1. **Create** — `POST /api/v1/runs` → `service.create_run` → `Store.insert_run` allocates `run-{2500 + seq}` from SQLite AUTOINCREMENT, persists JSON doc, returns the document including `id`.
2. **Submit** — orchestrator queues work under that id.
3. **Frontend** — `NewRun` navigates to `/runs/${run.id}` using **only** the POST response body.
4. **Detail** — `RunDetail` reads `:id` from the route, polls `getRun(id)`, and loads report / model-calls / events for that same id.
5. **Refresh** — SPA reload hits the same route; backend serves the persisted row from `bifrost.db`.

Backend 404 path already returns a clear message (`run '{id}' not found`) and does not substitute another run.

## Root cause

The frontend **invented** run ids that never existed in the database.

### 1. `createRun` mock fallback generated random ids (`frontend/src/lib/api.ts`)

```ts
id: `run-${Math.floor(Math.random() * 9000 + 1000)}`  // e.g. run-2511
```

`withFallback` treated **any network failure** (including AbortController timeout) as “use fixtures”.  
`POST /runs` often exceeds the default **8s** client timeout because live/auto mode probes Bifrost chat completions (up to ~12s per distinct model). The client aborted, fell back to a random id, and navigated to `/runs/run-2511`. The backend may still have completed the real create under a different id (`run-2509`, …). Subsequent GETs for the phantom id 404.

### 2. `getRun` silently substituted another run

```ts
() => MOCK_RUNS.find((r) => r.id === id) ?? MOCK_RUNS[0]
```

On network error or unknown fixture id, the UI could display **MOCK_RUNS[0]** (different id) while the URL and polling still targeted the missing id — amplifying 404 noise for report / traces / events.

### 3. Secondary panels used `current.id`

`ModelTracePanel` / `EventLog` / `TimelinePanel` took `current.id` from merged poll state. If substitution had occurred, those panels would request the wrong id. They now use the **route param**.

## Fixes

| File | Change |
|------|--------|
| `frontend/src/lib/api.ts` | `createRun`: no fixture fallback on network error in live mode; only `VITE_USE_MOCK` uses a `run-demo-*` id; 60s timeout for create; require response `id`. |
| `frontend/src/lib/api.ts` | `getRun` / `cancelRun`: unknown id → `ApiError` 404; never substitute another run. |
| `frontend/src/lib/api.ts` | `request()` accepts optional `timeoutMs`. |
| `frontend/src/pages/RunDetail.tsx` | Traces / events / timeline use route `id`. |
| `backend/tests/test_stage3_launch.py` | Regression: create↔get id match, 404 message, report/model-calls/events same id, refresh, no substitution. |
| `frontend/src/lib/connection.test.ts` | Regression: create uses server id; network/timeout do not invent ids; getRun does not substitute. |

## Validation (local)

```powershell
cd backend
pytest tests/test_stage3_launch.py -k "id_consistency or same_id or substituted or page_refresh" -q

cd ../frontend
npm test -- src/lib/connection.test.ts
```

Manual: create a run → confirm URL id equals POST body id → refresh → report / model-calls / events all use that id → unknown id returns 404 detail containing the id.

## What was not changed

- API contracts for create/get.
- Real benchmark execution path (no mock-only execution).
- 404 responses remain hard errors (not hidden).
