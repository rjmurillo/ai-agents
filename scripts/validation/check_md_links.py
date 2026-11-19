#!/usr/bin/env python3
"""Detect relative markdown links whose target file or anchor does not exist.

Scope: tracked ``.md`` files under ``docs/``, under
``src/claude/skills/**/references/``, and every ``src/claude/skills/**/SKILL.md``.
Generated mirrors (``src/copilot-cli``, ``.claude``, and the rest) are outside
the scope, so a fix lands once, at the source.

Two finding kinds:

* ``missing-target``: the path is neither a tracked file nor a tracked directory.
* ``missing-anchor``: the target is a tracked markdown file with no heading slug
  or ``<a id>`` / ``<a name>`` anchor matching the ``#fragment``. Same-file
  fragments are skipped because markdownlint MD051 already checks them. Slugs
  come from :mod:`md_anchors`.

"Tracked" means the git index (``git ls-files``), so a target staged in the
same commit counts as present. Skipped destinations: external schemes,
``mailto:``, network-path and absolute ``/`` paths, empty destinations, and ADR
targets (``check_adr_links.py`` owns those).

Baseline: ``check_md_links_baseline.txt``, entries shaped
``<kind>:<file>:<target>`` like ``check_adr_links_baseline.txt``. The ``#`` that
starts a fragment is written ``%23`` there, because ``#`` opens a comment in the
shared baseline reader. An entry the base ref does not carry fails the run, and
a full-scope run fails on an entry that no longer matches a finding.

EXIT CODES:
  0 - no findings
  1 - at least one finding
  2 - configuration error (unreadable file, malformed baseline, empty scope)
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from check_adr_links import _run_git, base_allowances_for_run, is_adr_target  # noqa: E402
from md_anchors import anchors_in  # noqa: E402
from md_link_parse import (  # noqa: E402
    EXTERNAL_SCHEME_RE,
    LINK,
    _link_definitions,
    _live_lines,
    _reference_link_pairs,
    mask_inline_code,
    normalize_label,
    split_destination_fragment,
)
from stale_script_refs import load_allowlist  # noqa: E402

LABEL = "check_md_links"
DEFAULT_BASELINE = Path("scripts/validation/check_md_links_baseline.txt")
BASELINE_KINDS = frozenset({"missing-target", "missing-anchor"})
_LINE_FRAGMENT = re.compile(r"^L\d+(?:C\d+)?(?:-L\d+(?:C\d+)?)?$")
_SKILLS_ROOT = "src/claude/skills/"


@dataclass(frozen=True)
class Finding:
    """One broken relative link in a tracked markdown file."""

    file: str
    line: int
    kind: str
    target: str

    def key(self) -> str:
        """Return the line-independent baseline key, ``#`` written as ``%23``."""
        return f"{self.kind}:{self.file}:{self.target.replace('#', '%23')}"

    def format(self) -> str:
        """Return the ``path:line: kind: destination`` line."""
        return f"{self.file}:{self.line}: {self.kind}: {self.target}"


@dataclass(frozen=True)
class Inventory:
    """Tracked files, the directories that contain them, and tracked symlinks."""

    files: frozenset[str]
    dirs: frozenset[str]
    symlinks: dict[str, str]

    def known(self, path: str) -> bool:
        """Return whether ``path`` is a tracked file or directory."""
        return path in self.files or path in self.dirs

    def follow_symlinks(self, path: str) -> str:
        """Return ``path`` with each tracked-symlink prefix replaced by its target.

        ``.claude/skills/<name>`` is a tracked symlink to ``src/claude/skills/<name>``
        (ADR-119), so a link written through it names a file the index only
        lists under the real path. Bounded so a symlink cycle cannot loop.
        """
        for _ in range(8):
            parts = path.split("/")
            for i in range(1, len(parts) + 1):
                prefix = "/".join(parts[:i])
                target = self.symlinks.get(prefix)
                if target is None:
                    continue
                joined = posixpath.normpath(posixpath.join(posixpath.dirname(prefix), target))
                path = "/".join([joined, *parts[i:]])
                break
            else:
                return path
        return path


@dataclass
class Tally:
    """Findings plus how many fragment links were examined."""

    findings: list[Finding]
    fragments_checked: int = 0


def in_scope(path: str) -> bool:
    """Return whether a repo-relative path is a markdown file this gate checks."""
    if not path.endswith(".md"):
        return False
    if path.startswith("docs/"):
        return True
    if not path.startswith(_SKILLS_ROOT):
        return False
    return path.endswith("/SKILL.md") or "/references/" in path


