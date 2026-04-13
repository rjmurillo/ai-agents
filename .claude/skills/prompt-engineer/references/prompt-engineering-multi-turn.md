# Prompt Engineering: Research-Backed Techniques for Multi-Turn Prompts

This document synthesizes practical prompt engineering patterns with academic research on iterative LLM reasoning. All techniques target **multi-turn prompts**—structured sequences of messages where output from one turn becomes input to subsequent turns. These techniques leverage the observation that models can improve their own outputs through deliberate self-examination across multiple passes.

**Prerequisite**: This guide assumes familiarity with single-turn techniques (CoT, Plan-and-Solve, RE2, etc.). Multi-turn techniques often enhance or extend single-turn methods across message boundaries.

**Meta-principle**: The value of multi-turn prompting comes from separation of concerns—each turn has a distinct cognitive goal (generate, critique, verify, synthesize). Mixing these goals within a single turn reduces effectiveness.

---

## Technique Selection Guide

| Domain              | Technique                  | Trigger Condition                                      | Stacks With                          | Conflicts With             | Cost/Tradeoff                                  | Effect                                                             |
| ------------------- | -------------------------- | ------------------------------------------------------ | ------------------------------------ | -------------------------- | ---------------------------------------------- | ------------------------------------------------------------------ |
| **Refinement**      | Self-Refine                | Output quality improvable through iteration            | Any single-turn reasoning technique  | Time-critical tasks        | 2-4x tokens per iteration                      | 5-40% absolute improvement across 7 task types                     |
| **Refinement**      | Iterative Critique         | Specific quality dimensions need improvement           | Self-Refine, Format Strictness       | —                          | Moderate; targeted feedback reduces iterations | Monotonic improvement on scored dimensions                         |
| **Verification**    | Chain-of-Verification      | Factual accuracy critical; hallucination risk          | Quote Extraction (single-turn)       | Joint verification         | 3-4x tokens (baseline + verify + revise)       | List-based QA: 17%→70% accuracy; FACTSCORE: 55.9→71.4              |
| **Verification**    | Factored Verification      | High hallucination persistence in joint verification   | CoVe                                 | Joint CoVe                 | Additional token cost for separation           | Outperforms joint CoVe by 3-8 points across tasks                  |
| **Aggregation**     | Universal Self-Consistency | Free-form output; standard SC inapplicable             | Any sampling technique               | Greedy decoding            | N samples + 1 selection call                   | Matches SC on math; enables SC for open-ended tasks                |
| **Aggregation**     | Multi-Chain Reasoning      | Evidence scattered across reasoning attempts           | Self-Consistency, CoT                | Single-chain reliance      | N chains + 1 meta-reasoning call               | +5.7% over SC on multi-hop QA; high-quality explanations           |
| **Aggregation**     | Complexity-Weighted Voting | Varying reasoning depth across samples                 | Self-Consistency, USC                | Simple majority voting     | Minimal; selection strategy only               | Further gains over standard SC (+2-3 points)                       |
| **Meta-Reasoning**  | Chain Synthesis            | Multiple valid reasoning paths exist                   | MCR, USC                             | —                          | Moderate; synthesis pass                       | Combines complementary facts from different chains                 |
| **Meta-Reasoning**  | Explanation Generation     | Interpretability required alongside answer             | MCR                                  | —                          | Included in meta-reasoning pass                | 82% of explanations rated high-quality                             |

---

## Quick Reference: Key Principles

