# Model selection guide

Choose a model tier for each agent using four criteria: the task's
**complexity, expected duration, required autonomy, and response-speed
needs.** Set the tier wherever this project's agent-definition format
exposes a model field — typically the agent definition file's
frontmatter, or a per-call model parameter on the host tool's delegation
mechanism. Record the reason as a comment in the agent definition or
orchestrator.

This guide uses three portable tiers — **high-capability**,
**general-purpose**, and **fast** — instead of any single vendor's model
names, since different host tools expose different model catalogs. Map
each tier to whatever models your host tool actually offers: typically
its strongest/most expensive reasoning model for high-capability, its
standard default model for general-purpose, and its smallest/fastest
model for fast. If your tool only exposes one or two tiers, collapse
accordingly and note that limitation in the orchestrator.

## Summary decision table

| Tier | Selection criteria | Representative work |
| --- | --- | --- |
| **high-capability** | A long-horizon, autonomous model that plans for itself from a complex goal and carries multiple linked steps through to a final deliverable | Hard reasoning, creative work, agent orchestration, work that must be planned and carried out autonomously over a long horizon |
| **general-purpose** | A reasoning-focused model for deeply analyzing a professional, complex problem to a refined judgment or conclusion | Design/architecture, code generation, complex analysis, cross-verification, creative work |
| **fast** | A balanced general model for most everyday work — writing, coding, analysis, research | General writing/coding/research, log parsing, format conversion, static file checks, running deploy scripts, simple collection |

## 1. High-capability

**Core role:** suited to the hardest work that requires planning and
running autonomously over a long horizon. Rather than just answering a
question directly, it understands a goal, plans multiple stages, carries
them out in sequence, and produces a final deliverable.

### Good fit

**① Long-horizon, multi-stage work** — use it when the work isn't a
single answer but a sequence of tasks performed in order.
- Market research → competitor analysis → strategy → report
- Requirements analysis → service architecture → development plan → deliverables
- Reviewing multiple documents and producing a synthesized conclusion and action plan
- Designing the full course of a long-running project

What matters is that stages aren't isolated — **the result of an earlier
stage shapes the next one.**

**② Reviewing large, complex material** — use it when you need to
jointly review large volumes of complex material (papers, reports,
meeting notes, technical documents) and do more than summarize it.
- Analyzing similarities and differences across multiple sources
- Identifying conflicting claims
- Distinguishing core evidence from peripheral information
- Synthesizing a large body of material into one coherent deliverable

**③ Turning a vague idea into a concrete deliverable** — use it when
requirements aren't fixed and only a rough idea is given, and the model
must decide the missing details itself to produce the deliverable.
- Developing "a service kind of like this" into a business proposal
- Designing a presentation's structure and content from just a rough topic
- Turning an incomplete product idea into a feature list and development plan
- Producing a finished report or piece of content with no draft to start from

Choose this tier when **the ability to judge and fill in what's
missing** matters more than the ability to follow a fixed set of
instructions.

**④ Problems needing deep reasoning together with planning,
coordination, and long-horizon execution** — a high-capability model
isn't unconditionally "deeper" at reasoning than a general-purpose one.
It's the better fit specifically when deep reasoning must be combined
with planning, coordination, and long-horizon execution.

### When to choose high-capability

- When reaching the result takes several stages
- When the user can't specify every step themselves
- When the model itself must plan the order of work
- When a finished deliverable must be produced from a large body of material
- When a project-level result is needed, not a short answer

## 2. General-purpose

**Core role:** a high-performance reasoning model for deeply analyzing
and solving hard problems. Where high-capability suits long-horizon
planning and autonomous execution, general-purpose suits digging deeply
and logically into a problem whose scope is already fixed.

### Good fit

**① Complex research and analysis** — work that doesn't stop at finding
information, but requires weighing multiple pieces of evidence to reach
a logical conclusion.
- Deep research into a complex industry or market
- Comparative analysis across multiple studies
- Weighing the pros and cons of a policy or business strategy
- Cause-and-effect analysis from data and documents
- Writing a conclusion that synthesizes different viewpoints

