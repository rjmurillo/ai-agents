#!/usr/bin/env python3
# taste-lint: ignore file-size -- single-file security boundary
# taste-lint: ignore complexity -- security validators require complex auth logic
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
import ast
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
    # --- Python runtime and dependency resolution ---
    (
        "pyproject.toml",
        "d2350f57b2d2836a447dab9a4dcb6ec3f46e67ea2fd9c054d09943eecc4cb553",
        "Python project configuration",
    ),
    (
        "uv.lock",
        "cab8e6e1433363e2e53264e5bc0ae2b0a482fe0c5d02f798671f2b00660ad07e",
        "Python dependency lock",
    ),
    (
        ".python-version",
        "3a55324cbeddc91df012407d051dad08c88624c95a82fbdb856728729fbd14ab",
        "Python interpreter selection",
    ),
    # --- Hook executables (pre-verification) ---
    (
        ".claude/hooks/PreToolUse/_bootstrap.py",
        "8f1af9122ae5d58e6b4ccd2c9918005c0832bb6b8e4c16cf449c2f53420ccbf1",
        "Hook bootstrap",
    ),
    (
        ".claude/hooks/PreToolUse/invoke_require_subagent_model.py",
        "c81ad3d83a953b0eb5f9235395991e16825f7892ebe30582b35be585814215e6",
        "Require explicit sub-agent model guard",
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
    (
        ".claude/hooks/PreToolUse/invoke_push_pr_script_identity_guard.py",
        "0c8d6bfa22017724d5cb62c27c0bd51c9a39dfdac656ad1e898b61a15cff9de5",
        "Push PR script identity guard",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_commands.py",
        "46f925781cdd1e457ed014958854c6ee5add0c89d569272f499856c7e4b148ea",
        "Push PR guard module: push pr guard commands",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_evaluators.py",
        "115b1f81659f3be5444a9d801ee62aa1b6ef4579be49b175b051b40835f456f1",
        "Push PR guard module: push pr guard evaluators",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_expansion.py",
        "40596f004d3574fdf0bba7c873f13ef51901581603d727e0b55f56c7099ce1ad",
        "Push PR guard module: push pr guard expansion",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_git.py",
        "b6868f509bb5deb0291f1080bdf5e87e6c177e2da1323251adf084e3da077351",
        "Push PR guard module: push pr guard git",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_git_tables.py",
        "e477634738dff882dffe89538ef7253ff9b7909ea7817d59ce8e8ba8780a8315",
        "Push PR guard module: push pr guard git tables",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_identity.py",
        "5ccfbb7e642e3a251fb35407163f41416dbbb6a28cb780f66b14705dccdda88a",
        "Push PR guard module: push pr guard identity",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_lex.py",
        "e9883faf41923afac71cd2be833ebea3172ab2c84ce3115448833116d547aefd",
        "Push PR guard module: push pr guard lex",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_scope.py",
        "a37ca8af1a722c8b7c90612177549794e15031145872ab89f6afba1174ee6c60",
        "Push PR guard module: push pr guard scope",
    ),
    (
        ".claude/hooks/PreToolUse/_push_pr_guard_tables.py",
        "5bd3c988ec672d9de57950832bf1d0d44955294f408522a54ad1e1e042e431f5",
        "Push PR guard module: push pr guard tables",
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
        "src/copilot-cli/hooks/PreToolUse/invoke_push_pr_script_identity_guard__Bash_f620ca.py",
        "03ed67c363ef927d78c2e6db3e521fbcc1cc982e1bdfcfcbf6c8a0f1d6bd972c",
        "Generated push PR script identity guard mirror",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/invoke_markdownlint_guard__Bash_git_push_0e93bf.py",
        "1ace4b27be46dd7105430073e92eac466854fe52799f1fda19c5709ccffe3969",
        "Generated markdownlint guard mirror",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/invoke_require_subagent_model__Agent_Task_456aac.py",
        "a08cfc5d0510b44943ea9f4056b929ac1d1a458ffa8464195d5f522d279ca93b",
        "Generated require-subagent-model guard mirror",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_commands.py",
        "46f925781cdd1e457ed014958854c6ee5add0c89d569272f499856c7e4b148ea",
        "Generated push PR guard module: push pr guard commands",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_evaluators.py",
        "115b1f81659f3be5444a9d801ee62aa1b6ef4579be49b175b051b40835f456f1",
        "Generated push PR guard module: push pr guard evaluators",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_expansion.py",
        "40596f004d3574fdf0bba7c873f13ef51901581603d727e0b55f56c7099ce1ad",
        "Generated push PR guard module: push pr guard expansion",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_git.py",
        "b6868f509bb5deb0291f1080bdf5e87e6c177e2da1323251adf084e3da077351",
        "Generated push PR guard module: push pr guard git",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_git_tables.py",
        "e477634738dff882dffe89538ef7253ff9b7909ea7817d59ce8e8ba8780a8315",
        "Generated push PR guard module: push pr guard git tables",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_identity.py",
        "5ccfbb7e642e3a251fb35407163f41416dbbb6a28cb780f66b14705dccdda88a",
        "Generated push PR guard module: push pr guard identity",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_lex.py",
        "e9883faf41923afac71cd2be833ebea3172ab2c84ce3115448833116d547aefd",
        "Generated push PR guard module: push pr guard lex",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_scope.py",
        "a37ca8af1a722c8b7c90612177549794e15031145872ab89f6afba1174ee6c60",
        "Generated push PR guard module: push pr guard scope",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_tables.py",
        "5bd3c988ec672d9de57950832bf1d0d44955294f408522a54ad1e1e042e431f5",
        "Generated push PR guard module: push pr guard tables",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/markdownlint-safe-config.yaml",
        "db5924f182f68fd637e65550ab615e7c62d2a2be422e6cd685dbd55710c0c50d",
        "Generated markdownlint safe config",
    ),
    # --- Copilot-CLI dispatch ---
    (
        "src/copilot-cli/hooks/PreToolUse/_dispatch.py",
        "9324714377e69ea297dd429acc3a7eafa24c43af75f06cdba29596d25090eef9",
        "Generated dispatch",
    ),
    # --- Generator surface (full local import closure) ---
    (
        "build/scripts/generate_hooks_events.py",
        "79f0a6622aedb37760de7ceef0a1d69f2ae18a5acee5738900981820ca0e60e8",
        "Hook event generator",
    ),
    (
        "build/scripts/generate_dispatcher.py",
        "0de2b8992132d74993f97f351cea2addf491e3e8d3da2f9e48fad28ae7e4bfed",
        "Build script (hooks generator import)",
    ),
    (
        "build/scripts/generate_hooks_body.py",
        "5c98f1d3b2ea457a15124bfae2d9c100a02850b65853f492394dc12c6fca74be",
        "Build script (hooks generator import)",
    ),
    (
        "build/scripts/generate_hooks_emit.py",
        "5d51b29d3db035427eb5c1a3be0102122f8d0536c92029e86733ebb6b0dc6133",
        "Build script (hooks generator import)",
    ),
    (
        "build/scripts/generate_hooks_expand.py",
        "213005f52f9b66c7495304bc9cc65a71ffc7f7ee0bab55121752b1f559c793cd",
        "Build script (hooks generator import)",
    ),
    (
        "build/scripts/generate_hooks_shim.py",
        "a76dd53e57dfbbcbe9391bba05f17ba1288ed94c713c405917825849b798c12a",
        "Build script (hooks generator import)",
    ),
    (
        "build/scripts/generate_hooks_transaction.py",
        "203122bf4de1766cfe2067b17768e4a431f4bd7f69fee88df6d3f7bfb31fc683",
        "Build script (hooks generator import)",
    ),
    (
        "build/scripts/regen_guard.py",
        "c9e331d1b5dcb81cf5da35ed50eeee30464b3fb972fb6b2546be1dfac375b106",
        "Build script (hooks generator import)",
    ),
    (
        "build/scripts/yaml_loader.py",
        "d2163ab8468da3dc905f2403088d5d617b803d7a28c48cbfd0b12d7bdb10b950",
        "Build script (hooks generator import)",
    ),
    # --- Hook executables (non-PreToolUse) ---
    (
        ".claude/hooks/PostToolUse/invoke_markdown_auto_lint.py",
        "d8272d9117378cb185e1bbb0d059ad819dbbd2c0249ed221c31cd7de1820fcd4",
        "Hook executable",
    ),
    (
        ".claude/hooks/PostToolUse/invoke_memory_capture.py",
        "985259278d6a52a8d65927f9be3282aa0b61b7b8a3346c0d1dbbb0b97d59de39",
        "Hook executable",
    ),
    (
        ".claude/hooks/PostToolUse/invoke_observation_sync.py",
        "9e0200aae4f31a9df5f1069220ba01ae8ef458ef35a886bf7083afb99c2f4a25",
        "Hook executable",
    ),
    (
        ".claude/hooks/PreCompact/invoke_compact_checkpoint.py",
        "087a81091cdd9e193a89525958762e7823e55c095f5ef54e8651f131406742f3",
        "Hook executable",
    ),
    (
        ".claude/hooks/SessionEnd/invoke_memory_reflection.py",
        "a37caa77432d54e4c39b9127fc9369795199b819a1fea9c88e779698d7a92992",
        "Hook executable",
    ),
    (
        ".claude/hooks/SessionStart/invoke_context_loader.py",
        "d4e25686953f52ac7f85bdf1b33d4f196ba0d1d44f91210b2082a13e7fe88d38",
        "Hook executable",
    ),
    (
        ".claude/hooks/UserPromptSubmit/invoke_memory_recall.py",
        "eb1ba8bea43c4785d0a2c82d8a996672026d0f14e40b5aaea2595d331dc79235",
        "Hook executable",
    ),
    (
        ".claude/hooks/invoke_dispatch_claude.py",
        "421169b98d44b91ef0246a8427a036cc2fe40f8e2454469fac504c30eea2e136",
        "Hook executable",
    ),
    (
        ".claude/hooks/session-start.sh",
        "a0e973a02ac898d1880f9a9965f850f5f5cc34de4d1f152c5158f5261921f2b7",
        "Hook executable",
    ),
    # --- Generated PostToolUse ---
    (
        "src/copilot-cli/hooks/PostToolUse/_bootstrap.py",
        "8f1af9122ae5d58e6b4ccd2c9918005c0832bb6b8e4c16cf449c2f53420ccbf1",
        "PostToolUse bootstrap",
    ),
    (
        "src/copilot-cli/hooks/PostToolUse/_dispatch.py",
        "74aa15ca89fe3cefb5b659fd4c04a28d2d73119c448e79736c6cf9f0a5ec93a8",
        "PostToolUse dispatch",
    ),
    (
        "src/copilot-cli/hooks/PostToolUse/invoke_markdown_auto_lint__Write_Edit_c39898.py",
        "291a1ff814d6b2597b769a3f50a292e547d5f614014c616977b5def844f7ec7c",
        "PostToolUse markdownlint guard",
    ),
    # --- Build scripts (full closure) ---
    (
        "build/scripts/__init__.py",
        "692bbfdaae4de1ca66daf44c0a6c4acf74d533326c35539c0ba80ea4aa83bf62",
        "Build script",
    ),
    (
        "build/scripts/aggregate_guard_intercepts.py",
        "31decd248bf6234e3370f529ef8eec67f2dcfe4591a431b11fd641be413a3752",
        "Build script",
    ),
    (
        "build/scripts/build_all.py",
        "edaacad18930c3570d072a3bc2180d34bd6941cc2e321a14080b0e4f485d6058",
        "Build script",
    ),
    (
        "build/scripts/check_agent_content_parity.py",
        "d006ad536bec11c746dbad3a15a2e9553923093ff215719869a322d782d77203",
        "Build script",
    ),
    (
        "build/scripts/check_plugin_manifest_parity.py",
        "dc8398eb3080a078afcaa492c0bd267ed209bee89da65d47544df78f43d58ef9",
        "Build script",
    ),
    (
        "build/scripts/classify_guard_maturity.py",
        "557052b0f769d86ecc07ac8be8f7270143e84a36facc2eb35d6fe3006139e09f",
        "Build script",
    ),
    (
        "build/scripts/copilot_body_translation.py",
        "ec9ce73359ee526e8729d3aba183ca5551d143b204baff8c30429b58a035add4",
        "Build script",
    ),
    (
        "build/scripts/detect_agent_drift.py",
        "5d7f2c0ac3a2d938a2ae7a35b4e9186ddf3877fbd27fea3e91a118be46545f3c",
        "Build script",
    ),
    (
        "build/scripts/generate_commands.py",
        "dd9e305d40e2994cc2d8bcc054802470a24836a17e1932c974b15822f9eddaa0",
        "Build script",
    ),
    (
        "build/scripts/generate_hooks.py",
        "683f8f711629da35748589fabe3a8be43a72a87747f29bd7eb0eb93de392e556",
        "Build script",
    ),
    (
        "build/scripts/generate_pr_quality_prompts.py",
        "ed8647159295166e8bd69c975ad98aea97f8bb1586ab51cb2e1237040970758f",
        "Build script",
    ),
    (
        "build/scripts/generate_rules.py",
        "46798995f522870007ff67dfb549e4e2e42024eb93da94d91fb1763e7355378a",
        "Build script",
    ),
    (
        "build/scripts/generate_skills.py",
        "7e97a6e4291b1af5a0b4b3bd14c1a8d46e328bde6cbb947ae1ed8be8f340e032",
        "Build script",
    ),
    (
        "build/scripts/run_drift_check_ci.py",
        "d8a5d3b6251cc5a5cd8294e38aa83153eb1b86fb50f541e18a4f48047c53f12c",
        "Build script",
    ),
    (
        "build/scripts/validate_agent_matrix_refs.py",
        "2332dc799bc0f21e7bb2522cd655ad0ebd522da3924bdd8d9a4ef223f0c0363c",
        "Build script",
    ),
    (
        "build/scripts/validate_install_parity.py",
        "5f1a89be3ea0faa2fad23ecb01e45ee497da0ba0e9c33a802b04e3354e6d2bbf",
        "Build script",
    ),
    (
        "build/scripts/validate_path_normalization.py",
        "6df72f760a853388f9b1b81b151d772179ea3007a95cba3709a6cdfa905d4868",
        "Build script",
    ),
    (
        "build/scripts/validate_planning_artifacts.py",
        "638889ac130e2a00787ad24fad53ab9780b6bcbe0b452893b3aa5429cb35019b",
        "Build script",
    ),
    (
        "build/scripts/validate_plugin_manifests.py",
        "edf1cc6730fc580b4ee5578a3b785f5e7ce84f41b84ad413ea1f281ae1978fe9",
        "Build script",
    ),
    (
        "build/scripts/validate_plugin_version_bump.py",
        "ba1b1cbeadd5345c8b255ca61a38106f9bcba37acf0749ba21d98f9e100a1c04",
        "Build script",
    ),
    (
        "build/scripts/validate_templates_schema.py",
        "d06178ca99457014ed6e79f90a985cf1222e4e86024e72db34a7e6ef339b9d45",
        "Build script",
    ),
    # --- Hook wiring / config inputs ---
    (
        "src/copilot-cli/hooks/PreToolUse/_manifest.json",
        "6ae49c235033af22ca24395b63e248b87c3ffc9e2b2c44b353a2f477f1904eba",
        "Hook wiring manifest",
    ),
    (
        ".claude/hooks/dispatch_groups.json",
        "97de568309304b92387a806bb0e68a65c5aba286132afaead769b9bb0cb9dd86",
        "Hook wiring dispatch groups",
    ),
    (
        ".github/copilot/settings.json",
        "eddf8243b570daaa3892fbea0114a82dcfcd5794d01f9746557b268452b8b099",
        "GitHub Copilot settings (hook surface)",
    ),
    (
        ".claude/settings.json",
        "b86d26b12e49b75ed007f6e6c32fe428d2b6c4b17bb0da21e42bdcafaf6e3fc8",
        "Claude settings (hook wiring)",
    ),
    (
        ".markdownlint-cli2.yaml",
        "17c5a7d9f537f58626cd05138177a253ec06e685b1a59a53acc88be08852f863",
        "Markdownlint config (pinned safe config)",
    ),
    (
        ".claude/hooks/hooks.json",
        "ec1f54f17efd974a7d05db7ab8ebb277b93c97069e4392c5e95ea5342594dd2c",
        "Hook wiring",
    ),
    (
        "src/copilot-cli/hooks/PostToolUse/_manifest.json",
        "2775f6d04e41938b1497386ba1bc0d51fb0704569f22221fd2f22dacc5375364",
        "Hook wiring",
    ),
    (
        "src/copilot-cli/hooks/hooks.json",
        "47d4ef54c7f0459083c5cbebc7952d5323c16c89dcfd80d062ff4f28c3a0c86e",
        "Hook wiring",
    ),
    # --- Lib: full import closure (.claude/lib + src/copilot-cli/lib) ---
    (
        ".claude/lib/ai_review_common/__init__.py",
        "5417034baa3559df545628194476d4b69549b7636fbe06f56214fbd0d28493c6",
        "Lib: .claude/lib/ai_review_common/__init__.py",
    ),
    (
        ".claude/lib/ai_review_common/cache_guard.py",
        "831609daa3a9693507ede9335562af1c3b2f85fc21491bcca96471cceef458c6",
        "Lib: .claude/lib/ai_review_common/cache_guard.py",
    ),
    (
        ".claude/lib/ai_review_common/feature_review.py",
        "f1df8a966212a49fd3ce788d13523421904304b0a7d576bcdf9c946f6951f522",
        "Lib: .claude/lib/ai_review_common/feature_review.py",
    ),
    (
        ".claude/lib/ai_review_common/issue_triage.py",
        "4ef473208dfacba52a514c4bc06155c9e877faf01bbb48bfdfb1795487e38061",
        "Lib: .claude/lib/ai_review_common/issue_triage.py",
    ),
    (
        ".claude/lib/ai_review_common/quality_gate.py",
        "22ea33bd691f40861379bdfcd5cf2abfff61d49cf008c697818898224b114fc7",
        "Lib: .claude/lib/ai_review_common/quality_gate.py",
    ),
    (
        ".claude/lib/ai_review_common/retry.py",
        "946e205f020fd5dd595bc19053d4b90dc344df5f8b1ea99571f072d5705eacf1",
        "Lib: .claude/lib/ai_review_common/retry.py",
    ),
    (
        ".claude/lib/ai_review_common/verdict.py",
        "6b3475739059a19aef3022a05e7b77ff7f5add074b06310fbdb5d48fa61d60e1",
        "Lib: .claude/lib/ai_review_common/verdict.py",
    ),
    (
        ".claude/lib/ai_review_common/workflow.py",
        "afc062433185e6daf4a066162000ab7a13caa0b4e33383ff2dd450065de240ea",
        "Lib: .claude/lib/ai_review_common/workflow.py",
    ),
    (
        ".claude/lib/bootstrap.py",
        "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
        "Lib: .claude/lib/bootstrap.py",
    ),
    (
        ".claude/lib/claude_hook_dispatch.py",
        "516aab08f8adbdd0234758762ac8fc91c9633e688fff343e96b4ac7fc5db5f75",
        "Lib: .claude/lib/claude_hook_dispatch.py",
    ),
    (
        ".claude/lib/claude_hook_protocol.py",
        "7005a9db7fb91d3d286035606706ed152c7b3e725a988de52609956e596755b8",
        "Lib: .claude/lib/claude_hook_protocol.py",
    ),
    (
        ".claude/lib/github_core/__init__.py",
        "0ce449b32d479955d1f453de05c830abe5192558a08424c5778756f86ea3a26d",
        "Lib: .claude/lib/github_core/__init__.py",
    ),
    (
        ".claude/lib/github_core/api.py",
        "c31ab8f5719295313a8ab1d71405769d72f8b417737817f97cc3163df47312b6",
        "Lib: .claude/lib/github_core/api.py",
    ),
    (
        ".claude/lib/github_core/bot_config.py",
        "4abe6cd8dcb35770ac9ecbe56df1692756c1371cdbbc21b4387ce768490f5415",
        "Lib: .claude/lib/github_core/bot_config.py",
    ),
    (
        ".claude/lib/github_core/checks_rollup.py",
        "dede2391ab079ee5be7c7e9964ab3de3308368ecaf137ec632ffb7af4c0759a1",
        "Lib: .claude/lib/github_core/checks_rollup.py",
    ),
    (
        ".claude/lib/github_core/comment_classification.py",
        "c17b44af346cca4f28fdd93db44ebccde3f373ab0142292c50fc0abba2eadf9b",
        "Lib: .claude/lib/github_core/comment_classification.py",
    ),
    (
        ".claude/lib/github_core/formatting.py",
        "ed8945a7dfd0a16b514afb8f3b126bf5456b5c24afe55d6c36433352186b3bef",
        "Lib: .claude/lib/github_core/formatting.py",
    ),
    (
        ".claude/lib/github_core/gh_client.py",
        "f7657ab90f92b9d45270388e6615e7e0ebc81329449aebfac3d4eda5618a5a16",
        "Lib: .claude/lib/github_core/gh_client.py",
    ),
    (
        ".claude/lib/github_core/log_safety.py",
        "d4696f8fd629359f3749743a18a0aea99e5c83a5d8f56835fbb50f3c14e318a1",
        "Lib: .claude/lib/github_core/log_safety.py",
    ),
    (
        ".claude/lib/github_core/output.py",
        "0e2d424dc3b069dcd0b2cf612cc88b995e649da3aa818a6859ef7e0c5fe73f8a",
        "Lib: .claude/lib/github_core/output.py",
    ),
    (
        ".claude/lib/github_core/placeholder_identity.py",
        "6e0246dd64011fdce3eeb1e8094471fecd3e2f8d6855899940acc57fd7447f1c",
        "Lib: .claude/lib/github_core/placeholder_identity.py",
    ),
    (
        ".claude/lib/github_core/protocol.py",
        "76c0595da9bf62dbe6851c5ef98b2d32a8a75106eaafcbd9338ba03c92ed8c76",
        "Lib: .claude/lib/github_core/protocol.py",
    ),
    (
        ".claude/lib/github_core/rate_limit.py",
        "2740751a1c9ce7a4514478c6cb510bdb1521bdd00a2d5323a0c46270598c84f3",
        "Lib: .claude/lib/github_core/rate_limit.py",
    ),
    (
        ".claude/lib/github_core/repo.py",
        "189b9f3cfa59b9d185a0524db79b323a9c0368a0d5fe3236762b409c66eed47e",
        "Lib: .claude/lib/github_core/repo.py",
    ),
    (
        ".claude/lib/github_core/review_threads.py",
        "4e0d629c358a40a0d20a73c5f40a9c85f3c11dd192fdeae0110dec9201288dcb",
        "Lib: .claude/lib/github_core/review_threads.py",
    ),
    (
        ".claude/lib/github_core/validation.py",
        "8dc31f511595e06656a3ba3ffc3a403994808f0fb35537d0167bbc67935304c0",
        "Lib: .claude/lib/github_core/validation.py",
    ),
    (
        ".claude/lib/github_core/worktree_identity.py",
        "70be96d7a0130cceadfaada781394ae7c40209cdafa0028c29cd9a1b44956f62",
        "Lib: .claude/lib/github_core/worktree_identity.py",
    ),
    (
        ".claude/lib/hook_dispatch.py",
        "cc88353d58c9c6d55d684cc33be7d0dbb05d9b88dba10e9438714175dea5af20",
        "Lib: .claude/lib/hook_dispatch.py",
    ),
    (
        ".claude/lib/hook_dispatch_protocol.py",
        "09eb4f18a2e00080b0ddf61ee08d1ab624b650dc8b15fb695bc827d4f354f9c6",
        "Lib: .claude/lib/hook_dispatch_protocol.py",
    ),
    (
        ".claude/lib/hook_dispatch_timeout.py",
        "ef55506b44b412977fa5692ace50060a15ee7d42ff97991387d7138b78de9e23",
        "Lib: .claude/lib/hook_dispatch_timeout.py",
    ),
    (
        ".claude/lib/hook_utilities/__init__.py",
        "046bf0c55e5e4143bfc5485009bf9cc1b7fd0c86a5fbf55a3dadfa69801464ca",
        "Lib: .claude/lib/hook_utilities/__init__.py",
    ),
    (
        ".claude/lib/hook_utilities/bootstrap.py",
        "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
        "Lib: .claude/lib/hook_utilities/bootstrap.py",
    ),
    (
        ".claude/lib/hook_utilities/guards.py",
        "7cef097821da9494ec4cc6fb0ad95223f0a92ad3f038b7c55c1a7b345f90d574",
        "Lib: .claude/lib/hook_utilities/guards.py",
    ),
    (
        ".claude/lib/hook_utilities/path_safety.py",
        "5e74bbfd4a7a88137745cca178c34efe5632873fa0836d192f164074cfb03b10",
        "Lib: .claude/lib/hook_utilities/path_safety.py",
    ),
    (
        ".claude/lib/hook_utilities/utilities.py",
        "99ace215a380a0f1f17f15d7c910c5927d650ff260d89e6cc8eb6bf087d9de6f",
        "Lib: .claude/lib/hook_utilities/utilities.py",
    ),
    (
        ".claude/lib/output_capture.py",
        "dde31065769a49a0d66b63f4487e9dd1efbf7e82f9e3b6f42c31de2bc0047fc1",
        "Lib: .claude/lib/output_capture.py",
    ),
    (
        ".claude/lib/paths.py",
        "0d11d6295855d9547e8316968a241de580159346cc92e1cca8708ba3e191bee1",
        "Lib: .claude/lib/paths.py",
    ),
    (
        ".claude/lib/qa_report.py",
        "9cdcb33916e7ffcd2df84acefe8cc8706a1c32625b794196c315aebec2d31ae1",
        "Lib: .claude/lib/qa_report.py",
    ),
    (
        ".claude/lib/shim_loader.py",
        "56d6dc47d0871278790690fe9cf78baad73a4f89540866bb14b430db28a56600",
        "Lib: .claude/lib/shim_loader.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/__init__.py",
        "5417034baa3559df545628194476d4b69549b7636fbe06f56214fbd0d28493c6",
        "Lib: src/copilot-cli/lib/ai_review_common/__init__.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/cache_guard.py",
        "831609daa3a9693507ede9335562af1c3b2f85fc21491bcca96471cceef458c6",
        "Lib: src/copilot-cli/lib/ai_review_common/cache_guard.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/feature_review.py",
        "f1df8a966212a49fd3ce788d13523421904304b0a7d576bcdf9c946f6951f522",
        "Lib: src/copilot-cli/lib/ai_review_common/feature_review.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/issue_triage.py",
        "4ef473208dfacba52a514c4bc06155c9e877faf01bbb48bfdfb1795487e38061",
        "Lib: src/copilot-cli/lib/ai_review_common/issue_triage.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/quality_gate.py",
        "22ea33bd691f40861379bdfcd5cf2abfff61d49cf008c697818898224b114fc7",
        "Lib: src/copilot-cli/lib/ai_review_common/quality_gate.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/retry.py",
        "946e205f020fd5dd595bc19053d4b90dc344df5f8b1ea99571f072d5705eacf1",
        "Lib: src/copilot-cli/lib/ai_review_common/retry.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/verdict.py",
        "6b3475739059a19aef3022a05e7b77ff7f5add074b06310fbdb5d48fa61d60e1",
        "Lib: src/copilot-cli/lib/ai_review_common/verdict.py",
    ),
    (
        "src/copilot-cli/lib/ai_review_common/workflow.py",
        "afc062433185e6daf4a066162000ab7a13caa0b4e33383ff2dd450065de240ea",
        "Lib: src/copilot-cli/lib/ai_review_common/workflow.py",
    ),
    (
        "src/copilot-cli/lib/bootstrap.py",
        "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
        "Lib: src/copilot-cli/lib/bootstrap.py",
    ),
    (
        "src/copilot-cli/lib/claude_hook_dispatch.py",
        "516aab08f8adbdd0234758762ac8fc91c9633e688fff343e96b4ac7fc5db5f75",
        "Lib: src/copilot-cli/lib/claude_hook_dispatch.py",
    ),
    (
        "src/copilot-cli/lib/claude_hook_protocol.py",
        "7005a9db7fb91d3d286035606706ed152c7b3e725a988de52609956e596755b8",
        "Lib: src/copilot-cli/lib/claude_hook_protocol.py",
    ),
    (
        "src/copilot-cli/lib/github_core/__init__.py",
        "0ce449b32d479955d1f453de05c830abe5192558a08424c5778756f86ea3a26d",
        "Lib: src/copilot-cli/lib/github_core/__init__.py",
    ),
    (
        "src/copilot-cli/lib/github_core/api.py",
        "c31ab8f5719295313a8ab1d71405769d72f8b417737817f97cc3163df47312b6",
        "Lib: src/copilot-cli/lib/github_core/api.py",
    ),
    (
        "src/copilot-cli/lib/github_core/bot_config.py",
        "4abe6cd8dcb35770ac9ecbe56df1692756c1371cdbbc21b4387ce768490f5415",
        "Lib: src/copilot-cli/lib/github_core/bot_config.py",
    ),
    (
        "src/copilot-cli/lib/github_core/checks_rollup.py",
        "dede2391ab079ee5be7c7e9964ab3de3308368ecaf137ec632ffb7af4c0759a1",
        "Lib: src/copilot-cli/lib/github_core/checks_rollup.py",
    ),
    (
        "src/copilot-cli/lib/github_core/comment_classification.py",
        "c17b44af346cca4f28fdd93db44ebccde3f373ab0142292c50fc0abba2eadf9b",
        "Lib: src/copilot-cli/lib/github_core/comment_classification.py",
    ),
    (
        "src/copilot-cli/lib/github_core/formatting.py",
        "ed8945a7dfd0a16b514afb8f3b126bf5456b5c24afe55d6c36433352186b3bef",
        "Lib: src/copilot-cli/lib/github_core/formatting.py",
    ),
    (
        "src/copilot-cli/lib/github_core/gh_client.py",
        "f7657ab90f92b9d45270388e6615e7e0ebc81329449aebfac3d4eda5618a5a16",
        "Lib: src/copilot-cli/lib/github_core/gh_client.py",
    ),
    (
        "src/copilot-cli/lib/github_core/log_safety.py",
        "d4696f8fd629359f3749743a18a0aea99e5c83a5d8f56835fbb50f3c14e318a1",
        "Lib: src/copilot-cli/lib/github_core/log_safety.py",
    ),
    (
        "src/copilot-cli/lib/github_core/output.py",
        "0e2d424dc3b069dcd0b2cf612cc88b995e649da3aa818a6859ef7e0c5fe73f8a",
        "Lib: src/copilot-cli/lib/github_core/output.py",
    ),
    (
        "src/copilot-cli/lib/github_core/placeholder_identity.py",
        "6e0246dd64011fdce3eeb1e8094471fecd3e2f8d6855899940acc57fd7447f1c",
        "Lib: src/copilot-cli/lib/github_core/placeholder_identity.py",
    ),
    (
        "src/copilot-cli/lib/github_core/protocol.py",
        "76c0595da9bf62dbe6851c5ef98b2d32a8a75106eaafcbd9338ba03c92ed8c76",
        "Lib: src/copilot-cli/lib/github_core/protocol.py",
    ),
    (
        "src/copilot-cli/lib/github_core/rate_limit.py",
        "2740751a1c9ce7a4514478c6cb510bdb1521bdd00a2d5323a0c46270598c84f3",
        "Lib: src/copilot-cli/lib/github_core/rate_limit.py",
    ),
    (
        "src/copilot-cli/lib/github_core/repo.py",
        "189b9f3cfa59b9d185a0524db79b323a9c0368a0d5fe3236762b409c66eed47e",
        "Lib: src/copilot-cli/lib/github_core/repo.py",
    ),
    (
        "src/copilot-cli/lib/github_core/review_threads.py",
        "4e0d629c358a40a0d20a73c5f40a9c85f3c11dd192fdeae0110dec9201288dcb",
        "Lib: src/copilot-cli/lib/github_core/review_threads.py",
    ),
    (
        "src/copilot-cli/lib/github_core/validation.py",
        "8dc31f511595e06656a3ba3ffc3a403994808f0fb35537d0167bbc67935304c0",
        "Lib: src/copilot-cli/lib/github_core/validation.py",
    ),
    (
        "src/copilot-cli/lib/github_core/worktree_identity.py",
        "70be96d7a0130cceadfaada781394ae7c40209cdafa0028c29cd9a1b44956f62",
        "Lib: src/copilot-cli/lib/github_core/worktree_identity.py",
    ),
    (
        "src/copilot-cli/lib/hook_dispatch.py",
        "cc88353d58c9c6d55d684cc33be7d0dbb05d9b88dba10e9438714175dea5af20",
        "Lib: src/copilot-cli/lib/hook_dispatch.py",
    ),
    (
        "src/copilot-cli/lib/hook_dispatch_protocol.py",
        "09eb4f18a2e00080b0ddf61ee08d1ab624b650dc8b15fb695bc827d4f354f9c6",
        "Lib: src/copilot-cli/lib/hook_dispatch_protocol.py",
    ),
    (
        "src/copilot-cli/lib/hook_dispatch_timeout.py",
        "ef55506b44b412977fa5692ace50060a15ee7d42ff97991387d7138b78de9e23",
        "Lib: src/copilot-cli/lib/hook_dispatch_timeout.py",
    ),
    (
        "src/copilot-cli/lib/hook_utilities/__init__.py",
        "046bf0c55e5e4143bfc5485009bf9cc1b7fd0c86a5fbf55a3dadfa69801464ca",
        "Lib: src/copilot-cli/lib/hook_utilities/__init__.py",
    ),
    (
        "src/copilot-cli/lib/hook_utilities/bootstrap.py",
        "f18044a4ab6383dd647b3616bacd01ae96145cf2a0107cb45b212a45a66279cc",
        "Lib: src/copilot-cli/lib/hook_utilities/bootstrap.py",
    ),
    (
        "src/copilot-cli/lib/hook_utilities/guards.py",
        "7cef097821da9494ec4cc6fb0ad95223f0a92ad3f038b7c55c1a7b345f90d574",
        "Lib: src/copilot-cli/lib/hook_utilities/guards.py",
    ),
    (
        "src/copilot-cli/lib/hook_utilities/path_safety.py",
        "5e74bbfd4a7a88137745cca178c34efe5632873fa0836d192f164074cfb03b10",
        "Lib: src/copilot-cli/lib/hook_utilities/path_safety.py",
    ),
    (
        "src/copilot-cli/lib/hook_utilities/utilities.py",
        "99ace215a380a0f1f17f15d7c910c5927d650ff260d89e6cc8eb6bf087d9de6f",
        "Lib: src/copilot-cli/lib/hook_utilities/utilities.py",
    ),
    (
        "src/copilot-cli/lib/output_capture.py",
        "dde31065769a49a0d66b63f4487e9dd1efbf7e82f9e3b6f42c31de2bc0047fc1",
        "Lib: src/copilot-cli/lib/output_capture.py",
    ),
    (
        "src/copilot-cli/lib/paths.py",
        "0d11d6295855d9547e8316968a241de580159346cc92e1cca8708ba3e191bee1",
        "Lib: src/copilot-cli/lib/paths.py",
    ),
    (
        "src/copilot-cli/lib/qa_report.py",
        "9cdcb33916e7ffcd2df84acefe8cc8706a1c32625b794196c315aebec2d31ae1",
        "Lib: src/copilot-cli/lib/qa_report.py",
    ),
    (
        "src/copilot-cli/lib/shim_loader.py",
        "56d6dc47d0871278790690fe9cf78baad73a4f89540866bb14b430db28a56600",
        "Lib: src/copilot-cli/lib/shim_loader.py",
    ),
    # --- Vendor artifacts (added by vendor/runtime PR) ---
    # Zero hashes mark artifacts that have not landed. Existing vendor files
    # carry immutable pins. Only _VENDOR_ONLY_PREFIXES may be absent.
    (
        ".claude/hooks/PreToolUse/_markdownlint_verifier.py",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "Verifier (pin placeholder - update on vendor PR)",
    ),
    (
        ".claude/hooks/PreToolUse/markdownlint-safe-config.yaml",
        "db5924f182f68fd637e65550ab615e7c62d2a2be422e6cd685dbd55710c0c50d",
        "Markdownlint safe config",
    ),
    (
        ".claude/hooks/PreToolUse/markdownlint-cli2.yaml",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "CLI2 config (pin placeholder - update on vendor PR)",
    ),
    (
        ".claude/hooks/PreToolUse/_vendor/markdownlint/INTEGRITY.json",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "Manifest (pin placeholder - update on vendor PR)",
    ),
]

