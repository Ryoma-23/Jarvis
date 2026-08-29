const assert = require("node:assert/strict");
const test = require("node:test");
const path = require("node:path");

function loadTransitions() {
    global.window = { JarvisUI: {} };
    const modulePath = path.resolve(__dirname, "../../static/js/core/state-transitions.js");
    delete require.cache[modulePath];
    require(modulePath);
    return global.window.JarvisUI.coreStateTransitions;
}

test("state profiles interpolate instead of jumping", function() {
    const transitions = loadTransitions().createStateTransitions("idle");
    transitions.setState("thinking");
    const first = transitions.update(1 / 60, false).profile;
    assert.ok(first.rotationSpeed > 0.10);
    assert.ok(first.rotationSpeed < 0.42);
    for (let index = 0; index < 180; index += 1) transitions.update(1 / 60, false);
    const settled = transitions.update(1 / 60, false).profile;
    assert.ok(Math.abs(settled.rotationSpeed - 0.42) < 0.001);
    assert.ok(Math.abs(settled.attraction - 0.92) < 0.001);
});

test("connecting completion and error are one-shot decaying events", function() {
    const transitions = loadTransitions().createStateTransitions("connecting");
    transitions.setState("idle");
    const stable = transitions.update(1 / 60, false).stabilityWave;
    assert.ok(stable > 0);
    assert.ok(transitions.update(2, false).stabilityWave < stable);
    transitions.setState("error");
    const burst = transitions.update(1 / 60, false).errorBurst;
    assert.ok(burst > 0);
    assert.ok(transitions.update(1, false).errorBurst < burst);
});

test("reduced motion settles immediately and suppresses transient flashes", function() {
    const transitions = loadTransitions().createStateTransitions("idle");
    transitions.setState("speaking");
    const result = transitions.update(1 / 60, true);
    assert.equal(result.profile.audioResponse, 0.92);
    assert.equal(result.profile.outwardWave, 0.88);
    assert.equal(result.stabilityWave, 0);
    assert.equal(result.errorBurst, 0);
});
