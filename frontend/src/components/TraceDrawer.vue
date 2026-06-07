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
        <h2>{{ result.university_name }}</h2>
        <p>
          {{ result.group_code }} · {{ result.major_name }} · {{ result.city }}
        </p>
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
          v-for="item in result.trace"
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