# Vendor-only pins: paths that are allowed to be absent (not yet landed).
# All other pinned paths MUST exist as regular non-symlink files.
_VENDOR_ONLY_PREFIXES = (
    ".claude/hooks/PreToolUse/_markdownlint_verifier.py",
    ".claude/hooks/PreToolUse/markdownlint-cli2.yaml",
    ".claude/hooks/PreToolUse/_vendor/",
)

_TRUSTED_UPDATE_ACTORS = frozenset({"rjmurillo"})
_TRUSTED_UPDATE_ACTIONS = frozenset({"opened", "synchronize"})
_VENDOR_PAYLOAD = PurePosixPath(".claude/hooks/PreToolUse/_vendor/markdownlint")
_MAX_MARKDOWNLINT_CONFIG_BYTES = 256 * 1024
_MARKDOWNLINT_POLICY_PATHS = (
    ".markdownlint-cli2.yaml",
    ".claude/hooks/PreToolUse/markdownlint-safe-config.yaml",
    ".claude/hooks/PreToolUse/markdownlint-cli2.yaml",
    "src/copilot-cli/hooks/PreToolUse/markdownlint-safe-config.yaml",
    "src/copilot-cli/hooks/PreToolUse/markdownlint-cli2.yaml",
)
_FORBIDDEN_MARKDOWNLINT_KEYS = frozenset(
    {
        "customRules",
        "extends",
        "markdownItPlugins",
        "outputFormatters",
        "plugins",
        "require",
    }
)

