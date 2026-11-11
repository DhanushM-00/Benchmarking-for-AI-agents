"""Real workspace tools used by multi-step agents.

Every invocation is recorded with name, args summary, duration, outcome, and sequence number.
Risky operations (shell, write outside workspace) are permission-checked.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolContext:
    workspace: Path
    network_allowed: bool = False
    allow_shell: bool = True
    allow_write: bool = True
    max_output_chars: int = 12_000
    seq: int = 0
    history: list[dict] = field(default_factory=list)

    def record(
        self,
        name: str,
        args_summary: str,
        outcome: str,
        duration_ms: int,
        error: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        self.seq += 1
        entry = {
            "seq": self.seq,
            "tool": name,
            "args_summary": args_summary[:240],
            "outcome": outcome,  # success | error | rejected
            "duration_ms": duration_ms,
            "error": (error or "")[:240] or None,
        }
        if extra:
            entry.update(extra)
        self.history.append(entry)
        return entry


def _safe_path(ctx: ToolContext, rel: str) -> Path:
    """Resolve path under workspace; reject traversal."""
    rel = (rel or "").strip().lstrip("/")
    if not rel:
        rel = "."
    target = (ctx.workspace / rel).resolve()
    root = ctx.workspace.resolve()
    if root not in target.parents and target != root:
        raise PermissionError(f"path escapes workspace: {rel}")
    return target


def tool_fs_read(ctx: ToolContext, path: str = "solution.py") -> str:
    t0 = time.monotonic()
    try:
        p = _safe_path(ctx, path)
        if not p.is_file():
            ctx.record("fs_read", f"path={path}", "error", int((time.monotonic() - t0) * 1000), "not found")
            return f"ERROR: file not found: {path}"
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > ctx.max_output_chars:
            text = text[: ctx.max_output_chars] + "\n...[truncated]"
        ctx.record("fs_read", f"path={path}", "success", int((time.monotonic() - t0) * 1000))
        return text
    except Exception as e:
        ctx.record("fs_read", f"path={path}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


def tool_fs_write(ctx: ToolContext, path: str = "solution.py", content: str = "") -> str:
    t0 = time.monotonic()
    if not ctx.allow_write:
        ctx.record("fs_write", f"path={path}", "rejected", 0, "write disabled")
        return "ERROR: write permission denied"
    try:
        p = _safe_path(ctx, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content if content is not None else "", encoding="utf-8")
        ctx.record("fs_write", f"path={path} bytes={len(content or '')}", "success", int((time.monotonic() - t0) * 1000))
        return f"OK wrote {path} ({len(content or '')} bytes)"
    except Exception as e:
        ctx.record("fs_write", f"path={path}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


def tool_list_dir(ctx: ToolContext, path: str = ".") -> str:
    t0 = time.monotonic()
    try:
        p = _safe_path(ctx, path)
        if not p.is_dir():
            ctx.record("list_dir", f"path={path}", "error", int((time.monotonic() - t0) * 1000), "not a directory")
            return f"ERROR: not a directory: {path}"
        names = sorted(os.listdir(p))[:200]
        ctx.record("list_dir", f"path={path} n={len(names)}", "success", int((time.monotonic() - t0) * 1000))
        return "\n".join(names) if names else "(empty)"
    except Exception as e:
        ctx.record("list_dir", f"path={path}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


def tool_grep(ctx: ToolContext, pattern: str, path: str = ".") -> str:
    t0 = time.monotonic()
    try:
        root = _safe_path(ctx, path)
        rx = re.compile(pattern)
        hits: list[str] = []
        files = [root] if root.is_file() else list(root.rglob("*.py")) + list(root.rglob("*.txt")) + list(root.rglob("*.md"))
        for f in files[:80]:
            if not f.is_file():
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        rel = f.relative_to(ctx.workspace)
                        hits.append(f"{rel}:{i}: {line.strip()[:160]}")
                        if len(hits) >= 40:
                            break
            except Exception:
                continue
            if len(hits) >= 40:
                break
        ctx.record("grep", f"pattern={pattern!r} path={path}", "success", int((time.monotonic() - t0) * 1000))
        return "\n".join(hits) if hits else "(no matches)"
    except re.error as e:
        ctx.record("grep", f"pattern={pattern!r}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: invalid pattern: {e}"
    except Exception as e:
        ctx.record("grep", f"pattern={pattern!r}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


def tool_shell(ctx: ToolContext, cmd: str, timeout_sec: float = 15.0) -> str:
    t0 = time.monotonic()
    if not ctx.allow_shell:
        ctx.record("shell", f"cmd={cmd[:80]}", "rejected", 0, "shell disabled")
        return "ERROR: shell permission denied"
    # Block obviously dangerous patterns
    banned = ("rm -rf /", "mkfs", ":(){", "shutdown", "reboot", "dd if=", ">/dev/sd")
    low = cmd.lower()
    if any(b in low for b in banned):
        ctx.record("shell", f"cmd={cmd[:80]}", "rejected", 0, "dangerous command blocked")
        return "ERROR: command blocked by policy"
    try:
        env = os.environ.copy()
        if not ctx.network_allowed:
            # Best-effort: do not pass proxy vars; OS-level network block is sandbox's job
            for k in list(env):
                if "proxy" in k.lower():
                    env.pop(k, None)
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ctx.workspace),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > ctx.max_output_chars:
            out = out[: ctx.max_output_chars] + "\n...[truncated]"
        outcome = "success" if proc.returncode == 0 else "error"
        ctx.record(
            "shell",
            f"cmd={cmd[:100]}",
            outcome,
            int((time.monotonic() - t0) * 1000),
            None if proc.returncode == 0 else f"exit {proc.returncode}",
        )
        return out or f"(exit {proc.returncode}, no output)"
    except subprocess.TimeoutExpired:
        ctx.record("shell", f"cmd={cmd[:100]}", "error", int((time.monotonic() - t0) * 1000), "timeout")
        return "ERROR: command timed out"
    except Exception as e:
        ctx.record("shell", f"cmd={cmd[:100]}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


def tool_python_exec(ctx: ToolContext, code: str, timeout_sec: float = 10.0) -> str:
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["python", "-I", "-c", code],
            cwd=str(ctx.workspace),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > ctx.max_output_chars:
            out = out[: ctx.max_output_chars] + "\n...[truncated]"
        outcome = "success" if proc.returncode == 0 else "error"
        ctx.record(
            "python_exec",
            f"code_len={len(code)}",
            outcome,
            int((time.monotonic() - t0) * 1000),
            None if proc.returncode == 0 else f"exit {proc.returncode}",
        )
        return out or f"(exit {proc.returncode})"
    except subprocess.TimeoutExpired:
        ctx.record("python_exec", "code", "error", int((time.monotonic() - t0) * 1000), "timeout")
        return "ERROR: python timed out"
    except Exception as e:
        ctx.record("python_exec", "code", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


def tool_run_tests(ctx: ToolContext, path: str = "smoke_test.py", timeout_sec: float = 20.0) -> str:
    """Run a local (non-hidden) test file the agent may have written — not the hidden suite."""
    t0 = time.monotonic()
    try:
        p = _safe_path(ctx, path)
        if not p.is_file():
            # Fallback: try importing solution and running a minimal self-check if agent wrote none
            ctx.record("pytest", f"path={path}", "error", int((time.monotonic() - t0) * 1000), "file missing")
            return f"ERROR: test file not found: {path}"
        proc = subprocess.run(
            ["python", "-I", str(p)],
            cwd=str(ctx.workspace),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > ctx.max_output_chars:
            out = out[: ctx.max_output_chars] + "\n...[truncated]"
        outcome = "success" if proc.returncode == 0 else "error"
        ctx.record("pytest", f"path={path}", outcome, int((time.monotonic() - t0) * 1000),
                   None if proc.returncode == 0 else f"exit {proc.returncode}")
        return out or f"(exit {proc.returncode})"
    except Exception as e:
        ctx.record("pytest", f"path={path}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


def tool_lint(ctx: ToolContext, path: str = "solution.py") -> str:
    t0 = time.monotonic()
    try:
        p = _safe_path(ctx, path)
        if not p.is_file():
            ctx.record("lint", f"path={path}", "error", int((time.monotonic() - t0) * 1000), "missing")
            return f"ERROR: missing {path}"
        src = p.read_text(encoding="utf-8", errors="replace")
        # Lightweight lint: syntax + a few style checks (no external flake8 dependency required)
        issues: list[str] = []
        try:
            compile(src, str(p), "exec")
        except SyntaxError as e:
            issues.append(f"SyntaxError: {e.msg} at line {e.lineno}")
        for i, line in enumerate(src.splitlines(), 1):
            if len(line) > 120:
                issues.append(f"L{i}: line longer than 120 chars")
            if "\t" in line:
                issues.append(f"L{i}: tab character (prefer spaces)")
        outcome = "success" if not issues else "error"
        ctx.record("lint", f"path={path}", outcome, int((time.monotonic() - t0) * 1000),
                   None if not issues else f"{len(issues)} issues")
        return "OK: no issues" if not issues else "\n".join(issues[:30])
    except Exception as e:
        ctx.record("lint", f"path={path}", "error", int((time.monotonic() - t0) * 1000), str(e))
        return f"ERROR: {e}"


TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "fs_read": tool_fs_read,
    "fs_write": tool_fs_write,
    "list_dir": tool_list_dir,
    "grep": tool_grep,
    "shell": tool_shell,
    "python_exec": tool_python_exec,
    "pytest": tool_run_tests,
    "lint": tool_lint,
}


def dispatch_tool(ctx: ToolContext, name: str, args: dict[str, Any]) -> str:
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        t0 = time.monotonic()
        ctx.record(name or "unknown", str(args)[:120], "rejected", int((time.monotonic() - t0) * 1000), "unknown tool")
        return f"ERROR: unknown tool '{name}'. Available: {', '.join(sorted(TOOL_REGISTRY))}"
    # Only pass kwargs the tool accepts by name from args
    try:
        return fn(ctx, **{k: v for k, v in args.items() if k in fn.__code__.co_varnames})
    except TypeError:
        # Fallback: call with common patterns
        if name == "fs_write":
            return tool_fs_write(ctx, path=str(args.get("path", "solution.py")), content=str(args.get("content", "")))
        if name == "fs_read":
            return tool_fs_read(ctx, path=str(args.get("path", "solution.py")))
        if name == "shell":
            return tool_shell(ctx, cmd=str(args.get("cmd", args.get("command", "echo"))))
        if name == "python_exec":
            return tool_python_exec(ctx, code=str(args.get("code", "print(1)")))
        if name == "grep":
            return tool_grep(ctx, pattern=str(args.get("pattern", ".")), path=str(args.get("path", ".")))
        if name == "list_dir":
            return tool_list_dir(ctx, path=str(args.get("path", ".")))
        if name == "pytest":
            return tool_run_tests(ctx, path=str(args.get("path", "smoke_test.py")))
        if name == "lint":
            return tool_lint(ctx, path=str(args.get("path", "solution.py")))
        raise
