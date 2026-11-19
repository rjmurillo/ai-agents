"""Tests for the skill artifact flow gate: entry shape, producers, and parsing.

Every fixture repository is built in `tmp_path` by `artifact_flow_fixtures`.
Each negative test changes one thing and asserts the exit code and the gate's
own message, so a test cannot pass for the wrong reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.artifact_flow_fixtures import (  # noqa: F401
    _DEFAULTS,
    _PLAIN_KEY,
    _REPO_ROOT,
    _VALIDATION,
    Overrides,
    _block_yaml,
    _corpus,
    _handoff,
    _in,
    _keyed,
    _out,
    _run,
    _scalar,
    _write_skill,
    gate,
)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return _corpus(tmp_path)


def _refused(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Run the gate, require the violation exit code 1, and return stderr."""
    code, _, err = _run(root, capsys)
    assert code == 1, err
    return err


# --- positive ---------------------------------------------------------------


def test_valid_corpus_passes_and_reports_the_template_count(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(corpus, capsys)

    assert code == 0, err
    assert "examined 7 skill templates" in out
    assert "0 violation(s)" in out


def test_valid_corpus_credits_each_output_to_its_lifecycle_skill(corpus: Path) -> None:
    result = gate.survey(corpus)

    assert result.credit == {
        "spec-helper": "spec",
        "plan": "plan",
        "build": "build",
        "review": "review",
    }


# --- entry shape ------------------------------------------------------------


def test_legacy_list_shape_is_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _corpus(tmp_path, {"build": {"inputs": ["execution-plan"]}})

    err = _refused(tmp_path, capsys)

    assert "inputs must be a mapping keyed by artifact name, not list" in err


def test_scalar_entry_value_is_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _corpus(tmp_path, {"build": {"inputs": {"execution-plan": "yes"}}})

    err = _refused(tmp_path, capsys)

    assert "inputs.'execution-plan' must be empty or a mapping, not str" in err


def test_unknown_key_in_output_entry_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"build": {"outputs": [_out("implementation-change", paths="x/")]}})

    err = _refused(tmp_path, capsys)

    assert "outputs.'implementation-change' has unknown key 'paths'" in err


def test_scalar_outputs_are_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _corpus(tmp_path)
    _write_skill(tmp_path, "scalar-outputs", invoker="harness")
    path = tmp_path / gate.TEMPLATE_DIR / f"scalar-outputs{gate.TEMPLATE_SUFFIX}"
    path.write_text(
        path.read_text(encoding="utf-8").replace("metadata:\n", "metadata:\n  outputs: nope\n"),
        encoding="utf-8",
    )

    err = _refused(tmp_path, capsys)

    assert "outputs must be a mapping keyed by artifact name, not str" in err


@pytest.mark.parametrize(
    "bad_name",
    ["Bad_Name", "UPPER", "1leading", "double--dash", "trailing-", "requirements-ledger\n"],
    ids=[
        "underscore",
        "upper",
        "leading-digit",
        "double-dash",
        "trailing-dash",
        "trailing-newline",
    ],
)
def test_artifact_name_must_be_lowercase_kebab_case(
    corpus: Path, capsys: pytest.CaptureFixture[str], bad_name: str
) -> None:
    _write_skill(corpus, "extra-skill", invoker="harness", outputs=[_out(bad_name)])

    err = _refused(corpus, capsys)

    assert "must be lowercase kebab case" in err


@pytest.mark.parametrize(
    "bad_path",
    ["../x", "a/../b", "/etc", "C:\\x", "~/x", "$HOME/x", ".git/hooks", "plans/\n"],
    ids=[
        "parent",
        "embedded-parent",
        "absolute",
        "drive-letter",
        "home",
        "env-var",
        "dot-git",
        "trailing-newline",
    ],
)
def test_hostile_output_path_is_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str], bad_path: str
) -> None:
    _write_skill(
        corpus, "extra-skill", invoker="harness", outputs=[_out("scratch-note", path=bad_path)]
    )

    err = _refused(corpus, capsys)

    assert "must be a lowercase path relative to the artifact root" in err


def test_relative_directory_output_path_is_accepted(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        outputs=[_out("scratch-note", path="plans/active/")],
    )

    code, _, err = _run(corpus, capsys)

    assert code == 0, err


def test_string_required_flag_is_rejected(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        inputs=[_in("requirements-spec", required="yes")],
    )

    err = _refused(corpus, capsys)

    assert "required must be true or false" in err


def test_list_valued_source_is_rejected_without_crashing(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        inputs=[_in("requirements-spec", source=["skill"])],
    )

    err = _refused(corpus, capsys)

    assert "must be one of skill, user, repo" in err


def test_unknown_source_value_is_rejected(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        inputs=[_in("requirements-spec", source="network")],
    )

    err = _refused(corpus, capsys)

    assert "source 'network' must be one of skill, user, repo" in err


# --- producers and consumers ------------------------------------------------


def test_two_producers_of_one_artifact_are_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "second-writer", invoker="harness", outputs=[_out("execution-plan")])

    err = _refused(corpus, capsys)

    assert "artifact `execution-plan` has 2 producers (plan, second-writer)" in err
    assert "ADR-123 allows one" in err


