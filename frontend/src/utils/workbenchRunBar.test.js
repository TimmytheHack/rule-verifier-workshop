import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatModeTag,
  formatOptionsSourceTag,
  hasDisplayableRunData,
} from './workbenchRunBar.js';

test('formatModeTag labels api and demo modes for the run bar', () => {
  assert.deepEqual(formatModeTag('api'), { type: 'warning', label: 'API 查询' });
  assert.deepEqual(formatModeTag('demo'), { type: 'info', label: '演示数据' });
});

test('formatOptionsSourceTag labels backend and fallback option sources', () => {
  assert.deepEqual(formatOptionsSourceTag('api'), { type: 'success', label: '后端选项' });
  assert.deepEqual(formatOptionsSourceTag('partial_fallback'), { type: 'warning', label: '部分 fallback' });
  assert.deepEqual(formatOptionsSourceTag('fallback'), { type: 'info', label: 'fallback' });
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
