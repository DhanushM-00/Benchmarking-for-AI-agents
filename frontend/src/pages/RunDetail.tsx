import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Coins,
  Download,
  Gauge,
  ListChecks,
  Play,
  RotateCcw,
  Scale,
  ShieldCheck,
  Timer,
  Wrench,
  XCircle,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useAsync, usePolling } from '@/hooks/useAsync'
import { agentColor, fmtCompact, fmtDuration, fmtNum, fmtTime, fmtUsd, scoreColor } from '@/lib/format'
import { Card, AgentChip, Stat } from '@/components/ui/Card'
import { Badge, Button, Callout, EmptyState, Progress, Skeleton, StatusPill } from '@/components/ui/Primitives'
import { GroupedBars, HorizontalBars, LegendRow, RadarProfile } from '@/components/charts/Charts'

const TABS = ['Overview', 'Task matrix', 'Agents', 'Fairness', 'Model traces', 'Event log', 'Timeline'] as const
type Tab = (typeof TABS)[number]

const METRIC_AXES = [
  { key: 'task_success', label: 'Task success' },
  { key: 'correctness', label: 'Correctness' },
  { key: 'efficiency', label: 'Efficiency' },
  { key: 'tool_usage', label: 'Tool usage' },
  { key: 'consistency', label: 'Consistency' },
] as const

