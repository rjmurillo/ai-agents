#!/usr/bin/env python3
"""Trusted vendor provenance validator (base-branch owned, standalone).

Runs from BASE branch via pull_request_target. Authenticates every
pre-verification executable, generated counterpart, config, manifest, and
vendor tree in a candidate PR. Imports NO candidate modules before or
during verification. Trust-anchor pin changes require a separate bootstrap
PR merged into main.

Exit codes: 0 = pass, 1 = blocked, 2 = infra error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

# ── Trust-anchor pins (SHA-256, lowercase hex) ──
# Each entry: (relative path in candidate, expected sha256, label).
# Pins cover every file that executes BEFORE or DURING verification,
# plus generated counterparts and configs. Future vendor/runtime PRs
# add new pins here via a bootstrap update PR.
_PINNED_ARTIFACTS: list[tuple[str, str, str]] = [
    # --- Hook executables (pre-verification) ---
    (
        ".claude/hooks/PreToolUse/_bootstrap.py",
        "8f1af9122ae5d58e6b4ccd2c9918005c0832bb6b8e4c16cf449c2f53420ccbf1",
        "Hook bootstrap",
    ),
    (
        ".claude/hooks/PreToolUse/invoke_markdownlint_guard.py",
        "236e1310f325bbb5c6fea8d71af61a578e58e7fe72c9f2c14a6903bb9122fb76",
        "Markdownlint guard invoker",
    ),
    (
        ".claude/hooks/PreToolUse/push_guard_base.py",
        "06350d22bfe67737ffede2abd71dcd761d751dd41081da83d30254a8c14785ff",
        "Push guard base",
    ),
    # --- Generated counterparts (copilot-cli mirrors) ---
    (
        "src/copilot-cli/hooks/PreToolUse/_bootstrap.py",
        "8f1af9122ae5d58e6b4ccd2c9918005c0832bb6b8e4c16cf449c2f53420ccbf1",
        "Generated bootstrap mirror",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/push_guard_base.py",
        "080ecaed5dfc7bc26db053ab824ed2f22b8f3b99d80e401bbd09e9a8d467f6ba",
        "Generated push_guard_base mirror",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/"
        "invoke_markdownlint_guard__Bash_git_push_0e93bf.py",
        "2016218b8e3be302820c0b0c97cd7f95370381d6b171cb244919e9a2e3215e92",
        "Generated markdownlint guard mirror",
    ),
    # --- Copilot-CLI dispatch ---
    (
        "src/copilot-cli/hooks/PreToolUse/_dispatch.py",
        "9324714377e69ea297dd429acc3a7eafa24c43af75f06cdba29596d25090eef9",
        "Generated dispatch",
    ),
    # --- Generator surface ---
    (
        "build/scripts/generate_hooks_events.py",
        "2d3b7c11ee600e57483b950f67f40c1da52ff80ce0f14db584fdc93ea3cbe8eb",
        "Hook event generator",
    ),
    # --- Lib: full import closure (.claude/lib + src/copilot-cli/lib) ---
    (".claude/lib/ai_review_common/__init__.py",
     "5417034baa3559df545628194476d4b69549b7636fbe06f56214fbd0d28493c6",
     "Lib: .claude/lib/ai_review_common/__init__.py"),
    (".claude/lib/ai_review_common/cache_guard.py",
     "831609daa3a9693507ede9335562af1c3b2f85fc21491bcca96471cceef458c6",
     "Lib: .claude/lib/ai_review_common/cache_guard.py"),
    (".claude/lib/ai_review_common/feature_review.py",
     "f1df8a966212a49fd3ce788d13523421904304b0a7d576bcdf9c946f6951f522",
     "Lib: .claude/lib/ai_review_common/feature_review.py"),
    (".claude/lib/ai_review_common/issue_triage.py",
     "4ef473208dfacba52a514c4bc06155c9e877faf01bbb48bfdfb1795487e38061",
     "Lib: .claude/lib/ai_review_common/issue_triage.py"),
    (".claude/lib/ai_review_common/quality_gate.py",
     "22ea33bd691f40861379bdfcd5cf2abfff61d49cf008c697818898224b114fc7",
     "Lib: .claude/lib/ai_review_common/quality_gate.py"),
    (".claude/lib/ai_review_common/retry.py",
     "946e205f020fd5dd595bc19053d4b90dc344df5f8b1ea99571f072d5705eacf1",
     "Lib: .claude/lib/ai_review_common/retry.py"),
    (".claude/lib/ai_review_common/verdict.py",
     "6b3475739059a19aef3022a05e7b77ff7f5add074b06310fbdb5d48fa61d60e1",
     "Lib: .claude/lib/ai_review_common/verdict.py"),
    (".claude/lib/ai_review_common/workflow.py",
     "afc062433185e6daf4a066162000ab7a13caa0b4e33383ff2dd450065de240ea",
     "Lib: .claude/lib/ai_review_common/workflow.py"),
    (".claude/lib/bootstrap.py",
     "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
     "Lib: .claude/lib/bootstrap.py"),
    (".claude/lib/claude_hook_dispatch.py",
     "516aab08f8adbdd0234758762ac8fc91c9633e688fff343e96b4ac7fc5db5f75",
     "Lib: .claude/lib/claude_hook_dispatch.py"),
    (".claude/lib/claude_hook_protocol.py",
     "7005a9db7fb91d3d286035606706ed152c7b3e725a988de52609956e596755b8",
     "Lib: .claude/lib/claude_hook_protocol.py"),
    (".claude/lib/github_core/__init__.py",
     "d5191bc7d7232ef8bd9063103a3ceabe9bc393dde6f1fa03321db6157d250d77",
     "Lib: .claude/lib/github_core/__init__.py"),
    (".claude/lib/github_core/api.py",
     "02c6f626fa07a623a1be1c3e2582a018684d25748405d5df9a8fa2c2bba6a654",
     "Lib: .claude/lib/github_core/api.py"),
    (".claude/lib/github_core/bot_config.py",
     "321a0d5c13fc0f302677842c9cfb346cbd27750746cb9205a619e218428d806d",
     "Lib: .claude/lib/github_core/bot_config.py"),
    (".claude/lib/github_core/checks_rollup.py",
     "b734e7f33978d6d2048825810d9f71f8eb9845be2c2936c85cb1f9b171084575",
     "Lib: .claude/lib/github_core/checks_rollup.py"),
    (".claude/lib/github_core/comment_classification.py",
     "c17b44af346cca4f28fdd93db44ebccde3f373ab0142292c50fc0abba2eadf9b",
     "Lib: .claude/lib/github_core/comment_classification.py"),
    (".claude/lib/github_core/formatting.py",
     "ed8945a7dfd0a16b514afb8f3b126bf5456b5c24afe55d6c36433352186b3bef",
     "Lib: .claude/lib/github_core/formatting.py"),
    (".claude/lib/github_core/gh_client.py",
     "f7657ab90f92b9d45270388e6615e7e0ebc81329449aebfac3d4eda5618a5a16",
     "Lib: .claude/lib/github_core/gh_client.py"),
    (".claude/lib/github_core/log_safety.py",
     "d4696f8fd629359f3749743a18a0aea99e5c83a5d8f56835fbb50f3c14e318a1",
     "Lib: .claude/lib/github_core/log_safety.py"),
    (".claude/lib/github_core/output.py",
     "0e2d424dc3b069dcd0b2cf612cc88b995e649da3aa818a6859ef7e0c5fe73f8a",
     "Lib: .claude/lib/github_core/output.py"),
    (".claude/lib/github_core/placeholder_identity.py",
     "6e0246dd64011fdce3eeb1e8094471fecd3e2f8d6855899940acc57fd7447f1c",
     "Lib: .claude/lib/github_core/placeholder_identity.py"),
    (".claude/lib/github_core/protocol.py",
     "76c0595da9bf62dbe6851c5ef98b2d32a8a75106eaafcbd9338ba03c92ed8c76",
     "Lib: .claude/lib/github_core/protocol.py"),
    (".claude/lib/github_core/rate_limit.py",
     "9acbdd9adc00d9ad47ec539d0e9c67bec7c071f022bdb83eb40b9b5ab58ac9d8",
     "Lib: .claude/lib/github_core/rate_limit.py"),
    (".claude/lib/github_core/repo.py",
     "189b9f3cfa59b9d185a0524db79b323a9c0368a0d5fe3236762b409c66eed47e",
     "Lib: .claude/lib/github_core/repo.py"),
    (".claude/lib/github_core/review_threads.py",
     "4e0d629c358a40a0d20a73c5f40a9c85f3c11dd192fdeae0110dec9201288dcb",
     "Lib: .claude/lib/github_core/review_threads.py"),
    (".claude/lib/github_core/validation.py",
     "8dc31f511595e06656a3ba3ffc3a403994808f0fb35537d0167bbc67935304c0",
     "Lib: .claude/lib/github_core/validation.py"),
    (".claude/lib/github_core/worktree_identity.py",
     "70be96d7a0130cceadfaada781394ae7c40209cdafa0028c29cd9a1b44956f62",
     "Lib: .claude/lib/github_core/worktree_identity.py"),
    (".claude/lib/hook_dispatch.py",
     "3ad0408099710eced8a30655680882ab13d99dd1cd4637a5e453cc1b7b76a92d",
     "Lib: .claude/lib/hook_dispatch.py"),
    (".claude/lib/hook_dispatch_protocol.py",
     "09eb4f18a2e00080b0ddf61ee08d1ab624b650dc8b15fb695bc827d4f354f9c6",
     "Lib: .claude/lib/hook_dispatch_protocol.py"),
    (".claude/lib/hook_dispatch_timeout.py",
     "1f27deac44f92df8904ba7c22fb916589ff20a009b8f5f9c4c93be46acebee0c",
     "Lib: .claude/lib/hook_dispatch_timeout.py"),
    (".claude/lib/hook_utilities/__init__.py",
     "046bf0c55e5e4143bfc5485009bf9cc1b7fd0c86a5fbf55a3dadfa69801464ca",
     "Lib: .claude/lib/hook_utilities/__init__.py"),
    (".claude/lib/hook_utilities/bootstrap.py",
     "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
     "Lib: .claude/lib/hook_utilities/bootstrap.py"),
    (".claude/lib/hook_utilities/guards.py",
     "7cef097821da9494ec4cc6fb0ad95223f0a92ad3f038b7c55c1a7b345f90d574",
     "Lib: .claude/lib/hook_utilities/guards.py"),
    (".claude/lib/hook_utilities/path_safety.py",
     "5e74bbfd4a7a88137745cca178c34efe5632873fa0836d192f164074cfb03b10",
     "Lib: .claude/lib/hook_utilities/path_safety.py"),
    (".claude/lib/hook_utilities/utilities.py",
     "99ace215a380a0f1f17f15d7c910c5927d650ff260d89e6cc8eb6bf087d9de6f",
     "Lib: .claude/lib/hook_utilities/utilities.py"),
    (".claude/lib/output_capture.py",
     "dde31065769a49a0d66b63f4487e9dd1efbf7e82f9e3b6f42c31de2bc0047fc1",
     "Lib: .claude/lib/output_capture.py"),
    (".claude/lib/paths.py",
     "0d11d6295855d9547e8316968a241de580159346cc92e1cca8708ba3e191bee1",
     "Lib: .claude/lib/paths.py"),
    (".claude/lib/qa_report.py",
     "9cdcb33916e7ffcd2df84acefe8cc8706a1c32625b794196c315aebec2d31ae1",
     "Lib: .claude/lib/qa_report.py"),
    (".claude/lib/shim_loader.py",
     "56d6dc47d0871278790690fe9cf78baad73a4f89540866bb14b430db28a56600",
     "Lib: .claude/lib/shim_loader.py"),
    ("src/copilot-cli/lib/ai_review_common/__init__.py",
     "5417034baa3559df545628194476d4b69549b7636fbe06f56214fbd0d28493c6",
     "Lib: src/copilot-cli/lib/ai_review_common/__init__.py"),
    ("src/copilot-cli/lib/ai_review_common/cache_guard.py",
     "831609daa3a9693507ede9335562af1c3b2f85fc21491bcca96471cceef458c6",
     "Lib: src/copilot-cli/lib/ai_review_common/cache_guard.py"),
    ("src/copilot-cli/lib/ai_review_common/feature_review.py",
     "f1df8a966212a49fd3ce788d13523421904304b0a7d576bcdf9c946f6951f522",
     "Lib: src/copilot-cli/lib/ai_review_common/feature_review.py"),
    ("src/copilot-cli/lib/ai_review_common/issue_triage.py",
     "4ef473208dfacba52a514c4bc06155c9e877faf01bbb48bfdfb1795487e38061",
     "Lib: src/copilot-cli/lib/ai_review_common/issue_triage.py"),
    ("src/copilot-cli/lib/ai_review_common/quality_gate.py",
     "22ea33bd691f40861379bdfcd5cf2abfff61d49cf008c697818898224b114fc7",
     "Lib: src/copilot-cli/lib/ai_review_common/quality_gate.py"),
    ("src/copilot-cli/lib/ai_review_common/retry.py",
     "946e205f020fd5dd595bc19053d4b90dc344df5f8b1ea99571f072d5705eacf1",
     "Lib: src/copilot-cli/lib/ai_review_common/retry.py"),
    ("src/copilot-cli/lib/ai_review_common/verdict.py",
     "6b3475739059a19aef3022a05e7b77ff7f5add074b06310fbdb5d48fa61d60e1",
     "Lib: src/copilot-cli/lib/ai_review_common/verdict.py"),
    ("src/copilot-cli/lib/ai_review_common/workflow.py",
     "afc062433185e6daf4a066162000ab7a13caa0b4e33383ff2dd450065de240ea",
     "Lib: src/copilot-cli/lib/ai_review_common/workflow.py"),
    ("src/copilot-cli/lib/bootstrap.py",
     "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
     "Lib: src/copilot-cli/lib/bootstrap.py"),
    ("src/copilot-cli/lib/claude_hook_dispatch.py",
     "516aab08f8adbdd0234758762ac8fc91c9633e688fff343e96b4ac7fc5db5f75",
     "Lib: src/copilot-cli/lib/claude_hook_dispatch.py"),
    ("src/copilot-cli/lib/claude_hook_protocol.py",
     "7005a9db7fb91d3d286035606706ed152c7b3e725a988de52609956e596755b8",
     "Lib: src/copilot-cli/lib/claude_hook_protocol.py"),
    ("src/copilot-cli/lib/github_core/__init__.py",
     "d5191bc7d7232ef8bd9063103a3ceabe9bc393dde6f1fa03321db6157d250d77",
     "Lib: src/copilot-cli/lib/github_core/__init__.py"),
    ("src/copilot-cli/lib/github_core/api.py",
     "02c6f626fa07a623a1be1c3e2582a018684d25748405d5df9a8fa2c2bba6a654",
     "Lib: src/copilot-cli/lib/github_core/api.py"),
    ("src/copilot-cli/lib/github_core/bot_config.py",
     "321a0d5c13fc0f302677842c9cfb346cbd27750746cb9205a619e218428d806d",
     "Lib: src/copilot-cli/lib/github_core/bot_config.py"),
    ("src/copilot-cli/lib/github_core/checks_rollup.py",
     "b734e7f33978d6d2048825810d9f71f8eb9845be2c2936c85cb1f9b171084575",
     "Lib: src/copilot-cli/lib/github_core/checks_rollup.py"),
    ("src/copilot-cli/lib/github_core/comment_classification.py",
     "c17b44af346cca4f28fdd93db44ebccde3f373ab0142292c50fc0abba2eadf9b",
     "Lib: src/copilot-cli/lib/github_core/comment_classification.py"),
    ("src/copilot-cli/lib/github_core/formatting.py",
     "ed8945a7dfd0a16b514afb8f3b126bf5456b5c24afe55d6c36433352186b3bef",
     "Lib: src/copilot-cli/lib/github_core/formatting.py"),
    ("src/copilot-cli/lib/github_core/gh_client.py",
     "f7657ab90f92b9d45270388e6615e7e0ebc81329449aebfac3d4eda5618a5a16",
     "Lib: src/copilot-cli/lib/github_core/gh_client.py"),
    ("src/copilot-cli/lib/github_core/log_safety.py",
     "d4696f8fd629359f3749743a18a0aea99e5c83a5d8f56835fbb50f3c14e318a1",
     "Lib: src/copilot-cli/lib/github_core/log_safety.py"),
    ("src/copilot-cli/lib/github_core/output.py",
     "0e2d424dc3b069dcd0b2cf612cc88b995e649da3aa818a6859ef7e0c5fe73f8a",
     "Lib: src/copilot-cli/lib/github_core/output.py"),
    ("src/copilot-cli/lib/github_core/placeholder_identity.py",
     "6e0246dd64011fdce3eeb1e8094471fecd3e2f8d6855899940acc57fd7447f1c",
     "Lib: src/copilot-cli/lib/github_core/placeholder_identity.py"),
    ("src/copilot-cli/lib/github_core/protocol.py",
     "76c0595da9bf62dbe6851c5ef98b2d32a8a75106eaafcbd9338ba03c92ed8c76",
     "Lib: src/copilot-cli/lib/github_core/protocol.py"),
    ("src/copilot-cli/lib/github_core/rate_limit.py",
     "9acbdd9adc00d9ad47ec539d0e9c67bec7c071f022bdb83eb40b9b5ab58ac9d8",
     "Lib: src/copilot-cli/lib/github_core/rate_limit.py"),
    ("src/copilot-cli/lib/github_core/repo.py",
     "189b9f3cfa59b9d185a0524db79b323a9c0368a0d5fe3236762b409c66eed47e",
     "Lib: src/copilot-cli/lib/github_core/repo.py"),
    ("src/copilot-cli/lib/github_core/review_threads.py",
     "4e0d629c358a40a0d20a73c5f40a9c85f3c11dd192fdeae0110dec9201288dcb",
     "Lib: src/copilot-cli/lib/github_core/review_threads.py"),
    ("src/copilot-cli/lib/github_core/validation.py",
     "8dc31f511595e06656a3ba3ffc3a403994808f0fb35537d0167bbc67935304c0",
     "Lib: src/copilot-cli/lib/github_core/validation.py"),
    ("src/copilot-cli/lib/github_core/worktree_identity.py",
     "70be96d7a0130cceadfaada781394ae7c40209cdafa0028c29cd9a1b44956f62",
     "Lib: src/copilot-cli/lib/github_core/worktree_identity.py"),
    ("src/copilot-cli/lib/hook_dispatch.py",
     "3ad0408099710eced8a30655680882ab13d99dd1cd4637a5e453cc1b7b76a92d",
     "Lib: src/copilot-cli/lib/hook_dispatch.py"),
    ("src/copilot-cli/lib/hook_dispatch_protocol.py",
     "09eb4f18a2e00080b0ddf61ee08d1ab624b650dc8b15fb695bc827d4f354f9c6",
     "Lib: src/copilot-cli/lib/hook_dispatch_protocol.py"),
    ("src/copilot-cli/lib/hook_dispatch_timeout.py",
     "1f27deac44f92df8904ba7c22fb916589ff20a009b8f5f9c4c93be46acebee0c",
     "Lib: src/copilot-cli/lib/hook_dispatch_timeout.py"),
    ("src/copilot-cli/lib/hook_utilities/__init__.py",
     "046bf0c55e5e4143bfc5485009bf9cc1b7fd0c86a5fbf55a3dadfa69801464ca",
     "Lib: src/copilot-cli/lib/hook_utilities/__init__.py"),
    ("src/copilot-cli/lib/hook_utilities/bootstrap.py",
     "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
     "Lib: src/copilot-cli/lib/hook_utilities/bootstrap.py"),
    ("src/copilot-cli/lib/hook_utilities/guards.py",
     "7cef097821da9494ec4cc6fb0ad95223f0a92ad3f038b7c55c1a7b345f90d574",
     "Lib: src/copilot-cli/lib/hook_utilities/guards.py"),
    ("src/copilot-cli/lib/hook_utilities/path_safety.py",
     "5e74bbfd4a7a88137745cca178c34efe5632873fa0836d192f164074cfb03b10",
     "Lib: src/copilot-cli/lib/hook_utilities/path_safety.py"),
    ("src/copilot-cli/lib/hook_utilities/utilities.py",
     "99ace215a380a0f1f17f15d7c910c5927d650ff260d89e6cc8eb6bf087d9de6f",
     "Lib: src/copilot-cli/lib/hook_utilities/utilities.py"),
    ("src/copilot-cli/lib/output_capture.py",
     "dde31065769a49a0d66b63f4487e9dd1efbf7e82f9e3b6f42c31de2bc0047fc1",
     "Lib: src/copilot-cli/lib/output_capture.py"),
    ("src/copilot-cli/lib/paths.py",
     "0d11d6295855d9547e8316968a241de580159346cc92e1cca8708ba3e191bee1",
     "Lib: src/copilot-cli/lib/paths.py"),
    ("src/copilot-cli/lib/qa_report.py",
     "9cdcb33916e7ffcd2df84acefe8cc8706a1c32625b794196c315aebec2d31ae1",
     "Lib: src/copilot-cli/lib/qa_report.py"),
    ("src/copilot-cli/lib/shim_loader.py",
     "56d6dc47d0871278790690fe9cf78baad73a4f89540866bb14b430db28a56600",
     "Lib: src/copilot-cli/lib/shim_loader.py"),
    # --- Vendor artifacts (added by vendor/runtime PR) ---
    # Uncomment and pin when the vendor PR is created:
    # (".claude/hooks/PreToolUse/_markdownlint_verifier.py", "<sha256>", "Verifier"),
    # (".claude/hooks/PreToolUse/markdownlint-safe-config.yaml", "<sha256>", "Config"),
    # (".claude/hooks/PreToolUse/markdownlint-cli2.yaml", "<sha256>", "CLI2 config"),
    # (".claude/hooks/PreToolUse/_vendor/markdownlint/INTEGRITY.json", "<sha256>", "Manifest"),
]

# Vendor-only pins: paths that are allowed to be absent (not yet landed).
# All other pinned paths MUST exist as regular non-symlink files.
_VENDOR_ONLY_PREFIXES = (
    ".claude/hooks/PreToolUse/_markdownlint_verifier.py",
    ".claude/hooks/PreToolUse/markdownlint-safe-config.yaml",
    ".claude/hooks/PreToolUse/markdownlint-cli2.yaml",
    ".claude/hooks/PreToolUse/_vendor/",
)

# ── Lockfile policy ──
_CANONICAL_REGISTRY = "https://registry.npmjs.org/"
_INTEGRITY_RE = re.compile(r"^sha512-[A-Za-z0-9+/]+=*$")
_APPROVED_LOCKFILE_VERSION = "3"
_REJECTED_DEP_KEYS = ("link", "hasInstallScript")

# ── Config safety: execution-capable keys ──
_EXECUTION_KEYS = frozenset((
    "customRules", "markdownItPlugins", "extends",
    "outputFormatters", "globs",
))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_vendor_only(rel: str) -> bool:
    """Return True if the pin is for a vendor artifact not yet landed."""
    return any(rel.startswith(p) for p in _VENDOR_ONLY_PREFIXES)


# ── Artifact authentication ──

def _authenticate_pinned(candidate: Path) -> list[str]:
    """Authenticate every pinned artifact against its trust anchor.

    Every pinned file MUST exist as a regular non-symlink file, unless it
    is a vendor-only pin (not yet landed). Symlinks are rejected to prevent
    TOCTOU or indirection attacks.
    """
    errors: list[str] = []
    for rel, expected, label in _PINNED_ARTIFACTS:
        fpath = candidate / rel
        if _is_vendor_only(rel):
            # Vendor artifacts may be absent until vendor PR lands
            if not fpath.exists():
                continue
        # Non-vendor pins MUST exist
        if not fpath.exists():
            errors.append(f"{label} ({rel}): pinned file missing")
            continue
        # Reject symlinks (even if they point to the right content)
        if fpath.is_symlink():
            errors.append(f"{label} ({rel}): is a symlink, expected regular file")
            continue
        if not fpath.is_file():
            errors.append(f"{label} ({rel}): not a regular file")
            continue
        actual = _sha256_file(fpath)
        if actual != expected:
            errors.append(
                f"{label} ({rel}): SHA-256 mismatch "
                f"(expected {expected[:16]}..., got {actual[:16]}...)"
            )
    return errors


def _check_unpinned_executables(candidate: Path) -> list[str]:
    """Flag executables in watched dirs that are not pinned.

    Scans recursively through hook dirs AND lib dirs to catch any file
    in the import closure that was not pinned.
    """
    errors: list[str] = []
    pinned_rels = {rel for rel, _, _ in _PINNED_ARTIFACTS}
    watched_dirs = [
        candidate / ".claude" / "hooks",
        candidate / ".claude" / "lib",
        candidate / "src" / "copilot-cli" / "hooks",
        candidate / "src" / "copilot-cli" / "lib",
        candidate / "build" / "scripts",
    ]
    for hdir in watched_dirs:
        if not hdir.is_dir():
            continue
        for f in sorted(hdir.rglob("*")):
            if not f.is_file() or f.is_symlink():
                continue
            if "__pycache__" in str(f):
                continue
            if f.suffix not in (".py", ".sh", ".mjs", ".js"):
                continue
            if f.name.startswith(".") or f.name == "CLAUDE.md":
                continue
            rel = str(PurePosixPath(f.relative_to(candidate)))
            if rel not in pinned_rels:
                errors.append(
                    f"Unpinned executable: {rel} "
                    f"(sha256: {_sha256_file(f)[:16]}...)"
                )
    return errors


# ── Mirror parity ──

_MIRROR_PAIRS: list[tuple[str, str]] = [
    (
        ".claude/hooks/PreToolUse/_bootstrap.py",
        "src/copilot-cli/hooks/PreToolUse/_bootstrap.py",
    ),
    # push_guard_base.py: generated mirror strips noqa comments, so byte
    # parity does not hold. Both are independently pinned above.
]


def _check_mirror_parity(candidate: Path) -> list[str]:
    errors: list[str] = []
    for canon_rel, mirror_rel in _MIRROR_PAIRS:
        canon = candidate / canon_rel
        mirror = candidate / mirror_rel
        if canon.is_file() and mirror.is_file():
            if canon.read_bytes() != mirror.read_bytes():
                errors.append(f"Parity mismatch: {canon_rel} vs {mirror_rel}")
    return errors


# ── Lockfile validation ──

def _validate_package_entry(name: str, meta: dict[str, object]) -> list[str]:
    errors: list[str] = []
    resolved = str(meta.get("resolved", ""))
    if not resolved:
        errors.append(f"No resolved URL for {name}")
    elif not resolved.startswith(_CANONICAL_REGISTRY):
        errors.append(f"Non-canonical registry for {name}: {resolved[:80]}")
    integrity = str(meta.get("integrity", ""))
    if not _INTEGRITY_RE.match(integrity):
        errors.append(f"Missing/invalid sha512 integrity for {name}")
    for key in _REJECTED_DEP_KEYS:
        if meta.get(key):
            errors.append(f"Rejected dependency type ({key}) for {name}")
    if resolved and "://" in resolved:
        scheme = resolved.split("://")[0].lower()
        if scheme != "https":
            errors.append(f"Non-HTTPS scheme for {name}: {scheme}")
    return errors


def _validate_lockfile(lockfile: Path) -> list[str]:
    if not lockfile.is_file():
        return []  # No vendor tree yet: not an error
    try:
        data = json.loads(lockfile.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot parse lockfile: {exc}"]
    errors: list[str] = []
    version = str(data.get("lockfileVersion", ""))
    if version != _APPROVED_LOCKFILE_VERSION:
        errors.append(f"lockfileVersion {version!r} != {_APPROVED_LOCKFILE_VERSION!r}")
    packages = data.get("packages", {})
    non_root = {k: v for k, v in packages.items() if k}
    if not non_root and lockfile.is_file():
        errors.append("lockfile has no non-root packages")
    for name, meta in non_root.items():
        errors.extend(_validate_package_entry(name, meta))
        if len(errors) >= 10:
            errors.append("(truncated)")
            break
    return errors


# ── Config safety ──

def _validate_config_safe(config_path: Path) -> list[str]:
    if not config_path.is_file():
        return []  # Config not present yet
    raw = config_path.read_bytes()
    try:
        import yaml
        parsed = yaml.safe_load(raw)
    except ImportError:
        parsed = None
    if parsed is not None:
        return _find_exec_keys(parsed)
    # Regex fallback
    text = raw.decode("utf-8", errors="replace")
    errors: list[str] = []
    for key in _EXECUTION_KEYS:
        pat = rf"""(?:^|\{{|,)\s*['"]?{re.escape(key)}['"]?\s*:"""
        if re.search(pat, text, re.MULTILINE):
            errors.append(f"Execution-capable key '{key}' in config")
    return errors


def _find_exec_keys(obj: object, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            cur = f"{path}.{k}" if path else str(k)
            if str(k) in _EXECUTION_KEYS:
                hits.append(f"Execution-capable key '{k}' at {cur}")
            hits.extend(_find_exec_keys(v, cur))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(_find_exec_keys(item, f"{path}[{i}]"))
    return hits


# ── Symlink containment ──

def _check_symlink_containment(vendor_dir: Path) -> list[str]:
    if not vendor_dir.is_dir():
        return []
    errors: list[str] = []
    vr = vendor_dir.resolve()
    for item in vendor_dir.rglob("*"):
        if item.is_symlink():
            target = (item.parent / os.readlink(item)).resolve()
            if not str(target).startswith(str(vr) + os.sep) and target != vr:
                errors.append(
                    f"Symlink escapes vendor: {item.relative_to(vendor_dir)}"
                )
                if len(errors) >= 5:
                    break
    return errors


# ── .npmrc rejection ──

def _reject_npmrc(candidate: Path, vendor_dir: Path) -> list[str]:
    if not vendor_dir.is_dir():
        return []
    check = vendor_dir
    errors: list[str] = []
    while True:
        if (check / ".npmrc").exists():
            errors.append(f".npmrc at {check.relative_to(candidate)}")
        if check == candidate or check == check.parent:
            break
        check = check.parent
    return errors


# ── Vendor reconstruction ──

def _reconstruct_and_compare(vendor_dir: Path) -> list[str]:
    if not (vendor_dir / "package-lock.json").is_file():
        return []  # No vendor tree
    import shutil
    import tempfile
    nm = vendor_dir / "node_modules"
    if not nm.is_dir():
        return ["vendor has lockfile but no node_modules"]
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vendor-prov-") as td:
        copy = Path(td) / "committed"
        shutil.copytree(vendor_dir, copy, symlinks=True)
        try:
            proc = subprocess.run(
                ["npm", "ci", "--ignore-scripts", "--audit=false"],
                cwd=vendor_dir, capture_output=True,
                encoding="utf-8", errors="replace",
                timeout=120,
                env={**os.environ, "npm_config_fund": "false",
                     "npm_config_registry": _CANONICAL_REGISTRY},
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [f"npm ci failed: {exc}"]
        if proc.returncode != 0:
            return [f"npm ci exit {proc.returncode}: {proc.stderr[:200]}"]
        errors.extend(_compare_nm(copy / "node_modules", vendor_dir / "node_modules"))
    return errors


def _collect_tree(root: Path) -> tuple[dict[str, str], dict[str, str], set[str]]:
    files: dict[str, str] = {}
    symlinks: dict[str, str] = {}
    executables: set[str] = set()
    for item in sorted(root.rglob("*")):
        rel = str(PurePosixPath(item.relative_to(root)))
        if item.is_symlink():
            symlinks[rel] = os.readlink(item)
        elif item.is_file():
            files[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
            if os.access(item, os.X_OK):
                executables.add(rel)
    return files, symlinks, executables


def _compare_nm(committed: Path, reconstructed: Path) -> list[str]:
    errors: list[str] = []
    if not committed.is_dir() or not reconstructed.is_dir():
        return ["node_modules missing for comparison"]
    cf, cs, ce = _collect_tree(committed)
    rf, rs, re_ = _collect_tree(reconstructed)
    extra = set(cf) - set(rf)
    if extra:
        errors.append(f"Extra committed: {sorted(extra)[:3]}")
    miss = set(rf) - set(cf)
    if miss:
        errors.append(f"Missing committed: {sorted(miss)[:3]}")
    for k in sorted(set(cf) & set(rf)):
        if cf[k] != rf[k]:
            errors.append(f"Content mismatch: {k}")
            if len(errors) >= 5:
                break
    if cs != rs:
        errors.append("Symlink set/target differs")
    if ce ^ re_:
        errors.append(f"Executable mode differs: {sorted(ce ^ re_)[:3]}")
    return errors


# ── Main ──

def _run_phase(label: str, errors: list[str]) -> None:
    print(f"\n=== {label} ===")
    for e in errors:
        print(f"  FAIL: {e}")
    if not errors:
        print("  PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Trusted vendor provenance gate")
    parser.add_argument("--candidate-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.candidate_root.resolve()
    if not root.is_dir():
        print(f"ERROR: candidate root not found: {root}", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    vendor = root / ".claude" / "hooks" / "PreToolUse" / "_vendor" / "markdownlint"
    config = root / ".claude" / "hooks" / "PreToolUse" / "markdownlint-safe-config.yaml"

    # 1. Authenticate pinned artifacts
    errs = _authenticate_pinned(root)
    _run_phase("Trust-Anchor Authentication", errs)
    all_errors.extend(errs)

    # 2. Flag unpinned executables
    errs = _check_unpinned_executables(root)
    _run_phase("Unpinned Executable Scan", errs)
    all_errors.extend(errs)

    # 3. Mirror parity
    errs = _check_mirror_parity(root)
    _run_phase("Mirror Parity", errs)
    all_errors.extend(errs)

    # 4. Lockfile policy
    errs = _validate_lockfile(vendor / "package-lock.json")
    _run_phase("Lockfile Policy", errs)
    all_errors.extend(errs)

    # 5. Config safety
    errs = _validate_config_safe(config)
    _run_phase("Config Safety", errs)
    all_errors.extend(errs)

    # 6. Symlink containment
    errs = _check_symlink_containment(vendor)
    _run_phase("Symlink Containment", errs)
    all_errors.extend(errs)

    # 7. .npmrc rejection
    errs = _reject_npmrc(root, vendor)
    _run_phase(".npmrc Rejection", errs)
    all_errors.extend(errs)

    # 8. Vendor reconstruction
    errs = _reconstruct_and_compare(vendor)
    _run_phase("Lockfile Reconstruction", errs)
    all_errors.extend(errs)

    if all_errors:
        print(f"\nBLOCKED: {len(all_errors)} error(s)")
        return 1
    print("\nPASS: All vendor provenance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
