import { useCallback, useEffect, useRef, useState } from 'react'
import { getDataSource, subscribeDataSource } from '@/lib/api'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  /** True when the current data came from the bundled fixtures, not the live API. */
  mock: boolean
  reload: () => void
}

/**
 * Fetch-on-mount hook with a manual reload handle. Keeps the previous
 * value visible while refetching so charts don't flash empty.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mock, setMock] = useState(getDataSource() === 'demo')
  const [nonce, setNonce] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  // Follow the API client's data source so a fallback to fixtures is visible
  // even when the request itself succeeded.
  useEffect(() => subscribeDataSource((s) => setMock(s === 'demo')), [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    loaderRef
      .current()
      .then((res) => {
        if (!alive) return
        setData(res)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!alive) return
        setError(err instanceof Error ? err.message : 'Unexpected error')
      })
      .finally(() => {
        if (!alive) return
        setLoading(false)
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  return { data, loading, error, mock, reload }
}

/** Polls a loader on an interval, pausing when the tab is hidden. */
export function usePolling<T>(loader: () => Promise<T>, intervalMs = 4000): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mock, setMock] = useState(getDataSource() === 'demo')
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => subscribeDataSource((s) => setMock(s === 'demo')), [])

  const tick = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return
    try {
      const res = await loaderRef.current()
      setData(res)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void tick()
    const id = setInterval(() => void tick(), intervalMs)
    return () => clearInterval(id)
  }, [tick, intervalMs])

  const reload = useCallback(() => void tick(), [tick])

  return { data, loading, error, mock, reload }
}

/** Persisted state in localStorage (fairness config, UI prefs, ...). */
export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? ({ ...initial, ...JSON.parse(raw) } as T) : initial
    } catch {
      return initial
    }
  })

  const set = useCallback(
    (v: T) => {
      setValue(v)
      try {
        localStorage.setItem(key, JSON.stringify(v))
      } catch {
        /* storage unavailable — ignore */
      }
    },
    [key],
  )

  return [value, set]
}
