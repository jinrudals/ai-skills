# Orchestrator skill templates

The orchestrator coordinates the whole team. This doc gives three
templates, one per execution primitive, and explains how to combine
primitives stage by stage.

- **Template A: checklist-driven delegation** — large-scale distributed
  execution or repeated verification whose control flow is fixed ahead
  of time
- **Template B: file-mediated coordination** — repeated feedback,
  negotiation, or long-running collaboration where agents must retain
  prior conversational context
- **Template C: one-shot delegation** — independent work handed off once
  each, collecting only the results

Every template checks prior work in step 0. All of them must also cover
the `_workspace/` file-organization rules, error handling, and test
scenarios.

---

## Template A: checklist-driven delegation

```markdown
---
name: {domain}-orchestrator
description: "Coordinates the {domain} checklist. Use when the user asks with one of {initial trigger keywords}; also use for follow-up work — fixing the {domain} result, a partial rerun, an update, a refinement, rerunning, or improving the previous result."
---

# {Domain} orchestrator

## Execution primitive: checklist-driven delegation

This skill coordinates work whose control flow is fixed ahead of time
(as a plain checklist, or as an actual script if the host tool exposes
workflow scripting). Invoking this skill implies the user is fine with
that. Cap the default number of delegations at {N}; only increase it
when the user explicitly asks for "thorough", "exhaustive", or "all of
it" coverage.

## Team composition

| Role | Agent type | Skill | Output (`schema` summary) |
|------|-----------|------|--------------------|
| {collector} | {custom or built-in} | {skill} | {findings: [...]} |
| {verifier}  | {custom or built-in} | {skill} | {status, reason} |

`{custom or built-in}` names either a custom agent type or a built-in
one.

## Procedure

### Step 0: check prior work (handling follow-up requests)

1. Check whether `_workspace/` exists.
   - Missing → run from scratch
   - Exists, and the request only asks to fix part of it → rerun only that part
   - Exists, and there's new input → move the existing `_workspace/` to `_workspace_{ts}/`, then run fresh
2. If rerunning only part of it, and the host tool supports resuming a
   prior run from a saved run identifier (recorded in
   `_workspace/run_meta.json`):
   - Edit only the affected step, then resume from that identifier.
     Steps whose inputs haven't changed should return their cached
     result rather than re-running, keeping cost low.
3. If running fresh, record a new run identifier in `_workspace/run_meta.json`.

### Step 1: fix the item list (the orchestrating session does this directly)

Before starting the checklist, take a quick look at {the file list /
research axes / review targets} and lay them out as a list. Pass that
list in as the checklist's input.

### Step 2: run the checklist

Dispatch the following procedure (see `workflow-recipes.md` for concrete
skeletons):

- Name: `{domain}-run`; stages: [{collect}, {verify}, {synthesize}]
- Collect: for each item in the fixed list, independently, dispatch a
  delegation with the COLLECT output shape
- Verify: for each finding, run adversarial verification → drop anything
  that fails → only verified findings proceed
- Synthesize: return the structured result

Wait for the completion notification after dispatching. Don't assume
the result before it arrives.

### Step 3: assemble and report the result

1. Take the returned value.
2. If anything was excluded or missing, state it explicitly in the report.
3. Produce the final deliverable at `{output-path}/{filename}`.
4. Leave intermediate output and `run_meta.json` in `_workspace/`.

## Error handling

| Situation | Response |
| --- | --- |
| A single delegation fails (returns null) | Filter it out, log how many were dropped, and disclose the gap in the report. |
| The whole checklist fails | Check the actual returned values in the run log, fix only the failed step, and resume from the saved run identifier if supported. |
| A failure that won't resolve by retrying (quota exhaustion, expired auth, denied permission) | Don't retry or resume until the underlying cause is fixed — retrying just burns remaining quota. Open the run log and partial output directly to see how far it actually got, record the gap as a file in `_workspace/`, and report it to the user — including when a quota resets, if that's the cause. Once the cause is fixed, resume from the saved run identifier. The orchestrator only reflects facts it verified itself; it doesn't guess at a delegation's judgment calls (e.g. which material it excluded and why). |
| An empty result | Don't mistake this for success. Check each delegation's actual returned value in the run log. |
| Conflicting data | Don't delete either side — record both with their source. |

## Test scenarios

### Happy path
1. Given {input}, the pre-check step fixes {M} items.
2. The checklist collects all {M} items; {K} pass verification; the result is assembled.
3. Expected result: `{output-path}/{filename}` is created, and `run_meta.json` records the run.

### Error path
1. Two items return null during the collect stage.
2. They're filtered out via the null-filter and logged as "2 excluded".
3. The final report states "failed to collect 2 {item name}".
```

---

## Template B: file-mediated coordination

