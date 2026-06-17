const sendButton = document.getElementById("send-button");

const messageInput =
    document.getElementById("message-input");

const chatArea =
    document.getElementById("chat-area");


sendButton.addEventListener("click", sendMessage);


async function sendMessage() {

    const message = messageInput.value;

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


function addMessage(sender, text) {

    const div = document.createElement("div");

    if (sender === "user") {

        div.className = "user-message";

        div.innerHTML =
            `<strong>あなた:</strong> ${text}`;

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