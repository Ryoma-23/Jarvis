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
- After history restoration and microphone enablement, the Window starts a
  client-side 180-second inactivity timer. If no conversation is in progress
  when it expires, it ends the session with reason `idle_timeout` through the
  same `finishRealtimeVoice()` cleanup path.
- The inactivity timer does not run while the user is speaking, a response is
  pending or playing, Realtime text input is queued, or a tool call is running.
  Accepted voice/text activity and completed output restart the 180-second
  interval.
- Cleanup and reconnect invalidate the previous timer generation, preventing
  an old session timer from closing a newer connection.
- Realtime `idle_timeout_ms` is intentionally not configured: that server
  setting prompts an additional model response rather than disconnecting the
  WebRTC session.

The inactivity duration can be adjusted with
`REALTIME_CONVERSATION_IDLE_TIMEOUT_MS` in `static/script.js`.

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
- Speech-stop silence duration: `1200 ms`
- Automatic response creation: disabled; the Window sends `response.create`
  at a normal speech stop or after accepting a finalized barge-in transcript
- Server-side automatic response interruption: disabled

`prefix_padding_ms` is not set, so the Realtime default remains in use.
`silence_duration_ms` is explicitly set to 1200 ms so a short thinking pause
does not immediately end a normal user turn. This adds the same delay before a
completed utterance is considered stopped. `interrupt_response: false`
prevents a single `speech_started` event from immediately cancelling JARVIS
output. While the WebRTC output audio buffer is playing, the client records
whether speech lasts at least 600 ms but does not interrupt from VAD duration
alone. After
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
- `REALTIME_SERVER_VAD_SILENCE_DURATION_MS`
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

Conversation-history SQLite failures do not terminate Realtime. Failed user,
Assistant, or interruption transcript writes are accepted into a process-local
three-attempt retry queue with a stable Message ID. Audio and transcript display
continue, and Realtime cleanup does not wait for the retry worker or browser
status polling. Only an exhausted operation produces a server log and the small
`一部の会話履歴を保存できませんでした` Window toolbar warning.

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
22. Under an injected transient SQLite message-write failure, confirm the text
    or voice answer continues and no warning appears if a retry succeeds.
23. Under an injected permanent SQLite message-write failure, confirm only the
    final retry logs an error and the Window shows the small history warning.
24. Disconnect Realtime while a persistence retry is pending. Confirm browser
    microphone cleanup, Tray notification, and Wake Word resume are not delayed.
25. Connect Realtime and leave it without recognizable conversation for three
    minutes. Confirm it changes to `3分間会話がなかったため終了しました`,
    releases the Realtime microphone, and resumes Wake Word waiting.
26. Speak again before three minutes have elapsed and confirm the timeout restarts
    from that turn rather than closing at the original deadline.
27. Make JARVIS produce a response or tool call that crosses the deadline and
    confirm the session does not close mid-response; it should close only after
    a full idle interval following completion.
28. Disconnect and reconnect shortly before an old idle deadline. Confirm the
    old timer does not close the new Realtime session.

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

## Wake-word greeting

After Realtime history restoration, a wakeword session adds the detected
"Hey Jarvis" as a user input_text message via conversation.item.create and requests
a spoken reply with response.create and tool_choice=none. No response-specific
instructions override the normal session personality, memory, or voice rules;
the model generates the reply using those instructions and conversation history.
Wording is not fixed, although similar replies can naturally recur. Manual starts
do not greet. It shares normal response tracking, audio playback,
interruption, and idle handling. Repeated initialization cannot request it twice;
a failed send is not retried automatically.

Run `node --test tests/js/wake-greeting.test.cjs` for lifecycle regression checks.
Manually check wake-word startup, audible greeting, a follow-up voice request,
manual startup without a greeting, and disconnect/re-wake. Hardware playback and
microphone timing require testing on the actual device.

## Additional wake phrases

The existing openWakeWord detector remains responsible for Hey Jarvis. A local
sherpa-onnx KeywordSpotter also receives the same 16 kHz microphone frames and
detects Jarvis only. The supported wake phrases are Jarvis and Hey Jarvis.
Wake up and Wake up Jarvis are no longer registered keywords. Saying Wake up
Jarvis can still activate on its Jarvis portion; this is keyword spotting, not
whole-utterance matching. No extra microphone or cloud speech recognition is
used. The UI uses Hey Jarvis as the canonical greeting input for
all wake activations; this is not a verbatim transcription of these aliases.

Install requirements and run `python download_wakeword_models.py` once. The
official sherpa-onnx zh-en 3M 2025-12-20 model is stored under data/wakeword/sherpa-kws
(ignored by Git). Startup does not download models. If the extra detector is
unavailable, a warning is printed and existing Hey Jarvis detection remains active.
The English words are encoded with the model's en.phone lexicon. Source:
https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html

