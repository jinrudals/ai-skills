# Execution primitives in detail — the three portable modes

This doc explains the main capabilities, limits, and selection criteria
for agent-harness's three execution primitives. It supplements step 2-1
of `SKILL.md`.

---

## Table of contents

1. [Checklist-driven delegation](#1-checklist-driven-delegation)
2. [File-mediated coordination](#2-file-mediated-coordination)
3. [One-shot delegation](#3-one-shot-delegation)
4. [Decision tree for choosing a primitive](#4-decision-tree)
5. [Porting an existing tool-specific harness](#5-porting-an-existing-tool-specific-harness)
6. [Workspace isolation (git worktree)](#6-workspace-isolation-git-worktree)

---

## 1. Checklist-driven delegation

The orchestrating session follows a plain-language procedure (or, where
the host tool exposes an explicit workflow-scripting feature, an actual
script) that fixes control flow — fan-out, repetition, conditional
branching — ahead of time instead of leaving it to the model's
in-the-moment judgment. Control fixed this way is easy to reproduce
given the same input, and suits large parallel fan-outs.

```
[orchestrating session] → run the checklist
           ├── stage "collect": dispatch one delegation per item, independently
           ├── stage "verify": for each finding, search for counter-evidence and verify (in parallel)
           └── return { confirmed }   ← structured final result
```

**Key capabilities, however the host tool exposes them:**
- **Dispatch-with-schema**: dispatch a subagent with a prompt and, where
  supported, a required output schema; a result that doesn't match gets
  retried automatically so the caller doesn't have to parse free text.
  Where the host tool also supports a reusable custom-agent-type
  reference and a reasoning-effort/isolation setting, use them.
- **Per-item staging**: run each item through a sequence of stages
  independently, with no synchronization barrier between stages — this
  is the default for multi-stage work.
- **All-results barrier**: wait for every parallel item to finish before
  continuing — use this only when the next stage genuinely needs to
  compare *all* results together (deduplication, an early-exit based on
  a total count).
- **Stage labels and progress logging**: group progress under named
  stages and narrate what's currently happening to the user.
- **Token-budget awareness**: when the user names a token budget (e.g.
  "+500k"), check remaining budget and scale the work down accordingly.
- **Nested delegation**: delegate a sub-procedure down one more level
  when work is naturally hierarchical.

**Properties:**
- Because code (or a fixed checklist) decides control flow, the same
  input produces the same execution shape.
- Structured output lets each stage pass schema-conforming data to the
  next.
- If the host tool supports resuming an interrupted run from a prior run
  identifier, unchanged steps can return cached results — use it to keep
  partial-reruns cheap.
- Runs in the background where supported, notifying on completion.

**Limits:**
- **Only use it when the work actually calls for it.** Don't reach for a
  large parallel fan-out just because the tool is available — keep the
  default scale small, and use a large fan-out only when the user
  explicitly asks for thorough/exhaustive coverage.
- If the host tool exposes an actual scripting language for this
  primitive, stick to a plain, portable subset: no non-deterministic
  values (wall-clock time, random numbers) baked into the script itself
  — pass them in as arguments instead, since they'd otherwise break
  resume/retry.
  Keep structural metadata (the stage list, its description) as literal
  values, not computed expressions.
- There's usually a per-session concurrency cap on how many delegations
  can run at once; anything past it queues automatically. Keep an
  overall cap on total delegations in one run to avoid runaway execution.
- A failed or skipped delegation should produce a null/empty result
  rather than aborting the batch; always filter nulls out before using
  a result set.
- An all-results barrier only lines up *when* things finish, not what
  happens *after*. In a mixed-primitive run, a file-mediated delegation
  woken up after a checklist-driven stage has finished can still edit
  that stage's output file — freeze (see "Output freezing" in
  `orchestrator-template.md`'s file-mediated template) at the boundary
  where a primitive switch happens.

**Good fit:** fan-outs over a list fixable ahead of time (N files, M
review angles), loop-until-dry search with adversarial verification,
large-scale conversion/audits, generating a structured report.

**Poor fit:** work where the target list can only be discovered through
an ongoing conversation, or that needs frequent check-ins with the user
mid-run.

> For concrete procedure skeletons and pitfalls, see
> `references/workflow-recipes.md`.

## 2. File-mediated coordination

Dispatch named, re-invokable delegations and coordinate them through a
shared coordination file (a task list, or a structured hand-off note)
instead of a dedicated persistent-agent messaging API — most host tools
don't expose one, but a shared file both the orchestrator and each named
delegation read on entry and write on exit achieves the same effect
portably. Where the host tool *does* expose a native live-messaging or
shared-task-list feature between subagents, prefer it — it is more
efficient — but every pattern in this doc must also work with plain
re-invocation plus a shared file when it isn't available.

```
[orchestrating session (leader)]
    ├── dispatch named delegation "researcher"   ← in parallel
    ├── dispatch named delegation "critic"
    ├── maintain a shared coordination file (tasks + dependencies)
    ├── re-invoke "researcher" with added instructions, passing the file's current state
    └── collect completion → gather results → final synthesis
```

**Key capabilities, however the host tool exposes them:**
- **Named, re-invokable delegation**: giving a delegation a stable name
  or identifier lets you call it again later with its prior context
  intact, so it can revise its own earlier work instead of starting
  fresh. This is what makes "just fix section 2 of the draft you made
  earlier" possible.
- **Shared coordination file**: a task list or hand-off note that every
  participating delegation reads on entry and updates on exit. Use it to
  track dependencies between tasks and who owns what.
- **Stop/cancel**: stop a delegation that's run too long or is no longer
  needed.

**Properties:**
- Because a delegation remembers its own prior conversation and work,
  follow-up requests work ("just fix section 2 of the draft you made
  earlier, in this same session").
- Delegations can share findings, discuss disagreements, and course-correct.
- The same specialist keeps being available for as long as the session
  runs.

**Limits:**
- The orchestrating session does all the coordinating itself, so more
  named delegations means more coordination burden on it. 3-5 is a
  reasonable ceiling.
- Nesting delegation more than two levels deep tends to lose context and
  add latency. Keep it to two levels.
- Costs more tokens than a one-shot call.
- Because a named delegation keeps accepting messages even after
  reporting completion, it can still edit output it already handed off
  while answering a late question from someone else. If a later stage
  reads that output, freeze it at the stage boundary. The freeze
  procedure is in template B's step 4 in `references/orchestrator-template.md`.

**Good fit:** a producer and reviewer trading revisions back and forth;
reconciling conflicting data through discussion; a supervisor
reassigning work as progress comes in; needing the same specialist
available for the whole session.

**Poor fit:** one-off work where only the result matters; large fan-outs
whose item list can be fixed ahead of time.

## 3. One-shot delegation

Call the delegation tool once per independent item. Only the result
comes back to the orchestrating session; delegations don't talk to each
other.

```
[orchestrating session] → delegate A ─┐
                        → delegate B ─┼→ (parallel, in one turn) → collect results
                        → delegate C ─┘
```

**Properties:**
- Low overhead, fast. The orchestrating session gets a summarized
  result.
- Independent calls issued together in a single turn run concurrently.
- Where the host tool defaults to foreground/blocking delegation, prefer
  running it in the background when you don't need the result
  immediately, and wait for completion notifications instead of polling.
- The orchestrating session doesn't repeat work it already delegated —
  it waits for the result.

**Limits:**
- Delegations can't talk to each other, and context doesn't persist past
  one call. To start fresh work, just make a new call without a
  stable name/identifier.
- All coordination falls on the orchestrating session.

**Good fit:** one-off research/collection, picking the right specialist
for a result and nothing more, a single independent verification pass.

**Poor fit:** work needing repeated back-and-forth revision, or a large
fan-out whose control flow should be fixed ahead of time.

## 4. Decision tree

```
Can the item list, verification criteria, and repeat conditions
be fixed ahead of time (in code or a written checklist)?
├── Yes → Checklist-driven delegation
│         Control flow is fixed ahead of time, not decided by the model
│         in the moment. Keep the delegation count no larger than the
│         work actually needs.
│
└── No → Does quality depend on repeated back-and-forth and persistent
          conversational context across delegations?
          ├── Yes → File-mediated coordination
          │
          └── No → More than one delegation needed?
                        ├── Yes → One-shot delegation, in parallel
                        └── No  → One-shot delegation, single call
```

**Choosing a mixed combination:** when different stages answer the
question above differently, mix primitives. Common combinations:

| Combination | Shape | Example |
| --- | --- | --- |
| Checklist-driven collection → file-mediated integration | A → B | Gather material at scale, then have a team discuss and reconcile conflicting data |
| File-mediated drafting → checklist-driven verification | B → A | A team drafts something, then adversarial verification runs at scale over each finding |
| One-shot scouting → checklist-driven main work | C → A | The orchestrator or a one-shot delegation first discovers the item list, then passes it to a checklist-driven run |

**Confirm the item list before starting a checklist-driven run:** before
kicking off a checklist-driven run, take a quick look at the file list,
review targets, or research items and fix the item list. Knowing the
shape of the work before execution keeps the checklist simple and avoids
wasted work.

## 5. Porting an existing tool-specific harness

If you find an orchestrator or agent definitions that were written for
one specific host tool's proprietary multi-agent API (an explicit
workflow-scripting tool, a persistent-named-agent messaging tool, a
dedicated team-lifecycle API), offer to rewrite them using this skill's
three portable primitives instead:

1. Identify which primitive each tool-specific construct was standing in
   for — a workflow/pipeline call is almost always checklist-driven
   delegation; a named-agent-plus-messaging construct is almost always
   file-mediated coordination; a single delegate-and-collect call is
   one-shot delegation.
2. Rewrite the orchestrator using the matching template in
   `references/orchestrator-template.md`, keeping the same stages, data
   flow, and error-handling intent.
3. Drop anything that only makes sense inside the original tool's API
   (an explicit team-lifecycle step, an environment flag needed only to
   unlock that tool's feature, a hardcoded reference to that tool's
   model-name strings) and replace it with this skill's portable
   equivalent (see the model-tier mapping in
   `references/model-selection-guide.md`).
4. Re-run step 6's verification (structural checks and a test run) and
   record the port in the project's change log.

## 6. Workspace isolation (git worktree)

Whenever several delegations might edit files in parallel and could
conflict — checklist-driven fan-out editing many files, a
producer/reviewer pair touching the same tree, any pattern flagged
"file-isolation setting" in `references/team-patterns.md` — and the
project is a git repository, **default to a git worktree per
delegation** wherever the host tool lets you pass each delegation its
own working directory. A worktree gives each delegation a real,
file-system-isolated checkout on its own branch without the cost of a
full repo clone, so prefer it over a plain sandbox/copy when the host
tool supports either. Only skip it when the project isn't a git
repository, or the host tool has no way to point a delegation at a
specific working directory — fall back to whatever isolation the host
tool does offer, or note the conflict risk and proceed without
isolation if it genuinely doesn't.

**Convention:**
1. Create each delegation's worktree under `.worktrees/<identifier>` at
   the repository root (e.g. `.worktrees/migrate-batch-03`), on its own
   branch. Keep `<identifier>` short and descriptive of the delegation's
   task so a human skimming `.worktrees/` can tell runs apart.
2. Before the first worktree is created in a given repository, make sure
   `.worktrees/` is excluded from version control: if the repo has no
   `.gitignore`, create one containing a `.worktrees/` entry; if it has
   one, append a `.worktrees/` entry unless an equivalent pattern (e.g.
   `.worktrees/`, `/.worktrees/`, `.worktrees`) is already present. Don't
   add a duplicate entry on later runs.
3. Pass each delegation its worktree's absolute path so it both works
   there and reports it back (see the `worktreePath` field in Example 4
   of `references/team-examples.md`) — the orchestrating session needs
   that path to inspect, merge, or cherry-pick the result afterward.
4. Once a worktree's result has been merged or cherry-picked into the
   base branch (or discarded because it was refuted/uncertain), remove
   the worktree (and its branch, if no longer needed) so `.worktrees/`
   doesn't accumulate stale checkouts across runs.
