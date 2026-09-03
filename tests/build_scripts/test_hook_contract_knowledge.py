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
    REPO_ROOT / ".agents" / "architecture" / "ADR-085-cross-harness-permission-surface-asymmetry.md"
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
    REPO_ROOT / "src" / "claude" / "AGENTS.md",
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
    # ADR-097 retired `.github/hooks/require-subagent-model.json`, so the third
    # registration source is gone. The catalog must say two, and must still
    # carry a re-verify line for the retired surface: a deleted source that
    # simply vanishes from the doc leaves the next reader unable to tell it was
    # deliberate rather than overlooked.
    assert "Two independent registration sources" in catalog
    assert ".github/hooks/require-subagent-model.json" in _section_after(
        catalog, "## Provenance and Maintenance", REPO_ROOT
    )
    assert not (REPO_ROOT / ".github" / "hooks" / "require-subagent-model.json").exists()
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

    # ADR-097 retired every tool-call hook, so the generated Copilot dispatcher
    # is gone: no per-event `_manifest.json`, no entries in `hooks.json`. The
    # live-metric derivations this test used to make (shim counts, summed
    # timeouts, host timeout, reduction percentage) have no subject. Assert the
    # zero state instead, then keep pinning the ADR prose, whose dated
    # historical records remain true and must not silently drift.
    assert source_counts == {}, f"a generated dispatcher manifest reappeared: {source_counts}"
    assert copilot_hooks == {}, f"generated Copilot hooks reappeared: {copilot_hooks}"
    assert not (hooks_root / "PreToolUse" / "_manifest.json").exists()
    assert not list(hooks_root.glob("*/_dispatch.py"))
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

    # Issues #4917, #5061, and #5154 (all 2026-08-18) landed independently on
    # three separate branches against the same #5013 baseline, then merged on
    # 2026-08-19. #5061 added the Serena memory worktree-scope guard, whose
    # matcher (`mcp__serena__(write|delete)_memory|...`) does not reduce to a
    # known Claude core tool name, so the host-side matcher union fails open
    # for PreToolUse (see test_committed_matcher_capable_entries_have_matchers
    # in test_dispatcher_matcher_union.py). #4917 added the Serena worktree
    # scope guard, registered as group 12 after renumbering up from its own
    # branch's `-11-` suffix to avoid colliding with #5061's already-landed
    # group 11; its Copilot matcher is likewise unreducible. #5154 deleted
    # `push_pr_script_identity_guard`, `markdownlint_guard`, and
    # `markdown_auto_lint`. Merged, all three compose: three PreToolUse shims
    # (`require_subagent_model`, `serena_memory_scope_guard`,
    # `serena_worktree_scope`) survive, no PostToolUse event remains. The
    # expected values below are the independently reviewed current facts,
    # not a self-confirming echo of whatever the generator happens to emit.
    assert (
        "vendored Claude plugin source and the generated "
        "Copilot manifest each now contain three registrations on one event: three "
        "PreToolUse shims and no PostToolUse shim" in adr_068
    )
    assert "a 66.7 percent reduction" in adr_068
    assert "not for matched-call process savings" in adr_068
    # Whole sentences, not loose fragments. ADR-068 states the manifest and
    # host-entry numbers in three places (a dated Status paragraph, Decision
    # item 4, and a Negative bullet), so a bare "host entry requests N
    # seconds" fragment is satisfied by any one of them and a wrong number in
    # the other two goes unseen. Measured: changing Decision item 4 to 105
    # left the fragment form green because the Status paragraph still said 15.
    assert "the in-process bypass is latent" in adr_068
    assert (
        "three registrations on one event, PreToolUse, and Copilot generation "
        "still emits one host registration" in adr_085
    )
    deletion_note = "deleted `push_pr_script_identity_guard` from both harnesses"
    assert deletion_note in adr_068
    assert deletion_note in adr_071
    assert "Issue #5154 (2026-08-18) deletes the guard outright" in adr_085
    # The 2026-08-11 and 2026-08-14 baselines are dated historical records,
    # not live claims, and stay pinned in all three ADRs precisely because
    # they were true then and the amendment sections say so explicitly.
    assert "growing the active manifest to three shims and 110 seconds of summed timeout" in adr_068
    assert "active manifest contains three shims" in adr_071
    assert "110 seconds of configured timeout" in adr_071
    assert "four registrations across two events" in adr_068
    assert (
        "four registrations across two events: three PreToolUse shims and "
        "one PostToolUse shim" in adr_068
    )
    assert "three PreToolUse shims and one PostToolUse shim" in adr_068
    # The 2026-08-19 three-way merge re-baselines trigger 2 up from #5154's
    # down-baseline; every dated re-baseline step stays pinned as history.
    assert "landing the per-increment threshold at three shims and 30 seconds" in adr_068
    assert "PreToolUse manifest grows beyond three shims" in adr_068
    assert "four registrations across two events" in adr_085
    containment_note = (
        "excluded `push_pr_script_identity_guard` from the generated Copilot inventory only"
    )
    assert containment_note in adr_068
    assert containment_note in adr_071
    assert containment_note in adr_085
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
        # Superseded by the 2026-08-19 three-way merge reconciliation: these
        # read as live claims about inventories that no longer exist as the
        # current state. Their dated forms above are the record.
        "current PreToolUse manifest has two shims with 100 seconds",
        "The current PreToolUse manifest sums to 100 seconds",
        "The current PreToolUse inventory is two shims, and it is timed",
        "current PreToolUse manifest has one shim",
        "current PreToolUse manifest has two shims with 20",
        "re-baselined it back up to two shims and 20 seconds after",
        "PreToolUse manifest grows beyond two shims",
        # A `git push` starting zero dispatcher processes was true for #5154
        # alone on `main`, never true once merged with #5061's and #4917's
        # unreducible matchers; the merge reconciliation states the real
        # 2026-08-19 number.
        "starts no dispatcher process on either harness today",
    ):
        assert stale not in adr_068, f"stale metric survives in ADR-068: {stale}"