```markdown
---
name: {domain}-orchestrator
description: "Coordinates collaboration among {domain} agents. Use when the user asks with one of {initial trigger keywords}; also use for follow-up work — fixes, a partial rerun, an update, a refinement, rerunning, or improving the previous result."
---

# {Domain} orchestrator

## Execution primitive: file-mediated coordination

Named delegations invoked in this session automatically belong to one
coordination group — there's no separate team-lifecycle object to
create or tear down.

## Team composition

| Name | Agent type | Role | Skill | Output |
|------|--------------|------|------|------|
| {teammate-1} | {custom or built-in} | {role} | {skill} | {output-file} |
| {teammate-2} | {custom or built-in} | {role} | {skill} | {output-file} |

`{custom or built-in}` names either a custom agent type or a built-in one.

## Procedure

### Step 0: check prior work
Same as template A: check whether `_workspace/` exists to decide between
running from scratch, a partial rerun, or a fresh run. For a partial
rerun, pass the prior output's path into the delegation's prompt so it
reads and incorporates it.

### Step 1: prepare
1. Analyze the user's input to confirm {what needs to be determined}.
2. Create `_workspace/` and store the input under `_workspace/00_input/`.

### Step 2: dispatch delegations and register tasks

1. Dispatch delegations in parallel, in a single turn. Each needs a
   stable name/identifier so it can be re-invoked later with context
   intact.
   - Dispatch "{teammate-1}" ({type}), prompt: "{role + task instructions + output path}"
   - Dispatch "{teammate-2}" ({type}), prompt: "..."
2. Register a shared task list (the coordination file).
   - Add task "{task-1}", assignee "{teammate-1}"
   - Add task "{task-3}", depends_on: [task-1]
   > 3-6 tasks per teammate is a reasonable load. State dependencies
   > between tasks explicitly.

### Step 3: coordinate collaboration

- Follow completion/waiting notifications as they arrive. Check overall
  progress via the shared task list.
- Request a review by re-invoking {teammate-2} with: "review
  {teammate-1}'s draft at `_workspace/01_...` in the coordination file
  and report what needs fixing." Relay the answer to {teammate-1} to
  apply. Because a delegation remembers its own prior context, you can
  scope instructions narrowly — "just section 2 of the draft from
  earlier."
- If findings need discussion among teammates, the leader relays
  messages. Output always lands in a file.

**Where each teammate's output goes:**

| Teammate | Output path |
| --- | --- |
| {teammate-1} | `_workspace/{phase}_{teammate-1}_{artifact}.md` |
| {teammate-2} | `_workspace/{phase}_{teammate-2}_{artifact}.md` |

### Step 4: freeze output

A named delegation keeps accepting messages even after reporting
completion. If it answers a late question from another teammate and, in
doing so, edits output it already handed off, the next stage ends up
reading content that changed after the fact. Don't block teammates from
cross-checking each other — that catches real errors — but freeze output
at every stage boundary so the next stage's input can't shift underneath
it.

1. Use the shared task list and completion notifications to confirm
   every teammate on the prior stage has reported done.
2. Tell each of them the stage is frozen: "{stage}'s output is now
   frozen. If you need to change anything later, don't edit the
   existing file — write a new version like
   `{phase}_{teammate}_{artifact}_v2.md` and notify the leader."
3. Record a hash of the output, e.g.
   `shasum _workspace/{phase}_* > _workspace/freeze_{phase}.sha` (`md5sum` works too).
4. Pass the output path and hash-file path into the next stage's
   delegation prompt.

Repeat this at every stage boundary in a multi-stage collaboration.

### Step 5: integrate
1. Confirm every task is done via the shared task list.
2. Read each output file and apply {integration/verification logic}.
3. Right before producing the final deliverable, recompute the hash
   (e.g. `shasum -c _workspace/freeze_{phase}.sha`) to confirm frozen
   output hasn't changed. If the hash differs or a new version file
   appeared, check what changed and decide whether to rerun any stage
   that read the earlier content.
4. Produce the final deliverable at `{output-path}/{filename}`.

### Step 6: wrap up
1. Leave `_workspace/` in place for later verification and audit.
2. Report a summary of the result to the user. There's no team-teardown
   step — a delegation ends naturally once its work is done; stop it
   explicitly only if it's still running unnecessarily.

## Error handling

| Situation | Response |
| --- | --- |
| A teammate stops responding or has stopped | Check status via the coordination file and re-issue instructions. If that still fails, dispatch a fresh delegation of the same type under a new name, passing the needed task context in its prompt. |
| Stopped due to quota exhaustion, expired auth, or denied permission | Don't re-instruct or dispatch a replacement — retrying produces the same result. Open the partial output directly to see how far it actually got, record the gap as a file in `_workspace/`, and report it to the user, including when a quota resets if that's the cause. The leader only reflects facts it verified itself, never guessing at a delegation's judgment calls. |
| More than half the teammates fail | Tell the user and confirm whether to continue. |
| A time limit is exceeded | Proceed with whatever results arrived, and disclose the unfinished areas in the report. |
| Conflicting data | Don't delete either side — list both side by side with their source. |
| Task status updates arrive late | Check the shared task list and update it directly. |

## Test scenarios

### Happy path
1. Given {input}, step 2 dispatches {N} delegations and registers {M} tasks.
2. Step 3 exchanges feedback {K} times; step 4 freezes output; step 5 integrates the result.
3. Expected result: `{output-path}/{filename}` is created.

### Error path
1. {teammate-2} stops responding during step 3.
2. Check status via the coordination file and re-issue instructions. If that still fails, dispatch a replacement named "{teammate-2}b", passing the existing output path.
3. The final report states "partial rework in the {teammate-2} area".
```

