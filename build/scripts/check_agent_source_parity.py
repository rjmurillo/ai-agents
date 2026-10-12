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
``SHARED_FRONTMATTER_KEYS`` (``name``, ``model``, ``model_tier``, ``tools``,
``tools_vscode``, ``tools_copilot``, ``isolation_required``, ``metadata``
other than ``metadata.role``), and for the Claude pair an H2 section present
on only one side (section inventory stays with ``detect_agent_drift.py``).

Shared, compared exactly after ``detect_agent_drift.normalize_content``: the
frontmatter keys ``description``, ``argument-hint`` and ``role`` (Claude spells
``role`` either top level or as ``metadata.role``), the preamble before the
first H2, and the body of every H2 section both sides carry. The normalization
rewrites MCP tool prefixes, handoff invocation spelling, fence language tags,
and whitespace, and it ignores blank lines. A repeated H2 name in one source is a
ConfigError, because a repeat would hide the earlier body. It never drops a text line, reorders
a step, or edits a number, so the eight ADR-107 section 5 invariants are never
excused: ordered steps, completion criteria, evidence requirements, failure
states, approval gates, authorization and capability statements, idempotence and
rollback statements, and the exit-code contract all live in section text that
must match.

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
from dataclasses import dataclass
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import agent_templates  # noqa: E402
from detect_agent_drift import (  # noqa: E402
    get_markdown_section_list,
    normalize_content,
    remove_yaml_frontmatter,
)

EXIT_OK = 0
EXIT_DIVERGED = 1
EXIT_CONFIG = 2

BASELINE_RELATIVE_PATH = Path(".agents") / "governance" / "agent-source-divergence.json"
BASELINE_SCHEMA_VERSION = "1"
# Pinned divergences at the time the gate landed. Raising this needs a code
# edit, so growth is a reviewed change and not a quiet re-record.
BASELINE_CEILING = 56

SHARED_FRONTMATTER_KEYS: tuple[str, ...] = ("description", "argument-hint", "role")
PAIR_CLAUDE = "claude-shared"
PAIR_COPILOT = "copilot-shared"
PAIRS: tuple[str, ...] = (PAIR_CLAUDE, PAIR_COPILOT)

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_MAX_REPORT_LINES = 100

KIND_DIVERGED = "DIVERGED"
KIND_CHANGED = "PIN-CHANGED"
KIND_STALE = "PIN-STALE"
KIND_MISSING = "MISSING-MEMBER"

Key = tuple[str, str, str]


class ConfigError(Exception):
    """The gate could not run: a tree, template, or baseline is unusable."""


@dataclass(frozen=True)
class Finding:
    """One reason the gate fails."""

    kind: str
    agent: str
    pair: str
    unit: str
    detail: str = ""


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


def extract_units(text: str) -> dict[str, str]:
    """Return ``{unit: normalized text}`` for every shared unit in one member."""
    frontmatter = _frontmatter(text)
    units: dict[str, str] = {}
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

    A unit on one side only counts when ``strict`` is set or the unit is
    frontmatter (a missing shared key is a divergence in every pair).
    """
    found: dict[str, str] = {}
    for unit in sorted(set(left) | set(right)):
        one_sided = unit not in left or unit not in right
        if one_sided and not strict and not unit.startswith("frontmatter:"):
            continue
        a, b = left.get(unit, ""), right.get(unit, "")
        if one_sided or a != b:
            found[unit] = _digest(a, b)
    return found


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


def _render(tmpl: Path, partials: Path) -> str:
    try:
        return str(agent_templates.render(tmpl, partials))
    except _RENDER_ERRORS as exc:
        raise ConfigError(f"cannot render {tmpl}: {exc}") from exc


def _stems(repo_root: Path) -> list[str]:
    agents = repo_root / "templates" / "agents"
    if not agents.is_dir():
        raise ConfigError(f"directory not found: {agents}")
    stems = set(agent_templates.discover(repo_root))
    stems.update(p.name.removesuffix(".shared.md") for p in agents.glob("*.shared.md"))
    return sorted(stems)


def _compare_stem(
    stem: str,
    shared_text: str,
    claude_tmpl: Path,
    copilot_tmpl: Path,
    partials: Path,
) -> dict[Key, str]:
    """Return the divergences between one agent's shared source and its templates."""
    shared_units = extract_units(shared_text)
    found: dict[Key, str] = {}
    for pair, tmpl, strict in (
        (PAIR_CLAUDE, claude_tmpl, False),
        (PAIR_COPILOT, copilot_tmpl, True),
    ):
        units = extract_units(_render(tmpl, partials))
        diverged = diverged_units(units, shared_units, strict=strict)
        found.update({(stem, pair, unit): digest for unit, digest in diverged.items()})
    return found


