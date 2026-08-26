(function initializeJarvisSystemLog(global) {
    "use strict";

    const jarvisUI = global.JarvisUI;

    if (!jarvisUI || !jarvisUI.dom || !jarvisUI.state) {
        throw new Error("Jarvis UI log dependencies are unavailable.");
    }

    const maximumEntries = 100;

    function append(message, level = "info") {
        const logContainer = jarvisUI.dom.elements.systemLog;

        if (!logContainer) {
            return null;
        }

        const entry = document.createElement("div");
        const timestamp = document.createElement("time");
        const content = document.createElement("span");

        entry.className = "system-log-entry";
        entry.dataset.level = String(level);
        timestamp.dateTime = new Date().toISOString();
        timestamp.textContent = new Date().toLocaleTimeString("ja-JP", {
            hour12: false
        });
        content.textContent = String(message);

        entry.append(timestamp, content);
        logContainer.appendChild(entry);

        while (logContainer.children.length > maximumEntries) {
            logContainer.firstElementChild.remove();
        }

        logContainer.scrollTop = logContainer.scrollHeight;
        return entry;
    }

    function clear() {
        const logContainer = jarvisUI.dom.elements.systemLog;

        if (logContainer) {
            logContainer.replaceChildren();
        }
    }

    jarvisUI.systemLog = Object.freeze({
        append: append,
        clear: clear
    });

    const clearButton = jarvisUI.dom.elements.systemLogClearButton;
    if (clearButton) {
        clearButton.addEventListener("click", clear);
    }

    append("INTERFACE_READY");

    jarvisUI.state.subscribe(function(state, previousState) {
        if (state.jarvisState !== previousState.jarvisState) {
            append(`STATE_${state.jarvisState.toUpperCase()}`);
        }

        if (
            state.connectionStatus === previousState.connectionStatus &&
            state.statusMessage === previousState.statusMessage
        ) {
            return;
        }

        const level = state.connectionStatus === "error" ? "error" : "info";
        append(
            `VOICE_${state.connectionStatus.toUpperCase()} ${state.statusMessage}`,
            level
        );
    });
})(window);
