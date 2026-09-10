#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: one CLI owns the scan, the ratchet, and the
# atomic baseline write. That is the same shape check_doc_interpreter_portability.py
# and check_skill_md_exec_portability.py took this exemption for, and the direct
# sibling check_adr_lifecycle.py took it with the same reasoning.
#
# The rule's remediation is to split helpers out. The three functions that would
# move, tally/read_baseline/write_baseline, are already duplicated from
# check_adr_lifecycle.py, whose copies are hard-keyed to its own eight-name CHECKS
# tuple and its own baseline description, so they cannot be imported as they
# stand. Extracting a fourth copy here would add a module without retiring either
# existing one. Unifying them means parameterizing that gate, which has its own
# ratchets and a 1717-line suite, so it is a separate change rather than a
# side effect of this one.
#
# A large share of the lines are the module docstring, which canonical-source-mirror.md
# requires to carry its quoted contracts verbatim rather than paraphrased.
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

## Scope is git-tracked files

Candidate paths come from the index, through ``tracked_files`` in
`scripts/ci/count_ratchet.py`, and each path's content is then read off disk. A
filesystem walk was the first implementation and is wrong for a ratchet.
`scripts/ci/count_ratchet.py:18-21` states why, verbatim::

    Scope is git-TRACKED files, never a directory walk. ``os.walk`` also visits
    untracked scratch, nested worktrees, and vendored caches that a contributor
    happens to have on disk, which inflated a local ruff run to 767 against a real
    tracked count of 361 and made that gate report a phantom regression outside CI.

`.claude/rules/ci-scripts.md` MUST 9 binds it: a ratchet baseline is a claim
about a ref, so the measurement behind it must not read untracked state, or the
same commit scores differently on two machines. Measured on this gate before the
change: one untracked `SKILL.md` declaring ADR-007, on a tree byte-identical at
HEAD and in the index, took the count from 16 to 17 and exited 1, and the remedy
it printed sent the reader to repoint a file the repository does not contain.

