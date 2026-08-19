let peerConnection = null;
let dataChannel = null;
let localStream = null;
let remoteAudioElement = null;

let isRealtimeConnected = false;
let isRealtimeConnecting = false;
let activeRealtimeLifecycle = null;
let realtimeBargeInTimer = null;
let realtimeBargeInTimerGeneration = 0;
let isRealtimeUserSpeechActive = false;
let isRealtimeOutputAudioPlaying = false;
let isRealtimeResponseActive = false;
let activeRealtimeResponseId = null;
let activeRealtimeOutputResponseId = null;
let activeConversationId = null;
let isConversationHistoryLoading = false;
let activeTextRequestCount = 0;

const messageElementsById = new Map();

const TRAY_REALTIME_BRIDGE_URL = "http://127.0.0.1:8767";
const REALTIME_FINISHED_NOTIFY_RETRY_COUNT = 8;
const REALTIME_FINISHED_NOTIFY_RETRY_DELAY_MS = 500;
const REALTIME_MEDIA_AUDIO_CONSTRAINTS = Object.freeze({
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true
});
const REALTIME_INPUT_NOISE_REDUCTION_TYPE = "far_field";
const REALTIME_SERVER_VAD_THRESHOLD = 0.8;
const REALTIME_BARGE_IN_GUARD_MS = 600;

const sendButton = document.getElementById("send-button");
const newConversationButton = document.getElementById(
    "new-conversation-button"
);
const conversationStatus = document.getElementById("conversation-status");
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
newConversationButton.addEventListener("click", function() {
    void createNewConversation();
});
window.addEventListener("focus", function() {
    void loadActiveConversationHistory();
});

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

void loadActiveConversationHistory();


async function loadActiveConversationHistory() {
    if (isConversationHistoryLoading || activeTextRequestCount > 0) {
        return;
    }

    setConversationHistoryLoading(true, "会話履歴を読み込んでいます...");

    try {
        const activeData = await requestJson("/conversations/active");
        let conversation = activeData.conversation;

        if (!conversation) {
            const createdData = await requestJson("/conversations", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({})
            });
            conversation = createdData.conversation;
        }

        activeConversationId = conversation.id;

        const historyData = await requestJson(
            `/conversations/${encodeURIComponent(activeConversationId)}` +
            "/messages"
        );
        renderConversationHistory(historyData.messages);
        conversationStatus.textContent = "";

    } catch (error) {
        console.error("会話履歴の読み込みに失敗しました。", error);
        conversationStatus.textContent =
            "会話履歴を読み込めませんでした";

    } finally {
        setConversationHistoryLoading(false);
    }
}


async function createNewConversation() {
    if (isConversationHistoryLoading || activeTextRequestCount > 0) {
        return;
    }

    setConversationHistoryLoading(true, "新しい会話を作成しています...");

    try {
        const data = await requestJson("/conversations", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({})
        });

        activeConversationId = data.conversation.id;
        clearRenderedMessages();
        conversationStatus.textContent = "";
        messageInput.focus();

    } catch (error) {
        console.error("新しい会話の作成に失敗しました。", error);
        conversationStatus.textContent =
            "新しい会話を作成できませんでした";

    } finally {
        setConversationHistoryLoading(false);
    }
}


async function requestJson(url, options = undefined) {
    const response = await fetch(url, options);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
}


function setConversationHistoryLoading(isLoading, message = "") {
    isConversationHistoryLoading = isLoading;
    messageInput.disabled = isLoading;
    sendButton.disabled = isLoading;
    updateNewConversationButton();

    if (message) {
        conversationStatus.textContent = message;
    }
}


function updateNewConversationButton() {
    newConversationButton.disabled = (
        isConversationHistoryLoading || activeTextRequestCount > 0
    );
}


