import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildQueryControls,
  summarizeDatasetCapability,
} from './queryOptions.js';

test('summarizeDatasetCapability ignores template ids and uses capability fields', () => {
  const summary = summarizeDatasetCapability({
    domain_template_id: 'legacy_template_x',
    capability_level: 'admissions_filterable',
    recommendation_readiness: 'candidate_list',
    semantic_query_options: {
      query_types: ['admissions_major_rank'],
      required_user_context: ['user_rank'],
    },
  });

  assert.equal(summary.label, '可查询候选列表');
  assert.equal(summary.requiresUserRank, true);
  assert.equal(summary.canCallRecommendation, false);
});

test('buildQueryControls renders filters and sort fields from backend options', () => {
  const controls = buildQueryControls({
    filters: {
      city: { source_column: '城市', allowed_ops: ['contains'], field_type: 'text' },
      tuition: { source_column: '学费', allowed_ops: ['between'], field_type: 'number' },
    },
    sort_fields: {
      tuition: { source_column: '学费', field_type: 'number' },
    },
    required_user_context: ['user_rank'],
  });

  assert.deepEqual(
    controls.requiredInputs.map((item) => item.id),
    ['user_rank'],
  );
  assert.deepEqual(
    controls.filters.map((item) => item.id),
    ['city', 'tuition'],
  );
  assert.equal(controls.sortFields[0].label, '学费');
});
