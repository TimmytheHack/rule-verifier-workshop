import assert from 'node:assert/strict';
import test from 'node:test';

import {
  confirmableCandidates,
  createEmptyWorkbenchState,
  isEmptyWorkbenchState,
  mergeDemoRun,
  splitCandidateConfirmationState,
} from './workbenchState.js';
import {
  FALLBACK_WORKBENCH_OPTIONS,
  firstOptionValue,
  normalizeWorkbenchOptions,
} from './workbenchOptions.js';
import {
  buildConfirmedWorkbenchRequest,
  buildWorkbenchRequest,
} from './workbenchRequests.js';

test('createEmptyWorkbenchState does not expose mock results', () => {
  const state = createEmptyWorkbenchState();

  assert.equal(state.status, 'idle');
  assert.equal(state.result_count, 0);
  assert.deepEqual(state.items, []);
  assert.deepEqual(state.top_results, []);
  assert.equal(isEmptyWorkbenchState(state), true);
});

test('mergeDemoRun marks data as explicit demo only after user action', () => {
  const demo = {
    status: 'ok',
    result_count: 1,
    top_results: [{ university_name: '演示大学' }],
  };
  const merged = mergeDemoRun(demo, {
    selectedOptions: { extractor: 'regex' },
  });

  assert.equal(merged.status, 'ok');
  assert.equal(merged.result_count, 1);
  assert.equal(merged.frontend_state.source, 'demo');
  assert.equal(merged.frontend_state.is_explicit_demo, true);
  assert.equal(merged.selected_options.extractor, 'regex');
});

test('confirmableCandidates keeps only candidates with generated candidate_id values', () => {
  const candidates = confirmableCandidates({
    candidates_to_confirm: [
      { candidate_id: 'c_city', label: '广州' },
      { id: 'legacy_id', preference: '软件工程' },
      { preference: '没有 id' },
    ],
  });

  assert.deepEqual(
    candidates.map((candidate) => candidate.confirmationId),
    ['c_city'],
  );
});

test('splitCandidateConfirmationState keeps id-only candidates warning-only', () => {
  const split = splitCandidateConfirmationState({
    candidates_to_confirm: [
      { candidate_id: 'c_city', label: '广州' },
      { id: 'legacy_id', preference: '软件工程' },
      { preference: '没有 id' },
    ],
  });

  assert.deepEqual(
    split.confirmable.map((candidate) => candidate.confirmationId),
    ['c_city'],
  );
  assert.deepEqual(
    split.blocked.map((candidate) => candidate.preference),
    ['软件工程', '没有 id'],
  );
});

test('normalizeWorkbenchOptions prefers API payload and falls back per group', () => {
  const options = normalizeWorkbenchOptions({
    extractors: [{ value: 'hybrid', label: '规则优先，LLM 补槽' }],
    generators: [{ value: 'template_evidence', label: '模板证据回答' }],
    models: [{ value: 'deepseek-v4-flash', label: 'LLM 快速模型' }],
    rank_windows: [{ value: 'steady', label: '稳一点', rank_window_upper_percent: 15 }],
    sort_modes: [{ value: 'rank_desc', label: '按历史位次从低到高看（更稳）' }],
  });

  assert.equal(options.source, 'api');
  assert.equal(options.extractors[0].value, 'hybrid');
  assert.equal(options.rank_windows[0].description, '');
});

test('normalizeWorkbenchOptions uses complete fallback when API payload is empty', () => {
  const options = normalizeWorkbenchOptions(null);

  assert.equal(options.source, 'fallback');
  assert.deepEqual(options.extractors, FALLBACK_WORKBENCH_OPTIONS.extractors);
  assert.equal(options.rank_windows.length, 3);
});

test('normalizeWorkbenchOptions marks missing API option groups as partial fallback', () => {
  const options = normalizeWorkbenchOptions({
    extractors: [{ value: 'hybrid', label: '规则优先，LLM 补槽' }],
    generators: [],
    models: [{ value: 'deepseek-v4-flash', label: 'LLM 快速模型' }],
    rank_windows: [{ value: 'steady', label: '稳一点', rank_window_upper_percent: 15 }],
    sort_modes: [{ value: 'rank_desc', label: '按历史位次从低到高看（更稳）' }],
  });

  assert.equal(options.source, 'partial_fallback');
  assert.deepEqual(options.generators, FALLBACK_WORKBENCH_OPTIONS.generators);
});

test('normalizeWorkbenchOptions isolates fallback options from mutation', () => {
  const options = normalizeWorkbenchOptions(null);

  options.extractors[0].label = '被修改的标签';

  assert.equal(FALLBACK_WORKBENCH_OPTIONS.extractors[0].label, '规则优先，LLM 补槽');
});

test('firstOptionValue returns the first value or provided fallback', () => {
  assert.equal(
    firstOptionValue([{ value: 'hybrid' }, { value: 'regex' }], 'regex'),
    'hybrid',
  );
  assert.equal(firstOptionValue([], 'template_evidence'), 'template_evidence');
  assert.equal(firstOptionValue(null, 'deepseek-v4-flash'), 'deepseek-v4-flash');
});

test('buildWorkbenchRequest includes dataset id only for uploaded sources', () => {
  const request = buildWorkbenchRequest({
    source: {
      type: 'uploaded',
      datasetId: 'dataset_1',
      domainName: 'admissions',
      label: '上传：a.xlsx',
    },
    runRequest: {
      user_input: '广东物理，排位 32000。',
      hard_filters: { user_rank: 32000 },
      soft_preferences: { prompt: '想学计算机' },
    },
    extractor: 'hybrid',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  });

  assert.equal(request.dataset_id, 'dataset_1');
  assert.equal(request.domain_name, 'admissions');
  assert.equal(request.extractor, 'hybrid');
  assert.deepEqual(request.confirmed_candidates, []);
});

test('buildWorkbenchRequest omits dataset id for bundled sources', () => {
  const request = buildWorkbenchRequest({
    source: {
      type: 'bundled',
      datasetId: 'demo_dataset',
      domainName: 'admissions',
      label: '内置演示数据',
    },
    runRequest: {
      user_input: '广东物理，排位 32000。',
      hard_filters: { user_rank: 32000 },
      soft_preferences: { prompt: '想学计算机' },
    },
    extractor: 'hybrid',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  });

  assert.equal('dataset_id' in request, false);
  assert.equal(request.domain_name, 'admissions');
});

test('buildConfirmedWorkbenchRequest reuses previous request and appends candidate ids', () => {
  const previous = {
    domain_name: 'admissions',
    user_input: '广东物理，排位 32000。',
    hard_filters: { user_rank: 32000 },
    soft_preferences: { prompt: '想学计算机' },
    extractor: 'regex',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  };

  const request = buildConfirmedWorkbenchRequest(previous, ['c_city', 'c_major']);

  assert.deepEqual(request.confirmed_candidates, ['c_city', 'c_major']);
  assert.equal(request.user_input, previous.user_input);
  assert.notEqual(request, previous);
});

test('buildConfirmedWorkbenchRequest preserves existing confirmed candidate ids', () => {
  const previous = {
    domain_name: 'admissions',
    user_input: '广东物理，排位 32000。',
    hard_filters: { user_rank: 32000 },
    soft_preferences: { prompt: '想学计算机' },
    confirmed_candidates: ['c_city'],
  };

  const request = buildConfirmedWorkbenchRequest(previous, ['c_major']);

  assert.deepEqual(request.confirmed_candidates, ['c_city', 'c_major']);
  assert.notEqual(request.confirmed_candidates, previous.confirmed_candidates);
});
