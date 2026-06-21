import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canRerunConfirmedRequest,
  defaultWorkbenchMode,
  describeDataSourceState,
  isActiveWorkbenchResponse,
  shouldShowOptionsLoadError,
} from './workbenchPresentation.js';

test('defaultWorkbenchMode starts api-first', () => {
  assert.equal(defaultWorkbenchMode(), 'api');
});

test('describeDataSourceState distinguishes empty demo mode from explicit demo results', () => {
  const description = describeDataSourceState({
    mode: 'demo',
    selectedDataSource: {
      description: '使用仓库内置 admissions 数据。',
    },
    runData: {
      frontend_state: {
        is_explicit_demo: false,
      },
    },
  });

  assert.equal(description, '演示模式尚未加载演示结果；开始查询前不会展示演示院校。');
});

test('describeDataSourceState labels explicit demo results', () => {
  const description = describeDataSourceState({
    mode: 'demo',
    selectedDataSource: {
      description: '使用仓库内置 admissions 数据。',
    },
    runData: {
      frontend_state: {
        is_explicit_demo: true,
      },
    },
  });

  assert.equal(description, '当前显示演示结果；切到后端后使用所选数据。');
});

test('describeDataSourceState keeps api source description', () => {
  const description = describeDataSourceState({
    mode: 'api',
    selectedDataSource: {
      description: '使用上传表格查询。',
    },
    runData: {},
  });

  assert.equal(description, '使用上传表格查询。');
});

test('shouldShowOptionsLoadError only displays warnings in api mode', () => {
  assert.equal(shouldShowOptionsLoadError('api', '后端选项加载失败'), true);
  assert.equal(shouldShowOptionsLoadError('demo', '后端选项加载失败'), false);
  assert.equal(shouldShowOptionsLoadError('api', ''), false);
});

test('isActiveWorkbenchResponse accepts matching latest request', () => {
  assert.equal(
    isActiveWorkbenchResponse({
      requestId: 2,
      activeRequestId: 2,
      requestDataSourceId: 'uploaded:dataset_1',
      selectedDataSourceId: 'uploaded:dataset_1',
      requestMode: 'api',
      currentMode: 'api',
    }),
    true,
  );
});

test('isActiveWorkbenchResponse rejects stale request identity, source, or mode', () => {
  const activeRequest = {
    requestId: 2,
    activeRequestId: 2,
    requestDataSourceId: 'uploaded:dataset_1',
    selectedDataSourceId: 'uploaded:dataset_1',
    requestMode: 'api',
    currentMode: 'api',
  };

  assert.equal(isActiveWorkbenchResponse({ ...activeRequest, activeRequestId: 3 }), false);
  assert.equal(isActiveWorkbenchResponse({ ...activeRequest, selectedDataSourceId: 'uploaded:dataset_2' }), false);
  assert.equal(isActiveWorkbenchResponse({ ...activeRequest, currentMode: 'demo' }), false);
});

test('canRerunConfirmedRequest accepts matching api request context', () => {
  assert.equal(
    canRerunConfirmedRequest({
      context: {
        requestBody: { user_input: '广东物理，排位 32000。' },
        dataSourceId: 'uploaded:dataset_1',
        mode: 'api',
        inputSignature: 'rank-32000',
      },
      candidateIds: ['c_city'],
      currentMode: 'api',
      selectedDataSourceId: 'uploaded:dataset_1',
      currentInputSignature: 'rank-32000',
    }),
    true,
  );
});

test('canRerunConfirmedRequest rejects stale or non-api confirmation context', () => {
  const context = {
    requestBody: { user_input: '广东物理，排位 32000。' },
    dataSourceId: 'uploaded:dataset_1',
    mode: 'api',
    inputSignature: 'rank-32000',
  };

  assert.equal(
    canRerunConfirmedRequest({
      context: null,
      candidateIds: ['c_city'],
      currentMode: 'api',
      selectedDataSourceId: 'uploaded:dataset_1',
    }),
    false,
  );
  assert.equal(
    canRerunConfirmedRequest({
      context,
      candidateIds: [],
      currentMode: 'api',
      selectedDataSourceId: 'uploaded:dataset_1',
    }),
    false,
  );
  assert.equal(
    canRerunConfirmedRequest({
      context,
      candidateIds: ['c_city'],
      currentMode: 'demo',
      selectedDataSourceId: 'uploaded:dataset_1',
    }),
    false,
  );
  assert.equal(
    canRerunConfirmedRequest({
      context,
      candidateIds: ['c_city'],
      currentMode: 'api',
      selectedDataSourceId: 'uploaded:dataset_2',
      currentInputSignature: 'rank-32000',
    }),
    false,
  );
  assert.equal(
    canRerunConfirmedRequest({
      context: { ...context, mode: 'demo' },
      candidateIds: ['c_city'],
      currentMode: 'api',
      selectedDataSourceId: 'uploaded:dataset_1',
      currentInputSignature: 'rank-32000',
    }),
    false,
  );
  assert.equal(
    canRerunConfirmedRequest({
      context,
      candidateIds: ['c_city'],
      currentMode: 'api',
      selectedDataSourceId: 'uploaded:dataset_1',
      currentInputSignature: 'rank-41000',
    }),
    false,
  );
});
