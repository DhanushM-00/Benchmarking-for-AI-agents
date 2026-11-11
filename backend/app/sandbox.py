"""Sandbox: grade a solution against a hidden test suite.

Isolation levels
  docker     `docker run --network none --memory --cpus --pids-limit`, workspace mounted read-only.
  subprocess `python -I` with RLIMITs, stripped environment, throwaway cwd. It CANNOT block the
             network and shares the host kernel — fine for a trusted dev box, not for untrusted code.

If docker is requested but unavailable the sandbox falls back to subprocess and reports what it
actually used, so the fairness report can flag the downgrade instead of hiding it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

RESULT_MARK = "__BIFROST_RESULT__"

RUNNER = r'''
import importlib.util, json, os, sys, traceback
sys.path.insert(0, os.getcwd())
MARK = "__BIFROST_RESULT__"

def out(passed, total, error=None, failures=None):
    print(MARK + json.dumps({"passed": passed, "total": total, "error": error, "failures": failures or []}))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

try:
    sys.setrecursionlimit(10000)
    load("solution", "solution.py")
except BaseException as e:
    tests_src = open("hidden_tests.py").read()
    total = sum(1 for l in tests_src.splitlines() if l.startswith("def test_"))
    out(0, total, "solution failed to import: %s: %s" % (type(e).__name__, e))
    sys.exit(0)

try:
    t = load("hidden_tests", "hidden_tests.py")
except BaseException as e:
    out(0, 0, "test suite error: %s" % e)
    sys.exit(0)

names = [n for n in dir(t) if n.startswith("test_") and callable(getattr(t, n))]
passed, failures = 0, []
for n in names:
    try:
        getattr(t, n)()
        passed += 1
    except BaseException as e:
        failures.append(n + ": " + type(e).__name__)
out(passed, len(names), None, failures)
'''


@dataclass
class GradeResult:
    passed: int
    total: int
    error: str | None
    duration_sec: float
    isolation_used: str
    network_blocked: bool
    timed_out: bool = False


_docker_ok: bool | None = None


def docker_available() -> bool:
    global _docker_ok
    if _docker_ok is None:
        _docker_ok = False
        if shutil.which("docker"):
            try:
                _docker_ok = subprocess.run(["docker", "info"], capture_output=True, timeout=4).returncode == 0
            except Exception:
                _docker_ok = False
    return _docker_ok


def _limits(timeout: int, mem_mb: int):
    def apply() -> None:  # runs in the child between fork and exec (POSIX only)
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (timeout + 1, timeout + 1))
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 2**20 * 2, mem_mb * 2**20 * 2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 2**20, 10 * 2**20))
        os.setsid()
    return apply


def _count_tests(src: str) -> int:
    return len(re.findall(r"^def test_", src, re.M))


def grade(solution_code: str, hidden_tests: str, *, timeout_sec: int, isolation: str, image: str,
          network_policy: str, memory_mb: int = 256, require_docker: bool = False) -> GradeResult:
    """Grade solution against hidden tests.

    Security:
      - Preferred path is Docker with network/memory/pid limits.
      - If isolation=docker but Docker is unavailable:
          * require_docker=True  → fail closed (do NOT run untrusted code on host)
          * require_docker=False → subprocess fallback with RLIMIT + stripped env (reported in result)
    """
    total = _count_tests(hidden_tests)
    if isolation == "docker" and not docker_available():
        if require_docker:
            return GradeResult(
                0, total,
                "Sandbox unavailable: isolation=docker was required but Docker is not available. "
                "Refusing to execute untrusted code on the host.",
                0.0, "unavailable", False, timed_out=False,
            )
    use_docker = isolation == "docker" and docker_available()
    used = "docker" if use_docker else "subprocess"
    blocked = use_docker and network_policy == "none"

    with tempfile.TemporaryDirectory(prefix="bifrost-") as tmp:
        d = Path(tmp)
        (d / "solution.py").write_text(solution_code)
        (d / "hidden_tests.py").write_text(hidden_tests)
        (d / "runner.py").write_text(RUNNER)
        os.chmod(tmp, 0o755)
        for f in d.iterdir():
            os.chmod(f, 0o644)

        if use_docker:
            cmd = ["docker", "run", "--rm", "--user", "65534", "--memory", f"{memory_mb}m", "--cpus", "1",
                   "--pids-limit", "128", "-v", f"{tmp}:/work:ro", "-w", "/work"]
            if network_policy == "none":
                cmd += ["--network", "none"]
            cmd += [image, "python", "-I", "runner.py"]
            kwargs: dict = {}
        else:
            cmd = [sys.executable, "-I", "runner.py"]
            kwargs = {"cwd": tmp,
                      "env": {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONHASHSEED": "0",
                              "PYTHONDONTWRITEBYTECODE": "1"}}
            if os.name == "posix":
                kwargs["preexec_fn"] = _limits(timeout_sec, memory_mb)

        t0 = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, **kwargs)
        except subprocess.TimeoutExpired:
            return GradeResult(0, total, "Sandbox timeout — agent did not finish within the limit.",
                               time.monotonic() - t0, used, blocked, timed_out=True)
        dur = time.monotonic() - t0

    line = next((l for l in reversed(proc.stdout.splitlines()) if l.startswith(RESULT_MARK)), None)
    if line is None:
        tail = (proc.stderr or proc.stdout or "no output").strip().splitlines()[-1:] or ["no output"]
        return GradeResult(0, total, f"Sandbox crashed: {tail[0][:160]}", dur, used, blocked)
    data = json.loads(line[len(RESULT_MARK):])
    err = data["error"]
    if not err and data["failures"]:
        err = "Tests failed: " + ", ".join(data["failures"][:3])
    return GradeResult(data["passed"], data["total"], err, dur, used, blocked)
