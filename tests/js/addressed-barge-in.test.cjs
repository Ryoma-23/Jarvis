const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../static/script.js'), 'utf8');
function part(start, end) { return source.slice(source.indexOf(start), source.indexOf(end)); }
function setup() {
    const sent = [], actions = [];
    const turn = {startedWhileOutputPlaying: true, guardDurationMet: true};
    const c = {
        console, dataChannel: {readyState: 'open', send: text => sent.push(JSON.parse(text))},
        realtimeRejectedBargeInItemIds: new Set(), realtimeUserMessagesByItemId: new Map(),
        isCurrentRealtimeSession: id => id === 'current', isRestoredRealtimeItem: () => false,
        normalizeRealtimeId: id => id || null, getRealtimeSpeechTurn: () => turn,
        discardRealtimeSpeechTurn: () => { c.getRealtimeSpeechTurn = () => null; },
        isRealtimeOutputAudioPlaying: true, activeConversationId: 'conversation',
        updateVoiceStatus: (...args) => actions.push(['status', ...args]),
        processRealtimeTextInputQueue() {}, scheduleRealtimeIdleTimeout() {},
        markRealtimeConversationActivity() {},
        interruptRealtimeResponse: () => actions.push(['interrupt']),
        requestRealtimeResponse: () => actions.push(['response']),
        renderConversationMessage: data => { actions.push(['render', data]); return {}; },
        saveRealtimeConversationMessage: async data => { actions.push(['save', data]); return {}; },
        applyPersistedRealtimeMessage() {}, updateMessageContent() {},
        window: {JarvisUI: {systemLog: {append: message => actions.push(['log', message])}, controller: {
            speechStarted: () => actions.push(['listening']),
            speechStopped: () => actions.push(['thinking']),
            speechFailed: () => actions.push(['idle'])
        }}},
        pauseRealtimeIdleTimer() {}, startRealtimeSpeechTurn: () => turn,
        stopRealtimeSpeechTurn: () => turn, startRealtimeBargeInGuard() {}, clearRealtimeBargeInTimer() {}
    };
    vm.createContext(c);
    vm.runInContext(part('const REALTIME_BARGE_IN_GUARD_MS', 'const {\n    sendButton'), c);
    vm.runInContext(part('function isMeaningfulRealtimeUserTranscript(', 'function requestRealtimeWakeGreeting('), c);
    vm.runInContext(part('async function handleRealtimeUserTranscriptionCompleted(', 'function handleRealtimeAssistantTranscriptDelta('), c);
    vm.runInContext('function speechEvent(data, sessionId) {' + part(
        '    if (data.type === "input_audio_buffer.speech_started")',
        '    if (data.type === "response.done")') + '}', c);
    const failedMarker = source.indexOf('"conversation.item.input_audio_transcription.failed"');
    vm.runInContext('function failedEvent(data, sessionId) {' + source.slice(
        source.lastIndexOf('    if (', failedMarker),
        source.indexOf('    if (data.type === "response.output_audio_transcript.delta")', failedMarker)
    ) + '}', c);
    return {c, sent, actions, turn};
}

test('only explicitly addressed interruptions pass the name check', () => {
    const {c} = setup();
    for (const text of ['Jarvis, stop', 'Hey Jarvis!', 'ジャービス、止めて', 'ジャービス止めて', 'ジャーヴィス、待って', 'ねえ、ジャービス', 'じゃーびす、天気は？', '「ジャービス」、止めて', ' Ｊａｒｖｉｓ、天気は？']) {
        assert.equal(c.isMeaningfulRealtimeUserTranscript(text, true), true, text);
    }
    for (const text of ['チャンネル登録お願いします', '次のニュースです', '止めて', 'これはJarvisの紹介です', 'Jarvison says hello']) {
        assert.equal(c.isMeaningfulRealtimeUserTranscript(text, true), false, text);
    }
    assert.equal(c.isMeaningfulRealtimeUserTranscript('明日の天気は？', false), true);
    assert.equal(c.isMeaningfulRealtimeUserTranscript('ジャービス、明日の天気は？', false), true);
});

test('video dialogue does not interrupt, respond or persist; rejected item is removed once', async () => {
    const {c, sent, actions} = setup();
    const data = {item_id: 'video', transcript: '次のニュースです'};
    await c.handleRealtimeUserTranscriptionCompleted(data, 'current');
    await c.handleRealtimeUserTranscriptionCompleted(data, 'current');
    assert.deepEqual(sent, [{type: 'conversation.item.delete', item_id: 'video'}]);
    assert.equal(actions.some(a => ['interrupt', 'response', 'save', 'render'].includes(a[0])), false);
});

test('addressed sustained interruption cancels then responds and persists', async () => {
    const {c, actions} = setup();
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'user', transcript: 'ジャービス、止めて'}, 'current');
    assert.deepEqual(actions.filter(a => ['interrupt', 'response', 'save'].includes(a[0])).map(a => a[0]), ['interrupt', 'response', 'save']);
});

test('short or stale addressed speech does not interrupt', async () => {
    const {c, actions, sent, turn} = setup();
    turn.guardDurationMet = false;
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'short', transcript: 'Jarvis'}, 'current');
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'old', transcript: 'Jarvis'}, 'stale');
    assert.equal(actions.some(a => a[0] === 'interrupt'), false);
    assert.equal(sent.length, 1);
});

