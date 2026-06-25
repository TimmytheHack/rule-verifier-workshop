import assert from 'node:assert/strict';
import test from 'node:test';

import {
  admissionsTemplateMismatchMessage,
  approvalFailureMessage,
  mergeApprovedDatasetState,
} from './uploadDatasetState.js';

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

test('approvalFailureMessage explains approve-domain business failures', () => {
  const message = approvalFailureMessage({
    ok: false,
    message: 'approve-domain checks failed',
    payload: {
      failures: ['title field 不存在：university_name', 'primary field 不存在：city'],
    },
  });

  assert.equal(
    message,
    '字段模板审核未通过：title field 不存在：university_name；primary field 不存在：city',
  );
});

test('admissionsTemplateMismatchMessage warns when generated pack missed the reviewed template', () => {
  const message = admissionsTemplateMismatchMessage(
    {
      dataset_id: 'ds_uploaded',
      domain_name: 'admissions',
      domain_template_id: null,
    },
    'admissions',
    'admissions_schema_v1',
  );

  assert.equal(
    message,
    '后端没有应用 admissions_schema_v1 字段模板。请重启后端后重新生成草稿。',
  );
});
