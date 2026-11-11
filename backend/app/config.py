from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no extra dependency).

    * Non-empty real environment variables win over the file.
    * An *empty* environment variable (e.g. ``BIFROST_API_KEY=`` left over in the
      shell) is treated as unset, so it can no longer hide the value in ``.env``.
    * Tolerates a UTF-8 BOM, ``export KEY=value``, spaces around ``=``, quotes and
      trailing ``# comments`` on unquoted values.
    * If a key appears several times, the last non-empty value wins.
    """
    if not path.exists():
        return
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if v[:1] in ("'", '"') and v.find(v[0], 1) > 0:
            v = v[1 : v.find(v[0], 1)]
        elif " #" in v:
            v = v.split(" #", 1)[0].rstrip()
        if v:
            values[k] = v
    for k, v in values.items():
        if not os.environ.get(k):
            os.environ[k] = v


@dataclass
class Settings:
    mode: str = "auto"
    db_path: str = str(BACKEND_DIR / "bifrost.db")
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    # Maxim AI Bifrost gateway (OpenAI-compatible)
    bifrost_gateway_url: str = "http://127.0.0.1:8081"
    bifrost_api_key: str = ""  # optional virtual key (sk-bf-...) or dummy; keys live in Bifrost
    bifrost_enabled: bool = True
    bifrost_timeout_sec: float = 120.0
    # Total budget for one gateway probe. Kept short so a health check can never
    # hang on an unreachable gateway.
    gateway_probe_timeout_sec: float = 4.0
    # How long /health may reuse a previously probed gateway status.
    gateway_cache_ttl_sec: float = 15.0
    docker_image: str = "bifrost/sandbox:py3.11-slim"
    sandbox_memory_mb: int = 256
    require_docker: bool = True  # live untrusted code: fail closed without Docker
    allow_host_sandbox: bool = False  # explicit dev-only subprocess grading
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"])
    max_parallel_runs: int = 2
    sim_delay_ms: int = 30
    seed_demo: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(BACKEND_DIR / ".env")
        e = os.environ
        return cls(
            mode=e.get("BIFROST_MODE", "auto").lower(),
            db_path=e.get("BIFROST_DB", str(BACKEND_DIR / "bifrost.db")),
            gemini_api_key=e.get("GEMINI_API_KEY", ""),
            openrouter_api_key=e.get("OPENROUTER_API_KEY", ""),
            bifrost_gateway_url=e.get("BIFROST_GATEWAY_URL", "http://127.0.0.1:8081").rstrip("/"),
            bifrost_api_key=e.get("BIFROST_API_KEY", e.get("BIFROST_VIRTUAL_KEY", "")),
            bifrost_enabled=e.get("BIFROST_ENABLED", "1") in ("1", "true", "yes"),
            bifrost_timeout_sec=float(e.get("BIFROST_TIMEOUT_SEC", "120")),
            gateway_probe_timeout_sec=float(e.get("BIFROST_GATEWAY_PROBE_TIMEOUT_SEC", "4")),
            gateway_cache_ttl_sec=float(e.get("BIFROST_GATEWAY_CACHE_TTL_SEC", "15")),
            docker_image=e.get("BIFROST_DOCKER_IMAGE", "bifrost/sandbox:py3.11-slim"),
            sandbox_memory_mb=int(e.get("BIFROST_SANDBOX_MEMORY_MB", "256")),
            require_docker=e.get("BIFROST_REQUIRE_DOCKER", "1") in ("1", "true", "yes"),
            allow_host_sandbox=e.get("BIFROST_ALLOW_HOST_SANDBOX", "0") in ("1", "true", "yes"),
            cors_origins=[o.strip() for o in e.get("BIFROST_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173").split(",") if o.strip()],
            max_parallel_runs=int(e.get("BIFROST_MAX_PARALLEL_RUNS", "2")),
            sim_delay_ms=int(e.get("BIFROST_SIM_DELAY_MS", "30")),
            seed_demo=e.get("BIFROST_SEED_DEMO", "0") in ("1", "true", "yes"),
        )

    def provider_key(self, provider: str) -> str:
        """Legacy direct-provider keys (only used if Bifrost is disabled — not the normal path)."""
        p = provider.strip().lower()
        if p in ("google ai", "google", "gemini"):
            return self.gemini_api_key
        if p == "openrouter":
            return self.openrouter_api_key
        return ""

    @property
    def bifrost_chat_url(self) -> str:
        base = self.bifrost_gateway_url.rstrip("/")
        # Prefer unified OpenAI-compatible path used by Bifrost
        return f"{base}/v1/chat/completions"
