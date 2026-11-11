/* ============================================================
   Bifrost domain types — shared with the FastAPI backend.
   Mirrors pydantic schemas in backend/app/schemas.
   ============================================================ */

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export type TaskDifficulty = 'easy' | 'medium' | 'hard' | 'expert'

export type MetricKey =
  | 'task_success'
  | 'correctness'
  | 'efficiency'
  | 'tool_usage'
  | 'consistency'

export interface MetricDef {
  key: MetricKey
  label: string
  short: string
  description: string
  weight: number
  higher_is_better: boolean
}

/** A single evaluation metric definition used by the scoring engine. */
export interface Metric {
  key: MetricKey
  label: string
  description: string
  weight: number
  unit: string
}

export interface Task {
  id: string
  benchmark_id: string
  title: string
  category: string
  difficulty: TaskDifficulty
  prompt: string
  test_count: number
  time_limit_sec: number
  max_tokens: number
  tags: string[]
  reference_solution_lines: number
}

export interface Benchmark {
  id: string
  name: string
  description: string
  task_count: number
  categories: string[]
  difficulty_mix: Record<TaskDifficulty, number>
  total_time_limit_sec: number
  version: string
  tags: string[]
  created_at: string
}

export interface AgentTool {
  name: string
  description: string
}

export interface Agent {
  id: string
  name: string
  model: string
  model_provider: string
  description: string
  system_prompt_version: string
  tools: AgentTool[]
  orchestration: string
  memory: string
  color_index: number
  enabled: boolean
  cost_per_1k_input: number
  cost_per_1k_output: number
  registered_at: string
}

/** Fair Agent Testing Engine — the configuration that guarantees parity. */
export interface FairnessConfig {
  time_limit_per_task_sec: number
  max_tokens_per_task: number
  repeats: number
  isolation: 'docker' | 'subprocess' | 'vm'
  container_image: string
  network_policy: 'none' | 'allowlist' | 'full'
  randomize_task_order: boolean
  random_seed: number
  scorer_version: string
  temperature: number
  blinded_evaluation: boolean
  metric_weights: Record<MetricKey, number>
}

export interface IntegrityCheck {
  id: string
  label: string
  detail: string
  status: 'pass' | 'warn' | 'fail'
}

export interface FairnessReport {
  score: number
  checks: IntegrityCheck[]
  violations: string[]
}

export interface ToolCall {
  tool: string
  args_summary: string
  outcome: 'success' | 'error' | 'rejected'
  duration_ms: number
}

export interface TaskResult {
  task_id: string
  task_title: string
  category: string
  difficulty: TaskDifficulty
  completed: boolean
  correctness: number
  unit_tests_passed: number
  unit_tests_total: number
  execution_time_sec: number
  tokens_input: number
  tokens_output: number
  tokens_cached: number
  cost_usd: number
  tool_calls: ToolCall[]
  unnecessary_steps: number
  efficiency_score: number
  tool_usage_score: number
  error?: string
}

export interface AgentRunResult {
  agent_id: string
  agent_name: string
  color_index: number
  status: RunStatus
  tasks_completed: number
  tasks_total: number
  task_results: TaskResult[]
  metrics: Record<MetricKey, number>
  overall_score: number
  avg_execution_time_sec: number
  p95_execution_time_sec: number
  total_tokens: number
  total_cost_usd: number
  tool_calls_total: number
  unnecessary_steps_total: number
  repeat_variance: number
}

export interface Run {
  id: string
  name: string
  benchmark_id: string
  benchmark_name: string
  agent_ids: string[]
  /** Exact task set executed (persisted for reproducibility). */
  task_ids?: string[]
  task_count?: number
  dataset_hash?: string
  total_executions?: number
  agent_results: AgentRunResult[]
  status: RunStatus
  fairness: FairnessConfig
  fairness_report: FairnessReport
  started_at: string
  finished_at: string | null
  duration_sec: number | null
  progress: number
  notes: string
  created_by: string
  execution_mode?: 'live' | 'simulated'
  mode_reasons?: string[]
  isolation_requested?: string
  isolation_note?: string | null
}

export interface SummaryStats {
  total_runs: number
  completed_runs: number
  tasks_executed: number
  total_agent_executions: number
  total_cost_usd: number
  total_tokens: number
  avg_overall_score: number
  avg_cost_per_run: number
  avg_execution_time_sec: number
  fairness_score: number | null
    score_delta?: number | null
    fairness_checks_passing?: number | null
    fairness_checks_total?: number | null
}

export interface LeaderboardEntry {
  agent_id: string
  agent_name: string
  color_index: number
  overall_score: number
  task_success: number
  correctness: number
  efficiency: number
  tool_usage: number
  consistency: number
  avg_execution_time_sec: number
  p95_execution_time_sec: number
  total_tokens: number
  total_cost_usd: number
  runs_count: number
  rank: number
  delta_rank: number
}

export interface AnalyticsPayload {
  comparison?: {
    agents?: Array<{
      agent_id: string
      agent_name?: string
      task_success_rate?: number | null
      hidden_test_pass_rate?: number | null
      avg_execution_time_sec?: number | null
      total_tokens?: number | null
      cost_per_successful_task?: number | null
      recovery_rate?: number | null
    }>
    fairness_warnings?: string[]
  }
  recovery?: {
    recovery_rate?: number | null
    total_retries?: number | null
    failures_by_category?: Array<{ key: string; count: number }>
  }
  [key: string]: unknown
}

export interface DashboardData {
  stats: SummaryStats
  recent_runs: Run[]
  leaderboard: LeaderboardEntry[]
  score_trend: { label: string; [agent: string]: string | number }[]
  cost_by_benchmark: { name: string; value: number; color: string }[]
  /** Analytics computed by the backend from stored runs (never from fixtures). */
  analytics?: AnalyticsPayload
  /** Where the dashboard payload came from, as reported by the backend. */
  data_source?: string
  demo_data?: boolean
}

export interface ApiState {
  loading: boolean
  error: string | null
  usingMock: boolean
}
