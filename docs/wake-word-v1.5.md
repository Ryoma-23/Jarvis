# Wake Word v1.5

## Goal

JARVIS waits for a wake word while running in the system tray.

The target flow is:

1. Detect the wake word.
2. Release the wake-word microphone.
3. Show or restore the JARVIS window.
4. Start the Realtime connection automatically.
5. Start voice conversation.
6. End and clean up the Realtime session.
7. Release all Realtime audio resources.
8. Return to wake-word waiting mode automatically.

## Implemented

The following behavior is implemented and working:

- openWakeWord standalone detection
- Wake-word monitoring after tray startup
- Wake-word detection using the ReSpeaker microphone
- Releasing the wake-word microphone after detection
- Showing or restoring the JARVIS window after detection
- Starting the JARVIS window process when it is not running
- Manually resuming wake-word monitoring from the tray
- Clearing queued audio when monitoring resumes
- Resetting the openWakeWord model when monitoring resumes
- Ignoring detections during the resume guard period
- Repeating the wake-word and window-display flow multiple times

This is the completed v1.5.1 behavior.

## State management foundation

The first v1.5.2 implementation phase is complete:

- Wake-word and Realtime lifecycle state is represented by one explicit state:
  `STOPPED`, `WAITING`, `ACTIVATING`, `CONNECTING`, or `CONVERSING`.
- Each activation or conversation has a unique session ID and source.
- Duplicate notifications for the active session are safe.
- Notifications for an older or different session are ignored.
- Activation callback failure or an exception returns the manager to
  wake-word waiting mode.
- A Realtime microphone-release failure returns the manager to waiting mode.
- Manual wake-word resume is blocked while Realtime is connecting or active.
- The state manager can be tested without loading audio or hardware libraries.

This phase provides the state and session-safety foundation used by the tray,
window, and JavaScript Realtime lifecycle notifications.

## Manual Realtime lifecycle bridge

The second v1.5.2 implementation phase is complete:

- The tray starts a local Realtime lifecycle bridge on
  `http://127.0.0.1:8767`.
- The manual Realtime button sends a `starting` notification before requesting
  an ephemeral token or browser microphone access.
- The tray releases the wake-word microphone and moves to `CONNECTING` before
  browser microphone access begins.
- Every browser-side manual connection has a unique session ID.
- The browser sends `started` after the Realtime `session.created` server event.
- Manual disconnect, startup failure, WebRTC failure, and data-channel failure
  clean up browser audio resources before sending `finished`.
- An accepted `finished` notification returns the tray to wake-word waiting.
- Duplicate and stale notifications are rejected without changing the active
  session.
- Browser requests are accepted only from the local JARVIS server origin, or
  from a non-browser local client without an `Origin` header.
- Window unload uses `sendBeacon` for a best-effort `finished` notification.

The manual Realtime connection now depends on the tray bridge being available.
If the bridge cannot accept `starting`, the browser does not request the
microphone or connect to Realtime.

This phase also remains available for manual Realtime starts made while the
manager is in `WAITING`.

## Wake-word Realtime automatic start

The third v1.5.2 implementation phase is complete:

- Wake-word detection shows or starts the JARVIS window and then sends a
  session-aware Realtime start command to the window control server.
- The window control server accepts `POST /realtime/start` on
  `127.0.0.1:8766`; this command accepts only the `wakeword` source.
- The window controller waits up to 10 seconds for the pywebview page `loaded`
  event before evaluating JavaScript.
- JavaScript exposes one synchronous `window.jarvisRealtime.start` command
  boundary and reuses the existing Realtime connection function.
- The wake-word session ID and `wakeword` source are preserved through the
  window command and all tray lifecycle notifications.
- The tray waits up to 5 seconds for `ACTIVATING` to transition after command
  delivery. A timeout, window failure, rejected command, or unavailable tray
  bridge returns the manager to wake-word waiting.
- If only the window-command HTTP response is lost, the tray checks the actual
  session state before recovering, so it does not resume wake-word audio over
  an already-started Realtime connection.
- A delayed automatic-start notification is rejected after its wake-word
  session has expired, preventing a late microphone acquisition.