def test_skill_sourced_input_without_a_producer_is_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "extra-skill", invoker="harness", inputs=[_in("ghost-artifact")])

    err = _refused(corpus, capsys)

    assert "input `ghost-artifact` has no producing skill" in err


@pytest.mark.parametrize("source", ["user", "repo"])
def test_user_or_repo_sourced_input_needs_no_producer(
    corpus: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    _write_skill(
        corpus, "extra-skill", invoker="harness", inputs=[_in("ghost-artifact", source=source)]
    )

    code, _, err = _run(corpus, capsys)

    assert code == 0, err


def test_shipped_consumer_of_a_repo_local_producer_is_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus, "local-writer", invoker="harness", repo_local=True, outputs=[_out("local-note")]
    )
    _write_skill(corpus, "shipped-reader", invoker="harness", inputs=[_in("local-note")])

    err = _refused(corpus, capsys)

    assert "shipped skill reads `local-note`, which only a repo-local skill produces" in err


def test_repo_local_consumer_of_a_repo_local_producer_is_accepted(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus, "local-writer", invoker="harness", repo_local=True, outputs=[_out("local-note")]
    )
    _write_skill(
        corpus, "local-reader", invoker="harness", repo_local=True, inputs=[_in("local-note")]
    )

    code, _, err = _run(corpus, capsys)

    assert code == 0, err


# --- frontmatter ------------------------------------------------------------


def test_unparseable_frontmatter_is_a_defect(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = corpus / gate.TEMPLATE_DIR / f"broken{gate.TEMPLATE_SUFFIX}"
    path.write_text("---\nname: broken\nmetadata: [unclosed\n---\n\nBody.\n", encoding="utf-8")

    err = _refused(corpus, capsys)

    assert "broken.SKILL.md.tmpl: frontmatter does not parse" in err


def test_duplicate_frontmatter_key_is_a_defect_not_a_crash(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = corpus / gate.TEMPLATE_DIR / f"dupe{gate.TEMPLATE_SUFFIX}"
    path.write_text("---\nname: x\nname: y\n---\n\nBody.\n", encoding="utf-8")

    err = _refused(corpus, capsys)

    assert "dupe.SKILL.md.tmpl: frontmatter does not parse" in err
    assert "duplicate key" in err


# --- edge cases from the ADR-123 amendment debate --------------------------


def test_mixed_type_option_keys_are_a_defect_not_a_crash(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_skill(corpus, "extra-skill", invoker="harness")
    text = path.read_text(encoding="utf-8").replace(
        "metadata:\n", "metadata:\n  outputs:\n    scratch-note:\n      1: a\n      bar: b\n"
    )
    path.write_text(text, encoding="utf-8")

    err = _refused(corpus, capsys)

    assert "has unknown key 1" in err
    assert "has unknown key 'bar'" in err


def test_artifact_is_no_longer_an_option_key(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus, "extra-skill", invoker="harness", outputs={"scratch-note": {"artifact": "x"}}
    )

    err = _refused(corpus, capsys)

    assert "outputs.'scratch-note' has unknown key 'artifact'" in err


@pytest.mark.parametrize("word", ["yes", "no", "on", "off"])
def test_yaml_boolean_artifact_names_are_named_as_such(
    corpus: Path, capsys: pytest.CaptureFixture[str], word: str
) -> None:
    path = _write_skill(corpus, "extra-skill", invoker="harness")
    text = path.read_text(encoding="utf-8").replace(
        "metadata:\n", f"metadata:\n  outputs:\n    {word}:\n"
    )
    path.write_text(text, encoding="utf-8")

    err = _refused(corpus, capsys)

    assert "is a YAML 1.1 boolean" in err


def test_quoted_artifact_key_is_refused_by_the_shipped_subset_parser(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_skill(corpus, "extra-skill", invoker="harness")
    text = path.read_text(encoding="utf-8").replace(
        "metadata:\n", 'metadata:\n  outputs:\n    "scratch-note":\n'
    )
    path.write_text(text, encoding="utf-8")

    err = _refused(corpus, capsys)

    assert "skillforge's stdlib frontmatter parser refuses this template" in err


@pytest.mark.parametrize(
    "block",
    ["  inputs: [{artifact: x}]\n", "  capability: {kind: orchestrator}\n"],
    ids=["flow-list-of-mappings", "flow-mapping"],
)
def test_flow_collections_are_refused_by_the_shipped_subset_parser(
    corpus: Path, capsys: pytest.CaptureFixture[str], block: str
) -> None:
    path = _write_skill(corpus, "extra-skill", invoker="harness")
    path.write_text(
        path.read_text(encoding="utf-8").replace("metadata:\n", f"metadata:\n{block}"),
        encoding="utf-8",
    )

    err = _refused(corpus, capsys)

    assert "skillforge's stdlib frontmatter parser refuses this template" in err


def test_a_skill_may_read_an_artifact_it_also_produces(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Recorded behavior: a self-produced input resolves through the skill
    # itself. The lifecycle checks credit it to that skill, so it cannot
    # satisfy the "earlier lifecycle skill" rule on its own.
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        inputs=[_in("scratch-note")],
        outputs=[_out("scratch-note")],
    )

    code, _, err = _run(corpus, capsys)

    assert code == 0, err
