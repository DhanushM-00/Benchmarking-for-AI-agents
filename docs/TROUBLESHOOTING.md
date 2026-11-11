# Troubleshooting

## Backend offline in the UI

1. Confirm FastAPI is listening: `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health`
2. Align hosts: frontend `VITE_API_BASE_URL` must match (prefer `127.0.0.1`, not `localhost`).
3. CORS: backend `BIFROST_CORS_ORIGINS` must include the Vite origin (`http://127.0.0.1:5173`).
4. If the UI shows **Demo data**, the client fell back to fixtures after a network error — fix connectivity, then refresh.

## Bifrost gateway

| Symptom | Meaning |
|---------|---------|
| `reachable: false` | Process not listening on 8081, or firewall |
| `status: auth_error` | Gateway up; virtual key rejected |
| `reachable: true` but `model_call_path_ok: false` | Health ok, models path not confirmed — live calls may still fail |

Start gateway on **8081**:

```powershell
.\scripts\start-bifrost.ps1
# or: npx -y @maximhq/bifrost -port 8081
```

Do not treat gateway reachability alone as proof that model execution works.

## Live run rejected (422)

Common detail strings:

- `live mode unavailable — BIFROST_GATEWAY_URL is empty`
- `live docker isolation requires Docker...`
- `unknown agent` / `unknown task_ids` / `not in benchmark`
- `selected tasks have no hidden test suites`

Use `BIFROST_MODE=simulated` for offline demos, or `auto` to allow labeled simulation fallback.

## Port already in use

```powershell
Get-NetTCPConnection -LocalPort 8000,8081,5173 -State Listen |
  Select-Object LocalPort, OwningProcess
```

Stop the old process or change the port in the start script **and** the matching env var.

## Windows Python / venv

Scripts look for `backend\.venv\Scripts\python.exe`, then `.myenv`, then `venv`. Create one with:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Avoid assuming Linux paths such as `backend/.venv/bin/python` in Windows terminals.

## Docker / subprocess

- Live + `isolation=docker` requires Docker, unless `BIFROST_ALLOW_HOST_SANDBOX=1`.
- Subprocess isolation is **development only** and is recorded on the run fairness report when used as a downgrade.

## Clean vs existing database

Catalogue sync on startup upserts benchmarks/tasks/built-in agents. It does **not** delete runs or user agents. Safe to restart repeatedly.
