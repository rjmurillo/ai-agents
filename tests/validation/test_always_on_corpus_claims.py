"""Guards the always-on corpus claims that ship inside the plugin.

Two documents state, in prose, which rules load on every turn:

* `.claude/skills/context-optimizer/references/model-context-doctrine.md`
  enumerates always-on rules in a three-row table, one row per declaration
  convention.
* `.claude/skills/software-engineering-library/SKILL.md` names which of the
  three book-derived rules load on every turn and which load on code files.

Both are hand-maintained and both have drifted. PR #4424 narrowed
`pragmatic-programmer` out of the always-on set and updated neither, which is
the drift these tests exist to catch.

Membership is measured from the generated `.github/instructions/` mirrors, not
from `.claude/rules/`. `generate_rules.py` drops `alwaysApply:`, renames
`paths:` to `applyTo:`, and synthesizes `applyTo: "**"` for a rule that declares
no scope. A rule whose globs are all filtered out as internal-only is skipped
outright rather than universalized, so it leaves the destination tree entirely.
The synthesized case reaches the always-on corpus with no source line to grep,
so the mirror is authoritative for membership.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
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


def parse_library_sentence(text: str) -> tuple[set[str], set[str]]:
    """Return (always-on, code-files) rule ids named by the library skill."""
    match = _LIBRARY_SENTENCE.search(text)
    if not match:
        raise ValueError(
            "library skill loading sentence did not match the expected shape; "
            "update the sentence and this guard together"
        )
    split = re.compile(r"\s*,\s*|\s+and\s+")
    return (
        {p for p in split.split(match.group("always")) if p},
        {p for p in split.split(match.group("code")) if p},
    )


def test_measured_always_on_set_is_not_empty() -> None:
    """A silent glob or parse failure would make every other assertion vacuous."""
    measured = measured_always_on()
    assert len(measured) >= 5, f"suspiciously small always-on set: {measured}"
    assert "universal" in measured


def test_doctrine_table_matches_measured_always_on_set() -> None:
    listed = parse_doctrine_table(DOCTRINE.read_text(encoding="utf-8"))
    measured = measured_always_on()
    assert listed == measured, (
        f"doctrine table drift. only in doc: {sorted(listed - measured)}; "
        f"only in .github/instructions: {sorted(measured - listed)}"
    )


def test_doctrine_table_parser_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="not found"):
        parse_doctrine_table("# doc with no table\n\nprose only.\n")


def test_doctrine_table_parser_rejects_a_header_with_no_rows() -> None:
    with pytest.raises(ValueError, match="no rule rows"):
        parse_doctrine_table(f"{_TABLE_HEADER}\n|---|---|\n\nprose.\n")


def test_doctrine_table_parser_reads_every_row() -> None:
    """A parser that stopped at the first row would still pass a one-row doc."""
    doc = (
        f"{_TABLE_HEADER}\n|---|---|\n"
        "| `applyTo: '**'` | `alpha`, `beta` |\n"
        "| `alwaysApply: true` | `gamma` |\n"
        '| `paths: ["**"]` | `delta` |\n'
    )
    assert parse_doctrine_table(doc) == {"alpha", "beta", "gamma", "delta"}


def test_library_skill_loading_sentence_matches_reality() -> None:
    always, code = parse_library_sentence(LIBRARY_SKILL.read_text(encoding="utf-8"))
    measured = measured_always_on()
    assert always | code == BOOK_RULES, (
        f"library sentence names {sorted(always | code)}, expected {sorted(BOOK_RULES)}"
    )
    assert always == BOOK_RULES & measured, (
        f"sentence claims {sorted(always)} load every turn; "
        f"measured always-on book rules are {sorted(BOOK_RULES & measured)}"
    )
    assert not code & measured, (
        f"sentence claims {sorted(code & measured)} load on code files only, but they are always-on"
    )


def test_library_sentence_parser_rejects_an_unexpected_shape() -> None:
    with pytest.raises(ValueError, match="expected shape"):
        parse_library_sentence("For the everyday default, read whatever you like.")


def test_library_sentence_parser_splits_both_groups() -> None:
    parsed = parse_library_sentence(
        "For the everyday default, alpha loads on every turn and beta and "
        "gamma load on code files; open a reference here only when needed."
    )
    assert parsed == ({"alpha"}, {"beta", "gamma"})


# --- Numeric claims -------------------------------------------------------
#
# The membership guards above catch a rule joining or leaving the always-on
# set. They do not catch the byte and file-count figures going stale, which is
# the more common drift: a rule grows by 400 bytes and every number quoted in
# the doctrine is silently wrong. These guards pin each stated figure to a live
# measurement so the doc and the tree cannot diverge.
#
# Measurement reuses `instruction_budget.py` rather than reimplementing it. A
# guard with its own summing logic agrees with itself, not with the tool the
# repo actually enforces.

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


def test_doctrine_always_on_figures_match_the_measured_mirror() -> None:
    figures = parse_doctrine_figures(DOCTRINE.read_text(encoding="utf-8"))
    result = _budget(".md")
    assert (figures["mirror_files"], figures["mirror_bytes"]) == (
        len(result.matched_files),
        result.total_bytes,
    ), (
        f"doctrine states {figures['mirror_files']} rules / "
        f"{figures['mirror_bytes']} bytes always-on; measured "
        f"{len(result.matched_files)} / {result.total_bytes}"
    )


def test_doctrine_python_figures_match_the_measured_mirror() -> None:
    figures = parse_doctrine_figures(DOCTRINE.read_text(encoding="utf-8"))
    result = _budget(".py")
    assert (figures["py_files"], figures["py_bytes"]) == (
        len(result.matched_files),
        result.total_bytes,
    ), (
        f"doctrine states a `.py` edit sees {figures['py_files']} files / "
        f"{figures['py_bytes']} bytes; measured "
        f"{len(result.matched_files)} / {result.total_bytes}"
    )


def test_doctrine_source_basis_figure_and_delta_are_consistent() -> None:
    """The doc quotes two bases; both, and the gap between them, must hold."""
    figures = parse_doctrine_figures(DOCTRINE.read_text(encoding="utf-8"))
    result = _budget(".md")
    measured_source = _source_bytes(result.matched_files)
    assert figures["source_bytes"] == measured_source, (
        f"doctrine states {figures['source_bytes']} bytes at source; measured {measured_source}"
    )
    assert figures["source_delta"] == measured_source - result.total_bytes, (
        f"doctrine states a {figures['source_delta']}-byte gap between source "
        f"and mirror; measured {measured_source - result.total_bytes}"
    )


def test_doctrine_plugin_tree_figures_match_the_shipped_tree() -> None:
    """The plugin tree must match `.github/instructions`; pin both sides."""
    figures = parse_doctrine_figures(DOCTRINE.read_text(encoding="utf-8"))
    plugin_tree = REPO_ROOT / "src" / "copilot-cli" / "instructions"
    files, total = _tree_always_on(plugin_tree)
    assert (figures["plugin_files"], figures["plugin_bytes"]) == (files, total), (
        f"doctrine states the plugin tree carries {figures['plugin_files']} "
        f"rules / {figures['plugin_bytes']} bytes always-on; measured "
        f"{files} / {total}"
    )
    repo_files, repo_total = _tree_always_on(MIRROR_DIR)
    assert (files, total) == (repo_files, repo_total), (
        "the plugin tree diverged from `.github/instructions` "
        f"({files} rules / {total} bytes versus {repo_files} / {repo_total}). "
        "Before issue #4317 an internal-only glob was dropped rather than "
        "skipped, leaving an empty scope that defaulted to `**`, so a "
        "repository-internal rule shipped to every consumer as always-on. "
        "A gap here means that failure direction has returned: find the rule "
        "present in one tree and not the other, and check its source scope."
    )


def test_doctrine_8kb_multipliers_match_the_measured_source_sizes() -> None:
    figures = parse_doctrine_figures(DOCTRINE.read_text(encoding="utf-8"))
    always = _source_bytes(_budget(".md").matched_files) / _EIGHT_KB
    code = _source_bytes(_budget(".py").matched_files) / _EIGHT_KB
    assert round(always, 1) == figures["always_multiplier"], (
        f"doctrine states {figures['always_multiplier']}x the 8KB threshold; "
        f"measured {round(always, 1)}x"
    )
    assert round(code, 1) == figures["code_multiplier"], (
        f"doctrine states a Python edit sees {figures['code_multiplier']}x; "
        f"measured {round(code, 1)}x"
    )


def test_doctrine_largest_always_on_rule_matches_the_source_tree() -> None:
    """The doctrine names one rule as the biggest and states its size.

    Both halves are checked. Asserting only the byte count would let the doc
    keep naming `voice.md` after another rule overtook it; asserting only the
    name would let the figure drift. This figure went stale while every
    aggregate above stayed correct, precisely because no test read it.
    """
    figures = parse_doctrine_figures(DOCTRINE.read_text(encoding="utf-8"))
    sizes = {
        name.replace(".instructions.md", ".md"): len(
            (REPO_ROOT / ".claude" / "rules" / name.replace(".instructions.md", ".md")).read_bytes()
        )
        for name in _budget(".md").matched_files
    }
    largest_name, largest_bytes = max(sizes.items(), key=lambda kv: kv[1])
    assert largest_name == "voice.md", (
        f"doctrine names `voice.md` as the biggest always-on rule; measured {largest_name}"
    )
    assert figures["largest_bytes"] == largest_bytes, (
        f"doctrine states `voice.md` is {figures['largest_bytes']} bytes; "
        f"measured {largest_bytes}"
    )


@pytest.mark.parametrize(
    ("pattern", "label"),
    [
        (_FIG_MIRROR, "always-on"),
        (_FIG_PY, "`.py` effective"),
        (_FIG_SOURCE, "source-basis"),
        (_FIG_PLUGIN, "plugin-tree"),
        (_FIG_MULTIPLIERS, "8KB multiplier"),
        (_FIG_LARGEST, "largest always-on rule"),
    ],
)
def test_figure_parser_rejects_prose_with_a_figure_removed(
    pattern: re.Pattern[str], label: str
) -> None:
    """Rewording any one figure sentence must raise, never silently pass.

    Every numeric test in this file reads its expected value out of the prose.
    If a reworded sentence made the parser return a partial dict instead of
    raising, those tests would compare against a stale or absent figure and go
    green while the doc drifted. Each of the five patterns is checked because
    a single-pattern test leaves the other four free to fail open.
    """
    text = DOCTRINE.read_text(encoding="utf-8")
    stripped = pattern.sub("prose with the figure removed", text)
    assert stripped != text, f"{label} pattern did not match the doc; test is vacuous"
    with pytest.raises(ValueError, match=re.escape(label)):
        parse_doctrine_figures(stripped)


# ---------------------------------------------------------------------------
# The same corpus figures restated outside the doctrine.
#
# The guards above read two files. Two more documents state the same numbers in
# their own prose, and both went stale for months while the doctrine was being
# corrected, because nothing read them. Membership and byte totals are cheap to
# measure, so pin every place that claims them rather than one place.
# ---------------------------------------------------------------------------

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


@pytest.mark.parametrize(("doc", "path"), CORPUS_PROSE_DOCS)
def test_corpus_prose_table_matches_both_measured_trees(doc: str, path: Path) -> None:
    """Each document's two-row table must match what each tree actually holds."""
    figures = parse_corpus_prose(path.read_text(encoding="utf-8"), doc)
    for tree, key in ((MIRROR_DIR, "mirror"), (PLUGIN_DIR, "plugin")):
        measured = _tree_always_on(tree)
        assert (figures[f"{key}_files"], figures[f"{key}_bytes"]) == measured, (
            f"{doc} states {figures[f'{key}_files']} rules / "
            f"{figures[f'{key}_bytes']} bytes for {tree.name}; measured {measured}"
        )


