import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Tasks from './Tasks'
import type { Benchmark, Task } from '@/types'

const BENCHES: Benchmark[] = [
  {
    id: 'python-core',
    name: 'Python Fundamentals',
    description: 'Core Python competency',
    task_count: 3,
    categories: ['Fundamentals', 'Algorithms'],
    difficulty_mix: { easy: 1, medium: 1, hard: 1, expert: 0 },
    total_time_limit_sec: 360,
    version: 'v1.3',
    tags: ['python'],
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'debug-suite',
    name: 'Debugging & Fixes',
    description: 'Fault localisation',
    task_count: 2,
    categories: ['Sorting'],
    difficulty_mix: { easy: 1, medium: 1, hard: 0, expert: 0 },
    total_time_limit_sec: 240,
    version: 'v1.1',
    tags: ['debug'],
    created_at: '2026-01-01T00:00:00Z',
  },
]

const TASKS: Task[] = [
  {
    id: 'python-core-t01',
    benchmark_id: 'python-core',
    title: 'Write a Python palindrome function',
    category: 'Fundamentals',
    difficulty: 'easy',
    prompt:
      'Implement the following in Python 3.11. Write the code to `solution.py`.\n\nWrite a Python palindrome function.\n\nReturn true if the string is a palindrome.',
    test_count: 3,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: ['fundamentals', 'easy'],
    reference_solution_lines: 12,
  },
  {
    id: 'python-core-t02',
    benchmark_id: 'python-core',
    title: 'Implement FizzBuzz with a twist',
    category: 'Algorithms',
    difficulty: 'medium',
    prompt: 'FizzBuzz full prompt that must remain visible in the detail modal without truncation of the only copy.',
    test_count: 5,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: ['algorithms', 'medium'],
    reference_solution_lines: 19,
  },
  {
    id: 'python-core-t03',
    benchmark_id: 'python-core',
    title: 'Hard matrix task',
    category: 'Algorithms',
    difficulty: 'hard',
    prompt: 'Hard prompt body',
    test_count: 8,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: ['algorithms', 'hard'],
    reference_solution_lines: 26,
  },
  {
    id: 'debug-suite-t01',
    benchmark_id: 'debug-suite',
    title: 'Debug a broken bubble sort',
    category: 'Sorting',
    difficulty: 'easy',
    prompt: 'Debug prompt',
    test_count: 3,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: ['sorting', 'easy'],
    reference_solution_lines: 12,
  },
  {
    id: 'debug-suite-t02',
    benchmark_id: 'debug-suite',
    title: 'Debug LRU cache',
    category: 'Sorting',
    difficulty: 'medium',
    prompt: 'LRU prompt',
    test_count: 5,
    time_limit_sec: 120,
    max_tokens: 32000,
    tags: ['sorting', 'medium'],
    reference_solution_lines: 19,
  },
]

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      listBenchmarks: vi.fn(async () => BENCHES),
      listTasks: vi.fn(async () => TASKS),
      getTask: vi.fn(async (id: string) => {
        const t = TASKS.find((x) => x.id === id)
        if (!t) throw new Error('not found')
        return t
      }),
    },
    getDataSource: () => 'live' as const,
    subscribeDataSource: () => () => {},
  }
})

function renderTasks() {
  return render(
    <MemoryRouter>
      <Tasks />
    </MemoryRouter>,
  )
}

describe('Tasks explorer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders every benchmark card with name, version and task count', async () => {
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('benchmark-card-python-core')).toBeInTheDocument())
    expect(screen.getByTestId('benchmark-card-debug-suite')).toBeInTheDocument()
    expect(screen.getByTestId('bench-task-count-python-core')).toHaveTextContent('3 tasks')
    expect(screen.getByTestId('bench-task-count-debug-suite')).toHaveTextContent('2 tasks')
    // Scope to each card so duplicate page text does not collide
    const pyCard = screen.getByTestId('benchmark-card-python-core')
    expect(within(pyCard).getByText('Python Fundamentals')).toBeInTheDocument()
    expect(within(pyCard).getByText('v1.3')).toBeInTheDocument()
    expect(screen.getByTestId('catalogue-counts')).toHaveTextContent('2 benchmarks · 5 tasks')
  })

  it('opens task detail and shows the full untruncated prompt', async () => {
    const user = userEvent.setup()
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('task-row-python-core-t01')).toBeInTheDocument())
    await user.click(screen.getByTestId('view-task-python-core-t01'))
    const modal = await screen.findByTestId('task-detail-modal')
    expect(modal).toBeInTheDocument()
    const prompt = screen.getByTestId('task-full-prompt')
    expect(prompt.textContent).toContain('Return true if the string is a palindrome')
    expect(prompt.textContent).toContain('Implement the following in Python 3.11')
    // Full prompt, not truncated copy
    expect(prompt.textContent).toBe(TASKS[0].prompt)
    expect(within(modal).getByText('python-core-t01')).toBeInTheDocument()
    expect(within(modal).getByText('Fundamentals')).toBeInTheDocument()
  })

  it('filters by difficulty and updates result count', async () => {
    const user = userEvent.setup()
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('task-row-python-core-t01')).toBeInTheDocument())
    await user.click(screen.getByTestId('filter-diff-easy'))
    expect(screen.getByTestId('filter-result-count')).toHaveTextContent('Showing 2 matches')
    expect(screen.getByTestId('task-row-python-core-t01')).toBeInTheDocument()
    expect(screen.queryByTestId('task-row-python-core-t02')).not.toBeInTheDocument()
  })

  it('filters by search query', async () => {
    const user = userEvent.setup()
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('task-search')).toBeInTheDocument())
    await user.type(screen.getByTestId('task-search'), 'palindrome')
    await waitFor(() => {
      expect(screen.getByTestId('task-row-python-core-t01')).toBeInTheDocument()
      expect(screen.queryByTestId('task-row-python-core-t02')).not.toBeInTheDocument()
    })
  })

  it('filters by benchmark card click', async () => {
    const user = userEvent.setup()
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('benchmark-card-debug-suite')).toBeInTheDocument())
    // The card element itself is the interactive button
    await user.click(screen.getByTestId('benchmark-card-debug-suite'))
    await waitFor(() => {
      expect(screen.getByTestId('task-row-debug-suite-t01')).toBeInTheDocument()
      expect(screen.queryByTestId('task-row-python-core-t01')).not.toBeInTheDocument()
    })
  })

  it('shows empty state when filters match nothing', async () => {
    const user = userEvent.setup()
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('task-search')).toBeInTheDocument())
    await user.type(screen.getByTestId('task-search'), 'zzznomatchzzz')
    await waitFor(() => expect(screen.getByText('No tasks match')).toBeInTheDocument())
  })

  it('supports keyboard activation of a task row', async () => {
    const user = userEvent.setup()
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('task-row-python-core-t02')).toBeInTheDocument())
    const row = screen.getByTestId('task-row-python-core-t02')
    row.focus()
    await user.keyboard('{Enter}')
    const modal = await screen.findByTestId('task-detail-modal')
    expect(within(modal).getByTestId('task-full-prompt').textContent).toBe(TASKS[1].prompt)
  })

  it('shows live data source banner when not in demo mode', async () => {
    renderTasks()
    await waitFor(() => expect(screen.getByTestId('data-source-banner')).toBeInTheDocument())
    expect(screen.getByTestId('data-source-banner')).toHaveTextContent(/Live catalogue/i)
  })
})
