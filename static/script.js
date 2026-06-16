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

    try {

        const response = await fetch("/chat", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();

        addMessage("ai", data.reply);

    } catch (error) {

        addMessage(
            "ai",
            "エラーが発生しました"
        );
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
}
