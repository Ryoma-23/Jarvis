# JARVIS Notion / RAG 開発記録

## 1. 概要

JARVISにNotion連携とRAG（Retrieval-Augmented Generation）を段階的に
追加した開発記録です。

実装は、既存のMemo・Task・Long-term Memory・テキスト会話・Realtime会話を
壊さないことを最優先にし、次の順序で進めました。

1. Notion REST APIへ安全に接続する
2. 既存ストレージとNotionをDual Writeで接続する
3. Notionの構造化データを読み取る
4. Memo・Task・Memoryの保存境界を整理する
5. Notion本文を検索可能なChunkへ変換する
6. ChunkのEmbeddingを作成・再利用する
7. Chromaを再生成可能なVector Indexとして導入する
8. 意味検索を単体で評価する
9. テキスト会話とRealtime会話へRAGを接続する
10. 複数のNotionページとNotesを差分・定期同期する

完成時点の基本方針は次のとおりです。

```text
Notion
  └─ Memo / Task / Memory / 通常ページの情報本体
       ↓ Chunking
Embedding Store
  └─ 再利用可能なEmbeddingキャッシュ
       ↓ Upsert
Chroma
  └─ Notionから再生成できる検索インデックス
       ↓ Retrieval
JARVIS Text / Realtime
  └─ 必要な質問にだけ検索結果をContextとして渡す
```

Chromaだけに存在する知識は作らず、Conversation SQLiteには従来どおり
ユーザーとAssistantの会話だけを保存します。

## 2. 設計上の重要な判断

### 2.1 既存機能をNotion障害から分離する

Notion設定が存在しない場合でも、既存JARVISは起動できます。Memo・Task・
Memoryの書き込みはLocal-firstで行い、ローカル保存に成功した後でNotionへ
同期します。

```text
Local成功 + Notion成功  → synced
Local成功 + Notion失敗  → pending（ローカルデータは利用可能）
Local失敗               → Notionへ書かない
```

読み取りはFeature Flagを有効にした対象のみNotionを優先し、Notion APIの障害や
設定不備が発生した場合はLocal JSONへフォールバックします。そのため、Notionを
優先的な参照先に切り替えた後も、Local JSONは削除せず復旧経路として維持します。

### 2.2 構造化検索とRAGを分ける

明確な条件を持つ操作は、Vector検索へ送らず構造化検索を使います。

- Memoの一覧、Local ID検索、Content検索
- 今日の未完了Task、期限、Status検索
- MemoryのCategory検索

「前にどう考えていたか」「以前話したアイデア」のような曖昧な知識検索だけを
RAGへ送ります。特に「今日の未完了タスク」はRAGではなくTask Data Sourceの
構造化検索を使用します。

### 2.3 Notion Search APIを知識検索の中心にしない

Memo検索はNotes Data Source Query、TaskとMemoryも各Data SourceのQueryを
使用します。Workspace全体のSearch APIは、条件が明確なデータ検索の中心には
採用していません。

### 2.4 NotionとChromaの責務を分ける

- Notion: 人が編集できる情報本体
- Embedding Store: 同じ内容を再Embeddingしないためのキャッシュ
- Chroma: 消してもNotionから再生成できる検索インデックス
- Conversation SQLite: 会話履歴のみ

Embeddingモデルまたは次元数が異なる場合は、Chroma Collectionを分離します。
これにより、互換性のないVectorが同じCollectionへ混在しません。

### 2.5 秘密情報を境界の外へ出さない

Notion Internal Connectionの静的トークンとOpenAI API Keyは環境変数からだけ
読み取ります。Clientの表現、ログ、ユーザー向けエラー、テストFixtureへTokenを
含めません。`.env`はGit管理対象外であり、実装作業でも変更していません。

## 3. Phase別の実装内容

### Phase 1 — Notion Connection

Notion APIだけを安全に使用できる独立した接続境界を作成しました。

実装内容:

- `NOTION_API_TOKEN`、`NOTION_PARENT_PAGE_ID`、`NOTION_API_VERSION`を設定化
- API versionの既定値を`2026-03-11`に設定
- `Authorization`、`Notion-Version`、`Content-Type`の共通Header
- HTTP TimeoutとJSON Response検証
- 401、403、404、429、5xxの安全な例外変換
- Windowsの信頼済みRoot Certificateを利用したTLS接続
- 親Page取得、テストPage作成、Page ID再取得による接続確認
- 実APIを使わないNotion Clientテスト

`NOTION_PARENT_PAGE_ID`は接続確認用の子Pageや、JARVIS用Databaseを作成するときの
配置先です。RAGで参照する全ページを指定する設定ではありません。

### Phase 2 — Memo Notion Write

既存の`add_note()`の返答とLocal保存を維持しながら、Notes Data Sourceへの
Dual Writeを追加しました。

Notes Schema:

| Property | Type | 用途 |
| --- | --- | --- |
| Title | title | Memoの短いタイトル |
| Content | rich_text | Memo本文 |
| Jarvis Local ID | number | 既存Local整数ID |
| Created At | date | 作成日時 |
| Source | select | JARVISからの作成元 |
| Sync Key | rich_text | 重複防止用の安定キー |

Local ID確定後にSync Keyを作成し、NotionへPageを作成します。Timeout後に再実行
しても、作成前にSync Keyを検索するため同じMemoを重複作成しません。Notion書き
込みに失敗したMemoは`pending`としてLocalに残し、後から再同期できます。

### Phase 3 — Notion Read / Structured Search

Vector DBを使用せず、Notes Data SourceからMemoを取得する読み取り機能を追加
しました。

- Page ID取得
- 全件一覧
- Local ID検索
- Content部分一致検索
- Created At順Sort
- Data Source Queryのページネーション
- Notion Read Feature Flag
- Notion失敗時のLocal JSONフォールバック
- LocalとNotionの件数・主要Field比較

この時点ではEmbeddingやRAGは導入していません。

### Phase 4 — Existing Storage Integration

Router、IntentService、Realtime Toolから保存先の知識を取り除き、Serviceの下に
Repository境界を設けました。

```text
IntentService / Realtime Tool
  → Entity Service
    → Repository
      ├─ Local JSON
      ├─ Notion Data Source
      └─ Dual Write / Read fallback
```

#### Memo

- 一覧、検索、削除をNotion対応
- Local整数ID、Sync Key、Notion Page IDの対応管理
- 削除をNotion PageのTrash操作へ変換
- 既存Memo移行コマンド
- Dry RunとSync Keyによる重複防止

#### Task

Task Data Sourceへ次の項目を保存します。

- Title
- Status
- Due Date
- Created At
- Completed At
- Jarvis ID
- Sync Key

`complete_tasks()`はStatusとCompleted Atを同じNotion更新で変更します。

#### Long-term Memory

Memory Data Sourceへ次の項目を保存します。

- Content
- Category
- Created At
- Updated At
- Jarvis ID
- Sync Key

既存の`format_memory_for_prompt()`は暫定経路として維持しました。この段階では
Long-term MemoryをRAGの関連度検索へ置き換えていません。

#### 読み取り切り替え

以下のFeature Flagを個別に用意しました。

```dotenv
NOTION_NOTES_READ_ENABLED=true
NOTION_TASKS_READ_ENABLED=true
NOTION_MEMORY_READ_ENABLED=true
```

有効時はNotionを優先して読みますが、書き込みは引き続きLocal-firstです。

### Phase 5 — Chunking

Notion Page取得だけでは本文Blockが得られないため、Block Children APIを再帰的に
呼び出す処理を実装しました。

- `has_children`を持つBlockの再帰取得
- Block Childrenのページネーション
- Paragraph、Heading、List、Quote、Codeなどの共通テキスト化
- 空文字、装飾だけのBlockの除外
- Heading Pathを維持したChunk分割
- 最大Chunk文字数による分割
- 安定したChunk IDとContent Hash

Chunk Metadata:

- `chunk_id`
- `notion_page_id`
- `block_id` / `block_ids`
- `title`
- `chunk_index`
- `content_hash`
- `last_edited_time`
- `source_type`
- `notion_url`
- `heading_path`

