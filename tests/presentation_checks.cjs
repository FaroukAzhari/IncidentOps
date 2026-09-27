// Optional frontend regression checks using Node's built-in assertions only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
vm.runInThisContext(fs.readFileSync('incidentops/static/presentation.js', 'utf8'));
const P = globalThis.IncidentPresentation;
const results = JSON.parse(fs.readFileSync(0, 'utf8'));
for (const result of results) {
  let previous = {};
  const first = result.steps.find(s => s.node === 'monitor').state;
  assert.equal(P.health(first).login, null, 'No inferred login test from auth health');
  for (const step of result.steps) {
    assert.notEqual(P.portal(step.state).tone, 'healthy', 'No premature restoration during execution');
    for (const [key, count] of P.tools(step.state, previous, step.node)) {
      assert.ok(step.state.tool_calls[key] > 0);
      assert.equal(count, step.state.tool_calls[key] - (previous.tool_calls?.[key] || 0));
    }
    previous = step.state;
  }
  const shouldResolve = result.scenario !== 'persistent_auth';
  assert.equal(P.resolved(result.state), shouldResolve);
  assert.equal(P.portal(result.state, true).tone, shouldResolve ? 'healthy' : 'failed');
  const finalChecks = P.health(result.state, true);
  assert.equal(Object.values(finalChecks).every(x => x === true), shouldResolve);
  if (result.scenario === 'multiple_faults') {
    const failed = result.steps.find(s => s.node === 'verify' && !s.state.verification_passed);
    assert.equal(P.portal(failed.state).tone, 'failed');
    assert.equal(P.health(failed.state, true).auth, true);
    assert.equal(P.health(failed.state, true).database, false);
  }
  if (result.scenario === 'healthy') {
    const step = result.steps.find(s => s.node === 'recover');
    assert.equal(P.nodeStatus('recover', step.state), 'skipped');
    assert.deepEqual(P.tools(step.state, {}, 'recover'), []);
  }
}
assert.equal(P.resolved({final_status:'resolved', incident_resolved:true, verification_passed:false}), false);
assert.equal(P.resolved({final_status:'unresolved', incident_resolved:true, verification_passed:true}), false);
assert.equal(P.health({service_status:{api:false}}).auth, null);
assert.equal(P.health({verification_result:{checks:[{name:'login',passed:true,error:'Unavailable'}]}}, true).login, null);
assert.equal(P.portal(null).tone, 'unknown');
assert.deepEqual(P.health(null), {api:null,auth:null,database:null,login:null,profile:null});
assert.equal(P.nodeStatus('diagnose', {suspected_root_cause:'Unknown',needs_more_evidence:true}), 'attention');
console.log(`Presentation rules passed for ${results.length} real scenario traces.`);
