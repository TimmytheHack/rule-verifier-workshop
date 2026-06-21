export function buildWorkbenchRequest({
  source,
  runRequest,
  extractor,
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
    generator,
    model,
    confirmed_candidates: [...confirmedCandidates],
  };

  if (source?.datasetId) {
    requestBody.dataset_id = source.datasetId;
  }

  return requestBody;
}

export function buildConfirmedWorkbenchRequest(previousRequest, confirmedCandidates) {
  return {
    ...previousRequest,
    confirmed_candidates: [...confirmedCandidates],
  };
}
