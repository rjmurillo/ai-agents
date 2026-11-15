"""Contract tests for the review skill's technical-review contract (issue #5395).

Covers: the contract file states every required section and a verdict rule
that `extract_verdict` parses; the capability blocks declare the owners and
edges the graph relies on; the `review` template runs the step 4c pass with
the CONTEXT_MODE-prefixed diff; and `code-reviewer` depends on the contract
instead of restating the doctrine that moved into it.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import pytest
import yaml

from scripts.ai_review_common.verdict import extract_verdict, merge_verdicts

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_CONTRACT = PROJECT_ROOT / ".claude" / "skills" / "review" / "resources" / "technical-review.md"
_REVIEW_TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "review.SKILL.md.tmpl"
_FENCE_TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "chestertons-fence.SKILL.md.tmpl"
_AGENT_SHARED = PROJECT_ROOT / "templates" / "agents" / "code-reviewer.shared.md"
_UNTRUSTED_AGENT_PARTIAL = (
    PROJECT_ROOT / "templates" / "agents" / "partials" / "untrusted-content.mustache"
)

_REQUIRED_CONTRACT_HEADINGS = (
    "Scope and coverage accounting",
    "Untrusted content",
    "Necessity and design first",
    "Evidence order",
    "Convention discovery",
    "Reasoning protocol",
    "Edge cases and concurrency",
    "Test semantics",
    "Comments",
    "Code-intent analysis",
    "Yell-test proposal",
    "Specialist routing",
    "Finding shape",
    "Verdict",
)

# Sentences distinctive to the doctrine that moved out of the agent.
_MOVED_DOCTRINE_SENTENCES = (
    "Report only findings scored 80 or higher",
    "Do not assume a file named CLAUDE.md exists",
    "Emit findings in this exact order, with no preamble beyond the Summary",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required file: {path}"
    return path.read_text(encoding="utf-8")


def _headings(text: str) -> set[str]:
    return set(re.findall(r"(?m)^## (.+?)\s*$", text))


def _capability(text: str) -> dict:
    """Return the parsed metadata.capability block of a frontmatter file."""
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, "no frontmatter block"
    front = yaml.safe_load(match.group(1)) or {}
    return (front.get("metadata") or {}).get("capability") or {}


def _moved_doctrine_in(text: str) -> str | None:
    return next((s for s in _MOVED_DOCTRINE_SENTENCES if s in text), None)


def _verdict_rules(text: str) -> dict[str, str]:
    """Map each numbered verdict rule's lead clause to the token it names."""
    section = text.split("## Verdict", 1)[1]
    rules = re.findall(r"(?ms)^\d+\. (.+?): `(PASS|WARN|CRITICAL_FAIL)`\.", section)
    return {clause.split(",")[0].strip(): token for clause, token in rules}


class TestContractShape:
    TEXT = _read(_CONTRACT)

    def test_every_required_heading_is_a_real_h2(self) -> None:
        missing = set(_REQUIRED_CONTRACT_HEADINGS) - _headings(self.TEXT)
        assert not missing, missing

    def test_heading_parser_rejects_a_heading_that_is_only_prose(self) -> None:
        assert "Verdict" not in _headings("The Verdict section says ## Verdict inline.")

    def test_post_2023_invariant_is_stated(self) -> None:
        assert "evidence earns preservation, complexity does not" in self.TEXT

    def test_context_mode_other_than_full_is_partial(self) -> None:
        assert "anything but `full` is partial context" in self.TEXT

    def test_no_em_or_en_dash(self) -> None:
        assert not {chr(0x2013), chr(0x2014)} & set(self.TEXT)


class TestContractVerdictRule:
    TEXT = _read(_CONTRACT)

    def test_blocking_maps_to_critical_fail(self) -> None:
        assert _verdict_rules(self.TEXT)["Any `blocking` finding remaining"] == "CRITICAL_FAIL"

    def test_unverified_state_cannot_reach_pass(self) -> None:
        section = self.TEXT.split("## Verdict", 1)[1]
        warn_rule = re.search(r"(?ms)^2\. (.+?)`WARN`", section)
        assert warn_rule, "no WARN rule"
        for state in ("partial", "hazard", "skipped specialist", "neither reviewed nor excluded"):
            assert state in warn_rule.group(1), state

    def test_rule_parser_rejects_a_rule_with_no_token(self) -> None:
        assert _verdict_rules("## Verdict\n\n1. Any finding: `MAYBE`.\n") == {}

    @pytest.mark.parametrize("token", ["PASS", "WARN", "CRITICAL_FAIL"])
    def test_every_emitted_token_parses(self, token: str) -> None:
        assert extract_verdict(f"findings\nVERDICT: {token}\n") == token

    def test_template_form_line_does_not_parse_as_a_verdict(self) -> None:
        assert extract_verdict("VERDICT: PASS|WARN|CRITICAL_FAIL\n") != "PASS"

    def test_correctness_warn_is_not_hidden_by_other_passes(self) -> None:
        assert merge_verdicts(["PASS", "PASS", "WARN"]) == "WARN"


