"""Finding parser, match rule, and leak check for the code-review catch-rate harness (issue #7149).

Pure functions, no I/O and no model calls. A reviewer answer is a list of
`FINDING:` lines. The match rule is deterministic: no model judges another model.

Match rule (pinned in evals/code-review-catch-rate/README.md):
    caught      a finding among the first TOP_N names the same file as the
                defect and the same defect class.
    near miss   a finding among the first TOP_N names the same file with
                another class. It is not a catch. It is reported so the owner
                can see how much of the miss is class labelling.
    miss        anything else, including an answer with no findings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOP_N = 5

DEFECT_CLASSES: tuple[str, ...] = (
    "logic-error",
    "edge-case",
    "error-handling",
    "security",
    "concurrency",
    "api-contract",
    "test-defect",
    "config-wiring",
    "resource-handling",
)

# FINDING: <path>:<line> | logic-error | One sentence naming the defect.
_FINDING = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?FINDING(?:\*\*)?\s*:\s*"
    r"(?P<location>[^|]+?)\s*\|\s*(?P<klass>[A-Za-z][A-Za-z -]*?)\s*\|\s*(?P<text>.+?)\s*$",
    re.IGNORECASE,
)
_LINE_SUFFIX = re.compile(r":(?:\d+(?:-\d+)?|\?|-)$")
_HEX_RUN = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{7,40}(?![0-9a-zA-Z])")
_MIN_PATH_LEN = 3
_LEAK_LINE_MIN = 40


@dataclass(frozen=True)
class Finding:
    path: str
    klass: str
    text: str


@dataclass(frozen=True)
class Score:
    """Outcome of one review of one corpus entry."""

    caught: bool
    near_miss: bool
    findings: tuple[Finding, ...]
    extra: int
    matched: str | None


def normalize_path(raw: str) -> str:
    """Strip markdown ticks, a trailing `:line`, and a leading `./`. A diff `a/` or `b/` prefix is
    left alone: `same_file` absorbs it as a leading directory."""
    path = raw.strip().strip("`").strip()
    path = _LINE_SUFFIX.sub("", path)
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return path


def parse_findings(raw: str) -> list[Finding]:
    """Every `FINDING:` line in answer order. `NO FINDINGS` and prose parse to nothing."""
    found: list[Finding] = []
    for line in raw.splitlines():
        match = _FINDING.match(line)
        if match is None:
            continue
        found.append(
            Finding(
                path=normalize_path(match.group("location")),
                klass=match.group("klass").strip().lower().replace(" ", "-"),
                text=match.group("text"),
            )
        )
    return found


def same_file(finding_path: str, defect_path: str) -> bool:
    """Equal paths, or one is a suffix of the other at a `/` boundary.

    Tolerates a reviewer that drops the directory prefix. A bare name shorter
    than `_MIN_PATH_LEN` characters never matches by suffix.
    """
    a, b = normalize_path(finding_path), normalize_path(defect_path)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= _MIN_PATH_LEN and longer.endswith("/" + shorter)


def score_findings(
    findings: list[Finding], defect_files: tuple[str, ...], defect_class: str
) -> Score:
    """Apply the pinned rule to the first TOP_N findings."""
    top = tuple(findings[:TOP_N])
    near = False
    for finding in top:
        if not any(same_file(finding.path, path) for path in defect_files):
            continue
        if finding.klass == defect_class:
            return Score(True, False, top, max(0, len(findings) - TOP_N), finding.text)
        near = True
    return Score(False, near, top, max(0, len(findings) - TOP_N), None)


def score_response(raw: str, defect_files: tuple[str, ...], defect_class: str) -> Score:
    return score_findings(parse_findings(raw), defect_files, defect_class)


def added_lines(patch: str) -> set[str]:
    """Stripped `+` lines of a unified diff, excluding the `+++` header."""
    out: set[str] = set()
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            out.add(line[1:].strip())
    return out


def leaked_fix_content(
    prompt: str,
    fix_sha: str,
    fix_subject: str,
    fix_patch: str,
    introducer_patch: str,
) -> list[str]:
    """Reasons the reviewer prompt carries content from the fixing commit.

    Checks three things. The fix SHA, in full or as any hex run of 7 or more characters
    that prefixes it (a `git log --oneline` short SHA). The fix subject. Every added
    line of the fix of at least `_LEAK_LINE_MIN` characters that does not also occur in
    the introducing patch text. Text the reviewer legitimately sees in the introducing
    diff (added, removed, context, or a fragment of a line) is shared, not a leak.
    """
    reasons: list[str] = []
    for run in sorted(set(_HEX_RUN.findall(prompt))):
        if fix_sha and fix_sha.startswith(run):
            reasons.append(f"fix sha {run}")
    if fix_subject and fix_subject in prompt:
        reasons.append("fix subject")
    for line in sorted(added_lines(fix_patch)):
        if len(line) >= _LEAK_LINE_MIN and line in prompt and line not in introducer_patch:
            reasons.append(f"fix line {line[:60]!r}")
    return reasons
