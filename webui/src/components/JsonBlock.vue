<template>
  <pre>{{ formatted }}</pre>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  data: {
    type: [Object, Array, String, Number, Boolean],
    default: undefined,
  },
});

const formatted = computed(() => {
  if (props.data === undefined) {
    return "undefined";
  }
  try {
    return JSON.stringify(props.data, null, 2);
  } catch (_err) {
    return String(props.data);
  }
});
</script>
