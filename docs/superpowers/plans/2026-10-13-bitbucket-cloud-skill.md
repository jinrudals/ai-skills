# bitbucket-cloud Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `skills/bitbucket-cloud/`: a stdlib-only, Windows-compatible Python CLI plus docs (including a scope guide) for Bitbucket Cloud REST work.

**Architecture:** One self-contained script `scripts/bitbucket_cloud.py`. A single `COMMANDS` table (area, action, HTTP method, path template, required scopes, destructive flag) drives the argparse tree, dispatch, the `--yes` gate, the `scopes` command, and 403 hints. Handlers are only written where a command builds a body or post-processes output.

**Tech Stack:** Python 3.8+ stdlib (`urllib`, `json`, `argparse`, `base64`, `pathlib`, `unittest`). No third-party packages.

**Spec:** `docs/superpowers/specs/2026-10-13-bitbucket-cloud-skill-design.md`

## Global Constraints

- Python stdlib only; works on Windows and POSIX.
- API base: `https://api.bitbucket.org/2.0`.
- Settings: `BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN`, `BITBUCKET_WORKSPACE`; env beats config file; `BITBUCKET_CLOUD_CONFIG` overrides the config path.
- Config path: POSIX `~/.config/bitbucket-cloud/credentials.json` (mode `0600`); Windows `%APPDATA%\bitbucket-cloud\credentials.json` (no chmod).
- Auth: Basic `email:token` when an email is set, else `Bearer token`.
- The token never appears in stdout, stderr, logs, or dry-run output.
- API token scopes are not hierarchical: a write scope never implies its read scope.
- Destructive actions need `--yes`; without it, print the would-be request and exit non-zero.
- stdout/stderr reconfigured to UTF-8. Body input: `--body`, `--body-file`, or `-` (stdin), UTF-8.
- Exit codes: 0 ok, 2 usage/config, 3 auth or scope (401/403), 4 other API error, 5 `--yes` required.
- Lists follow the `next` URL, capped by `--limit` (default 100).
- Tests: `python -m unittest discover -s skills/bitbucket-cloud/tests -v` (use `python3` on POSIX).

## Review Focus

1. Branch names and file paths containing `/`, spaces, or Korean (`feature/한글`) must be URL-quoted correctly in `refs`, `src`, and `diff` paths.
2. Empty results print `[]`, and `--limit` smaller than one page returns exactly that many items.
3. Non-JSON error bodies (HTML gateway page, empty body) produce a clean error with the HTTP status, not a traceback.
4. A UTF-8 BOM or CRLF in a `--body-file`, and Korean text on a cp949 console, do not corrupt the request or crash output.
5. `api POST|PUT|DELETE|PATCH` is gated like the named destructive commands, and dry-run output contains no credentials.

---

### Task 1: Config and auth

**Files:**
- Create: `skills/bitbucket-cloud/scripts/bitbucket_cloud.py`
- Create: `skills/bitbucket-cloud/tests/support.py`
- Test: `skills/bitbucket-cloud/tests/test_config.py`

**Interfaces:**
- Produces: `config_path() -> pathlib.Path`, `load_config() -> dict`, `setting(key: str) -> str` (key in `email|token|workspace`, returns `""` when unset), `auth_header() -> str` (raises `ConfigError` if no token), `class ConfigError(Exception)`, `configure(args) -> int`.
- Produces (tests): `support.bb` (the imported module) and `support.env(**kw)` context manager that patches `os.environ` and clears the three `BITBUCKET_*` vars first.

- [ ] **Step 1: Write failing tests** in `test_config.py` (`unittest`, `tempfile` for config dir, `unittest.mock.patch`):
  - `test_env_beats_file`: file has token `A`, env `BITBUCKET_API_TOKEN=B` → `setting("token") == "B"`.
  - `test_auth_basic_when_email`: email `a@b.c`, token `t` → `auth_header() == "Basic " + b64("a@b.c:t")`.
  - `test_auth_bearer_when_no_email`: token only → `"Bearer t"`; an empty-string email also yields Bearer.
  - `test_missing_token_raises_configerror`.
  - `test_config_path_posix`: patch `os.name="posix"` → ends with `.config/bitbucket-cloud/credentials.json`.
  - `test_config_path_windows`: patch `sys.platform="win32"`, `APPDATA=C:\Users\x\AppData\Roaming` → path name `credentials.json`, parent name `bitbucket-cloud`, parent's parent is the APPDATA dir.
  - `test_config_path_override`: `BITBUCKET_CLOUD_CONFIG` wins.
  - `test_configure_merges`: run `configure` twice (first `--email`, then `--token`) → file has both; stdout never contains the token.
  - `test_configure_skips_chmod_on_windows`: patch `sys.platform="win32"` and `os.chmod` with a mock → not called.
