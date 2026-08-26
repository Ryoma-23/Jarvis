(function initializeJarvisStatusBar(global) {
    "use strict";

    const jarvisUI = global.JarvisUI;

    if (!jarvisUI || !jarvisUI.state || !jarvisUI.dom) {
        throw new Error("Jarvis UI status dependencies are unavailable.");
    }

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
    }

    jarvisUI.state.subscribe(render);
    render(jarvisUI.state.getSnapshot());

    jarvisUI.statusBar = Object.freeze({
        render: render
    });
})(window);
