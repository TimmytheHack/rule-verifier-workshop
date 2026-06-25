import assert from 'node:assert/strict';
import test from 'node:test';

import { BUILTIN_ADMISSIONS_SOURCE, createUploadedAdmissionsSource } from '../domain/admissionsAdapter.js';
import {
  DATA_SOURCES_STORAGE_KEY,
  SELECTED_SOURCE_STORAGE_KEY,
  browserStorage,
  loadSelectedDataSourceId,
  loadUploadedDataSources,
  mergeUploadedDataSource,
  persistSelectedDataSourceId,
  persistUploadedDataSources,
} from './dataSourceRegistry.js';

function memoryStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (key) => store.has(key) ? store.get(key) : null,
    setItem: (key, value) => store.set(key, String(value)),
  };
}

function withThrowingBrowserStorage(callback) {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {},
  });
  Object.defineProperty(globalThis.window, 'localStorage', {
    configurable: true,
    get: () => {
      throw new Error('localStorage unavailable');
    },
  });

  try {
    callback();
  } finally {
    if (originalWindow) {
      Object.defineProperty(globalThis, 'window', originalWindow);
    } else {
      delete globalThis.window;
    }
  }
}

test('browserStorage returns null when localStorage access throws', () => {
  withThrowingBrowserStorage(() => {
    assert.equal(browserStorage(), null);
  });
});

test('storage helpers tolerate unavailable browser storage', () => {
  withThrowingBrowserStorage(() => {
    assert.deepEqual(loadUploadedDataSources(), []);
    assert.equal(loadSelectedDataSourceId({ sources: [] }), BUILTIN_ADMISSIONS_SOURCE.id);
    assert.doesNotThrow(() => persistUploadedDataSources(undefined, []));
    assert.doesNotThrow(() => persistSelectedDataSourceId(undefined, 'uploaded:ds_1'));
  });
});

test('loadUploadedDataSources ignores malformed storage', () => {
  const storage = memoryStorage({ [DATA_SOURCES_STORAGE_KEY]: '{bad json' });
  assert.deepEqual(loadUploadedDataSources(storage), []);
});

test('loadSelectedDataSourceId falls back to builtin for stale selection', () => {
  const sources = [createUploadedAdmissionsSource({ dataset_id: 'ds_1' })];
  const storage = memoryStorage({ [SELECTED_SOURCE_STORAGE_KEY]: 'uploaded:missing' });
  assert.equal(loadSelectedDataSourceId({ storage, sources }), BUILTIN_ADMISSIONS_SOURCE.id);
});

test('loadSelectedDataSourceId accepts saved uploaded source from named options', () => {
  const sources = [createUploadedAdmissionsSource({ dataset_id: 'ds_1' })];
  const storage = memoryStorage({ [SELECTED_SOURCE_STORAGE_KEY]: 'uploaded:ds_1' });
  assert.equal(loadSelectedDataSourceId({ storage, sources }), 'uploaded:ds_1');
});

test('mergeUploadedDataSource replaces same id and keeps newest first', () => {
  const oldSource = createUploadedAdmissionsSource({ dataset_id: 'ds_old' });
  const first = createUploadedAdmissionsSource({ dataset_id: 'ds_1', file_name: 'old.xlsx' });
  const updated = createUploadedAdmissionsSource({ dataset_id: 'ds_1', file_name: 'new.xlsx' });

  const merged = mergeUploadedDataSource([oldSource, first], updated);

  assert.deepEqual(merged.map((item) => item.id), ['uploaded:ds_1', 'uploaded:ds_old']);
  assert.equal(merged[0].label, '上传：new.xlsx');
});

test('persist helpers write stable JSON and selected source id', () => {
  const storage = memoryStorage();
  const source = createUploadedAdmissionsSource({ dataset_id: 'ds_1' });

  persistUploadedDataSources(storage, [source]);
  persistSelectedDataSourceId(storage, source.id);

  assert.deepEqual(JSON.parse(storage.getItem(DATA_SOURCES_STORAGE_KEY)), [source]);
  assert.equal(storage.getItem(SELECTED_SOURCE_STORAGE_KEY), 'uploaded:ds_1');
});
