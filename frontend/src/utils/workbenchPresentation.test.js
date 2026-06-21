import assert from 'node:assert/strict';
import test from 'node:test';

import {
  defaultWorkbenchMode,
  describeDataSourceState,
} from './workbenchPresentation.js';

test('defaultWorkbenchMode starts api-first for builtin sources', () => {
  assert.equal(defaultWorkbenchMode('builtin_admissions'), 'api');
  assert.equal(defaultWorkbenchMode('uploaded:dataset_1'), 'api');
  assert.equal(defaultWorkbenchMode(null), 'api');
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
