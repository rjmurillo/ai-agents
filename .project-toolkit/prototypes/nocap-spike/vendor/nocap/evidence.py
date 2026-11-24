"""Turn one tool call into an evidence record: the facts a reply's claims can be checked against.

Stdlib only. Raw output is scanned here and never stored; only the extracted
facts leave this module. File-scoped test runs may inventory local test filenames (bounded, read-only).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shlex
import time
from typing import Any, Dict, List, Optional

# Scan window per tool output. Test summaries sit at the end of a run and commands, push lines and errors near the
# start, so only the first HEAD and last TAIL characters are parsed in full. From the middle, only short lines that
# look like a summary or a failure (MID_KEY_RE, at most MID_LINES lines / MID_BYTES) are kept, in order, so a failing
# crate in the middle of a long cargo run still counts. Every regex then runs on at most ~56 KB, and the parsers
# stay under 50 ms per output (tests/test_redos.py). A longer output that exited non-zero never earns a 🧾 (a failure
# may sit in the part that was skipped). Raw output is never stored either way.
HEAD = 8_000
TAIL = 32_000
MID_LINES = 200  # per budget: failure lines and other summary lines each get MID_LINES / MID_BYTES
MID_BYTES = 8_000
MAX_LINE = 1_000  # a summary line is short; longer lines (progress bars, minified blobs) are not parsed for counts
MAX_CMD = 16_000  # commands are parsed up to this length; an unterminated heredoc in a cut command runs to the end
MAX_SEGS = 200  # shell segments (split on ; && || | and newlines) looked at per command
MAX_SEG = 2_000  # characters of one segment that get tokenised
MAX_NUMBERS = 2000
MAX_ITEMS = 200

TEST_CMD_RE = re.compile(
    r"\b(pytest|py\.test|jest|vitest|mocha|ava|go\s+(?:-C\s+\S+\s+)?test|ginkgo|gotestsum|cargo\s+(?:\+\S+\s+)?(?:test|nextest)|"
    r"(?:npm|pnpm|yarn|bun)(?:\s+(?:-[\w-]+(?:=\S+)?|(?:workspace|--prefix|--filter|--dir|--cwd|-C|-w|--workspace)\s+"
    r"(?!test\b)[^\s-]\S*))*\s+(?:run\s+)?(?:test[\w:-]*|t)(?=\s|$)|"
    r"bun\s+test|deno\s+test|make\s+(?:-C\s+\S+\s+)?(?:test|check)\w*|tox|nox|unittest|nose2|"
    r"node\s+(?:--\S+\s+)*--test|tsx\s+--test|gleam\s+test|(?:just|task|rake|hatch)\s+(?:test|spec)\w*|"
    r"manage\.py\s+test|runtests|pest|(?:dart|flutter|stack|cabal|lein)\s+test|zig\s+build\s+test|bats|"
    r"(?:turbo|nx)\s+(?:run(?:-many)?\s+)?(?:\S+:)?test|"
    r"rspec|phpunit|xcodebuild\b(?:(?!xcodebuild\b).)*\btest|swift\s+test|(?:\./)?gradlew?\b(?:(?!gradlew?\b).)*\b(?:test|check)\w*|"
    r"(?:\./)?mvnw?\b(?:(?!mvnw?\b).)*\b(?:test|verify|install)|dotnet\s+test|ctest|meson\s+test|bazel\s+test|sbt\b(?:(?!sbt\b).)*\btest|"
    r"mix\s+test|run_tests|test\.sh|playwright\s+test|karma)\b", re.I)
NOT_RUNNER_RE = re.compile(r"^(?:echo|printf|cat|grep|rg|egrep|tail|head|sed|awk|less|more|tee|jq|wc|sort|uniq|cut|ls|"
                           r"find|git\s+(?:log|show|diff|grep)|python3?\s+-c\s+['\"]print)\b", re.I)

NOT_A_RUN_RE = re.compile(  # installing, asking for a version, or only collecting tests is not running them
    r"^(?:(?:npm|pnpm|yarn|bun)\s+(?:i|install|add|remove|uninstall|ci|update|up|upgrade|link|dlx\s+\S+\s+add)\b|"
    r"(?:pip3?|uv\s+pip|pipx|poetry|pdm|uv)\s+(?:install|add|sync|lock)\b|cargo\s+(?:install|add)\b|"
    r"go\s+(?:get|install|mod)\b|(?:brew|apt(?:-get)?|apk|yum|dnf|gem|conda)\s+|which\s|command\s+-v\s|type\s)|"
    r"\s--version\b|\s-V\b|\s--help\b|\s-h\b|--collect-only\b|\s--co\b|--listTests\b|\s-list\b|--list\b", re.I)


_SH_C_RE = re.compile(r"(?:/bin/)?(?:ba|z)?sh\s+-l?c\s+(['\"])")
_HEREDOC_RE = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1[^\n]*\n")
MAX_HEREDOCS = 20


def _unwrap_sh(s: str) -> str:
    """`bash -c '<inner>'` → `<inner>` (up to the last matching quote), for the first few wrappers."""
    for _ in range(3):
        m = _SH_C_RE.search(s)
        if not m:
            break
        j = s.rfind(m.group(1))
        if j < m.end():
            break
        s = s[:m.start()] + s[m.end():j] + s[j + 1:]
    return s


def strip_heredocs(s: str, cut: bool = False) -> str:
    """Blank out heredoc bodies (`<<EOF ... EOF`): file contents written by `cat > f <<EOF` are not commands.
    Linear: a terminator is searched once per opener, and at most MAX_HEREDOCS openers are read. When the command
    was cut at MAX_CMD (`cut`), an unterminated heredoc runs to the end, as it would in the shell."""
    out, pos, n = [], 0, 0
    for m in _HEREDOC_RE.finditer(s):
        if m.start() < pos:
            continue
        n += 1
        if n > MAX_HEREDOCS:
            break
        end = re.compile(r"\n[ \t]*" + re.escape(m.group(2)) + r"[ \t]*(?=\n|$)").search(s, m.end() - 1)
        if not end:
            if cut:
                out.append(s[pos:m.start()] + " ")
                return "".join(out)
            continue
        out.append(s[pos:m.start()] + " ")
        pos = end.end()
    out.append(s[pos:])
    return "".join(out)


def runner_segment(cmd: str, cut: bool = False) -> str:
    """The test-runner command inside a shell line, or "". Text inside echo/cat/grep never counts."""
    cmd = cmd or ""
    inner = strip_heredocs(_unwrap_sh(cmd[:MAX_CMD]), cut=cut or len(cmd) > MAX_CMD)
    for seg in re.split(r"&&|\|\||;|\||\n", inner)[:MAX_SEGS]:
        seg = re.sub(r"^\s*(?:[A-Z_][A-Z0-9_]*=\S*\s+)*", "", seg[:MAX_SEG])
        seg = re.sub(r"^(?:time|timeout\s+\S+|env|uv\s+run(?:\s+--\S+)*|poetry\s+run|pipenv\s+run|npx|bunx|"
                     r"pnpm\s+exec|(?:\S*/)?python3?(?:\.\d+)?\s+-m|bundle\s+exec|nice)\s+", "", seg.strip())
        if not seg or NOT_RUNNER_RE.match(seg) or seg.startswith("cd ") or NOT_A_RUN_RE.search(seg):
            continue
        unq = re.sub(r"'[^']*'|\"[^\"]*\"", " ", seg)
        if TEST_CMD_RE.search(unq):
            return seg.strip()
    return ""
DEPLOY_CMD_RE = re.compile(
    r"(?<![\w./-])(vercel(?:@[\w.]+)?\s+(?:deploy|--prod|--yes)|netlify\s+deploy|fly(?:ctl)?\s+deploy|wrangler\s+(?:deploy|publish|pages)|firebase\s+deploy|"
    r"gcloud\b(?:(?!gcloud\b).)*\bdeploy|kubectl\s+(?:apply|rollout)|helm\s+(?:upgrade|install)|railway\s+up|heroku\b|"
    r"eb\s+deploy|serverless\s+deploy|sls\s+deploy|terraform\s+apply|gh-pages|surge\b|"
    r"(?:npm|pnpm|yarn)\s+publish|cargo\s+publish|twine\s+upload|gh\s+release\s+create|docker\s+push|"
    r"(?:npm|pnpm|yarn)\s+run\s+deploy|(?:^|[;&|]\s*|\s)(?:\./|bash\s+|sh\s+)?(?:scripts/)?deploy(?:\.sh)?(?=\s|$))\b", re.I)
BUILD_CMD_RE = re.compile(
    r"\b((?:npm|pnpm|yarn|bun)\s+run\s+build|(?:npm|pnpm|yarn)\s+build|make\b|cargo\s+build|go\s+build|tsc\b|"
    r"xcodebuild|swift\s+build|gradlew?\s+(?:build|assemble)|mvn\s+(?:package|install)|vite\s+build|next\s+build|"
    r"build\.sh)", re.I)
WRITE_CMD_RE = re.compile(
    r"(>>?|\btee\b|\bcp\b|\bmv\b|\btouch\b|\bmkdir\b|\bsed\s+-i|\bperl\s+-[a-z]*i|\bffmpeg\b|\s-o\s|--out(?:put)?\b|"
    r"\bgit\s+mv\b|\brm\b|\bunzip\b|\btar\b|\bwget\b|\bcurl\b(?:(?!\bcurl\b).)*\s-o\b|\binstall\b|\bln\b|\bconvert\b|\bmagick\b)")

PATH_KEYS = ("path", "file_path", "filename", "target_file", "filepath", "file", "relative_workspace_path")
EDIT_NAMES = ("write", "patch", "edit", "create", "save", "replace", "insert", "apply", "append", "delete", "rename",
              "move", "modify")
READONLY_NAME_RE = re.compile(r"^(?:read|view|list|grep|glob|find|show|get)(?:_|$)")
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:(?:Update|Add|Delete) File|Move to):\s*([^\s\\\"]+)", re.M)
DOC_PATH_RE = re.compile(r"(?i)(?:\.(?:md|txt|log|csv|out|err|jsonl|rst)|/tmp/\S*|\$TMPDIR\S*|PROGRESS\S*|/dev/null)$")
TEST_PATH_RE = re.compile(
    r"(?i)(?:^|/)(?:tests?|__tests__|specs?|testdata|test_?data|fixtures|e2e|testing)/|(?:^|/)test_[^/]*$|"
    r"_tests?\.\w+$|\.(?:test|spec|e2e)\.\w+$|_spec\.rb$|(?:^|/)src/test/|(?<=[a-z0-9])Tests?\.(?:java|kt|cs|swift|scala|php)$|"
    r"(?:^|/)conftest\.py$|(?:^|/)snapshots?/|\.snap$")
TEMP_PATH_RE = re.compile(r"(?i)^/tmp/|^/var/folders/|^\$TMPDIR|(?:^|/)(?:tmp|temp|scratch)/|(?:^|/)(?:repro|reproduce|scratch)"
                          r"[\w-]*\.\w+$|(?:^|/)(?:tmp|temp)[_-][\w.-]*$|\.(?:tmp|bak|orig|rej)$")
PY_WRITE_RE = re.compile(r"open\([^)\n]*,\s*['\"][wa]b?\+?['\"]|\.write_text\(|\.write_bytes\(|os\.replace\(|shutil\.(?:copy|move)")
STOPPED_RE = re.compile(r"(?i)(?<!!)!+[ \t]*stopping after \d+ failures?|Interrupted: \d+ errors? during collection|"
                        r"^FAIL!? -- \d+ Passed \| [1-9]|^[ \t]*bail out", re.M)
_MID_FAIL_RE = re.compile(r"(?<![\d,])[1-9][\d,]{0,12} (?:failed|failures?|errors?|failing)\b|\bFAIL(?:ED|URE)?\b|"
                          r"(?i:failures:\s*[1-9]|errors:\s*[1-9]|errors? during|stopping after|bail out|panicked)")
MID_KEY_RE = re.compile(r"(?i)passed|failed|passing|failing|failures|errors? during|test result|tests run|stopping after|"
                        r"bail out|TEST (?:FAILED|SUCCEEDED)|^(?:ok|FAIL|--- FAIL)\b", re.M)


def _shell_file_args(cmd: str) -> List[str]:
    """Files a shell line writes by name: cp/mv/ln/install destinations, touch/mkdir/rm/git rm args, -o/--output."""
    out: List[str] = []
    for seg in re.split(r"&&|\|\||;|\||\n", cmd or "")[:MAX_SEGS]:
        seg = seg[:MAX_SEG]
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        while toks and (re.fullmatch(r"[A-Z_][A-Z0-9_]*=\S*", toks[0]) or toks[0] in ("sudo", "command", "env")):
            toks = toks[1:]
        if toks[:2] in (["git", "mv"], ["git", "rm"]):
            toks = [toks[0] + "-" + toks[1]] + toks[2:]
        if not toks:
            continue
        args = [t for t in toks[1:] if not t.startswith("-")]
        if toks[0] in ("cp", "mv", "ln", "install", "git-mv", "rsync") and len(args) >= 2:
            out.append(args[-1])
            if toks[0] in ("mv", "git-mv"):
                out += args[:-1]  # a move also removes the source path
        elif toks[0] in ("touch", "mkdir", "rm", "rmdir", "unlink", "git-rm", "truncate"):
            out += args
        for k, t in enumerate(toks[:-1]):
            if t in ("-o", "--output", "--out", "--outfile", "-O"):
                out.append(toks[k + 1])
        out += [t.split("=", 1)[1] for t in toks if re.match(r"--(?:output|out|outfile)=\S", t)]
    return [p for p in out if p and not p.startswith("$") and p not in ("/dev/null", "-")]


FAIL_TEXT_RE = re.compile(r"(?i)\bFAIL(?:ED|URES?|ING)?\b|\berrors?\b|Traceback|panic:|exit status [1-9]|✗|✘|×|"
                          r"AssertionError|Exception\b|not found|No such file|cannot |could not|unable to|segmentation|"
                          r"\bkilled\b|timed? ?out")


def path_class(p: str) -> str:
    """"test", "doc", "temp" or "code": only edits to code make an earlier test run stale."""
    p = (p or "").strip("`'\"")
    if DOC_PATH_RE.search(p):
        return "doc"
    if TEMP_PATH_RE.search(p):
        return "temp"
    if TEST_PATH_RE.search(p):
        return "test"
    return "code"


_COMMENT_LINE_RE = re.compile(r"^\s*(?:#(?!\[|!|(?:include|define|if|ifdef|ifndef|endif|else|elif|pragma|import|undef|"
                              r"error|line|region|endregion)\b)|//|/\*|\*/|\*(?!\*)|--\s|<!--|;;|\"\"\"\s*$)")


_TRAILING_COMMENT_RE = re.compile(r"(?<=\s)(?:#|//)\s")  # linear: one fixed-width lookbehind, no \s+ to rescan


def _code_lines(s: str) -> List[str]:
    out = []
    for ln in s.splitlines():
        if _COMMENT_LINE_RE.match(ln):
            continue
        m = _TRAILING_COMMENT_RE.search(ln)  # trailing comment (needs a space before and after)
        ln = (ln[:m.start()] if m else ln).strip()
        if ln:
            out.append(ln)
    return out


SKIP_MARK_RE = re.compile(r"@pytest\.mark\.(?:skip|xfail)|@(?:unittest\.)?skip\w*|\bpytest\.skip\(|\bt\.Skip\w*\(|"
                          r"#\[ignore\]|\b(?:it|test|describe)\.(?:skip|todo)\(|\bx(?:it|describe)\(|@Disabled\b|@Ignore\b")
# The agent's own checks: a script it runs (python repro.py, node check.mjs, ./smoke.sh), `python -c ...`, an import
# or collection check. Not a test run, but test-like evidence: "tests pass" next to one is not stamped 🤔.
CHECK_CMD_RE = re.compile(
    r"(?:^|[;&|(]\s*|\s)(?:[\w.~/-]*/)?(?:python[\d.]*|node|deno\s+run|bun|tsx|ts-node|ruby|php|perl|bash|sh|zsh)"
    r"(?:\s+-[\w-]+)*\s+(?:-c\s|-\s*<<|[\w./~-]+\.(?:py|m?[jt]s|rb|php|pl|sh)\b)|"
    r"(?:^|[;&|(]\s*|\s)\./[\w./-]+\.(?:py|sh|m?js)\b|--collect-only\b|\s--co\b|\bgo\s+(?:run|vet)\b|\bcargo\s+(?:run|check)\b")


def _adds_skip(args: Dict[str, Any]) -> bool:
    """An edit that adds a skip/xfail marker (a failing test quietly switched off)."""
    for old_k, new_k in (("old_string", "new_string"), ("old_str", "new_str"), ("old_text", "new_text"),
                         ("search", "replace")):
        old, new = args.get(old_k), args.get(new_k)
        if isinstance(new, str):
            return len(SKIP_MARK_RE.findall(new)) > len(SKIP_MARK_RE.findall(old if isinstance(old, str) else ""))
    for k in ("content", "file_text", "text", "patch", "diff", "input"):
        v = args.get(k)
        if isinstance(v, str) and k in ("patch", "diff", "input"):
            return bool(re.search(r"(?m)^\+.*(?:" + SKIP_MARK_RE.pattern + ")", v[:MAX_CMD]))
    return False


def _comment_only(args: Dict[str, Any]) -> bool:
    """A patch whose old and new text differ only in comments and blank lines (needs both texts in the args)."""
    for old_k, new_k in (("old_string", "new_string"), ("old_str", "new_str"), ("old_text", "new_text"),
                         ("search", "replace")):
        old, new = args.get(old_k), args.get(new_k)
        if isinstance(old, str) and isinstance(new, str) and old != new:
            return _code_lines(old) == _code_lines(new)
    return False


_VALUE_FLAGS = {"-n", "-p", "--tb", "-c", "-o", "-W", "--rootdir", "--timeout", "--maxfail", "--cov", "--cov-report",
                "--junitxml", "-r", "--durations", "--color", "--log-level", "--numprocesses", "--dist", "--basetemp",
                "--capture", "-timeout", "-count", "-tags", "-parallel", "-coverprofile", "-covermode", "-cpu",
                "-j", "--jobs", "--features", "-F", "--target", "--manifest-path", "--profile", "--config",
                "--reporter", "--maxWorkers", "--testTimeout", "--environment", "--pool", "--test-threads",
                "--import-mode", "-gcflags", "-ldflags", "-exec", "--max-workers", "--shard", "--workers"}
_SUBSET_FLAG_RE = re.compile(r"[\s'\"=]-k\s|--testPathIgnorePatterns\b|\bpytest\b(?:(?!\bpytest\b).)*\s-m\s|::|\s--lf\b|\s--last-failed\b|\s--deselect\b|\s--ignore\b|--testNamePattern|"
                             r"\s-t\s|--testPathPattern|\s-run[\s=]|\s['\"]?-D(?:it\.)?test=|\s-pl\s|\s--projects?\s|"
                             r"\s--tests?\s|\s--tests?=|\s--package\s|\bcargo\b(?:(?!\bcargo\b).)*\s(?:-p|--package|--test|"
                             r"--lib|--bin|--doc|--example)\b|--grep\b|\s-g\s|--filter\b|--only\b|:\w[\w-]*:test\b")
_FULL_ARGS = {".", "./", "./...", "...", "tests", "tests/", "test", "test/", "spec", "spec/", "./tests", "./test"}


_JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")
# where a run's project starts: the nearest of these at or above the run's directory (stat only)
_ROOT_MARKERS = (".git", "pyproject.toml", "setup.cfg", "setup.py", "pytest.ini", "tox.ini", "package.json")
# configs that can change which files the runner collects; a pattern override there makes the inventory unknowable
_COLLECT_CONFIGS = {"pytest.ini": "python_files", "tox.ini": "python_files", "setup.cfg": "python_files",
                    "pyproject.toml": "python_files", "package.json": "testMatch|testRegex"}
_COLLECT_JS_CONFIGS = ("jest.config", "vitest.config", "vite.config", "vitest.workspace")


def _project_dirs(run_dir: str) -> List[str]:
    """run_dir and up to four parents, up to the project root: the `.git` checkout if there is one in reach
    (a monorepo's packages are not separate suites), else the nearest marker. [] when no marker is in reach."""
    chain, cur = [], run_dir
    for _ in range(5):
        chain.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    git = next((i for i, d in enumerate(chain) if os.path.lexists(os.path.join(d, ".git"))), None)
    near = next((i for i, d in enumerate(chain) if any(os.path.lexists(os.path.join(d, m)) for m in _ROOT_MARKERS)),
                None)
    top = git if git is not None else near
    return [] if top is None else chain[:top + 1]


def _custom_collection(root: str) -> bool:
    """True when a runner config at root may override the default test-file patterns (or can't be checked).
    Reads at most 64 KB of each config file that exists; nothing is stored."""
    names = list(_COLLECT_CONFIGS.items()) + [(f"{b}{e}", r"testMatch|testRegex|\binclude\b|projects")
                                               for b in _COLLECT_JS_CONFIGS for e in _JS_EXT + (".json",)]
    for name, keys in names:
        path = os.path.join(root, name)
        if not os.path.lexists(path):
            continue
        if os.path.islink(path) or not os.path.isfile(path):
            return True
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            if re.search(keys, fh.read(65536)):
                return True
    return False


def _test_file(path: str) -> bool:
    """Files a default pytest or jest/vitest run would collect. Wider than the brief's three shapes on purpose:
    any of these that the run didn't target means the run was not the full suite (precision first)."""
    name = os.path.basename(path)
    if fnmatch.fnmatchcase(name, "test_*.py") or fnmatch.fnmatchcase(name, "*_test.py"):
        return True
    stem, ext = os.path.splitext(name)
    return ext in _JS_EXT and (stem.endswith((".test", ".spec")) or "__tests__" in path.replace("\\", "/").split("/"))


def _full_file_run(seg: str, cmd: str, workdir: str) -> List[str]:
    """Literal file targets cover a bounded, read-only inventory; uncertainty keeps subset=True.

    Never follow symlinks; the only contents read are runner configs, for a test-pattern override. Limits include
    all visited entries, not just tests.
    Only simple runner invocations are eligible: shell expansion and unknown options are ambiguous.
    """
    if len(seg) >= MAX_SEG or _SUBSET_FLAG_RE.search(" " + cmd):
        return []
    try:
        tokens = shlex.split(seg)
        # not mocha: its default spec is every file under test/, whatever the name, so an inventory can't bound it
        start = next((i + 1 for i, t in enumerate(tokens) if t in ("pytest", "py.test", "jest", "vitest")), None)
        if start is None:
            return []
        targets = []
        for t in tokens[start:]:
            if t in ("-q", "-v", "-vv", "--quiet", "--verbose", "run", "--"):
                continue
            if not _test_file(t) or any(c in t for c in "*?[]$`|;&<>\n") or t.startswith("-"):
                return []
            targets.append(t)
        if not targets:
            return []
        if not workdir or not os.path.isabs(workdir):
            return []  # a relative or missing root would resolve against the plugin process's cwd
        run_dir = os.path.abspath(workdir)
        # inventory the whole project, not just the directory the run happened to start in (`cd tests && pytest
        # test_x.py` must still see ../test_root.py). No marker: only a run outside a tests/ directory qualifies.
        dirs = _project_dirs(run_dir)
        if not dirs:
            if os.path.basename(run_dir) in ("tests", "test", "__tests__", "spec", "specs"):
                return []
            dirs = [run_dir]
        root = dirs[-1]
        if any(_custom_collection(d) for d in dirs):  # a config anywhere from the run's dir up to the root
            return []
        selected = {os.path.normpath(os.path.relpath(os.path.abspath(os.path.join(run_dir, t)), root))
                    for t in targets}
        pending, found, count = [(root, 0)], set(), 0
        while pending:
            directory, depth = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > 2000:
                        return []
                    if entry.name in (".git", ".venv", "venv", "node_modules", "__pycache__"):
                        continue
                    if entry.is_symlink():
                        return []
                    if entry.is_dir(follow_symlinks=False):
                        if depth >= 4:
                            return []
                        pending.append((entry.path, depth + 1))
                    elif entry.is_file(follow_symlinks=False) and _test_file(os.path.relpath(entry.path, root)):
                        found.add(os.path.relpath(entry.path, root))
        return sorted(selected) if found and found == selected else []
    except (OSError, ValueError):
        return []


def _subset(seg: str, cmd: str) -> bool:
    """A run that can't prove "all tests pass": a -k/-m filter, a node id, a single file, a package or name filter."""
    if _SUBSET_FLAG_RE.search(" " + cmd) or re.search(r"\btest_\w+\.py\b|\w+_test\.(?:py|go)\b|\.(?:test|spec)\.[jt]sx?\b",
                                                     cmd):
        return True
    s = re.sub(r"\s[12]?>&?\s*\S+", " ", seg[:MAX_SEG])  # redirections
    try:
        toks = shlex.split(s)
    except ValueError:
        toks = s.split()
    low = [t.lower() for t in toks]
    start = None
    for k, t in enumerate(low):
        if re.fullmatch(r"(?:py\.test|pytest|jest|vitest|mocha|ava|deno|bun|ginkgo|rspec|phpunit|karma|tap)", t) or \
                (t == "test" and k and low[k - 1] in ("go", "cargo", "swift", "dotnet", "mix", "deno", "bun", "gleam",
                                                      "zig", "dart", "flutter", "stack", "cabal", "lein")):
            start = k + 1
            break
        if t in ("npm", "pnpm", "yarn", "bun") and "--" in toks[k:]:
            start = toks.index("--", k) + 1
            break
        if t in ("npm", "pnpm", "yarn") and k + 1 < len(low) and re.fullmatch(r"(?:run\s+)?test[:_-]\w[\w:-]*",
                                                                          " ".join(low[k + 1:k + 3]).split(" -")[0].strip()):
            return True  # a named sub-suite (test:unit, test-e2e)
    if start is None:
        return False
    rest, skip = toks[start:], False
    if rest[:1] and rest[0].lower() in ("run", "nextest", "test", "--"):
        rest = rest[1:]
    if rest[:1] and rest[0].lower() == "run":
        rest = rest[1:]
    for t in rest:
        if skip:
            skip = False
            continue
        if t == "--":
            continue
        if t.startswith("-"):
            skip = t in _VALUE_FLAGS
            continue
        if t.isdigit() or t in _FULL_ARGS or t.rstrip("/") in _FULL_ARGS:
            continue
        return True
    return False


# Secret masking (applied to every string before it is stored, and to quotes). Each rule is linear: a name or
# token is matched from its first character only (lookbehinds), so a long run can't be rescanned from every offset.
_SECRET_NAME_RE = re.compile(r"(?i)token|secret|passw|pwd|api[_-]?key|apikey|auth|bearer|credential|private[_-]?key|"
                             r"(?:^|[_-])key(?:s|[_-]|$)|^key$|dsn$|cookie|session[_-]?id")
# the lookahead skips names with no secret word before the Python callback runs (a long "a:b a:b ..." run was ~1 µs
# per pair in _assign); _assign still checks the exact rule (_SECRET_NAME_RE)
_ASSIGN_RE = re.compile(r"(?<![\w.-])(?=[\w.-]*?(?i:token|secret|passw|pwd|key|auth|bearer|credential|dsn|cookie|session))"
                        r"([\w.-]+)(['\"]?[ \t]*(?:=|:(?!:))[ \t]*)((?:(?i:bearer|basic|token)[ \t]+)?['\"]?)([^\s'\",;}]+)")
_KEYWORD_SPACE_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(authorization|bearer|token|api[_-]?key|secret|password|passwd|pwd)"
                               r"\b([ \t]+)((?:bearer[ \t]+)?['\"]?)([^\s'\"]+)")