- Automatic connection failure cleans up browser audio and returns to
  wake-word waiting through the existing `finished` notification.
- Manual Realtime connection behavior remains available.

## Automatic termination, cleanup, and wake-word resume

The fourth v1.5.2 implementation phase is complete:

- Manual disconnect, startup failure, WebRTC failure, data-channel failure,
  and window closure are treated as technical termination events.
- Realtime cleanup closes the data channel and peer connection, stops every
  browser microphone track, and releases the remote audio element before the
  tray receives `finished`.
- An accepted `finished` notification returns the state to `WAITING` and
  resumes wake-word monitoring.
- Window unload still performs synchronous browser cleanup and sends a
  best-effort `sendBeacon` notification.
- After the pywebview window has closed, the window process sends a second,
  session-aware `finished` notification as a fallback.
- The window-process fallback retries transient delivery failures up to three
  times. Duplicate delivery is safe because the tray rejects stale or already
  completed session IDs without changing the current state.
- `response.done` remains a per-response event and does not end the Realtime
  conversation.

## Abnormal recovery and device resilience

The fifth v1.5.2 implementation phase is complete:

- The tray checks the Realtime bridge and managed window process once per
  second.
- If the Realtime bridge thread stops, the tray closes its stale server and
  starts the bridge again.
- A browser `finished` notification is retried up to eight times at 500 ms
  intervals. A duplicate `409` response is treated as completion for this
  terminal notification only.
- If the managed window process exits before its pywebview close callback can
  notify the tray, the tray uses the active session ID to return to wake-word
  waiting.
- If wake-word resume raises an exception, the active state and session ID are
  retained so the same terminal notification can be retried safely.
- Browser cleanup isolates errors for the data channel, peer connection, each
  local microphone track, and the remote audio element. One cleanup failure
  does not prevent the remaining resources from being released.
- If the ReSpeaker is missing or temporarily busy when wake-word monitoring
  opens its stream, the listener remains alive and retries every two seconds.
- A selected audio device with fewer than the configured six input channels is
  rejected with a clear diagnostic instead of failing later in the audio
  callback.

## Realtime background-noise mitigation

Realtime microphone input now uses the browser's built-in WebRTC processing:

- `echoCancellation: true`
- `noiseSuppression: true`
- `autoGainControl: true`

The Realtime `session.update` keeps the existing Japanese
`gpt-4o-mini-transcribe` configuration and uses the current
`session.audio.input` Realtime session fields:

- Input noise reduction: `far_field`
- Turn detection: `server_vad`
- VAD threshold: `0.8`
- Automatic response creation: disabled; the Window sends `response.create`
  at a normal speech stop or after accepting a finalized barge-in transcript
- Server-side automatic response interruption: disabled

`prefix_padding_ms` and `silence_duration_ms` are not set, so the Realtime
defaults remain in use. `interrupt_response: false` prevents a single
`speech_started` event from immediately cancelling JARVIS output. While the
WebRTC output audio buffer is playing, the client records whether speech lasts
at least 600 ms but does not interrupt from VAD duration alone. After
`conversation.item.input_audio_transcription.completed`, it accepts the turn
only when the transcript contains meaningful speech. An accepted barge-in
sends `response.cancel` for a response that is still being generated, followed
by `output_audio_buffer.clear` to stop buffered WebRTC playback, then sends
`response.create` for the new user turn. During JARVIS playback, empty
transcripts, common cough/noise labels, filler fragments, one-character
barge-in fragments, and sub-600 ms detections do not stop JARVIS or create a
follow-up response. Outside JARVIS playback, the Window sends
`response.create` at `speech_stopped`, preserving the existing normal-turn
latency while the finalized transcript is processed separately for history.

The adjustable frontend constants are located together near the top of
`static/script.js`:

- `REALTIME_MEDIA_AUDIO_CONSTRAINTS`
- `REALTIME_INPUT_NOISE_REDUCTION_TYPE`
- `REALTIME_SERVER_VAD_THRESHOLD`
- `REALTIME_BARGE_IN_GUARD_MS`
- `REALTIME_BARGE_IN_MIN_TRANSCRIPT_CHARACTERS`
- `REALTIME_NON_SPEECH_TRANSCRIPTS`
- `REALTIME_BARGE_IN_FILLER_TRANSCRIPTS`

