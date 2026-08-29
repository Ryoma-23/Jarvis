# Jarvis UI manual verification

## Preparation

1. Completely exit Jarvis, including the Tray process.
2. Start Jarvis through the normal Tray startup path.
3. Open the Window and confirm the System Log contains `INTERFACE_READY` and
   `CORE_WEBGL_READY`.
4. Confirm no connection error notification is visible before connecting.

## Layout and visual baseline

1. Confirm the Jarvis Core and spatial scene fill the Window, with System Log
   quietly overlaid at the left edge and Conversation at the right edge.
2. Resize below 900 px and confirm System Log hides without covering Core or
   Conversation.
3. Resize below 680 px and confirm Conversation becomes a bottom overlay while
   the upper Core and all voice/text controls remain reachable.
4. Confirm the Core remains centered and its particles retain circular edges.
5. Disable WebGL or hardware acceleration in a test environment and confirm the
   CSS Core fallback remains visible.

## Cinematic startup and responsive acceptance

1. Fully close and create a new Jarvis Window. Confirm the background appears,
   the nucleus lights, particles converge into the Core, then JARVIS CORE / IDLE
   and the quiet interface resolve in approximately 1.2–2.0 seconds.
2. Hide and restore the same Window. Confirm the startup sequence does not play
   again. Create a genuinely new Window and confirm it runs once there.
3. Enable Reduced Motion before creating the Window and confirm startup resolves
   immediately with no convergence or interface fade.
4. Verify widths 974px, 900px, 680px, and 480px. At each width inspect Core
   centering, Tool status, error notification, Conversation input, voice controls,
   Footer, and available scroll regions.
5. Repeat at 200% display/browser scaling and high DPI. Confirm controls remain
   reachable and the Bloom/Canvas resolution settles without stretching.

## Text and voice Conversation

1. Send text while Realtime is disconnected. Confirm the user row shows TEXT
   and SENDING, the assistant row shows TEXT and STREAMING, and both processing
   labels disappear after completion.
2. Connect Realtime and speak a normal turn. Confirm the finalized user and
   assistant transcripts appear in the same Conversation panel with VOICE.
3. Send text during Realtime. Confirm it uses the same panel and remains marked
   TEXT even though the response is spoken.
4. Interrupt Jarvis while it is speaking. Confirm the interrupted assistant
   row shows INTERRUPTED and the accepted user voice turn follows it.
5. Restart Jarvis and confirm completed, failed, and interrupted displayable
   history restores with the same source/status labels.
6. Exercise a conversation longer than 200 visible rows. Confirm the oldest
   DOM rows leave the display while restarting/reloading restores persisted
   history according to the same latest-200 presentation limit.

## State, Tool, error, and log integration

1. Connect and confirm Header, Status Bar, microphone label, Core caption, and
   System Log all reflect the connection transition.
2. Trigger an available Tool. Confirm the Core shows ACTIVE TOOL and its name,
   the Core enters THINKING, and System Log records TOOL_START.
3. Confirm the badge clears and TOOL_END is logged when the Tool completes,
   including a Tool followed by another model response.
4. Cause a safe connection failure, such as denying microphone permission.
   Confirm the error notification is announced and visible, Header/Status Bar
   show error, Core uses its error state, and System Log records VOICE_ERROR.
5. Recover or reconnect and confirm the error notification disappears.
6. Use the Log clear icon and confirm only visible browser log entries clear;
   conversation history, files, Python logs, and later events remain intact.

## Core and Audio Reactive

1. In IDLE, confirm slow motion is smooth and restrained.
2. Speak at low and high volume during LISTENING. Confirm Core displacement and
   scale respond proportionally and return smoothly toward baseline.
3. Listen to quiet and loud Jarvis output during SPEAKING. Confirm the Core
   follows output audio rather than microphone input.
4. Confirm THINKING motion remains active without requiring audio.
5. Disconnect and reconnect repeatedly. Confirm visualization resumes and no
   duplicate audio reaction or stale Tool badge remains.

## Surface Resonance

1. Speak while Jarvis is LISTENING and confirm a localized portion of the
   existing outer particles draws inward and becomes more saturated. No ring,
   arc, or new outline should appear.
