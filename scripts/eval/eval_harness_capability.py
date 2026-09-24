#!/usr/bin/env python3
"""Assemble and validate the per-harness capability matrix (issue #5423).

This is a thin CLI. It loads the checked-in matrix, fills a live runtime
version where that CLI is installed, optionally executes shell-free behavioral
probe commands from a JSON plan, derives #5422 arm eligibility, and emits a
machine-readable report for #5424 and #5426.

Version and behavioral probing are read-only and evidence-honest. A behavioral
result can upgrade only the capability named by its plan entry, and only after
the runtime version is confirmed. A harness that is absent from PATH, or not
probe-capable, keeps its checked-in UNVERIFIED state.

Exit codes follow AGENTS.md: 0 ok, 2 config, 3 external.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

from _capability_probes import (
    OVERRIDE_CAPABILITIES,
    BehavioralProbe,
    build_override_plan,
    load_behavioral_probes,
    probe_concurrency,
    probe_override,
    probe_subagent_support,
)
from _harness_capability import (
    Capability,
    EvidenceKind,
    HarnessCapabilityError,
    HarnessCapabilityRecord,
    apply_behavioral_probe,
    apply_version_probe,
    build_report,
    load_matrix,
    write_report,
)
from _runtime_harness import probe_version, runtime_env

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = Path(__file__).parent / "examples" / "harness-capability-matrix.json"
DEFAULT_TIMEOUT = 60.0

# Only harnesses whose isolated profile `_runtime_parity.runtime_env` knows how
# to build are probe-capable through the existing prober. `_runtime_parity`
# now has a codex branch (profile root, isolated env, version-probe argv), so
# codex is wired in alongside copilot. Neither harness's *behavioral*
# capabilities (model/effort override, subagent support, and so on) are
# probed anywhere in this module: only the version string can move off
# UNVERIFIED here, and only when the CLI is actually on PATH.
PROBE_HARNESS: dict[str, str] = {"copilot": "copilot", "codex": "codex"}

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _probe_bin(harness: str, copilot_bin: str) -> str:
    return copilot_bin if harness == "copilot" else harness


_ISOLATED_ENV_KEYS = frozenset(
    {
        "APPDATA",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "COPILOT_CACHE_HOME",
        "COPILOT_HOME",
        "COPILOT_SESSION_STATE_DIR",
        "HOME",
        "LOCALAPPDATA",
        "PATH",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
    }
)


def _canonical_executable(executable: str) -> Path | None:
    resolved = shutil.which(executable)
    return Path(resolved).resolve() if resolved is not None else None


def _install_codex_auth(source: Path, codex_home: Path) -> Path:
    """Copy an operator-supplied ChatGPT `auth.json` into an isolated CODEX_HOME.

    A ChatGPT-login Codex authenticates only through `$CODEX_HOME/auth.json`;
    `CODEX_ACCESS_TOKEN` is ignored (probed 2026-09-24, codex-cli 0.156.0: a
    ChatGPT access token supplied through that variable produced a 401
    "Missing bearer" against api.openai.com). `_runtime_harness.runtime_env`
    therefore leaves an isolated codex probe unauthenticated unless the
    operator opts in with `--codex-auth-file`.

    The file is copied, not symlinked or referenced by path, so the probe's
    isolated profile under the report directory holds its own credential
    copy: the operator's real `auth.json` is never opened by the probed CLI.
    The caller (`_augment_behavioral`) deletes the returned path once the
    probe using it has run, whether or not it raised, so the copy never
    outlives the single probe it authenticates.

    Two windows a plain `shutil.copyfile` + `os.chmod(0o600)` leaves open are
    closed here: `codex_home` is chmod'd to `0o700` after creation, because
    `Path.mkdir(mode=...)` is masked by the process umask and cannot be
    trusted alone to produce an exact mode; and `target` is created with
    `os.open(..., O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)` so the file is never
    briefly world- or group-readable between creation and the follow-up
    `chmod` a copy-then-chmod sequence would need, and a symlink planted at
    `target` by another process cannot be followed. Mode `0o600` matches the
    file Codex itself writes at `~/.codex/auth.json`. Contents are never
    logged; only the source and destination paths are ever reported, through
    the caller's `HarnessCapabilityError` message.
    """
    if not source.is_file():
        raise HarnessCapabilityError(f"--codex-auth-file {source} is not a regular file")
    codex_home.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
    os.chmod(codex_home, stat.S_IRWXU)
    target = codex_home / "auth.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "wb") as dest, source.open("rb") as src:
            shutil.copyfileobj(src, dest)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def _isolate_probe(
    probe: BehavioralProbe,
    *,
    workspace: Path,
    executable: str,
    codex_auth_file: Path | None = None,
) -> tuple[BehavioralProbe, Path | None]:
    """Bind a plan command to the runtime's isolated profile and workspace.

    The second return value is the copied `auth.json` path when one was
    installed for this probe, or `None`. The caller deletes it once the
    probe has run so the credential copy never outlives that one probe.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    environment = runtime_env(workspace, probe.harness)
    installed_auth: Path | None = None
    if codex_auth_file is not None and probe.harness == "codex":
        installed_auth = _install_codex_auth(codex_auth_file, Path(environment["CODEX_HOME"]))
    try:
        root = workspace.resolve()
        cwd = root
        if probe.command.cwd is not None:
            requested = probe.command.cwd
            cwd = (root / requested if not requested.is_absolute() else requested).resolve()
            try:
                cwd.relative_to(root)
            except ValueError as exc:
                raise HarnessCapabilityError(
                    f"{probe.harness} behavioral probe cwd escapes its isolated workspace: {cwd}"
                ) from exc
        cwd.mkdir(parents=True, exist_ok=True)
        for key, value in (probe.command.env or {}).items():
            protected_key = next(
                (
                    name
                    for name in _ISOLATED_ENV_KEYS
                    if key == name or (os.name == "nt" and key.casefold() == name.casefold())
                ),
                None,
            )
            if protected_key is not None and (
                key != protected_key or value != environment.get(protected_key)
            ):
                raise HarnessCapabilityError(
                    f"{probe.harness} behavioral probe cannot override isolated environment {key}"
                )
            environment[key] = value
    except BaseException:
        if installed_auth is not None:
            installed_auth.unlink(missing_ok=True)
        raise
    isolated = replace(
        probe,
        command=replace(
            probe.command,
            argv=(executable, *probe.command.argv[1:]),
            cwd=cwd,
            env=environment,
        ),
    )
    return isolated, installed_auth


