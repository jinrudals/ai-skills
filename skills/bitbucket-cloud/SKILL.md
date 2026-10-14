---
name: bitbucket-cloud
description: >
  Use for Bitbucket Cloud (비트버킷 클라우드, bitbucket.org) work when no MCP
  server is configured — repositories and branches, pull request create /
  review / approve / merge, PR comments and tasks, commits / diffs / file
  contents, Pipelines (trigger, stop, logs), webhooks, repository
  permissions, and the issue tracker — via direct REST calls with a single
  zero-dependency Python script that runs on Windows and POSIX. Includes a
  guide for which API-token scopes to grant. Trigger words — Bitbucket,
  bitbucket.org, pull request, PR, pipeline, webhook, 비트버킷, 풀리퀘스트,
  파이프라인, 스코프. For Jira/Confluence use the atlassian-cloud skill.
---

# bitbucket-cloud — direct REST access to Bitbucket Cloud

Bitbucket Cloud REST API 2.0 (`https://api.bitbucket.org/2.0`) through one
stdlib-only script, `scripts/bitbucket_cloud.py`. Python 3.8+; use `python`
on Windows and `python3` on Linux/macOS.

**The Jira/Confluence API token does NOT work here.** Bitbucket needs its own
*scoped* API token, and scopes are **not hierarchical** (`admin:x` does not
include `read:x`/`write:x`). Read `references/setup.md` before creating one —
it has the exact scope presets.

## Setup (once per machine)

```bash
python3 scripts/bitbucket_cloud.py configure --email you@company.com --token <TOKEN> --workspace myworkspace
python3 scripts/bitbucket_cloud.py check
```

Config is written to `~/.config/bitbucket-cloud/credentials.json` (mode
`0600`) on POSIX or `%APPDATA%\bitbucket-cloud\credentials.json` on Windows.
Env vars win over the file: `BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN`,
`BITBUCKET_WORKSPACE`; `BITBUCKET_CLOUD_CONFIG` overrides the file path.
Without an email the token is sent as a Bearer token (repository/workspace
access tokens). PowerShell: `$env:BITBUCKET_API_TOKEN = "..."`.

Run `python3 scripts/bitbucket_cloud.py scopes --preset dev` to print the
scopes to tick when creating the token, or `scopes` alone to see the scopes
every command needs.

## Command shape

`bitbucket_cloud.py AREA ACTION [REPO] [IDS] [flags]` — areas: `repo`,
`commit`, `pr`, `task`, `pipeline`, `webhook`, `perm`, `issue`, plus
`configure`, `check`, `scopes`, `api`. Every command accepts `--workspace`,
`--limit` (list size, default 100) and `--yes`. Output is JSON (diffs and
logs are plain text).

```bash
python3 scripts/bitbucket_cloud.py repo list
python3 scripts/bitbucket_cloud.py repo branches myrepo --query feature
python3 scripts/bitbucket_cloud.py repo branch-create myrepo feature/x --from main
python3 scripts/bitbucket_cloud.py commit list myrepo --revision main
python3 scripts/bitbucket_cloud.py commit diff myrepo main..feature/x
python3 scripts/bitbucket_cloud.py commit file myrepo README.md --ref main

python3 scripts/bitbucket_cloud.py pr list myrepo --state OPEN
python3 scripts/bitbucket_cloud.py pr create myrepo --title "Fix" --source feature/x --dest main --body-file desc.md
python3 scripts/bitbucket_cloud.py pr diff myrepo 12
python3 scripts/bitbucket_cloud.py pr comment-add myrepo 12 --body "LGTM" --parent 345
python3 scripts/bitbucket_cloud.py pr approve myrepo 12
python3 scripts/bitbucket_cloud.py pr merge myrepo 12 --strategy squash --close-source-branch --yes
python3 scripts/bitbucket_cloud.py task add myrepo 12 --body "Update the docs" --comment 345
python3 scripts/bitbucket_cloud.py task update myrepo 12 99 --state RESOLVED

python3 scripts/bitbucket_cloud.py pipeline trigger myrepo --branch main --pattern deploy --var ENV=prod --yes
python3 scripts/bitbucket_cloud.py pipeline log myrepo '{pipeline-uuid}' --step '{step-uuid}'
python3 scripts/bitbucket_cloud.py webhook create myrepo --url https://x.example/h --event repo:push
python3 scripts/bitbucket_cloud.py perm set myrepo --user <account_id> --permission write --yes
python3 scripts/bitbucket_cloud.py issue create myrepo --title "Bug" --body "details" --kind bug
python3 scripts/bitbucket_cloud.py api GET /repositories/myworkspace/myrepo/pullrequests/12/activity
```

Quote UUIDs (`{…}`) in PowerShell and bash. Long text: use `--body-file`
(`-` reads stdin, UTF-8 safe).

## Safety rules

- **Destructive or hard-to-undo requests need `--yes`; without it the script
  prints a dry-run (method, URL, body) and exits 5 without sending.** Gated:
  `pr merge`, `pr decline`, `task delete`, `pipeline trigger`, `pipeline stop`,
  `webhook delete`, `perm set`, `perm remove`, and every non-GET `api` call.
  Show the dry-run to the user and get approval before re-running with `--yes`.
- Never echo, log, or commit the token; error messages are redacted.
- The script only talks to `api.bitbucket.org` and refuses other hosts.

## Exit codes

0 ok · 2 usage/config error · 3 auth or scope problem (401/403 — the message
names the scopes the command needs) · 4 other API error · 5 `--yes` required.

## References

- `references/setup.md` — **scope guide**: token creation, presets,
  command → scope table, Windows notes, 401/403 troubleshooting.
- `references/api-notes.md` — endpoint map, pagination, quirks.
- `examples/smoke_test.py` — opt-in read-only live check (`BITBUCKET_SMOKE=1`).
