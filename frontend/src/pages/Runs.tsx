import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Filter, Play, Search, Square } from 'lucide-react'
import { api } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { fmtDateTime, fmtNum, fmtUsd, relTime } from '@/lib/format'
import { Card, AgentChip } from '@/components/ui/Card'
import { Badge, Button, EmptyState, Progress, Skeleton, StatusPill } from '@/components/ui/Primitives'

const STATUS_FILTERS = ['all', 'completed', 'running', 'failed', 'queued'] as const

export default function Runs() {
  const { data: runs, loading } = useAsync(() => api.listRuns(), [])
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>('all')
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const list = runs ?? []
    return list.filter((r) => {
      const okStatus = status === 'all' || r.status === status
      const q = query.trim().toLowerCase()
      const okQuery =
        !q ||
        r.name.toLowerCase().includes(q) ||
        r.benchmark_name.toLowerCase().includes(q) ||
        r.agent_results.some((a) => a.agent_name.toLowerCase().includes(q))
      return okStatus && okQuery
    })
  }, [runs, status, query])

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head page-head-row">
        <div>
          <div className="page-eyebrow">Benchmarking</div>
          <h1 className="page-title">Benchmark runs</h1>
          <p className="page-desc">
            Every execution is reproducible: the same benchmark, the same agent set, the same locked
            fairness configuration.
          </p>
        </div>
        <Link to="/run">
          <Button variant="primary" icon={<Play />}>
            New benchmark run
          </Button>
        </Link>
      </div>

      <Card bodyClassName="tight">
        <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
          <div className="search" style={{ width: 280 }}>
            <Search />
            <input
              placeholder="Search runs, benchmarks, agents…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="row-wrap" style={{ gap: 6 }}>
            <Filter size={14} className="muted" />
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                className="btn btn-sm"
                onClick={() => setStatus(s)}
                style={{
                  height: 28,
                  padding: '0 11px',
                  borderRadius: 7,
                  fontSize: 12,
                  fontWeight: 550,
                  cursor: 'pointer',
                  border: `1px solid ${status === s ? 'var(--accent-line)' : 'var(--border)'}`,
                  background: status === s ? 'var(--accent-soft)' : 'transparent',
                  color: status === s ? '#a8c4ff' : 'var(--muted)',
                }}
              >
                {s === 'all' ? 'All' : s[0].toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {loading ? (
        <div className="stack">
          <Skeleton h={110} radius={16} />
          <Skeleton h={110} radius={16} />
          <Skeleton h={110} radius={16} />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Activity size={30} />}
            title="No runs match these filters"
            description="Try a different status, or launch a fresh benchmark run to populate the timeline."
            action={
              <Link to="/run">
                <Button variant="primary" icon={<Play />}>
                  New benchmark run
                </Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="stack" style={{ gap: 12 }}>
          {filtered.map((run) => {
            const best = [...run.agent_results].sort((a, b) => b.overall_score - a.overall_score)[0]
            const cost = run.agent_results.reduce((s, a) => s + a.total_cost_usd, 0)
            return (
              <Card key={run.id} bodyClassName="tight">
                <div className="row-wrap" style={{ gap: 18, alignItems: 'flex-start' }}>
                  <div style={{ flex: '1 1 300px', minWidth: 0 }}>
                    <div className="row" style={{ gap: 9 }}>
                      <Link to={`/runs/${run.id}`} className="strong" style={{ fontSize: 14.5 }}>
                        {run.name}
                      </Link>
                      <StatusPill status={run.status} />
                      {run.fairness_report?.score === 100 && (
                        <Badge tone="violet" className="tip" data-tip="All parity checks passed">
                          fair
                        </Badge>
                      )}
                    </div>
                    <div className="row-wrap small muted" style={{ gap: 8, marginTop: 5 }}>
                      <span>{run.benchmark_name}</span>
                      <span>·</span>
                      <span title={fmtDateTime(run.started_at)}>{relTime(run.started_at)}</span>
                      {run.duration_sec && (
                        <>
                          <span>·</span>
                          <span>{fmtNum(run.duration_sec)}s wall clock</span>
                        </>
                      )}
                      <span>·</span>
                      <span>{run.fairness.repeats} repeat{run.fairness.repeats > 1 ? 's' : ''}</span>
                    </div>
                    <div className="row-wrap" style={{ gap: 12, marginTop: 9 }}>
                      {run.agent_results.map((a) => (
                        <AgentChip key={a.agent_id} name={a.agent_name} colorIndex={a.color_index} />
                      ))}
                    </div>
                  </div>

                  <div style={{ flex: '0 1 220px' }}>
                    <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
                      <span className="tiny muted">Progress</span>
                      <span className="mono tiny strong">{run.progress}%</span>
                    </div>
                    <Progress
                      value={run.progress}
                      color={
                        run.status === 'failed'
                          ? 'var(--rose)'
                          : run.status === 'running'
                            ? 'var(--accent)'
                            : 'var(--teal)'
                      }
                    />
                    <div className="tiny muted" style={{ marginTop: 6 }}>
                      {run.agent_results.reduce((s, a) => s + a.tasks_completed, 0)}/
                      {run.agent_results.reduce((s, a) => s + a.tasks_total, 0)} task executions
                    </div>
                  </div>

                  <div className="row" style={{ gap: 22, flex: '0 0 auto' }}>
                    <div className="right">
                      <div className="tiny muted">Best score</div>
                      <div className="mono strong" style={{ fontSize: 16 }}>
                        {best ? best.overall_score.toFixed(1) : '—'}
                      </div>
                      {best && <div className="tiny muted">{best.agent_name}</div>}
                    </div>
                    <div className="right">
                      <div className="tiny muted">Cost</div>
                      <div className="mono strong" style={{ fontSize: 16 }}>
                        {fmtUsd(cost)}
                      </div>
                      <div className="tiny muted">
                        {fmtNum(run.agent_results.reduce((s, a) => s + a.total_tokens, 0))} tok
                      </div>
                    </div>
                    <Link to={`/runs/${run.id}`}>
                      <Button size="sm">{run.status === 'running' ? 'Monitor' : 'Open'}</Button>
                    </Link>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {runs && runs.some((r) => r.status === 'running') && (
        <div className="callout">
          <Square size={15} style={{ marginTop: 1 }} />
          <div>
            A run is currently executing. Results stream in live — open the run to watch per-agent
            progress on the task matrix.
          </div>
        </div>
      )}
    </div>
  )
}
