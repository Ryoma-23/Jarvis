(function initializeJarvisDom(global, document) {
    "use strict";

    function byId(id) {
        return document.getElementById(id);
    }

    const elements = Object.freeze({
        sendButton: byId("send-button"),
        newConversationButton: byId("new-conversation-button"),
        conversationStatus: byId("conversation-status"),
        messageInput: byId("message-input"),
        chatArea: byId("chat-area"),
        voiceConnectButton: byId("voice-connect-button"),
        voiceDisconnectButton: byId("voice-disconnect-button"),
        voiceReconnectButton: byId("voice-reconnect-button"),
        voiceStatus: byId("voice-status"),
        coreArea: byId("core-area"),
        coreState: byId("core-state"),
        coreCaption: byId("core-caption"),
        systemLog: byId("system-log"),
        systemLogClearButton: byId("system-log-clear-button"),
        statusBar: byId("status-bar"),
        headerConnectionStatus: byId("header-connection-status")
    });

    const missingRequiredElements = [
        "sendButton",
        "newConversationButton",
        "conversationStatus",
        "messageInput",
        "chatArea",
        "voiceConnectButton",
        "voiceDisconnectButton",
        "voiceReconnectButton",
        "voiceStatus"
    ].filter(function(key) {
        return !elements[key];
    });

    if (missingRequiredElements.length > 0) {
        throw new Error(
            "Jarvis UI required elements are missing: " +
            missingRequiredElements.join(", ")
        );
    }

    const jarvisUI = global.JarvisUI || {};
    jarvisUI.dom = Object.freeze({
        byId: byId,
        elements: elements
    });
    global.JarvisUI = jarvisUI;
})(window, document);
