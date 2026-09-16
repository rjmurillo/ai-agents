"""Tests for the harness x billing matrix and its two readers.

Offline: no network, no CLI, no credential. Everything here is table lookup,
selection precedence, and the two consistency invariants that keep the biller
a run is charged on tied to the transport it runs on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _billing_matrix
    import _eval_common
    import _providers
    from _billing_matrix import MatrixCell
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH


# --- Shape of the matrix ------------------------------------------------


def test_matrix_has_one_cell_per_harness_and_billing_mode() -> None:
    pairs = {(cell.harness, cell.payer) for cell in _billing_matrix.cells()}

    expected = {
        (harness, billing)
        for harness in _billing_matrix.HARNESSES
        for billing in _billing_matrix.BILLING_MODES
    }
    assert pairs == expected
    assert len(_billing_matrix.cells()) == 6


@pytest.mark.parametrize("cell", _billing_matrix.cells(), ids=lambda c: c.name)
def test_every_cell_declares_a_known_cost_basis(cell: MatrixCell) -> None:
    assert cell.cost_basis in (
        _billing_matrix.COST_BASIS_USD,
        _billing_matrix.COST_BASIS_REQUESTS,
    )


@pytest.mark.parametrize("cell", _billing_matrix.cells(), ids=lambda c: c.name)
def test_every_cell_declares_a_known_status_and_a_reason(cell: MatrixCell) -> None:
    assert cell.status in (
        _billing_matrix.STATUS_VERIFIED,
        _billing_matrix.STATUS_UNVERIFIED,
    )
    assert cell.note.strip()


@pytest.mark.parametrize("cell", _billing_matrix.cells(), ids=lambda c: c.name)
def test_a_required_env_var_flag_names_at_least_one_variable(cell: MatrixCell) -> None:
    """`env_var_required` with no variable named would be unsatisfiable."""
    if cell.env_var_required:
        assert cell.env_vars_read


def test_every_subscription_cell_bills_requests() -> None:
    """A seat spends an allowance; quoting it in dollars invents a rate."""
    subscription = [
        cell for cell in _billing_matrix.cells() if cell.payer == "subscription"
    ]

    assert subscription
    assert all(
        cell.cost_basis == _billing_matrix.COST_BASIS_REQUESTS for cell in subscription
    )


# --- Lookup -------------------------------------------------------------


@pytest.mark.parametrize(
    "harness,billing,provider",
    [
        ("claude", "api", "anthropic"),
        ("claude", "subscription", "claude-cli"),
        ("codex", "api", "openai"),
        ("codex", "subscription", "codex-cli"),
        ("copilot", "api", "copilot-api"),
        ("copilot", "subscription", "copilot-cli"),
    ],
)
def test_provider_for_returns_the_canonical_transport(
    harness: str, billing: str, provider: str
) -> None:
    assert _billing_matrix.provider_for(harness, billing) == provider


def test_cell_for_is_case_insensitive_and_strips() -> None:
    assert _billing_matrix.cell_for("  Claude ", "API ").name == "claude-api"


def test_cell_for_rejects_an_unknown_harness() -> None:
    with pytest.raises(_billing_matrix.BillingMatrixError, match="gemini"):
        _billing_matrix.cell_for("gemini", "api")


def test_cell_for_rejects_an_unknown_billing_mode() -> None:
    with pytest.raises(_billing_matrix.BillingMatrixError, match="barter"):
        _billing_matrix.cell_for("claude", "barter")


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("anthropic", "claude-api"),
        ("anthropic-sdk", "claude-api"),
        ("claude-api", "claude-api"),
        ("CLAUDE-CLI", "claude-subscription"),
        ("claude-code", "claude-subscription"),
        ("codex", "codex-api"),
        ("openai", "codex-api"),
        ("codex-cli", "codex-subscription"),
        ("copilot", "copilot-subscription"),
        ("copilot-cli", "copilot-subscription"),
        ("copilot-api", "copilot-api"),
    ],
)
def test_legacy_and_canonical_spellings_resolve_to_one_cell(
    alias: str, expected: str
) -> None:
    cell = _billing_matrix.cell_for_provider(alias)

    assert cell is not None
    assert cell.name == expected


@pytest.mark.parametrize("name", ["github", "github-models", "bogus", "", None])
def test_cell_for_provider_returns_none_for_a_name_no_cell_claims(
    name: str | None,
) -> None:
    assert _billing_matrix.cell_for_provider(name) is None


# --- Selection precedence ----------------------------------------------


def test_selection_defaults_to_claude_api_when_nothing_is_named() -> None:
    assert _billing_matrix.resolve_selection(environ={}).name == "claude-api"


def test_selection_reads_the_environment_when_no_flag_is_passed() -> None:
    cell = _billing_matrix.resolve_selection(
        environ={"EVAL_HARNESS": "copilot", "EVAL_BILLING": "subscription"}
    )

    assert cell.name == "copilot-subscription"


def test_an_explicit_flag_outranks_the_environment() -> None:
    cell = _billing_matrix.resolve_selection(
        provider="codex-cli", environ={"EVAL_PROVIDER": "openai"}
    )

    assert cell.name == "codex-subscription"


def test_agreeing_provider_and_axes_resolve_to_that_cell() -> None:
    cell = _billing_matrix.resolve_selection(
        provider="copilot-cli", harness="copilot", billing="subscription", environ={}
    )

    assert cell.name == "copilot-subscription"


def test_disagreeing_provider_and_axes_are_refused() -> None:
    """Picking one would bill a transport the operator did not ask for."""
    with pytest.raises(_billing_matrix.BillingMatrixError, match="Pass one or the other"):
        _billing_matrix.resolve_selection(
            provider="copilot-cli", harness="claude", billing="api", environ={}
        )


@pytest.mark.parametrize(
    "harness,billing",
    [("codex", ""), ("", "subscription")],
)
def test_half_an_axis_pair_is_refused(harness: str, billing: str) -> None:
    with pytest.raises(
        _billing_matrix.BillingMatrixError, match="must be given together"
    ):
        _billing_matrix.resolve_selection(
            harness=harness, billing=billing, environ={}
        )


def test_an_unknown_provider_names_the_valid_spellings() -> None:
    with pytest.raises(_billing_matrix.BillingMatrixError) as excinfo:
        _billing_matrix.resolve_selection(provider="gemini-cli", environ={})

    assert "claude-subscription" in str(excinfo.value)


# --- apply_selection ----------------------------------------------------


def test_apply_selection_publishes_the_canonical_provider_for_an_axis_pair() -> None:
    env: dict[str, str] = {}

    cell = _billing_matrix.apply_selection(
        harness="codex", billing="subscription", environ=env
    )

    assert cell is not None and cell.name == "codex-subscription"
    assert env["EVAL_PROVIDER"] == "codex-cli"


def test_apply_selection_writes_an_explicit_provider_verbatim() -> None:
    """Rewriting it would move anthropic-sdk onto a different transport."""
    env: dict[str, str] = {}

    _billing_matrix.apply_selection(provider="anthropic-sdk", environ=env)

    assert env["EVAL_PROVIDER"] == "anthropic-sdk"


def test_apply_selection_leaves_the_environment_alone_when_nothing_is_named() -> None:
    env = {"EVAL_PROVIDER": "copilot-cli"}

    assert _billing_matrix.apply_selection(environ=env) is None
    assert env["EVAL_PROVIDER"] == "copilot-cli"


def test_apply_selection_passes_a_retired_provider_name_through() -> None:
    """`github-models` is dispatchable history, not a cell. Do not block it."""
    env: dict[str, str] = {}

    assert _billing_matrix.apply_selection(provider="github-models", environ=env) is None
    assert env["EVAL_PROVIDER"] == "github-models"


def test_apply_selection_refuses_an_unmapped_provider_paired_with_axes() -> None:
    env: dict[str, str] = {}

    with pytest.raises(_billing_matrix.BillingMatrixError):
        _billing_matrix.apply_selection(
            provider="github-models", harness="codex", billing="api", environ=env
        )

    assert "EVAL_PROVIDER" not in env


def test_apply_selection_propagates_a_conflict_instead_of_writing() -> None:
    env: dict[str, str] = {}

    with pytest.raises(_billing_matrix.BillingMatrixError):
        _billing_matrix.apply_selection(
            provider="openai", harness="claude", billing="subscription", environ=env
        )

    assert "EVAL_PROVIDER" not in env


# --- Consistency with the two readers -----------------------------------


def test_every_registry_row_is_classified_by_a_matrix_cell() -> None:
    """A new transport must declare its biller, not inherit the usd default."""
    assert _providers.registry_classification_gaps() == frozenset()


@pytest.mark.parametrize(
    "alias", sorted(_billing_matrix.known_selector_names())
)
def test_cost_basis_agrees_with_the_cell_for_every_selector(
    alias: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    cell = _billing_matrix.cell_for_provider(alias)

    assert cell is not None
    assert _eval_common.cost_basis(alias) == cell.cost_basis


def test_retired_github_rows_keep_their_request_basis() -> None:
    """They are outside the matrix but still resolve for archived runs."""
    assert "github" in _eval_common.QUOTA_BILLED_PROVIDERS
    assert "github-models" in _eval_common.QUOTA_BILLED_PROVIDERS


def test_quota_billed_names_exclude_every_per_token_cell() -> None:
    quota = _billing_matrix.quota_billed_provider_names()

    assert "anthropic-sdk" not in quota
    assert "openai" not in quota
    assert "claude-api" not in quota


# --- Rendering ----------------------------------------------------------


def test_format_matrix_renders_one_row_per_cell() -> None:
    rendered = _billing_matrix.format_matrix()

    body = [line for line in rendered.splitlines() if line.startswith("| ")]
    # Header row plus six data rows; the separator line starts with "|---".
    assert len(body) == 7
    for cell in _billing_matrix.cells():
        assert f"`{cell.provider}`" in rendered


def test_provider_help_text_names_every_cell() -> None:
    help_text = _billing_matrix.provider_help_text()

    for cell in _billing_matrix.cells():
        assert cell.name in help_text