def _augment_versions(
    records: list[HarnessCapabilityRecord],
    *,
    output: Path,
    copilot_bin: str,
    timeout: float,
    runner: Runner,
) -> list[HarnessCapabilityRecord]:
    """Fill live runtime versions where the CLI is installed and probe-capable.

    A probe failure leaves the record at its checked-in UNVERIFIED version.
    UNVERIFIED is the restrictive default here, so continuing on failure never
    upgrades a claim; it only declines to.
    """
    augmented: list[HarnessCapabilityRecord] = []
    for record in records:
        probe_name = PROBE_HARNESS.get(record.harness)
        executable = _probe_bin(record.harness, copilot_bin)
        if probe_name is None or _canonical_executable(executable) is None:
            augmented.append(record)
            continue
        try:
            version = probe_version(
                executable,
                probe_name,
                output.parent / "version-probes" / record.harness,
                runner,
                timeout,
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            augmented.append(record)
            continue
        augmented.append(apply_version_probe(record, version))
    return augmented


def _run_behavioral_probe(
    probe: BehavioralProbe,
    *,
    executable_allowlist: Mapping[str, Path],
    runner: Runner,
    timeout: float,
) -> Capability:
    if probe.capability in OVERRIDE_CAPABILITIES:
        if probe.parent_value is None or probe.child_value is None:
            raise HarnessCapabilityError(
                f"{probe.harness}.{probe.capability} is missing override values"
            )
        plan = build_override_plan(
            capability=probe.capability,
            harness=probe.harness,
            parent_value=probe.parent_value,
            candidates=(probe.child_value,),
        )
        return probe_override(
            plan,
            probe.command,
            runner=runner,
            timeout=timeout,
            executable_allowlist=executable_allowlist,
        )
    if probe.capability == "subagent_support":
        return probe_subagent_support(
            probe.command,
            runner=runner,
            timeout=timeout,
            executable_allowlist=executable_allowlist,
        )
    if probe.requested is None:
        raise HarnessCapabilityError(
            f"{probe.harness}.{probe.capability} is missing requested concurrency"
        )
    return probe_concurrency(
        probe.command,
        requested=probe.requested,
        runner=runner,
        timeout=timeout,
        executable_allowlist=executable_allowlist,
    )


def _augment_behavioral(
    records: list[HarnessCapabilityRecord],
    *,
    probes: Sequence[BehavioralProbe],
    output: Path,
    copilot_bin: str,
    timeout: float,
    runner: Runner,
    codex_auth_file: Path | None = None,
) -> list[HarnessCapabilityRecord]:
    """Run live probes through the configured executable and isolated profile."""
    by_harness = {record.harness: record for record in records}
    probe_date = date.today().isoformat()
    for probe_index, probe in enumerate(probes):
        if probe.harness not in by_harness:
            raise HarnessCapabilityError(
                f"behavioral probe targets unknown harness: {probe.harness}"
            )
        record = by_harness[probe.harness]
        if record.version_evidence is not EvidenceKind.BACKEND or not record.version:
            continue
        executable = _probe_bin(probe.harness, copilot_bin)
        expected = _canonical_executable(executable)
        if expected is None:
            continue
        # A fresh directory per run, never a reused `probe-<n>`: a run killed
        # before its `finally` leaves `auth.json` behind, and the exclusive
        # create in `_install_codex_auth` would then refuse every later run.
        # Two concurrent invocations also never share a credential copy.
        harness_root = output.parent / "behavioral-probes" / probe.harness
        harness_root.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix=f"probe-{probe_index}-", dir=harness_root))
        isolated_probe, installed_auth = _isolate_probe(
            probe,
            workspace=workspace,
            executable=executable,
            codex_auth_file=codex_auth_file,
        )
        try:
            result = _run_behavioral_probe(
                isolated_probe,
                executable_allowlist={probe.harness: expected},
                runner=runner,
                timeout=timeout,
            )
        finally:
            if installed_auth is not None:
                installed_auth.unlink(missing_ok=True)
        by_harness[probe.harness] = apply_behavioral_probe(
            record,
            probe.capability,
            result,
            reported_value=probe.child_value,
            probe_command=shlex.join(isolated_probe.command.argv),
            date=probe_date,
        )
    return [by_harness[record.harness] for record in records]


