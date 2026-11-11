import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getDataSource,
  probeBackend,
  subscribeDataSource,
  type BackendHealth,
  type BackendState,
  type DataSource,
  type HealthCheckResult,
} from '@/lib/api'

export interface BackendHealthState {
  /** `checking` until the first probe completes. It is never `connected` by default. */
  state: BackendState
  detail: BackendHealth | null
  error: string | null
  latencyMs: number | null
  checking: boolean
  /** Timestamp of the last completed probe. */
  checkedAt: number | null
  /** Perform a fresh live probe now. */
  refresh: () => Promise<HealthCheckResult>
}

/**
 * Tracks the real backend connection.
 *
 * The state starts as `checking` and only becomes `connected` after an actual
 * HTTP health request succeeds. A failed probe clears any previous detail and
 * reports `disconnected` with the reason, so a stale "connected" badge can
 * never survive a backend that went away.
 */
export function useBackendHealth(options?: {
  intervalMs?: number
  enabled?: boolean
}): BackendHealthState {
  const intervalMs = options?.intervalMs ?? 15_000
  const enabled = options?.enabled ?? true

  const [state, setState] = useState<BackendState>('checking')
  const [detail, setDetail] = useState<BackendHealth | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkedAt, setCheckedAt] = useState<number | null>(null)
  const aliveRef = useRef(true)

  const refresh = useCallback(async (): Promise<HealthCheckResult> => {
    setChecking(true)
    const result = await probeBackend()
    if (aliveRef.current) {
      setState(result.state)
      setDetail(result.detail)
      setError(result.error)
      setLatencyMs(result.latencyMs)
      setCheckedAt(result.checkedAt)
      setChecking(false)
    }
    return result
  }, [])

  useEffect(() => {
    aliveRef.current = true
    if (!enabled) return () => { aliveRef.current = false }

    void refresh()
    const id = setInterval(() => {
      // Skip polling while the tab is hidden — the next tick will catch up.
      if (typeof document !== 'undefined' && document.hidden) return
      void refresh()
    }, intervalMs)

    return () => {
      aliveRef.current = false
      clearInterval(id)
    }
  }, [enabled, intervalMs, refresh])

  return { state, detail, error, latencyMs, checking, checkedAt, refresh }
}

/** Tracks whether the data on screen came from the live API or the fixtures. */
export function useDataSource(): DataSource {
  const [source, setSource] = useState<DataSource>(getDataSource())
  useEffect(() => subscribeDataSource(setSource), [])
  return source
}
