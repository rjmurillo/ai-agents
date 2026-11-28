"""Globs, CODEOWNERS, policy, registry, and classifier parser tests."""

from __future__ import annotations

import json

import pytest

from scripts.pr_approval.classifier import (
    MAX_REASON_CHARS,
    ClassifierOutputError,
    StubClassifier,
    parse_classifier_output,
)
from scripts.pr_approval.codeowners import owners_for, parse_codeowners
from scripts.pr_approval.globs import GlobError, any_match, glob_match, validate_glob
from scripts.pr_approval.policy import PolicyError, parse_policy
from scripts.pr_approval.registry import RegistryError, parse_registry
from tests.pr_approval.fixtures import POLICY_TOML, REGISTRY_TOML


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("docs/*.md", "docs/a.md", True),
        ("docs/*.md", "docs/sub/a.md", False),
        ("docs/**/*.md", "docs/a.md", True),
        ("docs/**/*.md", "docs/x/y/a.md", True),
        ("docs/**", "docs", True),
        ("**/.env", ".env", True),
        ("**/.env", "a/b/.env", True),
        ("docs/*.md", "Docs/a.md", False),
        ("docs/*.md", "docs/A.MD", False),
        ("docs/*.md", "/docs/a.md", False),
        ("docs/*.md", "", False),
        ("a/b", "a", False),
    ],
)
def test_glob_match(pattern: str, path: str, expected: bool) -> None:
    assert glob_match(pattern, path) is expected


@pytest.mark.parametrize("pattern", ["", "/abs", "a//b", "a/../b", "./a", "a\\b", "a**/b", 7])
def test_validate_glob_rejects(pattern) -> None:
    with pytest.raises(GlobError):
        validate_glob(pattern)


def test_any_match() -> None:
    assert any_match(["x/*", "docs/*.md"], "docs/a.md")
    assert not any_match([], "docs/a.md")


CODEOWNERS_TEXT = """
# comment
/scripts/validation/   @owner
/templates/*           @owner
lefthook.yml           @owner # inline comment
docs/design/           @owner
docs/design/open.md
/build/scripts/        @owner
"""


@pytest.mark.parametrize(
    ("path", "owned"),
    [
        ("scripts/validation/a.py", True),
        ("scripts/validation/deep/a.py", True),
        ("scripts/validationx/a.py", False),
        ("templates/a.md", True),
        ("templates/sub/a.md", False),
        ("lefthook.yml", True),
        ("nested/lefthook.yml", True),
        ("docs/design/x.md", True),
        ("docs/design/open.md", False),
        ("build/scripts/x.py", True),
        ("docs/runbooks/x.md", False),
    ],
)
def test_codeowners_effective_owners(path: str, owned: bool) -> None:
    rules = parse_codeowners(CODEOWNERS_TEXT)
    assert bool(owners_for(rules, path)) is owned


def test_codeowners_inline_owner_parsing() -> None:
    rules = parse_codeowners(CODEOWNERS_TEXT)
    assert owners_for(rules, "lefthook.yml") == ("@owner",)


def test_codeowners_catch_all() -> None:
    rules = parse_codeowners("* @owner\n/ @owner\n")
    assert owners_for(rules, "any/path.md") == ("@owner",)


def test_policy_parses_test_fixture() -> None:
    policy = parse_policy(POLICY_TOML.encode())
    assert policy.mode == "observe"
    assert [rule.id for rule in policy.rules] == ["docs-prose-only"]
    assert policy.budget.max_classifier_calls == 1


