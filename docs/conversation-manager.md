# Conversation Manager

## Scope

Phase 2 adds `ConversationService` above the SQLite `ConversationStore`. It is
the common history boundary for text and voice integration. Phase 3 connects
the text chat path to it. Phase 4 connects its history to the Window, and Phase
5 persists finalized Realtime speech transcripts and renders them in the same
message list. Phase 6 restores the shared history into every new Realtime
session.

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
adding or deleting a note.

`GET /realtime/token` accepts the local `conversation_id` and returns it with
the ephemeral token. After the WebRTC DataChannel opens, the Window requests
`GET /realtime/conversation/history` and sends the returned events in stored
order. The API always uses `DEFAULT_CONTEXT_TURN_LIMIT`, currently 15 user
turns.

Microphone tracks are attached in a disabled state so SDP audio negotiation can
complete without sending user audio. Each restoration event has a local
`event_id`. The Window records the server item ID at `conversation.item.added`,
then waits for the corresponding `conversation.item.done` event before counting
that item as restored. Microphone tracks are enabled only after every restored
item is done. Restored server item IDs are tracked and excluded from transcript
persistence, and restoration never sends `response.create`.

If a text exchange completes while the same Realtime session is already open,
the finalized user and Assistant text messages are appended to that session as
an ordered pair of `conversation.item.create` events. The microphone is disabled
while those two items are synchronized and is re-enabled only after both
`conversation.item.done` events. This keeps a following voice turn aware of text
that was added after the initial connection without asking the Realtime model to
generate a duplicate response.

History HTTP requests and acknowledgement waits both have a five-second
timeout. An HTTP error, invalid response, rejected client event, timeout,
DataChannel closure, or manual disconnect leaves the microphone disabled and
uses the existing Realtime cleanup path. Cleanup cancels the pending restore,
stops microphone tracks, closes WebRTC, and notifies the Tray so Wake Word can
resume.

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

`ConversationService.get_display_messages()` is the UI boundary. It returns
non-empty `source=text` and `source=voice` user and assistant messages. System
rows, hidden tool rows, metadata, external Realtime IDs, and internal error
details are not exposed. Completed and non-empty failed or interrupted messages
are returned with their status so the UI can distinguish them.

The browser renders labels and content using DOM nodes, `textContent`, and text
nodes rather than `innerHTML`. Each stored message root has a
`data-message-id`, and the page keeps a Message ID-to-element map for future
incremental updates.

## Realtime transcript integration

Phase 5 handles these server events from the Realtime WebRTC data channel:

- `conversation.item.input_audio_transcription.completed` renders and stores a
  finalized user transcript with `source=voice` and its `item_id`.
- `response.output_audio_transcript.delta` appends safe text nodes to one
  pending Assistant DOM message. It does not write a database row.
- `response.output_audio_transcript.done` replaces the pending DOM content with
  the final transcript and stores it once with `source=voice`, `item_id`, and
  `response_id`.

The Realtime `session.update` configures transcription under
`session.audio.input.transcription`. The local Window posts accepted finalized
records to
`POST /realtime/conversation/messages`. Store uniqueness for non-null
`item_id` and `response_id` makes repeated Realtime completion events
idempotent.

VAD automatic response creation and interruption are disabled. For a normal
voice turn, the Window sends `response.create` at `speech_stopped` to preserve
the existing response latency, then independently renders and stores the
finalized transcript. During JARVIS playback, it waits for the finalized
transcript, which must contain meaningful speech and belong to a turn lasting
at least 600 ms. Only then does the Window send `response.cancel`, clear WebRTC
output audio, and create the next response. Empty transcripts and common
cough/noise markers are ignored and are not stored or displayed.

When a confirmed barge-in clears the output, the Window posts the buffered
Assistant transcript once to
`POST /realtime/conversation/assistant/interrupted`. The service creates or
updates that voice Assistant row as `interrupted`. If the transcript-done event
arrives later, it can fill an initially empty interrupted row but cannot change
its status back to `completed`. Interrupted rows remain excluded from LLM
context.

The Realtime API cannot precisely align generated transcript text with the
exact audio playback cutoff, so the stored interrupted text is the transcript
buffered by the Window at the terminal interruption.
