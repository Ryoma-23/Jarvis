(function initializeJarvisAppState(global) {
    "use strict";

    const listeners = new Set();
    let state = Object.freeze({
        jarvisState: "idle",
        connectionStatus: "disconnected",
        statusMessage: "未接続",
        activeTool: null,
        latencyMs: null
    });

    function getSnapshot() {
        return state;
    }

    function update(patch) {
        if (!patch || typeof patch !== "object") {
            return state;
        }

        const previousState = state;
        state = Object.freeze({
            ...state,
            ...patch
        });

        listeners.forEach(function(listener) {
            try {
                listener(state, previousState);
            } catch (error) {
                console.error("Jarvis UI state listener failed:", error);
            }
        });

        return state;
    }

    function subscribe(listener) {
        if (typeof listener !== "function") {
            return function noop() {};
        }

        listeners.add(listener);

        return function unsubscribe() {
            listeners.delete(listener);
        };
    }

    const jarvisUI = global.JarvisUI || {};
    jarvisUI.state = Object.freeze({
        getSnapshot: getSnapshot,
        update: update,
        subscribe: subscribe
    });
    global.JarvisUI = jarvisUI;
})(window);