WAKEWORD_KEYWORD_THRESHOLD defaults to 0.35; higher values reduce sensitivity.
Short/common phrases may activate during ordinary speech. Test each phrase at the
usual distance, then disconnect and repeat; verify normal conversation and ambient
speech do not cause unwanted activation. The extra stream is reset on resume.

## Jarvis pronunciation profile v3 (stricter detection)

Jarvis alternatives are supplied inline on every new detection stream, including
after resume. They do not depend on regenerating the downloaded keywords.txt.
Each pronunciation has a distinct ID, normalized to Jarvis before activation.
The keyword search uses 16 active paths to accommodate the expanded vocabulary.
Jarvis alternatives now use WAKEWORD_JARVIS_THRESHOLD=0.35 (previously 0.25).
WAKEWORD_KEYWORD_TRAILING_BLANKS=4 adds
end confirmation for all sherpa keywords (previously 1), with some extra latency.
The profile supports additional English and bilingual-model phoneme renderings;
it is not a general Japanese speech recognizer or a guarantee for every accent.

After a full tray restart, logs/jarvis_tray.log must show
`jarvis-pronunciation-v4-name-only loaded`. Detection decisions are recorded as
`[WakeWord] candidate=` JSON events (see diagnostics below).
Validate repeated standalone Jarvis calls at the usual microphone distance,
follow-up conversation, disconnect/resume, and ordinary speech for false triggers.
Recordings used for local evaluation are not committed to the repository.

This adjustment trades some recall for stricter detection after reported video
false activations. In the supplied 17-second recording, detections changed from
five to four. Twelve synthetic ordinary-speech clips had no triggers with either
profile; these do not reproduce the reported video. The actual triggering video
must be checked in the live microphone environment before claiming resolution.
This keyword detector does not distinguish a human voice from speaker playback.

## Name-only wake phrases (v4)

The runtime keyword graph uses Jarvis keywords only: a temporary keyword file
with the existing English dictionary pronunciation, plus seven inline
pronunciation alternatives. The temporary file is removed after model loading. Legacy
`data/wakeword/sherpa-kws/keywords.txt` files are not loaded, so old Wake up
entries cannot re-enable those keywords. Model preparation now writes only
Jarvis to that file. No model download or data-file migration is required.
Unexpected legacy result IDs are also rejected before activation.

Thresholds, end confirmation, Hey Jarvis detection, microphone handoff, and
cooldown behavior are unchanged. Fully exit and restart the Tray to apply this
change; hiding/reopening the Window alone is insufficient.

Manual verification:

1. Restart the Tray and confirm the v4 profile log above.
2. Say Jarvis and Hey Jarvis separately at the usual microphone distance; check
   Window activation, the spoken reply, and a follow-up voice request.
3. Disconnect, wait for wake monitoring to resume, and repeat both phrases.
4. Say Wake up alone repeatedly and confirm it does not activate. A false match
   against a remaining Jarvis model is still possible and needs separate tuning.
5. Replay the previously problematic video and observe false activations.
   Removing keywords does not guarantee that all background-audio triggers stop.

## Wake-word diagnostics

`logs/jarvis_tray.log` records timestamped `[WakeWord] candidate=` JSON events
when either detector produces a candidate. No audio or conversation transcripts
are recorded by this diagnostic path. Frames with no candidate are not logged.

- `decision`: `activate`, `resume_guard` (startup/resume suppression), or
  `cooldown` (repeat suppression). A candidate is not necessarily an activation.
- `detectors`: `openwakeword`, `sherpa_onnx`, or both if both qualify on this frame.
- `keyword`: normalized keyword, not a transcription. Jarvis takes precedence
  in this field when both detectors qualify; both remain listed in `detectors`.
- `openwakeword_model`, `openwakeword_score`, `openwakeword_threshold`: actual
  model output and configured threshold, also recorded when sherpa triggers.
  An openWakeWord score below threshold does not invalidate a sherpa detection.
- `sherpa_keyword_id`, `sherpa_pronunciation`: base `JARVIS` or a specific
  `JARVIS_ALT_0` through `JARVIS_ALT_6` and its configured phonemes.
- `sherpa_threshold`: effective threshold for that keyword (including inline
  pronunciation overrides); `sherpa_trailing_blanks` and `profile` identify the
  remaining detection settings.
- `sherpa_score`: always `null`. The public keyword API used here does not
  provide a confidence score. `sherpa_score_status` is `unavailable` on detection,
  otherwise `not_detected`. The manager's legacy callback value is labeled
  `activation_signal`, not confidence; sherpa still sends the fixed signal 1.0.