async function sendMessage() {

    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    const userMessageView = renderConversationMessage({
        role: "user",
        content: message,
        status: "completed"
    });

    messageInput.value = "";

    const assistantMessageView = renderConversationMessage({
        role: "assistant",
        content: "",
        status: "pending"
    });

    activeTextRequestCount += 1;
    updateNewConversationButton();

    try {

        const response = await fetch("/chat/stream", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message,
                conversation_id: activeConversationId
            })
        });

        if (!response.ok || !response.body) {
            throw new Error(`HTTP ${response.status}`);
        }

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

                if (data.conversation_id) {
                    activeConversationId = data.conversation_id;
                }

                if (data.user_message_id) {
                    registerMessageElement(
                        data.user_message_id,
                        userMessageView.element
                    );
                }

                if (data.assistant_message_id) {
                    registerMessageElement(
                        data.assistant_message_id,
                        assistantMessageView.element
                    );
                }

                if (data.text) {
                    appendMessageText(assistantMessageView, data.text);
                }

                if (data.error) {
                    markMessageStatus(assistantMessageView.element, "failed");
                    appendMessageText(
                        assistantMessageView,
                        "\nエラーが発生しました: " + data.error
                    );
                }

                if (data.done) {
                    markMessageStatus(
                        assistantMessageView.element,
                        "completed"
                    );
                }

                chatArea.scrollTop =
                    chatArea.scrollHeight;
            }
        }

    } catch (error) {

        markMessageStatus(assistantMessageView.element, "failed");
        appendMessageText(
            assistantMessageView,
            "\n通信エラーが発生しました"
        );

    } finally {
        activeTextRequestCount = Math.max(0, activeTextRequestCount - 1);
        updateNewConversationButton();
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
    resetRealtimeBargeInState();

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
            audio: REALTIME_MEDIA_AUDIO_CONSTRAINTS
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
                    },
                    input_audio_noise_reduction: {
                        type: REALTIME_INPUT_NOISE_REDUCTION_TYPE
                    },
                    turn_detection: {
                        type: "server_vad",
                        threshold: REALTIME_SERVER_VAD_THRESHOLD,
                        create_response: true,
                        interrupt_response: false
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


function clearRealtimeBargeInTimer() {
    realtimeBargeInTimerGeneration += 1;

    if (realtimeBargeInTimer !== null) {
        clearTimeout(realtimeBargeInTimer);
        realtimeBargeInTimer = null;
    }
}


function resetRealtimeBargeInState() {
    clearRealtimeBargeInTimer();
    isRealtimeUserSpeechActive = false;
    isRealtimeOutputAudioPlaying = false;
    isRealtimeResponseActive = false;
    activeRealtimeResponseId = null;
    activeRealtimeOutputResponseId = null;
}


function startRealtimeBargeInGuard(sessionId) {
    clearRealtimeBargeInTimer();

    if (
        !isCurrentRealtimeSession(sessionId) ||
        !isRealtimeUserSpeechActive ||
        !isRealtimeOutputAudioPlaying
    ) {
        return;
    }

    const timerGeneration = realtimeBargeInTimerGeneration;

    realtimeBargeInTimer = setTimeout(function() {
        if (timerGeneration !== realtimeBargeInTimerGeneration) {
            return;
        }

        realtimeBargeInTimer = null;

        if (
            !isCurrentRealtimeSession(sessionId) ||
            !isRealtimeUserSpeechActive ||
            !isRealtimeOutputAudioPlaying
        ) {
            return;
        }

        interruptRealtimeResponse(sessionId);
    }, REALTIME_BARGE_IN_GUARD_MS);
}


function interruptRealtimeResponse(sessionId) {
    if (
        !isCurrentRealtimeSession(sessionId) ||
        !isRealtimeUserSpeechActive ||
        !isRealtimeOutputAudioPlaying
    ) {
        return false;
    }

    const currentDataChannel = dataChannel;

    if (!currentDataChannel || currentDataChannel.readyState !== "open") {
        console.warn("Realtime割り込みを送信できません: DataChannel未接続");
        return false;
    }

    let eventSent = false;

    if (isRealtimeResponseActive) {
        const cancelEvent = {
            type: "response.cancel"
        };
        const responseId = (
            activeRealtimeResponseId || activeRealtimeOutputResponseId
        );

        if (responseId) {
            cancelEvent.response_id = responseId;
        }

        try {
            currentDataChannel.send(JSON.stringify(cancelEvent));
            isRealtimeResponseActive = false;
            activeRealtimeResponseId = null;
            eventSent = true;
        } catch (error) {
            console.warn("Realtime response.cancel送信エラー:", error);
        }
    }

    try {
        currentDataChannel.send(JSON.stringify({
            type: "output_audio_buffer.clear"
        }));
        isRealtimeOutputAudioPlaying = false;
        activeRealtimeOutputResponseId = null;
        eventSent = true;
    } catch (error) {
        console.warn("Realtime output audio clear送信エラー:", error);
    }

    clearRealtimeBargeInTimer();
    return eventSent;
}


function finishRealtimeOutputAudio(responseId) {
    if (
        responseId &&
        activeRealtimeOutputResponseId &&
        responseId !== activeRealtimeOutputResponseId
    ) {
        return;
    }

    isRealtimeOutputAudioPlaying = false;
    activeRealtimeOutputResponseId = null;
    clearRealtimeBargeInTimer();
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

    if (data.type === "response.created") {
        isRealtimeResponseActive = true;
        activeRealtimeResponseId = data.response
            ? data.response.id || null
            : null;
        return;
    }

    if (data.type === "output_audio_buffer.started") {
        isRealtimeOutputAudioPlaying = true;
        activeRealtimeOutputResponseId = (
            data.response_id || activeRealtimeResponseId
        );

        if (isRealtimeUserSpeechActive) {
            startRealtimeBargeInGuard(sessionId);
        }
        return;
    }

    if (
        data.type === "output_audio_buffer.stopped" ||
        data.type === "output_audio_buffer.cleared"
    ) {
        finishRealtimeOutputAudio(data.response_id || null);
        return;
    }

    if (data.type === "input_audio_buffer.speech_started") {
        isRealtimeUserSpeechActive = true;

        if (isRealtimeOutputAudioPlaying) {
            startRealtimeBargeInGuard(sessionId);
        } else {
            clearRealtimeBargeInTimer();
        }

        updateVoiceStatus("connected", "聞き取り中...");
        return;
    }

    if (data.type === "input_audio_buffer.speech_stopped") {
        isRealtimeUserSpeechActive = false;
        clearRealtimeBargeInTimer();
        updateVoiceStatus("connected", "考え中...");
        return;
    }

    if (data.type === "response.done") {
        const completedResponseId = data.response
            ? data.response.id || null
            : null;

        if (
            !completedResponseId ||
            completedResponseId === activeRealtimeResponseId
        ) {
            isRealtimeResponseActive = false;
            activeRealtimeResponseId = null;
        }

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


function renderConversationHistory(messages) {
    clearRenderedMessages();

    for (const message of messages) {
        renderConversationMessage(message);
    }

    chatArea.scrollTop = chatArea.scrollHeight;
}


function clearRenderedMessages() {
    messageElementsById.clear();
    chatArea.replaceChildren();
}


function renderConversationMessage(message) {
    const isUser = message.role === "user";
    const element = document.createElement("div");
    const label = document.createElement("strong");
    const contentElement = document.createElement("span");

    element.className = isUser ? "user-message" : "ai-message";
    label.textContent = isUser ? "自分: " : "Jarvis: ";
    contentElement.className = "message-content";
    contentElement.textContent = String(message.content || "");

    element.append(label, contentElement);
    markMessageStatus(element, message.status || "completed");

    if (message.id) {
        registerMessageElement(message.id, element);
    }

    chatArea.appendChild(element);
    chatArea.scrollTop = chatArea.scrollHeight;

    return {
        element: element,
        contentElement: contentElement
    };
}


function appendMessageText(messageView, text) {
    messageView.contentElement.append(
        document.createTextNode(String(text))
    );
}


function registerMessageElement(messageId, element) {
    const normalizedMessageId = String(messageId || "").trim();

    if (!normalizedMessageId) {
        return;
    }

    const previousMessageId = element.dataset.messageId;

    if (previousMessageId) {
        messageElementsById.delete(previousMessageId);
    }

    element.dataset.messageId = normalizedMessageId;
    messageElementsById.set(normalizedMessageId, element);
}


function markMessageStatus(element, status) {
    element.dataset.messageStatus = status;
    element.classList.toggle("message-failed", status === "failed");
    element.classList.toggle(
        "message-interrupted",
        status === "interrupted"
    );
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

    resetRealtimeBargeInState();

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
