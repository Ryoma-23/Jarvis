const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../static/script.js'), 'utf8');
function part(start, end) { return source.slice(source.indexOf(start), source.indexOf(end)); }
function setup(sourceName = 'wakeword') {
    const sent = [];
    const lifecycle = {source: sourceName, historyRestoring: true};
    const channel = {readyState: 'open', send: value => sent.push(JSON.parse(value))};
    const stream = {};
    const c = {
        console, dataChannel: channel, localStream: stream,
        getRealtimeLifecycle: id => id === 'current' ? lifecycle : null,
        isCurrentRealtimeSession: id => id === 'current',
        realtimePendingResponseRequestCount: 0,
        pendingRealtimeTextResponseTurn: null,
        pauseRealtimeIdleTimer() {}, scheduleRealtimeIdleTimeout() {},
        updateVoiceStatus() {}, markRealtimeConversationActivity() {},
        processRealtimeTextInputQueue() {}, notifyTrayRealtimeStarted: async () => {},
        setRealtimeMicrophoneEnabled() {}, finishRealtimeVoice: async () => {},
        REALTIME_INPUT_NOISE_REDUCTION_TYPE: 'near_field',
        REALTIME_SERVER_VAD_THRESHOLD: 0.5,
        REALTIME_SERVER_VAD_SILENCE_DURATION_MS: 500,
        restoreRealtimeConversationHistory: async () => {}
    };
    vm.createContext(c);
    vm.runInContext(part('function requestRealtimeWakeGreeting(', 'function finishRealtimeOutputAudio('), c);
    vm.runInContext(part('async function initializeRealtimeDataChannel(', 'async function restoreRealtimeConversationHistory('), c);
    return {c, sent, lifecycle, channel, stream};
}
test('wake greeting waits for history and is sent only once', async () => {
    const {c, sent, lifecycle, channel, stream} = setup();
    let release;
    c.restoreRealtimeConversationHistory = () => new Promise(resolve => { release = resolve; });
    const pending = c.initializeRealtimeDataChannel(channel, stream, 'current', 'conversation');
    assert.equal(sent.filter(e => e.type === 'response.create').length, 0);
    release();
    assert.equal(await pending, true);
    assert.equal(c.requestRealtimeWakeGreeting('current'), false);
    const responses = sent.filter(e => e.type === 'response.create');
    assert.equal(responses.length, 1);
    assert.equal(Object.hasOwn(responses[0].response, 'instructions'), false);
    const greetingItems = sent.filter(e => e.type === 'conversation.item.create');
    assert.deepEqual(greetingItems, [{
        type: 'conversation.item.create',
        item: {type: 'message', role: 'user', content: [{type: 'input_text', text: 'Hey Jarvis'}]}
    }]);
    assert.ok(sent.indexOf(greetingItems[0]) < sent.indexOf(responses[0]));
    assert.equal(responses[0].response.tool_choice, 'none');
    assert.equal(c.realtimePendingResponseRequestCount, 1);
    assert.equal(lifecycle.wakeGreetingRequested, true);
});
test('manual startup and stale or finishing sessions do not greet', async () => {
    const {c, sent, lifecycle, channel, stream} = setup('manual');
    await c.initializeRealtimeDataChannel(channel, stream, 'current', 'conversation');
    lifecycle.source = 'wakeword';
    assert.equal(c.requestRealtimeWakeGreeting('stale'), false);
    lifecycle.finishing = true;
    assert.equal(c.requestRealtimeWakeGreeting('current'), false);
    assert.equal(sent.filter(e => e.type === 'response.create').length, 0);
});
test('failed restoration does not greet', async () => {
    const {c, sent, channel, stream} = setup();
    c.restoreRealtimeConversationHistory = async () => { throw Error('restore failed'); };
    assert.equal(await c.initializeRealtimeDataChannel(channel, stream, 'current', 'conversation'), false);
    assert.equal(sent.filter(e => e.type === 'response.create').length, 0);
});
test('ordinary response remains unchanged and failed greeting send clears pending count', () => {
    const {c, sent, lifecycle, channel} = setup();
    assert.equal(c.requestRealtimeResponse('current'), true);
    assert.deepEqual(sent, [{type: 'response.create'}]);
    c.realtimePendingResponseRequestCount = 0;
    lifecycle.historyRestoring = false;
    channel.send = () => { throw Error('closed'); };
    assert.equal(c.requestRealtimeWakeGreeting('current'), false);
    assert.equal(c.realtimePendingResponseRequestCount, 0);
    assert.equal(c.requestRealtimeWakeGreeting('current'), false);
});
