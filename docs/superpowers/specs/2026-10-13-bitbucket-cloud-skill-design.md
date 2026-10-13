# bitbucket-cloud skill — design

## Goal

A skill that lets an agent work with **Bitbucket Cloud** through direct REST
calls (`https://api.bitbucket.org/2.0`) when no MCP server is configured.
It mirrors the existing `atlassian-cloud` skill: one dependency-free Python
script plus `SKILL.md`, `references/`, and `examples/`. That skill already
points to `bitbucket-cloud` for Bitbucket work.

Location: `skills/bitbucket-cloud/`

## Requirements

- **Python, stdlib only** (`urllib`, `json`, `argparse`, `base64`, `pathlib`).
- **Windows and POSIX** both supported (details below).
- **Scope:** repositories/branches, commits/diff/files, pull requests
  (create/review/merge), comments and tasks, Pipelines, webhooks,
  permissions, Issues, plus a generic `api` escape hatch.
- **Auth:** a Bitbucket-scoped API token. The Jira/Confluence token does not
  work for Bitbucket; a separate token with Bitbucket scopes must be created.

## Authentication and configuration

- Two shapes, auto-selected:
  - **Basic**: `email:token` (Atlassian account email + scoped API token).
  - **Bearer**: token only, used when no email is configured.
- Settings: `BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN`, `BITBUCKET_WORKSPACE`.
  Environment variables take priority over the config file.
- `configure` writes a credentials file and merges into an existing one.
  `BITBUCKET_CLOUD_CONFIG` overrides the path.
  - POSIX: `~/.config/bitbucket-cloud/credentials.json`, mode `0600`.
  - Windows: `%APPDATA%\bitbucket-cloud\credentials.json`; the chmod step is
    skipped.
- `check` calls `GET /user` and a workspace read, and on 403 reports which
  scope is probably missing.
- The token is never printed, logged, or included in error output.

## Commands

Form: `bitbucket_cloud.py <area> <action> [options]`.
The default workspace comes from configuration; `--workspace` overrides it.

| Area | Actions |
|---|---|
| `repo` | list, get, branches, branch-create, tags |
| `commit` | list, get, diff, file (content by path and ref) |
| `pr` | list, get, create, update, diff, comments, comment-add, approve, unapprove, request-changes, merge, decline |
| `task` | list, add, update, delete (PR tasks) |
| `pipeline` | list, get, trigger, stop, log |
| `webhook` | list, create, delete |
| `perm` | list and change user/group permissions |
| `issue` | list, get, create, update, comment |
| `api` | `METHOD /path` for anything else |

## Behavior

- **Pagination:** list commands follow the `next` URL, capped by `--limit`
  (sensible default).
- **Body input:** `--body`, `--body-file`, or `-` for stdin. Files are read
  as UTF-8.
- **Destructive actions** (`pr merge`, `pr decline`, all deletes, `perm`
  changes, `pipeline trigger`, `pipeline stop`, and non-GET `api` calls) do
  not execute without `--yes`. Without it they print the request that would be
  sent and exit non-zero.
- **Output:** JSON on stdout. Errors go to stderr with the HTTP status and
  Bitbucket's error message; exit codes distinguish usage, auth/scope, and API
  failures. Log output is raw text for `pipeline log`.
- **Encoding:** stdout and stderr are reconfigured to UTF-8 so Korean text
  does not break on Windows code pages.
- **Paths:** `pathlib` only; no shell-specific syntax in the script or the
  docs' examples beyond a note on `python` vs `python3`.

## Files

```
skills/bitbucket-cloud/
  SKILL.md                      # routing, setup summary, command overview, safety rules
  scripts/bitbucket_cloud.py    # the CLI
  references/setup.md           # creating the token, required scopes per area, Windows notes
  references/api-notes.md       # endpoint map, pagination, quirks
  examples/smoke_test.py        # opt-in live check (read-only)
  tests/test_bitbucket_cloud.py # offline unit tests (mocked HTTP)
```

`SKILL.md` front matter follows the `atlassian-cloud` style: name,
description with trigger words (Bitbucket, bitbucket.org, pull request, PR,
pipeline, 비트버킷, 풀리퀘스트, 파이프라인).

## Testing

- Offline unit tests with `unittest` and a mocked opener cover: auth header
  selection, config precedence and merge, pagination, `--yes` gating,
  token redaction, UTF-8 output, and Windows config-path selection (by
  patching `os.name`/environment).
- The live smoke test is read-only and opt-in; it needs real credentials.
- Endpoint paths and scope names are verified against the official Bitbucket
  Cloud REST docs during implementation, not taken from memory.

## Out of scope

OAuth flows, Bitbucket Data Center/Server, Git clone/push, and a
cross-skill shared library (the script stays self-contained, as in
`atlassian-cloud`).