# ── Lockfile policy ──
_CANONICAL_REGISTRY = "https://registry.npmjs.org/"
_INTEGRITY_RE = re.compile(r"^sha512-[A-Za-z0-9+/]+=*$")
_APPROVED_LOCKFILE_VERSION = "3"
_REJECTED_DEP_KEYS = ("link", "hasInstallScript")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_vendor_only(rel: str) -> bool:
    """Return True if the pin is for a vendor artifact not yet landed."""
    return any(rel.startswith(p) for p in _VENDOR_ONLY_PREFIXES)


def _load_candidate_pins(
    candidate: Path,
) -> tuple[list[tuple[str, str, str]] | None, list[str]]:
    """Parse candidate pin data without importing or executing candidate code."""
    source_path = candidate / "scripts" / "ci" / "validate_vendor_provenance.py"
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return None, [f"Cannot parse candidate pin table: {exc}"]

    value: ast.expr | None = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_PINNED_ARTIFACTS":
                value = node.value
                break
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_PINNED_ARTIFACTS"
            for target in node.targets
        ):
            value = node.value
            break
    if value is None:
        return None, ["Candidate validator has no _PINNED_ARTIFACTS assignment"]

    try:
        raw = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError) as exc:
        return None, [f"Candidate pin table is not literal data: {exc}"]
    if not isinstance(raw, list):
        return None, ["Candidate pin table must be a list"]

    pins: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    errors: list[str] = []
    for index, entry in enumerate(raw):
        if (
            not isinstance(entry, tuple)
            or len(entry) != 3
            or not all(isinstance(item, str) for item in entry)
        ):
            errors.append(f"Candidate pin entry {index} must be three strings")
            continue
        rel, digest, label = entry
        rel_path = PurePosixPath(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts or "\\" in rel:
            errors.append(f"Candidate pin path is unsafe: {rel}")
        if rel in seen:
            errors.append(f"Candidate pin path is duplicated: {rel}")
        seen.add(rel)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"Candidate pin digest is invalid: {rel}")
        pins.append((rel, digest, label))
    return (None, errors) if errors else (pins, [])


