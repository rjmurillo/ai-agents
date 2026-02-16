# Skill Activation Observations

**Last Updated**: 2026-02-07
**Sessions Analyzed**: 30+ (session 1183 meta-analysis)

## Constraints (HIGH confidence)

- Before EVERY operation (git, gh, script), check: "Is there a skill for this?" Negative framing ("never use raw commands") fails. Positive checkpoint succeeds. (Session 1183, 2026-02-07)
- The activation problem has TWO components: (1) trigger phrase matching AND (2) agent decision-making habit. Fixing triggers alone is insufficient. Even with perfect catalog knowledge, agents default to raw commands. (Session 1183, 2026-02-07)
- Skills have 0% natural language activation rate. Users rely entirely on slash commands. Top user verbs (run, review, create, commit, fix, check) are missing from most triggers. (Session 1183, 2026-02-07)

## Preferences (MED confidence)

- Before any git, gh, or script operation, explicitly check SKILL-QUICK-REF.md "User Phrasing → Skill" mapping. Include this check in the reasoning process, not just as passive knowledge. (Session 1183, 2026-02-07)
- Trigger phrases should use verb-object patterns ("create PR" not "PR creation") matching actual user language. (Session 1183, 2026-02-07)
- Auto-triggers (context-based like URL detection) outperform phrase matching. 100% vs 0% success rate. (Session 1183, 2026-02-07)

## Edge Cases (MED confidence)

- Skills won't activate naturally even when the agent knows they exist. Requires deliberate habit formation, not just better triggers. (Session 1183, 2026-02-07)
- 83% of skills (35/42) have never been activated in 30 sessions. Discovery is a systemic failure. (Session 1183, 2026-02-07)
- Users request workflows ("run PR review workflow"), skills provide atomic operations. No skill chains multiple operations. (Session 1183, 2026-02-07)

## Notes for Review (LOW confidence)

- Consider creating a workflow-executor skill that chains multiple skills based on user intent. (Session 1183, 2026-02-07)
- A /skills list command would improve discovery. (Session 1183, 2026-02-07)
