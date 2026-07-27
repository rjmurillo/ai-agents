"""An ADR may not mark a hook implemented when its file is absent (Issue #3373).

ADR-008 marked five hooks implemented. Three had been deleted across two
separate purges (#3184, #3349), and each purge left the ADR alone. ADR-008 is
the document a reader reaches for when asking what the lifecycle-hook surface
is, and it answered with files that are not on disk.

Correcting the prose once buys one clean read. This is the part that survives
the next purge: delete a hook without amending the ADR that claims it and this
test names both the ADR and the missing file.

Scope, and why it is not the existing ledger's job. ``AUTHORIZED_HOOKS`` in
``test_dispatch_groups_parity.py`` is bidirectional over the *live dispatch
surface*: every running hook needs an authorization and every authorization
needs a running hook. It says nothing about ADR prose, and it cannot, because a
hook can be authorized and documented in an ADR that spells its path
differently. This test is the ADR-prose half and deliberately checks only one
direction: a claim must have a file. The converse (every hook file is claimed
by some ADR) is not asserted, because hooks legitimately arrive via issues
rather than ADRs.

An ADR records what was decided, so retiring a hook does not mean deleting its
row. Mark the row retired and the row stops being a claim. That is the intended
edit, and it is why the marker and not the path is what makes a row a claim.
"""

from __future__ import annotations

import importlib.util
import re
from bisect import bisect_right
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = PROJECT_ROOT / ".agents" / "architecture"
HOOKS_ROOT = PROJECT_ROOT / ".claude" / "hooks"
HOOK_SEARCH_ROOTS = (
    HOOKS_ROOT,
    PROJECT_ROOT / "src" / "copilot-cli" / "hooks",
)

# A backticked path naming an `invoke_*.py` file directly under an event
# directory (`Stop/invoke_x.py`), optionally prefixed by the repo-relative
# hooks root (`.claude/hooks/Stop/invoke_x.py`). ADR-008 uses both spellings,
# so both have to resolve.
_HOOK_PATH_RE = re.compile(
    r"`([^`]*?(?:hooks/)?[A-Za-z]\w*/invoke_[\w.-]+\.py)(?::\d+(?:-\d+)?)?`"
)
_BACKTICKED_INVOKE_RE = re.compile(r"`([^`]*invoke_[\w.-]+\.py)(?::\d+(?:-\d+)?)?`")
_IMPLEMENTED_RE = re.compile(r"^\s*(?:\u2705\s*)?implemented\b", re.IGNORECASE)
_RETIRED_RE = re.compile(
    r"\b(?:deleted|deregistered|dropped|historical|no longer|previously|removed|"
    r"replaced|retired|superseded)\b",
    re.IGNORECASE,
)
_LIVE_REGISTRATION_RE = re.compile(
    r"\b(?:consumer-effective|enforce[sd]?|registered|registration|run(?:s|ning)?)\b"
    r"|\bstill\s+(?:exists|registered|runs|enforces)\b",
    re.IGNORECASE,
)


