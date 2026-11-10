#!/usr/bin/env python3
"""Render a skill-doctor report.json into one shareable HTML report.

Output (next to report.json):
  report.html - summary, findings, candidate skill changes with copyable
                handoff prompts, and collapsible evidence in a single
                self-contained page, with a Share button that draws a
                1200x675 share card at 2x (2400x1350 pixels) client-side and downloads it.

Python 3.10+, stdlib only. Uses system fonts so the page and the exported PNG
render the same everywhere.
"""

import argparse
import base64
import html
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import report_audit
import report_evaluation
import report_script
import report_style

GRADES = [
    (0.97, "A+"),
    (0.93, "A"),
    (0.90, "A-"),
    (0.87, "B+"),
    (0.83, "B"),
    (0.80, "B-"),
    (0.77, "C+"),
    (0.73, "C"),
    (0.70, "C-"),
    (0.60, "D"),
    (0.0, "F"),
]

DIFFS_BUNDLE_PATH = Path(__file__).resolve().parent.parent / "assets" / "pierre-diffs.js"

# Collapsed height of a diff before the "show more" toggle takes over.
DIFF_CLAMP_PX = 320
BROWSER_TIMEOUT_SECONDS = 5


def grade_for(score: float) -> str:
    for threshold, letter in GRADES:
        if score >= threshold:
            return letter
    return "F"


def pct(score: Any) -> int:
    return round(float(score) * 100)


def format_generated_at(value: Any) -> str:
    if not value:
        return ""
    raw = str(value)
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    if re.search(r"[+-]\d{2}$", normalized):
        normalized += ":00"
    try:
        generated_at = datetime.fromisoformat(normalized)
    except ValueError:
        return raw
    suffix = ""
    if generated_at.tzinfo is not None:
        generated_at = generated_at.astimezone(timezone.utc)
        suffix = " UTC"
    time = generated_at.strftime("%I:%M %p").lstrip("0")
    return (
        f"{generated_at.strftime('%B')} {generated_at.day}, {generated_at.year} at {time}{suffix}"
    )


def open_report(report_path: Path) -> bool:
    """Bound the browser controller without forwarding its output to the CLI."""
    command = [
        sys.executable,
        "-I",
        "-X",
        "utf8",
        "-c",
        "import sys, webbrowser; sys.exit(0 if webbrowser.open(sys.argv[1], new=2) else 1)",
        report_path.absolute().as_uri(),
    ]
    try:
        # A file, rather than a pipe, keeps inherited browser handles from
        # holding up pipe draining after the controller times out.
        with tempfile.TemporaryFile(encoding="utf-8", mode="w+") as output:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                encoding="utf-8",
                errors="replace",
                timeout=BROWSER_TIMEOUT_SECONDS,
                check=False,
            )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def esc(v: Any) -> str:
    value = v if v is not None else ""
    return html.escape(str(value))


def render_diff(diff_text: str, proposed_path: str = "") -> str:
    if not diff_text:
        return ""
    encoded = base64.b64encode(diff_text.encode("utf-8")).decode("ascii")
    filename = Path(proposed_path).name if proposed_path else "SKILL.md"
    return (
        '<div class="diff-wrap" data-collapsed="true">'
        f'<div class="diff-view" data-pierre-diff data-diff="{encoded}" '
        f'data-filename="{esc(filename)}">'
        f'<pre class="diff-fallback">{esc(diff_text)}</pre></div>'
        '<button class="button-quiet diff-toggle" type="button" hidden>Show more</button>'
        "</div>"
    )


def embedded_diffs_script() -> str:
    if not DIFFS_BUNDLE_PATH.exists():
        raise RuntimeError(
            f"@pierre/diffs bundle missing: {DIFFS_BUNDLE_PATH}; "
            "restore it from warpdotdev/skill-doctor, which builds the bundle "
            "with `pnpm build:diffs`"
        )
    bundle = DIFFS_BUNDLE_PATH.read_text(encoding="utf-8")
    return re.sub(r"</script", r"<\\/script", bundle, flags=re.IGNORECASE)


SCORE_LABELS = (
    ("efficiency", "Efficiency"),
    ("code_quality", "Code Quality"),
    ("procedure_compliance", "Procedure Compliance"),
    ("verbosity", "Verbosity"),
    ("skill_coverage", "Skill Coverage"),
)

