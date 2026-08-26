"""Runtime tests: run_completion_gate under an installed-plugin layout.

Issue #2572: the installed Copilot plugin copy of run_completion_gate.py failed
with ``ModuleNotFoundError: No module named 'scripts'`` because the repo's
top-level scripts/ package is not bundled with the skill and the project-root
walk started from the script location (inside installed-plugins/) instead of
the user's working directory. The first test copies the script to a directory
with no scripts/ tree above it and runs it from a separate working directory,
asserting the module loads (``--help`` reaches argparse).

Issue #5112: ``resolve_pr_review_config()`` in ``.claude/commands/pr-review.md``
offers plugin roots as config sources, but path containment refused any
``--config`` outside the consumer repository, so an installed ``/pr-review``
whose config resolved to the bundled copy could not dispatch at all. Option 1
of that issue admits a config inside a host-declared plugin root OUTSIDE the
work tree as a second trusted origin. The remaining tests exercise that end to
end, in the layout the issue describes.

How these tests discriminate, and why the obvious assertion does not
--------------------------------------------------------------------
An earlier revision asserted ``"install-trusted" not in result.stderr``. That
assertion cannot fail: the status reaches the JSON payload on stdout and is
never written to stderr, so it held whether or not the config was wrongly
install-trusted (Copilot review, PR #5329). It is replaced by two strings that
the gate really does print, one on each side of the decision:

``Refusing to load config from unsafe path``
    Emitted by ``_resolve_and_read_config`` when work-tree containment rejects
    the path. Present in the pre-issue-#5112 behavior, absent once a root
    install-trusts the config.

``HALT: completion-gate config``
    Emitted by ``_enforce_config_trust`` (both its git-error and its untrusted
    branch), and by nothing else; the command-trust halts read "completion-gate
    verifier files". An install-trusted config SKIPS verification, so this
    string is absent exactly when install trust applied and present exactly
    when it did not. That makes it the discriminator these tests turn on,
    falsifiable in both directions.

These fixtures deliberately stop at the config boundary rather than proving a
criterion executed. Reaching dispatch needs a real remote-tracking trusted ref
and command-trust verification of every argv file, which is a different
boundary with its own tests. What issue #5112 reports, and what these pin, is
whether the gate accepts the bundled config at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "run_completion_gate.py"
)

# Quoted verbatim from run_completion_gate so these cannot drift from the
# messages they assert on (.claude/rules/canonical-source-mirror.md):
#   _resolve_and_read_config:
#     f"Refusing to load config from unsafe path {config_arg!r}: {exc}"
#   _enforce_config_trust:
#     f"HALT: completion-gate config {config_path} cannot be "
#     f"HALT: completion-gate config {config_path} is not trusted "
_CONTAINMENT_REFUSAL = "Refusing to load config from unsafe path"
_CONFIG_TRUST_HALT = "HALT: completion-gate config"

# `command` must be a non-empty STRING; _validate_criterion_schema rejects a
# list ("criterion {name!r}: command must be a non-empty string"). An earlier
# revision used ["true"] here, which could never have reached dispatch
# (Copilot review, PR #5329).
_CONFIG_BODY = """completion_criteria:
  - name: placeholder
    command: "true"
"""


def _install_plugin(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build an installed-plugin layout beside a separate consumer repo.

    Returns ``(plugin_root, bundled_config, user_repo)``. The plugin root is a
    SIBLING of the consumer repo, never an ancestor of it, which is the
    arrangement a real install produces and the only one condition 3 admits.
    """
    plugin_root = tmp_path / "installed-plugins" / "project-toolkit"
    script_dir = plugin_root / "skills" / "github" / "scripts" / "pr"
    script_dir.mkdir(parents=True)
    shutil.copy2(_SCRIPT, script_dir / "run_completion_gate.py")

    bundled_config = plugin_root / "commands" / "pr-review-config.yaml"
    bundled_config.parent.mkdir(parents=True)
    bundled_config.write_text(_CONFIG_BODY, encoding="utf-8")

    user_repo = tmp_path / "user_repo"
    (user_repo / ".git").mkdir(parents=True)
    return plugin_root, bundled_config, user_repo


