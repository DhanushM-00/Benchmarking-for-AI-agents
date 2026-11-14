# Bifrost Benchmark Platform

A platform for evaluating, comparing, and understanding AI coding agents
through repeatable benchmark runs.

Bifrost Benchmark Platform brings benchmark tasks, AI agents, execution
results, model-call traces, and performance analytics into one
workspace. It helps developers move beyond a single pass/fail score and
understand how agents perform, where they fail, how long they take, and
what model usage information is available.

> **Project status:** This project is a working prototype with a React
> dashboard, FastAPI backend, benchmark catalogue, run orchestration,
> analytics, and a Maxim AI Bifrost gateway adapter. Validate the
> current checkout and its live integrations in your own environment
> before using it for production evaluations.

## Why this project?

AI coding agents can produce different results even when given similar
programming tasks. A useful comparison needs consistent tasks,
evaluation rules, execution limits, and inspectable evidence.

The platform is designed to help answer:

-   Which agent completes more benchmark tasks correctly?
-   How do agents compare on completion, latency, and reliability?
-   Which tasks cause failures, and what kinds of failures occur?
-   What model calls and tool activity happened during a run?
-   How much token usage and cost were reported by the gateway/provider?
-   Were the agents evaluated under comparable conditions?

## Key features

### Benchmark catalogue and task explorer

-   Browse benchmark collections and their tasks.
-   Inspect task descriptions and execution requirements.
-   Search and filter tasks using available task attributes.
-   Select individual tasks or a larger task set for evaluation.
-   Keep hidden evaluation tests separate from the task information
    shown to agents.

### AI agent management

-   View the built-in coding agents.
-   Compare agents across benchmark runs.
-   Register supported custom agent configurations through the backend
    API.
-   Evaluate different agent strategies, including ReAct-style and
    plan/act/verify-style execution.

### Benchmark execution

-   Select a benchmark, tasks, and one or more agents.
-   Configure available evaluation and fairness settings.
-   Estimate the number of executions before launching.
-   Track run progress and inspect completed, failed, or cancelled
    tasks.
-   Review run details, task outcomes, and generated reports.

The estimated execution count is based on:

`selected tasks × selected agents × repeats`

Choose at least one task before launching a run.

### Maxim AI Bifrost integration

-   Route live model requests through the Bifrost gateway.
-   Authenticate from the backend using a Bifrost virtual key.
-   Keep gateway credentials on the server rather than exposing them in
    browser code.
-   Check gateway connectivity separately from backend health.
-   Use an explicitly labelled simulated mode for demonstrations and
    offline development.

### Analytics and observability

-   Review benchmark results, agent comparisons, and leaderboards.
-   Explore run reports, execution events, and model-call records.
-   Inspect latency and token usage when returned by the provider.
-   View cost information when the gateway/provider supplies it.
-   Review failure patterns, recovery behaviour, and fairness evidence.

**Measurement note:** Token usage, latency, and cost depend on the
metadata returned by the configured model provider and Bifrost. The
platform should not invent missing values. A successful API response
alone does not prove that a live model call occurred; check the recorded
execution mode and model-call trace.

## How it works

1.  **Choose a benchmark** and inspect its tasks.
2.  **Choose agents** to evaluate against the same task selection.
3.  **Set run conditions**, such as repeats, time limits, token budgets,
    isolation, and network policy where supported.
4.  **Launch the run.** The backend coordinates agent execution and
    records task outcomes, events, tool activity, and model calls.
5.  **Evaluate solutions** using the benchmark's evaluation logic and
    configured tests, including hidden tests where applicable.
6.  **Review the evidence** in run details, reports, traces, fairness
    checks, and analytics.
7.  **Compare agents** using the recorded results and execution
    conditions.

## Technology

  Area                  Technology
  --------------------- ---------------------------------------
  Frontend              React, TypeScript, Vite
  UI and charts         Recharts, Lucide React
  Backend API           Python, FastAPI, Pydantic
  Model gateway         Maxim AI Bifrost
  HTTP communication    HTTPX
  Persistence           SQLite
  Testing               Pytest, Vitest, React Testing Library
  Development scripts   PowerShell

## Getting started

### Requirements

Install the following before starting:

-   Windows 10/11, macOS, or Linux
-   Python 3.10 or newer
-   Node.js and npm
-   Git
-   Maxim AI Bifrost for live model inference
-   Docker Desktop when using the configured Docker-based isolation for
    live code execution

The included PowerShell helper scripts are intended for Windows. On
other operating systems, start the backend, frontend, and Bifrost using
the commands appropriate for your environment.

### 1. Get the project

Clone the repository:

``` bash
git clone https://github.com/DhanushM-00/Benchmarking-for-AI-agents
cd Benchmarking-for-AI-agents
```

Alternatively, download the repository as a ZIP file and extract it.

