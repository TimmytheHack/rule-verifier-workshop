import assert from 'node:assert/strict';
import test from 'node:test';

import { selectedRawUploadFile } from './uploadFiles.js';

test('selectedRawUploadFile returns Element Plus raw file', () => {
  const rawFile = new File(['name,score'], 'admissions.csv', { type: 'text/csv' });
  const uploadFile = {
    name: rawFile.name,
    status: 'ready',
    raw: rawFile,
  };

  assert.equal(selectedRawUploadFile(uploadFile), rawFile);
});

test('selectedRawUploadFile accepts direct File values', () => {
  const rawFile = new File(['x'], 'admissions.xlsx');

  assert.equal(selectedRawUploadFile(rawFile), rawFile);
});

test('selectedRawUploadFile returns null for empty upload state', () => {
  assert.equal(selectedRawUploadFile(null), null);
  assert.equal(selectedRawUploadFile({ name: 'missing-raw.xlsx' }), null);
});
