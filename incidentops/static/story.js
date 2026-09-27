/* DOM presentation of backend snapshots. No workflow decisions live here. */
(function (root) {
  'use strict';
  const P = root.IncidentPresentation;
  const $ = id => document.getElementById(id);
  const names = {monitor:'Monitoring', diagnose:'Diagnostic', recover:'Recovery', verify:'Verification', retry:'Retry', finalize:'Final outcome'};
  const statusLabels = {waiting:'Waiting', running:'Running', complete:'Completed', failed:'Failed', attention:'Needs attention', skipped:'Skipped'};
  let first = null, previous = {}, steps = [], mode = 'demo', cycles = [], totalMs = 0;
  function el(tag, value, cls) {const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;}
  function pair(container, label, value) {const row=el('div','','detail');row.append(el('dt',label),el('dd',value ?? 'Not available'));container.append(row);}
  function signal(value, unknown='Not observed') {return el('span',value===true?'\u2713 Pass':value===false?'\u2717 Fail':unknown,value===true?'pass':value===false?'fail':'muted');}
  function stateOfCard(node, status) {
    const card=document.querySelector(`[data-node="${node}"]`);if(!card)return;
    card.className='agent-card '+status;card.querySelector('.agent-state').textContent=statusLabels[status];
  }
  function stage(stage, done=false) {
    const ids=['problem','report','investigation','outcome'];
    ids.forEach((id,index)=>{const e=$('story-'+id);e.classList.toggle('active',index===stage);e.classList.toggle('done',index<stage || done);});
  }
  function paintPortal(view, source, caption, restored=false) {
    $('portal-body').className='portal-body '+view.tone;
    $('portal-title').textContent=view.title;$('portal-message').textContent=view.message;
    $('portal-source').textContent=source;$('portal-caption').textContent=caption;
    $('portal-login').hidden=restored;$('portal-profile').hidden=!restored;
  }
  function preview(selectedMode, scenario) {
    mode=selectedMode;
    const entry=P.previews[scenario];
    if(mode==='demo' && entry) paintPortal({tone:scenario==='healthy'?'pending':'failed',title:entry[0],message:entry[1]},'Scenario preview','Illustration of the selected demo fault, not a live browser. Investigation results replace this preview.');
    else paintPortal(P.portal(null),'Not observed','Local service health is unknown until tools run. The report does not inject a fault.');
    $('header-mode').textContent=mode==='demo'?'Isolated lab / deterministic diagnosis':'Local services / Gemini';
    $('diagnostic-role').textContent=mode==='demo'?'Deterministic demo rules; no Gemini call.':'Gemini structured output from observed evidence.';
  }
  function portalProbe(snapshot) {
    if(mode!=='gemini')return;
    const login=snapshot.login, profile=snapshot.profile;
    const message=snapshot.ready?'Demo sign-in and database-backed profile both succeeded.':
      !login?.passed?(login?.error || login?.details || 'Authentication is unavailable.'):
      (profile?.error || profile?.details || 'Profile is unavailable.');
    paintPortal({tone:snapshot.ready?'healthy':'failed',title:snapshot.ready?'Employee portal is working':'Employee portal has a problem',message},
      'Live service probe','Fixed demo identity. This view uses fresh authentication and profile requests; the agents use their own checks.',snapshot.ready);
  }
  function observations(state, final=false) {
    const current=P.health(state, state?.evidence_source==='verification');
    $('topology').replaceChildren();
    for(const name of ['api','auth','database']) {const box=el('div','','topology-node');box.append(el('strong',P.names[name]),signal(current[name]));$('topology').append(box);}
    $('topology-note').textContent=state ? `Source: ${state.evidence_source || 'monitoring'}${final?' / final snapshot':''}` : 'Waiting for actual service observations.';
    const before=P.health(first || {});
    const after=P.health(state || {},true);
    $('after-heading').textContent=final?'Final verification':'Latest verification';
    $('comparison').replaceChildren();
    for(const name of Object.keys(P.names)) {const row=document.createElement('tr');const a=document.createElement('td'),b=document.createElement('td');a.append(signal(before[name],name==='login'?'Not tested':'Not observed'));b.append(signal(after[name]));const label=el('th',P.names[name]);label.scope='row';row.append(label,a,b);$('comparison').append(row);}
  }
  function reset(selectedMode, scenario) {
    first=null;previous={};steps=[];cycles=[];totalMs=0;
    preview(selectedMode,scenario);stage(0);observations(null);
    for(const node of ['monitor','diagnose','recover','verify']) {stateOfCard(node,'waiting');$('result-'+node).replaceChildren(el('p','Waiting for observed results.','hint'));$('tools-'+node).replaceChildren();}
    for(const id of ['timeline','execution-history','cycles','errors'])$(id).replaceChildren();
    $('cycles-panel').hidden=true;$('final-outcome').hidden=true;
    $('retry-count').textContent='\u2014';$('attempts').textContent='\u2014';
  }
  function started(node) {
    stage(2);
    for(const card of document.querySelectorAll('.agent-card.running')) stateOfCard(card.dataset.node,'waiting');
    stateOfCard(node,'running');
    if($('result-'+node))$('result-'+node).replaceChildren(el('p','Waiting for this agent\u2019s current result.','hint'));
    if($('tools-'+node))$('tools-'+node).replaceChildren();
  }
  function tool(node, tool, status) {
    const box=$('tools-'+node);if(!box)return;
    let chip=Array.from(box.children).find(c=>c.dataset.tool===tool);
    if(!chip){chip=el('span','','tool-chip');chip.dataset.tool=tool;box.append(chip);}
    chip.textContent=`${tool} / ${status}`;
  }
  function summary(step) {
    const s=step.state;
    switch(step.node) {
      case 'monitor': return `Evidence collected${s.collection_errors?.length?' with collection errors':''}`;
      case 'diagnose': return s.suspected_root_cause || 'No validated diagnosis';
      case 'recover': return s.recovery_result || 'No action executed';
      case 'verify': return (s.verification_passed?'Passed':'Failed')+(s.verification_result?.remaining_problem?': '+s.verification_result.remaining_problem:'');
      case 'retry': return `Retry ${s.retry_count} / ${s.max_retries}: return to Diagnostic`;
      default: return s.termination_reason || 'Finalizing';
    }
  }
  function cardResult(step) {
    const s=step.state,node=step.node,box=$('result-'+node);if(!box)return;
    box.replaceChildren();const content=document.createElement('dl');
    if(node==='monitor') {
      const checks=P.health(s);
      for(const name of ['api','auth','database','profile']) {const line=el('div','','check-line');line.append(el('span',P.names[name]),signal(checks[name]));box.append(line);}
      if(s.profile_check?.status_code)box.append(el('p',`Profile HTTP ${s.profile_check.status_code}`,'hint'));
      box.append(el('p',`${s.logs.length} log entries / ${Object.keys(s.metrics).length} metrics`,'hint'));
    } else if(node==='diagnose') {
      pair(content,'Suspected component',s.suspected_component);pair(content,'Root cause',s.suspected_root_cause);
      pair(content,'Confidence',typeof s.diagnosis_confidence==='number'?`${Math.round(s.diagnosis_confidence*100)}%`:'Not available');
      pair(content,'Recommended action',s.recommended_action);
      if(s.needs_more_evidence)pair(content,'Additional evidence',s.requested_evidence.join(', '));
      if(s.diagnosis_evidence?.length){const d=document.createElement('details');d.append(el('summary','Supporting evidence'));const list=document.createElement('ul');s.diagnosis_evidence.forEach(item=>list.append(el('li',item)));d.append(list);content.append(d);}
    } else if(node==='recover') {
      pair(content,'Executed action',s.recovery_action || 'None');pair(content,'Result',s.recovery_result || 'Skipped: no action executed');pair(content,'Attempt',`${s.recovery_attempts} / ${s.max_recovery_attempts}`);
    } else {
      for(const check of s.verification_result?.checks || []){const line=el('div','','check-line');line.append(el('span',P.names[check.name.replace('_health','')]||check.name),signal(check.error?null:check.passed, 'Error'));box.append(line);}
      pair(content,'Verdict',s.verification_passed===true?'PASSED':s.verification_passed===false?'FAILED':'Not verified');
      if(s.verification_result?.remaining_problem)pair(content,'Remaining problem',s.verification_result.remaining_problem);
    }
    box.append(content);stateOfCard(node,P.nodeStatus(node,s));
    const tools=$('tools-'+node);tools.replaceChildren();
    for(const [name,count] of P.tools(s,previous,node))tools.append(el('span',`${name} \u00d7 ${count}`,'tool-chip'));
  }
  function cycleStep(step) {
    if(!cycles.length)cycles.push([]);
    if(step.node==='retry')cycles.push([]);
    else if(step.node!=='finalize')cycles[cycles.length-1].push(step);
    if(cycles.length<2)return;
    $('cycles-panel').hidden=false;$('cycles').replaceChildren();
    cycles.forEach((items,index)=>{
      if(index)$('cycles').append(el('p',`\u21bb Retry ${index}: fresh verification evidence returns to Diagnostic`,'retry-link'));
      const box=el('section','','cycle');box.append(el('h3',`Cycle ${index+1}`));
      for(const item of items){const line=el('p',`${names[item.node]}: ${summary(item)}`);if(item.node==='verify')line.className=item.state.verification_passed?'pass':'fail';box.append(line);}
      $('cycles').append(box);
    });
  }
  function stepCompleted(step) {
    steps.push(step);totalMs+=step.elapsed_ms;
    if(!first && step.node==='monitor')first=step.state;
    cardResult(step);cycleStep(step);
    if(step.node==='monitor'||step.node==='verify'){
      if(mode==='demo')paintPortal(P.portal(step.state),'Observed evidence','Visualized from actual tool results. A successful action alone does not prove restoration.');observations(step.state);
    }
    $('retry-count').textContent=`${step.state.retry_count} / ${step.state.max_retries}`;
    $('attempts').textContent=`${step.state.recovery_attempts} / ${step.state.max_recovery_attempts}`;
    $('errors').replaceChildren(...step.state.errors.map(e=>el('p',e,'fail')));
    const entry=document.createElement('details');entry.className='timeline-step';
    entry.append(el('summary',`${steps.length}. ${names[step.node]} / ${(totalMs/1000).toFixed(2)}s / ${summary(step)}`));
    entry.append(el('p',`Node duration: ${step.elapsed_ms.toFixed(0)} ms`,'hint'),el('h4','Partial state update'),el('pre',JSON.stringify(step.update,null,2)));
    const snapshot=document.createElement('details');snapshot.append(el('summary','Full state snapshot'),el('pre',JSON.stringify(step.state,null,2)));entry.append(snapshot);$('timeline').append(entry);
    previous=step.state;
  }
  function finish(result) {
    const s=result.state, good=P.resolved(s);stage(3,true);observations(s,true);
    if(mode==='demo')paintPortal(P.portal(s,true),'Final verified outcome','Illustrative portal driven by the actual terminal workflow state.',good);
    $('final-outcome').hidden=false;$('final-outcome').className='panel final-outcome '+(good?'success':'failure');
    $('final-title').textContent=good?'\u2713 INCIDENT RESOLVED':'\u2717 INCIDENT UNRESOLVED';
    $('final-description').textContent=good?(s.verification_result?.summary || 'Independent verification passed.'):`Reason: ${s.termination_reason || s.final_status}. ${s.verification_result?.remaining_problem || ''}`;
    $('execution-history').replaceChildren(...s.execution_history.map(item=>el('li',item)));
    $('errors').replaceChildren(...s.errors.map(item=>el('p',item,'fail')));
    for(const card of document.querySelectorAll('.agent-card.running'))stateOfCard(card.dataset.node,'attention');
  }
  root.IncidentStory={reset,preview,portalProbe,started,tool,stepCompleted,finish,stage,summary};
})(globalThis);