class TestCapabilityBlocks:
    def test_review_owns_technical_review_and_depends_on_archaeology(self) -> None:
        cap = _capability(_read(_REVIEW_TEMPLATE))
        assert cap["kind"] == "orchestrator"
        assert cap["owns"] == ["technical-review"]
        assert set(cap["depends-on"]) == {"code-archaeology", "untrusted-content-handling"}

    def test_fence_owns_archaeology_with_no_edge_back(self) -> None:
        cap = _capability(_read(_FENCE_TEMPLATE))
        assert cap["kind"] == "reusable-primitive"
        assert cap["owns"] == ["code-archaeology"]
        assert "technical-review" not in (cap.get("depends-on") or [])

    def test_agent_owns_nothing_and_depends_on_the_contract(self) -> None:
        cap = _capability(_read(_AGENT_SHARED))
        assert cap["kind"] == "specialized-implementation"
        assert not cap.get("owns")
        assert set(cap["depends-on"]) == {"technical-review", "untrusted-content-handling"}

    def test_capability_parser_sees_a_wrong_owner(self) -> None:
        text = "---\nmetadata:\n  capability:\n    owns: [other]\n---\nbody\n"
        assert _capability(text)["owns"] != ["technical-review"]


class TestReviewTemplateRunsTheCorrectnessPass:
    TEXT = _read(_REVIEW_TEMPLATE)

    def _step_4c(self) -> str:
        match = re.search(r"(?m)^4c\. .+$", self.TEXT)
        assert match, "step 4c missing"
        return match.group(0)

    def test_step_4c_dispatches_code_reviewer_with_the_contract(self) -> None:
        step = self._step_4c()
        assert "Delegate to the `code-reviewer` agent" in step
        assert "resources/technical-review.md" in step
        assert "general-purpose" in step

    def test_step_4c_passes_the_context_mode_prefixed_diff(self) -> None:
        assert "CONTEXT_MODE-prefixed diff" in self._step_4c()

    def test_merge_step_includes_the_correctness_verdict(self) -> None:
        merge = re.search(r"(?m)^7\. .+$", self.TEXT)
        assert merge and "step 4c correctness verdict" in merge.group(0)


class TestAgentCarriesNoMovedDoctrine:
    TEXT = _read(_AGENT_SHARED)

    def test_no_moved_doctrine_sentence(self) -> None:
        assert _moved_doctrine_in(self.TEXT) is None

    def test_leak_detector_reports_a_leak(self) -> None:
        leaked = "Some prose. Report only findings scored 80 or higher. More prose."
        assert _moved_doctrine_in(leaked) == "Report only findings scored 80 or higher"

    def test_agent_loads_the_contract_from_the_copilot_root_first(self) -> None:
        first = re.search(r"(?m)^1\. `(.+?)`$", self.TEXT)
        assert first and first.group(1).startswith("${COPILOT_PLUGIN_ROOT:-")

    def test_untrusted_block_stays_byte_identical_to_the_partial(self) -> None:
        assert _read(_UNTRUSTED_AGENT_PARTIAL) in self.TEXT


_SHIP_RESOLUTION = (
    PROJECT_ROOT
    / "src"
    / "claude"
    / "skills"
    / "ship"
    / "references"
    / "review-marker-resolution.md"
)
_RENDERED_AGENTS = (
    PROJECT_ROOT / "src" / "claude" / "agents" / "code-reviewer.md",
    PROJECT_ROOT / "src" / "copilot-cli" / "agents" / "code-reviewer.agent.md",
    PROJECT_ROOT / "src" / "vs-code-agents" / "code-reviewer.agent.md",
)
_ROOT_VARS = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
_CONTRACT_REL = "skills/review/resources/technical-review.md"


def _candidates(text: str) -> list[str]:
    """Return the contract candidates in resolution order.

    The numbered checkout candidates come first, then each installed-plugin
    root named in the "Otherwise try" sentence, joined to the contract path.
    """
    section = text.split("## Load the contract", 1)[1].split("Apply the loaded contract", 1)[0]
    numbered = re.findall(r"(?m)^\d+\. `(.+?)`$", section)
    sentence = re.search(r"Otherwise try `[^`]+` under (.+?) \(", section, re.DOTALL)
    assert sentence, "installed-plugin sentence missing from the Load the contract section"
    roots = re.findall(r"`(~/[^`]+)`", sentence.group(1))
    return numbered + [f"{root}/{_CONTRACT_REL}" for root in roots]


