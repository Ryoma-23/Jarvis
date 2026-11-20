const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const flush = () => new Promise(resolve => setImmediate(resolve));
function setup() {
    const checkbox = {checked:false,addEventListener(t,fn){this.change=fn;}}, label={textContent:''};
    const records=[], requests=[]; let lastCapture;
    class Capture {
        constructor(){this.position=48000*4;this.rate=48000;lastCapture=this;}
        async start() {} close(){this.closed=true;} wav(){return 'wav';}
    }
    const c={document:{getElementById:id=>id==='speaker-shadow'?checkbox:label},
        performance:{now:()=>100},AbortSignal:{timeout:()=>null},JarvisSpeakerCapture:{Capture},
        JarvisVoiceDiagnostics:{record:(...args)=>records.push(args)},
        fetch:async(url,options)=>{
            requests.push(url);
            return {ok:true,json:async()=> url.endsWith('/status')?{active:'p',model_available:true}:
                {decision:'owner_candidate',score:.7,compute_ms:30,profile:'p'}};
        }};
    c.window=c;vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/js/audio/speaker-observer.js'),'utf8'),c);
    const begin=()=>c.JarvisSpeakerObserver.observe({type:'input_audio_buffer.speech_started',item_id:'i'},'s');
    const end=()=>c.JarvisSpeakerObserver.observe({type:'input_audio_buffer.speech_stopped',item_id:'i'},'s');
    return {c,checkbox,label,records,requests,begin,end,capture:()=>lastCapture};
}
test('disabled observer never sends audio; enabled observer only calls local comparison',async()=>{
    const {c,checkbox,requests,records,begin,end}=setup();
    c.JarvisSpeakerObserver.connection('s',{});begin();end();await flush();assert.equal(requests.length,0);
    checkbox.checked=true;await checkbox.change();await flush();begin();end();await flush();
    assert.deepEqual(requests,['/speaker/status','/speaker/compare']);
    assert.equal(records[0][0],'speaker_result');assert.equal(records[0][1].value,'owner_candidate');
});
test('in-flight results are ignored after disabling and capture is closed',async()=>{
    const {c,checkbox,records,begin,end,capture}=setup();c.JarvisSpeakerObserver.connection('s',{});
    checkbox.checked=true;await checkbox.change();await flush();
    let release;c.fetch=()=>new Promise(resolve=>{release=resolve;});begin();end();
    c.JarvisSpeakerObserver.off();assert.equal(capture().closed,true);
    release({ok:true,json:async()=>({decision:'owner_candidate',score:.7,compute_ms:30,profile:'p'})});await flush();
    assert.equal(records.length,0);
});
test('busy work is skipped rather than queuing unbounded audio; errors cannot affect conversation',async()=>{
    const {c,checkbox,records,begin,end}=setup();c.JarvisSpeakerObserver.connection('s',{});
    checkbox.checked=true;await checkbox.change();await flush();
    let reject;c.fetch=()=>new Promise((_,r)=>{reject=r;});begin();end();begin();end();
    assert.equal(records[0][1].value,'skipped_busy');reject(Error('offline'));await flush();
    assert.equal(records[1][1].value,'request_failed');
});
test('WAV encoder preserves mono PCM shape and ring refuses missing audio', async()=>{
    const c={Blob,window:null};c.window=c;vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/js/audio/speaker-capture.js'),'utf8'),c);
    const blob=c.JarvisSpeakerCapture.encodeWav(new Float32Array([0,.5,-.5]),16000);
    const view=new DataView(await blob.arrayBuffer());assert.equal(view.getUint16(22,true),1);
    assert.equal(view.getUint32(24,true),16000);assert.equal(view.getUint32(40,true),6);
    const capture=new c.JarvisSpeakerCapture.Capture();assert.throws(()=>capture.wav(),/capture_unavailable/);
});

test('capture construction and cleanup failures remain isolated from voice connection', async()=>{
    const {c,checkbox,records}=setup();
    c.JarvisSpeakerCapture.Capture=class {constructor(){throw Error('capture unavailable');}};
    checkbox.checked=true;await checkbox.change();
    assert.doesNotThrow(()=>c.JarvisSpeakerObserver.connection('s',{}));
    await flush();assert.equal(records[0][1].value,'capture_failed');
    c.JarvisSpeakerCapture.Capture=class {async start(){} close(){throw Error('cleanup');}};
    c.JarvisSpeakerObserver.connection('s',{});await flush();
    assert.doesNotThrow(()=>c.JarvisSpeakerObserver.connection(null,null));
    await flush();
});