def _load_dispatch_groups_parity() -> ModuleType:
    path = Path(__file__).with_name("test_dispatch_groups_parity.py")
    spec = importlib.util.spec_from_file_location("test_dispatch_groups_parity", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DISPATCH_GROUPS_PARITY = _load_dispatch_groups_parity()


def _adr_files() -> list[Path]:
    return sorted(ADR_DIR.glob("ADR-*.md"))


def _claims(text: str) -> list[tuple[int, str]]:
    """(line number, hook path) for every row claiming a hook is implemented.

    A row is a claim when it names a hook path, some cell marks it implemented,
    and no cell retires it. Keying on the marker rather than the path is what
    lets an ADR keep a historical row for a hook that has since been removed.
    """
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if _RETIRED_RE.search(line):
            continue
        if not any(_IMPLEMENTED_RE.match(c) for c in cells):
            continue
        for cell in cells:
            for match in _HOOK_PATH_RE.finditer(cell):
                found.append((number, match.group(1)))
    return found


def _prose_claims(text: str) -> list[tuple[int, str]]:
    """(line number, hook token) for references without same-context retirement."""
    return [
        (number, path)
        for number, path, context in _hook_references(text)
        if not _has_retirement_marker(context)
    ]


def _hook_references(text: str) -> list[tuple[int, str, str]]:
    line_starts = [0]
    for match in re.finditer(r"\n", text):
        line_starts.append(match.end())
    found: list[tuple[int, str, str]] = []
    for match in _BACKTICKED_INVOKE_RE.finditer(text):
        line_number = bisect_right(line_starts, match.start())
        line_start = line_starts[line_number - 1]
        line_end = text.find("\n", match.start())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        context = line if line.lstrip().startswith("|") else _sentence_context(text, match)
        found.append((line_number, match.group(1), context))
    return found


def _sentence_context(text: str, match: re.Match[str]) -> str:
    starts = [marker.start() for marker in re.finditer(r"[.?!](?=\s|$)", text[: match.start()])]
    start = starts[-1] if starts else -1
    end_candidates = [
        marker.start()
        for marker in re.finditer(r"[.?!](?=\s|$)", text[match.end() :])
    ]
    end_candidates = [match.end() + position for position in end_candidates]
    end = min(end_candidates) + 1 if end_candidates else len(text)
    return text[start + 1 : end]


def _has_retirement_marker(context: str) -> bool:
    return _RETIRED_RE.search(context) is not None


@cache
def _repo_basename_exists(basename: str) -> bool:
    ignored_parts = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"}
    return any(
        path.is_file() and not (set(path.relative_to(PROJECT_ROOT).parts) & ignored_parts)
        for path in PROJECT_ROOT.rglob(basename)
    )


def _names_running_hook(hook_path: str) -> bool:
    return Path(hook_path).name in DISPATCH_GROUPS_PARITY._every_running_basename()


def _claims_live_registration(context: str) -> bool:
    return _LIVE_REGISTRATION_RE.search(context) is not None


def _resolves(hook_path: str) -> bool:
    # removeprefix, not lstrip: lstrip takes a character set, so lstrip("./")
    # eats the leading dot of ".claude/hooks/..." and the path stops resolving.
    candidate = re.sub(r":\d+(?:-\d+)?$", "", hook_path.removeprefix("./"))
    if (PROJECT_ROOT / candidate).is_file() or (HOOKS_ROOT / candidate).is_file():
        return True
    if "/" in candidate:
        return any((root / candidate).is_file() for root in HOOK_SEARCH_ROOTS)
    return any(root.joinpath(candidate).is_file() for root in HOOK_SEARCH_ROOTS) or any(
        path.is_file() for root in HOOK_SEARCH_ROOTS for path in root.glob(f"*/{candidate}")
    ) or _repo_basename_exists(candidate)


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.stem)
def test_no_adr_claims_a_hook_that_is_absent(adr: Path) -> None:
    missing = [
        f"{adr.name}:{line} claims `{path}`"
        for line, path in _claims(adr.read_text(encoding="utf-8"))
        if not _resolves(path)
    ]
    assert not missing, (
        "ADR marks a hook implemented whose file is not in the tree: "
        f"{missing}. Either restore the hook or amend the ADR: change the row's "
        "status to name the issue that retired it. Do not delete the row; an "
        "ADR records what was decided."
    )


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.stem)
def test_no_adr_prose_names_a_hook_that_is_absent_without_retirement_marker(adr: Path) -> None:
    missing = [
        f"{adr.name}:{line} names `{path}`"
        for line, path in _prose_claims(adr.read_text(encoding="utf-8"))
        if not _resolves(path)
    ]
    assert not missing, (
        "ADR prose names a hook file that is not in the tree without a same-sentence "
        f"or same-row retirement marker: {missing}. Either name the current "
        "enforcement point or mark the reference as historical in that sentence or row."
    )


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.stem)
def test_no_adr_prose_claims_an_unregistered_hook_is_live(adr: Path) -> None:
    missing = []
    for number, path, context in _hook_references(adr.read_text(encoding="utf-8")):
        if (
            not _has_retirement_marker(context)
            and _claims_live_registration(context)
            and not _names_running_hook(path)
        ):
            missing.append(f"{adr.name}:{number} claims `{path}` is live")
    assert not missing, (
        "ADR prose claims a hook is live but the hook is not in dispatch_groups "
        f"or direct settings: {missing}. Either name the current enforcement point "
        "or mark the hook reference as historical in the same sentence or row."
    )


class TestTheScanIsNotVacuous:
    """A parametrized check that matches nothing passes for the wrong reason."""

    def test_some_adr_claims_at_least_one_hook(self):
        total = sum(len(_claims(a.read_text(encoding="utf-8"))) for a in _adr_files())
        assert total >= 1, "no ADR row was read as a hook implementation claim"

    def test_adr_008_is_among_them(self):
        """The ADR the issue was filed against must be inside the scan."""
        adr = ADR_DIR / "ADR-008-protocol-automation-lifecycle-hooks.md"
        assert _claims(adr.read_text(encoding="utf-8"))

    def test_some_adr_prose_names_at_least_one_hook(self):
        total = sum(len(_prose_claims(a.read_text(encoding="utf-8"))) for a in _adr_files())
        assert total >= 1, "no ADR prose was read as a hook file reference"


