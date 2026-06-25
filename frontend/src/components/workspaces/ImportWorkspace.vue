<script setup>
const props = defineProps({
  activeSource: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['source-ready', 'open-review']);

const emitSourceReady = (payload) => emit('source-ready', payload);
const openReview = () => emit('open-review');
</script>

<template>
  <section class="workspace-panel single-scroll import-workspace">
    <slot
      :active-source="props.activeSource"
      :emit-source-ready="emitSourceReady"
      :open-review="openReview"
    />
  </section>
</template>
