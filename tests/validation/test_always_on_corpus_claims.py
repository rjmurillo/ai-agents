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
`paths:` to `applyTo:`, and synthesizes `applyTo: "**"` for a rule that
declares no scope or whose globs are all filtered out as internal-only. Those
last two paths reach the always-on corpus with no source line to grep, so the
mirror is authoritative for membership.
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


def _search(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    match = pattern.search(text)
    if not match:
        raise ValueError(
            f"doctrine {label} figure did not match the expected prose shape; "
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
    """The plugin tree diverges from `.github/instructions`; pin both sides."""
    figures = parse_doctrine_figures(DOCTRINE.read_text(encoding="utf-8"))
    plugin_tree = REPO_ROOT / "src" / "copilot-cli" / "instructions"
    files, total = _tree_always_on(plugin_tree)
    assert (figures["plugin_files"], figures["plugin_bytes"]) == (files, total), (
        f"doctrine states the plugin tree carries {figures['plugin_files']} "
        f"rules / {figures['plugin_bytes']} bytes always-on; measured "
        f"{files} / {total}"
    )
    repo_files, repo_total = _tree_always_on(MIRROR_DIR)
    assert (files, total) != (repo_files, repo_total), (
        "the two instruction trees no longer diverge, so the passage "
        "explaining why they differ is obsolete"
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


AUDIT_PROCEDURE = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "context-optimizer"
    / "references"
    / "rule-audit-procedure.md"
)
RULES_DIR = REPO_ROOT / ".claude" / "rules"

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

_AUDIT_CORPUS = re.compile(r"(?P<word>[A-Za-z]+)\s+rules\s+is\s+the\s+corpus")
_AUDIT_DELTA = re.compile(r"total\s+(?P<n>[\d,]+)\s+bytes\s+less\s+than\s+the")
_AUDIT_APPLYTO_FORM = re.compile(r"`applyTo:\s*'\*\*'`\s*\((?P<word>[a-z]+)\s+rules?\)")
_AUDIT_ALWAYSAPPLY_FORM = re.compile(r"`alwaysApply: true`\s*\((?P<word>[a-z]+),")
_AUDIT_PATHS_FORM = re.compile(r"`paths:`\s*carrying\s*`\*\*`\s*\((?P<word>[a-z]+),")
_AUDIT_RULE_SIZE = re.compile(r"`(?P<rule>[a-z0-9-]+)\.md`\s*\((?P<n>[\d,]+) bytes\)")
_AUDIT_PRIORITY_DELTA = re.compile(r"carry\s+it,\s+worth\s+(?P<n>[\d,]+)\s+bytes")
_AUDIT_REWRITE_DELTA = re.compile(r"worth\s+the\s+remaining\s+(?P<n>[\d,]+)\s+bytes")

_AUDIT_FIGURES = (
    (_AUDIT_CORPUS, "corpus size"),
    (_AUDIT_DELTA, "mirror byte delta"),
    (_AUDIT_PRIORITY_DELTA, "priority strip"),
    (_AUDIT_REWRITE_DELTA, "alwaysApply rewrite"),
    (_AUDIT_APPLYTO_FORM, "applyTo form count"),
    (_AUDIT_ALWAYSAPPLY_FORM, "alwaysApply form count"),
    (_AUDIT_PATHS_FORM, "paths form count"),
)


def _to_int(raw: str) -> int:
    """Return the integer for a digit run with commas or an English number word."""
    cleaned = raw.replace(",", "").strip()
    if cleaned.isdigit():
        return int(cleaned)
    word = _NUMBER_WORDS.get(cleaned.lower())
    if word is None:
        raise ValueError(f"unrecognized number {raw!r}")
    return word


def parse_audit_figures(text: str) -> dict[str, int]:
    """Return the scalar claims the audit procedure states in prose.

    Raises `ValueError` naming the missing figure so a reworded sentence fails
    loudly rather than letting a downstream assertion compare against a figure
    that is no longer present.
    """
    figures: dict[str, int] = {}
    for pattern, label in _AUDIT_FIGURES:
        match = pattern.search(text)
        if not match:
            raise ValueError(f"{label} sentence did not match the expected shape")
        group = match.groupdict()
        figures[label] = _to_int(group.get("word") or group["n"])
    return figures


def parse_audit_rule_sizes(text: str) -> dict[str, int]:
    """Return the per-rule byte figures the audit procedure quotes."""
    sizes = {m.group("rule"): _to_int(m.group("n")) for m in _AUDIT_RULE_SIZE.finditer(text)}
    if not sizes:
        raise ValueError("per-rule byte figures did not match the expected shape")
    return sizes


def _declared_forms(front: dict[str, object]) -> list[str]:
    """Return every always-on convention a single rule's frontmatter declares.

    Returns a list rather than a first match so a rule carrying two conventions
    is visible. `measured_source_forms` sums these, and the corpus-sum
    assertion only detects a non-disjoint form if that rule is counted twice.
    """
    forms: list[str] = []
    applyto = front.get("applyTo")
    paths = front.get("paths")
    if isinstance(applyto, str) and applyto.strip() == "**":
        forms.append("applyTo form count")
    if front.get("alwaysApply") is True:
        forms.append("alwaysApply form count")
    if isinstance(paths, list) and any(str(p).strip() == "**" for p in paths):
        forms.append("paths form count")
    return forms


def measured_source_forms() -> dict[str, int]:
    """Return how many source rules declare always-on scope by each convention.

    Counts the source tree rather than the mirror because the audit procedure
    makes a claim about the source declaration conventions, which
    `generate_rules.py` collapses into a single `applyTo` on the way out.
    """
    counts = {"applyTo form count": 0, "alwaysApply form count": 0, "paths form count": 0}
    for path in sorted(RULES_DIR.glob("*.md")):
        front = _frontmatter(path.read_text(encoding="utf-8"))
        for form in _declared_forms(front):
            counts[form] += 1
    return counts


def measured_multi_form_rules() -> dict[str, list[str]]:
    """Return rules declaring always-on scope more than one way, by rule id."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(RULES_DIR.glob("*.md")):
        forms = _declared_forms(_frontmatter(path.read_text(encoding="utf-8")))
        if len(forms) > 1:
            offenders[path.stem] = forms
    return offenders


def measured_delta_split() -> dict[str, int]:
    """Return the mirror byte delta split by which frontmatter rewrite caused it.

    `generate_rules.py` performs two distinct transformations. Attributing the
    whole delta to either one is the error this split exists to keep out of the
    procedure's prose.
    """
    split = {"priority strip": 0, "alwaysApply rewrite": 0}
    for rule_id in measured_always_on():
        source = RULES_DIR / f"{rule_id}.md"
        mirror = MIRROR_DIR / f"{rule_id}.instructions.md"
        delta = source.stat().st_size - mirror.stat().st_size
        if not delta:
            continue
        front = _frontmatter(source.read_text(encoding="utf-8"))
        key = "priority strip" if "priority" in front else "alwaysApply rewrite"
        split[key] += delta
    return split


def measured_mirror_delta() -> int:
    """Return source bytes minus mirror bytes across the always-on corpus."""
    total = 0
    for rule_id in measured_always_on():
        source = RULES_DIR / f"{rule_id}.md"
        mirror = MIRROR_DIR / f"{rule_id}.instructions.md"
        total += source.stat().st_size - mirror.stat().st_size
    return total


def test_audit_procedure_corpus_size_matches_measurement() -> None:
    """The doc has stated a stale corpus size twice; this is the third guard."""
    claimed = parse_audit_figures(AUDIT_PROCEDURE.read_text(encoding="utf-8"))
    assert claimed["corpus size"] == len(measured_always_on()), (
        f"audit procedure claims {claimed['corpus size']} always-on rules; "
        f"measured {len(measured_always_on())} from {MIRROR_DIR}"
    )


def test_audit_procedure_form_counts_match_source_frontmatter() -> None:
    claimed = parse_audit_figures(AUDIT_PROCEDURE.read_text(encoding="utf-8"))
    measured = measured_source_forms()
    for label, count in measured.items():
        assert claimed[label] == count, (
            f"audit procedure claims {claimed[label]} rules use the {label}; measured {count}"
        )


def test_audit_procedure_form_counts_sum_to_the_corpus() -> None:
    """Three disjoint conventions must account for every always-on rule.

    A form that stopped being disjoint, or a fourth convention nobody added to
    the survey, is exactly the failure the doc warns about and would otherwise
    go unnoticed.
    """
    measured = measured_source_forms()
    assert sum(measured.values()) == len(measured_always_on()), (
        f"source forms sum to {sum(measured.values())} but the mirror reports "
        f"{len(measured_always_on())} always-on rules; a rule declares scope some other way"
    )


def test_audit_procedure_mirror_delta_matches_measurement() -> None:
    claimed = parse_audit_figures(AUDIT_PROCEDURE.read_text(encoding="utf-8"))
    assert claimed["mirror byte delta"] == measured_mirror_delta(), (
        f"audit procedure claims the mirrors total {claimed['mirror byte delta']} bytes "
        f"less than source; measured {measured_mirror_delta()}"
    )


_EXPECTED_QUOTED_RULES = frozenset({"code-quality", "voice", "pragmatic-programmer"})


def test_audit_procedure_rule_sizes_match_the_files() -> None:
    sizes = parse_audit_rule_sizes(AUDIT_PROCEDURE.read_text(encoding="utf-8"))
    assert set(sizes) == _EXPECTED_QUOTED_RULES, (
        f"audit procedure quotes byte figures for {sorted(sizes)}; expected "
        f"{sorted(_EXPECTED_QUOTED_RULES)}. A dropped or misspelled rule name would "
        "otherwise leave its figure unchecked"
    )
    for rule_id, claimed in sizes.items():
        source = RULES_DIR / f"{rule_id}.md"
        assert source.exists(), f"audit procedure quotes {rule_id}.md, which does not exist"
        assert claimed == source.stat().st_size, (
            f"audit procedure quotes {rule_id}.md at {claimed} bytes; "
            f"the file is {source.stat().st_size}"
        )


def test_audit_rule_size_parser_finds_the_quoted_rules() -> None:
    """A parser matching nothing would make the size test vacuously green."""
    sizes = parse_audit_rule_sizes(AUDIT_PROCEDURE.read_text(encoding="utf-8"))
    assert "code-quality" in sizes, f"expected code-quality among {sorted(sizes)}"


def test_audit_rule_size_parser_rejects_prose_with_no_figures() -> None:
    with pytest.raises(ValueError, match="expected shape"):
        parse_audit_rule_sizes("# doc\n\nNo rule carries a byte figure here.\n")


@pytest.mark.parametrize(
    ("pattern", "label"),
    [(pattern, label) for pattern, label in _AUDIT_FIGURES],
)
def test_audit_figure_parser_rejects_prose_with_a_figure_removed(
    pattern: re.Pattern[str], label: str
) -> None:
    """Rewording any one figure sentence must raise, never silently pass."""
    text = AUDIT_PROCEDURE.read_text(encoding="utf-8")
    stripped = pattern.sub("prose with the figure removed", text)
    assert stripped != text, f"{label} pattern did not match the doc; test is vacuous"
    with pytest.raises(ValueError, match=re.escape(label)):
        parse_audit_figures(stripped)


def test_number_word_parser_handles_both_forms() -> None:
    assert _to_int("8") == 8
    assert _to_int("70,510") == 70510
    assert _to_int("Eight") == 8
    with pytest.raises(ValueError, match="unrecognized number"):
        _to_int("several")


def test_no_source_rule_declares_always_on_scope_more_than_once() -> None:
    """A rule using two conventions makes the form counts sum past the corpus.

    The sum assertion above catches that, but reports it as a phantom fourth
    convention. This names the actual rule so the next reader is not sent
    looking for a form that does not exist.
    """
    offenders = measured_multi_form_rules()
    assert not offenders, (
        "these rules declare always-on scope more than one way, which double counts "
        f"them in the form survey: {offenders}"
    )


def test_multi_form_detector_sees_a_rule_using_two_conventions() -> None:
    """Negative control: the detector returned empty, so prove it can be non-empty."""
    both = _declared_forms({"applyTo": "**", "alwaysApply": True})
    assert both == ["applyTo form count", "alwaysApply form count"]
    assert _declared_forms({"applyTo": "src/**"}) == []
    assert _declared_forms({"paths": ["**"]}) == ["paths form count"]


def test_audit_procedure_delta_split_matches_the_two_rewrites() -> None:
    """The doc attributed the whole delta to one rewrite; there are two."""
    claimed = parse_audit_figures(AUDIT_PROCEDURE.read_text(encoding="utf-8"))
    measured = measured_delta_split()
    for label, count in measured.items():
        assert claimed[label] == count, (
            f"audit procedure attributes {claimed[label]} bytes to the {label}; measured {count}"
        )


def test_audit_procedure_delta_split_accounts_for_the_whole_delta() -> None:
    """Two parts that do not sum to the total mean a third rewrite went unnoticed."""
    measured = measured_delta_split()
    assert sum(measured.values()) == measured_mirror_delta(), (
        f"the two named rewrites account for {sum(measured.values())} bytes but the "
        f"mirrors are {measured_mirror_delta()} bytes smaller; a third transformation exists"
    )
