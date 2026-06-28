import { authHeaders, requestJson } from './client.js';

export function listDatasets() {
  return requestJson('/datasets');
}

export function datasetProfile(datasetId) {
  return requestJson(`/datasets/${datasetPath(datasetId)}/profile`);
}

export function reviewSummary(datasetId) {
  return requestJson(`/datasets/${datasetPath(datasetId)}/review-summary`);
}

export function uploadDataset({ file, datasetId, sheetName }) {
  if (!file) {
    return Promise.reject(new Error('请选择要上传的表格文件。'));
  }
  const params = new URLSearchParams({ filename: file.name || 'dataset' });
  if (datasetId) params.set('dataset_id', datasetId);
  if (sheetName) params.set('sheet_name', sheetName);
  return fetch(`/datasets/upload?${params.toString()}`, {
    method: 'POST',
    headers: authHeaders(),
    body: file,
  }).then(handleUploadResponse);
}

export function generateDomainPack(datasetId, payload = {}) {
  return requestJson(`/datasets/${datasetPath(datasetId)}/generate-domain-pack`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function approveDomain(datasetId, payload = {}) {
  return requestJson(`/datasets/${datasetPath(datasetId)}/approve-domain`, {
    method: 'POST',
    body: JSON.stringify({
      title_field: null,
      primary_fields: [],
      reviewed_by: 'local_user_web',
      ...payload,
    }),
  });
}

export function buildWarehouse(datasetId) {
  return requestJson(`/datasets/${datasetPath(datasetId)}/build-warehouse`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function preflightDatasetQuery({
  datasetId,
  domainName,
  userInput,
  hardFilters = {},
  softPreferences = {},
  model = '',
  plannerMode = 'auto',
}) {
  return requestJson('/workbench/preflight', {
    method: 'POST',
    body: JSON.stringify({
      dataset_id: datasetId,
      domain_name: domainName,
      user_input: userInput,
      hard_filters: hardFilters,
      soft_preferences: softPreferences,
      model,
      planner_mode: plannerMode,
    }),
  });
}

export function runDatasetQuery({
  datasetId,
  domainName,
  userInput,
  hardFilters = {},
  softPreferences = {},
  extractor = 'regex',
  generator = 'template_evidence',
  model = '',
  plannerMode = 'auto',
  confirmedCandidates = [],
  preflightId = null,
  confirmedBoundaries = [],
  disabledBoundaries = [],
}) {
  return requestJson('/workbench/query', {
    method: 'POST',
    body: JSON.stringify({
      dataset_id: datasetId,
      domain_name: domainName,
      user_input: userInput,
      hard_filters: hardFilters,
      soft_preferences: softPreferences,
      extractor,
      generator,
      model,
      planner_mode: plannerMode,
      confirmed_candidates: confirmedCandidates,
      preflight_id: preflightId,
      confirmed_boundaries: confirmedBoundaries,
      disabled_boundaries: disabledBoundaries,
    }),
  });
}

async function handleUploadResponse(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(uploadErrorMessage(payload, response.status));
  }
  return payload;
}

function uploadErrorMessage(payload, status) {
  if (payload?.detail && typeof payload.detail === 'object' && payload.detail.message) {
    return payload.detail.message;
  }
  if (typeof payload?.detail === 'string') {
    return payload.detail;
  }
  return `上传失败：${status}`;
}

function datasetPath(datasetId) {
  return encodeURIComponent(datasetId);
}
