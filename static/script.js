let peerConnection = null;
let dataChannel = null;
let localStream = null;
let remoteAudioElement = null;

let isRealtimeConnected = false;
let isRealtimeConnecting = false;
let activeRealtimeLifecycle = null;

const TRAY_REALTIME_BRIDGE_URL = "http://127.0.0.1:8767";
const REALTIME_FINISHED_NOTIFY_RETRY_COUNT = 8;
const REALTIME_FINISHED_NOTIFY_RETRY_DELAY_MS = 500;

const sendButton = document.getElementById("send-button");
const messageInput = document.getElementById("message-input");
const chatArea = document.getElementById("chat-area");
const voiceConnectButton = document.getElementById("voice-connect-button");
const voiceDisconnectButton = document.getElementById("voice-disconnect-button");
const voiceReconnectButton = document.getElementById("voice-reconnect-button");
const voiceStatus = document.getElementById("voice-status");

voiceConnectButton.addEventListener("click", function() {
    void startRealtimeVoice("manual");
});
voiceDisconnectButton.addEventListener("click", function() {
    void stopRealtimeVoice();
});
voiceReconnectButton.addEventListener("click", function() {
    void reconnectRealtimeVoice();
});

sendButton.addEventListener("click", sendMessage);

updateVoiceStatus("disconnected", "未接続");
updateVoiceButtons("disconnected");

window.jarvisRealtime = Object.freeze({
    start: requestRealtimeVoiceStart
});

messageInput.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
});


async function sendMessage() {

    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    addMessage("user", message);

    messageInput.value = "";

    const aiMessageDiv = addMessage("ai", "");

    try {

        const response = await fetch("/chat/stream", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message
            })
        });

        const reader = response.body.getReader();

        const decoder = new TextDecoder("utf-8");

        let buffer = "";

        while (true) {

            const { done, value } = await reader.read();

            if (done) {
                break;
            }

            buffer += decoder.decode(value, {
                stream: true
            });

            const events = buffer.split("\n\n");

            buffer = events.pop();

            for (const event of events) {

                if (!event.startsWith("data: ")) {
                    continue;
                }

                const jsonText = event.replace("data: ", "");

                const data = JSON.parse(jsonText);

                if (data.text) {
                    aiMessageDiv.innerHTML += data.text;
                }

                if (data.error) {
                    aiMessageDiv.innerHTML +=
                        "\nエラーが発生しました: " + data.error;
                }

                chatArea.scrollTop =
                    chatArea.scrollHeight;
            }
        }

    } catch (error) {

        aiMessageDiv.innerHTML +=
            "\n通信エラーが発生しました";
    }
}


function requestRealtimeVoiceStart(source, sessionId) {
    const normalizedSource = String(source || "").trim();
    const normalizedSessionId = String(sessionId || "").trim();

    if (!normalizedSource || !normalizedSessionId) {
        return false;
    }

    if (activeRealtimeLifecycle) {
        return (
            activeRealtimeLifecycle.source === normalizedSource &&
            activeRealtimeLifecycle.sessionId === normalizedSessionId
        );
    }

    if (isRealtimeConnected || isRealtimeConnecting) {
        return false;
    }

    void startRealtimeVoice(
        normalizedSource,
        normalizedSessionId
    );
    return true;
}


