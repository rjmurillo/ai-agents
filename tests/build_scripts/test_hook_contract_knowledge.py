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
PLATFORM_TEMPLATE = REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_text(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


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
        "## Plugin Version Bump Rule",
    ),
    (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-generation-and-release" / "SKILL.md",
        "### Phase 4: Plugin Versioning Discipline",
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


def test_reference_lists_exact_copilot_event_set() -> None:
    events = _text_code_block_after(
        _reference_text(),
        "The exact 14 native events are:",
    )

    assert events == COPILOT_NATIVE_EVENTS


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
    text = _reference_text()

    assert "| Stop | None | Direct entries if added, one JSON decision per command |" in text
    assert "| SessionEnd | SessionEnd | Direct lifecycle event, never a Stop alias |" in text
    assert "host merges structured decisions" not in text
    assert "Stop: SessionEnd" not in text
    assert "Omitting `decision` permits completion." in text
    assert "`allow` permits completion" not in text


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
    assert "sentinel comment `# AUTO-GENERATED MATCHER SHIM (REQ-003-007)` at line 1" not in section
    assert "shall NOT emit the matcher" not in section
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
    assert "observe dispatcher passes stdout through" not in text


def test_reference_versions_matcher_and_timeout_evidence() -> None:
    text = _reference_text()

    assert "Matchers are supported." in text
    assert "Copilot CLI 1.0.57 and 1.0.58 had matcher bugs." in text
    assert "| PreToolUse exit 2 | Denies |" in text
    assert "| Any command-hook timeout | Fails open, including policy PreToolUse |" in text
    assert "PreCompact | None | Supported observe/discard policy" in text
    probe = (SKILL_ROOT / "references" / "probe-evidence.md").read_text(encoding="utf-8")
    assert "Manual `/compact` is therefore a negative control" in probe
    assert "Automatic-compaction delivery remains unmeasured" in probe


def test_reference_labels_unstable_fields_and_cloud_limits() -> None:
    text = _reference_text()

    assert "implementation-only SDK types" in text
    assert "Cloud agent loads `.github/hooks/*.json` only" in text
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
    text = _reference_text()

    assert '"permissionDecision": "allow"' in text
    assert "Do not emit Claude's nested `hookSpecificOutput` envelope" in text
    assert '"behavior": "allow"' in text
    assert "`behavior` accepts only `allow` or `deny`." in text
    assert "The adapter must emit no stdout" in text
    assert '"decision": "block"' in text


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
    generated_hooks = _read_json(
        REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json"
    )["hooks"]
    dispatch_groups = _read_json(REPO_ROOT / ".claude" / "hooks" / "dispatch_groups.json")[
        "groups"
    ]

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

    sidecar = OFFICIAL_SOURCES.read_text(encoding="utf-8")
    assert "Shared Stop producers can emit this shape on" in sidecar
    assert "both harnesses." in sidecar


def test_reference_preserves_single_structured_output_boundary() -> None:
    text = _reference_text()
    sidecar = OFFICIAL_SOURCES.read_text(encoding="utf-8")
    rule = (REPO_ROOT / ".claude" / "rules" / "generated-artifacts.md").read_text(encoding="utf-8")

    assert "at most one final JSON document from each command hook" in text
    assert '`{"additionalContext":"..."}` object' in text
    assert "Failed-observer partial output is discarded." in text
    assert "when all observers are silent." in text
    assert "no config-file output field for PreCompact" in text
    assert "| PreCompact | DOCS SILENT:" in sidecar
    assert "| UserPromptSubmitted / UserPromptSubmit | DOCS SILENT:" in sidecar
    assert "Preserve one valid structured output per command hook" in rule
    assert "Byte passthrough is not output merging." in rule


def test_official_sidecar_pins_sources_and_refresh_procedure() -> None:
    text = OFFICIAL_SOURCES.read_text(encoding="utf-8")

    assert "https://docs.github.com/en/copilot/reference/hooks-reference" in text
    assert "github/docs/blob/0b02cd6336f4eebda1e409b45a89dab5c2193d9a" in text
    assert "raw.githubusercontent.com/github/copilot-cli/fd24cea5" in text
    assert "https://code.claude.com/docs/en/hooks" in text
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
    assert "The exact 14 native events are:" in reference
    assert "The adapter must emit no stdout" in reference
    assert "| PreCompact | None | Supported observe/discard policy" in reference
    assert "| Stop | None | Direct entries if added" in reference


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
    assert "Does not exist" not in requirement
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
        text = path.read_text(encoding="utf-8")
        for stale_claim in stale_claims:
            assert stale_claim not in text, (path, stale_claim)


def test_operational_skills_read_plugin_versions_from_manifests() -> None:
    semver_literal = re.compile(r"\b\d+\.\d+\.\d+\b")

    for path, marker in PLUGIN_VERSION_SECTIONS:
        section = _section_after(path.read_text(encoding="utf-8"), marker, path)
        assert "Current values are intentionally not copied into this skill." in section
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
    assert "registers 7 events" not in architecture
    assert "expected 7 and 14" not in architecture
    assert "8 events / 23 matcher groups" not in architecture


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

    assert source_counts == {"PreToolUse": 1, "PostToolUse": 1}
    assert source_total == 2
    assert host_total == 2
    assert round(reduction, 1) == 0.0
    assert "two registrations across two events" in adr_068
    assert "one PreToolUse shim and one PostToolUse shim" in adr_068
    assert "saves no current host process start" in adr_068
    assert len(pretool_manifest["shims"]) == 1
    assert timeout_total == 90
    assert "current PreToolUse manifest has one shim" in adr_068
    assert "90-second configured value" in adr_068
    assert f"host entry requests {host_timeout} seconds" in adr_068
    assert "five seconds of dispatcher headroom" in adr_068
    assert "cannot bypass a later PreToolUse shim" in adr_068
    assert "two registrations across two events" in adr_085
    assert "active manifest contains one shim" in adr_071
    assert "90-second configured timeout" in adr_071
    assert f"host entry requests {host_timeout} seconds" in adr_071
    assert timeout_headroom == 5


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

    assert "The skill-first hook blocks gh pr create" not in pr_rules
    assert "Raw `gh` may be blocked by `invoke_skill_first_guard.py`" not in observations
    assert "This repo has a PreToolUse hook" not in script_reference
    assert "PR #3293 implemented Retirement" in decision_memory


def test_generation_skill_requires_an_explicit_reason_for_hook_drops() -> None:
    generation = (
        REPO_ROOT / ".claude" / "skills" / "ai-agents-generation-and-release" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "an unexplained drop means contract drift" in generation
    assert "Drops are unsupported Copilot events, by design" not in generation