export default function RunDetail() {
  const { id = '' } = useParams()
  const { data: run, loading, error, reload } = useAsync(() => api.getRun(id), [id])
  const [actionBusy, setActionBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  const handleCancel = async () => {
    if (!id || actionBusy) return
    setActionBusy(true)
    setActionMsg(null)
    try {
      await api.cancelRun(id)
      setActionMsg('Cancel requested')
      reload?.()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Cancel failed')
    } finally {
      setActionBusy(false)
    }
  }

  const handleExport = async () => {
    if (!id || actionBusy) return
    setActionBusy(true)
    setActionMsg(null)
    try {
      const report = await api.runReport(id)
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${id}-report.json`
      a.click()
      URL.revokeObjectURL(url)
      setActionMsg('Report downloaded')
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setActionBusy(false)
    }
  }

  const live = usePolling(() => api.getRun(id), 5000)
  const [tab, setTab] = useState<Tab>('Overview')

  const current = live.data ?? run

  const perAgent = useMemo(
    () => [...(current?.agent_results ?? [])].sort((a, b) => b.overall_score - a.overall_score),
    [current],
  )

  if (error) {
    return (
      <Card>
        <EmptyState
          icon={<XCircle size={30} />}
          title="Run not found"
          description={error}
          action={
            <Link to="/runs">
              <Button icon={<ArrowLeft />}>Back to runs</Button>
            </Link>
          }
        />
      </Card>
    )
  }

  if (loading || !current) {
    return (
      <div className="stack">
        <Skeleton h={110} radius={16} />
        <div className="grid grid-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} h={104} radius={16} />
          ))}
        </div>
        <Skeleton h={320} radius={16} />
      </div>
    )
  }

  const totalCost = perAgent.reduce((s, a) => s + a.total_cost_usd, 0)
  const totalTokens = perAgent.reduce((s, a) => s + a.total_tokens, 0)
  const avgScore = perAgent.length
    ? perAgent.reduce((s, a) => s + a.overall_score, 0) / perAgent.length
    : 0
  const avgTime = perAgent.length
    ? perAgent.reduce((s, a) => s + a.avg_execution_time_sec, 0) / perAgent.length
    : 0
  const best = perAgent[0]

  const radarSeries = perAgent.map((a) => ({
    name: a.agent_name,
    colorIndex: a.color_index,
    values: METRIC_AXES.map((m) => a.metrics[m.key] ?? 0),
  }))

  const metricBars = METRIC_AXES.map((m) => ({
    name: m.label,
    value: perAgent.length ? perAgent.reduce((s, a) => s + (a.metrics[m.key] ?? 0), 0) / perAgent.length : 0,
  }))

  return (
    <div className="stack" style={{ gap: 20 }}>
      {/* ---------- Header ---------- */}
      <div className="page-head page-head-row">
        <div style={{ minWidth: 0 }}>
          <Link to="/runs" className="small muted row" style={{ gap: 5, marginBottom: 8 }}>
            <ArrowLeft size={13} /> All runs
          </Link>
          <div className="row-wrap" style={{ gap: 10 }}>
            <h1 className="page-title">{current.name}</h1>
            <StatusPill status={current.status} />
            {current.fairness_report?.score === 100 && (
              <Badge tone="violet" className="tip" data-tip="Fair Agent Testing Engine: all parity checks passed">
                <ShieldCheck /> Fair
              </Badge>
            )}
          </div>
          <div className="row-wrap small muted" style={{ gap: 9, marginTop: 7 }}>
            <span>{current.benchmark_name}</span>
            <span>·</span>
            <span>started {fmtTime(current.started_at)}</span>
            {current.duration_sec && (
              <>
                <span>·</span>
                <span>{fmtDuration(current.duration_sec)} wall clock</span>
              </>
            )}
            <span>·</span>
            <span>{current.fairness.repeats} repeats</span>
          </div>
          {current.notes && <div className="small muted mt-2">“{current.notes}”</div>}
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
          <Button icon={<Download />} onClick={handleExport} disabled={actionBusy}>
            Export report
          </Button>
          <Link to={`/run?rerun=${current.id}`}>
            <Button icon={<RotateCcw />} disabled={actionBusy}>
              Re-run config
            </Button>
          </Link>
          {current.status === 'running' || current.status === 'queued' ? (
            <Button variant="danger" icon={<XCircle />} onClick={handleCancel} disabled={actionBusy}>
              Cancel run
            </Button>
          ) : (
            <Link to="/run">
              <Button variant="primary" icon={<Play />}>
                New run
              </Button>
            </Link>
          )}
          {actionMsg && <span className="small muted">{actionMsg}</span>}
        </div>
      </div>

      {/* ---------- Live progress ---------- */}
      {current.status === 'running' && (
        <Card>
          <div className="row-wrap" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <div className="row" style={{ gap: 9 }}>
              <Activity size={16} style={{ color: 'var(--accent)' }} className="status-running" />
              <span className="strong">Run in progress</span>
              <span className="small muted">orchestrator dispatching tasks to the sandbox pool</span>
            </div>
            <span className="mono strong">{current.progress}%</span>
          </div>
          <Progress value={current.progress} color="var(--accent)" large />
          <div className="grid grid-3 mt-4" style={{ gap: 12 }}>
            {perAgent.map((a) => (
              <div key={a.agent_id}>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
                  <AgentChip name={a.agent_name} colorIndex={a.color_index} />
                  <span className="mono tiny muted">
                    {a.tasks_completed}/{a.tasks_total}
                  </span>
                </div>
                <Progress
                  value={(a.tasks_completed / Math.max(1, a.tasks_total)) * 100}
                  color={agentColor(a.color_index)}
                />
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ---------- Stats ---------- */}
      <div className="grid grid-4">
        <Stat
          label="Winning score"
          value={best ? best.overall_score.toFixed(1) : '—'}
          unit="/100"
          foot={best ? <AgentChip name={best.agent_name} colorIndex={best.color_index} /> : undefined}
          accent={best ? agentColor(best.color_index) : 'var(--accent)'}
          icon={<Gauge />}
        />
        <Stat
          label="Mean score"
          value={avgScore.toFixed(1)}
          unit="/100"
          foot={<span>across {perAgent.length} agents</span>}
          accent="#2dd4a7"
          icon={<TargetIcon />}
        />
        <Stat
          label="Avg execution time"
          value={avgTime.toFixed(1)}
          unit="s"
          foot={<span>p95 {Math.max(...perAgent.map((a) => a.p95_execution_time_sec)).toFixed(1)}s</span>}
          accent="#f5a524"
          icon={<Timer />}
        />
        <Stat
          label="Run cost"
          value={fmtUsd(totalCost)}
          foot={
            <>
              <Coins size={12} />
              <span>{fmtCompact(totalTokens)} tokens</span>
            </>
          }
          accent="#a78bfa"
          icon={<Coins />}
        />
      </div>

      {/* ---------- Tabs ---------- */}
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'Overview' && (
        <div className="stack">
          <div className="grid grid-2">
            <Card title="Capability profile" subtitle="Weighted metric fingerprint per agent">
              {radarSeries.length ? (
                <RadarProfile axes={METRIC_AXES.map((m) => m.label)} series={radarSeries} height={306} />
              ) : (
                <Skeleton h={306} />
              )}
            </Card>

            <Card title="Metric breakdown" subtitle="Average across agents in this run">
              <div className="stack" style={{ gap: 14 }}>
                {metricBars.map((m) => (
                  <div key={m.name}>
                    <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
                      <span style={{ fontSize: 12.5 }}>{m.name}</span>
                      <span className="mono strong" style={{ fontSize: 12.5, color: scoreColor(m.value) }}>
                        {m.value.toFixed(1)}
                      </span>
                    </div>
                    <div className="bar bar-lg">
                      <div
                        className="bar-fill"
                        style={{ width: `${m.value}%`, background: scoreColor(m.value) }}
                      />
                    </div>
                  </div>
                ))}
                <div className="divider" />
                <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
                  <span className="small muted">Weights applied</span>
                  <span className="mono small">
                    {METRIC_AXES.map((m) => `${Math.round(current.fairness.metric_weights[m.key] * 100)}%`).join(' · ')}
                  </span>
                </div>
              </div>
            </Card>
          </div>

          <div className="grid grid-3">
            <Card title="Cost per agent" subtitle="Total spend for this run">
              <GroupedBars
                data={perAgent.map((a) => ({ name: a.agent_name, cost: a.total_cost_usd }))}
                bars={[{ key: 'cost', name: 'Cost (USD)', colorIndex: 0 }]}
                rowColors={perAgent.map((a) => agentColor(a.color_index))}
                yFormatter={(v) => `$${v.toFixed(2)}`}
                height={236}
              />
              <div className="mt-3 small muted">
                Cost is billed from the token ledger, so it tracks output volume almost exactly —
                Nova is 9× cheaper than Forge but solves far fewer tasks.
              </div>
            </Card>

            <Card title="Execution time" subtitle="Average and p95 wall clock per task">
              <GroupedBars
                data={perAgent.map((a) => ({
                  name: a.agent_name,
                  avg: a.avg_execution_time_sec,
                  p95: a.p95_execution_time_sec,
                }))}
                bars={[
                  { key: 'avg', name: 'Avg seconds', colorIndex: 0 },
                  { key: 'p95', name: 'p95 seconds', colorIndex: 3 },
                ]}
                yFormatter={(v) => `${v.toFixed(0)}s`}
                height={236}
              />
              <div className="mt-3 small muted">
                Speed and spend rarely move together — Forge is the slowest but produces the most
                correct solutions.
              </div>
            </Card>

            <Card title="Token consumption" subtitle="Input + output tokens billed">
              <GroupedBars
                data={perAgent.map((a) => ({ name: a.agent_name, tokens: a.total_tokens }))}
                bars={[{ key: 'tokens', name: 'Tokens', colorIndex: 1 }]}
                rowColors={perAgent.map((a) => agentColor(a.color_index))}
                yFormatter={(v) => fmtCompact(v)}
                height={236}
              />
            </Card>
          </div>

          <Card title="Score per agent" subtitle="Weighted overall score for this run">
            <HorizontalBars
              data={perAgent.map((a) => ({
                name: a.agent_name,
                value: a.overall_score,
                color: agentColor(a.color_index),
              }))}
              formatter={(v) => v.toFixed(1)}
            />
            <div className="mt-3">
              <LegendRow
                items={perAgent.map((a) => ({ name: a.agent_name, colorIndex: a.color_index }))}
              />
            </div>
          </Card>
        </div>
      )}

      {tab === 'Task matrix' && (
        <Card
          title="Task × agent matrix"
          subtitle="Every agent saw the same tasks — the columns are directly comparable"
          flush
        >
          <div className="card-body">
            <div className="row-wrap" style={{ gap: 14, marginBottom: 12 }}>
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: 'rgba(45,212,167,0.5)' }} /> passed
              </span>
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: 'rgba(245,165,36,0.5)' }} /> partial
              </span>
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: 'rgba(244,82,95,0.5)' }} /> failed
              </span>
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: 'var(--surface-2)' }} /> not run
              </span>
            </div>

            {perAgent.length === 0 ? (
              <EmptyState
                icon={<ListChecks size={30} />}
                title="No task results yet"
                description="The orchestrator has not written task outcomes for this run."
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="matrix">
                  <thead>
                    <tr>
                      <th className="task-name">Task</th>
                      {perAgent.map((a) => (
                        <th key={a.agent_id} style={{ minWidth: 96 }}>
                          <span
                            className="row"
                            style={{ gap: 6, justifyContent: 'center', color: agentColor(a.color_index) }}
                          >
                            <span className="agent-dot" style={{ background: agentColor(a.color_index) }} />
                            {a.agent_name.split(' ')[0]}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(perAgent[0].task_results ?? []).map((task, ti) => (
                      <tr key={task.task_id}>
                        <td className="task-name">
                          <div className="row" style={{ gap: 8 }}>
                            <Badge tone="neutral">{task.difficulty}</Badge>
                            <span className="small truncate" title={task.task_title}>
                              {task.task_title}
                            </span>
                          </div>
                        </td>
                        {perAgent.map((a) => {
                          const tr = a.task_results[ti]
                          if (!tr)
                            return (
                              <td key={a.agent_id}>
                                <div className="matrix-cell mc-na">—</div>
                              </td>
                            )
                          const cls = tr.completed
                            ? tr.correctness >= 85
                              ? 'mc-pass'
                              : tr.correctness >= 45
                                ? 'mc-partial'
                                : 'mc-fail'
                            : 'mc-fail'
                          return (
                            <td key={a.agent_id}>
                              <div
                                className={`matrix-cell ${cls}`}
                                title={`${tr.task_title} · ${tr.correctness}% correct · ${tr.execution_time_sec}s`}
                              >
                                {tr.completed ? Math.round(tr.correctness) : '✕'}
                              </div>
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}

      {tab === 'Agents' && (
        <div className="stack">
          <Card title="Per-agent results" flush>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th className="num">Overall</th>
                    <th className="num">Success</th>
                    <th className="num">Correct</th>
                    <th className="num">Efficiency</th>
                    <th className="num">Tool use</th>
                    <th className="num">Avg time</th>
                    <th className="num">p95</th>
                    <th className="num">Tokens</th>
                    <th className="num">Cost</th>
                    <th className="num">Variance</th>
                  </tr>
                </thead>
                <tbody>
                  {perAgent.map((a) => (
                    <tr key={a.agent_id}>
                      <td>
                        <AgentChip name={a.agent_name} colorIndex={a.color_index} />
                        <div className="tiny muted">
                          {a.tasks_completed}/{a.tasks_total} tasks
                        </div>
                      </td>
                      <td className="num strong" style={{ color: scoreColor(a.overall_score) }}>
                        {a.overall_score.toFixed(1)}
                      </td>
                      <td className="num">{a.metrics.task_success.toFixed(1)}</td>
                      <td className="num">{a.metrics.correctness.toFixed(1)}</td>
                      <td className="num">{a.metrics.efficiency.toFixed(1)}</td>
                      <td className="num">{a.metrics.tool_usage.toFixed(1)}</td>
                      <td className="num">{a.avg_execution_time_sec.toFixed(1)}s</td>
                      <td className="num">{a.p95_execution_time_sec.toFixed(1)}s</td>
                      <td className="num">{fmtCompact(a.total_tokens)}</td>
                      <td className="num">{fmtUsd(a.total_cost_usd)}</td>
                      <td className="num muted">±{a.repeat_variance.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {perAgent.map((a) => {
            const topTasks = [...(a.task_results ?? [])]
              .sort((x, y) => y.correctness - x.correctness)
              .slice(0, 5)
            const worst = [...(a.task_results ?? [])]
              .sort((x, y) => x.correctness - y.correctness)
              .slice(0, 3)
            const toolUsage = (a.task_results ?? [])
              .flatMap((t) => t.tool_calls)
              .reduce(
                (acc, tc) => {
                  acc[tc.tool] = acc[tc.tool] ?? { calls: 0, errors: 0 }
                  acc[tc.tool].calls += 1
                  if (tc.outcome !== 'success') acc[tc.tool].errors += 1
                  return acc
                },
                {} as Record<string, { calls: number; errors: number }>,
              )
            return (
              <Card
                key={a.agent_id}
                title={<AgentChip name={a.agent_name} colorIndex={a.color_index} />}
                subtitle={`${a.tool_calls_total} tool calls · ${a.unnecessary_steps_total} unnecessary steps`}
                action={<Badge tone="neutral">score {a.overall_score.toFixed(1)}</Badge>}
              >
                <div className="grid grid-3" style={{ gap: 18 }}>
                  <div>
                    <div className="kv-label mb-2">Strongest tasks</div>
                    <div className="stack" style={{ gap: 6 }}>
                      {topTasks.map((t) => (
                        <div className="row" style={{ gap: 8 }} key={t.task_id}>
                          <CheckCircle2 size={13} style={{ color: 'var(--teal)', flexShrink: 0 }} />
                          <span className="small truncate">{t.task_title}</span>
                          <span className="mono tiny muted" style={{ marginLeft: 'auto' }}>
                            {Math.round(t.correctness)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="kv-label mb-2">Weakest tasks</div>
                    <div className="stack" style={{ gap: 6 }}>
                      {worst.map((t) => (
                        <div className="row" style={{ gap: 8 }} key={t.task_id}>
                          <XCircle size={13} style={{ color: 'var(--rose)', flexShrink: 0 }} />
                          <span className="small truncate">{t.task_title}</span>
                          <span className="mono tiny muted" style={{ marginLeft: 'auto' }}>
                            {Math.round(t.correctness)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="kv-label mb-2">Tool usage</div>
                    <div className="stack" style={{ gap: 6 }}>
                      {Object.entries(toolUsage).map(([tool, v]) => (
                        <div className="row" style={{ gap: 8 }} key={tool}>
                          <Wrench size={13} className="muted" style={{ flexShrink: 0 }} />
                          <span className="small mono">{tool}</span>
                          <span className="tiny muted" style={{ marginLeft: 'auto' }}>
                            {v.calls} calls
                            {v.errors > 0 && (
                              <span style={{ color: 'var(--amber)' }}> · {v.errors} err</span>
                            )}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {tab === 'Fairness' && (
        <div className="stack">
          <Card title="Parity report" subtitle="Verified by the Fair Agent Testing Engine before scoring">
            <div className="row-wrap" style={{ gap: 20, alignItems: 'flex-start' }}>
              <div style={{ flex: '0 0 160px' }}>
                <div className="tiny muted">Fairness score</div>
                <div
                  className="mono"
                  style={{ fontSize: 40, fontWeight: 650, color: 'var(--violet)', lineHeight: 1.1 }}
                >
                  {current.fairness_report?.score ?? 0}%
                </div>
                <Progress
                  value={current.fairness_report?.score ?? 0}
                  color="var(--violet)"
                  large
                  className="mt-2"
                />
                <div className="tiny muted mt-2">
                  {current.fairness_report?.checks?.filter((c) => c.status === 'pass').length ?? 0} of{' '}
                  {current.fairness_report?.checks?.length ?? 0} checks passing
                </div>
              </div>
              <div style={{ flex: '1 1 380px', minWidth: 0 }}>
                <div className="stack" style={{ gap: 9 }}>
                  {(current.fairness_report?.checks ?? []).map((c) => (
                    <div className="row" style={{ gap: 10, alignItems: 'flex-start' }} key={c.id}>
                      {c.status === 'pass' ? (
                        <CheckCircle2 size={15} style={{ color: 'var(--teal)', flexShrink: 0, marginTop: 2 }} />
                      ) : c.status === 'warn' ? (
                        <Clock size={15} style={{ color: 'var(--amber)', flexShrink: 0, marginTop: 2 }} />
                      ) : (
                        <XCircle size={15} style={{ color: 'var(--rose)', flexShrink: 0, marginTop: 2 }} />
                      )}
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 550 }}>{c.label}</div>
                        <div className="tiny muted">{c.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          <div className="grid grid-2">
            <Card title="Locked parameters" subtitle="Identical for every agent in this run">
              <div className="stack" style={{ gap: 11 }}>
                {[
                  ['Time limit / task', `${current.fairness.time_limit_per_task_sec}s`],
                  ['Token budget / task', fmtNum(current.fairness.max_tokens_per_task)],
                  ['Repeats', `×${current.fairness.repeats}`],
                  ['Isolation', current.fairness.isolation],
                  ['Container image', current.fairness.container_image],
                  ['Network policy', current.fairness.network_policy],
                  ['Random seed', String(current.fairness.random_seed)],
                  ['Scorer version', current.fairness.scorer_version],
                  ['Temperature', String(current.fairness.temperature)],
                  ['Blinded evaluation', current.fairness.blinded_evaluation ? 'enabled' : 'disabled'],
                ].map(([k, v]) => (
                  <div className="row" style={{ justifyContent: 'space-between', gap: 16 }}>
                    <span className="small muted">{k}</span>
                    <span className="mono small strong truncate" title={v}>
                      {v}
                    </span>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Metric weights" subtitle="How the overall score was composed">
              <div className="stack" style={{ gap: 14 }}>
                {METRIC_AXES.map((m) => (
                  <div key={m.key}>
                    <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
                      <span style={{ fontSize: 12.5 }}>{m.label}</span>
                      <span className="mono small strong">
                        {Math.round(current.fairness.metric_weights[m.key] * 100)}%
                      </span>
                    </div>
                    <Progress
                      value={current.fairness.metric_weights[m.key] * 100}
                      color="var(--accent)"
                    />
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Callout tone="amber" icon={<Scale size={15} style={{ marginTop: 1 }} />}>
            <div>
              <strong>Why this matters.</strong> Without a parity contract, an agent can score higher
              simply because it got more time, a friendlier prompt, or a laxer scorer. Bifrost pins
              every one of these before a single task is dispatched.
            </div>
          </Callout>
        </div>
      )}

      {tab === 'Model traces' && (
        <Card
          title="Bifrost model-call traces"
          subtitle="Every LLM request routed through the gateway for this run"
        >
          {/* Always use the route param — never a substituted fixture run id */}
          <ModelTracePanel runId={id} />
        </Card>
      )}

      {tab === 'Event log' && (
        <Card
          title="Orchestrator event log"
          subtitle="Persisted agent and orchestrator events for this run"
        >
          <EventLog runId={id} />
        </Card>
      )}
      {tab === 'Timeline' && (
        <Card title="Unified execution timeline" subtitle="Events and model calls in chronological order">
          <TimelinePanel runId={id} />
        </Card>
      )}
    </div>
  )
}

/* ---------------------------------------- */
function EventLog({ runId }: { runId: string }) {
  const [events, setEvents] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const load = async () => {
      try {
        const data = await api.runEvents(runId)
        if (cancelled) return
        setEvents(data.events || [])
        setError(null)
        setLoading(false)
        // Poll while run may still be active
        timer = setTimeout(load, 2000)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load events')
        setLoading(false)
        timer = setTimeout(load, 4000)
      }
    }
    load()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [runId])

  const tagClass = (status?: string, type?: string) => {
    if (status === 'error' || type?.includes('fail')) return 'tag-err'
    if (status === 'running') return 'tag-info'
    if (type?.includes('completed') || status === 'ok') return 'tag-ok'
    if (status === 'warn') return 'tag-warn'
    return 'tag-info'
  }

  const download = () => {
    const blob = new Blob([JSON.stringify({ run_id: runId, events }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${runId}-events.json`
    a.click()
    URL.revokeObjectURL(url)
  }
  if (loading && events.length === 0) {
    return <div className="log"><div className="log-line"><span className="log-msg">Loading events…</span></div></div>
  }
  if (error && events.length === 0) {
    return <div className="log"><div className="log-line"><span className="log-tag tag-err">error</span><span className="log-msg">{error}</span></div></div>
  }
  if (events.length === 0) {
    return <div className="log"><div className="log-line"><span className="log-msg">No events recorded for this run yet.</span></div></div>
  }

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={download} disabled={!events.length}>
          Download JSON
        </button>
        <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>{events.length} events</span>
      </div>
      <div className="log">
        {events.map((ev, i) => (
          <div className="log-line" key={ev.event_id ?? i}>
            <span className="log-time">{ev.ts ? fmtTime(String(ev.ts)) : '—'}</span>
            <span className={`log-tag ${tagClass(ev.status, ev.type)}`}>{ev.type}</span>
            <span className="log-msg">
              {ev.message || ev.type}
              {ev.agent_id ? ` · ${ev.agent_id}` : ''}
              {ev.task_id ? ` · ${ev.task_id}` : ''}
              {ev.gateway_request_id ? ` · gw:${ev.gateway_request_id}` : ''}
              {ev.duration_ms != null ? ` · ${ev.duration_ms}ms` : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ModelTracePanel({ runId }: { runId: string }) {
  const [calls, setCalls] = useState<any[]>([])
  const [summary, setSummary] = useState<any | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [agentFilter, setAgentFilter] = useState<string>('')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [c, s] = await Promise.all([
          api.modelCalls(runId, { agentId: agentFilter || undefined, limit: 500 }),
          api.modelCallSummary(runId),
        ])
        if (cancelled) return
        setCalls(c.calls || [])
        setSummary(s)
        setError(null)
        setLoading(false)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load traces')
        setLoading(false)
      }
    }
    load()
    const t = setInterval(load, 3000)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [runId, agentFilter])

  if (loading && !calls.length) {
    return <div className="muted">Loading model-call traces…</div>
  }
  if (error && !calls.length) {
    return <div className="muted">Error: {error}</div>
  }

  return (
    <div>
      {summary && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12, fontSize: 13 }}>
          <span><b>{summary.total_calls}</b> calls</span>
          <span className="tag-ok">{summary.successful_calls} ok</span>
          <span className="tag-err">{summary.failed_calls} failed</span>
          <span>
            tokens{' '}
            {summary.total_tokens != null ? summary.total_tokens : '—'}
            {' '}(in {summary.tokens_input ?? '—'} / out {summary.tokens_output ?? '—'})
          </span>
          <span>
            cost{' '}
            {summary.cost_usd != null
              ? `$${Number(summary.cost_usd).toFixed(6)} (${summary.cost_source})`
              : 'n/a'}
          </span>
          <span>avg latency {summary.latency_ms_avg != null ? `${Math.round(summary.latency_ms_avg)}ms` : '—'}</span>
        </div>
      )}
      <div style={{ marginBottom: 8 }}>
        <label style={{ fontSize: 12, marginRight: 8 }}>Agent</label>
        <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}>
          <option value="">All</option>
          <option value="atlas-coder">atlas-coder</option>
          <option value="nova-coder">nova-coder</option>
          <option value="forge-coder">forge-coder</option>
        </select>
      </div>
      {!calls.length && <div className="muted">No model calls recorded for this run (simulated mode produces none).</div>}
      <div className="log">
        {calls.map((c) => (
          <div key={c.id} className="log-line" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', cursor: 'pointer' }} onClick={() => setOpenId(openId === c.id ? null : c.id)}>
              <span className="log-time">{c.started_at ? fmtTime(String(c.started_at)) : '—'}</span>
              <span className={`log-tag ${c.success ? 'tag-ok' : 'tag-err'}`}>{c.success ? 'ok' : 'error'}</span>
              <span className="log-msg">
                {c.agent_id || '—'} · {c.phase || c.strategy || 'call'} · {c.provider || '?'}/{c.model || '?'}
                {c.gateway_request_id ? ` · gw:${c.gateway_request_id}` : ''}
                {c.latency_ms != null ? ` · ${c.latency_ms}ms` : ''}
                {c.total_tokens != null ? ` · tok ${c.total_tokens}` : ' · tok n/a'}
                {c.cost_usd != null ? ` · $${Number(c.cost_usd).toFixed(6)}` : ''}
                {c.error ? ` · ${c.error}` : ''}
              </span>
            </div>
            {openId === c.id && (
              <pre style={{ fontSize: 11, opacity: 0.85, margin: '6px 0 0 0', whiteSpace: 'pre-wrap' }}>
{JSON.stringify(
  {
    id: c.id,
    task_id: c.task_id,
    strategy: c.strategy,
    attempt: c.attempt,
    is_retry: c.is_retry,
    tokens_input: c.tokens_input,
    tokens_output: c.tokens_output,
    tokens_cached: c.tokens_cached,
    cost_usd: c.cost_usd,
    cost_source: c.cost_source,
    http_status: c.http_status,
    gateway_request_id: c.gateway_request_id,
    metadata: c.metadata,
  },
  null,
  2,
)}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}



function TimelinePanel({ runId }: { runId: string }) {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [agentFilter, setAgentFilter] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await api.runTimeline(runId, agentFilter || undefined)
        if (cancelled) return
        setItems(data.items || [])
        setError(null)
        setLoading(false)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load timeline')
        setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [runId, agentFilter])

  if (loading) return <div className="muted">Loading timeline…</div>
  if (error) return <div className="muted" style={{ color: 'var(--danger)' }}>{error}</div>

  return (
    <div>
      <div style={{ marginBottom: 10, display: 'flex', gap: 8, alignItems: 'center' }}>
        <label className="muted" style={{ fontSize: 12 }}>Agent</label>
        <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className="input" style={{ maxWidth: 220 }}>
          <option value="">All</option>
          <option value="atlas-coder">Atlas</option>
          <option value="nova-coder">Nova</option>
          <option value="forge-coder">Forge</option>
        </select>
        <span className="muted" style={{ fontSize: 12 }}>{items.length} items</span>
      </div>
      {items.length === 0 && <div className="muted">No timeline items for this run.</div>}
      <div className="log">
        {items.map((it) => (
          <div className="log-line" key={it.id}>
            <span className="log-ts">{it.ts || '—'}</span>
            <span className={`log-tag ${it.status === 'error' ? 'tag-err' : it.kind === 'model_call' ? 'tag-info' : 'tag-ok'}`}>
              {it.kind === 'model_call' ? 'model' : (it.type || 'event')}
            </span>
            <span className="log-msg">
              {it.agent_id ? `[${it.agent_id}] ` : ''}
              {it.task_id ? `${it.task_id}: ` : ''}
              {it.message || ''}
              {it.gateway_request_id ? ` · req=${it.gateway_request_id}` : ''}
              {it.latency_ms != null ? ` · ${it.latency_ms}ms` : ''}
              {it.tokens_input != null || it.tokens_output != null
                ? ` · tok ${it.tokens_input ?? '—'}/${it.tokens_output ?? '—'}`
                : ''}
              {it.cost_usd != null ? ` · $${it.cost_usd}` : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}


function TargetIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  )
}
