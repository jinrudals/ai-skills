# Checklist-driven delegation recipes — procedure skeletons and pitfalls

Patterns for the fixed procedure a checklist-driven orchestrator skill
follows (mode A / checklist-driven delegation). Where the host tool
exposes an actual workflow-scripting feature, these skeletons translate
directly into that scripting language; where it doesn't, follow them as
a plain-language checklist the orchestrating session executes itself,
dispatching delegations at each described point.

The pseudocode below is intentionally generic — not any one host tool's
real API — so it ports to whichever scripting or delegation mechanism
your tool provides. `dispatch(prompt, opts)` means "delegate this prompt
to a subagent, optionally requiring its result to match the given output
shape." `for each ... independently` means run without waiting on
siblings; `wait for all` means a synchronization barrier.

---

## Table of contents

1. [Basic skeleton](#1-basic-skeleton)
2. [Fan-out + adversarial verification](#2-fan-out--adversarial-verification)
3. [Judge panel](#3-judge-panel)
4. [Loop-until-dry](#4-loop-until-dry)
5. [Token-budget-aware looping](#5-token-budget-aware-looping)
6. [Custom agent types + structured output](#6-custom-agent-types--structured-output)
7. [Pitfalls checklist](#7-pitfalls-checklist)

---

## 1. Basic skeleton

Start with a literal description of the stage list; the stage names used
when narrating progress must exactly match this list.

```
procedure "domain-task":
  description: "one-line summary (shown wherever the host tool surfaces it)"
  stages: ["collect", "verify"]
    # collect: research each angle in parallel
    # verify: for each finding, search for counter-evidence and verify

stage "collect":
  raw = for each item in args.items, independently:
          dispatch(f"...{item}...", { label: f"collect:{item}", stage: "collect", schema: COLLECT_SCHEMA })

stage "verify":
  # ...

return { result }   # the final return value is handed back to the orchestrating session
```

**Principles:**
- **Default to per-item, independent staging; use an all-results
  barrier only when you truly need one.** A barrier is needed only when
  the next stage must compare **every** result from the previous stage
  together — deduplication, an early exit based on a total count, or a
  prompt that says "compare against the other findings."
- Don't hardcode the item list's values into the procedure itself.
  Prefer having the orchestrating session fix the list via a quick
  pre-check and pass it in as input.
- If a timestamp is needed, pass it in as input too. Reading the
  wall-clock inside the procedure breaks resumability on host tools that
  support resuming a run.

## 2. Fan-out + adversarial verification

Collect findings from each angle, then verify each finding
independently. Don't wait for every angle's research to finish before
verifying — verify an angle's findings the moment that angle's research
completes.

```
procedure "review-fanout-verify":
  description: "review by angle, then search for counter-evidence and verify each finding"
  stages: ["review", "verify"]

FINDINGS = schema: { findings: [{ title, file, evidence }] }
VERDICT  = schema: { status: confirmed | refuted | uncertain, reason }

results = for each dimension in args.dimensions, independently:
            # e.g. [{key: 'security', prompt: '...'}, {key: 'perf', prompt: '...'}]
            review = dispatch(dimension.prompt, { label: f"review:{dimension.key}", stage: "review", schema: FINDINGS })
            for each finding in (review?.findings ?? []), in parallel:
              verdict = dispatch(
                f"Verify this finding. Mark confirmed if well-evidenced, refuted if clearly disproven, uncertain if unclear: {finding}",
                { label: f"verify:{finding.file}", stage: "verify", schema: VERDICT })
              yield { ...finding, verdict }

confirmed = flatten(results).filter(x => x != null).filter(x => x.verdict.status == "confirmed")
log(f"{confirmed.length} of {flatten(results).filter(x => x != null).length} passed verification.")
return { confirmed }
```

For stricter verification, run 3 independent adversarial verifiers per
finding and keep only findings where more than half mark `confirmed`.
Giving each verifier a different lens — accuracy, security,
reproducibility — catches more than repeating the same check N times.

## 3. Judge panel

Used for design work with many viable solutions. Build N independent
drafts, judge them in parallel, then write a final version based on the
best-scoring draft.

```
procedure "design-judge-panel":
  description: "build N independent drafts, judge them, write the final version from the best one"
  stages: ["draft", "judge", "synthesize"]

angles = args.angles?.length ? args.angles : ["MVP-first", "risk-averse", "UX-first"]
judgeCount = args.judgeCount ?? 3

stage "draft":
  drafts = (for each angle in angles, in parallel:
              dispatch(f"Draft independently from a {angle} angle: {args.brief}", { label: f"draft:{angle}", stage: "draft" })
           ).filter(x => x != null)
  log(f"{drafts.length} of {angles.length} drafts completed.")
  if drafts.empty: return { error: "no completed drafts", drafts: [] }

stage "judge":   # needs an all-results barrier: every draft must be compared against every other
  SCORE = schema: { scores: [{ index, score, strengths }] }
  judged = (for j in range(judgeCount), in parallel:
              dispatch(f"Score the following {drafts.length} drafts:\n{drafts listed with index}", { label: f"judge:{j}", stage: "judge", schema: SCORE })
           ).filter(x => x != null)
  log(f"{judged.length} of {judgeCount} judges responded.")
  if judged.empty: return { error: "no completed judging", drafts }

stage "synthesize":
  ranked = for each draft index i:
             scores = judged.flatMap(r => r.scores).filter(s => s.index == i).map(s => s.score)
             yield scores.empty ? null : { index: i, average: mean(scores) }
  ranked = ranked.filter(x => x != null)
  if ranked.empty: return { error: "no valid per-draft scores", drafts, judged }
  winner = ranked.max_by(r => r.average).index
  finalDraft = dispatch(
    f"Write the final version based on the highest-scoring draft, folding in other drafts' strengths where useful.\nTop draft:\n{drafts[winner]}\nJudging notes:\n{judged}",
    { stage: "synthesize" })
  if finalDraft == null:
    log("failed to produce a final draft.")
    return { error: "failed to produce a final draft", drafts, judged, winner }
  return finalDraft
```

## 4. Loop-until-dry

Used when you don't know ahead of time how many items exist to find.
Keep searching until K consecutive rounds turn up nothing new.

```
finders = args.finders ?? []
dryLimit = args.dryRuns ?? 2
findingKey(finding) = serialize([finding.file ?? "", finding.title ?? "", finding.evidence ?? ""])
seen = {}, confirmed = []
if finders.empty: return { confirmed, error: "no search criteria" }

dry = 0
while dry < dryLimit:
  found = (for each finder in finders, in parallel:
             dispatch(finder.prompt, { stage: "search", schema: FINDINGS })
          ).filter(x => x != null).flatMap(r => r.findings)
  fresh = found.filter(f => !seen.has(findingKey(f)))
  # Dedupe against `seen`, not `confirmed` — see note below.
  if fresh.empty: dry += 1; continue
  dry = 0
  fresh.forEach(f => seen.add(findingKey(f)))
  judged = for each finding in fresh, in parallel:
             verdict = dispatch(
               f"Verify this finding. Mark confirmed if well-evidenced, refuted if clearly disproven, uncertain if unclear: {finding}",
               { stage: "verify", schema: VERDICT })
             yield { finding, ok: verdict?.status == "confirmed" }
  confirmed.push(...judged.filter(x => x != null).filter(x => x.ok).map(x => x.finding))
  log(f"{confirmed.length} confirmed so far; {fresh.length} new this round.")

return { confirmed }
```

Deduping against `confirmed` instead of `seen` makes the loop never
terminate — a rejected finding would just reappear every round. Dedupe
against everything ever found at least once, regardless of its
verdict.

## 5. Token-budget-aware looping

When the user names a token budget for the session (e.g. "+500k"),
scale search depth to what's left. Where the host tool exposes no
budget tracker at all, treat a session as unbounded and skip this
pattern. Where `budget.total` is unset (an unbounded session),
`budget.remaining()` returns infinity — always check `budget.total` is
set before relying on `remaining()` in a loop condition.

```
findings = []
while budget.total and budget.remaining() > 50_000:
  r = dispatch("Continue the next search task.", { schema: FINDINGS })
  if r: findings.push(...r.findings)
  log(f"{findings.length} found so far; ~{round(budget.remaining()/1000)}k tokens remaining.")

# Fixing scale up front instead: FLEET = budget.total ? floor(budget.total / 100_000) : 3
```

## 6. Custom agent types + structured output

Reuse agent definitions this harness already created under this
project's agent directory, inside a checklist-driven run.

```
r = dispatch(
  "Verify _workspace/02_draft.md and return the findings.",
  { agentType: "qa-inspector",      # {agent-dir}/qa-inspector.md
    schema: FINDINGS,               # only a result matching this schema is accepted; a mismatch is retried
    effort: "high" })               # raising reasoning effort tends to help at the verification stage
```

- Omitting `agentType` falls back to whatever default delegation type
  the host tool provides.
- Pick a model tier per stage's actual demands: **fast** for repetitive
  collection/transformation stages, **general-purpose** for deep
  verification/judging/design stages, **high-capability** for
  whole-plan, long-horizon stages. Full criteria in
  `model-selection-guide.md`.
- If several delegations might edit files concurrently and conflict,
  isolate each one's workspace — default to a dedicated git worktree per
  delegation where the host tool supports it and the project is a git
  repo (see "Workspace isolation (git worktree)" in
  `references/execution-modes.md`), otherwise fall back to whatever
  sandbox/isolation the host tool offers. Setting up an isolated
  workspace has cost, so only use it when conflicts are actually
  possible.

## 7. Pitfalls checklist

Check this list when verifying a checklist-driven procedure in step 6-2
of `SKILL.md`.

| Pitfall | Symptom | Prevention |
|------|------|------|
| Using variables or computed expressions where the host tool expects a literal stage/metadata declaration | The procedure/script fails to parse | Keep structural metadata (name, description, stage list) as literals only |
| Using a non-portable language dialect where the host tool only supports a plain scripting subset | The procedure/script fails to parse | Write in the plain subset the host tool documents (e.g. plain JavaScript with no TypeScript-only syntax, if that's what it requires) |
| Reading wall-clock time / random numbers / unseeded randomness inside the procedure | Breaks resume/retry protection | Pass timestamps and seeds in as input; for needed randomness, vary the prompt by index instead |
| Forgetting to filter out failed/null results | A failed delegation's null breaks the next stage | Always filter nulls out of a parallel or per-item result set before using it |
| Using an all-results barrier when it isn't needed | Total run time grows because a fast delegation waits on a slow one | Rewrite as independent, per-item staging unless you truly need to compare every result together |
| Stage-name mismatch | Progress doesn't group into the intended buckets | Keep narrated stage names and the declared stage list in sync |
| Calling the global progress-stage marker from inside a parallel step | Progress buckets collide with each other | Set the stage explicitly in that step's own options |
| Deduping against confirmed results instead of everything ever seen | A rejected finding reappears every round, so loop-until-dry never ends | Dedupe against a `seen` set that includes rejected findings too |
| Missing a `budget.total` check in a budget-aware loop | An unbounded session's loop runs until it hits the per-run delegation cap | Guard the loop with `while budget.total and ...` |
| Silently processing only part of the input without saying so | "Processed the top N" gets reported as "processed everything" | Always log how many items were left unprocessed |
| Diagnosing a result without checking the actual run log | A cached empty result gets mistaken for success | Before diagnosing a completed run, check its run log/transcript for what each delegation actually returned |
| Writing the procedure to a file first, "just in case" | Adds an unnecessary step | Pass the procedure's content directly where the host tool's dispatch call expects it; if the host tool preserves the script across calls, edit that in place and re-invoke by reference for later iterations |
