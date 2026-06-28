const STATUS_WEIGHT = {
  queryable: 70,
  approved: 60,
  needs_review: 50,
  profiled: 40,
  uploaded: 30,
  blocked: 20,
  error: 10,
};

export function collapseDuplicateDatasets(datasets = []) {
  const groups = new Map();
  for (const dataset of Array.isArray(datasets) ? datasets : []) {
    const key = duplicateKey(dataset);
    const group = groups.get(key) || [];
    group.push(dataset);
    groups.set(key, group);
  }

  const visible = [];
  let hiddenCount = 0;
  for (const group of groups.values()) {
    const ranked = [...group].sort(compareDatasets);
    visible.push(ranked[0]);
    hiddenCount += Math.max(0, ranked.length - 1);
  }

  visible.sort(compareDatasets);
  return {
    datasets: visible,
    hiddenCount,
  };
}

function duplicateKey(dataset = {}) {
  if (dataset.source_fingerprint) {
    return `fingerprint:${dataset.source_fingerprint}`;
  }
  const filename = String(dataset.original_filename || '').trim().toLowerCase();
  if (filename) {
    return [
      'shape',
      filename,
      dataset.sheet_name || '',
      dataset.row_count ?? '',
      dataset.column_count ?? '',
    ].join(':');
  }
  return `dataset:${dataset.dataset_id || Math.random()}`;
}

function compareDatasets(left, right) {
  const statusDelta = statusWeight(right) - statusWeight(left);
  if (statusDelta !== 0) return statusDelta;
  return timestamp(right) - timestamp(left);
}

function statusWeight(dataset = {}) {
  return STATUS_WEIGHT[dataset.status] || 0;
}

function timestamp(dataset = {}) {
  const value = Date.parse(dataset.updated_at || dataset.created_at || '');
  return Number.isFinite(value) ? value : 0;
}
