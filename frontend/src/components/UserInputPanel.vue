<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { MagicStick, Search } from '@element-plus/icons-vue';

import { mergePromptText } from '../utils/workbenchUiState';

const props = defineProps({
  defaultHardFilters: {
    type: Object,
    required: true,
  },
  defaultSoftPreferences: {
    type: Object,
    required: true,
  },
  mode: {
    type: String,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  showPanelActions: {
    type: Boolean,
    default: true,
  },
  rankWindowOptions: {
    type: Array,
    default: () => [],
  },
  sortModeOptions: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['draft-change', 'run']);

const provinceOptions = ['广东'];
const subjectOptions = ['物理', '历史'];
const reselectedSubjectOptions = ['化学', '生物', '政治', '地理'];
const cityOptions = ['广州', '深圳', '佛山', '东莞', '珠海', '汕头', '惠州'];
const tuitionOptions = [
  { label: '先不选', value: '' },
  { label: '10000 元/年', value: 10000 },
  { label: '20000 元/年', value: 20000 },
  { label: '40000 元/年', value: 40000 },
];
const quickExamples = [
  {
    label: '我想学计算机',
    hard: { major_keyword: '计算机', preferred_cities: ['广州', '深圳'] },
    soft: { prompt: '想学计算机，最好在广州深圳，学校稳一点。' },
  },
  {
    label: '预算 2 万以内',
    hard: { tuition_cap_yuan: 20000 },
    soft: { tuition_cap_yuan: 20000, prompt: '想找学费两万以内的专业。' },
  },
  {
    label: '先看稳一点',
    hard: {},
    soft: { rank_window_preset: 'steady', prompt: '学校稳一点，专业不要太冷门。' },
  },
];

const hard = reactive(emptyHardFilters());
const soft = reactive(emptySoftPreferences());
const formError = ref('');
const draftSignature = computed(() => JSON.stringify(formDraftPayload()));

function emptyHardFilters() {
  return {
    source_province: '广东',
    subject_type: '物理',
    reselected_subjects: ['化学', '生物'],
    user_rank: 32000,
    major_keyword: null,
    preferred_cities: [],
    tuition_cap_yuan: null,
  };
}

function emptySoftPreferences() {
  return {
    prompt: '想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。',
    safety_margin_percent: '',
    rank_window_preset: '',
    rank_window_lower_percent: null,
    rank_window_upper_percent: null,
    rank_window_label: '',
    sort_mode: '',
    tuition_cap_yuan: '',
  };
}

function assignFormState() {
  Object.assign(hard, emptyHardFilters(), props.defaultHardFilters || {});
  hard.preferred_cities = [...(props.defaultHardFilters?.preferred_cities || hard.preferred_cities || [])];
  hard.reselected_subjects = [...(props.defaultHardFilters?.reselected_subjects || hard.reselected_subjects || [])];
  Object.assign(soft, emptySoftPreferences(), props.defaultSoftPreferences || {});
  normalizeRankWindowState();
}

watch(
  () => [props.defaultHardFilters, props.defaultSoftPreferences],
  assignFormState,
  { deep: true, immediate: true },
);

watch(
  () => [soft.rank_window_preset, soft.sort_mode],
  () => {
    if (formError.value) {
      formError.value = '';
    }
  },
);

watch(draftSignature, (signature) => {
  emit('draft-change', signature);
}, { immediate: true });

function submitRun() {
  const rankWindow = selectedRankWindow();
  const sortMode = selectedSortMode();
  if (!rankWindow) {
    formError.value = '请先选择排位范围：冲一冲、稳一点或保底。';
    return;
  }
  if (!sortMode) {
    formError.value = '请先选择排序方式。';
    return;
  }
  formError.value = '';
  const hardPayload = {
    source_province: hard.source_province || null,
    subject_type: hard.subject_type || null,
    reselected_subjects: [...(hard.reselected_subjects || [])],
    user_rank: hard.user_rank || null,
    major_keyword: hard.major_keyword || null,
    preferred_cities: [...(hard.preferred_cities || [])],
    tuition_cap_yuan: hard.tuition_cap_yuan || null,
  };
  const softPayload = {
    prompt: (soft.prompt || '').trim(),
    safety_margin_percent: null,
    rank_window_label: rankWindow?.label || null,
    rank_window_lower_percent: rankWindow?.lower ?? null,
    rank_window_upper_percent: rankWindow?.upper ?? null,
    sort_mode: sortMode.value,
    tuition_cap_yuan: soft.tuition_cap_yuan || null,
  };
  emit('run', {
    user_input: composeRequest(hardPayload, softPayload),
    hard_filters: hardPayload,
    soft_preferences: softPayload,
    form_signature: draftSignature.value,
  });
}

function formDraftPayload() {
  const rankWindow = selectedRankWindow();
  return {
    hard: {
      source_province: hard.source_province || null,
      subject_type: hard.subject_type || null,
      reselected_subjects: [...(hard.reselected_subjects || [])],
      user_rank: hard.user_rank || null,
      major_keyword: hard.major_keyword || null,
      preferred_cities: [...(hard.preferred_cities || [])],
      tuition_cap_yuan: hard.tuition_cap_yuan || null,
    },
    soft: {
      prompt: (soft.prompt || '').trim(),
      rank_window_preset: soft.rank_window_preset || '',
      rank_window_label: rankWindow?.label || '',
      rank_window_lower_percent: rankWindow?.lower ?? null,
      rank_window_upper_percent: rankWindow?.upper ?? null,
      sort_mode: soft.sort_mode || '',
      tuition_cap_yuan: soft.tuition_cap_yuan || null,
    },
  };
}

function applyExample(example) {
  Object.assign(hard, example.hard || {});
  const { prompt, rank_window_preset: rankWindowPreset, ...softPatch } = example.soft || {};
  Object.assign(soft, softPatch);
  if (prompt) {
    soft.prompt = mergePromptText(soft.prompt, prompt);
  }
  if (rankWindowPreset) {
    applyRankWindowPreset(rankWindowPreset);
  }
}

function composeRequest(hardPayload, softPayload) {
  const hardParts = [
    hardPayload.source_province,
    hardPayload.subject_type ? `${hardPayload.subject_type}类` : '',
    hardPayload.reselected_subjects.length ? `再选科目：${hardPayload.reselected_subjects.join('、')}` : '',
    hardPayload.user_rank ? `排位${hardPayload.user_rank}` : '',
    hardPayload.major_keyword ? `想学${hardPayload.major_keyword}` : '',
    hardPayload.preferred_cities.length ? `城市优先：${hardPayload.preferred_cities.join('、')}` : '',
  ].filter(Boolean);
  const boundaryParts = [
    softPayload.rank_window_label ? rankWindowText(softPayload) : '',
    softPayload.tuition_cap_yuan ? `费用上限 ${softPayload.tuition_cap_yuan} 元/年` : '',
  ].filter(Boolean);
  const promptText = trimSentence(softPayload.prompt);
  const suffixParts = [];
  if (boundaryParts.length) suffixParts.push(`已确认边界：${boundaryParts.join('，')}`);
  if (promptText) suffixParts.push(`偏好描述：${promptText}`);
  if (!suffixParts.length) {
    return `${hardParts.join('，')}。`;
  }
  return `${hardParts.join('，')}；${suffixParts.join('；')}。`;
}

function trimSentence(value) {
  return String(value || '').replace(/[。；;，,\s]+$/u, '');
}

function normalizeRankWindowState() {
  if (soft.rank_window_preset && !selectedRankWindow()) {
    soft.rank_window_preset = '';
    soft.rank_window_label = '';
  }
}

function normalizedRankWindowOptions() {
  return (props.rankWindowOptions || []).map((item) => ({
    label: item.label,
    value: item.value,
    lower: Number(item.rank_window_lower_percent || 0),
    upper: Number(item.rank_window_upper_percent || 0),
    description: item.description || '',
  }));
}

function applyRankWindowPreset(value) {
  const option = normalizedRankWindowOptions().find((item) => item.value === value);
  if (!option) {
    soft.rank_window_preset = '';
    soft.rank_window_label = '';
    return;
  }
  soft.rank_window_preset = option.value;
  soft.rank_window_label = option.label;
  soft.rank_window_lower_percent = option.lower;
  soft.rank_window_upper_percent = option.upper;
}

function selectedRankWindow() {
  if (!soft.rank_window_preset) return null;
  const option = normalizedRankWindowOptions().find((item) => item.value === soft.rank_window_preset);
  if (!option) return null;
  return {
    label: option.label,
    lower: option.lower,
    upper: option.upper,
  };
}

function selectedSortMode() {
  if (!soft.sort_mode) return null;
  return (props.sortModeOptions || []).find((item) => item.value === soft.sort_mode) || null;
}

function selectedRankWindowDescription() {
  const window = selectedRankWindow();
  if (!window) return '请选择后端白名单中的排位范围；只执行后向上界。';
  const option = normalizedRankWindowOptions().find((item) => item.value === soft.rank_window_preset);
  return option?.description || `只按后 ${window.upper}% 以内设置上界，不设前向下界。`;
}

function rankWindowText(payload) {
  return `${payload.rank_window_label}（后 ${payload.rank_window_upper_percent}% 以内）`;
}

defineExpose({ submitRun });
</script>

<template>
  <el-card class="workbench-card input-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>先填这几项</h2>
        </div>
        <el-tag :type="mode === 'api' ? 'warning' : 'info'" effect="plain">
          {{ mode === 'api' ? '实时查询' : '演示' }}
        </el-tag>
      </div>
    </template>

    <section class="input-section">
      <div class="input-section-title">
        <h3>基本情况</h3>
        <el-tag type="success" effect="plain">必填</el-tag>
      </div>
      <div class="hard-form-grid">
        <label class="control-block">
          <span class="control-label">生源地</span>
          <el-select v-model="hard.source_province" class="full-control">
            <el-option
              v-for="option in provinceOptions"
              :key="option"
              :label="option"
              :value="option"
            />
          </el-select>
        </label>

        <label class="control-block">
          <span class="control-label">科类</span>
          <el-segmented
            v-model="hard.subject_type"
            :options="subjectOptions"
            class="full-control"
          />
        </label>

        <label class="control-block">
          <span class="control-label">全省排位</span>
          <el-input-number
            v-model="hard.user_rank"
            class="full-control"
            :min="1"
            :step="100"
            controls-position="right"
          />
        </label>

        <label class="control-block wide-field">
          <span class="control-label">选考科目</span>
          <el-checkbox-group
            v-model="hard.reselected_subjects"
            :max="2"
            class="subject-checkboxes"
          >
            <el-checkbox-button
              v-for="option in reselectedSubjectOptions"
              :key="option"
              :label="option"
              :value="option"
            />
          </el-checkbox-group>
        </label>

        <p class="form-note">
          不用填分数，排位更适合做筛选。
        </p>
      </div>
    </section>

    <section class="input-section soft-section">
      <div class="input-section-title">
        <h3>想看的方向</h3>
        <el-tag type="warning" effect="plain">含必填</el-tag>
      </div>
      <div class="quick-example-row" aria-label="常用示例">
        <el-button
          v-for="example in quickExamples"
          :key="example.label"
          :icon="MagicStick"
          plain
          @click="applyExample(example)"
        >
          {{ example.label }}
        </el-button>
      </div>
      <el-alert
        v-if="formError"
        class="inline-alert"
        type="warning"
        :closable="false"
        :title="formError"
      />
      <div class="soft-form-grid">
        <label class="control-block">
          <span class="control-label">想学专业</span>
          <el-input
            v-model="hard.major_keyword"
            class="full-control"
            clearable
            placeholder="如：计算机"
          />
        </label>

        <label class="control-block">
          <span class="control-label">城市偏好</span>
          <el-select
            v-model="hard.preferred_cities"
            class="full-control"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="可多选"
          >
            <el-option
              v-for="option in cityOptions"
              :key="option"
              :label="option"
              :value="option"
            />
          </el-select>
        </label>

        <label class="control-block">
          <span class="control-label">排位范围</span>
          <el-select
            v-model="soft.rank_window_preset"
            class="full-control"
            popper-class="rank-window-select-popper"
            placeholder="请选择排位范围"
            @change="applyRankWindowPreset"
          >
            <el-option
              v-for="option in normalizedRankWindowOptions()"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            >
              <div class="rank-window-option">
                <strong>{{ option.label }}</strong>
                <span>{{ option.description }}</span>
              </div>
            </el-option>
          </el-select>
          <span class="inline-help">{{ selectedRankWindowDescription() }}</span>
        </label>

        <div class="control-block">
          <span class="control-label">排序方式</span>
          <el-select
            v-model="soft.sort_mode"
            class="full-control"
            placeholder="请选择排序方式"
          >
            <el-option
              v-for="option in sortModeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </div>

        <label class="control-block">
          <span class="control-label">学费上限</span>
          <el-select
            v-model="soft.tuition_cap_yuan"
            class="full-control"
            placeholder="先不选"
          >
            <el-option
              v-for="option in tuitionOptions"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>

        <label class="control-block prompt-field">
          <span class="control-label">补充偏好</span>
          <el-input
            v-model="soft.prompt"
            class="input-textarea"
            type="textarea"
            :rows="2"
            maxlength="240"
            show-word-limit
            resize="none"
            placeholder="例如：学校稳一点，不想去太贵的中外合作。"
          />
        </label>
      </div>
    </section>

    <div v-if="showPanelActions" class="panel-actions">
      <el-button
        type="primary"
        size="large"
        :icon="Search"
        :loading="loading"
        @click="submitRun"
      >
        查看可筛结果
      </el-button>
      <span class="muted-note">
        {{ mode === 'api' ? '实时查询' : '演示结果' }}
      </span>
    </div>
  </el-card>
</template>
