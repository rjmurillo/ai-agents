# ADR Debate Log: ADR-123 amendment, artifact-keyed declarations

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-123-debate-log.md` (closed, consensus)
- **Outcome**: Consensus
- **Final Status**: accepted

The amendment changes Decision item 1 from lists of mappings to mappings keyed by artifact name.
Reason: `skillforge`'s stdlib frontmatter parser refuses flow mappings and mappings inside a sequence.
The first schema made conformance report NOT_EVALUATED on 16 of 110 skills at `b8bedf583`.
The change touches executable enforcement, so the full panel ran.

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Disagree-and-Commit |
| independent-thinker | Disagree-and-Commit |
| security | Disagree-and-Commit |
| analyst | Disagree-and-Commit (conditional on measuring the 16; measured) |
| high-level-advisor | Accept |

Every seat agreed the schema must move rather than the parser.
No seat disputed the maintainer's choice of typed, `yq`-queryable `inputs` and `outputs`.

### Key Issues Addressed

| # | Issue | Raised by | Pri | Resolution |
|---|-------|-----------|-----|------------|
| 1 | Mixed-type option keys crash `sorted()` in the gate, breaking "a defect, not a crash". | critic, security | P1 | Unknown keys sort with `key=repr`. Test `test_mixed_type_option_keys_are_a_defect_not_a_crash`. |
| 2 | A quoted key passes PyYAML but the shipped subset parser refuses it. | critic | P1 | The gate now parses each template with `skillforge`'s `_conformance_parse` and refuses what it cannot read. Tests cover quoted keys and flow collections. |
| 3 | `artifact` stayed an allowed option key from the list shape. | analyst | P1 | Removed from both option sets. Test `test_artifact_is_no_longer_an_option_key`. |
| 4 | The "16 skills" count lacked a cited measurement; one seat counted 13. | analyst, independent-thinker | P1 | Measured: `load_skill` fails on 16 of 110 skills at `b8bedf583`. Thirteen were artifact declarations and three were one-line `capability` blocks. The ADR says both. |
| 5 | Raw keys in messages could forge log lines. | security | P2 | Messages print names with `repr()`. |
| 6 | `yes`, `no`, `on`, `off` read as YAML 1.1 booleans. | critic | P2 | The gate names the cause. Parametrized test added. |
| 7 | `~` and `null` read as text in the stdlib parser. | critic | P2 | ADR says to write nothing after the colon for an empty entry. |
| 8 | A self-produced input is not flagged. | critic | P2 | Behavior recorded in `test_a_skill_may_read_an_artifact_it_also_produces`. |
| 9 | Corpus guard missed `src/codex`, `src/cursor`, `src/muse`. | architect, critic, analyst | P2 | All five shipped trees are guarded. |
| 10 | No Rationale row for extending the parser. | architect, independent-thinker | P2 | Row added: rejected, because the subset is deliberate and ships to consumers. |
| 11 | One skill cannot list one artifact under two sources. | architect | P2 | Stated in item 1. |
| 12 | The stdlib parser reads `required: false` as text. | high-level-advisor | P2 | Item 7 states the gate does the type checks. |

### Dissent Carried

None beyond the prior log's carried dissent on generating the Handoff line.

### Noticed Outside Scope

- Conformance `spec.frontmatter.known-fields` already fails on project fields (`argument-hint`, `user-invocable`, `version`). It predates ADR-123 and the project profile reports it as a deviation.
- `spec.metadata.string-map` warns on any nested `metadata` value, as it already did for `capability` and `routing`.
