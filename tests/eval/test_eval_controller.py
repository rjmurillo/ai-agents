# taste-lint: ignore file-size
# One contract, one shared fake scorer and proposer. Splitting the file would
# scatter the setup every test reads; the sibling optimize-artifact suite does
# the same.
"""Tests for scripts/eval/eval_controller.py (ADR-087 Open Requirement 1, #7678).

The controller runs the optimizing agent as a child proposer. The properties
under test are the ones the cooperating-optimizer design could not give:

- the proposer's workspace never holds a held-out task id or outcome,
- the proposer learns one bit per gated candidate,
- a rejected candidate never stays on disk,
- an edited task definition stops the loop before it is scored,
- the consultation cap comes from the launcher's config, not the proposer.

The scorer is a deterministic fake that emits JUnit XML (the hook kind), so
these tests spend no eval budget.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "eval_controller.py"
_spec = importlib.util.spec_from_file_location("eval_controller", _SCRIPT)
assert _spec is not None and _spec.loader is not None
ec = importlib.util.module_from_spec(_spec)
sys.modules["eval_controller"] = ec
_spec.loader.exec_module(ec)

TASKS = [f"T{n:02d}" for n in range(1, 11)]

_SCORER = textwrap.dedent(
    """
    import json, sys
    from xml.sax.saxutils import quoteattr
    artifact, out = sys.argv[1], sys.argv[2]
    state = json.load(open(artifact))
    cases = []
    for task, ok in sorted(state.items()):
        body = "" if ok else "<failure message='no'/>"
        cases.append(f"<testcase classname='suite' name={quoteattr(task)}>{body}</testcase>")
    open(out, "w").write("<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>")
    """
)

# Each step writes the artifact named in the plan for that step, or leaves it
# alone when the plan has no entry. It also copies whatever it can see in the
# workspace into a transcript, so a test can assert what the proposer saw.
_PROPOSER = textwrap.dedent(
    """
    import json, os, sys
    feedback, artifact, plan, transcript = sys.argv[1:5]
    fb = json.load(open(feedback))
    seen = {}
    for root, _dirs, files in os.walk(os.path.dirname(feedback)):
        for name in files:
            seen[os.path.join(root, name)] = open(os.path.join(root, name)).read()
    with open(transcript, "a") as handle:
        handle.write(json.dumps({"feedback": fb, "seen": seen}) + "\\n")
    step = str(fb["step"])
    plan = json.load(open(plan))
    if step in plan:
        if plan[step] == "TAMPER":
            with open(os.environ["TAMPER_TARGET"], "a") as handle:
                handle.write("edited")
        else:
            json.dump(plan[step], open(artifact, "w"))
    """
)


def _setup(
    tmp_path: Path,
    plan: dict[str, Any],
    *,
    steps: int = 3,
    max_consultations: int = 3,
    initial: dict[str, bool] | None = None,
) -> tuple[Path, Path]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "scorer.py").write_text(_SCORER, encoding="utf-8")
    (scripts / "proposer.py").write_text(_PROPOSER, encoding="utf-8")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for task in TASKS:
        (fixtures / f"{task}.json").write_text(json.dumps({"id": task}), encoding="utf-8")
    artifact = tmp_path / "artifact.json"
    state = initial if initial is not None else {task: task <= "T05" for task in TASKS}
    artifact.write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    config = {
        "kind": "hook",
        "artifact": str(artifact),
        "state_dir": str(tmp_path / "state"),
        "workspace_dir": str(tmp_path / "workspace"),
        "scorer": [sys.executable, str(scripts / "scorer.py"), "{artifact}", "{run_dir}/junit.xml"],
        "inputs": ["{run_dir}/junit.xml"],
        "proposer": [
            sys.executable,
            str(scripts / "proposer.py"),
            "{feedback}",
            "{artifact}",
            str(tmp_path / "plan.json"),
            str(tmp_path / "transcript.jsonl"),
        ],
        "seed": "7642",
        "max_consultations": max_consultations,
        "steps": steps,
        "opt_task_files": str(fixtures / "{task_name}.json"),
        "deny_paths": [str(fixtures)],
        "proposer_env": ["TAMPER_TARGET"],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path, artifact


def _split(tmp_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (tmp_path / "state" / "split.json").read_text(encoding="utf-8")
    )
    return data


def _transcript(tmp_path: Path) -> list[dict[str, Any]]:
    lines = (tmp_path / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _all_true() -> dict[str, bool]:
    return {task: True for task in TASKS}


def test_accept_keeps_the_candidate_and_reports_one_bit(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=2)
    assert ec.main(["run", "--config", str(config)]) == 0
    assert json.loads(artifact.read_text(encoding="utf-8")) == _all_true()
    second = _transcript(tmp_path)[1]["feedback"]
    assert second["last_decision"] == "ACCEPT"
    assert set(second) == {
        "step",
        "artifact",
        "opt_results",
        "opt_score",
        "last_decision",
        "consultations_left",
    }


def test_reject_restores_the_incumbent(tmp_path: Path) -> None:
    worse = {task: False for task in TASKS}
    config, artifact = _setup(tmp_path, {"1": worse}, steps=2)
    before = artifact.read_text(encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == 0
    assert artifact.read_text(encoding="utf-8") == before
    assert _transcript(tmp_path)[1]["feedback"]["last_decision"] == "REJECT"


def test_proposer_never_sees_a_held_out_id(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {"1": _all_true()}, steps=2)
    assert ec.main(["run", "--config", str(config)]) == 0
    split = _split(tmp_path)
    held_out = [task.split("::")[-1] for task in split["sel"] + split["test"]]
    assert held_out
    for entry in _transcript(tmp_path):
        assert set(entry["feedback"]["opt_results"]) == set(split["opt"])
        blob = json.dumps(entry)
        for task in held_out:
            assert f"suite::{task}" not in blob
            assert f"{task}.json" not in blob


def test_opt_task_files_are_copied_and_nothing_else(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    assert ec.main(["run", "--config", str(config)]) == 0
    opt = {task.split("::")[-1] for task in _split(tmp_path)["opt"]}
    copied = {p.stem for p in (tmp_path / "workspace" / "tasks").iterdir()}
    assert copied == opt


def test_unchanged_artifact_spends_no_consultation(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=2, max_consultations=1)
    assert ec.main(["run", "--config", str(config)]) == 0
    feedback = _transcript(tmp_path)[1]["feedback"]
    assert feedback["last_decision"] == "NO_CHANGE"
    assert feedback["consultations_left"] == 1


def test_loop_stops_when_the_cap_is_spent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    worse = {task: False for task in TASKS}
    config, _ = _setup(tmp_path, {"1": worse, "2": worse, "3": worse}, steps=3, max_consultations=2)
    assert ec.main(["run", "--config", str(config)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["consultations_spent"] == 2
    assert summary["steps_run"] == 2
    assert len(_transcript(tmp_path)) == 2


def test_edited_task_definition_refuses_before_scoring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _ = _setup(tmp_path, {"1": "TAMPER"}, steps=1)
    # Tampering alone leaves the artifact unchanged, so also edit the
    # artifact to force a scoring attempt in the same step.
    monkeypatch.setenv("TAMPER_TARGET", str(tmp_path / "fixtures" / "T01.json"))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"1": "TAMPER"}), encoding="utf-8")
    proposer = tmp_path / "scripts" / "proposer.py"
    proposer.write_text(
        proposer.read_text(encoding="utf-8")
        + "\njson.dump({t: True for t in json.load(open(artifact))}, open(artifact, 'w'))\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert not list((tmp_path / "state" / "runs").glob("candidate-*"))


def test_state_dir_is_private_and_holds_the_ledger(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {"1": _all_true()}, steps=1)
    assert ec.main(["run", "--config", str(config)]) == 0
    state = tmp_path / "state"
    if sys.platform != "win32":
        assert state.stat().st_mode & 0o077 == 0
    assert any((state / "ledger").rglob("*"))


def test_reused_state_dir_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    assert ec.main(["run", "--config", str(config)]) == 0
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_policy_lists_state_and_task_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    assert ec.main(["policy", "--config", str(config)]) == 0
    policy = json.loads(capsys.readouterr().out)
    assert policy["deny_read_write"] == [
        str(tmp_path / "state"),
        str(config.resolve()),
        str(tmp_path / "fixtures"),
        str(sys.modules["_controller_lock"].artifact_lock_path(tmp_path / "artifact.json")),
    ]
    # The whole eval directory, so a planted sibling module is covered too.
    assert policy["deny_write"] == [str(_SCRIPT.parent)]


def test_scorer_failure_is_external(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["scorer"] = [sys.executable, "-c", "raise SystemExit(4)"]
    config.write_text(json.dumps(data), encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL


def test_proposer_failure_is_external_and_restores_nothing_ungated(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    before = artifact.read_text(encoding="utf-8")
    data = json.loads(config.read_text(encoding="utf-8"))
    data["proposer"] = [sys.executable, "-c", "raise SystemExit(5)"]
    config.write_text(json.dumps(data), encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert artifact.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("kind", "prompt"),
        ("max_consultations", 0),
        ("max_consultations", True),
        ("steps", -1),
        ("scorer", []),
        ("proposer", "not-a-list"),
        ("opt_task_files", "no-placeholder.json"),
        ("max_p", "0.05"),
        ("max_p", 1.1),
        ("max_p", -0.1),
        ("inputs", ["/elsewhere/report.xml"]),
        ("sel_ratio", 0.4),
        ("deny_paths", []),
        ("timeout_seconds", 0),
        ("proposer_env", None),
        ("scorer_exit_codes", []),
        ("scorer_exit_codes", [True]),
    ],
)
def test_bad_config_is_refused(tmp_path: Path, key: str, value: object) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    data = json.loads(config.read_text(encoding="utf-8"))
    data[key] = value
    config.write_text(json.dumps(data), encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_workspace_inside_state_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["workspace_dir"] = str(tmp_path / "state" / "ws")
    config.write_text(json.dumps(data), encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_deny_path_covering_the_artifact_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["deny_paths"] = [str(tmp_path)]
    config.write_text(json.dumps(data), encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def _edit_config(config: Path, **changes: object) -> None:
    data = json.loads(config.read_text(encoding="utf-8"))
    data.update(changes)
    config.write_text(json.dumps(data), encoding="utf-8")


def test_proposer_that_edits_then_fails_leaves_the_incumbent(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    before = artifact.read_text(encoding="utf-8")
    script = (
        "import json, sys; json.dump({'T01': True}, open(sys.argv[1], 'w')); raise SystemExit(5)"
    )
    _edit_config(config, proposer=[sys.executable, "-c", script, "{artifact}"])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert artifact.read_text(encoding="utf-8") == before


def test_artifact_changed_during_scoring_is_refused(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=1)
    before = artifact.read_text(encoding="utf-8")
    scorer = tmp_path / "scripts" / "scorer.py"
    # On the candidate run only, rewrite the artifact after scoring it, the way
    # a proposer's leftover child process could.
    scorer.write_text(
        scorer.read_text(encoding="utf-8")
        + "\nif 'candidate' in out:\n    open(artifact, 'w').write(json.dumps({'T01': False}))\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert artifact.read_text(encoding="utf-8") == before


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_planted_feedback_symlink_is_not_followed(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=2)
    outside = tmp_path / "outside.txt"
    outside.write_text("untouched", encoding="utf-8")
    plant = (
        "import os, sys; p = os.path.join(sys.argv[1], 'feedback.json'); "
        "os.remove(p); os.symlink(sys.argv[2], p)"
    )
    _edit_config(config, proposer=[sys.executable, "-c", plant, "{workspace}", str(outside)])
    # Step 1 plants the link; the controller's step 2 write must replace it
    # rather than write through it.
    assert ec.main(["run", "--config", str(config)]) == 0
    assert outside.read_text(encoding="utf-8") == "untouched"


def test_no_change_then_change_gates_the_second_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _setup(tmp_path, {"2": _all_true()}, steps=2)
    assert ec.main(["run", "--config", str(config)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["consultations_spent"] == 1
    assert summary["accepts"] == 1


def test_collect_moves_scorer_output_into_state(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    loose = tmp_path / "loose"
    scorer = tmp_path / "scripts" / "scorer.py"
    _edit_config(
        config,
        scorer=[sys.executable, str(scorer), "{artifact}", str(loose / "{run_id}.xml")],
        collect=[str(loose / "{run_id}.xml")],
        inputs=["{run_dir}/0"],
    )
    loose.mkdir()
    assert ec.main(["run", "--config", str(config)]) == 0
    assert list(loose.iterdir()) == []
    assert list((tmp_path / "state" / "runs").glob("incumbent-0-*/0"))


def test_missing_collected_output_is_external(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    _edit_config(config, collect=[str(tmp_path / "never-written.xml")])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL


def test_proposer_timeout_is_external(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    before = artifact.read_text(encoding="utf-8")
    _edit_config(
        config,
        timeout_seconds=1,
        proposer=[sys.executable, "-c", "import time; time.sleep(30)"],
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert artifact.read_text(encoding="utf-8") == before
    assert "proposer step 1 timed out" in _events(tmp_path)[-1]["error"]


def test_config_inside_workspace_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    moved = workspace / "config.json"
    moved.write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    assert ec.main(["run", "--config", str(moved)]) == ec.EXIT_CONFIG


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_artifact_swapped_for_symlink_cannot_redirect_the_restore(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    denied = tmp_path / "fixtures" / "T01.json"
    before = denied.read_text(encoding="utf-8")
    swap = "import os, sys; os.remove(sys.argv[1]); os.symlink(sys.argv[2], sys.argv[1])"
    _edit_config(config, proposer=[sys.executable, "-c", swap, "{artifact}", str(denied)])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert denied.read_text(encoding="utf-8") == before
    assert not artifact.is_symlink()


def test_denied_file_edited_on_a_no_change_step_stops_the_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _ = _setup(tmp_path, {"1": "TAMPER"}, steps=2)
    monkeypatch.setenv("TAMPER_TARGET", str(tmp_path / "fixtures" / "T02.json"))
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert len(_transcript(tmp_path)) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="setsid is POSIX only")
def test_escaped_grandchild_cannot_stretch_the_timeout(tmp_path: Path) -> None:
    import time

    config, _ = _setup(tmp_path, {}, steps=1)
    started_marker = tmp_path / "grandchild-started"
    escape = (
        "import os, subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], "
        "start_new_session=True); open(sys.argv[1], 'w').write(str(p.pid)); time.sleep(20)"
    )
    _edit_config(
        config,
        timeout_seconds=1,
        proposer=[sys.executable, "-c", escape, str(started_marker)],
    )
    started = time.monotonic()
    try:
        assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
        assert time.monotonic() - started < 10
        assert started_marker.exists()
        assert "proposer step 1 timed out" in _events(tmp_path)[-1]["error"]
    finally:
        # The grandchild left the group on purpose; stop it so the test
        # does not leave a sleeper behind.
        if started_marker.exists():
            with contextlib.suppress(ProcessLookupError, ValueError):
                os.kill(int(started_marker.read_text(encoding="utf-8")), signal.SIGKILL)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
def test_artifact_mode_survives_restore_and_accept(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=2)
    artifact.chmod(0o755)
    assert ec.main(["run", "--config", str(config)]) == 0
    assert artifact.stat().st_mode & 0o7777 == 0o755


def test_artifact_hard_linked_to_a_denied_file_is_refused(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    denied = tmp_path / "fixtures" / "T01.json"
    link = "import os, sys; os.remove(sys.argv[1]); os.link(sys.argv[2], sys.argv[1])"
    _edit_config(config, proposer=[sys.executable, "-c", link, "{artifact}", str(denied)])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert artifact.stat().st_nlink == 1


def test_summary_digest_is_the_file_on_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib

    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=1)
    assert ec.main(["run", "--config", str(config)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["artifact_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()


def _events(tmp_path: Path) -> list[dict[str, Any]]:
    lines = (tmp_path / "state" / "log.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _wrap_optimizer(
    monkeypatch: pytest.MonkeyPatch, seen: list[list[str]], gate: dict[str, Any] | None = None
) -> None:
    real = ec.optimizer

    def fake(args: list[str], timeout: int, env: Any = None) -> tuple[int, dict[str, Any]]:
        seen.append(list(args))
        if gate is not None and args[0] == "gate":
            return 1, gate
        return real(args, timeout, env)

    monkeypatch.setattr(ec, "optimizer", fake)


def test_gate_refusal_stops_the_run_and_spends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=2)
    before = artifact.read_text(encoding="utf-8")
    refusal = {"decision": "REJECT", "compared": False, "consultations": 0}
    _wrap_optimizer(monkeypatch, [], gate=refusal)
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert artifact.read_text(encoding="utf-8") == before
    assert _events(tmp_path)[-1]["event"] == "abort"
    assert len(_transcript(tmp_path)) == 1


def test_max_p_reaches_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _ = _setup(tmp_path, {"1": _all_true()}, steps=1)
    _edit_config(config, max_p=0.5)
    seen: list[list[str]] = []
    _wrap_optimizer(monkeypatch, seen)
    assert ec.main(["run", "--config", str(config)]) == 0
    gate = next(args for args in seen if args[0] == "gate")
    assert gate[gate.index("--max-p") + 1] == "0.5"


def test_scorer_that_edits_controller_state_is_refused(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=1)
    before = artifact.read_text(encoding="utf-8")
    scorer = tmp_path / "scripts" / "scorer.py"
    tasks = tmp_path / "state" / "tasks.txt"
    scorer.write_text(
        scorer.read_text(encoding="utf-8")
        + f"\nif 'candidate' in out:\n    open({str(tasks)!r}, 'a').write('x')\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert artifact.read_text(encoding="utf-8") == before
    assert not any(e["event"] == "gate" for e in _events(tmp_path))


def test_workspace_is_emptied_between_steps(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=2)
    note = "import os, sys; open(os.path.join(sys.argv[1], 'note.txt'), 'w').write('x')"
    record = (
        "import json, os, sys; seen = sorted(os.listdir(sys.argv[1])); "
        "open(sys.argv[2], 'a').write(json.dumps(seen) + '\\n'); " + note.split("; ", 1)[1]
    )
    log = tmp_path / "listing.jsonl"
    _edit_config(config, proposer=[sys.executable, "-c", record, "{workspace}", str(log)])
    assert ec.main(["run", "--config", str(config)]) == 0
    listings = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert listings[1] == ["feedback.json", "tasks"]


def test_trusted_path_edit_stops_the_loop(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=2)
    trusted = tmp_path / "trusted.py"
    trusted.write_text("x = 1\n", encoding="utf-8")
    edit = "import sys; open(sys.argv[1], 'a').write('y = 2\\n')"
    _edit_config(
        config,
        trusted_paths=[str(trusted)],
        proposer=[sys.executable, "-c", edit, str(trusted)],
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_proposer_env_drops_the_ledger_variable_and_honors_an_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    monkeypatch.setenv("EVAL_LEDGER_DIR", "/should/not/pass")
    monkeypatch.setenv("SECRET_TOKEN", "hidden")
    monkeypatch.setenv("ALLOWED_VAR", "kept")
    dump = "import json, os, sys; json.dump(dict(os.environ), open(sys.argv[1], 'w'))"
    out = tmp_path / "env.json"
    _edit_config(
        config, proposer_env=["ALLOWED_VAR"], proposer=[sys.executable, "-c", dump, str(out)]
    )
    assert ec.main(["run", "--config", str(config)]) == 0
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env.get("ALLOWED_VAR") == "kept"
    assert "SECRET_TOKEN" not in env
    assert "EVAL_LEDGER_DIR" not in env


def test_artifact_replaced_by_a_directory_is_refused_and_restored(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    before = artifact.read_text(encoding="utf-8")
    swap = "import os, sys; os.remove(sys.argv[1]); os.mkdir(sys.argv[1])"
    _edit_config(config, proposer=[sys.executable, "-c", swap, "{artifact}"])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert artifact.is_file()
    assert artifact.read_text(encoding="utf-8") == before


def test_missing_opt_task_file_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    _edit_config(config, opt_task_files=str(tmp_path / "nowhere" / "{task_name}.json"))
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_deny_path_containing_state_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["state_dir"] = str(tmp_path / "fixtures" / "state")
    config.write_text(json.dumps(data), encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_sigterm_raises_outside_a_restore(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    controller = ec.Controller(ec.load_config(config))
    with pytest.raises(ec.ControllerError) as caught:
        controller.on_sigterm(15, None)
    assert caught.value.code == ec.EXIT_EXTERNAL


def test_sigterm_during_a_restore_waits_for_the_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    controller = ec.Controller(ec.load_config(config))
    controller.incumbent_bytes = b"incumbent"
    controller.mode = 0o644
    real = ec.write_artifact

    def interrupted(path: Path, data: bytes, mode: int) -> None:
        controller.on_sigterm(15, None)  # arrives mid-restore: must not raise
        real(path, data, mode)

    monkeypatch.setattr(ec, "write_artifact", interrupted)
    with pytest.raises(ec.ControllerError):
        controller._restore()
    assert artifact.read_bytes() == b"incumbent"


def test_failure_detail_goes_to_the_log_not_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    noisy = "import sys; sys.stderr.write('PRIVATE-DETAIL'); raise SystemExit(4)"
    _edit_config(config, proposer=[sys.executable, "-c", noisy])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert "PRIVATE-DETAIL" not in capsys.readouterr().err
    assert "PRIVATE-DETAIL" in _events(tmp_path)[-1]["detail"]


def test_artifact_inside_the_workspace_is_refused(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    inside = tmp_path / "workspace" / "artifact.json"
    inside.parent.mkdir()
    inside.write_text(artifact.read_text(encoding="utf-8"), encoding="utf-8")
    _edit_config(config, artifact=str(inside))
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert inside.is_file()


def test_non_empty_workspace_is_refused_and_left_alone(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    keep = tmp_path / "workspace" / "keep.txt"
    keep.parent.mkdir()
    keep.write_text("mine", encoding="utf-8")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert keep.read_text(encoding="utf-8") == "mine"
    assert not (tmp_path / "state" / "log.jsonl").exists()


def test_new_file_in_a_trusted_directory_stops_the_loop(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=2)
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    (trusted / "mod.py").write_text("x = 1\n", encoding="utf-8")
    plant = "import os, sys; os.mkdir(os.path.join(sys.argv[1], 'json'))"
    _edit_config(
        config, trusted_paths=[str(trusted)], proposer=[sys.executable, "-c", plant, str(trusted)]
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_gate_runs_with_bytecode_cache_under_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _ = _setup(tmp_path, {"1": _all_true()}, steps=1)
    envs: list[Any] = []
    real = ec.optimizer

    def fake(args: list[str], timeout: int, env: Any = None) -> tuple[int, dict[str, Any]]:
        envs.append(env)
        return real(args, timeout, env)

    monkeypatch.setattr(ec, "optimizer", fake)
    assert ec.main(["run", "--config", str(config)]) == 0
    prefixes = [Path(env["PYTHONPYCACHEPREFIX"]) for env in envs]
    # One fresh private directory per call, under state, gone once it returns,
    # so a cache planted between calls is never read.
    assert len(prefixes) >= 3 and len(set(prefixes)) == len(prefixes)
    assert all(prefix.parent == tmp_path / "state" for prefix in prefixes)
    assert not any(prefix.exists() for prefix in prefixes)


@pytest.mark.parametrize("task", ["suite::../secret", "suite::a/b", "suite::..", "a\\b"])
def test_task_file_refuses_ids_that_leave_the_directory(task: str) -> None:
    with pytest.raises(ec.ControllerError):
        ec.task_file("/fixtures/{task_name}.json", task)


def test_task_file_fills_a_plain_id() -> None:
    assert ec.task_file("/fixtures/{task_name}.json", "suite::T01") == "/fixtures/T01.json"


def test_scorer_runs_with_its_bytecode_cache_in_its_run_dir(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    scorer = tmp_path / "scripts" / "scorer.py"
    scorer.write_text(
        scorer.read_text(encoding="utf-8")
        + "\nimport os\nopen(out + '.env', 'w').write(os.environ.get('PYTHONPYCACHEPREFIX', ''))\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == 0
    recorded = next((tmp_path / "state" / "runs").glob("incumbent-0-*/junit.xml.env"))
    assert recorded.read_text(encoding="utf-8") == str(recorded.parent / "pycache")


def test_scorer_exit_one_is_refused_by_default(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    scorer = tmp_path / "scripts" / "scorer.py"
    scorer.write_text(
        scorer.read_text(encoding="utf-8") + "\nraise SystemExit(1)\n", encoding="utf-8"
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL


def test_scorer_exit_codes_accept_a_run_with_failing_tests(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {"1": _all_true()}, steps=1)
    scorer = tmp_path / "scripts" / "scorer.py"
    # pytest exits 1 when any test failed; the JUnit report is still complete.
    scorer.write_text(
        scorer.read_text(encoding="utf-8")
        + "\nraise SystemExit(0 if all(state.values()) else 1)\n",
        encoding="utf-8",
    )
    _edit_config(config, scorer_exit_codes=[0, 1])
    assert ec.main(["run", "--config", str(config)]) == 0
    assert any(e["event"] == "gate" for e in _events(tmp_path))


def test_failed_scorer_output_is_moved_out_of_the_checkout(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    loose = tmp_path / "loose" / "report.xml"
    loose.parent.mkdir()
    write = f"open({str(loose)!r}, 'w').write('held-out'); raise SystemExit(4)"
    _edit_config(config, scorer=[sys.executable, "-c", write], collect=[str(loose)])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert not loose.exists()
    assert list((tmp_path / "state" / "runs").glob("incumbent-0-*/0"))


def test_baseline_scorer_that_edits_the_artifact_is_refused(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    before = artifact.read_text(encoding="utf-8")
    scorer = tmp_path / "scripts" / "scorer.py"
    scorer.write_text(
        scorer.read_text(encoding="utf-8") + "\nopen(artifact, 'a').write(' ')\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert not (tmp_path / "state" / "split.json").exists()
    assert artifact.read_text(encoding="utf-8") == before


def test_baseline_scorer_that_edits_a_task_file_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    scorer = tmp_path / "scripts" / "scorer.py"
    fixture = tmp_path / "fixtures" / "T01.json"
    scorer.write_text(
        scorer.read_text(encoding="utf-8") + f"\nopen({str(fixture)!r}, 'a').write(' ')\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert not (tmp_path / "state" / "split.json").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_task_file_that_is_a_link_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    fixtures = tmp_path / "fixtures"
    for task in TASKS:
        path = fixtures / f"{task}.json"
        path.unlink()
        path.symlink_to(tmp_path / "artifact.json")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_task_files_sharing_a_name_are_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    fixtures = tmp_path / "fixtures"
    for task in TASKS:
        (fixtures / task).mkdir()
        (fixtures / task / "fixture.json").write_text("{}", encoding="utf-8")
    _edit_config(config, opt_task_files=str(fixtures / "{task_name}" / "fixture.json"))
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_launcher_artifact_symlink_resolves_to_its_target(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=1)
    link = tmp_path / "artifact-link.json"
    link.symlink_to(artifact)
    _edit_config(config, artifact=str(link))
    assert ec.main(["run", "--config", str(config)]) == 0
    assert link.is_symlink()
    assert json.loads(artifact.read_text(encoding="utf-8")) == _all_true()


def test_state_dir_inside_trusted_code_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    _edit_config(config, trusted_paths=[str(trusted)], state_dir=str(trusted / "state"))
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_gate_event_records_the_candidate_digest(tmp_path: Path) -> None:
    import hashlib

    config, _ = _setup(tmp_path, {"1": _all_true()}, steps=1)
    assert ec.main(["run", "--config", str(config)]) == 0
    gate = next(e for e in _events(tmp_path) if e["event"] == "gate")
    expected = hashlib.sha256(json.dumps(_all_true()).encode()).hexdigest()
    assert gate["candidate_sha256"] == expected


def test_artifact_inside_state_is_refused(tmp_path: Path) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    inside = tmp_path / "state" / "artifact.json"
    inside.parent.mkdir()
    inside.write_text(artifact.read_text(encoding="utf-8"), encoding="utf-8")
    _edit_config(config, artifact=str(inside))
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_tamper_refusal_still_collects_the_scorer_report(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    scorer = tmp_path / "scripts" / "scorer.py"
    loose = tmp_path / "loose"
    loose.mkdir()
    report = loose / "copy.xml"
    scorer.write_text(
        scorer.read_text(encoding="utf-8")
        + f"\nimport shutil\nshutil.copy(out, {str(report)!r})\nopen(artifact, 'a').write(' ')\n",
        encoding="utf-8",
    )
    _edit_config(config, collect=[str(report)])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert not report.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_symlinked_deny_directory_is_digested_by_content(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    link = tmp_path / "fixtures-link"
    link.symlink_to(tmp_path / "fixtures", target_is_directory=True)
    scorer = tmp_path / "scripts" / "scorer.py"
    fixture = tmp_path / "fixtures" / "T01.json"
    scorer.write_text(
        scorer.read_text(encoding="utf-8") + f"\nopen({str(fixture)!r}, 'a').write(' ')\n",
        encoding="utf-8",
    )
    _edit_config(config, deny_paths=[str(link)])
    assert ec.load_config(config).deny_paths == [(tmp_path / "fixtures").resolve()]
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_artifact_inside_the_eval_directory_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    _edit_config(config, artifact=str(_SCRIPT))
    with pytest.raises(ec.ControllerError):
        ec.load_config(config)


@pytest.mark.skipif(sys.platform == "win32", reason="setsid is POSIX only")
def test_optimizer_timeout_is_bounded_and_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules["_controller_io"], "OPTIMIZER", slow)
    started = time.monotonic()
    with pytest.raises(ec.ControllerError) as caught:
        ec.optimizer(["gate"], 1)
    assert caught.value.code == ec.EXIT_EXTERNAL
    assert time.monotonic() - started < 10


def test_artifact_that_is_the_config_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    _edit_config(config, artifact=str(config))
    with pytest.raises(ec.ControllerError):
        ec.load_config(config)


def test_planted_results_file_is_not_written_through(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    scorer = tmp_path / "scripts" / "scorer.py"
    scorer.write_text(
        scorer.read_text(encoding="utf-8")
        + "\nimport os\nopen(os.path.join(os.path.dirname(out), 'results.json'), 'w').write('x')\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_every_collect_output_is_moved_even_when_one_is_missing(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    loose = tmp_path / "loose"
    loose.mkdir()
    present = loose / "second.xml"
    write = f"open({str(present)!r}, 'w').write('held-out')"
    _edit_config(
        config,
        scorer=[sys.executable, "-c", write],
        collect=[str(loose / "first.xml"), str(present)],
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert not present.exists()


def test_baseline_os_error_still_restores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, artifact = _setup(tmp_path, {}, steps=1)
    before = artifact.read_bytes()

    def broken(self: Any, label: str, expected: bytes) -> Path:
        artifact.write_bytes(b"changed by scorer")
        raise OSError("disk went away")

    monkeypatch.setattr(ec.Controller, "score", broken)
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert artifact.read_bytes() == before


@pytest.mark.skipif(
    sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs POSIX permissions and a non-root user",
)
def test_unreadable_protected_directory_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    hidden = tmp_path / "fixtures" / "hidden"
    hidden.mkdir()
    hidden.chmod(0)
    try:
        assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    finally:
        hidden.chmod(0o700)


def test_windows_proposer_env_keeps_startup_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    io = sys.modules["_controller_io"]
    monkeypatch.setattr(io.os, "name", "nt")
    monkeypatch.setattr(
        io.os,
        "environ",
        {"Path": "C:/bin", "SystemRoot": "C:/Windows", "SECRET": "x", "EVAL_LEDGER_DIR": "y"},
    )
    config = type("C", (), {"proposer_env": []})()
    env = io.proposer_env(config)
    assert env == {"Path": "C:/bin", "SystemRoot": "C:/Windows"}


def test_oversized_optimizer_reply_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    io = sys.modules["_controller_io"]
    big = tmp_path / "big.py"
    big.write_text("print('{' + ' ' * 5000 + '}')\n", encoding="utf-8")
    monkeypatch.setattr(io, "OPTIMIZER", big)
    monkeypatch.setattr(io, "_MAX_JSON_BYTES", 1000)
    with pytest.raises(ec.ControllerError):
        ec.optimizer(["gate"], 30)


def test_policy_names_collect_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    _edit_config(config, collect=["evals/x/reports/{run_id}"])
    assert ec.main(["policy", "--config", str(config)]) == 0
    assert json.loads(capsys.readouterr().out)["deny_read_write_collect"] == [
        "evals/x/reports/{run_id}"
    ]


def test_stale_report_at_a_collect_path_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    stale = tmp_path / "loose" / "report.xml"
    stale.parent.mkdir()
    stale.write_text("from an earlier run", encoding="utf-8")
    _edit_config(config, collect=[str(stale)])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert stale.read_text(encoding="utf-8") == "from an earlier run"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_task_path_through_a_linked_directory_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    real = tmp_path / "real-tasks"
    real.mkdir()
    for task in TASKS:
        (real / f"{task}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "linked").symlink_to(real, target_is_directory=True)
    _edit_config(config, opt_task_files=str(tmp_path / "linked" / "{task_name}.json"))
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


@pytest.mark.skipif(
    sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs POSIX permissions and a non-root user",
)
def test_protected_root_that_cannot_be_inspected_is_refused(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    locked = tmp_path / "locked"
    (locked / "inner").mkdir(parents=True)
    _edit_config(config, trusted_paths=[str(locked / "inner")])
    locked.chmod(0)
    try:
        assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    finally:
        locked.chmod(0o700)


def test_cache_directory_in_a_deny_path_is_digested(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    cache = tmp_path / "fixtures" / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_text("a", encoding="utf-8")
    scorer = tmp_path / "scripts" / "scorer.py"
    scorer.write_text(
        scorer.read_text(encoding="utf-8") + f"\nopen({str(cache / 'x.pyc')!r}, 'a').write('b')\n",
        encoding="utf-8",
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


def test_run_installs_and_restores_a_sigint_handler(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    before = signal.getsignal(signal.SIGINT)
    seen: list[object] = []
    controller = ec.Controller(ec.load_config(config))
    original = controller._run

    def spy() -> dict[str, Any]:
        seen.append(signal.getsignal(signal.SIGINT))
        return original()

    controller._run = spy
    controller.run()
    assert seen == [controller.on_sigterm]
    assert signal.getsignal(signal.SIGINT) is before


@pytest.mark.parametrize("template", ["{run_dir}/../escape.xml", "{run_dir}sibling/x.xml"])
def test_input_that_escapes_the_run_directory_is_refused(tmp_path: Path, template: str) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    _edit_config(config, inputs=[template])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


# Claim from an imported review learning: the collector (then `_collect`, now
# `collect_all`) follows a planted symlink
# and reads or copies bytes from outside the results tree. These pin the
# observed behavior: the link itself moves, its target is never read, and
# extract refuses an input that resolves outside the run directory.
_PLANT_LEAF = textwrap.dedent(
    """
    import os, sys
    os.symlink(sys.argv[2], sys.argv[1])
    """
)

_PLANT_NESTED = textwrap.dedent(
    """
    import os, sys
    os.makedirs(sys.argv[1])
    os.symlink(sys.argv[2], os.path.join(sys.argv[1], "junit.xml"))
    """
)


def _outside_report(tmp_path: Path) -> Path:
    outside = tmp_path / "outside" / "secret.xml"
    outside.parent.mkdir()
    outside.write_text(
        "<testsuites><testsuite><testcase classname='suite' name='T01'/></testsuite></testsuites>",
        encoding="utf-8",
    )
    return outside


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_collected_leaf_symlink_moves_the_link_and_is_not_read(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    outside = _outside_report(tmp_path)
    before = outside.read_bytes()
    loose = tmp_path / "loose"
    loose.mkdir()
    target = str(loose / "{run_id}.xml")
    _edit_config(
        config,
        scorer=[sys.executable, "-c", _PLANT_LEAF, target, str(outside)],
        collect=[target],
        inputs=["{run_dir}/0"],
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    (moved,) = (tmp_path / "state" / "runs").glob("incumbent-0-*/0")
    assert moved.is_symlink()
    assert outside.read_bytes() == before
    assert not (tmp_path / "state" / "split.json").exists()
    assert "outside the run directory" in _events(tmp_path)[-1]["error"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_collected_tree_with_a_nested_symlink_is_not_read(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    outside = _outside_report(tmp_path)
    before = outside.read_bytes()
    loose = tmp_path / "loose"
    loose.mkdir()
    target = str(loose / "{run_id}")
    _edit_config(
        config,
        scorer=[sys.executable, "-c", _PLANT_NESTED, target, str(outside)],
        collect=[target],
        inputs=["{run_dir}/0/junit.xml"],
    )
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    (moved,) = (tmp_path / "state" / "runs").glob("incumbent-0-*/0")
    assert moved.is_dir() and not moved.is_symlink()
    assert (moved / "junit.xml").is_symlink()
    assert outside.read_bytes() == before
    assert not (tmp_path / "state" / "split.json").exists()
    assert "outside the run directory" in _events(tmp_path)[-1]["error"]


# The scorer is told `{run_dir}`, so it can plant the collect destination
# itself before writing its report. `link` points `{run_dir}/0` at a directory
# outside state; `dir` makes it a real directory. A nonzero `exit` makes the
# scorer fail after planting, which takes the collect-on-failure path.
_PLANT_DESTINATION = textwrap.dedent(
    """
    import os, runpy, sys
    mode, run_dir, outside, exit_code = sys.argv[1:5]
    destination = os.path.join(run_dir, "0")
    if mode == "link":
        os.symlink(outside, destination)
    else:
        os.mkdir(destination)
    sys.argv = sys.argv[5:]
    runpy.run_path(sys.argv[0], run_name="__main__")
    sys.exit(int(exit_code))
    """
)


def _plant_destination(tmp_path: Path, mode: str, exit_code: int = 0) -> tuple[Path, Path, Path]:
    config, _ = _setup(tmp_path, {}, steps=1)
    outside = tmp_path / "outside"
    outside.mkdir()
    loose = tmp_path / "loose"
    loose.mkdir()
    report = str(loose / "{run_id}.xml")
    scorer = tmp_path / "scripts" / "scorer.py"
    plant = [sys.executable, "-c", _PLANT_DESTINATION, mode, "{run_dir}", str(outside)]
    _edit_config(
        config,
        scorer=[*plant, str(exit_code), str(scorer), "{artifact}", report],
        collect=[report],
        inputs=["{run_dir}/0"],
    )
    return config, outside, loose


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_collect_does_not_move_a_report_through_a_planted_destination_link(
    tmp_path: Path,
) -> None:
    config, outside, loose = _plant_destination(tmp_path, "link")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert list(outside.iterdir()) == []
    # The report still leaves the checkout: it lands inside state.
    assert list(loose.iterdir()) == []
    (moved,) = (tmp_path / "state" / "runs").glob("incumbent-0-*/0")
    assert moved.is_file() and not moved.is_symlink()
    assert "existed before collection" in _events(tmp_path)[-1]["error"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_failed_scorer_cannot_move_its_report_through_a_destination_link(
    tmp_path: Path,
) -> None:
    config, outside, loose = _plant_destination(tmp_path, "link", exit_code=5)
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert list(outside.iterdir()) == []
    assert list(loose.iterdir()) == []


def test_real_directory_at_the_collect_destination_fails_the_run(tmp_path: Path) -> None:
    config, outside, _ = _plant_destination(tmp_path, "dir")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    assert list(outside.iterdir()) == []
    (planted,) = (tmp_path / "state" / "runs").glob("incumbent-0-*/0")
    assert planted.is_dir() and list(planted.iterdir()) == []
    assert "existed before collection" in _events(tmp_path)[-1]["error"]


# The first scorer to start claims `held` and waits for `release`; any later
# scorer runs straight through. That parks one controller mid-baseline, after
# its `split.json` check and before it writes the split.
_HOLD_FIRST = textwrap.dedent(
    """
    import os, runpy, sys, time
    held, release = sys.argv[1], sys.argv[2]
    try:
        os.close(os.open(held, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        pass
    else:
        deadline = time.monotonic() + 60
        while not os.path.exists(release) and time.monotonic() < deadline:
            time.sleep(0.05)
    sys.argv = sys.argv[3:]
    runpy.run_path(sys.argv[0], run_name="__main__")
    """
)


def _wait_for(path: Path, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)


def _hold_first_scorer(tmp_path: Path, config: Path) -> tuple[Path, Path]:
    held, release = tmp_path / "held", tmp_path / "release"
    scorer = tmp_path / "scripts" / "scorer.py"
    _edit_config(
        config,
        scorer=[
            sys.executable,
            "-c",
            _HOLD_FIRST,
            str(held),
            str(release),
            str(scorer),
            "{artifact}",
            "{run_dir}/junit.xml",
        ],
        timeout_seconds=120,
    )
    return held, release


def _race(tmp_path: Path, first_config: Path, second_config: Path) -> tuple[int, int]:
    """Park a first controller mid-baseline, run a second, then let the first finish."""
    held, release = _hold_first_scorer(tmp_path, first_config)
    first = subprocess.Popen(
        [sys.executable, str(_SCRIPT), "run", "--config", str(first_config)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for(held)
        second = ec.main(["run", "--config", str(second_config)])
    finally:
        release.touch()
        first.wait(timeout=120)
    return first.returncode, second


def test_second_controller_on_the_same_state_dir_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    first, second = _race(tmp_path, config, config)
    assert second == ec.EXIT_CONFIG
    assert "use a fresh state_dir" in capsys.readouterr().err
    assert first == ec.EXIT_OK


def test_second_controller_on_the_same_artifact_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, artifact = _setup(tmp_path, {"1": _all_true()}, steps=1)
    before = artifact.read_bytes()
    other = tmp_path / "other.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    data.update(state_dir=str(tmp_path / "state2"), workspace_dir=str(tmp_path / "workspace2"))
    other.write_text(json.dumps(data), encoding="utf-8")
    first, second = _race(tmp_path, config, other)
    assert second == ec.EXIT_CONFIG
    assert "one controller per artifact" in capsys.readouterr().err
    assert first == ec.EXIT_OK
    # The refused run never scored, so it left no state behind but its lock.
    assert not (tmp_path / "state2" / "split.json").exists()
    assert artifact.read_bytes() != before


def test_reused_state_dir_still_names_the_old_session_not_the_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    assert ec.main(["run", "--config", str(config)]) == 0
    capsys.readouterr()
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    err = capsys.readouterr().err
    assert "already holds a session" in err
    assert "another controller" not in err


# The scorer is told `{run_dir}`. These plant something in or around it before
# running the real scorer, as candidate code inside a hook scorer could.
_PLANT_AROUND_RUN = textwrap.dedent(
    """
    import os, runpy, shutil, sys
    mode, run_dir, outside = sys.argv[1:4]
    runs = os.path.dirname(run_dir)
    state = os.path.dirname(runs)
    if mode == "run_dir":
        shutil.rmtree(run_dir)
        os.symlink(outside, run_dir)
    elif mode == "runs":
        os.rename(runs, os.path.join(outside, "moved-runs"))
        os.symlink(outside, runs)
        os.mkdir(run_dir)
    elif mode == "log_link":
        os.symlink(os.path.join(outside, "victim.txt"), os.path.join(state, "log.jsonl"))
    elif mode == "log_fifo":
        os.mkfifo(os.path.join(state, "log.jsonl"))
    sys.argv = sys.argv[4:]
    runpy.run_path(sys.argv[0], run_name="__main__")
    """
)


def _plant_around_run(tmp_path: Path, mode: str, *, collect: bool = False) -> tuple[Path, Path]:
    config, _ = _setup(tmp_path, {}, steps=1)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("keep", encoding="utf-8")
    scorer = tmp_path / "scripts" / "scorer.py"
    plant = [sys.executable, "-c", _PLANT_AROUND_RUN, mode, "{run_dir}", str(outside)]
    if collect:
        loose = tmp_path / "loose"
        loose.mkdir()
        report = str(loose / "{run_id}.xml")
        changes: dict[str, Any] = {"collect": [report], "inputs": ["{run_dir}/0"]}
    else:
        report = "{run_dir}/junit.xml"
        changes = {}
    _edit_config(config, scorer=[*plant, str(scorer), "{artifact}", report], **changes)
    return config, outside


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
@pytest.mark.parametrize("collect", [False, True])
def test_run_dir_swapped_for_a_link_is_refused_before_anything_lands_outside(
    tmp_path: Path, collect: bool
) -> None:
    config, outside = _plant_around_run(tmp_path, "run_dir", collect=collect)
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    # The scorer's own report and bytecode cache may be there; nothing the
    # controller wrote is.
    scorer_wrote = {"junit.xml", "pycache"}
    assert [p.name for p in outside.iterdir() if p.name not in scorer_wrote] == ["victim.txt"]
    if collect:
        _assert_report_quarantined(tmp_path)
    else:
        # Nothing to collect, so no quarantine is made.
        assert not list((tmp_path / "state").glob("quarantine-*"))


def _assert_report_quarantined(tmp_path: Path) -> None:
    # The report left the checkout for a fresh directory in state.
    assert list((tmp_path / "loose").iterdir()) == []
    (quarantine,) = (tmp_path / "state").glob("quarantine-incumbent-*")
    assert [p.name for p in quarantine.iterdir()] == ["0"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_runs_directory_swapped_for_a_link_is_refused(tmp_path: Path) -> None:
    config, outside = _plant_around_run(tmp_path, "runs", collect=True)
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    planted = outside / next(p.name for p in outside.iterdir() if p.name.startswith("incumbent"))
    assert [p.name for p in planted.iterdir() if p.name != "pycache"] == []
    _assert_report_quarantined(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_planted_quarantine_names_cannot_capture_the_report(tmp_path: Path) -> None:
    # The scorer knows `run_id`, so it can plant the old fixed name and the
    # bare prefix. Neither is where the report goes.
    config, outside = _plant_around_run(tmp_path, "run_dir", collect=True)
    state = tmp_path / "state"
    real = sys.modules["_controller_io"].collect_or_quarantine
    planted: list[Path] = []

    def plant_first(
        templates: list[str], values: dict[str, str], run_dir: Path, base: Path, prefix: str
    ) -> tuple[Path, list[str]]:
        for name in (f"quarantine-{values['run_id']}", prefix):
            (base / name).symlink_to(outside)
            planted.append(base / name)
        result: tuple[Path, list[str]] = real(templates, values, run_dir, base, prefix)
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ec, "collect_or_quarantine", plant_first)
        assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert [p.name for p in outside.iterdir() if p.name != "pycache"] == ["victim.txt"]
    (quarantine,) = [p for p in state.glob("quarantine-incumbent-*") if p not in planted]
    assert not quarantine.is_symlink()
    assert [p.name for p in quarantine.iterdir()] == ["0"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_replaced_run_dir_error_names_the_quarantine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _plant_around_run(tmp_path, "run_dir", collect=True)
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    (quarantine,) = (tmp_path / "state").glob("quarantine-incumbent-*")
    assert f"reports moved to {quarantine}" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_replaced_run_dir_error_names_the_quarantine_and_the_missing_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _plant_around_run(tmp_path, "run_dir", collect=True)
    missing = str(tmp_path / "loose" / "{run_id}.missing")
    data = json.loads(config.read_text(encoding="utf-8"))
    _edit_config(config, collect=[*data["collect"], missing])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    (quarantine,) = (tmp_path / "state").glob("quarantine-incumbent-*")
    err = capsys.readouterr().err
    assert f"reports moved to {quarantine}" in err
    assert ".missing" in err


def test_failed_quarantine_does_not_hide_the_scorer_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    _edit_config(config, scorer=[sys.executable, "-c", "raise SystemExit(9)"])

    def broken(*_args: object) -> tuple[Path, list[str]]:
        raise ec.ControllerError("quarantine broke", ec.EXIT_EXTERNAL)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ec, "collect_or_quarantine", broken)
        assert ec.main(["run", "--config", str(config)]) == ec.EXIT_EXTERNAL
    err = capsys.readouterr().err
    assert "exited 9" in err
    assert "quarantine broke" not in err


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_abort_record_is_written_while_the_locks_are_held(tmp_path: Path) -> None:
    config, _ = _plant_around_run(tmp_path, "run_dir")
    lock = sys.modules["_controller_lock"]
    real = ec.Controller._record
    held: list[bool] = []

    def probe(self: Any, event: dict[str, Any]) -> None:
        if event.get("event") == "abort":
            # flock conflicts across descriptors even in one process.
            try:
                with lock.state_lock(tmp_path / "state"):
                    held.append(False)
            except ec.ControllerError:
                held.append(True)
        real(self, event)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ec.Controller, "_record", probe)
        assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert held == [True]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_log_planted_as_a_link_is_never_written_through(tmp_path: Path) -> None:
    config, outside = _plant_around_run(tmp_path, "log_link")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert (outside / "victim.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX FIFOs")
@pytest.mark.timeout(60)
def test_log_planted_as_a_fifo_does_not_hang_the_controller(tmp_path: Path) -> None:
    config, _ = _plant_around_run(tmp_path, "log_fifo")
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_ledger_directory_swapped_for_a_link_stops_the_gate(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path, {}, steps=1)
    outside = tmp_path / "outside"
    plant = (
        "import json, os, sys; state, outside, artifact = sys.argv[1:4]; "
        "ledger = os.path.join(state, 'ledger'); os.rename(ledger, outside); "
        "os.symlink(outside, ledger); "
        "json.dump({f'T{n:02d}': True for n in range(1, 11)}, open(artifact, 'w'))"
    )
    state = str(tmp_path / "state")
    _edit_config(config, proposer=[sys.executable, "-c", plant, state, str(outside), "{artifact}"])
    assert ec.main(["run", "--config", str(config)]) == ec.EXIT_CONFIG
    assert "ledger directory was replaced" in _events(tmp_path)[-1]["error"]
    assert list(outside.iterdir()) == []
