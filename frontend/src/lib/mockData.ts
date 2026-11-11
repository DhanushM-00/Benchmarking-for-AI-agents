import type {
  Agent,
  AgentRunResult,
  Benchmark,
  FairnessConfig,
  FairnessReport,
  IntegrityCheck,
  LeaderboardEntry,
  MetricKey,
  Run,
  Task,
  TaskResult,
  ToolCall,
} from '@/types'
import { mean, quantile, seededRandom } from '@/lib/utils'
import { slug } from '@/lib/format'

/* ============================================================
   Fixture catalogue — mirrors what the FastAPI backend serves.
   ============================================================ */

export const MOCK_AGENTS: Agent[] = [
  {
    id: 'atlas-coder',
    name: 'Atlas Coder',
    model: 'gemini-2.5-pro',
    model_provider: 'Google AI',
    description:
      'High-capability generalist. ReAct loop with a 20-step scratchpad, full filesystem and shell access.',
    system_prompt_version: 'sys-2.4.1',
    tools: [
      { name: 'fs_read', description: 'Read a file from the sandbox filesystem' },
      { name: 'fs_write', description: 'Create or overwrite a file' },
      { name: 'shell', description: 'Execute a shell command inside the sandbox' },
      { name: 'grep', description: 'Search file contents by pattern' },
      { name: 'python_exec', description: 'Run a Python snippet and capture stdout' },
    ],
    orchestration: 'ReAct loop (think → act → observe)',
    memory: 'Scratchpad window, 20 messages',
    color_index: 0,
    enabled: true,
    cost_per_1k_input: 0.00125,
    cost_per_1k_output: 0.01,
    registered_at: '2026-02-11T09:20:00Z',
  },
  {
    id: 'nova-coder',
    name: 'Nova Coder',
    model: 'gemini-2.5-flash',
    model_provider: 'Google AI',
    description:
      'Fast, cheap baseline. Plan → Act → Verify with no persistent memory and a restricted toolset.',
    system_prompt_version: 'sys-2.4.1',
    tools: [
      { name: 'fs_read', description: 'Read a file from the sandbox filesystem' },
      { name: 'fs_write', description: 'Create or overwrite a file' },
      { name: 'shell', description: 'Execute a shell command inside the sandbox' },
      { name: 'python_exec', description: 'Run a Python snippet and capture stdout' },
    ],
    orchestration: 'Plan → Act → Verify (single pass)',
    memory: 'None (stateless)',
    color_index: 1,
    enabled: true,
    cost_per_1k_input: 0.0003,
    cost_per_1k_output: 0.0025,
    registered_at: '2026-02-11T09:24:00Z',
  },
  {
    id: 'forge-coder',
    name: 'Forge Coder',
    model: 'gemini-2.5-pro',
    model_provider: 'OpenRouter',
    description:
      'Deliberate engineering agent. LangGraph state machine with lint/test tooling and a vector scratchpad.',
    system_prompt_version: 'sys-2.4.1',
    tools: [
      { name: 'fs_read', description: 'Read a file from the sandbox filesystem' },
      { name: 'fs_write', description: 'Create or overwrite a file' },
      { name: 'shell', description: 'Execute a shell command inside the sandbox' },
      { name: 'grep', description: 'Search file contents by pattern' },
      { name: 'lint', description: 'Run the configured linter on a path' },
      { name: 'pytest', description: 'Run the project test suite' },
    ],
    orchestration: 'LangGraph state machine (plan · code · test · repair)',
    memory: 'Vector scratchpad, top-k = 8',
    color_index: 2,
    enabled: true,
    cost_per_1k_input: 0.0014,
    cost_per_1k_output: 0.011,
    registered_at: '2026-02-14T15:02:00Z',
  },
]

