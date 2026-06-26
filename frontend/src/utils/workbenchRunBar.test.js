import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatModeTag,
  formatOptionsSourceTag,
  hasDisplayableRunData,
  normalizeRunBarStatus,
} from './workbenchRunBar.js';

test('formatModeTag labels api and demo modes for the run bar', () => {
  assert.deepEqual(formatModeTag('api'), { type: 'warning', label: '后端查询' });
  assert.deepEqual(formatModeTag('demo'), { type: 'info', label: '演示数据' });
});

test('formatOptionsSourceTag labels backend and fallback option sources', () => {
  assert.deepEqual(formatOptionsSourceTag('api'), { type: 'success', label: '后端选项' });
  assert.deepEqual(formatOptionsSourceTag('partial_fallback'), { type: 'warning', label: '部分本地选项' });
  assert.deepEqual(formatOptionsSourceTag('fallback'), { type: 'info', label: '本地保守选项' });
});

test('hasDisplayableRunData distinguishes initial empty state from completed runs', () => {
  assert.equal(hasDisplayableRunData({
    status: 'idle',
    result_count: 0,
    items: [],
    top_results: [],
    frontend_state: { source: 'empty', is_explicit_demo: false },
  }), false);
  assert.equal(hasDisplayableRunData({ status: 'no_results', result_count: 0 }), true);
  assert.equal(hasDisplayableRunData({
    status: 'ok',
    result_count: 0,
    frontend_state: { source: 'demo', is_explicit_demo: true },
  }), true);
});

test('normalizeRunBarStatus shows pending for initial empty state', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: false,
    lastRunFailed: false,
    runData: {
      status: 'idle',
      result_count: 0,
      frontend_state: { source: 'empty' },
    },
  }), { type: 'info', label: '待查询' });
});

test('normalizeRunBarStatus shows running while loading', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: true,
    lastRunFailed: false,
    runData: { status: 'ok', result_count: 3 },
  }), { type: 'warning', label: '查询中' });
});

test('normalizeRunBarStatus lets failure win over prior successful data', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: false,
    lastRunFailed: true,
    runData: { status: 'ok', result_count: 3 },
  }), { type: 'danger', label: '查询失败' });
});

test('normalizeRunBarStatus treats needs_confirmation with confirmable candidates as actionable', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: false,
    lastRunFailed: false,
    runData: {
      status: 'needs_confirmation',
      result_count: 0,
      candidates_to_confirm: [{ candidate_id: 'c_city', preference: '广州' }],
    },
  }), { type: 'warning', label: '待确认' });
});

test('normalizeRunBarStatus treats needs_confirmation with only warning candidates as informational', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: false,
    lastRunFailed: false,
    runData: {
      status: 'needs_confirmation',
      result_count: 0,
      candidates_to_confirm: [{ preference: '离家近', reason: '没有距离字段' }],
    },
  }), { type: 'info', label: '有提示' });
});

test('normalizeRunBarStatus treats needs_confirmation without candidate items as completed', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: false,
    lastRunFailed: false,
    runData: { status: 'needs_confirmation', result_count: 0 },
  }), { type: 'success', label: '已完成' });
});

test('normalizeRunBarStatus treats blocked with zero results as blocked', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: false,
    lastRunFailed: false,
    runData: { status: 'blocked', result_count: 0 },
  }), { type: 'danger', label: '已阻断' });
});

test('normalizeRunBarStatus treats no_results as a no-results response', () => {
  assert.deepEqual(normalizeRunBarStatus({
    loading: false,
    lastRunFailed: false,
    runData: { status: 'no_results', result_count: 0 },
  }), { type: 'info', label: '无结果' });
});
