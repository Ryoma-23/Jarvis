const test=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup(){
    const nodes=new Map(),notifications=[],requests=[];
    const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',handlers:{},children:[],
        addEventListener(t,f){this.handlers[t]=f;},replaceChildren(){this.children=[];this.value='';},
        append(e){this.children.push(e);if(!this.value)this.value=e.value;}});return nodes.get(id);};
    const track={stopped:false,stop(){this.stopped=true;}};
    const c={document:{getElementById:node,createElement:()=>({})},
        activeRealtimeLifecycle:null,isRealtimeConnecting:false,isRealtimeConnected:false,
        REALTIME_MEDIA_AUDIO_CONSTRAINTS:{},TRAY_REALTIME_BRIDGE_URL:'http://127.0.0.1:8767',
        crypto:{randomUUID:()=> 'enrollment-session'},AbortSignal:{timeout:()=>null},
        setTimeout:()=>1,clearTimeout(){},addEventListener(){},confirm:()=>true,
        navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[track]})}},
        notifyTrayRealtime:async(type,payload)=>notifications.push([type,payload.session_id]),
        notifyTrayRealtimeFinished:async(reason,id)=>notifications.push(['finished',id]),
        JarvisSpeakerObserver:{off(){}},
        JarvisSpeakerCapture:{Capture:class{async start(){} close(){} wav(){return 'wav';}}},
        fetch:async(url,options)=>{requests.push([url,options]);return {ok:true,json:async()=>({model_available:true,
            active:null,profiles:[{id:'profile',created_at:'2026-11-20',samples:0,prompts:[]}]})};}};
    c.window=c;vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/js/audio/speaker-enrollment.js'),'utf8'),c);
    return {c,track,notifications,requests,node,click:id=>node(id).handlers.click()};
}
test('enrollment borrows and releases mic and uploads only to local enrollment route',async()=>{
    const {c,track,notifications,requests,click}=setup();await flush();
    assert.equal(c.JarvisLocalCapture.busy(),false);
    click('speaker-record');await flush();assert.equal(c.JarvisLocalCapture.busy(),true);
    assert.deepEqual(notifications.map(n=>n[0]),['starting','started']);
    click('speaker-stop');await flush();
    assert.equal(track.stopped,true);assert.equal(c.JarvisLocalCapture.busy(),false);
    assert.equal(notifications.at(-1)[0],'finished');
    assert.equal(requests.filter(([url,options])=>options.body).length,1);
    assert.ok(requests.every(([url])=>url.startsWith('/speaker/')));
});
test('cannot record while realtime is active and cancellation never uploads audio',async()=>{
    const {c,requests,notifications,click}=setup();await flush();
    c.isRealtimeConnected=true;click('speaker-record');await flush();assert.equal(notifications.length,0);
    c.isRealtimeConnected=false;click('speaker-record');await flush();click('speaker-cancel');await flush();
    assert.equal(requests.filter(([,o])=>o.body).length,0);
});
test('microphone acquisition failure releases tray reservation',async()=>{
    const {c,notifications,click}=setup();await flush();
    c.navigator.mediaDevices.getUserMedia=async()=>{throw Error('denied');};
    click('speaker-record');await flush();
    assert.deepEqual(notifications.map(n=>n[0]),['starting','finished']);
    assert.equal(c.JarvisLocalCapture.busy(),false);
});
