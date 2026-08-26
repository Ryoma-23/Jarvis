# Jarvis UI architecture

## Compatibility boundaries

The UI remains a FastAPI-served HTML, CSS, and JavaScript application hosted
inside pywebview. The Window process starts Realtime through the synchronous
`window.jarvisRealtime.start(source, sessionId)` boundary. UI refactoring must
preserve that public API and the existing Realtime cleanup order.

The following DOM IDs are required by the current application:

- `new-conversation-button`
- `conversation-status`
- `chat-area`
- `message-input`
- `voice-connect-button`
- `voice-disconnect-button`
- `voice-reconnect-button`
- `voice-status`
- `send-button`

## Phase 1 foundation

The first UI foundation uses ordered classic scripts so the current pywebview
loading and JavaScript command boundary remain unchanged:

1. `static/js/app-state.js` owns display-only shared state and subscriptions.
2. `static/js/dom.js` centralizes required and optional DOM references.
3. `static/js/ui/jarvis-state.js` validates and renders the visual Jarvis state.
4. `static/js/ui/system-log.js` safely renders a bounded local event log.
5. `static/js/ui/status-bar.js` renders connection status when the status bar
   is introduced.
6. `static/script.js` retains conversation and Realtime behavior.

The future Core, System Log, and Status Bar elements are optional during Phase
1. Their renderers are no-ops until Phase 2 adds those elements. Required
legacy controls fail fast at page load if their DOM contract is broken.

## Phase 2 layout

Phase 2 introduces the production layout without adding Three.js or changing
the Realtime lifecycle:

- The header contains the Jarvis identity and local-system indicator.
- The left panel displays a bounded browser-side System Log.
- The center gives visual priority to a lightweight CSS Core placeholder and
  keeps the existing voice controls immediately below it.
- The right panel contains the shared text and voice transcript, conversation
  controls, and text composer.
- The footer displays compact Realtime, microphone, and memory status.

The System Log header includes a small symbol-only clear control. It removes
only currently rendered browser log entries and does not delete Python logs,
persistent data, conversation history, or future events.

The default 974-pixel Window width supports the complete three-region layout.
At 900 pixels and below, the secondary System Log is hidden. At 680 pixels and
below, Core and Conversation become a vertical layout. Required controls stay
in the document at every breakpoint, and reduced-motion preferences disable
the decorative Core animation.

## Phase 3 visual system

Phase 3 establishes consistent visual and accessibility rules without changing
Realtime ownership:

- Header, Status Bar, and microphone labels render from the same display-only
  connection state.
- Core color tokens support idle, listening, thinking, speaking, and error
  states before those states are connected to Realtime events.
- Empty conversation history has an unobtrusive explanation.
- Voice-origin messages receive a small source label without changing stored
  message data or the existing render flow.
- Keyboard focus, text selection, reduced motion, increased contrast, long
  message wrapping, and both standard and WebKit scrollbars are styled.
- A solid-surface fallback is provided when backdrop blur is unavailable.

The interface remains local to pywebview. No hosting, external font, image,
icon package, or new runtime dependency is introduced.

## Phase 4 display state machine

`static/js/ui/ui-state-controller.js` converts existing Realtime event signals
into a single visual state. Its priority rules and event mapping are documented
in `docs/ui-state-machine.md`. The controller owns display signals only; the
existing lifecycle flags in `static/script.js` remain authoritative for audio,
conversation, Tool, Tray, and cleanup behavior.

## State ownership

`JarvisUI.state` is display-only. It must not control the Realtime lifecycle,
microphone tracks, peer connection, Tray notifications, conversation storage,
or tool execution. Existing lifecycle variables in `static/script.js` remain
the source of truth until a later state-machine phase deliberately changes the
architecture.

The initial state contains:

- `jarvisState`
- `connectionStatus`
- `statusMessage`
- `activeTool`
- `latencyMs`

Consumers subscribe through `JarvisUI.state.subscribe()` and receive immutable
snapshots. Listener failure is isolated so one visual component cannot prevent
the remaining UI from updating.
