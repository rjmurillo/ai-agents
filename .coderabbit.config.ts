// CodeRabbit configuration for the ai-agents repository.
//
// This file states the full effective review config for this repository:
// the settings that used to live in .coderabbit.yaml, plus the organization
// path instructions, tone, and title conventions inherited from the
// CodeRabbit dashboard. CodeRabbit reads this file only when no
// .coderabbit.yaml exists, so do not add one back.
//
// CodeRabbit evaluates this file on its servers, so the @coderabbitai/config
// package is needed only for editor types. It is not a repo dependency.
//
// With inheritance on, CodeRabbit matches path_instructions entries by
// `path`. An entry here replaces the dashboard entry with the same path, so
// no rule applies twice. An empty array here takes the dashboard array.
// Source: https://docs.coderabbit.ai/configuration/configuration-inheritance
//
// Noise tuning comes from Issue #326: fewer than 20 comments per PR,
// high-confidence findings only, generated files and agent artifacts skipped.

import { defineConfig } from "@coderabbitai/config";

interface ReviewRule {
  /** Glob the instructions apply to. Each path appears once. */
  readonly path: string;
  /** Review instructions for files that match `path`. */
  readonly instructions: string;
  /**
   * Optional guideline document the rule enforces. When set, the rule also
   * becomes a knowledge-base code guideline entry ({ files, applyTo: path }).
   */
  readonly files?: string;
}

// One table states each rule once. It generates both reviews.path_instructions
// and knowledge_base.code_guidelines.filePatterns.
//
// Order: the repository rule first, then the organization rules in dashboard
// order. The dashboard held two .githooks/** entries; they are merged here
// into one rule because path instructions match by path.
const RULES: readonly ReviewRule[] = [
  {
    path: "src/claude/**/*.md",
    instructions: `## Agent Prompt Review Criteria
### P0 (Must Fix)
- Missing required Front Matter
- Model assignment violating ADR-002
- Absolute paths in documentation
### P1 (Should Fix)
- Missing Core Identity section
- Drift from VS Code/Copilot CLI versions
Prefix all comments with: [P0] or [P1]

Only comment when you have HIGH CONFIDENCE (>80%) that an issue exists.
Be concise: one sentence per comment when possible.
Focus on actionable feedback, not observations.
If uncertain whether something is an issue, do not comment.
`,
  },
  {
    path: ".agents/**",
    instructions: `Agent configuration files.
Only flag security issues or broken cross-references.
Ignore style, formatting, and structure.
`,
  },
  {
    path: ".github/workflows/**",
    instructions: `SECURITY-CRITICAL PATH. Apply assertive enforcement.
Focus on: authentication and secrets handling, OIDC, credential exposure, injection, race conditions, and resource exhaustion.
Flag: unquoted variables, direct user input in scripts, missing error handling, hardcoded secrets, and unsafe third-party actions.
Do not ignore security findings on this path.
`,
  },
  {
    path: ".githooks/**",
    instructions: `SECURITY-CRITICAL PATH. Apply assertive enforcement.
Focus on: code execution safety, symlink TOCTOU, credential exposure, privilege escalation, and DoS.

GitHub Actions criteria:
### P0
- CWE-78 script injection via github.event body
- Secrets in logs
- Missing permissions block
- Unpinned actions
### P1
- Missing timeout-minutes
- Missing concurrency group

Git hook criteria:
### P0
- CWE-78 unquoted variables
- Missing exit code propagation
### P1
- AUTO-FIX sections missing an AUTOFIX check
- PowerShell calls without exit verification

Prefix all comments with: [P0], [P1], or [P2]
`,
  },
  {
    path: "**/*.cs",
    instructions: `Review against the Software Hierarchy of Needs.
Qualities: testability, cohesion, coupling (only identity coupling is acceptable by default), DRY, and encapsulation (flag public fields).
Principles: open-closed, separate use from creation, separation of concerns, and the Law of Demeter.
Abstraction quality (CVA): flag wrong, missing, and leaky abstractions.
Security: CWE-78, CWE-79, CWE-89, trust boundaries, and resource leaks.
Performance: allocations in hot paths, boxing, LINQ in tight loops, missing ConfigureAwait(false), and sync-over-async.
Limits: cyclomatic complexity over 10, methods over 60 lines, and deep nesting.
Ignore: style and formatting (dotnet format), naming (analyzers), and XML doc completeness.
`,
  },
  {
    path: "**/*Test*.cs",
    instructions: `Coverage: all new or changed code paths need tests. Flag missing edge, null, empty, and boundary cases.
Quality: arrange-act-assert, one assertion concept per test, names that describe behavior, mock only what you must, and prefer fakes.
Flag: tests of implementation details, complex setup, missing failure cases, commented-out tests, and sync-over-async.
Ignore: naming style and file organization.
`,
  },
  {
    path: "**/*.md",
    instructions: `Writing quality: grade 9 reading level, active voice, short sentences under 25 words, and simple words.
Flag: passive voice, vague statements, unexplained jargon, and sentences over 30 words.
Ignore: markdown formatting and link format.
### P0
- Absolute paths
- Broken links
### P1
- Relative links
- Outdated docs
`,
  },
  {
    path: "**/ADR-*.md",
    instructions: `Required sections: Status, Context, Decision, Consequences, and Alternatives Considered.
Flag: missing sections, vague decisions, and missing consequences or alternatives.
Superseded ADRs must be marked as superseded and cross-referenced.
`,
  },
  {
    path: "**/README.md",
    instructions: `A project root README needs: a one-paragraph description, a quick start, prerequisites, and build and test commands.
Flag: outdated instructions, missing prerequisites, broken links, and conflicts with the actual setup.
`,
  },
  {
    path: "**/*.{props,targets}",
    instructions: `Only flag breaking changes to build or packaging.
Verify that such changes are intentional and documented.
Ignore formatting and ordering.
`,
  },
  {
    path: "**/*.csproj",
    instructions: `Target .NET 10 and C# 14 unless overridden. Analyzers target .NET Standard 2.0.
Only flag: missing or incompatible dependencies, package vulnerabilities, breaking TFM changes, and duplicate or conflicting references.
Ignore ordering and formatting.
`,
  },
  {
    path: "**/Benchmarks/**",
    instructions: `Check measurement validity.
Flag: allocation regressions, missing baselines, and wrong methodology.
Verify BenchmarkDotNet attributes.
`,
  },
  {
    path: "**/*.ps1",
    instructions: `### P0
- CWE-78: Invoke-Expression with user input
- CWE-20: missing ValidateScript on external input
- CWE-22: path concatenation without normalization
- Hardcoded secrets
### P1
- Missing error handling
- Functions over 60 lines
Skip test coverage.
Prefix all comments with: [P0], [P1], or [P2]
`,
  },
  {
    path: "**/*.Tests.ps1",
    instructions: `### P0
- Tests that modify global state without cleanup
- Hardcoded paths (use $PSScriptRoot)
### P1
- Non-descriptive test names
Skip coverage percentage.
Prefix all comments with: [P0], [P1], or [P2]
`,
  },
];

