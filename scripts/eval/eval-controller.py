#!/usr/bin/env python3
"""Trusted controller for the held-out-gated optimization loop (ADR-087 OR1).

`optimize-artifact.py` assumes a cooperating optimizer: the agent that edits
the artifact also runs `extract`, `split`, and `gate`, so held-out outcomes and
task definitions sit in files it can read. This controller inverts that. The
launcher runs the controller, and the controller runs the optimizing agent as
a child "proposer". The proposer never calls the optimizer rails. Each step it
receives:

- the optimize-group results of the current incumbent (task id to pass bool),
- copies of the optimize-group task files, when the config names them,
- one bit about its last candidate: ACCEPT or REJECT.

Everything else stays under the controller's state directory: the scorer's raw
output, every results file, the split with held-out membership, the
consultation ledger, and the full gate payloads.

The boundary is real only when the launcher denies the proposer read and write
access to every path `policy` prints. Python cannot stop a same-user process
from opening a file. The controller makes that one rule sufficient: no
workflow step needs the proposer to touch a denied path. The controller also
digests the denied task files before the loop and refuses to score after any
of them changed, so a write that slips past the sandbox is caught, not scored.

Subcommands:

- `policy --config C`: print the paths the launcher must deny the proposer.
- `run --config C`: baseline the incumbent, then run the proposer loop.

Exit codes (ADR-035): 0 loop finished, 2 config or integrity refusal,
3 scorer, proposer, or optimizer subprocess failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_KINDS = ("agent", "rule", "hook")
_OPTIMIZER = Path(__file__).resolve().with_name("optimize-artifact.py")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DECISIONS = {0: "ACCEPT", 1: "REJECT"}


class ControllerError(Exception):
    """A config, integrity, or subprocess failure with a known exit code."""

    def __init__(self, message: str, code: int = EXIT_CONFIG) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Config:
    kind: str
    artifact: Path
    state_dir: Path
    workspace_dir: Path
    scorer: list[str]
    collect: list[str]
    inputs: list[str]
    extract_args: list[str]
    proposer: list[str]
    seed: str
    sel_ratio: str
    max_consultations: int
    max_p: float | None
    steps: int
    opt_task_files: str | None
    deny_paths: list[Path]
    config_path: Path
    timeout_seconds: int


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _REPO_ROOT / path


def _string_list(data: Mapping[str, Any], key: str, required: bool = True) -> list[str]:
    value = data.get(key, None if required else [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ControllerError(f"config `{key}` must be a list of strings")
    if required and not value:
        raise ControllerError(f"config `{key}` must not be empty")
    return list(value)


def _positive_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ControllerError(f"config `{key}` must be a positive integer")
    return value


def load_config(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ControllerError(f"cannot read config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ControllerError("config must be a JSON object")
    kind = data.get("kind")
    if kind not in _KINDS:
        raise ControllerError(f"config `kind` must be one of {', '.join(_KINDS)}")
    for key in ("artifact", "state_dir", "workspace_dir", "seed"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ControllerError(f"config `{key}` must be a non-empty string")
    max_p = data.get("max_p")
    if max_p is not None and (isinstance(max_p, bool) or not isinstance(max_p, (int, float))):
        raise ControllerError("config `max_p` must be a number or null")
    opt_task_files = data.get("opt_task_files")
    if opt_task_files is not None and (
        not isinstance(opt_task_files, str)
        or ("{task_id}" not in opt_task_files and "{task_name}" not in opt_task_files)
    ):
        raise ControllerError(
            "config `opt_task_files` must be a string holding `{task_id}` or `{task_name}`"
        )
    sel_ratio = data.get("sel_ratio", "0.4")
    if not isinstance(sel_ratio, str):
        raise ControllerError("config `sel_ratio` must be a string, as `split` reads it")
    state_dir = _resolve(data["state_dir"])
    workspace_dir = _resolve(data["workspace_dir"])
    if _overlaps(state_dir, workspace_dir):
        raise ControllerError("`workspace_dir` and `state_dir` must not contain each other")
    return Config(
        kind=kind,
        artifact=_resolve(data["artifact"]),
        state_dir=state_dir,
        workspace_dir=workspace_dir,
        scorer=_string_list(data, "scorer"),
        collect=_string_list(data, "collect", required=False),
        inputs=_string_list(data, "inputs"),
        extract_args=_string_list(data, "extract_args", required=False),
        proposer=_string_list(data, "proposer"),
        seed=data["seed"],
        sel_ratio=sel_ratio,
        max_consultations=_positive_int(data, "max_consultations"),
        max_p=None if max_p is None else float(max_p),
        steps=_positive_int(data, "steps"),
        opt_task_files=opt_task_files,
        # Required: an empty list leaves the held-out task definitions readable
        # and undigested, which is the cooperating-optimizer design again.
        deny_paths=[_resolve(item) for item in _string_list(data, "deny_paths")],
        config_path=path.resolve(),
        timeout_seconds=_positive_int({"timeout_seconds": 3600, **data}, "timeout_seconds"),
    )


def _overlaps(left: Path, right: Path) -> bool:
    a, b = left.resolve(), right.resolve()
    return a == b or a in b.parents or b in a.parents


def denied_paths(config: Config) -> list[Path]:
    """The state directory, the config, and every task-definition path.

    The config is denied because it names the seed and the task inventory, so a
    proposer that reads it can redraw the split and recover held-out membership.
    """
    paths = [config.state_dir, config.config_path, *config.deny_paths]
    if _overlaps(config.config_path, config.workspace_dir):
        raise ControllerError("the config must not sit inside the proposer workspace")
    for path in paths[2:]:
        if _overlaps(path, config.workspace_dir) or _overlaps(path, config.artifact):
            raise ControllerError(
                "a deny path overlaps the proposer workspace or the artifact; "
                "the proposer would need it to do its job"
            )
    return paths


def tree_digest(paths: Sequence[Path]) -> str:
    """One digest over the names and bytes of every file under `paths`."""
    sha = hashlib.sha256()
    for root in paths:
        files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else [root]
        for file in files:
            if not file.exists():
                sha.update(f"missing:{file}\n".encode())
                continue
            sha.update(f"{file}:{hashlib.sha256(file.read_bytes()).hexdigest()}\n".encode())
    return sha.hexdigest()


def _fill(template: str, values: Mapping[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    """Kill the child's process group when its call ends.

    A proposer that leaves a background child behind could rewrite the artifact
    after the controller read it. This kills the group the child started in.
    It does not reach a descendant that left the group with `setsid`, and on
    Windows it kills only the direct child. The post-score byte check and the
    per-step integrity check in `Controller.run` are the guards that remain.
    """
    if os.name != "posix":
        proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run(argv: list[str], what: str, timeout: int) -> str:
    # Output goes to temporary files, not pipes. A descendant that escapes the
    # process group would otherwise hold a pipe open, and the read would block
    # past the timeout until that descendant exited.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(
                argv, stdout=out, stderr=err, cwd=_REPO_ROOT, start_new_session=True
            )
        except OSError as exc:
            raise ControllerError(f"{what} could not start: {exc}", EXIT_EXTERNAL) from exc
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill_group(proc)
            proc.wait()
            raise ControllerError(f"{what} timed out after {timeout}s", EXIT_EXTERNAL) from exc
        finally:
            _kill_group(proc)
        out.seek(0)
        err.seek(0)
        stdout = out.read().decode("utf-8", errors="replace")
        stderr = err.read().decode("utf-8", errors="replace")
    if proc.returncode != 0:
        tail = (stderr or stdout).strip()[-400:]
        raise ControllerError(f"{what} exited {proc.returncode}: {tail}", EXIT_EXTERNAL)
    return stdout


def _write_artifact(path: Path, data: bytes, mode: int) -> None:
    """Replace the artifact without following a link the proposer planted.

    `os.replace` swaps the directory entry, so a symlink or hard link at
    `path` is replaced rather than written through. Writing through it would
    let the proposer aim a controller write at a denied file. `mkstemp`
    creates the temp file at 0600, so the artifact's own mode, recorded before
    the loop, is set before the swap.
    """
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _read_artifact(path: Path) -> bytes:
    """Read the artifact, refusing a symlink or a hard link.

    A hard link would let the proposer make a denied file's bytes the
    candidate, and read them through the artifact path.
    """
    if path.is_symlink() or not path.is_file():
        raise ControllerError(f"artifact {path} is no longer a regular file")
    if path.stat().st_nlink > 1:
        raise ControllerError(f"artifact {path} has more than one hard link")
    return path.read_bytes()


def _optimizer(args: list[str], env: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    argv = [sys.executable, str(_OPTIMIZER), *args]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=_REPO_ROOT,
        env=dict(env) if env is not None else None,
    )
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise ControllerError(
            f"optimize-artifact {args[0]} returned no JSON (exit {proc.returncode})",
            EXIT_EXTERNAL,
        ) from exc
    if not isinstance(payload, dict):
        raise ControllerError(f"optimize-artifact {args[0]} returned a non-object", EXIT_EXTERNAL)
    return proc.returncode, payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class Controller:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = config.state_dir
        self.log = self.state / "log.jsonl"
        self.integrity = ""

    def _record(self, event: Mapping[str, Any]) -> None:
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _check_integrity(self) -> None:
        if tree_digest(self.config.deny_paths) != self.integrity:
            raise ControllerError(
                "a denied task-definition path changed during the loop; "
                "refusing to score against edited tasks"
            )

    def score(self, label: str) -> Path:
        """Run the scorer, move its output into state, extract all results."""
        self._check_integrity()
        run_id = f"{label}-{uuid.uuid4().hex[:8]}"
        run_dir = self.state / "runs" / run_id
        run_dir.mkdir(parents=True)
        values = {"run_id": run_id, "run_dir": str(run_dir), "artifact": str(self.config.artifact)}
        _run(
            [_fill(part, values) for part in self.config.scorer],
            f"scorer ({label})",
            self.config.timeout_seconds,
        )
        for index, template in enumerate(self.config.collect):
            source = _resolve(_fill(template, values))
            if not source.exists():
                raise ControllerError(f"scorer output {source} was not produced", EXIT_EXTERNAL)
            shutil.move(str(source), str(run_dir / str(index)))
        inputs = [_fill(item, values) for item in self.config.inputs]
        code, payload = _optimizer(
            ["extract", "--kind", self.config.kind, "--input", *inputs, *self.config.extract_args]
        )
        if code != 0:
            raise ControllerError(f"extract refused the {label} scorer output", EXIT_EXTERNAL)
        results = run_dir / "results.json"
        _write_json(results, payload)
        return results

    def opt_view(self, results: Path) -> dict[str, Any]:
        """The only results the proposer sees: the optimize group."""
        data = json.loads(results.read_text(encoding="utf-8"))
        opt_ids = json.loads((self.state / "split.json").read_text(encoding="utf-8"))["opt"]
        mapping = data["results"]
        return {task: mapping[task] for task in opt_ids if task in mapping}

    def _publish(self, step: int, opt: Mapping[str, Any], last: str | None, left: int) -> Path:
        workspace = self.config.workspace_dir
        if workspace.is_symlink():
            raise ControllerError("workspace_dir must not be a symlink")
        workspace.mkdir(parents=True, exist_ok=True)
        feedback = workspace / "feedback.json"
        tasks_dir = workspace / "tasks"
        # The proposer can write here, so it could plant a symlink that sends a
        # controller write outside the deny rule. Remove both names, never
        # following a link, then create them fresh.
        for name in (feedback, tasks_dir):
            if name.is_symlink() or name.is_file():
                name.unlink()
            elif name.is_dir():
                shutil.rmtree(name)
        if self.config.opt_task_files:
            tasks_dir.mkdir()
            for task in opt:
                source = _resolve(
                    _fill(
                        self.config.opt_task_files,
                        {"task_id": task, "task_name": task.rsplit("::", 1)[-1]},
                    )
                )
                if source.is_file():
                    shutil.copy2(source, tasks_dir / source.name)
        passed = sum(1 for value in opt.values() if value)
        document = json.dumps(
            {
                "step": step,
                "artifact": str(self.config.artifact),
                "opt_results": dict(opt),
                "opt_score": passed / len(opt) if opt else 0.0,
                "last_decision": last,
                "consultations_left": left,
            },
            indent=2,
            sort_keys=True,
        )
        with feedback.open("x", encoding="utf-8") as handle:
            handle.write(document + "\n")
        return feedback

    def run(self) -> dict[str, Any]:
        config = self.config
        denied_paths(config)
        if (self.state / "split.json").exists():
            raise ControllerError("state_dir already holds a session; use a fresh state_dir")
        self.state.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state, 0o700)
        if not config.artifact.is_file():
            raise ControllerError(f"artifact {config.artifact} does not exist")
        self.integrity = tree_digest(config.deny_paths)

        incumbent = self.score("incumbent-0")
        tasks = self.state / "tasks.txt"
        task_ids = sorted(json.loads(incumbent.read_text(encoding="utf-8"))["results"])
        tasks.write_text("\n".join(task_ids) + "\n", encoding="utf-8")
        split_args = [
            "split",
            "--tasks",
            str(tasks),
            "--seed",
            config.seed,
            "--sel-ratio",
            config.sel_ratio,
            "--out",
            str(self.state / "split.json"),
        ]
        corpus = json.loads(incumbent.read_text(encoding="utf-8")).get("corpus")
        if corpus:
            split_args += ["--corpus", corpus]
        code, split_doc = _optimizer(split_args)
        if code != 0:
            raise ControllerError(f"split refused: {split_doc.get('error')}", EXIT_EXTERNAL)
        fingerprint = split_doc["fingerprint"]
        self._record({"event": "baseline", "results": str(incumbent), "split": split_doc})

        gate_env = {**os.environ, "EVAL_LEDGER_DIR": str(self.state / "ledger")}
        incumbent_bytes = _read_artifact(config.artifact)
        mode = config.artifact.stat().st_mode & 0o7777
        last: str | None = None
        accepts = 0
        spent = 0
        steps_run = 0
        for step in range(1, config.steps + 1):
            if spent >= config.max_consultations:
                break
            steps_run = step
            feedback = self._publish(
                step, self.opt_view(incumbent), last, config.max_consultations - spent
            )
            values = {
                "feedback": str(feedback),
                "artifact": str(config.artifact),
                "workspace": str(config.workspace_dir),
                "step": str(step),
            }
            try:
                _run(
                    [_fill(part, values) for part in config.proposer],
                    f"proposer (step {step})",
                    config.timeout_seconds,
                )
                candidate_bytes = _read_artifact(config.artifact)
                if candidate_bytes == incumbent_bytes:
                    last = "NO_CHANGE"
                    self._record({"event": "no_change", "step": step})
                    continue
                candidate = self.score(f"candidate-{step}")
                if _read_artifact(config.artifact) != candidate_bytes:
                    raise ControllerError(
                        f"the artifact changed while step {step} was being scored; "
                        "refusing to gate bytes that were not the ones scored"
                    )
            finally:
                # Every exit from the step restores the incumbent before the
                # gate: a failed proposer, a failed scorer, and a normal step.
                # Only an ACCEPT below writes the candidate back.
                _write_artifact(config.artifact, incumbent_bytes, mode)
                # Checked after the restore, not only before scoring, so a step
                # that edits a denied file and leaves the artifact alone (the
                # NO_CHANGE path) still stops the loop.
                self._check_integrity()
            gate_args = [
                "gate",
                "--incumbent",
                str(incumbent),
                "--candidate",
                str(candidate),
                "--split",
                str(self.state / "split.json"),
                "--max-consultations",
                str(config.max_consultations),
                "--incumbent-fingerprint",
                fingerprint,
            ]
            if config.max_p is not None:
                gate_args += ["--max-p", str(config.max_p)]
            code, verdict = _optimizer(gate_args, env=gate_env)
            self._record(
                {
                    "event": "gate",
                    "step": step,
                    "exit": code,
                    "verdict": verdict,
                    "candidate": str(candidate),
                }
            )
            if code not in _DECISIONS:
                raise ControllerError(
                    f"gate refused at step {step}; see the controller log", EXIT_EXTERNAL
                )
            spent += 1
            last = _DECISIONS[code]
            if last == "ACCEPT":
                accepts += 1
                incumbent = candidate
                incumbent_bytes = candidate_bytes
                _write_artifact(config.artifact, incumbent_bytes, mode)
        final_bytes = _read_artifact(config.artifact)
        if final_bytes != incumbent_bytes:
            raise ControllerError(
                "the artifact changed after the controller's last write; "
                "the file on disk is not the incumbent this run selected"
            )
        summary = {
            "steps_run": steps_run,
            "accepts": accepts,
            "consultations_spent": spent,
            "last_decision": last,
            # Read from disk, not memory, so the summary describes the file
            # left behind rather than the bytes the controller meant to write.
            "artifact_sha256": hashlib.sha256(final_bytes).hexdigest(),
        }
        self._record({"event": "done", **summary})
        return summary


def cmd_policy(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    paths = denied_paths(config)
    print(
        json.dumps(
            {
                "deny_read_write": [str(p) for p in paths],
                "proposer_workspace": str(config.workspace_dir),
                "proposer_may_write": [str(config.artifact)],
            },
            indent=2,
        )
    )
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    summary = Controller(load_config(args.config)).run()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval-controller.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, text in (
        ("policy", cmd_policy, "print the paths the launcher must deny the proposer"),
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
        return exc.code
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
