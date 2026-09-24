"""`--codex-auth-file` coverage for the capability-matrix CLI (issue #5423).

Split out of `test_harness_capability_codex_probe.py` after PR review flagged
that file over the 500-line taste-lint limit; this is its opt-in
credential-copy slice, not a new test category.

A ChatGPT-login Codex authenticates only through `$CODEX_HOME/auth.json`;
`CODEX_ACCESS_TOKEN` is ignored (probed 2026-09-24, codex-cli 0.156.0: a
ChatGPT access token in that variable produced a 401 "Missing bearer" against
api.openai.com). `runtime_env`'s isolated profile carries no such file, so a
codex behavioral probe has no working auth unless the operator opts in with
`--codex-auth-file`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._harness_capability_test_support import UNPROBED_MATRIX, cli


@pytest.fixture(autouse=True)
def _start_from_the_unprobed_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI default at the pre-probe matrix, not the live-probed one."""
    monkeypatch.setattr(cli, "DEFAULT_MATRIX", UNPROBED_MATRIX)


class _MultiHarnessRunner:
    """Dispatch fake `--version` output keyed by the invoked executable."""

    def __init__(
        self,
        *,
        versions: dict[str, str] | None = None,
        fail: frozenset[str] = frozenset(),
        stdout: str = "",
    ) -> None:
        self.versions = versions or {}
        self.fail = fail
        self.stdout = stdout
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []

    def __call__(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        self.calls.append(args)
        self.kwargs.append(dict(_kwargs))
        executable = args[0]
        if executable in self.fail:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        if "--version" not in args:
            return subprocess.CompletedProcess(args, 0, self.stdout, "")
        return subprocess.CompletedProcess(args, 0, self.versions.get(executable, ""), "")


class _CodexEffortRunner:
    """Return a codex version on `--version`, and fixed stdout/stderr otherwise."""

    def __init__(self, *, version: str, stdout: str, stderr: str) -> None:
        self.version = version
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []

    def __call__(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        self.calls.append(args)
        self.kwargs.append(dict(_kwargs))
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, self.version, "")
        return subprocess.CompletedProcess(args, 0, self.stdout, self.stderr)


def _which_only(*names: str):
    allowed = set(names)
    return lambda name: f"/bin/{name}" if name in allowed else None


def _write_model_probe(path: Path) -> None:
    path.write_text(
        '{"probes":[{"harness":"copilot","capability":"model_override",'
        '"parent_value":"gpt-5.6-sol","child_value":"claude-opus-5",'
        '"cwd":"nested","argv":["copilot","--prompt","probe"],'
        '"request_flag":"--model"}]}',
        encoding="utf-8",
    )


def _write_codex_effort_probe(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "harness": "codex",
                        "capability": "effort_override",
                        "parent_value": "medium",
                        "child_value": "low",
                        "argv": ["codex", "exec", "--json", "-m", "gpt-5.6-sol"],
                        "request_flag": "-c",
                        "env": {"RUST_LOG": "tungstenite::protocol=trace"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_codex_auth_file_is_copied_into_the_isolated_codex_home(
    tmp_path: Path, monkeypatch
) -> None:
    """POSITIVE: the operator's auth.json lands at `$CODEX_HOME/auth.json`, mode 0600,
    for the probe that uses it.

    `_augment_behavioral` deletes the copy once the probe returns, whether it
    succeeded or raised (see the two tests below), so the only place left to
    observe the copy's content and mode is from inside the runner itself,
    mid-probe, before the CLI's cleanup can run.
    """
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    _write_codex_effort_probe(plan)
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex"))
    frame = '{"type":"response.completed","response":{"reasoning":{"effort":"low"}}}'
    seen_auth: list[tuple[str, str]] = []

    class _RecordingCodexRunner:
        def __call__(
            self, argv: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            args = [str(value) for value in argv]
            if "--version" in args:
                return subprocess.CompletedProcess(args, 0, "codex-cli 0.156.0", "")
            env = kwargs.get("env")
            assert isinstance(env, dict)
            installed = Path(str(env["CODEX_HOME"])) / "auth.json"
            seen_auth.append(
                (installed.read_text(encoding="utf-8"), oct(installed.stat().st_mode)[-3:])
            )
            stdout = json.dumps({"type": "turn.completed", "data": {"usage": {}}}) + "\n"
            stderr = f"TRACE tungstenite::protocol: Received message {frame}\n"
            return subprocess.CompletedProcess(args, 0, stdout, stderr)

    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"tokens": {}}', encoding="utf-8")

    code = cli.main(
        [
            "--output",
            str(output),
            "--behavioral-probes",
            str(plan),
            "--codex-auth-file",
            str(auth_file),
        ],
        runner=_RecordingCodexRunner(),
    )

    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    codex = next(row for row in report["harnesses"] if row["harness"] == "codex")
    assert codex["capabilities"]["effort_override"]["status"] == "VERIFIED"
    assert seen_auth == [('{"tokens": {}}', "600")]


def test_codex_auth_file_is_removed_after_the_probe_runs(tmp_path: Path, monkeypatch) -> None:
    """POSITIVE: the copied credential does not outlive the one probe it authenticated."""
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    _write_codex_effort_probe(plan)
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex"))
    frame = '{"type":"response.completed","response":{"reasoning":{"effort":"low"}}}'
    runner = _CodexEffortRunner(
        version="codex-cli 0.156.0",
        stdout=json.dumps({"type": "turn.completed", "data": {"usage": {}}}) + "\n",
        stderr=f"TRACE tungstenite::protocol: Received message {frame}\n",
    )
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"tokens": {}}', encoding="utf-8")

    code = cli.main(
        [
            "--output",
            str(output),
            "--behavioral-probes",
            str(plan),
            "--codex-auth-file",
            str(auth_file),
        ],
        runner=runner,
    )

    assert code == 0
    behavioral_kwargs = runner.kwargs[-1]
    env = behavioral_kwargs["env"]
    assert isinstance(env, dict)
    codex_home = Path(str(env["CODEX_HOME"]))
    assert not (codex_home / "auth.json").exists()


def test_codex_auth_file_is_removed_even_when_the_runner_raises(
    tmp_path: Path, monkeypatch
) -> None:
    """POSITIVE: the credential copy is cleaned up on the failure path too.

    `probe_override` itself catches `FileNotFoundError`, `OSError`, and
    `subprocess.SubprocessError` from the runner and turns them into an
    UNVERIFIED result, so none of those would exercise the cleanup's
    exception path at all: the call into `_run_behavioral_probe` would
    return normally either way. This runner raises `RuntimeError`, which
    none of `probe_override`'s handlers catch, so it propagates uncaught
    through `_augment_behavioral`. The `try/finally` around the probe call
    there must still delete the copied `auth.json` before that exception
    continues past it.
    """
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    _write_codex_effort_probe(plan)
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex"))
    seen_codex_home: list[Path] = []

    class _RaisingCodexRunner:
        def __call__(
            self, argv: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            args = [str(value) for value in argv]
            if "--version" in args:
                return subprocess.CompletedProcess(args, 0, "codex-cli 0.156.0", "")
            env = kwargs.get("env")
            assert isinstance(env, dict)
            seen_codex_home.append(Path(str(env["CODEX_HOME"])))
            raise RuntimeError("boom: simulated crash inside the runner")

    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"tokens": {}}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="boom"):
        cli.run(
            matrix_path=cli.DEFAULT_MATRIX,
            output=output,
            copilot_bin="copilot",
            timeout=5.0,
            dry_run=False,
            runner=_RaisingCodexRunner(),
            behavioral_probes=plan,
            codex_auth_file=auth_file,
        )

    assert seen_codex_home
    assert not (seen_codex_home[0] / "auth.json").exists()


@pytest.mark.skipif(cli.os.name == "nt", reason="POSIX file-mode bits")
def test_codex_home_directory_is_created_mode_0700(tmp_path: Path, monkeypatch) -> None:
    """POSITIVE: the profile directory holding the credential copy is not group/other readable."""
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    _write_codex_effort_probe(plan)
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex"))
    frame = '{"type":"response.completed","response":{"reasoning":{"effort":"low"}}}'
    runner = _CodexEffortRunner(
        version="codex-cli 0.156.0",
        stdout=json.dumps({"type": "turn.completed", "data": {"usage": {}}}) + "\n",
        stderr=f"TRACE tungstenite::protocol: Received message {frame}\n",
    )
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"tokens": {}}', encoding="utf-8")

    code = cli.main(
        [
            "--output",
            str(output),
            "--behavioral-probes",
            str(plan),
            "--codex-auth-file",
            str(auth_file),
        ],
        runner=runner,
    )

    assert code == 0
    behavioral_kwargs = runner.kwargs[-1]
    env = behavioral_kwargs["env"]
    assert isinstance(env, dict)
    codex_home = Path(str(env["CODEX_HOME"]))
    assert oct(codex_home.stat().st_mode)[-3:] == "700"


