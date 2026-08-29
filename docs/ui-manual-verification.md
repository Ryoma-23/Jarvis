# Jarvis UI manual verification

## Preparation

1. Completely exit Jarvis, including the Tray process.
2. Start Jarvis through the normal Tray startup path.
3. Open the Window and confirm the System Log contains `INTERFACE_READY` and
   `CORE_WEBGL_READY`.
4. Confirm no connection error notification is visible before connecting.

## Layout and visual baseline

1. Confirm System Log is on the left, Jarvis Core is central, and Conversation
   is on the right at the default Window size.
2. Resize below 900 px and confirm System Log hides without covering Core or
   Conversation.
3. Resize below 680 px and confirm Core and Conversation stack vertically and
   all voice/text controls remain reachable.
4. Confirm the Core remains centered and its particles retain circular edges.
5. Disable WebGL or hardware acceleration in a test environment and confirm the
   CSS Core fallback remains visible.

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
   1.75, 1.5, and 1.25 without rebuilding the scene or flashing the fallback.
4. Produce more than 100 System Log events and confirm the visible log remains
   bounded.
5. Perform repeated connect, disconnect, reconnect, and Window-close cycles;
   confirm microphone, speaker, AudioContext, PeerConnection, and Wake Word
   ownership return to their expected states.

## Hardware-dependent acceptance

The following must be verified on the target PC and cannot be established by
automated tests alone: ReSpeaker channel selection, microphone permissions,
speaker playback, Wake Word handoff, Tray lifecycle, pywebview WebGL rendering,
AudioContext behavior, real GPU load, and device sleep/resume behavior.
