/**
 * Phase 5 — the Settings page must report the truth about connectivity.
 *
 * Three independent indicators are rendered:
 *   1. Backend      — Connected / Disconnected / Checking (from a real probe)
 *   2. Data source  — Live API / Demo fixtures
 *   3. Bifrost      — Connected / Unreachable / Authentication error / Unknown
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Settings from '@/pages/Settings'
import { setDataSource } from '@/lib/api'

const BACKEND = 'http://127.0.0.1:8765/api/v1'

const gatewayPayload = (over: Record<string, unknown> = {}) => ({
  enabled: true,
  gateway_url: 'http://localhost:8080',
  reachable: true,
  authenticated: true,
  model_call_path_ok: true,
  status: 'connected',
  error: null,
  providers: ['gemini'],
  models: ['gemini/gemini-2.5-pro'],
  version: '1.0.0',
  latency_ms: 7,
  ...over,
})

const jsonResponse = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

/** Routes the mocked fetch by URL so health and gateway calls differ. */
const routedFetch = (routes: {
  health?: () => Promise<unknown>
  gateway?: () => Promise<unknown>
}) =>
  vi.fn(async (url: string) => {
    if (String(url).includes('/health')) {
      const body = routes.health ? await routes.health() : { status: 'ok' }
      return jsonResponse(body)
    }
    if (String(url).includes('/gateway/status')) {
      const body = routes.gateway ? await routes.gateway() : gatewayPayload()
      return jsonResponse(body)
    }
    return jsonResponse({})
  })

/** The card whose title matches, so indicators are checked in isolation. */
const card = (title: string): HTMLElement => {
  const heading = screen.getByText(title)
  const section = heading.closest('section')
  if (!section) throw new Error(`card "${title}" not found`)
  return section as HTMLElement
}

/** Every badge label inside a card (badges carry the status text). */
const badges = (root: HTMLElement): string[] =>
  Array.from(root.querySelectorAll('.badge')).map((b) => (b.textContent ?? '').trim())

/** How many badges in the card start with this label. */
const badgeCount = (root: HTMLElement, label: string): number =>
  badges(root).filter((t) => t.startsWith(label)).length

describe('Settings connection indicators', () => {
  beforeEach(() => {
    setDataSource('live')
    vi.stubEnv('VITE_API_BASE_URL', BACKEND)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('shows Connected and Live API when the backend answers', async () => {
    vi.stubGlobal('fetch', routedFetch({}))

    render(<Settings />)

    await waitFor(() => expect(badgeCount(card('Backend connection'), 'Connected')).toBe(1))
    expect(badgeCount(card('Backend connection'), 'Live API')).toBe(1)
    expect(badgeCount(card('Backend connection'), 'Demo fixtures')).toBe(0)
    expect(badgeCount(card('Maxim AI Bifrost gateway'), 'Connected')).toBe(1)
  })

  it('shows Disconnected and Demo fixtures when the backend is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )

    render(<Settings />)

    await waitFor(() => expect(badgeCount(card('Backend connection'), 'Disconnected')).toBe(1))
    expect(badgeCount(card('Backend connection'), 'Demo fixtures')).toBe(1)
    expect(badgeCount(card('Backend connection'), 'Live API')).toBe(0)
    // The gateway state cannot be known when the backend is down.
    expect(badgeCount(card('Maxim AI Bifrost gateway'), 'Unknown')).toBe(1)
    expect(card('Maxim AI Bifrost gateway').textContent ?? '').toMatch(/Backend unreachable/)
  })

  it('shows Unreachable when the backend reports the gateway is down', async () => {
    vi.stubGlobal(
      'fetch',
      routedFetch({
        gateway: async () =>
          gatewayPayload({
            reachable: false,
            authenticated: false,
            model_call_path_ok: false,
            status: 'unreachable',
            error: 'Connection refused to http://localhost:8080',
            providers: [],
            models: [],
            latency_ms: null,
          }),
      }),
    )

    render(<Settings />)

    await waitFor(() => expect(badgeCount(card('Maxim AI Bifrost gateway'), 'Unreachable')).toBe(1))
    expect(card('Maxim AI Bifrost gateway').textContent ?? '').toMatch(/Connection refused/)
    // The backend itself is still fine.
    expect(badgeCount(card('Backend connection'), 'Connected')).toBe(1)
  })

  it('shows Authentication error when the gateway rejects the key', async () => {
    vi.stubGlobal(
      'fetch',
      routedFetch({
        gateway: async () =>
          gatewayPayload({
            reachable: true,
            authenticated: false,
            model_call_path_ok: false,
            status: 'auth_error',
            error: '401 Unauthorized — invalid Bifrost API key',
          }),
      }),
    )

    render(<Settings />)

    await waitFor(() =>
      expect(badgeCount(card('Maxim AI Bifrost gateway'), 'Authentication error')).toBe(1),
    )
    expect(card('Maxim AI Bifrost gateway').textContent ?? '').toMatch(/401 Unauthorized/)
  })

  it('re-runs the live checks when Refresh is clicked', async () => {
    const fetchMock = routedFetch({})
    vi.stubGlobal('fetch', fetchMock)

    render(<Settings />)
    await waitFor(() => expect(badgeCount(card('Backend connection'), 'Connected')).toBe(1))

    const before = fetchMock.mock.calls.length
    const refresh = screen.getAllByRole('button', { name: /refresh/i })[0]
    await userEvent.click(refresh)

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before))
    const healthCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/health'))
    const gatewayCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/gateway/status'))
    expect(healthCalls.length).toBeGreaterThan(1)
    expect(gatewayCalls.length).toBeGreaterThan(1)
  })

  it('performs a real connectivity test when Test is clicked', async () => {
    vi.stubGlobal('fetch', routedFetch({}))

    render(<Settings />)
    await waitFor(() => expect(badgeCount(card('Backend connection'), 'Connected')).toBe(1))

    await userEvent.click(screen.getByRole('button', { name: /^test$/i }))

    await waitFor(() =>
      expect(card('Backend connection').textContent ?? '').toMatch(/OK — backend answered in/),
    )
  })

  it('reports a failing connectivity test instead of a stale Connected badge', async () => {
    let healthy = true
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (!healthy) throw new TypeError('Failed to fetch')
        if (String(url).includes('/gateway/status')) return jsonResponse(gatewayPayload())
        return jsonResponse({ status: 'ok' })
      }),
    )

    render(<Settings />)
    await waitFor(() => expect(badgeCount(card('Backend connection'), 'Connected')).toBe(1))

    healthy = false
    await userEvent.click(screen.getByRole('button', { name: /^test$/i }))

    await waitFor(() => expect(badgeCount(card('Backend connection'), 'Disconnected')).toBe(1))
    expect(badgeCount(card('Backend connection'), 'Connected')).toBe(0)
    expect(card('Backend connection').textContent ?? '').toMatch(/Failed to fetch|Cannot reach/)
  })
})
