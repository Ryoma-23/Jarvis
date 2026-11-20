(function(global) {
    "use strict";
    let run = null, active = false, saving = false, dirty = false, timer = null;
    let startTime = 0, trial = 0, scenario = "quiet", session = "", stream = null;
    let estimatedBytes = 0;
    const itemTrials = new Map();
    const trialScenarios = new Map();
    const panel = document.getElementById("voice-diagnostics");
    const status = document.getElementById("diagnostic-status");
    const startButton = document.getElementById("diagnostic-start");
    const stopButton = document.getElementById("diagnostic-stop");
    const consent = document.getElementById("diagnostic-transcript");
    const trialButton = document.getElementById("diagnostic-trial");
    const scenarioInput = document.getElementById("diagnostic-scenario");
    function show(message) { status.textContent = message; }
    function controls() {
        startButton.disabled = active || saving || dirty;
        stopButton.disabled = !run || (!active && !dirty);
        consent.disabled = active || saving || dirty;
        trialButton.disabled = !active;
        panel.querySelectorAll("[data-diagnostic-mark]").forEach(b => { b.disabled = !active || trial === 0; });
        global.JarvisDiagnosticTurns?.setActive(active);
    }
    function record(kind, fields = {}) {
        if (!active) return;
        if (kind !== "stop" && (run.events.length >= 9998 || performance.now() - startTime > 23 * 3600000)) {
            stop(); return;
        }
        const entry = Object.assign({ms: Math.round(performance.now() - startTime), kind,
            session, trial, scenario}, fields);
        const key = entry.session + ":" + (fields.item || "");
        if (kind === "speech_start" && fields.item) itemTrials.set(key, {trial, scenario});
        if (fields.item && itemTrials.has(key)) Object.assign(entry, itemTrials.get(key));
        const size = JSON.stringify(entry).length * 3;
        if (kind !== "stop" && estimatedBytes + size > 3_000_000) { stop(); return; }
        estimatedBytes += size;
        run.events.push(entry);
        dirty = true;
        try { global.JarvisDiagnosticTurns?.update(entry); } catch (_) { /* UI cannot affect recording */ }
    }
    async function save() {
        if (!run || saving || !dirty) return;
        saving = true; dirty = false; controls();
        const snapshot = JSON.stringify(run);
        try {
            const response = await fetch("/voice-diagnostics", {method: "POST",
                headers: {"Content-Type": "application/json"}, body: snapshot,
                signal: AbortSignal.timeout(10000)});
            if (!response.ok) throw Error("save failed");
            const result = await response.json();
            if (active) show(`診断中・試行 ${trial}／保存済み ${result.file}`);
            else if (!dirty) {
                const metrics = result.report?.metrics?.stop_to_audio;
                const counts = result.report?.counts || {};
                show(`保存完了：${result.file}（${run.events.length}件）。発話検出 ${counts.speech_start || 0}件、受付 ${counts.accepted || 0}件、拒否 ${counts.rejected || 0}件。応答開始待ち p95：${metrics?.p95_ms ?? "未計測"} ms（対応付けできた発話のみ）。`);
                clearInterval(timer); timer = null;
            }
        } catch (_) {
            dirty = true;
            show("診断の保存に失敗しました。ウィンドウを閉じずに「終了／保存再試行」を押してください。");
        } finally {
            saving = false; controls();
        }
        // If stop occurred during an autosave, write the final snapshot immediately.
        if (!active && dirty && run.complete && snapshot !== JSON.stringify(run)) void save();
    }
    function microphone(currentStream) {
        stream = currentStream;
        if (!active || !stream) return;
        for (const track of stream.getAudioTracks()) {
            const settings = track.getSettings();
            const fields = {device: String(track.label || "不明").slice(0, 256),
                muted: track.muted, enabled: track.enabled};
            for (const [source, destination] of [["sampleRate", "sample_rate"], ["channelCount", "channels"],
                ["echoCancellation", "echo_cancellation"], ["noiseSuppression", "noise_suppression"], ["autoGainControl", "auto_gain"]]) {
                if (["number", "boolean"].includes(typeof settings[source])) fields[destination] = settings[source];
            }
            record("microphone", fields);
        }
    }
    function start() {
        if (active || dirty || saving) return;
        run = {id: crypto.randomUUID(), started_at: new Date().toISOString(),
            include_transcript: consent.checked, complete: false, events: []};
        startTime = performance.now(); trial = 0; active = true; estimatedBytes = 0; itemTrials.clear(); trialScenarios.clear();
        global.JarvisDiagnosticTurns?.reset((observedSession, item, label) => {
            if (!active || !itemTrials.has(observedSession + ":" + item)) return;
            record("speaker_label", {session: observedSession, item, speaker_label: label});
            void save();
        });
        scenario = scenarioInput.value;
        record("start"); microphone(stream);
        show("診断中。「次の試行」を押してから発話してください。");
        timer = setInterval(() => {
            try { microphone(stream); } catch (_) { /* device may have disappeared */ }
            void save();
        }, 5000);
        controls(); void save();
    }
    function stop() {
        if (!run) return;
        if (active) { record("stop"); active = false; run.complete = true; dirty = true; }
        controls(); void save();
    }
    function observe(data, sessionId) {
        session = sessionId || "";
        if (!active) return;
        const kinds = {"input_audio_buffer.speech_started": "speech_start",
            "input_audio_buffer.speech_stopped": "speech_stop",
            "conversation.item.input_audio_transcription.completed": "transcript",
            "conversation.item.input_audio_transcription.failed": "transcription_failed",
            "response.created": "response_created", "output_audio_buffer.started": "audio_start",
            "response.done": "response_done", "error": "error"};
        const kind = kinds[data.type];
        if (!kind) return;
        const fields = {item: String(data.item_id || "").slice(0, 128),
            response: String(data.response_id || data.response?.id || "").slice(0, 128)};
        if (kind === "transcript") {
            fields.chars = String(data.transcript || "").length;
            if (run.include_transcript) fields.transcript = String(data.transcript || "").slice(0, 2000);
        }
        if (kind === "response_done") fields.value = ["completed", "cancelled", "failed", "incomplete"].includes(data.response?.status) ? data.response.status : "unknown";
        if (kind === "error" || kind === "transcription_failed") {
            // Only classifications, never API messages/SDP/authentication data.
            fields.value = "server_error";
            const code = data.error?.code;
            fields.error_code = ["conversation_already_has_active_response", "response_cancel_not_active",
                "rate_limit_exceeded", "insufficient_quota", "invalid_value", "invalid_event",
                "server_error", "audio_unintelligible", "transcription_failed"].includes(code) ? code : "unclassified";
        }
        record(kind, fields);
    }
    // Instrumentation must never throw into the voice lifecycle.
    const safe = fn => (...args) => { try { return fn(...args); } catch (_) { /* observer only */ } };
    global.JarvisVoiceDiagnostics = Object.freeze({
        observe: safe(observe), record: safe(record), microphone: safe(microphone),
        connection: safe((id, currentStream) => { session = id || ""; microphone(currentStream); }),
        request: safe((id, item, origin, state = {}) => { session = id; record("response_request", {item: item || "", value: origin, ...state}); })
    });
    startButton.addEventListener("click", start);
    stopButton.addEventListener("click", stop);
    trialButton.addEventListener("click", () => {
        if (!active || trial >= 1000) return;
        trial += 1; scenario = scenarioInput.value;
        trialScenarios.set(trial, scenario);
        document.getElementById("diagnostic-result-trial").value = String(trial);
        record("trial"); show(`試行 ${trial}：発話してください。終了後に結果を選んでください。`); controls();
    });
    panel.querySelectorAll("[data-diagnostic-mark]").forEach(button => {
        button.addEventListener("click", () => {
            if (!active || !trial) return;
            const target = Number(document.getElementById("diagnostic-result-trial").value);
            if (!trialScenarios.has(target)) { show("開始済みの試行番号を選んでください。"); return; }
            record("mark", {value: button.dataset.diagnosticMark, trial: target, scenario: trialScenarios.get(target)});
            show(`試行 ${target}：${button.textContent}を記録しました。`); void save();
        });
    });
    controls();
})(window);