# ── Artifact authentication ──


def _check_tree_entries(scan_dir: Path, candidate: Path, candidate_resolved: Path) -> list[str]:
    """Check all entries in a watched tree for symlink violations."""
    errors: list[str] = []
    if not scan_dir.is_dir():
        return errors
    for item in sorted(scan_dir.rglob("*")):
        if item.is_symlink() and item.is_dir():
            rel = str(PurePosixPath(item.relative_to(candidate)))
            errors.append(f"Directory symlink in watched tree: {rel}")
        elif item.is_symlink():
            target = (item.parent / os.readlink(item)).resolve()
            if not str(target).startswith(str(candidate_resolved) + os.sep):
                rel = str(PurePosixPath(item.relative_to(candidate)))
                errors.append(f"Symlink escapes candidate root: {rel}")
        elif item.is_file():
            resolved = item.resolve()
            if not str(resolved).startswith(str(candidate_resolved) + os.sep):
                rel = str(PurePosixPath(item.relative_to(candidate)))
                errors.append(f"Resolved path escapes candidate root: {rel}")
    return errors


def _check_path_component_symlinks(candidate: Path) -> list[str]:
    """Reject symlinks in any path component under watched directories.

    Prevents bypass where .claude/lib -> /trusted/base causes leaf files
    to resolve to valid base content while candidate controls the symlink.
    Also enforces that every resolved path stays within candidate root.
    """
    errors: list[str] = []
    candidate_resolved = candidate.resolve()
    scan_dirs = [
        candidate / ".claude" / "hooks",
        candidate / ".claude" / "lib",
        candidate / "src" / "copilot-cli" / "hooks",
        candidate / "src" / "copilot-cli" / "lib",
        candidate / "build" / "scripts",
    ]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        # Check the scan_dir itself
        rel_scan = scan_dir.relative_to(candidate)
        parts = list(rel_scan.parts)
        check = candidate
        for part in parts:
            check = check / part
            if check.is_symlink():
                errors.append(
                    f"Directory component is symlink: "
                    f"{PurePosixPath(*parts[: parts.index(part) + 1])}"
                )
                break
        else:
            errors.extend(_check_tree_entries(scan_dir, candidate, candidate_resolved))
        if len(errors) >= 10:
            break
    return errors


