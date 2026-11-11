"""Static catalogue — mirrors frontend/src/lib/mockData.ts so real data replaces fixtures 1:1."""
from __future__ import annotations

import re

from .hidden_tests import SPECS

# Bump when benchmarks, tasks, or built-in agents change in a way that should
# force a catalogue resync on existing databases.
CATALOGUE_VERSION = "2026.03.1-100tasks-5bench-3agents"

DIFFICULTY_TESTS = {"easy": 3, "medium": 5, "hard": 8, "expert": 11}
DIFFICULTY_CYCLE = ["easy", "easy", "medium", "medium", "medium", "hard", "medium", "easy",
                    "hard", "medium", "expert", "medium", "easy", "hard", "medium"]

_T = lambda name, desc: {"name": name, "description": desc}  # noqa: E731
FS_READ = _T("fs_read", "Read a file from the sandbox filesystem")
FS_WRITE = _T("fs_write", "Create or overwrite a file")
SHELL = _T("shell", "Execute a shell command inside the sandbox")
GREP = _T("grep", "Search file contents by pattern")
PY_EXEC = _T("python_exec", "Run a Python snippet and capture stdout")
LINT = _T("lint", "Run the configured linter on a path")
PYTEST = _T("pytest", "Run the project test suite")

AGENTS = [
    {
        "id": "atlas-coder", "name": "Atlas Coder", "model": "gemini-2.5-pro", "model_provider": "Google AI",
        "description": "High-capability generalist. ReAct loop with a 20-step scratchpad, full filesystem and shell access.",
        "system_prompt_version": "sys-2.4.1", "tools": [FS_READ, FS_WRITE, SHELL, GREP, PY_EXEC],
        "orchestration": "ReAct loop (think → act → observe)", "memory": "Scratchpad window, 20 messages",
        "color_index": 0, "enabled": True, "cost_per_1k_input": 0.00125, "cost_per_1k_output": 0.01,
        "registered_at": "2026-02-11T09:20:00Z",
    },
    {
        "id": "nova-coder", "name": "Nova Coder", "model": "gemini-2.5-flash", "model_provider": "Google AI",
        "description": "Fast, cheap baseline. Plan → Act → Verify with no persistent memory and a restricted toolset.",
        "system_prompt_version": "sys-2.4.1", "tools": [FS_READ, FS_WRITE, SHELL, PY_EXEC],
        "orchestration": "Plan → Act → Verify (single pass)", "memory": "None (stateless)",
        "color_index": 1, "enabled": True, "cost_per_1k_input": 0.0003, "cost_per_1k_output": 0.0025,
        "registered_at": "2026-02-11T09:24:00Z",
    },
    {
        "id": "forge-coder", "name": "Forge Coder", "model": "gemini-2.5-pro", "model_provider": "OpenRouter",
        "description": "Deliberate engineering agent. LangGraph state machine with lint/test tooling and a vector scratchpad.",
        "system_prompt_version": "sys-2.4.1", "tools": [FS_READ, FS_WRITE, SHELL, GREP, LINT, PYTEST],
        "orchestration": "LangGraph state machine (plan · code · test · repair)", "memory": "Vector scratchpad, top-k = 8",
        "color_index": 2, "enabled": True, "cost_per_1k_input": 0.0014, "cost_per_1k_output": 0.011,
        "registered_at": "2026-02-14T15:02:00Z",
    },
]