- [ ] **Step 2: Run** `python -m unittest discover -s skills/bitbucket-cloud/tests -v` → FAIL (module missing).
- [ ] **Step 3: Implement** the Interfaces in `bitbucket_cloud.py`. Use `sys.platform == "win32"` (not `os.name`) for Windows checks. `configure` reads `args.email|token|workspace`, merges only provided values, `mkdir(parents=True, exist_ok=True)`, writes UTF-8 JSON, then `os.chmod(path, 0o600)` on non-Windows.
- [ ] **Step 4: Run** the suite → PASS.
- [ ] **Step 5: Commit** `feat(bitbucket-cloud): config and auth`.

### Task 2: HTTP core

**Files:**
- Modify: `skills/bitbucket-cloud/scripts/bitbucket_cloud.py`
- Modify: `skills/bitbucket-cloud/tests/support.py` (add `FakeResponse`, `fake_urlopen`)
- Test: `skills/bitbucket-cloud/tests/test_http.py`

**Interfaces:**
- Consumes: `auth_header()`, `ConfigError`.
- Produces:
  - `BASE = "https://api.bitbucket.org/2.0"`; module-level `_open = urllib.request.urlopen` (tests patch this).
  - `class ApiError(Exception)` with `status: int`, `message: str`.
  - `request(method: str, path_or_url: str, *, params: dict | None = None, body: dict | str | None = None, raw: bool = False) -> object` — path joins to `BASE`; absolute URLs pass through (only if host is `api.bitbucket.org`); dict body → JSON with `Content-Type: application/json`; `raw=True` returns decoded text instead of JSON.
  - `paginate(path: str, params: dict | None = None, limit: int = 100) -> list` — follows `next`, returns at most `limit` items from `values`.
  - `quote(segment: str) -> str` — `urllib.parse.quote(segment, safe="")`; `quote_path(p: str) -> str` keeps `/`.
  - `read_body(args) -> str | None` — from `args.body`, `args.body_file` (`-` = stdin), decoded `utf-8-sig`, CRLF kept as-is.
  - `emit(obj) -> None` (JSON, `ensure_ascii=False`, indent 2) and `emit_text(s: str) -> None`; `setup_stdio()` reconfigures stdout/stderr to UTF-8 (`errors="replace"`).
  - `support.fake_urlopen(responses: list[tuple[int, bytes | str]])` returns a callable recording `(method, url, headers, data)` in `.calls` and raising `urllib.error.HTTPError` for status ≥ 400.