@pytest.mark.parametrize(("doc", "path"), CORPUS_PROSE_DOCS)
def test_corpus_prose_membership_matches_the_measured_set(doc: str, path: Path) -> None:
    """The enumerated names must be exactly the always-on set, not a subset."""
    figures = parse_corpus_prose(path.read_text(encoding="utf-8"), doc)
    measured = measured_always_on()
    assert figures["members"] == measured, (
        f"{doc} names {sorted(figures['members'])}; measured {sorted(measured)}"
    )


@pytest.mark.parametrize(("doc", "path"), CORPUS_PROSE_DOCS)
def test_corpus_prose_source_basis_and_delta_are_consistent(doc: str, path: Path) -> None:
    """Both bases and the gap between them must hold, or the basis note misleads."""
    figures = parse_corpus_prose(path.read_text(encoding="utf-8"), doc)
    _, mirror_bytes = _tree_always_on(MIRROR_DIR)
    result = _budget(".md")
    measured_source = _source_bytes(result.matched_files)
    assert figures["source_bytes"] == measured_source, (
        f"{doc} states {figures['source_bytes']} bytes at source; measured {measured_source}"
    )
    assert figures["source_delta"] == measured_source - mirror_bytes, (
        f"{doc} states a {figures['source_delta']}-byte source-to-mirror gap; "
        f"measured {measured_source - mirror_bytes}"
    )


