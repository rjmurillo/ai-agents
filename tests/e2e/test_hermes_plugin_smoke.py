#!/usr/bin/env python3
"""Real-runtime smoke for the Hermes plugin packs (ADR-115 Decision 10).

``generated-artifacts.md`` MUST 4 asks for the shipped artifact to run in its
target runtime. Every structural test on ``src/hermes/`` could pass while Hermes
skipped a skill or refused the install, so these tests install the packs into a
real ``hermes`` at the pinned commit and use them:

1. **Guard gate.** The pinned ``tools.plugin_guard.scan_plugin`` returns a verdict
   for each pack. ``dangerous`` fails. A synthetic pack built from a skill the
   guard marks dangerous must return ``dangerous``, so the gate can fail.
2. **Install, enable, list.** Each pack installs with ``hermes plugins install``,
   enables, and ``skills_list`` returns every skill the pack table names. A
   synthetic pack with a skill Hermes rejects must lose that skill, so the
   listing check can fail.
3. **Script-backed step.** One script per pack in ``SCRIPTS_UNDER_TEST``, such
   as ``get_pr_checks.py --help`` from the installed ``github`` skill, exits 0
   under ``python -I`` from a neutral directory with ``PLUGIN_ROOT`` set and
   ``CLAUDE_PLUGIN_ROOT``, ``COPILOT_PLUGIN_ROOT``, and ``GITHUB_WORKSPACE``
   unset. The same script in a copy of its pack without ``lib/`` must exit
   nonzero, so the step can fail.

No model call and no credential: every command reads the packs and the scratch
home only. The tests skip, loudly, unless ``RUN_CLI_E2E=1`` is set and a
``hermes`` CLI is on ``PATH`` (or named by ``HERMES_SMOKE_BIN``). The CI leg
that must not skip is described in the pull request; ``assert_smoke_ran.py``
turns a skipped smoke into a failure there.

Run locally against a hermes-agent checkout at the pinned commit installed with
``uv pip install -e <checkout>`` on Python 3.14::

    RUN_CLI_E2E=1 HERMES_SMOKE_BIN=<venv>/bin/hermes \\
        uv run --frozen pytest tests/e2e/test_hermes_plugin_smoke.py -m "smoke and hermes" -v
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

import pytest
import yaml

_E2E_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _E2E_DIR.parent.parent
for _extra in (_E2E_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import hermes_runtime as hr  # noqa: E402
from hermes_pack_config import HermesConfig, parse_stanza  # noqa: E402

HERMES_YAML = _REPO_ROOT / "templates" / "platforms" / "hermes.yaml"
SKILLS_SOURCE = _REPO_ROOT / "src" / "claude" / "skills"


class ScriptCase(NamedTuple):
    """A script-backed step in one pack that imports ``lib/`` through its resolver."""

    pack: str
    script: Path
    usage: str
    missing_lib: str


# One script per pack. The delivery and authoring scripts resolve lib/ through
# skill_bootstrap.py. The quality and knowledge scripts use the inline ADR-047
# bootstrap, so the cases cover both resolver shapes.
SCRIPTS_UNDER_TEST = (
    ScriptCase(
        "delivery",
        Path("skills/github/scripts/pr/get_pr_checks.py"),
        "usage: get_pr_checks.py",
        "Plugin lib directory not found",
    ),
    ScriptCase(
        "quality",
        Path("skills/threat-modeling/scripts/validate_threat_model.py"),
        "usage: validate_threat_model.py",
        "Expected portability helper lib directory not found",
    ),
    ScriptCase(
        "knowledge",
        Path("skills/chestertons-fence/scripts/investigate.py"),
        "usage: investigate.py",
        "Expected portability helper lib directory not found",
    ),
    ScriptCase(
        "authoring",
        Path("skills/prose-self-check/scripts/prose_lint.py"),
        "usage: prose_lint.py",
        "Plugin lib directory not found",
    ),
)
NEGATIVE_CONTROL_PACK = "project-toolkit-negctl"

_RUN = os.environ.get("RUN_CLI_E2E") == "1"
_BIN = os.environ.get("HERMES_SMOKE_BIN") or shutil.which("hermes")
needs_hermes = pytest.mark.skipif(
    not (_RUN and _BIN),
    reason=(
        "SKIPPED, NOT PASSED: needs RUN_CLI_E2E=1 and the hermes CLI at the pinned commit "
        "on PATH or in HERMES_SMOKE_BIN. The Hermes packs were not run in Hermes."
    ),
)


def load_config() -> HermesConfig:
    data = yaml.safe_load(HERMES_YAML.read_text(encoding="utf-8"))
    return parse_stanza(data["artifacts"]["skills"])


class Runtime(NamedTuple):
    """One installed Hermes: its launcher, its Python, and the scratch sandbox."""

    hermes: Path
    python: Path
    env: dict[str, str]
    home: Path
    workdir: Path
    config: HermesConfig
    verdicts: dict[str, str]

    def pack_dir(self, key: str) -> Path:
        return Path(self.env["HERMES_HOME"]) / "plugins" / f"project-toolkit-{key}"


def pack_source(config: HermesConfig, key: str) -> Path:
    return _REPO_ROOT / config.output_dir / f"project-toolkit-{key}"


class GuardScan(NamedTuple):
    """The pinned guard's verdict for one pack and its high or critical findings."""

    verdict: str
    high: frozenset[hr.ReviewedFinding]


