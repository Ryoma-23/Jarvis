(function initializeJarvisSystemLog(global) {
    "use strict";

    const jarvisUI = global.JarvisUI;

    if (!jarvisUI || !jarvisUI.dom || !jarvisUI.state) {
        throw new Error("Jarvis UI log dependencies are unavailable.");
    }

    const maximumEntries = 100;

    function classify(message, level) {
        const normalized = String(message || "");
        if (level === "error") return { kind: "error", label: "ERROR", content: normalized };
        if (normalized.startsWith("TOOL_")) {
            return { kind: "tool", label: "TOOL", content: normalized.replace(/^TOOL_/, "") };
        }
        return { kind: "info", label: "INFO", content: normalized };
    }

    function append(message, level = "info") {
        const logContainer = jarvisUI.dom.elements.systemLog;

        if (!logContainer) {
            return null;
        }

        const entry = document.createElement("div");
        const timestamp = document.createElement("time");
        const type = document.createElement("span");
        const content = document.createElement("span");
        const classification = classify(message, level);

        entry.className = "system-log-entry log-entry-new";
        entry.dataset.level = String(level);
        entry.dataset.kind = classification.kind;
        timestamp.dateTime = new Date().toISOString();
        timestamp.textContent = new Date().toLocaleTimeString("ja-JP", {
            hour12: false
        });
        type.className = "log-type";
        type.textContent = classification.label;
        content.className = "log-content";
        content.textContent = classification.content;

        entry.append(timestamp, type, content);
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

        if (state.activeTool !== previousState.activeTool) {
            if (previousState.activeTool) {
                append(`TOOL_END ${String(previousState.activeTool).toUpperCase()}`);
            }
            if (state.activeTool) {
                append(`TOOL_START ${String(state.activeTool).toUpperCase()}`);
            }
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