BENCHMARKS = [
    {"id": "python-core", "name": "Python Fundamentals",
     "description": "Core Python competency: algorithms, data structures, idioms and test writing.",
     "categories": ["Fundamentals", "Algorithms", "Data Structures", "Testing"], "version": "v1.3",
     "tags": ["python", "core-skills"], "created_at": "2026-01-18T10:00:00Z"},
    {"id": "debug-suite", "name": "Debugging & Fixes",
     "description": "Fault localisation and repair across sorting, caching, iteration and error handling.",
     "categories": ["Sorting", "Logic Errors", "Edge Cases", "Exception Handling"], "version": "v1.1",
     "tags": ["python", "debugging"], "created_at": "2026-01-24T10:00:00Z"},
    {"id": "api-dev", "name": "REST API Engineering",
     "description": "Design and implement HTTP endpoints with validation, auth, pagination and error semantics.",
     "categories": ["REST Design", "Routing", "Serialization", "Auth"], "version": "v1.0",
     "tags": ["api", "fastapi", "http"], "created_at": "2026-02-02T10:00:00Z"},
    {"id": "file-io-stats", "name": "File & Text Analytics",
     "description": "Streaming file processing: parsing, aggregation, statistics and reporting.",
     "categories": ["Parsing", "Aggregation", "Encoding", "Reporting"], "version": "v0.9",
     "tags": ["files", "data"], "created_at": "2026-02-08T10:00:00Z"},
    {"id": "swe-lite", "name": "SWE-Lite",
     "description": "Miniature software-engineering tasks — bugfixes, features, refactors and test repair.",
     "categories": ["Bugfix", "Feature", "Refactor", "Tests"], "version": "v2.0",
     "tags": ["swe", "realistic"], "created_at": "2026-02-16T10:00:00Z"},
]

TASK_TITLES = {
    "python-core": [
        "Write a Python palindrome function", "Implement FizzBuzz with a twist", "Write a memoised Fibonacci generator",
        "Detect prime numbers efficiently", "Reverse a linked list", "Implement binary search", "Merge two sorted lists",
        "Flatten a nested list", "Implement an LRU cache", "Build a word frequency counter", "Check for valid parentheses",
        "Implement a stack and a queue", "Convert Roman numerals to integers", "Transpose a matrix", "Write a retry decorator",
        "Implement a simple event emitter", "Parse a CSV string into dictionaries", "Implement a context-manager timer",
        "Chunk a list into fixed-size groups", "Bubble sort with an early exit", "Compute a string checksum",
        "Implement a singleton metaclass", "Solve a maze recursively", "Implement a token-bucket rate limiter"],
    "debug-suite": [
        "Debug a broken bubble sort", "Debug a broken quicksort partition", "Debug a broken binary search",
        "Fix an off-by-one in list slicing", "Debug a broken merge sort", "Debug LRU cache eviction",
        "Debug a broken palindrome checker", "Debug an incorrect Fibonacci memo", "Debug a broken stack implementation",
        "Debug a broken group-by iterator", "Debug a broken retry decorator", "Debug a broken timeout handler",
        "Debug a broken deep copy", "Debug a broken event emitter", "Debug a broken rate limiter",
        "Debug a broken tokenizer", "Debug a broken matrix rotation", "Debug a broken dependency resolver"],
    "api-dev": [
        "Create a REST health-check endpoint", "Implement CRUD endpoints for a resource", "Add path parameters and validation",
        "Add query-parameter filtering", "Implement cursor-based pagination", "Build a nested resource route",
        "Implement request-body schema validation", "Add structured error responses", "Implement API-key authentication",
        "Add rate-limit headers", "Implement a file upload endpoint", "Build a bulk batch endpoint",
        "Add content negotiation", "Implement idempotency keys", "Add optimistic concurrency with ETags",
        "Stream a paginated response"],
    "file-io-stats": [
        "Read a text file and calculate statistics", "Count word frequency across a directory",
        "Compute line and character statistics", "Parse a JSONL file and aggregate", "Compute a rolling average from CSV",
        "Detect duplicate records in a file", "Build a histogram of numeric values", "Extract and count email addresses",
        "Compute a diff between two files", "Generate and verify a compressed report", "Stream a large file and count matches",
        "Merge multiple files into one corpus"],
    "swe-lite": [
        "Fix incorrect date arithmetic in utils", "Add pagination to the users endpoint", "Fix a race condition in the cache layer",
        "Migrate deprecated logging calls", "Handle empty input in the parser", "Fix broken timezone conversion",
        "Add type hints to the request models", "Fix a memory leak in the streaming client",
        "Support the new retry policy in the HTTP client", "Correct the retry backoff calculation",
        "Add validation to the webhook handler", "Fix a flaky timezone-aware test", "Implement a missing __eq__ on the domain object",
        "Add structured logging to the worker", "Fix incorrect sorting of nested records", "Add bulk export to the reporting service",
        "Fix a null dereference in the resolver", "Migrate configuration to environment variables", "Add idempotent job submission",
        "Remove duplicate records after retry", "Support partial batch failure", "Add rate limits to the public API",
        "Fix incorrect currency rounding", "Add request tracing identifiers", "Fix dependency version resolution",
        "Harden file path handling", "Add missing pagination defaults", "Fix inconsistent JSON key casing",
        "Add health probes for dependencies", "Fix flaky async timing in tests"],
}