Replace the repository URL and folder name above with the values for
your GitHub repository.

### 2. Set up the backend

From the project directory, open PowerShell and run:

``` powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `backend/.env` and configure the settings required by your
environment. For Bifrost live mode, the main settings are:

``` dotenv
BIFROST_MODE=live
BIFROST_ENABLED=1
BIFROST_GATEWAY_URL=http://127.0.0.1
BIFROST_API_KEY=YOUR_BIFROST_VIRTUAL_KEY
```

Use the actual gateway address configured in your Bifrost installation.

**Important credential distinction:** - `BIFROST_API_KEY` must contain a
Bifrost **virtual key**. - Your provider credential (for example, a
Gemini API key) belongs in the Bifrost provider configuration, not in
place of the virtual key. - Do not commit `.env` files, API keys,
virtual keys, or other secrets to GitHub. - Never expose gateway
credentials through frontend environment variables.

For interface demonstrations or offline development, use the explicitly
supported simulated mode:

``` dotenv
BIFROST_MODE=simulated
```

Simulated runs are not real model evaluations and must not be reported
as live provider results.

### 3. Set up the frontend

Open another terminal from the project directory:

``` powershell
cd frontend
npm install
Copy-Item .env.example .env
```

Ensure the frontend is configured to use the backend rather than fixture
data:

``` dotenv
VITE_USE_MOCK=false
```

Use the supplied example configuration as the starting point. Update the
API base configuration only when your backend is hosted at a different
address.

### 4. Start the application

#### Windows: use the helper script

From the project root, run:

``` powershell
.\scripts\start-all.ps1
```

The helper starts the configured services in separate terminal windows
and performs basic startup checks. Configure Bifrost and its provider
before attempting live model execution.

If Bifrost is already running:

``` powershell
.\scripts\start-all.ps1 -SkipBifrost
```

Check service status:

``` powershell
.\scripts\status.ps1
```

Stop services started by the helper:

``` powershell
.\scripts\stop-all.ps1
```

Review the helper scripts and their prerequisites before using them in a
different environment.

#### Start services manually

If you prefer to start services separately:

**Backend**

``` powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

**Frontend**

``` powershell
cd frontend
npm run dev
```

**Bifrost**

Start Maxim AI Bifrost using your installed Bifrost setup. The project
also includes a Windows helper:

``` powershell
.\scripts\start-bifrost.ps1
```

Keep the required services running while using the platform.

### 5. Open the application

After startup, open the frontend address printed by the development
server or launcher in your browser.

The backend also provides interactive API documentation through its
`/docs` route while the backend is running. When a production frontend
build is available, the backend can serve the built website from the
same origin.

## Using the platform

### Explore benchmarks

Open the benchmark catalogue, select a benchmark, and inspect its tasks.
Choose the complete task set or only the tasks relevant to your
evaluation.

### Select agents

Review the available agents and select the agents you want to compare.
Use the same task selection and shared run settings when making a direct
comparison.

### Create a benchmark run

1.  Open the new-run workflow.
2.  Select a benchmark.
3.  Select one or more agents.
4.  Choose the tasks to execute.
5.  Configure the available evaluation and fairness settings.
6.  Review the estimated execution count.
7.  Launch the run and follow its progress.

### Review results

Open a completed run to inspect the available evidence:

-   Overall run status and benchmark results
-   Per-task outcomes and evaluation details
-   Agent comparisons and leaderboard results
-   Model-call traces and summaries
-   Execution events and timeline information
-   Tool-call activity
-   Token usage, latency, and cost fields when available
-   Fairness checks and generated reports

## Execution modes

-   **Live:** Sends model requests through the configured Bifrost
    gateway. It requires a reachable gateway, a valid Bifrost virtual
    key, configured provider credentials, an available model route, and
    the required execution environment.
-   **Simulated:** Supports demonstrations and offline development.
    Simulated results are not evidence of real model performance,
    provider token usage, or actual provider cost.
-   **Auto:** Uses the automatic behaviour configured by the project.
    Inspect the run's recorded execution mode and mode reasons before
    interpreting results.

Always verify the execution mode and inspect model-call traces before
sharing benchmark findings. Gateway connectivity by itself does not
prove that a real model completion succeeded.

## Configuration reference