@pytest.mark.parametrize(("doc", "path"), CORPUS_PROSE_DOCS)
def test_corpus_prose_tree_file_counts_match_the_generated_trees(doc: str, path: Path) -> None:
    """The 23-against-27 gap is the intentional internal-scope skip; pin both."""
    figures = parse_corpus_prose(path.read_text(encoding="utf-8"), doc)
    measured_plugin = len(list(PLUGIN_DIR.glob("*.instructions.md")))
    measured_mirror = len(list(MIRROR_DIR.glob("*.instructions.md")))
    assert (figures["plugin_file_count"], figures["mirror_file_count"]) == (
        measured_plugin,
        measured_mirror,
    ), (
        f"{doc} states the plugin ships {figures['plugin_file_count']} files against "
        f"{figures['mirror_file_count']}; measured {measured_plugin} and {measured_mirror}"
    )


@pytest.mark.parametrize(("doc", "path"), CORPUS_PROSE_DOCS)
@pytest.mark.parametrize(("pattern", "label"), _PROSE_PATTERNS)
def test_corpus_prose_parser_rejects_a_removed_claim(
    pattern: re.Pattern[str], label: str, doc: str, path: Path
) -> None:
    """Removing any one claim must raise, never yield a partial dict.

    Both documents are parsed by the same function, so a pattern that silently
    failed to match would take every assertion above with it in one direction:
    green, with nothing compared. Check each pattern against each document.
    """
    text = _normalized(path.read_text(encoding="utf-8"))
    stripped = pattern.sub("prose with the claim removed", text)
    assert stripped != text, f"{label} pattern did not match {doc}; test is vacuous"
    with pytest.raises(ValueError, match=re.escape(label)):
        parse_corpus_prose(stripped, doc)


@pytest.mark.parametrize(("doc", "path"), CORPUS_PROSE_DOCS)
def test_corpus_prose_parser_rejects_a_removed_table_row(doc: str, path: Path) -> None:
    """The table rows are built per tree, so cover them with their own case."""
    text = _normalized(path.read_text(encoding="utf-8"))
    stripped = _prose_table_row("src/copilot-cli/instructions").sub("row removed", text)
    assert stripped != text, f"plugin row did not match {doc}; test is vacuous"
    with pytest.raises(ValueError, match=re.escape("src/copilot-cli/instructions table row")):
        parse_corpus_prose(stripped, doc)


def test_corpus_prose_membership_parser_rejects_a_shortened_list() -> None:
    """A dropped name must fail, not pass as a subset that happens to overlap."""
    text = _normalized(CANONICAL_MIRROR_RULE.read_text(encoding="utf-8"))
    shortened = text.replace("`universal`, `voice`.", "`universal`.")
    assert shortened != text, "membership sentence shape changed; test is vacuous"
    figures = parse_corpus_prose(shortened, "shortened")
    assert figures["members"] != measured_always_on(), (
        "dropping a name from the sentence still matched the measured set; "
        "the membership assertion cannot fail and is vacuous"
    )
