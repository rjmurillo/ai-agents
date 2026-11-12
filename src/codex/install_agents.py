#!/usr/bin/env python3
# taste-lint: ignore file-size, one file because it runs under `python -I` with no sibling imports.
"""Install the project-toolkit Codex agents into a Codex agents directory.

Codex loads custom agents from ``.codex/agents/*.toml`` (project) or
``$CODEX_HOME/agents/*.toml`` (user); a plugin cannot ship them. This script
copies the files from the ``agents/`` folder next to it. It must stay one file:
the smoke runs it with ``python -I``, which does not put its folder on sys.path.

``<target>/.project-toolkit-agents.json`` records the SHA-256 of each file the
script wrote; a file is upgraded or removed only while it still matches. An
unowned same-named file is a conflict (exit 1, nothing written) unless
``--namespace PREFIX`` installs it as ``PREFIX-<name>``. Agent files are written
first and the ownership file last, so a crash heals on rerun (identical
unrecorded files are adopted). Exit codes: 0 ok, 1 conflict, 2 usage or
configuration error, 3 file system error. Stdlib only; ``tomllib`` is optional.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

try:
    tomllib: ModuleType | None = importlib.import_module("tomllib")
except ImportError:  # Python 3.10
    tomllib = None

OWNERSHIP_FILE = ".project-toolkit-agents.json"
AGENT_SUFFIX = ".toml"
PREFIX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_NAME_LINE = re.compile(r'^name = "([^"\n]*)"\n')
EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_IO = 0, 1, 2, 3
_KINDS = ("installed", "updated", "adopted", "removed", "skipped")


class InstallError(Exception):
    """A usage or configuration problem (exit 2)."""


@dataclass
class Ownership:
    """What a previous run recorded: file hashes and namespaced-file sources."""

    files: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> str:
        data: dict[str, object] = {"files": dict(sorted(self.files.items()))}
        if self.sources:
            data["namespaced"] = dict(sorted(self.sources.items()))
        return json.dumps(data, indent=2) + "\n"


@dataclass
class Plan:
    """Decided actions. ``writes`` maps file name to new bytes."""

    writes: dict[str, bytes] = field(default_factory=dict)
    removes: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_KINDS, 0))
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    record: Ownership = field(default_factory=Ownership)
    shipped_ours: set[str] = field(default_factory=set)  # plain names decided from shipped files

    def note(self, kind: str, name: str, text: str) -> None:
        self.counts[kind] += 1
        self.lines.append(f"  {kind}: {name}{text}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _safe_name(name: object) -> bool:
    """True for a ``*.toml`` base name of ``[A-Za-z0-9._-]`` (the ownership file is untrusted)."""
    return (
        isinstance(name, str)
        and name.endswith(AGENT_SUFFIX)
        and _SAFE_NAME.fullmatch(name) is not None
    )


def _is_sha256(value: object) -> bool:
    """True for lowercase SHA-256 hex; disk markers such as ``symlink`` never match."""
    return isinstance(value, str) and _SHA256_HEX.fullmatch(value) is not None


def namespaced_file_name(prefix: str, file_name: str) -> str:
    """The file name a ``--namespace`` install gives ``file_name``: ``<prefix>-<file_name>``."""
    return f"{prefix}-{file_name}"


def namespace_prefix_of(ns_name: str, source: str) -> str:
    """Inverse of :func:`namespaced_file_name`; ``ns_name`` must end in ``-<source>``."""
    return ns_name[: -len(source) - 1]


def _valid_namespaced(file_name: object, source: object) -> bool:
    """True when ``file_name`` is exactly ``<valid prefix>-<source>`` for a safe ``source``."""
    if not (isinstance(file_name, str) and isinstance(source, str)):
        return False
    if not (_safe_name(file_name) and _safe_name(source) and file_name.endswith(f"-{source}")):
        return False
    return PREFIX_PATTERN.fullmatch(namespace_prefix_of(file_name, source)) is not None


def read_ownership(target: Path) -> Ownership:
    path = target / OWNERSHIP_FILE
    if path.is_symlink():
        raise InstallError(f"ownership file is a symlink: {path}")
    if not path.exists():
        return Ownership()
    if not path.is_file():
        raise InstallError(f"ownership path is not a regular file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        files, sources = data["files"], data.get("namespaced", {})
        ok = isinstance(files, dict) and isinstance(sources, dict)
        ok = ok and all(_safe_name(k) and _is_sha256(v) for k, v in files.items())
        ok = ok and all(_valid_namespaced(k, v) and k in files for k, v in sources.items())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise InstallError(f"unreadable ownership file {path}: {exc}") from exc
    if not ok:
        raise InstallError(f"malformed ownership file {path}")
    return Ownership(dict(files), dict(sources))


def load_shipped(agents_dir: Path) -> dict[str, bytes]:
    shipped = {p.name: p.read_bytes() for p in sorted(agents_dir.glob(f"*{AGENT_SUFFIX}"))}
    if not shipped:
        raise InstallError(f"no {AGENT_SUFFIX} agents under {agents_dir}")
    for name, data in shipped.items():  # refuse to copy a file Codex could not parse
        try:
            text = data.decode("utf-8")
            if tomllib is not None:
                tomllib.loads(text)
        except ValueError as exc:
            raise InstallError(f"{name}: not a valid TOML agent file: {exc}") from exc
    return shipped


def namespaced_bytes(data: bytes, prefix: str, file_name: str) -> bytes:
    """Return ``data`` with the ``name`` line set to ``<prefix>-<stem>``.

    The name comes only from the validated prefix and the shipped stem, and the
    result is parsed with ``tomllib`` (when available) to check it.
    """
    if PREFIX_PATTERN.fullmatch(prefix) is None:
        raise InstallError(f"invalid namespace prefix: {prefix!r}")
    if not _safe_name(file_name):
        raise InstallError(f"unsafe agent file name: {file_name!r}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError(f"{file_name}: not valid UTF-8: {exc.reason}") from exc
    match = _NAME_LINE.match(text)
    if match is None:
        raise InstallError(f'{file_name}: first line is not `name = "..."`')
    new_name = namespaced_file_name(prefix, file_name[: -len(AGENT_SUFFIX)])
    rewritten = f'name = "{new_name}"\n' + text[match.end() :]
    if tomllib is not None:
        try:
            parsed_name = tomllib.loads(rewritten).get("name")
        except tomllib.TOMLDecodeError:
            parsed_name = None
        if parsed_name != new_name:
            raise InstallError(f"{file_name}: namespaced rewrite is invalid TOML or misnamed")
    return rewritten.encode("utf-8")


def _disk_hash(path: Path) -> str | None:
    """Hash of the file at ``path``; ``None`` when absent. A symlink hashes as its own marker."""
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return sha256_hex(path.read_bytes())
    return "not-a-file" if path.exists() else None


def _decide(
    plan: Plan, target: Path, name: str, data: bytes, owned: Ownership, source: str | None = None
) -> bool:
    """Plan one file. Returns False when ``name`` is occupied by something not ours."""
    new_hash = sha256_hex(data)
    current = _disk_hash(target / name)
    recorded = owned.files.get(name)
    if current is None:
        plan.writes[name] = data
        plan.note("installed", name, "")
    elif current == new_hash:
        adopted = recorded != new_hash
        plan.note("adopted" if adopted else "skipped", name, "" if adopted else " (current)")
    elif recorded is not None and current == recorded:
        plan.writes[name] = data
        plan.note("updated", name, "")
    else:
        return False
    plan.record.files[name] = new_hash
    if source is not None:
        plan.record.sources[name] = source
    return True


def _warn_handoff(plan: Plan, name: str, prefix: str) -> None:
    agent = name[: -len(AGENT_SUFFIX)]
    plan.warnings.append(
        f"other shipped agents hand work to `{agent}`; that name still reaches your own "
        f"`{agent}` agent, not `{namespaced_file_name(prefix, agent)}`"
    )


def _plan_namespaced(
    plan: Plan,
    target: Path,
    name: str,
    data: bytes,
    owned: Ownership,
    prefix: str,
    taken: set[str],
) -> None:
    ns_name = namespaced_file_name(prefix, name)
    if ns_name in taken:
        plan.conflicts.append(f"{ns_name} (namespaced name of {name}) is also a shipped agent")
        return
    ns_data = namespaced_bytes(data, prefix, name)
    if _decide(plan, target, ns_name, ns_data, owned, source=name):
        plan.lines[-1] += f"  (namespaced from {name} to avoid a conflict)"
        _warn_handoff(plan, name, prefix)
    else:
        plan.conflicts.append(f"{ns_name} (namespaced name of {name}) exists and is not owned")


def _prior_namespaced_copy(target: Path, name: str, owned: Ownership) -> str | None:
    """Return the recorded ``--namespace`` copy of ``name`` that is still on disk, else ``None``.

    A recorded entry alone proves nothing: the ownership file can be committed by
    a repository author. The copy has to exist before it excuses a plain-name clash.
    """
    for ns_name, source in sorted(owned.sources.items()):
        if source == name and _disk_hash(target / ns_name) not in (None, "symlink", "not-a-file"):
            return ns_name
    return None


def _conflict_text(target: Path, name: str, owned: Ownership) -> str:
    """Say why ``name`` blocks the install, so the remedy is clear."""
    current = _disk_hash(target / name)
    if current == "symlink":
        return f"{name} is a symlink; remove it or use --namespace"
    if current == "not-a-file":
        return f"{name} is not a regular file; remove it or use --namespace"
    if name in owned.files:
        return f"{name} was edited after install; restore it, delete it, or use --namespace"
    return f"{name} exists and is not owned by this installer"


def _keep_edited(plan: Plan, name: str, owned: Ownership) -> None:
    """Leave a recorded file the user edited, and keep its record."""
    plan.warnings.append(f"{name} was edited after install; leaving it and its record")
    plan.record.files[name] = owned.files[name]
    if name in owned.sources:
        plan.record.sources[name] = owned.sources[name]


def _plan_owned_leftovers(
    plan: Plan, target: Path, shipped: dict[str, bytes], owned: Ownership
) -> None:
    """Handle recorded files the install loop did not decide: dropped or namespaced ones.

    A namespaced copy follows its source: upgraded while the source still clashes,
    removed once the plain agent is ours again. An edited file is always kept.
    """
    for name in sorted(set(owned.files) - set(plan.record.files)):
        source = owned.sources.get(name)
        current = _disk_hash(target / name)
        if current is None:
            plan.lines.append(f"  dropped: {name} (deleted by the user, not restored)")
            continue
        follows_source = source in shipped and source not in plan.shipped_ours
        wanted = (
            namespaced_bytes(shipped[source], namespace_prefix_of(name, source), source)
            if follows_source and source is not None
            else None
        )
        # An interrupted upgrade leaves the new bytes on disk and the old hash on record.
        interrupted = wanted is not None and current == sha256_hex(wanted)
        if current != owned.files[name] and not interrupted:
            _keep_edited(plan, name, owned)
        elif wanted is not None and source is not None:
            _decide(plan, target, name, wanted, owned, source)
        else:
            plan.removes.append(name)
            reason = "no longer shipped" if source not in shipped else "plain agent is installed"
            plan.note("removed", name, f" ({reason})")


def build_install_plan(
    shipped: dict[str, bytes], target: Path, owned: Ownership, namespace: str | None
) -> Plan:
    plan = Plan()
    taken = set(shipped)
    for name, data in shipped.items():
        if _decide(plan, target, name, data, owned):
            plan.shipped_ours.add(name)
            continue
        prior = _prior_namespaced_copy(target, name, owned)
        # An earlier --namespace run owns this agent; the leftover pass upgrades it.
        if prior is not None:
            prefix = namespace_prefix_of(prior, name)
            _warn_handoff(plan, name, prefix)
            if namespace is not None and namespace != prefix:
                plan.warnings.append(
                    f"{name} stays installed as {prior}; --namespace {namespace} was not applied"
                )
            continue
        if namespace is None:
            plan.conflicts.append(_conflict_text(target, name, owned))
        else:
            _plan_namespaced(plan, target, name, data, owned, namespace, taken)
    _plan_owned_leftovers(plan, target, shipped, owned)
    return plan


def build_uninstall_plan(target: Path, owned: Ownership) -> Plan:
    plan = Plan()
    for name, recorded in sorted(owned.files.items()):
        current = _disk_hash(target / name)
        if current is None:
            continue
        if current == recorded:
            plan.removes.append(name)
            plan.note("removed", name, "")
        else:
            _keep_edited(plan, name, owned)
    return plan


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)  # mkstemp creates 0600; agents are not secrets
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _sync_dir(path: Path) -> None:
    """Flush directory entries so the renames persist before the ownership file is written."""
    if not hasattr(os, "O_DIRECTORY"):
        return  # Windows has no directory fsync
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
            raise  # a real I/O error; only "this file system cannot sync a directory" is excused
    finally:
        os.close(fd)


def apply_plan(plan: Plan, target: Path) -> None:
    """Write agent files and removals first, the ownership file last."""
    for name, data in plan.writes.items():
        _atomic_write(target / name, data)
    for name in plan.removes:
        (target / name).unlink(missing_ok=True)
    if plan.writes or plan.removes:
        _sync_dir(target)
    ownership = target / OWNERSHIP_FILE
    if plan.record.files:
        _atomic_write(ownership, plan.record.as_json().encode("utf-8"))
    else:
        ownership.unlink(missing_ok=True)


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def trust_warning(project: Path) -> str | None:
    """Return a warning when Codex will not load agents from ``project``, else ``None``."""
    config = codex_home() / "config.toml"
    if tomllib is None:
        return "cannot check the trust list without Python 3.11+; confirm the project is trusted"
    try:
        projects = tomllib.loads(config.read_text(encoding="utf-8")).get("projects", {})
    except (OSError, ValueError):  # ValueError covers bad UTF-8 and TOMLDecodeError
        return f"{config} is missing or unreadable, so {project} is not a trusted project"
    for candidate in {str(project), str(project.resolve())}:
        entry = projects.get(candidate) if isinstance(projects, dict) else None
        if isinstance(entry, dict) and entry.get("trust_level") == "trusted":
            return None
    return f"{project} is not a trusted project in {config}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install project-toolkit agents for Codex.")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--project", metavar="DIR", help="project directory (default: cwd)")
    where.add_argument("--user", action="store_true", help="install into $CODEX_HOME/agents")
    parser.add_argument("--namespace", metavar="PREFIX", help="install conflicts as PREFIX-<name>")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument("--uninstall", action="store_true", help="remove files this tool installed")
    return parser


def _is_link(path: Path) -> bool:
    """True for a symlink or a Windows junction. ``is_symlink`` alone misses a junction."""
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
    if isjunction is not None:
        return bool(isjunction(path))
    try:  # Python 3.10 and 3.11: only Windows sets st_file_attributes; 0x400 is a reparse point
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False
    except OSError:
        return True  # an unreadable path is not proven safe, so refuse it


def resolve_target(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Return ``(agents dir, project dir or None)``; refuse a link below the root (CWE-59)."""
    project = None if args.user else Path(args.project or Path.cwd()).absolute()
    if project is not None and not project.is_dir():
        raise InstallError(f"project directory does not exist: {project}")
    root, parts = (
        (codex_home(), ("agents",)) if project is None else (project, (".codex", "agents"))
    )
    current = root
    for part in parts:
        current = current / part
        if _is_link(current):
            raise InstallError(f"refusing to write through a symlink or junction: {current}")
    return current, project