def _check_ancestors_not_symlink(root: Path, rel: str) -> str | None:
    """Reject symlinks in any path component of rel under root.

    Returns an error message if any ancestor is a symlink, None otherwise.
    Does not follow symlinks or depend on target existence.
    """
    parts = Path(rel).parts
    check = root
    for part in parts[:-1]:  # All ancestors, not the leaf
        check = check / part
        if check.is_symlink():
            ancestor_rel = str(check.relative_to(root))
            return f"ancestor {ancestor_rel} is a symlink"
    return None


def _check_file_mode(candidate: Path, base: Path, rel: str, label: str) -> str | None:
    """Reject Git mode changes between base and candidate.

    Compares file permissions (executable bit). If base has 0o755 and
    candidate has 0o644 (or vice versa), reports a mode mismatch.
    Symlink mode (0o120000) and submodule mode (0o160000) are rejected.
    """
    cand_path = candidate / rel
    base_path = base / rel
    if not base_path.exists():
        return None  # Bootstrap: no base reference
    cand_mode = cand_path.stat().st_mode
    base_mode = base_path.stat().st_mode
    # Reject symlink or submodule modes in candidate
    import stat as stat_mod

    if stat_mod.S_ISLNK(cand_mode):
        return f"{label} ({rel}): candidate has symlink mode"
    # Check executable bit consistency
    cand_exec = bool(cand_mode & 0o111)
    base_exec = bool(base_mode & 0o111)
    if cand_exec != base_exec:
        change = "executable->regular" if base_exec else "regular->executable"
        return f"{label} ({rel}): mode changed ({change}); mode tampering rejected"
    return None


