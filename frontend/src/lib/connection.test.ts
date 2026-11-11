/**
 * Phase 5 — backend connection detection.
 *
 * These tests pin the behaviour that was broken: the dashboard used to derive
 * "connected" from the demo-mode flag, so it reported a live backend that was
 * not running, and a slow gateway probe made the backend look offline.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  api,
  apiBaseUrl,
  getDataSource,
  isMockMode,
  probeBackend,
  setDataSource,
  HEALTH_TIMEOUT_MS,
} from '@/lib/api'

const BACKEND = 'http://127.0.0.1:8765/api/v1'

const okResponse = (body: unknown = { status: 'ok', mode: 'live' }) => ({
  ok: true,
  status: 200,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

/** A fetch that hangs until the abort signal fires — models a slow backend. */
const hangingFetch = () =>
  vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise((_resolve, reject) => {
        const signal = init?.signal
        if (!signal) return
        signal.addEventListener('abort', () =>
          reject(new DOMException('The operation was aborted.', 'AbortError')),
        )
      }),
  )

describe('probeBackend', () => {
  beforeEach(() => {
    setDataSource('live')
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('reports connected only when the backend answers 2xx with status "ok"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse()))

    const res = await probeBackend()

    expect(res.state).toBe('connected')
    expect(res.ok).toBe(true)
    expect(res.error).toBeNull()
    expect(res.latencyMs).toBeGreaterThanOrEqual(0)
    expect(fetch).toHaveBeenCalledWith(`${BACKEND}/health`, expect.anything())
  })

  it('reports disconnected when the backend refuses the connection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const res = await probeBackend()

    expect(res.state).toBe('disconnected')
    expect(res.ok).toBe(false)
    expect(res.error).toContain(BACKEND)
    expect(res.detail).toBeNull()
  })

  it('reports disconnected on an HTTP error status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'boom' }),
        text: async () => 'boom',
      }),
    )

    const res = await probeBackend()

    expect(res.state).toBe('disconnected')
    expect(res.ok).toBe(false)
    expect(res.error).toMatch(/503/)
  })

  it('reports disconnected when the body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('Unexpected token < in JSON at position 0')
        },
        text: async () => '<html>nginx</html>',
      }),
    )

    const res = await probeBackend()

    expect(res.state).toBe('disconnected')
    expect(res.error).toBeTruthy()
  })

  it('reports disconnected when the payload is JSON but not a healthy status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse({ status: 'degraded' })))

    const res = await probeBackend()

    expect(res.state).toBe('disconnected')
    expect(res.ok).toBe(false)
  })

  it('aborts and reports disconnected when the backend hangs past the timeout', async () => {
    vi.stubGlobal('fetch', hangingFetch())

    const started = Date.now()
    const res = await probeBackend()
    const elapsed = Date.now() - started

    expect(res.state).toBe('disconnected')
    expect(res.error).toMatch(/timed out|abort/i)
    expect(elapsed).toBeLessThan(HEALTH_TIMEOUT_MS + 4000)
  }, 20_000)

  it('never returns a connected state without a successful response', async () => {
    const failures = [
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}), text: async () => 'x' }),
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}), text: async () => '{}' }),
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'nope' }), text: async () => '{}' }),
    ]

    for (const f of failures) {
      vi.stubGlobal('fetch', f)
      const res = await probeBackend()
      expect(res.state).not.toBe('connected')
      expect(res.ok).toBe(false)
    }
  })
})

describe('data source is independent of connection state', () => {
  beforeEach(() => {
    setDataSource('live')
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('serves the fixture catalogue and marks demo when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const benchmarks = await api.listBenchmarks()

    expect(benchmarks.length).toBeGreaterThan(0)
    expect(getDataSource()).toBe('demo')
    expect(isMockMode()).toBe(true)
  })

  it('marks live when the backend answers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse([])))

    await api.listBenchmarks()

    expect(getDataSource()).toBe('live')
    expect(isMockMode()).toBe(false)
  })

  it('does not mask a real HTTP failure with fixtures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'boom' }),
        text: async () => 'boom',
      }),
    )

    await expect(api.listBenchmarks()).rejects.toThrow()
  })

  it('marks the data source as demo as soon as the probe fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    expect(getDataSource()).toBe('live')
    await probeBackend()
    expect(getDataSource()).toBe('demo')
  })
})

