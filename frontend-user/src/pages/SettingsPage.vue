<script setup>
import { computed, reactive, ref, watchEffect } from 'vue';
import { saveLlmSettings } from '../api/settings.js';

const DEFAULT_PROVIDER_OPTIONS = [
  {
    provider: 'deepseek',
    label: 'DeepSeek',
    model: 'deepseek-chat',
    apiUrl: 'https://api.deepseek.com/chat/completions',
  },
  {
    provider: 'qwen',
    label: '通义千问 / DashScope',
    model: 'qwen-plus',
    apiUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
  },
  {
    provider: 'kimi',
    label: 'Kimi / Moonshot',
    model: 'moonshot-v1-8k',
    apiUrl: 'https://api.moonshot.cn/v1/chat/completions',
  },
  {
    provider: 'zhipu',
    label: '智谱 GLM',
    model: 'glm-4-flash',
    apiUrl: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
  },
  {
    provider: 'qianfan',
    label: '百度千帆',
    model: 'ernie-4.0-turbo-8k',
    apiUrl: 'https://qianfan.baidubce.com/v2/chat/completions',
  },
  {
    provider: 'hunyuan',
    label: '腾讯混元',
    model: 'hunyuan-lite',
    apiUrl: 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions',
  },
];

const props = defineProps({
  settings: {
    type: Object,
    default: () => ({}),
  },
});
const emit = defineEmits(['saved', 'back']);

const form = reactive({
  enabled: false,
  provider: 'deepseek',
  model: 'deepseek-chat',
  api_url: 'https://api.deepseek.com/chat/completions',
  api_key: '',
});
const saving = ref(false);
const error = ref('');

const providerOptions = computed(() => {
  const options = Array.isArray(props.settings.provider_options) && props.settings.provider_options.length
    ? props.settings.provider_options
    : DEFAULT_PROVIDER_OPTIONS;
  return options
    .map((item) => ({
      provider: item.provider,
      label: item.label || item.display_name || item.provider,
      model: item.model || item.default_model || '',
      apiUrl: item.apiUrl || item.api_url || '',
    }))
    .filter((item) => item.provider);
});

function providerOption(provider) {
  return providerOptions.value.find((item) => item.provider === provider);
}

watchEffect(() => {
  const provider = props.settings.provider || 'deepseek';
  const option = providerOption(provider);
  form.enabled = Boolean(props.settings.enabled);
  form.provider = provider;
  form.model = props.settings.model || option?.model || 'deepseek-chat';
  form.api_url = props.settings.api_url || option?.apiUrl || 'https://api.deepseek.com/chat/completions';
});

function applyProviderDefaults() {
  const option = providerOption(form.provider);
  if (!option) return;
  form.model = option.model;
  form.api_url = option.apiUrl;
}

function providerLabel(provider) {
  return providerOption(provider)?.label || provider;
}

function apiKeyLabel(provider) {
  return `${providerLabel(provider)} API key`;
}

async function save() {
  saving.value = true;
  error.value = '';
  try {
    const payload = await saveLlmSettings({ ...form });
    form.api_key = '';
    emit('saved', payload);
  } catch (exc) {
    error.value = exc.message || '保存失败，请检查配置。';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="page-section narrow-section">
    <button class="secondary-button inline-button" type="button" @click="emit('back')">
      返回数据源
    </button>
    <div>
      <p class="kicker">本机配置</p>
      <h2>LLM 设置</h2>
      <p>密钥保存在本机。页面只显示是否已配置，不回显明文。</p>
    </div>
    <form class="form-stack" @submit.prevent="save">
      <label class="checkbox-row">
        <input v-model="form.enabled" type="checkbox" />
        <span>启用 LLM</span>
      </label>
      <label>
        <span>Provider</span>
        <select v-model="form.provider" @change="applyProviderDefaults">
          <option
            v-for="option in providerOptions"
            :key="option.provider"
            :value="option.provider"
          >
            {{ option.label }}
          </option>
        </select>
      </label>
      <label>
        <span>Model</span>
        <input v-model="form.model" type="text" autocomplete="off" />
      </label>
      <label>
        <span>API URL</span>
        <input v-model="form.api_url" type="url" autocomplete="off" />
      </label>
      <label>
        <span>{{ apiKeyLabel(form.provider) }}</span>
        <input v-model="form.api_key" type="password" autocomplete="off" />
      </label>
      <p class="state-line">
        当前密钥状态：{{ settings.api_key_configured ? '已配置' : '未配置' }}
      </p>
      <p v-if="error" class="error-line">{{ error }}</p>
      <button class="primary-button" type="submit" :disabled="saving">
        {{ saving ? '保存中' : '保存设置' }}
      </button>
    </form>
  </section>
</template>