# Every match of _ASSIGN_RE or _KEYWORD_SPACE_RE contains one of these words, so one cheap test decides whether either
# rule can match at all (a case-insensitive regex search for them cost about 10 ms on 100 KB of Thai or CJK text).
_SECRET_WORDS = ("token", "secret", "passw", "pwd", "key", "auth", "bearer", "credential", "dsn", "cookie", "session")
# `re` also treats these as i, s and k when it ignores case, and str.lower() does not map them: never skip on them.
_CASE_ODDITIES = ("\u0130", "\u0131", "\u017f", "\u212a")


def _has_secret_word(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in _SECRET_WORDS) or any(c in text for c in _CASE_ODDITIES)


_USERINFO_RE = re.compile(r"(?i)(?<![a-z0-9+.-])([a-z][a-z0-9+.-]{0,30}://[^\s/:@'\"]{1,200}:)([^\s@/'\"]{1,500})@")
_AWS_SECRET_RE = re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])")
_DOTTED_TOKEN_RE = re.compile(r"(?<![\w-])[\w-]{20,200}\.[\w-]{6,200}\.[\w-]{20,500}(?![\w-])")
SECRET_RES = [
    re.compile(r"(?<![\w-])(?:sk|pk|rk|ghp|gho|ghs|ghu|ghr|github_pat|glpat|xox[abpr]|AKIA|ASIA|npm|hf|AIza)[-_A-Za-z0-9]{12,}"),
    re.compile(r"(?<![\w+-])(?![0-9a-f]{32,}\b)(?=[A-Za-z0-9_+-]*\d)(?=[A-Za-z0-9_+-]*[A-Za-z])[A-Za-z0-9_+-]{32,}={0,2}"),
]
# Runs first: a key behind a secret-looking name (`private_key: -----BEGIN ...`) would otherwise lose only its
# `-----BEGIN` word to the KEY=value rule, and the key body would stay.
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)
REDACTED = "[redacted]"
# Passwords passed as command-line flags (S9). Each masks only its capture group, so the command stays readable.
# The curl and mysql shapes only run when that tool is named, so `docker run -u 1000:1000` and `pytest -p no:x` stay.
_CURL_RE = re.compile(r"\bcurl\b")
_CURL_USER_RE = re.compile(r"((?<![\w-])(?:-u|--user)(?:[ \t]+|=)['\"]?[^\s:'\"@/]{1,100}:)[^\s'\"]{1,300}")
_MYSQL_RE = re.compile(r"\b(?:mysql\w{0,10}|mariadb\w{0,10})\b")
_MYSQL_PW_RE = re.compile(r"((?<![\w-])-p['\"]?)[^\s'\"\[-][^\s'\"]{0,300}")
_REDIS_RE = re.compile(r"\bredis-cli\b")
_REDIS_PW_RE = re.compile(r"((?<![\w-])-a[ \t]+)[^\s'\"\[][^\s'\"]{0,300}")
_FLAG_PW_RES = [
    re.compile(r"(\bsshpass[ \t]+(?:-[a-zA-Z][ \t]+)?-p[ \t]*['\"]?)[^\s'\"\[][^\s'\"]{0,300}"),
    re.compile(r"((?<![\w-])--pass(?:word|wd|phrase)?(?:[ \t]+|=))[^\s'\"\[][^\s'\"]{0,300}"),
]
_MASK = "\\g<1>" + REDACTED  # group 1 is everything before the secret: a template, no Python callback per match