def run(args: argparse.Namespace, agents_dir: Path) -> int:
    target, project = resolve_target(args)
    owned = read_ownership(target)
    if args.uninstall:
        plan = build_uninstall_plan(target, owned)
    else:
        plan = build_install_plan(load_shipped(agents_dir), target, owned, args.namespace)
    if args.uninstall and not owned.files:
        print(f"No ownership file with recorded agents at {target}; nothing to remove.")
        print("Check that --project or --user matches the install.")
        return EXIT_OK
    if plan.conflicts:
        for conflict in plan.conflicts:
            print(f"CONFLICT: {conflict}", file=sys.stderr)
        print("Nothing written. Resolve the conflicts or rerun with --namespace.", file=sys.stderr)
        print(f"Refused for {target}: conflicts {len(plan.conflicts)}, nothing written")
        return EXIT_REFUSED
    if project is not None and not args.uninstall:
        warning = trust_warning(project)
        if warning:
            plan.warnings.append(f"Codex loads project agents only for trusted projects: {warning}")
    mode = "Plan (dry run)" if args.dry_run else "Applied"
    if not args.dry_run:
        apply_plan(plan, target)
    print(f"{mode} for {target}:", *plan.lines, sep="\n")
    for warning in plan.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print("Summary: " + ", ".join(f"{key} {value}" for key, value in plan.counts.items()))
    return EXIT_OK


def main(argv: list[str] | None = None, agents_dir: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.namespace is not None and not PREFIX_PATTERN.fullmatch(args.namespace):
        parser.error(f"--namespace must match {PREFIX_PATTERN.pattern}")
    if args.namespace is not None and args.uninstall:
        parser.error("--namespace cannot be used with --uninstall")
    try:
        return run(args, agents_dir or Path(__file__).resolve().parent / "agents")
    except (InstallError, ValueError, RuntimeError) as exc:
        # ValueError: undecodable shipped file; RuntimeError: no home directory to resolve.
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"Error: {exc.filename or 'file system'}: {exc.strerror or exc}", file=sys.stderr)
        print(
            "Some agent files may be written. Rerun to repair; matching files are adopted.",
            file=sys.stderr,
        )
        return EXIT_IO


if __name__ == "__main__":
    sys.exit(main())
