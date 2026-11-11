// @vitest-environment node
/**
 * Phase 5 — live end-to-end scenarios driven through the *frontend* code.
 *
 * A real `uvicorn` process is started, stopped and restarted while
 * `probeBackend()` — the exact function the dashboard uses — decides what the
 * UI should show. This is the path that used to lie: the dashboard reported
 * "connected" from a flag instead of an HTTP response.
 *
 *   A  backend up, gateway up        → connected
 *   B  backend down                  → disconnected
 *   C  backend up, gateway down      → connected (the backend is fine)
 *   D  gateway rejects the key       → connected + gateway auth error
 *   E  backend stopped then restarted → disconnected, then connected
 */
import { describe, it, expect, afterEach, afterAll, vi } from 'vitest'
import { spawn, type ChildProcess } from 'node:child_process'
import net from 'node:net'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import fs from 'node:fs'
import { probeBackend, getDataSource, setDataSource, api } from '@/lib/api'

const BACKEND_DIR = path.resolve(__dirname, '../../../backend')
// Works on Windows (.myenv\Scripts\python.exe) and Linux/macOS (.venv/bin/python).
function resolvePython(): string {
  if (process.env.BIFROST_TEST_PYTHON) return process.env.BIFROST_TEST_PYTHON
  for (const venv of ['.venv', '.myenv', 'venv']) {
    for (const rel of [['bin', 'python'], ['Scripts', 'python.exe']]) {
      const p = path.join(BACKEND_DIR, venv, ...rel)
      if (fs.existsSync(p)) return p
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}
const PYTHON = resolvePython()
const TMP_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'bifrost-scenario-'))

let backend: ChildProcess | null = null

const freePort = (): Promise<number> =>
  new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const port = (srv.address() as net.AddressInfo).port
      srv.close(() => resolve(port))
    })
  })

const portOpen = (port: number): Promise<boolean> =>
  new Promise((resolve) => {
    const s = net.connect({ port, host: '127.0.0.1' })
    s.on('connect', () => {
      s.destroy()
      resolve(true)
    })
    s.on('error', () => {
      s.destroy()
      resolve(false)
    })
    setTimeout(() => {
      s.destroy()
      resolve(false)
    }, 1000)
  })

interface BackendOpts {
  gatewayUrl?: string
  apiKey?: string
}

