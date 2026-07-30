"""Tests for scripts.modules.investigation_allowlist module."""

from __future__ import annotations

import importlib.util
import re
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from scripts.modules.investigation_allowlist import (
    get_investigation_allowlist,
    get_investigation_allowlist_display,
)
from scripts.modules.investigation_allowlist import (
    test_file_matches_allowlist as file_matches_allowlist,
)


class TestGetInvestigationAllowlist:
    def test_returns_non_empty_list(self) -> None:
        result = get_investigation_allowlist()
        assert len(result) > 0

    def test_patterns_are_anchored(self) -> None:
        for pattern in get_investigation_allowlist():
            assert pattern.startswith("^"), f"Pattern not anchored: {pattern}"


class TestGetInvestigationAllowlistDisplay:
    def test_returns_non_empty_list(self) -> None:
        result = get_investigation_allowlist_display()
        assert len(result) > 0

    def test_same_count_as_allowlist(self) -> None:
        assert len(get_investigation_allowlist()) == len(get_investigation_allowlist_display())


class TestFileMatchesAllowlist:
    def test_matches_sessions_path(self) -> None:
        assert file_matches_allowlist(".agents/sessions/log.json") is True

    def test_matches_analysis_path(self) -> None:
        assert file_matches_allowlist(".agents/analysis/report.md") is True

    def test_matches_serena_memories(self) -> None:
        assert file_matches_allowlist(".serena/memories/test.md") is True

    def test_rejects_source_code(self) -> None:
        assert file_matches_allowlist("src/main.py") is False

    def test_rejects_scripts(self) -> None:
        assert file_matches_allowlist("scripts/build.py") is False

    def test_normalizes_backslashes(self) -> None:
        assert file_matches_allowlist(".agents\\sessions\\log.json") is True

    def test_matches_architecture_review(self) -> None:
        assert file_matches_allowlist(".agents/architecture/REVIEW-001.md") is True

    def test_rejects_architecture_adr(self) -> None:
        assert file_matches_allowlist(".agents/architecture/ADR-001.md") is False


