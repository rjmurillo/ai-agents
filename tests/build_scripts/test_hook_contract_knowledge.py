"""Contract tests for durable cross-harness hook knowledge."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / ".claude" / "skills" / "agent-harness-reference"
REFERENCE = SKILL_ROOT / "SKILL.md"
OFFICIAL_SOURCES = SKILL_ROOT / "references" / "official-hook-contracts.md"
COPILOT_SKILL_ROOT = REPO_ROOT / "src" / "copilot-cli" / "skills"
COPILOT_REFERENCE = COPILOT_SKILL_ROOT / "agent-harness-reference" / "SKILL.md"
COPILOT_OFFICIAL_SOURCES = (
    COPILOT_SKILL_ROOT / "agent-harness-reference" / "references" / "official-hook-contracts.md"
)
SERENA_HOOK_MEMORY = REPO_ROOT / ".serena" / "memories" / "copilot-hooks-observations.md"
HOOK_REQUIREMENT = (
    REPO_ROOT / ".agents" / "specs" / "requirements" / "REQ-003-multi-tool-artifact-build.md"
)
RUNTIME_ADR = (
    REPO_ROOT / ".agents" / "architecture" / "ADR-071-plugin-hook-runtime-contract-verification.md"
)
DISPATCHER_ADR = REPO_ROOT / ".agents" / "architecture" / "ADR-068-consolidated-hook-dispatcher.md"
PERMISSION_ADR = (
    REPO_ROOT
    / ".agents"
    / "architecture"
    / "ADR-085-cross-harness-permission-surface-asymmetry.md"
)
PLATFORM_TEMPLATE = REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(document: str) -> str:
    return re.sub(r"\s+", " ", document)


def _normalized_text(path: Path) -> str:
    return _normalize(path.read_text(encoding="utf-8"))


def _refute(document: str, *phrases: str, source: Path | None = None) -> None:
    """Assert none of ``phrases`` appear, whatever the source wrapping is.

    A negative substring check against raw markdown is defeated by a line
    break inside the banned phrase, and prose is exactly what gets reflowed,
    so the raw form goes quietly green on the reintroduction it exists to
    catch. Measured: appending "The host merges structured\\ndecisions from
    every observer." to the reference left the raw assertion passing and this
    one failing. Every negative in this module goes through here so the
    guarantee is one function rather than a convention at each call site.
    """
    normalized = _normalize(document)
    for phrase in phrases:
        assert phrase not in normalized, f"{source}: {phrase}" if source else phrase


COPILOT_NATIVE_EVENTS = {
    "agentStop",
    "errorOccurred",
    "notification",
    "permissionRequest",
    "postToolUse",
    "postToolUseFailure",
    "preCompact",
    "preToolUse",
    "sessionEnd",
    "sessionStart",
    "subagentStart",
    "subagentStop",
    "userPromptSubmitted",
    "userPromptTransformed",
}

CLAUDE_EVENTS = {
    "SessionStart",
    "Setup",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "PreToolUse",
    "PermissionRequest",
    "PermissionDenied",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "Notification",
    "MessageDisplay",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "Stop",
    "StopFailure",
    "TeammateIdle",
    "InstructionsLoaded",
    "ConfigChange",
    "CwdChanged",
    "FileChanged",
    "WorktreeCreate",
    "WorktreeRemove",
    "PreCompact",
    "PostCompact",
    "Elicitation",
    "ElicitationResult",
    "SessionEnd",
}

ROUTING_FILES = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / ".claude" / "agents" / "AGENTS.md",
    REPO_ROOT / ".claude" / "skills" / "CLAUDE.md",
    REPO_ROOT / ".github" / "AGENTS.md",
    REPO_ROOT / ".github" / "copilot-instructions.md",
    REPO_ROOT / "src" / "AGENTS.md",
    REPO_ROOT / "templates" / "AGENTS.md",
)

GENERATED_INSTRUCTION_MIRRORS = (
    REPO_ROOT / ".github" / "instructions" / "generated-artifacts.instructions.md",
    REPO_ROOT / "src" / "copilot-cli" / "instructions" / "generated-artifacts.instructions.md",
)

RUNTIME_ROUTING_FILES = (
    REPO_ROOT / ".claude" / "skills" / "autoplan" / "SKILL.md",
    REPO_ROOT / ".claude" / "commands" / "build.md",
    REPO_ROOT / ".claude" / "commands" / "test.md",
    COPILOT_SKILL_ROOT / "autoplan" / "SKILL.md",
    COPILOT_SKILL_ROOT / "build" / "SKILL.md",
    COPILOT_SKILL_ROOT / "test" / "SKILL.md",
)

OPERATIONAL_SKILLS = (
    REPO_ROOT / ".claude" / "skills" / "ai-agents-architecture-contract" / "SKILL.md",
    REPO_ROOT / ".claude" / "skills" / "ai-agents-config-catalog" / "SKILL.md",
    REPO_ROOT / ".claude" / "skills" / "ai-agents-generation-and-release" / "SKILL.md",
    REPO_ROOT / ".claude" / "skills" / "ai-agents-portability-campaign" / "SKILL.md",
    COPILOT_SKILL_ROOT / "ai-agents-architecture-contract" / "SKILL.md",
    COPILOT_SKILL_ROOT / "ai-agents-config-catalog" / "SKILL.md",
    COPILOT_SKILL_ROOT / "ai-agents-generation-and-release" / "SKILL.md",
    COPILOT_SKILL_ROOT / "ai-agents-portability-campaign" / "SKILL.md",
)

PLUGIN_VERSION_SECTIONS = (
    (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-architecture-contract" / "SKILL.md",
        "### Phase 5: Know the plugin and product surfaces",
    ),
    (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-config-catalog" / "SKILL.md",
        "## Plugin Manifest Version Prohibition",
    ),
    (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-generation-and-release" / "SKILL.md",
        "### Phase 4: Plugin Manifests Carry No Version",
    ),
)


def _reference_text() -> str:
    return REFERENCE.read_text(encoding="utf-8")


def _text_code_block_after(text: str, marker: str) -> set[str]:
    block = text.split(marker, 1)[1].split("```text\n", 1)[1].split("```", 1)[0]
    return set(block.split())


def _section_after(text: str, marker: str, path: Path) -> str:
    _, separator, remainder = text.partition(marker)
    assert separator, f"{path}: missing section {marker!r}"
    return remainder.split("\n##", 1)[0]


def _paragraph_after(text: str, marker: str, path: Path) -> str:
    """Return only the paragraph that starts at ``marker``.

    ``_section_after`` stops at the next heading, so two prose paragraphs
    inside the same ``## Status`` section (no heading between them) come back
    concatenated. A current-vs-historical check on adjacent dated paragraphs
    needs the blank-line boundary instead, or the historical paragraph's own
    values leak into what should be a check of the paragraph after it.
    """
    _, separator, remainder = text.partition(marker)
    assert separator, f"{path}: missing paragraph {marker!r}"
    return remainder.split("\n\n", 1)[0]


def test_official_sidecar_lists_both_exact_event_sets() -> None:
    text = OFFICIAL_SOURCES.read_text(encoding="utf-8")
    copilot_events = _text_code_block_after(
        text,
        "The official table lists 14 native events:",
    )
    claude_events = _text_code_block_after(
        text,
        "The official table lists 30 events:",
    )

    assert copilot_events == COPILOT_NATIVE_EVENTS
    assert claude_events == CLAUDE_EVENTS


def test_reference_separates_stop_from_session_end() -> None:
    """Stop is per-turn, SessionEnd is process lifecycle, and they never alias.

    The event-policy rows are a repository decision, so they stay in SKILL.md.
    The Stop wire semantics are a vendor fact, so they live in the sidecar that
    the skill's own Authority Order names as the owner of vendor contracts.
    """
    text = _reference_text()
    sidecar = _normalized_text(OFFICIAL_SOURCES)

    # The table rows stay on raw text because their formatting is the assertion.
    assert "| Stop | None | Direct entries if added, one JSON decision per command |" in text
    assert "| SessionEnd | SessionEnd | Direct lifecycle event, never a Stop alias |" in text
    assert "Omitting `decision` permits completion." in sidecar
    assert "`block` forces another turn." in sidecar
    for document in (text, sidecar):
        _refute(
            document,
            "host merges structured decisions",
            "Stop: SessionEnd",
            "`allow` permits completion",
        )


def test_hook_requirement_tracks_dispatcher_and_matcher_contract() -> None:
    text = HOOK_REQUIREMENT.read_text(encoding="utf-8")
    section = _section_after(text, "**REQ-003-007", HOOK_REQUIREMENT)

    assert "one dispatcher entry" in section
    assert "Keep `Stop` and `SubagentStop` decision producers as direct entries" in section
    assert "ordered host-side `|` union" in section
    assert '"powershell": "py -3 -u' in section
    assert "plus five seconds of dispatcher headroom" in section
    assert "`HOOK_STDIN_CEILING_MIB`" in section
    assert "`MATCHED_SHIM_PAYLOAD_LIMIT_MIB`" in section
    assert "`MAX_MATCHER_TOOL_CALLS`" in section
    assert "cap manifest-controlled diagnostic values at 512 characters" in section
    assert "immediately after required future imports" in section
    _refute(
        section,
        "sentinel comment `# AUTO-GENERATED MATCHER SHIM (REQ-003-007)` at line 1",
        "shall NOT emit the matcher",
    )
    assert "manual `/compact` does not emit it" in section


def test_locked_schema_matches_copilot_artifact_configuration() -> None:
    text = HOOK_REQUIREMENT.read_text(encoding="utf-8")
    section = _section_after(text, "**REQ-003-002", HOOK_REQUIREMENT)
    match = re.search(r"```yaml\n(?P<yaml>.*?)\n```", section, re.DOTALL)
    assert match is not None

    locked = yaml.safe_load(match.group("yaml"))
    configured = yaml.safe_load(PLATFORM_TEMPLATE.read_text(encoding="utf-8"))

    assert locked["artifacts"] == configured["artifacts"]
    assert locked["auditPolicy"] == configured["auditPolicy"]


def test_runtime_adr_tracks_observer_output_merge() -> None:
    text = _normalized_text(RUNTIME_ADR)

    assert "emits one `additionalContext` object when captured output exists" in text
    assert "separates shim output with one blank line" in text
    assert "does not preserve per-shim attribution" in text
    assert "Stderr is not a documented model-context path" in text
    _refute(text, "observe dispatcher passes stdout through")


def test_reference_versions_matcher_and_timeout_evidence() -> None:
    """Timeouts fail open on every event, including the ones where exit 2 denies.

    The exit and timeout table is a vendor fact and lives in the sidecar. What
    stays in SKILL.md is the repository's response to it: keep script-side
    self-filtering because two shipped releases had matcher bugs.
    """
    text = _reference_text()

    normalized = _normalized_text(REFERENCE)
    normalized_sidecar = _normalized_text(OFFICIAL_SOURCES)

    # Pin the whole sentence. Bare version strings also appear in the probe
    # paragraph and the ADR list, so asserting "1.0.57" alone stays green with
    # the matcher-bug finding deleted, which is the regression that matters.
    assert (
        "Matchers do work, but 1.0.57 and 1.0.58 shipped matcher bugs, so a hook "
        "that filters only through the host has one point of failure." in normalized
    )
    assert "Keep script-side self-filtering as defense in depth." in normalized
    assert "it warns and continues by default, and denies only for PreToolUse" in normalized
    assert "Timeouts fail open on every event" in normalized

    # The dedicated exit-code table, not the PreToolUse-specific failure table.
    # The narrow row says deny flatly; only this one carries the default.
    assert (
        "| 2 | Warning and continue by default; deny for PreToolUse and "
        "PermissionRequest; PostToolUseFailure converts stdout to context |" in normalized_sidecar
    )
    assert (
        "| Timeout | Fail open for every event, including policy PreToolUse |" in normalized_sidecar
    )
    assert "PreCompact | None | Supported observe/discard policy" in text
    probe = (SKILL_ROOT / "references" / "probe-evidence.md").read_text(encoding="utf-8")
    assert "Manual `/compact` is therefore a negative control" in probe
    assert "Automatic-compaction delivery remains unmeasured" in probe


def test_reference_labels_unstable_fields_and_cloud_limits() -> None:
    """suppressOutput is SDK-only and cloud agent reads one path.

    Both are vendor facts. The cross-harness delta table stays in SKILL.md
    because it is the routing surface for a porting decision.
    """
    text = _reference_text()

    normalized_sidecar = _normalized_text(OFFICIAL_SOURCES)
    assert "implementation-only SDK types" in normalized_sidecar
    assert "loads only `.github/hooks/*.json`" in normalized_sidecar
    assert "Claude Code is a separate contract" in text


def test_reference_names_repository_loading_surfaces() -> None:
    text = _reference_text()

    assert ".claude/skills/agent-harness-reference/" in text
    assert "src/copilot-cli/skills/agent-harness-reference/" in text
    assert "`.github/skills/` is not a repository shipping surface" in text
    assert "Individual agent prompts do not copy the vendor contract." in text


def test_serena_memory_routes_to_current_contract_sources() -> None:
    text = SERENA_HOOK_MEMORY.read_text(encoding="utf-8")

    assert "references/official-hook-contracts.md" in text
    assert 'PermissionRequest uses `behavior: "allow"|"deny"`' in text
    assert "There is no `ask` behavior." in text
    assert "`.github/skills/` is not a shipping surface" in text
    assert "Do not copy current plugin versions into guidance." in text


def test_reference_preserves_cross_harness_decision_shapes() -> None:
    """The three wire shapes are vendor facts; not confusing them is policy."""
    sidecar = _normalized_text(OFFICIAL_SOURCES)

    assert '"permissionDecision": "allow"' in sidecar
    assert '"behavior": "allow"' in sidecar
    assert '"decision": "block"' in sidecar
    assert "`behavior` accepts only `allow` or `deny`." in sidecar

    normalized = _normalized_text(REFERENCE)
    assert "never Claude's nested `hookSpecificOutput` envelope" in normalized
    assert "never a top-level `decision`" in normalized
    assert "A translated `ask` emits nothing" in normalized


def test_no_stop_hook_is_registered_on_any_surface() -> None:
    """Stop is unregistered everywhere, and no dispatch group targets it.

    The vendored and generated surfaces were purged under ADR-084. The local
    surface kept one Stop group whose only remaining shim was
    invoke_auto_retrospective.py, which #3187 measured net-negative and #3349
    found still firing: it wrote a retrospective skeleton into the working
    tree at session end and returned a block decision to force another turn.
    Deleting it emptied the group, so the whole Stop path is gone rather than
    reduced. Asserting absence on all four surfaces, and on group ids as well
    as registrations, is what keeps it gone: a group with no registration
    would still be dispatchable by hand.
    """
    local_hooks = _read_json(REPO_ROOT / ".claude" / "settings.json")["hooks"]
    vendored_hooks = _read_json(REPO_ROOT / ".claude" / "hooks" / "hooks.json")["hooks"]
    generated_hooks = _read_json(REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json")[
        "hooks"
    ]
    dispatch_groups = _read_json(REPO_ROOT / ".claude" / "hooks" / "dispatch_groups.json")["groups"]

    assert "Stop" not in local_hooks
    assert "Stop" not in vendored_hooks
    assert "Stop" not in generated_hooks
    assert "agentStop" not in generated_hooks
    assert [group_id for group_id in dispatch_groups if group_id.startswith("stop-")] == []
    assert [
        group_id
        for group_id, spec in dispatch_groups.items()
        if spec.get("event") in {"Stop", "SubagentStop", "agentStop"}
    ] == []

    sidecar = _normalized_text(OFFICIAL_SOURCES)
    assert "Shared Stop producers can emit this shape on both harnesses." in sidecar


def test_reference_preserves_single_structured_output_boundary() -> None:
    sidecar = _normalized_text(OFFICIAL_SOURCES)
    rule = (REPO_ROOT / ".claude" / "rules" / "generated-artifacts.md").read_text(encoding="utf-8")

    assert "performs one `JSON.parse`" in sidecar
    assert "Two final JSON objects concatenate into invalid JSON and are ignored." in sidecar
    normalized = _normalized_text(REFERENCE)
    assert '`{"additionalContext":"..."}` object' in normalized
    assert "Failed-observer partial output is discarded." in normalized
    assert "It emits nothing when every observer is silent." in normalized
    assert "| PreCompact | DOCS SILENT:" in sidecar
    assert "| UserPromptSubmitted / UserPromptSubmit | DOCS SILENT:" in sidecar
    assert "Preserve one valid structured output per command hook" in rule
    assert "Byte passthrough is not output merging." in rule


def test_official_sidecar_pins_sources_and_refresh_procedure() -> None:
    text = _normalized_text(OFFICIAL_SOURCES)

    assert "https://docs.github.com/en/copilot/reference/hooks-reference" in text
    assert "github/docs/blob/0b02cd6336f4eebda1e409b45a89dab5c2193d9a" in text
    assert "raw.githubusercontent.com/github/copilot-cli/fd24cea5" in text
    assert "https://code.claude.com/docs/en/hooks" in text
    assert (
        "Sources: GitHub Copilot hook reference, agentStop / subagentStop "
        "decision control; Claude Code hooks reference, Stop decision control." in text
    )
    assert "## Refresh procedure" in text
    assert "DOCS SILENT" in text


def test_authoring_surfaces_route_to_settled_contract() -> None:
    for path in ROUTING_FILES:
        text = path.read_text(encoding="utf-8")
        assert "agent-harness-reference" in text, path
        assert "ai-agents-portability-campaign" in text, path

    rule = (REPO_ROOT / ".claude" / "rules" / "generated-artifacts.md").read_text(encoding="utf-8")
    assert "references/official-hook-contracts.md" in rule
    assert "Do not infer one harness from another." in rule


def test_runtime_routes_load_hook_contract_before_hook_work() -> None:
    for path in RUNTIME_ROUTING_FILES:
        text = path.read_text(encoding="utf-8")
        assert "agent-harness-reference" in text, path
        assert "ai-agents-portability-campaign" in text, path


def test_generated_copilot_skill_mirrors_settled_contract() -> None:
    reference = COPILOT_REFERENCE.read_text(encoding="utf-8")

    assert COPILOT_OFFICIAL_SOURCES.read_text(encoding="utf-8") == (
        OFFICIAL_SOURCES.read_text(encoding="utf-8")
    )
    assert reference == REFERENCE.read_text(encoding="utf-8")
    assert "| PreCompact | None | Supported observe/discard policy" in reference
    assert "| Stop | None | Direct entries if added" in reference
    assert "A translated `ask` emits nothing" in _normalized_text(COPILOT_REFERENCE)


def test_generated_instruction_mirrors_route_to_contract() -> None:
    for path in GENERATED_INSTRUCTION_MIRRORS:
        text = path.read_text(encoding="utf-8")
        assert "agent-harness-reference" in text, path
        assert "references/official-hook-contracts.md" in text, path
        assert "ai-agents-portability-campaign" in text, path


def test_requirement_and_historical_audit_do_not_reassert_old_contract() -> None:
    requirement = (
        REPO_ROOT / ".agents" / "specs" / "requirements" / "REQ-003-multi-tool-artifact-build.md"
    ).read_text(encoding="utf-8")
    audit = (REPO_ROOT / ".agents" / "audit" / "m5-matcher-classification.md").read_text(
        encoding="utf-8"
    )

    assert "14 native events:" in requirement
    assert "SubagentStop, PermissionRequest, and PreCompact are supported" in requirement
    _refute(requirement, "Does not exist")
    assert "Historical implementation snapshot" in audit
    assert "not the current Copilot CLI contract" in audit


def test_operational_sources_exclude_superseded_claims() -> None:
    paths = (
        REFERENCE,
        OFFICIAL_SOURCES,
        COPILOT_REFERENCE,
        SERENA_HOOK_MEMORY,
        *OPERATIONAL_SKILLS,
    )
    stale_claims = (
        "Notification and PreCompact remain dropped",
        '"behavior":"allow|deny|ask"',
        "Stop: SessionEnd",
    )

    for path in paths:
        _refute(path.read_text(encoding="utf-8"), *stale_claims, source=path)


def test_operational_skills_state_the_manifests_carry_no_version() -> None:
    # ADR-092 deleted the field, so these sections must state the prohibition
    # rather than tell the reader to look the current value up. A semver
    # literal here would be a value that no longer exists to read.
    semver_literal = re.compile(r"\b\d+\.\d+\.\d+\b")

    for path, marker in PLUGIN_VERSION_SECTIONS:
        section = _section_after(path.read_text(encoding="utf-8"), marker, path)
        flattened = " ".join(section.split())
        assert "may carry a `version` field" in flattened, path
        assert not semver_literal.search(section), path


def test_operational_skills_do_not_pin_pre_push_line_numbers() -> None:
    paths = (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-config-catalog" / "SKILL.md",
        REPO_ROOT / ".claude" / "skills" / "ai-agents-generation-and-release" / "SKILL.md",
        COPILOT_SKILL_ROOT / "ai-agents-config-catalog" / "SKILL.md",
        COPILOT_SKILL_ROOT / "ai-agents-generation-and-release" / "SKILL.md",
    )

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\.githooks/pre-push:\d", text), path


def test_operational_skills_match_current_hook_registration_counts() -> None:
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))[
        "hooks"
    ]
    plugin = json.loads(
        (REPO_ROOT / ".claude" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )["hooks"]
    copilot = json.loads(
        (REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )["hooks"]
    architecture = (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-architecture-contract" / "SKILL.md"
    ).read_text(encoding="utf-8")
    catalog = (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-config-catalog" / "SKILL.md"
    ).read_text(encoding="utf-8")

    settings_summary = f"{len(settings)} events, {sum(map(len, settings.values()))} groups"
    plugin_summary = f"{len(plugin)} events, {sum(map(len, plugin.values()))} groups"
    copilot_summary = f"{len(copilot)} events, {sum(map(len, copilot.values()))} registrations"

    assert settings_summary in architecture
    assert settings_summary in catalog
    assert plugin_summary in architecture
    assert plugin_summary in catalog
    assert copilot_summary in architecture
    assert (
        f"vendored source prints `{len(plugin)} {sum(map(len, plugin.values()))}`" in architecture
    )
    assert "Three independent registration sources" in catalog
    assert ".github/hooks/require-subagent-model.json" in _section_after(
        catalog, "## Provenance and Maintenance", REPO_ROOT
    )
    _refute(
        architecture,
        "registers 7 events",
        "expected 7 and 14",
        "8 events / 23 matcher groups",
    )

    # The weak-point table restates the same counts in prose ("N events and M
    # groups") rather than the comma form asserted above. That phrasing went
    # unchecked, so hooks.json drifted to "2 events and 3 groups" and
    # contradicted the re-verify table in the same document. Pin both trees.
    settings_prose = f"{len(settings)} events and {sum(map(len, settings.values()))} groups"
    plugin_prose = f"{len(plugin)} events and {sum(map(len, plugin.values()))} groups"
    for surface in (
        architecture,
        (
            REPO_ROOT
            / "src"
            / "copilot-cli"
            / "skills"
            / "ai-agents-architecture-contract"
            / "SKILL.md"
        ).read_text(encoding="utf-8"),
    ):
        assert settings_prose in surface
        assert plugin_prose in surface

    # The provenance table is the third copy of these counts and states them in
    # a slash form the two assertions above cannot see. It sat at "3 events / 4
    # groups" while the command printed in its own row returned 5 and 7, which
    # discredits every other row in the skill's evidence layer. Pin both trees.
    settings_slash = f"{len(settings)} events / {sum(map(len, settings.values()))} groups"
    plugin_slash = f"{len(plugin)} events / {sum(map(len, plugin.values()))} groups"
    copilot_slash = f"{len(copilot)} events / {sum(map(len, copilot.values()))} registrations"
    provenance_paths = (
        REPO_ROOT
        / ".claude"
        / "skills"
        / "ai-agents-architecture-contract"
        / "references"
        / "provenance.md",
        COPILOT_SKILL_ROOT / "ai-agents-architecture-contract" / "references" / "provenance.md",
    )
    for path in provenance_paths:
        surface = path.read_text(encoding="utf-8")
        assert settings_slash in surface, path
        assert plugin_slash in surface, path
        assert copilot_slash in surface, path

    provenance = provenance_paths[0].read_text(encoding="utf-8")
    weak_points = (
        REPO_ROOT
        / ".claude"
        / "skills"
        / "ai-agents-architecture-contract"
        / "references"
        / "weak-points.md"
    ).read_text(encoding="utf-8")
    date_patterns = (
        (architecture, r"Registered \(re-verified (\d{4}-\d{2}-\d{2})\)"),
        (architecture, r"facts re-verified against the working tree on (\d{4}-\d{2}-\d{2})"),
        (catalog, r"Shape re-verified (\d{4}-\d{2}-\d{2})"),
        (catalog, r"Audited (\d{4}-\d{2}-\d{2}) against the working tree"),
        (provenance, r"Verified (\d{4}-\d{2}-\d{2}) against the working tree"),
        (weak_points, r"Evidence \(as of (\d{4}-\d{2}-\d{2})\)"),
    )
    verified_dates: set[str] = set()
    for text, pattern in date_patterns:
        match = re.search(pattern, text)
        assert match is not None, pattern
        verified_dates.add(match.group(1))
    assert len(verified_dates) == 1, verified_dates


def test_dispatcher_adrs_match_current_generated_metrics() -> None:
    hooks_root = REPO_ROOT / "src" / "copilot-cli" / "hooks"
    source_counts: dict[str, int] = {}
    for path in hooks_root.glob("*/_manifest.json"):
        manifest = _read_json(path)
        source_counts[manifest["event"]] = len(manifest["shims"])

    copilot_hooks = _read_json(hooks_root / "hooks.json")["hooks"]
    for event, registrations in copilot_hooks.items():
        source_counts.setdefault(event, len(registrations))

    pretool_manifest = _read_json(hooks_root / "PreToolUse" / "_manifest.json")
    source_total = sum(source_counts.values())
    host_total = sum(map(len, copilot_hooks.values()))
    timeout_total = sum(pretool_manifest["timeouts"].values())
    host_timeout = copilot_hooks["PreToolUse"][0]["timeoutSec"]
    timeout_headroom = host_timeout - timeout_total
    reduction = 100 * (1 - host_total / source_total)
    adr_068 = _normalized_text(
        REPO_ROOT / ".agents" / "architecture" / "ADR-068-consolidated-hook-dispatcher.md"
    )
    adr_085 = _normalized_text(
        REPO_ROOT
        / ".agents"
        / "architecture"
        / "ADR-085-cross-harness-permission-surface-asymmetry.md"
    )
    adr_071 = _normalized_text(
        REPO_ROOT
        / ".agents"
        / "architecture"
        / "ADR-071-plugin-hook-runtime-contract-verification.md"
    )

    # Issue #4917 (2026-08-18) added the Serena worktree scope guard, which is
    # not excluded from Copilot generation (unlike push_pr_script_identity_guard,
    # #5013). The dynamic reads above now see three PreToolUse shims, not two;
    # the expected values below are the independently reviewed current facts,
    # not a self-confirming echo of whatever the generator happens to emit.
    assert source_counts == {"PreToolUse": 3, "PostToolUse": 1}
    assert source_total == 4
    assert host_total == 2
    assert round(reduction, 1) == 50.0
    assert "five registrations across two events" in adr_068
    assert "four PreToolUse shims and one PostToolUse shim" in adr_068
    assert (
        "four registrations across two events (three PreToolUse shims and "
        "one PostToolUse shim)" in adr_068
    )
    assert "not for matched-call process savings" in adr_068
    assert len(pretool_manifest["shims"]) == 3
    assert timeout_total == 110
    assert "current PreToolUse manifest has three shims" in adr_068
    assert "110 seconds of configured timeout" in adr_068
    assert f"host entry requests {host_timeout} seconds" in adr_068
    assert "five seconds of dispatcher headroom" in adr_068
    assert "the in-process bypass is latent" in adr_068
    assert "four registrations across two events" in adr_085
    containment_note = (
        "excluded `push_pr_script_identity_guard` from the generated "
        "Copilot inventory only"
    )
    assert containment_note in adr_068
    assert containment_note in adr_071
    assert containment_note in adr_085
    # The 2026-08-11 baseline (issue #4874) is a dated historical record, not
    # a live claim, and stays pinned in both ADRs precisely because it was
    # true then and the amendment paragraphs say so explicitly.
    assert (
        "growing the active manifest to three shims and 110 seconds of "
        "summed timeout" in adr_068
    )
    assert "active manifest contains three shims" in adr_071
    assert "110 seconds of configured timeout" in adr_071
    for stale in (
        "125 seconds",
        "four starts on a `git push` today",
        "direct registration would start at most two",
        "two-shim PreToolUse",
        "manifest value is 100 seconds",
        "saves one host process start",
        "can skip later gates",
        "No in-process timeout enforcement",
        "the spawn cost this ADR removes",
        "removes process startup",
    ):
        assert stale not in adr_068, f"stale metric survives in ADR-068: {stale}"
    assert f"host entry requests {host_timeout} seconds" in adr_071
    assert timeout_headroom == 5


def test_adr_068_scopes_2026_08_11_and_2026_08_14_status_paragraphs() -> None:
    """The two dated Status paragraphs must not blur into each other.

    Round 1 found the 2026-08-14 paragraph framed as a blanket "facts
    refresh" with no named policy authority. The fix must land in the
    2026-08-14 paragraph specifically, and the 2026-08-11 paragraph must keep
    its own historical numbers unchanged. Explicit reviewed values, not a
    dynamic re-derivation of the same generator output the prose describes.
    """
    text = DISPATCHER_ADR.read_text(encoding="utf-8")
    historical = _normalize(
        _paragraph_after(text, "Amended 2026-08-11 (issue #4874):", DISPATCHER_ADR)
    )
    current = _normalize(
        _paragraph_after(text, "Amended 2026-08-14 (issue #5013):", DISPATCHER_ADR)
    )

    assert "three shims and 110 seconds of summed timeout" in historical
    assert "ADR-085 Decision 7 is the policy authority" in current
    assert "scoped derived-metrics update" in current
    assert "100 seconds of configured timeout" in current
    assert "host entry requests 105 seconds" in current
    assert "same file still lists the guard in Claude Code's canonical dispatch group" in current
    assert (
        "excluded `push_pr_script_identity_guard` from the generated Copilot "
        "inventory only" in current
    )
    assert "ADR-068-071-085-5013-debate-log.md" in current
    _refute(current, "three shims and 110 seconds of summed timeout")
    _refute(historical, "scoped derived-metrics update", "ADR-085 Decision 7 is the policy")


def test_adr_071_scopes_2026_08_11_and_2026_08_14_amendment_sections() -> None:
    """Same current-vs-historical boundary, on ADR-071's dated subsections."""
    text = RUNTIME_ADR.read_text(encoding="utf-8")
    historical = _normalize(
        _section_after(
            text,
            "### 2026-08-11 amendment: require-subagent-model gate (issue #4874)",
            RUNTIME_ADR,
        )
    )
    current = _normalize(
        _section_after(
            text,
            "### 2026-08-14 amendment: push-pr identity guard excluded from "
            "Copilot generation (issue #5013)",
            RUNTIME_ADR,
        )
    )

    assert "three shims with 110 seconds of configured timeout" in historical
    assert "115 seconds" in historical
    assert "ADR-085 Decision 7 is the policy authority" in current
    assert "scoped runtime-contract update" in current
    assert "100 seconds of configured timeout" in current
    assert "105 seconds" in current
    assert "Copilot excludes the guard from generation entirely" in current
    assert "ADR-068-071-085-5013-debate-log.md" in current
    _refute(current, "three shims with 110 seconds of configured timeout", "115 seconds")
    _refute(historical, "scoped runtime-contract update", "ADR-085 Decision 7 is the policy")

    status = _normalize(RUNTIME_ADR.read_text(encoding="utf-8"))
    assert "Amended 2026-08-11 (issue #4874)" in status
    assert "Amended 2026-08-14 (issue #5013)" in status
    assert "ADR-068-071-085-metric-refresh-debate-log.md" in status
    assert "ADR-068-071-085-5013-debate-log.md" in status


