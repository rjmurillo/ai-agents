#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: most of this file is prose, not code. Every
# regex here records which shape it excludes and which reported defect made it
# exclude that shape, so docstring, comment, and blank lines outweigh executable
# ones by a wide margin. Splitting the small code core to satisfy a line count
# measured mostly on prose would move the prose away from the pattern it
# explains, and the patterns carry load-bearing semantics that only read
# correctly next to each other. Exact counts are deliberately omitted: they
# drift on every comment edit and would make this rationale stale rather than
# wrong-but-checkable.
"""Frontmatter self-containment gate for shipped plugin files (issue #3565).

Why this exists separately from ``check_skill_md_portability.py``:

  That validator is a baselined ratchet over skill *prose*, scoped to
  ``.claude/skills``. Three of the four surfaces the plugin-self-containment
  rule names are outside its scan (``.claude/commands``, ``src/claude``,
  ``src/copilot-cli``), and its pattern set does not include ``docs/``. A
  ``docs/`` reference in a shipped frontmatter description therefore passes
  every gate in this repository, wherever it sits. Two were sitting in the
  tree, both older than the rule that forbids them.
  ``docs/agent-metrics.md`` entered the ``metrics`` description in
  ``817e466f82`` (#2136, 2026-05-30) and ``docs/autonomous-pr-monitor.md``
  entered the ``pr-autofix`` description in ``79867ca6ed`` (#2049, 2026-05-25),
  under that command's pre-rename name ``autofix-pr.md``. The rule forbidding
  both shipped on 2026-07-26 in #3443 with no validator, so neither moved.

  Two traps sit in that paragraph, both of which produced a wrong claim in an
  earlier draft. Check provenance against the source file, never the generated
  mirror: the mirror's history begins when the generator first wrote it, which
  dates the copy rather than the claim. And check it against the *field* named
  in the claim: ``git log -S`` finds the string anywhere in the file, so a
  reference that lived in body prose for months reads as frontmatter
  provenance unless the historical file is opened and the block inspected.
  Follow renames, or the date belongs to the rename.

Measured precision, and the cost of being wrong:

  The gate has no baseline, so a false positive hard-blocks a legitimate
  change. That claim was tested rather than asserted. Replaying this check over
  the retained reachable history of Markdown under all three plugin roots,
  3,687 blobs from ``git rev-list --objects --all``, produces four distinct
  references and no others: ``docs/autonomous-pr-monitor.md``,
  ``docs/agent-metrics.md``, ``.agents/governance/golden-principles.md``
  (declared), and ``scripts/incoherence.py`` in a deprecated skill. All four
  are real. None resolves for a consumer. Across every Markdown file in the
  current tree the gate reports nothing at all.

  State that as reachable history, not as all of it, and not as a rate. Blobs
  from squashed-away branch tips are unreachable once the branch is deleted, so
  a shape that a contributor wrote and fixed before merge is invisible here,
  and that is exactly where a false positive would bite. ``--all`` also spans
  local heads and stashes rather than merged history alone. A blob replay
  carries no tree, so it cannot answer root-relative questions on its own.
  The measurement bounds what has shipped; it does not bound what could.

  The known false positive is a description that names a consumer artifact the
  skill writes rather than reads, such as ``.github/workflows/ci.yml``. The
  extension test cannot tell those apart from an upstream dependency. That
  shape has never appeared in a shipped frontmatter here, which is why the
  check is absolute instead of baselined. If one lands, the remedy is a
  ``vendor-portability`` marker naming that path, and a second marker
  vocabulary is worth adding only once the case is real rather than imagined.

Why frontmatter, and only frontmatter:

  A ``description`` is loaded into every session so the harness can route,
  whether or not the skill is ever invoked. Body prose is read only on
  invocation. A dangling path in a description is therefore the most-read and
  least-useful kind: the consumer sees it constantly and can never resolve it.
  Body prose is a far larger surface (2,556 references across 347 files at
  ``30eaa85dde``) that needs per-file classification against the rule's
  three-kind table, so it stays with the existing ratchet and with review.

What counts as a violation:

  A frontmatter ``description`` or ``name`` under a plugin root that names a
  *file* (a path with an extension) which the plugin does not carry. Two
  shapes qualify. The first is a path under a directory that exists only in
  ``rjmurillo/ai-agents``. The second is a path that spells out a plugin root,
  which the rule forbids twice over: MUST-2 bans the bare in-root form because
  it "resolves only when the consumer's working directory happens to match",
  and MUST-3 bans reaching across roots because the roots install separately.

  Requiring an extension is what keeps this check honest. The rule permits
  consumer-workspace paths, which are the plugin doing its job: an agent told
  to write to ``.agents/planning/`` or ``docs/adr/`` is correct, because those
  are directories in the *installing* repo. Those have no extension. It also
  sidesteps the prose collisions the rule warns about, such as
  "build/buy/partner", which would match a bare ``build/`` prefix.

  ``templates/`` is deliberately narrowed to ``templates/agents/`` and
  ``templates/platforms/``. The bare directory name is overloaded: a skill may
  ship its own ``templates/`` directory, and framework conventions appear in
  prose. Only those two are upstream-only.

Opt-out:

  A ``<!-- vendor-portability: ... -->`` marker suppresses a frontmatter
  reference only when the marker itself names that path. The sibling
  validators read the marker as a whole-file switch, and for frontmatter that
  is demonstrably wrong: ``.claude/skills/metrics/SKILL.md`` carries one
  written about the consumer's ``.agents/`` artifacts, and a whole-file reading
  lets it silence the unrelated ``docs/agent-metrics.md`` sitting in its own
  description. The rule states the general form: a whole-file declaration
  "would also hide a later real regression in the same file". Scoping the
  opt-out to the path it names keeps the hatch specific and makes it say what
  it is buying.

Scanned surface versus triggered surface:

  ``iter_markdown`` walks every Markdown file under a plugin root, including
  files inside nested dot-directories. That is only safe because the workflow's
  path filter reaches them too, and it reaches them because
  ``dorny/paths-filter`` passes ``{dot: true}`` to picomatch at the SHA this
  repository pins. Verified at ``7b450fff21473bca461d4b92ce414b9d0420d706``,
  ``src/filter.ts`` line 16, applied at both ``picomatch()`` call sites.

  The default matters because it runs the other way: picomatch without that
  option does *not* match ``.claude/.hidden/a.md`` against ``.claude/**``.
  Confirmed directly against the library. So a future change that swaps the
  action, unpins it onto a release that drops the option, or hand-rolls the
  filter would silently shrink the trigger below the scan, and a violation in a
  nested dot-directory would stop firing this gate while still shipping. If
  that ever happens, narrow ``iter_markdown`` to match rather than leaving the
  gap. Today no plugin root contains a Markdown file in a nested dot-directory,
  so the exposure is latent either way.

No baseline. The surface is four files, two of which are declared, so the
honest starting point is zero and staying there. A baseline on a surface this
small would only invite drift.

Exit codes:
  0 - no undeclared outward file references in frontmatter
  1 - at least one violation
  2 - configuration error (no plugin root found)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

PLUGIN_ROOTS = (".claude", "src/claude", "src/copilot-cli")

# A path that spells out a plugin root. The directory exists here, so this is
# not an upstream-only reference, but it does not resolve for a consumer
# either: the root is what gets installed, and it lands wherever the harness
# puts it, not at the repo-relative path written here. The rule forbids both
# shapes. MUST-2 bans a bare in-root path, because it "resolves only when the
# consumer's working directory happens to match", and MUST-3 bans reaching
# across roots, because ``.claude`` and ``src/copilot-cli`` install separately.
# Resolution handles the difference between the two: an in-root reference is
# tried against the file's own directory and against the owning root first, so
# a relative path that genuinely resolves is never flagged, while a
# root-prefixed spelling of that same file has nowhere to land and is.
ROOT_PREFIXED = tuple(re.escape(root) for root in PLUGIN_ROOTS)

# Directories that exist only in this repository. A consumer who installs a
# plugin receives the plugin root and nothing above it.
UPSTREAM_ONLY = (
    r"docs",
    r"\.agents",
    r"\.github",
    r"\.serena",
    r"scripts",
    r"tests",
    r"build",
    r"templates/agents",
    r"templates/platforms",
)

# A remote URI, removed from a value before paths are looked for. A path inside
# one is not a filesystem path: the reader resolves it over the network and it
# works for them, which is also what the rule's SHOULD-2 asks for when a
# reference really is contributor-scoped. Removing the URI is the right shape
# rather than widening the path boundary, because a query parameter or a
# fragment puts `=`, `?`, or `#` before the path and widening the boundary to
# cover those would also stop detecting `--config=docs/a.md`.
#
# `file:` is caught by `LOCAL_URI` below, which reads the raw value before this
# pattern runs, so excluding it here would change nothing: measured across the
# `file://host/...`, `file:///abs/...`, and single-slash shapes, the reference
# set is identical with and without the exclusion. `OUTWARD_FILE` cannot match
# inside a file URI either, because the character before any directory name in
# one is always `/`, which is not a token boundary. A guard that cannot fail is
# noise, so there is none here.
#
# The tail stops at whitespace and at the punctuation that encloses a URI in
# prose. A greedy `\S+` swallows a real reference that follows a URI with only
# punctuation between them, as in `http://example.com,docs/a.md`, which turns a
# precision fix into a silent miss.
#
# `file:` is excluded because a standalone local file URI has to survive this
# strip for `LOCAL_URI` to report it. The exclusion is categorical, not an
# ordering detail: a `file:` URI names a local path, so a pass that removes
# addresses which are not local paths has nothing to do with it. Reading the
# guard as merely order-dependent is what got it deleted once as dead code,
# when the local scan still read the raw value. It is live now, because the
# local scan reads the stripped value and `[a-z][a-z0-9+.-]*://` matches
# `file://` like any other scheme, so without it every `file://` reference
# would be erased here and pass silently.
REMOTE_URI = re.compile(
    r"(?<![A-Za-z0-9])(?!file:)[a-z][a-z0-9+.-]*://[^\s<>,;)\]\"']+",
    re.IGNORECASE,
)

# Schemes that carry no authority component and no filesystem path. Their tails
# are addresses and payloads, so a path-shaped substring in one is not a
# reference. The list is explicit rather than a general `scheme:` pattern
# because a general one also matches ordinary prose such as `Note:docs/a.md`.
#
# `data:` is split out because its payload follows a comma, and the shared tail
# stops at one. Sharing the tail left `data:text/plain,docs/a.md` half-stripped
# and reported the payload as a reference.
OPAQUE_URI = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:mailto|tel|urn):[^\s<>,;)\]\"']+"
    r"|data:[^\s<>;)\]\"']+)",
    re.IGNORECASE,
)

# A local file URI. Nothing about it survives leaving this machine, so it is a
# violation on sight rather than a path to resolve. It is reported whole,
# because the part a consumer cannot use is the scheme, not the tail.
#
# The tail may not end in sentence punctuation. Without that, `file:///docs/a.md.`
# at the end of a sentence reports the period as part of the URI, and because the
# opt-out below compares the reported string against the declared one, a period on
# one side and not the other would silently defeat a correct declaration.
LOCAL_URI = re.compile(
    r"(?<![A-Za-z0-9])file:/(?:[^\s<>,;)\]\"']*[^\s<>,;)\]\"'.!?])?",
    re.IGNORECASE,
)

# A path under an upstream-only directory, or one that spells a plugin root,
# that names a file rather than a directory. The trailing extension is
# load-bearing: see the module docstring.
#
# The leading group is a consumed token boundary rather than a negative
# lookbehind so that the path may begin with `/` or with any number of `../`
# segments, which a fixed-width lookbehind cannot express. It is a negated
# class, not an enumerated one: an allow-list of the punctuation seen in prose
# silently drops every Markdown delimiter left out of it, and a path in a
# description is most often written inside backticks, bold markers, or a table
# cell. Measured on this repository, an enumerated class matched 1,902 body
# references against 2,556 for the negated one.
#
# `src/docs/a.md` still does not match: the character before `docs` is `/`,
# which is a path character, so the boundary rejects it, and the only other
# candidate start is `src`, which is not a watched directory. `findall`
# returns the capture group, which is the path without its boundary character.
#
# `+` is in the interior class because leaving it out silently dropped whole
# paths, not just the plus. `docs/c++/notes.md` failed at the `+`, and with no
# other candidate start the reference vanished; so did `docs/a+b.md`. Widening
# an interior class cannot create a match on its own, since a match still has
# to open on a watched directory and close on an extension, and a sweep of
# every checked value in all three plugin roots returned the same set before
# and after. The extension alphabet is deliberately not widened: nothing
# tracked here carries an extension past nine characters that this pattern
# could reach, and a looser tail reads more prose as a path.
OUTWARD_FILE = re.compile(
    r"(?:^|[^\w./-])"
    r"(/?(?:\.{1,2}/)*(?:"
    + "|".join(UPSTREAM_ONLY + ROOT_PREFIXED)
    + r")/[\w./+-]*\w\.[A-Za-z][A-Za-z0-9]{0,9})(?![\w/])"
)

DECLARATION = re.compile(r"<!--\s*vendor-portability:(.*?)-->", re.IGNORECASE | re.DOTALL)

# Frontmatter keys whose values reach the consumer before invocation.
CHECKED_KEYS = ("description", "name")

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG = 2


def frontmatter_lines(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, line)`` for the frontmatter block, 1-based.

    Empty when the file has no frontmatter or the block is unterminated. An
    unterminated block is not frontmatter; treating the whole file as
    frontmatter would scan body prose this check deliberately excludes.

    A fence counts only at column zero. An indented ``---`` sits inside a
    literal scalar, where YAML reads it as content, so closing the block there
    truncates the value and every reference below the indented line goes
    unseen while a real loader still hands the whole string to the consumer.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return []
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return [(n + 2, line) for n, line in enumerate(lines[1:index])]
    return []


def _line_scan(lines: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """Attribute each frontmatter line to the checked key that owns it.

    The fallback for frontmatter that is not valid YAML. Continuation lines of
    a folded or literal scalar belong to the key that opened them, so they are
    attributed to it rather than skipped.
    """
    found: list[tuple[int, str, str]] = []
    active: str | None = None
    for number, line in lines:
        match = re.match(r"([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if match:
            key = match.group(1)
            active = key if key in CHECKED_KEYS else None
            if active:
                found.append((number, key, match.group(2)))
            continue
        if active and line.startswith((" ", "\t")):
            found.append((number, active, line.strip()))
    return found


def _key_line(lines: list[tuple[int, str]], key: str) -> int:
    """The frontmatter line that opens ``key``, or the block's first line.

    Comment lines are skipped. The search is deliberately unanchored, so that a
    key inside a flow mapping still reports its own line, and that same
    looseness would otherwise let a commented-out key claim the line number
    belonging to the real one below it.
    """
    pattern = re.compile(r"""["']?\b""" + re.escape(key) + r"""["']?\s*:""")
    for number, line in lines:
        if line.lstrip().startswith("#"):
            continue
        if pattern.search(line):
            return number
    return lines[0][0] if lines else 1


