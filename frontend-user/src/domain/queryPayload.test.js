import assert from 'node:assert/strict';
import test from 'node:test';

import { buildWorkbenchPayload } from './queryOptions.js';

test('buildWorkbenchPayload sends only schema-declared fields as hard filters', () => {
  const payload = buildWorkbenchPayload({
    prompt: '想找广州的低学费项目',
    userContext: { user_rank: '15000', unsupported_context: 'x' },
    filterValues: {
      city: '广州',
      unknown_field: '不要发送',
      tuition: '',
    },
    options: {
      required_user_context: ['user_rank'],
      filters: {
        city: { allowed_ops: ['contains'], field_type: 'text', source_column: '城市' },
        tuition: { allowed_ops: ['<='], field_type: 'number', source_column: '学费' },
      },
    },
  });

  assert.equal(payload.user_input, '想找广州的低学费项目');
  assert.deepEqual(payload.hard_filters, {
    user_rank: 15000,
    city: { op: 'contains', value: '广州' },
  });
  assert.deepEqual(payload.soft_preferences, {
    prompt: '想找广州的低学费项目',
  });
});

test('buildWorkbenchPayload keeps empty prompt valid without inventing filters', () => {
  const payload = buildWorkbenchPayload({
    prompt: '',
    userContext: {},
    filterValues: {},
    options: {
      required_user_context: ['user_rank'],
      filters: {
        major: { allowed_ops: ['contains_any'], field_type: 'text' },
      },
    },
  });

  assert.equal(payload.user_input, '查询');
  assert.deepEqual(payload.hard_filters, {});
  assert.deepEqual(payload.soft_preferences, { prompt: '查询' });
});