This processing reduces false activation from steady environmental noise and
far-field playback, but it does not identify the speaker. Television, video,
or another person can still activate VAD when their audio is sufficiently loud
and speech-like.

The 600 ms barge-in timer only marks the current input turn as eligible; it no
longer sends a delayed cancellation by itself. It is cleared when user speech
stops, WebRTC playback stops or is cleared, a new guard starts, or Realtime
cleanup runs. Realtime cleanup also clears pending speech-turn records, so an
old event cannot cancel a later session.

Finalized Realtime user transcriptions and Assistant audio transcripts are now
shown in the common chat history and stored with `source=voice`. Assistant
transcript deltas update only the current DOM message. A normal transcript is
written at the transcript-done event; a confirmed 600 ms barge-in writes or
updates the current Assistant message once as `interrupted`. Existing Wake Word
and Realtime microphone lifecycle state remains separate from this history
persistence.

## Realtime shared-history restoration

Every manual or Wake Word Realtime start now carries the active local
`conversation_id` through token creation. Once the DataChannel opens, the
Window fetches the most recent 15 shared user turns and sends their eligible
user and Assistant messages as ordered `conversation.item.create` events.
Completed text and voice messages are included. Interrupted, failed, pending,
hidden tool, system, and tool rows are excluded.

Browser microphone tracks are disabled before they are added to WebRTC and are
enabled only after all restored items first receive `conversation.item.added`
and then reach `conversation.item.done`. Restored item IDs are ignored by the
transcript persistence handlers, so reconnecting does not insert duplicate
SQLite rows. Restoration does not send `response.create`, execute tools, or
replay audio.

While Realtime remains connected, new Window text input is sent directly to the
same Realtime conversation as `input_text`. Once the user item is accepted and
stored, the Window sends `response.create`; the answer is played through WebRTC,
rendered from audio transcript deltas, and stored with `source=text`. When
Realtime is not active, the existing `/chat/stream` path remains unchanged.

Realtime text requests wait during active microphone speech and are serialized
behind another text-origin response. A text request made while JARVIS audio is
playing uses the existing explicit response cancellation and audio-clear path
before it starts; this also clears any buffered tail from a completed response.
Tool calling continues through the existing function-call output and follow-up
response flow.

The adjustable `REALTIME_HISTORY_RESTORE_TIMEOUT_MS` constant is located near
the other Realtime frontend constants in `static/script.js`. A history request,
server rejection, acknowledgement timeout, disconnect, or cleanup failure
terminates the Realtime attempt without enabling microphone input and returns
through the existing Tray cleanup and Wake Word recovery flow.

## Remaining limitations

- Abrupt termination of a window process that was launched independently and
  is not managed by the tray cannot be identified by the process watchdog.
- If the bridge cannot be restarted before all browser retries are exhausted,
  the tray can remain in an active state until the managed window exits or the
  application is restarted.
- Model download or model-loading failure still stops the wake-word listener;
  only microphone stream-open failures are retried automatically.
- A WebRTC `disconnected` state is currently treated as terminal immediately;
  there is no grace period for a transient network handoff.
- Realtime noise reduction and VAD are not speaker verification. They cannot
  guarantee rejection of television audio, video speech, or other people.

## Automated state tests

The state-management tests are located in:

`tests/test_wakeword_manager.py`

They cover:

- idempotent start and stop
- start failure recovery
- one session per wake-word activation
- callback failure and exception recovery
- manual Realtime state transitions
- duplicate and stale session notifications
- microphone-release failure recovery

The Realtime bridge tests are located in:

`tests/test_realtime_bridge.py`

They cover:

- local bridge health and idempotent lifecycle
- manual `starting` → `started` → `finished` state transitions
- wake-word pause before Realtime and resume after cleanup notification
- startup-failure recovery from `CONNECTING` to `WAITING`
- duplicate and stale session rejection
- required session IDs and browser-origin restrictions

