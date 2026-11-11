/**
 * Regression test: the dashboard must render when the backend has no runs yet.
 *
 * The API returns null for every average it cannot compute (no completed
 * runs). Those nulls used to reach `.toFixed()` and crash the whole page —
 * taking the connection badge in the top bar with it.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '@/pages/Dashboard'
import { setDataSource } from '@/lib/api'

const BACKEND = 'http://127.0.0.1:8765/api/v1'

const emptyDashboard = {
  stats: {
    total_runs: 0,
    completed_runs: 0,
    tasks_executed: 0,
    total_agent_executions: 0,
    total_cost_usd: 0,
    total_tokens: 0,
    avg_overall_score: null,
    avg_cost_per_run: null,
    avg_execution_time_sec: null,
    fairness_score: null,
  },
  recent_runs: [],
  leaderboard: [],
  score_trend: [],
  cost_by_benchmark: [],
  analytics: { comparison: { agents: [] }, recovery: { failures_by_category: [] } },
  data_source: 'stored_runs',
  demo_data: false,
}

const jsonResponse = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

describe('Dashboard with an empty workspace', () => {
  beforeEach(() => {
    setDataSource('live')
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('renders instead of crashing on null metrics', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/dashboard')) return jsonResponse(emptyDashboard)
        if (String(url).includes('/runs')) return jsonResponse([])
        return jsonResponse({})
      }),
    )

    const { container } = render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Avg overall score')).toBeInTheDocument())
    // The null average is rendered as a dash, not NaN and not a crash.
    expect(container.textContent).toContain('—/100')
    expect(container.textContent).toContain('— avg per run')
    expect(screen.getByText('No completed benchmark data yet.')).toBeInTheDocument()
  })
})
