# Mutation analysis and adversarial review fail in opposite directions

## Question

A guard has survived eighteen consecutive rounds of adversarial review, each
against a different model family, and each round still returns real defects.
Is another review round the best next spend?

## Conventional answer

Yes. The reviews are still productive. Yield is the signal that a method is
working, so keep running it until the yield drops.

## First-principles position

Yield says nothing about coverage. Adversarial review samples the **input**
space: a reviewer proposes a shape, the guard answers, and the answer is
compared. That procedure can only find defects on shapes somebody thought to
propose. It is structurally blind to two things:

1. Code the guard never executes. A reviewer only reaches paths its inputs
   reach.
2. A confident wrong answer on an unproposed shape. If nobody submits
   `partial(run, capture_output=False)`, nobody checks it.

Mutation analysis samples the **code** space instead. It asks which lines can
be changed without any test noticing, which is a direct measure of exactly what
the input sampling missed. The two methods are not redundant and one does not
substitute for the other.

## Evidence

Eighteen review rounds against the subprocess text-encoding guard never
surfaced a false positive that mutation battery 29 exposed in a single session.
The guard flagged `partial(run, capture_output=False)` while staying quiet on
the semantically identical direct call. Runtime proof under
`LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0` confirmed the partial form
decodes nothing at all, so there is no codec to pin.

The same session found one unreachable branch (a mutant on dead code can never
be killed) and one corrupted battery entry. Battery 29 fell from 15 survivors
to 4.

Retrospective: `.agents/retrospective/2026-07-30-guard-round-19-mutation-analysis.md`.
Issue: rjmurillo/ai-agents#3927.

## Decision

Treat mutation survivors as a first-class defect signal, not a coverage report.
A surviving mutant means one of three things, and assuming it always means the
first is the mistake:

| Meaning | Action |
| --- | --- |
| Coverage gap | Write a distinguishing test |
| The code under test is wrong | Fix the code |
| The branch is unreachable | Delete it |

Read which code path the mutant sits on before writing a test for it. Writing a
test for case two pins the defect in place as expected behavior. Writing a test
for case three is impossible and wastes the attempt.

Two supporting rules that came out of the same session:

- When two inputs both kill a mutant, choose the one where the base's answer is
  defensible. Both give a green test; only one gives a correct test.
- Prove equivalence structurally when the mutated branch has a small enumerable
  domain. Enumerate it instead of guessing more inputs.
