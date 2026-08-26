let peerConnection = null;
let dataChannel = null;
let localStream = null;
let remoteAudioElement = null;

let isRealtimeConnected = false;
let isRealtimeConnecting = false;
let activeRealtimeLifecycle = null;
let activeRealtimeHistoryRestore = null;
let realtimeBargeInTimer = null;
let realtimeBargeInTimerGeneration = 0;
let isRealtimeUserSpeechActive = false;
let activeRealtimeSpeechTurn = null;
let isRealtimeOutputAudioPlaying = false;
let isRealtimeResponseActive = false;
let activeRealtimeResponseId = null;
let activeRealtimeOutputResponseId = null;
let isRealtimeResponseCancelPending = false;
let activeConversationId = null;
let isConversationHistoryLoading = false;
let activeTextRequestCount = 0;
let realtimeHistorySyncGeneration = 0;
let realtimeTextContextSyncQueue = Promise.resolve();
let realtimeTextTurnSequence = 0;
let activeRealtimeTextTurn = null;
let pendingRealtimeTextResponseTurn = null;
let realtimePendingResponseRequestCount = 0;
let realtimeIdleTimer = null;
let realtimeIdleTimerGeneration = 0;
let realtimeLastMeaningfulActivityAt = 0;
let activeRealtimeToolCallCount = 0;
let hasConversationPersistenceWarning = false;

const messageElementsById = new Map();
const realtimeUserMessagesByItemId = new Map();
const realtimeSpeechTurnsByItemId = new Map();
const realtimeRestoredItemIds = new Set();
const realtimeAssistantMessagesByItemId = new Map();
const realtimeAssistantMessagesByResponseId = new Map();
const realtimeTextInputQueue = [];
const realtimeTextTurnsByResponseId = new Map();
const monitoredConversationPersistenceOperations = new Set();

const TRAY_REALTIME_BRIDGE_URL = "http://127.0.0.1:8767";
const REALTIME_FINISHED_NOTIFY_RETRY_COUNT = 8;
const REALTIME_FINISHED_NOTIFY_RETRY_DELAY_MS = 500;
const REALTIME_HISTORY_RESTORE_TIMEOUT_MS = 5000;
const REALTIME_HISTORY_EVENT_ID_PREFIX = "jarvis_history_restore";
const REALTIME_TEXT_INPUT_ACK_TIMEOUT_MS = 5000;
const REALTIME_TEXT_EVENT_ID_PREFIX = "jarvis_text_input";
const CONVERSATION_PERSISTENCE_POLL_INTERVAL_MS = 500;
const CONVERSATION_PERSISTENCE_MAX_POLLS = 80;
const REALTIME_MEDIA_AUDIO_CONSTRAINTS = Object.freeze({
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true
});
const REALTIME_INPUT_NOISE_REDUCTION_TYPE = "far_field";
const REALTIME_SERVER_VAD_THRESHOLD = 0.8;
const REALTIME_SERVER_VAD_SILENCE_DURATION_MS = 1200;
const REALTIME_CONVERSATION_IDLE_TIMEOUT_MS = 60_000;
const REALTIME_BARGE_IN_GUARD_MS = 600;
const REALTIME_BARGE_IN_MIN_TRANSCRIPT_CHARACTERS = 2;
const REALTIME_NON_SPEECH_TRANSCRIPTS = new Set([
    "咳",
    "咳払い",
    "せき",
    "せきばらい",
    "cough",
    "coughs",
    "coughing",
    "throatclearing",
    "blank_audio",
    "noise",
    "雑音",
    "物音",
    "無音",
    "音声なし",
    "咳き込み",
    "咳き込む",
    "ごほん"
]);
const REALTIME_BARGE_IN_FILLER_TRANSCRIPTS = new Set([
    "ん",
    "んっ",
    "んん",
    "あ",
    "あっ",
    "あー",
    "うっ",
    "うん",
    "うーん",
    "え",
    "えっ",
    "えー",
    "ふっ",
    "はっ"
]);

const {
    sendButton,
    newConversationButton,
    conversationStatus,
    messageInput,
    chatArea,
    voiceConnectButton,
    voiceDisconnectButton,
    voiceReconnectButton,
    voiceStatus
} = window.JarvisUI.dom.elements;

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
    if (
        isConversationHistoryLoading ||
        activeTextRequestCount > 0 ||
        activeRealtimeLifecycle
    ) {
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
        restoreConversationPersistenceWarning();

    } catch (error) {
        console.error("会話履歴の読み込みに失敗しました。", error);
        conversationStatus.textContent =
            "会話履歴を読み込めませんでした";

    } finally {
        setConversationHistoryLoading(false);
    }
}


