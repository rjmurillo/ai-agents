#!/usr/bin/env python3
"""Fail CI when a vendor-shipped script hard-codes an upstream-only path.

Issue #2050: skills in a vendored plugin install hard-code paths (`.agents/`,
`.claude/lib/`) that exist only in the upstream `rjmurillo/ai-agents` checkout.
In a consumer repo those paths do not exist, so the skill fails or degrades
silently. Phase 1 ships a `.claude/lib/paths.py` helper with
`resolve_artifact_root` (write path), `artifact_dir` (resolve a write location
without creating it), and `resolve_skill_resource` (read path). This check stops
NEW scripts from hard-coding those paths instead of routing through it.

What it flags:
  A Python file under a scanned skill-scripts root carrying a non-docstring
  string literal or f-string text matching `_BANNED_PATH`, when the file does
  not import and use the portability helper. A file that imports the helper is
  assumed to resolve paths through it, so the literal is the documented lazy
  default or prose. Comments and docstrings are ignored.

What it does NOT flag (Issue #2510 and #4046, false-positive guards):
  * Raw-string regex patterns: a raw prefix plus a metacharacter is a pattern
    that *matches* paths, not a path the script reads, so there is no I/O to
    migrate. The metacharacter set is per prefix; see `_is_regex_pattern`.
  * A `scripts/` literal under a `tests/` directory in a scan root, scoped the
    same way: an `.agents/` literal in a test tree is still flagged. See
    `_is_exempt_match`.
  * CLI prose: a literal inside a `help`, `description`, `epilog`, `metavar`,
    or `usage` keyword argument is rendered to stderr, never opened. Scoped to
    that value's line range, so a real path elsewhere in the file still fails.

Known residual (Issue #4046 sub-claim, deliberately not fixed):
  `_prose_lines` covers CLI keyword arguments only, so a module-level template
  constant is still scanned. No AST shape separates a template constant from a
  real dependency (`SCRIPT = "scripts/run.py"` is the same node as
  `README = "run scripts/<name>.py"`), so exempting the shape would un-flag real
  dependencies. The placeholder and bare-directory forms are handled by
  `_BANNED_PATH`'s path-component requirement instead.

Baseline ratchet:
  Files that already hard-code these paths (Issue #2050) are recorded in a
  baseline (see `baseline_path()`) and reported as known debt without failing
  the check, so regressions are gated without forcing that migration now. A NEW
  offender not in the baseline fails. `--update-baseline` regenerates it.

EXIT CODES (ADR-035):
  0 - No new offenders (baseline-listed debt is allowed); OR no scan roots
      present (a vendor install without `.claude/skills` is benign here, and
      prints `[SKIP] no scan roots present`); OR `--update-baseline` wrote.
  1 - One or more NEW offenders found (not in the baseline).
  2 - Configuration error (repo root or baseline path invalid).
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

# Upstream-only path prefixes that break in a vendored consumer repo.
# `.claude/skills/` is intentionally NOT flagged: the `/review` pattern resolves
# skill resources via the helper's `.claude/skills/...` candidate, so a
# reference to it inside or via the helper is correct. `scripts/` IS flagged
# (#4013): that tree ships in neither plugin root, so naming
# `scripts/validate_session_json.py` fails silently in every consumer install.
#
# The lookbehind `(?<![/\\\w.])` rejects `scripts` as a suffix (`build/scripts/`,
# `test_scripts/`, `../scripts/`); a parent-relative path can legitimately name
# a skill-internal sibling. The optional `(?:\.[\\/])?` re-admits an explicit
# current-directory prefix, so `"./scripts/x.py"` is flagged: without it the
# lookbehind saw the `/` in `./` and let shell-style
# `subprocess.run(["python3", "./scripts/x.py"])` bypass the gate.
#
# `scripts/` needs two alternations, because the separator can be followed by a
# path component or by nothing at all. Third, component follows: the trailing
# `[\w.\-]` requires a real component, so prose ("Extract logic to scripts/
# subdirectory.") and a placeholder ("python scripts/<name>.py") stop
# registering as paths (#4046). Neither resolves to a file, so there is no
# dependency to migrate.
#
# Fourth, nothing follows. A built path puts no path byte after the separator,
# and those are the most common real dependencies:
#   f"scripts/{name}"           FSTRING_MIDDLE token text ends at `scripts/`
#   "scripts/" + name           STRING token ends at `scripts/`
#   os.path.join("scripts/", r) same token shape
#   "scripts/%s" % name         printf placeholder follows
#   "scripts/{}".format(name)   str.format placeholder follows
# Dropping it let `subprocess.run(["python3", f"scripts/{t}.py"])` through, the
# exact dependency #4013 exists to catch. It is anchored on the start of the
# literal's body (token start, or right after an opening quote), which separates
# a built path from a sentence ending in the word: without the anchor
# `f"...consider adding scripts/"` (validate-skill.py:622) is an offender.
_BANNED_PATH = re.compile(
    r"\.agents(?:[\\/]+|['\"]|$)"
    r"|\.claude[\\/]+lib(?:[\\/]+|['\"]|$)"
    r"|(?<![/\\\w.])(?:\.[\\/])?scripts[\\/][\w.\-]"
    r"|(?:^|(?<=['\"]))(?:\.[\\/])?scripts[\\/](?:['\"%{]|$)"
)

# True for a `_BANNED_PATH` hit from a `scripts/` alternation. #4046 widened the
# false-positive guards for that prefix only, and keying on the matched text is
# what keeps `.agents/` and `.claude/lib/` detection unchanged.
_SCRIPTS_MATCH = re.compile(r"(?:\.[\\/])?scripts[\\/]")
_STRING_TOKEN_TYPES = {tokenize.STRING}
if hasattr(tokenize, "FSTRING_MIDDLE"):
    _STRING_TOKEN_TYPES.add(tokenize.FSTRING_MIDDLE)

# Helper function names exposed by .claude/lib/paths.py.
_HELPER_FUNCTIONS: frozenset[str] = frozenset(
    {"artifact_dir", "resolve_artifact_root", "resolve_skill_resource"}
)

# Keyword argument names whose value is CLI prose, not an I/O path.
# A banned path inside one of these kwargs (argparse `help=`, `description=`,
# `epilog=`, `metavar=`, `usage=`; Click and Typer follow the same convention)
# is rendered onto stderr by the CLI parser. It never opens or writes a file, so
# it cannot be migrated through the helper and must not be flagged. Issue #2510.
_PROSE_KWARGS: frozenset[str] = frozenset({"help", "description", "epilog", "metavar", "usage"})

# Directories scanned for vendor-shipped scripts.
_SCAN_ROOTS: tuple[str, ...] = (".claude/skills",)

# Baseline of known pre-existing offenders, relative to repo root, one
# POSIX path per line. Comments (`#`) and blank lines are ignored.
BASELINE_FILENAME = "vendor_portability_baseline.txt"

_REMEDIATION: tuple[str, ...] = (
    "These files hard-code an upstream-only path (.agents/, .claude/lib/, "
    "or scripts/) and do not route through the portability helper.",
    "Use .claude/lib/paths.py: resolve_artifact_root() for write paths, "
    "artifact_dir() to resolve a write location without creating it, "
    "resolve_skill_resource() for read paths. See Issue #2050 and #4013.",
    "Those helpers resolve paths inside the plugin root, so they do NOT "
    "fix a scripts/ reference: that tree is upstream-only and ships in "
    "neither plugin root. Drop the reference, or record it in this "
    "baseline with a comment naming the dependency.",
)
_BASELINE_ESCAPE_HATCH = (
    "If this offender is intentional and cannot be made portable, add it "
    "to scripts/validation/vendor_portability_baseline.txt with a comment "
    "or run --update-baseline."
)


@dataclass
class Offender:
    """A scanned file that hard-codes a banned path without the helper."""

    relpath: str
    line: int
    excerpt: str


def baseline_path(repo_root: Path) -> Path:
    """Return the baseline file path co-located with this script."""
    return repo_root / "scripts" / "validation" / BASELINE_FILENAME


def load_baseline(path: Path) -> set[str]:
    """Load the baseline allowlist of known offenders (POSIX relpaths)."""
    if not path.is_file():
        return set()
    entries: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line)
    return entries


def scan_roots(repo_root: Path) -> list[Path]:
    """Return the scan-root directories that exist under repo_root."""
    return [repo_root / r for r in _SCAN_ROOTS if (repo_root / r).is_dir()]


def _routes_through_helper(content: str) -> bool:
    """True when the file imports and uses the portability helper."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    paths_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "paths":
                    paths_aliases.add(alias.asname or "paths")
        if isinstance(node, ast.ImportFrom) and node.module == "paths":
            if any(alias.name in _HELPER_FUNCTIONS for alias in node.names):
                return True

    if not paths_aliases:
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr not in _HELPER_FUNCTIONS:
            continue
        if isinstance(node.value, ast.Name) and node.value.id in paths_aliases:
            return True
    return False


