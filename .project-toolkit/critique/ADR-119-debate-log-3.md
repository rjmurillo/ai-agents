# ADR Debate Log: ADR-119 Decision 11, GitHub Copilot Runs the Shipped Agents

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-119-debate-log-2.md` (closed by consensus)
- **Outcome**: Consensus
- **Final Status**: proposed
- **Records covered**: ADR-119 (decision 11, an owner directive), ADR-111 (dated amendment: rules 2 and 3 bind Claude agents only), ADR-080 (dated amendment: the `code-reviewer` pin is gone, 7 remain).
- **Panel**: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the delta changes model-pin enforcement and the generator's allowed outputs.
- **Owner directive, 2026-10-17**: the owner asked why `.github/` differed from what ships ("that means we're not using what we're shipping") and then said "drop the code-reviewer agent model pin". The panel reviewed consequences and implementation, not the directive.

## Round 1 Summary

### Key Issues Addressed

- architect (P1): ADR-111 and ADR-080 were not cross-referenced. Fix: dated notes in both, and ADR-119 Related Decisions names them.
- critic (P1): `check_skill_md_portability.py` drifted after the contract-skill edit (38 to 37 suppressed refs). Fix: baseline tightened with the documented updater, 1644 to 1643 suppressed refs; the check exits 0.
- critic, high-level-advisor (P1): loading of linked `.github/agents` on the github.com cloud agent and in VS Code was unverified and unstated. Fix: a Negative consequence names it, with a post-merge check and Reversibility step 4 as the rollback.
- independent-thinker (P1): "GitHub rejects `model:`" overstated issue #4938. PR #5040 (commit `63b94de85`) shows unrecognized values silently fall back and that the tree was made inherit-only. Fix: the wording now says inherit-only per PR #5040 everywhere it appeared.
- analyst (P1): the `code-reviewer` body still said it was pinned to `haiku`. Fix: the shared body, the partial, and both golden fixtures now say it inherits the harness default.
- P2 items fixed: Copilot-only pin drop recorded as a rejected alternative; cost consequence stated; reverse-direction link test (only `pr-comment-responder.prompt.md` and `security/` are real entries); `hooks.json` link target pinned, `memory-recall.json` asserted real, and the shipped `hooks` map asserted empty until a link-loading probe is recorded; Reversibility step 4 deletes the new `agents-github` row; Windows consequence names the new links; stale comments fixed in `detect_agent_drift.py`, `sync_slim_agents.py`, `validate_install_parity.py`, `build/AGENTS.md`, `validate-generated-agents.yml`, and the architecture-contract skill template.
- Deferred by choice: a generator-level refusal of Copilot agent pins. `check_model_pins.py` scans `.github/agents/*.md` through the links, and `test_github_agents_link_to_shipped_copilot_agents_without_a_model_pin` fails on any pin, so the surface is gated after render.

### Major Changes Made

- ADR-119 decision 11 text, consequences, alternatives, reversibility, related decisions; ADR-111 and ADR-080 dated notes; tests and comments above.

### Agent Positions

| Agent | Round 1 | Round 2 |
|-------|---------|---------|
| architect | Accept | Accept |
| critic | Accept | Accept |
| independent-thinker | Accept | Accept |
| security | Accept | Accept |
| analyst | Accept | Accept |
| high-level-advisor | Accept | Accept |

## Round 2 Summary

### Key Issues Addressed

Every seat verified its round-1 findings against files and commands and marked all P1 items resolved. Remaining P2 items, fixed after the vote: ADR-111's trailing rule-3 paragraph now says no template sets `model_tier` on a Copilot agent; `validate_install_parity.py` says the trees link; ADR-119 says a Claude-only pin would need a later owner decision. Left as is: `.github/AGENTS.md` instruction counts, which predate this change.

### Major Changes Made

- The P2 wording fixes above. No P1 change followed the vote.

### Next Steps

None blocking. After merge, list the custom agents in a github.com cloud-agent session to confirm linked `.github/agents` load there. Status stays `proposed` until the owner accepts.
