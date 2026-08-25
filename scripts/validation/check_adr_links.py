#!/usr/bin/env python3
# taste-lint: ignore file-size. A large share of the lines are comments and
# docstrings: the four-violation-class module docstring, the per-function
# rationale for each detection rule, the RFC 3986 section 3.1/4.2 citations
# backing is_adr_target()'s scheme and network-path checks (PR #5209 round-8
# review), the CommonMark citations backing fence, reference-link, and label
# normalization behavior, and the three-way baseline-ratchet rationale
# (shape, provenance, staleness). Logic alone is well under the ceiling; a split
# would move prose between files rather than reduce anything. (Deliberately
# no exact line count here: an earlier version cited "243 of the 537 lines"
# and it went stale twice in the two review rounds right after it was
# written, Copilot, PR #5209 round-10 review.)
r"""Detect ADR markdown links that do not resolve or that name the wrong ADR number.

Scans tracked markdown files for links whose target matches ``ADR-\d+.*\.md`` and
reports four violation classes. Both CommonMark link syntaxes are in scope: the
inline form (``[text](dest)``) and the reference form (``[text][label]``,
``[text][]``, or a bare ``[label]``) resolved through the file's
``[label]: dest`` definitions. Judging only the inline form let an unresolved
or wrong-numbered reference-style link past this gate entirely (PR #5209
review).

The violation classes:

``unresolved``
    The target is not a tracked file when resolved relative to the file
    containing the link. Catches stale slugs left behind by an ADR rename, for
    example ``ADR-005-powershell-only.md`` after the file became
    ``ADR-005-powershell-only-scripting.md``. Resolution is against
    ``git ls-files``, not the filesystem: an untracked file at the target path
    must not make a broken tracked link pass locally when the same commit
    fails in a clean checkout (PR #5209 review).

``absolute``
    The target starts with ``/``. A leading slash cannot resolve relative to the
    containing file, and GitHub resolves it against the site root rather than the
    blob tree, so the link renders broken. ``ADR-023`` cited its debate log as
    ``/.agents/critique/ADR-023-debate-log.md`` while the file was present all
    along at ``.agents/critique/ADR-023-debate-log.md``.

``number-mismatch``
    The link text names an ADR number and the target filename names a different
    one. This is the rule no existing gate carries. ``ADR-033`` linked
    ``[ADR-032 Exit Code Standardization](./ADR-032-exit-code-standardization.md)``
    when exit-code standardization is ADR-035 and ADR-032 is EARS requirements
    syntax, so a reader who ignored the dead path and followed the number landed
    on an unrelated decision.

``malformed``
    The link destination carries a nested ``[`` or ``]``, or the destination is
    never closed on its line (``[ADR-080](./ADR-080-model-pin-justification-policy.md``).
    A distinct authoring mistake from a target that simply does not exist.

Scope is tracked ``*.md`` files. Non-markdown files are never scanned, so the
deliberate ``ADR-999`` / ``ADR-099`` / ``ADR-100`` / ``ADR-101`` / ``ADR-102``
constants in the Python test fixtures named by issue #5197 are out of scope by
construction rather than by allowlist entry.

Links inside fenced code blocks are illustrations, not references, and are
skipped. A ``[label]: dest`` definition inside a fence defines nothing, for the
same reason.

``scripts/validation/check_adr_links_baseline.txt`` records pre-existing
defects. It is a ratchet in three directions, all enforced rather than merely
documented: an entry must be shaped ``<kind>:<file>:<target>`` (a bare filename
is not a wildcard for the file), an entry must already exist in the baseline at
the base ref (a branch cannot clear a defect it just introduced), and on a
full-corpus scan every entry must match a live finding (a repaired link's entry
must be deleted, not left to suppress a future regression).

Exit codes follow ADR-035: 0 clean, 1 violations found, 2 configuration error.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# HISTORICAL_ROOTS and load_allowlist are reused, not copied, so a root added to
# the stale-script-ref exemption list is honoured here without a second edit.
# scripts/validation/stale_script_refs.py:14-27 defines HISTORICAL_ROOTS as a
# tuple of path prefixes; :89-99 defines load_allowlist as a comment-stripping
# line reader returning a set of normalized strings.
from stale_script_refs import HISTORICAL_ROOTS, load_allowlist  # noqa: E402

DEFAULT_BASELINE = Path("scripts/validation/check_adr_links_baseline.txt")

# CommonMark caps fence indentation at three spaces
# (spec.commonmark.org/0.31.2/#fenced-code-blocks, quoted verbatim): a fenced
# code block "begins with a code fence, preceded by up to three spaces of
# indentation", and the spec's own example 134 states "Four spaces of
# indentation is too many". `\s*` (unbounded, and matching tabs) previously
# let a four-space-indented ``` ` ``` ` line put the scanner into fence
# mode, hiding a broken ADR link in the live prose that followed, since
# CommonMark treats that line as indented-code content, not a fence opener
# (Copilot, PR #5209 round-10 review).
FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
LINK = re.compile(r"\[(?P<text>[^\[\]\n]*)\]\((?P<dest>[^()\n]*)\)")
UNTERMINATED = re.compile(r"\[(?P<text>[^\[\]\n]*)\]\((?P<dest>[^()\n]*)$")

# CommonMark reference links (spec.commonmark.org/0.31.2/#reference-link) are
# real links this scanner could not see at all: ``[ADR-005][decision]`` with a
# ``[decision]: ./ADR-006-wrong.md`` definition elsewhere in the same file
# carries a link text naming one ADR and a destination naming another, yet
# ``LINK`` matches only the inline ``[text](dest)`` form, so neither the
# unresolved target nor the number mismatch reached any rule and the whole
# syntax passed the repo-wide gate (Copilot, PR #5209 round-11 review).
#
# LINK_DEFINITION matches a link reference definition, which the spec allows up
# to three spaces of indentation exactly as it allows for a fence.
# REFERENCE_LINK matches the full (``[text][label]``) and collapsed
# (``[text][]``) forms; an empty label means the text is the label
# (spec.commonmark.org/0.31.2/#collapsed-reference-link). SHORTCUT_LINK matches
# the shortcut form (``[label]``), which the spec makes a link only when the
# bracket content is itself a defined label, so it is resolved against the
# collected definitions rather than treated as a link on sight; the negative
# lookahead keeps it off an inline link's ``(``, off a full reference's second
# bracket, and off a definition's own ``:``.
LINK_DEFINITION = re.compile(r"^ {0,3}\[(?P<label>[^\[\]\n]+)\]:\s*(?P<dest>.*)$")
REFERENCE_LINK = re.compile(r"\[(?P<text>[^\[\]\n]*)\]\[(?P<label>[^\[\]\n]*)\]")
SHORTCUT_LINK = re.compile(r"\[(?P<text>[^\[\]\n]+)\](?![\[(:])")
ADR_BASENAME = re.compile(r"^ADR-\d+.*\.md$", re.IGNORECASE)
ADR_ANYWHERE = re.compile(r"ADR-\d+[^\s)]*\.md", re.IGNORECASE)
TEXT_ADR_NUMBER = re.compile(r"\bADR[-\s]?(?P<number>\d{1,4})\b", re.IGNORECASE)
FILE_ADR_NUMBER = re.compile(r"^ADR-(?P<number>\d+)", re.IGNORECASE)

# RFC 3986 section 3.1's ABNF, quoted verbatim (rfc-editor.org/rfc/rfc3986#section-3.1):
#   scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )
# A colon-terminated scheme this shape, not a fixed enumeration, marks a
# destination as external: enumerating http/https/mailto/ftp missed ssh://,
# git://, and every other valid scheme, so a link like
# "ssh://host/ADR-005-x.md" reached ADR_BASENAME and was reported as a false
# "unresolved" repository-relative target instead of being recognized as
# external (Copilot, PR #5209 round-8 review).
EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

# The four violation classes a baseline entry can name. Mirrors the literal
# strings passed to Finding(kind=...) below (search this file for
# 'Finding(' to confirm the set stays exhaustive as classes are added).
# "stale-allowance" (see find_broken_adr_links) is deliberately excluded: a
# stale-allowance finding reports that a baseline entry is unused, so a
# baseline entry cannot itself allow one without defeating its own purpose.
BASELINE_KINDS = frozenset({"unresolved", "absolute", "malformed", "number-mismatch"})


@dataclass(frozen=True)
class Finding:
    """One broken or misleading ADR link in a tracked markdown file."""

    file: str
    line: int
    kind: str
    target: str
    detail: str = ""

    def key(self) -> str:
        """Return the line-independent baseline key for this finding.

        Includes ``kind``: a key of bare ``file:target`` conflates every
        violation class that can name the same (file, target) pair. An
        existing ``unresolved`` allowance for one link would also hide a
        newly introduced ``number-mismatch`` on the identical file and
        target if only the link text's cited number changed, since that new
        finding shares the same file and target as the baselined one (PR
        #5209 review, discussion_r3831835196). Verified against the live
        corpus: 2 of this baseline's 19 entries are ``absolute``, not
        ``unresolved``, so the conflation was not hypothetical. (Re-measured
        after the round-5 fix removed a stale ``absolute`` entry; the prior
        20/3 figures went stale one round before this comment was corrected
        to match, Copilot, PR #5209 round-6 review.)
        """
        return f"{self.kind}:{self.file}:{self.target}"

    def format(self) -> str:
        """Return the human and machine readable finding line."""
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.file}:{self.line}: {self.kind}: {self.target}{suffix}"


def is_historical_path(path: str) -> bool:
    """Return whether path sits in a history-only root that is never repaired."""
    return path.startswith(HISTORICAL_ROOTS)


def git_ls_markdown(repo_root: Path) -> list[str]:
    """Return tracked markdown paths, newest-git-state, normalized to forward slashes.

    ``errors="replace"`` on the subprocess decode is not a shortcut: it is the
    mandatory convention ``scripts/validation/check_subprocess_encoding.py``
    gates every ``subprocess.run(text=True, encoding="utf-8", ...)`` call
    against (issue #4261). That gate's own failure message states the reason
    verbatim: "a child process on Windows can emit bytes invalid for UTF-8"
    and "Without errors='replace', the decode raises before the caller can
    report the real failure." Removing it here to make a bad-encoding path
    raise, as a reviewer suggested (Copilot, PR #5209), would fix this one
    caller's silent-skip while reintroducing the exact crash-before-report
    failure mode issue #4261 was filed to eliminate repo-wide, and would fail
    the "Subprocess Encoding Convention" pre-PR gate.

    So the replacement stays, and the silent-skip is closed a different way:
    a tracked path that decoded with the U+FFFD replacement character is
    exactly the input this convention exists to tolerate at the subprocess
    boundary without crashing, but passing it on unnoticed is how it becomes
    silent instead of merely tolerated. `scan_file()` builds
    ``repo_root / file`` from this list and returns ``[]`` at its
    ``path.is_file()`` guard when the result is not a real file, so a
    replacement-corrupted entry does not fail loudly there either: it looks
    like a file that does not exist and is
    scanned as zero findings, indistinguishable from a file that was never
    tracked (Copilot, PR #5209 round-6 review). Raising here, once, with the
    corrupted name visible, is the fail-loud path issue #4261 asks the
    subprocess call itself not to take.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )
    entries = sorted(entry.replace("\\", "/") for entry in result.stdout.split("\0") if entry)
    corrupted = [entry for entry in entries if "�" in entry]
    if corrupted:
        listed = "\n  ".join(corrupted)
        raise ValueError(
            f"git ls-files returned {len(corrupted)} markdown path(s) with a "
            f"non-UTF-8 byte replaced by U+FFFD, so this tool cannot resolve "
            f"them to real files and cannot scan them for broken ADR links:\n"
            f"  {listed}"
        )
    return entries


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one git command under ``repo_root`` and return the completed process."""
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )


def resolve_base_ref(repo_root: Path) -> str | None:
    """Return the first base ref that resolves locally, or None.

    A narrowed, offline-safe version of
    ``scripts/validation/checks_common.py``'s ``_resolve_default_base_ref``
    (:356-385), whose candidate order this mirrors from its third candidate
    on: that function's list, quoted from its own body, is
    ``candidates += ["refs/remotes/origin/HEAD", "origin/main", "main"]``
    after an optional ``gh pr view`` probe.

    Stricter/looser/different than canonical: the ``gh pr view`` probe is
    dropped. This gate runs inside ``pre_pr.py`` on every push and inside a
    pre-commit hook, where a network round-trip per run is not worth the
    precision, and the remaining three candidates already resolve to the
    default branch in every checkout that has one. Returning ``None`` when
    none resolve matches the canonical function exactly.
    """
    for ref in ("refs/remotes/origin/HEAD", "origin/main", "main"):
        if _run_git(repo_root, ["rev-parse", "--verify", "--quiet", ref]).returncode == 0:
            return ref
    return None


def _merge_base(repo_root: Path, base_ref: str) -> str:
    """Return the merge base of HEAD and ``base_ref``, or ``base_ref`` itself.

    Comparing against the merge base, not the ref tip, is what
    ``scripts/validation/memory_index.py`` (:491-505) does for the same
    reason: once the base branch advances past the point this branch forked
    from, its tip carries entries this branch never saw, and every one of
    them would read as an entry this branch is missing rather than one it
    added.
    """
    result = _run_git(repo_root, ["merge-base", "HEAD", base_ref])
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else base_ref


def _parse_allowlist(text: str) -> set[str]:
    """Parse baseline text into entries, mirroring ``load_allowlist``'s reader.

    ``stale_script_refs.load_allowlist`` (:90-101) is reused, not copied,
    everywhere a baseline is read from a path. It cannot be reused here
    because the text comes from ``git show``, not from disk, so its loop
    body is mirrored instead. Quoted verbatim from that function:

        for line in path.read_text(encoding="utf-8").splitlines():
            clean = line.split("#", 1)[0].strip()
            if clean:
                entries.add(clean.replace("\\\\", "/"))

    Keep the two in step: a parser that strips comments differently than the
    on-disk reader would report entries as branch-added that are not.
    """
    entries: set[str] = set()
    for line in text.splitlines():
        clean = line.split("#", 1)[0].strip()
        if clean:
            entries.add(clean.replace("\\", "/"))
    return entries


def baseline_entries_at_ref(repo_root: Path, base_ref: str, baseline_path: Path) -> set[str] | None:
    """Return the baseline's entries as recorded at ``base_ref``.

    ``None`` means the baseline file does not exist at that revision, which
    is the branch that introduces the baseline itself: there is no prior
    exemption set to ratchet against, so the caller skips the provenance
    check and says so. Existence is probed with ``git cat-file -e`` so that
    "absent at the base ref" stays distinguishable from "present but
    unreadable"; the second raises, because a baseline this gate cannot read
    is a configuration error, not a licence to skip the check.
    """
    try:
        relative = baseline_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        raise ValueError(
            f"baseline {baseline_path} is outside the repository root {repo_root}, "
            f"so it cannot be read at {base_ref}"
        ) from None

    revision = _merge_base(repo_root, base_ref)
    if _run_git(repo_root, ["cat-file", "-e", f"{revision}:{relative}"]).returncode != 0:
        return None
    result = _run_git(repo_root, ["show", f"{revision}:{relative}"])
    if result.returncode != 0:
        detail = result.stderr.strip() or "git show failed"
        raise ValueError(f"could not read {relative} at {base_ref}: {detail}")
    return _parse_allowlist(result.stdout)


def base_allowances_for_run(
    repo_root: Path, baseline_path: Path, base_ref: str = "auto"
) -> set[str] | None:
    """Return the base-ref baseline entries to ratchet this run against.

    ``base_ref`` of ``"auto"`` resolves one locally; ``"none"`` disables the
    provenance check outright. ``None`` comes back, with a line on stderr
    naming which case it was, when no ratchet is possible: no base ref
    resolves (a fresh clone with no remote, a repository with no default
    branch), or the baseline does not exist yet at the base ref. Both are
    silent-pass shapes, so neither is left silent.
    """
    if base_ref == "none":
        return None
    if base_ref == "auto":
        resolved = resolve_base_ref(repo_root)
        if resolved is None:
            print(
                "check_adr_links: no base ref resolved (refs/remotes/origin/HEAD, "
                "origin/main, main), so baseline additions are not ratcheted this run",
                file=sys.stderr,
            )
            return None
        base_ref = resolved

    entries = baseline_entries_at_ref(repo_root, base_ref, baseline_path)
    if entries is None:
        print(
            f"check_adr_links: {baseline_path.name} does not exist at {base_ref}, so "
            f"baseline additions are not ratcheted this run",
            file=sys.stderr,
        )
    return entries


def split_destination(raw: str) -> str:
    """Return the path part of a markdown link destination.

    Drops an optional ``"title"`` suffix, surrounding angle brackets, and any
    ``#anchor``. Returns an empty string when nothing path-like remains.

    The angle-bracket form is closed by its own ``>``, not by the end of the
    string: ``[ADR-005](<./ADR-005-x.md> "Title")`` is valid CommonMark (a
    pointy-bracket destination followed by a title), but ``dest`` here also
    carries that trailing title text, so ``dest.endswith(">")`` was false and
    the brackets were never stripped. The unstripped ``<./ADR-005-x.md>``
    then failed ``is_adr_target()``'s ``ADR_BASENAME`` match (its basename
    ends in ``>``, not ``.md``), so a broken or wrong-numbered link written
    with this legal syntax was silently treated as a non-ADR destination and
    never checked (Copilot, PR #5209 round-10 review). Finding the closing
    ``>`` explicitly, rather than requiring it to be the last character,
    fixes both the bracket-only and bracket-plus-title forms.
    """
    dest = raw.strip()
    if dest.startswith("<"):
        end = dest.find(">")
        if end != -1:
            dest = dest[1:end].strip()
    if not dest:
        return ""
    path = dest.split()[0]
    return path.split("#", 1)[0]


def is_adr_target(path: str) -> bool:
    """Return whether a link destination points at an ADR markdown file.

    External detection matches the RFC 3986 scheme shape (``EXTERNAL_SCHEME_RE``)
    rather than enumerating specific schemes: an earlier version listed only
    ``http://``, ``https://``, ``mailto:``, and ``ftp://``, so a destination
    like ``ssh://host/ADR-005-x.md`` or ``git://host/ADR-005-x.md`` fell
    through to the ADR-basename check below and was reported as an
    ``unresolved`` repository-relative target: a false positive with no
    repository fix available, since the target is genuinely external
    (Copilot, PR #5209 round-8 review). The scheme regex's character class
    already covers both cases, so ``HTTPS://example.test/ADR-005-x.md``
    matches the same as its lowercase spelling without a separate
    ``.lower()`` call.

    A network-path reference (``//host/ADR-005-x.md``, RFC 3986 section 4.2:
    "A relative reference that begins with two slash characters is termed a
    network-path reference") is external for the same reason a scheme is: it
    names a host, not a path in this repository. It is checked before the
    scheme regex because it carries no scheme of its own.
    """
    if not path or path.startswith("//") or EXTERNAL_SCHEME_RE.match(path):
        return False
    basename = path.rsplit("/", 1)[-1]
    return bool(ADR_BASENAME.match(basename))


def adr_number(value: str) -> int | None:
    """Return the leading ADR number in an ADR filename, or None."""
    match = FILE_ADR_NUMBER.match(value)
    return int(match.group("number")) if match else None


def text_adr_number(text: str) -> int | None:
    """Return the first ADR number named in link text, or None."""
    match = TEXT_ADR_NUMBER.search(text)
    return int(match.group("number")) if match else None


def normalize_label(label: str) -> str:
    """Return a CommonMark-normalized link label.

    The spec's normalization rule, quoted verbatim
    (spec.commonmark.org/0.31.2/#matches): "To normalize a label, strip off
    the opening and closing brackets, perform the Unicode case fold, strip
    leading and trailing spaces, tabs, and line endings, and collapse
    consecutive internal spaces, tabs, and line endings to a single space."
    ``str.split()`` with no argument does the strip-and-collapse half over
    exactly that whitespace set, and ``str.casefold()`` is Python's Unicode
    case fold, so ``[Decision]`` and ``[  decision ]`` resolve to the one
    definition a Markdown renderer would give them.
    """
    return " ".join(label.split()).casefold()


def _malformed_findings(file: str, line_number: int, line: str) -> list[Finding]:
    """Return malformed-destination findings for one line."""
    findings: list[Finding] = []
    for match in LINK.finditer(line):
        dest = match.group("dest")
        if ("[" in dest or "]" in dest) and ADR_ANYWHERE.search(dest):
            findings.append(
                Finding(file, line_number, "malformed", dest.strip(), "bracket inside destination")
            )

    unterminated = UNTERMINATED.search(line)
    if unterminated and ADR_ANYWHERE.search(unterminated.group("dest")):
        findings.append(
            Finding(
                file,
                line_number,
                "malformed",
                unterminated.group("dest").strip(),
                "destination never closed",
            )
        )
    return findings


def _malformed_baseline_entries(entries: set[str]) -> list[str]:
    """Return every entry not shaped ``<kind>:<file>:<target>``.

    The baseline file's own header requires this exact shape and forbids a
    looser one, but nothing enforced it: a bare filename such as
    ``some/file.md`` matched every finding in that file through a
    ``finding.file in allowed`` branch this gate used to carry, making one
    line a silent, unbounded wildcard for every current and future ADR-link
    defect anywhere in that file rather than the one defect it was meant to
    record (Copilot, PR #5209). Validating the shape at load time turns a
    malformed or over-broad entry into a loud config error instead of a
    silent exemption.

    ``split(":", 2)`` caps the split at two colons so a target containing one
    (unlikely for a repo-relative path, but not forbidden) stays intact in
    the third field rather than being cut.
    """
    malformed = []
    for entry in sorted(entries):
        parts = entry.split(":", 2)
        if len(parts) != 3 or parts[0] not in BASELINE_KINDS or not parts[1] or not parts[2]:
            malformed.append(entry)
    return malformed


def _resolves_to_tracked_file(file: str, path: str, tracked: frozenset[str]) -> bool:
    """Return whether ``path``, taken relative to ``file``, names a tracked file.

    Resolution is purely lexical against the ``git ls-files`` inventory
    (``tracked``), never against the working-tree filesystem. An untracked
    file sitting at the target path would make ``Path.exists()`` pass locally
    for a link that is broken in a clean checkout, and the identical commit
    would then fail in CI while looking clean on the author's machine.

    ``posixpath.normpath`` collapses ``..`` segments without touching disk,
    matching the forward-slash-normalized paths ``git_ls_markdown`` returns.
    A result of ``..`` or one starting with ``../`` has walked out of the
    repository root and is rejected outright, since nothing under
    ``git ls-files`` can ever resolve there.
    """
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(file), path))
    if resolved == ".." or resolved.startswith("../"):
        return False
    return resolved in tracked


def _target_findings(
    file: str, line_number: int, text: str, path: str, tracked: frozenset[str]
) -> list[Finding]:
    """Return the number-mismatch, absolute, and unresolved findings for one link.

    Shared by the inline (``[text](dest)``) and reference
    (``[text][label]``) paths so both syntaxes are judged by one set of
    rules. Splitting the rules per syntax is how reference links reached the
    gate with none of them applied in the first place (Copilot, PR #5209
    round-11 review).
    """
    findings: list[Finding] = []

    # The number check runs whether or not the path resolves. A dead path and
    # a wrong number are separate defects, and reporting only the dead path
    # would surface the wrong number one review round later.
    named = text_adr_number(text)
    actual = adr_number(path.rsplit("/", 1)[-1])
    if named is not None and actual is not None and named != actual:
        findings.append(
            Finding(
                file,
                line_number,
                "number-mismatch",
                path,
                f"text says ADR-{named:03d}, target is ADR-{actual:03d}",
            )
        )

    if path.startswith("/"):
        findings.append(
            Finding(file, line_number, "absolute", path, "does not resolve from this file")
        )
    elif not _resolves_to_tracked_file(file, path, tracked):
        findings.append(Finding(file, line_number, "unresolved", path))

    return findings


def _link_findings(
    file: str, line_number: int, line: str, tracked: frozenset[str]
) -> list[Finding]:
    """Return unresolved, absolute, and number-mismatch findings for one line."""
    findings: list[Finding] = []

    for match in LINK.finditer(line):
        dest = match.group("dest")
        if "[" in dest or "]" in dest:
            continue
        path = split_destination(dest)
        if not is_adr_target(path):
            continue
        findings.extend(_target_findings(file, line_number, match.group("text"), path, tracked))

    return findings


def _link_definitions(lines: list[tuple[int, str]]) -> dict[str, str]:
    """Return the file's link reference definitions, normalized label to destination.

    Collected over the whole file before any line is scanned, because
    CommonMark places no ordering constraint between a reference and its
    definition: ``[ADR-005][decision]`` on line 3 is a link to whatever
    ``[decision]:`` names on line 300.

    ``setdefault`` keeps the first definition of a reused label, per the
    spec (spec.commonmark.org/0.31.2/#link-reference-definition, quoted
    verbatim): "If there are several matching definitions, the first one
    takes precedence."

    A label that normalizes to nothing is not a label, per the spec
    (spec.commonmark.org/0.31.2/#link-label, quoted verbatim): "A link label
    must contain at least one character that is not a space, tab, or line
    ending." Dropping it here is the only place that needs to know: an
    empty-normalizing label can then never be a key, so a task-list checkbox
    (``- [ ] item``) looks up nothing and a second guard at the lookup would
    be unreachable noise.
    """
    definitions: dict[str, str] = {}
    for _, line in lines:
        match = LINK_DEFINITION.match(line)
        if not match:
            continue
        label = normalize_label(match.group("label"))
        if label:
            definitions.setdefault(label, match.group("dest"))
    return definitions


def _reference_link_pairs(line: str) -> list[tuple[str, str]]:
    """Return ``(link text, label)`` for every reference-style link on one line.

    Covers the three reference forms CommonMark defines: full
    (``[text][label]``), collapsed (``[text][]``, where the text is the
    label), and shortcut (``[label]``). A shortcut match that falls inside a
    full reference's span is that reference's second bracket, not a link of
    its own, so it is dropped; ``SHORTCUT_LINK``'s lookahead already keeps
    the first bracket of a full reference and of an inline link out.

    Whether a pair is actually a link is decided by the caller, against the
    file's definitions: an undefined label renders as literal text, not a
    link, so it must not produce a finding.
    """
    pairs: list[tuple[str, str]] = []
    spans: list[tuple[int, int]] = []
    for match in REFERENCE_LINK.finditer(line):
        text = match.group("text")
        pairs.append((text, match.group("label") or text))
        spans.append(match.span())
    for match in SHORTCUT_LINK.finditer(line):
        if any(start <= match.start() < end for start, end in spans):
            continue
        pairs.append((match.group("text"), match.group("text")))
    return pairs


def _reference_link_findings(
    file: str,
    line_number: int,
    line: str,
    definitions: dict[str, str],
    tracked: frozenset[str],
) -> list[Finding]:
    """Return findings for reference-style links on one line.

    Reported at the line of the reference, not of the definition: that is
    the line a reader follows and the line an author edits.

    A definition whose destination is never referenced produces nothing. A
    renderer drops an unreferenced definition from the output entirely, so
    its destination is not a link that can be broken.
    """
    findings: list[Finding] = []
    for text, label in _reference_link_pairs(line):
        dest = definitions.get(normalize_label(label))
        if dest is None:
            continue
        path = split_destination(dest)
        if not is_adr_target(path):
            continue
        findings.extend(_target_findings(file, line_number, text, path, tracked))
    return findings


def _live_lines(body: str) -> list[tuple[int, str]]:
    """Return ``(line number, text)`` for every line outside a fenced code block.

    Fence tracking keys on the opening marker's character AND run length, not
    a bare open/closed toggle. CommonMark closes a fence only with the same
    character it opened with, in a run at least as long as the opening one
    (spec.commonmark.org section 4.5): a ```` ```` ```` (four-backtick) block
    containing a three-backtick line (a shell transcript showing a ` ``` `
    example, say) is not closed by that shorter run, and a bare open/closed
    toggle would resume scanning that fenced example content as live prose one
    fence early, or the reverse for a ``~~~`` block containing a backtick
    example. ``FENCE`` captures the whole run (``` `{3,}` ``` or ``~{3,}``),
    and a fence-shaped line closes the block only when all three hold: its
    character matches the opener's, its length matches or exceeds the
    opener's, and the rest of the line is whitespace-only, per CommonMark's
    closing-fence rule (spec.commonmark.org/0.31.2/#fenced-code-blocks). The
    third condition is why a line such as ``` ```python ``` inside an
    already-open ``` block is content (an inner example) rather than a close:
    a closing fence takes no info string (Copilot, PR #5209 round-9 review).
    Any other fence-shaped line while inside a fence is likewise content, not
    a delimiter. (Round 7 corrected an earlier version of this docstring
    which said the length condition was deferred because "no fence in this
    corpus nests same-character runs of different lengths" -- true of the
    corpus at the time, not a property the scanner can rely on going
    forward.) Indented (4-space) code blocks and
    inline single-backtick spans are still out of scope, per the module
    docstring's "Links inside fenced code blocks... are skipped": both are a
    full CommonMark parse away, which this line-scanner deliberately is not
    (PR #5209 review).

    Returning the surviving lines, rather than scanning them in place, is
    what lets ``scan_file`` collect the file's link reference definitions
    before it scans any line: a reference may precede its definition, and a
    definition inside a fence is an illustration, not a definition.
    """
    live: list[tuple[int, str]] = []
    fence_char: str | None = None
    fence_length = 0
    for line_number, line in enumerate(body.splitlines(), 1):
        match = FENCE.match(line)
        if match:
            run = match.group("marker")
            char, length = run[0], len(run)
            # A closing fence may be followed only by spaces or tabs, per
            # CommonMark (spec.commonmark.org/0.31.2/#fenced-code-blocks,
            # quoted verbatim): "The closing code fence may be preceded by
            # up to three spaces of indentation, and may be followed only by
            # spaces or tabs, which are ignored." An opening fence has no
            # such restriction; its info string can carry any text (a
            # language tag, a shell prompt). Before this fix, a line like
            # "```python" inside an already-open ``` block matched the same
            # char/length as the opener and closed it, so the block's real
            # closing fence was then read as a new opener: a nested example
            # in the fenced content could report links, and a broken link in
            # the live prose that followed could be silently skipped
            # (Copilot, PR #5209 round-9 review).
            trailing_is_whitespace_only = not line[match.end() :].strip()
            if fence_char is None:
                fence_char, fence_length = char, length
            elif char == fence_char and length >= fence_length and trailing_is_whitespace_only:
                fence_char, fence_length = None, 0
            # else: a fence-shaped line that does not close (wrong character,
            # a shorter run than the opener, or trailing text after the
            # marker) is content, not a delimiter; fence_char/fence_length hold.
            continue
        if fence_char is None:
            live.append((line_number, line))

    return live


def scan_file(repo_root: Path, file: str, tracked: frozenset[str]) -> list[Finding]:
    """Return every ADR-link finding in one tracked markdown file.

    Reads strictly (no ``errors="replace"``): this is a file read, not one of
    the ``subprocess`` text-capture calls ``check_subprocess_encoding.py``
    gates (issue #4261), so that convention does not reach here. A tracked
    file with a non-UTF-8 byte is a real defect in the file this gate exists
    to scan, not a Windows subprocess quirk to tolerate; replacing the bad
    byte would silently alter link syntax at the exact point the scan needs
    to read it correctly, which could turn a genuinely broken link into one
    that happens to re-parse as resolvable, or the reverse (Copilot, PR #5209
    round-6 review). Raising lets ``main()``'s existing ``UnicodeDecodeError``
    handler report the file and exit 2, the same config-error path an
    unreadable file already takes.

    Fenced code is stripped first by ``_live_lines``; link reference
    definitions are then collected across the whole file, because a
    reference-style link may cite a label defined hundreds of lines below it.
    """
    path = repo_root / file
    if not path.is_file():
        return []

    live = _live_lines(path.read_text(encoding="utf-8"))
    definitions = _link_definitions(live)

    findings: list[Finding] = []
    for line_number, line in live:
        findings.extend(_malformed_findings(file, line_number, line))
        findings.extend(_link_findings(file, line_number, line, tracked))
        findings.extend(_reference_link_findings(file, line_number, line, definitions, tracked))
    return findings


def _validate_allowances(allowed: set[str], base_allowances: set[str] | None) -> None:
    """Raise when the baseline is malformed or the branch widened it.

    Two separate config errors, both raised before any file is scanned so
    neither can be mistaken for a clean result:

    Shape. Every entry must be ``<kind>:<file>:<target>``. A bare filename
    used to match every finding in that file through a ``finding.file in
    allowed`` branch this gate carried, making one line a silent, unbounded
    wildcard for every current and future defect in the file (Copilot,
    PR #5209).

    Provenance. An entry absent from the baseline at the base ref was added
    by this branch. The baseline file's own header already says "MUST NOT
    add an entry to clear a link the current change introduced"; nothing
    enforced it, so the exemption set was fully branch-controlled and a
    branch could clear its own new defect by writing one line (Copilot,
    PR #5209). ``base_allowances`` of ``None`` means there was nothing to
    ratchet against and this check does not run; see
    :func:`base_allowances_for_run` for when that happens and what it
    prints.
    """
    malformed = _malformed_baseline_entries(allowed)
    if malformed:
        listed = "\n  ".join(malformed)
        allowed_kinds = ", ".join(sorted(BASELINE_KINDS))
        raise ValueError(
            f"check_adr_links baseline has {len(malformed)} entry(ies) not shaped "
            f"<kind>:<file>:<target> with kind in {{{allowed_kinds}}}:\n  {listed}"
        )

    if base_allowances is None:
        return
    added = sorted(allowed - base_allowances)
    if added:
        listed = "\n  ".join(added)
        raise ValueError(
            f"check_adr_links baseline has {len(added)} entry(ies) this branch added "
            f"that the base ref does not carry. A baseline records a pre-existing "
            f"defect; it must not be used to clear one the current change "
            f"introduced. Fix the link instead:\n  {listed}"
        )


def find_broken_adr_links(
    repo_root: Path,
    *,
    files: list[str] | None = None,
    baseline: set[str] | None = None,
    tracked: frozenset[str] | None = None,
    base_allowances: set[str] | None = None,
) -> list[Finding]:
    """Return every non-exempt, non-baselined ADR-link finding in the tree.

    ``tracked`` defaults to the live ``git ls-files`` inventory (git is the
    I/O boundary this function owns) and is always the full markdown corpus,
    even when ``files`` narrows which files get scanned: a target-resolution
    check must see every tracked file to answer "does this link's destination
    exist", regardless of which subset is being linted this run. Callers that
    already know the tracked set, or that run against a directory that is not
    a git repository, may pass it explicitly to skip the subprocess call.

    ``base_allowances`` is the same baseline as recorded at the base ref; see
    :func:`_validate_allowances`. Pass ``None`` to skip the provenance check.
    """
    resolved_tracked = tracked if tracked is not None else frozenset(git_ls_markdown(repo_root))
    candidates = files if files is not None else sorted(resolved_tracked)
    allowed = baseline if baseline is not None else load_allowlist(repo_root / DEFAULT_BASELINE)
    _validate_allowances(allowed, base_allowances)

    # Each baseline entry allows exactly one matching finding, not every finding
    # that ever shares its key. Finding.key() is `kind:file:target`, with no line
    # number, so two occurrences of the same broken link in one file (or a new
    # occurrence added later that happens to name the same file and target as an
    # already-baselined one) share a key. A plain `in` membership check against
    # `allowed` suppresses both forever; consuming the entry from a working copy
    # after its first match means only the baselined occurrence is exempt, and a
    # second, genuinely new occurrence of the same kind:file:target still surfaces
    # as a finding (Copilot, PR #5209).
    remaining_allowances = set(allowed)
    findings: list[Finding] = []
    for file in sorted(candidates):
        normalized = file.replace("\\", "/")
        if is_historical_path(normalized):
            continue
        for finding in scan_file(repo_root, normalized, resolved_tracked):
            key = finding.key()
            if key in remaining_allowances:
                remaining_allowances.discard(key)
                continue
            findings.append(finding)

    # An unused allowance never surfaces as a finding on its own: the loop
    # above only discards a key it actually matched. Left unchecked, a
    # baseline entry whose real finding was already fixed keeps silently
    # suppressing the next unrelated regression that happens to produce the
    # identical kind:file:target key, because the `in remaining_allowances`
    # check above has no memory of whether an entry has EVER matched across
    # runs, only within this one (Copilot, PR #5209). Only enforced on a
    # full-corpus scan (`files is None`): a caller that explicitly narrows
    # `files` to a subset is not claiming the rest of the baseline is
    # unused, only that it did not look there this run.
    if files is None and remaining_allowances:
        for key in sorted(remaining_allowances):
            kind, file, target = key.split(":", 2)
            findings.append(
                Finding(
                    file,
                    0,
                    "stale-allowance",
                    target,
                    f"baseline entry for {kind!r} no longer matches any finding; "
                    f"remove it from {DEFAULT_BASELINE} or it silently suppresses "
                    "the next unrelated regression sharing this key",
                )
            )
    return findings


def _scannable_files(repo_root: Path) -> list[str]:
    """Tracked markdown files a default-argument scan would examine.

    Excludes ``HISTORICAL_ROOTS`` the same way ``find_broken_adr_links``'s
    per-file loop does. Used only to report the examined-file count
    alongside the violation count, so a narrowed or empty scan scope is not
    indistinguishable from a completed one: an existing but empty
    ``.agents/architecture`` corpus, or a ``git_ls_markdown`` regression that
    only sees a handful of tracked files, would otherwise still print
    "0 violation(s)" and read as a clean, complete pass (Copilot, PR #5209
    round-8 review). ``find_broken_adr_links`` computes its own candidate set
    internally, including the ``files``/``tracked`` overrides tests pass, so
    this duplicates its default-path computation rather than changing its
    return type, which 30+ existing call sites depend on as ``list[Finding]``.
    """
    tracked = git_ls_markdown(repo_root)
    return [f for f in tracked if not is_historical_path(f.replace("\\", "/"))]


def validate_adr_links(repo_root: Path, base_ref: str = "auto") -> bool:
    """Print broken ADR links and return True when none are found.

    This is the ``pre_pr.py`` entry point, so the base-ref provenance check
    runs here by default rather than only behind a CLI flag: an exemption
    set the branch controls is not a ratchet, and a guard nothing invokes is
    not a guard. ``base_ref="none"`` disables it; see
    :func:`base_allowances_for_run` for the cases that leave nothing to
    ratchet against.

    Checks the examined-file count before scanning, not after: a
    ``repo_root`` that resolves to a real git repository with zero tracked
    markdown files (wrong path, or a checkout outside this repo) makes
    ``git ls-files`` succeed with empty output, so ``find_broken_adr_links``
    would scan nothing and return ``[]``, printing the same "0 violation(s)"
    a genuinely clean full-corpus scan prints. A wrong-but-valid repository
    root must not manufacture a green result (Copilot, PR #5209 round-9
    review). ``main()`` below already fails on a fully-invalid path (not a
    git repository at all) via its ``subprocess.CalledProcessError`` handler;
    this closes the narrower, valid-git-empty-result case that handler
    cannot catch.
    """
    examined = len(_scannable_files(repo_root))
    if examined == 0:
        print(
            f"check_adr_links: no tracked markdown files found under {repo_root}",
            file=sys.stderr,
        )
        return False
    baseline_path = repo_root / DEFAULT_BASELINE
    findings = find_broken_adr_links(
        repo_root,
        base_allowances=base_allowances_for_run(repo_root, baseline_path, base_ref),
    )
    for finding in findings:
        print(finding.format())
    print(
        f"check_adr_links: {len(findings)} violation(s) across "
        f"{examined} tracked markdown file(s)"
    )
    return not findings


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Detect broken or wrong-numbered ADR links.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Baseline file, relative to repo root unless absolute.",
    )
    parser.add_argument(
        "--base-ref",
        default="auto",
        help=(
            "Git ref whose copy of the baseline this run may not add entries to. "
            "'auto' (default) resolves refs/remotes/origin/HEAD, origin/main, or "
            "main; 'none' disables the check. A baseline entry absent at the base "
            "ref was added by this branch, which is how a branch clears a defect "
            "it just introduced."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ADR link check."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = Path(args.repo_root).resolve()
        baseline_path = Path(args.baseline)
        if not baseline_path.is_absolute():
            baseline_path = repo_root / baseline_path

        # A repo_root that resolves to a real git repository with zero
        # tracked markdown files (wrong path, or a checkout outside this
        # repo) makes `git ls-files` succeed with empty output, so the scan
        # below would find nothing and print the same "0 violation(s)" a
        # genuinely clean full-corpus scan prints. The
        # subprocess.CalledProcessError handler below already covers a path
        # that is not a git repository at all; this closes the narrower,
        # valid-git-empty-result case that handler cannot catch (Copilot,
        # PR #5209 round-9 review).
        examined = len(_scannable_files(repo_root))
        if examined == 0:
            print(
                f"check_adr_links: no tracked markdown files found under {repo_root}",
                file=sys.stderr,
            )
            return 2

        findings = find_broken_adr_links(
            repo_root,
            baseline=load_allowlist(baseline_path),
            base_allowances=base_allowances_for_run(repo_root, baseline_path, args.base_ref),
        )
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError, ValueError) as exc:
        print(f"check_adr_links: {exc}", file=sys.stderr)
        return 2

    for finding in findings:
        print(finding.format())
    print(
        f"check_adr_links: {len(findings)} violation(s) across "
        f"{examined} tracked markdown file(s)"
    )

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
