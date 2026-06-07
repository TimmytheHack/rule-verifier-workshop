<script setup>
import { reactive, watch } from 'vue';
import { Search } from '@element-plus/icons-vue';

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
const safetyOptions = [
  { label: '不使用', value: '' },
  { label: '5%', value: 5 },
  { label: '10%', value: 10 },
  { label: '15%', value: 15 },
];
const tuitionOptions = [
  { label: '不使用', value: '' },
  { label: '10000 元/年', value: 10000 },
  { label: '20000 元/年', value: 20000 },
  { label: '40000 元/年', value: 40000 },
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
    safety_margin_percent: 10,
    tuition_cap_yuan: 20000,
  };
}

function assignFormState() {
  Object.assign(hard, emptyHardFilters(), props.defaultHardFilters || {});
  hard.preferred_cities = [...(props.defaultHardFilters?.preferred_cities || hard.preferred_cities || [])];
  hard.reselected_subjects = [...(props.defaultHardFilters?.reselected_subjects || hard.reselected_subjects || [])];
  Object.assign(soft, emptySoftPreferences(), props.defaultSoftPreferences || {});
}

watch(
  () => [props.defaultHardFilters, props.defaultSoftPreferences],
  assignFormState,
  { deep: true, immediate: true },
);

function submitRun() {
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
    safety_margin_percent: soft.safety_margin_percent || null,
    tuition_cap_yuan: soft.tuition_cap_yuan || null,
  };
  emit('run', {
    user_input: composeRequest(hardPayload, softPayload),
    hard_filters: hardPayload,
    soft_preferences: softPayload,
  });
}

function composeRequest(hardPayload, softPayload) {
  const hardParts = [
    hardPayload.source_province,
    hardPayload.subject_type ? `${hardPayload.subject_type}类` : '',
    hardPayload.reselected_subjects.length ? `再选科目：${hardPayload.reselected_subjects.join('、')}` : '',
    hardPayload.user_rank ? `排位${hardPayload.user_rank}` : '',
  ].filter(Boolean);
  const boundaryParts = [
    softPayload.safety_margin_percent ? `位次窗口 ${softPayload.safety_margin_percent}%` : '',
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
</script>

<template>
  <el-card class="workbench-card input-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <p class="section-kicker">用户输入</p>
          <h2>基础信息与偏好描述</h2>
        </div>
        <el-tag :type="mode === 'api' ? 'warning' : 'info'" effect="plain">
          {{ mode === 'api' ? '调用后端 API' : '加载内置演示数据' }}
        </el-tag>
      </div>
    </template>

    <section class="input-section">
      <div class="input-section-title">
        <h3>考生基础信息</h3>
        <el-tag type="success" effect="plain">结构化事实，进入规则验证</el-tag>
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
          <span class="control-label">省排位</span>
          <el-input-number
            v-model="hard.user_rank"
            class="full-control"
            :min="1"
            :step="100"
            controls-position="right"
          />
        </label>

        <label class="control-block wide-field">
          <span class="control-label">再选科目（四选二）</span>
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
          专业、城市、中外合作、学校性质等偏好请写入下方文本，由规则解析或 LLM 辅助解析；选科要求由上方基础信息参与规则验证。
        </p>
      </div>
    </section>

    <section class="input-section soft-section">
      <div class="input-section-title">
        <h3>偏好描述与边界确认</h3>
        <el-tag type="warning" effect="plain">偏好来自文本，边界用于确认候选规则</el-tag>
      </div>
      <div class="soft-form-grid">
        <label class="control-block">
          <span class="control-label">位次窗口（可选）</span>
          <el-select v-model="soft.safety_margin_percent" class="full-control">
            <el-option
              v-for="option in safetyOptions"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>

        <label class="control-block">
          <span class="control-label">费用上限（可选）</span>
          <el-select v-model="soft.tuition_cap_yuan" class="full-control">
            <el-option
              v-for="option in tuitionOptions"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>

        <label class="control-block prompt-field">
          <span class="control-label">偏好描述</span>
          <el-input
            v-model="soft.prompt"
            class="input-textarea"
            type="textarea"
            :rows="4"
            maxlength="240"
            show-word-limit
            resize="none"
            placeholder="例如：想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。"
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
        运行规则验证
      </el-button>
      <span class="muted-note">
        {{ mode === 'api' ? '将请求后端运行受控选项。' : '演示模式只加载内置数据。' }}
      </span>
    </div>
  </el-card>
</template>