BAD_POLICIES = [
    ("not toml", "=", "valid UTF-8 TOML"),
    ("unknown top key", POLICY_TOML + "\nextra = 1\n", "unknown keys"),
    (
        "wrong schema",
        POLICY_TOML.replace("schema_version = 1", "schema_version = 2"),
        "schema_version",
    ),
    (
        "bool schema",
        POLICY_TOML.replace("schema_version = 1", "schema_version = true"),
        "schema_version",
    ),
    ("bad mode", POLICY_TOML.replace('mode = "observe"\n\n', 'mode = "live"\n\n'), "mode must be"),
    ("no budget", POLICY_TOML.replace("[budget]", "[budgetx]"), "unknown keys"),
    ("budget missing key", POLICY_TOML.replace("deadline_seconds = 15\n", ""), "missing keys"),
    (
        "budget unknown key",
        POLICY_TOML.replace("deadline_seconds = 15", "deadline_seconds = 15\nfoo = 1"),
        "unknown",
    ),
    ("budget negative", POLICY_TOML.replace("max_rounds = 3", "max_rounds = -1"), "max_rounds"),
    (
        "budget spend string",
        POLICY_TOML.replace("max_spend_usd = 0.02", 'max_spend_usd = "x"'),
        "max_spend_usd",
    ),
    (
        "deadline zero",
        POLICY_TOML.replace("deadline_seconds = 15", "deadline_seconds = 0"),
        "deadline_seconds",
    ),
    (
        "rule unknown key",
        POLICY_TOML.replace('effect = "allow"', 'effect = "allow"\npriority = 1'),
        "unknown keys",
    ),
    (
        "selector unknown",
        POLICY_TOML.replace("max_files = 5", "max_files = 5\nlabels = []"),
        "unknown keys",
    ),
    ("bad effect", POLICY_TOML.replace('effect = "allow"', 'effect = "approve"'), "effect"),
    (
        "bad rule mode",
        POLICY_TOML.replace(
            'id = "docs-prose-only"\nmode = "observe"', 'id = "docs-prose-only"\nmode = "x"'
        ),
        "mode",
    ),
    (
        "rule exceeds repo",
        POLICY_TOML.replace(
            'id = "docs-prose-only"\nmode = "observe"', 'id = "docs-prose-only"\nmode = "enforce"'
        ),
        "exceeds",
    ),
    ("empty id", POLICY_TOML.replace('id = "docs-prose-only"', 'id = " "'), "id must"),
    ("missing id", POLICY_TOML.replace('id = "docs-prose-only"\n', ""), "missing 'id'"),
    ("bad author class", POLICY_TOML.replace('"independent"', '"human"'), "author_class"),
    ("bad glob", POLICY_TOML.replace('"docs/runbooks/*.md"', '"/docs/x.md"'), "repo-relative"),
    (
        "empty paths",
        POLICY_TOML.replace('paths = ["docs/runbooks/*.md", "docs/design/**/*.md"]', "paths = []"),
        "non-empty",
    ),
    ("max files zero", POLICY_TOML.replace("max_files = 5", "max_files = 0"), "max_files"),
    ("max files bool", POLICY_TOML.replace("max_files = 5", "max_files = true"), "max_files"),
    (
        "forbid not bool",
        POLICY_TOML.replace("forbid_binary = true", "forbid_binary = 1"),
        "boolean",
    ),
    (
        "rules not list",
        POLICY_TOML.split("[[rules]]")[0].replace("[budget]", "rules = 3\n[budget]"),
        "array",
    ),
    (
        "rule not table",
        POLICY_TOML.split("[[rules]]")[0].replace("[budget]", "rules = [1]\n[budget]"),
        "must be a table",
    ),
    ("duplicate ids", POLICY_TOML + POLICY_TOML[POLICY_TOML.index("[[rules]]") :], "duplicate"),
    (
        "classifier on allow",
        POLICY_TOML.replace(
            'effect = "allow"', 'effect = "allow"\nclassifier = "docs-prose-residue"'
        ),
        "only valid",
    ),
    (
        "unknown classifier",
        POLICY_TOML.replace('effect = "allow"', 'effect = "classify"\nclassifier = "nope"'),
        "unknown",
    ),
    ("protected unknown", POLICY_TOML + '\n[protected]\nremove = ["x"]\n', "unknown keys"),
    (
        "empty selector",
        POLICY_TOML.split("[rules.all]")[0] + "[rules.all]\n",
        "at least one selector",
    ),
]


@pytest.mark.parametrize(
    ("name", "text", "message"), BAD_POLICIES, ids=[c[0] for c in BAD_POLICIES]
)
def test_policy_rejects(name: str, text: str, message: str) -> None:
    with pytest.raises(PolicyError, match=message):
        parse_policy(text.encode())


