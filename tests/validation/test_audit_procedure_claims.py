"""Guard the scalar claims in the context-optimizer rule-audit procedure.

`.claude/skills/context-optimizer/references/rule-audit-procedure.md` states
figures in prose: the corpus size, the byte delta between source rules and
their generated mirrors, how many rules use each always-on declaration form,
and per-rule byte sizes. Every one of those goes stale the moment a rule is
added, removed, or edited, and the doc has shipped a stale corpus size twice.

These guards parse the prose and compare it against the tree. A reworded
sentence raises rather than silently passing, so a figure cannot go unchecked
by disappearing.

Split from `test_always_on_corpus_claims.py`, which guards a different
document (`model-context-doctrine.md`). The shared measurement helpers are
imported from that module rather than duplicated, so the two guards cannot
drift on what "always-on" means.
"""

from __future__ import annotations

import re
import sys

import pytest

from tests.validation.always_on_corpus_helpers import _frontmatter
from tests.validation.test_always_on_corpus_claims import (
    MIRROR_DIR,
    REPO_ROOT,
    measured_always_on,
)

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
    "zero": 0,
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
        f"{len(measured_always_on())} always-on rules; a rule declares always-on "
        "scope more than one way, or a fourth convention exists"
    )


def test_form_sum_failure_message_names_double_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-disjoint form should not be reported only as a missing convention."""
    monkeypatch.setattr(
        sys.modules[__name__],
        "measured_source_forms",
        lambda: {
            "applyTo form count": 1,
            "alwaysApply form count": 1,
            "paths form count": 0,
        },
    )
    monkeypatch.setattr(sys.modules[__name__], "measured_always_on", lambda: {"code-quality"})

    with pytest.raises(AssertionError) as excinfo:
        test_audit_procedure_form_counts_sum_to_the_corpus()

    assert "more than one way" in str(excinfo.value)


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
