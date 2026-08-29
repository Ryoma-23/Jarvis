(function initializeJarvisConversationView(global, document) {
    "use strict";

    const jarvisUI = global.JarvisUI;
    if (!jarvisUI || !jarvisUI.dom) {
        throw new Error("Jarvis conversation view dependencies are unavailable.");
    }

    const chatArea = jarvisUI.dom.elements.chatArea;
    const messageElementsById = new Map();
    const statusElementsByMessage = new WeakMap();
    const pendingMessages = new Set();
    const maximumRenderedMessages = 200;
    const statusLabels = Object.freeze({
        pending: "STREAMING",
        interrupted: "INTERRUPTED",
        failed: "FAILED"
    });

    function renderConversationHistory(messages) {
        clearRenderedMessages();
        messages.forEach(renderConversationMessage);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function clearRenderedMessages() {
        messageElementsById.clear();
        pendingMessages.clear();
        chatArea.setAttribute("aria-busy", "false");
        chatArea.replaceChildren();
    }

    function trimRenderedMessages() {
        while (chatArea.children.length > maximumRenderedMessages) {
            const oldestMessage = chatArea.firstElementChild;
            const messageId = oldestMessage.dataset.messageId;
            if (messageId) {
                messageElementsById.delete(messageId);
            }
            pendingMessages.delete(oldestMessage);
            oldestMessage.remove();
        }
    }

    function renderConversationMessage(message) {
        const isUser = message.role === "user";
        const source = message.source === "voice" ? "voice" : "text";
        const element = document.createElement("div");
        const headerElement = document.createElement("div");
        const label = document.createElement("strong");
        const contentElement = document.createElement("span");
        const metadataElement = document.createElement("span");
        const sourceElement = document.createElement("span");
        const statusElement = document.createElement("span");

        element.className = isUser ? "user-message" : "ai-message";
        element.dataset.messageRole = isUser ? "user" : "assistant";
        element.dataset.messageSource = source;
        headerElement.className = "message-head";
        label.textContent = isUser ? "YOU" : "JARVIS";
        contentElement.className = "message-content";
        contentElement.textContent = String(message.content || "");
        metadataElement.className = "message-meta";
        sourceElement.className = "message-source";
        sourceElement.textContent = source.toUpperCase();
        statusElement.className = "message-state";
        metadataElement.append(sourceElement, statusElement);
        headerElement.append(label, metadataElement);
        element.append(headerElement, contentElement);
        statusElementsByMessage.set(element, statusElement);

        markMessageStatus(element, message.status || "completed");
        if (message.id) {
            registerMessageElement(message.id, element);
        }

        chatArea.appendChild(element);
        trimRenderedMessages();
        chatArea.scrollTop = chatArea.scrollHeight;
        return {element: element, contentElement: contentElement};
    }

    function appendMessageText(messageView, text) {
        messageView.contentElement.append(document.createTextNode(String(text)));
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
        const normalizedStatus = statusLabels[status] ? status : "completed";
        const statusElement = statusElementsByMessage.get(element);
        element.dataset.messageStatus = normalizedStatus;
        element.classList.toggle("message-pending", normalizedStatus === "pending");
        element.classList.toggle("message-failed", normalizedStatus === "failed");
        element.classList.toggle("message-interrupted", normalizedStatus === "interrupted");
        if (normalizedStatus === "pending") {
            pendingMessages.add(element);
        } else {
            pendingMessages.delete(element);
        }
        chatArea.setAttribute(
            "aria-busy",
            pendingMessages.size > 0 ? "true" : "false"
        );
        if (statusElement) {
            statusElement.textContent = normalizedStatus === "pending"
                && element.dataset.messageRole === "user"
                ? "SENDING"
                : statusLabels[normalizedStatus] || "";
            statusElement.hidden = normalizedStatus === "completed";
        }
    }

    jarvisUI.conversationView = Object.freeze({
        renderConversationHistory: renderConversationHistory,
        clearRenderedMessages: clearRenderedMessages,
        renderConversationMessage: renderConversationMessage,
        appendMessageText: appendMessageText,
        updateMessageContent: updateMessageContent,
        registerMessageElement: registerMessageElement,
        markMessageStatus: markMessageStatus
    });
})(window, document);