def _authenticate_pinned(
    candidate: Path,
    base: Path | None = None,
    pinned_artifacts: list[tuple[str, str, str]] | None = None,
) -> list[str]:
    """Authenticate every pinned artifact against its trust anchor.

    Every pinned file MUST exist as a regular non-symlink file, unless it
    is a vendor-only pin (not yet landed) AND absent from the base tree.
    Once a vendor-only artifact appears in the trusted base, candidate
    deletion is treated as tampering (fail closed).
    """
    errors: list[str] = []
    pins = _PINNED_ARTIFACTS if pinned_artifacts is None else pinned_artifacts
    for rel, expected, label in pins:
        fpath = candidate / rel
        if _is_vendor_only(rel):
            if not fpath.exists():
                if expected != "0" * 64:
                    errors.append(
                        f"{label} ({rel}): pinned file missing for non-placeholder digest"
                    )
                    continue
                # Permit absence only if base also lacks the file
                if base and (base / rel).is_file():
                    errors.append(
                        f"{label} ({rel}): deleted from candidate but "
                        f"present in base (vendor deletion not permitted)"
                    )
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
        # Reject path-component symlinks before reading content
        comp_err = _check_ancestors_not_symlink(candidate, rel)
        if comp_err:
            errors.append(f"{label} ({rel}): {comp_err}")
            continue
        # Authenticate Git mode if base is available
        if base:
            mode_err = _check_file_mode(candidate, base, rel, label)
            if mode_err:
                errors.append(mode_err)
                continue
        actual = _sha256_file(fpath)
        if actual != expected:
            errors.append(
                f"{label} ({rel}): SHA-256 mismatch "
                f"(expected {expected[:16]}..., got {actual[:16]}...)"
            )
    return errors


def _check_unpinned_executables(
    candidate: Path,
    pinned_artifacts: list[tuple[str, str, str]] | None = None,
) -> list[str]:
    """Flag executables in watched dirs that are not pinned.

    Scans recursively through hook dirs AND lib dirs to catch any file
    in the import closure that was not pinned.
    """
    errors: list[str] = []
    pins = _PINNED_ARTIFACTS if pinned_artifacts is None else pinned_artifacts
    pinned_rels = {rel for rel, _, _ in pins}
    vendor_payload = candidate / _VENDOR_PAYLOAD
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
            if f.is_relative_to(vendor_payload):
                continue
            # Reject any symlink (leaf or ancestor): import-through-symlink
            # allows executing code outside the pinned closure.
            if f.is_symlink():
                rel = str(PurePosixPath(f.relative_to(candidate)))
                errors.append(f"Symlink in executable root: {rel}")
                continue
            if not f.is_file():
                continue
            rel_path = f.relative_to(candidate)
            if "__pycache__" in f.parts and (candidate / ".git").exists():
                tracked = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(candidate),
                        "ls-files",
                        "--error-unmatch",
                        "--",
                        str(rel_path),
                    ],
                    check=False,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    text=True,
                )
                if tracked.returncode != 0:
                    continue
            # Skip known non-executable data files
            if f.name == "CLAUDE.md":
                continue
            if f.suffix in (".md", ".txt", ".rst", ".cfg", ".ini", ".toml", ".lock", ".typed"):
                continue
            rel = str(PurePosixPath(rel_path))
            if rel not in pinned_rels:
                errors.append(f"Unpinned executable: {rel} (sha256: {_sha256_file(f)[:16]}...)")
    return errors


# ── Markdownlint config auto-discovery rejection ──

# markdownlint-cli2 auto-discovers config from these names.  Only the
# pinned root config is acceptable.  Any other file matching these patterns
# in watched directories is rejected.
_MARKDOWNLINT_CONFIG_GLOBS: tuple[str, ...] = (
    ".markdownlint-cli2.yaml",
    ".markdownlint-cli2.yml",
    ".markdownlint-cli2.jsonc",
    ".markdownlint-cli2.json",
    ".markdownlint-cli2.cjs",
    ".markdownlint-cli2.mjs",
    ".markdownlint.yaml",
    ".markdownlint.yml",
    ".markdownlint.json",
    ".markdownlint.jsonc",
    ".markdownlint.cjs",
    ".markdownlint.mjs",
)


def _reject_markdownlint_config_injection(candidate: Path) -> list[str]:
    """Reject unpinned markdownlint config anywhere in the candidate tree.

    markdownlint-cli2 auto-discovers config by walking up from the linted
    file. A config placed at ANY depth (docs/, packages/x/, templates/)
    gains Node code execution when linting files in that subtree. Reject
    every markdownlint config basename anywhere except the one pinned root
    config (.markdownlint-cli2.yaml).
    """
    errors: list[str] = []
    pinned_rels = {rel for rel, _, _ in _PINNED_ARTIFACTS}
    # Walk entire candidate tree for markdownlint config names
    for f in sorted(candidate.rglob("*")):
        if f.name not in _MARKDOWNLINT_CONFIG_GLOBS:
            continue
        rel = str(__import__("pathlib").PurePosixPath(f.relative_to(candidate)))
        if f.is_symlink():
            errors.append(f"Markdownlint config is a symlink: {rel}")
            continue
        if not f.is_file():
            continue
        if rel not in pinned_rels:
            errors.append(f"Unpinned markdownlint config: {rel} (auto-discovery attack surface)")
    # Also check for package.json markdownlint-cli2 config field in vendor
    pkg_json = (
        candidate / ".claude" / "hooks" / "PreToolUse" / "_vendor" / "markdownlint" / "package.json"
    )
    if pkg_json.is_file():
        try:
            import json

            data = json.loads(pkg_json.read_text())
            if "markdownlint-cli2" in data:
                errors.append(
                    "package.json contains markdownlint-cli2 config "
                    "(embedded config override attack surface)"
                )
        except (json.JSONDecodeError, OSError):
            pass
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
        vendor_dir = lockfile.parent
        if vendor_dir.exists() or vendor_dir.is_symlink():
            return ["vendor directory exists without package-lock.json"]
        return []
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


def _is_update_authorized(author: str, sender: str, action: str) -> bool:
    # Merge queue admission proves the PR-head provenance check already passed.
    # The synthetic merge_group event does not expose the originating PR identity.
    if action == "merge_group":
        return True
    return (
        author in _TRUSTED_UPDATE_ACTORS
        and sender in _TRUSTED_UPDATE_ACTORS
        and action in _TRUSTED_UPDATE_ACTIONS
    )


def _reject_settings_local(candidate: Path) -> list[str]:
    """Reject .claude/settings.local.json if present in candidate.

    This file can override hook behavior. Repository convention is to
    not commit it. Presence in candidate tree is treated as tampering.
    """
    local_settings = candidate / ".claude" / "settings.local.json"
    if local_settings.exists() or local_settings.is_symlink():
        return [
            ".claude/settings.local.json present in candidate "
            "(hook override file must not be committed)"
        ]
    return []


# ── Trust-anchor self-protection ──
# Once the workflow and validator exist in the trusted base, candidate
# modifications to them must be rejected. The validator runs FROM base,
# so candidate changes only take effect after merge. Blocking here prevents
# a weakened gate from ever landing.
_TRUST_ANCHOR_SELF: tuple[str, ...] = (
    ".github/workflows/vendor-provenance.yml",
    "scripts/ci/validate_vendor_provenance.py",
    "tests/ci/test_validate_vendor_provenance.py",
)


def _check_trust_anchor_integrity(
    candidate: Path,
    base: Path | None,
    *,
    allow_update: bool = False,
) -> list[str]:
    """Reject candidate modification/deletion of trust anchors once base owns them.

    Bootstrap: if base lacks a trust anchor, candidate may add or omit it.
    Post-bootstrap: candidate must have identical bytes to base for each anchor,
    unless the base-owned workflow authenticated a trusted update author.
    Authorized updates may modify anchors but may not delete them.
    """
    if base is None:
        return []  # Cannot compare without base tree
    errors: list[str] = []
    for rel in _TRUST_ANCHOR_SELF:
        base_path = base / rel
        if not base_path.is_file():
            continue  # Bootstrap: base doesn't have it yet
        cand_path = candidate / rel
        if not cand_path.exists():
            errors.append(
                f"Trust anchor deleted: {rel} (present in base, candidate deletion not permitted)"
            )
            continue
        if cand_path.is_symlink():
            errors.append(f"Trust anchor is symlink: {rel}")
            continue
        if not cand_path.is_file():
            errors.append(f"Trust anchor not a regular file: {rel}")
            continue
        # Reject path-component symlinks before reading content
        comp_err = _check_ancestors_not_symlink(candidate, rel)
        if comp_err:
            errors.append(f"Trust anchor path component symlink: {rel} ({comp_err})")
            continue
        base_hash = hashlib.sha256(base_path.read_bytes()).hexdigest()
        cand_hash = hashlib.sha256(cand_path.read_bytes()).hexdigest()
        if cand_hash != base_hash and not allow_update:
            errors.append(
                f"Trust anchor modified: {rel} (candidate differs from base; requires bootstrap PR)"
            )
    return errors


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
                errors.append(f"Symlink escapes vendor: {item.relative_to(vendor_dir)}")
                if len(errors) >= 5:
                    break
    return errors


