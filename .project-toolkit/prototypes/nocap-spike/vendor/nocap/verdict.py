"""Match claims to the turn's evidence ledger: NO_CAP (proven), CAP (contradicted), NO_RECEIPT.

Precision first: CAP is only returned when a tool output in this turn says the opposite of the claim.
Missing or ambiguous evidence is NO_RECEIPT, never CAP.
"""
from __future__ import annotations

import posixpath
import re

from . import tamper
from .evidence import _test_file, redact
from typing import Any, Dict, List, Optional

NO_CAP, CAP, NO_RECEIPT = "NO_CAP", "CAP", "NO_RECEIPT"


def _r(claim, verdict, ev=None, why="", quote=""):
    return {"kind": claim["kind"], "text": claim.get("text", ""), "start": claim.get("start"), "end": claim.get("end"),
            "verdict": verdict, "cite": ev["i"] if ev else None, "tool": ev["tool"] if ev else None,
            "cmd": ev.get("cmd", "") if ev else "", "exit": ev.get("exit") if ev else None,
            "why": why, "quote": redact(quote or "")[:160],
            "claim": {k: v for k, v in claim.items() if k not in ("text", "start", "end")}}


def _summary(ev):
    return ev["tests"][-1] if ev["tests"] else None


def _run_failed(ev) -> bool:
    if ev.get("no_tests"):
        return False  # pytest exit 5 / "no tests ran" is not a failure, and not a pass either
    t = _summary(ev)
    if t:
        return bool(t["failed"] or t["errors"])  # chained commands make the exit code unreliable here
    return ev.get("exit") not in (0, None)


def _any_failed(ev) -> bool:
    """Any summary in the output with failures (a chained or -x run), or a runner that stopped early."""
    ts = ev.get("tests") or []
    if ev.get("windowed") and ev.get("exit") not in (0, None) and not ev.get("chained"):
        return True  # a long output only partly parsed, and the runner exited non-zero: a failure may be in the gap
    if ev.get("stopped") or (ts and (ts[-1]["failed"] or ts[-1]["errors"])):
        return True
    # an earlier failing block counts unless a later, bigger green run covers it (a deliberate break probe, then the suite)
    return any((t["failed"] or t["errors"]) and _total(t) >= _total(ts[-1]) for t in ts[:-1])


def _run_quote(ev) -> str:
    t = _summary(ev)
    q = t["line"] if t else ""
    if ev.get("exit") not in (0, None):
        q = (q + f" (exit {ev['exit']})").strip()
    return q or "exit 0"


def _direct_failure(ev) -> bool:
    """See below. A bare non-zero exit with no parsed counts never contradicts (coverage gates, setup errors)."""
    t = _summary(ev)
    if not t:
        return False
    return _direct_failure_counts(ev)


def _direct_failure_counts(ev) -> bool:
    """Only a parsed failure count, or a clean non-zero exit of the runner itself, can contradict.
    A run with only errors and nothing passed or failed is a setup problem (imports, env): 🤔, not 🧢."""
    if not _run_failed(ev):
        return False
    t = _summary(ev)
    if t and not t["failed"] and not t["passed"]:
        return False
    return bool(_summary(ev)) or not (ev.get("masked") or ev.get("chained"))


def _total(t) -> int:
    return t["passed"] + t["failed"] + t["errors"]


RUNNER_RES = {
    "pytest": r"\bpy(?:\.)?test\b", "jest": r"\bjest\b", "vitest": r"\bvitest\b", "mocha": r"\bmocha\b",
    "go test": r"\bgo\s+tests?\b", "cargo test": r"\bcargo\s+(?:test|nextest)\b", "playwright": r"\bplaywright\b",
    "rspec": r"\brspec\b", "phpunit": r"\bphpunit\b", "ginkgo": r"\bginkgo\b", "gradle": r"\bgradlew?\b",
    "maven": r"\b(?:mvnw?|maven)\b", "unittest": r"\bunittest\b", "tox": r"\btox\b", "deno": r"\bdeno\s+test\b",
    "bun": r"\bbun\s+test\b", "ctest": r"\bctest\b", "swift test": r"\bswift\s+test\b",
    "dotnet test": r"\bdotnet\s+test\b", "xcodebuild": r"\bxcodebuild\b"}
FULL_ALSO_RE = re.compile(r"\b(?:full|whole|entire|complete) (?:test )?(?:suite|run)\b|\ball (?:the )?other tests\b|"
                          r"\beverything else\b|\brest of the (?:suite|tests)\b", re.I)