---

## Template C: one-shot delegation

```markdown
---
name: {domain}-orchestrator
description: "Delegates independent {domain} work to subagents. Use when the user asks with one of {initial trigger keywords}; also use for follow-up work — fixing the result, a partial rerun, an update, a refinement, rerunning, or improving the previous result."
---

## Execution primitive: one-shot delegation

## Procedure

### Step 0: check prior work
Check whether `_workspace/` exists to decide between running from
scratch, a partial rerun, or a fresh run.

### Step 1: prepare
Analyze the input and create `_workspace/`.

### Step 2: dispatch in parallel
Call the delegation tool N times in a single turn. Run them in the
background by default where the host tool supports it.

| Agent | Type | Input | Output |
|---------|--------------|------|------|
| {agent-1} | {type} | {source} | `_workspace/{phase}_{agent}_{artifact}.md` |
| {agent-2} | {type} | {source} | `_workspace/{phase}_{agent}_{artifact}.md` |

`{type}` names either a custom agent type or a built-in one.

Wait for completion notifications. The orchestrating session doesn't
redo work it has already delegated.

### Step 3: integrate
1. Gather return values and file output, integrate them, and produce
   the final deliverable.

### Step 4: wrap up
Leave `_workspace/` in place and report a summary to the user.

## Error handling
- If one delegation fails, retry once. If it fails again, disclose the
  gap and continue.
- Don't retry a failure that will produce the same result again — quota
  exhaustion, expired auth, denied permission. Open the partial output
  directly to see how far it actually got, record the gap as a file in
  `_workspace/`, and report it, including when a quota resets. The
  orchestrating session only reflects facts it verified itself, never
  guessing at a delegation's judgment calls.
- If more than half the delegations fail, tell the user and confirm
  whether to continue.
```

---

## Combining primitives stage by stage (mixed mode)

Use the primitive each stage actually needs. Mark each stage with
`**Execution primitive:**` at the top.

```markdown
## Execution primitive: mixed

| Stage | Execution primitive | Why |
|------|----------|-----------|
| Stage 1 (pre-check) | Orchestrating session directly, or one-shot delegation | The item list must be fixed first. |
| Stage 2 (bulk collection/verification) | Checklist-driven delegation | A pre-fixed list needs distributed processing plus adversarial verification. |
| Stage 3 (reconciliation/integration) | File-mediated coordination | Conflicting data needs discussion to reach agreement. |
| Stage 4 (independent verification) | One-shot delegation | A single QA agent can verify independently. |
```

**Rules for switching primitives:**
- Checklist-driven → file-mediated: save the checklist's structured
  output to `_workspace/`, and put that file's path in the file-mediated
  delegation's prompt.
- File-mediated → checklist-driven: freeze the team's output first
  (template B's step 4), then pass the list of output file paths as the
  checklist's input.
- At every point where the primitive changes, write down the data
  hand-off path so a later stage never fails to find the previous
  stage's result.

---

## Writing principles for every template

1. **State the execution primitive at the top of the document.** For a
   mixed-primitive run, lay out each stage's primitive in a table.
2. **For checklist-driven delegation, spell out the procedure/script
   structure in detail.** Don't leave out the stage list, output-shape
   summary, or what the item list contains.
3. **For file-mediated coordination, spell out naming, messaging, and
   task-registration usage in detail.** Include the delegation roster,
   communication rules, task dependencies, and the output-freeze
   procedure at stage boundaries.
4. **For one-shot delegation, spell out every delegation parameter.**
   State whether it's a nameless, single-shot call, and specify the
   agent type, prompt, and output path.
5. **State file paths clearly.** Base paths on `_workspace/` and follow
   the `{phase}_{agent}_{artifact}.{ext}` naming rule.
6. **State dependencies between stages.** Be especially careful to spell
   out how data moves at any point where the execution primitive
   changes.
7. **Plan for errors that can actually happen.** Don't assume every task
   succeeds — define a response per situation.
8. **Always include test scenarios.** Write one happy-path scenario and
   at least one error-path scenario.
9. **Don't carry over anything specific to one proprietary tool's API.**
   If you find a reference to a tool-specific team-lifecycle call, a
   broadcast-to-everyone messaging construct, or an experimental-feature
   flag, that's a sign the orchestrator needs porting — see "Porting an
   existing tool-specific harness" in `execution-modes.md`.

## Follow-up-request phrasing for `description`

Add these phrasings so the skill gets selected again for revisions and
reruns, not just the first run:

- rerun, run again, update, fix, refine
- "just rerun the {part} of {domain}"
- "based on the previous result", "improve the result"
- phrasing specific to the domain's everyday vocabulary (e.g. a
  launch-strategy harness might add "launch", "promotion", "trending")

Without follow-up phrasing, this harness may not get selected again
after its first run.
