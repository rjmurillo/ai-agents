# taste-lint: ignore file-size, one suite shares the installed-plugin
# layout fixtures (_install_plugin, _git_init, _run_gate, _CONFIG_BODY)
# across every install-trust state. Splitting it duplicates the layout
# builder or moves it to a module that pytest's rootdir insertion does
# not reliably import from tests/, and each case here is only readable
# against the same layout. Same rationale as test_why_pr_blocked.py.
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

These fixtures reach dispatch, and one asserts on it.
``test_the_bundled_config_runs_its_criteria_end_to_end`` runs the criterion and
reads the parsed ``--json`` payload, because the absence assertions above
cannot separate "install trust worked" from "the run died earlier for an
unrelated reason".

An earlier version of this paragraph claimed the opposite, that the fixtures
"deliberately stop at the config boundary", on the reasoning that dispatch
would need a real remote-tracking trusted ref and command-trust verification of
every argv file. Both halves were wrong, and each was wrong in a way that hid a
defect. ``_install_plugin`` now builds a real work tree WITH
``refs/remotes/origin/main``, which the install-trusted path requires like any
other; the version that lacked one passed only because the ref check was being
skipped, and that skip was itself the security defect (Copilot review,
PR #5329). And the criterion here names ``printf``, which resolves to a path
inside the work tree that is not a file, so ``_classify_argv_token`` returns
``_ARGV_SKIP`` and there is no work-tree file to byte-compare.

That second fact is stated the way it is because an earlier version of this
paragraph got it wrong in a specific way worth naming. It said ``printf`` was
classified as EXTERNAL, reasoning from "it is a bare interpreter name, so it
must be outside the tree". Reading ``_classify_argv_token`` shows
``_ARGV_EXTERNAL`` requires a resolved path outside the tree that IS a file;
a bare name that resolves to nothing takes the ``_ARGV_SKIP`` branch instead.
The refutation was already in this file's own end-to-end payload, where
``skipped_external_files`` is empty, and I did not read it. Both branches
refuse to compare, so nothing was broken, but the claim would have misled the
next person reasoning about which tokens get verified.
"""

from __future__ import annotations

import json
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

# Quoted verbatim from .claude/skills/github/scripts/pr/run_completion_gate.py
# (the canonical source; src/copilot-cli/... is its generated mirror) so these
# cannot drift from the messages they assert on. The rule requires the path,
# not just the module name (.claude/rules/canonical-source-mirror.md):
#   _resolve_and_read_config:
#     f"Refusing to load config from unsafe path {config_arg!r}: {exc}"
#   _enforce_config_trust:
#     f"HALT: completion-gate config {config_path} cannot be "
#     f"HALT: completion-gate config {config_path} is not trusted "
_CONTAINMENT_REFUSAL = "Refusing to load config from unsafe path"
_CONFIG_TRUST_HALT = "HALT: completion-gate config"
# The command-trust halt, distinct from the config one above:
#     f"HALT: completion-gate verifier files cannot be verified "
_COMMAND_TRUST_HALT = "HALT: completion-gate verifier files"

# Must satisfy _validate_criterion_schema in full, not merely parse as YAML.
# Required: `name` (non-empty str), `verification: command`, `command` (non-empty
# STRING; a list raises "command must be a non-empty string"), and exactly one of
# `pass_when` / `pass_when_python`. An earlier revision used ["true"] with no
# `verification` key, so every run died at schema validation and no case that
# asserts on a LATER stage (command trust, dispatch) could observe that stage at
# all. Found by mutation: removing the work-tree anchor left the bypass case
# failing on a schema error rather than on the boundary under test.
# The criterion emits a JSON object and pass_when reads a key out of it, so a
# run that reaches dispatch is observable in the payload rather than inferred
# from an exit code. `printf` resolves to <cwd>/printf, which is INSIDE the
# work tree and is not a file, so _classify_argv_token returns _ARGV_SKIP and
# there is no work-tree file to byte-compare. Not _ARGV_EXTERNAL: that branch
# needs a resolved path OUTSIDE the tree that IS a file, so
# `command_trust.skipped_external_files` stays empty here. An earlier comment
# claimed external; the payload in this file's own end-to-end case shows the
# list empty, which was the evidence against it sitting in plain sight
# (Copilot review, PR #5329).
# `true` (YAML/Python) is not a pass_when literal; the evaluator wants `true`
# lowercase, and `True` raises "Unrecognized literal in pass_when".
_CONFIG_BODY = """completion_criteria:
  - name: placeholder
    verification: command
    command: "printf '{\\"gate_ran\\": true}'"
    pass_when: "gate_ran == true"
"""


def _git_init(path: Path) -> None:
    """Make `path` a real git work tree with a remote-tracking trust anchor.

    An empty ``.git`` directory is not enough: ``_consumer_work_tree`` shells
    out to ``git rev-parse --show-toplevel``, which reports
    "fatal: not a git repository" for one. Verified before relying on it.

    ``refs/remotes/origin/main`` is created because the default
    ``--trusted-ref origin/main`` must resolve to a remote-tracking ref on
    the install-trusted path too. An earlier fixture omitted it and passed
    only because that check was being skipped, which was the bug (Copilot
    review, PR #5329). A fixture that satisfies a guard only when the guard
    is absent is not a fixture, it is the defect wearing a costume.
    """
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", *a], cwd=path, check=True, capture_output=True, text=True,
    )
    run("init", "--quiet")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "test")
    run("commit", "--quiet", "--allow-empty", "-m", "base")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    run("update-ref", "refs/remotes/origin/main", head)


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
    user_repo.mkdir(parents=True)
    _git_init(user_repo)
    return plugin_root, bundled_config, user_repo


def _run_gate(
    plugin_root: Path,
    config: Path,
    user_repo: Path,
    *,
    env_var: str | None,
    env_value: str | None = None,
    json_output: bool = False,
    trusted_ref: str | None = None,
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
            *(["--json"] if json_output else []),
            *(["--trusted-ref", trusted_ref] if trusted_ref else []),
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


def test_install_trust_exits_3_when_git_is_not_on_path(tmp_path: Path) -> None:
    """Missing git is external (exit 3), like the non-work-tree case.

    Same layout as the passing case; the only change is an emptied PATH, so
    ``_run_git`` raises ``FileNotFoundError``. That IS an ``OSError``, so it
    was already caught, but nothing asserted which code it produced and the
    old code produced 2.
    """
    plugin_root, config, user_repo = _install_plugin(tmp_path)
    script = (
        plugin_root / "skills" / "github" / "scripts" / "pr"
        / "run_completion_gate.py"
    )
    env = dict(os.environ)
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    # An empty directory as the whole PATH: git cannot be found, but the
    # interpreter is invoked by absolute path so the run still starts.
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env["PATH"] = str(empty_bin)

    result = subprocess.run(
        [sys.executable, str(script), "--pull-request", "1",
         "--config", str(config)],
        cwd=user_repo, capture_output=True, encoding="utf-8",
        errors="replace", env=env, check=False,
    )

    assert result.returncode == 3, (result.returncode, result.stderr)
    assert "could not run git" in result.stderr, result.stderr
    assert _CONTAINMENT_REFUSAL not in result.stderr, result.stderr


def test_a_local_trusted_ref_is_refused_for_an_installed_config(
    tmp_path: Path,
) -> None:
    """`--trusted-ref HEAD` cannot anchor trust, install-trusted or not.

    Reproduced before the fix: install trust short-circuited ahead of BOTH
    ref guards, and `_enforce_command_trust` repeats neither, so command
    trust compared every work-tree verifier against the PR's OWN commit.
    A PR-modified verifier was declared trusted and executed. Exit 3, and
    `--approve-untrusted-config` does not override it.
    """
    plugin_root, config, user_repo = _install_plugin(tmp_path)

    result = _run_gate(
        plugin_root, config, user_repo,
        env_var="CLAUDE_PLUGIN_ROOT", trusted_ref="HEAD",
    )

    assert result.returncode == 3, (result.returncode, result.stderr)
    assert "remote-tracking" in result.stderr, result.stderr
    # Proof no criterion ran: the fixture criterion prints this key.
    assert "gate_ran" not in result.stdout, result.stdout


def test_an_option_shaped_trusted_ref_is_refused_for_an_installed_config(
    tmp_path: Path,
) -> None:
    """The regex guard runs ahead of the install short-circuit.

    Before the fix the raw value reached a git invocation, which is the
    argument-injection surface `_TRUSTED_REF_RE` exists to close.
    """
    plugin_root, config, user_repo = _install_plugin(tmp_path)

    result = _run_gate(
        plugin_root, config, user_repo,
        env_var="CLAUDE_PLUGIN_ROOT",
        trusted_ref="--upload-pack=touch /tmp/should-not-exist",
    )

    assert result.returncode == 2, (result.returncode, result.stderr)
    assert "Refusing malformed --trusted-ref" in result.stderr, result.stderr
    assert "gate_ran" not in result.stdout, result.stdout


def test_the_bundled_config_runs_its_criteria_end_to_end(tmp_path: Path) -> None:
    """Positive control for every absence assertion in this file.

    The other install cases assert that a refusal string is ABSENT, which
    cannot distinguish "install trust worked" from "the run died earlier for
    an unrelated reason". This drives the same layout with --json and reads
    the structured payload, so the claim is what the gate reported rather
    than what a substring search did not find (testing.md MUST 9).

    Requested in Copilot review on PR #5329: the acceptance criterion for
    issue #5112 is that an installed /pr-review can DISPATCH its bundled
    config, and until this case existed nothing observed a criterion running.
    """
    plugin_root, config, user_repo = _install_plugin(tmp_path)

    result = _run_gate(
        plugin_root, config, user_repo,
        env_var="CLAUDE_PLUGIN_ROOT", json_output=True,
    )

    assert result.returncode == 0, (result.returncode, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["config_trust"]["status"] == "install-trusted"
    # The config was install-trusted; the FILES its criteria name were still
    # verified. Widening the config origin must not widen the command
    # boundary, so this is not incidental detail.
    assert payload["command_trust"]["status"] == "trusted"
    assert payload["all_passed"] is True
    criterion = payload["criteria"][0]
    # Proof of execution, not of acceptance: the gate ran the command and
    # parsed what the command printed.
    assert criterion["passed"] is True
    assert criterion["exit_code"] == 0
    assert criterion["stdout_json"] == {"gate_ran": True}
    # `printf` takes the _ARGV_SKIP branch, NOT _ARGV_EXTERNAL: it resolves
    # inside the work tree and is not a file. Pinned because the reverse was
    # asserted in prose here and stood for several revisions.
    assert payload["command_trust"]["skipped_external_files"] == []
    assert payload["command_trust"]["checked_files"] == []


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


def test_a_pr_created_nested_claude_cannot_relocate_the_trust_boundary(
    tmp_path: Path,
) -> None:
    """The second bypass Copilot found on PR #5329, pinned.

    ``_resolve_project_root`` falls back to the nearest ancestor of the cwd
    holding ``.claude`` OR ``.git``, and PR content can create a ``.claude``
    directory. With the host started in ``repo/subdir`` and the PR adding
    ``repo/subdir/.claude``, ``_PROJECT_ROOT`` becomes ``repo/subdir``, so a
    declared root of ``repo/.claude`` is neither above nor below it. A
    disjointness test anchored on ``_PROJECT_ROOT`` therefore passed, and a
    wholly PR-controlled config became install-trusted (CWE-829).

    ``_install_trusted_root`` now anchors on ``git rev-parse --show-toplevel``,
    which PR content cannot move. Reproduced end to end before the fix: the
    config-trust halt was absent (verification skipped) and execution reached
    command trust.

    Asserted here on the containment refusal rather than on the absence of a
    halt string. Once install trust is correctly withheld the run fails
    EARLIER, at work-tree containment, so an absence-only assertion would pass
    for the wrong reason.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git_init(repo)

    # PR-controlled, inside the real work tree.
    declared_root = repo / ".claude"
    (declared_root / "commands").mkdir(parents=True)
    config = declared_root / "commands" / "pr-review-config.yaml"
    config.write_text(_CONFIG_BODY, encoding="utf-8")

    # The nested .claude the malicious PR adds, in the directory the host
    # starts from. This is what used to relocate _PROJECT_ROOT.
    subdir = repo / "subdir"
    (subdir / ".claude").mkdir(parents=True)

    installed = tmp_path / "plug" / "skills" / "github" / "scripts" / "pr"
    installed.mkdir(parents=True)
    shutil.copy2(_SCRIPT, installed / "run_completion_gate.py")

    env = dict(os.environ)
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env["CLAUDE_PLUGIN_ROOT"] = str(declared_root)

    result = subprocess.run(
        [
            sys.executable,
            str(installed / "run_completion_gate.py"),
            "--pull-request",
            "1",
            "--config",
            str(config),
        ],
        cwd=subdir,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert _CONTAINMENT_REFUSAL in result.stderr, result.stderr
    # Never reached command trust, so no criterion could have run. With the
    # bypass present this string WAS produced.
    assert _COMMAND_TRUST_HALT not in result.stderr, result.stderr
    assert result.returncode == 2, (result.returncode, result.stderr)


def test_install_trust_fails_closed_outside_a_git_work_tree(
    tmp_path: Path,
) -> None:
    """No establishable work tree halts with exit 3, not exit 2.

    Nothing can be shown to lie outside PR-controlled content, so install
    trust is withheld. The layout is otherwise the valid one from
    ``_install_plugin``, so the only difference from the passing case is
    the missing work tree.

    The CODE is the point, not just the halt. An earlier revision returned
    ``None`` from the probe and fell through to containment, exiting 2 with
    "Refusing to load config from unsafe path". It failed closed, but named
    the wrong cause: the path was fine, the work tree was not establishable.
    Per ADR-035 and this repo's table (2 config, 3 external) that is a 3.
    Found by Copilot review on PR #5329.
    """
    plugin_root, config, user_repo = _install_plugin(tmp_path)
    # Remove the marker that makes this look like a work tree. git then
    # reports no toplevel for this cwd.
    shutil.rmtree(user_repo / ".git")

    # Precondition, not decoration. If TMPDIR happened to sit inside a
    # repository, git would walk up and report ITS toplevel, install trust
    # would be evaluated normally, and the assertions below would pass for
    # a reason unrelated to the fail-closed branch under test.
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=user_repo, capture_output=True, text=True, check=False,
    )
    assert probe.returncode != 0, (
        f"cwd is inside a work tree at {probe.stdout.strip()!r}; "
        "this case cannot exercise the fail-closed branch"
    )

    result = _run_gate(
        plugin_root, config, user_repo, env_var="CLAUDE_PLUGIN_ROOT",
    )

    assert result.returncode == 3, (result.returncode, result.stderr)
    assert "Refusing to evaluate install trust" in result.stderr, result.stderr
    # The old exit-2 message must be GONE, not merely accompanied. A
    # positive-only assertion would pass on a run that printed both.
    assert _CONTAINMENT_REFUSAL not in result.stderr, result.stderr
