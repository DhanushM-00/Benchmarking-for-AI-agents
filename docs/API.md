# Bifrost API

Base URL: `http://127.0.0.1:8000/api/v1`

Errors are always `{ "detail": "<string>" }` so the UI can show them verbatim.

## Catalogue

### `GET /benchmarks`
Array of benchmarks. `task_count` is computed from the database.

### `GET /benchmarks/{id}/tasks`
Plain array of tasks. Query: `search`, `difficulty`, `category`, `limit`, `offset`.

### `GET /tasks`
Same filters; optional `benchmark_id`.

### `GET /tasks/{task_id}`
Single task document. **Never includes hidden tests.**

### `GET /catalogue/integrity`
`catalogue_version`, counts, `db_matches_catalogue`, missing/extra task ids.

## Agents

### `GET /agents` / `GET /agents/{id}` / `POST /agents`
Unknown agent ids return **404** (no silent substitution).

## Runs

### `POST /runs` (201)

```json
{
  "benchmark_id": "python-core",
  "agent_ids": ["atlas-coder", "nova-coder"],
  "task_ids": ["python-core-t01", "python-core-t02"],
  "fairness": { "...": "FairnessConfig — all fields required" },
  "notes": "",
  "name": null
}
```

- Omit `task_ids` to run the full benchmark (backward compatible).
- Empty `task_ids` → 422.
- Foreign/unknown task ids → 422.
- Live mode never silently falls back to simulated (use `BIFROST_MODE=auto` for explicit fallback with `mode_reasons`).

Response includes `task_ids`, `task_count`, `dataset_hash`, `total_executions`, `execution_mode`.

### `GET /runs/{id}`, `POST /runs/{id}/cancel`
### `GET /runs/{id}/events`, `/model-calls`, `/model-calls/summary`

## Health

### `GET /health`
Fast. Gateway status may be cached. Includes `catalogue_version`, `task_count`, `benchmark_count`. **No API keys.**

### `GET /gateway/status`
Fresh probe. Distinguishes unreachable vs auth_error vs connected; `model_call_path_ok` is separate from mere reachability.
