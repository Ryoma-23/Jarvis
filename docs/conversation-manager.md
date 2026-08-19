# Conversation Manager

## Scope

Phase 2 adds `ConversationService` above the SQLite `ConversationStore`. It is
the common history boundary for text and voice integration. Phase 3 connects
the text chat path to it. Phase 4 connects its text history to the Window; the
Realtime path is not connected yet.

The service provides:

- active conversation creation and lookup
- atomic active-conversation creation plus message insertion
- user and assistant message registration with `text` or `voice` source
- assistant `pending`, `completed`, `interrupted`, and `failed` transitions
- LLM context generation from the most recent 15 user turns
- Realtime history restoration event generation
- hidden tool-call metadata storage

## Context rules

A turn starts with one eligible user message. The default context begins at the
fifteenth-most-recent user message and includes the eligible assistant messages
that follow those user messages in stored order.

Only non-empty, completed user and assistant messages are eligible. The service
excludes:

- `pending` messages
- `interrupted` messages
- `failed` messages
- system and tool rows
- any row whose metadata contains `hidden: true`

The result uses the shared LLM format:

```json
{"role": "user", "content": "..."}
```

Text and voice source information remains in SQLite but does not change the LLM
role format.

## Realtime restoration

Realtime restoration uses the same filtered 15-turn context and creates
`conversation.item.create` events. Stored user text or voice transcripts become
`input_text`; stored assistant text or voice transcripts become `output_text`.
Assistant items are marked `completed`.

The service intentionally does not restore audio bytes, send `response.create`,
or replay tool calls. Replaying a tool call could repeat a side effect such as
adding or deleting a note. The future Realtime integration layer is responsible
for sending all restoration events once when a new Realtime session starts.

## Hidden tool metadata

Tool executions are stored as hidden `role=tool`, `source=tool` message rows.
The metadata contains the tool name, call ID, arguments, and result. An optional
Realtime item ID gives retries the Store's existing idempotency protection.

Hidden tool rows remain available through `get_hidden_tool_metadata()` for
audit and future UI or debugging use, but are excluded from normal LLM context
and Realtime restoration.

## Text chat integration

`chat_service.generate_chat_stream()` no longer owns a global in-memory
history. For every text request it now:

1. selects the requested conversation or reuses the persisted active one
2. stores the user message with `source=text`
3. routes Memo, Task, Memory, or normal chat behavior
4. passes the shared 15-turn context to the Responses API for normal chat
5. streams text deltas to the browser
6. stores the complete assistant text only after the stream finishes normally

Normal Responses API input still starts with the existing system prompt,
current time, and long-term memory context. The common user and assistant
history follows those system messages.

Memo, Task, and Memory operations use their existing intent handlers. Their
user request and returned result are stored as a normal visible user/assistant
pair with intent metadata, without making an additional chat-completion call.

If the Responses API reports `response.failed` or `response.incomplete`, the
stream iterator raises, or the browser closes the stream before completion,
the partial assistant text is stored with `status=failed` and excluded from
future context.

`POST /chat/stream` accepts an optional `conversation_id`. Every SSE event
returns the resolved ID, and the browser sends it with later text requests.
When no ID is supplied after an application restart, the Store's persisted
active conversation is reused.

The stream also returns the stored user `message_id` in its first event and the
stored assistant `message_id` when that message reaches a final completed or
failed state. This lets newly rendered messages use the same application-owned
IDs as messages restored from SQLite.

## Conversation API and Window history

Phase 4 adds three local API operations:

- `GET /conversations/active` returns the active conversation, or `null` when
  no conversation has been created yet.
- `GET /conversations/{conversation_id}/messages` returns displayable messages
  in stored order.
- `POST /conversations` creates a new conversation and makes it active.

On page load and when the Window regains focus, it gets the active conversation,
creates one if needed, then retrieves and renders its history. A focus refresh
is skipped while a text stream or another history operation is active. The
**New Conversation** button creates a separate active conversation and clears
the current display without deleting older persisted conversations.

`ConversationService.get_display_messages()` is the UI boundary. In Phase 4 it
returns only non-empty `source=text` user and assistant messages. Voice rows,
system rows, hidden tool rows, metadata, external Realtime IDs, and internal
error details are not exposed. Completed and non-empty failed or interrupted
text are returned with their status so the UI can distinguish them.

The browser renders labels and content using DOM nodes, `textContent`, and text
nodes rather than `innerHTML`. Each stored message root has a
`data-message-id`, and the page keeps a Message ID-to-element map for future
incremental updates.

## Deferred integration

Later phases still need to:

- persist Realtime transcription and assistant response events
- send restoration events when Realtime connects
- render stored voice transcripts in the chat UI
- distinguish restoration acknowledgements from newly generated Realtime items
