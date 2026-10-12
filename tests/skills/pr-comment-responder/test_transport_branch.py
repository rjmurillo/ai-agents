"""The responder workflow must carry an MCP branch for every gh-backed step.

Issue #5518: `/pr-review` decides the transport once, but the responder skill
called the `gh`-backed scripts unconditionally, so a `gh_unusable` session hit
the HTTP 403 the preflight exists to avoid, one step after it passed.

The checks here are structural. They compare the workflow's transport table
with the scripts the skill's own documents invoke and with the operation names
`transport-routing.md` defines, so a script added to the workflow without a
branch, or an invented MCP operation name, fails here rather than in a live
`gh_unusable` session.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "pr-comment-responder"
WORKFLOW = SKILL_DIR / "references" / "workflow.md"
GATES = SKILL_DIR / "references" / "gates.md"
CONVERSATION = SKILL_DIR / "references" / "review-conversation.md"
SKILL = SKILL_DIR / "SKILL.md"
GITHUB_SCRIPTS = REPO_ROOT / ".claude" / "skills" / "github" / "scripts"
ROUTING = REPO_ROOT / ".claude" / "skills" / "github" / "references" / "transport-routing.md"
CLUSTER_SCRIPT = SKILL_DIR / "scripts" / "cluster_threads.py"
CONFIG = REPO_ROOT / ".claude" / "skills" / "pr-review" / "pr-review-config.yaml"

REVIEW_SURFACES = [
    REPO_ROOT / ".claude" / "skills" / "pr-review" / "SKILL.md",
    REPO_ROOT / "src" / "claude" / "skills" / "pr-review" / "SKILL.md",
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-review" / "SKILL.md",
    REPO_ROOT / ".github" / "prompts" / "pr-review.prompt.md",
]
RESPONDER_SURFACES = [
    SKILL,
    REPO_ROOT / "src" / "claude" / "skills" / "pr-comment-responder" / "SKILL.md",
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-comment-responder" / "SKILL.md",
]

# Parameters and field names the table's third column may name besides MCP
# operations. Anything else in backticks there must be defined by the routing
# reference, which is what stops an invented operation name.
_NON_OPERATION_TOKENS = frozenset(
    {
        "reaction",
        "comment_id",
        "isResolved",
        "thread_id",
        "path",
        "first_comment_body",
        "--threads-file",
        "git remote get-url origin",
        "gh repo view",
        "gh api graphql",
        "[COMPLETE]",
        "0 unresolved",
    }
)

_SCRIPT_NAME = re.compile(r"\b([a-z][a-z0-9_]*\.py)\b")
_BACKTICKED = re.compile(r"`([^`\n]+)`")


def _transport_section(text: str) -> str:
    start = text.index("## Transport (BLOCKING, decided once)")
    end = text.index("## Phase -1:", start)
    return text[start:end]


def _table_rows(section: str) -> list[list[str]]:
    """Return the cells of the step table, the one whose header names `gh` script."""
    rows: list[list[str]] = []
    in_table = False
    for line in section.splitlines():
        if line.startswith("| Step |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif in_table:
            break
    return rows


def _unknown_operations(rows: list[list[str]], routing_text: str) -> list[str]:
    """Backticked last-column tokens defined by neither the routing doc nor the allowlist."""
    unknown: list[str] = []
    for row in rows:
        for token in _BACKTICKED.findall(row[-1]):
            if token in _NON_OPERATION_TOKENS or token.endswith(".py"):
                continue
            if f"`{token}`" not in routing_text:
                unknown.append(token)
    return unknown


def _invoked_github_scripts() -> set[str]:
    """Scripts the skill's own documents invoke that ship in the github skill."""
    shipped = {p.name for p in GITHUB_SCRIPTS.rglob("*.py")}
    names: set[str] = set()
    for doc in (WORKFLOW, GATES, CONVERSATION, SKILL):
        text = doc.read_text(encoding="utf-8")
        if doc == WORKFLOW:
            text = text.replace(_transport_section(text), "")
        names |= {n for n in _SCRIPT_NAME.findall(text) if n in shipped}
    return names