def _docstring_lines(content: str) -> set[int]:
    """Return line numbers occupied by module, class, and function docstrings."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()

    lines: set[int] = set()
    nodes: list[ast.AST] = [tree]
    nodes.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    )
    for node in nodes:
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            continue
        start = first.lineno
        end = getattr(first, "end_lineno", start)
        lines.update(range(start, end + 1))
    return lines


def _prose_lines(content: str) -> set[int]:
    """Return line numbers occupied by CLI prose keyword-arg values.

    Walks every ``ast.Call`` and records the line range of any keyword in
    ``_PROSE_KWARGS``. The whole value expression's span is marked, so a
    concatenation or a ``+``/``%`` expression spanning lines is covered too, and
    any banned-path token inside that span reads as prose, not a path operation.
    Issue #2510: ``argparse.ArgumentParser(epilog=...)`` and
    ``parser.add_argument("--out", help="...")`` motivated it; Click and Typer
    follow the same convention and fall under the same rule.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()

    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg is None or kw.arg not in _PROSE_KWARGS:
                continue
            start = getattr(kw.value, "lineno", None)
            end = getattr(kw.value, "end_lineno", start)
            if start is None:
                continue
            lines.update(range(start, (end or start) + 1))
    return lines


# String-literal prefixes that mark a raw string. A raw string disables Python's
# own backslash interpretation, so a `\.` inside one is a regex escape rather
# than an escape the interpreter consumed (Issue #2510). The `f` letters cover
# raw f-string prefixes (`rf`/`fr`/`Rf`...), a single STRING token before 3.12.
_RAW_STRING_PREFIX = re.compile(r"^[bBuUfF]*[rR][bBuUfF]*")