def test_adr_085_decision_seven_applies_eligibility_test_to_the_exclusion() -> None:
    """ADR-085 Decision 7 must apply Decision 1's test, not just cite it."""
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_seven = _normalize(
        _section_after(
            text,
            "### 7. `push_pr_script_identity_guard`: temporary Copilot-only "
            "exclusion, Claude retained (D-C)",
            PERMISSION_ADR,
        )
    )

    for label in ("**Portability.**", "**Fidelity.**", "**Policy safety.**"):
        assert label in decision_seven, label
    assert "Containment passes temporarily because" in decision_seven
    assert (
        "Copilot CLI has no guard against a prompt-injected repository "
        "lookalike `new_pr.py` gaining user-level Python execution" in decision_seven
    )
    assert "Claude Code is unaffected because its host entry is not a timed" in decision_seven


def test_adr_085_decision_seven_records_generic_field_governance() -> None:
    """The nine governance requirements the ruling attaches to copilotExclude."""
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_seven = _normalize(
        _section_after(
            text,
            "### 7. `push_pr_script_identity_guard`: temporary Copilot-only "
            "exclusion, Claude retained (D-C)",
            PERMISSION_ADR,
        )
    )

    assert "**Generic field governance.**" in decision_seven
    governance_requirements = (
        "Strict boolean validation.",
        "Plugin surface named.",
        "Issue metadata.",
        "Decision metadata.",
        "Residual risk stated.",
        "Unaffected-harness behavior stated.",
        "Reintroduction criteria named.",
        "Cleanup obligation named.",
        "Tests required.",
    )
    for requirement in governance_requirements:
        assert requirement in decision_seven, requirement


