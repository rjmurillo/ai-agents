"""The investigate tool loop for the inline-vs-referenced diff A/B harness (#5856).

Evaluation harness support module only. Not wired to any hook. Split out of
``scripts/metrics/sg_reference_ab.py`` (by way of ``sg_reference_ab_api.py``,
itself over the taste-lints file-size gate) into its own module: the
tool-confined filesystem handlers a reviewed fixture exposes to the model,
the tool definitions/dispatch, per-turn usage accounting, and the loop that
drives them against ``sg_reference_ab_api.post_messages`` until the model
calls ``report_findings`` or the turn budget runs out.

Canonical source cited per ``.claude/rules/canonical-source-mirror.md``:
usage field names (``input_tokens``, ``output_tokens``,
``cache_read_input_tokens``, ``cache_creation_input_tokens``) mirror
``_record_usage`` at ``<plugin>/hooks/_base.py:147-177``, verified by reading
that function in the session that first wrote this harness. Verbatim
excerpt::

    i = int(u.get("input_tokens") or 0)
    o = int(u.get("output_tokens") or 0)
    cr = int(u.get("cache_read_input_tokens") or 0)
    cw = int(u.get("cache_creation_input_tokens") or 0)
"""

from __future__ import annotations

import http.client
import os
import re
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.metrics import sg_diff_artifact as sgda
from scripts.metrics import sg_diff_producer as sgdp
from scripts.metrics.sg_reference_ab_api import classify_failure, post_messages

MAX_TURNS = 12


# ---------------------------------------------------------------------------
# Tool-confined filesystem access (CWE-22: reject absolute paths and '..')
# ---------------------------------------------------------------------------


def _confine_path(fixture_dir: Path, raw_path: str) -> Path | None:
    if not raw_path or os.path.isabs(raw_path) or ".." in Path(raw_path).parts:
        return None
    resolved_root = fixture_dir.resolve()
    candidate = (resolved_root / raw_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate


def _tool_read_file(fixture_dir: Path, raw_path: str) -> str:
    target = _confine_path(fixture_dir, raw_path)
    if target is None:
        return "Error: path rejected (must be relative, within the repository, no '..')."
    if not target.is_file():
        return f"Error: {raw_path} is not a file."
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Error reading {raw_path}: {exc}"


def _confine_walked_candidate(resolved_root: Path, candidate: Path) -> Path | None:
    """Reject a ``rglob``-discovered ``candidate`` whose resolved (symlink-
    followed) target escapes ``resolved_root``.

    ``_confine_path`` validates a single caller-supplied relative path
    string against traversal and an escaping symlink; it never sees the
    files ``Path.rglob`` discovers by walking the tree, so a *file* symlink
    sitting inside the fixture (unlike the symlink ``_confine_path`` itself
    rejects) previously reached ``candidate.read_text()`` unchecked and
    ``grep`` returned its target's lines. Mirrors ``_confine_path``'s guard:
    resolve, then require ``relative_to(resolved_root)``.
    """
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved_candidate


def _grep_file_matches(resolved_root: Path, candidate: Path, regex: re.Pattern[str]) -> list[str]:
    """Matched ``"rel:lineno:line"`` strings for one ``rglob``-discovered
    ``candidate``, or ``[]`` when it is not a regular file, escapes
    ``resolved_root`` via a symlink (see ``_confine_walked_candidate``), or
    cannot be read.
    """
    if not candidate.is_file():
        return []
    confined_candidate = _confine_walked_candidate(resolved_root, candidate)
    if confined_candidate is None:
        return []
    try:
        text = confined_candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rel = candidate.relative_to(resolved_root)
    return [
        f"{rel}:{lineno}:{line}"
        for lineno, line in enumerate(text.splitlines(), start=1)
        if regex.search(line)
    ]


def _tool_grep(fixture_dir: Path, pattern: str, raw_path: str | None) -> str:
    if not pattern:
        return "Error: pattern is required."
    resolved_root = fixture_dir.resolve()
    search_root = resolved_root
    if raw_path:
        confined = _confine_path(fixture_dir, raw_path)
        if confined is None:
            return "Error: path rejected (must be relative, within the repository, no '..')."
        search_root = confined
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"Error: invalid pattern: {exc}"
    candidates = [search_root] if search_root.is_file() else sorted(search_root.rglob("*"))
    matches: list[str] = []
    for candidate in candidates:
        matches.extend(_grep_file_matches(resolved_root, candidate, regex))
    return "\n".join(matches[:200]) if matches else "No matches."


# ---------------------------------------------------------------------------
# Tool definitions and dispatch
# ---------------------------------------------------------------------------


def _tool_definitions(
    *, include_read_diff_artifact: bool, findings_schema: dict[str, Any]
) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {
            "name": "read_file",
            "description": "Read a file's contents, confined to the reviewed repository.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "grep",
            "description": "Search file contents for a regex pattern, confined to the "
            "reviewed repository.",
            "input_schema": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    ]
    if include_read_diff_artifact:
        tools.append(
            {
                "name": "read_diff_artifact",
                "description": "Fetch the exact capped diff text referenced by sha256.",
                "input_schema": {
                    "type": "object",
                    "properties": {"sha256": {"type": "string"}},
                    "required": ["sha256"],
                },
            }
        )
    tools.append(
        {
            "name": "report_findings",
            "description": "Report your final security findings and end the review.",
            "input_schema": findings_schema,
        }
    )
    return tools


def _execute_tool(
    tool_use: dict[str, Any],
    *,
    fixture_dir: Path,
    store_dir: Path,
    ref: sgda.ArtifactRef | None,
    expected_repo_id: str,
    expected_head: str,
    inline_diff_text: str,
) -> tuple[str, bool]:
    name = tool_use.get("name")
    args = tool_use.get("input") or {}
    if name == "read_file":
        return _tool_read_file(fixture_dir, str(args.get("path", ""))), False
    if name == "grep":
        raw_path = args.get("path")
        return _tool_grep(fixture_dir, str(args.get("pattern", "")), raw_path), False
    if name == "read_diff_artifact":
        if ref is None:
            return "read_diff_artifact is not available in inline mode.", False
        text = sgdp.serve_artifact_tool(
            store_dir, ref, expected_repo_id, expected_head, inline_diff_text
        )
        return text, True
    return f"Unknown tool: {name}", False


# ---------------------------------------------------------------------------
# Usage accounting and the investigate tool loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsageTotals:
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage: dict[str, Any]) -> UsageTotals:
        return UsageTotals(
            input_tokens=self.input_tokens + int(usage.get("input_tokens") or 0),
            cache_creation_tokens=self.cache_creation_tokens
            + int(usage.get("cache_creation_input_tokens") or 0),
            cache_read_tokens=self.cache_read_tokens
            + int(usage.get("cache_read_input_tokens") or 0),
            output_tokens=self.output_tokens + int(usage.get("output_tokens") or 0),
        )

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    findings: list[dict[str, Any]]
    turns: int
    read_diff_artifact_called: bool
    usage: UsageTotals
    failure: str | None = None
    failure_detail: str | None = None
    infra_failure: bool = False


