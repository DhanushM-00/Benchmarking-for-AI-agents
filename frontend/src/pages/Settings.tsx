import { useCallback, useEffect, useState } from 'react'
import {
  Database,
  Plug,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  Sliders,
  Network,
  Activity,
  ShieldCheck,
} from 'lucide-react'
import { api, apiBaseUrl, type GatewayStatus } from '@/lib/api'
import { useBackendHealth, useDataSource } from '@/hooks/useBackendHealth'
import { useLocalStorage } from '@/hooks/useAsync'
import { DEFAULT_FAIRNESS } from '@/lib/mockData'
import { fmtNum } from '@/lib/format'
import { Card } from '@/components/ui/Card'
import { Badge, Button, Callout, Field, Progress, Switch } from '@/components/ui/Primitives'
import type { FairnessConfig } from '@/types'

/* ---------------------------------------------------------------------------
   Status vocabulary
   --------------------------------------------------------------------------- */

const BACKEND_LABEL = {
  checking: 'Checking',
  connected: 'Connected',
  disconnected: 'Disconnected',
} as const

const BACKEND_TONE = {
  checking: 'neutral',
  connected: 'teal',
  disconnected: 'rose',
} as const

/** Gateway statuses come from the backend's live probe — never invented here. */
const GATEWAY_LABEL: Record<string, string> = {
  connected: 'Connected',
  auth_error: 'Authentication error',
  unreachable: 'Unreachable',
  misconfigured: 'Misconfigured',
  disabled: 'Disabled',
  unknown: 'Unknown',
}

const GATEWAY_TONE: Record<string, 'teal' | 'rose' | 'amber' | 'neutral'> = {
  connected: 'teal',
  auth_error: 'rose',
  unreachable: 'rose',
  misconfigured: 'amber',
  disabled: 'neutral',
  unknown: 'neutral',
}

/** The shape rendered when the backend could not be asked about the gateway. */
const UNKNOWN_GATEWAY: GatewayStatus = {
  enabled: true,
  gateway_url: '',
  reachable: false,
  authenticated: false,
  model_call_path_ok: false,
  status: 'unknown',
  error: null,
  providers: [],
  models: [],
  version: null,
  latency_ms: null,
}