- [ ] **Step 1: Write failing tests** in `test_http.py`:
  - `test_request_sets_auth_and_json_headers`.
  - `test_paginate_follows_next`: 2 pages of 2 items, `limit=100` → 4 items, second call URL equals the `next` value.
  - `test_paginate_limit_smaller_than_page`: page of 5, `limit=2` → 2 items and no second call. *(Review Focus 2)*
  - `test_paginate_empty_returns_empty_list`. *(Review Focus 2)*
  - `test_error_json_message`: 404 with `{"error":{"message":"nope"}}` → `ApiError(status=404, message contains "nope")`.
  - `test_error_non_json_body`: 502 with `<html>Bad Gateway</html>` and a 500 with empty body → `ApiError` with status and no `JSONDecodeError`. *(Review Focus 3)*
  - `test_token_not_in_error_message`: error text never contains the token.
  - `test_absolute_url_other_host_rejected` (prevents sending credentials to another host).
  - `test_read_body_strips_bom_and_reads_korean`: file with BOM + `한글\r\n` → `"한글\r\n"`. *(Review Focus 4)*
  - `test_read_body_stdin`: patch `sys.stdin` with `io.StringIO`.
  - `test_emit_korean_on_cp949_stream`: wrap a `io.TextIOWrapper(io.BytesIO(), encoding="cp949")`, call `setup_stdio()` against it, `emit({"t":"한글"})` → output decodes as UTF-8 and contains `한글`. *(Review Focus 4)*
  - `test_quote_branch_with_slash_and_korean`: `quote("feature/한글 x") == "feature%2F%ED%95%9C%EA%B8%80%20x"`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the Interfaces. Error message extraction: parse JSON and read `error.message`, falling back to `message`, then the first 200 chars of the text body. Never include request headers in errors.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(bitbucket-cloud): http core, pagination, stdio`.

### Task 3: Command framework, safety gate, scopes, check

**Files:**
- Modify: `skills/bitbucket-cloud/scripts/bitbucket_cloud.py`
- Test: `skills/bitbucket-cloud/tests/test_framework.py`

**Interfaces:**
- Consumes: Task 1–2 functions.
- Produces:
  - `@dataclass Cmd`: `area: str`, `action: str`, `method: str`, `path: str` (template with `{ws}`, `{repo}`, and command-specific `{id}`-style placeholders), `scopes: tuple[str, ...]`, `destructive: bool = False`, `list_result: bool = False`, `text: bool = False`, `handler: Callable | None = None`, `args: tuple[ArgSpec, ...] = ()`.
  - `COMMANDS: list[Cmd]` (empty here; Tasks 4–6 append rows) and `register(cmd: Cmd) -> None`.
  - `PRESETS: dict[str, tuple[str, ...]]` with keys `read-only`, `dev`, `admin` (contents per Scope Presets below).
  - `build_parser() -> argparse.ArgumentParser`; global options `--workspace`, `--limit`, `--yes`; `main(argv: list[str] | None = None) -> int`.
  - `require_yes(args, method: str, url: str, body) -> None` — if `args.yes` is false, `emit({"dry_run": true, "method", "url", "body"})` then `raise SystemExit(5)`.
  - `scope_hint(cmd_key: str) -> str` (e.g. `"pr merge needs: read:pullrequest:bitbucket, write:pullrequest:bitbucket"`); 403 handling in `main` prints it and returns 3; 401 returns 3 with "check email/token".
  - Commands `configure`, `check` (calls `GET /user`, then `GET /workspaces/{ws}` if a workspace is set; prints per-call OK/FAIL with hints), `scopes [--preset NAME]` (prints the table from `COMMANDS`, or the preset list).
  - `api` command: `api METHOD PATH [--body …]`; non-GET goes through `require_yes`.
- Scope Presets (all names end in `:bitbucket`; list is final):
  - `read-only`: `read:repository`, `read:pullrequest`, `read:pipeline`, `read:issue`, `read:webhook`, `read:user`, `read:workspace`
  - `dev`: read-only plus `write:repository`, `write:pullrequest`, `write:pipeline`, `write:issue`
  - `admin`: dev plus `write:webhook`, `admin:repository`, `read:permission`, `write:permission`, `delete:webhook`, `delete:issue`
- [ ] **Step 1: Write failing tests** in `test_framework.py` (register a throwaway `Cmd` in `setUp`, restore `COMMANDS` in `tearDown`):
  - `test_destructive_without_yes_prints_dry_run_and_exits_5` — fake `_open` records zero calls; stdout JSON has `dry_run: true`.
  - `test_dry_run_has_no_credentials`: token `SECRET123` absent from stdout and stderr. *(Review Focus 5)*
  - `test_destructive_with_yes_sends_request`.
  - `test_api_non_get_requires_yes` for `POST`, `PUT`, `PATCH`, `DELETE`; `api GET /user` does not. *(Review Focus 5)*
  - `test_403_returns_3_and_prints_scope_hint`.
  - `test_401_returns_3`.
  - `test_missing_config_returns_2_with_setup_hint`.
  - `test_workspace_flag_overrides_config`.
  - `test_scopes_command_lists_every_registered_command`.
  - `test_presets_only_use_known_scopes`: every preset scope exists in the `KNOWN_SCOPES` set (the API-token scope names from the Bitbucket docs that this skill uses; defined once in the script).
  - `test_every_cmd_has_scopes_unless_api_or_meta`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the Interfaces. Parser: `area` subparsers with `action` subparsers generated from `COMMANDS`; path placeholders become positional arguments in template order (`{ws}` comes from `--workspace`/config, `{repo}` is the first positional when present). Generic dispatch: format path with `quote()`d values, add `--limit` handling when `list_result`, call `require_yes` when `destructive`, send via `request`/`paginate`, `emit` or `emit_text` (`text=True`). Commands with a `handler` get `(args, cmd)` instead. `main` calls `setup_stdio()`, catches `ConfigError`→2, `ApiError`→3/4.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(bitbucket-cloud): command framework, gate, scopes, check`.