def _cli_passwords(text: str) -> str:
    # each rule needs its literal word, so a plain substring test (no regex pass) skips the rules a text can't match
    if "curl" in text and _CURL_RE.search(text):
        text = _CURL_USER_RE.sub(_MASK, text)
    if ("mysql" in text or "mariadb" in text) and _MYSQL_RE.search(text):
        text = _MYSQL_PW_RE.sub(_MASK, text)
    if "redis-cli" in text and _REDIS_RE.search(text):
        text = _REDIS_PW_RE.sub(_MASK, text)
    if "sshpass" in text:
        text = _FLAG_PW_RES[0].sub(_MASK, text)
    if "--pass" in text:
        text = _FLAG_PW_RES[1].sub(_MASK, text)
    return text


def home_tilde(s: str) -> str:
    """The user's home directory as `~` (S9): stored and printed commands and working dirs never name the user."""
    home = os.path.expanduser("~").rstrip("/")
    if not s or not home or home == "~" or len(home) < 2 or home not in s:
        return s
    return re.sub(re.escape(home) + r"(?=/|$|[\s'\";&|)])", "~", s)


def _assign(m: "re.Match") -> str:
    name = m.group(1)
    if not _SECRET_NAME_RE.search(name) or m.group(4).lower() in ("[redacted]", "***"):
        return m.group(0)
    return name + m.group(2) + m.group(3) + REDACTED


def _aws_secret(m: "re.Match") -> str:
    v = m.group(0)
    mixed = any(c.isupper() for c in v) and any(c.islower() for c in v) and any(c.isdigit() for c in v)
    return REDACTED if mixed and ("/" in v or "+" in v) else v


URL_RE = re.compile(r"https?://[^\s'\"<>()\[\]{}`]+")
SHA_RE = re.compile(r"\b[0-9a-f]{7,64}\b")
NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\d.]\d|\d)")
HTTP_RES = [
    re.compile(r"\bHTTP/[\d.]+\s+(\d{3})\b"),
    re.compile(r"(?i)[\"']?(?:status(?:_?code)?|http_code)[\"']?\s*[:=]\s*(\d{3})\b"),
]

_TOKEN = r"(?<![\d,])(\d{1,3}(?:,\d{3})+|\d+)\s+(passed|failed|errors?|error|skipped|xfailed|xpassed|deselected|failures?|todo|total|passing|failing|pending)"


def _digest(args: Any) -> str:
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        blob = repr(args)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]


def redact(text: str) -> str:
    """Mask secrets: KEY=value pairs whose name says secret (DB_PASSWORD=, GITHUB_TOKEN=, client_secret:, X-Api-Key:),
    `token <v>` / `--password <v>`, URL userinfo passwords (https://u:pw@, postgres://u:pw@), provider token
    prefixes, long mixed tokens, AWS secret keys, dotted tokens (JWT, Discord) and PEM private keys."""
    if not text:
        return text
    out = _PEM_RE.sub(REDACTED, text) if "-----BEGIN" in text else text
    if "://" in out:  # the rule needs a scheme; a substring test is far cheaper than a regex pass over 100 KB
        out = _USERINFO_RE.sub(lambda m: m.group(1) + REDACTED + "@", out)
    if _has_secret_word(out):  # both rules need one of these words; most tool output has none
        out = _ASSIGN_RE.sub(_assign, out)
        out = _KEYWORD_SPACE_RE.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + REDACTED
                                    if m.group(4) != REDACTED else m.group(0), out)
    out = _DOTTED_TOKEN_RE.sub(REDACTED, out)
    out = _AWS_SECRET_RE.sub(_aws_secret, out)
    for rx in SECRET_RES:
        out = rx.sub(REDACTED, out)
    return _cli_passwords(out)  # last: each mask lengthens the text, so the rules above scan the shorter original