def _handle_tool_uses(
    tool_uses: list[dict[str, Any]],
    *,
    fixture_dir: Path,
    store_dir: Path,
    ref: sgda.ArtifactRef | None,
    expected_repo_id: str,
    expected_head: str,
    inline_diff_text: str,
) -> tuple[list[dict[str, Any]], bool]:
    results: list[dict[str, Any]] = []
    called_artifact = False
    for tool_use in tool_uses:
        text, this_called = _execute_tool(
            tool_use,
            fixture_dir=fixture_dir,
            store_dir=store_dir,
            ref=ref,
            expected_repo_id=expected_repo_id,
            expected_head=expected_head,
            inline_diff_text=inline_diff_text,
        )
        called_artifact = called_artifact or this_called
        results.append(
            {"type": "tool_result", "tool_use_id": tool_use.get("id"), "content": text}
        )
    return results, called_artifact


def run_investigate_loop(
    *,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    fixture_dir: Path,
    store_dir: Path,
    ref: sgda.ArtifactRef | None,
    expected_repo_id: str,
    expected_head: str,
    inline_diff_text: str,
    findings_schema: dict[str, Any],
) -> ToolLoopResult:
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    usage = UsageTotals()
    read_diff_artifact_called = False
    tools = _tool_definitions(
        include_read_diff_artifact=ref is not None, findings_schema=findings_schema
    )

    for turn in range(1, MAX_TURNS + 1):
        try:
            response = post_messages(api_key, model, system, messages, tools)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            http.client.HTTPException,
            ValueError,
            TypeError,
            OSError,
        ) as exc:
            # OSError also catches TimeoutError and ConnectionError, both of
            # which are OSError subclasses (Python's OS-exception hierarchy):
            # a socket timeout or a reset connection during response.read()
            # raises through post_messages the same as a connection-setup
            # failure urlopen() itself would raise. http.client.HTTPException
            # (e.g. IncompleteRead) and ValueError (json.loads on a non-JSON
            # 200 body, or dict() on a non-object JSON value) are the two
            # post-connection failure modes _send_once can raise that a bare
            # urllib.error catch never saw, so a single malformed response
            # used to abort run_all for every fixture/mode/run still queued,
            # discarding every already-completed row. classify_failure's
            # generic `error_{type(exc).__name__}` branch already handles
            # every one of these; only this except clause was too narrow to
            # reach it.
            classification = classify_failure(exc)
            return ToolLoopResult(
                findings=[],
                turns=turn,
                read_diff_artifact_called=read_diff_artifact_called,
                usage=usage,
                failure=classification.failure,
                failure_detail=classification.failure_detail,
                infra_failure=classification.infra_failure,
            )

        usage = usage.add(response.get("usage") or {})
        content = response.get("content") or []
        messages.append({"role": "assistant", "content": content})

        tool_uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        report = next((b for b in tool_uses if b.get("name") == "report_findings"), None)
        if report is not None:
            findings = (report.get("input") or {}).get("findings") or []
            return ToolLoopResult(
                findings=list(findings),
                turns=turn,
                read_diff_artifact_called=read_diff_artifact_called,
                usage=usage,
            )
        if not tool_uses:
            return ToolLoopResult(
                findings=[],
                turns=turn,
                read_diff_artifact_called=read_diff_artifact_called,
                usage=usage,
                failure="model_stopped_without_report",
            )

        results, called_artifact = _handle_tool_uses(
            tool_uses,
            fixture_dir=fixture_dir,
            store_dir=store_dir,
            ref=ref,
            expected_repo_id=expected_repo_id,
            expected_head=expected_head,
            inline_diff_text=inline_diff_text,
        )
        read_diff_artifact_called = read_diff_artifact_called or called_artifact
        messages.append({"role": "user", "content": results})

    return ToolLoopResult(
        findings=[],
        turns=MAX_TURNS,
        read_diff_artifact_called=read_diff_artifact_called,
        usage=usage,
        failure="max_turns_exceeded",
    )