def guard_scans(
    rt_python: Path, env: dict[str, str], dirs: list[Path], cwd: Path
) -> dict[str, GuardScan]:
    parsed, _ = hr.python_json(
        rt_python, hr.GUARD_SNIPPET, env, cwd=cwd, argv=[str(d) for d in dirs]
    )
    assert isinstance(parsed, dict)
    return {
        Path(path).name: GuardScan(
            str(scan["verdict"]),
            frozenset(
                (str(pid), str(rel), int(line), str(digest))
                for pid, rel, line, digest in scan["high"]
            ),
        )
        for path, scan in parsed.items()
    }


def guard_verdicts(
    rt_python: Path, env: dict[str, str], dirs: list[Path], cwd: Path
) -> dict[str, str]:
    return {name: scan.verdict for name, scan in guard_scans(rt_python, env, dirs, cwd).items()}


@pytest.fixture(scope="module")
def runtime(tmp_path_factory: pytest.TempPathFactory) -> Runtime:
    """Install every pack into a scratch Hermes home, enabled, once per module."""
    hermes = Path(str(_BIN))
    python = hr.hermes_python(hermes)
    root = tmp_path_factory.mktemp("hermes-smoke")
    env = hr.scratch_env(root / "home")
    workdir = root / "neutral"
    workdir.mkdir()
    config = load_config()
    commit = hr.hermes_checkout_commit(python, env, cwd=workdir)
    assert commit == config.hermes_commit, (
        f"hermes runs from {commit}, hermes.yaml pins {config.hermes_commit}; the guard "
        "verdicts and install caps in this smoke are measured at the pin"
    )
    dirs = [pack_source(config, pack.key) for pack in config.packs]
    scans = guard_scans(python, env, dirs, workdir)
    verdicts = {name: scan.verdict for name, scan in scans.items()}
    repo = hr.stage_git_repo(_REPO_ROOT / config.output_dir, root / "repo", subdir="hermes")
    for pack in config.packs:
        scan = scans[pack.dir_name]
        assert scan.verdict != "dangerous", (
            f"{pack.dir_name} is dangerous; Hermes blocks the install"
        )
        force = hr.force_for_verdict(pack.dir_name, scan.verdict, scan.high)
        done = hr.install_pack(
            hermes, env, repo, f"hermes/{pack.dir_name}", force=force, cwd=workdir
        )
        assert done.returncode == 0, (
            f"install {pack.dir_name}: {done.stdout[-500:]}{done.stderr[-500:]}"
        )
        enabled = hr.enable_pack(hermes, env, pack.dir_name, cwd=workdir)
        assert enabled.returncode == 0, f"enable {pack.dir_name}: {enabled.stderr[-500:]}"
    return Runtime(hermes, python, env, root / "home", workdir, config, verdicts)


def listed_bare_names(rt: Runtime) -> tuple[set[str], str]:
    parsed, stderr = hr.python_json(rt.python, hr.LIST_SKILLS_SNIPPET, rt.env, cwd=rt.workdir)
    assert isinstance(parsed, list)
    return {str(name).split(":", 1)[1] for name in parsed}, stderr


# --- guard gate ----------------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.hermes
@needs_hermes
def test_no_pack_is_dangerous_under_the_pinned_guard(runtime: Runtime) -> None:
    assert set(runtime.verdicts) == {p.dir_name for p in runtime.config.packs}
    assert "dangerous" not in runtime.verdicts.values(), runtime.verdicts