Logging errors do not prevent activation. This change does not adjust thresholds
or add a new detection filter. It cannot classify correct versus false triggers
automatically, or explain missed calls that produced no candidate.

After fully restarting the Tray, inspect recent events in PowerShell:

```powershell
Get-Content .\logs\jarvis_tray.log -Tail 200 | Select-String -SimpleMatch '[WakeWord] candidate='
```

For manual evaluation, note the local time and whether each trial was an intended
Jarvis/Hey Jarvis call, silence/background noise, or video playback. Compare that
note with the event's timestamp, detector, and pronunciation ID. Check Window
activation, microphone handoff, audible reply, and disconnect/re-wake as before.
Count `activate` events separately from suppressed candidates. Keep the number
of deliberate calls and the duration of background/video trials to evaluate
misses and false activations later; log counts alone are not accuracy rates.

## Offline WAV evaluation

`scripts/evaluate_wakeword.py` evaluates existing local audio using both installed
detectors and the current thresholds. It does not open a microphone, play audio,
start a Window/Realtime session, call cloud APIs, or download models. Both models
must be available; a missing model fails the evaluation instead of silently
changing the detector set. Existing reports are never overwritten.

Prepare uncompressed **16-bit PCM WAV** files under `data/wakeword-evaluation/`
(already ignored by Git). Record at the normal microphone position and gain:

- Positive: one deliberate Jarvis or Hey Jarvis call per file, with roughly one
  second of quiet lead-in and trailing silence. Use several normal pronunciations
  and distances. Keep the two phrases in separate, clearly named files.
- Negative: no deliberate wake call; include silence, room noise, ordinary speech,
  and the video that caused unwanted activation. Record video playback through
  the usual microphone/speaker setup to include the actual acoustic conditions.
  A direct video audio export can also be tested, but is a different condition.

The evaluator does not record these samples for you. Keep the same WAV files,
channel, and labels when comparing changes. Each input path may be listed only
once. `--positive` and `--negative` can each be repeated. At least one is required.

From the project root in PowerShell, for example:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_wakeword.py --positive data\wakeword-evaluation\jarvis-01.wav --positive data\wakeword-evaluation\hey-jarvis-01.wav --negative data\wakeword-evaluation\video-01.wav --output data\wakeword-evaluation\baseline.json
```

The example filenames must be replaced with files you have prepared. Parent
directories for `--output` must exist. Omit `--output` to print JSON to stdout.
Progress/errors go to stderr. Exit code 0 means evaluation completed, not that
recognition quality passed an acceptance target; invalid inputs or model failures
return nonzero. Reports contain input paths but no audio or speech transcripts.

`--channel 0` is the default (zero-based, matching the live mic channel). Stereo
and multichannel WAVs use only the selected channel, without downmixing. Audio
is streamed in 80 ms blocks and converted with the same resampler as the live
listener. Each clip starts with reset model state; the final partial block is
zero-padded, followed by 1.04 seconds of silence to flush streaming latency.

The JSON includes:

- `summary.positive_clip_detection_rate`: fraction of positive files with at
  least one event; `positive_clips_missed` counts files with no event. This is
  clip-level detection, not word-timed recall: a false match elsewhere in a
  positive clip can count as a hit. Review event timing when interpreting it.
- `summary.negative_events_per_hour`: events in negative clips divided by their
  original duration in hours. Short recordings give unstable estimates. Missing
  positive or negative groups yield `null` for their corresponding rate.
- Per-file events: frame-end detection time (not the spoken word's onset), both
  detector names when applicable, actual openWakeWord score, sherpa pronunciation
  ID/phonemes and threshold. sherpa confidence remains `null` because the API
  does not expose it. `peak_openwakeword_score` includes subthreshold maxima.
- `during_padding`: flags detections after the original file ends. These events
  count in the summary to retain delayed detections; padding time is excluded
  from the negative-duration denominator. Inspect these events before tuning.
- `settings` and `profile`: thresholds, frame size, cooldown, padding, and the
  evaluation conditions needed to compare reports.

This is continuous-listening detector evaluation with a two-second event cooldown.
It does **not** apply the live one-second startup guard or simulate conversation
pauses, microphone handoffs, or resets after each activation. It therefore does
not predict actual Tray activation counts. After tuning, still verify Tray
restart, Window opening, speaker response, follow-up microphone input, and
disconnect/re-wake with the real hardware. This tool alone changes no sensitivity.

## Recording evaluation samples

`scripts/record_wakeword_sample.py` creates one PCM16 WAV per invocation. Unlike
the offline evaluator, this command **opens the microphone and records locally**.
It does not upload audio, start Realtime, play a sound, or change wake sensitivity.
Recording starts only when you run the command, after a visible countdown.

1. Fully exit JARVIS from the Tray to release its microphone. Closing the Window
   alone is insufficient. The recorder does not stop other applications for you.
2. Keep the normal ReSpeaker position, speaker volume, and Windows microphone
   gain. The recorder uses the same device-name/host-API selection as the listener
   (currently ReSpeaker + MME), its native sample rate, six capture channels, and
   configured channel 0. It saves that selected channel as a **mono** WAV; use
   the evaluator's default channel 0 even if the source channel changes later.
3. Run a command below. Wait for `RECORDING`, leave about one second of silence,
   say the phrase once, and leave the remaining time quiet. The countdown itself
   is not recorded. For background/video samples, do not deliberately call JARVIS.

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\record_wakeword_sample.py --output data\wakeword-evaluation\jarvis-01.wav --seconds 5
.\.venv\Scripts\python.exe scripts\record_wakeword_sample.py --output data\wakeword-evaluation\hey-jarvis-01.wav --seconds 5
.\.venv\Scripts\python.exe scripts\record_wakeword_sample.py --output data\wakeword-evaluation\video-01.wav --seconds 60
```

