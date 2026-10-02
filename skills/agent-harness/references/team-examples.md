# Worked team-composition examples

Each example shows the criteria for picking the right execution
primitive, plus a sketch of the resulting structure. Primitive
definitions are in `execution-modes.md`; procedure skeletons are in
`workflow-recipes.md`.

---

## Example 1: comprehensive research team — checklist-driven delegation

**Composition:** fan-out/fan-in + adversarial verification

**Why:** the research angles can be listed ahead of time, and the
per-claim verification procedure can be fixed in a checklist.

```
[orchestrator] pre-check: fix research angles (official sources, press, community, background)
     → checklist-driven run with input {axes, topic, workspace}
         stage "research": for each axis, independently, dispatch a delegation returning FINDINGS
         stage "verify": run adversarial verification per claim → only claims a majority mark confirmed pass
         stage "synthesize": run one gap-reviewer delegation → if an angle was missed, research it too
     → orchestrator writes the final report from the returned structured result
```

Put research principles and the structured-output format in a
`researcher` agent definition, and rebuttal-first verification
principles in a `fact-checker` agent definition. The checklist
references both by their custom agent type.

Don't discard either side of conflicting information — carry both
through the return schema along with their sources.

## Example 2: writing a sci-fi novel — file-mediated-centered mixed mode

**Composition:** pipeline + producer-reviewer

**Why:** worldbuilding, characters, and plot must stay mutually
consistent and get adjusted live, so each specialist needs to remember
prior conversation. Reviewers, by contrast, only need to hand back an
independent opinion once each, so one-shot delegation is enough for
them.

```
Stage 1 (file-mediated): dispatch named delegations "worldbuilder", "character-designer",
               and "plot-architect" in parallel
               → register tasks for worldbuilding/characters/plot with their dependencies
               → the leader relays: once worldbuilder fixes the social structure
                 → pass it to character-designer
                 → if a character's occupation conflicts with the worldbuilding,
                   send it back to worldbuilder for adjustment
                 Because prior context persists, instructions can be scoped narrowly:
                 "just revise the merchant class within the class structure we set earlier."
Stage 2 (one-shot): dispatch "prose-stylist" once → it reads the three output files in
               _workspace/ and drafts the prose
Stage 3 (one-shot, parallel): "science-consultant" and "continuity-manager" each review independently
Stage 4 (file-mediated): a one-shot "prose-stylist" call from stage 2 can't be re-invoked with
               context intact. If stage 2 instead gave it a stable name, you can now tell it
               to incorporate the review findings. If revisions seem likely to repeat, give
               it a name from the very first call.
```

Give a stable name to any delegation you might need to send revision
requests to again. A nameless, one-shot delegation can't resume its own
prior context.

## Example 3: comprehensive code review — checklist-driven delegation

**Composition:** fan-out/fan-in + adversarial verification

**Why:** review angles — security, performance, architecture, tests —
can be fixed ahead of time, and the per-finding re-verification
procedure can also be expressed as a checklist.

```
# Review by angle → verify each finding adversarially.
# Don't wait for the full review to finish — once the security review
# completes, verify its findings right away even while the performance
# review is still running.

procedure:
  FINDINGS = schema: { findings: [{ title, file, evidence }] }
  VERDICT  = schema: { status: confirmed | refuted | uncertain, reason }
  angles = [
    { key: "security", prompt: "Review from a security angle." },
    { key: "perf",     prompt: "Review from a performance angle." },
    { key: "arch",     prompt: "Review from an architecture angle." },
    { key: "test",     prompt: "Review from a test-coverage angle." },
  ]
  results = for each angle in angles, independently:
              review = dispatch(angle.prompt, { stage: "review", schema: FINDINGS })
              for each finding in (review?.findings ?? []), in parallel:
                verdict = dispatch(
                  f"Verify this finding. Mark confirmed if well-evidenced, refuted if clearly disproven, uncertain if unclear: {finding}",
                  { stage: "verify", schema: VERDICT })
                yield { ...finding, verdict }
  confirmed = flatten(results).filter(x => x != null).filter(f => f.verdict?.status == "confirmed")
```