const BENCHMARK_DEFS: Omit<Benchmark, 'task_count' | 'difficulty_mix' | 'total_time_limit_sec'>[] = [
  {
    id: 'python-core',
    name: 'Python Fundamentals',
    description:
      'Core Python competency: algorithms, data structures, idioms and test writing.',
    categories: ['Fundamentals', 'Algorithms', 'Data Structures', 'Testing'],
    version: 'v1.3',
    tags: ['python', 'core-skills'],
    created_at: '2026-01-18T10:00:00Z',
  },
  {
    id: 'debug-suite',
    name: 'Debugging & Fixes',
    description:
      'Fault localisation and repair across sorting, caching, iteration and error handling.',
    categories: ['Sorting', 'Logic Errors', 'Edge Cases', 'Exception Handling'],
    version: 'v1.1',
    tags: ['python', 'debugging'],
    created_at: '2026-01-24T10:00:00Z',
  },
  {
    id: 'api-dev',
    name: 'REST API Engineering',
    description:
      'Design and implement HTTP endpoints with validation, auth, pagination and error semantics.',
    categories: ['REST Design', 'Routing', 'Serialization', 'Auth'],
    version: 'v1.0',
    tags: ['api', 'fastapi', 'http'],
    created_at: '2026-02-02T10:00:00Z',
  },
  {
    id: 'file-io-stats',
    name: 'File & Text Analytics',
    description:
      'Streaming file processing: parsing, aggregation, statistics and reporting.',
    categories: ['Parsing', 'Aggregation', 'Encoding', 'Reporting'],
    version: 'v0.9',
    tags: ['files', 'data'],
    created_at: '2026-02-08T10:00:00Z',
  },
  {
    id: 'swe-lite',
    name: 'SWE-Lite',
    description:
      'Miniature software-engineering tasks — bugfixes, features, refactors and test repair.',
    categories: ['Bugfix', 'Feature', 'Refactor', 'Tests'],
    version: 'v2.0',
    tags: ['swe', 'realistic'],
    created_at: '2026-02-16T10:00:00Z',
  },
]

