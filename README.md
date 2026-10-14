# ai-skills

Claude Code skills built for Hanon Systems work. Each directory under `skills/`
is one self-contained skill.

## Skills

| Skill | What it does |
|---|---|
| [`atlassian-cloud`](skills/atlassian-cloud/) | Jira Cloud and Confluence Cloud via direct REST calls (no MCP, zero dependencies). Issue/page CRUD, JQL/CQL search, attachments, macros. |
| [`bitbucket-cloud`](skills/bitbucket-cloud/) | Bitbucket Cloud via direct REST calls (no MCP, zero dependencies, Windows + POSIX). Repos, commits, pull requests, tasks, Pipelines, webhooks, permissions, issues, plus an API-token scope guide. |
| [`agent-harness`](skills/agent-harness/) | Designs a harness — a team of specialist agents plus the skills they follow — for a project, from a one-sentence domain description. Agentic-tool-agnostic: uses three portable execution primitives (checklist-driven delegation, file-mediated coordination, one-shot delegation) instead of any single vendor's orchestration API. A derivative of [revfactory/harness](https://github.com/revfactory/harness) (Apache-2.0; see the skill's `NOTICE`). |
| [`agent-harness-evolve`](skills/agent-harness-evolve/) | Retrospects on a running `agent-harness` harness and feeds generalized feedback back into its agents, skills, and change log. |

## PR checks

`.github/workflows/pr-checks.yml` runs on every pull request to `main`:

- **skills-structure** — `scripts/validate_skills.py`: each `skills/<name>/` has a `SKILL.md` whose frontmatter `name` matches the directory and `description` is non-empty.
- **python** — syntax check, `ruff` (errors only), and the `bitbucket-cloud` unit tests.
- **secrets** — gitleaks over the full history.

Run the structure check locally with `python scripts/validate_skills.py`.

## Installing a skill

Symlink it into your skills directory. A symlink is picked up without restarting
Claude Code, and edits in this repo take effect immediately:


To uninstall, remove the symlink — the repo is untouched:


Copying the directory works too, but then repo edits have to be re-copied.

## Conventions

A skill directory holds:

- **`SKILL.md`** — required. Frontmatter `name` plus a `description` dense with
  the words that should trigger it; the body is the workflow Claude follows.
  Keep it short enough to stay read in full.
- **`references/`** — the detail SKILL.md points at. Loaded on demand, so this is
  where length is affordable.
- **`scripts/`** — executables, with a `requirements.txt` if they have deps.
- **`assets/`** — files the skill needs at runtime (templates, fonts). These are
  the part that cannot be regenerated, so they are tracked in git.
- **`examples/`** — inputs that exercise the skill end to end. Run one after any
  change; it is the cheapest regression check available.

Python deps live in a `.venv/` **inside the skill**, so the skill stays
self-contained when copied and does not depend on the system interpreter.
`.venv/` is gitignored, so a fresh clone recreates it — see the skill's own
setup notes.
