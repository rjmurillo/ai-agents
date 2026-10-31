"""Tests for repository-consumer-proof scripts/artifact_owner.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/repository-consumer-proof/scripts/artifact_owner.py"
spec = importlib.util.spec_from_file_location("artifact_owner", SCRIPT)
artifact_owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact_owner)

MANIFEST = """\
schemaVersion: "1.0"
rows:
  - class: skills
    # comment
    source: templates/skills
    plugin_tree: src/claude/skills
    install_tree: .claude/skills
    link: true
  - class: hooks
    source: templates/hooks
    plugin_tree: src/claude/hooks
    install_tree: .claude/hooks
  - class: settings
    source: templates/hooks/settings.tmpl
    plugin_tree: null
    install_tree: .claude/settings.json
"""


def _repo(tmp_path: Path) -> Path:
    target = tmp_path / "templates/platforms"
    target.mkdir(parents=True)
    (target / "binplace.yaml").write_text(MANIFEST, encoding="utf-8")
    return tmp_path


def test_real_manifest_covers_installed_hook(capsys):
    code = artifact_owner.main(["--repo", str(ROOT), ".claude/hooks/hooks.json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["examined"] > 10
    classes = {m["class"] for m in out["owner_rows"]}
    assert "hooks-json" in classes


def test_layers_and_relation(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert artifact_owner.main(["--repo", str(repo), "src/claude/skills/x/SKILL.md"]) == 0
    match = json.loads(capsys.readouterr().out)["owner_rows"][0]
    assert match["class"] == "skills"
    assert match["layers"] == ["plugin"]
    assert match["relation"] == "link"
    assert artifact_owner.main(["--repo", str(repo), ".claude/hooks/a.py"]) == 0
    match = json.loads(capsys.readouterr().out)["owner_rows"][0]
    assert match["layers"] == ["installed"] and match["relation"] == "copy"


def test_render_only_row(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert artifact_owner.main(["--repo", str(repo), ".claude/settings.json"]) == 0
    match = json.loads(capsys.readouterr().out)["owner_rows"][0]
    assert match["relation"] == "render-only"


def test_uncovered_path_exits_1(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert artifact_owner.main(["--repo", str(repo), "docs/readme.md"]) == 1
    assert json.loads(capsys.readouterr().out)["owner_rows"] == []


def test_prefix_is_path_segment_not_substring(tmp_path):
    repo = _repo(tmp_path)
    assert artifact_owner.main(["--repo", str(repo), "templates/skills-extra/a.md"]) == 1


def test_missing_manifest_exits_2(tmp_path):
    assert artifact_owner.main(["--repo", str(tmp_path), "a.md"]) == 2


def test_path_outside_repo_exits_2(tmp_path):
    repo = _repo(tmp_path)
    assert artifact_owner.main(["--repo", str(repo), "../x.md"]) == 2


def test_dot_slash_prefix_normalized(tmp_path):
    repo = _repo(tmp_path)
    assert artifact_owner.main(["--repo", str(repo), "./templates/skills/a.tmpl"]) == 0


def test_help_exits_0():
    assert artifact_owner.main(["--help"]) == 0


def test_installed_lib_file_resolves_to_canonical_source(capsys):
    code = artifact_owner.main(["--repo", str(ROOT), ".claude/lib/hook_utilities/guards.py"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    upstream = [u for m in out["owner_rows"] for u in m["upstream"]]
    assert {
        "class": "lib-hook_utilities",
        "source": "scripts/hook_utilities",
        "plugin_tree": "src/claude/lib/hook_utilities",
    } in upstream


def test_source_layer_match_has_no_upstream(tmp_path, capsys):
    repo = _repo(tmp_path)
    artifact_owner.main(["--repo", str(repo), "templates/skills/a.tmpl"])
    assert json.loads(capsys.readouterr().out)["owner_rows"][0]["upstream"] == []
