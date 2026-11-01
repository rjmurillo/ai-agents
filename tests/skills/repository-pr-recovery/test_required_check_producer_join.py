"""Tests for repository-pr-recovery required_check_producer_join.py. Every GitHub read is faked."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/repository-pr-recovery/scripts/required_check_producer_join.py"
spec = importlib.util.spec_from_file_location("producer_join", SCRIPT)
assert spec is not None and spec.loader is not None
join = importlib.util.module_from_spec(spec)
spec.loader.exec_module(join)

SLUG = "rjmurillo/ai-agents"
RULES = f"repos/{SLUG}/rules/branches/main"
RULESETS = f"repos/{SLUG}/rulesets?includes_parents=true"
SHA = "abc1234"
RUNS = f"repos/{SLUG}/commits/{SHA}/check-runs?filter=all"


def rule(*pairs, ruleset_id=11):
    checks = [{"context": c, "integration_id": i} for c, i in pairs]
    params = {"required_status_checks": checks}
    return {"type": "required_status_checks", "ruleset_id": ruleset_id, "parameters": params}


def run(name, app_id, suite=1):
    return {
        "name": name,
        "app": {"id": app_id, "slug": "a"},
        "head_sha": SHA,
        "check_suite": {"id": suite},
        "status": "completed",
        "conclusion": "success",
    }


class FakeClient:
    """Serves lists by base endpoint, splitting them into pages of `size`."""

    def __init__(self, data, size=100, fail=None, ignore_page=False):
        self.data, self.size, self.fail, self.ignore_page = data, size, fail, ignore_page
        self.calls: list[str] = []

    def rest_get(self, endpoint):
        self.calls.append(endpoint)
        if endpoint in self.data and endpoint.startswith(f"repos/{SLUG}/pulls/"):
            return self.data[endpoint]
        if self.fail and self.fail in endpoint:
            raise RuntimeError("boom")
        sep = "&per_page=" if "&per_page=" in endpoint else "?per_page="
        base, _, tail = endpoint.partition(sep)
        page = int(tail.split("page=")[1])
        if self.ignore_page:
            page = 1
        value = self.data[base]
        if isinstance(value, dict):
            key = next(k for k in value if isinstance(value[k], list))
            chunk = value[key][(page - 1) * self.size : page * self.size]
            return {**{k: v for k, v in value.items() if k != key}, key: chunk}
        return value[(page - 1) * self.size : page * self.size]


def data(rules, runs, total=None):
    return {
        RULESETS: [{"id": 11, "name": "default", "enforcement": "active"}],
        RULES: rules,
        RUNS: {"total_count": len(runs) if total is None else total, "check_runs": runs},
    }


def test_all_produced_by_required_app():
    c = FakeClient(data([rule(("build", 15368))], [run("build", 15368, suite=9)]))
    out = join.join(c, SLUG, None, SHA, "main")
    assert out["required"][0]["state"] == join.PRODUCED
    assert out["required"][0]["runs"][0]["check_suite_id"] == 9
    assert out["summary"] == {join.PRODUCED: 1, join.OTHER_APP: 0, join.MISSING: 0}


def test_other_app_and_missing_classified():
    c = FakeClient(data([rule(("build", 15368), ("lint", 15368))], [run("build", 999)]))
    states = {r["context"]: r["state"] for r in join.join(c, SLUG, None, SHA, "main")["required"]}
    assert states == {"build": join.OTHER_APP, "lint": join.MISSING}


def test_pagination_reads_every_page():
    runs = [run(f"job{i}", 15368) for i in range(5)] + [run("build", 15368)]
    c = FakeClient(data([rule(("build", 15368))], runs), size=2)
    out = join.join(c, SLUG, None, SHA, "main")
    assert out["pages"]["check_runs"] == 3
    assert out["required"][0]["state"] == join.PRODUCED
    assert out["examined"] == 1 + 1 + 6


def test_unpinned_integration_accepts_any_app():
    c = FakeClient(data([rule(("build", None))], [run("build", 5)]))
    assert join.join(c, SLUG, None, SHA, "main")["required"][0]["state"] == join.PRODUCED


def test_pr_input_resolves_sha_and_base():
    d = data([rule(("build", 1))], [run("build", 1)])
    d[f"repos/{SLUG}/pulls/7"] = {"head": {"sha": SHA}, "base": {"ref": "main"}}
    out = join.join(FakeClient(d), SLUG, 7, None, None)
    assert out["pr"] == 7 and out["head_sha"] == SHA and out["base"] == "main"


def test_total_count_mismatch_fails_loud():
    c = FakeClient(data([rule(("build", 1))], [run("build", 1)], total=3))
    with pytest.raises(join.ExternalFailureError, match="total_count is 3"):
        join.join(c, SLUG, None, SHA, "main")


def test_repeated_page_fails_loud():
    c = FakeClient(data([rule(("build", 1))], [run("build", 1)]), ignore_page=True)
    with pytest.raises(join.ExternalFailureError, match="repeats page"):
        join.join(c, SLUG, None, SHA, "main")


def test_page_read_failure_names_endpoint():
    c = FakeClient(data([rule(("build", 1))], []), fail="check-runs")
    with pytest.raises(join.ExternalFailureError, match="check-runs"):
        join.join(c, SLUG, None, SHA, "main")


def test_required_contexts_dedupe_and_ignore_other_rules():
    rules = [{"type": "deletion"}, rule(("a", 1)), rule(("a", 1)), rule(("a", 2))]
    got = [(r["context"], r["integration_id"]) for r in join.required_contexts(rules)]
    assert got == [("a", 1), ("a", 2)]


def _patch(monkeypatch, client):
    monkeypatch.setattr(join, "make_client", lambda repo: client)


def _no_client(monkeypatch):
    """Fail if main builds a client: argument checks must run first."""

    def _refuse(repo):
        raise AssertionError("make_client called before argument validation")

    monkeypatch.setattr(join, "make_client", _refuse)


def test_main_exit_0_on_full_match(monkeypatch, capsys):
    _patch(monkeypatch, FakeClient(data([rule(("build", 1))], [run("build", 1)])))
    assert join.main(["--sha", SHA, "--base", "main"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"][join.PRODUCED] == 1


def test_main_exit_1_on_missing(monkeypatch):
    _patch(monkeypatch, FakeClient(data([rule(("build", 1))], [])))
    assert join.main(["--sha", SHA, "--base", "main"]) == 1


def test_main_exit_1_when_no_required_rule(monkeypatch):
    _patch(monkeypatch, FakeClient(data([], [run("build", 1)])))
    assert join.main(["--sha", SHA, "--base", "main"]) == 1


def test_main_exit_3_on_external_failure(monkeypatch):
    _patch(monkeypatch, FakeClient(data([], []), fail="rulesets"))
    assert join.main(["--sha", SHA, "--base", "main"]) == 3


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--pr", "1", "--sha", "x"],
        ["--sha", "x"],
        ["--pr", "1", "--slug", "nope"],
        ["--pr", "abc"],
    ],
)
def test_main_exit_2_on_bad_arguments(argv):
    assert join.main(argv) == 2


def test_main_exit_2_when_lib_missing(tmp_path, monkeypatch):
    # A sibling test in the same worker can leave a plugin root exported;
    # the lookup must fall through to the empty --repo tree.
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert join.main(["--repo", str(tmp_path), "--sha", SHA, "--base", "main"]) == 2


def test_help_exits_0():
    assert join.main(["--help"]) == 0


class EndlessClient:
    """Returns a distinct non-empty page until a hard stop well past the cap.

    The stop makes a removed cap fail loudly instead of hanging the test.
    """

    def __init__(self):
        self.calls = 0

    def rest_get(self, endpoint):
        self.calls += 1
        if self.calls > join.MAX_PAGES * 2:
            raise AssertionError("page cap did not stop the read")
        return [{"page": endpoint}]


def test_pagination_cap_fails_loud():
    with pytest.raises(join.ExternalFailureError, match="pagination exceeded 50 pages") as exc:
        join.paged(EndlessClient(), f"repos/{SLUG}/rulesets")
    assert "incomplete" in str(exc.value) and f"repos/{SLUG}/rulesets" in str(exc.value)


@pytest.mark.parametrize(
    "slug", ["a/b/c", "a b/c", "owner/", "/name", "a/b?x=1", "../x", "a/..", "./a", "o/n\n"]
)
def test_main_exit_2_on_bad_slug(slug, monkeypatch):
    _no_client(monkeypatch)
    assert join.main(["--sha", SHA, "--base", "main", "--slug", slug]) == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["--sha", "XYZ"],
        ["--sha", "abc12"],
        ["--sha", "-abc1234"],
        ["--sha", "abc1234\n"],
        ["--sha", ""],
    ],
)
def test_main_exit_2_on_bad_sha(argv, monkeypatch):
    _no_client(monkeypatch)
    assert join.main([*argv, "--base", "main"]) == 2


@pytest.mark.parametrize("base", ["-x", "a?b", "a#b", "a/../b"])
def test_main_exit_2_on_bad_cli_base(base, monkeypatch):
    _no_client(monkeypatch)
    assert join.main(["--sha", SHA, "--base", base]) == 2


@pytest.mark.parametrize("base", ["a?b=1", "x/../y", "-main"])
def test_bad_api_base_fails_external(base):
    d = {f"repos/{SLUG}/pulls/7": {"head": {"sha": SHA}, "base": {"ref": base}}}
    with pytest.raises(join.ExternalFailureError, match="base must not"):
        join.join(FakeClient(d), SLUG, 7, None, None)


def test_bad_api_sha_fails_external():
    d = {f"repos/{SLUG}/pulls/7": {"head": {"sha": "ZZ"}, "base": {"ref": "main"}}}
    with pytest.raises(join.ExternalFailureError, match="sha must be"):
        join.join(FakeClient(d), SLUG, 7, None, None)


def test_main_exit_3_on_bad_api_base(monkeypatch):
    d = {f"repos/{SLUG}/pulls/7": {"head": {"sha": SHA}, "base": {"ref": "a?b"}}}
    _patch(monkeypatch, FakeClient(d))
    assert join.main(["--pr", "7"]) == 3