# The `scripts/`-only metacharacter set. The pre-#4046 check keyed on `\.`
# alone, which worked because both prefixes it was written for start with a dot,
# so a pattern matching one had to escape it. `scripts/` carries no dot, so the
# exemption could never fire for that class (#4046). Anchors, quantifiers,
# groups, classes, and alternation mean the same "this is a pattern" and cover
# `r"^scripts/"` and `r'python\s+scripts/'`.
#
# Deliberately NOT used for `.agents/` or `.claude/lib/`: `*`, `?`, `[`, `]` are
# glob wildcards as well as regex metacharacters, so the set would exempt
# `glob.glob(r".agents/analysis/*.md")`, a real read of the upstream tree.
# #4046 AC3 froze those prefixes, and they still key on `\.`. A bare backslash
# is in neither set: it is the Windows separator, so admitting it would exempt
# `r".\scripts\pre_pr.py"`.
_REGEX_METACHAR = re.compile(r"\\\.|[\^$*+?\[\]()|]")


def _is_raw_string(
    token_text: str, is_fstring_middle: bool = False, is_raw_fstring: bool = False
) -> bool:
    """True when the token's text came from a raw string literal.

    A ``tokenize.STRING`` token carries the prefix, so raw-ness is read from it.
    A ``FSTRING_MIDDLE`` token (3.12+ splits f-strings into START/MIDDLE/END)
    does not, so the caller passes ``is_raw_fstring`` from the START token.
    """
    if is_fstring_middle:
        return is_raw_fstring
    return _RAW_STRING_PREFIX.match(token_text) is not None


def _is_regex_pattern(match_text: str, token_text: str, is_raw: bool) -> bool:
    """True when the literal reads as a regex rather than a path.

    Requires the raw-string signal plus a metacharacter, with the set chosen by
    which banned prefix matched: the wide set for ``scripts/``, the pre-#4046
    escaped dot for the other two. A plain ``r".agents/x"`` with no
    metacharacter stays flagged, so a bare pattern is not a silent bypass.
    """
    if not is_raw:
        return False
    if _SCRIPTS_MATCH.match(match_text):
        return _REGEX_METACHAR.search(token_text) is not None
    return "\\." in token_text


def _is_exempt_match(match_text: str, token_text: str, is_raw: bool, in_tests: bool) -> bool:
    """True when this banned-path hit is a known false positive.

    The ``tests/`` exemption is scoped to ``scripts/`` for the same reason the
    wide metacharacter set is. Four of the nine #4046 false positives were bare
    ``scripts/`` fixture strings with nothing separating them from a real
    dependency, and a skill's tests never execute in a consumer install; but
    widening the exemption to every prefix drops four pre-existing ``.agents/``
    baseline entries, changing the #2050 gate that #4046 AC3 froze.
    """
    if in_tests and _SCRIPTS_MATCH.match(match_text):
        return True
    return _is_regex_pattern(match_text, token_text, is_raw)


