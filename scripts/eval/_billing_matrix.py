"""The harness x billing matrix the eval transport layer can dispatch to.

Two axes, six cells. The harness axis is `claude`, `codex`, `copilot`: the
three CLIs this repository's agents actually run in. The billing axis is
`api` (a metered vendor account charged per token or per request) and
`subscription` (a seat the operator already pays for, reached by shelling out
to the CLI that holds its login).

Why the axis is explicit rather than implied by a provider name: the two cells
of one harness are not interchangeable. They differ in credential, in what a
run costs, in which sampling controls exist, and in whose system prompt sits
in front of the fixture. Before this module the harness and the biller were
fused into a single `--provider` string, so `copilot` meant a subscription
seat, `codex` meant a metered OpenAI key, and `claude` meant nothing at all.
An operator who wanted "the same fixture, the other biller" had to know which
of seven alias spellings carried that meaning.

This module is pure data plus lookup. It imports nothing from the rest of the
harness, which is what lets `_eval_common` derive its cost basis from the same
table `_providers` dispatches through: one table, two readers, no way for the
biller a run is charged on to disagree with the transport it ran on.

Selection precedence, implemented by `resolve_selection`:

1. an explicit `--provider` / `EVAL_PROVIDER` name, including every legacy
   alias, which already names one cell;
2. `--harness` plus `--billing` (or `EVAL_HARNESS` / `EVAL_BILLING`);
3. the default cell, claude on api, which is the urllib Anthropic transport
   every checked-in baseline was measured on.

Evidence discipline matches `examples/harness-capability-matrix.json`:
`status` is `VERIFIED` only where a live run through that exact cell is
recorded in this repository. A cell whose transport is implemented but never
exercised against its backend from here stays `UNVERIFIED`, because code that
routes correctly is not evidence that the credential, the model id, and the
billing surface line up.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from dataclasses import dataclass

#: The CLI families this harness can drive. Order is the display order.
HARNESSES: tuple[str, ...] = ("claude", "codex", "copilot")

#: Who pays. `api` is a metered vendor account; `subscription` is a seat the
#: operator already holds, reached through that vendor's CLI.
BILLING_MODES: tuple[str, ...] = ("api", "subscription")

#: `cost_basis` values. `usd` means a published per-token rate exists and the
#: report may quote dollars. `requests` means the run spends an allowance
#: nobody publishes a token price for, so the USD column stays empty rather
#: than carrying an invented figure (issue #3786).
COST_BASIS_USD = "usd"
COST_BASIS_REQUESTS = "requests"

STATUS_VERIFIED = "VERIFIED"
STATUS_UNVERIFIED = "UNVERIFIED"


class BillingMatrixError(RuntimeError):
    """An unusable harness, billing mode, or combination of the two."""


@dataclass(frozen=True)
class MatrixCell:
    """One (harness, billing) pair and everything that follows from it."""

    harness: str
    billing: str
    #: Canonical provider name. Accepted by `--provider`, `EVAL_PROVIDER`,
    #: `_providers.resolve_provider`, and `_anthropic_api.call_api`.
    provider: str
    #: Every spelling that selects this cell, canonical name first.
    aliases: tuple[str, ...]
    #: Short transport description for `--help` and the README table.
    transport: str
    #: Names of the environment variables the transport reads to authenticate,
    #: in the order it reads them. Empty when the transport reuses a CLI login
    #: it does not read directly.
    #:
    #: Named for what it holds, variable names, rather than `credentials`,
    #: which is what it was called until CodeQL flagged the preflight's JSON
    #: output as clear-text logging of sensitive data. The alert traced a real
    #: flow, this field into `print`, on a name-based heuristic; the values are
    #: variable names an operator has to be told to set and never a secret. The
    #: honest fix is the accurate name, not a suppression, and this note is
    #: here so nobody renames it back.
    env_vars_read: tuple[str, ...]
    #: True when the run cannot start without one of `env_vars_read`. False
    #: when a CLI login on disk can supply it instead, which no environment
    #: check can see, so a preflight must answer "unknown" rather than "not
    #: ready" for that cell.
    env_var_required: bool
    cost_basis: str
    status: str
    note: str

    @property
    def name(self) -> str:
        """`<harness>-<billing>`, the spelling the matrix documents."""
        return f"{self.harness}-{self.billing}"


_CELLS: tuple[MatrixCell, ...] = (
    MatrixCell(
        harness="claude",
        billing="api",
        provider="anthropic",
        aliases=(
            "anthropic",
            "claude-api",
            "anthropic-http",
            "anthropic-urllib",
            "anthropic-sdk",
        ),
        transport="Anthropic Messages API over urllib (dependency-free default)",
        env_vars_read=("ANTHROPIC_API_KEY",),
        env_var_required=True,
        cost_basis=COST_BASIS_USD,
        status=STATUS_VERIFIED,
        note=(
            "The default transport. Every checked-in baseline in this "
            "repository was measured through it, which is the live evidence "
            "behind VERIFIED. `anthropic-sdk` is the same cell through the "
            "official SDK instead of urllib; it is a separate registry row "
            "because the transports differ, not because the biller does."
        ),
    ),
    MatrixCell(
        harness="claude",
        billing="subscription",
        provider="claude-cli",
        aliases=("claude-cli", "claude-subscription", "claude-code"),
        transport="Claude Code CLI subprocess (`claude --print`)",
        env_vars_read=("CLAUDE_CODE_OAUTH_TOKEN",),
        # Required, not optional: this transport relocates CLAUDE_CONFIG_DIR
        # to an isolated profile, and a relocated profile carries no stored
        # login for the CLI to fall back on.
        env_var_required=True,
        cost_basis=COST_BASIS_REQUESTS,
        status=STATUS_UNVERIFIED,
        note=(
            "Spends a Claude subscription allowance rather than per-token "
            "dollars. ANTHROPIC_API_KEY and the other metered credentials are "
            "stripped from the child environment because Claude Code's "
            "documented precedence puts them above the subscription token, "
            "and in --print mode the API key is always used when present "
            "(code.claude.com/docs/en/iam, read 2026-09-16). Leaving them in "
            "would put an API-billed run in the subscription cell. "
            "UNVERIFIED: CLI 2.1.273 accepted this exact argv and returned "
            "the documented JSON envelope on 2026-09-16, but the container "
            "that ran it authenticates first-party at list price, so nothing "
            "has yet exercised the subscription credential itself."
        ),
    ),
    MatrixCell(
        harness="codex",
        billing="api",
        provider="openai",
        aliases=("openai", "codex", "codex-api"),
        transport="OpenAI Chat Completions via the `openai` SDK",
        env_vars_read=("OPENAI_API_KEY",),
        env_var_required=True,
        cost_basis=COST_BASIS_USD,
        status=STATUS_UNVERIFIED,
        note=(
            "`codex` has meant this metered-key cell since PR #2710 and keeps "
            "meaning it, so no operator script changes meaning under them. "
            "UNVERIFIED: the transport is exercised offline against a fake "
            "SDK; no live OpenAI run is recorded in-tree."
        ),
    ),
    MatrixCell(
        harness="codex",
        billing="subscription",
        provider="codex-cli",
        aliases=("codex-cli", "codex-subscription"),
        transport="Codex CLI subprocess (`codex exec`)",
        env_vars_read=("CODEX_ACCESS_TOKEN",),
        # Optional: `--ignore-user-config` drops config.toml without touching
        # the login state, so CODEX_HOME keeps the operator's `codex login`
        # session and the variable is only the automation alternative.
        env_var_required=False,
        cost_basis=COST_BASIS_REQUESTS,
        status=STATUS_UNVERIFIED,
        note=(
            "Runs on a `codex login` ChatGPT session held under CODEX_HOME, "
            "or on CODEX_ACCESS_TOKEN for automation holding one, so it "
            "spends the plan's allowance. CODEX_API_KEY and OPENAI_API_KEY "
            "are stripped for the same reason the Claude cell strips its "
            "metered credentials. UNVERIFIED, and more thinly than the other "
            "cells: the argv comes from the openai/codex source read "
            "2026-09-16, the CLI is not installed in this repository's "
            "container, and no fixture has been through it. This cell also "
            "confirms no served model id, so it refuses to score a reply "
            "until the operator sets EVAL_CODEX_ALLOW_UNVERIFIED_MODEL."
        ),
    ),
    MatrixCell(
        harness="copilot",
        billing="api",
        provider="copilot-api",
        aliases=("copilot-api",),
        transport=("OpenAI-compatible HTTP endpoint at COPILOT_API_BASE_URL (operator-supplied)"),
        env_vars_read=("COPILOT_API_KEY", "GITHUB_COPILOT_TOKEN"),
        env_var_required=True,
        cost_basis=COST_BASIS_REQUESTS,
        status=STATUS_UNVERIFIED,
        note=(
            "The one cell with no endpoint this repository can name from a "
            "primary source, and the gap is GitHub's, not this harness's. "
            "GitHub Models, which used to fill it, was retired on 2026-07-30; "
            "re-probed 2026-09-16 it still answers HTTP 410. api.githubcopilot"
            ".com/chat/completions is live but documented nowhere on "
            "docs.github.com as a public API, and the headers third-party "
            "clients send it are community-observed only. GitHub's documented "
            "Copilot APIs are administrative and metrics endpoints, and "
            "Copilot usage is metered as premium requests against a seat "
            "rather than sold as a separate per-token product. So this cell "
            "is a configured seam rather than a claim: it refuses to run "
            "until the operator points COPILOT_API_BASE_URL at an endpoint "
            "they are entitled to use, takes any extra headers from "
            "COPILOT_API_HEADERS, and never guesses a default."
        ),
    ),
    MatrixCell(
        harness="copilot",
        billing="subscription",
        provider="copilot-cli",
        aliases=("copilot-cli", "copilot", "copilot-subscription"),
        transport="GitHub Copilot CLI subprocess over ACP",
        env_vars_read=(),
        env_var_required=False,
        cost_basis=COST_BASIS_REQUESTS,
        status=STATUS_VERIFIED,
        note=(
            "Reuses the operator's Copilot CLI login and needs no key. Live "
            "runs through it are recorded in scripts/eval/README.md and in "
            "the rule-audit instrument, including the 2026-07-29 token "
            "measurement behind --no-custom-instructions."
        ),
    ),
)

_BY_PAIR: dict[tuple[str, str], MatrixCell] = {
    (cell.harness, cell.billing): cell for cell in _CELLS
}


def _build_alias_index() -> dict[str, MatrixCell]:
    """Map every accepted spelling to its cell, refusing a duplicate.

    A duplicate would mean one name resolving to two billers depending on
    lookup order, which is the exact confusion this table exists to remove,
    so it fails at import rather than at dispatch.
    """
    index: dict[str, MatrixCell] = {}
    for cell in _CELLS:
        for alias in (cell.name, *cell.aliases):
            key = alias.strip().lower()
            existing = index.get(key)
            if existing is not None and existing is not cell:
                raise BillingMatrixError(
                    f"provider alias {alias!r} is claimed by both {existing.name} and {cell.name}"
                )
            index[key] = cell
    return index


_BY_ALIAS: dict[str, MatrixCell] = _build_alias_index()


def cells() -> tuple[MatrixCell, ...]:
    """Every cell, in harness-then-billing display order."""
    return _CELLS


def cell_for(harness: str, billing: str) -> MatrixCell:
    """Return the cell for one (harness, billing) pair.

    Raises `BillingMatrixError` naming the valid values, because a typo here
    would otherwise fall through to the default cell and quietly bill the run
    to the wrong account.
    """
    key = (harness.strip().lower(), billing.strip().lower())
    cell = _BY_PAIR.get(key)
    if cell is None:
        raise BillingMatrixError(
            f"no eval transport for harness {harness!r} with {billing!r} "
            f"billing. Harnesses: {', '.join(HARNESSES)}. Billing modes: "
            f"{', '.join(BILLING_MODES)}."
        )
    return cell


def cell_for_provider(name: str | None) -> MatrixCell | None:
    """Return the cell a provider name selects, or None when unrecognized."""
    return _BY_ALIAS.get((name or "").strip().lower())


def provider_for(harness: str, billing: str) -> str:
    """Return the canonical provider name for one (harness, billing) pair."""
    return cell_for(harness, billing).provider


def quota_billed_provider_names() -> frozenset[str]:
    """Every alias whose cell meters requests instead of per-token dollars.

    `_eval_common.cost_basis` reads this so the billing decision and the
    transport decision come from one table. Returning aliases rather than
    canonical names is deliberate: `cost_basis` is handed the raw operator
    string, and `EVAL_PROVIDER=copilot` has to answer the same way
    `EVAL_PROVIDER=copilot-cli` does.
    """
    return frozenset(
        alias for alias, cell in _BY_ALIAS.items() if cell.cost_basis == COST_BASIS_REQUESTS
    )


def known_selector_names() -> list[str]:
    """Sorted list of every spelling `--provider` accepts."""
    return sorted(_BY_ALIAS)


def resolve_selection(
    *,
    provider: str | None = None,
    harness: str | None = None,
    billing: str | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> MatrixCell:
    """Resolve a CLI/environment selection to exactly one cell.

    An explicit provider name wins, because it already names a cell and every
    existing script and archived command passes one. `--harness` plus
    `--billing` is the axis-first spelling. Supplying both is refused when
    they disagree instead of silently preferring one: a run whose flags
    contradict each other has no correct answer, and picking one would bill
    the operator on a transport they did not ask for.
    """
    env = os.environ if environ is None else environ
    selected_provider = (provider or env.get("EVAL_PROVIDER") or "").strip()
    selected_harness = (harness or env.get("EVAL_HARNESS") or "").strip()
    selected_billing = (billing or env.get("EVAL_BILLING") or "").strip()

    from_provider: MatrixCell | None = None
    if selected_provider:
        from_provider = cell_for_provider(selected_provider)
        if from_provider is None:
            raise BillingMatrixError(
                f"Unknown provider {selected_provider!r}. Valid: "
                + ", ".join(known_selector_names())
            )

    from_axes: MatrixCell | None = None
    if selected_harness or selected_billing:
        if not selected_harness or not selected_billing:
            raise BillingMatrixError(
                "harness and billing must be given together; got harness="
                f"{selected_harness!r}, billing={selected_billing!r}."
            )
        from_axes = cell_for(selected_harness, selected_billing)

    if from_provider is not None and from_axes is not None:
        if from_provider is not from_axes:
            raise BillingMatrixError(
                f"provider {selected_provider!r} selects {from_provider.name}, "
                f"but harness/billing select {from_axes.name}. Pass one or the "
                "other."
            )
        return from_provider
    if from_provider is not None:
        return from_provider
    if from_axes is not None:
        return from_axes
    return cell_for("claude", "api")


def apply_selection(
    *,
    provider: str | None = None,
    harness: str | None = None,
    billing: str | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> MatrixCell | None:
    """Resolve a CLI selection and publish it as `EVAL_PROVIDER`.

    `EVAL_PROVIDER` is how the selection reaches the adapter, the cost plan,
    and `call_api`, so every entry point has to write it the same way. One
    function rather than a line copied into each script is the point: the two
    copies that existed before wrote only `--provider`, and a second axis
    added to one of them would have gone missing from the other.

    An explicit provider name is written through verbatim. Rewriting it to its
    cell's canonical name would silently move `anthropic-sdk` onto the urllib
    transport, which is a different transport measuring the same biller.

    A provider name no cell claims is also written through, and the return is
    None. The matrix lists the cells an operator should choose between; the
    transport registry still holds retired rows such as `github-models` so an
    archived command keeps resolving, and this function is not the place to
    retire them. An unknown name is rejected downstream by
    `_providers.resolve_provider`, which is the component that knows what it
    can dispatch. Pairing an unmapped name with an axis pair is still refused,
    because there is no cell for the two to agree on.

    Returns the selected cell, or None when the caller named nothing, or named
    only a provider outside the matrix.
    """
    env = os.environ if environ is None else environ
    named = bool(provider) or bool(harness) or bool(billing)
    if not named:
        return None
    if provider and not harness and not billing:
        cell = cell_for_provider(provider)
        env["EVAL_PROVIDER"] = provider.strip()
        return cell
    cell = resolve_selection(
        provider=provider, harness=harness, billing=billing, environ=env
    )
    env["EVAL_PROVIDER"] = provider.strip() if provider else cell.provider
    return cell


def provider_help_text() -> str:
    """One `--provider` help string, shared by every entry point."""
    return (
        "Transport cell, as <harness>-<billing> or a legacy provider name. "
        "Cells: " + ", ".join(cell.name for cell in _CELLS) + ". Legacy names "
        "still resolve: anthropic (default) and anthropic-sdk are claude-api, "
        "openai and codex are codex-api, copilot is copilot-subscription. "
        "Baseline and variant run on the SAME cell; cross-cell scores are not "
        "comparable (ADR-058)."
    )


def format_matrix() -> str:
    """Render the matrix as a markdown table for `--help` and the README."""
    header = (
        "| Harness | Billing | Provider name | Transport | Credential | "
        "Cost basis | Status |\n"
        "|---|---|---|---|---|---|---|"
    )
    rows = [
        "| {harness} | {billing} | `{provider}` | {transport} | {credential} |"
        " {basis} | {status} |".format(
            harness=cell.harness,
            billing=cell.billing,
            provider=cell.provider,
            transport=cell.transport,
            credential=(
                ", ".join(f"`{name}`" for name in cell.env_vars_read)
                if cell.env_vars_read
                else "none (CLI login)"
            ),
            basis=cell.cost_basis,
            status=cell.status,
        )
        for cell in _CELLS
    ]
    return "\n".join([header, *rows])