def run(
    *,
    matrix_path: Path,
    output: Path,
    copilot_bin: str,
    timeout: float,
    dry_run: bool,
    runner: Runner,
    behavioral_probes: Path | None = None,
    codex_auth_file: Path | None = None,
) -> dict[str, object]:
    """Load the matrix, validate plans, and optionally run live probes."""
    records = load_matrix(matrix_path)
    probes = load_behavioral_probes(behavioral_probes) if behavioral_probes is not None else ()
    # Checked before any CLI runs, so a bad path cannot let version probes and
    # earlier copilot probes spend a live run first. A plan with no codex
    # probe ignores the option.
    if (
        codex_auth_file is not None
        and any(probe.harness == "codex" for probe in probes)
        and not codex_auth_file.is_file()
    ):
        raise HarnessCapabilityError(f"--codex-auth-file {codex_auth_file} is not a regular file")
    if not dry_run:
        records = _augment_versions(
            records,
            output=output,
            copilot_bin=copilot_bin,
            timeout=timeout,
            runner=runner,
        )
        if behavioral_probes is not None:
            records = _augment_behavioral(
                records,
                probes=probes,
                output=output,
                copilot_bin=copilot_bin,
                timeout=timeout,
                runner=runner,
                codex_auth_file=codex_auth_file,
            )
    report: dict[str, object] = build_report(records)
    if not dry_run:
        write_report(output, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--copilot-bin", default="copilot")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--behavioral-probes",
        type=Path,
        help="JSON plan of live behavioral probe commands",
    )
    parser.add_argument(
        "--codex-auth-file",
        type=Path,
        default=None,
        help=(
            "Opt-in: copy this ChatGPT auth.json into each codex probe's isolated "
            "CODEX_HOME. Ignored for non-codex probes."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _default_output() -> Path:
    return REPO_ROOT / "artifacts" / "harness-capability" / "report.json"


def main(argv: Sequence[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    if not (args.timeout > 0):
        print("Error: --timeout must be greater than zero.", file=sys.stderr)
        return EXIT_CONFIG
    # Path.resolve() touches the filesystem, so it fails the same ways the run
    # does. A relative path resolves through os.getcwd(), which raises
    # FileNotFoundError once the working directory has been removed. Resolving
    # outside this block let that escape as a traceback instead of the exit
    # contract below.
    try:
        output = (args.output or _default_output()).resolve()
        behavioral_probes = args.behavioral_probes.resolve() if args.behavioral_probes else None
        codex_auth_file = args.codex_auth_file.resolve() if args.codex_auth_file else None
        report = run(
            matrix_path=args.matrix.resolve(),
            output=output,
            copilot_bin=args.copilot_bin,
            timeout=args.timeout,
            dry_run=args.dry_run,
            runner=runner,
            behavioral_probes=behavioral_probes,
            codex_auth_file=codex_auth_file,
        )
    except HarnessCapabilityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(json.dumps(report, indent=2))
    if not args.dry_run:
        print(f"Report: {output}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