def test_adr_068_scopes_its_six_dated_status_paragraphs() -> None:
    """The six dated Status paragraphs must not blur into each other.

    Round 1 found the 2026-08-14 paragraph framed as a blanket "facts
    refresh" with no named policy authority. The fix must land in the
    2026-08-14 paragraph specifically, and the 2026-08-11 paragraph must keep
    its own historical numbers unchanged. Issues #5061 and #5154 each added a
    dated paragraph independently, both 2026-08-18, on separate branches
    against the same #5013 baseline; merging them on 2026-08-19 added a
    fifth. Issue #4917 landed independently the same day on a third branch;
    reconciling it into the #5061+#5154 tree on 2026-08-19 added a sixth.
    Each of the first five owns its own point-in-time numbers unchanged, and
    only the sixth, final 2026-08-19 paragraph may claim the current
    inventory. Explicit reviewed values, not a dynamic re-derivation of the
    same generator output the prose describes.
    """
    text = DISPATCHER_ADR.read_text(encoding="utf-8")
    historical = _normalize(
        _paragraph_after(text, "Amended 2026-08-11 (issue #4874):", DISPATCHER_ADR)
    )
    superseded_5013 = _normalize(
        _paragraph_after(text, "Amended 2026-08-14 (issue #5013):", DISPATCHER_ADR)
    )
    superseded_5061 = _normalize(
        _paragraph_after(text, "Amended 2026-08-18 (issue #5061):", DISPATCHER_ADR)
    )
    superseded_5154 = _normalize(
        _paragraph_after(
            text,
            "Amended 2026-08-18 (issue #5154, landed on `main` independently "
            "of #5061",
            DISPATCHER_ADR,
        )
    )
    superseded_5061_5154 = _normalize(
        _paragraph_after(
            text, "Amended 2026-08-19 (merge of issues #5061 and #5154):", DISPATCHER_ADR
        )
    )
    current = _normalize(
        _paragraph_after(
            text,
            "Amended 2026-08-19 (merge of issue #4917 into the #5061+#5154 "
            "reconciliation",
            DISPATCHER_ADR,
        )
    )

    assert "three shims and 110 seconds of summed timeout" in historical

    assert "ADR-085 Decision 7 is the policy authority" in superseded_5013
    assert "scoped derived-metrics update" in superseded_5013
    assert "100 seconds of configured timeout" in superseded_5013
    assert "host entry requests 105 seconds" in superseded_5013
    assert (
        "same file still lists the guard in Claude Code's canonical dispatch group"
        in superseded_5013
    )
    assert (
        "excluded `push_pr_script_identity_guard` from the generated Copilot "
        "inventory only" in superseded_5013
    )
    assert "ADR-068-071-085-5013-debate-log.md" in superseded_5013

    assert (
        "held three shims, `markdownlint_guard`, `require_subagent_model`, and"
        in superseded_5061
    )
    assert (
        "110 seconds of configured timeout, with a 115-second generated host entry"
        in superseded_5061
    )
    assert "held five registrations across two events" in superseded_5061
    assert "HISTORICAL numbers as they stood before the 2026-08-19" in superseded_5061

    assert "ADR-085 section 8 is the policy authority" in superseded_5154
    assert "superseding the 2026-08-14 Copilot-only exclusion" in superseded_5154
    assert "held one shim with 10 seconds of configured timeout" in superseded_5154
    assert "generated host entry requested 15 seconds" in superseded_5154
    assert "PostToolUse left the generated tree entirely" in superseded_5154
    assert "host matcher union narrowed to `Agent|Task`" in superseded_5154
    assert "scoped derived-metrics update" in superseded_5154
    assert "HISTORICAL `main`-only numbers" in superseded_5154

    assert "mechanical reconciliation of two already-reviewed decisions" in superseded_5061_5154
    assert (
        "two registrations on one event: two PreToolUse shims and no PostToolUse shim"
        in superseded_5061_5154
    )
    assert "sums to 20 seconds of configured timeout, so" in superseded_5061_5154
    assert "generated host entry requests 25 seconds" in superseded_5061_5154
    assert "matcher union still collapses to no `matcher` field at all" in superseded_5061_5154
    assert "reduction is 50.0 percent" in superseded_5061_5154

    assert "three-way mechanical composition of three already-reviewed decisions" in current
    assert (
        "three registrations on one event: three PreToolUse shims"
        in current
    )
    assert "sums to 30 seconds of configured timeout" in current
    assert "generated host entry requests 35 seconds" in current
    assert "renumbered up from the `-11-` suffix" in current
    assert "the reduction is 66.7 percent, up from 50.0 percent" in current

    _refute(current, "100 seconds of configured timeout", "host entry requests 105 seconds")
    _refute(current, "110 seconds of configured timeout", "host entry requests 115 seconds")
    _refute(superseded_5013, "three shims and 110 seconds of summed timeout")
    _refute(superseded_5013, "host entry requests 15 seconds", "ADR-085 section 8 is the policy")
    _refute(superseded_5061, "100 seconds of configured timeout")
    _refute(
        superseded_5154,
        "100 seconds of configured timeout",
        "110 seconds of configured timeout",
    )
    _refute(historical, "scoped derived-metrics update", "ADR-085 Decision 7 is the policy")
    _refute(historical, "ADR-085 section 8 is the policy")