def tracked_inventory(repo_root: Path) -> Inventory:
    """Read the git index. Raises ValueError on a path that did not decode."""
    result = _run_git(repo_root, ["ls-files", "-s", "-z"])
    if result.returncode != 0:
        raise ValueError(f"git ls-files failed: {result.stderr.strip() or result.returncode}")
    files: set[str] = set()
    symlinks: dict[str, str] = {}
    for entry in result.stdout.split("\0"):
        meta, _, name = entry.partition("\t")
        if not name:
            continue
        name = name.replace("\\", "/")
        files.add(name)
        if meta.startswith("120000"):
            try:
                symlinks[name] = (repo_root / name).readlink().as_posix()
            except OSError:
                continue
    corrupted = sorted(f for f in files if "\ufffd" in f)
    if corrupted:
        raise ValueError(f"tracked path(s) with undecodable bytes: {', '.join(corrupted)}")
    dirs = {"."}
    for path in files:
        parent = posixpath.dirname(path)
        while parent and parent not in dirs:
            dirs.add(parent)
            parent = posixpath.dirname(parent)
    return Inventory(frozenset(files), frozenset(dirs), symlinks)


def _skip_path(path: str) -> bool:
    """Return whether a link path is outside what this gate resolves."""
    if not path or path.startswith("/") or EXTERNAL_SCHEME_RE.match(path):
        return True
    return bool(is_adr_target(path))


class _Scanner:
    """Scans files against one inventory, caching each target's anchors."""

    def __init__(self, repo_root: Path, inventory: Inventory) -> None:
        self._root = repo_root
        self._inventory = inventory
        self._anchors: dict[str, set[str]] = {}

    def _anchors_of(self, target: str) -> set[str]:
        if target not in self._anchors:
            body = (self._root / target).read_text(encoding="utf-8", errors="replace")
            self._anchors[target] = anchors_in(body)
        return self._anchors[target]

    def check_link(self, file: str, line: int, dest: str, tally: Tally) -> None:
        """Judge one destination and append any finding to ``tally``."""
        raw_path, fragment = split_destination_fragment(dest)
        path = unquote(raw_path.split("?", 1)[0])
        if _skip_path(path):
            return
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(file), path))
        escaped = resolved == ".." or resolved.startswith("../")
        if not escaped and not self._inventory.known(resolved):
            resolved = self._inventory.follow_symlinks(resolved)
        if escaped or not self._inventory.known(resolved):
            tally.findings.append(
                Finding(file, line, "missing-target", dest_label(raw_path, fragment))
            )
            return
        self._check_fragment(file, line, resolved, raw_path, unquote(fragment), tally)

    def _check_fragment(
        self, file: str, line: int, resolved: str, raw_path: str, fragment: str, tally: Tally
    ) -> None:
        if not fragment or _LINE_FRAGMENT.match(fragment):
            return
        if resolved == file or not resolved.lower().endswith(".md"):
            return
        if resolved not in self._inventory.files or not (self._root / resolved).is_file():
            return
        tally.fragments_checked += 1
        if fragment not in self._anchors_of(resolved):
            tally.findings.append(
                Finding(file, line, "missing-anchor", dest_label(raw_path, fragment))
            )

    def scan_file(self, file: str, tally: Tally) -> None:
        """Check every inline and reference-style link in one file."""
        path = self._root / file
        if not path.is_file():
            return
        live = [
            (n, mask_inline_code(text)) for n, text in _live_lines(path.read_text(encoding="utf-8"))
        ]
        definitions = _link_definitions(live)
        for number, line in live:
            for match in LINK.finditer(line):
                dest = match.group("dest")
                if "[" not in dest and "]" not in dest:
                    self.check_link(file, number, dest, tally)
            for _, label in _reference_link_pairs(line):
                dest = definitions.get(normalize_label(label))
                if dest is not None:
                    self.check_link(file, number, dest, tally)


def dest_label(path: str, fragment: str) -> str:
    """Return the destination as written, ``path#fragment`` when it has one."""
    return f"{path}#{fragment}" if fragment else path


def malformed_baseline_entries(entries: set[str]) -> list[str]:
    """Return entries not shaped ``<kind>:<file>:<target>`` with a known kind."""
    bad = []
    for entry in sorted(entries):
        parts = entry.split(":", 2)
        if len(parts) != 3 or parts[0] not in BASELINE_KINDS or not parts[1] or not parts[2]:
            bad.append(entry)
    return bad


