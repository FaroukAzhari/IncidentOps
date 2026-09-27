/* Pure presentation rules. No requests, actions, or inferred health values. */
(function (root) {
  'use strict';
  const names = {api:'API', auth:'Authentication', database:'Database', login:'Login', profile:'Profile'};
  const previews = {
    healthy:['Ready for sign-in', 'The selected demo starts healthy. No recovery is expected.'],
    auth_down:['Sign-in unavailable', 'Authentication service unavailable.'],
    database_down:['Profile unavailable', 'The database-backed profile cannot load.'],
    api_degraded:['Application unavailable', 'The application API is degraded.'],
    wrong_db_config:['Profile unavailable', 'Authentication may work, but the application cannot load profile data.'],
    multiple_faults:['Sign-in and profile unavailable', 'The demo starts with authentication and database faults.'],
    persistent_auth:['Sign-in unavailable', 'Authentication is unavailable; this demo deliberately blocks repair.']
  };
  function checkValue(check) {
    return check && !check.error && typeof check.passed === 'boolean' ? check.passed : null;
  }
  function health(state = {}, verification = false) {
    state = state || {};
    const checks = state.verification_result?.checks || [];
    const find = name => checks.find(c => c.name === name);
    const values = {};
    for (const key of ['api','auth','database']) {
      values[key] = verification ? checkValue(find(key+'_health')) :
        typeof state.service_status?.[key] === 'boolean' ? state.service_status[key] : null;
    }
    // Monitoring does not perform a standalone login check. Never infer its result.
    values.login = verification ? checkValue(find('login')) : null;
    values.profile = checkValue(verification ? find('profile') : state.profile_check);
    return values;
  }
  function resolved(state) {
    return state?.final_status === 'resolved' && state.incident_resolved === true && state.verification_passed === true;
  }
  function portal(state, final = false) {
    if (!state) return {tone:'unknown', title:'Waiting for observations', message:'Run an investigation to check the local application.'};
    if (final && resolved(state)) return {tone:'healthy', title:state.recovery_attempts ? 'Application restored' : 'Application verified healthy', message:'Login successful. Welcome, Demo User. Profile loaded successfully.'};
    if (final) return {tone:'failed', title:'Incident remains unresolved', message:state.verification_result?.remaining_problem || state.termination_reason || 'Recovery has not been verified.'};
    const current = health(state, state.evidence_source === 'verification');
    if (current.api === false) return {tone:'failed', title:'Application unavailable', message:'The latest API health check failed.'};
    if (current.auth === false) return {tone:'failed', title:'Sign-in unavailable', message:'The latest authentication health check failed.'};
    if (current.profile === false || current.database === false) return {tone:'failed', title:'Profile unavailable', message:state.profile_check?.error || state.profile_check?.details || 'The latest database check failed.'};
    return {tone:'pending', title:'Awaiting final verification', message:'Observations have arrived. The application is not marked restored until the final verified outcome.'};
  }
  function tools(state = {}, previous = {}, node) {
    return Object.entries(state.tool_calls || {}).filter(([key, count]) =>
      key.startsWith(node+'.') && count > (previous.tool_calls?.[key] || 0)
    ).map(([key,count]) => [key, count - (previous.tool_calls?.[key] || 0)]);
  }
  function nodeStatus(node, state) {
    if (node === 'monitor') return state.collection_errors?.length ? 'attention' : 'complete';
    if (node === 'diagnose') return !state.suspected_root_cause ? 'failed' : state.needs_more_evidence ? 'attention' : 'complete';
    if (node === 'recover') return state.recovery_result?.startsWith('failed:') ? 'failed' : !state.recovery_action ? 'skipped' : 'complete';
    if (node === 'verify') return state.verification_passed === true ? 'complete' : state.verification_passed === false ? 'failed' : 'skipped';
    return 'complete';
  }
  root.IncidentPresentation = {names, previews, health, resolved, portal, tools, nodeStatus};
})(globalThis);