def _cut(line: str, n: int = 160) -> str:
    """A stored line: masked whole first, then cut. Cutting first can remove the context a rule needs (the `@` after
    a URL password, the far end of a long token), and the kept prefix of the secret then matches nothing."""
    return redact(line)[:n]


def scan_window(text: str) -> str:
    """The part of a tool output that gets parsed: head + summary-like lines from the middle + tail (see HEAD)."""
    if len(text) <= HEAD + TAIL:
        return text
    mid = text[HEAD:len(text) - TAIL]
    keep: List[str] = []
    size = {False: 0, True: 0}  # bytes kept: other summary-like lines, failure lines (each has its own budget)
    count = {False: 0, True: 0}
    last_end = -1
    for m in MID_KEY_RE.finditer(mid):
        if m.start() < last_end:
            continue
        a = mid.rfind("\n", max(0, m.start() - 300), m.start()) + 1 or max(0, m.start() - 300)
        b = mid.find("\n", m.end(), m.end() + 300)
        b = min(len(mid), m.end() + 300) if b < 0 else b
        last_end = b
        line = mid[a:b]
        bad = bool(_MID_FAIL_RE.search(line))
        if count[bad] >= MID_LINES or size[bad] >= MID_BYTES:
            if count[not bad] >= MID_LINES or size[not bad] >= MID_BYTES:
                break
            continue
        keep.append(line)
        count[bad] += 1
        size[bad] += len(line)
    return text[:HEAD] + "\n" + "\n".join(keep) + ("\n" if keep else "") + text[len(text) - TAIL:]



ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b\n]{0,2000}\x07")
JSON_MAX = 2_000_000  # a tool result up to this size is decoded as JSON in full (json is linear); larger: head/tail


def _json_head_tail(s: str) -> Any:
    """A JSON tool result too big to decode: keep its exit code and the windowed raw text."""
    m = re.search(r'"(?:exit_code|returncode|exitCode)"\s*:\s*(-?\d{1,4})\b', s[-4000:]) or \
        re.search(r'"(?:exit_code|returncode|exitCode)"\s*:\s*(-?\d{1,4})\b', s[:4000])
    w = scan_window(s.replace("\\r", "").replace("\\t", "\t").replace("\\n", "\n").replace('\\"', '"'))
    out: Dict[str, Any] = {"output": w}
    if m:
        out["exit_code"] = int(m.group(1))
    return out


def _decode(result: Any) -> tuple:
    """(text, exit_code, error_text, parsed_dict)."""
    parsed = result
    if isinstance(result, (bytes, bytearray)):
        result = result.decode("utf-8", "replace")
    if isinstance(result, str):
        s = result.strip()
        if s[:1] in "{[":
            try:
                parsed = json.loads(s) if len(s) <= JSON_MAX else _json_head_tail(s)
            except Exception:
                parsed = result
    if isinstance(parsed, dict):
        parts = []
        for key in ("output", "stdout", "stderr", "content", "result", "text", "message", "error", "data", "body"):
            val = parsed.get(key)
            if isinstance(val, str):
                parts.append(val)
            elif isinstance(val, (dict, list)):
                parts.append(json.dumps(val, default=str)[:JSON_MAX])
        if not parts:
            parts.append(json.dumps(parsed, default=str)[:JSON_MAX])
        exit_code = None
        for key in ("exit_code", "returncode", "exitCode", "code"):
            val = parsed.get(key)
            if isinstance(val, int) and not isinstance(val, bool):
                exit_code = val
                break
        err = parsed.get("error")
        return "\n".join(parts), exit_code, (str(err) if err else ""), parsed
    if isinstance(parsed, list):
        return json.dumps(parsed, default=str)[:JSON_MAX], None, "", None
    return ("" if result is None else str(result)), None, "", None


def _sum_tokens(line: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for n, word in re.findall(_TOKEN, line, re.I):
        n = n.replace(",", "")
        w = word.lower()
        w = {"passing": "passed", "failing": "failed", "failure": "failed", "failures": "failed",
             "error": "errors", "pending": "skipped"}.get(w, w)
        counts[w] = counts.get(w, 0) + int(n)
    return counts


_CAND_LINE_RE = re.compile(r"(?m)^(?:[^\d\n]*\d[^\n]*|[ \t]*--- (?:FAIL|PASS):[^\n]*|(?:ok|FAIL)[ \t][^\n]*)$")


_LINE_KEY_RE = re.compile(r"pass|fail|error|test|ok|pending|executed|assert|example|propert")


def parse_tests(text: str) -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []

    def add(runner, passed=0, failed=0, errors=0, skipped=0, line=""):
        runs.append({"runner": runner, "passed": passed, "failed": failed, "errors": errors,
                     "skipped": skipped, "line": _cut(line.strip())})

    # only lines with a digit, or Go's per-test / per-package lines, can carry a summary
    lines = [m.group(0) for m in _CAND_LINE_RE.finditer(text.replace("\r\n", "\n").replace("\r", "\n"))]
    surefire: List[tuple] = []
    go_fail = go_pass = go_ok = go_FAIL = 0
    mocha: Dict[str, int] = {}
    tap: Dict[str, int] = {}
    bun: Dict[str, int] = {}
    for raw in lines:
        if not raw or len(raw) > MAX_LINE:
            continue
        line = raw.strip().strip("=").strip()
        if not line:
            continue
        low = line.lower()
        if not _LINE_KEY_RE.search(low):
            continue  # every summary shape below needs one of these words
        m = re.search(r"(?i)^(?:passed|failed)!\s+-\s+failed:\s*(\d+),\s*passed:\s*(\d+)(?:,\s*skipped:\s*(\d+))?", line)
        if m:  # dotnet test
            add("dotnet", int(m.group(2)), int(m.group(1)), skipped=int(m.group(3) or 0), line=line)
            continue
        m = re.search(r"(?i)(?<!\d)\d+% tests passed,\s*(\d+) tests? failed out of (\d+)", line)
        if m:  # ctest
            f, total = int(m.group(1)), int(m.group(2))
            add("ctest", total - f, f, line=line)
            continue
        m = re.search(r"(?i)(?<!\d)\b(\d+) tests? run:\s*(\d+) passed(?:\s*\([^)]*\))?(?:,\s*(\d+) failed)?", line)
        if m:  # cargo nextest
            add("nextest", int(m.group(2)), int(m.group(3) or 0), line=line)
            continue
        m = re.match(r"(?i)^(?:ok|failed|FAILED)\s*\|\s*(\d+) passed(?: \(\d+ steps?\))?\s*\|\s*(\d+) failed", line)
        if m:  # deno
            add("deno", int(m.group(1)), int(m.group(2)), line=line)
            continue
        m = re.match(r"(?i)^(\d+) (?:examples?|tests?|properties),\s*(\d+) failures?(?:,\s*(\d+) (?:pending|skipped|excluded))?", line)
        if m:  # rspec, ExUnit (mix test)
            total, f = int(m.group(1)), int(m.group(2))
            add("rspec", total - f, f, skipped=int(m.group(3) or 0), line=line)
            continue
        m = re.match(r"(?i)^(\d+) passed,\s*(?:no failures|(\d+) failures?)", line)
        if m:  # gleam
            add("gleam", int(m.group(1)), int(m.group(2) or 0), line=line)
            continue
        m = re.match(r"^OK \((\d+) tests?, \d+ assertions?\)", line)
        if m:  # phpunit, green
            add("phpunit", int(m.group(1)), 0, line=line)
            continue
        m = re.match(r"(?i)^Tests:\s*(\d+),\s*Assertions:\s*\d+(?:,\s*Errors:\s*(\d+))?(?:,\s*Failures:\s*(\d+))?", line)
        if m:  # phpunit, red
            total, e, f = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
            add("phpunit", total - e - f, f, e, line=line)
            continue
        m = re.match(r"^#\s+(pass|fail|tests)\s+(\d+)$", line)
        if m:  # node --test (TAP)
            tap[m.group(1)] = int(m.group(2))
            continue
        m = re.match(r"^(\d+) (pass|fail)$", line)
        if m:  # bun test
            bun[m.group(2)] = int(m.group(1))
            continue
        m = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)(?:,\s*Skipped:\s*(\d+))?", line)
        if m:
            total, f, e, sk = (int(x or 0) for x in m.groups())
            surefire.append((total - f - e - sk, f, e, sk, line))
            continue
        m = re.search(r"(?<!\d)(\d+) tests? completed,\s*(\d+) failed(?:,\s*(\d+) skipped)?", line)
        if m:
            total, f, sk = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            add("gradle", total - f - sk, f, skipped=sk, line=line)
            continue
        m = re.search(r"(?<!\d)(\d+) Passed \| (\d+) Failed(?: \| (\d+) Pending)?(?: \| (\d+) Skipped)?", line)
        if m:
            add("ginkgo", int(m.group(1)), int(m.group(2)), skipped=int(m.group(4) or 0), line=line)
            continue
        m = re.match(r"(?i)test result:\s*(ok|failed)\.\s*(\d+)\s+passed;\s*(\d+)\s+failed", line)
        if m:
            add("cargo", int(m.group(2)), int(m.group(3)), line=line)
            continue
        if re.match(r"(?i)^test (?:files|suites):?\s", line):
            continue  # file/suite tallies, not test counts
        m = re.match(r"(?i)^tests?:?\s+(.*)$", line)
        if m and re.search(r"(?<!\d)\d+\s+(passed|failed)", m.group(1), re.I):
            c = _sum_tokens(m.group(1))
            add("jest", c.get("passed", 0), c.get("failed", 0), c.get("errors", 0), c.get("skipped", 0), line)
            continue
        m = re.search(r"(?i)executed\s+(\d+)\s+tests?,\s+with\s+(\d+)\s+failures?", line)
        if m:
            total, failed = int(m.group(1)), int(m.group(2))
            add("xctest", total - failed, failed, line=line)
            continue
        if re.search(r"(?<!\d)\d+\s+(passed|failed|errors?)\b", low) and (
                re.search(r"\bin\s+(?<![\d.])[\d.]+\s*s(ec(onds)?)?\b", low) or raw.lstrip().startswith("=")
                or re.fullmatch(r"[\d\w ,]+", low)):
            c = _sum_tokens(line)
            if "passed" in c or "failed" in c or "errors" in c:
                add("pytest", c.get("passed", 0), c.get("failed", 0), c.get("errors", 0), c.get("skipped", 0), line)
                continue
        m = re.match(r"(?i)^(\d+)\s+(passing|failing|pending)\b", line)
        if m:
            key = {"passing": "passed", "failing": "failed", "pending": "skipped"}[m.group(2).lower()]
            mocha[key] = mocha.get(key, 0) + int(m.group(1))
            mocha.setdefault("_line", 0)
            continue
        if line.startswith("--- FAIL:"):
            go_fail += 1
        elif line.startswith("--- PASS:"):
            go_pass += 1
        elif re.match(r"^ok\s+\S+", raw):
            go_ok += 1
        elif re.match(r"^FAIL\s+\S+", raw):
            go_FAIL += 1
    for ran in list(re.finditer(r"(?m)^Ran (\d+) tests? in [\d.]+s\s*\n\s*\n?(OK\b[^\n]*|FAILED \(([^)]*)\))", text))[-3:]:
        total = int(ran.group(1))
        failed = errors = 0
        if ran.group(3) is not None:
            f = re.search(r"failures=(\d+)", ran.group(3))
            e = re.search(r"errors=(\d+)", ran.group(3))
            failed = int(f.group(1)) if f else 0
            errors = int(e.group(1)) if e else 0
        add("unittest", total - failed - errors, failed, errors, line=_cut(ran.group(0).replace("\n", " ")))
    if tap and ("pass" in tap or "fail" in tap):
        add("node", tap.get("pass", 0), tap.get("fail", 0), line=f"# pass {tap.get('pass', 0)}, # fail {tap.get('fail', 0)}")
    if bun and "pass" in bun:
        add("bun", bun.get("pass", 0), bun.get("fail", 0), line=f"{bun.get('pass', 0)} pass, {bun.get('fail', 0)} fail")
    cargo = [r for r in runs if r["runner"] == "cargo"]
    if len(cargo) > 1:  # one "test result:" line per crate/target: the claim counts all of them
        add("cargo", sum(r["passed"] for r in cargo), sum(r["failed"] for r in cargo),
            line=f"cargo test: {sum(r['passed'] for r in cargo)} passed, {sum(r['failed'] for r in cargo)} failed "
                 f"across {len(cargo)} targets")
    if surefire:  # the last "Tests run:" line is Maven's aggregate under "Results:"
        p_, f_, e_, sk_, ln = surefire[-1]
        add("surefire", p_, f_, e_, sk_, ln)
    if mocha:
        add("mocha", mocha.get("passed", 0), mocha.get("failed", 0), skipped=mocha.get("skipped", 0),
            line=f"{mocha.get('passed', 0)} passing, {mocha.get('failed', 0)} failing")
    if (go_fail or go_pass) or ((go_ok or go_FAIL) and re.search(r"(?m)^(?:ok|FAIL)\s+\S+\s+[\d.]+s\b|\(cached\)", text)):
        add("go", go_pass or go_ok, max(go_fail, go_FAIL),
            line=f"go test: {go_pass or go_ok} ok, {max(go_fail, go_FAIL)} FAIL")
    if "** TEST FAILED **" in text and not any(r["failed"] for r in runs):
        add("xcodebuild", 0, 1, line="** TEST FAILED **")
    elif "** TEST SUCCEEDED **" in text and not runs:
        add("xcodebuild", 1, 0, line="** TEST SUCCEEDED **")
    return runs[-20:]


