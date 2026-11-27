"""Launcher config, layout checks, and the printed access rule.

Split from `_controller_io.py` so each controller file stays reviewable. The
launcher owns the config, so it is trusted; these checks refuse layouts where
the proposer would need a denied path, or where the controller's own writes
would read as tampering.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

KINDS = ("agent", "rule", "hook")
EVAL_DIR = Path(__file__).resolve().parent
OPTIMIZER = EVAL_DIR / "optimize-artifact.py"
REPO_ROOT = EVAL_DIR.parents[1]


class ControllerError(Exception):
    """A config, integrity, or subprocess failure with a known exit code."""

    def __init__(self, message: str, code: int = EXIT_CONFIG, detail: str = "") -> None:
        super().__init__(message)
        self.code = code
        # Child output stays out of the message, which reaches the launcher's
        # stderr. The controller writes it to its own denied log instead.
        self.detail = detail


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
    trusted_paths: list[Path]
    proposer_env: list[str]
    scorer_exit_codes: tuple[int, ...]
    config_path: Path
    timeout_seconds: int


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def overlaps(left: Path, right: Path) -> bool:
    a, b = left.resolve(), right.resolve()
    return a == b or a in b.parents or b in a.parents


def _string_list(data: Mapping[str, Any], key: str, required: bool = True) -> list[str]:
    value = data.get(key, None if required else [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ControllerError(f"config `{key}` must be a list of strings")
    if required and not value:
        raise ControllerError(f"config `{key}` must not be empty")
    return list(value)


def _run_dir_inputs(inputs: list[str]) -> list[str]:
    """`extract` reads only the private run directory, after collection.

    An input outside it would be a report the launcher's rule never names,
    readable by the proposer while it waits there.
    """
    for item in inputs:
        if not item.startswith("{run_dir}"):
            raise ControllerError(
                f"config `inputs` entry {item!r} must start with `{{run_dir}}`; "
                "name reports written elsewhere in `collect`"
            )
    return inputs


def _positive_int(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ControllerError(f"config `{key}` must be a positive integer")
    return value


def _checked_strings(data: Mapping[str, Any]) -> None:
    if data.get("kind") not in KINDS:
        raise ControllerError(f"config `kind` must be one of {', '.join(KINDS)}")
    for key in ("artifact", "state_dir", "workspace_dir", "seed"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ControllerError(f"config `{key}` must be a non-empty string")
    max_p = data.get("max_p")
    if max_p is not None and (
        isinstance(max_p, bool) or not isinstance(max_p, (int, float)) or not 0 <= max_p <= 1
    ):
        # Checked here, not first at the gate, so a bad bar never pays for scoring.
        raise ControllerError("config `max_p` must be a number in [0, 1] or null")
    template = data.get("opt_task_files")
    if template is not None and (
        not isinstance(template, str)
        or ("{task_id}" not in template and "{task_name}" not in template)
    ):
        raise ControllerError(
            "config `opt_task_files` must be a string holding `{task_id}` or `{task_name}`"
        )
    if not isinstance(data.get("sel_ratio", "0.4"), str):
        raise ControllerError("config `sel_ratio` must be a string, as `split` reads it")


def load_config(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ControllerError(f"cannot read config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ControllerError("config must be a JSON object")
    _checked_strings(data)
    max_p = data.get("max_p")
    codes = data.get("scorer_exit_codes", [0])
    if (
        not isinstance(codes, list)
        or not codes
        or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c < 256 for c in codes)
    ):
        raise ControllerError("config `scorer_exit_codes` must be a non-empty list of exit codes")
    if not isinstance(data.get("proposer_env"), list):
        raise ControllerError(
            "config `proposer_env` must list the variables the proposer may see ([] for none)"
        )
    config = Config(
        kind=data["kind"],
        # Canonical path: a launcher may name a tracked symlink (rules are
        # links into src/claude/rules/). Every later read refuses a link, so
        # the controller works on the file the link names.
        artifact=resolve(data["artifact"]).resolve(),
        # Canonical paths throughout: a symlinked directory would otherwise be
        # digested as one link entry, and edits inside it would go unseen.
        state_dir=resolve(data["state_dir"]).resolve(),
        workspace_dir=resolve(data["workspace_dir"]).resolve(),
        scorer=_string_list(data, "scorer"),
        collect=_string_list(data, "collect", required=False),
        inputs=_run_dir_inputs(_string_list(data, "inputs")),
        extract_args=_string_list(data, "extract_args", required=False),
        proposer=_string_list(data, "proposer"),
        seed=data["seed"],
        sel_ratio=data.get("sel_ratio", "0.4"),
        max_consultations=_positive_int(data.get("max_consultations"), "max_consultations"),
        max_p=None if max_p is None else float(max_p),
        steps=_positive_int(data.get("steps"), "steps"),
        opt_task_files=data.get("opt_task_files"),
        # Required: an empty list leaves the held-out task definitions readable
        # and undigested, which is the cooperating-optimizer design again.
        deny_paths=[resolve(item).resolve() for item in _string_list(data, "deny_paths")],
        trusted_paths=[
            resolve(item).resolve() for item in _string_list(data, "trusted_paths", required=False)
        ],
        proposer_env=_string_list(data, "proposer_env", required=False),
        scorer_exit_codes=tuple(codes),
        config_path=path.resolve(),
        timeout_seconds=_positive_int(data.get("timeout_seconds", 3600), "timeout_seconds"),
    )
    check_layout(config)
    return config


def trusted_code(config: Config) -> list[Path]:
    """Code the controller runs with its own authority: the gate and the scorer.

    The whole eval directory, not only its `.py` files: a planted package
    directory or data file beside `optimize-artifact.py` could shadow a module
    it imports. `tree_digest` records every entry, directories included.
    Bytecode caches are excluded because the controller runs the optimizer
    with `PYTHONPYCACHEPREFIX` under its state directory, so a cache under
    `scripts/eval/__pycache__` is never read.
    """
    return [EVAL_DIR, *config.trusted_paths]


def check_layout(config: Config) -> None:
    """Refuse a layout where the proposer would need a denied path to work."""
    _check_workspace_and_artifact(config)
    _check_protected_paths(config)


def _check_workspace_and_artifact(config: Config) -> None:
    if overlaps(config.state_dir, config.workspace_dir):
        raise ControllerError("`workspace_dir` and `state_dir` must not contain each other")
    if overlaps(config.config_path, config.workspace_dir):
        raise ControllerError("the config must not sit inside the proposer workspace")
    if overlaps(config.artifact, config.workspace_dir):
        raise ControllerError(
            "the artifact must not sit inside the proposer workspace, which is emptied each step"
        )
    if overlaps(config.artifact, config.state_dir):
        raise ControllerError("the artifact must not sit inside state_dir")
    if config.artifact == config.config_path:
        raise ControllerError("the artifact must not be the launcher config")


def _check_protected_paths(config: Config) -> None:
    for path in [*config.deny_paths, *trusted_code(config)]:
        if overlaps(path, config.workspace_dir) or overlaps(path, config.artifact):
            raise ControllerError(
                "a deny or trusted path overlaps the proposer workspace or the artifact; "
                "the proposer would need it to do its job"
            )
    for path in trusted_code(config):
        if overlaps(path, config.state_dir) or overlaps(path, config.workspace_dir):
            raise ControllerError(
                "state_dir and workspace_dir must sit outside trusted code; the controller's "
                "own writes there would read as tampering"
            )
    for path in config.deny_paths:
        if overlaps(path, config.state_dir) or overlaps(path, config.config_path):
            raise ControllerError(
                "a deny path overlaps state_dir or the config; the digest would "
                "change as the controller writes its own state"
            )


def access_rule(config: Config) -> dict[str, Any]:
    """The rule the launcher must apply to the proposer, as `policy` prints it."""
    return {
        "deny_read_write": [str(p) for p in (config.state_dir, config.config_path)]
        + [str(p) for p in config.deny_paths],
        "deny_write": [str(p) for p in trusted_code(config)],
        # Scorer reports sit here until the controller moves them. They can
        # hold held-out outcomes, so the proposer must not read them either.
        # Templates are printed as given; deny the directory each one names.
        "deny_read_write_collect": list(config.collect),
        "proposer_workspace": str(config.workspace_dir),
        "proposer_may_write": [str(config.artifact)],
    }