def validate_baseline(allowed: set[str], base_allowances: set[str] | None) -> None:
    """Raise ValueError when the baseline is malformed or the branch widened it."""
    bad = malformed_baseline_entries(allowed)
    if bad:
        listed = "\n  ".join(bad)
        raise ValueError(
            f"{LABEL} baseline has {len(bad)} entry(ies) not shaped "
            f"<kind>:<file>:<target> with kind in {sorted(BASELINE_KINDS)}:\n  {listed}"
        )
    if base_allowances is None:
        return
    added = sorted(allowed - base_allowances)
    if added:
        listed = "\n  ".join(added)
        raise ValueError(
            f"{LABEL} baseline has {len(added)} entry(ies) this branch added that the "
            f"base ref does not carry. A baseline records a pre-existing defect; it "
            f"must not clear one this change introduced. Fix the link instead:\n  {listed}"
        )


def find_broken_md_links(
    repo_root: Path,
    *,
    files: list[str] | None = None,
    baseline: set[str] | None = None,
    base_allowances: set[str] | None = None,
    inventory: Inventory | None = None,
) -> tuple[list[Finding], int, int]:
    """Return ``(findings, files_examined, fragment_links_checked)``.

    ``files`` narrows the scan to those paths (staged mode), filtered to scope.
    The inventory always covers the whole index so targets resolve fully.
    A full-scope run also reports baseline entries that matched nothing.
    """
    inv = inventory if inventory is not None else tracked_inventory(repo_root)
    allowed = baseline if baseline is not None else load_allowlist(repo_root / DEFAULT_BASELINE)
    validate_baseline(allowed, base_allowances)
    candidates = sorted(p for p in (files if files is not None else inv.files) if in_scope(p))
    scanner = _Scanner(repo_root, inv)
    tally = Tally([])
    for file in candidates:
        scanner.scan_file(file, tally)

    remaining = set(allowed)
    findings: list[Finding] = []
    for finding in tally.findings:
        if finding.key() in remaining:
            remaining.discard(finding.key())
        else:
            findings.append(finding)
    if files is None:
        for key in sorted(remaining):
            kind, file, target = key.split(":", 2)
            findings.append(Finding(file, 0, "stale-allowance", f"{kind} {target}"))
    return findings, len(candidates), tally.fragments_checked


def _report(findings: list[Finding], examined: int, fragments: int) -> None:
    for finding in findings:
        print(finding.format())
    print(
        f"{LABEL}: {len(findings)} violation(s) across {examined} markdown file(s); "
        f"{fragments} fragment link(s) checked"
    )


def run(repo_root: Path, files: list[str] | None, base_ref: str, baseline_path: Path) -> int:
    """Run one check and return the exit code (0 ok, 1 findings, 2 config)."""
    try:
        allowed = load_allowlist(baseline_path)
        base = base_allowances_for_run(repo_root, baseline_path, base_ref, label=LABEL)
        findings, examined, fragments = find_broken_md_links(
            repo_root, files=files, baseline=allowed, base_allowances=base
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as exc:
        print(f"{LABEL}: {exc}", file=sys.stderr)
        return 2
    if examined == 0 and files is None:
        print(f"{LABEL}: no in-scope markdown found under {repo_root}", file=sys.stderr)
        return 2
    _report(findings, examined, fragments)
    return 1 if findings else 0


def validate_md_links(repo_root: Path, base_ref: str = "auto") -> bool:
    """Full-scope entry point for ``pre_pr``: print findings, return True when clean."""
    return run(repo_root, None, base_ref, repo_root / DEFAULT_BASELINE) == 0


def validate_staged_md_links(repo_root: Path, files: list[str], base_ref: str = "auto") -> bool:
    """Staged-file entry point for the pre-commit markdown check."""
    normalized = [f.replace("\\", "/") for f in files]
    return run(repo_root, normalized, base_ref, repo_root / DEFAULT_BASELINE) == 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Detect broken relative markdown links.")
    parser.add_argument("files", nargs="*", help="Staged files; omit for the full scope.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="Baseline file.")
    parser.add_argument(
        "--base-ref",
        default="auto",
        help="Ref whose baseline copy this run may not add to; 'none' disables.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the markdown link check."""
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    baseline = Path(args.baseline)
    baseline = baseline if baseline.is_absolute() else repo_root / baseline
    files = [f.replace("\\", "/") for f in args.files] if args.files else None
    return run(repo_root, files, args.base_ref, baseline)


if __name__ == "__main__":
    raise SystemExit(main())
