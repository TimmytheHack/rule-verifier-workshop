<script setup>
import { computed } from 'vue';

const props = defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  result: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['update:modelValue']);

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

function tagType(status) {
  return status === 'PASS' || status === 'pass' ? 'success' : 'danger';
}

function statusLabel(status) {
  return status === 'PASS' || status === 'pass' ? '通过' : '未执行';
}

const title = computed(() => {
  if (!props.result) {
    return '';
  }
  return props.result.title || props.result.university_name || props.result.item_id;
});

const subtitle = computed(() => {
  if (!props.result) {
    return '';
  }
  if (props.result.subtitle) {
    return props.result.subtitle;
  }
  return [
    props.result.group_code,
    props.result.major_name,
    props.result.city,
  ].filter(Boolean).join(' · ');
});

const traceItems = computed(() => {
  if (!props.result) {
    return [];
  }
  if (Array.isArray(props.result.matched_filters)) {
    return props.result.matched_filters.map((item) => ({
      status: item.matched ? 'pass' : 'not_executed',
      text: item.text || `${item.field} ${item.operator} ${item.value}`,
    }));
  }
  return props.result.trace || [];
});
</script>

<template>
  <el-drawer
    v-model="visible"
    size="520px"
    title="行级追踪"
    append-to-body
  >
    <template v-if="result">
      <div class="trace-heading">
        <h2>{{ title }}</h2>
        <p>{{ subtitle }}</p>
      </div>

      <el-alert
        class="inline-alert"
        type="warning"
        :closable="false"
        show-icon
        title="中外合作仅标记为未执行：缺少合作办学类型字段，未参与过滤。"
      />

      <div class="trace-list">
        <div
          v-for="item in traceItems"
          :key="`${item.status}-${item.text}`"
          class="trace-item"
        >
          <el-tag :type="tagType(item.status)" effect="dark">
            {{ statusLabel(item.status) }}
          </el-tag>
          <span>{{ item.text }}</span>
        </div>
      </div>
    </template>
  </el-drawer>
</template>
