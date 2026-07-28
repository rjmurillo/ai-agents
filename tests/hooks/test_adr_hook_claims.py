"""ADR hook claims must name real or explicitly retired hook files."""

from __future__ import annotations

import importlib.util
import re
from bisect import bisect_right
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = PROJECT_ROOT / ".agents" / "architecture"
HOOKS_ROOT = PROJECT_ROOT / ".claude" / "hooks"
HOOK_SEARCH_ROOTS = (
    HOOKS_ROOT,
    PROJECT_ROOT / "src" / "copilot-cli" / "hooks",
)
REFERENCE_FORM_CASES = (
    ("backticked bare name", "`invoke_context_loader`"),
    ("backticked bare py", "`invoke_context_loader.py`"),
    ("backticked claude path", "`.claude/hooks/SessionStart/invoke_context_loader.py`"),
    (
        "backticked copilot path",
        "`src/copilot-cli/hooks/SessionStart/invoke_context_loader.py`",
    ),
    ("backticked table cell", "| Hook | `invoke_context_loader.py` |"),
    (
        "line and range suffixes",
        "`invoke_context_loader.py:12` and `invoke_context_loader.py:12-18`",
    ),
    ("plain bare name", "invoke_context_loader"),
    ("plain bare py", "invoke_context_loader.py"),
    ("plain claude path", ".claude/hooks/SessionStart/invoke_context_loader.py"),
    ("plain copilot path", "src/copilot-cli/hooks/SessionStart/invoke_context_loader.py"),
    ("backtick fenced yaml", "```yaml\nhook: invoke_context_loader.py\n```"),
    ("tilde fenced yaml", "~~~yaml\nhook: invoke_context_loader.py\n~~~"),
    ("plain table cell", "| Hook | invoke_context_loader.py |"),
    ("markdown link target", "[hook](.claude/hooks/SessionStart/invoke_context_loader.py)"),
    ("html comment", "<!-- invoke_context_loader.py -->"),
    ("embedded yaml", "hooks:\n  - invoke_context_loader.py"),
    ("embedded json", '{"hook": "invoke_context_loader.py"}'),
    ("different case", "Invoke_Context_Loader.py"),
    ("hyphen form", "invoke-context-loader.py"),
    ("frontmatter", "---\nhook: invoke_context_loader.py\n---"),
    (
        "retired and live in one sentence",
        "The retired `invoke_old_gate.py` is gone; `invoke_context_loader.py` remains active.",
    ),
    ("registration runs", "`invoke_context_loader.py` runs at session start."),
    ("registration ships", "`invoke_context_loader.py` ships in the base."),
    ("registration enforcing", "`invoke_context_loader.py` is enforcing the policy."),
    ("registration guards", "`invoke_context_loader.py` guards the flow."),
    ("registration active", "`invoke_context_loader.py` is active."),
    ("registration remains", "`invoke_context_loader.py` remains registered."),
)

_HOOK_TOKEN_RE = re.compile(
    r"(?<![\w-])"
    r"((?:(?:(?:\.claude|src/copilot-cli)/hooks/(?:[A-Za-z]\w*/)?|[A-Za-z]\w*/))?"
    r"(?:Invoke_[\w.]*[-_][\w.-]+|Invoke-[\w.]*[-_][\w.-]+)"
    r"(?:\.py)?(?::\d+(?:-\d+)?)?)"
    r"(?![\w-])",
    re.IGNORECASE,
)
_IMPLEMENTED_RE = re.compile(r"^\s*(?:\u2705\s*)?implemented\b", re.IGNORECASE)
_RETIREMENT_WORDS = (
    r"deleted|deregistered|dropped|historical|no longer|previously|"
    r"removed|replaced|retired|superseded"
)
_RETIRED_RE = re.compile(
    rf"\b(?:{_RETIREMENT_WORDS})\b",
    re.IGNORECASE,
)
_NEGATED_RETIRED_RE = re.compile(
    rf"\b(?:never|not)\s+(?:{_RETIREMENT_WORDS})\b",
    re.IGNORECASE,
)
_LIVE_REGISTRATION_RE = re.compile(
    r"\b(?:"
    r"active|blocks?|consumer-effective|enforc(?:e[sd]?|ing)|fires?|guards?|"
    r"invokes?|registered|registers?|registration|remains|run(?:s|ning)?|ships"
    r")\b"
    r"|\bstill\s+(?:active|exists|registered|runs|enforces|ships)\b",
    re.IGNORECASE,
)


