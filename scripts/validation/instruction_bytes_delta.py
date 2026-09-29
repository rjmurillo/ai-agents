"""Base/head delta for the instruction-context byte report (issue #5400).

``materialize_base`` reads a git revision without checking it out: it streams
``git archive`` into a caller-owned directory and keeps only ``.md`` and
``.tmpl`` members, the only file types the measurement reads. ``compute_delta``
is pure over two report dicts so it can be tested without git.
"""

from __future__ import annotations

import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import IO, Any, cast

__all__ = [
    "DEFAULT_GROWTH_THRESHOLD_BYTES",
    "GitError",
    "compute_delta",
    "materialize_base",
    "resolve_ref",
]

DEFAULT_GROWTH_THRESHOLD_BYTES = 2_000
_MEASURED_SUFFIXES = (".md", ".tmpl")
_GIT_TIMEOUT_SECONDS = 120


class GitError(RuntimeError):
    """A git command failed (ADR-035 exit code 3)."""


def resolve_ref(repo_root: Path, ref: str) -> str:
    """Resolve ``ref`` to a commit SHA. A leading dash is refused (CWE-88)."""
    if ref.startswith("-") or not ref.strip():
        raise GitError(f"refusing base ref {ref!r}")
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise GitError(f"base ref {ref!r} does not resolve to a commit")
    return result.stdout.strip()


def materialize_base(repo_root: Path, sha: str, dest: Path) -> None:
    """Extract the Markdown and template files of commit ``sha`` into ``dest``.

    The tar streams from ``git archive`` so the whole revision is never held in
    memory or written to disk; only the measured file types are extracted.
    """
    with tempfile.TemporaryFile() as stderr_file:
        proc = subprocess.Popen(
            ["git", "-C", str(repo_root), "archive", "--format=tar", sha],
            stdout=subprocess.PIPE,
            stderr=stderr_file,
        )
        stream = cast("IO[bytes]", proc.stdout)  # PIPE was requested above
        try:
            _extract_measured(stream, dest)
        except tarfile.TarError as exc:
            proc.kill()
            proc.wait()
            raise GitError(f"git archive {sha} produced no readable tar: {exc}") from exc
        finally:
            stream.close()
        if proc.wait(timeout=_GIT_TIMEOUT_SECONDS) != 0:
            stderr_file.seek(0)
            message = stderr_file.read().decode("utf-8", errors="replace").strip()
            raise GitError(f"git archive {sha} failed: {message}")


def _extract_measured(stream: IO[bytes], dest: Path) -> None:
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            if member.isfile() and member.name.endswith(_MEASURED_SUFFIXES):
                archive.extract(member, dest, filter="data")


def _scalar_metrics(report: dict[str, Any]) -> dict[str, int]:
    """Flatten the report to the named byte and token totals a delta compares."""
    metrics: dict[str, int] = {}
    for section in ("canonical", "generated"):
        for unit in ("bytes", "tokens"):
            metrics[f"{section}.total.{unit}"] = report[section]["total"][unit]
    for harness, data in report["always_on"].items():
        metrics[f"always_on.{harness}.bytes"] = data["bytes"]
        metrics[f"always_on.{harness}.tokens"] = data["tokens"]
    for fid, data in report["fixtures"].items():
        if "error" in data:
            continue
        metrics[f"fixtures.{fid}.bytes"] = data["bytes"]
        metrics[f"fixtures.{fid}.tokens"] = data["tokens"]
    return metrics


def _changed_paths(base: dict[str, int], head: dict[str, int], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "path": p,
            "base": base.get(p, 0),
            "head": head.get(p, 0),
            "delta": head.get(p, 0) - base.get(p, 0),
        }
        for p in sorted(set(base) | set(head))
        if base.get(p) != head.get(p)
    ]
    rows.sort(key=lambda r: (-abs(r["delta"]), r["path"]))
    return rows[:limit]


def _is_gated(name: str) -> bool:
    """Material growth is judged on always-on and per-fixture bytes only."""
    return name.endswith(".bytes") and name.startswith(("always_on.", "fixtures."))


def compute_delta(
    base: dict[str, Any],
    head: dict[str, Any],
    threshold_bytes: int = DEFAULT_GROWTH_THRESHOLD_BYTES,
    limit: int = 10,
) -> dict[str, Any]:
    """Compare two reports. A metric missing on either side is skipped, not zeroed."""
    base_metrics, head_metrics = _scalar_metrics(base), _scalar_metrics(head)
    metrics: list[dict[str, Any]] = [
        {
            "name": n,
            "base": base_metrics[n],
            "head": head_metrics[n],
            "delta": head_metrics[n] - base_metrics[n],
        }
        for n in sorted(head_metrics)
        if n in base_metrics
    ]
    return {
        "threshold_bytes": threshold_bytes,
        "metrics": metrics,
        "material_growth": [
            m["name"] for m in metrics if _is_gated(m["name"]) and m["delta"] > threshold_bytes
        ],
        "changed_paths": _changed_paths(
            base["canonical"]["paths"], head["canonical"]["paths"], limit
        ),
        "unmeasured_at_base": sorted(n for n in head_metrics if n not in base_metrics),
    }
