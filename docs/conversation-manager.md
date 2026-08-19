# Conversation Manager

## Scope

Phase 2 adds `ConversationService` above the SQLite `ConversationStore`. It is
the common history boundary for future text and voice integration. The current
chat and Realtime paths do not import or call it yet.

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

## Deferred integration

Later phases still need to:

- replace `chat_service.conversation_history` with `ConversationService`
- persist Realtime transcription and assistant response events
- send restoration events when Realtime connects
- expose common history to the chat UI
- distinguish restoration acknowledgements from newly generated Realtime items