2. Trigger a spoken response and confirm energy travels from the inner particle
   volume toward the outer surface. Microphone noise must not drive this motion.
3. Let both input and output fall silent and confirm residual fine vibration
   settles. Disconnect Realtime and confirm resonance stops immediately.
4. Confirm IDLE and THINKING retain the Phase C appearance without any audio
   overlay. With reduced motion enabled, confirm resonance deformation is off.

## Spatial background

1. Confirm sparse, dim particles appear behind rather than on top of the Core,
   and remain much darker than Core particles in every state.
2. Confirm the lower spatial grid converges toward the Core and fades near the
   Core itself instead of appearing as a flat full-screen checkerboard.
3. Resize across 680px and confirm the background becomes quieter without a
   flash, stretched grid, or broken projection.
4. Confirm System Log and Conversation text retain their prior contrast and do
   not receive grid, noise, or Bloom overlays.
5. Enable reduced motion and confirm background particles, parallax, and
   atmospheric drift stop while the static depth composition remains visible.
6. Confirm the background reads as a dim blue-black cosmic volume: sparse stars
   should occupy different depths and extremely faint blue/violet/teal haze may
   be visible, but no cloud, star, or grid line should compete with Core text.
7. Confirm the same star and haze field continues across the complete Window,
   including behind Header, Footer, System Log, Conversation, and the outer
   corners; it must not appear confined to a rectangle around the Core.

## Panels and controls

1. Confirm the Core remains visually dominant and both side regions read as
   timeline/instrument surfaces rather than isolated dashboard cards.
2. Generate INFO, TOOL, and ERROR log entries. Confirm fixed columns, distinct
   type colors, a brief new-row highlight, gradual aging, and unchanged Clear.
3. Confirm YOU/JARVIS alignment, small TEXT/VOICE labels, restrained streaming
   cursor, readable long-message line length, and subdued failed/interrupted rows.
4. Operate Connect, Disconnect, and Reconnect with mouse and keyboard. Confirm
   hover, focus, pressed, disabled state, tooltip, and screen-reader names.
5. Trigger sequential and overlapping Tools. Confirm the latest short name is
   displayed, progress remains subtle, Thinking persists through overlap, and
   the final Tool fades without leaving stale UI.
6. At 200% browser/display scaling, confirm voice controls, new conversation,
   message input, and Send remain visible and keyboard reachable.

## Accessibility

1. Navigate every button and text input using only Tab and Shift+Tab; confirm a
   visible focus indicator and logical order.
2. With a screen reader, confirm connection changes, error alerts, Tool status,
   Core state, Conversation additions, and busy state are announced without
   reading decorative Canvas content.
3. Enable reduced motion and confirm decorative CSS/WebGL animation stops while
   state text and controls continue to update.
4. Enable increased contrast and confirm panels, controls, Tool badge, and
   error alert retain clear borders and readable text.
5. Test 200% text scaling and confirm controls remain usable without horizontal
   page clipping at the supported responsive breakpoints.

## Long-running operation

1. Leave Jarvis idle for at least one hour and compare CPU/GPU usage before and
   after; IDLE should remain capped at 20 FPS.
2. Hide/minimize the Window and confirm Core rendering pauses, then resumes when
   shown.
3. Generate sustained active animation and confirm quality can step between DPR
   2.5, 2.0, and 1.5 without rebuilding the scene or flashing the fallback.
4. Produce more than 100 System Log events and confirm the visible log remains
   bounded.
5. Perform repeated connect, disconnect, reconnect, and Window-close cycles;
   confirm microphone, speaker, AudioContext, PeerConnection, and Wake Word
   ownership return to their expected states.
6. During the same cycle, confirm startup does not replay, connection waves and
   Tool animations do not multiply, ResizeObserver is released on close, and
   Canvas/Composer GPU memory does not grow monotonically.

## Hardware-dependent acceptance

The following must be verified on the target PC and cannot be established by
automated tests alone: ReSpeaker channel selection, microphone permissions,
speaker playback, Wake Word handoff, Tray lifecycle, pywebview WebGL rendering,
AudioContext behavior, real GPU load, and device sleep/resume behavior.
