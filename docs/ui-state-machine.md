# Jarvis UI state machine

## Purpose

The UI state machine translates existing browser-side Realtime events into one
visual Jarvis state. It is display-only. It does not own or change the
PeerConnection, microphone tracks, DataChannel, conversation history, tool
execution, Tray lifecycle, or Wake Word state.

## States

- `idle`: no active UI signal
- `connecting`: Realtime is starting or shutting down
- `listening`: user speech is active
- `thinking`: a response or tool operation is being processed
- `speaking`: Realtime output audio is playing
- `error`: the Realtime connection is in an error state

## Priority

When signals overlap, the state is selected in this order:

1. `error`
2. `listening`
3. `speaking`
4. `thinking`
5. `connecting`
6. `idle`

Listening intentionally has priority over speaking so a barge-in attempt gives
immediate visual feedback even while buffered assistant audio is still playing.

## Event mapping

| Existing event | UI controller signal |
| --- | --- |
| connection status update | automatic subscription |
| `input_audio_buffer.speech_started` | `speechStarted()` |
| `input_audio_buffer.speech_stopped` | `speechStopped()` |
| input transcription failure | `speechFailed()` |
| `response.created` | `responseCreated()` |
| `response.done` | `responseDone()` with completed Tool-call status |
| `output_audio_buffer.started` | `audioStarted()` |
| output buffer stopped or cleared | `audioStopped()` |
| tool execution begins | `toolStarted()` |
| tool execution finishes | `toolFinished()` with follow-up response status |
| Realtime cleanup | `reset()` |

Tool depth is counted so overlapping tool work cannot return the display to
idle prematurely. A completed tool keeps the visual state at thinking while
the existing follow-up response is requested. A failed Tool call returns to
idle instead of leaving the UI in a stale thinking state.

## Phase 11 integrated outputs

All consumers observe `JarvisUI.state`; none of them control the Realtime
lifecycle.

| State field | UI outputs |
| --- | --- |
| `jarvisState` | Core color, motion profile, caption, System Log transition |
| `connectionStatus` | Header, Status Bar, microphone label, error alert, Core state |
| `statusMessage` | Voice status, Status Bar accessible label, error alert, System Log |
| `activeTool` | Core Tool badge and System Log start/end records |
| `latencyMs` | Status Bar latency value when available |

The connection error alert uses `role=alert` only while an error is active and
is hidden automatically after recovery. Tool display is cleared by the
existing controller reset path during disconnect, reconnect failure, or normal
cleanup. Conversation pending state is separate from Jarvis state and is
represented by `aria-busy` on the shared transcript container.