The window automatic-start tests are located in:

`tests/test_window_realtime_start.py`

They cover:

- waiting for page readiness before JavaScript evaluation
- safely encoding the source and session ID in the JavaScript command
- rejecting an unready, unavailable, or busy window
- the local `POST /realtime/start` control endpoint
- the tray-to-window session-aware POST request
- reporting window display command success to the tray
- retryable, session-aware window-close fallback notification
- sending the fallback notification only once for the active session

The state tests also verify that an expired wake-word session cannot start
Realtime after the manager has returned to `WAITING`. They also verify that a
wake-word resume exception retains the active session and that a later retry
can complete it.

`tests/test_tray_wakeword_activation.py` verifies that wake-word activation
shows the window, sends the same session ID to the automatic-start command,
and recovers when command delivery or transition confirmation fails. It also
verifies bridge restart, managed-window exit recovery, and retry after a
wake-word resume exception.

`tests/test_window_realtime_start.py` verifies that an exited managed window
process is reaped exactly once while a running process is left unchanged.

## Conversation completion scope

For v1.5.2, conversation completion means a clear technical termination event, such as:

- The user presses the disconnect button.
- The Realtime connection fails or closes.
- Realtime startup fails.
- Microphone permission is denied.
- The JARVIS window is closed.

Natural-language conversation-ending detection can be implemented separately later.

The `response.done` Realtime event must not be treated as conversation completion.

## Behavior that must be preserved

- Tray mode starts normally.
- Wake-word monitoring remains active while idle.
- Wake-word detection releases its microphone before activating JARVIS.
- Wake-word detection shows or starts the application window.
- Manual wake-word resume continues to work.
- Resume-time queue clearing, model reset, and guard behavior remain intact.
- Existing manual Realtime conversation behavior must not be broken.
- Existing text conversation behavior must not be broken.

## Important constraints

- Wake Word and Realtime must not use the microphone at the same time.
- The wake-word microphone must be released before Realtime requests the microphone.
- All Realtime microphone tracks must be stopped before wake-word monitoring resumes.
- Tray, window, and FastAPI run in separate processes.
- Existing tray and window control boundaries should be preserved.
- State changes and notifications must be safe when received more than once.
- Local inter-process communication must use `127.0.0.1`.

## ReSpeaker settings and tuning

The currently confirmed device path is:

- Device name: `ReSpeaker 4 Mic Array (UAC1.0)`
- Host API: `MME`
- Device sample rate observed at runtime: `44100 Hz`
- Configured capture channels: `6`
- Selected microphone channel: `0`
- openWakeWord input: `16000 Hz`, `1280` samples per frame
- Detection threshold: `0.5`
- Resume guard: `1.0` second
- Stream-open retry interval: `2.0` seconds

The user has confirmed the normal wake-word → Realtime → cleanup → wake-word
cycle with threshold `0.5` and resume guard `1.0`, so this phase does not
change either value. Tune only one value at a time:

1. Run at least 20 wake-word attempts from the normal speaking position and
   record detections, misses, and false detections.
2. If there are repeated misses, lower `WAKEWORD_THRESHOLD` by `0.05`. If there
   are false detections, raise it by `0.05`.
3. If JARVIS output or room echo triggers a new detection just after cleanup,
   increase `WAKEWORD_RESUME_GUARD_SECONDS` from `1.0` to `1.5`, then retest.
4. Change `WAKEWORD_MIC_CHANNEL_INDEX` only after comparing actual scores for
   channels `0` through `5`; do not infer the best channel from the USB device
   index.
5. Keep `WAKEWORD_CAPTURE_CHANNELS` at `6` for the confirmed ReSpeaker path.
   The runtime now logs both configured and available channel counts.

## Manual verification checklist

Run JARVIS using `python jarvis_tray.py` and verify the following on the actual
microphone and speaker:

1. Repeat the normal cycle at least 10 times: say “Hey Jarvis”, wait for the
   window and `接続中`, speak one request, hear the response, disconnect, and
   confirm `「Hey Jarvis」を待機中です。` appears again.