@lru_cache(maxsize=1)
def _load_session_skill_module() -> ModuleType:
    """Load the packaged session-skill eligibility script by path.

    The script ships to installed-plugin trees, so it keeps a verbatim copy
    of the allowlist instead of importing the repo-relative module. This
    loader lets the parity test compare the two in-repo. The result is cached
    so the script executes once across the whole test class.
    """
    script = (
        Path(__file__).resolve().parents[1]
        / ".claude"
        / "skills"
        / "session"
        / "scripts"
        / "test_investigation_eligibility.py"
    )
    assert script.is_file(), f"session-skill eligibility script missing: {script}"
    spec = importlib.util.spec_from_file_location("_session_eligibility", script)
    assert spec is not None and spec.loader is not None, (
        f"could not build import spec for {script}"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSessionSkillAllowlistParity:
    """Lock the session-skill allowlist copy to the canonical module (#2966).

    The session skill cannot import scripts.modules.investigation_allowlist at
    runtime because it is packaged into plugin trees where scripts/ is absent.
    These tests fail CI if the verbatim copy drifts from the module, which is
    the DRY gap the ADR-034 amendment deferred.
    """

    def test_patterns_match_module(self) -> None:
        skill = _load_session_skill_module()
        assert list(skill._ALLOWLIST_PATTERNS) == get_investigation_allowlist()

    def test_display_matches_module(self) -> None:
        skill = _load_session_skill_module()
        assert list(skill._ALLOWLIST_DISPLAY) == get_investigation_allowlist_display()

    def test_match_behavior_matches_module(self) -> None:
        skill = _load_session_skill_module()
        samples = [
            ".agents/sessions/log.json",
            ".agents/memory/episodes/ep.json",
            ".serena/memories/note.md",
            ".agents/architecture/REVIEW-1.md",
            ".agents/architecture/ADR-1.md",
            "src/main.py",
            "scripts/build.py",
        ]
        for path in samples:
            assert skill._file_matches_allowlist(path) == file_matches_allowlist(path), path


_PROTOCOL_PATH = Path(__file__).resolve().parents[1] / ".agents" / "SESSION-PROTOCOL.md"
_CLAUSE_MARKER = "**Investigation-only**:"
_INELIGIBLE_MARKER = "**Not investigation sessions**"
_COMMENT_MARKER = 'Investigation sessions may skip QA with evidence "SKIPPED: investigation-only"'
_ARTIFACT_PREFIXES = (".agents/", ".serena/")
_NEXT_ITEM_RE = re.compile(r"\s*[-*+]\s")
_ARTIFACT_TOKEN_RE = re.compile(r"\.(?:agents|serena)/[\w./*-]*")
_CLAUSE_ENUM_START = "limited to investigation artifacts:"
_CLAUSE_ENUM_END = ". Use evidence:"
_COMMENT_ENUM_START = "when only staging:"
_COMMENT_ENUM_END = "See ADR-034"


def _protocol_text() -> str:
    return _PROTOCOL_PATH.read_text(encoding="utf-8")


def _investigation_only_clause() -> str:
    """Return the whole clause, including hand-wrapped continuation lines.

    Reading only the marker's physical line made the parity tests fail on a
    plain line wrap, which is an authoring choice with no bearing on drift.
    """
    lines = _protocol_text().splitlines()
    for index, line in enumerate(lines):
        if _CLAUSE_MARKER in line:
            block = [line]
            for candidate in lines[index + 1 :]:
                if not candidate.strip() or _NEXT_ITEM_RE.match(candidate):
                    break
                block.append(candidate)
            return "\n".join(block)
    raise AssertionError(f"{_CLAUSE_MARKER} not found in {_PROTOCOL_PATH}")


def _checklist_comment_block() -> str:
    lines = _protocol_text().splitlines()
    for index, line in enumerate(lines):
        if _COMMENT_MARKER in line:
            block = []
            for candidate in lines[index:]:
                block.append(candidate)
                if "-->" in candidate:
                    return "\n".join(block)
            raise AssertionError("Unterminated investigation-only comment block")
    raise AssertionError(f"{_COMMENT_MARKER} not found in {_PROTOCOL_PATH}")


def _normalize_token(token: str) -> str:
    """Strip markup and trailing punctuation until the bare path remains.

    Order matters: ``**.agents/critique/**.`` ends in punctuation, so a
    single strip of ``**`` never fires. Looping until the token stops
    changing handles either order, and stripping only a trailing ``**``
    pair preserves the single ``*`` in ``.agents/architecture/REVIEW-*``.
    """
    previous = None
    while token != previous:
        previous = token
        token = token.strip().strip("`").strip()
        token = token.rstrip(".,`")
        if token.startswith("**"):
            token = token[2:]
        if token.endswith("**"):
            token = token[:-2]
    return token


def _artifact_paths(text: str) -> set[str]:
    """Collect allowlist-shaped path tokens regardless of their delimiters.

    The earlier form required a backtick, space, or comma immediately before
    the path, so emphasising a path (``**.agents/critique/**``) silently
    dropped it. Matching the path itself keeps the tests keyed to content
    rather than to one particular way of marking it up.
    """
    found = {_normalize_token(token) for token in _ARTIFACT_TOKEN_RE.findall(text)}
    return {t for t in found if t.startswith(_ARTIFACT_PREFIXES)}


def _enumerated_paths(text: str, start: str, end: str) -> set[str]:
    """Return every item the enumeration between two markers names.

    Unlike :func:`_artifact_paths` this applies no prefix filter, so a path
    the module rejects (``src/``) is still collected. That is what lets the
    caller assert equality and catch a widened allowlist. The span is a bare
    comma-separated list in both places it appears, so surrounding prose,
    including a deliberate contrast example, stays outside it.
    """
    normalized = " ".join(text.split())
    head, marker, tail = normalized.partition(start)
    assert marker, f"enumeration start {start!r} not found"
    body, marker, _ = tail.partition(end)
    assert marker, f"enumeration end {end!r} not found"
    return {token for token in (_normalize_token(item) for item in body.split(",")) if token}


class TestSessionProtocolAllowlistParity:
    """Lock SESSION-PROTOCOL.md's prose allowlist to the canonical module.

    The ADR-034 amendment (2026-07-08) reconciled the allowlist to 8 patterns
    and named its deferred follow-ups. SESSION-PROTOCOL.md was not among them,
    so it kept teaching the original 5 while CI accepted 8. Agents read the
    protocol, not the module, so the prose is load-bearing and must not drift.

    These assertions work in two layers. The enumeration spans are checked
    for equality, which catches a dropped pattern and an invented one alike;
    a widened prose allowlist is the dangerous direction, because agents read
    the protocol and would take `src/` as exempt from QA. The surrounding
    clause is checked for containment, because equality over the whole clause
    also failed when the protocol named a not-allowed path for contrast,
    which is prose the protocol legitimately wants.
    """

    def test_clause_enumerates_exactly_the_allowlist(self) -> None:
        assert _enumerated_paths(
            _investigation_only_clause(), _CLAUSE_ENUM_START, _CLAUSE_ENUM_END
        ) == set(get_investigation_allowlist_display())

    def test_checklist_comment_enumerates_exactly_the_allowlist(self) -> None:
        assert _enumerated_paths(
            _checklist_comment_block(), _COMMENT_ENUM_START, _COMMENT_ENUM_END
        ) == set(get_investigation_allowlist_display())

    def test_clause_lists_every_allowlisted_path(self) -> None:
        assert set(get_investigation_allowlist_display()) <= _artifact_paths(
            _investigation_only_clause()
        )

    def test_checklist_comment_lists_every_allowlisted_path(self) -> None:
        assert set(get_investigation_allowlist_display()) <= _artifact_paths(
            _checklist_comment_block()
        )

    def test_clause_omits_paths_the_module_rejects(self) -> None:
        for rejected in (".agents/planning/", ".agents/qa/", ".agents/roadmap/"):
            assert file_matches_allowlist(f"{rejected}doc.md") is False

    def test_clause_scopes_architecture_to_the_review_prefix(self) -> None:
        clause = _artifact_paths(_investigation_only_clause())
        assert ".agents/architecture/REVIEW-*" in clause
        assert ".agents/architecture/" not in clause
        assert file_matches_allowlist(".agents/architecture/ADR-1.md") is False


class TestParityExtractionIsFormattingAgnostic:
    """Pin the parity helpers against authoring changes that carry no drift.

    The first version of these helpers read one physical line and required a
    backtick, space, or comma before each path. A line wrap, a contrast
    clarifier, and a bolded path each produced a failure with no drift behind
    it. Each case below reproduces one of those and asserts it now passes,
    with a negative control proving the helper still detects a real drop.
    """

    def test_wrapped_clause_keeps_continuation_lines(self) -> None:
        clause = _investigation_only_clause()
        assert _CLAUSE_MARKER in clause
        assert "**Docs-only**" not in clause

    def test_bolded_path_is_still_extracted(self) -> None:
        assert _artifact_paths("**.agents/critique/**") == {".agents/critique/"}

    def test_bolded_path_before_punctuation_is_extracted(self) -> None:
        assert _artifact_paths("**.agents/critique/**. Use evidence") == {
            ".agents/critique/"
        }

    def test_bold_stripping_preserves_the_review_glob(self) -> None:
        assert _artifact_paths("**.agents/architecture/REVIEW-***") == {
            ".agents/architecture/REVIEW-*"
        }

    def test_naming_a_rejected_path_for_contrast_does_not_break_parity(self) -> None:
        text = _investigation_only_clause() + " Do not stage `.agents/planning/`."
        assert set(get_investigation_allowlist_display()) <= _artifact_paths(text)

    def test_dropping_a_pattern_still_fails(self) -> None:
        text = _investigation_only_clause().replace("`.agents/critique/`", "")
        assert not set(get_investigation_allowlist_display()) <= _artifact_paths(text)

    def test_widening_the_enumeration_fails(self) -> None:
        """A path the module rejects must not be able to appear as allowed.

        Containment alone accepted this, so the protocol could have taught
        that staging `src/` still earns the QA exemption while every other
        assertion stayed green. This is the direction that actually costs
        something, so it gets its own control.
        """
        text = _investigation_only_clause().replace(
            "`.agents/critique/`. Use evidence:", "`.agents/critique/`, `src/`. Use evidence:"
        )
        assert "`src/`" in text, "mutation did not apply"
        assert _enumerated_paths(text, _CLAUSE_ENUM_START, _CLAUSE_ENUM_END) != set(
            get_investigation_allowlist_display()
        )

    def test_narrowing_the_enumeration_fails(self) -> None:
        text = _investigation_only_clause().replace("`.agents/memory/`, ", "", 1)
        assert _enumerated_paths(text, _CLAUSE_ENUM_START, _CLAUSE_ENUM_END) != set(
            get_investigation_allowlist_display()
        )

    def test_enumeration_equality_survives_a_wrap_and_a_bold(self) -> None:
        text = _investigation_only_clause().replace(
            "`.agents/security/`, `.agents/memory/`",
            "`.agents/security/`,\n      **.agents/memory/**",
            1,
        )
        assert _enumerated_paths(text, _CLAUSE_ENUM_START, _CLAUSE_ENUM_END) == set(
            get_investigation_allowlist_display()
        )

    def test_contrast_prose_outside_the_span_is_ignored(self) -> None:
        text = _investigation_only_clause() + " Do not stage `.agents/planning/`."
        assert _enumerated_paths(text, _CLAUSE_ENUM_START, _CLAUSE_ENUM_END) == set(
            get_investigation_allowlist_display()
        )


def _ineligible_examples_block() -> str:
    """Return the 'Not investigation sessions' bullet list."""
    lines = _protocol_text().splitlines()
    for index, line in enumerate(lines):
        if _INELIGIBLE_MARKER in line:
            block = []
            for candidate in lines[index + 1 :]:
                if candidate.startswith("#"):
                    break
                block.append(candidate)
            return "\n".join(block)
    raise AssertionError(f"{_INELIGIBLE_MARKER} not found in {_PROTOCOL_PATH}")


class TestIneligibleExamplesStayConsistentWithTheAllowlist:
    """Lock the examples section that carried the original eligibility defect.

    The protocol used to list critique sessions as requiring QA while the
    module accepted `.agents/critique/`. The clause and checklist parity
    tests do not read this section, so that exact defect could return with
    every other test green. These assertions close that gap.
    """

    def test_block_is_found_and_populated(self) -> None:
        block = _ineligible_examples_block()
        assert "Implementation sessions" in block

    def test_allowlisted_artifact_kinds_are_not_called_ineligible(self) -> None:
        block = _ineligible_examples_block().lower()
        for allowed in ("critique", "review artifact", "memory-graph"):
            assert allowed not in block

    def test_adr_design_files_remain_ineligible(self) -> None:
        assert ".agents/architecture/ADR-*" in _ineligible_examples_block()
        assert file_matches_allowlist(".agents/architecture/ADR-9.md") is False

    def test_eligible_examples_name_every_amended_pattern(self) -> None:
        text = _protocol_text()
        for pattern in (".agents/memory/", ".agents/critique/"):
            assert pattern in text
