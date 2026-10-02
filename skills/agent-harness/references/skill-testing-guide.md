# Skill testing and iteration guide

How to verify the quality of skills built with agent-harness and improve
them over several rounds. Supplements step 6 of `SKILL.md`.

---

## Table of contents

1. [Overview of the testing approach](#1-overview)
2. [Writing test prompts](#2-writing-test-prompts)
3. [Comparing a with-skill run against a baseline run](#3-with-skill-vs-baseline)
4. [Running an A/B test at scale (checklist-driven)](#4-ab-testing-at-scale)
5. [Quantitative scoring with assertions](#5-assertion-based-scoring)
6. [Using specialist agents](#6-using-specialist-agents)
7. [The iteration loop](#7-iteration-loop)
8. [Verifying `description` trigger conditions](#8-verifying-trigger-conditions)
9. [Test workspace structure](#9-workspace-structure)

---

## 1. Overview

Confirm skill quality using both **qualitative evaluation** (a human
judging the output) and **quantitative evaluation** (scoring against
assertions).

| Evaluation style | Method | Good fit |
| --- | --- | --- |
| **Qualitative** | A person directly reviews the output. | Skills where quality judgment needs a human — writing style, design, creative work |
| **Quantitative** | Scored automatically against assertions. | Skills with an objectively checkable result — file creation, data extraction, code generation |

Follow the order: **write → run the test → evaluate → improve → test again.**

## 2. Writing test prompts

### Writing principles

Write test prompts as **specific, natural sentences a real user would
actually type.** Abstract or artificially staged prompts don't tell you
whether the skill works well in actual use.

**Bad examples:** `"process the PDF"`, `"extract the data"`

**Good example:**

```
"In 'Q4_Sales_Final_v2.xlsx' in my downloads folder, use column C
(revenue) and column D (cost) to add a profit-margin (%) column. Then
sort it descending by profit margin."
```

### Varying your prompts

- Mix formal and casual phrasing.
- Mix requests that state intent directly with ones where intent must
  be inferred from context — for example, both naming the file format
  explicitly and leaving it to be inferred.
- Mix simple and complex tasks, and include some abbreviations, typos,
  and everyday phrasing.

### Coverage to start with

Start with two or three prompts. Always include one core use case and
one edge case; add one multi-task-in-one-request case if relevant.

<a id="3-with-skill-vs-baseline"></a>

## 3. Comparing a with-skill run against a baseline run

### 3-1. Running both in comparison

For each test prompt, run two delegations **at the same time** in one
turn.

- **With-skill run**: reads the skill, does the work, and saves output
  to `_workspace/iteration-N/eval-{id}/with_skill/outputs/`.
- **Baseline run**: handles the same prompt without the skill, saving
  output to `_workspace/iteration-N/eval-{id}/without_skill/outputs/`.

### 3-2. Choosing the baseline

| Situation | Baseline |
| --- | --- |
| Building a new skill | Run the same prompt with no skill at all. |
| Improving an existing skill | Keep a separate copy of the pre-change skill and use it. |

### 3-3. Record duration and token usage immediately

As soon as a delegation's completion notification arrives, save
`total_tokens` and `duration_ms` **right away.** Both values are only
visible at that moment and can't be recovered later.

<a id="4-ab-testing-at-scale"></a>

## 4. Running an A/B test at scale (checklist-driven)

If you have three or more test cases, or need to re-verify repeatedly,
turn the A/B test itself into a checklist-driven run. Only do this with
the user's agreement to run the test. See `workflow-recipes.md` for the
pseudocode conventions used below.

```
procedure "skill-ab-test":
  description: "run with-skill and baseline, then grade them blind"
  stages: ["run", "grade"]

RUN_RESULT = schema: { saved: boolean, files: [string] (min 2) }
SLOT_GRADE = schema: {
  expectations: [{ text, passed, evidence }],
  summary: { passed, failed, total, pass_rate } }
GRADE = schema: { A: SLOT_GRADE, B: SLOT_GRADE,
                  comparison: { preferred: A | B | tie, reason } }

results = for each eval in args.evals, independently:
            # eval = {id, prompt, assertions, skillPath, withSkillSlot: 'A' | 'B'}
            withSkillSlot = eval.withSkillSlot == 'B' ? 'B' : 'A'
            baselineSlot  = withSkillSlot == 'A' ? 'B' : 'A'
            runs = for each of [with-skill, baseline], in parallel:
              with-skill: dispatch(
                f"{eval.prompt}\n\nFirst read {eval.skillPath} and follow it. Save output to " +
                f"{ws}/{eval.id}/with_skill/outputs/, and save the same files to " +
                f"{ws}/{eval.id}/blind/{withSkillSlot}/outputs/. Return every saved path.",
                { label: f"with-skill:{eval.id}", stage: "run", schema: RUN_RESULT })
              baseline: dispatch(
                f"{eval.prompt}\n\nSave output to {ws}/{eval.id}/without_skill/outputs/, and " +
                f"save the same files to {ws}/{eval.id}/blind/{baselineSlot}/outputs/. Return every saved path.",
                { label: f"baseline:{eval.id}", stage: "run", schema: RUN_RESULT })
            completed = runs.filter(x => x != null)
            if completed.length != 2 or any(r => !r.saved or r.files.length < 2 for r in completed):
              log(f"{eval.id}: skipping grading — with-skill and baseline outputs aren't both ready.")
              yield null
              continue
            grade = dispatch(
              f"First confirm output exists at both {ws}/{eval.id}/blind/A/outputs/ and " +
              f"{ws}/{eval.id}/blind/B/outputs/. If either is empty, don't grade — report why. " +
              f"Otherwise grade A and B each, and judge which is better as A, B, or tie. To preserve " +
              f"anonymity, don't open eval_metadata.json, with_skill/, or without_skill/. " +
              f"Assertions: {eval.assertions}",
              { label: f"grade:{eval.id}", stage: "grade", schema: GRADE })
            if grade == null:
              log(f"{eval.id}: skipping — no blind-grading result returned.")
            yield grade

mapped = for each (grade, eval) in zip(results, args.evals):
  if grade == null: continue
  withSkillSlot = eval.withSkillSlot == 'B' ? 'B' : 'A'
  baselineSlot  = withSkillSlot == 'A' ? 'B' : 'A'
  yield {
    evalId: eval.id,
    withSkill: grade[withSkillSlot],
    baseline: grade[baselineSlot],
    comparison: {
      preferred: grade.comparison.preferred == 'tie' ? 'tie'
               : grade.comparison.preferred == withSkillSlot ? 'with_skill' : 'baseline',
      reason: grade.comparison.reason,
    },
  }
return { results: mapped }
```

The orchestrating session alternates `withSkillSlot` between A and B for
each test case. The grader only reads the neutral `blind/A/` and
`blind/B/` paths, so it can't tell which slot used the skill. Only
cases where both runs' outputs are ready get graded, and grading for a
case starts as soon as that case is ready — no need to wait for every
case to finish. Record the mapped result in each run directory's
`grading.json`. If the host tool supports resuming a run and the skill
changes, unchanged cases can reuse their cached result and skip
re-running.

<a id="5-assertion-based-scoring"></a>

## 5. Quantitative scoring with assertions

### 5-1. Writing assertions

A **good assertion** can be objectively judged true or false, is
understandable from its wording alone, and measures a result that should
actually improve when the skill is used. Avoid assertions that always
pass regardless of the skill (e.g. "output exists") or that need
subjective human judgment (e.g. "is well written").

### 5-2. Assertions checkable by code

Write any assertion a script can check as a script. It's faster and more
reliable than visual inspection, and the same script can be reused
across iteration rounds.

### 5-3. Watch for assertions with no discriminating power

An assertion that both the with-skill and baseline runs pass 100% of the
time measures nothing about the skill's actual effect. Delete it, or
tighten it until it can reveal a real difference between the two runs.

### 5-4. Grading result schema

Follow the `grading.json` shape (`text`/`passed`/`evidence` plus
`summary`) defined in `skill-writing-guide.md`.

## 6. Using specialist agents

| Role | Does | Use when |
| --- | --- | --- |
| **Grader** | Records each assertion's pass/fail with evidence, cross-checks factual claims in the output, and checks the quality of the assertions themselves. | Every iteration round |
| **Blind comparator** | Hides which output used the skill, shuffles A/B order, then compares quality. | Rigorously confirming a new version is actually better |
| **Analyzer** | Analyzes statistical patterns — assertions with no discriminating power, outlier cases, the time/token trade-off. | After three or more rounds of results have accumulated |

<a id="7-iteration-loop"></a>

## 7. The iteration loop

### 7-1. Improvement principles

1. **Generalize feedback.** Fixing something to match only one test case
   overfits. Rewrite it as a principle that applies to other cases too.
2. **Delete instructions that don't help.** Read the agent's work log;
   if the skill is causing unnecessary work, remove that instruction.
3. **Explain the reason.** Even short feedback matters for a reason —
   find it, then revise the skill so the reason is visible in the text.
4. **Pre-bundle tools needed repeatedly.** If every test run recreates
   the same helper script, put it in `scripts/`.

### 7-2. Iteration order

```
1. Revise the skill.
2. Rerun every test case in a new `iteration-{N+1}/` directory.
3. Present the comparison against the previous round to the user.
4. Take feedback, revise again, and repeat.
```

**Stop when:** the user is satisfied, there's no more feedback to
incorporate, or further changes no longer meaningfully improve things.

### 7-3. Review a fresh draft from a new angle

When revising a skill, write a draft first. Then re-read it from the
start as if you were a reviewer seeing it for the first time, and fix
what needs fixing. Don't try to get it perfect on the first pass.

<a id="8-verifying-trigger-conditions"></a>

## 8. Verifying `description` trigger conditions

### 8-1. Writing evaluation requests

Write 20 evaluation requests: 10 `should-trigger` requests that should
invoke the skill, and 10 `should-NOT-trigger` requests that shouldn't.

**Criteria for writing them:**

- Use specific, natural sentences a real user would type.
- Include specifics — file paths, the user's situation, column names,
  company names.
- Focus on **boundary cases** that are genuinely hard to judge, not
  obvious ones.

**`should-trigger`:** include the same intent phrased several different
ways, requests that don't name a file type but clearly need this skill,
uncommon use cases, and requests that overlap another skill but should
still select this one.

**`should-NOT-trigger`:** **near-miss cases that sound similar but
aren't actually a match matter most here.** Include requests that use
similar words but where a different tool or skill actually fits better.
A clearly unrelated request isn't worth testing.

### 8-2. Check for conflicts with existing skills

1. Collect every existing skill's `description`.
2. Confirm the new skill's `should-trigger` requests don't accidentally
   invoke an existing skill instead.
3. If a conflict appears, sharpen the `description`'s scope and
   exclusions.

### 8-3. Automated optimization (optional, advanced)

1. Split the 20 evaluation requests into a 60% train set and a 40% test set.
2. Measure the current `description`'s trigger accuracy.
3. Analyze failed cases and improve the `description`.
4. Pick the best-performing `description` based on the **test set's**
   results. Picking based on the train set's results overfits.
5. Repeat this up to five times.

> Check this with a scripted, headless run of the host tool if it
> supports one. This uses a lot of tokens, so run it only as a final
> step once the skill is otherwise stable.

<a id="9-workspace-structure"></a>

## 9. Test workspace structure

```
_workspace/
├── iteration-1/
│   ├── eval-descriptive-name/
│   │   ├── eval_metadata.json
│   │   ├── with_skill/    (outputs/ + timing.json + grading.json)
│   │   ├── without_skill/ (outputs/ + timing.json + grading.json)
│   │   └── blind/         (A/outputs/ + B/outputs/)
│   └── benchmark.json
├── iteration-2/
└── evals/evals.json
```

**Retention rules:**

- Name each `eval` directory descriptively instead of numbering it
  (e.g. `eval-multi-page-table-extraction`).
- Give each iteration round its own directory; never overwrite a
  previous `iteration-*` directory.
- Don't delete `_workspace/` — it's needed for later verification and
  change tracking.
