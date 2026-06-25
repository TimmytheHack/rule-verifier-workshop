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
  if (end === -1) {
    const selfCloseEnd = source.indexOf('/>', start);
    assert.notEqual(selfCloseEnd, -1, `missing ${closeTag}`);
    return source.slice(start, selfCloseEnd + 2);
  }
  return source.slice(start, end + closeTag.length);
}

function cssRule(source, selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`));
  assert.ok(match, `missing CSS rule ${selector}`);
  return match[1];
}

test('App renders QueryWorkspace as the query shell without nested query markup', () => {
  const appSource = readSource('../App.vue');
  const block = componentBlock(appSource, 'QueryWorkspace');

  assert.doesNotMatch(block, /v-slot\s*=\s*"/);
  assertIncludesAll(block, [
    'v-model:mode="mode"',
    'v-model:extractor="extractor"',
    'v-model:generator="generator"',
    'v-model:model="model"',
    ':run-data="runData"',
    ':preflight-state="preflightState"',
    ':workbench-options="workbenchOptions"',
    ':options-load-error="shouldShowOptionsLoadError(mode, optionsLoadError) ? optionsLoadError : \'\'"',
    '@update:selected-data-source-id="handleDataSourceChange"',
    '@show-demo="showDemoRun"',
    '@go-import="goToUpload"',
    '@draft-change="handleInputDraftChange"',
    '@run-workbench="runWorkbench"',
    '@update-preflight-selection="updatePreflightSelection"',
    '@confirm-candidates="rerunWithConfirmedCandidates"',
    '@view-trace="openTrace"',
  ]);
  assert.doesNotMatch(block, /<WorkbenchRunBar/);
  assert.doesNotMatch(block, /<UserInputPanel/);
  assert.doesNotMatch(block, /<PreflightPanel/);
  assert.doesNotMatch(block, /<ResultTable/);
});

test('QueryWorkspace owns query layout and forwards key events', () => {
  const source = readSource('./workspaces/QueryWorkspace.vue');

  assert.ok(source.includes('const props = defineProps({'));
  assertIncludesAll(source, [
    'import { ref } from \'vue\';',
    'import WorkbenchRunBar from \'../WorkbenchRunBar.vue\';',
    'import UserInputPanel from \'../UserInputPanel.vue\';',
    'import PreflightPanel from \'../PreflightPanel.vue\';',
    'import ResultTable from \'../ResultTable.vue\';',
    'const inputPanelRef = ref(null);',
    'function submitCurrentForm()',
    '<section class="workspace-panel c-lite-query">',
    '<WorkbenchRunBar',
    '<UserInputPanel',
    '<PreflightPanel',
    '<ResultTable',
    '@run="submitCurrentForm"',
    '@demo="emit(\'show-demo\')"',
    '@upload="emit(\'go-import\')"',
    '@draft-change="emit(\'draft-change\', $event)"',
    '@run="emit(\'run-workbench\', $event)"',
    '@update-selection="emit(\'update-preflight-selection\', $event)"',
    '@confirm="emit(\'confirm-candidates\', $event)"',
    '@view-trace="emit(\'view-trace\', $event)"',
  ]);
  assert.doesNotMatch(source, /<slot/);
});

test('QueryWorkspace keeps beginner decision summary visible outside evidence collapse', () => {
  const source = readSource('./workspaces/QueryWorkspace.vue');
  const collapse = componentBlock(source, 'el-collapse');
  const summaryIndex = source.indexOf('<BeginnerDecisionPanel');
  const collapseIndex = source.indexOf('<el-collapse');

  assert.notEqual(summaryIndex, -1, 'missing BeginnerDecisionPanel');
  assert.notEqual(collapseIndex, -1, 'missing evidence collapse');
  assert.ok(summaryIndex < collapseIndex, 'BeginnerDecisionPanel should render before the collapse');
  assert.doesNotMatch(collapse, /<BeginnerDecisionPanel/);
});

test('C-lite query layout bounds desktop overflow and restores mobile page flow', () => {
  const source = readSource('../style.css');
  const cLiteQuery = cssRule(source, '.c-lite-query');
  const queryGrid = cssRule(source, '.c-lite-query-grid');
  const inputPanel = cssRule(source, '.query-input-panel,\n.query-output-panel');
  const mobileBlock = source.match(/@media \(max-width: 1120px\) \{[\s\S]*?\.wide-field,/);

  assert.match(cLiteQuery, /height:\s*100%;/);
  assert.match(cLiteQuery, /min-height:\s*0;/);
  assert.match(queryGrid, /min-height:\s*0;/);
  assert.match(queryGrid, /overflow:\s*hidden;/);
  assert.match(inputPanel, /min-height:\s*0;/);
  assert.match(inputPanel, /overflow:\s*auto;/);
  assert.match(inputPanel, /scrollbar-width:\s*thin;/);
  assert.ok(mobileBlock, 'missing mobile workspace override block');
  assert.match(mobileBlock[0], /\.c-lite-query-grid[\s\S]*?overflow:\s*visible;/);
  assert.match(mobileBlock[0], /\.query-input-panel,\s*\.query-output-panel[\s\S]*?overflow:\s*visible;/);
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