async function startRealtimeVoice(
    source = "manual",
    requestedSessionId = null
) {
    if (
        isRealtimeConnected ||
        isRealtimeConnecting ||
        activeRealtimeLifecycle
    ) {
        console.log("Realtime voice is already connected or connecting.");
        return false;
    }

    const sessionId = requestedSessionId || createRealtimeSessionId();
    const lifecycle = {
        sessionId: sessionId,
        source: source,
        trayAccepted: false,
        startedNotified: false,
        finishing: false,
        finishPromise: null
    };

    activeRealtimeLifecycle = lifecycle;

    try {
        isRealtimeConnecting = true;

        updateVoiceStatus("connecting", "接続中...");
        updateVoiceButtons("connecting");

        await notifyTrayRealtime("starting", {
            source: source,
            session_id: sessionId
        });

        lifecycle.trayAccepted = true;

        const tokenResponse = await fetch("/realtime/token");

        if (!tokenResponse.ok) {
            throw new Error(`Realtime token取得失敗: ${tokenResponse.status}`);
        }

        const tokenData = await tokenResponse.json();

        const ephemeralKey = tokenData.value;

        if (!ephemeralKey) {
            throw new Error("Realtime用の一時トークンが取得できませんでした。");
        }

        const currentPeerConnection = new RTCPeerConnection();
        peerConnection = currentPeerConnection;

        remoteAudioElement = document.createElement("audio");
        remoteAudioElement.autoplay = true;

        currentPeerConnection.ontrack = function(event) {
            remoteAudioElement.srcObject = event.streams[0];
        };

        currentPeerConnection.onconnectionstatechange = function() {
            if (
                peerConnection !== currentPeerConnection ||
                !isCurrentRealtimeSession(sessionId)
            ) {
                return;
            }

            const state = currentPeerConnection.connectionState;

            console.log("PeerConnection state:", state);

            if (state === "connected") {
                isRealtimeConnected = true;
                isRealtimeConnecting = false;

                updateVoiceStatus("connected", "接続中");
                updateVoiceButtons("connected");
            }

            if (
                state === "disconnected" ||
                state === "failed" ||
                state === "closed"
            ) {
                void finishRealtimeVoice(
                    `connection_${state}`,
                    sessionId,
                    "error",
                    "切断されました"
                );
            }
        };

        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });

        localStream.getTracks().forEach(function(track) {
            currentPeerConnection.addTrack(track, localStream);
        });

        const currentDataChannel = (
            currentPeerConnection.createDataChannel("oai-events")
        );
        dataChannel = currentDataChannel;

        currentDataChannel.onopen = function() {
            console.log("Realtime data channel opened");

            const event = {
                type: "session.update",
                session: {
                    modalities: ["audio", "text"],
                    input_audio_transcription: {
                        model: "gpt-4o-mini-transcribe",
                        language: "ja"
                    }
                }
            };

            currentDataChannel.send(JSON.stringify(event));
        };

        currentDataChannel.onmessage = async function(event) {
            if (!isCurrentRealtimeSession(sessionId)) {
                return;
            }

            const data = JSON.parse(event.data);
            console.log("Realtime event:", data);

            await handleRealtimeEvent(data, sessionId);
        };

        currentDataChannel.onerror = function(error) {
            console.error("Realtime data channel error:", error);
            void finishRealtimeVoice(
                "data_channel_error",
                sessionId,
                "error",
                "データ通信エラー"
            );
        };

        currentDataChannel.onclose = function() {
            console.log("Realtime data channel closed");

            const currentLifecycle = getRealtimeLifecycle(sessionId);

            if (currentLifecycle && !currentLifecycle.finishing) {
                void finishRealtimeVoice(
                    "data_channel_closed",
                    sessionId,
                    "error",
                    "切断されました"
                );
            }
        };

        const offer = await currentPeerConnection.createOffer();
        await currentPeerConnection.setLocalDescription(offer);

        const sdpResponse = await fetch(
            "https://api.openai.com/v1/realtime/calls",
            {
                method: "POST",
                body: offer.sdp,
                headers: {
                    "Authorization": `Bearer ${ephemeralKey}`,
                    "Content-Type": "application/sdp"
                }
            }
        );

        if (!sdpResponse.ok) {
            const errorText = await sdpResponse.text();

            console.error("Realtime SDP error status:", sdpResponse.status);
            console.error("Realtime SDP error body:", errorText);

            throw new Error(
                `Realtime接続失敗: ${sdpResponse.status} ${errorText}`
            );
        }

        const answer = {
            type: "answer",
            sdp: await sdpResponse.text()
        };

        await currentPeerConnection.setRemoteDescription(answer);

        isRealtimeConnected = true;
        isRealtimeConnecting = false;

        updateVoiceStatus("connected", "接続中");
        updateVoiceButtons("connected");

        return true;

    } catch (error) {
        console.error(error);

        await finishRealtimeVoice(
            "startup_failed",
            sessionId,
            "error",
            "接続失敗"
        );

        if (source === "manual") {
            alert("音声接続に失敗しました。Consoleを確認してください。");
        }
        return false;
    }
}


function createRealtimeSessionId() {
    if (globalThis.crypto && globalThis.crypto.randomUUID) {
        return globalThis.crypto.randomUUID();
    }

    return [
        Date.now().toString(36),
        Math.random().toString(36).slice(2)
    ].join("-");
}


function getRealtimeLifecycle(sessionId) {
    if (
        !activeRealtimeLifecycle ||
        activeRealtimeLifecycle.sessionId !== sessionId
    ) {
        return null;
    }

    return activeRealtimeLifecycle;
}


function isCurrentRealtimeSession(sessionId) {
    return getRealtimeLifecycle(sessionId) !== null;
}