const TASK_TITLES: Record<string, string[]> = {
  'python-core': [
    'Write a Python palindrome function',
    'Implement FizzBuzz with a twist',
    'Write a memoised Fibonacci generator',
    'Detect prime numbers efficiently',
    'Reverse a linked list',
    'Implement binary search',
    'Merge two sorted lists',
    'Flatten a nested list',
    'Implement an LRU cache',
    'Build a word frequency counter',
    'Check for valid parentheses',
    'Implement a stack and a queue',
    'Convert Roman numerals to integers',
    'Transpose a matrix',
    'Write a retry decorator',
    'Implement a simple event emitter',
    'Parse a CSV string into dictionaries',
    'Implement a context-manager timer',
    'Chunk a list into fixed-size groups',
    'Bubble sort with an early exit',
    'Compute a string checksum',
    'Implement a singleton metaclass',
    'Solve a maze recursively',
    'Implement a token-bucket rate limiter',
  ],
  'debug-suite': [
    'Debug a broken bubble sort',
    'Debug a broken quicksort partition',
    'Debug a broken binary search',
    'Fix an off-by-one in list slicing',
    'Debug a broken merge sort',
    'Debug LRU cache eviction',
    'Debug a broken palindrome checker',
    'Debug an incorrect Fibonacci memo',
    'Debug a broken stack implementation',
    'Debug a broken group-by iterator',
    'Debug a broken retry decorator',
    'Debug a broken timeout handler',
    'Debug a broken deep copy',
    'Debug a broken event emitter',
    'Debug a broken rate limiter',
    'Debug a broken tokenizer',
    'Debug a broken matrix rotation',
    'Debug a broken dependency resolver',
  ],
  'api-dev': [
    'Create a REST health-check endpoint',
    'Implement CRUD endpoints for a resource',
    'Add path parameters and validation',
    'Add query-parameter filtering',
    'Implement cursor-based pagination',
    'Build a nested resource route',
    'Implement request-body schema validation',
    'Add structured error responses',
    'Implement API-key authentication',
    'Add rate-limit headers',
    'Implement a file upload endpoint',
    'Build a bulk batch endpoint',
    'Add content negotiation',
    'Implement idempotency keys',
    'Add optimistic concurrency with ETags',
    'Stream a paginated response',
  ],
  'file-io-stats': [
    'Read a text file and calculate statistics',
    'Count word frequency across a directory',
    'Compute line and character statistics',
    'Parse a JSONL file and aggregate',
    'Compute a rolling average from CSV',
    'Detect duplicate records in a file',
    'Build a histogram of numeric values',
    'Extract and count email addresses',
    'Compute a diff between two files',
    'Generate and verify a compressed report',
    'Stream a large file and count matches',
    'Merge multiple files into one corpus',
  ],
  'swe-lite': [
    'Fix incorrect date arithmetic in utils',
    'Add pagination to the users endpoint',
    'Fix a race condition in the cache layer',
    'Migrate deprecated logging calls',
    'Handle empty input in the parser',
    'Fix broken timezone conversion',
    'Add type hints to the request models',
    'Fix a memory leak in the streaming client',
    'Support the new retry policy in the HTTP client',
    'Correct the retry backoff calculation',
    'Add validation to the webhook handler',
    'Fix a flaky timezone-aware test',
    'Implement a missing __eq__ on the domain object',
    'Add structured logging to the worker',
    'Fix incorrect sorting of nested records',
    'Add bulk export to the reporting service',
    'Fix a null dereference in the resolver',
    'Migrate configuration to environment variables',
    'Add idempotent job submission',
    'Remove duplicate records after retry',
    'Support partial batch failure',
    'Add rate limits to the public API',
    'Fix incorrect currency rounding',
    'Add request tracing identifiers',
    'Fix dependency version resolution',
    'Harden file path handling',
    'Add missing pagination defaults',
    'Fix inconsistent JSON key casing',
    'Add health probes for dependencies',
    'Fix flaky async timing in tests',
  ],
}

const DIFFICULTY_CYCLE: Task['difficulty'][] = [
  'easy', 'easy', 'medium', 'medium', 'medium', 'hard', 'medium', 'easy',
  'hard', 'medium', 'expert', 'medium', 'easy', 'hard', 'medium',
]

const PROMPT_TEMPLATES: Record<string, string> = {
  'python-core':
    'Implement the following in Python 3.11. Write the code to `solution.py`. Your implementation must satisfy every hidden unit test.\n\n{task}',
  'debug-suite':
    'The file `broken.py` contains a bug. Diagnose it, then write the corrected implementation to `solution.py`. Preserve the public API.\n\n{task}',
  'api-dev':
    'Build a FastAPI application in `app.py` exposing the required endpoint(s). Include request validation and typed responses.\n\n{task}',
  'file-io-stats':
    'Read the provided data file and produce the requested output. Write your solution to `solution.py`.\n\n{task}',
  'swe-lite':
    'A small Python repository is mounted at `/workspace/repo`. Implement the change described below, following existing conventions and keeping the test suite green.\n\n{task}',
}

export const buildTasks = (): Task[] => {
  const tasks: Task[] = []
  for (const bench of BENCHMARK_DEFS) {
    const titles = TASK_TITLES[bench.id] ?? []
    titles.forEach((title, i) => {
      const category = bench.categories[i % bench.categories.length]
      const difficulty = DIFFICULTY_CYCLE[i % DIFFICULTY_CYCLE.length]
      tasks.push({
        id: `${bench.id}-t${String(i + 1).padStart(2, '0')}`,
        benchmark_id: bench.id,
        title,
        category,
        difficulty,
        prompt: (PROMPT_TEMPLATES[bench.id] ?? '{task}').replace('{task}', title),
        test_count: difficulty === 'easy' ? 3 : difficulty === 'medium' ? 5 : difficulty === 'hard' ? 8 : 11,
        time_limit_sec: 120,
        max_tokens: 32_000,
        tags: [slug(category), difficulty],
        reference_solution_lines: 12 + (i % 9) * 7,
      })
    })
  }
  return tasks
}

