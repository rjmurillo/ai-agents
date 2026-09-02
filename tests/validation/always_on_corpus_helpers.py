"""Measurement and parsing helpers for the always-on corpus guards.

Split out of `test_always_on_corpus_claims.py` so neither module carries the
whole subject. The tests assert; this module measures the trees and parses the
prose that states what those measurements should be.

Membership is measured from the generated `.github/instructions/` mirrors, not
from `.claude/rules/`. `generate_rules.py` drops `alwaysApply:`, renames
`paths:` to `applyTo:`, and synthesizes `applyTo: "**"` for a rule that declares
no scope. A rule whose globs are all filtered out as internal-only is skipped
outright rather than universalized, so it leaves the destination tree entirely.
The synthesized case reaches the always-on corpus with no source line to grep,
so the mirror is authoritative for membership.

Every parser raises `ValueError` when it cannot locate a claim. Reworded prose
must fail loudly; a parser that returned a partial result would leave the
assertions comparing against nothing and passing while the document drifted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.instruction_budget as ib

MIRROR_DIR = REPO_ROOT / ".github" / "instructions"
DOCTRINE = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "context-optimizer"
    / "references"
    / "model-context-doctrine.md"
)
LIBRARY_SKILL = REPO_ROOT / ".claude" / "skills" / "software-engineering-library" / "SKILL.md"

BOOK_RULES = frozenset({"code-quality", "pragmatic-programmer", "unified-software-engineering"})

_TABLE_HEADER = "| Form | Rules |"
_ROW_NAME = re.compile(r"`([a-z0-9-]+)`")
_LIBRARY_SENTENCE = re.compile(
    r"everyday default,\s*(?P<always>.+?)\s+loads? on every turn"
    r"\s+and\s+(?P<code>.+?)\s+loads? on code files",
    re.IGNORECASE,
)


def _frontmatter(text: str) -> dict:
    """Return the YAML frontmatter mapping bounded by the leading `---` pair."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def measured_always_on() -> set[str]:
    """Return rule ids whose generated mirror declares universal scope."""
    found = set()
    for path in sorted(MIRROR_DIR.glob("*.instructions.md")):
        applyto = _frontmatter(path.read_text(encoding="utf-8")).get("applyTo")
        if isinstance(applyto, str) and applyto.strip() == "**":
            found.add(path.name.removesuffix(".instructions.md"))
    return found


def parse_doctrine_table(text: str) -> set[str]:
    """Return rule ids listed in the doctrine document's always-on table.

    Raises `ValueError` when the table cannot be located so that a rewrite of
    the surrounding prose fails loudly instead of asserting against an empty
    set.
    """
    start = text.find(_TABLE_HEADER)
    if start == -1:
        raise ValueError(f"always-on table header {_TABLE_HEADER!r} not found")
    names: set[str] = set()
    rows = 0
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        rows += 1
        names.update(_ROW_NAME.findall(line))
    if rows == 0 or not names:
        raise ValueError("always-on table matched no rule rows")
    return names


# Either group can be legitimately empty. No book rule loads on every turn
# since issue #4871 rescoped `code-quality` to code files, so the sentence says
# "none", which must parse as the empty set and not as a rule named "none".
_NO_RULES = frozenset({"none", "no rule", "no book rule"})


def parse_library_sentence(text: str) -> tuple[set[str], set[str]]:
    """Return (always-on, code-files) rule ids named by the library skill."""
    match = _LIBRARY_SENTENCE.search(text)
    if not match:
        raise ValueError(
            "library skill loading sentence did not match the expected shape; "
            "update the sentence and this guard together"
        )
    split = re.compile(r"\s*,\s*|\s+and\s+")

    def names(raw: str) -> set[str]:
        if raw.strip().lower() in _NO_RULES:
            return set()
        return {part for part in split.split(raw) if part}

    return names(match.group("always")), names(match.group("code"))


_EIGHT_KB = 8192

_FIG_MIRROR = re.compile(r"always-on corpus is (?P<files>[\d,]+) rules?, (?P<bytes>[\d,]+) bytes")
_FIG_PY = re.compile(
    r"effective context on a `\.py` edit is (?P<bytes>[\d,]+) bytes\s*"
    r"across (?P<files>[\d,]+) files"
)
_FIG_SOURCE = re.compile(r"(?P<delta>[\d,]+) bytes larger in total \((?P<bytes>[\d,]+) always-on\)")
_FIG_PLUGIN = re.compile(
    r"`src/copilot-cli/instructions` carries (?P<files>[\d,]+) rules? and "
    r"(?P<bytes>[\d,]+) bytes"
)
_FIG_MULTIPLIERS = re.compile(
    r"always-on corpus is (?P<always>[\d.]+)x that threshold and a Python edit "
    r"sees (?P<code>[\d.]+)x"
)
_FIG_LARGEST = re.compile(r"`voice\.md` at (?P<bytes>[\d,]+) bytes")


def _int(raw: str) -> int:
    return int(raw.replace(",", ""))


def _search(
    pattern: re.Pattern[str], text: str, label: str, doc: str = "doctrine"
) -> re.Match[str]:
    match = pattern.search(text)
    if not match:
        raise ValueError(
            f"{doc} {label} figure did not match the expected prose shape; "
            "update the sentence and this guard together"
        )
    return match


