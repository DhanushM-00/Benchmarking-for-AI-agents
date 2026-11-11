import { useEffect, useMemo, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  FlaskConical,
  FolderTree,
  Search,
  Timer,
  X,
  Zap,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { fmtNum } from '@/lib/format'
import { Card } from '@/components/ui/Card'
import { Badge, Button, EmptyState, Skeleton } from '@/components/ui/Primitives'
import { cn } from '@/lib/utils'
import type { Benchmark, Task, TaskDifficulty } from '@/types'

const DIFFICULTIES = ['all', 'easy', 'medium', 'hard', 'expert'] as const
type DiffFilter = (typeof DIFFICULTIES)[number]

const DIFF_COLOR: Record<string, string> = {
  easy: 'var(--teal)',
  medium: 'var(--accent)',
  hard: 'var(--amber)',
  expert: 'var(--rose)',
}

const PAGE_SIZE = 25
type SortKey = 'id' | 'title' | 'difficulty' | 'category' | 'test_count'
const DIFF_ORDER: Record<string, number> = { easy: 0, medium: 1, hard: 2, expert: 3 }

function DataSourceBanner({ mock, error }: { mock: boolean; error: string | null }) {
  if (error) {
    return (
      <div className="callout" role="alert" style={{ borderColor: 'var(--rose)', background: 'var(--rose-soft)' }}>
        <strong>Could not load catalogue.</strong> {error}
      </div>
    )
  }
  if (mock) {
    return (
      <div className="callout" role="status" data-testid="data-source-banner">
        <Badge tone="amber">Demo data</Badge>
        <span className="small muted" style={{ marginLeft: 8 }}>
          Showing bundled fixture catalogue — connect the backend for the live 100-task dataset.
        </span>
      </div>
    )
  }
  return (
    <div className="callout" role="status" data-testid="data-source-banner">
      <Badge tone="teal">Live catalogue</Badge>
      <span className="small muted" style={{ marginLeft: 8 }}>
        Data from the Bifrost backend.
      </span>
    </div>
  )
}

function TaskDetailModal({
  task,
  benchmark,
  onClose,
}: {
  task: Task
  benchmark?: Benchmark
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-detail-title"
      data-testid="task-detail-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal" style={{ maxWidth: 720 }}>
        <div className="modal-head">
          <div style={{ minWidth: 0 }}>
            <div className="tiny muted mono">{task.id}</div>
            <div className="modal-title" id="task-detail-title">
              {task.title}
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close task detail">
            <X size={16} />
          </button>
        </div>
        <div className="modal-body stack" style={{ gap: 14 }}>
          <div className="row-wrap" style={{ gap: 8 }}>
            <Badge tone="neutral">{benchmark?.name ?? task.benchmark_id}</Badge>
            <Badge tone="neutral">{task.category}</Badge>
            <span
              className="badge"
              style={{
                background: `color-mix(in srgb, ${DIFF_COLOR[task.difficulty]} 14%, transparent)`,
                color: DIFF_COLOR[task.difficulty],
                borderColor: `color-mix(in srgb, ${DIFF_COLOR[task.difficulty]} 32%, transparent)`,
              }}
            >
              {task.difficulty}
            </span>
            {task.tags?.map((tag) => (
              <span className="badge badge-neutral" key={tag}>
                {tag}
              </span>
            ))}
          </div>

          <div className="grid grid-3" style={{ gap: 10 }}>
            <div className="stat-tile">
              <div className="tiny muted">Tests</div>
              <div className="mono strong">{task.test_count}</div>
            </div>
            <div className="stat-tile">
              <div className="tiny muted">Time limit</div>
              <div className="mono strong">{task.time_limit_sec}s</div>
            </div>
            <div className="stat-tile">
              <div className="tiny muted">Token cap</div>
              <div className="mono strong">{fmtNum(task.max_tokens)}</div>
            </div>
          </div>

          <div>
            <div className="small strong" style={{ marginBottom: 6 }}>
              Full prompt
            </div>
            <pre
              data-testid="task-full-prompt"
              className="prompt-block"
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
                padding: 14,
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--r-md)',
                fontFamily: 'var(--mono)',
                fontSize: 12.5,
                lineHeight: 1.55,
                maxHeight: '48vh',
                overflow: 'auto',
              }}
            >
              {task.prompt}
            </pre>
          </div>
        </div>
        <div className="modal-foot">
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  )
}

