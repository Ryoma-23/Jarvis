let peerConnection = null;
let dataChannel = null;
let localStream = null;
let remoteAudioElement = null;

let isRealtimeConnected = false;
let isRealtimeConnecting = false;

const sendButton = document.getElementById("send-button");
const messageInput = document.getElementById("message-input");
const chatArea = document.getElementById("chat-area");
const voiceConnectButton = document.getElementById("voice-connect-button");
const voiceDisconnectButton = document.getElementById("voice-disconnect-button");
const voiceReconnectButton = document.getElementById("voice-reconnect-button");
const voiceStatus = document.getElementById("voice-status");

voiceConnectButton.addEventListener("click", startRealtimeVoice);
voiceDisconnectButton.addEventListener("click", stopRealtimeVoice);
voiceReconnectButton.addEventListener("click", reconnectRealtimeVoice);

sendButton.addEventListener("click", sendMessage);

updateVoiceStatus("disconnected", "未接続");
updateVoiceButtons("disconnected");

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


async function startRealtimeVoice() {
    if (isRealtimeConnected || isRealtimeConnecting) {
        console.log("Realtime voice is already connected or connecting.");
        return;
    }

    try {
        isRealtimeConnecting = true;

        updateVoiceStatus("connecting", "接続中...");
        updateVoiceButtons("connecting");

        const tokenResponse = await fetch("/realtime/token");

        if (!tokenResponse.ok) {
            throw new Error(`Realtime token取得失敗: ${tokenResponse.status}`);
        }

        const tokenData = await tokenResponse.json();

        console.log("Realtime token data:", tokenData);

        const ephemeralKey = tokenData.value;

        if (!ephemeralKey) {
            throw new Error("Realtime用の一時トークンが取得できませんでした。");
        }

        peerConnection = new RTCPeerConnection();

        remoteAudioElement = document.createElement("audio");
        remoteAudioElement.autoplay = true;

        peerConnection.ontrack = function(event) {
            remoteAudioElement.srcObject = event.streams[0];
        };

        peerConnection.onconnectionstatechange = function() {
            if (!peerConnection) {
                return;
            }

            const state = peerConnection.connectionState;

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
                isRealtimeConnected = false;
                isRealtimeConnecting = false;

                updateVoiceStatus("disconnected", "切断されました");
                updateVoiceButtons("error");
            }
        };

        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });

        localStream.getTracks().forEach(function(track) {
            peerConnection.addTrack(track, localStream);
        });

        dataChannel = peerConnection.createDataChannel("oai-events");

        dataChannel.onopen = function() {
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

            dataChannel.send(JSON.stringify(event));
        };

        dataChannel.onmessage = async function(event) {
            const data = JSON.parse(event.data);
            console.log("Realtime event:", data);

            await handleRealtimeEvent(data);
        };

        dataChannel.onerror = function(error) {
            console.error("Realtime data channel error:", error);
            updateVoiceStatus("error", "データ通信エラー");
            updateVoiceButtons("error");
        };

        dataChannel.onclose = function() {
            console.log("Realtime data channel closed");
        };

        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);

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

        await peerConnection.setRemoteDescription(answer);

        isRealtimeConnected = true;
        isRealtimeConnecting = false;

        updateVoiceStatus("connected", "接続中");
        updateVoiceButtons("connected");

    } catch (error) {
        console.error(error);

        isRealtimeConnected = false;
        isRealtimeConnecting = false;

        cleanupRealtimeVoice();

        updateVoiceStatus("error", "接続失敗");
        updateVoiceButtons("error");

        alert("音声接続に失敗しました。Consoleを確認してください。");
    }
}


async function handleRealtimeEvent(data) {
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


function stopRealtimeVoice() {
    cleanupRealtimeVoice();

    isRealtimeConnected = false;
    isRealtimeConnecting = false;

    updateVoiceStatus("disconnected", "未接続");
    updateVoiceButtons("disconnected");
}


function cleanupRealtimeVoice() {
    if (dataChannel) {
        try {
            dataChannel.close();
        } catch (error) {
            console.warn("DataChannel close error:", error);
        }

        dataChannel = null;
    }

    if (peerConnection) {
        try {
            peerConnection.close();
        } catch (error) {
            console.warn("PeerConnection close error:", error);
        }

        peerConnection = null;
    }

    if (localStream) {
        localStream.getTracks().forEach(function(track) {
            track.stop();
        });

        localStream = null;
    }

    if (remoteAudioElement) {
        remoteAudioElement.srcObject = null;
        remoteAudioElement = null;
    }
}


async function reconnectRealtimeVoice() {
    stopRealtimeVoice();

    updateVoiceStatus("connecting", "再接続中...");
    updateVoiceButtons("connecting");

    await new Promise(function(resolve) {
        setTimeout(resolve, 1000);
    });

    await startRealtimeVoice();
}


window.addEventListener("beforeunload", function() {
    cleanupRealtimeVoice();
});


