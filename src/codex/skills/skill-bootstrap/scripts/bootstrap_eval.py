#!/usr/bin/env python3
"""Measure whether an authored skill makes an agent more capable.

A bootstrap run authors skills. This script measures each one: the pass rate
of an agent that has the skill minus the pass rate of the same agent without
it. Grading is deterministic (substring, regex, or set F1 over a JSON block),
so the same outputs always score the same.

Subcommands:

    freeze  Validate eval cases and write them to a file that cannot be
            changed afterwards. The file carries a SHA-256 of the sorted
            cases.
    score   Grade recorded agent outputs against a frozen file and report the
            capability delta per case, per skill, and overall.

Cases file (`freeze --cases`):

    {"cases": [{"id": "C1", "skill": "acme-change-control",
                "source": "correction:<ref>" | "lens:<name>" | "outcome:<ref>",
                "prompt": "...", "grader": {...}}]}

Graders:

    {"kind": "contains_all", "terms": ["a", "b"]}
        Pass when every term appears in the output (case-insensitive).
    {"kind": "regex", "pattern": "...", "ignore_case": true}
        Pass when `re.search` finds the pattern. `ignore_case` is optional.
    {"kind": "json_set_f1", "key": "stale", "gold": ["x"], "threshold": 0.8}
        Read the last fenced json block in the output that parses as an
        object, take the list under `key`, and compare it with `gold` as
        string sets. Pass when F1 >= threshold (default 1.0). A block that is
        not valid JSON, or not an object, is skipped. A missing key, a value
        that is not a list of strings, or no usable block fails the case.

Results file (`score --results`), JSON lines, several reps per case and
condition allowed:

    {"case_id": "C1", "condition": "baseline" | "with_skill", "output": "..."}

Case status in the score payload:

    gain        with_skill pass rate is above baseline.
    no_gap      baseline already passes every rep and with_skill does too, so
                the knowledge is not missing and the skill adds nothing
                measurable for this case.
    regression  with_skill pass rate is below baseline. This wins over no_gap:
                a baseline of 1.0 with a lower with_skill rate is a regression.
    flat        Equal pass rates and baseline below 1.0.
    incomplete  A condition has no results.

Skill and overall means cover complete cases only, and include no_gap cases.

Exit codes:

    0  freeze wrote the file, or score found every case complete (and met
       `--min-delta` when given).
    1  score found an incomplete case, or the overall delta is below
       `--min-delta` (or unmeasured, when no case is complete).
    2  Configuration error: bad arguments, malformed cases, results, or
       frozen file, a frozen file edited after freezing, an existing `--out`,
       an `--out` inside a git work tree without `--allow-in-repo`, or git
       missing or failing when it must be asked.

Limits: freeze refuses to overwrite, so frozen means immutable on disk, and
the hash detects an edit to the cases at score time. It does not stop someone
from deleting the file and freezing new cases. The in-repo check asks git for
the work tree that encloses the output directory; it cannot see a path git
ignores differently from the check. Stdlib only, so the script runs from any
plugin root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FROZEN_SCHEMA = "skill-bootstrap-eval/1"
SOURCE_PREFIXES = ("correction:", "lens:", "outcome:")
CONDITIONS = ("baseline", "with_skill")
STATUSES = ("gain", "no_gap", "regression", "flat", "incomplete")
CASE_KEYS = frozenset({"id", "skill", "source", "prompt", "grader"})
JSON_FENCE = re.compile(r"```json[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
NOT_A_REPO = "not a git repository"

Payload = dict[str, Any]
Grade = Callable[[str], bool]


class ConfigError(Exception):
    """Bad input or a refused write: exit 2."""


# --- graders ---------------------------------------------------------------


def _check_keys(grader: Payload, allowed: set[str]) -> None:
    extra = sorted(set(grader) - allowed - {"kind"})
    if extra:
        raise ConfigError(f"grader {grader['kind']!r} has unknown keys: {', '.join(extra)}")


def _non_empty_strings(value: Any, what: str, allow_empty_list: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty_list):
        raise ConfigError(f"{what} must be a non-empty list of strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigError(f"{what} must hold only non-empty strings")
    return value


def _contains_all(grader: Payload) -> Grade:
    _check_keys(grader, {"terms"})
    terms = [t.casefold() for t in _non_empty_strings(grader.get("terms"), "terms")]
    return lambda output: all(term in output.casefold() for term in terms)


def _regex(grader: Payload) -> Grade:
    _check_keys(grader, {"pattern", "ignore_case"})
    pattern = grader.get("pattern")
    ignore_case = grader.get("ignore_case", False)
    if not isinstance(pattern, str) or not pattern:
        raise ConfigError("regex pattern must be a non-empty string")
    if not isinstance(ignore_case, bool):
        raise ConfigError("regex ignore_case must be a boolean")
    try:
        compiled = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        raise ConfigError(f"regex pattern does not compile: {exc}") from exc
    return lambda output: compiled.search(output) is not None


def extract_last_json_object(output: str) -> Payload | None:
    """Return the last fenced json block that parses to an object, else None."""
    found = None
    for block in JSON_FENCE.findall(output):
        try:
            parsed = json.loads(block)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            found = parsed
    return found


def set_f1(predicted: set[str], gold: set[str]) -> float:
    """Return F1 of two string sets. Two empty sets agree perfectly."""
    if not predicted and not gold:
        return 1.0
    hits = len(predicted & gold)
    if hits == 0:
        return 0.0
    precision, recall = hits / len(predicted), hits / len(gold)
    return 2 * precision * recall / (precision + recall)


def _threshold(value: Any) -> float:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not ok or not 0 < value <= 1:
        raise ConfigError("json_set_f1 threshold must be a number above 0 and at most 1")
    return float(value)


def _json_set_f1(grader: Payload) -> Grade:
    _check_keys(grader, {"key", "gold", "threshold"})
    key = grader.get("key")
    if not isinstance(key, str) or not key:
        raise ConfigError("json_set_f1 key must be a non-empty string")
    gold = {g.strip() for g in _non_empty_strings(grader.get("gold"), "gold", True)}
    threshold = _threshold(grader.get("threshold", 1.0))

    def grade(output: str) -> bool:
        block = extract_last_json_object(output)
        values = None if block is None else block.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            return False
        return set_f1({v.strip() for v in values}, gold) >= threshold

    return grade


GRADER_BUILDERS: dict[str, Callable[[Payload], Grade]] = {
    "contains_all": _contains_all,
    "regex": _regex,
    "json_set_f1": _json_set_f1,
}


def compile_grader(grader: Any) -> Grade:
    """Validate a grader spec and return a function from output text to pass."""
    if not isinstance(grader, dict):
        raise ConfigError("grader must be an object")
    kind = grader.get("kind")
    builder = GRADER_BUILDERS.get(kind) if isinstance(kind, str) else None
    if builder is None:
        raise ConfigError(f"unknown grader kind {kind!r}")
    return builder(grader)


# --- cases and frozen file --------------------------------------------------


def _read_json(path: str, what: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read {what} {path}: {exc}") from exc


def _validate_case(case: Any, position: int) -> Payload:
    if not isinstance(case, dict):
        raise ConfigError(f"case {position} is not an object")
    missing = sorted(CASE_KEYS - set(case))
    extra = sorted(set(case) - CASE_KEYS)
    if missing or extra:
        raise ConfigError(f"case {position} keys: missing {missing}, unknown {extra}")
    for key in ("id", "skill", "prompt"):
        if not isinstance(case[key], str) or not case[key].strip():
            raise ConfigError(f"case {position} {key} must be a non-empty string")
    source = case["source"]
    prefix = next(
        (p for p in SOURCE_PREFIXES if isinstance(source, str) and source.startswith(p)), ""
    )
    if not prefix or not source[len(prefix) :].strip():
        raise ConfigError(
            f"case {case['id']} source must be {' | '.join(p + '<ref>' for p in SOURCE_PREFIXES)}"
        )
    try:
        compile_grader(case["grader"])
    except ConfigError as exc:
        raise ConfigError(f"case {case['id']}: {exc}") from exc
    return case


def validate_cases(raw: Any) -> list[Payload]:
    """Return the cases sorted by id, or raise ConfigError on any defect."""
    cases = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ConfigError('input must be {"cases": [...]} with at least one case')
    checked = [_validate_case(case, i) for i, case in enumerate(cases)]
    ids = [case["id"] for case in checked]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ConfigError(f"duplicate case ids: {', '.join(duplicates)}")
    return sorted(checked, key=lambda case: case["id"])


def cases_digest(cases: list[Payload]) -> str:
    """Return the SHA-256 of the canonical JSON of the cases list."""
    canonical = json.dumps(cases, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def enclosing_repo(directory: Path) -> Path | None:
    """Return the git work tree that contains `directory`, or None when there is none.

    The directory may not exist yet, so ask from its nearest existing ancestor.
    Fails closed: any git failure other than "not a repository" raises.
    """
    probe = directory.resolve()
    while not probe.exists():
        probe = probe.parent
    try:
        proc = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env={**os.environ, "LC_ALL": "C"},  # the "not a git repository" test needs English
        )
    except FileNotFoundError as exc:
        raise ConfigError("git is not on PATH, so the in-repo check cannot run") from exc
    if proc.returncode == 0:
        return Path(proc.stdout.strip()).resolve()
    if NOT_A_REPO in proc.stderr.lower():
        return None
    raise ConfigError(f"git rev-parse failed for {probe}: {proc.stderr.strip()}")


def _check_out_path(out: Path, allow_in_repo: bool) -> None:
    if out.exists():
        raise ConfigError(f"{out} already exists; a frozen file is immutable, pick a new path")
    repo = None if allow_in_repo else enclosing_repo(out.parent)
    if repo is not None:
        raise ConfigError(
            f"{out} is inside the git work tree {repo}; write outside it, or pass"
            " --allow-in-repo to commit the eval cases on purpose"
        )


def freeze(args: argparse.Namespace) -> tuple[int, Payload]:
    cases = validate_cases(_read_json(args.cases, "cases file"))
    out = Path(args.out).resolve()
    _check_out_path(out, args.allow_in_repo)
    record = {
        "schema": FROZEN_SCHEMA,
        "frozen_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "sha256": cases_digest(cases),
        "cases": cases,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    # Mode "x" fails with FileExistsError (an OSError, exit 2) if --out appeared since the check.
    with out.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return 0, {
        "frozen": out.as_posix(),
        "sha256": record["sha256"],
        "skills": sorted({case["skill"] for case in cases}),
        "examined": {"cases": len(cases)},
    }


# --- scoring ----------------------------------------------------------------


def load_frozen(path: str) -> list[Payload]:
    """Return the frozen cases after checking the schema and the hash."""
    record = _read_json(path, "frozen file")
    if not isinstance(record, dict) or record.get("schema") != FROZEN_SCHEMA:
        raise ConfigError(f"{path} is not a {FROZEN_SCHEMA} file")
    cases = validate_cases({"cases": record.get("cases")})
    if cases_digest(cases) != record.get("sha256"):
        raise ConfigError(f"frozen file was edited after freezing: {path}")
    return cases


def _parse_result(line: str, number: int, graders: dict[str, Grade]) -> tuple[str, str, bool]:
    try:
        row = json.loads(line)
    except ValueError as exc:
        raise ConfigError(f"results line {number} is not JSON: {exc}") from exc
    if not isinstance(row, dict):
        raise ConfigError(f"results line {number} is not an object")
    case_id, condition, output = row.get("case_id"), row.get("condition"), row.get("output")
    if case_id not in graders:
        raise ConfigError(f"results line {number}: unknown case_id {case_id!r}")
    if condition not in CONDITIONS:
        raise ConfigError(f"results line {number}: unknown condition {condition!r}")
    if not isinstance(output, str):
        raise ConfigError(f"results line {number}: output must be a string")
    return case_id, condition, graders[case_id](output)


def grade_results(path: str, cases: list[Payload]) -> tuple[dict[tuple[str, str], list[bool]], int]:
    """Grade every result line. Return pass flags per (case, condition) and the line count."""
    graders = {case["id"]: compile_grader(case["grader"]) for case in cases}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(f"cannot read results {path}: {exc}") from exc
    tally: dict[tuple[str, str], list[bool]] = {}
    count = 0
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        case_id, condition, passed = _parse_result(line, number, graders)
        tally.setdefault((case_id, condition), []).append(passed)
        count += 1
    return tally, count


def _rate(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _status(baseline: float | None, with_skill: float | None) -> str:
    if baseline is None or with_skill is None:
        return "incomplete"
    if with_skill > baseline:
        return "gain"
    if with_skill < baseline:
        return "regression"
    return "no_gap" if baseline == 1.0 else "flat"


def _case_row(case: Payload, tally: dict[tuple[str, str], list[bool]]) -> Payload:
    base_flags = tally.get((case["id"], "baseline"), [])
    with_flags = tally.get((case["id"], "with_skill"), [])
    baseline, with_skill = _rate(base_flags), _rate(with_flags)
    delta = with_skill - baseline if baseline is not None and with_skill is not None else None
    return {
        "id": case["id"],
        "skill": case["skill"],
        "baseline_pass_rate": baseline,
        "with_skill_pass_rate": with_skill,
        "delta": delta,
        "status": _status(baseline, with_skill),
        "baseline_runs": len(base_flags),
        "with_skill_runs": len(with_flags),
    }


def _summary(rows: list[Payload]) -> Payload:
    """Means over complete rows, the capability delta, and counts by status."""
    complete = [row for row in rows if row["status"] != "incomplete"]
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in STATUSES}
    if not complete:
        return {"baseline": None, "with_skill": None, "capability_delta": None, "statuses": counts}
    baseline = sum(row["baseline_pass_rate"] for row in complete) / len(complete)
    with_skill = sum(row["with_skill_pass_rate"] for row in complete) / len(complete)
    return {
        "baseline": round(baseline, 4),
        "with_skill": round(with_skill, 4),
        "capability_delta": round(with_skill - baseline, 4),
        "statuses": counts,
    }


def _rounded(rows: list[Payload]) -> list[Payload]:
    keys = ("baseline_pass_rate", "with_skill_pass_rate", "delta")
    return [
        {k: (round(v, 4) if k in keys and v is not None else v) for k, v in row.items()}
        for row in rows
    ]


def score(args: argparse.Namespace) -> tuple[int, Payload]:
    cases = load_frozen(args.frozen)
    tally, result_count = grade_results(args.results, cases)
    rows = [_case_row(case, tally) for case in cases]
    skills = {
        name: _summary([row for row in rows if row["skill"] == name])
        for name in sorted({row["skill"] for row in rows})
    }
    overall = _summary(rows)
    failing = overall["statuses"]["incomplete"] > 0
    payload: Payload = {
        "cases": _rounded(rows),
        "skills": skills,
        "overall": overall,
        "examined": {"cases": len(cases), "results": result_count},
    }
    if args.min_delta is not None:
        delta = overall["capability_delta"]
        met = delta is not None and delta >= args.min_delta
        payload["min_delta"] = {"required": args.min_delta, "met": met}
        failing = failing or not met
    return (1 if failing else 0), payload


# --- CLI --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bootstrap_eval", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_freeze = sub.add_parser("freeze", help="validate cases and write an immutable frozen file")
    p_freeze.add_argument("--cases", required=True, help="cases JSON file")
    p_freeze.add_argument("--out", required=True, help="frozen file to create (must not exist)")
    p_freeze.add_argument(
        "--allow-in-repo",
        action="store_true",
        help="allow --out inside a git work tree, to commit the eval cases on purpose",
    )

    p_score = sub.add_parser("score", help="grade results and report the capability delta")
    p_score.add_argument("--frozen", required=True, help="frozen file from freeze")
    p_score.add_argument("--results", required=True, help="JSON lines of agent outputs")
    p_score.add_argument(
        "--min-delta", type=float, help="exit 1 when the overall capability delta is below this"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"freeze": freeze, "score": score}
    try:
        if getattr(args, "min_delta", None) is not None and not math.isfinite(args.min_delta):
            raise ConfigError("--min-delta must be a finite number")
        code, payload = handlers[args.command](args)
    except ConfigError as exc:
        print(json.dumps({"error": "config", "message": str(exc)}))
        return 2
    except OSError as exc:
        print(json.dumps({"error": "io", "message": str(exc)}))
        return 2
    print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