def checked_values(text: str) -> list[tuple[int, str, str]]:
    """Return ``(line_number, key, value)`` for each checked frontmatter key.

    Frontmatter is YAML, so it is parsed as YAML. A line-oriented reader sees
    ``description:`` and misses every other spelling the format allows: a
    quoted key, a flow mapping, an escape that encodes the separator. Each of
    those is valid YAML that a consumer's loader resolves to a path, and each
    one would walk past a reader that only matches a bare key at line start.

    The line scan remains as the fallback for frontmatter that is not valid
    YAML. This repository ships two such files on purpose: the SkillForge
    templates carry placeholder syntax that a real loader rejects. Parsing
    strictly and failing closed would break them; parsing strictly and falling
    back reads every valid file correctly and still reads the invalid ones.
    """
    lines = frontmatter_lines(text)
    if not lines:
        return []
    try:
        data = yaml.safe_load("\n".join(line for _, line in lines))
    except yaml.YAMLError:
        data = None
    if not isinstance(data, dict):
        return _line_scan(lines)
    found: list[tuple[int, str, str]] = []
    for key in CHECKED_KEYS:
        value = data.get(key)
        if value is not None:
            found.append((_key_line(lines, key), key, str(value)))
    return found


def _path_surface(value: str) -> str:
    """The part of a value where a filesystem path can legitimately appear.

    Remote and opaque URIs are removed first because their tails are hosts,
    addresses, and payloads. A path-shaped substring inside one is not a
    reference to a file, and reporting it is a false positive on a gate that
    blocks a merge.

    Both readers of a value go through here, and that is the point rather than
    tidiness. When only ``scan_file`` stripped URIs, a marker reading
    ``<!-- vendor-portability: https://example.test/?path=docs/a.md -->``
    declared ``docs/a.md`` out of a query string and silently waived a real
    violation elsewhere in the same file. An opt-out that a URL can trigger is
    not an opt-out.
    """
    return OPAQUE_URI.sub(" ", REMOTE_URI.sub(" ", value))


