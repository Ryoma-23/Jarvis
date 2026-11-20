(function(global) {
    "use strict";
    let enabled = false, stream = null, session = "", capture = null, generation = 0, pending = false;
    let outputPlaying = false;
    const starts = new Map();
    const checkbox = document.getElementById("speaker-shadow");
    const label = document.getElementById("speaker-shadow-status");
    function emit(item, fields, observedSession = session) {
        global.JarvisVoiceDiagnostics?.record("speaker_result", Object.assign({item, session: observedSession}, fields));
    }
    function stop() {
        generation++; starts.clear();
        try { if (capture) capture.close(); } catch (_) { /* observation cleanup must not interrupt conversation */ }
        capture = null;
    }
    async function attach() {
        stop();
        if (!enabled || !stream) return;
        const current = generation;
        let next;
        try {
            next = new global.JarvisSpeakerCapture.Capture();
            capture = next;
            await next.start(stream);
            if (current !== generation) { next.close(); return; }
            label.textContent = "照合を観測中。会話の受付・応答には影響しません。";
        } catch (_) {
            try { next?.close(); } catch (_) { /* preserve normal voice connection */ }
            if (current === generation) {
                capture = null; label.textContent = "照合用の音声取得に失敗しました。会話は継続します。";
                emit("", {value: "capture_failed"});
            }
        }
    }
    async function compare(item, turn) {
        const current = generation, observedSession = session;
        const timing = {capture_start_sample: turn.start, capture_end_sample: capture?.position,
            capture_rate: capture?.rate, capture_start_received_ms: turn.received,
            capture_stop_received_ms: performance.now(), server_audio_start_ms: turn.serverStart,
            server_audio_end_ms: turn.serverEnd};
        if (!capture || pending) { emit(item, {...timing, value: pending ? "skipped_busy" : "capture_unavailable"}); return; }
        let body;
        try { body = capture.wav(turn.start, timing.capture_end_sample); }
        catch (_) { emit(item, {...timing, value: "capture_unavailable", reason: "missing_or_overlong_segment"}); return; }
        pending = true;
        const requested = performance.now();
        try {
            const response = await fetch("/speaker/compare", {method: "POST", headers: {"Content-Type": "audio/wav"}, body,
                signal: AbortSignal.timeout(15000)});
            const result = await response.json();
            if (current !== generation) return;
            if (!response.ok) {
                const reason = ["busy", "not_enrolled", "model_missing", "insufficient_audio"].includes(result.detail) ? result.detail : "processing_failed";
                emit(item, {...timing, value: reason}, observedSession);
                label.textContent = "照合できませんでした：" + reason + "（会話は継続）"; return;
            }
            const names = {owner_candidate: "本人候補", other_candidate: "別話者候補", uncertain: "判定保留", insufficient: "音声材料不足"};
            const fields = {...timing, value: result.decision, score: result.score ?? null,
                reason: result.reason ?? null, clipped_fraction: result.quality?.clipped_fraction ?? null,
                trim_start_s: result.quality?.trim_start_s ?? null, trim_end_s: result.quality?.trim_end_s ?? null,
                compute_ms: result.compute_ms, roundtrip_ms: Math.round(performance.now() - requested),
                profile: result.profile, owner_threshold: result.owner_threshold ?? .60, other_threshold: result.other_threshold ?? .35,
                overlap_output: turn.outputPlaying,
                audio_duration_s: result.quality?.duration_s ?? null, energy_s: result.quality?.energy_s ?? null};
            emit(item, fields, observedSession);
            label.textContent = `${names[result.decision] || "判定保留"}（未調整の仮判定）／類似度 ${result.score ?? "—"}／計算 ${result.compute_ms}ms`;
        } catch (_) {
            if (current === generation) { emit(item, {...timing, value: "request_failed"}, observedSession); label.textContent = "照合通信に失敗しました。会話は継続します。"; }
        } finally { pending = false; }
    }
    function observe(event, id) {
        if (id === session) {
            if (event.type === "output_audio_buffer.started") outputPlaying = true;
            if (["output_audio_buffer.stopped", "output_audio_buffer.cleared"].includes(event.type)) outputPlaying = false;
        }
        if (!enabled || id !== session) return;
        if (event.type === "input_audio_buffer.speech_started") {
            if (capture) starts.set(event.item_id, {start: Math.max(0, capture.position - Math.round(capture.rate * .8)),
                received: performance.now(), serverStart: event.audio_start_ms, outputPlaying});
        }
        if (event.type === "input_audio_buffer.speech_stopped") {
            const start = starts.get(event.item_id); starts.delete(event.item_id);
            if (start === undefined) emit(event.item_id || "", {value: "capture_unavailable"});
            else { start.serverEnd = event.audio_end_ms; void compare(event.item_id, start); }
        }
    }
    checkbox.addEventListener("change", async () => {
        enabled = checkbox.checked;
        if (enabled) {
            try {
                const response = await fetch("/speaker/status"); const state = await response.json();
                if (!response.ok || !state.active || !state.model_available) throw Error();
                if (!enabled) return;
            } catch (_) {
                enabled = false; checkbox.checked = false; label.textContent = "先に本人の声を8本以上登録し、有効にしてください。"; return;
            }
        }
        label.textContent = enabled ? "照合オン。診断を開始してから会話すると結果を保存できます。" : "照合はオフです。";
        void attach();
    });
    global.JarvisSpeakerObserver = Object.freeze({
        connection(id, currentStream) { session = id || ""; stream = currentStream; outputPlaying = false; void attach(); },
        observe(event, id) { try { observe(event, id); } catch (_) { /* cannot affect conversation */ } },
        off() { enabled = false; checkbox.checked = false; stop(); label.textContent = "照合はオフです。"; }
    });
})(window);
