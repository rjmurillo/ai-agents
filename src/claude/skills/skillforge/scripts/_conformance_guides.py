"""The agentskills.io conformance catalog: rules from the skill-creation guides.

The specification rules and the Rule type live in _conformance_rules.py.
"""

from __future__ import annotations

import _conformance_files as f
from _conformance_rules import DESCRIPTIONS, EVALS, PRACTICES, SCRIPTS, Rule

_PEP723 = (
    "Shipped scripts run on python3 and the standard library only, so they carry no "
    "PEP 723 dependency block and no runner such as uv."
)
_PLUGIN_ROOT = (
    "Project skills run scripts through the plugin-root locator, because the agent's "
    "working directory is not the skill directory."
)

GUIDE_RULES: tuple[Rule, ...] = (
    # Using scripts guide ----------------------------------------------------
    Rule(
        "scripts.pinned-one-off",
        "SHOULD",
        f"{SCRIPTS}#one-off-commands",
        "One-off uvx, npx, bunx, pipx, deno, and go commands pin a version.",
        f.scripts_pinned_one_off,
    ),
    Rule(
        "scripts.listed-in-skill-md",
        "SHOULD",
        f"{SCRIPTS}#referencing-scripts-from-skill-md",
        "SKILL.md names every entry script so the agent knows it exists.",
        f.scripts_listed,
    ),
    Rule(
        "scripts.relative-paths",
        "SHOULD",
        f"{SCRIPTS}#referencing-scripts-from-skill-md",
        "SKILL.md runs bundled scripts by paths relative to the skill root.",
        deviation=_PLUGIN_ROOT,
    ),
    Rule(
        "scripts.inline-dependencies",
        "MAY",
        f"{SCRIPTS}#self-contained-scripts",
        "A script declares its dependencies inline (PEP 723 or the language equivalent).",
        deviation=_PEP723,
    ),
    Rule(
        "scripts.no-interactive-prompts",
        "SHOULD",
        f"{SCRIPTS}#avoid-interactive-prompts",
        "Scripts take input from flags, environment, or stdin, never an interactive prompt.",
        f.scripts_no_prompts,
    ),
    Rule(
        "scripts.help",
        "SHOULD",
        f"{SCRIPTS}#document-usage-with---help",
        "Each entry script documents its usage through --help.",
        f.scripts_help,
    ),
    Rule(
        "scripts.helpful-errors",
        "SHOULD",
        f"{SCRIPTS}#write-helpful-error-messages",
        "Errors say what went wrong, what was expected, and what to try.",
    ),
    Rule(
        "scripts.structured-output",
        "SHOULD",
        f"{SCRIPTS}#use-structured-output",
        "Data goes to stdout in a structured format; diagnostics go to stderr.",
    ),
    Rule(
        "scripts.idempotent",
        "SHOULD",
        f"{SCRIPTS}#further-considerations",
        "A retried command is safe: create if missing, not fail on duplicate.",
    ),
    Rule(
        "scripts.input-constraints",
        "SHOULD",
        f"{SCRIPTS}#further-considerations",
        "Ambiguous input is rejected with a clear error instead of guessed.",
    ),
    Rule(
        "scripts.dry-run",
        "SHOULD",
        f"{SCRIPTS}#further-considerations",
        "Destructive or stateful operations offer --dry-run.",
    ),
    Rule(
        "scripts.exit-codes",
        "SHOULD",
        f"{SCRIPTS}#further-considerations",
        "Each entry script documents its exit codes where --help or its header shows them.",
        f.scripts_exit_codes_documented,
    ),
    Rule(
        "scripts.safe-defaults",
        "SHOULD",
        f"{SCRIPTS}#further-considerations",
        "Destructive operations need an explicit flag such as --confirm or --force.",
    ),
    Rule(
        "scripts.output-size",
        "SHOULD",
        f"{SCRIPTS}#further-considerations",
        "Large output defaults to a summary or a limit, with flags to get more.",
    ),
    # Best practices guide -----------------------------------------------------
    Rule(
        "practice.real-expertise",
        "SHOULD",
        f"{PRACTICES}#start-from-real-expertise",
        "The skill comes from a real task or project artifacts, not generic knowledge.",
    ),
    Rule(
        "practice.refine-with-execution",
        "SHOULD",
        f"{PRACTICES}#refine-with-real-execution",
        "The skill was run on real tasks and revised from the execution traces.",
    ),
    Rule(
        "practice.add-what-agent-lacks",
        "SHOULD",
        f"{PRACTICES}#add-what-the-agent-lacks-omit-what-it-knows",
        "Instructions add what the agent lacks and omit what it already knows.",
    ),
    Rule(
        "practice.coherent-unit",
        "SHOULD",
        f"{PRACTICES}#design-coherent-units",
        "The skill covers one coherent unit of work, neither too narrow nor too broad.",
    ),
    Rule(
        "practice.moderate-detail",
        "SHOULD",
        f"{PRACTICES}#aim-for-moderate-detail",
        "Instructions are detailed enough to act on, without exhaustive coverage.",
    ),
    Rule(
        "practice.load-conditions",
        "SHOULD",
        f"{PRACTICES}#structure-large-skills-with-progressive-disclosure",
        "SKILL.md tells the agent when to load each reference file.",
    ),
    Rule(
        "practice.match-specificity",
        "SHOULD",
        f"{PRACTICES}#match-specificity-to-fragility",
        "Fragile steps are prescriptive; flexible steps explain the goal.",
    ),
    Rule(
        "practice.defaults-not-menus",
        "SHOULD",
        f"{PRACTICES}#provide-defaults-not-menus",
        "The skill picks a default tool or approach instead of listing equal options.",
    ),
    Rule(
        "practice.procedures",
        "SHOULD",
        f"{PRACTICES}#favor-procedures-over-declarations",
        "The skill teaches how to approach a class of problems, not one answer.",
    ),
    Rule(
        "practice.gotchas",
        "SHOULD",
        f"{PRACTICES}#gotchas-sections",
        "Environment facts that defy reasonable assumptions sit in a Gotchas section.",
    ),
    Rule(
        "practice.output-templates",
        "SHOULD",
        f"{PRACTICES}#templates-for-output-format",
        "A required output format comes with a concrete template.",
    ),
    Rule(
        "practice.checklists",
        "SHOULD",
        f"{PRACTICES}#checklists-for-multi-step-workflows",
        "Multi-step workflows come with a checklist the agent can track.",
    ),
    Rule(
        "practice.validation-loops",
        "SHOULD",
        f"{PRACTICES}#validation-loops",
        "The agent validates its own work and fixes issues before moving on.",
    ),
    Rule(
        "practice.plan-validate-execute",
        "SHOULD",
        f"{PRACTICES}#plan-validate-execute",
        "Batch or destructive work drafts a plan, validates it, then executes.",
    ),
    Rule(
        "practice.bundle-scripts",
        "SHOULD",
        f"{PRACTICES}#bundling-reusable-scripts",
        "Logic the agent reinvents on every run becomes a bundled, tested script.",
    ),
    # Optimizing descriptions guide ------------------------------------------
    Rule(
        "description.imperative",
        "SHOULD",
        f"{DESCRIPTIONS}#writing-effective-descriptions",
        "The description is phrased as an instruction: 'Use this skill when...'.",
    ),
    Rule(
        "description.user-intent",
        "SHOULD",
        f"{DESCRIPTIONS}#writing-effective-descriptions",
        "The description names what the user wants, not the skill's internals.",
    ),
    Rule(
        "description.pushy",
        "SHOULD",
        f"{DESCRIPTIONS}#writing-effective-descriptions",
        "The description lists contexts where the skill applies, even unnamed ones.",
    ),
    Rule(
        "description.concise",
        "SHOULD",
        f"{DESCRIPTIONS}#writing-effective-descriptions",
        "The description is a few sentences to a short paragraph.",
    ),
    Rule(
        "description.trigger-evals",
        "SHOULD",
        f"{DESCRIPTIONS}#designing-trigger-eval-queries",
        "About 20 trigger queries, 8 to 10 should trigger and 8 to 10 near-misses should not.",
    ),
    Rule(
        "description.repeat-runs",
        "SHOULD",
        f"{DESCRIPTIONS}#running-multiple-times",
        "Each trigger query runs several times and reports a trigger rate.",
    ),
    Rule(
        "description.train-validation-split",
        "SHOULD",
        f"{DESCRIPTIONS}#avoiding-overfitting-with-train-validation-splits",
        "Description changes are tuned on a train split and judged on a held-out split.",
    ),
    # Evaluating skills guide ------------------------------------------------
    Rule(
        "evals.file-shape",
        "SHOULD",
        f"{EVALS}#designing-test-cases",
        "evals/evals.json, when present, has skill_name and evals with id, prompt, "
        "expected_output, existing files, and string assertions.",
        f.evals_file_shape,
    ),
    Rule(
        "evals.realistic-prompts",
        "SHOULD",
        f"{EVALS}#designing-test-cases",
        "Eval prompts read like real user requests, with varied phrasing and detail.",
    ),
    Rule(
        "evals.baseline",
        "SHOULD",
        f"{EVALS}#running-evals",
        "Each eval runs with the skill and without it (or with the previous version).",
    ),
    Rule(
        "evals.clean-context",
        "SHOULD",
        f"{EVALS}#spawning-runs",
        "Each eval run starts from a clean context with no leftover state.",
    ),
    Rule(
        "evals.timing",
        "SHOULD",
        f"{EVALS}#capturing-timing-data",
        "Runs record tokens and duration, so cost is compared with quality.",
    ),
    Rule(
        "evals.verifiable-assertions",
        "SHOULD",
        f"{EVALS}#writing-assertions",
        "Assertions are specific and checkable, scripted where a script can check them.",
    ),
    Rule(
        "evals.grading-evidence",
        "SHOULD",
        f"{EVALS}#grading-principles",
        "Each PASS or FAIL cites concrete evidence from the output.",
    ),
    Rule(
        "evals.aggregate",
        "SHOULD",
        f"{EVALS}#aggregating-results",
        "Results aggregate into pass rate, time, and tokens, with the delta.",
    ),
    Rule(
        "evals.human-review",
        "SHOULD",
        f"{EVALS}#reviewing-results-with-a-human",
        "A human reviews outputs and records feedback the assertions missed.",
    ),
)