def test_adr_085_decision_seven_records_the_eight_reintroduction_gates() -> None:
    """The eight measurable gates from issue #5013, and their ownership."""
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_seven = _normalize(
        _section_after(
            text,
            "### 7. `push_pr_script_identity_guard`: temporary Copilot-only "
            "exclusion, Claude retained (D-C)",
            PERMISSION_ADR,
        )
    )

    assert "**Reintroduction gates.**" in decision_seven
    assert "Issue #5013 and assignee rjmurillo own reintroduction." in decision_seven
    assert (
        "Reintroduction is optional and requires rjmurillo's approval before "
        "the field reverts to `false`." in decision_seven
    )
    eight_gates = (
        "Unrelated commands never launch the guard's child process on Copilot.",
        "The canonical `new_pr.py` invocation is allowed.",
        "A prompt-injected repository lookalike `new_pr.py` is denied.",
        "A dynamic launcher, `python -c`, `eval`, or shell substitution, "
        "targeting `new_pr.py` is denied.",
        "A Windows load test of 32 calls across 8 workers completes without "
        "a false denial.",
        "Latency stays under a 500ms p95 and a 1 second maximum across that "
        "load test.",
        "The measurement runs against a real Copilot CLI probe, not a "
        "simulated harness.",
        "The owner classifies the guard's disposition as deleted or "
        "essential before it returns to the generated inventory.",
    )
    for gate in eight_gates:
        assert gate in decision_seven, gate


