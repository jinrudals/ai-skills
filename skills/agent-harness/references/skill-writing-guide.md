# Skill-writing guide

Detailed guidance for raising the quality of skills built with
agent-harness. Supplements step 4 of `SKILL.md`.

---

## Table of contents

1. [Writing `description`](#1-writing-description)
2. [Body-writing style](#2-body-writing-style)
3. [Defining output format](#3-defining-output-format)
4. [Writing examples](#4-writing-examples)
5. [Progressive disclosure](#5-progressive-disclosure)
6. [When to bundle a script](#6-when-to-bundle-a-script)
7. [Data schema standards](#7-data-schema-standards)
8. [What not to put in a skill](#8-what-not-to-put-in-a-skill)
9. [Designing for skill reuse](#9-designing-for-skill-reuse)

---

## 1. Writing `description`

The fields a host agent sees are `name` and `description`; concrete
trigger conditions go in `description`. The host agent reads both to
decide which skill to use.

### How skill selection tends to work

Host agents tend not to invoke a skill for simple work their built-in
tools can already handle easily. A simple request like "read this PDF"
may not trigger a skill even with a well-written `description`. The more
a task requires multiple steps or specialist judgment, the more likely a
skill gets invoked.

### Writing principles

1. State both **what the skill does** and **the concrete situations
   that should trigger it**.
2. If there are look-alike situations that should *not* trigger the
   skill, state the scope and exclusions clearly.
3. Since host agents tend to be conservative about invoking a skill,
   phrase the trigger conditions somewhat assertively.
4. For a skill that orchestrates multi-step work, always include
   **phrases for follow-up work** (rerun, fix, refine, improve the
   previous result).

### Good example

```yaml
description: >
  Reads PDF files, extracts text and tables, merges, splits, rotates,
  watermarks, encrypts/decrypts, and OCRs. Always use this when the
  user mentions a .pdf file or asks for a PDF deliverable. Especially
  useful for conversion/editing/analysis beyond a plain "read this
  PDF" request.
```

### Bad examples

- `"A skill for processing data"` — too vague to tell which files or
  tasks it covers.
- `"PDF-related work"` — doesn't say what it can do or when to use it.

## 2. Body-writing style

### Explain why first

A large language model that understands *why* a rule exists can judge
correctly even in edge cases. Stating the reason behind a rule works
better than listing only what to do and not do.

**Bad example:**

```markdown
Always use pdfplumber for table extraction. Never use PyPDF2 for tables.
```

**Good example:**

```markdown
Use pdfplumber for table extraction. PyPDF2 is built for text extraction
and doesn't preserve a table's row/column structure, while pdfplumber
recognizes cell boundaries and returns structured data.
```

### Generalize to principles that apply across cases

When feedback or testing surfaces a problem, don't just add an
instruction that fixes that one example. Rewrite it as a principle that
generalizes.

**Overfit fix:** `If there's a "Q4 Revenue" column, convert it to a number.`

**Generalized fix:** `If a column name contains a quantity word like
"revenue", "amount", or "quantity", convert that column to a numeric
type. Leave unconvertible values as-is.`

### Write as directives

Use "do this"/"always do X" phrasing, not "you could do this" or hedged
language. A skill is an instruction document an AI agent must follow.

### Reduce how much must be held in context at once

A model's working context is limited, and that limit covers everything
needed for the task, not just the skill's own instructions. For every
sentence, weigh its token cost against these questions:

- "Does the agent already know this?" → delete it.
- "Would leaving this out cause a mistake?" → keep it.
- "Would one concrete example be clearer than this long explanation?" →
  replace it with an example.

## 3. Defining output format

For a skill where output format matters, spell out the structure to
follow.

```markdown
## Report structure
Follow this template exactly.

# [Title]
## Summary
## Key findings
## Recommendations
```

Keep the format description short and pair it with a real example —
this is more effective than a long explanation alone.

**Output a later checklist-driven stage will read programmatically:** if
a later stage parses this output as code, specify a **structured data
shape** (e.g. a small JSON schema) instead of a markdown template, and
note that the final text is not a user-facing message but return data
for the next stage. Where the host tool enforces a schema on a
delegation's structured return, keep the skill's documented shape and
the dispatching code's schema in sync.

## 4. Writing examples

A concrete example conveys a rule more clearly than a long explanation.

```markdown
## Commit message format

**Example 1:**
Input: add user authentication using JWT tokens
Output: feat(auth): implement JWT authentication

**Example 2:**
Input: fix bug where password visibility toggle doesn't work on login page
Output: fix(login): fix password visibility toggle
```

## 5. Progressive disclosure

### Method 1: split files by subject area

```
bigquery-skill/
├── SKILL.md (overview + guidance on which subject-area file to load)
└── references/
    ├── finance.md (revenue, billing metrics)
    ├── sales.md (opportunities, pipeline)
    └── product.md (API usage, features)
```

If the user asks about revenue, load only `finance.md`.

### Method 2: load detailed instructions only when needed

```markdown
## Document editing
For simple edits, modify the XML directly.
**If change tracking is needed**, see [REDLINING.md](references/redlining.md).
```

### Method 3: put a table of contents in long reference docs

For reference docs over 300 lines, add a table of contents near the top
of the file.

## 6. When to bundle a script

Look at the work logs from agents that ran your tests. If the same
pattern keeps recurring, fold the script or procedure into the skill.

| Recurring pattern | Action |
| --- | --- |
| The same helper script gets rewritten in all three test runs. | Put the script in `scripts/`. |
| The same install command runs every time. | Document the dependency-install step in the skill. |
| The same multi-step procedure gets followed every time. | Write the standard procedure into the skill body. |
| The same workaround follows a similar error every time. | Document the known issue and its fix in the skill. |

Always run and verify any script you bundle into a skill.

## 7. Data schema standards

Use the following standard schemas so data flows consistently between
skills. The same schemas apply when testing and evaluating skills built
with agent-harness.

### `eval_metadata.json`

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "the user's task prompt",
  "assertions": [
    "the output includes X",
    "a file was produced in Y format"
  ]
}
```

### `grading.json`

```json
{
  "expectations": [
    {
      "text": "the output includes 'Seoul'",
      "passed": true,
      "evidence": "confirmed 'extracted Seoul-region data' in stage three"
    }
  ],
  "summary": { "passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0 }
}
```

**Field-name note:** use exactly `text`, `passed`, and `evidence`. Don't
rename them to `name`/`met`/`details` or similar.

### `timing.json`

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

As soon as a delegation's completion notification arrives, save
`total_tokens` and `duration_ms` immediately — both values are only
visible at that moment and can't be recovered later.

## 8. What not to put in a skill

- Supplementary docs like `README.md`, `CHANGELOG.md`, `INSTALLATION_GUIDE.md`
- Information only needed while building the skill (test results,
  revision history)
- End-user documentation (a skill is an instruction document for an AI
  agent, not a user manual)
- General knowledge the host agent already has
- Anything specific to one proprietary multi-agent API that doesn't
  port (a tool-specific team-lifecycle call, an environment flag needed
  only to unlock one tool's experimental feature, a blanket model tier
  assigned to every agent without reason)

## 9. Designing for skill reuse

Before creating a new skill, compare its functionality against the
existing skills in this project's skill directory. Building or
extending a harness repeatedly is exactly how same-purpose skills pile
up under different names.

| Relationship to an existing skill | Action |
| --- | --- |
| An existing skill already covers the new functionality entirely | Don't create a new one — wire the existing skill to the agent. |
| Partial overlap, and generalizing the existing skill would cover the new functionality too | Generalize and extend the existing skill. |
| Partial overlap, but the domain is deliberately specialized | Create a separate, new skill. |
| Functionality scope is entirely different | Create a new skill. |

**Principle:** a skill focused on one role is easier to reuse and
creates less duplication. If a role ends up covering two or more
responsibilities, check first whether it should be split.

### How far to generalize

Generalization has no natural stopping point on its own, so stop at the
boundary of the responsibility the skill was actually meant to own.
Strip off accidental coupling, but keep deliberate domain specialization.

For example, generalizing a "fintech risk-assessment PDF" skill might go:

| Coupling stripped | Result |
| --- | --- |
| Fintech | "assessment-result PDF". If the skill's responsibility is assessment reports, stop here. |
| Assessment | "PDF formatting". If a skill with this exact functionality already exists, use it instead of creating a new one. |

If the skill's responsibility was deliberately scoped to "fintech risk
assessment" from the start, don't generalize it — keep it as a separate
skill.

Extending an existing skill can change the behavior of agents that use
it. Before extending, check which agents use this skill, and update its
`description` to reflect the now-wider scope.
