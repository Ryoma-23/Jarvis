const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function setup() {
    const elements = new Map(), saves = [], timers = [];
    const element = id => {
        if (!elements.has(id)) elements.set(id, {disabled: false, checked: false, value: 'quiet', textContent: '',
            handlers: {}, addEventListener(type, fn) {this.handlers[type] = fn;}, querySelectorAll: () => marks});
        return elements.get(id);
    };
    const marks = ['heard','missed','false_response','unknown'].map(value => {
        const e = element(value); e.dataset = {diagnosticMark: value}; return e;
    });
    let time = 0;
    const c = {document: {getElementById: element}, crypto: {randomUUID: () => 'diagnostic-id'},
        performance: {now: () => time++}, Date, AbortSignal: {timeout: () => undefined},
        setInterval: fn => {timers.push(fn); return timers.length;}, clearInterval() {},
        addEventListener() {}, fetch: async (url, options) => {saves.push(JSON.parse(options.body)); return {ok:true,json:async()=>({file:'local.json'})};}};
    c.window = c; vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/js/audio/voice-diagnostics.js'),'utf8'),c);
    const click = id => element(id).handlers.click();
    return {c, element, saves, click, timers};
}
const flush = () => new Promise(resolve => setImmediate(resolve));
test('disabled by default, transcript opt-in, delayed events retain original trial', async () => {
    const {c,click,saves} = setup();
    c.JarvisVoiceDiagnostics.observe({type:'input_audio_buffer.speech_started',item_id:'ignored'},'s');
    assert.equal(saves.length,0);
    click('diagnostic-start'); await flush(); click('diagnostic-trial');
    c.JarvisVoiceDiagnostics.observe({type:'input_audio_buffer.speech_started',item_id:'i'},'s');
    click('diagnostic-trial');
    c.JarvisVoiceDiagnostics.observe({type:'conversation.item.input_audio_transcription.completed',item_id:'i',transcript:'private'},'s');
    click('diagnostic-stop'); await flush();
    const snapshot=saves.at(-1), transcript=snapshot.events.find(e=>e.kind==='transcript');
    assert.equal(snapshot.complete,true); assert.equal(transcript.trial,1);
    assert.equal(transcript.chars,7); assert.equal(transcript.transcript,undefined);
});
test('opt-in stores only bounded user transcript, never error body', async () => {
    const {c,click,element,saves}=setup(); element('diagnostic-transcript').checked=true;
    click('diagnostic-start'); await flush();
    c.JarvisVoiceDiagnostics.observe({type:'conversation.item.input_audio_transcription.completed',item_id:'i',transcript:'元気？'},'s');
    c.JarvisVoiceDiagnostics.observe({type:'error',error:{message:'secret'}},'s');
    click('diagnostic-stop'); await flush();
    assert.equal(saves.at(-1).events.find(e=>e.kind==='transcript').transcript,'元気？');
    assert.equal(JSON.stringify(saves).includes('secret'),false);
});
test('save failure retains snapshot for manual retry and prevents replacement', async () => {
    const {c,click,element,saves}=setup(); click('diagnostic-start'); await flush();
    const workingFetch=c.fetch; c.fetch=async()=>{throw Error('offline');};
    click('diagnostic-stop'); await flush();
    assert.match(element('diagnostic-status').textContent,/失敗/);
    assert.equal(element('diagnostic-start').disabled,true);
    c.fetch=workingFetch; click('diagnostic-stop'); await flush();
    assert.equal(saves.at(-1).complete,true); assert.equal(element('diagnostic-start').disabled,false);
});
test('microphone observer failure cannot break voice lifecycle', async () => {
    const {c,click}=setup(); click('diagnostic-start'); await flush();
    assert.doesNotThrow(()=>c.JarvisVoiceDiagnostics.microphone({getAudioTracks(){throw Error('gone');}}));
});
test('stop during an autosave persists the final snapshot after it completes', async () => {
    const {c,click,saves,element}=setup();
    let release;
    c.fetch=async (url,options)=>{
        saves.push(JSON.parse(options.body));
        if(saves.length===1) await new Promise(resolve=>{release=resolve;});
        return {ok:true,json:async()=>({file:'local.json'})};
    };
    click('diagnostic-start'); click('diagnostic-trial'); click('diagnostic-stop');
    assert.equal(element('diagnostic-start').disabled,true);
    release(); await flush();
    assert.equal(saves.length,2); assert.equal(saves[1].complete,true);
    assert.equal(element('diagnostic-start').disabled,false);
});
test('manual result can target an earlier trial and speaker observations retain its session', async () => {
    const {c,click,element,saves}=setup();click('diagnostic-start');await flush();
    click('diagnostic-trial');
    c.JarvisVoiceDiagnostics.observe({type:'input_audio_buffer.speech_started',item_id:'i'},'old');
    click('diagnostic-trial');element('diagnostic-result-trial').value='1';click('heard');
    c.JarvisVoiceDiagnostics.connection('new',null);
    c.JarvisVoiceDiagnostics.record('speaker_result',{session:'old',item:'i',value:'uncertain',score:.4});
    click('diagnostic-stop');await flush();
    assert.equal(saves.at(-1).events.find(e=>e.kind==='mark').trial,1);
    assert.equal(saves.at(-1).events.find(e=>e.kind==='speaker_result').trial,1);
});