def test_issue_5013_adrs_refute_stale_framing_and_incomplete_lists() -> None:
    """Round 1 findings that must stay fixed across every affected ADR.

    ADR-068 and ADR-071 both described the issue #5013 exclusion as a
    blanket "facts refresh" naming no policy authority; that framing is
    retired everywhere, not only in the paragraph a reviewer happened to
    read. ADR-068's settings inventory named five events for seven
    registrations while a sixth event, PostToolUseFailure, holds one of
    them.
    """
    for path in (DISPATCHER_ADR, RUNTIME_ADR, PERMISSION_ADR):
        _refute(
            path.read_text(encoding="utf-8"),
            "This is a facts refresh",
            "seven registrations across SessionStart, UserPromptSubmit, "
            "PostToolUse, SessionEnd, and PreCompact",
            source=path,
        )
    assert (
        "seven registrations across SessionStart, UserPromptSubmit, "
        "PostToolUse, PostToolUseFailure, SessionEnd, and PreCompact"
        in _normalized_text(DISPATCHER_ADR)
    )


def test_issue_5013_adrs_state_claude_retention_and_copilot_exclusion() -> None:
    """Every affected ADR must say, in its own words, who keeps the guard."""
    exclusion_note = (
        "excluded `push_pr_script_identity_guard` from the generated Copilot "
        "inventory only"
    )

    for path in (DISPATCHER_ADR, RUNTIME_ADR, PERMISSION_ADR):
        normalized = _normalized_text(path)
        assert "canonical dispatch group" in normalized, path
        assert ".claude/hooks/hooks.json` still registers" in normalized, path
        assert exclusion_note in normalized, path

    assert "Copilot excludes the guard from generation entirely" in _normalized_text(RUNTIME_ADR)
    assert (
        "Claude Code is unaffected because its host entry is not a timed "
        "child process" in _normalized_text(PERMISSION_ADR)
    )


