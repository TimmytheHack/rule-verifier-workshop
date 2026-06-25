import assert from 'node:assert/strict';
import test from 'node:test';

import {
  boundarySelectionsFromPreflight,
  confirmableCandidates,
  createEmptyWorkbenchState,
  isEmptyWorkbenchState,
  mergeDemoRun,
  splitPreflightBoundarySelections,
  splitCandidateConfirmationState,
} from './workbenchState.js';
import {
  FALLBACK_WORKBENCH_OPTIONS,
  firstOptionValue,
  normalizeWorkbenchOptions,
} from './workbenchOptions.js';
import {
  buildConfirmedWorkbenchRequest,
  buildPreflightConfirmedWorkbenchRequest,
  buildWorkbenchPreflightRequest,
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

test('empty state keeps quick stat compatible fields empty', () => {
  const state = createEmptyWorkbenchState({
    selected_options: { extractor: 'hybrid' },
  });

  assert.equal(state.executed_filters.length, 0);
  assert.equal(state.candidates_to_confirm.length, 0);
  assert.equal(state.no_schema_field_preferences.length, 0);
  assert.equal(state.selected_options.extractor, 'hybrid');
});

test('empty state includes detail-tab compatible defaults', () => {
  const state = createEmptyWorkbenchState();

  assert.deepEqual(state.simulated_confirmations, {});
  assert.deepEqual(state.deterministic_rules, []);
  assert.deepEqual(state.extracted_preferences, []);
  assert.deepEqual(state.attribute_grounding, {});
  assert.deepEqual(state.proposed_rules, []);
});

test('empty state includes evidence report compatible defaults', () => {
  const state = createEmptyWorkbenchState();

  assert.equal(state.natural_language_report.title, '');
  assert.equal(state.natural_language_report.summary, '');
  assert.deepEqual(state.natural_language_report.executed_rules, []);
  assert.deepEqual(state.natural_language_report.top_results, []);
  assert.deepEqual(state.natural_language_report.warnings, []);
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

test('confirmableCandidates excludes preferences without generated candidate ids', () => {
  const candidates = confirmableCandidates({
    candidates_to_confirm: [
      { candidate_id: 'c_rank', preference: '稳一点' },
      { preference: '离家近', reason: '没有 schema 字段' },
    ],
  });

  assert.deepEqual(
    candidates.map((candidate) => candidate.confirmationId),
    ['c_rank'],
  );
  assert.deepEqual(
    candidates.map((candidate) => candidate.preference),
    ['稳一点'],
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
    extractors: [{ value: 'hybrid', label: '规则优先，大模型补槽' }],
    planner_modes: [{ value: 'auto', label: '上传数据集优先语义意图规划' }],
    generators: [{ value: 'template_evidence', label: '模板证据回答' }],
    models: [{ value: 'deepseek-v4-flash', label: 'LLM 快速模型' }],
    rank_windows: [{ value: 'steady', label: '稳一点', rank_window_upper_percent: 15 }],
    sort_modes: [{ value: 'rank_desc', label: '按历史位次从低到高看（更稳）' }],
  });

  assert.equal(options.source, 'api');
  assert.equal(options.extractors[0].value, 'hybrid');
  assert.equal(options.planner_modes[0].value, 'auto');
  assert.equal(options.rank_windows[0].description, '');
});

test('normalizeWorkbenchOptions uses complete fallback when API payload is empty', () => {
  const options = normalizeWorkbenchOptions(null);

  assert.equal(options.source, 'fallback');
  assert.deepEqual(options.extractors, FALLBACK_WORKBENCH_OPTIONS.extractors);
  assert.deepEqual(options.planner_modes, FALLBACK_WORKBENCH_OPTIONS.planner_modes);
  assert.equal(options.rank_windows.length, 3);
});

test('normalizeWorkbenchOptions marks missing API option groups as partial fallback', () => {
  const options = normalizeWorkbenchOptions({
    extractors: [{ value: 'hybrid', label: '规则优先，大模型补槽' }],
    planner_modes: [],
    generators: [],
    models: [{ value: 'deepseek-v4-flash', label: 'LLM 快速模型' }],
    rank_windows: [{ value: 'steady', label: '稳一点', rank_window_upper_percent: 15 }],
    sort_modes: [{ value: 'rank_desc', label: '按历史位次从低到高看（更稳）' }],
  });

  assert.equal(options.source, 'partial_fallback');
  assert.deepEqual(options.planner_modes, FALLBACK_WORKBENCH_OPTIONS.planner_modes);
  assert.deepEqual(options.generators, FALLBACK_WORKBENCH_OPTIONS.generators);
});

test('normalizeWorkbenchOptions isolates fallback options from mutation', () => {
  const options = normalizeWorkbenchOptions(null);

  options.extractors[0].label = '被修改的标签';

  assert.equal(FALLBACK_WORKBENCH_OPTIONS.extractors[0].label, '规则优先，大模型补槽');
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
    plannerMode: 'legacy',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  });

  assert.equal(request.dataset_id, 'dataset_1');
  assert.equal(request.domain_name, 'admissions');
  assert.equal(request.extractor, 'hybrid');
  assert.equal(request.planner_mode, 'legacy');
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

test('buildWorkbenchPreflightRequest only targets uploaded admissions sources', () => {
  const runRequest = {
    user_input: '我的排位是15000，想读人工智能。',
    hard_filters: { user_rank: 15000 },
    soft_preferences: { prompt: '我的排位是15000，想读人工智能。' },
  };

  const uploaded = buildWorkbenchPreflightRequest({
    source: {
      type: 'uploaded',
      datasetId: 'dataset_1',
      domainName: 'admissions',
    },
    runRequest,
    model: 'deepseek-v4-flash',
  });
  const builtin = buildWorkbenchPreflightRequest({
    source: {
      type: 'builtin',
      domainName: 'admissions',
    },
    runRequest,
    model: 'deepseek-v4-flash',
  });

  assert.equal(uploaded.dataset_id, 'dataset_1');
  assert.equal(uploaded.domain_name, 'admissions');
  assert.equal(uploaded.planner_mode, 'llm_semantic');
  assert.equal(builtin, null);
});

test('preflight boundary selections split confirmed and disabled choices', () => {
  const preflight = {
    boundary_confirmations: [
      {
        confirmation_id: 'pfc_1',
        default_option_id: 'rank_window_steady',
        options: [
          { option_id: 'rank_window_steady', disabled_boundary: false },
          { option_id: 'do_not_use', disabled_boundary: true },
        ],
      },
      {
        confirmation_id: 'pfc_2',
        default_option_id: 'do_not_use',
        options: [{ option_id: 'do_not_use', disabled_boundary: true }],
      },
    ],
  };

  const defaults = boundarySelectionsFromPreflight(preflight);
  const split = splitPreflightBoundarySelections(preflight, defaults);

  assert.deepEqual(defaults, {
    pfc_1: 'rank_window_steady',
    pfc_2: 'do_not_use',
  });
  assert.deepEqual(split.confirmed_boundaries, [
    { confirmation_id: 'pfc_1', option_id: 'rank_window_steady' },
  ]);
  assert.deepEqual(split.disabled_boundaries, [
    { confirmation_id: 'pfc_2', option_id: 'do_not_use' },
  ]);
});

test('buildPreflightConfirmedWorkbenchRequest attaches preflight selections', () => {
  const previous = {
    domain_name: 'admissions',
    user_input: '我的排位是15000。',
    hard_filters: { user_rank: 15000 },
    soft_preferences: { prompt: '我的排位是15000。' },
  };

  const request = buildPreflightConfirmedWorkbenchRequest(previous, {
    preflightId: 'pf_1',
    confirmedBoundaries: [{ confirmation_id: 'pfc_1', option_id: 'rank_window_steady' }],
    disabledBoundaries: [{ confirmation_id: 'pfc_2', option_id: 'do_not_use' }],
  });

  assert.equal(request.preflight_id, 'pf_1');
  assert.deepEqual(request.confirmed_boundaries, [
    { confirmation_id: 'pfc_1', option_id: 'rank_window_steady' },
  ]);
  assert.deepEqual(request.disabled_boundaries, [
    { confirmation_id: 'pfc_2', option_id: 'do_not_use' },
  ]);
  assert.notEqual(request, previous);
});
