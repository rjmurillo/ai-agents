#!/usr/bin/env python3
"""Source-parity gate: the three hand-written members of each agent must agree.

After ADR-109 B1 every agent output tree is generated, but each agent still has
three independently written sources under ``templates/agents/``:

- ``<stem>.shared.md``: the VS Code input and the governance reference body.
- ``<stem>.claude.md.tmpl``: renders to ``src/claude/agents/<stem>.md``.
- ``<stem>.copilot.md.tmpl``: renders to the Copilot CLI and GitHub trees.

Nothing compared their content before this gate. ``detect_agent_drift.py`` scores
a word-set overlap on a section allowlist of the rendered outputs, and a
contradiction that reuses the surrounding vocabulary passes it. This gate
compares the sources themselves and fails on any difference the normalization
contract does not excuse. ADR-107 migration step M3, issue #5688.

NORMALIZATION CONTRACT (predicate ``normalized``, ADR-107 section 4). The
authoritative statement is the "Agent source equivalence" section of
``.agents/governance/GENERATOR-FILES.md``; this module implements it.

Pairs compared, each against ``<stem>.shared.md``:

- ``claude-shared``: the rendered Claude template.
- ``copilot-shared``: the rendered Copilot template. Strict: an H2 section on
  one side only is a divergence, because both feed the same platform family.

Tree-specific, dropped from comparison: every frontmatter key outside
``SHARED_FRONTMATTER_KEYS`` and the tool lists (``name``, ``model``,
``model_tier``, ``isolation_required``, ``metadata`` other than
``metadata.role``), and for the Claude pair an H2 section present on only one
side (section inventory stays with ``detect_agent_drift.py``).

Shared, compared exactly after ``detect_agent_drift.normalize_content``: the
frontmatter keys ``description``, ``argument-hint`` and ``role`` (Claude spells
``role`` either top level or as ``metadata.role``), the preamble before the
first H2, the body of every H2 section both sides carry, and the order of the H2
sections both sides carry (unit ``order``). The normalization
rewrites MCP tool prefixes, handoff invocation spelling, fence language tags,
and whitespace, and it ignores blank lines. A repeated H2 name in one source is a
ConfigError, because a repeat would hide the earlier body. It never drops a text
line, reorders a step, or edits a number, so invariants 1 to 5, 7 and 8 stay in
the compared text: ordered steps, completion criteria, evidence requirements,
failure states, approval gates, idempotence and rollback statements, and the
exit-code contract.

Invariant 6, authorization and the abstract capability set, lives in the tool
lists. Only the platform spelling is excused. ``agent_capabilities.py`` reduces
each list to abstract capabilities (``Read`` and ``read``, ``Bash`` and
``shell``, ``mcp__github__issue_read`` and ``github/issue_read``), expands
``$toolset:`` references, and the gate compares those units. The Claude
``tools`` list is compared with the shared ``tools_copilot`` list. The Copilot
template's ``tools_copilot`` and ``tools_vscode`` lists are compared with their
shared twins. A member with no list is ``unrestricted`` (Claude Code gives such
an agent every tool), and it diverges from a ``restricted`` list. An unknown
tool name stays literal and a wildcard is not an explicit tool list, so neither
can hide a difference.

Accepted divergence that predates this gate is pinned in
``.agents/governance/agent-source-divergence.json`` by a digest of both
normalized sides. The pin makes a later edit to either side fail until a
reviewer re-records it, so an injected contradiction cannot hide in an already
divergent unit. A pin whose units now agree is stale and fails, so the file
only shrinks. ``BASELINE_CEILING`` caps its size.

Prose invariants 1 to 5 and 7 bind authors and reviewers, not this gate: no
extractor exists for them (ADR-107 section 5). The gate checks text equality,
not meaning.

CLI::

    uv run python build/scripts/check_agent_source_parity.py
    uv run python build/scripts/check_agent_source_parity.py --format json
    uv run python build/scripts/check_agent_source_parity.py --write-baseline

EXIT CODES (ADR-035)
--------------------
0 - every pair agrees, or differs only where the baseline pins it exactly
1 - a divergence, a changed pin, or a stale pin
2 - configuration error (missing tree, bad baseline, template render failure)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import agent_capabilities  # noqa: E402
import agent_templates  # noqa: E402
from agent_source_report import (  # noqa: E402
    KIND_CHANGED,
    KIND_DIVERGED,
    KIND_MISSING,
    KIND_STALE,
    Finding,
    Key,
    print_json,
    print_text,
    reconcile,
)
from detect_agent_drift import (  # noqa: E402
    get_markdown_section_list,
    normalize_content,
    remove_yaml_frontmatter,
)

__all__ = ["KIND_CHANGED", "KIND_DIVERGED", "KIND_MISSING", "KIND_STALE", "Finding", "Key"]

_T = TypeVar("_T")
EXIT_OK = 0
EXIT_DIVERGED = 1
EXIT_CONFIG = 2

BASELINE_RELATIVE_PATH = Path(".agents") / "governance" / "agent-source-divergence.json"
BASELINE_SCHEMA_VERSION = "1"
# Pinned divergences at the time the gate landed: 62 in prose and 47 in the
# capability set. Raising this needs a code edit, so growth is a reviewed change
# and not a quiet re-record.
BASELINE_CEILING = 109

SHARED_FRONTMATTER_KEYS: tuple[str, ...] = ("description", "argument-hint", "role")
PAIR_CLAUDE = "claude-shared"
PAIR_COPILOT = "copilot-shared"
PAIRS: tuple[str, ...] = (PAIR_CLAUDE, PAIR_COPILOT)
# Capability lists compared per pair, as (template key, shared key, unit prefix).
# The Claude template lists tools in Claude spelling; its counterpart is the
# Copilot CLI list in the shared source. The Copilot template and the shared
# source use one spelling, so each list is compared with its own twin.
CAPABILITY_KEYS: dict[str, tuple[tuple[str, str, str], ...]] = {
    PAIR_CLAUDE: (("tools", "tools_copilot", "capability"),),
    PAIR_COPILOT: (
        ("tools_copilot", "tools_copilot", "capability"),
        ("tools_vscode", "tools_vscode", "capability-vscode"),
    ),
}

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


class ConfigError(Exception):
    """The gate could not run: a tree, template, or baseline is unusable."""


def _digest(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}\0{right}".encode()).hexdigest()


def _frontmatter(text: str) -> dict[str, object]:
    """Return the parsed frontmatter mapping, empty when there is none."""
    match = _FRONTMATTER_RE.match(text.replace("\r\n", "\n"))
    if match is None:
        return {}
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML frontmatter: {exc}") from exc
    return parsed if isinstance(parsed, dict) else {}


def _shared_value(frontmatter: dict[str, object], key: str) -> str:
    """Return one shared key's value as text, '' when absent.

    Claude templates spell ``role`` as ``metadata.role`` for most agents.
    """
    value = frontmatter.get(key)
    if value is None and key == "role":
        metadata = frontmatter.get("metadata")
        value = metadata.get("role") if isinstance(metadata, dict) else None
    return "" if value is None else str(value).strip()


def _normalize(text: str) -> str:
    """Apply the shared normalization, then ignore blank lines."""
    lines = normalize_content(text).splitlines()
    return "\n".join(line for line in lines if line.strip())


def _capability_units(
    frontmatter: dict[str, object],
    capabilities: tuple[tuple[str, str], ...],
    toolsets: dict[str, dict[str, object]],
) -> dict[str, str]:
    units: dict[str, str] = {}
    try:
        for key, prefix in capabilities:
            units.update(agent_capabilities.capability_units(frontmatter, key, prefix, toolsets))
    except agent_capabilities.CapabilityError as exc:
        raise ConfigError(str(exc)) from exc
    return units


def extract_units(
    text: str,
    capabilities: tuple[tuple[str, str], ...] = (),
    toolsets: dict[str, dict[str, object]] | None = None,
) -> dict[str, str]:
    """Return ``{unit: normalized text}`` for every shared unit in one member.

    ``capabilities`` lists ``(frontmatter key, unit prefix)`` tool lists to
    reduce to abstract capability units (``agent_capabilities.py``).
    """
    frontmatter = _frontmatter(text)
    units = _capability_units(frontmatter, capabilities, toolsets or {})
    for key in SHARED_FRONTMATTER_KEYS:
        value = _shared_value(frontmatter, key)
        if value:
            units[f"frontmatter:{key}"] = _normalize(value)
    seen: set[str] = set()
    for name, body in get_markdown_section_list(remove_yaml_frontmatter(text)):
        if name in seen:
            raise ConfigError(
                f"duplicate H2 heading {name!r}: a repeated section would hide "
                "text from the comparison; rename or merge it"
            )
        seen.add(name)
        unit = "preamble" if name == "preamble" else f"section:{name}"
        units[unit] = _normalize(body)
    return units


def diverged_units(
    left: dict[str, str],
    right: dict[str, str],
    *,
    strict: bool,
) -> dict[str, str]:
    """Return ``{unit: digest}`` for each unit the two members disagree on.

    A section on one side only counts only when ``strict`` is set. The
    preamble and the frontmatter keys count in every pair.
    """
    found: dict[str, str] = {}
    for unit in sorted(set(left) | set(right)):
        one_sided = unit not in left or unit not in right
        if one_sided and not strict and unit.startswith("section:"):
            continue
        a, b = left.get(unit, ""), right.get(unit, "")
        if one_sided or a != b:
            found[unit] = _digest(a, b)
    return found


def section_order_divergence(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    """Return ``{"order": digest}`` when shared sections appear in a different order."""
    both = [u for u in left if u.startswith("section:") and u in right]
    in_right = [u for u in right if u in set(both)]
    if both == in_right:
        return {}
    return {"order": _digest("\n".join(both), "\n".join(in_right))}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc


_RENDER_ERRORS = (
    agent_templates.TemplateGrammarError,
    agent_templates.MissingPartialError,
    agent_templates.PartialNewlineError,
    agent_templates.UnresolvedTagError,
)


def _render(tmpl: Path, partials: Path, denylists: dict[str, object] | None = None) -> str:
    try:
        if denylists is None:
            return str(agent_templates.render(tmpl, partials))
        return str(agent_templates.render_claude(tmpl, partials, denylists))
    except (*_RENDER_ERRORS, agent_capabilities.CapabilityError) as exc:
        raise ConfigError(f"cannot render {tmpl}: {exc}") from exc


_MEMBER_SUFFIXES = (".shared.md", ".claude.md.tmpl", ".copilot.md.tmpl")


def _load_config(loader: Callable[[Path], _T], repo_root: Path) -> _T:
    """Run a ``templates/*.yaml`` loader, turning its error into a ConfigError."""
    try:
        return loader(repo_root)
    except agent_capabilities.CapabilityError as exc:
        raise ConfigError(str(exc)) from exc


def _stems(repo_root: Path) -> list[str]:
    agents = repo_root / "templates" / "agents"
    if not agents.is_dir():
        raise ConfigError(f"directory not found: {agents}")
    stems: set[str] = set()
    for suffix in _MEMBER_SUFFIXES:
        stems.update(p.name.removesuffix(suffix) for p in agents.glob(f"*{suffix}"))
    return sorted(stems)


def _compare_stem(
    stem: str,
    shared_text: str,
    claude_tmpl: Path,
    copilot_tmpl: Path,
    partials: Path,
    toolsets: dict[str, dict[str, object]],
    denylists: dict[str, object],
) -> dict[Key, str]:
    """Return the divergences between one agent's shared source and its templates."""
    found: dict[Key, str] = {}
    for pair, tmpl, strict in (
        (PAIR_CLAUDE, claude_tmpl, False),
        (PAIR_COPILOT, copilot_tmpl, True),
    ):
        spec = CAPABILITY_KEYS[pair]
        text = _render(tmpl, partials, denylists if pair == PAIR_CLAUDE else None)
        units = extract_units(text, tuple((own, prefix) for own, _, prefix in spec), toolsets)
        shared_units = extract_units(
            shared_text, tuple((theirs, prefix) for _, theirs, prefix in spec), toolsets
        )
        if pair == PAIR_CLAUDE:
            agent_capabilities.reduce_deny_list_member(
                _frontmatter(text), units, shared_units, "capability"
            )
        agent_capabilities.drop_families_on_declaration_mismatch(units, shared_units)
        diverged = diverged_units(units, shared_units, strict=strict)
        diverged.update(section_order_divergence(units, shared_units))
        found.update({(stem, pair, unit): digest for unit, digest in diverged.items()})
    return found


def collect_divergence(repo_root: Path) -> tuple[dict[Key, str], list[Finding]]:
    """Compare every agent's members. Return divergences and missing-member findings."""
    agents = repo_root / "templates" / "agents"
    pairs = agent_templates.discover(repo_root)
    toolsets = _load_config(agent_capabilities.load_toolsets, repo_root)
    denylists = _load_config(agent_capabilities.load_denylists, repo_root)
    found: dict[Key, str] = {}
    missing: list[Finding] = []
    for stem in _stems(repo_root):
        shared = agents / f"{stem}.shared.md"
        if stem not in pairs or not shared.is_file():
            absent = "shared.md" if stem in pairs else "claude/copilot template pair"
            missing.append(Finding(KIND_MISSING, stem, "-", "-", f"no {absent}"))
            continue
        claude_tmpl, copilot_tmpl = pairs[stem]
        found.update(
            _compare_stem(
                stem,
                _read(shared),
                claude_tmpl,
                copilot_tmpl,
                agents / "partials",
                toolsets,
                denylists,
            )
        )
    return found, missing


def load_baseline(repo_root: Path) -> dict[Key, str]:
    """Return the pinned divergences. A missing file is an empty baseline."""
    path = repo_root / BASELINE_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(_read(path))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    return _parse_baseline(data, path)


def _parse_baseline(data: object, path: Path) -> dict[Key, str]:
    if not isinstance(data, dict) or data.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ConfigError(
            f"{path}: expected an object with schema_version {BASELINE_SCHEMA_VERSION!r}"
        )
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: 'entries' must be a list")
    pinned: dict[Key, str] = {}
    for entry in entries:
        key = _entry_key(entry, path)
        if key in pinned:
            raise ConfigError(f"{path}: duplicate entry {key}")
        pinned[key] = entry["digest"]
    return pinned


def _entry_key(entry: object, path: Path) -> Key:
    fields = ("agent", "pair", "unit", "digest")
    if not isinstance(entry, dict) or not all(isinstance(entry.get(f), str) for f in fields):
        raise ConfigError(f"{path}: each entry needs string fields {fields}")
    if entry["pair"] not in PAIRS:
        raise ConfigError(f"{path}: unknown pair {entry['pair']!r}")
    return (entry["agent"], entry["pair"], entry["unit"])


def render_baseline(found: dict[Key, str]) -> str:
    """Return the baseline file text for ``found``, one entry per line.

    One line per pin keeps the file under the 500-line taste limit and makes a
    re-record diff show one line per changed pin.
    """
    description = (
        "Accepted divergence between the hand-written members of each agent, pinned by "
        "digest of both normalized sides. Read by build/scripts/check_agent_source_parity.py "
        "(ADR-107 M3, issue #5688). A pin that no longer matches fails the gate. The file "
        "only shrinks."
    )
    rows = [
        "    " + json.dumps({"agent": a, "pair": p, "unit": u, "digest": found[(a, p, u)]})
        for (a, p, u) in sorted(found)
    ]
    body = ",\n".join(rows)
    entries = f"[\n{body}\n  ]" if rows else "[]"
    return (
        "{\n"
        f'  "schema_version": {json.dumps(BASELINE_SCHEMA_VERSION)},\n'
        f'  "description": {json.dumps(description)},\n'
        f'  "entries": {entries}\n'
        "}\n"
    )


def _ceiling_finding(count: int) -> list[Finding]:
    if count <= BASELINE_CEILING:
        return []
    detail = f"{count} pins exceed the ceiling of {BASELINE_CEILING}"
    return [Finding(KIND_DIVERGED, "-", "-", "baseline", detail)]


def _write_baseline(repo_root: Path, found: dict[Key, str]) -> int:
    if len(found) > BASELINE_CEILING:
        print(
            f"ERROR: {len(found)} divergences exceed BASELINE_CEILING={BASELINE_CEILING}; "
            "reconcile the sources instead of pinning more.",
            file=sys.stderr,
        )
        return EXIT_DIVERGED
    path = repo_root / BASELINE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_baseline(found), encoding="utf-8")
    print(f"Wrote {len(found)} pins to {BASELINE_RELATIVE_PATH.as_posix()}")
    return EXIT_OK


def _find_repo_root(start: Path) -> Path:
    here = start.resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise ConfigError(f"could not find repo root from {start}")


def run(repo_root: Path, *, output: str, write_baseline: bool) -> int:
    """Run the gate and return its exit code."""
    found, missing = collect_divergence(repo_root)
    if write_baseline:
        if missing:
            print_text(missing, len(_stems(repo_root)), 0)
            print("ERROR: refusing to write the baseline with incomplete agents.", file=sys.stderr)
            return EXIT_DIVERGED
        return _write_baseline(repo_root, found)
    pinned = load_baseline(repo_root)
    findings = missing + reconcile(found, pinned) + _ceiling_finding(len(pinned))
    examined = len(_stems(repo_root))
    emit = print_json if output == "json" else print_text
    emit(findings, examined, len(pinned))
    return EXIT_DIVERGED if findings else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="re-record the pins from the current sources (reviewed in the diff)",
    )
    args = parser.parse_args(argv)
    try:
        repo_root = args.repo_root or _find_repo_root(Path.cwd())
        return run(repo_root, output=args.format, write_baseline=args.write_baseline)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