def declared_paths(text: str) -> set[str]:
    """Paths named inside this file's ``vendor-portability`` markers.

    Scoping the opt-out to the paths it names is the difference between an
    escape hatch and a blanket. A marker written about one dependency must not
    silence an unrelated one that lands in the same file later.
    """
    declared: set[str] = set()
    for body in DECLARATION.findall(text):
        surface = _path_surface(body)
        declared.update(OUTWARD_FILE.findall(surface))
        # A local file URI is checked as a whole string, and `OUTWARD_FILE`
        # cannot produce that string: the character before any directory name
        # inside a URI is always `/`, which the boundary rejects. Reading the
        # marker with `OUTWARD_FILE` alone therefore left `declared` empty for
        # every local URI, so the opt-out the docstring and the failure message
        # both advertise could never be taken. The two matchers cannot collide,
        # because one always yields a string containing `file:/` and the other
        # never does.
        declared.update(LOCAL_URI.findall(surface))
    return declared


def reference_shipper(repo_root: Path, root: str, file_dir: Path) -> Callable[[str], bool]:
    """True for references that resolve inside the content a consumer installs.

    A path is resolved two ways, because both are things a consumer can act on.
    Against the directory of the file that names it: a skill that bundles its
    own ``scripts/`` is the skill-bundle convention, and 90 skills in this
    repository ship one. Against the plugin root that ships that file:
    ``src/copilot-cli`` ships its own ``docs/``, so
    ``docs/copilot-instructions.md`` resolves for that plugin's consumer while
    the same string under ``.claude`` points at nothing they installed.

    A ``..`` segment never resolves, even when the file exists one level up.
    Escaping the plugin root is the thing this check exists to catch, so the
    test is for the segment rather than the substring: a filename may contain
    consecutive dots (``docs/a..b.md``) without being a traversal, and the
    traversal may sit anywhere in the path rather than only at the front.

    An absolute candidate never resolves either, and the reason is a pathlib
    behaviour rather than a policy: ``base / "/docs/a.md"`` discards the base
    and yields ``/docs/a.md``. Without the guard the existence test asks about
    the host filesystem rather than about shipped content, so an absolute
    reference is laundered into "shipped" by whatever happens to sit at the
    root of the build container. ``/build`` and ``/scripts`` are ordinary
    directories in a container image, and both spell a watched directory here.
    """

    bases = (file_dir, repo_root / root)

    def ships(reference: str) -> bool:
        candidate = reference[2:] if reference.startswith("./") else reference
        if candidate.startswith("/"):
            return False
        if ".." in candidate.split("/"):
            return False
        return any((base / candidate).exists() for base in bases)

    return ships


