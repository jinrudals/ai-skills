# QA agent design guide

Guidance for including a QA agent in a harness you build. Based on real
bugs found in production projects and their root causes, this explains
how to catch the defects a QA agent typically misses.

---

## Table of contents

1. [Patterns of defects a QA agent misses](#1-patterns-of-defects-a-qa-agent-misses)
2. [Integration coherence verification](#2-integration-coherence-verification)
3. [QA agent design principles](#3-qa-agent-design-principles)
4. [Running QA at scale with checklist-driven delegation](#4-running-qa-at-scale-with-checklist-driven-delegation)
5. [Verification checklist template](#5-verification-checklist-template)
6. [QA agent definition template](#6-qa-agent-definition-template)

---

## 1. Patterns of defects a QA agent misses

### 1-1. Boundary mismatch between connected components

The most common defect. Two components are each correctly implemented
on their own, but follow different contracts at the point where they
connect.

| Boundary | Example mismatch | Why it's missed |
| --- | --- | --- |
| API response → frontend hook | The API returns `{ projects: [...] }` but the hook expects `Project[]`. | Each component is checked in isolation, never against the other. |
| API response field name → type definition | The API uses `thumbnailUrl` (camelCase), the type uses `thumbnail_url` (snake_case). | Asserting the type with a generic hides the mismatch from the compiler. |
| File path → link `href` | The page lives at `/dashboard/create` but the link points to `/create`. | File structure and `href` values are never cross-checked. |
| State-transition map → actual `status` updates | The map defines a transition but the code never performs it. | Checking that the map exists isn't the same as tracing the actual update code. |
| API endpoint → frontend hook | The API exists but no hook calls it. | The endpoint list and the hook list are never matched one-to-one. |
| Immediate response → async result | The API immediately returns `{ status }` but the frontend accesses a field only present in the final result. | Checking types alone doesn't distinguish the immediate response from the final one. |

### 1-2. Why static code review alone struggles to catch these

- **Generic types hide the mismatch**: `fetchJson<Project[]>()` compiles
  fine even when the actual response is `{ projects: [...] }`.
- **A successful build doesn't guarantee correct behavior**: code using
  type assertions, `any`, or loose generics can build successfully and
  still fail at runtime.
- **"Does the API exist" and "does the response match what the caller
  expects" are different checks**: confirming an API exists is a
  completely different task from confirming its response matches what
  the calling code actually expects.

## 2. Integration coherence verification

A QA agent must include verification that **cross-checks components
against each other.** The examples below use a Next.js-style app, but
the principle applies to any tech stack: open the producer code and the
consumer code together and compare their contracts.

### 2-1. Cross-check API response shape against frontend hook types

```
1. Extract the response shape at the API route's serialization point.
2. Check the type the corresponding hook/client expects.
3. Compare the response shape against that type. If the API returns
   { data: [...] }, confirm the hook actually unwraps .data.
```

Pay particular attention to: a paginated response wrongly treated as a
bare array, a missing snake_case ↔ camelCase conversion, and an
immediate response (e.g. HTTP 202) whose shape differs from the final
result.

### 2-2. Cross-check file paths against link/router paths

```
1. Extract URL patterns from the routing file structure. Strip route
   groups like (group); treat [param] as a dynamic segment.
2. Collect every href=, router.push(, redirect( value in the code.
3. Confirm each link actually matches an existing route.
```

### 2-3. Trace whether state transitions are fully implemented

```
1. Extract the list of allowed transitions from the state-transition map.
2. Search for every place that updates status.
3. Confirm every transition the code performs is defined in the map
   (no unauthorized transitions).
4. Find transitions defined in the map but never executed in the code
   (no dead transitions).
5. Specifically check for a missing transition from an intermediate
   state into a final state.
```

### 2-4. Match API endpoints and frontend hooks one-to-one

```
1. Extract the endpoint list by HTTP method.
2. Extract the list of fetch-call URLs on the client.
3. For any endpoint with no matching call, determine whether it's an
   admin-only API not meant to be called directly from the client, or
   whether the calling code is simply missing.
```

## 3. QA agent design principles

### 3-1. Choose an agent type with full tool access

If the QA agent uses a read-only exploration type, it can only read
files. Proper QA needs to search for patterns, run scripts to
automatically cross-check results, and fix code when needed. Choose a
full-access general type or a custom type with full tool access, and
spell out a "verify → report → request fix" procedure in the agent
definition.

### 3-2. Put cross-checked results in the checklist, not mere existence

| Shallow checklist | Cross-check-centered checklist |
| --- | --- |
| Does the API endpoint exist? | Does the API's response shape match the corresponding hook's type? |
| Is a state-transition map defined? | Does every piece of code that updates `status` match the transition map? |
| Does the page file exist? | Does every link in the code actually point to an existing page? |
| Is strict mode enabled? | Is there anywhere a generic type assertion bypasses type safety? |

### 3-3. Read both sides of a connection together

Finding a boundary bug requires reading more than one side. Read the API
route together with its corresponding hook, the transition map together
with the actual update code, and the file structure together with link
paths. State this principle explicitly in the agent definition.

### 3-4. Run QA as each module finishes, not only after everything is built

Running QA only after the whole implementation is done lets bugs pile
up, raising the cost of fixing them, and lets an early contract mismatch
propagate into later modules. Prefer **incremental QA**: cross-check
each API endpoint against its hook as soon as that endpoint is
finished.

## 4. Running QA at scale with checklist-driven delegation

If the boundaries to verify can be enumerated as a list, run the QA pass
itself as checklist-driven delegation.

```
Stage "inspect" (per boundary, independently):
  for each boundary {api, consumer} in a pre-extracted list:
    dispatch a delegation with: "read both sides together and find
    contract mismatches between {api} and {consumer}"
    → return { findings: [{ title, file, evidence }] }

Stage "re-verify" (per finding, in parallel, as soon as its boundary's
  inspection finishes — don't wait on other boundaries):
    dispatch a delegation with: "from the opposite perspective, verify
    whether this mismatch actually causes a runtime error: <finding>"
    → return { status: confirmed | refuted | uncertain, reason }

Keep only findings re-verified as "confirmed".
```

Re-verifying each finding from the opposite perspective, and keeping
only `confirmed` results, filters out plausible-looking but ultimately
non-issues — making the findings in the final QA report more
trustworthy.

## 5. Verification checklist template

Include the following integration-coherence checklist in a QA agent
definition for a web application.

```markdown
### Integration coherence verification (web app)

#### API ↔ frontend connections
- [ ] Every API route's response shape matches its hook's generic type.
- [ ] The hook correctly unwraps a wrapped response ({ items: [...] }) to get the actual data.
- [ ] snake_case ↔ camelCase conversion is applied consistently.
- [ ] The frontend distinguishes an immediate response (e.g. 202) from the final response's shape.
- [ ] Every API endpoint has a corresponding frontend hook that's actually called.

#### Routing coherence
- [ ] Every href/router.push value in the code matches an actual page file path.
- [ ] Route-group segments like (group) are correctly stripped when checking against the URL.
- [ ] Dynamic segments ([id]) receive the correct parameter value.

#### State machine coherence
- [ ] Every defined state transition is executed somewhere in the code (no dead transitions).
- [ ] Every status update in the code is defined in the transition map (no unauthorized transitions).
- [ ] No missing transition from an intermediate state into a final state.
- [ ] Every state referenced in a frontend branch (if status === "X") is actually reachable.

#### Data-flow coherence
- [ ] DB schema field names and API response field names map consistently.
- [ ] Frontend type definitions match the API response's field names.
- [ ] Optional-field null/undefined handling is consistent on both sides.
```

## 6. QA agent definition template

```markdown
---
name: qa-inspector
description: "A QA agent that verifies spec compliance, integration coherence, and design quality."
---

# QA agent

## Core role
Confirm the implementation matches spec, and verify **integration
coherence between modules.**

## Verification priority
1. **Integration coherence** (highest) — boundary contract mismatches
   are the leading cause of runtime errors.
2. **Functional spec compliance** — check the API, state machine, and
   data model.
3. **Design quality** — check colors, fonts, responsive behavior.
4. **Code quality** — check for dead code and naming conventions.

## Method: read both connected sides together
| What to verify | Producer | Consumer |
| --- | --- | --- |
| API response shape | Response serialization point | Type the client expects |
| Routing | Routing file structure | href, router.push values |
| State transitions | Transition map | status update code |
| DB → API → UI | DB table column names | API response field → type definition |

## Reporting and fix-request procedure
- On finding a problem, request a specific fix directly from the
  responsible agent (file:line + how to fix).
- If the problem is at a boundary, notify both sides' responsible
  agents.
- Send the leader a verification report that distinguishes passed,
  failed, and unverified items.
```

---

## Real-world cases: bugs found and their causes

| Bug | Boundary | Cause |
| --- | --- | --- |
| `projects?.filter is not a function` | API → hook | The API returns `{projects:[]}` but the hook expects an array. |
| Every link on the dashboard 404s | File path → `href` | The `/dashboard/` prefix is missing. |
| Thumbnail images don't render | API → UI component | `thumbnailUrl` and `thumbnail_url` don't match. |
| Selected value isn't saved | API → hook | The API exists but no corresponding hook does. |
| Creation page stays stuck pending | State transition → code | The code that moves it to its final state is missing. |
| Crash accessing `data.failedIndices` | Immediate response → frontend | The frontend accesses a background-processing result on the immediate response. |
| 404 opening the detail page after completion | File path → `href` | The route prefix doesn't match. |
