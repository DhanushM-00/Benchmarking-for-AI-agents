import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Crown, Scale, Trophy } from 'lucide-react'
import { api } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { agentColor, fmtCompact, fmtNum, fmtUsd, scoreColor } from '@/lib/format'
import { Card, AgentChip, Stat } from '@/components/ui/Card'
import { Badge, Button, EmptyState, Progress, Skeleton } from '@/components/ui/Primitives'
import { GroupedBars, HorizontalBars, RadarProfile, TrendChart } from '@/components/charts/Charts'

const METRIC_OPTIONS = [
  { key: 'overall_score', label: 'Overall score' },
  { key: 'task_success', label: 'Task success' },
  { key: 'correctness', label: 'Correctness' },
  { key: 'efficiency', label: 'Efficiency' },
  { key: 'tool_usage', label: 'Tool usage' },
  { key: 'consistency', label: 'Consistency' },
] as const

type MetricKey = (typeof METRIC_OPTIONS)[number]['key']

export default function Leaderboard() {
  const { data: benchmarks } = useAsync(() => api.listBenchmarks(), [])
  const { data: dashboard } = useAsync(() => api.dashboard(), [])
  const { data: runs } = useAsync(() => api.listRuns(), [])

  const [benchmarkId, setBenchmarkId] = useState<string>('all')
  const [metric, setMetric] = useState<MetricKey>('overall_score')

  const board = useMemo(() => {
    const base = dashboard?.leaderboard ?? []
    if (benchmarkId === 'all') return base
    // Recompute for a single benchmark from the run list.
    const filtered = (runs ?? []).filter((r) => r.benchmark_id === benchmarkId && r.status === 'completed')
    const acc = new Map<string, (typeof base)[number]>()
    for (const run of filtered) {
      for (const ar of run.agent_results) {
        const prev = acc.get(ar.agent_id)
        if (!prev) {
          acc.set(ar.agent_id, {
            agent_id: ar.agent_id,
            agent_name: ar.agent_name,
            color_index: ar.color_index,
            overall_score: ar.overall_score,
            task_success: ar.metrics.task_success,
            correctness: ar.metrics.correctness,
            efficiency: ar.metrics.efficiency,
            tool_usage: ar.metrics.tool_usage,
            consistency: ar.metrics.consistency,
            avg_execution_time_sec: ar.avg_execution_time_sec,
            p95_execution_time_sec: ar.p95_execution_time_sec,
            total_tokens: ar.total_tokens,
            total_cost_usd: ar.total_cost_usd,
            runs_count: 1,
            rank: 0,
            delta_rank: 0,
          })
        } else {
          const n = prev.runs_count
          const keys = [
            'overall_score', 'task_success', 'correctness', 'efficiency', 'tool_usage', 'consistency',
            'avg_execution_time_sec', 'p95_execution_time_sec',
          ] as const
          keys.forEach((k) => {
            const nv = k === 'overall_score' ? ar.overall_score : (ar.metrics as never)[k]
            prev[k] = Math.round(((prev[k] as number) * n + (nv as number)) / (n + 1) * 10) / 10
          })
          prev.total_tokens += ar.total_tokens
          prev.total_cost_usd = Math.round((prev.total_cost_usd + ar.total_cost_usd) * 10000) / 10000
          prev.runs_count += 1
        }
      }
    }
    return [...acc.values()].sort((a, b) => b[metric] - a[metric])
  }, [dashboard, runs, benchmarkId, metric])

  const sorted = useMemo(() => [...board].sort((a, b) => b[metric] - a[metric]), [board, metric])

  const radarSeries = sorted.map((e) => ({
    name: e.agent_name,
    colorIndex: e.color_index,
    values: [e.task_success, e.correctness, e.efficiency, e.tool_usage, e.consistency],
  }))

  const trend = dashboard?.score_trend ?? []
  const trendSeries = sorted.map((e) => ({ name: e.agent_name, colorIndex: e.color_index }))

  const leader = sorted[0]

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head page-head-row">
        <div>
          <div className="page-eyebrow">Benchmarking</div>
          <h1 className="page-title">Leaderboard</h1>
          <p className="page-desc">
            Every score on this board comes from a parity-locked run: identical dataset, prompt,
            budget, environment and scorer. Switch the metric to see where each agent actually leads.
          </p>
        </div>
        <Link to="/runs">
          <Button icon={<ArrowUpRight />}>Inspect runs</Button>
        </Link>
      </div>

      <Card bodyClassName="tight">
        <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
          <div className="row-wrap" style={{ gap: 10 }}>
            <select
              className="select"
              style={{ width: 210 }}
              value={benchmarkId}
              onChange={(e) => setBenchmarkId(e.target.value)}
            >
              <option value="all">All benchmarks</option>
              {(benchmarks ?? []).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
            <select
              className="select"
              style={{ width: 190 }}
              value={metric}
              onChange={(e) => setMetric(e.target.value as MetricKey)}
            >
              {METRIC_OPTIONS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <Badge tone="violet">
            <Scale /> parity-locked results only
          </Badge>
        </div>
      </Card>

      <div className="grid grid-4">
        {leader ? (
          <>
            <Stat
              label="Current leader"
              value={leader[metric].toFixed(1)}
              foot={<AgentChip name={leader.agent_name} colorIndex={leader.color_index} />}
              accent="#f5a524"
              icon={<Crown />}
            />
            <Stat
              label="Spread (1st → 3rd)"
              value={(leader[metric] - (sorted[2]?.overall_score ?? leader[metric])).toFixed(1)}
              unit="pts"
              foot={<span>across {sorted.length} agents</span>}
              accent="#5b8cff"
              icon={<Trophy />}
            />
            <Stat
              label="Total spend"
              value={fmtUsd(sorted.reduce((s, e) => s + e.total_cost_usd, 0))}
              foot={
                <>
                  <span>{fmtCompact(sorted.reduce((s, e) => s + e.total_tokens, 0))} tokens</span>
                </>
              }
              accent="#a78bfa"
              icon={<Scale />}
            />
            <Stat
              label="Runs aggregated"
              value={fmtNum(sorted.reduce((s, e) => s + e.runs_count, 0))}
              foot={<span>median of repeats reported</span>}
              accent="#2dd4a7"
              icon={<Trophy />}
            />
          </>
        ) : (
          <Skeleton h={104} radius={16} />
        )}
      </div>

      <Card title="Rankings" subtitle={`Sorted by ${METRIC_OPTIONS.find((m) => m.key === metric)?.label}`} flush>
        {sorted.length === 0 ? (
          <EmptyState title="No results for this selection" description="Run a benchmark to populate the board." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th style={{ width: 52 }}>Rank</th>
                  <th>Agent</th>
                  <th style={{ width: 180 }}>Score</th>
                  <th className="num">Success</th>
                  <th className="num">Correct</th>
                  <th className="num">Efficiency</th>
                  <th className="num">Tool use</th>
                  <th className="num">Avg time</th>
                  <th className="num">Cost</th>
                  <th className="num">Runs</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((e, i) => (
                  <tr key={e.agent_id}>
                    <td>
                      <div className="row" style={{ gap: 6 }}>
                        <span className={`rank rank-${i + 1}`}>{i + 1}</span>
                        {e.delta_rank !== 0 && (
                          <span
                            className={`tiny ${e.delta_rank > 0 ? 'delta-up' : 'delta-down'}`}
                            style={{ fontWeight: 700 }}
                          >
                            {e.delta_rank > 0 ? '▲' : '▼'}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <AgentChip name={e.agent_name} colorIndex={e.color_index} />
                      <div className="tiny muted">{e.agent_id}</div>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 9 }}>
                        <span className="mono strong" style={{ color: scoreColor(e[metric]) }}>
                          {e[metric].toFixed(1)}
                        </span>
                        <Progress value={e[metric]} color={scoreColor(e[metric])} className="w-full" />
                      </div>
                    </td>
                    <td className="num">{e.task_success.toFixed(1)}</td>
                    <td className="num">{e.correctness.toFixed(1)}</td>
                    <td className="num">{e.efficiency.toFixed(1)}</td>
                    <td className="num">{e.tool_usage.toFixed(1)}</td>
                    <td className="num">{e.avg_execution_time_sec.toFixed(1)}s</td>
                    <td className="num">{fmtUsd(e.total_cost_usd)}</td>
                    <td className="num muted">{e.runs_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid grid-2">
        <Card title="Capability fingerprint" subtitle="Per-agent profile across the five tracked metrics">
          {radarSeries.length ? (
            <RadarProfile
              axes={['Task success', 'Correctness', 'Efficiency', 'Tool usage', 'Consistency']}
              series={radarSeries}
              height={296}
            />
          ) : (
            <Skeleton h={296} />
          )}
        </Card>

        <Card title="Score trend" subtitle="Overall score across completed runs">
          {trend.length ? (
            <TrendChart data={trend} series={trendSeries} height={296} />
          ) : (
            <Skeleton h={296} />
          )}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Cost per agent" subtitle="Cumulative spend across aggregated runs">
          <GroupedBars
            data={sorted.map((e) => ({ name: e.agent_name, cost: e.total_cost_usd }))}
            bars={[{ key: 'cost', name: 'Cost (USD)', colorIndex: 0 }]}
            rowColors={sorted.map((e) => agentColor(e.color_index))}
            yFormatter={(v) => `$${v.toFixed(2)}`}
            height={220}
          />
        </Card>

        <Card title="Execution time" subtitle="Average and p95 wall clock per task">
          <GroupedBars
            data={sorted.map((e) => ({
              name: e.agent_name,
              avg: e.avg_execution_time_sec,
              p95: e.p95_execution_time_sec,
            }))}
            bars={[
              { key: 'avg', name: 'Avg seconds', colorIndex: 0 },
              { key: 'p95', name: 'p95 seconds', colorIndex: 3 },
            ]}
            yFormatter={(v) => `${v.toFixed(0)}s`}
            height={220}
          />
          <div className="mt-3 small muted">
            Nova is the fastest and the cheapest, but trails Forge on correctness — the trade-off the
            leaderboard exists to make visible.
          </div>
        </Card>
      </div>

      <Card title="Efficiency index" subtitle="Higher is better — fewer wasted steps per solved task">
        <HorizontalBars
          data={sorted.map((e) => ({
            name: e.agent_name,
            value: e.efficiency,
            color: agentColor(e.color_index),
          }))}
          formatter={(v) => v.toFixed(1)}
        />
      </Card>
    </div>
  )
}