### Task 4: repo and commit commands

**Files:**
- Modify: `skills/bitbucket-cloud/scripts/bitbucket_cloud.py`
- Test: `skills/bitbucket-cloud/tests/test_repo_commit.py`

**Interfaces:**
- Consumes: `Cmd`, `register`, `quote`, `quote_path`.
- Produces rows (paths relative to `/repositories/{ws}/{repo}` unless noted). All scopes end in `:bitbucket`; a write row also lists its read scope.

| Command | Method | Path | Scopes | Notes |
|---|---|---|---|---|
| `repo list` | GET | `/repositories/{ws}` | read:repository | list |
| `repo get REPO` | GET | `` | read:repository | |
| `repo branches REPO` | GET | `/refs/branches` | read:repository | list; `--query` → `q=name~"…"` |
| `repo branch-create REPO NAME --from COMMIT` | POST | `/refs/branches` | read+write:repository | body `{"name": NAME, "target": {"hash": COMMIT}}` |
| `repo tags REPO` | GET | `/refs/tags` | read:repository | list |
| `commit list REPO [--revision REV]` | GET | `/commits` or `/commits/{REV}` | read:repository | list |
| `commit get REPO SHA` | GET | `/commit/{SHA}` | read:repository | |
| `commit diff REPO SPEC` | GET | `/diff/{SPEC}` | read:repository | text |
| `commit file REPO PATH --ref REF` | GET | `/src/{REF}/{PATH}` | read:repository | text; `quote_path` for PATH, `quote` for REF |

