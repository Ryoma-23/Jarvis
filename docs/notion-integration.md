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

## Phase 3: Structured Memo Read

Phase 3 reads Memo records only from the configured Notes Data Source. It does
not use Notion workspace Search, a Vector Database, Embeddings, or RAG.

The reader supports these structured operations:

- list every Memo with an explicit `Created At` ascending sort
- filter `Content` with the Data Source `rich_text.contains` condition
- filter `Jarvis Local ID` with the Data Source `number.equals` condition;
  multiple historical matches are returned without data loss
- retrieve one Memo directly by its Notion Page ID
- follow `has_more` and `next_cursor` until every query page is collected

The Data Source schema is validated before the first read. A malformed page,
missing pagination cursor, or Notion API error is treated as a failed Notion
read instead of returning a silent partial result. The service's single-record
Local ID operation falls back to Local JSON when historical Notion pages make
the Local ID ambiguous.

Official references:

- [Query a data source](https://developers.notion.com/reference/query-a-data-source)
- [Filter data source entries](https://developers.notion.com/reference/filter-data-source-entries)
- [Sort data source entries](https://developers.notion.com/reference/sort-data-source-entries)
- [Notion pagination](https://developers.notion.com/reference/intro#pagination)

### Feature flag and fallback

Notion Read is disabled by default. To enable it for Memo list, Content search,
Local ID retrieval, and Page ID retrieval, add this value to the local `.env`:

```dotenv
NOTION_NOTES_READ_ENABLED=true
```

The repository does not modify `.env`. Values `1`, `true`, `yes`, and `on` are
accepted case-insensitively. With the flag disabled, all existing read behavior
continues to use `data/notes.json`.

With the flag enabled, a configured reader uses the Notes Data Source. If the
configuration is unavailable, schema validation fails, a response is malformed,
or a Notion request fails, the same operation falls back to Local JSON. Existing
text and Realtime list/search result strings remain unchanged.

Memo records created before Phase 2 have not been migrated to Notion. Therefore,
successful Notion reads contain only records that exist in the Notes Data Source;
they do not merge legacy Local-only records. Backfilling those records belongs to
a later storage integration phase. The Phase 3 parity check intentionally compares
Notion with Local records whose `notion_sync_status` is `synced`.

### Verification

Run the Local/Notion structured-read comparison with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_notion_memo_read.py
```

The command is read-only. It checks the complete sorted list, Local ID filter,
Content partial-match filter, Page ID retrieval, and the major fields and counts
of synced Local/Notion Memo records tracked by Local Page ID. Notion pages left
from an older Local state are reported as `Untracked Notion count`; they are not
deleted and do not invalidate the tracked-record comparison. Pagination with
more than 100 results is covered without a live API call by the unit tests.

Notion normalizes the tested `Created At` Date property to minute precision even
when JARVIS sends an ISO timestamp containing seconds. The parity command compares
that field at minute precision; Local JSON keeps its original seconds and existing
Local display behavior is not changed.

Run the Phase 3 unit tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_notion_client tests.test_notion_memo_reader tests.test_note_service
```

## Phase 4: Existing Storage Integration

Phase 4 moves storage selection below the Service layer:

```text
IntentService / Realtime Tool
→ Memo / Task / Memory Service
→ Entity Repository
   ├─ Local JSON
   ├─ Notion Data Source
   └─ Local-first Dual Write
```

Router, IntentService, and Realtime tools continue to call the same Service
functions and do not know which storage backend is active.

### Repository behavior

All writes remain Local-first. A create or update is saved to JSON before Notion
is called. A Notion failure leaves `notion_sync_status: pending` and does not make
the existing JARVIS operation unavailable.

Deletes are recoverable tombstones rather than physical JSON removal. The record
receives `deleted_at` and is immediately hidden from Local and Notion-backed reads.
If Notion trash succeeds its status becomes `deleted`; otherwise it remains
`delete_pending` and the migration command retries it. Tombstones retain the Local
integer ID, Sync Key, and Notion Page ID and prevent deleted IDs from being reused.

Notion API version `2026-03-11` uses `in_trash: true`; the removed `archived`
request field is never sent.

### Task and Memory Data Sources

Create or validate both Data Sources with:

```powershell
.\.venv\Scripts\python.exe scripts\setup_notion_storage.py --entity all
```

`--entity tasks` and `--entity memory` can be used separately. Non-secret Database
and Data Source IDs are saved to ignored `data/notion_resources.json`.

Task properties:

| Property | Type |
| --- | --- |
| Title | title |
| Status | status |
| Due Date | date |
| Created At | date |
| Completed At | date |
| Jarvis ID | number |
| Sync Key | rich_text |

Local `todo` maps to Notion `Not started`; Local `done` maps to `Done`.
`complete_tasks()` writes Status and Completed At in the same Notion Page update.

Long-term Memory properties:

| Property | Type |
| --- | --- |
| Content | title |
| Category | select |
| Created At | date |
| Updated At | date |
| Jarvis ID | number |
| Sync Key | rich_text |

`format_memory_for_prompt()` continues to load every active Memory record. It is
not replaced with RAG or relevance retrieval in this phase.

### Existing-data migration

Migration defaults to a read-only Dry Run:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_notion_storage.py --entity all --dry-run
```

Apply after reviewing the counts:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_notion_storage.py --entity all --apply
```

The command derives missing timezone-aware ISO timestamps and Sync Keys in memory.
Dry Run does not modify JSON or Notion. Apply queries every Sync Key before create,
reuses an existing Page, stores the Page ID locally, and retries `delete_pending`
tombstones. Local files are never cleared.

Compare migrated Task and Memory records without writing:

```powershell
.\.venv\Scripts\python.exe scripts\verify_notion_storage.py --entity all
```

The comparison checks Local-tracked Page counts, IDs, content fields, state fields,
Sync Keys, and dates. As in Phase 3, Notion Date properties are compared at minute
precision because Notion normalizes submitted seconds.

Run an isolated real CRUD verification with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_notion_storage_crud.py
```

It creates one uniquely named verification Page in each Memo, Task, and Memory
Data Source, retrieves and updates the Task and Memory Pages, and moves all three
verification Pages to Notion Trash. It does not add records to Local JSON.

### Read source flags

Read switching is independent for each entity and disabled by default:

```dotenv
NOTION_NOTES_READ_ENABLED=true
NOTION_TASKS_READ_ENABLED=true
NOTION_MEMORY_READ_ENABLED=true
```

The repository does not modify `.env`. When a flag is enabled, list/search/prompt
reads use the corresponding Notion Data Source. Invalid configuration, network
failure, schema mismatch, or malformed pagination causes that operation to fall
back to active Local JSON records. Locally tombstoned Page IDs remain hidden even
while a Notion trash retry is pending.

Do not switch an entity flag permanently until migration comparison, CRUD checks,
text and Realtime manual checks, and outage behavior have been accepted. Keeping
the flags off preserves Local JSON as the current source of truth and rollback
path.

Official references:

- [Update a page](https://developers.notion.com/reference/patch-page)
- [Trash a page](https://developers.notion.com/reference/trash-page)
- [Data source properties](https://developers.notion.com/reference/property-object)
- [Query a data source](https://developers.notion.com/reference/query-a-data-source)

## Phase 5: Notion Page Chunking

Phase 5 adds a read-only document-processing layer. It does not change the
Memo, Task, or Memory repositories, their Feature Flags, or the current source
of truth.

The processing flow is:

```text
Notion Page
→ paginated Block Children retrieval
→ recursive retrieval for has_children Blocks
→ common plain-text normalization
→ empty/decorative Block filtering
→ heading-aware section splitting
→ deterministic Chunk metadata
```

Notion returns only one level of Block Children per request. JARVIS follows
`next_cursor` until each level is complete and then recursively retrieves every
Block whose `has_children` value is true. A depth limit and checks for repeated
cursors, duplicate Block IDs, malformed responses, and cycles prevent an invalid
response from causing an unbounded traversal.

Text normalization uses each rich-text item's `plain_text`, so annotations such
as bold, italic, and color do not alter Chunk identity. Paragraphs, headings,
bulleted and numbered list items, to-do items, quotes, toggles, code, equations,
table rows, child-page titles, links, and media captions are supported. Empty
text, dividers, breadcrumbs, table containers, and other decoration-only Blocks
do not produce text, while any supported descendants are still traversed.

### Heading-aware chunks and identity

Heading 1-3 values form a hierarchy. Each Chunk repeats its current heading path
before the body, which keeps section context when a long section is split. The
default maximum size is 1,200 characters and can be overridden by callers with a
minimum of 100 characters.

Every Chunk contains:

| Field | Meaning |
| --- | --- |
| `chunk_id` | Deterministic ID for Page, anchor Block, and normalized content |
| `notion_page_id` | Source Notion Page ID |
| `block_id` | Stable section/first-content anchor Block ID |
| `title` | Source Page title |
| `chunk_index` | Current document-order index |
| `content_hash` | SHA-256 of normalized Chunk content |
| `last_edited_time` | Source Page's latest edit timestamp |
| `source_type` | `notion_page` |
| `notion_url` | Source Page URL |

`heading_path` and all contributing `block_ids` are also retained for later
indexing and diagnostics. `chunk_index` and `last_edited_time` are metadata only;
they are deliberately excluded from identity. The ID input is the canonical Page
ID, canonical anchor Block ID, and `content_hash`. Therefore the same normalized
content from the same source Block produces the same Chunk ID on every sync, while
a content change produces a new ID.

This phase stores no chunks and adds no Vector DB, embeddings, or RAG retrieval.
Those layers can consume the deterministic Chunk objects in later phases.

### Verification

Run unit tests without calling Notion:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_notion_client tests.test_notion_chunking
```

Run the isolated live verification with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_notion_chunking.py
```

The live command creates one timestamped child Page under
`NOTION_PARENT_PAGE_ID`, retrieves nested content twice, verifies stable Chunk IDs
and required Metadata, and moves the Page to Notion Trash in a `finally` cleanup.

Official references:

- [Working with page content](https://developers.notion.com/guides/data-apis/working-with-page-content)
- [Retrieve block children](https://developers.notion.com/reference/get-block-children)
- [Block object](https://developers.notion.com/reference/block)
- [Rich text object](https://developers.notion.com/reference/rich-text)
- [Pagination](https://developers.notion.com/reference/pagination)

## Phase 6: Embedding

Phase 6 converts Phase 5 Chunks into OpenAI embedding vectors. It introduces a
dedicated `OpenAIEmbeddingClient`; the existing response and intent client in
`app/openai_client.py` is not reused or modified.

The processing flow is:

```text
Notion Page Chunks
→ exclude empty content
→ calculate Embedding version
→ skip an already stored matching version
→ send pending content in batches
→ commit each successful batch to local SQLite
```

OpenAI accepts multiple strings in one Embeddings request. Empty strings are not
accepted, and the `dimensions` parameter is available for `text-embedding-3`
models. JARVIS therefore removes empty Chunks before the API boundary and sends a
maximum of the configured batch size in each request.

### Configuration

The defaults work without adding new values to `.env`:

```dotenv
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
OPENAI_EMBEDDING_BATCH_SIZE=100
```

The existing `OPENAI_API_KEY` value is used to construct the separate Embedding
client. JARVIS never writes these values to `.env`, the database, logs, or error
messages. Batch size must be between 1 and 2,048.

`text-embedding-3-large` can be evaluated by changing the model and dimensions
settings. Small and large records have different versions and can coexist, so
switching models does not overwrite the previous evaluation data.

### Versioning and restart behavior

The Embedding version is a deterministic SHA-256 value calculated from:

```text
content_hash + model + dimensions
```

The local record ID additionally includes `chunk_id`. A stored record is reused
only when its record ID, content hash, model, dimensions, and vector length all
match. Content, model, or dimension changes therefore create a new record, while
an unchanged Chunk makes no API call.

Generated records are stored in the ignored file `data/embeddings.sqlite3`.
SQLite is used only as restart-safe Phase 6 persistence and is not a Vector DB.
Each successful API batch is committed in one transaction. If a later batch
fails, earlier batches remain committed; rerunning the same command skips them
and resumes with only the missing Chunks.

### Commands

Embed one Notion Page and persist the results:

```powershell
.\.venv\Scripts\python.exe scripts\embed_notion_page.py <NOTION_PAGE_ID>
```

Run a small live OpenAI API check using a temporary Store:

```powershell
.\.venv\Scripts\python.exe scripts\verify_embedding.py
```

Run unit tests without calling OpenAI or Notion:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_embedding_client tests.test_embedding_service
```

Phase 6 does not add similarity search, a Vector DB, or RAG retrieval. It only
produces versioned vectors for those later phases.

Official OpenAI documentation:

- [Create embeddings](https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create)
- [text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small)

## Phase 7: Chroma Vector DB

Phase 7 adds Chroma as a regenerable local search index:

```text
Notion Page (source of truth)
→ Phase 5 deterministic Chunks
→ Phase 6 versioned Embeddings
→ Chroma Collection (regenerable index)
```

Chroma `1.5.9` is the first Vector DB dependency in this repository. A local
`PersistentClient` stores its files under the ignored `data/chroma/` directory.
The Chroma embedding function is explicitly disabled: only vectors already
generated and validated by Phase 6 can be upserted.

### Collections and Metadata

Collection names are deterministic for the exact Embedding model and dimensions.
Changing either setting selects a different Collection and leaves the previous
index available for comparison.

Each record uses the Phase 5 `chunk_id` as its Chroma ID, the normalized Chunk
content as its document, and includes at least:

- Notion Page ID and canonical Page key
- Block ID and contributing Block IDs
- Page title and Notion URL
- Chunk index and heading path
- Content hash and last-edited timestamp
- Embedding version, model, and dimensions

### Page resynchronization

A Page sync first retrieves the current Notion content and completes any missing
Phase 6 Embeddings. All current Chunk IDs are then upserted. Only after every
upsert succeeds does JARVIS delete IDs that were previously indexed for that Page
but are absent from the current Notion result.

An API or Chroma failure never creates a fallback document. Rerunning repeats the
Notion-derived sync and converges the Collection to the current Page. Historical
Embedding cache records may remain in `embeddings.sqlite3`, but stale records are
removed from the active Chroma index.

Sync one Page:

```powershell
.\.venv\Scripts\python.exe scripts\sync_notion_page_to_chroma.py <NOTION_PAGE_ID>
```

### Notes Data Source Content bulk sync

Memo pages store their text in the Notes Data Source `Content` property rather
than in Block Children. The Memo ingestion path therefore queries every Notes
page, retrieves the complete `Content` rich-text property with its own
pagination, and converts it into the same `NotionChunk` contract used by normal
pages:

```text
Notes Data Source Query (all pages)
→ complete Content property retrieval per Page
→ deterministic Memo Chunks
→ versioned Embeddings
→ active Chroma Collection
```

The Notion title is retained as the Chunk title and as a heading in the Chunk
content. Property-backed virtual Block IDs are derived from the canonical Page
ID, so unchanged title and Content values produce the same Chunk IDs on every
run. Memo records use `source_type=notion_memo` to distinguish them from normal
Block-backed pages.

Preview every page and candidate Chunk without calling OpenAI or changing
Chroma:

```powershell
.\.venv\Scripts\python.exe scripts\sync_notion_notes_to_chroma.py --dry-run
```

Create missing Embeddings and converge each Memo page in Chroma:

```powershell
.\.venv\Scripts\python.exe scripts\sync_notion_notes_to_chroma.py --apply
```

Dry Run is the default when neither option is specified. Apply is restart-safe:
unchanged Chunk versions reuse the local Embedding cache, Chunk IDs are
upserted, and stale Chunks belonging to each processed Memo page are deleted.
If one page fails, the remaining pages are attempted and the command exits with
a failure summary. Rerunning processes only missing or changed Embeddings.
An empty `Content` property produces no Chunk and removes an older Chroma Chunk
for that same page during Apply.

This command is currently explicit, not scheduled automatically. Run Apply after
adding or editing Memo pages until an incremental synchronization trigger is
introduced. The Data Source Query API currently returns at most 10,000 results
per query, so a larger Notes source will require a partitioned sync strategy.

Official Notion references:

- [Query a data source](https://developers.notion.com/reference/query-a-data-source)
- [Retrieve a page property item](https://developers.notion.com/reference/retrieve-a-page-property)

### Missing Page audit

The audit enumerates distinct Notion Page IDs in the current Collection and calls
the Notion Page API for each. A 404 response or a Page in Trash is reported with
all affected Chunk IDs. Permission, authentication, connection, and server errors
abort the audit rather than being misclassified as missing. The command never
deletes Chroma records.

```powershell
.\.venv\Scripts\python.exe scripts\audit_chroma_pages.py
```

Run the isolated end-to-end verification with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_chroma.py
```

It creates one temporary Notion child Page, runs Chunking, Embedding, persistent
Chroma sync twice, verifies unchanged-Chunk skipping and Collection separation,
moves the Notion Page to Trash, detects the stale indexed Page, and removes the
local Chroma/Embedding test data.

Phase 7 does not make Chroma authoritative and does not add semantic query or RAG
answer generation. Chroma can be rebuilt entirely from Notion.

Official references:

- [Chroma PersistentClient](https://docs.trychroma.com/reference/python/client)
- [Chroma Collection API](https://docs.trychroma.com/reference/python/collection)
- [Chroma upsert](https://docs.trychroma.com/docs/collections/update-data)
- [Chroma metadata filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering)

## Phase 8: RAG Retrieval

Phase 8 adds standalone semantic retrieval over the Phase 7 Chroma Collection.
It does not connect retrieval to the Router, text chat, Realtime tools, or answer
generation yet.

The processing flow is:

```text
Question
→ dedicated OpenAI Embedding client
→ active model/dimensions Chroma Collection
→ Top K by L2 distance
→ convert distance to score and apply threshold
→ remove exact duplicates and merge adjacent same-Page Chunks
→ apply total Context token upper bound
→ RetrievedChunk[]
```

`RetrievedChunk` is the common retrieval result and contains only:

- `content`
- `score`
- `title`
- `notion_page_id`
- `notion_url`
- `source_type`

### Retrieval settings

The defaults work without adding values to `.env`:

```dotenv
RAG_RETRIEVAL_TOP_K=5
RAG_RETRIEVAL_MIN_SCORE=0.45
RAG_RETRIEVAL_MAX_CONTEXT_TOKENS=2000
```

The question must use the same `OPENAI_EMBEDDING_MODEL` and
`OPENAI_EMBEDDING_DIMENSIONS` as the selected Chroma Collection. Retrieval fails
clearly instead of querying a mismatched Collection.

The existing Phase 7 Collection uses Chroma's default L2 distance. Phase 8
converts it to a higher-is-better bounded score with:

```text
score = 1 / (1 + distance)
```

The threshold is applied before duplicate cleanup. Exact duplicate content from
the same Notion Page is retained only once. Results with consecutive
`chunk_index` values from that Page are merged in document order; repeated
heading lines and directly overlapping lines are not repeated. Non-adjacent
Chunks remain separate results.

Because Phase 8 is intentionally independent of a target chat model, it does not
add a tokenizer dependency. The Context limiter counts UTF-8 bytes as a
conservative upper bound for byte-level tokenizers and truncates the lowest-level
content representation when necessary. The configured limit therefore will not
be exceeded by the value reported by the evaluation command. When retrieval is
connected to a specific LLM in a later phase, this estimator can be replaced by
that model's exact tokenizer without changing `RetrievedChunk`.

### Standalone evaluation

Run the three fixed evaluation questions from the roadmap:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_retrieval.py
```

The fixed cases are:

- `前にAECについてどう考えてた？`
- `最近後回しにしてた開発作業は？`
- `気分で音楽を選ぶ機能について考えたことは？`

Evaluate one or more custom questions instead:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_retrieval.py `
  --question "確認したい質問" `
  --question "別の質問"
```

The command calls OpenAI once per question to create the question Embedding, but
does not call Notion or an answer-generation LLM. It prints the score, source
metadata, retrieved content, and conservative Context token upper bound. Only
Pages already synchronized into the active Chroma Collection can be found.

Run the isolated unit tests without calling OpenAI or Notion:

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.test_rag_retrieval `
  tests.test_chroma_index
```

## Phase 9: LLM Context Integration

Phase 9 connects Phase 8 retrieval to text and Realtime conversations while
keeping the existing structured Memo, Task, and Memory operations unchanged.
No new environment variable is required.

### Text routing and Context

The text Router now supports:

```text
Router
├─ note
├─ task
├─ memory
├─ knowledge_search
└─ chat
```

`knowledge_search` is for ambiguous recall of prior thoughts, discussions,
ideas, and decisions. Explicit Memo CRUD remains `note`; explicit Task status,
date, list, and CRUD requests remain `task`; explicit long-term-memory CRUD
remains `memory`. In particular, `今日の未完了タスク` takes the structured
Task route and does not query Chroma.

Only `knowledge_search` calls `RagRetrievalService`. A successful retrieval is
added to that one Responses API request as a transient System Context. Each
reference contains the Chunk content, score, title, Notion Page ID, Notion URL,
and source type. The guard instructions treat retrieved content as untrusted
data, require answers to use only supported information, and require the title
and Notion URL for sources used in the answer.

The final SSE `done` payload also includes a `sources` array without Chunk
content. This lets an API client retain exact source information independently
of the generated prose.

If retrieval returns no Chunk above the configured score threshold, JARVIS does
not call the answer-generation model. It directly returns:

```text
関連情報を見つけられませんでした。
```

Embedding or Chroma failures return a separate temporary-unavailable message
and never fall through to ordinary chat. Error logs contain the exception type,
not the question text or credentials.

### Realtime knowledge Tool

Realtime sessions expose one additional read-only function Tool:

```text
Realtime model
→ search_knowledge(question)
→ RagRetrievalService
→ Chroma
→ function_call_output
→ follow-up audio response
```

The Tool result contains `success`, `found`, `message`, and `results`. Found
results use the common `RetrievedChunk` fields, including title and Notion URL.
For `found=false`, Realtime instructions require the model to speak the returned
message without guessing. They also explicitly reserve `list_tasks` with
`status_filter=todo` for today's incomplete tasks and preserve `search_notes`
and `search_memory` for their structured searches.

The Window already sends local Tool results back to Realtime as a
`function_call_output` conversation item and creates the follow-up response, so
Phase 9 requires no browser transport change.

### Conversation persistence boundary

Retrieved Chunk content and source payloads are transient. The Conversation
SQLite database still stores only the visible user message and final Assistant
message for this flow. The Assistant row records the route name but does not
store retrieved Chunk content, embeddings, or the source list. The existing
conversation context builder therefore continues to restore conversation only.

Only content already present in the active Chroma Collection can be retrieved.
Run `scripts/sync_notion_notes_to_chroma.py --apply` after adding or editing
Notes Data Source Memo pages so their `Content` values can participate in RAG.

Run Phase 9 tests without live OpenAI or Notion calls:

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.test_knowledge_service `
  tests.test_realtime_knowledge_tool `
  tests.test_intent_routing `
  tests.test_chat_service
```
