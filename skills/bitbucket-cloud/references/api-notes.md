# API notes

Base URL `https://api.bitbucket.org/2.0`. Scopes were verified against
`https://api.bitbucket.org/swagger.json` (`x-atlassian-oauth2-scopes`).

## Endpoint map

`R` = `/repositories/{workspace}/{repo}`

| Area | Endpoints |
|---|---|
| repo | `GET /repositories/{ws}`, `R`, `R/refs/branches`, `R/refs/tags`; `POST R/refs/branches` |
| commit | `R/commits[/{rev}]`, `R/commit/{sha}`, `R/diff/{spec}` (text), `R/src/{ref}/{path}` (text) |
| pr | `R/pullrequests[/{id}]`, `/diff` (text), `/comments`, `/approve` (POST/DELETE), `/request-changes`, `/merge`, `/decline` |
| pr (mine) | `GET /workspaces/{ws}/pullrequests/{account_id}` (use `pr mine`) |
| task | `R/pullrequests/{id}/tasks[/{task_id}]` |
| pipeline | `R/pipelines/` (trailing slash), `/{uuid}`, `/{uuid}/stopPipeline`, `/{uuid}/steps/`, `/{uuid}/steps/{step}/log` (text) |
| webhook | `R/hooks[/{uid}]` |
| perm | `R/permissions-config/users[/{account_id}]`, `.../groups[/{slug}]` |
| issue | `R/issues[/{id}]`, `/comments` |

## Behaviour

- **My PRs:** use `pr mine`. The global `GET /pullrequests/{uuid|account_id}`
  and `GET /user/permissions/repositories` return 404 (deprecated); do not
  call them or scan repos one by one. The workspace-scoped form works with
  either a UUID or an `account_id`.
- **Pagination:** list commands follow the `next` link until `--limit` items
  are collected. Pagination links are only followed on `api.bitbucket.org`.
- **Text vs JSON:** diffs, file contents and step logs are returned as raw
  text and printed as-is (UTF-8). A 204/empty response prints `{"ok": true}`.
- **Pipelines** require the trailing slash on `/pipelines/`. Trigger target
  is `pipeline_ref_target` with `ref_type: branch`; `--pattern` adds a custom
  `selector`. `--var KEY=VALUE` splits on the first `=`.
- **Merge** sends `type: pullrequest_merge_parameters` plus only the flags
  you passed. Strategies: `merge_commit`, `squash`, `fast_forward`,
  `squash_fast_forward`, `rebase_fast_forward`, `rebase_merge`.
- **Decline** reason is sent as `{"reason": ...}`; the reference documents no
  request body, so the server may ignore it.
- **Tasks** need only `read:pullrequest` per the reference (even for writes).
- **Permissions** are set per user (Atlassian account id) or group slug.
- **Issues:** the published OpenAPI file has no issue-tracker paths, so these
  paths/scopes follow the documented convention and are unverified. The
  tracker must be enabled on the repository.
- **Security:** `Authorization` is dropped on cross-host redirects, requests
  to hosts other than `api.bitbucket.org` are rejected, and the token is
  redacted from error output.