1. **Self-Refine for Iterative Improvement** — Feedback must be actionable ("use the formula n(n+1)/2") and specific ("the for loop is brute force"); vague feedback fails
2. **Separate Feedback from Refinement** — Generate feedback in one turn, apply it in another; mixing degrades both
3. **Factored Verification Beats Joint** — Answer verification questions without attending to the original response; prevents hallucination copying
4. **Shortform Questions Beat Longform** — 70% accuracy on individual verification questions vs. 17% for the same facts in longform generation
5. **Universal Self-Consistency for Free-Form** — When answers can't be exactly matched, ask the LLM to select the most consistent response
6. **Multi-Chain Reasoning for Evidence Collection** — Use reasoning chains as evidence sources, not just answer votes
7. **Meta-Reasoning Over Chains** — A second model pass that reads all chains produces better answers than majority voting
8. **Complexity-Weighted Voting** — Vote over complex chains only; simple chains may reflect shortcuts
9. **History Accumulation Helps** — Retain previous feedback and outputs in refinement prompts; models learn from past mistakes
10. **Open Questions Beat Yes/No** — Verification questions expecting factual answers outperform yes/no format
11. **Stopping Conditions Matter** — Use explicit quality thresholds or iteration limits; models rarely self-terminate optimally
12. **Non-Monotonic Improvement Possible** — Multi-aspect tasks may improve on one dimension while regressing on another; track best-so-far

---

## 1. Iterative Refinement

Techniques where the model critiques and improves its own output across multiple turns.

### Self-Refine

A general-purpose iterative improvement framework. Per Madaan et al. (2023): "SELF-REFINE: an iterative self-refinement algorithm that alternates between two generative steps—FEEDBACK and REFINE. These steps work in tandem to generate high-quality outputs."

**The core loop:**

```
Turn 1 (Generate):
  Input: Task description + prompt
  Output: Initial response y₀

Turn 2 (Feedback):
  Input: Task + y₀ + feedback prompt
  Output: Actionable, specific feedback fb₀

Turn 3 (Refine):
  Input: Task + y₀ + fb₀ + refine prompt
  Output: Improved response y₁

[Iterate until stopping condition]
```

**Critical quality requirements for feedback:**

Per the paper: "By 'actionable', we mean the feedback should contain a concrete action that would likely improve the output. By 'specific', we mean the feedback should identify concrete phrases in the output to change."

**CORRECT feedback (actionable + specific):**

```
This code is slow as it uses a for loop which is brute force.
A better approach is to use the formula n(n+1)/2 instead of iterating.
```

**INCORRECT feedback (vague):**

```
The code could be more efficient. Consider optimizing it.
```

**History accumulation improves refinement:**

The refinement prompt should include all previous iterations. Per the paper: "To inform the model about the previous iterations, we retain the history of previous feedback and outputs by appending them to the prompt. Intuitively, this allows the model to learn from past mistakes and avoid repeating them."

```
Turn N (Refine with history):
  Input: Task + y₀ + fb₀ + y₁ + fb₁ + ... + yₙ₋₁ + fbₙ₋₁
  Output: Improved response yₙ
```

**Performance:** "SELF-REFINE outperforms direct generation from strong LLMs like GPT-3.5 and GPT-4 by 5-40% absolute improvement" across dialogue response generation, code optimization, code readability, math reasoning, sentiment reversal, acronym generation, and constrained generation.

**When Self-Refine works best:**

| Task Type                   | Improvement | Notes                                        |
| --------------------------- | ----------- | -------------------------------------------- |
| Code optimization           | +13%        | Clear optimization criteria                  |
| Dialogue response           | +35-40%     | Multi-aspect quality (relevance, engagement) |
| Constrained generation      | +20%        | Verifiable constraint satisfaction           |
| Math reasoning (with oracle) | +4.8%      | Requires correctness signal                  |

**Limitation — Non-monotonic improvement:**

Per the paper: "For tasks with multi-aspect feedback like Acronym Generation, the output quality can fluctuate during the iterative process, improving on one aspect while losing out on another."

**Mitigation:** Track scores across iterations; select the output with maximum total score, not necessarily the final output.

---

### Feedback Prompt Design

The feedback prompt determines refinement quality. Key elements from Self-Refine experiments:

**Structure:**

