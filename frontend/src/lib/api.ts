
export type ModelCall = {
  id: string
  run_id?: string
  agent_id?: string
  task_id?: string
  strategy?: string
  provider?: string
  model?: string
  started_at?: string
  finished_at?: string
  latency_ms?: number | null
  tokens_input?: number | null
  tokens_output?: number | null
  tokens_cached?: number | null
  total_tokens?: number | null
  cost_usd?: number | null
  cost_source?: string | null
  http_status?: number | null
  success?: boolean
  error?: string | null
  gateway_request_id?: string | null
  attempt?: number
  is_retry?: boolean
  phase?: string
  seq?: number
  metadata?: Record<string, unknown>
}

export type ModelCallSummary = {
  run_id: string
  total_calls: number
  successful_calls: number
  failed_calls: number
  tokens_input: number | null
  tokens_output: number | null
  tokens_cached: number | null
  total_tokens: number | null
  cost_usd: number | null
  cost_source: string | null
  latency_ms_avg: number | null
  latency_ms_p95: number | null
  by_agent: Array<{
    agent_id: string
    calls: number
    success: number
    failed: number
    tokens_input: number
    tokens_output: number
    cost_usd: number | null
    cost_source: string | null
  }>
}

export type RunEvent = {
  event_id?: number
  run_id?: string
  type: string
  message?: string
  ts?: string
  status?: string
  agent_id?: string
  task_id?: string
  duration_ms?: number
  gateway_request_id?: string
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

/* ============================================================
   Bifrost API client.

   Talks to the FastAPI backend described in docs/API.md. When the
   backend is unreachable (or mock mode is on) the client transparently
   serves the fixture catalogue so the dashboard stays fully usable.
   ============================================================ */

import type {
  Agent,
  Benchmark,
  DashboardData,
  FairnessConfig,
  LeaderboardEntry,
  Run,
  Task,
} from '@/types'
import {
  MOCK_AGENTS,
  MOCK_BENCHMARKS,
  MOCK_RUNS,
  MOCK_TASKS,
  buildLeaderboard,
  buildScoreTrend,
} from '@/lib/mockData'

const FORCE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/**
 * Resolved at call time (not module load) so the target can be changed at
 * runtime — tests point it at a different port, and the Settings page reads
 * it live.
 */
export const apiBaseUrl = (): string =>
  (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')

/* ============================================================
   Data source vs. connection state

   These are two different things and must never be conflated:

   * *Connection state* — did the backend actually answer a health check?
   * *Data source*  — are the numbers on screen coming from the live API or
     from the bundled fixture catalogue?

   Deriving "connected" from the data source is what made the dashboard claim
   a live backend that was not running. The connection state now comes from a
   real HTTP probe and nothing else.
   ============================================================ */

export type DataSource = 'live' | 'demo'

let dataSource: DataSource = FORCE_MOCK ? 'demo' : 'live'
const dataSourceListeners = new Set<(s: DataSource) => void>()

export const getDataSource = (): DataSource => dataSource

/**
 * True when the source was demoted to "demo" because the backend was
 * unreachable. A recovered backend may promote the source back to "live";
 * a source that is "demo" for any other reason (an explicit fixture
 * catalogue, a failed data request) is left alone.
 */
let demoFromDisconnect = false

export const setDataSource = (s: DataSource): void => {
  if (dataSource === s) return
  dataSource = s
  dataSourceListeners.forEach((l) => l(s))
}

/** Reset the cached connection state (tests, and a hard reset of the client). */
export const resetConnectionState = (): void => {
  dataSource = FORCE_MOCK ? 'demo' : 'live'
  demoFromDisconnect = false
  dataSourceListeners.forEach((l) => l(dataSource))
}

export const subscribeDataSource = (fn: (s: DataSource) => void): (() => void) => {
  dataSourceListeners.add(fn)
  return () => {
    dataSourceListeners.delete(fn)
  }
}

/** True when the UI is serving bundled fixtures rather than live API data. */
export const isMockMode = (): boolean => dataSource === 'demo'

/** True when demo mode was explicitly requested via VITE_USE_MOCK. */
export const isForcedMock = (): boolean => FORCE_MOCK

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    /** `network` = the backend could not be reached; `http` = it answered with an error. */
    readonly kind: 'network' | 'http' = 'http',
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/* ============================================================
   Backend health
   ============================================================ */

export type BackendState = 'checking' | 'connected' | 'disconnected'

export interface BackendHealth {
  status?: string
  mode?: string
  providers?: Record<string, boolean>
  bifrost?: {
    enabled?: boolean
    gateway_url?: string
    reachable?: boolean
    authenticated?: boolean
    model_call_path_ok?: boolean
    status?: string
    error?: string | null
    latency_ms?: number | null
    cached?: boolean
  }
  docker_available?: boolean
  require_docker?: boolean
  allow_host_sandbox?: boolean
  scorer_version?: string
}

export interface HealthCheckResult {
  state: BackendState
  ok: boolean
  error: string | null
  latencyMs: number | null
  detail: BackendHealth | null
  checkedAt: number
}

export const HEALTH_TIMEOUT_MS = 6000

const DISCONNECTED = (
  error: string,
  latencyMs: number | null = null,
): HealthCheckResult => {
  // No backend means the dashboard falls back to the bundled fixtures, so the
  // data source is demo — regardless of what a previous request returned.
  demoFromDisconnect = true
  setDataSource('demo')
  return {
    state: 'disconnected',
    ok: false,
    error,
    latencyMs,
    detail: null,
    checkedAt: Date.now(),
  }
}

/**
 * Probe the backend's health endpoint with a real HTTP request.
 *
 * Reports `connected` only when the backend answers 2xx with a JSON body
 * whose `status` is `"ok"`. Connection refused, timeouts, network errors,
 * non-JSON bodies, malformed payloads and HTTP error codes are all reported
 * as `disconnected` with a reason. There is no fixture path here on purpose:
 * this function is the single source of truth for connectivity.
 */
export async function probeBackend(timeoutMs: number = HEALTH_TIMEOUT_MS): Promise<HealthCheckResult> {
  const startedAt = typeof performance !== 'undefined' ? performance.now() : Date.now()
  const elapsed = () =>
    Math.round((typeof performance !== 'undefined' ? performance.now() : Date.now()) - startedAt)

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(`${apiBaseUrl()}/health`, {
      method: 'GET',
      signal: controller.signal,
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })

    const latencyMs = elapsed()
    if (!res.ok) {
      return DISCONNECTED(
        `Backend responded with HTTP ${res.status}${res.statusText ? ` ${res.statusText}` : ''}`,
        latencyMs,
      )
    }

    let body: unknown
    try {
      body = await res.json()
    } catch {
      return DISCONNECTED('Backend returned a response that is not valid JSON', latencyMs)
    }

    if (!body || typeof body !== 'object' || (body as { status?: unknown }).status !== 'ok') {
      return DISCONNECTED('Backend health response did not contain a valid "ok" status', latencyMs)
    }

    // The probe proves the backend is reachable — it says nothing about which
    // dataset is on screen, so it never promotes the source on its own. The
    // one exception is a backend that has just come back after being down:
    // then the "demo" state was caused by the outage and can be lifted.
    if (demoFromDisconnect && !FORCE_MOCK && getDataSource() === 'demo') {
      demoFromDisconnect = false
      setDataSource('live')
    }
    return {
      state: 'connected',
      ok: true,
      error: null,
      latencyMs,
      detail: body as BackendHealth,
      checkedAt: Date.now(),
    }
  } catch (err) {
    const latencyMs = elapsed()
    if (err instanceof DOMException && err.name === 'AbortError') {
      return DISCONNECTED(`Health check timed out after ${timeoutMs}ms`, latencyMs)
    }
    if (err instanceof Error && err.name === 'AbortError') {
      return DISCONNECTED(`Health check timed out after ${timeoutMs}ms`, latencyMs)
    }
    const reason = err instanceof Error ? err.message : String(err)
    return DISCONNECTED(`Cannot reach the backend at ${apiBaseUrl()} — ${reason}`, latencyMs)
  } finally {
    clearTimeout(timer)
  }
}

const TIMEOUT_MS = 8000
/** Run creation may probe the Bifrost gateway per model; allow enough headroom. */
const CREATE_RUN_TIMEOUT_MS = 60_000

/**
 * Turn an error response into a message a human can act on.
 *
 * The backend answers `{"detail": "..."}` (FastAPI validation errors use a
 * list of objects), so the raw body is never shown to the user.
 */
function errorDetail(body: string, status: number): string {
  const raw = (body ?? '').trim()
  if (!raw) return `Request failed: ${status}`
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown }
    const detail = parsed.detail ?? parsed.message
    if (typeof detail === 'string' && detail.trim()) return detail.trim()
    if (Array.isArray(detail)) {
      const parts = detail
        .map((d) => {
          if (typeof d === 'string') return d
          const item = d as { loc?: unknown[]; msg?: string }
          const where = Array.isArray(item.loc) ? item.loc.filter((p) => p !== 'body').join('.') : ''
          return where ? `${where}: ${item.msg ?? ''}` : (item.msg ?? '')
        })
        .filter(Boolean)
      if (parts.length) return parts.join(' · ')
    }
  } catch {
    // Not JSON — fall through and show the body as-is.
  }
  return raw.length > 400 ? `${raw.slice(0, 400)}…` : raw
}

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const timeoutMs = init?.timeoutMs ?? TIMEOUT_MS
  const { timeoutMs: _ignored, ...fetchInit } = init ?? {}
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(`${apiBaseUrl()}${path}`, {
      ...fetchInit,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(fetchInit.headers ?? {}),
      },
    })
  } catch (err) {
    throw new ApiError(
      err instanceof Error ? err.message : 'Network request failed',
      undefined,
      'network',
    )
  } finally {
    clearTimeout(timer)
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(errorDetail(body, res.status), res.status, 'http')
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/**
 * Serve live data when the backend is up; fall back to the bundled fixture
 * catalogue only when the backend is genuinely unreachable.
 *
 * An HTTP error (the backend answered, but badly) is re-thrown rather than
 * masked with fixtures — that would hide a real failure behind pretty data.
 * Either way the data source is recorded so the UI can say which one it is.
 */
async function withFallback<T>(path: string, fallback: () => T, init?: RequestInit): Promise<T> {
  if (FORCE_MOCK) {
    setDataSource('demo')
    return fallback()
  }
  try {
    const res = await request<T>(path, init)
    demoFromDisconnect = false
    setDataSource('live')
    return res
  } catch (err) {
    if (err instanceof ApiError && err.kind === 'network') {
      setDataSource('demo')
      return fallback()
    }
    demoFromDisconnect = false
    setDataSource('live')
    throw err
  }
}

/* ============================================================
   Endpoints
   ============================================================ */

export type GatewayStatus = {
  enabled: boolean
  gateway_url: string
  reachable: boolean
  authenticated: boolean
  model_call_path_ok: boolean
  status: string
  error: string | null
  providers: string[]
  models: string[]
  version: string | null
  latency_ms: number | null
}

export const api = {
  listBenchmarks: (): Promise<Benchmark[]> =>
    withFallback('/benchmarks', () => MOCK_BENCHMARKS),

  listTasks: (benchmarkId?: string): Promise<Task[]> =>
    withFallback(
      benchmarkId ? `/benchmarks/${benchmarkId}/tasks` : '/tasks',
      () => (benchmarkId ? MOCK_TASKS.filter((t) => t.benchmark_id === benchmarkId) : MOCK_TASKS),
    ),

  getTask: (taskId: string): Promise<Task> =>
    withFallback(`/tasks/${encodeURIComponent(taskId)}`, () => {
      const t = MOCK_TASKS.find((x) => x.id === taskId)
      if (!t) throw new ApiError(`task '${taskId}' not found`, 404, 'http')
      return t
    }),

  listAgents: (): Promise<Agent[]> => withFallback('/agents', () => MOCK_AGENTS),

  registerAgent: (payload: Partial<Agent>): Promise<Agent> =>
    withFallback(
      '/agents',
      () => ({
        id: `agent-${Date.now().toString(36)}`,
        name: payload.name ?? 'New agent',
        model: payload.model ?? 'unknown',
        model_provider: payload.model_provider ?? 'unknown',
        description: payload.description ?? '',
        system_prompt_version: 'sys-2.4.1',
        tools: payload.tools ?? [],
        orchestration: payload.orchestration ?? 'ReAct loop',
        memory: payload.memory ?? 'None',
        color_index: payload.color_index ?? 3,
        enabled: true,
        cost_per_1k_input: payload.cost_per_1k_input ?? 0.001,
        cost_per_1k_output: payload.cost_per_1k_output ?? 0.008,
        registered_at: new Date().toISOString(),
      }),
      { method: 'POST', body: JSON.stringify(payload) },
    ),

  listRuns: (): Promise<Run[]> => withFallback('/runs', () => MOCK_RUNS),

  /**
   * Fetch one run by the exact id returned from createRun / listRuns.
   *
   * Never substitutes a different run when the id is unknown — that used to
   * make the UI poll and display a fixture run while the URL still pointed at
   * a nonexistent id (e.g. run-2511), producing repeated 404s after recovery.
   */
  getRun: (id: string): Promise<Run> =>
    withFallback(`/runs/${id}`, () => {
      const found = MOCK_RUNS.find((r) => r.id === id)
      if (!found) {
        throw new ApiError(`run '${id}' not found`, 404, 'http')
      }
      return found
    }),

  /**
   * Create a benchmark run. The only authoritative run id is the one returned
   * by POST /api/v1/runs. The client must never invent an id and navigate to it.
   *
   * Mutations do not fall back to fixtures on network errors: a timeout during
   * gateway probing used to synthesize a random `run-####` id, navigate there,
   * then 404 once the backend was reachable again.
   */
  createRun: async (payload: {
    benchmark_id: string
    agent_ids: string[]
    task_ids?: string[]
    fairness: FairnessConfig
    notes?: string
    name?: string
  }): Promise<Run> => {
    if (FORCE_MOCK) {
      setDataSource('demo')
      const bench = MOCK_BENCHMARKS.find((b) => b.id === payload.benchmark_id) ?? MOCK_BENCHMARKS[0]
      const now = new Date().toISOString()
      const taskIds =
        payload.task_ids ?? MOCK_TASKS.filter((t) => t.benchmark_id === bench.id).map((t) => t.id)
      // Demo-only id. Stable enough for the fixture session; never used against a live API.
      const id = `run-demo-${Date.now().toString(36)}`
      return {
        id,
        name: payload.name || `${bench.name} · ${id}`,
        benchmark_id: bench.id,
        benchmark_name: bench.name,
        agent_ids: payload.agent_ids,
        task_ids: taskIds,
        task_count: taskIds.length,
        agent_results: [],
        status: 'queued',
        fairness: payload.fairness,
        fairness_report: { score: 0, checks: [], violations: [] },
        started_at: now,
        finished_at: null,
        duration_sec: null,
        progress: 0,
        notes: (payload.notes ?? '').startsWith('[SIMULATED]')
          ? payload.notes ?? ''
          : `[SIMULATED] ${payload.notes ?? ''}`.trim(),
        created_by: 'you',
        execution_mode: 'simulated' as const,
      }
    }

    const run = await request<Run>('/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeoutMs: CREATE_RUN_TIMEOUT_MS,
    })
    demoFromDisconnect = false
    setDataSource('live')
    if (!run?.id || typeof run.id !== 'string') {
      throw new ApiError('Backend created a run without an id', 500, 'http')
    }
    return run
  },

  cancelRun: (id: string): Promise<Run> =>
    withFallback(
      `/runs/${id}/cancel`,
      () => {
        const run = MOCK_RUNS.find((r) => r.id === id)
        if (!run) throw new ApiError(`run '${id}' not found`, 404, 'http')
        run.status = 'cancelled'
        return run
      },
      { method: 'POST' },
    ),

  leaderboard: (benchmarkId?: string): Promise<LeaderboardEntry[]> =>
    withFallback(
      `/leaderboard${benchmarkId ? `?benchmark_id=${benchmarkId}` : ''}`,
      () => {
        const runs = benchmarkId ? MOCK_RUNS.filter((r) => r.benchmark_id === benchmarkId) : MOCK_RUNS
        return buildLeaderboard(runs)
      },
    ),

  analytics: (params?: { benchmarkId?: string; agentId?: string; provider?: string }) => {
    const q = new URLSearchParams()
    if (params?.benchmarkId) q.set('benchmark_id', params.benchmarkId)
    if (params?.agentId) q.set('agent_id', params.agentId)
    if (params?.provider) q.set('provider', params.provider)
    const qs = q.toString()
    return request<any>(`/analytics${qs ? `?${qs}` : ''}`)
  },
  runReport: (runId: string) => request<any>(`/runs/${runId}/report`),
  dashboard: (): Promise<DashboardData> =>
    withFallback('/dashboard', () => {
      const completed = MOCK_RUNS.filter((r) => r.status === 'completed')
      const allResults = completed.flatMap((r) => r.agent_results)
      const totalCost = allResults.reduce((s, a) => s + a.total_cost_usd, 0)
      const totalTokens = allResults.reduce((s, a) => s + a.total_tokens, 0)
      const totalTasks = allResults.reduce((s, a) => s + a.task_results.length, 0)
      const fairnessScores = completed.map((r) => r.fairness_report.score).filter((s) => s > 0)

      return {
        stats: {
          total_runs: MOCK_RUNS.length,
          completed_runs: completed.length,
          tasks_executed: totalTasks,
          total_agent_executions: allResults.length,
          total_cost_usd: Math.round(totalCost * 100) / 100,
          total_tokens: totalTokens,
          avg_overall_score:
            Math.round((allResults.reduce((s, a) => s + a.overall_score, 0) / (allResults.length || 1)) * 10) / 10,
          avg_cost_per_run: Math.round((totalCost / (completed.length || 1)) * 100) / 100,
          avg_execution_time_sec:
            Math.round((allResults.reduce((s, a) => s + a.avg_execution_time_sec, 0) / (allResults.length || 1)) * 10) / 10,
          fairness_score: fairnessScores.length
            ? Math.round(fairnessScores.reduce((s, v) => s + v, 0) / fairnessScores.length)
            : 0,
        },
        recent_runs: MOCK_RUNS.slice(0, 6),
        leaderboard: buildLeaderboard(MOCK_RUNS),
        score_trend: buildScoreTrend(MOCK_RUNS),
        cost_by_benchmark: MOCK_BENCHMARKS.map((b, i) => {
          const spent = completed
            .filter((r) => r.benchmark_id === b.id)
            .flatMap((r) => r.agent_results)
            .reduce((s, a) => s + a.total_cost_usd, 0)
          return {
            name: b.name,
            value: Math.round(spent * 100) / 100,
            color: ['#5b8cff', '#2dd4a7', '#f5a524', '#a78bfa', '#f472b6'][i % 5],
          }
        }),
      }
    }),

  /** Maxim AI Bifrost gateway status (never exposes keys). */
  modelCalls: (runId: string, opts?: { agentId?: string; errorsOnly?: boolean; offset?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (opts?.agentId) q.set('agent_id', opts.agentId)
    if (opts?.errorsOnly) q.set('errors_only', 'true')
    if (opts?.offset != null) q.set('offset', String(opts.offset))
    if (opts?.limit != null) q.set('limit', String(opts.limit))
    const qs = q.toString()
    return request<{ run_id: string; calls: ModelCall[]; count: number; offset: number; limit: number }>(
      `/runs/${runId}/model-calls${qs ? `?${qs}` : ''}`,
    )
  },
  modelCallSummary: (runId: string) =>
    request<ModelCallSummary>(`/runs/${runId}/model-calls/summary`),
  modelCall: (callId: string) => request<ModelCall>(`/model-calls/${callId}`),
  runEvents: (runId: string, afterId = 0, agentId?: string) => {
    const q = new URLSearchParams({ after_id: String(afterId) })
    if (agentId) q.set('agent_id', agentId)
    return request<{ run_id: string; events: RunEvent[]; count: number }>(`/runs/${runId}/events?${q}`)
  },
  runToolCalls: (runId: string, agentId?: string) => {
    const q = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''
    return request<{ run_id: string; tool_calls: any[]; count: number }>(`/runs/${runId}/tool-calls${q}`)
  },
  runTimeline: (runId: string, agentId?: string) => {
    const q = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''
    return request<{ run_id: string; items: any[]; count: number }>(`/runs/${runId}/timeline${q}`)
  },
  /**
   * Maxim AI Bifrost gateway status.
   *
   * Never falls back to fixtures: a gateway status is a live measurement, and
   * inventing one would let the UI claim a gateway that is not there. The
   * request throws when the backend is unreachable — the caller turns that
   * into an explicit "unknown / unreachable" state.
   */
  gatewayStatus: (): Promise<GatewayStatus> => request<GatewayStatus>('/gateway/status'),
}