def _first_banned_line(content: str, in_tests: bool = False) -> tuple[int, str] | None:
    """Return the first banned path in a non-docstring string literal."""
    skip_lines = _docstring_lines(content) | _prose_lines(content)
    reader = io.StringIO(content).readline
    fstring_start = getattr(tokenize, "FSTRING_START", None)
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    fstring_end = getattr(tokenize, "FSTRING_END", None)
    is_raw_fstring = False
    try:
        for token in tokenize.generate_tokens(reader):
            if token.type == fstring_start:
                is_raw_fstring = "r" in token.string.lower()
                continue
            if token.type == fstring_end:
                is_raw_fstring = False
                continue
            if token.type not in _STRING_TOKEN_TYPES or token.start[0] in skip_lines:
                continue
            is_raw = _is_raw_string(token.string, token.type == fstring_middle, is_raw_fstring)
            for match in _BANNED_PATH.finditer(token.string):
                if _is_exempt_match(match.group(), token.string, is_raw, in_tests):
                    continue
                return token.start[0], token.line.strip()
    except tokenize.TokenError:
        return None
    return None


def collect_offenders(repo_root: Path) -> list[Offender]:
    """Find files that hard-code a banned path without the helper.

    A file offends when it contains a banned path AND does not route through the
    portability helper. The helper itself (`.claude/lib/paths.py`) lives outside
    the scan roots, so it is never scanned.
    """
    offenders: list[Offender] = []
    for root in scan_roots(repo_root):
        for py_file in sorted(root.rglob("*.py")):
            parts = py_file.relative_to(root).parts
            if "__pycache__" in parts:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _routes_through_helper(content):
                continue
            hit = _first_banned_line(content, in_tests="tests" in parts)
            if hit is None:
                continue
            line_no, excerpt = hit
            relpath = py_file.relative_to(repo_root).as_posix()
            offenders.append(Offender(relpath, line_no, excerpt))
    return offenders


def split_offenders(
    offenders: list[Offender],
    baseline: set[str],
) -> tuple[list[Offender], list[Offender]]:
    """Partition offenders into (new, known) by baseline membership."""
    new: list[Offender] = []
    known: list[Offender] = []
    for off in offenders:
        (known if off.relpath in baseline else new).append(off)
    return new, known


def format_report(new: list[Offender], known: list[Offender]) -> str:
    """Format a human-readable report."""
    lines: list[str] = []
    if not new:
        lines.append("[PASS] No new vendor-portability offenders.")
        if known:
            lines.append(
                f"       {len(known)} known offender(s) tracked in the baseline "
                "(Issue #2050 migration debt)."
            )
        return "\n".join(lines) + "\n"

    lines.append(f"[FAIL] {len(new)} new vendor-portability offender(s) found.")
    lines.append("")
    lines.extend(_REMEDIATION)
    lines.append("")
    for off in new:
        lines.append(f"  - {off.relpath}:{off.line}")
        lines.append(f"      {off.excerpt!r}")
    lines.append("")
    lines.append(_BASELINE_ESCAPE_HATCH)
    return "\n".join(lines) + "\n"


def write_baseline(path: Path, offenders: list[Offender]) -> None:
    """Write the baseline file from the current offender set."""
    header = [
        "# Vendor-portability baseline (Issue #2050).",
        "# Pre-existing scripts that hard-code .agents/, .claude/lib/, or scripts/ paths.",
        "# check_vendor_portability.py allows these but fails on NEW offenders.",
        "# Regenerate: python3 scripts/validation/check_vendor_portability.py --update-baseline",
        "",
    ]
    body = sorted({off.relpath for off in offenders})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(header + body) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Fail CI on new hard-coded upstream-only paths in skills.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to the script's grandparent).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Regenerate the baseline from the current offenders, then exit 0.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)

    repo_root = args.repo_root
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent

    if not repo_root.is_dir():
        print(f"[FAIL] repo root not found: {repo_root}", file=sys.stderr)
        return 2

    roots = scan_roots(repo_root)
    if not roots:
        print("[SKIP] no scan roots present (.claude/skills).")
        return 0

    offenders = collect_offenders(repo_root)

    bpath = baseline_path(repo_root)
    if args.update_baseline:
        try:
            write_baseline(bpath, offenders)
        except OSError as exc:
            print(f"[FAIL] cannot write baseline {bpath}: {exc}", file=sys.stderr)
            return 2
        print(f"[OK] wrote baseline: {bpath} ({len(offenders)} entr(ies))")
        return 0

    baseline = load_baseline(bpath)
    new, known = split_offenders(offenders, baseline)
    print(format_report(new, known))
    return 1 if new else 0


if __name__ == "__main__":
    raise SystemExit(main())
