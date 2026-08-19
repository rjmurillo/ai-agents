#!/usr/bin/env python3
"""Tests for the plugin hook anchoring gate (issue #2205).

Covers both shipped plugin hook files. Copilot entries are compared against the
generator's anchored shape; Claude commands are checked against the
``${CLAUDE_PLUGIN_ROOT}`` invariant. Pins the PASS case (real artifacts) and the
FAIL cases (the regression shapes), plus the config-error path.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import validate_hook_anchoring as gate  # noqa: E402


def test_real_repo_passes_both_plugins() -> None:
    """Both committed plugin hook files anchor correctly (exit 0)."""
    code, messages = gate.validate(REPO_ROOT)
    assert code == 0, messages


# --- Copilot (generator-compared) -------------------------------------------


def _anchored_seed() -> dict:
    """Build a correctly-anchored one-entry manifest from the canonical builder.

    The shipped manifest is empty since ADR-097 retired every tool-call hook,
    so these drift tests can no longer seed themselves from it. They synthesize
    an entry from ``generate_dispatcher.dispatcher_entry``, the same builder
    ``_check_copilot_entry`` compares against, then mutate one field. The
    mutation is the discriminator: ``test_copilot_seed_is_clean_before_mutation``
    below is the control proving the unmutated seed passes, so a seed that
    silently stopped matching the generator cannot make every FAIL case pass
    vacuously.
    """
    sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
    import generate_dispatcher

    return {"hooks": {"PreToolUse": [generate_dispatcher.dispatcher_entry("PreToolUse", 35)]}}


def _copilot_root(tmp_path: Path, mutate: Callable[[dict], None]) -> Path:
    (tmp_path / "build").mkdir()
    src_scripts = REPO_ROOT / "build" / "scripts"
    dst_scripts = tmp_path / "build" / "scripts"
    try:
        dst_scripts.symlink_to(src_scripts)
    except (OSError, NotImplementedError):
        # Windows without admin/dev-mode cannot create symlinks; copy instead
        # so the gate is still exercised on those platforms.
        shutil.copytree(src_scripts, dst_scripts)
    hooks_dir = tmp_path / "src" / "copilot-cli" / "hooks"
    hooks_dir.mkdir(parents=True)
    doc = _anchored_seed()
    mutate(doc)
    (hooks_dir / "hooks.json").write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def test_copilot_seed_is_clean_before_mutation(tmp_path: Path) -> None:
    """Control for every FAIL case below: the unmutated seed must pass."""
    checked, violations, config = gate._check_copilot(_copilot_root(tmp_path, lambda _doc: None))
    assert config == 0
    assert checked == 1
    assert not violations


def test_copilot_bare_bash_path_fails(tmp_path: Path) -> None:
    def mutate(doc: dict) -> None:
        entry = next(iter(doc["hooks"].values()))[0]
        entry["bash"] = 'python3 -u "./hooks/PreToolUse/x.py"'

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".bash" in v for v in violations)


def test_copilot_asymmetric_powershell_fails(tmp_path: Path) -> None:
    def mutate(doc: dict) -> None:
        entry = next(iter(doc["hooks"].values()))[0]
        entry["powershell"] = (
            'py -3 -u "$env:COPILOT_PLUGIN_ROOT/hooks/PreToolUse/x.py"'
        )

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".powershell" in v for v in violations)


# -- Degraded-trigger asymmetry fixtures (issue #4672) ----------------------
# Each removes one guard from the powershell form while keeping the bash form
# intact.  The validator must catch the drift.


def _strip_pwsh_guard(pwsh: str, marker: str) -> str:
    """Remove one semicolon-delimited guard statement from a powershell command.

    Finds the statement containing *marker* and deletes it (including the
    trailing semicolon separator) so the command is syntactically valid but
    structurally asymmetric with the bash form.
    """
    parts = pwsh.split("; ")
    return "; ".join(p for p in parts if marker not in p)


def test_copilot_asymmetric_root_unresolvable(tmp_path: Path) -> None:
    """Powershell missing the root-unresolvable guard must be a violation."""

    def mutate(doc: dict) -> None:
        entry = next(iter(doc["hooks"].values()))[0]
        entry["powershell"] = _strip_pwsh_guard(
            entry["powershell"], "Plugin root unresolvable"
        )

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".powershell" in v for v in violations), violations


def test_copilot_asymmetric_interpreter_absent(tmp_path: Path) -> None:
    """Powershell missing the interpreter-absent guard must be a violation."""

    def mutate(doc: dict) -> None:
        entry = next(iter(doc["hooks"].values()))[0]
        entry["powershell"] = _strip_pwsh_guard(
            entry["powershell"], "No suitable Python interpreter found"
        )

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".powershell" in v for v in violations), violations


def test_copilot_asymmetric_dispatcher_missing(tmp_path: Path) -> None:
    """Powershell missing the dispatcher-exists guard must be a violation."""

    def mutate(doc: dict) -> None:
        entry = next(iter(doc["hooks"].values()))[0]
        entry["powershell"] = _strip_pwsh_guard(
            entry["powershell"], "Dispatcher missing"
        )

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".powershell" in v for v in violations), violations


def test_copilot_asymmetric_interpreter_failed(tmp_path: Path) -> None:
    """Powershell missing the exit 126/127 guard must be a violation."""

    def mutate(doc: dict) -> None:
        entry = next(iter(doc["hooks"].values()))[0]
        entry["powershell"] = _strip_pwsh_guard(
            entry["powershell"], "Python interpreter failed to start"
        )

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".powershell" in v for v in violations), violations


def test_copilot_direct_session_start_requires_shell_suppression(tmp_path: Path) -> None:
    def mutate(doc: dict) -> None:
        doc["hooks"]["SessionStart"] = [
            {
                "type": "command",
                "bash": (
                    'python3 -u "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}'
                    '/hooks/SessionStart/direct.py"'
                ),
                "powershell": (
                    'py -3 -u "$(if ($env:COPILOT_PLUGIN_ROOT) '
                    "{$env:COPILOT_PLUGIN_ROOT} else {$env:CLAUDE_PLUGIN_ROOT})"
                    '/hooks/SessionStart/direct.py"'
                ),
                "cwd": ".",
                "timeoutSec": 10,
            }
        ]

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))

    assert config == 0
    assert any("SessionStart[0].bash" in violation for violation in violations)
    assert any("SessionStart[0].powershell" in violation for violation in violations)


# --- Claude (invariant against ${CLAUDE_PLUGIN_ROOT}) -----------------------


def test_claude_real_file_is_anchored() -> None:
    # ADR-097 retired every tool-call hook, so the real manifest registers zero
    # command hooks. That is a valid anchored state, not a config error: the
    # anchoring invariant holds over an empty set.
    checked, violations, config = gate._check_claude(REPO_ROOT)
    assert config == 0
    assert checked == 0
    assert not violations


def test_empty_claude_manifest_is_valid_not_a_config_error(tmp_path: Path) -> None:
    """Zero registered hooks passes (ADR-097); it is not a missing manifest."""
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text(json.dumps({"hooks": {}}), encoding="utf-8")

    checked, violations, config = gate._check_claude(tmp_path)

    assert config == 0
    assert checked == 0
    assert not violations


def test_claude_manifest_without_hooks_key_is_still_a_config_error(tmp_path: Path) -> None:
    """Negative control for the case above: empty is valid, malformed is not.

    Without this, permitting the empty mapping would also permit a manifest
    whose "hooks" key failed to generate at all, and the two are not the same
    failure.
    """
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text(json.dumps({"version": 1}), encoding="utf-8")

    _checked, violations, config = gate._check_claude(tmp_path)

    assert config == 2
    assert violations and "malformed or missing" in violations[0]


def test_empty_copilot_manifest_is_valid_not_a_config_error(tmp_path: Path) -> None:
    """The generated Copilot manifest is also legitimately empty (ADR-097)."""
    artifact = Path("src/copilot-cli/hooks/hooks.json")
    target = tmp_path / artifact
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"hooks": {}, "version": 1}), encoding="utf-8")

    checked, violations, config = gate._check_copilot(tmp_path, artifact)

    assert config == 0
    assert checked == 0
    assert not violations


def test_copilot_manifest_with_non_mapping_hooks_is_a_config_error(tmp_path: Path) -> None:
    """Negative control: a wrong-typed 'hooks' value must not read as empty."""
    artifact = Path("src/copilot-cli/hooks/hooks.json")
    target = tmp_path / artifact
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"hooks": [], "version": 1}), encoding="utf-8")

    _checked, violations, config = gate._check_copilot(tmp_path, artifact)

    assert config == 2
    assert violations and "malformed or missing" in violations[0]


def test_claude_bare_path_fails(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    doc = {
        "hooks": {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": 'python3 -u ".claude/hooks/x.py"'}]}
            ]
        }
    }
    (hooks_dir / "hooks.json").write_text(json.dumps(doc), encoding="utf-8")
    checked, violations, config = gate._check_claude(tmp_path)
    assert config == 0
    assert checked == 1
    assert violations and "not anchored" in violations[0]


def test_missing_files_are_config_error(tmp_path: Path) -> None:
    """Absent hook files are a config error (exit 2), not a false pass."""
    code, _ = gate.validate(tmp_path)
    assert code == 2


def test_malformed_platform_yaml_is_config_error(tmp_path: Path) -> None:
    """Platform config parse failures are config errors, not skipped inputs."""
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (platforms / "broken.yaml").write_text("artifacts: [", encoding="utf-8")

    code, messages = gate.validate(tmp_path)

    assert code == 2
    assert any("cannot read/parse platform config" in message for message in messages)


def test_null_platform_artifacts_is_config_error(tmp_path: Path) -> None:
    """Explicit null artifacts are config errors, not empty discovery."""
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (platforms / "broken.yaml").write_text("artifacts:\n", encoding="utf-8")

    code, messages = gate.validate(tmp_path)

    assert code == 2
    assert any("platform artifacts must be a mapping" in message for message in messages)


def test_null_platform_hooks_is_config_error(tmp_path: Path) -> None:
    """Explicit null hooks are config errors, not empty discovery."""
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (platforms / "broken.yaml").write_text("artifacts:\n  hooks:\n", encoding="utf-8")

    code, messages = gate.validate(tmp_path)

    assert code == 2
    assert any("platform hooks must be a mapping" in message for message in messages)