def test_policy_rejects_non_utf8() -> None:
    with pytest.raises(PolicyError):
        parse_policy(b"\xff\xfe")


def test_policy_digest_tracks_bytes() -> None:
    assert (
        parse_policy(POLICY_TOML.encode()).digest
        != parse_policy((POLICY_TOML + "\n").encode()).digest
    )


def test_registry_parses() -> None:
    registry = parse_registry(REGISTRY_TOML.encode())
    assert registry.independent_authors == {1001}
    assert registry.is_bot(3003) and registry.is_bot(5005) and not registry.is_bot(4004)
    assert registry.principal(1001) == {1001}


def test_registry_aliases() -> None:
    registry = parse_registry(
        (REGISTRY_TOML + "\n[[aliases]]\nids = [1001, 9009]\nnote = 'x'\n").encode()
    )
    assert registry.principal(9009) == {1001, 9009}


BAD_REGISTRIES = [
    ("not toml", "=", "TOML"),
    ("unknown key", "schema_version = 1\nfoo = []\n", "unknown keys"),
    ("bad schema", "schema_version = 3\n", "schema_version"),
    ("list not array", "schema_version = 1\nagent_accounts = 3\n", "array"),
    ("entry not table", "schema_version = 1\nagent_accounts = [1]\n", "must be a table"),
    (
        "entry unknown key",
        "schema_version = 1\nagent_accounts = [{ id = 1, kind = 'x' }]\n",
        "unknown keys",
    ),
    ("id zero", "schema_version = 1\nagent_accounts = [{ id = 0 }]\n", "positive"),
    ("id string", "schema_version = 1\nagent_accounts = [{ id = '7' }]\n", "positive"),
    ("aliases not array", "schema_version = 1\naliases = 2\n", "array"),
    ("alias one id", "schema_version = 1\n[[aliases]]\nids = [1]\n", "at least two"),
    (
        "alias unknown key",
        "schema_version = 1\n[[aliases]]\nids = [1, 2]\nx = 1\n",
        "must be a table",
    ),
]


@pytest.mark.parametrize(
    ("name", "text", "message"), BAD_REGISTRIES, ids=[c[0] for c in BAD_REGISTRIES]
)
def test_registry_rejects(name: str, text: str, message: str) -> None:
    with pytest.raises(RegistryError, match=message):
        parse_registry(text.encode())


def test_registry_rejects_non_utf8() -> None:
    with pytest.raises(RegistryError):
        parse_registry(b"\xff")


@pytest.mark.parametrize("verdict", ["pass", "hold", "abstain"])
def test_classifier_output_valid(verdict: str) -> None:
    result = parse_classifier_output(
        json.dumps({"verdict": verdict, "reason": "r" * MAX_REASON_CHARS})
    )
    assert result.verdict == verdict


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        None,
        "[]",
        json.dumps({"verdict": "pass"}),
        json.dumps({"verdict": "pass", "reason": "x", "confidence": 1}),
        json.dumps({"verdict": "approve", "reason": "x"}),
        json.dumps({"verdict": "PASS", "reason": "x"}),
        json.dumps({"verdict": "pass", "reason": 5}),
        json.dumps({"verdict": "pass", "reason": "r" * (MAX_REASON_CHARS + 1)}),
    ],
)
def test_classifier_output_rejected(text) -> None:
    with pytest.raises(ClassifierOutputError):
        parse_classifier_output(text)


def test_stub_classifier_is_unavailable() -> None:
    assert StubClassifier().classify("docs-prose-residue", {}) is None


def test_policy_without_budget_rejected() -> None:
    text = POLICY_TOML.replace(
        "[budget]\nmax_rounds = 3\nmax_classifier_calls = 1\n"
        "max_spend_usd = 0.02\ndeadline_seconds = 15\n",
        "",
    )
    with pytest.raises(PolicyError, match="missing 'budget'"):
        parse_policy(text.encode())


def test_registry_principal_outside_alias_groups() -> None:
    registry = parse_registry((REGISTRY_TOML + "\n[[aliases]]\nids = [1001, 9009]\n").encode())
    assert registry.principal(4004) == {4004}
