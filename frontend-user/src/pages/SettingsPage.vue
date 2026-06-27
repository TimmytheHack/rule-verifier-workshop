<script setup>
import { reactive, ref, watchEffect } from 'vue';
import { saveLlmSettings } from '../api/settings.js';

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

watchEffect(() => {
  form.enabled = Boolean(props.settings.enabled);
  form.provider = props.settings.provider || 'deepseek';
  form.model = props.settings.model || 'deepseek-chat';
  form.api_url = props.settings.api_url || 'https://api.deepseek.com/chat/completions';
});

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
        <input v-model="form.provider" type="text" autocomplete="off" />
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
        <span>API key</span>
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
