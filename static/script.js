let peerConnection = null;
let dataChannel = null;
let localStream = null;

const sendButton = document.getElementById("send-button");
const messageInput = document.getElementById("message-input");
const chatArea = document.getElementById("chat-area");
const voiceButton = document.getElementById("voice-button");

voiceButton.addEventListener("click", startRealtimeVoice);

sendButton.addEventListener("click", sendMessage);

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
    try {
        voiceButton.disabled = true;
        voiceButton.textContent = "接続中...";

        const tokenResponse = await fetch("/realtime/token");
        const tokenData = await tokenResponse.json();

        const ephemeralKey = tokenData.value;

        peerConnection = new RTCPeerConnection();

        const audioElement = document.createElement("audio");
        audioElement.autoplay = true;

        peerConnection.ontrack = function(event) {
            audioElement.srcObject = event.streams[0];
        };

        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });

        peerConnection.addTrack(localStream.getTracks()[0]);

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

        dataChannel.onmessage = function(event) {
            const data = JSON.parse(event.data);
            console.log("Realtime event:", data);

            if (data.type === "session.created") {
                const updateEvent = {
                    type: "session.update",
                    session: {
                        modalities: ["audio", "text"],
                        input_audio_transcription: {
                            model: "gpt-4o-mini-transcribe",
                            language: "ja"
                        }
                    }
                };

                dataChannel.send(JSON.stringify(updateEvent));
            }
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

        const answer = {
            type: "answer",
            sdp: await sdpResponse.text()
        };

        await peerConnection.setRemoteDescription(answer);

        voiceButton.textContent = "音声接続中";

    } catch (error) {
        console.error(error);
        voiceButton.disabled = false;
        voiceButton.textContent = "音声接続";
        alert("音声接続に失敗しました。Consoleを確認してください。");
    }
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