Backend settings are read from `backend/.env`.

  -----------------------------------------------------------------------
  Variable                            Purpose
  ----------------------------------- -----------------------------------
  `BIFROST_MODE`                      Selects `live`, `simulated`, or
                                      `auto` execution behaviour

  `BIFROST_ENABLED`                   Enables or disables Bifrost
                                      integration

  `BIFROST_GATEWAY_URL`               Base address of the Bifrost gateway

  `BIFROST_API_KEY`                   Bifrost virtual key used by the
                                      backend

  `BIFROST_DB`                        Optional SQLite database file
                                      location

  `BIFROST_TIMEOUT_SEC`               Timeout for gateway requests

  `BIFROST_REQUIRE_DOCKER`            Requires Docker isolation for live
                                      untrusted-code execution

  `BIFROST_ALLOW_HOST_SANDBOX`        Development-only host sandbox
                                      option

  `BIFROST_MAX_PARALLEL_RUNS`         Maximum number of parallel
                                      benchmark runs

  `BIFROST_CORS_ORIGINS`              Allowed browser origins for backend
                                      requests

  `BIFROST_SEED_DEMO`                 Enables optional demo-run seeding
                                      on a fresh database
  -----------------------------------------------------------------------

Frontend settings are read from `frontend/.env`.

  -----------------------------------------------------------------------
  Variable                            Purpose
  ----------------------------------- -----------------------------------
  `VITE_API_BASE_URL`                 Backend API base address

  `VITE_USE_MOCK`                     Enables fixture/demo data when set
                                      to `true`

  `VITE_PROXY_TARGET`                 Backend target used by the Vite
                                      development proxy
  -----------------------------------------------------------------------

Do not place secrets in variables prefixed with `VITE_`. Frontend
environment variables are bundled into browser-accessible code.

## Testing and quality checks

Run backend tests:

``` powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

Run frontend checks:

``` powershell
cd frontend
npm run typecheck
npm test
npm run build
```

For an optional live Bifrost smoke test, configure and start the gateway
with a valid virtual key first. Then run this from the backend
environment:

``` powershell
$env:BIFROST_SMOKE="1"
pytest -q -rs
```

A live smoke test may fail if the gateway is unavailable, the virtual
key is invalid, provider credentials are missing, or the requested model
cannot be accessed. Mocked-gateway tests are useful for application
testing but are not proof of a successful real provider call.

The packaged project notes recorded **89 backend tests passed and 1
skipped** at the time of that validation. Re-run the tests in your
current checkout before relying on that result. Frontend type checking,
tests, and production build should also be run in your own environment.

## Troubleshooting

### The dashboard shows demo data

Confirm that the backend is running, `VITE_USE_MOCK=false`, and the
frontend API configuration points to the correct backend. Restart the
frontend after changing environment variables.

### The frontend cannot connect to the backend

Check that the backend started successfully, that the frontend API base
configuration is correct, and that the backend allows the frontend
origin through its CORS settings. Inspect the browser console and
backend logs for the failing request.

### Bifrost reports an authentication error

Confirm that `BIFROST_API_KEY` contains an active virtual key created in
the same Bifrost instance. A provider API key and a Bifrost virtual key
are different credentials.

### Bifrost is reachable but model calls fail

Check provider configuration, model permissions, virtual-key access
rules, model routing, and gateway logs. Gateway reachability alone does
not prove that model completion requests are working.

### Live execution requires Docker

Start Docker Desktop and confirm it is ready. The default configuration
requires Docker isolation for live untrusted-code execution. Use a host
sandbox override only for local development when you understand and
accept the security implications.

### A run cannot be found

Verify that the run was successfully created and persisted, and that the
frontend is using the run ID returned by the backend. Review the backend
logs and the run lifecycle documentation if the issue continues.

## Security notes

-   Keep `.env` files and credentials private.
-   Use Bifrost virtual keys for gateway access.
-   Never expose provider keys or virtual keys in frontend code.
-   Use an isolated execution environment for live code evaluation.
-   Treat host sandbox options as development-only unless their security
    implications have been reviewed.
-   Review authentication, authorization, rate limits, network access,
    and deployment settings before exposing the platform publicly.

## Additional documentation

If included in your checkout, refer to the following project documents
for deeper technical details:

-   `docs/API.md` --- API endpoints and request/response behaviour.
-   `docs/TROUBLESHOOTING.md` --- setup, gateway, environment, and
    execution troubleshooting.
-   `docs/RELEASE_REPORT.md` --- release validation and known
    limitations.
-   `docs/RUN_ID_CONSISTENCY_REPORT.md` --- run ID lifecycle
    investigation.
-   `frontend/README.md` --- frontend-specific guidance.

## Contributing

Contributions, bug reports, and suggestions are welcome.

1.  Fork the repository.
2.  Create a branch for your change.
3.  Make the change and add or update tests.
4.  Run the relevant backend and frontend checks.
5.  Open a pull request with a clear explanation of the change.

Do not include API keys, virtual keys, private database files, or local
environment files in pull requests.

## License

Add a `LICENSE` file before describing this repository as open source or
granting reuse permissions. No license should be assumed unless one is
included in the repository.

## Acknowledgements

Built with the Python, React, and TypeScript ecosystems and integrated
with [Maxim AI Bifrost](https://www.getbifrost.ai/) for model gateway
functionality.
