import assert from 'node:assert/strict';
import test from 'node:test';

import { mergeApprovedDatasetState } from './uploadDatasetState.js';

test('mergeApprovedDatasetState preserves dataset metadata after approve-domain', () => {
  const current = {
    dataset_id: 'ds_admissions',
    status: 'needs_review',
    domain_pack_status: 'needs_review',
    source_name: 'admissions.xlsx',
  };
  const approval = {
    dataset_id: 'ds_admissions',
    ok: true,
    payload: {
      domain_pack_status: 'approved',
    },
  };

  assert.deepEqual(mergeApprovedDatasetState(current, approval), {
    dataset_id: 'ds_admissions',
    status: 'approved',
    domain_pack_status: 'approved',
    source_name: 'admissions.xlsx',
    last_review_result: approval,
  });
});

test('mergeApprovedDatasetState keeps current metadata when approval fails', () => {
  const current = {
    dataset_id: 'ds_admissions',
    status: 'needs_review',
    domain_pack_status: 'needs_review',
  };
  const approval = {
    dataset_id: 'ds_admissions',
    ok: false,
    payload: {
      domain_pack_status: 'needs_review',
    },
  };

  assert.deepEqual(mergeApprovedDatasetState(current, approval), {
    ...current,
    last_review_result: approval,
  });
});