export const MOCK_TASKS: Task[] = buildTasks()

export const MOCK_BENCHMARKS: Benchmark[] = BENCHMARK_DEFS.map((b) => {
  const bt = MOCK_TASKS.filter((t) => t.benchmark_id === b.id)
  const mix = { easy: 0, medium: 0, hard: 0, expert: 0 }
  bt.forEach((t) => (mix[t.difficulty] += 1))
  return {
    ...b,
    task_count: bt.length,
    difficulty_mix: mix,
    total_time_limit_sec: bt.reduce((s, t) => s + t.time_limit_sec, 0),
  }
})

/* ============================================================
   Fair Agent Testing Engine
   ============================================================ */

export const DEFAULT_FAIRNESS: FairnessConfig = {
  time_limit_per_task_sec: 120,
  max_tokens_per_task: 32_000,
  repeats: 3,
  isolation: 'docker',
  container_image: 'bifrost/sandbox:py3.11-slim@sha256:9f2c…',
  network_policy: 'none',
  randomize_task_order: true,
  random_seed: 42,
  scorer_version: 'scorer-2026.03.1',
  temperature: 0.2,
  blinded_evaluation: true,
  metric_weights: {
    task_success: 0.25,
    correctness: 0.3,
    efficiency: 0.15,
    tool_usage: 0.15,
    consistency: 0.15,
  },
}

export const buildFairnessReport = (
  cfg: FairnessConfig,
  agentCount: number,
  repeat: number,
): FairnessReport => {
  const checks: IntegrityCheck[] = [
    {
      id: 'dataset',
      label: 'Identical task dataset',
      detail: `All ${agentCount} agents received the same ${repeat > 1 ? 'task set and ordering seed' : 'task set'}.`,
      status: 'pass',
    },
    {
      id: 'instructions',
      label: 'Identical instruction template',
      detail: 'Prompt template pinned to build 2026.03.1 — no agent-specific edits.',
      status: 'pass',
    },
    {
      id: 'timelimit',
      label: 'Equal time limit',
      detail: `${cfg.time_limit_per_task_sec}s per task, enforced by the sandbox supervisor.`,
      status: 'pass',
    },
    {
      id: 'environment',
      label: 'Same execution environment',
      detail: `All agents ran on ${cfg.container_image.split('@')[0]} with identical seeded fixtures.`,
      status: 'pass',
    },
    {
      id: 'budget',
      label: 'Equal token budget',
      detail: `${cfg.max_tokens_per_task.toLocaleString('en-US')} max tokens per task, hard-capped.`,
      status: 'pass',
    },
    {
      id: 'network',
      label: 'Network policy enforced',
      detail: cfg.network_policy === 'none' ? 'Network fully disabled in the sandbox.' : `Network policy: ${cfg.network_policy}.`,
      status: cfg.network_policy === 'none' ? 'pass' : 'warn',
    },
    {
      id: 'scoring',
      label: 'Same scoring rules',
      detail: `Single scorer ${cfg.scorer_version} applied to every result.`,
      status: 'pass',
    },
    {
      id: 'repeats',
      label: 'Repeated runs',
      detail: `${cfg.repeats} repeat${cfg.repeats > 1 ? 's' : ''} per agent; median score reported, variance tracked.`,
      status: cfg.repeats >= 2 ? 'pass' : 'warn',
    },
    {
      id: 'blinding',
      label: 'Blinded evaluation',
      detail: cfg.blinded_evaluation
        ? 'Judge prompts contain no agent identity or model name.'
        : 'Judge can see agent identity — scores may be biased.',
      status: cfg.blinded_evaluation ? 'pass' : 'fail',
    },
    {
      id: 'isolation',
      label: 'Run isolation',
      detail: `${cfg.isolation} isolation; no shared filesystem state between agents.`,
      status: 'pass',
    },
  ]

  const violations = checks.filter((c) => c.status === 'fail').map((c) => c.label)
  const warnings = checks.filter((c) => c.status === 'warn').length
  const score = Math.max(
    0,
    Math.round((checks.reduce((s, c) => s + (c.status === 'pass' ? 1 : c.status === 'warn' ? 0.5 : 0), 0) / checks.length) * 100),
  )

  return { score, checks, violations: warnings ? [] : violations }
}