def _chained(cmd: str) -> bool:
    """True when the exit code may belong to another command. A leading `cd <dir> &&` doesn't count."""
    core = re.sub(r"^\s*(?:cd\s+(?:\"[^\"]*\"|'[^']*'|\S+)\s*&&\s*)+", "", cmd)
    return bool(re.search(r"&&|\|\||;|\|", core))


def _ci_status(text: str, exit_code: Optional[int]) -> Optional[Dict[str, Any]]:
    """gh pr checks / gh run list|view: read status columns or JSON conclusions, not free text."""
    fails = passes = pending = 0
    for line in text.splitlines():
        cols = [c.strip().lower() for c in line.split("\t")]
        if len(cols) >= 2 and cols[1] in ("fail", "failure", "failed", "pass", "success", "pending", "skipping",
                                          "queued", "in_progress", "cancel", "cancelled"):
            fails += cols[1] in ("fail", "failure", "failed")
            passes += cols[1] in ("pass", "success")
            pending += cols[1] in ("pending", "queued", "in_progress")
        elif re.match(r"^\s*(?:X|✗|×)\s+\S", line):
            fails += 1
        elif re.match(r"^\s*(?:✓|✔)\s+\S", line):
            passes += 1
        elif re.match(r"^completed\s+(success|failure)\b", line.strip()):
            fails += "failure" in line
            passes += "success" in line
    for c in re.findall(r'"(?:conclusion|state|c|status)"\s*:\s*"(SUCCESS|FAILURE|FAILED|ERROR|PASS|FAIL)"', text, re.I):
        fails += c.upper() in ("FAILURE", "FAILED", "ERROR", "FAIL")
        passes += c.upper() in ("SUCCESS", "PASS")
    pending += len(re.findall(r'"(?:status|state)"\s*:\s*"(?:IN_PROGRESS|QUEUED|PENDING|EXPECTED)"', text))
    if exit_code == 8:
        pending += 1
    if not fails and not passes and not pending:
        return None
    return {"ci_fail": fails > 0, "ci_pass": fails == 0 and passes > 0 and pending == 0, "ci_pending": pending > 0}


def parse_git(cmd: str, text: str, exit_code: Optional[int]) -> Dict[str, Any]:
    g: Dict[str, Any] = {}
    ok = exit_code in (0, None)
    if re.search(r"\bgit\b(?:(?!\bgit\b)[^|;&])*\bpush\b", cmd) and not re.search(
            r"\bpush\b(?:(?!\bpush\b)[^|;&])*(?:--dry-run|\s-n\b)", cmd):
        rejected = bool(re.search(r"\[rejected\]|\[remote rejected\]|error: failed to push", text))
        g["push_ok"] = ok and not rejected and not re.search(r"^fatal:", text, re.M)
        g["push_failed"] = rejected or (bool(re.search(r"^fatal:", text, re.M)) and not _chained(cmd))
        refs = set(re.findall(r"->\s*([\w./-]+)", text))
        refs |= set(re.findall(r"\b(?:origin|upstream)\s+([\w./:-]+)", cmd))
        refs = {r.split(":")[-1].replace("refs/heads/", "") for r in refs}
        g["push_refs"] = sorted(refs)[:MAX_ITEMS]
        g["push_line"] = next((ln.strip() for ln in text.splitlines() if "->" in ln or "rejected" in ln
                               or "up-to-date" in ln or "error" in ln), "")
        g["push_line"] = _cut(g["push_line"])
    if re.search(r"\bgit\b(?:(?!\bgit\b)[^|;&])*\bcommit\b", cmd):
        m = re.search(r"^\[([^\]\s]+)(?:\s+\(root-commit\))?\s+([0-9a-f]{7,40})\]", text, re.M)
        clean = bool(re.search(r"nothing to commit|nothing added to commit", text))  # already committed: not a failure
        failed = bool(re.search(r"^(?:error|fatal):", text, re.M)) and not m and not clean
        g["commit_ok"] = bool(m) or (ok and exit_code == 0 and not failed and not _chained(cmd))
        g["commit_failed"] = failed and (exit_code not in (0, None) or not _chained(cmd))
        g["commit_nothing"] = clean and not m and exit_code == 1 and not _chained(cmd)
        if m:
            g["commit"] = m.group(2)
            g["commit_branch"] = m.group(1)
        g["commit_line"] = _cut(m.group(0) if m else text.strip().splitlines()[0] if text.strip() else "")
    if re.search(r"\bgh\s+pr\s+merge\b", cmd):
        nums = [int(n) for n in re.findall(r"\bgh\s+pr\s+merge\s+(\d+)", cmd)]
        nums += [int(n) for n in re.findall(r"(?i)merged pull request [^#\n]*#(\d+)", text)]
        merged = ok and bool(re.search(r"(?i)\bmerged\b", text) or (exit_code == 0 and not _chained(cmd)))
        if re.search(r"--auto\b", cmd) or re.search(r"(?i)will be (?:automatically )?merged|added to the merge queue", text):
            merged = bool(re.search(r"(?i)\bmerged pull request\b", text))
        refused = bool(re.search(r"(?i)not mergeable|merge commit cannot|could not|cannot|failed to merge|"
                                 r"pull request (?:(?!pull request ).)* is not|GraphQL: ", text)) and not re.search(r"(?i)\bmerged pull request", text)
        if refused:
            merged = False
        g["merge_ok"] = merged
        g["merge_failed"] = refused and (exit_code not in (0, None) or not _chained(cmd))
        g["merge_cmd_prs"] = sorted(set(nums))
        if merged:
            g["merged_prs"] = sorted(set(nums))
        g["merge_line"] = _cut(text.strip().splitlines()[0]) if text.strip() else ""
    elif re.search(r"\bgh\s+pr\s+(view|status|list)\b", cmd) or re.search(r"\bgh\s+api\b(?:(?!\bgh\s+api\b).)*pulls", cmd):
        states = re.findall(r"(?i)\"?state\"?\s*[:=]\s*\"?(MERGED|OPEN|CLOSED)\b", text)
        nums = [int(n) for n in re.findall(r"\bgh\s+pr\s+view\s+(\d+)", cmd)]
        if len(set(nums)) != 1 or len(set(s.upper() for s in states)) != 1 or "$" in cmd:
            states = []
        if states:
            g["pr_view_state"] = states[0].upper()
            g["pr_view_prs"] = nums
            if states[0].upper() == "MERGED":
                g["merged_prs"] = nums
        # `gh pr view 42` on a PR that doesn't exist: the number is named in the command (or the GraphQL error)
        gone = re.search(r"(?i)could not resolve to a pull ?request with the number of (\d+)|"
                         r"^no pull requests? (?:found|match)", text[:2000], re.M)
        if gone and len(set(nums)) <= 1 and "$" not in cmd and not states:
            n = int(gone.group(1)) if gone.group(1) else (nums[0] if nums else None)
            if n is not None and (not nums or nums[0] == n):
                g["pr_missing"] = [n]
    elif re.search(r"\bgit\b(?:(?!\bgit\b)[^|;&])*\bmerge\b", cmd) and not re.search(r"--abort", cmd):
        g["git_merge_failed"] = bool(re.search(r"CONFLICT|Automatic merge failed|^fatal:", text, re.M))
        g["git_merge_ok"] = ok and not g["git_merge_failed"]
        g["merge_line"] = _cut(text.strip().splitlines()[0]) if text.strip() else ""
    if re.search(r"\bgh\s+pr\s+create\b", cmd):
        g["opened_prs"] = sorted({int(n) for n in re.findall(r"/pull/(\d+)", text)})
        g["pr_create_ok"] = bool(g["opened_prs"])
        g["pr_create_failed"] = not g["opened_prs"] and exit_code not in (0, None) and not _chained(cmd)
    if re.search(r"\bgh\s+(pr\s+checks|pr\s+view\b(?:(?!\bgh\s).)*statusCheckRollup|run\s+(view|watch))\b", cmd) \
            and not re.search(r"\bfor\s+\w+\s+in\b", cmd):
        st = _ci_status(text, exit_code)
        if st:
            g.update(st)
            line = next((ln for ln in text.splitlines() if re.search(r"(?i)\b(fail|failure)\b", ln)), "") \
                if st["ci_fail"] else (text.strip().splitlines() or [""])[0]
            g["ci_line"] = _cut(line.strip())
    return g


def unit_stem(unit: str) -> str:
    u = unit.lower()
    u = {"seconds": "s", "second": "s", "sec": "s", "secs": "s", "minutes": "min", "minute": "min", "mins": "min",
         "percent": "%", "milliseconds": "ms", "millisecond": "ms"}.get(u, u)
    return u[:-1] if len(u) > 3 and u.endswith("s") else u


def _numbers(text: str) -> List[str]:
    seen: Dict[str, None] = {}
    for m in NUM_RE.finditer(text):
        whole = m.group(1).replace(",", "")
        val = whole + ("." + m.group(2) if m.group(2) else "")
        seen.setdefault(val, None)
        if m.group(2):
            seen.setdefault(whole, None)
        if len(seen) >= MAX_NUMBERS:
            break
    return list(seen)


