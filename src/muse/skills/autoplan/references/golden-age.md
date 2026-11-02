# The Golden Age

Motivation behind `builder-ethos.md` section 1 (Boil the Lake). Read it when sizing a build-vs-skip decision; the binding rules stay in `builder-ethos.md`.

A single person with AI can now build what used to take a team of twenty. The engineering barrier is gone. What remains is taste, judgment, and the willingness to do the complete thing.

This is not a prediction. It is happening right now. 10,000+ usable lines of code per day. 100+ commits per week. Not by a team. By one person, part-time, using the right tools. The compression ratio between human-team time and AI-assisted time ranges from 3x (research) to 100x (boilerplate):

| Task type                   | Human team | AI-assisted | Compression |
|-----------------------------|-----------|-------------|-------------|
| Boilerplate / scaffolding   | 2 days    | 15 min      | ~100x       |
| Test writing                | 1 day     | 15 min      | ~50x        |
| Feature implementation      | 1 week    | 30 min      | ~30x        |
| Bug fix + regression test   | 4 hours   | 15 min      | ~20x        |
| Architecture / design       | 2 days    | 4 hours     | ~5x         |
| Research / exploration      | 1 day     | 3 hours     | ~3x         |

This table changes everything about how you make build-vs-skip decisions. The last 10% of completeness that teams used to skip? It costs seconds now.

This table prices one task the user picked and says nothing about how many tasks run.

## Build for Yourself

The best tools solve your own problem. gstack exists because its creator wanted it. Every feature was built because it was needed, not because it was requested. If you're building something for yourself, trust that instinct. The specificity of a real problem beats the generality of a hypothetical one every time.

This section describes the human user's posture toward the project, not the agent's. When the AI is helping the user-who-is-the-builder, both lenses point the same way.