```
You are given [task description] and an output.

Output: {previous_output}

Provide feedback on this output. Your feedback should:
1. Identify specific phrases or elements that need improvement
2. Explain why they are problematic
3. Suggest concrete actions to fix them

Do not rewrite the output. Only provide feedback.

Feedback:
```

**Why separation matters:** Combining feedback and rewriting in one turn degrades both. The model either produces shallow feedback to get to rewriting, or rewrites without fully analyzing problems.

---

### Refinement Prompt Design

The refinement prompt applies feedback to produce improved output.

**Structure:**

```
You are given [task description], a previous output, and feedback on that output.

Previous output: {previous_output}

Feedback: {feedback}

Using this feedback, produce an improved version of the output.
Address each point raised in the feedback.

Improved output:
```

**With history (for iteration 2+):**

```
You are given [task description], your previous attempts, and feedback on each.

Attempt 1: {y₀}
Feedback 1: {fb₀}

Attempt 2: {y₁}
Feedback 2: {fb₁}

Using all feedback, produce an improved version. Do not repeat previous mistakes.

Improved output:
```

---

### Stopping Conditions

Self-Refine requires explicit stopping conditions. Options:

1. **Fixed iterations:** Stop after N refinement cycles (typically 2-4)
2. **Feedback-based:** Prompt the model to include a stop signal in feedback
3. **Score-based:** Stop when quality score exceeds threshold
4. **Diminishing returns:** Stop when improvement between iterations falls below threshold

**Prompt for feedback-based stopping:**

```
Provide feedback on this output. If the output is satisfactory and needs no
further improvement, respond with "NO_REFINEMENT_NEEDED" instead of feedback.

Feedback:
```

**Warning:** Models often fail to self-terminate appropriately. Per Madaan et al.: fixed iteration limits are more reliable than self-assessed stopping.

---

## 2. Verification

Techniques where the model fact-checks its own outputs through targeted questioning.

### Chain-of-Verification (CoVe)

A structured approach to reducing hallucination through self-verification. Per Dhuliawala et al. (2023): "Chain-of-Verification (CoVe) whereby the model first (i) drafts an initial response; then (ii) plans verification questions to fact-check its draft; (iii) answers those questions independently so the answers are not biased by other responses; and (iv) generates its final verified response."

**The four-step process:**

```
Turn 1 (Baseline Response):
  Input: Original query
  Output: Initial response (may contain hallucinations)

Turn 2 (Plan Verifications):
  Input: Query + baseline response
  Output: List of verification questions

Turn 3 (Execute Verifications):
  Input: Verification questions ONLY (not baseline response)
  Output: Answers to each verification question

Turn 4 (Final Verified Response):
  Input: Query + baseline response + verification Q&A pairs
  Output: Revised response incorporating verifications
```

**The critical insight — shortform beats longform:**

Per the paper: "Shortform verification questions are more accurately answered than longform queries. In a longform response, LLMs are prone to generate a number of hallucinations. However, it can often be the case that the LLM itself would know these hallucinations are wrong if queried specifically for that individual fact, independent of the rest of the longform generation."

**Quantitative evidence:**

| Setting                       | Accuracy |
| ----------------------------- | -------- |
| Facts in longform generation  | ~17%     |
| Same facts as individual Q&A  | ~70%     |

The same model that hallucinates facts in context can correctly answer when asked directly. CoVe exploits this asymmetry.

**Example from the paper:**

```
Query: Name some politicians who were born in NY, New York.

Baseline Response (with hallucinations):
1. Hillary Clinton - former secretary of state... [WRONG: born in Chicago]
2. Donald Trump - former president... [CORRECT: born in Queens, NYC]
3. Michael Bloomberg - former Mayor... [WRONG: born in Boston]

Verification Questions:
- Where was Hillary Clinton born?
- Where was Donald Trump born?
- Where was Michael Bloomberg born?

Verification Answers:
- Hillary Clinton was born in Chicago, Illinois
- Donald Trump was born in Queens, New York City
- Michael Bloomberg was born in Boston, Massachusetts

Final Verified Response:
1. Donald Trump - former president (born in Queens, NYC)
2. Alexandria Ocasio-Cortez - Democratic representative (born in NYC)
...
```