# ---- suite tampering (S4) and agent-written runners (S5) -----------------------------------------------------------
# A green run only proves "all tests pass" for the suite as it was. These record, per call, a change to WHICH tests run:
# a test file deleted or moved, a skip/xfail/only/todo marker, a test or an assertion removed, conftest collection
# hooks, a runner-config filter, an env filter (PYTEST_ADDOPTS=...). Each entry names the change in a short sentence.
# Precision first: new test files, added tests, and edits that keep every test and assertion are not changes.
# Every regex here is bounded (fixed-width repeats, no nested quantifiers) and runs on at most MAX_CMD characters.
TAMPER_MARK_RE = re.compile(
    r"@pytest\.mark\.(?:skip(?!if)|xfail)\b|@pytest\.mark\.skipif\([ \t]*(?:True|1)\b|"
    r"\bpytestmark[ \t]*=[ \t]*\[?[ \t]*pytest\.mark\.(?:skip(?!if)|xfail)\b|"
    r"(?<![\w.])pytest\.(?:skip|xfail)\(|@(?:unittest\.)?skip(?:\(|\b(?!If|Unless))|\.skipTest\(|"
    r"\bt\.Skip(?:Now|f)?\(|#\[ignore\]|@Disabled\b|@Ignore\b|"
    r"(?<![\w.$])(?:it|test|describe|context|suite)\.(?:skip|only|todo)\b|(?<![\w.$])(?:xit|xdescribe|xtest|fit|fdescribe)\(")
CONFTEST_KEY_RE = re.compile(r"\bcollect_ignore(?:_glob)?\b|\bpytest_collection_modifyitems\b|\bpytest_ignore_collect\b|"
                             r"\bpytest_deselected\b|\bitems\[:\][ \t]*=|\bitems\.(?:remove|pop|clear)\(")
# runner configs: a dedicated one (pytest.ini, jest.config.*) changes the suite with any edit; a shared one
# (pyproject.toml, setup.cfg, package.json) only when the new text holds a key that selects tests
RUNNER_CONFIG_RE = re.compile(r"(?:^|/)(?:pytest\.ini|tox\.ini|noxfile\.py|\.mocharc(?:\.[a-z]{2,4})?|karma\.conf\.[cm]?js|"
                              r"phpunit\.xml(?:\.dist)?|(?:jest|vitest|vitest\.workspace|playwright|cypress)\.config\.[cm]?[jt]s(?:on)?)$")
SHARED_CONFIG_RE = re.compile(r"(?:^|/)(?:pyproject\.toml|setup\.cfg|package\.json|vite\.config\.[cm]?[jt]s)$")
CONFIG_KEY_RE = re.compile(r"\baddopts\b|--deselect\b|\bdeselect\b|--ignore(?:-glob)?\b|\bcollect_ignore\b|\bnorecursedirs\b|"
                           r"\btestpaths\b|\bpython_(?:files|functions|classes)\b|\btestPathIgnorePatterns\b|"
                           r"\bmodulePathIgnorePatterns\b|\btestMatch\b|\btestRegex\b|--testNamePattern\b|"
                           r"\"test\"[ \t]*:|\btest[ \t]*:[ \t]*\{|(?:^|[\s'\"=])-k[ \t]")
ENV_FILTER_RE = re.compile(r"(?:^|[\s;&|(])(?:export[ \t]+)?((?:PYTEST_ADDOPTS|JEST_[A-Z_]{1,30}|VITEST_[A-Z_]{1,30}|"
                           r"MOCHA_[A-Z_]{1,30})=('[^'\n]{0,300}'|\"[^\"\n]{0,300}\"|[^\s;&|]{0,300}))")
ENV_FILTER_VALUE_RE = re.compile(r"(?:^|[\s'\"=])(?:-k|-m|-t|--deselect|--ignore(?:-glob)?|--lf|--last-failed|--sw|"
                                 r"--stepwise|--testNamePattern|--testPathIgnorePatterns|--grep)\b")
ASSERT_LINE_RE = re.compile(r"^[ \t]*(?:assert\b|self\.assert\w{0,40}\(|expect\(|assert\w{0,40}\(|t\.(?:Error|Fatal)f?\(|"
                            r"require\.\w{1,40}\(|XCTAssert\w{0,40}\(|should\b)")
TEST_DEF_RE = re.compile(r"(?m)^[ \t]*(?:async[ \t]+)?def[ \t]+(test\w{0,100})|^[ \t]*func[ \t]+(Test\w{0,100})\(|"
                         r"(?<![\w.$])(?:it|test)\([ \t]*['\"`]([^'\"`\n]{1,120})['\"`]")
_DIFF_HEAD_RE = re.compile(r"(?m)^\*\*\* (Update|Add|Delete) File:[ \t]*([^\s\\\"]{1,300})|^\+\+\+ (?:b/)?([^\s\\\"]{1,300})|"
                           r"^--- (?:a/)?([^\s\\\"]{1,300})")
_TEST_DIRS = ("tests", "test", "__tests__", "spec", "specs", "e2e")
_CODE_EXT_RE = re.compile(r"\.(?:py|[cm]?[jt]sx?|rb|go|rs|java|kt|php|cs|swift|scala|ex|exs)$")
_NOT_SOURCE_RE = re.compile(r"(?:^|/)(?:testdata|test_?data|fixtures|snapshots?)/|\.snap$")
MAX_TAMPER = 10
FAILED_ID_RE = re.compile(
    r"(?m)^(?:FAILED|ERROR)[ \t]+([\w./-]{1,200}\.\w{1,5})(?:::([\w.\[\]-]{1,200}))?|"
    r"^([\w./-]{1,200}\.py)::([\w\[\].-]{1,200})[ \t]+(?:FAILED|ERROR)\b|"
    r"^[ \t]*FAIL[ \t]+([\w./@-]{1,200}\.[cm]?[jt]sx?)\b|^[ \t]*--- FAIL: (\w{1,200})|"
    r"^(?:FAIL|ERROR): (\w{1,200}) \(([\w.]{1,200})\)")


def _bare(name: str) -> str:
    """A test name without its parameters: test_login[bob] -> test_login."""
    return name.split("[", 1)[0]


def failed_test_ids(text: str) -> List[str]:
    """Tests a run names as failing: "file::name" (pytest, unittest), "file::" (a jest/vitest file), "::Name" (go)."""
    out: List[str] = []
    for m in FAILED_ID_RE.finditer(text):
        g = m.groups()
        if g[0]:
            item = f"{g[0]}::{_bare((g[1] or '').split('::')[-1])}"
        elif g[2]:
            item = f"{g[2]}::{_bare(g[3])}"
        elif g[4]:
            item = f"{g[4]}::"
        elif g[5]:
            item = f"::{g[5]}"
        else:  # unittest: "FAIL: test_x (pkg.mod.Class)" or, on 3.11+, "(pkg.mod.Class.test_x)"
            parts = g[7].split(".")
            if parts[-1] == g[6]:
                parts.pop()
            if len(parts) > 1 and parts[-1][:1].isupper():
                parts.pop()
            item = f"{'/'.join(parts)}.py::{g[6]}"
        if item not in out:
            out.append(item)
        if len(out) >= 50:
            break
    return out


def test_source(p: str) -> bool:
    """A file (or a whole test directory) the runner collects tests from; not fixtures, test data or snapshots."""
    p = (p or "").strip("`'\"").rstrip("/")
    if not p or path_class(p) != "test" and os.path.basename(p) not in _TEST_DIRS:
        return False
    if os.path.basename(p) in _TEST_DIRS or os.path.basename(p) == "conftest.py":
        return True
    return bool(_CODE_EXT_RE.search(p)) and not _NOT_SOURCE_RE.search(p)


def _test_names(s: str) -> List[str]:
    return [next(g for g in m.groups() if g) for m in TEST_DEF_RE.finditer(s or "")][:MAX_ITEMS]


def _marked_names(s: str) -> List[str]:
    """Tests a skip marker sits on: the next def within 3 lines, or the name inside it.skip('name')."""
    out: List[str] = []
    for k, m in enumerate(TAMPER_MARK_RE.finditer(s or "")):
        if k >= MAX_ITEMS:
            break
        after = s[m.start():m.start() + 600]
        d = TEST_DEF_RE.search("\n".join(after.split("\n")[:4]))
        if d:
            name = next(g for g in d.groups() if g)
            if name not in out:
                out.append(name)
    return out[:MAX_ITEMS]


def _edit_texts(args: Dict[str, Any]) -> List[tuple]:
    """(path or None, old text, new text, whole_file) per edited file named by the tool's own arguments."""
    for old_k, new_k in (("old_string", "new_string"), ("old_str", "new_str"), ("old_text", "new_text"),
                         ("search", "replace")):
        new = args.get(new_k)
        if isinstance(new, str):
            old = args.get(old_k)
            return [(None, old[:MAX_CMD] if isinstance(old, str) else "", new[:MAX_CMD], False)]
    for k in ("content", "file_text", "text", "contents"):
        if isinstance(args.get(k), str):
            return [(None, "", args[k][:MAX_CMD], True)]
    for k in ("patch", "diff", "input"):
        v = args.get(k)
        if isinstance(v, str):
            return _diff_sections(v[:MAX_CMD])
    return []


