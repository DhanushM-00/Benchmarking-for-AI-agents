import { Link } from 'react-router-dom'
import {
  CheckCircle2,
  Clock,
  Cpu,
  Dices,
  Eye,
  Layers,
  Lock,
  RotateCcw,
  Scale,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useAsync, useLocalStorage } from '@/hooks/useAsync'
import { DEFAULT_FAIRNESS } from '@/lib/mockData'
import { fmtNum } from '@/lib/format'
import { Card } from '@/components/ui/Card'
import { Badge, Button, Callout, Field, Progress, Switch } from '@/components/ui/Primitives'
import type { FairnessConfig } from '@/types'

const ENFORCEMENTS = [
  {
    icon: Layers,
    title: 'Same task dataset',
    body: 'A single dataset identifier and content hash are resolved before dispatch and re-verified after the run. Agents cannot be handed different tasks.',
  },
  {
    icon: Lock,
    title: 'Same input instructions',
    body: 'One prompt template is rendered per task and broadcast to every agent. Agent-specific prompt edits are rejected by the orchestrator.',
  },
  {
    icon: Clock,
    title: 'Same time limit',
    body: 'The sandbox supervisor enforces a hard wall-clock ceiling per task for every agent, so a fast agent never gets more compute than a slow one.',
  },
  {
    icon: Cpu,
    title: 'Same execution environment',
    body: 'Identical container image, seeded fixtures, identical filesystem and CPU/memory limits. Network policy is applied to the whole run.',
  },
  {
    icon: Scale,
    title: 'Same scoring rules',
    body: 'One scorer version and one metric-weight vector. Hidden unit tests, DeepEval judges and custom metrics all run through the same pipeline.',
  },
  {
    icon: RotateCcw,
    title: 'Repeated runs',
    body: 'Each task is repeated where practical. The median score is reported and the variance is published, so a lucky single attempt cannot win.',
  },
]

