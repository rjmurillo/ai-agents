"""Real-runtime smoke for the Pi package (ADR-115 Decisions 5, 9, 10).

Installs the repository root into an isolated Pi config directory, asks the Pi
RPC server for its commands, and requires every ``src/claude/skills`` directory
to appear as ``skill:<name>`` from this package. Then it runs the ``github``
skill's ``get_pr_checks.py --help`` from the path Pi reported, with every plugin
root variable unset, so the script's own resolver has to find ``lib/``. Pi uses a
local-path package in place, so that resolver lands on ``src/claude/lib``.

Loading a package needs no login and no model call, so the leg has no secret.

Opt-in like the other real-CLI smokes: without ``RUN_CLI_E2E=1`` and a ``pi``
binary the smoke SKIPS with a loud reason, and ``assert_smoke_ran.py`` turns that
skip into a red CI run. ``PI_BIN`` names the binary when ``pi`` is not on PATH.

Run locally:
    RUN_CLI_E2E=1 PI_BIN=/path/to/pi uv run pytest tests/e2e/test_pi_package_smoke.py \
        -v -m "smoke and pi"
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "src" / "claude" / "skills"
PR_CHECKS_RELATIVE = Path("github") / "scripts" / "pr" / "get_pr_checks.py"

# Pi 1.2.0 on a fresh config directory installs and answers in a few seconds.
_PI_COMMAND_TIMEOUT_SECONDS = 60
_PI_COMMAND_COUNT = 3
_SCRIPT_TIMEOUT_SECONDS = 30
_PYTEST_MARGIN_SECONDS = 30
_SMOKE_BUDGET_SECONDS = (
    _PI_COMMAND_TIMEOUT_SECONDS * _PI_COMMAND_COUNT
    + _SCRIPT_TIMEOUT_SECONDS
    + _PYTEST_MARGIN_SECONDS
)

_PI_ENV_ALLOWLIST = frozenset({"PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "LANG"})
# Variables the script resolver reads before it falls back to its own location.
_PLUGIN_ROOT_ENV_KEYS = ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT", "GITHUB_WORKSPACE")
_LIB_MISSING_MESSAGE = "Plugin lib directory not found"
_CONFIG_ERROR_EXIT = 2

_RUN = os.environ.get("RUN_CLI_E2E") == "1"


def pi_binary() -> str | None:
    """Return the Pi executable named by ``PI_BIN`` or found on PATH, else ``None``."""
    explicit = os.environ.get("PI_BIN", "").strip()
    if explicit:
        return shutil.which(explicit)
    return shutil.which("pi")


requires_pi = pytest.mark.skipif(
    not (_RUN and pi_binary()),
    reason="needs RUN_CLI_E2E=1 and the pi CLI (PATH or PI_BIN); no credential is read",
)


def pi_env(config_dir: Path, home: Path) -> dict[str, str]:
    """Env for a Pi subprocess: an allow-list, isolated config and home, offline."""
    env = {key: value for key, value in os.environ.items() if key.upper() in _PI_ENV_ALLOWLIST}
    env["PI_CODING_AGENT_DIR"] = str(config_dir)
    env["PI_OFFLINE"] = "1"
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def skill_script_env() -> dict[str, str]:
    """Env for a skill script: the parent env without any plugin-root variable."""
    return {k: v for k, v in os.environ.items() if k not in _PLUGIN_ROOT_ENV_KEYS}


def shipped_skill_names() -> set[str]:
    return {path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()}


def package_skill_paths(response_line: str, repo_root: Path) -> dict[str, Path]:
    """Map ``<name>`` to its ``SKILL.md`` for each skill sourced from ``repo_root``.

    ``response_line`` is Pi's ``get_commands`` RPC response. An entry counts only
    when its ``sourceInfo.origin`` is ``package`` and its path sits under
    ``repo_root``, so a same-named skill from the user's own skills never passes.
    """
    response = json.loads(response_line)
    if response.get("command") != "get_commands" or response.get("success") is not True:
        raise ValueError(f"unexpected Pi response: {response_line[:300]}")
    found: dict[str, Path] = {}
    for command in response["data"]["commands"]:
        info = command.get("sourceInfo") or {}
        name = command.get("name", "")
        if command.get("source") != "skill" or not name.startswith("skill:"):
            continue
        path = Path(info.get("path", ""))
        if info.get("origin") == "package" and path.is_relative_to(repo_root):
            found[name.removeprefix("skill:")] = path
    return found


def _run_pi(
    pi: str, args: list[str], env: dict[str, str], cwd: Path, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [pi, *args],
        input=stdin,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_PI_COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, (
        f"pi {' '.join(args)} failed (rc={result.returncode}). "
        f"stdout tail: {result.stdout[-400:]!r} stderr tail: {result.stderr[-400:]!r}"
    )
    return result


def run_skill_script(script: Path) -> subprocess.CompletedProcess[str]:
    """Run ``script --help`` isolated, with no plugin-root variable set."""
    return subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        env=skill_script_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_SCRIPT_TIMEOUT_SECONDS,
        check=False,
    )


@pytest.mark.smoke
@pytest.mark.pi
@requires_pi
@pytest.mark.timeout(_SMOKE_BUDGET_SECONDS)
def test_pi_package_loads_every_skill_and_a_skill_script_finds_lib(tmp_path: Path) -> None:
    """pi installs the repo root, lists all skills from it, and a script imports lib/."""
    pi = pi_binary()
    assert pi is not None
    config_dir = tmp_path / "pi-config"
    home = tmp_path / "home"
    work = tmp_path / "cwd"
    for directory in (config_dir, home, work):
        directory.mkdir()
    env = pi_env(config_dir, home)

    try:
        _run_pi(pi, ["install", str(REPO_ROOT)], env, work)
        listing = _run_pi(pi, ["list"], env, work)
        rpc = _run_pi(pi, ["--mode", "rpc"], env, work, stdin='{"id":"1","type":"get_commands"}\n')
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"pi command exceeded {_PI_COMMAND_TIMEOUT_SECONDS}s: {exc.cmd}")

    assert str(REPO_ROOT) in listing.stdout, f"pi list omits the package: {listing.stdout!r}"
    expected = shipped_skill_names()
    loaded = package_skill_paths(rpc.stdout.splitlines()[0], REPO_ROOT)
    missing = expected - set(loaded)
    assert not missing, (
        f"pi lists no skill:<name> from this package for {len(missing)} skills, "
        f"first {sorted(missing)[:10]}. "
        f"Loaded {len(loaded)} of {len(expected)}."
    )
    for name in expected:
        assert loaded[name] == SKILLS_ROOT / name / "SKILL.md", (name, loaded[name])

    script = loaded["github"].parent / "scripts" / "pr" / "get_pr_checks.py"
    result = run_skill_script(script)
    assert result.returncode == 0, (
        f"{script} --help exited {result.returncode}: {result.stderr[-400:]!r}"
    )
    assert "usage:" in result.stdout


def test_a_script_copy_without_lib_at_the_resolver_location_fails(tmp_path: Path) -> None:
    """Negative control: the resolver needs lib/ four directories above the script."""
    shipped = SKILLS_ROOT / PR_CHECKS_RELATIVE
    copy = tmp_path / "claude" / "skills" / PR_CHECKS_RELATIVE
    copy.parent.mkdir(parents=True)
    shutil.copyfile(shipped, copy)

    result = run_skill_script(copy)

    assert result.returncode == _CONFIG_ERROR_EXIT
    assert _LIB_MISSING_MESSAGE in result.stderr


def test_a_script_copy_with_lib_at_the_resolver_location_passes(tmp_path: Path) -> None:
    """Positive control: the same copy runs once lib/ sits where the resolver looks."""
    copy = tmp_path / "claude" / "skills" / PR_CHECKS_RELATIVE
    copy.parent.mkdir(parents=True)
    shutil.copyfile(SKILLS_ROOT / PR_CHECKS_RELATIVE, copy)
    shutil.copytree(REPO_ROOT / "src" / "claude" / "lib", tmp_path / "claude" / "lib")

    result = run_skill_script(copy)

    assert result.returncode == 0, result.stderr[-400:]


def test_shipped_skill_names_lists_the_skill_directories() -> None:
    names = shipped_skill_names()

    assert "github" in names
    assert all((SKILLS_ROOT / name / "SKILL.md").is_file() for name in names)


def _response(
    *commands: dict[str, object], success: bool = True, command: str = "get_commands"
) -> str:
    return json.dumps(
        {
            "id": "1",
            "type": "response",
            "command": command,
            "success": success,
            "data": {"commands": list(commands)},
        }
    )


def _skill(name: str, path: Path, origin: str = "package") -> dict[str, object]:
    return {
        "name": f"skill:{name}",
        "source": "skill",
        "sourceInfo": {"path": str(path), "origin": origin},
    }


def test_package_skill_paths_keeps_package_skills_under_the_repo(tmp_path: Path) -> None:
    line = _response(_skill("a", tmp_path / "a" / "SKILL.md"))

    assert package_skill_paths(line, tmp_path) == {"a": tmp_path / "a" / "SKILL.md"}


@pytest.mark.parametrize(
    "command",
    [
        lambda root: _skill("a", Path("/elsewhere/a/SKILL.md")),
        lambda root: _skill("a", root / "a" / "SKILL.md", origin="top-level"),
        lambda root: {
            "name": "a",
            "source": "skill",
            "sourceInfo": {"path": "x", "origin": "package"},
        },
        lambda root: {"name": "skill:a", "source": "extension", "sourceInfo": {"path": "x"}},
        lambda root: {"name": "skill:a", "source": "skill"},
    ],
    ids=["outside-repo", "not-package", "no-prefix", "not-a-skill", "no-source-info"],
)
def test_package_skill_paths_ignores_skills_not_from_this_package(tmp_path: Path, command) -> None:
    assert package_skill_paths(_response(command(tmp_path)), tmp_path) == {}


@pytest.mark.parametrize(
    "line",
    [
        _response(success=False),
        _response(command="other"),
        "{}",
    ],
)
def test_package_skill_paths_rejects_an_unexpected_response(line: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unexpected Pi response"):
        package_skill_paths(line, tmp_path)


def test_package_skill_paths_rejects_non_json(tmp_path: Path) -> None:
    with pytest.raises(json.JSONDecodeError):
        package_skill_paths("not json", tmp_path)


def test_pi_env_isolates_config_home_and_drops_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("PI_CODING_AGENT_DIR", "/real/config")

    env = pi_env(tmp_path / "c", tmp_path / "h")

    assert env["PI_CODING_AGENT_DIR"] == str(tmp_path / "c")
    assert env["HOME"] == str(tmp_path / "h")
    assert env["PI_OFFLINE"] == "1"
    assert "OPENAI_API_KEY" not in env


def test_skill_script_env_drops_plugin_root_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PLUGIN_ROOT_ENV_KEYS:
        monkeypatch.setenv(key, "/somewhere")

    env = skill_script_env()

    assert not set(_PLUGIN_ROOT_ENV_KEYS) & set(env)


def test_pi_binary_prefers_pi_bin_and_returns_none_when_it_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "fake-pi"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PI_BIN", str(fake))
    assert pi_binary() == str(fake)

    monkeypatch.setenv("PI_BIN", str(tmp_path / "absent"))
    assert pi_binary() is None
