import assert from 'node:assert/strict';
import test from 'node:test';

import { runAdmissionsImportPipeline } from './importPipeline.js';

function fakeFile(name = '录取表.xlsx') {
  return { name };
}

test('runAdmissionsImportPipeline calls dataset APIs in order', async () => {
  const calls = [];
  const requestJson = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body });
    if (url.startsWith('/datasets/upload')) {
      return { dataset_id: 'ds_1', source_name: '录取表.xlsx' };
    }
    if (url.endsWith('/generate-domain-pack')) {
      return { dataset_id: 'ds_1', domain_template_id: 'admissions_schema_v1' };
    }
    if (url.endsWith('/profile')) {
      return { fields: [] };
    }
    if (url.endsWith('/review-summary')) {
      return { reviewable_fields: [] };
    }
    if (url.endsWith('/approve-domain')) {
      return { ok: true, payload: { domain_pack_status: 'approved' } };
    }
    if (url.endsWith('/build-warehouse')) {
      return {
        dataset_id: 'ds_1',
        domain_name: 'admissions',
        status: 'queryable',
        source_name: '录取表.xlsx',
        warehouse: { row_count: 10, column_count: 4 },
      };
    }
    throw new Error(`unexpected url ${url}`);
  };

  const result = await runAdmissionsImportPipeline({
    file: fakeFile(),
    requestJson,
    onStep: () => {},
  });

  assert.deepEqual(calls.map((call) => call.url), [
    '/datasets/upload?filename=%E5%BD%95%E5%8F%96%E8%A1%A8.xlsx',
    '/datasets/ds_1/generate-domain-pack',
    '/datasets/ds_1/profile',
    '/datasets/ds_1/review-summary',
    '/datasets/ds_1/approve-domain',
    '/datasets/ds_1/build-warehouse',
  ]);
  assert.equal(result.dataset.dataset_id, 'ds_1');
  assert.equal(result.dataset.status, 'queryable');
});

test('runAdmissionsImportPipeline stops when approve-domain reports business failure', async () => {
  const visited = [];
  const requestJson = async (url) => {
    visited.push(url);
    if (url.startsWith('/datasets/upload')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/generate-domain-pack')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/profile')) return {};
    if (url.endsWith('/review-summary')) return {};
    if (url.endsWith('/approve-domain')) {
      return { ok: false, payload: { failures: ['primary field 不存在：city'] } };
    }
    throw new Error('build warehouse must not run after failed approval');
  };

  await assert.rejects(
    () => runAdmissionsImportPipeline({ file: fakeFile(), requestJson, onStep: () => {} }),
    /字段模板审核未通过/,
  );
  assert.equal(visited.some((url) => url.endsWith('/build-warehouse')), false);
});

test('runAdmissionsImportPipeline rejects blocked warehouse builds', async () => {
  const stepEvents = [];
  const requestJson = async (url) => {
    if (url.startsWith('/datasets/upload')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/generate-domain-pack')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/profile')) return { fields: [] };
    if (url.endsWith('/review-summary')) return { reviewable_fields: [] };
    if (url.endsWith('/approve-domain')) {
      return { ok: true, payload: { domain_pack_status: 'approved' } };
    }
    if (url.endsWith('/build-warehouse')) {
      return {
        dataset_id: 'ds_1',
        status: 'blocked',
        warehouse_audit: {
          ok: false,
          warnings: [{ code: 'ambiguous_admissions_score_fields' }],
        },
      };
    }
    throw new Error(`unexpected url ${url}`);
  };

  await assert.rejects(
    () => runAdmissionsImportPipeline({
      file: fakeFile(),
      requestJson,
      onStep: (event) => stepEvents.push(event),
    }),
    /生成可查询数据未通过校验/,
  );

  assert.deepEqual(stepEvents.at(-1), {
    key: 'build_warehouse',
    status: 'error',
    details: { message: '生成可查询数据未通过校验：ambiguous_admissions_score_fields' },
  });
});

test('runAdmissionsImportPipeline marks failed API step and stops later steps', async () => {
  const visited = [];
  const stepEvents = [];
  const requestJson = async (url) => {
    visited.push(url);
    if (url.startsWith('/datasets/upload')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/generate-domain-pack')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/profile')) throw new Error('profile exploded');
    throw new Error(`unexpected later url ${url}`);
  };

  await assert.rejects(
    () => runAdmissionsImportPipeline({
      file: fakeFile(),
      requestJson,
      onStep: (event) => stepEvents.push(event),
    }),
    /profile exploded/,
  );

  assert.deepEqual(visited, [
    '/datasets/upload?filename=%E5%BD%95%E5%8F%96%E8%A1%A8.xlsx',
    '/datasets/ds_1/generate-domain-pack',
    '/datasets/ds_1/profile',
  ]);
  assert.deepEqual(stepEvents.at(-1), {
    key: 'profile',
    status: 'error',
    details: { message: 'profile exploded' },
  });
  assert.equal(stepEvents.some((event) => event.key === 'review_summary'), false);
});
