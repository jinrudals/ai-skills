# Setup

## 1. Find your site

- **Jira/Confluence site**: the subdomain in the URL you use to log in,
  `https://<site>.atlassian.net`. Set `ATLASSIAN_SITE=<site>` (bare subdomain,
  not the full URL — the script adds the scheme and domain). A full
  `https://...` URL also works if the subdomain scheme differs (e.g. a custom
  domain).

## 2. Create an API token

1. Go to <https://id.atlassian.com/manage-profile/security/api-tokens>.
2. "Create API token" (use "Create API token with scopes" if your org enforces
   scoped tokens; grant at least `read:jira-work`, `write:jira-work`,
   `read:confluence-content`, `write:confluence-content` for scoped tokens, or
   broader as needed).
3. Copy the token immediately — it is shown once. Store it as
   `ATLASSIAN_API_TOKEN`, never commit it to a repo.

This single token/email pair authenticates both Jira and Confluence Cloud.
It does **not** authenticate Bitbucket Cloud — Bitbucket requires its own
scoped API token and a different auth shape (username instead of email).
Use the separate `bitbucket-cloud` skill for that.

## 3. Store it globally (recommended) and verify

```bash
python3 scripts/atlassian_cloud.py configure \
  --site yourcompany --email you@yourcompany.com \
  --token xxxxxxxxxxxx

python3 scripts/atlassian_cloud.py jira issue-search "order by created DESC" --max-results 1
```

`configure` writes `~/.config/atlassian-cloud/credentials.json` with mode
`0600` and merges new flags into whatever is already there — safe to re-run
with just the one field you're rotating (e.g. `configure --token newvalue`
after rotating the token). It needs to be run **once per machine**; every
later shell, script, or tool invocation on that machine already has
credentials, no `export` required. Running `configure` again never loses
previously-set fields unless you pass a new value for that same flag.

Need per-project credentials instead of one global set? Point
`ATLASSIAN_CLOUD_CONFIG=/path/to/other.json` at a different file before
running `configure` or any other command — most users don't need this.

### Or: environment variables (session-scoped)

Skip the config file and export instead if you want per-session or CI-only
credentials; env vars always override the config file when both are present:

```bash
export ATLASSIAN_SITE=yourcompany
export ATLASSIAN_EMAIL=you@yourcompany.com
export ATLASSIAN_API_TOKEN=xxxxxxxxxxxx
```

A JSON payload with an `issues` array (even an empty one) means auth is good.
A `401` means the email/token pair is wrong; a `403` usually means the token
lacks the scope for that action.

## Never

- Never print or log `ATLASSIAN_API_TOKEN` values.
- Never hardcode credentials into a script or commit them — env vars and the
  config file (which is gitignored by convention — keep it that way) only.
- The config file holds a plaintext secret; `configure` sets `0600` automatically,
  but double-check that mode if you ever move or copy the file by hand.