export default function Fairness() {
  const { data: runs } = useAsync(() => api.listRuns(), [])
  const [fairness, setFairness] = useLocalStorage<FairnessConfig>('bifrost.fairness', DEFAULT_FAIRNESS)

  const completed = (runs ?? []).filter((r) => r.status === 'completed')
  const avgScore = completed.length
    ? Math.round(completed.reduce((s, r) => s + (r.fairness_report?.score ?? 0), 0) / completed.length)
    : 0

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head page-head-row">
        <div>
          <div className="page-eyebrow">System</div>
          <h1 className="page-title">Fair Agent Testing Engine</h1>
          <p className="page-desc">
            The differentiator. Ordinary agent comparisons break because each agent is tested with
            different tasks, different budgets and different judges. Bifrost enforces parity before a
            single token is spent, and publishes the evidence alongside every result.
          </p>
        </div>
        <Button icon={<RotateCcw />} onClick={() => setFairness(DEFAULT_FAIRNESS)}>
          Restore defaults
        </Button>
      </div>

      <div className="grid grid-4">
        <div className="stat" style={{ ['--stat-accent' as string]: 'var(--violet)' }}>
          <div className="stat-label">
            <ShieldCheck size={13} /> Fairness integrity
          </div>
          <div className="stat-value">
            {avgScore}
            <span className="unit">%</span>
          </div>
          <div className="stat-foot">across {completed.length} completed runs</div>
        </div>
        <div className="stat" style={{ ['--stat-accent' as string]: 'var(--teal)' }}>
          <div className="stat-label">
            <CheckCircle2 size={13} /> Parity checks
          </div>
          <div className="stat-value">
            10
            <span className="unit">/10</span>
          </div>
          <div className="stat-foot">enforced per run</div>
        </div>
        <div className="stat" style={{ ['--stat-accent' as string]: 'var(--accent)' }}>
          <div className="stat-label">
            <Eye size={13} /> Blinded judging
          </div>
          <div className="stat-value">
            {fairness.blinded_evaluation ? 'On' : 'Off'}
          </div>
          <div className="stat-foot">judge sees no agent identity</div>
        </div>
        <div className="stat" style={{ ['--stat-accent' as string]: 'var(--amber)' }}>
          <div className="stat-label">
            <Dices size={13} /> Repeats per task
          </div>
          <div className="stat-value">
            ×{fairness.repeats}
          </div>
          <div className="stat-foot">median reported, variance published</div>
        </div>
      </div>

      <Card title="What the engine enforces" subtitle="Six guarantees, all applied before execution">
        <div className="grid grid-3" style={{ gap: 20 }}>
          {ENFORCEMENTS.map((e) => (
            <div key={e.title} className="row" style={{ gap: 11, alignItems: 'flex-start' }}>
              <div
                style={{
                  width: 30, height: 30, borderRadius: 9, display: 'grid', placeItems: 'center',
                  background: 'var(--violet-soft)', border: '1px solid rgba(167,139,250,0.28)',
                  color: 'var(--violet)', flexShrink: 0,
                }}
              >
                <e.icon size={15} />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{e.title}</div>
                <div className="small muted" style={{ marginTop: 3 }}>
                  {e.body}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-2" style={{ alignItems: 'start' }}>
        <Card title="Global fairness configuration" subtitle="Defaults applied to every new run">
          <div className="stack" style={{ gap: 16 }}>
            <Field label="Time limit per task" hint="Wall-clock ceiling enforced by the supervisor">
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
                <span className="mono nowrap" style={{ width: 52, textAlign: 'right' }}>
                  {fairness.time_limit_per_task_sec}s
                </span>
              </div>
            </Field>

            <Field label="Token budget per task" hint="Hard cap shared by all agents">
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
                <span className="mono nowrap" style={{ width: 66, textAlign: 'right' }}>
                  {fmtNum(fairness.max_tokens_per_task)}
                </span>
              </div>
            </Field>

            <Field label="Repeats" hint="How many independent attempts per task">
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
                <span className="mono nowrap" style={{ width: 52, textAlign: 'right' }}>
                  ×{fairness.repeats}
                </span>
              </div>
            </Field>

            <div className="grid grid-2" style={{ gap: 12 }}>
              <Field label="Isolation">
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
              <Field label="Network policy">
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
                  <option value="none">None</option>
                  <option value="allowlist">Allowlist</option>
                  <option value="full">Full</option>
                </select>
              </Field>
            </div>

            <div className="stack" style={{ gap: 12 }}>
              <label className="row" style={{ justifyContent: 'space-between', cursor: 'pointer' }}>
                <span>
                  <span className="strong" style={{ fontSize: 13 }}>Blinded evaluation</span>
                  <div className="tiny muted">Judge prompts omit agent and model identity</div>
                </span>
                <Switch
                  checked={fairness.blinded_evaluation}
                  onChange={(v) => setFairness({ ...fairness, blinded_evaluation: v })}
                  label="Blinded evaluation"
                />
              </label>
              <label className="row" style={{ justifyContent: 'space-between', cursor: 'pointer' }}>
                <span>
                  <span className="strong" style={{ fontSize: 13 }}>Randomize task order</span>
                  <div className="tiny muted">Same seed for every agent</div>
                </span>
                <Switch
                  checked={fairness.randomize_task_order}
                  onChange={(v) => setFairness({ ...fairness, randomize_task_order: v })}
                  label="Randomize task order"
                />
              </label>
            </div>
          </div>
        </Card>

        <div className="stack">
          <Card title="Parity audit trail" subtitle="Fairness score per run" flush>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Agents</th>
                    <th className="num">Repeats</th>
                    <th style={{ width: 150 }}>Fairness</th>
                    <th className="num">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {(runs ?? []).map((r) => {
                    const score = r.fairness_report?.score ?? 0
                    const fails = (r.fairness_report?.checks ?? []).filter((c) => c.status === 'fail').length
                    const warns = (r.fairness_report?.checks ?? []).filter((c) => c.status === 'warn').length
                    return (
                      <tr key={r.id}>
                        <td>
                          <Link to={`/runs/${r.id}`} className="strong">
                            {r.name}
                          </Link>
                          <div className="tiny muted">{r.benchmark_name}</div>
                        </td>
                        <td className="muted">{r.agent_ids.length}</td>
                        <td className="num muted">×{r.fairness.repeats}</td>
                        <td>
                          <div className="row" style={{ gap: 8 }}>
                            <Progress
                              value={score}
                              color={score >= 95 ? 'var(--teal)' : score >= 70 ? 'var(--amber)' : 'var(--rose)'}
                              className="w-full"
                            />
                            <span className="mono tiny strong">{score}%</span>
                          </div>
                        </td>
                        <td className="num">
                          {fails > 0 ? (
                            <Badge tone="rose">
                              <XCircle /> {fails} failed
                            </Badge>
                          ) : warns > 0 ? (
                            <Badge tone="amber">
                              <Clock /> {warns} warning
                            </Badge>
                          ) : (
                            <Badge tone="teal">
                              <CheckCircle2 /> clean
                            </Badge>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          <Callout tone="amber" icon={<Scale size={15} style={{ marginTop: 1 }} />}>
            <div>
              <strong>Fair ≠ identical outcomes.</strong> Agents will still score differently — that is
              the signal. What the engine removes is the confound where a difference comes from the
              harness rather than the agent.
            </div>
          </Callout>
        </div>
      </div>
    </div>
  )
}