export default defineConfig({
  // Merge organization defaults for any key this file leaves unset.
  inheritance: true,

  // Organization tone convention.
  tone_instructions:
    "Be direct. Grade 9 reading level. No pleasantries. Flag issues that matter. Ignore style and formatting handled by dotnet format and analyzers.",

  issue_enrichment: {
    auto_enrich: {
      enabled: false,
    },
  },

  reviews: {
    // "chill" reduces nitpicky feedback.
    profile: "chill",

    // Skip generated files and agent artifacts.
    path_filters: [
      "!.project-toolkit/sessions/**",
      "!.project-toolkit/analysis/**",
      "!.serena/memories/**",
      "!**/*.generated.*",
      "!**/bin/**",
      "!**/obj/**",
    ],

    // Less supplementary content.
    collapse_walkthrough: true,
    poem: false,
    related_issues: false,
    related_prs: false,

    // Organization title convention.
    auto_title_instructions: "Use conventional commit format",

    auto_review: {
      base_branches: ["main", "develop"],
      labels: ["feature", "enhancement", "priority:P0"],
    },

    pre_merge_checks: {
      title: {
        mode: "warning",
        requirements: "Use conventional commit format",
      },
    },

    tools: {
      // .markdownlint-cli2.yaml owns markdown linting.
      markdownlint: {
        enabled: false,
      },
    },

    path_instructions: RULES.map(({ path, instructions }) => ({ path, instructions })),
  },

  knowledge_base: {
    code_guidelines: {
      filePatterns: RULES.flatMap(({ path, files }) =>
        files === undefined ? [] : [{ files, applyTo: path }],
      ),
    },
  },
});
