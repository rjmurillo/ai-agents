"""Regression tests for issue #5522: hook generation never writes through a redirect.

Covers the two stage-path writes in ``generate_hooks_events``: the
``hooks.json`` config write and the dispatcher artifact staging in
``_stage_dispatcher_artifacts``. Each test swaps every transaction stage path
for a symlink right after allocation, then asserts the external target is
byte-for-byte unchanged and the published files are regular files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_hooks  # noqa: E402
import generate_hooks_events  # noqa: E402
from generate_hooks_transaction import HookGenerationTransaction  # noqa: E402

_EXTERNAL_BYTES = b"external file, must never change\n"


def _external_file(tmp_path: Path) -> Path:
    outside = tmp_path / "outside" / "external.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(_EXTERNAL_BYTES)
    return outside


# --- generate_hooks_events staging ------------------------------------------


_HOOKS_YAML = """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  hooks:
    settingsSource: "settings.json"
    scriptSource: "hooks_src"
    outputConfig: "out/hooks.json"
    outputScripts: "out"
    eventRemap:
      PreToolUse: PreToolUse
    eventDrop: []
    matcherPolicy: "inline-script-shim"
    versionField: 1
"""


def _hooks_repo(tmp_path: Path) -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(_HOOKS_YAML, encoding="utf-8")
    script = tmp_path / "hooks_src" / "PreToolUse" / "guard.py"
    script.parent.mkdir(parents=True)
    script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "python3 .claude/hooks/PreToolUse/guard.py"}
                    ],
                }
            ]
        }
    }
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return cfg


def test_hooks_generation_never_writes_through_a_redirect_raced_onto_a_stage_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Swap every transaction stage file for a symlink right after it exists.

    Stage files are created empty by ``tempfile.mkstemp`` and filled by the
    generator afterward. That fill is the window: the dispatcher artifact copy
    and the ``hooks.json`` write both ran ``copy2`` or ``write_text`` against a
    path another process could have turned into a link.
    """
    external = _external_file(tmp_path)
    cfg = _hooks_repo(tmp_path)
    real_new_stage_path = HookGenerationTransaction.new_stage_path
    raced: list[Path] = []

    def racing_new_stage_path(self: HookGenerationTransaction, directory: Path) -> Path:
        stage = real_new_stage_path(self, directory)
        stage.unlink()
        stage.symlink_to(external)
        raced.append(stage)
        return stage

    try:
        monkeypatch.setattr(HookGenerationTransaction, "new_stage_path", racing_new_stage_path)
        rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    except OSError:
        pytest.skip("symlink creation unavailable on this platform")

    assert raced, "generation never allocated a stage path"
    assert rc == 0
    assert external.read_bytes() == _EXTERNAL_BYTES
    assert (tmp_path / "out" / "hooks.json").is_file()
    assert not (tmp_path / "out" / "hooks.json").is_symlink()


def _dispatcher_hooks_repo(tmp_path: Path) -> Path:
    """Two hooks on one gated event with ``dispatcher: true``.

    One hook per event never reaches dispatcher consolidation, so the
    ``_stage_dispatcher_artifacts`` publish loop needs this wider fixture.
    """
    cfg = _hooks_repo(tmp_path)
    cfg.write_text(
        _HOOKS_YAML.replace("    versionField: 1\n", "    versionField: 1\n    dispatcher: true\n"),
        encoding="utf-8",
    )
    second = tmp_path / "hooks_src" / "PreToolUse" / "second.py"
    second.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"].append(
        {"type": "command", "command": "python3 .claude/hooks/PreToolUse/second.py"}
    )
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    return cfg


def test_dispatcher_artifact_staging_never_writes_through_a_redirect_raced_onto_a_stage_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover the dispatcher artifact stage write in ``_stage_dispatcher_artifacts``.

    ``dispatcher: true`` with two hooks on ``PreToolUse`` makes consolidation
    emit ``_manifest.json``, ``_dispatch.py`` and ``_bootstrap.py``. Each is
    copied to a transaction stage path that this test swaps for a symlink right
    after allocation. A ``copy2`` into that path would write the external file.
    """
    external = _external_file(tmp_path)
    cfg = _dispatcher_hooks_repo(tmp_path)
    real_new_stage_path = HookGenerationTransaction.new_stage_path
    raced: list[Path] = []

    def racing_new_stage_path(self: HookGenerationTransaction, directory: Path) -> Path:
        stage = real_new_stage_path(self, directory)
        stage.unlink()
        stage.symlink_to(external)
        raced.append(stage)
        return stage

    try:
        monkeypatch.setattr(HookGenerationTransaction, "new_stage_path", racing_new_stage_path)
        rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    except OSError:
        pytest.skip("symlink creation unavailable on this platform")

    event_dir = tmp_path / "out" / "PreToolUse"
    assert rc == 0
    assert external.read_bytes() == _EXTERNAL_BYTES
    assert sum(stage.parent == event_dir for stage in raced) >= len(
        generate_hooks_events._DISPATCHER_ARTIFACT_NAMES
    )
    for name in generate_hooks_events._DISPATCHER_ARTIFACT_NAMES:
        published = event_dir / name
        assert published.is_file()
        assert not published.is_symlink()
