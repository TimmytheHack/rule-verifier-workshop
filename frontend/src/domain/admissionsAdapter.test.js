import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ADMISSIONS_DOMAIN,
  BUILTIN_ADMISSIONS_SOURCE,
  createUploadedAdmissionsSource,
  shouldUseUploadedAdmissionsPreflight,
} from './admissionsAdapter.js';

test('admissions domain centralizes reviewed template settings', () => {
  assert.equal(ADMISSIONS_DOMAIN.domainName, 'admissions');
  assert.equal(ADMISSIONS_DOMAIN.templateId, 'admissions_schema_v1');
  assert.equal(ADMISSIONS_DOMAIN.supportsPreflight, true);
  assert.equal(ADMISSIONS_DOMAIN.resultRenderer, 'admissions');
});

test('builtin admissions source is not treated as uploaded dataset', () => {
  assert.equal(BUILTIN_ADMISSIONS_SOURCE.id, 'builtin_admissions');
  assert.equal(BUILTIN_ADMISSIONS_SOURCE.type, 'builtin');
  assert.equal(BUILTIN_ADMISSIONS_SOURCE.datasetId, null);
  assert.equal(shouldUseUploadedAdmissionsPreflight(BUILTIN_ADMISSIONS_SOURCE, 'api'), false);
});

test('uploaded admissions source normalizes warehouse metadata', () => {
  const source = createUploadedAdmissionsSource({
    dataset_id: 'ds_1',
    domain_name: 'admissions',
    file_name: '录取表.xlsx',
    warehouse: { row_count: 1200, column_count: 27 },
    updated_at: '2026-06-25T06:30:00.000Z',
  });

  assert.equal(source.id, 'uploaded:ds_1');
  assert.equal(source.type, 'uploaded');
  assert.equal(source.datasetId, 'ds_1');
  assert.equal(source.domainName, 'admissions');
  assert.equal(source.label, '上传：录取表.xlsx');
  assert.equal(source.description, '1,200 行，27 列，使用上传表格查询。');
  assert.equal(source.rowCount, 1200);
  assert.equal(source.columnCount, 27);
  assert.equal(source.updatedAt, '2026-06-25T06:30:00.000Z');
});

test('uploaded admissions source preserves zero warehouse counts', () => {
  const source = createUploadedAdmissionsSource({
    dataset_id: 'ds_empty',
    warehouse: { row_count: 0, column_count: 0 },
  });

  assert.equal(source.rowCount, 0);
  assert.equal(source.columnCount, 0);
});

test('uploaded admissions source ignores null payload', () => {
  assert.equal(createUploadedAdmissionsSource(null), null);
});

test('uploaded admissions preflight only applies in API mode', () => {
  const source = createUploadedAdmissionsSource({
    dataset_id: 'ds_1',
    domain_name: 'admissions',
    source_name: '录取表.xlsx',
  });

  assert.equal(shouldUseUploadedAdmissionsPreflight(source, 'api'), true);
  assert.equal(shouldUseUploadedAdmissionsPreflight(source, 'demo'), false);
  assert.equal(shouldUseUploadedAdmissionsPreflight({ ...source, domainName: 'other' }, 'api'), false);
});