SECTION_NOTE = {
    "skillopt": "Scores an existing skill against a baseline; tooling and new-skill "
    "candidates get a routing note instead.",
    "skillforge": "Routes the gap: reuse a skill, hand it to skillopt, or justify a new one.",
}


def render_sampling(sampling: Any) -> str:
    """Per-harness candidate and sampled counts, and the cap notice when coverage was partial."""
    per_harness = (sampling or {}).get("per_harness") or {}
    if not per_harness:
        return ""
    notice = sampling.get("notice")
    rows = "".join(
        f"<tr><td>{esc(harness)}</td><td>{esc(c.get('scoreable', 0))}</td>"
        f"<td>{esc(c.get('skill_candidates', 0))}</td><td>{esc(c.get('sampled', 0))}</td>"
        f"<td>{pct(c['overall']) if c.get('overall') is not None else '-'}</td></tr>"
        for harness, c in per_harness.items()
    )
    body = (
        (f'<p class="notice">{esc(notice)}</p>' if notice else "")
        + '<p class="muted">Selection is skill-first within each harness, so each row grades '
        "sessions that exercise skills first, not the whole harness.</p>"
        '<div class="table-scroll" role="region" aria-label="Sampling by harness" tabindex="0">'
        "<table><caption>Sampling by harness</caption>"
        '<thead><tr><th scope="col">Harness</th><th scope="col">Scoreable</th>'
        '<th scope="col">Used a skill</th><th scope="col">Sampled</th>'
        f'<th scope="col">Overall</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )
    return report_audit.details_html(esc, "Sampling", body, open_=bool(notice))


def empty_suggestions_text(r: Any) -> str:
    if report_evaluation.evaluation_of(r)["optimization"] != "run":
        return report_evaluation.EMPTY_STATIC_STATEMENT
    return "No candidates remain after the recorded skillopt evaluation."


def _field(label: str, values: Any, css: str = "field") -> str:
    items = [str(v) for v in (values if isinstance(values, (list, tuple)) else [values]) if v]
    if not items:
        return ""
    if len(items) == 1:
        value = f'<p class="field-value">{esc(items[0])}</p>'
    else:
        value = "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"
    return f'<div class="{css}"><p class="field-label">{esc(label)}</p>{value}</div>'


def _group(title: str, *blocks: str) -> str:
    body = "".join(block for block in blocks if block)
    if not body:
        return ""
    return f'<div class="group"><h4 class="group-title">{esc(title)}</h4>{body}</div>'


def render_handoff(kind: str, text: str, prompt_id: str) -> str:
    """One handoff prompt with Copy and Select all controls (Select all is the fallback)."""
    return (
        '<div class="handoff"><div class="handoff-head">'
        f"<h4>{esc(kind)} handoff prompt</h4>"
        '<div class="handoff-actions">'
        '<button class="button-quiet copy-btn" type="button">Copy</button>'
        '<button class="button-quiet select-btn" type="button">Select all</button>'
        '<span class="copy-status" role="status" aria-live="polite"></span></div></div>'
        f'<p class="muted">{esc(SECTION_NOTE[kind])} Nothing runs until you paste it.</p>'
        f'<details><summary>Show prompt text</summary><pre class="prompt" id="{esc(prompt_id)}" '
        f'tabindex="0">{esc(text)}</pre></details></div>'
    )


def render_suggestion(s: Any, index: int = 0) -> str:
    """One candidate card: facts, hypothesis, checks, diff, and copyable handoff prompts."""
    status = report_evaluation.suggestion_status(s)
    measured = s.get("evaluation") if isinstance(s.get("evaluation"), dict) else {}
    unmeasured = status == "unevaluated"
    missing = _field("Missing evidence", report_evaluation.missing_evidence(s), "field missing")
    parts = [
        f'<article class="candidate" aria-labelledby="candidate-{index}">',
        f'<div class="candidate-head"><h3 id="candidate-{index}"><code>{esc(s.get("skill"))}</code></h3>'
        f'<span class="badge" data-status="{esc(status)}">{esc(status)}</span></div>',
        f'<p class="change">{esc(s.get("change"))}</p>',
        '<div class="fields">',
        _field("Target", report_evaluation.target_identity(s)),
        _field("Owner", s.get("owner") or "skill"),
        "</div>",
        _group(
            "What was observed",
            _field("Observed (fact)", s.get("evidence")),
            _field("Reproduction", s.get("reproduction")),
        ),
        _group(
            "What is hypothesized, not yet tested",
            _field("Hypothesis", s.get("mechanism")),
            _field(
                "Expected improvement (unmeasured)" if unmeasured else "Expected improvement",
                s.get("expected_improvement"),
            ),
            _field("Risks and counterexamples", s.get("risks")),
        ),
        _group(
            "How to check it",
            _field("Acceptance checks", s.get("acceptance_checks")),
            missing,
            _field("Baseline evidence", measured.get("baseline")),
            _field("Candidate evidence", measured.get("candidate")),
        ),
        _group("Proposed edit", render_diff(s.get("diff", ""), s.get("proposed_path", ""))),
        render_handoff(
            "skillopt", report_evaluation.skillopt_prompt(s), f"prompt-{index}-skillopt"
        ),
        render_handoff(
            "skillforge", report_evaluation.skillforge_prompt(s), f"prompt-{index}-skillforge"
        ),
        "</article>",
    ]
    return "".join(part for part in parts if part)


def render_header(r: Any, generated_at: str) -> str:
    title = esc(r.get("title", "Agent Skill Report"))
    stats = r.get("stats", {})
    items = [
        f"Generated {esc(generated_at)}" if generated_at else "",
        f"Harness: {esc(r.get('harness', 'codex'))}",
        f"Scope: {esc(stats.get('sessions_scanned', 0))} conversations found in the "
        f"last {esc(stats.get('window_days', 45))} days",
    ]
    meta = "".join(f"<li>{item}</li>" for item in items if item)
    return (
        '<header class="page-head"><div class="title-row">'
        f"<h1>{title}</h1>"
        '<button class="button" id="share-png" type="button" '
        'title="Save a 2400x1350 PNG share card">Share</button></div>'
        f'<ul class="meta">{meta}</ul></header>'
    )


def render_summary(r: Any, grade: str) -> str:
    scores = r["scores"]
    stats = r.get("stats", {})
    bars = "".join(
        f'<li><div class="bar-head"><span class="bar-name">{esc(name)}</span>'
        f'<span class="bar-val">{pct(scores.get(key, 0))}</span></div>'
        f'<div class="bar-track" aria-hidden="true"><div class="bar-fill" '
        f'style="width:{pct(scores.get(key, 0))}%;--metric-delay:{180 + index * 110}ms"></div></div></li>'
        for index, (key, name) in enumerate(SCORE_LABELS)
    )
    stat_cells = "".join(
        f'<li class="stat"><span class="num">{esc(value)}</span><span class="lbl">{esc(label)}</span></li>'
        for value, label in [
            (stats.get("sessions_analyzed", 0), "conversations scored"),
            (stats.get("skills_found", 0), "skills installed"),
            (stats.get("skills_used", 0), "skills used"),
        ]
    )
    return (
        '<section class="summary" aria-labelledby="summary-h"><h2 id="summary-h">Summary</h2>'
        '<div class="scorecard"><div class="grade-col">'
        f'<div class="grade">{esc(grade)}</div>'
        f'<div class="grade-label">Overall {pct(scores["overall"])} / 100</div></div>'
        f'<ul class="bars" aria-label="Scores out of 100">{bars}</ul></div>'
        '<div class="eval-band"><h3>Evaluation status</h3>'
        f'<p class="evaluation" id="evaluation-status">{esc(report_evaluation.evaluation_summary(r))}</p></div>'
        f'<ul class="stats" aria-label="Report totals">{stat_cells}</ul></section>'
    )


def render_findings(r: Any) -> str:
    findings = [f for f in r.get("top_findings", []) if f]
    body = (
        '<ol class="findings">' + "".join(f"<li>{esc(f)}</li>" for f in findings) + "</ol>"
        if findings
        else '<p class="empty">No findings were recorded in this report. That does not mean '
        "the conversations had no problems; it means none were written down.</p>"
    )
    return (
        f'<section aria-labelledby="findings-h"><h2 id="findings-h">Findings</h2>{body}</section>'
    )


def render_candidates(r: Any) -> str:
    suggestions = r.get("suggestions", [])
    cards = "".join(render_suggestion(s, index) for index, s in enumerate(suggestions)) or (
        f'<p class="empty">{esc(empty_suggestions_text(r))}</p>'
    )
    intro = (
        '<p class="muted">Each candidate is a proposed change with the evidence behind it. '
        "Paste a handoff prompt into skillopt to measure the change, or into skillforge to "
        "draft the edit. Skill-doctor does not apply any edit.</p>"
        if suggestions
        else ""
    )
    return (
        '<section aria-labelledby="candidates-h"><h2 id="candidates-h">Suggested skill changes</h2>'
        f"{intro}{cards}</section>"
    )


def render_evidence(r: Any) -> str:
    body = render_sampling(r.get("sampling")) + report_audit.render_audit(r, esc)
    if not body:
        return ""
    return (
        f'<section aria-labelledby="evidence-h"><h2 id="evidence-h">Evidence</h2>{body}</section>'
    )


def card_data_json(r: Any, grade: str) -> str:
    scores = r["scores"]
    stats = r.get("stats", {})
    return json.dumps(
        {
            "title": r.get("title", "Agent Skill Report"),
            "eyebrow": "skill-doctor",
            "handle": r.get("handle") or "agent skill report",
            "harness": r.get("harness", "codex"),
            "grade": grade,
            "grade_label": f"Overall {pct(scores['overall'])} / 100",
            "bars": [[label, pct(scores.get(key, 0))] for key, label in SCORE_LABELS],
            "meta": f"{stats.get('sessions_scanned', 0)} conversations found · "
            f"last {stats.get('window_days', 45)} days",
            "stats": [
                [str(stats.get("sessions_analyzed", 0)), "conversations scored"],
                [str(stats.get("skills_found", 0)), "skills installed"],
                [str(stats.get("skills_used", 0)), "skills used"],
            ],
        }
    )


def render_page(r: Any) -> str:
    scores = r["scores"]
    grade = r.get("grade") or grade_for(scores["overall"])
    generated_at = format_generated_at(r.get("generated_at"))
    title = esc(r.get("title", "Agent Skill Report"))
    css = report_style.PAGE_CSS.replace("__CLAMP__", str(DIFF_CLAMP_PX))
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<style>{css}</style></head><body>
<a class="skip" href="#main">Skip to report</a>
<div class="page">
{render_header(r, generated_at)}
<main id="main">
{render_summary(r, grade)}
{render_findings(r)}
{render_candidates(r)}
{render_evidence(r)}
</main>
</div>
<script>{embedded_diffs_script()}</script>
<script>{page_script(card_data_json(r, grade))}</script>
</body></html>"""


def page_script(card_data: str) -> str:
    return report_script.page_script(card_data, DIFF_CLAMP_PX)


def load_report(report_path: Path) -> dict[str, Any]:
    """Read report.json; exit 2 when unreadable or not JSON, 1 when it has no overall score."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"error: cannot read {report_path}: {exc}", file=sys.stderr)
        sys.exit(2)
    scores = report.get("scores") if isinstance(report, dict) else None
    if not isinstance(scores, dict) or not isinstance(scores.get("overall"), (int, float)):
        print(f"error: {report_path} needs a numeric scores.overall", file=sys.stderr)
        sys.exit(1)
    return report


def parse_args(argv: Any = None) -> Any:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report_path",
        nargs="?",
        default="./skill-doctor-report/report.json",
        help="Path to the report.json file",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the generated report in the default browser",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> None:
    args = parse_args(argv)
    report_path = Path(args.report_path).expanduser()
    r = load_report(report_path)
    r.setdefault("grade", grade_for(r["scores"]["overall"]))
    errors = report_evaluation.validate_report(r) + report_audit.validate_audit(r)
    if errors:
        for error in errors:
            print(f"error: unsupported claim: {error}", file=sys.stderr)
        sys.exit(1)

    out_path = report_path.parent / "report.html"
    out_path.write_text(render_page(r), encoding="utf-8")
    print(f"report: {out_path.absolute().as_uri()}")
    print(f"evaluation: {report_evaluation.evaluation_summary(r)}")
    if args.open_browser:
        if open_report(out_path):
            print("        opened in the default browser")
        else:
            print(
                "warning: could not open the report in the default browser",
                file=sys.stderr,
            )
    print("        use the Share button to save a 2400x1350 PNG")


if __name__ == "__main__":
    main()