@pytest.fixture(scope="module")
def section() -> str:
    return _transport_section(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(section: str) -> list[list[str]]:
    return _table_rows(section)


class TestEveryGhStepHasAnMcpBranch:
    def test_the_table_is_not_empty(self, rows):
        assert len(rows) >= 10

    def test_every_invoked_gh_script_has_a_row(self, rows):
        """A script added to the workflow without a branch fails here."""
        named = {n for row in rows for n in _SCRIPT_NAME.findall(row[1])}
        missing = sorted(_invoked_github_scripts() - named)
        assert not missing, f"gh-backed scripts with no gh_unusable branch: {missing}"

    def test_cluster_threads_has_a_row(self, rows):
        """It lives in the skill's own scripts, so the github-skill scan misses it."""
        named = {n for row in rows for n in _SCRIPT_NAME.findall(row[1])}
        assert "cluster_threads.py" in named

    def test_every_row_has_a_nonempty_branch(self, rows):
        for row in rows:
            assert len(row) == 3, f"row is not three cells: {row}"
            assert row[2], f"empty gh_unusable branch for {row[1]}"


class TestOperationNamesAreNotInvented:
    def test_every_named_operation_is_defined_by_the_routing_reference(self, rows):
        routing = ROUTING.read_text(encoding="utf-8")
        assert _unknown_operations(rows, routing) == []

    def test_an_invented_operation_is_caught(self):
        """Negative control: the check above must fail on a made-up name."""
        routing = ROUTING.read_text(encoding="utf-8")
        fake = [["1.3", "`get_pr_review_comments.py`", "`fetch_everything_about_pr`"]]
        assert _unknown_operations(fake, routing) == ["fetch_everything_about_pr"]

    def test_a_real_operation_passes(self):
        routing = ROUTING.read_text(encoding="utf-8")
        real = [["6", "`resolve_pr_review_thread.py`", "`resolve_review_thread`"]]
        assert _unknown_operations(real, routing) == []

    def test_cluster_fallback_names_the_keys_the_script_reads(self):
        """The `--threads-file` shape in the table must be the shape the script reads."""
        source = CLUSTER_SCRIPT.read_text(encoding="utf-8")
        for key in ("thread_id", "path", "first_comment_body", "--threads-file"):
            assert key in source, f"cluster_threads.py never mentions {key}"


class TestTransportContract:
    def test_the_workflow_accepts_exactly_the_preflight_verdicts(self, section):
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        verdicts = {v["transport"] for v in config["transport_preflight"]["verdicts"]}
        stated = set(re.findall(r"`Transport: (\w+)`", section))
        assert stated == verdicts

    def test_the_workflow_forbids_the_gh_fallback_and_the_transport_verdict(self, section):
        assert "Never run a `gh`-backed script to double-check" in section
        assert "A transport failure is an unknown, never a verdict." in section

    def test_the_workflow_runs_the_preflight_when_the_line_is_absent(self, section):
        assert "check_github_transport.py" in section
        assert "absent" in section

    def test_the_transport_section_precedes_the_first_github_call(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert text.index("## Transport (BLOCKING") < text.index("## Phase -1:")

    @pytest.mark.parametrize(
        "path", RESPONDER_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
    )
    def test_the_skill_names_the_transport_line_and_points_at_the_workflow(self, path):
        body = path.read_text(encoding="utf-8")
        assert "## Transport" in body
        assert "`Transport: gh_unusable`" in body
        assert "references/workflow.md" in body


class TestPrReviewDelegatesWithTheVerdict:
    @pytest.mark.parametrize("path", REVIEW_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_step_4_passes_the_verdict_to_the_responder(self, path):
        body = path.read_text(encoding="utf-8")
        step4 = body[body.index("### Step 4: Launch Agents") : body.index("### Step 5")]
        assert "`Transport: gh_unusable`" in step4
        assert step4.count("`Transport:") >= 2, "parallel mode must carry the line as well"

    @pytest.mark.parametrize("path", REVIEW_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_the_gh_unusable_refusal_is_gone(self, path):
        body = path.read_text(encoding="utf-8")
        for stale in (
            "Neither mode is available",
            "Refuse `--parallel`",
            "has no MCP branch",
            "Do not delegate.",
            "this mode is unavailable",
        ):
            assert stale not in body, f"{path.name} still says: {stale}"