def test_codex_auth_file_refuses_a_non_regular_file(tmp_path: Path, monkeypatch) -> None:
    """NEGATIVE CONTROL: a directory is not a regular file; fail closed before any CLI call."""
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    plan.write_text(
        json.dumps(
            {"probes": [{"harness": "codex", "capability": "subagent_support", "argv": ["codex"]}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex"))
    runner = _MultiHarnessRunner(versions={"codex": "codex-cli 0.156.0"})
    not_a_file = tmp_path / "a-directory"
    not_a_file.mkdir()

    code = cli.main(
        [
            "--output",
            str(output),
            "--behavioral-probes",
            str(plan),
            "--codex-auth-file",
            str(not_a_file),
        ],
        runner=runner,
    )

    assert code == cli.EXIT_CONFIG
    assert not any("exec" in call for call in runner.calls)


def test_codex_auth_file_refuses_a_missing_path_directly() -> None:
    """NEGATIVE CONTROL: `_install_codex_auth` is the single validation point."""
    with pytest.raises(cli.HarnessCapabilityError, match="is not a regular file"):
        cli._install_codex_auth(Path("/nonexistent/auth.json"), Path("/tmp/unused-codex-home"))


def test_codex_auth_file_is_ignored_for_a_copilot_only_plan(tmp_path: Path, monkeypatch) -> None:
    """NEGATIVE CONTROL: a codex-only opt-in must not touch a copilot probe.

    Points `--codex-auth-file` at a path that does not exist. If the flag were
    applied to a copilot probe, `_install_codex_auth` would raise and this run
    would exit non-zero; it does not, because no codex probe runs here at all.
    """
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    _write_model_probe(plan)
    monkeypatch.setattr(cli.shutil, "which", _which_only("custom-copilot"))
    runner = _MultiHarnessRunner(
        versions={"custom-copilot": "copilot 9.9.9"},
        stdout=json.dumps(
            {"type": "assistant.message", "data": {"content": "ok", "model": "claude-opus-5"}}
        )
        + "\n",
    )
    missing_auth = tmp_path / "does-not-exist.json"

    code = cli.main(
        [
            "--output",
            str(output),
            "--copilot-bin",
            "custom-copilot",
            "--behavioral-probes",
            str(plan),
            "--codex-auth-file",
            str(missing_auth),
        ],
        runner=runner,
    )

    assert code == 0