_SCOPE_STOP = {"the", "all", "full", "whole", "entire", "existing", "every", "test", "tests", "suite", "suites", "spec",
               "specs", "case", "cases", "remaining", "other", "our", "my", "your", "now", "still", "also", "both", "and",
               "these", "those", "a", "an", "rest", "complete", "repo", "repository", "project", "unit", "integration",
               "e2e", "automated", "python", "js", "ts", "go", "rust", "cargo", "jest", "vitest", "pytest", "npm", "core",
               "regression", "new", "added", "relevant", "affected", "related", "targeted", "focused", "confirmed",
               "verified", "checked", "ran", "run", "reran", "re-ran", "with", "after", "then", "that", "which", "pass",
               "passes", "passed", "passing", "fail", "fails", "failed", "failing", "green", "red", "on", "in", "for",
               "under", "of", "from", "original", "code", "without", "patch", "fix", "fixed", "change", "changes", "my",
               "previously", "were", "was", "are", "is", "now", "again", "local", "locally", "including", "plus", "its",
               "their", "this", "there", "here", "both", "two", "three", "four", "five", "every", "single", "one",
               "frontend", "backend", "mocha", "gradle", "maven", "mvn", "rspec", "phpunit", "ginkgo", "playwright",
               "tox", "deno", "bun", "unittest", "dotnet", "swift", "ctest", "not", "no", "any", "some", "latest",
               "last", "first", "previous", "final", "more", "most", "few", "many", "several", "current", "same",
               "only", "just", "quick", "slow", "fast", "flaky", "known", "each", "what", "where", "when", "so", "but",
               "or", "if", "i", "we", "it", "they", "them", "you", "me", "ok", "good", "done", "already", "successful",
               "successfully", "clean", "cleanly", "total", "overall", "together", "individually", "broader", "wider",
               "smaller", "larger", "everything", "nothing", "none", "lint", "type", "types", "typecheck", "build",
               "builds", "check", "checks", "ci", "workspace", "package", "packages", "module", "modules", "crate",
               "crates", "file", "files", "dir", "directory", "target", "targets", "whole-suite", "full-suite"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _scope_words(text: str) -> List[str]:
    """Names that narrow a test claim: `internal/spec`, "the native-output tests", "tests for the parser"."""
    low = re.sub(r"\*+", "", text or "").lower()
    words: List[str] = []
    for m in re.finditer(r"`([^`]+)`", low):
        words += re.split(r"[\s:]+", m.group(1))
    for m in re.finditer(r"((?:[\w./`-]+\s+){1,3})(?:test suites?|test cases?|tests?|suites?|specs?)\b", low):
        words += m.group(1).split()
    for m in re.finditer(r"\b(?:tests?|suites?|specs?)\s+(?:in|for|under|of)\s+(?:the\s+)?`?([\w./-]+)", low):
        words.append(m.group(1))
    out = []
    for w in words:
        w = w.strip("`*,.:;()[]'\"")
        if not w or w in _SCOPE_STOP or w.isdigit() or len(_norm(w)) < 3 or re.fullmatch(r"-+\w*", w):
            continue
        if w not in out:
            out.append(w)
    return out[:8]


def _names(e, words) -> bool:
    cmd = _norm(e.get("cmd", ""))
    for w in words:
        n = _norm(w)
        stem = re.sub(r"(?:ing|ed|es|s)$", "", n)
        if n in cmd or (len(stem) >= 4 and stem in cmd):
            return True
    return False


CUT_WHY = "that run's output was cut by a pipe; other crates/packages may be hidden"


def _green(e) -> bool:
    if e.get("no_tests") or _run_failed(e) or _any_failed(e) or e.get("partial"):
        return False
    return bool(_summary(e)) or (not e.get("masked") and e.get("exit") is not None) or _quiet_ok(e)


def _quiet_ok(e) -> bool:
    """`mvn -q test 2>&1 | tail -20` with exit 0 and no failure text: the tail would show a failure."""
    return bool(e.get("tail_only")) and e.get("exit") == 0 and not e.get("fail_text") and not _summary(e) and (
        not e.get("out_empty") or bool(e.get("quiet_silent")))


BROAD_RE = re.compile(r"(?i)\b(?:existing|other|remaining|rest|entire|whole|full|complete|every|everything)\b")
NARROW_RE = re.compile(r"(?i)\b(?:new|newly|added|relevant|affected|related|targeted|focused|specific|modified|updated|"
                       r"regression|these|those|this|that|my|both|two|three|four|five|single|individual)\b")


_RUNNERS = {"pytest", "py.test", "jest", "vitest", "mocha", "go", "cargo", "tox", "nox", "unittest", "rspec", "phpunit",
            "ctest", "dotnet", "mvn", "gradle", "gradlew", "./gradlew", "swift", "xcodebuild", "deno", "bun", "playwright",
            "cypress", "ava", "tap", "node", "npm", "pnpm", "yarn", "make"}
_WRAPPERS = {"npm", "pnpm", "yarn", "bun", "make", "node"}


def _runner(e) -> str:
    """The test runner a run used (`pytest`, `go`, `jest`...). A wrapper (`yarn jest`) names the runner after it;
    an unknown shape keeps the whole suite text, so only identical commands compare equal."""
    words = (e.get("suite") or "").split()
    known = [w for w in words if w in _RUNNERS]
    inner = [w for w in known if w not in _WRAPPERS]
    return (inner or known or [" ".join(words)])[0]


def _scoped_pass(c, fresh, runs=()):
    """A narrowed "X tests pass": judge it by the runs that name X, or by a green full-suite run. Else abstain."""
    words = _scope_words(c.get("text", "") + " " + c.get("scope_text", ""))
    full = [e for e in fresh if not e.get("subset")]
    if c.get("formerly_failing"):
        # A count of former failures does not identify them in a mixed run. Only a later complete green
        # run covers them; unrelated subset successes (or failures) cannot settle this claim.
        # ...and it must be the runner that showed them failing: a green `go test` says nothing about pytest failures
        runners = {_runner(e) for e in list(runs) + list(fresh) if not _green(e)}
        if full and _green(full[-1]) and all(_green(e) for e in fresh if e["i"] > full[-1]["i"]) and _runner(
                full[-1]) and (not runners or runners == {_runner(full[-1])}):
            return _r(c, NO_CAP, full[-1], quote=_run_quote(full[-1]))
        return _r(c, NO_RECEIPT, fresh[-1], why="no complete green run covers the formerly failing tests",
                  quote=_run_quote(fresh[-1]))
    if not words and BROAD_RE.search(c.get("text", "")) and not NARROW_RE.search(c.get("text", "")):
        # "all existing tests pass", "the remaining tests pass": as wide as the suite, so only a full run proves it
        if full and _green(full[-1]) and all(_green(e) for e in fresh if e["i"] > full[-1]["i"]):
            return _r(c, NO_CAP, full[-1], quote=_run_quote(full[-1]))
        e = full[-1] if full else fresh[-1]
        return _r(c, NO_RECEIPT, e, why="only a subset of the tests ran" if not full else
                  "the full run didn't pass", quote=_run_quote(e))
    if words:
        named = [e for e in fresh if _names(e, words)]
        if named:
            bad = [e for e in named if not _green(e)]
            if bad:
                why = CUT_WHY if bad[-1].get("partial") and not _run_failed(bad[-1]) else "a run of that scope didn't pass"
                return _r(c, NO_RECEIPT, bad[-1], why=why, quote=_run_quote(bad[-1]))
            return _r(c, NO_CAP, named[-1], quote=_run_quote(named[-1]))
        if full and _green(full[-1]):
            return _r(c, NO_CAP, full[-1], quote=_run_quote(full[-1]))
        return _r(c, NO_RECEIPT, fresh[-1], why="no run of that scope after the last code edit",
                  quote=_run_quote(fresh[-1]))
    if all(_green(e) for e in fresh):
        return _r(c, NO_CAP, fresh[-1], quote=_run_quote(fresh[-1]))
    if full and _green(full[-1]) and all(_green(e) for e in fresh if e["i"] > full[-1]["i"]):
        return _r(c, NO_CAP, full[-1], quote=_run_quote(full[-1]))
    bad = [e for e in fresh if not _green(e)]
    return _r(c, NO_RECEIPT, bad[-1], why="runs with mixed results; can't tell which one the claim means",
              quote=_run_quote(bad[-1]))


def _ledger_subset(e, evs) -> bool:
    """A file-only inventory cannot erase other test files already observed in this workdir."""
    files = e.get("test_files")
    return bool(files) and any(
        _test_file(p) and not any(_path_match(f, p) for f in files)
        for seen in evs if not (seen.get("where") and e.get("where") and seen["where"] != e["where"])
        for key in ("paths_seen", "paths_read", "paths_edited", "paths_written") for p in seen.get(key, []))


def _tests(c, evs):
    """Pick the run the claim is about, then compare. Only real test-runner commands count as runs:
    an echo/cat of a summary, a git-stash baseline and a background start are not evidence."""
    runs = [dict(e, subset=True) if _ledger_subset(e, evs) else e for e in evs
            if e["test_cmd"] and not e.get("background") and not e.get("baseline")]
    if c.get("cites_log"):  # "the log shows 44 passed": a read of that log is the receipt
        hits = [e for e in evs if _summary(e) and _summary(e)["passed"] == c.get("passed")]
        if hits:
            return _r(c, NO_CAP, hits[-1], quote=_run_quote(hits[-1]))
        return _r(c, NO_RECEIPT, why="no output shows that count")
    if not runs:
        seen = [e for e in evs if (e["test_cmd"] and (e.get("background") or e.get("baseline"))) or _summary(e)]
        if seen:  # test output read from a log, a background run, or a runner we don't recognise
            return _r(c, NO_RECEIPT, seen[-1], why="test output seen, but not from a test run we can attribute",
                      quote=_run_quote(seen[-1]))
        checks = [e for e in evs if e.get("check_cmd")]
        if checks:  # the agent's own check: a reproduce script, `python -c` asserts, a smoke or import check
            return _r(c, NO_RECEIPT, checks[-1], why="only the agent's own check script ran, not the test suite",
                      quote=_run_quote(checks[-1]))
        return _r(c, NO_RECEIPT, why="no test run in this turn")
    named = [k for k, rx in RUNNER_RES.items() if re.search(rx, c.get("text", ""), re.I)]
    if named:  # "`go test ./...` passes", "vitest is green": only that runner's runs describe the claim
        uses = lambda e, ks: any(re.search(RUNNER_RES[k], e.get("cmd", ""), re.I) for k in ks)
        mine = [e for e in runs if uses(e, named) or not uses(e, RUNNER_RES)]  # npm test / make test may wrap it
        if not mine:
            return _r(c, NO_RECEIPT, runs[-1], why=f"no {named[0]} run in this turn", quote=_run_quote(runs[-1]))
        runs = mine
    n = c.get("passed") if c.get("passed") is not None else c.get("total")
    last_edit = max((e["i"] for e in evs if e.get("edit")), default=0)
    fresh = [e for e in runs if e["i"] > last_edit]
    if c.get("count_only"):  # "552 passed" states a count, not that nothing failed
        hits = [e for e in runs if _summary(e) and _summary(e)["passed"] == n]
        fresh_hits = [e for e in hits if e["i"] > last_edit]
        if fresh_hits:
            return _r(c, NO_CAP, fresh_hits[-1], quote=_run_quote(fresh_hits[-1]))
        if hits:
            return _r(c, NO_RECEIPT, hits[-1], why="code changed after that run", quote=_run_quote(hits[-1]))
        return _r(c, NO_RECEIPT, runs[-1], why=f"no run shows {n} passed", quote=_run_quote(runs[-1]))
    if c.get("fixed_failing"):
        red = [e for e in runs if _run_failed(e)]
        green = [e for e in fresh if not _run_failed(e) and not _any_failed(e) and _summary(e) and not e.get("subset")]
        if red and green and green[-1]["i"] > red[-1]["i"]:
            return _r(c, NO_CAP, green[-1], quote=f"{_run_quote(red[-1])} → {_run_quote(green[-1])}")
        return _r(c, NO_RECEIPT, runs[-1], why="no failing run earlier in this turn", quote=_run_quote(runs[-1]))
    if c.get("all_pass") and not c.get("scoped") and any(e.get("skip_added") for e in evs) and \
            any(_run_failed(e) for e in runs):
        e = fresh[-1] if fresh else runs[-1]
        return _r(c, NO_RECEIPT, e, why="a test was marked skip after a failing run", quote=_run_quote(e))
    suites = {e.get("suite") for e in fresh}
    can_cap = not c.get("scoped") and not (c.get("table") and len(suites) > 1)
    if c.get("fails"):
        words = _scope_words(c.get("text", ""))
        if words:  # "the date tests fail without the patch": an unrelated failing suite is not that receipt
            runs = [e for e in runs if _names(e, words)]
            if not runs:
                return _r(c, NO_RECEIPT, why="no run of that scope in this turn")
        failing = [e for e in runs if _run_failed(e)]
        if c.get("asserts_pass"):  # says all pass and names a failure: no run is a receipt for that sentence
            e = failing[-1] if failing else runs[-1]
            return _r(c, NO_RECEIPT, e, why="says all tests pass, but names a failure", quote=_run_quote(e))
        if c.get("failed"):
            hits = [e for e in runs if _summary(e) and c["failed"] in (_summary(e)["failed"],
                                                                         _summary(e)["failed"] + _summary(e)["errors"])]
            if hits:
                return _r(c, NO_CAP, hits[-1], quote=_run_quote(hits[-1]))
        elif failing:
            return _r(c, NO_CAP, failing[-1], quote=_run_quote(failing[-1]))
        return _r(c, NO_RECEIPT, runs[-1], why="no run shows that failure", quote=_run_quote(runs[-1]))
    if not fresh:
        return _r(c, NO_RECEIPT, runs[-1], why="code changed after the last test run", quote=_run_quote(runs[-1]))
    full_fresh = [e for e in fresh if not e.get("subset")]
    if (c.get("scoped") or n is not None) and FULL_ALSO_RE.search(c.get("text", "")) and not (
            full_fresh and _green(full_fresh[-1])):
        e = full_fresh[-1] if full_fresh else fresh[-1]
        return _r(c, NO_RECEIPT, e, why="the claim also covers the full suite", quote=_run_quote(e))
    if n is not None:  # "all 44 tests pass": find the run with that count, then its latest rerun
        match = [e for e in fresh if _summary(e) and n in (_summary(e)["passed"], _total(_summary(e)))]
        if match and not c.get("scoped") and all(e.get("subset") for e in match):
            return _r(c, NO_RECEIPT, match[-1], why="only a subset of the tests ran", quote=_run_quote(match[-1]))
        match = [e for e in match if c.get("scoped") or not e.get("subset")] or match
        if not match:
            return _r(c, NO_RECEIPT, fresh[-1], why=f"no run shows {n} tests", quote=_run_quote(fresh[-1]))
        e = match[-1]
        later = [x for x in fresh if x["i"] > e["i"] and x.get("suite") == e.get("suite") and _summary(x)]
        if later and _direct_failure(later[-1]) and can_cap:
            return _r(c, CAP, later[-1], why="the latest run of that suite failed", quote=_run_quote(later[-1]))
        if later and _total(_summary(later[-1])) != _total(_summary(e)):
            return _r(c, NO_RECEIPT, later[-1], why="a later run of that suite has another count",
                      quote=_run_quote(later[-1]))
        e = later[-1] if later else e
        if _summary(e) and _summary(e)["passed"] == n and _run_failed(e) and c.get("failed") != 0:
            return _r(c, NO_RECEIPT, e, why=f"{n} did pass; the run also had failures", quote=_run_quote(e))
        if _run_failed(e) and any(x["i"] > e["i"] for x in fresh):
            return _r(c, NO_RECEIPT, e, why="a later run (another scope) came after this failure", quote=_run_quote(e))
        if _direct_failure(e) and can_cap:
            return _r(c, CAP, e, quote=_run_quote(e))
        if _run_failed(e):
            return _r(c, NO_RECEIPT, e, why="the claim may mean another part of the run", quote=_run_quote(e))
        if _any_failed(e):
            return _r(c, NO_RECEIPT, e, why="that run also shows failures", quote=_run_quote(e))
        if e.get("partial"):
            return _r(c, NO_RECEIPT, e, why=CUT_WHY, quote=_run_quote(e))
        return _r(c, NO_CAP, e, quote=_run_quote(e))
    if c.get("scoped") and not c.get("table"):
        return _scoped_pass(c, fresh, runs)
    full = [e for e in fresh if not e.get("subset")]
    if not full:
        e = fresh[-1]
        if _summary(e) and _summary(e)["failed"] and can_cap and c.get("all_pass"):
            return _r(c, CAP, e, why="even the subset that ran had failures", quote=_run_quote(e))
        if c.get("scoped") and not _run_failed(e) and not _any_failed(e) and not e.get("no_tests") and \
                not e.get("partial") and (
                _summary(e) or not e.get("masked")):
            return _r(c, NO_CAP, e, quote=_run_quote(e))
        return _r(c, NO_RECEIPT, e, why="only a subset of the tests ran", quote=_run_quote(e))
    e = full[-1]
    if c.get("table") and len(suites) > 1 and any(_run_failed(x) for x in fresh):
        return _r(c, NO_RECEIPT, e, why="several suites ran with mixed results", quote=_run_quote(e))
    if e.get("no_tests"):
        return _r(c, NO_RECEIPT, e, why="no tests ran", quote=_run_quote(e))
    if _direct_failure(e) and can_cap:
        return _r(c, CAP, e, quote=_run_quote(e))
    if _run_failed(e):
        return _r(c, NO_RECEIPT, e, why="a run failed; the claim may mean another suite", quote=_run_quote(e))
    if not _summary(e) and (e.get("masked") or e.get("exit") is None) and not _quiet_ok(e):
        return _r(c, NO_RECEIPT, e, why="that run can't prove it (exit code hidden)", quote=_run_quote(e))
    if _any_failed(e):
        return _r(c, NO_RECEIPT, e, why="that run also shows failures", quote=_run_quote(e))
    if e.get("partial"):
        return _r(c, NO_RECEIPT, e, why=CUT_WHY, quote=_run_quote(e))
    return _r(c, NO_CAP, e, quote=_run_quote(e))


def _ci(c, evs):
    cands = [e for e in evs if "ci_pass" in e.get("git", {})]
    if not cands:
        return _r(c, NO_RECEIPT, why="no CI check read in this turn")
    last = cands[-1]
    if last["git"].get("ci_pending") and not last["git"]["ci_fail"]:
        return _r(c, NO_RECEIPT, last, why="checks still pending", quote=last["git"].get("ci_line", ""))
    if last["git"]["ci_fail"] and not c.get("scoped"):
        return _r(c, CAP, last, quote=last["git"].get("ci_line", ""))
    if last["git"]["ci_fail"]:
        return _r(c, NO_RECEIPT, last, why="a check failed; the claim names another one")
    if last["git"]["ci_pass"]:
        return _r(c, NO_CAP, last, quote=last["git"].get("ci_line", ""))
    return _r(c, NO_RECEIPT, last, why="CI output had no pass/fail")


def _by_flag(c, evs, flag, label):
    cands = [e for e in evs if e.get(flag) and not e.get("background")]
    compiled = [e for e in evs if e.get("test_cmd") and re.search(
        r"\b(?:go\s+test|cargo|mvnw?|gradlew?|dotnet|swift|xcodebuild|tsc|zig|gleam|stack|cabal)\b", e.get("cmd", ""))]
    if not cands and flag == "build_cmd" and compiled:
        return _r(c, NO_RECEIPT, compiled[-1], why="only a test run compiled it", quote=_run_quote(compiled[-1]))
    if not cands:
        return _r(c, NO_RECEIPT, why=f"no {label} command in this turn")
    last = cands[-1]
    if flag == "build_cmd" and any(e.get("any_edit", e.get("edit")) and e["i"] > last["i"] for e in evs):
        return _r(c, NO_RECEIPT, last, why="code changed after the last build")
    if last["ok"]:
        if last.get("masked"):
            return _r(c, NO_RECEIPT, last, why="exit code hidden by a pipe")
        return _r(c, NO_CAP, last, quote=f"exit {last.get('exit', 0) if last.get('exit') is not None else 0}")
    if (last.get("exit") is None and not last.get("error")) or last.get("masked"):
        return _r(c, NO_RECEIPT, last, why="no reliable exit code")
    return _r(c, CAP, last, quote=last.get("error") or f"exit {last.get('exit')}")


def _merged(c, evs):
    keys = ("git_merge_ok",) if c.get("git_merge") else ("merge_ok", "pr_view_state", "git_merge_ok")
    cands = [e for e in evs if any(k in e.get("git", {}) for k in keys)]
    pr = c.get("pr")
    if pr is not None:
        cands = [e for e in cands if pr in e["git"].get("merge_cmd_prs", []) + e["git"].get("merged_prs", [])
                 + e["git"].get("pr_view_prs", []) or f"#{pr}" in e["git"].get("merge_line", "")]
    if not cands:
        return _r(c, NO_RECEIPT, why="no merge" + (f" of #{pr}" if pr else "") + " in this turn")
    good = [e for e in cands if e["git"].get("merge_ok") or e["git"].get("pr_view_state") == "MERGED"
            or e["git"].get("git_merge_ok")]
    if good:
        return _r(c, NO_CAP, good[-1], quote=good[-1]["git"].get("merge_line", "") or "state MERGED")
    # a git merge conflict is usually resolved later in the turn, so it never stamps 🧢 on its own
    later_ok = lambda e: any(x["i"] > e["i"] and (x.get("git", {}).get("merge_ok") or x.get("git", {}).get(
        "pr_view_state") == "MERGED") for x in evs)
    cands_pr = [e for e in cands if pr is None or pr in e["git"].get("merge_cmd_prs", []) + e["git"].get(
        "pr_view_prs", []) + e["git"].get("merged_prs", [])]
    if cands_pr and cands_pr[-1] is not cands[-1]:
        cands = cands_pr
    bad = [e for e in cands[-1:] if (e["git"].get("merge_failed")
                                or (pr is not None and e["git"].get("pr_view_state") == "CLOSED"
                                    and pr in e["git"].get("pr_view_prs", []))) and not later_ok(e)
           and not c.get("git_merge")]
    if bad:
        g = bad[-1]["git"]
        q = g.get("merge_line") or f"state {g.get('pr_view_state')}"
        return _r(c, CAP, bad[-1], quote=q)
    last = cands[-1]
    viewed = {p for e in cands for p in e["git"].get("pr_view_prs", [])}
    if last["git"].get("pr_view_state") == "OPEN" and not c.get("git_merge") and (
            pr is not None or len(viewed) <= 1) and not last.get("chained"):
        return _r(c, CAP, last, quote="state OPEN")  # the latest look at the PR, in this turn, says it isn't merged
    return _r(c, NO_RECEIPT, cands[-1], why="merge output was not conclusive")


def _pushed(c, evs):
    cands = [e for e in evs if "push_ok" in e.get("git", {})]
    if not cands:
        return _r(c, NO_RECEIPT, why="no git push in this turn")
    b = c.get("branch")
    if b:
        match = [e for e in cands if b in e["git"].get("push_refs", []) or re.search(r"(?<![\w/-])" + re.escape(b) +
                                                                                    r"(?![\w/-])", e.get("cmd", ""))]
        if not match:
            ok_other = [e for e in cands if e["git"]["push_ok"] and e["git"].get("push_refs")]
            if ok_other:
                refs = ", ".join(ok_other[-1]["git"]["push_refs"][:3])
                return _r(c, CAP, ok_other[-1], why=f"push went to {refs}, not {b}", quote=f"pushed {refs}")
            return _r(c, NO_RECEIPT, cands[-1], why=f"pushes seen, none to {b}")
        cands = match
    good = [e for e in cands if e["git"]["push_ok"]]
    if good:
        return _r(c, NO_CAP, good[-1], quote=good[-1]["git"].get("push_line", ""))
    bad = [e for e in cands if e["git"].get("push_failed")]
    if bad:
        return _r(c, CAP, bad[-1], quote=bad[-1]["git"].get("push_line") or f"exit {bad[-1].get('exit')}")
    return _r(c, NO_RECEIPT, cands[-1], why="push output was not conclusive")


def _committed(c, evs):
    cands = [e for e in evs if "commit_ok" in e.get("git", {})]
    if not cands:
        return _r(c, NO_RECEIPT, why="no git commit in this turn")
    sha = c.get("sha")
    good = [e for e in cands if e["git"]["commit_ok"]]
    if sha:
        good = [e for e in good if e["git"].get("commit", "").startswith(sha) or sha.startswith(e["git"].get("commit", "~"))]
    if good:
        return _r(c, NO_CAP, good[-1], quote=good[-1]["git"].get("commit_line", ""))
    if any(e["git"]["commit_ok"] for e in cands):
        return _r(c, NO_RECEIPT, cands[-1], why="commit SHA differs")
    already = bool(re.search(r"\balready\b|\bearlier\b|\bpreviously\b", c.get("text", "").lower()))
    bad = [e for e in cands if e["git"].get("commit_failed") or (e["git"].get("commit_nothing") and not already)]
    if bad:
        return _r(c, CAP, bad[-1], quote=bad[-1]["git"].get("commit_line") or f"exit {bad[-1].get('exit')}")
    return _r(c, NO_RECEIPT, cands[-1], why="commit output was not conclusive")


def _pr_opened(c, evs):
    cands = [e for e in evs if "pr_create_ok" in e.get("git", {})]
    if not cands:
        return _r(c, NO_RECEIPT, why="no gh pr create in this turn")
    pr = c.get("pr")
    good = [e for e in cands if e["git"]["pr_create_ok"] and (pr is None or pr in e["git"].get("opened_prs", []))]
    if good:
        return _r(c, NO_CAP, good[-1], quote=f"/pull/{good[-1]['git']['opened_prs'][-1]}")
    if any(e["git"]["pr_create_ok"] for e in cands):
        return _r(c, NO_RECEIPT, cands[-1], why=f"opened a different PR than #{pr}")
    bad = [e for e in cands if e["git"].get("pr_create_failed")]
    if bad:
        return _r(c, CAP, bad[-1], quote=bad[-1].get("error") or f"exit {bad[-1].get('exit')}")
    return _r(c, NO_RECEIPT, cands[-1], why="gh pr create output was not conclusive")


def _norm_url(u: str) -> str:
    return u.rstrip("/").lower()


def _url(c, evs):
    want = _norm_url(c["url"])
    cands = [e for e in evs if any(_norm_url(u) == want for u in e.get("urls", []))]
    if not cands:
        return _r(c, NO_RECEIPT, why="URL not fetched in this turn")
    for e in reversed(cands):
        if e.get("http"):
            code = e["http"][-1]
            if c.get("status") and code == c["status"]:
                return _r(c, NO_CAP, e, quote=f"HTTP {code}")  # an honest 404/503 report matches
            if c.get("status") and code != c["status"]:
                return _r(c, CAP, e, why=f"claimed {c['status']}", quote=f"HTTP {code}")
            if code < 400:
                return _r(c, NO_CAP, e, quote=f"HTTP {code}")
            return _r(c, CAP, e, quote=f"HTTP {code}")
    e = cands[-1]
    if e["tool"] != "terminal":
        if e["ok"]:
            return _r(c, NO_CAP, e, quote=f"{e['tool']} fetched it")
        if e.get("error"):
            return _r(c, CAP, e, quote=e["error"])
    return _r(c, NO_RECEIPT, e, why="no HTTP status in the output")


def _path_match(claim_path: str, seen: str) -> bool:
    a = claim_path.strip("`").lstrip("./") if not claim_path.startswith("/") else claim_path
    b = seen.strip("`")
    if not a or not b:
        return False
    if a == b or b.endswith("/" + a) or a.endswith("/" + b.lstrip("./")):
        return True
    return "/" not in a and posixpath.basename(b) == a


def _file(c, evs):
    """🧾 needs a successful call that wrote that path (a write/patch tool, a redirect, sed -i, cp/mv, rm...).
    A command that merely names the file, or edits that all failed, are not receipts."""
    p = c["path"]
    hit = lambda e, key: any(_path_match(p, s) for s in e.get(key, []))
    edits = [e for e in evs if hit(e, "paths_edited")]
    good = [e for e in edits if e["ok"]]
    if good:
        return _r(c, NO_CAP, good[-1], quote=f"{good[-1]['tool']} ok")
    if edits:
        # 🧢 for files is DISABLED: on real agent runs most "failed write" caps were edits made another way
        # (sed, heredoc, editor pseudo-commands). A failed write is a 🤔 with the error quoted.
        return _r(c, NO_RECEIPT, edits[-1], why="the write we saw failed", quote=edits[-1].get("error") or "write failed")
    told = [e for e in evs if hit(e, "paths_reported")]
    if told:  # a script's own output: "Wrote report.pdf"
        return _r(c, NO_CAP, told[-1], quote=f"{told[-1]['tool']} reported writing it")
    seen = [e for e in evs if hit(e, "paths_seen") or hit(e, "paths_read") or _names_path(e, p)]
    if seen:
        return _r(c, NO_RECEIPT, seen[-1], why="the file was only read or named by a command, not written")
    return _r(c, NO_RECEIPT, why="no write to that path in this turn")


def _names_path(e, p: str) -> bool:
    base = posixpath.basename(p.strip("`").rstrip("/"))
    return len(base) >= 3 and bool(re.search(r"(?<![\w.-])" + re.escape(base) + r"(?![\w-])", e.get("cmd", "")))


def _sha(c, evs):
    s = c["sha"]
    if c.get("head"):
        heads = [e for e in evs if e.get("head_sha")]
        if heads:
            h = heads[-1]["head_sha"]
            if h.startswith(s):
                return _r(c, NO_CAP, heads[-1], quote=h[:12])
            if not any(e.get("git") and e["i"] > heads[-1]["i"] for e in evs):  # nothing moved HEAD after
                return _r(c, CAP, heads[-1], quote=f"HEAD {h[:12]}")
            return _r(c, NO_RECEIPT, heads[-1], why="HEAD may have moved since")
    for e in reversed(evs):
        if any(x.startswith(s) or s.startswith(x) for x in e.get("shas", []) if len(x) >= 7):
            return _r(c, NO_CAP, e, quote=s)
    return _r(c, NO_RECEIPT, why="SHA not in any tool output")


def _number(c, evs):
    from .evidence import unit_stem
    v = c["value"]
    stem = unit_stem((c.get("unit") or "").split()[-1] if c.get("unit") else "")
    if c.get("action") and stem == "file":
        diffs = [e for e in evs if e.get("diff_files")]
        if diffs:
            d = diffs[-1]["diff_files"]
            if d["n"] == int(v) and not (d["scoped"] and c.get("repo_wide")):
                return _r(c, NO_CAP, diffs[-1], quote=d["line"])
            return _r(c, NO_RECEIPT, diffs[-1], why="the diff shows another count" if d["n"] != int(v) else
                      "that diff was limited to a path", quote=d["line"])
    for e in evs:  # the number must appear with its unit in one output, not anywhere
        if f"{v}|{stem}" in e.get("num_units", []):
            return _r(c, NO_CAP, e, quote=f"{v} {c.get('unit', '')}".strip())
    unit = (c.get("unit") or "").split()[-1:] or [""]
    counted = {"file": [e for e in evs if e.get("paths_written") and e["ok"]],
               "commit": [e for e in evs if e.get("git", {}).get("commit_ok")]}
    for prefix, hits in counted.items():
        if unit[0].startswith(prefix) and hits and v.isdigit() and int(v) == len(hits):
            return _r(c, NO_CAP, hits[-1], quote=f"{len(hits)} successful {prefix} writes" if prefix == "file"
                      else f"{len(hits)} commits")
    return _r(c, NO_RECEIPT, why="number not in any tool output")


def _keep(r) -> bool:
    """Unmatched numbers stay silent unless they're an action count ("changed 3 files")."""
    if r["claim"].get("quoted") and r["verdict"] != NO_CAP:
        return False
    return not (r["kind"] == "number" and r["verdict"] == NO_RECEIPT and not r["claim"].get("action"))


def _many_places(evs) -> bool:
    return len({e.get("where") for e in evs if e.get("where")}) > 1


def _guard(fn, key):
    """In a turn that touched several repos, a failure in one can't contradict a claim about another."""
    def judge_one(c, evs):
        r = fn(c, evs)
        if r["verdict"] == CAP and key(evs):
            r = dict(r, verdict=NO_RECEIPT, why="several repos in this turn; can't tell which one the claim means")
        return r
    return judge_one


JUDGES = {"tests": _tests,
          "ci": _guard(_ci, lambda evs: _many_places([e for e in evs if "ci_pass" in e.get("git", {})]) or len(
              {e.get("cmd") for e in evs if "ci_pass" in e.get("git", {})}) > 1 and _many_places(evs)),
          "merged": _guard(_merged, lambda evs: _many_places([e for e in evs if e.get("git")])),
          "pushed": _guard(_pushed, lambda evs: _many_places([e for e in evs if "push_ok" in e.get("git", {})])),
          "committed": _guard(_committed, lambda evs: _many_places([e for e in evs if "commit_ok" in e.get("git", {})])),
          "pr_opened": _pr_opened, "url": _url, "file": _file, "sha": _sha, "number": _number,
          "build": lambda c, e: _by_flag(c, e, "build_cmd", "build"),
          "deployed": lambda c, e: _by_flag(c, e, "deploy_cmd", "deploy"),
          # a completion claim in a language No Cap can't parse yet: recorded (hidden), never silently dropped
          "unchecked": lambda c, e: _r(c, NO_RECEIPT, why="non-English completion claim; No Cap can't check this "
                                                          "kind in that language yet")}


# 🧢 is switched off for kinds that did not reach 0.9 precision on hand-labelled real agent runs.
# They still earn 🧾 and 🤔; a contradiction is reported as 🤔 with the disagreeing output quoted.
DISABLED_CAP = {
    "file": "🧢 off for files: on real runs, most failed writes were redone another way",
    "build": "🧢 off for builds: on real runs, chained or edited commands made the exit code unreliable",
}


# Claim types where a tool call is the normal way to back the claim. A 🤔 is only stamped by default when one
# of these has no relevant call at all in the turn (no test command for "tests pass", no push for "pushed").
EXPECTED_KINDS = {"tests", "build", "ci", "pushed", "merged", "committed", "pr_opened", "deployed", "url", "file"}
SHOW_UNCERTAIN = ("off", "strict", "expected", "all")
# Visible 🤔 is opt-in. Blind evals: `expected` 🤔 were right 0/12 and `strict` 🤔 0/6 on unseen runs (all six were
# proven by the agent's own check scripts, which now count as test-like evidence). That fix has no fresh labelled
# sample behind it yet, so the default stamps 🧾 and 🧢 only; unsure claims are still recorded for /nocap all and /cap.
DEFAULT_SHOW_UNCERTAIN = "off"


def absent(r: Dict[str, Any]) -> bool:
    """A 🤔 because nothing relevant ran (no cited call), on a claim type that expects a receipt."""
    return r["verdict"] == NO_RECEIPT and r.get("cite") is None and r["kind"] in EXPECTED_KINDS


def zero_test_runs(r: Dict[str, Any]) -> bool:
    """"Tests pass" in a turn with no test command and no test output at all."""
    c = r.get("claim", {})
    return absent(r) and r["kind"] == "tests" and not c.get("fails") and not c.get("fixed_failing") and (
        bool(c.get("all_pass")) or c.get("passed") is not None)


def level_of(v: Any) -> str:
    v = str(v or "").lower()
    return DEFAULT_SHOW_UNCERTAIN if v in ("", "default") or v not in SHOW_UNCERTAIN else v


def shown(r: Dict[str, Any], level: str) -> bool:
    """Whether a receipt is stamped on the reply. 🧾 and 🧢 always are; 🤔 depends on `show_uncertain`:
    off (default) = never, strict = "tests pass" with zero test runs (and no check script), expected = any expected receipt with nothing
    relevant run, all = every unsure claim."""
    if r["verdict"] != NO_RECEIPT or r.get("loud"):  # loud: a suite-change 🤔 that replaced a 🧾 (nocap/tamper.py)
        return True
    level = level_of(level)
    if level == "all":
        return True
    if level == "off" or r["kind"] == "unchecked":
        return False
    if level == "expected":
        return absent(r)
    return zero_test_runs(r)


def judge(claims: List[Dict[str, Any]], evidence: List[Dict[str, Any]],
          kinds: Optional[set] = None, history: Optional[List[Dict[str, Any]]] = None,
          turn: int = 0, reply: str = "") -> List[Dict[str, Any]]:
    """``history``: earlier turns of the same session (store.Ledger.history), ``turn``: this turn's number.
    Without them every claim is judged on this turn's calls only, as before. ``reply``: the whole reply, so a suite
    change the reply owns up to is never 🧢 (nocap/tamper.py)."""
    out = []
    for c in claims:
        if kinds is not None and c["kind"] not in kinds:
            continue
        if c.get("revived"):  # "tests passed in the last turn": only an earlier turn of this session can answer
            r = _earlier(c, evidence or [], history or [], turn, revived=True) if c["kind"] in CROSS_KINDS else None
            if r is None:
                continue  # nothing in an earlier turn: left alone, as before cross-turn receipts
        else:
            r = JUDGES[c["kind"]](c, evidence or [])
            if r["verdict"] == NO_RECEIPT and r.get("cite") is None:
                if history and c.get("earlier") and c["kind"] in CROSS_KINDS:
                    r = _earlier(c, evidence or [], history, turn) or r
                elif c["kind"] in ("merged", "pr_opened") and isinstance(c.get("pr"), int):
                    r = _pr_session(c, evidence or [], history or [], turn) or r
        r = tamper.apply(r, c, evidence or [], history, reply)  # suite changed before the green run (S4, S5)
        if r["verdict"] == CAP and (c["kind"] in DISABLED_CAP or c.get("ack_near")):
            r = dict(r, verdict=NO_RECEIPT, why=DISABLED_CAP.get(c["kind"]) or "a sentence nearby admits failures")
        if c["kind"] == "tests" and c.get("ack_reply") and not c.get("fails") and (
                r["verdict"] == CAP or (r["verdict"] == NO_CAP and c.get("all_pass") and not c.get("scoped"))):
            r = dict(r, verdict=NO_RECEIPT, why="the reply admits a failing test elsewhere")
        if not _keep(r):
            continue  # numbers are bonus receipts: a match earns 🧾, a miss stays silent (too many aren't claims)
        out.append(r)
    return out


# ---- cross-turn receipts -------------------------------------------------------------------------------------------
CROSS_KINDS = {"tests", "build", "ci", "pushed", "merged", "committed", "pr_opened", "deployed", "file", "sha"}
_RELEVANT = {
    "tests": lambda e: bool(e.get("test_cmd")),
    "build": lambda e: bool(e.get("build_cmd")),
    "deployed": lambda e: bool(e.get("deploy_cmd")),
    "ci": lambda e: "ci_pass" in (e.get("git") or {}),
    "pushed": lambda e: "push_ok" in (e.get("git") or {}),
    "committed": lambda e: "commit_ok" in (e.get("git") or {}),
    "pr_opened": lambda e: "pr_create_ok" in (e.get("git") or {}),
    "merged": lambda e: any(k in (e.get("git") or {}) for k in ("merge_ok", "pr_view_state", "git_merge_ok", "pr_missing")),
    "sha": lambda e: bool(e.get("head_sha") or e.get("git")),
    "file": lambda e: bool(e.get("paths_edited")),
}


def session_evidence(history: List[Dict[str, Any]], evs: List[Dict[str, Any]], turn: int) -> List[Dict[str, Any]]:
    """Earlier turns' call facts, then this turn's calls, renumbered in order (each keeps its turn and own index)."""
    out: List[Dict[str, Any]] = []
    for t in history or []:
        for e in t.get("calls") or []:
            if isinstance(e, dict):
                out.append(dict(e, _turn=int(t.get("turn") or 0), _i=e.get("i")))
    for e in evs or []:
        out.append(dict(e, _turn=turn, _i=e.get("i")))
    for k, e in enumerate(out, 1):
        e["i"] = k
        e.setdefault("tests", [])
        e.setdefault("test_cmd", False)
        e.setdefault("ok", True)
        e.setdefault("tool", "")
    return out


def _cited_ev(r: Dict[str, Any], combined: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    c = r.get("cite")
    return combined[c - 1] if isinstance(c, int) and 0 < c <= len(combined) else None


def _relabel(r: Dict[str, Any], e: Dict[str, Any], turn: int) -> Dict[str, Any]:
    """Point a receipt at the call's own turn and index (the footer says "turn N")."""
    r = dict(r, cite=e.get("_i"))
    if e.get("_turn") != turn:
        r["turn"] = e.get("_turn")
    return r


def _earlier(c, evs, history, turn, revived=False) -> Optional[Dict[str, Any]]:
    """A claim about earlier work, judged on the whole session ledger. Stale evidence still loses (the judges see
    every later edit, in any turn); 🧢 only from an earlier turn that no later call of the same kind supersedes."""
    if not history:
        return None
    combined = session_evidence(history, evs, turn)
    r = JUDGES[c["kind"]](c, combined)
    e = _cited_ev(r, combined)
    if e is None:
        return None
    if revived and e["_turn"] == turn:
        return None  # the claim is about an earlier turn; this turn's calls aren't what it means
    if r["verdict"] == CAP:
        later = [x for x in combined if x["i"] > e["i"] and _RELEVANT[c["kind"]](x)]
        if e["_turn"] == turn:
            r = dict(r, verdict=NO_RECEIPT, why="this turn disagrees, but the claim is about earlier work")
        elif later:
            r = dict(r, verdict=NO_RECEIPT, why=f"later evidence (turn {later[-1]['_turn']}) supersedes it")
        elif any(JUDGES[c["kind"]](c, session_evidence([t], [], -1))["verdict"] == NO_CAP for t in history
                 if t.get("turn") != e["_turn"]):
            r = dict(r, verdict=NO_RECEIPT, why="another earlier turn shows it; the claim may mean that one")
    return _relabel(r, e, turn)


def _pr_session(c, evs, history, turn) -> Optional[Dict[str, Any]]:
    """"Merged PR #N" / "opened PR #N" with no matching call in this turn: look for #N in any gh output this
    session. 🧢 only when gh showed #N in another state (merge) or that #N doesn't exist; no output is 🤔."""
    pr = c["pr"]
    combined = session_evidence(history, evs, turn)

    def nums(e, *keys):
        g = e.get("git") or {}
        return [n for k in keys for n in (g.get(k) or [])]

    seen = [e for e in combined if pr in nums(e, "pr_view_prs", "merged_prs", "merge_cmd_prs", "opened_prs", "pr_missing")]
    if not seen:
        return _r(c, NO_RECEIPT, why=f"no gh output this session shows #{pr}")
    # a GitHub tool other than gh (an MCP server) may have done it: it can prove nothing here, and veto a 🧢
    other_tool = any(re.search(r"(?i)pull|merge|github", str(e.get("tool") or "")) and not e.get("cmd") for e in combined)
    last = seen[-1]
    g = last.get("git") or {}
    if c["kind"] == "merged":
        good = [e for e in seen if pr in nums(e, "merged_prs")]
        if good and good[-1] is last:
            return _relabel(_r(c, NO_CAP, good[-1], quote=g.get("merge_line") or "state MERGED"), last, turn)
        if pr in nums(last, "pr_missing") and not other_tool:
            return _relabel(_r(c, CAP, last, why=f"no pull request #{pr}", quote=f"no pull request #{pr} found"),
                            last, turn)
        if g.get("pr_view_state") in ("OPEN", "CLOSED") and pr in nums(last, "pr_view_prs") and not other_tool \
                and not last.get("chained"):
            return _relabel(_r(c, CAP, last, quote=f"#{pr} state {g['pr_view_state']}"), last, turn)
        return _relabel(_r(c, NO_RECEIPT, last, why=f"gh output for #{pr} was not conclusive"), last, turn)
    made = [e for e in seen if pr in nums(e, "opened_prs")]
    if made:
        return _relabel(_r(c, NO_CAP, made[-1], quote=f"/pull/{pr}"), made[-1], turn)
    if pr in nums(last, "pr_missing") and not other_tool:
        return _relabel(_r(c, CAP, last, why=f"no pull request #{pr}", quote=f"no pull request #{pr} found"), last, turn)
    return _relabel(_r(c, NO_RECEIPT, last, why=f"gh shows #{pr}, but not that it was opened here"), last, turn)
