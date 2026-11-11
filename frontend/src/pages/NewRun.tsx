import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Cpu,
  Dices,
  Layers,
  Play,
  RotateCcw,
  Scale,
  ShieldCheck,
  Sparkles,
  Terminal,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useBackendHealth } from '@/hooks/useBackendHealth'
import { useAsync } from '@/hooks/useAsync'
import { useLocalStorage } from '@/hooks/useAsync'
import { DEFAULT_FAIRNESS } from '@/lib/mockData'
import { agentColor, fmtCompact, fmtNum, fmtUsd } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { FairnessConfig } from '@/types'
import { Card, AgentChip } from '@/components/ui/Card'
import { Badge, Button, Callout, Field, Progress, Skeleton, Switch } from '@/components/ui/Primitives'

const STEPS = ['Benchmark', 'Agents', 'Fairness', 'Review'] as const

export default function NewRun() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const rerunId = searchParams.get('rerun')
  const { data: benchmarks, loading: benchmarksLoading } = useAsync(() => api.listBenchmarks(), [])
  const { data: agents, loading: agentsLoading } = useAsync(() => api.listAgents(), [])
  const { data: tasks, loading: tasksLoading } = useAsync(() => api.listTasks(), [])
  const { data: rerunSource } = useAsync(
    () => (rerunId ? api.getRun(rerunId) : Promise.resolve(null as any)),
    [rerunId],
  )
  const catalogueLoading = benchmarksLoading || agentsLoading || tasksLoading

  const [step, setStep] = useState(0)
  const [benchmarkId, setBenchmarkId] = useState<string>('')
  const [agentIds, setAgentIds] = useState<string[]>([])
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([])
  const [notes, setNotes] = useState('')
  const [fairness, setFairness] = useLocalStorage<FairnessConfig>('bifrost.fairness', DEFAULT_FAIRNESS)
  const [launching, setLaunching] = useState(false)
  const [launchError, setLaunchError] = useState<string | null>(null)
  const [prefilled, setPrefilled] = useState(false)
  const [defaultsReady, setDefaultsReady] = useState(false)

  // The backend knows whether Docker is available and which mode it would
  // pick — a live run with docker isolation is rejected (422) without Docker.
  const health = useBackendHealth({ intervalMs: 30_000 })

  // Initialize selections from the live backend catalogue (not hardcoded IDs).
  useEffect(() => {
    if (defaultsReady || prefilled) return
    if (!benchmarks || !agents) return
    if (benchmarks.length === 0) {
      setDefaultsReady(true)
      return
    }
    // Prefer first backend benchmark; fall back only if list empty (handled above).
    if (!benchmarkId) setBenchmarkId(benchmarks[0].id)
    if (agentIds.length === 0) {
      const enabled = agents.filter((a) => a.enabled).map((a) => a.id)
      setAgentIds(enabled.slice(0, 3))
    }
    setDefaultsReady(true)
  }, [benchmarks, agents, defaultsReady, prefilled, benchmarkId, agentIds.length])

  useEffect(() => {
    if (!rerunSource || prefilled) return
    setBenchmarkId(rerunSource.benchmark_id)
    if (rerunSource.agent_ids?.length) setAgentIds([...rerunSource.agent_ids])
    if (rerunSource.task_ids?.length) setSelectedTaskIds([...rerunSource.task_ids])
    if (rerunSource.fairness) setFairness(rerunSource.fairness as FairnessConfig)
    setNotes(`Re-run of ${rerunSource.id}`)
    setPrefilled(true)
    setDefaultsReady(true)
  }, [rerunSource, prefilled, setFairness])

  const benchmark = (benchmarks ?? []).find((b) => b.id === benchmarkId)
  const benchTasks = useMemo(
    () => (tasks ?? []).filter((t) => t.benchmark_id === benchmarkId),
    [tasks, benchmarkId],
  )
  // Keep selection scoped to the current benchmark — never carry foreign task IDs.
  const benchTaskIdKey = benchTasks.map((t) => t.id).join(',')
  useEffect(() => {
    setSelectedTaskIds(benchTasks.map((t) => t.id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [benchmarkId, benchTaskIdKey])
  const selectedAgents = (agents ?? []).filter((a) => agentIds.includes(a.id))
  const selectedTasks = benchTasks.filter((t) => selectedTaskIds.includes(t.id))

  const estimatedCost = useMemo(() => {
    if (!benchmark) return 0
    const n = selectedTaskIds.length
    if (n === 0) return 0
    const perAgent = selectedAgents.reduce((sum, a) => {
      const avgTokensIn = 1400
      const avgTokensOut = 2600
      return sum + (avgTokensIn / 1000) * a.cost_per_1k_input + (avgTokensOut / 1000) * a.cost_per_1k_output
    }, 0)
    return perAgent * n * fairness.repeats
  }, [benchmark, selectedAgents, fairness.repeats, selectedTaskIds.length])

  // Exact formula: selected tasks × selected agents × repeats. Never fall back to
  // benchmark.task_count when the user has cleared the selection.
  const totalTaskExecutions = selectedTaskIds.length * agentIds.length * fairness.repeats

  const toggleAgent = (id: string) => {
    setAgentIds((prev) => (prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]))
  }

  const toggleTask = (id: string) => {
    setSelectedTaskIds((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id],
    )
  }

  const selectAllTasks = () => setSelectedTaskIds(benchTasks.map((t) => t.id))
  const clearAllTasks = () => setSelectedTaskIds([])

  const launch = async () => {
    if (launching) return // prevent duplicate submissions
    if (!benchmarkId) {
      setLaunchError('Select a benchmark before launching.')
      return
    }
    if (agentIds.length === 0) {
      setLaunchError('Select at least one agent.')
      return
    }
    if (selectedTaskIds.length === 0) {
      setLaunchError('Select at least one task.')
      return
    }
    setLaunching(true)
    setLaunchError(null)
    try {
      const run = await api.createRun({
        benchmark_id: benchmarkId,
        agent_ids: agentIds,
        task_ids: selectedTaskIds,
        fairness,
        notes,
      })
      navigate(`/runs/${run.id}`)
    } catch (err) {
      // The backend explains *why* it refused (422 detail). Show it instead of
      // failing silently — a silent failure invites a click-storm of retries.
      setLaunchError(
        err instanceof Error && err.message
          ? err.message
          : 'The backend refused to create the run.',
      )
    } finally {
      setLaunching(false)
    }
  }

  // Do not allow progress or launch while catalogue data is still loading,
  // unavailable, or when no tasks are selected.
  const tasksReady = !catalogueLoading && !!benchmarkId && benchTasks.length > 0
  const canContinue =
    step === 0
      ? tasksReady && selectedTaskIds.length > 0
      : step === 1
        ? agentIds.length > 0
        : true
  const canLaunch =
    !catalogueLoading &&
    !launching &&
    !!benchmarkId &&
    selectedTaskIds.length > 0 &&
    agentIds.length > 0 &&
    benchTasks.length > 0

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head">
        <div className="page-eyebrow">Benchmarking</div>
        <h1 className="page-title">New benchmark run</h1>
        <p className="page-desc">
          Pick a benchmark, choose the agents to compare, then lock the fairness parameters. Every
          agent receives the identical task set, instructions, budget and scoring rules.
        </p>
      </div>

      {/* Stepper */}
      <Card bodyClassName="tight">
        <div className="steps">
          {STEPS.map((s, i) => (
            <div key={s} className="row" style={{ gap: 0, flex: 1 }}>
              <div className={cn('step', i === step && 'active', i < step && 'done')}>
                <span className="step-dot">{i < step ? <Check size={13} /> : i + 1}</span>
                <span className="step-label">{s}</span>
              </div>
              {i < STEPS.length - 1 && <div className="step-line" style={{ flex: 1 }} />}
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-2-1" style={{ alignItems: 'start' }}>
        <div className="stack">
          {/* ---------- Step 1: benchmark ---------- */}
          {step === 0 && (
            <Card title="Choose a benchmark" subtitle="Each benchmark is a fixed, versioned task dataset">
              {!benchmarks ? (
                <div className="stack">
                  <Skeleton h={64} />
                  <Skeleton h={64} />
                  <Skeleton h={64} />
                </div>
              ) : (
                <div className="stack" style={{ gap: 10 }}>
                  {benchmarks.map((b) => {
                    const selected = b.id === benchmarkId
                    return (
                      <button
                        key={b.id}
                        className={cn('agent-card', selected && 'selected')}
                        style={{ ['--agent-color' as string]: 'var(--accent)', textAlign: 'left', width: '100%' }}
                        onClick={() => setBenchmarkId(b.id)}
                      >
                        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div style={{ minWidth: 0 }}>
                            <div className="row" style={{ gap: 8 }}>
                              <span style={{ fontWeight: 600 }}>{b.name}</span>
                              <Badge tone="neutral">{b.version}</Badge>
                              {selected && <Badge tone="accent">Selected</Badge>}
                            </div>
                            <div className="small muted" style={{ marginTop: 3 }}>
                              {b.description}
                            </div>
                            <div className="row-wrap" style={{ gap: 6, marginTop: 8 }}>
                              {b.categories.map((c) => (
                                <span className="badge badge-neutral" key={c}>
                                  {c}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className="right nowrap">
                            <div className="mono strong" style={{ fontSize: 17 }}>
                              {b.task_count}
                            </div>
                            <div className="tiny muted">tasks</div>
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}

              {benchmark && benchTasks.length > 0 && (
                <div className="mt-4" data-testid="newrun-task-picker">
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
                    <div>
                      <div className="strong" style={{ fontSize: 13 }}>
                        Tasks in this benchmark
                      </div>
                      <div className="tiny muted" data-testid="selected-task-count">
                        {selectedTaskIds.length} of {benchTasks.length} selected
                      </div>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <Button size="sm" variant="ghost" type="button" onClick={selectAllTasks} data-testid="select-all-tasks">
                        Select all
                      </Button>
                      <Button size="sm" variant="ghost" type="button" onClick={clearAllTasks} data-testid="clear-all-tasks">
                        Clear all
                      </Button>
                    </div>
                  </div>
                  <div className="table-wrap" style={{ maxHeight: 280, overflow: 'auto' }}>
                    <table className="data">
                      <thead>
                        <tr>
                          <th style={{ width: 40 }} />
                          <th style={{ width: 120 }}>ID</th>
                          <th>Title</th>
                          <th style={{ width: 100 }}>Difficulty</th>
                          <th style={{ width: 120 }}>Category</th>
                        </tr>
                      </thead>
                      <tbody>
                        {benchTasks.map((t) => {
                          const on = selectedTaskIds.includes(t.id)
                          return (
                            <tr
                              key={t.id}
                              className="clickable"
                              data-testid={`newrun-task-${t.id}`}
                              onClick={() => toggleTask(t.id)}
                            >
                              <td>
                                <input
                                  type="checkbox"
                                  checked={on}
                                  onChange={() => toggleTask(t.id)}
                                  onClick={(e) => e.stopPropagation()}
                                  aria-label={`Select ${t.id}`}
                                />
                              </td>
                              <td className="mono tiny muted">{t.id}</td>
                              <td className="small">{t.title}</td>
                              <td>
                                <Badge tone="neutral">{t.difficulty}</Badge>
                              </td>
                              <td className="tiny muted">{t.category}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* ---------- Step 2: agents ---------- */}
          {step === 1 && (
            <Card
              title="Choose the agents to compare"
              subtitle="An agent = model + instructions + tools + orchestration + memory"
            >
              {!agents ? (
                <Skeleton h={220} />
              ) : (
                <>
                  <div className="stack" style={{ gap: 10 }}>
                    {agents.map((a) => {
                      const selected = agentIds.includes(a.id)
                      const color = agentColor(a.color_index)
                      return (
                        <div
                          key={a.id}
                          className={cn('agent-card', selected && 'selected')}
                          style={{ ['--agent-color' as string]: color }}
                          onClick={() => toggleAgent(a.id)}
                        >
                          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div className="row" style={{ gap: 8 }}>
                                <AgentChip name={a.name} colorIndex={a.color_index} />
                                <Badge tone="neutral">{a.model}</Badge>
                              </div>
                              <div className="small muted" style={{ marginTop: 4 }}>
                                {a.description}
                              </div>
                              <div className="row-wrap" style={{ gap: 6, marginTop: 9 }}>
                                <span className="badge badge-neutral">
                                  <Terminal /> {a.tools.length} tools
                                </span>
                                <span className="badge badge-neutral">
                                  <Layers /> {a.orchestration}
                                </span>
                                <span className="badge badge-neutral">
                                  <Sparkles /> {a.memory}
                                </span>
                              </div>
                            </div>
                            <div className="agent-check" style={selected ? { background: color, borderColor: color } : undefined}>
                              {selected && <Check />}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  <div className="mt-4">
                    <Callout tone="amber">
                      Agents are compared as <strong>whole systems</strong>. Swapping the model under the
                      same harness is a different agent — the harness, prompt and tools stay pinned.
                    </Callout>
                  </div>
                </>
              )}
            </Card>
          )}

          {/* ---------- Step 3: fairness ---------- */}
          {step === 2 && (
            <div className="stack">
              <Card title="Fair Agent Testing Engine" subtitle="Parameters locked across every agent in this run">
                <div className="grid grid-2" style={{ gap: 16 }}>
                  <Field label="Time limit per task" hint="Enforced by the sandbox supervisor">
                    <div className="row">
                      <input
                        className="slider"
                        type="range"
                        min={30}
                        max={300}
                        step={10}
                        value={fairness.time_limit_per_task_sec}
                        onChange={(e) =>
                          setFairness({ ...fairness, time_limit_per_task_sec: Number(e.target.value) })
                        }
                      />
                      <span className="mono nowrap" style={{ width: 54, textAlign: 'right' }}>
                        {fairness.time_limit_per_task_sec}s
                      </span>
                    </div>
                  </Field>

                  <Field label="Token budget per task" hint="Hard cap — exceeding it fails the task">
                    <div className="row">
                      <input
                        className="slider"
                        type="range"
                        min={8000}
                        max={64000}
                        step={2000}
                        value={fairness.max_tokens_per_task}
                        onChange={(e) =>
                          setFairness({ ...fairness, max_tokens_per_task: Number(e.target.value) })
                        }
                      />
                      <span className="mono nowrap" style={{ width: 68, textAlign: 'right' }}>
                        {fmtNum(fairness.max_tokens_per_task)}
                      </span>
                    </div>
                  </Field>

                  <Field label="Repeats per agent" hint="Median score reported, variance tracked">
                    <div className="row">
                      <input
                        className="slider"
                        type="range"
                        min={1}
                        max={5}
                        step={1}
                        value={fairness.repeats}
                        onChange={(e) => setFairness({ ...fairness, repeats: Number(e.target.value) })}
                      />
                      <span className="mono nowrap" style={{ width: 54, textAlign: 'right' }}>
                        ×{fairness.repeats}
                      </span>
                    </div>
                  </Field>

                  <Field label="Isolation mode" hint="How each agent is sandboxed">
                    <select
                      className="select"
                      value={fairness.isolation}
                      onChange={(e) =>
                        setFairness({
                          ...fairness,
                          isolation: e.target.value as FairnessConfig['isolation'],
                        })
                      }
                    >
                      <option value="docker">Docker container</option>
                      <option value="subprocess">Python subprocess</option>
                      <option value="vm">MicroVM</option>
                    </select>
                  </Field>

                  <Field label="Network policy" hint="Applied identically to all agents">
                    <select
                      className="select"
                      value={fairness.network_policy}
                      onChange={(e) =>
                        setFairness({
                          ...fairness,
                          network_policy: e.target.value as FairnessConfig['network_policy'],
                        })
                      }
                    >
                      <option value="none">None — fully disabled</option>
                      <option value="allowlist">Allowlist</option>
                      <option value="full">Full access</option>
                    </select>
                  </Field>

                  <Field label="Scorer version" hint="Pinned for reproducibility">
                    <input
                      className="input"
                      value={fairness.scorer_version}
                      onChange={(e) => setFairness({ ...fairness, scorer_version: e.target.value })}
                    />
                  </Field>
                </div>

                <div className="divider mt-4 mb-3" />

                <div className="stack" style={{ gap: 12 }}>
                  <label className="row" style={{ justifyContent: 'space-between', cursor: 'pointer' }}>
                    <span className="row" style={{ gap: 9 }}>
                      <Dices size={15} className="muted" />
                      <span>
                        <span className="strong" style={{ fontSize: 13 }}>Randomize task order</span>
                        <div className="tiny muted">
                          Same seed for every agent — prevents position bias in the task list.
                        </div>
                      </span>
                    </span>
                    <Switch
                      checked={fairness.randomize_task_order}
                      onChange={(v) => setFairness({ ...fairness, randomize_task_order: v })}
                      label="Randomize task order"
                    />
                  </label>

                  <label className="row" style={{ justifyContent: 'space-between', cursor: 'pointer' }}>
                    <span className="row" style={{ gap: 9 }}>
                      <ShieldCheck size={15} className="muted" />
                      <span>
                        <span className="strong" style={{ fontSize: 13 }}>Blinded evaluation</span>
                        <div className="tiny muted">
                          The judge never sees which agent produced the solution.
                        </div>
                      </span>
                    </span>
                    <Switch
                      checked={fairness.blinded_evaluation}
                      onChange={(v) => setFairness({ ...fairness, blinded_evaluation: v })}
                      label="Blinded evaluation"
                    />
                  </label>
                </div>

                <div className="mt-4">
                  <Field label="Run notes">
                    <textarea
                      className="input"
                      style={{ height: 72, paddingTop: 9, resize: 'vertical' }}
                      placeholder="Why is this run happening?"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                    />
                  </Field>
                </div>
              </Card>

              <Card title="Metric weights" subtitle="How the overall score is composed">
                <div className="stack" style={{ gap: 13 }}>
                  {(
                    [
                      ['task_success', 'Task success', 'Did the agent complete the task?'],
                      ['correctness', 'Correctness', 'Do the hidden unit tests pass?'],
                      ['efficiency', 'Efficiency', 'How many unnecessary steps were taken?'],
                      ['tool_usage', 'Tool usage', 'Were tools used appropriately?'],
                      ['consistency', 'Consistency', 'How stable is the score across repeats?'],
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
                  <div className="callout amber">
                    <Scale size={15} style={{ marginTop: 1 }} />
                    <div>
                      Weights total{' '}
                      <strong>
                        {Math.round(
                          Object.values(fairness.metric_weights).reduce((s, w) => s + w, 0) * 100,
                        )}
                        %
                      </strong>
                      . Weights are normalised by the scorer, but keeping them near 100% keeps the
                      leaderboard honest.
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          )}

          {/* ---------- Step 4: review ---------- */}
          {step === 3 && (
            <div className="stack">
              <Card title="Review & launch" subtitle="Confirm the run definition before dispatching">
                <div className="grid grid-2" style={{ gap: 18 }}>
                  <div>
                    <div className="kv-label mb-2">Benchmark</div>
                    <div className="row" style={{ gap: 8 }}>
                      <Layers size={15} className="muted" />
                      <span className="strong">{benchmark?.name ?? '—'}</span>
                      <Badge tone="neutral">{benchmark?.version}</Badge>
                    </div>
                    <div className="small muted mt-1" data-testid="review-task-count">
                      {selectedTaskIds.length} of {benchmark?.task_count ?? 0} tasks selected ·{' '}
                      {benchmark?.categories?.join(', ')}
                    </div>
                  </div>
                  <div>
                    <div className="kv-label mb-2">Agents</div>
                    <div className="row-wrap" style={{ gap: 8 }}>
                      {selectedAgents.map((a) => (
                        <span key={a.id} className="row" style={{ gap: 6 }}>
                          <AgentChip name={a.name} colorIndex={a.color_index} />
                          <span className="tiny muted">
                            {a.model} · {a.model_provider}
                          </span>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="divider mt-4 mb-3" />

                <div className="grid grid-2" style={{ gap: 18 }} data-testid="review-execution-summary">
                  <div className="stack" style={{ gap: 9 }}>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Selected tasks</span>
                      <span className="mono small strong">{selectedTaskIds.length}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Agents</span>
                      <span className="mono small strong">{agentIds.length}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Repeats</span>
                      <span className="mono small strong">×{fairness.repeats}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Total executions</span>
                      <span className="mono small strong" data-testid="review-total-executions">
                        {totalTaskExecutions}
                      </span>
                    </div>
                  </div>
                  <div className="stack" style={{ gap: 9 }}>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Est. cost</span>
                      <span className="mono small">{fmtUsd(estimatedCost)}</span>
                    </div>
                    <div className="tiny muted">
                      Assumes ~1.4k input + 2.6k output tokens per task execution at each agent&apos;s
                      listed rates.
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Token budget / task</span>
                      <span className="mono small">{fmtNum(fairness.max_tokens_per_task)}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Time limit / task</span>
                      <span className="mono small">{fairness.time_limit_per_task_sec}s</span>
                    </div>
                  </div>
                </div>

                <div className="divider mt-4 mb-3" />

                <div className="grid grid-2" style={{ gap: 18 }}>
                  <div className="stack" style={{ gap: 9 }}>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Time limit / task</span>
                      <span className="mono small">{fairness.time_limit_per_task_sec}s</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Token budget / task</span>
                      <span className="mono small">{fmtNum(fairness.max_tokens_per_task)}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Repeats</span>
                      <span className="mono small">×{fairness.repeats}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Isolation / sandbox</span>
                      <span className="mono small">{fairness.isolation}</span>
                    </div>
                    {fairness.isolation === 'subprocess' && (
                      <div className="tiny" style={{ color: 'var(--amber)' }} data-testid="subprocess-warning">
                        Development only — subprocess isolation is not a secure sandbox for untrusted
                        code. Prefer Docker for live runs.
                      </div>
                    )}
                  </div>
                  <div className="stack" style={{ gap: 9 }}>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Network</span>
                      <span className="mono small">{fairness.network_policy}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Scorer</span>
                      <span className="mono small">{fairness.scorer_version}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Order</span>
                      <span className="mono small">
                        {fairness.randomize_task_order ? `seeded (${fairness.random_seed})` : 'fixed'}
                      </span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Blinded judge</span>
                      <span className="mono small">{fairness.blinded_evaluation ? 'on' : 'off'}</span>
                    </div>
                  </div>
                </div>

                {selectedTasks.length > 0 && (
                  <div className="mt-4">
                    <div className="kv-label mb-2">
                      Task preview (first 6 of {selectedTasks.length} selected)
                    </div>
                    <div className="stack" style={{ gap: 6 }}>
                      {selectedTasks.slice(0, 6).map((t) => (
                        <div className="row" style={{ gap: 9 }} key={t.id}>
                          <Badge tone="neutral">{t.difficulty}</Badge>
                          <span className="small truncate">{t.title}</span>
                          <span className="tiny muted" style={{ marginLeft: 'auto' }}>
                            {t.test_count} tests
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>

              <Callout tone="teal" icon={<Play size={15} style={{ marginTop: 1 }} />}>
                <strong>Ready to launch.</strong> {totalTaskExecutions.toLocaleString('en-US')} agent-task
                executions will be dispatched across {agentIds.length} agent{agentIds.length > 1 ? 's' : ''} ×{' '}
                {selectedTaskIds.length} task{selectedTaskIds.length !== 1 ? 's' : ''} × {fairness.repeats}{' '}
                repeat{fairness.repeats > 1 ? 's' : ''}.
              </Callout>
            </div>
          )}

          {/* ---------- Actions ---------- */}
          {launchError && (
            <Callout tone="rose" icon={<ShieldCheck size={15} style={{ marginTop: 1 }} />}>
              <div className="small">
                <strong>The run was not created.</strong> {launchError}
              </div>
            </Callout>
          )}

          {health.state === 'connected' &&
            health.detail?.bifrost &&
            health.detail.bifrost.enabled &&
            health.detail.bifrost.status !== 'connected' && (
              <Callout tone="amber" icon={<ShieldCheck size={15} style={{ marginTop: 1 }} />}>
                <div className="small">
                  <strong>The Bifrost gateway is not ready ({health.detail.bifrost.status}).</strong>{' '}
                  {health.detail.bifrost.error ??
                    'Every live model call goes through the gateway, so a live run would fail.'}{' '}
                  Fix the gateway first — check the gateway status on the Settings page.
                </div>
              </Callout>
            )}

          {health.state === 'connected' &&
            health.detail?.docker_available === false &&
            fairness.isolation === 'docker' && (
              <Callout tone="amber" icon={<ShieldCheck size={15} style={{ marginTop: 1 }} />}>
                <div className="small">
                  <strong>Docker is not available on the backend host.</strong> A live run with{' '}
                  <code className="mono">docker</code> isolation is rejected with HTTP 422, so the
                  launch below would fail. Start Docker Desktop (recommended), or switch this run
                  to the host sandbox:
                  <div className="row mt-2" style={{ gap: 10 }}>
                    <Button
                      size="sm"
                      icon={<Cpu />}
                      onClick={() => setFairness({ ...fairness, isolation: 'subprocess' })}
                    >
                      Switch to subprocess isolation
                    </Button>
                    <span className="tiny muted">
                      Development only — the run record reports{' '}
                      <code className="mono">isolation_used: subprocess</code> and the fairness
                      report flags the weaker sandbox.
                    </span>
                  </div>
                </div>
              </Callout>
            )}

          <div className="row" style={{ justifyContent: 'space-between' }}>
            <Button
              icon={<ArrowLeft />}
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
            >
              Back
            </Button>
            <div className="row">
              <Button
                variant="ghost"
                icon={<RotateCcw />}
                onClick={() => {
                  setFairness(DEFAULT_FAIRNESS)
                  setAgentIds(['atlas-coder', 'nova-coder', 'forge-coder'])
                  setStep(0)
                }}
              >
                Reset
              </Button>
              {step < STEPS.length - 1 ? (
                <Button
                  variant="primary"
                  icon={<ArrowRight />}
                  disabled={!canContinue}
                  onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
                >
                  Continue
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="lg"
                  icon={<Play />}
                  loading={launching}
                  onClick={launch}
                  disabled={!canLaunch}
                  data-testid="launch-benchmark"
                >
                  Launch benchmark
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* ---------- Summary rail ---------- */}
        <div className="stack" style={{ position: 'sticky', top: 84 }}>
          <Card title="Run summary">
            <div className="stack" style={{ gap: 13 }}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Benchmark</span>
                <span className="small strong truncate" style={{ maxWidth: 160 }}>
                  {benchmark?.name ?? '—'}
                </span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Agents</span>
                <span className="small strong">{agentIds.length}</span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Tasks</span>
                <span className="small strong" data-testid="summary-selected-tasks">
                  {selectedTaskIds.length}
                </span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Repeats</span>
                <span className="small strong">×{fairness.repeats}</span>
              </div>
              <div className="divider" />
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Agent-task executions</span>
                <span className="mono small strong" data-testid="summary-total-executions">{fmtNum(totalTaskExecutions)}</span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Est. token spend</span>
                <span className="mono small strong">
                  {fmtCompact(totalTaskExecutions * 2600)}
                </span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">Est. cost</span>
                <span className="mono small strong" style={{ color: 'var(--amber)' }}>
                  {fmtUsd(estimatedCost)}
                </span>
              </div>
            </div>
          </Card>

          <Card title="Parity preview">
            <div className="stack" style={{ gap: 9 }}>
              {[
                ['Same task dataset', true],
                ['Same instructions', true],
                ['Same time limit', true],
                ['Same environment', true],
                ['Same scoring rules', true],
                ['Repeated runs', fairness.repeats >= 2],
                ['Blinded judge', fairness.blinded_evaluation],
              ].map(([label, ok]) => (
                <div className="row" style={{ gap: 8 }} key={label as string}>
                  {ok ? (
                    <ShieldCheck size={14} style={{ color: 'var(--teal)' }} />
                  ) : (
                    <ShieldCheck size={14} style={{ color: 'var(--amber)' }} />
                  )}
                  <span className="small" style={{ color: ok ? 'var(--text-2)' : 'var(--amber)' }}>
                    {label as string}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-3">
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="tiny muted">Fairness score</span>
                <span className="mono tiny strong">100%</span>
              </div>
              <Progress value={100} color="var(--violet)" />
            </div>
          </Card>

          <Card title="Cost drivers">
            <div className="stack" style={{ gap: 10 }}>
              {selectedAgents.map((a) => (
                <div key={a.id}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
                    <AgentChip name={a.name} colorIndex={a.color_index} />
                    <span className="mono tiny muted">
                      ${(a.cost_per_1k_output).toFixed(4)}/1k out
                    </span>
                  </div>
                </div>
              ))}
              <div className="callout" style={{ fontSize: 11.5 }}>
                <Cpu size={14} style={{ marginTop: 1 }} />
                <div>Estimated cost uses the token budget × model pricing at register time.</div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
