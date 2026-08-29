(function initializeJarvisIntegrationStatus(global) {
    "use strict";

    const jarvisUI = global.JarvisUI;
    if (!jarvisUI || !jarvisUI.state || !jarvisUI.dom) {
        throw new Error("Jarvis integration status dependencies are unavailable.");
    }

    function formatToolName(value) {
        return String(value || "")
            .trim()
            .replace(/[_-]+/g, " ")
            .replace(/\s+/g, " ")
            .toUpperCase();
    }

    function renderTool(state) {
        const container = jarvisUI.dom.elements.coreToolStatus;
        if (!container) {
            return;
        }

        const toolName = formatToolName(state.activeTool);
        const label = container.querySelector("[data-tool-name]");
        container.hidden = !toolName;
        if (label) {
            label.textContent = toolName;
        }
        document.body.dataset.toolActive = toolName ? "true" : "false";
    }

    function renderNotification(state) {
        const notification = jarvisUI.dom.elements.uiNotification;
        if (!notification) {
            return;
        }

        const isError = state.connectionStatus === "error";
        notification.hidden = !isError;
        notification.setAttribute("role", isError ? "alert" : "status");
        notification.textContent = isError
            ? `CONNECTION ERROR — ${state.statusMessage}`
            : "";
    }

    function render(state) {
        renderTool(state);
        renderNotification(state);
    }

    jarvisUI.state.subscribe(render);
    render(jarvisUI.state.getSnapshot());

    jarvisUI.integrationStatus = Object.freeze({render: render});
})(window);
