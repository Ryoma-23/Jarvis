(function initializeJarvisStatusBar(global) {
    "use strict";

    const jarvisUI = global.JarvisUI;

    if (!jarvisUI || !jarvisUI.state || !jarvisUI.dom) {
        throw new Error("Jarvis UI status dependencies are unavailable.");
    }

    const connectionLabels = Object.freeze({
        connected: "LOCAL / ONLINE",
        connecting: "LOCAL / CONNECTING",
        disconnected: "LOCAL / OFFLINE",
        error: "LOCAL / ERROR"
    });

    const microphoneLabels = Object.freeze({
        connected: "ACTIVE",
        connecting: "STARTING",
        disconnected: "STANDBY",
        error: "UNAVAILABLE"
    });

    function render(state) {
        const statusBar = jarvisUI.dom.elements.statusBar;

        if (!statusBar) {
            return;
        }

        statusBar.dataset.connectionStatus = state.connectionStatus;
        statusBar.setAttribute(
            "aria-label",
            `Realtime: ${state.statusMessage}`
        );

        const connectionElement = statusBar.querySelector(
            "[data-status=connection]"
        );
        if (connectionElement) {
            connectionElement.textContent = state.statusMessage;
        }

        const microphoneElement = statusBar.querySelector(
            "[data-status=microphone]"
        );
        if (microphoneElement) {
            microphoneElement.textContent = (
                microphoneLabels[state.connectionStatus] || "STANDBY"
            );
        }

        const headerStatus = jarvisUI.dom.elements.headerConnectionStatus;
        if (headerStatus) {
            headerStatus.dataset.connectionStatus = state.connectionStatus;

            const headerLabel = headerStatus.querySelector(
                "[data-status=header-connection]"
            );
            if (headerLabel) {
                headerLabel.textContent = (
                    connectionLabels[state.connectionStatus] ||
                    connectionLabels.disconnected
                );
            }
        }
    }

    jarvisUI.state.subscribe(render);
    render(jarvisUI.state.getSnapshot());

    jarvisUI.statusBar = Object.freeze({
        render: render
    });
})(window);