def _load_dispatch_groups_parity() -> ModuleType:
    path = Path(__file__).with_name("test_dispatch_groups_parity.py")
    spec = importlib.util.spec_from_file_location("test_dispatch_groups_parity", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DISPATCH_GROUPS_PARITY = _load_dispatch_groups_parity()


def _adr_files() -> list[Path]:
    return sorted(ADR_DIR.glob("ADR-*.md"))


def _claims(text: str) -> list[tuple[int, str]]:
    """(line number, hook path) for every row claiming a hook is implemented.

    A row is a claim when it names a hook path, some cell marks it implemented,
    and no cell retires it. Keying on the marker rather than the path is what
    lets an ADR keep a historical row for a hook that has since been removed.
    """
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if _RETIRED_RE.search(line):
            continue
        if not any(_IMPLEMENTED_RE.match(c) for c in cells):
            continue
        for cell in cells:
            for match in _HOOK_TOKEN_RE.finditer(cell):
                found.append((number, match.group(1)))
    return found


def _prose_claims(text: str) -> list[tuple[int, str]]:
    """(line number, hook token) for references without same-context retirement."""
    return [
        (number, path)
        for number, path, context in _hook_references(text)
        if not _has_retirement_marker(context)
        and path not in _documented_governance_gap_tokens(text)
    ]


def _hook_references(text: str) -> list[tuple[int, str, str]]:
    line_starts = [0]
    for match in re.finditer(r"\n", text):
        line_starts.append(match.end())
    found: list[tuple[int, str, str]] = []
    for match in _HOOK_TOKEN_RE.finditer(text):
        line_number = bisect_right(line_starts, match.start())
        line_start = line_starts[line_number - 1]
        line_end = text.find("\n", match.start())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        token = _normal_hook_token(match.group(1))
        context = line if line.lstrip().startswith("|") else _prose_context(text, match)
        found.append((line_number, token, context))
    return found


def _prose_context(text: str, match: re.Match[str]) -> str:
    paragraph_start = text.rfind("\n\n", 0, match.start())
    paragraph_start = 0 if paragraph_start == -1 else paragraph_start + 2
    paragraph_end = text.find("\n\n", match.end())
    paragraph_end = len(text) if paragraph_end == -1 else paragraph_end
    paragraph = text[paragraph_start:paragraph_end]
    return _sentence_context(
        paragraph,
        match.start() - paragraph_start,
        match.end() - paragraph_start,
    )


def _sentence_context(text: str, start_offset: int, end_offset: int) -> str:
    starts = [marker.start() for marker in re.finditer(r"[.?!](?=\s|$)", text[:start_offset])]
    start = starts[-1] if starts else -1
    end_candidates = [
        marker.start()
        for marker in re.finditer(r"[.?!](?=\s|$)", text[end_offset:])
    ]
    end_candidates = [end_offset + position for position in end_candidates]
    end = min(end_candidates) + 1 if end_candidates else len(text)
    sentence = text[start + 1 : end]
    return _clause_context(sentence, start_offset - start - 1, end_offset - start - 1)


def _clause_context(text: str, start_offset: int, end_offset: int) -> str:
    boundary_re = r"\||;|\band\b|\bbut\b|\bor\b|\bwhile\b|\bwhereas\b"
    boundaries = [match for match in re.finditer(boundary_re, text, re.IGNORECASE)]
    start = -1
    for marker in boundaries:
        if marker.start() < start_offset:
            start = marker.end() - 1
        else:
            break
    end = len(text)
    for marker in boundaries:
        if marker.start() >= end_offset:
            end = marker.start()
            break
    return text[start + 1 : end]


def _has_retirement_marker(context: str) -> bool:
    affirmative_context = _NEGATED_RETIRED_RE.sub("", context)
    return _RETIRED_RE.search(affirmative_context) is not None


def _documented_governance_gap_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for context in text.split("\n\n"):
        if (
            "governance gap" in context.lower()
            and re.search(r"\b(?:absent|absence|missing)\b", context, re.IGNORECASE)
        ):
            tokens.update(
                _normal_hook_token(match.group(1))
                for match in _HOOK_TOKEN_RE.finditer(context)
            )
    return tokens


def _names_running_hook(hook_path: str) -> bool:
    basename = Path(_candidate_hook_paths(hook_path)[0]).name
    return basename in DISPATCH_GROUPS_PARITY._every_running_basename()


def _claims_live_registration(context: str) -> bool:
    return _LIVE_REGISTRATION_RE.search(context) is not None


def _resolves(hook_path: str) -> bool:
    # removeprefix, not lstrip: lstrip takes a character set, so lstrip("./")
    # eats the leading dot of ".claude/hooks/..." and the path stops resolving.
    candidates = _candidate_hook_paths(hook_path)
    for candidate in candidates:
        if _repo_relative_hook_path_exists(candidate):
            return True
        if "/" in candidate and any((root / candidate).is_file() for root in HOOK_SEARCH_ROOTS):
            return True
        if "/" not in candidate and (
            any(root.joinpath(candidate).is_file() for root in HOOK_SEARCH_ROOTS)
            or any(
                path.is_file()
                for root in HOOK_SEARCH_ROOTS
                for path in root.glob(f"*/{candidate}")
            )
        ):
            return True
    return False


def _repo_relative_hook_path_exists(candidate: str) -> bool:
    path = Path(candidate)
    allowed_roots = (Path(".claude") / "hooks", Path("src") / "copilot-cli" / "hooks")
    return any(path.is_relative_to(root) for root in allowed_roots) and (
        PROJECT_ROOT / path
    ).is_file()


def _candidate_hook_paths(hook_path: str) -> list[str]:
    candidate = _normal_hook_token(hook_path.removeprefix("./"))
    if candidate.endswith(".py"):
        return [candidate]
    return [f"{candidate}.py", candidate]


def _normal_hook_token(hook_path: str) -> str:
    return re.sub(r":\d+(?:-\d+)?$", "", hook_path)


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.stem)
def test_no_adr_claims_a_hook_that_is_absent(adr: Path) -> None:
    missing = [
        f"{adr.name}:{line} claims `{path}`"
        for line, path in _claims(adr.read_text(encoding="utf-8"))
        if not _resolves(path)
    ]
    assert not missing, (
        "ADR marks a hook implemented whose file is not in the tree: "
        f"{missing}. Either restore the hook or amend the ADR: change the row's "
        "status to name the issue that retired it. Do not delete the row; an "
        "ADR records what was decided."
    )


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.stem)
def test_no_adr_prose_names_a_hook_that_is_absent_without_retirement_marker(adr: Path) -> None:
    missing = [
        f"{adr.name}:{line} names `{path}`"
        for line, path in _prose_claims(adr.read_text(encoding="utf-8"))
        if not _resolves(path)
    ]
    assert not missing, (
        "ADR prose names a hook file that is not in the tree without a same-sentence "
        f"or same-row retirement marker: {missing}. Either name the current "
        "enforcement point or mark the reference as historical in that sentence or row."
    )


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.stem)
def test_no_adr_prose_claims_an_unregistered_hook_is_live(adr: Path) -> None:
    missing = []
    text = adr.read_text(encoding="utf-8")
    governance_gap_tokens = _documented_governance_gap_tokens(text)
    for number, path, context in _hook_references(text):
        if (
            not _has_retirement_marker(context)
            and path not in governance_gap_tokens
            and _claims_live_registration(context)
            and not _names_running_hook(path)
        ):
            missing.append(f"{adr.name}:{number} claims `{path}` is live")
    assert not missing, (
        "ADR prose claims a hook is live but the hook is not in dispatch_groups "
        f"or direct settings: {missing}. Either name the current enforcement point "
        "or mark the hook reference as historical in the same sentence or row."
    )


