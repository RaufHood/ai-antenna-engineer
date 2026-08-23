"""Load `.env` into the process environment at start-up.

`app/agent/devin.py` reads credentials straight from `os.environ`, which means
they have to be exported by hand in every shell that starts the backend or the
dev driver — easy to forget, and the failure mode (DevinConfigError, or worse,
a silent fall back to the mock agent) does not point at the cause.

Deliberately hand-rolled rather than `python-dotenv`: it is fifteen lines, and
one fewer dependency in a service whose whole job is to be reproducible on
someone else's laptop during a hackathon.

Rules, matching what everyone expects of a .env:
- `KEY=value`, blank lines and `#` comments ignored
- surrounding single or double quotes stripped
- **an existing environment variable always wins**, so
  `DEVIN_MAX_ACU=1 python scripts/dev_run.py` overrides the file
"""
from __future__ import annotations

import os
from pathlib import Path

# backend/.env — the file lives next to pyproject.toml, not at the repo root,
# because these credentials belong to the backend service specifically.
DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_env(path: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Read a .env file into os.environ. Returns what it set (values redacted).

    Missing file is not an error: the mock agent needs no credentials, and CI
    supplies real ones through the environment.
    """
    p = Path(path) if path else DEFAULT_ENV_PATH
    if not p.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key in os.environ and not override:
            continue
        os.environ[key] = value
        loaded[key] = _redact(key, value)
    return loaded


def _redact(key: str, value: str) -> str:
    """Never let a secret reach a log line. Length is enough to debug with."""
    if any(m in key.upper() for m in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
        return f"<set, {len(value)} chars>"
    return value


def describe_agent_config() -> str:
    """One line for start-up logs: what is configured, without leaking it."""
    key = os.environ.get("DEVIN_API_KEY")
    org = os.environ.get("DEVIN_ORG_ID")
    agent = os.environ.get("AGENT", "mock")
    if agent != "devin":
        return f"agent={agent} (no Devin credentials needed)"
    if not key or not org:
        missing = [n for n, v in (("DEVIN_API_KEY", key), ("DEVIN_ORG_ID", org)) if not v]
        return f"agent=devin but {', '.join(missing)} missing — will fail"
    acu = os.environ.get("DEVIN_MAX_ACU", "unset")
    return (f"agent=devin org={org} key=<set, {len(key)} chars> "
            f"max_acu={acu}")
