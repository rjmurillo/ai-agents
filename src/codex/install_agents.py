#!/usr/bin/env python3
"""Install the project-toolkit Codex agents into a Codex agents directory.

Codex loads custom agents from ``.codex/agents/*.toml`` (project) or
``$CODEX_HOME/agents/*.toml`` (user). A Codex plugin cannot ship agents, so
this script copies the generated files from ``agents/`` next to it. It works
from a clone (``src/codex/``) and from the plugin cache
(``$CODEX_HOME/plugins/cache/<marketplace>/project-toolkit/<version>/``)
because it finds ``agents/`` relative to its own path.

Ownership: ``<target>/.project-toolkit-agents.json`` records the SHA-256 of
every file this script wrote. A file is overwritten, upgraded or removed only
while its hash still equals the recorded one. A same-named file that is not
owned is a conflict: the default is to write nothing and exit 1;
``--namespace PREFIX`` installs it as ``PREFIX-<name>`` instead.

Write order: agent files first, the ownership file last (atomic replace). An
unrecorded target file whose bytes equal the shipped bytes is adopted, so a
crash between the two steps heals on the next run.

Exit codes: 0 success, 1 conflict or refusal (nothing written), 2 usage or
configuration error.

Stdlib only. ``tomllib`` (Python 3.11+) is used when present to verify a
namespaced rewrite and to read the Codex trust list.
"""

from __future__ import annotations

import argparse
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
EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 1, 2


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
    counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(
            ("installed", "updated", "adopted", "removed", "conflicts", "skipped"), 0
        )
    )
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    record: Ownership = field(default_factory=Ownership)

    def note(self, kind: str, name: str, text: str) -> None:
        self.counts[kind] += 1
        self.lines.append(f"  {kind}: {name}{text}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: object) -> bool:
    """True for a plain ``*.toml`` base name: no separator, no dot segment."""
    return (
        isinstance(name, str)
        and name.endswith(AGENT_SUFFIX)
        and name == Path(name).name
        and not name.startswith(".")
        and "\\" not in name
    )


def read_ownership(target: Path) -> Ownership:
    path = target / OWNERSHIP_FILE
    if not path.is_file():
        return Ownership()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        files, sources = data["files"], data.get("namespaced", {})
        ok = isinstance(files, dict) and isinstance(sources, dict)
        ok = ok and all(_safe_name(k) and isinstance(v, str) for k, v in files.items())
        ok = ok and all(_safe_name(k) and _safe_name(v) for k, v in sources.items())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise InstallError(f"unreadable ownership file {path}: {exc}") from exc
    if not ok:
        raise InstallError(f"malformed ownership file {path}")
    return Ownership(dict(files), dict(sources))


def load_shipped(agents_dir: Path) -> dict[str, bytes]:
    if not agents_dir.is_dir():
        raise InstallError(f"agents directory not found: {agents_dir}")
    shipped = {p.name: p.read_bytes() for p in sorted(agents_dir.glob(f"*{AGENT_SUFFIX}"))}
    if not shipped:
        raise InstallError(f"no {AGENT_SUFFIX} agents under {agents_dir}")
    return shipped


def namespaced_bytes(data: bytes, prefix: str, file_name: str) -> bytes:
    """Return ``data`` with the ``name`` line prefixed; verify the result parses."""
    text = data.decode("utf-8")
    match = _NAME_LINE.match(text)
    if match is None:
        raise InstallError(f'{file_name}: first line is not `name = "..."`')
    new_name = f"{prefix}-{match.group(1)}"
    rewritten = f'name = "{new_name}"\n' + text[match.end() :]
    if tomllib is not None:
        try:
            tomllib.loads(rewritten)
        except tomllib.TOMLDecodeError as exc:
            raise InstallError(f"{file_name}: namespaced rewrite is invalid TOML: {exc}") from exc
    return rewritten.encode("utf-8")


def _disk_hash(path: Path) -> str | None:
    """Hash of the file at ``path``; ``None`` when absent. A symlink hashes as its own marker."""
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return sha256_hex(path.read_bytes())
    # A directory or other non-file under an agent name is never ours: a conflict.
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


def _plan_namespaced(
    plan: Plan, target: Path, name: str, data: bytes, owned: Ownership, prefix: str
) -> None:
    ns_name = f"{prefix}-{name}"
    ns_data = namespaced_bytes(data, prefix, name)
    if _decide(plan, target, ns_name, ns_data, owned, source=name):
        plan.lines[-1] += f"  (namespaced from {name} to avoid a conflict)"
        agent = name[: -len(AGENT_SUFFIX)]
        plan.warnings.append(
            f"other shipped agents hand work to `{agent}`; that name still reaches your own "
            f"`{agent}` agent, not `{prefix}-{agent}`"
        )
    else:
        plan.conflicts.append(f"{ns_name} (namespaced name of {name}) exists and is not owned")


def _plan_owned_leftovers(
    plan: Plan, target: Path, shipped: dict[str, bytes], owned: Ownership
) -> None:
    """Handle recorded files the install loop did not decide: dropped or namespaced ones."""
    for name in sorted(set(owned.files) - set(plan.record.files)):
        source = owned.sources.get(name)
        current = _disk_hash(target / name)
        if current is None:
            if source in shipped:
                # The user deleted a namespaced copy while its source still clashes:
                # reinstall it, so two identical runs give the same answer.
                prefix = name[: -len(source) - 1]
                data = namespaced_bytes(shipped[source], prefix, source)
                _decide(plan, target, name, data, owned, source)
            continue
        if current != owned.files[name]:
            plan.warnings.append(f"{name} was edited after install; leaving it and its record")
            plan.record.files[name] = owned.files[name]
            if source:
                plan.record.sources[name] = source
            continue
        if source in shipped:
            prefix = name[: -len(source) - 1]
            _decide(
                plan, target, name, namespaced_bytes(shipped[source], prefix, source), owned, source
            )
            continue
        plan.removes.append(name)
        plan.note("removed", name, " (no longer shipped)")


def build_install_plan(
    shipped: dict[str, bytes], target: Path, owned: Ownership, namespace: str | None
) -> Plan:
    plan = Plan()
    for name, data in shipped.items():
        if _decide(plan, target, name, data, owned):
            continue
        if name in owned.sources.values():
            continue  # an earlier --namespace run owns this agent; the leftover pass upgrades it
        plan.counts["conflicts"] += 1
        if namespace is None:
            plan.conflicts.append(f"{name} exists and is not owned by this installer")
        else:
            _plan_namespaced(plan, target, name, data, owned, namespace)
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
            plan.warnings.append(f"{name} was edited after install; leaving it")
            plan.record.files[name] = recorded
            if name in owned.sources:
                plan.record.sources[name] = owned.sources[name]
    return plan


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def apply_plan(plan: Plan, target: Path) -> None:
    """Write agent files and removals first, the ownership file last."""
    for name, data in plan.writes.items():
        _atomic_write(target / name, data)
    for name in plan.removes:
        (target / name).unlink(missing_ok=True)
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
    why = f"{project} is not a trusted project in {config}"
    if tomllib is None:
        return (
            "cannot check the Codex trust list (needs Python 3.11+); confirm the project is trusted"
        )
    try:
        projects = tomllib.loads(config.read_text(encoding="utf-8")).get("projects", {})
    except (OSError, tomllib.TOMLDecodeError):
        return f"{config} is missing or unreadable, so {project} is not a trusted project"
    for candidate in {str(project), str(project.resolve())}:
        entry = projects.get(candidate) if isinstance(projects, dict) else None
        if isinstance(entry, dict) and entry.get("trust_level") == "trusted":
            return None
    return why


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install project-toolkit agents for Codex.")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--project", metavar="DIR", help="project directory (default: cwd)")
    where.add_argument("--user", action="store_true", help="install into $CODEX_HOME/agents")
    parser.add_argument("--namespace", metavar="PREFIX", help="install conflicts as PREFIX-<name>")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument("--uninstall", action="store_true", help="remove files this tool installed")
    return parser


