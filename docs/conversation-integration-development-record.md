# JARVIS チャット・音声会話統合 開発記録

## 1. 概要

JARVISで別系統になっていたテキストチャットとRealtime音声会話を、同じ会話に
対する入力方法の違いとして統合した開発記録です。

開発期間は2026年8月18日から8月26日です。統合後の安定化として、音声入力の
誤検知対策、発話終了判定、無操作時の自動切断も同じ期間に整備しました。

最終的に実現した構成は次のとおりです。

```text
テキスト入力 ─┐
               ├─→ 共通Conversation ID / ConversationService
音声入力 ──────┘                  ↓
                              SQLite履歴
                                  ↓
                 ┌────────────────┴────────────────┐
                 │                                 │
        Responses API経路                 Realtime API経路
        （Realtime未接続時）              （音声・接続中テキスト）
                 │                                 │
                 └──────── 共通Assistant履歴 ────────┘
                                  ↓
                         共通チャット欄へ表示
```

ここでいう`ConversationService`は、両方のLLM通信を直接実行する単一の
オーケストレーターではありません。Conversation ID、履歴、Context、状態、
重複防止を共有する会話ドメインの境界です。Responses APIのストリーミング制御は
`chat_service.py`、RealtimeのWebRTC・DataChannel・マイク制御はWindow側が担当します。

## 2. 開発前の状態と問題

開発前は、テキストと音声に次の分離がありました。

- テキスト会話はプロセス内の`conversation_history`を使用していた
- テキスト回答は`POST /chat/stream`からResponses APIへ送信していた
- 音声会話は接続中のRealtime ConversationだけをContextとしていた
- Realtimeの音声transcriptionはチャット欄や永続履歴へ保存されていなかった
- Windowまたはサーバーの再起動後に、テキスト履歴を確実に復元できなかった
- Realtimeを切断して再接続すると、直前の音声会話Contextが失われた
- Realtime接続中にテキストを送ると、別のResponses API会話として処理される余地が
  あった

この状態では、テキストで提示した候補を音声で番号指定する、音声の質問を
テキストで続ける、といった入力方法をまたぐ会話が成立しませんでした。

## 3. 目標と非目標

### 3.1 目標

- テキストと音声で同じActive Conversationを使用する
- 両方のユーザー入力とAssistant回答をSQLiteへ保存する
- 音声transcriptも共通チャット欄へ表示する
- アプリケーション再起動後も履歴を維持する
- Realtime再接続時に直近の共通履歴を復元する
- Realtime接続中のテキストを同じRealtime Conversationへ送る
- Memo・Task・Memory・tool callingの既存動作を維持する
- 割り込み、失敗、重複イベントを履歴上で安全に扱う
- 履歴保存障害が現在の回答、音声cleanup、Wake Word復帰を止めないようにする

### 3.2 非目標

- Responses APIとRealtime APIを同じ通信実装へ統合すること
- Realtime音声バイト列そのものをSQLiteへ保存すること
- 過去のtool callをRealtime再接続時に再実行すること
- Speaker Verificationや声紋認証を導入すること
- 古いConversationを削除するUIやAPIを追加すること

## 4. 設計上の重要な判断

### 4.1 会話を入力方法ではなくConversation IDで識別する

Active Conversationはアプリケーション所有のIDで管理します。テキストと音声は
別履歴を持たず、Messageの`source`だけを`text`または`voice`として記録します。

```text
Conversation A
  ├─ user      / source=text
  ├─ assistant / source=text
  ├─ user      / source=voice
  └─ assistant / source=voice
```

`source`は入力・出力経路の追跡に使い、LLMへ渡すroleは従来どおり`user`と
`assistant`です。

### 4.2 SQLiteを共通履歴の正本にする

共通履歴は`data/conversations.sqlite3`へ永続化します。プロセス内のグローバル履歴を
正本にはしません。これにより、Windowやサーバーを再起動してもActive Conversationと
Messageを再取得できます。

### 4.3 Conversation Managerは履歴の境界に限定する

`ConversationService`が担当するのは次の責務です。

- Active Conversationの作成・取得・切り替え
- user／assistantメッセージの登録
- `text`／`voice` sourceの検証
- `pending`／`completed`／`interrupted`／`failed`状態の管理
- 直近15ユーザーターンからのContext生成
- Realtime履歴復元イベントの生成
- hidden tool metadata用の保存・取得インターフェース

通信方式ごとにライフサイクルが大きく異なるため、Responses APIのSSE処理と
RealtimeのWebRTC処理は無理に一つのManagerへ集約していません。この分離により、
マイク所有権やWake Word復帰をテキスト経路から切り離したまま、会話の意味だけを
共有しています。

