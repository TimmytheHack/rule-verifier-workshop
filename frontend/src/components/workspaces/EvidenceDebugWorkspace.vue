<script setup>
import CandidateConfirmation from '../CandidateConfirmation.vue';
import ExtractedPreferences from '../ExtractedPreferences.vue';
import RuleSummaryCards from '../RuleSummaryCards.vue';
import VerificationAudit from '../VerificationAudit.vue';

defineProps({
  runData: {
    type: Object,
    required: true,
  },
});
</script>

<template>
  <section class="workspace-panel detail-workspace evidence-debug-workspace">
    <el-card class="workbench-card evidence-debug-header-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>证据调试</h2>
            <p class="panel-copy">这里展示规则、候选、抽取和 verification 细节，不代表额外筛选已经执行。</p>
          </div>
          <el-tag effect="plain">调试</el-tag>
        </div>
      </template>
    </el-card>
    <RuleSummaryCards
      :deterministic-rules="runData?.deterministic_rules || []"
      :candidate-rules="runData?.candidate_rules || []"
      :not-executed-preferences="runData?.not_executed_preferences || []"
      :executable-rules="runData?.executable_rules || []"
    />
    <CandidateConfirmation
      :candidate-rules="runData?.candidate_rules || []"
      :confirmations="runData?.simulated_confirmations || {}"
    />
    <ExtractedPreferences :preferences="runData?.extracted_preferences || []" />
    <VerificationAudit
      :grounding="runData?.attribute_grounding || {}"
      :proposed-rules="runData?.proposed_rules || []"
    />
  </section>
</template>
