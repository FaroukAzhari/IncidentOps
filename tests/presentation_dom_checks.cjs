// DOM contract tests, not a browser/layout emulator. No external dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {results, tree} = JSON.parse(fs.readFileSync(0, 'utf8'));

class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag; this.children = []; this.attrs = attrs; this.handlers = {};
    this.id = attrs.id; this.className = attrs.class || ''; this.dataset = {};
    for (const [k,v] of Object.entries(attrs)) if (k.startsWith('data-')) this.dataset[k.slice(5)] = v;
    this.value = attrs.value || ''; this.hidden = 'hidden' in attrs;
    this.checked = 'checked' in attrs; this.disabled = 'disabled' in attrs;
    this.classList = {
      add: (...items) => {this.className = [...new Set([...this.className.split(' ').filter(Boolean),...items])].join(' ');},
      remove: (...items) => {this.className = this.className.split(' ').filter(x => !items.includes(x)).join(' ');},
      toggle: (name, on) => {on ? this.classList.add(name) : this.classList.remove(name);}
    };
  }
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children = [...children]; this.ownText = '';}
  set textContent(value) {this.children = []; this.ownText = String(value);}
  get textContent() {return (this.ownText || '') + this.children.map(x => x.textContent).join('');}
  all() {return this.children.flatMap(x => [x, ...x.all()]);}
  querySelectorAll(selector) {
    return this.all().filter(e => {
      if (selector.startsWith('.')) return selector.slice(1).split('.').every(c => e.className.split(' ').includes(c));
      const data = /^\[data-node="([^"]+)"\]$/.exec(selector);
      return data ? e.dataset.node === data[1] : e.tagName === selector;
    });
  }
  querySelector(selector) {return this.querySelectorAll(selector)[0] || null;}
  addEventListener(name, handler) {this.handlers[name] = handler;}
  setAttribute(name, value) {this.attrs[name] = value;}
  scrollIntoView() {}
  get elements() {return this.all().filter(e => ['input','select','textarea','button'].includes(e.tagName));}
}
function build(data) {
  const e = new Element(data.tag, data.attrs);
  e.ownText = data.text || '';
  e.append(...data.children.map(build));
  if(e.tagName === 'textarea') e.value = e.textContent;
  return e;
}
const root = build(tree);
globalThis.document = {
  createElement: tag => new Element(tag),
  getElementById: id => root.all().find(e => e.id === id) || null,
  querySelectorAll: selector => root.querySelectorAll(selector),
  querySelector: selector => root.querySelector(selector)
};
globalThis.window = {innerWidth:1200, matchMedia:()=>({matches:false})};
globalThis.setInterval = () => 1;
globalThis.clearInterval = () => {};
// Test replay's ordering without slowing the suite; browser playback uses 800 ms.
globalThis.setTimeout = callback => {callback();return 1;};
const byId = id => document.getElementById(id);
let calls = 0, selected = results[0];
globalThis.fetch = async (url, options) => {
  calls++;
  if(url === '/api/config') return {ok:true,json:async()=>({model:'gemini-3.5-flash-lite',gemini_configured:false,max_retries:2,scenarios:results.map(r=>({id:r.scenario,label:r.scenario}))})};
  if(options) {
    const request = JSON.parse(options.body);
    selected = results.find(r => r.scenario === request.scenario) || results[0];
    const events = [{event:'run_started',mode:selected.mode,thread_id:selected.thread_id,elapsed_ms:0}];
    for(const step of selected.steps) events.push({event:'node_started',node:step.node,elapsed_ms:0},{event:'step_completed',step,elapsed_ms:0});
    events.push({event:'run_completed',result:selected});
    const bytes = new TextEncoder().encode(events.map(e=>JSON.stringify(e)).join('\n')+'\n');
    let position = 0;
    return {ok:true,body:{getReader:()=>({read:async()=>{
      if(position >= bytes.length)return {done:true};
      const value=bytes.slice(position,position+127);position+=127;return {done:false,value};
    },releaseLock(){}})}};
  }
  return {ok:true,json:async()=>selected};
};
for(const name of ['presentation','story','app'])vm.runInThisContext(fs.readFileSync(`incidentops/static/${name}.js`,'utf8'),{filename:name+'.js'});

(async()=>{
  await new Promise(setImmediate); // Finish the configuration request.
  assert.equal(byId('run').disabled,false);
  assert.match(byId('portal-source').textContent,/preview/);
  for(const result of results) {
    byId('scenario').value=result.scenario;
    byId('scenario').handlers.change();
    byId('report').value='Investigate the current observed incident.';
    byId('mode').value='demo';
    byId('auto-replay').checked=true;
    await byId('incident-form').handlers.submit({preventDefault(){}});
    const resolved=result.state.incident_resolved;
    assert.equal(byId('portal-profile').hidden,!resolved,result.scenario);
    assert.equal(byId('cycles-panel').hidden,result.state.retry_count===0);
    assert.equal(byId('timeline').children.length,result.steps.length);
    assert.equal(byId('run').disabled,false);
    assert.match(byId('result-diagnose').textContent,/Confidence/);
    assert.match(byId('comparison').textContent,/Not tested/);
    const before=calls;
    await byId('replay').handlers.click();
    assert.equal(calls,before,'Replay must not call the backend');
    assert.equal(byId('portal-profile').hidden,!resolved);
    assert.equal(byId('timeline').children.length,result.steps.length,'Replay must not duplicate timeline');
    byId('retrieve-thread').value=result.thread_id;
    await byId('retrieve').handlers.click();
    assert.equal(byId('portal-profile').hidden,!resolved);
    assert.equal(byId('timeline').children.length,result.steps.length);
  }
  byId('mode').value='gemini';byId('mode').handlers.change();
  assert.equal(byId('scenario-control').hidden,true);
  assert.equal(byId('portal-profile').hidden,true);
  assert.equal(byId('portal-title').textContent,'Waiting for observations');
  console.log('DOM startup, fragmented streaming, seven outcomes, replay, retrieval, and mode switch passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
