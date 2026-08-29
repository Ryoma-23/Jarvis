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

For concurrent Tool activity, the counter continues to determine Thinking
lifetime and the latest `activeTool` value is the visible short label. Clearing
the final Tool starts a 320ms presentation-only fade; it does not delay or alter
the state-machine transition.

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

## Visual Phase C transition profiles

The UI controller continues to select one discrete state using the priority
above. It also clears activity signals and `activeTool` whenever the connection
enters connecting, disconnected, or error, preventing stale Thinking or Tool
visuals after reconnect and recovery.

Core animation does not apply state values directly. `state-transitions.js`
owns immutable target profiles and a mutable current profile. Every rendered
frame exponentially damps the current values toward the target over a bounded
0.4–1.2 second interval. Rotation speed, noise, particle radius, attraction,
Bloom strength, two colors, audio response, particle size, Aura density,
orbital synchronization, axis tilt, inward flow, and outward-wave strength all
share this transition path.

State-specific motion is as follows:

- Idle uses slow rotation, weak inner convection, subtle breathing, low outer
  drift, no audio response, and low Bloom.
- Connecting increases inward attraction and orbital synchronization. Leaving
  Connecting successfully emits one decaying stability wave.
- Listening expands slightly, pulls outer particles inward, increases cyan
  saturation, and enables restrained microphone deformation.
- Thinking strengthens convergence, noise speed, and axis tilt. Active Tool
  state adds a directional inner flow without changing the discrete state.
- Speaking emits outward waves, scales with output audio, raises central Glow,
  and sends a seeded subset of particles outward before their sinusoidal return.
- Error emits one rapidly decaying scatter impulse and red accent while slowing
  rotation. It does not continuously flash, and normal color interpolation is
  restored on recovery.

Reduced-motion mode resolves profiles immediately but disables transient waves,
scatter, breathing, and continuous displacement.

## Cinematic transient ownership

Startup is a presentation lifecycle, not a Jarvis state. It never changes the
controller priority or connection lifecycle and does not emit synthetic Idle,
Connecting, or Tool events. The Shader runtime supplies `uIntroProgress` only
during the initial Window document and removes `data-core-intro` when complete.
Visibility restoration cannot replay it. Reduced Motion bypasses it.

Connection stability, Tool direction, Tool convergence, and Error distortion
remain derived from real state transitions. Each is represented by a decaying
value, so reconnecting or repeated Tool activity updates one active animation
path instead of registering another loop or timer.