# ── Integrity manifest ──

_MARKDOWNLINT_ENTRYPOINT = "node_modules/markdownlint-cli2/markdownlint-cli2-bin.mjs"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_integrity_manifest(vendor_dir: Path) -> list[str]:
    """Verify the manifest covers and authenticates the committed vendor tree."""
    if not vendor_dir.exists():
        return []
    manifest_path = vendor_dir / "INTEGRITY.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return ["INTEGRITY.json missing or not a regular file"]
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot parse INTEGRITY.json: {exc}"]
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        return ["INTEGRITY.json files must be a mapping"]
    if not isinstance(manifest.get("symlinks", {}), dict):
        return ["INTEGRITY.json symlinks must be a mapping"]
    if not isinstance(manifest.get("executables", []), list):
        return ["INTEGRITY.json executables must be a list"]

    declared: dict[str, str] = {}
    errors: list[str] = []
    for raw_rel, raw_digest in manifest["files"].items():
        if not isinstance(raw_rel, str) or not isinstance(raw_digest, str):
            errors.append("INTEGRITY.json entries must map paths to SHA-256 strings")
            continue
        declared_path = PurePosixPath(raw_rel)
        if declared_path.is_absolute() or ".." in declared_path.parts or "\\" in raw_rel:
            errors.append(f"Invalid INTEGRITY.json path: {raw_rel!r}")
            continue
        if not _SHA256_RE.fullmatch(raw_digest):
            errors.append(f"Invalid SHA-256 for manifest path: {raw_rel}")
            continue
        declared[str(declared_path)] = raw_digest

    declared_symlinks: dict[str, str] = {}
    for raw_rel, raw_target in manifest.get("symlinks", {}).items():
        if not isinstance(raw_rel, str) or not isinstance(raw_target, str):
            errors.append("INTEGRITY.json symlinks must map paths to targets")
            continue
        declared_path = PurePosixPath(raw_rel)
        target_path = PurePosixPath(raw_target)
        if declared_path.is_absolute() or ".." in declared_path.parts or "\\" in raw_rel:
            errors.append(f"Invalid INTEGRITY.json symlink path: {raw_rel!r}")
            continue
        if target_path.is_absolute() or "\\" in raw_target:
            errors.append(f"Invalid INTEGRITY.json symlink target: {raw_target!r}")
            continue
        resolved_target = PurePosixPath(declared_path.parent, target_path)
        normalized_parts: list[str] = []
        escapes_root = False
        for part in resolved_target.parts:
            if part == "..":
                if not normalized_parts:
                    escapes_root = True
                    break
                normalized_parts.pop()
            elif part != ".":
                normalized_parts.append(part)
        if escapes_root:
            errors.append(f"INTEGRITY.json symlink escapes vendor tree: {raw_rel}")
            continue
        declared_symlinks[str(declared_path)] = raw_target

    declared_executables: set[str] = set()
    for raw_rel in manifest.get("executables", []):
        if not isinstance(raw_rel, str):
            errors.append("INTEGRITY.json executables must contain paths")
            continue
        declared_path = PurePosixPath(raw_rel)
        if declared_path.is_absolute() or ".." in declared_path.parts or "\\" in raw_rel:
            errors.append(f"Invalid INTEGRITY.json executable path: {raw_rel!r}")
            continue
        declared_executables.add(str(declared_path))

    actual: dict[str, str] = {}
    actual_symlinks: dict[str, str] = {}
    actual_executables: set[str] = set()
    for path in sorted(vendor_dir.rglob("*")):
        if path == manifest_path:
            continue
        rel = str(PurePosixPath(path.relative_to(vendor_dir)))
        if path.is_symlink():
            actual_symlinks[rel] = os.readlink(path)
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            errors.append(f"Manifest path is not a file or symlink: {rel}")
            continue
        actual[rel] = _sha256_file(path)
        if path.stat().st_mode & 0o111:
            actual_executables.add(rel)

    missing = sorted(actual.keys() - declared.keys())
    extra = sorted(declared.keys() - actual.keys())
    if missing:
        errors.append(f"INTEGRITY.json missing files: {missing[:5]}")
    if extra:
        errors.append(f"INTEGRITY.json lists absent files: {extra[:5]}")
    if _MARKDOWNLINT_ENTRYPOINT not in declared:
        errors.append(f"Entrypoint {_MARKDOWNLINT_ENTRYPOINT} not in INTEGRITY.json")
    if actual_symlinks != declared_symlinks:
        errors.append("INTEGRITY.json symlink set or target mismatch")
    if actual_executables != declared_executables:
        errors.append("INTEGRITY.json executable set mismatch")
    unknown_executables = sorted(declared_executables - declared.keys())
    if unknown_executables:
        errors.append(
            f"INTEGRITY.json executables list absent files: {unknown_executables[:5]}"
        )
    for rel in sorted(actual.keys() & declared.keys()):
        if actual[rel] != declared[rel]:
            errors.append(f"INTEGRITY.json hash mismatch: {rel}")
            if len(errors) >= 10:
                errors.append("(truncated)")
                break
    return errors


# ── .npmrc rejection ──


def _reject_gitlinks(pr_sha: str) -> list[str]:
    """Reject gitlink (submodule) entries in the candidate tree.

    git checkout-index writes mode-160000 (gitlink) entries as empty
    directories, invisible to filesystem-based validators.  Inspecting the
    git tree object directly closes this bypass vector.
    """
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "-z", pr_sha],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ["_reject_gitlinks: git ls-tree failed (fail closed)"]
    if result.returncode != 0:
        return [f"_reject_gitlinks: git ls-tree exited {result.returncode} (fail closed)"]
    errors: list[str] = []
    # NUL-delimited records are newline-safe (ci-scripts.md:29).
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        # Format: b"<mode> <type> <hash>\t<path>"
        tab_idx = record.find(b"\t")
        if tab_idx == -1:
            continue
        meta = record[:tab_idx]
        path = record[tab_idx + 1:]
        parts = meta.split(None, 2)
        if len(parts) >= 1 and parts[0] == b"160000":
            errors.append(f"gitlink rejected: {path.decode(errors='replace')}")
    return errors