def _run_gate(
    plugin_root: Path,
    config: Path,
    user_repo: Path,
    *,
    env_var: str | None,
    env_value: str | None = None,
) -> subprocess.CompletedProcess[str]:
    script = plugin_root / "skills" / "github" / "scripts" / "pr" / "run_completion_gate.py"
    env = dict(os.environ)
    # Clear both so an ambient value in the developer's own shell cannot
    # decide the outcome of a test about these variables.
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("COPILOT_PLUGIN_ROOT", None)
    if env_var is not None:
        env[env_var] = env_value if env_value is not None else str(plugin_root)
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--pull-request",
            "1",
            "--config",
            str(config),
        ],
        cwd=user_repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def test_runs_from_installed_path_without_scripts_tree(tmp_path: Path) -> None:
    # Simulate the installed plugin: script under .../skills/github/scripts/pr/
    # with no scripts/ package above it.
    installed = tmp_path / "installed-plugins" / "skills" / "github" / "scripts" / "pr"
    installed.mkdir(parents=True)
    shutil.copy2(_SCRIPT, installed / "run_completion_gate.py")

    # Separate working directory standing in for the user's repo (no scripts/).
    user_repo = tmp_path / "user_repo"
    (user_repo / ".git").mkdir(parents=True)

    result = subprocess.run(
        [sys.executable, str(installed / "run_completion_gate.py"), "--help"],
        cwd=user_repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "run_completion_gate.py" in result.stdout


def test_bundled_config_is_refused_without_a_declared_plugin_root(
    tmp_path: Path,
) -> None:
    """Negative control for the two tests below.

    With neither variable set the bundled config is outside the consumer repo
    and nothing install-trusts it, so containment refuses it. This is the
    pre-issue-#5112 behavior and it must survive unchanged, otherwise the
    tests asserting that refusal is ABSENT prove nothing.
    """
    plugin_root, config, user_repo = _install_plugin(tmp_path)

    result = _run_gate(plugin_root, config, user_repo, env_var=None)

    assert _CONTAINMENT_REFUSAL in result.stderr, result.stderr
    assert result.returncode != 0, result.stdout


def test_claude_plugin_root_admits_the_bundled_config(tmp_path: Path) -> None:
    plugin_root, config, user_repo = _install_plugin(tmp_path)

    result = _run_gate(
        plugin_root, config, user_repo, env_var="CLAUDE_PLUGIN_ROOT",
    )

    assert _CONTAINMENT_REFUSAL not in result.stderr, result.stderr
    # Install trust SKIPS verification, so the config-trust halt must not
    # appear. This is the assertion that fails if the root stops being
    # honored; the containment check above only proves the path was accepted.
    assert _CONFIG_TRUST_HALT not in result.stderr, result.stderr


def test_copilot_plugin_root_admits_the_bundled_config(tmp_path: Path) -> None:
    """Both host variables work, per resolve_pr_review_config's own list."""
    plugin_root, config, user_repo = _install_plugin(tmp_path)

    result = _run_gate(
        plugin_root, config, user_repo, env_var="COPILOT_PLUGIN_ROOT",
    )

    assert _CONTAINMENT_REFUSAL not in result.stderr, result.stderr
    assert _CONFIG_TRUST_HALT not in result.stderr, result.stderr


def test_a_root_that_is_an_ancestor_of_the_repo_does_not_install_trust(
    tmp_path: Path,
) -> None:
    """The bypass Copilot found on PR #5329, pinned.

    Condition 3 originally tested only "the root is not below the project".
    A root that is an ANCESTOR of the project passes that one-way test while
    containing every PR-controlled file in the repo, so a config the checked-out
    PR wrote became install-trusted and skipped byte-identity verification
    (CWE-829). Condition 3 now requires the two trees to be disjoint.

    The config here lives inside the consumer repo, so containment accepts it;
    the question is purely whether verification is skipped. The trust halt must
    be PRESENT, proving install trust did not apply.
    """
    plugin_root, _, user_repo = _install_plugin(tmp_path)
    ancestor = user_repo.parent
    pr_controlled = user_repo / ".claude" / "commands" / "pr-review-config.yaml"
    pr_controlled.parent.mkdir(parents=True)
    pr_controlled.write_text(_CONFIG_BODY, encoding="utf-8")

    result = _run_gate(
        plugin_root,
        pr_controlled,
        user_repo,
        env_var="CLAUDE_PLUGIN_ROOT",
        env_value=str(ancestor),
    )

    assert _CONFIG_TRUST_HALT in result.stderr, result.stderr
    assert result.returncode != 0, result.stdout


def test_in_repo_plugin_root_does_not_install_trust_its_config(
    tmp_path: Path,
) -> None:
    """The PR-controlled in-repo fallback root gets no widening.

    ``resolve_pr_review_config`` falls back to ``.claude`` inside the consumer
    repo. That directory is written by the checked-out PR, so condition 3
    refuses it as an install-trusted origin even when the operator points a
    plugin-root variable at it. The config then takes the ordinary path:
    containment passes (it is inside the repo) and verification applies.
    """
    plugin_root, _, user_repo = _install_plugin(tmp_path)
    in_repo_root = user_repo / ".claude"
    in_repo_config = in_repo_root / "commands" / "pr-review-config.yaml"
    in_repo_config.parent.mkdir(parents=True)
    in_repo_config.write_text(_CONFIG_BODY, encoding="utf-8")

    result = _run_gate(
        plugin_root,
        in_repo_config,
        user_repo,
        env_var="CLAUDE_PLUGIN_ROOT",
        env_value=str(in_repo_root),
    )

    assert _CONFIG_TRUST_HALT in result.stderr, result.stderr
    assert result.returncode != 0, result.stdout


def test_symlink_out_of_the_plugin_root_is_not_install_trusted(
    tmp_path: Path,
) -> None:
    """A link planted in the install directory cannot borrow install trust.

    Condition 4 resolves the config before containment, so a symlink whose
    target is the checked-out repo lands outside the plugin root and does not
    install-trust (CWE-59).

    It is NOT hard-refused, and that is deliberate: it falls through to the
    ordinary path, where work-tree containment accepts the in-repo target and
    byte-identity verification then applies to it. That is strictly more
    scrutiny than install trust would have given, not less. The assertion is
    therefore that verification RAN, not that the path was rejected.
    """
    plugin_root, _, user_repo = _install_plugin(tmp_path)
    attacker_config = user_repo / "evil-config.yaml"
    attacker_config.write_text(_CONFIG_BODY, encoding="utf-8")

    link = plugin_root / "commands" / "linked-config.yaml"
    link.symlink_to(attacker_config)

    result = _run_gate(
        plugin_root, link, user_repo, env_var="CLAUDE_PLUGIN_ROOT",
    )

    assert _CONFIG_TRUST_HALT in result.stderr, result.stderr
    assert result.returncode != 0, result.stdout