class TestTheScanIsNotVacuous:
    """A parametrized check that matches nothing passes for the wrong reason."""

    def test_some_adr_claims_at_least_one_hook(self):
        total = sum(len(_claims(a.read_text(encoding="utf-8"))) for a in _adr_files())
        assert total >= 1, "no ADR row was read as a hook implementation claim"

    def test_adr_008_is_among_them(self):
        """The ADR the issue was filed against must be inside the scan."""
        adr = ADR_DIR / "ADR-008-protocol-automation-lifecycle-hooks.md"
        assert _claims(adr.read_text(encoding="utf-8"))

    def test_some_adr_prose_names_at_least_one_hook(self):
        total = sum(len(_prose_claims(a.read_text(encoding="utf-8"))) for a in _adr_files())
        assert total >= 1, "no ADR prose was read as a hook file reference"


class TestWhatCountsAsAClaim:
    def test_an_implemented_row_naming_a_hook_is_a_claim(self):
        row = "| Ctx | `SessionStart/invoke_context_loader.py` | SessionStart | Implemented |\n"
        assert _claims(row) == [(1, "SessionStart/invoke_context_loader.py")]

    def test_a_check_mark_prefix_is_still_implemented(self):
        row = "| Ctx | `SessionStart/invoke_context_loader.py` | S | \u2705 Implemented |\n"
        assert _claims(row) == [(1, "SessionStart/invoke_context_loader.py")]

    def test_a_retired_row_is_not_a_claim(self):
        """The intended amendment shape: keep the row, change the status."""
        row = "| Retro | `Stop/invoke_auto_retrospective.py` | Stop | Retired by #3349 |\n"
        assert _claims(row) == []

    def test_a_row_marked_both_reads_as_retired(self):
        """Retirement wins, so an amendment is never fighting a stale marker."""
        row = "| X | `Stop/invoke_auto_retrospective.py` | Implemented | Retired by #3349 |\n"
        assert _claims(row) == []

    def test_prose_outside_a_table_is_not_a_claim(self):
        """ADRs name hooks in narrative constantly; only rows carry status."""
        assert _claims("The `Stop/invoke_auto_retrospective.py` hook is Implemented.\n") == []

    def test_a_row_with_no_status_is_not_a_claim(self):
        assert _claims("| Ctx | `SessionStart/invoke_context_loader.py` | Loads context |\n") == []

    def test_a_repo_relative_path_is_read(self):
        row = "| C | `.claude/hooks/SessionStart/invoke_context_loader.py` | S | Implemented |\n"
        assert _claims(row) == [(1, ".claude/hooks/SessionStart/invoke_context_loader.py")]

    def test_an_implemented_row_naming_a_bare_hook_is_a_claim(self):
        row = "| Security | `invoke_deleted_gate` | PreToolUse | Implemented |\n"
        assert _claims(row) == [(1, "invoke_deleted_gate")]