describe('backend error messages are readable', () => {
  beforeEach(() => {
    setDataSource('live')
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('shows the backend detail instead of a raw JSON body', async () => {
    const detail = 'live docker isolation requires Docker. Start Docker, or set BIFROST_ALLOW_HOST_SANDBOX=1.'
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail }),
        text: async () => JSON.stringify({ detail }),
      }),
    )

    await expect(api.createRun({
      benchmark_id: 'python-core',
      agent_ids: ['atlas-coder'],
      fairness: {} as any,
    })).rejects.toThrow(detail)
  })

  it('joins FastAPI validation errors into one sentence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: [{ loc: ['body', 'fairness', 'repeats'], msg: 'Input should be >= 1' }] }),
        text: async () => JSON.stringify({ detail: [{ loc: ['body', 'fairness', 'repeats'], msg: 'Input should be >= 1' }] }),
      }),
    )

    await expect(api.listBenchmarks()).rejects.toThrow(/fairness\.repeats: Input should be >= 1/)
  })
})

describe('gateway status is never fabricated', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('rejects instead of returning a made-up status when the backend is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(api.gatewayStatus()).rejects.toThrow()
  })

  it('rejects on an HTTP error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
        text: async () => 'boom',
      }),
    )

    await expect(api.gatewayStatus()).rejects.toThrow()
  })

  it('passes the backend payload through unchanged', async () => {
    const payload = {
      enabled: true,
      gateway_url: 'http://localhost:8080',
      reachable: true,
      authenticated: false,
      model_call_path_ok: false,
      status: 'auth_error',
      error: '401 unauthorized',
      providers: [],
      models: [],
      version: null,
      latency_ms: 12,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(payload)))

    const res = await api.gatewayStatus()

    expect(res.status).toBe('auth_error')
    expect(res.authenticated).toBe(false)
    expect(res.reachable).toBe(true)
  })
})

describe('apiBaseUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('reads the configured base URL and strips a trailing slash', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://example.test:9000/api/v1/')
    expect(apiBaseUrl()).toBe('http://example.test:9000/api/v1')
  })
})

describe('run ID consistency — never invent or substitute', () => {
  beforeEach(() => {
    setDataSource('live')
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
    vi.stubEnv('VITE_USE_MOCK', 'false')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('createRun uses the exact id returned by POST /runs', async () => {
    const serverRun = {
      id: 'run-2509',
      name: 'Python Fundamentals · run-2509',
      benchmark_id: 'python-core',
      status: 'queued',
      agent_ids: ['atlas-coder'],
      task_ids: ['python-core-t01'],
      task_count: 1,
      agent_results: [],
      fairness: {},
      fairness_report: { score: 0, checks: [], violations: [] },
      started_at: new Date().toISOString(),
      finished_at: null,
      duration_sec: null,
      progress: 0,
      notes: '[SIMULATED]',
      created_by: 'api',
      execution_mode: 'simulated',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => serverRun,
        text: async () => JSON.stringify(serverRun),
      }),
    )

    const run = await api.createRun({
      benchmark_id: 'python-core',
      agent_ids: ['atlas-coder'],
      task_ids: ['python-core-t01'],
      fairness: {} as any,
    })

    expect(run.id).toBe('run-2509')
    expect(run.id).not.toMatch(/^run-demo-/)
    expect(run.id).toBe(serverRun.id)
  })

  it('createRun does not invent a random id when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(
      api.createRun({
        benchmark_id: 'python-core',
        agent_ids: ['atlas-coder'],
        fairness: {} as any,
      }),
    ).rejects.toThrow()
  })

  it('getRun throws for an unknown id instead of substituting another run', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: "run 'run-2511' not found" }),
        text: async () => JSON.stringify({ detail: "run 'run-2511' not found" }),
      }),
    )

    await expect(api.getRun('run-2511')).rejects.toThrow(/run-2511/)
  })

  it('getRun on network error does not return a different fixture run id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(api.getRun('run-2511')).rejects.toThrow(/run-2511|not found/i)
  })
})