Chunk IDはPage ID、基準Block ID、Content Hashから決定します。同じ内容を再同期
した場合は同じChunk IDになります。

### Phase 6 — Embedding

Embedding処理を会話用OpenAI Clientから分離しました。

- 既定モデル:`text-embedding-3-small`
- モデル、次元数、Batch Sizeを設定化
- 空Chunkの除外
- 複数ChunkのBatch送信
- `content_hash + model + dimensions`によるEmbedding Version
- SQLite Embedding Storeへの途中結果保存
- 未変更ChunkのEmbedding再利用
- API失敗後の再実行

Batch途中まで成功した場合も保存済みEmbeddingは残るため、次回は未完了Chunkだけを
処理できます。

### Phase 7 — Chroma Vector DB

このPhaseでChromaを導入し、永続化先を`data/chroma/`に設定しました。

- Embeddingモデル・次元ごとのCollection分離
- Chunk IDをKeyとしたUpsert
- Page ID、Title、URL、Source TypeなどのMetadata保存
- Page再同期時の古いChunk削除
- Notionに存在しない、またはTrashにあるPageの監査
- Notes Data Sourceの`Content` PropertyをChunk化する一括同期

Notesの`Content`はData Source Query Responseだけでは長文が省略される可能性がある
ため、Page Property Item APIのページネーションで完全な本文を取得してからChunk化
します。

### Phase 8 — RAG Retrieval

Routerや会話へ接続する前に、検索単体のRetrieval Serviceを作成しました。

```text
Question
  → Question Embedding
  → Chroma Top K
  → L2 distanceをscoreへ変換
  → 最小scoreを適用
  → 重複・近接Chunkを整理
  → Context上限を適用
  → RetrievedChunk[]
```

`RetrievedChunk`は次の共通形式です。

- `content`
- `score`
- `title`
- `notion_page_id`
- `notion_url`
- `source_type`

同一Pageの完全重複を除去し、連続するChunkを順序どおりに統合します。Context量は
設定値以下に制限します。現在のScoreはChromaのL2 distanceから
`1 / (1 + distance)`で計算します。

評価用に次の固定質問を用意しました。

- 「前にAECについてどう考えてた？」
- 「最近後回しにしてた開発作業は？」
- 「気分で音楽を選ぶ機能について考えたことは？」

評価の結果、閾値を機械的に下げると無関係なChunkが採用されることも確認しました。
そのため、`RAG_RETRIEVAL_MIN_SCORE`は固定質問の正解順位とScoreを見ながら調整する
方針としました。

### Phase 9 — LLM Context Integration

#### テキスト会話

Routerへ`knowledge_search`を追加しました。

```text
Router
├─ note
├─ task
├─ memory
├─ knowledge_search
└─ chat
```

`knowledge_search`のときだけRetrievalを実行し、取得した本文、Title、Notion URL、
Page ID、Score、Source Typeを一時的なSystem Contextへ追加します。

閾値以上のChunkがない場合は回答生成LLMを呼ばず、次の固定応答を返します。

```text
関連情報を見つけられませんでした。
```

EmbeddingまたはChromaが一時利用不能な場合も通常Chatへ流さず、検索不能であることを
明示します。これにより、検索結果が弱い質問を推測で補うことを防ぎます。

#### Realtime会話

RealtimeはRouterを通らないため、読み取り専用の`search_knowledge` Toolを追加
しました。

```text
Realtime model
  → search_knowledge(question)
  → Retrieval Service
  → Chroma
  → function_call_output
  → 音声回答
```

既存のMemo・Task・Memory Toolは変更していません。検索結果がない場合はToolの
Messageをそのまま伝え、推測しないようRealtime Instructionsへ明記しました。

検索に使ったChunk本文とSource一覧は一時Contextであり、Conversation SQLiteへは
保存しません。SQLiteには従来どおり表示された会話だけを保存します。

## 4. 複数ページと運用同期

### 4.1 Knowledge Source Registry

`NOTION_PARENT_PAGE_ID`を複数形にするのではなく、RAGで参照する通常Pageを専用の
Registryで管理する方式にしました。