async function createNewConversation() {
    if (
        isConversationHistoryLoading ||
        activeTextRequestCount > 0 ||
        activeRealtimeLifecycle
    ) {
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
        restoreConversationPersistenceWarning();
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


function monitorConversationPersistence(persistence) {
    const operationId = persistence
        ? String(persistence.operation_id || "").trim()
        : "";

    if (
        !operationId ||
        persistence.status !== "pending" ||
        monitoredConversationPersistenceOperations.has(operationId)
    ) {
        return;
    }

    monitoredConversationPersistenceOperations.add(operationId);
    void pollConversationPersistence(operationId);
}


async function pollConversationPersistence(operationId) {
    try {
        for (
            let pollCount = 0;
            pollCount < CONVERSATION_PERSISTENCE_MAX_POLLS;
            pollCount += 1
        ) {
            if (pollCount > 0) {
                await new Promise(function(resolve) {
                    setTimeout(
                        resolve,
                        CONVERSATION_PERSISTENCE_POLL_INTERVAL_MS
                    );
                });
            }

            let status;

            try {
                status = await requestJson(
                    "/conversations/persistence/" +
                    encodeURIComponent(operationId)
                );
            } catch (error) {
                continue;
            }

            if (status.status === "succeeded") {
                return;
            }

            if (status.status === "failed") {
                showConversationPersistenceWarning();
                return;
            }
        }

    } finally {
        monitoredConversationPersistenceOperations.delete(operationId);
    }
}


function showConversationPersistenceWarning() {
    hasConversationPersistenceWarning = true;
    conversationStatus.classList.add("warning");
    conversationStatus.textContent =
        "一部の会話履歴を保存できませんでした";
}


function restoreConversationPersistenceWarning() {
    if (hasConversationPersistenceWarning) {
        showConversationPersistenceWarning();
        return;
    }

    conversationStatus.classList.remove("warning");
    conversationStatus.textContent = "";
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
        isConversationHistoryLoading ||
        activeTextRequestCount > 0 ||
        Boolean(activeRealtimeLifecycle)
    );
}


async function sendMessage() {
    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    messageInput.value = "";

    if (shouldUseRealtimeTextInput()) {
        enqueueRealtimeTextInput(message);
        return;
    }

    await sendHttpChatMessage(message);
}


async function sendHttpChatMessage(message) {

    const userMessageView = renderConversationMessage({
        role: "user",
        content: message,
        status: "completed"
    });

    const assistantMessageView = renderConversationMessage({
        role: "assistant",
        content: "",
        status: "pending"
    });

    activeTextRequestCount += 1;
    updateNewConversationButton();
    let fullAssistantText = "";

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
                monitorConversationPersistence(data.persistence);

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
                    fullAssistantText += data.text;
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
                    await queueRealtimeTextContextSync(
                        message,
                        fullAssistantText,
                        activeConversationId
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

        const lifecycle = activeRealtimeLifecycle;

        if (lifecycle && !lifecycle.finishing) {
            markRealtimeConversationActivity(lifecycle.sessionId);
        }
    }
}


function shouldUseRealtimeTextInput() {
    return Boolean(
        activeRealtimeLifecycle &&
        !activeRealtimeLifecycle.finishing
    );
}


function enqueueRealtimeTextInput(message) {
    const lifecycle = activeRealtimeLifecycle;

    if (!lifecycle || lifecycle.finishing) {
        void sendHttpChatMessage(message);
        return;
    }

    const messageView = renderConversationMessage({
        role: "user",
        content: message,
        source: "text",
        status: "pending"
    });
    const turn = {
        sessionId: lifecycle.sessionId,
        conversationId: lifecycle.conversationId || activeConversationId,
        text: message,
        messageView: messageView,
        inputEventId: null,
        inputSignature: null,
        userItemId: null,
        userPersistPromise: null,
        userPersisted: false,
        responseRequested: false,
        responseEventIds: new Set(),
        responseIds: new Set(),
        ackTimeoutId: null,
        completed: false,
        failed: false
    };

    realtimeTextInputQueue.push(turn);
    activeTextRequestCount += 1;
    updateNewConversationButton();
    markRealtimeConversationActivity(turn.sessionId);
    processRealtimeTextInputQueue();
}


function processRealtimeTextInputQueue() {
    const lifecycle = activeRealtimeLifecycle;
    const currentDataChannel = dataChannel;

    if (
        activeRealtimeTextTurn ||
        realtimeTextInputQueue.length === 0 ||
        !lifecycle ||
        lifecycle.finishing ||
        lifecycle.historyRestoring ||
        !isRealtimeConnected ||
        !currentDataChannel ||
        currentDataChannel.readyState !== "open" ||
        isRealtimeUserSpeechActive ||
        isRealtimeResponseCancelPending
    ) {
        return;
    }

    if (
        realtimePendingResponseRequestCount > 0 ||
        isRealtimeResponseActive ||
        isRealtimeOutputAudioPlaying
    ) {
        if (!isRealtimeOutputAudioPlaying) {
            return;
        }

        if (!interruptRealtimeResponse(lifecycle.sessionId)) {
            return;
        }

        return;
    }

    const turn = realtimeTextInputQueue.shift();

    if (turn.sessionId !== lifecycle.sessionId) {
        failRealtimeTextTurn(turn, "Realtimeセッションが変更されました。");
        processRealtimeTextInputQueue();
        return;
    }

    activeRealtimeTextTurn = turn;
    turn.conversationId = lifecycle.conversationId || activeConversationId;
    realtimeTextTurnSequence += 1;
    turn.inputEventId = [
        REALTIME_TEXT_EVENT_ID_PREFIX,
        turn.sessionId,
        realtimeTextTurnSequence,
        "input"
    ].join("_");
    const inputEvent = {
        event_id: turn.inputEventId,
        type: "conversation.item.create",
        item: {
            type: "message",
            role: "user",
            content: [
                {
                    type: "input_text",
                    text: turn.text
                }
            ]
        }
    };
    turn.inputSignature = createRealtimeHistoryItemSignature(
        inputEvent.item
    );
    turn.ackTimeoutId = setTimeout(function() {
        failRealtimeTextTurn(
            turn,
            "Realtimeテキスト入力の確認がタイムアウトしました。"
        );
    }, REALTIME_TEXT_INPUT_ACK_TIMEOUT_MS);

    try {
        currentDataChannel.send(JSON.stringify(inputEvent));
        updateVoiceStatus("connected", "テキスト送信中...");
    } catch (error) {
        failRealtimeTextTurn(turn, String(error));
    }
}


async function handleRealtimeTextInputItemAdded(data, sessionId) {
    const turn = activeRealtimeTextTurn;

    if (
        !turn ||
        turn.sessionId !== sessionId ||
        turn.userItemId ||
        createRealtimeHistoryItemSignature(data.item) !== turn.inputSignature
    ) {
        return false;
    }

    const itemId = normalizeRealtimeId(data.item ? data.item.id : null);

    if (!itemId) {
        failRealtimeTextTurn(turn, "Realtimeテキスト入力IDがありません。");
        return true;
    }

    turn.userItemId = itemId;
    turn.userPersistPromise = saveRealtimeConversationMessage({
        role: "user",
        source: "text",
        content: turn.text,
        conversation_id: turn.conversationId,
        item_id: itemId
    });

    try {
        const result = await turn.userPersistPromise;
        turn.userPersisted = true;
        applyPersistedRealtimeMessage(turn.messageView, result);
    } catch (error) {
        console.error("Realtimeテキスト入力の保存に失敗しました。", error);
        failRealtimeTextTurn(turn, "テキスト履歴を保存できませんでした。");
    }

    return true;
}


async function handleRealtimeTextInputItemDone(data, sessionId) {
    const turn = activeRealtimeTextTurn;
    const itemId = normalizeRealtimeId(data.item ? data.item.id : null);

    if (
        !turn ||
        turn.sessionId !== sessionId ||
        !itemId ||
        itemId !== turn.userItemId
    ) {
        return false;
    }

    if (turn.userPersistPromise) {
        try {
            await turn.userPersistPromise;
        } catch (error) {
            return true;
        }
    }

    if (turn.failed || turn.responseRequested) {
        return true;
    }

    clearTimeout(turn.ackTimeoutId);
    turn.ackTimeoutId = null;
    turn.responseRequested = requestRealtimeResponse(sessionId, turn);

    if (!turn.responseRequested) {
        failRealtimeTextTurn(turn, "Realtime応答を開始できませんでした。");
        return true;
    }

    updateVoiceStatus("connected", "考え中...");
    return true;
}


function rejectRealtimeTextTurnFromServer(data, sessionId) {
    const turn = activeRealtimeTextTurn;

    if (!turn || turn.sessionId !== sessionId) {
        return false;
    }

    const eventId = normalizeRealtimeId(
        data.event_id || (data.error ? data.error.event_id : null)
    );

    if (
        !eventId ||
        (
            eventId !== turn.inputEventId &&
            !turn.responseEventIds.has(eventId)
        )
    ) {
        return false;
    }

    const message = data.message || (
        data.error ? data.error.message : "Realtimeテキスト入力エラー"
    );

    if (turn.responseEventIds.has(eventId)) {
        realtimePendingResponseRequestCount = Math.max(
            0,
            realtimePendingResponseRequestCount - 1
        );
    }

    failRealtimeTextTurn(turn, message);
    return true;
}


function failRealtimeTextTurn(turn, reason, continueQueue = true) {
    if (!turn || turn.completed || turn.failed) {
        return;
    }

    turn.failed = true;
    clearTimeout(turn.ackTimeoutId);
    turn.ackTimeoutId = null;

    if (activeRealtimeTextTurn === turn) {
        activeRealtimeTextTurn = null;
    }

    if (pendingRealtimeTextResponseTurn === turn) {
        pendingRealtimeTextResponseTurn = null;
    }

    if (!turn.userPersisted) {
        markMessageStatus(turn.messageView.element, "failed");
    }

    renderConversationMessage({
        role: "assistant",
        content: "Realtimeテキスト処理に失敗しました。",
        source: "text",
        status: "failed"
    });
    console.error("Realtimeテキスト処理に失敗しました。", reason);
    activeTextRequestCount = Math.max(0, activeTextRequestCount - 1);
    updateNewConversationButton();
    markRealtimeConversationActivity(turn.sessionId);

    if (continueQueue) {
        processRealtimeTextInputQueue();
    }
}


function completeRealtimeTextTurn(turn) {
    if (!turn || turn.completed || turn.failed) {
        return;
    }

    turn.completed = true;
    clearTimeout(turn.ackTimeoutId);
    turn.ackTimeoutId = null;

    if (activeRealtimeTextTurn === turn) {
        activeRealtimeTextTurn = null;
    }

    if (pendingRealtimeTextResponseTurn === turn) {
        pendingRealtimeTextResponseTurn = null;
    }

    activeTextRequestCount = Math.max(0, activeTextRequestCount - 1);
    updateNewConversationButton();
    markRealtimeConversationActivity(turn.sessionId);
    processRealtimeTextInputQueue();
}


function failPendingRealtimeTextTurns(reason) {
    const turns = [];

    if (activeRealtimeTextTurn) {
        turns.push(activeRealtimeTextTurn);
    }

    turns.push(...realtimeTextInputQueue.splice(0));

    for (const turn of turns) {
        failRealtimeTextTurn(turn, reason, false);
    }

    activeRealtimeTextTurn = null;
    pendingRealtimeTextResponseTurn = null;
    realtimePendingResponseRequestCount = 0;
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
        sessionCreatedReceived: false,
        historyRestoring: true,
        conversationId: null,
        finishing: false,
        finishPromise: null
    };

    activeRealtimeLifecycle = lifecycle;
    resetRealtimeBargeInState();
    resetRealtimeConversationTracking();
    resetRealtimeIdleState();

    try {
        isRealtimeConnecting = true;

        updateVoiceStatus("connecting", "接続中...");
        updateVoiceButtons("connecting");

        await notifyTrayRealtime("starting", {
            source: source,
            session_id: sessionId
        });

        lifecycle.trayAccepted = true;

        const tokenUrl = activeConversationId
            ? "/realtime/token?conversation_id=" +
                encodeURIComponent(activeConversationId)
            : "/realtime/token";
        const tokenResponse = await fetch(tokenUrl);

        if (!tokenResponse.ok) {
            throw new Error(`Realtime token取得失敗: ${tokenResponse.status}`);
        }

        const tokenData = await tokenResponse.json();

        const ephemeralKey = tokenData.value;
        const realtimeConversationId = normalizeRealtimeId(
            tokenData.conversation_id
        );

        if (!ephemeralKey || !realtimeConversationId) {
            throw new Error("Realtime用の一時トークンが取得できませんでした。");
        }

        activeConversationId = realtimeConversationId;
        lifecycle.conversationId = realtimeConversationId;

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

                updateVoiceStatus(
                    "connected",
                    lifecycle.historyRestoring
                        ? "履歴復元中..."
                        : "接続中"
                );
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

        const currentLocalStream = await navigator.mediaDevices.getUserMedia({
            audio: REALTIME_MEDIA_AUDIO_CONSTRAINTS
        });
        localStream = currentLocalStream;

        currentLocalStream.getTracks().forEach(function(track) {
            track.enabled = false;
            currentPeerConnection.addTrack(track, currentLocalStream);
        });

        const currentDataChannel = (
            currentPeerConnection.createDataChannel("oai-events")
        );
        dataChannel = currentDataChannel;

        currentDataChannel.onopen = function() {
            console.log("Realtime data channel opened");
            void initializeRealtimeDataChannel(
                currentDataChannel,
                currentLocalStream,
                sessionId,
                realtimeConversationId
            );
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

        updateVoiceStatus("connected", "履歴復元中...");
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


async function initializeRealtimeDataChannel(
    currentDataChannel,
    currentLocalStream,
    sessionId,
    conversationId
) {
    try {
        if (
            !isCurrentRealtimeSession(sessionId) ||
            dataChannel !== currentDataChannel
        ) {
            return false;
        }

        currentDataChannel.send(JSON.stringify({
            type: "session.update",
            session: {
                type: "realtime",
                audio: {
                    input: {
                        transcription: {
                            model: "gpt-4o-mini-transcribe",
                            language: "ja"
                        },
                        noise_reduction: {
                            type: REALTIME_INPUT_NOISE_REDUCTION_TYPE
                        },
                        turn_detection: {
                            type: "server_vad",
                            threshold: REALTIME_SERVER_VAD_THRESHOLD,
                            silence_duration_ms:
                                REALTIME_SERVER_VAD_SILENCE_DURATION_MS,
                            create_response: false,
                            interrupt_response: false
                        }
                    }
                }
            }
        }));

        updateVoiceStatus("connected", "履歴復元中...");
        await restoreRealtimeConversationHistory(
            currentDataChannel,
            sessionId,
            conversationId
        );

        const lifecycle = getRealtimeLifecycle(sessionId);

        if (
            !lifecycle ||
            lifecycle.finishing ||
            dataChannel !== currentDataChannel ||
            localStream !== currentLocalStream
        ) {
            return false;
        }

        setRealtimeMicrophoneEnabled(currentLocalStream, true);
        lifecycle.historyRestoring = false;
        markRealtimeConversationActivity(sessionId);
        updateVoiceStatus("connected", "接続中");
        processRealtimeTextInputQueue();

        if (lifecycle.sessionCreatedReceived) {
            await notifyTrayRealtimeStarted(sessionId);
        }

        return true;

    } catch (error) {
        console.error("Realtime履歴の復元に失敗しました。", error);

        if (isCurrentRealtimeSession(sessionId)) {
            await finishRealtimeVoice(
                "history_restore_failed",
                sessionId,
                "error",
                "履歴復元失敗"
            );
        }

        return false;
    }
}


async function restoreRealtimeConversationHistory(
    currentDataChannel,
    sessionId,
    conversationId
) {
    const historyUrl =
        "/realtime/conversation/history?conversation_id=" +
        encodeURIComponent(conversationId);
    const abortController = new AbortController();
    const fetchTimeoutId = setTimeout(function() {
        abortController.abort();
    }, REALTIME_HISTORY_RESTORE_TIMEOUT_MS);
    let response;

    try {
        response = await fetch(historyUrl, {
            signal: abortController.signal
        });
    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error("Realtime履歴取得がタイムアウトしました。");
        }

        throw error;
    } finally {
        clearTimeout(fetchTimeoutId);
    }

    if (!response.ok) {
        throw new Error(`Realtime履歴取得失敗: ${response.status}`);
    }

    const historyData = await response.json();
    const restoredConversationId = normalizeRealtimeId(
        historyData.conversation_id
    );
    const events = historyData.events;

    if (
        restoredConversationId !== conversationId ||
        !Array.isArray(events)
    ) {
        throw new Error("Realtime履歴レスポンスが不正です。");
    }

    if (events.length === 0) {
        return;
    }

    await sendRealtimeHistoryItemsAndWait(
        currentDataChannel,
        sessionId,
        events
    );
}


async function sendRealtimeHistoryItemsAndWait(
    currentDataChannel,
    sessionId,
    events
) {
    const restoreState = beginRealtimeHistoryRestore(
        sessionId,
        events
    );

    try {
        events.forEach(function(event, index) {
            if (
                !isCurrentRealtimeSession(sessionId) ||
                dataChannel !== currentDataChannel ||
                currentDataChannel.readyState !== "open"
            ) {
                throw new Error("Realtime履歴復元中に接続が終了しました。");
            }

            const eventId = [
                REALTIME_HISTORY_EVENT_ID_PREFIX,
                sessionId,
                restoreState.syncGeneration,
                index
            ].join("_");
            const restoreEvent = Object.assign({}, event, {
                event_id: eventId
            });

            restoreState.eventIds.add(eventId);
            currentDataChannel.send(JSON.stringify(restoreEvent));
        });

        await restoreState.promise;

    } catch (error) {
        failRealtimeHistoryRestore(restoreState, error);
        throw error;
    }
}


function beginRealtimeHistoryRestore(sessionId, events) {
    cancelRealtimeHistoryRestore("新しい履歴復元を開始します。");
    realtimeHistorySyncGeneration += 1;

    let resolveRestore;
    let rejectRestore;
    const promise = new Promise(function(resolve, reject) {
        resolveRestore = resolve;
        rejectRestore = reject;
    });
    const restoreState = {
        sessionId: sessionId,
        syncGeneration: realtimeHistorySyncGeneration,
        remainingItemCount: events.length,
        eventIds: new Set(),
        expectedItemSignatures: events.map(function(event) {
            return createRealtimeHistoryItemSignature(event.item);
        }),
        matchedSignatureIndexes: new Set(),
        addedItemIds: new Set(),
        completedItemIds: new Set(),
        timeoutId: null,
        resolve: resolveRestore,
        reject: rejectRestore,
        promise: promise
    };

    restoreState.timeoutId = setTimeout(function() {
        failRealtimeHistoryRestore(
            restoreState,
            new Error("Realtime履歴復元がタイムアウトしました。")
        );
    }, REALTIME_HISTORY_RESTORE_TIMEOUT_MS);
    activeRealtimeHistoryRestore = restoreState;
    return restoreState;
}


function registerRealtimeHistoryItemAdded(data, sessionId) {
    const restoreState = activeRealtimeHistoryRestore;

    if (!restoreState || restoreState.sessionId !== sessionId) {
        return false;
    }

    const itemId = normalizeRealtimeId(
        data.item ? data.item.id : null
    );

    if (!itemId) {
        return true;
    }

    const itemSignature = createRealtimeHistoryItemSignature(data.item);
    const signatureIndex = restoreState.expectedItemSignatures.findIndex(
        function(expectedSignature, index) {
            return (
                !restoreState.matchedSignatureIndexes.has(index) &&
                expectedSignature === itemSignature
            );
        }
    );

    if (signatureIndex < 0) {
        return false;
    }

    restoreState.matchedSignatureIndexes.add(signatureIndex);
    restoreState.addedItemIds.add(itemId);
    realtimeRestoredItemIds.add(itemId);
    return true;
}


function createRealtimeHistoryItemSignature(item) {
    const content = item && Array.isArray(item.content)
        ? item.content
        : [];

    return JSON.stringify({
        role: item ? item.role || "" : "",
        content: content.map(function(part) {
            return {
                type: part ? part.type || "" : "",
                text: part ? String(part.text || "") : ""
            };
        })
    });
}


function acknowledgeRealtimeHistoryItemDone(data, sessionId) {
    const restoreState = activeRealtimeHistoryRestore;

    if (!restoreState || restoreState.sessionId !== sessionId) {
        return false;
    }

    const itemId = normalizeRealtimeId(
        data.item ? data.item.id : null
    );

    if (!itemId || !restoreState.addedItemIds.has(itemId)) {
        return false;
    }

    if (restoreState.completedItemIds.has(itemId)) {
        return true;
    }

    restoreState.completedItemIds.add(itemId);
    restoreState.remainingItemCount -= 1;

    if (restoreState.remainingItemCount <= 0) {
        completeRealtimeHistoryRestore(restoreState);
    }

    return true;
}


function queueRealtimeTextContextSync(
    userText,
    assistantText,
    conversationId
) {
    const normalizedUserText = String(userText || "").trim();
    const normalizedAssistantText = String(assistantText || "").trim();
    const normalizedConversationId = normalizeRealtimeId(conversationId);
    const lifecycle = activeRealtimeLifecycle;

    if (
        !normalizedUserText ||
        !normalizedAssistantText ||
        !normalizedConversationId ||
        !lifecycle ||
        lifecycle.finishing ||
        lifecycle.conversationId !== normalizedConversationId
    ) {
        return Promise.resolve(false);
    }

    const sessionId = lifecycle.sessionId;

    realtimeTextContextSyncQueue = realtimeTextContextSyncQueue
        .catch(function(error) {
            console.warn("前回のRealtimeテキスト履歴同期に失敗しました。", error);
            return false;
        })
        .then(function() {
            return syncCompletedTextExchangeToRealtime(
                normalizedUserText,
                normalizedAssistantText,
                normalizedConversationId,
                sessionId
            );
        });

    return realtimeTextContextSyncQueue;
}


async function syncCompletedTextExchangeToRealtime(
    userText,
    assistantText,
    conversationId,
    sessionId
) {
    const lifecycle = getRealtimeLifecycle(sessionId);
    const currentDataChannel = dataChannel;
    const currentLocalStream = localStream;

    if (
        !lifecycle ||
        lifecycle.finishing ||
        lifecycle.historyRestoring ||
        lifecycle.conversationId !== conversationId ||
        !currentDataChannel ||
        currentDataChannel.readyState !== "open" ||
        !currentLocalStream
    ) {
        return false;
    }

    const events = [
        {
            type: "conversation.item.create",
            item: {
                type: "message",
                role: "user",
                content: [
                    {
                        type: "input_text",
                        text: userText
                    }
                ]
            }
        },
        {
            type: "conversation.item.create",
            item: {
                type: "message",
                role: "assistant",
                status: "completed",
                content: [
                    {
                        type: "output_text",
                        text: assistantText
                    }
                ]
            }
        }
    ];

    setRealtimeMicrophoneEnabled(currentLocalStream, false);
    updateVoiceStatus("connected", "テキスト履歴同期中...");

    try {
        await sendRealtimeHistoryItemsAndWait(
            currentDataChannel,
            sessionId,
            events
        );
    } catch (error) {
        console.error("Realtimeへのテキスト履歴同期に失敗しました。", error);

        if (isCurrentRealtimeSession(sessionId)) {
            await finishRealtimeVoice(
                "text_context_sync_failed",
                sessionId,
                "error",
                "履歴同期失敗"
            );
        }

        return false;
    }

    if (
        !isCurrentRealtimeSession(sessionId) ||
        dataChannel !== currentDataChannel ||
        localStream !== currentLocalStream
    ) {
        return false;
    }

    setRealtimeMicrophoneEnabled(currentLocalStream, true);
    updateVoiceStatus("connected", "接続中");
    return true;
}


function completeRealtimeHistoryRestore(restoreState) {
    if (activeRealtimeHistoryRestore !== restoreState) {
        return;
    }

    activeRealtimeHistoryRestore = null;
    clearTimeout(restoreState.timeoutId);
    restoreState.resolve();
}


function failRealtimeHistoryRestore(restoreState, error) {
    if (activeRealtimeHistoryRestore !== restoreState) {
        return;
    }

    activeRealtimeHistoryRestore = null;
    clearTimeout(restoreState.timeoutId);
    restoreState.reject(error);
}


function rejectRealtimeHistoryRestoreFromServer(data, sessionId) {
    const restoreState = activeRealtimeHistoryRestore;

    if (!restoreState || restoreState.sessionId !== sessionId) {
        return false;
    }

    const eventId = normalizeRealtimeId(
        data.event_id || (data.error ? data.error.event_id : null)
    );

    if (!eventId || !restoreState.eventIds.has(eventId)) {
        return false;
    }

    const message = data.message || (
        data.error ? data.error.message : "Realtime履歴復元エラー"
    );
    failRealtimeHistoryRestore(restoreState, new Error(message));
    return true;
}


function cancelRealtimeHistoryRestore(reason) {
    const restoreState = activeRealtimeHistoryRestore;

    if (!restoreState) {
        return;
    }

    failRealtimeHistoryRestore(restoreState, new Error(reason));
}


function setRealtimeMicrophoneEnabled(stream, enabled) {
    if (!stream) {
        return;
    }

    let tracks = [];

    try {
        tracks = stream.getTracks();
    } catch (error) {
        console.warn("Realtime microphone track取得エラー:", error);
        return;
    }

    tracks.forEach(function(track) {
        try {
            track.enabled = enabled;
        } catch (error) {
            console.warn("Realtime microphone切替エラー:", error);
        }
    });
}


function isRestoredRealtimeItem(data) {
    const itemId = normalizeRealtimeId(data.item_id);
    return itemId ? realtimeRestoredItemIds.has(itemId) : false;
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


function clearRealtimeIdleTimer(resetActivity = false) {
    realtimeIdleTimerGeneration += 1;

    if (realtimeIdleTimer !== null) {
        clearTimeout(realtimeIdleTimer);
        realtimeIdleTimer = null;
    }

    if (resetActivity) {
        realtimeLastMeaningfulActivityAt = 0;
    }
}


function resetRealtimeIdleState() {
    clearRealtimeIdleTimer(true);
    activeRealtimeToolCallCount = 0;
}


function pauseRealtimeIdleTimer() {
    clearRealtimeIdleTimer(false);
}


function markRealtimeConversationActivity(sessionId) {
    const lifecycle = getRealtimeLifecycle(sessionId);

    if (!lifecycle || lifecycle.finishing) {
        return false;
    }

    realtimeLastMeaningfulActivityAt = Date.now();
    scheduleRealtimeIdleTimeout(sessionId);
    return true;
}


function isRealtimeConversationBusy(sessionId) {
    const lifecycle = getRealtimeLifecycle(sessionId);

    return Boolean(
        !lifecycle ||
        lifecycle.finishing ||
        lifecycle.historyRestoring ||
        activeRealtimeHistoryRestore ||
        !isRealtimeConnected ||
        isRealtimeConnecting ||
        isRealtimeUserSpeechActive ||
        isRealtimeResponseActive ||
        isRealtimeOutputAudioPlaying ||
        isRealtimeResponseCancelPending ||
        realtimePendingResponseRequestCount > 0 ||
        activeRealtimeTextTurn ||
        pendingRealtimeTextResponseTurn ||
        realtimeTextInputQueue.length > 0 ||
        activeTextRequestCount > 0 ||
        activeRealtimeToolCallCount > 0
    );
}


function scheduleRealtimeIdleTimeout(sessionId) {
    if (!isCurrentRealtimeSession(sessionId)) {
        return false;
    }

    clearRealtimeIdleTimer(false);

    if (
        realtimeLastMeaningfulActivityAt <= 0 ||
        isRealtimeConversationBusy(sessionId)
    ) {
        return false;
    }

    const elapsedMs = Math.max(
        0,
        Date.now() - realtimeLastMeaningfulActivityAt
    );
    const delayMs = Math.max(
        0,
        REALTIME_CONVERSATION_IDLE_TIMEOUT_MS - elapsedMs
    );
    const timerGeneration = realtimeIdleTimerGeneration;

    realtimeIdleTimer = setTimeout(function() {
        void handleRealtimeIdleTimeout(sessionId, timerGeneration);
    }, delayMs);
    return true;
}


async function handleRealtimeIdleTimeout(sessionId, timerGeneration) {
    if (
        timerGeneration !== realtimeIdleTimerGeneration ||
        !isCurrentRealtimeSession(sessionId)
    ) {
        return false;
    }

    realtimeIdleTimer = null;

    if (isRealtimeConversationBusy(sessionId)) {
        return false;
    }

    const elapsedMs = Math.max(
        0,
        Date.now() - realtimeLastMeaningfulActivityAt
    );

    if (elapsedMs < REALTIME_CONVERSATION_IDLE_TIMEOUT_MS) {
        return scheduleRealtimeIdleTimeout(sessionId);
    }

    return finishRealtimeVoice(
        "idle_timeout",
        sessionId,
        "disconnected",
        "1分間会話がなかったため終了しました"
    );
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
    activeRealtimeSpeechTurn = null;
    realtimeSpeechTurnsByItemId.clear();
    isRealtimeOutputAudioPlaying = false;
    isRealtimeResponseActive = false;
    activeRealtimeResponseId = null;
    activeRealtimeOutputResponseId = null;
    isRealtimeResponseCancelPending = false;
}


function startRealtimeBargeInGuard(sessionId) {
    clearRealtimeBargeInTimer();

    if (
        !isCurrentRealtimeSession(sessionId) ||
        !isRealtimeUserSpeechActive ||
        !isRealtimeOutputAudioPlaying ||
        !activeRealtimeSpeechTurn
    ) {
        return;
    }

    const guardedTurn = activeRealtimeSpeechTurn;
    guardedTurn.startedWhileOutputPlaying = true;
    const timerGeneration = realtimeBargeInTimerGeneration;

    realtimeBargeInTimer = setTimeout(function() {
        if (timerGeneration !== realtimeBargeInTimerGeneration) {
            return;
        }

        realtimeBargeInTimer = null;

        if (
            !isCurrentRealtimeSession(sessionId) ||
            !isRealtimeUserSpeechActive ||
            activeRealtimeSpeechTurn !== guardedTurn
        ) {
            return;
        }

        guardedTurn.guardDurationMet = true;
    }, REALTIME_BARGE_IN_GUARD_MS);
}


function interruptRealtimeResponse(sessionId) {
    if (
        !isCurrentRealtimeSession(sessionId) ||
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
    const interruptedResponseId = (
        activeRealtimeResponseId || activeRealtimeOutputResponseId
    );

    if (isRealtimeResponseActive) {
        const cancelEvent = {
            type: "response.cancel"
        };
        const responseId = interruptedResponseId;

        if (responseId) {
            cancelEvent.response_id = responseId;
        }

        try {
            currentDataChannel.send(JSON.stringify(cancelEvent));
            isRealtimeResponseActive = false;
            activeRealtimeResponseId = null;
            isRealtimeResponseCancelPending = true;
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

    if (eventSent) {
        markActiveRealtimeAssistantInterrupted(
            sessionId,
            interruptedResponseId
        );
    }

    clearRealtimeBargeInTimer();
    return eventSent;
}


function startRealtimeSpeechTurn(data) {
    const itemId = normalizeRealtimeId(data.item_id);
    const turn = {
        itemId: itemId,
        startedAtMs: Date.now(),
        startedWhileOutputPlaying: isRealtimeOutputAudioPlaying,
        guardDurationMet: false,
        responseRequested: false
    };

    activeRealtimeSpeechTurn = turn;

    if (itemId) {
        realtimeSpeechTurnsByItemId.set(itemId, turn);
    }

    return turn;
}


function stopRealtimeSpeechTurn(data) {
    const itemId = normalizeRealtimeId(data.item_id);
    let turn = itemId
        ? realtimeSpeechTurnsByItemId.get(itemId) || null
        : null;

    if (!turn) {
        turn = activeRealtimeSpeechTurn;
    }

    if (!turn) {
        return null;
    }

    if (!turn.itemId && itemId) {
        turn.itemId = itemId;
        realtimeSpeechTurnsByItemId.set(itemId, turn);
    }

    if (
        turn.startedWhileOutputPlaying &&
        Date.now() - turn.startedAtMs >= REALTIME_BARGE_IN_GUARD_MS
    ) {
        turn.guardDurationMet = true;
    }

    if (activeRealtimeSpeechTurn === turn) {
        activeRealtimeSpeechTurn = null;
    }

    return turn;
}


function getRealtimeSpeechTurn(itemId) {
    if (itemId && realtimeSpeechTurnsByItemId.has(itemId)) {
        return realtimeSpeechTurnsByItemId.get(itemId);
    }

    if (
        activeRealtimeSpeechTurn &&
        (!itemId || !activeRealtimeSpeechTurn.itemId)
    ) {
        return activeRealtimeSpeechTurn;
    }

    return null;
}


function discardRealtimeSpeechTurn(turn, itemId) {
    if (itemId) {
        realtimeSpeechTurnsByItemId.delete(itemId);
    }

    if (turn && turn.itemId) {
        realtimeSpeechTurnsByItemId.delete(turn.itemId);
    }

    if (activeRealtimeSpeechTurn === turn) {
        activeRealtimeSpeechTurn = null;
    }
}


function isMeaningfulRealtimeUserTranscript(transcript, isBargeIn) {
    const normalized = String(transcript || "").trim();

    if (!normalized) {
        return false;
    }

    const compact = normalized
        .toLowerCase()
        .replace(/[\s。、！？!?.,…・「」『』\[\]()（）【】<>"'`]/g, "");

    if (
        !compact ||
        REALTIME_NON_SPEECH_TRANSCRIPTS.has(compact) ||
        (isBargeIn && REALTIME_BARGE_IN_FILLER_TRANSCRIPTS.has(compact))
    ) {
        return false;
    }

    const lexicalCharacters = compact.match(
        /[a-z0-9\u3040-\u30ff\u3400-\u9fff]/g
    ) || [];

    if (lexicalCharacters.length === 0) {
        return false;
    }

    return (
        !isBargeIn ||
        lexicalCharacters.length >=
            REALTIME_BARGE_IN_MIN_TRANSCRIPT_CHARACTERS
    );
}


function requestRealtimeResponse(sessionId, textTurn = null) {
    if (!isCurrentRealtimeSession(sessionId)) {
        return false;
    }

    const currentDataChannel = dataChannel;

    if (!currentDataChannel || currentDataChannel.readyState !== "open") {
        console.warn("Realtime応答を開始できません: DataChannel未接続");
        return false;
    }

    const responseEvent = {
        type: "response.create"
    };

    if (textTurn) {
        realtimeTextTurnSequence += 1;
        responseEvent.event_id = [
            REALTIME_TEXT_EVENT_ID_PREFIX,
            sessionId,
            realtimeTextTurnSequence,
            "response"
        ].join("_");
        textTurn.responseEventIds.add(responseEvent.event_id);
        pendingRealtimeTextResponseTurn = textTurn;
    }

    realtimePendingResponseRequestCount += 1;
    pauseRealtimeIdleTimer();

    try {
        currentDataChannel.send(JSON.stringify(responseEvent));
        return true;
    } catch (error) {
        realtimePendingResponseRequestCount = Math.max(
            0,
            realtimePendingResponseRequestCount - 1
        );

        if (pendingRealtimeTextResponseTurn === textTurn) {
            pendingRealtimeTextResponseTurn = null;
        }

        console.warn("Realtime response.create送信エラー:", error);
        scheduleRealtimeIdleTimeout(sessionId);
        return false;
    }
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
    if (rejectRealtimeHistoryRestoreFromServer(data, sessionId)) {
        return;
    }

    if (rejectRealtimeTextTurnFromServer(data, sessionId)) {
        return;
    }

    if (
        data.type === "conversation.item.added" &&
        registerRealtimeHistoryItemAdded(data, sessionId)
    ) {
        return;
    }

    if (
        data.type === "conversation.item.added" &&
        await handleRealtimeTextInputItemAdded(data, sessionId)
    ) {
        return;
    }

    if (
        data.type === "conversation.item.done" &&
        acknowledgeRealtimeHistoryItemDone(data, sessionId)
    ) {
        return;
    }

    if (
        data.type === "conversation.item.done" &&
        await handleRealtimeTextInputItemDone(data, sessionId)
    ) {
        return;
    }

    if (data.type === "session.created") {
        const lifecycle = getRealtimeLifecycle(sessionId);

        if (!lifecycle) {
            return;
        }

        lifecycle.sessionCreatedReceived = true;

        if (!lifecycle.historyRestoring) {
            await notifyTrayRealtimeStarted(sessionId);
        }
        return;
    }

    if (data.type === "response.function_call_arguments.done") {
        await handleRealtimeToolCall(data, sessionId);
        return;
    }

    if (
        data.type ===
        "conversation.item.input_audio_transcription.completed"
    ) {
        await handleRealtimeUserTranscriptionCompleted(data, sessionId);
        return;
    }

    if (
        data.type ===
        "conversation.item.input_audio_transcription.failed"
    ) {
        const itemId = normalizeRealtimeId(data.item_id);
        const speechTurn = getRealtimeSpeechTurn(itemId);
        discardRealtimeSpeechTurn(speechTurn, itemId);
        window.JarvisUI.controller.speechFailed();
        updateVoiceStatus("connected", "接続中");
        console.warn("ユーザー音声の文字起こしに失敗しました。", data);
        processRealtimeTextInputQueue();
        scheduleRealtimeIdleTimeout(sessionId);
        return;
    }

    if (data.type === "response.output_audio_transcript.delta") {
        handleRealtimeAssistantTranscriptDelta(data);
        return;
    }

    if (data.type === "response.output_audio_transcript.done") {
        await handleRealtimeAssistantTranscriptDone(data, sessionId);
        return;
    }

    if (data.type === "response.created") {
        window.JarvisUI.controller.responseCreated();
        pauseRealtimeIdleTimer();
        realtimePendingResponseRequestCount = Math.max(
            0,
            realtimePendingResponseRequestCount - 1
        );
        isRealtimeResponseActive = true;
        activeRealtimeResponseId = normalizeRealtimeId(
            data.response ? data.response.id : null
        );

        if (pendingRealtimeTextResponseTurn && activeRealtimeResponseId) {
            const turn = pendingRealtimeTextResponseTurn;
            pendingRealtimeTextResponseTurn = null;
            turn.responseIds.add(activeRealtimeResponseId);
            realtimeTextTurnsByResponseId.set(
                activeRealtimeResponseId,
                turn
            );
        }
        return;
    }

    if (data.type === "output_audio_buffer.started") {
        window.JarvisUI.controller.audioStarted();
        pauseRealtimeIdleTimer();
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
        window.JarvisUI.controller.audioStopped();
        finishRealtimeOutputAudio(data.response_id || null);
        processRealtimeTextInputQueue();
        markRealtimeConversationActivity(sessionId);
        return;
    }

    if (data.type === "input_audio_buffer.speech_started") {
        window.JarvisUI.controller.speechStarted();
        pauseRealtimeIdleTimer();
        isRealtimeUserSpeechActive = true;
        startRealtimeSpeechTurn(data);

        if (isRealtimeOutputAudioPlaying) {
            startRealtimeBargeInGuard(sessionId);
        } else {
            clearRealtimeBargeInTimer();
        }

        updateVoiceStatus("connected", "聞き取り中...");
        return;
    }

    if (data.type === "input_audio_buffer.speech_stopped") {
        window.JarvisUI.controller.speechStopped();
        isRealtimeUserSpeechActive = false;
        const speechTurn = stopRealtimeSpeechTurn(data);
        clearRealtimeBargeInTimer();

        if (speechTurn && !speechTurn.startedWhileOutputPlaying) {
            speechTurn.responseRequested = requestRealtimeResponse(sessionId);
        }

        updateVoiceStatus("connected", "考え中...");
        scheduleRealtimeIdleTimeout(sessionId);
        return;
    }

    if (data.type === "response.done") {
        const completedResponseId = normalizeRealtimeId(
            data.response ? data.response.id : null
        );
        const textTurn = completedResponseId
            ? realtimeTextTurnsByResponseId.get(completedResponseId) || null
            : null;
        const responseStatus = data.response
            ? String(data.response.status || "")
            : "";
        const hasFunctionCall = realtimeResponseHasFunctionCall(
            data.response
        );
        const isCompletedFunctionCall = (
            hasFunctionCall && responseStatus === "completed"
        );

        window.JarvisUI.controller.responseDone(isCompletedFunctionCall);
        isRealtimeResponseCancelPending = false;

        if (
            !completedResponseId ||
            completedResponseId === activeRealtimeResponseId
        ) {
            isRealtimeResponseActive = false;
            activeRealtimeResponseId = null;
        }

        if (textTurn && !isCompletedFunctionCall) {
            const assistantState = completedResponseId
                ? realtimeAssistantMessagesByResponseId.get(
                    completedResponseId
                ) || null
                : null;

            if (assistantState && assistantState.persistPromise) {
                try {
                    await assistantState.persistPromise;
                } catch (error) {
                    failRealtimeTextTurn(
                        textTurn,
                        "Realtime回答を保存できませんでした。"
                    );
                    updateVoiceStatus("connected", "接続中");
                    return;
                }
            }

            if (
                responseStatus === "completed" ||
                responseStatus === "cancelled"
            ) {
                if (
                    responseStatus === "completed" &&
                    (!assistantState || !assistantState.persisted)
                ) {
                    failRealtimeTextTurn(
                        textTurn,
                        "Realtime回答のtranscriptを保存できませんでした。"
                    );
                } else {
                    completeRealtimeTextTurn(textTurn);
                }
            } else {
                failRealtimeTextTurn(
                    textTurn,
                    `Realtime応答終了: ${responseStatus || "unknown"}`
                );
            }
        } else if (!textTurn) {
            processRealtimeTextInputQueue();
        }

        updateVoiceStatus("connected", "接続中");
        markRealtimeConversationActivity(sessionId);
        return;
    }
}


function realtimeResponseHasFunctionCall(response) {
    const output = response && Array.isArray(response.output)
        ? response.output
        : [];
    return output.some(function(item) {
        return item && item.type === "function_call";
    });
}


async function handleRealtimeUserTranscriptionCompleted(data, sessionId) {
    if (
        !isCurrentRealtimeSession(sessionId) ||
        isRestoredRealtimeItem(data)
    ) {
        return;
    }

    const itemId = normalizeRealtimeId(data.item_id);
    const transcript = String(data.transcript || "");
    const speechTurn = getRealtimeSpeechTurn(itemId);
    const isBargeIn = Boolean(
        speechTurn && speechTurn.startedWhileOutputPlaying
    );
    const passedBargeInGuard = Boolean(
        speechTurn && speechTurn.guardDurationMet
    );
    let messageView = realtimeUserMessagesByItemId.get(itemId);
    const isNewTranscription = !messageView;

    if (
        !itemId ||
        !isMeaningfulRealtimeUserTranscript(transcript, isBargeIn) ||
        (isBargeIn && !passedBargeInGuard)
    ) {
        discardRealtimeSpeechTurn(speechTurn, itemId);
        updateVoiceStatus("connected", "接続中");
        processRealtimeTextInputQueue();
        scheduleRealtimeIdleTimeout(sessionId);
        return;
    }

    markRealtimeConversationActivity(sessionId);

    if (
        isNewTranscription &&
        !(speechTurn && speechTurn.responseRequested)
    ) {
        if (isBargeIn && isRealtimeOutputAudioPlaying) {
            interruptRealtimeResponse(sessionId);
        }

        requestRealtimeResponse(sessionId);
    }
    discardRealtimeSpeechTurn(speechTurn, itemId);

    if (!messageView) {
        messageView = renderConversationMessage({
            role: "user",
            content: transcript,
            source: "voice",
            status: "completed"
        });
        realtimeUserMessagesByItemId.set(itemId, messageView);
    } else {
        updateMessageContent(messageView, transcript);
    }

    try {
        const result = await saveRealtimeConversationMessage({
            role: "user",
            source: "voice",
            content: transcript,
            conversation_id: activeConversationId,
            item_id: itemId
        });
        applyPersistedRealtimeMessage(messageView, result);

    } catch (error) {
        console.error("ユーザー音声履歴の保存に失敗しました。", error);
        markMessageStatus(messageView.element, "failed");
    }
}


function handleRealtimeAssistantTranscriptDelta(data) {
    if (isRestoredRealtimeItem(data)) {
        return;
    }

    const state = getRealtimeAssistantTranscriptState(data);
    const delta = String(data.delta || "");

    if (!state || !delta) {
        return;
    }

    state.transcript += delta;

    if (!state.messageView) {
        state.messageView = renderConversationMessage({
            role: "assistant",
            content: state.transcript,
            source: state.source,
            status: state.interruptedRequested
                ? "interrupted"
                : "pending"
        });
    } else {
        appendMessageText(state.messageView, delta);
    }
}


async function handleRealtimeAssistantTranscriptDone(data, sessionId) {
    if (
        !isCurrentRealtimeSession(sessionId) ||
        isRestoredRealtimeItem(data)
    ) {
        return;
    }

    const state = getRealtimeAssistantTranscriptState(data);

    if (!state) {
        return;
    }

    const transcript = String(data.transcript || state.transcript || "");

    if (!transcript.trim()) {
        return;
    }

    state.transcript = transcript;

    if (!state.messageView) {
        state.messageView = renderConversationMessage({
            role: "assistant",
            content: transcript,
            source: state.source,
            status: state.interruptedRequested
                ? "interrupted"
                : "pending"
        });
    } else {
        updateMessageContent(state.messageView, transcript);
    }

    try {
        const persistPromise = saveRealtimeConversationMessage({
            role: "assistant",
            source: state.source,
            content: transcript,
            conversation_id: activeConversationId,
            item_id: state.itemId,
            response_id: state.responseId
        });
        state.persistPromise = persistPromise;
        const result = await persistPromise;
        state.persisted = true;
        applyPersistedRealtimeMessage(state.messageView, result);

        if (state.interruptedRequested) {
            markMessageStatus(state.messageView.element, "interrupted");

            if (!state.interruptionPersisted) {
                void persistRealtimeAssistantInterruption(state, sessionId);
            }
        }

    } catch (error) {
        console.error("Assistant音声履歴の保存に失敗しました。", error);
        markMessageStatus(state.messageView.element, "failed");
    }
}


function getRealtimeAssistantTranscriptState(data) {
    const itemId = normalizeRealtimeId(data.item_id);
    const responseId = normalizeRealtimeId(data.response_id);
    let state = null;

    if (itemId) {
        state = realtimeAssistantMessagesByItemId.get(itemId) || null;
    }

    if (!state && responseId) {
        state = (
            realtimeAssistantMessagesByResponseId.get(responseId) || null
        );
    }

    if (!state) {
        if (!itemId && !responseId) {
            return null;
        }

        state = {
            itemId: itemId,
            responseId: responseId,
            source: responseId && realtimeTextTurnsByResponseId.has(responseId)
                ? "text"
                : "voice",
            transcript: "",
            messageView: null,
            interruptedRequested: false,
            interruptionPersisted: false,
            interruptionPersistPromise: null,
            persistPromise: null,
            persisted: false
        };
    }

    if (itemId) {
        state.itemId = itemId;
        realtimeAssistantMessagesByItemId.set(itemId, state);
    }

    if (responseId) {
        state.responseId = responseId;

        if (realtimeTextTurnsByResponseId.has(responseId)) {
            state.source = "text";
        }

        realtimeAssistantMessagesByResponseId.set(responseId, state);
    }

    return state;
}


function markActiveRealtimeAssistantInterrupted(sessionId, responseId) {
    if (!isCurrentRealtimeSession(sessionId) || !responseId) {
        return;
    }

    const state = getRealtimeAssistantTranscriptState({
        response_id: responseId
    });

    if (!state) {
        return;
    }

    state.interruptedRequested = true;

    if (state.messageView) {
        markMessageStatus(state.messageView.element, "interrupted");
    }

    void persistRealtimeAssistantInterruption(state, sessionId);
}


async function persistRealtimeAssistantInterruption(state, sessionId) {
    if (
        state.interruptionPersisted ||
        state.interruptionPersistPromise ||
        !isCurrentRealtimeSession(sessionId)
    ) {
        return;
    }

    const persistPromise = requestJson(
        "/realtime/conversation/assistant/interrupted",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                content: state.transcript,
                source: state.source,
                conversation_id: activeConversationId,
                item_id: state.itemId,
                response_id: state.responseId
            })
        }
    );
    state.interruptionPersistPromise = persistPromise;

    try {
        const result = await persistPromise;
        monitorConversationPersistence(result.persistence);
        state.interruptionPersisted = true;

        if (state.messageView) {
            applyPersistedRealtimeMessage(state.messageView, result);
            markMessageStatus(state.messageView.element, "interrupted");
        }

    } catch (error) {
        console.error("Assistant割り込み履歴の保存に失敗しました。", error);

    } finally {
        if (state.interruptionPersistPromise === persistPromise) {
            state.interruptionPersistPromise = null;
        }
    }
}


async function saveRealtimeConversationMessage(payload) {
    const result = await requestJson("/realtime/conversation/messages", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });
    monitorConversationPersistence(result.persistence);
    return result;
}


function applyPersistedRealtimeMessage(messageView, result) {
    const message = result.message;

    if (result.conversation_id) {
        activeConversationId = result.conversation_id;
    }

    if (!message) {
        return;
    }

    registerMessageElement(message.id, messageView.element);
    messageView.element.dataset.messageSource = message.source;

    if (String(message.content || "").trim()) {
        updateMessageContent(messageView, message.content);
    }

    markMessageStatus(messageView.element, message.status);
}


function normalizeRealtimeId(value) {
    const normalized = String(value || "").trim();
    return normalized || null;
}


function resetRealtimeConversationTracking() {
    realtimeUserMessagesByItemId.clear();
    realtimeRestoredItemIds.clear();
    realtimeAssistantMessagesByItemId.clear();
    realtimeAssistantMessagesByResponseId.clear();
    realtimeTextTurnsByResponseId.clear();
    pendingRealtimeTextResponseTurn = null;
    realtimePendingResponseRequestCount = 0;
}


async function handleRealtimeToolCall(data, sessionId) {
    const toolName = data.name;
    const callId = data.call_id;
    const responseId = normalizeRealtimeId(
        data.response_id || activeRealtimeResponseId
    );
    const textTurn = responseId
        ? realtimeTextTurnsByResponseId.get(responseId) || null
        : null;
    const currentDataChannel = dataChannel;
    let followupResponseRequested = false;

    if (
        !isCurrentRealtimeSession(sessionId) ||
        !currentDataChannel ||
        currentDataChannel.readyState !== "open"
    ) {
        return;
    }

    activeRealtimeToolCallCount += 1;
    window.JarvisUI.controller.toolStarted(toolName);
    markRealtimeConversationActivity(sessionId);

    try {
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

        if (!toolResponse.ok) {
            throw new Error(`Realtime tool実行失敗: ${toolResponse.status}`);
        }

        const result = await toolResponse.json();

        if (
            !isCurrentRealtimeSession(sessionId) ||
            dataChannel !== currentDataChannel ||
            currentDataChannel.readyState !== "open"
        ) {
            return;
        }

        currentDataChannel.send(JSON.stringify({
            type: "conversation.item.create",
            item: {
                type: "function_call_output",
                call_id: callId,
                output: JSON.stringify(result)
            }
        }));

        if (!requestRealtimeResponse(sessionId, textTurn)) {
            throw new Error("tool結果後のRealtime応答を開始できませんでした。");
        }
        followupResponseRequested = true;

    } catch (error) {
        console.error("Realtime tool callingに失敗しました。", error);

        if (textTurn) {
            failRealtimeTextTurn(textTurn, String(error));
        }

    } finally {
        activeRealtimeToolCallCount = Math.max(
            0,
            activeRealtimeToolCallCount - 1
        );
        window.JarvisUI.controller.toolFinished(
            followupResponseRequested
        );
        markRealtimeConversationActivity(sessionId);
    }
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
    element.dataset.messageSource = message.source || "text";

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


function updateMessageContent(messageView, text) {
    messageView.contentElement.textContent = String(text || "");
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

    window.JarvisUI.state.update({
        connectionStatus: status,
        statusMessage: message
    });
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

    updateNewConversationButton();
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

    window.JarvisUI.controller.reset();
    cancelRealtimeHistoryRestore("Realtime接続を終了しました。");
    failPendingRealtimeTextTurns("Realtime接続が終了しました。");
    resetRealtimeIdleState();
    resetRealtimeBargeInState();
    resetRealtimeConversationTracking();

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
