(function initializeJarvisIntegrationStatus(global) {
    "use strict";

    const jarvisUI = global.JarvisUI;
    if (!jarvisUI || !jarvisUI.state || !jarvisUI.dom) {
        throw new Error("Jarvis integration status dependencies are unavailable.");
    }

    const toolLabels = Object.freeze({
        memory_search: "MEMORY",
        memory_save: "MEMORY SAVE",
        weather: "WEATHER",
        web_search: "WEB SEARCH",
        note_create: "NOTE",
        task_create: "TASK"
    });
    let toolHideTimer = null;
    let visibleTool = "";

    function normalizeToolName(value) {
        return String(value || "")
            .trim()
            .replace(/[_-]+/g, " ")
            .replace(/\s+/g, " ")
            .toUpperCase();
    }

    function formatToolName(value) {
        const key = String(value || "").trim().toLowerCase();
        const normalized = toolLabels[key] || normalizeToolName(value);
        return normalized.length > 18 ? `${normalized.slice(0, 17)}…` : normalized;
    }

    function renderTool(state) {
        const container = jarvisUI.dom.elements.coreToolStatus;
        if (!container) {
            return;
        }

        const fullToolName = normalizeToolName(state.activeTool);
        const toolName = formatToolName(state.activeTool);
        const label = container.querySelector("[data-tool-name]");
        if (toolName) {
            if (toolHideTimer) global.clearTimeout(toolHideTimer);
            toolHideTimer = null;
            visibleTool = toolName;
            container.hidden = false;
            container.classList.remove("is-completing");
            container.setAttribute("aria-label", `Active tool: ${fullToolName}`);
            container.title = fullToolName;
            if (label) label.textContent = toolName;
        } else if (visibleTool && !container.hidden) {
            container.classList.add("is-completing");
            container.setAttribute("aria-label", `Tool completed: ${visibleTool}`);
            if (toolHideTimer) global.clearTimeout(toolHideTimer);
            toolHideTimer = global.setTimeout(function() {
                container.hidden = true;
                container.classList.remove("is-completing");
                visibleTool = "";
                toolHideTimer = null;
            }, 320);
        } else {
            container.hidden = true;
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
