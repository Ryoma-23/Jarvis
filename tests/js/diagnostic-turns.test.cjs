const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function element() { return {children:[], textContent:'', appendChild(e){this.children.push(e);},
    replaceChildren(){this.children=[];}, setAttribute(){}, addEventListener(t,f){this[t]=f;}}; }
test('turn labels use session and item, can be revised, and stop/reset disable old rows',()=>{
    const list=element(), labels=[]; const c={document:{getElementById:()=>list,createElement:element}};c.window=c;
    vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/js/audio/diagnostic-turns.js'),'utf8'),c);
    const ui=c.JarvisDiagnosticTurns;ui.reset((...a)=>labels.push(a));ui.setActive(true);
    ui.update({kind:'speech_start',session:'a',item:'i',ms:1000,trial:1,scenario:'quiet'});
    ui.update({kind:'speech_start',session:'b',item:'i',ms:2000,trial:2,scenario:'video_only'});
    assert.equal(list.children.length,2);
    const select=list.children[0].children[2];select.value='owner';select.change();select.value='video';select.change();
    assert.deepEqual(labels,[['a','i','owner'],['a','i','video']]);
    ui.update({kind:'speaker_result',session:'b',item:'i',value:'insufficient',reason:'clipped_audio',energy_s:1});
    assert.match(list.children[1].children[1].textContent,/音割れ/);
    assert.doesNotMatch(list.children[0].children[1].textContent,/音割れ/);
    ui.setActive(false);select.change();assert.equal(labels.length,2);assert.equal(select.disabled,true);
    ui.reset(()=>{});assert.equal(list.children.length,0);
});
