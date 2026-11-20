"""Optional ADR drift section for the skill-doctor HTML report.

A report.json may carry an ``adr_drift`` object (shape in
``references/report-schema.md``). ``render_adr_drift`` returns "" when it is
absent, so older reports render unchanged. ``validate_adr_drift`` reports every
finding that has an empty ``suggested_fix``. The section never feeds the
scorecard. Escaping is injected (``esc``) so this module shares the renderer's
single escape function.

python3, stdlib only.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from report_audit import Code, Escape, details_html, table_html

GROUPS = ("Numbering", "Links", "History")
ALIGN_LINES = {
    "absent": (
        "align not installed. Deterministic check complete. "
        "Optional cross-check: github.com/aligndottech/align-cli."
    ),
    "detected": "align found. Not run. To cross-check: `{hint}`.",
    "no_graph": (
        "align found, no graph. Not built, because building reads api.github.com "
        "and downloads a model."
    ),
}


def _repos(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    section = report.get("adr_drift")
    repos = section.get("repos") if isinstance(section, dict) else None
    return [r for r in (repos if isinstance(repos, list) else []) if isinstance(r, dict)]


def _findings(repo: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    found = repo.get("findings")
    return [f for f in (found if isinstance(found, list) else []) if isinstance(f, dict)]


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


def _draft_cell(esc: Escape, draft: Any) -> str:
    if not isinstance(draft, str) or not draft:
        return ""
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", draft) or draft.startswith("/") or ".." in draft:
        return esc(draft)
    return f'<a href="{esc(draft)}">{esc(draft)}</a>'


def _finding_table(esc: Escape, repo: Mapping[str, Any]) -> str:
    rows = []
    for finding in _findings(repo):
        rows.append(
            [
                finding.get("group", ""),
                Code(str(finding.get("kind", ""))),
                finding.get("severity", ""),
                finding.get("confidence", ""),
                Code(_where(finding)),
                finding.get("suggested_fix", ""),
            ]
        )
    headers = ["Group", "Kind", "Severity", "Confidence", "Where", "Suggested fix"]
    return table_html(esc, f"ADR drift findings for {repo.get('repo', '')}", headers, rows)


def _counts_line(repo: Mapping[str, Any]) -> str:
    findings = _findings(repo)
    parts = [
        f"{sum(1 for f in findings if f.get('group') == group)} {group.lower()}" for group in GROUPS
    ]
    scope = f"{repo.get('examined', 0)} commits examined"
    if repo.get("truncated"):
        scope += " (history truncated at the commit limit)"
    return f"{len(findings)} findings: " + ", ".join(parts) + f". {scope}."


def _drafts(esc: Escape, repo: Mapping[str, Any]) -> str:
    links = [
        f"<li>{esc(f.get('id', ''))}: {_draft_cell(esc, f.get('draft'))}</li>"
        for f in _findings(repo)
        if f.get("draft")
    ]
    if not links:
        return ""
    return "<h4>Draft ADRs</h4><ul>" + "".join(links) + "</ul>"


def align_block(esc: Escape, align: Any) -> str:
    """The align line, plus advisory text under its own heading when align ran."""
    align = align if isinstance(align, dict) else {"status": "absent"}
    status = str(align.get("status", "absent"))
    hint = str(align.get("command_hint") or "DO_NOT_TRACK=1 align adr")
    if status in ALIGN_LINES:
        return f'<p class="muted">{esc(ALIGN_LINES[status].format(hint=hint))}</p>'
    text = str(align.get("text") or "")
    if status == "ran":
        note = str(align.get("advisory_note") or "advisory")
        return f'<h4>align cross-check</h4><p class="muted">{esc(note)}</p><pre>{esc(text)}</pre>'
    code = align.get("exit_code")
    return f'<p class="muted">{esc(f"align failed (exit {code}): {text}")}</p>'


def render_adr_drift(report: Mapping[str, Any], esc: Escape) -> str:
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
        parts += [_drafts(esc, repo), align_block(esc, repo.get("align"))]
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


def is_adr_only(report: Any) -> bool:
    """An ADR-only report has an adr_drift section and no scorecard."""
    return (
        isinstance(report, dict)
        and "scores" not in report
        and isinstance(report.get("adr_drift"), dict)
    )


def render_adr_page(report: Mapping[str, Any], esc: Escape, css: str, generated_at: str) -> str:
    """The ADR-only page: a title, when it was generated, and the ADR drift section."""
    title = esc(report.get("title", "ADR Drift Report"))
    meta = f'<ul class="meta"><li>Generated {esc(generated_at)}</li></ul>' if generated_at else ""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<style>{css}</style></head><body>
<a class="skip" href="#main">Skip to report</a>
<div class="page">
<header class="page-head"><div class="title-row"><h1>{title}</h1></div>{meta}</header>
<main id="main">
{render_adr_drift(report, esc)}
</main>
</div>
</body></html>"""


def write_adr_only(
    report_path: Path,
    report: Mapping[str, Any],
    esc: Escape,
    css: str,
    format_generated_at: Callable[[Any], str],
) -> int:
    """Write report.html next to report.json for an ADR-only report. Returns the exit code."""
    errors = validate_adr_drift(report)
    if errors:
        for error in errors:
            print(f"error: unsupported claim: {error}", file=sys.stderr)
        return 1
    out_path = report_path.parent / "report.html"
    generated_at = format_generated_at(report.get("generated_at"))
    out_path.write_text(render_adr_page(report, esc, css, generated_at), encoding="utf-8")
    print(f"report: {out_path.absolute().as_uri()}")
    return 0


__all__: Sequence[str] = (
    "render_adr_drift",
    "validate_adr_drift",
    "align_block",
    "is_adr_only",
    "write_adr_only",
)
