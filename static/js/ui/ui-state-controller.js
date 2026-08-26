(function initializeJarvisUiStateController(global) {
    "use strict";

    const jarvisUI = global.JarvisUI;

    if (!jarvisUI || !jarvisUI.state || !jarvisUI.jarvisState) {
        throw new Error("Jarvis UI state controller dependencies are unavailable.");
    }

    const signals = {
        connectionStatus: jarvisUI.state.getSnapshot().connectionStatus,
        listening: false,
        thinking: false,
        speaking: false,
        toolDepth: 0
    };

    function resolveState() {
        if (signals.connectionStatus === "error") {
            return "error";
        }
        if (signals.listening) {
            return "listening";
        }
        if (signals.speaking) {
            return "speaking";
        }
        if (signals.thinking || signals.toolDepth > 0) {
            return "thinking";
        }
        if (signals.connectionStatus === "connecting") {
            return "connecting";
        }
        return "idle";
    }

    function render() {
        const nextState = resolveState();
        const currentState = jarvisUI.state.getSnapshot().jarvisState;

        if (nextState !== currentState) {
            jarvisUI.jarvisState.set(nextState);
        }

        return nextState;
    }

    function resetActivity() {
        signals.listening = false;
        signals.thinking = false;
        signals.speaking = false;
        signals.toolDepth = 0;
    }

    function speechStarted() {
        signals.listening = true;
        signals.thinking = false;
        render();
    }

    function speechStopped() {
        signals.listening = false;
        signals.thinking = true;
        render();
    }

    function speechFailed() {
        signals.listening = false;
        signals.thinking = false;
        render();
    }

    function responseCreated() {
        signals.thinking = true;
        render();
    }

    function responseDone(continuesWithTool = false) {
        signals.thinking = Boolean(continuesWithTool) || signals.toolDepth > 0;
        render();
    }

    function audioStarted() {
        signals.speaking = true;
        signals.thinking = false;
        render();
    }

    function audioStopped() {
        signals.speaking = false;
        render();
    }

    function toolStarted(toolName) {
        signals.toolDepth += 1;
        signals.thinking = true;
        jarvisUI.state.update({
            activeTool: String(toolName || "tool")
        });
        render();
    }

    function toolFinished(continuesWithResponse = false) {
        signals.toolDepth = Math.max(0, signals.toolDepth - 1);

        if (signals.toolDepth === 0) {
            jarvisUI.state.update({
                activeTool: null
            });
        }

        signals.thinking = (
            Boolean(continuesWithResponse) ||
            signals.toolDepth > 0
        );
        render();
    }

    function reset() {
        resetActivity();
        jarvisUI.state.update({
            activeTool: null
        });
        render();
    }

    jarvisUI.state.subscribe(function(state, previousState) {
        if (state.connectionStatus === previousState.connectionStatus) {
            return;
        }

        signals.connectionStatus = state.connectionStatus;

        if (
            state.connectionStatus === "connecting" ||
            state.connectionStatus === "disconnected" ||
            state.connectionStatus === "error"
        ) {
            resetActivity();
        }

        render();
    });

    jarvisUI.controller = Object.freeze({
        speechStarted: speechStarted,
        speechStopped: speechStopped,
        speechFailed: speechFailed,
        responseCreated: responseCreated,
        responseDone: responseDone,
        audioStarted: audioStarted,
        audioStopped: audioStopped,
        toolStarted: toolStarted,
        toolFinished: toolFinished,
        reset: reset
    });

    render();
})(window);
