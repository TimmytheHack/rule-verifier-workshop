import assert from 'node:assert/strict';
import test from 'node:test';

import { collapseDuplicateDatasets } from './datasetList.js';

test('collapseDuplicateDatasets keeps the best version of repeated uploads', () => {
  const payload = collapseDuplicateDatasets([
    {
      dataset_id: 'ds_old_review',
      status: 'needs_review',
      source_fingerprint: 'same_hash',
      updated_at: '2026-06-28T09:00:00Z',
    },
    {
      dataset_id: 'ds_new_queryable',
      status: 'queryable',
      source_fingerprint: 'same_hash',
      updated_at: '2026-06-28T10:00:00Z',
    },
    {
      dataset_id: 'ds_other',
      status: 'queryable',
      source_fingerprint: 'other_hash',
      updated_at: '2026-06-28T08:00:00Z',
    },
  ]);

  assert.equal(payload.hiddenCount, 1);
  assert.deepEqual(
    payload.datasets.map((dataset) => dataset.dataset_id),
    ['ds_new_queryable', 'ds_other'],
  );
});

test('collapseDuplicateDatasets falls back to file shape when fingerprint is absent', () => {
  const payload = collapseDuplicateDatasets([
    {
      dataset_id: 'ds_first',
      status: 'queryable',
      original_filename: 'rows.xlsx',
      row_count: 10,
      column_count: 3,
      updated_at: '2026-06-28T09:00:00Z',
    },
    {
      dataset_id: 'ds_second',
      status: 'queryable',
      original_filename: 'ROWS.xlsx',
      row_count: 10,
      column_count: 3,
      updated_at: '2026-06-28T10:00:00Z',
    },
  ]);

  assert.equal(payload.hiddenCount, 1);
  assert.equal(payload.datasets[0].dataset_id, 'ds_second');
});