/* ============================================================
   Run simulation
   ============================================================ */

const AGENT_PROFILE: Record<string, {
  completion: number
  correctness: number
  speed: number
  toolQuality: number
  toolCount: number
  effort: number
}> = {
  'atlas-coder': { completion: 0.76, correctness: 79, speed: 1.0, toolQuality: 84, toolCount: 4, effort: 1.0 },
  'nova-coder': { completion: 0.62, correctness: 66, speed: 0.61, toolQuality: 71, toolCount: 3, effort: 0.72 },
  'forge-coder': { completion: 0.84, correctness: 88, speed: 1.48, toolQuality: 91, toolCount: 5, effort: 1.35 },
}

const DIFF_ADJ: Record<Task['difficulty'], number> = {
  easy: 0.1, medium: 0, hard: -0.09, expert: -0.17,
}

const makeToolCalls = (agent: Agent, rng: () => number, count: number): ToolCall[] => {
  const names = agent.tools.map((t) => t.name)
  const calls: ToolCall[] = []
  for (let i = 0; i < count; i++) {
    const tool = names[Math.floor(rng() * names.length)]
    const outcomeRoll = rng()
    const outcome: ToolCall['outcome'] = outcomeRoll > 0.88 ? 'error' : outcomeRoll > 0.82 ? 'rejected' : 'success'
    calls.push({
      tool,
      args_summary:
        tool === 'fs_read' ? 'path=src/module.py' : tool === 'fs_write' ? 'path=solution.py' : tool === 'shell' ? 'cmd=pytest -q' : 'query="def main"',
      outcome,
      duration_ms: Math.round(120 + rng() * 2400),
    })
  }
  return calls
}