def test_adr_085_status_records_the_containment_incident() -> None:
    """The incident numbers belong in Status, not only in Decision 7."""
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    status = _normalize(_section_after(text, "## Status", PERMISSION_ADR))

    assert "127 unrelated Bash commands" in status
    assert "more than 21 minutes" in status
    assert "owner applied immediate containment" in status
    assert (
        "root cause was the guard's broad `Bash` registration paired with a "
        "timed child process that denies on overrun" in status
    )
    assert "dispatcher itself is unchanged" in status
    assert "ADR-068-071-085-5013-debate-log.md" in status


def test_current_memories_record_skill_first_guard_retirement() -> None:
    pr_rules = (
        REPO_ROOT / ".serena" / "memories" / "github-skill" / "pr-creation-rules.md"
    ).read_text(encoding="utf-8")
    observations = (REPO_ROOT / ".serena" / "memories" / "github-pr1873-observations.md").read_text(
        encoding="utf-8"
    )
    script_reference = (
        REPO_ROOT / ".serena" / "memories" / "tools" / "github-skill-scripts-reference.md"
    ).read_text(encoding="utf-8")
    decision_memory = (
        REPO_ROOT / ".serena" / "memories" / "decision-adr-085-permission-surface-asymmetry.md"
    ).read_text(encoding="utf-8")

    _refute(pr_rules, "The skill-first hook blocks gh pr create")
    _refute(observations, "Raw `gh` may be blocked by `invoke_skill_first_guard.py`")
    _refute(script_reference, "This repo has a PreToolUse hook")
    assert "PR #3293 implemented Retirement" in decision_memory


def test_generation_skill_requires_an_explicit_reason_for_hook_drops() -> None:
    generation = (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-generation-and-release" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "an unexplained drop means contract drift" in generation
    _refute(generation, "Drops are unsupported Copilot events, by design")
