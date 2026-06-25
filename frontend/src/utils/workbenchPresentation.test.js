import assert from 'node:assert/strict';
import test from 'node:test';

import * as presentation from './workbenchPresentation.js';
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

test('resultRowsForDisplay enriches group detail item rows with nested majors', () => {
  assert.equal(typeof presentation.resultRowsForDisplay, 'function');

  const major = {
    major_code: '0809',
    major_name: '计算机类',
    min_score: 0,
  };
  const runData = {
    query_type: 'group_detail_report',
    items: [
      {
        item_id: 'group_001',
        title: '深圳大学',
        raw: {
          group_code: ' 10590221 ',
        },
      },
    ],
    result_sections: {
      groups: [
        {
          group_code: '10590221 ',
          group_title: '221组',
          majors: [major],
        },
      ],
    },
  };

  const rows = presentation.resultRowsForDisplay(runData);

  assert.equal(rows.length, 1);
  assert.equal(rows[0].title, '深圳大学');
  assert.equal(rows[0].group_detail, true);
  assert.deepEqual(rows[0].majors, [major]);
  assert.equal(runData.items[0].majors, undefined);
});

test('groupMajorSections ignores unrelated items arrays', () => {
  assert.equal(typeof presentation.groupMajorSections, 'function');

  const sections = presentation.groupMajorSections({
    item_id: 'generic_001',
    title: '普通结果',
    items: [
      {
        item_id: 'note_001',
        title: '普通子项',
      },
    ],
  });

  assert.deepEqual(sections, []);
});

test('groupMajorSections requires a parent group marker before using items as majors', () => {
  const sections = presentation.groupMajorSections({
    item_id: 'generic_002',
    title: '普通结果',
    items: [
      {
        major_name: '计算机类',
        min_score: 620,
      },
    ],
  });

  assert.deepEqual(sections, []);
});

test('groupMajorTitle prefers full names when repeated short names differ', () => {
  const majors = [
    {
      major_name: '计算机类',
      full_major_name: '计算机类(软件工程方向)',
    },
    {
      major_name: '计算机类',
      full_major_name: '计算机类(人工智能方向)',
    },
  ];

  assert.deepEqual(
    majors.map((major) => presentation.groupMajorTitle(major)),
    ['计算机类(软件工程方向)', '计算机类(人工智能方向)'],
  );
});

test('group major helpers preserve zero scores from item-shaped major rows', () => {
  assert.equal(typeof presentation.formatGroupMajorScore, 'function');

  const major = {
    item_id: 'major_001',
    title: '计算机类',
    primary_attributes: [
      {
        label: '最低分',
        value: 0,
      },
    ],
  };

  assert.deepEqual(
    presentation.groupMajorSections({
      group_detail: true,
      items: [major],
    }),
    [major],
  );
  assert.equal(presentation.groupMajorTitle(major), '计算机类');
  assert.equal(presentation.groupMajorScore(major), 0);
  assert.equal(presentation.formatGroupMajorScore(major), 0);
});
