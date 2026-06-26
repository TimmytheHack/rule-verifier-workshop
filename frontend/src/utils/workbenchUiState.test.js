import assert from 'node:assert/strict';
import test from 'node:test';

import {
  mergePromptText,
  primaryWorkbenchRunLabel,
  workbenchProcessingStatus,
} from './workbenchUiState.js';

test('primaryWorkbenchRunLabel shows query progress for built-in data while loading', () => {
  assert.equal(primaryWorkbenchRunLabel({
    loading: true,
    shouldUsePreflight: false,
    currentPreflightCanQuery: false,
    currentPreflightReady: false,
    mode: 'api',
  }), '正在查询');
});

test('primaryWorkbenchRunLabel keeps preflight progress only for uploaded preflight runs', () => {
  assert.equal(primaryWorkbenchRunLabel({
    loading: true,
    shouldUsePreflight: true,
    currentPreflightCanQuery: false,
    currentPreflightReady: false,
    mode: 'api',
  }), '正在预检');
  assert.equal(primaryWorkbenchRunLabel({
    loading: true,
    shouldUsePreflight: true,
    currentPreflightCanQuery: true,
    currentPreflightReady: true,
    mode: 'api',
  }), '正在查询');
});

test('mergePromptText appends quick examples without replacing existing preferences', () => {
  assert.equal(
    mergePromptText('想学计算机，最好在广州深圳，学校稳一点。', '想找学费两万以内的专业。'),
    '想学计算机，最好在广州深圳，学校稳一点。想找学费两万以内的专业。',
  );
});

test('mergePromptText avoids duplicating the same quick example text', () => {
  assert.equal(
    mergePromptText('想找学费两万以内的专业。', '想找学费两万以内的专业。'),
    '想找学费两万以内的专业。',
  );
  assert.equal(
    mergePromptText(
      '想学计算机，最好在广州深圳，学校稳一点。想找学费两万以内的专业。',
      '想找学费两万以内的专业。',
    ),
    '想学计算机，最好在广州深圳，学校稳一点。想找学费两万以内的专业。',
  );
});

test('workbenchProcessingStatus labels non-actionable confirmation responses as tips', () => {
  assert.deepEqual(workbenchProcessingStatus({
    status: 'needs_confirmation',
    confirmationSummary: {
      confirmableCount: 0,
      warningOnlyCount: 1,
    },
  }), { label: '有提示', tone: 'info' });
});

test('workbenchProcessingStatus keeps actionable confirmation responses explicit', () => {
  assert.deepEqual(workbenchProcessingStatus({
    status: 'needs_confirmation',
    confirmationSummary: {
      confirmableCount: 1,
      warningOnlyCount: 0,
    },
  }), { label: '待确认', tone: 'needs_confirmation' });
});