Reading each path's content off disk rather than out of the ref is deliberate,
and matches the same sibling: a staged or unstaged edit to a tracked `SKILL.md`
is counted like any other content, so the pre-push hook sees a declaration the
author added locally, while ``git ls-files`` never offers an untracked path at
all. That enumeration lists index entries, so an unmerged path arrives once per
merge stage; ``tracked_files`` deduplicates it (issue #4746), which is the other
reason to borrow it rather than call git here.

A tracked path the working tree does not hold is counted and named rather than
dropped. The index lists it, but a deletion in progress, a sparse checkout and a
skip-worktree entry all leave it unreadable, and none of those is a finding about
the declaration. Dropping them silently was a defect: with every manifest absent
the gate printed ``improved: 0 of a permitted 16`` and exited 0, which does not
merely fail to warn, it asserts the tree got better and tells the reader to lower
the ceiling. Reproduced on five tracked manifests removed under
``git update-index --skip-worktree``, with ``git status`` reporting the tree
clean. So an absent path prints a note naming it, a run that examined NOTHING is
a configuration fault, and ``--write-baseline`` refuses anything short of a
complete read.

The two thresholds differ on purpose. A partial read can only undercount, which
cannot manufacture a regression, and blocking it would fail a contributor who
removed a manifest and has not staged the deletion yet. An undercount written as
a ceiling does real damage, so the write path requires
``examined == candidates > 0``. An earlier form of the check asked
``candidates and not examined``, which is False when ``candidates`` is 0, so a
tree offering no manifest at all printed the same ``improved: 0 of a permitted
16`` line, and its ``--write-baseline`` recorded 0 with no absent path to refuse
on.

A manifest whose bytes come from outside the repository is reported rather than
read. Two shapes share one invariant: a mode-120000 entry's tracked content is
the link target string, and a manifest under a symlinked PARENT resolves outside
the tree while its own final component is an ordinary file. Testing
``is_symlink()`` on the final component saw the first and missed the second, so
:func:`_escapes_repo` asks the question the invariant is about. No tracked
`SKILL.md` is a symlink today.

A declared id with no record is reported too. Without that, an
`.agents/architecture` holding unrelated records passes the presence check, no
declared id resolves, every violating skill scores clean, and the gate prints
``improved`` and invites lowering the ceiling. Measured on this tree: 106 records
resolve and no skill declares an id without one, so this cannot move today's
count.

A path that exists, resolves inside the tree, and still cannot be read is a
finding.

`evals/` is deliberately not excluded: its one tracked SKILL.md declares
`metadata.issue` and no `adr`, so it passes today, and a frozen evaluation
record that did declare a retired ADR is a finding a human should read rather
than a case to hide in advance.

## Why a ratchet rather than a hard gate

16 violations exist at the commit that introduced this file. Failing on any
violation would red every push until the repoint lands, so the baseline records
today's count as a ceiling that may fall and never rise, which is the shape
`scripts/validation/adr_lifecycle_baseline.json` already uses. Regenerate with
``--write-baseline`` only when the count falls.

Exit codes follow ADR-035: 0 ok, 1 the count rose above its baseline, 3 git could
not list the tracked files, and 2 for every configuration fault. Those are an
unreadable, unstattable or stale baseline, a missing ADR directory, an ADR
directory holding no records, a run that examined nothing,
and a ``--write-baseline`` that would raise the ceiling or was measured from a
partial tree. A gate that cannot read its own baseline, cannot enumerate what it
is meant to scan, or examined nothing has not run, and reporting any of those as
a pass is the silent-pass failure `.claude/rules/ci-scripts.md` exists to stop.

Every terminal line carries the examined count beside the violation count, which
MUST 12 requires in as many words: "0 violations in 381 files" is verifiable,
"OK" is not. `check_adr_lifecycle.py:1195` prints the same pairing.
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

_REPO_ROOT = _SCRIPT_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from check_adr_lifecycle import ADR_FILENAME_RE, Record, collect_records  # noqa: E402

from scripts.ci.count_ratchet import tracked_files  # noqa: E402

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

#: The one check name this gate owns. Mirrors the per-check baseline shape of
#: `check_adr_lifecycle.py` so both files read the same way, even though this
#: gate has a single check and that one has eight.
CHECK = "skill-adr-binding"
CHECKS = (CHECK,)

#: Subset of ADR-073's status enum naming a record no skill should declare as a
#: live dependency. See the module docstring for the verbatim enum.
RETIRED_STATUSES = frozenset({"superseded", "deprecated", "rejected"})

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


def find_skill_files(repo_root: Path) -> list[Path] | None:
    """Every git-tracked `SKILL.md` under ``repo_root``, sorted, or None on failure.

    None means git could not list the index, which is an external fault and not
    an empty result. See "Scope is git-tracked files" in the module docstring for
    why the index rather than a filesystem walk.
    """
    relatives = tracked_files(repo_root, ("*SKILL.md",))
    if relatives is None:
        return None
    # The pathspec is a suffix match, so it also offers `LEGACY-SKILL.md` and
    # `notes.SKILL.md`. The walk this replaced tested `"SKILL.md" in filenames`,
    # an exact basename, and a manifest is the only subject this gate has. No
    # tracked path needs the filter today, which is exactly why it is written
    # down rather than left to the tree's current shape.
    return sorted(
        repo_root / relative
        for relative in relatives
        if relative.rsplit("/", 1)[-1] == "SKILL.md"
    )


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


def _escapes_repo(skill: Path, repo_root: Path) -> bool:
    """True when reading ``skill`` would take bytes from outside the repository.

    Covers a symlinked manifest and a manifest under a symlinked parent with one
    question, because the invariant is about where the bytes come from rather
    than which path component carries the link. A resolve that raises is treated
    as escaping: a path this cannot place is not one to read through.
    """
    if skill.is_symlink():
        return True
    try:
        return not skill.resolve().is_relative_to(repo_root.resolve())
    except OSError:
        return True


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What a scan found, and as importantly what it managed to look at.

    `.claude/rules/ci-scripts.md` MUST 12 requires a run that examined nothing to
    be distinguishable from a run that examined everything and found nothing. The
    counts therefore travel together, so no caller can render one without the
    other. ``candidates`` is what the index offered, ``examined`` is what was
    actually read, and ``absent`` names the difference.
    """

    violations: list[Violation]
    candidates: int
    examined: int
    absent: list[str]


def _declaration_finding(
    skill: Path, rel: str, statuses: dict[int, str], adr_dir: Path
) -> Violation | None:
    """The one finding this manifest's declarations earn, or None when clean.

    Split out of :func:`scan` so that function keeps one subject. `scan` decides
    whether a path can be read at all, which is a question about the index and
    the working tree; this decides what the bytes say, which is a question about
    the corpus. Merging them put six branches in one loop and took `scan` to
    cyclomatic complexity 11 against this repository's ceiling of 10.
    """
    numbers, fault = declared_adr_numbers(skill)
    if fault is not None:
        return Violation(CHECK, rel, f"SKILL.md {fault}")

    unknown = [number for number in numbers if number not in statuses]
    if unknown:
        # A declared id with no record is drift too, and reporting it is what
        # keeps the count honest when the corpus itself is wrong. Without this,
        # an `.agents/architecture` holding unrelated records passes the presence
        # check, no declared id resolves, every violating skill scores clean, and
        # the gate prints `improved` and invites lowering the ceiling. Measured
        # on this tree: 106 records resolve and no skill declares an id without
        # one, so this cannot move today's count.
        missing = ", ".join(f"ADR-{number:03d}" for number in unknown)
        return Violation(
            CHECK,
            rel,
            f"metadata.adr declares {missing}, which no record under "
            f"{adr_dir.name}/ defines. Either the id is wrong or the corpus this "
            "ran against is not the one that holds it.",
        )

    retired = [
        (number, statuses[number])
        for number in numbers
        if statuses[number] in RETIRED_STATUSES
    ]
    if not retired:
        return None
    named = ", ".join(f"ADR-{number:03d} is {status}" for number, status in retired)
    return Violation(
        CHECK,
        rel,
        f"metadata.adr declares a retired record: {named}. "
        "Repoint it at the successor, or drop the declaration.",
    )


def scan(repo_root: Path, adr_dir: Path) -> ScanResult | str:
    """Every tracked SKILL.md declaring a retired ADR, in path order.

    Returns the fault reason as a string when the tracked-file list could not be
    read, mirroring :func:`read_baseline`, so a gate that could not enumerate
    anything never reports an empty findings list as a clean tree.
    """
    statuses = adr_statuses(repo_root, adr_dir)
    skills = find_skill_files(repo_root)
    if skills is None:
        return (
            f"git could not list tracked SKILL.md files under {repo_root}, so "
            "nothing was examined and the gate did not run"
        )
    violations: list[Violation] = []
    absent: list[str] = []
    examined = 0
    for skill in skills:
        try:
            rel = skill.relative_to(repo_root).as_posix()
        except ValueError:
            rel = skill.as_posix()
        if _escapes_repo(skill, repo_root):
            # Two shapes, one invariant: the bytes read must come from inside the
            # repository. A mode-120000 entry's tracked content is the link target
            # string rather than the manifest, and a manifest under a symlinked
            # PARENT resolves outside the tree while its own final component is an
            # ordinary file. Testing `is_symlink()` on the final component alone
            # saw the first and missed the second. Either way the count would come
            # from bytes no ref holds, which is the untracked-state read this gate
            # moved off `os.walk` to prevent, so it is reported, not followed.
            violations.append(
                Violation(
                    CHECK,
                    rel,
                    "SKILL.md is a symlink or resolves outside the repository, so "
                    "its tracked content is a link target rather than a manifest "
                    "and its declarations cannot be resolved from the index. "
                    "Replace it with a regular file inside the tree.",
                )
            )
            continue
        if not skill.exists():
            # The index lists a path the working tree does not hold: a deletion in
            # progress, a sparse checkout, or a skip-worktree entry. That is not a
            # finding, but it is also not an examination, so it is counted and
            # reported rather than dropped. See `_report_absent` for what the
            # caller does with it.
            absent.append(rel)
            continue
        examined += 1
        finding = _declaration_finding(skill, rel, statuses, adr_dir)
        if finding is not None:
            violations.append(finding)
    return ScanResult(
        violations=violations,
        candidates=len(skills),
        examined=examined,
        absent=absent,
    )


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


def _scan_or_report(repo_root: Path, adr_dir: Path) -> ScanResult | None:
    """:func:`scan`'s result, or None after writing the fault to stderr.

    One owner for the external-fault message, so the `--write-baseline` path and
    the checking path cannot drift into reporting the same failure differently.
    """
    scanned = scan(repo_root, adr_dir)
    if isinstance(scanned, str):
        print(f"[{CHECK}] external: {scanned}", file=sys.stderr)
        return None
    return scanned


#: How many absent paths to name before truncating. Enough to recognise a
#: pattern, few enough that a bulk checkout state does not flood the terminal.
_ABSENT_SAMPLE = 5


def _report_absent(result: ScanResult) -> None:
    """Name the tracked manifests the working tree does not hold.

    Silence here is what made a sparse or unchecked-out tree print `improved: 0
    of a permitted 16` and exit 0, which does not merely fail to warn: it asserts
    the tree got better and tells the reader to lower the ceiling.
    """
    if not result.absent:
        return
    shown = ", ".join(result.absent[:_ABSENT_SAMPLE])
    more = len(result.absent) - _ABSENT_SAMPLE
    suffix = f", and {more} more" if more > 0 else ""
    print(
        f"[{CHECK}] note: {len(result.absent)} of {result.candidates} tracked "
        f"SKILL.md file(s) are listed in the index but absent from the working "
        f"tree, so they were not examined: {shown}{suffix}",
        file=sys.stderr,
    )


def _corpus_is_empty(adr_dir: Path) -> bool:
    """True when no `ADR-NNN-*.md` is present, so no status can resolve.

    Mirrors the corpus-presence half of `check_adr_lifecycle.py:1258`, quoted
    verbatim::

        if not any(ADR_FILENAME_RE.match(md.name) for md in adr_dir.glob("ADR-*.md")):

    That gate added this because an emptied or misrouted corpus still passes the
    `is_dir()` check, so a missing corpus reads as a clean corpus. Here the
    consequence is worse than a false pass on the records: with no statuses
    resolved, `statuses.get(number, "")` puts every declared id outside
    :data:`RETIRED_STATUSES`, so every violating skill scores clean.
    """
    return not any(ADR_FILENAME_RE.match(md.name) for md in adr_dir.glob("ADR-*.md"))


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

    if _corpus_is_empty(adr_dir):
        print(
            f"[{CHECK}] config: no ADR records found under {adr_dir}, so every "
            "declaration would resolve to no status and score clean. The gate "
            "did not run",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    baseline_path = Path(args.baseline)

    if args.write_baseline:
        return _write_baseline_command(repo_root, adr_dir, baseline_path)

    # The gate's own configuration is read before its environment is touched. An
    # unusable baseline is the caller's fault and costs one small file read, so
    # reporting it ahead of a git failure gives the more actionable message when
    # both are true.
    baseline = read_baseline(baseline_path)
    if isinstance(baseline, str):
        print(f"[{CHECK}] config: {baseline}", file=sys.stderr)
        return EXIT_CONFIG

    result = _scan_or_report(repo_root, adr_dir)
    if result is None:
        return EXIT_EXTERNAL
    _report_absent(result)

    if not result.examined:
        # Nothing was read, whether because the index offered nothing or because
        # every candidate was absent. Both reach the same wrong outcome and the
        # earlier form caught only the second: `candidates and not examined` is
        # False when `candidates` is 0, so a tree offering no manifest printed
        # `improved: 0 of a permitted 16` and invited lowering the ceiling to
        # nothing.
        #
        # A PARTIAL read is deliberately not blocked here. It can only undercount,
        # which cannot manufacture a regression, and blocking it would fail a
        # contributor who has removed a manifest but not yet staged the deletion.
        # The note from `_report_absent` says what was skipped, and
        # `--write-baseline`, where an undercount does real damage, stays strict.
        print(
            f"[{CHECK}] config: examined 0 of {result.candidates} tracked SKILL.md "
            "file(s), so this run measured nothing. Check out the working tree, or "
            "point --repo-root at the repository that holds the manifests",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    counts = tally(result.violations)
    for violation in result.violations:
        print(violation.render())

    current = counts[CHECK]
    ceiling = baseline[CHECK]
    scope = f"across {result.examined} of {result.candidates} tracked SKILL.md file(s)"
    if current > ceiling:
        print(
            f"[{CHECK}] REGRESSION: {current} SKILL.md file(s) declare a retired "
            f"ADR {scope}, above the ceiling of {ceiling}. Repoint the "
            "declaration at the successor record, or drop it.",
            file=sys.stderr,
        )
        return EXIT_REGRESSION

    if current < ceiling:
        print(
            f"[{CHECK}] improved: {current} of a permitted {ceiling}, {scope}. "
            "Lower the ceiling with --write-baseline."
        )
    else:
        print(f"[{CHECK}] at baseline: {current} of a permitted {ceiling}, {scope}.")
    return EXIT_OK


def _write_baseline_command(repo_root: Path, adr_dir: Path, baseline_path: Path) -> int:
    """Record the current count as the ceiling, or refuse and say why.

    Two refusals, both of which the first revision of this gate lacked.

    A ceiling measured from a tree that does not hold every tracked manifest is
    lower than the same commit scores in a full checkout, and writing it makes
    every later full run a permanent regression against a number no tree ever
    held. So any absent path refuses the write.

    A ratchet may only fall. `.claude/rules/ci-scripts.md` MUST NOT 4 forbids
    raising a count baseline, and the shared `scripts/ci/count_ratchet.py:1016`
    enforces it by reaching its writer only inside ``if count < baseline:``.
    Without this, the remedy line this gate itself prints is a one-command way to
    legalise a new violation.

    Weaker than the sibling, deliberately and for now. An earlier revision of this
    docstring claimed `check_adr_lifecycle.py` "refuses the same way". That was
    false: it resolves a base ref and compares against the value recorded there
    (`_resolve_default_base_ref`, `baseline_absent_at_ref` and `_counts_at_ref`,
    wired at `scripts/validation/check_adr_lifecycle.py:1146-1150`), while this
    gate reads the ceiling only from the working-tree file. The gap that leaves is
    real and was reproduced in three ordinary commits: add a violation, `git rm`
    the baseline, then run the remedy line above, which sees no ceiling, treats it
    as a first write, and records the raised number. Nothing else catches it,
    because this gate is registered in no merge-tree backstop
    (`scripts/ci/merge_tree_ratchet_registry.py` holds five `scripts/ci` ratchets
    and not this one).

    It is disclosed rather than closed here because it differs in kind from the
    holes this module does close. Those were tree states that leave the diff
    untouched, so review cannot see them; this one deletes a tracked file and
    therefore appears in the diff as a deletion beside the rewritten ceiling.
    Closing it properly means a base-ref read, which is the follow-up named in the
    pull request rather than another behavioral change on top of this one.

    An absent baseline is a first write and is allowed. A baseline that exists
    and will not parse is refused, because the comparison that would have caught
    a raise did not happen, and scoring that as nothing-to-compare would let a
    corrupted file launder a number the readable one refuses. Measured before the
    distinction existed: a baseline holding ``not json at all`` was overwritten
    with 16 at exit 0.
    """
    result = _scan_or_report(repo_root, adr_dir)
    if result is None:
        return EXIT_EXTERNAL
    _report_absent(result)
    if result.examined != result.candidates or not result.candidates:
        print(
            f"[{CHECK}] config: refusing to write a ceiling from a run that "
            f"examined {result.examined} of {result.candidates} tracked SKILL.md "
            "file(s). A ceiling measured from a partial tree is lower than the "
            "same commit scores in a full checkout, which makes every later full "
            "run a permanent regression against a number no tree ever held",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    counts = tally(result.violations)
    current = counts[CHECK]
    try:
        baseline_path.stat()
    except FileNotFoundError:
        present = False
    except OSError as exc:
        # `Path.exists()` swallows this and answers False, which would classify a
        # ceiling that is present but unreadable as "no ceiling" and allow the
        # write. Same fail-closed rule as the unparseable case below.
        print(
            f"[{CHECK}] config: baseline {baseline_path} could not be stat'd "
            f"({exc}), so whether it records a ceiling is unknown and the write "
            "was refused",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    else:
        present = True

    if present:
        recorded = read_baseline(baseline_path)
        if isinstance(recorded, str):
            # An unreadable ceiling is not "no ceiling". The comparison that
            # would have refused a raise could not happen, and treating that as
            # nothing-to-compare is the same shape as every other defect this
            # module fails closed on: it would let a corrupted baseline launder
            # a number the readable one refuses.
            print(
                f"[{CHECK}] config: {recorded}, so the ceiling it records could "
                "not be compared against the measured count and the write was "
                "refused. Repair the file, or delete it to record a first ceiling",
                file=sys.stderr,
            )
            return EXIT_CONFIG
        if current > recorded[CHECK]:
            print(
                f"[{CHECK}] config: --write-baseline would raise the ceiling from "
                f"{recorded[CHECK]} to {current}. The baseline may only fall. Fix "
                "the declaration instead",
                file=sys.stderr,
            )
            return EXIT_CONFIG

    write_baseline(baseline_path, counts)
    print(
        f"[{CHECK}] baseline written to {baseline_path}: {current}, measured "
        f"across {result.examined} of {result.candidates} tracked SKILL.md file(s)"
    )
    return EXIT_OK


def validate_skill_adr_bindings(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True when the count is at or below its baseline.

    A config error (exit 2) and an external fault (exit 3) both return False.
    A gate that cannot read its own baseline, or cannot list the files it is
    meant to scan, has not run, and reporting that as a pass is the silent-pass
    failure the repository's CI-script rules exist to stop.
    """
    return main(["--repo-root", str(repo_root)]) == EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
