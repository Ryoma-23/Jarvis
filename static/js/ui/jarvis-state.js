(function initializeJarvisStateView(global, document) {
    "use strict";

    const jarvisUI = global.JarvisUI;

    if (!jarvisUI || !jarvisUI.state || !jarvisUI.dom) {
        throw new Error("Jarvis UI state dependencies are unavailable.");
    }

    const validStates = new Set([
        "idle",
        "listening",
        "thinking",
        "speaking",
        "error"
    ]);

    function setJarvisState(nextState) {
        const normalizedState = String(nextState || "").toLowerCase();

        if (!validStates.has(normalizedState)) {
            console.warn("Unknown Jarvis UI state:", nextState);
            return jarvisUI.state.getSnapshot();
        }

        return jarvisUI.state.update({
            jarvisState: normalizedState
        });
    }

    function render(state) {
        document.body.dataset.jarvisState = state.jarvisState;

        const coreState = jarvisUI.dom.elements.coreState;
        if (coreState) {
            coreState.textContent = state.jarvisState.toUpperCase();
        }
    }

    jarvisUI.state.subscribe(render);
    render(jarvisUI.state.getSnapshot());

    jarvisUI.jarvisState = Object.freeze({
        set: setJarvisState
    });
})(window, document);
