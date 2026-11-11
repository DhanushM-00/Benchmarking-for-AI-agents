# Bifrost Benchmark Platform — Final Frontend Repair Report

**Date:** 2026-11-11

## Files changed

| File | Change |
|------|--------|
| `frontend/src/pages/NewRun.tsx` | Removed unused `MOCK_BENCHMARKS` import; kept `DEFAULT_FAIRNESS`; added `data-testid="summary-total-executions"` |
| `frontend/src/pages/NewRun.tasks.test.tsx` | Removed unused `within` import; strengthened clear-all / executions assertions |
| `frontend/src/pages/NewRun.test.tsx` | Mocked realistic catalogue (benchmarks/tasks/agents) so the four-step workflow reaches Review; launch button becomes available; backend 422 detail is shown |
| `frontend/src/pages/Tasks.test.tsx` | Scoped name/version queries with `within(card)`; click the card button itself (no nested button search) |
| `frontend/src/lib/scenario.live.test.ts` | Windows-safe process tree kill (`taskkill /T /F`); awaited exit; bounded-retry temp-dir removal (no silent EPERM swallow) |

## Stage 1 — TypeScript

- Unused imports removed.
- **Execution status in this sandbox:** `npm install` / `npm run typecheck` could not be completed — the environment's npm registry proxy (`http://35.245.43.102/npm/`) and network path fail or hang for package fetches. Source fixes are in place; run locally:

```powershell
cd frontend
npm ci
npm run typecheck
```

Expected: zero TypeScript errors after the import cleanups.

## Stage 2 — NewRun launch failure

**Root cause:** `routedFetch` returned empty `[]` for benchmarks, tasks, and agents. After Stage 5 `canLaunch` / `canContinue` logic, Continue stayed disabled and the Launch button never appeared.

**Fix:** Provide `MOCK_BENCHES` / `MOCK_TASKS` / `MOCK_AGENTS` in the test, wait for `newrun-task-picker`, then step through Continue three times to Review before clicking Launch. The test still asserts the real backend rejection string (422 detail), not a fake button.

## Stage 3 — Tasks explorer tests

- Multiple "Python Fundamentals" nodes → assert inside `benchmark-card-python-core` with `within`.
- Card is already a `<button>` → click `getByTestId('benchmark-card-debug-suite')` directly.

## Stage 4 — Scenario cleanup (EPERM)

- On Windows, use `taskkill /pid … /T /F` so uvicorn children release SQLite handles.
- Await process exit; short delay; `removeTempDir()` with bounded retries that **re-throw** on final failure (no silent suppression).

## Stage 5 — Catalogue consistency

Frontend unit tests intentionally use small fixtures (2 benchmarks / 5 tasks). Production UI calls `api.listBenchmarks()` / `api.listTasks()` against the live backend (5 / 100). No hardcoded production counts were introduced. When the frontend is pointed at the same running backend as Stage 5 verification, counts match.

## Stage 6 — Production build

**Not executed in this sandbox** (npm install failure). On a normal machine:

```powershell
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

## Remaining limitations

1. This execution environment cannot complete `npm ci` / vitest / vite build due to registry/network limits. All source defects listed above were fixed in the tree.
2. Live Bifrost key scenarios remain environment-dependent (unchanged from Stage 5).
3. React Router future-flag warnings left alone (no routing redesign).

## Acceptance checklist (local machine)

- [ ] `npm run typecheck` — 0 errors
- [ ] `npm test` — all pass, including NewRun launch rejection, Tasks card tests, scenario cleanup
- [ ] `npm run build` — succeeds
- [ ] Connected frontend shows 5 benchmarks / 100 tasks from live backend
