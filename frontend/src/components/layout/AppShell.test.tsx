/**
 * The top bar badge must reflect the *measured* connection, never the
 * demo-mode flag. It used to render "LIVE DATA" whenever mock mode was off —
 * which is true even with no backend running.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { resetConnectionState, setDataSource } from '@/lib/api'

const BACKEND = 'http://127.0.0.1:8765/api/v1'

const jsonResponse = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

const topbar = () => screen.getByText(/^(LIVE DATA|DEMO DATA|BACKEND OFFLINE|CHECKING)$/)

describe('AppShell connection badge', () => {
  beforeEach(() => {
    resetConnectionState()
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('shows LIVE DATA when the backend answers and the data is live', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/gateway/status')) {
          return jsonResponse({
            enabled: true,
            gateway_url: 'http://localhost:8080',
            reachable: true,
            authenticated: true,
            model_call_path_ok: true,
            status: 'connected',
            error: null,
            providers: [],
            models: [],
            version: null,
            latency_ms: 1,
          })
        }
        return jsonResponse({ status: 'ok' })
      }),
    )

    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    )

    await waitFor(() => expect(topbar().textContent).toBe('LIVE DATA'))
  })

  it('shows BACKEND OFFLINE when the backend cannot be reached', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )

    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    )

    await waitFor(() => expect(topbar().textContent).toBe('BACKEND OFFLINE'))
    // It must never claim a live connection while the backend is down.
    expect(screen.queryByText('LIVE DATA')).not.toBeInTheDocument()
  })

  it('shows DEMO DATA when the backend is up but the data is the fixture catalogue', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/gateway/status')) {
          return jsonResponse({
            enabled: true,
            gateway_url: 'http://localhost:8080',
            reachable: true,
            authenticated: true,
            model_call_path_ok: true,
            status: 'connected',
            error: null,
            providers: [],
            models: [],
            version: null,
            latency_ms: 1,
          })
        }
        return jsonResponse({ status: 'ok' })
      }),
    )
    // The dashboard fell back to the bundled fixtures.
    setDataSource('demo')

    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    )

    await waitFor(() => expect(topbar().textContent).toBe('DEMO DATA'))
    expect(screen.queryByText('LIVE DATA')).not.toBeInTheDocument()
  })
})
