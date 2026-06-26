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

export function createEmptyPreflightState(overrides = {}) {
  return {
    response: null,
    inputSignature: '',
    selections: {},
    ...overrides,
  };
}

export function boundarySelectionsFromPreflight(preflight) {
  return (preflight?.boundary_confirmations || []).reduce((selections, boundary) => {
    const confirmationId = boundary?.confirmation_id;
    if (!confirmationId) return selections;
    const defaultOptionId = boundary?.default_option_id
      || boundary?.options?.[0]?.option_id
      || 'do_not_use';
    return {
      ...selections,
      [confirmationId]: defaultOptionId,
    };
  }, {});
}

export function splitPreflightBoundarySelections(preflight, selections = {}) {
  const result = {
    confirmed_boundaries: [],
    disabled_boundaries: [],
  };
  for (const boundary of preflight?.boundary_confirmations || []) {
    const confirmationId = boundary?.confirmation_id;
    if (!confirmationId) continue;
    const optionId = selections[confirmationId] || boundary?.default_option_id || 'do_not_use';
    const option = (boundary?.options || []).find((item) => item?.option_id === optionId);
    const entry = {
      confirmation_id: confirmationId,
      option_id: optionId,
    };
    if (option?.disabled_boundary || optionId === 'do_not_use') {
      result.disabled_boundaries.push(entry);
    } else {
      result.confirmed_boundaries.push(entry);
    }
  }
  return result;
}

export function isCurrentPreflight({ preflightState, inputSignature }) {
  return Boolean(
    preflightState?.response?.preflight_id
    && preflightState.inputSignature
    && preflightState.inputSignature === inputSignature
  );
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
    if (isConfirmableCandidate(candidate, confirmationId)) {
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

export function candidateConfirmationSummary(runData) {
  const candidateState = splitCandidateConfirmationState(runData);
  const confirmableCount = candidateState.confirmable.length;
  const warningOnlyCount = candidateState.blocked.length;
  return {
    confirmableCount,
    warningOnlyCount,
    hasConfirmable: confirmableCount > 0,
    hasWarningOnly: warningOnlyCount > 0,
  };
}

export function uniqueUnusedPreferences(runData) {
  const seenIds = new Set();
  const seenStructuredKeys = new Set();
  const seenStructuredFallbackKeys = new Set();
  const seenUnstructuredKeys = new Set();
  const uniqueItems = [];
  const items = [
    ...listOrEmpty(runData?.unexecuted_preferences),
    ...listOrEmpty(runData?.not_executed_preferences),
    ...listOrEmpty(runData?.no_schema_field_preferences),
  ];

  for (const item of items) {
    const identity = unusedPreferenceIdentity(item);
    if (
      (identity.idKey && seenIds.has(identity.idKey))
      || (
        identity.structured
        && identity.structuredKey
        && seenStructuredKeys.has(identity.structuredKey)
      )
      || (
        identity.structured
        && identity.fallbackKeys.some((key) => seenUnstructuredKeys.has(key))
      )
      || (
        !identity.structured
        && identity.fallbackKeys.some((key) => (
          seenUnstructuredKeys.has(key) || seenStructuredFallbackKeys.has(key)
        ))
      )
    ) {
      continue;
    }
    uniqueItems.push(item);
    if (identity.idKey) {
      seenIds.add(identity.idKey);
    }
    if (identity.structured) {
      if (identity.structuredKey) {
        seenStructuredKeys.add(identity.structuredKey);
      }
      identity.fallbackKeys.forEach((key) => seenStructuredFallbackKeys.add(key));
    } else {
      identity.fallbackKeys.forEach((key) => seenUnstructuredKeys.add(key));
    }
  }

  return uniqueItems;
}

export function tokenUsageSectionState(tokenUsage, key) {
  const usage = tokenUsage?.[key];
  if (!usage) return { status: 'not_returned', label: '未返回用量' };
  const hasPositiveValue = Object.values(usage).some((value) => Number(value) > 0);
  return hasPositiveValue
    ? { status: 'has_usage', label: '已返回用量' }
    : { status: 'zero_usage', label: '未发生调用' };
}

export function tokenUsageSummaryState(tokenUsage) {
  const sectionStates = ['extractor', 'generator', 'total'].map((key) => (
    tokenUsageSectionState(tokenUsage, key)
  ));
  if (sectionStates.some((state) => state.status === 'has_usage')) {
    return { type: 'success', label: '已返回用量' };
  }
  if (sectionStates.some((state) => state.status === 'zero_usage')) {
    return { type: 'info', label: '未发生调用' };
  }
  return { type: 'warning', label: '未返回用量' };
}

function listOrEmpty(items) {
  return Array.isArray(items) ? items : [];
}

function isConfirmableCandidate(candidate, confirmationId) {
  return Boolean(
    confirmationId
    && candidate?.executable !== false
    && !isNoSchemaCandidate(candidate)
  );
}

function isNoSchemaCandidate(candidate) {
  return candidate?.match_type === 'no_schema_field'
    || candidate?.status === 'not_executable_missing_schema';
}

function unusedPreferenceIdentity(item) {
  if (!item || typeof item !== 'object') {
    const value = normalizeSemanticValue(item);
    return {
      idKey: '',
      structured: false,
      structuredKey: '',
      fallbackKeys: value ? [`value:${value}`] : [],
    };
  }

  const id = normalizeSemanticValue(item.id);
  const text = preferenceDisplayText(item);
  const fieldId = normalizeSemanticValue(item.field_id || item.field);
  const reason = normalizeSemanticValue(item.reason || item.message);
  const matchType = normalizeSemanticValue(item.match_type);
  const fallbackValue = normalizeSemanticValue(item.value || item.normalized_value);
  const fallbackKeys = [];

  if (text && reason) {
    fallbackKeys.push(`reason_text:${reason}:${text}`);
  } else if (text) {
    fallbackKeys.push(`text:${text}`);
  }
  if (!fallbackKeys.length && fallbackValue) {
    fallbackKeys.push(`value:${fallbackValue}`);
  }

  let structuredKey = '';
  if (fieldId && text) {
    structuredKey = [
      'field_text',
      fieldId,
      text,
      reason ? `reason:${reason}` : '',
      matchType ? `match_type:${matchType}` : '',
    ].filter(Boolean).join(':');
  }

  return {
    idKey: id ? `id:${id}` : '',
    structured: Boolean(fieldId),
    structuredKey,
    fallbackKeys,
  };
}

function preferenceDisplayText(item) {
  return normalizeSemanticValue(
    item.source_text
    || item.preference
    || item.display
    || item.label
    || item.text
  );
}

function normalizeSemanticValue(value) {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) {
    return value.map((item) => normalizeSemanticValue(item)).filter(Boolean).join('|');
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value).trim().toLowerCase();
}
