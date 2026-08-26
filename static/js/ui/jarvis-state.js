(function initializeJarvisStateView(global, document) {
    "use strict";

    const jarvisUI = global.JarvisUI;

    if (!jarvisUI || !jarvisUI.state || !jarvisUI.dom) {
        throw new Error("Jarvis UI state dependencies are unavailable.");
    }

    const validStates = new Set([
        "idle",
        "connecting",
        "listening",
        "thinking",
        "speaking",
        "error"
    ]);
    const stateCaptions = Object.freeze({
        idle: "Awaiting instruction",
        connecting: "Establishing secure channel",
        listening: "Receiving voice input",
        thinking: "Processing request",
        speaking: "Voice response active",
        error: "Attention required"
    });

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

        const coreCaption = jarvisUI.dom.elements.coreCaption;
        if (coreCaption) {
            coreCaption.textContent = stateCaptions[state.jarvisState];
        }
    }

    jarvisUI.state.subscribe(render);
    render(jarvisUI.state.getSnapshot());

    jarvisUI.jarvisState = Object.freeze({
        set: setJarvisState
    });
})(window, document);