export default function Settings() {
  const [fairness, setFairness] = useLocalStorage<FairnessConfig>('bifrost.fairness', DEFAULT_FAIRNESS)
  const [saved, setSaved] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [compactRows, setCompactRows] = useState(false)
  const [notifyFail, setNotifyFail] = useState(true)

  const health = useBackendHealth({ intervalMs: 15_000 })
  const dataSource = useDataSource()

  const [gw, setGw] = useState<GatewayStatus>(UNKNOWN_GATEWAY)
  const [gwLoading, setGwLoading] = useState(false)
  const [gwError, setGwError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [testing, setTesting] = useState(false)

  /** Ask the backend about the gateway. Never invents a status. */
  const refreshGateway = useCallback(async () => {
    setGwLoading(true)
    setGwError(null)
    try {
      const data = await api.gatewayStatus()
      setGw(data)
    } catch (err) {
      // The backend itself is unreachable — the gateway state is unknown, not "ok".
      setGw({ ...UNKNOWN_GATEWAY, error: null })
      setGwError(
        err instanceof Error
          ? `Backend unreachable — gateway status unavailable: ${err.message}`
          : 'Backend unreachable — gateway status unavailable',
      )
    } finally {
      setGwLoading(false)
    }
  }, [])

  /** Re-run both live checks. */
  const refreshAll = useCallback(async () => {
    setTestResult(null)
    await Promise.all([health.refresh(), refreshGateway()])
  }, [health, refreshGateway])

  useEffect(() => {
    void refreshGateway()
  }, [refreshGateway])

  /** Explicit connectivity test against the configured backend URL. */
  const runTest = useCallback(async () => {
    setTesting(true)
    setTestResult(null)
    try {
      // Use the probe's own result — the hook's state has not re-rendered yet.
      const res = await health.refresh()
      await refreshGateway()
      setTestResult({
        ok: res.state === 'connected',
        message:
          res.state === 'connected'
            ? `OK — backend answered in ${res.latencyMs ?? 0}ms`
            : (res.error ?? 'Backend is unreachable'),
      })
    } finally {
      setTesting(false)
    }
  }, [health, refreshGateway])

  const save = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2200)
  }

  const backendLabel = BACKEND_LABEL[health.state]
  const backendTone = BACKEND_TONE[health.state]
  const gatewayLabel = GATEWAY_LABEL[gw.status] ?? gw.status
  const gatewayTone = GATEWAY_TONE[gw.status] ?? 'neutral'
  const gatewayKnown = gw.status !== 'unknown'

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head page-head-row">
        <div>
          <div className="page-eyebrow">System</div>
          <h1 className="page-title">Settings</h1>
          <p className="page-desc">
            Workspace configuration for the Bifrost dashboard. Runtime parameters for individual runs
            live on the fairness page.
          </p>
        </div>
        <Button variant="primary" icon={<Save />} onClick={save}>
          {saved ? 'Saved' : 'Save changes'}
        </Button>
      </div>

      <div className="grid grid-2">
        {/* ---------------- Backend connection ---------------- */}
        <Card
          title="Backend connection"
          subtitle="Live health of the FastAPI backend"
          action={
            <Button size="sm" icon={<RefreshCw />} onClick={() => void refreshAll()} disabled={gwLoading}>
              {gwLoading ? 'Checking…' : 'Refresh'}
            </Button>
          }
        >
          <div className="stack" style={{ gap: 14 }}>
            <Field label="API base URL" hint="Restart the dev server after changing this">
              <div className="row">
                <input className="input mono" defaultValue={apiBaseUrl()} readOnly />
                <Button size="sm" icon={<Plug />} loading={testing} onClick={() => void runTest()}>
                  Test
                </Button>
              </div>
            </Field>

            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="row" style={{ gap: 8 }}>
                <Server size={14} className="muted" />
                <span className="small">Backend</span>
              </span>
              <Badge tone={backendTone} dot>
                {backendLabel}
                {health.state === 'connected' && health.latencyMs != null
                  ? ` · ${health.latencyMs}ms`
                  : ''}
              </Badge>
            </div>

            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="row" style={{ gap: 8 }}>
                <Activity size={14} className="muted" />
                <span className="small">Data source</span>
              </span>
              <Badge tone={dataSource === 'live' ? 'teal' : 'amber'} dot>
                {dataSource === 'live' ? 'Live API' : 'Demo fixtures'}
              </Badge>
            </div>

            {health.checkedAt != null && (
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="row" style={{ gap: 8 }}>
                  <RefreshCw size={14} className="muted" />
                  <span className="small">Last checked</span>
                </span>
                <span className="mono tiny muted">
                  {new Date(health.checkedAt).toLocaleTimeString()}
                </span>
              </div>
            )}

            {testResult && (
              <Callout tone={testResult.ok ? 'teal' : 'rose'} icon={<Plug size={15} style={{ marginTop: 1 }} />}>
                <div className="small">{testResult.message}</div>
              </Callout>
            )}

            {health.state === 'disconnected' && (
              <Callout tone="rose" icon={<Server size={15} style={{ marginTop: 1 }} />}>
                <div className="small">
                  <strong>Backend unreachable.</strong> {health.error}
                  {dataSource === 'demo' && (
                    <>
                      {' '}
                      The dashboard is currently serving the bundled fixture catalogue — the numbers
                      on screen are demo data, not live results.
                    </>
                  )}
                </div>
              </Callout>
            )}

            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="row" style={{ gap: 8 }}>
                <Database size={14} className="muted" />
                <span className="small">Storage</span>
              </span>
              <Badge tone="neutral">SQLite (dev) · Postgres (prod)</Badge>
            </div>

            <Callout tone="amber" icon={<Plug size={15} style={{ marginTop: 1 }} />}>
              <div>
                The UI falls back to the bundled fixture catalogue when the backend is unreachable,
                so the dashboard stays explorable. While that is happening the backend is reported as
                <strong> disconnected</strong> and the data source as <strong>Demo fixtures</strong> —
                fixture data is never presented as a live connection.
              </div>
            </Callout>
          </div>
        </Card>

        {/* ---------------- Bifrost gateway ---------------- */}
        <Card
          title="Maxim AI Bifrost gateway"
          subtitle="All live model traffic is routed through Bifrost"
          action={
            <Button size="sm" icon={<RefreshCw />} onClick={() => void refreshGateway()} disabled={gwLoading}>
              {gwLoading ? 'Checking…' : 'Refresh'}
            </Button>
          }
        >
          <div className="stack" style={{ gap: 14 }}>
            <Field label="Gateway URL" hint="Set via BIFROST_GATEWAY_URL on the backend">
              <input
                className="input mono"
                value={gw.gateway_url || 'unknown — backend unreachable'}
                readOnly
              />
            </Field>

            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="row" style={{ gap: 8 }}>
                <Network size={14} className="muted" />
                <span className="small">Connection</span>
              </span>
              <Badge tone={gatewayTone} dot>
                {gatewayLabel}
                {gw.latency_ms != null && gatewayKnown ? ` · ${gw.latency_ms}ms` : ''}
              </Badge>
            </div>

            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="small muted">Enabled</span>
              <Badge tone={gw.enabled ? 'teal' : 'neutral'}>{gw.enabled ? 'yes' : 'no'}</Badge>
            </div>

            {gatewayKnown && (
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">HTTP reachable</span>
                <Badge tone={gw.reachable ? 'teal' : 'rose'}>{gw.reachable ? 'yes' : 'no'}</Badge>
              </div>
            )}

            {gatewayKnown && (
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Authenticated</span>
                <Badge tone={gw.authenticated ? 'teal' : 'rose'}>
                  {gw.authenticated ? 'yes' : 'no'}
                </Badge>
              </div>
            )}

            {gatewayKnown && (
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Model endpoint</span>
                <Badge tone={gw.model_call_path_ok ? 'teal' : 'amber'}>
                  {gw.model_call_path_ok ? 'available' : 'no models exposed'}
                </Badge>
              </div>
            )}

            {gwError && (
              <Callout tone="rose" icon={<Network size={15} style={{ marginTop: 1 }} />}>
                <div className="small">{gwError}</div>
              </Callout>
            )}

            {gw.error && (
              <Callout
                tone={gw.status === 'auth_error' ? 'rose' : gw.status === 'connected' ? 'amber' : 'rose'}
                icon={
                  gw.status === 'auth_error' ? (
                    <ShieldCheck size={15} style={{ marginTop: 1 }} />
                  ) : (
                    <Network size={15} style={{ marginTop: 1 }} />
                  )
                }
              >
                <div className="small">
                  {gw.status === 'auth_error' ? (
                    <>
                      <strong>Authentication failed.</strong> {gw.error}
                    </>
                  ) : gw.status === 'connected' ? (
                    <>
                      <strong>Gateway reachable.</strong> {gw.error}
                    </>
                  ) : (
                    <>
                      <strong>Gateway unreachable.</strong> {gw.error}
                    </>
                  )}
                </div>
              </Callout>
            )}

            {gw.reachable && (
              <>
                <div>
                  <div className="small muted mb-1">Configured providers</div>
                  <div className="row-wrap" style={{ gap: 6 }}>
                    {(gw.providers.length ? gw.providers : ['(none detected)']).map((p) => (
                      <Badge key={p} tone="neutral">
                        {p}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="small muted mb-1">
                    Available models {gw.models.length ? `(${gw.models.length})` : ''}
                  </div>
                  <div className="mono tiny" style={{ maxHeight: 72, overflow: 'auto' }}>
                    {gw.models.length
                      ? gw.models.slice(0, 24).join(', ') + (gw.models.length > 24 ? '…' : '')
                      : 'Configure providers in the Bifrost UI at the gateway URL'}
                  </div>
                </div>
              </>
            )}

            {!gw.reachable && !gw.error && !gwError && (
              <Callout tone="amber">
                <div className="small">
                  Start Bifrost with <code className="mono">npx -y @maximhq/bifrost</code> or Docker, then
                  add Gemini / OpenRouter keys in its web UI. API keys are never shown here.
                </div>
              </Callout>
            )}
          </div>
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Dashboard preferences" subtitle="Local to this browser">
          <div className="stack" style={{ gap: 14 }}>
            <label className="row" style={{ justifyContent: 'space-between', cursor: 'pointer' }}>
              <span>
                <span className="strong" style={{ fontSize: 13 }}>Auto-refresh live runs</span>
                <div className="tiny muted">Polls the run stream every 5 seconds</div>
              </span>
              <Switch checked={autoRefresh} onChange={setAutoRefresh} label="Auto refresh" />
            </label>
            <label className="row" style={{ justifyContent: 'space-between', cursor: 'pointer' }}>
              <span>
                <span className="strong" style={{ fontSize: 13 }}>Compact table rows</span>
                <div className="tiny muted">Denser tables for large run histories</div>
              </span>
              <Switch checked={compactRows} onChange={setCompactRows} label="Compact rows" />
            </label>
            <label className="row" style={{ justifyContent: 'space-between', cursor: 'pointer' }}>
              <span>
                <span className="strong" style={{ fontSize: 13 }}>Notify on run failure</span>
                <div className="tiny muted">Surface a toast when a run errors out</div>
              </span>
              <Switch checked={notifyFail} onChange={setNotifyFail} label="Notify on failure" />
            </label>
          </div>
        </Card>

        <Card title="Storage" subtitle="Where benchmark history is persisted">
          <div className="grid grid-3" style={{ gap: 18 }}>
            {[
              ['Runs & results', 'SQLite · bifrost.db', 'PostgreSQL in production'],
              ['Task fixtures', 'Container image + dataset hash', 'Immutable, content-addressed'],
              ['Artifacts', 'Sandbox stdout / diffs / traces', 'Object storage with signed URLs'],
            ].map(([t, sub, note]) => (
              <div key={t}>
                <div className="strong" style={{ fontSize: 13 }}>
                  {t}
                </div>
                <div className="mono tiny muted mt-1">{sub}</div>
                <div className="tiny muted mt-1">{note}</div>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <Progress value={34} color="var(--accent)" />
            <div className="tiny muted mt-2">34% of the 5 GB dev quota used by run artifacts</div>
          </div>
        </Card>
      </div>

      <Card
        title="Default scoring weights"
        subtitle="Applied to new runs unless overridden at launch"
        action={<Badge tone="neutral"><Sliders size={11} /> scorer {fairness.scorer_version}</Badge>}
      >
        <div className="grid grid-2" style={{ gap: 20 }}>
          {(
            [
              ['task_success', 'Task success', 'Did the agent complete the task?'],
              ['correctness', 'Correctness', 'Do the hidden unit tests pass?'],
              ['efficiency', 'Efficiency', 'How many unnecessary steps were taken?'],
              ['tool_usage', 'Tool usage', 'Were tools used appropriately?'],
              ['consistency', 'Consistency', 'How stable across repeats?'],
            ] as const
          ).map(([key, label, desc]) => (
            <div key={key}>
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 13 }}>
                  <span className="strong">{label}</span>
                  <span className="small muted"> — {desc}</span>
                </span>
                <span className="mono strong small">
                  {Math.round(fairness.metric_weights[key] * 100)}%
                </span>
              </div>
              <input
                className="slider"
                type="range"
                min={0}
                max={60}
                step={5}
                value={fairness.metric_weights[key]}
                onChange={(e) =>
                  setFairness({
                    ...fairness,
                    metric_weights: {
                      ...fairness.metric_weights,
                      [key]: Number(e.target.value) / 100,
                    },
                  })
                }
              />
            </div>
          ))}
        </div>
        <div className="divider mt-4 mb-3" />
        <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
          <span className="small muted">
            Total weight {Math.round(Object.values(fairness.metric_weights).reduce((s, w) => s + w, 0) * 100)}% ·
            token budget {fmtNum(fairness.max_tokens_per_task)} · time limit {fairness.time_limit_per_task_sec}s · ×
            {fairness.repeats} repeats
          </span>
          <Button size="sm" icon={<RotateCcw />} onClick={() => setFairness(DEFAULT_FAIRNESS)}>
            Reset defaults
          </Button>
        </div>
      </Card>
    </div>
  )
}
