"""Cache population guard for the agent-review composite action."""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

_AGENT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
NON_CACHEABLE_VERDICTS = frozenset({"NEEDS_REVIEW"})


def _atomic_write_text(path: str | os.PathLike[str], text: str) -> None:
    """Write ``text`` to ``path`` atomically via a temp file plus ``os.replace``.

    Writes to a temp file in the same directory, then ``os.replace`` swaps it
    into place, so a crash or two concurrent writers cannot leave the file
    half-written or truncated. On failure the partial temp file is removed and
    the ``OSError`` re-raised for the caller to handle.
    """
    directory = os.path.dirname(os.fspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_repo_root(start: Path | None = None) -> Path:
    """Return the repository root by walking up from this module.

    Anchors the default cache path to a stable base (the first ancestor that
    contains ``.git`` or ``.claude``) instead of the process working
    directory. A CWD-relative default is a path-traversal surface (CWE-22):
    the cache then lands wherever the caller happens to run from. Falls back
    to this module's own directory when no marker is found, never CWD.
    """
    here = (start or Path(__file__)).resolve()
    start_dir = here if here.is_dir() else here.parent
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / ".git").exists() or (candidate / ".claude").exists():
            return candidate
    return start_dir


class CacheGuardConfigError(ValueError):
    """Raised when the cache guard receives invalid configuration."""


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
    cache_root: Path | None = None,
) -> bool:
    """Populate the review cache only when the verdict is structurally valid.

    ``cache_root`` defaults to ``<repo_root>/ai-review-cache`` (anchored to
    this module, not the process CWD) so the cache lands in a stable location
    regardless of the working directory the action step runs from (CWE-22).
    """
    safe_agent = validate_agent_name(agent)

    if cache_root is None:
        cache_root = get_repo_root() / "ai-review-cache"

    reason = skip_cache_reason(verdict, infra_failure)
    if reason is not None:
        append_github_output(github_output, "cache_populated", "false")
        print(f"Skipping cache save: {reason}")
        return False

    cache_dir = cache_root / safe_agent
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        _atomic_write_text(cache_dir / "verdict.txt", verdict)
        _atomic_write_text(cache_dir / "findings.txt", findings)
        _atomic_write_text(
            cache_dir / "infrastructure-failure.txt", infra_failure or "false"
        )
    except OSError as exc:
        # A crash mid-sequence must not leave a partial cache dir that a later
        # read treats as a populated hit. Remove what landed and report
        # not-populated so the caller re-runs the review instead of trusting it.
        shutil.rmtree(cache_dir, ignore_errors=True)
        append_github_output(github_output, "cache_populated", "false")
        print(f"Failed to populate cache for {safe_agent}: {exc}", file=sys.stderr)
        return False
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