### 4.4 Contextは直近15ユーザーターンに制限する

Contextは単純な15メッセージではなく、15番目に新しい適格なuserメッセージから
始まるターン単位で生成します。空メッセージと次の状態は除外します。

- `pending`
- `interrupted`
- `failed`
- `system`／`tool` role
- `metadata.hidden = true`

このルールはResponses API入力とRealtime履歴復元の両方で共通です。

### 4.5 Realtime履歴はテキストとして復元する

保存済みのテキストと音声transcriptを、接続後に`conversation.item.create`で順番に
投入します。userは`input_text`、assistantは`output_text`として復元します。
音声データやtool callは再投入しません。

履歴復元中はマイクtrackを無効にし、すべての復元itemについてサーバー応答を確認して
から入力を有効化します。復元itemのIDを記録し、受信イベントを再保存しないように
しています。

### 4.6 Realtime接続中のテキストはRealtimeへ送る

Realtime接続中のテキスト入力は`/chat/stream`へ送りません。DataChannelで
`conversation.item.create`の`input_text`を送り、受理・保存後に`response.create`を
送信します。これにより、音声とテキストが同じRealtime ConversationのContextを
即時共有し、回答も画面表示と音声再生の両方へ流れます。

Realtime未接続時だけ、従来のResponses APIストリーミングを使用します。

### 4.7 同時入力は状態に応じて直列化する

- ユーザー音声認識中のテキスト入力は待機する
- JARVIS音声再生中のテキスト入力は明示的な割り込みとして扱う
- 回答生成中の追加テキストはキューへ入れる
- 一つのRealtime Conversationへ同時に複数回答を生成させない

この制御はブラウザ側のRealtime lifecycle、音声状態、text turn queueで行います。

### 4.8 deltaは表示だけ、確定イベントで保存する

Assistant音声transcriptのdeltaは共通チャット欄へ逐次表示しますが、SQLiteへは
書きません。transcript doneで確定した内容だけを保存します。これにより、delta単位の
大量書き込みや重複を避けています。

### 4.9 外部IDで重複保存を防ぐ

Realtimeの`item_id`と`response_id`には、nullでない値だけを対象とする一意Indexを
設定しました。同じ完了イベントが再送されても同じMessageを返し、別Conversationや
異なる内容と衝突した場合はエラーにします。

アプリケーション所有のMessage IDも再試行時に再利用し、Realtime外のテキストMessageも
重複させません。

### 4.10 保存失敗は会話を停止させない

SQLite書き込み失敗はメモリ上のRetry Queueへ移し、1秒間隔で最大3回再試行します。
同一Conversation内はFIFOで処理し、userより先にassistantだけが保存されることを
防ぎます。

再試行中も次の処理は継続します。

- Responses APIのストリーミング
- Realtimeの`response.create`
- 音声再生と画面表示
- Realtime cleanup
- Tray通知とWake Word復帰

最終失敗時だけログと画面上の控えめな警告を出します。Retry Queueはプロセス内だけに
存在するため、再試行中にサーバープロセスを終了した場合、その未完了処理は失われます。

### 4.11 UIへ内部情報を露出しない

履歴APIは表示可能なuser／assistant Messageだけを返します。hidden tool metadata、
外部ID、内部エラー詳細は返しません。描画は`innerHTML`ではなく`textContent`と
Text Nodeを使い、Message IDとDOM要素を対応付けます。

## 5. Phase別の実装内容

### Phase 0 — 既存動作の固定

統合前の挙動を回帰テストとして固定しました。

- テキスト会話の履歴追加、上限、ストリーミング
- Memo・Task・Memoryのintent routing
- Realtimeイベント、tool calling、cleanup
- 既存Window／Tray連携

主な追加ファイル:

- `tests/test_chat_service.py`
- `tests/test_intent_routing.py`

### Phase 1 — Conversation Store

SQLiteによる永続化層を追加しました。

- `conversations`と`messages`テーブル
- Active Conversationの一意制約
- 順序付きMessage
- `item_id`／`response_id`の重複防止
- transactionとrollback
- Message状態更新

主な追加ファイル:

- `app/services/conversation_store.py`
- `tests/test_conversation_store.py`
- `docs/conversation-store.md`

### Phase 2 — Conversation Manager

Storeの上に共通会話ドメインサービスを追加しました。

- Active Conversation管理
- text／voice Message登録
- 直近15ターンのContext生成
- Realtime復元イベント生成
- interrupted／failed除外
- hidden tool metadata用API

主な追加ファイル:

- `app/services/conversation_service.py`
- `tests/test_conversation_service.py`

### Phase 3 — テキスト会話の共通履歴移行

グローバル`conversation_history`を廃止し、`chat_service`を
`ConversationService`へ接続しました。

- user入力を回答生成前に保存
- 共通ContextをResponses APIへ渡す
- Assistant全文をストリーム確定時に保存
- 例外・中断・不完全応答を`failed`として保存
- Memo・Task・Memory結果も可視履歴へ保存
- SSEへ`conversation_id`とMessage IDを追加

### Phase 4 — Conversation APIと画面履歴

Windowが永続履歴を取得・表示するAPIを追加しました。

- `GET /conversations/active`
- `GET /conversations/{conversation_id}/messages`
- `POST /conversations`
- Window load／focus時の履歴再読込
- 新しい会話の作成と表示クリア
- Message IDとDOM要素の対応
- 安全なテキスト描画

主な追加ファイル:

- `app/routes/conversation.py`
- `tests/test_conversation_api.py`

### Phase 5 — 音声会話の表示・保存

Realtimeイベントを共通履歴へ接続しました。

- user transcription completedを表示・保存
- Assistant transcript deltaを逐次表示
- transcript doneだけをSQLiteへ保存
- voice Messageへ`item_id`／`response_id`を関連付け
- 割り込み時にAssistant Messageを`interrupted`へ更新
- 復元イベントや重複イベントの再保存を防止

主な追加ファイル:

- `tests/test_realtime_conversation_history.py`

### Phase 6 — Realtime開始時の履歴復元

新しいRealtime接続へ共通履歴を復元しました。

- token取得時にローカル`conversation_id`を確定
- 直近15ターンを復元イベントへ変換
- DataChannel open後に順番どおり投入
- 復元完了までマイク入力を無効化
- 復元Messageを再保存しない
- 復元失敗時は通常cleanupからWake Wordへ復帰

主な追加ファイル:

- `tests/test_realtime_history_restore.py`

### Phase 7 — Realtime接続中のテキスト入力統合

テキストを同じRealtime Conversationへ送る経路を実装しました。

- 接続状態による`/chat/stream`とDataChannelの切り替え
- `input_text` item作成後の`response.create`
- 音声再生と共通チャット欄への同時出力
- text turn queueと音声状態の競合防止
- tool calling後のfollow-up responseとの関連維持

主な追加ファイル:

- `tests/test_realtime_text_input.py`

### Phase 10 — 保存失敗・再試行

履歴保存を会話本体から切り離すRetry Queueを実装しました。

- SQLite例外の捕捉
- メモリ上の非同期再試行
- Conversation単位のFIFO
- 安定したMessage IDとoperation ID
- status確認APIと最終失敗警告
- cleanupとWake Word復帰からの分離

主な追加ファイル:

- `app/services/conversation_retry_service.py`
- `tests/test_conversation_retry_service.py`

Phase番号は当初の実装計画を維持しています。この開発系列には、Phase 8／9という名前の
独立した統合コミットはありません。

### 整理と安定化

統合完了後に、古いbackupスクリプトと手動確認用スクリプトを削除し、実行ログをGit追跡
対象から外しました。

音声会話については次の調整も行いました。

- WebRTCのecho cancellation、noise suppression、auto gain control
- Realtime入力の`far_field` noise reduction
- Server VAD threshold `0.8`
- 発話途中の考える間を許容する`silence_duration_ms = 1200`
- JARVIS発話中だけ適用する600 msのbarge-in guard
- 咳、短いfiller、非音声transcriptの除外
- Realtimeが60秒間idleのときの自動cleanupとWake Word復帰

## 6. 現在の処理フロー

### 6.1 Realtime未接続時のテキスト

```text
Windowテキスト入力
  → POST /chat/stream + conversation_id
  → user Message保存（source=text）
  → ConversationService.build_context()
  → Responses APIへ送信
  → SSE deltaを画面表示
  → 完了時にAssistant Message保存（source=text）
```

### 6.2 音声入力

```text
マイク入力
  → Realtime Server VAD
  → speech_stopped
  ├─ 通常発話: response.create
  └─ JARVIS再生中: 600 msと確定transcriptを確認後に割り込み・response.create
  → input_audio_transcription.completed（回答生成とは独立して到着）
  → 意味のあるtranscriptを共通チャット欄へ表示・保存（source=voice）
  → Assistant audio + transcript delta
  → 画面表示・音声再生
  → transcript doneでAssistant Message保存
```

### 6.3 Realtime接続中のテキスト