def parse_doctrine_figures(text: str) -> dict[str, float]:
    """Return every numeric claim the doctrine makes about corpus size.

    Raises `ValueError` when a figure cannot be located, so that rewritten
    prose fails loudly instead of leaving an assertion with nothing to check.
    """
    mirror = _search(_FIG_MIRROR, text, "always-on")
    py = _search(_FIG_PY, text, "`.py` effective")
    source = _search(_FIG_SOURCE, text, "source-basis")
    plugin = _search(_FIG_PLUGIN, text, "plugin-tree")
    mult = _search(_FIG_MULTIPLIERS, text, "8KB multiplier")
    largest = _search(_FIG_LARGEST, text, "largest always-on rule")
    return {
        "mirror_files": _int(mirror.group("files")),
        "mirror_bytes": _int(mirror.group("bytes")),
        "py_files": _int(py.group("files")),
        "py_bytes": _int(py.group("bytes")),
        "source_bytes": _int(source.group("bytes")),
        "source_delta": _int(source.group("delta")),
        "plugin_files": _int(plugin.group("files")),
        "plugin_bytes": _int(plugin.group("bytes")),
        "always_multiplier": float(mult.group("always")),
        "code_multiplier": float(mult.group("code")),
        "largest_bytes": _int(largest.group("bytes")),
    }


def _budget(ext: str):
    """Measure one extension's always-on budget with the enforced tool."""
    files = ib.load_instruction_files(REPO_ROOT)
    return ib.measure_extension(files, ext, ceiling_bytes=10**9)


def _source_bytes(mirror_names: tuple[str, ...]) -> int:
    """Sum the `.claude/rules/` sources behind a set of generated mirrors."""
    total = 0
    for name in mirror_names:
        source = REPO_ROOT / ".claude" / "rules" / name.replace(".instructions.md", ".md")
        total += len(source.read_bytes())
    return total


def _tree_always_on(tree: Path) -> tuple[int, int]:
    """Return (file count, byte total) for universally scoped rules in a tree."""
    files = 0
    total = 0
    for path in sorted(tree.glob("*.instructions.md")):
        raw = path.read_bytes()
        applyto = _frontmatter(raw.decode("utf-8")).get("applyTo")
        if isinstance(applyto, str) and applyto.strip() == "**":
            files += 1
            total += len(raw)
    return files, total


CANONICAL_MIRROR_RULE = REPO_ROOT / ".claude" / "rules" / "canonical-source-mirror.md"
MEMBERSHIP_MEMORY = (
    REPO_ROOT
    / ".serena"
    / "memories"
    / "architecture"
    / "always-on-membership-lives-in-the-mirror.md"
)
PLUGIN_DIR = REPO_ROOT / "src" / "copilot-cli" / "instructions"

CORPUS_PROSE_DOCS = (
    ("canonical-source-mirror rule", CANONICAL_MIRROR_RULE),
    ("always-on-membership memory", MEMBERSHIP_MEMORY),
)

_PROSE_MEMBERSHIP = re.compile(r"embership is identical:\s*(?P<names>[^.]+)\.")
_PROSE_SOURCE_BASIS = re.compile(
    r"measure (?P<bytes>[\d,]+) bytes at `\.claude/rules/`, (?P<delta>[\d,]+) more"
)
_PROSE_PLUGIN_FILES = re.compile(
    r"plugin ships (?P<plugin>[\d,]+) instruction files against "
    r"(?P<mirror>[\d,]+) in `\.github/instructions`"
)
_PROSE_PATTERNS = (
    (_PROSE_MEMBERSHIP, "membership sentence"),
    (_PROSE_SOURCE_BASIS, "source-basis"),
    (_PROSE_PLUGIN_FILES, "plugin file count"),
)


def _prose_table_row(tree: str) -> re.Pattern[str]:
    """Match the always-on cell of the table row naming one destination tree."""
    return re.compile(
        rf"\|\s*`{re.escape(tree)}`\s*\|[^|]*\|\s*"
        r"(?P<files>[\d,]+) rules?, (?P<bytes>[\d,]+) bytes\s*\|"
    )


def _normalized(text: str) -> str:
    """Collapse newlines so a wrapped sentence parses like an unwrapped one."""
    return re.sub(r"\s+", " ", text)


def parse_corpus_prose(text: str, doc: str) -> dict[str, object]:
    """Return every corpus claim a non-doctrine document restates.

    Raises `ValueError` when a claim cannot be located. A reworded sentence
    must fail loudly; a parser that returned a partial dict would leave the
    assertions comparing against nothing and passing while the doc drifted.
    """
    flat = _normalized(text)
    figures: dict[str, object] = {}
    trees = ((".github/instructions", "mirror"), ("src/copilot-cli/instructions", "plugin"))
    for tree, key in trees:
        row = _search(_prose_table_row(tree), flat, f"{tree} table row", doc)
        figures[f"{key}_files"] = _int(row.group("files"))
        figures[f"{key}_bytes"] = _int(row.group("bytes"))
    members = _search(_PROSE_MEMBERSHIP, flat, "membership sentence", doc)
    figures["members"] = frozenset(_ROW_NAME.findall(members.group("names")))
    basis = _search(_PROSE_SOURCE_BASIS, flat, "source-basis", doc)
    figures["source_bytes"] = _int(basis.group("bytes"))
    figures["source_delta"] = _int(basis.group("delta"))
    counts = _search(_PROSE_PLUGIN_FILES, flat, "plugin file count", doc)
    figures["plugin_file_count"] = _int(counts.group("plugin"))
    figures["mirror_file_count"] = _int(counts.group("mirror"))
    return figures
