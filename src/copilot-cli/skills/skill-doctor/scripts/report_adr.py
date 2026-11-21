"""ADR drift section for the skill-doctor HTML report.

A report.json may carry an ``adr_drift`` object (shape in
``references/report-schema.md``). Each repo entry names its ``scan`` file, the
output of ``adr_drift.py scan``, and optionally a ``decisions`` file. The report
reads both by path, so it never depends on findings retyped by the model.
``resolve_adr_drift`` loads them. ``render_adr_drift`` returns "" when the
section is absent, so older reports render unchanged. ``validate_adr_drift``
reports every finding with an empty ``suggested_fix``. The section never feeds
the scorecard. Escaping is injected (``esc``) so this module shares the
renderer's single escape function, and the caller owns the page shell.

python3, stdlib only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from adr_corpus import GROUPS
from report_audit import Code, Escape, details_html, table_html

ADR_ONLY_MODE = "adr_only"
MAX_FILE_BYTES = 5_000_000
DECISION_FIELDS = ("subject", "sha", "pr_url", "reason")


class AdrInputError(Exception):
    """An adr_drift input file is missing, unreadable, outside the report folder, or malformed."""


def is_adr_only(report: Any) -> bool:
    """An ADR-only report carries the explicit marker `"mode": "adr_only"`."""
    return isinstance(report, dict) and report.get("mode") == ADR_ONLY_MODE


def _read_json(base: Path, name: Any, label: str) -> Any:
    """Read one JSON file named relative to BASE. It must resolve inside BASE."""
    if not isinstance(name, str) or not name.strip():
        raise AdrInputError(f"{label} must be a path string")
    root = base.resolve()
    path = (root / name).resolve()
    if root != path and root not in path.parents:
        raise AdrInputError(f"{label} {name} is outside the report directory")
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise AdrInputError(f"{label} {name} is larger than {MAX_FILE_BYTES} bytes")
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise AdrInputError(f"cannot read {label} {name}: {exc}") from exc


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in (value if isinstance(value, list) else []) if isinstance(item, dict)]


def _load_decisions(base: Path, name: Any) -> list[dict[str, str]]:
    data = _read_json(base, name, "adr_drift decisions")
    items = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise AdrInputError(f"adr_drift decisions {name} holds no candidate list")
    candidates = []
    for item in _dicts(items):
        row = {field: str(item.get(field) or "") for field in DECISION_FIELDS}
        row["pr_url"] = row["pr_url"] or str(item.get("url") or "")
        candidates.append(row)
    return candidates


def _load_repo(base: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    name = entry.get("scan")
    scan = _read_json(base, name, "adr_drift scan")
    if not isinstance(scan, dict) or not isinstance(scan.get("findings"), list):
        raise AdrInputError(f"adr_drift scan {name} holds no findings list")
    repo: dict[str, Any] = {
        "repo": entry.get("repo") or scan.get("repo") or "",
        "head": scan.get("head"),
        "examined": scan.get("examined") or 0,
        "truncated": bool(scan.get("truncated")),
        "findings": _dicts(scan["findings"]),
        "read_errors": _dicts(scan.get("read_errors")),
    }
    if entry.get("decisions") is not None:
        repo["decisions"] = _load_decisions(base, entry["decisions"])
    return repo


def resolve_adr_drift(report: Mapping[str, Any], base: Path) -> dict[str, Any]:
    """Return REPORT with each repo's scan and decisions files loaded. Raises AdrInputError."""
    section = report.get("adr_drift")
    if not isinstance(section, dict):
        return dict(report)
    resolved = {key: value for key, value in section.items() if key != "repos"}
    if not section.get("skipped"):
        entries = _dicts(section.get("repos"))
        if not entries:
            raise AdrInputError("adr_drift has neither `skipped` nor a repos entry")
        resolved["repos"] = [_load_repo(base, entry) for entry in entries]
    return {**report, "adr_drift": resolved}


