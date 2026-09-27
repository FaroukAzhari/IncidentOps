/* API transport and UI lifecycle. Rendering lives in story.js. */
'use strict';
const $ = id => document.getElementById(id);
const Story = globalThis.IncidentStory;
const P = globalThis.IncidentPresentation;
const names = {monitor:'Monitoring',diagnose:'Diagnostic',recover:'Recovery',verify:'Verification',retry:'Retry',finalize:'Final outcome'};
const descriptions = {
  monitor:'Collecting current health, a profile probe, logs, and metrics.',
  diagnose:'Analyzing the report and tool evidence; waiting for a validated structured diagnosis.',
  recover:'Checking the recommendation and budget before a controlled application-layer repair.',
  verify:'Fresh API, authentication, database, login, and profile checks. All five must pass.',
  retry:'Verification failed. Returning to diagnosis with fresh evidence.',
  finalize:'Determining the terminal outcome from independent verification.'
};
const planned = {monitor:['check_api_health','check_auth_health','check_database_health','profile','get_application_logs','get_service_metrics'],diagnose:[],recover:[],verify:['api_health','auth_health','database_health','login','profile']};
let busy=false, terminal=false, currentMode='demo', threadId=null, lastResult=null, receivedResult=null;
let timer=null, startedAt=0, skipPlayback=false, configured=false;
const taskRows = new Map();
function text(tag,value,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;}
function modeNote(){
  const demo=$('mode').value==='demo';
  $('scenario-control').hidden=!demo;$('scenario').disabled=!demo||busy;$('live-environment-note').hidden=demo;
  $('fault-lab').hidden=demo;
  $('portal-check').disabled=demo||busy;
  $('inject-fault').disabled=demo||busy;
  $('clear-faults').disabled=demo||busy;
  $('mode-note').textContent=demo?'Injects a controlled fault into isolated services. Diagnosis uses deterministic rules, not Gemini.':'Gemini analyzes your running local services. This form does not inject a fault.';
}
async function probePortal(){
  if($('mode').value!=='gemini')return;
  try{const response=await fetch('/api/lab/portal');if(!response.ok)throw Error('Could not check the local portal.');
    const snapshot=await response.json();Story.portalProbe(snapshot);
    const active=Object.entries(snapshot.faults).filter(([,value])=>value).map(([name])=>name);
    $('lab-status').textContent=active.length?`Active lab fault: ${active.join(', ')}.`:'No lab faults active. If the portal fails, check that the local services and database are running.';
  }catch(error){$('lab-status').textContent=error.message;}
}
async function changeFault(path,payload){
  if(busy||$('mode').value!=='gemini')return;
  $('inject-fault').disabled=true;$('clear-faults').disabled=true;
  try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!response.ok){const body=await response.json();throw Error(body.detail||'Could not change the lab fault.');}
    const snapshot=await response.json();Story.portalProbe(snapshot);
    $('lab-status').textContent=path.endsWith('reset')?'All controlled faults cleared.':`Triggered ${payload.fault}. The incident report has not changed the fault.`;
  }catch(error){$('lab-status').textContent=error.message;}finally{modeNote();}
}
function lockControls(value){
  busy=value;for(const input of $('incident-form').elements)input.disabled=value;
  $('run').disabled=value||!configured;$('retrieve').disabled=value;$('retrieve-thread').disabled=value;$('replay').disabled=value;
  modeNote();
}
function clearView(mode,scenario,clearFeed=true){
  Story.reset(mode,scenario);currentMode=mode;taskRows.clear();$('active-tasks').replaceChildren();
  if(clearFeed)$('activity-feed').replaceChildren();
  $('error').hidden=true;$('activity-title').textContent='Starting investigation';
  $('activity-description').textContent='Results come from actual execution.';$('activity-kind').textContent='LIVE AGENT ACTIVITY';
  $('playback-bar').hidden=true;$('status').textContent='Connecting to the workflow';$('summary').textContent='Waiting for the first event...';
  $('badge').className='badge';$('badge').textContent='Live';$('elapsed').textContent='0.0s';$('elapsed-label').textContent='Execution time';
}
function setTask(tool,status,detail=''){
  if(!taskRows.has(tool)){const li=text('li',''),badge=text('strong','','muted'),content=text('span','');content.append(text('b',tool),text('small',''));li.append(badge,content);$('active-tasks').append(li);taskRows.set(tool,{badge,content});}
  const row=taskRows.get(tool);row.badge.textContent=status;
  row.badge.className=status==='FAIL'||status==='ERROR'?'fail':status==='WAIT'?'muted':'pass';row.content.querySelector('small').textContent=detail;
}
function activity(message,elapsed,result){
  const item=text('div','','activity-entry');item.append(text('span',`${(elapsed/1000).toFixed(1)}s`,'activity-time'),text('span',message));
  if(result){const d=document.createElement('details');d.append(text('summary','Observed result'),text('pre',JSON.stringify(result,null,2)));item.append(d);}
  $('activity-feed').append(item);$('activity-feed').scrollTop=$('activity-feed').scrollHeight;
}
function nodeStarted(event,recorded=false){
  Story.started(event.node);$('status').textContent=`${names[event.node]} ${recorded?'in recorded walkthrough':'in progress'}`;
  $('activity-title').textContent=`${names[event.node]} ${recorded?'snapshot':'running'}`;
  $('activity-description').textContent=descriptions[event.node]||'';
  if(event.node==='diagnose'&&currentMode==='demo')$('activity-description').textContent='Deterministic demo diagnosis from observations. No Gemini call.';
  taskRows.clear();$('active-tasks').replaceChildren();
  if(!recorded){for(const tool of planned[event.node]||[])setTask(tool,'WAIT');activity(`${names[event.node]} started`,event.elapsed_ms);}
  if(event.requested_evidence?.length&&event.node==='monitor')$('activity-description').textContent+=' Requested evidence: '+event.requested_evidence.join(', ');
}
function toolResult(result){
  if(result.error)return ['ERROR',result.error];
  if(result.healthy===false||result.passed===false||result.succeeded===false)return ['FAIL',result.details||'Check failed'];
  if('healthy' in result&&result.healthy===null)return ['ERROR','Health unknown'];
  if(result.logs)return ['DONE',`${result.logs.length} log entries`];
  if(result.metrics)return ['DONE',Object.entries(result.metrics).map(([k,v])=>`${k}: ${v}`).join(' / ')];
  if(result.probable_cause)return ['DONE',result.probable_cause];
  return ['PASS',result.details||'Completed'];
}
function finish(result){
  clearInterval(timer);lastResult=result;Story.finish(result);
  if(result.mode==='gemini')probePortal();
  const good=P.resolved(result.state);
  $('status').textContent=good?'Incident resolved':'Incident remains unresolved';$('badge').textContent=result.state.final_status;
  $('badge').className='badge '+(good?'success':'failure');
  $('summary').textContent=`${result.mode==='demo'?'Isolated demo / no Gemini':'Local services / Gemini'} \u00b7 ${result.state.termination_reason} \u00b7 Thread ${result.thread_id}`;
  $('elapsed').textContent=`${(result.elapsed_ms/1000).toFixed(2)}s`;
  $('activity-title').textContent='Investigation complete';$('activity-description').textContent='Review the observed results, cycle history, and expandable timeline.';
  $('active-tasks').replaceChildren();$('playback-bar').hidden=true;$('retrieve-thread').value=result.thread_id;
}
function receive(event){
  if(event.event==='heartbeat')return;
  switch(event.event){
    case 'run_started':threadId=event.thread_id;currentMode=event.mode;Story.stage(1);$('summary').textContent=`${event.mode==='demo'?'Isolated demo':'Gemini / local services'} \u00b7 Thread ${threadId}`;activity('Incident reported',event.elapsed_ms);break;
    case 'node_started':nodeStarted(event);break;
    case 'tool_started':setTask(event.tool,'RUN','Waiting for the result...');Story.tool(event.node,event.tool,'running');activity(`${event.tool} started`,event.elapsed_ms);break;
    case 'tool_completed':{const [status,detail]=toolResult(event.result);setTask(event.tool,status,detail);Story.tool(event.node,event.tool,status);activity(`${event.tool}: ${status.toLowerCase()} / ${detail}`,event.elapsed_ms,event.result);break;}
    case 'step_completed':Story.stepCompleted(event.step);activity(`${names[event.step.node]}: ${Story.summary(event.step)}`,event.elapsed_ms);break;
    case 'run_completed':terminal=true;receivedResult=event.result;clearInterval(timer);break;
    case 'run_failed':terminal=true;throw Error(event.message);
  }
}
async function consume(response){
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
  try{while(true){const {value,done}=await reader.read();pending+=decoder.decode(value,{stream:!done});let n;while((n=pending.indexOf('\n'))>=0){const line=pending.slice(0,n).trim();pending=pending.slice(n+1);if(line)receive(JSON.parse(line));}if(done)break;}
    if(pending.trim())receive(JSON.parse(pending));if(!terminal)throw Error('Live connection ended before the final result.');
  }finally{reader.releaseLock();}
}
async function playback(result){
  skipPlayback=false;clearView(result.mode,result.scenario,false);lockControls(true);$('run').textContent='Recorded walkthrough...';
  $('activity-kind').textContent='RECORDED SNAPSHOT PLAYBACK';$('playback-bar').hidden=false;$('badge').textContent='Replay';
  $('summary').textContent=`Recorded execution / Thread ${result.thread_id}. No new agent or tool calls.`;
  $('elapsed').textContent=`${(result.elapsed_ms/1000).toFixed(2)}s`;$('elapsed-label').textContent='Recorded execution';
  for(const [index,step] of result.steps.entries()){
    if(skipPlayback)break;
    $('playback-note').textContent=`Recorded walkthrough / step ${index+1} of ${result.steps.length} / 800 ms per step`;
    nodeStarted({node:step.node,requested_evidence:step.state.requested_evidence},true);
    await new Promise(resolve=>setTimeout(resolve,800));
    Story.stepCompleted(step);
  }
  if(skipPlayback){Story.reset(result.mode,result.scenario);for(const step of result.steps)Story.stepCompleted(step);}
  finish(result);
}
async function presentResult(result,auto){
  if(auto)await playback(result);else finish(result);
}
function interrupted(error){
  $('error').hidden=false;$('error').textContent=error.message;$('status').textContent='Live view interrupted';$('badge').textContent='Unknown outcome';$('badge').className='badge failure';
  $('summary').textContent=threadId?`Thread ${threadId}. The server may still be running. Retrieve the incident after completion; disconnection does not cancel recovery.`:'No completed workflow result was received.';
  if(threadId)$('retrieve-thread').value=threadId;
  $('activity-title').textContent='Live updates stopped';for(const card of document.querySelectorAll('.agent-card.running')){card.classList.remove('running');card.classList.add('attention');card.querySelector('.agent-state').textContent='Outcome unknown';}
}
$('incident-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;
  const payload={report:$('report').value,mode:$('mode').value,max_retries:Number($('retries').value),thread_id:$('thread').value||null};if(payload.mode==='demo')payload.scenario=$('scenario').value;
  const auto=$('auto-replay').checked;terminal=false;threadId=null;receivedResult=null;lastResult=null;
  clearView(payload.mode,payload.scenario);Story.stage(1);lockControls(true);$('run').textContent='Investigation running...';
  if(window.innerWidth>800)$('results').scrollIntoView({behavior:'auto',block:'start'});
  startedAt=performance.now();timer=setInterval(()=>{$('elapsed').textContent=`${((performance.now()-startedAt)/1000).toFixed(1)}s`;},100);
  try{
    const response=await fetch('/api/incidents/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!response.ok){const body=await response.json();throw Error(typeof body.detail==='string'?body.detail:'Invalid request. Check the input values.');}
    await consume(response);await presentResult(receivedResult,auto);
  }catch(error){
    let restored=false;
    if(threadId&&!terminal){try{const r=await fetch(`/api/incidents/${encodeURIComponent(threadId)}`);if(r.ok){const result=await r.json();Story.reset(result.mode,result.scenario);result.steps.forEach(Story.stepCompleted);finish(result);restored=true;}}catch{}}
    if(!restored)interrupted(error);
  }finally{clearInterval(timer);lockControls(false);$('run').textContent='Run investigation \u2192';}
});
$('skip-replay').addEventListener('click',()=>{skipPlayback=true;});
$('replay').addEventListener('click',async()=>{if(busy||!lastResult)return;try{await playback(lastResult);}finally{lockControls(false);$('run').textContent='Run investigation \u2192';}});
$('retrieve').addEventListener('click',async()=>{
  if(busy)return;const id=$('retrieve-thread').value.trim();
  if(!/^[A-Za-z0-9._-]{1,80}$/.test(id)){$('retrieve-message').textContent='Enter a valid thread ID.';return;}
  lockControls(true);
  try{const response=await fetch(`/api/incidents/${encodeURIComponent(id)}`);if(!response.ok)throw Error(response.status===404?'Incident not found in this server process.':'Could not retrieve incident.');
    const result=await response.json();$('mode').value=result.mode;if(result.scenario)$('scenario').value=result.scenario;$('report').value=result.state.user_report;
    clearView(result.mode,result.scenario);for(const step of result.steps)Story.stepCompleted(step);finish(result);$('retrieve-message').textContent='Loaded stored snapshots. No workflow was rerun.';
  }catch(error){$('retrieve-message').textContent=error.message;}finally{lockControls(false);}
});
function selectionChanged(){if(busy)return;lastResult=null;Story.reset($('mode').value,$('scenario').value);modeNote();if($('mode').value==='gemini')probePortal();$('status').textContent='Ready to investigate';$('badge').textContent='Ready';$('badge').className='badge';$('summary').textContent='New selection. Run an investigation to collect evidence.';$('activity-feed').replaceChildren();$('active-tasks').replaceChildren();$('activity-title').textContent='Waiting for an investigation';$('activity-description').textContent='Actual checks and their results appear as they run.';$('elapsed').textContent='\u2014';}
$('mode').addEventListener('change',selectionChanged);$('scenario').addEventListener('change',selectionChanged);
$('portal-check').addEventListener('click',probePortal);
$('inject-fault').addEventListener('click',()=>changeFault('/api/lab/faults',{fault:$('fault-choice').value}));
$('clear-faults').addEventListener('click',()=>changeFault('/api/lab/reset',{}));
if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)$('auto-replay').checked=false;
$('run').disabled=true;modeNote();Story.reset('demo','auth_down');
fetch('/api/config').then(r=>{if(!r.ok)throw Error();return r.json();}).then(config=>{
  for(const item of config.scenarios){const option=text('option',item.label);option.value=item.id;$('scenario').append(option);}
  $('scenario').value='auth_down';$('retries').value=config.max_retries;configured=true;$('run').disabled=busy;
  $('model').textContent=`Configured model: ${config.model} / Gemini key ${config.gemini_configured?'configured':'not configured'}`;
}).catch(()=>{$('error').hidden=false;$('error').textContent='Could not load configuration. Refresh when the backend is available.';});
