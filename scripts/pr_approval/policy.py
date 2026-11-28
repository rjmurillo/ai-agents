"""Closed-schema loader for ``.github/pr-approval-policy.toml``.

Any unknown key, duplicate rule ID, unknown classifier ID, or invalid value
raises ``PolicyError``. The engine turns that error into a hold.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import tomllib

from scripts.pr_approval.globs import GlobError, validate_glob

SCHEMA_VERSION = 1
MODES = ("off", "observe", "enforce")
EFFECTS = ("hold", "allow", "classify")
AUTHOR_CLASSES = ("independent", "agent")
KNOWN_CLASSIFIERS = frozenset({"docs-prose-residue"})

_TOP_KEYS = frozenset({"schema_version", "mode", "budget", "protected", "rules"})
_BUDGET_KEYS = frozenset(
    {"max_rounds", "max_classifier_calls", "max_spend_usd", "deadline_seconds"}
)
_PROTECTED_KEYS = frozenset({"extra_paths"})
_RULE_KEYS = frozenset({"id", "mode", "effect", "classifier", "all"})
_SELECTOR_KEYS = frozenset(
    {
        "paths",
        "author_class",
        "max_files",
        "max_changed_lines",
        "forbid_renames",
        "forbid_binary",
        "forbid_code_fences",
    }
)


class PolicyError(ValueError):
    """Raised when the policy file is missing, invalid, or unsupported."""


@dataclass(frozen=True)
class Budget:
    max_rounds: int
    max_classifier_calls: int
    max_spend_usd: float
    deadline_seconds: int


@dataclass(frozen=True)
class Selector:
    paths: tuple[str, ...] | None = None
    author_class: str | None = None
    max_files: int | None = None
    max_changed_lines: int | None = None
    forbid_renames: bool = False
    forbid_binary: bool = False
    forbid_code_fences: bool = False


@dataclass(frozen=True)
class Rule:
    id: str
    mode: str
    effect: str
    selector: Selector
    classifier: str | None = None


@dataclass(frozen=True)
class Policy:
    schema_version: int
    mode: str
    budget: Budget
    extra_protected_paths: tuple[str, ...]
    rules: tuple[Rule, ...]
    digest: str


def _check_keys(table: object, allowed: frozenset[str], where: str) -> dict:
    if not isinstance(table, dict):
        raise PolicyError(f"{where} must be a table")
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise PolicyError(f"{where} has unknown keys: {', '.join(unknown)}")
    return table


def _int(value: object, where: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PolicyError(f"{where} must be an integer >= {minimum}")
    return value


def _bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyError(f"{where} must be a boolean")
    return value


def _globs(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise PolicyError(f"{where} must be a non-empty list of globs")
    for item in value:
        try:
            validate_glob(item)
        except GlobError as exc:
            raise PolicyError(f"{where}: {exc}") from exc
    return tuple(value)


def _parse_budget(raw: object) -> Budget:
    table = _check_keys(raw, _BUDGET_KEYS, "budget")
    missing = sorted(_BUDGET_KEYS - set(table))
    if missing:
        raise PolicyError(f"budget is missing keys: {', '.join(missing)}")
    spend = table["max_spend_usd"]
    if isinstance(spend, bool) or not isinstance(spend, (int, float)) or spend < 0:
        raise PolicyError("budget.max_spend_usd must be a number >= 0")
    return Budget(
        max_rounds=_int(table["max_rounds"], "budget.max_rounds"),
        max_classifier_calls=_int(table["max_classifier_calls"], "budget.max_classifier_calls"),
        max_spend_usd=float(spend),
        deadline_seconds=_int(table["deadline_seconds"], "budget.deadline_seconds", 1),
    )


def _parse_selector(raw: object, where: str) -> Selector:
    table = _check_keys(raw, _SELECTOR_KEYS, where)
    if not table:
        raise PolicyError(f"{where} must declare at least one selector")
    author_class = table.get("author_class")
    if author_class is not None and author_class not in AUTHOR_CLASSES:
        raise PolicyError(f"{where}.author_class must be one of {AUTHOR_CLASSES}")
    return Selector(
        paths=_globs(table["paths"], f"{where}.paths") if "paths" in table else None,
        author_class=author_class,
        max_files=_int(table["max_files"], f"{where}.max_files", 1)
        if "max_files" in table
        else None,
        max_changed_lines=(
            _int(table["max_changed_lines"], f"{where}.max_changed_lines", 1)
            if "max_changed_lines" in table
            else None
        ),
        forbid_renames=_bool(table.get("forbid_renames", False), f"{where}.forbid_renames"),
        forbid_binary=_bool(table.get("forbid_binary", False), f"{where}.forbid_binary"),
        forbid_code_fences=_bool(
            table.get("forbid_code_fences", False), f"{where}.forbid_code_fences"
        ),
    )


def _parse_rule(raw: object, index: int, repo_mode: str) -> Rule:
    where = f"rules[{index}]"
    table = _check_keys(raw, _RULE_KEYS, where)
    for key in ("id", "mode", "effect", "all"):
        if key not in table:
            raise PolicyError(f"{where} is missing '{key}'")
    rule_id = table["id"]
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise PolicyError(f"{where}.id must be a non-empty string")
    mode = table["mode"]
    if mode not in MODES:
        raise PolicyError(f"{where}.mode must be one of {MODES}")
    if MODES.index(mode) > MODES.index(repo_mode):
        raise PolicyError(f"{where}.mode '{mode}' exceeds repository mode '{repo_mode}'")
    effect = table["effect"]
    if effect not in EFFECTS:
        raise PolicyError(f"{where}.effect must be one of {EFFECTS}")
    classifier = table.get("classifier")
    if effect == "classify":
        if classifier not in KNOWN_CLASSIFIERS:
            raise PolicyError(f"{where}.classifier is unknown: {classifier!r}")
    elif classifier is not None:
        raise PolicyError(f"{where}.classifier is only valid with effect 'classify'")
    return Rule(rule_id, mode, effect, _parse_selector(table["all"], f"{where}.all"), classifier)


def parse_policy(data: bytes) -> Policy:
    """Parse and validate policy bytes. Raises ``PolicyError`` on any defect."""
    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PolicyError(f"policy is not valid UTF-8 TOML: {exc}") from exc
    _check_keys(raw, _TOP_KEYS, "policy")
    if raw.get("schema_version") != SCHEMA_VERSION or isinstance(raw.get("schema_version"), bool):
        raise PolicyError(f"schema_version must be {SCHEMA_VERSION}")
    mode = raw.get("mode")
    if mode not in MODES:
        raise PolicyError(f"mode must be one of {MODES}")
    if "budget" not in raw:
        raise PolicyError("policy is missing 'budget'")
    protected = _check_keys(raw.get("protected", {}), _PROTECTED_KEYS, "protected")
    extra = protected.get("extra_paths", [])
    extra_paths = _globs(extra, "protected.extra_paths") if extra else ()
    rules_raw = raw.get("rules", [])
    if not isinstance(rules_raw, list):
        raise PolicyError("rules must be an array of tables")
    rules = tuple(_parse_rule(item, i, mode) for i, item in enumerate(rules_raw))
    ids = [rule.id for rule in rules]
    duplicates = sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})
    if duplicates:
        raise PolicyError(f"duplicate rule IDs: {', '.join(duplicates)}")
    return Policy(
        schema_version=SCHEMA_VERSION,
        mode=mode,
        budget=_parse_budget(raw["budget"]),
        extra_protected_paths=extra_paths,
        rules=rules,
        digest=hashlib.sha256(data).hexdigest(),
    )