Run each command separately for its intended condition. Repeat the positive
samples with new names (`jarvis-02.wav`, etc.) at your usual distance; ten calls
per phrase is a useful initial comparison set. Prepare longer negative samples
to measure unwanted triggers. `--seconds` defaults to 5 and accepts durations
greater than zero up to 600; `--countdown` defaults to 3 and accepts 0–10 seconds.
Output directories are created automatically. Recordings under `data/` are
ignored by Git. Existing output files are never overwritten, including if another
process creates one during recording.

The recorder streams into a temporary file and saves the requested WAV only
after successful capture. Ctrl+C during capture, input overflow, unexpected frame
shape, and all-digital-zero input do not publish a WAV. The microphone is released
when the stream context exits. If the final output write itself fails or is
interrupted, a partial output can remain; it is not automatically removed.
Choose a new filename when retrying.

On success it prints actual duration, peak amplitude, RMS amplitude, and the
number of samples at the int16 limits. Clipping or very low input gets a warning;
these samples are retained for inspection. Quiet room noise is valid negative
audio; only an entirely digital-zero signal is rejected. These level checks do
not determine whether a wake phrase was spoken correctly.

Pass the saved WAVs to the offline evaluator using the preceding example to
produce `baseline.json`. Inspect or listen to the samples locally to confirm the
intended word/background is present. Then restart the Tray and verify Jarvis/Hey
Jarvis opens the Window, the speaker reply is audible, follow-up microphone input
works, and disconnect/re-wake succeeds. The recorder's automated tests use fake
audio streams and do not certify physical microphone or speaker behavior.

## Comparing candidate detection settings

The offline evaluator accepts per-run tuning options. They do not edit
`core/config.py`, `.env`, model files, or the running Tray's configuration.
Omitting them preserves the current defaults:

| Option | Default | Scope |
| --- | --- | --- |
| `--openwakeword-threshold` | 0.5 | Hey Jarvis score threshold |
| `--sherpa-threshold` | 0.35 | Base English JARVIS pronunciation |
| `--jarvis-threshold` | 0.35 | All seven alternate Jarvis pronunciations |
| `--trailing-blanks` | 4 | sherpa keyword-end confirmation |

Thresholds must be finite numbers in [0, 1]; trailing blanks must be a positive
integer. Base and alternative Jarvis thresholds are independent: changing only
`--sherpa-threshold` does not change the seven inline pronunciation thresholds.
The selected inline threshold is preserved across every stream reset. Reports
store the selected values in `settings` and the effective sherpa threshold in
each event. Runtime defaults and the set of supported wake phrases are unchanged.

First evaluate the prepared positive/negative WAVs with no overrides and save
`baseline.json`. Repeat with the **same files and channel**, saving a new report
for each candidate. For example, isolate a stricter Hey Jarvis setting:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_wakeword.py --positive data\wakeword-evaluation\jarvis-01.wav --positive data\wakeword-evaluation\hey-jarvis-01.wav --negative data\wakeword-evaluation\video-01.wav --openwakeword-threshold 0.6 --output data\wakeword-evaluation\candidate-oww-060.json
```

The example value is a trial, not a recommended production threshold. Compare
missed positive clips, negative events/hour, and each event's detector/timing.
Change one condition at a time, include both call phrases, and collect additional
clips beyond those used to select settings. Increasing a threshold can remove
valid calls as well as false triggers. No production tuning can be concluded
from synthetic silence alone or before collecting actual recordings.

Selecting and applying a production setting remains a separate step after
reviewing the evaluation results and confirming behavior on the real microphone.