```text
data/notion_knowledge_sources.json
├─ include_notes
└─ pages[]
   ├─ page_id
   └─ label
```

Notion側では、参照したいPageをJARVIS Internal Connectionへ共有します。その後、
Page IDをRegistryへ登録します。親Pageと開発記録Pageは独立した参照元として扱えます。

既存Chromaから通常PageをRegistryへ取り込むコマンドも用意しました。単Page同期
コマンドは成功後に対象Pageを自動登録するため、統合同期から誤って削除されません。

### 4.2 差分同期

統合同期はRegistryの通常PageとNotes Data Sourceを一度に処理します。

```text
Registry / Notes Query
  → Page last_edited_time確認
    ├─ 未変更 → Block/Content取得とEmbeddingをスキップ
    └─ 変更あり
         → 本文取得
         → Chunking
         → 未変更Embeddingを再利用
         → Chroma Upsert
         → 古いChunk削除
         → Sync State保存
```

同期状態は`data/notion_knowledge_sync_state.json`へ保存します。Page単位で成功状態を
保存するため、別Pageの失敗後も完了済み処理をやり直しません。

Notes Queryが正常終了した後、以前IndexされていたMemoが結果から消えていれば
Chromaから削除します。通常PageがTrash、404、またはRegistry解除になった場合も
Chromaから削除します。Notion本体は変更しません。

### 4.3 安全対策

- Dry Runを既定動作にする
- Applyは明示指定する
- 同期Lockで多重起動を防ぐ
- 6時間以上残ったLockを中断プロセスの残骸として回復する
- 429、5xx、Connection、Embedding、Chromaの一時障害を再試行する
- Pageごとの失敗を記録し、可能な残りのPageを処理する
- Token、取得本文、質問を同期Logへ出さない

Registry Fileがまだ存在しない場合は、既存の通常Pageを削除しない非Authoritative
状態として扱います。既存IndexをRegistryへImportして保存した後から、Registryを
通常Pageの同期対象一覧として扱います。

### 4.4 定期同期

Trayへ任意有効化のSchedulerを追加しました。

```dotenv
NOTION_KNOWLEDGE_SYNC_ENABLED=true
NOTION_KNOWLEDGE_SYNC_INTERVAL_MINUTES=60
NOTION_KNOWLEDGE_SYNC_RETRY_COUNT=3
```

既定では無効です。有効化してTrayを再起動すると、起動時に1回、その後は指定間隔で
統合同期を別Processとして実行します。同期に失敗しても、JARVIS Server、Text Chat、
Realtime、Memo・Task・Memory機能は停止しません。

## 5. 主な設定値

| 設定 | 用途 |
| --- | --- |
| `NOTION_API_TOKEN` | Internal Connection Token |
| `NOTION_API_VERSION` | Notion REST API version |
| `NOTION_PARENT_PAGE_ID` | 接続確認・Database作成時の親Page |
| `NOTION_NOTES_DATA_SOURCE_ID` | Notes Data Source |
| `NOTION_TASKS_DATA_SOURCE_ID` | Tasks Data Source |
| `NOTION_MEMORY_DATA_SOURCE_ID` | Memory Data Source |
| `NOTION_*_READ_ENABLED` | EntityごとのNotion優先読み取り |
| `OPENAI_EMBEDDING_MODEL` | Embedding Model |
| `OPENAI_EMBEDDING_DIMENSIONS` | Embedding Vector次元数 |
| `OPENAI_EMBEDDING_BATCH_SIZE` | API Batch Size |
| `RAG_RETRIEVAL_TOP_K` | Chroma取得候補数 |
| `RAG_RETRIEVAL_MIN_SCORE` | 採用する最小Score |
| `RAG_RETRIEVAL_MAX_CONTEXT_TOKENS` | Context量の上限 |
| `NOTION_KNOWLEDGE_SYNC_ENABLED` | Tray定期同期の有効化 |
| `NOTION_KNOWLEDGE_SYNC_INTERVAL_MINUTES` | 定期同期間隔 |
| `NOTION_KNOWLEDGE_SYNC_RETRY_COUNT` | 一時障害時の最大試行回数 |