def _diff_sections(v: str) -> List[tuple]:
    """A unified diff or an apply_patch body, split per file: (path, removed lines, added lines, deleted?)."""
    out: List[tuple] = []
    heads = list(_DIFF_HEAD_RE.finditer(v))[:MAX_ITEMS]
    if not heads:
        plus = "\n".join(ln[1:] for ln in v.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
        minus = "\n".join(ln[1:] for ln in v.splitlines() if ln.startswith("-") and not ln.startswith("---"))
        return [(None, minus, plus, False)]
    minus_path = None
    for k, h in enumerate(heads):
        body = v[h.end():heads[k + 1].start() if k + 1 < len(heads) else len(v)]
        if h.group(4):  # "--- a/path": the old name of the next "+++" section
            minus_path = h.group(4)
            continue
        path = h.group(2) or h.group(3)
        deleted = h.group(1) == "Delete" or path == "/dev/null"
        if path == "/dev/null":
            path = minus_path
        plus = "\n".join(ln[1:] for ln in body.splitlines() if ln.startswith("+"))
        minus = "\n".join(ln[1:] for ln in body.splitlines() if ln.startswith("-"))
        out.append((path, minus, plus, "DELETE" if deleted else False))
        minus_path = None
    return out


def _key_lines(s: str) -> set:
    return {ln.strip() for ln in (s or "").splitlines()[:5000] if CONFIG_KEY_RE.search(ln)}


def _content_change(path: str, old: str, new: str, whole: Any) -> List[Dict[str, Any]]:
    """What one edit of `path` did to the suite (empty for ordinary edits)."""
    out: List[Dict[str, Any]] = []
    base = os.path.basename(path)
    if whole == "DELETE":
        if test_source(path):
            out.append({"kind": "deleted", "path": path, "what": f"{path} deleted"})
        return out
    if test_source(path):
        added = len(TAMPER_MARK_RE.findall(new)) > len(TAMPER_MARK_RE.findall(old))
        if added:
            names = _marked_names(new)
            out.append({"kind": "skip", "path": path, "names": names,
                        "what": f"skip marker added in {path}" + (f" ({', '.join(names[:3])})" if names else "")})
        if base == "conftest.py" and len(CONFTEST_KEY_RE.findall(new)) > len(CONFTEST_KEY_RE.findall(old)):
            key = CONFTEST_KEY_RE.search(new).group(0).rstrip("(=[: \t")
            out.append({"kind": "conftest", "path": path, "detail": new[:2000], "what": f"{path}: {key} added"})
        if old and not whole:
            now = set(_test_names(new))
            gone = [n for n in _test_names(old) if n not in now]
            if gone:
                out.append({"kind": "removed", "path": path, "names": gone,
                            "what": f"test removed from {path} ({', '.join(gone[:3])})"})
            elif not added:
                kept = {ln.strip() for ln in new.splitlines()}
                if any(ASSERT_LINE_RE.match(ln) and ln.strip() not in kept for ln in old.splitlines()):
                    out.append({"kind": "assert", "path": path, "what": f"assertion changed in {path}"})
    elif RUNNER_CONFIG_RE.search(path) or (SHARED_CONFIG_RE.search(path) and _key_lines(new) - _key_lines(old)):
        changed = sorted(_key_lines(new) - _key_lines(old))
        key = CONFIG_KEY_RE.search(changed[0]) if changed else None
        detail = f" ({key.group(0).strip(' =:{')})" if key and SHARED_CONFIG_RE.search(path) else ""
        out.append({"kind": "config", "path": path, "detail": new[:2000], "what": f"{path} edited{detail}"})
    return out


def _shell_suite_changes(cmd: str, flat: str, targets: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for seg in re.split(r"&&|\|\||;|\||\n", flat or "")[:MAX_SEGS]:
        try:
            toks = shlex.split(seg[:MAX_SEG])
        except ValueError:
            toks = seg[:MAX_SEG].split()
        while toks and (re.fullmatch(r"[A-Z_][A-Z0-9_]*=\S*", toks[0]) or toks[0] in ("sudo", "command", "env")):
            toks = toks[1:]
        if toks[:2] in (["git", "rm"], ["git", "mv"]):
            toks = [toks[0] + "-" + toks[1]] + toks[2:]
        if not toks:
            continue
        args = [t for t in toks[1:] if not t.startswith("-")]
        if toks[0] in ("rm", "git-rm", "unlink", "rmdir"):
            out += [{"kind": "deleted", "path": p, "what": f"{p.rstrip('/')} deleted"} for p in args if test_source(p)]
        elif toks[0] in ("mv", "git-mv") and len(args) >= 2:
            dest = args[-1]
            for p in args[:-1]:
                if test_source(p) and not (_test_file(dest) or os.path.basename(dest) == "conftest.py"):
                    out.append({"kind": "deleted", "path": p, "moved": True, "what": f"{p} moved to {dest}"})
    sed_targets = set(re.findall(r"\b(?:sed\s+-i(?:\s*''|\s+\S+)?|perl\s+-\w*i\S*(?:\s+-\w+)*)\s+(?:'[^']*'|\"[^\"]*\")\s+"
                                 r"([\w./~$-]+)", flat))
    for t in dict.fromkeys(targets):
        if test_source(t):
            if TAMPER_MARK_RE.search(cmd):  # names: a def right after the marker, or one the edit names (sed)
                names = _marked_names(cmd) or list(dict.fromkeys(re.findall(r"\bdef[ \t]+(test\w{0,100})", cmd)))[:20]
                out.append({"kind": "skip", "path": t, "names": names,
                            "what": f"skip marker added in {t}" + (f" ({', '.join(names[:3])})" if names else "")})
            elif os.path.basename(t) == "conftest.py" and CONFTEST_KEY_RE.search(cmd):
                key = CONFTEST_KEY_RE.search(cmd).group(0).rstrip("(=[: \t")
                out.append({"kind": "conftest", "path": t, "detail": cmd[:2000], "what": f"{t}: {key} added"})
            elif t in sed_targets:
                out.append({"kind": "edit", "path": t, "what": f"{t} edited by sed -i"})
        elif RUNNER_CONFIG_RE.search(t) or (SHARED_CONFIG_RE.search(t) and CONFIG_KEY_RE.search(cmd)):
            out.append({"kind": "config", "path": t, "detail": cmd[:2000], "what": f"{t} edited"})
    for m in ENV_FILTER_RE.finditer(cmd):
        if ENV_FILTER_VALUE_RE.search(m.group(2).strip("'\"")):
            out.append({"kind": "env", "detail": m.group(2), "what": f"{m.group(1)} set"})
        if len(out) >= MAX_TAMPER:
            break
    return out


def suite_changes(name: str, args: Dict[str, Any], cmd: str, flat: str, shell: bool, edit_tool: bool,
                  paths: List[str], targets: List[str]) -> List[Dict[str, Any]]:
    """The suite changes one successful call made (see TAMPER_MARK_RE). Each: kind, path, names, what."""
    out: List[Dict[str, Any]] = []
    if shell:
        out = _shell_suite_changes(cmd, flat, targets)
    elif edit_tool:
        deleting = bool(re.search(r"delete|remove|unlink", name))
        if deleting:
            out += [{"kind": "deleted", "path": p, "what": f"{p} deleted"} for p in paths if test_source(p)]
        elif re.search(r"rename|move", name):
            dest = next((args[k] for k in ("new_path", "destination", "dest", "to", "target") if isinstance(args.get(k), str)), "")
            out += [{"kind": "deleted", "path": p, "moved": True, "what": f"{p} moved to {dest or 'elsewhere'}"}
                    for p in paths[:1] if test_source(p) and not _test_file(dest)]
        else:
            for path, old, new, whole in _edit_texts(args):
                for p in ([path] if path else paths[:1]):
                    if p:
                        out += _content_change(p, old, new, whole)
    for t in out:
        t["what"] = redact(t["what"])[:160]
        if "detail" in t:
            t["detail"] = redact(t["detail"])[:2000]
    return out[:MAX_TAMPER]


# a test runner the agent may have written itself: a script named by the run, or the Makefile behind `make test`
RUNNER_SCRIPT_RE = re.compile(r"(?:^|\s)(?:(?:ba|z)?sh\s+|\./)?((?:[\w.-]{1,100}/){0,6}[\w.-]{1,100}\.(?:sh|bash|py))\b|"
                              r"(?:^|\s)\./((?:[\w.-]{1,100}/){0,6}[\w-]{1,100})(?=\s|$)")


def runner_files(cmd: str) -> List[str]:
    """Files a test command runs that an agent could have written: `./test.sh`, `bash scripts/ci.sh`, a Makefile."""
    seg = runner_segment(cmd or "")
    if not seg:
        return []
    out = [a or b for a, b in RUNNER_SCRIPT_RE.findall(seg)]
    if re.match(r"(?:g?make)\b", seg):
        mk = re.search(r"\s-f\s+(\S+)", seg)
        out += [mk.group(1)] if mk else ["Makefile", "makefile", "GNUmakefile"]
    return [p for p in dict.fromkeys(out) if p][:10]


def extract(tool_name: str, args: Any, result: Any, status: Optional[str] = None,
            index: int = 0, error_message: Optional[str] = None, cwd: str = "") -> Dict[str, Any]:
    """`cwd`: the session's recorded working directory (ctx.session_cwd), used only to place a file-scoped test run."""
    args = args if isinstance(args, dict) else {}
    text, exit_code, err, parsed = _decode(result)
    windowed = len(text) > HEAD + TAIL
    text = ANSI_RE.sub("", scan_window(text))
    cmd = ""
    cut = False
    for key in ("command", "cmd", "code", "script", "input"):
        if isinstance(args.get(key), str):
            cmd, cut = args[key][:MAX_CMD], len(args[key]) > MAX_CMD
            break
    shell = str(tool_name or "").lower() in ("terminal", "execute_code", "process", "process_manage", "bash", "shell")
    if not shell:
        cmd = cmd if str(tool_name or "").lower() in ("run_command",) else ""
    ok = status != "error" and not err and exit_code in (0, None)
    if isinstance(parsed, dict) and parsed.get("success") is False:
        ok = False
    arg_text = json.dumps(args, default=str)[:HEAD] if args else ""
    ev: Dict[str, Any] = {
        "i": index,
        "tool": str(tool_name or "")[:80],
        "digest": _digest(args),
        "cmd": redact(home_tilde(cmd.strip().replace("\n", " ⏎ ")))[:160],
        "exit": exit_code,
        "ok": ok,
        "error": redact(err or (error_message or ""))[:160],
        "tests": parse_tests(text),
        "test_cmd": bool(runner_segment(cmd, cut)) if shell or tool_name == "run_command" else False,
        "deploy_cmd": bool(DEPLOY_CMD_RE.search(cmd)),
        "build_cmd": bool(BUILD_CMD_RE.search(cmd)) and not TEST_CMD_RE.search(cmd),
        "git": parse_git(cmd, text, exit_code) if cmd else {},
        "paths_written": [],
        "paths_seen": [],
        "http": [],
        "urls": [],
        "shas": [],
        "numbers": [],
        "windowed": windowed,  # the output was longer than the scan window (see HEAD): only part of it was parsed
        "ts": round(time.time(), 3),  # when the call's result arrived (the /cap re-check's session start)
    }
    test_cmd = ev["test_cmd"]
    seg = runner_segment(cmd, cut) if test_cmd else ""
    ev["suite"] = _cut(" ".join(t for t in re.sub(r"\s[12]?>&?\S*", " ", seg).split() if not t.startswith("-")), 120)
    git = r"\bgit\s+(?:(?:-C|-c)\s+\S+\s+|--[\w-]+=\S+\s+)*"  # `git -C /repo stash`, `git -c k=v stash`
    ev["baseline"] = bool(re.search(git + r"stash\b(?!\s+(?:list|show))", cmd)) or bool(
        re.search(git + r"(?:checkout|switch)\s+(?:-\S+\s+)*(?:main|master|origin/\S+|HEAD~\d*|[0-9a-f]{7,40})\b", cmd))
    ev["chained"] = _chained(cmd)
    wm = re.search(r"(?:^|&&|;)\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)|\s-C\s+(\S+)|\s-R\s+(\S+)|--repo[ =](\S+)", cmd)
    where = next((g for g in wm.groups() if g), "").strip("\"'") if wm else ""
    ev["where"] = home_tilde(where)
    wd = args.get("workdir") or args.get("cwd") if isinstance(args, dict) else ""
    ev["workdir"] = home_tilde(wd)[:300] if isinstance(wd, str) else ""  # the tool's own working dir (another repo)
    ev["background"] = bool(args.get("background")) or bool(re.search(r"(?<!&)&\s*$|\bnohup\b", cmd))
    ev["masked"] = bool(re.search(r"\|\||\|\s*(?:tail|head|grep|tee|less|cat|sed|awk)\b|;\s*(?:true|exit 0)\b|\|\s*true\b"
                                  r"|;\s*echo\b", cmd))
    ev["subset"] = test_cmd and _subset(seg, cmd)
    if ev["subset"]:
        # the inventory root: one `cd` before the runner, or none; `-C`/`--repo` or a later `cd` make it unknown.
        # A result "cwd" is where the command ended (Hermes reports it only when a `cd` changed it); otherwise the
        # call's workdir, else the session's cwd. Never the plugin process's own cwd: unknown root = abstain.
        cds = list(re.finditer(r"(?:^|&&|;)\s*cd\s", cmd))
        known = not (wm and not wm.group(1)) and len(cds) <= 1 and (not cds or cds[0].start() < cmd.find(seg))
        ended = parsed.get("cwd") if isinstance(parsed, dict) else None
        base = args.get("workdir") or args.get("cwd") or cwd or ""
        if isinstance(ended, str) and ended:
            directory = ended
        else:
            directory = os.path.join(base, where) if isinstance(base, str) and where else base
        files = _full_file_run(seg, cmd, directory) if isinstance(directory, str) and known else []
        if files:
            ev["subset"] = False
            ev["test_files"] = [redact(p) for p in files]
    # a quiet run piped only into tail: the end of the output is shown, so failures would be too
    ev["tail_only"] = ev["masked"] and not re.search(r"\|\||\|\s*(?:head|grep|tee|less|cat|sed|awk)\b|;\s*(?:true|exit 0)\b|"
                                                     r"\|\s*true\b|;\s*echo\b", cmd) and bool(re.search(r"\|\s*tail\b", cmd))
    # multi-section runners (one summary per crate / package) cut by `| head`, or filtered and then cut: the
    # visible summaries are only part of the run, so they can't prove "all tests pass" or an exact count
    ev["partial"] = bool(test_cmd) and bool(re.search(r"\bcargo\s+(?:\+\S+\s+)?(?:test|nextest)\b|\bgo\s+test\b", seg)) \
        and bool(re.search(r"\|\s*head\b|\|\s*(?:grep|rg|egrep)\b[^|]*(?:\|(?!\s*tail\b)[^|]*)*\|\s*tail\b", cmd))
    ev["fail_text"] = bool(FAIL_TEXT_RE.search(text[-16_000:]))  # read for `| tail` runs, whose output is short
    # silent on success: an empty tail only proves something for runners that print nothing when quiet and green
    ev["quiet_silent"] = not text.strip() and bool(re.search(r"\b(?:mvnw?|gradlew?)\b(?:(?!\b(?:mvnw?|gradlew?)\b).)*\s(?:-q|--quiet)\b", cmd))
    ev["out_empty"] = not text.strip()
    ev["stopped"] = bool(STOPPED_RE.search(text))
    green = [t for t in ev["tests"] if t["passed"] and not t["failed"] and not t["errors"]]
    ev["no_tests"] = (bool(re.search(r"(?i)no tests ran|collected 0 items|no tests found|no test files|ran 0 tests", text))
                      and not green) or (test_cmd and exit_code == 5 and "pytest" in cmd)
    if test_cmd and not ev["tests"] and re.search(r"(?m)^(?:\[INFO\] )?BUILD SUCCESS(?:FUL)?\b", text) and \
            re.search(r"gradlew?|mvnw?", cmd) and not re.search(r"(?m)^(?:\[\w+\] )?BUILD FAIL", text):
        ev["tests"].append({"runner": "gradle" if "gradle" in cmd else "maven", "passed": 0, "failed": 0, "errors": 0,
                            "skipped": 0, "line": "BUILD SUCCESSFUL", "green_marker": True})
    name = ev["tool"].lower()
    path = next((args[k] for k in PATH_KEYS if isinstance(args.get(k), str) and args[k].strip()), None)
    edit_tool = any(k in name for k in EDIT_NAMES) and not READONLY_NAME_RE.search(name) and \
        str(args.get("command") or "").lower() not in ("view", "read", "show")
    if isinstance(path, str) and path and edit_tool:
        ev["paths_written"].append(path)
    if edit_tool and not shell:  # apply_patch-style tools name their files inside the patch text
        ev["paths_written"] += [p for p in PATCH_FILE_RE.findall(arg_text.replace("\\n", "\n"))
                                if p not in ev["paths_written"]][:MAX_ITEMS]
    doc = DOC_PATH_RE
    flat = strip_heredocs(cmd, cut=cut)
    targets = re.findall(r"(?:(?<![\d&>])>{1,2}|\btee\s+(?:-a\s+)?)\s*['\"]?([\w./~$-]+)", flat)
    targets += re.findall(r"\b(?:sed\s+-i(?:\s*''|\s+\S+)?|perl\s+-\w*i\S*(?:\s+-\w+)*)\s+(?:'[^']*'|\"[^\"]*\")\s+([\w./~$-]+)", flat)
    targets += PATCH_FILE_RE.findall(cmd) if shell else []
    py_write = shell and bool(PY_WRITE_RE.search(cmd))
    if py_write:
        targets += re.findall(r"['\"]([~\w./-]+\.[A-Za-z0-9]{1,5})['\"]", cmd)
    code_targets = [t for t in targets if not doc.search(t)]
    written = [p for p in ev["paths_written"] if not doc.search(p)]
    unknown_target = not test_cmd and bool(
        re.search(r"\bgit\s+(?:apply|checkout\s+--|restore|stash\s+pop|merge|pull|rebase|cherry-pick|am)\b|"
                  r"(?:^|[;&|(]\s*|\s)patch\s+(?:-[\w-]+(?:\s+\S+)?\s+)*(?:<|-i\b|-p\d)", cmd)
        or (py_write and not code_targets))
    ev["any_edit"] = bool(written) or (not test_cmd and bool(code_targets)) or unknown_target
    # "edit" = a change that can make an earlier test run stale: source code, not tests, docs, temp files or comments
    comment_only = bool(written) and _comment_only(args)
    tool_code = [p for p in written if path_class(p) == "code"] if ok and not comment_only else []
    shell_code = [t for t in code_targets if path_class(t) == "code"] if not test_cmd else []
    ev["edit"] = bool(tool_code) or bool(shell_code) or unknown_target
    ev["skip_added"] = bool(written) and ok and _adds_skip(args)
    # suite tampering (S4): which tests run changed in this call; a test run's own env filter makes it a subset
    ev["tamper"] = suite_changes(name, args, cmd, flat, shell, edit_tool, ev["paths_written"], targets) if ok else []
    ev["suite_change"] = [t["what"] for t in ev["tamper"]]
    if test_cmd and any(t["kind"] == "env" for t in ev["tamper"]):
        ev["subset"] = True
    ev["failed_tests"] = [redact(x)[:200] for x in failed_test_ids(text)] if test_cmd else []
    ev["check_cmd"] = shell and not test_cmd and bool(CHECK_CMD_RE.search(strip_heredocs(cmd, cut=cut)))
    if cmd and WRITE_CMD_RE.search(cmd) and ok:
        ev["paths_seen"] = sorted(set(re.findall(r"[\w.@~/-]*[\w-]\.[A-Za-z0-9]{1,5}\b|[\w.~-]+/[\w./@-]+", cmd)))[
            :MAX_ITEMS]
    if re.search(r"open\([^)]*,\s*['\"][wa]b?['\"]|\.write_text\(|\.write_bytes\(|shutil\.(?:copy|move)|os\.replace|"
                 r"os\.rename|\.save\(|json\.dump\(", cmd) and ok:
        ev["paths_seen"] = sorted(set(ev["paths_seen"]) | set(re.findall(r"['\"]([~\w./-]+\.[A-Za-z0-9]{1,5})['\"]", cmd)))[:MAX_ITEMS]
    # paths this call actually wrote, moved, created or deleted (a file claim needs one of these, and ok)
    ev["paths_edited"] = list(dict.fromkeys(ev["paths_written"] + (targets + _shell_file_args(flat) if shell else [])))[
        :MAX_ITEMS]
    ev["paths_read"] = [path] if isinstance(path, str) and path and not edit_tool else []
    written_in_output = re.findall(r"(?i)\b(?:wrote|saved|created|written|generated|writing)\b[^\n]{0,40}?"
                                   r"([\w.~/-]+\.[A-Za-z0-9]{1,5})\b", text)
    ev["paths_seen"] = sorted(set(ev["paths_seen"]) | set(written_in_output))[:MAX_ITEMS]
    ev["paths_reported"] = sorted(set(written_in_output))[:MAX_ITEMS] if ok else []  # "Wrote report.pdf"
    if isinstance(parsed, dict) and isinstance(parsed.get("path"), str) and ok:
        ev["paths_seen"].append(parsed["path"])
        (ev["paths_edited"] if edit_tool else ev["paths_read"]).append(parsed["path"])
    codes: List[int] = []
    for rx in HTTP_RES:
        codes += [int(c) for c in rx.findall(text)]
    if "%{http_code}" in cmd:
        codes += [int(c) for c in re.findall(r"(?m)^\s*([1-5]\d\d)\s*$", text)]
    ev["http"] = codes[:MAX_ITEMS]
    urls = URL_RE.findall(cmd + "\n" + arg_text) + URL_RE.findall(text)
    ev["urls"] = list(dict.fromkeys(u.rstrip(".,;:'\"") for u in urls))[:MAX_ITEMS]
    ev["shas"] = list(dict.fromkeys(s for s in SHA_RE.findall(text + "\n" + cmd)
                                    if re.search(r"\d", s) and re.search(r"[a-f]", s)))[:MAX_ITEMS]
    ev["numbers"] = _numbers(text)
    if re.search(r"\bgit\s+(?:diff|show)\b(?:(?!\bgit\b)[^|;&])*--stat", cmd):
        fm = list(re.finditer(r"(\d+) files? changed", text))
        if fm:
            pathspec = re.search(r"--stat\S*\s+(?:\S+\s+)*?(?:--\s+)?(?![-~^])[\w./-]*/[\w./-]*|--stat\S*\s+(?:\S+\s+)*--\s+\S", cmd)
            ev["diff_files"] = {"n": int(fm[-1].group(1)), "scoped": bool(pathspec), "line": fm[-1].group(0)}
    if re.search(r"\bgit\s+rev-parse\s+(?:--verify\s+)?HEAD\b", cmd) and ok:
        hm = re.match(r"\s*([0-9a-f]{40})\s*$", text)
        if hm:
            ev["head_sha"] = hm.group(1)
    ev["num_units"] = sorted({f"{n.replace(',', '')}|{unit_stem(u)}" for n, u in
                              re.findall(r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)\s*(%|[A-Za-z]+)", text)} |
                             {f"{n.replace(',', '')}|{unit_stem(u)}" for u, n in
                              re.findall(r"\b([A-Za-z]+)\s*[:=]\s*(\d[\d,]*(?:\.\d+)?)\b", text)})[:MAX_NUMBERS]
    if isinstance(parsed, dict):
        for key in ("bytes_written", "count", "total", "lines"):
            if isinstance(parsed.get(key), int):
                ev["numbers"].append(str(parsed[key]))
    return ev


def summary(ev: Dict[str, Any]) -> Dict[str, Any]:
    """What is persisted: facts only, no raw output, no bulk number/URL sets."""
    keep = {k: ev.get(k) for k in ("i", "tool", "digest", "cmd", "exit", "ok", "error", "test_cmd", "deploy_cmd",
                                   "build_cmd", "background", "edit", "any_edit", "where", "suite", "baseline",
                                   "diff_files", "head_sha", "subset", "stopped", "tail_only", "partial", "fail_text",
                                   "quiet_silent", "out_empty", "windowed")}
    keep["tests"] = ev.get("tests", [])[-3:]
    keep["git"] = ev.get("git", {})
    keep["paths_written"] = ev.get("paths_written", [])[:10]
    keep["http"] = ev.get("http", [])[:10]
    return keep


# The session ledger (cross-turn receipts) keeps, per call, the facts a later turn's claim can be judged on:
# flags, exit codes, test summaries, git facts, SHAs and written paths. Never raw output, numbers or URLs.
_FACT_FLAGS = ("i", "tool", "cmd", "exit", "ok", "error", "test_cmd", "deploy_cmd", "build_cmd", "background", "edit",
               "any_edit", "skip_added", "check_cmd", "where", "suite", "baseline", "chained", "masked", "subset",
               "stopped", "tail_only", "partial", "fail_text", "quiet_silent", "out_empty", "windowed", "no_tests",
               "head_sha", "diff_files", "workdir", "ts")
_FACT_LISTS = {"paths_written": 10, "paths_edited": 20, "paths_reported": 10, "shas": 20, "test_files": 50,
               "failed_tests": 20, "suite_change": 10}


def ledger_fact(ev: Dict[str, Any]) -> Dict[str, Any]:
    """One call as stored in the session ledger (every string still goes through redact() in the store)."""
    keep = {k: ev.get(k) for k in _FACT_FLAGS if k in ev}
    keep["tests"] = list(ev.get("tests") or [])[-5:]
    keep["git"] = dict(ev.get("git") or {})
    for k, n in _FACT_LISTS.items():
        keep[k] = [str(x)[:200] for x in (ev.get(k) or [])][:n]
    return keep