2. During a Realtime conversation, close the JARVIS window. Confirm the browser
   microphone indicator disappears and wake-word monitoring resumes once.
3. During a Realtime conversation, terminate only the managed JARVIS window
   process from Task Manager. Confirm the tray logs
   `Jarvis Windowプロセスの終了を検知しました` followed by
   `Window異常終了後にWake Word待機へ戻りました`.
4. Disconnect the network before automatic Realtime startup. Confirm startup
   fails, browser audio resources are released, and wake-word waiting resumes.
5. Deny browser microphone permission. Confirm the same startup-failure
   recovery and no repeated connection attempt.
6. Temporarily disconnect the ReSpeaker while in wake-word waiting. Confirm a
   two-second retry log appears, reconnect it, and confirm waiting resumes
   without restarting the tray.
7. Play JARVIS output near the ReSpeaker immediately after disconnect. Confirm
   the one-second guard prevents an immediate false activation.
8. While Realtime is connecting or active, choose `Wake Word待機を再開` from
   the tray. Confirm the request is rejected and no second microphone capture
   starts.
9. In a quiet room, confirm a normal voice still starts and completes a turn.
10. With television or YouTube speech playing, confirm playback alone is less
    likely to produce `input_audio_buffer.speech_started`.
11. With television playing, speak near the ReSpeaker and confirm JARVIS still
    recognizes the user from the normal operating distance.
12. While JARVIS is speaking, make short and slightly longer cough/throat-clear
    sounds. Confirm they are not displayed as a user turn, do not stop JARVIS,
    and do not create a separate follow-up response.
13. While JARVIS is speaking, say a phrase such as “ちょっと待って” for at
    least 600 ms and confirm the response is interrupted and the new user turn
    is accepted.
14. Repeat JARVIS response → user interruption → next response → interruption
    several times and confirm no delayed cancellation occurs.
15. Complete a text conversation, connect Realtime, and ask a follow-up that
    depends on the text context. Confirm JARVIS answers with that context.
16. Speak to JARVIS, disconnect Realtime, reconnect, and ask a follow-up.
    Confirm the voice context continues and the restored messages are not
    duplicated in the chat history or SQLite.
17. During a Realtime start, confirm the status shows `履歴復元中...` before
    `接続中`, and that speech during restoration is not accepted as input.
18. While Realtime remains connected, complete a text exchange and confirm the
    answer is both displayed and played through the speaker. Then ask a voice
    follow-up that depends on that text and confirm the context is understood.
19. Start with a voice question, enter a text follow-up without disconnecting,
    and confirm the text response uses the voice context and is stored after a
    Window or server restart.
20. While a Realtime text response is running, submit another text request and
    confirm it waits until the current response finishes. Also confirm a text
    request during active microphone speech does not start a competing response.
21. Use a Memo, Task, or Memory request through Realtime text input and confirm
    tool execution and its spoken/displayed follow-up response still complete.

For each run, check that only one Realtime connection is created, the browser
and wake-word microphones are never active together, and no Python window or
audio process remains after tray shutdown.

## Current concerns

- Wake-word monitoring must not start multiple times.
- Realtime connection attempts must not overlap.
- Realtime connections must not remain open after termination.
- Audio resources must be released correctly.
- Wake-word monitoring must resume after Realtime cleanup or failure.
- State transitions must not overlap or become stuck.
- A newly started window must finish page loading within the configured timeout.
- Window closure must not leave wake-word monitoring paused.

## Definition of done

- One wake-word detection starts one Realtime connection.
- Multiple wake-word detections do not create duplicate connections.
- Realtime starts only after the wake-word microphone is released.
- Ending or failing the Realtime session closes the connection and releases audio resources.
- Wake-word waiting resumes automatically after Realtime cleanup.
- Closing the JARVIS window returns the system to wake-word waiting mode.
- Realtime startup failure returns the system to wake-word waiting mode.
- The complete wake-word → Realtime → wake-word cycle can be repeated multiple times.
- Existing tray, window, text conversation, and manual Realtime behavior still works.
- Hardware and audio behavior is verified manually.
