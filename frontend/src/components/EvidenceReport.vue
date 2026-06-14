<script setup>
defineProps({
  report: {
    type: Object,
    required: true,
  },
});
</script>

<template>
  <el-card class="workbench-card report-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>证据回答</h2>
        </div>
        <el-tag type="warning" effect="plain">规则验证结果</el-tag>
      </div>
    </template>

    <el-alert
      class="inline-alert"
      type="warning"
      :closable="false"
      show-icon
      title="这不是最终志愿建议。"
    />

    <article class="report-body">
      <h3>{{ report.title }}</h3>
      <p class="report-summary">{{ report.summary }}</p>
      <p class="count-line">{{ report.result_count_text }}</p>

      <section>
        <h4>已执行规则</h4>
        <div class="tag-list">
          <el-tag
            v-for="rule in report.executed_rules"
            :key="rule"
            type="success"
            effect="light"
          >
            {{ rule }}
          </el-tag>
        </div>
      </section>

      <section>
        <h4>重点结果</h4>
        <ol class="report-list">
          <li v-for="item in report.top_results" :key="item">{{ item }}</li>
        </ol>
      </section>

      <section v-if="report.full_text">
        <el-collapse>
          <el-collapse-item title="展开完整证据文本" name="full-report">
            <pre class="full-report-text">{{ report.full_text }}</pre>
          </el-collapse-item>
        </el-collapse>
      </section>

      <section>
        <h4>警告</h4>
        <el-alert
          v-for="warning in report.warnings"
          :key="warning"
          class="report-warning"
          type="error"
          :closable="false"
          show-icon
          :title="warning"
        />
      </section>

      <p class="disclaimer">{{ report.disclaimer }}</p>
    </article>
  </el-card>
</template>
