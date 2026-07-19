"""Wiring tests for the model-pin governance gate in the pre-PR runner (Issue #3073).

Covers the ADR-080 model-pin check being wired into ``pre_pr`` in warn mode:

- positive: the wrapper passes in warn mode against the real tree, and
  ``check_model_pins.py`` runs as a plain standalone script (the import-path
  bug this issue fixed);
- negative: a config-error exit (2) from the wrapped script fails the wrapper,
  and an absent script raises ``MissingScriptSkip``;
- observability: new violations that print after the long grandfathered backlog
  are not truncated away (the warn gate exists to surface them);
- edge: the sequence extraction keeps ``pre_pr.py`` under its size ceiling and
  places the new gate immediately after the spec-contradiction check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the pre-PR runner modules the way they are designed to be imported: add
# ``scripts/validation`` to ``sys.path`` and import by bare name. These modules
# self-insert their own directory and use bare intra-package imports
# (Issue #2223), so a package-path import (``from scripts.validation import ...``)
# makes mypy at repo root type-check them and surface the pre-existing #2876
# bare-Any ``no-any-return`` debt in unrelated code. The bare import keeps this
# test scoped to the wiring it verifies.
#
# The three modules resolve their sibling imports at import time (cached in
# ``sys.modules``). Do NOT snapshot-and-restore ``sys.path`` after these imports.
# Production ``pre_pr`` leaves ``scripts/validation`` on ``sys.path`` for the
# whole run, and ``checks_tooling.validate_copilot_version_pin`` performs a
# *function-local* ``from check_copilot_version_pin import EXIT_OK, check_action``
# (checks_tooling.py, #3073) that resolves by bare name at call time. Restoring
# ``sys.path`` here would remove that directory and make the lazy import fail
# with ``ModuleNotFoundError`` when this test file runs in isolation (the full
# suite masks it because test_check_copilot_version_pin.py imports the module
# first). Mirror production: insert once, leave it.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_spec  # noqa: E402
import pre_pr  # noqa: E402
import pre_pr_sequence  # noqa: E402


def test_validate_model_pins_passes_in_warn_mode() -> None:
    """Positive: warn mode reports and exits 0 against the current tree."""
    assert checks_spec.validate_model_pins(REPO_ROOT) is True


def test_validate_model_pins_fails_on_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative: a config-error exit (2) from the wrapped script fails the gate.

    Warn mode never exits nonzero on a policy violation, so a nonzero exit here
    is a real defect (an unreadable or malformed baseline or manifest) and must
    not pass.
    """
    monkeypatch.setattr(
        checks_spec, "_run_subprocess", lambda *_a, **_k: (2, "", "config error")
    )
    assert checks_spec.validate_model_pins(REPO_ROOT) is False


