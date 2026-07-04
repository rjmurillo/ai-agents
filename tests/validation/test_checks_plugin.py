from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import checks_plugin


def test_workflow_local_run_warns_on_missing_local_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path
    script = repo_root / "scripts" / "validation" / "run_workflow_local_test.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('stub')\n", encoding="utf-8")

    workflow = repo_root / ".github" / "workflows" / "secret.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: secret\n", encoding="utf-8")

    monkeypatch.setattr(checks_plugin, "_resolve_default_base_ref", lambda _root: "origin/main")

    def fake_run_subprocess(args: list[str], *_, **__) -> tuple[int, str, str]:
        if args[:4] == ["git", "-C", str(repo_root), "diff"]:
            return 0, ".github/workflows/secret.yml\n", ""
        return 4, "unrunnable-locally: actionlint passed\n", ""

    monkeypatch.setattr(checks_plugin, "_run_subprocess", fake_run_subprocess)

    assert checks_plugin.validate_workflow_local_run(repo_root) is True

    output = capsys.readouterr().out
    assert "unrunnable-locally: actionlint passed" in output
    assert "workflow local-run auth material unavailable locally" in output
