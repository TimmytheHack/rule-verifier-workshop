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
