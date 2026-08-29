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

## Phase 5 Three.js Core

Phase 5 adds a local Three.js renderer while preserving the Phase 2 CSS Core as
the fallback. The initial WebGL scene contains only a 1,000-point Particle
Sphere and two lightweight Inner Core meshes. Connection lines, post
processing, Bloom, and audio analysis remain intentionally out of scope.

The renderer uses a 30 FPS cap, a 1.5 device-pixel-ratio cap, the low-power GPU
preference, ResizeObserver sizing, reduced-motion support, and full pause while
the document is hidden. Geometry, materials, and the renderer are disposed on
page unload or WebGL context loss. The Canvas becomes visible only after
successful initialization; otherwise the CSS Core remains visible.

Three.js 0.128.0 is vendored under `static/vendor/three/` so Jarvis does not
depend on a CDN at runtime. Its MIT license is stored beside the runtime file.
Jarvis loads the classic browser build before `jarvis-core.js`, avoiding an ES
Module compatibility dependency in the embedded pywebview runtime.

## Phase 6 Core animation

Phase 6 adds motion without changing Realtime or audio ownership. The outer
Particle Sphere receives a small deterministic radial wave. Connection lines
are intentionally omitted so long chords cannot obscure the particle form.

The former solid Inner Core meshes are replaced by three nested particle
layers containing 260, 170, and 90 points. Each layer has a separate radius,
opacity, particle size, rotation direction, and phase. Radial waves, subtle
axis drift, and independent rotations create fluid movement without shaders or
post-processing.

The three inner radii are reduced to 90% of their initial Phase 6 values. All
point layers share one locally generated 64-pixel radial texture, producing
round antialiased particles without a network asset or per-layer texture cost.
The innermost layer uses larger, brighter source particles for a stronger
central glow while retaining additive blending and the active state color.

A second refinement scales all three inner radii to 90% again, raises the
shared radial texture from 64 to 96 pixels, and increases the renderer DPR cap
from 1.5 to 1.75. Particle size and intensity increase slightly to compensate
for the sharper edges. White mixing is reduced across all layers so stronger
additive light preserves the active Jarvis state color instead of washing out.

The visible drifting outline belongs to the outer 1,000-point Particle Sphere,
not the three nested inner layers. Its radius and jitter envelope are scaled to
81% of the original Phase 5 values (`1.1178` and `0.0972` respectively),
representing the two requested consecutive 90% scale adjustments. The inner
layers were already at the same cumulative scale and are not reduced again.

The nested particle layers remain active and collectively form the compact
center cluster; their overlap means they are not intended to read as three
hard circular outlines. The innermost 90-point layer uses `0.88` source opacity
to keep its glow slightly below saturation while preserving its motion and
state color.

## Phase 7 performance control

Phase 7 completes the renderer controls for a resident desktop assistant.
Idle, connecting, and error states render at a maximum of 20 FPS; listening,
thinking, and speaking render at a maximum of 30 FPS. Hidden documents remain
fully paused and reduced-motion mode remains static.

The renderer samples 90 rendered-frame intervals and treats intervals above
150% of the current frame budget as slow. If more than 20% are slow, the DPR
cap steps down through `1.75`, `1.5`, and `1.25`. Four stable sample windows
with fewer than 3% slow frames permit one recovery step. Quality changes have
a 15-second cooldown to avoid oscillation. Particle counts and textures remain
fixed, so adaptive quality does not rebuild scene geometry or allocate arrays.
The frame limiter carries timing remainder forward, preventing 60 Hz rounding
from turning a nominal 30 FPS cadence into false slow-frame samples.

## Phase 8 Audio reactive Core

`static/js/audio/audio-reactive.js` owns display-only Web Audio analysis. It
creates separate AnalyserNodes for the existing Realtime microphone stream and
WebRTC remote output stream. Sources connect only to their analyser and never
to an AudioContext destination, so WebRTC remains responsible for capture and
playback. Realtime cleanup disconnects both analyser branches and closes their
shared AudioContext before the original tracks and audio element are released.

Each analyser uses a 256-sample time-domain buffer, one reusable Uint8Array,
RMS normalization with a small noise floor, and asymmetric smoothing. The Core
reads microphone amplitude only while the visual state is `listening`, and
remote amplitude only while it is `speaking`. The selected level adds bounded
particle displacement, scale, and colored intensity. Unsupported or suspended
Web Audio produces level zero and leaves the Phase 6 state animation intact.

## Phase 9 Chat integration

Text chat, voice user transcripts, assistant audio transcripts, and text turns
sent through an active Realtime session already share the persisted
Conversation history. Phase 9 consolidates their browser rendering in
`static/js/ui/conversation-view.js`. The module owns message DOM creation,
safe incremental text updates, Message ID registration, and visual status.
`static/script.js` retains API, persistence, Realtime, interruption, and queue
ownership and calls this display-only boundary.

Every message now renders a real `TEXT` or `VOICE` metadata element rather than
a CSS pseudo-element. Pending user and assistant output displays `SENDING` and
`STREAMING` respectively; interrupted and failed records display `INTERRUPTED`
and `FAILED`. Restored history and live messages use the same renderer and
`textContent`/Text Node safety boundary.

Each visual Jarvis state selects a target profile for rotation speed, particle
movement, pulse depth, inner particle motion, and intensity. Values ease
toward the profile to prevent abrupt visual changes. The existing 30 FPS and
device-pixel-ratio caps, hidden-document pause, reduced-motion handling, CSS
fallback, and disposal flow remain in effect. Post-processing Bloom and Web
Audio analysis remain outside Phase 6.

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
