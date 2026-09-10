#!/usr/bin/env python3
"""Flag a SKILL.md that declares a retired ADR in `metadata.adr` (issue #5665).

A skill names the decision records it depends on in nested frontmatter::

    ---
    name: memory-search
    metadata:
      adr: ADR-007, ADR-037, ADR-038, ADR-056, ADR-063
    ---

Nothing validated those names against the ADRs' own lifecycle state. When a
record is superseded, every skill that declares it keeps pointing at a decision
the generated index marks Do Not Cite, and no gate notices: the supersession PR
touches only `.agents/architecture/`, and every later PR leaves the stale
declaration outside its diff. An agent loading the skill then reads a retired
record as current, which is the failure `.claude/rules/canonical-source-mirror.md`
describes as a wrong citation weaponizing the next reader's trust.

Measured when this gate was written, at `e06736d12`: 18 SKILL.md files declare
`metadata.adr` and 16 of them name at least one retired record. The oldest is
not from the change that prompted this gate. ADR-056 went `superseded` on
2026-08-25 in PR #5283, and four skills still declared it two weeks later, so
the drift is a standing condition rather than one supersession's side effect.

The key is nested. It is `metadata:` then `adr:`, never a top-level `adr:`
field, so a probe for `^adr:` returns zero matches and will convince the reader
that the surface does not exist.

## The status vocabulary, quoted from canonical

`.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md:48` declares the
enum verbatim::

    status: proposed | accepted | rejected | deprecated | superseded   # enum, no prose

`scripts/validation/check_adr_lifecycle.py:152-155` carries the same list as the
set it validates against, with the same attribution::

    # ADR-073 Decision section, verbatim: "status: proposed | accepted | rejected |
    ...
    {"proposed", "accepted", "rejected", "deprecated", "superseded"}

There is no `withdrawn` status. :data:`RETIRED_STATUSES` is the subset of that
enum naming a record a skill must not declare as a live dependency, and it
matches the three issue #5665 names: superseded, deprecated, rejected.

`proposed` is deliberately NOT retired. A proposed record is an open decision,
not a withdrawn one, and skills legitimately declare one while it is under
debate. Gating it would flag ADR-070, which ADR-106 cites as a live gate.

## Stricter/looser/different than canonical

This gate reuses :func:`check_adr_lifecycle.collect_records` so ADR parsing has
one owner, and re-derives the status read from the public ``Record.frontmatter``
rather than importing that module's private ``_status_of``.

It diverges from `check_adr_lifecycle.py` in subject and therefore in scope. That
gate validates ADR records against ADR-073's schema; this one validates the
*consumers* of those records and never reports a finding against an ADR file. A
record whose own frontmatter will not parse is that gate's finding, not this
one's: such a record is skipped here with no status, so the two gates cannot
double-report the same file.

Directory pruning mirrors `build/scripts/validate_plugin_manifests.py:331-344`,
quoted verbatim::

    excluded_dirs = {
        ".agent-tmp",
        ".worktrees",
        "worktrees",
    ...
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]

Different than that canonical set: :data:`_PRUNED_DIRS` adds `.venv`, `.git`,
`node_modules`, `__pycache__`, `.pytest_cache` and `.pytest_tmp`, because this
gate walks for `SKILL.md` rather than `plugin.json` and a virtualenv can carry
an installed copy of this repository's own skills. `evals/` is deliberately NOT
pruned: its one tracked SKILL.md declares `metadata.issue` and no `adr`, so it
passes today, and a frozen evaluation record that did declare a retired ADR is a
finding a human should read rather than a case to hide in advance.

## Why a ratchet rather than a hard gate

16 violations exist at the commit that introduced this file. Failing on any
violation would red every push until the repoint lands, so the baseline records
today's count as a ceiling that may fall and never rise, which is the shape
`scripts/validation/adr_lifecycle_baseline.json` already uses. Regenerate with
``--write-baseline`` only when the count falls.

Exit codes follow ADR-035: 0 ok, 1 the count rose above its baseline, 2 a
configuration fault (unreadable or stale baseline, missing ADR directory). A
gate that cannot read its own baseline has not run, and reporting that as a pass
is the silent-pass failure `.claude/rules/ci-scripts.md` exists to stop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from check_adr_lifecycle import Record, collect_records  # noqa: E402

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2

#: The one check name this gate owns. Mirrors the per-check baseline shape of
#: `check_adr_lifecycle.py` so both files read the same way, even though this
#: gate has a single check and that one has eight.
CHECK = "skill-adr-binding"
CHECKS = (CHECK,)

#: Subset of ADR-073's status enum naming a record no skill should declare as a
#: live dependency. See the module docstring for the verbatim enum.
RETIRED_STATUSES = frozenset({"superseded", "deprecated", "rejected"})

#: Directory names never walked. See "Stricter/looser/different than canonical".
_PRUNED_DIRS = frozenset(
    {
        ".agent-tmp",
        ".worktrees",
        "worktrees",
        "node_modules",
        ".git",
        "cache",
        ".pytest_cache",
        ".pytest_tmp",
        ".venv",
        "__pycache__",
    }
)

#: An ADR id as it appears inside a `metadata.adr` value: "ADR-007", "adr-7",
#: "ADR_37". Deliberately does not match a bare integer, because `metadata.adr`
#: is prose-ish and a bare number there is far more likely to be a count than a
#: record id. `check_adr_lifecycle._ADR_REFERENCE_RE` does accept a bare integer,
#: but it reads a structured frontmatter reference field where that is the
#: documented shorthand; this field has no such contract.
_ADR_REF_RE = re.compile(r"ADR[-_ ]?(\d{1,4})", re.IGNORECASE)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)

_BASELINE_PATH = Path(__file__).with_name("skill_adr_bindings_baseline.json")

_BASELINE_DESCRIPTION = (
    "Ceiling on SKILL.md files declaring a retired ADR in metadata.adr "
    "(issue #5665). The count may fall but never rise. Regenerate with: "
    "uv run python scripts/validation/check_skill_adr_bindings.py --write-baseline"
)


@dataclass(frozen=True, slots=True)
class Violation:
    """One SKILL.md declaring at least one retired ADR.

    Shaped like `check_adr_lifecycle.Violation` (check, path, detail, render) so
    a reader moving between the two gates meets one finding format.
    """

    check: str
    path: str
    detail: str

    def render(self) -> str:
        return f"{self.path}: [{self.check}] {self.detail}"


def adr_statuses(repo_root: Path, adr_dir: Path) -> dict[int, str]:
    """ADR number to lowercased frontmatter status, for records that parsed.

    Reuses :func:`check_adr_lifecycle.collect_records` so ADR discovery and
    frontmatter parsing keep one owner. A record whose frontmatter did not parse
    is absent from the mapping rather than present with an empty status: an
    unparseable record is the lifecycle gate's finding, and treating it here as
    "not retired" is the correct conservative read for a consumer check.
    """
    records, _violations = collect_records(adr_dir, repo_root)
    statuses: dict[int, str] = {}
    for record in records:
        statuses[record.number] = _status_of_record(record)
    return statuses


def _status_of_record(record: Record) -> str:
    """Lowercased frontmatter status, or "" when unparseable or non-scalar.

    Re-derived from the public ``Record.frontmatter`` rather than importing
    `check_adr_lifecycle._status_of`, which is private. The contract is the same
    one that function documents: "Lowercased frontmatter status, or "" when
    absent or non-scalar."
    """
    frontmatter = record.frontmatter
    if not isinstance(frontmatter, dict):
        return ""
    value = frontmatter.get("status")
    if value is None or isinstance(value, (list, dict)):
        return ""
    return str(value).strip().lower()


def find_skill_files(repo_root: Path) -> list[Path]:
    """Every `SKILL.md` under ``repo_root``, pruned and sorted for stable output."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _PRUNED_DIRS)
        if "SKILL.md" in filenames:
            found.append(Path(dirpath) / "SKILL.md")
    return sorted(found)