def _resolve(candidates: list[str], *, home: Path, cwd: Path, env: dict[str, str]) -> Path | None:
    """Walk candidates as the agent does: env vars, `~`, glob, first readable file."""
    for candidate in candidates:
        root_value = env.get("COPILOT_PLUGIN_ROOT") or env.get("CLAUDE_PLUGIN_ROOT") or ".claude"
        expanded = candidate.replace(_ROOT_VARS, root_value)
        if expanded.startswith("~/"):
            expanded = str(home) + expanded[1:]
        if not Path(expanded).is_absolute():
            expanded = str(cwd / expanded)
        for match in sorted(glob.glob(expanded)):
            if Path(match).is_file():
                return Path(match)
    return None


def _install(root: Path) -> Path:
    contract = root / _CONTRACT_REL
    contract.parent.mkdir(parents=True)
    contract.write_text("# contract\n")
    return contract


class TestAgentResolvesInstalledPluginContract:
    """Issue #7356: find the contract in an installed plugin with both root vars unset."""

    CANDIDATES = _candidates(_read(_AGENT_SHARED))

    def test_candidate_list_names_the_installed_plugin_roots(self) -> None:
        joined = "\n".join(self.CANDIDATES)
        assert "~/.copilot/installed-plugins/_direct/project-toolkit/" in joined
        assert "~/.copilot/installed-plugins/*/project-toolkit/" in joined
        assert "~/.claude/plugins/cache/*/project-toolkit/" in joined

    def test_installed_roots_match_the_ship_resolution_rule(self) -> None:
        ship = _read(_SHIP_RESOLUTION)
        ship_roots = re.findall(r'"\$\{HOME:-\}/(\.[^"]*?project-toolkit)"?', ship)
        ship_roots = [r.replace('"/*/', "/*/") for r in ship_roots]
        assert ship_roots, "ship rule lost its installed-plugin roots"
        for root in ship_roots:
            assert any(f"~/{root}/" in c for c in self.CANDIDATES), root

    def test_checkout_paths_stay_and_precede_the_installed_roots(self) -> None:
        index = {c: i for i, c in enumerate(self.CANDIDATES)}
        checkout = index[f".claude/{_CONTRACT_REL}"]
        direct = next(i for c, i in index.items() if "installed-plugins/_direct" in c)
        assert index[f"{_ROOT_VARS}/{_CONTRACT_REL}"] == 0
        assert checkout < index[_CONTRACT_REL] < direct

    @pytest.mark.parametrize(
        "root",
        [
            ".copilot/installed-plugins/_direct/project-toolkit",
            ".copilot/installed-plugins/some-marketplace/project-toolkit",
            ".claude/plugins/cache/some-marketplace/project-toolkit",
        ],
    )
    def test_installed_plugin_resolves_with_both_root_vars_unset(
        self, tmp_path: Path, root: str
    ) -> None:
        home, cwd = tmp_path / "home", tmp_path / "unrelated-checkout"
        cwd.mkdir()
        contract = _install(home / root)
        assert _resolve(self.CANDIDATES, home=home, cwd=cwd, env={}) == contract

    def test_root_variable_wins_over_an_installed_plugin(self, tmp_path: Path) -> None:
        home, cwd = tmp_path / "home", tmp_path / "cwd"
        cwd.mkdir()
        _install(home / ".copilot/installed-plugins/_direct/project-toolkit")
        explicit = _install(tmp_path / "explicit-root")
        env = {"COPILOT_PLUGIN_ROOT": str(tmp_path / "explicit-root")}
        assert _resolve(self.CANDIDATES, home=home, cwd=cwd, env=env) == explicit

    def test_checkout_contract_wins_over_an_installed_plugin(self, tmp_path: Path) -> None:
        home, cwd = tmp_path / "home", tmp_path / "cwd"
        cwd.mkdir()
        _install(home / ".copilot/installed-plugins/_direct/project-toolkit")
        checkout = _install(cwd / ".claude")
        assert _resolve(self.CANDIDATES, home=home, cwd=cwd, env={}) == checkout

    def test_no_readable_location_resolves_nothing(self, tmp_path: Path) -> None:
        home, cwd = tmp_path / "home", tmp_path / "cwd"
        home.mkdir()
        cwd.mkdir()
        assert _resolve(self.CANDIDATES, home=home, cwd=cwd, env={}) is None

    def test_other_plugin_in_the_installed_dir_is_not_matched(self, tmp_path: Path) -> None:
        home, cwd = tmp_path / "home", tmp_path / "cwd"
        cwd.mkdir()
        _install(home / ".copilot/installed-plugins/_direct/other-plugin")
        assert _resolve(self.CANDIDATES, home=home, cwd=cwd, env={}) is None

    def test_refusal_to_pass_without_the_contract_is_kept(self) -> None:
        text = _read(_AGENT_SHARED)
        assert "Without the contract, never emit PASS." in text
        assert "VERDICT: WARN" in text

    @pytest.mark.parametrize("path", _RENDERED_AGENTS, ids=lambda p: p.parent.parent.name)
    def test_rendered_copies_carry_the_same_candidates(self, path: Path) -> None:
        assert _candidates(_read(path)) == self.CANDIDATES
