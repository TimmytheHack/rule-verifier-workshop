import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatModeTag,
  formatOptionsSourceTag,
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