---

### Factored vs. Joint Verification

**The hallucination copying problem:**

Per Dhuliawala et al.: "Models that attend to existing hallucinations in the context from their own generations tend to repeat the hallucinations."

When verification questions are answered with the baseline response in context, the model tends to confirm its own hallucinations rather than correct them.

**Joint verification (less effective):**

```
Turn 3 (Joint):
  Input: Query + baseline response + verification questions
  Output: All answers in one pass

Problem: Model sees its original hallucinations and copies them
```

**Factored verification (more effective):**

```
Turn 3a: Answer Q1 independently (no baseline in context)
Turn 3b: Answer Q2 independently (no baseline in context)
Turn 3c: Answer Q3 independently (no baseline in context)
...
```

**2-Step verification (middle ground):**

```
Turn 3a: Generate all verification answers (no baseline in context)
Turn 3b: Cross-check answers against baseline, note inconsistencies
```

**Performance comparison (Wiki-Category task):**

| Method          | Precision |
| --------------- | --------- |
| Baseline        | 0.13      |
| Joint CoVe      | 0.15      |
| 2-Step CoVe     | 0.19      |
| Factored CoVe   | 0.22      |

Factored verification consistently outperforms joint verification by preventing hallucination propagation.

---

### Verification Question Design

**Open questions outperform yes/no:**

Per the paper: "We find that yes/no type questions perform worse for the factored version of CoVe. Some anecdotal examples... find the model tends to agree with facts in a yes/no question format whether they are right or wrong."

**CORRECT (open verification question):**

```
When did Texas secede from Mexico?
→ Expected answer: 1836
```

**INCORRECT (yes/no verification question):**

```
Did Texas secede from Mexico in 1845?
→ Model tends to agree regardless of correctness
```

**LLM-generated questions outperform heuristics:**

Per the paper: "We compare the quality of these questions to heuristically constructed ones... Results show a reduced precision with rule-based verification questions."

Let the model generate verification questions tailored to the specific response, rather than using templated questions.

---

### Factor+Revise for Complex Verification

For longform generation, add an explicit cross-check step between verification and final response.

**Structure:**

```
Turn 3 (Execute verifications): [as above]

Turn 3.5 (Cross-check):
  Input: Baseline response + verification Q&A pairs
  Output: Explicit list of inconsistencies found

Turn 4 (Final response):
  Input: Baseline + verifications + inconsistency list
  Output: Revised response
```

**Performance:** Factor+Revise achieves FACTSCORE 71.4 vs. 63.7 for factored-only, demonstrating that explicit reasoning about inconsistencies further improves accuracy.

**Prompt for cross-check:**

```
Original passage: {baseline_excerpt}

From another source:
Q: {verification_question_1}
A: {verification_answer_1}

Q: {verification_question_2}
A: {verification_answer_2}

Identify any inconsistencies between the original passage and the verified facts.
List each inconsistency explicitly.

Inconsistencies:
```

---

## 3. Aggregation and Consistency

Techniques that sample multiple responses and select or synthesize the best output.

### Universal Self-Consistency (USC)

Extends self-consistency to free-form outputs where exact-match voting is impossible. Per Chen et al. (2023): "USC leverages LLMs themselves to select the most consistent answer among multiple candidates... USC eliminates the need of designing an answer extraction process, and is applicable to tasks with free-form answers."

**The two-step process:**

```
Turn 1 (Sample):
  Input: Query
  Output: N responses sampled with temperature > 0
  [y₁, y₂, ..., yₙ]

Turn 2 (Select):
  Input: Query + all N responses
  Output: Index of most consistent response
```

**The selection prompt:**

```
I have generated the following responses to the question: {question}

Response 0: {response_0}
Response 1: {response_1}
Response 2: {response_2}
...

Select the most consistent response based on majority consensus.
The most consistent response is Response:
```

