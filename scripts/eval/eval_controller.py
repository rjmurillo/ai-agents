#!/usr/bin/env python3
"""Trusted controller for the held-out-gated optimization loop (ADR-087 OR1).

`optimize-artifact.py` assumes a cooperating optimizer that runs `extract`,
`split`, and `gate` itself. This controller inverts that: the launcher runs
the controller, and the controller runs the optimizing agent as a child
"proposer". Each step the proposer's workspace is emptied and then holds
`feedback.json` (step, artifact path, optimize-group results and pass
fraction, consultations left, `last_decision`) and, optionally, copies of the
optimize-group task files. Everything else stays in the state directory.

The boundary holds only when the launcher applies the rule `policy` prints.
Python cannot stop a same-user process from opening a file, so the controller
digests the denied and trusted paths around each scoring run and step, and the
state directory around each scoring run, and stops on a change it did not make.
For the `hook` kind, candidate code runs inside the scorer; the controller
detects it tampering with earlier state, not it forging its own results.

Subcommands: `policy --config C` prints the access rule; `run --config C`
baselines the incumbent, then runs the proposer loop.

Exit codes (ADR-035): 0 loop finished, 2 config or integrity refusal,
3 scorer, proposer, optimizer, or I/O failure.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import signal
import sys
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import FrameType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _controller_config import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    Config,
    ControllerError,
    access_rule,
    load_config,
    resolve,
    trusted_code,
)
from _controller_io import (
    clear_dir,
    collect_or_quarantine,
    contained_inputs,
    fill,
    is_real_dir,
    optimizer,
    proposer_env,
    read_artifact,
    read_private,
    refuse_stale_reports,
    run_child,
    task_file,
    tree_digest,
    write_artifact,
    write_private,
)
from _controller_lock import artifact_lock, artifact_lock_path, state_lock

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "Controller",
    "ControllerError",
    "load_config",
    "main",
    "optimizer",
    "task_file",
    "write_artifact",
]

_DECISIONS = {0: "ACCEPT", 1: "REJECT"}


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
        self.restoring = False
        self.term_pending = False

    def _record(self, event: Mapping[str, Any]) -> None:
        stamp = dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")
        line = {"ts": stamp, "session": self.session, **event}
        # The scorer can plant `log.jsonl`; an append never writes through it.
        write_private(self.log, json.dumps(line, sort_keys=True) + "\n", append=True)

    def _optimizer(
        self, args: list[str], extra: Mapping[str, str] | None = None
    ) -> tuple[int, dict[str, Any]]:
        # A fresh private cache per call, so neither a cache planted in
        # `scripts/eval/__pycache__` nor one left in state is ever read.
        with tempfile.TemporaryDirectory(prefix="pycache-", dir=self.state) as cache:
            env = {**os.environ, "PYTHONPYCACHEPREFIX": cache, **(extra or {})}
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

    def score(self, label: str, expected: bytes) -> Path:
        """Run the scorer, move its output into state, extract all results.

        `expected` is the artifact the scorer must have seen. A scorer that
        runs the artifact's code (the `hook` kind) could rewrite it, a denied
        task file, or controller state; each is checked before the results
        are used.
        """
        self._check_integrity()
        run_id = f"{label}-{uuid.uuid4().hex[:8]}"
        run_dir = self.state / "runs" / run_id
        run_dir.mkdir(parents=True)
        values = {"run_id": run_id, "run_dir": str(run_dir)}
        # The candidate's code may run inside the scorer. Everything already in
        # state must be exactly as the controller left it when the scorer ends.
        before = tree_digest([self.state], exclude=run_dir)
        refuse_stale_reports(self.config.collect, values, label)
        # The scorer's bytecode cache goes inside its own run directory, so a
        # cache planted beside the scorer's code is never read and the state
        # digest above still excludes everything the scorer may write.
        scorer_env = {**os.environ, "PYTHONPYCACHEPREFIX": str(run_dir / "pycache")}
        argv = [fill(part, values) for part in self.config.scorer]
        try:
            duration = run_child(
                [fill(part, {"artifact": str(self.config.artifact)}) for part in argv],
                f"scorer {label}",
                self.config.timeout_seconds,
                scorer_env,
                self.config.scorer_exit_codes,
            )
        except ControllerError:
            # A failed scorer may still have written a report outside state,
            # with held-out outcomes in it. Move what exists before stopping;
            # collection problems must not hide the scorer's own error.
            collect_or_quarantine(
                self.config.collect, values, run_dir, self.state / f"quarantine-{run_id}"
            )
            raise
        # Collected before every check below, so no refusal leaves a report
        # outside state.
        problems = collect_or_quarantine(
            self.config.collect, values, run_dir, self.state / f"quarantine-{run_id}"
        )
        # The digest skips `run_dir` by path, so a link swapped in for it (or
        # for `runs/`) would carry reports and results outside state unseen.
        self._require_run_dir(run_dir, label)
        if tree_digest([self.state], exclude=run_dir) != before:
            raise ControllerError(f"controller state changed while {label} was scored")
        if problems:
            raise ControllerError("; ".join(problems), EXIT_EXTERNAL)
        self._check_integrity()
        if read_artifact(self.config.artifact) != expected:
            raise ControllerError(
                f"the artifact changed while {label} was being scored; "
                "refusing to use results for bytes that were not the ones scored"
            )
        self._record({"event": "call", "label": f"scorer {label}", "duration_s": duration})
        inputs = contained_inputs(self.config.inputs, values, run_dir)
        code, payload = self._optimizer(
            ["extract", "--kind", self.config.kind, "--input", *inputs, *self.config.extract_args]
        )
        if code != 0:
            raise ControllerError(f"extract refused the {label} scorer output", EXIT_EXTERNAL)
        self._require_run_dir(run_dir, label)
        results: Path = run_dir / "results.json"
        # Exclusive create: the scorer ran in this directory and could have
        # planted `results.json` as a link into state.
        write_private(results, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return results

    def _require_run_dir(self, run_dir: Path, label: str) -> None:
        if not is_real_dir(run_dir):
            raise ControllerError(f"{run_dir} was replaced while {label} was scored")

    def _results(self, path: Path) -> dict[str, Any]:
        document: dict[str, Any] = json.loads(read_private(path, "controller file"))
        return document

    def _publish(self, step: int) -> Path:
        """Empty the workspace, then write the step's feedback and task copies.

        Emptying it closes a channel: candidate code run by the scorer could
        otherwise leave held-out data there for the next proposer step. No
        controller write follows a link the proposer planted.
        """
        workspace = self.config.workspace_dir
        clear_dir(workspace)
        mapping = self._results(self.incumbent)["results"]
        opt_ids = self._results(self.state / "split.json")["opt"]
        opt = {task: mapping[task] for task in opt_ids if task in mapping}
        if self.config.opt_task_files:
            tasks_dir = workspace / "tasks"
            tasks_dir.mkdir()
            for task in opt:
                source = resolve(task_file(self.config.opt_task_files, task))
                # Every component, not only the leaf: a linked directory in
                # the path would copy bytes from outside the task tree.
                if os.path.realpath(source) != os.path.abspath(source):
                    raise ControllerError(
                        f"optimize-group task path {source} passes through a link"
                    )
                # A link could point at a held-out definition and hand it over
                # under an optimize-group name, so links are refused.
                # One descriptor, so a link or hard link swapped in after the
                # path check is refused rather than copied.
                data = read_private(source, "optimize-group task file")
                target = tasks_dir / source.name
                if target.exists():
                    raise ControllerError(
                        f"two optimize-group task files share the name {source.name}; "
                        "use a template whose file names are unique per task"
                    )
                target.write_bytes(data)
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
        # `state_lock` made state private. The ledger is made here, so the
        # gate never creates it through a link.
        (self.state / "ledger").mkdir(mode=0o700, exist_ok=True)
        self.incumbent_bytes = read_artifact(config.artifact)
        self.mode = config.artifact.stat().st_mode & 0o7777
        self.integrity = tree_digest(self._protected())
        try:
            self.incumbent = self.score("incumbent-0", self.incumbent_bytes)
        except Exception:
            # A scorer that runs the incumbent's code may have rewritten it.
            # Put the launcher's file back before stopping, whatever failed.
            self.restoring = True
            self._restore()
            raise
        document = self._results(self.incumbent)
        tasks = self.state / "tasks.txt"
        write_private(tasks, "\n".join(sorted(document["results"])) + "\n")
        args = ["split", "--tasks", str(tasks), "--seed", config.seed]
        args += ["--sel-ratio", config.sel_ratio, "--out", str(self.state / "split.json")]
        if document.get("corpus"):
            args += ["--corpus", document["corpus"]]
        code, split_doc = self._optimizer(args)
        if code != 0:
            raise ControllerError("split refused the incumbent's task inventory", EXIT_EXTERNAL)
        self.fingerprint = split_doc["fingerprint"]
        self._record({"event": "baseline", "results": str(self.incumbent), "split": split_doc})

    def _gate(self, step: int, candidate: Path, candidate_sha: str) -> str:
        if not is_real_dir(self.state / "ledger"):
            raise ControllerError("the consultation ledger directory was replaced")
        args = ["gate", "--incumbent", str(self.incumbent), "--candidate", str(candidate)]
        args += ["--split", str(self.state / "split.json")]
        args += ["--max-consultations", str(self.config.max_consultations)]
        args += ["--incumbent-fingerprint", self.fingerprint]
        if self.config.max_p is not None:
            args += ["--max-p", str(self.config.max_p)]
        code, verdict = self._optimizer(args, {"EVAL_LEDGER_DIR": str(self.state / "ledger")})
        self._record(
            {
                "event": "gate",
                "step": step,
                "exit": code,
                "verdict": verdict,
                "candidate_sha256": candidate_sha,
            }
        )
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
            candidate = self.score(f"candidate-{step}", candidate_bytes)
        finally:
            # Every exit from the step restores the incumbent before the gate:
            # a failed proposer, a failed scorer, and a normal step. Only an
            # ACCEPT below writes the candidate back. The integrity check runs
            # here too, so a NO_CHANGE step that edited a denied file stops.
            # Guard set before the call, so a SIGTERM between here and the
            # write is deferred rather than raised ahead of the restore.
            self.restoring = True
            self._restore()
            self._check_integrity()
        self.last = self._gate(step, candidate, hashlib.sha256(candidate_bytes).hexdigest())
        if self.last == "ACCEPT":
            self.accepts += 1
            self.incumbent = candidate
            self.incumbent_bytes = candidate_bytes
            write_artifact(config.artifact, self.incumbent_bytes, self.mode)

    def _restore(self) -> None:
        """Write the incumbent back, holding SIGTERM until the write lands.

        A SIGTERM raised mid-write would stop before `os.replace` and leave
        the ungated candidate on disk. The signal is recorded, and honored
        once the incumbent is in place.
        """
        self.restoring = True  # callers set it first too; see `_step`
        try:
            write_artifact(self.config.artifact, self.incumbent_bytes, self.mode)
        finally:
            self.restoring = False
        if self.term_pending:
            raise ControllerError("controller received a stop signal", EXIT_EXTERNAL)

    def on_sigterm(self, _signum: int, _frame: FrameType | None) -> None:
        # Raised, so the step's `finally` restores the incumbent and kills the
        # child's group before the process exits. Deferred during a restore.
        # SIGINT (Ctrl+C) takes the same path, so it cannot unwind a restore.
        self.term_pending = True
        if not self.restoring:
            raise ControllerError("controller received a stop signal", EXIT_EXTERNAL)

    def run(self) -> dict[str, Any]:
        previous = signal.signal(signal.SIGTERM, self.on_sigterm)
        previous_int = signal.signal(signal.SIGINT, self.on_sigterm)
        try:
            # Held for the whole run; a refused second run has not started.
            with state_lock(self.state), artifact_lock(self.config.artifact):
                return self._run()
        except ControllerError as exc:
            # A planted log refuses the abort record; the original error wins.
            with contextlib.suppress(ControllerError):
                if self.started and self.log.parent.is_dir():
                    self._record(
                        {
                            "event": "abort",
                            "code": exc.code,
                            "error": str(exc),
                            "detail": exc.detail,
                        }
                    )
            raise
        finally:
            # A handler installed from C reads back as None; fall back to default.
            signal.signal(signal.SIGTERM, previous if previous is not None else signal.SIG_DFL)
            signal.signal(
                signal.SIGINT, previous_int if previous_int is not None else signal.SIG_DFL
            )

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


def cmd_policy(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    rule = access_rule(config)
    # A proposer that removed an artifact lock could let a second controller on.
    rule["deny_read_write"].append(str(artifact_lock_path(config.artifact)))
    print(json.dumps(rule, indent=2))
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