export const simulateAgentRun = (
  agent: Agent,
  tasks: Task[],
  cfg: FairnessConfig,
  seed: number,
): AgentRunResult => {
  const profile = AGENT_PROFILE[agent.id] ?? AGENT_PROFILE['atlas-coder']
  const rng = seededRandom(seed)
  const results: TaskResult[] = []

  for (const task of tasks) {
    const p = Math.min(0.97, Math.max(0.05, profile.completion + DIFF_ADJ[task.difficulty]))
    const completed = rng() < p
    const correctness = completed
      ? Math.min(100, Math.max(30, profile.correctness + (rng() - 0.45) * 34 + DIFF_ADJ[task.difficulty] * 60))
      : Math.round(rng() * 28)

    const testsPassed = Math.round((correctness / 100) * task.test_count)
    const execTime = Math.max(
      1.2,
      (9 + task.test_count * 1.7) * profile.speed * (0.72 + rng() * 0.62) * (1 - DIFF_ADJ[task.difficulty] * 0.6),
    )

    const tokensIn = Math.round(620 + task.test_count * 46 + rng() * 520)
    const tokensOut = Math.round(
      (320 + task.test_count * 128) * profile.effort * (0.6 + rng() * 0.9) * (completed ? 1 : 0.45),
    )
    const tokensCached = Math.round(tokensIn * (0.12 + rng() * 0.3))

    const toolCount = Math.max(0, Math.round(profile.toolCount * (0.6 + rng() * 0.9)))
    const toolCalls = makeToolCalls(agent, rng, toolCount)
    const unnecessarySteps = Math.max(
      0,
      Math.round((toolCount * 0.32 - (rng() * 1.6 - 0.2)) * profile.effort),
    )

    const efficiency = Math.max(
      5,
      Math.min(100, 100 - unnecessarySteps * 7.5 - (execTime / cfg.time_limit_per_task_sec) * 28),
    )
    const toolUsage = Math.max(
      10,
      Math.min(100, profile.toolQuality + (rng() - 0.5) * 22 - toolCalls.filter((c) => c.outcome === 'error').length * 6),
    )

    results.push({
      task_id: task.id,
      task_title: task.title,
      category: task.category,
      difficulty: task.difficulty,
      completed,
      correctness: Math.round(correctness * 10) / 10,
      unit_tests_passed: testsPassed,
      unit_tests_total: task.test_count,
      execution_time_sec: Math.round(execTime * 10) / 10,
      tokens_input: tokensIn,
      tokens_output: tokensOut,
      tokens_cached: tokensCached,
      cost_usd: Math.round(
        ((tokensIn / 1000) * agent.cost_per_1k_input + (tokensOut / 1000) * agent.cost_per_1k_output) * 10000,
      ) / 10000,
      tool_calls: toolCalls,
      unnecessary_steps: unnecessarySteps,
      efficiency_score: Math.round(efficiency * 10) / 10,
      tool_usage_score: Math.round(toolUsage * 10) / 10,
      error: completed ? undefined : rng() > 0.5 ? 'Sandbox timeout — agent did not finish within the limit.' : 'Tests failed; agent halted after max repair steps.',
    })
  }

  const completedCount = results.filter((r) => r.completed).length
  const times = results.map((r) => r.execution_time_sec)
  const scores: MetricKey[] = ['task_success', 'correctness', 'efficiency', 'tool_usage', 'consistency']

  const repeatVariance = Math.round((seededRandom(seed + 7)() * 9 + 1) * 10) / 10
  const consistency = Math.max(40, Math.min(100, 100 - repeatVariance * 2.1))

  const metrics: Record<MetricKey, number> = {
    task_success: Math.round((completedCount / results.length) * 1000) / 10,
    correctness: Math.round(mean(results.map((r) => r.correctness)) * 10) / 10,
    efficiency: Math.round(mean(results.map((r) => r.efficiency_score)) * 10) / 10,
    tool_usage: Math.round(mean(results.map((r) => r.tool_usage_score)) * 10) / 10,
    consistency: Math.round(consistency * 10) / 10,
  }

  const overall = Math.round(
    scores.reduce((s, k) => s + metrics[k] * cfg.metric_weights[k], 0) * 10,
  ) / 10

  return {
    agent_id: agent.id,
    agent_name: agent.name,
    color_index: agent.color_index,
    status: 'completed',
    tasks_completed: completedCount,
    tasks_total: results.length,
    task_results: results,
    metrics,
    overall_score: overall,
    avg_execution_time_sec: Math.round(mean(times) * 10) / 10,
    p95_execution_time_sec: Math.round(quantile(times, 0.95) * 10) / 10,
    total_tokens: results.reduce((s, r) => s + r.tokens_input + r.tokens_output, 0),
    total_cost_usd: Math.round(results.reduce((s, r) => s + r.cost_usd, 0) * 10000) / 10000,
    tool_calls_total: results.reduce((s, r) => s + r.tool_calls.length, 0),
    unnecessary_steps_total: results.reduce((s, r) => s + r.unnecessary_steps, 0),
    repeat_variance: repeatVariance,
  }
}

/* ---------- historical runs ---------- */

interface RunSeed {
  id: string
  name: string
  benchmark_id: string
  agent_ids: string[]
  days_ago: number
  hour: number
  status: Run['status']
  notes: string
}