def declared_adr_numbers(skill_path: Path) -> tuple[list[int], str | None]:
    """ADR numbers a skill declares in `metadata.adr`, plus a read fault.

    Returns ``([], reason)`` when the file could not be read at all, so the
    caller can surface an I/O fault instead of silently scoring it as clean.
    A file that reads but has no frontmatter, no `metadata`, or no nested `adr`
    returns ``([], None)``: declaring nothing is valid and common.
    """
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"could not be read: {exc}"
    except UnicodeDecodeError as exc:
        return [], f"is not valid UTF-8: {exc}"

    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return [], None
    try:
        parsed: Any = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        # Frontmatter shape is another gate's subject. A skill whose YAML will
        # not parse declares nothing this gate can resolve, and inventing a
        # finding here would double-report that gate's violation.
        return [], None
    if not isinstance(parsed, dict):
        return [], None
    metadata = parsed.get("metadata")
    if not isinstance(metadata, dict):
        return [], None
    raw = metadata.get("adr")
    if raw is None:
        return [], None

    # The field is authored as a comma-joined string today, but a YAML list is
    # the shape an author reaching for multiple values would try next. Render
    # either to text and scan, so a list does not silently read as zero ids.
    if isinstance(raw, (list, tuple)):
        haystack = " ".join(str(item) for item in raw)
    else:
        haystack = str(raw)

    numbers = sorted({int(m.group(1)) for m in _ADR_REF_RE.finditer(haystack)})
    return numbers, None


def scan(repo_root: Path, adr_dir: Path) -> list[Violation]:
    """Every SKILL.md declaring a retired ADR, in path order."""
    statuses = adr_statuses(repo_root, adr_dir)
    violations: list[Violation] = []
    for skill in find_skill_files(repo_root):
        try:
            rel = skill.relative_to(repo_root).as_posix()
        except ValueError:
            rel = skill.as_posix()
        numbers, fault = declared_adr_numbers(skill)
        if fault is not None:
            violations.append(Violation(CHECK, rel, f"SKILL.md {fault}"))
            continue
        retired = [
            (number, statuses[number])
            for number in numbers
            if statuses.get(number, "") in RETIRED_STATUSES
        ]
        if not retired:
            continue
        named = ", ".join(f"ADR-{number:03d} is {status}" for number, status in retired)
        violations.append(
            Violation(
                CHECK,
                rel,
                f"metadata.adr declares a retired record: {named}. "
                "Repoint it at the successor, or drop the declaration.",
            )
        )
    return violations


