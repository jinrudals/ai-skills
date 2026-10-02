# API notes

Endpoint bases used by `scripts/atlassian_cloud.py`:

| Product | Base |
|---|---|
| Jira Cloud | `https://<site>.atlassian.net/rest/api/3` |
| Confluence Cloud (CRUD) | `https://<site>.atlassian.net/wiki/api/v2` |
| Confluence Cloud (CQL search) | `https://<site>.atlassian.net/wiki/rest/api` (v1 — v2 has no CQL search yet) |

## Credential resolution order

`_setting(key)` checks, in order: the matching env var, then
`~/.config/atlassian-cloud/credentials.json` (or `$ATLASSIAN_CLOUD_CONFIG` if
set). `configure` only ever writes the config file; it never touches env
vars. This means an env var set in the current shell always masks whatever
`configure` wrote, which is the intended escape hatch for CI/one-off
overrides without disturbing the global file.

## Endpoint → command map

| Command | HTTP | Path |
|---|---|---|
| `configure` | local only | writes `~/.config/atlassian-cloud/credentials.json`, no API call |
| `jira issue-get KEY` | GET | `/issue/{key}` |
| `jira issue-create` | POST | `/issue` |
| `jira issue-update KEY` | PUT | `/issue/{key}` |
| `jira issue-delete KEY` | DELETE | `/issue/{key}` |
| `jira issue-search JQL` | POST | `/search/jql` |
| `jira comment-add KEY TEXT` | POST | `/issue/{key}/comment` |
| `jira transition KEY --list` | GET | `/issue/{key}/transitions` |
| `jira transition KEY --to NAME` | GET then POST | `/issue/{key}/transitions` |
| `jira attachment-add KEY FILE` | POST (multipart) | `/issue/{key}/attachments` |
| `jira attachment-list KEY` | GET | `/issue/{key}?fields=attachment` |
| `jira attachment-download ID` | GET then binary GET | `/attachment/{id}` then its `content` URL |
| `confluence page-get ID` | GET | `/pages/{id}?body-format=storage` |
| `confluence page-create` | POST | `/pages` |
| `confluence page-update ID` | PUT | `/pages/{id}` |
| `confluence page-delete ID` | DELETE | `/pages/{id}` |
| `confluence search CQL` | GET | `/content/search?cql=...` (v1) |
| `confluence attachment-add ID FILE` | POST (multipart) | `/content/{id}/child/attachment` (v1) |
| `confluence attachment-list ID` | GET | `/content/{id}/child/attachment` (v1) |
| `confluence attachment-download ID FILENAME` | GET then binary GET | `/content/{id}/child/attachment` then `_links.download` |
| `confluence macro-wrap NAME` | local only | prints `<ac:structured-macro>` XML, no API call |

## Multipart uploads (stdlib only)

`jira attachment-add` and `confluence attachment-add` both POST
`multipart/form-data`, built by hand in `_build_multipart()` — no
`requests`/`urllib3` dependency. Both additionally require the
`X-Atlassian-Token: no-check` header (a CSRF guard against unsolicited file
uploads via a browser's cached session); the script always sends it.

## Confluence macros — mechanism, not a catalog

There is no REST endpoint to enumerate which macros (built-in or
marketplace-installed) are available on a site — the storage format simply
accepts any `<ac:structured-macro ac:name="...">` whose name the renderer
recognizes at view time; an unrecognized name renders as a visible error
box but the page still saves. Common built-ins and their typical shape:

| Macro | `ac:name` | Body | Typical params |
|---|---|---|---|
| Info/Note/Warning/Tip panels | `info`, `note`, `warning`, `tip` | plain-text or rich-text | `title` |
| Code block | `code` | plain-text (CDATA) | `language`, `title`, `linenumbers` |
| Table of contents | `toc` | none | `maxLevel`, `minLevel` |
| Expand/collapse | `expand` | rich-text | `title` |
| Status lozenge | `status` | none | `colour`, `title` |
| Jira issue/filter embed | `jira` | none | `key` (single issue) or `jqlQuery` |
| Page include | `include` | none | `` (uses `<ri:page>` child, not a simple param) |
| Excerpt / excerpt-include | `excerpt`, `excerpt-include` | rich-text / none | `atlassian-macro-output-type` |

For anything not in this table — a marketplace app's macro — `macro-wrap`
still works mechanically (it's just XML assembly); the only unknown is the
exact `ac:name` and parameter names, which come from the app's own docs or
by inspecting a page that already uses it (`confluence page-get ID` returns
the live storage XML verbatim).

## Atlassian Document Format (ADF)

Jira Cloud `description` and comment `body` fields are ADF, a JSON tree, not
Markdown or wiki markup. `_text_to_adf()` in the script produces only the
simplest valid shape:

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {"type": "paragraph", "content": [{"type": "text", "text": "..."}]}
  ]
}
```

For anything beyond plain paragraphs — bullet lists, links, mentions, code
blocks, tables — construct the ADF node tree yourself and pass the whole
`fields` object override via `--fields-json` (merged on top of the
auto-generated fields, so it can replace `description` wholesale). Common
nodes:

- Bullet list: `{"type": "bulletList", "content": [{"type": "listItem", "content": [...paragraph...]}]}`
- Link: inside a text node, `"marks": [{"type": "link", "attrs": {"href": "https://..."}}]`
- Code block: `{"type": "codeBlock", "attrs": {"language": "python"}, "content": [{"type": "text", "text": "..."}]}`

Full schema: <https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/>

## Confluence storage format

Page bodies are XHTML-like "storage format" strings, e.g.:

```html
<p>Plain paragraph.</p>
<ul><li>Bullet item</li></ul>
<ac:structured-macro ac:name="info"><ac:rich-text-body><p>Note text</p></ac:rich-text-body></ac:structured-macro>
```

Write this directly into the file passed to `--body-file`. There is no
Markdown-to-storage conversion in this script — if you're starting from
Markdown, convert it (e.g. with pandoc to XHTML and hand-fix macros) before
calling `page-create`/`page-update`.

## Pagination

- `jira issue-search` results include `nextPageToken` when more results
  remain; re-run with that token to continue (not yet wired into the script —
  pass `--fields-json '{"nextPageToken": "..."}'`-style via a direct body
  edit if you need to page past `--max-results`, or raise `--max-results`).
- `confluence search` paginates via a `_links.next` relative URL in the
  response; fetch it directly with the same auth header if you need more
  than `--limit`.

The script does not auto-follow pagination — treat `next`/`nextPageToken` in
the JSON output as the signal to issue one more call yourself.
