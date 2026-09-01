"""``--base-ref`` handling in ``scripts/validation/checks_ratchet.py``.

Split out of ``test_pre_pr_runs_lefthook_ratchets.py`` to keep both files
under the taste-lints 500-line ceiling (issue #5441 review; same reasoning as
``test_checks_ratchet_merge_tree_backstop.py``'s own split).

Coverage:

- ``build_command`` appends ``--base-ref`` only for a ``Ratchet`` that
  declares ``uses_base_ref=True``, exercised against a synthetic entry since
  neither entry left in ``RATCHETS`` after issue #5441 sets that flag (the
  five that did moved to ``merge_tree_ratchet_registry.py``).
- ``skip_merge_tree=True`` resolves no base ref at all: neither remaining
  RATCHETS entry consumes one and the merge-tree backstop that would is
  itself skipped in this mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ratchet  # noqa: E402


class TestBuildCommandBaseRef:
    def test_adds_base_ref_when_required(self) -> None:
        """A synthetic ``Ratchet``, not a live one: see module docstring."""
        ratchet = checks_ratchet.Ratchet(
            "synthetic-base-ref-ratchet", "scripts/ci/does_not_run.py", False, True
        )
        command = checks_ratchet.build_command(ratchet, "origin/main")
        assert command[-2:] == ["--base-ref", "origin/main"]

    def test_omits_base_ref_when_not_required(self) -> None:
        """Negative control for the assertion above."""
        ratchet = checks_ratchet.Ratchet(
            "synthetic-no-base-ref-ratchet", "scripts/ci/does_not_run.py", False, False
        )
        command = checks_ratchet.build_command(ratchet, "origin/main")
        assert "--base-ref" not in command


class TestSkipMergeTreeBaseRef:
    def test_never_resolves_base_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """See module docstring: skip_merge_tree needs no base ref at all."""

        def fail_refresh(*_a: object, **_k: object) -> str:
            raise AssertionError("must not be called when skip_merge_tree=True")

        monkeypatch.setattr(checks_ratchet, "_refresh_remote_base", fail_refresh)
        monkeypatch.setattr(checks_ratchet, "_run_subprocess", lambda *_a, **_k: (0, "", ""))
        assert (
            checks_ratchet.validate_count_ratchets(REPO_ROOT, skip_merge_tree=True) is True
        )
