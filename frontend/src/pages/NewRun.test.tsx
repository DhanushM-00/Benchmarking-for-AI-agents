/**
 * A rejected run must be visible.
 *
 * The launch used to swallow the backend's refusal: the POST returned 422 and
 * the UI showed nothing, so the only place the reason appeared was the
 * backend's terminal — and clicking again just produced another 422.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import NewRun from '@/pages/NewRun'
import { resetConnectionState } from '@/lib/api'

const BACKEND = 'http://127.0.0.1:8765/api/v1'

const jsonResponse = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

const emptyHealth = {
  status: 'ok',
  mode: 'auto',
  providers: { google_ai: false, openrouter: false },
  docker_available: true,
  require_docker: true,
  bifrost: { enabled: true, gateway_url: 'http://localhost:8080', reachable: true, status: 'connected' },
}

const MOCK_BENCHES = [
  {
    id: 'python-core',
    name: 'Python Fundamentals',
    description: 'Core Python',
    task_count: 2,
    categories: ['Fundamentals'],
    difficulty_mix: { easy: 1, medium: 1, hard: 0, expert: 0 },
    total_time_limit_sec: 240,
    version: 'v1.3',
    tags: ['python'],
    created_at: '2026-01-01T00:00:00Z',
  },
]

const MOCK_TASKS = [
  {
    id: 'python-core-t01',
    benchmark_id: 'python-core',
    title: 'Palindrome',
    category: 'Fundamentals',
    difficulty: 'easy',
    prompt: 'p1',
    test_count: 3,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: [],
    reference_solution_lines: 10,
  },
  {
    id: 'python-core-t02',
    benchmark_id: 'python-core',
    title: 'FizzBuzz',
    category: 'Algorithms',
    difficulty: 'medium',
    prompt: 'p2',
    test_count: 5,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: [],
    reference_solution_lines: 10,
  },
]

const MOCK_AGENTS = [
  {
    id: 'atlas-coder',
    name: 'Atlas Coder',
    model: 'gemini-2.5-pro',
    model_provider: 'Google AI',
    description: 'generalist',
    system_prompt_version: 'sys-2.4.1',
    tools: [],
    orchestration: 'ReAct',
    memory: 'scratch',
    color_index: 0,
    enabled: true,
    cost_per_1k_input: 0.001,
    cost_per_1k_output: 0.01,
    registered_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'nova-coder',
    name: 'Nova Coder',
    model: 'gemini-2.5-flash',
    model_provider: 'Google AI',
    description: 'planner',
    system_prompt_version: 'sys-2.4.1',
    tools: [],
    orchestration: 'Plan-Act-Verify',
    memory: 'scratch',
    color_index: 1,
    enabled: true,
    cost_per_1k_input: 0.0001,
    cost_per_1k_output: 0.0004,
    registered_at: '2026-01-01T00:00:00Z',
  },
]

const routedFetch = (opts: {
  createRun?: () => Promise<unknown>
  health?: () => Promise<unknown>
}) =>
  vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/health')) return jsonResponse(opts.health ? await opts.health() : emptyHealth)
    if (u.includes('/runs') && init?.method === 'POST') {
      const body = opts.createRun
        ? await opts.createRun()
        : { detail: 'live docker isolation requires Docker. Start Docker, or set BIFROST_ALLOW_HOST_SANDBOX=1.' }
      return jsonResponse(body, 422)
    }
    if (u.includes('/benchmarks')) return jsonResponse(MOCK_BENCHES)
    if (u.includes('/tasks')) return jsonResponse(MOCK_TASKS)
    if (u.includes('/agents')) return jsonResponse(MOCK_AGENTS)
    if (u.includes('/runs')) return jsonResponse([])
    return jsonResponse({})
  })

/** Walk the stepper to the final review step once catalogue is ready. */
const goToReview = async () => {
  // Wait for catalogue so Continue is enabled
  await waitFor(() => expect(screen.getByTestId('newrun-task-picker')).toBeInTheDocument())
  for (let i = 0; i < 3; i += 1) {
    const cont = await screen.findByRole('button', { name: /continue/i })
    expect(cont).not.toBeDisabled()
    await userEvent.click(cont)
  }
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /launch benchmark/i })).toBeInTheDocument(),
  )
}

describe('New run — launch errors', () => {
  beforeEach(() => {
    resetConnectionState()
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('shows the backend reason when the run is rejected', async () => {
    vi.stubGlobal('fetch', routedFetch({}))

    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await goToReview()
    await userEvent.click(screen.getByRole('button', { name: /launch benchmark/i }))

    await waitFor(() =>
      expect(screen.getByText(/The run was not created/)).toBeInTheDocument(),
    )
    // The backend's own explanation — not a raw JSON blob.
    expect(screen.getByText(/live docker isolation requires Docker/)).toBeInTheDocument()
    expect(screen.queryByText(/"detail"/)).not.toBeInTheDocument()
  })

  it('warns before launching when Docker is unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      routedFetch({
        health: async () => ({ ...emptyHealth, docker_available: false }),
      }),
    )

    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(screen.getByText(/Docker is not available on the backend host/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/rejected with HTTP 422/)).toBeInTheDocument()
  })

  it('warns when the Bifrost gateway is not ready', async () => {
    vi.stubGlobal(
      'fetch',
      routedFetch({
        health: async () => ({
          ...emptyHealth,
          bifrost: {
            enabled: true,
            gateway_url: 'http://localhost:8080',
            reachable: true,
            authenticated: false,
            status: 'auth_error',
            error: 'Gateway reachable at http://localhost:8080 but rejected our credentials (HTTP 401).',
          },
        }),
      }),
    )

    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(screen.getByText(/Bifrost gateway is not ready/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/rejected our credentials/)).toBeInTheDocument()
  })

  it('offers a one-click switch to subprocess isolation when Docker is missing', async () => {
    vi.stubGlobal(
      'fetch',
      routedFetch({
        health: async () => ({ ...emptyHealth, docker_available: false }),
      }),
    )

    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(screen.getByText(/Docker is not available on the backend host/)).toBeInTheDocument(),
    )

    await userEvent.click(screen.getByRole('button', { name: /switch to subprocess isolation/i }))

    // The warning disappears as soon as the run is no longer asking for docker.
    await waitFor(() =>
      expect(screen.queryByText(/Docker is not available on the backend host/)).not.toBeInTheDocument(),
    )
  })

  it('does not warn about Docker when it is available', async () => {
    vi.stubGlobal('fetch', routedFetch({}))

    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText(/Benchmarking/)).toBeInTheDocument())
    expect(screen.queryByText(/Docker is not available/)).not.toBeInTheDocument()
  })
})
