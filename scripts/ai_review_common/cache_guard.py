"""Cache population guard for the agent-review composite action."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_AGENT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
NON_CACHEABLE_VERDICTS = frozenset({"NEEDS_REVIEW"})

_REPO_MARKERS = (".git", ".claude")


class CacheGuardConfigError(ValueError):
    """Raised when the cache guard receives invalid configuration."""


def get_repo_root() -> Path:
    """Return the repo root by walking up from this file to a `.git` or `.claude` marker.

    Anchoring defaults to the repo root (rather than CWD) keeps script
    behavior stable regardless of where the process is launched from and
    avoids CWE-22 path-traversal surface introduced by CWD-relative defaults.
    """
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if any((parent / marker).exists() for marker in _REPO_MARKERS):
            return parent
    # Fallback: two levels up (scripts/ai_review_common/ -> repo root).
    return here.parents[2]


_DEFAULT_CACHE_ROOT = get_repo_root() / "ai-review-cache"


def validate_agent_name(agent: str) -> str:
    """Return a safe agent name or raise for invalid path input."""
    if not _AGENT_PATTERN.fullmatch(agent):
        raise CacheGuardConfigError(
            f"Invalid agent name: {agent}. Must match '^[a-zA-Z0-9_-]+$'."
        )
    return agent


def skip_cache_reason(verdict: str, infra_failure: str) -> str | None:
    """Return a skip reason when review output must not be cached."""
    if infra_failure == "true":
        return "infrastructure failure"
    if not verdict:
        return "empty verdict (truncated or malformed AI output)"
    if verdict in NON_CACHEABLE_VERDICTS:
        return "verdict is NEEDS_REVIEW (malformed AI output)"
    return None


def append_github_output(output_path: Path, key: str, value: str) -> None:
    """Append one GitHub Actions output value."""
    with output_path.open("a", encoding="utf-8") as output_file:
        output_file.write(f"{key}={value}\n")


def populate_cache(
    *,
    agent: str,
    verdict: str,
    findings: str,
    infra_failure: str,
    github_output: Path,
    cache_root: Path = _DEFAULT_CACHE_ROOT,
) -> bool:
    """Populate the review cache only when the verdict is structurally valid."""
    safe_agent = validate_agent_name(agent)

    reason = skip_cache_reason(verdict, infra_failure)
    if reason is not None:
        append_github_output(github_output, "cache_populated", "false")
        print(f"Skipping cache save: {reason}")
        return False

    cache_dir = cache_root / safe_agent
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "verdict.txt").write_text(verdict, encoding="utf-8")
    (cache_dir / "findings.txt").write_text(findings, encoding="utf-8")
    (cache_dir / "infrastructure-failure.txt").write_text(
        infra_failure or "false",
        encoding="utf-8",
    )
    append_github_output(github_output, "cache_populated", "true")
    print(f"Populated cache directory for {safe_agent}")
    return True


def main() -> int:
    """Run from GitHub Actions."""
    github_output = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not github_output:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return 2

    try:
        populate_cache(
            agent=os.environ.get("AGENT", ""),
            verdict=os.environ.get("VERDICT", ""),
            findings=os.environ.get("FINDINGS", ""),
            infra_failure=os.environ.get("INFRA_FAILURE", ""),
            github_output=Path(github_output),
        )
    except CacheGuardConfigError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"::error::Failed to populate review cache: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
