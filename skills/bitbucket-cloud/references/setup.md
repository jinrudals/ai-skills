# Setup and scope guide

## 1. Create the API token

1. Bitbucket → avatar → **Personal settings** → **Atlassian account settings**
   → **Security** → **Create and manage API tokens** → **Create API token with
   scopes**.
2. Name it, set an **expiry** (required; max 1 year), choose **Bitbucket** as
   the app.
3. Tick the scopes for your preset below (**not hierarchical**: `admin:*`
   grants neither read nor write, so tick every scope you need).
4. Copy the token once; it is never shown again.
5. Configure: `python3 scripts/bitbucket_cloud.py configure --email <atlassian-email> --token <TOKEN> --workspace <slug>` then `check`.

The plain Atlassian API token used for Jira/Confluence does **not** work for
Bitbucket. Auth is Basic `email:token` (your Atlassian account email, not the
Bitbucket username). Repository/workspace **access tokens** use Bearer auth:
configure with `--token` only (no email); they use OAuth-style scope names and
cannot manage permissions.

## 2. Pick a preset

`python3 scripts/bitbucket_cloud.py scopes --preset <name>` prints the list.

**read-only** — browse repos, PRs, pipelines, issues:

- `read:repository:bitbucket`
- `read:pullrequest:bitbucket`
- `read:pipeline:bitbucket`
- `read:issue:bitbucket`
- `read:webhook:bitbucket`
- `read:user:bitbucket`
- `read:workspace:bitbucket`

**dev** (recommended) — read-only plus:

- `write:repository:bitbucket`
- `write:pullrequest:bitbucket`
- `write:pipeline:bitbucket`
- `write:issue:bitbucket`

**admin** — dev plus webhook/permission management:

- `write:webhook:bitbucket`
- `delete:webhook:bitbucket`
- `admin:repository:bitbucket`
- `write:permission:bitbucket`
- `delete:permission:bitbucket`
- `delete:issue:bitbucket`

`admin:project` and `admin:workspace` are never needed.
`read:user` + `read:workspace` are needed only by `check`.

## 3. Command → scopes

Scope names below omit nothing: each is `<verb>:<resource>:bitbucket`.
`scopes` (no flag) prints the same table from the code.

| Command | Scopes |
|---|---|
| `check` | `read:user:bitbucket`, `read:workspace:bitbucket` |
| `repo list`, `repo get`, `repo branches`, `repo tags` | `read:repository:bitbucket` |
| `repo branch-create` | `write:repository:bitbucket`, `read:repository:bitbucket` |
| `commit list/get/diff/file` | `read:repository:bitbucket` |
| `pr list/get/diff/comments/comment-add`, all `task` commands | `read:pullrequest:bitbucket` |
| `pr mine` | `read:pullrequest:bitbucket`, `read:user:bitbucket` |
| `pr create/update/approve/request-changes/merge/decline` | `read:pullrequest:bitbucket`, `write:pullrequest:bitbucket` |
| `pr unapprove` | `write:pullrequest:bitbucket` |
| `pipeline list/get/log` | `read:pipeline:bitbucket` |
| `pipeline trigger` | `read:pipeline:bitbucket`, `write:pipeline:bitbucket` |
| `pipeline stop` | `write:pipeline:bitbucket` |
| `webhook list` | `read:webhook:bitbucket` |
| `webhook create` | `read:webhook:bitbucket`, `write:webhook:bitbucket` |
| `webhook delete` | `delete:webhook:bitbucket` |
| `perm list` | `read:repository:bitbucket` |
| `perm set` | `admin:repository:bitbucket`, `write:permission:bitbucket` |
| `perm remove` | `admin:repository:bitbucket`, `delete:permission:bitbucket` |
| `issue list/get` | `read:issue:bitbucket` |
| `issue create/update/comment` | `read:issue:bitbucket`, `write:issue:bitbucket` |
| `api` | whatever the endpoint needs |

Issue-tracker scopes follow Bitbucket's naming convention; they were not
present in the published OpenAPI file, so confirm with `issue list` if you
use that area. The issue tracker must also be enabled in the repository.

## 4. Windows notes

- Use `python` (or `py -3`). Config lives in
  `%APPDATA%\bitbucket-cloud\credentials.json`; file-mode hardening is a
  POSIX-only step, so protect the folder with normal user permissions.
- PowerShell env vars: `$env:BITBUCKET_API_TOKEN = "..."`,
  `$env:BITBUCKET_EMAIL = "..."`, `$env:BITBUCKET_WORKSPACE = "..."`.
  `cmd.exe`: `set BITBUCKET_API_TOKEN=...`.
- Quote UUIDs: `'{3f2a-...}'` in PowerShell, `"{...}"` in cmd.
- Output is forced to UTF-8; if a legacy console garbles Korean text, run
  `chcp 65001` or `$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()`.

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| exit 3, 401 | Wrong email/token, expired token, or a Jira-only token. Recreate with Bitbucket scopes; email must be the Atlassian account email. |
| exit 3, 403 | Missing scope — the error lists what the command needs. Scopes cannot be edited; create a new token with the right ones. |
| 403 but scopes right | Your Bitbucket role lacks access to that repo/workspace (permissions still apply on top of scopes). |
| 404 on a repo | Wrong workspace slug or repo slug (use the slug, not the display name); private repos return 404 without access. |
| `no workspace` (exit 2) | Pass `--workspace` or run `configure --workspace NAME`. |
| exit 5 | The command is gated; review the dry-run and re-run with `--yes`. |
