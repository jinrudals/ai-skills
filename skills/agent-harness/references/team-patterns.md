# Team patterns — the 6 base patterns, quality verification, agent definitions

This doc supplements steps 2-2 and 3 of `SKILL.md`. For each pattern it
names the execution primitive agent-harness recommends. Full primitive
detail is in `execution-modes.md`.

---

## Table of contents

1. [The 6 base patterns](#1-the-6-base-patterns)
2. [Quality verification patterns](#2-quality-verification-patterns)
3. [Composite patterns](#3-composite-patterns)
4. [Choosing an agent type](#4-choosing-an-agent-type)
5. [Agent definition structure](#5-agent-definition-structure)
6. [Criteria for splitting agents](#6-criteria-for-splitting-agents)
7. [Designing for agent reuse](#7-designing-for-agent-reuse)
8. [Skills vs. agents](#8-skills-vs-agents)

---

## 1. The 6 base patterns

### 1-1. Pipeline

Work proceeds through a fixed sequence of stages; one stage's output is
the next stage's input.

```
[analyze] → [design] → [implement] → [verify]
```

**Good fit:** each stage heavily depends on the previous stage's output.

**Example:** writing fiction — worldbuilding → characters → plot →
drafting → editing.

**Caution:** a delay at one stage delays the whole chain. Design each
stage to be as independent as possible.

**Recommended execution primitive:** if stages and items can be listed
ahead of time, prefer **checklist-driven delegation** with per-item
staging (no synchronization barrier between stages — each item advances
as soon as the previous stage finishes with it, so the whole run doesn't
wait on the slowest item). If a human needs to review the output between
every stage, call delegations one at a time instead.

### 1-2. Fan-out/fan-in

Independent work runs in parallel, then results are merged.

```
          ┌→ [specialist A] ─┐
[split] → ├→ [specialist B] ─┼→ [merge]
          └→ [specialist C] ─┘
```

**Good fit:** the same input needs independent analysis from several
angles or domains.

**Example:** comprehensive research — official sources, press,
community discussion, and background all researched concurrently, then
combined into one report.

**Caution:** how you merge the results determines overall quality.

**Recommended execution primitive:** prefer **checklist-driven
delegation** first — define the list of angles, dispatch one delegation
per angle, collect schema-conforming results, and merge in code/logic.
Use an all-results barrier only when you must deduplicate across every
result; that's the one case where you wait for every parallel call to
finish before moving on. For a small research team (2-4 people) that
needs to share findings live, **file-mediated coordination** also fits.

### 1-3. Expert pool

Only the specialist matching the input is called.

```
[classifier] → { specialist A | specialist B | specialist C }
```

**Good fit:** different input types need fundamentally different
handling.

**Example:** code review — only the security, performance, or
architecture specialist relevant to the input gets called.

**Caution:** if the classifier misclassifies the input, the wrong
specialist gets picked.

**Recommended execution primitive:** call the needed specialist once via
**one-shot delegation**. If the same specialist needs a follow-up
conversation, switch to a named, re-invokable delegation under
**file-mediated coordination**.

### 1-4. Producer-reviewer

A producer and a reviewer work as a pair.

```
[produce] → [review] → (if problems found) → [produce] again
```

**Good fit:** output quality must be verified against an objective
standard.

**Caution:** cap retries at 2-3 rounds so verify-and-revise doesn't loop
forever.

**Recommended execution primitive:** if verification criteria can be
expressed as a checklist, use **checklist-driven delegation** with the
adversarial-verification pattern below — verify each finding in
parallel. If the judgment is more subjective and needs negotiation, name
the producer and reviewer as a **file-mediated pair** and have them trade
feedback through the coordination file; because the producer keeps its
prior context, it can fix exactly the part that was flagged.

### 1-5. Supervisor

A central agent tracks progress and reassigns work as it comes in.

```
             ┌→ [worker A]
[supervisor] ─┼→ [worker B]    ← reassigned based on progress
             └→ [worker C]
```

**Good fit:** workload keeps changing, or how to split work can only be
decided mid-run.

**Difference from fan-out/fan-in:** fan-out/fan-in fixes the split
before starting. A supervisor watches progress and reassigns as it goes.

**Caution:** splitting work too finely makes the supervisor a bottleneck
— it ends up reassigning constantly.

**Recommended execution primitive:** use **file-mediated coordination**.
The orchestrating session, as leader, maintains the shared task list,
watches for completion, and reassigns work by updating that file and
re-invoking the relevant delegation. If the item list and assignment
logic actually can be fixed ahead of time, switch to checklist-driven
delegation instead — in that case there's no real judgment left for a
supervisor to make.

### 1-6. Hierarchical delegation

A delegated agent further delegates to sub-agents. Used to split a
complex problem across several levels.

```
[top-level] → [lead A] → [worker A1, A2]
            → [lead B] → [worker B1]
```

**Good fit:** the problem naturally splits into a parent task and child
tasks.

**Caution:** going three or more levels deep slows everything down and
loses prior context along the way. **Keep it to two levels.**

**Recommended execution primitive:** nest checklist-driven delegation
one level deep where the host tool supports invoking a named
sub-procedure from within a procedure; this naturally caps how deep the
nesting can go. Otherwise, flatten the hierarchy back into stages of a
single checklist-driven run.

## 2. Quality verification patterns

Add these verification patterns to any harness where output accuracy
matters. Their purpose is to catch results that look right but aren't.

| Pattern | Structure | Use when |
| --- | --- | --- |
| **Adversarial verification** | Run N independent adversarial verifiers against each finding. Only findings where more than half the verifiers mark `confirmed` with sufficient evidence pass. | Found content or claims must be trustworthy (review, audit, investigation) |
| **Multi-angle verification** | Instead of giving N adversarial verifiers the same prompt, assign each a different lens — accuracy, security, reproducibility. | Errors can take several different shapes. Splitting verification criteria catches what repeating the same check would miss. |
| **Judge panel** | Build N drafts independently (different approaches), judge them all in parallel. Write the final version based on the highest-scoring draft, folding in other drafts' strengths where useful. | Design or planning problems with many viable solutions — comparing several drafts beats endlessly revising one. |
| **Loop-until-dry** | Keep searching until K consecutive rounds turn up nothing new. Record rejected findings in a `seen` set too, so the same item isn't repeatedly re-proposed. | Open-ended search (bugs, issues, edge cases) where you don't know how many problems exist. Fixing the round count ahead of time risks missing later discoveries. |
| **Multi-angle sweep** | Run parallel searchers using different criteria — container, content, entity, time. | A single search criterion can't find everything. |
| **Gap reviewer** | A final agent whose only job is: what search criteria went unused, what claims went unverified, what material went unread? | Right before merging results. Anything it flags as missing feeds back into another search round. |
| **Disclose excluded counts** | When you cap coverage with a top-N or sampling approach, always log how many items were excluded. | Every fan-out. Without disclosing the excluded count, the user wrongly assumes full coverage. |

**Scaling principle:** size the effort to the scope the user asked for.
"See if there are any bugs" calls for a handful of searchers plus one
adversarial verifier. "Audit this thoroughly" calls for more searchers,
3-5 adversarial verifiers per finding, and a synthesis stage. When scope
is ambiguous, err toward careful/thorough for review/audit/investigation
requests, and small for quick checks.

> Implementation sketches are in `workflow-recipes.md`.

## 3. Composite patterns

Real work usually combines several patterns.

| Composite pattern | Shape | Example |
| --- | --- | --- |
| **Fan-out/fan-in + producer-reviewer** | Build several drafts concurrently, verify each independently | Multilingual translation — translate into four languages in parallel, each checked by a native-language reviewer |
| **Pipeline + fan-out/fan-in** | Some stages in a fixed sequence run part of their work in parallel | Analyze (sequential) → implement (parallel) → integration test (sequential) |
| **Supervisor + expert pool** | The supervisor calls whichever specialist fits the situation | Customer-inquiry handling — the supervisor classifies the inquiry, then assigns the matching specialist |
| **Search + adversarial verification + synthesis** | Multi-angle search → per-finding verification → gap review → report | Comprehensive code audit, deep investigation |

In a composite pattern, choose the right execution primitive per stage —
this is a mixed-primitive run. The deciding question at each stage is
still whether its control flow can be fixed ahead of time.

## 4. Choosing an agent type

When you invoke a delegation, specify its type through whatever
parameter the host tool uses for a custom agent/subagent type.

### Built-in types most host tools expose some version of

| Type | Tool access | Good fit |
| --- | --- | --- |
| Full-access general type | Everything, including web search/fetch | Web research, general work, editing files |
| Read-only exploration type | Read-only (no edit/write) | Locating code in a codebase. Don't use it for review or audit work. |
| Read-only planning type | Read-only (no edit/write) | Architecture design, writing an implementation plan |

### Custom types

Define a type as a file under this project's agent-definition convention
(`{agent-dir}/{name}.md`). Invoke it by referencing that name through
whatever parameter the host tool exposes for a custom agent/subagent
type. Set allowed tools and model tier in the file's frontmatter.

### Selection criteria

| Situation | Recommendation | Why |
| --- | --- | --- |
| Role is complex and reused across many sessions | **Custom type** | Keeps the specialist role and working principles consistent in one file. |
| A simple one-off research/collection task where a detailed prompt is enough | Full-access general type + detailed prompt | No need for a dedicated definition file. |
| Only locating code | Read-only exploration type | No edit tool, so no risk of an accidental wrong fix. |
| Only producing a design or plan | Read-only planning type | Keeps focus on analysis, no code changes. |
| A simple one-off file edit | Full-access general type + detailed prompt | Handle directly with a built-in type. |
| Implementation work that recurs or needs specialist rules | **Custom type** | Grants the needed tools and applies specialist guidance. |
| Several files edited in parallel | Custom type + file-isolation setting — default to a git worktree per delegation (see "Workspace isolation (git worktree)" in `references/execution-modes.md`) when the project is a git repo and the host tool supports it | Prevents delegations from clobbering each other's edits. Only use it when parallel edits can actually conflict — isolating a workspace has setup cost. |

**Principle:** define a specialist role you'll reuse across sessions as
a custom type under this project's agent directory. Don't create a
definition file for a one-off task that a built-in type already covers.

**Model policy:** choose a model tier by complexity, expected duration,
how much judgment the agent must exercise unsupervised, and required
response speed. Use **high-capability** for the hardest work that must
plan and run autonomously over a long horizon, and for orchestration
itself. Use **general-purpose** for design/architecture, code
generation, complex analysis, cross-verification, and creative work. Use
**fast** for low-judgment, well-defined work — log analysis, format
conversion, static file checks, running deploy scripts, simple
collection. Default to fast when the call is close. Don't assign the
same tier to every agent without reason — record the reason for each
choice as a comment. Full criteria are in `model-selection-guide.md`.

## 5. Agent definition structure

```markdown
---
name: agent-name
description: "One or two sentences on the role, listing the phrasings that should trigger it."
# tools: read, search-code, find-files, run-shell      ← optional: restrict available tools (e.g. a read-only reviewer)
#                                                          an agent that fixes output needs edit-in-place as well as write
# model: fast                                           ← pick per the task (model-selection-guide.md); comment the reason
---

# Agent Name — one-line role summary

You are a [role] specialist in [domain].

## Core role
1. Responsibility 1
2. Responsibility 2

## Working principles
- Principle 1 (explain *why* too — knowing the reason lets you judge correctly in edge cases)
- Principle 2

## Input/output rules
- Input: [where it comes from — file paths, parameters, prior stage's output]
- Output: [where it goes — a workspace path, or a structured return value]
- Format: [file format, structure, schema]

## Coordination notes (file-mediated coordination only)
- First report: tell the leader which tools are actually usable (to catch any `tools` entry that turned out unavailable)
- Receiving: [who sends it what]
- Sending: [who it sends what to]
- Shared tasks: [what kind of task it registers or requests]

## On re-invocation
- If prior output exists, read it and incorporate the requested improvement.
- Apply user feedback only to the affected part.

## Error handling
- [what to do on failure]
- [what to do when input is missing or ambiguous]

## Collaboration
- Relationship to other agents
```

**For agents used only in checklist-driven delegation:** replace
"Coordination notes" with a "Structured output" section. Spell out the
exact structure to return, and note that the final text is **return
data**, not a message sent to the user.

**Caveats when restricting tools:**

- Give an agent that fixes output both write and edit-in-place access.
  With write-only access, even a one-line fix means rewriting the whole
  file; on large output, the agent gives up on fixing it and works
  around it in a different file instead, leaving the original
  unfixed.
- Some lazily-loaded tools (shared task-list operations, live
  messaging) have been observed missing at call time even when listed
  as available, depending on the host tool and version — the boundary of
  what's actually granted isn't always obvious ahead of time. Have
  named delegations report, in their first update, exactly which tools
  are usable. If one is missing, either have the orchestrator take over
  that part of the work (e.g. the leader updates the shared task list
  itself) or loosen the tool restriction in the definition file.

## 6. Criteria for splitting agents

| Criterion | Split | Merge |
| --- | --- | --- |
| Expertise | Split if the domains differ | Merge if the domains overlap |
| Parallelism | Split if the work can run independently | Consider merging if it must run in sequence |
| Context needed | Split if one agent would need a lot of information | Consider merging if little information is needed and the task is short |
| Reusability | Split if other teams could reuse it | Consider merging if only this team uses it |

## 7. Designing for agent reuse

Before creating a new agent, compare its role against the existing
agents in this project's agent directory. Building or extending a
harness repeatedly is exactly how same-role agents pile up under
different names.

| Relationship to an existing agent | Action |
| --- | --- |
| An existing agent already covers the new role entirely | Don't create a new one — call the existing agent. |
| Partial overlap, and generalizing the existing agent would cover the new role too | Generalize and extend the existing agent. |
| Partial overlap, but the domain is deliberately specialized | Create a separate, new agent. |
| Scope is entirely different | Create a new agent. |

**Principle:** an agent focused on one role is easier to reuse and
creates less duplication. If extending ends up giving an agent two or
more roles, check first whether it should be split instead.

**When extending an existing agent:** the orchestrator(s) that call it
may change behavior too. Before extending, check which orchestrator(s)
call this agent, and update its `description` to reflect the now-wider
role. After extending, dry-run (`SKILL.md` step 6-5) to confirm existing
flows still work.

## 8. Skills vs. agents

| | Skill | Agent |
| --- | --- | --- |
| Defines | A procedure and a toolkit | A specialist role and behavioral principles |
| Lives in | This project's skill directory | This project's agent directory |
| Triggers | When a user request matches the applicability conditions in `description` | When directly invoked via a delegation call |
| Answers | "How is it done" | "Who does it" |

### Wiring a skill to an agent

| Method | Implementation | Good fit |
| --- | --- | --- |
| **Invoke the skill-loading mechanism** | State in the agent's prompt that it should load/invoke the named skill | The skill is an independent procedure a user might also invoke directly |
| **Inline in the prompt** | Write the skill's content directly into the agent definition | The skill is 50 lines or less and only this agent uses it |
| **Load a reference file on demand** | Read the skill's `references/` file only when needed | The skill has a lot of content needed only under specific conditions |

A skill shared by several agents should be invoked through the host
tool's normal skill-loading mechanism. A short skill used by only one
agent can be inlined directly; if it has a lot of content, only load the
specific reference file actually needed.
