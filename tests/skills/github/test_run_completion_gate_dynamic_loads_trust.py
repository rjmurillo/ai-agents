"""The ADR's concrete case, and the trust integration of dynamic loads.

`new_pr.py` loading `pr_validations.py` through a computed path is the case the
decision was made against. The integration cases run real git and the real
dispatcher: a dynamic edge is verified or it halts before any command runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import NEW_PR, REPO_ROOT, closure, gate, write


class TestTheConcreteCaseTheAdrNames:
    """``new_pr.py`` loads ``pr_validations.py`` through a computed path."""

    def test_new_pr_falls_on_the_fail_closed_side(self) -> None:
        loads = gate._dynamic_loads(NEW_PR.read_bytes(), NEW_PR)

        kinds = [load.kind for load in loads]
        assert "spec_from_file_location" in kinds
        target = next(load for load in loads if load.kind == "spec_from_file_location")
        assert target.path is None

    def test_the_computed_path_shape_from_new_pr_is_unresolvable(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util, sys
            from pathlib import Path

            def _load_sibling(name):
                path = Path(__file__).resolve().with_name(f"{name}.py")
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                return module

            _pr_val = _load_sibling("pr_validations")
            """,
        )
        write(tmp_path, "pr_validations.py", "X = 1\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1
        assert closure(tmp_path, "verify.py") == ["verify.py"]

    def test_the_same_load_with_a_literal_name_resolves_and_is_verified(
        self, tmp_path: Path
    ) -> None:
        """The refactor that keeps python3 -I isolation and gains verification."""
        write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path

            path = Path(__file__).resolve().with_name("pr_validations.py")
            spec = importlib.util.spec_from_file_location("pr_validations", path)
            """,
        )
        write(tmp_path, "pr_validations.py", "X = 1\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []
        assert closure(tmp_path, "verify.py") == ["verify.py", "pr_validations.py"]

    def test_no_shipped_verifier_reaches_a_dynamic_load_today(self) -> None:
        """Measured 2026-09-29: the closure of the configured verifiers has none."""
        import yaml

        config = yaml.safe_load(
            (REPO_ROOT / ".claude/skills/pr-review/pr-review-config.yaml").read_text(
                encoding="utf-8"
            )
        )
        named: set[str] = set()

        def collect(value: object) -> None:
            if isinstance(value, str):
                for token in value.replace('"', " ").replace("'", " ").split():
                    marker = token.find(".claude/skills/")
                    if marker != -1 and token.endswith(".py"):
                        named.add(token[marker:])
            elif isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(config)
        present = sorted(path for path in named if (REPO_ROOT / path).is_file())
        assert present, "the config names no verifier script; the scan proves nothing"

        closure = gate._expand_import_closure(present, REPO_ROOT)

        assert len(closure) > len(present)
        assert gate._unresolvable_dynamic_sites(closure, REPO_ROOT) == []


def _git(cwd: Path, *args: str) -> None:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(gate, "_PROJECT_ROOT", tmp_path)
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _trust(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "trusted")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def _criteria(script: Path) -> list[dict]:
    return [
        {
            "name": "Dynamic",
            "verification": "command",
            "command": f"{sys.executable} {script}",
            "pass_when": "stdout-json.ok == true",
        }
    ]


class TestCommandTrustIntegration:
    """Real git, real closure: a dynamic edge is verified or it halts."""

    def test_a_resolvable_dynamic_target_that_diverged_from_the_trusted_ref_halts(
        self, repo: Path
    ) -> None:
        script = write(
            repo,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('s', Path(__file__).parent / 'sibling.py')\n",
        )
        sibling = write(repo, "sibling.py", "X = 1\n")
        _trust(repo)
        sibling.write_text("X = 2  # the pull request rewrote this\n", encoding="utf-8")

        result = gate._verify_command_trust(_criteria(script), 1, "origin/main")

        assert result.status == gate.COMMAND_TRUST_UNTRUSTED
        assert "sibling.py" in result.untrusted_files

    def test_a_resolvable_dynamic_target_identical_to_the_trusted_ref_is_trusted(
        self, repo: Path
    ) -> None:
        script = write(
            repo,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('s', Path(__file__).parent / 'sibling.py')\n",
        )
        write(repo, "sibling.py", "X = 1\n")
        _trust(repo)

        result = gate._verify_command_trust(_criteria(script), 1, "origin/main")

        assert result.status == gate.COMMAND_TRUST_TRUSTED
        assert "sibling.py" in result.checked_files

    def test_an_unresolvable_dynamic_load_halts_as_untrusted_and_names_the_line(
        self, repo: Path
    ) -> None:
        script = write(repo, "verify.py", "import sys\n__import__(sys.argv[1])\n")
        _trust(repo)

        result = gate._verify_command_trust(_criteria(script), 1, "origin/main")

        assert result.status == gate.COMMAND_TRUST_UNTRUSTED
        assert result.untrusted_files == ["verify.py:2: unresolvable dynamic load (__import__)"]

    def test_main_halts_before_running_any_command(self, repo: Path) -> None:
        marker = repo / "ran.txt"
        script = write(
            repo,
            "verify.py",
            f"""\
            import json, pathlib, sys
            pathlib.Path({str(marker)!r}).write_text("ran")
            __import__(sys.argv[1])
            print(json.dumps({{"ok": True}}))
            """,
        )
        config = write(repo, "pr-review-config.yaml", "placeholder: 1\n")
        config.write_text(
            json.dumps({"completion_criteria": _criteria(script)}),
            encoding="utf-8",
        )
        _trust(repo)

        rc = gate.main(["--config", str(config), "--pull-request", "1"])

        assert rc == 2
        assert not marker.exists()

    def test_approval_lets_an_unresolvable_load_proceed(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        marker = repo / "ran.txt"
        script = write(
            repo,
            "verify.py",
            f"""\
            import json, pathlib
            pathlib.Path({str(marker)!r}).write_text("ran")
            exec(open(__file__).read().splitlines()[0])
            print(json.dumps({{"ok": True}}))
            """,
        )
        config = repo / "pr-review-config.yaml"
        config.write_text(
            json.dumps({"completion_criteria": _criteria(script)}),
            encoding="utf-8",
        )
        _trust(repo)

        rc = gate.main(
            ["--config", str(config), "--pull-request", "1", "--approve-untrusted-config"]
        )

        assert rc == 0
        assert marker.exists()
        assert "Untrusted entries" in capsys.readouterr().err

    def test_the_halt_message_names_the_dynamic_load_route(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = write(repo, "verify.py", "import sys\n__import__(sys.argv[1])\n")
        config = repo / "pr-review-config.yaml"
        config.write_text(json.dumps({"completion_criteria": _criteria(script)}), encoding="utf-8")
        _trust(repo)

        rc = gate.main(["--config", str(config), "--pull-request", "1"])

        err = capsys.readouterr().err
        assert rc == 2
        assert "unresolvable dynamic load" in err
        assert "verify.py:2:" in err