def test_validate_model_pins_prints_new_violations_past_backlog(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Observability: a new violation after a long backlog is not truncated.

    ``check_model_pins.py`` prints the grandfathered backlog (over a hundred
    lines) before any new violation and the footer. The wrapper must sample the
    backlog but always print the violation lines and summary, otherwise the warn
    gate reports drift the developer never sees. Regression for the flat
    head-truncation the first cut shipped.
    """
    backlog = [f"{checks_spec._MODEL_PIN_BACKLOG_PREFIX}unit-{i}" for i in range(60)]
    tail = [
        "[model-pins] VIOLATION: .claude/skills/new/SKILL.md: new pin",
        "[model-pins] 1 hard violation(s)",
        "[model-pins] warn mode: reporting only, exit 0",
    ]
    output = "\n".join(["[model-pins] scanned 60 pinned units", *backlog, *tail])
    monkeypatch.setattr(
        checks_spec, "_run_subprocess", lambda *_a, **_k: (0, output, "")
    )

    assert checks_spec.validate_model_pins(REPO_ROOT) is True

    printed = capsys.readouterr().out
    assert "VIOLATION: .claude/skills/new/SKILL.md: new pin" in printed
    assert "1 hard violation(s)" in printed
    assert "warn mode: reporting only, exit 0" in printed
    # The backlog body is sampled, not dumped in full.
    assert printed.count(checks_spec._MODEL_PIN_BACKLOG_PREFIX) < 60
    assert "additional grandfathered pins omitted" in printed


def test_check_model_pins_exits_2_on_malformed_baseline(tmp_path: Path) -> None:
    """Negative/real-subprocess: a malformed baseline is a config error (exit 2).

    Proves the exit-2 contract ``validate_model_pins`` relies on, through the
    real script rather than a stubbed return, so the config guard is grounded in
    the script's actual behavior.
    """
    bad_baseline = tmp_path / "bad_baseline.json"
    bad_baseline.write_text("{ this is not valid json", encoding="utf-8")
    script = REPO_ROOT / "scripts" / "validation" / "check_model_pins.py"
    result = subprocess.run(
        [sys.executable, str(script), "--mode", "warn", "--baseline", str(bad_baseline)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "config error" in (result.stdout + result.stderr)


def test_validate_model_pins_skips_when_script_absent(tmp_path: Path) -> None:
    """Edge: an absent check script raises the SKIP signal, not a hard failure."""
    # Use the exception class ``checks_spec`` actually raises (its bare-module
    # ``checks_common`` import), not the package-path copy, to avoid the
    # duplicate-module class-identity mismatch.
    with pytest.raises(checks_spec.MissingScriptSkip):
        checks_spec.validate_model_pins(tmp_path)


def test_pre_pr_facade_reexports_validate_model_pins() -> None:
    """Positive: ``pre_pr`` re-exports the wrapper for existing importers."""
    assert hasattr(pre_pr, "validate_model_pins")
    assert callable(pre_pr.validate_model_pins)


def test_run_all_validations_wires_model_pins_after_spec_contradiction() -> None:
    """Edge: the gate runs, and directly after the spec-contradiction check.

    Injects a recording ``run_validation`` so the ordered sequence is asserted
    without invoking the real validators. Locks the placement against an
    accidental reorder in a future refactor.
    """
    recorded: list[str] = []

    def fake_run_validation(
        name: str, _state: object, _callback: object, skip: bool = False
    ) -> bool:
        recorded.append(name)
        return True

    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    args = SimpleNamespace(quick=True, skip_tests=False, verbose=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)

    assert "Model Pin Governance (warn)" in recorded
    idx = recorded.index("Spec Contradiction Check")
    assert recorded[idx + 1] == "Model Pin Governance (warn)"


def test_check_model_pins_runs_as_standalone_script() -> None:
    """Negative/regression: the script must run outside ``-m`` and pre-commit.

    ``skill_frontmatter`` imports ``scripts.validation.models`` absolutely, so
    ``check_model_pins.py`` must add the repo root to ``sys.path``. Without the
    Issue #3073 fix this exits nonzero with ``ModuleNotFoundError: scripts``.
    """
    script = REPO_ROOT / "scripts" / "validation" / "check_model_pins.py"
    result = subprocess.run(
        [sys.executable, str(script), "--mode", "warn"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr


def test_pre_pr_under_size_ceiling() -> None:
    """Edge: extraction keeps ``pre_pr.py`` under 500 lines (Issue #3073)."""
    text = (REPO_ROOT / "scripts" / "validation" / "pre_pr.py").read_text(
        encoding="utf-8"
    )
    assert len(text.splitlines()) < 500


def test_lazy_version_pin_import_resolves_without_sys_path_restore() -> None:
    """Regression (#3073): the lazy version-pin import resolves without a sys.path restore.

    ``validate_copilot_version_pin`` (checks_tooling.py) runs a *function-local*
    ``from check_copilot_version_pin import EXIT_OK, check_action`` that resolves
    by bare name at call time. It works only because this module inserts
    ``scripts/validation`` on ``sys.path`` append-only and never restores it,
    mirroring production ``pre_pr``. An earlier revision of this module
    snapshotted and restored ``sys.path`` in a ``finally``, stripping the
    directory back off and breaking the import in isolation; PR #3228 removed the
    restore.

    An in-process guard cannot catch a reintroduced restore: sibling test
    modules (``test_check_skill_portability``, ``test_check_skill_md_portability``)
    insert ``scripts/validation`` at collection and leave it on ``sys.path``, so
    the directory stays reachable even if this module restores its own path, and
    a reintroduced bug passes. The guard therefore runs in a clean subprocess
    that scrubs ``scripts/validation`` from ``sys.path``, imports *only this
    module* (whose append-only discipline is then the sole thing keeping the
    directory reachable), evicts the lazy target, and calls the validator. If a
    future edit reintroduces the restore, the lazy import raises
    ``ModuleNotFoundError`` and the subprocess exits nonzero. The
    ``MissingScriptSkip`` branch is caught because the import at
    ``checks_tooling.py`` runs *before* the ``action.yml`` existence check, so a
    downstream install without the action still proves the import resolved.
    """
    tests_validation_dir = REPO_ROOT / "tests" / "validation"
    validation_dir = REPO_ROOT / "scripts" / "validation"
    probe = (
        "import importlib, sys\n"
        f"val = {str(validation_dir)!r}\n"
        "sys.path[:] = [p for p in sys.path if p != val]\n"
        f"sys.path.insert(0, {str(tests_validation_dir)!r})\n"
        'mod = importlib.import_module("test_pre_pr_model_pin_wiring")\n'
        'sys.modules.pop("check_copilot_version_pin", None)\n'
        "try:\n"
        "    mod.pre_pr.validate_copilot_version_pin(mod.REPO_ROOT)\n"
        "except mod.pre_pr.MissingScriptSkip:\n"
        "    pass\n"
        'assert "check_copilot_version_pin" in sys.modules, "lazy import failed"\n'
        'print("LAZY_IMPORT_OK")\n'
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "LAZY_IMPORT_OK" in result.stdout