- [ ] **Step 1: Write failing tests** (fake `_open` asserting method/URL/body):
  - one test per row checking the exact URL and scopes;
  - `test_branch_create_body`;
  - `test_branches_with_slash_and_korean_ref_is_quoted`: `commit file r a/b/한글.txt --ref feature/한글` → URL contains `%2F` for the ref and `/` preserved between path segments. *(Review Focus 1)*
  - `test_repo_list_empty_prints_empty_array`. *(Review Focus 2)*
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** by registering the rows above (handlers only for `branch-create`, `commit list` with optional revision, and `commit file`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(bitbucket-cloud): repo and commit commands`.

### Task 5: pr and task commands

**Files:**
- Modify: `skills/bitbucket-cloud/scripts/bitbucket_cloud.py`
- Test: `skills/bitbucket-cloud/tests/test_pr.py`

**Interfaces:**
- Consumes: framework from Task 3, `read_body`.
- Produces rows under `/repositories/{ws}/{repo}/pullrequests`. Read scope `read:pullrequest:bitbucket`; write rows add `write:pullrequest:bitbucket`.

| Command | Method | Path suffix | Notes |
|---|---|---|---|
| `pr list REPO [--state OPEN\|MERGED\|DECLINED\|SUPERSEDED]` | GET | `` | list; default state OPEN |
| `pr get REPO ID` | GET | `/{ID}` | |
| `pr create REPO --title T --source BRANCH [--dest BRANCH] [--description/--body…] [--reviewer UUID…] [--close-source-branch]` | POST | `` | body `{title, source:{branch:{name}}, destination:{branch:{name}}?, description?, reviewers:[{uuid}], close_source_branch}` |
| `pr update REPO ID [--title] [--description] [--dest]` | PUT | `/{ID}` | only provided fields sent |
| `pr diff REPO ID` | GET | `/{ID}/diff` | text |
| `pr comments REPO ID` | GET | `/{ID}/comments` | list |
| `pr comment-add REPO ID --body … [--parent COMMENT_ID]` | POST | `/{ID}/comments` | body `{"content":{"raw": …}, "parent":{"id":…}?}` |
| `pr approve REPO ID` / `pr unapprove REPO ID` | POST / DELETE | `/{ID}/approve` | |
| `pr request-changes REPO ID` | POST | `/{ID}/request-changes` | |
| `pr merge REPO ID [--strategy merge_commit\|squash\|fast_forward] [--message M] [--close-source-branch]` | POST | `/{ID}/merge` | **destructive** |
| `pr decline REPO ID [--reason R]` | POST | `/{ID}/decline` | **destructive** |
| `task list REPO PR_ID` | GET | `/{PR_ID}/tasks` | list |
| `task add REPO PR_ID --body … [--comment COMMENT_ID]` | POST | `/{PR_ID}/tasks` | body `{"content":{"raw":…}, "comment":{"id":…}?}` |
| `task update REPO PR_ID TASK_ID [--body] [--state RESOLVED\|UNRESOLVED]` | PUT | `/{PR_ID}/tasks/{TASK_ID}` | |
| `task delete REPO PR_ID TASK_ID` | DELETE | `/{PR_ID}/tasks/{TASK_ID}` | **destructive** |

- [ ] **Step 1: Write failing tests**:
  - URL/method/body assertions per row (exact JSON bodies above);
  - `test_pr_create_omits_dest_when_not_given` and `test_pr_update_sends_only_given_fields`;
  - `test_pr_merge_and_decline_gated`, `test_task_delete_gated` (no HTTP call without `--yes`);
  - `test_pr_comment_body_from_file_with_bom_and_crlf`: body equals file text without BOM. *(Review Focus 4)*
  - `test_pr_comment_body_korean_roundtrip`: request bytes decode to `한글`. *(Review Focus 4)*
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** by registering the rows; handlers build bodies and call `read_body` for `--body` / `--body-file` / `-`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(bitbucket-cloud): pr and task commands`.

### Task 6: pipeline, webhook, perm, issue commands

**Files:**
- Modify: `skills/bitbucket-cloud/scripts/bitbucket_cloud.py`
- Test: `skills/bitbucket-cloud/tests/test_misc_commands.py`

**Interfaces:**
- Consumes: framework from Task 3. Paths under `/repositories/{ws}/{repo}`. Scope suffix `:bitbucket`.

| Command | Method | Path suffix | Scopes | Notes |
|---|---|---|---|---|
| `pipeline list REPO` | GET | `/pipelines/?sort=-created_on` | read:pipeline | list |
| `pipeline get REPO UUID` | GET | `/pipelines/{UUID}` | read:pipeline | |
| `pipeline trigger REPO --branch B [--pattern CUSTOM_PIPELINE] [--var K=V…]` | POST | `/pipelines/` | read+write:pipeline | **destructive**; body `{"target":{"type":"pipeline_ref_target","ref_type":"branch","ref_name":B,"selector":{"type":"custom","pattern":P}?}, "variables":[{"key","value"}]?}` |
| `pipeline stop REPO UUID` | POST | `/pipelines/{UUID}/stopPipeline` | read+write:pipeline | **destructive** |
| `pipeline log REPO UUID [--step STEP_UUID]` | GET | `/pipelines/{UUID}/steps/` (no `--step`: JSON list) or `/pipelines/{UUID}/steps/{STEP}/log` | read:pipeline | log is text |
| `webhook list REPO` | GET | `/hooks` | read:webhook | list |
| `webhook create REPO --url U --event E… [--description D]` | POST | `/hooks` | read+write:webhook | body `{"description", "url", "active": true, "events": [...]}` |
| `webhook delete REPO UID` | DELETE | `/hooks/{UID}` | read+delete:webhook | **destructive** |
| `perm list REPO` | GET | `/permissions-config/users` and `/permissions-config/groups` | read:permission, admin:repository | prints `{"users": [...], "groups": [...]}` |
| `perm set REPO --user ACCOUNT_ID\|--group SLUG --permission read\|write\|admin` | PUT | `/permissions-config/users/{ACCOUNT_ID}` or `/permissions-config/groups/{SLUG}` | read+write:permission, admin:repository | **destructive**; body `{"permission": P}` |
| `perm remove REPO --user ACCOUNT_ID\|--group SLUG` | DELETE | same as above | read+delete:permission, admin:repository | **destructive** |
| `issue list REPO` | GET | `/issues` | read:issue | list |
| `issue get REPO ID` | GET | `/issues/{ID}` | read:issue | |
| `issue create REPO --title T [--body …] [--kind K] [--priority P]` | POST | `/issues` | read+write:issue | body `{"title","content":{"raw"}?,"kind"?,"priority"?}` |
| `issue update REPO ID [--title] [--body] [--state S]` | PUT | `/issues/{ID}` | read+write:issue | only provided fields |
| `issue comment REPO ID --body …` | POST | `/issues/{ID}/comments` | read+write:issue | body `{"content":{"raw":…}}` |

- [ ] **Step 1: Verify endpoints** against the Bitbucket Cloud REST reference (`https://developer.atlassian.com/cloud/bitbucket/rest/api-group-<group>/`) for pipelines, webhooks (`hooks`), permissions (`permissions-config`), and issues. If a path or body in the table differs, change the table in this plan first, then proceed. Record the check in the commit message.
- [ ] **Step 2: Write failing tests**: URL/method/body per row; `test_pipeline_trigger_gated`, `test_pipeline_stop_gated`, `test_webhook_delete_gated`, `test_perm_set_gated`, `test_perm_remove_gated`; `test_pipeline_log_without_step_lists_steps`; `test_pipeline_log_returns_raw_text` (no JSON parse; Korean log line preserved); `test_trigger_var_parsing` (`--var A=1 --var B=x=y` → value of `B` is `x=y`); `test_perm_requires_exactly_one_of_user_or_group` (exit 2).
- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement** by registering the rows with handlers for trigger, log, perm, and the body-building issue commands.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat(bitbucket-cloud): pipeline, webhook, perm, issue commands`.

### Task 7: Documentation, smoke test, wiring

**Files:**
- Create: `skills/bitbucket-cloud/SKILL.md`
- Create: `skills/bitbucket-cloud/references/setup.md`
- Create: `skills/bitbucket-cloud/references/api-notes.md`
- Create: `skills/bitbucket-cloud/examples/smoke_test.py`
- Modify: `README.md` (list the new skill, mirroring how `atlassian-cloud` is listed)
- Test: `skills/bitbucket-cloud/tests/test_docs.py`

**Interfaces:**
- Consumes: `COMMANDS`, `PRESETS`, `KNOWN_SCOPES`.
- [ ] **Step 1: Write failing tests** in `test_docs.py`:
  - `test_setup_md_lists_every_scope_used_by_commands`: every scope in `COMMANDS` appears in `references/setup.md`.
  - `test_setup_md_lists_each_preset_scope`.
  - `test_skill_md_front_matter`: starts with `---`, has `name: bitbucket-cloud` and a `description:` containing `Bitbucket`, `pull request`, `pipeline`, `비트버킷`.
  - `test_skill_md_mentions_every_area`: each `area` in `COMMANDS` appears in `SKILL.md`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Write the docs.**
  - `SKILL.md`: same shape as `atlassian-cloud/SKILL.md` — setup (configure + env vars), `check`, command overview by area, safety rules (`--yes`, dry-run, never echo tokens), `python`/`python3` note for Windows vs POSIX, pointer to `references/`.
  - `references/setup.md`: the scope guide required by the spec — token creation steps, API-token vs access-token differences, non-hierarchical scopes, expiry (max 1 year), command → scopes table, the three presets with exact scope lists from Task 3, OAuth-style equivalents, 403 troubleshooting, Windows notes (`%APPDATA%` path, PowerShell env var syntax `$env:BITBUCKET_API_TOKEN="…"`).
  - `references/api-notes.md`: endpoint map, pagination, text-vs-JSON responses, quirks found in Task 6 Step 1.
  - `examples/smoke_test.py`: opt-in (`BITBUCKET_SMOKE=1`) read-only run of `check`, `repo list --limit 1`.
- [ ] **Step 4: Run** the full suite → PASS; also run `python skills/bitbucket-cloud/scripts/bitbucket_cloud.py --help` and `... scopes --preset dev` and confirm sensible output.
- [ ] **Step 5: Verify Windows-safety by inspection:** `grep -n "os.name\|/tmp\|\\bchmod\\b\|shell=True" skills/bitbucket-cloud/scripts/bitbucket_cloud.py` shows only the guarded chmod; no POSIX-only calls.
- [ ] **Step 6: Commit** `docs(bitbucket-cloud): SKILL.md, scope guide, api notes, smoke test`.