const startBackend = async (port: number, opts: BackendOpts = {}): Promise<void> => {
  backend = spawn(
    PYTHON,
    ['-m', 'uvicorn', 'app.main:app', '--port', String(port), '--log-level', 'warning'],
    {
      cwd: BACKEND_DIR,
      env: {
        ...process.env,
        BIFROST_MODE: 'simulated',
        BIFROST_DB: path.join(TMP_DIR, `scenario-${port}.db`),
        BIFROST_SEED_DEMO: '0',
        BIFROST_SIM_DELAY_MS: '0',
        BIFROST_ENABLED: '1',
        BIFROST_GATEWAY_URL: opts.gatewayUrl ?? 'http://127.0.0.1:9',
        BIFROST_API_KEY: opts.apiKey ?? 'sk-test-key',
      },
      stdio: 'ignore',
    },
  )

  const deadline = Date.now() + 40_000
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/v1/health`)
      if (r.ok) return
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error('backend did not start in time')
}

const stopBackend = async (): Promise<void> => {
  if (!backend) return
  const proc = backend
  backend = null
  // On Windows, kill the whole process tree so uvicorn workers release DB locks.
  if (process.platform === 'win32' && proc.pid) {
    try {
      spawn('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { stdio: 'ignore' })
    } catch {
      /* fall through */
    }
  } else {
    proc.kill('SIGTERM')
  }
  const exited = new Promise<void>((resolve) => {
    if (proc.exitCode !== null || proc.killed) {
      resolve()
      return
    }
    proc.once('exit', () => resolve())
  })
  await Promise.race([exited, new Promise((r) => setTimeout(r, 8_000))])
  if (proc.exitCode === null && !proc.killed) {
    try {
      proc.kill('SIGKILL')
    } catch {
      /* already gone */
    }
    await Promise.race([
      new Promise<void>((resolve) => proc.once('exit', () => resolve())),
      new Promise((r) => setTimeout(r, 3_000)),
    ])
  }
  // Give the OS a moment to release file handles (Windows SQLite + temp dirs).
  await new Promise((r) => setTimeout(r, process.platform === 'win32' ? 400 : 50))
}

/** Remove TMP_DIR with bounded retries so Windows EPERM does not fail the suite. */
const removeTempDir = async (): Promise<void> => {
  const maxAttempts = process.platform === 'win32' ? 8 : 3
  let lastErr: unknown
  for (let i = 0; i < maxAttempts; i += 1) {
    try {
      fs.rmSync(TMP_DIR, { recursive: true, force: true })
      return
    } catch (err) {
      lastErr = err
      await new Promise((r) => setTimeout(r, 200 * (i + 1)))
    }
  }
  // Surface the failure rather than silently ignoring it.
  throw lastErr instanceof Error
    ? lastErr
    : new Error(`Failed to remove temp dir ${TMP_DIR}: ${String(lastErr)}`)
}

afterAll(async () => {
  await stopBackend()
  await removeTempDir()
})

afterEach(async () => {
  await stopBackend()
  vi.unstubAllEnvs()
  setDataSource('live')
})

describe('live backend scenarios', () => {
  it('A — reports connected when the backend is up', async () => {
    const port = await freePort()
    await startBackend(port)
    vi.stubEnv('VITE_API_BASE_URL', `http://127.0.0.1:${port}/api/v1`)

    const res = await probeBackend()

    expect(res.state).toBe('connected')
    expect(res.ok).toBe(true)
    expect(res.error).toBeNull()
    expect(res.latencyMs).not.toBeNull()
    expect(getDataSource()).toBe('live')
  }, 60_000)

  it('B — reports disconnected when the backend is down', async () => {
    const port = await freePort()
    vi.stubEnv('VITE_API_BASE_URL', `http://127.0.0.1:${port}/api/v1`)

    const res = await probeBackend()

    expect(res.state).toBe('disconnected')
    expect(res.ok).toBe(false)
    expect(res.error).toContain('Cannot reach the backend')
    // The dashboard falls back to fixtures — and says so.
    expect(getDataSource()).toBe('demo')
  }, 30_000)

  it('C — stays connected when only the gateway is down', async () => {
    const port = await freePort()
    const deadGateway = await freePort()
    await startBackend(port, { gatewayUrl: `http://127.0.0.1:${deadGateway}` })
    vi.stubEnv('VITE_API_BASE_URL', `http://127.0.0.1:${port}/api/v1`)

    const res = await probeBackend()
    expect(res.state).toBe('connected')

    // The gateway is a separate indicator and reports its own failure.
    const gw = await api.gatewayStatus()
    expect(gw.status).toBe('unreachable')
    expect(gw.reachable).toBe(false)
    expect(gw.error).toBeTruthy()
  }, 60_000)

  it('D — reports an authentication error when the gateway rejects the key', async () => {
    // A gateway that answers, but refuses our credentials.
    const gateway = http.createServer((_req, res) => {
      res.writeHead(401, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'invalid virtual key' }))
    })
    await new Promise<void>((resolve) => gateway.listen(0, '127.0.0.1', resolve))
    const gatewayPort = (gateway.address() as net.AddressInfo).port

    try {
      const port = await freePort()
      await startBackend(port, {
        gatewayUrl: `http://127.0.0.1:${gatewayPort}`,
        apiKey: 'sk-invalid-key',
      })
      vi.stubEnv('VITE_API_BASE_URL', `http://127.0.0.1:${port}/api/v1`)

      // The backend is fine — only the gateway credentials are wrong.
      expect((await probeBackend()).state).toBe('connected')

      const gw = await api.gatewayStatus()
      expect(gw.status).toBe('auth_error')
      expect(gw.reachable).toBe(true)
      expect(gw.authenticated).toBe(false)
      expect(gw.error).toContain('401')
    } finally {
      await new Promise<void>((resolve) => gateway.close(() => resolve()))
    }
  }, 60_000)

  it('E — recovers after the backend is restarted', async () => {
    const port = await freePort()
    await startBackend(port)
    vi.stubEnv('VITE_API_BASE_URL', `http://127.0.0.1:${port}/api/v1`)

    expect((await probeBackend()).state).toBe('connected')

    await stopBackend()
    await new Promise((r) => setTimeout(r, 500))
    expect(await portOpen(port)).toBe(false)

    const down = await probeBackend()
    expect(down.state).toBe('disconnected')
    expect(getDataSource()).toBe('demo')

    await startBackend(port)
    const up = await probeBackend()
    expect(up.state).toBe('connected')
    expect(getDataSource()).toBe('live')
  }, 90_000)
})
