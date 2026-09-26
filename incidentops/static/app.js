const $ = id => document.getElementById(id);
const names = {monitor:'Monitoring',diagnose:'Diagnostic',recover:'Recovery',verify:'Verification',retry:'Retry',finalize:'Final outcome'};
function text(tag, value, cls) { const el=document.createElement(tag); el.textContent=value; if(cls) el.className=cls; return el; }
function modeNote() {
  const demo=$('mode').value==='demo'; $('scenario').disabled=!demo;
  $('mode-note').textContent=demo?'Real service endpoints in isolated storage, with deterministic diagnosis. This does not measure Gemini quality.':'Uses Gemini and your running local services. Recovery changes their configured fault store; no scenario is injected.';
}
$('mode').addEventListener('change',modeNote);
fetch('/api/config').then(r=>{if(!r.ok) throw Error();return r.json();}).then(config=>{
  for(const item of config.scenarios) {const option=text('option',item.label);option.value=item.id;$('scenario').append(option);}
  $('scenario').value='auth_down';$('retries').value=config.max_retries;
  $('model').textContent=`Model: ${config.model} · Gemini key ${config.gemini_configured?'configured':'not configured'}`;
}).catch(()=>{$('error').hidden=false;$('error').textContent='Could not load configuration. Refresh when the backend is available.';});
function render(result) {
  const s=result.state; $('status').textContent=s.final_status==='resolved'?'Incident resolved':s.final_status==='monitoring_only'?'Monitoring complete':'Incident unresolved';
  $('badge').textContent=s.final_status; $('badge').className='badge '+(s.incident_resolved?'success':'failure');
  $('summary').textContent=`${result.mode==='demo'?'Isolated demo':'Gemini / local services'} · ${s.termination_reason} · Thread ${result.thread_id}`;
  $('retry-count').textContent=`${s.retry_count} / ${s.max_retries}`;$('attempts').textContent=`${s.recovery_attempts} / ${s.max_recovery_attempts}`;$('elapsed').textContent=`${(result.elapsed_ms/1000).toFixed(2)}s`;
  for(const li of document.querySelectorAll('[data-node]')) li.classList.toggle('complete',result.steps.some(step=>step.node===li.dataset.node));
  const verification=document.querySelector('[data-node="verify"]');verification.classList.toggle('failed',s.verification_passed===false);verification.querySelector('span').textContent=s.verification_passed===false?'Checks failed':s.verification_passed===true?'Checks passed':'Not verified';
  $('detail-panel').hidden=false;$('agent-details').replaceChildren();
  const monitoring=result.steps.find(step=>step.node==='monitor');
  const details=[['Monitoring',JSON.stringify(monitoring?.state.service_status||{})],['Probable cause',s.suspected_root_cause||'No valid diagnosis'],['Recommended action',s.recommended_action||'None'],['Recovery',s.recovery_result||'No recovery action executed'],['Verification',s.verification_result?.summary||'No independent result']];
  for(const [label,value] of details){const div=text('div','', 'detail');div.append(text('b',label),text('span',value));$('agent-details').append(div);}
  $('checks').replaceChildren();for(const check of s.verification_result?.checks||[]){const li=text('li','');li.append(text('strong',check.passed&&!check.error?'PASS':'FAIL',check.passed&&!check.error?'pass':'fail'),text('span',`${check.name}: ${check.error||check.details}`));$('checks').append(li);}
  $('errors').replaceChildren(...s.errors.map(error=>text('p',error)));
  $('timeline').replaceChildren();for(const [index,step] of result.steps.entries()){const item=document.createElement('details');item.append(text('summary',`${index+1}. ${names[step.node]||step.node} · ${step.elapsed_ms.toFixed(0)} ms`),text('pre',JSON.stringify(step.update,null,2)));$('timeline').append(item);}
}
$('incident-form').addEventListener('submit',async event=>{
  event.preventDefault();$('error').hidden=true;$('run').disabled=true;$('run').textContent='Investigation running…';$('results').setAttribute('aria-busy','true');
  $('status').textContent='Investigation in progress';$('badge').textContent='Running';$('badge').className='badge';$('summary').textContent='Collecting evidence and running the workflow. Results appear when it finishes.';
  $('detail-panel').hidden=true;$('timeline').replaceChildren();for(const id of ['retry-count','attempts','elapsed'])$(id).textContent='—';for(const li of document.querySelectorAll('[data-node]'))li.classList.remove('complete','failed');document.querySelector('[data-node="verify"] span').textContent='Test independently';
  try{const response=await fetch('/api/incidents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({report:$('report').value,mode:$('mode').value,scenario:$('scenario').value,max_retries:Number($('retries').value),thread_id:$('thread').value||null})});const body=await response.json();if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Invalid request. Check the input values.');render(body);}
  catch(error){$('error').hidden=false;$('error').textContent=error.message;$('status').textContent='Investigation could not complete';$('summary').textContent='No completed result was returned. Review the error and try again.';$('badge').textContent='Error';$('badge').className='badge failure';}
  finally{$('run').disabled=false;$('run').textContent='Run investigation →';$('results').setAttribute('aria-busy','false');}
});
