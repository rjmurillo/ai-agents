#!/usr/bin/env python3
"""Trusted controller for the held-out-gated optimization loop (ADR-087 OR1).

`optimize-artifact.py` assumes a cooperating optimizer: the agent that edits
the artifact also runs `extract`, `split`, and `gate`, so held-out outcomes and
task definitions sit in files it can read. This controller inverts that. The
launcher runs the controller, and the controller runs the optimizing agent as
a child "proposer". The proposer never calls the optimizer rails. Each step its
workspace is emptied and then holds:

- `feedback.json`: the step, the artifact path, the optimize-group results of
  the current incumbent and their pass fraction, the consultations left, and
  `last_decision` (ACCEPT or REJECT after a gate, NO_CHANGE otherwise),
- copies of the optimize-group task files, when the config names them.

Everything else stays under the controller's state directory: the scorer's raw
output, every results file, the split with held-out membership, the
consultation ledger, the full gate payloads, and child output.

The boundary is real only when the launcher applies the rule `policy` prints:
deny the proposer read and write on `deny_read_write`, and deny it write on
`deny_write`. Python cannot stop a same-user process from opening a file. The
controller digests the denied and trusted paths before each scoring run and
after each step, and digests the state directory around each scoring run. It
stops on a change it did not make, so a write that slips past the sandbox in
those windows is caught, not scored.

When the scorer executes the artifact (the `hook` kind), the candidate's code
runs inside the scorer with the scorer's access. The controller detects it
tampering with earlier state; it cannot stop it forging its own results.

Subcommands:

- `policy --config C`: print the access rule the launcher must apply.
- `run --config C`: baseline the incumbent, then run the proposer loop.

Exit codes (ADR-035): 0 loop finished, 2 config or integrity refusal,
3 scorer, proposer, optimizer, or I/O failure.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import signal
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import FrameType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _controller_io import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    Config,
    ControllerError,
    clear_dir,
    fill,
    load_config,
    optimizer,
    proposer_env,
    read_artifact,
    resolve,
    run_child,
    task_file,
    tree_digest,
    trusted_code,
    write_artifact,
)

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "Controller",
    "ControllerError",
    "main",
    "task_file",
]

_DECISIONS = {0: "ACCEPT", 1: "REJECT"}


def access_rule(config: Config) -> dict[str, Any]:
    """The rule the launcher must apply to the proposer, as `policy` prints it."""
    return {
        "deny_read_write": [str(p) for p in (config.state_dir, config.config_path)]
        + [str(p) for p in config.deny_paths],
        "deny_write": [str(p) for p in trusted_code(config)],
        "proposer_workspace": str(config.workspace_dir),
        "proposer_may_write": [str(config.artifact)],
    }


class Controller:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state: Path = config.state_dir
        self.log: Path = self.state / "log.jsonl"
        self.session = uuid.uuid4().hex[:12]
        self.integrity = ""
        self.mode = 0o644
        self.incumbent = Path()
        self.incumbent_bytes = b""
        self.fingerprint = ""
        self.spent = 0
        self.accepts = 0
        self.last: str | None = None
        self.started = False

    def _record(self, event: Mapping[str, Any]) -> None:
        stamp = dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")
        line = {"ts": stamp, "session": self.session, **event}
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, sort_keys=True) + "\n")

    def _optimizer(
        self, args: list[str], extra: Mapping[str, str] | None = None
    ) -> tuple[int, dict[str, Any]]:
        # Bytecode caches live under state, so a cache planted in
        # `scripts/eval/__pycache__` is never read by the gate.
        env = {**os.environ, "PYTHONPYCACHEPREFIX": str(self.state / "pycache"), **(extra or {})}
        result: tuple[int, dict[str, Any]] = optimizer(args, self.config.timeout_seconds, env)
        return result

    def _protected(self) -> list[Path]:
        return [*self.config.deny_paths, *trusted_code(self.config)]

    def _check_integrity(self) -> None:
        if tree_digest(self._protected()) != self.integrity:
            raise ControllerError(
                "a denied task-definition path or trusted code changed during the loop; "
                "refusing to continue"
            )

    def _call(self, argv: list[str], label: str, env: Mapping[str, str] | None = None) -> float:
        values = {
            "artifact": str(self.config.artifact),
            "workspace": str(self.config.workspace_dir),
        }
        duration: float = run_child(
            [fill(part, values) for part in argv], label, self.config.timeout_seconds, env
        )
        return duration

    def score(self, label: str) -> Path:
        """Run the scorer, move its output into state, extract all results."""
        self._check_integrity()
        run_id = f"{label}-{uuid.uuid4().hex[:8]}"
        run_dir = self.state / "runs" / run_id
        run_dir.mkdir(parents=True)
        values = {"run_id": run_id, "run_dir": str(run_dir)}
        # The candidate's code may run inside the scorer. Everything already in
        # state must be exactly as the controller left it when the scorer ends.
        before = tree_digest([self.state], exclude=run_dir)
        # The scorer's bytecode cache goes inside its own run directory, so a
        # cache planted beside the scorer's code is never read and the state
        # digest above still excludes everything the scorer may write.
        scorer_env = {**os.environ, "PYTHONPYCACHEPREFIX": str(run_dir / "pycache")}
        duration = self._call(
            [fill(part, values) for part in self.config.scorer], f"scorer {label}", scorer_env
        )
        if tree_digest([self.state], exclude=run_dir) != before:
            raise ControllerError(f"controller state changed while {label} was scored")
        self._record({"event": "call", "label": f"scorer {label}", "duration_s": duration})
        for index, template in enumerate(self.config.collect):
            source = resolve(fill(template, values))
            if not source.exists():
                raise ControllerError(f"scorer output {source} was not produced", EXIT_EXTERNAL)
            shutil.move(str(source), str(run_dir / str(index)))
        inputs = [fill(item, values) for item in self.config.inputs]
        code, payload = self._optimizer(
            ["extract", "--kind", self.config.kind, "--input", *inputs, *self.config.extract_args]
        )
        if code != 0:
            raise ControllerError(f"extract refused the {label} scorer output", EXIT_EXTERNAL)
        results: Path = run_dir / "results.json"
        results.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return results

    def _publish(self, step: int) -> Path:
        """Empty the workspace, then write the step's feedback and task copies.

        Emptying it closes a channel: candidate code run by the scorer could
        otherwise leave held-out data there for the next proposer step. No
        controller write follows a link the proposer planted.
        """
        workspace = self.config.workspace_dir
        clear_dir(workspace)
        mapping = json.loads(self.incumbent.read_text(encoding="utf-8"))["results"]
        opt_ids = json.loads((self.state / "split.json").read_text(encoding="utf-8"))["opt"]
        opt = {task: mapping[task] for task in opt_ids if task in mapping}
        if self.config.opt_task_files:
            tasks_dir = workspace / "tasks"
            tasks_dir.mkdir()
            for task in opt:
                source = resolve(task_file(self.config.opt_task_files, task))
                if not source.is_file():
                    raise ControllerError(f"optimize-group task file {source} is missing")
                shutil.copy2(source, tasks_dir / source.name)
        passed = sum(1 for value in opt.values() if value)
        document = {
            "step": step,
            "artifact": str(self.config.artifact),
            "opt_results": opt,
            "opt_score": passed / len(opt) if opt else 0.0,
            "last_decision": self.last,
            "consultations_left": self.config.max_consultations - self.spent,
        }
        feedback: Path = workspace / "feedback.json"
        with feedback.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
        return feedback

    def _baseline(self) -> None:
        config = self.config
        if (self.state / "split.json").exists():
            raise ControllerError("state_dir already holds a session; use a fresh state_dir")
        workspace = config.workspace_dir
        if workspace.exists() and (workspace.is_symlink() or any(workspace.iterdir())):
            raise ControllerError(
                "workspace_dir must be absent or empty; the controller empties it every step"
            )
        self.started = True
        self.state.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state, 0o700)
        self.incumbent_bytes = read_artifact(config.artifact)
        self.mode = config.artifact.stat().st_mode & 0o7777
        self.integrity = tree_digest(self._protected())
        self.incumbent = self.score("incumbent-0")
        document = json.loads(self.incumbent.read_text(encoding="utf-8"))
        tasks = self.state / "tasks.txt"
        tasks.write_text("\n".join(sorted(document["results"])) + "\n", encoding="utf-8")
        args = ["split", "--tasks", str(tasks), "--seed", config.seed]
        args += ["--sel-ratio", config.sel_ratio, "--out", str(self.state / "split.json")]
        if document.get("corpus"):
            args += ["--corpus", document["corpus"]]
        code, split_doc = self._optimizer(args)
        if code != 0:
            raise ControllerError("split refused the incumbent's task inventory", EXIT_EXTERNAL)
        self.fingerprint = split_doc["fingerprint"]
        self._record({"event": "baseline", "results": str(self.incumbent), "split": split_doc})

    def _gate(self, step: int, candidate: Path) -> str:
        args = ["gate", "--incumbent", str(self.incumbent), "--candidate", str(candidate)]
        args += ["--split", str(self.state / "split.json")]
        args += ["--max-consultations", str(self.config.max_consultations)]
        args += ["--incumbent-fingerprint", self.fingerprint]
        if self.config.max_p is not None:
            args += ["--max-p", str(self.config.max_p)]
        code, verdict = self._optimizer(args, {"EVAL_LEDGER_DIR": str(self.state / "ledger")})
        self._record({"event": "gate", "step": step, "exit": code, "verdict": verdict})
        # Exit 1 is also how the gate refuses without comparing (split drift,
        # corpus mismatch, guard). Only a comparison is a decision; a refusal
        # spends nothing and teaches the proposer nothing, so the run stops.
        if code not in _DECISIONS or verdict.get("compared") is not True:
            raise ControllerError(
                f"gate refused at step {step}; see the controller log", EXIT_EXTERNAL
            )
        self.spent += 1
        return _DECISIONS[code]

    def _step(self, step: int) -> None:
        config = self.config
        feedback = self._publish(step)
        argv = [
            part.replace("{feedback}", str(feedback)).replace("{step}", str(step))
            for part in config.proposer
        ]
        try:
            duration = self._call(argv, f"proposer step {step}", proposer_env(config))
            self._record(
                {"event": "call", "label": f"proposer step {step}", "duration_s": duration}
            )
            candidate_bytes = read_artifact(config.artifact)
            if candidate_bytes == self.incumbent_bytes:
                self.last = "NO_CHANGE"
                self._record({"event": "no_change", "step": step})
                return
            candidate = self.score(f"candidate-{step}")
            if read_artifact(config.artifact) != candidate_bytes:
                raise ControllerError(
                    f"the artifact changed while step {step} was being scored; "
                    "refusing to gate bytes that were not the ones scored"
                )
        finally:
            # Every exit from the step restores the incumbent before the gate:
            # a failed proposer, a failed scorer, and a normal step. Only an
            # ACCEPT below writes the candidate back. The integrity check runs
            # here too, so a NO_CHANGE step that edited a denied file stops.
            write_artifact(config.artifact, self.incumbent_bytes, self.mode)
            self._check_integrity()
        self.last = self._gate(step, candidate)
        if self.last == "ACCEPT":
            self.accepts += 1
            self.incumbent = candidate
            self.incumbent_bytes = candidate_bytes
            write_artifact(config.artifact, self.incumbent_bytes, self.mode)

    def run(self) -> dict[str, Any]:
        previous = signal.signal(signal.SIGTERM, _terminated)
        try:
            return self._run()
        except ControllerError as exc:
            if self.started and self.log.parent.is_dir():
                self._record(
                    {"event": "abort", "code": exc.code, "error": str(exc), "detail": exc.detail}
                )
            raise
        finally:
            signal.signal(signal.SIGTERM, previous)

    def _run(self) -> dict[str, Any]:
        config = self.config
        if not config.artifact.is_file():
            raise ControllerError(f"artifact {config.artifact} does not exist")
        self._baseline()
        steps_run = 0
        for step in range(1, config.steps + 1):
            if self.spent >= config.max_consultations:
                break
            steps_run = step
            self._step(step)
        final = read_artifact(config.artifact)
        if final != self.incumbent_bytes:
            raise ControllerError(
                "the artifact changed after the controller's last write; "
                "the file on disk is not the incumbent this run selected"
            )
        summary = {
            "steps_run": steps_run,
            "accepts": self.accepts,
            "consultations_spent": self.spent,
            "last_decision": self.last,
            # Read from disk, not memory, so the summary describes the file
            # left behind rather than the bytes the controller meant to write.
            "artifact_sha256": hashlib.sha256(final).hexdigest(),
        }
        self._record({"event": "done", **summary})
        return summary


def _terminated(_signum: int, _frame: FrameType | None) -> None:
    # Raised, so the step's `finally` restores the incumbent and kills the
    # child's group before the process exits.
    raise ControllerError("controller received SIGTERM", EXIT_EXTERNAL)


def cmd_policy(args: argparse.Namespace) -> int:
    print(json.dumps(access_rule(load_config(args.config)), indent=2))
    return int(EXIT_OK)


def cmd_run(args: argparse.Namespace) -> int:
    summary = Controller(load_config(args.config)).run()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return int(EXIT_OK)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval_controller.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, text in (
        ("policy", cmd_policy, "print the access rule the launcher must apply"),
        ("run", cmd_run, "baseline the incumbent and run the proposer loop"),
    ):
        command = sub.add_parser(name, help=text)
        command.add_argument("--config", type=Path, required=True, help="launcher-owned JSON")
        command.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except ControllerError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return int(exc.code)
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return int(EXIT_EXTERNAL)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
