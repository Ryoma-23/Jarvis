# Conversation Store

## Scope

Phase 1 adds an independent SQLite persistence layer for future text and voice
conversation unification. It does not replace `chat_service.conversation_history`
and it is not called by the current chat, Realtime, window, or tray paths yet.

The database is created only when `ConversationStore` is instantiated. Its
default location is `data/conversations.sqlite3`, which remains under the
existing ignored `data/` directory.

## Data model

`conversations` stores a stable application-owned conversation ID, optional
title, active flag, and timestamps. A partial unique index guarantees that at
most one conversation is active. This active selection represents the shared
history to continue; it is separate from the Wake Word and Realtime connection
lifecycle state.

`messages` stores ordered user, assistant, system, and tool messages. Each
message records its source (`text`, `voice`, `tool`, or `system`), content,
metadata, timestamps, and one of these processing states:

- `pending`
- `completed`
- `interrupted`
- `failed`

Partial unique indexes on non-null `item_id` and `response_id` make repeated
Realtime event delivery idempotent. If a retry supplies the second external ID,
the existing row is enriched rather than duplicated. Conflicting IDs are
rejected.

## Transaction boundary

Every mutating store method uses `BEGIN IMMEDIATE` and either commits all of
its changes or rolls them back. Callers can also open `transaction()` and pass
the yielded connection to multiple store operations so that creating a
conversation, selecting it, and adding messages can be one atomic unit.

Foreign keys are enabled for every connection. Deleting a conversation at the
database level cascades to its messages, although no deletion API is exposed in
this phase.

## Deferred integration

Phase 2 now provides the Store's common management layer in
`docs/conversation-manager.md`. The following application-path integrations
remain deferred:

- replacing the in-memory text `conversation_history`
- writing Realtime input and output events
- rendering stored voice transcripts in the chat UI
- coordinating queued text input with Realtime speech and response state
