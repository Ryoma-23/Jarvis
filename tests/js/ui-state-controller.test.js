const assert = require("node:assert/strict");
const test = require("node:test");
const path = require("node:path");


function createStateHarness() {
    const listeners = new Set();
    let snapshot = {
        jarvisState: "idle",
        connectionStatus: "disconnected",
        activeTool: null
    };

    function update(patch) {
        const previousState = snapshot;
        snapshot = {
            ...snapshot,
            ...patch
        };
        listeners.forEach(function(listener) {
            listener(snapshot, previousState);
        });
        return snapshot;
    }

    return {
        getSnapshot: function() {
            return snapshot;
        },
        update: update,
        subscribe: function(listener) {
            listeners.add(listener);
        }
    };
}


test("Realtime signals resolve to the expected visual state", function() {
    const state = createStateHarness();
    global.window = {
        JarvisUI: {
            state: state,
            jarvisState: {
                set: function(nextState) {
                    return state.update({
                        jarvisState: nextState
                    });
                }
            }
        }
    };

    require(path.resolve(
        __dirname,
        "../../static/js/ui/ui-state-controller.js"
    ));

    const controller = global.window.JarvisUI.controller;

    state.update({ connectionStatus: "connecting" });
    assert.equal(state.getSnapshot().jarvisState, "connecting");

    state.update({ connectionStatus: "connected" });
    assert.equal(state.getSnapshot().jarvisState, "idle");

    controller.audioStarted();
    assert.equal(state.getSnapshot().jarvisState, "speaking");

    controller.speechStarted();
    assert.equal(state.getSnapshot().jarvisState, "listening");

    controller.speechStopped();
    assert.equal(state.getSnapshot().jarvisState, "speaking");

    controller.audioStopped();
    assert.equal(state.getSnapshot().jarvisState, "thinking");

    controller.responseDone(false);
    assert.equal(state.getSnapshot().jarvisState, "idle");

    controller.toolStarted("memory_search");
    assert.equal(state.getSnapshot().jarvisState, "thinking");
    assert.equal(state.getSnapshot().activeTool, "memory_search");

    controller.toolFinished(false);
    assert.equal(state.getSnapshot().jarvisState, "idle");
    assert.equal(state.getSnapshot().activeTool, null);

    controller.toolStarted("weather");
    controller.toolFinished(true);
    assert.equal(state.getSnapshot().jarvisState, "thinking");

    controller.responseDone(false);
    assert.equal(state.getSnapshot().jarvisState, "idle");

    state.update({ connectionStatus: "error" });
    assert.equal(state.getSnapshot().jarvisState, "error");

    controller.speechStarted();
    assert.equal(state.getSnapshot().jarvisState, "error");

    state.update({ connectionStatus: "disconnected" });
    assert.equal(state.getSnapshot().jarvisState, "idle");
});
