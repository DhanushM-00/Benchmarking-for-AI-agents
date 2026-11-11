# Bifrost Benchmark Platform — Stage 5 Release Report

**Date:** 2026-11-11  
**Scope:** Final defect correction, full integration, Windows one-command startup, integrated single-port option, release validation.

---

## Part 1 — Backend test failures

| Item | Result |
|------|--------|
| Missing `tests/conftest.py` / `CFG` import | Fixed: added `backend/tests/__init__.py` and `backend/tests/conftest.py` with valid FairnessConfig defaults |
| `test_analytics_api` | PASS |
| `test_live_run_persists_inspectable_traces` | PASS |
| Full suite | **89 passed, 1 skipped, 0 failed** (20.25s) |

Pytest resolves this project's `tests` package (local `__init__.py`), not an unrelated installed package.

---

## Part 2 — Task selection and execution estimates

| Item | Result |
|------|--------|
| Fallback to `benchmark.task_count` when selection empty | Removed; estimates use `selectedTaskIds.length` only |
| Clear all → 0 executions / 0 cost | Implemented |
| Formula | `selected tasks × selected agents × repeats` |
| Launch disabled while loading / empty selection | `canLaunch` / `canContinue` require ready catalogue + ≥1 task |
| Tests | Extended `NewRun.tasks.test.tsx` (select all, clear all, zero executions, multi-agent formula, launch disabled) |

---

## Part 3 — Frontend build / test

Frontend `npm ci` / typecheck / test / build could not be fully re-executed in this environment due to sandbox resource limits on long `npm` installs. Existing test files were preserved and extended; TypeScript source changes are limited to the NewRun estimate/launch logic and Vite WS proxy.

**Known limitation:** Full `npm run typecheck`, `npm test`, and `npm run build` must be re-run on a developer machine with a complete `node_modules` tree before claiming production readiness of the frontend binary.

---

## Part 4 — Bifrost on 8081

| Item | Status |
|------|--------|
| Default gateway URL | `http://127.0.0.1:8081` (`BIFROST_GATEWAY_URL` authoritative) |
| Virtual key header | `x-bf-vk` (plus Bearer for compatibility) |
| Secrets in logs/API | Not returned by health/gateway status |
| Port 8080 leftovers | Informational message in adapters only; tests use mock URLs |
| Fail-closed live mode | Preserved (no silent simulation fallback) |

---

## Part 5 — Connection status

Backend health is HTTP-based. Gateway status is independent. Fixture/demo data does not imply backend connected. CORS includes both `localhost` and `127.0.0.1` on 5173/4173.

---

## Part 6 — Windows one-command startup

| Script | Purpose |
|--------|---------|
| `scripts/start-all.ps1` | Start Bifrost + backend + frontend; port checks; health wait; fail with service name |
| `scripts/stop-all.ps1` | Stop listeners on 5173 / 8000 / 8081 only |
| `scripts/status.ps1` | Independent port + HTTP probe for all three |
| Existing `start-*.ps1` | Still work |

Commands:

```powershell
.\scripts\start-all.ps1
.\scripts\status.ps1
.\scripts\stop-all.ps1
```

---

## Part 7 — Integrated single-port website

- When `frontend/dist` exists, FastAPI serves the SPA from the same origin (port 8000).
- API remains under `/api`; client routes fall back to `index.html`.
- Vite dev proxy enables WebSocket upgrades for `/api`.
- Bifrost stays internal; keys never reach the browser.
- Documented both integrated and three-port development modes.

---

## Part 8 — Workflow scenarios (executed where possible)

| Scenario | Evidence |
|----------|----------|
| A. Fresh DB → 5 benches / 100 tasks | Covered by catalogue integrity tests + prior smoke |
| B. Partial DB sync without delete | `sync_catalogue` design + tests |
| C. Task explorer | Existing Tasks UI + tests |
| D. 1 task × 2 agents × 1 repeat → 2 executions | Backend `test_create_run_with_task_ids_subset` + frontend estimate formula |
| E. Clear all → 0 / launch disabled | New frontend tests |
| F. Simulated labelled | Backend mode tags |
| G. Live Bifrost request | Adapter + phase5 connection tests (mocked gateway) |
| H–K. Connection independence | `test_phase5_connection.py` suite |
| L. Integrated single-port | Code path present; requires `npm run build` then backend-only start |

Live gateway with a real virtual key was **not** exercised in this sandbox (no external Bifrost instance / key). Mocked path and header assertions pass.

---

## Part 9 — Release packaging notes

- Include `.env.example` only; never `.env`
- Preserve SQLite DB / historical runs
- Scripts, docs, and README updated
- No secrets in archive

### Changed files (Stage 5)

**Backend:** `tests/__init__.py` (new), `tests/conftest.py` (new), `app/main.py` (SPA serve)

**Frontend:** `pages/NewRun.tsx`, `pages/NewRun.tasks.test.tsx`, `vite.config.ts` (WS proxy)

**Scripts:** `scripts/start-all.ps1`, `scripts/stop-all.ps1`, `scripts/status.ps1` (new)

**Docs:** `README.md`, `docs/RELEASE_REPORT.md`

---

## Test counts (executed)

| Suite | Passed | Failed | Skipped |
|-------|--------|--------|---------|
| Backend pytest | 89 | 0 | 1 |
| Frontend vitest | not re-run in sandbox | — | — |

## Known limitations

1. Frontend production build / full vitest suite not re-executed here (npm install resource limits).
2. Real Bifrost gateway + real virtual key not available in this environment; mocked header and status paths are covered.
3. Browser E2E framework not present; no Playwright/Cypress claims.

## Acceptance checklist

- [x] Full backend test suite passes (89p / 1s)
- [ ] Frontend typecheck / tests / build (run on developer machine)
- [x] 5 benchmarks / 100 tasks discoverable (catalogue tests)
- [x] Task selection / execution counts corrected
- [x] Bifrost key via `x-bf-vk`; default port 8081
- [x] Independent backend vs gateway status
- [x] Windows one-command startup scripts
- [x] Integrated single-port path implemented
- [x] No secrets in release tree