**Why this works:**

Per the paper: "Although prior works show that LLMs sometimes have trouble evaluating the prediction correctness, empirically we observe that LLMs are generally able to examine the response consistency across multiple tasks."

Assessing consistency is easier than assessing correctness. The model doesn't need to know the right answer—just which answers agree with each other most.

**Performance:**

| Task                    | Greedy | Random | USC   | Standard SC |
| ----------------------- | ------ | ------ | ----- | ----------- |
| GSM8K                   | 91.3   | 91.5   | 92.4  | 92.7        |
| MATH                    | 34.2   | 34.3   | 37.6  | 37.5        |
| TruthfulQA (free-form)  | 62.1   | 62.9   | 67.7  | N/A         |
| SummScreen (free-form)  | 30.6   | 30.2   | 31.7  | N/A         |

USC matches standard SC on structured tasks and enables consistency-based selection where SC cannot apply.

**Robustness to ordering:**

Per the paper: "The overall model performance remains similar with different response orders, suggesting the effect of response order is minimal." USC is not significantly affected by the order in which responses are presented.

**Optimal sample count:**

USC benefits from more samples up to a point, then plateaus or slightly degrades due to context length limitations. Per experiments: 8 samples is a reliable sweet spot balancing accuracy and cost.

---

### Multi-Chain Reasoning (MCR)

Uses multiple reasoning chains as evidence sources, not just answer votes. Per Yoran et al. (2023): "Unlike prior work, sampled reasoning chains are used not for their predictions (as in SC) but as a means to collect pieces of evidence from multiple chains."

**The key insight:**

Self-Consistency discards the reasoning and only votes on answers. MCR preserves the reasoning and synthesizes facts across chains.

**The three-step process:**

```
Turn 1 (Generate chains):
  Input: Query
  Output: N reasoning chains, each with intermediate steps
  [chain₁, chain₂, ..., chainₙ]

Turn 2 (Concatenate):
  Combine all chains into unified multi-chain context

Turn 3 (Meta-reason):
  Input: Query + multi-chain context
  Output: Final answer + explanation synthesizing evidence
```

**Why MCR outperforms SC:**

Per the paper: "SC solely relies on the chains' answers... By contrast, MCR concatenates the intermediate steps from each chain into a unified context, which is passed, along with the original question, to a meta-reasoner model."

**Example from the paper:**

```
Question: Did Brad Peyton need to know about seismology?

Chain 1 (Answer: No):
- Brad Peyton is a film director
- What is seismology? Seismology is the study of earthquakes
- Do film directors need to know about earthquakes? No

Chain 2 (Answer: Yes):
- Brad Peyton directed San Andreas
- San Andreas is about a massive earthquake
- [implicit: he needed to research the topic]

Chain 3 (Answer: No):
- Brad Peyton is a director, writer, and producer
- What do film directors have to know? Many things
- Is seismology one of them? No

Self-Consistency vote: No (2-1)

MCR meta-reasoning: Combines facts from all chains:
- Brad Peyton is a film director (chain 1, 3)
- He directed San Andreas (chain 2)
- San Andreas is about a massive earthquake (chain 2)
- Seismology is the study of earthquakes (chain 1)

MCR answer: Yes (synthesizes that directing an earthquake film required seismology knowledge)
```

**Performance:**

MCR outperforms SC by up to 5.7% on multi-hop QA datasets. Additionally: "MCR generates high quality explanations for over 82% of examples, while fewer than 3% are unhelpful."

---

### Complexity-Weighted Voting

An extension to self-consistency that weights votes by reasoning complexity. Per Fu et al. (2023): "We propose complexity-based consistency, where instead of taking a majority vote among all generated chains, we vote over the top K complex chains."

**The process:**