An earlier approach had reviewers share findings live through a
file-mediated team. Where a finding can be verified on its own, as
above, put enough evidence in the prompt to verify it immediately
instead. Only when findings must be compared against each other do you
need to collect the full review set behind a barrier before verifying.
Reach for file-mediated coordination only when real-time discussion is
genuinely needed — for example, debating which design direction to take.

## Example 4: large-scale code migration — file-mediated supervisor, or checklist-driven delegation

**Composition:** fan-out/fan-in if work batches can be split ahead of
time; supervisor if they must be re-split mid-run

**Decision criterion:** whether the work batches can be fixed ahead of
time.

If batches can be fixed ahead of time, use checklist-driven delegation.
Each batch's `isolation: "worktree"` follows the
`.worktrees/<identifier>` convention and `.gitignore` setup in
"Workspace isolation (git worktree)" in `references/execution-modes.md`.

```
MIGRATION_RESULT = schema: { worktreePath, changedFiles: [string] }
MIGRATION_VERDICT = schema: { status: confirmed | refuted | uncertain, reason }

migrated = for each batch in args.batches, independently:
             # batches are fixed ahead of time by scouting complexity first
             result = dispatch(
               f"Migrate this batch and return the absolute path of its isolated workspace and the actual list of changed files: {batch.files}",
               { agentType: "migrator", isolation: "worktree", schema: MIGRATION_RESULT })
             if result == null: yield null; continue
             verdict = dispatch(
               f"In isolated workspace {result.worktreePath}, verify the migration against the intended targets for gaps and errors. Intended: {batch.files}. Actual: {result.changedFiles}",
               { agentType: "qa-inspector", schema: MIGRATION_VERDICT })
             yield { ...result, verdict }

confirmed = migrated.filter(x => x != null).filter(x => x.verdict?.status == "confirmed")
return { confirmed }
```

Always pass the isolated-workspace path containing the migration result
to the adversarial-verification delegation. Once the checklist finishes,
the orchestrating session checks each `confirmed` result's
`worktreePath` one by one and either merges the change into the base
branch or cherry-picks just the needed commits. Resolve conflicts before
merging the next workspace, and only apply the next change once
integration tests pass. Don't merge `refuted`/`uncertain` results —
report the gap instead. Remove each worktree once its result is merged,
cherry-picked, or discarded.

If batches must be re-split as work progresses, use file-mediated
coordination instead.

```
Leader registers batches as tasks (with depends_on) in the shared task list
→ dispatch named delegations "migrator-1", "migrator-2", "migrator-3" in parallel
→ check results as completion notifications arrive
→ for a failed task, check the cause via the coordination file, then reassign it
→ once everything's done, run integration tests
```

## Example 5: webtoon production — a named producer and a one-shot reviewer

**Composition:** producer-reviewer

**Why:** only one producer and one reviewer are needed. Sending review
results back to the producer at most twice is enough, so a lightweight
mixed mode suffices.

```
Stage 1: dispatch named delegation "artist" → generate panels → _workspace/panels/
Stage 2: dispatch one-shot "webtoon-reviewer" → PASS/FIX/REDO verdict
         → _workspace/review_report.md
Stage 3: for panels marked REDO, send "artist" instructions to regenerate just those
         panels (re-invoked by name). Repeat at most twice. Because "artist" remembers
         prior context, instructions can be scoped narrowly: "just fix panel 3's composition."
Retry policy: if a panel still fails after two fixes, report it unresolved with its cause.
             If 50%+ of all panels are REDO, suggest revising the prompt to the user.
```

---

## Where output lives

- **Agent definitions:** under this project's agent directory,
  `{name}.md`. Always cover core role, working principles,
  input/output rules, how to re-invoke, error handling, and how to
  collaborate. For file-mediated agents, add communication rules; for
  checklist-driven agents, add the structured-output format.
- **Skills:** this project's skill directory, `{name}/SKILL.md`, with
  `references/` and `scripts/` as needed.
- **Orchestrator:** always state the execution primitive. Use the
  matching template in `orchestrator-template.md`.
- **Intermediate output:** `_workspace/{phase}_{agent}_{artifact}.{ext}`,
  kept even after verification finishes.