class TestPathResolution:
    def test_a_hooks_root_relative_path_resolves(self):
        assert _resolves("SessionStart/invoke_context_loader.py")

    def test_a_repo_relative_path_resolves(self):
        assert _resolves(".claude/hooks/SessionStart/invoke_context_loader.py")

    def test_a_deleted_hook_does_not_resolve(self):
        """The three #3373 named, as the negative control on the whole file."""
        assert not _resolves("Stop/invoke_auto_retrospective.py")
        assert not _resolves("PreToolUse/invoke_false_completion_gate.py")
        assert not _resolves("PostToolUse/invoke_plan_state_sync.py")

    def test_a_bare_live_hook_filename_resolves(self):
        assert _resolves("invoke_context_loader.py")

    def test_a_decoy_outside_hook_roots_does_not_resolve(self):
        assert (PROJECT_ROOT / "scripts" / "invoke_session_start_gate.py").is_file()
        assert not _resolves("scripts/invoke_session_start_gate.py")


class TestWhatCountsAsAProseClaim:
    @pytest.mark.parametrize(
        ("case_name", "text"),
        REFERENCE_FORM_CASES,
        ids=[case_name for case_name, _ in REFERENCE_FORM_CASES],
    )
    def test_reference_form_is_scanned(self, case_name: str, text: str):
        references = [path for _, path, _ in _hook_references(text)]
        assert references, f"{case_name} was not scanned"

    def test_a_resolvable_prose_token_is_a_claim(self):
        text = "The `invoke_context_loader.py` hook runs at session start.\n"
        assert _prose_claims(text) == [(1, "invoke_context_loader.py")]

    def test_an_unresolved_unmarked_prose_token_is_a_claim(self):
        text = "The `invoke_deleted_gate.py` hook still enforces this policy.\n"
        assert _prose_claims(text) == [(1, "invoke_deleted_gate.py")]

    def test_an_unresolved_bare_prose_token_is_a_claim(self):
        text = "The `invoke_deleted_gate` hook still enforces this policy.\n"
        assert _prose_claims(text) == [(1, "invoke_deleted_gate")]

    def test_an_unresolved_token_with_same_sentence_retirement_marker_is_suppressed(self):
        text = (
            "The retired hook `invoke_deleted_gate.py` used to enforce this policy.\n"
        )
        assert _prose_claims(text) == []

    def test_an_unresolved_token_with_only_nearby_retirement_marker_is_a_claim(self):
        text = (
            "The hook was retired by #3184.\n"
            "This paragraph still names `invoke_deleted_gate.py`.\n"
        )
        assert _prose_claims(text) == [(2, "invoke_deleted_gate.py")]

    def test_a_removed_heading_does_not_suppress_a_later_stale_claim(self):
        text = (
            "## Removed\n\n"
            "The `invoke_deleted_gate.py` hook still enforces this policy.\n"
        )
        assert _prose_claims(text) == [(3, "invoke_deleted_gate.py")]

    def test_a_negated_retirement_marker_does_not_suppress_a_stale_claim(self):
        text = "This hook was never removed: `invoke_deleted_gate.py` still enforces this policy.\n"
        assert _prose_claims(text) == [(1, "invoke_deleted_gate.py")]

    def test_a_retired_token_does_not_suppress_a_live_token_in_the_same_sentence(self):
        text = (
            "The retired `invoke_old_gate.py` is gone; "
            "`invoke_deleted_gate.py` remains active.\n"
        )
        assert _prose_claims(text) == [(1, "invoke_deleted_gate.py")]

    def test_documented_governance_gap_does_not_read_as_unmarked_stale_prose(self):
        text = (
            "`invoke_deleted_gate.py` MUST remain in the base.\n\n"
            "Observed state: `invoke_deleted_gate.py` is absent. "
            "The absence is a governance gap, not a relaxed decision.\n"
        )
        assert _prose_claims(text) == []

    def test_a_table_row_reference_without_retirement_marker_is_a_claim(self):
        row = "| Gate | `invoke_deleted_gate.py:66-95` | Direct | Medium |\n"
        assert _prose_claims(row) == [(1, "invoke_deleted_gate.py")]

    def test_a_table_row_bare_reference_without_retirement_marker_is_a_claim(self):
        row = "| Gate | `invoke_deleted_gate` | Direct | Medium |\n"
        assert _prose_claims(row) == [(1, "invoke_deleted_gate")]

    def test_a_table_row_reference_with_retirement_marker_is_suppressed(self):
        row = "| Gate | `invoke_deleted_gate.py:66-95` | Historical, removed | Medium |\n"
        assert _prose_claims(row) == []

    def test_line_range_suffix_is_ignored_for_resolution(self):
        assert _resolves("invoke_context_loader.py:1-2")

    def test_live_registration_claim_uses_dispatch_inventory(self):
        context = "The `invoke_context_loader.py` hook still runs."
        assert _claims_live_registration(context)
        assert _names_running_hook("invoke_context_loader.py")

    def test_live_registration_claim_maps_bare_name_to_dispatch_inventory(self):
        context = "The `invoke_context_loader` hook still runs."
        assert _claims_live_registration(context)
        assert _names_running_hook("invoke_context_loader")

    @pytest.mark.parametrize(
        "phrase",
        (
            "runs",
            "ships",
            "is enforcing",
            "guards",
            "is active",
            "remains",
            "registers",
            "fires",
            "invokes",
            "blocks",
        ),
    )
    def test_live_registration_claim_verbs_are_recognized(self, phrase: str):
        assert _claims_live_registration(f"`invoke_context_loader.py` {phrase}.")

    def test_a_line_range_suffix_is_stripped_and_the_reference_is_still_captured(self):
        text = "See `invoke_serena_reassertion.py:38-41` for the guard.\n"
        assert _prose_claims(text) == [(1, "invoke_serena_reassertion.py")]