def _publish_check_run(
    repo: str, head_sha: str, conclusion: str, summary: str,
) -> int:
    """Publish a check run on the PR head SHA via the GitHub Checks API.

    pull_request_target attaches the native job check to the base-branch
    SHA, not the PR head SHA.  This function mirrors the job conclusion
    onto the PR head commit so branch-protection rules can gate on it.

    Returns 0 on success, 1 on failure.
    """
    import json as _json
    payload = _json.dumps({
        "name": "Validate Vendor Provenance",
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": "Vendor Provenance",
            "summary": summary,
        },
    })
    try:
        result = subprocess.run(
            [
                "gh", "api", f"repos/{repo}/check-runs",
                "-X", "POST",
                "--input", "-",
            ],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"ERROR: check-run publication failed: {exc}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(f"ERROR: check-run publication failed: {result.stderr}", file=sys.stderr)
        return 1
    return 0


def _reject_npmrc(candidate: Path, vendor_dir: Path) -> list[str]:
    check = vendor_dir
    errors: list[str] = []
    while True:
        npmrc = check / ".npmrc"
        if npmrc.exists() or npmrc.is_symlink():
            errors.append(f".npmrc at {check.relative_to(candidate)}")
        if check == candidate or check == check.parent:
            break
        check = check.parent
    return errors


def _find_forbidden_config_keys(value: object, location: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if isinstance(key, str) and key in _FORBIDDEN_MARKDOWNLINT_KEYS:
                errors.append(f"forbidden execution key at {child_location}")
            errors.extend(_find_forbidden_config_keys(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_find_forbidden_config_keys(child, f"{location}[{index}]"))
    return errors


def _validate_markdownlint_config_policy(candidate: Path) -> list[str]:
    """Safely parse markdownlint YAML and reject code-loading directives."""
    try:
        import yaml
    except ImportError:
        return ["PyYAML is unavailable; cannot validate markdownlint config policy"]
    errors: list[str] = []
    for rel in _MARKDOWNLINT_POLICY_PATHS:
        path = candidate / rel
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > _MAX_MARKDOWNLINT_CONFIG_BYTES:
                errors.append(f"{rel}: config exceeds {_MAX_MARKDOWNLINT_CONFIG_BYTES} bytes")
                continue
            raw = path.read_text(encoding="utf-8")
            unsafe_tokens = {
                token.__class__.__name__
                for token in yaml.scan(raw)
                if token.__class__.__name__ in {"AliasToken", "AnchorToken", "TagToken"}
            }
            if unsafe_tokens:
                errors.append(
                    f"{rel}: YAML aliases, anchors, and tags are forbidden "
                    f"({', '.join(sorted(unsafe_tokens))})"
                )
                continue
            value = yaml.safe_load(raw)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"{rel}: cannot safely parse YAML: {exc}")
            continue
        for error in _find_forbidden_config_keys(value):
            errors.append(f"{rel}: {error}")
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
                cwd=vendor_dir,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                env={
                    **os.environ,
                    "npm_config_fund": "false",
                    "npm_config_registry": _CANONICAL_REGISTRY,
                },
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


# ── Relevance check (extracted for testability) ──

# Watched path prefixes that trigger full validation.
# Executable scan roots (must match _check_unpinned_executables watched_dirs)
_SCAN_ROOTS: tuple[str, ...] = (
    ".claude/hooks/",
    ".claude/lib/",
    "src/copilot-cli/hooks/",
    "src/copilot-cli/lib/",
    "build/scripts/",
)

# Additional trust-anchor surfaces not inside scan roots
_EXTRA_WATCHED: tuple[str, ...] = (
    ".github/workflows/vendor-provenance.yml",
    "scripts/ci/validate_vendor_provenance.py",
    "tests/ci/test_validate_vendor_provenance.py",
    ".claude/settings.json",
    ".markdownlint-cli2.yaml",
    ".gitattributes",
    ".claude/settings.local.json",
    ".github/copilot/settings.json",
    ".claude/.npmrc",
    ".npmrc",
)


def _watched_paths() -> frozenset[str]:
    """Structurally derive the full relevance set.

    Combines: every pinned artifact path, every scan root prefix,
    trust-anchor surfaces, and markdownlint auto-discovery names.
    This prevents drift between pins/rejection and relevance by construction.
    """
    paths: set[str] = set()
    # Every pinned artifact is relevant
    for rel, _, _ in _PINNED_ARTIFACTS:
        paths.add(rel)
    # Scan root directories (prefix match)
    for root in _SCAN_ROOTS:
        paths.add(root)
    # Extra trust-anchor files
    for extra in _EXTRA_WATCHED:
        paths.add(extra)
    # Root markdownlint config names (structurally derived from rejection list)
    for config_name in _MARKDOWNLINT_CONFIG_GLOBS:
        paths.add(config_name)
    return frozenset(paths)


WATCHED_PREFIXES: frozenset[str] = _watched_paths()


def check_relevance(changed_files: list[str]) -> bool:
    """Return True if any changed file falls under a watched path.

    Coverage is derived structurally from _PINNED_ARTIFACTS + _SCAN_ROOTS +
    _EXTRA_WATCHED so that adding a pin automatically adds relevance.
    Covers additions, modifications, deletions, renames, and type changes.
    """
    for f in changed_files:
        # Exact match (pinned files, extra watched files)
        if f in WATCHED_PREFIXES:
            return True
        # Prefix match (scan root directories end with /)
        for prefix in WATCHED_PREFIXES:
            if prefix.endswith("/") and f.startswith(prefix):
                return True
        # Any markdownlint config name at any depth is relevant
        basename = f.rsplit("/", 1)[-1] if "/" in f else f
        if basename in _MARKDOWNLINT_CONFIG_GLOBS:
            return True
    return False


# ── Main ──


def _run_phase(label: str, errors: list[str]) -> None:
    print(f"\n=== {label} ===")
    for e in errors:
        print(f"  FAIL: {e}")
    if not errors:
        print("  PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Trusted vendor provenance gate")
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument(
        "--base-root",
        type=Path,
        default=None,
        help="Base (trusted) tree root for deletion detection",
    )
    parser.add_argument(
        "--check-relevance",
        nargs="*",
        metavar="FILE",
        help="Print 'true'/'false' for whether FILE list touches watched paths",
    )
    parser.add_argument(
        "--check-relevance-stdin",
        action="store_true",
        help="Read NUL-delimited file list from stdin for relevance check",
    )
    parser.add_argument(
        "--pull-request-author",
        default="",
        help="GitHub-authenticated PR author supplied by the base-owned workflow",
    )
    parser.add_argument(
        "--pull-request-sender",
        default="",
        help="GitHub-authenticated actor that created the current PR event",
    )
    parser.add_argument(
        "--pull-request-action",
        default="",
        help="GitHub pull_request_target action that triggered validation",
    )
    parser.add_argument(
        "--pr-sha",
        default="",
        help="PR head SHA for git-tree-level checks (gitlink rejection)",
    )
    parser.add_argument(
        "--publish-check-run",
        nargs=3,
        metavar=("REPO", "HEAD_SHA", "CONCLUSION"),
        help="Publish check run on HEAD_SHA: REPO HEAD_SHA success|failure",
    )
    parser.add_argument(
        "--reject-gitlinks",
        metavar="SHA",
        help="Check tree SHA for gitlink entries and exit 0/1",
    )
    args = parser.parse_args()

    # Gitlink rejection mode
    if args.reject_gitlinks:
        errs = _reject_gitlinks(args.reject_gitlinks)
        if errs:
            for e in errs:
                print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print("PASS: No gitlinks in candidate tree")
        return 0

    # Check-run publication mode

    # Check-run publication mode
    if args.publish_check_run:
        repo, head_sha, conclusion = args.publish_check_run
        summary = (
            f"Vendor provenance validated for {head_sha}"
            if conclusion == "success"
            else f"Vendor provenance validation failed for {head_sha}"
        )
        return _publish_check_run(repo, head_sha, conclusion, summary)

    # Relevance-check mode: output true/false and exit
    if args.check_relevance_stdin:
        import sys as _sys

        data = _sys.stdin.buffer.read()
        # NUL-delimited; filter empty segments (trailing NUL)
        files = [p for p in data.decode("utf-8", errors="surrogateescape").split("\0") if p]
        print("true" if check_relevance(files) else "false")
        return 0
    if args.check_relevance is not None:
        print("true" if check_relevance(args.check_relevance) else "false")
        return 0

    if not args.candidate_root:
        parser.error("--candidate-root is required for validation mode")
    root = args.candidate_root.resolve()
    if not root.is_dir():
        print(f"ERROR: candidate root not found: {root}", file=sys.stderr)
        return 2

    base: Path | None = None
    if args.base_root:
        base = args.base_root.resolve()
        if not base.is_dir():
            print(f"ERROR: base root not found: {base}", file=sys.stderr)
            return 2

    all_errors: list[str] = []
    vendor = root / ".claude" / "hooks" / "PreToolUse" / "_vendor" / "markdownlint"
    update_authorized = _is_update_authorized(
        args.pull_request_author,
        args.pull_request_sender,
        args.pull_request_action,
    )
    pins = _PINNED_ARTIFACTS

    if update_authorized and base is not None:
        candidate_pins, errs = _load_candidate_pins(root)
        _run_phase("Trusted Update Pin Table", errs)
        all_errors.extend(errs)
        if candidate_pins is not None:
            pins = candidate_pins

    # 0a. Path-component symlink bypass check (before any file reads)
    errs = _check_path_component_symlinks(root)
    _run_phase("Path Component Symlinks", errs)
    all_errors.extend(errs)

    # 0b. Trust-anchor self-protection (workflow/validator immutability)
    errs = _check_trust_anchor_integrity(
        root,
        base,
        allow_update=update_authorized,
    )
    _run_phase("Trust-Anchor Self-Protection", errs)
    all_errors.extend(errs)

    # 0c. Reject .claude/settings.local.json
    errs = _reject_settings_local(root)
    _run_phase("Settings Local Rejection", errs)
    all_errors.extend(errs)

    # 0d. Reject gitlinks (submodules) in candidate tree
    if args.pr_sha:
        errs = _reject_gitlinks(args.pr_sha)
        _run_phase("Gitlink Rejection", errs)
        all_errors.extend(errs)

    # 1. Authenticate pinned artifacts (including vendor deletion check)
    errs = _authenticate_pinned(root, base, pins)
    _run_phase("Trust-Anchor Authentication", errs)
    all_errors.extend(errs)

    # 2. Flag unpinned executables
    errs = _check_unpinned_executables(root, pins)
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

    # 5. Symlink containment
    errs = _check_symlink_containment(vendor)
    _run_phase("Symlink Containment", errs)
    all_errors.extend(errs)

    # 6. Integrity manifest
    errs = _validate_integrity_manifest(vendor)
    _run_phase("Integrity Manifest", errs)
    all_errors.extend(errs)

    # 7. Markdownlint config injection
    errs = _reject_markdownlint_config_injection(root)
    _run_phase("Markdownlint Config Injection", errs)
    all_errors.extend(errs)

    # 8. Markdownlint content policy
    errs = _validate_markdownlint_config_policy(root)
    _run_phase("Markdownlint Config Policy", errs)
    all_errors.extend(errs)

    # 9. .npmrc rejection
    errs = _reject_npmrc(root, vendor)
    _run_phase(".npmrc Rejection", errs)
    all_errors.extend(errs)

    # 10. Vendor reconstruction (npm ci)
    # ABORT if any preflight error: never execute npm with tainted inputs.
    if all_errors:
        print("\n  SKIP: Vendor reconstruction skipped (preflight errors)")
    else:
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