@pytest.mark.smoke
@pytest.mark.hermes
@needs_hermes
def test_guard_negative_control_flags_a_dangerous_skill(runtime: Runtime, tmp_path: Path) -> None:
    pack = tmp_path / NEGATIVE_CONTROL_PACK
    # memory-search carries critical findings at the pin. stuck-detection was the
    # control until main reworded it and the pinned guard rated it safe.
    shutil.copytree(SKILLS_SOURCE / "memory-search", pack / "skills" / "memory-search")
    write_manifest(pack)

    verdicts = guard_verdicts(runtime.python, runtime.env, [pack], runtime.workdir)

    assert verdicts[NEGATIVE_CONTROL_PACK] == "dangerous"


def write_manifest(pack: Path) -> None:
    (pack / "plugin.json").write_text(
        '{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",'
        f' "name": "{pack.name}", "description": "negative control"}}\n',
        encoding="utf-8",
    )


# --- install, enable, list -----------------------------------------------------


@pytest.mark.smoke
@pytest.mark.hermes
@needs_hermes
def test_hermes_lists_every_packed_skill_with_no_loader_diagnostic(runtime: Runtime) -> None:
    expected = {skill for pack in runtime.config.packs for skill in pack.skills}

    listed, stderr = listed_bare_names(runtime)

    assert expected - listed == set(), f"packed but not listed: {sorted(expected - listed)}"
    assert listed - expected == set(), f"listed but not packed: {sorted(listed - expected)}"
    assert "Agent Plugin '" not in stderr, stderr[-600:]


@pytest.mark.smoke
@pytest.mark.hermes
@needs_hermes
def test_listing_negative_control_loses_a_skill_hermes_rejects(
    runtime: Runtime, tmp_path: Path
) -> None:
    pack = tmp_path / "stage" / NEGATIVE_CONTROL_PACK
    skill = pack / "skills" / "negctl-skill"
    skill.mkdir(parents=True)
    # `metadata` nested one level deeper than a flat string map: Hermes skips the skill.
    (skill / "SKILL.md").write_text(
        "---\nname: negctl-skill\ndescription: negative control\n"
        "metadata:\n  domains:\n    - x\n---\nBody\n",
        encoding="utf-8",
    )
    write_manifest(pack)
    repo = hr.stage_git_repo(pack, tmp_path / "repo", subdir=NEGATIVE_CONTROL_PACK)
    done = hr.install_pack(
        runtime.hermes, runtime.env, repo, NEGATIVE_CONTROL_PACK, force=False, cwd=runtime.workdir
    )
    assert done.returncode == 0, done.stdout[-400:] + done.stderr[-400:]
    assert (
        hr.enable_pack(
            runtime.hermes, runtime.env, NEGATIVE_CONTROL_PACK, cwd=runtime.workdir
        ).returncode
        == 0
    )

    listed, stderr = listed_bare_names(runtime)

    assert "negctl-skill" not in listed
    assert "Agent Plugin 'project-toolkit-negctl'" in stderr


# --- script-backed step ----------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.hermes
@needs_hermes
@pytest.mark.parametrize("case", SCRIPTS_UNDER_TEST, ids=lambda case: case.pack)
def test_installed_skill_script_runs_with_plugin_root_only(
    runtime: Runtime, case: ScriptCase
) -> None:
    pack = runtime.pack_dir(case.pack)
    env = hr.script_env(runtime.home, pack)
    assert not set(hr.SCRIPT_ENV_KEYS_THAT_MUST_BE_UNSET) & set(env)

    done = hr.run_script_help(pack / case.script, env, cwd=runtime.workdir)

    assert done.returncode == 0, done.stderr[-600:]
    assert case.usage in done.stdout


@pytest.mark.smoke
@pytest.mark.hermes
@needs_hermes
@pytest.mark.parametrize("case", SCRIPTS_UNDER_TEST, ids=lambda case: case.pack)
def test_script_negative_control_fails_without_lib(
    runtime: Runtime, case: ScriptCase, tmp_path: Path
) -> None:
    broken = tmp_path / "no-lib-pack"
    shutil.copytree(runtime.pack_dir(case.pack), broken)
    shutil.rmtree(broken / "lib")
    env = hr.script_env(runtime.home, broken)

    done = hr.run_script_help(broken / case.script, env, cwd=runtime.workdir)

    assert done.returncode != 0
    assert case.missing_lib in done.stderr


@pytest.mark.smoke
@pytest.mark.hermes
@needs_hermes
def test_every_pack_installs_a_manifest_and_its_own_lib(runtime: Runtime) -> None:
    for pack in runtime.config.packs:
        installed = runtime.pack_dir(pack.key)
        assert (installed / "plugin.json").is_file(), pack.key
        assert (installed / "lib" / "github_core" / "__init__.py").is_file(), pack.key
        assert (installed / "lib" / "bootstrap.py").is_file(), pack.key
