export function createEmptyWorkbenchState(overrides = {}) {
  return {
    schema_version: null,
    domain: null,
    domain_version: null,
    domain_pack_status: null,
    status: 'idle',
    query_type: null,
    query: {},
    answer: '',
    items: [],
    top_results: [],
    result_sections: {},
    result_count: 0,
    executed_filters: [],
    deterministic_rules: [],
    executable_rules: [],
    candidates_to_confirm: [],
    candidate_rules: [],
    confirmed_rules: [],
    unconfirmed_candidates: [],
    unexecuted_preferences: [],
    not_executed_preferences: [],
    no_schema_field_preferences: [],
    rejected_confirmations: [],
    warnings: [],
    evidence_pack: {},
    debug_trace: {},
    simulated_confirmations: {},
    extracted_preferences: [],
    attribute_grounding: {},
    proposed_rules: [],
    natural_language_report: createEmptyEvidenceReport(),
    token_usage: null,
    selected_options: {},
    frontend_state: {
      source: 'empty',
      is_explicit_demo: false,
      options_source: 'fallback',
    },
    ...overrides,
  };
}

export function createEmptyEvidenceReport() {
  return {
    title: '',
    summary: '',
    result_count_text: '',
    executed_rules: [],
    top_results: [],
    full_text: '',
    warnings: [],
    disclaimer: '',
  };
}

export function isEmptyWorkbenchState(data) {
  return !data || data.status === 'idle' || data.frontend_state?.source === 'empty';
}

export function mergeDemoRun(demoRun, { runRequest = null, selectedOptions = {} } = {}) {
  return {
    ...demoRun,
    ...(runRequest
      ? {
          user_input: runRequest.user_input,
          hard_filters: runRequest.hard_filters,
          soft_preferences: runRequest.soft_preferences,
        }
      : {}),
    selected_options: {
      ...(demoRun?.selected_options || {}),
      ...selectedOptions,
    },
    token_usage: null,
    frontend_state: {
      source: 'demo',
      is_explicit_demo: true,
      options_source: 'demo',
    },
  };
}

export function candidateIdentifier(candidate) {
  return candidate?.candidate_id || '';
}

function candidateConfirmationList(runData) {
  return Array.isArray(runData?.candidates_to_confirm) && runData.candidates_to_confirm.length
    ? runData.candidates_to_confirm
    : Array.isArray(runData?.candidate_rules)
      ? runData.candidate_rules
      : [];
}

export function splitCandidateConfirmationState(runData) {
  const candidates = candidateConfirmationList(runData);

  return candidates.reduce((result, candidate) => {
    const confirmationId = candidateIdentifier(candidate);
    const candidateWithState = {
      ...candidate,
      confirmationId,
    };
    if (confirmationId) {
      result.confirmable.push(candidateWithState);
    } else {
      result.blocked.push(candidateWithState);
    }
    return result;
  }, { confirmable: [], blocked: [] });
}

export function confirmableCandidates(runData) {
  return splitCandidateConfirmationState(runData).confirmable;
}