def test_adr_071_scopes_its_six_dated_amendment_sections() -> None:
    """Current-vs-historical boundary, on ADR-071's six dated subsections.

    Issues #5061 and #5154 landed independently on separate branches, both
    dated 2026-08-18, against the same #5013 baseline. Merging them on
    2026-08-19 added a fifth dated subsection. Issue #4917 landed
    independently the same day on a third branch; reconciling it into the
    #5061+#5154 tree on 2026-08-19 added a sixth. Each of the first five
    keeps its own point-in-time numbers unchanged; only the sixth, final
    2026-08-19 reconciliation may claim the current inventory.
    """
    text = RUNTIME_ADR.read_text(encoding="utf-8")
    historical = _normalize(
        _section_after(
            text,
            "### 2026-08-11 amendment: require-subagent-model gate (issue #4874)",
            RUNTIME_ADR,
        )
    )
    superseded_5013 = _normalize(
        _section_after(
            text,
            "### 2026-08-14 amendment: push-pr identity guard excluded from "
            "Copilot generation (issue #5013)",
            RUNTIME_ADR,
        )
    )
    superseded_5061 = _normalize(
        _section_after(
            text,
            "### 2026-08-18 amendment: Serena memory worktree-scope guard "
            "(issue #5061)",
            RUNTIME_ADR,
        )
    )
    superseded_5154 = _normalize(
        _section_after(
            text,
            "### 2026-08-18 amendment: push-pr identity guard deleted from "
            "both harnesses (issue #5154, landed on `main` independently of "
            "#5061 above)",
            RUNTIME_ADR,
        )
    )
    superseded_5061_5154 = _normalize(
        _section_after(
            text,
            "### 2026-08-19 reconciliation: merging issues #5061 and #5154",
            RUNTIME_ADR,
        )
    )
    current = _normalize(
        _section_after(
            text,
            "### 2026-08-19 reconciliation: merging issue #4917 into the "
            "#5061+#5154 tree",
            RUNTIME_ADR,
        )
    )

    assert "three shims with 110 seconds of configured timeout" in historical
    assert "115 seconds" in historical

    assert "ADR-085 Decision 7 is the policy authority" in superseded_5013
    assert "scoped runtime-contract update" in superseded_5013
    assert "100 seconds of configured timeout" in superseded_5013
    assert "105 seconds" in superseded_5013
    assert "Copilot excludes the guard from generation entirely" in superseded_5013
    assert "ADR-068-071-085-5013-debate-log.md" in superseded_5013

    assert (
        "contains three shims, `markdownlint_guard`, `require_subagent_model`, and"
        in superseded_5061
    )
    assert "110 seconds of configured timeout" in superseded_5061
    assert "115 seconds" in superseded_5061
    assert "carries no" in superseded_5061

    assert "ADR-085 section 8 is the policy authority" in superseded_5154
    assert "deleted `push_pr_script_identity_guard` from both harnesses" in superseded_5154
    assert "contains one shim, `require_subagent_model`, with 10 seconds" in superseded_5154
    assert "host entry requests 15 seconds" in superseded_5154
    assert "narrows to `Agent|Task`" in superseded_5154
    assert "PostToolUse leaves the generated tree entirely" in superseded_5154
    assert "scoped runtime-contract update" in superseded_5154
    assert "describe `main` alone at the moment this" in superseded_5154

    assert "mechanical composition of two already-reviewed decisions" in superseded_5061_5154
    assert "contains two shims" in superseded_5061_5154
    assert "summing to 20" in superseded_5061_5154
    assert "generated host entry requests 25 seconds" in superseded_5061_5154
    assert "stays collapsed to no matcher" in superseded_5061_5154
    assert "three process starts total" in superseded_5061_5154
    assert "PostToolUse stays out of the generated tree" in superseded_5061_5154

    assert "three-way mechanical composition of three already-reviewed decisions" in current
    assert "manifest contains three shims" in current
    assert "summing to 30 seconds of configured timeout" in current
    assert "generated host entry requests 35 seconds" in current
    assert "renumbered up from the `-11-` suffix" in current
    assert "four process starts total" in current
    assert "No two Claude-side matchers overlapped before this merge" in current

    _refute(superseded_5013, "three shims with 110 seconds of configured timeout", "115 seconds")
    _refute(superseded_5013, "host entry requests 15 seconds", "ADR-085 section 8 is the policy")
    _refute(superseded_5061, "105 seconds", "ADR-085 Decision 7 is the policy")
    _refute(superseded_5154, "105 seconds", "115 seconds", "ADR-085 Decision 7 is the policy")
    _refute(historical, "scoped runtime-contract update", "ADR-085 Decision 7 is the policy")
    _refute(historical, "ADR-085 section 8 is the policy")
    _refute(current, "105 seconds", "generated host entry requests 15 seconds")

    status = _normalize(RUNTIME_ADR.read_text(encoding="utf-8"))
    assert "Amended 2026-08-11 (issue #4874)" in status
    assert "Amended 2026-08-14 (issue #5013)" in status
    assert "Amended 2026-08-18 (issue #5061)" in status
    assert "Amended 2026-08-18 (issue #5154, landed on `main` independently of #5061" in status
    assert "Amended 2026-08-19 (merge of issues #5061 and #5154)" in status
    assert "ADR-068-071-085-metric-refresh-debate-log.md" in status
    assert "ADR-068-071-085-5013-debate-log.md" in status