async function notifyTrayRealtime(
    eventName,
    payload,
    acceptConflict = false
) {
    const response = await fetch(
        `${TRAY_REALTIME_BRIDGE_URL}/realtime/${eventName}`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        }
    );

    let responseData = {};

    try {
        responseData = await response.json();
    } catch (error) {
        console.warn("Tray通知レスポンスの解析に失敗しました:", error);
    }

    if (acceptConflict && response.status === 409) {
        return responseData;
    }

    if (!response.ok || responseData.accepted === false) {
        const message = responseData.message || response.status;
        throw new Error(`Tray Realtime通知失敗: ${message}`);
    }

    return responseData;
}


async function notifyTrayRealtimeFinished(reason, sessionId) {
    let lastError = null;

    for (
        let attempt = 1;
        attempt <= REALTIME_FINISHED_NOTIFY_RETRY_COUNT;
        attempt += 1
    ) {
        try {
            return await notifyTrayRealtime(
                "finished",
                {
                    reason: reason,
                    session_id: sessionId
                },
                true
            );

        } catch (error) {
            lastError = error;
            console.warn(
                "Realtime終了通知に失敗しました:",
                `attempt=${attempt}`,
                error
            );

            if (attempt < REALTIME_FINISHED_NOTIFY_RETRY_COUNT) {
                await new Promise(function(resolve) {
                    setTimeout(
                        resolve,
                        REALTIME_FINISHED_NOTIFY_RETRY_DELAY_MS
                    );
                });
            }
        }
    }

    throw lastError || new Error("Realtime終了通知に失敗しました。");
}


async function notifyTrayRealtimeStarted(sessionId) {
    const lifecycle = getRealtimeLifecycle(sessionId);

    if (
        !lifecycle ||
        !lifecycle.trayAccepted ||
        lifecycle.startedNotified ||
        lifecycle.finishing
    ) {
        return false;
    }

    lifecycle.startedNotified = true;

    try {
        await notifyTrayRealtime("started", {
            source: lifecycle.source,
            session_id: lifecycle.sessionId
        });
        return true;

    } catch (error) {
        console.error("Realtime開始通知に失敗しました:", error);

        await finishRealtimeVoice(
            "started_notification_failed",
            sessionId,
            "error",
            "Tray通知失敗"
        );
        return false;
    }
}


async function handleRealtimeEvent(data, sessionId) {
    if (data.type === "session.created") {
        await notifyTrayRealtimeStarted(sessionId);
        return;
    }

    if (data.type === "response.function_call_arguments.done") {
        await handleRealtimeToolCall(data);
        return;
    }

    if (data.type === "input_audio_buffer.speech_started") {
        updateVoiceStatus("connected", "聞き取り中...");
        return;
    }

    if (data.type === "input_audio_buffer.speech_stopped") {
        updateVoiceStatus("connected", "考え中...");
        return;
    }

    if (data.type === "response.done") {
        updateVoiceStatus("connected", "接続中");
        return;
    }
}


async function handleRealtimeToolCall(data) {
    const toolName = data.name;
    const callId = data.call_id;
    const argumentsJson = JSON.parse(data.arguments);

    const toolResponse = await fetch("/realtime/tools", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            tool_name: toolName,
            arguments: argumentsJson
        })
    });

    const result = await toolResponse.json();

    dataChannel.send(JSON.stringify({
        type: "conversation.item.create",
        item: {
            type: "function_call_output",
            call_id: callId,
            output: JSON.stringify(result)
        }
    }));

    dataChannel.send(JSON.stringify({
        type: "response.create"
    }));
}


function addMessage(sender, text) {

    const div = document.createElement("div");

    if (sender === "user") {

        div.className = "user-message";

        div.innerHTML =
            `<strong>自分:</strong> ${text}`;

    } else {

        div.className = "ai-message";

        div.innerHTML =
            `<strong>Jarvis:</strong> ${text}`;
    }

    chatArea.appendChild(div);

    chatArea.scrollTop =
        chatArea.scrollHeight;

    return div;
}


function updateVoiceStatus(status, message) {
    voiceStatus.textContent = `音声状態: ${message}`;

    voiceStatus.classList.remove(
        "connected",
        "connecting",
        "disconnected",
        "error"
    );

    voiceStatus.classList.add(status);
}