export default function Tasks() {
  const { data: benchmarks, loading: loadingBench, error: errBench, mock: mockBench } = useAsync(
    () => api.listBenchmarks(),
    [],
  )
  const { data: tasks, loading: loadingTasks, error: errTasks, mock: mockTasks } = useAsync(
    () => api.listTasks(),
    [],
  )

  const [benchmarkId, setBenchmarkId] = useState<string>('all')
  const [difficulty, setDifficulty] = useState<DiffFilter>('all')
  const [category, setCategory] = useState<string>('all')
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('id')
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(0)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)

  const loading = loadingBench || loadingTasks
  const error = errBench || errTasks
  const mock = mockBench || mockTasks

  const categories = useMemo(() => {
    const set = new Set<string>()
    ;(tasks ?? []).forEach((t) => {
      if (benchmarkId === 'all' || t.benchmark_id === benchmarkId) set.add(t.category)
    })
    return ['all', ...[...set].sort()]
  }, [tasks, benchmarkId])

  const filtered = useMemo(() => {
    const list = tasks ?? []
    let out = list.filter((t) => {
      if (benchmarkId !== 'all' && t.benchmark_id !== benchmarkId) return false
      if (difficulty !== 'all' && t.difficulty !== difficulty) return false
      if (category !== 'all' && t.category !== category) return false
      const q = query.trim().toLowerCase()
      if (!q) return true
      return (
        t.title.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        t.category.toLowerCase().includes(q) ||
        t.prompt.toLowerCase().includes(q) ||
        (t.tags ?? []).some((tag) => tag.toLowerCase().includes(q))
      )
    })
    out = [...out].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'difficulty') {
        cmp = (DIFF_ORDER[a.difficulty] ?? 0) - (DIFF_ORDER[b.difficulty] ?? 0)
      } else if (sortKey === 'test_count') {
        cmp = a.test_count - b.test_count
      } else {
        cmp = String(a[sortKey] ?? '').localeCompare(String(b[sortKey] ?? ''))
      }
      return sortAsc ? cmp : -cmp
    })
    return out
  }, [tasks, benchmarkId, difficulty, category, query, sortKey, sortAsc])

  // Reset page when filters change
  useEffect(() => {
    setPage(0)
  }, [benchmarkId, difficulty, category, query, sortKey, sortAsc])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const pageItems = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE)

  const grouped = useMemo(() => {
    const map = new Map<string, Task[]>()
    pageItems.forEach((t) => {
      map.set(t.benchmark_id, [...(map.get(t.benchmark_id) ?? []), t])
    })
    return [...map.entries()]
  }, [pageItems])

  const totalCatalogue = tasks?.length ?? 0
  const totalBenchmarks = benchmarks?.length ?? 0

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v)
    else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head">
        <div className="page-eyebrow">Library</div>
        <h1 className="page-title">Tasks & benchmarks</h1>
        <p className="page-desc">
          The immutable task catalogue. Every benchmark is versioned — the same dataset identifier is
          passed to every agent in a run so parity can be verified after the fact.
        </p>
      </div>

      <DataSourceBanner mock={mock} error={error} />

      <div className="row-wrap" style={{ gap: 12, alignItems: 'center' }}>
        <span className="mono small strong" data-testid="catalogue-counts">
          {loading ? '…' : `${totalBenchmarks} benchmarks · ${totalCatalogue} tasks`}
        </span>
        {!loading && filtered.length !== totalCatalogue && (
          <span className="small muted" data-testid="filter-result-count">
            Showing {filtered.length} match{filtered.length === 1 ? '' : 'es'}
          </span>
        )}
      </div>

      {/* Benchmark cards */}
      <div className="grid grid-3" data-testid="benchmark-grid">
        {loading && !benchmarks ? (
          [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} h={150} radius={16} />)
        ) : (
          (benchmarks ?? []).map((b) => (
            <Card key={b.id} bodyClassName="tight">
              <button
                type="button"
                data-testid={`benchmark-card-${b.id}`}
                onClick={() => setBenchmarkId(benchmarkId === b.id ? 'all' : b.id)}
                aria-pressed={benchmarkId === b.id}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  width: '100%',
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <div className="row" style={{ gap: 9 }}>
                    <FlaskConical size={16} style={{ color: 'var(--accent)' }} />
                    <span className="strong">{b.name}</span>
                  </div>
                  <Badge tone={benchmarkId === b.id ? 'accent' : 'neutral'}>{b.version}</Badge>
                </div>
                <div className="small muted mt-2" style={{ minHeight: 38 }}>
                  {b.description}
                </div>
                <div className="row" style={{ justifyContent: 'space-between', marginTop: 10 }}>
                  <span className="mono small strong" data-testid={`bench-task-count-${b.id}`}>
                    {b.task_count} tasks
                  </span>
                  <span className="tiny muted">
                    {fmtNum(Math.round(b.total_time_limit_sec / 60))} min worst case
                  </span>
                </div>
                <div className="mt-2">
                  <div className="bar" style={{ display: 'flex', gap: 1 }} aria-label="Difficulty mix">
                    {(['easy', 'medium', 'hard', 'expert'] as TaskDifficulty[]).map((d) =>
                      b.difficulty_mix?.[d] ? (
                        <div
                          key={d}
                          title={`${d}: ${b.difficulty_mix[d]}`}
                          style={{
                            height: 5,
                            borderRadius: 3,
                            background: DIFF_COLOR[d],
                            width: `${(b.difficulty_mix[d] / Math.max(1, b.task_count)) * 100}%`,
                          }}
                        />
                      ) : null,
                    )}
                  </div>
                </div>
                <div className="row-wrap" style={{ gap: 5, marginTop: 9 }}>
                  {(b.categories ?? []).map((c) => (
                    <span className="badge badge-neutral" key={c}>
                      {c}
                    </span>
                  ))}
                </div>
              </button>
            </Card>
          ))
        )}
      </div>

      {/* Filters */}
      <Card bodyClassName="tight">
        <div className="row-wrap" style={{ justifyContent: 'space-between', gap: 10 }}>
          <div className="search" style={{ width: 300, maxWidth: '100%' }}>
            <Search />
            <input
              placeholder="Search tasks, IDs, categories, prompts…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search tasks"
              data-testid="task-search"
            />
          </div>
          <div className="row-wrap" style={{ gap: 6 }}>
            {DIFFICULTIES.map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDifficulty(d)}
                className={cn('btn', 'btn-sm')}
                aria-pressed={difficulty === d}
                data-testid={`filter-diff-${d}`}
                style={{
                  background: difficulty === d ? 'var(--accent-soft)' : 'transparent',
                  borderColor: difficulty === d ? 'var(--accent-line)' : 'var(--border)',
                  color: difficulty === d ? '#a8c4ff' : 'var(--muted)',
                }}
              >
                {d === 'all' ? 'All levels' : d[0].toUpperCase() + d.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div className="row-wrap" style={{ gap: 6, marginTop: 10 }}>
          <span className="tiny muted" style={{ alignSelf: 'center' }}>
            Category
          </span>
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={cn('btn', 'btn-sm')}
              aria-pressed={category === c}
              data-testid={`filter-cat-${c}`}
              style={{
                background: category === c ? 'var(--accent-soft)' : 'transparent',
                borderColor: category === c ? 'var(--accent-line)' : 'var(--border)',
                color: category === c ? '#a8c4ff' : 'var(--muted)',
              }}
            >
              {c === 'all' ? 'All categories' : c}
            </button>
          ))}
        </div>
      </Card>

      {loading && !tasks ? (
        <Card>
          <Skeleton h={220} />
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon={<FolderTree size={30} />}
            title="No tasks match"
            description="Adjust the benchmark, difficulty, category or search filters."
          />
        </Card>
      ) : (
        <>
          {grouped.map(([benchId, list]) => {
            const bench = (benchmarks ?? []).find((b) => b.id === benchId)
            return (
              <Card
                key={benchId}
                title={bench?.name ?? benchId}
                subtitle={`${list.length} on this page · ${filtered.filter((t) => t.benchmark_id === benchId).length} matching filter`}
                flush
              >
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th style={{ width: 130 }}>
                          <button type="button" className="th-sort" onClick={() => toggleSort('id')}>
                            Task {sortKey === 'id' ? (sortAsc ? '↑' : '↓') : ''}
                          </button>
                        </th>
                        <th>
                          <button type="button" className="th-sort" onClick={() => toggleSort('title')}>
                            Title {sortKey === 'title' ? (sortAsc ? '↑' : '↓') : ''}
                          </button>
                        </th>
                        <th style={{ width: 140 }}>
                          <button type="button" className="th-sort" onClick={() => toggleSort('category')}>
                            Category {sortKey === 'category' ? (sortAsc ? '↑' : '↓') : ''}
                          </button>
                        </th>
                        <th style={{ width: 100 }}>
                          <button type="button" className="th-sort" onClick={() => toggleSort('difficulty')}>
                            Difficulty {sortKey === 'difficulty' ? (sortAsc ? '↑' : '↓') : ''}
                          </button>
                        </th>
                        <th className="num" style={{ width: 80 }}>
                          <button type="button" className="th-sort" onClick={() => toggleSort('test_count')}>
                            Tests {sortKey === 'test_count' ? (sortAsc ? '↑' : '↓') : ''}
                          </button>
                        </th>
                        <th className="num" style={{ width: 100 }}>
                          Time
                        </th>
                        <th className="num" style={{ width: 110 }}>
                          Tokens
                        </th>
                        <th style={{ width: 90 }} />
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((t) => (
                        <tr
                          key={t.id}
                          className="clickable"
                          tabIndex={0}
                          data-testid={`task-row-${t.id}`}
                          onClick={() => setSelectedTask(t)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              setSelectedTask(t)
                            }
                          }}
                        >
                          <td className="mono tiny muted">{t.id}</td>
                          <td>
                            <div className="strong" style={{ fontSize: 13 }}>
                              {t.title}
                            </div>
                            <div className="tiny muted truncate" style={{ maxWidth: 420 }}>
                              {t.prompt}
                            </div>
                          </td>
                          <td>
                            <Badge tone="neutral">{t.category}</Badge>
                          </td>
                          <td>
                            <span
                              className="badge"
                              style={{
                                background: `color-mix(in srgb, ${DIFF_COLOR[t.difficulty]} 14%, transparent)`,
                                color: DIFF_COLOR[t.difficulty],
                                borderColor: `color-mix(in srgb, ${DIFF_COLOR[t.difficulty]} 32%, transparent)`,
                              }}
                            >
                              {t.difficulty}
                            </span>
                          </td>
                          <td className="num">{t.test_count}</td>
                          <td className="num">
                            <span className="row" style={{ gap: 5, justifyContent: 'flex-end' }}>
                              <Timer size={12} className="muted" />
                              {t.time_limit_sec}s
                            </span>
                          </td>
                          <td className="num">
                            <span className="row" style={{ gap: 5, justifyContent: 'flex-end' }}>
                              <Zap size={12} className="muted" />
                              {fmtNum(t.max_tokens)}
                            </span>
                          </td>
                          <td>
                            <Button
                              size="sm"
                              variant="ghost"
                              data-testid={`view-task-${t.id}`}
                              onClick={(e) => {
                                e.stopPropagation()
                                setSelectedTask(t)
                              }}
                            >
                              View details
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )
          })}

          {/* Pagination */}
          <div
            className="row"
            style={{ justifyContent: 'space-between', alignItems: 'center' }}
            data-testid="task-pagination"
          >
            <span className="small muted">
              Page {safePage + 1} of {pageCount} · {filtered.length} task
              {filtered.length === 1 ? '' : 's'}
            </span>
            <div className="row" style={{ gap: 8 }}>
              <Button
                size="sm"
                variant="ghost"
                disabled={safePage <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                aria-label="Previous page"
              >
                <ChevronLeft size={14} /> Prev
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={safePage >= pageCount - 1}
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                aria-label="Next page"
              >
                Next <ChevronRight size={14} />
              </Button>
            </div>
          </div>
        </>
      )}

      <Card title="Dataset integrity" subtitle="How Bifrost guarantees a task set is comparable">
        <div className="grid grid-3" style={{ gap: 18 }}>
          {[
            [
              'Immutable versioned sets',
              'Each benchmark carries a semantic version and content hash. A run pins the hash, so a later edit to the dataset can never rewrite history.',
            ],
            [
              'Identical task delivery',
              'Every agent in a run receives the same task IDs, prompts, hidden tests and resource limits — only the agent strategy differs.',
            ],
            [
              'Blinded scoring',
              'Hidden unit tests grade submissions. Scorer version is recorded on every run for auditability.',
            ],
          ].map(([title, body]) => (
            <div key={title}>
              <div className="strong" style={{ fontSize: 13, marginBottom: 4 }}>
                {title}
              </div>
              <div className="small muted">{body}</div>
            </div>
          ))}
        </div>
      </Card>

      {selectedTask && (
        <TaskDetailModal
          task={selectedTask}
          benchmark={(benchmarks ?? []).find((b) => b.id === selectedTask.benchmark_id)}
          onClose={() => setSelectedTask(null)}
        />
      )}
    </div>
  )
}