## 6. 主な運用コマンド

接続確認:

```powershell
.\.venv\Scripts\python.exe scripts\verify_notion_connection.py
```

Storage作成・移行:

```powershell
.\.venv\Scripts\python.exe scripts\setup_notion_storage.py
.\.venv\Scripts\python.exe scripts\migrate_notion_storage.py --dry-run
.\.venv\Scripts\python.exe scripts\migrate_notion_storage.py --apply
```

参照Page管理:

```powershell
.\.venv\Scripts\python.exe scripts\manage_notion_knowledge_sources.py list
.\.venv\Scripts\python.exe scripts\manage_notion_knowledge_sources.py `
  add <NOTION_PAGE_ID> --label "開発記録" --apply
```

統合差分同期:

```powershell
.\.venv\Scripts\python.exe scripts\sync_notion_knowledge.py --dry-run
.\.venv\Scripts\python.exe scripts\sync_notion_knowledge.py --apply
```

Chroma監査:

```powershell
.\.venv\Scripts\python.exe scripts\audit_chroma_pages.py
```

RAG固定質問評価:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_retrieval.py
```

全Pythonテスト:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 7. 完成時の検証結果

2026年9月7日時点で次を確認しました。

- Python全回帰テスト: 269件成功
- 通常Notion Page 2件をKnowledge Source Registryへ登録
- Notesを含むChroma Indexed Page: 5件
- Notion上でMissingまたはTrashのIndexed Page: 0件
- 新規Memo 1件のEmbedding・Chroma同期成功
- Apply後の再Dry Run:
  - Changed Pages: 0
  - Unchanged Pages: 5
  - Removed Pages: 0
  - Failures: 0
- 未変更の大規模開発記録Pageは1,555 Chunkすべて再Embeddingせずスキップ
- API Tokenを出力しないことを単体テストと実行結果で確認

マイク、スピーカー、Wake Wordを含む音声Hardwareの挙動は、このRAG同期検証の対象外
です。定期同期は自動テスト済みですが、Trayを再起動して実際の同期間隔を待つ手動確認
は別途必要です。

## 8. 現在残っている改善候補

一連のNotion連携とRAGは動作する状態ですが、将来の品質・運用改善として次が残って
います。

- Vector検索とKeyword検索を組み合わせるHybrid Search
- Rerankerによる検索順位の改善
- 固定3質問だけでなく正解Chunk付き評価Datasetの整備
- 質問種類・Source Typeごとの閾値調整
- 対象LLMのTokenizerを使った厳密なContext Token計算
- UI上でのNotion出典Link表示
- Long-term Memoryを全件Prompt投入から関連記憶取得へ切り替える
- 通常Notion PageへJARVISから直接追記する書き込み機能
- 10,000件を超えるNotes Data Source向けの分割同期
- Tray定期同期の最終成功日時・件数・失敗詳細を表示する管理画面

これらは現在のRAG基盤を置き換えず、Retrieval品質または運用性を高める追加Phaseとして
実装できます。

## 9. 関連実装

主要な実装場所:

- `app/integrations/notion_client.py`
- `app/integrations/notion_memo_reader.py`
- `app/integrations/notion_memo_writer.py`
- `app/integrations/notion_task_store.py`
- `app/integrations/notion_memory_store.py`
- `app/chunking/notion_blocks.py`
- `app/chunking/notion_chunker.py`
- `app/chunking/notion_memo_chunker.py`
- `app/integrations/openai_embedding_client.py`
- `app/embeddings/embedding_service.py`
- `app/embeddings/embedding_store.py`
- `app/vector/chroma_index.py`
- `app/vector/notion_chroma_sync.py`
- `app/rag/retrieval_service.py`
- `app/services/knowledge_service.py`
- `app/services/realtime_tools/knowledge_tools.py`
- `app/knowledge_sync/`
- `tray/knowledge_sync_scheduler.py`

詳細なSetup、Troubleshooting、個別コマンドの説明は
`docs/notion-integration.md`を参照してください。