```
Turn 1 (Sample with CoT):
  Generate N reasoning chains with answers

Turn 2 (Rank by complexity):
  Count reasoning steps in each chain
  Select top K chains by step count

Turn 3 (Vote):
  Majority vote only among the K complex chains
```

**Why complexity matters:**

Simple chains may reflect shortcuts or lucky guesses. Complex chains demonstrate thorough reasoning. Voting only over complex chains filters out low-effort responses.

**Performance (GSM8K):**

| Method                      | Accuracy |
| --------------------------- | -------- |
| Standard SC (all chains)    | 78.0     |
| Complexity-weighted (top K) | 80.5     |

**Implementation note:** This requires no additional LLM calls beyond standard SC—just post-processing to count steps and filter before voting.

---

## 4. Implementation Patterns

### Conversation Structure Template

A general template for multi-turn improvement:

```
SYSTEM: [Base system prompt with single-turn techniques]

--- Turn 1: Initial Generation ---
USER: [Task]
ASSISTANT: [Initial output y₀]

--- Turn 2: Analysis/Feedback ---
USER: [Analysis prompt - critique, verify, or evaluate y₀]
ASSISTANT: [Feedback, verification results, or evaluation]

--- Turn 3: Refinement/Synthesis ---
USER: [Refinement prompt incorporating Turn 2 output]
ASSISTANT: [Improved output y₁]

[Repeat Turns 2-3 as needed]

--- Final Turn: Format/Extract ---
USER: [Optional: extract final answer in required format]
ASSISTANT: [Final formatted output]
```

### Context Management

Multi-turn prompting accumulates context. Manage token limits by:

1. **Summarize history:** After N iterations, summarize previous attempts rather than including full text
2. **Keep recent + best:** Retain only the most recent iteration and the best-scoring previous output
3. **Structured extraction:** Extract key points from feedback rather than full feedback text

**Example (summarized history):**

```
Previous attempts summary:
- Attempt 1: Failed due to [specific issue]
- Attempt 2: Improved [aspect] but [remaining issue]
- Attempt 3: Best so far, minor issue with [aspect]

Latest attempt: [full text of y₃]

Feedback on latest attempt:
```

---

## 5. Anti-Patterns

### The Mixed-Goal Turn

**Anti-pattern:** Combining distinct cognitive operations in a single turn.

```
# PROBLEMATIC
Generate a response, then critique it, then improve it.
```

Each operation deserves focused attention. The model may rush through critique to reach improvement, or improve without thorough analysis.

```
# BETTER
Turn 1: Generate response
Turn 2: Critique the response (output: feedback only)
Turn 3: Improve based on feedback
```

### The Contaminated Context

**Anti-pattern:** Including the original response when answering verification questions.

Per Dhuliawala et al. (2023): "Models that attend to existing hallucinations in the context from their own generations tend to repeat the hallucinations."

```
# PROBLEMATIC
Original response: [contains potential hallucinations]
Verification question: Where was Hillary Clinton born?
Answer:
```

The model will often confirm the hallucination from its original response.

```
# BETTER
Verification question: Where was Hillary Clinton born?
Answer:
[Original response NOT in context]
```

Exclude the baseline response when executing verifications. Include it only in the final revision step.

### The Yes/No Verification Trap

**Anti-pattern:** Phrasing verification questions as yes/no confirmations.

```
# PROBLEMATIC
Is it true that Michael Bloomberg was born in New York?
```

Per CoVe research: Models tend to agree with yes/no questions regardless of correctness.

```
# BETTER
Where was Michael Bloomberg born?
```

Open questions expecting factual answers perform significantly better.

### The Infinite Loop

**Anti-pattern:** No explicit stopping condition for iterative refinement.

```
# PROBLEMATIC
Keep improving until the output is perfect.
```

Models rarely self-terminate appropriately. "Perfect" is undefined.

```
# BETTER
Improve for exactly 3 iterations, then output the best version.

# OR
Improve until the quality score exceeds 8/10, maximum 5 iterations.
```