class TestWhatCountsAsAClaim:
    def test_an_implemented_row_naming_a_hook_is_a_claim(self):
        row = "| Ctx | `SessionStart/invoke_context_loader.py` | SessionStart | Implemented |\n"
        assert _claims(row) == [(1, "SessionStart/invoke_context_loader.py")]

    def test_a_check_mark_prefix_is_still_implemented(self):
        row = "| Ctx | `SessionStart/invoke_context_loader.py` | S | \u2705 Implemented |\n"
        assert _claims(row) == [(1, "SessionStart/invoke_context_loader.py")]

    def test_a_retired_row_is_not_a_claim(self):
        """The intended amendment shape: keep the row, change the status."""
        row = "| Retro | `Stop/invoke_auto_retrospective.py` | Stop | Retired by #3349 |\n"
        assert _claims(row) == []

    def test_a_row_marked_both_reads_as_retired(self):
        """Retirement wins, so an amendment is never fighting a stale marker."""
        row = "| X | `Stop/invoke_auto_retrospective.py` | Implemented | Retired by #3349 |\n"
        assert _claims(row) == []

    def test_prose_outside_a_table_is_not_a_claim(self):
        """ADRs name hooks in narrative constantly; only rows carry status."""
        assert _claims("The `Stop/invoke_auto_retrospective.py` hook is Implemented.\n") == []

    def test_a_row_with_no_status_is_not_a_claim(self):
        assert _claims("| Ctx | `SessionStart/invoke_context_loader.py` | Loads context |\n") == []

    def test_a_repo_relative_path_is_read(self):
        row = "| C | `.claude/hooks/SessionStart/invoke_context_loader.py` | S | Implemented |\n"
        assert _claims(row) == [(1, ".claude/hooks/SessionStart/invoke_context_loader.py")]


class TestPathResolution:
    def test_a_hooks_root_relative_path_resolves(self):
        assert _resolves("SessionStart/invoke_context_loader.py")

    def test_a_repo_relative_path_resolves(self):
        assert _resolves(".claude/hooks/SessionStart/invoke_context_loader.py")

    def test_a_deleted_hook_does_not_resolve(self):
        """The three #3373 named, as the negative control on the whole file."""
        assert not _resolves("Stop/invoke_auto_retrospective.py")
        assert not _resolves("PreToolUse/invoke_false_completion_gate.py")
        assert not _resolves("PostToolUse/invoke_plan_state_sync.py")

    def test_a_bare_live_hook_filename_resolves(self):
        assert _resolves("invoke_context_loader.py")


class TestWhatCountsAsAProseClaim:
    def test_a_resolvable_prose_token_is_a_claim(self):
        text = "The `invoke_context_loader.py` hook runs at session start.\n"
        assert _prose_claims(text) == [(1, "invoke_context_loader.py")]

    def test_an_unresolved_unmarked_prose_token_is_a_claim(self):
        text = "The `invoke_deleted_gate.py` hook still enforces this policy.\n"
        assert _prose_claims(text) == [(1, "invoke_deleted_gate.py")]

    def test_an_unresolved_token_with_same_sentence_retirement_marker_is_suppressed(self):
        text = (
            "The retired hook `invoke_deleted_gate.py` used to enforce this policy.\n"
        )
        assert _prose_claims(text) == []

    def test_an_unresolved_token_with_only_nearby_retirement_marker_is_a_claim(self):
        text = (
            "The hook was retired by #3184.\n"
            "This paragraph still names `invoke_deleted_gate.py`.\n"
        )
        assert _prose_claims(text) == [(2, "invoke_deleted_gate.py")]

    def test_a_table_row_reference_without_retirement_marker_is_a_claim(self):
        row = "| Gate | `invoke_deleted_gate.py:66-95` | Direct | Medium |\n"
        assert _prose_claims(row) == [(1, "invoke_deleted_gate.py")]

    def test_a_table_row_reference_with_retirement_marker_is_suppressed(self):
        row = "| Gate | `invoke_deleted_gate.py:66-95` | Historical, removed | Medium |\n"
        assert _prose_claims(row) == []

    def test_line_range_suffix_is_ignored_for_resolution(self):
        assert _resolves("invoke_context_loader.py:1-2")

    def test_live_registration_claim_uses_dispatch_inventory(self):
        context = "The `invoke_context_loader.py` hook still runs."
        assert _claims_live_registration(context)
        assert _names_running_hook("invoke_context_loader.py")

    def test_a_line_range_suffix_is_stripped_and_the_reference_is_still_captured(self):
        text = "See `invoke_serena_reassertion.py:38-41` for the guard.\n"
        assert _prose_claims(text) == [(1, "invoke_serena_reassertion.py")]