def scan_file(
    path: Path, text: str, ships: Callable[[str], bool] | None = None
) -> list[tuple[int, str, str]]:
    """Return ``(line_number, key, reference)`` violations for one file."""
    declared = declared_paths(text)
    violations: list[tuple[int, str, str]] = []
    for number, key, value in checked_values(text):
        surface = _path_surface(value)
        for local in LOCAL_URI.findall(surface):
            if local not in declared:
                violations.append((number, key, local))
        for reference in OUTWARD_FILE.findall(surface):
            if reference in declared:
                continue
            if ships is not None and ships(reference):
                continue
            violations.append((number, key, reference))
    return violations


def iter_markdown(root: Path) -> list[Path]:
    """Every ``.md`` file under the plugin roots, in a stable order.

    ``.claude/worktrees`` holds nested checkouts of this same repository. They
    are not source, and scanning them multiplies every finding by the number of
    live agent worktrees.
    """
    found: list[Path] = []
    for name in PLUGIN_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            parts = path.relative_to(root).parts
            if "worktrees" in parts or "__pycache__" in parts or "node_modules" in parts:
                continue
            found.append(path)
    return sorted(found)


def owning_root(path: Path, repo_root: Path) -> str | None:
    """The plugin root that ships ``path``, or ``None`` if it is outside them."""
    relative = path.relative_to(repo_root).as_posix()
    for name in PLUGIN_ROOTS:
        if relative.startswith(f"{name}/"):
            return name
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to the tree containing this script.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root or Path(__file__).resolve().parents[2]
    if not any((root / name).is_dir() for name in PLUGIN_ROOTS):
        print(f"No plugin root found under {root}", file=sys.stderr)
        return EXIT_CONFIG

    files = iter_markdown(root)
    violations: list[tuple[Path, int, str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            print(f"Could not read {path}: {error}", file=sys.stderr)
            return EXIT_CONFIG
        root_name = owning_root(path, root)
        ships = reference_shipper(root, root_name, path.parent) if root_name else None
        for number, key, reference in scan_file(path, text, ships):
            violations.append((path, number, key, reference))

    if not violations:
        print(
            f"No outward frontmatter references. Scanned {len(files)} files "
            f"across {len(PLUGIN_ROOTS)} plugin roots."
        )
        return EXIT_OK

    print(f"Outward frontmatter references in {len(violations)} place(s):\n", file=sys.stderr)
    for path, number, key, reference in violations:
        relative = path.relative_to(root)
        print(f"  {relative}:{number}  {key}: {reference}", file=sys.stderr)
    print(
        "\nA frontmatter description loads into every session, and a consumer "
        "who installs the plugin receives the plugin root and nothing above it, "
        "so these paths never resolve for them. Inline the fact, drop the "
        "clause, or declare the dependency with a "
        "'<!-- vendor-portability: ... -->' marker if it is real and intended. "
        "See .claude/rules/plugin-self-containment.md.",
        file=sys.stderr,
    )
    return EXIT_VIOLATION


if __name__ == "__main__":
    raise SystemExit(main())