function updateVoiceButtons(state) {
    if (state === "disconnected") {
        voiceConnectButton.disabled = false;
        voiceDisconnectButton.disabled = true;
        voiceReconnectButton.disabled = true;
    }

    if (state === "connecting") {
        voiceConnectButton.disabled = true;
        voiceDisconnectButton.disabled = true;
        voiceReconnectButton.disabled = true;
    }

    if (state === "connected") {
        voiceConnectButton.disabled = true;
        voiceDisconnectButton.disabled = false;
        voiceReconnectButton.disabled = false;
    }

    if (state === "error") {
        voiceConnectButton.disabled = false;
        voiceDisconnectButton.disabled = true;
        voiceReconnectButton.disabled = false;
    }
}


async function stopRealtimeVoice() {
    const sessionId = activeRealtimeLifecycle
        ? activeRealtimeLifecycle.sessionId
        : null;

    if (!sessionId) {
        cleanupRealtimeVoice();

        isRealtimeConnected = false;
        isRealtimeConnecting = false;

        updateVoiceStatus("disconnected", "未接続");
        updateVoiceButtons("disconnected");
        return false;
    }

    return finishRealtimeVoice(
        "manual_disconnect",
        sessionId,
        "disconnected",
        "未接続"
    );
}


async function finishRealtimeVoice(
    reason,
    sessionId,
    status = "disconnected",
    statusMessage = "未接続"
) {
    const lifecycle = getRealtimeLifecycle(sessionId);

    if (!lifecycle) {
        return false;
    }

    if (lifecycle.finishPromise) {
        return lifecycle.finishPromise;
    }

    if (lifecycle.finishing) {
        return false;
    }

    lifecycle.finishing = true;

    lifecycle.finishPromise = (async function() {
        cleanupRealtimeVoice();

        isRealtimeConnected = false;
        isRealtimeConnecting = false;

        updateVoiceStatus("connecting", "切断処理中...");
        updateVoiceButtons("connecting");

        if (lifecycle.trayAccepted) {
            try {
                await notifyTrayRealtimeFinished(
                    reason,
                    lifecycle.sessionId
                );

            } catch (error) {
                console.error("Realtime終了通知に失敗しました:", error);
            }
        }

        if (activeRealtimeLifecycle === lifecycle) {
            activeRealtimeLifecycle = null;
        }

        updateVoiceStatus(status, statusMessage);
        updateVoiceButtons(
            status === "disconnected" ? "disconnected" : "error"
        );

        return true;
    })();

    return lifecycle.finishPromise;
}


function cleanupRealtimeVoice() {
    const currentDataChannel = dataChannel;
    const currentPeerConnection = peerConnection;
    const currentLocalStream = localStream;
    const currentRemoteAudioElement = remoteAudioElement;

    dataChannel = null;
    peerConnection = null;
    localStream = null;
    remoteAudioElement = null;

    if (currentDataChannel) {
        try {
            currentDataChannel.close();
        } catch (error) {
            console.warn("DataChannel close error:", error);
        }
    }

    if (currentPeerConnection) {
        try {
            currentPeerConnection.close();
        } catch (error) {
            console.warn("PeerConnection close error:", error);
        }
    }

    if (currentLocalStream) {
        let tracks = [];

        try {
            tracks = currentLocalStream.getTracks();
        } catch (error) {
            console.warn("Local stream getTracks error:", error);
        }

        tracks.forEach(function(track) {
            try {
                track.stop();
            } catch (error) {
                console.warn("Local audio track stop error:", error);
            }
        });
    }

    if (currentRemoteAudioElement) {
        try {
            currentRemoteAudioElement.srcObject = null;
        } catch (error) {
            console.warn("Remote audio cleanup error:", error);
        }
    }
}


async function reconnectRealtimeVoice() {
    await stopRealtimeVoice();

    updateVoiceStatus("connecting", "再接続中...");
    updateVoiceButtons("connecting");

    await new Promise(function(resolve) {
        setTimeout(resolve, 1000);
    });

    await startRealtimeVoice("manual");
}


window.addEventListener("beforeunload", function() {
    const lifecycle = activeRealtimeLifecycle;

    if (lifecycle) {
        lifecycle.finishing = true;
    }

    cleanupRealtimeVoice();

    if (lifecycle && lifecycle.trayAccepted) {
        const body = new Blob(
            [JSON.stringify({
                reason: "window_closed",
                session_id: lifecycle.sessionId
            })],
            {type: "text/plain;charset=UTF-8"}
        );

        navigator.sendBeacon(
            `${TRAY_REALTIME_BRIDGE_URL}/realtime/finished`,
            body
        );
    }

    activeRealtimeLifecycle = null;
});


