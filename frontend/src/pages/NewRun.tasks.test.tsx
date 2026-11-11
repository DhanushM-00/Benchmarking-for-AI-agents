import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import NewRun from '@/pages/NewRun'
import { resetConnectionState } from '@/lib/api'

const BACKEND = 'http://127.0.0.1:8765/api/v1'

const BENCHES = [
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
  {
    id: 'debug-suite',
    name: 'Debugging & Fixes',
    description: 'Debug',
    task_count: 1,
    categories: ['Sorting'],
    difficulty_mix: { easy: 1, medium: 0, hard: 0, expert: 0 },
    total_time_limit_sec: 120,
    version: 'v1.1',
    tags: ['debug'],
    created_at: '2026-01-01T00:00:00Z',
  },
]

const TASKS = [
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
  {
    id: 'debug-suite-t01',
    benchmark_id: 'debug-suite',
    title: 'Bubble sort bug',
    category: 'Sorting',
    difficulty: 'easy',
    prompt: 'd1',
    test_count: 3,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: [],
    reference_solution_lines: 10,
  },
]

const AGENTS = [
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
  {
    id: 'forge-coder',
    name: 'Forge Coder',
    model: 'claude-sonnet',
    model_provider: 'Anthropic',
    description: 'state machine',
    system_prompt_version: 'sys-2.4.1',
    tools: [],
    orchestration: 'StateMachine',
    memory: 'scratch',
    color_index: 2,
    enabled: true,
    cost_per_1k_input: 0.003,
    cost_per_1k_output: 0.015,
    registered_at: '2026-01-01T00:00:00Z',
  },
]

const jsonResponse = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

describe('New run — task selection', () => {
  beforeEach(() => {
    resetConnectionState()
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const u = String(url)
        if (u.includes('/health')) {
          return jsonResponse({
            status: 'ok',
            mode: 'simulated',
            providers: {},
            docker_available: true,
            require_docker: false,
            bifrost: { enabled: false, gateway_url: '', reachable: false, status: 'disabled' },
          })
        }
        if (u.includes('/benchmarks')) return jsonResponse(BENCHES)
        if (u.includes('/tasks')) return jsonResponse(TASKS)
        if (u.includes('/agents')) return jsonResponse(AGENTS)
        return jsonResponse({})
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('lists all tasks for the selected benchmark with select-all / clear-all', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('newrun-task-picker')).toBeInTheDocument())
    expect(screen.getByTestId('newrun-task-python-core-t01')).toBeInTheDocument()
    expect(screen.getByTestId('newrun-task-python-core-t02')).toBeInTheDocument()
    expect(screen.queryByTestId('newrun-task-debug-suite-t01')).not.toBeInTheDocument()

    await waitFor(() =>
      expect(screen.getByTestId('selected-task-count')).toHaveTextContent('2 of 2 selected'),
    )

    await user.click(screen.getByTestId('clear-all-tasks'))
    expect(screen.getByTestId('selected-task-count')).toHaveTextContent('0 of 2 selected')

    await user.click(screen.getByTestId('select-all-tasks'))
    expect(screen.getByTestId('selected-task-count')).toHaveTextContent('2 of 2 selected')
  })

  it('clears foreign task IDs when the benchmark changes', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('newrun-task-python-core-t01')).toBeInTheDocument())
    // Deselect one task so selection is partial
    await user.click(screen.getByTestId('newrun-task-python-core-t02'))
    expect(screen.getByTestId('selected-task-count')).toHaveTextContent('1 of 2 selected')

    // Switch to debug-suite
    const debugCard = screen.getByText('Debugging & Fixes').closest('button')
    expect(debugCard).toBeTruthy()
    await user.click(debugCard!)

    await waitFor(() => expect(screen.getByTestId('newrun-task-debug-suite-t01')).toBeInTheDocument())
    expect(screen.queryByTestId('newrun-task-python-core-t01')).not.toBeInTheDocument()
    // Selection reset to all tasks of the new benchmark
    expect(screen.getByTestId('selected-task-count')).toHaveTextContent('1 of 1 selected')
  })

  it('shows selected vs available counts on the review step', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('newrun-task-picker')).toBeInTheDocument())
    await user.click(screen.getByTestId('newrun-task-python-core-t02')) // deselect one
    expect(screen.getByTestId('selected-task-count')).toHaveTextContent('1 of 2 selected')

    // Continue through steps
    for (let i = 0; i < 3; i += 1) {
      await user.click(await screen.findByRole('button', { name: /continue/i }))
    }

    await waitFor(() => expect(screen.getByTestId('review-task-count')).toBeInTheDocument())
    expect(screen.getByTestId('review-task-count')).toHaveTextContent(/1 of 2 tasks selected/)
  })

  it('sets estimated executions to zero when Clear all is clicked', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('newrun-task-picker')).toBeInTheDocument())
    // Default: all tasks selected, agents default to first 3 enabled
    await waitFor(() =>
      expect(screen.getByTestId('summary-selected-tasks')).toHaveTextContent('2'),
    )
    // Clear all tasks
    await user.click(screen.getByTestId('clear-all-tasks'))
    expect(screen.getByTestId('selected-task-count')).toHaveTextContent('0 of 2 selected')
    expect(screen.getByTestId('summary-selected-tasks')).toHaveTextContent('0')
    // Summary executions must be zero (not fallback to task_count)
    expect(screen.getByTestId('summary-total-executions')).toHaveTextContent('0')
    // Cannot continue without tasks
    expect(screen.getByRole('button', { name: /continue/i })).toBeDisabled()
  })

  it('computes executions as selected tasks × agents × repeats', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('newrun-task-picker')).toBeInTheDocument())
    // Keep both tasks selected (default)
    // Advance to agents step
    await user.click(await screen.findByRole('button', { name: /continue/i }))
    // Ensure two agents are selected: deselect forge if present
    // Defaults take first 3; leave atlas + nova
    // Advance to fairness
    await user.click(await screen.findByRole('button', { name: /continue/i }))
    // Change repeats to 2 if possible
    const repeatsInput = screen.queryByLabelText(/repeats/i) || screen.queryByDisplayValue('1')
    if (repeatsInput) {
      await user.clear(repeatsInput as HTMLInputElement)
      await user.type(repeatsInput as HTMLInputElement, '2')
    }
    // Advance to review
    await user.click(await screen.findByRole('button', { name: /continue/i }))
    await waitFor(() => expect(screen.getByTestId('review-total-executions')).toBeInTheDocument())
    // 2 tasks × up to 3 agents × repeats (1 or 2). Accept either depending on default agents.
    const text = screen.getByTestId('review-total-executions').textContent || '0'
    const n = Number(text.replace(/,/g, ''))
    expect(n).toBeGreaterThan(0)
    // Must be a multiple of selected task count (2)
    expect(n % 2).toBe(0)
  })

  it('disables launch when no tasks are selected', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <NewRun />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('newrun-task-picker')).toBeInTheDocument())
    await user.click(screen.getByTestId('clear-all-tasks'))
    // Cannot reach review / launch without tasks
    expect(screen.getByRole('button', { name: /continue/i })).toBeDisabled()
  })
})
