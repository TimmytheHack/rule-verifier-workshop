<script setup>
import { reactive, watch } from 'vue';
import { MagicStick, Search } from '@element-plus/icons-vue';

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
});

const emit = defineEmits(['run']);

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
const rankWindowOptions = [
  {
    label: '先不选',
    value: '',
    lower: null,
    upper: null,
    description: '不按排位窗口筛。',
  },
  {
    label: '冲一冲',
    value: 'reach',
    lower: 20,
    upper: 0,
    description: '按后 0% 上界执行；前 20% 只作档位提示。',
  },
  {
    label: '稳一点',
    value: 'steady',
    lower: 5,
    upper: 15,
    description: '按后 15% 上界执行；前 5% 只作档位提示。',
  },
  {
    label: '保底',
    value: 'safe',
    lower: 0,
    upper: 50,
    description: '按后 50% 上界执行，不设前向下界。',
  },
  {
    label: '自定义',
    value: 'custom',
    lower: 10,
    upper: 10,
    description: '自己设置后向上界；前向比例只作提示。',
  },
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

function submitRun() {
  const rankWindow = selectedRankWindow();
  const hardPayload = {
    source_province: hard.source_province || null,
    subject_type: hard.subject_type || null,
    reselected_subjects: [...(hard.reselected_subjects || [])],
    user_rank: hard.user_rank || null,
    major_keyword: hard.major_keyword || null,
    preferred_cities: [...(hard.preferred_cities || [])],
    tuition_cap_yuan: hard.tuition_cap_yuan || null,
  };
  const legacySafetyMargin = rankWindow ? null : legacySafetyMarginPercent();
  const softPayload = {
    prompt: (soft.prompt || '').trim(),
    safety_margin_percent: legacySafetyMargin,
    rank_window_label: rankWindow?.label || null,
    rank_window_lower_percent: rankWindow?.lower ?? null,
    rank_window_upper_percent: rankWindow?.upper ?? null,
    tuition_cap_yuan: soft.tuition_cap_yuan || null,
  };
  emit('run', {
    user_input: composeRequest(hardPayload, softPayload),
    hard_filters: hardPayload,
    soft_preferences: softPayload,
  });
}

function applyExample(example) {
  Object.assign(hard, example.hard || {});
  Object.assign(soft, example.soft || {});
  if (example.soft?.rank_window_preset) {
    applyRankWindowPreset(example.soft.rank_window_preset);
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
  if (
    soft.rank_window_label
    && soft.rank_window_lower_percent !== null
    && soft.rank_window_upper_percent !== null
    && !soft.rank_window_preset
  ) {
    soft.rank_window_preset = 'custom';
  }
}

function applyRankWindowPreset(value) {
  const option = rankWindowOptions.find((item) => item.value === value);
  if (!option || option.value === '') {
    soft.rank_window_preset = '';
    soft.rank_window_label = '';
    return;
  }
  soft.rank_window_preset = option.value;
  soft.rank_window_label = option.label;
  if (option.value !== 'custom') {
    soft.rank_window_lower_percent = option.lower;
    soft.rank_window_upper_percent = option.upper;
  } else {
    soft.rank_window_lower_percent = soft.rank_window_lower_percent ?? option.lower;
    soft.rank_window_upper_percent = soft.rank_window_upper_percent ?? option.upper;
  }
}

function selectedRankWindow() {
  if (!soft.rank_window_preset) return null;
  const option = rankWindowOptions.find((item) => item.value === soft.rank_window_preset);
  if (!option || option.value === '') return null;
  const lower = clampPercent(soft.rank_window_lower_percent);
  const upper = clampPercent(soft.rank_window_upper_percent);
  return {
    label: option.value === 'custom' ? '自定义' : option.label,
    lower,
    upper,
  };
}

function clampPercent(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return 0;
  return Math.min(100, Math.max(0, Math.round(number)));
}

function legacySafetyMarginPercent() {
  if (
    soft.safety_margin_percent === null
    || soft.safety_margin_percent === undefined
    || soft.safety_margin_percent === ''
  ) {
    return null;
  }
  return clampPercent(soft.safety_margin_percent);
}

function selectedRankWindowDescription() {
  const window = selectedRankWindow();
  if (!window) return '不按排位窗口筛。';
  const lowerContext = window.lower > 0 ? `前 ${window.lower}% 只作档位提示，` : '';
  return `${lowerContext}只按后 ${window.upper}% 以内设置上界，不设前向下界。`;
}

function rankWindowText(payload) {
  return `${payload.rank_window_label}（后 ${payload.rank_window_upper_percent}% 以内）`;
}
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
        <el-tag type="warning" effect="plain">可选</el-tag>
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
            placeholder="先不选"
            @change="applyRankWindowPreset"
          >
            <el-option
              v-for="option in rankWindowOptions"
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

        <div
          v-if="soft.rank_window_preset === 'custom'"
          class="custom-window-row"
        >
          <label class="control-block">
            <span class="control-label">档位提示：前多少%</span>
            <el-input-number
              v-model="soft.rank_window_lower_percent"
              class="full-control"
              :min="0"
              :max="100"
              :step="1"
              controls-position="right"
            />
          </label>
          <label class="control-block">
            <span class="control-label">执行上界：后多少%</span>
            <el-input-number
              v-model="soft.rank_window_upper_percent"
              class="full-control"
              :min="0"
              :max="100"
              :step="1"
              controls-position="right"
            />
          </label>
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

    <div class="panel-actions">
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
