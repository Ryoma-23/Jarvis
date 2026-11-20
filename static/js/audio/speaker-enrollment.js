(function(global) {
    "use strict";
    const $ = id => document.getElementById(id);
    const prompts = [
        "今日は落ち着いて、いつもの声で話しています。これから私の声を登録します。",
        "朝は窓を開けて空気を入れ替えます。そのあと温かい飲み物を用意します。",
        "明日の予定を確認したいです。午前と午後に分けて、順番に教えてください。",
        "短い物語を聞かせてください。静かな森を歩く旅人のお話がいいです。",
        "仕事がひと段落しました。少し休憩してから、次の作業を始めようと思います。",
        "今日の出来事を振り返っています。うまくいったことも、難しかったこともありました。",
        "いつもより少し小さな声で話しています。このくらいの声でも聞こえていますか。",
        "普段座る位置で、自然に話しかけています。必要なときに短く答えてください。",
        "最近はどんなことがありましたか。私はゆっくり話しながら考えをまとめています。",
        "登録はこれで終わりです。次は別の言葉で、私の声を確認してみたいです。"
    ];
    let lease = null, capture = null, timer = null, pending = false;
    let selected = "", recorded = [], recordingProfile = "", recordingPrompt = 0;
    const messages = {insufficient_audio: "声のある区間が短いか小さすぎます。もう一度、例文を自然に読んでください。",
        clipped_audio: "音が大きすぎて歪んでいます。少し離れて録音してください。",
        more_samples_required: "異なる例文を8本以上登録してください。", prompt_already_recorded: "この例文は登録済みです。別の例文を選んでください。",
        model_missing: "話者モデルがありません。モデル準備スクリプトを実行してください。",
        busy: "照合処理中です。少し待ってから再試行してください。"};
    function show(text) { $("speaker-enroll-status").textContent = text; }
    function controls() {
        $("speaker-record").disabled = pending || !!lease || !selected || recorded.includes(Number($("speaker-prompt").value));
        $("speaker-stop").disabled = pending || !capture;
        $("speaker-cancel").disabled = pending || !lease;
        for (const id of ["speaker-new", "speaker-profiles", "speaker-prompt", "speaker-activate", "speaker-delete", "speaker-refresh"]) $(id).disabled = pending || !!lease;
    }
    async function api(path, method = "GET", body) {
        const response = await fetch("/speaker" + path, {method, body,
            headers: body ? {"Content-Type": "audio/wav"} : {}, signal: AbortSignal.timeout(20000)});
        const data = await response.json();
        if (!response.ok) throw Error(messages[data.detail] || "処理に失敗しました。保存状態を再確認してください。");
        return data;
    }
    async function refresh() {
        const state = await api("/status");
        $("speaker-profiles").replaceChildren();
        for (const p of state.profiles) {
            const option = document.createElement("option"); option.value = p.id;
            option.textContent = `${p.created_at.slice(0, 16)} ／ ${p.samples}本${p.id === state.active ? "（使用中）" : ""}`;
            $("speaker-profiles").append(option);
        }
        if (!state.profiles.some(p => p.id === selected)) selected = state.active || state.profiles.at(-1)?.id || "";
        $("speaker-profiles").value = selected;
        recorded = state.profiles.find(p => p.id === selected)?.prompts || [];
        const consistency = state.profiles.find(p => p.id === selected)?.consistency;
        $("speaker-consistency").textContent = consistency?.pair_count
            ? `登録例文同士の類似度：最小 ${consistency.pair_min}／平均 ${consistency.pair_mean}（${consistency.pair_count}組）。品質の合否判定ではありません。`
            : "登録例文同士の比較は2本以上で表示します。";
        $("speaker-prompt").replaceChildren();
        prompts.forEach((text, index) => {
            const option = document.createElement("option"); option.value = String(index);
            option.textContent = `${index + 1}${recorded.includes(index) ? "（登録済み）" : ""}：${text}`;
            $("speaker-prompt").append(option);
        });
        $("speaker-prompt").value = String(prompts.findIndex((_, index) => !recorded.includes(index)) % 10);
        if (!$("speaker-prompt").value) $("speaker-prompt").value = "0";
        $("speaker-phrase").textContent = prompts[Number($("speaker-prompt").value)];
        show(state.model_available ? `登録 ${recorded.length}/8本以上。登録用録音はPC内だけに保存します。` : "モデル未準備です。"); controls();
    }
    async function release() {
        clearTimeout(timer); timer = null;
        if (capture) { capture.close(); capture = null; }
        if (!lease) return;
        if (lease.stream) lease.stream.getTracks().forEach(track => track.stop());
        await notifyTrayRealtimeFinished("speaker_enrollment_finished", lease.id);
        lease = null;
    }
    async function startRecording() {
        if (pending || lease || !selected) return;
        if (activeRealtimeLifecycle || isRealtimeConnecting || isRealtimeConnected) {
            show("先に音声会話を切断してください。登録録音はOpenAIへ送信しません。"); return;
        }
        global.JarvisSpeakerObserver?.off();
        pending = true; controls();
        lease = {id: crypto.randomUUID(), stream: null};
        recordingProfile = selected; recordingPrompt = Number($("speaker-prompt").value);
        try {
            await notifyTrayRealtime("starting", {source: "manual", session_id: lease.id});
            lease.stream = await navigator.mediaDevices.getUserMedia({audio: REALTIME_MEDIA_AUDIO_CONSTRAINTS});
            await notifyTrayRealtime("started", {source: "manual", session_id: lease.id});
            capture = new global.JarvisSpeakerCapture.Capture();
            await capture.start(lease.stream);
            show("録音中：例文を読んで「停止して保存」を押してください。12秒で自動保存します。");
            timer = setTimeout(() => { void finishRecording(true); }, 12000);
        } catch (_) {
            try { await release(); } catch (_) { /* keep lease so cancel retries release */ }
            show("録音を開始できませんでした。マイクとTrayを確認し、必要なら「中止／マイク解放」を押してください。");
        } finally { pending = false; controls(); }
    }
    async function finishRecording(save) {
        if (pending || !lease) return;
        pending = true; controls();
        let body = null;
        try {
            if (save && capture) body = capture.wav();
            await release();
            if (body) {
                show("録音をPC内に保存し、特徴を計算しています…");
                await api(`/profiles/${recordingProfile}/samples/${recordingPrompt}`, "POST", body);
                await refresh();
            } else show("録音を中止しました。今回の音声は保存していません。");
        } catch (error) {
            try { await release(); } catch (_) { /* release can be retried */ }
            show(error.message === "capture_unavailable" ? "録音が短すぎます。もう一度録音してください。" : error.message);
        } finally { pending = false; controls(); }
    }
    async function action(fn) {
        if (pending || lease) return;
        pending = true; controls();
        try { await fn(); } catch (error) { show(error.message); }
        finally { pending = false; controls(); }
    }
    $("speaker-refresh").addEventListener("click", () => { void action(refresh); });
    $("speaker-new").addEventListener("click", () => { void action(async () => { selected = (await api("/profiles", "POST")).id; await refresh(); }); });
    $("speaker-profiles").addEventListener("change", () => { selected = $("speaker-profiles").value; void action(refresh); });
    $("speaker-prompt").addEventListener("change", () => { $("speaker-phrase").textContent = prompts[Number($("speaker-prompt").value)]; controls(); });
    $("speaker-record").addEventListener("click", () => { void startRecording(); });
    $("speaker-stop").addEventListener("click", () => { void finishRecording(true); });
    $("speaker-cancel").addEventListener("click", () => { void finishRecording(false); });
    $("speaker-activate").addEventListener("click", () => { void action(async () => { if (!selected) return; global.JarvisSpeakerObserver?.off(); await api(`/profiles/${selected}/activate`, "POST"); await refresh(); }); });
    $("speaker-delete").addEventListener("click", () => {
        if (!selected || !confirm("選択した登録の音声と特徴データを削除します。使用中の登録なら照合も無効になります。削除しますか？")) return;
        void action(async () => { global.JarvisSpeakerObserver?.off(); await api(`/profiles/${selected}`, "DELETE"); selected = ""; await refresh(); });
    });
    global.JarvisLocalCapture = Object.freeze({busy: () => !!lease});
    global.addEventListener("beforeunload", () => {
        if (capture) capture.close();
        if (lease) {
            lease.stream?.getTracks().forEach(track => track.stop());
            navigator.sendBeacon(`${TRAY_REALTIME_BRIDGE_URL}/realtime/finished`, new Blob([JSON.stringify({reason: "window_closed", session_id: lease.id})], {type: "text/plain;charset=UTF-8"}));
        }
    });
    void action(refresh);
})(window);