```text
Windowテキスト入力
  → Realtime text queue
  → conversation.item.create / input_text
  → server item ID確認
  → user Message保存（source=text）
  → response.create
  → Assistant audio + transcript
  → 画面表示・音声再生・Assistant Message保存（source=text）
```

### 6.4 Realtime再接続

```text
Active Conversation取得
  → Realtime token + conversation_id
  → WebRTC接続（マイクtrackはdisabled）
  → 共通履歴から直近15ターン取得
  → conversation.item.createを順番に送信
  → 全itemの完了確認
  → マイクtrackをenabled
  → 同じ文脈で音声・テキスト会話を継続
```

### 6.5 割り込み

```text
JARVIS音声再生中にspeech_started
  → 即時cancelしない
  → 600 ms継続と確定transcriptを確認
  ├─ 咳・短い音・意味のないtranscript → 無視
  └─ 意味のある発話
       → response.cancel
       → output_audio_buffer.clear
       → Assistant履歴をinterruptedへ更新
       → 新しいresponse.create
```

### 6.6 60秒idle終了

```text
履歴復元完了・マイク有効化
  → client-side idle timer開始
  → 発話・回答・tool・text queue中は停止
  → 処理完了後に60秒を再計測
  → idleのまま満了
  → finishRealtimeVoice("idle_timeout")
  → マイク・DataChannel・PeerConnectionをcleanup
  → Trayへfinished通知
  → Wake Word待機へ復帰
```

## 7. データモデル

### conversations

| 項目 | 役割 |
|---|---|
| `id` | アプリケーション所有のConversation ID |
| `title` | 任意タイトル |
| `is_active` | 現在継続するConversation |
| `created_at` | 作成日時 |
| `updated_at` | 最終更新日時 |

Active Conversationは部分一意Indexにより最大一件です。

### messages

| 項目 | 役割 |
|---|---|
| `id` | アプリケーション所有のMessage ID |
| `conversation_id` | 所属Conversation |
| `sequence` | Conversation内の順序 |
| `role` | `user`／`assistant`／`system`／`tool` |
| `source` | `text`／`voice`／`system`／`tool` |
| `status` | `pending`／`completed`／`interrupted`／`failed` |
| `content` | 表示・Contextに使う本文 |
| `item_id` | Realtime itemの重複防止ID |
| `response_id` | Realtime responseの重複防止ID |
| `metadata_json` | intentやhidden tool情報 |
| `error_message` | 内部エラー情報 |

## 8. 主要ファイル

| ファイル | 役割 |
|---|---|
| `app/services/conversation_store.py` | SQLite schema、transaction、Message永続化、重複防止 |
| `app/services/conversation_service.py` | 共通Conversation管理、Context、Realtime復元、状態管理 |
| `app/services/conversation_retry_service.py` | 非同期保存再試行とoperation status |
| `app/services/chat_service.py` | Realtime未接続時のResponses APIテキスト経路 |
| `app/services/realtime_service.py` | Realtime tokenとsession instructions |
| `app/routes/conversation.py` | Active Conversation、履歴、作成、再試行status API |
| `app/routes/realtime.py` | token、復元履歴、Realtime Message保存、割り込み、tool API |
| `static/script.js` | 画面履歴、Realtime lifecycle、音声・テキストqueue、表示、cleanup |
| `main.py` | Conversation／Realtime router登録 |

## 9. テスト構成

会話統合を主に次のテストで固定しています。

| テスト | 対象 |
|---|---|
| `tests/test_chat_service.py` | テキスト保存、Context、stream、失敗状態、特殊intent |
| `tests/test_intent_routing.py` | Memo・Task・Memoryの既存routing |
| `tests/test_conversation_store.py` | schema、transaction、active管理、重複防止、状態 |
| `tests/test_conversation_service.py` | 15ターンContext、source、除外条件、復元イベント |
| `tests/test_conversation_api.py` | 履歴API、画面契約、保存警告 |
| `tests/test_realtime_conversation_history.py` | 音声transcript、表示、確定保存、割り込み |
| `tests/test_realtime_history_restore.py` | 復元順序、マイク有効化条件、conversation_id |
| `tests/test_realtime_text_input.py` | Realtime text切替、queue、tool follow-up |
| `tests/test_conversation_retry_service.py` | 再試行、FIFO、重複防止、最終失敗 |
| `tests/test_realtime_bridge.py` | cleanup通知とWake Word復帰 |
| `tests/test_window_realtime_start.py` | Realtime設定、VAD、barge-in、idle cleanup |

自動テストで確認できるのはデータ、イベント、API、状態遷移、静的なJavaScript契約です。
マイク、スピーカー、テレビ音声、ReSpeaker、実際の認識精度と体感遅延は実機確認が必要です。