def test_adr_085_decision_seven_applies_eligibility_test_to_the_exclusion() -> None:
    """ADR-085 Decision 7 must apply Decision 1's test, not just cite it.

    Issue #5154 superseded this section without deleting it: the containment
    incident and the reasoning applied to it are the record of why the guard
    was contained before it was removed. The section must therefore keep its
    reasoning AND say plainly that it is history, so a later reader cannot
    mistake it for the current disposition.
    """
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
    assert (
        "Superseded on 2026-08-18 by section 8, which deletes the guard from "
        "both harnesses." in decision_seven
    )
    assert "Read it as history, not as the current disposition." in decision_seven


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
        "A Windows load test of 32 calls across 8 workers completes without a false denial.",
        "Latency stays under a 500ms p95 and a 1 second maximum across that load test.",
        "The measurement runs against a real Copilot CLI probe, not a simulated harness.",
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


def test_issue_5013_adrs_retain_the_exclusion_record_as_history() -> None:
    """The 2026-08-14 record survives #5154 in every affected ADR.

    Before #5154 these phrases were live claims about who kept the guard.
    They are now the historical record of the containment step that preceded
    deletion, and they stay asserted for that reason: a later cleanup that
    quietly drops them erases why the guard was contained before it was
    removed. The live disposition is asserted separately below.
    """
    exclusion_note = (
        "excluded `push_pr_script_identity_guard` from the generated Copilot inventory only"
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


def test_issue_5154_adrs_state_deletion_from_both_harnesses() -> None:
    """Every affected ADR must say, in its own words, that the guard is gone.

    The three facts the owner ruling turns on: the guard is deleted from both
    harnesses, the Copilot exclusion is therefore moot, and the protected
    outcome now rests on the server-side pr-validation gate. A reader landing
    on any one of the three ADRs must reach all three facts without having to
    open the other two.
    """
    for path in (DISPATCHER_ADR, RUNTIME_ADR, PERMISSION_ADR):
        normalized = _normalized_text(path)
        assert "issue #5154" in normalized.lower(), path
        assert "both harnesses" in normalized, path
        assert ".github/workflows/pr-validation.yml" in normalized, path

    # The derived ADRs must name the policy owner; the owner must carry the
    # decision itself rather than pointing at someone else.
    for path in (DISPATCHER_ADR, RUNTIME_ADR):
        assert "ADR-085 section 8 is the policy authority" in _normalized_text(path), path
    assert (
        "### 8. `push_pr_script_identity_guard`: deleted from both harnesses (D-D)"
        in _normalized_text(PERMISSION_ADR)
    )

    assert "the 2026-08-14 Copilot-only exclusion is moot" in _normalized_text(RUNTIME_ADR)
    assert "superseding the 2026-08-14 Copilot-only exclusion" in _normalized_text(DISPATCHER_ADR)
    assert (
        "the Copilot exclusion and its `copilotExclude: true` field are moot"
        in _normalized_text(PERMISSION_ADR)
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


def test_adr_085_status_records_the_2026_08_18_deletion() -> None:
    """Status must carry the deletion, its driver, and its replacement gate.

    Same rule the containment incident follows: a reader who stops at Status
    must not come away believing the guard still runs anywhere.
    """
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    status = _normalize(_section_after(text, "## Status", PERMISSION_ADR))

    assert (
        "On 2026-08-18 issue #5154 deleted `push_pr_script_identity_guard` "
        "from both harnesses" in status
    )
    assert "No shim remains to exclude" in status
    # Round 2 owner ruling: the warrant is the owner's security judgment, and
    # cost is context. A Status paragraph that reinstates the ROI bar as the
    # trigger puts the document back in conflict with ADR-084's carve-out.
    assert "The warrant is the owner's own security judgment, not a cost-benefit veto." in status
    assert "This decision does not invoke ADR-084's ROI bar" in status
    assert "a 102 ms tax on every Bash call" in status
    assert "Cost is context for that judgment, not its authority." in status
    _refute(status, "The trigger is ADR-084's vendored-hook ROI bar")
    assert "`.github/workflows/pr-validation.yml`" in status
    assert "<https://github.com/rjmurillo/ai-agents/issues/5154>" in status


def test_adr_085_decision_eight_records_the_owner_classification_and_gate() -> None:
    """Section 8 must show the reintroduction gate being met, not skipped.

    Decision 7 gate 8 names "deleted" as a valid terminal classification, so
    the deletion is that gate resolving rather than an exception to it. The
    section must also name what still enforces the outcome and what risk the
    deletion accepts, or it reads as a cost-only decision.
    """
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_eight = _normalize(
        _section_after(
            text,
            "### 8. `push_pr_script_identity_guard`: deleted from both harnesses (D-D)",
            PERMISSION_ADR,
        )
    )

    assert "Issue #5154 (2026-08-18) deletes the guard outright" in decision_eight
    assert "This supersedes section 7." in decision_eight
    assert "**Owner classification.**" in decision_eight
    assert "rjmurillo classified it as deleted" in decision_eight
    assert "gate 8 names deletion as a valid terminal answer" in decision_eight
    assert "**Decision driver: the owner's security judgment.**" in decision_eight
    assert "It is not the authority for it." in decision_eight
    assert "The 102 ms figure is the median of five timings taken before deletion" in decision_eight
    # Round 2: an unreproducible number must say so where it is stated.
    assert (
        "Because this change deletes that dispatch group, the number is not "
        "reproducible from the tree afterward." in decision_eight
    )
    assert (
        "**Where the protected outcome is enforced now, and what that does not cover.**"
        in decision_eight
    )
    for check in (
        "Validate PR Description vs Diff",
        "Validate PR Description Standards",
        "Enforce Blocking Issues",
        "`.github/scripts/parse_pr_standards.py`",
        "`scripts/ci/enforce_pr_validation.py`",
    ):
        assert check in decision_eight, check
    assert "**Residual risk accepted.**" in decision_eight
    assert (
        "neither harness now denies a prompt-injected repository lookalike "
        "`new_pr.py` at agent time" in decision_eight
    )
    assert "**Reversibility.**" in decision_eight


def test_adr_085_decision_eight_complies_with_the_adr_084_carve_out() -> None:
    """The carve-out must be quoted and complied with, not argued away.

    ADR-084 lines 145 to 148 forbid using its ROI bar to retire a security
    control. Round 1 used that bar as the driver anyway. The fix is to change
    the warrant, so the section has to name the carve-out, quote it, and say
    it is not invoking the bar. The quote is checked against the live ADR-084
    text below so a reworded carve-out cannot leave a stale quote here.
    """
    carve_out_source = REPO_ROOT / ".agents" / "architecture" / "ADR-084-vendored-hook-roi-bar.md"
    quoted = (
        "It does not authorize retiring an actual security control. A hook "
        "that enforces a security property in consumer repos earns its place "
        "by that property, not by an ROI cost-benefit veto, and a future "
        "reviewer must not use this ADR's ROI bar to retire it."
    )
    # Not a tautology: this reads the cited ADR, not the citing one. If ADR-084
    # rewords the carve-out, this fails and the quote gets refreshed.
    assert quoted in _normalized_text(carve_out_source), carve_out_source

    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_eight = _normalize(
        _section_after(
            text,
            "### 8. `push_pr_script_identity_guard`: deleted from both harnesses (D-D)",
            PERMISSION_ADR,
        )
    )

    assert (
        "**ADR-084's carve-out, and why this decision does not invoke the ROI bar.**"
        in decision_eight
    )
    # The citation must resolve, so it names the durable section anchor rather
    # than a line range. The 2026-08-18 rule 6 amendment moved the carve-out
    # from line 145 to 169 and orphaned 11 line-range citations across ADR-068,
    # ADR-071, and ADR-085; a range pins a number the next amendment shifts
    # again, which is the wrong-citation failure canonical-source-mirror.md
    # blocks on. The verbatim quote below is what actually proves the pointer
    # lands on the carve-out.
    assert "ADR-084-vendored-hook-roi-bar.md" in decision_eight
    assert '"What this ADR does NOT do"' in decision_eight
    assert "145-148" not in decision_eight, (
        "line-range citation reintroduced; cite the section anchor instead"
    )
    assert quoted in decision_eight
    assert "That carve-out binds." in decision_eight
    assert (
        "This decision complies with it by changing the warrant, not by "
        "arguing the carve-out away" in decision_eight
    )
    assert (
        "ADR-084's ROI bar is not cited as authority anywhere in this decision." in decision_eight
    )


def test_every_pr_validation_claim_carries_the_outcome_not_execution_qualifier() -> None:
    """The overclaim must be fixed everywhere, not corrected in one paragraph.

    Round 2 found Status and the References restatement asserting that
    pr-validation.yml carries the outcome the guard protected, while the
    Residual-risk paragraph said it catches the outcome and not the execution.
    A document that says both is a document a reader can quote either way. So
    every block that names the workflow must carry the qualifier itself.
    """
    # The verb is part of the qualifier. Measured: a mutation that changed
    # only "catches" to "carries" left a bare "outcome, not the execution"
    # check green, because the mutated block still contained that substring
    # while asserting the overclaim the substring was meant to forbid.
    qualifier = "catches the outcome, not the execution"
    checked = 0
    for path in (PERMISSION_ADR, DISPATCHER_ADR, RUNTIME_ADR):
        text = path.read_text(encoding="utf-8")
        for block in text.split("\n\n"):
            if "pr-validation.yml" not in block:
                continue
            checked += 1
            assert qualifier in _normalize(block), f"{path}: unqualified block: {block[:120]}"
        # The round-1 wording, banned document-wide so it cannot reappear in a
        # block that does not itself name the workflow.
        _refute(
            text,
            "carries the protected outcome",
            "that carries the outcome",
            source=path,
        )
    # Report the scope with the result: a zero-finding sweep over zero blocks
    # proves nothing. Measured composition at the time of writing: six blocks,
    # three in ADR-085 (Status, section 8, References), two in ADR-068 (the
    # 2026-08-18 Status amendment and References), one in ADR-071 (the
    # 2026-08-18 amendment section).
    assert checked == 6, f"expected 6 pr-validation blocks, scanned {checked}"


def test_adr_085_states_workflows_are_outside_the_vendored_surface() -> None:
    """A consumer gets no compensating control, not a weaker one."""
    text = _normalized_text(PERMISSION_ADR)

    assert (
        "`.github/workflows/` is not part of the vendored plugin surface, so a "
        "plugin consumer gets no compensating control at all for this vector." in text
    )
    assert (
        "A plugin consumer inherits no workflow from this repository, so for "
        "this vector a consumer gets no compensating control at all, not a "
        "weaker one." in text
    )


def test_adr_085_decision_nine_records_the_markdownlint_placement_judgment() -> None:
    """Section 9 must be section-8 shaped and must not lean on the ROI bar."""
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_nine = _normalize(
        _section_after(
            text,
            "### 9. `markdownlint_guard`: deleted, markdown linting belongs in Git hooks (D-E)",
            PERMISSION_ADR,
        )
    )

    for heading in (
        "**Owner classification.**",
        "**Rationale: placement, not ROI.**",
        "**Settled fact: this guard self-neutered in consumer repos.**",
        "**Residual risk accepted.**",
        "**Reversibility.**",
    ):
        assert heading in decision_nine, heading
    assert "linting can be done outside the harness, with Git hooks or Lefthook" in decision_nine
    assert (
        "not in a per-tool-call agent hook that spawns an interpreter on every "
        "`git push` the model issues" in decision_nine
    )
    assert "no ROI argument is offered here, so the carve-out does not arise" in decision_nine


def test_adr_085_decision_nine_settles_the_self_neuter_fact_with_the_source() -> None:
    """The disputed fact must be settled by quoted code, not by assertion.

    Two reviewers disagreed. The ADR has to carry the actual call and the
    actual delegation, and it has to say the ADR-084 debate log got it wrong.
    The debate-log claim is read here from the live file, so this fails if the
    log is edited and the ADR's correction goes stale.
    """
    debate_log = REPO_ROOT / ".agents" / "critique" / "ADR-084-debate-log.md"
    assert "not `skip_if_consumer_repo` gated and run in consumer repos" in _normalized_text(
        debate_log
    ), debate_log

    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_nine = _normalize(
        _section_after(
            text,
            "### 9. `markdownlint_guard`: deleted, markdown linting belongs in Git hooks (D-E)",
            PERMISSION_ADR,
        )
    )

    assert "`if skip_if_consumer_repo(name): return 0`" in decision_nine
    assert '`return run_guard(_validate, ["*.md"], GUARD_NAME)`' in decision_nine
    assert (
        "the guard therefore returned 0 before it read stdin, so it never ran "
        "`markdownlint-cli2` there" in decision_nine
    )
    assert "`.agents/critique/ADR-084-debate-log.md:17` says the opposite" in decision_nine
    assert "That verification was wrong, and this decision corrects it." in decision_nine
    assert (
        "a standing violation of ADR-084 rule 4, which bans self-neutering "
        "vendored hooks" in decision_nine
    )


def test_adr_085_decision_ten_accepts_the_consumer_coverage_drop() -> None:
    """Section 10 must state the drop to zero as accepted, not as continuity.

    The asymmetry with section 9 is the whole point: the push guard skipped
    consumer repos, this hook did not, so this is where the consumer loss is
    real and must be owned.
    """
    text = PERMISSION_ADR.read_text(encoding="utf-8")
    decision_ten = _normalize(
        _section_after(
            text,
            "### 10. `markdown_auto_lint`: deleted, the same placement judgment (D-F)",
            PERMISSION_ADR,
        )
    )

    for heading in (
        "**Owner classification.**",
        "**Rationale: placement, not ROI.**",
        "**Residual risk accepted, and it is larger here than in section 9.**",
        "**Reversibility.**",
    ):
        assert heading in decision_ten, heading
    assert (
        "this deleted hook carried no `skip_if_consumer_repo` call anywhere in "
        "its source, so it did run in consumer repos" in decision_ten
    )
    assert (
        "a consumer who installs neither Git hooks nor Lefthook now has no "
        "markdown gate from this plugin at all" in decision_ten
    )
    assert (
        "It is not continuity, and this decision does not present it as continuity." in decision_ten
    )
    assert "no ROI argument is offered" in decision_ten


def test_derived_adrs_do_not_name_the_roi_bar_as_the_deletion_driver() -> None:
    """ADR-068 and ADR-071 repeated the retired driver chain uncited.

    They may cite ADR-084 only to say the carve-out is why the bar is not the
    warrant. Naming it as the driver is the round-2 defect.
    """
    for path in (DISPATCHER_ADR, RUNTIME_ADR):
        text = _normalized_text(path)
        _refute(
            text,
            "the ADR-084 vendored-hook ROI bar, and the server-side",
            "the ADR-084 ROI driver",
            "The vendored-hook ROI bar that drove the 2026-08-18 deletion.",
            source=path,
        )
        # Section anchor, not a line range: see the note in
        # test_adr_085_decision_eight_complies_with_the_adr_084_carve_out.
        assert "ADR-084-vendored-hook-roi-bar.md" in text, path
        assert '"What this ADR does NOT do"' in text, path
        assert "145-148" not in text, (
            f"{path}: line-range citation reintroduced; cite the section anchor"
        )
        assert "not ADR-084's ROI bar" in text, path


def test_adr_082_marks_the_deleted_group_example_as_historical() -> None:
    """ADR-082 cited a group this change deletes as a live example."""
    text = _normalized_text(
        REPO_ROOT / ".agents" / "architecture" / "ADR-082-claude-hook-group-dispatch.md"
    )

    assert "`plugin-posttooluse-1-markdown_auto_lint` matched only" in text
    assert (
        "That group is historical: issue #5154 (2026-08-18) deleted it under "
        "ADR-085 section 10, so read it here as a worked example, not as a "
        "live group." in text
    )
    _refute(
        text,
        "`plugin-posttooluse-1-markdown_auto_lint` matches today only",
        source=REPO_ROOT / ".agents" / "architecture" / "ADR-082-claude-hook-group-dispatch.md",
    )


def test_adr_068_dependent_components_table_matches_the_registration_count() -> None:
    """Round 2 found "Four vendored plugin registrations" against a count of one.

    Merging issue #5061 (adds `serena_memory_scope_guard`), issue #4917
    (adds `serena_worktree_scope`, renumbered to group 12 to avoid
    colliding with #5061's already-landed group 11), and issue #5154
    (deletes three other hooks) on 2026-08-19 landed the count at three, not
    one: #5154 alone would have left one, but #5061 and #4917 each
    independently added a survivor.
    """
    hooks = _read_json(REPO_ROOT / ".claude" / "hooks" / "hooks.json")["hooks"]
    registrations = sum(map(len, hooks.values()))
    text = _normalized_text(DISPATCHER_ADR)

    # ADR-097 retired every tool-call hook, so the count is now zero. The row
    # keeps its historical chain (three after the three-way merge, four before
    # it) because those are dated records, not live claims.
    assert registrations == 0
    assert (
        "Zero vendored plugin registrations after ADR-097 retired every "
        "tool-call hook (three after merging issues #4917, #5061, and #5154; "
        "four before any of the three)" in text
    )
    _refute(text, "| Four vendored plugin registrations", source=DISPATCHER_ADR)
    _refute(text, "One vendored plugin registration after issue #5154", source=DISPATCHER_ADR)
    _refute(text, "| Two vendored plugin registrations", source=DISPATCHER_ADR)
    _refute(text, "| Three vendored plugin registrations", source=DISPATCHER_ADR)


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
