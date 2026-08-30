# Notion Integration

## Scope

Phase 1 provides an isolated Notion REST API connection check. It does not
connect Notion to Memo, Task, Long-term Memory, Router, or Realtime tools.
Local JSON files and the conversation SQLite database remain unchanged.

The verification command performs these operations in order:

1. retrieve the configured parent page
2. create a timestamped child page under it
3. retrieve the created page by its returned Page ID
4. verify the title, parent Page ID, and URL

The test page is intentionally left in Notion for visual confirmation. The
command does not delete or archive any page.

## Notion setup

1. Open the Notion integration settings and create an Internal Connection for
   JARVIS.
2. Enable the minimum capabilities required by Phase 1:
   - Read content
   - Insert content
3. Create or select a normal Notion page to use as the test parent page.
4. Open that page's connection settings and add the JARVIS Connection. An
   Internal Connection cannot access a page only because it exists in the same
   workspace; the page must be shared with the Connection.
5. Copy the Internal Connection token and the parent Page ID.

Official references:

- [Notion authorization](https://developers.notion.com/guides/get-started/authorization)
- [Create a page](https://developers.notion.com/reference/post-page)
- [Retrieve a page](https://developers.notion.com/reference/retrieve-a-page)

## Local configuration

Set the following values in the local `.env` file. Do not commit this file or
paste the real token into source code, logs, issues, or test fixtures.

```dotenv
NOTION_API_TOKEN=your_internal_connection_token
NOTION_PARENT_PAGE_ID=your_parent_page_id
NOTION_API_VERSION=2026-03-11
```

`NOTION_API_VERSION` is optional and defaults to `2026-03-11`. The other two
values are required only when the Notion verification command is run. Missing
Notion settings do not prevent the existing JARVIS application from importing
or starting.

The Page ID may be copied with or without hyphens. When copying it from a
Notion URL, use only the 32-character page identifier, not the complete URL or
query string.

## Run the connection check

From the repository root, run:

```powershell
.\.venv\Scripts\python.exe scripts\verify_notion_connection.py
```

On success, the command prints the parent Page ID, created Page ID, title, and
Notion URL. It never prints the configured API token.

On Windows, the Notion client uses the operating system's trusted root
certificates. TLS certificate and hostname verification remain enabled. This
allows JARVIS to work with locally trusted network security certificates
without using the unsafe `verify=False` option.

Example output:

```text
Notion接続確認に成功しました。
Parent Page ID: ...
Created Page ID: ...
Title: JARVIS Notion Connection Test - ...
URL: https://www.notion.so/...
テストページは確認用としてNotion上に残しています。
```

## Troubleshooting

- `NOTION_API_TOKEN が設定されていません`: add the token to the local
  environment and restart the command.
- HTTP 401: confirm that the Internal Connection token is current.
- HTTP 403: confirm Read content and Insert content capabilities and make sure
  the Connection was added to the parent page.
- HTTP 404: confirm the Page ID. Notion may also return not found when the
  Connection cannot access the page.
- HTTP 429: wait for the duration indicated by Notion and run the command
  again.
- HTTP 5xx or a timeout: check Notion's status and retry later. Creation is not
  retried automatically because a timed-out request may already have created a
  page.
- A certificate failure from a separate Python HTTP client does not
  necessarily apply to this verification command. The JARVIS Notion client
  uses the Windows trusted root certificate store as described above.

## Automated tests

The tests mock the HTTP session and never contact Notion:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_notion_client
```

Run the full Python regression suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Phase 2: Notes Data Source

Phase 2 adds Local-first Dual Write for newly created Memo records. Existing
Memo, Task, Long-term Memory, Router classification, and conversation storage
remain unchanged.

Create or validate the Notes Database and its Initial Data Source with:

```powershell
.\.venv\Scripts\python.exe scripts\setup_notion_notes.py
```

The command creates an inline `JARVIS Notes` database under the configured
parent page. It stores the non-secret Database ID and Data Source ID in the
ignored `data/notion_resources.json` file. It never modifies `.env`. An
optional `NOTION_NOTES_DATA_SOURCE_ID` environment value overrides the local
resource file.

The Data Source schema is fixed as follows:

| Property | Type | Purpose |
| --- | --- | --- |
| Title | title | Short Notion page title derived from the Memo |
| Content | rich_text | Complete Memo content |
| Jarvis Local ID | number | Existing Local JSON integer ID |
| Created At | date | Local creation time with timezone |
| Source | select | `JARVIS` for Phase 2 writes |
| Sync Key | rich_text | Stable key used before every create request |

For a new Memo, `add_note()` performs this flow:

```text
save notes.json with pending metadata
→ validate the Data Source schema on first use
→ query the Data Source by Sync Key
→ reuse an existing page or create one
→ save the Notion Page ID and synced status to notes.json
```

If Notion configuration, schema validation, network access, or the Notion
write fails, the Local Memo remains saved with `notion_sync_status: pending`.
The existing text and Realtime result strings do not expose or depend on sync
metadata.

Retry pending Phase 2 Memo records with:

```powershell
.\.venv\Scripts\python.exe scripts\retry_notion_notes.py
```

The retry command does not create another Local Memo. The writer queries by the
existing Sync Key before every Notion create, so a response timeout followed
by a retry reuses a page that Notion already created.

Existing Memo records created before Phase 2 do not have sync metadata and are
not migrated automatically. That migration belongs to a later storage
integration phase.

Run a real Local and Notion Dual Write verification with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_notion_memo_write.py
```

The command creates one clearly named verification Memo and leaves it in both
`data/notes.json` and Notion for inspection.