def collect_divergence(repo_root: Path) -> tuple[dict[Key, str], list[Finding]]:
    """Compare every agent's members. Return divergences and missing-member findings."""
    agents = repo_root / "templates" / "agents"
    pairs = agent_templates.discover(repo_root)
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
            _compare_stem(stem, _read(shared), claude_tmpl, copilot_tmpl, agents / "partials")
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


def reconcile(found: dict[Key, str], pinned: dict[Key, str]) -> list[Finding]:
    """Compare live divergence to the pins and return every failure."""
    findings: list[Finding] = []
    for key in sorted(found):
        agent, pair, unit = key
        if key not in pinned:
            findings.append(Finding(KIND_DIVERGED, agent, pair, unit))
        elif pinned[key] != found[key]:
            findings.append(
                Finding(
                    KIND_CHANGED, agent, pair, unit, "edited since pinned; review, then re-record"
                )
            )
    for key in sorted(set(pinned) - set(found)):
        findings.append(Finding(KIND_STALE, key[0], key[1], key[2], "now agrees; remove the pin"))
    return findings


def render_baseline(found: dict[Key, str]) -> str:
    """Return the baseline file text for ``found``."""
    entries = [
        {"agent": a, "pair": p, "unit": u, "digest": found[(a, p, u)]}
        for (a, p, u) in sorted(found)
    ]
    document = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "description": (
            "Accepted divergence between the hand-written members of each agent, pinned by "
            "digest of both normalized sides. Read by build/scripts/check_agent_source_parity.py "
            "(ADR-107 M3, issue #5688). A pin that no longer matches fails the gate. The file "
            "only shrinks."
        ),
        "entries": entries,
    }
    return json.dumps(document, indent=2) + "\n"


def _ceiling_finding(count: int) -> list[Finding]:
    if count <= BASELINE_CEILING:
        return []
    detail = f"{count} pins exceed the ceiling of {BASELINE_CEILING}"
    return [Finding(KIND_DIVERGED, "-", "-", "baseline", detail)]


def _print_text(findings: list[Finding], examined: int, pinned: int) -> None:
    print(f"Examined {examined} agents; {pinned} divergences pinned in the baseline.")
    for finding in findings[:_MAX_REPORT_LINES]:
        tail = f" ({finding.detail})" if finding.detail else ""
        print(f"  {finding.kind}: {finding.agent} {finding.pair} {finding.unit}{tail}")
    hidden = len(findings) - _MAX_REPORT_LINES
    if hidden > 0:
        print(f"  ... and {hidden} more")
    if findings:
        print(f"FAIL: {len(findings)} source parity issue(s). Contract: GENERATOR-FILES.md.")
    else:
        print("OK: agent sources agree under the normalization contract.")


def _print_json(findings: list[Finding], examined: int, pinned: int) -> None:
    report = {
        "agents_examined": examined,
        "pinned": pinned,
        "findings": [vars(f) for f in findings],
    }
    print(json.dumps(report, indent=2))


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
        return _write_baseline(repo_root, found)
    pinned = load_baseline(repo_root)
    findings = missing + reconcile(found, pinned) + _ceiling_finding(len(pinned))
    examined = len(_stems(repo_root))
    emit = _print_json if output == "json" else _print_text
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
