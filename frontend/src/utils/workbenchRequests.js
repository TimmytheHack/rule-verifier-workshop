export function buildWorkbenchRequest({
  source,
  runRequest,
  extractor,
  plannerMode = 'auto',
  generator,
  model,
  confirmedCandidates = [],
}) {
  const requestBody = {
    domain_name: source?.domainName || 'admissions',
    user_input: runRequest.user_input,
    hard_filters: runRequest.hard_filters,
    soft_preferences: runRequest.soft_preferences,
    extractor,
    planner_mode: plannerMode,
    generator,
    model,
    confirmed_candidates: [...confirmedCandidates],
  };

  if (source?.type === 'uploaded' && source?.datasetId) {
    requestBody.dataset_id = source.datasetId;
  }

  return requestBody;
}

export function buildWorkbenchPreflightRequest({
  source,
  runRequest,
  model,
  plannerMode = 'llm_semantic',
}) {
  if (source?.type !== 'uploaded' || !source?.datasetId || source?.domainName !== 'admissions') {
    return null;
  }
  return {
    dataset_id: source.datasetId,
    domain_name: source.domainName,
    user_input: runRequest.user_input,
    hard_filters: runRequest.hard_filters,
    soft_preferences: runRequest.soft_preferences,
    model,
    planner_mode: plannerMode,
  };
}

export function buildConfirmedWorkbenchRequest(previousRequest, confirmedCandidates) {
  return {
    ...previousRequest,
    confirmed_candidates: [
      ...(previousRequest.confirmed_candidates || []),
      ...confirmedCandidates,
    ],
  };
}

export function buildPreflightConfirmedWorkbenchRequest(
  previousRequest,
  {
    preflightId,
    confirmedBoundaries = [],
    disabledBoundaries = [],
  } = {},
) {
  return {
    ...previousRequest,
    preflight_id: preflightId,
    confirmed_boundaries: [...confirmedBoundaries],
    disabled_boundaries: [...disabledBoundaries],
  };
}