## 10. 実装結果

統合後は次の会話が成立します。

```text
テキストで候補を作る
  → 音声で「2番にして」と指定する

音声で質問する
  → 接続中にテキストで補足する
  → 回答が画面と音声の両方へ出る

音声会話を切断する
  → 再接続する
  → 直前の共通履歴を使って続ける

Windowまたはサーバーを再起動する
  → SQLiteのActive Conversationを再表示する
```

チャット欄はテキスト専用機能ではなく、JARVISとの共通Conversationを確認する画面に
なりました。音声とテキストは入力方法として切り替えられ、保存先、Context、表示先を
共有します。

## 11. 現在の制約と残課題

### 11.1 hidden tool metadataは実運用経路へ未接続

`ConversationService.record_hidden_tool_metadata()`と取得APIは実装・テストされていますが、
現在のMemo・Task・Memory・Realtime tool実行経路からは呼ばれていません。そのため、
通常運用でhidden tool Messageは作成されません。

将来接続する場合は、tool実行の直前ではなく結果確定後に、tool名、call ID、arguments、
result、statusを一回だけ記録するのが適切です。副作用のあるtoolを履歴復元から再実行
してはいけないため、引き続きContextとUIから除外します。

### 11.2 二つのAPI経路は意図的に残る

Realtime未接続時はResponses API、接続中はRealtime APIを使用します。これは未統合の
残骸ではなく、永続接続・音声再生・割り込みを必要とするRealtimeと、単発SSEの
Responses APIの責務を分ける設計です。

新しい機能を追加するときは、共通履歴へ保存する処理は`ConversationService`へ集約し、
LLMへの送信方法は各transport adapterへ置く方針を維持します。

### 11.3 Retry Queueはプロセス再起動を越えない

一時的なSQLite障害には対応しますが、再試行待ちのままサーバーが終了するとqueueは
失われます。必要になった場合は、将来outbox tableなどの永続queueへ移行します。

### 11.4 interrupted transcriptの音声位置は厳密ではない

Realtime APIのtranscript文字列と、実際にスピーカーで再生済みの位置は厳密には一致
しません。保存するinterrupted本文はWindowが受信済みのtranscriptであり、実際に
聞こえた末尾より長い可能性があります。

### 11.5 Conversation一覧・削除は未実装

新しいActive Conversationは作成できますが、過去Conversationの一覧選択、rename、
delete、archiveはこの開発範囲に含めていません。SQLite上の過去履歴は削除されず残ります。

## 12. Notion / RAGとの関係

会話統合は、後続のNotion／RAG実装に対して次の共通基盤を提供しました。

- text／voiceに依存しないConversation ID
- どちらの入力でも利用できる共通15ターンContext
- tool結果を通常会話のuser／assistant pairとして残す経路
- Realtime tool calling後も同じ会話を継続できる仕組み
- RAG取得結果そのものをConversation SQLiteへ混入させない境界

NotionやRAGを利用するために、すべてのLLM呼び出しを一つのConversation Managerへ
集約する必要はありません。検索・tool実行は各transportから呼び出し、ユーザーに見える
質問と回答だけを共通Conversationへ保存する構成で統合を維持できます。

## 13. コミット履歴

| 日付 | Commit | 内容 |
|---|---|---|
| 2026-08-18 | `fba1d92` | 既存動作の固定 |
| 2026-08-18 | `ec43d8e` | Conversation Store |
| 2026-08-19 | `db921ed` | Conversation Manager |
| 2026-08-19 | `b433057` | テキスト会話を共通履歴へ移行 |
| 2026-08-19 | `cfdccb4` | Conversation APIと画面履歴 |
| 2026-08-19 | `a1e307a` | 音声会話を画面表示・履歴保存 |
| 2026-08-20 | `f080a35` | Realtime開始時の履歴復元 |
| 2026-08-25 | `4da1fb6` | Realtime接続中のテキスト入力統合 |
| 2026-08-26 | `9f6fac2` | 保存失敗・再試行 |
| 2026-08-26 | `e62abdf` | 不要ファイル・ログ追跡の整理 |
| 2026-08-26 | `5e5d825` | 発話中の無音判定調整 |
| 2026-08-26 | `0dc9adf` | 60秒idle後の自動待機復帰 |

## 14. 関連資料

- `docs/conversation-store.md`
- `docs/conversation-manager.md`
- `docs/wake-word-v1.5.md`
- OpenAI Realtime API Reference:
  <https://platform.openai.com/docs/api-reference/realtime-client-events>