const RUN_SEEDS: RunSeed[] = [
  {
    id: 'run-2481',
    name: 'Sprint 41 · Baseline sweep',
    benchmark_id: 'swe-lite',
    agent_ids: ['atlas-coder', 'nova-coder', 'forge-coder'],
    days_ago: 0, hour: 9, status: 'completed',
    notes: 'Weekly cross-agent regression against the SWE-Lite set.',
  },
  {
    id: 'run-2480',
    name: 'Sprint 41 · SWE-Lite (forge fix)',
    benchmark_id: 'swe-lite',
    agent_ids: ['forge-coder'],
    days_ago: 0, hour: 8, status: 'running',
    notes: 'Re-running Forge after the prompt-template update.',
  },
  {
    id: 'run-2479',
    name: 'API suite · release candidate',
    benchmark_id: 'api-dev',
    agent_ids: ['atlas-coder', 'nova-coder', 'forge-coder'],
    days_ago: 1, hour: 16, status: 'completed',
    notes: 'Pre-release check of the new API design tasks.',
  },
  {
    id: 'run-2478',
    name: 'Debug drill #12',
    benchmark_id: 'debug-suite',
    agent_ids: ['atlas-coder', 'forge-coder'],
    days_ago: 2, hour: 14, status: 'completed',
    notes: 'Two-agent head-to-head on fault localisation.',
  },
  {
    id: 'run-2477',
    name: 'File analytics regression',
    benchmark_id: 'file-io-stats',
    agent_ids: ['nova-coder', 'atlas-coder'],
    days_ago: 3, hour: 11, status: 'completed',
    notes: 'Regression after the streaming-reader change.',
  },
  {
    id: 'run-2476',
    name: 'Python core · full sweep',
    benchmark_id: 'python-core',
    agent_ids: ['atlas-coder', 'nova-coder', 'forge-coder'],
    days_ago: 5, hour: 10, status: 'completed',
    notes: 'Quarterly full sweep of the Python core set.',
  },
  {
    id: 'run-2475',
    name: 'Forge sandbox trial',
    benchmark_id: 'python-core',
    agent_ids: ['forge-coder'],
    days_ago: 6, hour: 13, status: 'failed',
    notes: 'Sandbox image pull failed — rerun after infra fix.',
  },
  {
    id: 'run-2474',
    name: 'SWE-Lite · memory ablation',
    benchmark_id: 'swe-lite',
    agent_ids: ['atlas-coder', 'forge-coder'],
    days_ago: 8, hour: 9, status: 'completed',
    notes: 'Ablation: Forge with vector scratchpad disabled.',
  },
]

const isoFromDaysAgo = (daysAgo: number, hour: number): string => {
  const d = new Date('2026-11-02T12:00:00Z')
  d.setUTCDate(d.getUTCDate() - daysAgo)
  d.setUTCHours(hour, 0, 0, 0)
  return d.toISOString()
}