Always include explicit stopping criteria: iteration limits, quality thresholds, or both.

### The Forgotten History

**Anti-pattern:** Discarding previous iterations in refinement.

```
# PROBLEMATIC
Turn 3: Here is feedback. Improve the output.
[No reference to previous attempts]
```

Per Madaan et al.: "Retaining the history of previous feedback and outputs... allows the model to learn from past mistakes and avoid repeating them."

```
# BETTER
Turn 3:
Previous attempts and feedback:
- Attempt 1: [y₀] → Feedback: [fb₀]
- Attempt 2: [y₁] → Feedback: [fb₁]

Improve, avoiding previously identified issues:
```

### The Vague Feedback

**Anti-pattern:** Feedback without actionable specifics.

```
# PROBLEMATIC
The response could be improved. Some parts are unclear.
```

This feedback provides no guidance for refinement.

```
# BETTER
The explanation of photosynthesis in paragraph 2 uses jargon ("electron
transport chain") without definition. Add a brief explanation: "the process
by which plants convert light energy into chemical energy through a series
of protein complexes."
```

Feedback must identify specific elements AND suggest concrete improvements.

### The Majority Fallacy

**Anti-pattern:** Assuming majority vote is always correct.

```
# PROBLEMATIC
3 out of 5 chains say the answer is X, so X is correct.
```

Per Fu et al.: Simple chains may reflect shortcuts. Per Yoran et al.: Intermediate reasoning contains useful information discarded by voting.

```
# BETTER
Weight votes by reasoning complexity, or use MCR to synthesize
evidence from all chains including minority answers.
```

---

## 6. Technique Combinations

Multi-turn techniques can be combined for compounding benefits.

### Self-Refine + CoVe

Apply verification after refinement to catch introduced errors:

```
Turn 1: Generate initial output
Turn 2: Feedback
Turn 3: Refine
Turn 4: Plan verification questions for refined output
Turn 5: Execute verifications (factored)
Turn 6: Final verified output
```

### USC + Complexity Weighting

Filter by complexity before consistency selection:

```
Turn 1: Sample N responses with reasoning
Turn 2: Filter to top K by reasoning complexity
Turn 3: Apply USC to select most consistent among K
```

### MCR + Self-Refine

Use multi-chain evidence collection, then refine the synthesis:

```
Turn 1: Generate N reasoning chains
Turn 2: Meta-reason to synthesize evidence and produce answer
Turn 3: Feedback on synthesis
Turn 4: Refine synthesis
```

---

## Research Citations

- Chen, X., Aksitov, R., Alon, U., et al. (2023). "Universal Self-Consistency for Large Language Model Generation." arXiv.
- Dhuliawala, S., Komeili, M., Xu, J., et al. (2023). "Chain-of-Verification Reduces Hallucination in Large Language Models." arXiv.
- Diao, S., Wang, P., Lin, Y., & Zhang, T. (2023). "Active Prompting with Chain-of-Thought for Large Language Models." arXiv.
- Fu, Y., Peng, H., Sabharwal, A., Clark, P., & Khot, T. (2023). "Complexity-Based Prompting for Multi-Step Reasoning." arXiv.
- Madaan, A., Tandon, N., Gupta, P., et al. (2023). "Self-Refine: Iterative Refinement with Self-Feedback." arXiv.
- Wang, X., Wei, J., Schuurmans, D., et al. (2023). "Self-Consistency Improves Chain of Thought Reasoning in Language Models." ICLR.
- Yao, S., Yu, D., Zhao, J., et al. (2023). "Tree of Thoughts: Deliberate Problem Solving with Large Language Models." NeurIPS.
- Yoran, O., Wolfson, T., Bogin, B., et al. (2023). "Answering Questions by Meta-Reasoning over Multiple Chains of Thought." arXiv.
- Zhang, Y., Yuan, Y., & Yao, A. (2024). "Meta Prompting for AI Systems." arXiv.