PROMPT_TEMPLATES = {
    "python-core": "Implement the following in Python 3.11. Write the code to `solution.py`. Your implementation must satisfy every hidden unit test.\n\n{task}",
    "debug-suite": "The file `broken.py` contains a bug. Diagnose it, then write the corrected implementation to `solution.py`. Preserve the public API.\n\n{task}",
    "api-dev": "Build a FastAPI application in `app.py` exposing the required endpoint(s). Include request validation and typed responses.\n\n{task}",
    "file-io-stats": "Read the provided data file and produce the requested output. Write your solution to `solution.py`.\n\n{task}",
    "swe-lite": "A small Python repository is mounted at `/workspace/repo`. Implement the change described below, following existing conventions and keeping the test suite green.\n\n{task}",
}


def slug(s: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))


def build_catalogue() -> tuple[list[dict], list[tuple[dict, str | None]]]:
    """Returns (benchmarks, [(task, hidden_tests_or_None)]). task_count is always
    derived from the generated task list, never a hardcoded stale value."""
    tasks: list[tuple[dict, str | None]] = []
    benchmarks: list[dict] = []
    for b in BENCHMARKS:
        bt: list[dict] = []
        for i, title in enumerate(TASK_TITLES[b["id"]]):
            tid = f"{b['id']}-t{i + 1:02d}"
            category = b["categories"][i % len(b["categories"])]
            difficulty = DIFFICULTY_CYCLE[i % len(DIFFICULTY_CYCLE)]
            spec = SPECS.get(tid)
            hidden = spec["tests"] if spec else None
            test_count = len(re.findall(r"^def test_", hidden, re.M)) if hidden else DIFFICULTY_TESTS[difficulty]
            task_text = f"{title}.\n\n{spec['prompt']}" if spec else title
            bt.append({
                "id": tid, "benchmark_id": b["id"], "title": title, "category": category, "difficulty": difficulty,
                "prompt": PROMPT_TEMPLATES[b["id"]].replace("{task}", task_text),
                "test_count": test_count, "time_limit_sec": 120, "max_tokens": 32_000,
                "tags": [slug(category), difficulty], "reference_solution_lines": 12 + (i % 9) * 7,
            })
            tasks.append((bt[-1], hidden))
        mix = {"easy": 0, "medium": 0, "hard": 0, "expert": 0}
        for t in bt:
            mix[t["difficulty"]] += 1
        benchmarks.append({**b, "task_count": len(bt), "difficulty_mix": mix,
                           "total_time_limit_sec": sum(t["time_limit_sec"] for t in bt)})
    return benchmarks, tasks


def catalogue_integrity() -> dict:
    """Static integrity report for the in-code catalogue (no DB required)."""
    benchmarks, tasks = build_catalogue()
    task_ids = [t["id"] for t, _ in tasks]
    missing_hidden = [t["id"] for t, h in tasks if not h]
    by_bench = {}
    for t, _ in tasks:
        by_bench.setdefault(t["benchmark_id"], 0)
        by_bench[t["benchmark_id"]] += 1
    return {
        "catalogue_version": CATALOGUE_VERSION,
        "benchmark_count": len(benchmarks),
        "task_count": len(tasks),
        "builtin_agent_count": len(AGENTS),
        "task_ids_unique": len(task_ids) == len(set(task_ids)),
        "tasks_per_benchmark": by_bench,
        "tasks_missing_hidden_tests": missing_hidden,
        "all_live_tasks_have_hidden_tests": len(missing_hidden) == 0,
        "benchmarks": [
            {
                "id": b["id"],
                "task_count": b["task_count"],
                "version": b.get("version"),
            }
            for b in benchmarks
        ],
        "builtin_agent_ids": [a["id"] for a in AGENTS],
    }