def _repos(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    section = report.get("adr_drift")
    return _dicts(section.get("repos")) if isinstance(section, dict) else []


def _findings(repo: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _dicts(repo.get("findings"))


def validate_adr_drift(report: Mapping[str, Any]) -> list[str]:
    """One error per finding whose `suggested_fix` is missing or blank."""
    errors = []
    for repo in _repos(report):
        for finding in _findings(repo):
            fix = finding.get("suggested_fix")
            if not isinstance(fix, str) or not fix.strip():
                errors.append(
                    f"adr_drift finding {finding.get('id', '?')} ({finding.get('kind', '?')}) "
                    "has an empty suggested_fix"
                )
    return errors


def _where(finding: Mapping[str, Any]) -> str:
    evidence = finding.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    if evidence.get("path"):
        line = evidence.get("line")
        return f"{evidence['path']}:{line}" if line else str(evidence["path"])
    if evidence.get("sha"):
        subject = str(evidence.get("subject") or "")
        return f"{str(evidence['sha'])[:10]} {subject}".strip()
    return ""


def _finding_table(esc: Escape, repo: Mapping[str, Any]) -> str:
    rows = [
        [
            finding.get("group", ""),
            Code(str(finding.get("kind", ""))),
            finding.get("severity", ""),
            finding.get("confidence", ""),
            Code(_where(finding)),
            finding.get("suggested_fix", ""),
        ]
        for finding in _findings(repo)
    ]
    headers = ["Group", "Kind", "Severity", "Confidence", "Where", "Suggested fix"]
    return table_html(esc, f"ADR drift findings for {repo.get('repo', '')}", headers, rows)


def _decision_table(esc: Escape, repo: Mapping[str, Any]) -> str:
    rows = [
        [row["subject"], Code(row["sha"][:10]), row["pr_url"], row["reason"]]
        for row in _dicts(repo.get("decisions"))
    ]
    if not rows:
        return ""
    headers = ["Subject", "Commit", "PR", "Reason"]
    title = f"Candidate undocumented decisions for {repo.get('repo', '')}"
    return table_html(esc, title, headers, rows)


def _read_error_list(esc: Escape, repo: Mapping[str, Any]) -> str:
    errors = _dicts(repo.get("read_errors"))
    if not errors:
        return ""
    items = "".join(f"<li>{esc(e.get('path', ''))}: {esc(e.get('error', ''))}</li>" for e in errors)
    return f'<p class="muted">Unreadable paths, not checked:</p><ul>{items}</ul>'


def _counts_line(repo: Mapping[str, Any]) -> str:
    findings = _findings(repo)
    parts = [
        f"{sum(1 for f in findings if f.get('group') == group)} {group.lower()}" for group in GROUPS
    ]
    scope = f"{repo.get('examined', 0)} commits examined"
    if repo.get("truncated"):
        scope += " (history truncated at the commit limit)"
    return f"{len(findings)} findings: " + ", ".join(parts) + f". {scope}."


def render_adr_drift(report: Mapping[str, Any], esc: Escape) -> str:
    """The ADR drift section as HTML, or "" when the report has none."""
    section = report.get("adr_drift")
    if not isinstance(section, dict):
        return ""
    skipped = section.get("skipped")
    if skipped:
        body = f'<p class="empty">{esc(f"ADR drift was not run: {skipped}")}</p>'
        return _wrap(body, esc)
    blocks = []
    for repo in _repos(report):
        parts = [f"<h3>{esc(repo.get('repo', ''))}</h3>", f"<p>{esc(_counts_line(repo))}</p>"]
        if _findings(repo):
            parts.append(_finding_table(esc, repo))
        parts += [_decision_table(esc, repo), _read_error_list(esc, repo)]
        blocks.append("".join(parts))
    return _wrap("".join(blocks), esc)


def _wrap(body: str, esc: Escape) -> str:
    intro = (
        '<p class="muted">Findings from numbering, link, supersession, and git-history checks. '
        "History findings are candidates, not verdicts. This section does not change the grade.</p>"
    )
    return (
        '<section aria-labelledby="adr-drift-h"><h2 id="adr-drift-h">ADR drift</h2>'
        + intro
        + details_html(esc, "ADR drift evidence", body, open_=True)
        + "</section>"
    )


__all__ = (
    "AdrInputError",
    "is_adr_only",
    "render_adr_drift",
    "resolve_adr_drift",
    "validate_adr_drift",
)
