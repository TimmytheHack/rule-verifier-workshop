import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8');
}

function assertIncludesAll(source, snippets) {
  for (const snippet of snippets) {
    assert.ok(source.includes(snippet), `missing ${snippet}`);
  }
}

function componentBlock(source, componentName) {
  const openTag = `<${componentName}`;
  const start = source.indexOf(openTag);
  assert.notEqual(start, -1, `missing ${openTag}`);
  const closeTag = `</${componentName}>`;
  const end = source.indexOf(closeTag, start);
  assert.notEqual(end, -1, `missing ${closeTag}`);
  return source.slice(start, end + closeTag.length);
}

test('QueryWorkspace exposes the planned state and actions through its slot', () => {
  const source = readSource('./workspaces/QueryWorkspace.vue');

  assert.ok(source.includes('const props = defineProps({'));
  assertIncludesAll(source, [
    ':run-data="props.runData"',
    ':preflight-state="props.preflightState"',
    ':workbench-options="props.workbenchOptions"',
    ':mode="props.mode"',
    ':extractor="props.extractor"',
    ':generator="props.generator"',
    ':model="props.model"',
    ':loading="props.loading"',
    ':last-run-failed="props.lastRunFailed"',
    ':api-error="props.apiError"',
    ':selected-data-source-id="props.selectedDataSourceId"',
    ':data-source-options="props.dataSourceOptions"',
    ':data-source-tag="props.dataSourceTag"',
    ':data-source-description="props.dataSourceDescription"',
    ':options-load-error="props.optionsLoadError"',
    ':run-status="props.runStatus"',
    ':primary-run-label="props.primaryRunLabel"',
    ':quick-stats="props.quickStats"',
    ':result-rows="props.resultRows"',
    ':can-confirm-candidates="props.canConfirmCandidates"',
    ':default-hard-filters="props.defaultHardFilters"',
    ':default-soft-preferences="props.defaultSoftPreferences"',
    ':emit-update-mode="emitUpdateMode"',
    ':emit-update-extractor="emitUpdateExtractor"',
    ':emit-update-generator="emitUpdateGenerator"',
    ':emit-update-model="emitUpdateModel"',
    ':emit-update-selected-data-source-id="emitUpdateSelectedDataSourceId"',
    ':run-current-form="runCurrentForm"',
    ':show-demo="showDemo"',
    ':go-import="goImport"',
    ':draft-change="draftChange"',
    ':run-workbench="runWorkbench"',
    ':update-preflight-selection="updatePreflightSelection"',
    ':confirm-candidates="confirmCandidates"',
    ':view-trace="viewTrace"',
  ]);
});

test('App routes query children through the QueryWorkspace scoped slot', () => {
  const appSource = readSource('../App.vue');
  const block = componentBlock(appSource, 'QueryWorkspace');
  const slotChildren = block.slice(block.indexOf('>') + 1);

  assert.match(block, /v-slot\s*=\s*"/);
  assertIncludesAll(block, [
    'workspaceMode',
    'workspaceExtractor',
    'workspaceGenerator',
    'workspaceModel',
    'workspaceRunData',
    'workspacePreflightState',
    'workspaceOptions',
    'workspaceLoading',
    'workspaceLastRunFailed',
    'workspaceApiError',
    'workspaceSelectedDataSourceId',
    'workspaceDataSourceOptions',
    'workspaceDataSourceTag',
    'workspaceDataSourceDescription',
    'workspaceOptionsLoadError',
    'workspaceRunStatus',
    'workspacePrimaryRunLabel',
    'workspaceQuickStats',
    'workspaceResultRows',
    'workspaceCanConfirmCandidates',
    'workspaceDefaultHardFilters',
    'workspaceDefaultSoftPreferences',
    'emitUpdateMode',
    'emitUpdateExtractor',
    'emitUpdateGenerator',
    'emitUpdateModel',
    'emitUpdateSelectedDataSourceId',
    'emitRunCurrentForm',
    'emitShowDemo',
    'emitGoImport',
    'emitDraftChange',
    'emitRunWorkbench',
    'emitUpdatePreflightSelection',
    'emitConfirmCandidates',
    'emitViewTrace',
  ]);
  assert.match(block, /:mode="workspaceMode"/);
  assert.match(block, /@update:mode="emitUpdateMode"/);
  assert.match(block, /@update:selected-data-source-id="emitUpdateSelectedDataSourceId"/);
  assert.match(block, /@run="emitRunCurrentForm"/);
  assert.match(block, /@draft-change="emitDraftChange"/);
  assert.match(block, /@run="emitRunWorkbench"/);
  assert.match(block, /@update-selection="emitUpdatePreflightSelection"/);
  assert.match(block, /@confirm="emitConfirmCandidates"/);
  assert.match(block, /@view-trace="emitViewTrace"/);
  assert.doesNotMatch(slotChildren, /v-model:mode="mode"/);
  assert.doesNotMatch(slotChildren, /@run="submitCurrentForm"/);
  assert.doesNotMatch(slotChildren, /@draft-change="handleInputDraftChange"/);
  assert.doesNotMatch(slotChildren, /@confirm="rerunWithConfirmedCandidates"/);
  assert.doesNotMatch(slotChildren, /@view-trace="openTrace"/);
});

test('ImportWorkspace routes upload actions through its slot contract', () => {
  const source = readSource('./workspaces/ImportWorkspace.vue');
  const appSource = readSource('../App.vue');

  assert.ok(source.includes('const props = defineProps({'));
  assertIncludesAll(source, [
    ':active-source="props.activeSource"',
    ':emit-source-ready="emitSourceReady"',
    ':open-review="openReview"',
  ]);
  assert.ok(appSource.includes('v-slot="{ emitSourceReady }"'));
  assert.ok(appSource.includes('<DatasetIngestionPanel @source-ready="emitSourceReady" />'));
});
