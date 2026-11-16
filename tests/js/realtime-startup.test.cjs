const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../static/script.js'), 'utf8');
function setup({status = 200, body = {}, microphoneError = null} = {}) {
    const finished = [], calls = [];
    const track = {enabled: true};
    const c = {
        console: {log() {}, error() {}},
        isRealtimeConnected: false, isRealtimeConnecting: false,
        activeRealtimeLifecycle: null, activeConversationId: 'conversation',
        resetRealtimeBargeInState() {}, resetRealtimeConversationTracking() {},
        resetRealtimeIdleState() {}, updateVoiceStatus() {}, updateVoiceButtons() {},
        notifyTrayRealtime: async () => {}, normalizeRealtimeId: v => v,
        document: {createElement: () => ({})},
        window: {JarvisUI: {audioReactive: {attachInput() {}}}},
        navigator: {mediaDevices: {getUserMedia: async () => {
            if (microphoneError) throw microphoneError;
            return {getTracks: () => [track]};
        }}},
        REALTIME_MEDIA_AUDIO_CONSTRAINTS: {},
        RTCPeerConnection: class {
            addTrack() {} createDataChannel() { return {}; }
            async createOffer() { return {sdp: 'test-offer'}; }
            async setLocalDescription() {} async setRemoteDescription() {}
        },
        fetch: async url => {
            calls.push(url);
            return url.startsWith('/realtime/token')
                ? {ok: true, json: async () => ({value: 'test-secret', conversation_id: 'conversation'})}
                : {ok: status === 200, status, json: async () => body, text: async () => 'test-answer'};
        },
        finishRealtimeVoice: async (...args) => {finished.push(args);},
    };
    vm.createContext(c);
    vm.runInContext(source.slice(source.indexOf('async function startRealtimeVoice('),
        source.indexOf('async function initializeRealtimeDataChannel(')), c);
    return {c, calls, finished, track};
}
test('successful startup keeps microphone disabled until history restoration', async () => {
    const {c, finished, track} = setup();
    assert.equal(await c.startRealtimeVoice('wakeword', 'session'), true);
    assert.equal(c.isRealtimeConnected, true);
    assert.equal(track.enabled, false);
    assert.equal(finished.length, 0);
});
test('microphone failure identifies stage and never sends SDP', async () => {
    const {c, calls, finished} = setup({microphoneError: {name: 'NotReadableError'}});
    assert.equal(await c.startRealtimeVoice('wakeword', 'session'), false);
    assert.equal(calls.length, 1);
    assert.equal(finished[0][0], 'startup_failed:microphone:NotReadableError');
});
for (const [type, category] of [['insufficient_quota', 'quota'], ['rate_limit_error', 'rate_limit']]) {
    test(`SDP 429 ${type} is classified without exposing server message`, async () => {
        const {c, calls, finished} = setup({status: 429, body: {error: {type, message: 'private-data'}}});
        assert.equal(await c.startRealtimeVoice('wakeword', 'session'), false);
        assert.equal(calls.length, 2);
        assert.equal(finished[0][0], `startup_failed:sdp:HTTP_429:${category}`);
        assert.equal(JSON.stringify(finished).includes('private-data'), false);
        assert.match(finished[0][3], /429/);
    });
}
test('unknown 429 body preserves status without assuming quota or retrying', async () => {
    const {c, calls, finished} = setup({status: 429, body: null});
    await c.startRealtimeVoice('wakeword', 'session');
    assert.equal(calls.length, 2);
    assert.equal(finished[0][0], 'startup_failed:sdp:HTTP_429');
});
test('diagnostics whitelist stages and exception names', () => {
    const {c} = setup();
    const result = c.describeRealtimeStartupFailure('secret', {name: 'private', message: 'private'}, null, 'secret');
    assert.equal(result.code, 'unknown:Error');
    assert.equal(JSON.stringify(result).includes('private'), false);
});