**② Reviewing long technical documents** — reading and understanding
documents dense with jargon and complex structure: software design
docs, system architecture docs, research papers, technical
specifications, product requirements docs, complex API/dev docs. Suited
to **grasping logical structure and technical meaning**, not just
condensing the document.

**③ Reviewing research methodology** — scrutinizing not just a study's
results but whether the method that produced them is sound.
- Checking whether the research design is appropriate, the sample is
  sufficient, and the sample isn't biased
- Checking the measurement approach and statistical conclusions for
  problems
- Checking whether the conclusion overreaches the actual evidence, or
  admits other interpretations

**④ Coding that carries out several development steps autonomously** —
not just producing a line or two of code, but understanding a goal and
carrying out a linked sequence of development tasks.
- Analyzing an existing codebase and tracking down a bug's root cause
- Editing code across several files, implementing a feature, writing tests
- Improving code structure and deciding the next development step itself

### When to choose general-purpose

- The problem is professional and hard, but **its scope is relatively clear**
- Deep logical analysis and review are needed
- A technical document or paper must be understood precisely
- Finding holes in research or analysis
- Solving a complex coding or technical problem

## 3. Fast

**Core role:** a balanced, general-purpose model that handles most
everyday work reliably. Suited to writing, coding, research, and
analysis broadly, outside work that demands exceptional complexity or
specialist judgment.

### Good fit

**① Writing and content production** — emails, blog posts, report
drafts, ad copy, proofreading/rewriting, presentation scripts, social
content planning, brainstorming.

**② General coding work** — writing functions, fixing bugs, building
simple programs, explaining existing code, refactoring, writing test
code, building data-processing scripts.

**③ Analysis and research** — summarizing a topic, comparing
products/services, analyzing document content, light competitor
research, extracting key claims, comparing pros/cons, organizing
analysis into a table or report.

**④ Multi-step problems with a clear scope** — breaking a well-scoped
task into stages: summarizing material then writing a presentation,
analyzing requirements then producing a code example, analyzing data
then explaining the result. Distinct from the long-horizon, autonomous
projects that call for high-capability.

**⑤ Repetitive/operational work** — log parsing, format conversion,
static file checks, running deploy scripts, simple collection.

### When to choose fast

- When you're unsure which tier to pick — default to fast when the call is close.
- When everyday work needs to be done quickly and reliably.
- When the work mixes writing, coding, and research together.
- When the problem is neither trivially simple nor especially complex.
- When both speed and result quality matter.

## Distinguishing high-capability from general-purpose

- **High-capability**: plans the whole task and carries it out
  autonomously over a long horizon.
- **General-purpose**: reasons deeply about and analyzes one hard
  problem whose scope is fixed.

For example, deeply critiquing a single paper calls for
**general-purpose**; reviewing dozens of papers to build a research
strategy and produce a final report calls for **high-capability**. Use
high-capability when an earlier stage's result shapes the next one and
the model must carry multiple stages forward itself. Use
general-purpose when you need deep analysis of one well-scoped problem.

## Applying this in a harness

1. **Judge by the task, not the agent's perceived status** — don't pick
   a tier because "this is an important agent." Choose based on the
   actual task's complexity, expected duration, required autonomy, and
   response-speed need.
2. **Don't blanket-assign the same tier without reason** — assigning
   high-capability or general-purpose to every agent just inflates cost.
   Pick the right tier per agent and record the reason as a comment.
3. **Distinguish the coordination layer from the execution layer** —
   even if the planning/coordination layer (the main session, or a
   supervisor agent) uses high-capability, pick each worker agent's tier
   independently based on its own task. A high-capability orchestrator
   doesn't require high-capability workers underneath it.
4. **Pick per stage in checklist-driven delegation** — where the host
   tool lets you set a model per dispatched delegation, vary it by
   stage: fast for repetitive collection/transformation stages,
   general-purpose for deep verification/judging/design stages, and
   high-capability for stages that plan and carry out long-horizon
   execution.