test('ordinary listening accepts explicitly addressed follow-up', async () => {
    const {c, actions, turn} = setup();
    turn.startedWhileOutputPlaying = false;
    c.isRealtimeOutputAudioPlaying = false;
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'user', transcript: 'ジャービス、明日は？'}, 'current');
    assert.equal(actions.some(a => a[0] === 'response'), true);
    assert.equal(actions.some(a => a[0] === 'save'), true);
    assert.equal(actions.some(a => a[0] === 'interrupt'), false);
});

test('listening non-speech is rejected before any response and never persisted', async () => {
    const {c, sent, actions, turn} = setup();
    turn.startedWhileOutputPlaying = false;
    c.isRealtimeOutputAudioPlaying = false;
    c.speechEvent({type: 'input_audio_buffer.speech_started'}, 'current');
    c.speechEvent({type: 'input_audio_buffer.speech_stopped'}, 'current');
    assert.equal(actions.some(a => a[0] === 'response'), false);
    const data = {item_id: 'background', transcript: '雑音'};
    await c.handleRealtimeUserTranscriptionCompleted(data, 'current');
    await c.handleRealtimeUserTranscriptionCompleted(data, 'current');
    assert.equal(actions.some(a => ['response', 'save', 'render', 'interrupt'].includes(a[0])), false);
    assert.equal(actions.some(a => a[0] === 'idle'), true);
    assert.deepEqual(sent, [{type: 'conversation.item.delete', item_id: 'background'}]);
});

test('addressed listening turn responds only after transcript validation', async () => {
    const {c, actions, turn} = setup();
    turn.startedWhileOutputPlaying = false;
    c.isRealtimeOutputAudioPlaying = false;
    c.speechEvent({type: 'input_audio_buffer.speech_stopped'}, 'current');
    assert.equal(actions.some(a => a[0] === 'response'), false);
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'user', transcript: 'Jarvis, what time is it?'}, 'current');
    assert.equal(actions.filter(a => a[0] === 'response').length, 1);
});

test('missing speech-start metadata cannot bypass playback guard', async () => {
    const {c, actions, sent} = setup();
    c.getRealtimeSpeechTurn = () => null;
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'late', transcript: 'Jarvis, stop'}, 'current');
    assert.equal(actions.some(a => ['response', 'interrupt', 'save'].includes(a[0])), false);
    assert.equal(sent[0].type, 'conversation.item.delete');
});

test('failed transcription is removed without starting a response', () => {
    const {c, sent, actions} = setup();
    c.console = {warn() {}};
    c.failedEvent({type: 'conversation.item.input_audio_transcription.failed', item_id: 'failed'}, 'current');
    assert.deepEqual(sent, [{type: 'conversation.item.delete', item_id: 'failed'}]);
    assert.equal(c.realtimeRejectedBargeInItemIds.has('failed'), true);
    assert.equal(actions.some(a => ['response', 'save', 'interrupt'].includes(a[0])), false);
});

test('speech candidates do not change speaking display to listening or thinking', () => {
    const {c, actions} = setup();
    c.speechEvent({type: 'input_audio_buffer.speech_started'}, 'current');
    c.speechEvent({type: 'input_audio_buffer.speech_stopped'}, 'current');
    assert.equal(actions.some(a => ['listening', 'thinking', 'status', 'response'].includes(a[0])), false);
});

test('normal completed speech is not rejected when playback starts before transcription arrives', async () => {
    const {c, actions, turn} = setup();
    turn.startedWhileOutputPlaying = false;
    turn.guardDurationMet = false;
    // Output started after this user turn ended; this is not a short barge-in.
    c.isRealtimeOutputAudioPlaying = true;
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'normal', transcript: 'ジャービス、天気は？'}, 'current');
    assert.equal(actions.some(a => a[0] === 'response'), true);
    assert.equal(actions.some(a => a[0] === 'save'), true);
    assert.equal(actions.some(a => a[0] === 'interrupt'), false);
});

test('rejection feedback distinguishes missing address, empty transcription and short interruption', () => {
    const {c} = setup();
    assert.match(c.explainRealtimeVoiceRejection('x', '明日は？', true, true), /呼びかけ/);
    assert.match(c.explainRealtimeVoiceRejection('x', '', false, false), /文字に変換/);
    assert.match(c.explainRealtimeVoiceRejection('x', 'Jarvis', true, false), /割り込みが短い/);
});

test('rejected ordinary noise shows a reason instead of silently returning to connected', async () => {
    const {c, actions, turn} = setup();
    turn.startedWhileOutputPlaying = false;
    c.isRealtimeOutputAudioPlaying = false;
    await c.handleRealtimeUserTranscriptionCompleted({item_id: 'noise', transcript: '雑音'}, 'current');
    assert.equal(actions.some(a => a[0] === 'status' && a[2].includes('発話内容')), true);
    assert.equal(actions.some(a => a[0] === 'log' && a[1].startsWith('VOICE_REJECTED')), true);
});

test('short normal questions work even if ASR drops or changes the name', async () => {
    for (const transcript of ['ジャービス、元気？', '元気？', 'ジャーヴィス、元気?', 'ジャービス、何か100文字ぐらいで物語作って']) {
        const {c, actions, turn} = setup();
        turn.startedWhileOutputPlaying = false;
        turn.guardDurationMet = false;
        c.isRealtimeOutputAudioPlaying = false;
        await c.handleRealtimeUserTranscriptionCompleted({item_id: 'question', transcript}, 'current');
        assert.equal(actions.filter(a => a[0] === 'response').length, 1, transcript);
        assert.equal(actions.filter(a => a[0] === 'save').length, 1, transcript);
    }
});
