import { Link } from 'react-router-dom'
import {
  Activity,
  ArrowUpRight,
  Coins,
  Play,
  Scale,
  Target,
  TrendingUp,
  Trophy,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { fmtCompact, fmtDateTime, fmtNum, fmtUsd, relTime, scoreColor } from '@/lib/format'
import { Card, Stat, AgentChip } from '@/components/ui/Card'
import { Callout } from '@/components/ui/Primitives'
import { Badge, Button, EmptyState, Progress, Skeleton, StatusPill } from '@/components/ui/Primitives'
import { Donut, TrendChart } from '@/components/charts/Charts'

export default function Dashboard() {
  const { data, loading, error } = useAsync(() => api.dashboard(), [])
  const { data: runsData } = useAsync(() => api.listRuns(), [])

  if (error) {
    return (
      <Card>
        <EmptyState
          icon={<Activity size={30} />}
          title="Could not reach the Bifrost API"
          description={error}
          action={
            <Button variant="primary" icon={<Play />}>
              Retry
            </Button>
          }
        />
      </Card>
    )
  }

  const stats = data?.stats
  const leaderboard = data?.leaderboard ?? []
  const trend = data?.score_trend ?? []
  const cost = data?.cost_by_benchmark ?? []
  const recent = runsData?.slice(0, 6) ?? []

  const series = leaderboard.map((e) => ({ name: e.agent_name, colorIndex: e.color_index }))

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head page-head-row">
        <div>
          <div className="page-eyebrow">Overview</div>
          <h1 className="page-title">Agent benchmarking, without the guesswork</h1>
          <p className="page-desc">
            Bifrost runs the same coding tasks, in the same sandbox, under the same budget and scorer
            for every agent — so the numbers on the leaderboard are actually comparable.
          </p>
        </div>
        <div className="row">
          <Link to="/runs">
            <Button icon={<Activity />}>View runs</Button>
          </Link>
          <Link to="/run">
            <Button variant="primary" icon={<Play />}>
              New benchmark run
            </Button>
          </Link>
        </div>
      </div>

      <div className="grid grid-4">
        {loading || !stats ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} h={104} radius={16} />)
        ) : (
          <>
            <Stat
              label="Benchmark runs"
              value={fmtNum(stats.total_runs)}
              foot={
                <>
                  <span className="badge badge-teal badge-dot">{stats.completed_runs} completed</span>
                  <span>{fmtNum(stats.tasks_executed)} tasks executed</span>
                </>
              }
              accent="#5b8cff"
              icon={<Activity />}
            />
            <Stat
              label="Avg overall score"
              value={stats.avg_overall_score != null ? Number(stats.avg_overall_score).toFixed(1) : '—'}
              unit="/100"
              foot={
                <>
                  <TrendingUp size={12} />
                  <span>
                    {stats.score_delta != null
                      ? `${stats.score_delta >= 0 ? '+' : ''}${stats.score_delta} pts vs prior run`
                      : 'Not enough data'}
                  </span>
                </>
              }
              accent="#2dd4a7"
              icon={<Target />}
            />
            <Stat
              label="Spend to date"
              value={fmtUsd(stats.total_cost_usd)}
              foot={
                <>
                  <Coins size={12} />
                  <span>{fmtUsd(stats.avg_cost_per_run)} avg per run</span>
                  <span>·</span>
                  <span>{fmtCompact(stats.total_tokens)} tokens</span>
                </>
              }
              accent="#f5a524"
              icon={<Coins />}
            />
            <Stat
              label="Fairness integrity"
              value={stats.fairness_score != null ? stats.fairness_score : '—'}
              unit="%"
              foot={
                <>
                  <Scale size={12} />
                  <span>
                    {stats.fairness_checks_passing != null && stats.fairness_checks_total != null
                      ? `${stats.fairness_checks_passing}/${stats.fairness_checks_total} checks passing (latest run)`
                      : stats.fairness_score != null
                        ? 'Mean fairness from completed runs'
                        : 'Unavailable'}
                  </span>
                </>
              }
              accent="#a78bfa"
              icon={<Scale />}
            />
          </>
        )}
      </div>

      <div className="grid grid-2-1">
        <Card
          title="Score trend by agent"
          subtitle="Overall weighted score across completed runs"
          action={<Badge tone="accent">Last {trend.length} runs</Badge>}
        >
          {loading ? (
            <Skeleton h={272} />
          ) : trend.length ? (
            <TrendChart data={trend} series={series} height={272} />
          ) : (
            <EmptyState
              icon={<TrendingUp size={28} />}
              title="No completed runs yet"
              description="Complete a benchmark run to generate historical score trends by agent."
              action={
                <Link to="/run">
                  <Button variant="primary" icon={<Play />}>
                    New run
                  </Button>
                </Link>
              }
            />
          )}
        </Card>

        <Card
          title="Spend by benchmark"
          subtitle="Cumulative cost across all agents"
          action={<Link to="/leaderboard" className="btn btn-ghost btn-sm">Details</Link>}
        >
          {loading ? (
            <Skeleton h={218} />
          ) : cost.length ? (
            <Donut
              data={cost}
              height={218}
              centerLabel="total"
              centerValue={fmtUsd(cost.reduce((s, c) => s + c.value, 0))}
            />
          ) : (
            <EmptyState
              icon={<Coins size={28} />}
              title="No spend data"
              description="Cost graphs appear after live or simulated runs record agent costs. Missing gateway usage is shown as unavailable, not zero."
            />
          )}
        </Card>
      </div>

      <div className="grid grid-1-2">
        <Card
          title="Leaderboard"
          subtitle="Average overall score"
          action={
            <Link to="/leaderboard" className="btn btn-ghost btn-sm">
              Full board <ArrowUpRight size={13} />
            </Link>
          }
          flush
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th style={{ width: 46 }}>#</th>
                  <th>Agent</th>
                  <th className="num">Score</th>
                  <th className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((e) => (
                  <tr key={e.agent_id}>
                    <td>
                      <span className={`rank rank-${e.rank}`}>{e.rank}</span>
                    </td>
                    <td>
                      <AgentChip name={e.agent_name} colorIndex={e.color_index} />
                    </td>
                    <td className="num">
                      <span style={{ color: scoreColor(e.overall_score), fontWeight: 600 }}>
                        {e.overall_score.toFixed(1)}
                      </span>
                    </td>
                    <td className="num muted">{fmtUsd(e.total_cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          title="Recent runs"
          subtitle="Latest benchmark executions on this workspace"
          action={
            <Link to="/runs" className="btn btn-ghost btn-sm">
              All runs <ArrowUpRight size={13} />
            </Link>
          }
          flush
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Agents</th>
                  <th>Status</th>
                  <th className="num">Started</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link to={`/runs/${run.id}`} className="strong">
                        {run.name}
                      </Link>
                      <div className="tiny muted">{run.benchmark_name}</div>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6 }}>
                        {run.agent_results.map((a) => (
                          <span
                            key={a.agent_id}
                            className="agent-dot"
                            title={a.agent_name}
                            style={{
                              background: ['#5b8cff', '#2dd4a7', '#f5a524', '#a78bfa', '#f472b6'][a.color_index % 5],
                            }}
                          />
                        ))}
                        <span className="tiny muted">{run.agent_ids.length}</span>
                      </div>
                    </td>
                    <td>
                      <StatusPill status={run.status} />
                    </td>
                    <td className="num muted nowrap" title={fmtDateTime(run.started_at)}>
                      {relTime(run.started_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card>
        <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
          <div className="row" style={{ gap: 14 }}>
            <div
              style={{
                width: 38, height: 38, borderRadius: 10, display: 'grid', placeItems: 'center',
                background: 'var(--violet-soft)', border: '1px solid rgba(167,139,250,0.3)', color: 'var(--violet)',
              }}
            >
              <Scale size={18} />
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>Fair Agent Testing Engine</div>
              <div className="small muted">
                Every run is pinned to one dataset, prompt template, time limit, sandbox image and scorer —
                with {2}+ repeats and a blinded judge, so agents cannot be flattered by the harness.
              </div>
            </div>
          </div>
          <Link to="/fairness">
            <Button icon={<Trophy />}>Inspect parity checks</Button>
          </Link>
        </div>
        {recent.length > 0 && (
          <div className="mt-4">
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <span className="small muted">Fairness score across the {recent.length} most recent runs</span>
              <span className="mono small strong">
                {Math.round(
                  recent.reduce((s, r) => s + (r.fairness_report?.score ?? 0), 0) / (recent.length || 1),
                )}
                %
              </span>
            </div>
            <Progress value={100} color="var(--violet)" large />
          </div>
        )}
      </Card>
    
      {/* Analytics from stored runs */}
      {data?.analytics && (
        <div className="grid grid-2" style={{ marginTop: 16 }}>
          <Card title="Agent comparison" subtitle="From completed stored runs only">
            {(data.analytics.comparison?.fairness_warnings || []).length > 0 && (
              <Callout tone="amber" style={{ marginBottom: 8 }}>
                {(data.analytics.comparison?.fairness_warnings as string[] | undefined)?.slice(0, 3).join(' · ')}
              </Callout>
            )}
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Success %</th>
                    <th>Hidden %</th>
                    <th>Avg time</th>
                    <th>Tokens</th>
                    <th>Cost/success</th>
                    <th>Recovery %</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.analytics.comparison?.agents || []).map((a: any) => (
                    <tr key={a.agent_id}>
                      <td>{a.agent_name || a.agent_id}</td>
                      <td>{a.task_success_rate != null ? a.task_success_rate : '—'}</td>
                      <td>{a.hidden_test_pass_rate != null ? a.hidden_test_pass_rate : '—'}</td>
                      <td>{a.avg_execution_time_sec != null ? a.avg_execution_time_sec : '—'}</td>
                      <td>{a.total_tokens != null ? a.total_tokens : '—'}</td>
                      <td>{a.cost_per_successful_task != null ? a.cost_per_successful_task : '—'}</td>
                      <td>{a.recovery_rate != null ? a.recovery_rate : '—'}</td>
                    </tr>
                  ))}
                  {(data.analytics.comparison?.agents || []).length === 0 && (
                    <tr><td colSpan={7}>No completed benchmark data yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="Failure distribution" subtitle="Classified from task errors (not all agent failures)">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {(data.analytics.recovery?.failures_by_category || []).map((row: any) => (
                <li key={row.key}><b>{row.key}</b>: {row.count}</li>
              ))}
              {(data.analytics.recovery?.failures_by_category || []).length === 0 && (
                <li>No failures recorded in stored runs.</li>
              )}
            </ul>
            <div style={{ marginTop: 12, fontSize: 12, opacity: 0.75 }}>
              Recovery rate:{' '}
              {data.analytics.recovery?.recovery_rate != null
                ? `${data.analytics.recovery.recovery_rate}%`
                : 'n/a'}
              {' · '}retries: {data.analytics.recovery?.total_retries ?? '—'}
            </div>
            {data.data_source && (
              <div style={{ marginTop: 8, fontSize: 11, opacity: 0.6 }}>Source: {data.data_source}</div>
            )}
          </Card>
        </div>
      )}

</div>
  )
}