export const buildMockRuns = (): Run[] =>
  RUN_SEEDS.map((seed, idx) => {
    const bench = MOCK_BENCHMARKS.find((b) => b.id === seed.benchmark_id)!
    const tasks = MOCK_TASKS.filter((t) => t.benchmark_id === seed.benchmark_id)
    const fairness = { ...DEFAULT_FAIRNESS, repeats: idx % 3 === 0 ? 3 : 2 }
    const report = buildFairnessReport(fairness, seed.agent_ids.length, fairness.repeats)

    const agentResults = seed.agent_ids.map((agentId, ai) => {
      const agent = MOCK_AGENTS.find((a) => a.id === agentId)!
      const res = simulateAgentRun(agent, tasks, fairness, 1000 + idx * 37 + ai * 11)
      if (seed.status === 'running') {
        // Trim the live run to a partial state.
        const keep = Math.max(1, Math.floor(tasks.length * 0.42))
        const partial = res.task_results.slice(0, keep)
        const times = partial.map((r) => r.execution_time_sec)
        res.task_results = partial
        res.tasks_completed = partial.filter((r) => r.completed).length
        res.avg_execution_time_sec = Math.round(mean(times) * 10) / 10
        res.status = 'running'
      }
      if (seed.status === 'failed') {
        res.status = 'failed'
      }
      return res
    })

    const duration = agentResults.reduce((s, r) => s + r.avg_execution_time_sec * r.task_results.length, 0)
    const startedAt = isoFromDaysAgo(seed.days_ago, seed.hour)

    return {
      id: seed.id,
      name: seed.name,
      benchmark_id: seed.benchmark_id,
      benchmark_name: bench.name,
      agent_ids: seed.agent_ids,
      agent_results: agentResults,
      status: seed.status,
      fairness,
      fairness_report: report,
      started_at: startedAt,
      finished_at:
        seed.status === 'completed'
          ? new Date(new Date(startedAt).getTime() + duration * 1000).toISOString()
          : null,
      duration_sec: seed.status === 'completed' ? Math.round(duration) : null,
      progress:
        seed.status === 'completed'
          ? 100
          : seed.status === 'running'
            ? 42
            : seed.status === 'failed'
              ? 18
              : 0,
      notes: seed.notes,
      created_by: 'platform-bot',
    }
  })

export const MOCK_RUNS: Run[] = buildMockRuns()

/* ============================================================
   Aggregation helpers — used by the leaderboard and dashboard
   ============================================================ */

export const buildLeaderboard = (runs: Run[], agentIds?: string[]): LeaderboardEntry[] => {
  const completed = runs.filter((r) => r.status === 'completed')
  const acc = new Map<string, LeaderboardEntry>()

  for (const run of completed) {
    for (const ar of run.agent_results) {
      if (agentIds && !agentIds.includes(ar.agent_id)) continue
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
        prev.overall_score = Math.round(((prev.overall_score * n + ar.overall_score) / (n + 1)) * 10) / 10
        prev.task_success = Math.round(((prev.task_success * n + ar.metrics.task_success) / (n + 1)) * 10) / 10
        prev.correctness = Math.round(((prev.correctness * n + ar.metrics.correctness) / (n + 1)) * 10) / 10
        prev.efficiency = Math.round(((prev.efficiency * n + ar.metrics.efficiency) / (n + 1)) * 10) / 10
        prev.tool_usage = Math.round(((prev.tool_usage * n + ar.metrics.tool_usage) / (n + 1)) * 10) / 10
        prev.consistency = Math.round(((prev.consistency * n + ar.metrics.consistency) / (n + 1)) * 10) / 10
        prev.avg_execution_time_sec =
          Math.round(((prev.avg_execution_time_sec * n + ar.avg_execution_time_sec) / (n + 1)) * 10) / 10
        prev.p95_execution_time_sec = Math.round(
          ((prev.p95_execution_time_sec * n + ar.p95_execution_time_sec) / (n + 1)) * 10,
        ) / 10
        prev.total_tokens += ar.total_tokens
        prev.total_cost_usd = Math.round((prev.total_cost_usd + ar.total_cost_usd) * 10000) / 10000
        prev.runs_count += 1
      }
    }
  }

  const sorted = [...acc.values()].sort((a, b) => b.overall_score - a.overall_score)
  sorted.forEach((e, i) => {
    e.rank = i + 1
    e.delta_rank = [0, 1, -1, 1, -1][i % 5]
  })
  return sorted
}

export const buildScoreTrend = (runs: Run[]): { label: string; [k: string]: string | number }[] => {
  const completed = [...runs]
    .filter((r) => r.status === 'completed')
    .sort((a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime())
    .slice(-8)

  return completed.map((run) => {
    const row: { label: string; [k: string]: string | number } = {
      label: run.benchmark_name.split(' ')[0],
    }
    for (const ar of run.agent_results) row[ar.agent_name] = ar.overall_score
    return row
  })
}
