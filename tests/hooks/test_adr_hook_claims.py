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

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = PROJECT_ROOT / ".agents" / "architecture"
HOOKS_ROOT = PROJECT_ROOT / ".claude" / "hooks"

# A backticked path ending .py that sits under a hooks directory, spelled either
# from the repository root (.claude/hooks/Stop/x.py) or from the hooks root
# (Stop/x.py). ADR-008 uses both spellings, so both have to resolve.
_HOOK_PATH_RE = re.compile(r"`([^`]*?(?:hooks/)?[A-Za-z]\w*/invoke_[\w.-]+\.py)`")
_IMPLEMENTED_RE = re.compile(r"^\s*(?:\u2705\s*)?implemented\b", re.IGNORECASE)
_RETIRED_RE = re.compile(r"\bretired\b|\bremoved\b|\bdeleted\b|\bsuperseded\b", re.IGNORECASE)


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


def _resolves(hook_path: str) -> bool:
    # removeprefix, not lstrip: lstrip takes a character set, so lstrip("./")
    # eats the leading dot of ".claude/hooks/..." and the path stops resolving.
    candidate = hook_path.removeprefix("./")
    return (PROJECT_ROOT / candidate).is_file() or (HOOKS_ROOT / candidate).is_file()


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


class TestTheScanIsNotVacuous:
    """A parametrized check that matches nothing passes for the wrong reason."""

    def test_some_adr_claims_at_least_one_hook(self):
        total = sum(len(_claims(a.read_text(encoding="utf-8"))) for a in _adr_files())
        assert total >= 2, "no ADR row was read as a hook implementation claim"

    def test_adr_008_is_among_them(self):
        """The ADR the issue was filed against must be inside the scan."""
        adr = ADR_DIR / "ADR-008-protocol-automation-lifecycle-hooks.md"
        assert _claims(adr.read_text(encoding="utf-8"))


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