def tally(violations: list[Violation]) -> dict[str, int]:
    """Per-check counts, with every known check present even at zero."""
    counts = {name: 0 for name in CHECKS}
    for violation in violations:
        counts[violation.check] = counts.get(violation.check, 0) + 1
    return counts


def _parse_baseline_payload(text: str, source: str) -> dict[str, int] | str:
    """Validate baseline JSON already read from ``source``, or a one-line reason.

    Mirrors `check_adr_lifecycle._parse_baseline_payload` in contract and in the
    order of its checks, so both baselines fail for the same reasons with the
    same wording shape.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"baseline {source} is not valid JSON: {exc}"
    if not isinstance(payload, dict) or not isinstance(payload.get("counts"), dict):
        return f"baseline {source} has no `counts` mapping"
    counts = payload["counts"]
    missing = sorted(set(CHECKS) - set(counts))
    unknown = sorted(set(counts) - set(CHECKS))
    if missing or unknown:
        return (
            f"baseline {source} does not match the check list (missing: "
            f"{missing or 'none'}, unknown: {unknown or 'none'}). "
            "Regenerate it with --write-baseline."
        )
    for name, value in counts.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return f"baseline {source} entry {name} is {value!r}, not a count"
    return {name: int(counts[name]) for name in CHECKS}


def read_baseline(path: Path) -> dict[str, int] | str:
    """Baseline counts, or a one-line reason the file cannot be used.

    Only ``FileNotFoundError`` and its siblings arrive as ``OSError``; a decode
    fault is a ``ValueError`` and is caught separately. Both degrade to the same
    one-line reason so the caller keeps a single decision point rather than
    meeting a traceback, which is the fail-closed read boundary this repository
    requires before acting on state.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"baseline {path} could not be read: {exc}"
    except UnicodeDecodeError as exc:
        return f"baseline {path} is not valid UTF-8: {exc}"
    return _parse_baseline_payload(text, str(path))


def write_baseline(path: Path, counts: dict[str, int]) -> None:
    """Record ``counts`` as the new ceiling, atomically.

    Writes a temporary sibling then ``os.replace()`` so an interrupted run
    cannot leave a truncated baseline behind, which would turn the next run into
    a config error instead of a pass.
    """
    payload = {
        "schema_version": "1",
        "description": _BASELINE_DESCRIPTION,
        "counts": {name: int(counts.get(name, 0)) for name in CHECKS},
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name,
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle as tmp:
            tmp.write(rendered)
            tmp_name = tmp.name
        os.replace(tmp_name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Flag a SKILL.md declaring a retired ADR in metadata.adr (issue #5665)."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to scan. Defaults to the current directory.",
    )
    parser.add_argument(
        "--baseline",
        default=str(_BASELINE_PATH),
        help="Path to the ceiling file.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Record the current counts as the new ceiling and exit 0.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    adr_dir = repo_root / ".agents" / "architecture"
    if not adr_dir.is_dir():
        print(
            f"[{CHECK}] config: ADR directory {adr_dir} does not exist, so no "
            "status could be resolved and the gate did not run",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    violations = scan(repo_root, adr_dir)
    counts = tally(violations)
    baseline_path = Path(args.baseline)

    if args.write_baseline:
        write_baseline(baseline_path, counts)
        print(f"[{CHECK}] baseline written to {baseline_path}: {counts[CHECK]}")
        return EXIT_OK

    baseline = read_baseline(baseline_path)
    if isinstance(baseline, str):
        print(f"[{CHECK}] config: {baseline}", file=sys.stderr)
        return EXIT_CONFIG

    for violation in violations:
        print(violation.render())

    current = counts[CHECK]
    ceiling = baseline[CHECK]
    if current > ceiling:
        print(
            f"[{CHECK}] REGRESSION: {current} SKILL.md file(s) declare a retired "
            f"ADR, above the ceiling of {ceiling}. Repoint the declaration at the "
            "successor record, or drop it.",
            file=sys.stderr,
        )
        return EXIT_REGRESSION

    if current < ceiling:
        print(
            f"[{CHECK}] improved: {current} of a permitted {ceiling}. "
            "Lower the ceiling with --write-baseline."
        )
    else:
        print(f"[{CHECK}] at baseline: {current} of a permitted {ceiling}.")
    return EXIT_OK


def validate_skill_adr_bindings(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True when the count is at or below its baseline.

    A config error (exit 2) returns False. A gate that cannot read its own
    baseline has not run, and reporting that as a pass is the silent-pass
    failure the repository's CI-script rules exist to stop.
    """
    return main(["--repo-root", str(repo_root)]) == EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