def resolve_target(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Return ``(agents dir, project dir or None)``."""
    if args.user:
        return codex_home() / "agents", None
    project = Path(args.project or Path.cwd()).absolute()
    return project / ".codex" / "agents", project


def _report(plan: Plan, label: str) -> None:
    print(label)
    for line in plan.lines:
        print(line)
    for warning in plan.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    counts = ", ".join(f"{key} {value}" for key, value in plan.counts.items())
    print(f"Summary: {counts}")


def run(args: argparse.Namespace, agents_dir: Path) -> int:
    target, project = resolve_target(args)
    owned = read_ownership(target)
    if args.uninstall:
        plan = build_uninstall_plan(target, owned)
    else:
        plan = build_install_plan(load_shipped(agents_dir), target, owned, args.namespace)
    if plan.conflicts:
        for conflict in plan.conflicts:
            print(f"CONFLICT: {conflict}", file=sys.stderr)
        print(
            "Nothing written. Resolve the conflicts or rerun with --namespace PREFIX.",
            file=sys.stderr,
        )
        print(f"Refused for {target}: conflicts {len(plan.conflicts)}, nothing written")
        return EXIT_REFUSED
    if project is not None and not args.uninstall:
        warning = trust_warning(project)
        if warning:
            plan.warnings.append(f"Codex loads project agents only for trusted projects: {warning}")
    mode = "Plan (dry run)" if args.dry_run else "Applied"
    if not args.dry_run:
        apply_plan(plan, target)
    _report(plan, f"{mode} for {target}:")
    return EXIT_OK


def main(argv: list[str] | None = None, agents_dir: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.namespace is not None and not PREFIX_PATTERN.match(args.namespace):
        parser.error(f"--namespace must match {PREFIX_PATTERN.pattern}")
    if args.namespace is not None and args.uninstall:
        parser.error("--namespace has no meaning with --uninstall")
    try:
        return run(args, agents_dir or Path(__file__).resolve().parent / "agents")
    except InstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
